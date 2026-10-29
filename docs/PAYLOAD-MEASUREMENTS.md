# PAYLOAD-MEASUREMENTS — payload/fountain timing record (2026-08-01)

Purpose: the complete measured record of payload- and fountain-stage
timing gathered during the v0.33/v0.34 phased-session-schedule work,
packaged as input to the payload-stage KISS/functionality review thread.
Everything here is a measurement or a file:line-verified code fact; the
interpretation paragraphs say which is which.  Machine: 12-core / 64 GiB
darwin, numpy 2.5.x / scipy 1.18.x, this repo's `env`.

Reproduction:

```
PYTHONPATH=src env/bin/python tests/holo/_bench_phased.py          # synthetic
PYTHONPATH=src env/bin/python tests/holo/_bench_real_corpus.py \
    scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-20260731-155516
# baseline arm: git worktree add <dir> f3711ea; copy the runner in; run there.
```

(2026-10-11: the corpus bytes were not kept — 19 GB of seeded simulation
output, by the evidence line's ruling. They are the output of
`scripts/run_c2_cmy7_hp_canon_chain.sh` as committed at 5c469945
(2026-07-29): a zero-filled payload of the capacity size, `holo.cli
generate` (coding c2-cmy7-p120-v0, printer hp-m281, source fraction
0.7), ghostscript at 600 dpi, `holo.qualification.color_distort
--profile nominal --seed 20260729 --output-dpi 4800`,
`holo.qualification.scrap_scan --pages 2 --scraps 20 --seed 20260730`.
These generation steps are unchanged through HEAD, and the
holo.qualification modules they call are also still in the tree; later
commits changed only the script's default run directory and its last
step, the v1 receiver's decode that wrote `receive.json` (that receiver
left the tree on 2026-09-05; from b167b9f the script decodes with
holo3), so a recreation of that decode runs on a checkout of that era;
byte-identity across ghostscript and numpy versions is not promised
(evidence line, docs/EVIDENCE-ARCHIVE-2026-10-08.md §12).)

## 1. Real-corpus A/B, instrumented (the primary dataset)

Corpus: `scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-20260731-155516`
— c2-cmy7-p120-v0@3328x2304, page domain {0}, two scrap captures
(`scraps-r4800-001/002.tif`, 6,811,996,672 bytes EACH, 4800 dpi), fresh
sessions, sequential runs.  `payload.bin` is ground truth; a scrap-only
session cannot reach K, so neither arm closes (that is expected and
correct).

Raw JSON, phased arm (HEAD, v0.34):

```
{"wall_s": 1724.0, "verified": false, "certificates": 604,
 "close_status": "open", "levels_per_capture": [8, 8],
 "peak_rss_mib": 23089,
 "stage_seconds": {"base.address": 329.5, "base.payload": 532.2,
                   "base.survey": 196.2, "mopup.address": 320.0,
                   "mopup.payload": 13.6, "mopup.survey": 0.0},
 "runtime_residual_s": 332.5, "barriers": 16, "colds": 148,
 "close_checks": 16, "capture_resumes": 10, "phase_events": 5}
```

Raw JSON, baseline arm (f3711ea, capture-major, pre-implementation):

```
{"wall_s": 1555.4, "verified": false, "certificates": 604,
 "close_status": "open", "levels_per_capture": [4, 4],
 "peak_rss_mib": 16387,
 "stage_seconds": {"base.address": 627.6, "base.payload": 550.3,
                   "base.survey": 194.6},
 "runtime_residual_s": 182.9, "barriers": 8, "colds": 152,
 "close_checks": 8}
```

An earlier uninstrumented pair (same corpus, same arms, separate runs)
for variance: phased 1666.2 s / RSS 23,107 MiB; baseline 1499.8 s /
RSS 16,409 MiB.  Run-to-run wall variance ~3.5%.

### 1.1 Attribution table (processor seconds)

| bucket | baseline | phased | delta | reading |
|---|---:|---:|---:|---|
| survey | 194.6 | 196.2 | +1.6 | unchanged work |
| address | 627.6 | 649.5 (329.5+320.0) | +21.9 | cold/rest RELOCATED to mop-up; the "+22 s = D7 label reconstruction + parked re-sampling" reading is INTERPRETATION, not a measured decomposition (MR-08): the timer seam is honest, but no instrument split the +22 s, and D7 label cost also recurs under mopup.payload |
| payload | 550.3 | 545.8 (532.2+13.6) | −4.5 | unattributed run-to-run variance — NOT "pooled labels" (falsified by finding color-payload:01: this c2-cmy7 color payload stage consumed no labels at all until the v0.35 pool law's stage 1b wired them) |
| residual | 182.9 | 332.5 | +149.6 | see §1.2 — source re-auth |
| wall | 1555.4 | 1724.0 | +168.6 | |

Yield: 604 = 604 certificates, both arms.  Colds 152 → 148 (hint
inheritance), all phased colds at the tail.  Fountain solves: baseline
paid 8 full solves (one per barrier); phased paid ~0 (all 16 checks
count-gated by D8).

### 1.2 The residual is source re-authentication, measured directly

One SHA-256 pass over one 6.8 GB scrap TIFF: **19.08 s** (17.77 user,
99% cpu — `shasum -a 256`).  `verify_source_unchanged` re-streams the
committing capture's source at every retention barrier, and
`open_capture` hashes once at ingest:

- baseline: 2 ingest + 8 barrier hashes ≈ 190 s — measured residual 182.9;
- phased: 2 ingest + 16 barrier hashes ≈ 342 s — measured residual 332.5.

The whole +169 s wall delta is therefore **eight extra 6.8 GB source
re-authentications** (one per added M-level barrier).  Persist and the
gated close checks are minor terms at this corpus size.  Any
optimization is design-gated on the §8 re-authentication law
(per-barrier re-auth is an integrity invariant); candidate rulings are
listed in PHASED-SCHEDULE §5a-bis.  NOTE for small sources this term
vanishes: the synthetic corpus (§2) has ~MB-scale arrays and its
residual is negligible.

### 1.3 Payload stage is the dominant compute on real color material

On the baseline arm, payload = 550.3 s of 1555.4 s wall (~35%; address
40%, survey 13%, residual 12%).  For the payload KISS review: the stage
under review is the single largest numerical bucket on real CMY7
material.  Its internals (not decomposed by this instrument): window
crop/filter + order-1 sampling, per-window QDA/PAVA calibration,
per-region ctx fit with held-out adoption, BP (max60 scan/union +
selective retry150), CRC certification, divergence audit.
Finer-grained per-phase numbers exist in the diag cost memory
(holo-diag-cost-model): retry150 ≈ 36 s per ~300-tile frontier;
measured event-flow costs; `_word_route` 17.53 s of a 24.6 s address
run at qualification geometry.

### 1.4 Peak RSS

16.4 → 23.1 GiB (+41%).  Suspects, unverified: the D10 raster pool
(both 6.8 GB TIFFs stay open across phases — mmap, so RSS counts
resident pages touched by hashing/sampling), M-level lane
re-materialization (fresh anonymous memmaps at the tail), and the
mop-up/label sampling churn.  A decomposition (e.g. RSS sampling per
phase) has NOT been done — candidate instrument for the review thread.

## 2. Synthetic A/B (close-preemption regime)

`tests/holo/_bench_phased.py` — roundtrip fixture field + two re-placed
scraps, single page, K row, byte-identical corpus:

| | baseline f3711ea | phased HEAD |
|---|---:|---:|
| wall | 49.67 s | 13.46 s (3.7x) |
| colds | 45 | 0 |
| full fountain solves | 2 | 1 |
| close checks | 2 | 4 (3 gated) |
| barriers | 2 | 4 |
| certificates | 49 | 49 |
| verified | yes | yes |

Mechanism (verified by event counts): parking erased every in-lane
cold; the session verified at the first close-gate-passing barrier and
close preemption skipped the whole tail and the scraps' remaining
lanes.  This is the regime the phased schedule was built for; §1 is the
regime it merely must not damage (yield held exactly; wall cost =
re-auth, not machinery).

## 3. Fountain/close cost facts (file:line-verified, 2026-07-31 read)

- The decoder is NOT persisted: every `close_volume` rebuilds
  `VolumeCode` + `Decoder` from the durable certificate frontier
  (fountain_close.py `_build_decoder`); page assignments re-derive (AES
  keystream draws + argsort per touched page, cached per instance only).
- `certificate_for_close` recomputes the full certificate identity hash
  per certificate per consult (records.py:181+).  The D8 gate
  memoizes these conversions per `ProductionClose` instance, keyed by
  `certificate_id` (true since phase 2 of the payload rework,
  RECEIVE-DESIGN v0.36; the v0.34 record asserted this before the memo
  existed — MR-01).
- Rank: `rank_status()` runs coefficient-only packed GE over
  `have x K_b` per partially-filled non-systematic block; systematic-
  complete blocks shortcut to rank K_b with no GE.  The declared
  feasibility knee is ~1 min/block of GE at K_b = 16384
  (fountain.py:15-16 — pin re-anchored 2026-08-02, MR-02).
- `close_count_ready` / `distinct_esi_block_counts` are count-only
  (no decoder, no coefficient rows) — the D8 gate's consult cost is
  O(certificates) hashing-free counting per barrier.
- D16 surplus audit: O(symbols x row weight) over SOLVED blocks only,
  one bulk frozen-row draw per block; zero cost in §1 (nothing solves)
  and negligible in §2.
- Measured gate effect: §1 baseline paid 8 decoder rebuilds + solves
  over 604 certificates; phased paid ~0.  §2: 2 solves → 1.

## 4. Historical anchors (context for regressions)

Three-way synthetic chain (address-stage CPU, byte-identical inputs,
2026-07-31): v0.21 = 493 s, v0.24 = 783 s, v0.31 = 647 s; all-stages
1394 s.  The v0.24 regression (+267 s) was the all-slot up-front word
sweep, cured by v0.26 staged Stage A (3,627 → 794 ms/window) and v0.29
lazy slot staging; the ~150 s residual (rest-ahead-of-cheap-cold at the
cold boundary) was resolved by the §3.5 price rule, which now lives in
the v0.33 engine (`cold_first_max_pages = 1`).

Cold-search costs: ~1–3 s at P=1 (the §1 corpus regime), 47.9 s at
P=312 (C3 full domain, 9.4 GiB peak — page-transform cache ~7.6 GiB);
one 8-slot rest sweep ≈ 2.8 s.

## 5. Open items this data motivates (for the review thread)

1. RSS decomposition of §1.4 (23.1 GiB) — no instrument yet.
2. The §8 re-auth ruling for multi-barrier plans on large sources
   (§1.2) — design-gated, sized at ~19 s x extra barriers here.
3. Per-phase payload internal decomposition (sampling vs calibration vs
   BP vs CRC) — the 532–550 s bucket is currently opaque; the profiling
   doctrine wants one instrumented single-decode harness, never pytest.
4. Growth-audit queued persist items (blob cache etc.) — real but
   second-order at this corpus size (residual arithmetic in §1.2 leaves
   them ≤ ~10 s per arm).

## 6. Payload-rework final checkpoint A/B (2026-08-02, branch payload-rework)

Same corpus, runner, and machine as §1; HEAD = the completed rework
(RECEIVE-DESIGN v0.41 + the crop-free refinement pre-gate). The runner
gained per-bucket payload decomposition (the §5-item-3 instrument, ported
from `_bench_payload_decomp`) and a BENCH-ONLY `--counterfactual-no-refine`
arm (never a production knob).

| arm | wall | base.payload | residual | RSS | certs |
|---|---:|---:|---:|---:|---:|
| capture-major baseline (f3711ea) | 1555.4 | 550.3 | 182.9 | 16.4 GiB | 604 |
| pre-rework phased (v0.34) | 1724.0 | 532.2 | 332.5 | 23.1 GiB | 604 |
| HEAD, counterfactual no-refine | **1485.9** | **457.4** | 149.5 | 27.4 GiB | 604 |
| HEAD, full (color refinement on) | 2036.5 | 959.9 | 154.2 | 27.2 GiB | 604 |

Attribution (instrumented, per-bucket):

- **The rework itself MEETS the plan's wall target**: 1486 s beats the
  capture-major baseline (−70 s) and pre-rework phased (−238 s, −14%),
  yield identical. Delivered as designed: re-auth stat-memo (residual
  332→150 s), D8 count gating + close plumbing, vectorization + label law
  (base.payload 532→457 s despite the added label rows), colds 148,
  16/16 close checks count-gated.
- **Color refinement (ruling 10.6) costs ~550 s on this corpus for zero
  yield**: 986 window crop+grid fits across 16 barriers, ~94% of the
  payload bucket in sampling_calibration_ctx; BP/CRC total is ~38 s. This
  corpus is the worst case for it — non-closing, coverage-limited (the
  uncertified remainder is below_attempt_floor), 4800 dpi crops. The
  crop-free cargo pre-gate (v0.41 checkpoint fix) is exact and pinned but
  most scrap windows genuinely border certified tiles, so it removes
  little here.
- **RSS ~27.4 GiB** (vs 23.1 pre-rework): the ruled 7.1 derived-lane pool
  (~+4.3 GiB of file-backed, evictable derived-lane mmaps held for the
  invocation). Expected, recorded, deprioritized per 7.3.

OPEN RULING (refinement scheduling — the one item this checkpoint sends
back): (a) tail-relocate color refinement to M-levels (the phased
philosophy: costly improvement last, close-preemptible — free on closing
sessions, same total on --complete/non-closing); (b) floor-price gate
(skip refinement for windows whose uncertified tiles are below the
attempt floor this lane — recovers ~all 550 s here; heuristic,
amendment-sized); (c) accept as priced work (hardware will show its
yield); (d) = (a)+(b). K refinement stays inline per its measured
history either way (1200 dpi, affordable); the K/color scheduling
asymmetry would be recorded if (a)/(b) adopted.

RESOLVED (adjudicated 2026-08-02): option (a)-AS-LANE — refinement (K
AND color, superseding the "K stays inline" lean above by the same
ruling) moves out of the inline payload stages into dedicated
refinement lanes `R(Lk)` appended to the scale plan after all
M-levels, run only under the new invocation-only `--refine` flag and
close-preemptible like the rest of the tail. Full decision text:
docs/PHASED-SCHEDULE.md D20; normative amendment RECEIVE-DESIGN v0.42.

## 7. R-lane qualification pair (2026-08-02, branch rlane-qual, v0.44 + viewer fix)

Corpus as §1; CPU (user+sys) is primary per the standing measurement rule
(wall contended + diag on 8023 throughout; machine shared).

- **Run 1 (default flags — ordinary ladder only): CPU 1166 s** (1152 u +
  14 s), exit 2, **601 certificates**, 95 windows parked across 8 M-lanes,
  8 R-lanes pending, distinct-symbol reach 601/1294. The parking flags do
  their job: the default run pays neither tail.
- **Run 2 (resume, --mopup --refine): CPU 1192 s** (1150 u + 42 s), exit
  2, **CRASH-FREE through every M- and R-level** — the v0.44 audited
  reconstruction's real-corpus proof (the pre-fix run died at the first
  478b R-level). M-levels minted exactly **+3 (601 → 604)**; R-levels
  attempted and minted **0**.
- **The 605th-certificate question, answered**: the crashed pre-fix run's
  R-minted tile (33, 29) was genuinely ATTEMPTED six times here (scan +
  retry150 at r01/r02/r03) and failed CRC each time. The pre-fix mint
  rode the rectangle reconstruction's polluted calibration (off-support
  background cells in the fit) that happened to push this borderline
  tile over the decode threshold — CRC proved those bits correct, a
  lucky-but-valid decode. The audited (per-design) population leaves it
  just under. Recorded as the measured face of the v0.44 policy bump;
  the tile is prime 3-4-scans-doctrine material (six near-misses).
- **NEW HEALTH-CANARY FINDING (open)**: run 2's epilogue reports
  `mop-up supersession dropped 44561 DISAGREEING observation(s) at
  committed cells` — synthetics showed ~0. Committed evidence is
  unchanged by construction (drops are safe), but the magnitude says the
  M-level re-observes its own lane's cells with different values.
  Leading hypothesis: the M-level's pooled region pitch (placements ∪
  labels ∪ its own windows, pool law L5) yields a different integer
  aperture than the base pass, so every re-observed cell differs at the
  byte level through the different filter. Needs its own investigation
  (the D5 counter was built for exactly this signal).
  INVESTIGATED 2026-08-02 (docs/CANARY-D5-DISAGREEMENTS.md): the
  aperture hypothesis is NOT the mechanism — 0 integer flips across
  all 42 cross-pass pool groups; the 44,561 reproduce exactly on
  byte-identical src and decompose as 100% different-window value
  disagreement at M-window overlap with committed coverage
  (structural: per-pass owner freeze + D4 fresh/parked ordinals make
  same-window re-observation impossible), multiplied once per ladder
  lane.   Committed evidence safe; state-winner flips 7.7% is the real
  health statistic; ruling options pending (counter split / aperture
  pin / doc amendment).
  RULED "replace" + EXECUTED same day (RECEIVE-DESIGN v0.46): the
  counter now reports dropped observations + winner flips; production
  confirmation reproduced dropped 44,561 exactly with winner flips
  2,383 (5.35%) under the corrected W-relative convention. The
  aperture-invariant ruling (option 2 vs 3) stays open.
- Viewer: all lanes rendered end-to-end (M rows, R rows, tri-state
  pane C); zero observer failures both runs.
