# Construction search — trial-B2

Mode `trial`; settings `{"s1_trials": 100, "walk_trials": 100, "fine_trials": 500, "side_trials": 100, "n_finalists": 2, "n_fine": 99, "seedvar_configs": 0, "chunk": 50, "workers": 12, "ks": [1664, 1280, 1600, 1216], "min_w2": 10, "s1_anchor": {"1664": {"es10": -3.1955028707748854, "p10": 0.11684241398541552, "src": "trial-A:k1664-h8-f0.5-l3-bal-g24-d1-s0"}, "1280": {"es10": -4.584906804806198, "p10": 0.155, "src": "trial-A:k1280-h12-f0.5-l3-bal-g24-d1-s1"}, "1600": {"es10": -3.470196884904838, "p10": 0.12260404969671047, "src": "trial-A:k1600-h12-f0.3-l3-bal-g24-d1-s1"}, "1216": {"es10": -4.824912185866601, "p10": 0.15917021883573235, "src": "trial-A:k1216-h10-f0.5-l3-uni-g24-d1-s1"}}}`; runs logged: 1.  
Decoder: production `holo.core.ldpc.decode` (min-sum α 0.8, 60 it + one sum-product retry). Seeds: bsc 100000+t, awgn 200000+t, eras 300000+t, robust 500000+t (common random numbers across codes).  
Screen 1 = 4 points at the frozen recipe's 10 % points: awgn +(0.0, 0.25) dB, bsc +(0.0, 0.005); score = mean ln BLER (0/n floored at 0.5/n), lower is better.  
Walks start at the frozen 10 % grid point (0.25 dB / 0.005 grids of the harness), easy side until two consecutive 0/n, hard side until BLER ≥ 0.5; 1 %/10 % by log-linear interpolation (harness tables.interp_x). `fine` = top-N at the fine trial count on the bracketing grid points + midpoint.  
Constraints: girth > 4, no info-free block row, min two-info-bit pair weight ≥ 10. Search configs RESTART on an info-free block row (rule e); baselines are the frozen recipe exactly.

Total worker CPU recorded: 2.83 h over 292 built configs.

## k = 1664 (R = 0.4062); Shannon -4.125 dB, p_cap 0.1437; frozen recipe (r0406, harness 200/pt): Es/N0@1% -2.825, @10% -3.108, p@1% 0.1039, p@10% 0.1118

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.196 dB, p 0.1168 — from trial-A:k1664-h8-f0.5-l3-bal-g24-d1-s0

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | 0 (0) | 2..6 | 29 / 21 | — | -4.26 | -3.103 | -3.316 | 1.02 | -0.27 | 0.1150 | 0.1205 | 0.079 | fine | 0/4000 | 52/100 / 87/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 2 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h-s1 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h s1 | 0 (0) | 2..6 | 45 / 13 | — | -3.43 | -3.058 | -3.338 | 1.07 | -0.22 | 0.1000 | 0.1169 | 0.125 | fine | 0/4500 | 89/100 / 98/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 3 | k1664-h10-f0.3-l3-bal-g24-d1-s3 | h10 f0.3 l3 bal s3 | 0 (0) | 5..6 | 56 / 14 | — | -2.74 | -3.000 | -3.231 | 1.13 | -0.17 | 0.1086 | 0.1145 | 0.098 | fine | 0/4000 | 84/100 / 98/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 4 | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | 0 (0) | 4..6 | 26 / 15 | — | -2.50 | -3.000 | -3.224 | 1.13 | -0.17 | 0.1028 | 0.1143 | 0.116 | fine | 0/4300 | 80/100 / 96/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 5 | k1664-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 4..6 | 33 / 16 | — | -2.67 | -2.991 | -3.192 | 1.13 | -0.16 | 0.1100 | 0.1164 | 0.094 | fine | 0/4000 | 54/100 / 91/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 6 | k1664-h10-f0.3-l3-bal-g24-d1-s1 | h10 f0.3 l3 bal s1 | 0 (0) | 5..6 | 46 / 10 | — | -2.62 | -2.978 | -3.266 | 1.15 | -0.14 | 0.1028 | 0.1150 | 0.116 | fine | 0/4400 | 87/100 / 96/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 7 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s0 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s0 | 0 (0) | 4..7 | 23 / 15 | — | -2.63 | -2.936 | -3.169 | 1.19 | -0.10 | 0.1078 | 0.1159 | 0.100 | fine | 0/4200 | 59/100 / 90/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 8 | k1664-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | 0 (0) | 5..6 | 27 / 12 | — | -2.41 | -2.892 | -3.183 | 1.23 | -0.06 | 0.1090 | 0.1175 | 0.097 | fine | 0/4100 | 33/100 / 80/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 9 | **base-r0406** | h10 f0.3 l3 uni s0 | 0 (0) | 3..7 | 43 / 16 | — | -1.67 | -2.835 | -3.089 | 1.29 | 0.00 | 0.1021 | 0.1109 | 0.118 | fine | 1/4100 ⚠ | 80/100 / 97/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 10 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s3 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s3 | 0 (0) | 5..7 | 10 / 17 | — | -2.61 | -2.979 | -3.196 | 1.15 | -0.14 | 0.1000 | 0.1147 | 0.125 | fine | 1/4400 ⚠ | 61/100 / 91/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1664-h10-f0.3-l3-bal-g24-d1-s0 robust -3.0 t42 w15/2; base-r0406 bsc 0.11 t303 w17/4; k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s3 awgn -3.0 t335 w10/1; k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s3 robust -3.0 t4 w10/1

### Screen 1 ranking (top 25 of 63 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | -4.26 | 0/100 / 0/100 | 2/100 / 8/100 | 21 | 2..6 |
| 2 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h-s1 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h s1 | -3.43 | 1/100 / 0/100 | 9/100 / 24/100 | 13 | 2..6 |
| 3 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s2 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s2 | -3.41 | 4/100 / 1/100 | 3/100 / 10/100 | 15 | 2..6 |
| 4 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s1 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s1 | -3.39 | 5/100 / 0/100 | 3/100 / 17/100 | 15 | 2..6 |
| 5 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l-s0 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l s0 | -3.35 | 4/100 / 0/100 | 5/100 / 15/100 | 18 | 2..6 |
| 6 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l-s1 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l s1 | -3.25 | 9/100 / 0/100 | 5/100 / 10/100 | 32 | 2..6 |
| 7 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l-s1 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l s1 | -3.24 | 4/100 / 0/100 | 5/100 / 24/100 | 19 | 2..6 |
| 8 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l-s2 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l s2 | -3.22 | 9/100 / 1/100 | 2/100 / 14/100 | 19 | 2..6 |
| 9 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s3 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s3 | -3.22 | 6/100 / 0/100 | 6/100 / 14/100 | 18 | 2..6 |
| 10 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l-s2 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l s2 | -3.13 | 6/100 / 0/100 | 6/100 / 20/100 | 14 | 2..6 |
| 11 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l-s3 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25l s3 | -3.11 | 6/100 / 0/100 | 6/100 / 22/100 | 22 | 2..6 |
| 12 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l-s3 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l s3 | -2.96 | 12/100 / 0/100 | 8/100 / 15/100 | 25 | 2..6 |
| 13 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l-s0 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.50l s0 | -2.91 | 9/100 / 2/100 | 4/100 / 12/100 | 29 | 2..6 |
| 14 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h s2 | -2.89 | 4/100 / 1/100 | 9/100 / 27/100 | 17 | 2..6 |
| 15 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h-s0 | k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h s0 | -2.82 | 5/100 / 1/100 | 9/100 / 28/100 | 22 | 2..6 |
| 16 | k1664-h10-f0.3-l3-bal-g24-d1-s3 | h10 f0.3 l3 bal s3 | -2.74 | 4/100 / 0/100 | 18/100 / 48/100 | 14 | 5..6 |
| 17 | k1664-h8-f0.5-l3-bal-g24-d1-s2 | h8 f0.5 l3 bal s2 | -2.70 | 12/100 / 0/100 | 10/100 / 34/100 | 15 | 4..6 |
| 18 | k1664-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -2.67 | 13/100 / 0/100 | 9/100 / 40/100 | 16 | 4..6 |
| 19 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s0 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s0 | -2.63 | 15/100 / 0/100 | 11/100 / 33/100 | 15 | 4..7 |
| 20 | k1664-h10-f0.3-l3-bal-g24-d1-s1 | h10 f0.3 l3 bal s1 | -2.62 | 6/100 / 1/100 | 12/100 / 39/100 | 10 | 5..6 |
| 21 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s3 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s3 | -2.61 | 10/100 / 0/100 | 14/100 / 41/100 | 17 | 5..7 |
| 22 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s2 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s2 | -2.61 | 13/100 / 0/100 | 12/100 / 38/100 | 20 | 5..7 |
| 23 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s1 | k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s1 | -2.58 | 11/100 / 1/100 | 8/100 / 37/100 | 18 | 5..7 |
| 24 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25l-s3 | k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25l s3 | -2.51 | 15/100 / 1/100 | 9/100 / 32/100 | 31 | 2..7 |
| 25 | k1664-h10-f0.3-l3-bal-g24-d1-s0 | h10 f0.3 l3 bal s0 | -2.50 | 7/100 / 1/100 | 15/100 / 43/100 | 15 | 4..6 |
| 41 | base-r0406 | h10 f0.3 l3 uni s0 | -1.67 | 20/100 / 3/100 | 34/100 / 61/100 | 16 | 3..7 |

### Screen 0: 72 built/attempted; verdicts {"pass": 62, "anchor_infeasible": 8, "min_w2": 2}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 62 | -2.09 | -4.26 |
| light | 3 | 8 | -2.53 | -2.74 |
| light | None | 54 | -2.03 | -4.26 |
| heavy_frac | 0.3 | 4 | -2.58 | -2.74 |
| heavy_frac | 0.5 | 4 | -2.49 | -2.70 |
| heavy_frac | None | 54 | -2.03 | -4.26 |
| heavy_deg | 10 | 4 | -2.58 | -2.74 |
| heavy_deg | 8 | 4 | -2.49 | -2.70 |
| heavy_deg | None | 54 | -2.03 | -4.26 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 64/64

### Seed variance

Screen-1 score: mean within-config SD 0.148 (over 16 configs with ≥2 seeds) vs between-config SD of the config means 0.869.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1 | 0,3 | -2.63, -2.61, -2.61, -2.58 | -3.196, -3.199 | 0.004 | -2.936, -2.979 | 0.1159, 0.1147 | 0.0012 |
| k1664-h10-f0.3-l3-bal-g24-d1 | 3,1,0 | -2.74, -2.62, -2.50, -2.46 | -3.236, -3.266, -3.224 | 0.041 | -3.000, -2.978, -3.000 | 0.1145, 0.1150, 0.1143 | 0.0007 |
| k1664-h8-f0.5-l3-bal-g24-d1 | 0,1 | -2.70, -2.67, -2.41, -2.17 | -3.196, -3.183 | 0.012 | -2.991, -2.892 | 0.1168, 0.1184 | 0.0015 |

## k = 1600 (R = 0.3906); Shannon -4.358 dB, p_cap 0.1498; frozen recipe (r0391, harness 200/pt): Es/N0@1% -3.108, @10% -3.384, p@1% 0.1075, p@10% 0.1176

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -3.470 dB, p 0.1226 — from trial-A:k1600-h12-f0.3-l3-bal-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1600-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | 0 (0) | 5..6 | 34 / 14 | — | -2.78 | -3.270 | -3.474 | 1.09 | -0.18 | 0.1090 | 0.1226 | 0.112 | fine | 0/4300 | 82/100 / 98/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 2 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s2 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s2 | 0 (0) | 5..7 | 51 / 19 | — | -2.70 | -3.241 | -3.466 | 1.12 | -0.15 | 0.1143 | 0.1223 | 0.096 | fine | 0/4200 | 47/100 / 83/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 3 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s1 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s1 | 0 (0) | 5..7 | 40 / 21 | — | -2.66 | -3.203 | -3.424 | 1.15 | -0.11 | 0.1121 | 0.1250 | 0.103 | fine | 0/4300 | 50/100 / 85/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 4 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h-s1 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h s1 | 0 (0) | 2..7 | 34 / 21 | — | -3.31 | -3.192 | -3.408 | 1.17 | -0.10 | 0.1206 | 0.1268 | 0.078 | fine | 0/4100 | 50/100 / 88/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 5 | **base-r0391** | h10 f0.3 l3 uni s0 | 0 (0) | 2..7 | 69 / 11 | info_free_block_rows=1 | -1.72 | -3.091 | -3.360 | 1.27 | 0.00 | 0.1100 | 0.1180 | 0.109 | fine | 5/4200 ⚠ | 81/100 / 99/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 6 | k1600-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | 0 (0) | 5..6 | 40 / 14 | — | -2.69 | -3.250 | -3.474 | 1.11 | -0.16 | 0.1100 | 0.1212 | 0.109 | fine | 3/4400 ⚠ | 73/100 / 96/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 7 | k1600-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | 0 (0) | 5..7 | 38 / 17 | — | -2.52 | -3.221 | -3.409 | 1.14 | -0.13 | 0.1150 | 0.1237 | 0.095 | fine | 1/4200 ⚠ | 54/100 / 89/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 8 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h s2 | 0 (0) | 2..6 | 70 / 11 | — | -3.26 | -3.217 | -3.597 | 1.14 | -0.13 | 0.1100 | 0.1263 | 0.109 | fine | 7/4300 ⚠ | 74/100 / 96/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 9 | k1600-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | 0 (0) | 5..7 | 33 / 20 | — | -2.34 | -3.175 | -3.407 | 1.18 | -0.08 | 0.1171 | 0.1232 | 0.088 | fine | 3/4200 ⚠ | 30/100 / 81/100 / 100/100 / 100/100 (1/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1600-h12-f0.3-l3-bal-g24-d1-s1 robust -3.3009 t28 w17/4; base-r0391 bsc 0.1226 t4 w11/2; base-r0391 bsc 0.125 t4 w11/2; base-r0391 awgn -3.0 t141 w11/2; base-r0391 awgn -3.25 t141 w11/2; base-r0391 awgn -3.125 t141 w11/2; k1600-h12-f0.3-l3-bal-g24-d1-s0 bsc 0.11 t127 w33/6; k1600-h12-f0.3-l3-bal-g24-d1-s0 bsc 0.115 t127 w33/6; k1600-h12-f0.3-l3-bal-g24-d1-s0 bsc 0.1125 t127 w33/6; k1600-h10-f0.5-l3-bal-g24-d1-s0 bsc 0.115 t313 w18/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 awgn -3.4702 t28 w11/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 awgn -3.0 t305 w11/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 awgn -3.25 t305 w11/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 awgn -3.125 t305 w11/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 bsc 0.11 t385 w11/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 bsc 0.115 t385 w11/2; k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 bsc 0.1125 t385 w11/2; k1600-h10-f0.5-l3-bal-g24-d1-s1 bsc 0.115 t131 w20/2; k1600-h10-f0.5-l3-bal-g24-d1-s1 bsc 0.12 t131 w20/2; k1600-h10-f0.5-l3-bal-g24-d1-s1 bsc 0.1175 t131 w20/2

### Screen 1 ranking (top 25 of 64 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h-s1 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h s1 | -3.31 | 20/100 / 0/100 | 2/100 / 9/100 | 21 | 2..7 |
| 2 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h s2 | -3.26 | 4/100 / 0/100 | 6/100 / 18/100 | 11 | 2..6 |
| 3 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25l-s2 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25l s2 | -3.21 | 10/100 / 0/100 | 3/100 / 18/100 | 21 | 2..7 |
| 4 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | -3.09 | 16/100 / 1/100 | 3/100 / 9/100 | 15 | 2..7 |
| 5 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25l-s0 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25l s0 | -3.08 | 10/100 / 0/100 | 6/100 / 15/100 | 21 | 2..7 |
| 6 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25l-s3 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25l s3 | -3.03 | 12/100 / 0/100 | 5/100 / 18/100 | 17 | 2..7 |
| 7 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s3 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h s3 | -2.87 | 7/100 / 0/100 | 11/100 / 27/100 | 13 | 2..6 |
| 8 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s0 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h s0 | -2.86 | 9/100 / 0/100 | 9/100 / 27/100 | 12 | 2..6 |
| 9 | k1600-h12-f0.3-l3-bal-g24-d1-s1 | h12 f0.3 l3 bal s1 | -2.78 | 13/100 / 0/100 | 10/100 / 23/100 | 14 | 5..6 |
| 10 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l-s3 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l s3 | -2.74 | 26/100 / 1/100 | 6/100 / 11/100 | 21 | 2..6 |
| 11 | k1600-h12-f0.3-l3-bal-g24-d1-s2 | h12 f0.3 l3 bal s2 | -2.71 | 11/100 / 0/100 | 13/100 / 27/100 | 12 | 5..6 |
| 12 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s2 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s2 | -2.70 | 11/100 / 1/100 | 7/100 / 27/100 | 19 | 5..7 |
| 13 | k1600-h12-f0.3-l3-bal-g24-d1-s0 | h12 f0.3 l3 bal s0 | -2.69 | 8/100 / 1/100 | 11/100 / 24/100 | 14 | 5..6 |
| 14 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s1 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s1 | -2.66 | 18/100 / 1/100 | 7/100 / 19/100 | 21 | 5..7 |
| 15 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l-s1 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l s1 | -2.60 | 22/100 / 2/100 | 4/100 / 17/100 | 31 | 2..6 |
| 16 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h-s2 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h s2 | -2.59 | 21/100 / 2/100 | 5/100 / 15/100 | 11 | 2..7 |
| 17 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h-s3 | k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h s3 | -2.54 | 20/100 / 3/100 | 5/100 / 13/100 | 13 | 2..7 |
| 18 | k1600-h10-f0.5-l3-bal-g24-d1-s0 | h10 f0.5 l3 bal s0 | -2.52 | 21/100 / 1/100 | 7/100 / 29/100 | 17 | 5..7 |
| 19 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s1 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h s1 | -2.50 | 7/100 / 2/100 | 11/100 / 29/100 | 18 | 2..6 |
| 20 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s0 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1 s0 | -2.47 | 16/100 / 2/100 | 7/100 / 23/100 | 14 | 5..7 |
| 21 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l-s0 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l s0 | -2.47 | 26/100 / 2/100 | 5/100 / 20/100 | 21 | 2..6 |
| 22 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l-s2 | k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.50l s2 | -2.41 | 28/100 / 4/100 | 3/100 / 19/100 | 31 | 2..6 |
| 23 | k1600-h10-f0.5-l3-bal-g24-d1-s1 | h10 f0.5 l3 bal s1 | -2.34 | 22/100 / 2/100 | 9/100 / 22/100 | 20 | 5..7 |
| 24 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.500-s2 | k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.500 s2 | -2.31 | 27/100 / 1/100 | 9/100 / 40/100 | 12 | 5..7 |
| 25 | k1600-h12-f0.3-l3-bal-g24-d1-s3 | h12 f0.3 l3 bal s3 | -2.30 | 11/100 / 3/100 | 9/100 / 34/100 | 12 | 5..6 |
| 31 | base-r0391 | h10 f0.3 l3 uni s0 | -1.72 | 33/100 / 2/100 | 27/100 / 58/100 | 11 | 2..7 |

### Screen 0: 72 built/attempted; verdicts {"pass": 63, "anchor_infeasible": 8, "min_w2": 1}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 63 | -1.70 | -3.31 |
| light | 3 | 8 | -2.42 | -2.78 |
| light | None | 55 | -1.59 | -3.31 |
| heavy_frac | 0.3 | 4 | -2.62 | -2.78 |
| heavy_frac | 0.5 | 4 | -2.23 | -2.52 |
| heavy_frac | None | 55 | -1.59 | -3.31 |
| heavy_deg | 10 | 4 | -2.23 | -2.52 |
| heavy_deg | 12 | 4 | -2.62 | -2.78 |
| heavy_deg | None | 55 | -1.59 | -3.31 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 64/64

### Seed variance

Screen-1 score: mean within-config SD 0.132 (over 16 configs with ≥2 seeds) vs between-config SD of the config means 0.968.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1600-h12-f0.3-l3-bal-g24-d1 | 1,0 | -2.78, -2.71, -2.69, -2.30 | -3.470, -3.474 | 0.004 | -3.270, -3.250 | 0.1226, 0.1212 | 0.0014 |
| k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1 | 2,1 | -2.70, -2.66, -2.47, -2.28 | -3.457, -3.433 | 0.024 | -3.241, -3.203 | 0.1223, 0.1250 | 0.0027 |
| k1600-h10-f0.5-l3-bal-g24-d1 | 0,1 | -2.52, -2.34, -2.04, -2.02 | -3.429, -3.407 | 0.022 | -3.221, -3.175 | 0.1237, 0.1230 | 0.0008 |

## k = 1280 (R = 0.3125); Shannon -5.624 dB, p_cap 0.1834; frozen recipe (r0313, harness 200/pt): Es/N0@1% -3.858, @10% -4.201, p@1% 0.1200, p@10% 0.1398

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.585 dB, p 0.1550 — from trial-A:k1280-h12-f0.5-l3-bal-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | 0 (0) | 2..6 | 58 / 19 | — | -3.12 | -4.341 | -4.624 | 1.28 | -0.59 | 0.1506 | 0.1578 | 0.076 | fine | 0/4200 | 65/100 / 93/100 / 100/100 / 100/100 (0/100) [1 undet] | 0/100 |
| 2 | k1280-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | 0 (0) | 4..6 | 77 / 17 | — | -2.51 | -4.278 | -4.585 | 1.35 | -0.53 | 0.1471 | 0.1550 | 0.085 | fine | 0/4300 | 68/100 / 91/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 3 | k1280-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 3..5 | 76 / 28 | — | -1.99 | -4.271 | -4.483 | 1.35 | -0.52 | 0.1400 | 0.1505 | 0.103 | fine | 0/4400 | 64/100 / 90/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 4 | k1280-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | 0 (0) | 5..6 | 99 / 29 | — | -2.18 | -4.229 | -4.500 | 1.39 | -0.48 | 0.1475 | 0.1538 | 0.084 | fine | 0/4100 | 50/100 / 80/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 5 | k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s2 | k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1 s2 | 0 (0) | 4..8 | 59 / 15 | — | -1.59 | -4.091 | -4.365 | 1.53 | -0.34 | 0.1425 | 0.1522 | 0.097 | fine | 0/4100 | 29/100 / 77/100 / 100/100 / 100/100 (1/100) [2 undet] | 0/100 |
| 6 | k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s1 | k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1 s1 | 0 (0) | 4..7 | 56 / 18 | — | -1.48 | -4.080 | -4.350 | 1.54 | -0.33 | 0.1444 | 0.1511 | 0.092 | fine | 0/4300 | 10/100 / 58/100 / 99/100 / 100/100 (0/100) | 0/100 |
| 7 | **base-r0313** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 58 / 12 | info_free_block_rows=5 | -0.60 | -3.750 | -4.190 | 1.87 | 0.00 | 0.1316 | 0.1400 | 0.126 | fine | 22/4500 ⚠ | 80/100 / 98/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 8 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s1 | 1 (0) | 2..5 | 75 / 11 | — | -3.26 | -4.458 | -4.694 | 1.17 | -0.71 | 0.1480 | 0.1570 | 0.083 | fine | 1/4000 ⚠ | 75/100 / 94/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 9 | k1280-h12-f0.5-l3-bal-g24-d1-s3 | h12 f0.5 l3 bal s3 | 0 (0) | 4..6 | 73 / 17 | — | -2.73 | -4.364 | -4.629 | 1.26 | -0.61 | 0.1400 | 0.1555 | 0.103 | fine | 5/4500 ⚠ | 54/100 / 92/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 robust -4.3253 t12 w19/2; k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s2 robust -4.0967 t5 w15/2; k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s2 robust -4.0967 t5 w15/2; base-r0313 awgn -4.5849 t82 w12/2; base-r0313 awgn -4.3349 t82 w12/2; base-r0313 bsc 0.155 t60 w12/2; base-r0313 bsc 0.16 t60 w12/2; base-r0313 bsc 0.155 t60 w12/2; base-r0313 bsc 0.16 t60 w12/2; base-r0313 awgn -4.5 t82 w12/2; base-r0313 awgn -4.25 t82 w12/2; base-r0313 awgn -4.0 t82 w12/2; base-r0313 awgn -3.75 t442 w14/2; base-r0313 awgn -3.75 t341 w12/2; base-r0313 awgn -3.75 t359 w14/2; base-r0313 awgn -4.0 t341 w12/2; base-r0313 awgn -4.0 t442 w14/2; base-r0313 awgn -4.0 t359 w14/2; base-r0313 awgn -3.875 t82 w12/2; base-r0313 awgn -3.875 t341 w12/2; base-r0313 awgn -3.875 t359 w14/2; base-r0313 awgn -3.875 t442 w14/2; base-r0313 bsc 0.125 t177 w12/2; base-r0313 bsc 0.13 t177 w12/2; base-r0313 bsc 0.1275 t177 w12/2; base-r0313 awgn -3.8467 t82 w12/2; k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 bsc 0.155 t160 w11/2; k1280-h12-f0.5-l3-bal-g24-d1-s3 awgn -4.0 t201 w17/2; k1280-h12-f0.5-l3-bal-g24-d1-s3 awgn -4.25 t201 w17/2; k1280-h12-f0.5-l3-bal-g24-d1-s3 awgn -4.125 t201 w17/2; k1280-h12-f0.5-l3-bal-g24-d1-s3 bsc 0.135 t186 w20/2; k1280-h12-f0.5-l3-bal-g24-d1-s3 bsc 0.1325 t186 w20/2; k1280-h12-f0.5-l3-bal-g24-d1-s3 robust -4.25 t1 w20/2

### Screen 1 ranking (top 25 of 67 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s1 | -3.26 | 5/100 / 0/100 | 4/100 / 22/100 | 11 | 2..5 |
| 2 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | -3.12 | 9/100 / 0/100 | 5/100 / 17/100 | 19 | 2..6 |
| 3 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s3 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s3 | -3.10 | 6/100 / 0/100 | 7/100 / 20/100 | 16 | 2..5 |
| 4 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | -2.90 | 6/100 / 0/100 | 10/100 / 30/100 | 15 | 2..5 |
| 5 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s2 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s2 | -2.84 | 5/100 / 1/100 | 10/100 / 23/100 | 13 | 2..5 |
| 6 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h-s3 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h s3 | -2.83 | 16/100 / 0/100 | 6/100 / 25/100 | 23 | 2..6 |
| 7 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h-s2 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h s2 | -2.82 | 14/100 / 1/100 | 6/100 / 15/100 | 24 | 2..6 |
| 8 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s1 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s1 | -2.77 | 8/100 / 0/100 | 10/100 / 39/100 | 17 | 2..5 |
| 9 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s0 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s0 | -2.75 | 8/100 / 1/100 | 9/100 / 23/100 | 16 | 2..5 |
| 10 | k1280-h12-f0.5-l3-bal-g24-d1-s3 | h12 f0.5 l3 bal s3 | -2.73 | 7/100 / 1/100 | 9/100 / 29/100 | 17 | 4..6 |
| 11 | k1280-h12-f0.5-l3-bal-g24-d1-s2 | h12 f0.5 l3 bal s2 | -2.70 | 13/100 / 0/100 | 10/100 / 31/100 | 15 | 4..6 |
| 12 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s3 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s3 | -2.70 | 10/100 / 0/100 | 13/100 / 32/100 | 14 | 2..5 |
| 13 | k1280-h12-f0.5-l3-bal-g24-d1-s1 | h12 f0.5 l3 bal s1 | -2.51 | 8/100 / 2/100 | 10/100 / 27/100 | 17 | 4..6 |
| 14 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s2 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s2 | -2.37 | 11/100 / 2/100 | 11/100 / 31/100 | 13 | 2..5 |
| 15 | k1280-h8-f0.5-l3-bal-g24-d1-s3 | h8 f0.5 l3 bal s3 | -2.18 | 17/100 / 0/100 | 32/100 / 60/100 | 12 | 4..5 |
| 16 | k1280-h12-f0.5-l3-bal-g24-d1-s0 | h12 f0.5 l3 bal s0 | -2.18 | 19/100 / 2/100 | 12/100 / 36/100 | 29 | 5..6 |
| 17 | k1280-h8-f0.5-l3-bal-g24-d1-s2 | h8 f0.5 l3 bal s2 | -2.12 | 18/100 / 1/100 | 22/100 / 52/100 | 17 | 4..5 |
| 18 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25l-s0 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25l s0 | -2.05 | 18/100 / 2/100 | 16/100 / 48/100 | 25 | 2..6 |
| 19 | k1280-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -1.99 | 20/100 / 1/100 | 26/100 / 66/100 | 28 | 3..5 |
| 20 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25l-s2 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25l s2 | -1.93 | 24/100 / 3/100 | 16/100 / 38/100 | 21 | 2..7 |
| 21 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50l-s3 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50l s3 | -1.87 | 19/100 / 3/100 | 20/100 / 50/100 | 85 | 2..5 |
| 22 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25l-s1 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.25l s1 | -1.85 | 19/100 / 3/100 | 20/100 / 53/100 | 36 | 2..5 |
| 23 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25l-s3 | k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25l s3 | -1.84 | 25/100 / 4/100 | 15/100 / 42/100 | 34 | 2..6 |
| 24 | k1280-h8-f0.5-l3-bal-g24-d1-s1 | h8 f0.5 l3 bal s1 | -1.84 | 18/100 / 2/100 | 31/100 / 57/100 | 29 | 4..5 |
| 25 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p1.00-s2 | k1280-h8-f0.5-l3-bal-g24-d1+ara-p1.00 s2 | -1.77 | 31/100 / 4/100 | 14/100 / 49/100 | 34 | 2..6 |
| 57 | base-r0313 | h10 f0.3 l3 uni s0 | -0.60 | 58/100 / 22/100 | 77/100 / 92/100 | 12 | 2..6 |

### Screen 0: 72 built/attempted; verdicts {"pass": 66, "anchor_infeasible": 4, "min_w2": 2}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 66 | -1.55 | -3.26 |
| light | 3 | 8 | -2.28 | -2.73 |
| light | None | 58 | -1.45 | -3.26 |
| heavy_frac | 0.5 | 8 | -2.28 | -2.73 |
| heavy_frac | None | 58 | -1.45 | -3.26 |
| heavy_deg | 12 | 4 | -2.53 | -2.73 |
| heavy_deg | 8 | 4 | -2.03 | -2.18 |
| heavy_deg | None | 58 | -1.45 | -3.26 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 68/68

### Seed variance

Screen-1 score: mean within-config SD 0.123 (over 17 configs with ≥2 seeds) vs between-config SD of the config means 0.852.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1280-h12-f0.5-l3-bal-g24-d1 | 3,1,0 | -2.73, -2.70, -2.51, -2.18 | -4.629, -4.585, -4.500 | 0.129 | -4.364, -4.278, -4.229 | 0.1555, 0.1550, 0.1547 | 0.0007 |
| k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1 | 2,1 | -1.59, -1.48, -1.38, -1.13 | -4.392, -4.350 | 0.041 | -4.091, -4.080 | 0.1522, 0.1511 | 0.0011 |

## k = 1216 (R = 0.2969); Shannon -5.903 dB, p_cap 0.1908; frozen recipe (r0297, harness 200/pt): Es/N0@1% -4.000, @10% -4.479, p@1% 0.1422, p@10% 0.1490

Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 -4.825 dB, p 0.1592 — from trial-A:k1216-h10-f0.5-l3-uni-g24-d1-s1

### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only

| # | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s1 | 0 (0) | 2..5 | 114 / 24 | — | -3.78 | -4.663 | -4.953 | 1.24 | -0.56 | 0.1566 | 0.1639 | 0.077 | fine | 0/4200 | 64/100 / 94/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 2 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s0 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s0 | 0 (0) | 2..5 | 61 / 21 | — | -3.65 | -4.653 | -4.973 | 1.25 | -0.55 | 0.1490 | 0.1636 | 0.096 | fine | 0/4300 | 85/100 / 99/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 3 | k1216-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | 0 (0) | 4..5 | 58 / 34 | — | -2.42 | -4.554 | -4.757 | 1.35 | -0.45 | 0.1518 | 0.1590 | 0.089 | fine | 0/4100 | 37/100 / 83/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 4 | k1216-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | 0 (0) | 4..5 | 56 / 20 | — | -2.29 | -4.500 | -4.767 | 1.40 | -0.39 | 0.1400 | 0.1578 | 0.119 | fine | 0/4600 | 64/100 / 93/100 / 100/100 / 100/100 (1/100) [1 undet] | 0/100 |
| 5 | k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s0 | k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1 s0 | 0 (0) | 4..6 | 56 / 39 | — | -1.74 | -4.449 | -4.668 | 1.45 | -0.34 | 0.1450 | 0.1564 | 0.106 | fine | 0/4400 | 50/100 / 83/100 / 100/100 / 100/100 (1/100) | 0/100 |
| 6 | k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s2 | k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1 s2 | 0 (0) | 4..6 | 49 / 29 | — | -1.71 | -4.432 | -4.705 | 1.47 | -0.33 | 0.1504 | 0.1567 | 0.092 | fine | 0/4000 | 29/100 / 81/100 / 100/100 / 100/100 (0/100) | 0/100 |
| 7 | **base-r0297** | h10 f0.3 l3 uni s0 | 0 (0) | 2..6 | 35 / 25 | info_free_block_rows=5 | -0.84 | -4.106 | -4.500 | 1.80 | 0.00 | 0.1335 | 0.1498 | 0.136 | fine | 1/4600 ⚠ | 73/100 / 97/100 / 100/100 / 100/100 (1/100) | 0/100 |

Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): k1216-h8-f0.5-l3-bal-g24-d1-s0 robust -4.5 t87 w32/4; base-r0297 bsc 0.135 t239 w17/3

### Screen 1 ranking (top 25 of 69 + baseline)

| # | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |
|---|---|---|---|---|---|---|---|
| 1 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s1 | -3.78 | 5/100 / 0/100 | 1/100 / 11/100 | 24 | 2..5 |
| 2 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s0 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s0 | -3.65 | 1/100 / 1/100 | 3/100 / 15/100 | 21 | 2..5 |
| 3 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s2 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s2 | -3.38 | 3/100 / 1/100 | 4/100 / 11/100 | 15 | 2..5 |
| 4 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h-s3 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h s3 | -3.29 | 8/100 / 0/100 | 3/100 / 16/100 | 39 | 2..5 |
| 5 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s3 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h s3 | -3.26 | 3/100 / 2/100 | 3/100 / 12/100 | 19 | 2..5 |
| 6 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h-s2 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h s2 | -3.25 | 6/100 / 0/100 | 4/100 / 19/100 | 25 | 2..5 |
| 7 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h-s0 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h s0 | -3.17 | 12/100 / 0/100 | 3/100 / 17/100 | 45 | 2..5 |
| 8 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s0 | -3.14 | 5/100 / 0/100 | 7/100 / 20/100 | 22 | 2..5 |
| 9 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h-s1 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h s1 | -3.12 | 8/100 / 1/100 | 3/100 / 16/100 | 27 | 2..5 |
| 10 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h-s3 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h s3 | -3.10 | 17/100 / 2/100 | 1/100 / 12/100 | 29 | 2..5 |
| 11 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h-s0 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25h s0 | -3.04 | 12/100 / 1/100 | 4/100 / 11/100 | 45 | 2..5 |
| 12 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h-s1 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h s1 | -3.01 | 13/100 / 1/100 | 3/100 / 15/100 | 54 | 2..5 |
| 13 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s3 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s3 | -2.92 | 7/100 / 1/100 | 7/100 / 17/100 | 23 | 2..5 |
| 14 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s2 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s2 | -2.89 | 5/100 / 1/100 | 9/100 / 21/100 | 33 | 2..5 |
| 15 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l-s2 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l s2 | -2.77 | 16/100 / 0/100 | 8/100 / 24/100 | 46 | 2..5 |
| 16 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s1 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.25h s1 | -2.76 | 10/100 / 1/100 | 6/100 / 27/100 | 18 | 2..5 |
| 17 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p1.00-s0 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p1.00 s0 | -2.73 | 19/100 / 1/100 | 4/100 / 24/100 | 31 | 2..6 |
| 18 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h-s2 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.50h s2 | -2.56 | 14/100 / 2/100 | 7/100 / 18/100 | 72 | 2..5 |
| 19 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l-s1 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l s1 | -2.56 | 17/100 / 1/100 | 7/100 / 30/100 | 33 | 2..6 |
| 20 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l-s3 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l s3 | -2.46 | 13/100 / 2/100 | 8/100 / 26/100 | 59 | 2..6 |
| 21 | k1216-h12-f0.3-l4-bal-g24-d1-s0 | h12 f0.3 l4 bal s0 | -2.42 | 16/100 / 1/100 | 10/100 / 39/100 | 34 | 4..5 |
| 22 | k1216-h8-f0.5-l3-bal-g24-d1-s2 | h8 f0.5 l3 bal s2 | -2.38 | 14/100 / 1/100 | 14/100 / 38/100 | 24 | 4..5 |
| 23 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p1.00-s1 | k1216-h8-f0.5-l3-bal-g24-d1+ara-p1.00 s1 | -2.33 | 23/100 / 4/100 | 4/100 / 24/100 | 60 | 2..6 |
| 24 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l-s0 | k1216-h12-f0.3-l4-bal-g24-d1+ara-p0.25l s0 | -2.33 | 17/100 / 4/100 | 5/100 / 26/100 | 40 | 2..5 |
| 25 | k1216-h8-f0.5-l3-bal-g24-d1-s0 | h8 f0.5 l3 bal s0 | -2.29 | 18/100 / 1/100 | 16/100 / 37/100 | 20 | 4..5 |
| 55 | base-r0297 | h10 f0.3 l3 uni s0 | -0.84 | 48/100 / 15/100 | 60/100 / 81/100 | 25 | 2..6 |

### Screen 0: 72 built/attempted; verdicts {"pass": 68, "anchor_infeasible": 4}

| factor | value | n | mean s1 score | best |
|---|---|---|---|---|
| placement | balanced | 68 | -1.97 | -3.78 |
| light | 3 | 4 | -2.22 | -2.38 |
| light | 4 | 4 | -2.16 | -2.42 |
| light | None | 60 | -1.94 | -3.78 |
| heavy_frac | 0.3 | 4 | -2.16 | -2.42 |
| heavy_frac | 0.5 | 4 | -2.22 | -2.38 |
| heavy_frac | None | 60 | -1.94 | -3.78 |
| heavy_deg | 12 | 4 | -2.16 | -2.42 |
| heavy_deg | 8 | 4 | -2.22 | -2.38 |
| heavy_deg | None | 60 | -1.94 | -3.78 |

Restarts rejected for an info-free block row (rule e), per placement: balanced: mean 0.0, max 0, zero in 68/68

### Seed variance

Screen-1 score: mean within-config SD 0.133 (over 17 configs with ≥2 seeds) vs between-config SD of the config means 0.914.

| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |
|---|---|---|---|---|---|---|---|
| k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h | 1,0 | -3.78, -3.65, -3.38, -3.26 | -4.944, -4.982 | 0.037 | -4.663, -4.653 | 0.1639, 0.1636 | 0.0003 |
| k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1 | 0,2 | -1.74, -1.71, -1.59, -1.36 | -4.699, -4.694 | 0.005 | -4.449, -4.432 | 0.1564, 0.1569 | 0.0005 |


---

# Tier B2 — ARA-precoded e-IRA and IRAA vs the plain e-IRA

Suffixes: `ara-pF{h|l}` = fraction F of info block-columns precoded (h = heavy/first columns, l = light/last), punctured intermediate bits, exclusive anchor block row per precoded column (rule f); `iraa-qF` = fraction F of parity block rows are second-accumulator outputs, every first-accumulator block linked; `x1` = one linked block per second-accumulator block row. Constructions: variants.py docstring.

## k = 1664

### Screen 1, PAIRED on (base config, seed) against the plain e-IRA row of the same config and seed (Δ = variant − plain; negative = better; common random numbers)

| variant | n pairs | mean Δ s1 | SD Δ | better / worse | mean s1 | best s1 | s0 verdicts | min w1 (min) | min w2 mean / min | chk deg | parity deg-2 frac | punct 1-SR | CPU s / 100 decodes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain | 8 | 0.00 | 0.00 | 0 / 0 | -2.53 | -2.74 | {"pass": 8} | 26 | 14.5 / 10 | 4..6 | — | — | 3.1 |
| ara-p0.25h | 7 | -0.84 | 0.40 | 7 / 0 | -3.35 | -4.26 | {"pass": 7, "min_w2": 1} | 29 | 16.1 / 8 | 2..6 | 1.00 | 1.00 | 3.0 |
| ara-p0.25l | 7 | -0.36 | 0.38 | 6 / 1 | -2.87 | -3.35 | {"pass": 7, "min_w2": 1} | 28 | 20.2 / 9 | 2..7 | 1.00 | 1.00 | 3.1 |
| ara-p0.5h | 8 | 1.48 | 0.40 | 0 / 8 | -1.06 | -1.79 | {"pass": 8} | 30 | 15.8 / 11 | 2..6 | 1.00 | 1.00 | 5.2 |
| ara-p0.5l | 8 | 0.18 | 0.71 | 4 / 4 | -2.36 | -3.25 | {"pass": 8} | 67 | 42.1 / 19 | 2..6 | 1.00 | 1.00 | 4.1 |
| ara-p1 | 0 | — | — | 0 / 0 | — | — | {"anchor_infeasible": 8} | — | — / — | — | — | — | — |
| iraa-q0.25 | 8 | 1.38 | 0.38 | 0 / 8 | -1.15 | -1.75 | {"pass": 8} | 29 | 55.2 / 39 | 4..9 | 0.26 | — | 4.1 |
| iraa-q0.25x1 | 8 | 0.37 | 0.42 | 2 / 6 | -2.17 | -2.63 | {"pass": 8} | 10 | 20.4 / 15 | 4..7 | 0.74 | — | 3.1 |
| iraa-q0.5 | 8 | 1.00 | 0.50 | 0 / 8 | -1.53 | -2.14 | {"pass": 8} | 29 | 24.0 / 15 | 4..7 | 0.50 | — | 3.6 |

### Screen 2 (walks; `fine` = 500 trials around the 1 % point). Recipe r0406 and the best clean plain e-IRA (Tier A winner) Es/N0@1% = -3.000 dB are the references

| code | family | Es/N0@1% | src | Δ vs best plain | Δ vs recipe | gap dB | p@1% | gap bit | min w2 | undet/trials | robust f0.1% | mean iters @ awgn pt nearest 1 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k1664-h8-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | ara-p0.25h | -3.103 | fine | -0.10 | -0.27 | 1.02 | 0.1150 | 0.079 | 21 | 0/4000 | 52/100 | 61.2 |
| k1664-h10-f0.3-l3-bal-g24-d1+ara-p0.25h-s1 | ara-p0.25h | -3.058 | fine | -0.06 | -0.22 | 1.07 | 0.1000 | 0.125 | 13 | 0/4500 | 89/100 | 60.0 |
| k1664-h10-f0.3-l3-bal-g24-d1-s0 | plain | -3.000 | fine | 0.00 | -0.17 | 1.13 | 0.1028 | 0.116 | 15 | 0/4300 | 80/100 | 57.0 |
| k1664-h10-f0.3-l3-bal-g24-d1-s3 | plain | -3.000 | fine | 0.00 | -0.17 | 1.13 | 0.1086 | 0.098 | 14 | 0/4000 | 84/100 | 58.0 |
| k1664-h8-f0.5-l3-bal-g24-d1-s0 | plain | -2.991 | fine | 0.01 | -0.16 | 1.13 | 0.1100 | 0.094 | 16 | 0/4000 | 54/100 | 45.0 |
| k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s3 | iraa-q0.25x1 | -2.979 | fine | 0.02 | -0.14 | 1.15 | 0.1000 | 0.125 | 17 | 1/4400 ⚠ | 61/100 | 41.5 |
| k1664-h10-f0.3-l3-bal-g24-d1-s1 | plain | -2.978 | fine | 0.02 | -0.14 | 1.15 | 0.1028 | 0.116 | 10 | 0/4400 | 87/100 | 59.4 |
| k1664-h10-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s0 | iraa-q0.25x1 | -2.936 | fine | 0.06 | -0.10 | 1.19 | 0.1078 | 0.100 | 15 | 0/4200 | 59/100 | 34.2 |
| k1664-h8-f0.5-l3-bal-g24-d1-s1 | plain | -2.892 | fine | 0.11 | -0.06 | 1.23 | 0.1090 | 0.097 | 12 | 0/4100 | 33/100 | 47.5 |
| base-r0406 | baseline | -2.835 | fine | 0.17 | 0.00 | 1.29 | 0.1021 | 0.118 | 16 | 1/4100 ⚠ | 80/100 | 47.4 |

## k = 1600

### Screen 1, PAIRED on (base config, seed) against the plain e-IRA row of the same config and seed (Δ = variant − plain; negative = better; common random numbers)

| variant | n pairs | mean Δ s1 | SD Δ | better / worse | mean s1 | best s1 | s0 verdicts | min w1 (min) | min w2 mean / min | chk deg | parity deg-2 frac | punct 1-SR | CPU s / 100 decodes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain | 8 | 0.00 | 0.00 | 0 / 0 | -2.42 | -2.78 | {"pass": 8} | 33 | 15.0 / 12 | 5..7 | — | — | 3.8 |
| ara-p0.25h | 8 | -0.45 | 0.34 | 7 / 1 | -2.88 | -3.31 | {"pass": 8} | 26 | 14.2 / 11 | 2..7 | 1.00 | 1.00 | 4.7 |
| ara-p0.25l | 7 | 0.16 | 0.62 | 3 / 4 | -2.21 | -3.21 | {"pass": 7, "min_w2": 1} | 28 | 22.2 / 9 | 2..7 | 1.00 | 1.00 | 4.7 |
| ara-p0.5h | 8 | 2.12 | 0.21 | 0 / 8 | -0.31 | -0.76 | {"pass": 8} | 26 | 16.9 / 12 | 2..7 | 1.00 | 1.00 | 6.7 |
| ara-p0.5l | 8 | 0.69 | 0.67 | 1 / 7 | -1.74 | -2.74 | {"pass": 8} | 28 | 30.0 / 19 | 2..7 | 1.00 | 1.00 | 5.6 |
| ara-p1 | 0 | — | — | 0 / 0 | — | — | {"anchor_infeasible": 8} | — | — / — | — | — | — | — |
| iraa-q0.25 | 8 | 1.48 | 0.34 | 0 / 8 | -0.95 | -1.53 | {"pass": 8} | 33 | 47.1 / 24 | 5..10 | 0.26 | — | 5.4 |
| iraa-q0.25x1 | 8 | 0.53 | 0.46 | 0 / 8 | -1.89 | -2.70 | {"pass": 8} | 21 | 20.0 / 13 | 5..8 | 0.74 | — | 4.2 |
| iraa-q0.5 | 8 | 1.18 | 0.49 | 0 / 8 | -1.25 | -2.31 | {"pass": 8} | 30 | 24.0 / 12 | 5..8 | 0.51 | — | 4.9 |

### Screen 2 (walks; `fine` = 500 trials around the 1 % point). Recipe r0391 and the best clean plain e-IRA (Tier A winner) Es/N0@1% = -3.270 dB are the references

| code | family | Es/N0@1% | src | Δ vs best plain | Δ vs recipe | gap dB | p@1% | gap bit | min w2 | undet/trials | robust f0.1% | mean iters @ awgn pt nearest 1 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k1600-h12-f0.3-l3-bal-g24-d1-s1 | plain | -3.270 | fine | 0.00 | -0.18 | 1.09 | 0.1090 | 0.112 | 14 | 0/4300 | 82/100 | 66.4 |
| k1600-h12-f0.3-l3-bal-g24-d1-s0 | plain | -3.250 | fine | 0.02 | -0.16 | 1.11 | 0.1100 | 0.109 | 14 | 3/4400 ⚠ | 73/100 | 67.9 |
| k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s2 | iraa-q0.25x1 | -3.241 | fine | 0.03 | -0.15 | 1.12 | 0.1143 | 0.096 | 19 | 0/4200 | 47/100 | 53.0 |
| k1600-h10-f0.5-l3-bal-g24-d1-s0 | plain | -3.221 | fine | 0.05 | -0.13 | 1.14 | 0.1150 | 0.095 | 17 | 1/4200 ⚠ | 54/100 | 62.7 |
| k1600-h12-f0.3-l3-bal-g24-d1+ara-p0.25h-s2 | ara-p0.25h | -3.217 | fine | 0.05 | -0.13 | 1.14 | 0.1100 | 0.109 | 11 | 7/4300 ⚠ | 74/100 | 79.8 |
| k1600-h12-f0.3-l3-bal-g24-d1+iraa-q0.250x1-s1 | iraa-q0.25x1 | -3.203 | fine | 0.07 | -0.11 | 1.15 | 0.1121 | 0.103 | 21 | 0/4300 | 50/100 | 53.1 |
| k1600-h10-f0.5-l3-bal-g24-d1+ara-p0.25h-s1 | ara-p0.25h | -3.192 | fine | 0.08 | -0.10 | 1.17 | 0.1206 | 0.078 | 21 | 0/4100 | 50/100 | 83.2 |
| k1600-h10-f0.5-l3-bal-g24-d1-s1 | plain | -3.175 | fine | 0.10 | -0.08 | 1.18 | 0.1171 | 0.088 | 20 | 3/4200 ⚠ | 30/100 | 62.7 |
| base-r0391 | baseline | -3.091 | fine | 0.18 | 0.00 | 1.27 | 0.1100 | 0.109 | 11 | 5/4200 ⚠ | 81/100 | 62.3 |

## k = 1280

### Screen 1, PAIRED on (base config, seed) against the plain e-IRA row of the same config and seed (Δ = variant − plain; negative = better; common random numbers)

| variant | n pairs | mean Δ s1 | SD Δ | better / worse | mean s1 | best s1 | s0 verdicts | min w1 (min) | min w2 mean / min | chk deg | parity deg-2 frac | punct 1-SR | CPU s / 100 decodes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain | 8 | 0.00 | 0.00 | 0 / 0 | -2.28 | -2.73 | {"pass": 8} | 45 | 20.5 / 12 | 3..6 | — | — | 4.5 |
| ara-p0.25h | 7 | -0.54 | 0.36 | 7 / 0 | -2.79 | -3.12 | {"pass": 7, "min_w2": 1} | 27 | 16.5 / 7 | 2..6 | 1.00 | 1.00 | 5.0 |
| ara-p0.25l | 8 | 0.49 | 0.36 | 2 / 6 | -1.79 | -2.05 | {"pass": 8} | 48 | 28.4 / 21 | 2..7 | 1.00 | 1.00 | 5.2 |
| ara-p0.5h | 7 | 0.44 | 1.63 | 4 / 3 | -1.81 | -3.26 | {"pass": 7, "min_w2": 1} | 26 | 14.9 / 5 | 2..6 | 1.00 | 1.00 | 6.1 |
| ara-p0.5l | 8 | 0.99 | 0.69 | 0 / 8 | -1.29 | -1.87 | {"pass": 8} | 114 | 64.4 / 39 | 2..6 | 1.00 | 1.00 | 5.9 |
| ara-p1 | 4 | 0.36 | 0.12 | 0 / 4 | -1.67 | -1.77 | {"anchor_infeasible": 4, "pass": 4} | 445 | 41.0 / 30 | 2..6 | 1.00 | 1.00 | 6.5 |
| iraa-q0.25 | 8 | 1.75 | 0.30 | 0 / 8 | -0.54 | -0.69 | {"pass": 8} | 69 | 68.8 / 18 | 3..9 | 0.25 | — | 6.2 |
| iraa-q0.25x1 | 8 | 0.93 | 0.27 | 0 / 8 | -1.35 | -1.59 | {"pass": 8} | 45 | 24.0 / 12 | 3..8 | 0.75 | — | 5.0 |
| iraa-q0.5 | 8 | 1.57 | 0.37 | 0 / 8 | -0.71 | -0.89 | {"pass": 8} | 66 | 31.8 / 17 | 3..8 | 0.50 | — | 5.8 |

### Screen 2 (walks; `fine` = 500 trials around the 1 % point). Recipe r0313 and the best clean plain e-IRA (Tier A winner) Es/N0@1% = -4.278 dB are the references

| code | family | Es/N0@1% | src | Δ vs best plain | Δ vs recipe | gap dB | p@1% | gap bit | min w2 | undet/trials | robust f0.1% | mean iters @ awgn pt nearest 1 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k1280-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 | ara-p0.5h | -4.458 | fine | -0.18 | -0.71 | 1.17 | 0.1480 | 0.083 | 11 | 1/4000 ⚠ | 75/100 | 88.5 |
| k1280-h12-f0.5-l3-bal-g24-d1-s3 | plain | -4.364 | fine | -0.09 | -0.61 | 1.26 | 0.1400 | 0.103 | 17 | 5/4500 ⚠ | 54/100 | 70.6 |
| k1280-h12-f0.5-l3-bal-g24-d1+ara-p0.25h-s0 | ara-p0.25h | -4.341 | fine | -0.06 | -0.59 | 1.28 | 0.1506 | 0.076 | 19 | 0/4200 | 65/100 | 86.3 |
| k1280-h12-f0.5-l3-bal-g24-d1-s1 | plain | -4.278 | fine | 0.00 | -0.53 | 1.35 | 0.1471 | 0.085 | 17 | 0/4300 | 68/100 | 71.7 |
| k1280-h8-f0.5-l3-bal-g24-d1-s0 | plain | -4.271 | fine | 0.01 | -0.52 | 1.35 | 0.1400 | 0.103 | 28 | 0/4400 | 64/100 | 67.4 |
| k1280-h12-f0.5-l3-bal-g24-d1-s0 | plain | -4.229 | fine | 0.05 | -0.48 | 1.39 | 0.1475 | 0.084 | 29 | 0/4100 | 50/100 | 72.3 |
| k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s2 | iraa-q0.25x1 | -4.091 | fine | 0.19 | -0.34 | 1.53 | 0.1425 | 0.097 | 15 | 0/4100 | 29/100 | 61.4 |
| k1280-h12-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s1 | iraa-q0.25x1 | -4.080 | fine | 0.20 | -0.33 | 1.54 | 0.1444 | 0.092 | 18 | 0/4300 | 10/100 | 47.3 |
| base-r0313 | baseline | -3.750 | fine | 0.53 | 0.00 | 1.87 | 0.1316 | 0.126 | 12 | 22/4500 ⚠ | 80/100 | 65.9 |

## k = 1216

### Screen 1, PAIRED on (base config, seed) against the plain e-IRA row of the same config and seed (Δ = variant − plain; negative = better; common random numbers)

| variant | n pairs | mean Δ s1 | SD Δ | better / worse | mean s1 | best s1 | s0 verdicts | min w1 (min) | min w2 mean / min | chk deg | parity deg-2 frac | punct 1-SR | CPU s / 100 decodes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain | 8 | 0.00 | 0.00 | 0 / 0 | -2.19 | -2.42 | {"pass": 8} | 35 | 31.8 / 20 | 3..5 | — | — | 4.4 |
| ara-p0.25h | 8 | -0.86 | 0.24 | 8 / 0 | -3.05 | -3.29 | {"pass": 8} | 32 | 29.0 / 18 | 2..5 | 1.00 | 1.00 | 4.8 |
| ara-p0.25l | 8 | -0.12 | 0.33 | 4 / 4 | -2.31 | -2.77 | {"pass": 8} | 40 | 38.8 / 20 | 2..6 | 1.00 | 1.00 | 5.1 |
| ara-p0.5h | 8 | -1.05 | 0.35 | 8 / 0 | -3.24 | -3.78 | {"pass": 8} | 25 | 34.9 / 15 | 2..5 | 1.00 | 1.00 | 5.5 |
| ara-p0.5l | 8 | 0.12 | 0.13 | 1 / 7 | -2.07 | -2.20 | {"pass": 8} | 40 | 65.6 / 36 | 2..5 | 1.00 | 1.00 | 5.7 |
| ara-p1 | 4 | -0.14 | 0.22 | 3 / 1 | -2.37 | -2.73 | {"anchor_infeasible": 4, "pass": 4} | 696 | 63.2 / 31 | 2..6 | 1.00 | 1.00 | 6.8 |
| iraa-q0.25 | 8 | 1.65 | 0.15 | 0 / 8 | -0.54 | -0.75 | {"pass": 8} | 80 | 110.4 / 29 | 3..9 | 0.24 | — | 6.7 |
| iraa-q0.25x1 | 8 | 0.76 | 0.20 | 0 / 8 | -1.43 | -1.74 | {"pass": 8} | 43 | 46.2 / 21 | 3..6 | 0.75 | — | 5.2 |
| iraa-q0.5 | 8 | 1.46 | 0.16 | 0 / 8 | -0.73 | -1.06 | {"pass": 8} | 56 | 54.1 / 20 | 3..7 | 0.49 | — | 6.2 |

### Screen 2 (walks; `fine` = 500 trials around the 1 % point). Recipe r0297 and the best clean plain e-IRA (Tier A winner) Es/N0@1% = -4.554 dB are the references

| code | family | Es/N0@1% | src | Δ vs best plain | Δ vs recipe | gap dB | p@1% | gap bit | min w2 | undet/trials | robust f0.1% | mean iters @ awgn pt nearest 1 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s1 | ara-p0.5h | -4.663 | fine | -0.11 | -0.56 | 1.24 | 0.1566 | 0.077 | 24 | 0/4200 | 64/100 | 81.9 |
| k1216-h8-f0.5-l3-bal-g24-d1+ara-p0.50h-s0 | ara-p0.5h | -4.653 | fine | -0.10 | -0.55 | 1.25 | 0.1490 | 0.096 | 21 | 0/4300 | 85/100 | 83.7 |
| k1216-h12-f0.3-l4-bal-g24-d1-s0 | plain | -4.554 | fine | 0.00 | -0.45 | 1.35 | 0.1518 | 0.089 | 34 | 0/4100 | 37/100 | 54.0 |
| k1216-h8-f0.5-l3-bal-g24-d1-s0 | plain | -4.500 | fine | 0.05 | -0.39 | 1.40 | 0.1400 | 0.119 | 20 | 0/4600 | 64/100 | 75.4 |
| k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s0 | iraa-q0.25x1 | -4.449 | fine | 0.10 | -0.34 | 1.45 | 0.1450 | 0.106 | 39 | 0/4400 | 50/100 | 63.5 |
| k1216-h8-f0.5-l3-bal-g24-d1+iraa-q0.250x1-s2 | iraa-q0.25x1 | -4.432 | fine | 0.12 | -0.33 | 1.47 | 0.1504 | 0.092 | 29 | 0/4000 | 29/100 | 50.9 |
| base-r0297 | baseline | -4.106 | fine | 0.45 | 0.00 | 1.80 | 0.1335 | 0.136 | 25 | 1/4600 ⚠ | 73/100 | 68.5 |

