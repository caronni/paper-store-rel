# analyzer — the impossible-endrun analyzer (design v0.5, 2026-09-12)

v0.3 folded into the body every ruling and every measured finding the
build produced: the six-lens adversarial review of 2026-09-03
(`analyzer/REVIEW-2026-09-03.md`), the W1–W7 build waves, the sheet-I and
sheet-H runs, and the 2026-09-04 separation ruling that took ground truth
out of the run.  **v0.4 adds W8, the third-layer C line** — the patch
discriminant and its family, per-sibling-state calibration and context,
the `platt-state` rule, the `L7c` and `L3f` rungs, the pure path, and the
self-discovery ruling that turned the family's knobs into choices a run
makes for itself.  §14 is that wave's own section; §4.6, §4.7, §4.8, §5,
§6 and §13 carry it where it belongs.  There are no appended notes: what
a section says is what is built.  The dated, run-by-run record lives in
`PLAN.md` §6; the standalone measurement records are
`GAPS-2026-09-03.md` (the C parity gap), `FIELD2-2026-09-03.md` (the page
field) and `MEASUREMENTS-2026-09-06-C-THIRD-LAYER.md` (the third layer),
and `APPROACHES-2026-09-06.md` is W8's enumeration, build spec and run
record.  The operator's manual is `README.md`.  **v0.5 (2026-09-12)
carries the PAGE-FIELD line** (`docs/PAGE-FIELD-DESIGN.md` v0.6, merged
to main the same day): the production field is one fact per (page,
plane) in page axes, read as such (§4.4, §15); the `smooth` arm and
`field2c` are retired (§4.6); the withholding controls refuse the
production field arms by construction (§8).  The workplan is
`analyzer/PAGE-FIELD-PLAN.md` v0.2; where this document names a phase of
it (A1, A2, A3), that phase is the one that lands the mechanism.

A dedicated, standalone research instrument aimed at the residue of a
finished holo3 decode: every tile-stream the production receiver left
uncertified.  It is NOT part of holo3 production, adds no rows, changes no
tree under `src/holo/receiver/` or `src/holo/`, and exists to answer one question per
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
whose findings this design generalizes), `src/holo/receiver/plugins/plane_k.py` (the
production per-tile plane arm this design REUSES), `src/holo/receiver/docs/SCHEDULE.md`.

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
  Two files are PRE-EXISTING exceptions — `arms.py` and `field2.py`, both
  over it before W8 opened — and only DISPATCH may land in them, never new
  mechanism; W8's mechanism lives in `patch.py`, `patchspec.py`, `patchgrid.py`,
  `patchcache.py`, `patchfit.py`, `patchlocal.py`, `autoknobs.py`,
  `statecal.py`, `pure.py` and `refit.py` for exactly that reason.  When a
  module does cross the cap, the move is a MOVE — the names are re-exported
  from where they lived, so no caller and no test changes (`patchgrid`,
  `patchfit`, `patchcache`, `patchspec` are all that).

## 1. What the record says, and the corrected assumptions

Sheet H (`L:c2-cmy8-r0850-p120-x1@3392x2368`, AltaLink, seven Canon
captures, machine 4 endrun as of 2026-09-02): 4,883 of 5,883 tile-streams
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

- cmy8: one LDPC frame per tile-stream; n = 4096, info block k with `p`
  shortened positions at `[k−p, k)`, user bits = k − 32 − p (p = 120 at
  the printed density, 3,368 at r0850); `user_bits[0]` is the metadata
  bit, `user_bits[1:]` the fountain symbol; CRC-32 at
  `[active−32, active)`.  A synthetic r0850 frame
  certifies at 3% hard cell error, not 6% (rate 0.855 against bi-AWGN
  capacity ≈ 0.80 at 6%).
- Payload cells: `row.payload_cells` = 4096 − p, 3,976 at the printed
  p120, per tile, permuted by
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
  `holo.receiver.format.identity.resolve_format_ref`, must keep the `RunOpen`'s
  pitch, and is recorded in the provenance as `format_ref_override
  {run_open, used}`.  Sheet J's run dirs MUST be analyzed with
  `--format-ref L:c2-cmy8-r0547@53x37`: the canonical-identity merge mints
  a different seed for the same display id, and the bare id descrambles the
  sheet to coin flips without raising.

## 2. Inputs and their roles

| input | role | source |
|---|---|---|
| run dir `facts.npz` | a flat fact tuple: Placement (rot_k, native_affine, pitch_px in NATIVE px, page_origin_yx, `local_cells_yx` = support in window-local coords, `quality`, and since holo3's D4 guard of 2026-09-04 `stood_affines` = the geometries the window already stood at), Certificate (user bits, `source` = `tiles/<stage>`), PlaneField, PooledColorCtx, LatticeSeed, Window, CaptureSurvey | `holo.receiver.snapshot.read` |
| run dir `report.json` | capture identity, dpi, channels, `levels_ppc`, shape, pages, the close block incl. rank | parsed |
| run dir `events.jsonl` | `RunOpen` (format ref, pitch); `TileOutcome` certified keys (the withhold set for the positive control) — REQUIRED for `controls`, optional otherwise | streamed |
| run dir `argv` | provenance string only | — |
| run dir `<capture12>/l{NN}-{r,g,b}.npy` | per-lane plane rasters (mmap) | holo3 intake products; `analyzer mirror` rebuilds them locally, byte-identical |
| capture TIFFs | native pixels only if a level is missing (`tifffile.memmap` RGB views) | the evidence archive (never in git) |

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
`src/holo/receiver/plugins/plane_k.py` already implements: the lane-scope mixing fit
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
LEVEL pitch.  Offsets are dots in (x, y) and convert through the
receiver's one mapping, `page_map.raster_points(points,
anchor.pose_linear(affine), delta_dots_xy, cell_dots_of(row))`, only (A1;
`anchor.shifted_points` was the same call under a spelling the receiver
kept for this reader alone); the +0.5 lives in exactly one place per path.
Per-cell deltas reach `read_rgb` as a per-owner 6-term affine
(`arms.affine_terms_for_delta`, exact for an affine delta, least squares
with a reported residual for the bilinear plane field), because `read_rgb`
takes a SCALAR offset.

**Delta frame (RULED 2026-09-03; RESTATED 2026-09-12).**  The analyzer
expresses every registration delta in the PAGE frame (the printer's
frame: the Y sinusoid is a page-x phenomenon), i.e. against
`pose_linear(compose_from_native(native_affine, frame))`.  Since the
page-field line the production field is page-frame AT ITS SOURCE: a
published `PlaneField.delta_dots_xy` is printed dots along the page axes,
`plane_k.choose_offset`'s sweep runs along the printer's x through
`page_map.raster_points` whatever the scrap's rotation, and production
applies both through `RegionWindow.page_linear`, which is byte-for-byte
the analyzer's own `anchor.pose_linear(_level_terms(...))`.  So the
analyzer applies a production delta UNROTATED, through the receiver's
mapping, and rotates nothing (A1).  Only the swim's local affine and
`refine.color`'s candidate poses remain window-local, and `page_map`
names them (`local_axes` / `page_axes`); `arms.to_page_frame` survives as
that algebra and is applied to no production field.

The record of the per-lane era, kept because it is why the rule is
stated at all: the retired receiver built its dot deltas against the
WINDOW-LOCAL linear part, the two frames differed by the placement's
`rot_k` (a sign on both axes at rot_k 2; 579 of sheet I's 3,687 accepted
placements), and MEASURED on eight rot_k-2 C tiles of sheet I the
un-rotated per-lane delta was 2.6× worse (0.407 search-fold log loss)
than the rotated one (0.157), with committed at 0.184.  The
discriminating rot_k-2 test now asserts the OPPOSITE — one page-frame
delta moves a rot-0 owner and a rot-2 owner by the same page vector — and
lives in the suite offline over a synthetic `PlaneField`.

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
  per-sibling-state clusters; does not depend on `head`);
- **`patch`, `rings`, `mixture` (W8, §14)** — the first modes that read
  PIXELS rather than the three box means.  `patch` is a learned linear
  discriminant over the pose-resampled raw patch around the cell (window
  and sampling are the run's own choice, §14.4), fitted per (lane, plane,
  sibling state) on the footprint's fit-fold labels and CROSS-FIT inside
  that fold (§4.8); `rings` is the same fit over radial means (shift-
  robust, cheap); `mixture` is a blind two-Gaussian split of the tile's
  own red channel for three-ink cells, with `subtract` elsewhere and no
  labels at all.  Every patch mode falls through a TIER LADDER — per
  state, then one state-agnostic filter, then `subtract` — and every
  population is put on one scale by its own out-of-fold sd.  The reason
  they exist is measured and spatial: on an M+Y pile the third C layer
  has no dot core, so the 0.7-cell box aperture reads it at ~60 %
  strength (§14.1).
- **`pure` (W8, §14.5)** — the same score `patch` computes, PRICED
  differently.  It is an unmix MODE and not only a calibration knob so
  that `pure+committed` and `patch+committed` can sit in one battery and
  be arbitrated by the select fold like any other pair of arms: they
  share the detector exactly and differ in the single stage between it
  and BP.  Where a `patch` arm's score goes on to PAVA, the context stage
  and Platt, a `pure` arm hands BP the filter's OWN held-out error rate
  as a log-odds (§4.7).  The knob spelling `--knob calibration=pure`
  survives and does the same to a `patch` arm; the mode is what makes the
  comparison an ARM comparison, which the ledger then attributes.

`lane_mix` pools a DETERMINISTIC 12-tile sample of the page (the target's
tile removed, memo keyed by it) rather than the whole page's regressors: a
page is 1,961 footprints per lane and stream, and the exhaustive page fit
(≈ 30 s per lane-stream) is available as a knob, not a default.

Registration (per footprint, per lane):
- `committed`;
- `field` (committed + the snapshot's page field delta, page-frame at its
  source and applied unrotated through the receiver's mapping; keyed
  (page, plane), valid on every lane of its page, refuses another page
  and — when a test hands one in by mistake — another plane; records
  `field_applied`, `field_ordinal` (the revision it read) and the median
  `PlaneField.uncertainty_dots` over the cells this row read — recorded,
  gating nothing — and collapses
  EXPLICITLY to `committed` when no field stands or the field reads
  exactly zero over EVERY OBSERVED CELL of the footprint, halo included
  (`field_reads_zero_here`; the per-owner affine is fitted over the
  observed cells, so a halo-only field would move the target's read —
  review 2026-09-13 F4; and no published field on the record has a
  single zero tile, the prior extrapolates a non-zero surface where no
  evidence reached, so the collapse fires only when no field stands) —
  never a duplicate row, which is a NAMING
  rule: the collapse renames the evidence and the row still reaches the
  select fold under its own name.  The economy beside it (A3's wave,
  2026-09-12): the collapse depends only on (page, plane, lane, field),
  never on the unmix mode, so when the twin arm (`arms.FIELD_COLLAPSE`:
  `field` → `committed`, `field+offset` → `offset`) was already
  evaluated for the same (key, lane) the collapsed arm REUSES its row
  under the new name (`reused_from_arm` in the blind detail,
  `reused_arm_evaluations` in the row diag) — same rows, names, order
  and losses at the select fold, one 26-evaluation offset grid saved per
  (key, lane) wherever the field reads zero; no support gate (design
  I6/I8); UNCONDITIONAL, `select_arm` arbitrates);
- `offset` (blind 2-D grid: x ±2 dots then y ±1 dot, step 0.25, separable
  = 26 evaluations; the y arm is pre-registered with a y-jitter null
  because production searches x only for a measured reason);
- `field+offset` (production never runs them together);
- `affine` (the swim's own `local_affine.search` with the correlation score
  — its objective touches the selection fold, so it is scored on a fold of
  its own);
- `smooth` — RETIRED 2026-09-12 (A3): a per-(lane, stream) field in
  disguise (design I1), built from the default arm's winning offsets with
  support normalisation, Y only, alive from generation 1 — and its key
  dropped the page, so on a duplex sheet it merged both faces into one
  grid (it ran in `DEFAULT_ARMS` on sheet J).  An ablation arm over the
  page field, if ever wanted, is re-added page-keyed and reads
  `PlaneField`;
- `word` (for C and M: hard-read the isolated plane at the committed pose,
  form states 3·bit at the 100 word sites, verify blind with
  `pilots.decode_color_word` (erasures allowed), then fit the tile's
  per-plane pose from the 120 sites — the one arm that separates "the C
  band is misregistered" from "above the floor".  Its REFUSAL on a
  non-decoding word is itself the measurement; 3 of 4 certified C tiles
  decode blind);
- `field2` (§13's page-field lead, built: see below; `field2c`, the
  per-lane certificate-anchored variant, RETIRED 2026-09-12 at A2).

Sampling has one knob of its own since W8: `aperture_cells` (production's
0.7-cell box, or 0.5 / 1.0) and `aperture_kind` (`box`, `gaussian`) on
the crop filter, with the crop halo grown for both.  The defaults are
byte-identical to production's, and the patch discriminant is the
general case of the same idea — a learned aperture, and a linear
deconvolution of the patch it sees.

**The page field, built** (`analyzer/field2.py`, record in
`FIELD2-2026-09-03.md`).  Per-plane registration is a smooth function of
position with small local deviations, so a page FIELD does not fight the
local physics the way page-scope context and pose do.  `fit_pooled_page_field`
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
tiles.**  On sheet J's complete residue (2026-09-10, 2,688 covered
targets) the pooled arms took 27 of 156 first-success and 13 only-this-
arm with 0 contradictions (`J-CONFETTI-2026-09-10.md` §3).  `field2` is in
the `everything` profiles, not in `DEFAULT_ARMS`.  `field2c` is RETIRED
(2026-09-12, A2): it was the per-lane object the page-field design
abolishes, and — certificate-anchored — it was not named in
`controls.FIELD_ARMS`, the latent withholding hazard the 2026-09-07
identity audit found; its numbers above stand as the record.

`field2`'s rules are ITS OWN and say so (A2): it bounds its surface at
`field2.BOUND_DOTS` because a polynomial plus a kernel residual has no
prior and no fade, so past the bound it is extrapolating beyond its lane
coverage (reported when it bites); it refuses outside its own furniture
coverage (`field2_reason: no_support`) because nothing pulls it to the pose where
the production field says "pose" by construction; and it reports no
"publishable" against production's retired quarter-dot floor.  The
kernel smoother it fits with (`gaussian_kernel`, `smooth`, `clamp`, the
bandwidth, truncation and twicing constants) is the analyzer's own module
(`field2_kernel.py`), adopted verbatim from the receiver's retired
estimator so the receiver can delete its copy.  Its evaluation per cell
is the receiver's `plane_field.evaluate` — the one mapping.

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

**The sibling-state amendments (W8, §14).**  The two-population split
above answers "can this cell be cleaned?".  The measured failure is one
level finer — the M+Y population reads 2–4× worse than any other and the
same map is over-confident there and under-confident elsewhere — so
`branches="state"` gives EACH sibling state its own standardisation and
its own PAVA map (`s0`–`s3`, plus `other` where the siblings are not
proven), refusing and falling back to the pooled map by exactly the rule
above.  Its TRAIN sets exclude word sites (a word site renders states 0
and 3 only, so within one sibling state it carries a single target class
and would skew the map), keep dust, and report word/dust/cargo counts per
state.  `ctx_state=True` adds the context axis per state: production's
own 9-bin solver, floors and adoption gate, fitted per state after the
pooled fit and applied only where a state adopts, with the pooled offsets
everywhere else.  Two consequences are stated rather than hidden — the
second `apply_context_offsets` pass RE-CLAMPS an adopted state's LLRs at
±12, and a per-state residual is invisible to L3 (see §6's L3 row).  The
pooled 9-vector stays published under `ctx_offsets`, so
`combine.pooled_ctx_offsets` and L3 keep their contract, and the 4×9
table rides beside it as `ctx_offsets_by_state`.

**The pure path** (`calibration="pure"`, W8; re-priced F2, §14.5).  A
calibration with no map in it: `llr = sign(score − threshold) ·
log((1−e)/e)`, one `e` per (lane, plane, sibling state).  `e` is the
TILE'S OWN — the error of that hard decision under an equal-prior
two-Gaussian fit on the detector's scores over the tile's own cargo
cells of the state (the keystream fixes the cargo's prior at 1/2; the
fit is percentile-initialised, run a fixed number of EM steps, and reads
no label and no fold) — floored by the halo's held-out error, measured
on the SAME two cross-fit halves the filter is fitted on (half A's
class-mean midpoint prices half B and vice versa, so no row is priced by
a threshold it set), and clamped into [0.01, 0.45] — a population that
measured zero errors on a few hundred rows has not proven certainty, and
one at 0.45 has barely proven a direction.  The threshold is the halo's
midpoint; a state whose halo cannot measure a floor takes the pooled
halo's; a cell whose sibling state is unknown is an erasure, LLR 0 and
counted.  No PAVA, no context, no Platt, no refit: the whole point is to
find out what the stack between the filter and BP is worth.

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
nested-CV loss for the winner — never the minimum.  The `searched` list
that decides when a reported loss is a search-fold MINIMUM rather than a
nested-CV number now names every arm that minimises the search fold
(`offset`, `field+offset`, `field2+offset`, `affine`,
`word`), not only the first two: a pre-existing gap the patch arms would
otherwise have inherited (W8).

**A FITTED SCORE CHANGES THE FOLD CONTRACT (RULED, W8).**  Every score
before W8 was a fixed function of the cell's three values, so a PAVA map
fitted on the fit fold saw scores that owed it nothing.  A learned
discriminant does not have that property: calibrating it on its own
training rows would price its in-sample optimism as if it were accuracy.
So the patch family CROSS-FITS inside the fit fold — the fit-fold
labelled rows split into halves A/B by `fold_hash` under a salted seed,
filter A scores B and filter B scores A, so every training row carries an
OUT-OF-FOLD score, and the full (A ∪ B) filter scores everything else
(cargo, search, select).  PAVA, the context fit and every search
objective see only those scores.  Both numbers are published
(`patch_fit_error_insample`, `patch_fit_error_crossfit`), and their gap
is what the tier admission of §14.4 reads.  Pseudo labels (self-training,
decoder feedback) join the training set of both halves and the full fit,
and never the select fold.

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
- `normalized` (mean; control),
- `platt-state` (W8): the pooled Platt weights first, then a separate
  weight vector per SIBLING STATE wherever that state's own select-fold
  labels hold at least `SELECT_MIN_MINORITY` of each class — deliberately
  NOT the discriminating-minority count, which is degenerate inside one
  state (with the siblings fixed, every discriminating label carries the
  same target bit).  A state under its floor is priced by the pooled
  weights; `Combined.coefficients` stays the pooled vector so
  `contributing_captures` and `pooled_ctx_offsets` keep their contract,
  and `coefficients_by_state` rides beside it.  The captures a
  `platt-state` certificate leaned on are the UNION of the supports over
  the pooled vector and every per-state vector — a lane that carries one
  state carried the certificate.

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
explicit denominators (mother 4096 / transmitted 4096 − p / active /
user; 3976 / 3400 / 3368 at the printed p120 and r0850).

| rung | what | status | knobs |
|---|---|---|---|
| L0 `prod60` | `cmy8_decode_stream` at 60 (parity baseline, bit-exact production); a second `mother.bp` at the same knobs supplies unsat/posterior and the exposure charge, and must agree with production's syndrome/user bits (asserted) | built; the workhorse (254 of sheet H's 508) | — |
| L1 `prod150` | production heavy, 150 | built | — |
| L2 `bp` | the analyzer's BP variants: sum-product-only N iterations; damped min-sum (λ) and damped+offset (λ, β); layered schedule; since W8 a variant may also carry a `temperature` t that scales the combined LLR before `to_mother` (T1: multi-lane sums on a print-frozen channel are over-confident), and the rung name says so (`L2:damped@300@t0.8`) | built; second workhorse (damped 151 + layered 65 of 508); T1 BUILT, its default variants unchanged and byte-identical | N, λ, β, schedule, temperature |
| L4 `flip` | entry = the fewest-unsat L2 state; blind gate `unsat_at_exit ≤ 12`; then hypotheses at ±LLR_KNOWN on the least reliable variables incident to unsatisfied checks — singles over 24, then pairs over 8 — each followed by a short BP, every candidate gated syndrome→CRC and charged per distinct codeword | BUILT (W4) and mints, thinly: 11/59 on a synthetic near-codeword battery where L0–L2 got 0/59, and 2 on sheet H; 0 on sheet J's 2,874 rows | m, m′ |
| L3 `ctx-iterate` | APPLY-mode (RULED 2026-09-03): it does NOT refit.  A refit inside the tile has no labels by construction (the target key's cargo is excluded), so L3 as first built refused on every real target.  It applies the footprint's production-context offsets — fitted on halo labels whose neighbours are known — to in-tile cells whose neighbour bins come from the decoder's EXTRINSIC: the bins move, the offsets do not.  The fed-back prior is clipped exactly as `tile_codec.cmy7_iterated_decode` does; ≤ 3 rounds; abort when mean \|LLR\| grows without reducing unsatisfied checks.  W8: the rung is EXACT only for a POOLED correction, so a row whose combination leaned on a lane that adopted a per-state context (§4.7) is refused `state_context_adopted` rather than shifted by offsets that are no longer the ones the cells were priced with | built; runs (73 keys on sheet I's Q2, 327/340 sum rows carry pooled offsets) and has certified nothing yet | rounds |
| L7 `erase` | L7a: down-weight lanes' disagreeing cells (factor a knob), cap erasures at n−k−margin taking least-agreeing first, from the per-cell lane-sign agreement vector on `Combined`; L7b: blind contiguous-run erasure; the below-floor refusal reproduced as an explicit outcome; `n_erased`, `n_disagreeing`, `bank_active_bits` recorded | built; needs ≥ 2 lanes (refuses under `best`) and first certified on sheet J, 2026-09-10: L7a 1, L7b 1 of that pass's 156 | threshold, margin |
| L7c `erase-state` | W8's state-keyed twin of L7a: erase the cells of one SIBLING STATE (3 = both siblings inked) whose \|L\| is under a threshold, least confident first, under L7a's own cap and below-floor rule.  Its producer is the frame's sequential sibling-state vector, not the decoder — it targets the measured over-confidence on M+Y directly | BUILT (W8); its own rung name, NOT under the `L7` alias, so no existing profile changes | `erase_state`, `erase_tau`, `erase_factor`, margin |
| L3f `feedback` | W8's decoder-feedback refit: after a BP exit that did not certify, the confident extrinsic bits (\|extrinsic\| ≥ `refit_confidence_llr`, sequential index 0 excluded because the injected metadata bit dominates any ranking) become a typed `PseudoLabels(source="decoder")` at their page cells; the chosen lanes' EVIDENCE is recomputed with them in the fit set only (the patch filter and the maps refit), the lanes are recombined under the ROUND-0 label view so the rule's coefficients cannot move, and BP runs again.  Bounded by `refit_rounds` AND a per-key evidence budget; every candidate gated syndrome→CRC and charged | BUILT (W8); a direct rung; not in any default rung list and not in `reroll_rungs` (its cost is a re-run of every chosen lane's evidence); +3 in composition on sheet H (W8 §3.2), then 13 more on sheet J (L3f.r0 11, L3f.r1 2), its first on a confetti sheet | `refit_rounds`, `refit_confidence_llr`, `refit_max_evidence`, `refit_calibration` |
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

The histogram DECIDED, twice, differently, and both answers are kept — and
on a third sheet it decided nothing:

- **Sheet I is bimodal.**  1,595 rung outcomes: unsat 0 → 590, 1–49 → 0,
  50–99 → 3, ≥ 100 → 1,002.  A few-error rung has nothing to work on.  The
  deferral holds on paper, not just in simulation.
- **Sheet H is not.**  7,369 outcomes with 222 exits at 5–9 and 234 at
  10–49.  That shoulder is what L4 was built for, and L4 does mint there.
- **Sheet J's zero bucket is mostly EMPTY EVIDENCE, so the rule cannot be
  read off it.**  The all-arms pass published 1,179,396 non-list outcomes:
  unsat 0 → 127,824, 2 → 1,170, 3–4 → 1,463, 5–9 → 2,523, 10–49 → 67,709,
  50–99 → 20,614, 100–499 → 155,320, ≥ 500 → 802,773.  Of 111,214 zero-unsat
  outcomes sampled over 2,306 of the ledger's 2,874 rows, **71,580 (64 %)
  carry `detail.n_observed == 0`** — an arm with no observed cell at all, BP
  exiting at iteration 0 on the all-zero vector, which IS a codeword
  (`syndrome_ok true`, `crc_failed`, zero new exposure).  On a fragment sheet,
  where a fifth of the tile-streams never reach the attempt floor, the
  0-vs-≥50 reading must be taken over rows that have evidence or not at all.
  The sample is a PREFIX of a 4.5 GB ledger, not a random draw: the direction
  is robust, the 64 % is not.

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
L0–L2.  `everything+field2` — RETIRED 2026-09-12 with `field2c` (A2 of the
page-field plan): it added the certificate-anchored per-lane arms, the
expensive ones (a refit per lane per generation), behind their own name
for that reason; `everything+patch` is rebased on `everything`.  Cost is
about 4× the default; exposure stays a stated number.  `wide-halo`, `battery` and `split-branches` are the narrower
named configurations.  W8 adds `patch`, `patch-self`, `patch-refit`,
`patch-affine`, `everything+patch`, the three `pure` profiles (§14.5) and
the two PLACED ones below.  A profile records itself in the ledger header
as `knobs_from = "profile:<name>"`.

**The placement, and the amendment it makes to the union (RULED, W8 —
Germano: "only run it after the other pass has done its job, in case it
does show incremental gains").**  The union ruling says nothing an arm
does can mint a wrong certificate, so add every arm; it does not say
every arm is worth its wall on every key.  An arm named in
`AnalyzerConfig.reroll_only_arms` is PLACED: `blind_key` computes its
evidence inside the re-roll block and nowhere else, so a key the battery
closes never pays for it, and it can never be a select-fold candidate —
it cannot displace an arm that was measured against the pinned default.
When it certifies, the row says `certifying_arm = "reroll:<arm>"`, the
header lists `reroll_only_arms` and the row's `reroll.deferred` names
what was placed.  `patch-then-pure` (= `patch-refit` plus the two pure
arms) and `everything+patch+pure` (= `everything+patch` plus the same)
are the two profiles that use it, and `--reroll-only-arms ARM[,ARM]`
places any arm behind any battery without one.  This supersedes the
sentence, true until W8, that every arm in `arms` is a selection
candidate: an arm is a candidate unless it is placed.

**A profile supplies what the operator did not say (RULED, W8).**  An
explicit `--arms`, `--rules`, `--rungs`, `--halo-cells`, `--ctx-mode`,
`--no-reroll` or `--reroll-only-arms` WINS over the profile's own value,
and the header then reads `profile:<name>+cli` and carries the arms,
rules, rungs, halo, context mode, re-roll, the placed arms and the knob
VALUES — so one arm can be isolated inside a profile's knobs, and a pass
is reproducible from its own first line.  Before W8 the profile silently
overrode the flags and two passes that differed only in a knob were
indistinguishable on disk.  A misspelled arm, rule or rung is refused at
the same door, before a run dir is opened: each was checked deep inside a
pass (an arm at the first `evidence_for`, a rung inside a worker at the
first key, a rule at the first `combine`), so a typo used to cost a
fourteen-worker pass its whole run.  `types.KNOWN_RUNGS` is the one place
the spellable rung set is written, and a test reads `ladder._run_rungs`'
own dispatch chain to keep it from drifting.

### 6a. The close

After the ladder, production ∪ analyzer certificates go to
`holo.receiver.format.close.close_volume`; status, k_total, symbols used, metadata
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

**The hand-back is a loop, not a law (sheet J, 2026-09-10).**  On sheet I's
single capture the fold came back as a cascade at the cheapest rung: the
harvest exported, holo3 resumed from it, and `tiles.scan` certified the last
four tile-streams for 0.198 cpu-s over 8 jobs (PLAN §6, 2026-09-07).  Sheet J
qualifies that.  156 analyzer certificates were folded and the receiver
resumed on the SAME four captures: it replayed 3,558 and minted **exactly
one**, `(0, 44, 8, Y)` via `tiles/retry150`, for 47,960 jobs and 20,898.9 machine 4
cpu-s — and that key is adjacent to no analyzer key at all; the nearest on
its page is `(0, 40, 11, C)`, four rows and three columns away, so nothing
measurable cascaded.  The 156 keys' 720 in-bounds neighbours (4-neighbour
same stream plus the two sibling streams) were 395 already certified, 195
below the attempt floor, 65 attempted-and-failed and 65 untouched: there was
no label-starved neighbour for a new label to feed.  What the harvest did
instead was arithmetic — the count went 3,402 → 3,558 and the block's
shortfall 618 → 462.

**The condition, stated: a fold cascades where the residue's limitation is
DETECTOR-side.  On a fragment sheet it is not.**  At the 3,402 state, 5,796 of
the 8,364 open tile-streams had no usable pixels at all (3,522 never
addressed + 2,274 below the attempt floor, the receiver's own census row), and
`--targets residue` at `cover_fraction 0.9` found 2,688 covered targets — 32 %
of the open set, the other 68 % not covered by any placement footprint.  The
analyzer certified 156 of 2,688, 5.8 % of everything attackable.  The lever
that moved this sheet was a capture: one more platen load minted 714
certificates in 19 minutes of a run the operator interrupted, and the
ten-capture run closed byte-exact.  No dial-off control was run, so the one
mint is attributed neither way.  Record: `J-CONFETTI-2026-09-10.md`.

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
  Under withholding the frame and PooledColorCtx are rebuilt without the
  withheld set (or refused → `committed`, no pooled head), and the
  production `field` arms are REFUSED outright: every page field is
  fitted from certified templates plus furniture (design §2.5; the blind
  tier is retired), so a production field always carries the withheld
  certificates and cannot be rebuilt without them here.  `FIELD_ARMS` is
  every register arm whose field reads certificates, pinned by a test
  that walks `REGISTER_ARMS` (A6); the pooled `field2` reads none and
  stays admitted;
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

JSON-lines, one row per (page, ty, tx, stream) ATTEMPT with nested
per-(lane, arm) and per-rule/per-rung records; a header with seed, knobs,
provenance (`targets_from`, `knobs_from`, non-blind flag,
`format_ref_override`), run-level exposure, `n_corroborated` and
`n_contradictions`.

**STREAMED, since 2026-09-13** (`analyzer/ledgerio.py`; the reason is
`MEMORY-2026-09-13.md`: the rows held in memory until a pass returned
were 15–32 GB on a ten-capture sheet and a kill lost every one of them).
The out dir and the header line exist before generation 0; each row is
appended as its generation folds it, flushed, and not retained; the
header carries `partial: true` and a FOOTER line — the final header,
`partial: false` — closes the file when the pass returns. A re-attacked
key APPENDS a new row (`row_seq` is the file ordinal), so the file is
one row per attempt and every reader takes the LAST row per key
(`ledgerio.iter_rows_latest`; `score`, `export-facts`, `close`, the
`read` pass, the summary and the maps all do) and tolerates a truncated
last line, which it counts (`ReadStats`: rows, superseded,
`truncated_lines`, `partial`). A certified key is never re-attacked, so
counting certificates over all rows stays exact. On-disk row order
therefore differs from the old in-place replacement — `score --limit`
decorates the first N rows of the file. Beside the ledger: `mints.jsonl`
(named after its ledger: `ledger-read.jsonl` → `mints-read.jsonl`), one
row per certificate appended by the worker that won it — a whole
generation before its ledger row — in the row's own spelling with the
certifying rung under `rungs`, so `export-facts` and `score` read it
unchanged; `checkpoint.json` every `--checkpoint-minutes` (30; 0 off),
temp-written and renamed, a product never the pass: generation, keys
pending/attempted, `retired_folded`/`certified_folded` (a mint won inside
the running generation is in `mints_written` and in neither, and the
file says so), the exposure accounting, config, elapsed, memory. An
existing ledger or mint file at open is kept aside as `.bak`, never
truncated. Recovery from a kill is the existing doors — `export-facts`
over `mints.jsonl` (or the partial ledger) into a new base, `union-base`,
the same pass again; a `--resume` would skip the fountain gate and leave
the census keyed to the old snapshot, so it is not built.

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
decode.  Every memo is process-wide (a module global or a slot in
`RunInputs._cache`); there is no thread-local anywhere in the package,
and `--workers` multiplies only the per-worker transients (one crop, one
patch bank, the key's evidence bag — about 120 MB each at 2400 dpi,
about 1.5 GB on a 4800 lane).

**Where a long pass holds memory** (`MEMORY-2026-09-13.md`, the audit
behind the 2026-09-13 wave): the ledger rows kept until the pass
returned were the dominant holder — 1.6 MB of JSON per row on the
four-capture sheet-J pass, twice that live, growing with lanes and with
every certificate, 15–32 GB on the ten-capture base — and are now
streamed (§9); what the fixed point keeps is 3.6 MB for 2,700 keys. The
rasters were always memory-mapped (22.6 GB of clean, evictable pages on
ten captures, 0 anonymous). The snapshot's read peak is 3× its array
bytes and is never returned to the OS; its one field, the window-local
cell list, is int16 since the same day (4× smaller; the J fixture's read
peak 287 → 146 MB). Still open, with prices: the frame projection memo
keeps eight generations' tokens (0.5–8 GB); the patch family's gram
memo is uncapped on a 4800 lane; the rows' five per-label arrays are
80–92 % of a row and only the live fit reads them.

Measured wall/peak on sheet H (1,000 residue tile-streams, seven captures,
8 workers): a three-rung pass 59 min / 19 GB; `--profile everything` 3.8 h
/ 44.6 GB; `everything+field2` (retired) 3.5 h / 48.6 GB; the incremental
pass on a union base 3.6 h / 51.3 GB.  `union-base` 4.7 s / 11.8 GB; `close
--localize` 6.4 s / 11.8 GB (all of it the snapshot read; the consistency
check itself is 0.66 s over 5,437 symbols); `export-facts` 75 s / 8.6 GB;
`score` over five ledgers (18 GB of JSON) 183 s / 0.52 GB.  Full operator
table in `README.md` §3.

One known cost trap, and its wiring: `field2_fit_workers` defaulted to 1,
so inside a `fixedpoint` run the lazy pooled fit blocked the first target
that needed it for ~6 minutes (Y, 22 lanes) while other workers waited on
its key lock.  Since 2026-09-12 (A2) `fixedpoint._knobs_for` publishes it
from `config.workers` (an operator knob still wins) and the pooled fit's
read threads are bounded so that concurrent (page, plane) fits cannot
multiply the worker count; the peak with that wiring is unmeasured and
owed with the next sheet-H battery.

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
| composite-pose prior | §4.6 `smooth` (support-normalised) — RETIRED 2026-09-12, a lane-keyed field (§15) |
| page field per plane | §4.6 `field2` (`field2c` retired 2026-09-12); the production field read as a fact, §15 |
| crosswise / 4800 strips | §2 doctrine (resume first) |
| controls | §8 |
| stop rule | §1 R statistic, §3 targets, §6.1 deferral, §6a criteria |
| cascade | §6b |
| more BP iterations / decoder variants | §6 L2 |
| the close, and proving it | §6a |
| a poisoned symbol | §6a consistency + localize |
| two paths, one tile | §5 independent agreement, §8 parity |
| the third layer: a detector that reads pixels | §4.6 `patch`/`rings`/`mixture`, §14 |
| the sibling state as a first-class axis | §4.7 branches and context, §5 `platt-state`, §6 `L7c`, §14.3 |
| the decoder's own confident bits as labels | §6 `L3f`, §4.8 the fold contract, §14.3 |
| a calibration with no map in it | §4.7 the pure path, §14.5 |
| the run decides its own knobs | §4.8, §14.4 |
| pay for a supplemental arm only where the battery failed | §6.2 the placement, §14.6 |
| make the expensive walk cheap without changing a number | §14.6 the exact economies |

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
| **Page field (`field2`)** | a low-order surface plus a support-normalised smoothed residual from blind per-tile offsets; pooled per (page, plane) over every lane from FURNITURE anchors only, so it is certificate-free and generation-invariant — the analyzer's blind cross-check of the receiver's production page field (§15); `field2c`, the certificate-anchored per-lane variant, RETIRED 2026-09-12 | page surface + 5×5 residual | R and cell error against `subtract+offset`; certificates; production vs `field2` per (page, plane) through `measure/page_field/compare.py` | BUILT (§4.6, `FIELD2-2026-09-03.md`); real oracle gain; on sheet J's complete residue 27 of 156 first-success, 13 only-this-arm; in the `everything` profiles, not in `DEFAULT_ARMS` (ruling owed after M3) |
| **Local5 context** | the 9-bin fit over the 5×5 neighbourhood with shrinkage to the footprint's own fit — for label-starved bands only | 5×5 tiles | held-out loss where the footprint refuses | BUILT as `ctx_mode="local5"`, not default, no CLI flag |
| **Whole-page plane view** | run holo3's own placement/refine/swim/region-ctx/union/cascade on an emitted unmixed C plane (K-shaped page, cmy8 stream codec) | holo3's own scopes | parity vs production C; the col 30–31 band | BUILT and RUN — a measured negative: 1,632 C certified from scratch, **zero plane-view-only certificates**, 122 production C tiles missed, cols 30–31 0/0.  The whole receiver on the isolated C plane reaches a strict SUBSET of production ∪ analyzer |
| **Seeded plane views** | seed a plane view with every known certificate of that stream so holo3's K cascade works the residue only; `--holo3-option --max-pages 1` | holo3's own | seeded vs unseeded C view: residue take, wall time | owed; both levers supported by the harness, and the unseeded run's cold-placement endgame (787 `cold_rest` windows, 12–15 h projected) is the reason.  Deferred again in W8: worth its 12–15 h only after the patch family has shown what the band's C looks like to a filter that reads it |
| **A disjoint-capture rule** | a second `best` over the complement of the first certificate's captures, or a re-roll restricted to lanes it did not use — the only way the corroboration half of §5 can ever fire | per tile | `independent_agreement` ≥ 2 on real rows; certificates | proposed, unbuilt; a yield-and-evidence proposal, not a repair.  It composes with `platt-state`, whose union `contributing_captures` is the accounting it would need |
| **Temperature ladder** | scale the combined LLR by t before `to_mother`, as an L2 variant field (multi-lane sums on a print-frozen channel are over-confident) | per tile | unsat at exit vs t; certificates | BUILT (W8, T1); the default variants carry no temperature and are byte-identical; measured in PLAN §6 2026-09-06 |
| **Pose list decoding** | decode at the top-3 offsets of the search, not only the best held-out one | per tile | 3 CRC consults per tile; certificates | untried; NOT built in W8 (a list of reads changes the arm contract — one `Evidence` per pose — and the re-roll is already the attempt-count channel).  Next if the band's tiles sit at R ≈ 0.95–1.0 |
| **Patch discriminant** ("learn the detector") | a per (lane, plane, sibling-state) linear discriminant over the pose-resampled raw patch, cross-fit inside the fit fold, trained on the halo's certified cells (`local5` trains over the 5×5 neighbourhood) | footprint halo, or 5×5 tiles | cell error by (band, state) against the box mean; certificates | **BUILT (W8)** and the wave's headline: it was the largest untried lever and it is the one that mints — 96 certificates on 153 open sheet-H C rows where the pinned default minted 0, 0 wrong (PLAN §6 2026-09-06, §14) |
| **Per-channel registration** | sample R, G, B at their own positions (e033 measured the Canon R−G lateral CA as an odd-symmetric field) | sheet-wide field, per-tile offset | offset sweep per channel on labels | untried; NOT built in W8 — the measured loss is spatial, not a per-channel pose, and an RGB patch filter already contains a linear version of it |
| **Aperture / deconvolution** | the 0.7-cell box aperture was tuned for K at 8 px/cell; a Gaussian or smaller aperture at 16 px/cell, or a Wiener deconvolution from the sheet's own certified edges (MTF10 ≈ 860 dpi) | aperture global, PSF sheet-wide | label-scored sweep | the APERTURE is BUILT (W8, A7: `aperture_cells` / `aperture_kind`, and one of the axes a run chooses for itself); the DECONVOLUTION is not — the patch discriminant is a learned aperture and already contains a linear deconvolution of its own window |
| **Full neighbour-interaction context** | 256-context (or 3×3 linear) toner model instead of the 9-bin ink count; unknown neighbours from the decoder's extrinsic (turbo) | 5×5 tiles + page prior | held-out loss vs the 9-bin fit | untried; NOT built in W8.  It is the mechanism the measured "error FALLS with more C-inked neighbours" wants and production's non-increasing 9-bin solver cannot express — recorded as a new mechanism, not a knob |
| **Joint three-stream turbo** | where C and M are open too, feed their extrinsic posteriors as soft siblings into Y's unmixing and iterate the three decodes (H: 147 tiles with C and Y both open) | per tile | certificates on the C∧Y-open set | untried; NOT built in W8, and it is what would give the per-state tier something on the open C rows whose Y is open too.  It waits on the Y half of the residue being measured under the union profile |
| **Neighbourhood colour head** | the 8-state mixture fitted on 5×5 tiles with per-context means, shrunk to a lane-page prior — the head that does not starve in dead bands | 5×5 tiles | head parity on the dead-band edge tiles | untried; NOT built in W8 — a spectral fit does not address a spatial loss (the per-state CENTRES of `conditional` measured 0.228 against `subtract`'s 0.214 on the band's three-ink cells) |
| **Defect map → erasures** | oracle-guided discovery of clustered wrong cells (fibres, splatter), then a BLIND anomaly detector against the local model marks them erased | per tile | clustering statistic; L7 certificates | untried; still owed.  W8's `L7c` is a different, state-keyed producer for a measured failure and does not disposition this one |
| **Targeted evidence** | scans where R sits at 0.95–1.0 (several hundred H tiles): real crosswise sheets, 4800 strips of the marginal regions, 16-bit linear output for the faint Y channel | — | per-lane marginal value in the ledger | open; the Hend snapshot's six extra lanes are the nearest instance |
| **M's page field** | `field2` fitted for M independently of C — the only M reference the receiver cannot make, since its gauge sets `F_M = −F_C` to the bit; the production-vs-`field2` M row is therefore the first test of the gauge on paper outside the receiver's suite | page | `compare.py --analyzer` on the generalised phase-C product | A2/A5 of the page-field plan: `phase_c` fits every stream and every live page; an M `field2` was fitted in flight on sheet J (908 M rows) and unrecorded |
| **Fountain relations** | none — dense repair rows, no low-weight relations (§1) | — | — | dead |
| **Format-axis and physical items** (W8, `APPROACHES-2026-09-06.md` §1i) | C one rung down; a cmy8-presence row that never prints CMY; a modulation constraint against isolated C dots on an M+Y pile; Y at r0775; a lower q; more 4800 captures and crosswise sheets; the toner-order check | a printed row, or a print day | the third-layer loss is sheet-wide on a quarter of C's cells, so C wants the rung margin as much as Y | enumerated for the record, NOT built — rows, modulation constraints and prints are a print day's work under `.claude/rules/hardware.md`, not the analyzer's |
- **A block-edge PAVA evaluator as an arm (2026-10-12, the owner's note on passing the receiver's R31).** For a label-stream family (cmy) the receiver's chain reads its PAVA maps through block centroids joined in logit; nodes at each block's FIRST and LAST training score (logit-joined) remove the squeeze that separable maps show on clean sims and lose 0.0006–0.0062 bit/cell on every c2 paper band, measured held out (measure/cmy_calibration/RESULTS-2026-10-12-evaluator.md). Not a receiver default, by ruling; as an analyzer ARM over the residue — one more evaluator per (tile-stream, lane), tried where the fitted map is separable (two blocks at the clamp) and paid for in certificates — it fits the ladder's doctrine. Blocked on the cmy analyzer plan (CMY-RECEIVER-PLAN's analyzer side, unbuilt): the analyzer refuses non-cmy8 snapshots today (`inputs.py`).

## 14. The third-layer C line (W8, 2026-09-06)

The whole wave answers one measured question, and the measurement record
is `MEASUREMENTS-2026-09-06-C-THIRD-LAYER.md` (cited MEAS §n); the
enumeration of every approach, its isolation command, its compositions
and the run matrix is `APPROACHES-2026-09-06.md`.

### 14.1 What was measured

Sheet H was read to 5,580 of 5,883 tile-streams when this wave started
(2026-09-06 morning) and what remained was C in the dead band (tile
columns 30–31) and scattered Y; by the end of the day the mechanisms below
had taken it to 5,883 of 5,883, close verified byte-exact
(`W8-2026-09-06.md` §3, PLAN §6 "the blind passes").  MEAS §1 located the
failure inside the C decision: a C cell whose siblings M and Y are BOTH
inked is read 2–4× worse than any other C cell, sheet-wide (band 0.214,
marginal 0.133, live 0.106 against 0.05–0.07 elsewhere), while M under
C+Y is the best-read state on the sheet (0.020).  MEAS §2 put the loss in
the pixels rather than the receiver: raw red-as-K 0.268, `subtract` 0.214,
`head` 0.215, `conditional` 0.228, `affine` 0.217 — registration moves
every other state by ~0.005 and leaves this one alone.  MEAS §3 gave the
mechanism: the third toner layer on an M+Y pile has NO DOT CORE — a flat
red deficit at ~60 % of a single layer's strength, spread across the cell
and into its neighbours (radial profile 0.472 → 0.470 from centre to
13 px, against 0.359 → 0.450 for C on paper) — so a 0.7-cell box aperture
reads it at 60 % strength, and the error on M+Y cells FALLS with the
number of C-inked neighbours (isolated C on a pile is the worst case,
0.33).  Nothing the analyzer carried touched it, because every arm it
carried read the same three box means.

### 14.2 The answer: read the pixels

The patch discriminant (§4.6) is the wave's mechanism and its result.
Trained on nothing but what a halo already supplies — certified
neighbours' projected cells, dust, the metadata cell, never the target
plane's own bit — it reads the band's three-ink cells at roughly half the
box mean's error, and the ordinary cells better too.  Measured blind on
sheet H's own residue (PLAN §6 2026-09-06): the pinned default arm minted
0 certificates on 153 open C rows, `patch+offset` alone minted 96, and
the offline scorer found 0 wrong.  Those rows had survived every prior
production and analyzer pass.

Three things make it honest rather than lucky: the labels are the frame's
(the target tile's own cargo is excluded by construction, §4.5); the fit
is CROSS-FIT inside the fit fold so the calibration never sees the
filter's own training rows (§4.8); and the whole arm is arbitrated
against the pinned default on the select fold like any other (§4.8), with
the gate — syndrome + CRC — unchanged.

### 14.3 The sibling state as an axis

Once the state is what separates a good cell from a bad one, it belongs
in more than the detector.  W8 threads it through four stages, each
reachable alone: per-state calibration branches and per-state context
(§4.7), the `platt-state` combination rule (§5), the `L7c` erasure rung
and the `L3f` decoder-feedback refit (§6).  Two rules bound the last one:
pseudo labels are TYPED (`PseudoLabels(source=…)` is the only value the
evidence door accepts, the CLI refuses the reserved knob names and the
offline scorer refuses a config that carries them) and they join the FIT
set only — the select-fold label arrays are byte-identical with and
without them, so the rule coefficients and the arm selection can never
see the decoder's own output.

Where the state is UNPROVEN there is nothing per-state to do, and that is
not a corner case: on sheet H's open live C rows the Y stream is open
too, so the sibling state is unknown for most of the tile.  Those rows
are carried by the state-agnostic tier and the `subtract` fallback, and
the measurements are read per (band, siblings-certified) for that reason.

### 14.4 The run decides its own knobs

**RULING (Germano, 2026-09-06):** *"even the existing pins / defaults are
not well grounded.  if a run can discover its own truth for the
paper-print-scanner-scan object at hand, it should!"*

So no default in the patch family is a number carried over from a sweep
on one sheet.  Every knob a run can decide takes the value `"auto"`, and
`"auto"` is what the W8 profiles ask for; the constants that used to be
the defaults remain as the INHERITED FALLBACK — what a run uses when its
own select fold cannot tell the candidates apart.  The arbitration is
§4.8's, one level down: each candidate is fitted on the fit fold and
cross-fit inside it, its out-of-fold scores fit a PAVA map, the map
prices the SEARCH fold, and two candidates are compared PAIRED over the
same rows with the same standard-error margin `select_arm` uses for arms.
The SEARCH fold and not the select fold (review 2026-09-06): a knob walk
MINIMISES, §4.8 reserves the search fold for exactly that, and the select
fold has to stay a fold no search has touched or `select_arm`'s paired
test, `platt`'s weights and `best`'s choice are all read off a minimum.
An arm that chose its own knobs therefore forfeits `nested_cv_logloss`
the way a searching register arm does, with the reason
`winner_chose_its_own_knobs_on_the_search_fold`.
The walk is a single coordinate pass in a fixed order, so the cost is a
sum over the axes and not a product, and it is deterministic.  The
candidate sets, the fallbacks and what is deliberately NOT auto are in
README §2.4 — including the one axis the `pure*` profiles still name,
`patch_samples_per_cell`, and why.

The label-count floor went with the pins.  A tier is admitted on its own
cross-fit numbers instead: its out-of-fold error must beat the
population's majority-class rate by more than the same standard-error
multiple, AND its optimism (the published in-sample vs cross-fit gap)
must not exceed the advantage it bought, AND — added by the review of
2026-09-06 — the score its cells would otherwise carry must not beat it
by more than that same margin.  The third clause exists because the first
two compare a filter to majority-class GUESSING, which a filter worse
than the plain `subtract` score can clear, and the tier ladder hands a
fitted tier its cells before any later tier sees them.  It runs in that
direction on purpose: the tier keeps every tie (it is the arm's own
mechanism, and `select_arm` still arbitrates the whole arm against
`subtract+offset` afterwards) and the alternative has to prove harm.  No
clause carries a number from a sheet — the tolerance is the population's
own realised gain, and the margin is `select_arm`'s own.

The consequence for this document: every number in `APPROACHES` §6 and
`PLAN` §6 dated 2026-09-06 is a MEASUREMENT ON ONE SHEET, recorded as
such.  None of them re-pins a default, and none of them is a tuning
target; the acceptance gates keep only their regression meaning (the new
arm does not lose what the default had; zero wrong under the offline
scorer).

**AMENDMENT (2026-09-07, `HALO-CHANNEL-2026-09-07.md`): the walk's
objective, its franchise and its burden of proof.**  Six blind passes
over one target list (halo ∈ {16, 48} × channels ∈ {r, auto, rgb}, 710
certificates checked, 0 wrong) and the two `auto` ledgers say that the paragraph
above described the arbitration correctly and the POPULATION it runs on
wrongly.  Three named changes, all on the SEARCH fold, all behind
operator knobs; the select fold is untouched throughout.  The
pre-registered isolation (`HALO-CHANNEL` §5, one code state, 153 open C
tile-streams, 843 certificates checked, 0 wrong, 0 false accepts)
flipped the two that passed — the FRANCHISE ships `pooled` (net +4,
+5/−1) and the DIRECTION ships `nested-richer` (net +6, +7/−1), each a
crossing and not a containment — and refused the WEIGHTING, which is −3
on its own isolation and, measured over the shipped pair the same day
(`HALO-CHANNEL` §5.5), exactly 0 gained and 0 lost.  Naming all three
restores the pre-change walk's RULES, which a null-proof test pins with
the ridge NAMED.

* **W1, the criterion.** The walk scores held-out loss on the HALO's
  labels — the furniture of the tiles the footprint touches plus the
  projected cargo of the neighbours THAT CERTIFIED, a sample selected on
  exactly the quantity being measured.  Their own cross-fit error is
  0.0356 (halo 16) / 0.0202 (halo 48) on the three-ink state against the
  dead band's three-ink cargo at 0.152–0.171: the objective is priced on
  a population 4.3–4.8× easier than the cargo it will price, and two
  filters that differ by 4.4 points of cargo cell error and 19
  certificates differ by 0.009 nats there.  This is §14.5's F2 defect
  one level up — "the halo's number is a floor, not an estimate" — so
  the treatment is the same: under `walk_weighting=cargo` the per-label
  losses are importance-weighted onto the target tile's own cargo over
  two BLIND covariates (the sibling state, and a difficulty bin from the
  incumbent box-mean score).  Blind because the target tile's cargo
  carries no target-plane bit by construction (§4.5's run-abort
  assertion), so the profile consumes no fold and no label; the weights
  multiply losses, restrict no hypothesis and enter no certificate.  The
  tile-wide APERTURE walk is not weighted: it runs before the fallback
  the difficulty covariate is read from, and moves the values that
  fallback is computed from.  The
  correction is bounded by its own variance budget — clipped until the
  Kish effective sample size clears half the raw count — because the bar
  it lives inside is 2 SE ∝ n^(−1/2) and the correction may not spend
  more than the effect it corrects.
* **W2, the franchise.** `patch._choose_axes` refused the walk below
  `SELECT_MIN_MINORITY` and returned the INHERITED constants, which the
  ledger then recorded as if they were a choice: at halo 16, 674 of
  3,186 three-ink populations (21 %) never voted, and the record's "the
  search picks red 85 % of the time" was 2,047 votes plus 674
  inheritances.  Under `walk_franchise=pooled` such a population takes
  the POOLED (state-agnostic) walk's axes — a discovery on this object,
  not a pin — and only where that refuses too does the constant apply.
  `auto_source` ∈ `own` / `pooled` / `inherited` is published either way,
  so a vote and an inheritance are countable apart.
* **W3, the burden of proof, on the CHANNEL axis only.** `r` is
  literally `rgb`'s first 144 columns.  Under
  `walk_direction=nested-richer` the richer candidate is adopted unless
  the LEANER one wins by `SELECT_SE_MULTIPLE` standard errors — the
  direction `autoknobs.admit`'s third clause already uses — because the
  loss is one-sided on the matrix that argues for it: under-richness
  cost 13–19 certificates, over-richness cost 0, and a richer filter
  cannot mint a wrong certificate (the gate decides that).  Window and
  samples keep ties-to-inherited: one axis was isolated, and
  ties-go-richer everywhere would run the walk to 3,072 features on ~200
  labels.  This changes a RULE, not a value; `patch_channels` stays
  `"auto"` and a sheet where the extra channels are noise will show it.

**And one change that is not a knob**: the REGULARISER left `AXIS_ORDER`.
As the last stop of a coordinate pass it meant every other axis was
judged at the inherited ridge and the ridge was chosen afterwards for the
axes already fixed — and the ledgers say the richer model asks for more
ridge (20 % against 7 % on the three-ink state at halo 48) only after it
has already lost the vote.  It is an INNER minimisation now: every
candidate is scored at the argmin over its own shrinkage ladder, with one
rung more when its own `n_fit_rows / n_features` is below 1.  That ratio
is the one mechanical duty `labels_per_feature` acquires; it stays a
published diagnostic with no target and no veto.  **And the ridge the
population chose is the ridge it is FITTED at** — that was the point and
it was not true of the code until `3a661fe`, where a review found the
walk's winner published in every ledger and discarded before the fit
(`HALO-CHANNEL` §5.5).  `patch_states/<state>/shrinkage_fitted` is the
field that pins the two together.  Applying it is a crossing at par on
the `auto` column (one certificate each way, six more closes at the base
rung, at no CPU) and **−2 on a channel-PINNED run**, where 22 % of the
three-ink populations move to the underdetermined ridge — so the
regulariser is now chosen by the same too-easy objective W1 exists to
correct, and that is where the next measurement goes.

**What was NOT done, and why.**  The halo did not become an auto axis and
no labels-per-feature floor was adopted.  At a FIXED channel set the wide
halo is neutral-to-harmful (red 109 → 104, rgb 128 → 127) at 4.3× the CPU
and +8 GiB of peak RSS; the best cell in the matrix runs at 0.77 labels
per parameter, so every floor the matrix can reach is refuted and
anything below it is a pin; and structurally the halo DEFINES the row
set, so two halo candidates have no common evaluation population and
cannot be compared paired by this machinery at all.  The patch profiles'
halo therefore stays production's `{C: 16, M: 16, Y: 32}`, an operator
axis with `--halo-cells` as its escape hatch — which now takes a
per-plane spelling and carries its own provenance (`halo_from`), because
`--halo-cells 48` is 48/48/48 and `wide-halo` is 48/48/32.

### 14.5 The pure path

The counterweight to all of it, and the user's own question: *"we already
have every tile addressed, the correct page field and mostly correct
poses per plane — there is no justification for pushing that through
PAVA, ctx, Platt; just try it out either way."*  So the pure path takes
the page-field pose with no search, trains the same filter over the 5×5
neighbourhood's certified cells, and replaces the whole calibration stage
with one error rate per sibling state as a log-odds (§4.7).  One rule, no
context, no re-roll.  It is a named path with named profiles (`pure`,
`pure-self`, `pure-refit`), not a default, and what it measures is what
the stack between a detector and BP is worth.

**F2 (2026-09-06): the tile prices itself.**  The first trial
(APPROACHES §6.5) priced eight dead-band tiles at the halo's held-out
error, ~3 %, on cells the sheet measures at ~15 %: a certified
neighbour's cells are easier than a dead-band tile's cargo, so the
halo's number is a floor, not an estimate — and the cells whose sibling
state was unknown, most of an open-Y footprint, were priced by the
pooled halo with no label behind them.  The user's rulings: unknown
sibling state is an erasure, uncounted; and "why do we need refit??" —
the price comes from the tile.  So per state the discriminant's scores
on the tile's own cargo are read as two equal-prior populations
(`pure.self_fit`, `pure.error_at`), the error of the hard decision at
the threshold on exactly the cells being decoded is the self price, the
halo's cross-fit error is its floor, and the blind detail says which
bound (`pure_price_by_state`, `pure_price_source`).  This is
self-discovery (§14.4) applied to the price: discovered on the object
at hand, per tile and per state, with no pin in it.  `pure-refit` keeps
its profile and is recommended by nothing.  The re-priced path has not
run on paper.

The follow-up review of that build (APPROACHES §6.8) took R2 one step
further than the decode: an unknown-state row is uncounted where it
would PRICE somebody else too, so the pooled halo — the population every
starved state's threshold and floor come from — holds known-state rows
only.  Two smaller consequences, both of the same principle (the halo is
a floor, never an estimate): a state with too few cargo cells to fit its
own populations takes the TILE-POOLED self fit at its own threshold
(pooling smears the components by the per-state offsets, so it reads the
overlap pessimistically and can only raise the price), and where even
the tile cannot be fitted the floor is all there is and the ledger says
how many cargo cells that covered (`pure_floor_only_cargo_cells`).
Under `pure-refit` the decoder's pseudo rows are subtracted from the
self population: a filter measured on the cells that trained it reads
its own error low, which is the optimism `arms` already refuses for the
PAVA map.

### 14.6 What the wave costs, and where the pure path runs

Two amendments closed the wave, and both came from the user in one
sentence: *"nothing prevents us from a) numpy optimizing and
parallelizing the pure pass, and b) only run it after the other pass has
done its job — in case it does show incremental gains."*

**(a) The patch family is RESAMPLER-bound.**  Measured on this machine:
`map_coordinates` at order 1 reads about 5.6 M points per second, while a
4096×576 normal-equation build takes 25 ms and a 576-wide solve 2 ms.
One full-footprint extraction at 576 features is therefore 2.6 s of
resampling on its own, and thirteen lanes times two patch arms is not a
constant-factor problem.  What the wave removed is the REPEATED work, and
each removal is exact rather than approximate: which rows fit the crop is
arithmetic on the extreme sample offsets (IEEE addition is monotone in
its addend), so the bounding-geometry extraction disappears; a narrower
candidate window is a SLICE of a wider one at the same sampling and `r`
is the leading block of `rgb`, so one extraction of the selection rows
serves the whole `auto` walk; and the normal equations are additive and
sliceable, so one Gram per (population, cross-fit half) prices every
window, both channel sets, both feature kinds and every shrinkage.  On
the synthetic world that is 27 extractions down to 4.  The interpolator
itself was deliberately NOT replaced: a hand-rolled bilinear gather
measured 2.1× faster but is not bit-identical, and every number this wave
has on disk was read through `map_coordinates`.  That is a comparability
decision, and it is the largest remaining lever.

**(b) The pure path runs last, on what is left.**  §6.2's placement.  The
pure calibration is a hypothesis about the stack between a detector and
BP, so it should be paid for only where the ordinary stack failed: the
`pure` arms are PLACED in the re-roll, computed for a key the battery
could not close and for no other, and never a selection candidate.  A
placed arm cannot lose the profile anything — the union ruling's premise
(nothing an arm does can mint a wrong certificate) is unchanged, and the
only thing the placement changes is who pays.

What the placement does NOT isolate (review 2026-09-06): in
`patch-then-pure` and `everything+patch+pure` the placed arms are
combined under the PROFILE's full rule list (`sum, best, platt, corr,
platt-state`), and `platt`, `platt-state` and `best` are themselves
fitted on the select fold.  A gain there is attributable to the pure
CALIBRATION as combined by those rules, not to the calibration alone; the
`pure` profile itself carries `rules: ("sum",)` and is the isolation.
The two-pass form below is the other isolation, and the stricter one.

## 15. The page field, as the analyzer sees it (2026-09-12)

The receiver's design of record for registration is `docs/PAGE-FIELD-
DESIGN.md` (v0.6).  This section states what it means on this side of
the certificate door, in the terms its two external reviews taught.

There is one registration displacement field per printed face and plane,
in page axes and printed dots, evaluated per cell through the receiver's
one mapping (`lib/page_map`).  It is a fact the receiver publishes, keyed
by page and plane and by nothing else.  Captures, levels, lanes, scraps,
generations and rotations belong to evidence and placement; none of them
belongs in the field's key, and none of them belongs in the analyzer's
key for it either.  The gauge holds `F_C + F_M = 0` with Y free, and the
per-window translation the solve estimates is private solver state that
the analyzer never sees, never re-fits and never publishes.

The analyzer READS that fact.  It does not produce one.  Its own pooled
fit from furniture alone, `field2`, is the blind cross-check: independent
evidence, fitted without certificates, reported beside the production
field and never handed to the receiver as a field.  The door back to the
receiver stays a certificate door (`export-facts`), and an export
preserves every fact family of its base, fields and revisions included —
the sheet-J campaign measured what dropping them costs (`README.md`
§2.1a: the resumed receiver re-solved from nothing and its revisions came
back lower).

- **The key.**  The receiver's first error was a field per lane; the
  analyzer's were the same error three times — the production field keyed
  per capture and level, a certificate-anchored per-lane `field2c`, and a
  `smooth` arm that was a field per lane and stream with the page dropped
  from its key.  All three are gone.  There is no lane-keyed field in the
  analyzer.
- **The frame is at the source.**  A published delta is a page-axis
  vector; a lane's rotation is a placement property the mapping composes,
  never something the consumer applies.  The analyzer has no evaluation
  code of its own for the production field.
- **Nothing gates on support or uncertainty.**  A tile no evidence
  reached reads the pose, which is zero, and uncertainty is published and
  gates nothing.  The analyzer's own rule for its arms — never a duplicate
  row — is kept by naming the collapse (`field_reads_zero_here`), not by
  refusing to sample.
- **Unknown is not zero, but reads as the pose.**  A (page, plane) the
  receiver never solved has no `PlaneField` fact at all (the `field` arm
  collapses with `no_field`); one it solved from no observation carries a
  zero grid and `n_observations == 0` (the fact has no `known` flag —
  that is the product row's), and the arm reads it as the pose and
  collapses by name.  Nothing is inferred from a missing row.
- **A calibrated tier never hands rejects to an uncalibrated one.**
  `field2` is legitimate because it is a separate estimator with rules of
  its own — a bound, a coverage refusal — named and argued as its own,
  not inherited from the production floor and clip the receiver retired.
- **Publication is bounded staleness.**  The fact the analyzer reads lags
  the receiver's latest solve by at most the measurement's resolution
  (`FIELD_NOISE_DOTS`); every comparison is against the standing field,
  and the ledger records the revision it stood at (`PlaneField.ordinal`).

What the analyzer measures here is one thing: production field against
`field2`, per page and plane, over covered tiles — and the STATISTIC is
the receiver harness's (`measure/page_field/compare.py::against_
analyzer`: median |Δx|, |Δy|, Spearman of the column profiles, a sinusoid
fitted on both sides, profile max, median uncertainty; the fitted
amplitude and the profile max are printed side by side and never divided
one by the other).  The analyzer's part is to produce its side for every
(page, plane) in the schema that instrument reads, and to record which
revision of the production field its ladder actually read.  A
disagreement past the noise scale is a finding about one of the two
estimators, reported and never gated on; M's row is a test of the gauge
itself, because the receiver's M carries no independent measurement; y's
row runs with the receiver's measured y as the reference and the
analyzer's as the thing under test.  The yield question — does a field,
anyone's, buy certificates over a complete residue — is the one no
receiver replay can answer, and it is read from the ledger's first-
success and only-this-arm marginals with both families competing on one
select fold.

It never fits a field from certificates, never rotates a production
delta, never gates a read on the field's uncertainty, never writes a
field into a snapshot, and never strips one out.
