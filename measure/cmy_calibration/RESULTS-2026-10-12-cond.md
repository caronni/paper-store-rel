# G13's channel — the conditioned decode's construction constant (2026-10-12)

The question (src/holo/receiver/docs/CMY-RECEIVER-PLAN.md A6; docs/CMY-DESIGN.md §7 (e), R5, §11 G13): G13 needs,
per order, a channel on which BICM fails and the conditioned attempt certifies. On a measured confusion the
conditioning gain is under one rung step, so the design scales one: C_alpha = (1 − alpha)·I + alpha·Ĉ over e043c
sheet 3's c2 state confusions (B1, B14). Which row and which alpha meet the construction criteria — the sibling plain
BLER ≤ 0.05 at the scan's budget, the target BICM BLER ≥ 0.9 at the retry's, the target conditioned BLER ≤ 0.1 at
cond150's — chosen on seeds disjoint from the test's?

**Answer, measured: the (R*, alpha*) table** (`test_h3_cmy_cond.G13_ROWS` / `G13_ALPHA`):

| order | row | alpha* | B1: sibling / BICM / cond BLER | B14: sibling / BICM / cond BLER | full margin |
|---|---|---|---|---|---|
| hi given lo | `c2-cmy-r0700x0547@10x10` | 1.875 | 0.012 / 0.996 / 0.008 | 0.031 / 0.926 / 0.000 | 0.019 |
| lo given hi | `c2-cmy-r0547x0625@10x10` | 2.0 | 0.000 / 0.969 / 0.008 | 0.000 / 1.000 / 0.031 | 0.050 |

256 trials per shape at alpha* (the confirm stage). 0 false accepts in 36,832 trial-cells over every stage and arm;
34 syndrome-valid decodes the CRC refused (consistent with the frozen rungs' CRC-caught floor, RUNG-LADDER-STUDY §7.4; not attributed). The window
is narrow on both orders — about 1/8 in alpha between "BICM certainly fails" and "the conditioned attempt stops
certifying" — and the hi-given-lo margin is set by B14, where lo at r0547 (the sibling) and hi BICM both sit near
their thresholds at once. Synthetic channel, no paper — NO promotion; the table is a construction constant.

**Provenance.** `measure/cmy_calibration/cond_gate.py` (uncommitted when this was written), run on machine 1 on the
`cmy-generator` worktree at 0f60ad7c plus the A6 working tree (`tiles.cond`; the stimulus, `g13_tile`, imported from
the uncommitted `src/holo/receiver/tests/test_h3_cmy_cond.py`, unchanged since). Confusions from
`scratch2/e043c/readout/summary.json` (sha256 `6b4c6eed…`; scan `E043-m281-cmy-probe3-a-scan.tiff`, `85894c27…`),
bands B1 and B14, checked equal to the test module's literal counts by the instrument at every stage. Artefacts NOT
committed: `scratch2/e043c/cond/` — `cond_gate.json` (sweep), `cond_gate_refine.json`, `cond_gate_confirm.json` (the
JSONs of record), their logs, `tree-head.txt`, and the two superseded runs named below.

```
cd <repo> && PYTHONPATH=src:. \
    env/bin/python -u -m measure.cmy_calibration.cond_gate --stage sweep --workers 8
... --stage refine --workers 8      # sweep 1,103 s, refine 832 s, confirm 191 s wall at 8 threads
... --stage confirm --workers 8
... --stage report [--full]
```

## Method

- **Trial.** One fresh tile of the row: random user bits per label stream, the receiver's frame encoder XOR the
  row's dither, the label pair to a state per payload cell (`CMY_LABEL_TO_STATE`), each state read through C_alpha
  at one uniform per cell (inverse CDF), each cell scored by the channel's exact W-relative log-likelihood ratios,
  laid through the tile's cell permutation onto its payload cells. A trial's bits and uniforms come from its entropy
  (root, index), so every alpha of a trial shares them (common random numbers).
- **Arms**, all through the production `tiles.attempt_tile`: the sibling plain at 60 iterations; the target BICM at
  60 and 150 (success at 60 implies success at 150, BP being deterministic and stopping at the first valid
  syndrome); the target conditioned on the sibling's TRUE label bits at 60 and 150. Success = certified with the
  true user bits.
- **Rows.** Seven rung pairs per order, the target's rung above the sibling's: hi given lo r0625×0547 …
  r0850×0775, lo given hi mirrored.
- **Stages, each on its own root:** sweep (2026101213) — alpha 0.25 to 3.0 by 1/8, 24 trials per cell; refine
  (2026101215) — around every row's near-feasible coarse cells (both shapes BICM ≥ 0.75, cond ≤ 0.25, sibling ≤
  0.10), 1/32 steps, 64 trials, THE PICK = the largest margin min(BICM − 0.9, 0.1 − cond) over both shapes with the
  sibling ≤ 0.05 as a cut, ties to the higher target rung; confirm (2026101214) — the picked row's whole feasible
  window, 256 trials, ALPHA* = the largest full margin min(BICM − 0.9, 0.1 − cond, 0.05 − sibling) over both shapes.
  The test's root is 2026101206.
- **Superseded, kept:** `pilot-v1-*` — the sweep stage before the stimulus moved into the test module (seeds laid
  out differently; same landscape: hi given lo feasible only at single coarse points); `first-confirm-*` — the
  confirm of the refine's single alpha (hi given lo at 1.90625): B14's sibling missed its criterion, 15/256 = 0.059
  against 0.05, which is why ALPHA* reads the whole window with the sibling in the margin. The widened confirm
  reproduces that alpha's cells to the last trial (one root, common random numbers).

## The window, refine (64 trials; sibling / BICM@150 / cond@150 BLER, margin without the sibling term)

| alpha | hi given lo, r0700×0547: B1 | B14 | margin |
|---|---|---|---|
| 1.75 | 0.000 / 0.969 / 0.000 | 0.000 / 0.750 / 0.000 | −0.150 |
| 1.8125 | 0.000 / 0.984 / 0.000 | 0.000 / 0.844 / 0.000 | −0.056 |
| 1.84375 | 0.000 / 1.000 / 0.000 | 0.016 / 0.922 / 0.000 | 0.022 |
| 1.875 | 0.000 / 1.000 / 0.016 | 0.031 / 0.969 / 0.000 | 0.069 |
| 1.90625 | 0.000 / 1.000 / 0.016 | 0.031 / 0.984 / 0.000 | 0.084 (the pick) |
| 1.9375 | 0.000 / 1.000 / 0.047 | 0.016 / 1.000 / 0.000 | 0.053 |
| 1.96875 | 0.000 / 1.000 / 0.031 | 0.047 / 1.000 / 0.000 | 0.069 |
| 2.0 | 0.000 / 1.000 / 0.062 | 0.062 / 1.000 / 0.000 | sibling out |

| alpha | lo given hi, r0547×0625: B1 | B14 | margin |
|---|---|---|---|
| 1.875 | 0.000 / 0.891 / 0.000 | 0.000 / 0.953 / 0.000 | −0.009 |
| 1.9375 | 0.000 / 0.938 / 0.000 | 0.000 / 1.000 / 0.000 | 0.037 |
| 2.0 | 0.000 / 0.984 / 0.000 | 0.000 / 1.000 / 0.000 | 0.084 (the pick) |
| 2.03125 | 0.000 / 0.984 / 0.000 | 0.000 / 1.000 / 0.031 | 0.069 |
| 2.0625 | 0.016 / 1.000 / 0.000 | 0.000 / 1.000 / 0.094 | 0.006 |
| 2.125 | 0.000 / 1.000 / 0.000 | 0.000 / 1.000 / 0.156 | −0.056 |

Every refined row (margin without the sibling term; feasible alphas): hi given lo — r0700×0547 1.84375–1.96875
(5), r0775×0625 1.15625–1.28125 (5, best 0.069), r0850×0700 0.625 (1, 0.022), r0850×0775 0.59375 (1, 0.006); lo
given hi — r0547×0625 1.90625–2.0625 (6), r0547×0700 1.375–1.46875 (4, 0.069), r0625×0700 1.40625–1.53125 (5,
0.069), r0625×0775 0.9375 (1, 0.022), r0700×0775, r0700×0850 and r0775×0850 none. A target at r0850 has the
narrowest window in both orders.

## The confirm (256 trials; sibling / BICM@60 / BICM@150 / cond@60 / cond@150 BLER)

| order | shape | alpha | | | | | |
|---|---|---|---|---|---|---|---|
| hi given lo | B1 | 1.84375 | 0.012 | 0.988 | 0.988 | 0.008 | 0.008 |
| hi given lo | B1 | **1.875** | 0.012 | 0.996 | 0.996 | 0.008 | 0.008 |
| hi given lo | B1 | 1.90625 | 0.008 | 1.000 | 1.000 | 0.012 | 0.008 |
| hi given lo | B14 | 1.84375 | 0.020 | 0.922 | 0.898 | 0.000 | 0.000 |
| hi given lo | B14 | **1.875** | 0.031 | 0.941 | 0.926 | 0.000 | 0.000 |
| hi given lo | B14 | 1.90625 | 0.059 | 0.973 | 0.953 | 0.000 | 0.000 |
| lo given hi | B1 | 1.96875 | 0.000 | 0.961 | 0.949 | 0.008 | 0.008 |
| lo given hi | B1 | **2.0** | 0.000 | 0.973 | 0.969 | 0.008 | 0.008 |
| lo given hi | B1 | 2.03125 | 0.000 | 0.988 | 0.980 | 0.016 | 0.012 |
| lo given hi | B14 | 1.96875 | 0.000 | 0.996 | 0.992 | 0.031 | 0.016 |
| lo given hi | B14 | **2.0** | 0.000 | 1.000 | 1.000 | 0.035 | 0.031 |
| lo given hi | B14 | 2.03125 | 0.000 | 1.000 | 1.000 | 0.059 | 0.055 |

cond150 against cond60 moves at most 0.016 at alpha* (B14 lo given hi 0.035 → 0.031); the refine's pick is the same
at either budget for hi given lo, and for lo given hi the cond60 pick is the same row and alpha with a smaller margin
(0.069 against 0.084).

## What the test then measured (test_h3_cmy_cond, root 2026101206, 32 fresh tiles per shape and order)

Per (shape, order) the tiles off "sibling certifies, BICM fails, conditioned certifies": B1 hi given lo tile 10
(the sibling failed, nothing conditioned), B1 lo given hi tile 2 (BICM certified), B14 hi given lo tile 31 (BICM
certified), B14 lo given hi none — 124 of 128 tiles certify through the conditioned attempt alone, every
certificate the stimulus's user bits. The negative arms on the 125 tiles that need their sibling: another tile's
sibling minted nothing and reached the CRC never (0 consults of 125); the sibling's bits with 10 % flipped minted
ONE certificate, the TRUE bits (B1 lo given hi tile 12, 420 of 3,976 bits flipped), and no other CRC consult —
a sibling 90 % right still carries most of the conditioning. No negative arm minted a wrong certificate.
