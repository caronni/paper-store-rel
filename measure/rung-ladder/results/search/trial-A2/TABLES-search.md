# Construction search — trial-A2

Mode `trial`; settings `{"s1_trials": 100, "walk_trials": 100, "fine_trials": 500, "side_trials": 100, "n_finalists": 6, "n_fine": 4, "seedvar_configs": 2, "chunk": 50, "workers": 13, "ks": [1664, 1280, 1600, 1216], "s1_anchor": {"1664": {"es10": -3.1955028707748854, "p10": 0.11684241398541552, "src": "trial-A:k1664-h8-f0.5-l3-bal-g24-d1-s0"}, "1280": {"es10": -4.584906804806198, "p10": 0.155, "src": "trial-A:k1280-h12-f0.5-l3-bal-g24-d1-s1"}, "1600": {"es10": -3.470196884904838, "p10": 0.12260404969671047, "src": "trial-A:k1600-h12-f0.3-l3-bal-g24-d1-s1"}, "1216": {"es10": -4.824912185866601, "p10": 0.15917021883573235, "src": "trial-A:k1216-h10-f0.5-l3-uni-g24-d1-s1"}}}`; runs logged: 1.  
Decoder: production `holo.core.ldpc.decode` (min-sum α 0.8, 60 it + one sum-product retry). Seeds: bsc 100000+t, awgn 200000+t, eras 300000+t, robust 500000+t (common random numbers across codes).  
Screen 1 = 4 points at the frozen recipe's 10 % points: awgn +(0.0, 0.25) dB, bsc +(0.0, 0.005); score = mean ln BLER (0/n floored at 0.5/n), lower is better.  
Walks start at the frozen 10 % grid point (0.25 dB / 0.005 grids of the harness), easy side until two consecutive 0/n, hard side until BLER ≥ 0.5; 1 %/10 % by log-linear interpolation (harness tables.interp_x). `fine` = top-N at the fine trial count on the bracketing grid points + midpoint.  
Constraints: girth > 4, no info-free block row, min two-info-bit pair weight ≥ 10. Search configs RESTART on an info-free block row (rule e); baselines are the frozen recipe exactly.

Total worker CPU recorded: 2.36 h over 292 built configs.

## k = 1664 (R = 0.4062); Shannon -4.125 dB, p_cap 0.1437; frozen recipe (r0406, harness 200/pt): Es/N0@1% -2.825, @10% -3.108, p@1% 0.1039, p@10% 0.1118

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.196 dB, p 0.1168 — from trial-A:k1664-h8-f0.5-l3-bal-g24-d1-s0

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | 0 (0) | 4..6 | 26 / 15 | — | -2.50 | -3.000 | -3.224 | 1.13 | -0.17 | 0.1000 | 0.1143 | 0.125 | walk | 0/1700 | 80/100 / 96/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 2 | k1664-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 4..6 | 33 / 16 | — | -2.67 | -2.991 | -3.192 | 1.13 | -0.16 | 0.1100 | 0.1164 | 0.094 | fine | 0/4000 | 54/100 / 91/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 3 | k1664-h10-f0.3-l3-bal-g24-d1-s1 | h10 f0.3 l3 bal s1 | 0 (0) | 5..6 | 46 / 10 | — | -2.62 | -2.978 | -3.266 | 1.15 | -0.14 | 0.1028 | 0.1150 | 0.116 | fine | 0/4400 | 87/100 / 96/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 4 | k1664-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | 0 (0) | 5..6 | 31 / 10 | — | -2.76 | -2.948 | -3.288 | 1.18 | -0.11 | 0.1050 | 0.1168 | 0.109 | fine | 0/4400 | 83/100 / 96/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 5 | k1664-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | 0 (0) | 5..7 | 49 / 14 | — | -2.55 | -2.933 | -3.182 | 1.19 | -0.10 | 0.1118 | 0.1181 | 0.088 | fine | 0/4100 | 57/100 / 89/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 6 | **base-r0406** | h10 f0.3 l3 uni s0 | 0 (0) | 3..7 | 43 / 16 | — | -1.67 | -2.835 | -3.089 | 1.29 | 0.00 | 0.1021 | 0.1109 | 0.118 | fine | 1/4100 ⚠ | 80/100 / 97/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 7 | k1664-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | 0 (0) | 5..6 | 27 / 12 | — | -2.41 | -2.750 | -3.183 | 1.38 | 0.08 | 0.1125 | 0.1184 | 0.086 | seedvar | 0/1500 | — | — |
| 8 | k1664-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | 0 (0) | 3..7 | 27 / 11 | — | -2.43 | -3.000 | -3.232 | 1.13 | -0.17 | 0.1000 | 0.1139 | 0.125 | walk | 1/1800 ⚠ | 88/100 / 98/100 / 100/100 / 100/100 (1/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1664-h10-f0.3-l3-bal-g24-d1-s0 robust -3.0 t42 w15/2; base-r0406 bsc 0.11 t303 w17/4; k1664-h12-f0.3-l3-uni-g24-d1-s0 bsc 0.12 t57 w12/2

### Screen 1 ranking (top 25 of 72 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1664-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | -2.76 | 10/100 / 0/100 | 11/100 / 29/100 | 10 | 5..6 |
| 2 | k1664-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -2.67 | 13/100 / 0/100 | 9/100 / 40/100 | 16 | 4..6 |
| 3 | k1664-h10-f0.3-l3-bal-g24-d1-s1 | h10 f0.3 l3 bal s1 | -2.62 | 6/100 / 1/100 | 12/100 / 39/100 | 10 | 5..6 |
| 4 | k1664-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | -2.55 | 16/100 / 1/100 | 10/100 / 23/100 | 14 | 5..7 |
| 5 | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -2.50 | 7/100 / 1/100 | 15/100 / 43/100 | 15 | 4..6 |
| 6 | k1664-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | -2.43 | 8/100 / 1/100 | 18/100 / 41/100 | 11 | 3..7 |
| 7 | k1664-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | -2.41 | 12/100 / 2/100 | 7/100 / 38/100 | 12 | 5..6 |
| 8 | k1664-h8-f0.5-l3-uni-g24-d1-s0 | h8 f0.5 l3 uni s0 | -2.41 | 12/100 / 1/100 | 13/100 / 42/100 | 20 | 3..7 |
| 9 | k1664-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.34 | 19/100 / 2/100 | 10/100 / 23/100 | 19 | 5..7 |
| 10 | k1664-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | -2.25 | 19/100 / 4/100 | 6/100 / 27/100 | 12 | 3..8 |
| 11 | k1664-h12-f0.3-l4-bal-g24-d1-s1 | h12 f0.3 l4 bal s1 | -2.25 | 19/100 / 2/100 | 10/100 / 33/100 | 35 | 5..7 |
| 12 | k1664-h10-f0.3-l3-uni-g24-d1-s0 | h10 f0.3 l3 uni s0 | -2.18 | 13/100 / 1/100 | 24/100 / 52/100 | 14 | 3..7 |
| 13 | k1664-h8-f0.3-l3-bal-g24-d1-s1 | h8 f0.3 l3 bal s1 | -2.13 | 17/100 / 1/100 | 21/100 / 55/100 | 17 | 4..6 |
| 14 | k1664-h10-f0.3-l4-bal-g24-d1-s0 | h10 f0.3 l4 bal s0 | -2.12 | 21/100 / 1/100 | 20/100 / 49/100 | 39 | 5..6 |
| 15 | k1664-h10-f0.3-l4-bal-g24-d1-s1 | h10 f0.3 l4 bal s1 | -2.11 | 24/100 / 1/100 | 19/100 / 47/100 | 20 | 5..6 |
| 16 | k1664-h12-f0.3-l3-uni-g24-d1-s1 | h12 f0.3 l3 uni s1 | -2.00 | 11/100 / 4/100 | 18/100 / 42/100 | 11 | 3..7 |
| 17 | k1664-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -1.99 | 21/100 / 4/100 | 12/100 / 34/100 | 29 | 5..7 |
| 18 | k1664-h8-f0.3-l3-bal-g24-d1-s0 | h8 f0.3 l3 bal s0 | -1.92 | 14/100 / 2/100 | 29/100 / 56/100 | 15 | 4..6 |
| 19 | k1664-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | -1.92 | 30/100 / 4/100 | 10/100 / 38/100 | 23 | 6..8 |
| 20 | k1664-h12-f0.5-l3-uni-g24-d1-s1 | h12 f0.5 l3 uni s1 | -1.90 | 28/100 / 5/100 | 11/100 / 32/100 | 12 | 4..9 |
| 21 | k1664-h10-f0.3-l4-uni-g24-d1-s1 | h10 f0.3 l4 uni s1 | -1.90 | 28/100 / 2/100 | 18/100 / 49/100 | 33 | 4..7 |
| 22 | k1664-h10-f0.3-l3-uni-g24-d1-s1 | h10 f0.3 l3 uni s1 | -1.88 | 16/100 / 3/100 | 21/100 / 54/100 | 13 | 3..7 |
| 23 | k1664-h12-f0.3-l4-uni-g24-d1-s0 | h12 f0.3 l4 uni s0 | -1.84 | 33/100 / 3/100 | 13/100 / 49/100 | 27 | 3..8 |
| 24 | k1664-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | -1.80 | 30/100 / 5/100 | 14/100 / 35/100 | 25 | 4..9 |
| 25 | k1664-h8-f0.5-l3-uni-g24-d1-s1 | h8 f0.5 l3 uni s1 | -1.79 | 35/100 / 2/100 | 20/100 / 56/100 | 14 | 3..7 |
| 29 | base-r0406 | h10 f0.3 l3 uni s0 | -1.67 | 20/100 / 3/100 | 34/100 / 61/100 | 16 | 3..7 |

### Screen 0: 72 built/attempted; verdicts {"pass": 71, "min_w2": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 35 | -1.40 | -2.76 |
| placement | uniform | 36 | -1.17 | -2.43 |
| light | 3 | 35 | -1.60 | -2.76 |
| light | 4 | 36 | -0.98 | -2.25 |
| heavy_frac | 0.3 | 23 | -1.93 | -2.76 |
| heavy_frac | 0.5 | 24 | -1.51 | -2.67 |
| heavy_frac | 0.7 | 24 | -0.43 | -1.48 |
| heavy_deg | 10 | 24 | -1.35 | -2.62 |
| heavy_deg | 12 | 23 | -1.12 | -2.76 |
| heavy_deg | 8 | 24 | -1.37 | -2.67 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 36/36; uniform: mean 0.3, max 3, zero in 28/36

### Seed variance

Screen-1 score: mean within-config SD 0.078 (over 35 configs with ≥2 seeds) vs between-config SD of the config means 0.791.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1664-h10-f0.3-l3-bal-g24-d1 | 1,0 | -2.62, -2.50 | -3.266, -3.224 | 0.041 | -2.978, -3.000 | 0.1150, 0.1143 | 0.0007 |
| k1664-h8-f0.5-l3-bal-g24-d1 | 0,1 | -2.67, -2.41 | -3.196, -3.183 | 0.012 | -2.991, -2.750 | 0.1168, 0.1184 | 0.0015 |

## k = 1600 (R = 0.3906); Shannon -4.358 dB, p_cap 0.1498; frozen recipe (r0391, harness 200/pt): Es/N0@1% -3.108, @10% -3.384, p@1% 0.1075, p@10% 0.1176

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.470 dB, p 0.1226 — from trial-A:k1600-h12-f0.3-l3-bal-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1600-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | 0 (0) | 5..6 | 34 / 14 | — | -2.78 | -3.270 | -3.474 | 1.09 | -0.18 | 0.1090 | 0.1226 | 0.112 | fine | 0/4300 | 82/100 / 98/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 2 | **base-r0391** | h10 f0.3 l3 uni s0 | 0 (0) | 2..7 | 69 / 11 | info_free_block_rows=1 | -1.72 | -3.091 | -3.360 | 1.27 | 0.00 | 0.1100 | 0.1180 | 0.109 | fine | 5/4200 ⚠ | 81/100 / 99/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 3 | k1600-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | 0 (0) | 5..7 | 79 / 14 | — | -2.20 | -3.044 | -3.318 | 1.31 | 0.05 | 0.1169 | 0.1241 | 0.089 | fine | 0/4300 | 45/100 / 87/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 4 | k1600-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | 0 (0) | 5..6 | 41 / 19 | — | -2.37 | -3.000 | -3.436 | 1.36 | 0.09 | 0.1150 | 0.1209 | 0.095 | walk | 0/1600 | 70/100 / 96/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 5 | k1600-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | 0 (0) | 5..6 | 40 / 14 | — | -2.69 | -3.000 | -3.474 | 1.36 | 0.09 | 0.1125 | 0.1212 | 0.102 | walk | 0/1800 | 73/100 / 96/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 6 | k1600-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 5..7 | 38 / 17 | — | -2.52 | -3.221 | -3.409 | 1.14 | -0.13 | 0.1150 | 0.1237 | 0.095 | fine | 1/4200 ⚠ | 54/100 / 89/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 7 | k1600-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | 0 (0) | 5..7 | 33 / 20 | — | -2.34 | -3.175 | -3.407 | 1.18 | -0.08 | 0.1171 | 0.1232 | 0.088 | fine | 3/4200 ⚠ | 30/100 / 81/100 / 100/100 / 100/100 (1/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1600-h12-f0.3-l3-bal-g24-d1-s1 robust -3.3009 t28 w17/4; base-r0391 bsc 0.1226 t4 w11/2; base-r0391 bsc 0.125 t4 w11/2; base-r0391 awgn -3.0 t141 w11/2; base-r0391 awgn -3.25 t141 w11/2; base-r0391 awgn -3.125 t141 w11/2; k1600-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.115 t313 w18/2; k1600-h10-f0.5-l3-bal-g24-d1-s1 bsc 0.115 t131 w20/2; k1600-h10-f0.5-l3-bal-g24-d1-s1 bsc 0.12 t131 w20/2; k1600-h10-f0.5-l3-bal-g24-d1-s1 bsc 0.1175 t131 w20/2

### Screen 1 ranking (top 25 of 70 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1600-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | -2.78 | 13/100 / 0/100 | 10/100 / 23/100 | 14 | 5..6 |
| 2 | k1600-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | -2.69 | 8/100 / 1/100 | 11/100 / 24/100 | 14 | 5..6 |
| 3 | k1600-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.52 | 21/100 / 1/100 | 7/100 / 29/100 | 17 | 5..7 |
| 4 | k1600-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -2.37 | 18/100 / 1/100 | 12/100 / 36/100 | 19 | 5..6 |
| 5 | k1600-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | -2.34 | 22/100 / 2/100 | 9/100 / 22/100 | 20 | 5..7 |
| 6 | k1600-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | -2.20 | 22/100 / 3/100 | 10/100 / 23/100 | 14 | 5..7 |
| 7 | k1600-h12-f0.3-l3-uni-g24-d1-s1 | h12 f0.3 l3 uni s1 | -2.16 | 13/100 / 1/100 | 26/100 / 52/100 | 15 | 3..7 |
| 8 | k1600-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -2.10 | 23/100 / 2/100 | 14/100 / 35/100 | 28 | 4..6 |
| 9 | k1600-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | -2.10 | 21/100 / 3/100 | 10/100 / 36/100 | 21 | 5..6 |
| 10 | k1600-h10-f0.3-l3-bal-g24-d1-s1 | h10 f0.3 l3 bal s1 | -2.10 | 13/100 / 3/100 | 15/100 / 39/100 | 10 | 4..6 |
| 11 | k1600-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | -1.97 | 34/100 / 6/100 | 8/100 / 23/100 | 14 | 6..7 |
| 12 | k1600-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | -1.97 | 24/100 / 5/100 | 10/100 / 32/100 | 23 | 4..8 |
| 13 | k1600-h12-f0.5-l3-uni-g24-d1-s1 | h12 f0.5 l3 uni s1 | -1.90 | 25/100 / 9/100 | 9/100 / 25/100 | 13 | 4..8 |
| 14 | k1600-h12-f0.3-l4-bal-g24-d1-s1 | h12 f0.3 l4 bal s1 | -1.83 | 33/100 / 5/100 | 10/100 / 40/100 | 38 | 5..7 |
| 15 | base-r0391 | h10 f0.3 l3 uni s0 | -1.72 | 33/100 / 2/100 | 27/100 / 58/100 | 11 | 2..7 |
| 16 | k1600-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -1.69 | 36/100 / 8/100 | 11/100 / 36/100 | 35 | 5..7 |
| 17 | k1600-h8-f0.3-l3-bal-g24-d1-s0 | h8 f0.3 l3 bal s0 | -1.65 | 23/100 / 4/100 | 24/100 / 62/100 | 11 | 4..5 |
| 18 | k1600-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | -1.52 | 42/100 / 7/100 | 16/100 / 48/100 | 21 | 3..8 |
| 19 | k1600-h10-f0.3-l4-bal-g24-d1-s1 | h10 f0.3 l4 bal s1 | -1.52 | 39/100 / 6/100 | 19/100 / 52/100 | 51 | 5..6 |
| 20 | k1600-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | -1.51 | 25/100 / 4/100 | 35/100 / 67/100 | 12 | 3..7 |
| 21 | k1600-h8-f0.5-l3-uni-g24-d1-s0 | h8 f0.5 l3 uni s0 | -1.49 | 37/100 / 4/100 | 28/100 / 62/100 | 16 | 3..7 |
| 22 | k1600-h10-f0.3-l4-bal-g24-d1-s0 | h10 f0.3 l4 bal s0 | -1.45 | 49/100 / 9/100 | 13/100 / 52/100 | 43 | 5..6 |
| 23 | k1600-h8-f0.5-l3-uni-g24-d1-s1 | h8 f0.5 l3 uni s1 | -1.40 | 35/100 / 8/100 | 23/100 / 58/100 | 13 | 3..7 |
| 24 | k1600-h8-f0.3-l3-uni-g24-d1-s1 | h8 f0.3 l3 uni s1 | -1.35 | 34/100 / 5/100 | 38/100 / 70/100 | 20 | 3..6 |
| 25 | k1600-h10-f0.3-l3-uni-g24-d1-s1 | h10 f0.3 l3 uni s1 | -1.32 | 32/100 / 6/100 | 38/100 / 69/100 | 15 | 2..7 |

### Screen 0: 72 built/attempted; verdicts {"pass": 69, "min_w2": 3}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 34 | -1.25 | -2.78 |
| placement | uniform | 35 | -0.87 | -2.16 |
| light | 3 | 33 | -1.38 | -2.78 |
| light | 4 | 36 | -0.76 | -1.83 |
| heavy_frac | 0.3 | 23 | -1.56 | -2.78 |
| heavy_frac | 0.5 | 23 | -1.36 | -2.52 |
| heavy_frac | 0.7 | 23 | -0.25 | -0.99 |
| heavy_deg | 10 | 23 | -1.04 | -2.52 |
| heavy_deg | 12 | 24 | -1.10 | -2.78 |
| heavy_deg | 8 | 22 | -1.02 | -2.10 |

Restarts rejected for an info-free block row (rule e), per placement: uniform: mean 0.5, max 3, zero in 26/36; balanced: mean 0.0, max 0, zero in 36/36

### Seed variance

Screen-1 score: mean within-config SD 0.051 (over 33 configs with ≥2 seeds) vs between-config SD of the config means 0.768.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1600-h12-f0.3-l3-bal-g24-d1 | 1,0 | -2.78, -2.69 | -3.470, -3.474 | 0.004 | -3.270, -3.000 | 0.1226, 0.1212 | 0.0014 |
| k1600-h10-f0.5-l3-bal-g24-d1 | 0,1 | -2.52, -2.34 | -3.429, -3.407 | 0.022 | -3.221, -3.175 | 0.1237, 0.1230 | 0.0008 |

## k = 1280 (R = 0.3125); Shannon -5.624 dB, p_cap 0.1834; frozen recipe (r0313, harness 200/pt): Es/N0@1% -3.858, @10% -4.201, p@1% 0.1200, p@10% 0.1398

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.585 dB, p 0.1550 — from trial-A:k1280-h12-f0.5-l3-bal-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1280-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | 0 (0) | 4..6 | 77 / 17 | — | -2.51 | -4.278 | -4.585 | 1.35 | -0.53 | 0.1471 | 0.1550 | 0.085 | fine | 0/4300 | 68/100 / 91/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 2 | k1280-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 3..5 | 76 / 28 | — | -1.99 | -4.271 | -4.483 | 1.35 | -0.52 | 0.1400 | 0.1505 | 0.103 | fine | 0/4400 | 64/100 / 90/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 3 | k1280-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | 0 (0) | 5..6 | 99 / 29 | — | -2.18 | -4.229 | -4.500 | 1.39 | -0.48 | 0.1475 | 0.1538 | 0.084 | fine | 0/4100 | 50/100 / 80/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 4 | k1280-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | 0 (0) | 3..5 | 130 / 14 | — | -1.97 | -4.000 | -4.537 | 1.62 | -0.25 | 0.1375 | 0.1472 | 0.110 | walk | 0/1800 | 76/100 / 98/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 5 | **base-r0313** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 58 / 12 | info_free_block_rows=5 | -0.60 | -3.750 | -4.190 | 1.87 | 0.00 | 0.1316 | 0.1400 | 0.126 | fine | 22/4500 ⚠ | 80/100 / 98/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 6 | k1280-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | 0 (0) | 4..5 | 43 / 14 | — | -2.26 | -4.333 | -4.591 | 1.29 | -0.58 | 0.1455 | 0.1550 | 0.089 | fine | 3/4100 ⚠ | 57/100 / 89/100 / 100/100 / 100/100 (2/100) | 0/100 |
| 7 | k1280-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 3..5 | 128 / 10 | — | -2.55 | -4.316 | -4.560 | 1.31 | -0.57 | 0.1000 | 0.1535 | 0.219 | walk | 19/2500 ⚠ | 54/100 / 84/100 / 100/100 / 100/100 (0/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): base-r0313 awgn -4.5849 t82 w12/2; base-r0313 awgn -4.3349 t82 w12/2; base-r0313 bsc 0.155 t60 w12/2; base-r0313 bsc 0.16 t60 w12/2; base-r0313 bsc 0.155 t60 w12/2; base-r0313 bsc 0.16 t60 w12/2; base-r0313 awgn -4.5 t82 w12/2; base-r0313 awgn -4.25 t82 w12/2; base-r0313 awgn -4.0 t82 w12/2; base-r0313 awgn -3.75 t442 w14/2; base-r0313 awgn -3.75 t341 w12/2; base-r0313 awgn -3.75 t359 w14/2; base-r0313 awgn -4.0 t341 w12/2; base-r0313 awgn -4.0 t442 w14/2; base-r0313 awgn -4.0 t359 w14/2; base-r0313 awgn -3.875 t82 w12/2; base-r0313 awgn -3.875 t341 w12/2; base-r0313 awgn -3.875 t359 w14/2; base-r0313 awgn -3.875 t442 w14/2; base-r0313 bsc 0.125 t177 w12/2; base-r0313 bsc 0.13 t177 w12/2; base-r0313 bsc 0.1275 t177 w12/2; base-r0313 awgn -3.8467 t82 w12/2; k1280-h10-f0.5-l3-bal-g24-d1-s1 awgn -4.25 t182 w14/2; k1280-h10-f0.5-l3-bal-g24-d1-s1 awgn -4.5 t182 w14/2; k1280-h10-f0.5-l3-bal-g24-d1-s1 awgn -4.375 t182 w14/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.16 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.16 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.15 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.15 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.165 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.145 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.145 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.14 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.14 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.135 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.135 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.13 t0 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.13 t46 w10/2; k1280-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.125 t46 w10/2 …

### Screen 1 ranking (top 25 of 73 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1280-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.55 | 12/100 / 0/100 | 15/100 / 42/100 | 10 | 3..5 |
| 2 | k1280-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | -2.51 | 8/100 / 2/100 | 10/100 / 27/100 | 17 | 4..6 |
| 3 | k1280-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | -2.26 | 10/100 / 3/100 | 10/100 / 40/100 | 14 | 4..5 |
| 4 | k1280-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | -2.18 | 19/100 / 2/100 | 12/100 / 36/100 | 29 | 5..6 |
| 5 | k1280-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -1.99 | 20/100 / 1/100 | 26/100 / 66/100 | 28 | 3..5 |
| 6 | k1280-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | -1.97 | 17/100 / 1/100 | 35/100 / 63/100 | 14 | 3..5 |
| 7 | k1280-h12-f0.3-l4-bal-g24-d1-s1 | h12 f0.3 l4 bal s1 | -1.90 | 14/100 / 4/100 | 21/100 / 43/100 | 48 | 4..5 |
| 8 | k1280-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | -1.85 | 26/100 / 4/100 | 13/100 / 45/100 | 23 | 3..7 |
| 9 | k1280-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | -1.84 | 18/100 / 2/100 | 31/100 / 57/100 | 29 | 4..5 |
| 10 | k1280-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | -1.75 | 18/100 / 6/100 | 16/100 / 52/100 | 19 | 3..6 |
| 11 | k1280-h10-f0.5-l3-uni-g24-d1-s1 | h10 f0.5 l3 uni s1 | -1.73 | 22/100 / 4/100 | 21/100 / 53/100 | 10 | 3..6 |
| 12 | k1280-h12-f0.3-l4-uni-g24-d1-s0 | h12 f0.3 l4 uni s0 | -1.73 | 20/100 / 3/100 | 27/100 / 62/100 | 43 | 3..6 |
| 13 | k1280-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -1.70 | 20/100 / 4/100 | 25/100 / 55/100 | 47 | 4..5 |
| 14 | k1280-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | -1.67 | 14/100 / 4/100 | 35/100 / 63/100 | 17 | 3..5 |
| 15 | k1280-h10-f0.3-l4-bal-g24-d1-s1 | h10 f0.3 l4 bal s1 | -1.61 | 20/100 / 5/100 | 27/100 / 59/100 | 21 | 3..5 |
| 16 | k1280-h12-f0.5-l3-uni-g24-d1-s1 | h12 f0.5 l3 uni s1 | -1.55 | 28/100 / 6/100 | 24/100 / 51/100 | 17 | 3..7 |
| 17 | k1280-h10-f0.3-l4-bal-g24-d1-s0 | h10 f0.3 l4 bal s0 | -1.53 | 27/100 / 6/100 | 22/100 / 62/100 | 52 | 4..5 |
| 18 | k1280-h12-f0.3-l4-uni-g24-d1-s1 | h12 f0.3 l4 uni s1 | -1.47 | 28/100 / 5/100 | 32/100 / 62/100 | 19 | 3..6 |
| 19 | k1280-h8-f0.5-l3-uni-g24-d1-s0 | h8 f0.5 l3 uni s0 | -1.45 | 28/100 / 4/100 | 38/100 / 71/100 | 15 | 3..6 |
| 20 | k1280-h8-f0.5-l4-bal-g24-d1-s0 | h8 f0.5 l4 bal s0 | -1.35 | 31/100 / 5/100 | 42/100 / 70/100 | 63 | 3..5 |
| 21 | k1280-h8-f0.3-l3-bal-g24-d1-s0 | h8 f0.3 l3 bal s0 | -1.35 | 25/100 / 6/100 | 43/100 / 71/100 | 16 | 3..5 |
| 22 | k1280-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | -1.28 | 25/100 / 5/100 | 61/100 / 79/100 | 14 | 3..6 |
| 23 | k1280-h8-f0.7-l3-bal-g24-d1-s0 | h8 f0.7 l3 bal s0 | -1.27 | 36/100 / 11/100 | 25/100 / 64/100 | 15 | 4..5 |
| 24 | k1280-h8-f0.3-l3-bal-g24-d1-s1 | h8 f0.3 l3 bal s1 | -1.24 | 31/100 / 7/100 | 44/100 / 74/100 | 21 | 3..5 |
| 25 | k1280-h10-f0.5-l4-bal-g24-d1-s0 | h10 f0.5 l4 bal s0 | -1.23 | 39/100 / 11/100 | 28/100 / 61/100 | 51 | 4..6 |
| 57 | base-r0313 | h10 f0.3 l3 uni s0 | -0.60 | 58/100 / 22/100 | 77/100 / 92/100 | 12 | 2..6 |

### Screen 0: 72 built/attempted; verdicts {"pass": 72}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 36 | -1.28 | -2.55 |
| placement | uniform | 36 | -0.92 | -1.85 |
| light | 3 | 36 | -1.27 | -2.55 |
| light | 4 | 36 | -0.93 | -1.90 |
| heavy_frac | 0.3 | 24 | -1.28 | -1.97 |
| heavy_frac | 0.5 | 24 | -1.48 | -2.55 |
| heavy_frac | 0.7 | 24 | -0.54 | -1.27 |
| heavy_deg | 10 | 24 | -1.09 | -2.55 |
| heavy_deg | 12 | 24 | -1.11 | -2.51 |
| heavy_deg | 8 | 24 | -1.10 | -1.99 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 36/36; uniform: mean 13.6, max 244, zero in 16/36

### Seed variance

Screen-1 score: mean within-config SD 0.072 (over 36 configs with ≥2 seeds) vs between-config SD of the config means 0.569.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1280-h10-f0.5-l3-bal-g24-d1 | 0,1 | -2.55, -2.26 | -4.560, -4.588 | 0.028 | -4.316, -4.333 | 0.1535, 0.1550 | 0.0015 |
| k1280-h12-f0.5-l3-bal-g24-d1 | 1,0 | -2.51, -2.18 | -4.585, -4.500 | 0.085 | -4.278, -4.229 | 0.1550, 0.1547 | 0.0003 |

## k = 1216 (R = 0.2969); Shannon -5.903 dB, p_cap 0.1908; frozen recipe (r0297, harness 200/pt): Es/N0@1% -4.000, @10% -4.479, p@1% 0.1422, p@10% 0.1490

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.825 dB, p 0.1592 — from trial-A:k1216-h10-f0.5-l3-uni-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1216-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | 0 (0) | 4..5 | 58 / 34 | — | -2.42 | -4.554 | -4.757 | 1.35 | -0.45 | 0.1518 | 0.1590 | 0.089 | fine | 0/4100 | 37/100 / 83/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 2 | k1216-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 4..5 | 56 / 20 | — | -2.29 | -4.500 | -4.767 | 1.40 | -0.39 | 0.1400 | 0.1578 | 0.119 | fine | 0/4600 | 64/100 / 93/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 3 | k1216-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | 0 (0) | 4..5 | 88 / 19 | — | -2.65 | -4.472 | -4.824 | 1.43 | -0.37 | 0.1542 | 0.1615 | 0.083 | fine | 0/4200 | 44/100 / 81/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 4 | k1216-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | 0 (0) | 4..6 | 47 / 23 | — | -2.37 | -4.375 | -4.736 | 1.53 | -0.27 | 0.1550 | 0.1620 | 0.081 | walk | 0/1600 | 54/100 / 89/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 5 | k1216-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 4..5 | 69 / 22 | — | -2.51 | -4.375 | -4.803 | 1.53 | -0.27 | 0.1517 | 0.1600 | 0.089 | walk | 0/1600 | 38/100 / 81/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 6 | **base-r0297** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 35 / 25 | info_free_block_rows=5 | -0.84 | -4.106 | -4.500 | 1.80 | 0.00 | 0.1335 | 0.1498 | 0.136 | fine | 1/4600 ⚠ | 73/100 / 97/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 7 | k1216-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | 0 (0) | 4..6 | 74 / 23 | — | -2.87 | -4.549 | -4.782 | 1.35 | -0.44 | 0.1518 | 0.1609 | 0.089 | fine | 2/4200 ⚠ | 49/100 / 86/100 / 100/100 / 100/100 (1/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1216-h8-f0.5-l3-bal-g24-d1-s0 robust -4.5 t87 w32/4; base-r0297 bsc 0.135 t239 w17/3; k1216-h12-f0.5-l3-bal-g24-d1-s1 bsc 0.155 t216 w26/2; k1216-h12-f0.5-l3-bal-g24-d1-s1 bsc 0.1525 t216 w26/2

### Screen 1 ranking (top 25 of 73 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1216-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | -2.87 | 13/100 / 1/100 | 4/100 / 20/100 | 23 | 4..6 |
| 2 | k1216-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | -2.65 | 9/100 / 2/100 | 5/100 / 28/100 | 19 | 4..5 |
| 3 | k1216-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.51 | 9/100 / 2/100 | 8/100 / 30/100 | 22 | 4..5 |
| 4 | k1216-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -2.42 | 16/100 / 1/100 | 10/100 / 39/100 | 34 | 4..5 |
| 5 | k1216-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | -2.37 | 21/100 / 4/100 | 4/100 / 23/100 | 23 | 4..6 |
| 6 | k1216-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -2.29 | 18/100 / 1/100 | 16/100 / 37/100 | 20 | 4..5 |
| 7 | k1216-h10-f0.5-l3-uni-g24-d1-s1 | h10 f0.5 l3 uni s1 | -2.26 | 14/100 / 2/100 | 12/100 / 35/100 | 22 | 3..6 |
| 8 | k1216-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -2.13 | 16/100 / 1/100 | 25/100 / 50/100 | 18 | 3..5 |
| 9 | k1216-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | -2.11 | 17/100 / 2/100 | 15/100 / 43/100 | 21 | 3..5 |
| 10 | k1216-h12-f0.5-l3-uni-g24-d1-s1 | h12 f0.5 l3 uni s1 | -2.09 | 25/100 / 7/100 | 4/100 / 33/100 | 20 | 3..7 |
| 11 | k1216-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | -2.02 | 15/100 / 2/100 | 25/100 / 42/100 | 21 | 4..5 |
| 12 | k1216-h12-f0.5-l3-uni-g24-d1-s0 | h12 f0.5 l3 uni s0 | -1.97 | 22/100 / 5/100 | 10/100 / 35/100 | 23 | 3..7 |
| 13 | k1216-h12-f0.3-l4-bal-g24-d1-s1 | h12 f0.3 l4 bal s1 | -1.96 | 18/100 / 5/100 | 12/100 / 37/100 | 30 | 4..5 |
| 14 | k1216-h10-f0.5-l3-uni-g24-d1-s0 | h10 f0.5 l3 uni s0 | -1.95 | 26/100 / 4/100 | 10/100 / 39/100 | 24 | 3..6 |
| 15 | k1216-h12-f0.3-l3-uni-g24-d1-s0 | h12 f0.3 l3 uni s0 | -1.95 | 20/100 / 1/100 | 34/100 / 61/100 | 15 | 3..6 |
| 16 | k1216-h12-f0.3-l4-uni-g24-d1-s1 | h12 f0.3 l4 uni s1 | -1.86 | 19/100 / 4/100 | 17/100 / 46/100 | 34 | 3..6 |
| 17 | k1216-h10-f0.3-l3-bal-g24-d1-s1 | h10 f0.3 l3 bal s1 | -1.85 | 20/100 / 2/100 | 29/100 / 52/100 | 20 | 4..5 |
| 18 | k1216-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | -1.85 | 18/100 / 2/100 | 31/100 / 55/100 | 20 | 3..5 |
| 19 | k1216-h10-f0.3-l4-bal-g24-d1-s0 | h10 f0.3 l4 bal s0 | -1.84 | 26/100 / 4/100 | 14/100 / 43/100 | 62 | 3..5 |
| 20 | k1216-h12-f0.3-l4-uni-g24-d1-s0 | h12 f0.3 l4 uni s0 | -1.72 | 32/100 / 3/100 | 19/100 / 56/100 | 51 | 3..6 |
| 21 | k1216-h8-f0.7-l3-bal-g24-d1-s0 | h8 f0.7 l3 bal s0 | -1.70 | 25/100 / 5/100 | 18/100 / 50/100 | 21 | 4..5 |
| 22 | k1216-h8-f0.3-l4-bal-g24-d1-s0 | h8 f0.3 l4 bal s0 | -1.67 | 29/100 / 3/100 | 25/100 / 57/100 | 28 | 3..5 |
| 23 | k1216-h10-f0.3-l4-bal-g24-d1-s1 | h10 f0.3 l4 bal s1 | -1.67 | 20/100 / 7/100 | 19/100 / 48/100 | 48 | 3..5 |
| 24 | k1216-h8-f0.3-l3-bal-g24-d1-s1 | h8 f0.3 l3 bal s1 | -1.55 | 26/100 / 4/100 | 33/100 / 59/100 | 14 | 2..4 |
| 25 | k1216-h8-f0.7-l3-bal-g24-d1-s1 | h8 f0.7 l3 bal s1 | -1.48 | 32/100 / 10/100 | 19/100 / 44/100 | 25 | 4..5 |
| 57 | base-r0297 | h10 f0.3 l3 uni s0 | -0.84 | 48/100 / 15/100 | 60/100 / 81/100 | 25 | 2..6 |

### Screen 0: 72 built/attempted; verdicts {"pass": 72}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 36 | -1.54 | -2.87 |
| placement | uniform | 36 | -1.07 | -2.26 |
| light | 3 | 36 | -1.54 | -2.87 |
| light | 4 | 36 | -1.08 | -2.42 |
| heavy_frac | 0.3 | 24 | -1.51 | -2.42 |
| heavy_frac | 0.5 | 24 | -1.63 | -2.87 |
| heavy_frac | 0.7 | 24 | -0.79 | -1.70 |
| heavy_deg | 10 | 24 | -1.35 | -2.65 |
| heavy_deg | 12 | 24 | -1.30 | -2.87 |
| heavy_deg | 8 | 24 | -1.27 | -2.29 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 36/36; uniform: mean 13.6, max 175, zero in 13/36

### Seed variance

Screen-1 score: mean within-config SD 0.084 (over 36 configs with ≥2 seeds) vs between-config SD of the config means 0.624.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1216-h12-f0.5-l3-bal-g24-d1 | 1,0 | -2.87, -2.37 | -4.782, -4.736 | 0.046 | -4.549, -4.375 | 0.1609, 0.1620 | 0.0011 |
| k1216-h10-f0.5-l3-bal-g24-d1 | 1,0 | -2.65, -2.51 | -4.824, -4.803 | 0.021 | -4.472, -4.375 | 0.1615, 0.1600 | 0.0015 |

