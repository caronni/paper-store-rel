# e026 DESIGN-NOTES — the 2026-07-18 encoding-geometry session

Discussion record: questions, reasoning, measurements, REVERSALS, and the
open state. **No format change shipped** — everything here is candidate
material for one bundled layout_version bump (natural vehicle: whatever
bump the 018b rate re-freeze forces). Compressed decision record:
docs/REASONING-LOG.md "Session 2026-07-18" + Addenda 1–5. Probe numbers:
../026-pilot-density-subsample.md (+ build/e026_report{,_c3}.json,
scratch/e026-grain-vs-density{,-c3}.png). This file exists so a later
session can resume the design work without replaying the conversation.

---

## 1. How the session ran (chronology — the churn is the content)

1. User: are pilots⊥LDPC and the no-data border the right choices?
   Proposals: (a) center the payload so the border is 4-sided; (b) split
   fountain symbols across border tiles.
2. User correction: "aligning pilot/payload" meant equal TILE SIZES
   (60 vs 64), not embedding pilots in codewords.
3. Descriptor placement: my border-tile idea → user's pilot-PAD-BIT idea
   (border tiles are the worst-exposed real estate; accepted).
4. User: align sizes, or keep disjoint so straddles "help each other"?
   → straddle coupling shown illusory at codeword granularity.
5. User: from physics, what is the OPTIMAL pilot size/density?
   ("60×60/100 is entirely arbitrary") → analysis collapsed the two knobs
   to one; the unmeasured input was grain(δ).
6. User: "try." → e026 built + run same day (c2), then 026.1 review
   corrections + c3 replication arm after user challenge.
7. User consolidation attempts exposed stale intermediate conclusions
   (centering) and my page-fill blindness (caught TWICE).
8. User: 64×64 colocation to keep the healthy 4096 code? published code
   lengths? → REVERSAL: pilots move, mother code stays.
9. User: 32×32 everything, from scratch, "old pilots never come back"
   → the wordless design space opened (32-site tiles CANNOT word).
10. User: hybrid 32-pilot/64-payload → analysis initially endorsed.
11. User brake: "what does 32 buy vs 64 at the pilot layer?" → my hybrid
    benefits exposed as density-in-disguise → collapse to a SINGLE
    64-grid and exactly ONE remaining binary (words vs wordless).
12. This document.

---

## 2. Measured findings of the session

### 2.1 The e026 probe (zero print; full numbers in the experiment log)

- **Placement quality is a function of pilot-sites-in-fragment alone**;
  all (size × density × profile) conditions collapse onto one curve.
  Transition bands (pass-down-to / highest-failure-at, pooled):
  c2 argmax 23/35, session gap gate 29/56, frozen §15.4 gate 61/92;
  c3 argmax 21/32, session 25/54, frozen 55/115.
- The pre-registered 140–150-site constant was a MARGIN artifact
  (MIN_WIN_CORE, 016.7 headroom), not the transition.
- **Identifiability bound fits both arms**: blind placement selects among
  ~2^23.7 pose hypotheses ⇒ needs ≳ 24/(1−h(BER)) sites ≈ 29 (c3,
  ~2–3% cell BER) / ~35 (c2, ~5–8%). The argmax floor IS this bound;
  the session gate sits ~2× it, the frozen gate ~3–4× (rival-bar
  starvation, not correlation SNR).
- Floors follow floor_mm = sqrt(sites_needed/δ)·pitch at every measured
  point. c2 frozen floors 5/5–6/6/8/8–10 mm and session ≤4/5/5/6/6 mm at
  δ = 2.78/2.22/1.78/1.22/1.00%; c3 at 2.78%: session 6 mm / frozen 8 mm
  (pre-registered prediction exact).
- **Safety**: 0 false placements in all 1,680 windows with ≥14 sites;
  the frozen gate had 0 false EVERYWHERE. ONE false placement total:
  a 3-site degenerate window (c3, 4 mm, δ=1.0%) admitted by the SESSION
  gap gate (mism 0.05, rival 0.19, gap 0.14) — the frozen rival bar
  refused it. Wrong-seed nulls reach mismatch 0.000 below ~24 bits of
  evidence: perfect decoys exist by counting.
  **Consequence (mandatory, decoder-axis, independent of any format
  decision): a hard fragment-support floor ≥ ~30–35 sites must precede
  the mismatch/gap logic. place_fragment's min_support gates the
  candidate OFFSET's support, not the fragment's own site count.**
- Probe conservatisms (both safe-direction): random thinning is clumpier
  than a real quota lattice; the probe's period-slip decoys are
  full-strength while a real thin format's dilute toward 0.5.
- Scope limits: placement axis only (enclosing ctx bits at full density;
  acquisition/calibration unthinned); clustered windows (8 locks c2 /
  6 locks c3, POS mostly one fy band); one sheet+engine per profile;
  densities above 2.78% unprobeable by subsampling.

### 2.2 The page-fill audit (user-caught, twice missed by me)

Measured printable margin ≤4 mm (007.6, ticks, all edges, BOTH engines —
lowest PROBED, not a cliff). CONTENT_MARGIN_MM = 6.0 is a round "stricter
than measured" constant never revisited. Current fields sit inside even
that: e012/c3 field 281.94×190.50 mm = margins 7.54/9.74 mm (it is the
6.0-max only because the next 60-cell x-rung, 198.12 mm, needs 5.94 mm —
blocked by 0.06 mm); e014–e016/c2 field 279.40×187.96 mm = margins
8.81/11.01 mm, NOT even the 6.0-max (3360×2280 legal today = +4.6%).
Maxima: c3@5.9 mm: 2220×1560 (+4.0%); c2@5.9: 3360×2340 (+7.3%).
At 64-cell field quantum (the converged grid): c3 2240×1536 (+3.3%);
c2@5.9 3328×2304 (+4.7%); c2@4.9 3392×2368 (+9.6%, needs the margin
probe). The next c3 y-rung needs 3.72 mm < the measured floor — a
zero-cost margin-ladder strip on any future print probes 3–3.5 mm.
This was the largest single capacity item found all session.

### 2.3 As-built facts confirmed by reading the code

- Edge/partial data tiles are LDPC-encoded scrambled ZEROS: printed,
  certifiable, fountain-inert; cost at r0700 = 2.33% (edge capacity)
  + 0.26% (interior S=min pad). They form an ACCIDENTAL 2-sided guard
  band (right/bottom only) at identical ink statistics.
- v2/v3 pilot lattice: exact 1/36, period 60; fields must be multiples
  of 60 (compose validation) — pilot tiles never clip; only DATA tiles
  (64) do.
- The 5 pilot pad bits are enforced zero at decode = a deliberate 2^-5
  FA gate (pilots.py:272).
- Capacity per tile depends on the shorten COUNT only, not positions
  (ldpc.tile_user_capacity) — count-uniform quotas ⇒ uniform S with no
  min-tax, regardless of where sites sit.

---

## 3. Derived findings (arithmetic/structure; no measurement needed)

- **Pilots⊥payload at encode is provably ~free**: embedding pilots as
  known-value codeword bits ≡ shortening (affine shift, ∞-LLR nodes);
  zero capacity either way. The only different design — data-dependent
  pilot values — destroys a-priori predictability, which acquisition
  and placement stand on (settled; do not reopen). Decode-side coupling
  is where value lives and is already harvested (PAVA labels, E024).
- **Straddles do not help**: pilot information is site-granular and
  seed-derivable post-placement ("word decode adds no labels" — E023
  record); geometry is window-granular; bch_ok is regionally
  aggregated. No codeword-granular coupling channel exists for grid
  phase to exploit.
- **Symbol-spanning across border tiles: rejected** (AND-coupled
  erasures across the most damage-exposed, page-distant tiles +
  cross-tile certificate provenance). The clean harvest, if ever
  wanted, is truncated/"ragged" symbols: fountain-v1 is bitwise-parallel
  GF(2), so an edge tile can contribute the first c bits of its OWN
  symbol; decode = per-column-class rank; certificates stay tile-local.
  (Obsoleted by the converged no-partial-tiles geometry, kept for the
  record.)
- **The word code pins ~100 sites**: (127,50,t=13)→(100,23) cannot
  shorten much further (127→81 leaves k=4). 64-site words fail:
  BCH(63,24,t=7,d=15) ⇒ ~12–15% word-fail at the 8% c2 budget + halved
  decoy floor + erasure budget 2e+f≤14. With words, the square-quota
  construction needs (P/B)²=100 ⇒ P ∈ {60,70,80,90,100} ("P=67/75" in
  the first e026 report are idealized labels — non-constructible).
- **Density is decoupled from BOTH the word question and the quota
  scale**: v4 dust is the precedent for plain keystream label sites
  alongside word sites (100+28 = 2.73%, 100+56 = 3.8%, …); and at equal
  density, quota scale 32 vs 64 changes only worst-case fragment
  site-count concentration (~2–3% in mm, hypergeometric) — the
  phase-enumeration argument is moot in a correlation receiver (the
  FFT scores all offsets at once).
- **Pad-bit descriptor arithmetic** (C1): sacrifice ONE pad (keep 4 ⇒
  2^-4 cold-start gate); bit index = counter mod D; the 2^18 counter
  already caps volumes at ~2^26 bytes ⇒ data_len_bytes fits 26–28 bits;
  core descriptor ≈ 40–44 bits incl. CRC ⇒ ~20 (c3) / ~45 (c2)
  word-certified copies per page at 1 bit/word. Warm regime: the whole
  23-bit message is predictable post-placement (known-position
  machinery), so the check RECOVERS and exceeds 2^-5; cross-word
  consistency (equal counters mod D must agree) retro-checks cold
  accepts. Format version needs no bits (scramble-label identity;
  un-bootstrappable in-band anyway); rate stays registry-pinned until
  mixed-rate volumes exist (then: per-page rung echo).
- **Block length**: 3500 vs 4096 ≈ 0.05–0.1 dB finite-length delta =
  noise vs channel day-variance. The value of n=4096 is its MEASUREMENT
  RECORD (ladder, cliffs, yields), not the number. Small tiles pay real
  fixed costs: at 32² (n=992, k=543) CRC-32 = 5.9% of k vs 1.5% at 64²,
  plus waterfall pull-in (est. 2–4 BER points, would need measuring)
  and trapping-set risk — against certify-alone grain 4.1/2.7 mm and a
  ~halved e015 fragment-boundary tax. Judged past the knee.
- **Published code lengths** (calibration; none fit our geometry):
  802.11n 648/1296/1944; WiMAX 576–2304; 10GBASE-T 2048(k=1723);
  DOCSIS 3.1 1120/5940/16200; CCSDS 8160 + AR4JA k=1024/4096/16384;
  DVB-S2 16200/64800; 5G NR any-n via lifting (Z≈88 lands near 3.5k but
  imports base graphs + rate matching). The one serious argument for a
  standard code is deep-time public documentation (BOOTSTRAP kernel),
  traded against tile=codeword=word=symbol unification. House e-IRA +
  golden/printable-spec discipline stands.
- **S arithmetic** at 64-grid (r0550, k=2240): today variable ~114-site
  shorten, S=2090 (c3) / 2087 (c2); uniform 100 sites ⇒ S=2108; uniform
  128 sites ⇒ S=2080. (REASONING-LOG Addendum 2 says "~2154" — that is
  an arithmetic slip; correct is 2108.)

---

## 4. Reversals and corrections (the thought-process record)

R1. **Centering the tile grid** (my endorsement) → OBSOLETED by
    alignment: on an aligned grid there are no partial tiles, hence no
    border to distribute. Died in consolidation; briefly survived as a
    stale item in my own summary.
R2. **"Align by moving the data tile to 60, never the pilots"** →
    REVERSED (user: keep the healthy 4096): uniform-100 shortening of
    the UNCHANGED mother code sits inside the already-measured regime;
    a new n=3500 e-IRA is a new-construction risk class (the 013
    falsified-textbook lesson) + full ladder re-anchor. Stage-0
    convenience was over-weighted (compute + FA re-arithmetic, not
    re-measurement).
R3. **"P=75 is free"** → non-constructible under the square quota
    (P=10B); verdict restated on real rungs {70,80,90}.
R4. **Pre-registered 140–150 sites** → measured ~92/56/35 (margin
    artifact vs transition).
R5. **Descriptor in border tiles** (mine) → pilot pad bits (user):
    border = worst-exposed real estate; pads ride the best-protected,
    most-dispersed channel at zero new cells.
R6. **Hybrid 32-pilot/64-payload "granularity benefits"** → density
    benefits mislabeled (user brake); at equal density the quota scale
    is second-order ⇒ single 64-grid.
R7. **Page-fill blindness** (mine, twice): the field never filled the
    printable envelope; +3.3–9.6 pp sitting in inherited field dims and
    a round margin constant.
R8. **"e026 verdict transfers to c3 by argument"** → replaced by
    measurement (026.1) after user challenge; transfer confirmed, with
    the BER-shift the identifiability bound predicts, plus the false-
    placement discovery the c2 arm alone would have missed.

Meta-lesson (user went 4-for-4): δ=2.78%, the 64-cell tile, the field
dims, and the 6.0 mm margin were all INHERITED constants that survived
because nobody re-derived them. When a constant's justification is "it
was chosen early," audit it — the audit either re-derives it (60→still
best as tile grid quantum? no: 64 won) or finds free capacity.

---

## 5. The converged bundle (invariant to the open binary)

ONE grid: 64×64 tiles for pilot quota AND payload. n=4096 mother code +
rate ladder FROZEN (uniform shortening by the exact per-tile site
count). Fields = largest multiples of 64 inside margins DERIVED from
measurement (5.9 mm policy now; margin-ladder probe may buy ~4.9 mm).
No partial tiles by construction. Density = free dial (e026-priced;
words don't pin it — filler label sites per the dust precedent).
Descriptor: pad bits (C1) or descriptor sites (C2). Stacked capacity vs
today ≈ +5–7 pp (c3) / +6–12 pp (c2): border reclaim +2.3–2.6, page-fill
+3.3–9.6 (policy-dependent), pilot-density delta −0.35…0, S-uniformity
~+0.3. All format-axis ⇒ ONE layout_version bump riding the 018b rate
re-freeze; legacy formats stay decodable via the registry.

## 6. The ONE open decision: C1 (words kept) vs C2 (wordless)

**C1**: (127,50)→(100,23) word per tile + filler sites as the density
dial. Keeps O(1) cold-start page-ID from any tile, descriptor-in-pads,
certifiable partial reads (2e+f≤26), d≥27 as the blind format-ID
arbiter, pencil-and-paper bootstrap of a tile, and the measured word
subsystem. New build: exact-100 site construction at period 64 (square
quota fails at 64 — that is the v1 stripe bug's origin; use a seeded
exact-count/blue-noise construction).

**C2**: pure position-keyed keystream values, correlation-only
addressing (cold start O(pages); E023c coarse-first cascade is the
right shape), descriptor-site class, gates re-derived from chance-only
decoy statistics + the hard support floor, one-evidence-type receiver
(word path + straddle audits + 018.9-class pathologies deleted), no
2^18 counter cap. New build: the §15.8-completing receiver + FA
derivations + 8-hypothesis (mirror×rot90) arbitration.

Capacity ≈ equal at fixed density. Decision deliberately NOT taken
(user: "let's not be too hasty"). My recorded lean: C1 default
(preserves the most measured machinery + the elegant descriptor), C2
as the documented clean-sheet alternative. The PILOTS-v2 design note
should carry both as one-page candidates; nothing else in the bundle
depends on the choice.

## 7. Ambiguities and open items

- **Grain requirements undecided**: no product-level statement of what
  confetti sizes the format PROMISES. Word grain (2P), certify-alone
  grain (tile), placement grain (density) are now all separately
  priced — but the target is policy, not physics. Needed before any
  density/quota freeze.
- **4 mm scraps**: c2 = a GATE problem (62 sites; session-solid in
  measurement; needs the support-conditional bar + hard floor, zero
  format cost). c3 = physics at 2.78% (27 sites < identifiability);
  paths = density ≥ ~5.6% (steep), profile switch to c2 (dominates), or
  certified-field sliver placement (§7.2 feedback edge, designed
  unbuilt — the real endgame lever; placed scraps below tile size
  contribute via cross-scrap assembly only).
- **Owed validations before ANY density/lattice change**: E022's
  49-null / 784-hypothesis battery re-run thinned; second-sheet/engine
  replication of e026 (one sheet per profile so far); the c3 frozen-gate
  band (~55/115 vs c2's 61/92) has an unexplained cluster-confounded
  residual (3 refusals at 108+ sites in two conditions).
- **e026 scope holes**: acquisition + calibration axes never thinned
  (enclosing locks at full density); real-scrap composition (rotation,
  torn edges, own-lock) not re-measured vs density — relative scaling
  assumed to transfer.
- **Margin-ladder probe** (<4 mm) — zero-cost rider on any future
  print; unlocks the next y-rung (c3 +2.7% more) and the c2@4.9 fill.
- **CRC-24 vs 32 attempt-budget arithmetic** — only if small tiles are
  ever revisited.
- **e015-style boundary-yield-vs-tile-size sweep** — quantifies what
  the 64-tile choice forgoes under fragmentation; run if
  grain-under-damage becomes a requirement.
- **COLOR (v4) never considered this session**: dust, per-level words
  (W vs CM), MLC symbol streams all interact with any pilot redesign;
  the PILOTS-v2 note must re-derive the v4 story explicitly.
- **Multi-lattice registry cost**: any new sites label means unknown
  scraps try two lattices (word-gated in C1; gate-statistics in C2) —
  bounded, but must be built and FA-budgeted.
- **Bootstrap ladder update** (BOOTSTRAP-DESIGN) needed under either
  candidate; C2 loses hand-decodable addresses (keystream reference
  was already the pinned dependency).
- **Descriptor content list** still provisional: data_len_bytes + CRC
  core; SHA tier optional; per-page rung echo only if mixed-rate
  volumes materialize.

## 8. Pointers

- docs/REASONING-LOG.md "Session 2026-07-18" + Addenda 1–5 (compressed;
  Addendum 2's S≈2154 corrected here to 2108).
- ../026-pilot-density-subsample.md (probe pre-registration, RESULTS,
  026.1) + build/e026_report{,_c3}.json + probe_e026.py (--c3, --quick)
  + scratch/e026-grain-vs-density{,-c3}.png.
- Measured anchors leaned on: 007.6 (margins), 016.3 (edge gradient =
  registration + ~0.2% dev residual), 014.5/016.7 (placement floors,
  gate provenance), e015 (f* = boundary yield), 017 P3 (0.25% dust
  label-sufficiency), 012.3/E023 (GT/truth-path + "word decode adds no
  labels"), pilots.py:272 (pad gate), fountain.py docstring (edge-tile
  mechanics).

---

## 9. 026.2 external-review corrections (2026-07-19) — READ WITH THE ABOVE

An external review was verified claim-by-claim (code + reports); every
checkable claim held. The authoritative correction list is
../026-pilot-density-subsample.md §026.2; headline deltas to THIS file:

- §2.1's false-placement paragraph: the "session gate" that admitted the
  3-site window was the probe's RELAXED gap-only variant; the real 016
  session gate (three-condition: best<0.20, rival>0.20, gap≥0.08, plus a
  ≥60-site refine floor) refuses it. No production gate failed. Counts:
  1,626 (not 1,680) windows ≥14 sites. Support gates are to be DERIVED
  from the declared attempt budget (search + held-out validation
  support), per stage; identifiability scales with the attempt space
  (1-page c2 ~2^24.8; ~128-page mirrored c2 ~2^32.8 → ~46-55 sites).
- §3/§6: the PAD-BIT DESCRIPTOR IS RETRACTED — measured: one pad flip
  changes 39-40/100 transmitted bits (systematic parity spread), which
  destroys the cold-field predictability C1's placement lives on. Pads
  stay zero; descriptor home = dedicated sparse filler-site class
  (excluded from cold correlation) or the bootstrap preface; volume
  binding (SHA/id) is MANDATORY for fixed-public-key profiles.
- §3 density slip: 100+28 = 3.125% (2.73% = 112 sites). And the C1/C2
  binary COUPLES to the density range (C1 word-per-tile floor 2.44%) —
  "everything else invariant" was overstated.
- §2.2 margins: base 64-quantum fields fit the EXISTING 6.0 mm policy
  (c3 6.26/7.46, c2 7.61/7.46) — the base +3.3/+4.7% needs no policy
  change; 3392×2368 needs ~4.75 mm; the "3.72 mm next y-rung" was the
  60-quantum figure (64-quantum rungs need 2.20/3.40 mm). All extent
  growth is additionally gated on E025-style payload-safe edge canaries
  (unresolved even at current extents) and distinct from the BOOTSTRAP
  archival trim policy.
- §5: "converged bundle" → LEADING-CANDIDATE bundle. §7's owed list is
  superseded by the adopted 8-item pre-freeze qualification plan
  (../026-pilot-density-subsample.md §026.2 item 12), which adds: a
  normative exact-100 P64 mask battery (thinning one P60 pattern
  qualifies no particular construction — v1's stripes are the
  precedent), correlated-raster replay through the now tile-invariant
  slot→codeword mapping (count-only capacity ≠ count-only BLER), and
  the LAYERS-vs-FEC rate/layout_version governance reconciliation.
