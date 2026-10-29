# Platen angle vs window placement — what the leftover orange windows cost

Read-only post-mortem, 2026-08-31.  Every number below is a count of
recorded events or a function of recorded poses.  No decode was run and
no repo file outside this scratch directory was touched.

Sources (all four are finished runs):

| run | file | captures |
|---|---|---|
| sheet I, from scratch | `/tmp/I/holo3-I-first-run/events.jsonl` (261,500 events) | 3 x 2400 dpi |
| sheet I, resume + 4800 | `/tmp/I/holo3-I-resume-3-run/events.jsonl` | +1 x 4800 dpi |
| **sheet H, seven-capture max-stack** | `scratch/holo3-overnight-events/sheetH-maxstack-events.jsonl.xz` (1.48 M events) | 7 (2x1200, 2x2400, 3x4800) |
| sheet H, mixed | `scratch/holo3-overnight-events/sheetH-mixed-events.jsonl.xz` | 4 (a subset of the same physical captures) |

The sheet-H max-stack run is the primary dataset: seven captures give
real angle spread and, because the same angle appears at different
scanner resolutions, it separates angle from dpi.

---

## 0. What "orange" actually is

From `holo3/diag/panes.py` (the capture pane) and `holo3/diag/model.py`
(the window census):

* a window enters `model.windows` on `WindowScheduled`;
* it is **removed** by an accepted `PoseCommitted`, by `WindowRetired`,
  or by a `WindowSettled` whose state is `done_covered`;
* it is drawn **orange** when it is still in the dict and carries a
  settle cause; **purple** when it is in the dict with no cause.

So an orange chip at the end of a run is exactly: *a window that was
scheduled, was refused at least once, was never placed, was never
retired, and was never suppressed by done-geometry.*

`report.json`'s `live_windows` is that same dict, but the diag key drops
`level_index`, so windows at different scale lanes with the same extent
collide.  Every census below is keyed by
`(capture, level, region, extent)`.  The level-aware totals reproduce the
report's within a few counts (sheet I: 61/52/25, sum 138, exact match;
sheet H: 49/1233/653/51/212/142/1448 vs the report's
49/1233/651/46/201/132/1442).

**In all four runs, `purple` at end-of-run is 0 and `done_covered` fired
exactly 0 times.**  The done-geometry gate is wired
(`place.py:675`, `place_sched.py:123`) but never triggered in any of
these runs.  That settles one of the questions up front: the leftover
windows are **not** certificate shadow produced by the done gate — they
are genuine placement refusals.

---

## 1. Angle per capture (recorded poses only)

Angle is read off each committed pose's `native_affine` with the diag
viewer's own estimator, `panes._rotation_deviation_deg`: the deviation
of the fitted cell-x axis from axis-aligned, taken modulo 90 deg so the
quarter-turn (`rot_k`) does not contaminate it.  The per-capture figure
is the median over all that capture's committed poses.

### Sheet H, seven-capture max-stack

| ord | dpi | poses | median angle | = mrad | sd | rot_k |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1200 | 741 | **-0.0585 deg** | -1.020 | 0.102 | 0 |
| 1 | 1200 | 573 | **-0.7412 deg** | -12.937 | 0.324 | 0 |
| 2 | 2400 | 1445 | **-0.4818 deg** | -8.410 | 0.297 | 2 |
| 3 | 2400 | 1079 | **+0.0595 deg** | +1.038 | 0.087 | 2 |
| 4 | 4800 | 1690 | **-0.2011 deg** | -3.510 | 0.162 | 0 |
| 5 | 4800 | 1604 | **-0.1500 deg** | -2.618 | 0.125 | 0 |
| 6 | 4800 | 1076 | **-1.0542 deg** | -18.400 | 0.158 | 0 |

Spread: 18x, from 1.0 mrad to 18.4 mrad.  Two of the seven were also
laid down 180 deg round (`rot_k` 2), which the receiver absorbs without
comment.

### Sheet I

| run | ord | dpi | poses | median angle | = mrad | rot_k |
|---|---:|---:|---:|---:|---:|---:|
| first | 0 (`a410631d`, *displaced*) | 2400 | 1021 | **-0.0697 deg** | -1.217 | 0 |
| first | 1 (`36b90a50`, *displaced2*) | 2400 | 1064 | **+0.1690 deg** | +2.950 | 0 |
| first | 2 (`269d8121`, plain) | 2400 | 1023 | **+0.0387 deg** | +0.675 | 0 |
| resume-3 | 3 (`5d242053`) | 4800 | 579 | **-0.5547 deg** | -9.682 | 2 |

The two deliberate re-placements are indeed the two more-rotated 2400
captures, but only by 1.8x and 4.4x over the plain scan, and all three
are under 0.17 deg.  **Sheet I alone has insufficient angle spread to
test the question** — see §3.

---

## 2. Residue per capture

"Orange" = end-state settled-refused, per §0.  "keys" counts every
distinct window the scheduler minted for that capture (parents plus
subdivided children).

### Sheet H max-stack

| ord | \|angle\| | keys | posed | **orange** | causes |
|---:|---:|---:|---:|---:|---|
| 0 | 0.0585 | 790 | 741 | **49** | consult_refused 49 |
| 3 | 0.0595 | 1130 | 1079 | **51** | consult 50, straddle 1 |
| 5 | 0.1500 | 1752 | 1604 | **142** | consult 140, cold 2 |
| 4 | 0.2011 | 1908 | 1690 | **212** | consult 209, cold 3 |
| 2 | 0.4818 | 2102 | 1445 | **653** | consult 636, cold 16, straddle 1 |
| 1 | 0.7412 | 1808 | 573 | **1233** | consult 1163, cold 65, straddle 5 |
| 6 | 1.0542 | 2528 | 1076 | **1448** | consult 1356, cold 91, straddle 1 |

### Sheet I first run

| ord | \|angle\| | keys | posed | **orange** | causes |
|---:|---:|---:|---:|---:|---|
| 2 | 0.0387 | 1062 | 1023 | **25** | consult 22, straddle 2, cold 1 |
| 0 | 0.0697 | 1158 | 1021 | **61** | consult 55, cold 5, straddle 1 |
| 1 | 0.1690 | 1190 | 1064 | **52** | consult 50, cold 2 |

Sheet I resume-3, 4800 capture at 0.5547 deg: keys 1664, posed 579,
**orange 203** (consult 117, cold 84, straddle 2).

Every orange window fired at least one job — `orange_never_fired` is 0
everywhere.  Nothing sits parked; the residue is worked and refused,
repeatedly.  The full settle ledger (every refused pass, not just the
last) shows each of these windows walking the whole ladder
`word_centre -> word_rest -> wide -> cold_live` and then being
re-consulted about four times: sheet H ord6 logs 5,959 `consult_refused`
settles over 1,448 windows that end orange.

---

## 3. The correlation

**Sheet H max-stack, n = 7: Spearman rho(|angle|, orange) = +1.0000.**
The rank orders are identical, element for element.  Exact one-sided
permutation p = 1/5040 = 0.0002.

**Sheet H mixed, n = 4 (a different run over four of the same physical
captures, different scheduling): rho = +1.0000, exact p = 0.042.**

**Sheet I first run, n = 3: rho = +0.50 — insufficient spread.**  All
three angles lie within 0.13 deg of each other and the two smallest
(0.0387 / 0.0697) sit in the flat part of the curve where the ordering
is noise.  Sheet I neither confirms nor contradicts; it simply cannot
resolve the question.  Add its 4800 capture (0.5547 deg -> 203 orange,
64.7% coarse-lane failure) and it falls right on the sheet-H curve.

**The dpi confound is dead.**  Each scanner resolution appears at both
ends of the angle range, and within every resolution the more-angled
capture carries an order of magnitude more residue:

| dpi | straight | angled | ratio |
|---|---|---|---|
| 1200 | 0.0585 deg -> 49 | 0.7412 deg -> **1,233** | **25.2x** |
| 2400 | 0.0595 deg -> 51 | 0.4818 deg -> **653** | **12.8x** |
| 4800 | 0.1500 deg -> 142 | 1.0542 deg -> **1,448** | **10.2x** |

Pooling all eleven captures from both sheets (§5 table):
rho(|angle|, coarse-lane failure rate) = **+0.964**, and the *linear*
correlation is +0.984 — the relationship is close to proportional, not
merely monotone.

**Verdict: yes, platen angle troubles window placement, and the effect
is large, monotone, and not a resolution artifact.**

---

## 4. Spatial structure — it is angle itself, not the platen sweet spot

If angle worked by pushing part of the sheet out of the scanner's good
region or off the crop, the refusals would pile up on one side or at the
edges.  They do not.

Comparing the median normalised distance-to-nearest-region-edge of
orange windows against posed windows, sheet H max-stack:

| ord | \|angle\| | edge-frac orange | edge-frac posed |
|---:|---:|---:|---:|
| 0 | 0.0585 | 0.296 | 0.261 |
| 1 | 0.7412 | 0.281 | 0.268 |
| 2 | 0.4818 | 0.279 | 0.295 |
| 6 | 1.0542 | 0.301 | 0.277 |

Indistinguishable.  The x- and y-marginals of the two big residues are
flat across the sheet — ord6's orange windows binned into ten columns
run `[124, 149, 141, 144, 148, 128, 156, 146, 168, 144]`, and its rows
`[114, 154, 142, 137, 137, 152, 137, 142, 156, 177]`.  Centroids sit at
0.50/0.50 of the region.  The residue is **page-wide and uniform**.

Sheet I's much smaller residue does lean toward the two x extremes
(median x at 0.74-0.85 of region width vs 0.51 for posed windows), but
that is 25-61 windows and is the ordinary boundary behaviour, not the
angle effect.

---

## 5. The mechanism: angle costs exactly one scale lane

Every capture is decoded on a ladder of decimated scale lanes; lane 0 is
always `ppc = 2` (two scanner pixels per printed cell), lane 1 is 4,
lane 2 is 8, lane 3 is 16.  Splitting the census by lane makes the whole
effect collapse onto one row:

### Sheet H max-stack — window failure rate per lane

| ord | \|angle\| | **lane 0 (2 px/cell)** | lane 1 (4) | lane 2 (8) | lane 3 (16) |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.0595 | **8.3%** | 1.2% | 3.1% | — |
| 0 | 0.0585 | **10.7%** | 0.0% | — | — |
| 5 | 0.1500 | **17.3%** | 0.9% | 3.0% | 3.0% |
| 4 | 0.2011 | **22.6%** | 1.4% | 2.3% | 1.7% |
| 2 | 0.4818 | **45.6%** | 0.6% | 0.9% | — |
| 1 | 0.7412 | **83.5%** | 0.0% | — | — |
| 6 | 1.0542 | **95.5%** | 0.6% | 0.6% | 0.6% |

Sheet I: lane 0 = 6.4% / 13.1% / 10.8% at 0.0387 / 0.0697 / 0.1690 deg,
and **64.7%** for the 4800 capture at 0.5547 deg.  Every finer lane on
every sheet-I capture is at or under 1.1%.

Pooled over all eleven captures, |angle| vs lane-0 failure rate:
Spearman +0.964, Pearson +0.984.

**Every lane with 4 or more pixels per cell places essentially
completely at any angle measured here, up to 1.05 deg.**  The most
extreme capture in the corpus, sheet H ord6 at 1.05 deg, placed
336 of 338 windows in each of its three fine lanes — and 68 of 1,514 in
lane 0.

Why lane 0.  At `ppc = 2` a printed cell is two pixels wide.  Across one
200-cell window the rotation shears the printed lattice by
`200 x 2 x tan(theta)` pixels: 0.4 px at 0.06 deg, but 7.3 px — 3.7 whole
cells — at 1.05 deg.  The window's own lattice fit still succeeds (there
is not a single `pose_refused` or `insufficient_support` settle in any
run), so the geometry is found; what fails is **addressing**.  The
dominant cause, 92-100% of every capture's residue, is
`consult_refused`: `place.local_search` takes a neighbour's committed
page affine, predicts this window's page origin, searches a +-3-cell box
around it (`NEIGHBOR_RADIUS_CELLS`), and then accepts only if the winning
origin lands within **2 cells** of the prediction
(`CONSISTENCY_CELLS = 2`) *and* clears the parity gates.  At 2 px/cell
with 3.7 cells of shear across the window, the sampled word sites are
smeared across cell boundaries and no origin in the box clears the gate.
At 8 or 16 px/cell the same rotation is resolved comfortably.

A secondary check rules out the obvious alternative.  Reconstructing the
chain prediction analytically from the recorded poses — for each posed
window, the address its nearest posed neighbour's affine would have
predicted, `e(c) = (J_S^-1 J_T - I)c + J_S^-1(t_T - t_S)` — the median
error is 0.32-0.41 cells for *every* capture and does not rank with angle
(rho +0.32).  So chain propagation between poses that *do* succeed is
healthy even at 1.05 deg.  The failure is local evidence quality in the
coarse lane, not accumulating geometric drift.

**The residue is also a subdivision cascade, not that many distinct
locations.**  A refused window subdivides (`place.subdivides`), so one
failed 200x200 parent becomes four 100x100 children that also fail.  On
the straight captures the orange are mostly parents (ord0: 33 of 49 are
200x200); on the angled ones they are mostly children (ord6: 1,150 of
1,448 are 100x100; ord1: 948 of 1,233).  The 1,448 chips on ord6's pane
represent roughly 300 distinct page locations, multiplied by the
subdivision ladder.

---

## 6. Cost

### CPU

| run | total run CPU | CPU on windows that end orange | share |
|---|---:|---:|---:|
| sheet H max-stack | 121,968 s | **8,679 s** over 36,215 jobs | **7.1%** |
| sheet H mixed | — | 4,271 s over 19,196 jobs | — |
| sheet I first | 175,681 s | **411 s** over 1,658 jobs | **0.23%** |

Per capture, the placement bill (place + refine.color, lane 0):

| ord | \|angle\| | lane-0 place CPU | premium over the ~0.06 deg baseline |
|---:|---:|---:|---:|
| 3 | 0.0595 | 272 s | — (baseline) |
| 0 | 0.0585 | 343 s | — (baseline) |
| 5 | 0.1500 | 521 s | +221 s |
| 4 | 0.2011 | 725 s | +425 s |
| 2 | 0.4818 | 1,769 s | +1,469 s |
| 1 | 0.7412 | 2,640 s | +2,340 s |
| 6 | 1.0542 | 2,985 s | +2,685 s |

Total angle premium in the seven-capture run: **~7,100 cpu-s, about 5.9%
of the run**.  Lane 0 absorbs 9,254 s of the 13,922 s spent on placement
across all lanes; placement itself is 11.4% of the run.  On sheet I,
with three near-straight 2400 captures, the whole premium is on the
order of 100-160 cpu-s and is not worth naming.

So: **the residue is not free, but it is cheap.**  A badly angled capture
costs roughly 2,500 cpu-s of wasted placement in a run whose real work
(colour conditioning, LDPC attempts) is two orders of magnitude larger.

### Yield — no measurable loss

**Page footprint.  Every capture in every run — angled or straight —
covers 1961/1961 page tiles with its committed poses.**  Losing lane 0
loses nothing in coverage because the finer lanes tile the page
completely.

Certificates attributable to each capture (from `JobDone.n_certificates`
on `tiles.scan` / `tiles.retry` jobs, whose subjects name the capture):

| run | straightest | most angled |
|---|---|---|
| H max-stack | ord0 0.059 deg -> 287 certs | ord1 0.741 deg -> **488 certs (the highest of all seven)**; ord6 1.054 deg -> 268 |
| H mixed | ord0 0.059 deg -> 807 | ord1 0.741 deg -> **1,027 (the highest of the four)** |
| I first | ord2 0.039 deg -> 4,346 | ord0 -> 219, ord1 -> 370 |

The two heavily angled sheet-H captures are the *best* certificate
producers in their runs.  Even ord6, which lost 95.5% of its coarse-lane
windows, still returned 179 certificates from that lane.

The sheet-I split (4,346 vs 219/370) is **ordering-confounded, not an
angle effect**: `269d8121` (ord2) is the first capture the scheduler
touches — it appears first in the `WindowScheduled` stream — so it
harvests the tiles and the later captures find them already certified.
Sheet H, where the first-scheduled capture (ord0) is *not* the top
producer, shows the confound does not dominate there.

**Are the leftover windows over ground that mattered?**  Two independent
checks say no:

1. **100% of orange windows sit on region ground the same capture
   already placed at some level** — 49/49, 1233/1233, 653/653, 51/51,
   212/212, 142/142, 1448/1448 on sheet H, and 61/61, 52/52, 25/25 on
   sheet I.  The residue is redundant coverage of already-addressed
   ground, never a hole.
2. Mapping orange window centres into page space through each capture's
   own recorded pose map (affine fit residual 0.79-0.96 cells median,
   well inside a 64-cell tile) and checking against the certified tile
   set: sheet I 84-92% of orange centres land on fully certified tiles
   against an 82.8% base rate; sheet H 26-35% against a 32.2% base rate.
   **At the base rate in both cases** — the leftovers are not sitting on
   the uncertified part of the page.

---

## 7. Answers

1. **Does platen angle trouble window placement?**  Yes, strongly and
   monotonically.  Seven captures, rho = +1.000, exact p = 0.0002,
   replicated at rho = +1.000 on an independent four-capture run, and
   robust to the scanner-resolution confound (10-25x more residue for
   the angled member of each same-dpi pair).

2. **Where does it bite?**  Only in the coarsest scale lane, `ppc = 2`.
   Failure there runs 6-13% at 0.04-0.07 deg and 95.5% at 1.05 deg.
   Every lane at 4 px/cell or better stays at or under ~3% at every
   angle measured.  The refusal is `consult_refused` (92-100% of every
   residue): the geometry is found but the address cannot be confirmed
   inside the +-2-cell consistency budget, because at two pixels per
   printed cell a degree of rotation shears the lattice by nearly four
   cells across a window.

3. **Is it an edge / sweet-spot effect?**  No.  The big residues are
   spatially uniform across the sheet; orange and posed windows sit at
   the same median distance from the region edge.  It is angle itself.

4. **Does it cost anything?**  CPU only, and modestly: ~7.1% of the
   seven-capture run's CPU sits on windows that end orange, roughly
   2,500 cpu-s per heavily angled capture, essentially all of it in the
   coarse lane's placement.  On the near-straight sheet-I run it is
   0.23%.

5. **Does it cost yield?**  No measurable loss.  Every capture, angled
   or not, ends with the full 1961-tile page footprint; the two most
   angled sheet-H captures were the top certificate producers in their
   runs; and 100% of the leftover windows sit on ground the same capture
   had already placed.

6. **Is the residue certificate shadow?**  Not by the done-geometry
   gate — `done_covered` fired 0 times in all four runs, so no window was
   ever suppressed as already-done.  These are real refusals.  They are
   nonetheless harmless, because the fine lanes had already covered the
   same ground.

### Two things worth the operator's attention

* **The done-geometry gate never fires.**  It is wired
  (`place.py:675`, `place_sched.py:123`) but produced zero
  `done_covered` settles across 1.9 M events and four runs.  Since 100%
  of the orange windows sit on already-placed ground, a working gate is
  exactly what would have retired them — and would have saved most of
  the 8,679 cpu-s in the seven-capture run and cleaned the pane.  Worth
  a look: either the gate's precondition (`store.done_cells`) is empty
  in practice, or `done_covers` is too strict.
* **The orange chips are honest but misleading to watch.**  They mark
  refusals in the *coarsest* lane only, over ground the fine lanes have
  already covered, inflated ~4x by subdivision.  A pane that separated
  lanes, or dimmed windows whose ground is placed elsewhere, would stop
  a good angled capture from looking like a failing one.
* **Deliberate angling remains a good idea.**  Nothing here argues
  against it — the diversity is free in yield and cheap in CPU.  If the
  cost ever matters, keeping the angle under ~0.2 deg holds coarse-lane
  failure under ~23%, and under 0.5 deg holds it under ~46%.
