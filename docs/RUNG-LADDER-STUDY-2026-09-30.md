# Rung ladder study — r0550 vs r0547, rungs below r0547, the construction search (2026-09-30)

STATUS: **PROVISIONAL. NO promotion. Rulings OWED to the owner (§8).**
Nothing here changed a format row, a golden, a profile, `src/`, `tests/`
or a sheet. It is a codec-level record: simulated channels (BSC, BIAWGN,
iid erasure plus flips, confidently-wrong LLRs) through the production
decoder `holo.core.ldpc.decode` (normalized min-sum α 0.8, 60 iterations
plus one sum-product retry) or its bit-exact batched twin. Every paper
number quoted is ONE sheet on ONE engine, taken from its experiment log.

Evidence lives under the GITIGNORED `scratch/rung-ladder-20260930/`.
(2026-10-09: the code moved to `measure/rung-ladder/`; the data is in the evidence
archive under `machine-4-salvage/scratch/rung-ladder-20260930/`. Paths below are as run.)
(2026-10-11: the data is in measure/rung-ladder/results/ beside the code, not in the
evidence archive; results/README.md lists the files.)
(2026-10-17: brought current on the 2026-10-01 confirm — §1, §2, §5, §7.4, §8 R4/R5
and §9 carry dated corrections, the rev. 2 map a rev. 3 note; the non-reproducible
remainder of the scratch evidence — the confirm rows, the row union of every search
stage, the run log, the pre-launch identity checks, the probes — joined
`measure/rung-ladder/results/` (its README, §2026-10-17), because scratch/ is going away.)
This document carries the numbers so they survive that tree:
- the decision map `RUNG-LADDER-MAP.md`, rev. 2, after a three-lens
  refutation pass: claim C7 withdrawn, nine claims qualified;
- `TABLES.md`, which is Appendix A, verbatim;
- `TABLES-c1.md`, which is Appendix B, verbatim;
- `structure.json` and `undetected_diag.txt`;
- `verify/`, which holds the edge digests, spot re-measures, capacity and
  puncture checks;
- the search harness `search/`, with its trials `trial-A`, `trial-A2`,
  `trial-B1` and `trial-B2`;
- the fast decoder record `search/fast/README.md`, with its independent
  verification in `search/fast/verify/`;
- the overnight plan `search/RUN-PLAN.md`.

Labels: **measured** means run today, with the source named.
**Documented** means from a committed log or source line.
**Inferred** means arithmetic or reading; it is marked where it
appears.

Harness resolution (map header): one construction draw per label and 200
trials per point, on a 0.005 p / 0.25 dB grid. Differences under about
0.02 in p or 0.25 dB are noise. Code identities were checked by edge
digest through both ports (holo reload = paperholo build = harness cache,
`verify/digest_results.json`), and five spot points were re-measured
(`verify/spot_results.json`).

## 1. The question, and the answers in five lines

The owner's question, verbatim from the map header: "r0550 is meaningless
(keep r0547); should we build r0300/r0400? Do they have the right
resilience, or should the 4096−100 bits be used some other way? Plus the
c1 reading (e039/e040): 'enticing for lower rungs' and 'a real capacity
gain over c2 at high rung'."

1. **r0550 and r0547 are the same rate** (k = 2240) from two independent
   draws. They tie on the waterfall. r0550 alone carries a weight-6
   two-information-bit codeword, which produced syndrome-valid wrong
   decodes in the harness. CRC-32 caught every one of them.
2. **r0300/r0400 build**, but under the frozen recipe the candidates at
   k 1216–1664 sit **1.25–1.90 dB** from Shannon at 1 % BLER ("r0400" =
   k 1664 at 1.30; "r0300" = k 1216 / 1280 at 1.90 / 1.77), against
   0.85–1.21 dB for the frozen six. Below k ≈ 1300 the uniform row draw leaves **8–22 %** of checks
   with no information edge. (2026-10-17: on the 5,000-trial confirm the
   frozen-recipe baselines read 1.35–1.77 dB and the frozen six 0.79–1.05 dB;
   §7.4.)
3. **No regime measured with a blind detector sits inside their hard
   reach** (§5). The soft reach, one rung step lower, is unmeasured.
4. **Alternatives for the 4096−100 bits:** shortening beats every
   puncture variant measured. `heavy_frac` was the only code-side lever
   measured before the search (R 0.20–0.31). The construction search
   (§7.4, confirmed 2026-10-01 on 5,000 fresh trials per point) found
   **0.25–0.51 dB**: gaps 1.03 / 1.11 / 1.29 / 1.26 dB at k 1664 / 1600 /
   1280 / 1216, hard gaps 0.079–0.092 bit, the frozen ladder's level;
   **balanced placement** removed every info-free row and every winner
   uses it; the frozen rungs were not beaten. None of the four winners
   fits the production loader (§7.4, the 2026-10-17 readings).
5. **c1:** no rung closes the recorded 21–22 % raw hard error. At
   capacity c1 beats c2-r0850 per area (1.03 hard / 1.43 soft vs 0.827).
   With the 132-bit tile overhead and today's recipe it is **at best
   break-even**. The tool's 21 % is not shown to be an upper bound.
   (2026-10-17: the hinge in §5 — a code within 1.5 dB at R 0.27 gives
   1.16× — was not revisited: the search reached 1.26 dB at R 0.297 but
   k < 1216 was not searched, so the c1 codes remain single frozen-recipe
   draws.)

## 2. The ladder today

Sources: `src/holo/core/ldpc/construct.py:69-76`. User bits = k − 32 −
sites (`src/holo/core/ldpc/tile.py:49-54`). The recorded BSC point is
from docs/FEC-DESIGN.md:87-89. The harness p@1 % and the BIAWGN gap are
from Appendix A.

| rung | k | true R | user bits p100 / p120 | BSC: record / harness p@1 % (gap, bit) | BIAWGN gap @1 % | on paper |
|---|---|---|---|---|---|---|
| r0547 | 2240 | 0.5469 | 2108 / 2088 | not recorded / 0.065 (0.106) | 1.13 dB | Y bank of every cmy8-p120 v0/v1 sheet; sheet J, all planes (e035, VERIFIED ×3) |
| r0550 | 2240 | 0.5469 | 2108 / 2088 | clean at 0.055 / 0.045 (0.188) with its syndrome-valid floor, 0.062 (0.118) detected-only | 1.21 dB (1.09 det-only) | fossil rows 1 (c3; e033 A2/G) and 12 (c4; e033 A); C/M banks of the cmy8 v0/v1 rows (e030; e032, incl. the first CMY8 close, 718,413 B; e033 D–F; e038 F); the cmy7 bank child (e032 ×2) — `src/holo/format/fossils.py:93-117`, `profiles.py:221-224,247-257`; row 2 (c2-r0550@3328x2304) is "goldens, unprinted" (`fossils.py:95-96`) |
| r0625 | 2560 | 0.625 | 2428 / 2408 | 0.5 % at 0.045 / 0.050 (0.089) | 0.86 dB | never printed |
| r0700 | 2880 | 0.703 | 2748 / 2728 | 1.5–1.8 % at 0.035 / 0.036 (0.073) | 0.85 dB | K: e029, e032, e039 A–C (VersaLink, HP VERIFIED); sheet I (e033/e034/e037, 100 %) |
| r0775 | 3200 | 0.781 | 3068 / 3048 | 0.5 % at 0.020 / 0.021 (0.072) | 0.95 dB | e039 H via the re-screening PDF path; unscanned |
| r0850 | 3520 | 0.859 | 3388 / 3368 | 3.5 % at 0.010 / 0.008 (0.075) | 0.88 dB | sheet H (e036, 100 %); VersaLink D VERIFIED 657,042 B from one 1200 dpi capture (e039:575-584) |

**Frozen ladder, measured (Appendix A):**
- BIAWGN gaps to Shannon at 1 % BLER are **0.85–1.21 dB**.
- (2026-10-17) On the 5,000-trial confirm (§7.4): **0.79–1.05 dB** (r0775
  0.79, r0850 0.82, r0700 0.84, r0625 0.89, r0547 0.99, r0550 1.05). There
  r0850, r0775, r0625 and r0550 show syndrome-valid wrong-decode floors
  (5 / 30,000, 6 / 40,000, 30 / 30,000, 123 / 60,000 trials); r0547 and
  r0700 none.
- BSC gaps are **0.07–0.11 bit**. r0550's 0.188 is driven by its
  syndrome-valid floor; detected-only it is 0.118.
- For scale (inferred, map §5): the finite-blocklength (normal
  approximation) penalty at n = 4096 is about 0.03 bit (0.028), or about
  0.45 dB below Shannon (the dB figure is not in any source file). That
  is roughly a third to a half of each frozen gap. The rest is the
  construction and the decoder.

Rung names are nominal for the top four (r0700 is really 0.703, and so
on). The ladder step is 320 user bits. The characterize instrument's table
spells the top rung "r0859" and has no r0547 entry
(`src/holo/characterize/summarize.py:466-474`).

## 3. r0550 vs r0547

**Measured and documented:**
- **Same rate, two draws.** They share k, user bits, width S = k − p − 33,
  and CPU per attempt (35.0 vs 35.2 ms, `cost_fit.py`). They are two
  independent draws of the seed label `ldpc-v1/<token>`
  (`src/paperholo/ldpc.py:208-210`).
- **The difference is in the undetected tail only.**
  - r0550 carries a **weight-6 codeword on information bits 1157 + 1363**.
    This was verified by encoding, three times independently
    (`structure.json`).
  - r0547's exhaustive two-information-bit minimum is **12**, at (684, 733).
- **Harness floor (log-LLR seeds).** r0550 produced syndrome-valid wrong
  decodes: 1/200 at p 0.025–0.040, then 2–4/200 at 0.045–0.065. Totals
  were **22/3600 BSC and 8/2000 AWGN**, against r0547's **0/2000 and
  0/1800**. CRC-32 rejects every such decode (`tile.py:161-162`), so the
  cost is a lost attempt, never a wrong certificate.
- **On the waterfall they tie within noise.** BSC detected-only: 0.062 vs
  0.065. AWGN: 1.09–1.21 vs 1.13 dB. Erasure plus 2 % flips at ε 0.3:
  50/200 vs 35/200.

**Qualifications carried from the refutation pass:**
- The low-p 1/200 is **one correlated trial repeated down the grid**,
  because the seed base is shared. Only trial 154 at p 0.03 is traced to
  the weight-6 word (`undetected_diag.txt:1`). A true floor should scale
  like p³, not stay flat.
- The committed test's magnitude-4.0 seeds read 0/200 at p 0.055
  (Appendix A §e). That is why the 2026-07-08 record says "clean". **The
  floor has never been seen on paper.**
- Low-weight pair words come from **the recipe, not this one draw**. The
  pair weights are r0625 6, r0775 5 and r0850 4 (`structure.json`).
  r0547's 12 is a pair weight, not its minimum distance: words with 3+
  information bits were never enumerated. Treat this as hygiene, not as
  safety.
- Ruling 6 of 2026-09-04 already reads "zero reason to choose 0550 over
  0547" (docs/CMY8-COLUMN-GROUPS.md:468-472). e039/e040 printed no 2240
  rung at all (e039:122-131).

**The owner's ruling in dialogue, 2026-09-30:** "rung 550 is totally
meaningless (keep 547)". What that ruling still has to spell out is
§8 R2.

**Lawful options (map §2). A ruling picks among them:**
- **(a) Emission retirement.** No new v2 identity names r0550. The cost is
  one sentence in docs/FORMAT-SPACE.md §6 plus the help text at
  `src/holo/cli.py:150-154`.
- **(b) Profile re-key, in addition to (a).** Re-key PROFILES rocksolid /
  resilient / high-volume to r0547. These become NEW v2 identities with
  no sheet lineage. holo3 never consumes profiles (receiver
  `cli.py:61-65`).
- **Stays under either option:**
  - the r0550 mother code (the LADDER entry and its json), which is frozen
    substrate (docs/FORMAT-SPACE.md:58-62);
  - the "same k ≠ same code" pin
    (`src/holo/receiver/tests/test_h3_format_identity.py:191-194`).
- **The fossil-sunset boundary.** Retiring r0550 is never a reason to
  delete anything. Fossils, the -v0 banks, legacy registry rows and legacy
  tests fall ONLY under the owner's separate fossil sunset. That sunset is
  still OPEN and user-declared (FORMAT-SPACE.md:12,18-22,362-368,551-553;
  row 15 / sheet J exempt, :436-438). Declaring it would strand printed
  r0550 sheets unless they get a replacement identity route.

## 4. Candidate rungs measured, and the recipe's low-rate defect

**Setup.** Frozen recipe (HEAVY_FRAC 0.30, heavy_deg 10) unless marked.
Sources: Appendix A (k ≥ 1216) and Appendix B (k ≤ 1152). The erasure
column is iid; 0/200 means BLER ≲ 1.5 %. Info-free = the share of checks
with no information edge.

| candidate | k | R | builds (restart) | info-free | BSC p@1 % (gap, bit) | BIAWGN gap @1 % | erasure reach at p 0.02 | variants |
|---|---|---|---|---|---|---|---|---|
| r0203 | 832 | 0.203 | yes (2) | 21.6 % | 0.145, floor (0.200) | 2.72 dB | 50 % + 5 % | f50: 0.185 / 2.03 dB. f70: 0.189 / 1.88 dB, the best hard point in the record |
| r0219 | 896 | 0.219 | yes (0) | 16.0 % | 0.165 (0.135) | 2.17 dB | 50 % + 2 % | — |
| r0234 | 960 | 0.234 | yes (0) | 16.3 % | 0.160 (0.131) | 2.15 dB | 50 % + 2 % | f50: 0.177 / 1.65 dB |
| r0250 | 1024 | 0.250 | yes (0) | 8.3 % | 0.150 (0.140) | **3.06 dB, a floor artefact**: a 2/200 stuck-trial plateau; ~1.7 dB at 10 % | 50 % + 2 %; 60 % + 1 % at 2/200 | f50: 0.167 / 1.81 dB. f70: 0.167 / 2.06 dB |
| r0281 | 1152 | 0.281 | yes (0) | 19.6 % | 0.140 (0.135) | 1.94 dB | 50 % + 2 % | f50: 0.157 / 1.59 dB |
| r0297 (= "r0300", nearest snap) | 1216 | 0.297 | yes (0) | 11.1 % | 0.142 (0.113) | **1.90 dB** | 50 % + 2 % | not measured |
| r0313 (= "r0300", upward snap) | 1280 | 0.3125 | yes (0) | 11.4 % | 0.120 / 0.130 detected-only (0.158 / 0.130); 13/4000 undetected | **1.77 dB** | 50 % + 2 % | f50: 0.135 / 0.145 detected-only, **1.37 dB**, 4.5 % info-free, **16/4000 BSC + 2/2000 AWGN + 1/3600 erasure undetected** (a distance-16 two-info-bit word). h14: 0.130 / 1.87 dB. h20 fails within 64 restarts |
| r0391 | 1600 | 0.391 | yes (0) | 2.6 % | 0.108 (0.117) | **1.25 dB** | 40 % + 2 % | f50: 0.115 (0.095), 1.23 dB (nil), 0 info-free. h14: 0.107 / 1.61 dB |
| r0406 (= "r0400", either snap) | 1664 | 0.406 | yes (0) | 0 % (one draw; ~1.5 % expected) | 0.104 (0.113) | **1.30 dB** | 40 % + 2 % (50 % + 2 % fails 197/200) | f50 never run at 1664; h20 fails within 64 restarts |
| r0469 | 1920 | 0.469 | yes (0) | 0 % | 0.068 / 0.078 detected-only (0.172 / 0.138) | 1.24 dB | 30 % + 2 % | — |
| r0547 (ref.) | 2240 | 0.547 | frozen | 0 % | 0.065 (0.106) | 1.13 dB | 20 % + 2 %; 30 % + 2 % at 35/200 | frozen six: §2 |

**Candidate gaps under the frozen recipe (BIAWGN, 1 % BLER):**
- k = 1664: 1.30 dB
- k = 1600: 1.25 dB
- k = 1280: 1.77 dB, or 1.37 dB with HEAVY_FRAC 0.5
- k = 1216: 1.90 dB
- k = 1024: 3.06 dB, a floor artefact

**The recipe's low-rate defect (measured; the cause is inferred from the
construction):**
- Below k ≈ 1300 (R ≤ 0.3125), **8–22 % of checks carry no information
  edge**.
- **Inferred cause.** The mean information-edge load per block row,
  (3(kb − nh) + 10·nh)/mb, is only 1.3–2.3. The recipe places those edges
  by uniform row draws (`src/paperholo/ldpc.py:333`).
- **It is NOT rule (d).** Rule (d) is an upper cap (:324). Simulated, it
  slightly reduces the number of empty rows.
- **Degrees.** 72–80 % of variables have degree 2 (the e-IRA accumulator).
  Check degrees are 3.3–4.6 below R 0.3.
- **Soft break.** It falls between R 0.31 and 0.39. The gaps are:
  - 1.77–3.06 dB for R ≤ 0.3125;
  - 1.24–1.30 dB for R 0.39–0.47;
  - 0.85–1.21 dB for the frozen six.
- **No hard break at R 0.4.** The BSC gaps are 0.113–0.200 bit below 0.4,
  0.113 at r0406, and 0.172 at r0469.
- **HEAVY_FRAC.** It was the only construction lever that helped before
  the search, and only for R ≈ 0.20–0.31:
  - 0.35–0.85 dB at the 1 % point (1.25 dB at r0250 against its
    floor-driven baseline);
  - 0.26–0.35 dB at 10 % BLER;
  - nil at R 0.39 (0.02 dB);
  - f70 is no better than f50 at k 1024.
  - These are one-draw results, confounded with seed variance. §7's trial
    measured that variance.
- **Other levers:**
  - heavy_deg 14 is worse on AWGN and about flat on BSC.
  - 200 iterations buy another 0.1–0.75 dB below R 0.3 (Appendix B,
    supplement). That is a receiver-identity ruling, not a rung
    (`tiles.py:45-52`).
- **Nothing below R 0.3 gets within ~1.5 dB of Shannon** under the recipe.

## 5. Where the channel needs them

**Method.** Measured hard cell error is compared against each code's
measured p@1 % (map §4). Every row is a hard-decision comparison. Under
the equal-variance Gaussian soft model, p = Q(√(2·Es/N0)), the reach
moves about one rung step lower: r0406 → 0.154; r0297 / r0313 → 0.186 /
0.182; r0281-f50 / r0250-f50 → 0.203 / 0.213. **No soft MI has been
measured on any row.**

(2026-10-17: the table below uses the frozen-recipe reach. The confirmed
winners reach p@1 % 0.1113 / 0.1159 / 0.1474 / 0.1558 at k 1664 / 1600 /
1280 / 1216 (§7.4), which covers e038's genie Y 14.1 % and ties its
supervised M 15.5 %. The hard-vs-hard method is contradicted by paper
beyond C10: Canon sheet G read C 14.2 / M 20.2 / Y 25.5 % whole-page and
closed at r0700, which needs 3.5 % (e040 §040.4f). What closes sheets is
the receiver's soft, retried, multi-capture read; this table ranks rungs
and does not predict recoverability.)

| regime | measured need | fits which rung (hard) | verdict |
|---|---|---|---|
| AltaLink weak planes: sheet I Y at r0700; sheet H C-on-M+Y 0.214 at r0850; xerox cmy7 18 % | detector-frozen; all closed at their ORIGINAL rung on the receiver axis (e037:110-111; e036:126-138; COLOR-UPLIFT-MEASUREMENTS.md:3044-3054) | none needed | No customer. Sheet J Y trails C/M by 4.5–7 % at r0547 "with margin" (e035:118-127,212) |
| e038 M281 fresh toner, c3, off-band, GENIE 9×9: M 12.0 % / Y 14.1 % (e038:115-133; pooled means, one sheet) | print-frozen | frozen r0297 (0.142; 0/200 at 0.125) covers M with margin and Y at its edge; r0406 (0.104) misses both | Genie only; no receiver has it. The log ranks the engine-contrast lever first (e038:145-152) |
| same, best "blind" classifier (still supervised on emitted truth, so optimistic): M 15.5 % / Y 19.7 % | print-frozen | M: r0281-f50 (0.157) is a tie inside the grid; first fit with margin is r0250-f50 0.167 / r0219 0.165. Y: no code at 1 % BLER (best 0.189); at 10 % BLER r0203-f70 reaches 0.199 (0.202 at 200 iterations) | Beyond r0300/r0400 at hard decisions. Soft would move M to r0297/r0313 and Y to r0281-f50/r0250-f50 (unmeasured). The toner epoch was invalidated 2026-09-14 |
| confetti; attempt floor k − p is 2120/3976 = 53.3 % of a p120 tile at r0547, 38.8 % at r0406, 37.2 % at k 1600, 29.2 % at k 1280 (`tiles.py:143-145,408-416`) | sheet J: 2,031 FLOOR (17.3 %) + 930 ATTEMPTED-failed (7.9 %) tile-streams, neither split into cut-edge vs hidden-face (e035:129-135,293) | iid-erasure proxy at p 0.02: r0547 20 %, r0406 40 %, r0313 50 % (Appendix A §c; not cut-edge geometry, `channels.py:93-96`) | FLOOR tiles (> 47 % erased) mostly lie beyond r0406's 40 %. A lower rung's natural customer is the 930 failed attempts, plus a thin FLOOR band for r0313. **Unpriced**; the net-bytes model is withdrawn (C7) |
| e039 colour footings: VersaLink F C 16.7 / M 24.0 / Y 30.4 %; HP F C 29 / M 19 / Y 48 % (raw hard, `cell_error.py`) | screened / starved, print-frozen | M/Y beyond every rung; VersaLink C within soft r0300 reach (unmeasured) | Sibling planes are dead: this is K-only or the dead-plane tier, not a rung |
| c1 K: VersaLink E 22.0 % RGB / 21.5 % grey (e039:585-624); Canon E 21.3 %, per tile min 17.3 / p5 18.4 / med 20.2 / p95 26.4 / max 35.3 % (e040:125-145; e040's uncommitted per-tile path); HP E dead at placement (e039:724-733) | hard, point-sample, first-placement read (`measure/e039-cell-truth/cell_error.py:31-52,89-101`) | hard: none whole-sheet; r0203-f70 (0.189) reaches only the Canon p5 | arithmetic below |

e038's lever line "Y r0400 / M r0450" matches the GENIE capacities of
0.41 / 0.47 bit with zero code gap. At hard decisions it is one to two
rung steps optimistic. Under the Gaussian soft model it is roughly right.

**c1 vs c2 (inferred arithmetic on measured thresholds; Appendix B)**

**Per-area values.** Net bits per c2-cell area are 4·(k − 132)/4096. The
comparators are c2-r0850 at 0.827 (VersaLink's own VERIFIED sheet D) and
c2-r0700 at 0.671.

| k | 832 | 1024 | 1152 | 1280 | 1600 |
|---|---|---|---|---|---|
| net bits per c2 area | 0.684 | 0.871 | 0.996 | 1.121 | 1.434 |

**Capacity at p = 0.21.** Hard 1.03, soft-Gaussian 1.43 (1.73×). The
owner's reading (b), "a real capacity gain", holds only AT capacity with
zero overhead.

**Hard decisions: a loss.** At the measured p@1 % / p_cap ratios of
0.60–0.79, the admissible R is 0.05–0.16, which is 0.10–0.61× c2-r0850.
The 0.55–0.61× figure holds only at the f50/f70 ratio of 0.77–0.79, and
it is extrapolated below the smallest built R (0.203).

**Soft decisions (unmeasured model):**
- r0250-f50 (soft 0.2132) comes to 1.05× at Canon 21.3 %. That is a tie
  inside grid and 200-trial noise. At 200 iterations it reaches 0.220
  (VersaLink RGB).
- r0234-f50 (0.98×) closes all three whole-sheet channels with margin.
- Folded with the soft closable-tile fraction, the result is 0.58–0.66×
  c2-r0850 (0.70–0.82× c2-r0700). An earlier "0.74–0.81×" was the
  ÷ c2-r0700 column.
- A code within 1.5 dB at R 0.27 would give 1.16×.
- **So with the 132-bit per-tile overhead and the recipe's gaps, c1 is at
  best break-even.**

**The instrument caveat (map C10).**
- What is checked: the tool's threshold. The genie threshold moves
  ≤ 0.3 pp (e039:616-617).
- What is not calibrated against the receiver: its position, its
  aperture, and its soft or context read.
- **The contradiction.** It reads VersaLink sheet D at **5.8 %** hard,
  which is +0.92 dB under the equal-variance model (a model number, since
  D's levels are asymmetric). Yet r0850 closed D, and r0850 needs +2.875
  dB, or **0.8 %** BSC (Appendix A). That is ~2 dB and ~7× short.
- So either the tool overstates the effective error, or D's error is
  concentrated. The record supports concentration: 1,553 certificates
  against K 1,552 of 1,961 tiles, so the uncertified 20.8 % would average
  24–28 %. Also, 909 certificates came from retry poses the tool never
  samples.
- **So the 21 % is not shown to be an upper bound.** Concentration cannot
  rescue Canon E, where no tile is below 15 %. Only the overstatement
  branch could move c1.
- **Nothing at c1 has been measured softly.**

**Receiver facts and addressing.**
- The 0-certificate c1-K outcomes on all three engines are receiver
  facts. They stand regardless of the tool.
- The frozen BCH(100,23) t = 13 address word decodes with iid probability
  2.8 % at p = 0.21. 1–2 words per sheet were observed, over 213–430 chain
  poses and 918–1,896 attempted tiles. **The measured binding limit is
  cell error, not addressing.**

**Format standing.**
- A c1 row with a new low rung alone is lawful data (c1-k-r0700@106x74 is
  an emitted identity).
- It becomes a new generation only if the word or the tile has to change
  (docs/FORMAT-SPACE.md:58-62).

**Verdicts (map):**
- (a) holds only as "c1 needs R 0.20–0.27, i.e. r0200–r0250 with a better
  profile, not r0300/r0400".
- (b) is neither demonstrated as measured nor refuted.

## 6. Alternatives for the 4096−100 bits

- **Shorten vs puncture (measured).**
  - Info-tail shortening (`tile.py:59-67,157`) is the strongest per p in
    every row. For example, r0313 shortened reads 0/200 at p 0.12–0.13.
  - **punct_last: the verifier's correction.** The 200/200 in Appendix A
    §d is a **decoder-budget artefact, not a property of the code**
    (`verify/punct_results.json`):
    - Noiseless at 60 + 60 iterations it gives 0/50 syndrome-valid, while
      all 50/50 information parts are correct.
    - At a 200 budget it gives 20/20, with a mean of 119 iterations.
    - Under noise it keeps a residual cost of its own. At r0547 p 0.06 it
      decodes 18/20 at both 200 and 400 iterations, against 0/200
      failures for the shortened code and for the mother code.
    - r0313 p 0.12 goes 20/20 at 200.
  - **punct_even: the cost is real at the production budget.** At r0547 it
    fails 5/14/57 per 200, against 0/2/6 for shorten (Appendix A §d).
    - Whether that cost is budget-bound is unresolved: r0547 plateaus at
      19/20 at 400, and r0313's 48/50 → 20/20 is not significant.
    - Part of it is a rate increase (0.547 → 0.563).
  - Any puncture needs a new rung id or a v2 generation token
    (`lattice.py:63-66`). It buys user bits, not reach for any regime in
    §5.
- **Degree profile (measured before the search).**
  - A per-rung `heavy_frac` LdpcSpec field (default 0.30) was the only
    measured code-side lever, at R 0.20–0.31.
  - The six frozen draws stay byte-identical if heavy_frac is kept out of
    the seed string (`ldpc.py:409`). The fork guards are
    tests/test_ldpc.py:44-68 H_SHA/CW_SHA (the optional paperholo lane,
    run explicitly) and tests/holo/test_holo_ldpc.py:43-72.
  - holo's loader already accepts any nh (`construct.py:166-172`).
  - This is a recipe change under FORMAT-SPACE user input 6. §7 widens
    this lever.
- **Other families** (protograph/ARA precoding, 5G BG2, constrained
  no-isolated-white codes).
  - These are schema or substrate changes. They are priced only if c1 gets
    a measured customer.
  - Nothing to gain at R ≥ 0.4, where the existing rungs sit 0.85–1.21 dB
    off.
  - ARA partial precoding is inside §7's Tier B2 as a same-schema variant.
- **Tile length at c1** (128×128, n = 16384; inferred).
  - The dispersion penalty only goes 0.028 → 0.014 bit, and the overhead
    3.2 % → 0.8 %.
  - That is second-order against a 1.6–2 dB code gap and the t = 13 word.
  - It would be a new generation.
- **p-axis.**
  - Plane-uniform, 180 bits per step, which is 56 % of one rung step
    (docs/P-AXIS-DESIGN.md:200-203). It is dominated by a true rung at
    equal area rate.
  - Low-Y triplets blow up the column-group spare at p244/p300 (Z → 2,
    21–44 bits per site). Any low-rung colour row would be minted at p120
    only.
- **Dead-plane tier.**
  - For a low-Y triplet, the dead-Y ceiling (34/41) and the any-one ceiling
    (24/41) diverge.
  - The planner enforces the any-one ceiling (`src/holo/gen/plan.py:106-121`;
    `capacity.py:283-286`), so a q = 0.8 low-Y row today is sized with NO
    promise.
  - The column-group selector also lacks a carried[light] floor.
    r0850x0850x0313 lands at Z = 3 (3:3:1), and its any-one ceiling of
    4/7 is below the uniform 2/3 (`column_groups.py:112-147`).
- **Withdrawn: C7**, the confetti net-bytes model (R × yield 0.435 vs
  0.385 at 25.4 mm; break-even ≈ 2.6 tiles per edge). It was refuted 2 of
  3: nothing on file computes those figures, e015's 0.796 yield is a
  single c3/r0550 simulation, the c2 grain is ~10 mm (e014:360), and the
  FLOOR tiles lie mostly beyond r0406's reach.

## 7. The construction search

**Why.** The candidates in §4 are ONE draw each of a recipe tuned for R ≥
0.55. The owner asked for r0300/r0400, and ruled on 2026-09-30 that the
frozen rungs are **full rows** of the search, not a control. So the
question became what the best buildable code is at each k, under the same
schema (n = 4096, Z = 64 QC e-IRA, shortened per tile, CRC-32 inside).

### 7.1 Design

- **Tier A — recipe space.**
  - The search space: heavy degree {6..16 step 2} × heavy fraction
    {0.2..0.8} × light degree {3, 4} × placement {uniform, balanced}.
    That is 168 configs per k, minus seed-0 build timeouts.
  - **Balanced placement** spreads the information edges evenly over the
    block rows, instead of the recipe's uniform row draw.
  - Search configs RESTART on an info-free block row (rule e). The
    baselines are the frozen recipe exactly.
- **Tier B1 — density evolution.** Profiles are designed by
  Gaussian-approximation DE (GA thresholds, with a population-dynamics MC
  cross-check). 20 DE candidates per k, built as QC codes.
- **Tier B2 — variants over Tier A base configs:**
  - ARA-precoded e-IRA (a fraction of information block-columns
    precoded, with punctured intermediate bits);
  - IRAA (second-accumulator parity rows).
- **Evaluation protocol:**
  - **Common random numbers.** Every code sees the same trial seeds.
  - **Screen 0: build and structure.** Girth > 4, no info-free block row,
    and a two-information-bit pair weight at or above a floor.
  - **Screen 1.** Four points at the anchor's 10 % points (AWGN +0 /
    +0.25 dB, BSC +0 / +0.005), 100 trials each. The score is the mean ln
    BLER.
  - **Screen 2: walks** at 200 trials per point, then `fine` at 500
    trials around the 1 % point. Side channels are measured at the code's
    own 1 % point:
    - confidently-wrong LLRs at f = 0.1 / 0.2 / 0.5 / 1 % of cells,
      magnitude 20;
    - erasure ε 0.3 + 2 % flips.
  - **Any syndrome-valid wrong decode in screens 1–2 disqualifies a code.**
  - **Confirm stage.** FRESH trials (t ≥ 20000, never used to select),
    **5000 trials per point**, 0.05 dB / 0.0025 p grids. This is the only
    stage free of the winner's curse.
- **Fast decoder** (`search/fast/fastdecode.py`).
  - What it is: a batched, **bit-exact twin** of `holo.core.ldpc.decode`,
    with the same schedule, the same float-sum order, and first-argmin
    ties.
  - **Bit-exactness, measured:**
    - 10,800 decode comparisons over 9 codes, covering
      `(ok, hard, n_iters)` and the extrinsic array byte for byte:
      **0 mismatches**.
    - The independent verification (`search/fast/verify/`) adds 533
      comparisons per code on r0406/r0547/r0700/r0850, including
      adversarial inputs (±inf, signed zeros, denormals, half-erased):
      **0 mismatches, PASS**.
    - The run-level check found production and fast equal outcome for
      outcome: 473 points / 55,300 decodes / 47 undetected, 0 mismatches
      (RUN-PLAN).
  - **Speed.** 1.41–1.72× per core single-thread at B = 32 (README), and
    1.5–1.8× per decode at 14 workers (RUN-PLAN calibration). The
    verification's own benchmark (`verify_bench.py`) left no result file.
  - **Free-threaded threads never beat spawned processes.** Measured
    (fast/README.md, one quiet repetition): 14 processes gave 669 dec/s,
    against 623 for 14 threads and 603 for 7 processes × 2 threads.
    numpy does not get faster from free-threading.
  - **The BLAS knob.** This numpy links Apple Accelerate, so
    `VECLIB_MAXIMUM_THREADS` is the thread knob. `OMP_NUM_THREADS` and
    `OPENBLAS_NUM_THREADS` do nothing on this build.
  - Exactness is a property of this numpy build: re-run
    `test_fastdecode.py` after any numpy upgrade or on another machine.

### 7.2 Trial findings (trial-A, -A2, -B1, -B2; production decoder; k = 1664 / 1600 / 1280 / 1216)

These are selection-trial numbers (100 / 500 trials per point), NOT the
confirm stage. The Δ is against the trial's own re-measure of the
frozen-recipe base code at 500 trials per point, which differs from
Appendix A's 200-trial value.

| k (candidate) | frozen recipe gap: harness 200/pt (trial re-measure) | best clean Tier A config | best gap | gain |
|---|---|---|---|---|
| 1664 (r0406) | 1.30 (1.29) | h8 f0.5 l3 balanced s0 | 1.13 dB | 0.16 dB |
| 1600 (r0391) | 1.25 (1.27) | h12 f0.3 l3 balanced s1 | 1.09 dB | 0.18 dB |
| 1280 (r0313) | 1.77 (1.87) | h12 f0.5 l3 balanced s1 | 1.35 dB | 0.53 dB |
| 1216 (r0297) | 1.90 (1.80) | h10 f0.5 l3 uniform s1 (3 rule-e restarts); tied by h12 f0.3 l4 balanced s0 | 1.35 dB | 0.45 dB |

Source: trial-A/TABLES-search.md finalists; the k 1600 winner's one
undetected decode came on the confidently-wrong side channel, not in
screens 1–2.

1. **Balanced placement removes the info-free rows.**
   - Balanced placement needed **zero** rule-e restarts in 36/36 configs
     at every k.
   - Uniform placement needed a mean of 0.3–0.5 restarts at k 1664/1600,
     and **a mean of 13.6 at k 1280/1216** (max 244 / 175; zero in only
     16/36 and 13/36).
   - With it (and heavy fraction 0.5 at the low k) the search buys
     **0.45–0.53 dB at k 1280/1216 and 0.16–0.18 dB at k 1664/1600**. The
     best gaps are 1.35 / 1.35 / 1.13 / 1.09 dB.
   - The frozen-recipe base codes threw undetected decodes in the same
     trials, all four of them: base-r0313 18/4300, base-r0391 5/4200,
     base-r0406 1/4100, base-r0297 1/4500.
2. **Seed variance is small against configuration effects.**
   - The median Es/N0@10 % spread between seeds of one config is
     **0.025 dB** (trial-A2, 8 configs; max 0.085).
   - Configuration effects reach **0.5 dB**.
   - Screen-1 score: the within-config SD is 0.05–0.08, against a
     between-config SD of 0.57–0.79 (trial-A2).
3. **A pair-weight floor of 10 is too low.** The k 1280 code h10 f0.5 l3
   balanced s0, with min w2 = 10, threw **19/2500 wrong decodes**, 14 of
   them listed on its weight-10 two-info-bit word (trial-A2). The
   overnight screen-1 floor is **16** at the search k.
4. **Confidently-wrong LLRs wreck every code alike.**
   - At f = 0.5 % of cells (magnitude 20), every finalist fails 99–100/100
     at its own 1 % point (one IRAA variant in trial-B2 at 99).
   - f = 0.1 % already costs 30–89/100 (10/100 for that one IRAA variant).
   - This is a decoder-axis question (clipping, damping, erasure
     marking). The search reports it and does not try to fix it.
5. **B1 (density evolution): the DE ordering partly survives at n = 4096.**
   - ρ(GA threshold, screen-1 score) is 0.59–0.70 at k 1280–1664, and 0.21
     at k 1216.
   - The GA-optimum profile at k 1664 walked to −3.000…−3.097 dB over 4
     seeds (gap 1.03–1.13 dB), close to Tier A's best.
   - The GA-optimum profiles sit 0.33–0.38 dB from Shannon at infinite
     length. The rest is finite-length and construction loss.
   - Several DE candidates threw undetected decodes (1–12 per candidate).
6. **B2 (variants): ARA partial precoding of 25–50 % of the heavy columns
   buys a further 0.06–0.11 dB clean.**
   - k 1664: ara-p0.25h gains 0.10 dB, gap 1.02 dB. It was better in 7/7
     screen-1 pairs.
   - k 1280: ara-p0.25h gains 0.06 dB. The 0.18 dB ara-p0.5h code threw
     1 undetected decode and is disqualified.
   - k 1216: ara-p0.5h gains 0.11 dB.
   - k 1600: nothing beats the plain winner.
   - IRAA lost in the paired screen 1 (q0.25 and q0.5 worse in 8/8 at
     k 1664).
   - Findings 5 and 6 are this record's reading of the trial tables; they
     are not confirmed.

### 7.3 The overnight run (plan in brief; `search/RUN-PLAN.md`)

**Launch.** 2026-09-30 23:21:54, pid 55343, 14 spawn workers, the fast
decoder. The preflight bit-exact tests were green at 23:23:35. It
touches nothing outside scratch, commits nothing, and uses no hardware.
The tables report; adoption is the owner's.

| stage | grid | seeds | codes | expected wall |
|---|---|---|---|---|
| A-primary | recipe space at k 1664 / 1280 (152 / 162 configs); 24 finalists, 8 at 500 trials | 24 | 7,536 | 1.9 h |
| A-frozen | the frozen rungs as FULL ROWS: k 2240 / 2560 / 2880 / 3200 / 3520 (45 / 38 / 29 / 36 / 30 configs), with r0547 + r0550, r0625, r0700, r0775 and r0850 as named baselines; screen-1 floor = the incumbent's own min(w1, w2) (6 / 6 / 7 / 5 / 4), since no built config there reaches 16 | 4 | 712 | 0.4 h |
| A-secondary | recipe space at k 1600 / 1216 (155 / 164 configs) | 16 | 5,104 | 1.3 h |
| B1 | 20 DE candidates per k, at the four search k | 12 | 964 | 0.8 h |
| B2 | 4 base configs × 9 ARA/IRAA variants per k, at the four search k | 8 | 1,152 | 0.6 h |
| confirm | per k (all nine): the top 12 clean by Es/N0@1 % + top 3 by p@1 % + every named baseline; FRESH trials t ≥ 20000; **5000 trials per point** | — | ~141 | 1.75 h |

**Budget.** About 76 CPU h plus about 4 h of builds and DE. Expected wall
**~7.0 h**, 8.4 h with a 20 % margin; the plan says "past ~08:30
something is wrong". The combined table will be
`scratch/rung-ladder-20260930/search/overnight-ALL/TABLES-search.md`.

**Not covered:**
- the decoder is fixed;
- no measured print/scan LLRs, bursts or per-plane correlation;
- no error floor below the confirm resolution (~1 %);
- no minimum distance beyond min w1 / w2;
- no other families;
- no k between the listed ones;
- configs whose seed-0 build hit the 120 s cap are grid holes;
- screen 1 selection noise: only the confirm stage is winner's-curse
  free.

### 7.4 RESULTS (2026-10-01, measured overnight; `overnight-ALL/TABLES-search.md`, `overnight-CONF/TABLES-confirm.md`)

The run started 2026-09-30 23:21:54 and ended 2026-10-01 06:04:00 with
every stage DONE and 0 errors (A-primary 138 min, A-frozen 18, A-secondary
95, B1 33, B2 22, confirm 90): 22,688 codes built (corrected 2026-10-17:
the run log's stage s0 counts sum to 15,478 built configurations, 15,474
tabulated in `overnight-ALL`; the source of 22,688 is not found),
11,592,700 decodes by the log, the
fast decoder throughout (selfcheck passed, no fallback). Below, per rung,
the best CLEAN code of the 5000-trial confirmation (fresh trials t ≥ 20000,
never used for selection; 0.05 dB / 0.0025 grid, 0.0005 below p 0.02)
beside the frozen code or frozen-recipe baseline. "Clean" = 0 syndrome-
valid wrong decodes in the confirmation. `und` = such decodes / confirm
trials. Gap = to Shannon at 1 % BLER. Codec sim only; NO promotion; the
tables REPORT, adoption is the owner's.

| k (rung) | best clean code (tier · config) | Es/N0@1 % | Δ vs base | gap dB | p@1 % | gap bit | min w1 / w2 | baseline: Es/N0@1 % / gap / p@1 % / und |
|---|---|---|---|---|---|---|---|---|
| 3520 (r0850) | A · h6 f0.4 l3 uniform s2 | 2.818 | +0.003 | 0.83 | 0.0098 | 0.061 | 27 / 6 | frozen r0850: 2.816 / 0.82 / 0.0089 / **5 / 30,000** |
| 3200 (r0775) | A · h8 f0.4 l3 uniform s3 | 1.692 | +0.096 | 0.89 | 0.0218 | 0.067 | 27 / 8 | frozen r0775: 1.596 / 0.79 / 0.0197 / **6 / 40,000** |
| 2880 (r0700) | A · h10 f0.3 l3 balanced s2 | 0.611 | +0.011 | 0.85 | 0.0350 | 0.078 | 25 / 7 | frozen r0700: 0.600 / 0.84 / 0.0346 / 0 / 30,000 |
| 2560 (r0625) | A · h12 f0.3 l3 uniform s1 | −0.360 | −0.019 | 0.87 | 0.0484 | 0.095 | 32 / 11 | frozen r0625: −0.340 / 0.89 / 0.0489 / **30 / 30,000** |
| 2240 (r0547) | A · h12 f0.3 l3 balanced s1 | −1.324 | −0.102 | 0.89 | 0.0690 | 0.091 | 25 / 13 | frozen r0547: −1.223 / 0.99 / 0.0652 / 0 / 30,000; frozen r0550: −1.161 / 1.05 / — / **123 / 60,000** |
| 1664 ("r0400") | B1 · DE profile 16×7.8×2.3×17, balanced, s9 | −3.094 | −0.317 | 1.03 | 0.1113 | 0.090 | 46 / 17 | recipe k1664: −2.778 / 1.35 / 0.1018 / 11 / 35,000 |
| 1600 | B1 · DE profile 16×7.7×2.3×16, balanced, s7 | −3.250 | −0.250 | 1.11 | 0.1159 | 0.092 | 100 / 22 | recipe k1600: −3.000 / 1.36 / 0.1084 / 23 / 35,000 |
| 1280 ("r0300") | B1 · DE profile 16×5.4×15, balanced, s4 | −4.331 | −0.467 | 1.29 | 0.1474 | 0.084 | 37 / 37 | recipe k1280: −3.864 / 1.76 / 0.1275 / 55 / 40,000 |
| 1216 | B2 · h12 f0.3 l4 balanced + ARA precoder on 3/8 of the info columns, s1 | −4.647 | −0.510 | 1.26 | 0.1558 | 0.079 | 45 / 38 | recipe k1216: −4.137 / 1.77 / 0.1369 / 3 / 35,000 |

Readings (measured, this run):

- **Frozen rungs (k 2240–3520): nothing beats the incumbents on the
  waterfall.** The best clean codes sit within −0.10 … +0.10 dB of the
  frozen codes, inside the noise of a 5000-trial 1 % point (qualified
  2026-10-17: at k=2240 the best clean code's −0.10 dB is resolvable, 13
  vs r0547's 77 failures of 5,000 at −1.25 dB, a draw difference; at
  k=3200 frozen r0775 beats the best clean code by 0.096 dB, 47 vs 165 of
  5,000 at 1.60 dB; neither changes the reading that the frozen rungs
  stand). The one
  measurable difference is the syndrome-valid wrong-decode floor: r0850,
  r0775, r0625 and r0550 land on their low-weight pair words (4 / 5 / 6 / 6)
  in 5, 6, 30 and 123 of 30,000–60,000 confirmation trials (0.02–0.2 %,
  CRC-caught in production, a lost attempt each); r0547 and r0700 are
  clean at 30,000. The search found clean codes at every frozen k with
  pair weights 6–13 — a hygiene property only.
- **Low rungs: the search found 0.25–0.51 dB.** k=1664: 1.35 → 1.03 dB
  (B1 DE profile); k=1600: 1.36 → 1.11 (B1); k=1280: 1.76 → 1.29 (B1);
  k=1216: 1.77 → 1.26 (B2 precoded). The hard BSC gap fell to 0.079–0.092
  bit, the frozen ladder's level. Every winner uses BALANCED placement;
  three have top degree 16, the grids' ceiling, and the k=1216 winner's
  is 12 (corrected 2026-10-17); the k=1664/1600 B1 winners are three-class
  degree profiles (labels as in the tables, e.g. `16x7.8x2.3x17` = 7 block
  columns of degree 16, 2 of degree 8, 17 of degree 3) that density
  evolution ranked and the measurement confirmed, the k=1280 winner
  `16x5.4x15` two-class with light degree 4 (corrected 2026-10-17); the B2 winner at k=1216 is the only place a
  precoder (ARA, 3/8 of the information block columns) beat the plain
  structure, by 0.01 dB over the B2 runner-up and ~0.1 dB over the best
  plain code. All winners are clean at 5000 trials with pair weights
  17–38.
- **Residual gap:** 1.03–1.29 dB at k 1216–1664 against ~0.45 dB (inferred)
  for the n=4096 finite-length bound; the remaining 0.6–0.8 dB is the
  construction family at this length, not the recipe's parameters
  (2026-10-17: that attribution is INFERRED at a grid edge — three winners
  sit at the top degree the grids allow, 16, nothing above 16 was measured
  (h20 did not build), the ~0.45 dB figure is computed in no file, and
  B1's own DE optima sit 0.33–0.38 dB from Shannon at infinite length).
- **Seed variance:** within-configuration spread of the 10 % point
  0.015–0.067 dB (median ~0.03) at every k; between-configuration spread
  of the screen-1 score 4–10× the within-configuration spread; the
  overnight's 8–24 seeds therefore bought ≤ 0.05 dB of draw selection,
  as the trial predicted.
- **Not run / not covered:** k < 1216 (the c1 line); B1/B2 at the frozen
  rungs; light degree 4 and heavy fraction > 0.6 at the frozen rungs; the
  confidently-wrong-LLR side check beyond the trial sizes; any paper.
  Verifier caveat carried: the Tier A BSC walk is coarse (0.005) at
  k ≥ 3200, so the confirmed table (fine grid) is the one of record there.
- **Loadability, and the R4(b) price (added 2026-10-17).** None of the
  four winners loads in production: `construct.load_code` takes one heavy
  class and light rows of width 3 (`src/holo/core/ldpc/construct.py:169-170`);
  the k=1664/1600 winners are three-class, the k=1280 winner has light
  degree 4, the k=1216 winner has light degree 4 and an ARA precoder on
  an n > 4096 mother graph (`tile.py` asserts n = 4096). The best
  schema-fitting clean codes (two classes, light degree 3, balanced) trail
  the winners by 0.04–0.08 dB — k=1664 h12 f0.4 l3 bal 1.10 vs 1.03,
  k=1600 1.16 vs 1.11, k=1280 1.33 vs 1.29, k=1216 1.34 vs 1.26 — and at
  k=1216 the confirm resolves the difference (52 vs 102 failures of 5,000
  at −4.65 dB). Even they need the recipe to grow balanced placement
  (which draws `g.random` floats where the frozen recipe and
  `keystream_ref.GeneratorRef` are integers-only) and a per-rung heavy
  fraction: recipe changes under FORMAT-SPACE user input 6 (R4).
- **The pair-weight screen does not predict cleanliness (added
  2026-10-17).** Every confirm finalist passed min pair weight ≥ 16 with 0
  undetected decodes in its screens, yet at 5,000 fresh trials k=1664 10
  of 15 non-baseline rows, k=1600 9 of 15, k=1280 11 of 15 and k=1216 3 of
  15 threw syndrome-valid wrong decodes, and cleanliness splits by seed
  inside one configuration (k=1664 h12 f0.4 l3 bal: s18 0, s17 12). The
  frozen rungs' own floors are in the table above. "Clean" is a per-draw,
  trial-count-bounded observation (0 in 5,000 bounds the rate to about
  6 × 10⁻⁴ at 95 %); R5's proposed screen would admit these codes.

## 8. Rulings owed to the owner

These are options with their costs and evidence. The record recommends
none of them.

- **R1 NAMING — how a new rung is spelled.**
  - Why it comes first: the token seeds the matrix and the id seeds AES
    (docs/FORMAT-SPACE.md:212-216,229-241,284-288), so this has to be
    ruled before any golden exists.
  - The record has no single snap rule:
    - Nearest-snap is the r0550 comment (`construct.py:71`); r0625,
      r0700 and r0775 are consistent with it.
    - Upward snap is r0850 (3520, where nearest gives 3456), and it is
      undocumented.
    - r0547 uses a true-rate token.
  - What each rule gives: "r0400" is k 1664 under either snap. "r0300" is
    k 1216 (nearest) or k 1280 (upward).
  - Options:
    - (a) one snap rule, written down, with the frozen exceptions recorded;
    - (b) true-rate tokens (r0297 / r0313 / r0406).
  - Cost: none. Evidence: §4.
- **R2 r0550 — how "keep 547" is spelled** (the direction was given
  2026-09-30, §3).
  - Options:
    - (a) emission retirement only;
    - (b) (a) plus a PROFILES re-key to r0547.
  - Stays either way: the mother code, the fossils and the sunset
    boundary.
  - Cost: one sentence plus one help string for (a); new v2 identities
    for (b).
- **R3 The characterize table.** Fix "r0859" → r0850 and add r0547. This
  is rates only, with no format effect.
  - Cost: ~1 h. That covers moving tests/holo/test_characterize_margins.py:255-257
    and running HOLO_RUN_CHARACTERIZE_SWEEPS=1.
  - Options: do it, or leave it.
- **R4 The construction lever for new rungs.**
  - Options:
    - (a) a per-rung `heavy_frac` LdpcSpec field (default 0.30, kept out of
      the seed string; `src/paperholo/ldpc.py:183,276,323`,
      `util/regen_holo_ldpc_data.py:44-61`);
    - (b) a wider recipe space, covering placement, heavy degree, light
      degree and ARA, per the overnight search's confirmed rows;
    - (c) refuse any recipe change.
  - Cost of (a): about half a day, with the goldens and H_SHA/CW_SHA
    proving the six draws unchanged. (b) priced 2026-10-17 from the
    confirm (§7.4, the loadability reading): the winners need three
    degree classes, light degree 4 and, at k 1216, an ARA precoder on
    n > 4096 — schema changes, not parameters; the best schema-fitting
    codes trail by 0.04–0.08 dB and still need balanced placement plus a
    per-rung heavy fraction.
  - This is a recipe change under FORMAT-SPACE user input 6. Evidence:
    §4, §7.2.
- **R5 Minting r0300/r0400.** The owner said in dialogue that he wants
  them.
  - Options:
    - (a) mint now on the frozen recipe;
    - (b) mint after the overnight search, on a confirmed construction;
    - (c) mint when a measured customer appears.
  - Cost: minting is irreversible, with ~14 pin sites and four ladder
    spellings.
  - Evidence:
    - No regime measured with a blind detector sits inside their hard
      reach (§5).
    - The soft reach one step lower is unmeasured.
    - The e038 "blind" rows are supervised.
    - The confirmed search gain is 0.47 / 0.51 dB at k 1280 / 1216 and
      0.25 / 0.32 dB at k 1600 / 1664 (§7.4; the trial's 0.45–0.53 dB
      superseded 2026-10-17).
    - (Withdrawn 2026-10-17: "f50 was never run at k 1664" — the trial's
      k 1664 winner is h8 f0.5, and the overnight swept heavy fraction
      0.2–0.8 at every search k.)
  - A possible acceptance screen for new rungs only: no info-free block
    row, and pair weight ≥ 16 (the overnight floor; 10 was shown too low,
    §7.2 finding 3). r0550 / r0625 / r0775 / r0850 would fail it
    retroactively at 6 / 6 / 5 / 4. The pair weight is a screen, not the
    minimum distance. (2026-10-17: the confirm shows the screen does not
    predict cleanliness — §7.4's added reading; an acceptance gate would
    need a sized fresh-trial run per minted draw, not a pair-weight bar.)
- **R6 Puncturing.**
  - Options:
    - (a) shorten stays, and puncturing is not a v1 lever;
    - (b) measure punct_even further (n ≥ 200, a higher budget).
  - In either case, every record that says "punct_last kills every code"
    would be corrected to the budget-plus-residual reading of §6.
  - Cost of (b): a harness run.
- **R7 The planner.** Options: a "dead-Y-only" tier-promise spelling plus a
  carried[light] ≥ 3 floor in column_groups, or refuse such rows. Cost:
  small, generator-side, with no receiver change. Evidence: §6.
- **R8 The c1 line.**
  - The next measurement would be on machine 1, using snapshots
    run-E-c1-k-both2.26022 / run-E-canon.33065 under scratch/<city>/.
    It needs zero toner. The map's order:
    - (i) Commit e040's per-tile `cell_error` path and calibrate it on
      sheet D, certified vs uncertified tiles, plus a ±half-cell
      offset / placement check on E.
    - (ii) Adapt measure/stripe_f_discriminant.py to K at c1: test error
      and empirical MI for point, 0.7-cell box, 3×3 LDA,
      inked-neighbour-conditioned and genie 3×3 reads, with an offset
      search and an RGB + grey LLR sum.
  - A proposed bar: a soft equivalent ≥ −4.7 dB (≈ 0.36 bit/cell)
    whole-sheet before any c1 code is discussed, with the line closed
    below −5.5 dB.
  - Also proposed, not a ruling of record: quote no corrected c1 figure
    until (i) lands. e040:136-137 already quotes "8–10 % with soft
    decisions and context".
  - The K wake-storm fix (57 cpu-h, e039:597-612) precedes any further c1
    decode.
  - Options: order the measurement, re-order it, or close the line.
- **R9 The first sim gate, if anything is minted.**
  - The steps: a scratch re-draw on the real labels, the harness BSC /
    AWGN / erasure runs plus the pair audit, then the slow-lane e2e runs
    `c2-k-r0400@53x37` and `c2-cmy8-r0700x0700x0400@53x37` at p120,
    byte-exact.
  - Plus the offline sheet-J replay: n_informative per tile-stream for the
    2,031 FLOOR and 930 ATTEMPTED-failed streams against 1160 / 1480 /
    1544 / 2120, split cut-edge vs hidden-face. This would decide whether
    a confetti customer exists, replacing the withdrawn C7.
  - Cost: hours of CPU, no toner.
- **R10 The first print candidate.**
  - Options:
    - (a) none until R8/R9 produce a customer;
    - (b) one K confetti sheet `c2-k-r0400` beside a `c2-k-r0547` control
      from the same batch, with the cut size set from the J replay.
  - Constraint: no low-Y colour row until an engine shows a blind-detector
    plane between 0.30 and 0.45 bit.
  - Any print needs the owner's go (.claude/rules/hardware.md).

## 9. Owed / not measured

- **The overnight search results** (§7.4): DONE 2026-10-01.
- **c1 instrument.** Calibration of `cell_error.py` on D (the per-tile
  code is uncommitted) and a c1 offset check on E.
- **Soft MI.** c1 soft / context / two-capture MI: nothing at c1 has been
  measured softly. The same holds for soft MI from the e038 classifiers.
- **f50 runs.** Heavy fraction 0.2–0.8 was swept at k 1216 / 1280 / 1600
  / 1664 by the overnight (corrected 2026-10-17); still owed on the real
  seed labels and at the c1 k's. Construction-seed variance beyond the
  search's four k.
- **Minimum distance.** 3+-info-bit codeword enumeration for every rung.
- **Confetti.** The sheet-J FLOOR / ATTEMPTED split, and a confetti yield
  model on real scraps (C7 withdrawn).
- **Engine.** The e038 sethalftone/PJL engine-contrast sheet and the
  fresh-toner discovery re-take.
- **Decoder axis:**
  - whether 60 / 150 iterations stay rung-agnostic (200 bought
    0.1–0.75 dB);
  - the confidently-wrong-LLR failure.
- **Puncture.** punct_even at a higher budget with n ≥ 200.
- **k 2176.** k = 2176 (0.531, flagged open in e017), never built.
- **Soft model.** The Gaussian-soft assumption vs the VersaLink's
  asymmetric blank-side fill-in.
- **Error floors** below 1 % BLER, at any rung.
- **Added 2026-10-17 — the gaps the confirm left** (evidence in
  measure/rung-ladder/results/, README §2026-10-17):
  - the finalists under production conditions: p120 shortening, the
    60 → 150-iteration retry tier (`src/holo/receiver/plugins/tiles.py:35-36`),
    the receiver's LLR clamps — every ranking here is the unshortened
    mother code at 60 iterations plus one sum-product retry;
  - erasure on the tile's slot map and shortened tail, on the winners
    (the confirm ran BSC and BIAWGN; the winners have one iid erasure
    side point);
  - addressing at the design points: under an iid hard-error model the
    BCH(100,23) t = 13 word decodes cold with probability ~0.78 / 0.375 /
    0.29 at the k 1664 / 1280 / 1216 winners' p@1 % (0.111 / 0.147 /
    0.156), all above the receiver's PROVISIONAL `BER_ENVELOPE` 0.08
    (`plugins/place.py`); nothing has evaluated placement there;
  - the grid above top degree 16, and k < 1216 for the c1 hinge (§5:
    1.16× at 1.5 dB, R 0.27);
  - a sized fresh-trial acceptance run per minted draw (the pair-weight
    screen does not predict cleanliness, §7.4);
  - §5's hard-vs-hard customer test replaced by a receiver-LLR
    measurement (C10 and e040's sheet G contradict it);
  - a bit-exactness re-run of `search/fast/test_fastdecode.py` on a
    current `env/` (proved on the wiped machine 4's numpy 2.5.3 only).

---

# Appendix A — TABLES.md (the rung-ladder harness), carried verbatim

Source: `scratch/rung-ladder-20260930/TABLES.md`. The text below is
verbatim; only the heading levels are shifted by two so they nest here.

**Verifier's caveats (inserted; from the map's refutation pass and
`verify/`):**
- **(1) punct_last in §d is a decoder-budget artefact, not a code
  property.** Noiseless it reads 0/50 syndrome-valid at 60 + 60
  iterations with 50/50 information parts correct, and 20/20 at 200.
  Under noise it keeps a residual (r0547 p 0.06: 18/20 decoded at 200 and
  400) (`verify/punct_results.json`).
- **(2) r0550's low-p undetected 1/200 is one trial repeated down the
  grid.** It comes from the shared seed base (common random numbers);
  only trial 154 is traced to the weight-6 word.
- **(3) One draw per label, 200 trials per point.** Differences under
  ~0.02 p or 0.25 dB are noise.
- **(4) r0250's BIAWGN 3.06 dB is a floor artefact.** It comes from 2/200
  stuck trials; the 10 % point puts it at ~1.7 dB.
- **(5) "min w2" is the two-info-bit pair weight, not the minimum
  distance.**
- **(6) Identities were checked by edge digest through both ports, and
  five spot points were re-measured** (`verify/digest_results.json`,
  `verify/spot_results.json`).

### Rung-ladder measurement — rung-ladder-20260930

Command: `cd <repo> && PYTHONPATH=src:. env/bin/python scratch/rung-ladder-20260930/harness/sweep.py --workers 12`  
Trials/point: 200 (chunks of 50), workers 12, wall 381 s.  
Seeds: trial t uses `np.random.default_rng(base + t)`, base = {'bsc': 100000, 'awgn': 200000, 'eras': 300000, 'accom': 400000, 'record': 0} (the 'record' channel uses the test's own 50_000/60_000 bases and magnitude 4.0).  
Decoder: `holo.core.ldpc.decode.decode` (production; min-sum α=0.8, 60 iters + one sum-product retry). Hard BSC LLR = ±log((1−p)/p) (tests/test_ldpc.py `_hard_llr` uses a FIXED magnitude 4.0, default, 8.0 in one identity check). Failure = not syndrome_ok or hard ≠ codeword; undetected = syndrome_ok and hard ≠ codeword.  
Walks: (a) from the BSC-capacity grid point (0.005 grid) down until two consecutive 0/200, up until BLER ≥ 0.5; (b) same on a 0.25 dB Es/N0 grid from the Shannon point. p@1%/p@10% by linear interpolation in log BLER (0/n floored at 0.5/n). Codes: existing six (frozen data), six candidates (frozen recipe), four VARIANTS (not the recipe).

#### Structural

| code | kind | k | R | kb/mb | nh×deg | restart | draw s | edges | chk deg min..max (mean) | checks w/o info edge | var deg hist | girth>4 | min w1 | min w2 (#≤8) | user bits p100 / p120 | S(p120) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r0547 | existing | 2240 | 0.5469 | 35/29 | 10×10 | 0 | frozen | 14911 | 5..10 (8.03) | 0 (0.0%) | 1:1, 2:1855, 3:1600, 10:640 | True (max 1) | 49 | 12 (0) | 2108 / 2088 | 2087 |
| r0550 | existing | 2240 | 0.5469 | 35/29 | 10×10 | 0 | frozen | 14911 | 3..10 (8.03) | 0 (0.0%) | 1:1, 2:1855, 3:1600, 10:640 | True (max 1) | 47 | 6 (2) | 2108 / 2088 | 2087 |
| r0625 | existing | 2560 | 0.6250 | 40/24 | 12×10 | 0 | frozen | 16127 | 6..12 (10.50) | 0 (0.0%) | 1:1, 2:1535, 3:1792, 10:768 | True (max 1) | 35 | 6 (1) | 2428 / 2408 | 2407 |
| r0700 | existing | 2880 | 0.7031 | 45/19 | 14×10 | 0 | frozen | 17343 | 11..16 (14.26) | 0 (0.0%) | 1:1, 2:1215, 3:1984, 10:896 | True (max 1) | 25 | 7 (1) | 2748 / 2728 | 2727 |
| r0775 | existing | 3200 | 0.7812 | 50/14 | 15×8 | 0 | frozen | 16191 | 14..20 (18.07) | 0 (0.0%) | 1:1, 2:895, 3:2240, 8:960 | True (max 1) | 25 | 5 (7) | 3068 / 3048 | 3047 |
| r0850 | existing | 3520 | 0.8594 | 55/9 | 16×6 | 0 | frozen | 14783 | 22..27 (25.66) | 0 (0.0%) | 1:1, 2:575, 3:2496, 6:1024 | True (max 1) | 25 | 4 (40) | 3388 / 3368 | 3367 |
| r0250 | candidate | 1024 | 0.2500 | 16/48 | 5×10 | 0 | 0.01 | 11455 | 2..5 (3.73) | 256 (8.3%) | 1:1, 2:3071, 3:704, 10:320 | True (max 1) | 75 | 20 (0) | 892 / 872 | 871 |
| r0297 | candidate | 1216 | 0.2969 | 19/45 | 6×10 | 0 | 0.0 | 12095 | 2..6 (4.20) | 320 (11.1%) | 1:1, 2:2879, 3:832, 10:384 | True (max 1) | 35 | 25 (0) | 1084 / 1064 | 1063 |
| r0313 | candidate | 1280 | 0.3125 | 20/44 | 6×10 | 0 | 0.0 | 12159 | 2..6 (4.32) | 320 (11.4%) | 1:1, 2:2815, 3:896, 10:384 | True (max 1) | 58 | 12 (0) | 1148 / 1128 | 1127 |
| r0391 | candidate | 1600 | 0.3906 | 25/39 | 8×10 | 0 | 0.01 | 13375 | 2..7 (5.36) | 64 (2.6%) | 1:1, 2:2495, 3:1088, 10:512 | True (max 1) | 69 | 11 (0) | 1468 / 1448 | 1447 |
| r0406 | candidate | 1664 | 0.4062 | 26/38 | 8×10 | 0 | 0.01 | 13439 | 3..7 (5.53) | 0 (0.0%) | 1:1, 2:2431, 3:1152, 10:512 | True (max 1) | 43 | 16 (0) | 1532 / 1512 | 1511 |
| r0469 | candidate | 1920 | 0.4688 | 30/34 | 9×10 | 0 | 0.01 | 14143 | 4..8 (6.50) | 0 (0.0%) | 1:1, 2:2175, 3:1344, 10:576 | True (max 1) | 31 | 14 (0) | 1788 / 1768 | 1767 |
| r0313-h14 | VARIANT | 1280 | 0.3125 | 20/44 | 6×14 | 0 | 0.03 | 13695 | 2..6 (4.86) | 64 (2.3%) | 1:1, 2:2815, 3:896, 14:384 | True (max 1) | 39 | 18 (0) | 1148 / 1128 | 1127 |
| r0313-f50 | VARIANT | 1280 | 0.3125 | 20/44 | 10×10 | 0 | 0.01 | 13951 | 2..6 (4.95) | 128 (4.5%) | 1:1, 2:2815, 3:640, 10:640 | True (max 1) | 43 | 15 (0) | 1148 / 1128 | 1127 |
| r0391-h14 | VARIANT | 1600 | 0.3906 | 25/39 | 8×14 | 0 | 0.13 | 15423 | 2..8 (6.18) | 64 (2.6%) | 1:1, 2:2495, 3:1088, 14:512 | True (max 1) | 51 | 10 (0) | 1468 / 1448 | 1447 |
| r0391-f50 | VARIANT | 1600 | 0.3906 | 25/39 | 12×10 | 0 | 0.01 | 15167 | 3..8 (6.08) | 0 (0.0%) | 1:1, 2:2495, 3:832, 10:768 | True (max 1) | 47 | 19 (0) | 1468 / 1448 | 1447 |

#### (a) BSC frontier

| code | kind | R | p_cap | p@1% | p@10% | gap@1% (bits) | p@1% detected-only | gap det-only | lowest p with an undetected | iters@1% (all / ok) | walk points | undetected/trials |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r0547 | existing | 0.5469 | 0.0951 | 0.0650 | 0.0726 | 0.106 | 0.0650 | 0.106 | — | 28.9 / 28.0 (p=0.065) | 10 | 0/2000 |
| r0550 | existing | 0.5469 | 0.0951 | 0.0450 | 0.0695 | 0.188 | 0.0619 | 0.118 | 0.025 | 11.0 / 11.0 (p=0.045) | 18 | 22/3600 |
| r0625 | existing | 0.6250 | 0.0724 | 0.0500 | 0.0542 | 0.089 | 0.0510 | 0.084 | 0.050 | 29.2 / 28.7 (p=0.05) | 8 | 2/1600 |
| r0700 | existing | 0.7031 | 0.0525 | 0.0360 | 0.0395 | 0.073 | 0.0360 | 0.073 | — | 25.6 / 25.1 (p=0.035) | 7 | 0/1400 |
| r0775 | existing | 0.7812 | 0.0350 | 0.0209 | 0.0241 | 0.072 | 0.0209 | 0.072 | — | 16.2 / 15.6 (p=0.02) | 7 | 0/1400 |
| r0850 | existing | 0.8594 | 0.0199 | 0.0078 | 0.0120 | 0.075 | 0.0078 | 0.075 | — | 15.5 / 12.3 (p=0.01) | 5 | 0/1000 |
| r0250 | candidate | 0.2500 | 0.2145 | 0.1500 | 0.1646 | 0.140 | 0.1500 | 0.140 | 0.160 | 79.2 / 78.8 (p=0.15) | 18 | 5/3600 |
| r0297 | candidate | 0.2969 | 0.1908 | 0.1422 | 0.1490 | 0.113 | 0.1422 | 0.113 | — | 81.9 / 81.7 (p=0.14) | 16 | 0/3200 |
| r0313 | candidate | 0.3125 | 0.1834 | 0.1200 | 0.1398 | 0.158 | 0.1300 | 0.130 | 0.105 | 50.7 / 50.2 (p=0.12) | 20 | 13/4000 |
| r0391 | candidate | 0.3906 | 0.1498 | 0.1075 | 0.1176 | 0.117 | 0.1075 | 0.117 | 0.125 | 62.7 / 61.6 (p=0.11) | 15 | 1/3000 |
| r0406 | candidate | 0.4062 | 0.1437 | 0.1039 | 0.1118 | 0.113 | 0.1039 | 0.113 | — | 61.4 / 60.5 (p=0.105) | 12 | 0/2400 |
| r0469 | candidate | 0.4688 | 0.1207 | 0.0682 | 0.0892 | 0.172 | 0.0775 | 0.138 | 0.030 | 19.2 / 18.2 (p=0.07) | 22 | 22/4400 |
| r0313-h14 | VARIANT | 0.3125 | 0.1834 | 0.1300 | 0.1427 | 0.130 | 0.1300 | 0.130 | — | 72.8 / 72.4 (p=0.13) | 17 | 0/3400 |
| r0313-f50 | VARIANT | 0.3125 | 0.1834 | 0.1350 | 0.1505 | 0.117 | 0.1450 | 0.090 | 0.105 | 62.0 / 61.8 (p=0.135) | 20 | 16/4000 |
| r0391-h14 | VARIANT | 0.3906 | 0.1498 | 0.1072 | 0.1176 | 0.118 | 0.1072 | 0.118 | 0.125 | 49.2 / 48.8 (p=0.105) | 13 | 3/2600 |
| r0391-f50 | VARIANT | 0.3906 | 0.1498 | 0.1150 | 0.1226 | 0.095 | 0.1150 | 0.095 | — | 58.6 / 58.0 (p=0.115) | 11 | 0/2200 |

##### (a) raw grid

| code | p : fails/n (undet) [mean iters] |
|---|---|
| r0547 | 0.055: 0/200 [15]; 0.060: 0/200 [20]; 0.065: 2/200 [29]; 0.070: 8/200 [48]; 0.075: 47/200 [75]; 0.080: 109/200 [103]; 0.085: 170/200 [116]; 0.090: 199/200 [120]; 0.095: 200/200 [120]; 0.100: 200/200 [120] |
| r0550 | 0.015: 0/200 [4]; 0.020: 0/200 [4]; 0.025: 1/200 (1u) [5]; 0.030: 1/200 (1u) [6]; 0.035: 1/200 (1u) [7]; 0.040: 1/200 (1u) [9]; 0.045: 2/200 (2u) [11]; 0.050: 3/200 (3u) [13]; 0.055: 4/200 (4u) [18]; 0.060: 4/200 (3u) [23]; 0.065: 9/200 (3u) [35]; 0.070: 22/200 (2u) [57]; 0.075: 76/200 [85]; 0.080: 132/200 (1u) [110]; 0.085: 189/200 [119]; 0.090: 200/200 [120]; 0.095: 200/200 [120]; 0.100: 200/200 [120] |
| r0625 | 0.040: 0/200 [13]; 0.045: 0/200 [18]; 0.050: 2/200 (1u) [29]; 0.055: 32/200 (1u) [58]; 0.060: 100/200 [95]; 0.065: 172/200 [116]; 0.070: 200/200 [120]; 0.075: 200/200 [120] |
| r0700 | 0.025: 0/200 [10]; 0.030: 0/200 [15]; 0.035: 1/200 [26]; 0.040: 28/200 [59]; 0.045: 114/200 [103]; 0.050: 186/200 [119]; 0.055: 200/200 [120] |
| r0775 | 0.010: 0/200 [5]; 0.015: 0/200 [9]; 0.020: 1/200 [16]; 0.025: 39/200 [53]; 0.030: 155/200 [108]; 0.035: 198/200 [119]; 0.040: 200/200 [120] |
| r0850 | 0.005: 0/200 [5]; 0.010: 6/200 [16]; 0.015: 131/200 [91]; 0.020: 199/200 [120]; 0.025: 200/200 [120] |
| r0250 | 0.135: 0/200 [59]; 0.140: 0/200 [66]; 0.145: 1/200 [74]; 0.150: 2/200 [79]; 0.155: 8/200 [84]; 0.160: 11/200 (1u) [90]; 0.165: 21/200 (1u) [95]; 0.170: 47/200 (1u) [102]; 0.175: 72/200 (1u) [108]; 0.180: 122/200 (1u) [113]; 0.185: 162/200 [117]; 0.190: 188/200 [119]; 0.195: 196/200 [120]; 0.200: 199/200 [120]; 0.205: 200/200 [120]; 0.210: 200/200 [120]; 0.215: 200/200 [120]; 0.220: 200/200 [120] |
| r0297 | 0.120: 0/200 [46]; 0.125: 0/200 [55]; 0.130: 1/200 [63]; 0.135: 1/200 [74]; 0.140: 1/200 [82]; 0.145: 5/200 [90]; 0.150: 28/200 [98]; 0.155: 65/200 [107]; 0.160: 121/200 [114]; 0.165: 165/200 [118]; 0.170: 191/200 [120]; 0.175: 199/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120]; 0.195: 200/200 [120] |
| r0313 | 0.095: 0/200 [17]; 0.100: 0/200 [21]; 0.105: 1/200 (1u) [26]; 0.110: 1/200 (1u) [32]; 0.115: 1/200 (1u) [41]; 0.120: 2/200 (1u) [51]; 0.125: 2/200 (1u) [62]; 0.130: 3/200 (1u) [72]; 0.135: 7/200 (1u) [82]; 0.140: 21/200 (1u) [92]; 0.145: 59/200 (2u) [102]; 0.150: 98/200 (1u) [110]; 0.155: 156/200 (1u) [116]; 0.160: 184/200 (1u) [119]; 0.165: 196/200 [120]; 0.170: 199/200 [120]; 0.175: 200/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120] |
| r0391 | 0.085: 0/200 [19]; 0.090: 0/200 [23]; 0.095: 1/200 [30]; 0.100: 1/200 [37]; 0.105: 1/200 [49]; 0.110: 4/200 [63]; 0.115: 11/200 [80]; 0.120: 35/200 [93]; 0.125: 78/200 (1u) [106]; 0.130: 144/200 [115]; 0.135: 182/200 [119]; 0.140: 198/200 [120]; 0.145: 199/200 [120]; 0.150: 200/200 [120]; 0.155: 200/200 [120] |
| r0406 | 0.095: 0/200 [35]; 0.100: 0/200 [47]; 0.105: 3/200 [61]; 0.110: 12/200 [80]; 0.115: 48/200 [96]; 0.120: 101/200 [108]; 0.125: 158/200 [116]; 0.130: 186/200 [119]; 0.135: 197/200 [120]; 0.140: 200/200 [120]; 0.145: 200/200 [120]; 0.150: 200/200 [120] |
| r0469 | 0.020: 0/200 [4]; 0.025: 0/200 [4]; 0.030: 1/200 (1u) [5]; 0.035: 1/200 (1u) [6]; 0.040: 1/200 (1u) [7]; 0.045: 1/200 (1u) [8]; 0.050: 1/200 (1u) [9]; 0.055: 1/200 (1u) [11]; 0.060: 1/200 (1u) [13]; 0.065: 1/200 (1u) [15]; 0.070: 3/200 (2u) [19]; 0.075: 3/200 (2u) [26]; 0.080: 6/200 (2u) [34]; 0.085: 10/200 (2u) [46]; 0.090: 23/200 (2u) [66]; 0.095: 49/200 (2u) [90]; 0.100: 112/200 (1u) [108]; 0.105: 167/200 (1u) [117]; 0.110: 193/200 [119]; 0.115: 199/200 [120]; 0.120: 200/200 [120]; 0.125: 200/200 [120] |
| r0313-h14 | 0.110: 0/200 [37]; 0.115: 0/200 [46]; 0.120: 1/200 [54]; 0.125: 1/200 [64]; 0.130: 2/200 [73]; 0.135: 8/200 [81]; 0.140: 11/200 [89]; 0.145: 33/200 [97]; 0.150: 62/200 [103]; 0.155: 99/200 [110]; 0.160: 138/200 [115]; 0.165: 173/200 [118]; 0.170: 193/200 [119]; 0.175: 198/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120] |
| r0313-f50 | 0.095: 0/200 [15]; 0.100: 0/200 [18]; 0.105: 1/200 (1u) [22]; 0.110: 1/200 (1u) [25]; 0.115: 1/200 (1u) [33]; 0.120: 1/200 (1u) [39]; 0.125: 1/200 (1u) [45]; 0.130: 1/200 (1u) [52]; 0.135: 2/200 (2u) [62]; 0.140: 3/200 (2u) [71]; 0.145: 4/200 (2u) [81]; 0.150: 18/200 (2u) [91]; 0.155: 50/200 (2u) [103]; 0.160: 119/200 [112]; 0.165: 160/200 [117]; 0.170: 194/200 [120]; 0.175: 197/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120] |
| r0391-h14 | 0.095: 0/200 [31]; 0.100: 0/200 [38]; 0.105: 1/200 [49]; 0.110: 5/200 [64]; 0.115: 14/200 [79]; 0.120: 28/200 [93]; 0.125: 69/200 (1u) [104]; 0.130: 121/200 (1u) [112]; 0.135: 172/200 (1u) [118]; 0.140: 196/200 [120]; 0.145: 199/200 [120]; 0.150: 200/200 [120]; 0.155: 200/200 [120] |
| r0391-f50 | 0.105: 0/200 [35]; 0.110: 0/200 [45]; 0.115: 2/200 [59]; 0.120: 10/200 [78]; 0.125: 37/200 [95]; 0.130: 100/200 [109]; 0.135: 170/200 [117]; 0.140: 194/200 [120]; 0.145: 198/200 [120]; 0.150: 200/200 [120]; 0.155: 200/200 [120] |

#### (b) BIAWGN frontier

| code | kind | R | Es/N0 Shannon (dB) | Es/N0@1% (dB) | gap (dB) | Es/N0@1% detected-only | gap det-only (dB) | Es/N0@10% | Eb/N0@1% (dB) | walk points | undetected/trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| r0547 | existing | 0.5469 | -2.214 | -1.083 | 1.13 | -1.083 | 1.13 | -1.400 | 1.538 | 9 | 0/1800 |
| r0550 | existing | 0.5469 | -2.214 | -1.000 | 1.21 | -1.120 | 1.09 | -1.335 | 1.621 | 10 | 8/2000 |
| r0625 | existing | 0.6250 | -1.226 | -0.362 | 0.86 | -0.362 | 0.86 | -0.571 | 1.679 | 7 | 0/1400 |
| r0700 | existing | 0.7031 | -0.237 | 0.611 | 0.85 | 0.611 | 0.85 | 0.369 | 2.140 | 7 | 0/1400 |
| r0775 | existing | 0.7812 | 0.804 | 1.750 | 0.95 | 1.750 | 0.95 | 1.412 | 2.822 | 8 | 0/1600 |
| r0850 | existing | 0.8594 | 1.993 | 2.875 | 0.88 | 2.875 | 0.88 | 2.593 | 3.533 | 8 | 0/1600 |
| r0250 | candidate | 0.2500 | -6.815 | -3.750 | 3.06 | -3.750 | 3.06 | -5.102 | 2.271 | 16 | 0/3200 |
| r0297 | candidate | 0.2969 | -5.903 | -4.000 | 1.90 | -4.000 | 1.90 | -4.479 | 1.274 | 12 | 0/2400 |
| r0313 | candidate | 0.3125 | -5.624 | -3.858 | 1.77 | -3.875 | 1.75 | -4.201 | 1.194 | 15 | 3/3000 |
| r0391 | candidate | 0.3906 | -4.358 | -3.108 | 1.25 | -3.167 | 1.19 | -3.384 | 0.975 | 12 | 5/2400 |
| r0406 | candidate | 0.4062 | -4.125 | -2.825 | 1.30 | -2.825 | 1.30 | -3.108 | 1.087 | 10 | 0/2000 |
| r0469 | candidate | 0.4688 | -3.242 | -2.000 | 1.24 | -2.000 | 1.24 | -2.318 | 1.291 | 11 | 0/2200 |
| r0313-h14 | VARIANT | 0.3125 | -5.624 | -3.750 | 1.87 | -3.750 | 1.87 | -4.333 | 1.301 | 11 | 0/2200 |
| r0313-f50 | VARIANT | 0.3125 | -5.624 | -4.250 | 1.37 | -4.250 | 1.37 | -4.460 | 0.801 | 10 | 2/2000 |
| r0391-h14 | VARIANT | 0.3906 | -4.358 | -2.750 | 1.61 | -2.750 | 1.61 | -3.376 | 1.332 | 12 | 0/2400 |
| r0391-f50 | VARIANT | 0.3906 | -4.358 | -3.131 | 1.23 | -3.131 | 1.23 | -3.369 | 0.951 | 8 | 0/1600 |

##### (b) raw grid

| code | Es/N0 dB : fails/n (undet) [mean iters] |
|---|---|
| r0547 | -2.50: 200/200 [120]; -2.25: 200/200 [120]; -2.00: 193/200 [119]; -1.75: 127/200 [109]; -1.50: 37/200 [70]; -1.25: 8/200 [38]; -1.00: 1/200 [22]; -0.75: 0/200 [16]; -0.50: 0/200 [12] |
| r0550 | -2.50: 200/200 [120]; -2.25: 200/200 [120]; -2.00: 198/200 [120]; -1.75: 147/200 [113]; -1.50: 54/200 (2u) [81]; -1.25: 12/200 (3u) [42]; -1.00: 2/200 (2u) [23]; -0.75: 1/200 (1u) [16]; -0.50: 0/200 [13]; -0.25: 0/200 [10] |
| r0625 | -1.50: 200/200 [120]; -1.25: 199/200 [120]; -1.00: 184/200 [118]; -0.75: 90/200 [99]; -0.50: 11/200 [50]; -0.25: 0/200 [22]; 0.00: 0/200 [14] |
| r0700 | -0.50: 200/200 [120]; -0.25: 200/200 [120]; 0.00: 175/200 [117]; 0.25: 60/200 [88]; 0.50: 6/200 [40]; 0.75: 0/200 [16]; 1.00: 0/200 [11] |
| r0775 | 0.50: 200/200 [120]; 0.75: 198/200 [119]; 1.00: 179/200 [116]; 1.25: 71/200 [77]; 1.50: 10/200 [30]; 1.75: 2/200 [13]; 2.00: 0/200 [9]; 2.25: 0/200 [7] |
| r0850 | 1.75: 200/200 [120]; 2.00: 198/200 [120]; 2.25: 154/200 [101]; 2.50: 52/200 [53]; 2.75: 4/200 [17]; 3.00: 1/200 [8]; 3.25: 0/200 [6]; 3.50: 0/200 [5] |
| r0250 | -7.00: 200/200 [120]; -6.75: 200/200 [120]; -6.50: 200/200 [120]; -6.25: 200/200 [120]; -6.00: 183/200 [119]; -5.75: 146/200 [116]; -5.50: 80/200 [109]; -5.25: 42/200 [101]; -5.00: 12/200 [92]; -4.75: 5/200 [84]; -4.50: 3/200 [75]; -4.25: 2/200 [66]; -4.00: 2/200 [52]; -3.75: 2/200 [40]; -3.50: 0/200 [30]; -3.25: 0/200 [22] |
| r0297 | -6.25: 200/200 [120]; -6.00: 200/200 [120]; -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 195/200 [120]; -5.00: 154/200 [117]; -4.75: 70/200 [107]; -4.50: 22/200 [95]; -4.25: 7/200 [83]; -4.00: 2/200 [71]; -3.75: 0/200 [57]; -3.50: 0/200 [42] |
| r0313 | -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 199/200 [120]; -5.00: 191/200 [120]; -4.75: 162/200 [117]; -4.50: 82/200 (1u) [109]; -4.25: 28/200 (1u) [96]; -4.00: 5/200 (1u) [81]; -3.75: 1/200 [64]; -3.50: 1/200 [51]; -3.25: 1/200 [37]; -3.00: 0/200 [27]; -2.75: 1/200 [19]; -2.50: 0/200 [15]; -2.25: 0/200 [13] |
| r0391 | -4.50: 200/200 [120]; -4.25: 200/200 [120]; -4.00: 195/200 [120]; -3.75: 151/200 [116]; -3.50: 67/200 [102]; -3.25: 5/200 (1u) [76]; -3.00: 1/200 (1u) [52]; -2.75: 1/200 (1u) [36]; -2.50: 1/200 (1u) [25]; -2.25: 1/200 (1u) [19]; -2.00: 0/200 [15]; -1.75: 0/200 [12] |
| r0406 | -4.50: 200/200 [120]; -4.25: 200/200 [120]; -4.00: 199/200 [120]; -3.75: 192/200 [119]; -3.50: 140/200 [115]; -3.25: 50/200 [97]; -3.00: 10/200 [69]; -2.75: 1/200 [45]; -2.50: 0/200 [30]; -2.25: 0/200 [21] |
| r0469 | -3.50: 200/200 [120]; -3.25: 200/200 [120]; -3.00: 198/200 [120]; -2.75: 162/200 [116]; -2.50: 63/200 [97]; -2.25: 13/200 [61]; -2.00: 2/200 [36]; -1.75: 1/200 [24]; -1.50: 1/200 [18]; -1.25: 0/200 [14]; -1.00: 0/200 [11] |
| r0313-h14 | -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 197/200 [120]; -5.00: 158/200 [117]; -4.75: 103/200 [111]; -4.50: 41/200 [101]; -4.25: 14/200 [90]; -4.00: 2/200 [78]; -3.75: 2/200 [63]; -3.50: 0/200 [48]; -3.25: 0/200 [35] |
| r0313-f50 | -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 196/200 [120]; -5.00: 169/200 (1u) [118]; -4.75: 103/200 (1u) [109]; -4.50: 31/200 [95]; -4.25: 2/200 [77]; -4.00: 1/200 [61]; -3.75: 0/200 [46]; -3.50: 0/200 [34] |
| r0391-h14 | -4.50: 200/200 [120]; -4.25: 200/200 [120]; -4.00: 191/200 [120]; -3.75: 131/200 [115]; -3.50: 44/200 [101]; -3.25: 9/200 [79]; -3.00: 3/200 [54]; -2.75: 2/200 [37]; -2.50: 1/200 [26]; -2.25: 1/200 [20]; -2.00: 0/200 [16]; -1.75: 0/200 [13] |
| r0391-f50 | -4.50: 200/200 [120]; -4.25: 200/200 [120]; -4.00: 193/200 [120]; -3.75: 145/200 [114]; -3.50: 64/200 [98]; -3.25: 7/200 [69]; -3.00: 0/200 [39]; -2.75: 0/200 [25] |

#### (c) Erasure + error (fragment regime), fails/n

| code | R | p | ε=0.2 | ε=0.3 | ε=0.4 | ε=0.5 | ε=0.6 | ε=0.7 | max ε @ BLER≤1% | (1−ε)(1−h2(p)) − R at that ε |
|---|---|---|---|---|---|---|---|---|---|---|
| r0547 | 0.547 | 0.01 | 0/200 | 0/200 | 200/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.097 |
| r0547 | 0.547 | 0.02 | 0/200 | 35/200 | 200/200 | 200/200 | 200/200 | 200/200 | 0.2 | 0.140 |
| r0547 | 0.547 | 0.05 | 184/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0550 | 0.547 | 0.01 | 0/200 | 0/200 | 200/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.097 |
| r0550 | 0.547 | 0.02 | 0/200 | 50/200 | 200/200 | 200/200 | 200/200 | 200/200 | 0.2 | 0.140 |
| r0550 | 0.547 | 0.05 | 193/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0625 | 0.625 | 0.01 | 0/200 | 189/200 | 200/200 | 200/200 | 200/200 | 200/200 | 0.2 | 0.110 |
| r0625 | 0.625 | 0.02 | 12/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0625 | 0.625 | 0.05 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0700 | 0.703 | 0.01 | 102/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0700 | 0.703 | 0.02 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0700 | 0.703 | 0.05 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0775 | 0.781 | 0.01 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0775 | 0.781 | 0.02 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0775 | 0.781 | 0.05 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0850 | 0.859 | 0.01 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0850 | 0.859 | 0.02 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0850 | 0.859 | 0.05 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0250 | 0.250 | 0.01 | 0/200 | 0/200 | 0/200 | 0/200 | 2/200 | 197/200 | 0.6 | 0.118 |
| r0250 | 0.250 | 0.02 | 0/200 | 0/200 | 0/200 | 0/200 | 6/200 | 200/200 | 0.5 | 0.179 |
| r0250 | 0.250 | 0.05 | 0/200 | 0/200 | 0/200 | 3/200 | 184/200 (1u) | 200/200 | 0.4 | 0.178 |
| r0297 | 0.297 | 0.01 | 0/200 | 0/200 | 0/200 | 0/200 | 18/200 | 200/200 | 0.5 | 0.163 |
| r0297 | 0.297 | 0.02 | 0/200 | 0/200 | 0/200 | 0/200 | 161/200 | 200/200 | 0.5 | 0.132 |
| r0297 | 0.297 | 0.05 | 0/200 | 0/200 | 0/200 | 108/200 | 200/200 | 200/200 | 0.4 | 0.131 |
| r0313 | 0.312 | 0.01 | 0/200 | 0/200 | 0/200 | 0/200 | 111/200 | 200/200 | 0.5 | 0.147 |
| r0313 | 0.312 | 0.02 | 0/200 | 0/200 | 0/200 | 0/200 | 198/200 | 200/200 | 0.5 | 0.117 |
| r0313 | 0.312 | 0.05 | 0/200 | 0/200 | 1/200 (1u) | 184/200 | 200/200 | 200/200 | 0.4 | 0.116 |
| r0391 | 0.391 | 0.01 | 0/200 | 0/200 | 0/200 | 17/200 (1u) | 200/200 | 200/200 | 0.4 | 0.161 |
| r0391 | 0.391 | 0.02 | 0/200 | 0/200 | 0/200 | 162/200 | 200/200 | 200/200 | 0.4 | 0.125 |
| r0391 | 0.391 | 0.05 | 0/200 | 0/200 | 172/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.109 |
| r0406 | 0.406 | 0.01 | 0/200 | 0/200 | 0/200 | 47/200 | 200/200 | 200/200 | 0.4 | 0.145 |
| r0406 | 0.406 | 0.02 | 0/200 | 0/200 | 0/200 | 197/200 | 200/200 | 200/200 | 0.4 | 0.109 |
| r0406 | 0.406 | 0.05 | 0/200 | 1/200 | 190/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.093 |
| r0469 | 0.469 | 0.01 | 0/200 | 0/200 | 1/200 | 200/200 | 200/200 | 200/200 | 0.4 | 0.083 |
| r0469 | 0.469 | 0.02 | 0/200 | 0/200 | 102/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.132 |
| r0469 | 0.469 | 0.05 | 3/200 | 183/200 | 200/200 | 200/200 | 200/200 | 200/200 | — | — |
| r0313-h14 | 0.312 | 0.01 | 0/200 | 0/200 | 0/200 | 1/200 | 36/200 | 200/200 | 0.5 | 0.147 |
| r0313-h14 | 0.312 | 0.02 | 0/200 | 0/200 | 0/200 | 3/200 | 169/200 | 200/200 | 0.4 | 0.203 |
| r0313-h14 | 0.312 | 0.05 | 0/200 | 0/200 | 4/200 | 128/200 | 200/200 | 200/200 | 0.3 | 0.187 |
| r0313-f50 | 0.312 | 0.01 | 0/200 | 0/200 | 0/200 | 0/200 | 119/200 | 200/200 | 0.5 | 0.147 |
| r0313-f50 | 0.312 | 0.02 | 0/200 | 0/200 | 0/200 | 0/200 | 200/200 | 200/200 | 0.5 | 0.117 |
| r0313-f50 | 0.312 | 0.05 | 0/200 | 0/200 | 1/200 (1u) | 155/200 | 200/200 | 200/200 | 0.4 | 0.116 |
| r0391-h14 | 0.391 | 0.01 | 0/200 | 0/200 | 0/200 | 9/200 (1u) | 200/200 | 200/200 | 0.4 | 0.161 |
| r0391-h14 | 0.391 | 0.02 | 0/200 | 0/200 | 0/200 | 134/200 | 200/200 | 200/200 | 0.4 | 0.125 |
| r0391-h14 | 0.391 | 0.05 | 0/200 | 1/200 | 146/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.109 |
| r0391-f50 | 0.391 | 0.01 | 0/200 | 0/200 | 0/200 | 31/200 | 200/200 | 200/200 | 0.4 | 0.161 |
| r0391-f50 | 0.391 | 0.02 | 0/200 | 0/200 | 0/200 | 180/200 | 200/200 | 200/200 | 0.4 | 0.125 |
| r0391-f50 | 0.391 | 0.05 | 0/200 | 1/200 | 177/200 | 200/200 | 200/200 | 200/200 | 0.3 | 0.109 |

#### (d) Shorten vs puncture at the 120-site accommodation

| code | k | variant | transmitted bits | user bits/tile | BLER at p (fails/n) … |
|---|---|---|---|---|---|
| r0547 | 2240 | mother | 4096 | 2208 | p=0.060: 0/200 [21 it]; p=0.065: 5/200 [30 it]; p=0.070: 10/200 [50 it] |
| r0547 | 2240 | shorten | 3976 | 2088 | p=0.060: 0/200 [18 it]; p=0.065: 2/200 [25 it]; p=0.070: 6/200 [37 it] |
| r0547 | 2240 | punct_last | 3976 | 2208 | p=0.060: 200/200 [120 it]; p=0.065: 200/200 [120 it]; p=0.070: 200/200 [120 it] |
| r0547 | 2240 | punct_even | 3976 | 2208 | p=0.060: 5/200 [33 it]; p=0.065: 14/200 [51 it]; p=0.070: 57/200 [84 it] |
| r0313 | 1280 | mother | 4096 | 1248 | p=0.120: 0/200 [54 it]; p=0.125: 1/200 [63 it]; p=0.130: 1/200 [73 it] |
| r0313 | 1280 | shorten | 3976 | 1128 | p=0.120: 0/200 [42 it]; p=0.125: 0/200 [50 it]; p=0.130: 0/200 [60 it] |
| r0313 | 1280 | punct_last | 3976 | 1248 | p=0.120: 200/200 [120 it]; p=0.125: 200/200 [120 it]; p=0.130: 200/200 [120 it] |
| r0313 | 1280 | punct_even | 3976 | 1248 | p=0.120: 3/200 [63 it]; p=0.125: 3/200 [73 it]; p=0.130: 6/200 [82 it] |
| r0391 | 1600 | mother | 4096 | 1568 | p=0.100: 0/200 [36 it]; p=0.105: 1/200 [47 it]; p=0.110: 4/200 [61 it] |
| r0391 | 1600 | shorten | 3976 | 1448 | p=0.100: 0/200 [30 it]; p=0.105: 0/200 [38 it]; p=0.110: 0/200 [48 it] |
| r0391 | 1600 | punct_last | 3976 | 1568 | p=0.100: 200/200 [120 it]; p=0.105: 200/200 [120 it]; p=0.110: 200/200 [120 it] |
| r0391 | 1600 | punct_even | 3976 | 1568 | p=0.100: 0/200 [49 it]; p=0.105: 3/200 [61 it]; p=0.110: 11/200 [77 it] |

#### (e) Recorded-battery cross-check

| code | p | recorded (FEC-DESIGN / test gate) | replicate mag 4.0, test seeds: fails/n (undet) | this sweep's log-LLR grid at same p |
|---|---|---|---|---|
| r0547 | 0.055 | (not recorded; r0550 twin) | 0/200 (0u) | 0/200 |
| r0550 | 0.055 | clean (0/100 gate ≤1) | 0/200 (0u) | 4/200 |
| r0625 | 0.045 | 0.5% (gate ≤2/100) | 0/200 (0u) | 0/200 |
| r0700 | 0.015 | 0/200 | 0/200 (0u) | (not on grid) |
| r0700 | 0.035 | 1.5–1.8% (gate ≤3/200) | 2/200 (0u) | 1/200 |
| r0775 | 0.02 | 0.5% (gate ≤2/100) | 0/200 (0u) | 1/200 |
| r0850 | 0.005 | (gate ≤1/100) | 0/200 (0u) | 0/200 |
| r0850 | 0.01 | 3.5% | 5/200 (0u) | 6/200 |

#### Undetected (syndrome-valid wrong) decodes

| code | channel | undetected | of trials | at points |
|---|---|---|---|---|
| r0550 | bsc | 22 | 3600 | {'p': 0.08}: 1/200; {'p': 0.07}: 2/200; {'p': 0.065}: 3/200; {'p': 0.06}: 3/200; {'p': 0.055}: 4/200; {'p': 0.05}: 3/200; {'p': 0.045}: 2/200; {'p': 0.04}: 1/200; {'p': 0.035}: 1/200; {'p': 0.03}: 1/200; {'p': 0.025}: 1/200 |
| r0550 | awgn | 8 | 2000 | {'esn0_db': -1.5, 'sigma': 0.8403979844760322}: 2/200; {'esn0_db': -1.25, 'sigma': 0.8165541721659758}: 3/200; {'esn0_db': -1.0, 'sigma': 0.7933868576533668}: 2/200; {'esn0_db': -0.75, 'sigma': 0.7708768473099378}: 1/200 |
| r0625 | bsc | 2 | 1600 | {'p': 0.055}: 1/200; {'p': 0.05}: 1/200 |
| r0250 | bsc | 5 | 3600 | {'p': 0.18}: 1/200; {'p': 0.175}: 1/200; {'p': 0.17}: 1/200; {'p': 0.165}: 1/200; {'p': 0.16}: 1/200 |
| r0250 | eras | 1 | 3600 | {'eps': 0.6, 'p': 0.05}: 1/200 |
| r0313 | bsc | 13 | 4000 | {'p': 0.16}: 1/200; {'p': 0.155}: 1/200; {'p': 0.15}: 1/200; {'p': 0.145}: 2/200; {'p': 0.14}: 1/200; {'p': 0.135}: 1/200; {'p': 0.13}: 1/200; {'p': 0.125}: 1/200; {'p': 0.12}: 1/200; {'p': 0.115}: 1/200; {'p': 0.11}: 1/200; {'p': 0.105}: 1/200 |
| r0313 | awgn | 3 | 3000 | {'esn0_db': -4.5, 'sigma': 1.187093705497686}: 1/200; {'esn0_db': -4.25, 'sigma': 1.1534134254027932}: 1/200; {'esn0_db': -4.0, 'sigma': 1.1206887238456493}: 1/200 |
| r0313 | eras | 1 | 3600 | {'eps': 0.4, 'p': 0.05}: 1/200 |
| r0391 | bsc | 1 | 3000 | {'p': 0.125}: 1/200 |
| r0391 | awgn | 5 | 2400 | {'esn0_db': -3.25, 'sigma': 1.0279807974462964}: 1/200; {'esn0_db': -3.0, 'sigma': 0.9988148764833451}: 1/200; {'esn0_db': -2.75, 'sigma': 0.9704764524422529}: 1/200; {'esn0_db': -2.5, 'sigma': 0.942942047540283}: 1/200; {'esn0_db': -2.25, 'sigma': 0.9161888501074875}: 1/200 |
| r0391 | eras | 1 | 3600 | {'eps': 0.5, 'p': 0.01}: 1/200 |
| r0469 | bsc | 22 | 4400 | {'p': 0.105}: 1/200; {'p': 0.1}: 1/200; {'p': 0.095}: 2/200; {'p': 0.09}: 2/200; {'p': 0.085}: 2/200; {'p': 0.08}: 2/200; {'p': 0.075}: 2/200; {'p': 0.07}: 2/200; {'p': 0.065}: 1/200; {'p': 0.06}: 1/200; {'p': 0.055}: 1/200; {'p': 0.05}: 1/200; {'p': 0.045}: 1/200; {'p': 0.04}: 1/200; {'p': 0.035}: 1/200; {'p': 0.03}: 1/200 |
| r0313-f50 | bsc | 16 | 4000 | {'p': 0.155}: 2/200; {'p': 0.15}: 2/200; {'p': 0.145}: 2/200; {'p': 0.14}: 2/200; {'p': 0.135}: 2/200; {'p': 0.13}: 1/200; {'p': 0.125}: 1/200; {'p': 0.12}: 1/200; {'p': 0.115}: 1/200; {'p': 0.11}: 1/200; {'p': 0.105}: 1/200 |
| r0313-f50 | awgn | 2 | 2000 | {'esn0_db': -5.0, 'sigma': 1.2574334296829353}: 1/200; {'esn0_db': -4.75, 'sigma': 1.2217574675274057}: 1/200 |
| r0313-f50 | eras | 1 | 3600 | {'eps': 0.4, 'p': 0.05}: 1/200 |
| r0391-h14 | bsc | 3 | 2600 | {'p': 0.135}: 1/200; {'p': 0.13}: 1/200; {'p': 0.125}: 1/200 |
| r0391-h14 | eras | 1 | 3600 | {'eps': 0.5, 'p': 0.01}: 1/200 |

##### Undetected diagnostic (one fixed seed per code hits one low-weight word; common random numbers make it persist down the walk)

```
r0550 p=0.03 trial 154: wrong codeword at distance 6 (info part 2, parity 4), channel errors 130, errors on the diff support 3/6, info diff idx [1157, 1363], iters 10
r0469 p=0.03 trial 8: wrong codeword at distance 16 (info part 3, parity 13), channel errors 123, errors on the diff support 8/16, info diff idx [760, 1289, 1305], iters 75
r0313 p=0.105 trial 177: wrong codeword at distance 12 (info part 2, parity 10), channel errors 452, errors on the diff support 7/12, info diff idx [856, 1137], iters 32
r0313-f50 p=0.105 trial 128: wrong codeword at distance 16 (info part 2, parity 14), channel errors 445, errors on the diff support 8/16, info diff idx [727, 896], iters 83
r0391 p=0.125 trial 4: wrong codeword at distance 11 (info part 2, parity 9), channel errors 522, errors on the diff support 6/11, info diff idx [1346, 1576], iters 120
r0250 p=0.16 trial 23: wrong codeword at distance 39 (info part 6, parity 33), channel errors 651, errors on the diff support 21/39, info diff idx [412, 570, 607, 667, 897, 1019], iters 108
```

#### Run record

Run 1 (same command) was ABORTED at ~13 min: an unrounded float key in `Walk.__init__` re-submitted r0625's hard BSC point on every completion (identical seeds, identical counts, never-terminating loop); fixed in harness/sweep.py line 51, run 2 is the one reported here (logs: run1_aborted.log, sweep_progress_run1_aborted.log). Build: harness/build.py (0.4 s, all ten at restart 0). Structure: harness/structure.py (2.4 s). Smoke: `sweep.py --smoke --workers 8` (9 s, results_smoke.json).

---

# Appendix B — TABLES-c1.md (the sub-r0300 / c1 extension), carried verbatim

Source: `scratch/rung-ladder-20260930/TABLES-c1.md`. Verbatim; heading levels shifted by two so they nest here. Its paths (`c1/…`, `../harness/…`) are relative to that gitignored directory. Caveats as for Appendix A; in addition, every SOFT column assumes the equal-variance two-Gaussian cell channel, and no c1 soft/context/multi-capture measurement exists.

### Rung-ladder measurement, c1 extension (sub-r0300) — rung-ladder-20260930

#### Headline

HARD: no k/profile closes any recorded whole-sheet c1 channel (Canon 21.3 %, VersaLink grey 21.5 % / RGB 22.0 %) at 1 % BLER. The best hard threshold is 0.189 (k=832, HEAVY_FRAC 0.7; 0.185 at 0.5; 0.190 for both at 200 iterations), which reaches only the Canon per-tile p5 (18.4 %). That is about 7–17 % of Canon tiles (interpolated), at 0.684 net bits per c2 area = 0.83× c2-r0850. Scaling the measured p@1 %/p_cap ratios (0.60–0.79) to p = 0.213–0.22 gives hard R ≤ ~0.15 (≈0.46–0.51 bits per c2 area, 0.55–0.61× c2-r0850). The orchestrator's "R ≤ ~0.19" is optimistic. SOFT (the equal-variance two-Gaussian model, p = Q(√(2·Es/N0)); unmeasured at c1): k = 832–960 close all three whole-sheet channels (best 0.239, r0203-f70), but every code that closes them costs ≤ 0.98× c2-r0850 per area. The codes that beat c2-r0850 per area (k ≥ 1024: 1.05× at k=1024, 1.20× at 1152, 1.36× at 1280) close ≤ 0.213 soft at production iterations: r0250-f50 reaches exactly Canon 21.3 %; at 200 iterations it reaches 0.220 = VersaLink RGB, the only ≥ 1.05× code at any whole-sheet channel. k = 1152–1280 reach only the Canon median/p5 tiles. So with the 132-bit overhead and today's recipe, c1 at 21 % is break-even with c2-r0850 at best, and only if the soft Gaussian model holds. It is a 1.0–1.2× gain over c2-r0700. The capacity ceiling at p = 0.21 is 1.43 bits per c2 area soft (1.73×); a code within 1.5 dB would give R 0.27 = 0.96 bits (1.16×). RECIPE BELOW R = 0.3: the frozen recipe's BIAWGN gap at 1 % grows as R falls: 1.94 dB at R 0.281, 2.15–2.17 at 0.219–0.234, 2.72 at 0.203, and r0250 3.06 (floor-driven). Its p@1 %/p_cap ratio drops to 0.60–0.72. Raising HEAVY_FRAC to 0.5–0.7 recovers 0.3–0.9 dB (gaps 1.59–2.06 dB, ratio 0.77–0.79, zero undetected in every variant run). Allowing 200 iterations instead of 60 recovers another 0.1–0.75 dB (variants 1.50–1.81 dB). The near-1 % failures are a few persistent trials with 1–34 wrong bits, most of which clear with more iterations (floor_diag). No construction here gets within ~1.5 dB of Shannon below R = 0.3. The structural cause is the e-IRA accumulator: 75–80 % of variables have degree 2, and check degrees are 3.3–4.6.

#### Run record

- Sweep: `cd <repo> && PYTHONPATH=src:. env/bin/python scratch/rung-ladder-20260930/c1/sweep_c1.py --workers 14` — 200 trials/point (chunks of 50), 14 workers, wall 188 s.
- Build: `cd <repo> && PYTHONPATH=src:. env/bin/python scratch/rung-ladder-20260930/c1/build_c1.py` (0.2 s; frozen recipe via ../harness/build.py build_one, seed label `ldpc-v1/<rid>`; restarts: r0203 2, r0219 0, r0234 0, r0281 0, r0203-f50 0, r0234-f50 0, r0250-f50 1, r0281-f50 0, r0203-f70 0, r0250-f70 0).
- Structure: `... c1/structure_c1.py` (0.7 s, ../harness/structure.py stats unchanged). Tables: `... c1/tables_c1.py`. Smoke: `c1/sweep_c1.py --smoke --workers 8` (10 s, results-c1-smoke.json).
- Seeds: trial t uses `np.random.default_rng(base + t)`, base = {'bsc': 100000, 'awgn': 200000, 'eras': 300000, 'accom': 400000, 'record': 0} (the previous run's; common random numbers across codes). Decoder: `holo.core.ldpc.decode.decode` (production, min-sum α=0.8, 60 iters + one sum-product retry). Hard LLR ±log((1−p)/p); BIAWGN LLR −2y/σ², x = 1−2c, Es/N0 = 1/(2σ²).
- Walks as the previous run: (a) 0.005 p grid from the BSC-capacity point, (b) 0.25 dB grid from the Shannon point; easy side until two consecutive 0/200, hard side until BLER ≥ 0.5; p@1% by linear interpolation in log BLER (0/n floored at 0.5/n). (c) fixed grid ε ∈ {0.3, 0.5, 0.7} × p ∈ {0.02, 0.05}.
- Supplement: `... c1/iters_c1.py` (max_iters=200 on every live (a)/(b) walk point of the ten new codes + r0250, same seeds, 14 workers, wall 185 s -> iters-c1.json); `... c1/floor_diag.py` (failing trial ids at ten near-1 % points, re-decoded at 200/500 iters, 6 s -> floor_diag.json). Total wall of this extension ~6.5 min of compute.
- Continuity rows r0250, r0313, r0313-f50 (and r0297, r0391-f50 in the c1-vs-c2 table) are the previous run's results.json entries, NOT re-run.
- SOFT conversion: an Es/N0@1% threshold on BIAWGN is mapped to the raw hard error of the same channel, p = Q(√(2·Es/N0)) = Q(1/σ). This assumes the cell channel is two equal-variance Gaussians (symmetric); the recorded c1 channels have unequal means and unmeasured variances, and NO c1 soft/context/multi-capture measurement exists.
- Net bits: K family p100, (k − 100 sites − 32 CRC)/4096 per c1 cell, ×4 per c2 cell area; c2-r0850 = 3388/4096 = 0.827, c2-r0700 = 2748/4096 = 0.671 per c2 cell.

#### c1 vs c2 (the deliverable)

| code | kind | k | R | p@1% HARD (a) | p@1% SOFT = Q(√(2·Es/N0@1%)) (b) | net bits / c1 cell (k−132)/4096 | per c2 area (×4) | ÷ c2-r0850 (0.827) | ÷ c2-r0700 (0.671) | VersaLink E RGB 22.0% | VersaLink E grey 21.5% | Canon E whole 21.3% | Canon per-tile p5 18.4% | Canon per-tile median 20.2% | Canon per-tile p95 26.4% | Canon tiles closable hard / soft (interp.) | p@1% hard / soft at 200 it (supplement) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r0203 | recipe (new) | 832 | 0.2031 | 0.1450 | 0.2174 | 0.1709 | 0.684 | 0.83 | 1.02 | no | soft only | soft only | soft only | soft only | no | 0.0% / 61.2% | 0.1700 / 0.2264 |
| r0203-f50 | VARIANT (new) | 832 | 0.2031 | 0.1850 | 0.2353 | 0.1709 | 0.684 | 0.83 | 1.02 | soft only | soft only | soft only | hard+soft | soft only | no | 7.5% / 74.2% | 0.1900 / 0.2425 |
| r0203-f70 | VARIANT (new) | 832 | 0.2031 | 0.1889 | 0.2392 | 0.1709 | 0.684 | 0.83 | 1.02 | soft only | soft only | soft only | hard+soft | soft only | no | 17.2% / 77.0% | 0.1900 / 0.2408 |
| r0219 | recipe (new) | 896 | 0.2188 | 0.1650 | 0.2220 | 0.1865 | 0.746 | 0.90 | 1.11 | soft only | soft only | soft only | soft only | soft only | no | 0.0% / 64.5% | 0.1769 / 0.2307 |
| r0234 | recipe (new) | 960 | 0.2344 | 0.1600 | 0.2132 | 0.2021 | 0.809 | 0.98 | 1.21 | no | no | soft only | soft only | soft only | no | 0.0% / 58.1% | 0.1675 / 0.2174 |
| r0234-f50 | VARIANT (new) | 960 | 0.2344 | 0.1769 | 0.2264 | 0.2021 | 0.809 | 0.98 | 1.21 | soft only | soft only | soft only | soft only | soft only | no | 1.8% / 67.7% | 0.1816 / 0.2287 |
| r0250 | recipe (prev run) | 1024 | 0.2500 | 0.1500 | 0.1792 | 0.2178 | 0.871 | 1.05 | 1.30 | no | no | no | no | no | no | 0.0% / 2.8% | 0.1533 / 0.1998 |
| r0250-f50 | VARIANT (new) | 1024 | 0.2500 | 0.1668 | 0.2132 | 0.2178 | 0.871 | 1.05 | 1.30 | no | no | soft only | soft only | soft only | no | 0.0% / 58.1% | 0.1718 / 0.2198 |
| r0250-f70 | VARIANT (new) | 1024 | 0.2500 | 0.1672 | 0.2065 | 0.2178 | 0.871 | 1.05 | 1.30 | no | no | no | soft only | soft only | no | 0.0% / 53.3% | 0.1678 / 0.2150 |
| r0281 | recipe (new) | 1152 | 0.2812 | 0.1400 | 0.1930 | 0.2490 | 0.996 | 1.20 | 1.48 | no | no | no | soft only | no | no | 0.0% / 27.4% | 0.1450 / 0.1973 |
| r0281-f50 | VARIANT (new) | 1152 | 0.2812 | 0.1566 | 0.2027 | 0.2490 | 0.996 | 1.20 | 1.48 | no | no | no | soft only | soft only | no | 0.0% / 50.5% | 0.1580 / 0.2050 |
| r0313 | recipe (prev run) | 1280 | 0.3125 | 0.1200 | 0.1822 | 0.2803 | 1.121 | 1.36 | 1.67 | no | no | no | no | no | no | 0.0% / 4.2% | — / — |
| r0313-f50 | VARIANT (prev run) | 1280 | 0.3125 | 0.1350 | 0.1930 | 0.2803 | 1.121 | 1.36 | 1.67 | no | no | no | soft only | no | no | 0.0% / 27.4% | — / — |
| r0297 | recipe (prev run) | 1216 | 0.2969 | 0.1422 | 0.1861 | 0.2646 | 1.059 | 1.28 | 1.58 | no | no | no | soft only | no | no | 0.0% / 10.3% | — / — |
| r0391-f50 | VARIANT (prev run) | 1600 | 0.3906 | 0.1150 | 0.1620 | 0.3584 | 1.434 | 1.73 | 2.14 | no | no | no | no | no | no | 0.0% / 0.0% | — / — |

Marks: `hard+soft` = p@1% HARD ≥ the channel's raw error; `soft only` = only the Gaussian-soft threshold reaches it; `no` = neither. Canon tile fractions: piecewise-linear CDF through e040's per-tile quantiles (min 17.3, p5 18.4, median 20.2, p95 26.4, max 35.3 %) evaluated at the code's p@1% — an interpolation, not a count.

#### Supplement: decoder iterations (max_iters 200 vs production 60, same seeds; NOT the production setting)

| code | p@1% hard, 60 it → 200 it | p@10% hard 60 → 200 | Es/N0@1% 60 → 200 (dB) | gap dB 60 → 200 | p@1% soft 60 → 200 | Es/N0@10% 60 → 200 | mean iters at the 200-it p@1% point | undetected (200 it) |
|---|---|---|---|---|---|---|---|---|
| r0203 | 0.1450 → 0.1700 | 0.1858 → 0.1935 | -5.158 → -5.500 | 2.72 → 2.38 | 0.2174 → 0.2264 | -5.954 → -6.270 | 224 (p=0.17) | 5/4600 |
| r0203-f50 | 0.1850 → 0.1900 | 0.1965 → 0.2022 | -5.847 → -6.131 | 2.03 → 1.74 | 0.2353 → 0.2425 | -6.260 → -6.410 | 234 (p=0.19) | 0/3000 |
| r0203-f70 | 0.1889 → 0.1900 | 0.1992 → 0.2017 | -6.000 → -6.064 | 1.88 → 1.81 | 0.2392 → 0.2408 | -6.228 → -6.300 | 223 (p=0.19) | 0/2400 |
| r0219 | 0.1650 → 0.1769 | 0.1809 → 0.1883 | -5.333 → -5.667 | 2.17 → 1.83 | 0.2220 → 0.2307 | -5.665 → -5.953 | 232 (p=0.175) | 1/3600 |
| r0234 | 0.1600 → 0.1675 | 0.1722 → 0.1789 | -5.000 → -5.158 | 2.15 → 1.99 | 0.2132 → 0.2174 | -5.338 → -5.619 | 236 (p=0.17) | 5/2800 |
| r0234-f50 | 0.1769 → 0.1816 | 0.1839 → 0.1874 | -5.500 → -5.589 | 1.65 → 1.56 | 0.2264 → 0.2287 | -5.750 → -5.882 | 232 (p=0.18) | 0/2600 |
| r0250 | 0.1500 → 0.1533 | 0.1646 → 0.1714 | -3.750 → -4.500 | 3.06 → 2.31 | 0.1792 → 0.1998 | -5.102 → -5.386 | 218 (p=0.155) | 4/3800 |
| r0250-f50 | 0.1668 → 0.1718 | 0.1750 → 0.1791 | -5.000 → -5.250 | 1.81 → 1.56 | 0.2132 → 0.2198 | -5.423 → -5.509 | 227 (p=0.17) | 0/2600 |
| r0250-f70 | 0.1672 → 0.1678 | 0.1724 → 0.1739 | -4.750 → -5.068 | 2.06 → 1.75 | 0.2065 → 0.2150 | -5.268 → -5.318 | 206 (p=0.17) | 0/2400 |
| r0281 | 0.1400 → 0.1450 | 0.1495 → 0.1544 | -4.250 → -4.408 | 1.94 → 1.79 | 0.1930 → 0.1973 | -4.594 → -4.750 | 217 (p=0.145) | 3/3000 |
| r0281-f50 | 0.1566 → 0.1580 | 0.1627 → 0.1645 | -4.608 → -4.693 | 1.59 → 1.50 | 0.2027 → 0.2050 | -4.940 → -5.009 | 224 (p=0.16) | 0/2400 |

##### Floor diagnostic (c1/floor_diag.py): the near-1% failures of the recipe codes are a few persistent trials (common random numbers)

| code | channel | point | failing trial ids (bit errors at 60 it; clears at 200 / 500 it?) |
|---|---|---|---|
| r0203 | bsc | 0.15 | t=159 (22 b; no / no) |
| r0203 | bsc | 0.16 | t=140 (11 b; yes / yes); t=159 (14 b; no / no) |
| r0203 | awgn | -5.25 | t=17 (2 b; yes / yes); t=94 (22 b; no / no); t=171 (19 b; yes / yes) |
| r0203 | awgn | -5.0 | t=94 (34 b; yes / yes) |
| r0250 | bsc | 0.15 | t=23 (98 b; yes / yes); t=32 (2 b; yes / yes) |
| r0250 | awgn | -4.0 | t=120 (9 b; yes / yes); t=129 (668 b; no / no) |
| r0250 | awgn | -3.75 | t=120 (6 b; yes / yes); t=129 (548 b; yes / yes) |
| r0203-f50 | bsc | 0.185 | t=98 (7 b; no / no); t=115 (1 b; yes / yes) |
| r0234 | awgn | -5.0 | t=66 (183 b; yes / yes); t=176 (18 b; no / no) |
| r0281 | awgn | -4.0 | t=67 (8 b; no / yes) |

#### Capacity check (orchestrator's soft numbers)

| raw hard p | source | 1−h2(p) (hard) | Es/N0 = Qinv(p)²/2 (dB) | BIAWGN C (soft) | ×4 per c2 area: hard / soft | ÷ c2-r0850 0.827: hard / soft | R closable at 1.0 / 1.5 / 2.0 / 3.0 dB gap | net bits per c2 area at those R ((4096R−132)/1024) |
|---|---|---|---|---|---|---|---|---|
| 0.058 | VersaLink D c2 (per c2 cell) | 0.681 | 0.92 | 0.789 | 2.72 / 3.16 | 3.29 / 3.82 | 0.715 / 0.676 / 0.636 / 0.557 | 2.73 / 2.58 / 2.42 / 2.10 |
| 0.1 | (reference) | 0.531 | -0.86 | 0.654 | 2.12 / 2.62 | 2.57 / 3.16 | 0.575 / 0.536 / 0.498 / 0.425 | 2.17 / 2.01 / 1.86 / 1.57 |
| 0.15 | (reference) | 0.390 | -2.70 | 0.509 | 1.56 / 2.04 | 1.89 / 2.46 | 0.436 / 0.401 / 0.368 / 0.308 | 1.61 / 1.48 / 1.34 / 1.10 |
| 0.173 | Canon per-tile min | 0.335 | -3.53 | 0.448 | 1.34 / 1.79 | 1.62 / 2.17 | 0.380 / 0.348 / 0.318 / 0.264 | 1.39 / 1.26 / 1.14 / 0.93 |
| 0.184 | Canon per-tile p5 | 0.311 | -3.92 | 0.420 | 1.25 / 1.68 | 1.51 / 2.03 | 0.354 / 0.324 / 0.296 / 0.245 | 1.29 / 1.17 / 1.05 / 0.85 |
| 0.202 | Canon per-tile median | 0.274 | -4.58 | 0.376 | 1.10 / 1.50 | 1.33 / 1.82 | 0.315 / 0.287 / 0.261 / 0.215 | 1.13 / 1.02 / 0.92 / 0.73 |
| 0.21 | orchestrator | 0.259 | -4.88 | 0.357 | 1.03 / 1.43 | 1.25 / 1.73 | 0.298 / 0.272 / 0.247 / 0.203 | 1.06 / 0.96 / 0.86 / 0.68 |
| 0.213 | Canon whole-sheet | 0.253 | -4.99 | 0.350 | 1.01 / 1.40 | 1.22 / 1.69 | 0.292 / 0.266 / 0.242 / 0.198 | 1.04 / 0.93 / 0.84 / 0.67 |
| 0.215 | VersaLink grey | 0.249 | -5.07 | 0.345 | 1.00 / 1.38 | 1.20 / 1.67 | 0.288 / 0.262 / 0.238 / 0.196 | 1.02 / 0.92 / 0.82 / 0.65 |
| 0.22 | VersaLink RGB | 0.240 | -5.26 | 0.334 | 0.96 / 1.34 | 1.16 / 1.62 | 0.278 / 0.253 / 0.230 / 0.188 | 0.98 / 0.88 / 0.79 / 0.62 |
| 0.264 | Canon per-tile p95 | 0.167 | -7.01 | 0.241 | 0.67 / 0.96 | 0.81 / 1.16 | 0.198 / 0.179 / 0.161 / 0.131 | 0.66 / 0.59 / 0.52 / 0.40 |

#### Structural

| code | kind | k | R | HEAVY_FRAC | kb/mb | nh×deg | restart | rule-(d) cap | edges | chk deg min..max (mean) | checks w/o info edge | var deg hist | girth>4 | min w1 | min w2 (#≤8) | user bits p100 / p120 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r0203 | recipe (new) | 832 | 0.2031 | 0.3 | 13/51 | 4×10 | 2 | 3 | 10815 | 2..5 (3.31) | 704 (21.6%) | 1:1, 2:3263, 3:576, 10:256 | True (max 1) | 139 | 18 (0) | 700 / 680 |
| r0203-f50 | VARIANT (new) | 832 | 0.2031 | 0.5 | 13/51 | 6×10 | 0 | 3 | 11711 | 2..5 (3.59) | 576 (17.6%) | 1:1, 2:3263, 3:448, 10:384 | True (max 1) | 59 | 34 (0) | 700 / 680 |
| r0203-f70 | VARIANT (new) | 832 | 0.2031 | 0.7 | 13/51 | 9×10 | 0 | 3 | 13055 | 2..5 (4.00) | 192 (5.9%) | 1:1, 2:3263, 3:256, 10:576 | True (max 1) | 260 | 46 (0) | 700 / 680 |
| r0219 | recipe (new) | 896 | 0.2188 | 0.3 | 14/50 | 4×10 | 0 | 3 | 10879 | 2..5 (3.40) | 512 (16.0%) | 1:1, 2:3199, 3:640, 10:256 | True (max 1) | 47 | 21 (0) | 764 / 744 |
| r0234 | recipe (new) | 960 | 0.2344 | 0.3 | 15/49 | 4×10 | 0 | 3 | 10943 | 2..5 (3.49) | 512 (16.3%) | 1:1, 2:3135, 3:704, 10:256 | True (max 1) | 45 | 18 (0) | 828 / 808 |
| r0234-f50 | VARIANT (new) | 960 | 0.2344 | 0.5 | 15/49 | 8×10 | 0 | 4 | 12735 | 2..6 (4.06) | 384 (12.2%) | 1:1, 2:3135, 3:448, 10:512 | True (max 1) | 40 | 22 (0) | 828 / 808 |
| r0250 | recipe (prev run) | 1024 | 0.2500 | 0.3 | 16/48 | 5×10 | 0 | 3 | 11455 | 2..5 (3.73) | 256 (8.3%) | 1:1, 2:3071, 3:704, 10:320 | True (max 1) | 75 | 20 (0) | 892 / 872 |
| r0250-f50 | VARIANT (new) | 1024 | 0.2500 | 0.5 | 16/48 | 8×10 | 1 | 4 | 12799 | 2..6 (4.17) | 384 (12.5%) | 1:1, 2:3071, 3:512, 10:512 | True (max 1) | 42 | 31 (0) | 892 / 872 |
| r0250-f70 | VARIANT (new) | 1024 | 0.2500 | 0.7 | 16/48 | 11×10 | 0 | 4 | 14143 | 2..6 (4.60) | 192 (6.2%) | 1:1, 2:3071, 3:320, 10:704 | True (max 1) | 79 | 33 (0) | 892 / 872 |
| r0281 | recipe (new) | 1152 | 0.2812 | 0.3 | 18/46 | 5×10 | 0 | 3 | 11583 | 2..5 (3.93) | 576 (19.6%) | 1:1, 2:2943, 3:832, 10:320 | True (max 1) | 105 | 14 (0) | 1020 / 1000 |
| r0281-f50 | VARIANT (new) | 1152 | 0.2812 | 0.5 | 18/46 | 9×10 | 0 | 4 | 13375 | 2..6 (4.54) | 128 (4.3%) | 1:1, 2:2943, 3:576, 10:576 | True (max 1) | 26 | 25 (0) | 1020 / 1000 |
| r0313 | recipe (prev run) | 1280 | 0.3125 | 0.3 | 20/44 | 6×10 | 0 | 4 | 12159 | 2..6 (4.32) | 320 (11.4%) | 1:1, 2:2815, 3:896, 10:384 | True (max 1) | 58 | 12 (0) | 1148 / 1128 |
| r0313-f50 | VARIANT (prev run) | 1280 | 0.3125 | 0.5 | 20/44 | 10×10 | 0 | 4 | 13951 | 2..6 (4.95) | 128 (4.5%) | 1:1, 2:2815, 3:640, 10:640 | True (max 1) | 43 | 15 (0) | 1148 / 1128 |

#### (a) BSC frontier

| code | kind | R | p_cap | p@1% | p@10% | gap@1% (bits) | p@1%/p_cap | p@1% detected-only | lowest p with an undetected | iters@1% (all / ok) | walk pts | undetected/trials |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r0203 | recipe (new) | 0.2031 | 0.2411 | 0.1450 | 0.1858 | 0.200 | 0.601 | 0.1450 | — | 61.6 / 61.1 (p=0.145) | 23 | 0/4600 |
| r0203-f50 | VARIANT (new) | 0.2031 | 0.2411 | 0.1850 | 0.1965 | 0.106 | 0.767 | 0.1850 | — | 87.7 / 87.4 (p=0.185) | 16 | 0/3200 |
| r0203-f70 | VARIANT (new) | 0.2031 | 0.2411 | 0.1889 | 0.1992 | 0.098 | 0.783 | 0.1889 | — | 85.6 / 85.1 (p=0.19) | 14 | 0/2800 |
| r0219 | recipe (new) | 0.2188 | 0.2319 | 0.1650 | 0.1809 | 0.135 | 0.712 | 0.1650 | — | 82.7 / 82.3 (p=0.165) | 20 | 0/4000 |
| r0234 | recipe (new) | 0.2344 | 0.2230 | 0.1600 | 0.1722 | 0.131 | 0.717 | 0.1600 | 0.185 | 84.8 / 84.4 (p=0.16) | 17 | 2/3400 |
| r0234-f50 | VARIANT (new) | 0.2344 | 0.2230 | 0.1769 | 0.1839 | 0.092 | 0.793 | 0.1769 | — | 87.5 / 87.3 (p=0.175) | 14 | 0/2800 |
| r0250 | recipe (prev run) | 0.2500 | 0.2145 | 0.1500 | 0.1646 | 0.140 | 0.699 | 0.1500 | 0.160 | 79.2 / 78.8 (p=0.15) | 18 | 5/3600 |
| r0250-f50 | VARIANT (new) | 0.2500 | 0.2145 | 0.1668 | 0.1750 | 0.100 | 0.778 | 0.1668 | — | 83.9 / 83.7 (p=0.165) | 14 | 0/2800 |
| r0250-f70 | VARIANT (new) | 0.2500 | 0.2145 | 0.1672 | 0.1724 | 0.099 | 0.780 | 0.1672 | — | 75.6 / 75.6 (p=0.165) | 13 | 0/2600 |
| r0281 | recipe (new) | 0.2812 | 0.1984 | 0.1400 | 0.1495 | 0.135 | 0.706 | 0.1400 | — | 79.9 / 79.5 (p=0.14) | 16 | 0/3200 |
| r0281-f50 | VARIANT (new) | 0.2812 | 0.1984 | 0.1566 | 0.1627 | 0.093 | 0.789 | 0.1566 | — | 81.0 / 80.9 (p=0.155) | 13 | 0/2600 |
| r0313 | recipe (prev run) | 0.3125 | 0.1834 | 0.1200 | 0.1398 | 0.158 | 0.654 | 0.1300 | 0.105 | 50.7 / 50.2 (p=0.12) | 20 | 13/4000 |
| r0313-f50 | VARIANT (prev run) | 0.3125 | 0.1834 | 0.1350 | 0.1505 | 0.117 | 0.736 | 0.1450 | 0.105 | 62.0 / 61.8 (p=0.135) | 20 | 16/4000 |

##### (a) raw grid

| code | p : fails/n (undet) [mean iters] |
|---|---|
| r0203 | 0.135: 0/200 [50]; 0.140: 0/200 [56]; 0.145: 2/200 [62]; 0.150: 1/200 [68]; 0.155: 2/200 [75]; 0.160: 2/200 [79]; 0.165: 2/200 [82]; 0.170: 4/200 [85]; 0.175: 6/200 [89]; 0.180: 12/200 [93]; 0.185: 18/200 [97]; 0.190: 36/200 [103]; 0.195: 72/200 [108]; 0.200: 108/200 [113]; 0.205: 148/200 [117]; 0.210: 188/200 [120]; 0.215: 198/200 [120]; 0.220: 200/200 [120]; 0.225: 200/200 [120]; 0.230: 200/200 [120]; 0.235: 200/200 [120]; 0.240: 200/200 [120]; 0.245: 200/200 [120] |
| r0203-f50 | 0.170: 0/200 [77]; 0.175: 0/200 [81]; 0.180: 1/200 [84]; 0.185: 2/200 [88]; 0.190: 5/200 [92]; 0.195: 15/200 [97]; 0.200: 39/200 [103]; 0.205: 82/200 [110]; 0.210: 129/200 [115]; 0.215: 169/200 [118]; 0.220: 189/200 [119]; 0.225: 196/200 [120]; 0.230: 199/200 [120]; 0.235: 200/200 [120]; 0.240: 200/200 [120]; 0.245: 200/200 [120] |
| r0203-f70 | 0.180: 0/200 [78]; 0.185: 0/200 [81]; 0.190: 3/200 [86]; 0.195: 8/200 [90]; 0.200: 24/200 [97]; 0.205: 62/200 [105]; 0.210: 119/200 [113]; 0.215: 162/200 [118]; 0.220: 192/200 [119]; 0.225: 197/200 [120]; 0.230: 200/200 [120]; 0.235: 200/200 [120]; 0.240: 200/200 [120]; 0.245: 200/200 [120] |
| r0219 | 0.140: 0/200 [55]; 0.145: 0/200 [63]; 0.150: 1/200 [69]; 0.155: 1/200 [74]; 0.160: 0/200 [78]; 0.165: 2/200 [83]; 0.170: 3/200 [87]; 0.175: 7/200 [91]; 0.180: 18/200 [97]; 0.185: 33/200 [102]; 0.190: 71/200 [108]; 0.195: 115/200 [113]; 0.200: 148/200 [117]; 0.205: 185/200 [119]; 0.210: 198/200 [120]; 0.215: 199/200 [120]; 0.220: 200/200 [120]; 0.225: 200/200 [120]; 0.230: 200/200 [120]; 0.235: 200/200 [120] |
| r0234 | 0.150: 0/200 [76]; 0.155: 0/200 [80]; 0.160: 2/200 [85]; 0.165: 8/200 [89]; 0.170: 14/200 [94]; 0.175: 31/200 [100]; 0.180: 73/200 [107]; 0.185: 115/200 (1u) [113]; 0.190: 155/200 (1u) [117]; 0.195: 185/200 [119]; 0.200: 198/200 [120]; 0.205: 200/200 [120]; 0.210: 200/200 [120]; 0.215: 200/200 [120]; 0.220: 200/200 [120]; 0.225: 200/200 [120]; 0.230: 200/200 [120] |
| r0234-f50 | 0.165: 0/200 [78]; 0.170: 0/200 [83]; 0.175: 1/200 [87]; 0.180: 6/200 [93]; 0.185: 28/200 [100]; 0.190: 69/200 [107]; 0.195: 120/200 [114]; 0.200: 167/200 [118]; 0.205: 191/200 [120]; 0.210: 197/200 [120]; 0.215: 200/200 [120]; 0.220: 200/200 [120]; 0.225: 200/200 [120]; 0.230: 200/200 [120] |
| r0250 | 0.135: 0/200 [59]; 0.140: 0/200 [66]; 0.145: 1/200 [74]; 0.150: 2/200 [79]; 0.155: 8/200 [84]; 0.160: 11/200 (1u) [90]; 0.165: 21/200 (1u) [95]; 0.170: 47/200 (1u) [102]; 0.175: 72/200 (1u) [108]; 0.180: 122/200 (1u) [113]; 0.185: 162/200 [117]; 0.190: 188/200 [119]; 0.195: 196/200 [120]; 0.200: 199/200 [120]; 0.205: 200/200 [120]; 0.210: 200/200 [120]; 0.215: 200/200 [120]; 0.220: 200/200 [120] |
| r0250-f50 | 0.155: 0/200 [70]; 0.160: 0/200 [77]; 0.165: 1/200 [84]; 0.170: 7/200 [90]; 0.175: 20/200 [96]; 0.180: 48/200 [104]; 0.185: 103/200 [112]; 0.190: 157/200 [117]; 0.195: 191/200 [119]; 0.200: 198/200 [120]; 0.205: 199/200 [120]; 0.210: 200/200 [120]; 0.215: 200/200 [120]; 0.220: 200/200 [120] |
| r0250-f70 | 0.160: 0/200 [68]; 0.165: 0/200 [76]; 0.170: 11/200 [84]; 0.175: 39/200 [95]; 0.180: 87/200 [106]; 0.185: 137/200 [114]; 0.190: 177/200 [118]; 0.195: 199/200 [120]; 0.200: 200/200 [120]; 0.205: 200/200 [120]; 0.210: 200/200 [120]; 0.215: 200/200 [120]; 0.220: 200/200 [120] |
| r0281 | 0.130: 0/200 [62]; 0.135: 0/200 [72]; 0.140: 2/200 [80]; 0.145: 8/200 [87]; 0.150: 22/200 [95]; 0.155: 42/200 [103]; 0.160: 100/200 [111]; 0.165: 138/200 [116]; 0.170: 183/200 [119]; 0.175: 197/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120]; 0.195: 200/200 [120]; 0.200: 200/200 [120]; 0.205: 200/200 [120] |
| r0281-f50 | 0.145: 0/200 [66]; 0.150: 0/200 [73]; 0.155: 1/200 [81]; 0.160: 9/200 [89]; 0.165: 40/200 [99]; 0.170: 87/200 [108]; 0.175: 131/200 [114]; 0.180: 177/200 [118]; 0.185: 194/200 [120]; 0.190: 200/200 [120]; 0.195: 200/200 [120]; 0.200: 200/200 [120]; 0.205: 200/200 [120] |
| r0313 | 0.095: 0/200 [17]; 0.100: 0/200 [21]; 0.105: 1/200 (1u) [26]; 0.110: 1/200 (1u) [32]; 0.115: 1/200 (1u) [41]; 0.120: 2/200 (1u) [51]; 0.125: 2/200 (1u) [62]; 0.130: 3/200 (1u) [72]; 0.135: 7/200 (1u) [82]; 0.140: 21/200 (1u) [92]; 0.145: 59/200 (2u) [102]; 0.150: 98/200 (1u) [110]; 0.155: 156/200 (1u) [116]; 0.160: 184/200 (1u) [119]; 0.165: 196/200 [120]; 0.170: 199/200 [120]; 0.175: 200/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120] |
| r0313-f50 | 0.095: 0/200 [15]; 0.100: 0/200 [18]; 0.105: 1/200 (1u) [22]; 0.110: 1/200 (1u) [25]; 0.115: 1/200 (1u) [33]; 0.120: 1/200 (1u) [39]; 0.125: 1/200 (1u) [45]; 0.130: 1/200 (1u) [52]; 0.135: 2/200 (2u) [62]; 0.140: 3/200 (2u) [71]; 0.145: 4/200 (2u) [81]; 0.150: 18/200 (2u) [91]; 0.155: 50/200 (2u) [103]; 0.160: 119/200 [112]; 0.165: 160/200 [117]; 0.170: 194/200 [120]; 0.175: 197/200 [120]; 0.180: 200/200 [120]; 0.185: 200/200 [120]; 0.190: 200/200 [120] |

#### (b) BIAWGN frontier

| code | kind | R | Es/N0 Shannon (dB) | Es/N0@1% (dB) | gap (dB) | Es/N0@1% det-only | Es/N0@10% | Eb/N0@1% (dB) | walk pts | undetected/trials |
|---|---|---|---|---|---|---|---|---|---|---|
| r0203 | recipe (new) | 0.2031 | -7.875 | -5.158 | 2.72 | -5.158 | -5.954 | 1.765 | 17 | 0/3400 |
| r0203-f50 | VARIANT (new) | 0.2031 | -7.875 | -5.847 | 2.03 | -5.847 | -6.260 | 1.076 | 14 | 0/2800 |
| r0203-f70 | VARIANT (new) | 0.2031 | -7.875 | -6.000 | 1.88 | -6.000 | -6.228 | 0.922 | 12 | 0/2400 |
| r0219 | recipe (new) | 0.2188 | -7.501 | -5.333 | 2.17 | -5.333 | -5.665 | 1.267 | 13 | 0/2600 |
| r0234 | recipe (new) | 0.2344 | -7.149 | -5.000 | 2.15 | -5.070 | -5.338 | 1.301 | 13 | 3/2600 |
| r0234-f50 | VARIANT (new) | 0.2344 | -7.149 | -5.500 | 1.65 | -5.500 | -5.750 | 0.801 | 13 | 0/2600 |
| r0250 | recipe (prev run) | 0.2500 | -6.815 | -3.750 | 3.06 | -3.750 | -5.102 | 2.271 | 16 | 0/3200 |
| r0250-f50 | VARIANT (new) | 0.2500 | -6.815 | -5.000 | 1.81 | -5.000 | -5.423 | 1.021 | 11 | 0/2200 |
| r0250-f70 | VARIANT (new) | 0.2500 | -6.815 | -4.750 | 2.06 | -4.750 | -5.268 | 1.271 | 13 | 0/2600 |
| r0281 | recipe (new) | 0.2812 | -6.194 | -4.250 | 1.94 | -4.250 | -4.594 | 1.259 | 14 | 2/2800 |
| r0281-f50 | VARIANT (new) | 0.2812 | -6.194 | -4.608 | 1.59 | -4.608 | -4.940 | 0.901 | 11 | 0/2200 |
| r0313 | recipe (prev run) | 0.3125 | -5.624 | -3.858 | 1.77 | -3.875 | -4.201 | 1.194 | 15 | 3/3000 |
| r0313-f50 | VARIANT (prev run) | 0.3125 | -5.624 | -4.250 | 1.37 | -4.250 | -4.460 | 0.801 | 10 | 2/2000 |

##### (b) raw grid

| code | Es/N0 dB : fails/n (undet) [mean iters] |
|---|---|
| r0203 | -8.25: 200/200 [120]; -8.00: 200/200 [120]; -7.75: 200/200 [120]; -7.50: 200/200 [120]; -7.25: 200/200 [120]; -7.00: 195/200 [120]; -6.75: 179/200 [119]; -6.50: 133/200 [115]; -6.25: 72/200 [108]; -6.00: 24/200 [100]; -5.75: 9/200 [93]; -5.50: 3/200 [87]; -5.25: 3/200 [82]; -5.00: 1/200 [77]; -4.75: 1/200 [69]; -4.50: 0/200 [60]; -4.25: 0/200 [47] |
| r0203-f50 | -8.25: 200/200 [120]; -8.00: 200/200 [120]; -7.75: 200/200 [120]; -7.50: 200/200 [120]; -7.25: 199/200 [120]; -7.00: 177/200 [119]; -6.75: 129/200 [115]; -6.50: 72/200 [108]; -6.25: 19/200 [100]; -6.00: 6/200 [92]; -5.75: 1/200 [86]; -5.50: 1/200 [82]; -5.25: 0/200 [76]; -5.00: 0/200 [69] |
| r0203-f70 | -8.25: 200/200 [120]; -8.00: 200/200 [120]; -7.75: 200/200 [120]; -7.50: 200/200 [120]; -7.25: 199/200 [120]; -7.00: 189/200 [120]; -6.75: 151/200 [116]; -6.50: 87/200 [108]; -6.25: 25/200 [96]; -6.00: 2/200 [87]; -5.75: 0/200 [79]; -5.50: 0/200 [71] |
| r0219 | -7.75: 200/200 [120]; -7.50: 200/200 [120]; -7.25: 200/200 [120]; -7.00: 200/200 [120]; -6.75: 193/200 [120]; -6.50: 171/200 [118]; -6.25: 126/200 [114]; -6.00: 75/200 [107]; -5.75: 32/200 [99]; -5.50: 8/200 [92]; -5.25: 1/200 [86]; -5.00: 0/200 [80]; -4.75: 0/200 [75] |
| r0234 | -7.50: 200/200 [120]; -7.25: 200/200 [120]; -7.00: 200/200 [120]; -6.75: 200/200 [120]; -6.50: 199/200 [120]; -6.25: 194/200 [120]; -6.00: 161/200 [118]; -5.75: 104/200 [112]; -5.50: 44/200 (1u) [103]; -5.25: 13/200 (1u) [94]; -5.00: 2/200 (1u) [87]; -4.75: 0/200 [81]; -4.50: 0/200 [73] |
| r0234-f50 | -7.50: 200/200 [120]; -7.25: 200/200 [120]; -7.00: 200/200 [120]; -6.75: 200/200 [120]; -6.50: 196/200 [120]; -6.25: 159/200 [118]; -6.00: 86/200 [109]; -5.75: 20/200 [98]; -5.50: 2/200 [90]; -5.25: 1/200 [81]; -5.00: 1/200 [73]; -4.75: 0/200 [62]; -4.50: 0/200 [52] |
| r0250 | -7.00: 200/200 [120]; -6.75: 200/200 [120]; -6.50: 200/200 [120]; -6.25: 200/200 [120]; -6.00: 183/200 [119]; -5.75: 146/200 [116]; -5.50: 80/200 [109]; -5.25: 42/200 [101]; -5.00: 12/200 [92]; -4.75: 5/200 [84]; -4.50: 3/200 [75]; -4.25: 2/200 [66]; -4.00: 2/200 [52]; -3.75: 2/200 [40]; -3.50: 0/200 [30]; -3.25: 0/200 [22] |
| r0250-f50 | -7.00: 200/200 [120]; -6.75: 200/200 [120]; -6.50: 200/200 [120]; -6.25: 197/200 [120]; -6.00: 169/200 [118]; -5.75: 109/200 [112]; -5.50: 37/200 [101]; -5.25: 5/200 [91]; -5.00: 2/200 [82]; -4.75: 0/200 [72]; -4.50: 0/200 [60] |
| r0250-f70 | -7.00: 200/200 [120]; -6.75: 200/200 [120]; -6.50: 200/200 [120]; -6.25: 200/200 [120]; -6.00: 192/200 [120]; -5.75: 153/200 [116]; -5.50: 75/200 [105]; -5.25: 18/200 [88]; -5.00: 6/200 [69]; -4.75: 2/200 [51]; -4.50: 1/200 [41]; -4.25: 0/200 [32]; -4.00: 0/200 [25] |
| r0281 | -6.50: 200/200 [120]; -6.25: 200/200 [120]; -6.00: 200/200 [120]; -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 176/200 [119]; -5.00: 106/200 [113]; -4.75: 47/200 (1u) [102]; -4.50: 12/200 (1u) [92]; -4.25: 2/200 [80]; -4.00: 1/200 [67]; -3.75: 1/200 [55]; -3.50: 0/200 [40]; -3.25: 0/200 [31] |
| r0281-f50 | -6.50: 200/200 [120]; -6.25: 200/200 [120]; -6.00: 200/200 [120]; -5.75: 198/200 [120]; -5.50: 182/200 [119]; -5.25: 105/200 [112]; -5.00: 31/200 [98]; -4.75: 5/200 [83]; -4.50: 1/200 [68]; -4.25: 0/200 [54]; -4.00: 0/200 [43] |
| r0313 | -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 199/200 [120]; -5.00: 191/200 [120]; -4.75: 162/200 [117]; -4.50: 82/200 (1u) [109]; -4.25: 28/200 (1u) [96]; -4.00: 5/200 (1u) [81]; -3.75: 1/200 [64]; -3.50: 1/200 [51]; -3.25: 1/200 [37]; -3.00: 0/200 [27]; -2.75: 1/200 [19]; -2.50: 0/200 [15]; -2.25: 0/200 [13] |
| r0313-f50 | -5.75: 200/200 [120]; -5.50: 200/200 [120]; -5.25: 196/200 [120]; -5.00: 169/200 (1u) [118]; -4.75: 103/200 (1u) [109]; -4.50: 31/200 [95]; -4.25: 2/200 [77]; -4.00: 1/200 [61]; -3.75: 0/200 [46]; -3.50: 0/200 [34] |

#### (c) Erasure + error, fails/n

| code | R | p | ε=0.3 | ε=0.5 | ε=0.7 | max ε @ BLER≤1% | (1−ε)(1−h2(p)) − R at that ε |
|---|---|---|---|---|---|---|---|
| r0203 | 0.203 | 0.02 | 0/200 | 0/200 | 123/200 | 0.5 | 0.226 |
| r0203 | 0.203 | 0.05 | 0/200 | 0/200 | 200/200 | 0.5 | 0.154 |
| r0203-f50 | 0.203 | 0.02 | 0/200 | 0/200 | 94/200 | 0.5 | 0.226 |
| r0203-f50 | 0.203 | 0.05 | 0/200 | 0/200 | 200/200 | 0.5 | 0.154 |
| r0203-f70 | 0.203 | 0.02 | 0/200 | 0/200 | 156/200 | 0.5 | 0.226 |
| r0203-f70 | 0.203 | 0.05 | 0/200 | 0/200 | 200/200 | 0.5 | 0.154 |
| r0219 | 0.219 | 0.02 | 0/200 | 0/200 | 182/200 | 0.5 | 0.211 |
| r0219 | 0.219 | 0.05 | 0/200 | 1/200 (1u) | 200/200 | 0.5 | 0.138 |
| r0234 | 0.234 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.195 |
| r0234 | 0.234 | 0.05 | 0/200 | 1/200 | 200/200 | 0.5 | 0.122 |
| r0234-f50 | 0.234 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.195 |
| r0234-f50 | 0.234 | 0.05 | 0/200 | 0/200 | 200/200 | 0.5 | 0.122 |
| r0250 | 0.250 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.179 |
| r0250 | 0.250 | 0.05 | 0/200 | 3/200 | 200/200 | 0.3 | 0.250 |
| r0250-f50 | 0.250 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.179 |
| r0250-f50 | 0.250 | 0.05 | 0/200 | 0/200 | 200/200 | 0.5 | 0.107 |
| r0250-f70 | 0.250 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.179 |
| r0250-f70 | 0.250 | 0.05 | 0/200 | 1/200 | 200/200 | 0.5 | 0.107 |
| r0281 | 0.281 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.148 |
| r0281 | 0.281 | 0.05 | 0/200 | 71/200 | 200/200 | 0.3 | 0.218 |
| r0281-f50 | 0.281 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.148 |
| r0281-f50 | 0.281 | 0.05 | 0/200 | 14/200 | 200/200 | 0.3 | 0.218 |
| r0313 | 0.312 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.117 |
| r0313 | 0.312 | 0.05 | 0/200 | 184/200 | 200/200 | 0.3 | 0.187 |
| r0313-f50 | 0.312 | 0.02 | 0/200 | 0/200 | 200/200 | 0.5 | 0.117 |
| r0313-f50 | 0.312 | 0.05 | 0/200 | 155/200 | 200/200 | 0.3 | 0.187 |

#### Undetected (syndrome-valid wrong) decodes

| code | channel | undetected/trials | at points |
|---|---|---|---|
| r0219 | eras | 1/1200 | {'eps': 0.5, 'p': 0.05}: 1 |
| r0234 | bsc | 2/3400 | {'p': 0.19}: 1; {'p': 0.185}: 1 |
| r0234 | awgn | 3/2600 | {'esn0_db': -5.5}: 1; {'esn0_db': -5.25}: 1; {'esn0_db': -5.0}: 1 |
| r0250 | bsc | 5/3600 | {'p': 0.18}: 1; {'p': 0.175}: 1; {'p': 0.17}: 1; {'p': 0.165}: 1; {'p': 0.16}: 1 |
| r0250 | eras | 1/3600 | {'eps': 0.6, 'p': 0.05}: 1 |
| r0281 | awgn | 2/2800 | {'esn0_db': -4.75}: 1; {'esn0_db': -4.5}: 1 |
| r0313 | bsc | 13/4000 | {'p': 0.16}: 1; {'p': 0.155}: 1; {'p': 0.15}: 1; {'p': 0.145}: 2; {'p': 0.14}: 1; {'p': 0.135}: 1; {'p': 0.13}: 1; {'p': 0.125}: 1; {'p': 0.12}: 1; {'p': 0.115}: 1; {'p': 0.11}: 1; {'p': 0.105}: 1 |
| r0313 | awgn | 3/3000 | {'esn0_db': -4.5}: 1; {'esn0_db': -4.25}: 1; {'esn0_db': -4.0}: 1 |
| r0313 | eras | 1/3600 | {'eps': 0.4, 'p': 0.05}: 1 |
| r0313-f50 | bsc | 16/4000 | {'p': 0.155}: 2; {'p': 0.15}: 2; {'p': 0.145}: 2; {'p': 0.14}: 2; {'p': 0.135}: 2; {'p': 0.13}: 1; {'p': 0.125}: 1; {'p': 0.12}: 1; {'p': 0.115}: 1; {'p': 0.11}: 1; {'p': 0.105}: 1 |
| r0313-f50 | awgn | 2/2000 | {'esn0_db': -5.0}: 1; {'esn0_db': -4.75}: 1 |
| r0313-f50 | eras | 1/3600 | {'eps': 0.4, 'p': 0.05}: 1 |
