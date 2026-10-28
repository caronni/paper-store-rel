# Experiment 026 — pilot-density subsample probe (zero print)

Date opened: 2026-07-18. Decoder-axis, zero print, no format change.
**Design-session record** (the full 2026-07-18 encoding-geometry
discussion this probe served: questions, reversals R1–R8, converged
bundle, the open C1/C2 words-vs-wordless binary, ambiguities):
026-pilot-density-subsample/DESIGN-NOTES.md.
Driver: `experiments/026-pilot-density-subsample/probe_e026.py`
(run from repo root: `env/bin/python experiments/026-pilot-density-subsample/probe_e026.py [--quick]`).

## Question

The pilot design collapsed to one knob (session 2026-07-18 discussion): with
the word size N_w ≈ 100 forced by {23-bit message, d>=27, worst-footing BER},
density and period are locked as δ = N_w/P². The capacity axis is flat
(45→90 spans ~6 pp); the grain axis should pick the operating point — and the
grain(δ) curve has NEVER been measured. This probe measures the downward half
(δ < 2.78%) for free by **subsampling the predicted pilot field in software**
and re-running the measured F13 placement harness on the real e014 Canon
scans. If the placement floor survives thinning better than the site-count
model predicts, P=75 (δ=1.78%) is a free-capacity candidate; if it degrades
on schedule, P=60 is confirmed as chosen rather than inherited.

## Method

- Substrate: `scans/xerox-e014-A-canon-4800gray-C-flattened.tiff` (5 window
  positions) + `-B-displaced.tiff` (3 positions) — the exact 014.5 harness
  (enclosing 25 mm blind lock → ctx hard bits → carved sub-windows with
  construction-known absolute origins → `place.place_fragment` against the
  full page, all 4 rotations, frozen §15.4 gates 0.15/0.20; session gap gate
  0.20/gap 0.08 reported alongside).
- Thinning: wrap `place.pilot_field` (probe-side monkeypatch, src untouched);
  keep site (y,x) iff blake2b(b"e026/keep"+y+x)/2^64 < f. Per-site,
  position-keyed, order-independent, **nested** across fractions (smaller f
  ⊂ larger f). Faithful for placement: dropped sites are simply not
  consulted; at wrong offsets consulted cells have the same scrambled
  Bernoulli(~0.5) marginals whether the printed cell is pilot or payload.
- Grid: sizes {4, 5, 6, 8, 10, 12} mm × fractions f ∈ {1.00, 0.80, 0.64,
  0.44, 0.36} = δ' {2.78, 2.22, 1.78, 1.22, 1.00}% = P-equivalent
  {60, 67, 75, 90, 100}; 4 sub-windows (2×2) per lock per size → up to 32
  windows/condition. ctx detector only (production path).
- Per window recorded: thinned sites in window, correct (exact origin+rot),
  near (≤1 cell slip), frozen-gate PASS, session-gate PASS, mismatch, rival,
  z_gap. Nulls: wrong-seed at f=0.36 (6 and 10 mm) must refuse.

### Scope limits (stated up front)

This measures the **correlation-placement** floor vs δ only. Word grain vs P
is arithmetic (N_w fixed, not probed). Calibration-label sufficiency at low δ
is not probed here (ctx bits come from full-density enclosing context); the
017 P3 dust measurement (0.25% label-sufficient) covers that axis. Densities
ABOVE 2.78% cannot be probed by subsampling (would need sim/print) and are
dominated per the analysis (c2 profile is the cheaper grain lever).

## Pre-registered expectations (written before first run)

1. **Control (f=1.00) must reproduce 014.5/016.7**: 4 mm refused, 5 mm
   partial, ≥6 mm solid correct+gated. A failing control = broken harness
   (gate-constants-vs-floors rule), stop and fix before reading any thinned
   row.
2. **Zero false placements** (gated AND >1-cell wrong) at every condition.
   Any false = headline finding: the frozen gates are not
   support-conditional (known E022 open item), and the P-sweep verdict is
   then gated on fixing that first.
3. **Site-count law**: the solid floor scales ~1/√f from 6.2 mm; i.e.
   f=0.64 → ~7.5 mm (6 mm degrades, 8 mm holds), f=0.44 → ~9 mm, f=0.36 →
   ~10 mm. Equivalent invariant form: correct+gated turns on at a roughly
   constant sites-in-window threshold (~140-150) across all (size, f) pairs.
4. If 6 mm instead SURVIVES solid at f=0.64, the model is pessimistic and
   P=75 is free on the placement axis (word-grain arithmetic then decides).

## RESULTS (2026-07-18, full sweep: 8/8 locks, 32 windows/condition,
960 place calls, 748 s; report build/e026_report.json, figure
scratch/e026-grain-vs-density.png)

**Control reproduces (pre-reg 1 PASS).** f=1.00: argmax exact 32/32 at
EVERY size 4-12 mm; frozen §15.4 gate passes 5 mm+ 32/32 and refuses all
4 mm — exactly the 014.5 record (gated floor 5 mm, 4 mm honest refusal).

**Zero false placements (pre-reg 2 PASS).** Across all 960 windows ×
{frozen, session} gates: every single admission was exact-origin/rot
(admitted-but-not-exact = 0; not even 1-cell slips). Wrong-seed nulls at
δ=1.00% refuse under BOTH gates at 5/6/8/10 mm, wrong-region pending null
refuses. Mechanism note: at ≤34 sites a wrong-seed decoy reaches best
mismatch 0.095 — BELOW gate_true 0.15 — so at low support the RIVAL/GAP
bar is the load-bearing FA defense (session gaps on nulls 0.001-0.023,
all << 0.08). The frozen 0.20 rival bar refuses toward safety, never
toward false accept, as designed.

**Site-count law: form CONFIRMED, constant REFUTED downward (pre-reg 3
half-wrong, pre-reg 4 branch FIRED).** Pooled over all (size, density)
pairs the outcomes collapse on sites-in-window with sharp transitions:

- argmax-correct:   solid above ~35 sites (passes observed down to 23)
- session gap gate: solid above ~56 sites (passes down to 29)
- frozen §15.4 gate: solid above ~92 sites (passes down to 61)

The pre-registered 140-150 constant was a MARGIN artifact (MIN_WIN_CORE
8000 cells ≈ 222 sites; 016.7 quoted ~150 with headroom), not the
transition. With the measured constant, floor_mm = sqrt(sites/δ')·pitch
predicts every row: frozen-gate floors P-equiv 60/67/75/90/100 →
5/5-6/6/8/8-10 mm measured (6 mm at P~75: 31/32 frozen, 32/32 session;
6 mm at P~90: 32/32 session, 2/32 frozen; 8 mm at P~100: 27/32 frozen,
32/32 session). Session-gate floors: ≤4/5/5/6/6 mm.

**Verdict for the format question:** P=75 (δ=1.78%) is FREE on the
placement axis — the 6 mm c2 floor survives intact (and 5 mm still
admits 31/32 under the session gate). Even P=90 (δ=1.22%) keeps a 6 mm
session floor; its frozen-gate floor moves 5→8 mm only because the
frozen rival bar starves below ~100 sites — the known E022
support-conditional-bar open item, which the session gap gate already
mostly closes (0 false here). Confirmed-not-inherited status for P=60 is
therefore REVERSED: on this evidence the placement axis does not defend
δ=2.78%; P=60's remaining defenses are word grain (2P arithmetic: 25%
larger at 75) and Stage-A hypothesis count (P², compute only).

### Caveats / follow-ups before any density freeze

- Enclosing ctx bits came from full-density 25 mm locks (acquisition and
  calibration axes NOT thinned here; 017 P3 says labels suffice to
  ~0.25%, but the word/acquisition layer at lower δ is arithmetic +
  unmeasured).
- Null battery here is small (wrong-seed × 4 sizes + wrong-region × 1);
  E022's 49-null / 784-hypothesis adversarial battery must be re-run
  thinned before freezing any lower-δ format.
- n=32 windows/condition come from 8 lock clusters on 2 scans of ONE
  sheet/engine (AltaLink print, Canon scan) — same substrate limitation
  as 014.5; a second-sheet replication is cheap if the decision becomes
  live.
- Densities above 2.78% not probed (subsampling can't; dominated per the
  P-collapse analysis — c2 profile is the cheaper grain lever).

## 026.1 Review corrections + c3 replication arm (2026-07-18, same day)

Adversarial self-review after the first publication of RESULTS; three
corrections and one new measurement.

**(a) CONSTRUCTIBILITY CORRECTION — the P knob is quantized to P = 10·B.**
The frozen word code is exactly (127,50,t=13)->(100,23): 100 transmitted
sites is GLUED to the code (further shortening guts k: 127-81 leaves k=4),
and the quota lattice needs integer block size B with (P/B)^2 = 100 sites,
i.e. P/B = 10. Constructible rungs: P in {60, 70, 80, 90, 100, ...} =
δ {2.78, 2.04, 1.56, 1.23, 1.00}%. The report's "P~67" (f=0.80) and
"P~75" (f=0.64) are IDEALIZED labels — no such format exists. Restated
verdict on constructible rungs (c2, from the measured curve): **P=70
(f=0.735, bracketed by two clean measured fractions) — 6mm floor intact,
FREE (+~1.2pp with aligned n=4900 tiles); P=80 (f=0.5625) — 6mm
session-solid / frozen-marginal (+~1.9pp); P=90 (f=0.444, measured
directly) — 8mm frozen / 6mm session floor (+~2.5pp).**

**(b) Probe conservatisms (both run in the safe direction, now stated):**
(i) random per-site thinning is CLUMPIER than a real lower-δ blocked-quota
lattice — real formats would have lower per-scrap site-count variance, so
measured floors are slight over-estimates; (ii) at period-aligned slips the
probe's decoys are FULL-strength (the printed field is still dense; only
consultation is thinned) while a real thin format's period-slip decoys
dilute toward 0.5 by (1-f) — so the probe's rival field is harder than
reality and the 0-false result is extra credible; frozen-gate refusal
rates at low δ are correspondingly pessimistic.

**(c) Sample-structure caveats (now explicit):** 32 windows/condition come
from 8 lock clusters, POS_C all on one fy=0.3 band (the 014.5 inheritance);
the "solid above N sites" thresholds are order statistics on clustered
trials, not independent-Bernoulli CIs. Carved windows are axis-aligned,
unrotated, enclosing-lock bits — real scissors pieces (rotation, torn
edges, own-lock) sit above these floors in absolute terms (016.4 ladder);
the δ-RELATIVE scaling is what transfers.

**(d) c3 replication arm** (`--c3`: e012 intact-sheet Canon 4800 scan,
gen_e012 spec, CD=3, 6 locks × 4 sub-windows, same fractions/sizes).
Pre-registration (stated before the run, from the c2 collapse): the site
thresholds (argmax ~35 / session ~56 / frozen ~92) transfer in SITES;
c3's cleaner per-site evidence (lower cell BER) may lower them slightly;
mm floors then = 1.5× fewer cells/mm: predicted c3 P=60 floors ≈ 6mm
session / 8mm frozen. Quick-mode smoke (2 locks) landed every row on the
c2-derived prediction (44/62-site windows session-pass+frozen-refuse,
112-site frozen-pass, 72-site session-only, 28-site refused; argmax exact
even at 28 sites). Full-sweep RESULTS below.

### 026.1 c3 RESULTS (full sweep: 6/6 locks on e012 A @4800, 24
windows/condition, 720 placements, 247 s; build/e026_report_c3.json)

**The site-count law TRANSFERS across profiles** — pooled c3 transition
bands vs c2: argmax passes down to 21 sites / highest failure 32 (c2:
23/35 — c3 slightly LOWER, consistent with its cleaner per-cell BER);
session gate ~25/54 (c2: 29/56 — same band); frozen gate ~55/115 (c2:
61/92 — c3's band sits somewhat higher, rival-side, with the 3 refusals
at 108+ sites clustered in the f=0.44/0.36 12mm rows). Measured c3 mm
floors at P=60: **session 6 mm (24/24; 5 mm 20/24 partial), frozen 8 mm
(24/24; 6 mm 1/24)** — exactly the pre-registered prediction from c2
site thresholds. Constructible-rung translation (c3): P=70 ≈ session
6 mm near-solid / frozen 8-10 mm; P=90 session 8 mm / frozen 10-12 mm
marginal.

**Information-theoretic reading (post-hoc, fits both arms):** blind
placement must select among ~4 x page_cells ≈ 2^23.7 hypotheses, so
identifiability needs ≳ 24/(1-h(BER)) sites ≈ 29 (c3, ~2-3% cell BER) /
~35 (c2, ~5-8%) — the measured argmax transitions land on both numbers.
The session gate sits ~2x the bound (safety), the frozen gate ~3-4x
(rival starvation).

**FALSE PLACEMENT UNDER THE PROBE'S RELAXED GATE — degenerate-support
regime (CORRECTED per 026.2; the original "first false placement on
record / admitted by the session gate" claim was WRONG):** window
A(0.55,0.4), 4 mm, f=0.36, carrying **3 sites** after thinning; the
probe's gap-only gate (mism<0.20 AND gap≥0.08 — a relaxed variant I
constructed) admitted a chance placement elsewhere (mism 0.05, rival
0.19, gap 0.14). The ACTUAL production gates both refuse it: the frozen
§15.4 gate (rival 0.19 < 0.20) and the real 016 session gate, which is
THREE-condition — place_fragment ok at gate_true=0.20 AND
gate_decoy=0.20 (i.e. rival must EXCEED 0.20) AND gap≥0.08, plus a
≥60-site floor on the refine path (session_decode.py:106-113). No
existing receiver gate was shown to fail. The degenerate-support
lesson stands in weakened-but-real form: a wrong-seed null at ~22
sites reached mismatch 0.000 (perfect decoys exist by counting below
~24 bits of evidence), and gates must be support-aware BY DERIVATION,
not by the accident of the rival bar. Counts: **0 false among the
1,626 windows (of 1,680 total) with ≥14 sites** under every gate
variant; the single relaxed-gate false sat at 3 sites. The operational
form of the fix (026.2, review-sharpened): stage-specific minimum
SEARCH support + independent VALIDATION support derived from the
declared attempt budget (pages × formats × mirror × rot90 × offsets)
— not a blanket "fragment contains 35 sites" rule; note the probe
recorded true-origin support, not the winning candidate's, and the
receiver only knows the latter pre-placement.

## 026.2 External review (2026-07-19) — verified findings + corrections

An external review of the session's records was checked claim-by-claim
against code and reports; every checkable claim CONFIRMED. Corrections
applied here, in DESIGN-NOTES (appendix), CLAUDE.md, and the durable
memory. REASONING-LOG addendum 7 = the compressed verdict.

1. **Session-gate mislabel (headline correction, applied above).** The
   probe's "session gate" omitted the real gate's rival>0.20 term
   (session_decode.py runs place_fragment at gate_true=0.20 AND
   gate_decoy=0.20, then gap≥0.08, then page consistency, and a
   ≥60-site refine floor). The 3-site false placement is refused by
   BOTH production gates; "first false placement on record" is
   retracted — it is "first false under a probe-relaxed gap-only
   gate". The perfect-chance-decoy lesson below ~24 evidence bits
   stands.
2. **Counts.** 1,626 of 1,680 windows carry ≥14 sites (960 c2 + 666
   c3); earlier prose said "all 1,680". 0 false among the 1,626.
3. **Null provenance.** The committed driver runs wrong-seed nulls at
   6/10 mm only; the 5/8 mm wrong-seed and wrong-region nulls quoted
   in RESULTS were ad-hoc uncommitted runs (conversation-only
   evidence). Re-scope or re-commit before citing them.
4. **PAD-BIT DESCRIPTOR RETRACTED (measured).** Flipping one pad bit
   of the v3 message changes 39-40 of the 100 transmitted word bits
   (systematic BCH parity spread; verified against bch.py for all 5
   pad positions). An a-priori-unknown descriptor bit therefore
   destroys ~40% of that tile's predictable correlation field —
   in direct conflict with the cold-start predictability that
   pilot_field/Stage-B/F13 rely on. Decision: ALL FIVE PADS STAY
   ZERO. Descriptor candidates: a dedicated sparse filler-site class
   excluded from cold correlation (the C2 descriptor-site mechanism
   grafted into C1), or the bootstrap/preface sheet (BOOTSTRAP-DESIGN
   already names it as the descriptor home), or an explicitly designed
   two-hypothesis word scorer (dispreferred: FA + compute costs).
5. **Density slip.** 100+28 sites in 64² = 3.125% (not 2.73%); 2.73%
   = 112 sites. Also: density is NOT invariant to C1/C2 — C1 with
   words-in-every-tile has a 2.44% FLOOR (fillers only dial upward);
   C2 (or sparse-word variants) can go below. The "one isolated
   binary" framing was overstated by this coupling.
6. **Page-fill sharpening.** The base 64-quantum fields fit under the
   EXISTING 6.0 mm policy (c3 2240×1536: margins 6.26/7.46 mm; c2
   3328×2304: 7.61/7.46) — no policy change needed for +3.3/+4.7%.
   Corrections: c2 3392×2368 needs ~4.75 mm (not 4.9); the c3
   64-quantum next rungs need 2.20 mm (y) / 3.40 mm (x) — the quoted
   3.72 mm was the 60-quantum rung. AND: geometric fit ≠ payload-safe
   channel — E025 distinguishes ink reach from payload-safe extent and
   has NOT yet certified a complete payload-safe C2 rectangle even at
   current extents; every extent change is gated on E025-style edge
   canaries at the exact proposed field edges. Printability is also
   distinct from the BOOTSTRAP archival trim-margin policy.
7. **Identifiability scales with the attempt space.** The ~2^23.7
   figure is the probe's geometry (one page × 4 rot). One c2 page is
   ~2^24.8; a ~128-page mirrored c2 volume ≈ 2^32.8 → ~46-55 sites at
   5-8% BER before safety margin. (Strengthens C1: words collapse the
   space; C2 pays it.)
8. **Thinning ≠ P64-mask qualification.** e026 thinned consultation of
   the existing P60 pattern; it does not qualify any particular
   exact-100-in-64² construction. A normative P64 mask needs its own
   battery: max empty rectangle/radius, autocorrelation + period-slip
   rivals, mirror/rot90 discrimination, tracking-interpolation
   residual, pose-refinement performance, cold acquisition, several
   independent seeds. (The v1 PERIOD=64 stripes are the cautionary
   precedent.)
9. **Aligned-shortening spatial-correlation caveat.** Capacity is
   count-only but BLER is not: P64 colocation repeats the same
   slot→codeword mapping in every tile, so banding/edge-gradient/
   phase-correlated errors hit the SAME variable nodes page-wide
   (today's 60/64 phase cycling decorrelates this). Mother graph can
   stay frozen; correlated-raster replay + real-sheet yield must be
   requalified; candidate mitigation if replay shows a problem =
   per-tile slot permutation keyed by tile index (format knob).
10. **Descriptor content.** data_len+CRC is insufficient: volume-
    instance binding is MANDATORY for fixed-public-key profiles (the
    e018b never-combine rule; LAYERS binding requirement) — SHA-256 or
    a volume id is not an optional tier there. Unique-seed volumes are
    bound by the seed itself.
11. **Governance conflict confirmed.** LAYERS.md ("code rates … any
    change is a layout_version bump") vs FEC-DESIGN ("rates are
    registry entries … no layout_version bump") disagree; reconcile at
    the PILOTS-v2 note.
12. **Rename.** "Converged bundle" → **leading-candidate bundle**; the
    architecture (64-grid, frozen n=4096, exact quota, no partial
    tiles, C1-with-zero-pads baseline) survived review; what was
    removed is premature certainty. The review's 8-item pre-freeze
    list (legacy-gate e026 rerun on the parity-split E022 receiver;
    normative P64 masks + battery; declared attempt budget → derived
    support gates; correlated-error replay; two-sheet/two-engine P64
    prints incl. low-density cold acquisition; E025 canaries at exact
    proposed extents; full descriptor + binding; color/bootstrap/
    governance reconciliation) is ADOPTED as the qualification plan,
    superseding this file's shorter "owed" list.
