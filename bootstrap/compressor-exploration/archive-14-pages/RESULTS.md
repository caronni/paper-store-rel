# v2-lab-archive: can T1 reach 14 (or 13) archive pages? (2026-10-20, this container)

Labels: MEASURED = run here; RECORDED = repo record; ESTIMATE = derived. Raw data: results.json, runs.jsonl,
r2cost.jsonl, inarch.jsonl, orders.json, dedupe*.json; arm texts arm_*.py (from mk_arms.py), diffs in diffs/.

## Baseline and ceilings (MEASURED unless marked)
| codec | T1_1MB | T1_2MB | T1 (9,533,440) |
|---|---|---|---|
| strong2 | 255,569 (enc 148 / dec 140 us/B, 1,038 MB) | 492,414 | 1,648,648 RECORDED, 15 pages, 13.1 min, 1.36 GB |
| xz -9e | 330,128 | 639,124 | 2,151,408 |
| lpaq1 9 | 258,326 | 498,283 | 1,677,993 |
| paq8l -8 | 239,944 (-6.1 %, 93 s) | - | **1,502,611 (-8.86 %, 867 s, 1.64 GB) = 14 pages** |
Page limits: 15 <= 1,655,012; 14 <= 1,544,395; 13 <= 1,433,778 (ESTIMATE, one page = 110,617 B). paq8l -8 reaches 14, not 13.
paq8l's lead over strong2 grows with n (-6.1 % at 1 MB, -8.9 % whole).

## Model arms on strong2, T1_1MB (MEASURED; R2 delta = ESTIMATE, cm2 of the minified region conditioned on r.py + receiver_ming.py)
| arm | bytes | delta % | enc us/B | R2 delta B |
|---|---|---|---|---|
| OL hashed orders 12/16/24 | 254,635 | -0.365 | 183 | +44 |
| M2 second verified match, order-16 hash | 255,013 | -0.218 | 161 | +153 |
| CRH counter cap 15->11 | 255,275 | -0.115 | 139 | 0 |
| CRH8 counter cap 15->8 | 255,218 | -0.137 | 137 | ~0 |
| SP sparse (b2-3, b3-4, b1+3) | 255,344 | -0.088 | 163 | +21 |
| APMM APM by match state x c0 | 255,363 | -0.081 | 154 | +44 |
| APM2 APM by order-2 x c0 | 255,441 | -0.050 | 155 | +49 |
| AQC order-3 APM keyed with c0 | 255,476 | -0.036 | 147 | +4 |
| O6 order 6 | 255,612 | +0.017 | 153 | +4 |
| K27 / K25 | 255,619 / 256,103 | +0.020 / +0.209 | 145 / 143 | 0 |
| MV verified match length, cap 31 | 255,675 | +0.041 | 146 | +19 |
| MIX2 two-layer mixer | 257,548 | +0.774 | 180 | +77 |
| CR2 slower counters R[2nt] | 258,256 | +1.051 | 144 | +1 |
8 KB only: WI weight init 0.375 +152 B, DUAL linear 2nd input/context +325 B, CRF +36 B.
k30 ESTIMATE: k25->k27 at 1 MB mirrors k28->k30 at T1: -0.19 % (~-3.1 KB), ~3.4 GB.
Combination C1 = OL+M2+SP+APMM+APM2+AQC: 254,296 (-0.498 %, NOT additive: parts sum -0.84 %), 243 us/B,
round trip MEASURED true on 1 MB (dec 259 s, 1,119 MB). R2 +262 B.
Finalist C1+CRH on T1_2MB: 489,192 vs 492,414 = **-0.654 %**, 233 us/B (1.67x), 1,135 MB; round trip 8 KB true.

## Preprocessing (MEASURED)
- Order (lpaq1 9, whole T1 tar): path 1,677,993; ext+dir 1,677,928; chain8 within ext 1,678,193; code first 1,679,491;
  chain8 1,681,467; basename 1,684,509. Path order is already best within 0.004 %.
- shar: lpaq1 -2,676 B; strong2 -2.3 KB RECORDED.
- Dedupe: 2 dup-file groups = 1,341 B; 31 duplicate functions = 5,604 B (ast); total 0.075 % of 9.28 MB content.
  Removing them all: lpaq1 +8 B (the match model already takes them for free). Repeated lines >= 40 chars: 299 KB.
  No strong2 dedupe run (lpaq1 null makes it moot).

## Conclusion (ESTIMATE)
- Best combination on T1: 1,648,648 x (1 - 0.00654) = 1,637,860; with k30 and shar ~1,632,500 = **15 pages**.
  88 KB (5.4 %) short of 14. Extrapolation = 2 MB ratio applied to 9.53 MB; the gain grew 0.50 -> 0.65 % from 1 to 2 MB,
  so it is likely larger on T1, but even double (-1.3 %) is 15 pages.
- Decode ~21.9 min (13.1 x 233/139), ~1.46 GB (3.4 GB with k30).
- R2: the combination costs ~+263 B against 9 B spare = 3 R2 pages; only CRH (0 B) and AQC (+4 B) fit 2 pages
  (together ~-0.15 %, no page). With the decoder inside the archive (214 B R2 RECORDED) the combo is 2,847 B
  minified / 1,408 B cm2 unprimed inside the archive (strong2 2,133 / 1,135).
- 14 pages needs paq8l-class modelling (bit-history states, many more models, 2-layer mixing with selected sets,
  SSE chain); paq8l -8 gives 1,502,611 (14 pages) but at ~90 us/B in C. 13 pages: not reached by any codec measured.
