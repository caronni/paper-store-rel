# PILOTS-DESIGN — the L2 pilot system and the page composer (M1)

**v0.3, 2026-07-08** (v0.1 07-07; v0.2 earlier 07-08). Companion to
docs/DESIGN.md §5 (normative baseline) and docs/LAYERS.md v0.2. Status:
**IMPLEMENTED and sim-measured at layout_version 2** (results in
experiments/011-pilot-roundtrip.md: blind end-to-end +1.97 pp over the
geometry-free footing at page scale, grain 15.1 mm placement-guaranteed at
c3@600, zero false accepts), **superseded same-day by layout_version 3**
(§13 — the format-thrift cut: 18-bit flat counter, (100,23) t=13, no
version/plane fields, single-stage full-strength search; decision record in
docs/REASONING-LOG.md "Session 2026-07-08"). v0.2 corrected §6.2 (v0.1's
code spec was arithmetically impossible); §6 below documents the v2 word for
the record — **§13 governs what is printed**. First hardware sheet = exp 012
(ARCH-1). Numbers are labeled **MEASURED** (with experiment.run) or
**ESTIMATE**; rate decisions stay on multi-sheet minima.

Settled questions this document does NOT reopen: pilots exist because v0.2's
marker-free keystream-correlation addressing is mathematically broken (zero
processing gain at the true offset — DESIGN §5.2, REASONING-LOG); the site
pattern must be periodic because pseudorandom sites are circular (§5.2a);
CMY-not-CMYK; the §10.2 trilemma.

---

## The one-page core (read this first)

The whole system is two ideas:

1. **Known cells for registration.** ~2.78% of cells (one per 6×6-cell
   block, seeded offsets, pattern repeating every 60 cells) are *known* at
   the decoder. Finding them = registration: the decoder locks the cell
   lattice from the data itself (gradient-FFT), then tests the 60×60 possible
   site phases × 4 rotations; only the true one makes the known cells decode.
   After the lock, the same cells are warp anchors (they carry both dy and
   dx, have no integer ambiguity, and work at page edges where self-clocking
   dies) and free channel probes.
2. **A coded counter for addressing.** The 100 known cells inside each
   60×60-cell tile spell one error-corrected word: an 18-bit flat counter =
   page × tiles-per-page + tile-index — i.e. "which tile of which page am I"
   (layout_version 3, §13; nothing else is signaled — format and plane are
   identified implicitly by which registry entry's descrambler makes the
   word decode). Any fragment containing one whole tile self-locates
   absolutely; neighbors must agree (cheap validation, kills false locks).
   Higher layers map the address to fountain-code symbol indices; no headers
   anywhere.

Everything else in this document is the engineering that makes those two
ideas survive the measured channel: which plane carries the cells (K; Y
rejected), how values are scrambled so acquisition isn't circular
(site-local, tile-periodic keystream), why the code is a shortened BCH and
how hard it may be pushed during search (t_acq: 8 at v2, full-strength 13 at
v3 — §13), what a fragment smaller than one tile can and cannot do, and what
it all costs (2.78% area).

**Terminology (2026-07-10 ruling, user decision):** the P×P-cell unit of
the pilot lattice (60×60 cells; 100 sites carrying one BCH word) is a
**pilot tile** — the names "period tile", "word tile", and "tile slot" in
older logs and docstrings denote the same object and are deprecated.
"Word" alone always means the BCH codeword (the content, never the
geometry); "period"/P survives only as the 60-cell repetition length; the
64×64-cell inner-FEC unit is always qualified as the **LDPC tile** (=
payload tile = one fountain symbol). The two grids are deliberately
misaligned (§6.6).

---

## 0. Summary of recommendations

1. **Site lattice fix: PERIOD = 60, BLOCK = 6** (`p60b6`), density exactly
   1/36 = 2.78%, 100 pilots per pilot tile — a layout_version bump
   (v1 → v2), not a hotfix. PERIOD stays 60 across all modes; BLOCK becomes
   the robustness knob (B ∈ {6, 5, 4} → 2.78 / 4.0 / 6.25%).
2. **Pilot cells are whole known cells** (all planes specified at the site),
   overlaid into the payload lattice by the composer; they displace payload
   cells one-for-one.
3. **Plane assignment:** K pilots in K fields; co-located all-plane known
   cells in CMY fields; an optional C-on-white rail for the BW path
   (dual-rail, §4.3c); **Y pilots rejected** (§4.5, three measured reasons).
4. **Window code:** per-pilot-tile coordinate words in **shortened
   BCH(127, 64, t = 10) → (100, 37)** (v0.2 correction — see §6.2),
   site-local scrambling, two-stage decode with a reduced acquisition radius
   t_acq = 8 and mandatory whole-fragment validation. Addressing grain
   MEASURED (011.0, sim): 15.1 mm placement-guaranteed / ~13 mm at ~60%
   placement odds at c3 on the 600-dpi engines (the DESIGN §5.3 “3×3 mm”
   assumes the 1200-dpi design target).
5. **Pilots supersede strips** as the tracking anchor set at M1 via a
   one-sheet-per-engine hybrid validation (§2.3); strips remain bench
   furniture, never archive furniture (R3).
6. **Tool 5 = `paperholo.compose.compose_page`** (§8): payload bits +
   FormatDescriptor in, per-plane bitmaps + manifest out; pilot furniture,
   capacity accounting, and layout_version all live there.

---

## 1. Roles — and which role drives which constraint

Pilots do four jobs. Conflating them produced the current stub's bug (a
site pattern designed for addressing that leaves anchor-free stripes,
harming tracking). Each role, and the design constraint it owns:

| role | what it needs | constraint it drives |
|---|---|---|
| (a) **warp-tracking anchors** | known cells at bounded spacing, uniform coverage, legal (no GT, no payload dependence) | site **density and uniformity** — no pilot-free stripes (the PERIOD/BLOCK bug directly injures this role); per-plane presence; anchor spacing sets the interpolation residual (§2.2, s² scaling) |
| (b) **absolute addressing** (window code) | enough known-value bits per unit area to decode ~36 address bits through the raw channel | site **periodicity P** (the ≤P² hypothesis bound, F7), window bit budget per pilot tile, BCH margin vs measured raw BER (§6) |
| (c) **orientation / mirror resolution** | a chiral site pattern + values that fail to decode under rotation/mirror | value structure: non-degenerate scrambled codewords; bounded 8×P² search; false-accept control (t_acq + Stage-B validation, §6.4) |
| (d) **channel monitoring** | nothing extra — known cells are free probes | drives nothing structural; delivers per-region measured BER for rate adaptation, recal maps, multi-scan weighting, and the canary discipline |

Role (a) is what strips do today and is the measured pain point (mid-gap bow,
007.7). Role (b) is what nothing does today (bench sheets use the jobid
manifest — not archival). Roles (c) and (d) come nearly free once (a) and (b)
are designed correctly. The doctrine boundary stands: **pilots/strips
MEASURE registration; codes CERTIFY it** (F9) — no pilot subsystem output is
terminal until an LDPC tile CRC passes.

---

## 2. Placement schemes

### 2.1 Scattered site lattice — the divisibility fix

Current stub (`pilots.py` v1): one pilot per 6×6-cell block at a seeded
offset, offsets repeating with PERIOD = 64. Because 64 = 10·6 + 4, each
period axis ends in a 4-cell **pilot-free stripe**: density 2.44% instead of
the specified ≈2.78% (MEASURED, code inspection; recorded in DESIGN §5.2
v0.4 note), the per-window bit budget is thinned ~12%, and — the role-(a)
injury — the stripes concatenate into anchor-free bands 4 cells wide every
64 cells. The site pattern is format-axis: the fix is a **layout_version
bump** (v1 → v2 in the site-derivation label, §6.3), never a silent edit.

Concrete (PERIOD, BLOCK) options at c3 on the measured engines
(cell = 3 dots @ 600 dpi = 0.127 mm; 62.0 cells/mm²). “Window budget” =
pilot sites per pilot tile; “grain” = side of the ~70-pilot-bit window the
§6 code needs (ESTIMATE from density; §6.5):

| layout | divisible | density | pilots / pilot tile | P² hypotheses | pilot tile (mm, c3) | grain side (mm, c3) |
|---|---|---|---|---|---|---|
| p64b6 (current bug) | NO | 2.44% | 100 (striped) | 4096 | 8.13 | 6.8 |
| **p60b6 (recommended)** | yes | 2.78% | 100 exact | 3600 | 7.62 | 6.4 |
| p48b6 | yes | 2.78% | 64 | 2304 | 6.10 | 6.4 (word no longer fits one tile — needs a weaker (64,36) code or 2-tile words) |
| p72b6 | yes | 2.78% | 144 | 5184 | 9.14 | 6.4 (budget surplus; larger tile = larger guaranteed-acquisition fragment) |
| p64b8 | yes | 1.56% | 64 | 4096 | 8.13 | 8.5 (density below the §5.2 spec; thin anchors) |
| p60b5 (robust) | yes | 4.00% | 144 | 3600 | 7.62 | 5.3 |
| p60b4 (robust) | yes | 6.25% | 225 | 3600 | 7.62 | 4.3 |

**Recommendation: p60b6 as the layout_version-2 nominal.** It preserves
DESIGN §5.2a's one-per-6×6 / ≈2.8% exactly; 100 sites per pilot tile fits
one BCH(100, 37) word with no residue (§6); P² = 3600 hypotheses is trivial;
and 60 has divisors {4, 5, 6, 10, 12} so **PERIOD is frozen across the whole
mode ladder and BLOCK alone is the density knob** — acquisition machinery,
word framing, and the hypothesis search are identical in every mode. A happy
alignment: the e006 strip pitch (360 dots = 120 c3 cells) is exactly two
pilot tiles, so the §2.3 hybrid sheet has strips landing on pilot-tile
boundaries. The one cosmetic mismatch: the LDPC tile (64×64 cells, DESIGN
§6) does not align to the 60-cell pilot tile — harmless, both grids are
derived from the same absolute frame once addressing is solved (§6.6).

### 2.2 Row-continuous anchors — what the bow data says pilots buy

The measured record that motivates scattered anchors over strips:

- Strips at 360-dot pitch (15.24 mm), linear interpolation between them:
  **+5.82 pp** B1 ctx BER vs genie (home, MEASURED 006.1; band range +0.8 to
  +16.0) and **+3.37 pp** (AltaLink, MEASURED 007.6), same mid-gap
  signature — BER doubles 108–168 dots from a strip.
- The GT-instrumented mechanism (MEASURED 007.7): true dy(y) **bows up to
  −2.3 dots at mid-gap** — more than half a c2 cell; linear interp is exact
  at strip endpoints and worst mid-gap.
- The designed fix inside the strip world — between-strip payload self-clock
  refinement — is **engine-conditional** (MEASURED 007.7/007.8-C4): home
  +1.6 pp single-scan / +2.05 pp 3-scan (B1 79.7 b/mm²), but AltaLink
  **−4.5 pp (harmful)** because that print's <5-dot feature erosion weakens
  the c2 payload lattice the self-clock feeds on; no blind global gate
  separates the engines.

The scaling argument. For a smooth warp component with curvature κ, linear
interpolation over an anchor gap g leaves peak residual ≈ κg²/8. The
measured 2.3-dot residual at g = 360 dots calibrates κ for this channel, so
residual(s) ≈ 2.3 · (s/360)² dots for anchor spacing s. Pilots at p60b6
give one known cell per 6×6-cell block; aggregating 3–4 block-rows into one
anchor band (18–24 cell rows = **54–72 dots** at c3, with 10 pilots per
60-cell width per block-row to average over) yields:

| anchor spacing s | expected smooth residual (ESTIMATE, measured-κ scaling) |
|---|---|
| 360 dots (strips) | 2.3 dots (MEASURED anchor point) |
| 72 dots (4 block-rows) | 0.092 dots |
| 54 dots (3 block-rows) | 0.052 dots |

i.e. **~25–44× smaller smooth residual than strips-alone**, comfortably under
every constellation's cell/2 budget. Two further advantages over the
between-strip stage, both grounded in measured failure modes:

1. **Legality and engine-robustness.** Pilots are known cells — anchor
   quality does not depend on payload lattice health, so the AltaLink
   between-strip failure mode (payload self-clock on an eroded c2 lattice)
   does not apply. Anchors carry their own per-site quality weights (§5).
2. **Steps and x.** The scanner's stochastic transport steps (up to 1.95
   dots, MEASURED 001.4/002.0b) are not smooth — no interpolation model
   crosses them. Anchors every 54–72 dots localize each step to one small
   gap for the F3 y-profile re-estimator, where strips leave 360-dot
   ambiguity windows. And pilots measure **(dy, dx) both**: the x-bow that
   was catastrophic from payload self-clock (007.7 — a narrow x-sub-band of
   a random field has no lattice signal) is legal from known cells.

Caveat, honestly: per-pilot centroid precision is UNMEASURED — the 0.05–0.09
dot residual bound assumes anchor-band noise beaten down to that scale by
averaging ~30–40 pilots per band (ESTIMATE; single-cell matched-filter
centroid noise ~0.3–0.5 dots would suffice — M-P3 in §9 measures it).

### 2.3 Hybrid strip+pilot transition plan (strips today → pilots at M1)

Phase 0 (today): strips, measured and frozen (lock 1.00 on every real scan,
both engines — LAYERS §4). Phase 1 (M1): **PILOT-1 validation sheet** — one
print per engine carrying BOTH the 17-strip skeleton AND p60b6 pilots over
B1 + A3 payload bands, so pilot-anchored tracking is scored against
strips-alone, strips+refinement, and genie **on the same sheet** (§9, M-P3).
Acceptance gate: pilot-anchored ctx BER within 1 pp of genie on interior
bands on both engines (ESTIMATE target from §2.2; outside-envelope =
finding). Phase 2: pilots become the primary tracker anchor set
(LAYERS §4 “supersedes strips”); strips stay on bench/loop pages only —
they are visible structure and were always an R3 concession; archive sheets
carry pilots alone.

---

## 3. Density / robustness ladder and overhead accounting

Pilot density is a **per-mode format parameter** (format axis — set at
compose time, immutable on paper):

| mode | layout | density | paired constellation | acquisition grain (c3/c4) | rationale |
|---|---|---|---|---|---|
| HD (nominal) | p60b6 | 2.78% | A3 c3 / B1 / B2 | 6.4 mm (c3) | DESIGN §5.2's ≈2.5–2.8% tax; word margin ~4× at c3 raw BER (§6.2) |
| robust | p60b4 | 6.25% | c4-class (A4, coarse-K) | 5.7 mm (c4) | coarser cells + denser anchors; 225 sites/tile = word + 125 pure-anchor sites; survives c2-class raw BER with duplicated words (§6.2) |
| (intermediate) | p60b5 | 4.00% | optional | 5.3 mm (c3) | defined for completeness; only freeze if a measured need appears |

Overhead vs tracking-residual bookkeeping, per scheme:

| scheme | area overhead | residual vs genie | net verdict |
|---|---|---|---|
| strips-alone | 1.67% (3-row c2 strip / 360 dots) | +5.8 pp home / +3.4 pp AltaLink B1 ctx (MEASURED) | cheap, measured, geometry-poor |
| strips + between-strip refi | 1.67% | +2.8 pp home (MEASURED 007.7); HARMFUL office | engine-conditional, needs per-band gate |
| pilots p60b6 | 2.78% | ~0–1 pp (ESTIMATE, §2.2; M-P3 measures) | +1.1 pp of area buys the geometry AND addressing AND monitoring |
| pilots p60b4 | 6.25% | <0.05 dots smooth (ESTIMATE) | robust mode only — the tax is real |

A 5.8 pp ctx-BER handicap costs far more mutual information than 1.1% of
area (B1 at 12.65→10.60% ctx was worth +7 b/mm², MEASURED 007.7) — the
pilot tax pays for itself if §2.2's prediction holds even loosely.

**Thinning under F9 (codes certify registration).** Once LDPC tiles decode,
CRC-passing tiles certify geometry and decoded cells become anchors (F10),
so in principle pilots could thin. But density is format-axis — it cannot
adapt at decode time, only at compose time. The doctrine therefore cashes
out as: (i) do NOT add density for tracking beyond what acquisition needs,
because the decode loop bootstraps (pilots acquire → tiles decode → decoded
cells densify the anchor set); (ii) a below-2.78% mode (e.g. p64b8, 1.56%)
is only admissible after M2 demonstrates the bootstrap on real scans —
until then 2.78% is the floor. Pilots measure, codes certify; thinning is a
bet that certification arrives early, and it stays unfrozen until measured.

---

## 4. Plane assignment

### 4.1 K pilots in K fields — baseline

For B1/B2/P-cons profiles, pilots are K cells carrying known values through
the same constellation as the payload (a c2 pilot cell is a 2×2-dot ink/no-
ink decision, etc.). They ride the measured K channel: c3 2.5–3.7%, c2
11–14% hard / 4.6–8.2% ctx (MEASURED, multi-sheet — CLAUDE.md ladder). No
new physics, no new emission path, zero R3 cost beyond the site periodicity
already conceded. This is the nominal assignment for K-only pages —
which are also exactly the pages the AltaLink prints MIC-free (007.8-C1).

### 4.2 Colored pilots — the measured record (003.0)

- **S3 (C pilots in 4×4-dot voids at pilot_sites density, K c3 field):
  601/601 recovered** at the S2 threshold; chroma d′ pilot-vs-white 4.7,
  pilot-vs-ink 3.1 (MEASURED 003.0).
- **Site-gating is mandatory**: a blind chroma sweep at the same threshold
  false-alarms on **26.5% of K-ink cells** (2.4% on white) — the pilot
  minimum sits below the max of ~24k data cells (min margin −0.589). Blind
  chroma detection is dead; detection is only defined AT known sites (§5).
- **The void tax**: pilot-margin K cells read BER 7.44% vs 2.66% clear
  (same sheet c3 2.53%) — the enforced void's left-column/top-row spill.
  And from S2/S1: void-adjacent K ink misses at **25–27% vs ~15% far-field
  in BOTH fields** — the void itself, not the C mark, stresses neighboring
  K development (MEASURED 003.0 H2; single replicate, repeat wanted).
- **No C→K coupling**: S2 K BER at C-mark sites is not worse than the S1
  control at the same sites; the b-channel (C-blind) shows the same global
  shift (MEASURED 003.0 H2).

### 4.3 C (or M) pilots on white cells in the BW-only data path

The attractive idea: in a K-only archive, put chroma pilots on WHITE cells —
the C mark survives (556/557, 0 FP, MEASURED S2), it is K-invisible, and if
the cell was going to be white anyway there is no void tax. The catch is a
data-dependence problem: **which cells are white moves with the payload.**
Three resolutions, analyzed:

**(a) Reserved always-white sites in the format.** The site is white by
construction; the C mark needs no enforced clearing beyond what the format
already guarantees. But “always-white site” IS an enforced void — it pays
the measured void tax (25–27% miss on adjacent K ink vs 15%; margin cells
+4.8 pp) at every site. At 2.78% density with ~2–3 margin-affected neighbor
cells per site, that is an effective extra ~6–8% of cells carrying a
degraded channel (ESTIMATE from the S3 margin split) — a real, measured
price. Verdict: acceptable ONLY at sparse acquisition density, not for
dense anchor duty.

**(b) Opportunistic pilots on payload-white cells.** Zero void tax: the
mark lands where the scrambled payload already put white (≈50% of cells,
i.e. abundant). But placement is known only after the payload is (partially)
decoded — **chicken-and-egg**: unusable for acquisition or first-pass
tracking. Usable as a REFINEMENT anchor set, F4-style: once a first decode
pass yields confident white cells near a region, C marks at
keystream-selected payload-white sites give legal, known, dense anchors for
a second tracking pass. This is exactly the between-strip idea with the
payload-lattice fragility removed — but it requires the encoder to have
placed the marks, which requires the ENCODER to know the payload (it does)
and commits the format to data-dependent furniture (the site set is
payload-derived; the DECODER re-derives it only after descrambling — fine,
that is the F4 stage by definition).

**(c) Dual-rail (recommended if the BW path wants chroma at all):** a
sparse reserved rail — reserved-white C sites at 1/12×12 cells ≈ 0.7%
density (ESTIMATE; ~4× sparser than p60b6) — carries acquisition +
coarse anchors and pays the void tax only at that sparse density; plus
opportunistic densification per (b) for the refinement pass. Capacity
math: 0.7% reserved + ~2% margin-degraded (ESTIMATE) vs the pure-K
alternative of simply running p60b6 K pilots with zero new physics.

**Position:** the K-pilot baseline (§4.1) remains nominal for the BW path;
the C rail is a designed OPTION whose one honest advantage is channel
diversity (an anchor set that survives K-plane closure days — the c2
white-closure canary, 004.0/005.0) and whose price is measured (void tax) —
freeze only if M-P4/M-P5 (§9) measure a net win on a real closure-day sheet.

### 4.4 C vs M for the chroma rail

Choose **C**. Measured basis:

- C detection SNR is measured and strong: d′ 4.7 vs white in the r-channel
  discriminant s = D_r − max(D_g, D_b) (MEASURED 003.0 S3). M as a pilot
  mark is UNMEASURED, and carries two strikes: the M281 unmix taxes M
  (MEASURED 002.2 — “unmix rescues Y, taxes M”), and on the AltaLink scan
  path **M clips at the scanner g-floor** (MEASURED 007.6/007.8-C2 — the
  very channel M pilots would be detected in; it broke QDA Gaussianity on
  LOOP-C).
- C on white involves the r channel where both engines' C planes are their
  healthiest measured selves (c3 isolated: home C 3.6%, AltaLink C 4.5% —
  007.9 table).

### 4.5 Y pilots — REJECTED

Three measured reasons, in increasing severity:

1. **Weak contrast.** Y is the weak plane everywhere it was measured: 7.2%
   isolated c3 / rate 0.55 on M281 CAL-1 (MEASURED 002.0); even healthy
   AltaLink Y (5.5%) trails C/M-class detection; Y-axis confusions are the
   measured capacity limiter of the composite alphabet (007.7/007.8-C2).
2. **Consumable fragility.** The 006.2 starved-Y event (Y solid D 0.374 =
   half of CAL-1's already-weakest 0.772, monotone fade, alphabet MI
   halved) is the recorded proof that Y is the first consumable to silently
   die. An anchor/addressing subsystem must not ride the most fragile
   consumable on the sheet.
3. **MIC collision (AltaLink).** The AltaLink lays a yellow tracking
   lattice on every color-content page: 24×24-dot cell, ~31×16-cell
   super-tile, 0.24/mm² (MEASURED 007.7/007.8-C1). Y pilots at p60b6 c3
   density are 1.7/mm² (1.51/mm² at the buggy 2.44%) — same plane, same
   scan channel (D_b), only ~7× denser: two interleaved sparse yellow dot
   lattices on one sheet. Distinguishability analysis: OUR decoder is fine —
   site-gating + the keystream-scrambled window code make pilots
   identifiable and the MIC lattice is periodic and rejectable (site-gated
   detection absorbs it; LAYERS §2 already calls it channel-absorbable).
   But (i) detection-side confusion is real for the FALLBACK paths — the
   §5.2b FFT correlator over a sparse Y point set would see the MIC comb as
   structured interference at comparable spatial frequencies (ESTIMATE,
   untested); and (ii) forensic ambiguity cuts both ways — our Y dust
   invites MIC-style scrutiny of archive sheets, and any future MIC-removal
   tooling would eat our pilots (R3 concerns). With C measured-good and K
   free, Y pilots have no compensating upside. REJECTED.

**Per-plane sync in CMY fields (A3/A4):** pilot cells are co-located whole
known cells (§0 rec. 2) — every plane gets a known component at the same
site, so inter-plane offsets (the measured per-plane registration bias that
broke naive cross-plane phase pooling, 004.0a) are measured DIRECTLY at
every pilot site as differential centroids. Y still carries pilot-cell
components (as part of known 7-state symbols — that is payload-class
content, not the addressing rail); the ADDRESSING word is read from the C/M/K
components only, and Y's registration rides the frozen-at-fuse fact
(DESIGN §2.5) plus the co-located differential measurements.

---

## 5. Detection

**Site-gated matched filter, never blind.** Detection is only defined at
hypothesis-selected sites (the ≤P² search, §6.4). The measured basis: blind
chroma trips on 26.5% of K-ink cells (003.0 S3); the site-gated same
threshold recovers 601/601. For K pilots the “matched filter” is simply the
payload constellation's own detector evaluated at known cells; for C marks
it is s = D_r − max(D_g, D_b) with the threshold set from an on-page null
(S1-null median + 4σ — the S2/S3 rule, MEASURED 003.0). On JPEG-compressed
scan paths (AltaLink scanner), <5-dot features are erased (007.2): 2×2-dot
pilot marks and c2 pilot cells are NOT detectable there — pilot decode
requires an uncompressed scan path (home flatbed or fixed office profile),
same as archive-grade payload decode (LAYERS §8 rider).

**Into the tracker as quality-weighted LLRs.** Each pilot yields (i) a
value LLR from the constellation detector and (ii) a centroid offset
(dy, dx) with a per-site quality weight (matched-filter peak sharpness /
residual). Anchor bands (§2.2) fit the local warp by quality-weighted
regression — the exact idiom validated in between_strip.py
(quality-weighted quadratic, forced through bracketing anchors), minus the
payload-dependence. Low-quality sites are downweighted, not imputed;
per-scan pilot agreement supplies the multi-scan combining weights
(004.0b protocol) and the per-region recal/rate-adaptation input (role d).

**FFT fallback acquisition (DESIGN §5.2b).** When local damage defeats
window decoding, the pilots at a hypothesized site-phase form a sparse KNOWN
sequence (after §6.3 descrambling) — classical correlation with processing
gain, ≤P²·8 hypotheses locally; volume-wide search ~10¹²–10¹³ ops ≈ minutes
on one GPU per stubborn fragment (DESIGN ESTIMATE, unchanged).

**Keystream-gated polarity = orientation check.** Pilot values are known
once the address hypothesis is fixed (§6.3), so the whole pilot population
doubles as a polarity/orientation witness: at the true orientation the
pilot mismatch rate ≈ channel BER (2.5–14% depending on constellation); at
a wrong rotation/mirror it sits at ~50%. This implements F12 without
touching payload, and the same statistic IS the role-(d) channel monitor.

---

## 6. Window code — `pilots.coordinate_code` specification

Implementation-ready; code itself is M1 scope. Design goal: any clean
~70-pilot-bit window decodes to an absolute address; everything below is
deterministic in (seed, layout_version).

### 6.1 Address space and word layout

Message m = 36 bits:

| field | bits | range | note |
|---|---|---|---|
| layout_version | 4 | 16 versions | printed format self-identifies |
| plane_id | 2 | K/C/M/Y | per-plane words (DESIGN §5.4) |
| page | 18 | 262,144 sides | >260 duplexed reams; extend by version bump if ever needed |
| ptile_y | 6 | 64 | pilot-tile row (A4 at c3: 38 used) |
| ptile_x | 6 | 64 | pilot-tile col (A4 at c3: 27 used) |

Total addressable: 2²·2¹⁸·2¹²·3600 cells ≈ 1.5×10¹³ — covers DESIGN §5.3's
~10¹⁰-cell volume with margin. In-tile position comes free: the site-phase
hypothesis (§6.4) already fixes the cell-level phase, so the word only needs
tile granularity.

### 6.2 Code choice (v0.2 CORRECTION — v0.1's spec was impossible)

v0.1 specified "BCH(127, 36, t = 15) shortened to (100, 36)". That object
does not exist: shortening removes *information* positions, so shortening
(127, 36) by 27 yields (100, **9**), and a (100, 36) code with the claimed
d ≥ 31 exceeds best-known linear-code bounds (tables give d ≈ 24 at that
length/dimension). The frozen, implemented code is:

**BCH(127, 64, t = 10) over GF(2⁷) (primitive poly 0x89), shortened by 27 →
(100, 37)** — 36 message bits + 1 zero pad bit (a free false-accept filter),
d ≥ 21, corrects e errors + f erasures whenever 2e + f ≤ 20. One codeword per
pilot tile, one code bit per pilot site in seed-fixed raster order over the
tile's 100 sites (p60b6: exactly 100, no residue). The t_acq = 8 Stage-A
arithmetic survives the correction: per-hypothesis false accept ≈
2³⁷·V(100,8)/2¹⁰⁰ ≈ 2.3×10⁻⁸ (MEASURED 011.0: 0/200,000 random words at
t_acq = 8; zero false accepts across the whole sim sweep, all wrong
rotations/seeds/planes rejected).

Margin vs the measured channel (binomial tails at MEASURED raw BER;
sim-MEASURED where marked):

| channel | raw BER | expected errors / 100 | word failure (t=10) |
|---|---|---|---|
| c3 K/C/M (both engines) | 2.5–3.7% | 2.5–3.7 | ~10⁻⁵–1.5×10⁻³; sim-MEASURED 011.0: 80–81/81 tiles decode at page scale |
| c2 hard | 11–14% | 11–14 | hopeless — unchanged verdict |
| c2 ctx-detected | 4.6–8.2% (home, day-range) / 5.5% (AltaLink) | 5–8 | ~1.4% at 5%, **~18% at the 8% day-2 tail — materially weaker than v0.1's t=15 claim; the robust-mode word duplication (M-P6) is now LOAD-BEARING for B1, not optional margin** |

Consequences, made explicit: at c3-class constellations the word is
overprovisioned (good — it is also the erasure budget for damaged
fragments). At c2-class (B1, robust profiles) acquisition uses
**context-detected pilot bits** (the ctx detector needs no GT — measured
legal since 001.4) and the **robust mode duplicates the word**: p60b4's 225
sites carry the 100-bit word on a fixed seed-chosen subset, a second
interleaved copy on the next 100, and 25 pure-anchor sites; bitwise LLR
combining of the two copies before BCH roughly squares the error rate per
bit (ESTIMATE; M-P6 simulates). On JPEG-class scans the context detector
misfires (007.2) — hard-decision pilots + the full t = 10 budget is the fallback
there.

### 6.3 Values, scrambling, and the acquisition circularity

A naive “pilot value = code bit ⊕ keystream(absolute address)” is circular:
the keystream needs the address the pilots are supposed to deliver. The
resolution — and the printed-value definition — is **site-local
scrambling**:

```
v(site) = c(site) ⊕ ks_P(plane_hint, site_index_mod_P)
```

where c is the BCH code bit for that site (raster order within the pilot
tile), and ks_P is a public keystream derived as
`rng(seed, b"pilot-values-v2" + plane_label)` over the P×P = 3600 site-index
classes — **periodic with P, hence removable under any site-phase
hypothesis** without knowing the absolute address. The coordinate word
itself never repeats (it encodes the tile index), so printed pilot values
never repeat (R3: the site pattern's 1/P spectral lines are the already-
conceded cost, DESIGN §5.2a; the values add no further structure —
ESTIMATE, spot-check in M-P1). Site derivation likewise versions its label:
`blake2b(seed + b"pilot-sites-v2")` so v1/v2 patterns cannot collide.
All randomness flows from the explicit seed (repo rule).

### 6.4 Decode procedure and budget

```
Stage 0  lattice lock (L2 geometry: §5.1 self-clock / strips / prior warp)
Stage A  for each of ≤8 orientations × P² = 3600 site phases (28,800 max):
           extract pilot bits at hypothesized sites (1 window, ~1–4 tiles)
           descramble with ks_P; BCH-decode each visible tile word with
           ACQUISITION RADIUS t_acq = 8 (not 15)
           → candidate address(es)
Stage B  for each candidate: regenerate ALL expected pilot values across
         the fragment (adjacent tiles' words are determined — tile indices
         differ by 1); require match rate ≥ 85% over ≥ 30 additional sites
         → accepted address + orientation resolved (F12) + measured pilot
           BER (role d)
Terminal F9: the first CRC-passing LDPC tile certifies the geometry/address.
```

Why t_acq = 8: at full radius t = 10 the per-hypothesis false-accept
probability is ≈ 2⁻⁶ (2³⁶ codewords × V(100,15)/2¹⁰⁰ — ESTIMATE), which
across 28,800 hypotheses would drown Stage B in candidates. At t_acq = 8 it
falls to ≈ 10⁻⁸ per hypothesis (~10⁻⁴ per full search) while still covering
4–8× the expected c3 error count. Stage B then re-decodes accepted tiles at
the full 2e + f ≤ 20 budget (erasure mode is a declared v1 gap — the
implemented decoder is errors-only; erasure support is queued behind the
first damaged-fragment use case) for damaged-fragment recovery.
Compute budget: ≤28,800 × (100-bit extraction + syndrome) ≈ 10⁷ ops per
acquisition attempt — microseconds-class; the §5 FFT fallback handles the
low-SNR tail.

### 6.5 Acquisition grain

Two regimes (all c3 @ 600 dpi; the DESIGN §5.3 3×3 mm figure is the same
cell count on the 1200-dpi design-target engine):

- **Typical (Stage A+B pooled):** ~70 readable pilot bits anywhere →
  70/0.0278 ≈ 2,500 cells ≈ **6.4×6.4 mm** (p60b6). Robust mode p60b4:
  4.3 mm; c4 robust: 5.7 mm.
- **Guaranteed (worst-case alignment, Stage A alone):** a fragment must
  contain ≥ ~70 of one tile's 100 sites; worst-case placement needs side
  ≈ 1.7·P ≈ 100 cells ≈ **13 mm** (ESTIMATE, geometric argument). Stage B's
  cross-tile pooling closes most of the gap between the regimes; M-P1
  measures the empirical crop-size curve on simulator + real scans.

Combined with the 64×64-cell LDPC tile (≈8.1×8.1 mm at c3 @600), the
effective holographic grain on the measured engines is ≈ **10×10 mm**
(ESTIMATE) — the §5.3 “≈4×4 mm” again assumes the 1200-dpi target engine.
This is a fact of the 600-dpi engine class, not a design regression; it
goes in the DESIGN amendment (§11).

### 6.6 How ESI consumes the decode

Window decode yields (plane, page, ptile_y, ptile_x) + in-tile phase →
absolute cell address for every locked cell → LDPC tile index =
(cell_y ÷ 64, cell_x ÷ 64) in the same absolute frame → **ESI = F(plane,
page, tileX, tileY)** (the fixed public bijection, LAYERS §1; headers
rejected 2026-07-06). Pilot tiles and LDPC tiles need not align (§2.1);
both are pure functions of the absolute address. Partial LDPC tiles at
fragment edges decode or erase on their own LLR merits — L3's business.

---

## 7. Compatibility matrix — pilots column expanded (proposal for LAYERS §8)

| constellation | pilot plane/form | acquisition path | anchor duty | notes & measured basis |
|---|---|---|---|---|
| B1 (c2 K) | K pilots = known c2 cells | ctx-detected bits; robust mode duplicated words (§6.2) | supersedes strips (§2.3); anchor bands per §2.2 | c2 raw 11–14% forces ctx acquisition; c2 is the channel canary — pilot BER doubles as the day-drift monitor (004.0/005.0). REQUIRED density ≥ p60b6; p60b4 recommended (MEASURED word-margin analysis §6.2) |
| B2 (RLL i2w3, free-form dots) | K motif pilots: known RLL-legal motifs at DOT-grid sites (one per 48×48-dot block, period_dots = 480 → 100 sites/pilot tile (dot-grid analog), same word math); value = 1-bit position modulation (motif at one of two in-block offsets) | site-gated only — **no self-clock exists at 2 px/dot** (MEASURED 004.0a; LAYERS §8) | REQUIRED (pilots or strips); 48-dot anchor spacing lands in the §2.2 target band | motif choice from the survival library: ink_domino_v survives 0.947 (MEASURED 003.0 H4); footprint incl. min-white-3 clearance ≈ 80 dots → ≈3.5% area at 48-dot blocks (ESTIMATE); grain ≈ 17 mm (coarse — B2 is the robustness profile); the constraint-legal void-tax analog is UNMEASURED (M-P4) |
| A3 (7-state c3 CMY) | co-located whole known cells (all planes); word read from C/M(/K) components | c3-class margins — word overprovisioned (§6.2) | per-plane offsets measured differentially at every site (fixes the 004.0a per-plane bias that broke phase pooling) | M281: payload self-clock BROKEN by the 165-lpi screen (MEASURED 004.0a) → pilots are the ONLY legal in-field anchor; AltaLink: composite unscreened (007.6), self-clock untested — pilots still required for ADDRESSING regardless |
| A4 ({7+K} c4) | as A3 | c4 robust mode p60b4 natural pairing | as A3 | K↔CM confusion (AltaLink, 007.6) does not touch pilot detection — known cells are classified against 2 hypotheses, not 8 |
| BW path chroma option | C-on-white dual rail (§4.3c) | reserved rail ~0.7% + §6 word on the K pilots | opportunistic densification = F4 refinement | void tax MEASURED (003.0); net win unproven — freeze gated on M-P4/M-P5 |
| robust mode (any) | p60b4, 6.25%, word duplicated | t_acq unchanged; combining halves effective BER (ESTIMATE) | densest anchors | pairs with coarse cells by design (§3) |
| HD mode (any) | p60b6, 2.78% | nominal | nominal | the 2.78% floor stands until F9-bootstrap thinning is measured (§3) |

Scan-mode riders (unchanged from LAYERS §8): grey scans for B-track pilots,
color for chroma/A-track; JPEG scan paths cannot carry pilot decode for
<5-dot pilot features (007.2).

---

## 8. Tool 5 — `compose_page` interface

The L2 page composer assembles a printable page from payload bits +
format. It is the single place where pilot furniture, strips, headers,
training bands, and capacity accounting meet. Spec'd against the emit
thread's stated API (`encode_field(...) -> PlaneBitmap`,
`emit_page(...)` places fields); **this spec governs at integration** —
if the emit thread's final shapes differ, integration adjusts there.

### 8.1 API

```python
# paperholo/compose.py
@dataclass(frozen=True)
class PilotLayout:
    period_cells: int = 60          # P; frozen across modes
    block_cells: int = 6            # B; density knob: 1/B²
    version: int = 2                # site/value derivation label suffix
    # derived: density(), sites(shape, seed, plane), word_subsets(seed)

@dataclass(frozen=True)
class ComposeSpec:                  # the FormatDescriptor slice Tool 5 owns
    layout_version: int
    constellation_id: str           # "A3", "B1", "B2", "A4", ...
    planes: str                     # "K" | "CMY"
    pilot: PilotLayout | None       # None only for bench sheets
    strips: bool = False            # bench/loop furniture, never archive
    header: bool = False            # machine strip + human text (DESIGN §9.1)
    training_bands: tuple[int, ...] = ()   # band indices, e006 idiom
    tile_geom_cells: int = 64
    page_cells_yx: tuple[int, int] = (2260, 1575)   # A4 @ c3, 600 dpi

@dataclass(frozen=True)
class ComposedPage:
    plane_bitmaps: dict[str, np.ndarray]  # PlaneBitmap per plane (LAYERS §1)
    manifest: dict                        # §8.3
    payload_capacity_bits: int            # after ALL furniture displacement

def compose_page(
    payload_bits: np.ndarray,      # flat uint8 {0,1}; length <= capacity
    spec: ComposeSpec,
    seed: bytes,
    page: int,
) -> ComposedPage: ...
```

Deterministic in (payload_bits, spec, seed, page) — byte-identical
regeneration, sha-gated like every stimulus. All randomness via
`paperholo.modulation.rng/keystream`.

### 8.2 Composition order (normative)

1. **Furniture masks first**: pilot sites (`PilotLayout.sites`), strip rows,
   training bands, header/margins — a single boolean furniture mask over the
   cell lattice. Conflicts (pilot site inside a strip row) resolve
   furniture-over-pilot: the site is skipped and its word bit becomes a
   known erasure at decode (within the 2e+f ≤ 30 budget; the composer
   asserts ≤ 10% of any tile's word is masked).
2. **Payload cell enumeration**: lattice minus furniture, fixed raster
   order → the payload-bit ↔ cell bijection is deterministic and public
   (the decoder re-derives it from the same spec).
   `payload_capacity_bits = n_payload_cells × bits_per_cell(constellation)`.
3. **Fields**: `encodings.encode_field(...)` per payload region →
   PlaneBitmap(s), scrambled per DESIGN §4.2.
4. **Pilot values**: `pilots.coordinate_code(spec.pilot, seed, page, plane)`
   → per-tile words → site-local scramble (§6.3) → rendered through the SAME
   constellation emitter as payload (a pilot cell is indistinguishable in
   emission path — clean masks stay clean, composites stay composite).
5. **Placement**: `emit_page(...)` → psgen PSDoc → .ps bytes + sha256.

### 8.3 Manifest (JSON, alongside the .ps)

FormatDescriptor fields (LAYERS §0) — layout_version, seed_label, planes,
emission_path per region class, constellation_id + params, pilot_layout_id
(`p60b6.v2`), strip_layout_id or null, training_furniture, tile_geom_cells,
scrambler convention — plus: page index, ps sha256, capacity accounting
block (cells total / pilots / strips / bands / header / net payload cells /
net bits), per-region inventory (band table, e006 idiom), and the generator
version. The manifest is bench convenience; the PRINTED page must remain
self-sufficient (window code + header strip), per the no-side-channel rule.

### 8.4 Capacity accounting (worked example, A4 @ c3, HD mode)

3.56 M cells; pilots 2.78% (−99 k); header row ≈0.4% (−14 k); archive page
(no strips, no training bands): net ≈ 3.44 M cells = **96.8% of lattice**.
Loop/bench variant adds strips 1.67% + 2 training bands ≈ 2% → 93.2%.
At A3's multi-sheet-minimum MI band this prices the pilot system at
~2–3 b/mm² of the 90–133 b/mm² measured range — against a measured
strips-alone geometry cost of ~7+ b/mm² on B1 (007.7). ESTIMATE until M-P3.

---

## 9. Measurement plan before the pilot freeze

Each item zero-print or one-sheet; sim-first per the M0 gate. Envelopes
pre-registered in the experiment log before any print.

| id | question | cost | method |
|---|---|---|---|
| M-P1 | window code round-trips at measured raw BER + warp; empirical crop-size (grain) curve | zero print | implement `coordinate_code`; round-trip on the measured simulator (c3 2.5–3.7%, c2 ctx 5–8%, stepped warp); fragment crops from full-page sims AND from existing real scans (e006bw/e004 crops re-addressed) |
| M-P2 | C-pilot vs MIC separability in scan space | zero print | MIC dot r/g/b responses from existing AltaLink color scans (007.7 sites) vs S3 C-mark responses (003.0 sheet); build the site-gated C discriminant's MIC rejection stats |
| M-P3 | PILOT-1 validation sheet: pilot-anchored tracking vs strips vs between-strip vs genie, same sheet; single-pilot centroid noise; window decode from real scans; grain via software crops of the scan | ONE sheet per engine | p60b6 pilots + 17-strip skeleton + B1/A3 bands + canary row; both engines; 3–4 re-placed scans per 004.0b |
| M-P4 | void tax per engine at rail density (C-on-white option) | rides M-P3 | one reserved-white C-rail band on PILOT-1; margin-vs-clear split per 003.0's method; repeat closes the 003.0 single-replicate caveat |
| M-P5 | C-on-white detectability at 1200 dpi on an AltaLink COLOR page (MIC lattice present) | rides M-P3 (office print) | PILOT-1 office print has color content → MIC appears → direct in-situ confusion measurement |
| M-P6 | c2-class word robustness: duplicated-word combining at 11–14% hard / 5–8% ctx | zero print | simulator + the existing e006bw scans' measured error maps replayed over pilot sites |

Freeze gate: M-P1 and M-P6 green in sim; M-P3 within envelope on both
engines (pilot-anchored ≤ genie + 1 pp on interior bands; window decode
100% at page scale, grain curve within 2× of §6.5's ESTIMATE). The chroma
rail (§4.3) freezes separately and only on a measured M-P4/M-P5 win.

**M-P1 STATUS (011.0, 2026-07-08): EXECUTED, sim half GREEN** — see
experiments/011-pilot-roundtrip.md. Window decode 100% at page scale
(80–81/81 tiles), zero false accepts, grain curve measured (15.1 mm
placement-guaranteed / 13 mm ≈ 60% / 10 mm below grain), blind end-to-end
+1.97 pp over the geometry-free footing on 600×600-cell windows (measured
strip comparators: +5.8 / +3.4 pp), 3-scan majority combining replicates
through the blind pipeline (5.80 → 2.12% on the adversarial warp seed), R3
value-spectrum spot check done (concern 6: the site line is the global
spectral peak at 88× median background — sites, not values; values never
repeat). Residue for M-P1's real-scan half: e006bw/e004 crop re-addressing
is NOT possible on existing scans (they carry LAY=1 furniture, no v2
pilots) — real-scan validation folds entirely into M-P3/PILOT-1. Concern 4
(false-accept arithmetic) is now MEASURED: 0/200k random words at t_acq=8.
Concern 1 (anchor precision) remains the load-bearing hardware unknown.

---

## 10. Concerns and open questions (honest list)

1. **Anchor precision is the load-bearing ESTIMATE.** §2.2's 0.05–0.09-dot
   residual assumes ~0.3–0.5-dot single-pilot centroid noise averaged over
   30–40 pilots/band — plausible (between_strip's quality-weighted fits
   worked at worse SNR) but UNMEASURED until M-P3. If single-cell centroids
   are ≥1 dot noisy, anchor bands widen and the strips-vs-pilots margin
   shrinks.
2. **Void tax is single-engine, single-replicate** (003.0 H2 explicitly
   flags the repeat). AltaLink's fa-dominant white-closure structure (007.6)
   could price enforced voids differently in either direction.
3. **c2 acquisition rides the ctx detector**, whose gains are engine- and
   field-dependent and which misfires on JPEG scans (007.2, LAYERS §3). The
   robust-mode duplicated word is the hedge; its combining gain is an
   ESTIMATE (M-P6).
4. **False-accept arithmetic** (§6.4) uses sphere-volume ESTIMATES; the
   t_acq = 8 choice should be re-derived once the real BCH decoder exists
   (M-P1 validates empirically against shuffled-site nulls).
5. **Engineered per-tile words are NOT a true M-array** — a fragment
   smaller than the Stage-A window in every visible tile relies on Stage-B
   pooled correlation, which is designed but unproven. The classical
   M-array/perfect-map construction (DESIGN §5.2a lineage) is retained as a
   fallback if Stage B measures fragile; switching would be another
   layout_version bump.
6. **Site-local scrambled values put a weak 1/P structure into value
   statistics** on top of the conceded site-pattern lines. ESTIMATE:
   spectrally negligible at 2.78% density; M-P1 spot-checks the printed
   spectrum against R3.
7. **Pilot tile (60) vs LDPC tile (64) misalignment** is cosmetic (§6.6)
   but means tile-local pilot counts vary slightly per 64×64 LDPC tile
   (≈110–118 at p60b6, phase-dependent); no action unless M2's per-tile
   bookkeeping wants alignment —
   which would argue p64b8-with-2-pilots-per-block (3.1%), an option NOT
   enumerated in §2.1's table and only worth pricing if M2 asks.
8. **Thinning (F9 bootstrap) is deliberately unfrozen** (§3): no
   below-2.78% mode until the decode loop demonstrates early certification
   on real scans.
9. **Duplex/versos**: page addressing (§6.1) treats sides independently;
   whether the physical duplex path perturbs pilot geometry (backside
   fusing pass) is UNMEASURED — the 007.1 duplex confound was demoted, but
   PILOT-1 should be printed simplex until someone measures it.
10. **The AltaLink scanner path cannot decode pilots** (JPEG, <5-dot
    erasure — 007.2). Office-printed sheets must come home to a flatbed for
    acquisition, or the office scan profile must be fixed to uncompressed
    (open LAYERS item). Pilot design does not fix scanner policy; it
    inherits it.

---

## 11. Proposed DESIGN.md amendments (for review, not yet applied)

1. **§5.2a**: replace the P = 64 example with the normative p60b6 layout
   (PERIOD = 60, BLOCK = 6, exactly 2.78%, 100 sites/pilot tile); add the
   mode ladder (B ∈ {6,5,4}) as format parameters; note layout_version 2
   supersedes the v1 stub pattern (which was never printed on an archive
   sheet — no orphaned media).
2. **§5.2a values**: specify the site-local scrambler (§6.3 here) as the
   resolution of the keystream/acquisition circularity.
3. **§5.3**: split grain numbers by engine class — ~3×3 mm (1200-dpi design
   target) vs ~6.4×6.4 mm measured-engine c3; effective holographic grain
   ≈10×10 mm on the 600-dpi class (ESTIMATE pending M-P1/M-P3).
   *Partially applied 2026-07-09 (user-approved in session): the
   fragment-session clause — grain is the ISOLATED-fragment floor; within a
   session holding decode state, sub-grain pieces stay usable (§15) — is in
   §5.3 now, with the measured c2 ladder (014.3). The engine-class split of
   the headline numbers remains queued with items 1–8.*
4. **§5.2d**: fold in the §4.3 dual-rail analysis (reserved-void tax vs
   opportunistic F4 rail) and the §4.5 Y rejection with the MIC fact.
5. **§5.4**: co-located whole-cell pilots as the per-plane mechanism;
   plane_id in the word message; Y addressing rides C/M/K + frozen fusing.
6. **§9 Encode**: “interleave the pilot lattice” becomes “compose_page
   overlays pilot furniture (displacing payload cells) per §8 of
   PILOTS-DESIGN”.
7. **LAYERS §4/§8**: pilot-anchored tracking row gets §2.2's spacing math;
   the §7 compat matrix column is replaced by §7 here; AddressResolver row
   for `pilots.coordinate_code` updated with the §6 spec parameters.
8. **(v0.2) §5.2a code spec**: the coordinate code is shortened
   BCH(127, 64, t = 10) → (100, 37) over GF(2⁷) (prim 0x89), 36 message bits
   + 1 pad — v0.1's "(127,36,t=15) → (100,36)" was arithmetically impossible
   (§6.2). Any DESIGN.md text citing t = 15 / d ≥ 31 for the window code
   must carry the corrected construction.

## 12. As-built notes (v0.2, 2026-07-08 — deltas discovered by building it)

Implementation: `src/paperholo/{bch,pilots,compose,acquire}.py`, format
pinned by `tests/test_format_v2_golden.py` (never edit the anchor — bump
layout_version). Full results + caveats: experiments/011-pilot-roundtrip.md.
Deviations from this document's v0.1 design, found necessary by measurement:

1. §6.2 code correction (above).
2. **Stage B pools clean tiles only**: naive all-site pooling vetoes correct
   addresses when a warp-slip band crosses the fragment (measured); per-tile
   match rates double as the slip diagnostic; acceptance still requires ≥30
   clean-tile sites plus the BCH false-accept gate.
3. **Integer one-cell slips are repaired by pilot-WORD voting under ±1-cell
   shifts, not by template anchors** — measured: detected-halo anchor
   templates are confidently wrong under a full-cell slip and drag the NCC
   peak to zero. Anchors remain the sub-cell refinement stage (§5's role),
   run 2 rounds with the warp folded between rounds.
4. Payload extraction trims cells whose footprint is not fully inside the
   fragment (partially-covered edge cells measured at 30–50% BER — silent
   LDPC-margin eaters otherwise).
5. The v1 decoder is errors-only (no erasure decoding yet); 2e + f ≤ 20 is
   the code's budget, not yet the decoder's. Queued behind the first
   damaged-fragment use case.

---

## 13. layout_version 3 — the format-thrift cut (2026-07-08, GOVERNS PRINTS)

Adopted the same day as the v2 sim measurements, from the design dialogue
recorded in docs/REASONING-LOG.md ("Session 2026-07-08"). Three moves, each
converting spent message bits into code distance at fixed 2.78% overhead:

**13.1 The word.** Message = **[flat counter c: 18 bits][zero pad: 5 bits]**,
c = page·tiles_per_page + ptile_y·tiles_x + ptile_x (geometry from the
format registry entry; e012 page: 925 tiles ⇒ 200 pages nominal, 283 max —
page 283 is only partially addressable, encode raises past 2¹⁸ and the
decoder skips such tiles; tested).
Code = **shortened BCH(127,50,t=13) → (100,23), d ≥ 27** (same GF(2⁷),
prim 0x89, roots α¹..α²⁶). Word failure: 2.0e-5 at 3.7% raw BER, **2.8% at
the 8% c2-ctx worst day** (was 17.6% at v2's t=10 — M-P6 word duplication
demotes to insurance). The BCH ladder at n=100 is quantized in k-steps of 7;
18 bits rounds up to k=23, and the 5 spare bits are fixed zero pads = free
consistency checks (false-accept ÷32).

**13.2 No version field, no plane field — implicit format signaling.** The
decoder identifies the format by trial: each registry entry's value
descrambler either turns the pilot bits into a decodable codeword or into
coin flips (measured FA arithmetic: 5.0e-5 per full 28,800-hypothesis window
search at k_eff=18, t=13; Stage B certifies). Grounds: R5 already requires
possessing the format registry — in-word version bits can only index a list
the archaeologist must have anyway, and cannot bootstrap a lost spec; this
is the same doctrine that rejected tile coordinate headers. **Measured
nesting fact (012 build):** the v3 root set (α¹..α²⁶) contains v2's
(α¹..α²⁰), so C_v3 ⊂ C_v2 — every v3 codeword IS a v2 codeword, and
cross-format rejection rests *entirely* on the labeled value scramble
(verified both directions, end to end: the v3 page under a v2 spec cleanly
fails at Stage A). The doctrine is load-bearing in its purest form here.
Discipline it imposes: (a) formats are separated by **XOR keystream labels,
never bit permutations** (BCH is cyclic; some permutations preserve the
codebook);
(b) **P = 60 frozen forever** — site-lattice diversity is the one expensive
hypothesis axis, so all formats share the p60b6 site derivation (label
`pilot-sites-v2`) and differ only in the value layer (`pilot-values-v3/<plane>`);
(c) every registry entry is a complete FormatDescriptor — no partial
format sharing, any change anywhere is a new entry;
(d) **the pairwise codeword-distance floor is load-bearing for fragment
placement (added 2026-07-10, from 014.4):** sub-grain confetti placement's
confusability margin IS the value layer's pairwise distance spectrum
(measured on v3: min 32/100 over sampled tile pairs; the d ≥ 27 guarantee is TIGHT (2026-07-29 exhaustive correction: TRUE min = 27, mult 3; 32 was a 400-pair sample — see the 014.4 correction)) —
any future value-layer change must preserve a distance floor of this
class, or it silently breaks §15 correlation placement on the sheets that
carry it.

**13.3 Single-stage search.** With k_eff = 18, t_acq = t_full = 13: the
v2 two-stage acquisition radius collapses; Stage A searches at full
correction strength, Stage B (≥0.85 over ≥30 clean-tile sites) remains the
false-accept certifier and the slip diagnostic. Erasure budget 2e+f ≤ 26
(decoder still errors-only — v1 gap, §12.5).

Format anchor: tests/test_format_v3_golden.py. v2 was never printed; it
remains in code and anchors as the registry's first entry and the 011
measurement record.

## 14. Fragment-pile ("confetti") recovery ladder

The R2 story as it falls out of this format (dialogue 2026-07-08; the
scrambled payload makes every region a position-unique fingerprint — a free
property that makes the jigsaw well-posed). Three regimes at c3@600:

| fragment | places itself by | status |
|---|---|---|
| ≥ ~15 mm (one full pilot tile) | pilot-word self-addressing | MEASURED (011.0: 15.1 mm guaranteed, 13 mm ≈60%) |
| ≥ ~80–85% of ONE pilot tile visible, ctx-class bits | erasure word decode: 2e+f ≤ 26, f = missing sites (bch.decode_erasures, binary two-trial fill; acceptance 2e_out+f ≤ 26 ⇒ within-budget uniqueness) | **MEASURED 2026-07-10 (014.5, 76 real tiles × 9,120 decodes): ctx q=0.80 → 96.1%, 0.85 → 98.7%, 0.90 → 100%; global bits dead below 0.80, as the arithmetic predicted; 0 wrong-address decodes.** Stage-A SEARCH with erasures still needs the §6.4 FA budget re-derived — known-position use only |
| ~5–15 mm (gated) / ≥4 mm (placement correct, gate refuses) | F13 correlation placement: `paperholo.place.place_fragment` — FFT matched filter over the seed-predicted pilot field, all offsets × 4 rot at once, support-aware z, §15.4 gate | **BUILT + MEASURED 2026-07-10 (014.5): 100% correct placement at 4–10 mm on genie bits; gate passes 5/5 at ≥5 mm and correctly refuses 4 mm (rival dips under the bar at ~60-site support); ISOLATED end-to-end (own pitch + own lock + ctx, no enclosing geometry) 5/5 at 6–10 mm, 5 mm 5/5-correct 4/5-gated; ~0.73 s/fragment full-page; wrong-seed/wrong-region nulls refused** |
| < ~3 mm | nothing (fingerprint too short) | RaptorQ absorbs ≈ its area fraction |

c2@600 compresses the ladder ~1.5× with cell pitch, MEASURED 014.3 (blind
ctx, off-crease): 10 mm placement-guaranteed 5/5 (BER 0.3–1.1%), 8 mm 1/5,
6 mm 0/5 — matching the geometric 2×-pilot-tile prediction. **014.4
ATTRIBUTED it (2026-07-10, pre-registered probe, experiments/
014-c2-print.md): word incompleteness, geometry exonerated** — blind =
full-tile-visible = genie-geometry at all 15 windows; the ladder is pure
pilot-tile placement geometry, and correlation placement separates true
from every decoy by ≥0.20 (floor = the window code's own distance
spectrum, sampled min 32/100; true min 27 (2026-07-29 exhaustive correction: TRUE min = 27, mult 3; 32 was a 400-pair sample — see the 014.4 correction)). F13 build GREEN.

Key mechanics: the jigsaw is solved in **cell-coordinate space** (absolute
addresses), never shape space; pieces need not touch. Below one tile, the
pipeline inverts: lattice lock → content/pilot-correlation placement →
pilots snap in as known cells. Real shredder output (P-4 cross-cut strips,
4 mm < one 7.62 mm tile) can NEVER self-address — the bootstrap (large
fragments seed the page, decoded content places strips, decode improves,
smaller pieces join) is the required path. LDPC-tile CRC passes certify the
placement of every contributing fragment at once (F9). Named dependency:
**erasure decoding at both levels** (BCH erasures + M2 LDPC) is the engine
of composite decoding — the strongest standing argument for pulling M2
forward. Sim quantification = candidate experiment (shred-grade sweep on the
e012 page); queued behind minimal-M2.

## 15. Fragment-session acquisition (decoder-axis doctrine, 2026-07-09)

Operationalizes §14's middle regime. The scenario: a scatter of torn
pieces on the scanner glass, recovered over a multi-scan session. The key
asymmetry that makes it cheap: **pilot values are seed-derived, so they are
predictable even in regions not yet recovered** — payload is only known
where LDPC tiles have certified (F9). Everything here is decoder-axis: no
layout_version change, applies to the printed e012/e014/e016 sheets.

**15.1 Staged protocol (big pieces first).** (i) Scan the large pieces
first; each acquires by the standard Stage-A/B word path and its cells
enter the page's `PageDecodeState` as ordinary `ScanObservation`s (the F6/F9
machinery — a placed fragment is just another partial scan). (ii) After
each batch, the session checks completeness by **fountain rank, not
LDPC-tile inventory** (edge F14): done = ANY K certified symbols (e016: any
~80% of 1734 LDPC tiles), so confetti triage is greedy, never a checklist. (iii) Only
the remaining sub-grain / boundary pieces get the expensive path (15.3),
against a hypothesis space the placed pieces have already shrunk.

**15.2 Multi-piece scans (segmentation + alignment front end).** A glass
of confetti is several disjoint lattices at arbitrary orientations in one
image; each piece, once found and de-rotated, is INGESTED AS A TINY PAGE
through the unchanged per-scan front end (pitch → lock → ctx → route:
word decode / erasure decode / F13 placer). Design (2026-07-10 dialogue):
(a) **backing-agnostic foreground statistic** — the ~50% scrambled field
reads mid-grey at cell scale against EITHER a dark backing sheet or the
bare white lid, so foreground = |cell-scale local mean − backing| with
backing auto-estimated from the image border; white lid = the easier
physical protocol and costs nothing for fully-printed pieces (caveat:
unprinted paper margins of real torn pieces vanish against white — the
segmenter finds the printed FIELD, grow-out recovers the rim);
(b) **conservative core + GROW-OUT**: label the confident interior, then
dilate the mask outward a few cells past the apparent boundary —
over-inclusion is cheap (background cells earn low |LLR| and erase;
the placer is mask-aware), under-inclusion loses valid cells forever;
(c) **alignment = lattice angle, not shape angle**: per piece, the
gradient-spectrum annulus at the known cell pitch yields the lattice
orientation mod 90° (torn shapes have no meaningful rectangle angle);
counter-rotate, and the residual small angle + rot90 ambiguity ride the
existing lock/orientation machinery. Build-vs-buy: external deskew/
auto-crop tools (ScanTailor/unpaper/OpenCV-minAreaRect class) measure
document-rectangle angles, are pixel-lossy, and give neither masks nor
lattice integration — REJECTED; built thin on scipy (in-tree dep).
Pieces must not overlap on the glass.

**15.2 AMENDED BY MEASUREMENT 2026-07-11 (016.6/016.7):** (c)'s
counter-rotation RESAMPLE is measured FREE at genie angle (mismatch
flat 0–45°); the real cost is the annulus estimator's accuracy
(0.4–0.5° median where <0.15° is free — dose–response measured). The
production placer path therefore no longer rotates the image at all:
detection samples ORIGINAL glass pixels along a continuous (angle,
pitch, sub-cell phase) lattice model (`segment.sample_cells_at`, exact
ndimage.rotate-equivalent transform), and after a gate-passed placement
the angle+phase are REFINED against the piece's seed-predicted pilot
sites on a signed-margin objective with a train/held-out site split
(`segment.refine_on_sites`; hard-mismatch objectives saturate on clean
channels). Companion amendments, same evidence base: the grow-out mask
(b) is a SEGMENTATION/support doctrine only — placement scoring and
LLR emission use the 4-cell-eroded CORE (the rim samples backing,
~coin-flip wrong, and lands inside neighboring pieces' cells = union
poison); §15.3 sessions merge by weighted-sum UNION across pieces
(disjoint cells — the multi-scan sum-negative does not apply, and
single-observation policies are geometrically insufficient for
boundary tiles). Counter-rotation remains in the WORD path (big pieces
as tiny pages), where estimator accuracy scales with piece size and
the resample is free.

**15.3 Sub-grain placement by pruned pilot correlation (edge F13).** For a
piece that cannot complete a word decode: (a) lattice-lock the piece
locally (pitch + rotation mod 90); (b) site-phase lock — the same ≤P²=3600
geometric hypothesis test as Stage A, no values needed; (c) value-correlate
the piece's readable pilot cells against predicted values over ONLY the
phase-compatible offsets inside the **pending-region set** (un-certified
LDPC tiles across the volume; the page population itself is pruned by the L0
index/descriptor and by which pages the large pieces hit). Budget, MEASURED
014.4 (correcting the 2026-07-09 draft's 4× cell-pitch slip): a 6 mm c2
piece holds ~5,000 cells = **135–139 pilot sites**; 8 mm = 240–251; 10 mm =
378–390. A 20%-missing 8-page c2 volume leaves ~11.7M pending cell offsets
÷ 3600 site phases × 4 rot ≈ 13k ≈ 2¹⁴ candidates. Decoys do NOT sit at
50%: pilot-tile values differ only by codewords of the (100,23) code, so the
decoy floor is the code's pairwise distance spectrum (true min 27 (2026-07-29 exhaustive correction: TRUE min = 27, mult 3; 32 was a 400-pair sample — see the 014.4 correction),
median 44; partial-tile subsampling → observed floor 0.257–0.342) — the
d≥27 word margin doubles as the placement margin. Measured separation:
true mismatch = channel BER (0.043–0.086) vs nearest decoy ≥ 0.257, gap
≥0.20 ≈ 4.7σ at 135 sites, every window. Gate form (POST-HOC constant,
validate in-build): true < 0.15 AND all comparable-support decoys > 0.20 —
NOT the pre-registered >0.35, which sits above the structural floor and
failed even the self-addressing 10 mm controls. The pilot-bit floor
extrapolates to ≈3 mm (35-site class ~3σ, ESTIMATE); **the remaining
unknown is the piece-local lattice lock** (all 014.4 bits inherited
enclosing-lock geometry; a real isolated 6 mm piece must lock pitch/
rotation on ~71 cells alone — first sim item of the F13 build).
Payload cells cannot place a piece into unknown regions but
**fast-reject redundant pieces** (match against F9 `known_cell_values`
where the piece overlaps certified area — triage, not placement).

**15.4 Certification.** A correlation placement is admitted only past a
margin gate, formalized (2026-07-10) as: score every candidate offset by
its **support-aware normal deviate** z = (0.5 − mismatch)·√support / 0.5
(support = pilot sites the candidate actually overlaps — raw mismatch
fractions are NOT comparable across supports), and accept iff (i) the best
candidate's mismatch < 0.15, (ii) every other candidate's mismatch > 0.20
(the bar sits BELOW the measured d-spectrum floor 0.257–0.342 and ABOVE
the worst true reading 0.086), and (iii) the z-gap between best and
runner-up exceeds a margin to be frozen only after the validation
protocol: re-run on fresh windows (scan B + sim) that had no part in
setting the constants. **Validation RAN 2026-07-10 (014.5 part 4): scan-B
fresh windows 6/6 correct + PASS (mismatch ≤ 0.021, rivals ≥ 0.271,
z-gaps 6.2–9.2) — constants (i) 0.15 and (ii) 0.20 are FROZEN; the (iii)
z-gap margin stays informational (measured ≥2.9 on every correct gated
placement).** Admitted cells then ride the normal path — LDPC+CRC certification (F9) remains the backstop,
so a mis-placed piece wastes itself; it cannot silently corrupt (013.0:
0 wrong certifications on record). Boundary LDPC tiles reassemble across pieces
by cell-address union in `tilemap` — the mechanism 015 priced: fragment-
boundary symbol yield 79.6% at 25.4 mm WAS the whole measured f-gap, and
cross-piece union is the direct attack on it.

**15.5 Open (build order).** (1) ~~run 014.4 failure attribution~~ DONE
2026-07-10: word incompleteness, F13 GREEN; (2) ~~piece-local lattice
lock~~ DONE 2026-07-10 (014.5 part 3, on REAL scans not sim: isolated
pieces self-lock and place 5/5 at 5–10 mm — not the binding floor);
(3) ~~segmentation front end (15.2)~~ DONE 2026-07-10/11 (016.4–016.7 +
first real-scissors session 018.2); (4) ~~F13
correlation placer + margin gate~~ DONE 2026-07-10 (paperholo.place;
constants frozen on scan-B fresh windows; torn-shape piece masks = small
open extension, v1 is square crops); (5) F14 session loop
(volume_scans_wanted generalized to piece triage); (6) shred-grade sim
sweep (§14's queued experiment) re-run WITH session state to re-measure
the effective ladder; (7) erasure-aware Stage-A search iff ever wanted:
re-derive the §6.4 FA budget first (the shipped erasure decoder is
known-position only by doctrine); (8) §15.6 v2 deferrals: anchor-seeded
search restriction, continuous affine sampler, sheet-level affine prior,
margin-aware piece thresholding.

**15.6 Anchor-graph piece acquisition (2026-07-11, decoder-axis — the
e018 real-scissors amendment).** The first real-scissors session (018.2:
17 pieces, 10 decoded; forensics on the failures measured piece-by-piece)
found every failure to be a **cascade artifact**, not a channel limit:
a single central-ID window vetoed a piece whose own windows read 4/6
(p5); a central-ID window that DECODED 8/9 words was discarded because
only tiled windows fold (p8); a page-bottom-edge piece's true origin sat
outside the placer's 'valid'-mode search space by construction (p8,
oy 1959 > 1874 max — real scissors always produce margin-bearing edge
pieces, a regime the field-only §15.2 fixtures never made); the rigid
one-(angle,phase) model floored at mismatch 0.248 > gate on a 47 mm
piece whose print-frozen affine (y-scale −0.31%, the M281 print-y-short
class; affine-fit residual 0.38 cells) sweeps sub-cell phase across the
span (p5); and scannorm's per-piece `angle_rad` — which measured the
+0.45° residual the whole time — was ignored. Three invariants are
therefore adopted as doctrine (decoder-axis, no format change):

- **I1 — no certified evidence is discarded.** Any decoded BCH word is
  evidence and enters the accumulator: identification windows fold like
  tiling windows; identification failure triggers RETRY at the piece's
  top-mask-coverage windows (measured: id-crop ink coverage does NOT
  predict id success — p16 decoded at 0.518 coverage, p5 failed at
  1.000 — so retry-elsewhere, not center-on-ink); window grids are
  mask-aware (Stage-A pass boundary ≈0.7 mask-fraction measured; the
  bbox-anchored grid put 6/6 of p8's windows at 0.35–0.62 on backing
  while its max-ink window read 6/6 words).
- **I2 — no physically-valid pose is excluded from search.** The
  correlation placer gains an opt-in PADDED search ('full'-mode
  semantics: pilot field zero-padded per (page, rot) hypothesis) so
  page-edge overhang places; off-page cells carry zero sites, so score
  and support semantics are unchanged. Measured: p8 places at z 25.1,
  mismatch 0.139, gap 0.234 under padding. Gate-provenance note: the
  frozen §15.4 constants were validated under 'valid' search; padding
  only ENLARGES the rival candidate set, which can only lower
  rival_mismatch — i.e. it moves the gate toward refusal, never toward
  false accept — but the padded regime still gets its own decoy
  validation on synthetics before first use ("valid" stays the default;
  sessions opt in).
- **I3 — model capacity scales with piece span.** One rigid
  (origin, rot90) + one (angle, phase) is valid only below the piece's
  geometric coherence length (~25 mm at c3 on this engine, measured:
  quadrant-scale placement of p5 passes gates 4/4 at 0.043–0.101 where
  the full 47 mm grid floors at 0.248). Above it, placement/refinement/
  emission go WINDOW-SCALE (~200 cells), sharing one angle, per-window
  integer origin + phase — a piecewise-constant approximation of the
  mild print-frozen affine field, which measurement says is all that is
  needed (affine residual 0.38 cells; no rubber-sheet warp). Window
  origins must be mutually consistent (±2 cells) — the free coherence
  check. Angle candidates come cheap: the segmenter estimate, scannorm's
  in-pipeline `angle_rad` (seed, not one-shot — it overshoots: 0.448°
  measured vs 0.30–0.35° true on p8), and a ±0.75° sweep at 0.25° step
  (gate-passing bands measured 0.5–0.75° wide on both forensic pieces).

The per-tile LDPC+CRC (F9) backstop and the §15.4 gates stay untouched —
the anchor-graph changes WHERE evidence is gathered and how poses are
searched, never how they are certified. v2 deferrals (design notes, not
built): anchor-SEEDED search restriction (a decoded word implies the
piece pose; restrict the placer to a local verify — compute
optimization, the padded global search is affordable); a continuous
affine sampler (piecewise windows already capture the measured field);
a sheet-level affine prior pooled from the session's decoded pieces
(print-frozen ⇒ transfers across pieces of one sheet); margin-aware
piece thresholding (the 50%-dark median lock is format-legal — the
keystream scramble guarantees 50/50 ink; attached blank page-margin
inside a grown mask shifts it — p8 measured 0.544, survivable, but a
2-mode fit removes the failure mode).

**15.7 Cross-piece assembly and post-decode feedback (design notes,
discussion 2026-07-11 — a PEER THREAD is prototyping the feedback loop;
this section captures the settled framing so it is not lost).** Two
distinct couplings, one live and one not:

*Cross-piece assembly (LIVE at the LDPC layer, absent at addressing).*
An LDPC tile straddling the cut between two placed pieces already
decodes today: every observation emits per-cell `(payload_index, LLR)`
and `decode_tiles` assembles each 64-cell tile from the UNION of all
observations touching its cells (weighted_sum, §15.6/016.5 — closure is
geometrically impossible without it: single-piece coverage ceiling
1027 < K). The one seam is the erode-4 dead strip (~8 cells ≈ 1 mm at
c3) along every physical cut that no piece emits — the 016.7 anti-union
poison trade; straddling tiles cross it on LDPC parity. Pilot WORDS
never straddle (each piece is its own crop; a scissored pilot tile
yields no word from either half) but this is moot: addressing rides the
seed-PREDICTED pilot field (§15.3), which exists across cuts, so a
placed piece needs no decoded neighbor word. What is genuinely ABSENT is
an ADJACENCY PRIOR: today the only cross-piece coupling is the F13
pending-prune (page-space, weak). A sub-grain strip (e.g. 1.4×31 mm,
~65 sites < the ~135-site 6 mm grain) whose neighbor is already placed
would flip from unplaceable to placeable if the placer restricted
candidates to the boundary RIBBON around the placed piece's torn edge
(collapses the decoy population at fixed support). Boundary-ribbon
prior + torn-edge shape matching (jigsaw) are the natural entries;
both compose with §15.6 as further I2-class "don't exclude the true
pose" moves.

*Post-decode feedback (the missing loop).* Four feedback edges exist —
F13 pending-prune (tiles→search space), F9 backfill (certified tiles→
±inf payload LLRs, merge/triage only), the P2 refine chain (placement→
PREDICTED-pilot-supervised angle/phase refit on raw glass, one round
per piece), PAVA (decoded pilot cells→detector calibration) — but NONE
carry PAYLOAD certainty back to the pixels. A certified tile's 4096
true cell values are a ground-truth patch ~40× denser than its pilot
sites, and nothing re-uses them. The missing loop: certified tiles →
dense local labels → refit local warp + detector (existing
`sample_cells_at`/`recal_llrs_from_labels`, fed payload labels instead
of pilot labels) → re-sample UNCERTIFIED NEIGHBORS under the improved
map → re-decode → repeat until no new certifications (self-sync growth
from certified islands). Circularity-safe: labels come only from
CRC-certified tiles (F9: 0 wrong certifications on record; a wrong
label needs a 2⁻³² CRC collision AND an LDPC codeword hit). It is the
p5 quadrant rescue done with payload labels instead of angle sweeps.
Where it bites (measured pointers): the 016.3 residual 7 tiles; the
014.2 crease band (that log already flags "failed-tile labels =
improvement path"); and — connecting to the ribbon above — the erode-4
boundary dead strips, where a certified tile on EACH side of a cut pins
local geometry precisely enough to safely re-sample and emit the eroded
rim from glass, shrinking the moat exactly where the union needs it.
Ranked build order (for the peer thread): (1) certified-neighbor-
supervised re-sample of failed tiles (bounded, local, all machinery
exists); (2) piece-local payload-supervised warp refit (P2 with 40×
labels); (3) boundary-ribbon placement prior for sub-grain strips;
(4) global bundle adjustment (probably overkill — the measured field is
affine + local phase). All are I1-class ("stop discarding information")
where the discarded information is post-decode CERTAINTY. Not built in
this thread by design.

**15.7 BUILD SPEC ("repass", feedback-repass branch, 2026-07-11 — the
peer-thread prototype of the loop above; normative for the build).**
Deployment shape: v1 is a standalone POST-PASS tool (session state in →
state out; resumable, A/B-able against the pre-repass state) run after
the session driver. Integration into the core session loop is
deliberately deferred until repass EXPERIMENTALLY validates on real
scans (user decision 2026-07-11); torn-edge jigsaw matching is deferred
by the same decision (the boundary-ribbon prior likely captures the
yield, and the ragged-tear regime where contours discriminate is
unprinted). Build rules:

- **R1 — labels only from CRC-certified tiles.** The label export
  already existed: tilemap.known_cell_values() (the F10
  detection-domain accessor — certified TX bits through the payload
  keystream) — the label source is free. Failed/low-coverage tiles
  never contribute labels. Circularity-safe by the F9 record.
- **R2 — supersede, never sum.** A re-sampled observation derives from
  the SAME pixels as the observation it improves; summing correlated
  evidence is the thrice-measured F1/F6 failure mode (012.3/013/
  014.2). Repass REPLACES the piece's prior observation(s) in the
  state (whole-observation replacement; certified tiles are untouched
  — their truth lives in TileState + the backfill arrays, never in the
  replaced observation).
- **R3 — monotone, terminating.** Certified tiles are never demoted,
  so the certified set grows monotonically; the loop stops when a
  round certifies nothing new (hard cap 3 rounds). Idempotence
  control: repass on a fully-certified state must be a no-op.
- **R4 — the gates stay in charge.** Refit poses re-verify through the
  frozen §15.4 gate (or the piece's already-gated pose); emissions
  face the same LDPC+CRC certification. Repass can only convert
  failed→certified honestly or leave the state unchanged.

v1 scope: (1) certified-neighbor-supervised re-decode — pieces holding
BOTH certified and failed tiles get label-refit (refine_on_sites and
recal_llrs_from_labels are label-source-agnostic: feed pilots UNION
certified cells) + re-sample from original glass + supersede (the p8
pattern: 9/18 certified feed the other 9); (2) failed pieces re-run
through the §15.6 anchor chain under the updated pending set (free
second chance; no labels apply — no placement); stretch (3) the
boundary-ribbon placement prior for sub-grain strips. Word-path-only
pieces = v1.1 — PROMOTED TO THE NEXT BUILD by the try_2 real-scan
verdict (v1 = 0 conversions on a 46:3 word:correlation state; 95 of
134 covered-failed tiles are marginal, clustered confident-wrong =
the refit class, sitting under word-path pieces — the §15.6 word
path's own success structurally starves v1's correlation-class
lever). v1.1-a design (2026-07-11, full record in the 018 log
close-out) — **BUILT 2026-07-12 (018.8)**: CONDITIONAL TRUST — word
evidence is higher-trust where it certified, measured-bad inside
failed tiles; the label-refit emission EXCLUDES the piece's
PROTECTED word cells (word-covered cells outside failed tiles,
frozen per round; the pre-existing exclude_idx emitter hook), so
word observations are trimmed on exactly their failed-tile cells.
(Adversarially-reviewed refinement of the record's failed-tile
INCLUDE-mask sketch: an include mask also discarded fresh refit
coverage on never-observed gap cells under word pieces — no word
evidence exists there for trust to protect; measured loss >=17
low_coverage tiles on the real 4-scan state. The exclusion form is
bit-identical on word-covered cells.) Trim re-adds copy
tile_words/fail_errs/meta directly (pilot_ber_est is a derived
property — an add_placed_fragment re-add weight-floors kept word
evidence to 0.05); the related-sids matcher grew an endswith arm
(`repassN/keep/<base>` keeps of single-sid word pieces have no
trailing segment — the v1 matcher would re-emit the piece as new in
round 2); repass invocations RESUME their round numbering past any
surviving repassN/ sids (a fresh counter re-derives colliding
emission sids and wedges the state — review-reproduced); no
anchor-pose constructor needed (the global placer search finds
word-piece poses; pose-from-words is a compute optimization).
Additive beyond the record: word-touched pieces with no observation
cell in any failed tile are SKIPPED (nothing to convert; the pruned
pending set can exclude their true pose from the re-placement
search).
Pre-registered bars (synthetics): >0 failed→certified conversions on a
locally-degraded fixture; 0 wrong certifications (GT-checked); no
regression of already-certified counts; fixed point within ≤3 rounds;
no-op on a fully-certified state. 018.8 MEASURED CAVEAT on the
conversion bar: the synthetic channel cannot host the v1.1 target
class — acquire's ctx+PAVA calibrates away every uniform
contrast/noise degradation (pilot BER 0.000 at levels that break the
v1 driver path), and within-window drift does not exist in a rigid
render — so the conversion bar is measured on REAL session states
(the 018.8 A/B), while tests/test_repass_v11.py pins the machinery
bars (trust boundary, trim algebra, keep quality, lineage matcher,
monotone fixed point, zero wrong certifications).

**15.8 Pilot-first piece acquisition (2026-07-12, decoder-axis — the
routing inversion; DESIGN registered pre-build, user decision in the
main thread; adversarial design-review round applied, 45 confirmed
findings / 8 distinct majors folded in below).** §15.1's staging
doctrine — big pieces acquire by the Stage-A/B word path, only
sub-grain leftovers get the "expensive" correlation path — is
INVERTED: **correlation against the seed-predicted pilot field becomes
the PRIMARY geometric solver for every piece, and the word machinery
is demoted from solver to evidence-reader at known positions.** The
size-threshold routing constants (WORD_PATH_MIN_MM2 / TILE_PATH_MIN_MM
/ SPLIT_CELLS / SPLIT_CORE_CELLS) cease to exist as correctness logic.

**Implementation status amendment (2026-07-14, current survey contract
updated 2026-07-16).**
E022 implements the clean, independent placement/addressing subset of this
inversion in `paperholo.pilotsearch`, against the actual post-021.6 survey
contract. It makes page-wide pilot-field correlation primary for arbitrary
partial and four-tile-straddled windows, retains one complete-word BCH
attempt only when measured faster and validates its implied origin against
the same field (search AND disjoint validation parity), and records
known-position BCH outcomes under the one-way trust rule at full t=13
errors-and-erasures strength. It processes largest regions and densest
windows first, applies a SITE-granular `need_mask` on every route
(cross-scrap halves of one pilot tile union and decode), and uses a
previously accepted window's full pose plus page origin only as a bounded
neighbor-search prior. The v2 pose is measured per WINDOW: both lattice
fundamentals of the window's gradient spectrum invert to a full 2x2
Jacobian (rotation + anisotropic scale + shear, blind mod 90), phase locks
subpixel, sampling reads the ORIGINAL raster through the pose (one box
prefilter as aperture; no rotation, no predecimation), and a signed-margin
train/held-out refinement polishes each accepted pose. Scanner y-steps
split into pose components; folds appear as two measured angles; a
straddle audit strips minority-side emission. Qualification: pose battery
exact at 8/11.7/23.85 px per cell (worst mapping error 0.199 cells;
0.029 at native 24), adversarial nulls 0/49 FA over 784 field hypotheses,
four-page rivals lose, wrong seed refused. **Full six-scan sessions (user
runs) recovered the COMPLETE 925/925 pilot-tile map of the cut e018 sheet
at BOTH footings — native 4800: 868 matching words / 0 contradictory / 22
refused; decimated 1600: 877/0/13 — zero contradictions in ~1,780
attempted reads.** This does **not** implement S4 payload emission,
LDPC/CRC certification, or E023 feedback. Measured open: sub-100-site
scraps refuse honestly (a decoy dipped to 0.166 at 61 search-parity sites,
under the 0.20 rival bar frozen at >=135-site support) pending a
support-conditional bar; gate constants remain inherited-then-validated.
E022's held-out correlation gate supersedes the provisional §15.8 session
gate only inside this standalone stage; the rest of this section remains
the registered full-receiver design and historical rationale.

Measured basis (e018 real-scissors forensics, 2026-07-12; the scan-2
emission findings adversarially verified cell-exact). From SCAN-1
(decimated-1_1600.tiff): p13 (593 mm²) — word path
all-formats-rejected, whole-piece rigid placement floors at 0.263 >
gate while its OWN 150-cell windows place at 0.094 (5/11 pass), and
the window-split gate refused to engage (core 33k < the 52k
threshold): a measured-placeable piece lost to routing alone; p14
(548 mm²) — one global lattice-angle estimate ~4° wrong killed BOTH
paths while the measured-correct answer (scannorm residual −4.245°)
sat in-pipeline, discarded by the |seed| ≤ 1.5° clamp; p15 (469 mm²
thin sliver) — best window 0.172, 1/7 pass, the honest-marginal
class. From 018.2: p5 — 47 mm rigid 0.248 vs per-quadrant
0.043–0.101 (the I3 coherence-length fact). From 018.7: 95/134
covered-failed tiles sit MARGINAL against the r0550 ~25% cliff —
per-window geometry + recal is therefore PROJECTED (not yet measured)
to convert tiles even on pieces that already "succeed"; bar (b)
reports the realized count. From SCAN-2 (decimated-1-2nd_1600.tiff),
the emission-poison classes: (i) the segmenter's find_objects bug
(`lab[sl] > 0` absorbs a bbox-intruding neighbor's component; fixed
at source 2026-07-12) let a −44.7° piece drag a 162k-px foreign lobe
to a wrong page location — 1,711 coin-flip cells (GT-BER 0.473) at
weight 0.465 into 4 otherwise-uncovered LDPC tiles — while
per-component pilot-site mismatch separated cleanly (main lobe 0.146,
foreign 0.471); (ii) the word path's window RECTANGLES emit off-scrap
cells (mask= gates window selection only): p4 emitted 6,233+5,403
cells at GT-BER ~0.50 and weight 0.87–0.91 onto a neighboring scrap's
territory, suppressing ≥1 certifiable tile; scan-1 p1 same pattern,
8,600 wrong cells at |LLR| > 3.

**The operative admission gate, stated once** (design-review major:
the first draft conflated two gate families): every §15.8 placement
runs the SESSION GAP GATE — best mismatch < 0.20 AND every rival
> 0.20 AND (rival − best) ≥ 0.08 — the 016.4-lineage tuple that all
evidence above and every 0-false record on file (016.4 ×4-admissions,
016.7's 0/355, the 018.3 GT audit) were earned under. §15.4's frozen
clean-regime pair (true < 0.15) stays the library default in
`place.py`; no session driver has ever run it — the 016 driver
measured 0.15 rejecting real-toner rotated pieces at ~13–14% BER.
§15.4's support-aware z and rival semantics are unchanged.

Four stages, per segmented piece:

- **S1 ANCHOR.** Pick the densest-core window (~150–200 cells a
  side ≈ 625–1,110 pilot sites at the exact 1/36 p60b6 density);
  solve (angle, origin, rot90) by padded `place_fragment` under the
  session gap gate. Angle candidates are SEEDS ordered
  cheapest-first — segmenter estimate, then the scannorm residual
  UNGUARDED (the 1.5° clamp discarded p14's correct answer), then a
  coarse ±6° sweep at 0.5° step (step ≤ the measured 0.5–0.75°
  gate-passing band width, so a band cannot fall between samples)
  with a 0.25°-step fine pass around the best coarse hit; stop at
  first gate-pass. Sweep-envelope constants are v1 initials, tuned
  against wall time in-build. Anchor-fail retries at the
  next-densest window (top-3 ladder — I1 retry-elsewhere: the
  densest window may sit on damage). This is the piece's only
  PLANNED full-page FFT search; the retry ladder and S2 re-anchors
  are bounded exceptions, all counted in the wall-time report. A
  piece with no gated anchor after the ladder falls back to the
  Stage-A word path as today (I1: certifiable word evidence must not
  be discarded); that fallback inherits the mask-filtered emission
  fix from the main-thread package (named reconciliation
  dependency).
- **S2 CHAIN.** Rigid-body-predict every other window's origin from
  the anchor; per-window LOCAL refinement
  (`segment.refine_on_sites`, ±0.6°, continuous phase). **Local
  verification is a real test, not an argmax** (design-review major:
  refine cannot fail on its own, so an ungated chain would emit
  under E1 vacuously): a chained window is ADMITTED iff its
  held-out-site mismatch (the refine_on_sites train/held-out split)
  reads < 0.30 — the per-component bar anchored just under the 014.4
  decoy floor (~0.32; measured separation: verified windows
  0.043–0.146 vs the foreign lobe 0.471) — AND its refined origin
  sits within ±2 cells of the anchor's rigid prediction (the
  consistency edge, defined on the prediction residual). The 0.30
  constant is PROVISIONAL until the bar-(c) GT audit validates it. A
  window failing either test may re-anchor ONCE (its own gated
  full-page search); a re-anchored window whose pose disagrees with
  the anchor's is a legitimate SPLIT — a merged touching scrap (the
  measured scan-2 class) or a physical break — and stands on its own
  gate. Honesty note on the break class: the 014.2 crease band is
  NOT geometric evidence for re-anchoring — that log measured
  geometry exonerated at the crease (genie gain 0.04 pp; cracked
  toner, irreducible); folds-break-rigidity is plausible but
  unmeasured, and merged scraps are the measured justification.
- **S3 WORDS-AS-READS.** With geometry locked, decode pilot BCH
  words at KNOWN tile positions — no Stage-A search. Two pieces of
  NEW machinery, named as such (design-review major: this is not
  free plumbing): (i) a known-position word reader — site
  enumeration exists (`place.fragment_pilot_sites`, the pilots
  geometry), but the descramble + BCH decode + address-verify
  assembly at a known tile is new code, with the same rot90
  bit-order and keystream-sign hazards `_emit_placed` handles; build
  it against render-extracted GT, never retyped draws; (ii) a
  tilemap extension attaching word records to placed fragments
  WITHOUT the v1.1-a weight-floor path. **One-way trust rule**: word
  reads may only ADD evidence. A decoded word feeds labels, tile
  records, and diag panel D; a failed read on an attempted tile is a
  logged diagnostic that never enters pilot_ber_est or any
  weighting/quality path (the starvation/veto trap: a structurally
  cut tile recorded as a 13-error failure would displace the
  placer-derived quality estimate and act as a de facto veto —
  exactly what "diagnostics, never vetoes" forbids). Word decode
  consumes CORE-mask sites only; rim sites are erasures by
  definition (measured ~coin-flip); a tile with insufficient core
  sites is NOT READ, not "failed". Errors-only in v1. The 014.5
  erasure rung (2e+f ≤ 26) ships wired behind a flag, default OFF,
  exercised only after errors-only parity (one lever at a time):
  pilot-first geometry satisfies its known-position-only doctrine
  everywhere, and a scissored pilot tile with s core word sites
  decodes at the algebraic floor s ≥ 74 only at e = 0 — at the
  measured 4–5% cell BER the practical knee is ~80–90 sites
  (s ≥ 74 + 2e; 014.5's own ladder went dead below 80).
- **S4 EMISSION.** Per-window sampling (means) + pilot-label
  Gaussian recal (`recal_llrs_from_labels`, the measured P2/016.6
  path) for EVERY piece. Stated plainly (design-review major): on
  pieces the word path serves today this REPLACES the ctx+PAVA
  detector ladder (measured ~3.5× at 16 px/cell, 014.2) with a
  different, weaker-pedigree detector — a REGISTERED RISK, guarded
  by bar (b)'s certified-tile count; if big-piece parity fails
  there, the named lever is ctx-features-at-locked-geometry before
  any architecture retreat. The BOUNDED-LLR INVARIANT (LAYERS §1,
  the 018.7 incident) holds — raw detector scores never cross an API
  boundary.

Emission doctrine — the scan-2 classes, closed honestly: **E1
(locality)** — a cell is emitted only under a window that passed its
OWN admission (anchor gate, chain held-out bar + consistency edge, or
re-anchor gate); whole-piece rigid extrapolation into unverified
regions never emits (the foreign lobe read 0.471 where its host's
verified window read 0.146 — locality is exactly the discriminator).
**E2 (per-component)** — the `lab[sl] == li` fix closes the measured
bbox-ABSORPTION class; label-merging of physically TOUCHING scraps is
NOT closed by segmentation (grow-out dilation bridges small gaps) and
is handled dynamically instead: a merged foreign region fails the
anchor's chain tests and its windows re-anchor to their OWN pose —
merged scraps decode as separate rigid bodies. Backstop: a
per-connected-component pilot-site mismatch audit (< 0.30) over the
emitted core, so no component ever rides a pose it does not itself
support. **E3 (masks)** — all emission, payload AND word evidence,
under the erode-4 CORE mask, never window rectangles; `page_decode`'s
rectangle tiling is not used in pilot_first mode, which retires the
p4/p1 class there; the S1 word-path FALLBACK is the one residual
rectangle-emission surface, covered by the main-thread mask-filter
fix (reconciliation dependency, restated).

Untouched: the printed format (no layout_version bump), the §15.4
z/support/rival semantics, LDPC+CRC certification, weighted_sum
union, the erode-4 doctrine, and `acquire`'s Stage-A as the
whole-page receiver for non-confetti scans — the inversion changes
WHERE evidence is gathered and how poses are searched, never how they
are certified. Gate-provenance note: the wide sweep multiplies
accept-side trials; each added candidate can only LOWER
rival_mismatch (refusal-biased, the I2 argument), but the swept
regime still earns its own decoy validation through the bar-(c) GT
audit before default-on. Relationship to §15.7: v1.1-a's
conditional-trust trim was motivated by word-observation dominance of
a word-path-first state; pilot-first removes that class going forward
(every emission masked, recal'd, locally gated), while repass R1–R4
compose unchanged on any state. Both attack the same 95/134 marginal
pool — A/B accounting runs on fresh states only, no double-crediting.

Cost shape: one PLANNED anchor search per piece (~0.73 s/page-search,
measured 014.5 on a c2 e014-class field under 'valid' unpadded search
with a cached field — the padded c3 e018-geometry figure is its own
measurement) × angle candidates, with seed-first ordering expected to
resolve most pieces in 1–3; plus local refines; plus the bounded
exceptions (retry ladder, re-anchors). Split pieces likely get
CHEAPER than today's chain (which full-page-searches every window);
big word-path pieces newly pay one anchor search. Per-piece wall time
AND re-anchor/retry counts vs the anchor chain are pre-registered
deliverables, measured not argued.

v1 deferrals: dense-label placement (certified tiles' payload cells
as additional correlation reference for scraps straddling
certified+pending regions — F15 alignment) = v1.1; the §15.7
boundary-ribbon prior for sub-grain strips stays deferred; the
pose-from-words compute shortcut stays a §15.6 v2 note.

Pre-registered bars (A/B on identical inputs, `--piece-chain
pilot_first` vs `anchor`, existing modes untouched until parity; both
sides on RECONCILED code — the anchor baseline is re-measured after
the segment fix + the main thread's pending knob package):
(a) 189-piece carve fixture — match the anchor-chain record (189/189
pieces, 0 failed; ≥325 symbols at canvas 1; closure by canvas 2,
where the record collected 512);
(b) scan-1 (decimated-1_1600.tiff, READ-ONLY) into a FRESH state —
match or beat the re-baselined piece yield AND certified-tile count
(the prior "12 word-path-tiled + 2 correlation-placed of 24" is a
main-thread record with no repo artifact, superseded by the
re-baseline run). Expected conversions: p13 and p14 (both
measured-placeable). p15 is marginal — under the session gate its
single passing window (0.172) may place partially; admitted only
through the audit, not counted toward the yield bar. Also REPORTED
(not pass/fail): converted-tile count on the 018.7 95-marginal-tile
pool;
(c) zero false placements AND zero wrong-position emitted COMPONENTS
(per-component GT-BER audit; truth via build/e018_gt = K field XOR
payload keystream, NEVER gen_e018.make_data(), truth path
sanity-checked on certified tiles ≈0.05 BER first) — exercised
additionally on a touching-scraps synthetic that produces a merged
label (the E2 class must appear in an input for its closure to be a
measurement, not a claim);
(d) full suite green (PYTHONPATH=src in worktrees);
(e) per-piece wall time + re-anchor/retry counts reported.


**15.9 Mask-aware ctx detection for pieces — BUILT + MEASURED NEGATIVE
(2026-07-13, decoder-axis; ON BRANCH `pilot-first-receiver`, NOT MERGED).**
The §15.8 S4 fix: bring the word path's ctx+PAVA detector to the
correlation-locked geometry by making `acquire`'s z-normalisation, GMM fit
and 16-context ICM take an optional core `mask` — quantiles and fits over
mask cells only, per-context re-estimation requiring all four neighbours
on-mask and confident, `mask=None` byte-identical. It works as a detector:
on a backing-polluted grid it recovers naive ctx's coin-flip collapse to the
blind floor, reproducing and fixing the `segment.py:107` degradation. **It
is not the confetti lever.** The real-scan A/B reads ctx+PAVA 35 certified
against recal's 35 — not strictly better (gains 3 tiles, loses 3); the
0.224 → 0.214 per-window BER move is PAVA-vs-Gaussian calibration, not a
ctx-ICM gain. **Mechanism: the ctx gain is SAMPLING-dependent** — 3.5× at
16 px/cell (014.2) versus ~nil at the 8 px/cell c3 footing measured here.
Worse, `means_at_zero` (needed only to give ctx a means grid at dA=0)
regressed placement 42 → 35 and introduced a wrong-placement poison, so
ctx's mere *requirement* for a means grid costs placement quality.
Disposition: mask-aware ctx kept in `acquire` as a correct reusable add,
`--pf-emit ctx` opt-in, `pilot_first` default stays `--pf-emit recal`. The
gap to the word path's 110 is upstream — `lock_grid` + `sample_cell_means`
sub-cell phase lock, not emission detection. Full text and numbers:
experiments/018-confetti-c3-play.md "Branch record"; branch commits
`8ebbf0d` (v1) and `5bf9847` (this negative) at
https://github.com/caronni/paper-store/tree/pilot-first-receiver.
In `src/holo` the equivalent protection exists but was re-derived from the
E023b line, not ported: `receive/detect.py` marks any cell without a
complete 8-neighbourhood as context-invalid (bin −1) rather than masking a
dense grid.

## 16. Pilots on the color page (layout_version 4)

Decision record: docs/COLOR-DESIGN.md D3 (this section is the pilot-layer
spec; COLOR-DESIGN holds the channel/coding decisions). Measured basis
cited inline; probe results land in experiments/017-color-channel.md.

### 16.1 The design in one paragraph

The pilot lattice, window code, counter, and receiver stages are the
p60b6.v3 machinery UNCHANGED — same site derivation (`pilot-sites-v2`
label, frozen contract), same BCH(127,50,t=13)→(100,23) words, same
Stage 0/A/B on a LUMA reduction. Two format-axis deltas: (i) word-site
RENDERING — bit=1 prints as the FIXED 2-ink state CM (measured 017.0/P1:
the M281 re-screen renders the CMY triple LIGHTER than CM, 10.1 vs 5.8%
at the Stage-A statistic; CM ties the triple on the AltaLink and is
starved-consumable-robust), bit=0 prints all-plane white — so
acquisition on a color page is byte-compatible with the
hardware-certified K receiver and works from a grey scan; (ii) a
TRAINING-DUST population is added (16.3): 18 sites/tile = 0.5%, per-tile
pure-plane quota 3.
The v4 value-scramble label is the format identity (implicit-signaling
doctrine unchanged).

### 16.2 Why the word stays luma-binary (the two lessons that force it)

003.0 measured the hazard directly: colored pilot marks recovered
601/601 when SITE-GATED, but a blind chroma threshold false-alarms on
26% of K-ink cells — pre-lock detection must not be a color decision.
And acquisition must not be hostage to one consumable: Y is the measured
canary (starved-Y e006c halved Y density mid-page). White-vs-3-ink
degrades gracefully under any single-toner death and is the
maximum-margin binary pair on the page. Alternatives considered and
rejected with numbers (per-plane words, in-alphabet 7-state pilot cells,
value-space co-mingling): COLOR-DESIGN §1/D3 and the 2026-07-10 design
review — the deciding measurements are the M281 raw-channel BERs
(C 8.8–11.1% ⇒ 5–22% word failure), the luma interleaving of the
ink-count partition (gap −0.02 D), and the W↔Y gap (0.066 D) that puts
any-ink renderings at the word code's failure knee on a starved-Y day.

### 16.3 Training dust

A second known-value cell population, NOT carrying message bits:
- POSITIONS: tile-periodic — seed-drawn in-tile offsets
  (`dust-sites-v4` label), identical in every pilot tile, disjoint from
  pilot sites. Periodicity keeps the LDPC shorten-mask derivation
  modulo-based and per-tile capacities deterministic (fountain symbol
  sizes). R3 cost: a second periodic SITE pattern (values are not
  periodic, see next).
- VALUES: keystream-drawn per (seed, page, absolute tile index) —
  `dust-states-v4` label — spanning all 8 states with a guaranteed
  per-tile quota of pure C, pure M, pure Y. Values never repeat
  tile-to-tile (R3: sites-only concession, as for pilots).
- DENSITY: 0.5% of cells = 18 sites per 60×60 pilot tile (frozen by
  probe P3's label-sufficiency curve at the Δ≤0.03 b/cell bar: knee
  ~0.1%, 0.25% already label-sufficient on both engines — 0.5% carries
  2× safety and funds the P4 registration-anchor budget).
- CONSUMED post-lock, site-gated, for four jobs: (1) labeled training
  set for the 8-class detector (blind-EM is measured dead: LOOP-C 0.999
  vs furniture-QDA 1.456 b/cell); (2) per-plane registration — pure-
  plane dust centroids per RGB channel fit each plane's offset field
  (global + linear-in-y; the CAL-1 drift-model shape, Y −0.5→−4.9
  dots), answering 004.0a's broken cross-plane pooling by measurement;
  (3) PAVA calibration labels per level (the 014.2 pattern); (4) a
  per-plane consumable canary (dust-class accuracy per plane is a
  direct health readout — unlike a per-plane WORD, which the 07-10
  review showed fails even on healthy toner in the raw channel).

### 16.4 Acquisition contract on color pages

Stage 0 (lattice/pitch), Stage A (3600 phases × rot90, t=13), Stage B
(slip voting, y-neighbor), sub-cell anchors, F13 placement: all run on
luma, code-identical to K pages, with ONE measured receiver rule (P1):
on color pages the Stage-A pinned-0.5/0.5 2-GMM is fit on the GATHERED
WORD-SITE population (50/50 by keystream construction), not on all
window cells — the all-cells fit on a mostly-ink page costs up to 2×
BER; the site fit recovers the oracle threshold within ~0.5 pp on every
measured dataset. P2 answered the lock question: screen DECOYS are a
non-issue (165-lpi luma contrast ~6, never captures) and
AltaLink-printed composite locks at K-class quality; but the M281's
off-lattice re-screen ATTENUATES the c3 luma cell line ~3× — blind
pitch ID fails on 75% of tiles at the 1200 dpi flatbed footing, so
M281-printed color pages require the Canon 8 px/dot footing (expected
rescue per the 014.2 mechanism; confirmed by E017.4's first Canon RGB
scan, with format-path pitch ID 8/8 at 8 px/dot) or a per-plane-channel
lock fallback. Never acquire from
home-flatbed COLOR-mode scans: that scanner mode lays an 11.3 px comb
that hijacks pitch identification (P2 instrument fact).

### 16.5 What deliberately did NOT change

Counter geometry, code parameters, t=13 single-stage acceptance, FA
arithmetic, slip-fold handling, erasure decoding (known-position, 014.5),
the placer gate constants, grain expectations at c3 (15.1 mm word-
guaranteed, 011.0) — the color page inherits the K page's acquisition
characterization wholesale BECAUSE the word channel is unchanged. Any
measured deviation on hardware is a finding about the composite CHANNEL
(screen, crosstalk), not the pilot design, unless pilot-cell BER itself
diverges from the co-located payload BER (the 014.1 fold-artifact check
carries over).
