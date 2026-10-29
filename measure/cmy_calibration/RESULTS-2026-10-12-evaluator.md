# The PAVA evaluator, held out — R31's measurement line (2026-10-12)

**RULED 2026-10-12 (owner): PASSED** — "we pass on R31, it does not seem to pay at this stage, maybe note down as a possible mechanism for the analyzer?" The shipped evaluator (PAVA centroid nodes joined in logit for the cmy chain; `PavaMap.logit_interpolation` off for cmy8) stands; R11's evaluator clause is not amended; block-edge nodes are recorded as a candidate ANALYZER arm (CMY-DESIGN §9.1, analyzer DESIGN §13) — an alternative per-(tile-stream, lane) evaluator the analyzer's arms × rules ladder can try where a map is separable, paid for in certificates like every arm, never a receiver default.

The question (R31, src/holo/receiver/docs/CMY-RECEIVER-PLAN.md §5 and A8's as-built paragraph; the 2026-10-12
outside review): the cmy chain as built (A8, `color_chain.fit_chain_map`) reads its three PAVA maps through the
block CENTROIDS joined in logit, and on the separable sim pages that squeezes the quieter state's label LLR to
~1e-6; the A8 refuter's probe replaced the centroids with BLOCK-EDGE nodes and fixed every probe. Does block-edge
recover the squeeze without losing information on paper, held out?

**Answer, measured: it recovers the squeeze completely on the separable sims, and on paper it is not free.** On the
noiseless sims every block-edge read is 0.9995 / 0.9984–0.9986 bit/cell where centroid-logit read 0.728 / 0.913
(offset page, no field), 0.500 / 0.500 (planted field) and, refused by its gate, 0.500 on the faint page's hi. On
the paper extracts it LOSES on every c2 decision band — 0.0006–0.0027 bit on hi, 0.0003–0.0062 on lo, every
interval below zero, 12 of 12 page fits — and 0.006–0.022 bit on hi cold at n = 2 and 8; it gains 0.0001–0.0025 on
hi on the lossless c3 controls, where it lands within 0.003 of the raw statistic on the page and the raw statistic
beats every evaluator cold — but on c3 it also loses on lo in 3 of 18 page fits and on lo|hi in 5 (6 counting B1
k1, upper bound −0.00005), intervals wholly below zero. Through the receiver's own lane on e044, its gate refuses
the cold region of sheet A (c2) at ppc 2 and 4 that centroid-logit's gate adopts (its dust leg, M read as M, goes
worse than raw), costing 0.010 / 0.014 bit there; on sheet B (c3) production wore raw on every lane at every level,
block-edge's gate would adopt on 3–6 of 140 first-fire windows per level (none cold), and the gated outcome differs
from raw by ≤ 0.0002. Every e044 number is a point estimate (one capture at truth poses, no interval computed).
Single sheets, one capture each, sims and emulations — NO promotion.

**Provenance.** `measure/cmy_calibration/evaluator.py` (the paper extracts, the four evaluators, the report) and
`measure/cmy_calibration/evaluator_lanes.py` (the receiver lane: sims, e044), uncommitted when this was written,
run on machine 1 in the `cmy-review-fixes` worktree at b21be9cf. The tree was DIRTY with a concurrent builder's
work, two files on the colour path among it (`color_region_head.py` routes the emission tail through a new
`color_region_ctx.relative_emission`); every receiver-lane run below ran its nulls against whatever was on disk
and passed (the emitted rows to 9.5e-7, production's gate verdict exactly), and `color_chain.py` /
`color_model.py`, which build the maps, were clean. Inputs: the R11 run's extracts
`scratch/cmy-calibration-20261010/cells-{S14-2400,S17-2400,S17-4800,X1-2400}.npz` (present, not re-extracted;
scans as RESULTS-2026-10-10.md lists them); e044 `scratch/e044/captures/E044-B-c3-cmy-r0850-hp-scan.tiff`
(sha256 `aeeca25c…`) and `E044-A-c2-cmy-r0775x0700-hp-scan.tiff` (`2fd8430b…`), GT
`scratch/e044/jobs/E044-{A,B}-page000_gt.npy` (array sha256 `42d5c8b6…` / `7020b7b2…` = each manifest's
`gt_sha256`); the sims rendered by `_h3_sims_cmy.make_cmy{,_offset,_faint}`, sha-checked against the module's
constants. Artefacts NOT committed: `scratch/cmy_calibration/evaluator-2026-10-12/` (`evaluator-paper.json`,
`evaluator-sim.json`, `evaluator-e044-{A,B}.json`, `e044-{A,B}/poses.json`, `evaluator.md` = every table per
level and band, the logs, `render/`).

```
cd <repo>
E=env/bin/python; O=scratch/cmy_calibration/evaluator-2026-10-12
PYTHONPATH=src:. $E -m measure.cmy_calibration.evaluator --stage paper \
    --art scratch/cmy-calibration-20261010 --out $O     # 72 s, peak RSS 4.4 GB, 8 workers
PYTHONPATH=src:. $E -m measure.cmy_calibration.evaluator_lanes --stage sim --out $O        # 25 s with the renders (6.2 GB), 20 s cached (1.1 GB)
PYTHONPATH=src:. $E -m measure.cmy_calibration.evaluator_lanes --stage e044 --sheet B --levels 0 1 2 3 --out $O
    # poses 216 s / 2.9 GB (first run), lanes 158 s / 12.7 GB, 6 workers
PYTHONPATH=src:. $E -m measure.cmy_calibration.evaluator_lanes --stage e044 --sheet A --levels 0 1 2 --out $O
    # poses 236 s / 2.8 GB (first run), lanes 228 s / 24.7 GB, 6 workers
PYTHONPATH=src:. $E -m measure.cmy_calibration.evaluator --stage report --out $O        # evaluator.md
```

## Method

**The four evaluators**, over ONE fit per calibration context — the same training population, the same PAVA
blocks, the same block probabilities (the clip [1/(n+2), 1 − 1/(n+2)], n the map's population):
1. **raw** — the bounded raw score triple, every piece the per-map fallback (the fold of three raw pieces is the
   identity, so this is the bounded raw triple itself).
2. **centroid-linear** — nodes at the block centroids (the block's score-weighted mean training score),
   interpolated linearly in probability: `PavaMap.llrs` with `logit_interpolation` False, cmy8's and A4b's
   evaluator.
3. **centroid-logit** — the same nodes interpolated linearly in logit(p), flat beyond the end nodes: the cmy chain
   AS BUILT (`fit_chain_map` sets `logit_interpolation=True`) and R11's ruled evaluator. The reference.
4. **block-edge** — per block a node at its FIRST and at its LAST training score, both at the block's
   probability (one node when they coincide), joined linearly in logit, flat beyond the end nodes; E017.6's
   (0, ½) node inserted under fit_component_pava's own test (the nodes straddle 0 with p straddling ½), applied
   to these nodes. Tie rule: the unique training scores are the groups, so tied scores never split; a group whose
   value is ≤ the open block's merges into it (`values[-2] >= values[-1]`), so block values rise strictly and a
   block's last score lies strictly below the next block's first — within a block the LLR is the block's,
   constant; between blocks it is logit-linear. This restates the refuter's probe (scratchpad a8probe/edges.py)
   and reproduces its numbers exactly (below).
`evaluator.pav_blocks` repeats the fitters' arithmetic with each block's first and last score carried along, and
refuses unless its centroid nodes equal the fitted `PavaMap`'s bit for bit (they did, on every map of every run).

**Held-out split.** Paper extracts: R11's page furniture P-a (`fit.fit_context`: the QDA on the search half, the
maps on the held-out half H — policy D1-DEFAULT, state-balanced L_hi, A4b's floors, no gate), evaluated on the
PAYLOAD cells, which enter no fit; replicates k = 0, 1, 2 (`regimes.rng_for("page_furniture", bc, 0, k)`); cold
n ∈ {1, 2, 8} emulated tiles, 150 draws each with the run's own rngs. Receiver lane: the chain's own population
as `fit_cmy_chain` receives it (the QDA's held-out `&1` side, `&2` into fit and validation sides), evaluated on
the lane's CARGO cells (`color_sites.cargo_row_indices`), which enter neither the QDA nor the maps; the context
head OFF (it is fitted after the chain and is not the evaluator). `gated:<evaluator>` = that evaluator where the
chain's three-way gate (validation side, `fit_cmy_chain`'s legs) adopts it, raw where it refuses — what the lane
would emit.

**Estimators** (`estimators.info_rows`, R11's, unclamped): information I = 1 − mean log2(1 + e^{−(2b−1)L}),
STATE-balanced (each state ¼; `lo|hi` = lo through the true hi's conditional form, each half ½) — I hi, I lo, I
lo|hi in bit/cell; log-loss = (1 − I) ln 2 nats; sign flips = cells with (2b − 1)L < 0, counted (ties L = 0 apart,
not flips: none on lo; on hi only in the cold U12 / X10 draws, 29–358 cells per row, and e044 B's ppc 4 first-fire,
213–243; mechanism not examined); margin = the signed (2b − 1)L, its p1 / p5 over cells (plain); paired dI against
centroid-logit with R11's window bootstrap (page, B 2000) or cluster-origin bootstrap (cold), 95 % percentile
intervals — on the paper extracts only: the receiver lane (`evaluator_lanes.summarise`) computes no bootstrap, so
the sim and e044 rows carry no interval. The receiver lane counts a cell once per emitting window (windows overlap
by 40 cells); the evaluators see the same cells.

**Nulls.** Paper: raw, centroid-linear and centroid-logit reproduce the follow-up run of record's fallback,
hi-first and hi-first/logit rows (bc 0–4, P-a, replicate 0) to max |ΔI| 4.6e-14. Receiver lane: the evaluator
production actually wore reproduces every emitted evidence row to ≤ 9.5e-7 (float32) on all 11 sim configs and
all 1,512 e044 lanes (B 4 × 141, A 3 × 316), and the recomputed centroid-logit gate reproduces production's verdict on every lane. The sims
reproduce the A8 probes' context-off numbers exactly (offset, no field: raw 0.3113 / 0.3136, chain 0.7278 /
0.9131, edges 0.9995 / 0.9986 plain-mean; σ 0.06 chain 0.9077 / 0.8645, edges 0.9062 / 0.8628; σ 0.04 0.9015 /
0.9221 and 0.9663 / 0.9408). e044 B's poses reproduce scorelane's medians, M−C (−0.919, +1.230), Y−C (−0.407,
+1.129) dots.

## (a) The separable synthetic case — the A8 probes' pages through the receiver's lane

c3 `CMY_FORMAT_REF` page at 1200 dpi, the render's own pose, one whole-page window, 397,600 cargo cells; σ =
the probes' seeded Gaussian on the three features before the QDA (rng 20261012). "gate" = what the chain's
three-way gate does with that evaluator's candidate; production wears centroid-logit or raw.

**cmy, σ 0.0, field none** — 397,600 cargo cells; held-out max|s| p99 2.99e+17; production wore raw; gate adopts: linear 0, logit 0, edge 0

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 1.0000 | 1.0000 | 1.0000 | 0.0000 / 0.0000 | 0 / 0 | 12.74 / 10.25 | 12.74 / 10.25 | — |
| centroid-linear | 0.9116 | 0.9267 | 0.9989 | 0.0613 / 0.0508 | 0 / 0 | 2.00 / 2.19 | 2.00 / 2.19 | refuse |
| centroid-logit | 0.9981 | 0.9971 | 0.9989 | 0.0013 / 0.0020 | 0 / 0 | 6.03 / 5.80 | 6.03 / 5.80 | refuse |
| block-edge | 0.9995 | 0.9984 | 0.9989 | 0.0004 / 0.0011 | 0 / 0 | 7.90 / 6.67 | 7.90 / 6.67 | refuse |

**offset, σ 0.0, field none** — 397,600 cargo cells; held-out max|s| p99 3.65e+07; production wore the chain; gate adopts: linear 1, logit 1, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.3113 | 0.3113 | 0.5000 | 0.4774 / 0.4774 | 99563 / 98631 | -0.69 / -0.69 | -0.69 / -0.69 | — |
| centroid-linear | 0.6693 | 0.8270 | 0.9134 | 0.2293 / 0.1199 | 0 / 0 | 0.00 / 0.50 | 0.00 / 0.50 | adopt |
| centroid-logit | 0.7282 | 0.9133 | 0.9750 | 0.1884 / 0.0601 | 0 / 0 | 0.00 / 0.10 | 0.00 / 0.10 | adopt |
| block-edge | 0.9995 | 0.9986 | 0.9989 | 0.0004 / 0.0010 | 0 / 0 | 7.90 / 6.67 | 7.90 / 6.67 | adopt |

**offset, σ 0.0, field planted** — 397,600 cargo cells; held-out max|s| p99 6.64e+08; production wore the chain; gate adopts: linear 1, logit 1, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.4566 | 0.4625 | 0.8640 | 0.3766 / 0.3725 | 99722 / 99684 | -0.39 / -0.38 | -0.39 / -0.38 | — |
| centroid-linear | 0.4998 | 0.5104 | 0.9983 | 0.3467 / 0.3394 | 0 / 74097 | 0.00 / -0.00 | 0.00 / -0.00 | adopt |
| centroid-logit | 0.5000 | 0.4997 | 0.9989 | 0.3466 / 0.3468 | 0 / 0 | 0.00 / 0.00 | 0.00 / 0.00 | adopt |
| block-edge | 0.9995 | 0.9985 | 0.9989 | 0.0004 / 0.0011 | 0 / 0 | 7.90 / 6.67 | 7.90 / 6.67 | adopt |

**faint, σ 0.0, field none** — 397,600 cargo cells; held-out max|s| p99 7.32e+07; production wore raw; gate adopts: linear 0, logit 0, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.4998 | 0.9990 | 0.9995 | 0.3467 / 0.0007 | 0 / 0 | 0.00 / 6.01 | 0.00 / 6.01 | — |
| centroid-linear | 0.4998 | 0.9977 | 0.9989 | 0.3467 / 0.0016 | 0 / 0 | 0.00 / 6.00 | 0.00 / 6.00 | refuse |
| centroid-logit | 0.5000 | 0.9986 | 0.9989 | 0.3466 / 0.0010 | 0 / 0 | 0.00 / 6.67 | 0.00 / 6.67 | refuse |
| block-edge | 0.9995 | 0.9986 | 0.9989 | 0.0004 / 0.0009 | 0 / 0 | 7.90 / 6.67 | 7.90 / 6.67 | adopt |

**offset, σ 0.06, field none** — 397,600 cargo cells; held-out max|s| p99 96.6; production wore the chain; gate adopts: linear 1, logit 1, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.7685 | 0.7136 | 0.8069 | 0.1605 / 0.1985 | 11186 / 18678 | -0.30 / -0.48 | 0.20 / 0.02 | — |
| centroid-linear | 0.9054 | 0.8361 | 0.8845 | 0.0655 / 0.1136 | 10160 / 14979 | -1.51 / -1.80 | 1.43 / 0.44 | adopt |
| centroid-logit | 0.9077 | 0.8642 | 0.9144 | 0.0640 / 0.0941 | 10163 / 15018 | -1.63 / -1.99 | 1.55 / 0.45 | adopt |
| block-edge | 0.9062 | 0.8626 | 0.9142 | 0.0650 / 0.0953 | 10312 / 15017 | -2.13 / -2.33 | 0.96 / 0.59 | adopt |

**offset, σ 0.06, field planted** — 397,600 cargo cells; held-out max|s| p99 105; production wore raw; gate adopts: linear 0, logit 0, edge 0

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 1.0000 | 0.9998 | 0.9998 | 0.0000 / 0.0002 | 0 / 1 | 8.93 / 6.02 | 10.62 / 7.81 | — |
| centroid-linear | 0.9083 | 0.8690 | 0.9414 | 0.0636 / 0.0908 | 0 / 4 | 0.98 / 0.79 | 1.32 / 1.15 | refuse |
| centroid-logit | 0.9965 | 0.9934 | 0.9967 | 0.0024 / 0.0046 | 0 / 1 | 3.61 / 3.26 | 4.59 / 4.14 | refuse |
| block-edge | 0.9995 | 0.9984 | 0.9989 | 0.0004 / 0.0011 | 0 / 1 | 7.90 / 6.67 | 7.90 / 6.67 | refuse |

**offset, σ 0.04, field none** — 397,600 cargo cells; held-out max|s| p99 192; production wore the chain; gate adopts: linear 1, logit 1, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.6345 | 0.6053 | 0.7282 | 0.2533 / 0.2736 | 23016 / 33494 | -0.23 / -0.33 | -0.03 / -0.11 | — |
| centroid-linear | 0.8738 | 0.8870 | 0.9336 | 0.0875 / 0.0783 | 2895 / 5456 | 0.48 / -0.54 | 1.07 / 1.07 | adopt |
| centroid-logit | 0.9016 | 0.9221 | 0.9598 | 0.0682 / 0.0540 | 2895 / 5449 | 0.56 / -0.61 | 1.20 / 1.25 | adopt |
| block-edge | 0.9663 | 0.9407 | 0.9613 | 0.0233 / 0.0411 | 2883 / 5514 | 1.04 / -1.10 | 7.90 / 2.24 | adopt |

**offset, σ 0.04, field planted** — 397,600 cargo cells; held-out max|s| p99 205; production wore raw; gate adopts: linear 0, logit 0, edge 0

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 1.0000 | 1.0000 | 1.0000 | 0.0000 / 0.0000 | 0 / 0 | 10.38 / 7.89 | 11.55 / 9.18 | — |
| centroid-linear | 0.9110 | 0.8907 | 0.9609 | 0.0617 / 0.0758 | 0 / 0 | 1.23 / 1.13 | 1.49 / 1.44 | refuse |
| centroid-logit | 0.9974 | 0.9956 | 0.9980 | 0.0018 / 0.0031 | 0 / 0 | 4.34 / 4.15 | 5.01 / 4.73 | refuse |
| block-edge | 0.9995 | 0.9984 | 0.9989 | 0.0004 / 0.0011 | 0 / 0 | 7.90 / 6.67 | 7.90 / 6.67 | refuse |

**faint, σ 0.06, field none** — 397,600 cargo cells; held-out max|s| p99 111; production wore the chain; gate adopts: linear 0, logit 1, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.8169 | 0.9981 | 0.9997 | 0.1269 / 0.0013 | 3833 / 17 | 0.01 / 3.76 | 0.54 / 5.42 | — |
| centroid-linear | 0.9492 | 0.9335 | 0.9372 | 0.0352 / 0.0461 | 3655 / 17 | 0.23 / 1.20 | 2.99 / 1.62 | refuse |
| centroid-logit | 0.9550 | 0.9955 | 0.9965 | 0.0312 / 0.0031 | 3647 / 16 | 0.31 / 3.76 | 3.11 / 4.62 | adopt |
| block-edge | 0.9586 | 0.9984 | 0.9989 | 0.0287 / 0.0011 | 3774 / 18 | 0.14 / 6.67 | 7.90 / 6.67 | adopt |

**faint, σ 0.04, field none** — 397,600 cargo cells; held-out max|s| p99 228; production wore raw; gate adopts: linear 0, logit 0, edge 1

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 0.7841 | 0.9994 | 0.9999 | 0.1497 / 0.0004 | 506 / 0 | 0.20 / 5.03 | 0.33 / 6.18 | — |
| centroid-linear | 0.6835 | 0.9284 | 0.9562 | 0.2194 / 0.0496 | 508 / 1 | 0.08 / 1.31 | 0.16 / 1.59 | refuse |
| centroid-logit | 0.8204 | 0.9953 | 0.9979 | 0.1245 / 0.0032 | 508 / 0 | 0.32 / 3.45 | 0.63 / 4.33 | refuse |
| block-edge | 0.9919 | 0.9985 | 0.9989 | 0.0056 / 0.0010 | 294 / 0 | 7.90 / 6.67 | 7.90 / 6.67 | adopt |

**cmy, σ 0.06, field none** — 397,600 cargo cells; held-out max|s| p99 115; production wore raw; gate adopts: linear 0, logit 0, edge 0

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | gate |
|---|---|---|---|---|---|---|---|---|
| raw | 1.0000 | 0.9996 | 0.9996 | 0.0000 / 0.0003 | 0 / 1 | 9.02 / 5.51 | 10.57 / 7.14 | — |
| centroid-linear | 0.9022 | 0.8635 | 0.9433 | 0.0678 / 0.0946 | 0 / 2 | 0.98 / 0.81 | 1.30 / 1.14 | refuse |
| centroid-logit | 0.9962 | 0.9932 | 0.9969 | 0.0026 / 0.0047 | 0 / 1 | 3.58 / 3.29 | 4.51 / 4.12 | refuse |
| block-edge | 0.9995 | 0.9984 | 0.9989 | 0.0004 / 0.0011 | 0 / 1 | 7.90 / 6.67 | 7.90 / 6.67 | refuse |

## (b) Paper — the R11 extracts (e041 M281 S14/S17, e042 AltaLink X1), P-a page, payload cells

Replicate 0; c2 = the decision band-captures, c3 = the controls. Every map qualified on every page fit; blocks
per map (L_hi / L_lo|hi=0 / L_lo|hi=1) over the three replicates 17–28 / 8–25 / 3–8 on c2, 2–3 / 2–5 / 2 on c3.

| band-capture | evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo | dI hi / lo vs logit |
|---|---|---|---|---|---|---|---|---|---|
| bc0 B3 c2 | raw | 0.9353 | 0.9176 | 0.9406 | 0.0449 / 0.0571 | 8755 / 11842 | -0.81 / -1.47 | 3.88 / 2.77 | -0.0093 / -0.0057 |
|  | centroid-linear | 0.9447 | 0.9094 | 0.9278 | 0.0383 / 0.0628 | 8392 / 12005 | -0.45 / -1.33 | 2.91 / 1.59 | +0.0001 / -0.0139 |
|  | centroid-logit | 0.9446 | 0.9233 | 0.9446 | 0.0384 / 0.0532 | 8393 / 11821 | -0.45 / -1.48 | 3.00 / 2.44 | — |
|  | block-edge | 0.9440 | 0.9230 | 0.9438 | 0.0388 / 0.0534 | 8459 / 11943 | -0.44 / -1.39 | 2.75 / 2.45 | -0.0006 / -0.0003 |
| bc1 U12 c2 | raw | 0.8661 | 0.8428 | 0.8952 | 0.0928 / 0.1090 | 11414 / 14087 | -2.63 / -2.87 | 1.24 / 0.70 | -0.0122 / -0.0115 |
|  | centroid-linear | 0.8784 | 0.8504 | 0.8934 | 0.0843 / 0.1037 | 11258 / 14055 | -2.13 / -2.28 | 1.33 / 0.56 | +0.0000 / -0.0039 |
|  | centroid-logit | 0.8784 | 0.8543 | 0.8990 | 0.0843 / 0.1010 | 11259 / 14048 | -2.14 / -2.39 | 1.37 / 0.57 | — |
|  | block-edge | 0.8774 | 0.8507 | 0.8939 | 0.0850 / 0.1035 | 11281 / 14029 | -2.10 / -2.54 | 1.46 / 0.56 | -0.0010 / -0.0036 |
| bc2 U12 c2 | raw | 0.8669 | 0.8434 | 0.8967 | 0.0922 / 0.1086 | 11094 / 13964 | -2.68 / -2.74 | 1.36 / 0.69 | -0.0129 / -0.0124 |
|  | centroid-linear | 0.8796 | 0.8457 | 0.8863 | 0.0834 / 0.1070 | 11092 / 13935 | -2.23 / -2.07 | 1.26 / 0.47 | -0.0002 / -0.0101 |
|  | centroid-logit | 0.8798 | 0.8558 | 0.8998 | 0.0833 / 0.1000 | 11092 / 13938 | -2.23 / -2.21 | 1.27 / 0.48 | — |
|  | block-edge | 0.8781 | 0.8541 | 0.8977 | 0.0845 / 0.1011 | 11092 / 14142 | -2.20 / -2.23 | 1.23 / 0.55 | -0.0017 / -0.0017 |
| bc3 X10 c2 | raw | 0.9217 | 0.9193 | 0.9552 | 0.0543 / 0.0559 | 6068 / 5952 | -1.38 / -1.34 | 3.32 / 3.41 | -0.0130 / -0.0118 |
|  | centroid-linear | 0.9321 | 0.9163 | 0.9438 | 0.0471 / 0.0580 | 5750 / 5971 | -1.00 / -1.07 | 2.21 / 1.75 | -0.0026 / -0.0148 |
|  | centroid-logit | 0.9347 | 0.9311 | 0.9598 | 0.0453 / 0.0477 | 5750 / 5952 | -1.01 / -1.10 | 2.23 / 2.34 | — |
|  | block-edge | 0.9319 | 0.9257 | 0.9551 | 0.0472 / 0.0515 | 5751 / 5929 | -1.10 / -1.14 | 2.39 / 2.70 | -0.0027 / -0.0054 |
| bc4 A1 c3 | raw | 0.9994 | 0.9957 | 0.9958 | 0.0004 / 0.0030 | 27 / 238 | 5.85 / 3.90 | 7.69 / 5.22 | +0.0012 / +0.0002 |
|  | centroid-linear | 0.9342 | 0.9268 | 0.9467 | 0.0456 / 0.0508 | 27 / 229 | 1.06 / 0.85 | 1.57 / 1.44 | -0.0640 / -0.0687 |
|  | centroid-logit | 0.9982 | 0.9955 | 0.9962 | 0.0013 / 0.0031 | 27 / 237 | 4.25 / 3.42 | 5.75 / 5.12 | — |
|  | block-edge | 0.9993 | 0.9949 | 0.9949 | 0.0005 / 0.0036 | 27 / 209 | 8.77 / 7.57 | 8.77 / 7.57 | +0.0011 / -0.0006 |
| bc5 B1 c3 | raw | 0.9991 | 0.9939 | 0.9943 | 0.0006 / 0.0042 | 18 / 277 | 4.98 / 3.34 | 6.53 / 4.65 | +0.0008 / -0.0013 |
|  | centroid-linear | 0.9391 | 0.9439 | 0.9657 | 0.0422 / 0.0389 | 18 / 238 | 1.07 / 1.15 | 1.61 / 1.79 | -0.0592 / -0.0513 |
|  | centroid-logit | 0.9983 | 0.9952 | 0.9960 | 0.0011 / 0.0033 | 18 / 240 | 4.30 / 3.30 | 5.84 / 5.04 | — |
|  | block-edge | 0.9995 | 0.9956 | 0.9958 | 0.0003 / 0.0030 | 18 / 241 | 8.77 / 7.55 | 8.77 / 7.55 | +0.0012 / +0.0005 |
| bc6 B2 c3 | raw | 0.9994 | 0.9957 | 0.9960 | 0.0004 / 0.0030 | 20 / 212 | 5.51 / 3.62 | 7.36 / 4.99 | +0.0009 / +0.0001 |
|  | centroid-linear | 0.9396 | 0.9436 | 0.9650 | 0.0418 / 0.0391 | 20 / 201 | 1.09 / 1.09 | 1.61 / 1.74 | -0.0588 / -0.0520 |
|  | centroid-logit | 0.9984 | 0.9956 | 0.9964 | 0.0011 / 0.0030 | 20 / 205 | 4.35 / 3.52 | 5.85 / 5.07 | — |
|  | block-edge | 0.9994 | 0.9968 | 0.9971 | 0.0004 / 0.0022 | 20 / 211 | 8.77 / 3.77 | 8.77 / 7.55 | +0.0009 / +0.0012 |
| bc7 U13 c3 | raw | 0.9989 | 0.9951 | 0.9955 | 0.0007 / 0.0034 | 8 / 95 | 4.91 / 3.80 | 6.11 / 5.24 | +0.0023 / +0.0023 |
|  | centroid-linear | 0.9295 | 0.9065 | 0.9447 | 0.0488 / 0.0648 | 9 / 99 | 0.96 / 0.83 | 1.48 / 1.33 | -0.0671 / -0.0862 |
|  | centroid-logit | 0.9966 | 0.9927 | 0.9942 | 0.0023 / 0.0050 | 9 / 94 | 3.49 / 2.99 | 4.94 / 4.43 | — |
|  | block-edge | 0.9992 | 0.9950 | 0.9953 | 0.0006 / 0.0035 | 9 / 95 | 7.85 / 6.64 | 7.85 / 6.69 | +0.0025 / +0.0023 |
| bc8 U13 c3 | raw | 0.9986 | 0.9924 | 0.9928 | 0.0009 / 0.0052 | 6 / 94 | 4.51 / 2.94 | 5.59 / 4.05 | +0.0016 / -0.0007 |
|  | centroid-linear | 0.9387 | 0.9179 | 0.9450 | 0.0425 / 0.0569 | 6 / 97 | 1.00 / 0.87 | 1.55 / 1.41 | -0.0584 / -0.0752 |
|  | centroid-logit | 0.9971 | 0.9931 | 0.9943 | 0.0020 / 0.0048 | 6 / 94 | 3.63 / 3.01 | 5.11 / 4.52 | — |
|  | block-edge | 0.9993 | 0.9952 | 0.9954 | 0.0005 / 0.0034 | 6 / 94 | 7.85 / 6.62 | 7.85 / 6.68 | +0.0022 / +0.0020 |
| bc9 X11 c3 | raw | 0.9991 | 0.9985 | 0.9991 | 0.0006 / 0.0011 | 35 / 48 | 8.71 / 7.52 | 12.13 / 10.67 | +0.0027 / +0.0047 |
|  | centroid-linear | 0.9295 | 0.9113 | 0.9395 | 0.0489 / 0.0615 | 35 / 54 | 0.99 / 0.85 | 1.49 / 1.36 | -0.0669 / -0.0824 |
|  | centroid-logit | 0.9964 | 0.9937 | 0.9954 | 0.0025 / 0.0043 | 35 / 47 | 3.59 / 3.11 | 4.96 / 4.44 | — |
|  | block-edge | 0.9987 | 0.9972 | 0.9980 | 0.0009 / 0.0019 | 35 / 48 | 7.85 / 6.67 | 7.85 / 6.67 | +0.0023 / +0.0035 |

All three replicates, dI = block-edge − centroid-logit (estimates; on c2 every interval of hi, lo and lo|hi lies
below zero; on c3 none wholly below on hi):

| band-capture | dI hi, k = 0 / 1 / 2 | dI lo, k = 0 / 1 / 2 | dI lo\|hi, k = 0 / 1 / 2 |
|---|---|---|---|
| bc0 B3 | -0.0006 / -0.0016 / -0.0016 | -0.0003 / -0.0030 / -0.0017 | -0.0008 / -0.0022 / -0.0032 |
| bc1 U12 | -0.0010 / -0.0015 / -0.0022 | -0.0036 / -0.0014 / -0.0041 | -0.0051 / -0.0019 / -0.0058 |
| bc2 U12 | -0.0017 / -0.0012 / -0.0007 | -0.0017 / -0.0062 / -0.0048 | -0.0020 / -0.0082 / -0.0045 |
| bc3 X10 | -0.0027 / -0.0016 / -0.0016 | -0.0054 / -0.0020 / -0.0031 | -0.0047 / -0.0027 / -0.0063 |
| bc4 A1 | +0.0011 / +0.0012 / +0.0024 | -0.0006 / +0.0016 / -0.0007 | -0.0013 / +0.0010 / -0.0016 |
| bc5 B1 | +0.0012 / +0.0012 / +0.0013 | +0.0005 / +0.0002 / +0.0011 | -0.0002 / -0.0005 / +0.0004 |
| bc6 B2 | +0.0009 / +0.0001 / +0.0011 | +0.0012 / -0.0002 / -0.0007 | +0.0006 / -0.0006 / -0.0013 |
| bc7 U13 | +0.0025 / +0.0022 / +0.0022 | +0.0023 / +0.0030 / +0.0011 | +0.0011 / +0.0019 / +0.0001 |
| bc8 U13 | +0.0022 / +0.0021 / +0.0022 | +0.0020 / +0.0021 / -0.0009 | +0.0011 / +0.0011 / -0.0022 |
| bc9 X11 | +0.0023 / +0.0020 / +0.0023 | +0.0035 / +0.0033 / +0.0025 | +0.0026 / +0.0025 / +0.0020 |

**Cold start** (D 150 draws; I = mean over draws; maps fitted = fraction of draws per map, L_hi / L_lo|hi=0 /
L_lo|hi=1; margin p1 pooled over the draws' payload cells):

| band-capture | n | maps fitted | I hi / lo centroid-logit | dI hi / lo block-edge − logit | dI hi / lo raw − logit | margin p1 hi logit / edge |
|---|---|---|---|---|---|---|
| bc0 B3 | 1 | 1.00 / 0.00 / 0.02 | 0.8611 / 0.8708 | +0.0165 [+0.0101, +0.0226] / +0.0056 [+0.0017, +0.0091] | +0.0351 / +0.0120 | -0.60 / -2.56 |
| bc0 B3 | 2 | 1.00 / 0.95 / 1.00 | 0.9072 / 0.8668 | -0.0061 [-0.0100, -0.0022] / +0.0076 [+0.0041, +0.0109] | +0.0058 / +0.0242 | -0.51 / -2.72 |
| bc0 B3 | 8 | 1.00 / 1.00 / 1.00 | 0.9377 / 0.9106 | -0.0098 [-0.0119, -0.0077] / -0.0066 [-0.0088, -0.0044] | -0.0036 / +0.0066 | -0.40 / -0.76 |
| bc1 U12 | 1 | 1.00 / 0.00 / 0.03 | 0.8020 / 0.8003 | -0.0138 [-0.0216, -0.0075] / -0.0076 [-0.0104, -0.0050] | -0.0045 / -0.0132 | -1.61 / -4.04 |
| bc1 U12 | 2 | 1.00 / 0.94 / 1.00 | 0.8389 / 0.8029 | -0.0179 [-0.0225, -0.0132] / -0.0092 [-0.0139, -0.0047] | -0.0108 / +0.0070 | -1.72 / -4.73 |
| bc1 U12 | 8 | 1.00 / 1.00 / 1.00 | 0.8700 / 0.8443 | -0.0119 [-0.0139, -0.0100] / -0.0131 [-0.0149, -0.0116] | -0.0087 / -0.0035 | -2.03 / -2.54 |
| bc2 U12 | 1 | 1.00 / 0.00 / 0.05 | 0.8070 / 0.8043 | -0.0121 [-0.0186, -0.0062] / -0.0073 [-0.0097, -0.0051] | -0.0019 / -0.0158 | -1.54 / -4.04 |
| bc2 U12 | 2 | 1.00 / 0.93 / 1.00 | 0.8429 / 0.8071 | -0.0223 [-0.0286, -0.0160] / -0.0126 [-0.0182, -0.0073] | -0.0088 / +0.0049 | -1.75 / -4.73 |
| bc2 U12 | 8 | 1.00 / 1.00 / 1.00 | 0.8728 / 0.8473 | -0.0099 [-0.0113, -0.0085] / -0.0109 [-0.0128, -0.0090] | -0.0082 / -0.0028 | -1.95 / -2.45 |
| bc3 X10 | 1 | 1.00 / 0.00 / 0.01 | 0.8550 / 0.8811 | +0.0083 [+0.0012, +0.0150] / +0.0022 [-0.0015, +0.0056] | +0.0294 / +0.0012 | -0.81 / -3.41 |
| bc3 X10 | 2 | 1.00 / 0.90 / 1.00 | 0.8902 / 0.8680 | -0.0081 [-0.0141, -0.0027] / +0.0147 [+0.0097, +0.0189] | +0.0058 / +0.0291 | -0.86 / -3.84 |
| bc3 X10 | 8 | 1.00 / 1.00 / 1.00 | 0.9254 / 0.9125 | -0.0085 [-0.0107, -0.0065] / -0.0020 [-0.0039, -0.0001] | -0.0058 / +0.0076 | -0.76 / -1.24 |
| bc4 A1 | 1 | 1.00 / 0.00 / 0.01 | 0.9222 / 0.9606 | +0.0322 [+0.0298, +0.0347] / +0.0118 [+0.0098, +0.0138] | +0.0750 / +0.0331 | 1.29 / 2.21 |
| bc4 A1 | 2 | 1.00 / 0.93 / 1.00 | 0.9708 / 0.9492 | +0.0157 [+0.0142, +0.0173] / +0.0168 [+0.0160, +0.0177] | +0.0273 / +0.0442 | 1.94 / 4.17 |
| bc4 A1 | 8 | 1.00 / 1.00 / 1.00 | 0.9902 / 0.9817 | +0.0063 [+0.0059, +0.0069] / +0.0075 [+0.0072, +0.0078] | +0.0086 / +0.0123 | 2.79 / 6.11 |
| bc5 B1 | 1 | 1.00 / 0.00 / 0.01 | 0.9209 / 0.9590 | +0.0311 [+0.0285, +0.0339] / +0.0113 [+0.0097, +0.0134] | +0.0766 / +0.0330 | 1.28 / 2.19 |
| bc5 B1 | 2 | 1.00 / 0.94 / 1.00 | 0.9704 / 0.9474 | +0.0161 [+0.0148, +0.0176] / +0.0185 [+0.0175, +0.0197] | +0.0266 / +0.0423 | 1.93 / 4.11 |
| bc5 B1 | 8 | 1.00 / 1.00 / 1.00 | 0.9910 / 0.9806 | +0.0055 [+0.0052, +0.0058] / +0.0077 [+0.0072, +0.0081] | +0.0072 / +0.0108 | 2.91 / 6.11 |
| bc6 B2 | 1 | 1.00 / 0.00 / 0.03 | 0.9205 / 0.9585 | +0.0323 [+0.0301, +0.0347] / +0.0114 [+0.0098, +0.0129] | +0.0774 / +0.0330 | 1.30 / 2.18 |
| bc6 B2 | 2 | 1.00 / 0.95 / 1.00 | 0.9709 / 0.9483 | +0.0156 [+0.0146, +0.0166] / +0.0177 [+0.0169, +0.0185] | +0.0267 / +0.0447 | 2.00 / 4.08 |
| bc6 B2 | 8 | 1.00 / 1.00 / 1.00 | 0.9907 / 0.9816 | +0.0058 [+0.0054, +0.0061] / +0.0073 [+0.0068, +0.0078] | +0.0080 / +0.0120 | 2.89 / 6.11 |
| bc7 U13 | 1 | 1.00 / 0.00 / 0.01 | 0.9219 / 0.9558 | +0.0326 [+0.0297, +0.0357] / +0.0161 [+0.0134, +0.0190] | +0.0743 / +0.0353 | 1.26 / 2.20 |
| bc7 U13 | 2 | 1.00 / 0.95 / 1.00 | 0.9712 / 0.9461 | +0.0153 [+0.0142, +0.0165] / +0.0194 [+0.0181, +0.0208] | +0.0248 / +0.0434 | 1.97 / 4.14 |
| bc7 U13 | 8 | 1.00 / 1.00 / 1.00 | 0.9910 / 0.9805 | +0.0055 [+0.0053, +0.0058] / +0.0082 [+0.0077, +0.0086] | +0.0067 / +0.0110 | 2.85 / 6.11 |
| bc8 U13 | 1 | 0.99 / 0.00 / 0.05 | 0.9276 / 0.9595 | +0.0290 [+0.0263, +0.0321] / +0.0132 [+0.0114, +0.0151] | +0.0683 / +0.0328 | 1.40 / 2.24 |
| bc8 U13 | 2 | 1.00 / 0.93 / 1.00 | 0.9711 / 0.9460 | +0.0154 [+0.0145, +0.0164] / +0.0190 [+0.0176, +0.0204] | +0.0250 / +0.0423 | 2.01 / 4.29 |
| bc8 U13 | 8 | 1.00 / 1.00 / 1.00 | 0.9912 / 0.9810 | +0.0053 [+0.0051, +0.0055] / +0.0077 [+0.0074, +0.0080] | +0.0059 / +0.0101 | 2.88 / 6.11 |
| bc9 X11 | 1 | 1.00 / 0.00 / 0.03 | 0.9214 / 0.9608 | +0.0323 [+0.0302, +0.0348] / +0.0153 [+0.0134, +0.0178] | +0.0762 / +0.0358 | 1.21 / 2.17 |
| bc9 X11 | 2 | 1.00 / 0.97 / 1.00 | 0.9689 / 0.9459 | +0.0169 [+0.0156, +0.0184] / +0.0208 [+0.0199, +0.0217] | +0.0292 / +0.0513 | 1.82 / 4.18 |
| bc9 X11 | 8 | 1.00 / 1.00 / 1.00 | 0.9894 / 0.9810 | +0.0063 [+0.0058, +0.0068] / +0.0097 [+0.0093, +0.0102] | +0.0094 / +0.0171 | 2.70 / 6.11 |

## (c) Paper through the receiver's lane — e044, truth-fitted poses, context off

The production colour job (`color_region.region_job`) on the real capture, every window at its truth-fitted pose
(scorelane.py's poses, window grid and truth arm); COLD = one region over all windows, FIRST-FIRE = each 200-cell
window its own region, both furniture-only. I hi / I lo per evaluator; "chain worn" = lanes where production's gate
adopted centroid-logit. Every number in this section is a POINT ESTIMATE over one capture at truth-fitted poses:
`evaluator_lanes.summarise` computes no bootstrap, so no e044 difference below carries an interval.

**Sheet B, c3-cmy-r0850@35x24** (5.4 M cargo cells per regime and level; every map qualified on every lane):

| level (ppc) | regime | lanes | chain worn (production) | gate adopts logit / edge | I hi / lo raw | centroid-linear | centroid-logit | block-edge | gated:logit | gated:edge |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 (2) | cold | 1 | 0 | 0 / 0 | 0.9900 / 0.9840 | 0.9347 / 0.9217 | 0.9888 / 0.9824 | 0.9904 / 0.9847 | 0.9900 / 0.9840 | 0.9900 / 0.9840 |
| 0 (2) | first-fire | 140 | 0 | 0 / 3 | 0.9897 / 0.9837 | 0.8856 / 0.8497 | 0.9695 / 0.9478 | 0.9849 / 0.9712 | 0.9897 / 0.9837 | 0.9897 / 0.9835 |
| 1 (4) | cold | 1 | 0 | 0 / 0 | 0.9921 / 0.9863 | 0.9647 / 0.9421 | 0.9941 / 0.9875 | 0.9945 / 0.9878 | 0.9921 / 0.9863 | 0.9921 / 0.9863 |
| 1 (4) | first-fire | 140 | 0 | 0 / 6 | 0.9917 / 0.9856 | 0.8914 / 0.8564 | 0.9733 / 0.9520 | 0.9890 / 0.9755 | 0.9917 / 0.9856 | 0.9918 / 0.9855 |
| 2 (6) | cold | 1 | 0 | 0 / 0 | 0.9942 / 0.9884 | 0.9793 / 0.9544 | 0.9954 / 0.9887 | 0.9950 / 0.9884 | 0.9942 / 0.9884 | 0.9942 / 0.9884 |
| 2 (6) | first-fire | 140 | 0 | 0 / 3 | 0.9931 / 0.9874 | 0.8946 / 0.8544 | 0.9744 / 0.9515 | 0.9896 / 0.9761 | 0.9931 / 0.9874 | 0.9932 / 0.9874 |
| 3 (12) | cold | 1 | 0 | 0 / 0 | 0.9958 / 0.9901 | 0.9452 / 0.9200 | 0.9955 / 0.9897 | 0.9959 / 0.9909 | 0.9958 / 0.9901 | 0.9958 / 0.9901 |
| 3 (12) | first-fire | 140 | 0 | 0 / 5 | 0.9948 / 0.9888 | 0.8997 / 0.8653 | 0.9780 / 0.9574 | 0.9923 / 0.9793 | 0.9948 / 0.9888 | 0.9949 / 0.9888 |

**Sheet A, c2-cmy-r0775x0700@53x37** (12.2 M cargo cells per regime and level):

| level (ppc) | regime | lanes | chain worn (production) | gate adopts logit / edge | I hi / lo raw | centroid-linear | centroid-logit | block-edge | gated:logit | gated:edge |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 (2) | cold | 1 | 1 | 1 / 0 | 0.8303 / 0.8208 | 0.8409 / 0.8353 | 0.8407 / 0.8353 | 0.8400 / 0.8349 | 0.8407 / 0.8353 | 0.8303 / 0.8208 |
| 0 (2) | first-fire | 315 | 33 | 33 / 12 | 0.8280 / 0.8171 | 0.8055 / 0.7647 | 0.8309 / 0.8156 | 0.8167 / 0.8008 | 0.8294 / 0.8188 | 0.8280 / 0.8172 |
| 1 (4) | cold | 1 | 1 | 1 / 0 | 0.8428 / 0.8317 | 0.8537 / 0.8459 | 0.8532 / 0.8459 | 0.8522 / 0.8456 | 0.8532 / 0.8459 | 0.8428 / 0.8317 |
| 1 (4) | first-fire | 315 | 27 | 27 / 14 | 0.8406 / 0.8283 | 0.8137 / 0.7708 | 0.8425 / 0.8245 | 0.8299 / 0.8132 | 0.8417 / 0.8298 | 0.8406 / 0.8283 |
| 2 (8) | cold | 1 | 1 | 1 / 1 | 0.8402 / 0.8310 | 0.8514 / 0.8454 | 0.8511 / 0.8454 | 0.8500 / 0.8450 | 0.8511 / 0.8454 | 0.8500 / 0.8450 |
| 2 (8) | first-fire | 315 | 33 | 33 / 16 | 0.8387 / 0.8281 | 0.8125 / 0.7710 | 0.8412 / 0.8241 | 0.8275 / 0.8120 | 0.8401 / 0.8297 | 0.8390 / 0.8283 |

At ppc 4, the full rows (the other levels in the artefact's `evaluator.md`):

**Sheet B, ppc 4, cold** — 1 lane(s), 5,436,433 cargo cells; production wore the chain on 0; gate adopts linear 0, logit 0, edge 0

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo |
|---|---|---|---|---|---|---|---|
| raw | 0.9921 | 0.9863 | 0.9891 | 0.0055 / 0.0095 | 6033 / 13004 | 2.63 / 2.30 | 4.44 / 4.39 |
| centroid-linear | 0.9647 | 0.9421 | 0.9532 | 0.0245 / 0.0401 | 4812 / 11772 | 1.33 / 0.92 | 1.89 / 1.58 |
| centroid-logit | 0.9941 | 0.9875 | 0.9899 | 0.0041 / 0.0087 | 4810 / 11771 | 3.14 / 2.42 | 5.13 / 4.54 |
| block-edge | 0.9945 | 0.9878 | 0.9901 | 0.0038 / 0.0085 | 4786 / 11690 | 4.08 / 3.52 | 10.03 / 8.82 |
| gated:centroid-logit | 0.9921 | 0.9863 | 0.9891 | 0.0055 / 0.0095 | 6033 / 13004 | 2.63 / 2.30 | 4.44 / 4.39 |
| gated:block-edge | 0.9921 | 0.9863 | 0.9891 | 0.0055 / 0.0095 | 6033 / 13004 | 2.63 / 2.30 | 4.44 / 4.39 |

**Sheet B, ppc 4, first-fire** — 140 lane(s), 5,436,433 cargo cells; production wore the chain on 0; gate adopts linear 0, logit 0, edge 6

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo |
|---|---|---|---|---|---|---|---|
| raw | 0.9917 | 0.9856 | 0.9884 | 0.0057 / 0.0100 | 5883 / 11877 | 2.49 / 2.02 | 4.24 / 3.95 |
| centroid-linear | 0.8914 | 0.8564 | 0.8900 | 0.0753 / 0.0996 | 5853 / 13858 | 0.51 / 0.35 | 1.03 / 0.86 |
| centroid-logit | 0.9733 | 0.9520 | 0.9607 | 0.0185 / 0.0332 | 5842 / 12308 | 1.39 / 0.91 | 2.64 / 2.08 |
| block-edge | 0.9890 | 0.9755 | 0.9800 | 0.0076 / 0.0170 | 6131 / 13437 | 5.53 / 3.50 | 5.53 / 4.37 |
| gated:centroid-logit | 0.9917 | 0.9856 | 0.9884 | 0.0057 / 0.0100 | 5883 / 11877 | 2.49 / 2.02 | 4.24 / 3.95 |
| gated:block-edge | 0.9918 | 0.9855 | 0.9884 | 0.0057 / 0.0100 | 5875 / 12007 | 2.56 / 2.12 | 4.36 / 4.09 |

**Sheet A, ppc 4, cold** — 1 lane(s), 12,232,017 cargo cells; production wore the chain on 1; gate adopts linear 1, logit 1, edge 0

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo |
|---|---|---|---|---|---|---|---|
| raw | 0.8428 | 0.8317 | 0.8900 | 0.1090 / 0.1166 | 432396 / 460785 | -2.86 / -3.10 | 0.79 / 0.69 |
| centroid-linear | 0.8537 | 0.8459 | 0.8986 | 0.1014 / 0.1068 | 432390 / 458377 | -2.20 / -2.46 | 0.62 / 0.62 |
| centroid-logit | 0.8532 | 0.8459 | 0.8988 | 0.1017 / 0.1068 | 432390 / 458380 | -2.21 / -2.47 | 0.62 / 0.62 |
| block-edge | 0.8522 | 0.8456 | 0.8983 | 0.1025 / 0.1070 | 433919 / 459018 | -2.18 / -2.46 | 0.74 / 0.60 |
| gated:centroid-logit | 0.8532 | 0.8459 | 0.8988 | 0.1017 / 0.1068 | 432390 / 458380 | -2.21 / -2.47 | 0.62 / 0.62 |
| gated:block-edge | 0.8428 | 0.8317 | 0.8900 | 0.1090 / 0.1166 | 432396 / 460785 | -2.86 / -3.10 | 0.79 / 0.69 |

**Sheet A, ppc 4, first-fire** — 315 lane(s), 12,232,017 cargo cells; production wore the chain on 27; gate adopts linear 8, logit 27, edge 14

| evaluator | I hi | I lo | I lo\|hi | log-loss hi / lo | flips hi / lo | margin p1 hi / lo | margin p5 hi / lo |
|---|---|---|---|---|---|---|---|
| raw | 0.8406 | 0.8283 | 0.8873 | 0.1105 / 0.1190 | 430871 / 460891 | -2.93 / -3.17 | 0.81 / 0.70 |
| centroid-linear | 0.8137 | 0.7708 | 0.8242 | 0.1291 / 0.1589 | 450294 / 509872 | -1.83 / -1.40 | 0.37 / 0.14 |
| centroid-logit | 0.8425 | 0.8245 | 0.8759 | 0.1092 / 0.1217 | 443524 / 483048 | -2.11 / -1.90 | 0.53 / 0.30 |
| block-edge | 0.8299 | 0.8132 | 0.8659 | 0.1179 / 0.1295 | 457004 / 494047 | -3.01 / -4.32 | 0.62 / 0.50 |
| gated:centroid-logit | 0.8417 | 0.8298 | 0.8882 | 0.1097 / 0.1180 | 432434 / 462281 | -2.80 / -2.99 | 0.78 / 0.63 |
| gated:block-edge | 0.8406 | 0.8283 | 0.8869 | 0.1105 / 0.1190 | 432863 / 461434 | -2.92 / -3.18 | 0.79 / 0.70 |

The gate's legs on sheet A's cold region (total / word / dust, mean 4-state NLL on 56,869 validation rows): raw
0.19756 / 0.20264 / 0.15360 at ppc 2, centroid-logit 0.18992 / 0.19436 / 0.15142 (adopted), block-edge 0.19074 /
0.19477 / 0.15585 (refused: dust worse than raw); ppc 4 raw 0.18596 / 0.19015 / 0.14961, logit 0.17784 / 0.18163
/ 0.14500, edge 0.17871 / 0.18182 / 0.15175 (refused); ppc 8 edge 0.14615 against raw 0.15074, adopted. On sheet B
the chain's total leg is worse than raw's for every evaluator at every level (ppc 4: raw 0.01179, logit 0.01201,
edge 0.01200).

## Reading, for the owner's ruling

Block-edge recovers the squeeze on the noiseless sims and on the emulation at σ 0.04 (p99 192: +0.065 / +0.019 bit)
— where the squeeze lives, on separable maps whose within-class spread spans orders of magnitude (that
characterisation is INFERENCE from the A8 refuter's scale probe, scratchpad a8probe/scale.py, not measured on this
line) — and there it also turns the faint page's tie into an adoption (hi 0.4998 → 0.9995; at σ 0.04 0.7841 →
0.9919). It does NOT do so without losing information on paper: on every c2 band of the R11 extracts it reads
0.0006–0.0062 bit/cell below centroid-logit on the page; cold it reads 0.006–0.022 below on hi at n = 2 and 8 and
0.002–0.013 below on lo at n = 8 (lo at n = 2 and both streams at n = 1 mixed: B3 and X10 gain, U12 loses), its
wrong cells more confident (cold p1 margin on hi −0.76 to −4.73 against −0.40 to −2.03); through the receiver's
lane on e044 A (point estimates, no interval) it loses 0.0007–0.0011 bit on hi on the cold region and 0.013–0.014
per first-fire window, unconditionally, and gated 0.010 / 0.014–0.015 on the cold region at ppc 2 and 4 (its
candidate's dust leg — M read as M — goes worse than raw's) and 0.0011–0.0014 on hi per first-fire window. Where it
gains on paper (the lossless c3 controls, +0.0001–0.0025 on hi, within 0.003 of raw; e044 B unconditionally,
+0.014–0.016 per first-fire window, point estimates) it does not gain everywhere — on the same c3 controls it loses
on lo in 3 of 18 page fits (A1 k0 [−0.0011, −0.0001], A1 k2 [−0.0013, −0.0002], B2 k2 [−0.0012, −0.0002]) and on
lo|hi in 5 (A1 k0, A1 k2, B2 k1, B2 k2, U13-4800 k2; a sixth, B1 k1, at upper bound −0.00005), intervals wholly
below zero — and on B production wore raw on every lane: block-edge's gate would adopt on 3 / 6 / 3 / 5 of 140
first-fire windows at ppc 2 / 4 / 6 / 12 and on none cold, centroid-logit's on none, even on the cold region at ppc
4 and 6 where centroid-logit and block-edge read 0.0001–0.0024 above raw on the cargo (a gate-versus-cargo
disagreement, recorded, not this line's) — so the gated emission differs from raw by ≤ 0.0002 on B. The emulation
at σ 0.06 reads edge −0.0015 / −0.0016; its p99 |L| (97) lies within the range paper's first-fire p99 reaches
(122), so by that statistic — a statistic of the map's range, not of information; the placement is INFERENCE — it
sits on paper's side. Measured cost of the shipped evaluator against the first one (probability-linear) stays as
R11 found it: centroid-linear is 0.045–0.086 bit below logit on c3 and up to 0.025 on c2. If R11's evaluator clause
were amended to block-edge as it stands, the clause would trade 0.0006–0.006 bit on every c2 page fit and a gate
refusal on sheet A's cold region for the separable sims' squeeze. Amended as it stands, the clause would read
"EVALUATOR: per PAVA block a node at its first and at its last training score, both at the block's probability,
joined in logit, flat beyond the end nodes, E017.6's zero node kept, inside the cmy entry point" — and on this
record it would have to carry its measured c2 cost beside it. The measurements do not show a single node rule that
wins on both, so an amendment would have to say which regime it serves — or condition the node rule on the map
(e.g. block-edge only where the map is separable, two blocks at the clamp), which is a new mechanism and unmeasured
here. What this line does not measure: LDPC or tile yield (information only), the context head on top of any
evaluator, sheet A or B at any other pose than truth, e043 (no format page, no cmy_calibration extract), cmy8.
