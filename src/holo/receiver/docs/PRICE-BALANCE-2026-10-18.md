# The price balance of 2026-10-18 — branch `price-balance`

The owner's instruction, 2026-10-18, on the yield-over-CPU census
([measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md](../../../../measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md)):
balance the prices as the census proposes, minimal changes with the
largest yield-over-time effect, and explain what changed. Two commits
on a branch cut from main at `99ccff57` (the sched-lifecycle review's
repairs merged). Nothing here is measured on paper yet; §5 says how.

## 1. What changed, in one table

| row | before | after | why (the census) |
|---|---|---|---|
| `tiles.local` | 220 + 2·rung, FLAT — every re-fire of a tile-lane at the same price | 220 on the first fire, + 220 for every earlier fire of the tile-lane, + 2·rung (`220*n` on the printed ladder) | its re-fires are the dearest minting work on every colour sheet (fires six and up: 1,236 cpu-s per certificate on e046, 2,092 on e042's sheet I; 38–45 % of those runs' CPU for 1–3 % of their certificates) and, flat, they popped ahead of planek's and swim's first fires |
| `tiles.planek`, `tiles.swim`, `tiles.uplift` | `base × attempts if attempts else base` — the first TWO fires both at the base | base + base × earlier fires — the base once, then the base again per re-fire | the one convention for every residue row: a row never pays its base twice (the owner, 2026-10-18); literals unchanged (230, 240, 210/220) |
| `tiles.retry` on the **cmy** family | 20 + 2·rung, the payload band, beside scan/union/cond | 241 + 2·rung, stage `retry_cmy`: above every residue row's first fire (local 220, planek 230, swim 240), below cold placement (250) | on the e044 cmy pages the retry took 20–25 % of the run for 3–11 certificates (first fires at 300–600 cpu-s per certificate, later fires 2 at 2,500 then nothing on M4, 6 at 264 on M3) while local's first fire minted at 1.2 and swim's at 6 |
| `tiles.retry` on K, cmy7, cmy8 (confetti included) | 20 + 2·rung | unchanged | the retry pays there: cmy8's re-fires after a refit mint as well as its first fires (e046 57 / 18 / 8 at 81 / 187 / 124 cpu-s), confetti's first fires at 13 |
| `tiles.cond` | shared `_retry_cost` | its own `_cond_cost` = the scan's price, 20 + 2·rung, on every family | cond is the productive conditioned decode on cmy (75 and 131 certificates on e044 at 2.6–5.5 cpu-s each); it must not follow the retry up |
| the colour refit, the pooled context, the page field | 160 × fits performed; first fire 0 then 170 × n; 180 × n | unchanged | the refit is already additive through its store cell; the pooled context's free first fire is ruling 9, measured on J; the field is HELD (§3) |
| every base literal | — | unchanged | the yield numbers do not reorder the bases: local's FIRST fire mints at 1–38 cpu-s per certificate, planek's at 7–29, swim's at 6–255 by encoding; only local's re-fires were out of place |

The printed ladder, after (the generated block of [SCHEDULE.md](SCHEDULE.md)):

```
   220*n  tiles.local      local        *    (was flat 220)
   220*n  tiles.uplift     uplift_a4b   *
   230*n  tiles.planek     planek
   240*n  tiles.swim       swim
     241  tiles.retry      retry_cmy         (new; cmy only)
     250  place            cold_live
     260  place            cold_rest
```

The order it produces on a hard colour tile, by fire: local 220 →
planek 230 → swim 240 → the cmy retry 241 → local's second fire 440 →
planek's second 460 → swim's second 480 → local's third 660 … Every
residue row's first fire now precedes any row's second, which is what
the census found to be the whole prize: the cheap first fires of
planek (cmy8) and swim (cmy) stop waiting behind local's re-fires until
the sixth decile of the run.

## 2. The mechanism, exactly

- **Escalation** (`0853d2be`): the four residue cost functions
  (`local_ctx._local_cost`, `plane_k._planek_cost`, `swim._swim_cost`,
  `uplift._uplift_cost`) return `base + base × attempts + rung term`,
  where `attempts` is the bookmark's fire count so far (0 on the first
  fire; the engine counts a fire only after it happened, `engine._fill`).
  `schedule.escalating_prices` derives the `*n` mark from the
  multiplication by `attempts` in the cost function's AST, so the ladder
  prints `220*n tiles.local` with no hand edit. Nothing is capped: a row
  may fire as often as new evidence justifies, it just drifts behind
  cheaper work by its base each time.
- **The cmy retry** (`b638eab7`): `tiles_sched._retry_cost` charges
  `RETRY_CMY_COST + RUNG_COST × rung` when `store.row.family is
  Family.CMY`, else the payload price; `_retry_stage` names the stage
  `retry_cmy` on cmy so the declared `prices` tuple carries the literal
  and the ladder prints it; `_cond_cost` keeps cond at the scan's price.
  The literal is derived, not chosen: one above `swim.SWIM_COST`, and
  `241 + 2 × 4 = 249 < place.STAGE_COST["cold_live"] = 250` for the
  five-level 4800-dpi ladder the bound assumes (a c5 pitch or a forced
  dpi above 4800 would lay a sixth level and its retry at 251, above
  cold_live — the test derives the depth from
  `decimate.auto_ppc_levels` over c2–c4 so a deeper ladder fails the pin
  rather than drifting). The engine is untouched: cost is a scheduling
  function of the plugins alone, as ruled 2026-08-29.
- **The field, held** (the owner, 2026-10-18): `fields.collect` keeps
  180 × its fire ordinal and `fields` its flat 40. It keeps running as
  long as its inputs improve: every certificate on the page wakes the
  collect (it reads `page_certs`), and with the residue rows escalating
  too its second collect at 360 now pops before local's second fires at
  440 instead of behind the whole residue band — which is what froze
  e044 M2's field at 71 % support. The cadence rule (what the right
  re-collect trigger is) is a discussion of its own; the census note's
  §6 and the session transcript hold the candidates.

## 3. What is pinned, and what moved

- `test_h3_schedule`: `ESCALATING_GOLDEN` gains `tiles.local: (220,)`;
  the declared-price check asks the FIRST fire at `attempts 0` (the
  pooled context at its first priced fire, `attempts 1`, ruling 9) and
  evaluates `retry_cmy` on a cmy store; the generated block is pinned
  line for line.
- `test_h3_plugins_local_ctx`: the "no escalation" pricing test is
  replaced by one that asserts base + base × earlier fires and
  `220 < 230 < 240 < 440`.
- `test_h3_plugins_planek`, `_swim`: the additive shape; planek's
  "above every other residue row" check keys by (name, stage) and
  leaves out the cmy-only `retry_cmy`.
- `test_h3_plugins_uplift`: the measured ladder `[210, 210, 420, 630]`
  → `[210, 420, 630, 840]`, ledgered.
- `test_h3_plugins_tiles`: cost and stage per family at rungs 0 and 2,
  cond's price on every family, both inequalities from the literals.
- `test_h3_cmy_cond`: the G13 engine test now expects `{scan 1, cond 1}`
  and the cmy retry retired certified without firing — cond's
  certificate lands first at 20, which is the CPU the change saves. The
  contract this pins (on cmy, cond before retry) is the intended one;
  the owner may prefer the test to pin cond's certificate alone.
- No golden moved. No base literal moved.

## 4. Open after this branch

- The rung bound's assumption (five levels, rung index ≤ 4) is stated
  at the literal and pinned by depth; a sixth level needs
  `RETRY_CMY_COST` lowered or the rung term capped.
- The escalation step is the row's own base; a separate step literal
  per row is the owner's alternative if a different slope is wanted.
- Dynamic, yield-fed pricing (a row's price falling while its recent
  fires mint) is a design chip of its own: the subject-level half is
  this branch's escalation, the row-level half needs a wake, since the
  engine re-prices only upward at the pop (PRICING-ESCALATION F7).
- The resume re-walk at generation zero (ruling 13 of the study) is not
  a price; it stays owed.

## 5. How to measure it (every real run needs the owner's go)

One variable at a time, from a frozen snapshot, the same sha on both
arms, `--diag 8023`:

| arm | base | what it answers |
|---|---|---|
| e042 sheet I, resume from `scratch2/e042/I-M1`'s snapshot (close 56 short, planek's 368 all after the sixth decile) | `99ccff57` vs this tip | does the close come earlier, and from which rows, when local's re-fires no longer hold planek back |
| e046 M1 from scratch (two captures, closed at the fourth decile) | same pair | time to the close count and total CPU to exhaustion |
| e044 sheet A from one capture (`scratch2/E044-A-…-scan.tiff`, M2's capture) | same pair | the cmy retry's 20–25 % of CPU moved behind local and swim; the field's support at the close |

## 6. The merge gate

Run once on the branch tip `b638eab7` (2026-10-18, machine 1, the sims
re-decoded cold on the production change, the machine loaded): receiver
slow lane 2,600 passed / 34 skipped / 1 xfailed in 930 s, every sim
close VERIFIED at its pinned sha and no measured pin moved (the cmy e2e
records included, whose retry now sits at 241); default suite 1,922
passed / 90 skipped in 209 s. Per commit only the touched test modules
and the receiver fast lane ran (P1 2,241 passed, P2 2,254 passed).
