# LAYERS — abstract layer contracts & implementation registry

**v0.4, 2026-07-16** (v0.2 2026-07-07 w/ the cross-engine AltaLink
measurements of 007.6–007.8 incl. the 007.1 retractions; v0.3 added the
layout_version-4 color rows — cmy8-c3 constellation, dust furniture,
site-fit Stage-A rule, e017 FormatDescriptor; v0.4 registers the E018b
fixed-key volume profiles, E021–E023b fragment receiver, physical-capture
evidence semantics, the read-only volume scorer, and the qualified E023c
geometry/sampler factorial). Companion to
docs/DESIGN.md, which stays normative for
*what* each layer must achieve and *why*. This document freezes the **seams**:
the interface each layer presents to its neighbors, the characterization
record every implementation must publish, the registry of implementations
with their measured properties, and the decode-side feedback edges. Goal:
plug-and-play across cell codings, color alphabets, trackers, pilot/addressing
schemes, tile compositions and code rates — with incompatibilities declared
here at spec time instead of discovered silently at decode time. Where this
document and DESIGN.md disagree, DESIGN.md wins and the fix is a DESIGN.md
amendment, never a silent divergence (CLAUDE.md ground rule).

Registry rows carry the measured record with its footing labels. Update rows
when new measurements land; never delete a retired row — retirements with
data are load-bearing facts.

---

## 0. The two plug axes and the FormatDescriptor

Swappability is different on the two sides of the paper, and conflating them
is the classic failure. Every component declares which axis it lives on:

- **Format axis (what is printed).** Constellation, plane set, pilot/strip
  layout, tile geometry, scrambler keying, code rates, strata. Any change is
  a **layout_version bump**: it breaks sha-gated stimulus regeneration and
  must be reflected in the printed bootstrap text (DESIGN §9). Printed sheets
  are immutable; a decoder must be able to select behavior from the sheet's
  layout_version forever. (Precedent: the pilots PERIOD/BLOCK divisibility
  fix is queued as exactly such a bump, not a hotfix.)
- **Decoder axis (how it is read).** Trackers, detectors, calibrators,
  combiners, EM loops. Freely swappable at any time, per scan or per session,
  provided they publish the same characterization metrics on the same footing
  so alternatives stay comparable. Nothing on this axis may require a format
  change to be *tried* (it may require one to *pay*, e.g. training furniture).

**FormatDescriptor** (the format-axis tuple; REIFIED 2026-07-09 in
`paperholo.formats.FormatDescriptor` + FORMAT_REGISTRY — blind receivers
hypothesis-test registry rows via the BCH-gated labeled scrambles; the
scramble is pitch- and geometry-blind, so rows sharing (seed, version,
plane) but differing only in encoding/page shape are separable only by
measured absolute pitch + Stage-B y-neighbor arithmetic — doctrine: no
partial format sharing, every printed sheet gets its own seed. Previously
played per-experiment by
the jobid-keyed manifest + sha-gated generator, formalized at M1):

**E018b declared exception (2026-07-16):** the generic C3/C2 payload-sheet
profiles use fixed public keys
`paper-store/018b-{c3,c2}-r0550-0.5`, registered as `e018b-v3-{c3,c2}`.
The receiver can therefore select the key before payload recovery; the cost
is that the key identifies the FORMAT, not one payload instance. Decoder
state must not combine distinct physical E018b sheets of the same profile;
the sidecar data length + expected SHA-256 bind and verify the volume
instance. This is intentional bootstrap independence, not a security key.

```
layout_version, seed_label,
planes            ("K" | "CMY" | ...),
emission_path     per plane region class (clean_mask | screened_composite),
constellation_id  (+ its parameters: cell_dots or constraint, alphabet),
pilot_layout_id   (site period/block/density) | strip_layout_id (pitch_dots),
training_furniture (band fraction & placement),
tile_geom_cells, code_id + rate ladder per plane/label bit,
strata            ({f_i, plane priority}),
scrambler         (AES-CTR keying convention = paperholo.modulation.keystream)
```

---

## 1. Interface currency — shared data types and conventions

Frozen conventions live in experiments/002-calibration-page/ANALYZER-CONTRACT.md
§1 (coordinate frames, affine convention, ink-is-dark, `[y, x]` indexing,
corner-aligned resampling) and CLAUDE.md (units in names, all randomness via
`paperholo.modulation.rng/keystream`). Types that cross layer boundaries:

| type | shape / units | producer → consumer |
|---|---|---|
| PlaneBitmap | uint8 dot grid, ink=1, layout dots | L1 encode → L0 emit (psgen) |
| ScanSet | list of physical captures, each with stable `capture_id`, source sha256, true DPI, mode, and compression class; **one scanner mode per member; modes never mixed for absolute y**; block-coded (JPEG) members change detector choice (§3). Deterministic resamples retain the same `capture_id` and are not additional scans | L0 acquire → L2/L1 |
| CaptureView | one deterministic representation of a physical capture: `capture_id` + `view_id` + exact derivation/kernel/coordinate transform + raster sha256. Views are correlated hypotheses; `view_id` is provenance, never an independence claim | L0/decoder preprocessing → L2/L1 |
| WarpField | global affine [a..f] + per-row dy profile (steps preserved) + local offsets; layout dots → scan px | L2 geometry → L1 sampling |
| Address | (plane, page, tile_yx, cell_yx) absolute; orientation/mirror resolved | L2 addressing → L1/L3/L4 |
| CellFeatures | per-cell feature vectors (density-domain channels, aligned per plane; optional grey feature) | L1 sampling → L1 detection |
| LLRs | float per label bit per cell (binary: one; alphabets: log2(states) MLC label bits), **PAVA-calibrated (BUILT 2026-07-09: pilot cells of decoded tiles are the on-page labeled set — isotonic score→P map fitted per window, acquire calibrate=True; measured reliability within 0.07 per confidence bin, 014.2)**. Combining by summation is legal only across independently acquired physical captures. Deterministic views of one capture may be selected as one vote or retained as separate decoder hypotheses, but never summed as independent evidence (E023b multiview, 2026-07-16). **BOUNDED-LLR INVARIANT (2026-07-11, 018.7): raw detector scores never cross an API boundary — every emitted LLR is calibrated (PAVA clamp ⇒ \|LLR\| ≤ ln(n_labels+1)) or explicitly bounded. Three incidents forced it: 017.6 PAVA cross-fit scale; the K-path <300-label gate leaking raw GMM scores (σ-floor ⇒ \|LLR\| to ~5e5 = a 70,000× union dictatorship, self-selecting for drifted windows; fix MIN_CAL_LABELS 60 + rescale fallback, measured +9 symbols on the e018 session); repass's dense recal clips ±12 by design** | L1 → L3, L3 extrinsic → L1 |
| TileResult | payload bytes + CRC verdict, or erasure; + decode diagnostics | L3 → L4 |
| ESI | = F(plane, page, tileX, tileY), fixed public bijection; no headers (decision 2026-07-06) | L2 geometry → L4 |
| ChannelParams | see §2 | CAL/DISC instruments → simulator, detectors, rate ladder |

Tile taxonomy (2026-07-10 ruling — one name per object, "tile" never bare
across layer boundaries): **pilot tile** = the P×P-cell unit (60×60) of the
pilot lattice whose 100 sites carry ONE BCH word — supersedes the synonyms
"period tile", "word tile", "tile slot" found in pre-ruling logs and
docstrings (same object; historical experiment logs are not rewritten).
"Word" alone = the BCH codeword (content, never geometry); "period"/P =
the 60-cell repetition length only. **LDPC tile** (= payload tile) = the
64×64-cell inner-FEC unit, one codeword + CRC = one fountain symbol. The
two grids are deliberately misaligned (PILOTS-DESIGN §6.6); code
identifiers (`ptile_y`, `period_cells`) keep their names.

Measurement discipline attached to every number that enters a registry row:
null control (shifted-GT BER 0.50±0.02), canary verdicts as
{pass, fail, indeterminate} + statistic + control, and a **footing label**:

```
footing = (geometry, training)
geometry ∈ { genie-warp, marks-affine, marks+strips, fully-legal }
training ∈ { labeled(GT), furniture(on-page bands), blind }
```

Rate currency: calibrated MI in b/cell (or b/dot), and b/mm² = MI × density.
Rate-ladder decisions use **multi-sheet minima**, never best-sheet numbers.

---

## 2. L0 — physical channel

**Service to L1:** per-plane reflectance rasters of what a bitmap became,
plus the characterization record that parameterizes everything above.

**Characterization record = `ChannelParams`** (implemented:
src/paperholo/channel/simulator.py — `PlaneParams`, `PrinterParams`,
`ScannerParams`, screens, crosstalk matrix). Key fields per engine: native
dpi per axis; per-plane PSF sigma, edge gain (V/H), dmax, morphology
(min_ink_run_dots, min_white_run_dots, white_fill_below_dots), registration
drift, mottle vs coverage; printer wander + y-scale; scanner steps + comb +
mode-dependent y-scale; screen (lpi, angle) per plane; density-domain 3×3(+K)
crosstalk matrix + condition number; paint-path fidelity classes.

**Paint-path enum (PER-ENGINE — the 002.0–003.0 "no PS escape" freeze is
M281-specific, 007.6):**
`clean_mask` — single-plane imagemask; bit-faithful on BOTH engines (M281:
C/M/K clean, Y carries a native 224 lpi texture; AltaLink: all four planes
clean, sharper dot rendering); `screened_composite` — M281: any region with
>1 plane, contone re-screened ~165 lpi, always, no PS escape; **AltaLink:
P0/P3(OPM)/S1/S2/S3 are ALL overlap-preserving AND unscreened at 600-dot
resolution (textbook Adobe overprint; bare masks P1/P2 knock out on both
engines) — composite c3 tax ≈0 for C/M, +6.5 pp Y crosstalk**; `dead` —
content addressed off the engine's real grid: M281 grants 1200 but
y-stretches (007.6 retraction: the recorded "granted-1200 degrades
600-addressed c3 12×" was a scorer artifact — real delta +0.9 pp); AltaLink
refuses all requests (fixed-600 PS device) and point-samples 1200-addressed
content onto its 600 grid (24–26% deterministic alias floor).

**Instruments (producers):** CAL-1 (`params_from_calpage_report`; per-engine,
per-media, re-run on consumable change), DISC-1 (portable two-page discovery
for unknown engines; validated blind against the M281 in 007.1), MSEL-1
(exp 008, 2026-07-07: portable two-page MODE-SELECTION sheet — portfolio
fields + morphology + emission probes + scanner-adequacy block + MIC
gating-control pair; pre-registered rules R1-R7 emit robust-K/dense-K/CMY
recommendations; M0-gated on the measured simulator, awaiting first
shakedown print).
**E025 physical-channel metrology (FORWARD DESIGN BUILT + SYNTHETIC-
PREFLIGHTED 2026-07-17; physical print pending):** `paperholo.metrology` +
`experiments/025-channel-metrology/` preserves
`(authored dpi_x/y, requested dpi_x/y, read-back dpi_x/y, c_x/y,
constellation, symbol shape, emission path)` as exact identity. Separate
layout-v2 one-page K-only and color jobs carry two live CRC device strips; independent
physical-ink and C2 payload-safe edge probes; chiral pose, internal warp and
x/y phase instruments; fixed-level full-width profiles plus permuted tone
response; controlled paper witnesses; typed H/V frequency, morphology,
holes/dots, slanted-edge and microprint probes; large balanced state fields;
equal-pitch authored-grid controls; and small real house-LDPC compatibility
coupons. Color adds distributed CMY-to-K registration and feed-direction
profiles; K adds C2 motif/aspect controls, and color adds KCMY4. Raw held-out
BER/MI and optional full traces are primary;
FEC confirms code-path compatibility rather than standing in for channel
physics. Analysis derives the usable rectangle from measured edge canaries and
reports raw/MI/coded capacity there. Profile kinds remain
emitter-through-reference-scanner, same-physical-sheet sensor, and exact
pipeline; hints are advisory. Current QDA footing does not automatically
certify E023b/E024 or another production detector. The superseded rate-column
atlas remains only in Git history and the reasoning log.
**Reference implementation (consumer):** the measured simulator
(`print_plane`/`scan_plane`/`rescreen_plane`/`planes_to_rgb_refl`) — every
new layer implementation must round-trip on it before toner (M0 gate).

**Sampling floor (cross-engine fact, 007.2/007.3):** decode is synchronized
sampling of a known lattice — 1 px/cell works while the cell fundamental
stays below scan Nyquist, and dies by aliasing once it crosses. px/cell
ladder: **6 solid, 4 marginal, 2 Nyquist-edge, <2 dead.** Corollary: a
printer's resolution advantage is cancelled by its own undersampling scanner
(office-printed 1200 content through the office 600 scanner is structurally
useless: c2@1200 sits AT Nyquist, c3@1200 aliases).

**Registry:**

- **M281 "<host>" (home)** — measured, frozen (defaults in simulator.py,
  CAL-1 2026-07-04). Scanner: home flatbed 1200 dpi — y-only scale
  instability, stochastic y steps, 18.63 mm CCD comb.
- **Xerox AltaLink C8245 (office; print side MEASURED 007.6–007.8, full
  ChannelParams draft via params_from_calpage_report — PlaneParams only,
  geometry/morphology/screen models still M281).** PRINT: fixed-600 PS
  device (RD=RE=600, ALL RQ300..2400 refused; spec 1200×2400 unreachable via
  PS; PJL/PCL untested); K ladder M281-class (c1 dead, c2 ~12%, c3 2.5–3.5%,
  c4 solid); print-to-print Δc3 ≤0.6 pp; healthy CMY (Y solid D 1.35, rate
  0.67, plane drift 5× tighter, cond(A_cmy) 1.83); K solid lighter (D 1.09);
  edge gain LOWER and FLIPPED H>V (M281 V>H — anisotropy is engine-specific);
  1-dot LINES resolve, isolated 1-dot DOTS dead on both engines; Nyquist
  closure + min-white-3 are cross-engine invariants; white closures MORE
  terminal (ctx-detector gains field-dependent, §3); RET-like edge
  thickening ON; new ~30 mm gear-train y-ripple family (attribution pending
  rotated scan); margins ≤4 mm (both engines — disc1 probes; CAL-1's ≤7.4
  was never probed lower); x-scale TRUE (2.0000 px/dot). **MIC: yellow
  tracking lattice on pages with COLOR CONTENT** (24×24-dot square cell,
  ~31×16-cell super-tile, ≤~360 bits payload, 0.24/mm² = 6.3× below pilot
  dust — channel-absorbable but NOT anonymous; K-only pages clean; 007.8
  corrected 007.7's render-mode-gating claim). SCANNER characterized (007.2
  + addendum, same-sheet pairs): scale +0.2–0.6% NEAR-ISOTROPIC, strips
  lock 1.00 (color path needs 2× upsample before stripdec), residuals ~1.7×
  home; binding impairment = DEFAULT JPEG (tiff_jpeg ~0.075 bpp): erases
  <5-dot features, costs c2 ~+6 pp / RLL +1.3 pp strip-tracked, breaks the
  context detector (§3). Verdict: scanner = triage/self-ID unless JPEG can
  be disabled; printer = full second engine, delivered the healthy LOOP-C
  number (90.3 b/mm² rgb-only) and the A3 record sheet (133.3).

Plug status: this seam already works end-to-end; it is the model for the
others.

---

## 3. L1 — modulation + detection

Two paired halves. The **constellation** is format-axis; the **detector** is
decoder-axis. They are separable (any detector may be tried on any printed
constellation) but characterized as pairs.

**Constellation contract (format axis).** Declares: `constellation_id`;
track (clean_mask | screened_composite); plane set; geometry (cell_dots per
axis, or free-form + 2-D constraint); alphabet + bit mapping (MLC label-bit
order for alphabets); entropy b/cell (or b/dot); emitter (imagemask vs
put_cmyk_bitmap via psgen); GT generator (sha-gated, byte-identical);
**requirements**: sync class needed (see §8), training furniture fraction,
scan mode. Encode: `bits × keystream → PlaneBitmap(s)`.

**Detector contract (decoder axis).** Input: ScanSet + WarpField + Address
(for keystream/furniture alignment) + ChannelParams priors + optional
extrinsic LLRs (M2 turbo). Output: LLRs (calibrated), hard decisions,
diagnostics (MI, confusion, per-class stats, canaries). Must run blind — GT
enters only as a scoring instrument. Must be re-invokable with updated priors
without double-counting (extrinsic separation) — this is what makes the §7
feedback edges legal. EM-style detectors must initialize from on-page
furniture or a fresh CAL, never stale priors (006.2 measured failure: −0.22
b/cell from a consumable-drift-stale crosstalk init). Detectors also declare
their noise-model assumptions: the 16-context ICM assumes print-side
development-context error structure and MISFIRES on JPEG block-coded scans
(007.2 addendum: ctx 20.6% > hard 19.0%) — on compressed office scans use
hard/global detection.

**Characterization record fields (the datasheet per pair):** raw BER (hard /
context / soft), MI b/cell recal'd, b/mm², footing, multi-sheet min↔max, day
fragility class, multi-scan response, training cost, known failure canaries.

**Registry — active candidates (numbers = genie-warp unless noted):**

| id | construction | channel | headline (best, labeled) | multi-sheet range b/mm² | fragility / notes |
|---|---|---|---|---|---|
| B1 | K solid cells, cell=2 | clean_mask | AltaLink e004: ctx 5.48%, recal 0.760 = 106.1 genie (007.6); home day-1 ctx 4.59%, 0.785 = 109 (003.0a). LEGAL strips-alone: AltaLink single-scan 7.32% / 94.8 (007.6); home 3-scan + between-strip refi 79.7 (007.7) | ~93–109 genie; 68–95 legal | day-FRAGILE on M281 (white-cell closure, page-edge structured — 004.0 day-2 8.15% / 92.8); AltaLink one-day point: miss HALVED, fa-dominant 2.15:1, page-edge penalty ABSENT (was M281 print-side); c2 = the channel canary. CTX-detector gains are engine/field-dependent (§3) |
| B2 | K 2-D RLL i2w3 free-form | clean_mask | 0.167 b/dot = 93.3 (4-scan, 004.0b — best ever) | **82–86 CROSS-ENGINE band** (3 sheets, 2 engines — the rate-ladder anchor); 82–93 overall | stationarity champion, now CROSS-ENGINE stationary to 3 sig-figs (AltaLink 13.65% / 83.1, 007.6); dot-dropout mechanism replicates on engine 2 (NOT engine-specific). Trellis gain ≈ ZERO (004.0a); motif-emission upside bounded ~98. No self-clock at 2 px/dot |
| A3 | 7-state CMY alphabet {W,C,M,Y,CM,CY,MY}, cell=3 | screened_composite (M281) / clean composite (AltaLink) | **AltaLink cross-tile 2.150 b/cell = 133.3 (007.6, RECORD)**; overlap2-sheet single-position 137.3 = same distribution (007.8-C3); home 1.896 = 117.6 (004.0). Loop-legal full page: 1.456 rgb-only = 90.3 (007.7/8). +grey 4th feature: M281 +0.03–0.09, AltaLink −0.014 (rgb-only wins, 007.8) | ~92–133 (MI 1.48–2.15) | largest sheet/day swing; Y-entangled (starved-Y 47.7, 006.2). Gain on engine 2 concentrated in Y-bearing states; Y-axis confusions at the QDA-family ceiling — non-Gaussian detectors untested, then Y-carrier design item (007.8-C2). Furniture-trained = genie parity on BOTH engines; loop receiver = furniture-QDA, NO EM (007.6). Composite page-position stationary to 0.006 b/cell (007.7). Warp legality OPEN on M281 (screen contaminates self-clock); AltaLink composite is unscreened → self-clock viability there untested |
| A4 | {7+K} 8-state, cell=4 (+grey feature) | screened_composite (M281) / clean composite (AltaLink) | AltaLink cross-page 2.685 = 93.6 (007.6); overlap2 {7+K} cross-tile 97.7 (007.7); home 2.458 = 85.7 (004.0) | ~69–98 | stable middle of track A; AltaLink weakness: K↔CM confusion ~9–10% (honored-overprint dense CM approaches K in RGB space, 007.6) |
| cmy8-c3 (layout_version 4, encoding kind cell_mlc) | 8-state CMY presence bits, cell=3, one bit per LEVEL per cell → 3 per-level LDPC codewords/tile (PID-MLC, COLOR-DESIGN D1/D2); + TRAINING-DUST furniture population (18/tile = 0.5%, pure-quota 3, P3-frozen — labels/registration/PAVA/consumable canary, no message bits) | screened_composite (M281) / clean composite (AltaLink); put_cmyk_bitmap emission | SIM/BUILD stage (exp 017, zero print): P5 per-level BER at the pessimistic 2 px/dot footing home C 5.3/M 4.3/Y 8.9%, office 2.9/2.8/6.4% (cross-tile QDA); rungs FROZEN C r0550/M r0550/Y r0547; e017 sheet net 72.1 b/mm² at provisional rungs, projection 91–103 measured / 108–117 Canon-est | UNPRINTED — no hardware row yet | detector = dust-trained 8-class full-covariance QDA → per-level LLRs, PAVA in-sample on dust labels with a zero-anchored map (017.5: the cross-fit variant retired with data — half-model/full-model score-scale mismatch latched whole levels at 50% on clean crops; COLOR-DESIGN D4); per-plane offset model (global + linear-in-y) from pure-plane dust anchors (D5, P4-confirmed both engines); acquisition on LUMA with the P1 site-fit rule (see §4 pilot row). KNOWN SIM RESIDUAL: sim per-level order INVERTED vs hardware (COLOR-DESIGN §3) |

**Registry — retired with data (do not reopen without new physics):**
cell=1 (dead, 001); 4-level per-plane and CMYK16 (MI-rejected, 002.0);
i2w2 (18% vs grid c2 11%, 003.0); i3w3 (0.120 b/dot < i2w3 0.147 — entropy
cost dominates, 006.1); grey3 c3+c4 (MI 0.55/0.93 ≪ binary, 006.1); fill75
(no benefit at balanced-error state, untested vs a closure day, 006.1);
K as 8th symbol at c3 (net loss, 002.0c). Curiosity kept warm: aniso 2×3
tall cells 11.69% vs c2 13.6% on the same warp, ceiling 93 cells/mm² (006.1).

---

## 4. L2 — synchronization + absolute addressing

Two services with separate contracts; both fiducial-free on archive sheets.

**GeometryTracker (decoder axis).** Input: one scan (+ plane channel) +
whatever format-axis anchors the sheet carries (marks on scratch sheets,
strips, pilots at M1). Output: WarpField + lock diagnostics (per-window lock
quality, residual RMS dots, step catalog). Properties to publish: payload-BER
gap vs genie (pp), residual dots, coverage domain (interior/edge), anchor
requirements, px/dot floor.

| id | anchors needed | status / measured record |
|---|---|---|
| genie (GT xcorr) | GT | instrument only — defines the genie footing |
| cal_core marks affine + local template locks | corner/plus marks | frozen (ANALYZER-CONTRACT); rms ~1.5–2 dots global, ±2 dots unrefined; ≥3 corners for orientation; strip pages use refine=False |
| scanlab v4 dense patch warp | GT templates or furniture, patch-scale | measured since 001.4: poly2 + step-preserving y-profile; the reference for patch decode |
| strip_tracker | printed known-c2 strips, 360-dot pitch | lock 1.00 on all real scans BOTH engines (006, 007.6); strips-alone costs +5.82 pp ctx vs genie home / +3.37 pp AltaLink (same mid-gap shape) — linear interp leaves a true mid-gap BOW up to ~2.3 dots (007.7, GT-instrumented) |
| dd_warp self-clocked band tracker | payload itself + mark residual anchors | interior tiles ≈ genie or better (T14 10.45% vs 11.76%); FAILS page-edge (transport-acceleration zone); c2 branch ambiguity needs anchors+DP; naive cross-plane phase pooling measured BROKEN (per-plane registration bias) |
| between_strip.py refinement (007.7) | strips + payload self-clock (y-bow, dd_warp phase anchored at bracketing strips) | BUILT, engine-CONDITIONAL: home +1.6 pp single / +2.05 pp 3-scan combined (B1 79.7 b/mm², beats 4-scan strips-alone 73.5; closes ~35% of the gap); **AltaLink HARMFUL −4.5 pp** (<5-dot erosion weakens the c2 lattice). Overlay only — needs a legal PER-BAND SNR go/no-go gate + preflight before wiring (007.8-C4; constants tuned once vs same-sheet genie, broad optimum) |
| pilot-anchored tracking (`paperholo.acquire`) | p60b6.v2 pilot lattice (2.78%) | BUILT + SIM-MEASURED (011.0, layout_version 2): fully blind end-to-end **+1.97 pp** payload BER vs the detector-matched geometry=False footing on 600×600-cell windows (vs strips-alone +5.8 pp / between-strip +3.4 pp measured hw) — supersedes strips on the sim; stages = tiled gradient-FFT lattice lock w/ separable phase profiles + DD refinement, pilot-WORD ±1-cell slip voting (integer slips; template anchors measurably cannot), 2-round sub-cell pilot anchors (dy,dx both; dx never self-clocked); multi-scan majority replicates at L2 (5.80→2.12% on the adversarial warp seed — SIM, marginal-BER regime; on hardware healthy-c3, 012.3 measured equal-weight majority LOSING to best single: print-frozen correlated errors). **HARDWARE-MEASURED 2026-07-09 (e012 run 012.3, layout_version 3: AltaLink print, Canon 1200/2400/4800 scans): blind payload BER 0.64–3.97% (envelope PASS ≤8%; best = 8 px/dot, below the genie c3 anchors), pilot-tile word decode 100%, orientation+addressing blind unanimous across 3 resolutions; anchor stage near-no-op on the clean Canon channel (rounds=0 1.74% vs rounds=2 1.77%); post-fold word-certification gate + anchor_rounds=0 skip added (suite 228).** Single-pilot centroid noise still unextracted (open 012.3 item); PILOT-1/M-P3 comparison sheet still owed |
| local pilot-field observation pose (`paperholo.pilotsearch`, E022) | E021 region mask + global pitch + optional angle hint + p60b6 field | **v2 BUILT + MEASURED 2026-07-14 (supersedes the v1 similarity fill-in):** every WINDOW measures its own full 2x2 Jacobian — the two lattice fundamentals of the window's gradient spectrum, zoom-DFT sub-bin, invert to rotation + anisotropic scale + shear, blind mod 90, no angle seed; sub-cell phase by 1/8-cell grid + quadratic subpixel; sampling = one box prefilter per region crop + one order-1 subpixel read per pose-mapped cell centre on the ORIGINAL raster (no rotation, no predecimation; 23.85 px/cell sampled as 23.85). Pose battery (GT-affine renders, hints withheld): rotations 0-44 deg x subpixel x aniso ±0.4% x shear ±0.25 deg at 8/11.7/23.85 px/cell all exact, worst mapping error 0.199 cells (0.029 at native 24). Full pose propagates as a neighbor prior (rot90-aware algebra pinned by test); scanner y-step -> pose components; fold -> two measured angles in one continuous component; straddle audit (min-binomial-impurity change-point) strips minority-side emission |

**AddressResolver (format+decoder axes).** Input: locked lattice + candidate
region. Output: Address + orientation/mirror disambiguation. Properties:
acquisition grain (mm² of clean area to first fix), overhead %, raw-BER
tolerance, bootstrap independence.

| id | overhead | status |
|---|---|---|
| jobid manifest (experiments) | n/a | not archival — bench harness only |
| machine strips (stripdec, LAY=1) | ~2 strips/page | measured, CRC'd, portable (007 self-ID on both layers); coarse-module, human-adjacent |
| pilot window code (`pilots.coordinate_code` / `paperholo.bch`) | exactly 2.78% cells (p60b6.v2) | IMPLEMENTED + SIM-MEASURED (011.0, layout_version 2, golden-anchored in tests/test_format_v2_golden.py): 36-bit words in shortened **BCH(127,64,t=10)→(100,37)** (PILOTS-DESIGN v0.1's (127,36,t=15)→(100,36) was impossible — v0.2 §6.2), t_acq=8 Stage A + clean-tile Stage B, site-local scrambling; MEASURED: false accept 0/200k random words (≈2.3e−8/hyp est.), page-scale decode 80–81/81 tiles, orientation resolution free (all wrong rotations BCH-rejected), grain 15.1 mm placement-guaranteed / 13 mm ≈60% / 10 mm below grain at c3@600; c2-class words need the M-P6 duplication (t=10 tail ~18% at 8% ctx BER — load-bearing, not margin). **REAL-SCAN MEASURED 2026-07-09 (v3 code, e012 run 012.3): pilot-tile word decode 100% on every ~40 mm window (20/20; 16/16 at the 4800 off-center), 3 scan resolutions, ~1 corrected error/word typical (werr 9–19; 63 at the worst-position window); 13 mm+ fragments acquire, 10 mm fails Stage A (matches sim grain); 0 false accepts observed anywhere incl. the phantom-GT incident (50% payload never produced a wrong certification)**. **layout_version 4 (color, exp 017 — sim-measured, unprinted): SAME machinery + sites + code; format identity = the v4 value-scramble label alone (C_v4 == C_v3 as codes; cross-rejection verified in tests both ways vs v3 AND v2, same seed); word rendering = fixed CM 2-ink, P1-frozen; one DECODER-AXIS rule (017.2): on n_levels==3 specs every pilot-word bit read comes from a pinned 2-GMM fit on the gathered WORD-SITE population, never the whole window (P1: the all-cells fit costs up to 2× word BER on mostly-ink pages; K path byte-identical)** |
| pilot-field correlation resolver (`paperholo.place` + `paperholo.pilotsearch`) | same pilots | **v2.1 BUILT + MEASURED 2026-07-14 (E022; supersedes v1's numbers):** correlation primary for arbitrary partial/straddled windows — disjoint SEARCH/VALIDATION parity sites end to end (the v1 neighbor route violated the split), padded edges, four-page legal rivals, SITE-granular `need_mask` (cross-scrap halves of one tile union and decode; the tile-granular form measurably rejected the fill scrap), rim-eroded audited emission, honest rival provenance, retry ledger on unresolved windows. Exact synthetic 12/12 across rot90/four-tile straddles/non-zero pages; adversarial nulls 0/49 FA over 784 field hypotheses; wrong seed refused. One dense BCH word retained as a field-validated ~3.2x fast start; known-position reads at FULL t=13 erasure strength (the (26-f)//2 call was a live bug: clean words with >6 erasures could never decode). **FULL-SESSION RESULT (6 scans each footing, user run): the COMPLETE 925/925 pilot-tile map of the e018 sheet at BOTH native-4800 (868 matching words / 0 contradictory / 22 refused) and decimated-1600 (877/0/13); footings agree, and at E022 placement/addressing decimation is a smaller input only. E023b later measures payload/LDPC complementarity, so this is not a whole-receiver equivalence claim.** MEASURED OPEN: sub-100-site scraps refuse honestly (rival floor 0.166 at 61 parity sites vs the 0.20 bar frozen at >=135); gates inherited-then-validated. No LDPC/CRC backstop exists inside E022 |
| syndrome blind sync | zero | research variant (§5.2c), fragile at high BER |

---

## 5. L3 — inner FEC (M2; K-binary production path built)

**TileCodec target contract.** Input: LLR array per label bit over one tile
(tile_geom_cells, nominal 64×64) + Address. Output: TileResult (payload+CRC
or erasure) + **extrinsic LLRs** (for the §7 turbo edge) + soft diagnostics
(pre/post-decode MI, iteration count). Config (format axis): code family +
rate per plane *and per MLC label bit* (alphabets decompose into label-bit
channels of different quality — the leading M2 frame), tile geometry,
interleaving local-only (fragment locality, DESIGN §6).

Duties beyond decoding: **codes certify registration** (2026-07-06 doctrine)
— a CRC-passing decode is the terminal validator for geometry/address
hypotheses (§7, edge F9); erasure semantics must be honest (a failed tile is
an erasure to L4, never a guess). Rate ladder set on multi-sheet minima.

The current K-binary implementation exposes the certified-payload subset of
that contract; it does not yet emit turbo extrinsic LLRs.

| implementation | measured status |
|---|---|
| `paperholo.payloaddec` / E023 | BUILT + QUALIFIED 2026-07-15: per-window pilot PAVA, one-owner-per-scan emission, max-60 hybrid BP, staged per-scan certificate union then changed cross-scan calibrated-LLR sum; syndrome+CRC certificate; 741/740 decimated/native, zero wrong |
| `paperholo.receiver` / E023b.0 | BUILT + QUALIFIED 2026-07-15: persistent atomic E021→E022→L3 composition, every scan prefix evaluated independent of CLI batching, immutable attempt/evidence ledger; 742/742, zero wrong |
| E023b.1 arms | QUALIFIED 2026-07-16: opt-in pilot-only `ctx-pava-v1` and explicit current-frontier max-150 BP. PAVA/BP/context/combined = 742/747/749/757 decimated and 742/747/746/752 native, all certificates correct |
| E023b correlated-view list | QUALIFIED 2026-07-16: native and exact-box3 views remain separate physical-capture-correlated hypotheses; conflict-checked certificate union 769 = 740 shared + 17 decimated-only + 12 native-only. LLR-level one-vote fusions reached at most 763 |
| historical E023c geometry/sampler factorial | NUMERICAL ARM QUALIFIED 2026-07-16: NN/DD/ND/DN = 752/757/749/756, conflict-free union 772, all GT-correct. Decimated geometry improves both samplers; DN has lowest BER. Four-lane cost 4,470 CRC calls / 242,555 BP iterations versus 2,226 / 119,790 NN+DD. This qualification-only frozen-inventory runner predates and is not the production cascade |
| `run_e023c.py` / production E023c | BUILT + SINGLE-CAPTURE QUALIFIED 2026-07-17: native-first E021→E022→E023b coarse-to-fine entry point; authenticated persistent multi-capture state, direct-native scale views, current-pixel hint gates, independent correlated lanes, certificate-only barriers, residual NeedMap, atomic resume, real payload/SHA completion, and four-pane diagnostics. HP C3 2→3→6 = 671+74+9 = 754 certificates / 731 useful; HP C2 2→4 = 1,310+128 = 1,438 / 1,363 useful. All certificates correct and conflict-free, both payload SHAs verify. Scope is one HP-1200 capture per format, not cross-scanner generalization |
| `paperholo.feedback` / E024.0 | BUILT + OWN-BRANCH/UNION-SEEDED NUMERICALLY QUALIFIED 2026-07-16: persistent append-only certified-feedback overlay over immutable current E021.6 E023b states; target-safe dependency closures, supersede-never-sum evidence, weighted PAVA/context and bounded pose factorial, changed-frontier BP, exact sequential durable replay, and observer-only four-pane diagnostics. Own control/recal/refine/combined = 757/758/759/759 decimated and 757/757/762/761 native; with the trusted 770 union = 770/770/772/772 decimated and 770/770/770/770 native. All correct and monotone; `refine` wins. HP E018b current-stack validation: standalone C3 730→734 (+3 useful/+1 inert), C2 1,416→1,423 (+0 useful/+7 inert); after production E023c C3 754→754 and C2 1,438→1,439 (+1 useful). Both post-cascade v2 audits are exact-artifact `QUALIFIED_BOUND`; broad feedback has sharply diminishing return |

## 6. L4 — outer erasure layer (M3; E018b fountain-v1 path built)

**VolumeCodec contract.** Input: set of (ESI, payload). Output: files +
verify hashes. Config (format axis): RaptorQ params, K_sym per stratum
{f₀≈0.02 catalog on C/M, f₁ critical, f₂ bulk on Y} (DESIGN §7.3). ESI is
geometric — no headers exist anywhere; tile coordinate headers were
considered and rejected (2026-07-06): geometric ESI gives addressing free,
and headers cannot bootstrap.

`paperholo.fountain` implements the current deterministic `fountain-v1`
encode/rank/decode path used by E018b. `score_e023b.py` is a read-only
adapter from one E023b state plus its matching manifest to actual fountain
rank and final payload length/SHA verification. It is outside E023b's
authoritative state and does not define that receiver's stop condition. The
general stratified RaptorQ/bootstrap protocol remains a later format/system
layer. The scorer does not yet consume E023b's terminal multiview-union JSON.

---

## 7. Decode-side feedback edges (the loop registry)

The retrieval stack is feed-forward for data but bidirectional for *beliefs*.
Every feedback consumer must accept updated priors without double-counting
(extrinsic separation). Current edges, innermost first:

| # | edge | boundary | status | evidence |
|---|---|---|---|---|
| F1 | context ICM: detector's own decisions define per-4-neighbor contexts, iterated | inside L1 detect | **BUILT INTO THE RECEIVER 2026-07-09 (acquire detector="ctx" + PAVA calibrate=True; 014.2)** — gains are SAMPLING-dependent, not engine-dependent: 007.6's AltaLink no-gain verdict was a 2 px/dot artifact | c2 11.2–11.4% → 5.0–5.4% day-1 (001.4); misfires on JPEG block channels — hard/global there (007.2); 007.6 AltaLink encode-c2 rescue "fails" at 2 px/dot (12.7→11.0) but **014.2 at 16 px/cell: 7.9→2.6% on the same engine's print** — the residual signal ctx needs is resolved at high sampling; mechanism note: the per-context pinned-2-GMM captures class SHIFTS, not within-class bimodality — terminal (fully-toppled) cells stay unrecoverable (test_ctx_calibration negative pair) |
| F2 | EM-GMM class re-estimation for alphabets | inside L1 detect | measured — DO NOT USE for the loop receiver: furniture-QDA, skip EM | blind gap 0.065–0.098 b/cell (004.0a); stale-prior init −0.22 (006.2); 007.7: EM walks away even from truth-derived furniture centroids (−0.43 MI vs QDA on engine 2) |
| F3 | residual → y-profile/step re-estimation | inside L2 (v4) | measured, in use | stepped-warp decoder (001.4); smooth-only model concentrated ~half of errors at step crossings |
| F4 | decision-templated warp refinement (payload decisions anchor tracking between strips) | L1 → L2 | BUILT 007.7 (between_strip.py), engine-CONDITIONAL — see §4 row; per-band gate pending | 004.0a; 006.1 gap +5.8 pp; 007.7: home +2 pp multi-scan, AltaLink harmful |
| F5 | decision-directed ISI cancellation (3×3 taps) | inside L1 | measured NO GAIN on this channel — negative result, keep off | 004.0a (errors are feature dropouts, not additive ISI) |
| F6 | multi-scan accumulation until converged | L1 quality → L0 acquire | protocolized: 3–4 scans, re-place sheet between scans; **BUILT 2026-07-09 as PageDecodeState multi-scan observations (paperholo.tilemap): per-scan evidence never pre-summed, merge policies best_scan/best_per_tile (coverage-aware)/pilot-agreement weighted_sum/sum-baseline; "until converged" is now EXECUTABLE — more_scans_useful() asks the operator for another scan while tiles are uncertified AND the last scan still gained coverage/confidence, stops on certification or diminishing returns (014.2 live demo). E023b sharpens "scan" to physical capture: independent capture ids may sum; native/decimated or other deterministic views of one capture may only supply one vote or separate decoder hypotheses, never an independent sum.** | 004.0b (+12–15%, diminishing returns after 3–4; placement diversity beats repetition 006.1); 012.3: equal-weight majority LOSES to best single on healthy c3 — hence policy-per-tile; **014.2: combining starts BEATING best-single once the ctx detector removes the correlated context bias (A+B+C ctx equal-sum 1.37% vs best single 1.71%) — F1 and F6 COMPOSE, order matters. E023b: correlated native/box3 certificate list 769 vs best legal LLR fusion 763.** |
| F7 | pilot site-phase hypotheses validated by window-code decode | inside L2 | designed (M1) | DESIGN §5.2a; ≤P² hypotheses |
| F8 | turbo equalization: LDPC extrinsic LLRs re-enter the detector | L3 ⇄ L1 | designed (M2) | DESIGN §6 ("cheapest +1–2 dB") |
| F9 | CRC-passing decode certifies geometry/address hypothesis | L3 → L2 | **BUILT 2026-07-09 (tilemap): certified tiles re-encoded and pinned ±inf in the payload-LLR overlay + exposed in the detection domain (known_cell_values, keystream-correct — verified exact vs the printed page); post-fold word gate in acquire is the L2-internal seed** | "codes certify registration, pilots/strips measure it" (2026-07-06) |
| F10 | decoded cells become training data → channel/detector re-estimation ("decoded-tile bootstrap", blind-cal EM) | L3 → L1/L0-estimate | designed | DESIGN §9 calibration-without-marks; named in 004.0a |
| F11 | verify-on-write: print → scan → full decode before trusting | system, write side | doctrine | DESIGN §9.1 |
| F12 | orientation/mirror trial: keystream correlation fails ⇒ flip and retry | inside L2 | designed; chiral corners implement it on scratch sheets today | DESIGN §5.1; 180° scans resolved in 006.2 |
| F13 | decode-state-conditioned fragment placement: the pending-region set (un-certified LDPC tiles across the volume) prunes the correlation-placement hypothesis space for sub-grain/boundary pieces; F9 known-cells fast-reject redundant pieces (triage, not placement — payload is only predictable where certified, pilots everywhere) | L3/L4 → L2 acquire | **BUILT + MEASURED 2026-07-10 (014.5): paperholo.place.place_fragment (FFT matched filter over the seed-predicted pilot field, support-aware z, §15.4 gate — constants frozen on scan-B fresh windows 6/6) + tilemap.add_placed_fragment (provenance, revocable until F9); bch.decode_erasures ships the §14 erasure rung (ctx q=0.80/0.85 → 96/99% on 76 real tiles, 0 wrong-address in 9,120). Isolated end-to-end (own lock, no enclosing geometry) 5/5 at 6–10 mm — the piece-local-lock unknown RESOLVED, not the binding floor. Remaining: multi-piece segmentation (needs a real confetti scan), F14 piece triage, torn-shape masks. ANCHOR-GRAPH AMENDMENT 2026-07-11 (PILOTS-DESIGN §15.6, e018 real-scissors forensics 018.2): place_fragment gains opt-in PADDED search — page-edge overhang poses were excluded by 'valid'-mode construction, and real scissors always make margin-bearing edge pieces — plus word-path evidence preservation (fold ID window, mask-aware window grid, ID retry) and window-split placement above the ~25 mm rigid-model coherence length (measured: a 47 mm piece floors at mismatch 0.248 rigid, passes 4/4 at quadrant scale). Invariants: I1 no-evidence-discarded / I2 no-pose-excluded / I3 capacity-scales-with-span; §15.4 gates + F9 backstop unchanged. E022 AMENDMENT 2026-07-14: `paperholo.pilotsearch` promotes this field correlation to the independent E021->E023 primary placer, searches the descriptor's legal pages without an LDPC pending-set prune, and uses `need_mask` only to prevent redundant recovery while retaining known pilots as evidence; largest-first and full-pose neighbor predictions are scheduling accelerators, never inherited acceptance. E022 does not yet implement the F9/F13 feedback edge.** | 014.3 grain ladder = pure pilot-tile placement geometry; oracle margins: true = channel BER (.043–.086) vs nearest decoy ≥ .257, gap ≥0.20 every window; decoy floor = the (100,23) code's pairwise distance spectrum (min 27 EXACT (2026-07-29 exhaustive correction: TRUE min = 27, mult 3; 32 was a 400-pair sample — see the 014.4 correction); sampled 32/100 MEASURED — d≥27 doubles as the placement margin); budget MEASURED: 135–139 sites/6 mm, 240–251/8 mm (the 07-09 "~35–62" was a 4× pitch slip); pre-registered >0.35 decoy bar impossible by construction — floor-aware gate (true<0.15, decoys>0.20, post-hoc) to be validated in-build; 015: fragment-boundary yield 79.6% at 25.4 mm was the entire measured f-gap this attacks |
| F14 | volume-completeness stop rule: fountain rank drives the session loop — done = ANY K certified symbols, not LDPC-tile inventory; confetti triage is greedy, never a checklist | L4 → L0 acquire loop / operator | partially built (tilemap.volume_scans_wanted, e016 decode protocol); session/piece-triage generalization designed (PILOTS-DESIGN §15) | e016: K/N 0.800 ⇒ any ~80% of 1734 LDPC tiles recovers all data; F6 more_scans_useful is the per-page special case (014.2 live demo) |
| F15 | decode-directed re-acquisition ("repass"): certified tiles → dense truth labels (~40× pilot-site density) → refit local warp+detector on the RAW GLASS pixels → re-sample uncertified neighbors → re-decode; supersede-never-sum observation semantics; monotone stop rule (certified never demoted) | L3 certainty → L1/L0 re-acquire | E018 repass v1.1 BUILT + REAL-STATE MEASURED 2026-07-12 (197→216 certified, +19, fixed point round 3, zero wrong in audited cells). E024.0 BUILT + OWN-BRANCH/UNION-SEEDED NUMERICALLY QUALIFIED 2026-07-16 over immutable current E021.6 E023b state: explicit revision/dependency graph, target leave-out, per-generation atomic checkpoints, detector/pose 2×2, changed-target BP, and exact durable replay. `refine` reaches 759 decimated / 762 native; merged union and trusted-union-seeded decimated refine both reach the identical 772, all correct and monotone. HP E018b validation 2026-07-17 safely composes production E023c lanes with E024: C3 754→754 and C2 1,438→1,439, demonstrating diminishing affine-feedback return. | E024 remains LDPC-and-below and does not define a fountain/session stop. Current arm revisits accepted windows only. Experimental production-E023c lane export/union is now retained; integrated backward replay remains future. E024.1 losing-hypothesis placement retry and E024.2 seam-aware support extension remain separate and are the better-motivated next mechanisms |

---

## 8. Compatibility matrix (constellation × geometry), measured

The binding constraints are physics, not code shape. Declared here so a
mismatched pairing fails at spec time:

| | marks affine only | + strips | payload self-clock | pilots (M1) |
|---|---|---|---|---|
| B1 (c2 K) | ±2 dots — insufficient at c2 (steps up to 1.95 dots > cell/2) | measured: works; handicap +5.8 pp home / +3.4 pp AltaLink; between-strip refinement recovers ~2 pp on home multi-scan but is HARMFUL on AltaLink (needs per-band gate, 007.7/8) | interior only (dd_warp); edge zones fail; engine-conditional (weak lattice on eroded prints) | expected to supersede strips |
| B2 (RLL dots) | no | REQUIRED (or pilots) | IMPOSSIBLE at 2 px/dot (dot lattice at scan Nyquist) | expected ok (site-gated) |
| A3/A4 (composite) | ±2 dots + per-plane offsets | strips are K-plane: transfer to C/M/Y needs per-plane offset solving | M281: BROKEN (165 lpi screen contaminates phase; needs screen-notching + per-plane bias, 004.0a); AltaLink: composite is UNSCREENED (007.6) so self-clock may be viable — untested | per-plane pilots by design (DESIGN §5.4) |

Scan-mode requirements ride along: B-track prefers grey (~1 pp, 004.0b),
A-track requires color; modes are separate transport passes — never mixed
within one combine. Scanner-path requirements too: block-coded (JPEG) scan
paths erase <5-dot features and break the context detector (007.2) —
archive-grade decode wants uncompressed scans; and every pairing sits on the
§2 px/cell ladder (6 solid / 4 marginal / 2 Nyquist-edge / <2 dead).

---

## 9. Conformance — admitting a new implementation

1. Simulate first: round-trip on the measured simulator (M0 gate) before any
   toner. Format-axis changes also need sha-gated byte-identical regeneration
   + preflight tests (gs render, GT pixel-exact).
2. Pre-register envelopes in the experiment log before printing; outside-
   envelope = finding, not failure.
3. Every number: null control + canary verdicts + footing label (§1).
4. One variable at a time on hardware; every physical run logged with sha256.
5. Publish the characterization row in this document (registry tables above).
6. Rate-relevant claims quoted on multi-sheet minima alongside the best case.

## 10. Porting map (experiments → package, at M1)

Package modules mirror DESIGN.md layers (CLAUDE.md convention): modulation=§4,
sync/pilots=§5, inner FEC=§6, outer=§7, channel=§3.

| lives today | graduates to | note |
|---|---|---|
| L1-encode/L0-emit seam | **DONE 2026-07-07: src/paperholo/encodings.py** (registry + scramble format LAYOUT_VERSION 1 + emit; rll-i2w3 seed-only) | L2 composer (compose_page, PILOTS-DESIGN §8) consumes its API in-process |
| 002/cal_core.py registration + PatchView | paperholo.sync (register/resample) | + 4-landmark/strip-aware + 2-corner support (queue e) |
| 006/strip_tracker.py + 006/between_strip.py | paperholo.sync | refinement is engine-conditional — port WITH its per-band go/no-go gate (pending) + preflight |
| 004/dd_warp.py | paperholo.sync | per-class bias solving before cross-plane pooling |
| 001/scanlab.py v4 decode (y-profile, LLR, ctx) | paperholo.modulation (detect side) | keep the null-control idiom |
| 004/blind_alphabet.py EM-GMM | paperholo.modulation (detect side) | furniture-init guardrail baked in |
| 002/stripdec.py | paperholo.pilots (addressing) | until the window code lands |
| pilots.coordinate_code (stub) | implement at M1 | PERIOD/BLOCK fix ⇒ layout_version bump |
| E022 pilot-field placement | **DONE 2026-07-14: src/paperholo/pilotsearch.py** | independent E021 survey -> addressed pilot observations; single-scan CLI + persistent atomic multi-scan harness + static/live three-pane diagnostics under `experiments/022-pilot-tile-search/`; scan provenance is retained, E023 payload/feedback remains separate |
| E023 payload/LDPC | **DONE 2026-07-15: src/paperholo/payloaddec.py** | pure evidence collection/owner freeze/tile evaluation primitives; frozen E023 remains the numerical reference |
| E023b integrated receiver | **DONE 2026-07-15/16: src/paperholo/receiver.py + experiments/023b-integrated-receiver/** | production composition root, persistent physical-capture ledger, four-pane diagnostics, context/BP arms, correlated-view certificate merge, and read-only volume scorer; E024 feedback remains separate |
| E023c production scale cascade | **DONE + ONE HP CAPTURE PER C3/C2 FORMAT QUALIFIED 2026-07-17: experiments/023c-scale-space-receiver/** | native-first E021/E022/E023b scale ladder, authenticated persistent lane/certificate graph, atomic resume, NeedMap, real completion oracle, and diagnostics. C3 754/731 useful; C2 1,438/1,363 useful. The older NN/DD/ND/DN factorial remains historical evidence, not this architecture |
| E024 certified feedback | **DONE 2026-07-16: src/paperholo/feedback.py + src/paperholo/feedbackstate.py + experiments/024-feedback-receiver/** | state-only post-pass with persistent revision/dependency overlay, exact union trust, target-safe evidence resolution, detector/pose factorial, changed-frontier BP, per-generation save/resume, diagnostics, and fail-closed sequential replay. No E021/E022 numerical changes and no fountain stop condition. Retained experimental E023c-lane adapter has v2 exact-artifact bound audits and measures 0 C3 / +1 useful C2 post-cascade gain; full integrated backward replay remains future |
| E025 physical-channel metrology | **LAYOUT-V2 FORWARD DESIGN BUILT + SYNTHETIC-PREFLIGHTED 2026-07-17: src/paperholo/metrology.py + experiments/025-channel-metrology/** | two one-page K/color instruments; live CRC device readback; physical + payload-safe extent; pose/warp/transport; fixed-level/tone/background/plane-registration analyzers; morphology/microprint; large exact PRND fields; matched grid, C2 motif/aspect, KCMY4 and path controls; small real-LDPC coupons; measured-rectangle capacity; emitter/same-sheet-sensor/pipeline profiles and advisory hint. Forward physical print and production-detector arms remain open |
| 004/trellis_b2.py | stays experimental | negative result on record; motif emissions are its only path back |
