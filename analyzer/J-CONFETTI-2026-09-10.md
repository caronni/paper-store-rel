# Sheet J, 2026-09-09/10 — two ladders on a confetti residue: +156, and what a capture was worth

One page.  The receiver chain this sits inside is
`experiments/035-sheet-j-confetti.md` (the e035 print and its machine 2 recoveries);
the 09-09/10 chain is that log's Branch record of 2026-09-12 and
`src/holo/receiver/docs/PAGE-FIELD-PLAN.md` §5.2, and its artefacts are
on machine 4 mount (`J-page-field-20260909-140648.60338`,
`J-after-analyzer-20260910.73290`, `J-add6a-20260910.73646`,
`J-all-20260910.73898`).  The analyzer's own products are
`J-page-field-20260909-140648.60338-ladder-all-20260909-201547/{ledger.md,
ledger.jsonl,close.json}` and
`J-after-analyzer-20260910-facts.npz.manifest.json`.  Every number below is a
ledger's, a manifest's or a run log's own blind count.  **No control, no
parity and no offline score was run for THIS campaign: under DESIGN §0.4 and
§8 the 156 certificates are a YIELD, not a result** (§4).

## 1. The day in one paragraph

Sheet J is the duplex CMY8 confetti volume (`L:c2-cmy8-r0547@53x37`, two pages
on one cut sheet, 11,766 tile-streams, K 4,020, 1 MiB).  The page-field
receiver read four 2400-dpi captures to exhaustion and stopped at 3,402
certificates, 618 symbols short.  The analyzer was pointed at that residue and
found 2,688 covered targets — 32 % of the 8,364 open tile-streams, the rest
under no placement footprint at all.  A default battery ran 1 h 50 m to
2,470 of them for +39 and was killed with nothing written; the
`everything+patch+pure` battery then ran to a fixed point in 7 h 11 m and
minted **156** (C 36 / M 31 / Y 89, 145/9/2/0 by generation) at E[false]
3.66e-08, every one of them single-witness.  Folded back through
`export-facts` and resumed on the SAME four captures, the receiver replayed
3,558 and minted **exactly one** certificate for 47,960 jobs and 20,899 machine 4
cpu-s.  The next run added one platen load and minted 714 in 19 minutes; the
run after it, with all ten captures, closed the volume byte-exact
(sha `fbbab289…`, K 8102/4020).  On a fragment sheet the lever was a capture,
not a battery.

## 2. What ran

| launch (local time) | what | outcome | survives |
|---|---|---|---|
| 16:05:17 | `ladder`, default battery, no generation flag — header `generations <=1` | killed at 32 s, 10/2,688, +0 | log only |
| 16:06:27 / :43 / :49 | three launches rejected: `--generations 10`, `--generation 10`, `--generation 10` | top-level `unrecognized arguments` | — |
| 16:07:00 | `ladder --help` | the option list, where `--max-generations` is named | — |
| 16:07:23 → 17:57:50 | `ladder`, default battery, `generations <=10` | **+39 at 2,470/2,688, 2.7 s/key, 1:50:23** — killed | **nothing: no ledger, no close, no export** |
| 20:15:47 → 03:29 | `ladder --profile everything+patch+pure` (+ CLI knobs) | **+156, fixed point, 4 generations, 25,889.3 s** | ledger, close, export |
| 09-10 10:16 → 10:43 | holo3 resume from the export, same four captures | replayed 3,558, **minted 1** | facts, report |
| 09-10 15:32 → 17:45 | `ladder`, all-arms, on the already-VERIFIED ten-capture run | **+51 at 350/2,740, 22.4 s/key, 2:10:36** — killed | **only its `-input/` dir** |

The last pass is NEARLY the 09-09 battery, not letter-identical: it spelled
its erasure rungs `L7,L7c` where the 09-09 pass spelled `L7a,L7b,L7c`, so
the two are comparable in kind and not row for row.

About 11 h 19 m of analyzer wall on this sheet; **4 h 01 m of it, and 90
certificates, thrown away by hard kills** — `_out_dir` is called only after
`fp.run` returns and the stop door writes through the same path, so a killed
pass leaves no directory (README §2.4).  Neither log carries the door's
`stop: signal N` line.

Both inputs were built with `union-base` and both recorded
`captures_verified: true`.  The first base's `facts.npz` was the
PlaneField-stripped variant, which `union-base.json` records (README §2.1a).
What stands today at the second base's `facts.npz` path on the mount is a raw
JSON spine that still carries BOTH new field families: it does not match that
base's own `union-base.json` fact count and `snapshot.read` cannot read it, so
nothing there is a post-W2 corpus anyone can open.

## 3. The harvest — 156 certificates

Header: seed 20260903, workers 14, `knobs_from profile:everything+patch+pure+cli`,
halo C 16 / M 16 / Y 32, 22 arms, 5 rules, rungs `L0,L1,L2,L4,L3,L3f,L7a,L7b,L7c`,
2,874 rows (2,688 targets + 174 + 9 + 3 re-targeted), `stop_reason "fixed point"`.

- **Generations** 0 → +145 (5:54:30), 1 → +9 (1:04:58), 2 → +2 (7:55), 3 → +0
  (4:05).  The analyzer's own cascade is 11 of 156, **7 %** — against 16 % on
  sheet I's first-run residue and 46 % on sheet H's pass 3.
- **Rungs** (first-success): L0 109, L1 19, L3f.r0 11, L2:damped@300 8,
  L2:layered@300 5, L3f.r1 2, L7a 1, L7b 1.  **L4 certified nothing; no
  certificate came from a list rung** (manifest `added_certified_list: 0`), so
  none is quarantined under §0.3.  L7a and L7b certify here for the first time
  on paper, and L3f adds 13 more after W8 §3.2's sheet-H measurement — its
  first on a confetti sheet (DESIGN §6's status cells amended).
- **Rules**: `sum` 66 on the selected arm, `best` 3, `platt` 1, `corr` 0,
  `platt-state` 0 — and **86 of 156 (55 %) came from the re-roll**, 58 of them
  through `sum|reroll:patch+offset` alone (leave-one-out 98: dropping that one
  spelling costs 58).  Leave-one-out over rules is exact here (`all_rules`):
  `platt`, `corr` and `platt-state` contributed nothing unique.
- **Arms** (first-success / only-this-arm): `patch+offset` 78/64,
  `patch+affine` 31/11, `patch+field2+offset` 25/11, `subtract+offset` 25/19,
  `patch+committed` 16/6, `rings+offset` 6/2, `global+offset` 5/4,
  `subtract+affine` 5/5, `head+offset` 2/2, `subtract+field2+offset` 2/2.
  **The W8 patch family is 150 of the 195 arm hits** — on J as on H it is the
  yield.  The two production-field arms minted 0 because the input was
  stripped of `PlaneField` (README §2.1a).
- **Stream × band**: C 924 rows (62 live / 862 marginal) → 36; M 908 (54/854)
  → 31; Y 1,042 (34/1,008) → **89**.  **No `dead` band on this sheet** at
  r0547, consistent with e035's own reading.  Y is 57 % of the harvest from
  36 % of the rows.
- **Export**: 156 added, 0 already certified, 0 skipped, by stream C 36 / M 31
  / Y 89; total after export 3,558 of K 4,020.

## 4. What this harvest's standing is, under §8

`ledger.md` says it under two headings of its own: **`## Controls`**, whose
body is "NOT RUN — a run without its controls is not a result (DESIGN §8).",
and **`## Parity`**, whose body is "NOT RUN."  Read against §0.2's four legs
and §8's gate:

| leg / control | on sheet J |
|---|---|
| 1. syndrome + CRC with priced exposure | **stands** — 157 distinct consultations, E[false] 3.655441105365753e-08 against the 0.01 bound |
| 2. the payload envelope at the close | **could not run in the pass** — `close.json status open`, 3,558 of K 4,020, short 462 |
| 3. fountain over-determination | **could not run** — `consistency.checked false, proven false, reason "no fountain group could be solved"` |
| 4. independent agreement | **zero** — all 156 rest on 1 independent certificate; corroborated 0, contradictions 0 |
| parity sample (THE acceptance gate, ≥ 80 %/stream, `n_disagreeing_with_production` 0) | NOT RUN |
| null arm / frame null / positive control / stratified holdout | NOT RUN |
| `analyzer score` against a payload | NOT RUN — and it has been possible since `J-all-20260910.bin` existed |

"NOT RUN" means for THIS campaign.  A `controls.json` for sheet J dated
2026-09-03 does exist on the laptop (`scratch/analyzer/J`, n = 30 per
stream), from an older tree and another configuration; it is not a control
over these passes and cannot be read as one.

So the 156 are a yield with one leg under them.  They were nonetheless folded,
and the ten-capture receiver run closed byte-exact with all of them in — which
is legs 2 and 3 arriving late and only in AGGREGATE: the metadata gate
absorbed one equation per certificate for all 8,102 at rank 24 with no
`IntegrityError`, and the envelope sha `fbbab289…` matches e035's emission.
That is real and weak: the solve took rank 4,020 of 8,102, so 4,082 redundant
symbols were never individually audited, and a wrong bit among the 156 need
not have surfaced there.  **Two things could settle it today with no new scan
and no decode** — `analyzer controls --parity 100 --null 5 --frame-null 3` on
the analyzer input dir, and `analyzer score --ledger <this ledger> --payload
J-all-20260910.bin`.  Until one of them runs, nothing here belongs in a
zero-wrong count.

## 5. Value against cost

- **The ladder**: 156 certificates for 25,889.3 s of WALL on 14 workers
  (`fixedpoint.py:900` — the analyzer records no CPU total anywhere; ≤ 362,450
  s at 14 workers, and ≈ 3.2–3.4 × 10⁵ machine 4 cpu-s by this machine's own measured
  cpu/wall of 12.47–13.16 × on the four receiver runs beside it, an
  ESTIMATE), plus 4 h 01 m of killed passes.
- **The fold**: the resume that consumed it cost 47,960 jobs and 20,898.9 machine 4
  cpu-s for one certificate, and carried the count 3,402 → 3,558 and the
  shortfall 618 → 462.  The 156 did their work as SYMBOLS, not as seeds.
- **The capture**: +714 certificates in 19 m 53 s and 14,876.3 cpu-s (4.6 ×
  the ladder's whole harvest), then +3,829 and a verified close.  Receiver
  total over the chain: 436,771 jobs, 262,922.2 machine 4 cpu-s, ≈ 5 h 40 m of active
  wall.  **On the ESTIMATE above, more than half the chain's compute bought
  the 156** — the receiver's cpu-seconds are measured, the analyzer's are not.
- **A/B on the same key order** (both passes walked the same seed-ordered
  list; the `last` key matches at 500, 1,000, 2,450 and 2,470): default +39 in
  1:50:23 against `everything+patch+pure` +139 at the same 2,470 keys in
  5:23:32 — **3.56 × the certificates for 2.93 × the wall**.  A first-success
  marginal on one sheet, not a controlled A/B in W8 §4's sense.
- **The step-6 pass was never yield**: its base was the VERIFIED close, so
  nothing it minted could change the payload.

## 6. Instrument findings worth keeping

- **The zero-unsat bucket is not a few-error regime here.**  Of 111,214
  zero-unsat outcomes sampled over 2,306 of 2,874 rows, 71,580 (64 %) have
  `n_observed == 0` — empty-evidence arms exiting on the all-zero codeword.
  §6.1's 0-vs-≥50 reading does not transfer to a confetti sheet (DESIGN §6.1,
  third bullet; prefix sample, direction robust, the 64 % not).
- **The residue was mostly dead space, three ways**: 5,796 of 8,364 open
  tile-streams with no usable pixels (3,522 never addressed + 2,274 below the
  attempt floor), only 2,688 covered at `cover_fraction 0.9`, and 156 of those
  2,688 certified (5.8 %).
- **The fold did not cascade** (DESIGN §6b): the one receiver mint,
  `(0, 44, 8, Y)`, is adjacent to no analyzer key — the nearest on its page is
  `(0, 40, 11, C)`, four rows and three columns away — and of the 156 keys'
  720 in-bounds neighbours 395 were already certified and 195 sit below the
  attempt floor.
- **The page-field seam cost the pass its production field arms** — with
  `plane_fields` empty every `field` arm refuses `no_field` by construction —
  **and cost the receiver its fields on resume** (README §2.1a; the fix is the
  analyzer's page-field plan on branch `page-field-analyzer`, A0 the corpus
  conversion and A1 the reader flip).
  **CLOSED 2026-09-12.**  A1 landed the reader — `PlaneField` keyed
  `(page, plane)`, the delta applied unrotated — and A0 converted this
  sheet's archive, so `scratch/J-run.54028.page-field` carries six page
  fields (C/M/Y observations 222/222/151 on page 0 and 197/198/121 on page
  1, field revision 591 and 891) and its two `EvidenceRevision` facts.  What that does NOT do is
  change anything above: this record's 156 certificates were minted on a
  stripped input, the production half of "does a field buy certificates"
  is still 0 BY CONSTRUCTION here, and the head-to-head the strip made
  impossible is owed on an appended base (PAGE-FIELD-PLAN A7, M3 —
  Germano's go).  A measured record, not a strike.
- **Roster note (2026-09-12).**  The two batteries this record was minted
  under have each lost arms since.  The default battery lost
  `subtract+smooth` (plan A3: a field keyed by lane and stream with the
  page dropped from its key — on a duplex sheet like this one it merged
  the two physical faces; nothing here was corrupted, that pass was
  killed before output).  `everything+patch+pure` lost the same arm and
  the two `field2c` arms with the `everything+field2` rebase (plan A2).
  Three arms in all, and none of them appears in §3's first-success
  table — but the batteries named here are the OLD rosters, and a re-run
  under the same profile names is not the same run.
- **Skipped loop steps**: `census` (no `census.jsonl` for this campaign, so no
  residue print and no rank cross-check), `controls`, `score`.  Targeting
  still worked — `_pass` builds the census in memory — but two operator
  products and the acceptance gate were lost.

## 7. What this is not

Single sheet, single print, single operator sequence, on the page-field
receiver branch (`pre-v1-v2-deletion-136-gd7eabd21`) whose field producer has
no flag and always runs.  Nothing here is controlled against e035's machine 2 chains:
chain-with-resumes against from-scratch, the 156 present on one side only,
capture-entry order, an operator ctrl-C, 14 workers against 12, and machine 4 CPU
seconds that are never comparable to machine 2 or laptop seconds.  No rung, no bar,
no profile and no branch is promoted; the receiver still prints PROVISIONAL on
every run.
