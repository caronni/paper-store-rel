# Construction search — calib-fast

Mode `trial`; settings `{"s1_trials": 100, "walk_trials": 100, "fine_trials": 500, "side_trials": 100, "n_finalists": 6, "n_fine": 4, "seedvar_configs": 2, "chunk": 50, "workers": 14, "ks": [1664, 1280], "min_w2": 10, "min_w2_final": null, "max_walk_pts": 40, "s1_anchor": {"1664": {"es10": -3.1955028707748854, "p10": 0.11684241398541552, "src": "trial-A:k1664-h8-f0.5-l3-bal-g24-d1-s0"}, "1280": {"es10": -4.584906804806198, "p10": 0.155, "src": "trial-A:k1280-h12-f0.5-l3-bal-g24-d1-s1"}}, "min_w2_by_k": null, "decoder": "fast"}`; runs logged: 1.  
Decoder: production schedule `holo.core.ldpc.decode` (min-sum α 0.8, 60 it + one sum-product retry); runs executed with ['fast'] (fast = fast/fastdecode.py, the bit-exact batched twin: identical outcomes).  Seeds: bsc 100000+t, awgn 200000+t, eras 300000+t, robust 500000+t (common random numbers across codes).  
Screen 1 = 4 points at the frozen recipe's 10 % points: awgn +(0.0, 0.25) dB, bsc +(0.0, 0.005); score = mean ln BLER (0/n floored at 0.5/n), lower is better.  
Walks start at the frozen 10 % grid point (0.25 dB / 0.005 grids of the harness), easy side until two consecutive 0/n, hard side until BLER ≥ 0.5; 1 %/10 % by log-linear interpolation (harness tables.interp_x). `fine` = top-N at the fine trial count on the bracketing grid points + midpoint.  
Constraints: girth > 4, no info-free block row; screen 1 only for codes with min(w1, w2) ≥ the run's floor (settings `min_w2` 10, per-k `min_w2_by_k` None; the `reject` column shows the protocol's fixed w2 < 10 flag). Search configs RESTART on an info-free block row (rule e); baselines are the frozen recipe exactly.

Total worker CPU recorded: 0.49 h over 74 built configs.

## k = 1664 (R = 0.4062); Shannon -4.125 dB, p_cap 0.1437; frozen recipe (r0406, harness 200/pt): Es/N0@1% -2.825, @10% -3.108, p@1% 0.1039, p@10% 0.1118

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.196 dB, p 0.1168 — from trial-A:k1664-h8-f0.5-l3-bal-g24-d1-s0

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | 0 (0) | 4..6 | 26 / 15 | — | -2.50 | -3.000 | -3.224 | 1.13 | -0.17 | 0.1028 | 0.1143 | 0.116 | fine | 0/4300 | 80/100 / 96/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 2 | A | k1664-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 4..6 | 33 / 16 | — | -2.67 | -2.991 | -3.192 | 1.13 | -0.16 | 0.1100 | 0.1164 | 0.094 | fine | 0/4000 | 54/100 / 91/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 3 | A | k1664-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 5..7 | 33 / 19 | — | -2.34 | -2.958 | -3.164 | 1.17 | -0.12 | 0.1125 | 0.1180 | 0.086 | fine | 0/4100 | 52/100 / 86/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 4 | A | k1664-h8-f0.5-l3-uni-g24-d1-s0 | h8 f0.5 l3 uni s0 | 1 (1) | 3..7 | 32 / 20 | — | -2.41 | -2.958 | -3.175 | 1.17 | -0.12 | 0.1084 | 0.1159 | 0.099 | fine | 0/4000 | 58/100 / 92/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 5 | recipe | **base-r0406** | h10 f0.3 l3 uni s0 | 0 (0) | 3..7 | 43 / 16 | — | -1.67 | -2.835 | -3.089 | 1.29 | 0.00 | 0.1021 | 0.1109 | 0.118 | fine | 1/4100 ⚠ | 80/100 / 97/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 6 | A | k1664-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | 0 (0) | 3..8 | 63 / 12 | — | -2.25 | -2.825 | -3.108 | 1.30 | 0.01 | 0.1125 | 0.1195 | 0.086 | walk | 0/1400 | 47/100 / 83/100 / 100/100 / 100/100 (2/100) | 0/100 |
| 7 | A | k1664-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | 0 (0) | 3..7 | 27 / 11 | — | -2.43 | -3.000 | -3.232 | 1.13 | -0.17 | 0.1000 | 0.1139 | 0.125 | walk | 1/1800 ⚠ | 88/100 / 98/100 / 100/100 / 100/100 (1/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1664-h10-f0.3-l3-bal-g24-d1-s0 robust -3.0 t42 w15/2; base-r0406 bsc 0.11 t303 w17/4; k1664-h12-f0.3-l3-uni-g24-d1-s0 bsc 0.12 t57 w12/2

### Screen 1 ranking (top 25 of 36 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | A | k1664-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -2.67 | 13/100 / 0/100 | 9/100 / 40/100 | 16 | 4..6 |
| 2 | A | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -2.50 | 7/100 / 1/100 | 15/100 / 43/100 | 15 | 4..6 |
| 3 | A | k1664-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | -2.43 | 8/100 / 1/100 | 18/100 / 41/100 | 11 | 3..7 |
| 4 | A | k1664-h8-f0.5-l3-uni-g24-d1-s0 | h8 f0.5 l3 uni s0 | -2.41 | 12/100 / 1/100 | 13/100 / 42/100 | 20 | 3..7 |
| 5 | A | k1664-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.34 | 19/100 / 2/100 | 10/100 / 23/100 | 19 | 5..7 |
| 6 | A | k1664-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | -2.25 | 19/100 / 4/100 | 6/100 / 27/100 | 12 | 3..8 |
| 7 | A | k1664-h10-f0.3-l3-uni-g24-d1-s0 | h10 f0.3 l3 uni s0 | -2.18 | 13/100 / 1/100 | 24/100 / 52/100 | 14 | 3..7 |
| 8 | A | k1664-h10-f0.3-l4-bal-g24-d1-s0 | h10 f0.3 l4 bal s0 | -2.12 | 21/100 / 1/100 | 20/100 / 49/100 | 39 | 5..6 |
| 9 | A | k1664-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -1.99 | 21/100 / 4/100 | 12/100 / 34/100 | 29 | 5..7 |
| 10 | A | k1664-h8-f0.3-l3-bal-g24-d1-s0 | h8 f0.3 l3 bal s0 | -1.92 | 14/100 / 2/100 | 29/100 / 56/100 | 15 | 4..6 |
| 11 | A | k1664-h12-f0.3-l4-uni-g24-d1-s0 | h12 f0.3 l4 uni s0 | -1.84 | 33/100 / 3/100 | 13/100 / 49/100 | 27 | 3..8 |
| 12 | A | k1664-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | -1.80 | 30/100 / 5/100 | 14/100 / 35/100 | 25 | 4..9 |
| 13 | A | k1664-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | -1.75 | 39/100 / 7/100 | 10/100 / 34/100 | 14 | 6..8 |
| 14 | A | k1664-h10-f0.3-l4-uni-g24-d1-s0 | h10 f0.3 l4 uni s0 | -1.70 | 29/100 / 4/100 | 18/100 / 53/100 | 33 | 3..7 |
| 15 | recipe | base-r0406 | h10 f0.3 l3 uni s0 | -1.67 | 20/100 / 3/100 | 34/100 / 61/100 | 16 | 3..7 |
| 16 | A | k1664-h8-f0.3-l3-uni-g24-d1-s0 | h8 f0.3 l3 uni s0 | -1.60 | 25/100 / 2/100 | 44/100 / 76/100 | 11 | 3..7 |
| 17 | A | k1664-h8-f0.3-l4-bal-g24-d1-s0 | h8 f0.3 l4 bal s0 | -1.35 | 36/100 / 7/100 | 27/100 / 67/100 | 22 | 4..6 |
| 18 | A | k1664-h8-f0.3-l4-uni-g24-d1-s0 | h8 f0.3 l4 uni s0 | -1.31 | 40/100 / 5/100 | 36/100 / 74/100 | 21 | 3..7 |
| 19 | A | k1664-h8-f0.5-l4-bal-g24-d1-s0 | h8 f0.5 l4 bal s0 | -1.28 | 40/100 / 7/100 | 31/100 / 68/100 | 20 | 5..7 |
| 20 | A | k1664-h8-f0.7-l3-bal-g24-d1-s0 | h8 f0.7 l3 bal s0 | -1.28 | 42/100 / 9/100 | 26/100 / 62/100 | 25 | 5..7 |
| 21 | A | k1664-h10-f0.5-l4-bal-g24-d1-s0 | h10 f0.5 l4 bal s0 | -1.06 | 54/100 / 15/100 | 28/100 / 63/100 | 41 | 6..7 |
| 22 | A | k1664-h10-f0.5-l4-uni-g24-d1-s0 | h10 f0.5 l4 uni s0 | -0.97 | 62/100 / 14/100 | 33/100 / 71/100 | 48 | 4..8 |
| 23 | A | k1664-h8-f0.5-l4-uni-g24-d1-s0 | h8 f0.5 l4 uni s0 | -0.95 | 61/100 / 12/100 | 38/100 / 79/100 | 38 | 3..8 |
| 24 | A | k1664-h8-f0.7-l3-uni-g24-d1-s0 | h8 f0.7 l3 uni s0 | -0.92 | 59/100 / 18/100 | 35/100 / 69/100 | 21 | 3..8 |
| 25 | A | k1664-h10-f0.7-l3-bal-g24-d1-s0 | h10 f0.7 l3 bal s0 | -0.69 | 72/100 / 32/100 | 36/100 / 76/100 | 28 | 6..8 |

### Screen 0: 36 built/attempted; verdicts {"pass": 35, "min_w2": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 17 | -1.33 | -2.67 |
| placement | uniform | 18 | -1.22 | -2.43 |
| light | 3 | 17 | -1.61 | -2.67 |
| light | 4 | 18 | -0.96 | -2.12 |
| heavy_frac | 0.3 | 11 | -1.91 | -2.50 |
| heavy_frac | 0.5 | 12 | -1.55 | -2.67 |
| heavy_frac | 0.7 | 12 | -0.42 | -1.28 |
| heavy_deg | 10 | 12 | -1.38 | -2.50 |
| heavy_deg | 12 | 11 | -1.03 | -2.43 |
| heavy_deg | 8 | 12 | -1.40 | -2.67 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 18/18; uniform: mean 0.3, max 3, zero in 14/18

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

## k = 1280 (R = 0.3125); Shannon -5.624 dB, p_cap 0.1834; frozen recipe (r0313, harness 200/pt): Es/N0@1% -3.858, @10% -4.201, p@1% 0.1200, p@10% 0.1398

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.585 dB, p 0.1550 — from trial-A:k1280-h12-f0.5-l3-bal-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | k1280-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 3..5 | 76 / 28 | — | -1.99 | -4.271 | -4.483 | 1.35 | -0.52 | 0.1400 | 0.1505 | 0.103 | fine | 0/4400 | 64/100 / 90/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 2 | A | k1280-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | 2 (2) | 3..6 | 52 / 19 | — | -1.75 | -4.241 | -4.480 | 1.38 | -0.49 | 0.1443 | 0.1516 | 0.092 | fine | 0/4200 | 47/100 / 85/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 3 | A | k1280-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | 0 (0) | 3..7 | 31 / 23 | — | -1.85 | -4.209 | -4.455 | 1.41 | -0.46 | 0.1464 | 0.1536 | 0.087 | fine | 0/4200 | 46/100 / 88/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 4 | A | k1280-h12-f0.3-l4-uni-g24-d1-s0 | h12 f0.3 l4 uni s0 | 1 (1) | 3..6 | 56 / 43 | — | -1.73 | -4.150 | -4.461 | 1.47 | -0.40 | 0.1434 | 0.1503 | 0.095 | fine | 0/4100 | 47/100 / 83/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 5 | A | k1280-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | 0 (0) | 5..6 | 99 / 29 | — | -2.18 | -4.097 | -4.500 | 1.53 | -0.35 | 0.1511 | 0.1547 | 0.075 | walk | 0/1500 | 50/100 / 80/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 6 | recipe | **base-r0313** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 58 / 12 | info_free_block_rows=5 | -0.60 | -3.750 | -4.190 | 1.87 | 0.00 | 0.1316 | 0.1400 | 0.126 | fine | 22/4500 ⚠ | 80/100 / 98/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 7 | A | k1280-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 3..5 | 128 / 10 | — | -2.55 | -4.316 | -4.560 | 1.31 | -0.57 | 0.1000 | 0.1535 | 0.219 | walk | 19/2500 ⚠ | 54/100 / 84/100 / 100/100 / 100/100 (0/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): base-r0313 awgn -4.5849 t82 w12/2; base-r0313 awgn -4.3349 t82 w12/2; base-r0313 bsc 0.155 t60 w12/2; base-r0313 bsc 0.16 t60 w12/2; base-r0313 bsc 0.155 t60 w12/2; base-r0313 bsc 0.16 t60 w12/2; base-r0313 awgn -4.5 t82 w12/2; base-r0313 awgn -4.25 t82 w12/2; base-r0313 awgn -4.0 t82 w12/2; base-r0313 awgn -3.75 t341 w12/2; base-r0313 awgn -3.75 t442 w14/2; base-r0313 awgn -3.75 t359 w14/2; base-r0313 awgn -4.0 t341 w12/2; base-r0313 awgn -4.0 t359 w14/2; base-r0313 awgn -4.0 t442 w14/2; base-r0313 awgn -3.875 t82 w12/2; base-r0313 awgn -3.875 t341 w12/2; base-r0313 awgn -3.875 t359 w14/2; base-r0313 awgn -3.875 t442 w14/2; base-r0313 bsc 0.125 t177 w12/2; base-r0313 bsc 0.13 t177 w12/2; base-r0313 bsc 0.1275 t177 w12/2; base-r0313 awgn -3.8467 t82 w12/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.16 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.16 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.15 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.15 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.165 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.145 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.145 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.14 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.14 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.135 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.135 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.13 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.13 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.125 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.12 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.115 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.11 t46 w10/2 …

### Screen 1 ranking (top 25 of 37 + baseline)

| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|---|
| 1 | A | k1280-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.55 | 12/100 / 0/100 | 15/100 / 42/100 | 10 | 3..5 |
| 2 | A | k1280-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | -2.18 | 19/100 / 2/100 | 12/100 / 36/100 | 29 | 5..6 |
| 3 | A | k1280-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -1.99 | 20/100 / 1/100 | 26/100 / 66/100 | 28 | 3..5 |
| 4 | A | k1280-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | -1.85 | 26/100 / 4/100 | 13/100 / 45/100 | 23 | 3..7 |
| 5 | A | k1280-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | -1.75 | 18/100 / 6/100 | 16/100 / 52/100 | 19 | 3..6 |
| 6 | A | k1280-h12-f0.3-l4-uni-g24-d1-s0 | h12 f0.3 l4 uni s0 | -1.73 | 20/100 / 3/100 | 27/100 / 62/100 | 43 | 3..6 |
| 7 | A | k1280-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -1.70 | 20/100 / 4/100 | 25/100 / 55/100 | 47 | 4..5 |
| 8 | A | k1280-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | -1.67 | 14/100 / 4/100 | 35/100 / 63/100 | 17 | 3..5 |
| 9 | A | k1280-h10-f0.3-l4-bal-g24-d1-s0 | h10 f0.3 l4 bal s0 | -1.53 | 27/100 / 6/100 | 22/100 / 62/100 | 52 | 4..5 |
| 10 | A | k1280-h8-f0.5-l3-uni-g24-d1-s0 | h8 f0.5 l3 uni s0 | -1.45 | 28/100 / 4/100 | 38/100 / 71/100 | 15 | 3..6 |
| 11 | A | k1280-h8-f0.5-l4-bal-g24-d1-s0 | h8 f0.5 l4 bal s0 | -1.35 | 31/100 / 5/100 | 42/100 / 70/100 | 63 | 3..5 |
| 12 | A | k1280-h8-f0.3-l3-bal-g24-d1-s0 | h8 f0.3 l3 bal s0 | -1.35 | 25/100 / 6/100 | 43/100 / 71/100 | 16 | 3..5 |
| 13 | A | k1280-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | -1.28 | 25/100 / 5/100 | 61/100 / 79/100 | 14 | 3..6 |
| 14 | A | k1280-h8-f0.7-l3-bal-g24-d1-s0 | h8 f0.7 l3 bal s0 | -1.27 | 36/100 / 11/100 | 25/100 / 64/100 | 15 | 4..5 |
| 15 | A | k1280-h10-f0.5-l4-bal-g24-d1-s0 | h10 f0.5 l4 bal s0 | -1.23 | 39/100 / 11/100 | 28/100 / 61/100 | 51 | 4..6 |
| 16 | A | k1280-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -1.22 | 30/100 / 8/100 | 44/100 / 71/100 | 17 | 3..5 |
| 17 | A | k1280-h8-f0.3-l4-bal-g24-d1-s0 | h8 f0.3 l4 bal s0 | -1.20 | 27/100 / 8/100 | 49/100 / 77/100 | 42 | 3..5 |
| 18 | A | k1280-h12-f0.5-l4-bal-g24-d1-s0 | h12 f0.5 l4 bal s0 | -1.18 | 45/100 / 11/100 | 28/100 / 65/100 | 45 | 5..6 |
| 19 | A | k1280-h10-f0.3-l4-uni-g24-d1-s0 | h10 f0.3 l4 uni s0 | -1.08 | 39/100 / 9/100 | 49/100 / 77/100 | 46 | 2..6 |
| 20 | A | k1280-h10-f0.3-l3-uni-g24-d1-s0 | h10 f0.3 l3 uni s0 | -1.04 | 34/100 / 10/100 | 55/100 / 82/100 | 18 | 3..6 |
| 21 | A | k1280-h10-f0.5-l4-uni-g24-d1-s0 | h10 f0.5 l4 uni s0 | -1.00 | 50/100 / 10/100 | 48/100 / 76/100 | 57 | 2..7 |
| 22 | A | k1280-h12-f0.5-l4-uni-g24-d1-s0 | h12 f0.5 l4 uni s0 | -0.99 | 55/100 / 14/100 | 38/100 / 65/100 | 55 | 3..7 |
| 23 | A | k1280-h8-f0.5-l4-uni-g24-d1-s0 | h8 f0.5 l4 uni s0 | -0.99 | 42/100 / 10/100 | 56/100 / 82/100 | 57 | 3..6 |
| 24 | A | k1280-h8-f0.7-l3-uni-g24-d1-s0 | h8 f0.7 l3 uni s0 | -0.89 | 47/100 / 16/100 | 52/100 / 73/100 | 24 | 3..6 |
| 25 | A | k1280-h8-f0.7-l4-bal-g24-d1-s0 | h8 f0.7 l4 bal s0 | -0.87 | 50/100 / 14/100 | 57/100 / 78/100 | 70 | 4..6 |
| 29 | recipe | base-r0313 | h10 f0.3 l3 uni s0 | -0.60 | 58/100 / 22/100 | 77/100 / 92/100 | 12 | 2..6 |

### Screen 0: 36 built/attempted; verdicts {"pass": 36}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 18 | -1.29 | -2.55 |
| placement | uniform | 18 | -0.94 | -1.85 |
| light | 3 | 18 | -1.28 | -2.55 |
| light | 4 | 18 | -0.95 | -1.73 |
| heavy_frac | 0.3 | 12 | -1.27 | -1.73 |
| heavy_frac | 0.5 | 12 | -1.54 | -2.55 |
| heavy_frac | 0.7 | 12 | -0.53 | -1.27 |
| heavy_deg | 10 | 12 | -1.12 | -2.55 |
| heavy_deg | 12 | 12 | -1.13 | -2.18 |
| heavy_deg | 8 | 12 | -1.10 | -1.99 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 18/18; uniform: mean 10.9, max 121, zero in 7/18

### Seed variance

Screen-1 score: mean within-config SD — (over 0 configs with ≥2 seeds) vs between-config SD of the config means —.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|

