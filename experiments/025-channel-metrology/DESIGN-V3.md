# E025 layout v3 — the generic printer-characterization instrument

Status: DESIGN v0.2 (2026-07-20). v0.1 was reviewed by a six-lens
adversarial panel against the corpus (69 findings: 2 P0, 16 P1, 33 P2,
18 notes); every P0/P1 is adjudicated below, load-bearing claims
independently verified (emit_e025.py --request default; strip
module_formula round-vs-floor; color-page occupancy arithmetic).
Grounded in a full-corpus extraction (12-reader sweep + gap check; 312
measurement properties, 332 constraints, 247 dead alleys digested).
v2 pages and their captures remain valid v2 instruments.

## 0. Mission

One instrument family printable on ANY reasonably expectable printer —
300 to 2400+ dpi, mono or color, unknown RIP — answering: what
information can THIS engine carry at maximum density x maximum
survivability? Cell ladders at the engine's OWN reachable grid, color
behavior and encodings, grey/multilevel tones, physical properties
(morphology, tone, registration, warp, margins). SELF-IDENTIFYING:
someone mails the physical page with no side channel and the analyzer
still does everything above.

HONESTY CLAUSE (P0-1): "the engine's native grid" is a MEASURED
outcome, not an input. The whole record says finer-than-default grids
are usually unreachable (AltaLink fixed-600, all RQ300..2400 refused;
M281 granted-1200 y-stretches; no PJL/PCL unlock anywhere — 007.6/009).
The instrument therefore measures the DEFAULT render grid honestly,
detects and labels resampled/aliased authored content, and proves what
is reachable — it never pretends a requested grid was delivered.

This is a DISCOVERY instrument. charsheet-1 (holo §13.13/13.14) is
repositioned as a registry-calibration page for an already-known
engine class; its review-hardened statistics are inherited here.

## 1. Architecture ruling

Built AS e025 layout v3, in e025 space (user-authorized): v2 already
carries the coordinate law, two-page mono/color discipline, evidence
hierarchy, area-priority law, 22 dead alleys, and a hardware-qualified
emitter+analyzer. holo `characterize` consumes e025 profiles at
registry-promotion time (batch E). The e025 experiment MAY import holo
(for production coupons); holo never imports back.

## 2. Grid provenance (P0-1 ruling)

- Request policy is a FIRST-CLASS EMISSION AXIS (DESIGN.md §8.9),
  recorded in the strip payload, the manifest, and every field's
  candidate identity. Generic presets default to REQUEST-NOTHING (the
  strip's RD/RE echo then measures the default grid free); `--request
  authored` emits a SEPARATE, separately-labeled footing carrying the
  measured risk (granted modes can distort — M281 y-stretch).
  [Verified: the v2 emitter defaulted to --request authored; v3 flips
  the generic default and keeps hp-m281 aliases on their measured
  footing.]
- The analyzer infers EFFECTIVE device grid from the scan itself (plus
  lattice + grating fundamentals — the ORES verdict logic: device_dpi
  = scan_dpi / px-per-grid-dot) and relabels any authored ladder whose
  effective grid differs as SCALED@<measured> (resample-path evidence,
  never "native-grid channel"). SCALED fields still get scored — the
  alias floor is itself a datum (007.6: 24-26%).
- Operator protocol for an unknown engine: print generic pages
  request-nothing first; if the strip/geometry reveal a finer default
  than assumed, re-emit with that primary. DISC-1/ORES remain the
  separate active-enumeration jobs (§8.10 stands — never on the
  science page).

## 3. Self-identification contract (mailed-sheet cold start)

Chain of independent stages, all but (4) proven parts:

1. **Absolute physical scale**: plus-mark lattice on a 25.4 mm grid;
   corner cross doubles as a by-eye dpi ruler (009).
2. **Orientation**: chiral corner satellites encoding the full 8-group
   (rotation x mirror); the v3 analyzer READS satellites (closing the
   recorded ORES gap).
3. **Machine self-report**: two PHCAL1/LAY=1 strips, CRC; module scale
   `max(3, floor(effective_dpi/100))` dots — FLOOR, with an emitted
   width guard (the v2 round() overflows A4 at specific dpi values;
   P1 fix). Payload: bundle/layout id + public seed + page kind + COPY
   INDEX + primary/comparison grids + REQUEST POLICY + LL/RD/RE/PS/IB
   + product/version/serial where exposed. Readback = provenance,
   never physical truth.
4. **Coarse fallback identity block** (NEW): >= 1.0 mm modules
   encoding {layout version, page kind, primary grid, request policy,
   copy index, 24-bit canonical-layout hash}; decodable at 300 dpi
   (>= 12 dots/module) when strips fail.
5. **Human bootstrap**: a BUDGETED header (one line: job id, seed
   string, layout version, copy, "regenerate: emit_e025 generic-<kind>
   --primary-grid N --copy K") + END sentinel. The full protocol lives
   in the repo, not on paper (P1: the v0.1 header was the largest
   unbudgeted consumer). Microtext arm doubles as its legibility
   measurement.
6. **Dual provenance**: pen-annotation box (operator writes printer/
   path/date); analyzer never reads it.
7. **Copy axis**: copy index seeds ALL stochastic fields; printed in
   strip + fallback block + header; GT regenerates from (seed, layout,
   kind, primary grid, request policy, copy). Wrong-copy GT must
   REFUSE via content mismatch (qualification row).

Refusal doctrine throughout: gates in dots/mm; per-element
unobservable; capture-record reports; tested negative space.

**Scanner adequacy (P1)**: the mailed sheet meets an arbitrary
scanner. The full 008 adequacy table applies, not just strip CRC:
>= 1/2 strips CRC-ok, corner set + satellites resolved, plus-lattice
scale consistent, AND per-candidate minimum measured samples-per-cell
(a 300-dpi scan cannot qualify c1@600 claims). Every tier/capacity row
is conditioned on footing adequacy; inadequate footings yield
"unmeasurable at this footing", never a number.

## 4. Page family and presets

```
emit_e025.py generic-bw      --primary-grid N [--copy K] [--request ...]
emit_e025.py generic-color   --primary-grid N [--copy K] [--request ...]
emit_e025.py generic-color-2 --primary-grid N [--copy K] [--request ...]
```

THREE pages (P0-2 ruling — verified occupancy arithmetic: the v2 color
page holds 28.3k mm² of elements in a 46.3k mm² interior; free
field-capable rectangles total ~3.3k mm² while the v3 color additions
need >= 7.5k mm² even after shrinking the OPM/grid controls, and the
§4.8-claimed displacement stock (c4/c6 fields) does not exist on the
color page):

- **generic-bw**: the K-only operating-path control (sacred, §8.7).
- **generic-color**: single-position color SCREENING + color physics
  (registration, per-plane tone, micro-rails, per-plane multilevel).
- **generic-color-2**: REPLICATED color finalists — each candidate that
  can win a density decision at >= 3 co-page strata + its coupons +
  a full §3 self-ID chain. Split by CANDIDATE, not by replica
  (within-page position variance is the point; cross-sheet replicas
  confound with print-to-print variance).
  USER VETO POINT: declining the third page = color candidates stay
  single-position in v3.0 and the worst-position tier claim is struck
  for them (recorded, not fudged).

Replication rule BOUNDED (P1): the winning-candidate shortlist is an
explicit per-page list, area-budgeted at plan time; the emitter
REFUSES oversubscription (overlap-refusing builder). "Could win" =
measured-record finalists + operator-flagged additions, named in the
manifest.

## 5. Element inventory v3 (delta over v2 §5)

KEPT: tick ladders; corners + plus lattice; fixed-level profiles +
permuted response strips; witnesses; registration stations +
feed-direction lanes; gratings/lines/dots/holes/checkerboards/slant
edges/microtext; state fields C1/C2/C3 (+C4/C6 controls, bw page);
motif + aspect factorials; equal-pitch grid controls; machine strips.

CHANGED / NEW:

1. **State-field ladder at the primary grid** with SCALED relabeling
   per §2 when effective != authored. Winning candidates: >= 3
   positions + production-rung coupon (bounded per §4).
2. **Multilevel/grey cell fields**: K 3- and 4-level at C2/C3 (bw
   page); one 3-level arm per plane (color page). Distance-spectrum
   vetting before any capacity claim (010).
3. **Canary system v3** (P1: merged with the e025 edge system, NOT
   the charsheet geometry — the charsheet 6 mm patches oversubscribe
   e025 edges 2.4-4x): e025's per-edge gap ladder retained, +1
   replica (2 total), PERMUTED gap order per (edge, rep), interior
   references, c2 stress + c3 robust arms, grading on pooled Wilson
   UPPER bounds vs HEALTH-GATED references + per-replica floors +
   completeness; NEW per-row-band grading inside each patch (the
   027.1 aggregate-vs-leading-edge caveat).
4. **Coupon families**: house-LDPC (v2 rungs) AND holo production
   coupons — holo coupons are ALWAYS 600-authored (the holo format is
   600-pinned; they qualify the production stack on the engine's
   600-grid rendering regardless of primary; labeled so — P1 fix).
   Verdicts: ldpc_exact_genie vs word_and_payload_exact.
5. **Fallback ID block + budgeted header + annotation box + END
   sentinel** (§3).
6. **Per-plane micro-rails** beside every chromatic field, CONSUMED by
   the new per-plane geometry arm (§6) — furniture and arm ship
   together (P1: v0.1 shipped furniture with no consumer).
7. **Transport rail v2** (P1): the y phase rail is measured-unresolved
   (resolved:false, corr 0.185) — v3 adds the WORKPLAN's finer
   sub-dot-resolvable transport rail; the legacy rail is retained for
   continuity and labeled diagnostic-only.
8. **Shaped-C2 / rectangular-cell probes** fold into the factorial
   block (Phase-G).

## 6. Analyzer v3-generic (delta over v2 §6)

- **Geometry**: per-window locks; WINDOW-SPAN LAW in mm (span <= the
  transport step pitch class ~4.7 mm, derived per grid); band
  y-refinement; gates in dots/mm.
- **Per-plane geometry arm** (P1, three lenses converged; WORKPLAN
  Phase-B item 3 verbatim): per-window PER-PLANE offsets for
  chromatic fields, seeded from registration stations + micro-rails,
  +-1.5-cell search, integer-slip disambiguation on phase-split cells
  only, per-plane refusal semantics. This is the measured binding
  limit for every CMY composite (0/54 cmy8-c2 windows locked;
  CMY-minus-K 0.57-1.39 cells). Build-order: WITH the color arms, not
  after.
- **Splits, corrected** (P1 — the panel caught v0.1 re-committing the
  F1 sin it cited): FOUR disjoint populations via independent hash
  bits over element-global indices: phase/lock FIT; lock/phase
  CERTIFICATION (never the fit cells); detector training; held-out
  validation (consulted by nothing). Partition unit test pins
  disjoint/cover/balance; certification never reuses fit cells,
  validation never enters any selection.
- **Detector**: QDA arm 1 (portable floor) + per-window min-error
  scalar arm; multilevel fields via multi-state QDA. Arm-2/arm-3
  ladder post-track-3 (user ruling).
- **New arms**: effective-grid inference + SCALED verdicts (§2);
  fallback-ID decode; corner satellites; copy plumbing; canary v3
  per-band grading; holo-coupon decode; scanner-adequacy gates (§3).
- **Reports**: capture records; qualified/refusals; 008 tier
  vocabulary on WORST-position stats; spatial tails (worst-window/
  p90) beside means; every number carries its footing + request
  policy + effective-grid label.

## 7. Decision layer

profile_e025 keeps emitter/sensor/pipeline boundaries and gains the
R1-R7-heritage recommendation: per-candidate tier at worst position,
robust/dense/color mode recommendation, explicit day-variance caveat
(one sheet = one day — flagged, never imputed). Registry promotion =
batch E; per-edge margin schema lands there.

## 8. Qualification before any print

1. Emitter: overlap refusal; deterministic per (kind, grid, request,
   copy); gs render == GT dot-exact; goldens per (kind, grid) at
   copy 0; strip width guard test at hostile dpi values.
2. Analyzer vs synthetic identity at 600 AND one non-600 grid, all
   arms, incl. a synthetic per-plane offset fixture with a >0.5-cell
   case, and a SCALED-grid fixture (authored 1200 rendered at 600).
3. M0 simulator harness at 600 (scope-declared M281 physics); non-600
   grids get geometric synthetic distortions only.
4. Refusal battery: wrong-sheet, wrong-COPY (layout matches, content
   must refuse), crop, noise, tamper, dead references, inadequate
   scanner footing.
5. Print gate: user go (hardware.md). First print: M281 generic pair
   at 600 copy 0 (anchored arms); first foreign engine = the real
   commissioning.

## 9. Deliberately excluded (with reasons)

- Active resolution-grant enumeration on science pages (§8.10;
  DISC-1/ORES are the jobs for it — RD/RE ride the strip for free).
- E024-class feedback, blind-receiver claims, RaptorQ.
- MIC/anonymity: color pages assumed non-anonymous (measured AltaLink
  lattice); reported, not fought.
- Full-protocol text on paper (pointer only — P1 header budget).

## 10. Review adjudication (v0.1 -> v0.2)

P0-1 grid provenance -> §0/§2 (request axis, SCALED verdicts,
operator protocol). P0-2 color area -> third page §4 (user veto point
recorded). P1 cluster "splits contamination" -> §6 four-population
doctrine. P1 "per-plane arm missing" -> §6 + §8 fixture + build
order. P1 "scanner adequacy" -> §3. P1 "rail unresolved" -> §5.7.
P1 "holo coupons at generic grids" -> §5.4 (600-authored always).
P1 "strip round/overflow" -> §3.3. P1 "replication unbounded" -> §4.
P1 "canary oversubscription" -> §5.3 (merge, not transplant). P1
"header unbudgeted" -> §3.5/§9. P2/notes (33/18) triaged into the
build checklist (experiments/025-channel-metrology/build notes),
none design-blocking.

## 11. Build order

1. e025_common: v3 seed, copy axis, request-policy axis, layout
   registry + identity hash, generic grid parameterization.
2. emit_e025: generic presets (3 pages), new elements, floor+guard
   strips, bounded replication, overlap refusal, goldens.
3. analyze_e025: effective-grid inference + SCALED verdicts,
   four-population splits, per-plane arm, canary v3, fallback ID,
   satellites, adequacy gates, capture records.
4. profile_e025: tier/recommendation layer.
5. Qualification battery (§8), then STOP for the print decision.
