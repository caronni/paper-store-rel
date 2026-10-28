# measure/ysampler — the Y-anchor sampler measurement

## src/holo diff: zero — the variant exists only inside this process

Standing rule from the project lead (2026-08-30):

> **v1 measurement needs are met by runtime composition inside a
> harness, never by tree edits.**

The ink-free anchor kernel this instrument measures is *composed at
runtime* from production's own parts, for the duration of one
measurement pass, and every substitution is restored on the way out.
Nothing outside this process observes it. The proof is a one-liner:

    git diff 165aa1a^1 HEAD -- src/holo     # empty

An earlier attempt (`9cc5708`, merged at `165aa1a`) got the same numbers
by editing `src/holo/receive/color_anchoring.py`. That edit was provably
inert in production — the removed forced-ink centre is a no-op on every
known-ink anchor and the anchor population came back byte-identical —
and it was still **reverted**, because "inert" is not the bar. The
measurement was not withdrawn; it moved here.

**Nothing here is a test and nothing here runs under `pytest`.**
`measure/` is outside `testpaths` (user ruling 2026-08-21: measurement-
instrument code lives in neither `tests/` nor `scratch/`). Nothing here
is imported by `src/holo`.

## The finding this exists for

`docs/COLOR-UPLIFT-MEASUREMENTS.md` §15.5, closing finding 4 of the
PK6/A2 measured negative:

> Y anchors are not currently measurable at fine pitch (dust-only
> supply, 9–22% correlation-edge saturation, strongest peak-lock) — a
> sampler improvement … is prerequisite to ANY Y-side registration
> claim.

"Dust-only" is literal, and the archived field corpus
(`scratch/color-uplift/regmap/*-regmap.npz`) states it exactly: the Y
**word** bucket holds **0** anchors on all four captures, in all three
passes, against 6.5k–83k for C and M. The cause is two facts meeting:

* `format/pilots.py::color_word_states` renders the v1 colour word as
  states `{0, 3}` — state 3 is C+M, so **no word site ever carries Y**;
* `receive/color_anchoring.py` requires known **INK** at the anchor
  centre, in two places: the candidate gate inline in
  `_fit_registration`, and `_measure_anchor`'s forced
  `bits[1, 1] = 1` / `weights[1, 1] = 1.0`.

Every Y word site is therefore a known cell the sampler refuses to
anchor on, purely for its polarity.

## How the variant is composed (`composition.py`)

Polarity is not what makes an anchor: the NCC template is built from the
whole 3×3 known/blind block, so a known ink-free centre in an inked
neighbourhood localizes exactly as an inked centre in a bare one. The
harness lifts the polarity requirement in both places without touching
the tree.

**The candidate gate** is inline in `_fit_registration`, so there is no
function to substitute. The *rows* are substituted instead:
`flip_known_component_bits` returns a `_Rows` whose known component bits
are inverted **at known sites only**. That retargets the inline gate
onto exactly `mask & ~true_bits & search` — the ink-free population —
and is undone inside the one substituted function, so the NCC template
still sees the true field. The inversion is an exact involution over the
only two readers of `known_component_bits` in the `_fit_registration`
call tree (the gate and the prepared field). Selection, dedupe, budget,
key order and `RegistrationAnchors` construction all stay production's
own code.

**The forced centre** is lifted by substituting
`color_anchoring._measure_anchor` with `measure_anchor_true_centre`:
production's body with the two forced-centre lines absent and the
un-flip added. `fit_plane_residual` is stubbed for the pass — nothing
consumes a measurement pass's residual and a Theil–Sen over these
anchor sets is pure cost. Both are restored in `finally`. These seams
are main-thread and serial (verified for `_color_uplift_harness.regmap`,
which uses the same technique on the same functions).

## The seam, named

`measure_anchor_true_centre` is **the one production body this harness
restates**, and it is fragile against future `color_anchoring`
refactors. Three guards make drift loud instead of silent:

1. `assert_kernel_seam` refuses to run unless production's
   `_measure_anchor` is still statement-for-statement the body this
   variant copied (`ast.unparse`-normalized, docstring dropped — a
   reflow or comment edit is not a false alarm; a semantic move is).
2. `assert_inline_gate_seam` refuses unless `_fit_registration` still
   carries the inline known-ink gate the rows flip retargets, its
   search-lattice term, and the prepared-field write the un-flip
   cancels.
3. **The identity control** (below) re-runs the composed pass with the
   polarity lift switched off and requires the result to be bit-identical
   to production's own return. A copied body that has drifted cannot
   pass it.

Guards 1 and 2 fail *closed*: `SeamError`, no numbers emitted.

## The instrument

`anchor_supply` runs ONE bounded specimen-patch decode with a read-only
spy at the `_fit_registration` seam and records three passes over the
identical rows and features:

| pass | what it is |
|---|---|
| `prod` | untouched production — what the residual fit consumed |
| `control` | the composed kernel with the polarity lift **off**; must be bit-identical to `prod` |
| `ink-free` | the composed kernel on known ink-free centres — the measurement |

The control is the integrity proof: on the known-ink population the
forced centre is provably a no-op, so any difference means the
composition diverged from the production kernel, and the JSON says so in
`identity_control.verdict`. `--skip-identity-control` omits it (the
ink-free numbers then carry no such proof).

The spy forwards the production return verbatim and never writes back,
so the decode is bit-identical to an uninstrumented patch run; only the
wall time moves.

    cd <repo>
    PYTHONPATH=src:measure env/bin/python \
        -m ysampler.anchor_supply --name frozen-cmy7 \
        --out scratch/ysampler/frozen-cmy7.json \
        --anchors-npz scratch/ysampler/frozen-cmy7-anchors.npz

`frozen-cmy7` is cut from `xerox-c2-cmy7`, the §15 PRIMARY capture, at
`cell_dots = 2` — the fine-pitch regime the finding is about.

SATURATION is scored with `regmap_analyze.pregates`' own G3 constants,
so the numbers sit next to §15.4's line for line.

## Reproduced measurement — `frozen-cmy7`, 2026-08-31

Run through the runtime composition on the **reverted** tree. These are
the same numbers the in-tree version produced, to the anchor row: the
computation is identical, so anything else would mean the composition
diverged.

| plane | production word / total | ink-free word / total |
|---|---|---|
| C | 2,838 / 3,288 | 2,491 / 3,096 |
| M | 2,889 / 3,255 | 2,392 / 3,124 |
| **Y** | **0 / 622** | **3,430 / 3,827** |

Y word anchor quality **0.668** median NCC, **0.164** G3 saturation,
against Y's production dust anchors at 0.834 / 0.119 — the supply half
of finding 4 closes, the saturation half does not (see §15.6 for the
search-radius mechanism).

Identity control: **PASS** — 7/7 region fits, and the composed
known-ink population is byte-identical to production's over all
**7,165 anchor rows** (`np.array_equal` and equal `tobytes()`; all six
`RegistrationAnchors` arrays per plane). That is §15.6's cross-tree
null proof re-derived inside one run. Decode outcome 0 certificates /
0 wrong, its pinned value; 7 region fits; peak RSS under 0.9 GB.

## The per-plane search radius (ruled 2026-08-31)

Project-lead ruling: the anchor search radius becomes PER-PLANE — Y at
±2.2 dots, C and M untouched — harness-side, never in `src/holo`.
`_ANCHOR_MAX_SHIFT_PX` is plane-COMMON in production, so
`composition.make_measure_anchor_true_centre` sets that module constant
around ONE `_rectified_ncc` call and restores it in `finally`.  A plane
the caller does not name never enters the branch, which is what makes
"C and M untouched" **structural** rather than a claim;
`assert_radius_seam` refuses the override if the radius stops being
derived from that constant.

The rectification quantizes the radius to ½ dot, so ±2.2 is honoured as
a LOWER bound (§15.6's own number is a censored bound) and the realized
**±2.5** is what the report carries.

`anchor_supply` measured, `frozen-cmy7`, identity control PASS, 0
certificates / 0 wrong (its pinned outcome).  Every recorded number
reproduced to the anchor row, and C and M came back **byte-identical**
across the radius change (3,096 and 3,124 rows, equal `tobytes()`):

| Y word anchors | ±1.5 dots | ±2.5 dots |
|---|---|---|
| anchors | 3,430 | 3,434 |
| saturation | 0.164 | **0.100** |
| median NCC quality | 0.668 | 0.677 |
| \|dx\| p50 / p75 | 0.393 / 0.715 | 0.422 / 0.827 |
| \|dx\| p95 / p99 | 1.50 / 1.50 (the wall) | **2.50 / 2.50 (the wall)** |

The wider radius buys 39% of the saturation and no quality, and the tail
is still AT the wall.  Saturation by quality quartile — 0.085 / 0.139 /
0.108 / **0.067** — says the runaway tail is a peak-lock population, not
a registration signal: about a tenth of Y word anchors will run to
whatever wall they are given.  G3's 2% bar is not reachable by widening.

## PHASE 1 — the bias check (`gt_bias.py`), 2026-08-31

The question the supply measurement could not answer: does the new Y
anchor lattice measure the sheet's REAL per-plane registration, and on
what scale?  Answered on **sheet I** (`L:c2-cmy8-r0700-p120-x1@3392x2368`,
the AltaLink print whose volume closed VERIFIED), the only printed page
carrying both halves of a registration ground truth — the e033
GT-correlation tool's per-tile plane displacements (`regmap-gt/
plane-offsets.json`) and the plane-fields swim pilot's decode-optimal
offsets.  **No decode**: poses come from the GT tool's own page affine
plus its own per-patch plane-COMMON lock, the format supplies the
furniture, the capture is a memmap read one tile at a time.  481 GT
tiles, 13 rows × 37 columns, ~160 s, ~1 GB.

Everything is made plane-relative — `Y − (C + M) / 2`, the GT file's own
`dY_rel_x` — which cancels the page affine, the paper's pose and the
scanner's common warp out of both sides.  `C − M` is the control.

### VERDICT: PASS — the anchor tier measures the sheet, at gain ~1

Measured on the **corrected** frame (see the half-cell note below), with
the PRODUCTION kernel (`field_tiers.anchor_offsets`) on the PRODUCTION
site partition (the format's furniture, halved by site parity), against
the recorded per-tile `dY_rel_x`.  **All 481 GT tiles**, 145 s:

| estimator | Pearson | Spearman | sign | gain |
|---|---|---|---|---|
| **anchor, sparse furniture kernel (production)** | **+0.916** | +0.919 | 0.88 | **0.936** |
| anchor, dense whole-tile furniture template | +0.937 | +0.942 | 0.92 | 0.976 |
| photometric (`plane_field`) | +0.843 | +0.846 | 0.88 | 0.527 |
| word sites, 3×3 blind block | +0.858 | +0.871 | 0.87 | 0.408 |
| word sites, ink-free 3×3 block | +0.886 | +0.900 | 0.90 | 0.439 |

At the recorded **per-column** means — the sharp form of the sinusoid,
13 rows each — the anchor reads Pearson **+0.982** at gain **0.972**;
the photometric tier reads +0.919 at gain 0.556.  The `C − M` control on
the same tiles: **+0.970** at gain 1.045.  Bootstrap of the anchor's
gain over 481 tiles: **0.936 [0.905, 0.968]**; across the 13 tile rows,
median 0.925, range 0.857–1.115.

Supply: the production tier returns **one measurement per tile per
plane, on all 481 tiles, on every plane including Y** (median NCC
quality 0.486 on Y against 0.863 on C) at **zero saturation** — it is
never at its wall.  The dense whole-tile arm correlates slightly better
but saturates hard on C and M (0.57 and 0.75), which is why the sparse
parity-halved form is the one that ships.

**Two gains, and they are not the same question.**  Against an INJECTED
displacement, with the template and the level table frozen (which is the
production situation — the pose an anchor measures against is
plane-COMMON and the displacement is per-plane), the anchor reads slope
**1.000** on C and M with an rms nonlinearity below 0.001 dot over a
±0.75 dot sweep, and the photometric tier reads 1.042 / 0.950 / 0.830.
Against the sheet's own recorded displacement the anchor still reads
~0.95–1.00 and the photometric tier reads **0.46–0.51**.  The
photometric tier responds correctly to a displacement it is shown and
under-reads by about half the one the printer actually made; that is
measured, and this instrument does not explain it.

`ANCHOR_GAIN` in `holo3/plugins/field_tiers.py` is therefore **1.0** —
the frozen-template calibration, and a no-op division rather than a
fitted correction nobody needs.

**RETRACTED, same day.**  A first pass reported the 3×3 blind-template
anchor at gain −0.07 ("measures nothing") and the photometric tier at
0.04 on Y ("20× attenuated").  Both were measured on a frame carrying a
HALF-CELL error — the instrument's affine put the sampler on the cell's
corner, not its centre, so every plane read a common +1 dot at c2.  The
error was plane-COMMON, so it cancelled out of the plane-relative
comparison and the shape numbers were not obviously wrong; it was the
per-plane gains it destroyed.  On the corrected frame the 3×3 anchors do
track the sinusoid (+0.84 to +0.87) at about 40% amplitude, which is
attenuation, not blindness.  The claim that the anchor tier needs a
truth-independent template still stands on its own evidence (below), but
it is a factor of ~2.4, not a factor of infinity.

Against DECODE-OPTIMAL (the swim pilot's `ber_argmin_dx`) the anchor
overshoots, as every direct estimator in the record does — measured on
the pre-correction frame at 1.3–1.9× over three dead-band tiles, between
the recorded regmap-gt (1.47) and dust (2.33).  Two different gains, and
they must not be confused: ≈1 against where the ink physically landed,
>1 against what the decoder wanted.  n = 3, and owed on the corrected
frame.

### The mechanism, and why the template matters

Injecting a known frame shift with the template RE-READ at each shift
gives slope +0.05 / −0.06 / −0.05 (C/M/Y) — no response at all — while
the same probe with the template FROZEN gives ~1.0.  That is not a
subtlety of the instrument: it is what a 3×3 block made of one known
cell and eight blind neighbours does when the pose under it moves.  The
production tier avoids it by construction: `rectified_ncc` is general
over template SHAPE, so the template is the whole tile with weight 1.0
at the format's own sites and 0.0 everywhere else — blind,
truth-independent, ~60 known cells per tile after the parity split, and
the same object `measure/yask`'s A1 arm found by a different route.

The tier runs SPARSELY (~4 ms a tile against the dense whole-tile NCC's
90 ms at c3, same evidence): the template is 120 of a tile's 4,096
cells, so correlating whole pixel blocks spends 34× the work to use the
same sites.  That kernel is the one calibrated above.

### Caveats

One sheet, one capture, one engine.  The pose is the GT tool's page
affine plus its recorded per-patch plane-common lock, standing in for a
committed window pose; the substitution is fair but it is a
substitution.  The photometric solve here is deliberately UNRIDGED and
unsmoothed, one tile at a time, so that shrinkage does not enter a
number being read as estimator gain — production pools and shrinks, and
would read lower still.  The corrected run covers 150 of the 481 GT
tiles; the full-grid re-run was killed unfinished when the machine went
to load 143.

### Where phase 1 landed

The tier was built, in holo3, on this measurement:
`holo3/plugins/field_tiers.py` (the anchor and blind-offset tiers and
the attribution law) and `holo3/plugins/fields.py` (the joint fit).
`ANCHOR_GAIN = 0.94` is this section's number and nothing else; the
production kernel is the SPARSE one (`field_tiers.anchor_offsets`), and
this instrument measures it directly — `--population sparse` — rather
than letting it inherit the dense kernel's calibration.

Two instrument bugs found on the way, both worth the next person's time:

* **the half-cell.** `_sheet_i.tile_affine` mapped a cell index to the
  cell's CORNER, because the GT tool's page affine maps a dot coordinate
  to that dot's corner, while every sampler downstream reads an integral
  cell coordinate as the cell's CENTRE.  Every plane then read a common
  +1 dot at c2 — invisible in the plane-relative comparison, and it ate
  the search radius (M saturated at the wall on every tile).
* **the self-referential probe.** The first response calibration moved
  the sampling frame and re-derived the template and the level table at
  the moved frame, so both estimators followed the probe and read slope
  ~0.  Freezing them is not a convenience: it is the production
  situation, because the pose an anchor measures against is
  plane-COMMON and the displacement it is measuring is per-plane.

## PHASE 2 — the tier, and where its gates stand

Built in holo3: `plugins/field_tiers.py` (the anchor and blind-offset
tiers, the attribution law, the per-tier accounting) and
`plugins/fields.py` (three tiers in one fit).  What the gates say, and
what is still owed, stated plainly because the machine ran out from
under the last of them.

| gate | status |
|---|---|
| fast suite | **PASS** — 1,575 passed, 415 skipped |
| attribution pins (disjointness, accounting sums, leave-one-out exactness) | **PASS** — 43 tests in `test_h3_plane_fields.py` |
| units pin (write side and read side agree on one dot) | **PASS** — new test, and the bug it pins is fixed |
| clean colour sim unmoved by the dial | **PASS** — dial-off and dial-on certificate signatures IDENTICAL (`44223c3d…`, 279 each), and with `plane_relative` the dial-on run now publishes NO field at all |
| the original existence proof | **FAILS ON MAIN, BEFORE THIS BRANCH** — reproduced on a pristine `main` checkout: control 300 certificates, displaced 300, **zero lost**.  The stimulus no longer exercises the mechanism, which is exactly what its own assertion says.  Three of its eight tests fail there |
| displaced-plane yield, dial on | **PASS** — 300/300, payload byte-exact, and the Y field's median delta is **1.13 dots** against a 2-dot injected sinusoid (the record's W6 note for the old fitter reads "about a quarter") |
| cross-tree dial-off null | **PASS** — the same colour sim decoded by a pristine `main` checkout and by this branch: certificate signature IDENTICAL (`44223c3d…`, 279 each), payload identical, and every scheduler row's job count identical line for line (`color` 48, `place` 537, `refine.color` 14, `revisit` 15, `survey` 1, `tiles.retry` 50, `tiles.scan` 220) |
| the FAINT existence proof | **STIMULUS BUILT, RUNS IN FLIGHT** — `_h3_sims.render_hard_faint`, `--sim hard-faint`.  It is expensive BY CONSTRUCTION and not because it is broken: measured without a decode, Y still reads d′ 6.37 at the 0.30 fade against the rung's ~2.8 floor, so the band is not below the detector — it sits on the knife edge, and the dial-off arm has no way to fix it, so its rescue tiers grind (18:44 CPU and counting per decode) |
| per-tier ablations (GATE 3) | **DONE, by exact subtraction rather than by ablation** — see the table below.  Certificate-level ablation is structurally unobtainable on these sims (`field_tiers`' dated note); leave-one-tier-out on the normal equations answers the same question exactly and needs no headroom |
| workers 1 == workers 8 | **PASS** — 300/300 each, certificate signature identical (`c31d3d14…`), address sets equal, payload byte-exact.  Re-run after the merge |
| the full 481-tile phase-1 re-run | **PASS** — table above; supersedes the 150-tile version |

### THE ORDER — subtract the common part, THEN clamp

Settled 2026-08-31.  `MAX_DELTA_DOTS` bounds a PUBLISHED per-plane
delta, and the question is whether `plane_relative` runs before or after
the clamp.

**Measured on the displaced sim with a clamp that genuinely binds.**
The real 2.0 ceiling does not bind at all here (max |δ| 1.785, zero
tiles clipped), so the ceiling was lowered to 0.8 — same page, same
evidence, same fit, one constant — until 90 of 100 tiles clipped.  The
two orders then came back INDISTINGUISHABLE: 300/300 certificates each,
identical certificate signature, identical payload, both publishing Y
alone, ΔPearson 0.0005 and Δgain 0.006 against the injected sinusoid.

**That is not the answer, and taking it as one would have been wrong.**
The orders can only diverge when a plane-COMMON component still reaches
the clamp, and on this page the fitted field's common part is ~0 — so
clamping before or after subtracting zero is the same operation.  The
clean colour sim, however, measures that common part at **0.97 dot** on
all three planes.  Combining the two measured scales (clean-sim common
0.97, displaced-sim per-plane 1.14):

| common | per-plane | ceiling | subtract-first | clamp-first |
|---|---|---|---|---|
| 0.00 | 1.14 | 2.0 | 1.140 | 1.140 |
| 0.00 | 1.14 | 0.8 | 0.800 | 0.800 |
| **0.97** | 1.14 | **2.0** | **1.140** | **1.030** |
| **0.97** | 1.14 | **0.8** | **0.800** | **0.000** |
| **1.50** | 1.14 | **2.0** | **1.140** | **0.500** |

Clamp-first loses 10% of the per-plane amplitude at the real ceiling, 56%
at a larger bias, and **annihilates the field entirely** when the bias
alone reaches the ceiling — because clipping three planes by different
amounts destroys the common part the subtraction was going to remove.
Subtract-first is unaffected in every row.  `settle` therefore subtracts
first, and the unit pin covers the regime the decode could not reach.

(The composite rows take their scales from two different sims and are
labelled as such; they are a worked case with measured inputs, not a
measured page.)

### A defect the w1 gate exposed in `plane_relative` — FIXED

`fields.plane_relative` publishes `p − mean(q ≠ p)`.  That cancels a
plane-COMMON bias exactly, which is what it was written for, and it also
REDISTRIBUTES one plane's real displacement onto the other two.  With
truth `(0, 0, D)` it returns `(−D/2, −D/2, D)`: Y is right and C and M
each acquire a spurious correction of half Y's displacement, in the
wrong direction.

Measured, not derived — the workers-1 gate run on the displaced sim
publishes Y at 1.117 dots and C and M at 0.45–0.56, against a predicted
`D/2 = 0.559`.  It cost nothing there (300/300, payload byte-exact,
because C and M had margin), but on a marginal plane it would.

FIXED: `plane_relative` subtracts the MEDIAN across the three planes.
`median(b, b, b) = b` cancels a common bias exactly as before, and
`median(0, 0, D) = 0` leaves a single displaced plane's neighbours
alone.  Confirmed on a decode: under the mean-of-others form C and M
published spurious fields at 0.45–0.56 dots on a sim where they were
never displaced; under the median form they publish NOTHING and Y alone
publishes, at median 1.141 dots.

The owed rows are owed to a machine at **load 148** from other agents'
decodes, not to a difficulty: every one of them is a single command
against a driver that is already wired.

## GATE 3 — what each tier contributes, by exact subtraction

Tiers add as normal equations, so a tier's effect is its equations
SUBTRACTED and the fit re-solved — exact, and needing no certificate
headroom (which these sims do not have).  Displaced sim, dial on,
300/300 certificates, payload byte-exact:

| plane | tier | observations | weight mass | median effect | max effect |
|---|---|---:|---:|---:|---:|
| **Y** (published, δ 1.141 d) | photometric | 542,315 | 19,898.5 | **0.1228 d** | 0.2746 d |
| | anchor | 163 | 162.79 | **0.0020 d** | 0.0044 d |
| | blind | 249 | 1.33 | **0.00001 d** | 0.0001 d |
| M (refused, δ 0.004 d) | photometric | 542,315 | 5,485.6 | 0.1857 d | 0.3114 d |
| | anchor | 164 | 163.99 | 0.0061 d | 0.0132 d |
| | blind | 155 | 0.0027 | 0.00000 d | 0.0000 d |
| C (refused, δ 0.002 d) | photometric | 542,315 | 5,482.6 | 0.1801 d | 0.4123 d |
| | anchor | 164 | 163.99 | 0.0063 d | 0.0105 d |
| | blind | 95 | 0.0014 | 0.00000 d | 0.0000 d |

`gain_check`: not refused on any plane, 90 overlap tiles.

**Read it honestly.**  On a page with abundant certified payload the
photometric tier carries the fit almost entirely — 122× the anchor
tier's weight mass and 15,000× the blind tier's — and the other two move
the field by thousandths of a dot.  That is the expected shape (the
anchor tier's case is the STARVED regime, which this sim is not), but on
this evidence alone neither new tier has yet earned its place.

### The faint stimulus does not change it — and that is the finding

Same accounting on the faint page (300/300, payload byte-exact, 140
windows against 69):

| plane Y | photometric | anchor | blind |
|---|---:|---:|---:|
| weight mass, displaced | 19,898.5 | 162.79 | 1.33 |
| weight mass, + faint band | 26,638.6 | 163.67 | 2.10 |
| median effect, displaced | 0.1228 d | 0.0020 d | 0.00001 d |
| median effect, + faint band | 0.2271 d | 0.0016 d | 0.00003 d |

The faint band was supposed to STARVE photometry and hand the page to
the other two tiers.  It does the opposite: the photometric tier's
weight mass RISES (more windows, more sites) and the ratio widens from
122× to 163×.  The reason is the one already measured without a decode —
at the 0.30 fade Y still reads d′ 6.37 against the rung's ~2.8 floor, so
photometry was never starved.  **Neither simulation in this tree
reaches the regime the anchor tier exists for.**

That regime is on paper, not in the sims: sheet I's Y, where the
photometric estimator reads gain 0.53 against the recorded ground truth
and the anchor reads 0.94–1.00.  The anchor tier's justification is the
PHASE 1 measurement; the sims show only that it is wired, exact, and
harmless.  A stimulus that genuinely starves photometry is owed to the
yield-repin line's stimulus family and would be the first sim evidence
either new tier could earn its place on.

**The blind tier's weight is not commensurate with the anchor's, and
that is unresolved.**  An anchor weighs itself with a correlation
coefficient (mean 0.999 per observation here); a blind offset weighs
itself with a held-out log-loss improvement spread over its window's
tiles (mean 0.005).  Both are admitted at their own natural size, which
is the only honest thing to do before the scaling is measured — no
factor has been invented to make them comparable.  Until that
measurement exists the blind tier is wired, reported and effectively
inert.

## What this tier can claim

Development signal from the replay tier. A patch is a SCRAP: its
certificate count is not a capture-level number (`patch_runner`'s own
caveat). Anchor **supply** and **saturation** are properties of the
sampler on real printed cells; that is what the instrument measures and
all it claims.

## What is deliberately NOT done

The variant is measurement-only and lives nowhere but this process.
`_fit_registration` consumes the historical known-ink anchors alone, so
every production decode — all three planes — is bit-identical and no
policy id moves. Feeding the ink-free anchors to `fit_plane_residual`
would move Y sampling on every archived colour state and is a separate,
policy-bumping adoption decision that belongs to a gated campaign.

## What the runtime form cannot do that a tree edit could

* **No production consumer.** A harness-local variant can be measured
  but never adopted. The adoption step — should it ever be ruled — is a
  tree change with its own policy-id bump, not a promotion of this code.
* **No pytest pin.** `measure/` is outside `testpaths`, so the
  invariants that made the forced centre a no-op have no standing test.
  The identity control replaces that pin, but it only runs when someone
  runs the instrument.
* **It restates one production body.** See "The seam, named" above. The
  in-tree form had none, because the kernel was factored once and shared.
