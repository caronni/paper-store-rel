# The 2026-09-03/04 measurements and findings ledger

Companion to MEASUREMENTS-2026-08-31.md.  This file is the record of the
canonical-identity re-key repair, its independent review, and the swim
stimulus re-derivation — the numbers the decisions turned on, in one
place, because the session scratchpad that held them was wiped on a
process restart.  Commits: 6df81e7, 1b2c676, 07ac30a, 6cc9640, cc70bdd,
8b08736, c1757a6 on main; the swim re-derivation on branch
`review-followthrough`.

## What broke, and who

FORMAT-SPACE §16 (merged 2026-09-02 as b8471fc) made the canonical format
id the fully explicit spelling.  The canonical id IS the AES row seed, so
every v2 sim render re-keyed.  The merge re-froze the two BASE renders in
`_h3_sims.py` and was verified on the fast lane only ("holo3 fast lane
1770 passed").  Every value measured off a render went stale.

Bisected, not assumed: the slow lane (`HOLO3_RUN_SLOW_TESTS=1`) gave
**17 failed / 2151 passed** at HEAD and at 4d98851 (the merge tip, before
the diag split and the venv rebuild), and **0 failed** at 8260257, one
commit earlier.  The receiver diff across the merge is the family_seed ->
sites_seed rename (site bytes `holo/v1/sites/pN` unchanged) plus a
display_id field; place.py, words.py and pilots.py differ by that rename
only, and no scheduling, pricing, eligibility or retry file was touched.
`row.seed` is the only input that moved.  Package versions in env/ were
byte-identical to holo3's former pins.

## The seventeen, by mechanism

| class | cases | what moved | fix |
|---|---|---|---|
| derived goldens the merge forgot | 4 (+2 sweeps-gated) | rotated-raster shas are np.rot90 of the re-frozen bases | re-freeze; the array witness stayed green throughout |
| churn tripwire | 1 | K serial job counts (scan 88->99, retry 18->25, place 61->55, ctx 9->10); yield unchanged | re-pin |
| latent order bug | 1 | test_h3_multires hand-ordered the union key as (sha_b, sha_a); component_signature SORTS by capture sha; the re-freeze flipped the sort | `tuple(sorted(...))` |
| stimulus out of reach | 7 | degraded capture: its ENTIRE failure supply was one tile; the re-key flipped it to BP-success, so tiles.retry and tiles.local were never born | one edge of the keep box, see below |
| stimulus out of reach | 4 | local patch: the proof needs on >= 48 of 49 (MIN_METADATA_EQUATIONS) and off <= 47; the standing point fell to on 45 / off 44 | noise sd 49 -> 35, see below |

**Degraded keep box.** Noise sd (15/20/22/25/28/30/35/40) and four seeds
give an identical certificate set — the capture is erasure-limited and
the box is its only live dial.  Left edge 0.35 -> 0.3625 alone: 4
certificates, 8 attempted_failed, retry 3, local 2 — the pre-fork
structure, all eight failures on (3, 2) as 3 scan + 3 retry + 2 local
(measured on TileOutcome events).  Band (left-arm status, bracketed on
the mirrored box): 0.3575 certifies, 0.36 and 0.3625 reproduce the
shape, 0.365 gives 6 failed / retry 2, 0.37 falls below the floor.  Six
cells wide; inherent to one partially erased tile.

**Local patch noise.** 26 rungs over (smear, sd).  At smear 5.0: sd
30/32/33 both arms close (gain 0); 34 both 46; **35 on 48 VERIFIED / off
47 open, gain 1** (taken); 36 both 47; 37/38 46/45; 40/43 46; 46 45;
49 (old) 45/44 gain 1; 52/55 42.  Every other smear either closes both
arms or neither, except 4.75/47 (on 48 / off 47), which moves the smear
too.  The count is NOT monotone in the noise: 35 is a searched point, as
49.0 was.  The knife edge is inherent — on = 48 IS the quorum.

## The oracle-sweeps half (13 more, never reached by the slow lane)

A full sweeps run against the pre-fix tree took 3 h 30 m: 33 failed /
2189 passed; 17 the slow-lane set, 2 colour rotation shas already fixed,
1 an artefact of editing a module mid-run (inspect.getsource re-reads
from disk), 13 real.

- **uplift_existence.** A3's arm gain fell 29 -> 8 (frontier 15 -> 16).
  Both paths driven over one page agree exactly (tier gain 8,
  prepared-job minted 8, set difference zero) — not a seam bug; nothing
  in holo3/plugins moved — not the arm.  The proof survives (control
  gains zero, 8 disjoint from frontier, fit adopts, zero wrong).  A4b
  32 -> 36 ordinary, residue 16 -> 12; `conditioned > off` holds at
  39,590 vs 39,568 of 49,152 cells (margin 22).
- **color_field_yield.** Displacement costs 10 (all Y, floor 8); the
  field buys back all ten: control 300 / off 290 / on 300.  The
  shortfall pin emptied and stays pinned at empty.  Ledgers: dial-off
  {local 81, planek 9, scan 200}, dial-on {90, 10, 200}.  EPISODE 4 in
  the module docstring; the case renamed off the count.
- **plugins_local_ctx colour arm.** Page harder (control 288 -> 271,
  tier-on 294 -> 280); tier gain 6 -> 9, strict superset, all C, in the
  patch.  planek fires 15 (was 0).  Who MINTS the nine: local150 6,
  planek150 3 — pinned by source (the fires re-pin had silently deleted
  the implicit planek-mints-nothing pin).
- **e2e_sims colour serial.** 80 -> 81 certificates for less work.
- **swim_existence.** Broken, not a number — below.
- **conventions wall budget.** Structural: `WALL_BUDGET_S` has fast and
  slow only; the sweeps lane is folded into "slow" and measured against
  140 s while running hours.  Left red; recommendation below.

## The independent review (four lenses, six adversarial checks)

Five findings confirmed, one downgraded.  Beyond the planek source pin
above: the swim docstring's mechanism was false (below); "byte-identical"
and "49/49 under --complete" were wrong as written; the degraded band
sentence mixed mirrored-box and one-edge readings; "THREE EPISODES"
headed four; two decodes were byte-identical duplicates (the steep pair's
control is the two-dot pair's control; the colour full-domain case
re-decoded decode_color_w1) and now share.  The review's own draft cell
counts for A4b were exactly 5x the run's — nothing is pinned that a run
did not print.

## The swim: re-derived to 4.5 by the yield principle

`tiles.swim` is per-plane: for each plane separately, per window, a
local affine searched within `translation_bound_dots` = one printed cell
(3.0 dots at c3) of the field's hint; the field publishes a per-plane
delta clamped at `MAX_DELTA_DOTS` = 2.0 (`lib/plane_field.py`).  Composed
reach ~5 dots from register, per plane.  The swim arms on
`OUTCOME_FAILED` attempts at ARMING_STAGES — the same facts retry and
local arm on — and retires when the address is certified.  A tile
misregistered far enough emits BELOW_FLOOR, not FAILED, and NO rescue
row is born: that arming gate, a sampler property, is the binding
ceiling, and at c3 it coincides with 2 + 3.

Measured, all with the field running (`--plane-fields`):

| amplitude | field alone | field + swim | swim's marginal gain |
|---|---|---|---|
| 3.0 (field-yield's stimulus) | — | 300/300 with swim held out | not needed |
| 4.0 (was STEEP) | 299 | 300 | 1 tile at 2026-08-31; **0** after the re-key — (9,3) taken by local150 |
| **4.5 (STEEP now)** | **200** (Y = 0; retry/local/planek fire 100 each, certify none) | **297** | 97: swim mints 20, local150 73, scan 4 |
| 5.0 | 200 | 200 | none; only tiles.scan fires |

My first reading — "the amplitude must be a whole dot, the only rung above
four is five, the axis is exhausted" — was WRONG: `plane_x_shift_dots`
rounds per row (the shift is whole dots; the amplitude never was, it was
3.5 once), and 4.0 was held by two fast-lane pins (`peak == 4`, which
4.5 also satisfies under banker's rounding; `STEEP == SHIFTED + 1.0`,
now re-scoped to an ordering).  The red case's claim becomes the causal
one: without the swim the plane stays at zero; with it, 97 return, 20
minted by the swim itself.  The confirming run (2026-09-04, the swim
module under both lane flags, 10 of 11 passed in 55:43, the eleventh red
on exactly this point) measured what happens without the swim at 4.5:
`tiles.retry`, `tiles.local` and `tiles.planek` each fire 100 times — the
count of Y tiles — and certify none.  Field-alone job counts: survey 1, place
606, color 50, tiles.scan 1083, fields 6, refine.color 44, revisit 40,
tiles.retry 100, tiles.local 100, tiles.planek 100.  So the earlier
phrasing "no rescue row is born" was inferred, not measured, and is
WRONG at 4.5: the Y tiles are ATTEMPTED and FAIL — the very fact the swim
arms on — and the floor mechanism belongs to 5.0 alone.  The exact-page
audit keeps zero-wrong and drops the completeness 4.0 had by luck (297
of 300).  The corrected case, re-run alone from the branch worktree: 1
passed in 1:03:45 — the 20/73/4 split and the field-alone rescue-row
counts are pinned by a passing run.  Independent review of the change
set (three lenses, 15 findings, 14 refuted on evidence) confirmed one:
both heavy tests still carried their 4.0-era names and docstrings —
renamed to the causal claim and the 297-of-300 sub-page claim, a dead
`>= 1` assert and an orphaned helper removed.

Exhausting the range is an instrument's job, not a lane's:
`measure/h3_swim.py run --amplitude-dots X` renders and decodes any
amplitude; a loop over 3.5/4.0/4.5/4.75/5.0 is two heavy decodes per
point (~35 min each) — an afternoon once, recorded here, not hours on
every sweeps pass.  The two modules together already pin the band's
ends.

## Recommendations left for the owner

- **Retire the wall tripwire** rather than add a sweeps budget: it is
  wall-clock, machine- and load-dependent, permanently tripped on all
  three lanes (fast ~50 s vs 15; slow ~315 vs 140; sweeps hours vs 140),
  and the mechanism-regression job it names is already done
  deterministically by the four job-count churn pins.  If cost ever
  needs pinning, `processor_seconds` per fixture is already recorded.
- test_h3_plugins_local_ctx crossed 1,000 lines (983 -> 1,047); the
  natural seam is the K half / colour half.
- FORMAT-SPACE §8 row 15's "must not be deleted at the sunset" is tagged
  as inference; it belongs with the open sunset ruling.
- retirement_docs-2026-09/DELETION-LOG.md still lists the slow lane as
  red with "a fix or re-freeze ruling is a Phase-2 prerequisite"; met.

## Process lessons (saved to memory)

Never edit a test module while a long lane runs from the same tree.
Measure a file's comment density before writing in it; stimulus records
go in the owning test module with a pointer in conftest.  A number a
reviewer hands you is a hypothesis until a run prints it.  For a
format-identity change, run every lane whose fixtures are rendered from
the format; the fast lane is not sufficient.
