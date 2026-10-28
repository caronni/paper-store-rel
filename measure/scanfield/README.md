# measure/scanfield — scanner per-channel geometry, measured against the publish floor

Two scanners, one question:

> Across the platen, how far apart do R, G and B put the same physical
> mark, in 600-dpi printed dots, and does that reach the field service's
> **0.25-dot publish floor** (`holo3/plugins/fields.py MIN_DELTA_DOTS`)
> anywhere a payload region sits?

| scanner | instrument | verdict |
|---|---|---|
| Canon LiDE 400 (scanner of record) | `channel_ca` | **NOT USEFUL** — everything 2.8-9x under the floor |
| HP M281fdw flatbed ("home flatbed 1200") | `hp_channel_ca` | **NOT USEFUL AS A FIELD** — a real above-floor offset, but a constant, and no colour capture from it was ever decoded |

The two halves of this file are the two measurements.  They share the
floor, the estimator (`_marks.mark_offsets`) and the pre-registered rule
by import, not by restatement.

---

# Canon LiDE 400 — `channel_ca`

## VERDICT: **NOT USEFUL** — the scanner's channel geometry is 2.8-9x under the floor

Measured on the Canon LiDE 400 (scanner of record), two archived colour
captures of the HCAL-R1 discovery page, 43 achromatic targets each
spanning platen x **4.0-205.9 mm** — the full width a 4 mm-margin
payload page occupies. Read-only; no scan, no print, no decode.

| statistic | dots | µm | as a fraction of a c2 cell (2 dots) |
|---|---:|---:|---:|
| publish floor `MIN_DELTA_DOTS` | 0.25 | 10.58 | 12.5 % |
| **worst single measurement, any pair, any axis, any arm** | **0.090** | 3.81 | 4.5 % |
| worst after removing the platen mean (what a *field* would carry) | 0.087 | 3.67 | 4.3 % |
| worst **reproducible** offset (agrees on both captures) | 0.028 | 1.17 | 1.4 % |
| lateral (x) offset, whole platen, either pair | ≤ 0.025 | 1.06 | 1.3 % |

The pre-registered rule (fixed before any capture was read, and encoded
in `channel_ca.verdict`) was: **USEFUL** iff some pair and axis reaches
0.25 dots somewhere in the payload band *and* reproduces across two
captures of the same scanner. Nothing came within a factor of 2.8 of the
floor, on any of the three tone-curve controls. **Phase B was not
built.**

### The primary table — `marks` arm, 82 targets, two captures, x 4.0-205.9 mm

Per-channel first moments and gradient registration of small achromatic
K marks. A K mark is one physical object in every channel, so the
printer, the toner and the paper are channel-common and cancel
identically in the difference; what is left is the scanner.

| pair / axis | mean | sd | p95 abs | max abs | range of the fitted platen model | over floor |
|---|---:|---:|---:|---:|---:|---:|
| x (sensor axis) R−G | +0.0022 | 0.0033 | 0.0071 | 0.0113 | **0.0003** | 0/82 |
| x (sensor axis) B−G | −0.0054 | 0.0055 | 0.0157 | 0.0251 | **0.0054** | 0/82 |
| y (transport) R−G | **+0.0277** | 0.0037 | 0.0321 | 0.0338 | 0.0028 | 0/82 |
| y (transport) B−G | **−0.0220** | 0.0120 | 0.0330 | 0.0437 | 0.0143 | 0/82 |

All values in printed dots. The fitted model is quadratic in platen x,
evaluated only over the span actually sampled.

**There is a real, reproducible scanner channel offset, and it is a
CONSTANT in the transport direction**: R sits +0.028 dots and B −0.022
dots from G, R-to-B 0.050 dots = 2.10 µm, uniform across the platen
(fitted range 0.003 dots for R−G over the 202 mm sampled; the
right-band-minus-left-band difference is −0.0001 dots for R−G and
+0.0017 for B−G, neither significant at 3 sigma). That is the signature of a
contact image sensor flashing its R, G and B LEDs at slightly different
times within one scan line — a per-channel line-timing offset, not
optics. **A constant is not a field**: the per-plane pose and the plane
field's own constant term already absorb it, so even this reproducible
term carries no information a scanner field could add.

The **lateral** (sensor-axis) offset — the chromatic aberration the
question was really about — is at the estimator's own resolution:
+0.0022 and −0.0054 dots on average, never more than 0.025.

### Cross-capture reproducibility (the invariance premise)

Same targets, same code, two captures on the same scanner (different
sheets, different engines, opposite ~0.145° placements).

| axis / pair | mean, e031 capture | mean, e028 capture | median abs difference, per target | Pearson r |
|---|---:|---:|---:|---:|
| x R−G | +0.0009 | +0.0035 | 0.0041 | 0.13 |
| x B−G | −0.0043 | −0.0066 | 0.0042 | 0.25 |
| y R−G | **+0.0279** | **+0.0275** | 0.0020 | 0.68 |
| y B−G | **−0.0220** | **−0.0221** | 0.0042 | 0.40 |

The y constants reproduce to 0.0002-0.0004 dots — that is a genuine
scanner property. Everything else has near-zero correlation between
captures, i.e. the per-target scatter is measurement noise, not a field.

### The independent estimator agrees — `edges` arm

Every side of seven K rectangles through `scanner/_edge`'s slanted-edge
engine, **polarity-split**: a real displacement moves a paper→ink and an
ink→paper edge the same way, a channel-dependent PSF asymmetry moves
them oppositely, so the pair separates the two.

| pair / axis | displacement mean | max abs | PSF skew mean | skew max |
|---|---:|---:|---:|---:|
| x R−G | +0.0032 | 0.0901 | +0.0097 | 0.0804 |
| x B−G | +0.0007 | 0.0317 | +0.0060 | 0.1205 |
| y R−G | +0.0117 | 0.0302 | +0.0072 | 0.0345 |
| y B−G | −0.0065 | 0.0324 | +0.0035 | 0.0447 |

A different target set, a different estimator, a different failure mode
— same answer. That arm's single 0.090-dot outlier is noise, not a
field: the same target differs by 0.090 dots *between the two captures*.
Skew is reported because a first moment cannot separate it from a
displacement; it is also under the floor, and it is not a displacement
in any case.

### The thing that DOES clear the floor is the printer — `margin` arm

The confetti-field boundary of sheet I (`c2-cmy8-r0700`, the VERIFIED
1,798,761-byte volume), three 2400-dpi captures with the sheet re-placed
between scans. This arm is an **upper bound, not a scanner
measurement**: what it returns is (scanner channel offset) + (printer
per-plane registration), and nothing in it separates the two.

| boundary | platen x | R−G, three captures | B−G, three captures |
|---|---:|---|---|
| left | 4.9 / 5.1 / 6.7 mm | +0.131 / +0.162 / +0.177 | −0.120 / −0.118 / −0.092 |
| right | 205.3 / 205.5 / 207.2 mm | +0.029 / +0.062 / +0.036 | +0.190 / +0.202 / +0.156 |

14 % (B−G) and 24 % (R−G) of these left/right segments clear the
0.25-dot floor, as does 33 % of R−G on the top/bottom pair. And the
shape is **odd-symmetric across the platen** — B−G right-minus-left =
+0.306 dots at 10 standard errors, exactly what lateral chromatic
aberration would look like.

It is not the scanner. The `marks` arm reads the *same platen x* with a
print-cancelling estimator and finds right-minus-left = **+0.0047 dots
for B−G and +0.0002 for R−G**, against the boundary's +0.306 and −0.111
— 65x and 555x smaller, and for R−G not even the same sign. So the
boundary's odd-symmetric signal is the printer's per-plane
magnification (0.306 dots ≈ 12.9 µm of Y-vs-M grid stretch over the
200 mm between the two boundaries, 0.0065 %), which is precisely the
quantity the plane-field service exists to correct. The two arms
together do not just bound the scanner; they *attribute* the effect.

### Robustness

| control | worst raw offset | y R−G constant | y B−G constant | verdict |
|---|---:|---:|---:|---|
| sRGB decode (default) | 0.090 | +0.0277 | −0.0220 | NOT USEFUL |
| gamma 2.2 | 0.090 | +0.0278 | −0.0232 | NOT USEFUL |
| no decode | 0.070 | +0.0287 | −0.0241 | NOT USEFUL |

The transfer function is a control, not a detail: the three channels sit
at different plateau levels on a K edge, so a wrong decode curve could
manufacture the very difference being reported. It does not.

**Estimator calibration** (`--selftest`, seeded, injected truth): worst
recovery error **0.00085 dots** across shifts of 0.1 / 0.5 / 2.0 px,
added noise, a ±15 % per-channel blur mismatch, and a dense speck field.
That is 300x below the floor, so the instrument is nowhere near being
the limit.

## The measured defect that shaped the instrument

The first run of the `marks` arm reported B−G offsets up to **1.96
dots** on the AltaLink sheet — eight times the floor. It was not the
scanner. The AltaLink lays yellow MIC tracking dots on every colour
sheet (experiments/031 §9, 0.210 dots/mm² on a 1.016 mm lattice); they are
invisible in red and green and **dark in blue**, and one of them near
the end of a 6 mm registration-cross stroke moves a first moment by
exactly that much. Three things settled it, and all three are kept:

1. **The engine discriminator.** The M281 sheet has no MIC dots at all
   (experiments/007 §007.7-007.8, blank-paper hunt clean). The same code
   on that capture read 0.16 dots where the AltaLink read 1.96.
2. **A common support mask.** Weights are zeroed outside the mark's own
   footprint (taken from the channel mean, so it is the same region in
   every channel) dilated by 120 µm. `excluded_fraction` reports what it
   threw away and is the standing contamination meter: median 0.0050 in
   blue on the MIC sheet against 0.0001 on the MIC-free one (50x), with
   red and green at 0.0000-0.0001 on both. That is the MIC dots,
   measured, by a statistic that knows nothing about them.
3. **A gradient estimator with no lever arm.** `_gradient_shift` solves
   `min_d ||ref(p−d) − c(p)||²` over the support, so its weight is the
   image gradient and a speck on a plateau contributes a residual, not a
   displacement. The first moment is retained alongside as
   `dx_dots_moment` / `dy_dots_moment`.

The lesson is the one this repo keeps re-learning: a large channel
difference on a colour sheet is a contamination hypothesis until an
engine that cannot produce it says otherwise.

## How to run

```
cd <repo>          # or any worktree
PYTHONPATH=measure env/bin/python -m scanfield.channel_ca --all
```

`scanfield` is the package and every module imports its siblings by
name, so `-m scanfield.<entry>` is the only supported invocation. `src`
is not needed: nothing here imports `holo`, `holo2` or `holo3` (numpy +
tifffile, plus `measure/scanner` for the shared edge engine and sheet
locator).

| flag | what it does |
|---|---|
| `--selftest` | synthetic marks with injected sub-pixel channel shifts |
| `--marks` | 43 K marks per discovery capture, x 4-206 mm |
| `--edges` | every side of seven K rectangles, polarity-split |
| `--margin` | sheet I's field boundary, three 2400-dpi captures |
| `--all` | all four, then the verdict |
| `--tone {srgb,gamma22,none}` | which capture transfer function to invert — the robustness control |
| `--sheets` | which discovery captures (default both colour ones) |
| `--margin-segments N` | boundary splits per side in the margin arm (default 10) |
| `--out DIR` | default `scratch/scanfield/` |

Measured 0 / 12 / 1 / 3 s for the four arms on a warm page cache. Every
capture is opened as a memmap and only the target crops are ever
materialized, so a 6.9 GB TIFF costs its targets and not its size; the
whole run peaks well under a gigabyte and never touches a decode.

Output: `scratch/scanfield/channel-ca[-<tone>].json` — every target with
its platen position and per-channel offset, the per-arm summary with the
fitted platen model, the antisymmetry test, the cross-capture pairing
and the verdict block — plus `channel-ca[-<tone>].png`, the offset map:
four panels on one y-axis of ±0.30 dots so the floor rules sit just
inside the frame. A is the lateral axis and B the transport axis,
scanner only; C puts the payload boundary (scanner + printer) over the
scanner-only marks at the same platen x, which is the attribution in one
picture; D is capture against capture per target. `--no-figure` skips it.

## Inputs (all read-only, all sha-pinned upstream in `scanner/ink_psf.py`)

| capture | what | record |
|---|---|---|
| `scratch/in/xerox-canon-cal-color.tiff` | HCAL-R1 discovery colour, AltaLink C8245, Canon 4800 RGB | experiments/031 |
| `scratch/e028/e028-m281-20260804-color-01-canon-4800rgb.tiff` | the same authored page, HP M281fdw | experiments/028 capture 028.1b |
| `scratch/xerox-canon-18.8-I-…-2400dpi{,-displaced,-displaced2}.tiff` | sheet I payload, three placements | experiments/033 |

Targets are located through the page manifest and the HCAL corner
affine (`scanner/_sheet`), never by pinned pixels, and manifest and
report are matched on `page_plan_semantic_sha256` — the wrong page plan
is a refusal, not a silent mislocation.

## Caveats that belong with any number taken from here

- **Two captures, one scanner, one scanner unit.** This measures *this*
  Canon LiDE 400. A CIS line-timing offset is a design property and
  should port; a lateral aberration need not. Nothing here is a claim
  about scanners in general, and there is no second unit in the corpus.
- **The two discovery sheets sit within ~0.5 mm of the same platen
  translation** (they differ mainly by an opposite 0.145° rotation), so
  the pair cannot separate "locked to the platen" from "locked to the
  page" on its own. It does not need to: the K-differential estimator
  cancels everything print-side by construction. The separation that
  *is* demonstrated is the `marks`-vs-`margin` attribution above.
- **The `edges` arm only spans x 31-107 mm** — the page's big K
  rectangles all live there. Full-width coverage comes from `marks`
  alone, which is why it carries seven independent target families
  (corner marks, four edge-tick rows, plus marks, registration crosses).
  Their family means agree to **0.004 dots in x R−G, 0.007 in x B−G,
  0.007 in y R−G and 0.022 in y B−G** — the last is a target-shape
  systematic (the solid 1.19 mm edge ticks read −0.007 to −0.011 where
  the thin-stroke families read −0.023 to −0.029), an order below the
  floor and consistent with the selftest's blur and skew cases. It is
  the largest unexplained term in the instrument and it does not change
  the verdict.
- **The `margin` arm is an upper bound**, not a scanner measurement, and
  its 0.25-dot exceedances are attributed to the printer only by
  comparison with `marks` — no arm here measures per-plane printer
  registration on its own terms.
- **Both discovery sheets are single copies from single print days**,
  one of them printed via `lpr -o raw` rather than the mandated
  socket-9100 path (e031 §1). That matters for print-side claims and not
  for a channel ratio, which is the only thing taken from them.
- **4800 dpi for the primary arms, 2400 for the margin arm.** A channel
  offset is an optical property in µm on the platen and should not
  depend on the sampling rate, but this instrument has not verified that
  at 1200 dpi and the corpus's 1200-dpi captures were not read.

## What would reopen this

The number to beat is 0.25 dots. Nothing in this corpus is within a
factor of 2.8 of it, and the *reproducible* part is a factor of 9 away
and is a constant. Reopening would need one of:

- a **different scanner** entering the corpus (a second unit, or a
  different model) — the whole measurement is one instrument's optics
  and timing, and none of it transfers;
- a payload rung whose cell is small enough that 0.03 dots stops being
  1.4 % of a cell — at c2 the cell is 2 dots, and the constant would
  have to grow ~9x or the cell shrink ~9x;
- evidence that the **skew** term (max 0.12 dots) matters to a sampler
  in a way a displacement does not — it is a PSF asymmetry, and this
  instrument measures it but does not model what a detector does with
  it.

The printer-side finding, by contrast, is live: `margin` measures 0.31
dots of odd-symmetric per-plane grid stretch across the page on sheet I,
which is above the floor and is the plane-field service's business.

---

# Home/HP flatbed — `hp_inventory`, `hp_targets`, `hp_comb`, `hp_channel_ca`

## VERDICT: **NOT USEFUL AS A FIELD.** The offset is real, six times the Canon's and above the floor — and it is a CONSTANT, flat to 0.009 dots over the whole platen. Nothing varies for a field to carry, and no colour capture from this scanner was ever decoded.

Measured on the HP M281fdw's own flatbed ("home flatbed 1200"), **1,056
achromatic marks across 23 colour captures (of 31 read)**, platen x **5.7-205.7 mm** —
the entire payload band. Read-only; no scan, no print, no decode.

This is a different answer from the Canon's, and the difference matters.
The Canon had nothing: every statistic sat 2.8-9x under the floor. This
scanner has something large and perfectly real. It is just the wrong
shape to be worth a field.

| quantity | dots | µm | against the 0.25-dot floor |
|---|---:|---:|---|
| **transport-axis R-to-B separation** | **0.2965** | 12.55 | **1.19x OVER** |
| transport R-G / B-G against green | +0.1278 / −0.1687 | +5.41 / −7.14 | 2.0x / 1.5x under |
| lateral (sensor-axis) R-to-B separation | 0.0146 | 0.62 | 17x under |
| worst median deviation from the platen constant | 0.0146 | 0.62 | **17.1x under** |
| largest fitted spatial variation, any axis, any pair | 0.0091 | 0.39 | 27x under |
| instrument resolution (selftest at 1200 dpi) | 0.0033 | 0.14 | 75x under |

The first row clears the floor and the fourth does not, and that pair is
the whole verdict. `holo3/plugins/fields.py publishable()` gates on the
**median magnitude of the fitted field over its support** — what varies,
not what the level is — because a constant per-channel offset is already
absorbed by the per-plane pose and by the plane field's own constant
term. Here the level is 0.30 dots and the variation is 0.015. There is a
correction to be had; it is three numbers, not a field.

### The primary table — `marks`, 1,056 targets, 23 captures, x 5.7-205.7 mm

| pair / axis | mean | sd | max abs | median abs dev from mean | fitted range across platen | fitted range down page |
|---|---:|---:|---:|---:|---:|---:|
| x (sensor) R−G | +0.0020 | 0.0122 | 0.0512 | 0.0082 | **0.0021** | 0.0016 |
| x (sensor) B−G | −0.0125 | 0.0186 | 0.1254 | 0.0108 | **0.0074** | 0.0038 |
| y (transport) R−G | **+0.1278** | 0.0188 | 0.1829 | 0.0125 | **0.0068** | 0.0064 |
| y (transport) B−G | **−0.1687** | 0.0249 | 0.2618 | 0.0146 | **0.0081** | 0.0091 |

All values in 600-dpi printed dots. Both fits are quadratics evaluated
only over the span actually sampled — across the platen, and (this
scanner's own axis of concern) down the page.

**Green sits between red and blue, and the offset is on the transport
axis.** That is the signature of a colour scanner that captures its three
channels at three different moments as the carriage moves — a
line-timing or trilinear-sensor offset, not optics. The Canon shows the
identical signature (R +0.0277, B −0.0220, G in the middle) at **one
sixth** the size. Same mechanism, six times worse compensated.

The lateral axis — the chromatic aberration the question was originally
about — is essentially absent: 0.0021 and 0.0074 dots of fitted variation
across 200 mm of platen.

### Why it is the scanner and not the printer: the placement arm

`channel_ca` recorded as a caveat that its two captures sat within 0.5 mm
of the same platen translation, so it could not separate an effect locked
to the platen from one locked to the page. This corpus can. Experiment
004.0b scanned **one physical sheet five times** — flat, displaced,
rotated 90 degrees, rotated 180 degrees — and the two hypotheses make
different arithmetic predictions.

| capture | placement | y R−G observed | platen-locked predicts | page-locked predicts |
|---|---|---:|---:|---:|
| finalists-1-col | re-placed, ~0° | +0.1314 | +0.1312 | — |
| finalists-2-col | displaced | +0.1352 | +0.1312 | — |
| finalists-3-col | rotated 90° | +0.1275 | +0.1312 | +0.0023 |
| finalists-4-col | rotated 180° | +0.1333 | +0.1312 | **−0.1312** |

The 180-degree capture is the clean one. A page-locked term — printer
per-plane registration, or anything else print-side — is carried around
by the sheet, so in platen coordinates its sign must flip. It does not:
observed +0.1333 against +0.1312 predicted, while the page-locked
prediction of −0.1312 is wrong by 0.26 dots, **130 times the agreement**.
The 90-degree capture says the same thing a second way: a page-locked
effect would exchange the two axes, putting +0.1312 on the lateral axis,
and the lateral axis reads +0.0050. B−G behaves identically.

So the effect belongs to the scanner, measured rather than assumed. It
also holds across both print engines (the AltaLink-printed control reads
+0.1124 / −0.1589) and across five different page designs.

### The two named combs are not the answer

This scanner is on record for two periodic hazards, and either could have
manufactured the result: the **18.63 mm sensor-axis chip-joint comb**
worth about **0.9 dot of position step** (experiments/002 §256 — three
and a half times the floor), and the **11.36 px colour-mode comb** that
got colour acquisition from this scanner banned outright (experiments/017
P2). The phase test needs no theory of mechanism: if a comb drives the
offsets, the offsets must vary with phase inside its period.

| comb / axis / pair | binned range | what pure scatter gives | the effect | share of effect |
|---|---:|---:|---:|---:|
| 18.63 mm, y R−G | 0.0084 | 0.0046 | +0.1279 | 6.6 % |
| 18.63 mm, y B−G | 0.0076 | 0.0061 | −0.1688 | 4.5 % |
| 11.36 px, y R−G | 0.0027 | 0.0046 | +0.1279 | 2.1 % |
| 11.36 px, y B−G | 0.0053 | 0.0061 | −0.1688 | 3.1 % |
| 11.36 px, x B−G | **0.0093** | 0.0045 | −0.0125 | (lateral axis) |

Neither comb accounts for more than 6.6 % of the transport constant, and
three of the four sit at or under what scatter alone would produce. The
one entry that does clear its noise band is a **0.0093-dot structure at
the colour comb's period, in blue, on the sensor axis** — 27x under the
floor, and worth recording as the only trace of the 11.36 px comb this
instrument can see in channel geometry at all.

The phase test detrends in platen x first, and that is load-bearing: the
marks sit on their pages' probe lattices, so their phase coverage is
uneven (one bin of the 18.63 mm test held 5 marks against another's 72)
and with coverage like that a smooth platen term redistributes across
the phase bins and reads as a comb. The detrend was added after an
undetrended run flagged the 18.63 mm test on blue's lateral axis as
significant — the axis that carries the one real smooth term in this
corpus. That run also had a quarter of the marks, so it is not a clean
before/after; the reason for detrending is the uneven coverage, which is
a property of the pages and not of any one run.

The spectra arm profiles ink-free paper in every capture (62 strip-axes
across all 31) and finds no large periodic structure at either named
period in any channel:

| period | amplitude, median | p90 | max | between-channel spread, median / max |
|---|---:|---:|---:|---:|
| 18.63 mm (sensor comb) | 0.058 | 0.258 | 1.347 | 0.075 / 0.822 |
| 11.36 px (colour comb) | 0.034 | 0.061 | 0.090 | 0.011 / 0.044 |
| 5.68 px (its harmonic) | 0.021 | 0.032 | 0.049 | 0.006 / 0.021 |

Grey levels, against a paper level of 254 — so the colour comb is at most
0.035 % of paper white here, and the sensor comb's median is 0.02 %.
Note what this arm does and does not settle: it measures an INTENSITY
ripple, while the record's 18.63 mm finding is a **position** step
(§256's "uniform ~−0.9 dot"), and an intensity spectrum cannot confirm or
refute a position artifact. At 18.63 mm the between-channel spread is as
large as the amplitude itself, which says the measurement is
noise-dominated at that period rather than that the channels differ.
This is why the phase test above is the load-bearing check and this table
is context.

### Reproducibility

The five primary captures are the same sheet at five different
placements, so there is no shared target name to pair on and no
correspondence is invented. What is compared is the offset-versus-platen
profile in 12 mm bins, which is the right test anyway: a scanner field is
a function of platen position.

| axis / pair | bin pairs | median abs difference | max abs difference | Pearson r |
|---|---:|---:|---:|---:|
| y R−G | 30 | **0.0054** | 0.0190 | −0.19 |
| y B−G | 30 | **0.0080** | 0.0344 | −0.03 |
| x R−G | 30 | 0.0032 | 0.0131 | −0.20 |
| x B−G | 30 | 0.0036 | 0.0220 | +0.16 |

The constants reproduce to 0.005-0.008 dots. The correlations are at
zero, which is the same finding stated the other way: **only the constant
reproduces**, and the per-bin variation around it is measurement scatter
with no spatial structure to learn. That is precisely why there is
nothing for a field to carry.

### Robustness: the transfer function does not manufacture it

The three channels sit at different plateau levels on a K edge, so a
wrong decode curve could in principle bend their profiles by different
amounts and invent the difference. Re-run on the same six captures
(n = 284) under all three:

| control | y R−G | y B−G | R-to-B | x R−G | x B−G |
|---|---:|---:|---:|---:|---:|
| sRGB (default) | +0.1285 | −0.1754 | 0.3039 | +0.0021 | −0.0153 |
| gamma 2.2 | +0.1276 | −0.1742 | 0.3018 | +0.0021 | −0.0149 |
| no decode | +0.1156 | −0.1587 | 0.2743 | +0.0015 | −0.0110 |

The transport constant moves by at most 0.017 dots across the three —
about 10 % of itself, and in the direction a compressive curve predicts.
It is not the transfer function.

### The pre-registered rule fired, and it should not be read as physics

Run exactly as written, the rule imported from `channel_ca` returns
**USEFUL** on this corpus: some pair and axis reaches 0.25 dots
(0.2618 at `marks/y/B-G`) and the offsets reproduce. That is reported
here as it computed, because the rule is the contract.

It is also a statistic that grows with sample size at fixed physics, and
this run demonstrates that from its own data rather than by argument.
`verdict_robustness` recomputes it as captures accumulate:

| captures | marks | max abs | p95 abs | mean |
|---:|---:|---:|---:|---:|
| 1 | 50 | 0.2211 | 0.2052 | −0.1812 |
| 6 | 284 | 0.2300 | 0.2064 | −0.1754 |
| 15 | 668 | 0.2394 | 0.2075 | −0.1747 |
| 23 | 1056 | **0.2618** | 0.2047 | −0.1687 |

The maximum climbs monotonically; the p95 and the mean do not move. An
earlier 8-capture run of this same instrument reported worst 0.2300 and
**NOT USEFUL** — the verdict flipped on adding captures, while the
population mean moved by 0.007 dots and nothing about the scanner
changed. **1 mark of 1,056 (0.09 %) is at or over the floor.**

Both statements are true and neither is hidden: there is a real
above-floor channel separation on this scanner (R-to-B, 0.2965 dots), and
the single-target maximum that the pre-registered rule keys on is not the
evidence for it.

### So what — nothing that exists would be compensated

This is not the scanner of record, so the payoff would have to come from
decoding its legacy captures. There are none to decode.

Every payload volume ever recovered on the HP-1200 footing is
**greyscale**: experiments/018b records "four full-page grayscale
captures", and `hp-e018b-c2-hp-1200-page.tiff.png` and
`hp-e018b-c3-hp-1200-page.tiff.png` are 8-bit grey, single channel — the
E023b, E023c and E024 chains all ran on those. A single-channel capture
has no channel geometry to compensate. Every colour payload capture in
the corpus, from e016 through e033, is Canon.

The 31 colour captures this instrument reads are the 2026-07-04..06
characterization pages — CAL-1, the modulation and overlap probes, the
density ladder, the loop pages, the finalists checkerboard. None is a
payload sheet, none was ever decoded, and colour acquisition from this
scanner has been banned since 2026-07-19. So the compensation would pay
for a set that is empty today and closed to new members.

That is the answer to "is it useful", and it does not depend on the
0.25-dot arithmetic at all. The arithmetic is what says it would not be
worth a field even if the material existed.

### Caveats that belong with any number taken from here

- **Targets are found, not looked up.** These pages predate HCAL and have
  no manifest, so `hp_targets` locates isolated dark objects in the
  capture itself. The instrument does not know what any mark IS; the
  achromaticity gate (max/min per-channel contrast ≤ 1.45) is the only
  thing standing between it and a coloured object. Measured population:
  contrast ratios cluster at 1.04-1.14, so the gate is not close to
  binding on real K toner, and a single-plane C, M or Y object is
  several-fold away.
- **The displacement-versus-PSF-skew separation is OWED.** A first moment
  cannot tell a channel that puts the mark elsewhere from a channel whose
  ink spreads asymmetrically. `channel_ca` separates them on the Canon
  with a polarity-split slanted-edge arm; here the equivalent needs white
  holes, and across all 31 captures exactly **one** object passed (0.35 mm
  across, inside a 0.4 mm ink collar). One target is not a measurement,
  and the arm reports NOT RUNNABLE rather than a number. What the marks
  arm reports is where each channel puts the mass, skew included — which
  is what a sampler reading cell centres suffers, but is not the same
  claim as a displacement.
- **One scanner unit, three consecutive days.** Every capture is from
  2026-07-04..06: one toner epoch, one environment, no temporal spread.
  A carriage-timing offset is a design property and should be stable, but
  this corpus cannot show that it is, and nothing here is a claim about
  another unit of this model.
- **2 px per printed dot.** The estimator was calibrated for the Canon at
  4800 dpi; it is re-calibrated here at 1200 (worst injected-truth error
  0.0033 dots), so the instrument is 75x below the floor and not the
  limit. The sampling is still four times coarser than the Canon arm's.
- **The comb spectra arm measures the wrong observable for the 18.63 mm
  comb** — an intensity ripple, where the record's finding is a position
  step. It bounds the intensity structure at both periods and nothing
  more; the phase test is what ties either comb to geometry.
- **The tone controls were run on six captures, not all 23** (the
  primary five plus the AltaLink control, n = 284), which is enough to
  show the transfer function does not create the effect but is not the
  full-corpus number.
- **The lateral result now spans the full payload band** (5.7-205.7 mm),
  which the Canon arm also managed; but it is pooled over 23 captures of
  five different page designs, not one authored target set.

### How to run

```
cd <repo>          # or any worktree
PYTHONPATH=measure env/bin/python -m scanfield.hp_inventory
PYTHONPATH=measure env/bin/python -m scanfield.hp_channel_ca --all \
    --roles primary control k-only secondary blank
```

| flag | what it does |
|---|---|
| `--selftest` | injected sub-pixel channel shifts, at 1200 dpi |
| `--marks` | isolated achromatic dark marks on every selected capture |
| `--holes` | the white-hole polarity split (not runnable on this corpus) |
| `--comb` | the 18.63 mm and 11.36 px comb confounders |
| `--all` | all four, then both verdicts |
| `--roles` | which captures — default `primary control k-only` |
| `--tone {srgb,gamma22,none}` | transfer-function control |
| `--bin-mm` | platen bin for the profile reproducibility (default 12) |

`hp_inventory` writes `scratch/scanfield/hp-inventory.json` (every capture
with its experiment, engine, placement and sha256; the five hashes the
logs recorded are checked). `hp_channel_ca` writes
`scratch/scanfield/hp-channel-ca.json` and `.png`, the four-panel offset
map on the same ±0.30-dot scale as the Canon's: A lateral, B transport
(the finding), C the placement arm against both predictions, D the comb
phase test against its noise band.

One capture is resident at a time — these are 557 MB decoded and PNG has
no windowed read — and the whole 31-capture run peaks around 3.4 GB and
touches no decode.
