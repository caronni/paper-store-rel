# Experiment 014 — ARCH-2: the c2 archive-style pilot sheet (layout_version 3)

**2026-07-08.** kcell-c2 companion to e012/ARCH-1, built the same day at
user request for the office print run. Same v3 format machinery (p60b6
pilots, 18-bit flat counter in BCH(100,23) t=13 words, site/value labels
unchanged, no overt furniture), at cell = 2×2 dots (300 cpi):

- Page 3300×2220 cells (multiples of P=60) = 6600×4440 dots at (260,208) on
  A4 → margins 11.0/8.8 mm. 55×37 = **2035 pilot tiles** (counter fits: 128
  pages max at this geometry). Payload 7,122,500 random bits (label
  `e014/payload`, frozen dtype form). Tooling delta: compose.ComposeSpec
  now admits kcell-c2 (one validation gate — every downstream path was
  already cell_dots-parameterized); zero changes to pilots/bch/acquire.
- **build/e014.ps sha256
  `eb2f8cbfb1c9f208472c52eeac30230bcfb9cea7481b722dfba9b93505fde153`**,
  7.38 MB; golden-anchored in tests/test_e014.py (6 gates: determinism,
  golden sha, manifest geometry, payload bijection, gs pixel-exact render
  — 0 differing dots — with pilot-word spot-check IN the rendered dots,
  and a GT-scored sim smoke).

**DECODE STATUS — deliberately deferred (user decision, on the record):**
this sheet is ENCODE-side gated only. The blind receiver cannot yet acquire
c2-class pages: at 11–14% hard BER the (100,23) t=13 words fail (~mean 12
errors > t), and the designed c2 machinery — ctx-detected pilot bits,
p60b4 duplicated words (PILOTS-DESIGN §6.2) — is spec'd but unbuilt.
The sim smoke is therefore GENIE-FOOTING GT-scored channel sanity, not a
round-trip: geometry=False, aligned block-mean cells, median threshold →
**BER 14.9%, null 0.501** — squarely the known c2 sim regime (sim ~15% vs
hw 11.1%; the 2-dot-white closure gap makes the sim conservative here).
The M0 sim-before-toner gate is thus explicitly REDUCED IN SCOPE for this
sheet; retraction rule: if the eventual c2 receiver cannot acquire clean
scans of this sheet, that is a receiver finding, not a format retraction,
UNLESS the pilot cells themselves measure outside the c2 channel envelope
(pilot-cell BER > 20% on a clean scan ⇒ revisit c2 pilot rendering).

Expected channel facts to check against the scans (measured history): c2
hard 11–14% both engines; 2-dot whites are the day/density canary; office
AltaLink JPEG scans useless (<5-dot erasure) — home flatbed 1200 grey only;
ctx detector gains are field/engine-dependent (do not budget from M281).

## Print protocol

Office AltaLink raw 9100 via the bundle script (scratch/office-2026-07-08),
K-only ⇒ MIC-free; alternatively home M281 `scripts/print_plane.sh
experiments/014-c2-print/build/e014.ps`. Scans: home flatbed 1200 dpi grey,
enhancements off, 3–4 re-placed scans; label sheets with engine + order.

## RESULTS (014.1, 2026-07-09 — FIRST BLIND C2 ACQUISITION ON REAL TONER)

The deferral is **lifted by measurement**, not by building the M-P6
machinery: the printed e014 format needed none of it. Sheet A (office
AltaLink print) scanned on the Canon flatbed at **4800 dpi grey = 8 px/dot
= 16 px/cell** (scans/xerox-e014-A-canon-4800gray.tiff, sha
5a8f895c…) and decoded FULLY BLIND through the acquire-v2 receiver
(scannorm → formats registry → cell_dots=2 acquire; no hints beyond
trusted dpi).

**18-window sweep (25 & 30 mm, 3×3 page positions): 17/18 decoded blind.**
Payload BER **min 6.01% / median 8.05% / max 20.26%**, nulls 0.497–0.502,
geometry (y-neighbor) confirmed. Per-window pilot-cell BER ≈ payload-cell
BER on EVERY window (e.g. 7.93/8.03, 5.67/6.01, 8.62/8.72) — uniform
detection, so this is a genuine ~8% channel, NOT a fold artifact (a broken
fold gives clean pilots + ~50% payload; here they track). 25 mm windows:
**9/9 decoded, 6.0–10.2%**. The retraction-rule escape hatch (pilot BER
> 20% ⇒ revisit c2 rendering) is NOT triggered: pilot BER ≈ 6–10%.

**This CONFIRMS the PILOTS-DESIGN §13.1 prediction on hardware: plain
(100,23) t=13 words decode a real c2 channel with NO duplication, because
8 px/dot oversampling delivers the "good channel" — ~8% vs the 2 px/dot
11–14%** (oversampling roughly halves c2 BER, mirroring 012.3's c3 finding).
The design's expensive fallback (p60b4 M-P6 duplication) is DEMONSTRATED
UNNECESSARY at Canon-4800 sampling.

Two hardware findings:
- **Window size matters more at c2 than c3.** 25 mm windows 9/9; 30 mm
  8/9 with more variance (a 20.26% outlier + one Stage-A FAIL). A 40 mm
  center window (decode_e014.py) hit the post-fold gate at 29% BER while
  the 25 mm center window at the SAME spot read 7.96% — warp accumulation:
  a 40 mm window is ~470 c2 cells (vs 315 c3 at equal mm; c2 packs 1.5×
  more cells/mm), exceeding the anchor interpolation. c2 wants tighter
  windows or denser warp tracking — a decoder-axis follow-up, not a format
  issue.
- **The post-fold word gate was made BER-aware before this decode**
  (acquire.py, same-day: bar = ½·binomial-predicted word-success from the
  pre-fold pilot match, provably 0.5·n_att at c3 so c3 stays byte-identical;
  mis-fold protection preserved because Stage-B accepts only at
  pooled_match ≥ 0.85). HONEST FOOTNOTE (verified, not assumed): on THIS
  sweep it was NOT empirically decisive — every OK window had n_dec/n_att
  ≥ 0.60 > 0.5, so the old fixed bar would have passed the same 17 windows,
  and the one vetoed 40 mm window (29% BER, n_dec≈0) is vetoed by BOTH.
  The change is the review-mandated correct fix (it prevents false-vetoes
  on larger windows with spatial BER variance, where Stage-A locks a clean
  sub-region while distant tiles fail) — defensively right, not the reason
  this sweep decoded.

Raw ~8% is above the LDPC ladder's c3 comfort (2–4%); the documented next
levers are the 16-context detector (c2's designed L1 gain, not budgeted
from M281) and lower inner rate — but the RECEIVER milestone (blind
lock + absolute address + payload extract on c2) is DONE.

## RESULTS (014.2, 2026-07-09 — ctx detector + PAVA calibration + multi-scan, WIRED)

Three Canon 4800 grey scans of sheet A (A original / B displaced / C
displaced + heavy book), 15×25 mm blind windows each, everything through
the acquire-v2 blind pipeline. The sheet had been FOLDED (pocket): two
creases; the horizontal one measured at abs rows ~1672–1675 (~2 mm off
page center).

**Error attribution (by-hand, 25 mm center window):** self-sync exonerated
— genie-best global offset gains only 0.04 pp over the blind lock. Taxonomy
of the 6,899 errant cells: 53% white-closure FAs (whites w/ ≥5 ink
neighbours read dark; fully-surrounded whites close at 98.7%, open whites
0.0% FA), 38% ink-erosion misses (isolated ink pales), ~6% crease band,
~6% borderline. Errors carry their own warning: median |LLR| 1.58 vs 4.29
correct.

**The ladder, measured (window BER, all blind):**

| lever | BER | note |
|---|---|---|
| baseline (A, global det) | 7.89% | |
| + flattening (C, global) | 7.10% | book helps; crease shoulders 11→7% |
| + ctx detector (C alone) | 1.93% | **the lever: ~3.5× on every scan** |
| + 3-scan equal LLR sum (ctx) | **1.37%** | off-crease **1.17%** |
| union coverage, erasure split | 2.6% erased → **0.98% silent** off-crease | LDPC currency |

**Doctrine corrections + new composition law:**
- **ctx gains are SAMPLING-dependent, not engine-dependent**: 007.6's
  "AltaLink encode-c2 ctx rescue fails (terminal closures)" was measured at
  2 px/dot; at 16 px/cell the same engine's print rescues 7.9→2.6%. The
  residual signal exists — it just needs resolving.
- **F1∘F6 compose, order matters**: with the global detector, multi-scan
  combining ≈ best-single (012.3/013 negatives replicate a third time);
  AFTER ctx removes the correlated context bias, equal-sum BEATS
  best-single (A+B+C 1.37% vs 1.71%). Soft sum > 3-way hard majority
  (1.37 vs 1.42). Per-tile best-scan underperforms at c2 (7.50 vs 7.24)
  — 1–2 word decodes/tile is too noisy a quality signal.
- Crease band irreducible at ~20–24% under everything (cracked toner);
  its stripe of tiles is the fountain's job. Sheet lies flatter when
  weighted: scan C best on every metric (pilot BER 0.062 vs A 0.074).

**WIRED INTO THE RECEIVER (suite 243):** `acquire_and_decode(detector=
"ctx", calibrate=True)` — ctx stage runs once on the settled grid (slip/
anchor tracking stays global); PAVA isotonic calibration fits score→P on
the pilot cells of DECODED tiles (the on-page labeled set, blind-legal)
and recalibrates the payload LLRs. Wired-path replication: A 2.58 / B 2.42
/ C 2.20%, combined equal-sum 1.97% (crease 20.7 / rest 1.78) on 1.35M
union cells. Calibration reliability within 0.03–0.06 per confidence bin —
residual OVER-confidence from label survivorship (labels come from decoded
tiles = better regions; improvement path: failed-tile sites still have
known expected bits). Discriminating tests (test_ctx_calibration.py):
i.i.d. flips = exact ctx/global parity; context-structured CONTINUUM
damage 6.84→3.67%; two instructive negatives kept on record — binary
flips are undetectable by construction, and within-class bimodal damage
defeats the pinned-2-GMM (it models SHIFTS; terminal closures are exactly
the unrecoverable subset).

**F6 adaptive scan loop (tilemap.more_scans_useful):** asks for another
scan while tiles are uncertified AND the last scan gained coverage or
mean-|LLR| confidence; stops on certification or diminishing returns.
Live on the real scans: ask(1 scan) → ask(+158k cells) → ask(+18k) →
**STOP on an exact duplicate of C** (v1 sum-based confidence metric was
duplicate-gameable — measured, fixed to per-cell mean before commit).

Net verdict: c2 = 300 cpi at 1.2–2% BER through the wired blind path puts
the format in LDPC-certifiable range (r0700 gate ~3.5%) — the projected
net density path (~95 b/mm²) is ~2× the validated c3 record. Next: ARCH-3
coded c2 volume print; per-context PAVA + failed-tile labels; crease-aware
tile handling.

## 014.4 — PRE-REGISTERED probe: sub-grain failure attribution (zero print, DESIGNED 2026-07-09, not yet run)

**Question.** 014.3 measured the c2 confetti grain (10 mm 5/5, 8 mm 1/5,
6 mm 0/5) but did not attribute the sub-grain failures: (a) **word
incompleteness** (no complete (100,23) word readable in the window — the
fixable case, by F13 correlation placement) vs (b) **geometry** (pitch/
rotation estimation too noisy on ~35 lattice periods — the case correlation
cannot rescue either). This probe gates the PILOTS-DESIGN §15 / F13 build:
run it BEFORE writing any correlation placer.

**Method (same data, no new scans).** Scan C (sha cb9569e7…), the 014.3
window positions at 6/8/10 mm, 5 each, off-crease. Three arms per window:
1. *Blind baseline* = the 014.3 result (0/5, 1/5, 5/5).
2. *Genie-geometry*: warp/pitch/rotation lifted from the enclosing
   full-page lock, window cells resampled on that geometry, then the
   standard word decode + in-window pilot-cell BER.
3. *Oracle-position correlation margin*: at genie geometry, score the
   window's pilot cells against predicted values at the TRUE offset and at
   ≥1000 decoy offsets (site-phase-compatible, drawn page-wide); record the
   mismatch-fraction separation.

**Pre-registered decision rules.**
- Genie-geometry recovers word decode at 6–8 mm (≥4/5) ⇒ failures were
  GEOMETRIC ⇒ F13 needs a geometry assist (piece-local lattice hardening /
  neighbor-piece priors) before correlation is even reachable; the
  pilot-bit floor is NOT the binding constraint at 6 mm.
- Words still fail under genie geometry BUT the oracle margin separates
  (pre-set gate: true-offset mismatch < 0.15 AND every decoy > 0.35) ⇒
  word incompleteness ⇒ §15 correlation placement is viable at that size ⇒
  build F13 as specced.
- Neither ⇒ the size is below the physical floor for c2; move §14's
  "nothing" boundary up accordingly and let RaptorQ absorb.

Decoder-axis only — no format implications any way it lands. Deliverable:
5×3 arm table + margin histograms, logged here as 014.4 RESULTS.

## RESULTS (014.4, 2026-07-10 — VERDICT: WORD INCOMPLETENESS; F13 viable; gate constant was miscalibrated)

Ran as pre-registered (probe_0144.py; declared deviations: positions =
deterministic scan fractions since 014.3's were inline-only; genie geometry
from an ENCLOSING 25 mm lock, not a full-page lock — 014.1 showed 40 mm c2
windows fail on warp accumulation, so the 25 mm lock IS the best available
geometry). 5 off-crease positions × {6,8,10} mm on scan C, ~1.9k decoy
offsets per window (≥ the pre-registered 1000).

| size | blind (ctx) | full tile visible | genie word decode | true mism. | decoy min/med |
|---|---|---|---|---|---|
| 6 mm (71 cells, 135–139 sites) | 0/5 | 0/5 | 0/5 | .043–.086 | .274–.302 / .43–.45 |
| 8 mm (94 cells, 240–251 sites) | 2/5 | 2/5 | 2/5 | .045–.075 | .257–.319 / .42–.44 |
| 10 mm (118 cells, 378–390 sites) | 5/5 (BER 0.27–0.98%) | 5/5 | 5/5 | .044–.070 | .307–.342 / .43–.45 |

**Finding 1 — attribution answered: WORD INCOMPLETENESS, geometry
exonerated.** blind = full-tile-visible = genie at every one of 15 windows.
Genie geometry adds nothing: whenever a complete pilot tile is in the
window, even the blind path decodes it (8 mm 2/5 matches the geometric
placement prediction (94−59)²/60² ≈ 34%); when none is, perfect geometry
cannot help (n_att = 0 — there is no word to decode). 10 mm = 5/5 despite
118 < 119 guarantee cells (per-axis odds 98.3%). The 014.3 grain ladder is
pure pilot-tile placement geometry.

**Finding 2 — oracle margins separate at every window, but the
pre-registered decoy bar (>0.35) FAILED everywhere — including the 10 mm
controls that self-address by word decode. That internal contradiction
(a window that provably carries its address fails the "placeable" gate)
means the gate constant is broken, not the data.** Mechanism VERIFIED, not
assumed (probe_0144_dmin.py): pilot values per tile = codeword(counter) ⊕
a tile-INDEPENDENT keystream, so decoy-vs-true disagreement at tile-aligned
shifts is exactly the Hamming distance between two codewords of the
(100,23) d≥27 code — measured pairwise spectrum min 32/100, p5 36, median
44 (adjacent-tile shifts 36–48); partial-tile subsampling of those
disagreement sets yields the observed 0.257–0.342 decoy floor
(support-stratified post-hoc, probe_0144_posthoc.py: the min-decoys have
FULL support, 4.7–7.7σ below a fair coin — NOT an edge-clip artifact; that
hypothesis was tested and refuted). The floor is structural: **the window
code's distance spectrum is the fragment-placement margin** — v3's d≥27
thrift cut doubles as the confetti-placement guarantee.

**2026-07-29 CORRECTION (exhaustive, both production encoders): the true
counter-subcode minimum is d = 27 EXACTLY, and "min 32/100" was a sampling
artifact of this probe.** Exhaustive Gray-walk over all 262,143 nonzero
counter XORs through paperholo v3 (pack_counter→CODE_V3) and holo v1
(format.pilots.encode_word — bit-identical codewords): low spectrum
**27:3, 28:8**, 31:119, 32:247; argmin XORs 57/114/228 (0x39 shift
family); direct no-algebra checks d(word(0),word(57)) =
d(word(100),word(93)) = 27. The probe missed them because it scanned
shifts from ONE reference tile (20,15) plus 400 random pairs, and only
0.50% of same-page pairs (2,135/427,350 on e012 p0) sit at d≤28 (~87%
miss probability at n=400). Reachability is physical, not abstract:
min-over-base-counters at this experiment's own shift list gives
**(1,0) = counter+55 → d = 27** (one tile ROW down), likewise (2,0) and
same-row +7 on other geometries. The measured 0.257–0.342 decoy band
brackets the d=27 prediction 0.27·(1−2p)+p ≈ 0.267–0.293 at working
BERs — the floor was already live in the data. Gate arithmetic must use
27 (PILOTS-DESIGN §'s "guarantee d≥27" was correct all along); every
"min 32/100 — code algebra" citation (LAYERS F13, 018 log) is hereby
retagged "sample statistic, floor is 27". Rival-bar margin above the
floor is 0.07, not 0.12.

**Verdict (overriding the rule-as-written at 6 mm, justification = the
10 mm control contradiction + measured mechanism):** decision rule B —
word incompleteness, correlation placement VIABLE. Every window separates
true (≤0.086 = channel BER) from nearest decoy (≥0.257) by ≥0.20 absolute
(≥ ~4.7σ at 135 sites). **F13 build is GREEN** with the gate re-formed
floor-aware: accept iff true < 0.15 AND all comparable-support decoys
> 0.20 (POST-HOC constant — validate on fresh windows, sim + scan B,
inside the F13 build before trusting).

Caveats on record: (i) piece-local lattice lock at 6 mm is UNMEASURED —
all arm-2/3 bits inherited enclosing-lock geometry; a real isolated 6 mm
confetti must lock pitch/rotation on ~71 cells alone (first sim item of
the F13 build; genie==blind at 8 mm says the lock is not the binder there);
(ii) single sheet, single engine, off-crease, K/c2 only; (iii) the
2026-07-09 doc-pass budget numbers ("~35 sites per 6 mm piece") were a 4×
cell-pitch slip (used 2 dots/cell at 300 cpi twice) — measured counts are
135–139 sites/6 mm, 240–251/8 mm, 378–390/10 mm; the pilot-bit floor
lands at ≈3 mm (35-site class, ~3σ vs the d-floor — ESTIMATE), corrected
in PILOTS-DESIGN §15 / DESIGN §5.3 / LAYERS F13 same-day.

## RESULTS (014.5, 2026-07-10 — erasure rung + F13 placer BUILT and MEASURED on real bits)

Probe: probe_0145.py (zero print; scan C locks at the 014.4 positions,
scan B for fresh-window validation). Code shipped same-day:
bch.decode_erasures (binary two-trial fill, acceptance 2e_out+f ≤ 2t ⇒
within-budget uniqueness), pilots.decode_word(erasures=...),
paperholo.place (FFT matched-filter fragment placer over the
seed-predicted pilot field, support-aware z, §15.4 gate),
tilemap.add_placed_fragment (provenance). Suite: tests/test_erasures_place.py.

**1 — Erasure rung MEASURED (76 real pilot tiles × 6 q values × edge/random
cuts × 2 detectors = 9,120 decodes):** ctx bits q=0.80 → 96.1%, q=0.85 →
98.7%, q=0.90 → 100%; global bits dead below q=0.80 (0–2.6%), 77.6% at
0.85, 92.1% at 0.90 — matches the §14 rung arithmetic (ctx-class bits
required, as predicted). Edge-geometric vs random cuts indistinguishable
at ctx (real error clusters don't couple to the cut shape). **Zero
wrong-address decodes in all 9,120 trials** — pad/counter gates hold under
erasure decoding. q=0.70 (f=30 > 26) refuses outright, as it must.

**2 — Placer, genie bits, FULL-page hypothesis space (no pruning), 5
positions × {4,5,6,8,10} mm × 2 detectors:** placement CORRECT 100% at
every size including 4 mm; gate PASSES 5/5 at ≥5 mm and correctly REFUSES
all 4 mm placements (rivals dip to 0.103–0.115 < the 0.20 bar at ~60-site
support — honest ambiguity, not a miss). Gated floor = **5 mm**; worst
correct-placement mismatch 0.086 (= the known channel), min rival at ≥5 mm
0.211. Rotation recovery 3/3 (k=1,2,3, exact origin). Wrong-seed null:
best mismatch 0.267 = the d-spectrum floor, gate False. Wrong-region
pending mask: refused (no false accept). ~0.73 s/fragment for the whole
7.3M-offset × 4-rot search (cached field); pruned-to-region same answer.

**3 — ISOLATED end-to-end (the §15.5-item-2 unknown, RESOLVED): own pitch
measure → own lattice lock → ctx detect → place, NO enclosing geometry.**
6/8/10 mm: **5/5 each** placed + gated + correct (placed-bits BER vs GT
0.3–2.7%); 5 mm: 5/5 placed correctly (BER 3.5–5.3%), 4/5 gated (one
conservative refusal). The piece-local lattice lock is NOT the binding
floor down to 5 mm on this channel — the sub-grain ladder is fully
decoder-limited by pilot-bit support, as §15 hoped.

**4 — Fresh-window gate validation (scan B, 3 positions × {6,8} mm —
constants were set on scan C):** 6/6 correct + gate PASS, mismatch
0.007–0.021, rivals 0.271–0.302, z-gaps 6.2–9.2. **Gate constants
(true < 0.15, rivals > 0.20) FROZEN** per §15.4(iii); measured z-gap on
correct ≥5 mm placements is ≥2.9 (informational — not yet gated).

Caveats: single sheet/engine (e014 AltaLink print, Canon 4800 scans);
crops are square razor cuts, not torn shapes (place.py v1 has no piece
mask — torn-edge support is a small extension); multi-piece-per-glass
segmentation (§15.5) still unbuilt, needs a real confetti scan.

Adversarial review round applied (2 CONFIRMED majors, both live-reproduced
by the verifiers, both fixed + regression-tested before commit): (1)
place_fragment retained ~167 MB of score maps per (page,rot) hypothesis —
a volume search would hold GBs; restructured to streaming top-2-with-
shoulder per hypothesis (results byte-identical on the spot-check: pos1
6 mm ctx mism 0.015 / rival 0.259 / z-gap 5.7; peak 786→272 MB) + field
cache capped at 16 pages. (2) placed fragments (no pilot words) fell to
the 0.5 no-evidence quality default, so every quality-aware merge policy
starved or drowned them — pilot_ber_est/tile_quality now fall back to the
placer-measured mismatch (test_placed_fragment_quality_plumbing).

## Run table

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 014.0 | 2026-07-08 | gen_e014.py (layout_version 3, kcell-c2) + 6-gate preflight green | build/e014.ps | eb2f8cbfb1c9f208472c52eeac30230bcfb9cea7481b722dfba9b93505fde153 |
| 014.0 | 2026-07-08 | added to office bundle scratch/office-2026-07-08.tar.gz | tarball | a07479ba8bcd586cc440f259fb67f37c5cce9ff72b607beaff7d8323fad91a07 |
| 014.1 | 2026-07-08 | PRINT (office AltaLink, from the bundle) + Canon 4800 dpi grey scan of sheet A | scans/xerox-e014-A-canon-4800gray.tiff | 5a8f895cda0045ffad95745601c8a242a9dd91b0a2d3eb8e938099c57fddb91d |
| 014.1 | 2026-07-09 | FIRST BLIND C2 decode (acquire-v2, cell_dots=2): 17/18 windows, BER 6.0–20.3% (median 8.05%), pilot≈payload uniform; §13.1 no-duplication prediction confirmed | scratch/{decode,sweep}_e014.py | 8 px/dot; BER-aware gate |
| 014.2 | 2026-07-09 | scan B (displaced) | scans/xerox-e014-A-canon-4800gray-B-displaced.tiff | 76226088c7595d5e97393f2d50ced69e5d68d9e01f11c2d91cdf987f13059b9b |
| 014.2 | 2026-07-09 | scan C (displaced + heavy book) | scans/xerox-e014-A-canon-4800gray-C-flattened.tiff | cb9569e7f2a63fc0f1169d9e362d67bb5011c4af28c057b2743d73a8372e6bb1 |
| 014.2 | 2026-07-09 | ctx+PAVA+multi-scan campaign + WIRED into acquire; fold analysis; F6 adaptive loop | scratch/{campaign,wired,multiscan,patches,handanalyze}_e014.py | see RESULTS |
| 014.3 | 2026-07-09 | c2 CONFETTI GRAIN measured (scan C, blind ctx, off-crease): 6mm 0/5, 8mm 1/5 (BER 1.0%), 10mm 5/5 (0.3-1.1%), 13/16/20mm 5/5 — grain ~10mm placement-guaranteed = the geometric 2x5.08mm tile prediction; 2/3 of c3's 13-15mm | inline (session) | fragments >=1cm2 self-address at ~1% |
| 014.2 | 2026-07-09 | ladder: 7.89% → ctx 1.93% (best scan) → 3-scan ctx sum 1.37% (off-crease 1.17%); wired path 1.97% combined; ctx sampling-dependence overturns 007.6; F1∘F6 composition law | tests/test_ctx_calibration.py | suite 243 |
| 014.4 | 2026-07-09 | PRE-REGISTERED (designed, not run): sub-grain failure attribution at 6/8 mm — genie-geometry + oracle-margin arms on scan C; gates the PILOTS-DESIGN §15 / F13 build | protocol above | zero print |
| 014.4 | 2026-07-10 | RAN: blind=full-tile-visible=genie at all 15 windows ⇒ WORD INCOMPLETENESS, geometry exonerated; oracle separation ≥0.20 everywhere; pre-registered decoy bar >0.35 impossible by construction (codeword distance spectrum min 32/100, measured) — gate re-formed floor-aware; F13 GREEN | probe_0144.py + _posthoc + _dmin | zero print |
| 014.5 | 2026-07-10 | erasure rung MEASURED (ctx q=0.80/0.85 → 96/99%, 0 wrong-addr in 9,120); F13 placer BUILT+MEASURED (gated floor 5mm, isolated end-to-end 6mm+ 5/5 incl. OWN lattice lock — §15.5 item 2 resolved); gate constants FROZEN on scan-B fresh windows 6/6 | probe_0145.py; paperholo.place; bch.decode_erasures; suite +6 | zero print |
