> **2026-08-22 — SYNTHESIS + STAGING LIVES IN docs/INDEPENDENT-PLANES.md.**
> That document records the 2026-08-21/22 measurement campaign (swim
> pilot, supervised affine ceiling, dead-vs-GT figure, adversarial
> review), its conclusions, and the re-scoped work in priority order.
> Amendments it makes to this doc: the §6.5.5a swim charter is
> RE-SCOPED (translation-only hint-seeded closer; 6-dof per-plane search
> and the ≤5/53 bar dropped — Jacobian measured plane-common); the
> §6.4 comb (V1) is DEMOTED from critical path; the §6.5.4b shrinkage
> target is CONFIRMED (review) and queued P1; the field's next form is a
> sheet-level service (INDEPENDENT-PLANES §4.A), not a payload-lane arm.
> Instruments: measure/plane_fields/ (placement ruling 2026-08-21).

# PLANE-FIELDS — per-plane registration for CMY8: comb-phase acquisition, tile-space pooling

Status: **DESIGN EXPLORATION v0.3** (2026-08-19, uncommitted draft in
refinement; v0.2 = concrete layout: differential-field representation,
R/F rounds, §3a/§3b; v0.3 = comb staged as optional, per-pixel channel
derivation, src/holo build target, certificates-always-taken ruling;
v0.4 = plane-generic ruling — K is the n=1 instance, §3b promoted from
learnings to design content; v0.5 = §3c the build — components, family
instances, yields, gated order, V0 added; v0.6 = representation
sharpened — translation vector field, gradient-Jacobian, lookup =
three uncoupled local affines per window; v0.7 = §6 detailed workplan
W0–W6 grounded in the 2026-08-20 receiver deep-dive — the seam, the
discarded anchors, the U-lane pattern, nine measured constraints,
measurement/illustration plan; field pane per user design — bottom
band, three-colour exaggerated quiver, threshold shading). Nothing here is built or scheduled; this document is the
line's charter and the durable record of its design dialogue — the §1
the 2026-08-18 session promised ("filed the whole exchange mentally as
the design dialogue for the A2 reopening; when we write that line's
plan, this conversation is its §1"). Per COLOR-UPLIFT-MEASUREMENTS
§15.5, this line does NOT inherit A2's charter or its struck token: it
is the merger of that disposition's two routings — (a) smooth
plane-differential field in the region model, (b) pose coupling for the
plane-common component — under a new acquisition idea that dissolves
the observability problem that killed A2.

Everything proposed is **receiver-axis only**. No format change; the
W/CM word law, site placement, dust law and keystream are untouched.
**Build target: src/holo** (the existing cascade + mop-up/refine lane
machinery and the e024 feedback pattern carry the R/F rounds today);
holo2 is the eventual home once its colour homework lands — the design
keeps the pull-model shape so that port stays natural.

---

## 1. Background

Two committed measurement records set the stage:

- **PK6/A2 (COLOR-UPLIFT-MEASUREMENTS §15, closed 2026-08-10 as a
  measured negative).** Plane-differential registration is real on
  every capture (τ ≈ 0.1–0.3 print dots, min-separation-flat, not the
  sampler's phase) but predominantly smooth with a strong plane-common
  component; the pre-registered per-window-constant arm failed its
  gate on all four captures, each on a different leg. Decisive
  pre-gate failures: own-window anchor reach on the residue C 21% /
  M 16% / **Y 0%** (κ=8 fallback fires exactly where the arm is
  needed), and Y anchor saturation 9–22% corpus-wide (dust-only
  supply) — Y registration was declared unmeasurable at fine pitch.
  The section's own post-hoc diagnostic found halo pooling lifts reach
  to 1.000 by *becoming a smoothed local field estimate* — "the
  reachable form of A2 collapses toward a field-model design, not
  independent per-window constants." On hp c3-cmy8 the arm would have
  actively harmed the registration-immune tails (ΔMSE_diff −33/−37 on
  M/Y): any correction must be dial-conditional per plane, never
  universal.
- **Sheet I (e033 §033.4, 2026-08-18).** The first capture that clears
  A2's bar, and it clears it as a *field*: the AltaLink prints the Y
  plane with a sinusoidal x-registration error — peak 0.83 dot = 0.42
  cell, period ≈ 100 mm (roller class), dead columns on the extrema,
  Spearman(|ΔY_x|, residue) +0.80. The failure law is a cliff:
  |ΔY_x| ≤ 0.25 dot → 1.3/53 residue; 0.62–0.75 dot → 39.8/53. C/M
  survive because the words are W/CM: the plane-common pose locks to
  the C/M mean (each ≤ 0.27 cell) while Y reaches 0.42. Dead-band Y
  toner mass, modulation and PSD are UNIFORM — the failures are
  full-evidence LDPC refusals: the receiver samples Y against a grid Y
  does not sit on. Attribution is airtight: three platen placements
  reproduce the same dead columns (print-fixed), the field is
  even-symmetric where scanner lateral CA is necessarily odd, and the
  HP sheets don't show it. Extra captures flip only
  threshold-straddling tiles (Y 1377 → 1444): more scans are not the
  lever.

The §15 record measured the differential field as "not a linear ramp —
M1 explains almost none of it; the right basis is the next question."
Sheet I answers the basis question: periodic transport harmonics.

## 3. The model and the concrete layout

**Representation ruling (v0.2, sharpened v0.6): the primary object is
the per-plane translation-delta VECTOR field over tile space** —
sampled (dx, dy) deltas RELATIVE to the committed plane-common pose,
each sample with a precision; there is no absolute truth anywhere in
it. The field is integrable by construction: the local Jacobian delta
IS its spatial gradient, never an independent unknown. What a window
receives at lookup is therefore a FULL UNCOUPLED LOCAL AFFINE per
plane (translation delta + 2x2 gradient), composed onto the common
pose — i.e. three poses per colour window, exactly the user's
two-additional-poses picture, served as the evaluated object rather
than stored as the record. Why delta, why field-not-per-window-poses:
(1) the differential is the SHEET's property (placement-invariant,
pools across scraps/captures/tile space); the absolute pose is the
CAPTURE's property and pools nowhere. (2) The evidence has this shape:
words are W/CM — the absolute lock is jointly C+M and Y has no
absolute evidence; common ∘ delta states what absolute-Y would hide.
(3) Deltas have a natural zero: shrinkage target, no-evidence
fallback, and the dial-conditional off-switch. (4) Free per-window
objects re-import the PK6 measured negative (Y own-window reach 0%),
and independent per-window Jacobians can express non-integrable
tears — which are jitter/damage, the erasure classifier's territory,
never pose. Genuinely local within-window structure is fitted as a
residual by the existing refine machinery where evidence is dense,
downstream of the field, and fed back. Parametric structure (harmonics, the roller story, C−M
constants) is demoted to three subordinate roles: smoothing/
extrapolation prior into evidence-poor zones, compression for the
engine library, and diagnosis. This is also the holo2-compatible
shape: a field of annotations serving lookups — hints, never facts.

**Plane-generic ruling (v0.4): the field machinery is built generic
over planes, and K is its n_planes = 1 instance.** One field store,
one evidence scatter, one smoothness/extrapolation engine, one
window-lookup projection — dimensioned by the codec family's stream
count. The K design improvements of §3b are then not a port or a
second project: they are the same lanes running at n = 1 (a K
certificate is per-plane GT for its one plane; the K comb is the luma
comb; K coherence classification is the same statistic). This mirrors
the family unification of the kiss branch (one engine, K/CMY7/CMY8 as
instances) and keeps the Family enum the only dispatch.

**The round structure (lands as lanes in the existing schedule, not a
new architecture):**

- **R1** — luma addressing exactly as today (the current path IS round
  one; zero regression surface).
- **F1** — build the differential field from R1's yield, three
  evidence tiers by strength:
  (i) **certified tiles** — a certificate reconstructs the exact
  printed cells of ALL THREE planes at that tile (re-encode from
  payload); local per-plane cross-correlation there is the regmap-gt
  measurement made online and per-tile — the strongest evidence class;
  (ii) per-channel word residuals at addressed windows;
  (iii) the comb phase — the spectral form of dialogue beat 3's
  spacing/variance statistic: per channel, locally highpass/square and
  read the cell-frequency comb line's phase = where that plane's
  lattice sits, from payload cells alone. Dense, weak, furniture-free.
  NOTE (v0.3): tier (iii) is an ADDITIONAL, STAGEABLE mechanism — the
  primary reach of the field is smoothness itself, propagating tier
  (i)/(ii) evidence to neighbouring windows with distance-growing
  uncertainty. F1 built from (i)+(ii)+smoothness is a complete loop;
  the comb uniquely adds: far-from-anchor reach (isolated scraps, dead
  interiors before first certification), the pre-address
  luma-vs-per-channel dispatch, and the offset-vs-jitter classifier.
  V1 measures whether it earns its slot.
- **R2** — project the field through placement poses back onto the
  FAILED windows; retry addressing, calibration and payload decoding
  with per-plane sampling.
- **R3** — per-channel word matching at field-predicted poses on the
  remainder; new anchors feed **F2**; iterate to fixed point or
  budget. Monotone by construction (certificates only accumulate).
  The channel images are PER-PIXEL derivations, never platen-global
  copies: zeroth order C ≈ 1−R, M ≈ 1−G (words are W/CM, so R sees
  the word through C's absorption and G through M's — same binary
  codebook, two lattices); the sharper form is the planecal 3×3
  crosstalk unmix per pixel, which the colour calibration machinery
  already fits. No new imaging path — the existing word matcher on a
  different derived image.
- **The instant trigger**: certification event → field-update wake →
  retry wakes for windows whose field lookup changed — the pull
  model's one-bit-wake / fire-time-consult shape, kept so the eventual
  holo2 port is natural.
- **Certificates are always taken** (user ruling, 2026-08-19): a
  certified payload is the holy grail — it solves the actual retrieval
  problem AND is the strongest field evidence. The false-accept
  control is the certificate gate itself (CRC-protected frames behind
  d=27 words with identity binding; measured 0 wrong in 69M+ audited
  cells across all campaigns), and it does not know which pose path or
  channel produced the attempt. Only attempt SCHEDULING (cost policy)
  needs pre-registration; acceptance never does.

**Three-frame factorization.** Total observed distortion factors into
terms with distinct coordinate frames and sharing scopes:

| Factor | Frame | Shared across |
|---|---|---|
| Engine registration field (per plane: Y sinusoid, C−M offset, per-station scale/skew) | tile/page space | all regions/scraps of a sheet; FORM (period, amplitude, axis) across sheets from the engine; PHASE per sheet (feed timing) |
| Paper deformation (hygroexpansion, damage) | tile space | one sheet, all its scraps |
| Placement pose | platen space | one scrap-placement |
| Scanner optics (lateral CA) | platen space | every capture that scanner makes at that dpi |

**Per-plane phase fields.** For each channel, per block: highpass /
square → the cell-frequency comb's complex phasor. Unmix channel
phasors to plane phasors via the planecal 3×3. Then per plane:

- field **value** = translation mod one cell (dense, furniture-free);
- field **gradient** = the local Jacobian (scale, shear, rotation);
- field **coherence/variance** = offset-vs-jitter classification.

**Hierarchy, two axes.** Across planes: per-plane fields with shrinkage
toward the pooled common field, weight set by per-block phase SNR (rich
C/M evidence floats free; Y in dead bands collapses gracefully to
common + low-order offset — never a free parameter where evidence is
thin, the PK6 lesson). Across space: block → window → region →
tile-space sheet field → engine form — where "engine form" is the
COMPRESSED prior distilled from accumulated fields (devices registry,
measured capability data; the archived e030/e032/e033 corpus seeds it
without new scans), never a substitute for the field itself.

**Absolute anchoring.** Phase gives pose, never identity. Spatial
unwrapping (trivial at measured gradients) yields continuous relative
fields per connected region; one decoded word anchors the region
absolutely for all planes; tile addresses then place every window in
tile space, closing the pooling loop (an EM-shaped fixed point:
fields → poses → words → addresses → pooled tile-space fields →
better sampling everywhere). The confetti payoff: a 25 mm scrap cannot
see a 100 mm sinusoid, but the assembly of scraps can — and then every
scrap benefits, including those too small to estimate anything alone.
This is the multi-scan law's geometric twin: pooling wins in the
de-correlated frame, and tile space is that frame for print effects.

**Readout.** Each plane sampled on its own composed pose
(word anchor ∘ unwrapped per-plane field ∘ placement). Where the
jitter classifier says the channel is incoherent, dial that plane to
erasures instead of feeding poisoned full-evidence LLRs (sheet I's
12,455 `attempted_failed` become an informed decision either way; the
pooled fountain's dead-plane tier is the graceful floor).

**Addressing dispatch.** Luma when |φC−φM| is small (SNR-optimal);
per-channel word matching (R→C/W, G→M/W) at the field-predicted pose
when large. The sheet-I mop-up winner-flip canary (~35%) is a live
detector for the threshold.

## 3a. Feedback symmetry with K

This line is e024's certified-feedback loop with the field as shared
state and per-plane deltas as the payload: certificates → better
geometry → retries. The expected yield differs from K's measured
diminishing returns (e024 after e023c): K's residual failures were not
pose-structured, while sheet I's are, with a cliff — crossing from
0.6 to 0.25 dot of Y error flips ~75% of dead-band tiles by the
measured law. Done-geometry's certified-done pixel space is the
certificate-level analogue of this line's field-level pooling; the two
compose (done gates work off, fields gate it on where it can pay).

## 3b. The K design improvements (same machinery, n_planes = 1)

Under the plane-generic ruling these are design content of THIS line,
not a follow-on port. Each maps onto the same F/R rounds:

1. **Tile-space transport/banding field for K.** K engine effects are
   fields too — e029's interior row-42 band and extreme-column losses
   (known M281 horizontal banding) were met by every window alone. F1
   at n=1: certified K tiles give exact GT (tier i), word residuals
   tier (ii); the pooled y-transport field projects back to failed
   windows in R2, and — the confetti payoff again — small scraps
   inherit sheet-level distortion they cannot see. Validation hook:
   whichever archived K captures carry the e029 band, the field's
   residual concentration at row 42 is the K analogue of V2.
2. **Luma comb phase as the pre-word placement prior.** K payload is
   equally cyclostationary; a local phase field (translation mod cell
   + Jacobian) turns cold placement into
   verification-at-predicted-pose — attacking the kiss branch's
   parked, measured cold-search cost mechanism — and rescues marginal
   windows sitting just under the word-match threshold. Same staged
   status as the colour comb (tier iii; optional; V1-class gate).
3. **Coherence-classified erasures for K bands.** Offset-vs-jitter
   classification gives banding-damaged rows an informed disposition
   (resample vs erasures) instead of ordinary-evidence LLRs — the
   geometric sibling of the 018.7 bounded-LLR honesty invariant:
   detect where the grid itself is lying, then say so to the decoder.
4. **Anchor extension across weakly-worded regions.** Field/phase
   continuity carries one region's word anchor into a connected
   neighbour whose own words are marginal — relevant exactly at the
   d=27 small-scrap floor, where words are the scarce resource; at
   n=1 this is pure field smoothness, no comb required.

## 3c. The build: components, family instances, and yield

Field dimension = PHYSICAL PLANES of the family (K:1, CMY7:3, CMY8:3;
cmy7 has one stream but three planes).

**Shared core (plane-generic, built once):**

1. Field store — per plane, sampled (dx,dy) differentials over tile
   space with per-sample precision, relative to the committed
   plane-common pose. TRANSIENT: rebuilt from the certificate/pose
   ledger at load — no state-schema change, ever; a hint store by
   construction (holo2-port-trivial).
2. Certified-tile registration probes (tier i) — per certificate,
   re-encode the tile's exact printed cells (the divergence-audit GT
   machinery), small per-plane NCC around the committed pose →
   (dx, dy, confidence). measure_plane_offsets.py made online.
3. Smoother/extrapolator — locally weighted regression of the
   per-plane translation-delta vector field over tile space,
   distance-growing uncertainty, shrinkage to the pooled common
   field; serves lookup(window) → local affine per plane (translation
   + gradient) + uncertainty.
4. Field-corrected readout + retry lane — sampling composes committed
   pose ∘ per-plane delta; batch F↔R alternation via the mop-up/refine
   lane pattern (event-driven only in holo2 later); dial-conditional
   per plane per block (the hp c3-cmy8 harm measurement); coherence
   failure → erasure dialing.

Staged extensions: tier (ii) per-channel word residuals + R3
per-channel addressing; tier (iii) comb behind V1.

**Family instances and expected yield:**

- **CMY8**: per-stream certificates give their own plane's GT (sheet I:
  1,444 Y anchors in clean columns; smoothness carries the field into
  the dead columns). Yield by the measured cliff: correcting Y to
  ≤0.25 dot moves ~490 of the 517 dead-band stream-slots from the
  39.8/53 to the ≤1.3/53 regime — sheet I closes with margin from one
  capture. Forward: sheet H (wider bands predicted) plausibly decodes
  ONLY with fields — the enabler for the colour rung ladder above
  r0700 and the climb past 230 b/mm²; registration-tolerant engine
  portability. Excluded honestly: toner starvation (M281 Y stays dead).
- **CMY7**: the brittle joint codec gains MOST per tile (one desynced
  plane poisons every joint symbol); its certificates are the richest
  tier-i source (one certificate → all three planes' GT). Hardens the
  codec whose e032 failure inverted the discovery ranking — another
  gain on the campaign's measured readout-axis lever. The hp
  screened-mush capture stays out of reach (addressing-level failure).
- **K (n=1, built first)**: certified probes → transport/banding field
  → corrected retry. Modest on intact sheets (e029's row-42 band and
  edge columns ≈ 1%), structurally important twice: scraps inherit
  sheet fields they cannot see, and it validates the machinery before
  colour complexity enters.

**Build order, gated:**

- **P0 = V0 (zero receiver code)**: a standalone script builds the
  field from sheet I's EXISTING 5,297 certificates + committed poses
  against the archived scans and must reproduce the regmap-gt
  sinusoid — validates tier-i + smoothing (the minimal loop's whole
  evidence chain) before src/holo is touched.
- **P1**: field store + probes + smoother in src/holo, plane-generic,
  K instance first.
- **P2**: corrected readout + retry lane; V3/V4 bar on sheet I; K's
  e029-band residual-concentration check.
- **P3**: word-residual tier + R3 per-channel addressing (certificates
  always taken; scheduling policy pre-registered).
- **P4**: comb iff V1 earns it; offset-vs-jitter erasure dialing.
- **V5** rides the next scans (sheet H; the 4800 run).

## 4. Pre-registered validation ladder

All of V0–V4 run on archived captures — no hardware.

- **V0 — the minimal loop's evidence chain, before any code lands.**
  Field from existing certificates + committed poses (sheet I state)
  reproduces the regmap-gt sinusoid. (Added v0.5 — the P0 gate.)

- **V1 — the estimator validates blind.** Per-channel comb-phase on
  the sheet-I 2400 scan, no GT, no addresses, no decode: must
  reproduce the regmap-gt sinusoid (0.83 dot peak, ~100 mm period,
  dead columns on extrema; bar: Spearman vs GT per-column field and
  amplitude/period agreement to be fixed at registration time).
- **V2 — departure spectrum, not a rule.** Measure per-plane Jacobian
  differences (dφ/dx, dφ/dy across planes) on sheet I and on the
  archived regmap NPZ corpus; output is the measured departure
  spectrum per engine (feeds the shrinkage prior), explicitly NOT a
  one-point global ruling.
- **V3 — the ceiling.** Inject the GT-measured Δx_Y(x) field into
  Y-plane readout on the archived sheet-I captures. Bar (from the
  measured cliff): dead-band residue moves from the 39.8/53 regime to
  the ≤1.3/53 regime. If the TRUE field does not buy the
  certificates, no estimator will.
- **V4 — the estimator earns it.** Same bar as V3 with the blind
  V1 field replacing GT.
- **V5 — out of sample.** Sheet H (r0850, thinner parity): wider dead
  bands, lower threshold — falsifiable before its decode. The 4800
  sheet-I mechanism run: bands persist (print-fixed, 16 px/cell does
  not undo a 0.42-cell offset).

## 5. Open issues and deliberations

1. **Basis for the field fit**: low-order harmonics in field-x
   (roller-seeded period, free phase) vs splines. Harmonics match the
   measured mechanism; splines are agnostic. V2's departure spectrum
   informs this. Roller phase is per-sheet (feed timing) — the engine
   library stores form, never phase.
2. **Comb SNR vs block size**: phase precision scales with block area;
   the dead bands are ~3–4 tile_x wide, so blocks ≤ ~2 tiles in x are
   needed to resolve band structure. c2 tile = 5.4 mm; the 100 mm
   period is comfortable, band edges are the binding constraint.
3. **Crosstalk algebra**: the phasor unmix treats the 3×3 as linear on
   edge-energy phasors; strictly the mixing is on reflectance. At
   measured α (~0.3) and Δφ (~0.4 cell) the residual bias estimate is
   ~0.1 cell — inside the correction budget, so V1 must measure it
   (GT comparison catches it for free).
4. **Y sampler saturation** (PK6 G3: 9–22%): the comb sidesteps
   furniture anchors, but any *anchor-based* cross-check on Y still
   needs the sampler prefilter fix first. Do not let the old anchor
   path back in as silent validation.
5. **Unwrap edge cases**: disconnected regions (confetti) each need
   their own word anchor — already the placement doctrine; torn
   boundaries where phase coherence breaks define the region graph.
6. **Scanner CA**: measurable once per scanner in platen space
   (odd-symmetric R−G field, ±4 px at 2400 on the Canon) and applied
   to every capture — a one-time calibration artifact that today's
   receiver never uses. Where does it live (devices registry as
   measured data) and what qualifies it?
7. **Scheduling/cost**: which lanes compute phase fields (survey-level
   coarse lanes are nearly free; fine-lane refinement on demand), and
   what the dial-conditional application looks like given hp c3-cmy8's
   measured harm on registration-immune tails — per-plane, per-block
   gating by measured benefit, monotone by construction (the §6.2a
   schedule-law pattern).
8. **Interplay with existing machinery**: done-geometry (certified
   tiles project to capture space — the certificate-level analogue of
   this line's field-level pooling); e024 certified feedback; the
   holo2 pull scheduler (fields are hints/annotations, never facts —
   fits the pull model); discovery integration explicitly deferred
   (FORMAT-SPACE §13) — per-channel addressing changes null budgets
   and waits for that line.
9. **RESOLVED (user ruling): certified payload is always taken.**
   The certificate gate is the false-accept control regardless of the
   pose/channel path that produced the attempt. What remains open is
   only the attempt-scheduling policy: where per-channel matching is
   worth its cost (the §6.2a schedule-law pattern), and the dispatch
   threshold's default.
10. **Naming/charter**: this document. The line supersedes nothing
    and blocks nothing; it competes for print-day-adjacent time with
    the fossil sunset and the corpus re-decode sweep.

## 6. The W6 verdict and after

### 6.4 W6 verdict (2026-08-21, sheet I, three 2400 captures, dial ON)

**PRIMARY BAR FAILED; MECHANISM VALIDATED.** Median dead-band Y
residue 24.0/53 vs the pre-registered ≤ 5/53 (baselines: 39/53 from
the archived state, 44/53 from the §033.4 table — which is a MID-RUN
snapshot, sums 581 vs the final state's 517). And yet: certificates
5297 → **5549** (+252; Y 1444 → **1629**), whole-page Y residue
517 → 332, C residue 66 → 2, M 3 → 0, **close VERIFIED byte-exact**
(payload sha 2445b95d… = the live volume). W4 probes at real-capture
scale: 16,125 measurements / 5,376 sites for 42.7 s + 0.052 s solve;
coverage ≥ 0.98 on ordinary/refine lanes; adoption gating correct on
the starved mop-up lanes; window_nulls 0. Run: 2 h 18 m, 12-level
plan × 3 captures, ~11.6 GB peak.

**The band structure is the finding.** Band 1 (cols 8–11) 164 → 121;
band 2 (15–19) 189 → **62**; band 3 (27–29) 108 → **127 — WORSE**.
Column 8 (zero Y evidence) 53 → 46. Three measured causes, each with
its follow-up:

1. **Zero-evidence bands defeat extrapolation** (col 8; V0 predicted
   this exactly) → the tier-(iii) comb is now EMPIRICALLY justified —
   the only evidence source that needs no decoded tiles. V1 next.
2. **Adoption is all-or-nothing per page** (the page is one region,
   so per-region adoption = per-page): a smooth field fitting two
   extrema and misfitting the third gets applied everywhere → band 3
   regresses. Follow-up: per-block application gating (the doc's
   original dial-conditional-per-block intent, §6.2 W2's region
   granularity was the shortcut).
3. **Tree-drift confound uncontrolled**: the 5297 baseline is the
   August c4-row tree; part of +252 may be receiver drift. Owed: a
   same-tree dial-OFF control run (~2.5 h) for clean attribution.

Also measured by the run: the a4b landmine's true form (bare
`PLANE_ORDER`, fixed at c79323f — the pinned qual tree predated the
fix and crashed in its refine tail; barriers had banked everything;
the close was recovered via a default-bound resume that never
re-enters the lane). And a W5 wiring defect found and fixed
(2026-08-21): FieldStats read Details only off stage.complete while
production emits them on payload.plane_fields — summary() was empty
on every real run; the production event shape is now pinned in the
test. Artifacts: scratch/plane-fields/qual/ (state VERIFIED,
recovered.bin, score-on.json, residue-comparison PNG; the driver is
committed as `measure/plane_fields/qualify_sheet_i.py`).

**Line status after W6**: W0–W5 built and null-proved; V0 passed;
V4 partial (bar failed, gains real and correctly located). Owed, in
order: V1 (blind comb vs regmap-gt — now the critical path to the
dead bands), per-block adoption, the same-tree dial-off control,
V5 out-of-sample (sheet H, the 4800 run — both decode on this
branch via --format L: + --refine).

### 6.5 Post-W6 design layer (2026-08-21) — recorded from dialogue

1. **Default-flip sequencing** (beat 13): wire `--plane-fields` as the
   explicit ordinary-lane opt-in (pane live from lane one; uF
   unchanged); land per-block adoption (kills the band-3 harm mode);
   then flip the default ON with a same-tree strict-superset proof
   (dial-on certificate set ⊇ dial-off set on sheet I), after which
   the flag becomes the off-switch. Until then --refine is REQUIRED
   for any field activity on the stock CLI, and the diag band appears
   only when uF fires at the tail.
2. **The swim rescue tier (R0.5)** (beat 14): per-window/per-scrap
   plane swimming for acquisition failures the field cannot reach
   (C–M desync breaking luma addressing on small scraps; cold start).
   C/M swim on per-channel words; Y swims RELATIVELY (dust pool or
   comb) given the C/M lock; certificate-gated; residue-scheduled,
   uF-style. Converges with tier (iii): the comb is the swim as a
   statistic.
3. **Cross-capture pooling**: the per-capture field is a builder
   scope choice, not a design one — the differential is print-frozen,
   so one sheet-level field over all captures is strictly better
   evidence; small change, unbuilt.
4. **Column 8 decomposed**: part extrapolation-with-no-evidence (the
   comb's job), part PEAK ATTENUATION — the smoother recovers ~74% of
   a sinusoid peak (W1 measured), leaving ~0.2 of 0.83 dots at the
   extremum, brushing the 0.25 cliff. The local-linear smoother
   upgrade (W1's noted path) attacks the second half independently
   of the comb.
5a. **THE SWIM CHARTER (ratified beat 17, v0.12).** Per-plane swim as
   a uF candidate strategy, generalized to the FULL local affine:

   - **Search space**: per plane per residue tile, 6 dof — (dx, dy)
     translation + the 2x2 Jacobian (shear/rotation/scale). Raw
     6-dof grids are infeasible (~13^6); the search is STRUCTURED:
     translation first (measured dominant — the sinusoid, the C−M
     offsets), Jacobian terms opened only where translation-only
     stalls or where the regime demands them (small-scrap rescue,
     where placement itself is suspect; engines with per-station
     skew). This UNIFIES the R0.5 rescue tier and the residue
     closer: one mechanism — per-plane local-affine search,
     hint-seeded, likelihood-guided, oracle-gated.
   - **Staged economics (his "gated by likelihood")**: (1) the FIELD
     HINT centres the search (hint design open — to be thought
     through further; blind fallback = coarse 1D-x on the measured
     axis); (2) a cheap LIKELIHOOD SURROGATE guides/prunes within
     the space — candidates: per-tile detector log-likelihood,
     known-cell (furniture + certified-neighbour) agreement, LLR
     margin; coordinate-descent / coarse-to-fine, NOT exhaustive
     grids; (3) LDPC attempts only at the top-k survivors;
     (4) the CERTIFICATE GATE is sole acceptance — monotone, failed
     searches change nothing, the 0-wrong record is the licence.
   - **Grounding**: this is the existing refine machinery
     generalized, not a new engine — certified_refine (K) and
     refine_color_window already run (dθ, du, dv) grid searches with
     held-out scoring inside bounds (0.15°, 0.25 cells); the swim
     widens bounds per plane under likelihood guidance and swaps
     adoption-gating for the decode oracle.
   - **PRE-REGISTERED BAR (unchanged)**: archived sheet-I captures,
     dead-band median Y residue ≤ 5/53 (the bar the field missed),
     column 8 reported separately; archived-data-only. If it hits,
     the always-on/adoption question collapses (monotone needs no
     dial) and item 1's flip sequencing is re-evaluated.
   - **Open (recorded, not resolved)**: hint design (his "we'll
     think through that some more"); surrogate choice + its
     calibration; per-dof bounds and the budget schedule; whether
     successful swim affines feed the field as full local-affine
     evidence (they should — tier-(i)-grade exactly where the field
     is blind) and how the field then serves Jacobian hints back.
4a. **Live-fire log (2026-08-21, post-merge, user runs).** Sheet I
   fresh single-capture 2400 state (`I-multi-pf`), stock CLI
   `--format L: --refine --no-close`: **5,164 certificates from ONE
   capture** (the dial-off live baseline needed three captures for
   5,297; no clean single-capture baseline exists for exact
   attribution). The E FIELD ×50 pane rendered as designed — the
   sinusoid legible live. uF field report: rms C/M/Y
   0.38/0.35/0.32 d, coverage 99.9%, samples 4,801
   (certified 1,516 / dust 1,505 / probe 768 / word 1,012) —
   **adoption C:1, M:1, Y:0**. THE FINDING: on single-capture
   evidence the uF arm refused exactly the plane it exists for.
   Hypothesis (needs per-leg Detail diagnostics, small follow-up):
   thin Y evidence raises the posterior sd leg and/or
   shrinkage-to-common suppresses the predicted |delta| below the
   0.25-dot has-something-to-say leg — a self-defeating interaction
   exactly when evidence is scarce (W6's three-capture ordinary
   lanes adopted Y on 21/25 reports). Practical consequence: for
   sheet I, add the remaining captures to the state before the
   closing run so Y adoption flips; the swim (oracle-gated, needs no
   adoption) is immune to this failure mode by construction — one
   more argument in its column. Mop-up winner-flip canary read
   44.3% (the e033 ~35% mechanism signature, expected on this
   sheet). Pane verify-item: distinguish "no field data" blocks
   (white) from the 0.25-dot threshold shading visually.
4b. **Reading the pane, and the shrinkage-target bug (user
   observation, 2026-08-21).** He noticed C/M arrows showing larger,
   OPPOSING motion than Y — "I thought it's the yellow that wanders
   off." Three layers: (i) C/M antisymmetry is STRUCTURAL — the
   committed pose is fit from W/CM words, so it sits at the C/M mean
   and each plane's stored delta is ±(C−M)/2; any C−M differential
   renders as opposing arrows. (ii) That differential is genuinely
   large: §033.4's Canon R−G lateral CA (±4 px @2400 = ±1 dot p-p,
   odd-symmetric), the constant C-above-M ≈ 0.37 dot in y, plus
   per-drum sinusoids — each plane carrying half puts C/M at ~0.54
   dot, AT the ~0.5-dot cliff; hence baseline C residue 66 → 2 with
   the field on (the field is correcting scanner CA, unplanned).
   (iii) **Y is UNDER-rendered, and that is a bug**: true excursion
   0.83 dot peak (rms ≈ 0.59) vs reported rms 0.32. Mechanism: the
   shrinkage prior pulls each plane toward the precision-weighted
   mean ACROSS PLANES, but C and M cancel in that mean, so the
   "common field" ≈ Y/3 — Y is shrunk toward a third of itself
   exactly when its own evidence is thin, which is also what pushed
   its predicted magnitude under the 0.25-dot adoption leg (§6.5.4a).
   The pane and the `Y:0` refusal are the same finding seen twice.
   FIX CANDIDATES: shrink toward zero (the natural no-evidence
   target); leave-one-out common (a plane's prior excludes its own
   evidence); or drop cross-plane shrinkage entirely (spatial
   smoothing does the real work). TEST: add the remaining sheet-I
   captures — Y arrows should grow toward the full sinusoid and
   adoption flip to C,M,Y; if they do not, the pooled-mean mechanism
   is confirmed dominant and the prior must change regardless.
   NOTE for interpretation: the pane shows DELTAS, not decode
   consequences — C/M errors are half-cancelled by the mean-pose,
   Y's is not.
5b. **FORMAT-AXIS CANDIDATE: CMY word states** (user, 2026-08-21 —
   recorded here as a cross-reference; this line's charter is
   receiver-axis, so pursuing it means a COLOR-DESIGN/HOLO-DESIGN
   amendment, not a PLANE-FIELDS work item). Print words in all three
   inks, acquire on luma exactly as today, then locate C, M AND Y by
   per-channel matched filter. Distinct from — and better than — the
   parked "rotate word ink across planes" idea (beat 2), which
   weakens per-site luma contrast; this adds a plane at every site
   instead.
   - **The mechanism**: today every word site is Y-WHITE (both W and
     CM leave Y absent), so the Y channel's view of the word field is
     featureless — the root reason Y anchors are dust-only and PK6
     called Y unmeasurable. CMY words give Y the same structured
     binary pattern as luma: ~100 high-contrast known cells/tile vs
     ~10 dust cells. And Y never needs to DECODE: once luma decodes
     the address the template is known, so Y registration is
     correlation against a known pattern — zero error-budget spent.
   - **Measured, engine-dependent** (COLOR-DESIGN D3 / P1 017.0):
     M281 triple is WORSE (luma 73 vs 65; Stage-A 10.1% vs 5.8%)
     because ANY plane overlap triggers its contone re-screen
     (layer-0 freeze); **AltaLink triple is marginally BETTER (0.92%
     vs 1.04%)** and e031 measured no re-screen on plane overlap
     there. Dead-Y degrades gracefully (intended-CMY prints as CM;
     the per-page word-site 2-GMM re-levels).
   - **TONER CAVEAT on the M281 numbers (2026-08-21).** The re-screen
     MECHANISM is solid and toner-independent: measured spectrally in
     e002/e003 (a month before the low-toner era) as ~165 lpi ±14° /
     ~212 lpi 45° screen families IN THE C AND M CHANNELS, triggered
     by REGION overlap not mark overlap (dot-disjoint emissions
     screen identically), with plane knockout on sequential masks,
     every emission path affected, single-plane imagemask
     bit-faithful in the same session, and the AltaLink as a negative
     control (e031). BUT the CMY-vs-CM word figures (luma 73 vs 65;
     Stage-A 10.1% vs 5.8%) come from 017.0 — inside the set flagged
     consumable-confounded (project-m281-toner-state; e017/e030
     Y-channel verdicts). The mechanism predicts starvation
     EXAGGERATES the penalty: the screen reallocates coverage away
     from C/M toward a Y that then deposits nothing. So the M281
     objection's magnitude is unqualified until re-measured on
     healthy toner; the healthy-Y, non-re-screening engine already
     read tie-or-better. Re-measurement rides the same one-patch
     test.
   - **Costs**: format fork (new coding, new prints, requalification);
     NOTHING for the printed A–I corpus, so comb/swim remain the
     rescues for paper already in the world; dust still required (W +
     CMY exemplars do not calibrate the other six states, cf. beat
     18).
   - **Cheap to express post-FORMAT-SPACE**: a cmy8 GENERATION token
     (e.g. `c2-cmy8-r0700-p120-v2@…`, v2 = CMY word states) —
     parseable, seed-distinct, fossil-safe, no plumbing.
   - **Discriminating test before any commitment**: one
     characterization patch carrying both word renderings on the next
     print day — Stage-A luma separation on this engine + per-channel
     Y correlation quality against the known template.
5. **The two-thrust synthesis**: the open items are two campaigns,
   not ten features — (a) evidence-free zones: comb (V1), swim-Y,
   local-linear; (b) addressing rescue: R3 per-channel words,
   swim-C/M, phase-informed dispatch. Plus the orthogonal hygiene
   items: per-block adoption, cross-capture pooling, CA calibration,
   the K instance, the engine library, holo2. The merge-time items
   are DONE: RECEIVE-DESIGN §9b (v0.57) and the CLAUDE.md bullet.

### 6.6 The swim's band and ceiling (2026-09-03/04, measured)

Recorded from the re-key repair and its review
(holo3/conversion_docs/MEASUREMENTS-2026-09-03.md).  The swim is
per-plane: for each plane separately, per window, a local affine
searched within `translation_bound_dots` = one printed cell (3.0 dots at
c3) of the field's hint, while the field publishes a per-plane delta
clamped at `MAX_DELTA_DOTS` = 2.0.  Composed reach is therefore about
5 dots from true register, per plane.  The binding ceiling is not the
swim's bound but its ARMING GATE: like tiles.retry and tiles.local it is
born only from `OUTCOME_FAILED` attempts, and a plane misregistered far
enough emits BELOW_FLOOR instead — no tile is attempted, no rescue row
is born, the swim included.  At c3 the two limits coincide near five
dots.

Measured on the steep pair with the field running: at 3 dots the field
and the cheaper rows recover the page without the swim; at 4 the swim's
marginal gain is one tile (zero after the b8471fc re-key, local150 takes
it); at **4.5 the field alone loses the whole Y plane (200/300 — Y
attempted, retry/local/planek each firing 100 jobs and certifying none)
and the swim brings it back to 297/300 — 20 minted by the swim, 73 by
local150, 4 by scan**; at 5 nothing helps (200/300 either way, only
tiles.scan fires).  The swim's existence stimulus is re-derived to
4.5 on the yield principle — the rung where the swim buys the most — and
its claim is now the causal one ("without the swim the plane is dead"),
not per-certificate attribution.  The amplitude is a float (per-row
shifts stay whole dots; peak 4 at 4.5 under banker's rounding); the
earlier "whole dots by construction, no third amplitude" was wrong and
is corrected in the modules.  Exhausting the band is an instrument run
(`measure/h3_swim.py run --amplitude-dots`), not a lane's job.

## 7. Provenance

- e033 §033.4 (the measured mechanism; regmap-gt instrument,
  `scratch/xerox-v1-20260818/regmap-gt/`, rerunnable, sha-validated).
- COLOR-UPLIFT-MEASUREMENTS §15 + PLAN §8 (the A2 measured negative,
  the two routings, the 2.27M-anchor NPZ corpus under
  `scratch/color-uplift/regmap/`).
- Design dialogue: transcripts a325690b (lines ~836–1086: hypothesis,
  measurement, photometric question, cyclostationary counter) and
  6c36fbc4 (the a–d acquisition sketch, connected-region unlock,
  tile-space pooling, per-plane-generic ruling), sessions
  2026-08-18/19.
- e031 position-variance metric (the offset-vs-jitter classifier's
  characterization-side ancestor).
