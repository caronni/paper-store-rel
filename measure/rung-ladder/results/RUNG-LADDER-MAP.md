# Rung ladder decision map — 2026-09-30 (rev. 2, after the three-lens refutation pass)

**rev. 3 note, 2026-10-17 — brought current on the overnight confirm (study §7.4); the rev. 2 text below stays as the dated artifact:**
- §3's candidate reach is the frozen recipe's. The confirmed winners (5,000 fresh trials, t ≥ 20,000): k 1664 1.03 dB / p@1 % 0.1113; k 1600 1.11 / 0.1159; k 1280 1.29 / 0.1474; k 1216 1.26 / 0.1558. Frozen six 0.79–1.05 dB, not beaten; r0850 / r0775 / r0625 / r0550 carry syndrome-valid floors of 5 / 6 / 30 / 123 per 30,000–60,000 trials.
- §4's "fits which rung" column therefore understates reach by about one row at the low k; the hard-vs-hard method is contradicted by Canon sheet G (e040 §040.4f: C 14.2 / M 20.2 / Y 25.5 % whole-page, closed at r0700) as well as by sheet D (C10).
- §6 R4: (b) priced — none of the four winners loads in production (`construct.load_code`: one heavy class, light degree 3; k 1216's ARA is n > 4096); schema-fitting codes trail by 0.04–0.08 dB (resolvable at k 1216: 52 vs 102 of 5,000 at −4.65 dB) and still need balanced placement plus a per-rung heavy fraction.
- §6 R5: "pair weight ≥ 10" → the study's floor is 16, and the confirm shows the screen does not predict cleanliness (dirty finalists 10/15, 9/15, 11/15, 3/15 at k 1664/1600/1280/1216; four in-service rungs would fail it). "Re-measure f50 at 1664 first" withdrawn: the trial's k 1664 winner is h8 f0.5, and the overnight swept heavy fraction 0.2–0.8. The gain to quote is the confirm's 0.25–0.51 dB, not the trial's 0.45–0.53.
- §7: "f50 at k 1216/1664" done by the sweep (real labels still owed); "DE thresholds for the candidates" done (B1). Added (study §9, 2026-10-17): the finalists under production conditions (p120 shortening, the 150-iteration retry), erasure on tile geometry, addressing at p 0.11–0.16, the grid above degree 16 and k < 1216, a sized acceptance run per minted draw, bit-exactness on a current env.
- Evidence: the confirm rows, the row union of every stage (xz), the run log, the pre-launch identity checks and the probes are in `measure/rung-ladder/results/` since 2026-10-17 (its README).

Question (owner): r0550 is meaningless (keep r0547); should we build r0300/r0400? Do they have the right resilience, or should the 4096−100 bits be used some other way? Plus the c1 reading (e039/e040): "enticing for lower rungs" and "a real capacity gain over c2 at high rung".
Evidence: the harness in scratch/rung-ladder-20260930/{TABLES.md,TABLES-c1.md,structure.json,undetected_diag.txt,verify/punct_results.json}. Code identities were checked by edge digest through both ports, and five spot points were re-measured. Every harness number is one construction draw per label, 200 trials per point, on a 0.005 / 0.25 dB grid, so differences under ~0.02 in p or 0.25 dB are noise. Every paper number below is ONE sheet on ONE engine. Nothing here is promoted.
Withdrawn (refuted 2 of 3):
- C7: the confetti net-bytes model is withdrawn. Its claims were: R×yield 0.435 vs 0.385 at 25.4 mm, a break-even of ≈ 2.6 tiles per edge equal to "the placement grain", and sheet J's FLOOR streams as "the only unpriced customer". Nothing on file computes 0.435/0.385 or 2.6. e015's 0.796 yield comes from a single c3/r0550 simulation. The c2 grain is ~10 mm, not 14 mm (e014:360). The FLOOR tiles are mostly beyond r0406's own erasure reach.

## 1. The ladder today (src/holo/core/ldpc/construct.py:69-76; user bits = k−32−sites, src/holo/core/ldpc/tile.py:49-54)

| rung | k | true R | user bits p100 / p120 | BSC 1 % point: record (docs/FEC-DESIGN.md:87-89) / harness p@1 % | on paper |
|---|---|---|---|---|---|
| r0547 | 2240 | 0.5469 | 2108 / 2088 | not recorded / 0.065 | Y bank of every cmy8-p120 v0/v1 sheet; sheet J, all planes (e035, VERIFIED ×3) |
| r0550 | 2240 | 0.5469 | 2108 / 2088 | clean at 0.055 / 0.062 det-only (0.045 with its syndrome-valid floor, §2) | fossil rows 1 (c3, e033 A2/G) and 12 (c4, e033 A). C/M banks of the cmy8 v0/v1 rows: e030, e032 (incl. the first CMY8 close, 718,413 B), e033 D-F, e038 F. The cmy7 bank child (e032 ×2). Sources: src/holo/format/fossils.py:93-117, profiles.py:221-224,247-257. Row 2 (c2-r0550@3328x2304) is "goldens, unprinted" (fossils.py:95-96). |
| r0625 | 2560 | 0.625 | 2428 / 2408 | 0.5 % at 0.045 / 0.050 | never printed |
| r0700 | 2880 | 0.703 | 2748 / 2728 | 1.5-1.8 % at 0.035 / 0.036 | K: e029, e032, e039 A-C (VersaLink, HP VERIFIED). Sheet I (e033/e034/e037, 100 %). |
| r0775 | 3200 | 0.781 | 3068 / 3048 | 0.5 % at 0.020 / 0.021 | e039 H via the re-screening PDF path; unscanned |
| r0850 | 3520 | 0.859 | 3388 / 3368 | 3.5 % at 0.010 / 0.008 | sheet H (e036, 100 %); VersaLink D VERIFIED 657,042 B from one 1200 dpi capture (e039:575-584) |

Rung names are nominal for the top four (r0700 is really 0.703, and so on). The ladder step is 320 user bits. The instrument table spells the top rung "r0859" and has no r0547 entry (src/holo/characterize/summarize.py:466-474).

## 2. r0550 vs r0547

- Same k, same user bits, same width S = k−p−33, same CPU per attempt (35.0 vs 35.2 ms, cost_fit.py). They are two independent draws: the seed label is `ldpc-v1/<token>` (src/paperholo/ldpc.py:208-210). As a rate, r0550 is meaningless.
- The two draws do differ, but only in the undetected tail.
  - r0550 has a weight-6 codeword on info bits 1157+1363 (verified by encoding, three times independently). r0547's exhaustive two-info-bit minimum is 12, at (684, 733). Source: structure.json.
  - In this harness (log-LLR seeds), r0550 produced syndrome-valid wrong decodes: 1/200 at p 0.025-0.040, then 2-4/200 at 0.045-0.065. Totals: 22/3600 BSC and 8/2000 AWGN, against r0547's 0/2000 and 0/1800 (TABLES.md:34-35,56,76-77,201-202).
  - The low-p 1/200 is ONE correlated trial repeated across the grid, because the seed base is shared. Only trial 154 (p 0.03) is traced to the weight-6 word (undetected_diag.txt:1). The floor should scale like p³, not stay flat.
  - The test's magnitude-4.0 seeds read 0/200 at p 0.055 (TABLES.md:189), which is why the record says "clean". The floor has never been seen on paper.
  - CRC-32 rejects every such decode (tile.py:161-162). The cost is a lost attempt, never a wrong certificate.
  - On the waterfall the two draws tie within noise: BSC det-only 0.062 vs 0.065; AWGN 1.09-1.21 vs 1.13 dB.
  - Low-weight pair words are a property of the recipe, not a flaw of this one draw: r0625 has pair weight 6, r0775 5, r0850 4 (structure.json). r0547's pair weight of 12 is not its minimum distance, because words with 3+ info bits were never enumerated. Treat this as hygiene, not safety.
- Ruling 6 already says "zero reason to choose 0550 over 0547" (docs/CMY8-COLUMN-GROUPS.md:468-472). e039/e040 printed no 2240 rung at all (e039:122-131).
- Lawful options:
  - (a) EMISSION retirement: no new v2 identity names r0550. This needs one sentence in docs/FORMAT-SPACE.md §6 plus the help text at src/holo/cli.py:150-154.
  - (b) Also re-key PROFILES rocksolid/resilient/high-volume to r0547. These become NEW v2 identities with no sheet lineage; holo3 never consumes profiles (receiver cli.py:61-65). Optional.
  - What must stay: the r0550 mother code (LADDER entry and json), which is frozen substrate (docs/FORMAT-SPACE.md:58-62).
  - Retiring r0550 is never a reason to delete anything. Fossils, -v0 banks, legacy registry rows and legacy tests fall ONLY under the owner's separate fossil sunset, which is still OPEN and user-declared (FORMAT-SPACE.md:12,18-22,362-368,551-553; row 15/sheet J exempt, :436-438). That sunset would strand printed r0550 sheets unless they get a replacement identity route.
  - Keep the "same k ≠ same code" pin (src/holo/receiver/tests/test_h3_format_identity.py:191-194).

## 3. Candidate rungs, measured (frozen recipe HEAVY_FRAC 0.30 / heavy_deg 10 unless marked; TABLES.md, TABLES-c1.md)

| candidate | k | R | builds (restart) | checks w/o info edge | BSC p@1 % (gap, bit) | BIAWGN gap | erasure reach at p 0.02 (iid; 0/200 ⇒ BLER ≲ 1.5 %) | variants |
|---|---|---|---|---|---|---|---|---|
| r0203 | 832 | 0.203 | yes (2) | 21.6 % | 0.145 floor (0.200) | 2.72 dB | 50 %+5 % | f50: 0.185 / 2.03 dB. f70: 0.189 / 1.88 dB (best hard point in the record). |
| r0219 | 896 | 0.219 | yes (0) | 16.0 % | 0.165 (0.135) | 2.17 dB | 50 %+2 % | — |
| r0234 | 960 | 0.234 | yes (0) | 16.3 % | 0.160 (0.131) | 2.15 dB | 50 %+2 % | f50: 0.177 / 1.65 dB |
| r0250 | 1024 | 0.250 | yes (0) | 8.3 % | 0.150 (0.140) | 3.06 dB (2/200 stuck-trial plateau; ~1.7 dB at 10 %) | 50 %+2 %; 60 %+1 % 2/200 | f50: 0.167 / 1.81 dB. f70: 0.167 / 2.06 dB. |
| r0281 | 1152 | 0.281 | yes (0) | 19.6 % | 0.140 (0.135) | 1.94 dB | 50 %+2 % | f50: 0.157 / 1.59 dB |
| r0297 (= "r0300" by nearest-snap) | 1216 | 0.297 | yes (0) | 11.1 % | 0.142 (0.113) | 1.90 dB | 50 %+2 % | not measured |
| r0313 (= "r0300" by upward snap) | 1280 | 0.3125 | yes (0) | 11.4 % | 0.120 / 0.130 det-only (0.158 / 0.130); 13/4000 undetected | 1.77 dB | 50 %+2 % | f50: 0.135 / 0.145 det-only, 1.37 dB, 4.5 % empty, **16/4000 BSC + 2/2000 AWGN + 1/3600 erasure undetected** (a distance-16 two-info-bit word, TABLES.md:47,213-215,225). h14: 0.130 / 1.87 dB. h20 fails within 64 restarts (err files name no rule; a rule-(b) stub at k1280 builds 8/8). |
| r0391 | 1600 | 0.391 | yes (0) | 2.6 % | 0.108 (0.117) | 1.25 dB | 40 %+2 % | f50: 0.115 (0.095), 1.23 dB (nil), 0 empty. h14: 0.107 / 1.61 dB. |
| r0406 (= "r0400" by either snap) | 1664 | 0.406 | yes (0) | 0 % (one draw; ~1.5 % expected) | 0.104 (0.113) | 1.30 dB | 40 %+2 % (50 %+2 % fails 197/200) | not measured (f50 never run at 1664); h20 fails within 64 restarts |
| r0469 | 1920 | 0.469 | yes (0) | 0 % | 0.068 / 0.078 det-only (0.172 / 0.138) | 1.24 dB | 30 %+2 % | — |
| r0547 (ref.) | 2240 | 0.547 | frozen | 0 % | 0.065 (0.106) | 1.13 dB | 20 %+2 %; 30 %+2 % 35/200 | Frozen six: BSC 0.072-0.089 for the upper four, r0547 0.106, r0550 0.188 (0.118 det-only). AWGN 0.85-1.21 dB. |

Reading:
- Build: every candidate builds. Recipe draws take ≤ 0.01 s; the 0.13 s maximum was the r0391-h14 variant.
- Info-free checks: 8-22 % for R ≤ 0.3125 (k ≤ 1280). The cause is a low mean info-edge load per block row, (3(kb−nh)+10·nh)/mb = 1.3-2.3, placed by uniform row draws (src/paperholo/ldpc.py:333). It is NOT rule (d): that is an upper cap (:324), and simulated, it slightly reduces empty rows.
- Degrees: 72-80 % of variables are degree 2 (the e-IRA accumulator).
- Soft (BIAWGN) break: between R 0.31 and 0.39. Gaps are 1.77-3.06 dB for R ≤ 0.3125, 1.24-1.30 dB for R 0.39-0.47, and 0.85-1.21 dB for the frozen six.
- Hard (BSC): no break at R 0.4. Gaps are 0.113-0.200 bit below 0.4, and 0.113 (r0406) and 0.172 (r0469) above it.
- HEAVY_FRAC (nh) is the only construction lever that helped, and only for R ≈ 0.20-0.31: 0.35-0.85 dB at the 1 % point (1.25 dB at r0250 against its floor-driven baseline) and 0.26-0.35 dB at 10 % BLER. At R 0.39 it gains nothing (0.02 dB). f70 is no better than f50 at k1024. Every result is one draw, so the effect is confounded with seed variance.
- heavy_deg 14 is worse on AWGN and about flat on BSC.
- Nothing below R 0.3 gets within ~1.5 dB of Shannon.
- 200 iterations buy another 0.1-0.75 dB below R 0.3 (c1/iters-c1.json). That is a receiver-identity ruling, not a rung (tiles.py:45-52).

## 4. Where the channel needs them (measured HARD cell error against the codes' measured p@1 %)

Every row in this section is a hard-decision comparison. Under the equal-variance Gaussian soft model (p = Q(√(2·Es/N0)), the same model used for c1), reach moves about one rung step lower: r0406 → 0.154, r0297/r0313 → 0.186/0.182, r0281-f50/r0250-f50 → 0.203/0.213. No soft MI has been measured on any row.

| regime | measured need | fits which rung (hard) | verdict |
|---|---|---|---|
| AltaLink weak planes: sheet I Y at r0700, sheet H C-on-M+Y 0.214 at r0850, xerox cmy7 18 % | detector-frozen. All closed at their ORIGINAL rung on the receiver axis (e037:110-111; e036:126-138; COLOR-UPLIFT-MEASUREMENTS.md:3044-3054). | none needed | No customer. Sheet J Y trails C/M by 4.5-7 % at r0547 "with margin" (e035:118-127,212). |
| e038 M281 fresh toner, c3, off-band, GENIE 9×9: M 12.0 % / Y 14.1 % (e038:115-133). Pooled means, one sheet. | print-frozen | Frozen r0297 (0.142; 0/200 at 0.125) covers M with margin and Y at its edge. r0406 (0.104) misses both. | Genie only; no receiver has it. The log ranks the engine-contrast lever first (e038:145-152). |
| same, best "blind" classifier (still supervised on emitted truth, so optimistic): M 15.5 % / Y 19.7 % | print-frozen | M: r0281-f50 (0.157) is a tie inside the grid; first fit with margin is r0250-f50 0.167 / r0219 0.165. Y: no code at 1 % BLER (best 0.189); at 10 % BLER r0203-f70 reaches 0.199 (0.202 at 200 iterations). | Beyond r0300/r0400 at hard decisions. Soft would move M to r0297/r0313 and Y to r0281-f50/r0250-f50 (unmeasured). The toner epoch was invalidated 09-14. |
| confetti. Attempt floor k−p: 2120/3976 = 53.3 % of a p120 tile at r0547, 38.8 % at r0406, 37.2 % at k1600, 29.2 % at k1280 (tiles.py:143-145,408-416). | sheet J: 2,031 FLOOR (17.3 %) + 930 ATTEMPTED-failed (7.9 %) tile-streams; neither is split into cut-edge vs hidden-face (e035:129-135,293) | iid-erasure proxy at p 0.02: r0547 20 %, r0406 40 %, r0313 50 % (TABLES.md §c; not cut-edge geometry, channels.py:93-96) | FLOOR tiles (>47 % erased) are mostly beyond r0406's 40 %. A lower rung's natural customer is the 930 failed attempts plus a thin FLOOR band for r0313. Unpriced; net-bytes model withdrawn (C7). |
| e039 colour footings: VersaLink F C 16.7 / M 24.0 / Y 30.4 %; HP F C 29 / M 19 / Y 48 % (raw hard, cell_error.py) | screened / starved, print-frozen | M/Y beyond every rung. VersaLink C is within soft r0300 reach (unmeasured). | Sibling planes are dead: K-only or the dead-plane tier, not a rung. |
| c1 K: VersaLink E 22.0 % RGB / 21.5 % grey (e039:585-624). Canon E 21.3 %, per tile min 17.3 / p5 18.4 / med 20.2 / p95 26.4 / max 35.3 % (e040:125-145; e040's uncommitted per-tile path). HP E dead at placement (e039:724-733). | hard, point-sample, first-placement read (measure/e039-cell-truth/cell_error.py:31-52,89-101) | hard: none whole-sheet; r0203-f70 (0.189) reaches only Canon p5 | arithmetic below |

e038's lever line "Y r0400 / M r0450" matches the GENIE capacities 0.41/0.47 bit with zero code gap. It is one-to-two rung steps optimistic at hard decisions and roughly right under the Gaussian soft model.

**c1 vs c2**, per c2-cell area, using 4·(k−132)/4096. Comparators: c2-r0850 net 0.827 (VersaLink's own VERIFIED sheet D) and c2-r0700 0.671.
- Per-area values: k=832 0.684, 1024 0.871, 1152 0.996, 1280 1.121, 1600 1.434.
- Capacity at p=0.21: hard 1.03, soft-Gaussian 1.43 (1.73×). The owner's (b) holds only AT capacity with zero overhead.
- Hard decisions: at the measured p@1 %/p_cap ratios of 0.60-0.79, the admissible R is 0.05-0.16, i.e. 0.10-0.61× c2-r0850. The 0.55-0.61× figure holds only at the f50/f70 ratio of 0.77-0.79, and it is extrapolated below the smallest built R (0.203). This is a LOSS.
- Soft, unmeasured model:
  - r0250-f50 (soft 0.2132) = 1.05× at Canon 21.3 %. That is a tie inside grid and 200-trial noise. At 200 iterations it reaches 0.220 (VersaLink RGB).
  - r0234-f50 (0.98×) closes all three whole-sheet channels with margin.
  - Folded with the soft closable-tile fraction: 0.58-0.66× c2-r0850 (0.70-0.82× c2-r0700). The earlier "0.74-0.81×" was the ÷c2-r0700 column.
  - A code within 1.5 dB at R 0.27 would give 1.16×.
- The instrument (C10): its threshold is checked (the genie threshold moves ≤ 0.3 pp, e039:616-617), but its position, aperture and soft/context read are uncalibrated against the receiver.
  - It reads sheet D at 5.8 % hard (+0.92 dB equal-variance, a model number since D's levels are asymmetric). Yet r0850 closed D, and r0850 needs +2.875 dB, or 0.8 % BSC (TABLES.md:39,81). That is ~2 dB and ~7× short.
  - So either the tool overstates the effective error, or D's error is concentrated. The record supports concentration: 1,553 certificates vs K 1,552 of 1,961 tiles, so the uncertified 20.8 % would average 24-28 %. Also, 909 certificates came from retry poses the tool never samples.
  - The 21 % is therefore NOT shown to be an upper bound. Concentration cannot rescue Canon E (no tile below 15 %). Only the overstatement branch could move c1.
- The 0-certificate c1-K outcomes on all three engines are receiver facts that stand regardless of the tool.
- The frozen BCH(100,23) t=13 word decodes with iid probability 2.8 % at p=0.21 (1-2 words per sheet observed; 213-430 chain poses, 918-1,896 attempted tiles). The measured binding limit is cell error, not addressing.
  - A c1 row with a new low rung alone is lawful data (c1-k-r0700@106x74 is an emitted identity). At best it breaks even.
  - It becomes a new generation only if the word or the tile has to change (docs/FORMAT-SPACE.md:58-62).
- Verdicts:
  - (a) holds only as "c1 needs R 0.20-0.27, i.e. r0200-r0250 with a better profile, not r0300/r0400".
  - (b) is not demonstrated as measured, and not refuted.

## 5. Alternatives for the 4096−100 bits (one line each)

- **Shorten vs puncture.** KEEP info-tail shortening (tile.py:59-67,157). It is strongest per p in every row (e.g. r0313 shorten 0/200 at p 0.12-0.13).
  - punct_last's 200/200 is a budget artefact. Noiseless, it gives 0/50 syndrome-valid at 60+60 iterations with info correct 50/50, and 20/20 at 200 (up to 200+200 including the retry, mean 119).
  - Under noise it keeps a cost of its own: r0547 p 0.06 plateaus at 18/20 at both 200 and 400 iterations, against 0/200 for shorten and the mother code (verify/punct_results.json).
  - punct_even's cost is real at the production budget: r0547 5/14/57 per 200 vs shorten 0/2/6 (TABLES.md:171-174). Whether it is budget-bound is unresolved: r0313's 48/50 → 20/20 is not significant, and r0547 plateaus at 19/20 at 400. Part of it is a rate increase (0.547 → 0.563).
  - Any puncture needs a new rung id or a v2 generation token (lattice.py:63-66). It buys user bits, not any regime above.
- **Degree profile.** A per-rung `heavy_frac` LdpcSpec field, default 0.30, is the ONLY measured code-side lever (R 0.20-0.31 only).
  - The six frozen draws stay byte-identical if heavy_frac is kept out of the seed string (ldpc.py:409). The fork guards are tests/test_ldpc.py:44-68 H_SHA/CW_SHA (the optional paperholo lane, which must be run explicitly) and tests/holo/test_holo_ldpc.py:43-72.
  - holo's loader already accepts any nh (construct.py:166-172).
  - This is a recipe change under FORMAT-SPACE user input 6, for the owner's ruling.
- **Other families** (protograph/ARA precoding, 5G BG2, constrained no-isolated-white codes): schema or substrate changes. Priced only if c1 gets a measured customer. Nothing to gain at R ≥ 0.4, where the existing rungs sit 0.85-1.21 dB off.
- **Tile length at c1** (128×128, n=16384): the dispersion penalty only goes 0.028 → 0.014 bit and overhead 3.2 % → 0.8 %. Second-order against a 1.6-2 dB code gap and the t=13 word. A new generation.
- **p-axis:** plane-uniform, 180 bits per step = 56 % of one rung step (docs/P-AXIS-DESIGN.md:200-203). Dominated by a true rung at equal area rate. Low-Y triplets blow up column-group spare at p244/p300 (Z→2, 21-44 bits/site). Mint any low-rung colour row at p120 only.
- **Dead-plane tier:** for a low-Y triplet, the dead-Y ceiling (34/41) and the any-one ceiling (24/41) diverge. The planner enforces the any-one ceiling (src/holo/gen/plan.py:106-121; capacity.py:283-286), so a q=0.8 low-Y row today is sized with NO promise. It needs a "dead-Y-only" spelling.
  - The column-group selector also needs a carried[light] floor: r0850x0850x0313 lands at Z=3 (3:3:1), and its any-one ceiling of 4/7 is below the uniform 2/3 (column_groups.py:112-147).

## 6. Recommendation: rulings for the owner (accept / reject each)

- **R1 NAMING.** Rule this before any golden, because the token seeds the matrix and the id seeds AES (docs/FORMAT-SPACE.md:212-216,229-241,284-288).
  - The record has no single snap rule. Nearest-snap is the r0550 comment (construct.py:71), and r0625/r0700/r0775 are consistent with it. Upward snap is r0850 (3520 where nearest gives 3456; undocumented). r0547 uses a true-rate token.
  - Under these, "r0400" = k1664 by either snap. "r0300" = k1216 (nearest) or k1280 (upward, r0850 precedent).
  - Ruling: pick ONE rule and write it down (e.g. nearest, with r0850 recorded as a frozen exception), or use true-rate tokens (r0297/r0313/r0406). Cost: none.
- **R2 r0550.** EMISSION-retired for new v2 identities; r0547 is the 2240 rung for new rows. The mother code stays as frozen substrate. Fossil deletion is the separate open sunset ruling, not this one. Docs ruling plus help text, no PROFILES re-key. Cost: one sentence, one help string. Evidence: §2.
- **R3 Characterize table.** Fix "r0859" → r0850 and add r0547 (rates only, no format effect). Move its pins (tests/holo/test_characterize_margins.py:255-257) and run HOLO_RUN_CHARACTERIZE_SWEEPS=1. Cost: ~1 h.
- **R4 `heavy_frac`.** Make it a per-rung LdpcSpec field (default 0.30, kept out of the seed string) in src/paperholo/ldpc.py:183,276,323 and util/regen_holo_ldpc_data.py:44-61. The goldens and the optional paperholo lane's H_SHA/CW_SHA prove the six draws unchanged. Cost: half a day. Ruled as a recipe change under user input 6, or refused.
- **R5 MINT NOTHING NOW.** No regime MEASURED with a blind detector sits inside r0300/r0400 hard reach (§4). The soft reach one step lower is unmeasured, and the e038 "blind" rows are supervised.
  - Minting is irreversible: ~14 pin sites and four ladder spellings.
  - Record the harness in docs/FEC-DESIGN.md as a dated note so it is not re-derived.
  - If a customer appears: r0400 = k1664 (0 info-free rows in this draw, 1.30 dB), but re-measure f50 at 1664 first, since it was never run. r0300 only at f50, on the real label.
  - Acceptance for new rungs only: no info-free block row, and min two-info-bit pair weight ≥ 10. r0550/r0625/r0775/r0850 would fork retroactively at 6/6/5/4. Pair weight is a screen, not the minimum distance.
- **R6 Puncturing.** Shorten stays; puncturing is not a v1 lever. In every record, replace "punct_last kills every code" with the budget-plus-residual reading in §5.
- **R7 Planner.** Add a "dead-Y-only" tier promise spelling and a carried[light] ≥ 3 floor in column_groups (or refuse such rows). Cost: small, generator-side, no receiver change.
- **R8 c1 line.** Next measurement on machine 1 (scratch/<city>/, snapshots run-E-c1-k-both2.26022 / run-E-canon.33065), zero toner, in this order:
  - (i) Commit e040's per-tile cell_error path. Calibrate it on sheet D, certified vs uncertified tiles. This gives a looseness scale at c2 and 1200 dpi, not a correction for c1, so also run a ±half-cell offset / placement check on E itself.
  - (ii) Adapt measure/stripe_f_discriminant.py to K at c1. Measure test error and EMPIRICAL MI for: point, 0.7-cell box, 3×3 LDA, inked-neighbour-conditioned, and genie 3×3. Add a ±half-cell offset search and an RGB+grey LLR sum.
  - Bar: soft-equivalent ≥ −4.7 dB (≈ 0.36 bit/cell) whole-sheet before any c1 code or family is discussed. The line is closed below −5.5 dB.
  - Until (i) lands, quote no corrected c1 per-cell error or capacity figure. This is a proposed discipline, not a ruling of record; e040:136-137 already quotes "8-10 % with soft decisions and context".
  - Land the K wake-storm fix (57 cpu-h, e039:597-612) before any further c1 decode.
- **R9 First sim gate** (only after R1/R4/R5 mint): a scratch re-draw on the real labels, then the harness BSC/AWGN/erasure runs plus the pair audit. Then the slow-lane e2e runs `c2-k-r0400@53x37` and `c2-cmy8-r0700x0700x0400@53x37`, p120, byte-exact.
  - Plus the offline sheet-J replay: n_informative per tile-stream for the 2,031 FLOOR and 930 ATTEMPTED-failed streams against 1160/1480/1544/2120, split cut-edge vs hidden-face. This decides whether a confetti customer exists, and it replaces the withdrawn yield model.
- **R10 First print candidate: NONE** until R8/R9 produce a customer.
  - If the J replay finds a residue a lower rung would certify: one K confetti sheet c2-k-r0400 beside a c2-k-r0547 control from the same batch, cut size set from the replay, with the owner's go (.claude/rules/hardware.md).
  - No low-Y colour row until an engine shows a blind-detector plane between 0.30 and 0.45 bit.

## 7. Owed / not measured

- cell_error.py calibration on D (per-tile code uncommitted) and a c1 offset check on E.
- c1 soft/context/two-capture MI: nothing at c1 has been measured softly. The same holds for soft MI from the e038 classifiers.
- f50 at k=1216/1664 and on the real seed labels.
- Construction-seed variance (one draw per label everywhere), including whether the HEAVY_FRAC gain survives it.
- 3+-info-bit codeword enumeration (min distance of every rung).
- DE thresholds for the candidates.
- The sheet-J FLOOR/ATTEMPTED split, and a confetti yield model on real scraps (the old one is withdrawn).
- The e038 sethalftone/PJL engine-contrast sheet and the fresh-toner discovery re-take.
- Whether 60/150 iterations stay rung-agnostic (200 bought 0.1-0.75 dB).
- punct_even at a higher budget with n ≥ 200.
- k=2176 (0.531, flagged open in e017), never built.
- The Gaussian-soft assumption vs the VersaLink's asymmetric blank-side fill-in.
