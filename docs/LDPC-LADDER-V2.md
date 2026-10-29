# LDPC ladder v2 — design and plan (2026-10-18)

STATUS: **v0.7 — THE SEARCH IS STOPPED (the owner, 2026-10-24) and SET-1
stands as published (§1.2; `ladder2/codes/`, locked by its manifest and
test, verified on fresh seeds): one accepted code and a runner-up per
rung under the as-built floor bar, ranked by rank v4 (the rung final,
the pooled floor) across eight campaigns (§8.1; the one-page view
`ladder2/results/LEADERBOARD.md`; §1.1 is c2-accept's measured table,
§9 the rulings, §7 the layout — the tracked record is self-sufficient
without `ladder2/runs/`). Nothing printed, nothing integrated (§10);
the one future measurement is the 5G BG2 reference (docs/TODO.md).**
Branch `ldpc-ladder-v2`, tooling under `ladder2/`. This document is the
design of record for a from-scratch rung ladder: twelve mother codes at
n = 4096, k 3712 … 832, each built with the best construction we can
reach and qualified in simulation under the production decoder. It
replaces nothing: the frozen v1 ladder (`src/holo/core/ldpc/construct.py`
LADDER, six rungs) stays the law for every printed sheet. Integration
into generator, receiver and analyzer is a later format version, after
the qualification record exists and the owner has ruled (§10).

Labels as in the rung-ladder study: **measured** (run, source named),
**documented** (a committed record), **inferred** (arithmetic or
reading). Prior record: `docs/RUNG-LADDER-STUDY-2026-09-30.md` (the
2026-09-30 study and its 2026-10-01 construction search),
`docs/FEC-DESIGN.md`, the harness `measure/rung-ladder/`.

## 0. Why, in five lines

1. The frozen rungs sit 0.79–0.99 dB from Shannon at 1 % BLER (measured,
   5,000-trial confirm), of which ~0.45 dB (the study's inference;
   computed in §1 on 2026-10-18: 0.32–0.56 dB by rung) is the n = 4096 finite-length
   price (inferred). Their reach is near the practical limit; four of
   the six carry syndrome-valid wrong-decode floors (r0850 5/30,000,
   r0775 6/40,000, r0625 30/30,000, r0550 123/60,000) from low-weight
   pair words the random recipe does not control.
2. Below k ≈ 1300 the recipe is defective (8–22 % info-free checks); the
   search's balanced placement plus density-evolution profiles bought
   0.25–0.51 dB, and none of the winners fits the production loader.
3. The ladder is uniform in bits (320 per step), about 1 dB per step at
   the top; it has no rung above 0.859 for the lossless c3 rows and none
   below 0.547 for weak planes, fragments and c1.
4. Addressing is keyed on p alone, so rung count costs the receiver
   nothing at discovery: a placed window tries each rung's decode.
5. A v2 ladder is therefore: the same length and lattice, twelve rates,
   every code drawn by a controlled construction, qualified by one
   protocol, with clean floors and a code description general enough to
   carry the better families.

## 1. The ladder

n printed = 4096 cells per tile per plane; Z = 64 (§9 R1); k a multiple of
64. User bits per tile = k − 32 (CRC) − p (furniture sites, shortened
from the information tail). Shannon Es/N0 is the BIAWGN capacity point
at R = k/4096; p_cap the BSC crossover with 1 − H(p) = R (both computed
2026-10-18, `ladder2/lib/channels.py` reproduces them).

| rung (v2 token) | k | kb | parity | mb | user p120 / p300 | Shannon Es/N0 dB | NA bound Es/N0 dB (n 4096, ε 0.01) | BSC p_cap | v1 twin |
|---|---|---|---|---|---|---|---|---|---|
| r0906 | 3712 | 58 | 384 | 6 | 3560 / 3380 | 2.869 | 3.200 (+0.330) | 0.0120 | — |
| r0859 | 3520 | 55 | 576 | 9 | 3368 / 3188 | 1.993 | 2.312 (+0.320) | 0.0199 | r0850 |
| r0781 | 3200 | 50 | 896 | 14 | 3048 / 2868 | 0.804 | 1.121 (+0.317) | 0.0350 | r0775 |
| r0703 | 2880 | 45 | 1216 | 19 | 2728 / 2548 | −0.237 | 0.086 (+0.323) | 0.0525 | r0700 |
| r0625 | 2560 | 40 | 1536 | 24 | 2408 / 2228 | −1.226 | −0.891 (+0.335) | 0.0724 | r0625 |
| r0547 | 2240 | 35 | 1856 | 29 | 2088 / 1908 | −2.214 | −1.861 (+0.353) | 0.0951 | r0547, r0550 |
| r0469 | 1920 | 30 | 2176 | 34 | 1768 / 1588 | −3.242 | −2.865 (+0.377) | 0.1207 | — |
| r0406 | 1664 | 26 | 2432 | 38 | 1512 / 1332 | −4.125 | −3.723 (+0.402) | 0.1437 | — ("r0400") |
| r0359 | 1472 | 23 | 2624 | 41 | 1320 / 1140 | −4.842 | −4.416 (+0.425) | 0.1627 | — |
| r0313 | 1280 | 20 | 2816 | 44 | 1128 / 948 | −5.624 | −5.169 (+0.454) | 0.1834 | — ("r0300") |
| r0250 | 1024 | 16 | 3072 | 48 | 872 / 692 | −6.815 | −6.310 (+0.505) | 0.2145 | — |
| r0203 | 832 | 13 | 3264 | 51 | 680 / 500 | −7.875 | −7.318 (+0.557) | 0.2411 | — |

The NA column is the normal-approximation bound (§5.4) computed by
`ladder2/lib/channels.py` on 2026-10-18 (W1); its excess over Shannon,
0.32 dB at the top rung to 0.56 dB at the bottom, is the finite-length
price no construction recovers. The frozen v1 rungs' 0.79–0.99 dB gaps
therefore leave 0.45–0.65 dB on the table at k ≥ 2240.

Tokens are the true rate k/4096 rounded to three decimals, in a new seed
namespace `ldpc-v2/<token>` (§9 R5); a v2 r0625 is a different code from
v1's r0625. Spacing is ~1 dB per step from r0906 to r0406 and 0.7–1.1 dB
below. Customers by band (documented, one sheet each): r0906 the c3 rows
at 0.06–0.5 % cell error; r0859–r0547 the measured closing population
(0.8–7 %); r0469–r0313 weak planes through the column-group pool and
the soft reach of 10–15 % channels; r0250–r0203 fragments below today's
attempt floor (k − p: 53 % of a tile at r0547, 23 % at r0250, 18 % at
r0203) and the c1 line if its soft read ever clears the study's bar.
Expectations, not gates (§4): gap to Shannon at 1 % BLER ≤ 0.80 dB for
R ≥ 0.55, ≤ 1.0 dB for 0.36–0.47, ≤ 1.2 dB for 0.25–0.31, ≤ 1.4 dB at
r0203; the gap to the finite-length normal approximation (§5.4) is the
number that says how much construction is left on the table.

### 1.1 Measured 2026-10-19 (campaigns c1-rank + c2-accept, seed 0)

The record: `ladder2/results/c2-accept/TABLES.md` (every candidate, walk
and verdict), `ladder2/results/c2-accept/acceptance/<spec>.json` (one
per S4 code), `ladder2/results/c2-accept/codes/` (c2-accept's own published codes, `CODES.md`; the published SET is §1.2). Es/N0
and gaps at 1 % BLER on BIAWGN under the production decoder's batched
twin (60 + SP 60); S3 numbers from 5,000 fresh trials per point on a
0.05 dB grid (the winner's curse of selection applies to them, the S4
BLER column is the unbiased 10⁵-trial check at the S3 point); p@1 % on
the BSC; the undetected counts at the 1 % point and at +0.5 dB per 10⁵
trials; cost = edges / mean iterations of successful decodes / CPU ms
per decode at the 1 % point on one worker. A rung marked NONE has no
S4-accepted code: its best refused code's numbers are shown (§9 R3).

| rung | published code (family · variant · z) | Es/N0@1 % | gap dB | gap to NA dB | p@1 % | gap bit | gap at p120 / p300 | 150-it Es/N0@1 % | S4 BLER | undetected @1 % / +0.5 dB | pair w / min found w | cost edges / iters / ms | v1 twin under this protocol: gap dB (undetected @1 % / +0.5 dB per 10⁵) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r0906 | F1 · v3 free · 64 | 3.673 | 0.804 | 0.473 | 0.0046 | 0.051 | 0.800 / 0.817 | 3.655 | 0.0084 | 5 / 1 | 7 / 6 | 15296 / 9.6 / 2.71 | — |
| r0859 | NONE (best refused F1 · v0 bound · 64) | 2.740 | 0.747 | 0.427 | 0.0092 | 0.065 | 0.756 / 0.747 | 2.733 | 0.0106 | 12 / 0 | 9 / 9 | 16000 / 13.0 / 3.28 | r0850 0.812 (9 / 5) |
| r0781 | F1 · v0 bound · **32** | 1.533 | 0.728 | 0.412 | 0.0193 | 0.081 | 0.756 / 0.745 | 1.522 | 0.0100 | 1 / 0 | 13 / 13 | 17120 / 19.4 / 5.00 | r0775 0.789 (11 / 6, refused by the v2 bar) |
| r0703 | F1 · v3 free · 64 | 0.519 | 0.756 | 0.434 | 0.0328 | 0.089 | 0.765 / 0.773 | 0.485 | 0.0097 | 8 / 0 | 12 / 11 | 16832 / 29.5 / 7.59 | r0700 0.843 (3 / 1) |
| r0625 | NONE (best refused F1 · v0 bound · 64) | −0.399 | 0.827 | 0.492 | 0.0485 | 0.095 | 0.870 / 0.898 | −0.459 | 0.0077 | 32 / 2 | 12 / 12 | 16320 / 32.8 / 8.44 | r0625 0.899 (41 / 32, refused) |
| r0547 | F3 · v0 · 64 | −1.341 | 0.873 | 0.520 | 0.0711 | 0.083 | 0.850 / 1.018 | −1.418 | 0.0066 | 3 / 0 | 22 / 22 | 16896 / 49.5 / 12.67 | r0547 0.981 (8 / 1); r0550 1.046 (181 / 89, refused) |
| r0469 | F3 · v0 · 64 | −2.314 | 0.929 | 0.552 | 0.0937 | 0.083 | 1.001 / 1.264 | −2.365 | 0.0090 | 8 / 0 | 29 / 29 | 16384 / 58.3 / 14.84 | — |
| r0406 | NONE (best refused F3 · v0 · 64) | −3.119 | 1.007 | 0.605 | 0.1130 | 0.085 | 1.036 / 1.145 | −3.192 | 0.0097 | 12 / 2 | 34 / 34 | 15936 / 69.3 / 17.54 | 2026-10-01 search k 1664 (DE e-IRA, another family, unloadable): 1.03 |
| r0359 | F3 · v0 · 64 | −3.659 | 1.182 | 0.757 | 0.1304 | 0.082 | 1.185 / 1.514 | −3.725 | 0.0084 | 9 / 1 | 35 / 35 | 15488 / 74.1 / 17.89 | — |
| r0313 | NONE (best refused F3 · v1 bound+W3 · 64) | −4.308 | 1.316 | 0.861 | 0.1425 | 0.097 | 1.493 / 1.583 | −4.496 | 0.0095 | 18 / 5 | 44 / 39 | 14848 / 85.8 / 19.99 | 2026-10-01 search k 1280 (DE e-IRA, another family, unloadable): 1.29 |
| r0250 | F3 · v1 · 64 | −5.371 | 1.444 | 0.939 | 0.1741 | 0.083 | 1.654 / 1.916 | −5.495 | 0.0097 | 3 / 0 | 50 / 50 | 14656 / 89.5 / 20.90 | — |
| r0203 | F3 · v0 · 64 (S3 rank 2) | −6.200 | 1.675 | 1.118 | 0.1939 | 0.087 | 1.938 / 2.420 | −6.547 | 0.0105 | 1 / 4 | 56 / 46 | 13504 / 91.9 / 19.77 | — |

Runners-up with the same record: r0906, r0703, r0547, r0250
(`<token>-runnerup.json`). The campaign, by its ledgers: c1-rank 4,116
lifts and 19,181 S2 walk tasks (9.6 M decodes); c2-accept 20,707 tasks
and 20.4 M decodes over four runs (8.4 M under the first S3 rule, 7.4 M
after the rate rule, 3.9 M after the duplicate-lift fix, plus one
stopped run), 0 failed, 740–870 decodes/s on 14 workers of machine 4; the
final plan registers 4,100 lifts and 9,888 S2 walks (the rest are the
superseded rules' rows, kept). S3 ranked 2–5 codes per rung and S4
measured the top three (two at r0203).

What the measurement says (measured unless marked; single seed, codec
simulation, NO promotion; the 2026-10-19 review's corrections are in,
`docs/reviews/ldpc-ladder-v2-2026-10-19/`):

- **Gaps to Shannon at 1 % BLER: 0.73–0.80 dB at r0859–r0703 and
  r0906, 0.83–0.93 at r0625–r0469, 1.0–1.3 at r0406–r0313, 1.44 and
  1.68 at the bottom two.** Against the §1 expectations (≤ 0.80 for
  R ≥ 0.55, ≤ 1.0 for 0.36–0.47, ≤ 1.2 for 0.25–0.31, ≤ 1.4 at r0203)
  four rungs meet their bar (r0859, r0781, r0703, r0469); three miss it
  by under 0.03 dB (r0906 +0.004, r0625 +0.027, r0406 +0.007); r0313
  misses by 0.116; r0250 and r0203 miss by 0.244 and 0.275; and two
  rungs fall between the bands as written — r0547 (R 0.547: +0.073
  against 0.80, inside 1.0) and r0359 (R 0.359: +0.182 against 1.0,
  inside 1.2). The gap to the normal approximation (an ML-style
  estimate of the best code's performance, not a bound and not
  BP-reachable) is 0.41–0.52 dB from r0906 to r0547 and 0.55–1.12 dB
  below; part of it is the decoder, not the construction: SP-200 alone
  recovers 0.07 dB at r0547, 0.28 at r0313 and 0.41 at r0203 (the
  SP-200 column), so the construction's own share of the gap grows
  more slowly with falling rate than the raw number suggests.
- **Against the frozen v1 twins — MEASURED LIKE FOR LIKE 2026-10-19
  (`measure/ladder2-v1-twins/`: the six frozen codes through this
  protocol's S3 walks and two 10⁵-trial S4 points; the v1 rows are single
  unselected codes, the v2 rows the best of many lifts, a selection
  effect the S4 column bounds at ≤ 0.01 dB):** r0781 0.728 vs r0775
  0.789, r0703 0.756 vs r0700 0.843, r0547 0.873 vs 0.981 — 0.06–0.11 dB
  better on published codes; r0859 0.747 vs r0850 0.812 and r0625 0.827
  vs r0625 0.899 compare the best REFUSED v2 codes (no v2 code is
  published at those rates under the current bar). The frozen floors
  under the same bar: r0850 9 / 5 (passes, at the edge), r0775 11 / 6
  (REFUSED), r0700 3 / 1, r0625 41 / 32 (REFUSED, a floor), r0547 8 / 1,
  r0550 181 / 89 (REFUSED, its weight-6 pair word) — three of the six
  printed-era codes fail the v2 bar, and r0850, which read sheet H to
  100 %, sits in the floor regime the bar refuses at r0859 (12 / 0,
  0.065 dB faster). The frozen codes' undetected words are two-
  information-bit words of total weight 4–7 (the recipe's uncontrolled
  pair words, every one caught by the CRC-32 deterministically); the v2
  codes' are heavier and carry more information bits — the lifting
  removed the pair-word floor and left the rarer heavy words. The
  2026-10-01 confirm's whole-walk counts agree with this run's waterfalls
  within 0.01 dB and are superseded for floors.
  Against the 2026-10-01 construction search (DE-profiled e-IRA, a
  different family, measured clean at 5,000 trials, unloadable then and
  now): r0406 1.007 vs 1.03, r0313 1.316 vs 1.29 — and both v2 codes
  are S4-refused.
- **Families by band:** F1 (IRA-irregular, PEXIT profile, QC-PEG+ACE)
  wins r0906–r0625; F3 (punctured XOR-state nodes) wins every rung from
  r0547 down — on the waterfall at r0406–r0203, where it leads the best
  F1 by 0.05–0.11 dB on BIAWGN and on the BSC alike; tied at r0469
  (0.929 vs 0.950) and r0547 (0.873 vs 0.874, that F1 dropped at S3 on
  a walk-correlated rate of 2.1e-3); and at r0359 by the BSC tie-break
  (F1 1.138 vs F3 1.182 is inside the 0.05 dB tie band; S4 reads 12 vs
  9 per 10⁵, which Poisson does not resolve). F2 (PBRL) reached no S4:
  dropped on its S3 rate at r0203 (1.5e-3, walk-correlated) where it
  leads the waterfall by 0.46 dB (1.218 vs 1.675); clean but out-ranked
  at r0547 (1.227, 0.35 dB behind) and r0469 (1.216, 0.29 behind). F4
  (near-regular) is third at r0906 and 0.14–0.21 dB behind elsewhere,
  with the cleanest S3 walks (r0781's F4: 0 undetected in its 5,000-
  trial walks; never S4-measured).
- **The F1 last-row-rule variants (§3.3, R8):** the free variant (v3)
  wins r0906 and r0703, the bound-aware placement (v0) r0859, r0781 and
  r0625; v1 (bound + weight-3-first) is F3's best at r0313 (refused) and
  its pick at r0250; the blanket rule (v2) was refused everywhere by the
  info-free-row check and is moot. The bound-aware placement is the
  default and costs nothing where it does not bind — which is also why
  the variants lift to identical codes: 627 duplicate lifts over the
  campaign (0–150 per rung; F1 v3→v0 269, F1 v1→v0 29, F2 96, F3 209,
  F4 24 — most of them are not F1's), the duplicate-lift rule of §3.4.
- **Z (R1):** Z 32 was searched at k 3200 and 2880 and shares the S1
  keep with Z 64 (one (family, variant) group holds both, so at r0703
  only five live Z 32 candidates were screened against 25). It wins
  r0781: 0.728 dB at 1 / 0 undetected, against a Z 64 code at 0.729 and
  18 / 5 — a tie that the S3 BSC tie-break (p 0.0193 vs 0.0192) gave to
  Z 32 and S4 then confirmed by refusing the Z 64 code. That Z 64 code
  is the FREE variant (v3); the bound Z 64 code reads 0.751 at 17 / 1,
  so the Z comparison is confounded with the variant. Nothing at r0703;
  the top two rungs untested at Z 32 (the lifter reaches girth 4).
- **The undetected-decode bar (R3):** at the 1 % point the 35 S4 codes
  produce syndrome-valid wrong decodes at 0.1–5.4 × 10⁻⁴ per trial
  (0.1–6.4 % of their failures; the 13 accepted codes 0.1–1.0 × 10⁻⁴,
  0.1–1.2 %); S4's 1e-4 refuses 22 of the 35, at 11–54 per 10⁵ at the
  1 % point (0–15 at +0.5 dB), including every S4 code at r0859
  (12 / 14 / 13 against ten allowed, with 0 / 0 / 1 at +0.5 dB), r0625
  (32 / 50 / 14), r0406 (12 / 21 / 11) and r0313 (18 / 37 / 27). A code
  at 1.2e-4 passes a 10⁵-trial point about one time in three, so the
  accepted/refused split at r0859 and r0406 is within counting noise of
  the accepted codes elsewhere. What the production CRC-32 makes of
  those decodes (§3.7, measured on the unshortened code's S4 words):
  the share with information weight ≤ 3 (≤ 4 where k − p ≤ 3000) —
  caught deterministically — is 0–88 % per code at the 1 % point
  (r0859's three 23–43 %, r0625's 71–88 %, r0406's 0–58 %, r0313's
  0–84 %); the rest are caught at 1 − 2⁻³² under the random-CRC model,
  a heuristic (each codeword's verdict is deterministic; the stored
  weights do not identify the words — docs/TODO.md).
- **Decoder budget (R6):** 150 + SP 150 against the production
  60 + SP 60 gains 0.01–0.03 dB at r0906–r0781, 0.03–0.08 dB at
  r0703–r0359, and 0.19 / 0.12 / 0.35 dB at r0313 / r0250 / r0203, at
  1.6–1.9× the CPU per decode — a measurable price at the bottom three
  rungs; and it is a selection question at one rung: at 150 iterations
  r0359's F1 leads its F3 pick by 0.079 dB (0.14 at SP-200), outside
  the tie band.
- **Shortening:** at p120 the gap moves by −0.004 … +0.043 dB down to
  r0625 and by −0.02 … +0.26 dB below (r0469 +0.07, r0313 +0.18, r0250
  +0.21, r0203 +0.26); at p300 by 0.00–0.15 dB at r0906–r0547 and
  r0406, 0.33 at r0469 and r0359, and 0.27 / 0.47 / 0.75 at the bottom
  three (the shortened rate at r0203-p300 is 0.14; the gap is measured
  against Shannon at that rate).
- **Cost:** successful decodes take 9.6 iterations at r0906 and 92 at
  r0203 (2.7 → 20 ms on one worker of the batched decoder, 21 at
  r0250; taken at the grid point nearest the 1 % point); the edge count
  is 13.5–17.1 k at every rung, so decode cost is the iteration count,
  i.e. the rate, not the family.
- **Floors as structure:** the pair-weight minima of the published
  codes are 7–16 at r0906–r0703 (bars 6–10) and 20–56 below (bars
  15–24). The impulse search found a codeword for the published code
  at r0906 (6 < pair 7) and r0703 (11 < 12) only; on 29 of the 35 S4
  codes — every F3 code and every code at R ≤ 0.625 — it found no word
  at all (the ±20 LLR clip limits its amplitude reach; `finite_note` in
  each record), so their "minimum found weight" is the single-
  information-bit minimum: equal to the pair minimum at eight rungs,
  below it at r0313 (39 < 44) and r0203 (46 < 56). The union-bound bar
  admits codes at the 1e-4 edge by construction; the §9 R3 options
  price the alternatives.

### 1.2 The published set SET-1 — the working set (adopted 2026-10-20; republished under the corrected metrics 2026-10-21, with c6-low 2026-10-23, with c7-top under rank v4 and with c8-low 2026-10-24)

The owner adopted the leaderboard's picks as the published v2 set on
2026-10-20 ("lock down, record, and document the current-best
candidates") and the same night asked for the rungs to be improved
"according to the correct metrics, and update set-1 accordingly. Drop
the tag, we aren't done yet." SET-1 is therefore the WORKING set: one
code (and a runner-up) per rung in `ladder2/codes/`, republished in
place whenever the search or the metrics move a pick; git history keeps
each publication (the first, rank v1, at f992336e / 38505e44; rank v3
over c2–c5 at e19afe1d; with c6-low at 56ac7b0b; with c7-top under rank
v4 at 83a48c5e; with c8-low, 2026-10-24, the current one).

- **Selection (rank v4, `ladder2/lib/leaderboard.py`, 2026-10-24; v3
  2026-10-21).**
  Eligible: the codes S4 ACCEPTED under the as-built floor bar
  (undetected ≤ 1e-4 per trial at the 1 % point and at +0.5 dB, 10⁵
  trials each; reproduction and bit-exactness as §4) in the tracked
  acceptance records of c2-accept, c3-search, c4-top, c5-mid, c6-low,
  c7-top and c8-low — AND,
  where the code has a rung-final row, the same bar on S4's and the
  final's counts POOLED (S4's verdict alone is conditioned on passing
  it). Ranked by the unbiased 1 % point: the RUNG FINAL's es1 where a
  code has a row, else S3's point corrected by S4's 10⁵-trial BLER
  along the code's own S3 slope; within 0.01 dB (the final's
  resolution) the cleaner floor first — v4: S4's and the final's
  undetected decodes POOLED (4 × 10⁵ trials; v3 read the final's
  2 × 10⁵ alone, and on 2026-10-24 that let a c7-top code with 9 S4
  undetected against 3 tie the fresh counts at r0906 and win on 0.03
  iterations) — then fewer mean iterations at x_ref + 0.5 dB (one
  common Es/N0). The runner-up is the next ranked eligible code with
  another edge_sha. The rung final measures EVERY eligible code inside
  the 0.05 dB window (cap 16; the earlier cap of 5 left a c7-top code
  without a row, and it out-ranked the published code by 0.001 dB on
  the S4-corrected point — two estimators in one rung; never again).
- **The rung final (`ladder2/lib/final.py`, `python -m ladder2 final`;
  `ladder2/results/final/FINAL.md`; MEASURED 2026-10-21, 6.4 M decodes,
  53,500 cpu-s on 9 workers).** Per rung, every S4-accepted code within
  0.05 dB of the rung's best S4-corrected point (≤ 5, plus the
  2026-10-20 picks) — 32 codes — decoded at ONE Es/N0 x_ref (the best
  corrected point) and at x_ref + 0.5 dB on 10⁵ FRESH trials each (t
  from 20,000,000; no campaign or verify run drew them), the SAME trials
  for every code of a rung (the message and the noise draws are shared,
  so the comparison is paired: two codes fail the same trial 18–28×
  more often than independence predicts at r0906–r0703, falling to 2×
  at r0203, and FINAL.md carries McNemar's difference to the best). The S4 correction moved the 82 records by
  −0.004 dB on average (−0.039 … +0.025): S3's points were not
  systematically optimistic, but individual codes moved by up to
  0.04 dB. SECOND MEASUREMENT 2026-10-23, after c6-low: 50 codes, 5,800
  new chunks (5.8 M decodes, 71,600 cpu-s; the 4,200 chunks of rungs
  whose plan did not move were reused), new x_ref at r0469–r0203. THIRD
  2026-10-24, after c7-top and with the cap raised: 60 codes, 2,600 new
  chunks (2.6 M decodes, 10,300 cpu-s); no x_ref moved. FOURTH
  2026-10-24, after c8-low: 64 codes, 2,000 new chunks (2.0 M decodes,
  34,100 cpu-s); x_ref moved at r0250 (−5.676 → −5.714) and r0203
  (−6.622 → −6.652), every contender there re-measured.
- **What the corrected metrics changed (against the 2026-10-20
  publication, rank v1).** Six rungs: **r0906** → the c4-top z 32 span
  code (0.794 dB final, 1 / 1 fresh undetected; v1's pick 0.012 dB
  slower at 11 / 1); **r0859** → c3's z 32 lever lift at 0.715 dB (v1's
  pick, 0.016 dB slower, had won on iterations counted at another
  Es/N0); **r0703** → c2's F1 v3 code (0.754 dB; v1's pick fails the
  pooled floor, 24 undetected in 2 × 10⁵ at the 1 % point); **r0406** →
  c5's F3 z 32 bound code (1.004 dB; v1's pick fails the pooled floor,
  25 in 2 × 10⁵); **r0359** → c2's F3 code at 1.178 dB, 0.029 dB slower
  than v1's F1 pick, which fails the pooled floor (29 in 2 × 10⁵ — the
  verify flag of 2026-10-20 confirmed); **r0203** → c3's F1 code, tied
  with c2's F3 at 0.001 dB and cleaner (6 / 0 against 7 / 1 fresh).
  The v1 defect that started this (its iteration tie-break compared
  counts measured at different grid points) is kept reproducible as
  rank v1; v2 (the floor tie-break on S4's counts) as rank v2.
- **What c6-low changed (2026-10-23).** The ruled PBRL codes (F2
  `weightn`, z 64, design §8.1 Wave D) take the bottom four rungs, each
  confirmed by the rung final on paired fresh trials: **r0359** 1.178 →
  1.035 dB, **r0313** 1.186 → 1.022, **r0250** 1.398 → 1.187,
  **r0203** 1.698 → 1.279 (−0.14 / −0.16 / −0.21 / −0.42 dB), and they
  decode in fewer iterations at the operating point (x_ref + 0.5 dB:
  45.6 → 17.1, 62.3 → 22.0, 76.1 → 37.5, 83.3 → 47.3). At r0250 and
  r0203 the FASTEST F2 code (0.05 / 0.01 dB ahead of the pick) fails the
  pooled floor (25 and 26 undetected in 2 × 10⁵ at the 1 % point against
  S4's 8 and 10) — the pooled rule doing what it was built for. Three
  more rungs move to c6-low codes inside the 0.01 dB window with cleaner
  floors: **r0625** (0.812 dB, 0 / 0 S4, 1 / 0 fresh), **r0469** (z 32,
  0.920, 0 / 0 · 0 / 0), **r0406** (0.999, 1 / 0 · 1 / 0). r0547 kept
  c2's code under v3 (c6's best 0.005 dB behind).
- **What c7-top changed (2026-10-24, rank v4).** The word gate's lifts
  at the top four rungs land inside the tie window of the published
  codes on the waterfall — the top rungs sit 0.40–0.46 dB above the
  finite-length limit and the gate buys floors there, not dB. Three
  rungs move inside the window on the pooled floor: **r0781** → c7's
  z 32 free-variant code (0.733 dB, the same gap; 3 undetected in
  4 × 10⁵ against 5), **r0703** → c7's z 32 free-variant code (0.759,
  0.005 dB behind; 4 against 19), **r0547** → c6's F3 span code (0.848,
  0.005 dB behind; 5 against 6 — the rule's call, at the noise floor of
  the counts). r0906 keeps c4-top's span code: under v3 the c7-top code
  at 0.793 (9 / 1 S4, 1 / 1 fresh) would have taken it on 0.03
  iterations; under v4 the pooled 12 against 6 keeps the cleaner one.
  r0859 unchanged (c7's best 0.009 dB behind, dirtier).
- **What c8-low changed (2026-10-24, PBRL at z 32 under the word gate,
  r0469 … r0203).** Above r0313 nothing: z 32 PBRL is 0.04–0.36 dB
  behind the published codes at r0469–r0313 (at r0359 / r0313 behind
  c6's z 64 PBRL by 0.04–0.09 dB, as the 2026-10-20 screen said). At
  the bottom two rungs it leads the waterfall and takes the pick AT THE
  FLOOR BAR'S EDGE: **r0250** 1.187 → 1.107 dB (−0.080) at 20.4
  iterations against 37.5, **r0203** 1.279 → 1.216 (−0.063) at 32.2
  against 47.3 — with pooled floors of 19 and 20 undetected decodes in
  2 × 10⁵ at the 1 % point (9.5e-5 and 1.0e-4 against the as-built bar's
  1e-4; S4 9 / 3 and 9 / 1, fresh 10 / 3 and 11 / 4) where the codes
  they replace read 12 and 4 (6e-5, 2e-5). The fastest z 32 codes at
  both rungs (another 0.03–0.07 dB ahead) FAIL the bar by 2–5 counts.
  So the bottom rungs are now floor-bound, not waterfall-bound: whether
  0.06–0.08 dB is worth a floor at the bar's edge is R3's ruling (§9),
  and the runner-ups are the cleaner codes (r0250: a z 32 PBRL code at
  1.144, pooled 12 / 1; r0203: c6's z 64 code at 1.278, 3 / 1).
  RULED 2026-10-24 (the owner: "Take the new picks"): the bar stands as
  built and SET-1 keeps them — the floor is a correctness guard the
  tile CRC already provides at these rates, the waterfall and the
  halved decode work are real.
- **Where.** `ladder2/codes/`: one CodeSpec JSON per code
  (`<token>[-z<z>][-runnerup].json`, provenance extended by the set,
  the selection, the campaign record, the measured numbers and the
  rung-final row), `MANIFEST.json` (sha256 and edge_sha per file, the
  frozen inputs: 136 acceptance records, 64 rung-final rows and 12
  rung plans, each with sha256; the ranking version), `CODES.md` (the
  one-page table), `VERIFY.md` / `verify.json`. Written only by
  `python -m ladder2 publish-set`, which refuses a v3 set whose rung
  finals are missing, partial, below 10⁵ trials or stale.
- **Locked per publication.** `ladder2/tests/test_l2_codes_set.py`
  pins every file to the manifest, one code per rung, each code's
  record (tracked, accepted, reproduced, bit-exact), CODES.md, and the
  selection recomputed from the FROZEN acceptance records and rung-final
  rows under the manifest's ranking version; `publish_set.check_set`
  re-runs the rung-final completeness check on the frozen plans.
- **Verified from the published files** (`python -m ladder2
  verify-codes`): digests, edge_sha, H·c = 0 on 64 messages, and the
  BIAWGN BLER at each code's acceptance point on 20,000 fresh trials (t
  from 10,000,000) against its S4 BLER. MEASURED 2026-10-24 (after
  c8-low): all 24 files verify, |z| ≤ 2.28; no floor flagged (fresh
  undetected 0–3 per 20,000) — the two bar-edge picks read 1 (r0250)
  and 3 (r0203) in 20,000, P 0.87 and 0.32 of those counts at the bar,
  and pooled with S4 1.0e-4 at r0203: on the bar, not over it.

| rung | k | file | family · variant · z | campaign | gap dB final (S3) | BLER @x_ref (final) | undetected S4 @1 % / +0.5 · final @x_ref / x_hi | iters @x_hi | ms @x_ref | runner-up: gap final (S4 · final und) |
|---|---|---|---|---|---|---|---|---|---|---|
| r0906 | 3712 | `r0906-z32.json` | F1 · v0 span3l/W30 · 32 | c4-top | 0.794 (0.799) | 0.0108 | 3 / 1 · 1 / 1 | 4.5 | 2.64 | 0.793 (9 / 1 · 1 / 1, c7-top) |
| r0859 | 3520 | `r0859-z32.json` | F1 · v3 F/W30 · 32 | c3-search | 0.715 (0.715) | 0.0099 | 3 / 0 · 3 / 0 | 6.2 | 3.63 | 0.724 (7 / 0 · 5 / 0, c7-top) |
| r0781 | 3200 | `r0781-z32.json` | F1 · v4 F/W30 · 32 | c7-top | 0.733 (0.730) | 0.0111 | 2 / 0 · 1 / 0 | 8.4 | 5.39 | 0.733 (1 / 0 · 4 / 1, c2-accept) |
| r0703 | 2880 | `r0703-z32.json` | F1 · v4 F/W30 · 32 | c7-top | 0.759 (0.746) | 0.0108 | 2 / 0 · 1 / 1 | 10.6 | 6.76 | 0.754 (8 / 0 · 9 / 2, c2-accept) |
| r0625 | 2560 | `r0625-z32.json` | F1 · v2 bound/W30 · 32 | c6-low | 0.812 (0.813) | 0.0104 | 0 / 0 · 1 / 0 | 13.1 | 6.26 | 0.818 (0 / 0 · 1 / 0, c6-low) |
| r0547 | 2240 | `r0547.json` | F3 · v0 span3/W30 · 64 | c6-low | 0.848 (0.842) | 0.0120 | 1 / 0 · 4 / 0 | 18.5 | 12.40 | 0.843 (3 / 0 · 3 / 0, c2-accept) |
| r0469 | 1920 | `r0469-z32.json` | F3 · v2 bound/W30 · 32 | c6-low | 0.920 (0.903) | 0.0104 | 0 / 0 · 0 / 0 | 22.9 | 12.34 | 0.916 (1 / 0 · 1 / 0, c6-low) |
| r0406 | 1664 | `r0406-z32.json` | F3 · v1 span/W30 · 32 | c6-low | 0.999 (1.016) | 0.0095 | 1 / 0 · 1 / 0 | 32.6 | 15.60 | 1.003 (3 / 0 · 2 / 1, c6-low) |
| r0359 | 1472 | `r0359.json` | F2 · v0 span3/W30 · 64 | c6-low | 1.035 (1.015) | 0.0100 | 2 / 0 · 4 / 0 | 17.1 | 12.60 | 1.057 (0 / 0 · 4 / 0, c6-low) |
| r0313 | 1280 | `r0313.json` | F2 · v0 span3/W30 · 64 | c6-low | 1.022 (1.046) | 0.0107 | 3 / 2 · 5 / 1 | 22.0 | 18.48 | 1.019 (6 / 0 · 7 / 2, c6-low) |
| r0250 | 1024 | `r0250-z32.json` | F2 · v0 span3/W30 · 32 | c8-low | 1.107 (1.147) | 0.0106 | 9 / 3 · 10 / 3 | 20.4 | 18.68 | 1.144 (6 / 1 · 6 / 0, c8-low) |
| r0203 | 832 | `r0203-z32.json` | F2 · v0 span3/W30 · 32 | c8-low | 1.216 (1.233) | 0.0094 | 9 / 1 · 11 / 4 | 32.2 | 22.21 | 1.278 (2 / 0 · 1 / 1, c6-low) |

The gap columns are against Shannon at the code's rate (the final's gap
from its es1; S3's in brackets). Where the runner-up's final gap is
SMALLER than or equal to the pick's (r0906, r0781, r0703, r0547, r0469,
r0313) the two sit inside the 0.01 dB tie window and the pick has the
cleaner pooled floor (S4 + final: r0906 6 against 12, r0703 4 against
19, r0547 5 against 6). At r0250 and r0203 the picks are c8-low's z 32
PBRL codes at the floor bar's edge (19 and 20 undetected in 2 × 10⁵ at
the 1 % point against the bar's 20); their runner-ups are the cleaner
codes, 0.04 and 0.06 dB behind.
What SET-1 is NOT: single seed, codec simulation only, nothing printed,
no receiver integration (§10); the search (§8.1) continues and the set
is republished when it moves a rung; the format version that carries
v2 codes names the publication it froze.

## 2. The code description v2

One artifact per rung, JSON, tracked under `ladder2/codes/<token>.json`,
with the fields below. It is PURE quasi-cyclic: every block of H,
parity part included, is a circulant or zero. A v1 code is NOT
expressible in it (v1 permutes the information part's check rows by a
bit-level interleaver `pi` and runs ONE bit-level accumulator across
them; v2's accumulator is the block dual-diagonal, i.e. z parallel
accumulator lanes, the standard QC-IRA / 5G / AR4JA shape). The v1
ladder keeps its own loader forever; v2 codes get the v2 loader in the
later format version. The description carries every family in §3; the
construction tool only writes it.

- `spec`: `token`, `k`, `n_printed` (4096), `z` (64), `n_punct` (0 or a
  multiple of z; §9 R2), `nb` = (n_printed + n_punct)/z, `mb` = nb − k/z
  (every non-information block column, punctured ones included, owns
  one block row; mb·z = n_printed + n_punct − k, which is
  `construct.LdpcSpec.m_bits` at n_bits = 4096 + n_punct). Block
  columns are ordered info, then parity (core and extension in any
  order), then punctured, fixed (W1 deviations 1 and 2). The JSON is one
  FLAT object (no `spec` sub-group, no `encoding` field: encodability is
  checked by the block-peeling encoder at use, W1 deviation 3); a loader
  with verification on refuses a spec whose three digests are missing
  (W1 refutation, finding 3).
- `base`: the base matrix, `mb × nb` integers, −1 for a zero block and a
  circulant shift `s ∈ [0, z)` otherwise; multiplicity 1 per block (one
  circulant per nonzero; a double-edge protograph is lifted twice, i.e.
  the base matrix is already the Z-level description). Circulant
  convention as v1: `I(s)[a, b] = 1 iff b == (a + s) mod z`.
- `roles`: per block column one of `info`, `parity_core`,
  `parity_ext`, `punct`; info columns in **shortening order**: the last
  info columns are the ones the tail shortening removes (§3.6).
- `encoding`: `systematic`; the parity part (`parity_core` + `parity_ext`
  columns, in order) is block lower-triangular with a circulant on every
  diagonal block (I(s), inverse I(−s)) — the block dual-diagonal
  accumulator (I(0) on the diagonal, I(0) on the sub-diagonal) and the
  identity blocks of extension rows are the two cases — so the encoder
  is block back-substitution in O(n) (§3.5). Nothing beyond the base
  matrix is needed to encode; the field only asserts the property. The
  encoder finds the solve order by block peeling (triangular under a
  joint row/column permutation), so an F3 precoder column that sits
  last but must be solved first is lawful (W1 deviation 3).
- `provenance`: family (§3.1), profile id, DE threshold, lifting
  method and seed, construction tool commit, the harness run ids that
  measured it.
- `digests`: `edge_sha` (lexsorted (chk, var) bit-level edges, the v1
  convention `common.edge_sha`), `h_sha` (dense H bits), `cw_sha` (the
  codeword of a fixed test message, encoder fork guard).
- `structure`: degree histograms, girth, ACE spectrum, the min
  two-info-bit pair weight, the lowest codeword weight any §3.7 method
  found, info-free check count (must be 0).

Expansion to the decoders: `ladder2/lib/base.py` turns `base` into the
bit-level edge arrays; `ladder2/lib/adapt.py` wraps them in a
`holo.core.ldpc.construct.Code` (its `enc_*` arrays are rebuilt from the
info edges; `spec.n_bits` = n_printed + n_punct; punctured nodes get LLR
0 at the decoder and are never printed). That is how the production
decoder `holo.core.ldpc.decode` and the bit-exact batched twin
(`measure/rung-ladder/search/fast/fastdecode.py`) decode v2 codes
unchanged; `decode_tile`'s framing is not used here.

## 3. Construction program

### 3.1 Families searched per rung

- **F1 IRA-irregular.** Information columns in 2–4 degree classes (max
  degree ≤ min(mb, 20)), accumulator parity (dual-diagonal, last column
  weight 1, with the option of a weight-3 first parity column to break
  the degree-2 chain's low-weight words). Today's family, done with a
  DE-optimised profile, balanced placement and PEG-ACE lifting. Every
  rung.
- **F2 PBRL / extended IRA.** An IRA core at a higher rate plus
  `parity_ext` columns of degree 1, each the XOR of a few info/core
  bits (one extension row each), the extension rows' info degrees
  DE-optimised row by row (raptor-like). Rungs ≤ r0469.
- **F3 punctured XOR-state nodes** (as built, W3; corrected 2026-10-18:
  NOT an ARA accumulate precoder — each of the 1–2 punctured state
  blocks is a one- or two-step XOR of a few information blocks that
  keep their core edges; a PBRL-like core without extension rows).
  `n_punct` ≤ 128. Rungs ≤ r0406, and r0547/r0469 under `probe`.
- **F4 high-rate.** r0906/r0859/r0781: F1 restricted to near-regular
  information degrees 3–5 (as built; the 5G BG1 high-rate core is NOT
  built, its core is not block-triangular for this encoder); girth 6 is
  the realistic target. The reach here is bounded by the gap in bits
  (r0906 needs p ≤ 1.2 % at capacity).

F2 is admitted at k ≤ 1664 and, with F3, at k 2240/1920 under `probe`
(as built). Every F1 candidate exists in three VARIANTS the campaign
enumerates and the Monte Carlo ranks: (last-row rule on, plain), (on,
weight-3 first parity column), (off, plain) — §3.3 and §9 R8.

The literature pass (`ladder2/docs/LITERATURE.md`) may add or strike a
family with its reason; it does not add a fifth by default.

### 3.2 Profile optimisation (threshold)

Every candidate is a base matrix, so the threshold tool is protograph
EXIT (Liva–Chiani PEXIT, Gaussian approximation) on the base matrix,
which takes punctured and degree-1 nodes as inputs but is the SAME
single-parameter Gaussian approximation the literature warns about
there (LITERATURE §4; we have no full quantized DE). Measured 2026-10-18
(W3 refutation): the PEXIT threshold depends on the convergence
criterion below k ≈ 1700 — thresholds move 0.3–1.0 dB between a
tolerance of 1 − I_APP ≤ 1e-2 and 1e-4, and F2/F3 beat F1 at 1e-2 but
lose at 1e-3, because the accumulator's finite chains leave a finite
good fixed point. RULED: PEXIT is a screen, never the verdict. Every
candidate carries two thresholds (tol 1e-2 and 1e-3); S1 keeps the
union of the top-N under each; S2's Monte Carlo on the production
decoder is the arbiter (the project's "analytics rank, never veto"). For F1 the
existing degree-profile GA-DE (`measure/rung-ladder/search/de_engine.py`,
`de_profile.py`: enumeration of three-class profiles, GA threshold,
local search, MC-DE re-score) stays as the fast enumerator; its
winners are placed into base matrices and re-ranked by PEXIT. Search
over profiles by enumeration plus local search (as the 2026-10-01
run), or differential evolution when the space is continuous
(F2 extension rows). Constraints: the stability condition on degree-2
fraction, no info-free check rows, every column degree ≥ 2 except
`parity_ext` and the accumulator end. Finite-length re-ranking by MC
is §3.4; DE ordering survived at ρ 0.66–0.98 last time, so DE keeps
N ≥ 8 candidates per family per rung.

FULL DENSITY EVOLUTION, MEASURED 2026-10-19 (`ladder2/lib/de_full.py`,
`de_full_kernels.py`; Wave B of §8.1): quantized DE on the protograph
(2¹¹ + 1 LLR points at step 0.04, FFT variable nodes, the
Richardson–Urbanke box-plus table at the checks, every nonzero base
entry an edge type, punctured columns from a delta at 0, renormalised
each iteration; (3,6) threshold −1.903 dB Es/N0 against the exact
−1.909, halving the step moves it < 0.01 dB) agrees with the loose
PEXIT threshold within ±0.02 dB on every code where no floor binds
(20 of the 35 S4 codes under the spec's "every info column < 1e-6"
criterion, 29 under the mean information-bit error rate). The rest are
DE FLOORS: an information column attached only to late accumulator
rows cannot fall below 2–5 × 10⁻⁶ (r0203's column 10), which the
criterion reports as a 0.2–1.4 dB worse threshold on a code whose
measured 1 % point is unmoved. NO predictor ranks codes within a rung:
mean within-rung Spearman against the measured es1 is 0.15 (PEXIT
loose), 0.25 (tight), 0.35 (DE spec) and 0.39 (DE mean), because es1
spans 0.01–0.10 dB inside a rung against ~0.02 dB of Monte Carlo
resolution — seven of eleven rungs carry no ranking signal at all.
Monte Carlo stays the arbiter; PEXIT stays the screen (its within-rung
residual is the smallest, 0.03 dB); full DE's use is a profile
OPTIMISER's objective and the floor diagnostic, and it costs ~150 cpu-s
per threshold at 2¹¹ points (60 % in the box-plus; a compiled kernel
owed before it screens hundreds of candidates).

### 3.3 Lifting: QC-PEG with ACE

Given a base-matrix support, choose each circulant shift by
progressive edge growth at block level: columns in non-decreasing
degree order (ties by a seeded permutation, recorded), each nonzero
block in turn, the shift chosen from [0, z) to maximise the local girth
of the lifted graph (cycle check = base-graph cycles whose shift sums
vanish mod z, enumerated up to length 2·d_ACE), subject to the ACE
constraint: every cycle of length ≤ 2·d_ACE through the new edge has
ACE ≥ η, ACE = Σ(deg − 2) over its variable nodes. Defaults d_ACE = 5,
η = 4 at R ≤ 0.55, relaxed to (4, 3) at high rate where density forbids
more; the literature pass fixes the defaults with its sources. Several
lifting seeds per base matrix; the MC screen picks. The structural
report records girth, the cycle counts at 4/6/8, and the ACE spectrum.

Accumulator span (added 2026-10-18 after the W2 refutation found a
weight-7 single-information-bit codeword in a girth-8, zero-violation
k 2240 lift): the ACE window cannot see words the accumulator closes
beyond the enumerated cycle length, so the lifter also enforces
pairwise DISTINCT shifts within an information column and keeps
information blocks out of the last block row (the weight-1 chain end)
for columns of degree ≥ 3 — a single-information-bit word then weighs
≥ 1 + Σ_i (mb − r_i) over the column's rows r_i — and runs the exact
pair-weight check (§3.7) as a post-lift gate: a lift whose single or
pair minimum is under the rung's bar re-places the offending blocks
with those shifts forbidden, a bounded number of times, and records the
attempts. Two bars exist (RULED 2026-10-19 after the c1-rank audit):
the LIFTER's gate bar, the knob that says how hard it re-places (16 /
12 / 10 by rate band, part of the lift's task identity), and the
planner's ACCEPTANCE bar over the recorded single and pair minima,
derived per rung from the union bound at the operating point — with
about z words at the minimum weight d the undetected rate at the 1 %
point is ≈ 64·Q(√(2·d·snr)); keeping it under 1e-4 needs
d ≥ 10.8/snr at Shannon + 0.8 dB (10.8 is 10.87 = Q⁻¹(1e-4/64)²/2
rounded down, which costs one weight at r0547 and r0469 — 15 and 19
where the exact constant gives 16 and 20; the one S4-measured code at
the bar, r0547's pair-15 rank-2, was refused by S4 anyway; and the 64
words are assumed at Z 32 too), clamped to [6, 24] — so about 6 at
r0906, 10 at r0703, 15 at r0547 and 24 from r0406 down. Both minima
must meet it and there is NO exemption for a support whose single-bit
bound is below it: the first campaign admitted free-mode lifts with
pair weights 7–13 through such an exemption while refusing bound-mode
lifts with 10–13 against a flat 16, and the blanket last-row-rule
variant was refused everywhere by the info-free-row check (the row it
empties), which makes it moot beside the bound mode that dominates it.
MEASURED 2026-10-19: the lifter's gate knob (16 / 12 / 10) sits BELOW
the acceptance bar from r0469 down (19–24), so the lifter stops
re-placing at a weight the planner then refuses — 532 gate-passing
lifts were refused by the bar (r0469 70, r0406 184, r0359 173, r0313
75, r0250 24, r0203 6); the knob should be max(gate bar, acceptance
bar) (docs/TODO.md).
THE TOP-RUNG FLOOR IS THE SUPPORT'S, NOT THE LIFT'S (measured
2026-10-19 in three steps; the records `ladder2/docs/SMALL-Z-2026-10-19.md`
and `LAST-ROWS-2026-10-19.md`). The codeword weight law on the block
dual-diagonal accumulator is exact (`ladder2/lib/families_span.py`,
0 mismatches against the encoder on every pair and on tens of thousands
of three- and four-bit words): a word weighs its message weight plus,
per accumulator lane, the GAP between two paired hits and the TAIL
(chain end − row) of every unpaired hit; a hit in the last block row
costs 1. So a single information bit of degree d weighs 1 + its d tails
(up to d·mb, not mb — the first version of this paragraph said "capped
by mb", which was the bound mode's bar of 10 at r0859 mistaken for a
cap; superseded), and the lightest PAIR words are, in 11 of 12 lifted
top-rung codes, words with at most two lane coincidences whose
unmatched hits sit in the last 1–4 rows — a SUPPORT property, which the
lift's shifts cannot change and a three-bit gate
(`lift_with_build(gate_triples=…)`, the lightest pairs' XOR with every
third information bit under the quasi-cyclic symmetry) can only
measure (+1 at best at r0859). Two levers follow: a smaller z gives
more rows per lane and raises the pair minima at k 3520 (+1–2) and
below (clearly), not at k 3712, where heavy columns cover every row;
and the SPAN RULE (`last_row_rule="span[N][l]"`: every information
column's span, the sum of its d − 2 smallest tails, ≥ σ) bounds every
≤ 2-coincidence pair word at 3 + 2σ by construction — a theorem under
girth ≥ 6 and the distinct-shift rule, 0 violations in 158,192
classified words — reaching pair and triple ≥ 10 on 7 of 8 codes at
k 3520 z 32 (σ 3) for +0.036 dB against z 32 bound codes and −0.006
against z 64 bound ones (the S4 floor there unmeasured), and at k 3712
only for 0.07–0.11 dB (§8.1 Wave C). What remains beyond both is the
≥ 3-coincidence shift words, which the gate can re-place, and the
CROWDING words of four light columns pairwise sharing one check (the K4
structure, weight 4 with 4 information bits at high σ), which no gate
sees yet (docs/TODO.md).
The last-block-row rule is a SUPPORT property and is W3's to enforce;
the lifter reports offending columns. PRICED 2026-10-18 (W3
refutation): with the rule on, the chain-end row holds only the last
two I(0) parity blocks, so the last parity block is a bitwise copy of
the previous one (z = 64 parity bits spent on a repetition at every
rung) and the PEXIT threshold worsens by 0.35 / 0.21 / 0.13 / 0.13 /
0.09 / 0.05 dB at k 3712 / 3520 / 3200 / 2880 / 2240 / 1280; with the
rule off the single-information-bit bound at k 3712 is 7 and the pair
bar of 10 is unreachable (0 of 8 lifts), while the weight-3-first
variant with the rule on clears it at every seed (pair 10–11). The
campaign measures all three variants; the choice is §9 R8.
Rung defaults: mb ≤ 14 (R ≥ 0.78) → (d_ACE 4, η 3, girth target 6);
otherwise (5, 4, 8). Ranking is girth first (never below target or the
achieved girth), then length-weighted ACE violations, then minimum ACE,
then count.

### 3.4 Selection pipeline per rung (S0–S4)

- **S0 structure.** Build; refuse any info-free check row, any degree-1
  column outside `parity_ext`/accumulator end, girth < 6; encoder check
  H·c = 0 on 64 random messages; digests. Seconds per code.
- **S1 threshold rank.** PEXIT threshold per candidate base matrix; keep
  the top N = 12 per family per rung (fewer when a family has fewer).
  As built (2026-10-19 audit): per (family, VARIANT), the union under
  both PEXIT tolerances, with backfill; Z 32 and Z 64 candidates share a
  group.
- **S2 quick screen.** For each kept base matrix, 3 lifting seeds; BIAWGN
  at 5 points spaced 0.1 dB around the predicted 1 % point, 500 trials
  per point, production decoder via the batched twin; Es/N0@1 % by
  log-linear interpolation; disqualify on any undetected decode. Keep
  the top 4 per rung plus the best of each family.
- **S3 confirm.** Fresh trials (t ≥ 20,000, never used in S2), 5,000
  trials per point on a 0.05 dB grid around the 1 % point, BIAWGN and
  BSC (0.0025 in p); the erasure side points (ε 0.3 and 0.5 at p 0.02,
  and the maximal ε at 0/200); the SP-200 intrinsic column (§5.3); the
  shortened p120 and p300 codes at their own 1 % points. Rank by the
  BIAWGN gap; ties (< 0.05 dB) broken by BSC gap, then by the §3.7
  floor evidence.
- **S4 acceptance** of the chosen code and the runner-up (§4). As built
  (2026-10-19): the top THREE of S3, no backfill — the third slot raises
  the chance of an accepted code at a rung, it does not guarantee one
  (four rungs ended with all three refused, §1.1).

Recorded deviations (2026-10-18, W5 as built and refuted): candidates
are generated and threshold-ranked first, and S0's structural checks
run on the lifts of S1's keep set (with backfill from the ranking when
a kept candidate's lifts all fail S0); S2 keeps the best lifting seed
per base matrix before taking the top 4 plus the best per family; S3
also disqualifies on any undetected decode in its BIAWGN, BSC or
shortened walks (SUPERSEDED 2026-10-19 by the rate rule, next
paragraph; S2's own any-decode rule still stands, see below); every
secondary walk (shortened, SP-200, 150
iterations) starts at a predicted point and walks coarse then fine, and
a walk that cannot bracket its target records why; the 150-iteration
column and the two 10⁵-trial acceptance points use fresh, disjoint
trial ranges; at r0859/r0906 the erasure REACH runs at p 0.005 and the
side points are recorded as beyond capacity (BSC 0.02 alone is above
capacity there); "byte-identical" results mean
timing-free rows compared as a set. The 60-iteration S3 number carries
the winner's curse of selection; S4's fresh 10⁵-trial BLER at the S3
point is the unbiased check and is reported beside it.

Recorded deviations of the campaign audits (2026-10-19): S1 keeps the
top N per (family, VARIANT), not per family — the best-threshold variant
had vetoed the others; the weight acceptance is the planner's rule over
the lifter's recorded minima (§3.3's two bars), so a changed bar
re-judges a ledger without re-lifting; the S3 undetected rule is a RATE
over the operating region (points at or easier than each walk's 1 %
point, bar 1e-3 — the whole-walk zero count had dropped every pick at
eleven rungs, and 2e-4 was counting noise at 35–60k trials that hid the
PBRL codes leading the low rungs by 0.3–0.5 dB); S4 measures the top
THREE of S3 against its 1e-4 bar, so a rung whose fastest codes fail
the floor still ends with an accepted code beside the measured
refusals; and a lift whose edge_sha equals an earlier lift's in the
same rung (a bound-rule and a free variant lift identically where the
rule places nothing differently) is recorded as `duplicate_of` and gets
no walk — c2-accept's first render had spent S2–S4 on eight such pairs
and published four "runners-up" that were the accepted code itself, and
its S4 "top three" was a top two at those rungs (the resumed campaign
filled the freed slots). Caveats the 2026-10-19 review attached to
these rules (measured on the c2-accept ledger, owed to the tooling,
docs/TODO.md): S2 still drops a spec on ANY undetected decode in its
walk, hard points included — 300 S0-passing specs went that way,
among them an F2 at r0250 0.15 dB faster than the best S2 pick and one
code each at r0859 and r0625 faster than every pick; the S3 rate is
counted over walk points that SHARE their trials (common random
numbers: one noise vector failing at up to six adjacent points counts
six times), so every S3 rate in this record is per point-trial and
only S4's two disjoint points are per-trial counts; an S3 counted walk
that ends unbracketed (floor, max_points) contributes nothing to the
rate (latent: none did); a candidate whose every passing lift is a
duplicate keeps its S1 slot with no walk and no backfill (236 slots
over the campaign); and S4's top three has no backfill, so a rung
whose three are refused ends empty (four did). Each of these was BUILT
later the same day behind a CampaignConfig flag — off for c1-rank and
c2-accept, whose plans are byte-identical, on for c3-search (§8.1 Wave
A): `s2_rule` "rate" with a Poisson tail test where a walk has few
operating-region trials (the refuter's M2: one event in 500 is 2e-3,
so a raw rate bar there was still "any decode"), distinct-trial S3
counts recorded beside the point-trial rate (the rate the bar uses:
the distinct rate is another estimator, a per-walk union probability,
not a uniformly stricter one — refuter M3), `s1_key_z`,
`s1_dead_if_all_duplicates`, `s4_backfill`, and the candidate-identity
mapping that lets a chained campaign with a larger candidate pool keep
the upstream campaign's lift and walk ids (the refuter's H1: the
candidate index was global across families, so a larger pool renamed
every F2/F3/F4 candidate).

### 3.5 Encoding

Systematic. With the parity part block lower-triangular, parity bit
blocks are solved in block-row order: `p_j = I(−s_jj) · (H_info,j · u +
Σ_{i<j} H_{j,i} p_i)` over GF(2); the block dual-diagonal accumulator is
the case H_{j,j−1} = I(0), i.e. z parallel prefix sums; `parity_ext`
bits are a single XOR each. The encoder is pure numpy, one function,
verified against H·c = 0 and against a dense GF(2) solve on small lifts
in tests.

### 3.6 Shortening

p furniture sites remove the last p information bits (known zero, not
printed): one full block column plus 56 bits at p120, four plus 44 at
p300. Design rule (amended 2026-10-18 per LITERATURE §7, as built in
W3): the info column ORDER is chosen so that the PEXIT thresholds of
the code shortened by its last 2 and by its last 5 block columns are
best, "lowest-degree last" being the fallback that wins ties; in
practice PEXIT puts the HEAVIEST class last at several rungs. Each
candidate records both shortened thresholds and the fallback's. S3
measures the shortened code at p120 and
p300; the record reports the shortened rate (k − p)/(4096 − p) and the
gap at that rate, beside the mother's.

### 3.7 Floor control and the undetected-error bar

- Pair weight: exhaustive two-information-bit codeword weights (the
  v1 `structure.py` method); counts kept for w ≤ 16 (`floors.PAIR_BAR`,
  the histogram cut-off the 2026-10-01 search's flat bar became); the
  acceptance bar is §3.3's per-rung bar.
- Three-information-bit words over the lowest-degree info columns
  (bounded enumeration), recorded.
- Error-impulse search (Hu–Fossorier–Eleftheriou; Berrou): inject
  impulses on single and paired variable nodes at a high-SNR operating
  point, decode, collect every syndrome-valid wrong decode's weight;
  report the minimum found and its count. This is an estimate of
  d_min from above, recorded, never claimed as d_min.
- Trapping-set census by NOISE at the operating point (fresh BIAWGN
  trials, seed base + t, chunkable) plus the (a, b) = (wrong bits,
  unsatisfied checks) of every impulse-search failure: the sets that
  stop the decoder at 60 iterations, counted by size; informs the
  lifting seed choice. (Amended 2026-10-18 after the W4 refutation: the
  first draft said "by impulse" alone.)
- Sized MC at the 1 % point and at +0.5 dB: 10⁵ fresh trials each on
  BIAWGN, undetected RATE at most 1e-4 at either point (§4.3; the first
  draft's "0 undetected" is the owner's stricter option, §9 R3); the
  ACE lifting and the §3.3 acceptance bar are what make this reachable;
  CRC-32 remains the backstop in production and is not credited in the
  bar.
- What the CRC makes of an undetected LDPC decode — MEASURED 2026-10-19
  (`ladder2/lib/crc_cover.py`, `python -m ladder2 crc-cover`): on holo's
  tile framing ([user | crc32_bits(user) | zeros(p)], zlib MSB-first) the
  CRC is affine, so its undetectable information patterns are exactly
  computable for small weights from the single-bit syndromes; every
  pattern of information weight ≤ 3 is detected at every rung, and every
  pattern of weight ≤ 4 wherever the transmitted information length
  k − p ≤ 3000 on this layout (r0781 at p300 and every rung below it;
  Koopman's HD-5 region ends at 2974 DATA bits, and holo packs the user
  bits into whole bytes, so the measured boundary here is n_user ≤ 2968,
  k − p ≤ 3000: None at 3000, a weight-4 pattern from 3001). Heavier
  patterns are caught with probability 1 − 2⁻³² each under the
  random-CRC MODEL — a heuristic, not a measurement: for a fixed code
  each recurring wrong codeword is caught every time or never, and the
  ledger stores the words' weights, not the words (docs/TODO.md). So a
  syndrome-valid wrong decode is a DETECTED tile failure (a lost
  attempt) except for a modelled ≤ 2⁻³² residue per heavy undetected
  decode — ≤ 1.3 × 10⁻¹³ per attempt at the largest S4 rate measured at
  the 1 % point (5.4e-4), and in production attempts × rate(regime) ×
  2⁻³², where the hard sub-threshold points of the S3 walks reach ~6e-3
  per trial (10⁶ retries there: ~1.4e-6 per volume). Behind it stand
  the fountain's consistency check and the envelope sha at close: a CRC
  miss surfaces in holo3 as a terminal integrity failure or a
  sha-failed close (`format/close.py`), which the analyzer's
  leave-one-out localization would have to resolve — never as a silent
  error. The undetected rate is therefore a BLER-accounting and
  code-quality number; the S3 walks and (since the review) the S4
  acceptance points record every undetected word's total and
  information weight (`undetected_weights`), measured on the
  unshortened code (p0).

### 3.8 What the previous search already settled (documented)

Balanced placement removes info-free rows (0 restarts in 36/36 configs);
three-class DE profiles beat the recipe at k 1216–1664 by 0.25–0.51 dB;
ARA partial precoding won at k 1216 by 0.01–0.1 dB; a pair-weight floor
of 10 is too low and 16 does not predict cleanliness (dirty finalists
3–11 of 15 per k) — hence §3.7's MC bar; seed spread ~0.03 dB against
configuration effects up to 0.5 dB; confidently-wrong LLRs at 0.5 % of
cells wreck every code alike (a decoder-axis matter, reported in §5
and not selected on).

## 4. Acceptance per rung (the gate)

A code enters `ladder2/codes/` only with all of the following, each a
deterministic check with its number recorded:

1. S0 passes; digests present; the build reproduces from `provenance`
   bit for bit (edge_sha equal) on a second machine or a second run.
2. S3 numbers on fresh seeds: Es/N0@1 % and @10 % (BIAWGN), p@1 % (BSC),
   erasure reach, SP-200 column, shortened p120/p300 columns.
3. Floor: the undetected-decode RATE at the 1 % point and at +0.5 dB,
   10⁵ fresh trials each, at most 1e-4 (ten in 10⁵: a lost attempt in
   ten thousand under CRC-32, three orders under the BLER target); the
   stricter "zero in 10⁵" is the owner's option (R3). AMENDED
   2026-10-19: the first draft said zero, and S3 was counting undetected
   decodes over whole walks including the hard points, which dropped
   every pick at eleven rungs (25–627 over ~100k trials); S3 now counts
   only at points at or easier than each walk's 1 % point, bar 1e-3
   (2e-4 first, which was counting noise at 35–60k trials). S4 runs on
   the top THREE of S3, so a rung keeps an accepted code beside the
   refusals of its faster codes. MEASURED (c2-accept, 2026-10-19): the
   bar refuses 22 of 35 measured codes at 11–54 undetected per 10⁵ at
   the 1 % point against ten allowed (11–50 at the four rungs it leaves
   empty), 0–15 at +0.5 dB — the union-bound acceptance bar of §3.3
   admits codes at the 1e-4 edge by construction; the price per rung
   and what the CRC makes of those decodes (§3.7) are in §9 R3.
   Pair weight and the §3.7 minimum found weight are recorded beside
   the per-rung acceptance bar (§3.3), which is the one weight rule.
4. Iteration sensitivity recorded: Es/N0@1 % at 60+SP60 (production),
   at 150+SP150 (the retry tier), at SP-200.
5. Decoder bit-exactness: the batched twin against `holo.core.ldpc.decode`
   on 1,000 decodes of this code (channel LLRs and extrinsics), 0
   mismatches; punctured codes included.
6. The runner-up kept with the same record, so a later ruling has a
   second choice without re-running the campaign.

Bars are expectations for ranking; the only hard refusals are 1, 3's
undetected-rate bar, and 5.

## 5. Channels, decoders, metrics (comparable to the 2026-09-30 study)

### 5.1 Channels (seeded, `ladder2/lib/channels.py`)
BSC(p): hard LLR ±log((1 − p)/p). BIAWGN(Es/N0): x = 1 − 2c, y = x + σz,
LLR = −2y/σ², σ² = 1/(2·Es/N0) — the HOUSE sign, positive = bit 1, as
`decode.py`, `tile.py` and the harness use it (W1 deviation 4).
Erasure(ε)+BSC(p): LLR 0 on the erased fraction; at p = 0 the hard
magnitude is the production clip 20, not infinity. Confidently-wrong(f):
a fraction f of cells at ±20 with the wrong sign, reported only. Common random numbers across grid points
within a code (trial t uses seed base + t), fresh bases for S3/S4
(t ≥ 20,000).

### 5.2 Decoders
Production: `holo.core.ldpc.decode` (normalized min-sum α 0.8, 60
iterations, early exit, one exact sum-product retry of 60, clip ±20).
Batched twin: `fastdecode.decode_batch`, bit-exact to production,
re-verified per new structure (§4.5). Reference: exact sum-product, 200
iterations, the "intrinsic" column.

### 5.3 Metrics
BLER at a point = failures/trials (a failure is any decode whose hard
decision ≠ the codeword, undetected ones counted separately). Es/N0@1 %
(and p@1 %) by log-linear interpolation between the bracketing grid
points. Gap dB = Es/N0@1 % − Shannon(R), R = k/4096 for the mother; gap
bit = (1 − H(p@1 %)) − R. Undetected rate = syndrome-valid wrong decodes
/ trials. Every table carries trials per point and the seed base.

### 5.4 Finite-length bound
The normal approximation (Polyanskiy–Poor–Verdú) at n = 4096 (and at
4096 − p for shortened rows), ε = 0.01: R* = C − √(V/n)·Q⁻¹(ε) +
log₂(n)/(2n); the BIAWGN dispersion V computed numerically. Reported per
rung as the Es/N0 where R* = R, so each code's gap to the bound is one
number beside its gap to Shannon.

## 6. Resumable campaigns

Everything expensive runs as a campaign of tasks under
`ladder2/runs/<campaign>/` (gitignored):

- A task is a pure function of its spec (code id, channel, point, seed
  base, trial range, decoder); its id is the sha256 of the canonical
  spec. Results are appended, one JSON line per task, to
  `results.jsonl`; the done set is rebuilt from that file at start, so a
  rerun is a resume. Stage boundaries (S1 → S2 → S3 → S4 selections) are
  recomputed from results on every start, deterministically, so a
  partial stage resumes without a planning file.
- MC work is chunked: ≤ 1,000 trials per task with its own seed base,
  so a shutdown loses one chunk per worker. Trial ranges are disjoint
  by construction (chunk index × chunk size).
- Workers: `multiprocessing` spawn processes (never threads; the
  numpy/Accelerate rule), `--workers N` default cpu − 2, each worker
  caches codes and decoder layouts.
- Stop: SIGINT/SIGTERM finish the running chunks and exit with status
  "stopped" (exit 0); `--max-minutes M` stops at a boundary; a lock
  file refuses a second runner on the same campaign.
- Commands: `python -m ladder2 campaign plan|run|status|report <name>`
  (`--runs`, `--workers`, `--max-minutes`, `--seed`, `--publish-to` are
  campaign flags), `ladder`, `spec show <path>`, `crc-cover`;
  `run` is idempotent; `status` prints per-stage done/total, failed
  tasks, and the elapsed and remaining CPU estimate from the chunk
  rates seen; the log goes to `runs/<campaign>/log.txt` and stderr.
- Laptop note (README): `caffeinate -i` around `run`; on wake the runner
  continues the same process; after a shutdown, `run` again.

## 7. Tooling layout, reuse, tests

```
ladder2/
  README.md          operator manual (commands, the campaign names, the laptop rule)
  __init__.py  __main__.py            python -m ladder2 …
  lib/spec.py        CodeSpec v2, JSON I/O, digests, the ladder table (§1), token law
  lib/base.py        base matrix -> bit-level edges, roles, shortening, block adjacency for W2
  lib/cycles.py      girth, cycle counts, ACE spectrum (brute force on the lift + the QC shift-sum method) — W2
  lib/encode.py      systematic block back-substitution encoder, H·c = 0 check
  lib/adapt.py       -> holo.core.ldpc.construct.Code (production decode, batched twin), punctured LLRs
  lib/channels.py    §5.1 channels, capacity points (§1), normal approximation (§5.4)
  lib/decoders.py    production / batched / SP-200 behind one interface; bit-exactness check
  lib/de.py          PEXIT on base matrices; the GA-DE profile enumerator imported from measure/rung-ladder
  lib/families.py    F1/F4 candidate base matrices from profiles (the F1 → F3 hand-off)
  lib/families_punct.py  F2 (PBRL) and F3 (punctured XOR-state nodes)
  lib/families_pbrl.py   F2's single-bit weight law and the `weightn` placement rule (Wave D)
  lib/families_span.py   the span rule on the block accumulator (last-row law, LAST-ROWS-2026-10-19.md)
  lib/families_place.py  lib/families_cap.py  placement helpers; the small-z row-pair cap
  lib/families_ara.py    F5, the ARA precode family (a measured negative, opt-in only)
  lib/families_rank.py   candidates_for_rung: the per-rung candidate list over every family
  lib/families_driver.py the per-rung driver behind families.py (split for the line cap)
  lib/peg.py         QC-PEG + ACE lifting (§3.3), the pair / triple / multi-bit word gates
  lib/peg_repair.py  the seeded 4-cycle repair below z 64 (SMALL-Z-2026-10-19.md)
  lib/floors.py      pair weights, 3-bit words, error impulse, trapping-set census (§3.7)
  lib/floors_triples.py  the three-bit word scan behind the triple gate
  lib/floors_words.py  lib/floors_words_mitm.py  the multi-bit low-weight word search (Wave D)
  lib/de_full.py  lib/de_full_kernels.py  full density evolution on the protograph (Wave B)
  lib/crc_cover.py   the production CRC-32's exact cover of low-weight information patterns (§3.7, R3)
  lib/mc.py          BLER at points, interpolation, the coarse-then-fine walks, erasure reach
  lib/jobs.py        the resumable runner (§6)
  lib/candidate.py   the Candidate shape W3 produces and W2/W5 consume
  lib/campaign.py    run / status entry points; the S0–S4 campaign is the campaign_* family:
  lib/campaign_config.py   CampaignConfig (every count a field; smoke / c1-rank / c2-accept)
  lib/campaign_plan.py     the planner: stages recomputed from results on every start
  lib/campaign_select.py   the pure selection rules (S1 keep + backfill, S2, S3, S4 verdict)
  lib/campaign_tasks.py    what a worker runs (cands, s0 lift, bler, floors, bitexact, reproduce)
  lib/toy.py         hand-made F1-like toy specs (smoke campaigns and tests)
  lib/report.py      TABLES.md, per-rung candidate tables, the ladder table, a campaign's own codes
  lib/leaderboard.py the best code per rung across campaigns; rank v1–v4 (§1.2)
  lib/final.py       the rung final: every near-tied contender at one Es/N0 on one fresh range (§1.2)
  lib/publish_set.py the named published set: selection, provenance, MANIFEST.json, CODES.md, check_set
  lib/verify_set.py  the published files on fresh seeds (VERIFY.md)
  tests/_l2_toy.py   the tests' toy helper (make_toy_spec, gf2_solve)
  tests/test_l2_*.py (globally unique basenames; lane: env/bin/python -m pytest ladder2/tests -q)
  codes/             THE PUBLISHED SET (SET-1, §1.2): code files, MANIFEST.json, CODES.md, VERIFY.md — written only by publish-set
  results/           THE TRACKED RECORD, self-sufficient: per campaign TABLES.md (every candidate's row),
                     acceptance/ (one JSON per S4-measured code: every S2/S3/S4 number, the verdict),
                     specs/ (that code's lifted CodeSpec, so any S4 code can be republished without runs/);
                     final/ (the rung final's plans, chunks and rows); LEADERBOARD.md
  runs/              gitignored campaign state (ledgers, candidate lists, every lifted spec); needed only to
                     RESUME or CHAIN a campaign or RE-JUDGE a stage — the record above regenerates from it
                     and stands without it. ARCHIVED 2026-10-24 (the owner: "bring it into scratch2") as
                     scratch2/ladder2-runs-20261024/ladder2-runs.tar.xz in the main checkout (README there:
                     contents, provenance, digest, restore); gitignored like every scratch2/ evidence tree
  docs/LITERATURE.md the literature pass
```

Reuse (read before writing): `measure/rung-ladder/search/fast/fastdecode.py`
(the batched decoder; its `_layout` must accept the v2 Code), `de_engine.py`
(GA-DE, the phi table), `de_profile.py` (profile enumeration and local
search), `common.py` (`edge_sha`, the interpolation and frontier walk, the
task/jsonl conventions), `variants.py` (ARA assembly with punctured
nodes, `pair_weights`), `harness/structure.py` (pair weights),
`harness/channels.py`. Port by import where the module is importable
under `PYTHONPATH=src:.`; copy a function only when its module drags the
search's globals, and say so in the docstring.

Conventions: Python ≥ 3.11, type hints, ≤ 1000 lines per file (split
along a seam, never trim), units in names (`esn0_db`, `p_flip`,
`n_trials`), every RNG seeded explicitly, no `Date.now`-style
non-determinism in task ids, pure functions where possible. Tests are
unit and narrow: expansion against a dense construction on a 2×3 base
at z = 4; encoder against a GF(2) solve; girth on a graph with a known
4-cycle; PEXIT reproduces the regular (3,6) BIAWGN threshold (σ* ≈
0.8809, 1.1 dB) within 0.02 dB; the batched twin bit-exact on a v2 code;
the runner: kill mid-run, resume, byte-identical results.jsonl; the
production decoder and the batched twin agree on a v2 code (§4.5).

## 8. Workplan

| wave | deliverable | done when | builder / review |
|---|---|---|---|
| W0 | this document; branch + worktree; `ladder2/docs/LITERATURE.md` | literature file in, design amended with its "adopt" list | owner-model design; Opus reader (web) |
| W1 | `spec`, `base`, `encode`, `adapt`, `channels`, `decoders` + tests; a hand-made v2 code at k 2240 decodes under production and the batched twin bit-exactly | lane green; capacity table of §1 reproduced | Opus builder; Opus refuter |
| W2 | `cycles` + `peg` (QC-PEG + ACE) + tests | girth/ACE verified against brute force on small lifts; a k 2240 F1 lift at girth ≥ 8 | Opus builder; Opus refuter |
| W3 | `de` (PEXIT), `families` (F1–F4) + tests | (3,6) threshold reproduced; every family yields S0-passing candidates at every rung | Opus builder; Opus refuter |
| W4 | `floors` + tests | finds r0550's weight-6 pair word; impulse search reproduces a planted low-weight word | Opus builder; Opus refuter |
| W5 | `jobs`, `mc`, `campaign`, `report`, CLI, README + tests | kill/resume test; a smoke campaign on two rungs end to end | Opus builder; Opus refuter |
| W6 | conventions + docs consistency pass | no finding open | Sonnet checker |
| C1 | campaign `c1-rank`: S0–S2 over twelve rungs | TABLES with top-4 per rung | runner, no agents |
| C2 | campaign `c2-accept`: S3–S4 on the C1 winners | twelve accepted codes + runners-up (since 2026-10-20 in `results/c2-accept/codes/`), acceptance JSON | runner, no agents |
| W8 | record: this document to the measured state; `CODES.md`; FEC-DESIGN pointer; one review pass | review dispositions written | owner-model record; Opus reviewer |

Status 2026-10-19: W0–W6 done 2026-10-18 (every wave Opus-built and
Opus-refuted, the refutations' findings in §3.3/§3.4/§3.7 as amended);
C1 (`c1-rank`) done 2026-10-18/19 — 4,116 lifts and 19,181 S2 walk
tasks in its ledger, 9.6 M decodes — and re-judged under the planner's
acceptance bar (`ladder2/results/c1-rank/TABLES.md`; the pre-audit
tables kept as `results/c1-rank-baseline/`); C2 (`c2-accept`) done
2026-10-19 — 20,707 tasks and 20.4 M decodes over four runs at 740–870
decodes/s on 14 workers (8.4 M under the first S3 rule, 7.4 M under the
rate rule, 3.9 M after the duplicate-lift fix, §3.4), 0 failed;
`results/c2-accept/` (with its codes) is the record; W8 = this
revision, reviewed 2026-10-19 (`docs/reviews/ldpc-ladder-v2-2026-10-19/`,
every finding dispositioned there).

### 8.1 The search program (from 2026-10-19)

The owner's directive after W8: "find me as close to best possible codes
at the rungs … strong error correction, efficiently decoded tiles. The
better, the better. You have time to find them, as long as things move
forward." The program that follows is the standing work of this line;
`ladder2/results/LEADERBOARD.md` (`python -m ladder2 leaderboard
--write`) is its one artifact — the best S4-measured code per rung
across every campaign, ranked by rank v3 (§1.2: the rung final's
unbiased 1 % BLER Es/N0 under the production decoder, ties within
0.01 dB to the cleaner fresh floor, then to fewer iterations at one
common Es/N0), shown under both floor rules (§9 R3's as-built "a" and
the post-CRC-priced "b": ≤ 5e-4 at the 1 % point, ≤ 1e-4 at +0.5 dB) so
the ladder the owner would publish under either is one table; ★ marks
the published codes. Objective: lowest Es/N0@1 % (BIAWGN, 60 + SP 60)
per rung; floors as a constraint under the ruled bar (until ruled, both
are shown), judged on S4's and the rung final's counts pooled; decode
iterations at a common Es/N0 as the last tie-breaker and a reported
cost; the BSC and erasure columns recorded, not optimised. Every
campaign is resumable and chained on its predecessors' ledgers so
measured rows are never re-run; only `publish-set` writes
`ladder2/codes/` (SET-1, the owner's working set, §1.2), and a new
campaign's contenders enter through the rung final before a
republication.

- **Wave A — the planner's debts and the floor-first lifter (built
  2026-10-19, campaign `c3-search`).** The four planner debts of the W8
  review repaired (S2's operating-region rate, distinct-trial S3 rates,
  Z in the S1 key, all-duplicate candidates dead for backfill) plus S4
  walking down the ranking; the lifter's gate raised two weights above
  the acceptance bar and extended to three-information-bit words (the
  refused codes' undetected words at r0859 weigh 7–13 with 1–3 info
  bits, below the recorded pair minimum of 9 — words the single/pair
  gate never saw) for three additional lift seeds per candidate; twice
  the candidates, a wider S1 keep, Z 32 tried at the top four rungs.
  c3-search chains on c2-accept → c1-rank, so only the new lifts, their
  S2 walks and the changed S3/S4 picks decode. LAUNCHED 2026-10-19 14:12
  on machine 4 (14 workers), STOPPED at 14:16 after its candidate round
  when the planner's refuter showed the larger candidate pool renamed
  every F2/F3/F4 candidate (the index was global across families — 90
  cpu-hours of c1/c2 rows would have been re-measured), RELAUNCHED at
  15:12 on the repaired planner (6157d84b: candidates mapped onto
  upstream rows by digest; the S2 rate rule a Poisson test; lever lifts
  with their own spec names). Measured before launch: the three-bit gate
  finds the floor words but buys +1 at most at r0859 — the floor there
  is the support's (§3.3), so the top-rung lever moved to
  Wave C's small z.
- **Wave B — full density evolution (BUILT and measured 2026-10-19;
  §3.2).** `ladder2/lib/de_full.py`: quantized DE on the protograph,
  validated on the (3,6) ensemble; on the 35 measured S4 codes it
  equals PEXIT within ±0.02 dB wherever no DE floor binds, and no
  predictor ranks codes within a rung (es1 spreads 0.01–0.10 dB there,
  at the Monte Carlo's resolution). So the threshold is NOT where the
  remaining gap lives: the gap to the normal approximation is finite-
  length and decoder, which the lifting (girth/ACE/floors, more seeds —
  c3-search), the small-z structure (Wave C) and the decoder budget
  (R6) address. A DE-optimised profile campaign is parked until a
  compiled box-plus kernel makes DE a screen (docs/TODO.md); DE's
  floor diagnostic (an info column held above 1e-6 by its accumulator
  attachment) joins the candidate record.
- **Wave C — small z at the top rungs (BUILT and measured 2026-10-19,
  `ladder2/docs/SMALL-Z-2026-10-19.md`), then new families.** The
  lifter now reaches girth ≥ 6 at z 32 and z 16 on every top-rung
  support but one (a seeded min-conflicts 4-cycle repair after the
  greedy, `ladder2/lib/peg_repair.py`, adopted only when it clears
  every 4-cycle; a row-pair cap in the F1/F4 placement below z 64; z 64
  lifts byte-identical). MEASURED on the c1-rank candidates: at k 3520
  z 32 the pair minimum gains +1–2 (9–10 against 8) and the waterfall
  costs nothing (500-trial check); at k 3200 and 2880 z 32 gains
  clearly (pairs 12–17 against 10–13); at k 3712 the minima do NOT move
  (pair 6–7 at every z: the lightest pair is two degree-3 columns with
  a block in the last accumulator row whose checks land on the same
  lane twice — more rows do not help when the support puts heavy
  columns on every row), so the k 3712 floor needs a SUPPORT rule on
  the last rows, not a smaller z. z 16 lifts cost 9–133× z 64 and buy
  nothing at the top: dropped there. c3-search's lever seeds re-lift
  z 32 at the four rungs with the repair (`lift_repair_iters`, its own
  task identity; the runner was restarted 19:08 for it).
  THE SPAN RULE (built and measured the same evening,
  `ladder2/docs/LAST-ROWS-2026-10-19.md`): the codeword weight law on
  the block accumulator is exact — a word weighs its message weight plus,
  per lane, the gaps between paired hits and the tails of unpaired ones
  (a hit in the chain-end row costs 1) — and the lightest pair words of
  the bound-mode codes are, in 11 of 12 lifted codes, words with at most
  two lane coincidences whose unmatched hits sit in the last 1–4 rows.
  The rule `last_row_rule="span[N][l]"` requires every information
  column's span (the sum of its d − 2 smallest tails) to reach σ, which
  bounds every ≤ 2-coincidence pair word at 3 + 2σ by construction (0
  violations in 158,192 classified words). MEASURED (8 full-effort
  candidates per cell, 5 × 1,000-trial walks): at k 3520 z 32 span 3
  gives pair and triple ≥ 10 on 7 of 8 codes (pair 10–12, triple 9–14)
  at −0.006 dB against the z 64 bound codes and +0.036 against z 32
  bound, 0 undetected in 40,000 walk trials — the S4 floor itself is
  unmeasured (c4-top's question); at k 3712 no setting reaches pair ≥ 10 and
  triple ≥ 10 on all eight codes within 0.05 dB (the cheapest: z 32
  span 6 at +0.07–0.11 dB; single codes do, best-of-eight at 1,000-trial
  resolution, an S3 walk owed), and a CROWDING floor appears at high σ
  (4–8-information-bit words of weight 4–9, the K4 structure of four
  degree-3 columns pairwise sharing one check; a crowding check is
  unbuilt, docs/TODO.md). Campaign `c4-top` (k 3712/3520, the three
  span variants, every lift at bar 12 with the three-bit gate and the
  z 32 repair) runs after c3-search. The wave's Opus refuter
  (2026-10-20 night) found and the builders repaired: an absent repair
  key had meant "repair on" (old ids would have re-lifted differently —
  now absent = the pre-repair lifter, pinned); the row-pair cap sat
  outside the cands call's identity (c3-search's k 3712 z 32 list had
  run uncapped — the cap is in the id where a campaign asks for it,
  `cands_pair_cap`, and the reproduce spec copies the producing call's
  cap); the three-bit scan's bar + 2 cut missed the r0859 word it was
  built for (the recorded minimum is `triple_min_found` over a stated
  cut, and `triple_cut` is a lever, 18 for c4-top); the span rule with
  weight-3-first recorded a false bound (refused); cap params were
  written for unchanged supports (now only when the cap changed the
  placement); and the §3.3 "capped by mb" paragraph was the bar
  mistaken for a cap (rewritten on the weight law). c3-search was
  restarted 01:40 on the repaired tree.
  **c3-search DONE 2026-10-20 12:05** (25 rounds, 40,144 tasks, 25.8 M
  decodes, 0 failed; `ladder2/results/c3-search/`, its own codes under
  `codes/` there; at that time the published set in `ladder2/codes/` was
  still c2's — SET-1 replaced it on 2026-10-20, §1.2). Against the
  as-built bar it FILLS r0859 —
  a z 32 lever lift at 0.715 dB and 3 / 0 undetected (0.032 dB faster
  than c2's refused best; the leaderboard prefers its sibling at 0.732
  dB and 7 / 0 for 18 % fewer iterations) — and r0313 (F3 at 1.201 dB,
  4 / 0, against the refused 1.316), improves r0359 (1.147 vs 1.182) and
  r0250 (1.402 vs 1.444), matches r0203 and r0469, and leaves r0625
  (best 0.817 dB at 18 / 4) and r0406 (1.007 at 12 / 2) EMPTY; at r0906
  its z 32 codes are 0.04 dB faster but read 12–14 per 10⁵. Lessons
  (docs/TODO.md): with 24 candidates and six seeds the S2 top-4 cut
  dropped c2's accepted r0547 code before S3 (c3's own r0547 walked its
  backfill down to an F2 at 1.227 dB — the leaderboard across campaigns
  keeps c2's 0.873), so `s2_keep` must scale with the pool and the S4
  backfill needs a dB cap.
  **ARA — BUILT AND MEASURED 2026-10-20, A MEASURED NEGATIVE**
  (`ladder2/lib/families_ara.py`, family F5, admitted only when a
  campaign names it; the record `ladder2/docs/ARA-2026-10-20.md`,
  instruments and rows `measure/ladder2-ara/`): a rate-1 block-
  accumulator precode over punctured state columns (P = f·kb of the
  information columns, f ∈ {0.25, 0.5, 1}) in the pure-QC CodeSpec —
  the encoder needed nothing new, the batched twin decodes it bit-exactly
  (n_bits up to 7,616; the price is iterations, not memory). It does not
  buy floor, and the reason is structural: the precoder maps the
  weight-2 input of adjacent chain blocks on one lane to ONE state flip,
  so every IRA-stage word on state columns returns with at most one
  extra printed bit per state — nothing is spread. Measured: at r0625
  +0.04–1.0 dB with its own 8-bit words; at r0859 +0.27 dB at 4–5× the
  iterations; at r0406 the full-ARA degree-3 variants sit −0.02…+0.11 dB
  from the F3 code at +1–24 % iterations but carry 3–6× its undetected
  share (16–23-bit words with 1–6 information bits); one f 0.5 lift is
  clean in 30,000 trials where its sibling is not — a lift, not a
  family, property. Not pursued further.
  **c4-top DONE 2026-10-20 14:11** (11 rounds, 4,837 tasks, 3.6 M
  decodes, 0 failed; `ladder2/results/c4-top/`): the span rule gives
  r0906 its first code with NO undetected decode in 2 × 10⁵ trials —
  0.843 dB (z 32 span, pair 12), 0.03 dB behind c2's accepted 0.814 at
  5 / 0 — and r0859 a 0.754 dB code at 3 / 0 (c3's 0.715 / 0.732 lever
  lifts stay faster). So at the top two rungs the ladder now holds
  clean codes under the as-built bar, the price of the cleanest being
  0.03 dB at r0906; adoption is the owner's.
  **c5-mid DONE 2026-10-20 18:29** (15 rounds, 8,550 tasks, 5.7 M
  decodes, 0 failed; `ladder2/results/c5-mid/`): the last two rungs are
  FILLED under the as-built bar — r0625 by a z 32 bound-mode lever lift
  at 0.816 dB and 1 / 1 undetected (c3's best had read 18 / 4 at 0.817:
  the floor moved with z, the waterfall did not), r0406 by a z 32 F3
  span lift at 0.997 dB and 6 / 4 (its sibling 1.003 at 9 / 0 is the
  leaderboard's pick for 6 % fewer iterations). EVERY RUNG of the
  ladder now holds an accepted code under the as-built bar
  (`ladder2/results/LEADERBOARD.md`, five campaigns); what remains is
  the owner's adoption per rung and the levers below.
  STILL OPEN in this wave: a 5G-NR BG2-pattern protograph as reference;
  the decoder budget at the bottom three rungs as a decoder ruling (R6).
  (PBRL at the bottom and the crowding check: Wave D.)
- **Wave D — the corrected metrics and two floor levers (built
  2026-10-20/21, after the owner's "improve the rung codes according to
  the correct metrics").** Four Opus builders, each refuted by an Opus
  refuter and fixed where the refuter held:
  (1) the METRICS — rank v3 and the rung final (§1.2; SET-1 republished
  under them 2026-10-21, six rungs moved);
  (2) the PLANNER — `s2_keep_frac` / `s2_keep_within_db` (S2 keeps
  ceil(frac × pool) or every code within the dB window; calibrated on
  c3-search, where 1/3 would have kept c2's r0547 code at rank 18 of 52
  — and doubled that campaign's S3 cost), `s4_backfill_max_db` (the S4
  walk skips codes more than the cap behind the S3 best; the refuter
  found the first version stopped at the first over-cap code although
  the S3 ranking is not monotone inside its tie band — repaired);
  (3) the MULTI-BIT WORD SEARCH and its lift gate
  (`ladder2/lib/floors_words.py`, `floors_words_mitm.py`; record
  `measure/ladder2-floor-words/`): codewords of up to t_max light-column
  information bits below a weight, found in check space on the exact
  accumulator weight law (exhaustive on F1/F4 and on F3 words that flip
  no state bit; one orbit per QC class), MEASURED: every recorded S4
  undetected decode (1,294) regenerated from its trial index — 78 % carry
  3–8 information bits, the crowding structure — and 342 of 342 in-scope
  S4 words found by the search; its union estimate ranks the 82 S4 floors
  with Spearman 0.865 (pooled; 0.75–1.00 within rungs) where the pair
  weight's pairwise error ranks them at 0.49. The gate
  (`lift_gate_words`, bars `word_bar_for`: 7 8 11 14 17 21 25 30 34 40
  51 62 from r0906 down, from the measured 1 % offsets and a 1e-5 target)
  re-places attempts with a word below the bar: at r0906/r0859 every
  gated lift met it (12 of 12), the union estimate fell 17–56 % (median),
  +60–180 s per lift; below r0406 the bar is a support property shifts
  cannot reach and the gate optimises only (estimate × 0.4);
  (4) PBRL's single-bit floor (`ladder2/lib/families_pbrl.py`,
  `f2_rule`; record `measure/ladder2-pbrl-weight/`): the exact single-
  information-bit weight law of the PBRL core and extension (equal to the
  encoder on 3,554 of 3,554 columns) and a placement rule (`weightn`:
  core-parity feeds at the chain end where the pair-target needs them,
  targets 93 / 74 / 58 / 49 / 42 at k 832 … 1664; ruled F2 lifts gate at
  the target); MEASURED at z 64 on fresh paired trials against the
  published codes: r0203 −0.47 dB, r0250 −0.22, r0313 −0.17, r0359
  −0.13, every confirmed pair-target code 0 undetected in 4,000 — a
  screen, not S4 (the floors need 10⁵ trials).
  **c6-low DONE 2026-10-23** (r0625 … r0203 under (2)–(4): 26 rounds,
  62,353 tasks, 40.8 M decodes, 0 failed, 487 cpu-h of lifting — the
  word gate makes a z 32 lift 7–10 min; `ladder2/results/c6-low/`): the
  ruled PBRL codes hold the bottom four rungs of SET-1 on the rung
  final (§1.2: −0.14 / −0.16 / −0.21 / −0.42 dB at r0359 / r0313 /
  r0250 / r0203, at a third to a half of the iterations), three middle
  rungs moved to cleaner codes inside the tie window, r0547 did not
  move. **c7-top DONE 2026-10-24** (r0906 … r0703 under the word gate:
  12 rounds, 27,467 tasks, 21.6 M decodes, 0 failed;
  `ladder2/results/c7-top/`): no top-rung code beats the published one
  beyond the tie window — the top four rungs sit 0.40–0.46 dB above the
  finite-length limit and the gate's clean lifts buy floors, not dB;
  r0781 and r0703 moved to c7-top codes on the pooled floor (§1.2).
  **c8-low DONE 2026-10-24** (the owner's go: PBRL only, z 32, the
  span3 variant, sixteen candidates all kept, six seeds under the word
  gate to eight information bits, r0469 … r0203, chained on c7-top; 12
  rounds in three runs — paused and resumed at 6 then 14 workers at the
  owner's request — 6,044 tasks, 0 failed, 12.6 M decodes;
  `ladder2/results/c8-low/`): behind at r0469–r0313, ahead at r0250 /
  r0203 by 0.08 / 0.06 dB at the floor bar's edge (§1.2).
  STILL OPEN after Wave D: the top rungs' remaining gap is the
  finite-length price plus the decoder's (R6); at the bottom the FLOOR
  BAR binds — the fastest z 32 PBRL codes fail it by 2–5 counts and the
  published ones sit on it — so the next lever there is a floor lever
  for PBRL at z 32 (z 32 halves the accumulator tails the pair target
  prices; neither it nor the word gate reaches the words that fail S4)
  and R3's ruling on the bar itself; the decoder budget (0.12–0.35 dB
  at r0313–r0203) stays a decoder ruling.
- **THE SEARCH STOPPED 2026-10-24 (the owner: "for now, I think we
  should stop the search").** Every rung sits 0.40–0.66 dB above the
  finite-length bound; lifting is saturated at the top (c7-top) and the
  bottom is floor-bound (c8-low); the remaining known levers are the
  decoder budget (a decoder ruling, R6) and the format (a longer tile or
  a different inner code, §10). The one measurement parked for the
  record is the 5G BG2 reference (docs/TODO.md). The branch was closed
  out the same day: the tracked record made self-sufficient (every S4
  code's spec under `results/<campaign>/specs/`, `publish_set.spec_path`
  falls back to it, a test pins it), the c1-rank / c2-accept reports
  regenerated by the current report code (two annotation keys added per
  walk, no number moved), the published set refrozen on them.
- **Each wave ends** with the leaderboard regenerated, this section's
  status line, and the owner's adoption call per rung (§9 R3 and R2
  stand until ruled).

W2–W5 run in parallel after W1 (disjoint modules; W5 stubs the
interfaces it needs from W2–W4 and the smoke campaign waits for them).
Each builder gets this document, the literature file, the reuse list,
and a bounded module list; each refuter gets the diff and the tests and
is asked to refute, not to approve. Model tiers per
`.claude/rules/workers.md`: builders, refuters, the literature reader
and the final reviewer Opus; the conventions pass Sonnet; nothing on the
session model but the design and the record.

Cost estimate (inferred from the 2026-10-01 run's 350–850 decodes/s on
14 workers): C1 ≈ 12 rungs × ~40 lifted candidates × 5 points × 500
trials ≈ 1.2 M decodes, 1–2 h; C2 ≈ 12 × 5 codes × (8 points × 5,000 +
shortened and SP-200 columns) + 24 × 10⁵ acceptance ≈ 5 M decodes,
4–8 h. Both resumable.

## 9. Rulings owed to the owner

- **R1 Z — RULED 2026-10-18** (owner: "i don't actually care what z is.
  my metrics is around decode quality and decode cost, you have freedom
  to choose z so those are optimized"). Z is a per-rung property of the
  frozen code data (the JSON carries it; nothing printed, placed or
  addressed depends on it; decode cost is the edge count and the
  iterations, not Z). The search runs Z ∈ {64, 32} where the block-row
  geometry binds (the top three rungs, plus one middle rung as a
  control) and picks per rung by the measured waterfall, floor and
  decode cost; the pick records z beside k.
  MEASURED 2026-10-19 (§1.1): Z 32 wins r0781 — a waterfall tie with
  the Z 64 free variant that the BSC tie-break gave to Z 32 and S4
  settled by refusing the Z 64 code (18 / 5), confounded with the
  last-row variant (the bound Z 64 code reads 0.751) — and places
  nothing at r0703, where only five live Z 32 candidates were screened
  because Z shares the S1 keep with Z 64; Z 64 everywhere else; the top
  two rungs untested at Z 32 (docs/TODO.md).
- **R2 Punctured state nodes.** Allowed, ≤ 128 per code (F3). They cost
  the later receiver one array shape and LLR-0 handling; refuse if that
  is unwanted, and F3 is dropped from the final pick. PRICE (§1.1): F3
  is the published code at every rung from r0547 down; striking it
  leaves F1's best there at 0.874 / 0.950 / 1.117 / 1.138 / 1.370 /
  1.526 / 1.761 dB (r0547 … r0203) against F3's 0.873 / 0.929 / 1.007 /
  1.182 / 1.316 / 1.444 / 1.675 — within 0.11 dB on the waterfall, F1
  ahead only at r0359 — but those F1 codes carry S3 undetected rates of
  2–40 × 10⁻⁴ (walk-correlated point-trials; r0547's and r0203's above
  the S3 bar) where F3's sit at 0.4–4 × 10⁻⁴. S4-measured F1 codes are
  accepted at r0906, r0781 and r0703 and refused at r0781 (Z 64),
  r0703 (one), r0469, r0359 (both, 12 and 16 per 10⁵) and r0313; the
  F1 bests at r0547, r0406, r0250 and r0203 never reached S4, so an
  F1-only ladder's holes are unmeasured there, not refused.
- **R3 Floor bars — the one ruling the published ladder waits on.** As
  built: the undetected RATE ≤ 1e-4 at the 1 % point and at +0.5 dB
  (10⁵ trials each, disjoint, the only independent counts in the
  campaign) is the hard refusal; the minimum-found-weight bars
  (≥ 20 / ≥ 12) and the per-rung weight bar are recorded expectations.
  CALIBRATION (2026-10-19, `measure/ladder2-v1-twins/`): under this
  same bar the frozen v1 codes read r0850 9 / 5 (passes at the edge;
  sheet H 100 %), r0775 11 / 6 (refused), r0700 3 / 1, r0625 41 / 32
  (refused), r0547 8 / 1, r0550 181 / 89 (refused) — the codes that
  close sheets on paper sit in the regime the bar refuses on the v2
  side, where the v2 r0859 (12 / 0) is 0.065 dB faster than r0850.
  MEASURED (§1.1, §3.7): the bar leaves four rungs without a code and
  refuses 22 of 35 measured codes, at 11–54 per 10⁵ at the 1 % point
  (11–50 at the four empty rungs) and 0–15 at +0.5 dB — the union-bound
  acceptance bar admits codes at that edge by construction, and a code
  at 1.2e-4 passes a 10⁵-trial point about one time in three, so the
  split at r0859 and r0406 is within counting noise of the accepted
  codes elsewhere. What the CRC makes of those decodes (§3.7): weight
  ≤ 3 information patterns (≤ 4 where k − p ≤ 3000) never certify —
  0–88 % of the measured words per code; the rest at 1 − 2⁻³² under
  the random-CRC model; the silent residue is ≤ 1.3 × 10⁻¹³ per attempt
  at the largest measured S4 rate (5.4e-4), and in production attempts
  × rate(regime) × 2⁻³² — the hard sub-threshold points of the S3 walks
  reach ~6e-3 per trial, so 10⁶ retries there bound the per-volume
  residue at ~1.4e-6 — behind which a CRC miss surfaces as a terminal
  integrity failure or a sha-failed close (holo3 `format/close.py`),
  never as a silent error. So the bar prices lost attempts and floor
  quality. The options, each with ONE explicit pick rule, priced from
  the ledger (every number already measured, no re-run needed):
  - **(a) as built: 1e-4 at both points, S4 on the S3 top three, no
    backfill.** Eight rungs published; r0859, r0625, r0406 and r0313
    EMPTY. Their S3 ranks 4–5 are unmeasured in S4 (r0859's rank-5 F4
    reads 0.882 dB with 2 undetected in its 45,000 walk point-trials;
    a clean walk does not predict S4 — r0406's rank-3 read 11 / 0 at
    S4 after a clean walk). Price: four holes, or one more S4 round
    walking down the ranking (≈ 0.4 M decodes per code, ~10 min each).
  - **(b) 1e-4 at +0.5 dB, 5e-4 (≈ 5 % of failures) at the 1 % point;
    pick = the fastest S4-measured code that passes.** Every rung
    filled: r0859 → 0.734 (14 / 0), r0625 → 0.827 (32 / 2), r0406 →
    1.006 (21 / 4), r0313 → 1.316 (18 / 5); r0547 → its S3 rank-2 at
    0.837 (33 / 3, 0.036 dB faster inside the tie band), r0359 → its F1
    at 1.138 (12 / 3, 0.044 dB); r0906, r0781, r0703, r0469, r0250 and
    r0203 keep their published codes. With pick = the S3 rank-1 that
    passes instead: r0859 0.747, r0406 1.007, r0203 its rank-1 at 1.695
    (0.02 dB slower), the rest as above.
  - **(c) a bar on the post-CRC silent rate** (≤ 10⁻¹² per attempt at
    the 1 % point): every measured code passes, the undetected rate
    stays a recorded ranking tie-breaker; the same picks as (b) under
    the same pick rule — and it is the bar the system's certification
    discipline implies. The S3 bar (1e-3 over the operating region)
    stands upstream unless ruled with it: r0203's F2 (1.218 dB, 0.46 dB
    faster, S3 rate 1.5e-3) was never S4-measured.
  - **(d) zero in 10⁵ at both points** (the first draft's rule): no
    S4-measured code meets it (the lowest read 1 / 0); not a ladder.
  - **The waterfall-vs-floor trade at the bottom:** F2 (PBRL) at r0203
    reads 1.218 dB against the published 1.675 — 0.46 dB, a quarter of
    the rung's whole gap — at a walk-correlated S3 rate of 1.5e-3 (the
    CRC catches the low-weight part deterministically, the rest at
    1 − 2⁻³²); the same family reads 0.29–0.35 dB BEHIND at r0547 and
    r0469. If fragments are the r0203 customer, that is the one place a
    looser floor bar buys real reach; it needs an S4 run of its own.
  The owner picks (a)–(d) or a bar of his own; the planner re-judges
  the ledger without re-lifting or re-measuring (§3.4) and `report`
  republishes; only (a)'s extra S4 round and (c)'s F2 case decode.
  RULED IN PART 2026-10-24 (the owner, on c8-low's bar-edge picks at
  r0250 / r0203 — 19 and 20 pooled undetected in 2 × 10⁵ against the
  bar's 20): "Take the new picks." The as-built bar (a) stands, applied
  since rank v3/v4 on S4's and the rung final's counts pooled (§1.2);
  what it guards against is priced above (a CRC miss behind an
  undetected decode, ≤ 10⁻⁹ per sheet at this floor). Not yet ruled: a
  tolerance so a count of Poisson noise cannot flip a verdict on
  re-measurement, and whether a published code is ever required to
  carry a margin under the bar.
- **R4 The top rung.** k 3712 (r0906). MEASURED: 0.804 dB against the
  0.80 expectation (misses it by 0.004 dB), 0.47 dB to the normal
  approximation; no margin, so the k 3776/3840 probe is NOT proposed.
- **R5 Naming.** True-rate tokens in the `ldpc-v2/` namespace; v1 tokens
  untouched; the format-version string carries the ladder version. As
  built: the floor report names a code `ldpc-v2/<token>/<edge_sha>`,
  the campaign names it by its spec id (`<token>-z<z>-<family>-v<i>-<n>-
  <digest>-L<seed>`), and the published file stems are
  `<token>[-z<z>][-runnerup].json`; the ruling owed is the spelling the
  format version will carry.
- **R6 Selection decoder.** The production identity (60 min-sum + SP 60,
  α 0.8, clip 20) selected. MEASURED (§1.1): 150 + SP 150 is worth
  0.01–0.03 dB at r0906–r0781, 0.03–0.08 dB at r0703–r0359, and 0.19 /
  0.12 / 0.35 dB at r0313 / r0250 / r0203, at 1.6–1.9× the CPU per
  decode (the receiver's retry tier already runs 150,
  `plugins/tiles.py` RETRY_BP_MAX_ITERS). It is a selection question at
  one rung: at 150 iterations r0359's F1 leads the F3 pick by 0.079 dB
  (0.14 at SP-200), outside the tie band. Ruling: the selection decoder
  stays the production identity unless the owner moves it; the
  bottom-three budget is a decoder ruling of its own.
- **R7 Families in the final pick.** F1–F4 all admitted; the pick per
  rung is by §3.4 and reads F1 at r0906–r0625, F3 at r0547–r0203 (§1.1
  "families by band"). F2 was dropped on its S3 rate at r0203 and
  out-ranked (clean) at r0547/r0469 — the r0203 trade is in R3; F4
  placed third at r0906 only. Nothing to strike unless R2 strikes F3.
- **R8 The last-block-row rule (added 2026-10-18).** Threshold against
  floor, priced in §3.3. MEASURED (§1.1): the bound-aware placement
  (v0, the default) and the free variant (v3) split the F1 rungs
  (v3 at r0906 and r0703, v0 at r0859, r0781 and r0625; v1 = bound +
  weight-3-first is F3's pick at r0250), the blanket rule (v2) is moot
  (refused everywhere by the info-free-row check). Proposed ruling:
  keep v0, v1 and v3 in the search, no per-band rule — the Monte Carlo
  decides and the duplicate-lift rule makes the overlap free.
- **R9 The PEXIT criterion (added 2026-10-18).** Tolerance 1e-2 vs 1e-3
  flips the low-rung family ranking; both were carried and the Monte
  Carlo decided; S1's union of the two top-12 lists went to S0/S2 at
  every rung. No disagreement reaches the final pick — MOOT as a ruling;
  full DE stays a follow-up (docs/TODO.md).
- **After the 2026-10-19 review (no ruling):** the review's planner
  debts — S2 dropping on ANY undetected decode (300 S0-passing specs,
  an F2 at r0250 0.15 dB faster than the best pick among them), the
  walk-correlated S3 rate, Z sharing the S1 keep, 236 all-duplicate S1
  slots, the lifter's gate knob below the acceptance bar from r0469
  down (532 gate-passing lifts refused by the planner) — are BUILT
  behind flags and run by c3-search (§3.4, §8.1); every S3 rate quoted
  in this record stays per point-trial. Still open: the acceptance
  bar's constant 10.8 is 10.87 rounded (one weight short at r0547 and
  r0469; the one S4 code at the bar, r0547's pair-15 rank-2, was refused
  by S4 anyway) and assumes 64 minimum-weight words at Z 32 too.

## 10. Non-goals and the integration boundary

No change under `src/holo`, `analyzer/` or the receiver; no new format
row, golden, profile or identity; no print. The v2 ladder becomes
printable only through a later format version that adds the v2 loader
(base-matrix expansion, punctured LLRs), the token namespace, the
capacity tables, goldens and the receiver's attempt-floor and
column-group arithmetic for the new k's — after C2's record, the review,
and the §9 rulings.
