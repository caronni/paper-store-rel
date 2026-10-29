# PAGE-FIELD — the per-plane registration field of a printed page

**Status: DESIGN OF RECORD, v0.6, 2026-09-12** (v0.5 was 2026-09-08's, the W8 amendment; v0.6 carries the W9 repairs of the 2026-09-09 external re-review — the publication ruling in §2.7 and I8, the fixed-point solve in §2.6 and B6, the fade promise ruled unmet on the printed page in §7.1, A4b closed in §7.2, the sheet-J chain in B6, B7 and §7.1 — and every number the W9 replays re-measured). The trigger of v0.5 was the
external review `docs/reviews/page-field-receiver-2026-09-08/REVIEW.md`
(eleven findings, seven reproduction scripts beside it, every one of them
reproducing on the landed tree at `d6bb311d`). The rulings that answer it
are the lead's and their home is `src/holo/receiver/docs/PAGE-FIELD-W8-CHARTER-2026-09-08.md` —
R-A to R-G, each written in plain words so that any one of them can be
vetoed on its own argument. This document says what those rulings mean
for the OBJECT; `src/holo/receiver/docs/PAGE-FIELD-PLAN.md` §2's W8 block
says what is built, deleted and re-measured. What moves: the gauge
becomes a constraint on the FIELDS with one nuisance translation per
window (§2.3); the estimator becomes a stated prior plus evidence, in
millimetres, with uncertainty published per tile (§2.4, §2.6); evidence
becomes raw rows, per plane and per component, from ONE null-calibrated
measurement primitive, with the blind tier retired (§2.5); and scheduling
becomes one revision per capture-page, with the residual trigger retired
(§2.7). Two invariants are new (I12 the revision, I13 unknown-is-not-zero)
and four amended (I3, I5, I6, I8); two bars are new (B8 the prior, B9 the
nulls) and the rest are restated against the behaviour suite that proves
them. **Nothing in this document is yet measured on the solve it now
describes** — §7.1's first item is that the whole requalification is owed.

**On the number.** The charter calls this amendment "v0.4". The tree's
W7b wave had already taken that number earlier the same day, so it lands
as v0.5. The two amendments this one stands on are kept as the record and
not as a preface: **v0.4**, which was a WITHDRAWAL of every sheet-J number
taken on the wrong identity, and **v0.3**, the W7 review's pass, are
§7.2's first two entries.

**Scope.** WHERE: `src/holo/receiver`
(holo3) is the producer and the production reader; `analyzer/` reads the
receiver's field and keeps its own furniture-only fit as the blind
cross-check. This document supersedes, for this object only:
`docs/PLANE-FIELDS.md` §3 (representation, hierarchy) and §6.5 (scope
items), `docs/COMPOSITE-POSE-DESIGN.md` §2 row (a), §4.1 and §7
(`SheetField`), `docs/INDEPENDENT-PLANES.md` §4.A (the sheet-level field
service), `src/holo/receiver/docs/COLOR-REDESIGN.md` §1 (registration),
and it restates the 2026-09-03 analyzer ruling (`analyzer/field2.py:43-59`)
as the receiver's law. Those documents stay as the measured record.
Workplans: `src/holo/receiver/docs/PAGE-FIELD-PLAN.md`,
`analyzer/PAGE-FIELD-PLAN.md`.

---

## 0. The object in one paragraph

A printed face carries, per ink plane, a displacement of that plane's
dots from where the format put them. It is put there by the printer and
frozen at print time. It is a function of page position and of nothing
else — not of the capture, the decimation level, the lane, the platen
placement, the scrap, or the cascade generation. It is smooth at the
tile scale and it is not small: on the M281 the Y plane sits 1.7 dots
from the word frame in the process direction with a 0.016 % stretch on
top, and on the AltaLink the Y plane wanders ±0.83 dots with a ~100 mm
period. A c2 cell is 2 dots. The page field is that displacement, per
(page, plane), in printed dots, in page axes, on the tile grid, evaluated
per cell, estimated once per page from every observation any capture ever
makes of that page, and applied by every reader that turns a page
coordinate into a raster position.

---

## 1. Why the object is defined this way (the record, briefly)

The identity was ruled four times before this document — the v0.2 origin
(`docs/REASONING-LOG.md:46-48`), 2026-08-19/22
(`docs/PLANE-FIELDS.md:311-313`, `docs/COMPOSITE-POSE-DESIGN.md:40-48`),
2026-09-03 (`analyzer/field2.py:43-59`), 2026-09-05 ("aren't they
identical?") — and built the other way three times: v1 per (capture,
lane), holo3 per (capture, level, page, plane), holo4's draft data model
inheriting holo3's key. The 2026-09-07 audit measured the consequences on
the archived facts:

- **Multiplicity.** Sheet H's one page stood 23 independent fields in the
  7-capture snapshot (C 18, M 5, Y 0), 44 lane-page subjects at 13
  captures, each re-fitting at ~120 CPU-s per certificate fold; sheet J's
  two faces stood 64 fits. The dial was on for every real sheet.
- **Invariance across levels, measured.** Within one capture, across its
  3–4 decimation levels, the published C median agrees to 0.003–0.034
  dots on all 20 capture-pages of sheet J and to 0.002 dots on sheet H.
  The level axis of a key is empirically void.
- **Frame regression.** holo3 stored the vector in the placement's local
  axes (rotation composed into the window 2×2,
  `plugins/color_region.py:617-619`, applied at
  `plugins/color_region_anchor.py:58-68`); v1 rotated at every crossing.
  Every sheet-J confetti lane-page mixes all four rotations, so those
  fields were frame-scrambled averages. Un-rotated deltas measured 2.6×
  worse than none (`analyzer/DESIGN.md:376-391`).
- **A second model of the same quantity, always on.** A per-region,
  per-lane intercept-plus-slope registration residual
  (`plugins/color_region_anchor.py:394-477`) ran under every colour read,
  replaced per plane where a field was published.
- **Pooling recovers signal per-lane fitting throws away.** On sheet H the
  per-lane Y fits read 0.21–0.27 dots and sat under the 0.25-dot floor;
  the 22-lane pooled fit reads 0.374 at r² 0.91 and clears it
  (`analyzer/FIELD2-2026-09-03.md:392-417`). The receiver has never
  published a Y field on any lane of any sheet.
- **The sinusoid's gradient.** Peak 0.83 dots, period ≈ 18.5 tiles ⇒ up to
  0.28 dots per tile, up to 0.9 dots across one 200-cell window at the
  zero crossings. The field must be evaluated per cell.

---

## 2. The model

### 2.1 Composition

For capture k, window w, plane p and page cell u (printed dots):

```
pixel(k, w, p, u) = P[k, w]( u + D_p(u) )
```

`P[k, w]` is the plane-common pose of window w in capture k — paper
stress, cut, platen placement, orientation, the plane-common part of the
printer's warp. `D_p` is the page field of plane p. Composition order is
physics, not convention: the printer acts on the page before it is paper,
the platen on the paper before it is light. A scanner term, if a scanner
ever needs one, acts on the light and enters AFTER the pose, on the pixel,
per sensor channel; none is built (§5). K has one plane and no
differential: `D_K ≡ 0`, no special case anywhere.

### 2.2 Identity

One field per **(page, plane)**. A page is a printed FACE: sheet J's two
duplex faces measured different fields inside the same capture (C medians
0.46 vs 0.53). Invariant across captures, decimation levels, lanes, platen
placements, scraps and cascade generations; those are the axes evidence
POOLS over, never axes of the key. There is no per-capture, per-lane or
per-level field of any kind, and no residual term at those scopes: a
capture's own error is pose error and belongs to the pose row; a scanner's
own error belongs to a scanner term that does not exist.

### 2.3 Gauge, and the window's nuisance

(RULED 2026-09-07 by Germano — the pose sits "in between C and M";
that ruling is where this section comes from and it still binds.
AMENDED 2026-09-08, W8 R-A: the same ruling now constrains the
FIELDS instead of each window's row set. AMENDED 2026-10-12, the cmy
receiver's A5 (CMY-DESIGN R7): the gauge follows the pose's ink, so a
row whose pose sits on one ink holds that ink's field at zero — the last
paragraph before R1's retirement below.)

The field is the differential of each plane relative to the frame the
sampler already uses, the pose. The pose is fit from the word ink, and the
v1 colour word is C+M overprint, so the pose sits between C and M by
construction. The gauge states that as a constraint on the FIELDS, at
every tile of the page:

```
F_C(u) + F_M(u) = 0      F_Y(u) free      F_K ≡ 0
```

"Zero field" therefore means "sample at the pose", which is the fallback
the receiver already trusts and the right one wherever the field has no
evidence. K has one plane and no differential.

**The pose a window stands at is not the pose that printed the page.** A
cut edge, a platen placement, a scrap's own paper stress each leave a
small residual error, and it is the same error for all three planes of
that window. The estimator names it instead of letting it settle into a
plane:

```
measured(window w, plane p, tile u) = F_p(u) + t_w + measurement error
```

`t_w` is ONE two-component translation per window, shared by every plane
that window measured, estimated jointly with the fields (§2.6). It is
ESTIMATION STATE: the solve returns it on its own result object, where
the diagnostics and the harness read it in the same process; no published
FACT carries it, and no reader applies it (§2.6 says this again where the
publication list is, and pins it). The pose row remains the only owner of
poses. That boundary
is measured, not stylistic: the common mode of the field's own
measurements is not the decode optimum, and the pose writer that tried to
adopt it measured −5 certificates and +2.1 pp
(`docs/COMPOSITE-POSE-DESIGN.md:197-219`). If a pose is wrong, the pose
row fixes it on its own held-out gate.

The two statements together are the point of the amendment: **no rule
about which planes a window must have seen is needed any more.** A window
that measured all three planes constrains the fields and its own
translation. A window that measured only Y still contributes — its rows
fix the SHAPE of `F_Y` across the tiles it covers, its translation is
pinned wherever it overlaps windows that did see word ink, and the prior
(§2.4) pins it otherwise. A window that measured nothing usable
contributes nothing, and needs no rule to say so.

**WHY THE OLD SUBTRACTION HAD TO GO, measured by the external review**
(`docs/reviews/page-field-receiver-2026-09-08/REVIEW.md` F1,
`collector_counterexamples.py`). Until W8 each window subtracted the
weighted average of whichever C and M measurements it happened to keep,
so the zero of the field moved with what a scanner saw. Hold the pose and
the physical displacements fixed at C +0.6, M −0.6, Y +1.5 dots: a window
that kept C and Y published Y **+0.9**, one that kept M and Y published
**+2.1**, one that kept both published **+1.5**. All three were accepted,
and they differ by **1.2 dots** in a quantity that is defined to be a
property of the page. Both word planes present is no defence either: with
C +0.67, M −0.67 and Y −1.7, dropping M's weight from 1 to 0.25 moves Y
from −1.7 to **−2.102**. Measurement quality and accepted-site counts were
setting the coordinate reference, and they differ across captures,
windows, planes and tiers while the printed word frame does not. Pooling
cannot put back a quantity that was subtracted before pooling. Under this
section it cannot happen: the gauge is one statement about the two fields
of one page, and each window's own error lives in its own parameter.

Refused alternatives, with the M281's numbers: a reference plane (M) puts
C and M half their separation off at zero (0.67 dots); a three-plane
centroid puts every plane a third of Y's offset off at zero (0.57 dots)
and re-couples Y to C and M through the mean — the Y/3 mechanism
(`docs/PLANE-FIELDS.md:1108-1120`) in another form. If a format's pose
ever sits on one ink, the gauge follows the pose's ink. (RESTATED
2026-10-12 per CMY-DESIGN R7, RULED 2026-10-09 — the pose's ink, not the
word ink; the sentence read "If a format ever prints its words in one
ink, the gauge follows the word ink.")

**AMENDED 2026-10-12 (CMY-RECEIVER-PLAN A5; docs/CMY-DESIGN.md §7 (f),
R7 RULED 2026-10-09): the gauge follows the pose's ink.** The receiver
reads it off the row's word '1' (`row.word_states[1]`) as its PROXY and
derives the gauge from that (`src/holo/receiver/lib/field_gauge.py`)
instead of hard-wiring it. The proxy is the pose's ink on every colour
row there is: cmy8 and cmy7 print their word in C+M and address on luma,
where that word is dark, so the pose sits between C and M by
construction, they cancel, and the gauge above stands byte for byte; cmy
prints its word in C alone and addresses on R (`words.ADDRESSING_ON_R`,
`plugins/words.py:47`), where C is its one dark ink, so the pose is C's
exactly and C's field is zero by name:

```
cmy:   F_C ≡ 0      F_M free      F_Y free      (each relative to C)
```

In the window model above (`measured = F_p(u) + t_w`) C's rows carry
coefficient 0 — they inform only their window's `t_w` — and M and Y are the solve's two free
fields at +1 each. The C field is PUBLISHED as the zero field, with zero
uncertainty, and is known by name whether or not C was measured (I13: a
definition is not an absence; the analyzer's AI3 reads a zero delta as
`committed` by name). No weights enter the gauge — v0.2 of the cmy
design's `w_C F_C + w_M F_M = 0` was withdrawn by R7 — and Y stays out of
it, so the three-plane centroid refused above never forms. `fields.moved`
stays one decision per page (R1). A cmy template correlates one channel
per plane — R for C, G for M, B for Y — and the cells whose ink darkens
that channel without printing the plane are weighted out of it,
furniture and certified templates alike
(`plugins/field_tiers.CROSS_TALK_STATES`; §2.5's floors count what is
left): M's template zero-weights the C cells (C darkens G by 48 % of M;
Y's 6 % is kept), Y's the C and the M cells (19 % and 77 % of Y in B),
and C's none (M's 8 % and Y's 1 % of C in R are kept). The shares are the
M281's solid bars, e043c sheet 3 (`_h3_sims_cmy.e043c_sheet3_bars`).

**RETIRED HERE: R1** (RULED 2026-09-08, W7 — "a window carrying no live C
and no live M yields NO Y observation"). Its argument was right about the
quantity: a Y delta measured where the common mode cannot be formed is
not the quantity this section defines. Its remedy was to drop the row,
and the remedy is what W8 replaces — the missing quantity is now NAMED
(`t_w`) instead of being subtracted or refused, so the row keeps its
information and cannot smuggle a window's pose error into the page. The
ruling's own measured price stays in the record and it was ZERO: on
`L:c2-cmy8-r0547@53x37`, load 1a, one Canon 2400 capture, both faces, the
W7 tree raises 155 window events (68 on page 0, 87 on page 1) and every
one carries live C and M mass, so the rule refused no row and an R1-off
control solved from the same collection's own recorded windows is
IDENTICAL on all six page-planes — support 222/227/176 and 187/179/149,
the same observation counts and the same medians (2026-09-08, W7b
review-fix, `scratchpad/w7b-fix/gauge_price.py`, one collection
instrumented at `Table.add_window` and solved twice).
`fields_collect.gauge_covered` was written against a run that declared
the wrong seed (§7), where the certified tier certified almost nothing and
windows therefore carried almost no C or M evidence, which is why the rule
looked like the majority case.

**What the Y loss on that capture was, and it was not this rule's.** Y
support falls 216 → 176 tiles on page 0 and 181 → 149 on page 1, −18.1 %
over both faces, and Y observations 446 → 330, −26.0 %, while C and M move
by at most two tiles and one observation. That is the two ANCHOR-TIER
FLOORS of §2.5 — 120 of the 129 scored anchor-Y calls refused, 58 at
`ANCHOR_MIN_PER_CLASS` and 62 at the size-aware floor, against one call
each of 129 on C and on M. §2.5 carries the full attribution and the
lead's open question on it.

What refusal still costs in bookkeeping, and it is every refusal's cost in
this collection rather than any one rule's: nothing in the observation
fact records that a row was refused, so a tile left with no rows is
indistinguishable from one never measured, counts as fresh at the next
collection, and its window opens a crop and re-measures it. W8 answers the
two halves of this that are about MEANING — a component nobody measured is
marked unmeasured (§2.5, I13) and evidence that disappears is replaced
explicitly rather than by absence (§2.6, I12) — and leaves the third,
which is about COST: a durable record that this tile was measured and
refused, so the next collection does not pay for it again. That is a
fact-schema change; it is OWED, not ruled.

### 2.4 Representation, and the prior (AMENDED 2026-09-08, W8 R-B)

A vector field in printed dots along the PAGE axes, sampled on the page's
tile grid, both components always (the M281's dominant term is in y),
evaluated at any page cell by bilinear interpolation of the tile samples.
Nonparametric: no offset model, no ramp model, no harmonic model. Roll
size (a ramp), an elliptic roll (a period), an axis wobble (a period whose
amplitude and phase vary across the page) are all smooth at the tile scale
and the field expresses each without being told which. It refuses features
narrower than that — those are jitter and damage, the erasure classifier's
territory, never registration.

The field's spatial gradient is the only per-plane "Jacobian" there is. It
is carried by the per-cell evaluation and it is never a free parameter of
a pose or of the field. "Translation-only" in the record means "no free
per-plane Jacobian parameters", not "no per-plane gradients"; the
"Jacobian is plane-common at ×11" measurement
(`docs/INDEPENDENT-PLANES.md:130-134`) was taken on dead-band tiles at the
sinusoid's extrema, where its gradient vanishes.

**The field is a stated prior plus evidence.** The solve (§2.6) is one
penalised, robust least-squares problem, and this section fixes its
penalty terms. The two LENGTHS are expressed in millimetres, because the
physics is the printer's and does not know the cell pitch:

- **Smoothness.** A curvature penalty over the tile grid with a length
  scale `SMOOTHING_LENGTH_MM`, **DERIVED FROM A BAR AND NO LONGER COPIED
  FROM A RETIRED FILTER — RULED 2026-09-08 (the lead, W8 landing)**.

  THE BAR. The field exists to resolve page-scale registration
  structure, and the structure this record has measured is the
  AltaLink's ~100 mm Y sinusoid (§0), so: **the solve must keep at least
  `GAIN_BAR` = 0.95 of a sinusoid of `GAIN_WAVELENGTH_MM` = 100 mm, at
  every pitch.** W7 and the W8 build set the length to 10.8 mm because
  that was what the shipped c2 bandwidth had been in millimetres (2.0
  tiles × 5.419 mm) — an inheritance, not a bar, and the W8 review
  measured what it bought: 0.776 of that wave at c2 and 0.791 at c3
  where the kernel the length was named after passed 0.957. Same
  millimetres, different filter.

  THE DERIVATION, which is now five lines of
  `lib/plane_field._smoothing_length_mm`. The penalty is a quadratic in
  the Laplacian, so its symbol is `S(k) = lambda_g k² + lambda_c k⁴`,
  the fit's transfer against one measurement per tile is `1 / (1 +
  S(k))`, and the normalisation `S(1/l_s) = 1` makes that
  `g (k l_s)² + (1 − g) (k l_s)⁴` with `g = GRADIENT_SHARE`. Asking that
  transfer for the bar at `k = 2π / GAIN_WAVELENGTH_MM` is one quadratic
  in `(k l_s)²` with one positive root: **`k l_s` = 0.4004,
  `l_s` = 6.373 mm** at the bar itself.

  VERIFIED, AND IT FALLS SHORT AT THE BAR'S OWN ROOT (measured
  2026-09-08 on the behaviour suite's stimulus, 20 × 40 tiles, full
  support, e033's 100 mm wave, the regression of the fit on the truth).
  At 6.373 mm the solve measures **0.9399 at c2 and 0.9491 at c3** — the
  bar is not met. The cause is the FINITE PAGE and not the derivation:
  the page's INTERIOR reads the transfer exactly (0.9491 measured
  against 0.9492 predicted), and switching the curvature term off
  collapses the edge deficit from 0.0081 to 0.0015, so it is the
  fourth-order term's free-end stencil over-penalising the tiles within
  a few of the page's own edge. How much of the wave that costs depends
  on where the edges cut it: the same length measures 0.9544 on the
  53-column page this format prints and 0.9414 on the 37-column one. The
  omitted ridge is worth another 0.0014 and the measurement noise
  0.0013.

  SO THE DESIGN POINT SITS INSIDE THE BAR, by one measured constant:
  `PAGE_EDGE_LOSS` = 0.015, the worst of those deficits rounded up, so
  the derivation solves for `GAIN_BAR + PAGE_EDGE_LOSS` and the shipped
  length is **5.557 mm**. Set it to zero and the constant is the bar's
  own root again. THE GAIN, MEASURED AT THE SHIPPED LENGTH:

  | | c2 | c3 |
  |---|---|---|
  | retired tile-pinned kernel (W7) | 0.953 | 0.832 |
  | W8 build, 10.8 mm copied | 0.776 | 0.791 |
  | the bar's own root, 6.373 mm | 0.940 | 0.949 |
  | **shipped, 5.557 mm derived** | **0.957** | **0.965** |

  and on the largest page this format prints, 0.969 / 0.963 at
  53 columns and 0.957 / 0.957 at 37 — six page-and-pitch combinations,
  worst margin over the bar 0.0066.

  WHAT THE SHORTER LENGTH BUYS AND WHAT IT COSTS, all measured the same
  day at both lengths. It buys the amplitude above; it buys back most of
  the island shrinkage the review's M1 found (table below: a 2 × 2
  measured island keeps 80 % where it kept 31 %); it halves the bridging
  error inside measured territory (c2 0.123 → 0.058 dots, c3 0.501 →
  0.335 — c3 is over `FIELD_NOISE_DOTS` at BOTH lengths, which no test
  asks and which is recorded here); and it takes the c3 field past one
  fade length from 0.586 dots to 0.456 against half of its largest
  measurement, 0.509 — from over that bound to under it. It costs noise:
  a page of pure `FIELD_NOISE_DOTS`-scale noise at unit weight publishes
  **0.059 dots rms** where 10.8 mm published 0.030 and the retired
  kernel published 0.035 (W1's own measurement, at its shipped one
  twicing pass). It costs the far corner: a 1.5-dot 2 × 2 island puts
  0.298 dots at tile (0, 0) where 10.8 mm put 0.164. And it doubles what
  a tile no evidence ever reached publishes as its uncertainty,
  `sigma_dots` 3.73 → **7.26 dots**, because the pull toward zero's
  weight is pinned to the gradient's so that the fade length stays put.

- **A weak pull toward zero.** Zero is "sample at the pose", so the pull
  says: where the page was not measured, fall back to the frame the
  receiver already trusts rather than guess. Its strength is set by a
  second physical length, `FADE_LENGTH_MM`, the HALF-VALUE LENGTH of that
  pull: a tile that far from every measurement keeps at most half of the
  nearest one, and the fall continues, so a tile twice that far keeps at
  most a quarter. Pinned at **50 mm**, half the 100 mm period §0 cites,
  which is 9.2 tiles at c2 and 6.2 at c3 — long enough to bridge any hole
  the smooth model can honestly bridge, short enough not to guess the
  phase of a wander nothing was measured on. A quarter of the largest
  field this record has measured (e033's 0.83-dot Y peak) is 0.21 dots,
  under `FIELD_NOISE_DOTS`, which is why the bar at twice the length is
  "reads the pose" and not merely "reads less".

  CHANGED FROM 40 mm at the W8 spec review, and the lead may put it
  back. 40 mm was chosen to reproduce the retired kernel's own measured
  reach (non-zero to 7 tiles = 37.9 mm at c2, `PAGE-FIELD-PLAN.md` §5)
  and it sits below the charter's stated range; 50 mm is the charter's
  own form — half the field's period — and keeps that measured reach
  comfortably inside it. The definition moved too: "less than
  `FIELD_NOISE_DOTS` of the nearest measurement" cannot be implemented
  or tested as written, because it holds everywhere when the nearest
  measurement is 0.2 dots and nowhere when it is 8; a half-value length
  is a property of the pull alone.

  UNCHANGED AT THE 2026-09-08 GAIN FIX, and the lead asked the question
  that decides whether it may stay: do the two decay roots still
  separate at the shorter smoothing length? They separate FURTHER. The
  fade's slow root decays over `FADE_LENGTH_MM / ln 2` = **72.1 mm** at
  every pitch, and the smoothing's fast root over twice the smoothing
  length = **11.1 mm**, a ratio of **6.5** where 10.8 mm gave 3.3. The
  "smooth" and "faded" scales the W8 build found nearly colliding are
  now most of an octave further apart, which is the second reason the
  `GRADIENT_SHARE` window widens below.

- **A GRADIENT term beside the curvature one — AMENDED AT THE W8 BUILD
  (2026-09-08), and the lead's to veto.** Two lengths and one
  normalisation fix only two weights, and the shipped prior has three:
  `lambda_c L² + lambda_g L + lambda_z I`, the split between the first
  two named once as `GRADIENT_SHARE` and measured, not chosen. The
  reason is that a curvature penalty ALONE is fourth-order, so past the
  last measured tile the fit matches the data's value AND its slope and
  carries that slope until the pull toward zero stops it — about one
  fade length away, with whatever sign the last slope had. Built exactly
  as the two bullets above describe, that fails this section's own
  sentence and two of §6 B8's bars: beyond one fade length RMS 0.666
  against the pose's 0.580, 0.274 dots past TWICE the fade length
  against a 0.25 bar, and a field five times the nearest measurement
  where the design says at most half. A gradient term is second-order,
  matches the value only, and gives the maximum principle this section
  already asserts. The share is measured into a NARROW window on this
  suite's own stimuli — at 0.10 the fade bar still fails, at 0.35 the
  gauge's four-tile Y island is pulled off its own measurement — and
  0.2, where the fast decay root sits at twice the smoothing length, is
  the only decade where both ends hold. That the window is narrow is
  itself a finding about this pair of lengths (10.8 mm and 50 mm are
  close enough that "smooth" and "faded" nearly collide) and is the
  lead's to rule on: either this document gains the third number, or one
  of the two lengths moves to widen it.

  ONE OF THE TWO LENGTHS DID MOVE, and the window widened — measured
  2026-09-08 at the gain fix, with the length re-derived at each share
  so that the gain bar holds throughout. The gauge's four-tile Y island,
  which closed the window's upper end at 10.8 mm, now reads its own
  1.5-dot injection to within 0.052–0.058 dots at EVERY share from 0.2
  to 1.0: the island shrinkage that pulled it off was the smoothing
  length's and not the share's. `GRADIENT_SHARE` stays 0.2, unruled and
  unmoved, and re-deriving it is a separate question from the one the
  lead ruled here.

**The penalties act at two scales, and each has its own job.**
INSIDE measured territory the smoothness terms INTERPOLATE: a hole of a
few tiles between measured tiles is bridged by the smoothest surface
through its neighbours, which is exactly the smooth-field assumption this
section makes, and the pull toward zero is too weak at that distance to
drag the bridge down. Only BEYOND measured territory, where curvature
alone would continue the last slope forever, does the pull take over and
the field fade to the pose. A prior that faded across a three-tile gap
would be throwing away what the tiles on both sides already know, which
is not caution — it is a second way of being wrong.

**WHAT THE PRIOR COSTS A SMALL MEASURED ISLAND** (W8 review M1,
re-measured at the fix pass). A square island of measured tiles on a
53 × 37 c2 page, each tile carrying one +1.5-dot Y observation at unit
weight, C and M measured at zero on the same tiles, one window:

| island | 1×1 | 2×2 | 3×3 | 4×4 | 6×6 | 8×8 | 12×12 |
|---|---|---|---|---|---|---|---|
| at 10.8 mm, published on its own tiles | 0.116 | 0.468 | 0.929 | 1.127 | 1.288 | 1.367 | 1.433 |
| kept | 8 % | 31 % | 62 % | 75 % | 86 % | 91 % | 96 % |
| **at the derived 5.557 mm** | **0.627** | **1.206** | **1.354** | **1.402** | **1.440** | **1.477** | **1.491** |
| kept | 42 % | 80 % | 90 % | 93 % | 96 % | 98 % | 99 % |

RE-MEASURED AT THE DERIVED LENGTH (2026-09-08, the lead's gain-fix
ruling), same probe, same page: most of M1 is bought back by the length
the gain bar derives, which is this section's own mechanism seen from
the other side — an island narrower than the smoothing length is a
feature the smooth model does not believe, and the smoothing length
halved. What it costs is at the far corner, where the same 2 × 2 island
now puts 0.298 dots at tile (0, 0) against 0.164 at 10.8 mm; at e033's
own 0.83-dot scale that is 0.16 dots, under `FIELD_NOISE_DOTS`. The
paragraphs below were written at 10.8 mm and their MECHANISM is
unchanged; their numbers are the first row's.

The mechanism is the SMOOTHING length against the island's extent, and
not the pull toward zero on its own: an island narrower than the
smoothing length is
a feature the smooth model does not believe, and the pull only decides
where the disbelieved mass goes — to the pose. Switch the pull off and
every island reads exactly 1.500, but so does the far corner of the page
(0.042 → 1.500 at tile (0, 0)), which is the runaway of §2.4's retired
bound; so that control prices the pull's JOB, not the shrinkage. Both
lengths move it, and both have a price at the far corner: a 100 mm fade
takes the 2 × 2 island to 63 % and puts 0.669 dots at (0, 0); a 5.4 mm
smoothing length takes it to 81 % at 0.298. Evidence moves it too, which
is what a real page brings: the same 2 × 2 island at a pooled weight of
4 keeps 76 % and at 16 keeps 93 %, and on sheet J's own measured support
the review measured 91–95 % kept on all three planes.

WHY IT MATTERS AND WHY IT IS NOT A BLOCKER: a reader sampling on an
isolated scrap gets a fraction of the displacement that scrap's own
window measured — at e033's 0.83-dot peak a 2 × 2 island publishes 0.26
dots and loses 0.57, more than twice `FIELD_NOISE_DOTS` — but the miss
is toward the POSE, which is the fallback the receiver already trusts.
No bar in §6 sees it: B8(b) asks about a hole INSIDE measured territory
(where the bridge is honest, measured at 0.003 of the gain), and B8(c)
is written ≤ the pose, which shrinkage passes by construction. OPEN for
the lead with `GRADIENT_SHARE` and the two lengths; it is one question,
not three.

**Where the millimetre becomes a tile.** `lib/` is the bottom of the
receiver and names no printer: the two constants above live in
`lib/plane_field.py` because they are this design's numbers, and the
SCALE that turns them into tiles — printed dots per millimetre, which is
`HW_DPI / MM_PER_INCH` and is the format's constant — is handed in by the
plugin that builds the prior (`default_prior(cell_dots, dots_per_mm=…)`).
So the solve converts, and nothing under `lib/` reaches up for a
resolution. Pinned by `test_h3_field_consumers.test_the_evidence_layer_imports_no_plugin_and_no_format`.

**Uncertainty is published per tile**, beside the value, in dots, as part
of the `PlaneField` fact. It grows with distance from evidence and shrinks
as AGREEING evidence arrives — QUALIFIED 2026-09-12 (the external
review's R9, and the qualification is the finding): it is bounded above
by `sigma_dots` always, because that is what a prior is, but it is NOT
monotone in the evidence. The weights are the robust loss's, so evidence
that CONFLICTS with what stands re-weights the rows already there and a
tile can come out less determined than it was: measured on a c3 1×2 page,
a tile read a grid step out publishes 0.431956 dots alone and 0.458141
once a window reading every plane in register lands beside it (+6.06 %,
the fit's own fixed point at 212 reweighting passes, inside the 250-pass
ceiling `IRLS_MAX_PASSES`; a 50-pass ceiling published the capped iterate
0.465298 and said so). The number
is not forced downward — a page less sure of itself after being
contradicted is the honest report. No reader is gated on it — the "no
floor, no gate" ruling of §2.8 stands for readers — and nothing is
shrunk toward the pose because a tile is uncertain. The diag shows it
and the harness reports it, which is how a sparse page now says out loud
what it does not know.

WHAT THAT NUMBER IS, and it is not the posterior standard deviation (W8
review M2, measured at the fix pass). `lib/plane_field._uncertainty`
publishes `sigma_dots · sqrt(diag(V) / diag(V0))`: the fraction of the
prior's ignorance the evidence has NOT removed, put back on the prior's
own stated scale, which is what makes a page with no evidence read
`sigma_dots` exactly at every tile, corners included. On the behaviour
suite's stimulus it is **19.4×** the posterior deviation
`FIELD_NOISE_DOTS · sqrt(diag(V))` at every tile, supported and faded
alike — 1.000 published against 0.049 on the supported band, 3.11
against 0.158 on the faded one. RE-MEASURED at the derived smoothing
length (2026-09-08): **18.1×**, 1.738 published against 0.096 supported
and 6.784 against 0.419 faded, `sigma_dots` 7.257 — the multiple is the
prior's shape and barely moved; the scale doubled. Neither is the fit's
actual error, which on those supported tiles is 0.141 median and 0.375
worst at 10.8 mm and 0.026 / 0.138 at the derived length: a posterior
deviation prices the VARIANCE and this prior is biased by construction
(the amplitude loss above), so the honest bar sits between the two and
nearer the published one. Nor is `sigma_dots` the prior's marginal
deviation at a tile, which is 0.165–0.268 dots: the smoothness terms
already say a great deal about a tile before any evidence arrives, and
`sigma_dots` is what the pull toward zero alone would say.

The SPELLING is therefore the lead's, and one of three: publish the
posterior deviation and re-argue B8(d) against it; keep this quantity
and name it in the fact and the readout; or state it here and leave
both. What may not stand unstated is a diag row reading `Y 0.31±1.99
dots` with nothing saying which of the three the second number is.

WHAT THE TILE-PINNED BANDWIDTH DID, measured, and why the length moved
into millimetres. `smooth_local_linear` at `BANDWIDTH_TILES` 2.0 and
`TWICING_PASSES` 1, full support, interior columns, against a 100 mm
sinusoid (the first two rows measured 2026-09-08 at W7, the third the
external review's numerical extension of the same kernel):

| pitch | tile width | 100 mm in tiles | amplitude kept |
|---|---|---|---|
| c2 | 5.419 mm | 18.45 | **0.957** |
| c3 | 8.128 mm | 12.30 | **0.835** |
| c4 (numerical extension) | 10.837 mm | 9.23 | **0.635** |

The module's own bar is ≥ 0.9 for one twicing pass, so c3 was already
under it and c4 badly so, while every product replayed to date is c2 —
latent, not harmful, and at c3 the loss on e033's own 0.83-dot peak is
0.14 dots, under `FIELD_NOISE_DOTS` 0.25. A penalty in millimetres removes
the pitch from the question; the behaviour suite measures the gain at both
pitches and on both axes (§6 B8).

RETIRED HERE: **the per-plane, per-axis publication bound** (RULED
2026-09-08, W7 R3 — the published field clipped at that plane's largest
tier search radius less the saturation margin). Two reasons, and the first
is the external review's F7: the bound was derived in the RAW measurement's
coordinates and applied to the GAUGED quantity, and the range of a
difference is not the range of either measurement. At c2, raw certified
C −2, M −2, Y +2 dots all sit inside the accepted radius; gauged, Y is
+4, and the solve clipped a legitimate measured differential to 2.24. The
second reason is that the bound was answering a question the prior now
answers properly. It was introduced because the smoother extrapolated into
regions nobody measured, and a hard clip bounds that runaway without
addressing it: on the same sparse-support stimulus the library test uses,
72 of 1,961 tiles carry observations, 1,256 unsupported tiles receive
extrapolated corrections, ten hit the bound, and the RMS error on the
extrapolated tiles is **0.621 dots against the zero-field pose's 0.584**
(external review §3, maximum error 1.774) — bounded, and still worse than
doing nothing. A pull toward zero acts on the estimate in the published
quantity's own coordinates, clips nothing that evidence supports, and
makes the unmeasured region fade to the pose rather than to a wall.

The measured record of what the unbounded smoother published stands as the
reason the prior exists. On `L:c2-cmy8-r0547@53x37`, load 1a, pre-W7 tree,
page 1's Y published **8.301 dots at tile (8, 0) with support 0.0**, three
tiles from the nearest supported tile — 5.6× the largest supported value
on that plane (1.484) and 2.6× the 3.168-dot ceiling on any single Y
observation; 1,696 of that face's 1,780 unsupported tiles read non-zero
(95 %), 56 tiles exceeded 2 dots (every one unsupported) and 17 exceeded
4. C was not clean either: page 1 published 2.841 dots at an unsupported
tile where its largest supported value is 0.745. Across the six
page-planes 68 individual components exceeded the 2.24-dot reach, the
largest at 7.372. With the W7 bound in place the same replay published 26
components sitting exactly at 2.24 and none above (page 0 C 1, page 1 C 2,
page 1 Y 23) — the bound biting on a real capture, on two planes and both
faces, which is also the measurement of how much extrapolation the prior
now has to answer for. On a supported page none of it bites: sheet H, with
0 unsupported tiles on any plane, published max 0.5432 / 0.5533 / 1.0608
dots, every one inside the reach. The tier reaches themselves stay
`field_tiers.measurement_reach_dots` and stay a statement about what a
correlation can see — 2.24 dots per plane at c2 and 3.49 at c3 with
`CERTIFIED_RADIUS_CELLS` at 1.25, measured 2026-09-08 — and the swim's
per-window search stays bounded by the printed cell, a bound in printed
cells being a different quantity from a radius in dots (`plugins/swim.py`,
W7).

### 2.5 Evidence (AMENDED 2026-09-08, W8 R-C and R-E)

**A row is one measurement of one plane on one tile from one capture**:
`(capture, page, tile_code, plane, delta_dots_xy in page axes,
measured_xy, weight, source, window, pose_generation)`. `measured_xy` is a flag per AXIS: an axis
nobody measured is marked unmeasured and enters no sum, which is not the
same statement as a measured zero. **Nothing is subtracted from a row** —
the gauge is a constraint on the fields (§2.3) and the window's own error
is a parameter of the solve, so a row is raw evidence and stays raw. Rows
are per plane, and a row exists for every plane a window could measure,
independently of what the other two planes did.

**There is ONE measurement primitive.** Correlate a known template against
that plane's channel at the window's pose over a two-axis grid of
page-axis offsets, and accept only what a null-calibrated threshold
admits. Both axes, always: the M281's dominant term is y and nothing in
this line has ever exercised it. Two template sources, and no third:

1. **The certified pattern OF THAT PLANE.** A certificate fixes every
   printed cell of the plane it certifies, so plane p's channel is
   correlated against p's own known bit image at the owning window's pose
   — up to 4,096 cells, gain ≈ 1.0 (measured `plugins/field_tiers.py`
   anchor tier: 1.000 injected, 0.947–1.002 on sheet I). This is
   stateless: bits from the certificate, pose from the owning window,
   raster from the capture, re-measured when the pose moves, memoised on
   the pose version. Nothing is stored on the certificate and nothing ever
   invalidates one. A tile the swim wins enters exactly this way — the win
   mints the certificate and the correlation measures it on the next
   solve; the swim's own affine is not kept.
2. **The furniture of that plane.** Word and dust sites at their known
   values, per plane, by weighted NCC around the pose (dust carries Y;
   word sites do not). Truth-free, available the moment a window is
   addressed.

**PER (TILE, PLANE), never per tile** (AMENDED 2026-09-08, W8 R-C; the
external review's F3). The design sentence "a certificate fixes every
printed cell of all three planes at its tile" is FALSE for CMY8, where a
certificate labels only its own plane
(`plugins/color_sites.py:76` is the format authority and always said so),
and the implementation encoded the mistaken premise twice: `window_sites`
kept only cells known in all three planes and `certified_whole` required
the whole three-plane tile before the certified template was allowed at
all. Measured on the existing fixture: with C certified the projection
exposes **[4096, 120, 120]** known C/M/Y cells and the collector retained
**120**; with C and M certified and Y unfinished it exposes **[4096, 4096,
120]** and the collector again retained 120 and refused the certified
tier — **3,976 authoritative payload cells discarded per certified
plane**, at exactly the moment they are most useful, because strong C and
M evidence is what stabilises the frame that Y is then measured in. Under
this section the tier is chosen per (tile, plane) against that plane's own
known mask: a certified C correlates its whole template while M and Y are
still on furniture, and the source is attributed per row.

**RETIRED HERE: the blind tier** (the held-out log-loss sweep on the
plane's own labels, `field_tiers.blind_offset` and
`fields_collect.measure_blind`). It selects an offset by the lowest
held-out loss and accepts any improvement over the centre above 1e-4, so
the held-out set has been used for model selection and a positive
improvement on it is not independent evidence that the displacement
exists; the near-zero weight floor does not correct a selection effect.
Measured through the PRODUCTION collector by the external review
(`yellow_noise.py`): keep correctly printed and registered C and M in the
four-tile fixture, replace only Y with independent smooth random noise,
and across 20 Y rasters every Y anchor measurement was rejected while
**11 of 20 collections nevertheless published Y through the blind tier**
(44 rows), false solved Y corrections reached **1.875 dots**, and in one
trial corrections above 0.25 dots spread across **28 tiles of a 100-tile
page** — beyond the four tiles anything was observed on. The kernel
reproduction accepted 141 of 200 smooth-noise trials and 134 of 200
unrelated binary-cell raster trials after the improvement, weight and
saturation filters (`estimator_counterexamples.py`). These are conditional
estimator false positives, not measured wrong certificates; they are
enough. A calibrated first tier is worth nothing if its rejection hands
the same noise to an uncalibrated second one.

**What retiring it costs, honestly.** The blind tier was the only source
that needed no template, so it was the only path to a field on a plane
that carries neither certificates nor readable furniture — which is
exactly the M281's starved Y (e030: C 620 / M 43 / Y 0 certificates).
Those pages now publish **no Y field at all**, their readers sample Y at
the pose, and that is what the receiver did before this line existed: the
loss is a field that was not trustworthy, and there is no dead-plane sheet
in this record where a blind Y field bought a certificate. What the two
template tiers reach is a different question and it is NOT yet measured
per source: sheets H and I are certified end to end, sheet J's ten-load
support is 81–82 % of a face on every plane, and no product splits that
support by SOURCE, so the blind tier's own share of it is unknown. The
charter rules the retirement on the false-positive evidence and quotes
82–100 % reach for the two template tiers; **the per-source census is
OWED with the W8 replays**, and if it shows the blind tier carrying a
material share of a real page, the ruling is worth re-opening with that
number in hand. A plane with no template reads "unknown" (I13), never a
guess.

Also retired: the linearised photometric tier (gain 0.46–0.53 against the
printer's real displacement, 1.000 against an injected one — an
unexplained anomaly, §7;
`src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:232-235`).

**THE ACCEPTANCE IS NULL-CALIBRATED, once, for the one primitive.** A
peak is admitted when its quality clears `min_quality(n_sites,
n_candidates)` = the measured null's own 99th percentile, which is

```
(0.2217 * ln(candidates) + 2.2750) / sqrt(sites)
```

— `sites` being how many template cells the correlation had to work with,
`candidates` how many offsets the grid scored. Both directions are the
ones a reader would guess: more sites make a chance peak smaller, so the
floor falls; more candidates give chance more chances, so the floor
rises. (The source writes the same expression as
`(0.2217 ln S + 2.2750) / sqrt(n)`, where `S` is the CANDIDATE count and
`n` the site count — the opposite of the argument order, which is why it
is spelled out here.) This is SYNTHETIC and it stands:
re-drawn at the W7 review from 500 trials at every template size the
certified tier uses (512 … 4,096 sites, radii 1.5 and 2.5), the fit tracks
the drawn p99 within 5 % — ratios 0.959–1.049 — over a 16× extension of
the support it was fitted on, and keeps 0.6–2.0 % of the null. One
absolute floor across two tiers was two mistakes at once: at the old
shared 0.10, driven through the tier's own kernel, the null peak quality
of an ink-independent template is 0.407 at 24 sites and 0.046 at 2,240, so
98–100 % of pure noise cleared on the small templates and nothing strong
cleared on the large ones. Evaluated at the template sizes the sheet-J
fossil run actually presents (2026-09-08, W7b review-fix): certified
templates 1,384–4,096 sites, median 3,833, floor **0.0586** over that
tier's 441-candidate grid — under the carried absolute 0.10, so it admits
where 0.10 refused; furniture templates 24–64 sites, median 33, floor
**0.594** on C and M's 169-candidate grid and **0.631** on Y's 441 — six
times 0.10, and that is where it bites.

*Which null.* The table is drawn against a SMOOTH random field. A real
plane channel is cell-structured, and under that model the same kernel's
null MEDIAN is 0.57–0.88× and its p99 −20 % to +4 %. So the floor, which
is cut from the p99, is insensitive to the model; a peak read as a
multiple of "its null" is not. On the identity the page was printed with,
the certified tier keeps **600 of 600** calls at median quality **0.820**,
the median call sitting at **13.2×** its own floor with the worst at
**6.9×** (both fall to 12.5× and 6.5× at the radius-4.0 headroom pass) —
nowhere near either null model. A null measured on a real scanned plane
channel is still owed; it decides how much a MARGINAL peak carries, and
this population has none.

**THE SEARCH RADIUS — the lead's open question, unchanged by W8.** R2's
rule stands (the smallest swept radius at which fewer than 5 % of the
peaks the tier KEEPS sit at the wall) and W7b re-derived its answer on the
fossil — 200 tiles × 3 planes, each call scoring one radius-4.0 grid whose
narrower radii are its centred sub-grids, so all four saw the same photons
(`scratchpad/w7b/probe_radius.py`, 254 s of CPU):

| radius, dots | cells | candidates | kept | at wall | \|d\| p50 / p90 / max |
|---|---|---|---|---|---|
| 1.50 | 0.75 | 169 | 600 | 3 (0.5 %) | 0.369 / 0.746 / 1.512 |
| 2.00 | 1.00 | 289 | 600 | 0 | 0.369 / 0.746 / 1.651 |
| 2.50 | 1.25 | 441 | 600 | 0 | 0.369 / 0.746 / 1.651 |
| 4.00 | 2.00 | 1089 | 600 | 0 | 0.369 / 0.746 / 1.651 |

0.75 cells passes the rule at 0.5 %, but its three wall peaks are real C
displacements of 1.28, 1.40 and 1.65 dots, and at 0.75 cells the tier's
reach bounds what it can see at 1.24 dots — below displacements this sheet
shows. 1.0 cell clears both and is refused by the swim row's licence (its
translation bound is one printed cell and must sit inside this reach on
every plane and row). 1.25 is the next step up, and is what ships.
**What the width buys on this sheet is nothing**: all 600 peaks are
identical from 1.0 cell outward, 598 of 600 already at 0.75, and given
3.74 dots of reach no peak moved past 1.651 — the 441 candidates are paid
for the licence and for a sheet whose displacements exceed 1.74 dots. What
the widening costs, measured on the printed identity, load 1a, same
extract and scan: the collection goes **65.2 → 97.7 s of CPU, +49.8 %**
(wall 83.4 → 115.4 s); on a wholly certified page the certified tier IS
the collection, so sheet H's 1,921.6 s scales by that factor. **OPEN for
the lead: 0.75, 1.0 or 1.25 cells, on that table with that cost beside
it.** The external review adds one argument against the ONE-CELL aliasing
premise the radius was first cut from — a whole known tile is a
pseudorandom bit pattern, not a lattice, so a one-cell shift moves the
wrong bits under the template rather than repeating it — which does not
change the table but does mean the ceiling is an ambiguity question to
measure, not a period to assume.

**The per-class site floor stays** (RULED 2026-09-08, W7 R5: the anchor
tier's site gate counts the MINORITY class, as the blind tier's already
did). The reason is the format's and is identity-robust — measured over
all 1,961 tiles of a face (`pilots.word_site_cells_yx` and
`dust_site_cells_yx` on `sites_seed`, split by `geometry.site_parity`):
the even-parity anchor half is 64 sites, 53 word and 11 dust, and its
minority class runs C 19–32 (median 29) and M 19–32 (median 29) against
**Y 3–11, median 7**, because Y carries no word ink and its polarity comes
from the dust sites alone. Y's minority falls below four on 1 tile of
1,961 on a whole face and never for C or M. What makes the gate bite is
the CUT, not the tile: the audit measured Y's minority below four in
41.8 % of simulated scrap cuts, where a 32-site template with ONE minority
site survives both the quality floor and saturation at a median error of
0.47 dots and a quality of 0.584. That simulation is synthetic and stands.

**WHAT THE FLOORS COST, measured, and the lead's second open question.**
On the printed identity, over the same capture, the W7 floors publish
**1,251 observations against 1,366, −8.4 %** (page 0 C/M/Y 254/258/179
against 252/259/246; page 1 211/198/151 against 211/198/200), and no plane
on either face is the zero field. **The whole loss is Y's**, and it is
these two floors' and not the gauge rule's (§2.3, measured). Per tier: the
certified tier keeps **600 of 600** calls, at median quality 0.820, and
would have kept all 600 under the flat 0.10 too, so it is untouched; the
anchor tier scores 129 calls per plane and loses **one of 129 on C and one
on M** against **120 of 129 on Y** — 58 refused by `ANCHOR_MIN_PER_CLASS`
(minority 1–3, which the old all-one-class gate passed) and 62 by the
size-aware floor (quality ≥ 0.225, which 0.10 kept), leaving 9. The three
planes read the SAME site set — 24 to 64 sites, median 33 on each — so the
size-aware floor sits at the same height on all three; what differs is the
polarity behind it, minority 7–28 (median 14) on C and 8–31 (median 14) on
M against **1–9, median 4** on Y. That is why one plane-blind pair of
floors lands on one plane. It is a YIELD change ruled in direction and not
in magnitude, and no certificate has been counted either way. **OPEN for
the lead.**

Three rules, one of them amended:

- **One observation per (capture, tile, plane)**, taken at the finest
  decimation level that has a placement covering the tile. Levels are the
  same photons; they never add weight. This is the multi-scan law ("never
  sum raw and decimated") applied to registration. OPEN (external review
  §3): "finest level owns the tile" should not prevent falling back to a
  coarser, adequately supported window when the finest one has too little
  usable template — choosing one informative measurement still respects
  the same-photons rule. Not built in this wave.
- **Every delta is mapped from window pixels to page dots through the
  inverse of the owning pose's linear part** — one operation that handles
  the scrap's orientation, scale and shear together. No separate rotation
  bookkeeping anywhere.
- **Sources are attributed per row and never double-counted.** AMENDED
  2026-09-08 (W8): the three-way parity partition of
  `plugins/field_tiers.py` (certified cells; furniture at even parity;
  furniture at odd parity) existed so that the blind tier's evidence was
  independent of the anchor tier's. With the blind tier retired there are
  two sources per (tile, plane) and they are disjoint by construction —
  payload cells against furniture sites — so the furniture template is
  that plane's WHOLE furniture set at that tile and the parity split has
  no consumer. The arithmetic consequence is stated, not claimed as a
  yield: the template doubles, the size-aware floor falls as 1/sqrt(S),
  and Y's minority class — the population the per-class floor refuses on
  cut scraps — doubles with it. The W8 replays measure whether that is
  worth anything.

### 2.6 The solve (AMENDED 2026-09-08, W8 R-B and R-F)

One solve per page, over every plane and every window at once. The
unknowns are the three plane fields on the page's tile grid under the
gauge constraint of §2.3 — which leaves two free fields, the C−M
differential and Y — and one translation `t_w` per window. The objective
is the evidence under a ROBUST loss, plus the two penalties of §2.4: a
lane that latched onto a wrong minimum is off by a whole grid step, and
one such row must not be able to drag a tile. That robustness is what the
per-tile weighted median used to provide; the median's own price is
measured and small (median against mean on sheet H differ by 0.03 dots,
`analyzer/FIELD2-2026-09-03.md:349-354`), and a robust loss keeps the
protection while letting one problem be solved once instead of three times
in sequence. Rows enter component by component: an axis marked unmeasured
enters no sum, and no plane's field is coupled to another's except through
the gauge and through the windows they share.

The solve publishes, per page:

- the per-plane grid in printed dots along the page axes;
- the per-tile UNCERTAINTY beside it (§2.4);
- the support grid (pooled weight per tile);
- the residual energy **per (capture, plane)** — never summed across
  planes before it is recorded (AMENDED 2026-09-08, W8 R-F). The external
  review's arithmetic is the reason: 100 perfectly explained C
  observations, 100 perfectly explained M observations and one Y
  observation with a 1-dot residual at equal weights give Y a ratio of
  **8** and the summed report **0.040**. Healthy, abundant word-plane
  evidence hides exactly the poorly supported Y this diagnostic was
  introduced to expose. The offline harness had kept the per-plane values
  all along; the production event had not;
- the evidence revision it was fitted at (§2.7);
- how many reweighted passes the robust loss took and whether they
  reached its fixed point (NEW 2026-09-12, the review's R2). The fit
  iterates until the Huber multipliers recomputed from its own residual
  agree with the ones that produced it, under a ceiling of
  `IRLS_MAX_PASSES`; the ceiling is REPORTED and never a refusal,
  because the objective is convex and the capped iterate is the best
  answer reached, so `passes` and `converged` travel with the solve and
  a reader can tell an optimum from an iterate. Diag-only, like the
  residuals: nothing gates on them.

The window nuisances are NOT in that list, and the distinction is the
whole guard of §2.3: the solve RETURNS them on its own result object, for
the diagnostics and the harness to read in the same process, and no
published FACT carries them — not `PlaneField`, not `FieldSolved`. A
nuisance that reached the fact stream would be a per-window field with
another name, and the next reader would sample through it. Pinned by
`test_h3_field_consumers.test_no_published_fact_carries_a_window_nuisance`.

Support, uncertainty and residuals are REPORTED. Nothing gates on them.

### 2.7 Revision, and when the page re-solves (AMENDED 2026-09-08, W8 R-D)

**The store keeps one integer revision per (capture, page).** It is
advanced by every placement birth, change or removal on that page and by
every certificate on it; by nothing else. The collect row's ordinal IS
that revision, so a collection whose inputs really changed is never
mistaken for one already done. A page whose LAST window leaves publishes
an EMPTY collection under a new revision — removal is a state transition,
not the absence of work — and the page then re-solves to no evidence: zero
field, full uncertainty, which is the honest statement that nothing is
known and the pose is what readers should use.

**A resume restores the number; it does not recount** (RULED at the W8
spec review; the lead may reverse it, and the alternative is named).
The revision counts EVENTS, and events are not recoverable from the facts
that survive them: a placement refined five times is snapshotted once, and
a placement that has left page 0 leaves page 0 no trace at all. So a
resumed run that recounted would come back with a LOWER number than the
interrupted run had reached — and the collection fact it restored beside
it carries the higher one, so every fresh collection would be outranked by
a restored one until enough new events arrived. The number is therefore
carried in the snapshot, one integer per (capture, page), and restored
with it. The alternative, if a schema line is unwanted: restore the
revision as at least the ordinal of the standing collection the resume
folds. Both keep the number monotone across a resume, which is the
property that matters; recounting does not.

**The page re-solves whenever its evidence revision changed, and
publishes only if the field moved.** No statistic decides whether to
solve. The cost measurement is the whole argument, and W8 MOVED IT BY
TWO ORDERS OF MAGNITUDE (review M4, re-measured at the fix pass). The
retired per-plane pooling ran 0.107 s against a collection's 1,921.6 on
sheet H (1:18,000) and 0.035 against 97.7 on sheet J's one capture
(1:2,800); the joint fit of §2.6 reads **6.165 CPU-s against 89.9 on
that same capture, 1:14.6** — three runs of it over this wave give 1:12
to 1:16, the spread being the machine's. Solving is now six to eight per
cent of collecting rather than a rounding error. The RULING does not
change, because the direction of the risk has not: a rule that skips
solves optimises the cheap half of the work while risking the expensive
direction, which is not solving when the field should have moved. What
changes is that the margin is no longer unbounded — the dense factor is
cubic in `2 · n_tiles + n_windows`, so a page an order of magnitude
larger, or a confetti page with thousands of windows, puts this question
back on the table. The requalification's ten-load sheet-J replay is
where that is measured next. Duplicate publication is suppressed by comparing the
solved field to the standing one, which is a fact about the OUTPUT and
needs no model of the input. MOVED means (RULED 2026-09-12, §7.1): the
decision is one for the page's three planes — publish all of them when no
field stands, when any plane's support presence changed, or when the
largest per-tile change over all three planes exceeds `FIELD_NOISE_DOTS`,
the measurement's own resolution; counts and uncertainty alone never
publish. Bit-identity was the review's proposal and is refused on the
sheet-J numbers: one added observation moves nearly every cell of a
penalised fit, so it would publish on every solve — 105 of them after 120
collections on that page, each re-arming every row that reads the field.

**THE REVISION IS BOOKKEEPING, NOT A TRIGGER** (W8 charter §3 item 6b —
the clause this section owes because W8 is the wave that makes the
revision move on every certificate). Advancing it costs nothing and must
buy nothing. Three consequences, and each is a rule:

- **Collections coalesce.** Ten certificates arriving on a page between
  two admissions of the collect row advance the revision ten times and
  cause ONE collection, when the ladder next admits the row. The revision
  says what the collection would be measuring, not when to measure.
- **A collection re-measures only what moved.** The tiles whose inputs
  changed — a new or moved pose, a new certificate — are re-measured; the
  rest are carried from the standing collection under the memo of §2.5
  rule 1. A page of 1,961 tiles that gained one certificate pays for one
  tile, not for 1,961.
- **A publication that did not move the field wakes no reader.** The
  solve runs on a changed revision, but it publishes only if the field
  moved, and only a publication is a wake. So the colour head refits once
  per REAL field change — never once per certificate — and records the
  revision it used.

- **A placement whose POSE did not move still advances it.** The store
  advances on every ADOPTED placement fact, and `data.placement_ordinal`
  admits one whose affine is identical and whose quality is better. The
  three rules above bound what that costs — every row carries under the
  memo, so the collection re-measures nothing; the field cannot move, so
  nothing is published and no reader wakes — but it is one collection
  and one solve bought by an adoption that changed no measurement, and
  this section's "by nothing else" is aimed at that kind of purchase.
  RECORDED, not changed, at the W8 fix pass (review's MINOR 5): R-D
  words the rule as "every placement birth, CHANGE or removal", and a
  better-quality adoption is a change of the standing fact. The lead's
  option, if the purchase is unwanted, is to advance on the affine
  rather than on the adoption — one clause in
  `store_folds._fold_placement`, where `affine_changed` is already
  computed for the done-cell stamp.

Without the first three, the fix that makes the revision honest would
make the page re-collect on every certificate, which is the expensive
direction. PROVED BY behaviour-suite line 6b in
`test_h3_field_lifecycle.py`, through the scheduler rather than the two
rows' prepare functions, because coalescing is a scheduling claim.

**Every consumer records the field revision it was fitted with**, and a
refit is owed whenever the standing revision differs. Two integration
defects the external review reproduced are exactly this rule missing:

- **F6.** A new window and a field publication arriving before the colour
  row runs let `prepare_color` choose its cheap assembly stage; the engine
  marked the field version tried, clearing the assembly debt emitted no
  new wake, and no refit followed — debt zero, still one head fit, one
  cost-15 assembly job, an empty queue, the old head and the old evidence
  row, worker and tried version both 2. A corrected head then reads new
  windows through the LATEST field with a detector fitted in the old
  feature space. **The colour head's assembly stage may not clear a refit
  debt.**
- **F10.** An adopted colour pose could not refine after a field-only
  change, because eligibility required a strict increase in certificates
  while the row subscribed to field versions. The anti-churn rule is right
  and stays; "same inputs" must include the field. **The refinement basis
  includes the field revision** — the held-out adoption gate and the
  "already stood here" pose guard are unchanged.

RETIRED HERE: **the residual-energy trigger**, in all three of its forms —
the page-wide Σ w·r² (RULED 2026-09-07), the per-tile statistic (built at
W2, ruled at W5's landing), and the argmax-of-ratio correction (RULED
2026-09-08, W7 R4). W7's correction was real: selecting the loudest tile
by the DIFFERENCE `energy − expected` and deciding by the RATIO does not
rank the same page, and on a confetti page the per-tile weight span is
675× to 2,330× across the six page-planes of the load-1a solve, so a heavy
tile just under the bar was picked while a faint tile far over it was
never examined. What W8 retires is the statistic itself, on arithmetic the
correction does not touch. It is a weighted mean squared residual, not a
measure of whether the estimate would move:

- Against a standing ZERO field, 1, 10 or 1,000 exact observations at
  +0.4 dots all give the same ratio, **1.28** — `r²` over the noise
  expectation `2 · FIELD_NOISE_DOTS²` = 0.16 / 0.125 — under the margin of
  2 that shipped. No amount of agreeing evidence can cross it, and solving
  would have returned essentially +0.4 dots. More evidence must never be
  unable to change the answer.
- Nine zero observations and one +2-dot outlier pool to zero, yet read
  **3.2 after solving** (Σ w·r² = 4 against an expectation of 1.25), so an
  unrelated collection change re-schedules the same unproductive refit
  forever. The engine's unchanged-state guard stops the loop; it does not
  make the statistic mean anything.

A trigger built on the expected MODEL CHANGE and its uncertainty would be
a different object and might earn its place if solving ever costs
measurable time. On the measured cost it does not, and the rule is "solve
when the evidence changed".

### 2.8 Application (unchanged at W8 but for one reachability rule)

There is ONE mapping and its inverse, and nothing else connects page
space to the raster. Forward: page cell → field → pose → pixel. Inverse:
pixel → pose inverse → subtract the field at the estimate (one Newton
step; the field is small and smooth). Cells, tiles, windows and regions
are page-space objects and all go through it; a window pose is the pose
for that window's cells. The survey is the only stage outside it, because
it has no page coordinates yet — it generates the hypotheses the mapping
is built on.

- **Per cell.** The field is evaluated at each cell's own page coordinate,
  never once per tile or window (§1, the gradient).
- **No floor, no gate, no adoption granularity.** The field applies
  everywhere; it is zero where nothing has been seen and better than the
  pose where something has. Consumers that can afford a search (the swim,
  local, pose refinement, and — AMENDED 2026-09-08 — the plane-as-K
  read's scalar x sweep) start from it and refine without shrinkage;
  consumers that sample once per plane (the ordinary payload read) adopt
  it. The colour lane's held-out comparison of corrected against raw
  features stays as the null safety for the adopters. "Per-block
  adoption" and the 0.25-dot publish floor are gone with the gate they
  belonged to. The plane-as-K read was listed as an adopter here while §4
  already retired its "do not search when a field stands" rule; the build
  followed §4 and this sentence is corrected to it. AMENDED 2026-09-08
  (W8): the per-tile uncertainty §2.4 publishes does not gate either. It
  is a diagnostic beside the value, and a consumer that samples once still
  samples at the field; making uncertainty change what a reader does would
  amend this ruling and is not proposed.
- **Numerical equality keeps the field (RULED 2026-09-08).** A searcher
  moves off the field's own value only when a candidate improves its
  objective by more than that objective can resolve. This is a statement
  about resolution, not a bar the search must clear, and it is not a
  shrinkage: it exists because a flat basin's argmin is arithmetic.
  The plane-as-K sweep spells it as `LOSS_TOLERANCE = 1e-6` in held-out
  log loss (`plugins/plane_k.py`); measured on its own synthetic stimulus
  the rival of a CORRECT field wins by 6.3e-12 and the rival of a field
  0.75 dots short wins by 3.8e-2, so nothing the objective can resolve is
  held back. Measured in the same pass, and NOT what the ruling
  anticipated: the box aperture's basin is about one dot wide, so at half
  a dot short the argmin is already the nominal shift with no tolerance
  applied at all — that limit is the objective's and no tolerance can
  move it.
- **A field value may never be an admission condition (AMENDED
  2026-09-08, W8 R-E).** A consumer decides whether a CANDIDATE is usable,
  never whether the search may start. `plane_k.read_window` required the
  initial field-shifted points to lie inside the raster and only then let
  the sweep evaluate the zero-field candidate, so a fallback existed that
  a bad starting field could make unreachable: on the existing c3 2×2
  raster cropped to its page edge the nominal pose yields an accepted mix
  at held-out loss 0.0038835, and an allowed −3.49-dot field turns the
  whole read into None (external review F9, `planek_border.py`). The rule
  is general — initialise from any viable candidate and reject candidates
  one at a time — and the plane-as-K sweep's pose candidate (W7 R6) is the
  case that has to be reachable.
- **Consumers carry the field revision they were fitted with** and owe a
  refit when the standing revision differs (§2.7). Sampling geometry and
  the detector fitted for it are one version, not two.
- **Always on** for colour families; there is no dial. The null proof is
  a measured statement (§6 B1), not a switch.
- **Any consumer holding a page-position hypothesis** — pose refinement,
  word validation, the cold search for scraps below one word — may render
  per-channel templates through the mapping at each plane's offset. The
  hook is the mapping itself; what uses it is the workplan's business.

### 2.9 What the field never carries

A window's own pose error, which is the nuisance the solve estimates and
never publishes (§2.3); anything indexed by capture, level, lane or
window; a per-plane Jacobian parameter; a scanner term; a parametric
engine model. A per-engine prior over fields (form across
sheets, phase per sheet) is a natural later object; it is a prior over
this one, not a different one.

---

## 3. Invariants (each one pinned by a test in the receiver workplan)

| # | invariant |
|---|---|
| I1 | One `PlaneField` per (page, plane). No fact, cell or accessor keyed by capture, level or lane. |
| I2 | `delta_dots_xy` is in printed dots along the PAGE axes; a one-dot field moves the sampler one dot along the named page axis at rot 0, 1, 2 and 3. |
| I3 | Gauge: `F_C + F_M = 0` at every tile of the page; Y free; K identity. AMENDED 2026-09-08 (W8 R-A): the gauge is a constraint on the FIELDS, not a subtraction inside a window — each window carries one plane-common translation, estimated with the fields, published nowhere and applied by nobody. The same set of measurements yields the same fields whichever planes a given window happened to see. |
| I4 | One observation per (capture, tile, plane); a second level of the same capture adds none. |
| I5 | The gauge is the ONLY coupling between planes, and it couples C and M by definition — they are the two halves of one differential (measured on sheet H: M = −0.970·C − 0.0008 on x, §7). Y takes no part of it, and no plane ever reads another's field: a plane with no evidence fades to the pose under the prior (I6) and is marked unknown (I13). |
| I6 | The field always exists for a colour family, and away from evidence it fades to the pose. AMENDED 2026-09-08 (W8 R-B, replacing W7 R3's clip): the prior, not a bound, governs the unmeasured region — a curvature penalty at `SMOOTHING_LENGTH_MM`, which BRIDGES a hole inside measured territory, and a pull toward zero at `FADE_LENGTH_MM`, its half-value length, so a tile twice that far from every measurement keeps at most a quarter of the nearest one and reads the pose; every tile publishes its uncertainty beside its value (§2.4). |
| I7 | Every application of a standing field to a page coordinate goes through the one mapping — `lib/page_map` is the only module that calls `plane_field.evaluate` or binds it (pinned, `test_h3_page_map.test_only_the_mapping_turns_a_standing_field_into_dots`). AMENDED 2026-09-08 (W7): the earlier wording, "every reader of raster pixels from page coordinates … the survey is the only exception", was broader than both what W6 verified and what the tree gates. W6's gap hunt classifies raster reads into THREE categories, two of them allowed: (a) the pose's own cell→pixel reads with no field (`calibrate`, `refine`, `pose`'s four samplers, `color_region_anchor`'s point primitives, `color_region.region_window`, `color_refine.revised_native_affine`), (b) the survey, which holds no page coordinate yet, and (c) a field application outside the mapping — of which there are none. The invariant is (c); (a) is a named category, not an exception. |
| I8 | No publish floor, no precision gate, and — AMENDED 2026-09-08 (W8 R-B) — no clip: what the solve produces is what the readers sample through. CLARIFIED 2026-09-12 (the R1 ruling, §7.1): "no floor" is about the field's MAGNITUDE — no displacement is too small to publish or to sample through; §2.7's duplicate suppression, which asks whether the joint solve MOVED against the standing field by more than the measurement's own resolution (`FIELD_NOISE_DOTS`, the anchor step) or changed any plane's support presence, is not a floor, and it decides for all three planes at once. The per-plane per-axis publication bound of W7 R3 is RETIRED: it was derived in the raw measurement's coordinates and applied to the gauged quantity, so it clipped legitimate differentials (external review F7 — raw C −2, M −2, Y +2 all inside the radius, gauged Y +4, clipped to 2.24), and the runaway it was hired to stop is the prior's job (I6). Uncertainty is published and gates nothing. |
| I9 | A certificate is never invalidated by the field; certified tiles are evidence by correlation, memoised on the pose version. |
| I10 | The solved field is a durable fact and a cache; observations are derived and regenerate from placements, certificates and rasters. |
| I11 | Evaluation is per cell, bilinear on the tile grid. |
| I12 | ONE REVISION (NEW 2026-09-08, W8 R-D). The store keeps one integer per (capture, page), advanced by every placement birth, change or removal on that page and by every certificate on it, and by nothing else; a resume restores it from the snapshot rather than recounting the surviving facts, because the count is over events and events do not survive (§2.7). The collect row's ordinal IS that revision; a page that loses its last window publishes an EMPTY collection under a new revision; the page solves whenever its evidence revision changed and publishes only if the field moved; every consumer records the field revision it was fitted with and owes a refit when the standing revision differs. The revision is BOOKKEEPING: many advances between two admissions buy ONE collection, that collection re-measures only the tiles whose inputs moved, and only a publication that moved the field wakes a reader (§2.7). |
| I13 | UNKNOWN IS NOT ZERO (NEW 2026-09-08, W8 R-C/R-E). An axis nobody measured is marked unmeasured and enters no sum; a plane with no template reads unknown, never a guess; evidence that disappears is replaced explicitly, never by the absence of rows. No downstream code infers meaning from a missing row. |

---

## 4. What this retires in holo3

The per-(capture, level, page, plane) key and the lane-page subject of
the `fields` row; the always-on `PlaneResidual` model and
`fit_registration`; the median-of-three gauge (`plane_relative`,
`settle`); the `publishable` floors and every use of `MIN_DELTA_DOTS`;
the `--plane-fields` dial; birth by `Certificate` and the 180 × ordinal
re-fit pricing; the linearised photometric tier; the plane-as-K row's
"do not search when a field stands" rule (it searches around the field);
and, in the analyzer, the rotation of production deltas into the page
frame (they are page-frame at the source once the receiver lands).

ADDED 2026-09-08 (W8), the second retirement wave, each with the ruling
that ordered it: the BLIND TIER and every constant and helper under it
(`field_tiers.blind_offset`, `blind_logloss`, `split_key`, the `BLIND_*`
constants, `fields_collect.measure_blind`, `SOURCE_BLIND`) and, with it,
the three-way parity partition, which existed only to keep that tier's
evidence independent of the anchor tier's (R-C); the per-window
common-mode subtraction `fields_collect.common_mode` and its
`gauge_covered` companion, and W7's R1 refusal with them (R-A); the
all-three-plane certified requirement (`certified_whole` and the
all-plane intersection in `window_sites`) (R-C); the RESIDUAL-ENERGY
TRIGGER in all three of its forms (`lib/plane_field.loudest_tile`,
`should_resolve`, `TRIGGER_MARGIN`, and the trigger row the readout and
report carry as a scheduling statistic), replaced by the evidence
revision (R-D); the collection ordinal as a sum of pose generations
(`fields_collect.prepare_collect`'s `pose_work`) (R-D); the per-plane,
per-axis publication bound where the solve applies it, and
`measurement_reach_dots` with it unless the tier's own acceptance keeps a
caller (R-B, and the external review's F7); and the per-tile weighted
median as the solve's pooling step (`lib/plane_field.pool`), whose
robustness the joint fit's loss now carries (R-B). `FIELD_NOISE_DOTS`
stays: it is the design's noise scale, it is what "reads the pose" is
measured against past twice `FADE_LENGTH_MM`, and it is B1's agreement
bar.

CORRECTED 2026-09-08 (W7): three names this list and the plan's W2 row
report as DELETED are still defined, and deliberately —
`plugins/fields.py:68` `MIN_DELTA_DOTS`, `lib/plane_field.py:95`
`MAX_DELTA_DOTS` and `lib/plane_field.py:641` `clamp`. No receiver
module reads any of them (grep over `src/holo/receiver`, 2026-09-08:
one hit each, the definition); they survive as the analyzer's reference
to production's retired floor and bound (`analyzer/field2.py:276, 283,
842` and `:118, 661`), which is what the plan's own W2 outcome text says
at `PAGE-FIELD-PLAN.md:189`. The RULE is retired — nothing in this
receiver refuses or clamps on them — and the CONSTANTS are not; W7's
per-plane publish bound (§2.4, I8) is a separate object and does not
reinstate `MAX_DELTA_DOTS`.

---

## 5. Out of scope, with the hook each leaves

| item | hook | why not now |
|---|---|---|
| scanner field (per scanner, resolution, channel; platen coordinates) | one sentence in §2.1: after the pose, on the pixel | no hard data; the Canon measured ≤0.09 dots, 2.8–9× under any useful floor (`measure/scanfield/README.md`); the HP flatbed a constant. Revisit only for yield. |
| cold search and word validation through the field | §2.8, the mapping is available to every hypothesis holder | its own program (confetti addressability); a receiver-workplan section, not a build in this wave |
| per-engine form library | §2.9 | a prior over this object; after two sheets of one engine agree on the constant terms (the M281's −1.7-dot Y offset already replicates across e017 and e028) |
| parametric surfaces (the analyzer's degree ≤3, v1's harmonics) | none | withdrawn 2026-09-07: the nonparametric field with a locally-linear smoother expresses every measured physics |
| snapshot compatibility, converters, validators in production | none | ruled out 2026-09-07; a throwaway extractor under `measure/` may read old snapshots for validation and is deleted after. AMENDED 2026-09-08 (W6): `measure/page_field/extract.py` is KEPT — sheet I's snapshot is pre-W2 and this is its only reader; the licence is unchanged, its expiry is |

---

## 6. Validation bars (pre-registered)

| # | bar | instrument |
|---|---|---|
| B1 | **Frame.** A synthetic page with one plane displaced by a known page-axis vector certifies the same set under rot 0, 1, 2 and 3 placements, and a confetti page whose windows mix all four rotations solves the same field as the un-rotated page to within 0.05 dots. AMENDED 2026-09-08 (W3b, measured): the agreement bar is `FIELD_NOISE_DOTS` (0.25 dots per tile, the design's own noise scale, §2.4) with the frame nulls — sign flip, axis swap, no field — at least 5× further off (RESTATED 2026-09-09, W8: the 7× was W3b's own measurement pinned as a floor with no room; the re-derived solve reads the no-field null at 6.94× at rot 2 with the sign flip at 13.9×, and the agreement bar itself is untouched); 0.05 was written before two placements had been compared and sits under their measured floor (C and M, no injected field, solve 0.06–0.07 apart; the estimator is 0.31–0.38 from the injected truth). Measured Y agreement 0.144 at rot 2, 0.093 on the confetti platen; nulls 7.9–15.8× off. Rot 1 and rot 3 are witnessed as confetti scraps, each quadrant against the un-cut page's field at its own turn (nulls 18–43× off), RULED to discharge the four-rotation wording. RESTATED 2026-09-08 (W8): PROVED BY `test_h3_e2e_field_frame.py`, kept whole — the rotations and the confetti platen are its four decode arms already. CORRECTED at the W8 spec review: that module gains nothing from the behaviour suite, and behaviour-suite line 16's OTHER clause — two captures at two decimation ladders solving one field — has no test anywhere. It is OWED, on the requalification list, and belongs to a decode arm, not to the library suite (B2). | receiver sims |
| B2 | **Invariance.** Two captures of one synthetic page, at two decimation ladders, solve one field per plane; adding the second capture changes the field by less than the noise floor and the observation count by exactly one per covered tile. ON PAPER 2026-09-08 (W5 replays, sheet I): the field from one capture and from four (three more added) agree to 0.023 / 0.024 / 0.028 dots median per tile on C / M / Y, p90 ≤ 0.07, against frame nulls of 0.31–0.76 dots. QUALIFIED 2026-09-08 (W7): measured at TERMINAL facts, so through the certified tier alone — a replay of a finished run finds every tile certified, and `fields_collect.measure_window` then routes every per-tile observation to `measure_certified` while the window's furniture set (`fields_collect.py:588`, the tiles that are NOT certified) is empty, so no anchor and no blind row is taken. Sheet I is 1,952–1,961 of 1,961 tiles certified per plane. The mixed-tier regime production runs in while the field still matters is NOT what this number measures. RESTATED 2026-09-08 (W8), CORRECTED at the spec review: the TWO-CAPTURE half is PROVED BY behaviour-suite line 15 in `test_h3_field_estimator.py` — `test_agreeing_evidence_shrinks_the_uncertainty_it_covers` (renamed from `test_more_evidence_…` 2026-09-12: the test always added an AGREEING capture, and "more evidence" is the claim R9 disproved — `test_conflicting_evidence_can_raise_the_uncertainty_it_covers` is the counterexample) and `test_a_second_capture_moves_a_supported_tile_inside_its_uncertainty`, a second capture over the same tiles, one field. The TWO-LADDER half is NOT proved by the suite and no test asserts it: the nearest standing pin is `test_h3_plane_fields.test_a_second_level_of_one_capture_adds_no_observation`, which is I4 — one capture, two levels, no added weight — and a different claim. Two captures at two ladders is OWED to a decode arm at requalification. The terminal-fact qualification is discharged only by a replay that collects on an UNFINISHED page, also on the requalification list. ON PAPER AGAIN 2026-09-09 (W8 requalification, plan §5.1): one capture against four on sheet I agree to **0.020 / 0.020 / 0.065** dots median per tile on C / M / Y (W5 0.023 / 0.024 / 0.028; the Y maximum 0.29), and every replay collects exactly once per (capture, page) — 1, 4 and 7 on sheet I one, sheet I four and sheet H, 20 for 20 capture-pages on sheet J's ten loads under the fossil identity. The two-ladder half and the unfinished-page replay stay owed. | receiver sims |
| B3 | **Ground truth.** On sheet I's archived placements and certificates, the receiver's estimator reproduces the supervised Y sinusoid of `scratch/xerox-v1-20260818/regmap-gt/` (Spearman ≥ 0.99, period within 3 %, amplitude reported against 0.935 of v1's V0) and agrees with the analyzer's pooled sheet-H fit to ≤ 0.12 dots median on x. MEASURED 2026-09-08 (W5 replays): sheet H — Y 0.101 / C 0.101 dots median on x against the analyzer's pooled fit, PASSES; sheet I — period 17.5 vs 17.1 tiles (1.023×, PASSES), Spearman 0.986 with one capture / 0.988 with four against ≥ 0.99, NOT MET by 0.002–0.004 (the supervised reference's own sinusoid fit is r² 0.824 against the field's 0.858, so the reference's noise bounds the agreement; the bar stands as written), FITTED amplitude 0.898× / 0.916× of the supervised FITTED amplitude 0.5906 dots, reported — and beside it the like-for-like profile MAX, 0.8247 / 0.8281 against the supervised 0.8331 (0.990× / 0.994×), the statistic e033's 0.83 is (§7). QUALIFIED 2026-09-08 (W7): every real-sheet number in this row came through the certified tier alone, for B2's reason — H is 5,883/5,883 and I 5,880–5,883/5,883 tile-streams, so the replays collect at terminal facts and no anchor or blind row is taken. The tier flip is measured, not assumed: on the W5 sim, where both regimes exist, holding the certificates out gives 91 anchor + 88 blind rows in place of 92 certified ones and moves the field by C 0.0389 / M 0.0264 / Y 0.0804 dots against a 0.12-dot bar that H passes at 0.101. AMENDED 2026-09-08 (W8 R-E): the bar GAINS A Y STIMULUS. No sheet in this record carries supervised y ground truth, so the y half is pre-registered on the sims — an injected y displacement is recovered within the same tolerance as the injected x one, at c2 and at c3 (behaviour-suite line 13, `test_h3_field_estimator.py`, and the y twin of `test_h3_color_field_yield.py`; RETIRED 2026-09-20: `test_h3_color_field_yield.py` left the tree with the widened matrix's whole-page proofs — record in the receiver docs' `WIDENED-MATRIX-RETIREMENT-2026-09-20.md` — so the y half is owed on the estimator's own test alone, never as a whole-page decode) — while the sheet-I and sheet-H numbers above remain the x half. The M281's dominant term is y and nothing in this line has ever exercised it. REQUALIFIED 2026-09-09 (W8, the re-derived solve; plan §5.1): sheet I with four captures MEETS the bar IN FULL for the first time — Spearman **0.9903**, period **1.020×**, fitted amplitude **0.955×** of the supervised 0.591 dots, profile max 0.980× of e033's peak; with one capture it is NOT met — Spearman 0.9874 and period 1.047× (over the 3 %), amplitude 0.893× — the sharper prior on one capture's noise. Sheet H against the analyzer's pooled fit: C 0.109 passes, **Y 0.122 is over the 0.12 bar by 0.002** (W5 0.101 for both), recorded and NOT moved — the derived length passes the noise its gain bar buys (pass-through 0.059 dots against 0.030 at the copied length), and whether `GAIN_BAR` sits at 0.95 or 0.90 is Germano's ruling with these two numbers in hand (§7.1) — RULED 2026-09-12: 0.95 stays, one-engine evidence, reopened only by a second engine's field. | `measure/page_field/` harness |
| B4 | **Gauge.** On the in-register colour sim the solved C and M fields are zero to 0.03 dots and Y's is zero; on the displaced sim the solved differential equals the injected one. RESTATED 2026-09-08 (W8 R-A): PROVED BY behaviour-suite lines 11 and 12 in `test_h3_field_gauge.py` — windows that saw C only, M only or both, at any weights, yield the SAME Y field, and a window's own pose error appears in its nuisance and in no plane's field while a plane-common shift of every window is absorbed entirely. | receiver sims |
| B5 | **Loop.** A swim win's certificate appears as a certified-tile observation in the next solve and as known cells for the pose refinement of its owning windows. RESTATED 2026-09-08 (W8): PROVED BY behaviour-suite line 7 in `test_h3_field_evidence.py` (a certified C contributes its whole template while M and Y are uncertified) together with the swim existence module, which is where the win is minted. | receiver sims |
| B6 | **Cost.** RESTATED 2026-09-08 (W7) as a cost bar with its measured counts, because the W5 wording had shrunk to a by-construction clause and to a count the harness makes rather than measures. The bar is: (a) **one collection per (capture, page)** — measured 7 collections for 7 capture-pages on sheet H, 2 for 2 on sheet J's one capture (fossil, both trees), 1 and 4 on sheet I — the 20-for-20 on sheet J's ten captures was a wrong-identity replay and is owed again; (b) **solving is negligible beside collecting** — `solve_cpu_s` against `collect_cpu_s` is 0.107 vs 1,921.6 on H (1:18,000), 0.035 vs 97.7 on sheet J's one capture (1:2,800, the fossil W7 run; the pre-W7 fossil run 0.041 vs 65.2), so the trigger may fire freely and under-triggering is the expensive direction (§2.7) — RE-MEASURED ON THE W8 SOLVE 2026-09-08 at the fix pass (review M4): **6.165 vs 89.9 CPU-s on that same sheet-J capture, 1:14.6**, and 1:12.4 / 1:15.7 on the review's and the integration's runs of it, so the clause AS WRITTEN — negligible — is no longer met and what this bar now records is *solving is 6-8 % of collecting*; the ruling stands on the direction of the risk and not on the margin, and the sheet-H and ten-load sheet-J halves are owed to the requalification on this solve — the sheet-J ratios this row used to quote (0.037 vs 1,529.9 on ten captures, 0.020 vs 47.9 on one) came from wrong-identity replays and are withdrawn with §7's incident; the ten-capture fossil run is the lead's and in flight; (c) **lane-page fits exactly 0**, which holds by construction (the field cell is keyed (page, plane)) and is counted, not asserted, by the harness — 0 on every replay, against the archived sheet-H run's 44 per-lane subjects. What is NOT a scheduling measurement: `pages_solved` on a harness replay is the tool's own order (`estimate.py` solves each page once, unconditionally), so the number of solves production would schedule is measured only on the sims, where `fields` fires TWICE per page — an early solve and a mature one (W3b; W5's sim replay `fields` 2, `fields.collect` 2). "One solve per page" as pre-registered is therefore NOT met and is not claimed. RESTATED 2026-09-08 (W8 R-D): the count clauses stand and gain their lifecycle proofs — PROVED BY behaviour-suite lines 1, 5, 6 and 6b in `test_h3_field_lifecycle.py` (a fresh placement re-collects, every relevant birth/change/removal and every certificate advances the revision and nothing else does, two identical collections publish once, and — the clause W8 adds because W8 makes the revision move on every certificate — many advances between two admissions of the collect row buy ONE collection and a publication that did not move the field wakes no reader, §2.7) with the descriptor, schedule and wake pins kept. The trigger clause is void with the trigger (§2.7): the page solves on a changed revision, so "solves per page" is now a statement about how often the evidence changed, and the replays report it. REQUALIFIED 2026-09-09 (W8, plan §5.1): (a) **20 collections for 20 capture-pages on sheet J's ten loads under the fossil identity** — the count this row owed is discharged — and 1 / 4 / 7 for 1 / 4 / 7 capture-pages on sheet I one, sheet I four and sheet H; (b) on real sheets the solve is **0.3–0.7 % of the collection** — 5.4 vs 741 CPU-s (I one, 1:137), 7.7 vs 2,864 (I four, 1:371), 12.9 vs 2,280 (J ten loads, two pages, 1:177), 12.9 vs 4,334 (H, 1:335) — so the 1:14.6 of the fix pass was the small-page end of a solve that costs seconds against collections that cost 12–72 minutes, and the direction of the risk is unchanged; (c) lane-page fits 0 on every replay. MEASURED IN PRODUCTION 2026-09-10 (plan §5.2, the sheet-J chain — the first counts this bar has that production SCHEDULED rather than the harness ordered): (a) as pre-registered — one collection per (capture, page) — is NOT met by production: **120 collections for 20 capture-pages, 6 per (capture, page) on all 20** on the ten-capture run (5 / 7, 3 / 3, 2 / 2 on the chain's other runs), each 31.6 cpu-s against the replay's 114, so the count rises and the unit cost falls; the replay count that discharged (a) above measures the harness. **105 solves over 2 pages** — with the trigger void (§2.7) that number states how often J's evidence changed. (b) holds on a confetti page: solve **243.00 cpu-s against collect 3,794.72, 1:15.6**, the pair 2.67 % of the run and solving 0.16 %. (c) 0 by construction. Two counts this bar did not anticipate: the store's ordinal guard silently REFUSED 6 of the 105 (8 of 20 on the five-capture run) because a resumed run's early solves sit below the standing field's ordinal; and of the 105, 39 changed support presence, 66 did not, 40 changed no reported scalar — the publication rule's datapoint, §7.1. **(b) IS STALE FROM 2026-09-12** (the external review's R2): every solve number in this row was measured when the estimator spent three unconditional reweighting passes, and it now iterates to the robust loss's fixed point, which multiplies the SOLVE half by the pass count — measured 16–23 passes on a 53x37 page carrying 60 windows at the module's own observation scale, and 1 where no residual leaves the knee (`lib/plane_field.IRLS_MAX_PASSES` carries the table). The direction of the risk is unchanged and the ruling stands; the ratios of (b) are owed a re-measurement on the next replays, and (a) and (c) do not move. RE-MEASURED 2026-09-12 (plan W9, the replays on f2b1dd49): solve 23.0 against collect 315 CPU-s on sheet I one capture (1:13.7) and 79.8 against 1,154 on sheet J's ten loads (1:14.5) — the solve up 4.3× and 6.2× with the pass count, the collection HALVED by R10's one-channel sampler, the fields unchanged to 0.02 dots at worst; (b) as written — negligible — is not met and *solving is 7 % of collecting* is the number this bar records now. | harness, scheduler counts |
| B7 | **Yield.** Both colour e2e sims recover byte-exact; the in-register sim's certificate set is a superset of today's; the displaced sim's certificate signature equals the in-register control's. A real-sheet re-decode is a costed run for Germano's go. MEASURED 2026-09-08 on his go (plan §2, "the sheet-I yield A/B"): sheet I from ONE 2400 capture, branch 5,860 of 5,883 certified (Y 1,949) in 2 h 39 min and 72,642 CPU-s against main's 5,820 (Y 1,903) in 3 h 43 min and 98,615 CPU-s, both verified byte-exact — +40 certificates, 26 % less CPU, the Y field published where the old receiver refused it. One sheet, no promotion. RESTATED 2026-09-08 (W8): that A/B was measured on the W7 solve and must be REPEATED on this one (charter §4); the sim clauses are proved by the two colour e2e modules on the slow lane, which are kept. REPEATED 2026-09-09 on the W8 solve (frozen export of 347285ef, same capture, same machine, run beside the sweeps rerun; plan §2, the yield section): **5,861** of 5,883 (C 1954 / M 1960 / Y 1947), 22 in attempt, verified byte-exact at the same sha, 2 h 51 wall, 71,794 CPU-s, peak RSS 18.0 GB, the field's own cost 6 collections 1,333 s + 6 solves 29 s (C 0.30 / M 0.30 / Y 0.36 dots, support 100 %; that 29 s is a three-pass number and rises with the pass count from 2026-09-12 — B6) — one certificate more than the W7b branch at 1 % less CPU, the collection 2.28× dearer (the certified radius, §7.1), wall 8 % longer on a shared machine. The whole-page re-decode clause is DISCHARGED. ON PAPER ON A FRAGMENT VOLUME 2026-09-10 (plan §5.2, Germano's machine 4 chain): e035's ten Canon captures of the duplex confetti sheet `L:c2-cmy8-r0547@53x37` through four runs with the field unconditional — **close VERIFIED byte-exact, sha `fbbab289…`, 1,048,576 B, rank 4,020 of 8,102 certificates** (C 2,738 / M 2,749 / Y 2,615), all six page-planes published and `known` at 82 % / 81 % support where e035's per-lane fitter published C alone and refused M and Y. That discharges the real-sheet re-decode clause on a fragment volume; it is NOT the yield comparison: against e035's from-scratch 7,887 the total is +215 of which 156 are the analyzer's, the receiver axis at most +59 (+0.75 %), uncontrolled five ways (chain against one run, the fold on one side, 14 workers against 12, machine 4 against machine 2 with CPU never compared, the tree). The yield half stays sheet I's A/B above. | receiver slow lane; one real-sheet A/B |
| B8 | **The prior (NEW 2026-09-08, W8 R-B).** (a) An injected x sinusoid and an injected y sinusoid come back within a stated error at c2 AND at c3 — the smoothing length is physical, so the two pitches may not differ by the 0.957-against-0.835 amplitude gap the tile-pinned bandwidth had (§2.4), which is the number the test uses as its bar: the gains must agree to better than 0.122. **AMENDED 2026-09-08 (the lead's ruling, W8 landing): (a) gains an ABSOLUTE clause, because agreement alone is blind to a common loss and a length copied from the retired kernel was passing 0.776 at c2 and 0.791 at c3 while satisfying the gap clause handsomely.** The clause: at c2 AND at c3 the solve keeps at least `GAIN_BAR` = 0.95 of a 100 mm sinusoid — the length is DERIVED from that bar (§2.4) rather than inherited, and the bar is asserted sim-free on the estimator module's own full-support stimulus (`test_the_hundred_millimetre_wave_comes_back_at_the_bar`, both pitches). Measured at the shipped length: **0.957 / 0.965**, and the mutation that fails it is the length the tree carried an hour earlier. (b) INSIDE measured territory a hole of a few tiles is BRIDGED — every tile of it within `FIELD_NOISE_DOTS` of the injected truth — because the curvature term's job there is interpolation, not fading (§2.4). (c) On sparse support, the field on unsupported tiles is never worse than the pose — RMS error against the truth ≤ the pose's on the identical tiles, AND worst tile against worst tile, which is where the shipped smoother fails hardest (0.621 against 0.584 dots RMS and a 1.774-dot maximum against the truth's own 0.83, external review §3) — and it reads the pose past twice `FADE_LENGTH_MM`. **QUALIFIED 2026-09-08 (W8 landing, measured): the RMS-against-the-pose comparison is not a property of the estimator.** It is decided by the PHASE at which the evidence band ends: over band edges 8, 9, 10, 11, 12, 13 of the suite's own stimulus it holds at the first three and fails at the last three ON THE 10.8 mm TREE, and at the first two on the shipped one; past twice the fade length the same coin lands the other way (edges 8 and 9 fail, at both lengths). What decides it is the sign of a 0.02–0.09-dot fading residue against a truth that swings ±0.83 out there, and the clause passed until now because edge 10 ends the band within 0.064 dots of a zero crossing. The worst-tile half was already shown unachievable by any fading field at the W8 build (§4.1 of the solver report). Both halves are replaced in the suite by the design's own sentence — past one fade length the field keeps at most HALF of the largest measurement — which the retired smoother fails by 5.6× and the shipped solve passes by 5.7×, and by the twice-the-length clause, which it passes by 5×. The bar's WORDING here is the lead's to restate; what W8 records is that this spelling of it cannot be tested. A tie in (c) is compliant: fading exactly to the pose is the wanted behaviour and the bar is written ≤, as the charter writes it. (d) Uncertainty grows with distance from evidence and shrinks with AGREEING evidence, it orders the three regimes (measured < bridged < faded), it never exceeds the prior's own — that is what a prior is — and adding a capture never moves a supported tile by more than its uncertainty. PROVED BY behaviour-suite lines 13, 14 and 15 in `test_h3_field_estimator.py`. **QUALIFIED 2026-09-12 (the review's R9, measured): "shrinks with evidence" is false as an unconditional claim and this clause now says AGREEING.** The shrinkage is a property of a posterior at FIXED weights; the weights here are the robust loss's, so a window that contradicts what stands re-weights the standing rows and can raise the old tile's uncertainty — 0.431956 → 0.458141 dots on a c3 1×2 page (+6.06 %, the fit's fixed point at 212 passes, inside the 250-pass ceiling; §2.4). The prior CEILING is unaffected and stays asserted. Pinned by `test_conflicting_evidence_can_raise_the_uncertainty_it_covers`, and no clamp, gate or recalibration was added to make the old wording true. QUALIFIED 2026-09-08 (W8 fix pass, review M2): the published quantity is NOT the posterior deviation but 19.4x it (§2.4), so the last clause is a bar against a multi-sigma number — the second capture's worst move on a supported tile is 0.126 dots against the smallest published uncertainty 0.808, six times over. Re-arguing it against the posterior deviation means re-writing the clause and not only the quantity: a per-tile *move within one sigma* bar refuses 56.5 % of the supported tiles of an HONEST posterior, measured on this stimulus, because that is what a one-sigma bar does. What the clause is really asking — that a second agreeing capture does not move a tile by more than the page admits it does not know — survives either spelling; the multiple does not. **RE-MEASURED 2026-09-08 at the gain fix**, since every number in this clause moved with the derived length: published median 1.738 supported / 6.784 faded against a posterior deviation of 0.096 / 0.419, ratio **18.1×**; `sigma_dots` 7.257; the second capture's worst move 0.069 against the smallest published uncertainty 1.318, **19× over**; and the fit's own error on those supported tiles fell to 0.026 median / 0.138 worst, from 0.141 / 0.375, which is what the amplitude the bar bought looks like per tile. | receiver sims |
| B9 | **Nulls (NEW 2026-09-08, W8 R-C).** A dead or noise plane driven through the WHOLE collector publishes no evidence for that plane and the solve reports it unknown — the complete chain, not one tier, because the defect this retires was a calibrated tier handing its rejects to an uncalibrated one (11 of 20 collections published a false Y field up to 1.875 dots, §2.5). PROVED BY behaviour-suite line 9 in `test_h3_field_evidence.py`, seeded with the external review's `yellow_noise.py`. | receiver sims |

---

## 7. Open items, and the measured record

### 7.1 Still open

- **THE W8 SOLVE IS REQUALIFIED ON THE REPLAYS AND ON THE DECODE
  (2026-09-09).** The charter's requalification (§4 there) ran on
  the engine-fixed tree 347285ef: H seven captures, I one and four, J ten
  loads on the fossil, the same tables as W5 — plan §5.1, and B2, B3, B6
  and B8 above carry the numbers (fields within 0.03–0.08 dots per tile
  of W5's on every sheet, every capture's residual under its noise
  expectation, B3 on sheet I met in full with four captures, sheet H's Y
  0.122 against the 0.12 bar recorded). The sheet-I single-capture decode A/B on this solve closed the same
  day: **5,861** against the W7b branch's 5,860 and main's 5,820, all
  three verified at one sha, CPU a wash against the branch, the
  collection 2.28× dearer (B7; plan §2, the yield section). What remains
  of the requalification is the radius item below, which now has its
  price on a whole page and, through the sheet-J chain of 2026-09-09/10
  (plan §2), on confetti.
- **THE SMOOTHING LENGTH IS RULED AND THE OTHER TWO ARE NOT** (W8
  adversarial review M1/M2/M3; the lead's ruling 2026-09-08, W8
  landing). RULED: the length is DERIVED from a bar — keep 0.95 of a
  100 mm wave at every pitch — and is 5.557 mm, measured 0.957 at c2 and
  0.965 at c3 where 10.8 mm passed 0.776 and 0.791 (§2.4, and B8(a) has
  the clause). M1 mostly went with it: a 2 × 2 measured island keeps
  80 % of its own displacement where it kept 31 %. STILL OPEN, and both
  are the lead's: the SPELLING of the published uncertainty (§2.4: a
  prior fraction on the prior's scale, 19.4× the posterior deviation, and
  `sigma_dots` is now 7.26 dots because the fade weight tracks the
  gradient's), which decides what B8(d) and every diag row mean; and
  `GRADIENT_SHARE`, which stays 0.2 unruled — its window is no longer
  narrow at the shorter length (§2.4: the gauge island holds at every
  share from 0.2 to 1.0), so re-deriving it is now a free choice rather
  than a squeeze. Whatever is ruled next, the requalification measures
  the prior it is run on. And the BAR'S OWN LEVEL is now a ruling with
  two numbers beside it (plan §5.1): at 0.95 the derived length gives
  sheet I its first full B3 pass (four captures, amplitude 0.955×) and
  puts sheet H's Y at 0.122 against the analyzer's pooled fit, 0.002 over
  B3's 0.12; at 0.90 the length would be longer, the analyzer agreement
  closer and the amplitude lower — the analyzer's pooled fit is itself
  the smoother estimate, so |Δx| against it rises with fidelity at the
  page scale. Germano's, with those two numbers in hand. RULED
  2026-09-12: **0.95 STAYS**, recorded as one-engine evidence — the 100 mm
  period and the 0.83-dot peak are the AltaLink's — and it reopens with a
  second engine's measured field, the M281's y term first. Sheet H's
  0.122 is agreement with the smoother analyzer fit, not truth, and does
  not move it.
- **The blind tier's retirement is not measured on a dead plane.** §2.5
  retires it on false-positive evidence, which is strong; what nobody has
  measured is what the two template tiers reach on a page whose Y carries
  neither certificates nor readable dust — the M281's starved Y (e030: C
  620 / M 43 / Y 0). No product in this record splits a page's support by
  SOURCE, so the blind tier's own share of sheet J's 81–82 % is unknown.
  The per-source census rides the W8 replays; if the blind tier turns out
  to carry a material share of a real page, R-C is worth re-opening with
  that number in hand. MEASURED 2026-09-09 (plan §5.1, the W8 sheet-J
  fossil replay against W5's): when the blind tier went, Y's support fell
  1,591 → 1,430 on page 0 and 1,590 → 1,402 on page 1 while the same
  change gave C and M +66 / +62 and +75 / +81 through the per-plane
  certified template — so the blind tier carried **about 8–10 % of the
  page on Y**, on a sheet whose Y prints healthily and certifies 1,430
  tiles; the remaining Y evidence is 3,361 certified + 272 anchor
  observations (page 0). That is the material share R-C was to be
  re-opened on, and it is the lead's call: the tiles it reached are
  exactly the ones with no certificate and no readable furniture, where
  the design says unknown (I13). On the M281's starved Y, where NO
  plane-Y certificate exists to seed either tier, the number is still
  unmeasured.
- **The certified tier's search radius — 0.75, 1.0 or 1.25 cells — is the
  lead's, unchanged by W8** (§2.5 carries the swept table and the +49.8 %
  CPU beside it). The external review adds one argument the sweep did not
  consider: a whole known tile is a pseudorandom bit pattern, not a
  lattice, so the one-cell aliasing premise the radius was first cut from
  does not hold, and the ceiling is an ambiguity question to measure.
  PRICED ON A REAL CONFETTI DECODE 2026-09-10 (plan §5.2): on the
  ten-capture sheet-J run the field pair costs 4,037.7 of 151,427.9 machine 4
  cpu-s — collecting 3,794.72 (2.5 %), solving 243.00 (0.16 %) — over
  120 collections and 105 solves. The radius the §5.1 multiple describes
  costs about two and a half per cent of a real decode's CPU on the page
  shape it was re-derived on, against a run whose `tiles.local` and
  `tiles.swim` take 62 % of it; the narrower radius would have sat near
  1.1–1.5 %. The trade is unchanged; what it now has is a production
  denominator rather than a replay's, and R10's single-channel sampler
  (the handoff) shrinks the absolute number without settling it.
- **THE PUBLICATION RULE — RULED 2026-09-12, on the sheet-J numbers.**
  The 2026-09-09 external re-review's R1 (`docs/reviews/page-field-
  receiver-2026-09-09`; distinct from the W7 gauge rule this document
  once called R1) found two defects in `plugins/fields.moved`: it
  decided per plane, so a support change on one plane published that
  plane alone and the durable C and M could break the gauge by up to the
  threshold (measured 0.1999 dots with ordinals [2, 1, 1]); and it
  refused any joint correction under `FIELD_NOISE_DOTS`, a history
  dependence bounded by that same 0.25 dots. The review asked for one
  coherent decision and exact array equality. RULED: the decision
  becomes JOINT — all three planes publish together when no field
  stands, when any plane's support PRESENCE changes, or when the
  largest per-tile change over all three planes exceeds
  `FIELD_NOISE_DOTS`; metadata-only changes never publish — and the
  threshold STAYS, because it is the measurement's own resolution (the
  anchor tier's step, §2.4) and not a floor on the field's magnitude
  (I8 is amended to say so). The price of keeping it is a bounded
  staleness of at most a quarter dot between the published field and the
  latest solve. The price of dropping it is measured on plan §5.2's
  ten-capture run: one added observation moves 92–96 % of the field's
  cells, so a publish-on-any-change rule publishes on every solve —
  there 105 solves followed 120 collections, and every publication
  re-arms the six rows that read the field, which spent **126,029 of
  151,428 cpu-s, 83.2 % of that run**; under the shipped rule the
  publications lay in [33, 64] of 105, and 35 solves are proven by the
  durable ordinals to have published nothing. On sheet I the same rule
  would have turned three publications into six, in the finished tail,
  under 2 % of the run. The J number is what decides it. What remains
  owed: the first sheet-J decode after the repair should count
  `FieldSolved` against `tiles.local` and `refine.color` job counts,
  since those two rows are flat-priced and never drift behind.
- **The anchor floors' yield is ruled in direction and not in magnitude**
  (§2.5): −8.4 % of the observations on sheet J's load 1a, all of it Y's,
  and no certificate counted either way on either tree. Also the lead's.
- **Terminal-fact bias.** Every real-sheet B2 and B3 number was collected
  on a FINISHED page, so through the certified tier alone; the mixed-tier
  regime the receiver actually runs in while the field still matters is
  unmeasured. The fix is a replay that collects at an intermediate
  snapshot, which is on the requalification list and is not a sim.
  NARROWED 2026-09-10 (plan §5.2): the sheet-J chain DID collect and
  solve on unfinished pages — 47 solves at 3,402 certificates of 11,766
  (support 39 % / 38 %), 21 at 3,558, 20 at 4,273 — so the mixed-tier
  regime has run in production on a real sheet, and those fields' medians
  sit within 0.02 dots of the finished run's on every plane but one
  (run 4's page-1 Y, 0.055 off). It does not discharge the item: there
  is no per-source census on those solves and no finished-page
  comparison on the same evidence, which is what a replay at an
  intermediate snapshot would give — and this chain's own snapshots are
  now that replay's input, no new scan needed.
- **TWO CAPTURES AT TWO DECIMATION LADDERS SOLVE ONE FIELD — the half of
  bar B2 that no test asserts** (found at the W8 spec review, 2026-09-08).
  The two-CAPTURE half is in the behaviour suite; the two-LADDER half is
  not, in the suite or in the frame module, and B1 and B2 both claimed it
  before this review. The nearest standing pin,
  `test_a_second_level_of_one_capture_adds_no_observation`, is a different
  statement (I4: one capture, two levels, no added weight). It belongs to
  a decode arm and is owed at requalification.
  THE PRODUCTION CASE HAS NOW RUN, AND IT IS NOT THE TEST (plan §5.2):
  the ten-capture sheet-J run pooled eight 2400 captures and two 4800
  rescans into one field per (page, plane) — 20 capture-pages collected,
  no supported tile measured on more than 7 captures, every per-capture
  residual under its noise expectation with the 4800 footings the
  loudest on page 0 — and closed byte-exact. That is evidence the
  mixed-ladder case runs and closes; it asserts nothing, because no arm
  in it compares a one-ladder field with a two-ladder one. The owed
  decode arm's cheapest discharge is now over this chain's archived
  facts.
- **`FADE_LENGTH_MM` is 50 mm on an argument, not on a measurement**
  (§2.4). Half the cited 100 mm period is the charter's own form and the
  retired kernel's measured 37.9 mm reach sits inside it, but no replay
  has yet been solved at two fade lengths and compared. The W8
  requalification is where that becomes a number.
- **THE FADE PROMISE IS NOT MET ON THE PRINTED PAGE BY THE SHIPPED
  FREE-END OPERATOR, AND THE FIX IS MEASURED AND UNADOPTED (the
  2026-09-09 external re-review's R3; measured 2026-09-12 in-process,
  nothing in the tree changed).** §2.4's sentence — a tile one
  `FADE_LENGTH_MM` from every measurement keeps at most half of the
  nearest one, twice that far a quarter and reads the pose — holds on
  the suite's zero-crossing sinusoid and fails on a CONSTANT plateau,
  because the grid Laplacian's free ends reflect: with the free end moved
  far away the operator meets the promise within 7 % (half at 1.10 fade
  lengths, a quarter at 2.09), so the miss is the boundary, not the pull.
  On the page this format prints (53 × 37 tiles; also 52 × 36 and
  35 × 24), a 0.83-dot plateau over 20 columns, worst row (the middle
  one), c2 unless said: | free end | 0.5134 at one fade against the bound
  0.4150, FAIL; 0.3628 at two against 0.2075 and the 0.25-dot pose bar,
  FAIL; c3 0.4357 / 0.2740, both FAIL | absorbing edge, `lg · ln2 /
  fade_tiles` on the gradient term's diagonal at every free end of both
  axes | 0.4031 / 0.2021, ok by 2.9 %; c3 0.4022 / 0.1963 | the exact
  absorbing block | 0.4137, ok by 0.3 % — no margin on the page that
  prints | evidence-gated edge (absorb only where the boundary tile is
  unmeasured) | 0.4032 / 0.2022, identical, and bit-identical to the free
  end on full support |. What the absorbing edge costs: nothing in size
  (it is a diagonal), the gain bar 0.9622 → 0.9615 at 53 × 37 (bar 0.95),
  the 2 × 2 island 0.8019 → 0.7900 kept, c3 bridging 0.3352 → 0.3553 on a
  bar already failed by 34 %, and the y structure it invents on a
  y-constant plateau is 0.02 dots inside measured columns. The 3-row
  cases the review used over-absorb (0.0926) and are not production
  geometry. RULED 2026-09-12: the free end STAYS for now and the
  gated variant is REFUSED (it makes the published uncertainty
  support-dependent, +18 % on a band-supported page, and costs the
  prior variance its separable route). What decides adoption is yield,
  and it is two-sided: the edge removes 0.2–0.37 dots of unsupported
  far-field excursion and also removes real field where a plane's
  evidence is sparse at one end of the page — sheet I's Y dead-band
  geometry exactly — so the ruling's diagonal is adopted only with a
  sheet-I single-capture decode A/B in hand. Until then the promise
  stands as written and UNMET on the printed page, pinned as a strict
  expected failure (`test_a_plateau_at_the_printed_geometry_fades_to_half_by_one_length`),
  and `PAGE_EDGE_LOSS` stays at 0.015 (every variant reads 0.937–0.948
  at the 6.37 mm root; the exact operator recovers a fifth of that
  deficit, so §2.4's stated cause is partly the reflection and partly
  the near field).
- **A durable record of a refused measurement** (§2.3's third half): a
  tile that was measured and refused is indistinguishable from one never
  measured, so the next collection pays for it again. A fact-schema
  change, owed, not ruled — and now the only part of the
  unknown-is-not-zero problem W8 does not answer.
- **Finest-level ownership against an adequate template.** "One
  observation per (capture, tile, plane), at the finest level covering the
  tile" can leave a tile measured by a window with too little usable
  template while a coarser window would have measured it well. Choosing
  the informative one still respects the same-photons rule. Not built
  (external review §3).
- **A null measured on a real scanned plane channel** is still owed. The
  acceptance floor is cut from a synthetic p99 and is insensitive to the
  null model (§2.5); a peak read as a multiple of "its null" is not, and
  that is what decides how much a MARGINAL peak carries. This population
  has none.
- **The window nuisances are new estimation state and want watching.**
  They are published nowhere and applied by nobody (§2.3), which is the
  guard against per-window fields returning by the back door. What is
  worth reading on the replays is whether they show a systematic pattern:
  if they do, the pose row is missing something and that is the pose row's
  business, on its own held-out gate.
- **A PLANE-COMMON AFFINE POSE ERROR BECOMES A FALSE Y FIELD — R8 of
  the 2026-09-09 external re-review, lifted into this list 2026-09-13;
  neither repaired nor qualified.** The window nuisance is
  translation-only (§2.3), so a plane-common error that VARIES across a
  window has nowhere to go: the reviewer's stimulus, a 3×3-tile c3
  window given the same raw x errors −0.4, 0, +0.4 across its columns in
  every plane (a common linear pose error of about 0.2083 %, every true
  differential field zero), solves to C = M = 0 and Y = −0.315099, 0,
  +0.315099 with a zero translation nuisance — the gauge forbids C and M
  the shared slope and Y fits it alone
  (`docs/reviews/page-field-receiver-2026-09-09/estimator_repros.py`,
  key `common_affine_pose_error_becomes_Y_field`; the R2 convergence
  repair does not touch it). The W9 wave took R1–R7 and R9–R11 and left
  this one unlisted. What the reviewer asks, kept here as the open item:
  qualify the translation-only nuisance against common scale, shear and
  rotation stimuli and separate pose-estimation error from print-fixed
  deformation; if the residual is material, ask first whether the pose
  row should own it before the estimator grows, and price any
  plane-common affine nuisance under identifiability tests, or
  co-located inter-plane differences where corresponding measurements
  exist; never publish a window nuisance, never add nuisance freedom to
  pass one probe.
- **Plane-as-K's spectral approximation** (external review §4). The read
  samples at the TARGET plane's field while using sibling labels tied to
  the original page cell; at substantial differential displacement and
  crosstalk the sibling ink under that point may belong to another cell.
  Existing independent-channel tests do not establish the approximation's
  accuracy. A modelling qualification to test, not a measured regression.
- **R6's decode proof** — that plane-as-K's pose candidate buys
  certificates, not just reachability — is still owed and is a decode.
- **The photometric-gain anomaly** (1.000 injected vs 0.46–0.53 real). The
  tier is retired; the number stays unexplained and is recorded here so
  nobody re-derives the tier without explaining it.
- **M on paper — STILL OPEN; the W5 claim is narrowed (W7,
  2026-09-08).** No pooled M field had been fitted on any sheet
  (`analyzer/FIELD2-2026-09-03.md:549`); B3 fits all three planes.
  2026-09-08, sheet H: 18,117 M observations over seven captures, median
  0.3286 dots, at terminal facts through the certified tier
  (`scratch/page-field-20260908/H/fields.json`). Two claims made beside
  that number are withdrawn. "Sinusoidal at ~16 tiles" is in no product —
  `H/compare.json` carries Y and C rows only — and the fit measured here
  reads period **17.10 tiles, amplitude 0.1888, r² 0.656**
  (`estimate.column_profile` into `compare.fit_sinusoid` on
  `H/fields.json`, the path `compare.py` itself takes), which does not
  clear a smooth-random-walk null: 300 three-tap-smoothed Gaussian walks
  of 37 columns through `compare.fit_sinusoid` give r² median 0.655, p95
  **0.865** (seed 20260908), where H reads C 0.690 and M 0.656 and only
  Y (0.917) clears. "Roughly anti-phase to C" is BY CONSTRUCTION, not a
  finding: §2.3's gauge sets `F_C + F_M = 0`, so the two planes carry
  ±½(C−M) and are exactly opposite wherever their tile
  weights are equal — measured on H, M = −0.970·C − 0.0008 on x, corr
  −0.873, residual rms 0.081 dots (sheet I −0.969 and −0.944). What
  sheet H publishes is therefore the C−M differential split by the gauge,
  not an independent M measurement, and it does not close this item. At
  W8 the gauge is a constraint on the fields (§2.3), so M = −C to the bit
  on every sheet (plan §5.1) — the −0.970 was the old per-window
  common-mode drop leaking a little C−M asymmetry, and it is gone; this
  item closes only against an M reference the receiver did not make.
### 7.2 Closed, corrected or withdrawn — kept as the measured record

- **A4b's existence proof — CLOSED 2026-09-12 on the evidence margin (Germano, on the lead's recommendation); the debt below was the W6 landing's, 2026-09-08.** The fixture was REBUILT to carry the physical effect the arm claims to use: the starved plane displaced by 2 px — one printed dot, a third of a c3 cell — with the injected page field handed to the tier the way production hands it (`measure/uplift_fixture.py`, commit 4d714282). Ablation, the arm off against on with everything else identical: the corrected arm reads **50,283 of 65,536 starved cells right against 50,140, margin +143**, positive across the band (+680 at plane scale 0.17, +387 at 0.19, +37 at 0.21), the conditioning stratum that failed its gate by 0.0006 now adopted at −0.0208; and it converts NO tile on this fixture, as the record has said since 2026-08-31 — the full 13-point cliff scan on the rebuilt fixture (2026-09-12, `measure/uplift_cliff.py`) reads certificates EQUAL at twelve points and, at plane scale 0.180, **0 for the arm against 2 for the base arm**: the conditioning cost two tiles there. So the evidence margin is real and the certificate yield is nil to negative on this fixture; the arm stays on the ruling's letter (margin > 0), and that one point is the number to reopen it on. The arm's existence is re-proved at the decoder's input on a real registration error, so the arm STAYS and the retirement branch does not fire; the strict expected failure became the pin. Not measured: a certificate from the arm, which would need the displacement-to-starvation ratio scanned (a costed probe), and the arm on the M281's starved-Y pages. The tier now takes its field as a required input — a defaulted None read both arms at the pose and printed margin +0. The supplemental A4b arm (RECEIVE-DESIGN §6.2a:
  conditioning the starved plane's detector on its certified siblings)
  proved its existence on a synthetic fixture (`measure/uplift_fixture`,
  `test_h3_uplift_existence`) by +22 correct cells of 49,152. On this
  tree both arms read 52,736 of 65,536 cells right — margin exactly
  zero. Measured, not inferred: the arm's whole code path is
  byte-identical to W2's; what changed is the fixture's state, because
  the always-on {1, y} registration residual §2.2 retired was the
  corrected arm the fixture had always been fitted beside. Without it
  the detector fit differs, the frontier moves 36 → 32 certificates,
  and the one conditioning stratum that reaches the starved plane's
  emitted cells — (plane 2, pattern 3), fitted on 96 furniture cells and
  no certificate cell on either tree — fails its held-out gate by 0.0006
  where it passed by 0.023. W2's own code with the corrected arm forced
  off reproduces every number bit-exactly. The claim stands in the tree
  as a strict expected failure. What would pose the question again: a
  fixture with a REAL sub-cell per-plane registration error and the page
  field handed to `build_region_inputs` the way production hands it, so
  the corrected arm exists for the reason this design says it should;
  or a retune of the starved plane's scale against the base-arm page. A
  yield-bearing arm may not be retired by a test — Germano rules.

- **v0.4, 2026-09-08 — the amendment v0.5 supersedes, and IT WAS A
  WITHDRAWAL.** Its rulings were Germano's in the 2026-09-07 dialogue,
  quoted where they bind, and in the 2026-09-08 W7 dialogue (R1–R7,
  recorded where each lands: §2.3 and §2.5 the gauge as part of the
  measurement, §2.4 and I6/I8 the per-plane publish bound, §2.7 the one
  trigger statistic, §7 and §6 the record withdrawals); the 2026-09-08
  audit of the receiver line (`scratch/page-field/AUDIT-2026-09-08.md`)
  was that wave's spec, and `PAGE-FIELD-PLAN.md` §2's W7 and W7b blocks
  carry what it found and what is owed. Every sheet-J number this
  document carried before v0.4 was measured on the WRONG IDENTITY and is
  void — the incident is the next item, with the mechanism and the list
  of void conclusions. What the rulings rest on was re-stated against the
  first measurement taken on the printed identity: the gauge rule R1 kept
  its ruling on its own argument and its measured price on that capture
  was ZERO — it did not fire once — the publish bound R3 kept its ruling
  with its motivating number re-measured rather than withdrawn, and the
  certified tier's radius and floor (R2) lost their evidence, got it back
  re-derived on the fossil, and went to the lead with the Y yield that had
  been misattributed to R1 restored to them. W8 has since retired R1
  (§2.3) and the publish bound (§2.4, I8); R2's radius question is still
  the lead's, in §2.5.
- **v0.3, 2026-09-08 — the W7 REVIEW's pass over that wave**
  (`scratch/page-field/W7-review.md`). Its B1 magnitude is void with the
  sheet-J numbers.
- **THE SHEET-J IDENTITY INCIDENT, 2026-09-08 — every sheet-J number
  taken that day is VOID.** Sheet J was printed and decoded (e035,
  2026-09-01…03) with the identity now spelled `L:c2-cmy8-r0547@53x37`,
  whose AES seed is `holo/v2/c2-cmy8-r0547@53x37`. The canonical-identity
  re-key of 2026-09-02 (`FORMAT-SPACE` §16) gave the DISPLAY string
  `c2-cmy8-r0547@53x37` a different row, `1i300-cmy8-r0547-p120-v1@53x37`,
  seed `holo/v2/1i300-cmy8-r0547-p120-v1@53x37`. The harness recipe for
  this sheet was copied from e035's own argv, written before the re-key,
  when that string still resolved to the printed seed; the sheet-H recipe
  beside it names a fossil and was never exposed. Every sheet-J replay of
  2026-09-08 — W5's single- and ten-capture runs, the audit's load-1a
  probe, W7's before/after and its radius sweep — therefore declared the
  wrong seed. Measured 2026-09-08 on this tree: the two seeds' payload
  keystreams differ in 33 of 64 bits at the first tile, their slot
  permutation parameters differ, and their colour cell permutations
  differ; `sites_seed` is byte-identical (`holo/v1/sites/p120`) in both,
  so the furniture — word and dust site positions — was right the whole
  time. That is exactly the observed pattern: the ANCHOR and BLIND tiers
  read a correct page while the CERTIFIED tier correlated every tile
  against a bit image the sheet does not carry, and the certified tier is
  the one that carries a confetti page's evidence.
  VOID, in this document and in `PAGE-FIELD-PLAN.md`: the certified
  tier's radius sweep and everything cut from it; the "the certified tier
  measured nothing at any radius" reading and its null-model framing; the
  122 → 31 observation collapse and the W7 review's B1 magnitude built on
  it; the 4–13.5× per-capture Y residuals and the Y > C = M observation
  asymmetry; the 2–3-dot Y clusters and the "not a smooth field"
  conclusion (already withdrawn at W7 for a different and also void
  reason); the 8.639-dot extrapolation; the 951× weight span; the
  certified-tier wall counts of F1 and F3. What SURVIVES survives because
  it was never a sheet-J measurement: every synthetic null and hazard
  table, the format-derived site counts, the frame algebra, the trigger's
  arithmetic, and the sheets H and I results, which named fossils.
  The harness now refuses the mistake rather than documenting it
  (`measure/page_field/estimate.check_identity`, W7b): the archive
  attests the ROW ID its own `RunOpen` recorded, the declared `--format`
  is resolved to a seed, and a replay whose two seeds differ does not run
  — before any raster is opened. The first
  measurement taken on the printed identity is the next item.
- **Sheet J on the printed identity — the FIRST VALID measurement,
  2026-09-08.** `L:c2-cmy8-r0547@53x37`, load 1a, one Canon 2400 capture
  of both faces (`xerox-canon-1.9-J-c2-cmy8-r0547-confetti-2400-1a.tiff`,
  `--max-pages 2`), the same extract `scratch/page-field/J-run.54028`,
  run twice: the pre-W7 tree at `d6488900` and the W7 tree.

  | | page 0 C / M / Y | page 1 C / M / Y |
  |---|---|---|
  | support, tiles of 1,961 — pre-W7 | 220 / 227 / 216 | 186 / 179 / 181 |
  | support, tiles of 1,961 — W7 | 222 / 227 / 176 | 187 / 179 / 149 |
  | observations — pre-W7 | 252 / 259 / 246 | 211 / 198 / 200 |
  | observations — W7 | 254 / 258 / 179 | 211 / 198 / 151 |
  | median \|delta\| dots — pre-W7 | 0.322 / 0.328 / 0.522 | 0.392 / 0.414 / 0.422 |
  | median \|delta\| dots — W7 | 0.322 / 0.345 / 0.483 | 0.393 / 0.411 / 0.426 |
  | largest SUPPORTED tile, dots — pre-W7 | 0.835 / 0.800 / 1.576 | 0.745 / 0.832 / 1.484 |
  | largest SUPPORTED tile, dots — W7 | 0.835 / 0.810 / 1.199 | 0.998 / 0.794 / 1.590 |

  Support is 7.6–11.6 % of a face on every plane, and on the pre-W7 tree
  the three planes land within 5.1 % of each other on page 0 and 3.9 % on
  page 1 — the Y > C = M asymmetry the void run showed is not there. No supported tile on any plane of either face exceeds 1.6
  dots and C and M carry none above 1.0, so the 2–3-dot supported Y
  clusters are not there either. Isolated supported tiles (no supported
  tile in the 8-neighbourhood) number 3 / 3 / 3 and 0 / 0 / 0 pre-W7, and
  3 / 3 / 2 and 0 / 0 / 4 on the W7 tree. Per-capture residual energy over
  its noise expectation reads 0.29 / 0.36 / 0.59 and 0.20 / 0.13 / 0.52
  pre-W7, 0.35 / 0.36 / 0.33 and 0.20 / 0.13 / 0.21 on W7 — every one
  under 1, where the void run read 4–13.5× on Y. That statistic is weak
  here and must be read as weak: with ONE capture the pooled field is
  fitted on that capture's own observations, so it measures internal
  consistency and not the cross-capture disagreement the ten-capture run
  measures. Products: `scratchpad/j-fossil/{d6488900,w7}/fields.json`
  (the lead's session), 83.4 s and 115.4 s wall, 65.2 s and 97.7 s
  collect CPU, one capture, two pages, two collections, two solves, zero
  lane-page fits on both.

  **What moved the Y numbers between those two trees, measured** (W7b
  review-fix, `scratchpad/w7b-fix/gauge_price.py` and
  `scratchpad/w7b/probe_radius.py`, both on the same extract and scan):
  the gauge rule R1 moved nothing — 155 window events, 68 on page 0 and
  87 on page 1, all gauge-covered, no row refused, and an R1-off control
  solved from the same collection is identical on all six page-planes.
  The two anchor-tier floors moved all of it: 120 of 129 scored anchor-Y
  calls refused (58 at the per-class floor, 62 at the size-aware one)
  against one of 129 on C and one on M, with the certified tier keeping
  600 of 600 either way. §2.3 and §2.5 carry the attribution.
- **Sheet J on the printed identity, TEN LOADS — the page field works on
  confetti (2026-09-08, the lead's run on the pre-W7 export `d6488900`,
  `scratch/page-field-20260908/J-ten-e035-fossil/`).** All ten platen
  loads of e035's from-scratch snapshot (7,887 certificates), both faces:
  support **1,607 / 1,615 / 1,591** of 1,961 tiles on page 0 and **1,594 /
  1,592 / 1,590** on page 1 (C / M / Y), from 4,014 / 4,036 / 4,001 and
  3,818 / 3,855 / 3,821 observations; medians 0.328 / 0.338 / 0.549 and
  0.377 / 0.406 / 0.449 dots; largest supported tile 0.58 / 0.57 / 1.16
  and 0.77 / 0.77 / 1.26; **zero isolated supported tiles** on any plane.
  Per-capture residual energy over its noise expectation, every one of
  the ten captures on both faces: C 0.33–0.49, M 0.34–0.51, **Y
  0.54–1.08** — the same band sheets H and I read. Y IS a smooth field at
  the tile scale on this sheet: the face-0 cross-section is a coherent
  curve with a 0.70-dot peak (C 0.29, M 0.30, near mirror images — the
  C−M differential the gauge splits), pooled from scraps placed at all
  four rotations across ten loads, which is B1's confetti statement on
  paper. Invariance on scraps: load 1a alone against the ten loads agrees
  per tile to 0.055 / 0.077 / 0.162 dots median on page 0 and 0.080 /
  0.085 / 0.132 on page 1 (p90 0.17–0.35) against sign-flip nulls of
  0.63–1.02 and no-field nulls of 0.33–0.50. The archived per-lane
  comparison stays empty (32 C-only lanes per face; the two M lanes
  disagree by 1.26 dots — the frame-scrambled fits §1 describes). Cost:
  2,689 s wall under a concurrent decode, 2,171 s collect CPU, 14.1 GB,
  20 collections, 2 solves, 0 lane-page fits. What one load could not
  say, ten do; and every "not a smooth field" sentence this document
  carried on 2026-09-08 was the identity error, now gated.
- **The sheet-H capture split — ANSWERED 2026-09-08 (W5 replay).** C
  fields of 0.62 dots on the 2400 captures and 0.44 on the 4800 captures,
  levels agreeing to 0.01 within each. Pose error at one footing leaking
  through the median-of-three gauge, or resolution-dependent scanner
  geometry, or decimation quantisation. Under this design it needs no
  one-off: the per-capture residual report of the first pooled solve
  names the disagreeing footing. It named none: over seven captures the
  per-capture residual sits under its noise expectation on C and M
  (0.44–0.89) and at 0.84–1.29 on Y. CORRECTED 2026-09-08 (W7): "the
  2400 captures quietest" is true of the PAIR MEANS only (C 0.510 / M
  0.482 / Y 0.895, against 1200's 0.577 / 0.590 / 1.107 and 4800's
  0.773 / 0.792 / 1.059) — the quietest single capture on C and M is a
  1200, `d792e00a45e7` at 0.460 / 0.439, and on Y a 2400,
  `68c16fcbf29b` at 0.842 (`scratch/page-field-20260908/H/fields.json`
  `residual_by_capture`, each capture's DPI from
  `measure/page_field/README.md`'s sha table). The
  split was the per-lane fitter's, sign-inconsistent between footings.
  AMENDED 2026-09-08 (W6): the corroborating clause read "the archived
  2400 per-lane C fits anti-correlate with the page field (Spearman
  −0.75) while the 4800 lanes correlate (+0.74)" and is RETRACTED —
  it scored a plane-relative lane fit against a word-ink-gauged page
  field, which is two gauges, and read the difference of convention as
  sign. The answer above does not move: the per-capture residual
  energies are the field against its OWN observations and carry no
  gauge question, and the sign inconsistency re-measures LANE AGAINST
  LANE, both sides in the archived fitter's own convention — 72
  cross-footing C pairs 0.968–1.058 dots apart at Spearman
  −0.996…−0.858, against 9 same-footing 2400 pairs at 0.013–0.044 /
  +0.990…+0.997 and 48 same-footing 4800 pairs at 0.012–0.163 /
  +0.827…+0.998 (`measure/page_field/lane_gauge.py`).
  ANSWERED 2026-09-12 from the analyzer side (its plan A4): the
  analyzer's own furniture-only per-lane fields of the same 22
  sheet-H lanes, fitted blind in the PAGE frame, agree across
  footings as well as within one — C cross-2400-4800 pairs |Δx|
  median 0.129 dots at Spearman +0.957 (72 pairs) against
  same-4800 0.105 / +0.972 (66) and same-2400 0.107 / +0.952 (15);
  M and Y likewise (+0.877 / +0.964 cross). The inversion is NOT
  reproduced, so it was the archived per-lane fitter's and not the
  print's or the scanner's — consistent with those fields having
  been spoken in each window's LOCAL frame, which flips both axes on
  a rot-2 placement (the frame error the analyzer's A1 retired on its
  side); the rot_k of the 4800 captures' placements is the check that
  would close it. Numbers: `analyzer/PAGE-FIELD-PLAN.md` §B, product
  `scratch/analyzer/sweeps/field2-page-field/phase-C.json`.
- **The amplitude gap — CLOSED 2026-09-08; its accounting CORRECTED
  the same day (W7).** Two statistics live in this item and the gap was
  stated across them, so every number now carries its own name: a FITTED
  sinusoid amplitude and a column-profile MAXIMUM are different
  quantities of the same profile, and on sheet H they differ by 1.604×.
  e033's 0.83 dots is a profile MAX; the supervised regmap-gt profile of
  sheet I reads max **0.8331** and fitted amplitude **0.5906**. The 0.374
  it was set against is the analyzer's FITTED amplitude on sheet H
  (0.37433 reported; 0.3680 refit here). Measured on the products
  (`scratch/page-field-20260908/H/compare.json` and
  `.../I-four-e034/estimate/compare.json`, where `profile_max_dots` now
  stands beside `mine.amplitude_dots`), the 2.226× "gap" factors exactly
  as **sheet 1.387× × statistic 1.604×** — the statistic is the larger
  half, and this item used to name only the sheet.
  What survives, like-for-like: on sheet I the receiver's Y profile MAX
  is 0.8247 dots from one capture and 0.8281 from four against the
  supervised MAX 0.8331 (0.990× / 0.994×) and against e033's 0.83
  (0.994× / 0.998×) — e033's peak reproduced blind by the receiver's own
  estimator on the same sheet, max against max. On sheet H, both sides
  FITTED amplitudes: the receiver reads 0.4214 dots at 15.60 tiles
  against the analyzer's 0.3680 at 16.20 (its own reported 0.37433 at
  16.0) — the two blind estimates agree within 15 %. The cross-sheet
  number is sheet H's own Y profile max, 0.6006 dots = **0.724×** of
  e033's 0.83: sheet H's Y sinusoid really is smaller than sheet I's,
  which is a different print. All of it measured at TERMINAL facts
  through the certified tier (B3).
- **The old sheet-J Y item is GONE, not amended.** It carried, in this
  order, a conclusion ("not a smooth field at the tile scale"), a
  withdrawal of that conclusion with a wrong attribution (the quality
  floor), and a correction of that attribution (the anchor radius and
  the empty gauge). All three rested on the same void replays. The
  mechanism the W7 correction named — a per-scrap pose off by a dot
  refuses C and M at the anchor wall and leaves an ungauged Y — is a
  plausible reading of the tier constants and it is now measured NOT to
  happen on this capture: all 155 window events carry live C and M mass
  (§2.3). R1 keeps its ruling on its own argument. What replaces the
  item is the two above: the incident, and the first valid measurement.

---

## 8. Provenance

Last, 2026-09-09 to 2026-09-12: the external RE-REVIEW of the W8 tree
(`docs/reviews/page-field-receiver-2026-09-09/REVIEW.md`, eleven findings
R1–R11 with nine reproduction scripts, all reproducing on the branch tip
`d7eabd21`) and its consolidated handoff
(`CLAUDE-IMPLEMENTATION-HANDOFF.md`); the lead's assessment of it
(twelve bounded readers and refuters, 2026-09-11 — findings real,
restraint genuine, two instructions not handed on as written); Germano's
sheet-J chain on that tip (plan §5.2, machine 4 archive mined by seven
readers and re-derived by four refuters); the W9 wave (plan §2's W9
block: nine owned builders, nine adversarial reviews, the lead's edits,
commits 8b8d68f3, 4d714282, cbd3801d and their records); the replays and
oracle modules on the repaired tree, and the six-way in-process bisect
that put the sims' schedule shift on R2 alone. Every W9 number in §2.4,
§2.6, §2.7, §6 and §7 names its run.

Then, 2026-09-08, the external review
`docs/reviews/page-field-receiver-2026-09-08/REVIEW.md` — an independent
pass over the landed tree at `d6bb311d`, eleven findings with seven
reproduction scripts (`lifecycle_counterexamples.py`, `color_assembly.py`,
`planek_border.py`, `collector_counterexamples.py`, `yellow_noise.py`,
`collector_noise.py`, `estimator_counterexamples.py`), each of which
reproduces on this tree — and the W8 charter that rules on it
(`src/holo/receiver/docs/PAGE-FIELD-W8-CHARTER-2026-09-08.md`, R-A to R-G, the lead's, made because
Germano asked for the decisions rather than the questions). Every number
this document attributes to "the external review" was produced by one of
those scripts, and the plan's W8 block maps each finding to the section
that answers it.

The 2026-09-07 audit (nine readers, five refuters, one critic; the
load-bearing findings reproduced by hand against `82d2ac3a` and the
archived snapshots `scratch/analyzer/H7-mirror/facts.npz`,
`scratch/J-run.54028/facts.npz`, `scratch/sheetJ-20260902/J-run-complete.81777/report.json`),
the measured record it cites (e017 P4, e028, e033, e034–e036, PLANE-FIELDS
W6, FIELD2 §2–§4, MEASUREMENTS-2026-08-31, scanfield), and the
2026-09-07 dialogue whose rulings are quoted in §2. Then the 2026-09-08
audit (`scratch/page-field/AUDIT-2026-09-08.md`), the W7 wave it
specified, and the adversarial review of that wave
(`scratch/page-field/W7-review.md`) with its dispositions
(`W7-review-applied-report.md`) — whose measurements are cited in §2.3,
§2.4 and §2.5 with the command that produced each. Then, the same day,
the identity incident (§7) and the W7b wave that withdrew every sheet-J
number those three produced: the audit's ADDENDUM
(`AUDIT-2026-09-08.md`, appended — which of its findings stand against
the printed identity and which fall), `PAGE-FIELD-PLAN.md`'s W7b block,
and `scratch/page-field/W7b-records-report.md`, which lists every
changed claim old against new.
