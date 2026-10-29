# The 2026-08-31 measurements and findings ledger

Companion to ARMS-2026-08-31.md (mechanism records) and
RULINGS-2026-08-31.md (the words). This file holds the findings that
are not any one arm's property, the real-sheet results, and the
method episodes. Detailed instrument records live with their
instruments (measure/*/README.md); this is the index and the numbers
that decisions turned on.

## Real-sheet results

**Sheet H, seven-capture max-stack (pre-repricing tree, studio):**
4,237/5,277, open — 70 BELOW the four-capture run (4,307), Y 660 vs
709. Certificate map: Y dead/alive in clean 1-D bands across the
short axis (columns 18-21, 25, 0-5 dead; column 16 certifies all 53)
— the measured Y x-registration sinusoid drawn in certificates. The
colour lane burned 38,512 CPU-s (31%) on the escalating-refit ladder
that the repricing fix then killed. First cross-dpi union
certificates on paper: 1,508 of the 4,307 four-capture harvest.
Events archived: scratch/holo3-overnight-events/.

**Sheet I, machine 2, 3×2400, current-era arms, fields dialled on
(pre-units-fix tree eee976c): 5,543 certificates — best ever**
(previous holo3 best 5,445; holo1 5,297), count-ready with 266
symbols of margin, close skipped by --no-close. C 1,949 / M 1,960 /
Y 1,634. tiles.local minted 213 (first real-paper yield of the new
arms) at 73% of the run's CPU. THE FIELD CONTRIBUTED NOTHING —
measured: 54 fits, 5,211 CPU-s, ZERO PlaneField facts in the
snapshot (that tree's floor was effectively 0.50 dots and its fitter
cells-valued). So the best-ever number was achieved with the field
effectively off, and the honest-units field's real-sheet upside is
untested as of this writing — the resume A/B from that run's
facts.npz is the experiment in flight.

**The 4800 question re-opened honestly:** the −70 was measured on
the defective-scheduling tree; the lead's own objection stands
(unions pair at shared rungs where 4800 contributions already ARE
decimated, so "native noise pollutes the unions" is wrong as
stated). The discriminating pair — four-capture baseline, then
--resume adding one/three 4800s on the current tree — is machine 4's
assignment.

## Cross-cutting findings

- **The receiver outgrew every naive sim stimulus** — measured at
  least four independent ways in one day (field-yield 300/300
  dial-off; the faint knife-edge band absorbed entirely by the
  rescue tiers, 453 tiles.local fires; local_ctx's six rescued
  identically by three different rows; the swim's bracket erased
  twice by field repairs). Consequence, now doctrine: stimuli need
  STRUCTURAL immunity to the other rows, not amplitude; cross-row
  fire-count goldens make the next outgrowing loud; "when this
  module rots, the receiver got better — re-harden, never delete."
- **The informative-floor ceiling bounds every residue row**: below
  it no AttemptFact is emitted, so no rescue row is ever born. A
  rescue row can only help a tile the receiver still tries.
- **The field-yield stimulus's amplitude band is CLOSED at c3**, and
  the closing was measured rather than argued (episode 3, the fifth
  instance of the same outgrowing, hours after the fourth).
  `tiles.swim`'s blind translation bound IS the printed cell
  (`translation_bound_dots` = `cell_dots_of(row)` = 3.000 dots here),
  exactly the injected peak and exactly a point on its own coarse
  grid, so with the field off that row recovers the whole page
  (300/300, 7 minted, `tiles.retry` 208 with the dial and 208
  without). The next whole dot is the swim module's stimulus, where
  the Y plane falls under the informative floor: 200/300, zero Y, and
  NO rescue row firing at all. Three ways past the row were measured
  and all failed. SHAPE — the curvature proposal — is closed by
  measuring the OPERATORS (commit d86feab): a window is
  `WINDOW_CELLS` 200 = 3.125 tiles against `BANDWIDTH_TILES` 2.0, so
  inside one the affine carries a slope where the field carries a
  smoothed constant, and run against the real `plane_field.solve` and
  the real `window_starts` at 3 dots the affine's residual is the
  SMALLER one at every frequency (0.5 to 3 cycles: field 0.96, 1.07,
  1.70, 2.58, 3.14 against affine 0.38, 0.37, 0.92, 1.34, 1.83 max),
  the gap WIDENING with frequency, with both sides upper-bounded
  fairly. Frequency is not free either: a non-integer cycle count
  leaves a nonzero mean (1.932 dots at half a cycle) which the {1, y}
  page-fraction residual absorbs before any rescue tier is reached. A
  second, independent model over the bounded affine and the clamped
  bilinear field agrees shape for shape (sine 1/1.5/2 cycles,
  triangle, dither-rounded, 3 and 4 dots — the affine smaller in
  every tile row). STARVING THE ROW'S LABELS is unreachable from a
  stimulus even though the architectural difference is real (the
  swim's objective floor is per WINDOW, the field's level table is
  fitted page-wide): the format lays 120 furniture cells per tile
  (100 word + 20 dust) and a window covers 9.77 tiles, so a window
  carries ~1,172 address-derived proven cells against a 64-cell
  floor — 18x — before any tile certifies, and furniture-only in a
  dead band is the regime that row was built for. Starving the
  certified COLLAR denies `tiles.local` and `tiles.planek`, not the
  row doing the absorbing. NOISE: sd 12/24/36 all certify 300/300 dial-off, and
  the direction is backwards — at sd 24 the FIELD's Y fit falls from
  1.1-2.0 dots to 0.52 and refuses to publish while the residue tier
  still closes. AN ABSOLUTE OFFSET: both the field and the swim
  OVERRIDE the {1, y} page-fraction residual rather than adding to it
  (`features_with_page_fraction`), and the field measures from zero,
  so a DC or ramp is charged to its 2-dot clamp before the swim's
  bound. Repair: hold `tiles.swim` out of that one pair, minimum cut,
  with the relation pinned so the hold-out expires itself.
- **The median-publication ruling's bill, now read by a test.** Taking
  the plane-COMMON part out of what the field publishes works exactly
  as designed — the clean colour sim's 0.973/0.974/0.975 dots on
  C/M/Y is now 0.012/0.025/0.004 and publishes nothing — and it was
  not free. On the displaced sim that ~0.97-dot pose-versus-ink bias
  had been carrying the ORDINARY read: `tiles.scan` minted 288 of 300
  with the dial on before the ruling and mints 202 after, the same
  count as the dial-off run, so the field's whole gain now arrives
  through the rows that RE-READ (`tiles.planek` 1 -> 11). The dial-on
  arm consequently stops one tile short of the control (Y (3, 0), the
  page-edge tile of the steepest band, which `tiles.swim` takes when
  it is present) and the rescue rows do MORE work with the field, not
  less — it converts hopeless tiles into rescuable ones and each
  rescue pays a full local head fit. The ruling stands; the price had
  been unmeasured, and `test_h3_color_field_yield` now pins both
  halves of it.
- **Height bites, width doesn't**: displacement losses land where
  the sinusoid CHANGES value; a locally-constant per-plane offset is
  absorbed by the colour head's {1,y} residual (a crest-widening
  knob was built, measured making pages easier, and removed).
- **The corner half-cell family** — one bare Affine alias serving
  two conventions half a cell apart produced THREE independent
  instances in one day (uplift fixture 4× contrast loss via
  quarter-contribution through the aperture; a latent twin; the
  anchortier instrument's plane-common +1 dot that forced two
  retractions). Resolution: unrepresentability — fixtures route
  through the production composer or one sanctioned door; an AST
  guard bans the idiom and caught two MORE cross-branch instances at
  merge time (the swim fixture; gt_bias allowlisted with a recorded
  reason).
- **Two meanings through one number, again**: the blind tier was
  silently discarded by the anchor tier's correlation floor
  filtering held-out log-loss weights — same defect class as the
  units bug. Three wrong explanations preceded the tally that
  settled it.
- **"Did it bite?"** — four times a measurement looked like a
  finding and was nothing (a clamp that never bound; an inert
  def-time-default override; a dead tier that survived two wrong
  hypotheses; a fix landed on a function the live path never calls).
  Each caught by checking the mechanism ENGAGED before reading the
  output as evidence. Recorded as the fourth episode of
  verify-before-concluding.
- **Y-anchor supply**: "dust-only" was literal format law (colour
  words render as states {0,3} — no word site carries Y ink) meeting
  an ink-only gate; the ink-free measurement (runtime-composed
  harness, src/holo untouched) yields 3,430 Y word anchors where
  production had 0, quality 0.668, and the residual saturation tail
  is peak-lock, not registration. The per-plane radius ruling (Y
  ±2.2→2.5 dots) bought saturation relief and no quality.
- **Sheet-I crop battery** (stopped at 13/26 as superseded): the
  original overnight exit-1 did not reproduce — it was the load-130
  thrash, not a defect. Union-vs-origin per-tile data and all
  sidecars retained under scratch/crop-parity/sheet-I/.

## Where the deep records live

measure/ysampler/README.md (bias check, radius, composition),
measure/yask/README.md (the Y-as-K ablation ladder),
measure/scanfield/README.md (+ hp- files; both scanner verdicts),
measure/accel/ (AMX + Metal BP), measure/local_ab/ + scratch/local-ab/
(union-vs-origin), measure/planek_parity.py, measure/h3_plane_fields.py
(the field-line driver), measure/h3_repricing.py, measure/resume_parity.py,
conversion_docs/crop-batteries/ (the battery tables),
scratch/holo3-overnight-events/ (events + certmaps + reports of every
overnight and max-stack run).

## Supersession note for PARITY.md

The overnight parity campaign's per-tile baselines describe the
receiver as of 2026-08-30 EVENING. Eight arms and three structural
fixes landed within the following 24 hours and the full-sheet results
moved accordingly (sheet I 5,445 -> 5,543 with the field still
effectively off). The recorded batteries stand as the record of THAT
receiver; the deep per-tile miss/gain analysis over those run dirs
was deliberately skipped as describing a receiver that no longer
exists (lead-approved lean wrap). Fresh baselines start from the
first current-tree full-domain runs (machine 2 sheet-I resume, machine 4 sheet-H
pair).

## Addendum — the sweep for undocumented findings (lead-ordered)

**The parked pool line (branch converted to
conversion_docs/tiles-pool-parked.patch, ref deleted).** Three durable
findings from the one worker whose mechanism did not land:
(1) THE PREMISE CORRECTION — holo3 already pools across captures:
tiles._combine sums per-capture post-context LLRs, so tiles.union IS
the multi-scan law and tiles.retry already re-runs it at bp150; the
only discarded evidence is WITHIN-capture window overlap
(freeze_page_owners gives each cell one winning window; 108 of 138
cover entries on the mixed sim had 2-9 covering windows).
(2) THE POOLING AMPLITUDE WINDOW, measured at the codec: pooled
closes from noise amplitude 1.2, winner-take-all union from 1.6, a
single view from 2.4 — on SYNTHETIC INDEPENDENT noise, which is true
across captures and false within one; the within-capture form was
parked on exactly that physics (correlated fit noise, the regime
where F1∘F6 measured equal-weight combining losing).
(3) THE TWO-BIRTH-PATH design for failure×pairing races: a
failure-only trigger minted zero subjects because the pairing arrived
after the failure with nothing left to re-arm it; the fix mints from
either side, gated by a monotone index. Reusable wherever a row
births from an intersection of two independently-arriving conditions.
Also recorded there: seven degraded-sim shapes (whole-page sd 44-56,
banded sd 70-100) all still certified 49/49 — holo3 sims fail
all-or-nothing, the first measurement of the no-sim-residue property
later confirmed four more ways.

**K-side validation scoring (the postfix harvests), previously only
in the thread**: e029-postfix hit its pre-registered yield bar
EXACTLY (1,938 predicted, 1,938 measured, ≥1,930 bar) — but both
churn bars MISSED: calibrate 16,504 jobs vs <15,000 (57% cut from
the defective 38,547; mean 22.9 fires/window, max 84) and ctx
80/38/30/25 fires across its four subjects vs <10. xerox-k-postfix:
1,922 vs the 1,927 reference (−5, unattributed, inside the w8
envelope), calibrate 17,523. The K-side flat-price re-fit churn is
real and standing — the colour lane got the repricing split; the K
calibrate/ctx rows still re-fire tens of times per subject on honest
wakes. A candidate for the same assembly-vs-refit treatment if K
endgames ever bind.

**Planek's rate-fact**, distinct from the informative-floor ceiling:
fully dead columns hold ~12.8% cell error against a rate-0.859 rung —
no receiver arm fixes that; it is the format axis's problem.

**The 3×3-anchor self-defeat mechanism** (why the anchor tier changed
shape): a template containing blind neighbours RE-READ at the pose
being measured scores the hypothesis into its own evidence — measured
slope +0.05/−0.06/−0.05 vs ~1.0 with the template frozen. The
production tier uses the format's own furniture as a frozen whole-tile
template. Related trade, measured at the 481-tile grid: the DENSE
whole-tile template correlates marginally better (+0.937 vs +0.916)
but saturates C/M hard (0.57/0.75) — the sparse parity-halved form
ships. And one measured-not-explained anomaly stands (also in OPEN):
the photometric estimator reads gain 1.000 against injected
displacement but 0.46-0.53 against the displacement the printer
actually made.

**Scale-free bars**: the HP scanner instrument's pre-registered
usefulness rule keyed on a MAXIMUM and fired USEFUL on one mark in
1,056 (0.2618 dots) while every distributional statistic sat 17×
under the floor — the max grows with sample size. Bars must be
distributional (medians, quantiles, s.e.-cleared trends), never
sample-size-dependent extremes.

**The MIC contamination catch**: the AltaLink's yellow tracking dots
(invisible in R/G, dark in B) polluted a blue-channel edge estimator
to a false 1.96-dot reading; fixed with a common support mask whose
excluded_fraction now doubles as a standing contamination meter
(0.0050 in blue on the MIC sheet vs 0.0001 without).

**The receiver out-converges its own records**: replaying the
union-vs-origin measurement's crops on current main left 33 residue
subjects where the record had 129, and a run-to-exhaustion I-tl crop
decode certified 555 where the record had 514 — recorded baselines
go stale in days now, so record comparisons must match convergence
(the replay harness gained exactly that: budget-matched runs,
absent-not-failed for since-certified tiles).

**Resume cost anatomy**: on a closed sheet, `place` is essentially
the entire resume cost (50 of 50 jobs on K, 295 of 325 colour) — the
price of persisting no bookmarks; and snapshot size is dominated by
Placement.local_cells_yx (~640 KB/placement uncompressed), which is
what the 9.2-9.3× compression is eating.
