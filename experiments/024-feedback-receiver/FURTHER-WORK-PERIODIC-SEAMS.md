# Further work — periodic seam recovery

**Status: hypothesis and bounded follow-on design; not implemented in
E024.0.**

This note records a failure family exposed by the E018b HP-1200 take and a
small recovery mechanism that is not yet specified by the main E024 design.
It is deliberately attribution-neutral: the current evidence does not prove
whether the seam is introduced by the printer/RIP, scanner transport, capture
driver, or an interaction between a mild physical seam and marginal sampling.

## Observation

The native HP-1200 C2 scan has about 4 pixels per cell. Its failure field is
not random:

- pilot acquisition collapses at approximately every sixth 60-cell pilot
  row, a 360-cell cadence;
- for C2 this is 720 printer dots, 1,440 HP scan pixels, or 30.48 mm;
- payload failures form near-solid horizontal bands at the same cadence;
- 101 of 449 accepted E022 placements were cut by the existing straddle
  audit;
- the Canon-4800 scan of the same C2 print certifies 1,815 of 1,819
  nondegenerate LDPC tiles, while all 782 HP certificates are a strict subset
  of the Canon certificates;
- the HP-1200 C3 take, at about 6 pixels per cell, shows weaker degradation at
  several corresponding physical heights.

The C2 bad-band errors are approximately symmetric between the two bit
directions. That is more consistent with phase, blur, or piecewise geometry
than with a simple detector-threshold bias.

The repository already models stochastic scanner transport steps and a
scanner-frame 18.63 mm CCD-joint comb. The new 30.48 mm process-direction
cadence must not be identified with either mechanism without measurement.

## What is already present, and what is missing

E022 already detects a within-window change point, removes the inconsistent
side from the authoritative core, and may subdivide a window whose residual
remains bad. This prevents a straddling pose from poisoning both sides.

E024.1 proposes bounded placement retry, and E024.2 proposes held-out-
validated core/halo expansion. Those are necessary ingredients, but neither
currently specifies:

- learning a repeated seam field;
- partitioning an already placed window at a seam;
- fitting independent scan mappings on both sides; or
- safely re-admitting the side that E022 censored.

E024.0's single bounded angle/phase revision may recover cells near a mild
seam. It cannot represent a genuine discontinuity inside one window, and its
frozen audited core cannot manufacture the missing coverage.

## Attribution experiments

Before choosing a production policy, establish the coordinate system of the
effect:

1. Rescan the same C2 sheet on the HP after a known vertical translation,
   then again after a 180-degree rotation. A scanner-frame seam remains fixed
   on the platen; a print/page seam travels with the sheet.
2. Reduce the Canon-4800 raster to 1200 dpi with an exact 4×4 box average and
   run the ordinary receiver. This holds nominal sampling at 4 pixels per
   cell without using the HP capture path.
3. Preserve and inspect the original HP TIFF, including strip/tile metadata
   and raw line coordinates. The current PNG retains scanner metadata but not
   enough container structure to test a TIFF-strip hypothesis.
4. If needed, reprint a diagnostic whose large bitmap origin or internal
   band boundaries are shifted by a noncommensurate amount. This separates a
   printer/RIP raster boundary from a page-content or receiver periodicity.

These are causal experiments. Recovery may still be useful before attribution
is complete, but the algorithm must learn the seam from evidence rather than
encode the observed cadence.

## Proposed bounded recovery arm

Treat this as a seam-aware specialization spanning E024.1 and E024.2; leave
its experiment number open until the attribution runs are complete.

1. Build a capture-local seam-likelihood field from E022 straddle cuts,
   held-out pilot residuals, between-window pose residuals, and legal
   CRC-certified payload labels.
2. Test both scan-coordinate and canonical-page-coordinate one-dimensional
   models. Estimate axis, phase, and optional period robustly; do not hard-code
   1,440 pixels or 30.48 mm.
3. Revisit only windows intersecting a strongly supported seam. Partition
   each into at most two supported children and fit an independent bounded
   local pose/phase for each side while keeping the admitted page, address,
   and orientation hypothesis fixed.
4. Gate each child independently on disjoint pilots and target-safe held-out
   certified labels. If one side cannot retain the inherited placement,
   defer it to E024.1's bounded losing-hypothesis retry.
5. Re-admit censored cells only through an explicitly versioned E024.2 support
   extension: the E021 mask and source pixels must exist, and held-out loss
   must improve.
6. Freeze one owner per capture and page cell, superseding the parent
   evidence. Two children of one physical capture are disjoint pieces of one
   observation, never independent votes.
7. Retry only unresolved tiles whose legal evidence digest changed, then use
   the ordinary synchronous E024 generation barrier.

The first implementation should stay small: one inferred axis, a tiny number
of seam candidates, and at most one split per affected window. It should not
become a free elastic warp or a page-wide pose portfolio.

## State and qualification requirements

Persist the seam-model identity, coordinate system, supporting residuals,
parent placement, child cores/poses, held-out gates, support extension, and
certificate dependency closure. Replaying a rejected proposal must be an
exact no-op.

Qualify at least:

- synthetic phase reset, row insertion/deletion, and localized blur-band
  fixtures;
- translated and rotated rescans of one physical sheet;
- native HP-1200 versus exact-4×4-box Canon-4800;
- no-seam controls, which must remain byte-identical;
- `attempted_failed` recovery separately from newly covered
  `below_attempt_floor` tiles;
- certificate correctness, one-vote-per-capture accounting, target-safe
  dependencies, runtime, and gain unique to split pose versus support
  extension.

## Non-goals

- no assumption that the scanner is the source;
- no hard-coded cadence or seam phase;
- no unrestricted re-segmentation, global elastic warp, or large aperture
  sweep;
- no uncertified LDPC beliefs as detector or pose labels;
- no fountain/RaptorQ accounting or completion condition.
