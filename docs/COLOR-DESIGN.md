# COLOR-DESIGN v0.2 — the CMY color channel

Status: measured historical record plus current Holo amendment,
2026-07-27. The original E017/layout-version-4 decision record is retained
below because it owns the paper-channel measurements. The current
`src/holo` format and receiver contract is
[COLOR-INTEGRATION-DESIGN](COLOR-INTEGRATION-DESIGN.md), with execution and
qualification gates in
[COLOR-IMPLEMENTATION-PLAYBOOK](COLOR-IMPLEMENTATION-PLAYBOOK.md).
Nothing in the established K rows changes.

## Change history

| Revision | Change | Standing |
|---|---|---|
| v0.1, 2026-07-10 | Recorded the E017 CMY8/PID-MLC design, measured W/CM bootstrap, QDA/PAVA detector, plane-registration model, and the engine-gated CMY7 response. | Retained as the historical measurement and rationale record. |
| Integration design, 2026-07-26 | Selected explicit CMY7 and CMY8 rows at c2 and c3 in the current 64×64 Holo architecture, with K numerical leaves preserved. | Current format/architecture authority lives in `COLOR-INTEGRATION-DESIGN`. |
| `1b100cb`, generator tranche, 2026-07-26 | Implemented the four catalog-only rows, compound CMY7 and independent-stream CMY8 codecs, composite DeviceCMYK emission, and plane ground truth. | Implemented; still provisional. |
| Receiver tranche, 2026-07-26 | Implemented direct-native RGB lanes, shared luma placement, color registration/detection with a deterministic 512-anchor cap per class and plane, compact evidence, and stream-aware attempts/certificates/close/replay. | Implemented software path; paper qualification and default promotion remain open. |
| Q1 software qualification, 2026-07-27 | Added full-page `tiffsep` plus clean-`tiff24nc` plane-recovery comparison of each production row against authored C/M/Y truth with zero K. | Implemented software-emission gate; no paper or default-discovery claim. |
| Standalone TIFF qualification tool, 2026-07-27, corrected 2026-07-27 | Preserved the useful dropout, speckle, shear, crop, blur, noise, and M281 simulation algorithms from the removed `78ac26a` corpus subsystem in one TIFF-in/TIFF-out tool. | `nominal`, `stress`, and `hp-m281-flatbed` are explicit tool-only shortcuts (2026-08-02: the characterized shortcut split into `hp-m281-flatbed-cmy` and the K-only `hp-m281-flatbed-k`). The corpus module, builder, manifest, CLI, tests, and Q0 corpus record were deleted. |
| Full-page M281/CAL-1 operational check, 2026-07-27 | Generated and ingested one c3-CMY8 1200-dpi full-page realization, retaining compact input/output/state hashes and frontier counts. | File seam passed; acquisition did not: zero poses, attempts, or certificates, close open. |
| Receiver correctness review, 2026-07-27 | Corrected CMY8 tie/prior calibration and collapsed-plane evidence, bounded K/RGB sampling by local window, enforced actual per-child/per-plane nonzero attempt floors, count-gated one pre-BP150 color close, removed terminal-only color evidence wiping, strengthened registered-row public validation, and clarified stable codec/repair reporting. | Current receiver semantics; digital tests added, physical qualification still open. |
| One-tile/NeedMap correction, 2026-07-28 | Uses the complete 20-row dust multiset for component PAVA, repairs sparse QDA split coverage without population overlap, replaces the aggregate 300-label cliff with the p120 6/2/3 component-support contract, keeps certificate feedback at prior barriers, and removes wholly terminal regions before image work. | Current receiver semantics; c2/c3 one-tile synthetic and four-row TIFF-chain software gates pass, physical qualification still open. |
| Direct all-four receiver gate, 2026-07-27 | Added a slow opt-in generator → Ghostscript → standalone TIFF CLI → real receiver → strict reload round trip for each current color row. | Lean test-only composition; the removed corpus subsystem remains deleted. |
| CMY7 structural attempt gate, 2026-07-27 | Added a cheap per-child complete-pack support check through the exact inverse interleaver before soft demapping. | Current scheduling rule; the post-demap actual-nonzero floor remains authoritative and physical qualification remains open. |
| Bounded receiver vectorization, 2026-07-27 | Replaced per-cell Python setup in E022 alignment, 3×3 neighborhoods, owner selection/provenance validation, and the CMY7 bit marginals with bounded array operations. | Mathematical and receiver behavior are unchanged; this is a KISS/performance implementation refinement, not a format or policy change. |

## A. Current `src/holo` amendment

The current implementation is not a compatibility reader for historical
layout-version-4 sheets. It defines four new Holo format-v1 rows:

```text
c2-cmy7-p120-v0    c3-cmy7-p120-v0
c2-cmy8-p120-v0    c3-cmy8-p120-v0
```

All four are immutable explicit catalog entries and are deliberately absent
from default cold discovery. They may be generated and received by exact
coding ID while provisional.

The implemented receiver keeps the established E021/E022 geometry and
address authority. Every color scale lane is decimated directly, channel by
channel, from the authenticated native RGB acquisition; the aligned luma
view is derived from that same lane. The binary placement reference contains
all 120 furniture sites. Word states project as `W=0`, `CM=1`; a dust state
projects to one exactly when at least two of its C/M/Y components are
present. This is the equal-channel luma hypothesis used for shared
E021/E022 scoring. Only the 100 word sites enter BCH decoding, so dust can
improve or reject a concrete placement hypothesis but cannot grant an
address.

After BCH promotion, the receiver uses the exact multistate labels of word
and dust furniture. Certificates committed before a lane opens may add
known payload components: a CMY7 `main` certificate exposes the complete
C/M/Y tile; each CMY8 certificate exposes only its named C, M, or Y
component. Unknown CMY8 siblings remain masked.

Registration is lane- and capture-local. The E022 pose is the shared sheet
geometry. For each plane, exact known-ink candidates are separated into
word, dust, and pre-lane-certificate classes. Each class is put in canonical
coordinate order and deterministically bounded to 512 candidates by taking
the left edge of each equal-width coordinate bin. A pinned-prior
two-Gaussian blind component fit provides the surrounding 3×3 halos for
those selected candidates, exact furniture/certificate labels override
known components, weighted NCC measures their ink-anchor offsets on a fixed
dot-domain footing, and a robust constant-plus-page-Y residual is fit. The
cap affects registration measurement only; detector training and held-out
validation still use every known site. The residual proposal is adopted
only if total held-out known-state loss improves and the held-out word and
dust losses each do not regress. A certificate used by an adopted proposal
is recorded as an evidence dependency; a certificate minted in the current
lane cannot feed back into that lane.

Sampling is genuinely local. K filters one transient crop per E022 window.
Color uses one transient RGB window for base features, one small raw footprint
per NCC anchor, and one corrected-point footprint plus aperture halo for each
residual proposal. A common region pitch and RGB scale divisor are scalar
facts; the QDA/refinement fit still spans all sampled windows in the region.
No K or color payload stage materializes the bounding box between far-apart
windows, and no page-sized crop cache is introduced.

Setup around those samples is array-based but remains bounded. E022 window
rows align by integer cell keys, 3×3 neighborhood indices use a window-local
lookup, and first-owner selection plus provenance validation operate in
current-frontier/window batches. They retain the same authoritative cell
order, stable first-owner rule, and refusal of non-replayable provenance;
they allocate neither a page raster nor session history.

The selected detector is the production-local port of the historical
equal-prior QDA leaf. CMY7 persists six joint state scores relative to W and
soft-demaps complete four-cell packs. CMY8 marginalizes the eight state
scores to C/M/Y, pools identical scores before isotonic regression, and gives
the two binary classes equal total calibration weight. Stored PAVA score
nodes are strictly increasing; the historical zero/0.5 anchor and finite
probability clamp remain. The printed dust schedule is unchanged. Its
missing-state quota is explained by the W/CM word, but only dust rows fit
PAVA; all 20 one-tile dust rows participate, while word and dust still
train/validate the QDA on disjoint populations with deterministic sparse-state
repair. Both component classes need six labels and two nuisance states with
three labels each. A collapsed component emits exact-zero LLR without
silencing usable sibling planes. A globally
degenerate model emits no informative evidence: its complete `N×3` result is
zero.

The CMY7 demapper still evaluates exactly the 2,048 legal candidate metrics.
It subtracts one common maximum per pack, forms normalized candidate weights,
and obtains all eleven one/zero bit partitions with dense reductions. The
normalization cancels in each log-ratio, so the mathematics is unchanged.
For extreme but finite inputs whose normalized partition underflows, only
those rows fall back to the direct log-domain reduction. Working memory is
bounded to the current tile's candidate bank and small marginal arrays.

One compact physical evidence block stores the observed-cell mask and either
the CMY7 `N×6` scores or CMY8 `N×3` LLRs, plus source/lane/address/origin
provenance. Each new capture block is tried alone (`scan`), then the complete
same-lane frontier is tried as a `union`; ordinary attempts use BP60.
Only the latest eligible ordinary failure is automatically retried at BP150.
`retry150` remains a separate ledger stage for audit, cost accounting, and
idempotence. CMY7 first maps complete-pack support through the exact inverse
interleaver and requires enough structurally supported positions in children
A/B/C separately. This necessary pre-gate prevents soft-demapping a tile that
cannot possibly qualify. A structurally eligible tile is soft-demapped once,
inverts dither/interleaving, and must still have actual nonzero support of at
least 2,240/1,883/1,883 in A/B/C; that post-demap floor is authoritative and
the same LLR vector feeds decoding. CMY8 counts actual nonzero evidence in the
selected plane and requires its active-information count. Physical-cell
counts alone cannot make either codec eligible.

After the complete ordinary color batch, one advisory pre-BP150 close runs
only if at least one new certificate exists, metadata is ready, and every
logical stream has at least `K` distinct ESIs plus at least `K_b` in every
fountain block of a multi-block volume. This gate can prove only that close is
impossible; `close` still decides rank and envelope SHA. A terminal preclose
skips retry150. Otherwise BP150 runs and the lane barrier performs the sole
authoritative persisted close. There are no per-certificate or in-retry
closes.

K and CMY7 have one logical stream, `main`; CMY8 has independent `C`, `M`,
and `Y` streams sharing one physical block. A successful CMY8 stream
suppresses only that stream. Compact numerical evidence is retained until
every row-required stream at its physical address is certified. Current
schema replay reconstructs the same attempt/certificate frontier; close runs
one fountain decoder per declared stream, checks their common metadata, then
reassembles and verifies the ordinary envelope. Terminal color close does not
globally empty the numerical frontier: ordinary per-address retirement remains
identical to K and removes a block only after all required streams at that
address certify. This preserves unresolved live evidence, not a complete
history of blocks already retired normally.

Public save/load for a registered row now performs both generic graph replay
and format-bound validation of scale plans, page domains, BCH conflicts,
payload-site legality, attempt policy, certificate identity, and exact close
reproduction from the certified frontier. Runtime barrier writes may skip the
quadratic full pass only because their delta was already incrementally
validated. Generator composition and color-attempt dispatch use stable codec
IDs rather than Python singleton identity. For CMY8, `N-K` is reported as
repair **symbols per stream**; stream-specific block assignment means it is
not a global source/repair classification of physical tiles.

`holo.qualification.color_distort` is deliberately only a TIFF transformer:
one single-frame 600-dpi RGB TIFF in and one RGB TIFF out. `nominal` and
`stress` are deterministic synthetic shortcuts for dropout, speckle, shear,
crop, blur, RGB noise, and 1200/4800-dpi sampling. With no profile, it starts
from the identity parameters, so an explicit option enables only that
effect. The tool invokes no generator, Ghostscript, receiver, corpus builder,
manifest, or device registry.

`hp-m281-flatbed-cmy` (named `hp-m281-flatbed` until the 2026-08-02 K
split) accepts an unperturbed, threshold-separable production palette,
recovers its binary C/M/Y planes, and delegates to the already-frozen
`paperholo.channel.simulator` M281 + M281-flatbed CAL-1 path. Its sibling
`hp-m281-flatbed-k` accepts a black/white page only and runs the single K
plane through the same pair's bit-faithful `clean_mask` imagemask path,
emitting 1200-dpi grayscale. Both emit 1200 dpi. The inherited simulator is non-streaming and can require several
GiB for a full page. The opt-in Q1 gate checks separately that all four
production rows' clean Ghostscript rasters recover the authored C/M/Y planes
exactly. Profiles must not be stacked.

This reuses the most complete existing parameter set, not a complete color
acquisition oracle. The frozen scanner parameters predate E017.4's
acquisition-breaking 11.3-pixel home-flatbed COLOR-mode comb, and the
simulator's per-level reliability order is known to differ from hardware.
The shortcut is therefore useful qualification material, not a complete
hardware oracle.

The full-page result is retained in
[`COLOR-M281-CAL1-QUALIFICATION.json`](COLOR-M281-CAL1-QUALIFICATION.json).
The receiver committed the acquisition but produced no pose, attempt, or
certificate. That is an operational file-contract check and a negative
channel result, not color receiver qualification.

The opt-in Q1 gate checks every pixel of the four production rows' C/M/Y/K
`tiffsep` plates, including white page margins, and checks exact plane
recovery from each clean production `tiff24nc` raster.

A second opt-in software gate sends every row through production generation,
Ghostscript, the standalone TIFF command's `nominal` profile, the real
receiver CLI, and strict session reload:

```console
HOLO_RUN_GS_COLOR_RECEIVER=1 PYTHONPATH=src env/bin/pytest -q \
  tests/holo/test_color_software_qualification.py \
  -k closes_through_standalone_tiff_transformer
```

It contains no corpus builder, corpus manifest layer, or production
distortion shortcut.

The historical measurements below remain the reason for carrying both
modulations. They are not record claims for these four current rows.

## 0. Historical E017 target

The color twin of the certified K pipeline (016.2): an 8-state CMY
composite page at c3 (200 cpi), pilot-addressed, LDPC-certified,
fountain-coded, blind-decodable from an RGB scan — plus the sim, tests,
golden anchors, and a print-ready ARCH-C sheet (e017). Measured basis:
A3-class composite fields read 1.80–2.15 b/cell raw MI across both
engines (002.2/004.0/007.6) ≈ 112–133 b/mm² — ~1.7–1.9× the K-c3 record,
roughly 1.5–2× the certified K-c2 net path after coding.

## 1. Historical decisions (with the reasoning that froze them)

### D1. Alphabet: 8-state CMY (3 presence bits/cell), NOT 7-state
**STATUS AMENDED 2026-07-10 (run 017.6): ENGINE-GATED.** The first
hardware decode measured the triple catastrophic on the M281 (its own
cells at 25/43/52% level errors; volume not decodable at any ladder
rung) — the anchors below were 7-state fields and mis-priced it, and
P6's revisit condition #1 has FIRED for M281-class engines. 8-state
STANDS for AltaLink-class engines (triple measured a full citizen,
2.208 > best-7 2.138); home-class engines require a triple-free mode:
**pack7 is PROMOTED from upgrade-path to the required c7-c3 build**
(with MLC-successive-decoding and flag-and-erase as decoder-side
complements). Rung-freeze doctrine amended: rungs only from
same-constellation anchors + the per-level MI >= rate check.
The measured MI story is split: home M281 best-7 beats best-8 (1.890 vs
1.801 b/cell, 002.0c — the CMY triple is the most-confused symbol);
AltaLink 8 beats 7 (2.208 vs 2.150, 007.6). We take 8 states anyway,
because of D2: with three independent per-level codewords the modulator
is per-plane bits and the triple occurs at ~12.5% of cells by
construction. The home penalty (≤0.09 b/cell ≈ 5.5 b/mm², measured as
MI) is priced into the per-level rate rungs; the alternative (true
7-ary "pack7": 11 bits → 4 cells base-7 under one code) is the
documented capacity upgrade path, worth building only if a measured
per-level rate ladder leaves ≥~5 b/mm² on the table (P6 probe holds the
decision numbers).

### D2. Coding: three per-LEVEL LDPC codewords per 64×64 tile (PID-MLC)
Each cell contributes one bit to each of three level codewords (C-, M-,
Y-presence). Level = the existing e-IRA n=4096 mother code, shortened by
pilot/dust/edge cells exactly as today, CRC-32-certified per level.
Rationale: (i) the measured per-level reliabilities differ hugely
(trained QDA at the 1200 dpi footing: C ~6.3%, M ~10.2%, Y ~15.9% —
002.2 label-bit view), so per-level rate rungs recover what 002.2 called
the MLC-per-label-bit frame without successive-decoding complexity;
(ii) every existing tile/certification/fountain mechanism reuses
verbatim — a fountain symbol becomes (page, tile, level); (iii) BICM
with a single code needs the pack7 bridge (see D1) — rejected for v1.
Erasure/partial-tile semantics: levels certify independently; a tile may
yield 1–3 symbols.

### D3. Pilots: CP-3 — luma-binary word sites + training dust
(full spec: PILOTS-DESIGN §16; summary here)
- Word sites: the p60b6 lattice (SAME site derivation label — frozen
  contract, no pilot-sites-v3/v4), same BCH(127,50,t=13)→(100,23) window
  code and 18-bit counter; NEW value-scramble label = the v4 format
  identity. Rendering FROZEN BY MEASUREMENT (P1, 017.0): bit=0 →
  all-plane white; bit=1 → the FIXED 2-ink state **CM**. P1 overturned
  the a-priori triple-stack choice: the M281's re-screen dilutes
  per-plane coverage so the 3-ink stack prints LIGHTER than CM (luma 73
  vs 65; W-vs-triple 10.1% vs W-vs-CM 5.8% at the Stage-A statistic),
  while on the AltaLink triple vs CM is a tie (0.92 vs 1.04%) — the
  triple spends a third ink to lose one engine and tie the other.
  Keystream-drawn 2-ink mixtures cost 5–9× vs fixed CM (Y-bearing draws
  are luma-light); any-ink is dead (12–32%). CM is also the
  starved-consumable-robust choice: its luma level is untouched by an
  empty Y cartridge (measured on e006c: W/CM margin unmoved while
  Y-states merge into W), and it survives a single C-or-M death (the
  surviving plane still prints dark).
- Stage-A detection rule (P1, load-bearing): on color pages the pinned
  0.5/0.5 2-GMM is fit on the GATHERED WORD-SITE population (50/50 by
  keystream construction), NOT on all window cells — the all-cells fit
  on a mostly-ink page costs up to 2× BER; the site fit recovers the
  oracle threshold within ~0.5 pp on every dataset measured.
- Bootstrap: Stage 0/A/B run on the LUMA reduction with the K receiver's
  machinery — acquisition never depends on color detection or on any
  single consumable (the 003.0 site-gating lesson: 601/601 site-gated vs
  26% blind-chroma false alarms).
- Training dust: a second, TILE-PERIODIC population, FROZEN at 0.5% of
  cells = 18 sites per 60×60 pilot tile with a per-tile quota of ≥3
  each pure C, pure M, pure Y (P3 measured 0.25% already
  label-sufficient at the Δ≤0.03 b/cell bar on both engines — knee
  ~0.1%; 0.5% carries 2× safety and funds the registration job: P4
  measured pure-plane anchor YIELD at only 15–25% for home Y at the
  2 px/dot footing, and ~100–200 valid anchors/page saturate the v1
  model). Positions seed-drawn per pilot tile and repeated every tile
  (P3: periodic placement measured FREE vs uniform at operating
  densities; periodicity keeps the LDPC shorten-mask derivation
  modulo-based and the fountain symbol size deterministic). Dust STATES
  are keystream-determined per (seed, page, absolute tile index) across
  all 8 states — values never repeat tile-to-tile (R3). Dust carries no
  message bits; consumed post-lock, site-gated, for: (i) the labeled
  training set (blind-EM measured dead — LOOP-C 0.999 vs furniture-QDA
  1.456), (ii) per-plane registration, (iii) PAVA labels per level,
  (iv) a live per-plane consumable canary.

### D4. Detection: dust-trained 8-class QDA → per-level LLRs
Full-covariance QDA on per-cell features sampled from the RGB scan at
plane-corrected grids; feature set (rgb vs rgb+grey) is engine-dependent
— P3 REPLICATED both records on independent data (home: grey 4th
feature +0.041 b/cell; AltaLink: −0.023, rgb-only wins) — and is chosen
AT DECODE TIME by cross-validating on the dust labels themselves
(both ceilings computable from the same dust; no engine identity needed
in the format). **v1 DEVIATION (explicit, 2026-07-10 review): the
shipped receiver exposes `color_features` as a manual caller knob
defaulting to "rgb" (the AltaLink winner); the dust-CV chooser is NOT
implemented — deferred as a 017 open item. A home-M281 decode on the
default leaves the measured +0.041 b/cell on the table until the knob
is set or the chooser lands.**
Per-level LLR = log-marginal ratio over the 8 posteriors. PAVA
calibration on dust labels (the 014.2 pattern; scores IN-SAMPLE from
the full model — **017.5 REVISION: the original cross-fitted variant
is RETIRED WITH DATA.** Cross-fitting fed the map half-model scores
and applied it to full-model payload scores; QDA level-LLR scales are
covariance-determined and differ arbitrarily between fits (measured
100-1000x on a clean render), displacing the map's p=0.5 crossing off
the payload score cloud — whole levels latched to a constant bit =
exactly 50% BER on window-specific clean crops (the e017 selftest M/Y
latch). The map is only meaningful on the score axis it is applied
to. Companion rule: a (0, 0.5) node is anchored into the map when
score 0 falls in a node gap (monotone-preserving) — on separated data
PAVA degenerates to 2 nodes and the interpolated boundary at the
block-mean midpoint sign-flips gap cells on a perfect channel; the
model's own boundary is the honest prior. In-sample calibration
over-states confidence — the known 014.2 direction, 0.03-0.06,
bounded by the 1/(n+2) probability clamp, recorded in diagnostics as
pava_in_sample). Known upgrade paths, out of v1 scope: per-class
mixtures (007.8: QDA is misspecified), a color ctx analog,
failed-tile label recycling.

### D5. Registration: per-plane offset fields from dust
v1 model: per plane, global (dy,dx) + linear-in-y drift, fitted from
pure-plane dust centroids (the CAL-1 drift models are exactly this
shape: Y −0.5→−4.9 dots top→bottom, M −2.6→+1.1, C ±1.1). Fit quality
and sufficiency measured by P4 against the half-cell budget (1.5 dots at
c3). 004.0a's broken cross-plane pooling is thereby answered by
measurement rather than pooling. Common-mode warp stays on the luma
anchors (all planes fuse in one pass — deformation moves them together).

### D6. Emission: composite path on both engines
compose emits three plane bitmaps; the PS job is the characterized
composite (M281: screened contone ~165 lpi, ALWAYS — no escape, H1
sealed; AltaLink: its RIP's behavior as measured in 007.6). Single-plane
imagemask stays K-only. MIC ledger: AltaLink color prints carry tracking
dots (not anonymous); the M281 is measured MIC-free (002.0a) — home
color pages keep anonymity.

### D7. Format identity and registry
layout_version 4 = {cmy8-c3 encoding, p60b6 sites, v4 value labels,
dust}. Implicit signaling doctrine unchanged: the v4 value-scramble
label alone identifies the format (plus per-plane payload keystreams);
v3↔v4 cross-rejection must be verified in tests the way C_v3⊂C_v2 was.
New registry row e017-v4-cmy8 (A4, 2220×1500 cells — e012's page
geometry, 60-divisible, grain properties known).

## 2. Certification plan

Zero-print (this build):
- suite gates: v4 golden sha; determinism; gs tiffsep per-plane
  pixel-exact render; K-format regression untouched (v2/v3 goldens);
  v3↔v4 cross-reject; clean-channel CODED round-trip byte-exact, fully
  blind (acquire → dust-QDA → 3-level LDPC certify → fountain →
  data sha); sim-regime sanity through the measured color channel
  (rescreen + crosstalk + warp).
- probe results P1–P6 recorded in experiments/017-color-channel.md;
  constants frozen from them (word rendering, dust density, features,
  per-level rungs).

Hardware (user steps, pre-registered in the 017 log):
1. FREE FIRST LEG, zero print: Canon 4800 RGB rescans of the EXISTING
   e004 finalists sheet (home) and office color sheets — moves every P#
   anchor from the 2 px/dot flatbed footing to the real footing (the
   014.2 lesson: footing flips verdicts).
2. e017 ARCH-C print (home M281 first — MIC-free engine), Canon RGB
   scans, blind volume decode, data sha match = first color-certified
   bits. Envelope and retraction rules in the 017 log.

## 3. Measured constants and expectations (017.0 probe results)

- Rate rungs FROZEN (P5, pessimistic 2 px/dot anchors, cross-tile QDA):
  C=r0550, M=r0550 (100% block yield both engines), Y=r0547 (the
  measured-weak level on BOTH engines — home Y r0550 yields 89.6% vs
  the 80% fountain threshold at K/N=0.8, i.e. Y leans on repair
  headroom at the worst footing). Canon-footing relaxation (ESTIMATE):
  C r0625–r0700 / M r0700 / Y r0550–r0625 — re-freeze after the RGB
  rescan leg.
- Net projection: **91–103 b/mm² at measured anchors; ~108–117 with the
  Canon footing (ESTIMATE)** — vs the 55.1 certified K-c2 record. Soft
  parallel-decode MI ceiling 135–148 b/mm². Per-level error structure
  measured MLC-friendly: dominant confusions flip exactly one level bit.
- Registration constants (P4, print-frozen, cross-scan corr 0.94–0.996):
  M281 C-plane is globally x-shifted −1.33 dots vs M and Y (the
  per-plane global term is load-bearing: it alone would eat 89% of the
  c3 half-cell budget); Y−C dy −2.55 dots mean with −0.71 dots
  linear-in-y drift; v1 model residuals ≤0.67 dots home / ≤0.91 office
  (=45%/60% of budget) — D5 CONFIRMED both engines; AltaLink carries a
  non-smooth per-plane dx structure (±0.9 dots) flagged as the first
  upgrade if c2-color is ever attempted.
- Acquisition footing (P2): the LUMA lattice lock is NOT threatened by
  screen decoys (165-lpi line contrast ~6, never captures), and
  AltaLink-printed composite locks at K-class quality — but the M281's
  off-lattice re-screen ATTENUATES the c3 luma cell line ~3× (blind
  pitch ID fails on 75% of tiles at the 1200 dpi flatbed footing).
  M281 color decode therefore REQUIRES the Canon 8 px/dot footing
  or a per-plane-channel lock fallback. E017.4's first Canon RGB scan
  confirmed that the clean Canon spectrum rescues acquisition and roughly
  halves per-level BER, but rotated attribution, MTF, and the step catalog
  remain unqualified. Screen-notch estimation comes OFF the critical path.
  Instrument fact: the home
  flatbed's COLOR mode lays an 11.3 px comb that can hijack pitch ID —
  never use home-flatbed color scans for acquisition.
- KNOWN SIM RESIDUAL (IMPL-2 calibration, provenance at
  simulator.CMY_RESCREEN_SIGMA_FRAC): the committed color sim's
  per-LEVEL reliability order is INVERTED vs hardware — sim Y is the
  STRONGEST level (level BER ~19.2/16.6/12.2% C/M/Y at the committed
  test_color_sim construction) while hardware Y is the weakest
  (6.3/10.2/15.9%). The Y-weakness mechanisms (224 lpi clean-path
  texture, development raggedness) are declared M0 TODOs. Per-level
  conclusions (rungs, orderings) come from HARDWARE ONLY; sim tests
  assert ceilings, never orderings.
- 7-vs-8 decision numbers (P6): AltaLink uniform-8 2.208 b/cell beats
  every 7-subset (best 2.138) — the triple is a full citizen on healthy
  engines; home M281 the triple is toxic (own-cell bit BER ~30%, 84% of
  the penalty confined to its own 12.5% of cells — the shape per-level
  soft LLRs down-weight naturally; cheap fallback: flag-and-erase
  triple-sited cells, 0.375 b/cell). pack7 NOT built; revisit needs all
  three conditions in P6's record (M281-class channel as certified
  color target + measured soft-MLC shortfall >10% vs 7-state MI +
  dust unable to flag-and-erase more cheaply).

Nothing above is a record claim until a volume certifies on hardware.

## 4. Out of scope for v1 (recorded so nobody re-litigates silently)

pack7 single-code alphabet (D1 revisit condition); MLC successive
decoding; color ctx detector; per-class mixture detectors; AltaLink
overprint-mask emission path; c2 color (measure first: the M281 screen
period ~3.6 dots exceeds the c2 cell — expected hostile, unmeasured);
duplex; Y-carrier modulation redesign.
