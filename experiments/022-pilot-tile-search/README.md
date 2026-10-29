# Experiment 022 - PILOT-FIELD PLACEMENT

**Status: v2.1 (per-window native pose + cross-scrap site unions)
implemented and qualified 2026-07-14 against synthetic pose/limit/null
batteries and the real e018 scans at BOTH footings (externally decimated
1600 dpi and native 4800 dpi). The v1 implementation (one similarity pose
per region, internal block-mean predecimation) is superseded: its measured
recall failures and the v1 retrospective's residual rows are recorded in
section 11 and `DESIGN-NOTES.md`. v2.2 (2026-07-14, the E023 seam fix,
section 11.4): redundant placements are recorded with full poses,
STATE_VERSION 3. Open: E023 closed-loop, c2 arms, gate re-derivation,
sub-100-site scrap contract.**

E022 is the format-aware placement pass between e021's platen survey and
e023's payload/LDPC pass.

E021 answers:

> Which native-scan regions may contain the printed lattice, what is the one
> platen-wide cell pitch, and does each region have a useful angle hint?

E022 answers:

> Where does each sufficiently supported region or subregion lie in a legal
> page's pilot field, and what local map samples its cells from the original
> scan?

The primary geometric solver is correlation against the regenerated,
page-wide pilot field. A candidate window can contain one complete pilot
tile, fragments of two tiles, or the A|B|C|D corner fragments of four tiles;
the same operation places all of them. It does not first have to decide where
the real 60x60 pilot-tile boundaries cross the crop.

This design is deliberately smaller than the legacy acquisition receiver.
It learns from that receiver and from `PILOTS-DESIGN` section 15.8, but it
does not recreate Stage A/B, the session driver, its routing thresholds, or
its payload-emission policy.

Implementation:

- `paperholo.pilotsearch` contains sampling, largest-first window search,
  BCH seeding, soft pilot-field correlation, neighborhood placement,
  observation aggregation, and known-position BCH reads;
- `paperholo.pilotcombine` purely rebases and unions immutable scan-local
  `SearchResult` records, retaining scan/region provenance and performing the
  same optional final known-position BCH pass; `session_e022.py` is only its
  persistence/ingest wrapper;
- `paperholo.pilotdiag` owns the reusable, state-free A/B/C panels and the
  stable search-result report. Experiment runners compose these public
  primitives instead of importing another CLI's private rendering helpers;
- `run_e022.py` runs E021 and E022, writes a JSON evidence report and the
  final three-pane PNG, and optionally writes one evolving frame per region;
- `session_e022.py` atomically accumulates independent scans across
  invocations, writes a combined evidence report/PNG, and optionally drives
  the E022 live web diagnostic in `e022_diag.py`;
- `qualify_e022.py` runs the frozen synthetic/timing/real-scan battery;
- `DESIGN-NOTES.md` records the reasoning and rejected alternatives.

The implementation does not call payload extraction or LDPC.

## 1. Scope and stage boundary

### In scope

- choose useful, possibly overlapping windows inside e021 regions;
- estimate a full local cell-to-scan pose for each window;
- sample cell evidence without geometrically rotating the scan;
- place a window by matching its observations against legal page-wide pilot
  fields;
- refine and validate the pose using pilot labels implied by a tentative
  placement;
- aggregate placed observations by absolute pilot-tile/site address;
- regenerate the 100 expected pilot labels for every addressed pilot tile;
- preserve unresolved windows and competing placements for a later retry.

### Out of scope

- payload-bit or payload-LLR emission;
- LDPC decoding, CRC certification, or fountain-symbol accounting;
- payload-assisted placement or pose fitting;
- using uncertified payload guesses as feedback;
- jointly solving two otherwise unplaceable scraps;
- changing the on-paper pilot format.

E022 may be invoked again by a later orchestrator with constraints derived
from CRC-certified e023 results. That is a new, explicitly provenanced pass,
not hidden LDPC state inside the initial E022 placement.

## 2. Actual E021 input contract

E022 consumes `paperholo.platen.PayloadSurvey` as it exists after the 021.4
reset:

- the original 2-D grey scan and its scan-DPI metadata;
- one platen-wide `c_dots` and `cell_pitch_px`, or honest absence of them;
- zero or more `PayloadRegion` records, each with native-scan `bbox`, mask,
  area, score, and optional `angle_hint_deg`;
- legal format descriptors, seeds, planes/modes, page geometries, and page
  sets supplied by the caller.

There is no per-region pitch, pitch uncertainty, contrast, or confidence
tier in the E021 API. E022 must not quietly require those deleted fields.
When global pitch is absent, E022 may try the finite descriptor pitch priors,
recording each prior as a separate hypothesis; otherwise it uses E021's
measured global pitch as its initial sampling scale.

On the frozen 600-dpi print grid,

```text
nominal_cell_pitch_px = scan_dpi * c_dots / 600
```

but the measured scan-space pitch is the sampling quantity. Scan geometry
alone observes a ratio and cannot independently infer print DPI and `c`.

Failure to place a window does not invalidate the E021 region.

## 3. One mechanism: match the page-wide pilot field

For every legal `(format, seed, plane, page)` hypothesis, regenerate two
page-sized matrices in canonical cell coordinates:

```text
P[y, x] = expected signed pilot value at pilot sites, 0 elsewhere
M[y, x] = 1 at pilot sites, 0 elsewhere
```

The current field is generated through the real format implementation, as
`paperholo.place.pilot_field` already does. For v3 this means that BCH words,
address fields, scrambling, overflow rules, and site geometry still define
the printed pilot values. E022 simply does not need to *decode* a BCH word to
search this field.

For a sampled window, E022 produces a cell-grid observation `O`, coverage
weights `W`, and a mask. Correlation evaluates all integer page offsets for
the allowed rotations. At each offset only sites where the shifted `M` and
the observed mask overlap contribute. Thus evidence from arbitrary fragments
of adjacent pilot tiles combines naturally without concatenating bits from
different BCH words.

`paperholo.place.place_fragment` is the executable precedent: FFT
correlation, support accounting, rival exclusion, legal-page enumeration,
and padded page-edge placement. E022 should extract or generalize those
small primitives, not route through the session decoder.

### 3.1 Search evidence and validation evidence

E022 has no CRC backstop, so address precision matters more than in the
legacy receiver. Use a deterministic split of pilot sites into disjoint
search and validation sets:

1. search the full legal page/offset/orientation space using the search set;
2. retain a bounded shortlist including spatial and cross-page rivals;
3. refine continuous pose parameters using search-set labels;
4. accept only when the validation set independently supports the winner and
   rejects its rivals;
5. report the combined score only after the independent decision is recorded.

The split is defined from render geometry/site indices, not selected from
the observed scan. A low-support window may be unable to populate both sets;
it is unresolved rather than accepted under a weaker, accidental rule.

This is a precision-oriented replacement for importing BCH Stage A followed
by Stage B. Gate values are not inherited from section 15.8: its session gap
gate is a useful baseline, but E022 has different observations, hypothesis
counts, and a held-out evidence split. Thresholds are frozen only on fresh
calibration windows that took no part in choosing them.

### 3.2 Legal search space

The initial pass searches the descriptor's full legal page set. It does not
assume an LDPC pending-set prune. Runtime, memory, rival density, and false
acceptance are measured over that actual search space.

After a placement is accepted, known content can still help score another
scrap, but it is no longer a recovery target. Keep these concepts separate:

- `evidence_mask`: expected sites allowed to support or reject a placement;
- `need_mask`: absolute sites/tiles for which a new placement would add
  unresolved scan evidence.

A candidate must add `need_mask` support. This avoids rediscovering the same
easy tile while retaining its known pilot values as geometric anchors. The
initial pass may simply define all legal pilot support as needed. A later
e023 feedback pass may provide a narrower, certified `need_mask`.

## 4. Local pose and sampling (v2 — normative)

Pose belongs to a physical observation window, not uniquely to an absolute
pilot tile and **not to an E021 region**. Two scraps covering opposite halves
of one pilot tile generally have two unrelated scan poses; two windows on one
long scrap generally need two slightly different poses (print y-short,
scanner y-steps, humidity, folds). The v1 failure record is explicit: one
similarity pose per region, selected by a region-scale contrast objective
that is measurably FLAT in angle (decimated-3 largest region: contrast 40.34
at an 0.55 deg wrong angle vs 40.73 at the true angle), left the largest
region of decimated-3 fully unresolved while the true angle placed its top
window at mismatch 0.144. v2 therefore fits geometry per window.

For window-local cell coordinates `q = (cell_y, cell_x)`:

```text
scan_yx(q) = origin_yx + J @ q
```

`origin_yx` is a continuous (subpixel) native-scan coordinate of cell
(0,0)'s centre and the 2x2 Jacobian `J` carries both lattice basis vectors:
rotation, separate axis scale, and shear. Discrete rot90 is canonical-index
bookkeeping outside `J`; `det(J) > 0` always (blind reflection stays out of
scope, as before). A window pose is estimated in three steps:

1. **Spectral Jacobian.** The window's gradient-magnitude spectrum carries
   the two lattice fundamentals. Both peaks are found in an annulus around
   the survey pitch prior (angle-blind mod 90 — no seed, no sweep ladder, so
   the measured 0.4-4 deg seed-error class cannot recur), then refined by
   zoom-DFT to sub-bin accuracy. The two reciprocal vectors form `F`
   (rows f_v, f_u) and `J = F^-1`: rotation, anisotropic stretch, and shear
   in one measurement. The mean pitch must agree with the survey prior
   within a tolerance or the window is pose-refused (a wrong-format or junk
   window fails here, honestly).
2. **Sub-cell phase.** With `J` fixed, the grid phase is searched on a
   coarse cell subgrid over one cell period in cell units (step 1/8 cell),
   then refined to subpixel by quadratic interpolation of the objective
   (masked |mean - median| — the house blind objective; at window scale it
   is sharp, unlike at region scale).
3. **Post-placement refinement.** Once a placement implies expected pilot
   labels, the pose (angle and subpixel origin) is refined on the signed
   margin of the SEARCH-parity sites only, and the refinement is kept only
   if the disjoint VALIDATION-parity mismatch does not degrade. This is the
   `segment.refine_on_sites` train/held-out idea transplanted to the affine
   pose; BCH correction count is never a continuous objective.

The affine window is intentionally the entire v2 model ladder. A long piece,
fold, humidity warp, or scanner transport y-step is represented by several
overlapping affine windows, each with its own measured pose. A window whose
pose or placement evidence says one affine map is inadequate is subdivided
once (four half-size windows, each with its own spectral pose) or refused.
E022 does not need a free-form residual field or a copy of the legacy
axis-aligned slip tracker; between-window origin inconsistency IS the step
detector.

An addressed pilot tile therefore aggregates zero or more observations from
one or more local poses. It retains the individual mappings and never
averages poses across separate scraps or scans.

### 4.1 Pose propagation to unprocessed areas

An accepted window proposes the **full affine pose** to every not-yet-placed
window of the same region: the neighbor's own spectrally fitted origin is
transported through the anchor's `J` into cell offsets, and the anchor's
page placement predicts the neighbor's page origin exactly (rot90-aware).
This is only a search prior:

- the neighboring window fits its OWN spectral pose and phase first;
- a bounded local placement check (a few cells around the prediction) must
  pass on search-parity sites and be confirmed on validation-parity sites;
- a window that disagrees with the prediction beyond the consistency bound
  re-anchors itself through the full-page search; if its independent
  placement wins its own gates at a discontinuous pose, it starts a new
  pose component (touching scraps inside one E021 mask, physical breaks);
- failures leave the window unresolved and never veto other windows.

Propagating only an angle would discard exactly the scale, shear, and phase
information that makes the anchor useful; propagating acceptance would be a
correctness bug. The pose-component partition and per-window predicted-vs-
accepted residuals are part of the output record.

### 4.2 Native sampling at arbitrary resolution — no predecimation

The source scan, crop, and sampled cell grid are never geometrically
rotated, counter-rotated, deskewed, or resampled onto a decimated working
raster. The v1 implementation's internal integer block-mean working image
is DELETED: it quantized the pose to the decimation grid and pinned the
sampler to one target footing (8 px/cell). v2 samples any footing directly
— a 200-cpi print scanned at 4800 dpi (about 24 px/cell), the externally
decimated 1600-dpi twin (about 8 px/cell), or anything else above the
information floor — through one code path:

1. one axis-aligned box prefilter (`uniform_filter`, aperture about 0.7 of
   the cell pitch) runs once per region crop. This is radiometric aperture
   integration — exactly the measured decimate-first advantage — WITHOUT
   moving any sample off the native coordinate grid;
2. every cell mean is then a single subpixel read of the prefiltered image
   at the pose-mapped cell centre (order-1 interpolation), and every mask
   coverage a read of the region mask at the same coordinate;
3. `pitch_px` therefore never needs to be an integer or a multiple of a
   work grid; 23.85 px/cell is sampled as exactly 23.85 px/cell.

The survey pitch is a band-centre prior only; each window's `J` re-measures
the local pitch pair. Consistency with the format descriptor's physical
pitch (`scan_dpi * c_dots / 600`) remains the format check, with the
tolerance wide enough for the measured scanner-scale and print-shrink
terms.

### 4.3 Per-window flow (normative order)

For each region, windows are laid out on the survey-pitch grid with
overlap, ordered densest-support first, then:

1. fit the window pose (spectral `J` + phase). Failure: subdivide once or
   mark the window pose-refused;
2. if an anchor exists in this region: try the pose-propagated local
   placement (section 4.1). Its argmax runs on SEARCH-parity sites only
   and its acceptance needs the disjoint VALIDATION-parity check — the v1
   neighbor route violated this split and is corrected;
3. else (or on failure) if the window is mask-dense and spans a complete
   pilot tile: try the BCH short-circuit — decode one high-quality word,
   derive the implied page origin, verify it against the pilot field
   (search parity) plus the validation parity. This is the measured 3.3x
   fast start, kept as an optimization, never as the only acceptance
   evidence;
4. else run the full-page soft correlation (session gap gate + disjoint
   validation, padded page-edge search);
5. on acceptance: post-placement pose refinement (section 4 step 3),
   re-sample, and emit pilot observations under the ERODED window mask
   (the rim samples backing and is confidently wrong — the measured 016.7
   rim-poison class; v1 emitted the un-eroded mask and is corrected);
6. windows that add no `need_mask` support are recorded as
   `redundant_skipped` with their would-be support, not silently dropped
   (v1 dropped them without a record).

Every attempted window leaves an audit record (outcome, route, scores,
pose, reasons). Rival scores are reported only where a rival was actually
searched; the local propagated route records `rival_searched: false`
instead of fabricated infinite margins (v1 reported rival_mismatch=1.0 and
z_gap=inf on the neighbor route — corrected).

## 5. Cell evidence and erasures

At every sampled cell preserve:

- original-scan coordinate and sampling footprint;
- region-mask coverage;
- raw/normalized sample statistic;
- bounded signed evidence and hard decision, if one is made;
- detector and footing provenance.

The primary correlation implementation should accept bounded signed evidence,
not require early one-bit quantization. Its normalization must make support
and scores comparable across windows without allowing a few extreme samples
to dominate. A hard-bit `place_fragment`-parity mode remains the reference
baseline.

Detector choice is an experiment variable that must be settled explicitly.
The starting arms are the masked-piece median detector already used by the
fragment path and a context detector where it has measured value on c2-class
material. Existing evidence also says context detection can degrade masked
piece grids, so neither arm wins by doctrine. Freeze the simplest detector
that meets the held-out precision/recall bar and retain raw samples so e023
can recalibrate later.

In v1, an erasure means inadequate physical scan/mask coverage at a known
site. Detector uncertainty may reduce a correlation weight but is not silently
turned into a BCH erasure policy. Confidence-selected BCH erasures would be a
new, separately measured arm.

## 6. Acceptance and outputs

### 6.1 `WindowPlacement`

Every attempted observation window emits a record containing:

- source E021 region, native bbox/mask support, and window identifier;
- full affine pose, sampling footing, detector, fit bounds, and uncertainty;
- winning format/page/origin/rot90, if any;
- search and validation support/scores;
- closest spatial, page, format, and geometry rivals;
- exact hypothesis count and rejection/acceptance reason;
- every observed pilot site's absolute address, expected label, raw evidence,
  coverage, and source-scan coordinate;
- unresolved native support suitable for a later retry.

Placement states are `accepted`, `ambiguous`, `insufficient_support`, and
`pose_refused`. There is no `certified` state in E022.

### 6.2 `PilotTileEvidence`

Accepted window placements are projected into absolute
`(page, pilot_tile_y, pilot_tile_x, site_index)` keys. A tile record contains:

- all 100 expected scrambled values regenerated from the format code;
- zero or more physical observations per site, without prematurely merging
  observations from different scraps/scans;
- contributing window placements and their full poses;
- observed matches/mismatches/coverage and unresolved sites;
- optional known-position BCH read records.

Expected labels are not fabricated scan evidence. A missing site has a known
expected value and predicted location under a particular pose, but no sampled
intensity or payload LLR. Pilot cells displace payload cells, so regenerating
them helps later LDPC only indirectly: it improves geometry, local contrast,
and detector calibration at physically observed sites.

### 6.3 BCH after placement

Once placement supplies a tile address, E022 may gather that tile's observed
word sites and run a known-position BCH errors/erasures read. This can add a
word-consistency record and corrected labels. It is not required to establish
placement and a failed or insufficient read never vetoes a correlation
placement.

The reader is new assembly code even though the BCH decoder and site geometry
exist. Build it against composer/render-extracted truth, including actual
rot90 ordering and keystream signs; never retype expected draws. Blind BCH
phase search, Stage A, Stage B, and blind erasure decode are not part of E022
v1. They may remain comparison baselines.

### 6.4 Persistent multi-scan state

`session_e022.py` is the E022 counterpart to E018's persistent session
driver, but its state stops at the E022 boundary. It stores a versioned
format/seed/page-set/DPI envelope and one immutable record per physical scan:
source path and SHA-256, E021 summary, placements, source-coordinate poses,
and pilot observations. The combined view is recomputed by absolute pilot
tile/site.

State is replaced atomically only after a complete scan. Refeeding the same
file content is a no-op, even through another path. A state refuses a different
DPI, format, seed, page geometry, or legal page set. Separate scans retain
separate poses; the union combines evidence only by absolute address and
reruns the known-position BCH read. It does not sum images, copy one scan's
pose to another, invoke LDPC, or perform E023 feedback.

```text
env/bin/python experiments/022-pilot-tile-search/session_e022.py \
  scratch/e018/hp-e018-canon-4800-confetti-1.tiff \
  --dpi 4800 --fresh --diag

env/bin/python experiments/022-pilot-tile-search/session_e022.py \
  scratch/e018/hp-e018-canon-4800-confetti-1-2ndtake.tiff \
  --dpi 4800 --diag
```

Defaults are `build/session_state.pkl`, `build/session_e022.{png,json}`, and
live frames under `build/session_diag/`. While `--diag` is running, the view
is served at `http://localhost:8022/`; numbered frames continue across
invocations. `run_e022.py --diag DIR` remains single-scan and static: it writes
a PNG after each region but starts no server. Both diagnostic modes are
additive observers whose failure must not abort or mutate placement.

## 7. Partial tiles, separate scraps, and boundaries

No special A|B|C|D algorithm is needed before placement. The correlation
window can start at any cell-grid phase, and shifted `P/M` selects whatever
pilot sites from all overlapped tiles are physically present.

After placement:

1. map every observed pilot site to its absolute tile and site index;
2. aggregate observations sharing an absolute key;
3. retain their distinct source poses and provenance;
4. optionally read a BCH word at that now-known position if its combined
   physical coverage supports the algebraic budget.

Two scraps may therefore resurrect opposite halves of one tile after each is
independently placed. E022 does not infer the placement of two ambiguous
scraps merely because their partial words could be combined under one of many
offsets. That joint inference needs another independent prior.

The intended source of that prior is e023: LDPC+CRC can certify payload tiles,
constrain which page support is still needed, and ask E022 to revisit boundary
windows with tighter placement/pose priors. Until then, an ambiguous partial
scrap remains unresolved. This is a precision feature, not a failure to model
torn paper.

## 8. Relationship to section 15.8 and existing tooling

E022 implements the placement insight of `PILOTS-DESIGN` section 15.8:
pilot-field correlation is the primary geometric solver and words are
known-position reads. It also keeps the measured doctrines of mask-local
evidence, padded page-edge search, rival-aware gates, retries in different
windows, and no failed-window veto.

It does **not** implement section 15.8's complete piece receiver. In
particular, it does not inherit S1/S2's exact window routing and gate constants,
the Stage-A fallback, S4 payload emission/recalibration, pending-LDPC pruning,
or session fixed-point policy. Those belong to a different stage boundary.

Likely reusable or instructive components:

- `paperholo.place.pilot_field`, `place_fragment`, `overlap_slices`, and
  support/rival calculations;
- `paperholo.pilots` and `paperholo.bch` for exact field generation and
  optional known-position reads;
- quantitative lock/sampling/refinement ideas from `acquire` and `segment`;
- E011/E014/E016/E018 fixtures and logs for acquisition, c2 visibility,
  decoy floors, page-edge overhang, real scraps, and pose coherence length.

Reuse is earned at primitive boundaries. E022 must remain callable on only an
E021 survey, original scan, and legal format descriptors.

## 9. E023 feedback contract

The expected cascade is:

```text
E021 candidate regions + global pitch
  -> E022 high-precision pilot-field placements + local poses
  -> E023 raw-coordinate payload sampling + LDPC/CRC
  -> certified payload labels and reduced unresolved support
  -> explicit E022 retry of boundary/ambiguous windows
  -> E023 resampling/redecode
```

Only CRC-certified results may narrow the retry search or supply payload-label
feedback. A retry can:

- reduce `need_mask` to unresolved support;
- provide a page/offset neighborhood as a prior;
- request smaller windows around boundaries or scanner steps;
- refit the affine pose and detector against raw samples;
- combine newly independently placed pilot observations by absolute address.

E023 owns LDPC confidence, feedback scheduling, convergence, and termination.
E022 owns pilot-field placement, local pose, native-coordinate observations,
and honest ambiguity. Keeping that line explicit makes the initial E022 pass
independently testable while allowing the combined receiver to outperform it.

## 10. Qualification

Calibration fixtures select detector, footing, window spans, search bounds,
and gates. A fresh frozen battery measures the selected implementation. The
legacy receiver is a comparison arm, not a required internal architecture.
A fixture inherited from the legacy record establishes a failure E022 must
detect, refuse, or recover from; it does not prescribe the legacy remedy.

1. **E021 contract:** consume actual 021.4 surveys, including global-pitch and
   no-pitch cases, `None` angle hints, touching regions, and irregular masks.
2. **Coordinate invariant:** prove no geometric image rotation/deskew occurs;
   compare all reported sampling footprints with analytic original-scan
   coordinates.
3. **Sampling footing:** raw area sampling versus exact integer block-mean,
   including the e018 native-4800/decimated-1600 case; report accuracy,
   runtime, and peak memory.
4. **Pose capture:** rotation, half-pixel shifts, anisotropic scale, modest
   shear, wrong/no angle hints, and all integer cell origins.
5. **Local-affine limit:** scanner transport steps, folds/kinks, the e018
   47-mm coherence failure, and the c2 25-mm/40-mm contrast; assert split or
   refusal when one pose does not generalize.
6. **Full legal correlation:** every allowed page/offset/rot90 and format,
   without pending-LDPC pruning; record total hypotheses and rival spectra.
7. **Precision:** exact-address matching, zero wrong accepts on the frozen
   battery, spatial/cross-page rivals, wrong seed/format/page geometry, blank
   backing, and unrelated printed textures.
8. **Evidence split:** search and validation subsets remain disjoint through
   pose selection; acceptance fails honestly when either lacks support.
9. **Partial support:** arbitrary crops spanning one boundary, a four-tile
   corner, irregular tears, and page-edge overhang; no pre-placement BCH-word
   partitioning.
10. **Cross-scrap aggregation:** independently placed halves of one pilot tile
    union by absolute site while retaining separate poses; jointly ambiguous
    halves remain unresolved.
11. **Detector:** bounded-soft correlation and hard-bit parity, masked median
    versus context detection on c2/c3 material, mask-coverage erasures, and
    extreme-sample robustness.
12. **Known-position reads:** exact gather/descramble/order against
    render-extracted truth, honest `2e+f` refusal, and the one-way rule that a
    failed read cannot veto placement.
13. **Known-target handling:** accepted support leaves `need_mask` but remains
    usable through `evidence_mask`; the search cannot repeatedly win by adding
    no new observations.
14. **Fresh thresholds:** calibration and frozen scans are disjoint; report
    false accepts over the complete multiplied hypothesis count, not only per
    window.
15. **E023 interface:** a synthetic certified retry prior narrows only the
    declared search/need masks and never changes original evidence records.

Headline metrics:

- exact-address placement precision and recall;
- wrong-address count and unresolved count;
- search/validation support, true score, closest-rival score, and gap;
- pose error at observed sites and window corners;
- held-out pilot mismatch before/after refinement;
- full, partial, boundary, and cross-scrap outcomes;
- number of pose and page-field hypotheses;
- runtime and peak memory per native scan area and accepted window;
- legacy `place_fragment`/section-15.8 baseline parity where comparable.

Report two results separately: E022's standalone precision/coverage curve,
including a zero-wrong high-confidence operating point, and the eventual
E021/E022/E023 closed-loop recovery. E022 is not required to resolve every
boundary or low-support case alone; ranked ambiguity and raw-coordinate
provenance are useful output when E023 can certify, reject, and request a
better-targeted retry. Promotion should prefer the smallest implementation
that improves the closed-loop result without hiding standalone errors.

Row status after the v2.1 battery (section 11.2): rows 1 (including the
missing-pitch descriptor-prior fallback), 2, 4, 5 (scanner-step AND fold
arms), 6 (four-page legal set), 7 (49 adversarial nulls including
wrong-page-geometry, FA accounted over the multiplied hypothesis count),
8, 9, 10 (cross-scrap fill of partially observed tiles, synthetic), 12,
13, and 14 are covered by `tests/test_e022.py` + `qualify_e022.py`. Row 3
is superseded in its A/B form — v2 has ONE sampling path (native aperture
reads) and its footing evidence is the measured native/decimated
cross-agreement. Still OPEN: row 5's c2 25/40-mm arm, row 11's detector
alternatives (c2 context arm), row 15 (E023 interface), gate re-derivation
(constants remain inherited-then-validated), and the measured
small-support rival floor: at 61 search-parity sites a decoy dipped to
mismatch 0.166 under the 0.20 bar frozen at >=135-site support, so
sub-100-site scraps refuse honestly and need a support-conditional bar or
z-gap leg before they are in contract.

## 11. Measured results

### 11.1 v1 baseline (superseded, kept as the comparison record)

The v1 implementation (one similarity pose per region on an internal 8
px/cell block-mean working image, ±1 deg angle offsets around the e021
hint) measured, all footings, before the v2 rework:

- decimated-1: 17/17 regions, 68 placements, 337 tiles, known-position BCH
  82 matching / 0 contradictory / 110 refused;
- decimated-2: 10/10, 37 placements, 210 tiles;
- decimated-3: **7/8 — the largest region (5383 mm2) fully unresolved**;
- native 4800 confetti-1: **15/17**, 45 placements, 248 tiles — strictly
  worse than its own externally decimated twin;
- mechanism (probe, recorded in `DESIGN-NOTES.md`): the region-scale
  contrast objective is flat in angle (1% over 0.55 deg on the dec-3
  failure), so one wrong region angle killed every window downstream.

### 11.2 v2 qualification (2026-07-14)

Commands:

```text
env/bin/pytest tests/test_e022.py tests/test_e022_session.py \
  tests/test_e022_shared.py -q
env/bin/python experiments/022-pilot-tile-search/qualify_e022.py
```

Synthetic battery (`build/qualify_report.json`, v2.1 run):

- Q1 exact field over a FOUR-page legal set: 12/12 placements exact
  (every rot90, windows straddling up to four pilot tiles, non-zero
  pages, cross-page rivals lose); adversarial nulls **0/49 false accepts
  over 784 field hypotheses** (iid at several shapes, a perfectly
  periodic value-less lattice, constant fields, and true fragments
  against a wrong-page-geometry same-seed field);
- Q2 BCH fast start on the real e018 page geometry: one mask-dense word
  0.209 s vs padded full-page correlation 0.658 s — 3.1x, starter stays;
- Q3 pose battery, end-to-end from rendered scans with ground-truth
  affine poses, angle hints withheld: rotations 0..44 deg, subpixel
  origins, anisotropy ±0.3-0.4%, shear ±0.15-0.25 deg, at 8.0 / 11.7 /
  23.85 px per cell. All placed exactly; worst-case cell-mapping error
  **0.199 cells at 8-11.7 px/cell, 0.029 cells at the native
  23.85 px/cell footing** (one code path, no predecimation anywhere);
- Q4 wrong-seed field: refused;
- Q5 local-affine limits: the 5-cell scanner y-step splits into two pose
  components with both mappings exact (offsets 60 and 55); the paper
  fold (lower half rotated 1.6 deg about the crease) measures both pose
  angles (span > 1.4 deg) in one continuous component; observation
  agreement **1.0000** on both after the straddle audit. Two audit/
  estimator defects were caught by these fixtures and fixed: a
  max-rate-difference split criterion left 14.5% wrong-address
  observations (now minimum binomial impurity), and the per-window
  spectral fit inherited the region's first reciprocal vectors as a
  zoom prior, which a 1.6-deg fold moves out of capture (now every
  window runs its own full coarse fit).

The cross-scrap contract is pinned in `tests/test_e022.py`: a scrap with
a four-tile hole plus a second scrap covering only the hole — the fill
scrap must be admitted (site-granular pending; the tile-granular form
measurably skipped it) and all four tiles union to 80-100 sites and
decode. That fixture also exposed a real decoder-call bug: known-position
reads passed `(26-f)//2` as max_errors, which the erasure decoder reads
as reduced strength and refuses whenever `f > 2*max_errors` — clean words
with more than 6 erasures could never decode. Full t=13 strength restored.

Real scans (Q6, both footings, `build/*_e022.{png,json}`, post-v2.1):

| scan | regions | placements (chain/bch/corr) | tiles | BCH ok/bad/refused | time |
|---|---|---|---|---|---|
| decimated-1 (1600) | **17/17** | 76 (56/7/13) | 363 | **222**/0/**6** | 71 s |
| decimated-2 (1600) | **10/10** | 41 (29/4/8) | 208 | **129**/0/**0** | 39 s |
| decimated-3 (1600) | **8/8** | 90 (80/9/1) | 529 | **412**/0/**7** | 66 s |
| native-1 (4800) | **17/17** | 82 (62/7/13) | 362 | **221**/0/**12** | 88 s |

versus v1: decimated-3's dead largest region and both unresolved native
regions are recovered; native now matches the decimated twin (362 vs 363
tiles, zero contradictions anywhere) — the decimated footing is no longer
the better path at E022 placement/addressing, it is merely the smaller input
(peak RSS 6.2 GB vs 13.5 GB). This is not a payload/LDPC equivalence claim:
E023b later measures complementary scale-specific likelihood tails.
Known-position word consistency is now 221-412 matching reads
per scan with 6-12 refusals (v1: 82 matching / 110 refused on dec-1; the
successive gains were rim erosion + per-window pose + dedupe in v2, then
the erasure-strength fix and site-granular unions in v2.1).

### 11.3 Full six-scan sessions — the complete pilot map, both footings

The e018 sheet was cut into three piece batches (17 + 10 + 8 pieces),
each scanned twice at native 4800 dpi and once externally decimated to
1600 dpi per take. Feeding all six scans of one footing through
`session_e022.py` (user runs, 2026-07-14):

| footing | scans | regions | placements | pilot tiles | BCH ok/bad/refused/not-attempted |
|---|---|---|---|---|---|
| native 4800 | 6 | 70/70 accepted | 432 | **925** | 868 / **0** / 22 / 35 |
| decimated 1600 | 6 | 70/70 accepted | 411 | **925** | 877 / **0** / 13 / 35 |

**925 tiles is the COMPLETE pilot-tile map of the page** (37 x 25 at the
e012/e018 geometry) — every pilot tile of the sheet is observed and
addressed, on both footings, with zero contradictory word reads across
1,780 attempted known-position decodes. Decimated-session detail
(surviving report): median tile observation 100/100 sites, 507 tiles
fully observed, 890 tiles above the 74-site erasure budget; the 35
never-attempted tiles are cut-line stragglers below the 2e+f<=26
coverage floor. Routing across the session: 331 chain / 42 correlation /
38 BCH-seed placements. Cross-scan poses remain per-scan records; the
union is by absolute site only.

For context (the user's observation on the same physical scans): the
e018 session receiver with the anchor chain and repass recovered the
payload volume through 15-17 of 17 pieces per scan with per-piece
routing casualties; e022 v2.1 resolves every region of every scan and
delivers the full addressed pose map that e023 will consume. The two
receivers end at different layers (payload vs addressing), but at the
addressing layer nothing is left unresolved.

Earlier two-take native session (pre-v2.1 state, kept as the
intermediate record): 34/34 regions, 155 placements, 368 tiles, BCH
213/0/31 — versus the v1 session's 264 tiles at 37/0/89 on identical
inputs.

### 11.4 v2.2 (2026-07-14): redundant placements recorded — the E023 seam

The E023 design review found a payload-coverage hole at this stage
boundary: a `redundant_skipped` window is a FULLY GATED placement (pose
fitted, refined, straddle-audited) that was dropped because it added no
unobserved pilot SITE — but **payload need != pilot need**. Its audited
core can cover payload cells no accepted window covers (subdivided edge
windows, audit-strip complements), and E023 samples payload only through
recorded poses. Multi-scan sessions masked the hole (the pending set is
per-scan); the single-scan archival case has no second chance.

v2.2 therefore records the placement either way: `PlacedWindow.redundant`
flags it, the record carries the full pose and audited `page_cells_yx`,
and ONLY pilot-observation emission, anchor duty, and the accepted counter
remain reserved for non-redundant windows (search behavior, need-mask
arithmetic, component numbering, and word voting are byte-identical;
redundant records carry `component=-1` when not chained). A region whose
windows all place redundantly now reports the honest `redundant` state
instead of `unresolved`. Session states bump to STATE_VERSION 3: pre-v2.2
pickles lack the redundant poses — an incomplete input for the payload
pass — and refuse cleanly. Pane B draws redundant footprints with a thin
outline and a `dup` label; reports carry the flag per placement.

Consequence for E023: both six-scan sessions must be re-run under v2.2
(the old decimated state remains the v2.1 comparison record).

Measured (v2.2 smoke, decimated-1 single scan, `build/v22_smoke.*`):
search behavior reproduces v2.1 exactly (76 accepted placements, 363
tiles, BCH 222/0/6) + 10 redundant placements recorded; the F1 hole on
this scan = 76 payload cells across 20 LDPC tiles covered ONLY by
previously-dropped windows. Small here — thin slivers, as predicted —
but structural: the value is correctness by construction, and the hole
scales with cut geometry and shrinks with scan count (single-scan
sessions are the exposed case).

Six-scan v2.2 re-runs (2026-07-14, old v2 states cleared; these are the
e023 input states): DECIMATED -> `build/session_state.pkl`: 6 scans,
**462 placements = v2.1's 411 accepted + exactly the 51 redundant
windows** the pre-fix audit counted, 925 tiles, BCH 877/0/13 — word
numbers identical to v2.1, coverage now complete. NATIVE ->
`build/session_native.pkl`: 6 scans, **481 placements = v2.1's 432
accepted + 49 redundant**, 925 tiles, BCH 868/0/22 — again identical
word numbers. Both footings confirm the v2.2 invariant: same search,
same words, plus the recorded payload coverage.

Focused tests: 12 e022 + 3 session tests pass; the registry gained the
e018 row (appended last; blind-identification and color-registry suites
pass unchanged). Full repository suite: **384 passed** in 12m26s.

### 11.5 v2.2 shared seam (2026-07-15): behavior-preserving extraction

The E023b composition review found an architectural dependency, not an E022
algorithm defect: multi-scan union lived inside `session_e022.py`, while the
A/B/C view lived inside `run_e022.py`. A higher-layer receiver therefore had
to import experiment CLI modules and even private panel helpers.

The implementation was moved without changing gates, ordering, voting, BCH,
or rendering into `paperholo.pilotcombine` and `paperholo.pilotdiag`.
`session_e022.combine_results` remains as a compatibility wrapper, and
`run_e022` retains aliases for existing qualification callers. A direct
pre-/post-refactor comparison on a two-scan fixture found an exact combined
`SearchResult` snapshot, byte-identical A/B/C PNG, and identical JSON report.
The focused 19 E022 shared/search/session tests pass; the two downstream E023
diagnostic compatibility tests also pass. The frozen synthetic E022 Q1-Q5
qualification battery remains **OVERALL PASS**.

Still open, unchanged from the design: E023 closed-loop qualification,
the fold/kink and c2 25/40-mm window arms, detector alternatives (context
detection on c2-class material), and real-scrap exact-address precision,
which still has no independent scissors-to-page transform (synthetic/
render GT remains the precision metric; the native/decimated
cross-footing agreement above is the strongest scanner-side check
available without one).

2026-10-09: `probe_dec3r0.py` (the decimated-3 region-0 mechanism probe cited in DESIGN-NOTES)
was retired from scratch/ into this directory; it reads `e018/decimated-3_1600.tiff` under
`--evidence-root`.

2026-10-09: inputs renamed to the published archive paths. `e018/decimated-3_1600.tiff` is NOT in
the published archive (tier delete: the six e018 decimations regenerate byte-identically), so
`probe_dec3r0.py` now reads it from `build/decimated-3_1600.tiff` and refuses by name, with the
command, until it is regenerated from the published 4800 capture:
`env/bin/python experiments/018-confetti-c3-play/decimate_scan.py <root>/paper-store-evidence-paperholo-era/018-confetti-c3-play/confetti/captures/confetti-canon-4800grey-3.tiff experiments/022-pilot-tile-search/build/decimated-3_1600.tiff --factor 3`
(`<root>` = `--evidence-root`; the capture is published as `.tiff.jxl`, rebuilt by the release's
`tools/unpack.sh`).
