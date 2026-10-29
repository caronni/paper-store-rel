# Yield over CPU per row, by fire ordinal — the recent cmy / cmy8 / confetti runs (2026-10-18)

The owner's question: given the recent K, cmy and cmy8 decodes, do we
know which rows should be priced how, in what order and with what
escalation, to maximise yield over time? This note is the measurement
that answers what can be answered without a run: `yield_over_cpu.py`
(beside this file) over the run directories on machine 1, reading only.
Cumulative job cpu is the clock (events.jsonl has no timestamps). The
counterfactual — what a row would have minted had it run earlier — is
NOT in these numbers; only isolation arms from a frozen snapshot give it
(LADDER-RECONSIDERATION §7.3), and the instrument for those is the
unbuilt hatch pair of §7.2. No K run directory is on this machine; K
rests on the pricing study's archived sheets.

## 1. cmy8 (AltaLink, c2)

| row, by subject fire ordinal | e046 three-width, 2 captures, closed (`scratch2/e046/M1`) | e042 I r0850, 4 captures, stalled 56 short (`scratch2/e042/I-M1`) | I r0700, 1 capture, closed (`scratch/lifecycle-20260921/I-branch`) |
|---|---|---|---|
| scan + union, all fires | 3,264 certs at 1.2 cpu-s each, all in the first decile | 3,519 at 1.8, first two deciles | 4,467 at 0.2 |
| local, fire 1 | 1,257 at 10 | 526 at 38 | 655 at 5.6 |
| local, fire 2 | 120 at 91 | 35 at 519 | 37 at 75 |
| local, fires 3–5 | 64 at 452 | 45 at 1,020 | 7 at 640 |
| local, fires 6+ | 49 at 1,236 (45 % of the run's CPU) | 36 at 2,092 (38 % of the run) | 1 at 2,654 |
| planek, fire 1 | 305 at 7, none before the sixth decile | 357 at 14, none before the sixth decile | never fired |
| planek, fire 2 | 23 at 35 | 11 at 118 | — |
| retry, fires 1 / 2 / 3+ | 57 at 81 / 18 at 187 / 8 at 124 | 45 at 150 / 22 at 216 / 37 at 105 | 60 at 25 / 43 at 19 / 7 at 20 |
| swim | never fired | never fired (2,843 queued at the close) | never fired |
| field | 4 collects / 2 solves, 335 cpu-s (0.2 %), support 100 % | 8 / 7, 691 cpu-s (0.4 %), support 100 % | 2 / 2 |
| run | 173,051 jobs, 135,058 cpu-s, 5,165 certs | 286,140 jobs, 195,827 cpu-s, 4,633 certs | 48,091 jobs, 18,981 cpu-s, 5,277 certs |

Resumes: e042's `resume1` 71,291 jobs / 35,889 cpu-s for 59 (planek 30,
scan 17, union 9, local 3 for 21,803 cpu-s); e042 `I-M2` 3,104 cpu-s for
0; e046 `M2` 5,092 for 1 and `M3` 905 for 0.

## 2. cmy (M281)

| row, by subject fire ordinal | e044 M4, c2, 2 captures, complete (`scratch2/e044/M4`) | e044 M3, c3, 2 captures, complete (`scratch2/e044/M3`) |
|---|---|---|
| scan / union / cond, all fires | 232 at 10 / 62 at 20 / 118 at 5.5 | 388 at 2 / 64 at 7 / 131 at 2.6 |
| local, fire 1 | 2,966 at 1.2 | 967 at 1.2 |
| local, fire 2 / 3–5 / 6+ | 195 at 9 / 68 at 61 / 23 at 362 | 46 at 12 / 16 at 68 / 5 at 140 |
| swim, fire 1 / later | 132 at 6.4 / 51 at 23, only in the last three deciles | 29 at 8 / 7 at 34 |
| planek, fire 1 | 47 at 29 | 15 at 28 |
| retry, fire 1 / later | 6 at 604 / 2 at 2,500, then 1,564 cpu-s for 0 | 5 at 300 / 6 at 264 |
| field | 17 collects / 14 solves, 701 cpu-s (1.6 %), support 99 % | 11 / 10, 592 cpu-s, support 100 % |
| run | 150,835 jobs, 43,104 cpu-s, 3,904 certs | 61,091 jobs, 12,661 cpu-s, 1,680 certs |

e044 M2 (sheet A, ONE capture, stopped at the close): the field solved
twice at 71 % support and never again — its second collect at 2 × 180
sat behind the residue band (e044 §044.4).

## 3. Confetti (J3, cmy8 r0547, 3 captures, `scratch/lifecycle-J-20260924/J3-branch`)

local fire 1 269 at 6, later 34 at 168; planek fire 1 73 at 10; retry
fire 1 66 at 13, later 40 at 37; swim fire 1 10 at 255, later 1 for
9,667 cpu-s; scan 1,651 at 0.4; union 402 at 1.0; field 33 collects /
27 solves, 575 cpu-s, and 1,009 colour-lane fires (3,440 cpu-s) behind
them. 97,852 jobs, 35,552 cpu-s, 2,561 certs.

## 4. K (the pricing study's archived sheets; nothing on the merged tree)

Fires 1 and 2 mint 77 % of sheet C's certificates at 0.4 cpu-s each,
later fires 23 % at 5.9; the retry's own 150-iteration budget mints 6 to
24 per sheet; the sheets close at the fountain margin; the re-fire waste
there was calibrate and ctx, removed by `037440da`
(PRICING-ESCALATION-2026-09-30.md §2, §5).

## 5. What this settles

1. The chain head (scan, union, cond) is the cheapest minting work on
   every sheet and finishes in the first decile. The ladder's bottom is
   right.
2. Every residue row's FIRST fire is cheap and its re-fires are dear, by
   five to ten times per ordinal bin, on every colour sheet and every
   encoding. `tiles.local`, the one residue row priced FLAT (220), spends
   38–45 % of a hard cmy8 run on fires six and up for 1–3 % of the
   certificates, and those re-fires hold planek's first fires (7–14
   cpu-s per certificate) back to the sixth decile and beyond.
3. Which residue row is cheap is per encoding: planek on cmy8, swim on
   cmy (6 cpu-s per certificate, popping only in the last three deciles
   behind local's re-fires), local and planek tied on confetti. cmy8's
   swim has never fired on a single-sheet run and has no price evidence.
4. The retry differs most by encoding: on cmy8 its re-fires after a
   refit pay as well as its first fires; on confetti its first fires
   pay; on cmy it pays nothing (20–25 % of the run for 3–11
   certificates).
5. A resume re-walks the residue at generation zero for nothing
   (ruling 13 of the pricing study).
6. The enablers — the page field, calibrate, ctx, the colour refit —
   mint nothing on their own and unlock everything: on sheet H nothing
   certified before the first lane refit (scan 7,213 and retry 16,447
   fires minted 0; every certificate came after a refit costing ~100
   cpu-s); on K sheet C 756 of 764 same-cover retry certificates had
   one context adoption between failure and success; cmy M2's 71 %
   field support is a starved enabler. Their own jobs are cheap (a field
   solve 10–20 cpu-s, a context fit 3–22, a calibrate fit 0.008); what
   turns them into waste is a fit on an unchanged input (the K
   ping-pong, 61–90 % of a K sheet's CPU before `037440da`) or a
   publication that re-fires the page for nothing (a field publication
   waking 15,631 residue subjects on H). The right currency for an
   enabler is certificates per cpu-second INCLUDING what it unlocks,
   which needs an attribution stamp (field revision, ctx ordinal, lane
   fit count on each certificate) — owed to the instrument card.

## 6. What the numbers support (per encoding, prices never caps)

- Price every residue row's re-fires by fire ordinal FROM THE SECOND
  FIRE, local included, so every row's first fire precedes any row's
  second.
- Put the cmy retry above the residue first fires; keep the retry where
  it is on cmy8 and confetti.
- Collect the page field on certificate growth at a flat price, not on
  its own fire count; the publication threshold already keeps a
  converged field quiet.
- Stop the resume re-walk (a durable verdict basis; medium build, not a
  price).

The first three are literals and one eligibility clause; the A/B for
each exists on machine 1 as a resume from e042's `I-M1` snapshot or e046's
`M1`.
