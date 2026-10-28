# Experiment 016 — ARCH-3: the first CODED archive sheet (c2 volume)

**2026-07-09.** The full stack on one sheet, printed: data → fountain-v1 →
per-tile LDPC r0550 + CRC-32 → kcell-c2 compose (e014 page geometry,
p60b6.v3 pilots) → home M281. Built the same day 014.2 measured the c2
channel at 1.4–2% (ctx + multi-scan, Canon 4800) — but on the OFFICE
AltaLink print; the M281's c2-at-16px/cell is unmeasured (its 2 px/dot
history: 11–14%, day-fragile whites), hence the CONSERVATIVE rung:

- **Volume: 361,833 bytes** (seeded rng bytes, data sha 412b9256…) =
  1387 source + 347 repair symbols × 2087 bits, **K/N 0.800** — ANY ~80%
  of the 1734 interior 64-cell tiles recovers ALL data byte-exact (the
  on-page crease/confetti budget). Net-if-recovered ≈ 55 b/mm².
- Volume seed `b"paper-store/exp016-arch3"` keys everything.
- **build/e016.ps sha256 `796f2609…53`** (golden in tests/test_e016.py).

**M0 gate, scope-DECLARED (e014 precedent):** the sim's c2 channel is the
known-pessimistic white-closure floor that no blind receiver passes (the
suite asserts sim-c2 fails clean; hardware decodes at ~8% raw / ~1.4% ctx
+multi-scan). Pre-toner gates run instead: byte-identical regeneration +
golden sha; gs render pixel-exact (29.3M dots); CODED machinery byte-exact
on the clean channel (blind acquire → tile map → r0550 CRC certify → user
bits match the fountain frame); sim genie-footing BER 15.1% = the known
c2 regime. Retraction rule: if Canon scans of the print fail to certify
at rates 014.2 predicts, that is an M281-vs-AltaLink c2 engine/day
finding (or a rate-rung finding), NOT a format retraction, unless pilot
BER > 20% on a clean scan.

**PRINTED 2026-07-09 — via `lpr -o raw` (USER), not print_plane.sh.**
CORRECTION on the record: the print_plane.sh attempt FAILED SILENTLY —
the script's interactive confirmation (`read`) hit EOF non-interactively
and `set -e` killed it before sending a byte; the calling pipeline's
`| tail` masked the exit status, so the session first logged "exit 0"
(wrong twice). Port 9100 verified reachable post-hoc; the script now
refuses loudly without a tty. Print path deviation is LOW-RISK and
declared: `-o raw` bypasses CUPS filters, and 001.2/001.3 retracted the
lpr-corruption alarm (9100 is preferred for attributability, not
correctness) — the CRC certification of this coded sheet is the
definitive bit-fidelity referee either way.

## Decode protocol (pre-registered)

Scan: Canon 4800 dpi grey (scanimage pixma, enhancements off), sheet
flattened (book — 014.2: crease shoulders halve), 2–3 RE-PLACED scans;
`tilemap.more_scans_useful()` is the stop rule per page,
`tilemap.volume_scans_wanted()` across the volume. Decode:
`formats.page_decode(..., detector="ctx", calibrate=True)` per scan →
`decode_tiles("r0550", policy="best_per_tile")` → `certified_results()` →
`fountain.tiles_to_symbols` → `volume_decode` → data sha must equal
412b9256… . ENVELOPE: PASS = byte-exact data recovery from ≤3 scans;
report per-tile certification rate + per-scan BER vs the 014.2 AltaLink
numbers (engine comparison for free); MARGINAL = volume under-ranked but
>60% tiles certified (rate rung finding); FAIL below that.

## RESULTS (016.2, 2026-07-10 — FIRST HARDWARE-CERTIFIED BITS, envelope PASS)

**The volume decoded BYTE-EXACT — data sha `412b9256…` = golden — from 2
of the allowed ≤3 scans, and (measured post-hoc) from scan A ALONE and
scan C ALONE.** 361,833 bytes over the 3300×2220-cell field = **55.1
b/mm² net CERTIFIED** — the first hardware-certified bits of the
project (~1.5× the 013 sim-blind c3 net of 35.7).

Setup: M281 print (016.1), 3 Canon 4800 dpi grey scans re-placed per
protocol (A original / B displaced / C displaced; filenames say `hp` —
an earlier `xerox` prefix was a naming slip, corrected same night).
Decoder: `decode_e016.py` — scans pre-decimated 2×2 box-mean to 2400 dpi
= 8 px/cell (DECLARED deviation: page_decode's full-page normalize is
~18 GB at 4800; the box mean is the same area averaging the canonical
16→8 resample applies), then fully blind
`formats.page_decode(detector="ctx", calibrate=True)`, 300-cell =
25.4 mm windows (014.1: c2 wants tight windows; `id_window_px` added to
page_decode — its 4096 px default identification crop is 43 mm at this
footing, the size 014.1 measured as veto-prone). Format identified
blind from the new `e016-v3-c2` registry row.

**Page-scale channel (full-page ctx detection BER vs gen-module GT):**

| scan | windows ok | page BER | pilot est | LDPC alone (interior syms) | volume alone |
|---|---|---|---|---|---|
| A | 110/165 | 2.63% | 2.56% | 1452/1734 | **BYTE-EXACT** |
| B | 104/165 | 2.83% | 2.95% | 1377/1734 | rank 1377/1387 — 10 short |
| C | 107/165 | 3.39% | 3.39% | 1412/1734 | **BYTE-EXACT** |

Pilot-est ≈ payload BER on every scan — the 014.1 fold-artifact check
passes at page scale. 3-scan equal-LLR-sum: **1.81%** vs best single
2.63% — the F1∘F6 composition law (combine only after ctx) replicates
on a third print/engine combination.

**LDPC r0550 (best_per_tile, incremental):** A→1465 certified, +B→1535
(+70), +C→1574 (+39); final interior symbol yield **1529/1734 = 88.2%**
vs the 1387 (80%) fountain threshold. r0550 is heavily margined at the
measured 2.6–3.4% page BER — the r0700 rung (gate ~3.5%, 013) projects
**~70 b/mm² net**; rate-ladder decision on multi-sheet minima per
doctrine (this is one sheet, one day).

**Coverage / scan-diversity accounting (tiles ≥50% observed):** A 1594,
B 1538, C 1575; union 1672 (1625/1734 interior). Incremental in fold
order: A 1594 → B **+9** → C +69; exclusive-to-one-scan A 54 / B 0 /
C 69. Word (pilot) tiles decoded: A 1672 / B 1605 / C 1631, union
1789/1820. B is strictly dominated (adds nothing A+C don't have);
re-placement diversity paid mainly via C.

**Failure geography (per-scan-alone failed-tile sets, absolute
coords):** 187/194/188 failed tiles per scan, pairwise Jaccard
0.28–0.38, **76 fail in ALL three scans** — two vertical stripes at
tile columns 1 and 33 plus scan-varying horizontal bands (rows 17,
32–40). **CORRECTED SAME SESSION (the first write-up said
"print-frozen": too strong).** The boundary-profile probe splits the
mechanism in two:
(i) **Boundary evidence desert = DECODER GEOMETRY, not print.** The
window grid tiles the IMAGE, so boundary window columns are ~40%
blank margin and mostly fail Stage A — mid-page, scan A has ZERO
observations within ~8 mm of the left/right field edges (right band
8–11 mm: n=237 cells, BER 13.5%). Tile cols 0–1/33–34 fail
DETERMINISTICALLY across re-placed scans because the tiling geometry
repeats, which is what mimicked "print-frozen". Fix is decoder-axis
and free: FIELD-AWARE window placement (origin is known absolutely
after identification — align windows inside the field). Queued.
(ii) **Field-boundary BER gradient = real channel+detector
pathology, measured:** 36.7% at the outermost cell row → 22.4 → 18.8
→ 14.7 → 10.0% (cells 4–8) → 2.1% deep interior (y-edges; x-edges
unmeasurable, see (i)). Steepest part = first ~0.3 mm (dot-scale
development edge + ctx context bias from margin-white neighbors);
~1–2 mm tail. Note for fragments: the DEVELOPMENT component exists
only at the printed field boundary (tearing happens post-development)
— torn edges inherit only the detector-side context bias.
Print-side mechanism attribution for any residual stripe = open
(loupe check still worthwhile); the fountain's 20% headroom absorbed
all of it either way.

F6 loop note: `more_scans_useful()` (inner, per-page) kept answering
True while 245 tiles stayed uncertified; `volume_scans_wanted()`
(outer) returned [] the moment the fountain closed — the outer,
volume-aware answer is the stop rule for coded volumes; the inner one
is for uncoded/characterization pages.

Characterization campaign (M281 twin of the 014.2 AltaLink ladder;
15 position-balanced 25.4 mm blind windows/scan, global vs ctx on the
same footing, `scratch/campaign_e016.py` → `campaign_e016.json`):

| scan | global med (mean) | ctx med (mean) | ctx max |
|---|---|---|---|
| A | 8.57% (9.40) | 2.13% (3.98) | 15.0% |
| B | 10.00% (10.60) | 4.86% (5.45) | 13.8% |
| C | 9.86% (10.32) | 4.90% (5.20) | 10.5% |

The ctx lever (~2–4.5×) replicates on the M281 print; the home engine
sits in the AltaLink's class at this footing (014.2 wired: 2.58/2.42/
2.20%), ~0.2–1.2 pp worse per scan. **The M281's "day-fragile c2"
history (11–14% at 2 px/dot) is now measured to be a SAMPLING story,
not an engine property** — second engine confirming 014.2's doctrine
correction. High-BER campaign windows map onto the failure-map bands
(print-frozen), not onto scan placement.

Durable tooling: `decode_e016.py` (in-experiment scorer, resumable
state), `formats.py` e016 registry row + `id_window_px` param;
analysis scripts `scratch/{campaign,report,alone_certify}_e016.py`;
`gen_confetti_session.py` (2026-07-10, commit 7ac7a05) — carves scan A
into staged NEVER-REPRINT confetti PNGs (big pieces first → 6–8 mm,
random rotation, dark backing, 2400 dpi footing, ground-truth manifest;
deterministic under `e016/confetti-session/v1`) = the fixture for the
PILOTS-DESIGN §15 session loop (segmentation → F13 place → tilemap
union → F14 rank stop). Default schedule issues ~67% of the field —
whether the fountain closes there is the session experiment; the
schedule is a CLI knob. `--backing dark|white|<grey>`: dark = the §15.2
backing-sheet protocol (trivial segmentation); white = bare scanner lid
(the much easier PHYSICAL protocol — segmentation must key on ink
density instead of paper-vs-backing). Same rng label ⇒ byte-identical
piece geometry across backings = a controlled A/B pair for the
segmentation front end. Output: scratch/confetti_session/ (dark) +
scratch/confetti_session_white/ (untracked).
Known scorer nit: a resumed `decode_e016.py` run rebuilds the report
JSON with only the newly-folded scans' entries (state is complete;
report is per-invocation).

## RESULTS (016.5, 2026-07-11 — FIRST BYTE-EXACT CONFETTI SESSION, zero print: fountain closure on the synth fixture)

**THE HEADLINE: `session_decode.py` reassembled the full 361,833-byte
volume from confetti — data sha = golden `412b9256…`, fountain closed at
scan 2 of 5** (closure fixture, 86 pieces folded: scan01 = 28 pieces
@38 mm all through the new window-tiled word path → 1,298 symbols;
scan02 = 58 pieces @12 mm, 12 word-path + 28 placed → 1,434 ≥ K=1,387).
Config at run: `--policy weighted_sum --emit-erode-cells 4`, median
piece chain (the P2 refine chain landed later the same day, see 016.6);
state build/session_state_close.pkl, log build/session_run_close.log.

The 016.4 issuance binder was only the first of FOUR binders this
session measured and fixed, in order:

1. **Issuance** (67% < 80% rank need): `carve()` gained a dense
   1-mm-stride greedy sweep (schedule token `sweep`; legacy `all` and
   its aligned raster are UNTOUCHED — the on-disk real-toner fixtures
   regenerate byte-identically). Stress-fixture default (now
   `45x6,25x14,12x40,8x60,12xsweep,8xsweep,6xsweep,5xsweep`) issues
   88.4% (its legacy default measured 65.5% — the oft-quoted 67.1% is
   the REAL-TONER fixture's number); the 6/5 mm tails sit at the F13
   placer's measured floor (016.7).
2. **Big pieces** (016.4: scan01 words 1/6-class): pieces with mask-bbox
   long side ≥26 mm now route through `formats.page_decode` — 25.4 mm
   windows tiled over the mask-cropped piece (the 014.1 c2 window
   ceiling; a whole-piece window at 40 mm+ vetoes from warp
   accumulation). Synth scan01: 6/6 pieces, 354 symbols ≈ the ENTIRE
   016.4 session (366).
3. **Merge policy** (review carve-sim, draw-faithful vs the on-disk
   manifest): under `best_per_tile` only 1,027/1,734 interior tiles have
   ANY single piece covering ≥70% of their cells (the 013 r0550
   coverage need) — geometrically unable to reach K=1,387; the union
   ceiling is 1,477. Sessions therefore default to **weighted_sum**:
   pieces are spatially disjoint (each cell scanned once), so the
   012.3/013/014.2 multi-scan sum-negative does not apply. Measured
   A/B, stress fixture: union 693 vs best_per_tile 653.
4. **The grow-out rim is union poison**: the segmenter's ~3-cell grown
   ring samples backing (reads confidently-paper on the white lid) and,
   because carved pieces are page-adjacent, lands INSIDE neighboring
   pieces' cells — corrupting exactly the boundary tiles the union
   needs. Fix: mask EROSION by 4 cells (grow 3 + 1) for placement
   scoring and LLR emission (grow-out remains the segmentation
   doctrine). Stress fixture: 693 → **900 symbols (+30%)**. Verified
   directly: full-vs-core mismatch on placed pieces drops 3–4 pp
   (e.g. 0.133→0.106); the removed ~9% of sites are ~coin-flip.

Closure became geometry-feasible on a big-sweep fixture (the review's
pre-computed schedule): `gen_confetti_synth.py --schedule
38xsweep,12xsweep,8xsweep,6xsweep,5xsweep --out
scratch/confetti_synth_close` = 98.0% issued in 124 pieces, union
ceiling 1,734/1,734, single-piece ceiling 1,603 > K. The stress fixture
(88.4%, 420 pieces incl. 178 at 5–6 mm) remains the placer-stress
vehicle: 900/1,387 final — with placement measured NOT the binder
(5 mm admissions ~45% under late-session pruning), residual deficit =
median-bit piece detection at 9–13% BER > r0550 reach, i.e. exactly
the P2 axis (016.6).

Process note: a 52-agent adversarial-review workflow over the day's
diff confirmed 6 findings, all fixed pre-closure — the best_per_tile
geometric ceiling (critical), old-pickle resume crash (spec migration
added), the closure-schedule pre-registration, the rim poison
(independently), a dpi-hardcoded id-window, and the 67.1%/65.5%
comment misattribution. Suite green at 327 throughout.

## RESULTS (016.6, 2026-07-11 — P2 real-toner detection chain: the 13–14% "binder" decomposed and beaten; refine chain wired)

**The 016.4 real-toner binder ("placed pieces detect at 13–14% BER,
beyond r0550") is a SUM of separable, now-measured terms — and two of
its recorded mechanisms are corrected:**

- **Ring (+3–4 pp, ~9% of masked sites)**: grow-out cells sampling
  backing; coin-flip wrong. Core-mask (erode 4) BER on the same placed
  pieces: 0.128 median vs full-mask 0.181 (N=99). The "13–14%" was
  ring-diluted; core detection was near r0550's edge all along.
- **Angle estimation (+0 to +20 pp, piece-dependent)**: the P3.1
  rotation-curve probe (016.7) measured the 016.4 "+4 pp INTRINSIC
  rotation loss" to be `lattice_angle` estimation error — the
  counter-rotation RESAMPLE itself is FREE at genie angle (mismatch
  0.131 flat 0°–45°, ΔBER ≤0.15 pp). Dose–response: <0.15° error →
  +0.000 mismatch; ≥0.5° → +0.203. The estimator delivers 0.4–0.5°
  median and even at 0° introduces ~0.4° spurious correction —
  016.4's "+4 pp intrinsic" was survivorship over lucky-angle
  admissions. RETRACTION of the mechanism, not the number.
- **Calibration (−0.3 to −1 pp)**: per-piece 2-class Gaussian recal on
  placed pilot labels (F10 at piece scale).

**Detector A/B on scratch/confetti_session_white (probes/
p2_detector_ab{,2}.py, N=212–219 sub-26 mm pieces, gate 0.20/0.20/
gap≥0.08, 0 admitted-wrong anywhere):**

| arm | admissions | core BER (placed) |
|---|---|---|
| A 016.4 baseline | 99/212 (47%) | 0.128 |
| E = A + CORE-mask placement | **146/212 (69%)** | 0.134 |
| F = rot-free + supervised refine + recal | 115/215 | **0.109** |

- E: removing the ring from the placer's score/support lifts admissions
  +47% at zero false placements — the single biggest admission lever.
  (Pre-placement angle search on the blind confidence objective bought
  ~nothing: round-1 arm C, 93 admissions — the objective is too flat.)
- F: with a gate-passed placement, the piece's ~600 seed-predicted
  pilot sites become a supervised reference (blind-legal, pilot layer
  only); searching (angle ±0.6° × CONTINUOUS sub-cell phase) on a TRAIN
  half of sites moves the angle 0.15° median and takes the HELD-OUT
  half 0.091 → 0.073; re-sample + per-piece recal lands core BER 0.109.
  Machinery cost per angle candidate = one coordinate transform (no
  image rotation) — rotation-free sampling's real payoff.

**Production wiring (decoder-axis only): paperholo/segment.py gains
`rotate_transform` (exact ndimage.rotate inverse), `phase_scan_glass`,
`sample_cells_at` (order-3 area sampling of ORIGINAL pixels at a
continuous (angle, phase) lattice model — no image resample anywhere),
`refine_on_sites`, `recal_llrs_from_labels`; `Piece` carries its
unrotated glass crop; paperholo/place.py gains `fragment_pilot_sites`.
`session_decode.py`: placement mask = core, `--piece-chain refine`
default (median = 016.4 baseline kept for A/B), every refine step
re-validates through the placer gate with fallback to the initial
observation.** **MEASURED, full 5-scan white real-toner session:
509 symbols vs the 75-symbol 016.4 baseline = 6.8×** (scan ladder
276 → 403 → 430 → 451 → 509; placements 6 tiled + ~19 word-path +
146 placed of which 113 refined; scan05: 84/115 pieces placed = 73%
admission on 8 mm real toner). Closure is NOT the target on this
fixture and cannot happen by construction — it is the FROZEN 016.4
baseline fixture at 67.1% issuance (byte-identical regeneration
preserved deliberately); the closure demonstration lives on the synth
closure fixture (016.5). The real-toner closure attempt = P4, the
physical scissors run.

**Post-probe hardening (tests/test_segment_refine.py, 4 tests — writing
them caught three real defects in the wired chain):** (1) candidate
angle frames each carried their OWN bbox center, so the locked phase
drifted laterally across the search (sub-cell on 8–12 mm pieces —
gains still real but the search fought a moving frame; ran into its
boundary on a 12 mm test piece) — fixed by anchoring every candidate
to the reference angle's frame (`rotate_transform(out_shape_ref=…)`);
(2) `sample_cells_at` mixed spline_filter's mirror boundary with a
constant-mode read — outer ~4 px corrupted (inside the eroded ring,
which is why measurements were unaffected) — modes unified;
(3) the refine objective was hard-bit mismatch, which SATURATES to a
zero plateau on clean channels (measured: a ±0.5° band reads every
site correctly on the synth-channel test piece) — production ships the
mean SIGNED-MARGIN objective (peaks with sites dead-center on cells,
informative at any BER; the probe's measured numbers used the hard
objective and are so labeled; held-out reporting stays hard-mismatch
for comparability). Also found: pytest in a WORKTREE resolves
`paperholo` via the shared env's editable install to the MAIN
checkout — worktree suite runs need `PYTHONPATH=src` (the session/
probe drivers were unaffected: they sys.path-insert their own tree).

Not built (ranked follow-up): multi-angle PLACEMENT attempts for the
~30% still-refused pieces (offer the placer bits at estimate ±0.2/0.4°,
gate decides; ~1 s per extra hypothesis) — the placement-fail
population never reaches supervised refinement by construction.

## RESULTS (016.7, 2026-07-11 — P3 measurement pack: rotation curve, pruned grain, page axis; all zero print, 0 false placements in 355 gated calls)

**P3.1 rotation-loss curve (probes/p3_rotation_curve.py, N=12 paired
12 mm real-toner pieces × {0,5,15,30,45}° × {production, genie-angle}):**
genie leg FLAT — mismatch 0.131/0.130/0.132/0.131/0.137, BER
12.45/12.42/12.44/12.60/12.46% — the rotate→counter-rotate resample
costs ≤0.6 pp mismatch at 45° and ≤0.15 pp BER. Production leg is
angle-ESTIMATION bound (details + dose–response in 016.6). Gate
integrity under rotation stress: 0 wrong placements in 119 calls.
Latent bug found: `gen_confetti_session.field_bbox`'s first..last rule
is dragged ~17 mm past the field by a dark scanner-edge strip on scan A
(bookkeeping-only: absolute addressing is pilot-anchored; the real-scan
fixtures' mm bookkeeping inherits it; fix before any fixture regen).

**P3.2 session-state grain (probes/p3_grain_pruned.py, N=10/cell,
sizes {4,5,6,8,10} mm × pending fractions {1.0,0.5,0.2,0.08},
unrotated, second engine print vs 014.3):** 6 mm+ = 10/10 at EVERY
pruning level; 5 mm = 7/10 (9/10 at f=0.08 — pruning deletes
near-gate rivals); 4 mm = 0/10 honest refusals (the placer's best
candidate WAS the true position in 32/36 refused trials — rival
ambiguity is support-starved, replicating 014.5's 4 mm verdict).
**0 false placements in 196 gated calls** (GT agreement 0.800–0.921 on
all 150 admissions). The floor move vs 014.3 (word-grain 10 mm →
solid 6 mm) is F13 correlation placement itself, present at f=1.0;
pruning buys gate margin, not a rung. Timing flat vs pending size (the
FFT correlates the full page regardless).

**P3.3 two-page volume / placer page axis (probes/
p3_twopage_volume.py, VolumeSpec n_pages=2 native, N=10/page at
8+12 mm):** correct-page 33/33 admitted (100%), correct-position
33/33 (≤1 cell); **wrong-page rejection 20/20 + bonus 20/20** — every
wrong-page best-mismatch sits at the 014.4 decoy floor (0.307–0.342),
none clears even the bare 0.20 gate. Cost linear: 2.455 s (2 pages) vs
1.244 s (1 page) per call ≈ 0.73 s/page-hypothesis extrapolation
holds. The frozen session gate needs NO page-aware retuning.

Artifacts: probes/p2_detector_ab{,2}.py, probes/p3_*.py +
build/p2_detector_ab{,2}.json, build/p3_*.json; session logs/states
build/session_run_{bpt,wsum,wsE,close,white_p2}.log + *.pkl.

## P4 REAL-SCISSORS PROTOCOL (registered 2026-07-11; run = future 016.8)

Subject: ONE printed e016-class sheet (a fresh `lpr -o raw` M281 print
of build/e016.ps is preferred over sacrificing the measured 016.2
sheet — same golden sha; log the print). Cut/scan/decode loop:

1. **Cut big-first, in batches** (the closure fixture's measured shape:
   ~30–40 mm pieces carrying most of the area first, then 10–15 mm,
   then small): scissors are fine, straight cuts not required; keep
   each batch's pieces together, NEVER return a scanned piece to the
   glass (every region exactly once — the union assumes it).
2. **Scan**: Canon 4800 dpi GREY, white lid, pieces face-down spread
   with ≥5 mm air between pieces (the segmenter merges closer pieces),
   any rotation. Re-placing and re-scanning the SAME batch before
   removing it is allowed and useful (F6 at piece level — the fixtures
   forbade it, hardware need not). sha256 every tiff into the run
   table.
3. **Decode after each batch**: `env/bin/python session_decode.py
   <batch.tiff> --state build/session_state_p4.pkl` (defaults are the
   measured config: weighted_sum, erode 4, refine chain; --dpi 4800 if
   feeding raw 4800 — the driver derives footing; or pre-decimate to
   2400 like decode_e016). The driver prints the fountain deficit after
   every image — STOP CUTTING when `VOLUME DECODED … == GOLDEN`
   appears; the remainder of the sheet stays uncut (that margin IS the
   result).
4. Envelope (pre-registered): closure before the sheet is fully
   consumed = PASS (the synth closure used 86 pieces / 93.5% of field;
   real toner has the measured ~0.109 core BER + kerf loss — expect
   more pieces needed; any closure = the project's first
   physical-confetti recovery). 0 wrong certifications (F9/CRC is the
   backstop). If closure stalls with the sheet exhausted: the state
   pkl + logs are the diagnostic artifact; do NOT re-scan removed
   pieces into a fresh state.

## RESULTS (016.4, 2026-07-10 — fragment-session rehearsals, zero print: fixtures + first session runs + measured mitigation ladder)

The §15 loop (segment → per-piece align/route → F13 place → tilemap
union → LDPC → fountain rank), driven by `session_decode.py` (resumable,
any-order glass images), was exercised end to end on fixtures carved
from this volume's scan A. Measured arc, in order:

1. **v1 scan fixture** (decimate→rotate order-1 at 8 px/cell): session
   52/1387 symbols — piece detection crushed.
2. **SYNTH fixture** (`gen_confetti_synth.py`: pieces rendered from the
   composed page by ONE coordinate sampling — rotation is free; optical
   channel blur+noise CALIBRATED to the ctx band 2–5%, dev morphology
   deliberately excluded, sim-c2 being receiver-dead): **366/1387
   symbols, ~80% of 12 mm pieces gate-placed** — the
   session-DEVELOPMENT vehicle. Along the way `segment.piece_cell_bits`
   replaced lock_grid for sub-grain pieces (lock_grid MEASURED to
   mislock on backing-embedded pieces: same piece mismatch 0.455 vs
   0.077 via the phase search).
3. **v2 scan fixture** (rotate order-3 at the 4800 source, THEN
   decimate) + a 4800-footing variant: piece mismatch 0.144 → 0.134 /
   0.141 — i.e. **rotation loss on real halftone is INTRINSIC (~+4 pp
   BER over the unrotated 9–10% channel), not an interpolation or
   footing artifact**; --out-dpi 4800 removed as measured-useless.
4. **ctx at piece scale: MEASURED HARMFUL** (synth 80→68% gated, scan
   3/42→0/42 — the ICM stage misfires on mask-filled small grids);
   reverted to masked-median bits + spread LLRs. Proper per-piece
   detection is the open lever.
5. **Gap gate** (best < 0.20 AND rival−best ≥ 0.08 — safe against the
   014.4 measured decoy floor ≥ 0.257, ≈0.33 at this BER): scan-fixture
   admissions ×4 with **0 false placements** (GT agreement 0.79–0.83 on
   every admitted piece); full session placements 6 → 99 pieces,
   symbols 52 → **75**.

**The measured binder after all of it:** placed real-toner pieces
detect at ~13–14% BER (median threshold) — beyond LDPC r0550's reach
(501 tiles attempted-and-failed). Placement is solved; per-piece
detection quality is the whole remaining game on real scans. Neither
fixture can close the fountain yet regardless (default schedule issues
67.1% of the field < the 80% rank need) — issuance ≥85% is a
prerequisite for any closure demonstration. Visual A/B (same piece,
v1|v2|synth): scratch/fixture_ab_visual.png. Fixtures:
scratch/confetti_synth (primary) + confetti_session{,_white}
(hard-mode real-toner). Next levers ranked: piece-labeled detector
(post-placement pilot cells = ~140 free labels per piece, F10 at piece
scale); rotation-free detection (sample the rotated lattice directly
from the unrotated piece — skip the counter-rotation resample);
window-tiled word path for >26 mm pieces (scan01 1/6); erasure-rung
routing (014.5 decoder built, unwired in the driver); issuance ≥85%.

## RESULTS (016.3, 2026-07-10 — field-aligned windows adopted; mirror-pad rejected)

Same-session follow-up on the 016.2 boundary finding. Two receiver
levers built into `formats.page_decode` (both OPT-IN:
`align_to_field`, `mirror_pad_cells`; suite unaffected, 9/9 targeted
tests green) and measured on scan A vs the 016.2 baseline:

**E1 — field-aligned window grid** (`_find_field_bbox` darkness
profile → windows tile the FIELD, not the image): **adopted.**
139/140 windows ok (was 110/165), page BER 2.05% (was 2.63%),
single-scan interior symbols **1681/1734 = 97.0%** (was 1452 =
83.7%), zero low-coverage tiles (was 167), the x-edge evidence
desert recovered at 2.64% BER. **Boundary-profile correction: with
well-locked windows the "white-adjacency" gradient collapses 36.7 →
13.4% (cell 0), 22.4 → 7.3 (cell 1), interior by cell ~3 — most of
the 016.2 boundary pathology was REGISTRATION quality of
margin-heavy windows, not channel.** True development-edge residual
= the outermost ~1–3 cell rows, small (~0.2% of payload cells).

**E2 — post-scan mirror padding** (reflect 16 cells of field content
into the margins so edge cells get in-distribution ctx context; no
printed guard): **MEASURED NEGATIVE, rejected.** Boundary cells
WORSE than E1 (cell 0: 19.8% vs 13.4; cell 1: 11.6 vs 7.3), page BER
2.21% vs 2.05, symbols 1667 vs 1681. Mechanism hypothesis (unproven):
the mirrored strip carries phase-reversed lattice structure that
pollutes grid/slip tracking near the edge — registration cost
exceeds the context benefit. Instructive negative on record; the
`mirror_pad_cells` hook stays for future probes.

**3-scan aligned union: 1812/1820 tiles certified (7 failed + 1
degenerate), interior 1727/1734 = 99.6%, 3.67 Mbit certified.**
Incremental: A 1766 → +B 36 → +C 10; `more_scans_useful` correctly
reads diminishing returns (weak-drop 0.008 on scan C). Volume
byte-exact throughout (single-scan margin now 294 symbols).

Doctrine: `align_to_field` stays opt-in until an e012/c3 regression
check; then it is the candidate default for page_decode. The 016.2
"queued" decoder follow-up is hereby DONE; border-aware ctx demoted
(residual is 1–3 cells deep ≈ 0.2% of cells); printed guard band
dead (E2 killed the scan-side version; the print-side version's
target shrank to the same 0.2%).

## Run table

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 016.0 | 2026-07-09 | gen_e016.py + 3 preflight gates green (suite 245) | build/e016.ps | 796f26094fef1b09220fcc184e86d5930bea11613649981ce249a19f57eb5053 |
| 016.0 | 2026-07-09 | data payload frozen | 361833 bytes | 412b9256829ece06243f16ab0456e4a817b1459d64625f28dd09eae26059bb90 |
| 016.1 | 2026-07-09 | print_plane.sh attempt FAILED SILENT (non-tty read + set -e + caller's piped exit status — script hardened, lesson logged); PRINT executed by user: `lpr -o raw experiments/016-arch3-c2-volume/build/e016.ps` (CUPS raw; 001.2/001.3 equivalence on record; CRC = fidelity referee) | paper sheet | scan pending |
| 016.2 | 2026-07-09/10 | scan A, Canon 4800 grey | scratch/e016c2hp-canon4800gray.tiff | 593742f68ee81f4004c551c0128990ab278f41030e6ad26f10b19e8656ad96e4 |
| 016.2 | 2026-07-09/10 | scan B (displaced) | scratch/e016c2hp-canon4800gray-displaced-1.tiff | 7dfc3a5b9268d29310aa64a2a28de7296badbc78948ee1b3b47c1acd3a6a9659 |
| 016.2 | 2026-07-10 | scan C (displaced) | scratch/e016c2hp-canon4800gray-displaced-2.tiff | aa1633252e86c91bb97ab650f581dfc77df5725935721dec59a4b7070110afb6 |
| 016.2 | 2026-07-10 | blind decode A+B → VOLUME BYTE-EXACT (also A alone, C alone); RESULTS above | build/e016_scan_report.json + build/e016_state.pkl | data sha = golden 412b9256… |
| 016.3 | 2026-07-10 | field-aligned windows (E1, adopted: 97.0% single-scan symbols) vs mirror-pad (E2, measured negative); 3-scan union 1727/1734 symbols | build/e016_report_E1{,_abc}.json, build/e016_report_E2.json, build/e016_state_E{1,2}.pkl | data sha = golden 412b9256… |
| 016.5 | 2026-07-11 | stress-fixture session A/B: best_per_tile 653 / weighted_sum 693 / +emit-erode-4 900 symbols (no closure, by ceiling) | build/session_run_{bpt,wsum,wsE}.log + state pkls | fixture scratch/confetti_synth (88.4% issued) |
| 016.5 | 2026-07-11 | **FIRST BYTE-EXACT CONFETTI SESSION: closure fixture, fountain closed at scan 2/5 (1,434 ≥ K=1,387)** | build/session_run_close.log + session_state_close.pkl | data sha = golden 412b9256… |
| 016.6 | 2026-07-11 | detector A/B rounds 1+2 (ring/angle/recal decomposition; E +47% admissions, F core BER 0.109) | build/p2_detector_ab{,2}.json | fixture scratch/confetti_session_white |
| 016.6 | 2026-07-11 | refine chain wired (segment/place/session_decode); full white session with P2 chain | build/session_run_white_p2.log + session_state_white_p2.pkl | vs 016.4 baseline 75 symbols |
| 016.7 | 2026-07-11 | P3 pack: rotation curve / pruned grain / two-page axis (0 false placements in 355 gated calls) | build/p3_{rotation_curve,grain_pruned,twopage_volume}.json | zero print |
