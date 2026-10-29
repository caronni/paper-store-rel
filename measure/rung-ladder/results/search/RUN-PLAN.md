# Overnight construction search — run plan (2026-09-30)

Scratch only: nothing here is a format row, nothing is committed, no hardware.
`S = scratch/rung-ladder-20260930/search` (all paths below are relative to the repo root).

## The one command

```sh
cd <repo>
nohup scratch/rung-ladder-20260930/search/run_overnight.sh > /dev/null 2>&1 &
```

Everything the run writes lands under `$S`: stage banners with timestamps in `$S/overnight.log`,
each stage's own progress in `$S/logs/<stage>.log`, results in `$S/overnight-{A,AF,B1,B2,CONF}/`,
the combined table in `$S/overnight-ALL/TABLES-search.md`. The script's pid is in
`$S/overnight.pid`.

## Stages, grids, expected wall

Order: Tier A primary, Tier A frozen rungs, Tier A secondary, B1, B2, confirmation, summary.
Every stage runs 14 spawn workers with the FAST decoder (`fast/fastdecode.py`, bit-exact batched
twin of `holo.core.ldpc.decode`; start-up `selfcheck`, loud fallback to the production decoder).

| stage | what | grid (configs x seeds) | codes | walked | CPU h | expected wall |
|---|---|---|---|---|---|---|
| preflight | `fast/test_fastdecode.py` + `test_tasks_fast.py` + `test_variants_fast.py` (once per numpy build) | — | — | — | — | 1.5 min |
| A-primary | recipe space at k=1664, 1280; N=24 finalists, 8 at 500 trials | heavy {6..16 step 2} x frac {0.2..0.8} x light {3,4} x {uniform, balanced} = 168 per k, minus seed-0 build timeouts (16 at 1664, 6 at 1280) -> 152 / 162 configs x **24 seeds** | 7,536 | 146 | 22.5 | 1.9 h |
| A-frozen | the frozen rungs as FULL ROWS: k=2240, 2560, 2880, 3200, 3520 with r0547 + r0550, r0625, r0700, r0775, r0850 as named baselines; N=16 | heavy <= mb-3 (2240/2560/2880: {6..16 step 2}, 3200: 6..11, 3520: 4..6) x frac {0.2..0.6} x light 3 x {uni, bal} minus seed-0 build timeouts -> 45 / 38 / 29 / 36 / 30 configs x **4 seeds** | 712 | 126 | 4.7 | 0.4 h |
| A-secondary | recipe space at k=1600, 1216 (into overnight-A; primary not re-staged); N=16 | 168 per k minus timeouts (13 / 4) -> 155 / 164 x **16 seeds** | 5,104 | 98 | 15.2 | 1.3 h |
| B1 | DE-designed profiles, k=1664/1280/1600/1216; 20 DE candidates per k | 20 x **12 seeds** per k (+ DE tables and MC-DE, ~20 min) | 964 | 164 | 5.5 | 0.8 h |
| B2 | ARA / IRAA variants over 4 Tier A base configs per k, 4 k | 4 x 9 variants x 8 seeds per k (plain rows copied from overnight-A) | 1,152 | 108 | 7.3 | 0.6 h |
| confirm | per k (all nine) the top 12 clean codes by Es/N0@1 % + top 3 by p@1 % + every named baseline, FRESH trials t >= 20000, **5000 trials/point**, 0.05 dB / 0.0025 (0.0005 below p 0.02) grids until the 1 % point is bracketed | — | ~141 | — | 20.8 | 1.75 h |
| summarize | one combined `overnight-ALL/TABLES-search.md` (+ `overnight-CONF/TABLES-confirm.md`) | — | — | — | — | 1 min |
| **total** | | | | | **~76 + ~4 build/DE** | **~7.0 h expected; 8.4 h with the 20 % margin** |

How the numbers were made (`$S/sizing.py`, re-runnable): decodes per code per screen from the protocol
(s1 4 x 100; walk ~12.5 points x 200; fine 2,600; side 6 x 200; confirm ~8 points x 5000) x the codes
above; CPU per decode MEASURED with the fast decoder on 14 workers (`chk/calib-fast`, the trial grid at
seed 0, k=1664/1280, 81,100 decodes, pool utilisation 0.96): s1 29.4 ms, walk 19.1, fine 13.3, side
24.9 (production decoder on the same lines of trial-A2: 44.9 / 30.8 / 24.3 / 40.0 -> 1.5-1.8x); B2 x1.15
for the larger mother graphs; wall = CPU / (14 x 0.85). Screen-1 eligibility 76-90 % at the floor 16
(trial-A2 / the seed-0 scans), 88 % at the frozen rungs' incumbent floor. Not in the model: code
builds that time out at seeds > 0 (each burns up to 120 s; ~0.2 h worst case), and the machine being
shared (the progress line's rate shows it).

Screen-1 floors (the min(w1, w2) a code needs to be measured): **16** at k=1664/1280/1600/1216 (the
trials: a k=1280 code threw 19 wrong decodes on its weight-10 pair); at the frozen rungs the
**incumbent's own** min(w1, w2) (6 / 6 / 7 / 5 / 4 at 2240 / 2560 / 2880 / 3200 / 3520 — the weakest
production code at that k), because no built configuration there reaches 16 (seed-0 scan maxima
17 / 13 / 12 / 8 / 6). Screen-1 anchors: trial-A's best clean code per search k (as trial-A2/B1/B2);
at the frozen rungs the frozen code's measured 10 % points (TABLES.md; r0547 at k=2240).

Expected timeline if launched ~23:20: A-primary done ~01:15, A-frozen ~01:40, A-secondary ~03:00,
B1 ~03:50, B2 ~04:25, confirm ~06:10, summary right after. Past ~08:30 something is wrong (shared
machine, or the fallback to the production decoder: grep `FALLING BACK` in `$S/logs/`).

## Verified before launch (2026-09-30, evidence under `$S/chk/`)

- Fast = production, outcome for outcome: `compare_runs.py` over every (code, screen, channel, x, t0)
  — smoke prod vs fast 264 points / 5,680 decodes / 3 undetected, 0 mismatches (s0 edge digests
  equal); fast trial grid vs the production trial-A2 lines 473 points / 55,300 decodes / 47
  undetected, 0 mismatches; the und_w path on base-r0550 (10 wrong decodes) identical;
  `fast/test_fastdecode.py` BIT-EXACT PASS, `test_tasks_fast.py` 30/30, `test_variants_fast.py` 15/15
  (ARA and IRAA mother graphs).
- Resume: a trial run SIGTERMed at 24 s and resumed with another worker count equals the
  uninterrupted run (611 points / 81,100 decodes, 0 mismatches, 0 duplicate lines).
- `run_overnight.sh --smoke`: every stage green, one combined table ranking A / frozen rungs /
  B1 / B2 / recipe rows; a second run skips every stage (JSONL byte-identical); with the markers
  deleted, every driver resumes with 0 decodes (only run-meta lines added); SIGTERM mid-B1 stops
  cleanly (exit 130, summary written, workers gone) and the rerun finishes.
- Dry starts of A-primary (7,538 configs incl. baselines) and A-frozen (718; incumbent floors
  6/6/7/5/4; frozen codes re-keyed edge-identical; selfcheck on r0547 and r0850) then SIGTERM.

## Monitor

```sh
S=scratch/rung-ladder-20260930/search
$S/run_overnight.sh --status          # stage banners + the running stage's last progress line
tail -f $S/overnight.log              # banners only (START / DONE / WARN / FAIL / STOP / SKIP)
tail -f $S/logs/A-primary.log         # one stage's progress: a line every 30 s
```

A progress line reads `[elapsed] s0 a/b s1 a/b s2walk a/b s2fine a/b s2side a/b | stages {k: …} |
decodes N (rate/s) queue Q errors E`: `a/b` = finished/launched jobs per screen, `stages` = where each
k is (screen0/1 → walk → final → done), `rate` = decodes per second since the stage started (the
sizing assumes the measured rate below; a rate far under it means the machine is shared), `errors`
= worker exceptions (should stay 0).

## Stop and resume

- Stop: `kill $(cat $S/overnight.pid)` (SIGTERM; or Ctrl-C if it runs in the foreground). The running
  stage stops cleanly (every finished line is already fsync'd to its `results.jsonl`), the later
  stages are skipped, the combined summary is written over what exists, the script exits 130.
  Use SIGTERM, not `kill -INT`: bash ignores SIGINT in a script started with `&` from a
  non-interactive shell (measured on the smoke). Do not `kill -9` the script: its python child would
  keep running.
- Resume: the SAME command. A stage that finished (exit 0) left a marker in
  `$S/overnight-state/` and is skipped; the stage that was stopped resumes from its JSONL (every
  (code, screen) line on disk is reused, only missing work runs); later stages start normally.
- A stage that exits 3 finished its work but some codes hit a worker exception (logged as `WARN`,
  those codes wrote no line): the night continues, the stage gets no marker, a rerun retries only
  those codes. Any other non-zero exit is a `FAIL`: the pipeline stops, the summary is still
  written, the rerun resumes at that stage.
- To redo a finished stage on purpose: delete its marker file.

## In the morning

```sh
S=scratch/rung-ladder-20260930/search
$S/run_overnight.sh --status
open $S/overnight-ALL/TABLES-search.md     # or: less
```

If the night did not finish, run the one command again (it resumes), or write the table over what
exists with the defaults: `PYTHONPATH=src:. env/bin/python $S/summarize_all.py` (no arguments —
its --runs/--conf/--out resolve RELATIVE TO THE SEARCH DIR, not the cwd, so the repo-relative
`$S/...` spellings find nothing and it exits with "nothing to summarize"; verified 2026-09-30).

The tables REPORT. They do not recommend: adoption of any code is the owner's decision.

## What every column of TABLES-search.md means

The file is, in order: (1) the confirmed ranking (stage 6), (2) per k the Tier A/B1/B2/frozen
finalists in ONE table, the screen-1 ranking, the screen-0 verdicts with factor marginals, the seed
variance, (3) Tier B1's density-evolution section, (4) Tier B2's paired section.

Terms: **BLER** = block error rate (a trial fails when the decoder does not return the transmitted
codeword). **Es/N0@1 %** = the BIAWGN channel quality in dB at which the code reaches 1 % BLER,
log-linear interpolation between grid points (lower = better code). **p@1 %** = the BSC crossover
probability at 1 % BLER (higher = better). **Undetected** = a syndrome-valid WRONG decode (the
decoder claims success with the wrong codeword); any undetected decode in screens 1/2 disqualifies a
code by the protocol (⚠). All codes see the same trial seeds (common random numbers).

### 1. Confirmed ranking (per k)

| column | meaning |
|---|---|
| # | rank: clean codes by Es/N0@1 % (codes with an undetected decode in this stage last) |
| tier | recipe = a frozen/baseline code; A = recipe space; B1 = DE profile; B2 = ARA/IRAA variant |
| code | registry name (`base-<rid>` = the frozen code itself) |
| Es/N0@1% | re-measured at FRESH trials (t ≥ 20000, never used to select), 0.05 dB grid |
| Δ vs recipe dB | Es/N0@1 % minus the anchor frozen code's confirmed value (negative = better) |
| gap dB | Es/N0@1 % minus the BIAWGN Shannon limit at this rate |
| p@1% / Δp vs recipe | BSC 1 % point on a 0.0025 grid, and its difference to the frozen code (positive = better) |
| gap bit | (1 − h2(p@1 %)) − R: rate gap to BSC capacity in bits |
| earlier Es/N0@1% (src) | the selection-run value and the run it came from (winner's-curse check) |
| trials/pt | trials per grid point in this stage |
| und | undetected decodes in this stage (> 0 ⚠) |
| prior und | undetected decodes in screens 1/2 |
| awgn pts / bsc pts | the grid points measured, `x:fails` |

### 2a. Finalists (screen 2), per k

| column | meaning |
|---|---|
| # | rank by Es/N0@1 % (fine where run, else walk); codes with an undetected decode ranked last |
| tier | as above (`recipe` rows are the named baselines: the frozen recipe draw at k=1664/1280/1600/1216, the frozen production codes r0547/r0550/r0625/r0700/r0775/r0850 at k=2240..3520) |
| code | registry name; **bold** = baseline |
| config | `h<heavy degree> f<heavy fraction> l<light degree> <placement> s<seed>` (B1: the DE profile tag) |
| restart (info-free restarts) | the construction restart that built the code; in brackets how many restarts were rejected for an info-free block row (rule e) |
| chk deg | min..max check-node degree |
| min w1 / w2 | minimum codeword weight from one info bit / from two info bits (structural distance proxies; the screen-1 floor applies to their minimum) |
| reject | screen-0 flags (`min_w2=…<10` = the protocol's fixed flag; the run's own floor is in the header) |
| s1 score | screen-1 score: mean ln BLER over the four screen-1 points (0/n floored at 0.5/n); lower = better |
| Es/N0@1% / @10% | BIAWGN 1 % and 10 % points |
| gap dB | Es/N0@1 % − Shannon |
| Δ vs recipe dB | vs the anchor frozen code's walked/fine 1 % point at this k |
| p@1% / p@10% | BSC 1 % and 10 % points |
| gap bit | BSC rate gap at 1 % |
| src | `fine` = 500 trials around the 1 % point; `walk` = 200-trial walk only; `seedvar` = walked only for the seed-variance table |
| undet/trials | undetected decodes over all screen-1/2 trials (⚠ > 0) |
| robust f0.1% / 0.2% / 0.5% / 1% | fails/trials at the code's own 1 % point with a fraction f of confidently-wrong LLRs (magnitude 20); in brackets the clean point; `[n undet]` if any |
| eras ε0.3 p0.02 | fails/trials with 30 % erasures + 2 % flips |

Below it: the list of every syndrome-valid wrong decode (channel, x, trial, error weight total / info).

### 2b. Screen 1 ranking (top 25 + baselines)

`score` as above; `awgn es10 / +0.25` = fails/n at the anchor's 10 % Es/N0 and 0.25 dB easier;
`bsc p10 / +0.005` = at the anchor's 10 % p and 0.005 harder; `min w2`; `chk deg`.

### 2c. Screen 0 and factor marginals

Built/attempted count and verdicts; per factor value (placement, light, heavy_frac, heavy_deg): number
of screen-1 codes, mean and best s1 score; rule-(e) restart counts per placement.

### 2d. Seed variance

Per config with ≥ 2 walked seeds: the seeds, their s1 scores, Es/N0@10 % per seed and its spread,
Es/N0@1 % per seed (fine where run), p@10 % per seed and spread. The header line compares the mean
within-config SD of the s1 score with the between-config SD.

### 3. Tier B1 (density evolution)

Spearman ρ between the GA threshold of every built code's actual profile and its s1 score / walk
Es/N0@10 % (ρ > 0 = the DE ordering survives at n = 4096); per k the DE candidate table: profile
(`deg x block columns`), why chosen, E_b and a = E_b/mb, GA and MC thresholds, GA − Shannon, per-seed
s1 scores and their mean, walk / fine / BSC points, undetected count.

### 4. Tier B2 (variants)

Screen 1 PAIRED against the plain e-IRA of the same config and seed: n pairs, mean and SD of Δ
(variant − plain; negative = better), better/worse count, mean/best s1, s0 verdicts, min w1 / w2,
check degree, parity degree-2 fraction, punctured-bit one-step recovery, CPU per 100 decodes. Screen 2:
per walked code its Es/N0@1 %, Δ vs the best clean plain row and vs the recipe, gaps, p@1 %,
min w2, undetected/trials, robust f 0.1 %, mean iterations.

## What the run does NOT cover

- **No adoption, no recommendation, no format change**: nothing under src/, tests/, docs/,
  experiments/, analyzer/ is touched, nothing is committed, no golden moves, no hardware. The tables
  report; adopting a code is the owner's decision.
- **The decoder is fixed** (normalized min-sum α 0.8, 60 iterations + one sum-product retry). The
  confidently-wrong-LLR failures (f = 0.5 % wrecks every code in the trials) are a decoder-axis
  question: the robust columns report them, nothing here tries to fix them (no LLR clipping, damping,
  or erasure-marking variants).
- **Channels**: BIAWGN, hard-decision BSC, one erasure+flip point, the confidently-wrong channel. No
  measured print/scan LLRs from the receiver, no bursts, no per-plane (CMY) correlation.
- **Error floors below the confirm resolution** are not measured: 5000 trials per point resolves the
  1 % region (~50 failures), not 1e-4. Minimum distance is only proxied by min w1 / w2 (one- and
  two-info-bit codeword weights).
- **Families**: n = 4096 (one tile), Z = 64 QC e-IRA (recipe space, DE profiles) and the ARA / IRAA
  variants. No other families (protograph with punctured high-degree nodes beyond ARA, polar,
  non-QC). B1 and B2 run at the four search k only, NOT at the frozen rungs.
- **Rates**: k = 1664, 1280 (primary), 1600, 1216 (secondary), 2240 / 2560 / 2880 / 3200 / 3520
  (frozen rungs). Nothing in between (e.g. 1024, 1920).
- **Grid holes**: configs whose SEED-0 build hit the 120 s cap are skipped for every seed
  (`feasibility-*-seed0.json`: 22 primary, 17 secondary, 92 of 270 frozen-rung configs — heavy
  degree above roughly mb/2 at the high rates). That is "not buildable at seed 0 within 120 s", not
  a proof of infeasibility. At the frozen rungs: heavy_frac <= 0.6, light degree 3 only, 4 seeds.
- **Selection noise**: screen 1 is 4 points x 100 trials; a good code that is unlucky there is never
  walked. Only the confirm stage is free of the winner's curse, and it re-measures only the top
  12 + 3 per k (+ baselines); everything below is ranked on selection trials.
- **Encoder cost / latency / iteration budget** are not optimized; mean iterations are reported only.
