# analyzer — the impossible-endrun analyzer (design v0.3, 2026-09-04)

v0.3 folds into the body every ruling and every measured finding the build
produced: the six-lens adversarial review of 2026-09-03
(`analyzer/REVIEW-2026-09-03.md`), the W1–W7 build waves, the sheet-I and
sheet-H runs, and the 2026-09-04 separation ruling that took ground truth
out of the run.  There are no appended notes: what a section says is what
is built.  The dated, run-by-run record lives in `PLAN.md` §6; the two
standalone measurement records are `GAPS-2026-09-03.md` (the C parity gap)
and `FIELD2-2026-09-03.md` (the page field).  The operator's manual is
`README.md`.

A dedicated, standalone research instrument aimed at the residue of a
finished holo3 decode: every tile-stream the production receiver left
uncertified.  It is NOT part of holo3 production, adds no rows, changes no
tree under `holo3/` or `src/holo/`, and exists to answer one question per
tile-stream:

> what, if anything, on the receiver axis turns this failed tile-stream
> into a certificate — and when nothing does, how far above the code's
> floor is it, and why.

Scope ruling (Germano, 2026-09-02): pure research; every certificate flip
and every explored instrument counts; hideous but acceptable cost; inputs
are the run folder (facts.npz + rasters) and the TIFFs.  No hardware
levers.  cmy8 rows only (per-plane independent LDPC is what makes a plane
decodable alone; cmy7 packs jointly and is out of scope).

Reads before touching this: `measure/yask/README.md` (the Y-as-K record
whose findings this design generalizes), `holo3/plugins/plane_k.py` (the
production per-tile plane arm this design REUSES), `holo3/SCHEDULE.md`.

## 0. Ground rules

### 0.1 The separation: a run is blind, scoring is offline

**RULED 2026-09-04 (Germano): the analyzer must never reference ground
truth in any shape during a run.  Truth as a run-time input was a breach
of separation.**  Ground truth is not a knob, not a gate, not a side table
a driver carries: it is absent from the process that decides anything.

Structurally: `--gt-dir` and `--payload` exist on ONE subcommand, `score`,
and the parser REJECTS them on `census`, `read`, `ladder`, `controls`,
`close` and `export-facts`.  `analyzer.score` is the only importer of
`analyzer.truth` in the package, and `cli` reaches `score` only inside
`cmd_score` / `truth_error`, at call time, so truth is not on any run
command's import graph.  This is enforced by a test that walks the package's
import CLOSURE from every module under `analyzer/` — dotted names,
relative imports resolved against each importer's own package, so a hop
through a subpackage is visible — and asserts `truth`, `oracle` and `score`
are unreachable from it.  `truth`, `oracle`, `score` and `sweeps` are THE
offline lanes; the test also asserts the reachable set contains the real
run side, so a shrunken root list cannot make it pass by reaching nothing.

Scoring against a payload is an OFFLINE, post-fact tool, and it works
against ANY payload we hold — including one the close itself verified.
That is not a weaker arrangement than the old one, it is a stronger claim:
on sheet H the five ledgers scored against the payload the close recovered
from the union base, with no generation dir and nothing handed to the
instrument, give 1,025 certificates checked, 0 wrong, 0 false accepts.

### 0.2 The four truth-free validators

Certificate correctness rests on four legs, all of them inside the run:

1. **The syndrome+CRC gate with its priced exposure** (§0.3).
2. **The payload envelope's own sha at the close** (§6a): the emitter wrote
   `{sha256}{len:4B BE}{data}` inside the volume, so a volume that closes
   has checked its own contents.
3. **The fountain's over-determination above K** (§6a): an over-determined
   GF(2) system detects a wrong symbol, can LOCALIZE it, and — since the
   error pattern is then known — can correct it.
4. **Independent agreement** (§5): two certificates for one key resting on
   DISJOINT physical captures and carrying identical user bits corroborate;
   two that differ are a contradiction and the key is refused.

### 0.3 The gate, and what it costs

- **Certificate gate.**  A certificate is a hard vector that satisfies
  every parity check of the tile's code AND its CRC-32.  Nothing else ever
  becomes a certificate.  Any decoder may PROPOSE a hard vector (production
  BP, the analyzer's BP variants, an enumerated hypothesis); only
  syndrome+CRC may certify.  Bit-exactness is a law of the encoder, the
  keystream, the permutation/dither and the certificate gate — not of the
  decoder.  The gate refuses codewords that violate the shortening window
  before the CRC is consulted at all.
- **Verdicts a RUN can produce**: `open`, `certified` (a direct rung:
  L0–L3, L7) and `certified_list` (a list-decoding rung: L4–L6 — it MINTS,
  cascades, closes and exports like any other syndrome+CRC certificate;
  the row keeps the distinct verdict and every count that includes it is
  quarantined from a zero-wrong CLAIM until the run's exposure is stated
  beside it).  Plus the blind non-outcomes `below_floor` (observed support
  under the bank's active bits) and `refused` (a rung that declined to
  run).  `wrong`, `false_accept` and `unscoreable` are the OFFLINE
  scorer's verdicts and cannot arise in a run; with them went the
  sticky-verdict carry, since there is nothing worse than `certified` left
  to carry.
- **Exposure is a correctness bound, not a yield cap.**  Every CRC
  consultation costs 2⁻³².  Candidates are de-duplicated by codeword hash;
  exposure is the count of DISTINCT codewords consulted, stated as an
  expectation at the RUN level (a per-rung column was dropped: it was
  thread-order dependent).  The run refuses to exceed E[false] ≤ 0.01
  (≈ 4.3e7 distinct consultations) — a candidate list is ranked by soft
  weight and only its top L (default 4) reaches the CRC.  The CRC never
  enters any elimination or reliability computation.  The codeword digest
  (blake2b-128) adds a negligible second exposure term, stated for honesty.
- **Bounded LLR invariant** (018.7) binds CHANNEL evidence: channel LLRs
  are clipped at the decoder's bound and no arm relaxes it.  Format-known
  bits (shortening; the metadata bit once trusted) and enumerated
  HYPOTHESES (a flipped bit in L4) enter at ±LLR_KNOWN; a hypothesis is
  verified by the certificate gate, so it does not touch the invariant.
- **Physical-evidence invariant**: one physical capture contributes ONE
  evidence vector to any sum; lanes are de-duplicated by capture id before
  any combination; decimated levels of one capture are the same capture.
  This is also the definition of independence in §5.

### 0.4 Discipline

- **Blind columns MAY gate; there are no oracle columns in a run.**
  Unsatisfied checks, iterations and posterior summaries gate freely.  The
  metadata bit is blind — it comes from the run's OWN certified metadata
  word — and lives in `inputs.metadata_bit` for exactly that reason: the
  old home in `truth.py` forced the driver to import the scoring module.
- **Determinism**: `--seed` recorded in the ledger header; every random
  draw (perturbation restarts, sample selection, fold assignment) is a hash
  of (seed, key, rung, index).
- **Controls or nothing** (§8).  A run without its controls is not a
  result.
- **Derive, don't patch**: codec, keystream, permutation, dither, fountain,
  metadata word, BP loop, spectral fit, PAVA, local-affine search, plane
  fields and the production plane arm are holo3's, CALLED.  Three declared
  deviations, each with its measured reason, are listed in PLAN §6:
  `mother.py` re-frames `decode_frame`'s assembly and calls the private
  `ldpc._bp_loop`, and owns a ~40-line damped/offset/layered min-sum;
  `calibrate.to_sequential` calls the private `tiles._sequential_payload`;
  the `head` arm is the analyzer's own per-plane 8-state classifier because
  `color_region_head.fit_region_stack` cannot be driven from a
  footprint-sized window.
- Plain names; units in names (`offset_dots_xy`, `pitch_px_level`).
- ≤ 1000 lines per file; pyflakes clean; every module change carries tests.

## 1. What the record says, and the corrected assumptions

Sheet H (`L:c2-cmy8-r0850-p120-x1@3392x2368`, AltaLink, seven Canon
captures, the machine 4 endrun as of 2026-09-02): 4,883 of 5,883 tile-streams
certified, K = 5,277, so 394 more of the 1,000 residue were needed.
Residue by stream: Y 782 (three full-height dead bands ≈ 555, scattered
≈ 227), C 208 (a full-height band at columns 30–31 plus a half band at
4–5), M 10 (all in the column 29–31 band).  The non-dead-band residue was
≈ 371 tile-streams against 394 needed, before any conversion rate — so a
close was NOT a pre-registered outcome of this instrument (§6a).  It
happened anyway: the instrument minted 508 on its third pass and the union
closed byte-exact (PLAN §6, 2026-09-04).  The sheet is visually homogeneous
and sheet I (same print day, r0700) decoded on the same columns, so the
bands are rate-margin phenomena of r0850, not scanner artefacts.

Measured facts this design builds on (`measure/yask/README.md`):

- Annihilating the sibling planes in the mean halves the Y cell error over
  the raw blue channel; per-cell sibling subtraction adds a little error
  but 5× the adds; a blind per-window sampling offset chosen on the plane's
  own known cells recovers the printer's Y registration sinusoid with no
  ground truth and triples the adds; the seven-capture union doubles them
  again.
- Labels are the binding resource: with certified neighbours' labels
  removed, Y certifies nothing even though the signal is no worse.
- **Corrected label arithmetic**: every word site renders state 0 or 3, so
  C ≡ M and Y = 0 at all 100 word sites.  The word field gives C and M a
  cold-start ADDRESS and ink-vs-paper labels, NOT a C-vs-M separation set.
  The only cells whose C and M bits differ, or whose Y bit is 1, are dust
  cells: ~13 per tile (states {1,2,5,6} for C≠M; {4,5,6,7} for Y=1 out of
  the 6-cycle).  The ledger therefore carries `n_discriminating_labels` per
  tile-stream and arm (labels whose sibling state differs from the
  target's), and blind selection is gated on it (§4.8).
- **Corrected floor argument**: yask's "12.8% vs 8.4% at rate 0.859"
  compares a hard-decision cell error to a soft-decision code rate and is
  not a valid converse (BSC capacity at 8.4% is 0.58, yet those columns
  certify at 0.855).  The decision statistic of this instrument is the SOFT
  INFORMATION RATE (§7): per tile-stream and arm, Î = 1 − mean over
  observed cargo cells of log2(1 + exp(−LLR·(2b−1))) with LLR positive
  meaning bit 1, R = Î·n_observed / active_bits (3400 at r0850).  R < 1
  with a bootstrap upper confidence bound below 1 is a genuine converse;
  the empirical waterfall P(certify | R) over all attempted tile-streams of
  a stream and rung gives R50/R05.  Hard cell error stays a descriptive
  column, computed at the calibrated MAP decision and at the median
  threshold, both labelled.  R is an ORACLE column and therefore an
  offline one: a run reports the blind unsatisfied-check count in its
  place, which answers the same question about a miss.
- **Cascade**: e034 measured 82% of the production plane arm's mints as
  cascade (chains 7 generations deep).  A single pass is a lower bound
  several fold below the arm's behaviour; this instrument runs to a fixed
  point (§6b), and the cascade is worth 16% of the residue on sheet I's
  first-run set and 46% of the harvest on sheet H's pass 3.

Format facts (verified):

- cmy8: one LDPC frame per tile-stream; n = 4096, info block k with 120
  shortened positions at `[k−120, k)`, user bits = k − 32 − 120 (3,368 at
  r0850); `user_bits[0]` is the metadata bit, `user_bits[1:]` the fountain
  symbol; CRC-32 at `[active−32, active)`.  A synthetic r0850 frame
  certifies at 3% hard cell error, not 6% (rate 0.855 against bi-AWGN
  capacity ≈ 0.80 at 6%).
- Payload cells: `row.payload_cells` = 3,976 per tile, permuted by
  `keystream.color_cell_permutation(seed, counter, payload_cells)` and
  dithered by `cmy8_dither_bits(seed, stream, counter, payload_cells)`.
  Production's SEQUENTIAL domain (`tiles._sequential_payload`) is
  un-permuted but STILL DITHERED; `tile_codec.cmy8_decode_stream` is the
  sole owner of the un-dither.  This instrument keeps exactly that domain
  (§4.9).
- The metadata bit is per tile-stream: the 24-bit metadata word (trusted at
  rank 24 and ≥ 48 distinct equations,
  `close.metadata_from_certificates`, re-assembled as the inverse of
  `decode_metadata`) evaluated at `metadata.equation_index(counter,
  stream_index, n_streams)` through `metadata.coefficient_table`.  It is
  injected in the UN-DITHERED mother domain at info index 0; its printed
  cell is `payload_flat[j]`, j = the position where the permutation maps
  sequential index 0, carrying `bit ^ dither[0]`.
- Fountain (pooled, `esi = counter·3 + stream`): ONE block for H/I/J;
  systematic rows for `row < k`, repair rows dense uniform random.  An
  uncertified symbol lies in the certified span only when the rank is ≈ k,
  and no low-weight relation among residue symbols exists: the joint
  fountain-decoding idea is DROPPED (structural).  `report.json` already
  carries the close's GF(2) rank; the census reads it and recomputes as a
  cross-check column only, and a disagreement is a finding.
- **A format id IS the AES seed.**  `--format-ref` replaces the id the
  run's `RunOpen` declares, must resolve through
  `holo3.format.identity.resolve_format_ref`, must keep the `RunOpen`'s
  pitch, and is recorded in the provenance as `format_ref_override
  {run_open, used}`.  Sheet J's run dirs MUST be analyzed with
  `--format-ref L:c2-cmy8-r0547@53x37`: the canonical-identity merge mints
  a different seed for the same display id, and the bare id descrambles the
  sheet to coin flips without raising.

## 2. Inputs and their roles

| input | role | source |
|---|---|---|
| run dir `facts.npz` | a flat fact tuple: Placement (rot_k, native_affine, pitch_px in NATIVE px, page_origin_yx, `local_cells_yx` = support in window-local coords, `quality`), Certificate (user bits, `source` = `tiles/<stage>`), PlaneField, PooledColorCtx, LatticeSeed, Window, CaptureSurvey | `holo3.snapshot.read` |
| run dir `report.json` | capture identity, dpi, channels, `levels_ppc`, shape, pages, the close block incl. rank | parsed |
| run dir `events.jsonl` | `RunOpen` (format ref, pitch); `TileOutcome` certified keys (the withhold set for the positive control) — REQUIRED for `controls`, optional otherwise | streamed |
| run dir `argv` | provenance string only | — |
| run dir `<capture12>/l{NN}-{r,g,b}.npy` | per-lane plane rasters (mmap) | holo3 intake products; `analyzer mirror` rebuilds them locally, byte-identical |
| capture TIFFs | native pixels only if a level is missing (`tifffile.memmap` RGB views) | `scratch/` |

**No payload is an input to a run.**  The generation dir and the emitted
payload are inputs to `analyzer score` alone (§7).

Doctrine: **holo3 places, the analyzer reads and refines per plane.**  A
capture without poses in the snapshot (the crosswise scans) enters through
a holo3 `--resume` first.  The analyzer never surveys or places a window;
it MAY refine an existing placement per plane within a bounded local search
(§4.6), including from the plane's own address word.

Live pages = pages carrying accepted placements ∩ manifest pages (never the
declared maximum; J's argv declares 100 pages, two exist).
`report.json capture_facts[].placements` is diag bookkeeping; live pages
come from snapshot placements.

**The union base** (`analyzer union-base`) is the incremental footing: a
run dir whose raster directories and `events.jsonl` are SYMLINKS to a base
run's, whose `report.json` and `argv` are copies, and whose `facts.npz` is
an exported snapshot carrying earlier passes' certificates.  It verifies
that every capture id the facts name is one `report.json` declares and
that every declared capture has rasters, because a snapshot holds POSES and
a pose against another capture's pixels yields evidence that looks fine and
means nothing.  Both checks refuse before writing.

## 3. Stage 0 — census and targeting (no pixels)

Per (page, ty, tx, stream) a ledger row with:

- `covered`: some accepted placement's page footprint (through
  `calibrate.window_page_cells`) intersects the tile.  Uncovered tiles get
  the verdict `uncovered` and are never targets.
- `certified` and `source`.
- `band`: computed per stream over COVERED columns only; a column with
  fewer than 12 covered tiles is unclassified; `dead` when the exact
  Clopper–Pearson upper bound (α = 0.05) of the certified fraction is below
  0.25; `marginal` when the fraction is below 0.75 otherwise; `live` at
  ≥ 0.75; classes by maximal runs; plus `band_any` = the cross-stream union
  (C, M and Y fail in the same columns on H).
- `neighbours_certified` (8-neighbourhood, this stream),
  `siblings_certified`, `known_cells_in_halo`, `n_discriminating_labels`
  (from furniture geometry and certified siblings, before pixels).
- `production_attempts` from events when present.
- `metadata_known`; `rank_report` and `rank_recomputed`.

Targets: `--targets residue` = covered ∧ uncertified (default) |
`band:dead` | `band:marginal` | `stream:C` | `list FILE` |
`open-after LEDGER[,LEDGER]` (the covered, uncertified keys after the union
of those ledgers and the run's own facts — what makes an incremental pass
targetable from ledgers not yet exported).  Order pinned (page, ty, tx,
stream) so attribution is reproducible.

## 4. Stage 1 — evidence per (tile-stream, lane, arm)

### 4.1 Reuse, not re-specification
`holo3/plugins/plane_k.py` already implements: the lane-scope mixing fit
(`fit_lane_mix`), the isolated-plane scores over raw/project/subtract
(`isolated_scores`), the plane-field delta (`field_delta_dots`), the blind
x-offset grid (`choose_offset`, ±2 dots step 0.25), and the calibrated rows
(`calibrated_rows`); `local_ctx.local_color_rows` re-fits the colour head
over a failed tile.  The analyzer CALLS these, re-deriving only a
footprint-sized `RegionWindow`.  §4 states the DELTA over the production
arm: the halo, the 2-D offset, field-and-offset together, the per-plane
word pose, the ablations, the branch-wise calibration, and the label
bookkeeping.  `choose_offset` and `calibrated_rows` themselves are NOT
called — window scope, x-only, and a site-parity objective where §4.8 needs
the search fold — but their grid and their two halves are reused.

### 4.2 Lanes
A lane is (capture, level) with `ppc` carried explicitly.  Default
`--lanes finest-covering`: per capture, the finest level whose accepted
placements cover at least `--cover-fraction` (RULED: 0.9) of the
footprint; when no level reaches it, the level with the largest non-zero
coverage is taken (partial coverage is evidence; the observed mask carries
the rest) — a tile never has zero lanes while any level sees it.  Measured
on sheet I: at 1.0, 176 of 1,961 tiles had no lane at all; at 0.9, none
(82 tiles use the largest-coverage fallback).  The fallback lives in
`inputs.finest_covering(..., fallback=True)`, so the census and the reader
agree by construction.

Sampling uses each PLACEMENT's own `pitch_px` (per-lane placement pitch
spread measured 1.2–1.7% on sheet I); the crop's filter aperture takes the
median over the footprint's OWNERS.  `--rung PPC` reproduces production's
shared-ppc pairing.  Level pitch = `placement.pitch_px / frame`, frame =
`intake.build_levels(dpi, row.pitch_in, shape_px)[level].scale`.

### 4.3 Footprint and ownership
Two objects: a lane-independent `TileFootprint` (page cells of the tile
plus a halo of `--halo-cells`, default 32 for Y and 16 for C/M, grown
adaptively until the label floor of §4.8 is met and recorded per row) and a
per-lane `LaneFootprint` (owned cells, owner placement per cell, pixel
points).  Ownership is frozen ONCE per lane from the reference arm
(`subtract+committed`) by `Placement.quality` then extent, and reused by
every arm and rule, so `n_observed` is identical across arms (asserted).
Support = `local_cells_yx` mapped through `window_page_cells` with `rot_k`
and `page_origin_yx`.

A wider halo (48/48/32) is the highest-yield single change measured on
sheet H's C sample (+3 certificates, −1) and is therefore a named PROFILE
(`wide-halo`, and inside `everything`), not a default: it lost a tile on
the sample it was chosen from.

### 4.4 Sampling
Per-channel crops opened ONCE per (lane, footprint) with a halo sized from
the registration bound (`ceil(bound_dots/cell_dots·pitch)` px plus the
anchor points halo), then sampled many times through the colour lane's own
per-channel path (`color_region_anchor.native_crop` → `filtered_rgb` →
`sample_rgb`; the K path's fused luma sampler is NOT used), `(N, 3)` RGB;
fill convention pinned to the crop median; a read outside the crop is a
REFUSAL the caller must check, never a fill; every sampler call takes the
LEVEL pitch.  Offsets are dots in (x, y) and convert through
`anchor.shifted_points(points, anchor.pose_linear(affine), delta_dots_xy /
cell_dots_of(row))` only; the +0.5 lives in exactly one place per path.
Per-cell deltas reach `read_rgb` as a per-owner 6-term affine
(`arms.affine_terms_for_delta`, exact for an affine delta, least squares
with a reported residual for the bilinear plane field), because `read_rgb`
takes a SCALAR offset.

**Delta frame (RULED 2026-09-03).**  The analyzer expresses every
registration delta in the PAGE frame (the printer's frame: the Y sinusoid
is a page-x phenomenon), i.e. against `pose_linear(compose_from_native
(native_affine, frame))`.  Production builds its dot deltas against the
WINDOW-LOCAL linear part (`PlaneField.delta_dots_xy`,
`plane_k.choose_offset`, the swim), and the two frames differ by the
placement's `rot_k` (a sign on both axes at rot_k 2; measured: 579 of sheet
I's 3,687 accepted placements are rot_k 2).  Every production delta
consumed by an arm is therefore rotated into the page frame by the
contributing placement's `rot_k` first (`to_page_frame(delta_dots_xy,
rot_k)`), and every delta the analyzer reports is page-frame.  MEASURED on
eight rot_k-2 C tiles of sheet I: the un-rotated production field delta is
2.6× worse (0.407 search-fold log loss) than the page-frame one (0.157),
with committed at 0.184.  A discriminating test on a rot_k-2 placement is
mandatory and lives in the suite.

### 4.5 Known-bit frame
For every footprint cell: three plane bits and a known mask from word/dust
furniture of every tile intersected, certified projections of every
certified (tile, stream) intersected EXCEPT the target key itself, and the
target stream's metadata cell when trusted.  Run-abort assertion: for the
target tile, `known[in_tile & cargo, target_plane].sum() == 0`, evaluated
AFTER the certified projections and BEFORE the metadata-cell injection (the
metadata cell is itself an in-tile cargo cell of the target plane); the
projection memo is keyed by the certificate MAPPING's identity as well as
the tile (a memo keyed by tile only carried a withheld certificate across
controls — caught and fixed in W1b review).  Splits: `regressors` (all
three planes known), `labels` (target plane known), `siblings` (both
siblings known), with `--siblings furniture` and `--labels furniture`
ablations.  Under `--withhold` (§8) the frame, PlaneField and
PooledColorCtx are all rebuilt without the withheld set.

### 4.6 Arms
Unmixing (target plane t; spectral is already plane-general; the mixing fit
follows a refusal ladder footprint → window → lane → region → page, first
accepted wins, `--mix-scope` pins it, region default on fragment sheets;
scope, reason and class counts recorded):
- `raw` (the channel t absorbs), `project` (GLS annihilating both siblings
  — also the paired control for `subtract`), `subtract` (per-cell sibling
  subtraction where both siblings known), `global` (= `subtract` with the
  lane-scope fit, memoised per lane), `head` (the analyzer's own per-plane
  8-state classifier with the two-of-three relaxation: cells with two
  planes known enter as regressors — the smallest production change yask
  named), `conditional` (per-cell classification against the spectral fit's
  per-sibling-state clusters; does not depend on `head`).

`lane_mix` pools a DETERMINISTIC 12-tile sample of the page (the target's
tile removed, memo keyed by it) rather than the whole page's regressors: a
page is 1,961 footprints per lane and stream, and the exhaustive page fit
(≈ 30 s per lane-stream) is available as a knob, not a default.

Registration (per footprint, per lane):
- `committed`;
- `field` (committed + the snapshot's plane field delta rotated into the
  page frame; records `field_applied` and collapses EXPLICITLY to
  `committed` when no field or no support — never a duplicate row;
  UNCONDITIONAL, `select_arm` arbitrates);
- `offset` (blind 2-D grid: x ±2 dots then y ±1 dot, step 0.25, separable
  = 26 evaluations; the y arm is pre-registered with a y-jitter null
  because production searches x only for a measured reason);
- `field+offset` (production never runs them together);
- `affine` (the swim's own `local_affine.search` with the correlation score
  — its objective touches the selection fold, so it is scored on a fold of
  its own);
- `smooth` (per-lane 1-D smoothing of the `offset` solutions over page x
  with SUPPORT NORMALISATION: num = smooth(w·offset), den = smooth(w),
  evaluated where den > 0 — never zero-padded into the sparse bands;
  Y only, and only live on large target sets);
- `word` (for C and M: hard-read the isolated plane at the committed pose,
  form states 3·bit at the 100 word sites, verify blind with
  `pilots.decode_color_word` (erasures allowed), then fit the tile's
  per-plane pose from the 120 sites — the one arm that separates "the C
  band is misregistered" from "above the floor".  Its REFUSAL on a
  non-decoding word is itself the measurement; 3 of 4 certified C tiles
  decode blind);
- `field2` / `field2c` (§13's page-field lead, built: see below).

**The page field, built** (`analyzer/field2.py`, record in
`FIELD2-2026-09-03.md`).  Per-plane registration is a smooth function of
position with small local deviations, so a page FIELD does not fight the
local physics the way page-scope context and pose do.  `fit_page_field`
takes each tile's own blind 2-D offset search (`arms._search_offset`,
called, not copied — with the tile's own key as the TARGET, so a certified
tile is read from its neighbours' labels and never from its own answer),
weights it by the x-sweep's CURVATURE rather than its gain (gain over
committed is zero both when the pose is already right and when the
objective is flat; curvature separates them:
`weight = n_labels × clip(curvature / 0.02 nats, 0, 1)`), and fits a
weighted degree-≤3 surface plus a support-normalised kernel-smoothed
residual at production's own bandwidth, with production's twicing pass and
clamp.  Twicing matters: a 2-tile kernel damps a 16-tile sinusoid by ~26%,
so a field without it under-reports exactly the amplitude the AltaLink
sinusoid is interesting for (planted-field median error 0.152 → 0.040
dots).

Two variants, and the ruling that separates them (Germano, 2026-09-03):
the field is a property of the PRINTED PAGE, so `field2` is ONE fit per
(page, plane) POOLED over every lane and rung, from FURNITURE anchors only
— invariant across cascade generations, blind by construction, no
certificate in it.  `field2c` is the certificate-anchored per-lane
variant, and is the expensive one.  MEASURED on 60 sheet-H residue tiles:
the pooled furniture field buys ~70–75% of `field2c`'s oracle gain on Y and
slightly more on C (Y R +0.0169 at +2.7 SE, cell error −0.63 pp at −3.1 SE)
with zero certificates in it — most of what the field knows is in the
paper, not in the neighbours' cargo.  On CERTIFICATES over those 60 tiles
it was a strict subset of the default (3 against 5) at better R and better
cell error, which is the honest reading: **an additive, cheap,
generation-invariant arm that costs 0 wrong, not shown to add on 60
tiles.**  Both are in the `everything` profiles, neither in `DEFAULT_ARMS`.

### 4.7 Calibration
Scores → PAVA on labels (`calibrate.window_scores(-score)` then
`fit_window_calibration`), LLR per cell clipped at the bound.

The two-population question (cleanable vs not, for `subtract`/`global`)
has an AMENDED answer, and the amendment is measured.  ONE map per branch
with its own standardisation, each refusing below `CAL_MIN_PER_CLASS` /
`CAL_MIN_HELDOUT`.  **A refused branch is not erased.**  Its cells are
priced by ONE map fitted over the footprint's union — the map
`branches="pooled"` would have used — and the row records `branch_fallback`
with that map's own class counts and acceptance.  Every branch that CAN fit
keeps its own map and its own standardisation, so the fallback only ever
replaces an LLR that would have been 0; when the union has no labels
either, the fallback refuses too and the cells stay erased.
`labels_cleanable_fraction` and `cargo_cleanable_fraction` are recorded and
a gap > 0.2 is flagged `extrapolating`.

The reason is measured: the split can put the WHOLE target tile in a branch
with no labels — the condition is a halo fully sibling-proven while the
target's own siblings are not — which erases a tile the score reads
perfectly well.  Sheet H page 0: 17 C, 18 M and 7 Y tiles, every C and M
one of them production-certified, 6 of the Y ones residue this instrument
is supposed to attack.  `(0, 34, 34, C)` had R = 0 and AUC = 0.5 on all
seven lanes with a perfectly good score; the fallback takes it to R 1.029,
AUC 0.9957, certified.  Production never has this failure:
`plane_k.calibrated_rows` fits one PAVA map per window with no split.
ADOPTED with no regression anywhere (sheet I 60/60 identical key sets;
sheet H M 20/20, Y 17/20 unchanged): `STARVED_FALLBACK = True` and
`DEFAULT_BRANCHES = "pooled"`.  `split-branches` is the profile that
reaches the unamended behaviour for a control run.

Context: production's variable (provisional ink over neighbours PRESENT in
the window), fitted PER FOOTPRINT, behind `apply_region_context`'s adoption
gate; the known-neighbour variant is a separate named arm `ctx-known`;
`n_ctx_eligible`, refusal reason and adopted are recorded.  Page-scope
pooling is NOT the lever: one 9-bin fit per (lane, page) over 130 tiles,
leave-one-tile-out, gives held-out select log loss 0.08171 against the
per-footprint fit's 0.08044 — the per-footprint fit is 1.6% BETTER.  The
two differ materially per cell (mean |ΔLLR| 0.251 nats over cargo, 0.71% of
cargo cells change sign) and swapping in the page-scope offsets certifies 3
of 11 missed keys byte-exact — which is the same yield as any comparable
perturbation, i.e. a re-roll at the waterfall edge, not a better
calibration.  Removing context entirely is catastrophic (mean R −0.06 to
−0.11 per tile, cell error +2 to +4 pp, 0/11 recovered).

`ctx_mode="local5"` is the neighbourhood option for LABEL-STARVED
footprints only (RULED: pose, page field and toner intensity are LOCAL, so
a fitted model takes a 5×5-tile neighbourhood, not the sheet).  It fits the
same 9-bin variable, solver and gate over the 5×5 tiles centred on the
target, then shrinks per bin toward the footprint's OWN fit
(`w_b = n_local_b / (n_local_b + n_footprint_b)`) and adopts the blend only
when it beats the footprint's own correction on the footprint's own
held-out labels.  With no neighbourhood context, or one the gate refuses,
it is BYTE-IDENTICAL to `production`.

### 4.8 Selection discipline
Three-way split of labels by an independent hash: fit / arm-search /
arm-selection.  Offset and affine searches use the search fold; arm choice
uses the selection fold, by a paired test on per-label log-loss differences
(adopt a non-default arm only when the paired mean difference exceeds 2
standard errors); blind selection is REFUSED below 40 minority-class
held-out discriminating labels, falling back to the pinned default arm and
recording `selection_refused`.

**DEFAULT ARM (RULED 2026-09-03): `subtract+offset` with production's
context** — production's own plane-arm composition.  The v0.2 pin
(`subtract+committed`, no context) is not it, and the measurement is the
reason: on five interior certified tiles per stream of sheet I,
`subtract+committed` without context re-derived C 3/5, M 5/5, Y 0/5; with
context C 5/5, M 5/5, Y 3/5; `subtract+offset` with context 5/5, 5/5, 5/5.
At parity 300 on sheet I the default arm gives C 100/100, M 99/100, Y
100/100 where the v0.2 default gives C 50, M 60, Y 25.  The blind offset
and the context correction are not optional extras; they are what makes the
plane read certify at all.

The `head` arm was once found reading its own labels (state hypotheses
restricted on the TARGET plane).  Fixed, and pinned by a test.

Reported: `heldout_logloss_search`, `heldout_logloss_select`, and a
nested-CV loss for the winner — never the minimum.

### 4.9 Output
Per (tile-stream, lane, arm): `llr_sequential` of length
`row.payload_cells` in production's SEQUENTIAL domain (un-permuted, STILL
DITHERED — byte-for-byte `_sequential_payload`'s contract) with an observed
mask; blind diagnostics (labels, discriminating labels, losses,
offset/affine, scope, refusals).  A row is emitted for every (tile-stream,
lane, arm) INCLUDING refusals.

## 5. Stage 2 — combination across lanes

Rules (a list; every rule's outcome is nested in the ledger row, plus a
"won by one rule / lost by another" table):
- `sum` (production; calibrated LLRs under independence),
- `best` (single best lane by selection-fold loss),
- `platt` (blind per-lane coefficients β_l ≥ 0 and one temperature fitted
  on the selection fold; refused below the label floor → `sum`),
- `corr` (equal-weight sum divided by (1 + (L−1)ρ)^½, ρ = mean pairwise
  correlation of per-lane errors at label cells, errors centred within
  label class — the print-frozen correction the multi-scan law demands),
- `normalized` (mean; control).

The v0.1 `weighted` and `agree` rules are deleted (unsound).  The
clipped-cell fraction per rule is reported (multi-lane agreement saturates
at ±20).  Lanes are de-duplicated by capture id; which level wins is pinned
(§4.2).  Pooled context offsets across a combination are the
coefficient-weighted SUM, not the mean (exact for every rule).

**Independent agreement (leg 4 of §0.2).**  Every gate-passing certificate
a key produces is collected with the PHYSICAL CAPTURES its combination
leaned on (`combine.contributing_captures` — a zero coefficient contributes
nothing, so `best` names one capture and `sum` names all).  Independence is
DISJOINT CAPTURES, not distinct rules: two rules over the same lanes read
the same paper once (§0.3).  Certificates that agree bit for bit on
disjoint captures CORROBORATE — `independent_agreement` on the row, a lower
bound by a smallest-sets-first greedy.  Certificates that DISAGREE are a
contradiction: both passed syndrome and CRC, so one is a false accept and
nothing blind can say which, so the key is REFUSED — no mint, no cascade,
`refusal = independent_certificates_disagree`, the claims kept on the row.

**Measured, and this is the honest half.**  On `H7-pass3` (508 certified
rows) 211 — 41.5% — had two or more RULES certify, which is the
contradiction check's live population; on `H7-pass5` (40 certified) 11.
But 0 of 508 and 0 of 40 carry a pair on DISJOINT captures, structurally:
of the five rules only `best` restricts to one capture and the other four
use all seven, so `best`'s set is always a subset.  The contradiction half
is live now over 41.5% of certified rows; the corroboration half is built,
tested, correct and unexercisable by the current rule set.  Making it bite
needs a rule that certifies on a disjoint capture subset (§13).

## 6. Stage 3 — the decoder ladder

All rungs read the combined sequential vector and go through ONE analyzer
helper (`mother.py`): un-dither once, scatter through
`tile_codec.transmitted_positions`, set `[active, k) = −∞`, inject the
metadata bit at info index 0 when trusted, and return (hard, syndrome
vector, unsat count, posterior Ltot) from `ldpc._bp_loop` called with the
INTERNAL sign.  Posterior identity: `Ltot = clip(llr) [±∞→±LLR_KNOWN] +
extrinsic`; reliability is `|Ltot|`, never `|extrinsic|`.  Iteration
accounting states the two-pass 2× explicitly.  Bits-wrong columns carry
explicit denominators (mother 4096 / transmitted 3976 / active 3400 / user
3368).

| rung | what | status | knobs |
|---|---|---|---|
| L0 `prod60` | `cmy8_decode_stream` at 60 (parity baseline, bit-exact production); a second `mother.bp` at the same knobs supplies unsat/posterior and the exposure charge, and must agree with production's syndrome/user bits (asserted) | built; the workhorse (254 of sheet H's 508) | — |
| L1 `prod150` | production heavy, 150 | built | — |
| L2 `bp` | the analyzer's BP variants: sum-product-only N iterations; damped min-sum (λ) and damped+offset (λ, β); layered schedule | built; second workhorse (damped 151 + layered 65 of 508) | N, λ, β, schedule |
| L4 `flip` | entry = the fewest-unsat L2 state; blind gate `unsat_at_exit ≤ 12`; then hypotheses at ±LLR_KNOWN on the least reliable variables incident to unsatisfied checks — singles over 24, then pairs over 8 — each followed by a short BP, every candidate gated syndrome→CRC and charged per distinct codeword | BUILT (W4) and mints, thinly: 11/59 on a synthetic near-codeword battery where L0–L2 got 0/59, and 2 on sheet H | m, m′ |
| L3 `ctx-iterate` | APPLY-mode (RULED 2026-09-03): it does NOT refit.  A refit inside the tile has no labels by construction (the target key's cargo is excluded), so L3 as first built refused on every real target.  It applies the footprint's production-context offsets — fitted on halo labels whose neighbours are known — to in-tile cells whose neighbour bins come from the decoder's EXTRINSIC: the bins move, the offsets do not.  The fed-back prior is clipped exactly as `tile_codec.cmy7_iterated_decode` does; ≤ 3 rounds; abort when mean \|LLR\| grows without reducing unsatisfied checks | built; runs (73 keys on sheet I's Q2, 327/340 sum rows carry pooled offsets) and has certified nothing yet | rounds |
| L7 `erase` | L7a: down-weight lanes' disagreeing cells (factor a knob), cap erasures at n−k−margin taking least-agreeing first, from the per-cell lane-sign agreement vector on `Combined`; L7b: blind contiguous-run erasure; the below-floor refusal reproduced as an explicit outcome; `n_erased`, `n_disagreeing`, `bank_active_bits` recorded | built; needs ≥ 2 lanes (refuses under `best`) and has certified nothing yet | threshold, margin |
| L5 `osd` | reliability = \|Ltot\| with shortened/known positions at ±LLR_KNOWN; ascending sort; greedy bit-packed GE admitting a column only when it raises the rank until n−k pivots; [I \| P]; order-0/1/2 candidates by XOR of P columns; rank by soft weight; explicit syndrome check on every candidate; top-L to the CRC | DEFERRED (§6.1) | order, m″, L |
| L6 `perturb` | restarts with σ as a fraction of the tile's median \|L\|, perturbing only low-\|Ltot\| positions, seeded | DEFERRED (§6.1) | N, σ |

Default rung order: `L0, L1, L2, L4, L3, L7`.  L4 sits after L2 (it enters
at the best posterior L2 produced) and before L3; it is BLINDLY gated on
the unsatisfied-check count, so a tile outside the few-error regime pays
one comparison for it.

L2's default variants are MEASURED, not pinned by taste: a synthetic
waterfall sweep (`analyzer/sweeps/l2_variants.py`) pinned
`DEFAULT_L2_VARIANTS` to damped@300 λ=0.5 then layered@300 λ=0.7 (greedy
union 72/200 against production's 69/200).  The variants only move
certificates at the waterfall edge — which is where the real residue's
marginal tiles sit.

**Verdict rule.**  A gate-passing certificate from a DIRECT rung
(L0/L1/L2/L3/L7) is `certified` — one proposal, the same exposure class as
production.  Only LIST rungs (L4/L5/L6) are quarantined as
`certified_list`, and they mint, cascade, close and export like any other
(RULED 2026-09-03).

### 6.1 The deferral rule, and what the histograms said

L5/L6 are deferred behind the blind `unsat_at_exit` histogram every pass
publishes, and the rule is "does mass sit at ≤ ~4 errors inside the most
reliable independent positions", corrected from "tens vs hundreds" to
"0 vs ≥ 50".

The histogram DECIDED, twice, differently, and both answers are kept:

- **Sheet I is bimodal.**  1,595 rung outcomes: unsat 0 → 590, 1–49 → 0,
  50–99 → 3, ≥ 100 → 1,002.  A few-error rung has nothing to work on.  The
  deferral holds on paper, not just in simulation.
- **Sheet H is not.**  7,369 outcomes with 222 exits at 5–9 and 234 at
  10–49.  That shoulder is what L4 was built for, and L4 does mint there.

So L4 is BUILT and L5/L6 stay deferred: the shoulder H shows is inside
L4's flip reach, and nothing measured yet asks for order-2 ordered-statistics
decoding or seeded restarts.  L4's pair sweep (21–190 s per gated tile) is
also the real dominant cost term of the deferred rungs, which is a second
reason not to build them speculatively.

### 6.2 The re-roll, and the profiles

**The re-roll** (`AnalyzerConfig.reroll`, default ON).  After the SELECTED
arm's ladder fails for a key, `combine.reroll_sets` hands back one evidence
set per REMAINING arm — evidence the selection already computed and threw
away — and each set gets its own combination per rule and its own
`reroll_rungs`.  Every candidate is gated syndrome→CRC and charged to the
same exposure; the select fold is not consulted again, so this is not a
second arm choice, it is more rolls of the same dice.  The winning arm is
recorded as `certifying_arm = reroll:<arm>` and the rung rows are keyed
`<rule>|reroll:<arm>`.

The reason is the C parity diagnosis (`GAPS-2026-09-03.md`): the C tiles
production had to work hardest for sit in the BP waterfall at mean
R ≈ 0.80–0.93 where certification is a coin flip, and production won them
by throwing six tools and hundreds of attempts at each (one took 362
recorded attempts).  Every factor that "recovers" such a tile does so by
moving R by one or two hundredths.  The gap is an ATTEMPT-COUNT gap, not a
capability gap.  Measured: re-rolling at L0/L1 alone recovered nothing on
the 8 keys the adopted defaults still miss, because L0/L1 on a different
arm is the same coin flip; adding L2 to the re-roll turned one of them.
`reroll_rungs` defaults to `("L0", "L1")` and the `everything` profiles
carry `("L0", "L1", "L2")`.  The re-roll is OFF for
`controls.parity_sample` (RULED): a parity number measures what ONE
configuration re-derives.  On sheet H's pass 3 the re-roll minted ~240 of
508 certificates.

**The profiles, and the union ruling.**  RULED 2026-09-03 (Germano, "why
not all of the above?"): on a residue pass nothing an arm, halo, rule or
rung does can mint a wrong certificate — the gate decides — so the yield
configuration is the UNION.  `everything` = every arm on every lane
(including the pooled `field2` arms, which are generation-invariant and
need no refit), all four rules, the full ladder, halo 48/48/32, re-roll at
L0–L2.  `everything+field2` adds the certificate-anchored `field2c` arms,
the expensive ones (a refit per lane per generation), behind their own name
for that reason.  Cost is about 4× the default; exposure stays a stated
number.  `wide-halo`, `battery` and `split-branches` are the narrower
named configurations.  A profile records itself in the ledger header as
`knobs_from = "profile:<name>"`.

### 6a. The close

After the ladder, production ∪ analyzer certificates go to
`holo3.format.close.close_volume`; status, k_total, symbols used, metadata
rank and the recovered payload sha are reported as a volume-level ledger
row, and the recovered bytes are written to `<out>/payload.bin`.

**THE VERDICT IS THE ENVELOPE (RULED 2026-09-04).**  The payload envelope
is `{sha256}{len:4B BE}{data}`, so a volume that closes has already checked
its contents against a digest the EMITTER wrote inside the volume;
`close_volume` reports `verified` exactly when that check passed.  No
generation manifest is consulted — the analyzer opens no payload during a
run — and the `truth=` argument and the `solved_unverified` status are
gone.  Writing `payload.bin` out is what makes an offline `analyzer score`
possible against a payload nobody handed the instrument.

**The fountain consistency check** (leg 3 of §0.2, default ON).  Above K
the fountain is OVER-DETERMINED, so the symbols the close did not need are
a parity check on the ones it used.  `close.consistency` solves the source
block exactly as `close_volume` does and RE-ENCODES every input symbol from
that solution through holo3's own generator rows — systematic rows read
straight off the source, repair rows as the XOR of the source rows their
keystream-drawn row selects.  It calls `fmt_close._symbol_index` /
`_tile_counter` / `_volume_code` / `_pooled_volume_code` rather than
respelling the ESI mapping, so a format fork cannot creep in through a
second spelling; the items it re-encodes are built through
`code.tile_slots` exactly as the decoder builds its own, so an uneven cmy8
triplet (column groups, 2026-09-04) is checked per (block, group) over the
symbol columns that group occupies, and a uniform row is the one-group
case of the same arithmetic.  With `have`
symbols and K source rows, `have − K` comparisons are genuinely free
evidence; a clean check with `n_redundant` large is the TRUTH-FREE
statement that every certificate the close consumed is right.

**Why this is not redundant with the close, MEASURED.**
`fountain._ge_solve_gf2` eliminates rows past the rank to zero on the LEFT
and never re-reads their right-hand sides, so a contradictory system
returns a solution at full rank and raises nothing; `Decoder._solve_block`
additionally short-circuits when all k systematic rows are present and
never consults a repair row.  Neither is a defect — the production caller
has no redundancy to spend and the CRC is its gate — but the consequence
is: **a poisoned REPAIR symbol leaves the close VERIFIED**, envelope
passing and payload byte-exact, while the volume carries a certificate that
cannot have come from it.  The close never reads that symbol.  This check
does, in 0.30 s over sheet I's 5,883.  Both holo3 behaviours are pinned by
tests, not asserted in prose.

**Localization** (`close --localize`) turns an inconsistent system into
NAMED keys.  Two signatures decided by the size of the disagreeing set:
outside the basis each poisoned symbol accuses itself; inside it every
residual is the SAME error pattern, and AND-reducing the disagreeing
generator rows names the poisoned column with
`false_candidate_bound = k · 2^−|D|` stated.  Either way the error pattern
is known, so the symbol is CORRECTED (`observed ^ e`) and the correction is
re-checked against the source the SURVIVORS solve.  Bounded at
`max_rounds + 1` solves (default 5), reported in `n_solves` and `seconds`;
a clean re-check with fewer than `LOCALIZE_MIN_REDUNDANCY` comparisons left
is reported `redundancy_exhausted`, never `localized`.

Pre-registered success criteria of a sheet-H wave were: (a) a decisive
dead-band converse (R < 1 with confidence) or its refutation; (b) the
unmeasured C-band measurement; (c) a certificate count with leave-one-out
attribution.  A close was welcome and not pre-registered.

### 6b. Fixed point

After each pass, newly certified keys are folded into the frame's
certificate set and every residue tile in their 8-neighbourhood plus the
other two streams of the same tile is re-targeted; iterate until no new
certificate.  Each certificate carries `generation` and `predecessors`;
generation 0 is the honest production-frame-only number and the cascade is
measured, not assumed.  `predecessors` is a SUPERSET — it includes failed
re-attack triggers.

The re-targeting must include a key's OWN open rows: an early version
excluded every already-attempted key, so generation 0 never re-attacked its
own, and the whole cascade collapsed to one generation.  A re-attack now
REPLACES the row, and `attempts` counts.  The fix is worth measuring:
sheet I's first-run residue went 279/340 → 331/340 (generations
279/44/8/…, four run), and sheet H's pass 3 ran 8 generations
(274/120/48/23/12/10/8/13) and was still yielding at the cap.

## 7. Offline scoring (`analyzer score`)

The one door that opens a payload, and it decodes nothing.  `--payload` may
be the EMITTED payload or one a close recovered.  With `--gt-dir` the
manifest sha-gates it and the emitted per-cell field enables the
cell-level splits; without one, the user bits are reconstructed from the
bytes alone and the two field gates report `skipped` rather than pretending
they ran.

Three validation gates when a generation dir is given: every snapshot
certificate matches its GT user bits; the projection of GT user bits
through `color_sites.certified_projection` matches the emitted field on a
stratified sample; the field is block-constant per cell.  Failure stops the
scoring.  GT user bits come from `measure.crop_parity._gt.reconstruct
(format_ref, payload, n_pages)` with `n_pages = max(live page) + 1`
(refuse, don't allocate, above a stated size).

What it produces:

- **Every certificate verified bit-for-bit**, with a mismatch reported as
  `wrong` (direct rung) or `false_accept` (list rung), every disagreeing
  key named in `score.md`, and CLI exit 2 on any of them.
- Per rung, bits wrong at exit recomputed from the ledger's packed hard
  vectors with all four denominators, plus the histogram §6.1's deferral
  rule reads.
- With `--run-dir`: R with its bootstrap bound and the empirical waterfall
  P(certify | R) per stream and rung (R50, R05); cell error at the
  calibrated MAP decision and at the median threshold; d′ =
  (μ₁−μ₀)/√(½(σ₀²+σ₁²)) with ROC AUC beside it, on cargo cells only;
  splits by TRUE sibling state (emitted field) and by context bin; capture
  agreement on wrong cells; the bits-wrong map per plane.  The evidence is
  recomputed BLIND through the same `arms.evidence_for` the run called,
  with ONE frame for every row (the run's certificates plus every
  certificate the ledgers minted) where the run used each key's own
  generation — the report says so in `evidence_frame` rather than leaving a
  reader to guess.
- Cell-level splits are POOLED BY CELL COUNT per stream, never as a mean of
  per-lane rates, and a refused lane never enters a split.

The reader STREAMS (`read_header` + `iter_rows`): materialising rows cost
26 GB of RSS before it was killed, because sheet H's passes are 2.6–5.8 GB
of JSON each.  Streaming, the same five score at ~0.5 GB.

The old `oracle-permutation` control — decode twice, truth real against
truth permuted, and demand byte-identical blind columns — is retired.
Under §0.1 a run has no truth in the room, so the claim it defended is
structural; what is left to test is that the scorer's blind columns are the
ledger's own, and that is a test of `analyzer.score`.  Measured
equivalently: the same ledger scored against a payload with one byte
flipped gives 3 WRONG, named, bits wrong 128/8/8 — and every blind column
identical between the two runs.

## 8. Controls and parity

- **Null arm** `N0`: evidence of the neighbour ≥ 8 tiles away (beyond the
  registration period) at this tile's address; climbs the FULL ladder at
  the same knobs; any certificate is a failure.  Its consults and predicted
  false count are reported beside the live totals with the power
  denominator (trials on tiles that certify truthfully).
- **Frame null**: correct pixels and address, certified frame
  contributions taken from another tile; must certify nothing extra; run on
  tiles that DO re-derive, so a zero has power.
- **Positive control**: withheld set = the run's own late mints from
  `events.jsonl` certified `TileOutcome` keys (`--withhold-run-mints`; an
  empty set is a hard error), or `--withhold-keys FILE`, or the coarse
  `--withhold-source tiles/planek150,…` with the REAL source strings.
  Under withholding the frame, PlaneField and PooledColorCtx are rebuilt
  without the withheld set (or refused → `committed`, no pooled head);
  placements stay contaminated (bounded by a `committed`-only registration
  run); `control_inputs_refit` lists what was cleaned.  Leave-one-out,
  stratified by source and band, Clopper–Pearson intervals, pre-registered
  proportional bar (≥ 70% of withheld keys in each stratum with ≥ 20 keys).
- **Stratified holdout** (`--holdout-stratified`): production certificates
  withheld by (stream, source) in a deterministic seeded sample, all at
  once, attacked by the default battery in ONE pass with no cascade.
  Recovered fraction per (stream, source, band) with exact intervals, and
  the misses' `miss_min_unsat_distribution` — unsat is blind and answers
  the question the retired R distribution asked.
- **Parity sample**: ≥ 100 production-certified tiles per stream,
  stratified by band, the DEFAULT arm at L0/L1, `sum` only, re-roll OFF.
  The re-derivation rate is THE acceptance gate (≥ 80% per stream).

**What replaced the GT comparison in every control** is truth-free and
stronger: a re-derived certificate must equal PRODUCTION's own bits for
that key (`_matches_production`, reported as
`n_disagreeing_with_production`; a disagreement fails the control).  That
is leg 4 of §0.2 — two independent paths certifying one tile bit-for-bit —
and it needs no payload.

**Reading a parity number.**  A rate below the bar is not automatically a
capability failure.  Sheet H's 60-tile C sample: default 49/60 (81.7%),
adopted defaults 52/60, the whole battery 56/60, and every recovery is an R
move of +0.005 to +0.018.  The bar is measuring how many re-rolls one
configuration gets, not whether the analyzer can read the C plane (§6.2).
Sheet I is 100/100/100 and sheet H's M is 20/20 because those planes are
not in the waterfall regime.

## 9. The ledger

JSON-lines, one row per (page, ty, tx, stream) with nested per-(lane, arm)
and per-rule/per-rung records; a header with seed, knobs, provenance
(`targets_from`, `knobs_from`, non-blind flag, `format_ref_override`),
run-level exposure, `n_corroborated` and `n_contradictions`.

A row carries the packed exit hard vector by default
(`keep_hard`, base64 in `detail.hard_packed_b64`, 683 chars against hex's
1,024).  With the certified user bits it is everything the offline scorer
needs that only the run can produce.  `LedgerRow.diag` is blind bookkeeping
(seconds, lanes, refusal, attempts) — it was called `oracle` and held the
GT side table until the 2026-09-04 ruling; the name went with the scores.

The Markdown summary carries: certificates by rule and by rung as BOTH
first-success marginals (order pinned) and leave-one-out, with the
order-free union count as the headline — leave-one-out over RULES is EXACT
(`all_rules` runs every rule's ladder even after one certifies), over RUNGS
it is a LOWER BOUND (the ladder stops at the first certificate);
stream×band tables with `corroborated` / `contradicted`; an
`## Independent agreement` section with the contradictions in full; the
BLIND unsat histogram; exposure live and null; controls; parity; the close
row.  Two PNGs per plane.  Bits wrong, R and the waterfall are NOT here —
the summary points the reader at `analyzer score` by name.

## 10. Cost and memory

One 3-channel 96×96 footprint read ≈ 10 ms (pitch 8) to 39 ms (pitch 16)
warm; the default battery is ~150 samples per (tile, lane) from ONE crop;
about 1.0 s per (key, lane) for the full battery.

`snapshot.read` peaks at ~6.5 GB RSS on the sheet-I snapshot and ~12 GB on
H, plus page cache for the native lanes.  The analyzer loads the snapshot
once per process, threads share it, and it MUST NOT run beside a holo3
decode.  Memos are per-thread where `head` lands.

Measured wall/peak on sheet H (1,000 residue tile-streams, seven captures,
8 workers): a three-rung pass 59 min / 19 GB; `--profile everything` 3.8 h
/ 44.6 GB; `everything+field2` 3.5 h / 48.6 GB; the incremental pass on a
union base 3.6 h / 51.3 GB.  `union-base` 4.7 s / 11.8 GB; `close
--localize` 6.4 s / 11.8 GB (all of it the snapshot read; the consistency
check itself is 0.66 s over 5,437 symbols); `export-facts` 75 s / 8.6 GB;
`score` over five ledgers (18 GB of JSON) 183 s / 0.52 GB.  Full operator
table in `README.md` §3.

One known cost trap: `field2_fit_workers` defaults to 1, so inside a
`fixedpoint` run the lazy pooled fit blocks the first target that needs it
for ~6 minutes (Y, 22 lanes) while other workers wait on its key lock.  A
battery run should pass the knob, or the driver should pre-fit.

## 11. Non-goals

No survey, no window placement, no new pose search beyond per-plane local
refits of existing placements; no production row; no change to holo3 or
src/holo; no sim stimuli; no caps that reduce yield (the exposure bound is
a correctness rule, not a budget); cmy7 out of scope.

## 12. Ideas from the dialogue, and where each lives

| idea | where |
|---|---|
| whole plane as K, C/M self-calibrating | §4.6 `global`, `word`; §13 plane view; §1 corrected label arithmetic |
| dust/word for calibration and registration; certified neighbours as labels/anchors | §4.5 frame, §4.6 `offset`/`affine`/`word` |
| metadata bit | §1 producer, §6 injection, §4.5 known cell |
| per-failed-cell analyzer | §6 ladder + §7 |
| rank / fountain relations | §1 (rank read from report + cross-check; relations dropped) |
| weighted union, "union can lose a tile" | §5 `platt`, `corr`, `best`; won/lost table |
| unsatisfied-check histogram | §6.1 (blind, gates L4–L6), §9 |
| bit-guessing, OSD, perturbation, CRC-selected lists + exposure | §6 L4 (built) / L5, L6 (deferred), §0.3 exposure bound |
| ctx-iterate | §6 L3 (apply mode) |
| erasure marking | §6 L7a/L7b |
| wrong cells by sibling state/context/position; capture agreement | §7 |
| conditional classification | §4.6 `conditional` |
| composite-pose prior | §4.6 `smooth` (support-normalised) |
| page field per plane | §4.6 `field2`/`field2c` |
| crosswise / 4800 strips | §2 doctrine (resume first) |
| controls | §8 |
| stop rule | §1 R statistic, §3 targets, §6.1 deferral, §6a criteria |
| cascade | §6b |
| more BP iterations / decoder variants | §6 L2 |
| the close, and proving it | §6a |
| a poisoned symbol | §6a consistency + localize |
| two paths, one tile | §5 independent agreement, §8 parity |

## 13. Further leads — the pile-on list

Rulings that bound every lead: (a) **locality** — pose, page field and
toner intensity are local, so any fitted model takes a 5×5-tile
neighbourhood by default (≈ 100k certified cells at 4800 dpi), with the
lane-page fit as a shrinkage PRIOR chosen per tile on the selection fold,
never as the model; sheet-wide fits only for what is sheet-wide (the
scanner's chromatic aberration field, its blur).  (b) **The truth line** —
H's payload is a counting pattern, so its user bits are predictable; that
is truth, and under §0.1 it does not enter a run at all.  (c) Every lead
enters as an arm or rung behind the same syndrome+CRC gate and the same
exposure ledger, and is judged by certificates on a blind battery before it
becomes a default.

| lead | mechanism | scope | deciding measurement (blind) | status |
|---|---|---|---|---|
| **Re-roll** | after the selected arm fails, decode the other arms' evidence too; every candidate gated and charged | per tile | certificates on the parity misses; exposure | BUILT, default ON; minted ~240 of sheet H's 508 (§6.2) |
| **Pooled-branch fallback** | never zero a tile whose calibration branch has no labels | per tile | the 0.9% C/M and 6/7 Y tiles with R = 0 | BUILT and ADOPTED as default (§4.7); no regression on I or H |
| **Page field (`field2`)** | a low-order surface plus a support-normalised smoothed residual from blind per-tile offsets; pooled per (page, plane) over every lane from FURNITURE anchors only, so it is certificate-free and generation-invariant; `field2c` = the certificate-anchored per-lane variant | page surface + 5×5 residual | R and cell error against `subtract+offset`; certificates | BUILT (§4.6, `FIELD2-2026-09-03.md`); real oracle gain, NOT shown to add certificates on 60 tiles; in the `everything` profiles, not in `DEFAULT_ARMS` |
| **Local5 context** | the 9-bin fit over the 5×5 neighbourhood with shrinkage to the footprint's own fit — for label-starved bands only | 5×5 tiles | held-out loss where the footprint refuses | BUILT as `ctx_mode="local5"`, not default, no CLI flag |
| **Whole-page plane view** | run holo3's own placement/refine/swim/region-ctx/union/cascade on an emitted unmixed C plane (K-shaped page, cmy8 stream codec) | holo3's own scopes | parity vs production C; the col 30–31 band | BUILT and RUN — a measured negative: 1,632 C certified from scratch, **zero plane-view-only certificates**, 122 production C tiles missed, cols 30–31 0/0.  The whole receiver on the isolated C plane reaches a strict SUBSET of production ∪ analyzer |
| **Seeded plane views** | seed a plane view with every known certificate of that stream so holo3's K cascade works the residue only; `--holo3-option --max-pages 1` | holo3's own | seeded vs unseeded C view: residue take, wall time | owed; both levers supported by the harness, and the unseeded run's cold-placement endgame (787 `cold_rest` windows, 12–15 h projected) is the reason |
| **A disjoint-capture rule** | a second `best` over the complement of the first certificate's captures, or a re-roll restricted to lanes it did not use — the only way the corroboration half of §5 can ever fire | per tile | `independent_agreement` ≥ 2 on real rows; certificates | proposed, unbuilt; a yield-and-evidence proposal, not a repair |
| **Temperature ladder** | scale the combined LLR by t ∈ [0.6, 1.4] chosen for the fewest unsatisfied checks (multi-lane sums on a print-frozen channel are over-confident) | per tile | unsat at exit vs t; certificates | untried, cheap |
| **Pose list decoding** | decode at the top-3 offsets of the search, not only the best held-out one | per tile | 3 CRC consults per tile; certificates | untried, cheap |
| **Patch discriminant** ("learn the detector") | a per-plane, per-context linear discriminant over the raw 16×16-px cell patch, trained on certified cells — the spatial twin of the unmixing gain | 5×5 tiles | AUC vs the box mean on H marginal Y, labels from certificates only | untried, the largest untried lever |
| **Per-channel registration** | sample R, G, B at their own positions (e033 measured the Canon R−G lateral CA as an odd-symmetric field) | sheet-wide field, per-tile offset | offset sweep per channel on labels | untried |
| **Aperture / deconvolution** | the 0.7-cell box aperture was tuned for K at 8 px/cell; a Gaussian or smaller aperture at 16 px/cell, or a Wiener deconvolution from the sheet's own certified edges (MTF10 ≈ 860 dpi) | aperture global, PSF sheet-wide | label-scored sweep | untried |
| **Full neighbour-interaction context** | 256-context (or 3×3 linear) toner model instead of the 9-bin ink count; unknown neighbours from the decoder's extrinsic (turbo) | 5×5 tiles + page prior | held-out loss vs the 9-bin fit | untried |
| **Joint three-stream turbo** | where C and M are open too, feed their extrinsic posteriors as soft siblings into Y's unmixing and iterate the three decodes (H: 147 tiles with C and Y both open) | per tile | certificates on the C∧Y-open set | untried |
| **Neighbourhood colour head** | the 8-state mixture fitted on 5×5 tiles with per-context means, shrunk to a lane-page prior — the head that does not starve in dead bands | 5×5 tiles | head parity on the dead-band edge tiles | untried |
| **Defect map → erasures** | oracle-guided discovery of clustered wrong cells (fibres, splatter), then a BLIND anomaly detector against the local model marks them erased | per tile | clustering statistic; L7 certificates | untried; would give L7 the producer it still lacks |
| **Targeted evidence** | scans where R sits at 0.95–1.0 (several hundred H tiles): real crosswise sheets, 4800 strips of the marginal regions, 16-bit linear output for the faint Y channel | — | per-lane marginal value in the ledger | open; the Hend snapshot's six extra lanes are the nearest instance |
| **M's page field** | `field2` is fitted for C and Y; M is unfitted and `head+field2+offset` untested | page | same as `field2` | owed |
| **Fountain relations** | none — dense repair rows, no low-weight relations (§1) | — | — | dead |
