# E022 reasoning and design process

**Started 2026-07-14 before qualification results were known; implementation
and qualification feedback appended the same day.**

This file records how the implementation choice was reached. `README.md` is
the normative experiment design; this is the decision trail, including ideas
that were considered and rejected.

## Starting question

E021 deliberately stopped after finding signal-bearing scan regions, one
platen-wide cell pitch, and optional angle hints. The next pass had to recover
absolute pilot-tile locations without also becoming the payload/LDPC receiver.

The first E022 draft followed the existing receiver too literally:

1. estimate a pose;
2. sweep pilot-tile phases;
3. decode a complete BCH word;
4. validate it with Stage B;
5. propagate to neighboring words;
6. add separate partial-word and correlation fallbacks.

That design was defensible from the historical record, but it was not clean.
It gave full words, partial words, and four-way straddles different geometric
solvers even though all three expose samples from the same deterministic pilot
field. It also imported remedies for old receiver failures before showing that
the new stage boundary suffered those failures.

## The useful inversion

The key observation was the A|B|C|D corner case. If every page's pilot values
are regenerated as one sparse matrix, an arbitrary scrap-grid window can slide
over that matrix without knowing where the true 60x60 boundaries cross the
window. Observations from one, two, or four pilot tiles contribute to the same
score while retaining their real site ownership after placement.

This is not a new mathematical primitive. `paperholo.place.place_fragment`
already correlates a fragment against `pilot_field`. The design change is to
make that operation primary rather than reserve it for small leftovers. This
matches the routing inversion already argued in `PILOTS-DESIGN` section 15.8,
but E022 takes only the placement idea, not the session receiver around it.

Consequences:

- BCH does not need to provide a gradient or the first address.
- There is no special pre-placement partial-word representation.
- Page geometry participates in every field hypothesis, so a wrong width is a
  rival field rather than a Stage-B special case.
- Expected pilot values are regenerated exactly once through the format code.
- A failed window can remain unresolved without vetoing another observation.

## Why BCH remains

Removing blind BCH from the correctness path does not imply deleting BCH from
the printed format or implementation. The current page-wide field is composed
of BCH-encoded, scrambled address words; its distance spectrum helps determine
the rival floor.

A high-quality window may also contain a nearly complete word. Vectorized BCH
search can then yield `(page, tile, phase)` without a full-page FFT. This is an
optimization only if measurement shows it wins on the actual page geometry.
The implementation therefore:

1. tries BCH only on mask-dense windows large enough for a complete word;
2. derives a candidate page origin from the decoded address;
3. checks that origin against regenerated pilot-field evidence;
4. records BCH and correlation time separately;
5. can disable the route with `--no-bch-first`.

The first small-page smoke benchmark already showed why the condition matters:
decoding four BCH windows took about 0.49 s while full correlation took about
0.10 s. On the full E018 page, four BCH windows still took about 0.80 s versus
about 0.69 s for padded correlation. Restricting the high-quality starter to
the single best interior word reduced BCH to about 0.20 s. Qualification must
repeat that full-geometry comparison before the default is frozen.

Known-position BCH reads after placement are a different operation. They can
combine physical observations from independently placed scraps and report
word consistency. A failed read never invalidates placement.

## Pose ownership

The early design said every addressed pilot tile should carry one full pose.
That was still slightly wrong. Pose belongs to a physical observation:

- opposite halves of the same absolute tile may sit on different scraps;
- separate scans of one scrap have different scanner transport distortion;
- a fold can make two windows on one scrap require different local maps.

The implementation therefore stores a full cell-centre-to-native-scan affine
map on every placed window. `PilotTileEvidence` aggregates observations by
absolute `(page, tile_y, tile_x, site_index)` but retains each observation's
source coordinate and window pose. It never averages unrelated scrap poses.

An accepted window can predict a nearby window's entire pose and page origin.
The neighbor performs a small local placement check and keeps its own pose.
Only propagating angle would discard scale, phase, and shear information.

## Distortion choice

The review correctly noted that a generic smooth residual field did not match
the measured stepped scanner channel, while the legacy slip repair was only
axis-aligned and separable. Importing either model would make v1 larger without
showing it was needed.

E022 v1 therefore stores a 2x2 affine Jacobian and processes long/distorted
pieces with overlapping local windows. A step or fold inside a window must
either be absorbed by a smaller window or refused. Scanner-step, fold, and
long-c2 fixtures test that boundary. A richer residual is promoted only after
a measured failure survives subdivision.

The first implementation seeds the matrix from the measured pitch, angle, and
phase sampler. The data contract is already affine; estimating independent
scale/shear components is an incremental refinement, not an API change.

## Sampling footing

"Use original pixels" was retained as a coordinate/provenance rule, not a
claim that native 4800-dpi samples are always superior. E018 measured a 3x3
block-mean 1600-dpi footing outperforming direct 4800-dpi processing.

The implementation may construct an axis-aligned integer block-mean working
image, but every cell centre is mapped analytically back to the original scan.
No crop or scan is rotated, counter-rotated, or deskewed. Candidate orientation
changes only the sampling coordinates and canonical index mapping.

## Largest first, known support, and neighbors

Regions are processed by decreasing E021 area. Within a region, mask-dense
windows are processed first. This ordering is useful because a large scrap is
more likely to produce a strong address and full local pose.

After placement, sufficiently observed pilot tiles leave the `need_mask`.
Their expected values remain in the `evidence_mask`, so they can still reject
or support a neighboring scrap but are not rediscovered as the only new work.

For later windows on the same E021 region, an accepted window predicts the
canonical page origin after the exact rot90 window-offset transform. A bounded
neighborhood is checked before a full-page search. This is an optimization,
not an acceptance inheritance: pilot evidence at the target window must pass.

## Precision without recreating Stage B

E022 has no payload CRC inside its initial pass, but the intended receiver does
have E023 after it. The design therefore distinguishes:

- high-confidence placements E022 can admit on pilot evidence;
- ranked/unresolved observations retained for E023-directed retry;
- CRC-certified payload results, which only E023 can produce.

The correlation search uses disjoint deterministic pilot-site subsets for
search and validation. The winner must pass both, and its closest search rival
is retained. This supplies independent address evidence without rebuilding
the BCH Stage-A/Stage-B chain.

The eventual operating point is evaluated twice: E022 standalone precision
and coverage, then E021/E022/E023 closed-loop recovery. A legacy failure case
becomes a qualification fixture; it does not automatically prescribe the old
implementation mechanism.

## Diagnostic choice

The terminal artifact must make address errors inspectable, not merely print a
tile count. The final PNG and every `--diag` frame therefore show:

- pane A: the E021 scan-space regions and current E022 outcome;
- pane B: each accepted scrap/window footprint in canonical page coordinates;
- pane C: addressed pilot tiles, with partial, correlation-registered, and
  successful known-position BCH states distinguished.

Frames are written after every largest-first region. The diagnostic is an
observer: rendering failure must not change placement results.

## Deliberate non-goals for v1

- no payload sampling or LDPC calls;
- no joint inference of two independently ambiguous scraps;
- no blind reflection unless the capture contract says it is legal;
- no free-form warp field;
- no live HTTP diagnostic server in the single-scan runner; the later
  persistent harness adds one as an additive observer over the same PNG;
- no copied gate justified only by its historical value.

These are boundaries, not claims that the combined receiver will never need
them. E023 feedback is expected to revisit boundary tiles with certified page
support and tighter raw-sample priors.

## Qualification feedback and corrections

The first implementation/qualification cycle changed three details.

First, the BCH timing question depended on what "candidate tile" meant. Blind
Stage A over four interior words took about 0.80 s on E018 geometry and was not
faster than padded full-page correlation at about 0.69 s. Trying exactly one
mask-dense interior word took about 0.21 s, a 3.31x median speedup. The shipped
starter therefore decodes one high-quality word, validates the implied origin
against the pilot field, and falls through immediately on failure.

Second, the initial real run accepted 79 overlapping windows. Full correlation
respected the unresolved support mask, but BCH-seeded and neighbor-seeded
routes did not recheck it. Applying the same exact mask-overlap rule to every
route reduced the result to 68 windows while retaining 337 addressed pilot
tiles. Known pilot values remain evidence; already-covered tiles no longer
justify another placement by themselves.

Third, the first real qualification incorrectly classified every BCH decoder
refusal as a placement contradiction. That violated the one-way trust rule and
the measured channel: a sufficiently covered word may still exceed its error
budget. The evidence model now distinguishes:

- not attempted because algebraic coverage is insufficient;
- attempted but refused by BCH;
- decoded to the expected known address;
- decoded to a contradictory address.

The frozen real run recorded 82 expected-address decodes, 110 refusals, and no
contradictory decoded addresses. Refusals remain diagnostics and do not veto
correlation placement.

The run also made one remaining limitation concrete. Every window emits a full
2x2 source-coordinate pose, and neighborhood routing propagates that complete
matrix plus page location, but the current estimator fills the matrix from one
local pitch and angle per E021 region. It does not yet fit independent
anisotropy/shear per window. The API and diagnostics are ready for that work;
the README does not claim the unmeasured capacity.

## v2 (2026-07-14): the measured v1 failures and the per-window inversion

The user review rejected v1 on recall and on design grounds (region-global
pose, internal predecimation). The v1 baseline was then measured on all
available footings before any change:

- decimated-1: 17/17 regions, 68 placements, 337 tiles (the frozen v1 run);
- decimated-2: 10/10, 37 placements, 210 tiles;
- decimated-3: **7/8 — the largest region (5383 mm2) fully unresolved**;
- native 4800 confetti-1: **15/17** (two regions unresolved), 45 placements,
  248 tiles — strictly worse than its own decimated twin;
- native 2nd take (session s001): 27 placements, 150 tiles.

Mechanism probe (decimated-3 largest region, `scratch/e022_probe_dec3r0.py`; since 2026-10-09
`probe_dec3r0.py` in this directory):
e021's hint was -4.45 deg and the truth -4.50 deg, but v1's region-level
score picked -3.95 deg because the region-scale contrast objective is
measurably FLAT in angle (40.34 at the wrong angle vs 40.73 at the true one
— 1 percent over 0.55 deg). One pose per 600-cell region turns that 0.55 deg
into multi-cell drift at region edges, so every window's bits decorrelated
and the region died. At the true angle the same top window places at
mismatch 0.144. Conclusion: the flat objective + one-pose-per-region +
the +-1 deg offset ladder are jointly the recall killer; the block-mean
working image additionally quantizes geometry and pins the sampler to
8 px/cell.

v2 changes, in dependency order:

1. **Spectral Jacobian per window.** The two lattice fundamentals of a
   window's gradient spectrum are measured (coarse rfft2 peak + zoom-DFT
   sub-bin refinement) and inverted into the full 2x2 J: rotation,
   anisotropic scale, and shear in one blind mod-90 measurement. No angle
   seed, no sweep ladder, no flat objective. Measured on the pose battery:
   J entries within 0.001 px of ground truth at 200-cell windows.
2. **Native aperture sampling.** One `uniform_filter` box prefilter per
   region crop (aperture ~0.7 pitch) plus one order-1 subpixel read per
   pose-mapped cell centre. This keeps the measured decimate-first
   radiometric advantage (the aperture) while deleting the decimation
   (the geometry quantization); 23.85 px/cell is sampled as exactly
   23.85 px/cell and the same code path serves 8 and 24 px/cell.
3. **Sub-cell phase + post-placement refinement.** Coarse 1/8-cell phase
   grid with quadratic subpixel interpolation before placement; after
   placement, signed-margin refinement of (angle, subpixel origin) on
   SEARCH-parity sites gated by the disjoint VALIDATION-parity mismatch.
4. **Parity discipline fix.** v1's neighbor route argmaxed on ALL sites
   and then "validated" on a subset of them; v2's chained placement
   argmaxes on parity-0 only and accepts on parity-1 only (the BCH seed
   route was aligned the same way). Rivals are reported only where a
   rival was actually searched (`rival_searched`), instead of v1's
   fabricated rival_mismatch=1.0 / z_gap=inf.
5. **Pose propagation + components.** An accepted window predicts a
   neighbor's page origin through its full J (rot90-aware, exact algebra
   pinned by test); the neighbor fits its own pose, must pass its own
   parity-split gates, and a consistency failure re-anchors through the
   full-page search, opening a new pose component when its independent
   placement wins elsewhere (touching scraps, breaks).
6. **Straddle audit.** A window across a scanner y-step or fold locks the
   majority side; the minority side reads ~50% against the placed address.
   A per-axis change-point on the site wrong-rate profile strips the bad
   side from the emission core, and refuses the window when the residual
   stays high. The first implementation used a max rate-difference split
   criterion and the y-step fixture caught it choosing a tail cut that
   left 14.5% poison in the kept side; the shipped criterion is minimum
   binomial impurity, which recovers the true cut (agreement 1.0000 on
   the fixture). Subdivision (one level, four half windows) remains the
   recovery path for refused windows.
7. **Emission and audit-trail fixes.** Observations are emitted under the
   ERODED, audited core (v1 emitted the un-eroded mask — the 016.7 rim
   class); same-scan duplicate observations of one site vote only once
   (highest weight; the F1/F6 correlated-evidence rule); windows that add
   no needed support are recorded as `redundant_skipped` with their
   would-be origin (v1 dropped them silently). The needed-support test
   became pilot-SITE-granular: cell granularity let duplicates ride
   site-less cells of boundary tiles forever (measured on the
   duplicate-scrap fixture).
8. **Seed hygiene.** The e018 descriptor moved into
   `formats.FORMAT_REGISTRY` (appended last so equal-seed test candidates
   keep identifying as e012); `run_e022.E018` is now a registry lookup.
   Session states bumped to STATE_VERSION 2 (v1 pickles refuse cleanly).

## v2.1 (2026-07-14, same day): closing the retrospective's residual rows

The implementing thread's v1 retrospective (recorded by the user) named
deficiencies beyond the pose/footing core. Cross-checked against v2, four
were still open and are closed in this round; each got its regression
fixture first:

1. **Cross-scrap tile resurrection.** v2's need mask was SITE-granular in
   its test but TILE-granular in its bookkeeping: a tile with >=
   found_tile_min_sites observed sites left the pending set wholesale, so
   a second scrap contributing ONLY that tile's unobserved half was
   `redundant_skipped` — precisely the resurrection the design promises.
   Pending is now per-site (`_pending_masks` clears exactly the observed
   site positions). Fixture: a scrap with a 60x60-cell hole astride four
   pilot tiles plus a second scrap covering only the hole; under the old
   mask the fill scrap was measurably skipped, now all four tiles union to
   80-100 sites and decode. The fixture also caught a REAL DECODER BUG:
   `decode_known_tiles` passed `max_errors=(26-f)//2` to the erasure
   decoder, which `bch.decode_erasures` reads as REDUCED strength and
   refuses whenever `f > 2*max_errors` — a CLEAN word with more than 6
   erasures could never decode. Full t=13 strength restored (the 2e+f<=26
   budget is enforced inside the decoder).
2. **Small-support rival floor, measured and registered.** A minimal
   70-cell fill scrap refused honestly: at 61 search-parity sites a decoy
   dipped to mismatch 0.166, under the 0.20 rival bar that was frozen at
   >=135-site support. Recorded as an open calibration item (the bar needs
   a support-conditional form or a z-gap leg before sub-100-site scraps
   are in contract); the fixture uses a 100-cell fill, which sits inside
   the frozen regime.
3. **Missing-pitch fallback.** `search_survey` now implements the
   section-2 prior chain (survey pitch -> explicit prior -> descriptor
   pitch through scan_dpi) instead of raising; drivers thread `--dpi`.
   The window spectral fit re-measures locally either way, so a
   descriptor prior only centres the search band.
4. **Retry ledger.** Unresolved windows now record their best losing
   candidate (page/origin/rot90/support/rival/validation) in the window
   audit — the E023-directed revisit needs the hypothesis, not just the
   word "unresolved".
5. **Fold fixture + a real pose-estimator fix.** The paper-fold fixture
   (lower half rotated 1.6 deg about the crease, content continuous)
   caught the per-window spectral fit inheriting the REGION's first-window
   reciprocal vectors as a zoom-DFT prior: a 1.6-deg fold moves the
   fundamental ~7 bins, outside the zoom capture, so bottom-half windows
   locked the top's angle and read garbage. Every window now runs its own
   full coarse fit (the prior path survives only for windows too small to
   measure). Post-fix: both fold angles measured (span > 1.4 deg),
   agreement 1.0000. Note the fold yields ONE pose component by design —
   the page mapping is continuous at the crease; the fold is visible in
   the pose ANGLES, not in the component partition (the y-step, which
   breaks the mapping, is the component fixture).
6. **Null battery + multi-page rivals.** Q1 now searches a four-page
   legal set (cross-page rivals must lose) and the null battery grew from
   12 iid draws to 49 adversarial nulls (iid at several shapes, a
   perfectly periodic value-less lattice, constant fields, and true
   fragments against a wrong-page-geometry same-seed field — tile row 0
   deliberately avoided, where the v3 counter really is tiles_x-invariant
   and the fields coincide). False accepts are reported over the full
   multiplied hypothesis count (784 field hypotheses this run), not per
   trial. Thresholds themselves remain inherited-then-validated, not
   re-derived — that stays an open registered item.

## Registered for later: measured coherence length / adaptive window span

(User suggestion 2026-07-14, deferred by decision.) The 200-cell window is
the c3 coherence length measured once by hand (018.2 p5: 47 mm rigid
fails, quadrants pass). E022 now produces that measurement continuously as
a by-product, so a later pass can close the loop without new
instrumentation:

- every chained window's `predicted_residual_cells` vs its anchor
  distance samples the pose-field gradient; the distance where residuals
  reach the ±2-cell consistency bound IS the coherence length, per sheet
  and per direction;
- straddle-audit strips and subdivision events are censored observations
  ("coherence < this span, here") whose spatial density maps coherence
  VARIANCE (creases, humidity, scanner transport zones);
- per-window refinement deltas separate the print-frozen affine component
  (transfers across scans of one sheet -> feeds the §15.6 sheet-level
  affine-prior deferral) from per-scan transport steps (do not transfer;
  keep subdividing).

Policy sketch: seed span from a per-descriptor default in MILLIMETERS
(~25 mm c3, tighter c2), maintain a per-region running coherence estimate
from chain residuals, shrink on audit/subdivision pressure, grow while
residuals stay well under a cell. Hard boundary: spans must not drop below
the gate-support contract (~135 sites ~ 70 cells at p60b6) until the
support-conditional rival bar exists — the two open items are natural
companions in one calibration pass.

## v2.2 (2026-07-14, from the E023 design review): payload need != pilot need

The E022 need-mask logic is deliberately pilot-centric — it exists to stop
re-discovering already-observed pilot sites. The E023 review exposed the
blind spot in reusing that logic as a RECORDING filter: a redundant window
is a fully gated placement whose pose is exactly as valid as an accepted
one, and the payload pass samples cells only through recorded poses. The
skip decision was made AFTER placement, refinement, and the straddle audit,
so recording the result costs nothing; only its pilot emission and anchor
duty stay suppressed, keeping search behavior byte-identical.

The alternative considered — tolerant `getattr` reading of old v2 states —
was rejected: pre-v2.2 states are not merely schema-old, they are
*incomplete for the payload pass* (their redundant poses were never
captured), and mixed-vintage states are exactly the silent trap this
project's version checks exist to refuse. STATE_VERSION 3, clean refusal,
re-run the sessions (minutes).

One semantic addition rode along: a region whose every placed window is
redundant used to report `unresolved` (red) — misleading once its
footprints appear in pane B. It now reports `redundant`, rendered in its
own color.

The first implementation deliberately stopped at one scan because E022 had
not yet proven its result contract. Once repeated ingest was requested,
persistence was added above that contract rather than by turning E022 into the
E018 payload session driver.

Each scan is searched independently. A second platen capture has a different
scan coordinate system and may have different paper distortion or transport
steps, so its pose cannot inherit the first scan's pose. The session stores
each `PlacedWindow` and `PilotObservation` with a stable `scan_id`, then
rebuilds an absolute-address union for display and known-position BCH voting.
E023 can later consume the independent source mappings without reconstructing
which observation came from which scan.

The state envelope is a versioned plain dictionary rather than a pickle of an
experiment-local `__main__` class. Writes use temporary-file plus
`os.replace`; a crash during E021/E022 leaves the preceding complete state
intact. SHA-256 suppresses duplicate content, and compatibility checks reject
mixed DPI, format, seed, page geometry, or legal page sets.

The live diagnostic reuses the exact three-pane renderer. During a scan pane A
shows that scan's E021 progress; panes B/C show all committed scans plus the
current partial result. A small stdlib localhost server publishes `/`,
`/frame.png`, and `/status.json`, while frames remain numbered on disk across
invocations. It owns no search state and catches observer failures.

Two native-4800 invocations established the persistence mechanics: `s000`
contributed 45 placements/248 tiles and `s001` 27/150, combining to 72
provenance-distinct placements and 264 unique tiles with BCH 37 matching / 0
contradictory / 89 refused. Duplicate re-ingest preserved the state byte for
byte. Native 4800 with E022's per-region 3x footing did not match the
externally decimated 1600 result (68/337 on one take); the harness is qualified
to ingest native scans, not to claim that this footing is the best input.
