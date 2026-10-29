# Construction search — id-smoke-fast

Mode `smoke`; settings `{"s1_trials": 20, "walk_trials": 20, "fine_trials": 40, "side_trials": 20, "n_finalists": 1, "n_fine": 1, "seedvar_configs": 0, "chunk": 50, "workers": 3, "ks": [1664, 1280, 1600, 1216, 2880, 3520], "min_w2": 10, "min_w2_final": null, "max_walk_pts": 40, "s1_anchor": null, "min_w2_by_k": null, "decoder": "fast"}`; runs logged: 1.  
Decoder: production schedule `holo.core.ldpc.decode` (min-sum α 0.8, 60 it + one sum-product retry); runs executed with ['fast'] (fast = fast/fastdecode.py, the bit-exact batched twin: identical outcomes).  Seeds: bsc 100000+t, awgn 200000+t, eras 300000+t, robust 500000+t (common random numbers across codes).  
Screen 1 = 4 points at the frozen recipe's 10 % points: awgn +(0.0, 0.25) dB, bsc +(0.0, 0.005); score = mean ln BLER (0/n floored at 0.5/n), lower is better.  
Walks start at the frozen 10 % grid point (0.25 dB / 0.005 grids of the harness), easy side until two consecutive 0/n, hard side until BLER ≥ 0.5; 1 %/10 % by log-linear interpolation (harness tables.interp_x). `fine` = top-N at the fine trial count on the bracketing grid points + midpoint.  
Constraints: girth > 4, no info-free block row; screen 1 only for codes with min(w1, w2) ≥ the run's floor (settings `min_w2` 10, per-k `min_w2_by_k` None; the `reject` column shows the protocol's fixed w2 < 10 flag). Search configs RESTART on an info-free block row (rule e); baselines are the frozen recipe exactly.

Total worker CPU recorded: 0.03 h over 12 built configs.

## k = 3520 (R = 0.8594); Shannon 1.993 dB, p_cap 0.0199; frozen recipe (r0850, harness 200/pt): Es/N0@1% 2.875, @10% 2.593, p@1% 0.0078, p@10% 0.0120

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 2.593 dB, p 0.0120 — from frozen r0850

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | recipe | **base-r0850** | h6 f0.3 l3 uni s0 | 0 (0) | 22..27 | 25 / 4 | min_w2=4<10 | -2.20 | 3.040 | 2.625 | 1.05 | 0.00 | -0.0016 | 0.0112 | 0.141 | fine | 0/400 | 7/20 / 17/20 / 20/20 / 20/20 (0/20) | 20/20 |

### Screen 1 ranking (top 25 of 1 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | recipe | base-r0850 | h6 f0.3 l3 uni s0 | -2.20 | 3/20 / 0/20 | 1/20 / 16/20 | 4 | 22..27 |

### Screen 0: 1 built/attempted; verdicts {"min_w2": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 1/1

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

## k = 2880 (R = 0.7031); Shannon -0.237 dB, p_cap 0.0525; frozen recipe (r0700, harness 200/pt): Es/N0@1% 0.611, @10% 0.369, p@1% 0.0360, p@10% 0.0395

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 0.369 dB, p 0.0395 — from frozen r0700

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | recipe | **base-r0700** | h10 f0.3 l3 uni s0 | 0 (0) | 11..16 | 25 / 7 | min_w2=7<10 | -2.37 | 0.750 | 0.411 | 0.99 | 0.00 | 0.0346 | 0.0387 | 0.080 | fine | 0/420 | 12/20 / 20/20 / 20/20 / 20/20 (0/20) [1 undet] | 20/20 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): base-r0700 robust 0.5995 t5 w26/12

### Screen 1 ranking (top 25 of 1 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | recipe | base-r0700 | h10 f0.3 l3 uni s0 | -2.37 | 3/20 / 0/20 | 1/20 / 8/20 | 7 | 11..16 |

### Screen 0: 1 built/attempted; verdicts {"min_w2": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 1/1

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

## k = 1664 (R = 0.4062); Shannon -4.125 dB, p_cap 0.1437; frozen recipe (r0406, harness 200/pt): Es/N0@1% -2.825, @10% -3.108, p@1% 0.1039, p@10% 0.1118

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.108 dB, p 0.1118 — from frozen r0406

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | 0 (0) | 4..6 | 26 / 15 | — | -3.24 | -2.960 | -3.214 | 1.17 | -0.25 | 0.0950 | 0.1150 | 0.141 | fine | 0/500 | 14/20 / 19/20 / 20/20 / 20/20 (0/20) | 0/20 |
| 2 | recipe | **base-r0406** | h10 f0.3 l3 uni s0 | 0 (0) | 3..7 | 43 / 16 | — | -2.65 | -2.710 | -3.000 | 1.42 | 0.00 | 0.1046 | 0.1094 | 0.110 | fine | 0/460 | 9/20 / 17/20 / 20/20 / 20/20 (0/20) | 0/20 |

### Screen 1 ranking (top 25 of 2 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | A | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -3.24 | 0/20 / 0/20 | 0/20 / 3/20 | 15 | 4..6 |
| 2 | recipe | base-r0406 | h10 f0.3 l3 uni s0 | -2.65 | 2/20 / 0/20 | 1/20 / 4/20 | 16 | 3..7 |

### Screen 0: 1 built/attempted; verdicts {"pass": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 1 | -3.24 | -3.24 |
| light | 3 | 1 | -3.24 | -3.24 |
| heavy_frac | 0.3 | 1 | -3.24 | -3.24 |
| heavy_deg | 10 | 1 | -3.24 | -3.24 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 1/1

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

## k = 1600 (R = 0.3906); Shannon -4.358 dB, p_cap 0.1498; frozen recipe (r0391, harness 200/pt): Es/N0@1% -3.108, @10% -3.384, p@1% 0.1075, p@10% 0.1176

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.384 dB, p 0.1176 — from frozen r0391

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | k1600-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | 0 (0) | 5..6 | 40 / 14 | — | -3.34 | -3.355 | -3.589 | 1.00 | -0.27 | 0.1100 | 0.1200 | 0.109 | fine | 0/460 | 14/20 / 19/20 / 20/20 / 20/20 (0/20) | 0/20 |
| 2 | recipe | **base-r0391** | h10 f0.3 l3 uni s0 | 0 (0) | 2..7 | 69 / 11 | info_free_block_rows=1 | -2.25 | -3.085 | -3.366 | 1.27 | 0.00 | 0.1034 | 0.1175 | 0.130 | fine | 2/440 ⚠ | 11/20 / 19/20 / 20/20 / 20/20 (0/20) | 0/20 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): base-r0391 bsc 0.12258 t4 w11/2; base-r0391 bsc 0.125 t4 w11/2

### Screen 1 ranking (top 25 of 2 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | A | k1600-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | -3.34 | 0/20 / 0/20 | 0/20 / 2/20 | 14 | 5..6 |
| 2 | recipe | base-r0391 | h10 f0.3 l3 uni s0 | -2.25 | 4/20 / 1/20 | 1/20 / 5/20 | 11 | 2..7 |

### Screen 0: 1 built/attempted; verdicts {"pass": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 1 | -3.34 | -3.34 |
| light | 3 | 1 | -3.34 | -3.34 |
| heavy_frac | 0.3 | 1 | -3.34 | -3.34 |
| heavy_deg | 12 | 1 | -3.34 | -3.34 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 1/1

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

## k = 1280 (R = 0.3125); Shannon -5.624 dB, p_cap 0.1834; frozen recipe (r0313, harness 200/pt): Es/N0@1% -3.858, @10% -4.201, p@1% 0.1200, p@10% 0.1398

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.201 dB, p 0.1398 — from frozen r0313

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | k1280-h10-f0.5-l4-uni-g24-d1-s0 | h10 f0.5 l4 uni s0 | 2 (2) | 2..7 | 28 / 57 | — | -3.34 | -4.105 | -4.358 | 1.52 | -0.15 | 0.1350 | 0.1450 | 0.117 | fine | 0/460 | 0/20 / 9/20 / 19/20 / 20/20 (0/20) | 0/20 |
| 2 | recipe | **base-r0313** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 58 / 12 | info_free_block_rows=5 | -2.89 | -3.960 | -4.375 | 1.66 | 0.00 | 0.1300 | 0.1391 | 0.130 | fine | 0/460 | 13/20 / 19/20 / 20/20 / 20/20 (0/20) | 0/20 |

### Screen 1 ranking (top 25 of 2 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | A | k1280-h10-f0.5-l4-uni-g24-d1-s0 | h10 f0.5 l4 uni s0 | -3.34 | 0/20 / 0/20 | 1/20 / 1/20 | 57 | 2..7 |
| 2 | recipe | base-r0313 | h10 f0.3 l3 uni s0 | -2.89 | 1/20 / 0/20 | 1/20 / 3/20 | 12 | 2..6 |

### Screen 0: 1 built/attempted; verdicts {"pass": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | uniform | 1 | -3.34 | -3.34 |
| light | 4 | 1 | -3.34 | -3.34 |
| heavy_frac | 0.5 | 1 | -3.34 | -3.34 |
| heavy_deg | 10 | 1 | -3.34 | -3.34 |

Restarts rejected for an info-free block row (rule e), per placement: uniform: mean 2.0, max 2, zero in 0/1

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

## k = 1216 (R = 0.2969); Shannon -5.903 dB, p_cap 0.1908; frozen recipe (r0297, harness 200/pt): Es/N0@1% -4.000, @10% -4.479, p@1% 0.1422, p@10% 0.1490

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.479 dB, p 0.1490 — from frozen r0297

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | k1216-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 4..5 | 69 / 22 | — | -3.69 | -4.250 | -4.704 | 1.65 | -0.33 | 0.1500 | 0.1594 | 0.093 | fine | 0/460 | 9/20 / 16/20 / 20/20 / 20/20 (0/20) | 0/20 |
| 2 | recipe | **base-r0297** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 35 / 25 | info_free_block_rows=5 | -3.24 | -3.920 | -4.579 | 1.98 | 0.00 | 0.1400 | 0.1494 | 0.119 | fine | 0/420 | 19/20 / 20/20 / 20/20 / 20/20 (0/20) | 0/20 |

### Screen 1 ranking (top 25 of 2 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | A | k1216-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -3.69 | 0/20 / 0/20 | 0/20 / 0/20 | 22 | 4..5 |
| 2 | recipe | base-r0297 | h10 f0.3 l3 uni s0 | -3.24 | 0/20 / 0/20 | 0/20 / 3/20 | 25 | 2..6 |

### Screen 0: 1 built/attempted; verdicts {"pass": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 1 | -3.69 | -3.69 |
| light | 3 | 1 | -3.69 | -3.69 |
| heavy_frac | 0.5 | 1 | -3.69 | -3.69 |
| heavy_deg | 10 | 1 | -3.69 | -3.69 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 1/1

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

