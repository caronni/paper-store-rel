# Experiment 018 — CONFETTI-C3-PLAY

A c3 K-plane coded volume built to be **cut up and recovered** — a companion
to e016 (coded c2 archive) on the home engine's strong plane, for driving a
confetti session in a separate thread. Self-referential payload: the archived
bytes are paperholo's own encode/format/confetti source.

## Design
- **Geometry:** `kcell-c3`, frozen e012 layout_version-3 page (2220×1500 cells
  = 4500×6660 dots at (230,178), ≥6 mm margins, p60b6.v3 pilots). This is the
  hardware-validated c3 archive geometry (012.3 envelope PASS, blind BER
  0.64–3.97%). Archive-style: one whole-page imagemask, no furniture (R3).
- **Fountain:** fountain-v1, single page, **K/N = 0.506 ≈ f 0.5** — 396 source
  + 386 repair symbols across the 782 interior 64-cell tiles (one dense block,
  so ANY ~half the certified tiles recovers ALL data). This is the confetti
  redundancy dial the user asked for as "f=0.5"; note *f* (the recovery
  fraction) is a measured outcome, K/N is the printed dial.
- **Inner FEC:** per-tile LDPC **r0550** + CRC-32 — the confetti pipeline's
  measured-proven rung (016.5–016.7), max parity/fragment robustness.
- **Payload:** deterministic tar.gz (mtime=0, sorted, gzip -9 -n) of the 18
  CORE modules `src/paperholo/{__init__, modulation, keystream_ref, encodings,
  pilots, bch, compose, ldpc, fountain, tilemap, scannorm, formats, segment,
  place, dust, sync, metrics, psgen}.py` = **103,195 bytes**. `acquire.py`
  (128 KB receiver) excluded for size — the K/N~0.5 c3 budget is ~102 KB and
  the receiver isn't needed to appreciate the archived format. `data` IS the
  tar.gz verbatim (no pad/header): `tar xzf <recovered>` → `paperholo/*.py`.
- **Seed:** `b"paper-store/exp018-confetti-c3"` keys everything.

## Build (2026-07-11, run 018.0, zero-print so far)
`experiments/018-confetti-c3-play/gen_e018.py` →
- `build/e018.ps` — 7.56 MB — **sha256 `a691c7d7e83629d5b20873478819f76f9211324bfea9e262f51393f878be86ff`**
- `data` (CORE tar.gz) — 103,195 B — **sha256 `4c75fe59241499a827293a1c6b9261a306a3936678d46ec78843feea1d17c44d`**
- Deterministic: re-gen reproduces both shas byte-for-byte (given an unchanged
  source snapshot; this is a *play* sheet, not a frozen golden format — the
  coding stack carries the guarantees, so no `test_format_*_golden.py` anchor).

## Pre-print recoverability gate (`verify_e018.py`, ALL PASS)
Sim-before-toner ground rule. Proves a separate session recovers the archive
byte-exact BEFORE any print:
1. **determinism** — tar.gz + ps shas stable; K/N 0.5064.
2. **payload integrity** — recovered bytes untar to the 18 exact source files.
3. **volume recovery** — `fountain.volume_decode` byte-exact from all 782
   tiles **and from a random 399/782 = 51% subset** (the confetti claim: close
   from ~half the page; one dense block ⇒ no per-block coverage worry).
4. **blind receiver** — clean-channel c3 window: 9 tiles certified, 18,848
   user bits byte-exact vs the fountain frame; sim genie BER **3.49%** (on the
   measured c3 anchor 3.56% sim / 3.74% hw).

## Print protocol (PENDING explicit user GO — .claude/rules/hardware.md)
- Engine: home **M281** (`<host>`), raw JetDirect 9100.
- Command: `scripts/print_plane.sh experiments/018-confetti-c3-play/build/e018.ps`
- Verify with a loupe (bit-fidelity) before trusting any decode (§2.4 / R).
- Scan (for the confetti thread): **Canon 4800 grey**, white lid, re-placed
  scans; the measured c3 footing.
- _[to fill on print: date, media, driver path, scan filename + sha256]_

## Decode handoff (separate confetti session)
**Superseded by 018.1 below** — the original note here said "drive
experiments/016-arch3-c2-volume/session_decode.py", which was aspirational:
that driver is pinned to e016 (format row, seed, golden sha, c2 window
constants) and cannot read this sheet. The e018 sibling driver now exists
in this directory and embeds the source-independent constants (seed,
data_len 103195, golden `4c75fe59…`, vspec 396/782 r0550) directly:
```
env/bin/python experiments/018-confetti-c3-play/session_decode.py \
    <img> [<img> ...] --dpi <true dpi> [--fresh]
```
STOP at `VOLUME DECODED … == GOLDEN, BYTE-EXACT` (exit 0; bytes land in
build/recovered_e018.tar.gz, `tar xzf` → paperholo source).
Big-pieces-first; ~51% of the sheet's tiles suffice.

## Session decoder (run 018.1, 2026-07-11, zero print)
`session_decode.py` (this directory) = the c3 sibling of the measured e016
fragment-session driver, same doctrine (weighted_sum union / erode-4 /
refine chain / 0.20+0.20 gap-gate). SOURCE-INDEPENDENT: local
`FormatDescriptor("e018-v3-c3")` passed as `candidates=[FMT]` (registry
untouched; verified spec-equal to `gen_e018.make_spec()` AND the e012
registry row), frozen vspec constants (never re-tars live source; manifest
cross-checked when present). c3 re-basing: WINDOW_CELLS=200 /
OVERLAP_CELLS=40 (the physically identical 25.4 mm window + 5.08 mm
overlap; NOTE overlap in cells is now 2/3 of a pilot period — unmeasured
invariant choice, harmless under absolute per-window addressing);
WORD_PATH_MIN_MM2=230 (at the 011.0 15.1 mm guarantee grain, routing-only);
--dpi REQUIRED, recommended footing = Canon 4800 grey decimated 3x → 1600
dpi = 8 px/cell (the measured-best c3 canonical: 0.57% < 1200-native 0.85%
< 2400 1.67%, acquire-v2 on e012 scans; the 8 px/cell win is
4800-SOURCED — do not route through 2400). Placer gates carried from e016:
safe because the decoy floor is the v3 window code's distance spectrum
(014.4, sampled min 32/100 — NOT code algebra (2026-07-29 exhaustive correction: TRUE min = 27, mult 3; 32 was a 400-pair sample — see the 014.4 correction); cell-size/seed-independent); c3 placer
grain ~9 mm is an ESTIMATE (2.25x sparser pilot sites), first real session
= its measurement.

**Sim gates (both PASS, before any real scan was fed):**
- Fixture A (whole page, mild optical channel, 8 px/cell): 1 piece →
  tiled word path → 782/782 interior symbols → VOLUME DECODED byte-exact
  == golden, exit 0.
- Fixture B (carved confetti, 68+121 rotated pieces 7.6–28 mm, white
  backing, blur 2.4/noise 7.0, 67.8% of interior carved): session OPEN
  after canvas 1 (264/396 symbols — closure correctly unreachable at
  43.8% carve), CLOSED on canvas 2 (443/396) byte-exact == golden;
  GT cross-check **178/178 observations in their unique source rects,
  0 false placements** (160 correlation-placed + 18 word/tiled); piece
  yield 59/68 + 119/121 = 97%; already-folded skip path verified.
  Fixture scripts scratchpad-only (session-scoped, not archived).
- Adversarial review round (3 lenses + adjudication, workflow): 25
  findings; transcription FAITHFUL (API signatures, keystream sign,
  rot90 algebra, pim addressing all verified live); constants audit PASS
  (every value consistent with the measured record). 1 CONFIRMED major
  — e016-inherited flow re-ran a CLOSED session as false "session open"
  / exit 0, inverting a MISMATCH exit — FIXED (post-loop verdict
  re-evaluation from persisted certified tiles) + mismatch bytes now go
  to recovered_e018.MISMATCH.bin (forensics-labeled, never the
  deliverable path) + atomic state writes (tmp+os.replace). Both fixed
  paths + a fresh in-loop closure re-verified after the fix.
  Known-and-accepted (shared with the measured e016 driver, unchanged):
  `done` dedup keys on basename only — don't feed two scans with the
  same filename; a zero-yield image (wrong --dpi) is still marked
  folded (re-feed under a new name or --fresh).

## 018.2 — p5/p8 failure forensics (2026-07-11, zero print)
First real scan (user run, `scratch/hp-e018-canon-4800-confetti-1.tiff`,
state `scratch/e018-session_state.json`): 25 segments = 17 real pieces +
8 toner-free phantoms; 10/17 decoded (9 tiled + 1 placed), 67/396
symbols, session open. Deep forensics on failed pieces 5 (1518 mm²,
−11.8°, interior) and 8 (842 mm², −4.4°, page-bottom-edge triangle with
attached blank margin); 3-agent workflow, all claims measured unless
labeled. **Pixels exonerated on both** (p5 ink 64/paper 209, p8 110/201
vs backing 224; pitch 8.000 exact) — **every failure is geometric**:
- **p5 word path**: central ID window failed `post_fold_words` at 100%
  ink coverage (2/6 words, the good ones 0-error = slip gradient), and
  page_decode's single-central-ID **veto killed the whole piece** —
  bypassing it, 4/6 of its own tiling windows acquire at pilot BER
  4.0–8.7%. Re-derotating by the measured −0.375° flips ident to OK.
- **p5 placer**: **localized correctly** (true origin (1341,704) rot 2,
  z 14.9 vs rival 6.1) but refused at mismatch 0.349 > 0.20 gate. Angle
  sweep: segmenter angle off by −0.33±0.05° (016.4 error class); even
  at best angle full-piece rigid mismatch floors at 0.248 — a 47 mm
  piece with y-scale −0.31% (M281 print-y-short class) exceeds the
  rigid model's coherence length. **Quadrant-scale placement + the
  EXISTING refine chain: 4/4 quadrants pass (0.043–0.101), 12 symbols
  certify vs 0 in production.**
- **p8 word path**: central ID **succeeded** (8/9 words, 2.8–3.9%
  pilot) — and page_decode **discards the ID window's decode**; then
  0/6 bbox-anchored tiling windows passed (35–62% on backing on the
  rotated triangle; stage-A pass boundary ≈0.7 mask-frac). Max-ink
  window: 6/6 words. 3 mask-aware windows → 5 tiles / 2 symbols.
- **p8 placer — STRUCTURAL FINDING**: true origin oy=1959 > 1874 = max
  feasible in place_fragment's 'valid'-mode correlation (rot-1 grid 346
  rows; the grown+derotated array of a **page-edge piece overhangs the
  field**, only 497/44k core cells actually off-page) — **the true
  placement is excluded by construction**; padded search places it at
  z 25.1, gate-passing 0.139/gap 0.234. Second binder: +0.30–0.35°
  angle residual (dose-response 0.139→0.306 over 0.3°) which
  scannorm.measure_cell_pitch **already measures in-pipeline
  (angle_rad +0.448°) and the pipeline ignores** — sweep seed, not
  one-shot (re-derotation to 0.448 lands at BER 0.253, still fails).
- **Cross-cutting**: id-crop ink coverage does NOT separate decoded
  from failed (p16 decoded at 0.518, p5 failed at 1.000) — "center ID
  on ink" refuted; the fix is ID **retry** at top-coverage windows.
  Footing ruled out (4800 ≡ 1600 on both). **Gates never
  false-accepted** (p5 refused a correct location honestly; p8's best
  was noise) — 0-false doctrine held on real scissors.
- **Decodability**: p5 YES (12 symbols measured via quadrant+refine;
  est 20–30 finer, labeled estimate); p8 partial (5 of ceiling 8 —
  bottom-edge tiles fountain-inert).
- **Fix package — APPROVED 2026-07-11, built as run 018.3 (see below);
  design doctrine = PILOTS-DESIGN §15.6 (anchor-graph invariants I1/I2/
  I3), LAYERS F13 row amended, REASONING-LOG session entry. Original
  ranked list (as measured, pre-build):**

## 018.3 — anchor-graph receiver BUILT + SIM-MEASURED (2026-07-11, zero print)
Implementation of §15.6 (decoder-axis, no format change; suite 339):
- `paperholo.place`: **allow_overhang** padded correlation (opt-in,
  default False preserves the frozen-gate provenance) + `overlap_slices`
  clip helper; `fragment_pilot_sites` overhang-safe. Unit tests
  (test_place_overhang.py, 5): negative-origin corner + far-edge
  (p8-class) place EXACTLY; decoy refusal under the enlarged padded
  candidate set 5/5; legacy mode byte-compatible (float32 FFT jitter
  ~5e-8 only).
- `paperholo.formats.page_decode`: **fold_id_window** (a successful ID
  acquire folds instead of being discarded), **mask**-aware window grid
  (min-coverage filter + quarter-stride mask-snapped candidates),
  **id_retry** at top-coverage windows — all default-off (default path
  verified behavior-identical; golden suites pass).
- e018 driver `--piece-chain anchor` (new default): word path with
  mask/retry/fold; placer = multi-angle retry (0 -> scannorm angle_rad
  seed -> ±0.25/0.5/0.75°) x window-split placement above the rigid-model
  span (SPLIT_CELLS 260 bbox AND SPLIT_CORE_CELLS 52k core — the core
  criterion was an IN-BUILD FIX: bbox-only split starved rotated pieces,
  caught by the failure-class synthetics) + mutual-consistency ±2 cells
  + per-window pilot-label recal + overhang-safe emission.
- **Failure-class synthetics** (test_session_anchor.py, durable): the
  three 018.2 classes — page-edge piece w/ attached blank margin
  (overhang), 350-cell piece rendered with y-scale −0.31% (M281
  print-y-short), 31° rotation — ALL place + certify byte-true vs the
  fountain frame; toner-free phantom sliver refused.
- **A/B on the 016-style carve fixture (189 pieces, 2 canvases,
  identical inputs)**: refine baseline 264 syms @ canvas 1 / closes at
  443 / 178 of 189 pieces (94%); **anchor 325 syms @ canvas 1 (+23%) /
  closes at 512 / 189 of 189 pieces (100%), 0 failed**; volume
  byte-exact == golden both chains. **GT audit: 189/189 observations
  inside their source rects, 0 misplaced, 0 duplicate claims** (171
  correlation + 18 word/tiled) — 0-false doctrine holds under padded
  search + window splits. Whole-page fixture A closes byte-exact
  through the anchor word path.
- **Adversarial review round (3 lenses + adjudication, post-build):**
  core math VERIFIED BY PROBE on all three lenses — padded-correlation
  origin arithmetic exact at all 4 rotations; pend_ok cache provably
  sound (shape bijective in pad); fragment_pilot_sites rewrite
  byte-identical to HEAD on 16 interior cases; _emit_placed
  byte-identical to the 016 inline emission; _rotated_offset exact on
  800 random probes; scannorm angle_rad sign convention CONFIRMED
  correct (reviewer disproved its own suspected flip); default-path
  regression identity verified hunk-by-hunk incl. fold order. 1
  CONFIRMED major — mask-filtered window grid IndexError on
  normalized images narrower than one window (elongated ≥26mm-long
  <25.4mm-wide pieces, the #11 strip class) — FIXED (sub-window guard)
  + 5 review minors fixed same round: id_retry mask-shape guard;
  consistency reference switched from decoupled per-axis median to the
  highest-z window (2-window median pathology); whole-piece fallback
  now also covers consistency-filter wipeouts; fold-only word "success"
  no longer skips the placer (ID-only fold kept as evidence, placer
  emission excludes the folded cells); refine_piece gains
  allow_overhang so page-edge pieces keep the P2 chain. Accepted
  as noted (fail-safe/cosmetic): padded low-support availability tax
  on tiny edge pieces; ≤2-cell seam double-emission between
  consistent windows; rot_k 1-1 tie insertion-order break; n_refined
  increments pre-emission.
- NEXT: re-run the real e018 scan-1 session (user-driven) with
  --piece-chain anchor; expected recovery per the 018.2 forensics:
  p5 +12-30 syms, p8 +5, plus the edge/corner cluster (10/12/13/14/15).

## 018.4 — scan-1 footing A/B (user runs, 2026-07-11; refine chain both)
Same scan, same OLD chain (`--piece-chain refine`), only the footing
varied — a clean decimate-vs-native A/B:
| footing | pieces | routing | refined | certified | symbols |
|---|---|---|---|---|---|
| 4800 native (try_1) | 25 | 9 tiled + 1 placed + 15 fail | 0 | 67 | 67/396 |
| 1600 decimated (try_2) | 24 | 9 tiled + 1 placed + 14 fail | **1** | **80** | **77/396** |
**Decimate-first BEATS feeding raw 4800: +13 certified tiles at
identical piece routing** (pure per-cell quality: one global 3x
box-average vs per-window 24→8 resampling inside scannorm; the refine
chain also succeeded at 1600 where it failed at 4800). Piece-count
delta = the footing-dependent phantom sliver. certified 80 vs symbols
77 = 3 non-interior (edge) tiles, fountain-inert — normal accounting.
Strengthens the 016.2 "pre-decimate, declared-equivalent" doctrine to
"pre-decimate, measurably better" for this driver. Anchor-chain re-run
of the same scan still pending (user).

## 018.5 — --diag live viewer (2026-07-11, merged 00a3a09)
Built in a background worktree, adversarially reviewed (no blocker;
1 major + 4 minors FIXED pre-merge: exception-proof hooks — a viewer
bug now self-disables with "[diag] viewer disabled" instead of
aborting the decode; port-in-use → ephemeral fallback; img_glass=None
guard; refined pieces' pilot dots at the REFINED angle (was up to
3.25 cells off at corners); terminal red frame on legacy-chain gate
refusal). Per-piece browser view (user choice), two spatial panels:
active glass (tilted-frame outlines, status colors, magenta sampled
pilot-site dots in each piece's rotated lattice) + reference page
(reassembly/LDPC/pilot from PageDecodeState). Byte-identity WITH vs
WITHOUT --diag asserted by test (state pickle byte-equal,
tests/test_diag.py); spec = DIAG-DESIGN.md. Deferred next pass:
per-piece detail inspector (gate numbers, angle sweep, BER).
Geometry note: dots are cell-centre-accurate (phase dropped) —
visualization, not measurement.
  (1) mask-aware window tiling + ID-retry + fold-the-ID-window (driver
  + page_decode, ~20–30 lines; rescues p8 word path and p5's veto);
  (2) padded 'full'-mode pilot correlation in place.py (unlocks ALL
  page-edge pieces — every real scissor session produces them; #10/
  #12/#13/#14 are edge/corner candidates of the same class);
  (3) multi-angle placement retry on gate-fail, seeded by scannorm's
  in-pipeline angle_rad (±0.6°, 0.1–0.25° step, same gate arbitrates);
  (4) window-scale placement for big placer pieces (also un-deadlocks
  refine, which is gated behind the full-piece admission it can never
  earn on a warped 47 mm piece). Bonus record: pilot-site BER tracks
  payload EXACTLY on real confetti (p5: 0.3493 vs 0.3418 core).

## Diagnostics — `--diag` live viewer (zero print)
`session_decode.py --diag [DIR] [--diag-port N]` opens a per-piece LIVE
view of the session decode: an ADDITIVE, read-only observer hook
(`diag.py`, `DiagViewer`) renders two spatial panels — **active glass**
(each piece in its tilted frame, coloured by live status, angle-labelled,
with the receiver's sampled pilot SITES dotted in the piece's own rotated
lattice frame) and the **reference page** (draw_decode_map panels B/C/D:
payload footprint / LDPC status / pilot tiles). Headless: the "window" is a
stdlib-http.server web view at `localhost:--diag-port` (numbered PNG frames
also written to DIR). Flag ABSENT ⇒ the decode path is byte-identical to a
plain run (regression `tests/test_diag.py`, driver run twice). Per-piece
detail inspector (gate numbers / BER side panel) DEFERRED to a next pass.
Architecture + geometry note: `DIAG-DESIGN.md`.
- **REAL-SCAN VERDICT (ingested from the live session thread,
  2026-07-11): repass v1 = 0 conversions on the try_2 e018 state**
  (4 scans, 181/396 symbols, 46 word-path : 3 correlation
  observations; repass refit the correlation pieces, gained nothing;
  fixed point round 1). NOT a correctness failure — the bars held and
  the correlation-only supersede gate did its job — a REGIME
  MISMATCH, as pre-flagged in the v1.1 deferral note: the 018.3
  anchor-graph word path is now so strong (mask-aware windows + ID
  retry) that big scraps decode via words (try_2: 10/10 tiled,
  0 placed), structurally starving v1's correlation-class lever.
  fixture-B (+2) was placer-heavy — the opposite regime.
  **Live-thread tile study (their numbers): certified BER mean
  ~4.4-5.4%, r0550 cliff ~25%; of 134 fully-covered failed tiles, 95
  are MARGINAL (BER below the cliff) failing on spatially clustered
  CONFIDENT-WRONG regions (|LLR| wrong 2444 > right 1580; within-tile
  warp/phase drift + seams) — exactly the §15.7 refit class. The
  mechanism is validated; the delivery (correlation-only) doesn't
  reach the patients. => v1.1-a (word-anchor poses -> refit word-path
  pieces) is promoted from deferral to THE next build, with a
  measured ~95-tile target pool and a design refinement: the trust
  rule goes CONDITIONAL — word evidence is higher-trust WHERE IT
  CERTIFIED; within failed tiles it is measured-bad, so
  label-supervised re-derivation supersedes there (cell-granular trim
  already built).** Also ingested: combined |LLR| max 692,895 (median
  ~7) = latent unbounded-calibration bug UPSTREAM of repass (branch
  emitters clip at 12/16; suspect acquire's PAVA log-odds); clipping
  the combine at ±8 recovers +7 tiles free (their measurement) —
  right home = tilemap combine, protects against any emitter incl.
  repass's own dense recal. make_data() live-source drift trap
  confirmed a third time (their GT study burned by it; guard idea:
  assert make_data sha vs manifest before any GT use).
## 018.6 — §15.7 "repass" decode-directed re-acquisition (2026-07-11, zero print, branch feedback-repass)
F15 build per the §15.7 BUILD SPEC (peer-thread handoff): certified
tiles as dense truth labels (~40x pilot density; export = the
pre-existing tilemap.known_cell_values — the F10 accessor anticipated
this loop) -> per-window label-augmented refit (refine_on_sites +
recal_llrs_from_labels are label-source-agnostic; pilots UNION
certified cells, raster-sorted) -> re-sample from original glass ->
gate re-verify -> SUPERSEDE at cell granularity (tilemap.drop_scan +
trimmed re-add; R2 replace-never-sum) -> decode_tiles -> fixed point.
Deployment = standalone post-pass (`repass.py <imgs> --dpi D --state S
[--rounds 3]`; pre-repass snapshot at <state>.prepass for A/B);
core-loop integration deferred until real-scan validation (user
decision); torn-edge jigsaw deferred (same session).
- **Validation round 1 (pre-review-fix code): all five §15.7 bars PASS
  on fixture-B** (509 certified/57 failed in, +1 conversion, 0 wrong
  in 510 GT-byte-checked, 0 demotions, fixed point round 2, no-op on
  the fully-certified fixA state, idempotent rerun) — then the
  adversarial round (2 lenses + adjudication) confirmed **3 blockers
  + 2 majors, all fixed**: (i) dense-recal LABEL-PAIRING SCRAMBLE
  (concat-order values vs raster-order mask extraction — ~49%
  mislabeled; conversions had come from the geometry refit alone);
  (ii) dead word-path guard (every obs carries placement_source;
  presence-test never fired) — word-path evidence could be superseded
  by placer re-derivations; (iii) _verdict FileNotFoundError in
  build-less worktrees (mkdir fix, rides to session_decode);
  (iv) non-refit windows were superseded with anchor-fallback quality,
  discarding refine-chain LLRs — supersede reworked to CELL
  granularity (emit improved windows only; old observations trimmed
  by exactly the covered cells, remainder survives verbatim; emit
  before drop); (v) no pre-repass snapshot (A/B claim undelivered).
- **In-build measured trap, now doctrine**: the e018 payload is a
  tar.gz of the LIVE sources — self-referential — so any src edit
  reshuffles fixture page content (a tilemap.py fix flipped the
  tuned band fixture). tests/test_repass.py therefore renders a
  FROZEN-payload page (seeded random bytes at the frozen 103,195-B
  length). test_session_anchor.py carries the same latent trap
  (loose bars mask it) — follow-up item.
- **Frozen conversion fixture (post-fix)**: uniform contrast
  compression ALPHA=0.41 + noise SIGMA=15 on a 280-cell piece at -8°
  targets the measured v1 mechanism (the driver's dA==0 path emits
  ctx LLRs with NO pilot recal; a global level shift de-calibrates
  it; label-refit restores it): driver 12 certified/18 failed ->
  repass round 1 converts 3, round 2 fixed point, 0 wrong certs;
  plateau alpha 0.39-0.42 x sigma 13-15 converts 1-3 everywhere;
  deterministic (2x identical). Suite green in-worktree.
- **Validation round 2 (post-fix code, final numbers): fixture-B
  509 -> 511 certified (+2 conversions, up from pre-fix +1 — the
  label-pairing fix pays), 51 pieces refit round 1, fixed point round
  2, volume still golden byte-exact, .prepass A/B snapshot written;
  GT audit on the repassed state: 233 observations (120 correlation +
  18 word + 95 repass incl. cell-trimmed keeps) all inside their
  source rects, 0 bad; 511/511 certified byte-exact, 0 wrong, 0
  demoted. Frozen-fixture pytest: driver 18 failed -> repass converts
  3, fixed point, deterministic 2x. Worktree suite 341.**
- NEXT: run repass on the REAL scan-1 anchor-chain state (the joint
  session) — the honest test; then the integration decision (§15.7
  deployment shape) and the v1.1/stretch items (word-path pieces via
  anchor poses; boundary-ribbon prior).- **BRANCH CLOSE-OUT (2026-07-11 EOD): v1.1-a DESIGNED, NOT BUILT**
  (user decision: LLR saturation is being fixed upstream in acquire by
  the live thread; v1.1-a build deferred to a fresh session). Design
  record so nothing is lost — v1.1-a = un-gate repass to word-path
  pieces under CONDITIONAL TRUST:
  (i) word evidence is higher-trust WHERE IT CERTIFIED; inside FAILED
  tiles it is measured-bad (try_2: clustered confident-wrong), so
  label-supervised re-derivation supersedes there and ONLY there —
  refit emission masked to failed-tile cells (helper sketch:
  frag_mask AND page-mask back-mapped through the placement, the
  fragment_truth_sites algebra); word observations trimmed on exactly
  those cells.
  (ii) GOTCHA (would have been a silent killer): ScanObservation
  quality is a PROPERTY (pilot_ber_est derives from tile_words +
  fail_errs + meta) — re-adding a trimmed word observation via
  add_placed_fragment loses tile_words and weight-floors it to 0.05,
  silently erasing kept evidence. Trim re-add must construct
  ScanObservation directly, copying tile_words/fail_errs/meta.
  (iii) GOTCHA: the related-sids matcher misses round-1 keep-sids of
  single-observation pieces in round 2 ("repassN/keep/<base>" has no
  trailing segment — match needs an endswith("/<base>") arm).
  (iv) No anchor-pose constructor needed for v1.1: the global placer
  search finds word-piece poses fine (018.2: p5 localized correctly
  even at bad angle); pose-from-decoded-words is a compute
  optimization, not a prerequisite.
  Partial in-worktree edits were REVERTED (unfinished flow is worse
  than none); this design note + §15.7 is the carry-forward. The
  OBS_LLR_CLIP experiment (per-observation ±8 in tilemap._dense,
  validated 9/9 tests in-branch) was also reverted — the upstream
  acquire-side fix owns that bug; if upstream lands source-side
  clamping only, the combine-side guard remains a good idea (protects
  against ANY emitter, incl. repass's dense recal which tightens
  Gaussians toward the ±12 clip by design).

## 018.7 — "in the middle" tile forensics + THE LLR HONESTY BUG (2026-07-11, zero print)
User-driven study of the covered-but-failing tiles ("study them visually
and in depth"), which found and fixed a receiver-wide bug. Instrument
promoted: `tile_forensics.py` (exact decoder-eye view: weighted_sum
combined LLR via gather_tile_llrs vs the PRINTED truth from
build/e018_gt/; renders cliff histogram + per-tile error/confidence
maps -> scratch/e018/e018_failed_tiles.png).

**Truth-path traps (measured, cost hours — recorded so nobody repays):**
(1) `gen_e018.make_data()` re-tars the LIVE source: post-018.3 edits make
it 59190c79… != printed 4c75fe59… — GT must come from build/e018_gt/
(decode itself is immune: CRC + hardcoded golden). (2) gather_tile_llrs'
slot raster pairs with `ldpc._tile_payload_indices`, NOT
encode_tile's codeword order. Lesson: validate any truth path on
CERTIFIED tiles first (expected ~4%, not ~50%).

**Tile-population facts (4-scan state, 181/396):** certified raw
pre-LDPC BER mean 4.4% / p95 15.1% / max 24.9% (= the operating r0550
cliff). Failed cov>=0.9 (n=134): 95 MARGINAL (BER <= cliff — should
decode, don't), only 39 broken (>25%). Error maps: MARGINAL class =
1.2%-BER tile failing on a clustered corner burst; MID = bottom-half
within-window drift gradient read CONFIDENTLY wrong; BROKEN =
wrong-phase salt-and-pepper with a correct band. |LLR| on wrong cells
(2444) EXCEEDED right cells (1580) — confidently-wrong, LDPC poison.

**THE BUG (user instinct: "LLRs of this magnitude scream bug; clipping
hides a symptom" — both confirmed):** acquire's K-path calibration gate
`if labels >= 300: PAVA else: RAW` leaked uncalibrated ctx-GMM scores
whenever a window decoded <~3 pilot tiles. Raw GMM scores reach ~5e5
(sigma floor 1e-3) vs calibrated <= ln(n+1) ~ 6.8 — a ~70,000x voice
imbalance in the union — and it SELF-SELECTS for garbage: geometry
drift -> fewer word decodes -> fewer labels -> uncalibrated -> the worst
windows shout loudest. Measured: combined |LLR| max 692,895; giant
values confined to word-path observations' tails (~3% of cells; healthy
windows bounded at exactly 6.0 = the PAVA clamp). Third
PAVA-boundary incident (017.6 cross-fit scale; now the K-path gate) ->
INVARIANT adopted (LAYERS §1 LLRs row): raw detector scores never cross
an API boundary — every emitted LLR is calibrated or bounded.

**FIX (src/paperholo/acquire.py, default-on):** MIN_CAL_LABELS 300->60 —
PAVA's 1/(n+2) clamp makes small-label maps SELF-LIMITING (60 labels ->
|LLR| <= ln 61 ~ 4.1: fewer labels, less confidence, exactly the honest
scaling) — and <60-label windows get scores RESCALED into the
calibrated range (UNCAL_LLR_CAP 6.0), never raw. The interim ±8
clipping probe (+7 tiles) retired as symptom-hiding.
**A/B (same 4 scans, fresh sessions): 181 -> 190/396 symbols (+9),
certified 188 -> 197, combined |LLR| max 692,895 -> 22.9.** Gain
distribution confirms the mechanism: scan 1 neutral (-1, single
observations — magnitude irrelevant to sign), +8/+8/+9 once the union
combines (the F1∘F6 composition surface). Suite 341 both pre- and
post-merge with the fix; the >=300-label path (all whole-page windows)
is byte-identical.

**Lattice-feedback answer of record (user question):** decoded pilot
words fix geometry ONLY inside acquire (slip voting + anchors, per
window, frozen at return); the P2 refine chain is PREDICTED-pilot-
supervised per piece; certified-LDPC-driven refit exists only in repass
(018.6) and is gated to correlation pieces — a word-path window's
geometry is never revisited. That gap + this bug compounded: drifted
regions were both unfixable and loudest. Next lever (peer thread):
un-gate repass to word-path windows under the v1.1-a conditional-trust
rule; the 95 marginal tiles are its target population.

Session state of record after the fix: scratch/e018/fixtest_state.pkl
(the user's 4 scans re-run through the fixed receiver, 190/396) —
continue the live session from THIS state (the old try_2 state carries
the poisoned magnitudes inside its stored observations).

## 018.8 — repass v1.1-a BUILT + MEASURED: conditional trust un-gates word-path pieces (2026-07-12, zero print)
The 018.6 close-out design record built, adversarially reviewed (7/7
findings confirmed, all fixed), and measured on the real state.
Suite 348 (+5: tests/test_repass_v11.py). Driver diff: NONE
(session_decode._emit_placed unchanged — the trust mask rides the
pre-existing exclude_idx hook); repass.py carries the whole change.

**HEADLINE (the honest test, scratch copy of fixtest_state.pkl +
its 4 decimated scans): 197 -> 216 certified tiles (+19), fountain
190 -> 208/396 symbols (+18), fixed point round 3, 0 wrong in
850,177 GT-audited certified cells** (printed-field GT from
build/e018_gt/, never make_data()). Round 1 alone: +18 tiles, 26
word-path pieces refit, 29 obs superseded, 775k dense labels. v1 on
this same regime: 0 conversions — the un-gating IS the yield. The
95-marginal-tile pool (018.7) converted 19: the remainder stays
failed honestly (r0550 + CRC gates unmoved, R4).

Build shape (mechanics per the 018.6 record, three deltas found by
the review round):
- CONDITIONAL TRUST as EXCLUSION, not inclusion: emission excludes
  the piece's PROTECTED word cells (word-covered outside failed
  tiles, frozen per round) instead of including only failed-tile
  cells. Bit-identical trust boundary on word-covered cells; frees
  never-observed GAP cells under word pieces (review-measured: the
  record's include-mask sketch silently discarded fresh coverage on
  >=17 low_coverage tiles). Measured effect on this state: 6
  low_coverage page-edge tiles gain first coverage (e.g. tile (3,4)
  at 7.3% via a round-3 refit window) — decoded-failed for now =
  union seeds for future scans; certified outcome identical to the
  record-strict variant (both +19/+18 — gap coverage alone converts
  nothing yet).
- ROUND RESUME (review MAJOR, reproduced pre-fix): invocation N+1
  re-derived invocation N's emission sids (deterministic refit) and
  add_placed_fragment raised mid-round — every retry crashed
  identically, state wedged. Fix: rounds number from
  resume_round(state)+1. Re-invocation smoke on the completed A/B
  state: resumes at round 4, clean fixed point, no churn damage.
- gotchas (ii)/(iii) of the record closed as specified: trim re-adds
  construct ScanObservation directly (tile_words/fail_errs/meta
  copied; pilot_ber_est byte-equal — the add_placed_fragment path
  floors kept word evidence to weight 0.05) and the related-sids
  matcher grew the endswith arm for `repassN/keep/<base>` keeps.
  Stakeless skip added beyond the record (word pieces with no
  failed-cell stake are skipped; fires 0 times on this state — all
  46 word pieces hold failed cells).

**Fixture finding (test scope honesty): the synthetic channel cannot
host the v1.1 conversion bar.** acquire's ctx+PAVA calibrates away
every uniform contrast/noise degradation tried (word-path pilot BER
0.000 at alpha 0.41/sigma 10 — per-pixel noise averages out over 64
px/cell; the v1 fixture converts only because the driver's dA==0
path emits UNCALIBRATED LLRs, a gap acquire does not have), and
within-window drift — the real marginal class — does not exist in a
rigid render. tests/test_repass_v11.py therefore pins the MACHINERY
exhaustively (word-piece engagement + real supersede overlap, trust
boundary per round, trim REMOVAL direction, keep quality, lineage
matcher, re-invocation resume, stakeless branch, monotone + verified
fixed point, 0 wrong certs) on a clean word-path fixture, and the
conversion bar is measured on real states (above). Review round also
hardened the v1 test (correlation-path emissions must extend beyond
failed tiles — mask-leakage guard) and de-tautologized two bars
(fixed-point now runs a post-convergence round; fail_errs pinned at
a non-default value).

Deployment note: run repass ONLY on states whose images are listed
verbatim (piece identity = filename + segment index); feed NEW scans
through session_decode.py first (an unknown image's pieces all look
unobserved and would ingest placer-only). Reproduced on the LIVE
try_3 state (user, 2026-07-12): identical +18/+18 to the scratch A/B
(197->216 certified, 208/396 symbols, fixed point r3) — the tool is
state-copy-independent.

Residue (none blocking): (1) core-session-loop integration is
unblocked by the round-resume fix but stays deferred (user decision);
(2) the `retried` failed-piece path (no prior obs -> free anchor-chain
second chance) is inherited v1 code with no dedicated test (fires 0x
on the real 4-scan state — segmentation is deterministic, so a
driver-failed piece re-fails); (3) repass re-segments every piece
every round (O(rounds x scans x pieces), ~15 min for 3x4 here) — a
memoization/only-touch-newly-failed-tiles target IFF wired into the
loop; (4) NOT repass-specific: the combine-side +-8 LLR clip ruling
(018.6 pro-guard vs 018.7 symptom-hiding) is still open, weaker now
that 018.7 fixed the source. Next volume lever unchanged: coverage
(the deficit 188 symbols > any refit pool — repass is a per-scan-set
margin extractor, not a volume-closer).

## 018.9 — live-session forensics + receiver/diag hardening (2026-07-12, zero print)
Driven by two user reports on the live try_3 session (2 sheets fed,
read-only snapshots `scratch/e018/try_3/…-after-sheet-1` and `…-2nd`).
Every finding below adversarially verified (independent GT path,
cell-exact); GT throughout from `build/e018_gt` XOR keystream, never
`make_data()` (certified-tile sanity 0.0457). Full suite 350 (+2:
tests/test_emission_mask.py).

**Why scan-1 p13/p14/p15 "failed to place" (they were routed to the
WORD path, not the placer):** all three have area >= 230 mm^2 AND
bbox-long >= 26 mm, so they tile the word path first, which returned
`all_formats_rejected`; falling through to the anchor placer they were
refused on `mismatch >= 0.20` (best 0.263 / 0.406 / 0.247). Measured
causes DIFFER:
- p13 (+39.25 deg): rigid-span. Its OWN 150-cell sub-windows place at
  mismatch 0.094, but the whole 396-cell piece floors at 0.263 — the
  §15.6/p5 rigid-model-past-25mm effect. The window-split that would
  rescue it did NOT engage: `SPLIT_CORE_CELLS=52000` vetoes (its core
  33k). At 20000 it converts (win 0.156 / gap 0.180, 11.5k cells, 6
  virgin tiles; origin corroborated 3 ways; p12/p16 regression-free).
- p14 (-26.97 deg): a GENUINE `lattice_angle` miscall of ~4 deg
  (scannorm residual -4.245; whole-piece optimum at dA=-4.0). The
  placer's +-0.75 deg sweep never reaches it AND the seed-candidate
  guard `|seed| <= 1.5` explicitly rejects the correct -4.245.
  Confirmed NOT segmentation-caused: the find_objects fix leaves
  p14's angle/residual bit-identical (hypothesis refuted by A/B).
- p15 (thin sliver, -2.21 deg): channel-marginal. Best admitted window
  0.217; a 0.094 window EXISTS at a grid offset the disjoint tiling
  misses -> an overlapping/offset window grid (pilot-first subsumes it).

**scan-2 p14 pane-B disjoint triangle = ride-along poison from a REAL
bug.** [`src/paperholo/segment.py`] `find_objects` did `comp = lab[sl]
> 0` — takes EVERY label in the bbox slice, not this component. A
-44.7 deg piece absorbed a clipped 162k-px corner of its bbox-intruding
neighbor (mutual: the neighbor took an 89k-px chunk back); the single
rigid placement dragged the foreign lobe to a wrong page location =
1,711 coin-flip cells (GT-BER 0.473, weighted_sum weight 0.465) into 4
otherwise-uncovered LDPC tiles. Latent poison (no certified tile
touched, F9 held; the sid's pilot_ber_est 0.164 earned by the good
lobe hides it). BIGGER incidental, systemic: word-path emission is NOT
mask-filtered — `page_decode`'s `mask=` gates window SELECTION only, so
square window rectangles emit off-scrap cells; piece p4 dumped
6,233+5,403 GT-BER~0.50 cells at weight 0.87-0.91 onto p16's true
territory, ablation-suppressing >=1 certifiable tile (= 1 fountain
symbol). Systemic (scan-1 p1: 8,600 |LLR|>3 wrong cells).

**Constants audit (user challenged the rationale; measured):**
- `MIN_WIN_CORE_CELLS` 8000->6000 WITHDRAWN — 8000 ~= 195 sites sits
  deliberately ABOVE the 016.7 ~150-site decoy-marginal zone; 6000
  ~= 146 lands inside it (spending a measured margin for one piece).
- Seed clamp 1.5->6 deg DEFERRED — no recorded provenance for 1.5, n=1
  motivation; the pilot-first anchor's wide sweep moots it anyway.
- `SPLIT_CORE_CELLS` 20000 preferred as a whole-first-THEN-split
  ORDERING (converts p13 identically, keeps p12 byte-identical, no the
  -14% emission loss the bare threshold caused) — DEFERRED to a
  carve-fixture A/B; pilot-first replaces the whole routing.

**Shipped this session (decoder-axis only, no format change; the
correctness + visualization tier):**
1. `segment.py` find_objects `comp = lab[sl] == li` — root cause. A/B
   both scans: masks shrink only for contaminated pieces, angles/
   residuals unchanged, no routing flips (one cosmetic p9<->p10
   near-tie swap); scan-1 p15's mask was 6% foreign.
2. `acquire.acquire_and_decode` gained a gated `cell_mask` (window-frame
   bool) that rides the identical canonical mirror/rot90 and samples at
   the cell centres (v_row/u_col) to drop off-mask cells from the
   payload `sel`; wired from `formats.page_decode` per-window
   (`nm_full` crop). `None` => byte-identical (every existing format
   unaffected). `tests/test_emission_mask.py`: all-True == no-mask
   (alignment) + partial-drop. Masks GRID windows only, not the single
   folded ID window (small residual, documented). NOTE: fixes both the
   p4-on-p16 class AND is redundant with Fix 1 for the triangle (the
   triangle no longer forms once segmentation is correct).
3. `session_decode._run`: per-piece `decode_tiles(tiles=touched)`
   UNCONDITIONAL at the loop top (panel C advances during the scan, not
   only at end_scan) — must be unconditional, the tests/test_diag
   byte-identity contract forbids diag-gating; `pend` HOISTED above the
   loop (frozen scan-start semantics so mid-scan certs don't shrink the
   placer's search); print `pds.summary()['tiles']` (cumulative) since
   the final sweep now reports mostly skipped_certified. Cost +~15 s/
   scan; one-piece viz lag; per-piece certs are CRC-gated so the fresh
   state may certify slightly MORE than the old single sweep (safe).
   `diag.py`: `close(grace_s=10)` waits until the browser fetched the
   final frame (a `/frame.png` served-counter, `_ever_served` gate = no
   wait headless), and frame numbering CONTINUES past existing frames
   (anti-clobber; a subdir would break test_diag's non-recursive glob).
4. `draw_decode_map`: TAB10->TAB20 (color-collision fix), panel C
   low_coverage YELLOW (was invisible grey), panel D tints
   correlation-placed tiles pale orange + "N words + M placed" title,
   panel B labels `S.P` (scan-feed-rank . piece) on EVERY disjoint
   component (the unlabeled triangle was the misread trigger). Preview
   of the `-after-sheet-1-2nd` snapshot confirms all four: the triangle
   now carries 3x `1.14`, self-explanatory.

**Operational rule (user asked): feed the 1600-decimated scans ONLY.**
`--dpi` is one global per invocation, so 1600+4800 in ONE command
breaks segmentation for the mismatched images. And the 1600s ARE a 3x
decimation of the 4800s (same physical placements, same page cells) —
feeding both double-counts correlated evidence (the measured F1/F6
negative; weighted_sum's disjoint-cell assumption violated) with no
benefit, and raw-4800 is the measured-worse footing (decimate-first
beats it by +13 tiles; 8 px/cell is canonical). If a 4800 scan is a
genuinely NEW arrangement, decimate IT to 1600 and feed at --dpi 1600.

Deferred/coordination: the pilot-first receiver (own branch/session)
replaces this routing wholesale (emission hygiene is a first-class goal
there) — the T2 knob work (whole-first-then-split, per-component
emission gate frozen from a fixture ROC) reconciles at that build.
segment.py:340 may also be fixed on the pilot-first branch — identical
one-liner, reconcile at merge.

## 018.10 — try_3 volume closure (2026-07-13, user run)

**E018 RECOVERED BYTE-EXACT.** The final
`scratch/e018/try_3/e018-session_state.pkl` contains all six decimated
scan basenames (confetti batches 1/2/3, two placements each), 532
certified tiles, and 1,094,138 certified bits. The session emitted
`build/recovered_e018.tar.gz`: 103,195 bytes, sha256
`4c75fe59241499a827293a1c6b9261a306a3936678d46ec78843feea1d17c44d`,
equal to `GOLDEN_SHA` — the printed sheet was reclaimed.

Record correction: repo-root `e018try3.sh` is the template the user used
to build the initial four-scan state (batches 1 and 2), then extended
manually with `decimated-3_1600.tiff`,
`decimated-3-2nd_1600.tiff`, and another repass. It is **not** a complete
literal command transcript of closure. The earlier commit-message wording
calling that four-scan script itself the fully recovered run was inaccurate;
the sheet-recovery claim is nevertheless verified directly by the persisted
state and golden payload artifact above.

## Branch record — pilot-first receiver + mask-aware ctx: MEASURED NEGATIVE, NOT MERGED

Recorded in main 2026-08-06. The work lives on branch
**`pilot-first-receiver`** (pushed to `origin`, 1 commit ahead of main's
base at the time plus the record commit below); it is **not merged and is
not proposed for merge**. Main carries this pointer so the negative is
findable from the experiment it belongs to.

| commit | branch section | what |
|---|---|---|
| [`8ebbf0d`](https://github.com/caronni/paper-store/commit/8ebbf0d17054d5c422983e880eb1fd68d235a22f) | branch 018.10 | pilot-first receiver v1 (`--piece-chain pilot_first`) BUILT + A/B measured |
| [`5bf9847`](https://github.com/caronni/paper-store/commit/5bf9847c40e00e6b34d3883bd2e65e905cf1b4b3) | branch 018.11 | mask-aware ctx+PAVA emission BUILT + **MEASURED NEGATIVE** |

> **SECTION-NUMBER COLLISION — read before merging anything.** This file's
> `018.10` is *try_3 volume closure (user run)*. The branch's `018.10` is
> *pilot-first receiver v1*, and the branch adds an `018.11`. The two
> histories assign different content to the same number. A merge will
> conflict here, and that conflict is correct — resolve it by renumbering,
> not by taking one side.

### What was built (branch)

`acquire._z_normalize` / `cell_bits_blind` / `context_llr_field` /
`cell_bits_ctx` gained an optional `mask` (True = valid core). Quantiles and
the GMM fit are taken over mask cells only; per-context re-estimation
requires all four neighbours ON-MASK and confident; per-context reassignment
touches mask cells only. So backing/off-piece mid-grey can neither compress
the white/ink span nor corrupt an on-mask cell's context. **`mask=None` is
byte-identical** to the pre-change detector, which is what protects the
whole-page word path. `session_decode` gained `--pf-emit {recal,ctx}`.

Unit bars (`tests/test_maskctx.py`, on the branch): exact byte-identity for
`mask=None ≡ mask=all-True`; and on a backing-polluted grid (core 4,900
cells against ~14,700 backing cells sitting dead-centre between the classes)
naive ctx is driven to a coin flip (BER > 0.30) while mask-aware ctx recovers
below 0.20 and never loses to blind. That reproduces **and** fixes the
`segment.py:107` degradation.

### The measured negative

Real scan `scratch/e018/decimated-1_1600.tiff`, fresh single scan, identical
placement, GT from `build/e018_gt`:

| pilot_first emission | certified | symbols | poison |
|---|---:|---:|---:|
| recal (uniform means) | 35 | 31 | 1 |
| **ctx+PAVA (uniform means)** | **35** | 30 | 1 |
| recal (piece_bits @0) | 42 | 38 | 0 |
| anchor word-path | 110 | 104 | 1 |

1. **ctx+PAVA == recal (35 = 35).** Strict-better FAILS — it gains 3 tiles
   and loses 3. Per-window BER 0.224 → 0.214, which is the PAVA-vs-Gaussian
   calibration, not a ctx-ICM gain. The "detector is the 2.5× gap"
   hypothesis is **refuted**.
2. **Why**, and this is the durable part: the ctx gain is
   SAMPLING-dependent — measured 3.5× at 16 px/cell (014.2), while this scan
   is 8 px/cell at c3, where the development nonlinearity ctx exploits is
   weakly resolved. Re-measurable at 16 px/cell or after a lock improvement.
3. `means_at_zero`, needed only to give ctx a means grid at dA=0,
   **regressed placement**: recal 42 → 35 plus a new wrong-placement poison
   (p1/w0 at GT-BER 0.50, 1,256 cells). Requiring a means grid costs
   placement quality.
4. The real gap to the word path's 110 is **upstream** — `lock_grid` +
   `sample_cell_means` (whole-window sub-cell phase lock) produce cleaner
   means than correlation placement + `segment.sample_cells_at` on the same
   piece (0.035 vs 0.09). Sampling/lock quality is the next lever, not the
   detector.

### Status in src/holo (2026-08-06)

The *capability* is present, **re-derived from the E023b line rather than
ported**: `receive/detect.py` `context_neighbour_counts` operates on a
sparse cell set and returns a completeness flag that is False for any cell
lacking a full 8-neighbourhood; `context_bins(counts, valid=…)` maps those
to bin **−1**, excluded from context modelling. Callers:
`certified_refine.py` and `_payload_context.py`. That is structurally
stronger than a mask argument — holo's detector never sees a dense grid
containing backing, so an absent neighbour cannot be sampled as if it were
paper. Support machinery around it: `survey.support_mask`,
`SupportMask`/`SupportRun` in `production.py`, `place._core` erosion, and the
`HISTORICAL_MIN_SUPPORT` gates.

**Not carried over:** the backing-aware z-norm / GMM class statistics. holo
fits calibration on an explicit search/validation split of known sites
(`CalibrationObservations.class_support`), so class statistics are
support-limited by construction instead of by masking a polluted estimate.
The CMY8/QDA path was **not** audited for backing exposure — open question,
not a claim.
