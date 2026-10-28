# Holographic Paper Archive — Design Document

**Version 0.4 — Layer 0 measured and frozen on the reference engine; layered architecture, color-channel analysis, single-layer feasibility study**

*v0.4 changes (2026-07-04, from experiments 001.4–003.0 on the HP CLJ M281fdw; the prior text is frozen verbatim in docs/DESIGN-v0.3.md): §2.4 gains the per-paint-path fidelity rule and the measured channel freeze — any page region carrying more than one colorant plane is rendered contone and re-screened (~165 lpi) by this RIP class regardless of emission path, while single-plane imagemask stays bit-faithful; §3 splits the geometric channel by owner — the printer contributes smooth 60–80 mm wander and anisotropic scale, the flatbed scanner contributes the discrete transport steps (001.4's step catalogs are hereby re-attributed to the scanner), a deterministic 18.6 mm CCD comb, and an unstable y-scale; §4.3's M-B constrained-pattern variant graduates from research profile to measured M2 candidate; §5.2 gains an implementation-divergence note on pilot density and a measured chroma-pilot variant; §8.1 adds the measured capacity ladder for the reference engine (the §8 tables assume a 1200-dpi-native engine and stand as design targets only); §9.1 formalizes the CAL-1 calibration artifact with its truth hierarchy and canary discipline. Explicitly reconsidered and NOT changed: the CMY-not-CMYK decision (§2.3 confirmed by measured K-vs-CMY margin), cell=2's M2-gated status, and the layered-over-single-layer verdict (§10).*

*v0.3 changes: §5.2 corrected — a data⊕PN field has zero correlation gain against the keystream, so absolute addressing now uses a sparse pilot lattice carrying a 2-D window-property code (perfect maps / M-arrays); capacity tables now include the ≈2.5% pilot tax; §10.2 adds the capacity–grainlessness–tractability trilemma; §5.1 gains the NRZ-null caveat — lattice acquisition requires a rectifying nonlinearity, found by the starter repo's first simulator test.*

## 0. Executive summary

This document specifies a system for storing digital data on laser-printed A4 paper at 1200 dpi with three defining properties: no visible registration marks or structure (the printed sheet is statistically white noise at every scale), holographic recoverability (any sufficiently large fragment of the printed volume — a 2D patch or a 3D "bite" through a stack — reconstructs the entire payload, up to a designed fraction f), and multi-decade media survivability.

The architecture is a five-layer stack: physical (printer/scanner/toner/paper channel), modulation (symbol lattice on a 3×3-dot cell), synchronization (self-clocking lattice + a statistically hidden ≈2.5% pilot lattice carrying a 2-D window-property position code), inner FEC (soft-decision LDPC per spatial tile), and outer erasure layer (RaptorQ fountain code across the whole volume, with symbol identity derived from recovered geometry rather than headers).

Key conclusions established below:

1. **Color is usable, but as CMY, not CMYK.** Fused toner is pigment-in-polymer and is archivally excellent in dark storage; the weak link is yellow (three independent reasons). Black toner cannot coexist with CMY data because it is spectrally colinear with a C+M+Y stack. The CMY variant yields ≈2.5–2.7× the net density of K-only.
2. **Nominal capacity:** ≈1.8 MB net per A4 side (CMY, f = 0.5, i.e. "any half of the printed area reconstructs everything"), ≈1.8 GB per duplexed 500-sheet ream. Conservative K-only archival profile: ≈0.39 MB/side. Aggressive profile: ≈5.9 MB/side. All figures are net of the 2.5% pilot overhead.
3. **Single-layer ("flat hologram") encoding — printing pseudorandom 1-bit projections of the entire payload — is computationally feasible within a <$1000 budget** once two facts are respected: the modulation/sync layers cannot be collapsed away (physics), and the projection operator must be structured (fast-transform or sparse), not dense. The binding constraint is not compute but information theory: dense 1-bit projections pay a provable ≈20% rate penalty versus the layered stack (≈33% with today's algorithms), plus an all-or-nothing failure mode. Verdict: layered by default; a hybrid and a genuinely novel "progressive hologram" variant are specified as research targets.

---

## 1. Requirements and threat model

**R1 — Density.** Maximize net bits per A4 sheet at 1200 dpi laser printing, consumer flatbed scanning (≥2400 dpi optical) for recovery.

**R2 — Holographic recovery.** A design parameter f ∈ (0,1]: any subset of printed area of total fraction ≥ f (plus small overhead ε), in any geometry — contiguous patch, scattered fragments, a diagonal cut through a multi-sheet stack — recovers the full payload. Corollary (information-theoretic, no scheme evades it): net payload ≤ f × raw channel capacity of the full volume. Physical volume holograms obey the same law — a hologram fragment reconstructs the full scene at reduced resolution, i.e. fewer bits.

**R3 — No overt structure.** No timing marks, quiet zones, finder patterns, headers, or visually periodic structure. Every printed region is statistically indistinguishable from every other (uniform pseudorandom field at ≈ constant ink density). Motivations: no single point of failure at marks, no wasted area, plausible visual deniability, and aesthetic uniformity.

**R4 — Longevity.** Decodable after 50–100 years of dark storage under archival conditions; graceful degradation under partial damage (water, tearing, abrasion, fading, yellowing).

**R5 — Self-containment.** Recovery must not depend on any external database. A future decoder needs only: the printed sheets, the format specification, and the public seed. (The bootstrap problem is addressed in §9.)

**Threat model (degradation & loss events).** Localized destruction: tears, burns, water tide-lines, mold colonies, abrasion/flaking of toner → spatial erasures, handled by outer layer. Global drift: pigment fade, paper yellowing, contrast loss → SNR erosion, handled by inner-code margin and per-plane rate allocation. Geometric: humidity cockling, fuser shrink, curl → low-frequency warp, handled by sync layer. Adversarial forensic artifacts: printer-injected yellow MIC tracking dots → sparse deterministic interference in the Y plane (§2.4).

---

## 2. Media physics: can we use all four toner channels? (Layer 0a)

### 2.1 Why laser toner is the right medium at all

Fused toner is a fundamentally different material system from inkjet ink. A toner particle is a 5–8 µm polymer bead (polyester or styrene-acrylate, glass transition Tg ≈ 55–65 °C) with pigment crystallites dispersed inside it at roughly 5–10% loading. Fusing melts the polymer into a thin film mechanically keyed into the paper fibers. Consequences:

- The colorant is a **pigment** (insoluble crystalline aggregate), not a dye (isolated molecule in solution). Pigments are orders of magnitude more resistant to photo-oxidation; this is the difference between a poster that fades in two summers and museum paint.
- The pigment is additionally **encapsulated in resin**, adding an oxygen/UV/pollutant diffusion barrier.
- The image sits in a fused thermoplastic layer: waterproof (water destroys the paper before the toner), smudge-proof, and chemically inert to mild acids/bases.

Dark-storage permanence of fused toner on alkaline paper is generally regarded as excellent — comparable to or better than silver-halide prints — though, unlike inkjet, no standardized vendor permanence ratings exist, so we design margins rather than trust datasheets.

### 2.2 Per-channel colorant chemistry and degradation ranking

Typical pigments (vendor-specific; treat as representative classes):

| Plane | Pigment class (typical) | Lightfastness (Blue Wool) | Thermal/acid stability | Archival verdict |
|---|---|---|---|---|
| K | Carbon black | 8 (effectively immune) | Inert (carbon inks survive on 2000-year-old manuscripts) | Reference standard |
| C | Copper phthalocyanine (PB15:3) | 7–8 | Stable > 200 °C, acid-resistant | Near-K |
| M | Quinacridone (PR122 class) | 7–8 | Very good | Near-K |
| Y | Azo / benzimidazolone (PY74, PY155, PY180…) | ≈5–7, strongly grade-dependent | Good resin protection, weakest intrinsic photochemistry | **Weakest link** |

**Degradation vectors, quantified where possible:**

**Light/UV.** Irrelevant in dark storage (the archive's normal state). Under exposure, Y fades first, K never. Design rule: assume Y-plane contrast may halve over the horizon if storage discipline fails; C/M/K margins dominated by other factors.

**Heat.** Two distinct mechanisms. (a) *Blocking/offset:* above toner Tg (≈55–65 °C), stacked sheets under pressure can sinter together and transfer toner. This sets the hard storage ceiling: keep < 35 °C, ideally < 21 °C, and interleave or sleeve high-coverage sheets. (b) *Cellulose hydrolysis:* paper embrittlement roughly doubles in rate per 5–7 °C; this attacks the substrate, not the colorant.

**Acidity.** Toner is acid-inert; the paper is not. Acidic (lignin-containing, alum-rosin sized) paper self-embrittles and **yellows** — and yellowing is not cosmetic here: it raises broadband blue absorption of the substrate, which is exactly the detection band of the yellow plane (and secondarily magenta). Acid decay therefore selectively erodes Y-channel SNR even though the toner itself is untouched. Mitigation is cheap and total: ISO 9706 "permanent" paper (lignin-free, alkaline reserve ≥ ~2% CaCO₃) or ISO 11108 cotton archival stock. Prefer **OBA-free** paper: optical brightening agents decay over decades, shifting the blue-channel white point — a slow calibration drift the decoder must otherwise track.

**Humidity.** Paper is hygroscopic and anisotropic: expect up to ~0.3–0.8% dimensional change across large RH swings, plus cockling. This is a *geometric* threat (handled by the warp-tracking sync layer, §5), not a data loss per se; cyclic RH can also microcrack very heavy toner deposits — one reason the design caps per-plane ink coverage (§4.4). Hold 30–50% RH; mold risk rises sharply above ~65%.

**Pollutants (O₃, NOₓ).** Significant for dyes, minor for encapsulated pigments. Boxed storage suffices.

**Mechanical.** Toner rides on the surface (it does not penetrate like ink), so folds, scratches and abrasion flake it off locally. These become spatial erasures — precisely the failure class the outer fountain layer is built for. Handling rule: never fold; sleeve or box flat.

### 2.3 The K-vs-CMY colinearity problem

Using all four channels as four independent bit-planes fails for a spectral reason, not a chemical one. C, M, Y each absorb in one third of the visible spectrum — almost exactly the R, G, B bands of a scanner. K absorbs in **all three**. Therefore a K dot is nearly indistinguishable from a coincident C+M+Y stack: the 4-plane → 3-channel measurement is rank-deficient. Recovering 4 bits/site from 3 spectral measurements relies on second-order spectral differences between composite black and true black — real but small, and the first thing to vanish as toners age and scanners vary. Two further practical strikes: consumer driver pipelines perform gray-component replacement (silently exchanging CMY for K), and the K plane in "composite black" modes is halftoned differently.

**Decision: use C, M, Y as three independent binary planes; do not print K in color mode.** Each plane is detected in its complementary scanner channel with a stable, calibrable 3×3 crosstalk matrix (toners have side absorptions: M absorbs some blue, C some green). Detection is done in optical-density space (−log reflectance), where overlapping toner layers combine approximately additively (Beer–Lambert), making the unmixing linear.

A 16-color CMYK variant (4 bits/site) is characterized in §3.4 for completeness; its effective yield after the ill-conditioning penalty is ≈3.2–3.5 bits/site at sharply higher error rates — dominated by clean 3-bit CMY. 

### 2.4 Two color-mode gotchas that must be engineered around

**Machine Identification Code (MIC).** Nearly all color laser engines covertly print a tiled pattern of faint ~0.1 mm yellow dots (serial number + timestamp steganography) on every color page. This is deterministic sparse interference in the Y plane — well under 0.1% of symbol sites, trivially absorbed by the inner LDPC, but it is one more tax on the already-weakest plane, and it cannot be disabled. K-only monochrome paths on many engines skip MIC entirely (a minor additional argument for the conservative profile).

**Driver color management.** The entire rendering pipeline (ICC transforms, halftone screening, resolution enhancement, toner-save) must be bypassed: the encoder must deliver raw, bit-exact 1-bit bitmaps per plane (PostScript/PCL separations or vendor raw modes). Verify with a microscope/loupe that the engine reproduces the plane bit-for-bit. Caveat: many "1200 dpi class" color engines are 600 dpi native with interpolation; the entire design below is parameterized by the *native* addressable grid — characterize the actual engine first (§9.1).

**Per-paint-path fidelity (v0.4, measured — runs 002.0–003.0).** Bit fidelity is a property of the *paint path*, per plane — not of the transport. On the reference engine's PS3 emulation: single-plane `imagemask` is bit-faithful for C/M/K (the Y plane carries a native ~224 lpi 26.6° texture even on this path); but **any page region carrying more than one colorant plane is rendered contone and re-screened (~165 lpi plane-angle families)** regardless of emission — DeviceCMYK `image`, DeviceN `image`, sequential masks (which additionally knock out earlier planes at overlap dots), Separation-space masks; `setoverprint`/OPM are accepted and ignored; the trigger is region overlap, not mark overlap (dot-disjoint emissions screen identically). The Layer-0 **channel freeze** for such engines: (a) clean single-plane mask channels, plus (b) the *characterized* screened composite channel for overlapping planes — measured, not fought; verify-on-write (§9) absorbs its calibration-drift exposure. Every new engine/path is gated by calibration-page canaries (screening detector with a ground-truth-spectrum control, §9.1); "verify with a loupe" is thereby mechanized. Open aging note: screened cells carry more edge perimeter and less toner mass than solid cells — flag for accelerated-aging measurement. Shelved escalations with measured price tags: PJL variable reconnaissance (free, unfired) and a PCL 5c `Esc*r-4U` planar-bilevel emitter (ceiling ≈ +0.09 bits/cell at cell=4; up to +0.5–0.9 at cell=3 contingent on an unproven raw raster path *and* 3-dot mixture cells surviving the measured ±2–5 dot plane misregistration).

### 2.5 Plane registration: why color does not break the no-fiducials sync

Tandem color engines write each plane with a separate drum/exposure unit; plane-to-plane misregistration of one to two 600-dpi dots (≈40–85 µm), slowly varying across the page, is normal. Two facts rescue us. First, all planes are fused in the same pass, so **inter-plane offsets are frozen at print time**; every subsequent paper deformation (humidity, aging) warps all three planes *together*. Second, the sync layer (§5) gives each plane its own PN sequence, so each plane is acquired, warped, and demodulated in its own coordinate frame — inter-plane registration is never assumed, it is *measured once* and then known. Crosstalk unmixing operates on the three individually-resampled planes.

### 2.6 Answer to the headline question

Yes — with the CMY restriction, per-plane code rates, and archival media discipline:

- **Material loss over time is real but rankable: K ≫ C ≥ M > Y.** In dark storage on ISO 9706+ paper at ≤21 °C / 30–50% RH, C/M/K margins are effectively static over a century; Y-plane margin erodes slowly via pigment photochemistry (if exposed), substrate yellowing (if paper/storage is wrong), OBA drift, and MIC pollution.
- The design response is not to reject color but to **allocate unequal protection**: Y carries a lower-rate inner code (e.g. R_Y = 0.60 vs R_C = R_M = 0.75) and the *bulk* priority class, while C and M carry the critical/index priority classes (§7.3).
- Net effect: CMY triples raw density; after crosstalk margin and Y's rate haircut, **≈2.5–2.7× net density versus K-only**. For century-scale, zero-maintenance cold archives where density is secondary, the K-only profile remains the gold standard.

---

## 3. Layer 0b: the print–scan channel model

Everything above the physical layer is designed against this channel. Per plane, the printed binary field passes through, in order: electrophotographic dot formation (dot gain of 10–30%, i.e. printed dots are fatter than addressed; edge raggedness from toner scatter; isolated single dots at 1200 dpi render unreliably or not at all), an effective point-spread function of roughly 1.5–2 dot pitches FWHM (laser spot × toner spread × fuser), 1-D periodic gain ripple from drum velocity error ("banding"), placement jitter, paper formation mottle (low-frequency reflectance noise), then — possibly decades later — substrate drift (yellowing, brightness loss), and finally the scanner: its own MTF, sensor noise, and a global geometric warp (platen optics + paper deformation).

The abstract channel per symbol is therefore: **binary-input, soft-output, with 2-D intersymbol interference, slowly-varying gain/offset fields, and a piecewise-smooth geometric warp**. Three design consequences: symbols must be larger than single dots; detection must be soft (grayscale in, LLRs out) with 2-D equalization; and all synchronization must track a spatially-varying, piecewise-smooth warp — smooth in the fast-scan axis, stepped in the process direction as observed through a flatbed. Scan at ≥2× the symbol frequency (2400 dpi scan for the nominal design), 16-bit gray or 48-bit RGB, all scanner "enhancements" and ICC corrections off.

**Measured warp decomposition by owner (v0.4, run 002.0b rotation test).** The received warp is a sum with two owners, and the simulator models them separately. *Printer (print-frozen, travels with the page):* smooth process-direction wander at 60–80 mm periods, ~1 dot amplitude, plus anisotropic scale (page-y prints 0.23% ± 0.03% short of page-x). *Scanner (fresh per scan / fixed in the scanner frame):* stochastic y-transport steps of 0.25–1.95 dots (~9 per 40 mm — the discrete steps of runs 001.2–001.4, originally mis-attributed to the printer), a deterministic ~18.6 mm CCD chip-joint comb (~0.9 dot, calibratable once per scanner), and an unstable, scan-mode-dependent y-scale (+0.6% class). Operational consequences: never mix scanner color modes for absolute y-scale; where the format allows, scan with the page's process direction on the CCD axis (measured 1.3–2.0 pp raw-BER improvement at cell=3).

### 3.4 Color-mode variants (Layer 0 summary)

| Variant | Bits/site (raw) | Detection conditioning | Longevity | MIC exposure | Verdict |
|---|---|---|---|---|---|
| **V-K** — black only | 1 | Excellent (max contrast) | Best possible | Avoidable | Century-scale archival profile |
| **V-CMY** — 3 binary planes | 3 | Good; stable 3×3 unmix in density domain | C,M ≈ K-class; Y weakest | Y plane only | **Nominal profile** |
| V-CMYK16 — 16 colors/site | 4 | Poor: K colinear with C+M+Y; rank-deficient | As CMY | Yes | Rejected: ≈3.2–3.5 effective bits at much higher error rate |
| V-duplex (orthogonal to above) | ×2 area | Show-through appears as low-frequency noise on the far side | Needs ≥100 g/m², high-opacity stock | — | Recommended with heavy paper |

---

## 4. Layer 1: modulation — the 2-D analog of GCR/RLL

### 4.1 Symbol lattice

The nominal symbol cell is **3×3 printer dots** (≈400 cells/inch at 1200 dpi native), printed solid-on or solid-off. This is deliberately the dumbest possible constellation, because at 1200 dpi the individual dot is not a reliable channel use — the cell is. Printable A4 area (≈200×287 mm inside engine margins) gives **3150 × 4520 ≈ 1.42×10⁷ cells per plane per side**.

### 4.2 Where GCR's jobs went

Group-code recording on magnetic media does three jobs: DC balance, clock content, and run-length limiting. Here, all three are delegated to the **scrambler** rather than a constrained code: every plane's bitstream is XORed with a cryptographic-quality PN keystream (AES-CTR keyed by the public seed and the absolute cell address, §5). The printed field is then i.i.d. Bernoulli — ink coverage pinned near the target, no runs long enough to matter, spectrally white (R3 satisfied for free), and every local patch carries full clock content for the lattice estimator. The rate cost is zero. This is the single most load-bearing trick in the design: **the scrambler is simultaneously the modulation conditioner and the invisibility mechanism.** (v0.2 also credited it with absolute addressing; that was wrong — see the §5.2 correction.)

### 4.3 Variants

| Variant | Cell | Bits/cell | Mechanism | Character |
|---|---|---|---|---|
| **M-A** scrambled solid cell | 3×3 | 1 | On/off, matched filter + 2-D equalizer | **Nominal.** Maximum per-symbol margin, fully self-clocking |
| M-B constrained pattern alphabet | free-form @ native grid | measured ~0.15–0.25 b/dot | 2-D run-length-constrained field (ink-run ≥2, white-run ≥3 — the measured asymmetric physics) + soft trellis detection (true 2-D GCR/PRML, as in page-oriented holographic storage and magnetic recording) | v0.4: MEASURED — 13.1% raw dot BER with naive detection (0.154 b/dot ≈ 86 b/mm², clean K path); white-run ≥2 is dead; motif survival library (exp 003) supplies trellis branch metrics; M2 candidate |
| M-C multilevel ink fraction | 3×3 | 2 | Cell carries 0/3/6/9-of-9 dots on (PAM-4 in ink area) | +1 bit/cell for ≈6 dB margin cost; viable only with strong equalization |
| M-D sub-cell position modulation | 4×4, one 2×2 blob in one of 4 quadrants | 2 | Sparse PPM; ~25% ink | Toner-economy profile; density-neutral vs M-A per area, better media stress |

### 4.4 Ink budget and shaping

Unbiased scrambling ⇒ ≈50% coverage per plane ⇒ ≈150% total area coverage in CMY — heavy (engines rate 240–300% max, but heavy deposits cost toner and raise flaking/blocking risk). Optional distribution shaping biases each plane to ≈37.5% coverage for a 4.6% rate cost (H(0.375) = 0.954), cutting toner mass by a quarter. Recommended for large archives.

---

## 5. Layer 2: synchronization and absolute addressing — no fiducials

Sync is split into *local geometry* (where is the lattice?) and *absolute phase* (which cells are these, in the whole volume?). Neither uses visible marks; local geometry is recovered from the data field itself, absolute phase from a statistically hidden pilot lattice (§5.2, corrected in v0.3).

### 5.1 Local geometry: the lattice is its own clock

Any patch of the printed field — after a rectifying nonlinearity such as a gradient-magnitude map — shows four sharp Fourier peaks at the cell fundamental (±400 cyc/in in x and y). The nonlinearity is not optional: random solid cells are NRZ-like, and an NRZ spectrum has a *null*, not a line, at the symbol rate; edge detection regenerates the discrete line — the 2-D analog of a squaring timing-recovery loop — and high-passes paper mottle and banding away for free. (Caught by the starter repo's first simulation test, whose raw-FFT estimator locked onto mottle instead.) The decoder tiles the scan (e.g. 64×64-cell tiles), estimates a local affine transform per tile from the peak positions, and stitches these into a smooth warp field (thin-plate spline), refined coarse-to-fine — **plus a per-row offset profile that follows transport steps** (v0.4: timing recovery with cycle-slip handling, not spline smoothing alone; the steps are scanner-borne but present in every flatbed scan, and a smooth-only model measurably concentrated ~half of all raw errors into step-crossing bands until the profile was added). This tracks humidity cockle, scanner optics, curl — deformations smooth at the centimeter scale — and the stepped residue on top of them. Rotation is recovered modulo 90°/180°; the PN correlation below resolves the ambiguity, so fragments can be scanned in any orientation, even mirrored (mirror ⇒ correlation fails ⇒ flip and retry).

### 5.2 Absolute phase: a sparse pilot lattice with the window property (v0.3 correction)

v0.2 proposed correlating the received field directly against the keystream. That construction is broken. Every cell carries data⊕PN; the coded data is itself uniform, so at the *true* offset the correlation sums (−1)^data — zero mean, √L fluctuation, no peak, no processing gain. The GPS analogy fails at exactly the point it was borrowed from: in DSSS one data bit spans thousands of known chips, so there is always a long window of pure known sequence to integrate over; here the data rate equals the chip rate and no such window exists. Absolute addressing therefore requires dedicated sync content. Three constructions, in order of preference:

**(a) Pilot lattice carrying a 2-D window-property code — nominal.** Reserve ≈2.5% of cells as pilots whose values encode position via a 2-D array with the *window property*: every k×k window occurs exactly once in the array, so any clean window decodes directly to absolute coordinates — position by lookup, not by search. Such arrays are classical: pseudorandom arrays (MacWilliams–Sloane 1976), perfect maps / de Bruijn tori (Paterson 1994; Etzion), and — in error-tolerant, mass-produced form — the Anoto pen pattern, in which any 6×6-dot window self-locates on a virtual surface of continental scale. Our instantiation spreads BCH-protected coordinate words over the pilot sites, so window decoding tolerates the same raw BER as the payload; plane identity rides on per-plane code offsets.

One subtlety decides implementability: the decoder must know *which* cells are pilots before it knows where it is, so purely pseudorandom pilot placement is circular. Resolution: pilot **sites** follow a seed-fixed pattern of modest period (one pilot per ≈6×6-cell block, in-block offsets repeating with period P = 64 cells); the decoder tests the ≤P² site-phase hypotheses (thousands — trivial) and the coordinate decode validates the winner. This is the design's one measured concession to R3: a hidden 2.5%-density site pattern with ~10 mm periodicity, spectrally negligible beside the cell-lattice lines that §5.1 already depends on, and carrying never-repeating values.

*Implementation-divergence note (v0.4):* the current `pilots.py` delivers 2.44% site density, not the specified ≈2.8% — P = 64 is not divisible by the 6-cell block, leaving 4-cell pilot-free stripes per period axis and thinning the per-window bit budget by ~12%. Reconcile code and spec at M1 (e.g. P = 60 or 72, or 8-cell blocks) with a layout-version bump: the site pattern is part of the printed format, so the change must not silently orphan existing sheets.

**(d) Chroma pilots — measured K-profile variant (v0.4, run 003.0).** For the K-only archival profile, 2×2-dot cyan marks placed in enforced white voids recover at ~100% (556/557; zero false positives) with site-gated detection — chroma replaces the value decode but not the site pattern, since a blind chroma sweep false-alarms on ~26% of K ink. Costs: a visible-structure concession beyond (a) — colored dust is findable — and a measured ~10 pp local miss-rate tax on void-adjacent K ink (enforced voids stress their neighbors' development). An *option* for P-cons, not the nominal profile.

**(b) Pilot correlation — low-SNR fallback.** The same pilots, treated as a sparse *known* sequence, restore classical FFT acquisition when local damage defeats window decoding: processing gain returns because pilot values are known a priori. A volume-wide search costs ~10¹²–10¹³ ops ≈ minutes on one GPU per stubborn fragment.

**(c) Syndrome-based blind synchronization — pilot-free research variant.** The inner LDPC's sparse parity checks are themselves position witnesses: at the correct (offset, descramble) hypothesis the syndrome weight collapses toward the channel BER; at wrong hypotheses it sits at 50% (Imad–Houcke-style blind frame synchronization, lifted to 2-D). Zero rate cost and perfect R3 purity — but discrimination decays as (1−2p)^(check degree), i.e. it is fragile precisely when sync is needed most, and the hypothesis search resists FFT acceleration. Kept as a variant, not the baseline.

### 5.3 Minimum useful fragment: the "grain size" of the hologram

Acquisition needs one successful window decode: addressing ~10¹⁰ cells takes ~33 coordinate bits, so with BCH margin a window of ~60–100 pilot bits suffices; at 2.5% pilot density that is a ≈50×50-cell patch ≈ **3×3 mm** (fallback (b) reaches similar sizes through correlation gain). Robust warp estimation wants comparable area. Combined with the inner-code tile (§6), the effective holographic grain is ≈4×4 mm: fragments below that contribute nothing; above it, every fragment contributes its full area to recovery. This is the discretization the optical-hologram metaphor was always going to acquire on a binary medium.

*Amendment (2026-07-09, decoder-axis — measured grain + fragment sessions; applied from PILOTS-DESIGN §15 with the pre-queued §11 items still pending).* The grain above is the floor for an **isolated** fragment, and "below it, nothing" is too strong. Measured on the 600-dpi engine class: c3 ≈ 13–15 mm placement-guaranteed (run 011.0), c2 ≈ 10 mm (run 014.3: 10 mm 5/5 blind, 8 mm 1/5, 6 mm 0/5). Within a decode **session** that holds volume state, sub-grain pieces remain usable: pilot values are seed-derived and therefore predictable even in not-yet-recovered regions, so a piece that cannot complete a word decode is placed by the §5.2b correlation fallback made cheap by state pruning — site-phase quotient (≤P² hypotheses) then value correlation over only the offsets compatible with the still-pending region set, big pieces first so each placement shrinks the space for the next. Run 014.4 (2026-07-10) measured the mechanics: a 6 mm c2 piece holds 135–139 pilot sites (the first draft's "~35" was a 4× cell-pitch slip, corrected); sub-grain word failure is pure pilot-tile placement geometry (blind = genie-geometry at all 15 probe windows); and the decoy floor of the correlation is the window code's own pairwise distance spectrum (min 32/100 measured) — true-offset mismatch (= channel BER, 0.04–0.09) separates from every decoy by ≥0.20. Session floor extrapolates to ≈ 3 mm at c2 (pilot-bit argument, ESTIMATE); the open item is the piece-local lattice lock on ~71 cells alone. Placements pass a floor-aware correlation-margin gate and are certified by the inner code's CRC (a mis-placed piece wastes itself; it cannot corrupt). Fragment-boundary tiles reassemble across pieces by cell-address union, and session completeness is fountain **rank**, not tile inventory. Doctrine and budgets: PILOTS-DESIGN §15; feedback edges F13/F14 in LAYERS §7.

### 5.4 Per-plane sync

Each color plane carries an independent PN offset (different subkey). Planes are acquired separately, then co-registered *by measurement* — which is what makes engine misregistration (§2.5) a non-event.

---

## 6. Layer 3: inner FEC — turning paper into erasures

Per spatial tile of 64×64 cells (4096 raw bits ≈ 4×4 mm), a soft-decision **LDPC** code (DVB-S2/5G-NR family) decodes from the equalizer's LLRs. Rates are a per-plane ladder set by measured channel quality: nominally R_C = R_M = 0.75, R_Y = 0.60, R_K = 0.65 (conservative profile). Each tile carries an interior CRC (inside the payload, invisible in the field); tiles failing decode+CRC are declared **erasures** to the outer layer. 

Two structural decisions matter more than the code family. **Interleaving is local only**: bits are interleaved *within* a tile, never across the page — global interleaving would maximize burst immunity but destroy exactly the fragment-locality that R2 requires; bursts are instead the outer layer's job. **Joint equalization–decoding** (turbo iteration between the 2-D equalizer and the LDPC decoder) is the cheapest +1–2 dB in the system and pushes the workable raw-BER regime toward ~10⁻¹.

---

## 7. Layer 4: outer erasure layer — where the holography actually lives

### 7.1 Fountain coding over the volume

The payload (pre-compressed — which also makes it fit the incompressible-source assumption — and optionally encrypted) is encoded with **RaptorQ (RFC 6330)** over the *entire multi-page volume*. Each inner tile's payload (≈384 bytes at R=0.75) is one fountain symbol. Symbol identity (ESI) is **computed from geometry**: ESI = F(plane, page, tileX, tileY) — a fixed public bijection. No headers exist anywhere; position, recovered by Layer 2, *is* the metadata. Decoding succeeds from *any* set of K(1+ε) distinct received symbols with ε ≈ 0.02% (RaptorQ: +2 symbols ⇒ failure < 10⁻⁶); the geometry of the surviving set is irrelevant — a contiguous patch, confetti, or a 3-D core sample through the stack are equivalent. The "3-D holographic" requirement is thus free: (plane, page, x, y) is one flat address space, and because fountain symbols are exchangeable, cross-sheet interleaving is automatic rather than designed.

### 7.2 The f-budget

Media area fixes the number of emitted symbols M_sym; choosing payload size K_sym = f·M_sym(1−ε) sets the recovery fraction. f = 0.5 ⇒ any half of the archive's total tile population reconstructs everything. Note f is a *global* budget: destroying 60% of one sheet is fine if the volume-wide survival rate stays above f.

### 7.3 Priority layers (recommended over flat f)

A single small f is expensive (f = 0.1 ⇒ 10× redundancy). Stratify instead: **L0** — format spec, seed fingerprint, archive index/file table: tiny, encoded at f₀ ≈ 0.02 and placed on C/M planes ⇒ *any few cm² of any sheet* recovers the catalog and proves what the archive is. **L1** — critical payload at f₁ = 0.3. **L2** — bulk at f₂ = 0.7. Plane-aware placement: L0/L1 on C and M, L2 dominates Y — the priority ladder and the longevity ladder (§2.6) are aligned.

### 7.4 Layer summary table

| Layer | Function | Technology (nominal) | Variants considered |
|---|---|---|---|
| 0 | Physical channel | 1200 dpi laser, CMY raw planes, ISO 9706 OBA-free ≥100 g/m², 2400 dpi 48-bit scan | V-K, V-CMY, V-CMYK16 (rejected), duplex |
| 1 | Modulation | 3×3-dot solid cells, AES-CTR scrambling, optional 37.5% shaping | M-A/B/C/D (§4.3) |
| 2 | Sync/addressing | Lattice-FFT warp field + 2.5% pilot lattice with 2-D window code (M-array + BCH), per plane | Pilot FFT-correlation fallback; syndrome-based blind sync (pilot-free, fragile) |
| 3 | Inner FEC | LDPC per 64×64-cell tile, soft, per-plane rate ladder, turbo-EQ | RS+hard decision (simpler, −20% density); polar |
| 4 | Outer erasure | RaptorQ over volume, geometric ESI, priority strata | LT/Raptor; large-block RS (inferior at this scale) |

---

## 8. End-to-end capacity budgets

Per A4 side, printable 200×287 mm, native 1200 dpi engine assumed; net columns include the 2.5% pilot overhead:

| Profile | Planes / cell | Cells/side | Inner rate (avg) | f | **Net per side** | Duplex ream (1000 sides) |
|---|---|---|---|---|---|---|
| **P-cons** (century archival) | K, 3×3 | 1.42×10⁷ | 0.65 | 0.35 | **≈0.39 MB** | ≈0.39 GB |
| **P-nom** | CMY, 3×3 | 4.26×10⁷ | 0.70 | 0.50 | **≈1.81 MB** | ≈1.8 GB |
| P-aggr | CMY, 2×2 | 9.6×10⁷ | 0.72 | 0.70 | ≈5.9 MB | ≈5.9 GB |

Calibration against prior art: Twibright **Optar** achieves ≈200 kB/A4 at 600 dpi with Golay hard-decision coding and visible fiducials; **PaperBack** reports up to ≈3 MB/A4 only under ideal conditions. P-nom's ≈1.9 MB with *no fiducials and any-half-recovery* is aggressive but consistent with what soft decoding + fountain layering buys over those baselines. The scanner MTF, not the printer, is the usual binding constraint — hence the 2× oversampling floor and the M-A margin-first constellation.

### 8.1 Measured capacity — reference engine (v0.4; HP CLJ M281fdw, 600 dpi native, 1200 dpi flatbed, runs 002.0–003.0, day-1 numbers)

The tables above assume a 1200-dpi-native engine and stand as *design targets*. On the measured reference engine (4× fewer sites), the leaderboard of deliverable information (mutual information × density; QDA-fold-optimistic; single-sheet variance ~±0.2 bits/cell class):

| configuration | channel | bits/cell (of max) | **bits/mm²** |
|---|---|---|---|
| 7-state CMY alphabet, cell=3 | screened composite | 1.48–1.89 of 2.81 (position-variant) | **92 (best measured)** |
| K 2-D constrained field, ink≥2/white≥3 | clean imagemask | 0.154 b/dot naive; trellis projected 0.20–0.25 | **86 → 111–139 projected** |
| {7-state + K} alphabet, cell=4 (+grey feature) | screened composite | 2.36 of 3.0 | 82 |
| binary CMY composite, cell=6, unmixed | screened composite | 2.66 of 3.0 | 41 |
| single-plane K binary, cell=3 (P-cons anchor) | clean imagemask | 0.85 | 53 |

End-to-end at cell=3 alphabet (~1.7 bits/cell midpoint): ≈600 kB net per A4 side at f≈1; **≈300 kB at f = 0.5** after the inner-code (~0.85×MI), pilot (2.5%), and holographic budgets. The two finalists for M2's rate-ladder decision are the screened c3 alphabet (color, screen- and Y-entangled) and clean constrained-K + trellis (carbon-black archival-grade, chroma-pilot/void-subchannel compatible); measurement supersedes this table when M2's soft pipeline lands.

---

## 9. Operations: pipeline, calibration, bootstrap

**Encode:** compress+encrypt → RaptorQ symbols → assign ESIs to tiles per F → per-tile LDPC encode → scramble with PN(seed, address) → interleave the pilot lattice (§5.2a) → emit three 1-bit plane bitmaps → raw print path.

**Decode:** scan (≥2400 dpi, corrections off) → per-plane lattice FFT + warp field → resample to cell grid → pilot window decode (§5.2a; correlation fallback §5.2b) ⇒ absolute addresses ⇒ descramble → density-domain 3×3 unmix → 2-D equalize ⇔ LDPC (turbo) → surviving tiles + ESIs → RaptorQ → verify hashes.

**Calibration without marks:** the PN field makes every decoded region a training sequence after the fact — an EM loop (acquire → estimate PSF/gain/crosstalk from agreeing cells → re-equalize) converges from a cold start; no test targets are printed. Engine characterization (native grid, dot gain, plane offsets) is done once on scratch sheets before an archive run, then re-estimated blind at decode time.

### 9.1 Engine calibration: the CAL-1 artifact (v0.4, implemented as experiment 002)

**Artifact.** One self-describing A4 scratch sheet (R3-exempt), generated as raw Level-2 PostScript, printed over a raw path, scanned at ≥2 px/dot, analyzed automatically. It measures: native grid per axis and plane; min reliable ink/white features per plane and orientation; edge gain and anisotropy; PSF; density transfer and mottle vs coverage; banding; transport/warp statistics; printable extent, scale, skew; inter-plane registration drift; crosstalk matrix and condition number; raw BER per plane at candidate cells; states-per-cell (binary, multilevel, mixture alphabets, K-colinearity margin); MIC presence. Output: a ChannelParams block for the simulator plus a modulation recommendation.

**Self-description.** Facts unknowable at generation time are queried from the interpreter at print time (default and effective `currentpagedevice`, `languagelevel`, product/version/serial — every read individually guarded) and printed on the sheet as human-readable text *and* a CRC-protected coarse-module machine strip, duplicated. A bare scan plus the public generator suffices; no side-channel metadata.

**Truth hierarchy.** Printed physical measurements outrank print-time device claims outrank generation-time assumptions. (Measured cautionary tale: the reference RIP *accepted* an unsupported resolution request and then mis-rasterized — a granted mode is a fingerprint, not evidence.)

**Resolution rule.** Never request an HWResolution not previously verified on the engine; probe finer grids passively, with stimuli whose death is the datum.

**Canaries.** The sheet carries discriminating detectors for broken print paths — re-screening (GT-spectrum control), resolution clamp, toner-save, edge enhancement, rescale, wrong-interpreter fingerprint — each reported as {pass, fail, indeterminate} with statistic and control, never a bare boolean.

**Protocol.** CAL-1 runs once per (engine, media, duplex side) before any archive run; re-run on consumable change or season-scale RH shift. Scan twice (second placement rotated 90° — separates printer-frame from scanner-frame effects, §3); optional +24 h rescan measures hygroexpansion. Archive sheets remain mark-free; CAL-1 is where the fiducials live.

**Verify-on-write:** every archive run is scanned and fully decoded *before* the source is trusted to it; golden hashes are part of L0.

**Bootstrap (R5):** a future decoder needs the spec. Two or three **human-readable pages** — format description, the public seed, reference decoder pseudocode — are included with every archive volume (and, at f₀, the L0 stratum contains the same text). This is the deliberate, single exception to R3, physically separable from the data sheets. Storage spec: dark, ≤21 °C, 30–50% RH, alkaline enclosures, flat.


---

## 10. The single-layer alternative: printing one giant nonlinear code

### 10.1 Formulation

Collapse layers 3–4 (and conceptually 1) into a single map: let x ∈ {±1}^K be the payload, Φ a seeded pseudorandom K→M operator, and print

  y = sign(Φx)  (one printed cell per measurement, M cells across the volume).

Every cell now depends on *all* payload bits — CDMA-like superposition, the closest binary analog of a true volume hologram. Any subset of cells is a valid measurement set; recovery is Bayesian inversion (message passing / AMP) given the seeded Φ. Degradation is perfectly smooth, structure is absent at every scale by construction, and there is no tile granularity.

One honest correction to the framing first: **the physical and sync layers do not collapse.** Individual 1200-dpi dots are still unreliable channel uses, so measurements still ride on ≥2×2- or 3×3-dot cells (§4); and each surviving cell is only useful if its *index* into Φ is known, so absolute addressing is still required. Pure y = sign(Φx) is self-obscuring — you cannot correlate against a known sequence because y depends on the unknown x. Fix: the same pilot lattice as §5.2 — single-layer never had a pilot-free option, since v0.2's keystream-correlation idea fails here for the identical reason; or fold warp and offset into the decoder as latent variables (research variant N2 below). Single-layer, properly stated, replaces the *coding* stack (Layers 3–4 and the scrambler), not the physics.

### 10.2 Theoretical constraints — what "maximal" means here

Fix the volume: M usable cells, per-cell soft print–scan capacity C_cell (binary-input; realistically 0.6–0.9 depending on profile). Constraints, from loose to tight:

1. **Counting:** net rate ≤ 1 bit/cell, so K ≤ M·C_cell regardless of scheme.
2. **Fragment law (R2):** decoding from any fraction f requires K ≤ f·M·C_cell·α⁻¹, where α ≥ 1 is the measurement overhead of the construction. This is the same bound the layered stack lives under, with (inner rate R) playing α⁻¹'s role.
3. **The superposition tax.** For dense i.i.d. Φ with sign output and binary x — the teacher–student binary perceptron / 1-bit GLM — the sharp asymptotics (Barbier–Krzakala–Macris–Miolane–Zdeborová, PNAS 2019) put the information-theoretic recovery threshold at **α_IT ≈ 1.25** measurements per payload bit (noiseless), i.e. a provable ≈20% rate penalty below the counting bound, and the AMP algorithmic threshold at **α_alg ≈ 1.49** (≈33% penalty) — with a conjectured hard phase between them (the solution space is frozen-1RSB: valid solutions are isolated singletons, which is exactly why local search dies). The low-SNR limit of the same tax is the classic 1-bit quantization factor 2/π ≈ 0.64. Noise moves both thresholds up.
4. **Spatial coupling** provably closes the algorithmic gap for such ensembles (threshold saturation: Kudekar–Richardson–Urbanke; Donoho–Javanmard–Montanari for compressed sensing): a coupled measurement design decodes at ≈α_IT with message passing.

**Consequence:** even an *optimal* single-layer dense construction nets K ≈ f·M·C_cell/1.25, while the layered stack nets f·M·C_cell·(R/C_cell) with modern LDPC sitting a few percent below capacity — i.e. **the layered design strictly dominates on rate; single-layer's elegance costs 20–33%.** What single-layer buys is qualitative: zero tile granularity (grain shrinks to the ~2×2 mm sync minimum), perfectly smooth degradation, and one code instead of four layers. What it risks is also qualitative: a *global* threshold — below f, the layered design still returns every file whose symbols survived; the single-layer design returns **nothing**. For an archive, that failure mode is the strongest argument against it.

The clean statement is a trilemma: **capacity, cell-level grainlessness, tractable decoding — pick two.** The layered stack picks capacity + tractability and pays with grain (the inner tile). Dense projections pick grainlessness + tractability and pay the α tax — or grainlessness + capacity, if the α_IT–α_alg hard phase ever falls. Sparse spatially-coupled constructions recover capacity + tractability exactly by reintroducing locality, i.e. by becoming the layered design with extra steps. Layer count is bookkeeping; the binding architectural choice is the density of the dependency structure between payload bits and printed cells.

### 10.3 Computational feasibility under a <$1000 budget

Assumptions: 200-page CMY volume at P-nom geometry ⇒ M ≈ 8.5×10⁹ cells; K ≈ 2.8×10⁹ payload bits (f = 0.5, α = 1.5); iterative decoders at ~100 iterations; rented H100-class GPU ≈ $2–3.5/h, sustained int8 throughput conservatively ~10¹⁵ op/s; Φ never stored — regenerated on the fly from a counter-mode PRNG (Philox/AES-CTR), which is what makes any of this memory-feasible.

| Variant | Operator | Per-iteration cost | Total (100 it.) | Wall clock / cost | Verdict |
|---|---|---|---|---|---|
| **S1** dense global | i.i.d. ±1, K×M | 2MK ≈ 4.8×10¹⁹ | ≈5×10²¹ | ~55 GPU-days ⇒ **$3–8k** | Over budget; also the α_alg regime |
| **S1′** dense per page, fountain across pages (hybrid **H1**) | K×M per page (M_p=4.3×10⁷, K_p=1.4×10⁷) | 1.2×10¹⁵/page | 2.4×10¹⁹ | ≈7–15 GPU-h ⇒ **$20–50** | Feasible; page-grain reappears at the top level only |
| **S2** fast-transform global | subsampled randomized Hadamard/Fourier (SRHT), random signs | O(M log M) ≈ 3×10¹¹ | ~10¹⁴ | **minutes, <$5**; memory ~20–50 GB (fits one 80 GB GPU or shards) | **Feasible and the practical winner** |
| **S3** sparse graph, d≈32 | LDGM-like, GAMP | 2dM ≈ 5×10¹¹ | ~10¹⁴ | minutes, <$5 | Feasible; converges toward… the layered design (density of Φ is a knob interpolating the two architectures) |
| **S4** spatially-coupled S3 | SC-LDGM / SC-CS | ~1.5× S3 | ~1.5×10¹⁴ | minutes, <$5 | Feasible; the theory-optimal α |

Overheads that multiply the above: joint warp-EM outer loops (×10–30) and turbo channel-estimation passes — S2/S3/S4 stay under ~$100 with them; S1′ becomes $200–800, borderline. Bit-sliced XNOR–popcount kernels (binary matmul at ~5–20× int8 throughput) pull dense-global to ~$1–3k: still the wrong tool when S2 exists.

**Revised claim from the earlier discussion:** "decoding is expensive" is true only for *dense unstructured* Φ at volume scale. With structured operators, single-layer decoding of a whole archive costs single-digit dollars; **compute is not the binding constraint — information theory and the all-or-nothing risk are.** The $1000 budget is comfortably sufficient for every variant worth building.

Caveat for S2: the exchangeability argument ("any subset of rows is a good measurement set") is clean for i.i.d. Φ; for SRHT it holds w.h.p. for random subsets, and adversarially-shaped contiguous erasures (a burned corner = a structured row deletion) need either the random pre-permutation of cell↔measurement assignment (cheap, seed-derived — do this) or empirical validation. This is a real, testable gap, not a hand-wave.

### 10.4 Novel / to-be-found algorithms worth pursuing

**N1 — 2-D spatially-coupled GAMP over page geometry.** Coupling chains are 1-D in the literature; a 2-D coupling pattern whose decoding wave can nucleate from an *arbitrary-shaped* surviving fragment (boundary conditions set by damage, not by design) appears open and is exactly what this medium wants.

**N2 — Sync-free decoding.** Treat the warp field as a latent smooth function and infer (warp, x) jointly — variational EM with a differentiable resampler inside the message-passing loop. Kills the pilot puncturing and the last vestige of structure.

**N3 — Learned print-channel detector.** An unrolled equalizer–decoder trained on real printer/scanner pairs (the channel is stable per device); +1–2 dB here is +10–20% density everywhere. The payload is incompressible so learning helps the *channel*, never the source — no hallucination risk by construction.

**N4 — Progressive holography (multiresolution measurement design).** Structure Φ so measurement density is stratified across a wavelet decomposition of (lossy-tolerant) payload: any fragment then yields the *whole* archive at reduced fidelity, refining as area accumulates — the literal behavior of an optical hologram fragment, which no digital paper scheme currently exhibits. For mixed archives (photos + exact files), combine with L0/L1 exact strata. To my knowledge unpublished as a paper-storage design; the ingredients (multiresolution CS, unequal-error-protection fountain layers) all exist.

**N5 — Decimation/survey-propagation decoders for the frozen phase**, targeting α between 1.25 and 1.49 for dense constructions — closing the computational-statistical gap here is a publishable result independent of paper.

**N6 — Binary-matmul decode kernels** (XNOR–popcount tensorization) as the enabling systems work if S1-class constructions are ever preferred.

### 10.5 Verdict

Default remains the **layered stack (§§3–9)**: it dominates on net rate, degrades per-file rather than all-or-nothing, and its decode cost is negligible (<$5 of compute for a full ream — the FFT sync and LDPC passes are ~10¹²–10¹³ ops total). Build **S2 with random cell-permutation** as the experimental single-layer track (it is nearly free to implement once Layers 0–2 exist, since it reuses them), and pursue **H1** and **N4** as the two ideas with genuine architectural upside.

---

## 11. Recommendations

1. Characterize the actual engine first **by printing and analyzing a CAL-1 sheet (§9.1)**: native grid, dot gain, plane misregistration, per-paint-path fidelity (§2.4), MIC pattern; everything downstream is parameterized by its ChannelParams. Scan with the page's process direction on the CCD axis where the format allows, and never mix scanner color modes for absolute scale (§3).
2. Media: ISO 9706 or 11108, OBA-free, ≥100 g/m² if duplexing; dark storage ≤21 °C, 30–50% RH.
3. Ship profile **P-nom** (CMY, 3×3 cells, per-plane LDPC rates 0.75/0.75/0.60, RaptorQ with L0/L1/L2 strata at f = 0.02/0.3/0.7); keep **P-cons** (K-only) for century-critical material.
4. Implement decode as: lattice-FFT warp → PN acquisition → density unmix → turbo EQ+LDPC → RaptorQ; budget: laptop-class.
5. Prototype S2 single-layer on one page-pair before believing any of §10's constants for your hardware; measure C_cell empirically and re-derive the tables.
6. Treat the human-readable bootstrap pages as part of the format, not documentation.

## 12. References (informal)

Ashley et al., "Holographic data storage," IBM J. R&D 44(3), 2000 (modulation codes for page-oriented optical memories). RFC 6330 (RaptorQ). Barbier, Krzakala, Macris, Miolane, Zdeborová, "Optimal errors and phase transitions in high-dimensional generalized linear models," PNAS 116(12), 2019 (α_IT ≈ 1.25, α_AMP ≈ 1.49 for the sign/binary GLM). Krauth & Mézard, J. Phys. France 50 (1989) (binary perceptron capacity). Kudekar, Richardson, Urbanke, IEEE T-IT 2011 (threshold saturation); Donoho, Javanmard, Montanari, IEEE T-IT 2013 (SC compressed sensing). Aubin, Perkins, Zdeborová / Perkins & Xu, 2019–2021 (frozen-1RSB structure of the symmetric binary perceptron). Van Vleck & Middleton (1-bit correlator, the 2/π law). EFF, "Machine Identification Code" documentation. ISO 9706, ISO 11108 (permanent/archival paper). Twibright Optar; PaperBack (prior art baselines). MacWilliams & Sloane, "Pseudo-random sequences and arrays," Proc. IEEE 64(12), 1976. Paterson, "Perfect maps," IEEE T-IT 40(3), 1994; Etzion, de Bruijn tori constructions. Anoto position-coding pattern (a window-property code in production). Imad & Houcke, blind frame synchronization via sparse parity-check codes, IEEE Trans. Commun., 2009.

*Numerical constants marked ≈ are design-stage estimates from the cited asymptotics or typical hardware; §11.5's measurement step supersedes all of them.*
