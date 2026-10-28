# yask — the Y-as-K experiment

Filter a colour scan for yellow, render the residue as black on white,
read it with the black-and-white machinery, and address it from
outside. An instrument under `measure/`; nothing in `holo3/` is
touched, and no production arm exists until the lead rules on this.

---

## 1. The verdict

**USEFUL.** On sheet H (`L:c2-cmy8-r0850-p120-x1@3392x2368`, the
2026-08-18 AltaLink print whose volume has never closed), reading the
yellow plane this way recovers yellow tiles that the production
seven-capture harvest left uncertified — every one of them matching the
emitted payload bit for bit, with **zero wrong certificates anywhere in
the battery** and a null arm that certifies nothing.

**One 2400 dpi capture**, eight crops, 324 tiles all C- and
M-certified in production, 105 of them Y-certified there and **219 not**:

| arm | what it is | Y certs | GT-exact | WRONG | **adds** |
|---|---|---:|---:|---:|---:|
| C0 | control: the raw blue channel | 0 | 0 | 0 | **0** |
| C1 | C and M annihilated in the mean, no per-cell subtraction | 25 | 25 | 0 | **1** |
| A0 | + per-cell certified-sibling subtraction | 39 | 39 | 0 | **5** |
| A1 | + blind per-window sampling offset (dust-anchored) | 48 | 48 | 0 | **15** |
| N0 | NULL: each tile decoded from its neighbour's evidence | 0 | 0 | 0 | **0** |

**All seven captures**, the same evidence production had, over the six
crops that carry a yellow gradient — the four marginal blocks plus H-d
and H-c (234 tiles, production Y 98, **136 uncertified**):

| arm | Y certs | GT-exact | WRONG | **adds** |
|---|---:|---:|---:|---:|
| A1 (one capture, same six crops) | 47 | 47 | 0 | **15** |
| A2 (seven-capture union) | 116 | 116 | 0 | **32** |

**32 yellow tiles that a seven-capture production harvest of the same
sheet did not have** — 24% of the yellow that was missing in those
crops — and the same run re-derives 84 of production's own 98. Run on
all nine crops, including the three cut around dead bands, A2 is 131
certificates, 131 GT-exact, 0 wrong, and still 32 adds: the three
dead-band crops contribute none.

Reading the first table downwards is the whole experiment. The naive
"yellow absorbs blue" readout certifies **nothing at all**. Cancelling
cyan and magenta in the mean gets 25 tiles. Subtracting known siblings
per cell gets 39. Letting each window choose its own sampling offset,
blind, on the format's own dust sites gets 48 — and takes the additive
count from 1 to 15. The union then doubles it again.

Three things the battery also settles:

* **The composition is sound.** A stand-alone yellow decode goes
  through the unchanged `tile_codec.cmy8_decode_stream` and produces
  certificates that are byte-identical to the emitted payload. cmy8's
  per-plane independent LDPC makes this exact, not approximate.
* **Yellow is not missing from the failing bands — it is buried under
  magenta and displaced.** Sections 4.1 and 4.2 measure both, and the
  displacement measurement independently reproduces e033's yellow
  registration sinusoid from a blind estimator.
* **The fully dead columns stay dead.** On H-a (tx 18-21, production
  yellow 0/24) nothing new certifies at any offset with any number of
  captures; on H-b (tx 0-3, no yellow certificate anywhere in the crop)
  the seven-capture union certifies **nothing at all**. Section 4.4
  says why in numbers, and it is a rate fact, not a receiver fact.

### The pre-registered bar

> at least one Y-stream certificate passes the full codec gate AND
> matches emitted ground truth bit for bit, on a tile where the
> production run left Y uncertified, with zero wrong certificates
> anywhere.

Met on the arm's cheapest configuration, before any union. The first
one was tile `(9, 12)` on case `H-d`: production holds C and M there
and no Y; this arm's certificate matches all 3,368 emitted user bits,
from one capture, in 57 belief-propagation iterations.

---

## 2. What is blind, and what is not

The one thing that must not be fudged, so it is stated flatly.

| input | where it comes from | blind? |
|---|---|---|
| poses, page, addresses | the production harvest's own committed poses | yes — ordinary receiver knowledge |
| C and M cell values | the emitted payload, **only at addresses production certified** | yes in substance: those are the bits that run's own certificates hold |
| yellow labels for calibration | format truth — 100 word sites (yellow-blank) and 20 dust sites per tile — plus payload cells of Y-certified neighbours | yes |
| the emitted CELL FIELD | d', cell error rate, and the X1 oracle arm | **NO — measurement only**, never on a path that can mint a certificate |

Yellow never self-addresses, and that is format law, not an accident:
the colour address word renders states {0, 3}
(`src/holo/format/pilots.py:185-195`, `color_word_states`), whose
yellow bit is zero at all 100 word sites. A yellow-only reader cannot
find the page. Every pose here therefore comes from a run that placed
and addressed through C and M — the "external addressing" the proposal
called for.

The certified-sibling row is not taken on trust: section 4.3 ablates it
two ways and reports what each is worth. The truth chain itself is
gated before any report is written — the payload is checked against the
generation manifest's sha256, re-encoded to per-tile user bits through
`src/holo`'s generation arithmetic, projected back to cells through the
format's own `certified_projection`, and compared to the emitted dot
field: up to 12 tiles per case, **983,040 cell bits across the battery,
all exact**, refusing the run on any disagreement.

---

## 3. Method

### 3.1 Spectral isolation (`_spectral.py`)

A cell's three sampled channel means are modelled as

```
v = m0 + mC·C + mM·M + mY·Y + noise,    C, M, Y ∈ {0, 1}
```

fitted by least squares on every cell whose three plane bits are known.
Measured on H-a (2400 dpi, one capture), with `m0 = (155.4, 135.5,
117.5)`:

| plane | mean shift (R, G, B) |
|---|---|
| C | (−54.3, −12.6, −4.4) |
| M | (−0.7, −55.9, **−23.0**) |
| Y | (+1.0, −1.2, **−38.6**) |

**That −23.0 is the whole problem.** Magenta darkens blue by 60% of
what yellow does. The blue channel is not a yellow readout; it is a
yellow-plus-magenta readout, and magenta is the larger nuisance because
it is present on half the page.

Two readouts follow, and one control:

* `project` (C1) — the minimum-variance functional `w` with `w·mC = 0`,
  `w·mM = 0`, `w·mY = 1` under the fitted residual covariance. Cyan and
  magenta cancel in the mean; nothing per-cell is needed, so it works
  everywhere. Measured `w ≈ (−0.0004, +0.0108, −0.0263)` — it buys the
  blue channel by *subtracting green*, i.e. by subtracting magenta.
* `subtract` (A0) — where a cell's C and M bits are known, subtract
  their contribution exactly and project the residual on `mY`. Falls
  back to `project` cell by cell.
* `rawb` (C0) — the blue channel's own deficit. The control.

The synthetic "yellow as black on white" image is never materialized,
and nothing is lost by that: holo3's aperture filter and the unmixing
are both linear, so unmixing the sampled channel means **is** sampling
the unmixed plane.

### 3.2 The black-and-white read (`_read.py`)

Library calls into unchanged holo3:

* `calibrate.sampled_window_means` — the same aperture filter and
  bilinear read the K path uses, once per channel at the committed pose;
* `calibrate.window_scores` — median split, mean-absolute-deviation
  scale;
* `calibrate.fit_window_calibration` — the PAVA score-to-probability
  map on holo3's own site-parity held-out split;
* `calibrate.apply_region_context` — the nine-bin neighbour-count
  detector with its own held-out adoption gate (adopted on every case).

One thing genuinely differs from a K page, and it is a format fact:
**which cells carry labels.** On a K page the 100 word sites per tile
are a BCH codeword under a keystream scramble — about half ones. On the
yellow plane they are all zeros, so the only yellow marks in the
furniture are the 20 dust sites, cycling {1, 2, 4, 5, 6, 7}. This is
the lead's "fill back tile addresses according to dust locations", and
sections 4.2 and 4.3 are what it turned out to be good for — and what
it turned out not to be enough for.

### 3.3 The unchanged codec

A `TileCut` whose Y column carries the calibrated LLRs (C and M columns
zero, the erasure spelling) goes through `tiles.attempt_tile` →
`_sequential_payload` → `tile_codec.cmy8_decode_stream` at 150
belief-propagation iterations. No codec change, no format change: cmy8
is per-plane independent LDPC, so a stand-alone Y decode is bit for bit
the codeword the colour path would decode. Zero-wrong is inherited from
that gate — LDPC syndrome, CRC-32, and the address-bound slot
permutation and dither — and every certificate is *additionally*
checked against the emitted payload.

The union arm is the receiver's own: one owner-frozen cut per capture,
summed by `tiles._combine` exactly as `tiles.prepare_union` sums them.
No new arithmetic.

---

## 4. The measurements

### 4.1 Does the unmixing help? Quantified.

Cell error rate of a hard median threshold on the scalar readout,
measured against the emitted field on cargo cells. `target` = the tiles
under test; `live` = tiles production certified in yellow.

| case | population | C0 raw B | C1 project | A0 subtract | A1 + blind offset |
|---|---|---:|---:|---:|---:|
| H-a | target (dead, tx 18-21) | 0.2343 | 0.1635 | 0.1620 | 0.1469 |
| H-a | live | 0.1712 | — | 0.0836 | — |
| H-b | target (dead, tx 0-3) | 0.2431 | 0.1681 | 0.1680 | 0.1424 |
| H-m2 | target (marginal) | 0.1761 | 0.0893 | 0.0843 | 0.0749 |
| H-m4 | target (marginal) | 0.1849 | 0.1108 | 0.1091 | 0.0954 |
| H-c | target (marginal) | 0.1799 | 0.0971 | 0.0953 | 0.0780 |

Read across: **annihilating C and M is worth 7-9 percentage points of
cell error over the raw blue channel** — it roughly halves it — and it
is the difference between zero certificates and 25. Per-cell
subtraction on top of that is worth a further 0.2-0.5 pp of cell error
but **five times the additive yield** (1 → 5 adds), because it acts
where the projection is weakest.

### 4.2 Registration or spectral separation? Both, and they separate cleanly.

A constant per-crop yellow x-offset, ±2 dots in 0.25-dot steps (the
harness's `--shift-min/--shift-max/--shift-step` grid), on H-a's
`subtract` readout:

| offset (dots) | target band d' | target cell err | live d' | live cell err | Y certs |
|---:|---:|---:|---:|---:|---:|
| −1.00 | 0.756 | 0.3656 | 1.371 | 0.2651 | 0 |
| −0.50 | 1.299 | 0.2593 | 2.168 | 0.1345 | 0 |
| −0.25 | 1.617 | 0.2041 | 2.475 | 0.0979 | 4 |
| **0.00** | 1.917 | 0.1620 | **2.612** | **0.0836** | **6** |
| +0.25 | 2.137 | 0.1361 | 2.537 | 0.0910 | 4 |
| **+0.50** | **2.215** | **0.1283** | 2.267 | 0.1225 | 0 |
| +1.00 | 1.906 | 0.1715 | 1.471 | 0.2479 | 0 |

**The two populations peak at different offsets.** The live columns
peak at 0.00; the dead band peaks at +0.50 dots and is 3.4 pp better
there. One global offset cannot serve both — which is why the sweep's
best-shift row still certifies nothing extra: it trades the live
columns away to buy the dead ones. The offset has to be local, and the
A1 arm makes it so.

That is the same object e033 measured from the certificate residue —
the AltaLink's yellow-plane x-registration sinusoid, 0.83 dot peak,
~100 mm period — seen here directly in the yellow signal, on a
different capture, by a different instrument.

And it can be estimated **blind**. A1 picks each window's offset by the
lowest held-out log loss on that window's own yellow labels, which in a
dead band means the 20 dust sites per tile. Rolled up across the
battery by page-x position (`summarize`):

| page x (mm) | windows | mean blind offset (dots) |
|---|---:|---:|
| 0-20 | 6 | +0.500 |
| 30-40 | 10 | +0.350 |
| 40-80 | 44 | −0.19 |
| 80-90 | 7 | +0.179 |
| 110-120 | 11 | +0.386 |
| 120-140 | 20 | −0.05 |
| 150-160 | 11 | −0.091 |

A wave of roughly ±0.4 dots with a period near 90-100 mm — the
printer's own registration field, recovered with no ground truth
anywhere in the estimator. On H-a the blind estimator reaches cell
error 0.1469 against the oracle's 0.1355 and the nominal 0.1620: it
captures about three quarters of what a perfect offset would buy.

**Verdict on the two levers.** Spectral separation is the bigger one
and it is what makes the arm exist at all (C0 certifies nothing).
Registration is what converts near misses into certificates: worth
0.2-1.4 pp of cell error, but it triples the additive count (5 → 15).
Neither alone rescues a fully dead band.

### 4.3 What a certified neighbour is actually for

A certified neighbouring tile does two different jobs here: it supplies
**regressors** for the mixing fit (and cells the subtraction can
cancel), and it supplies **labels** for the calibration. The harness
ablates them independently. Arm A1, five marginal crops:

| configuration | Y certs | **adds** | H-m1 target d' | H-m1 target cell err |
|---|---:|---:|---:|---:|
| both certified | 42 | **15** | 2.459 | 0.0963 |
| `--siblings furniture` (regressors gone) | 5 | **1** | 2.391 | 0.1060 |
| `--labels furniture` (labels gone) | 0 | **0** | 2.480 | 0.0942 |
| both furniture | 0 | **0** | 2.420 | 0.1031 |

(The "both furniture" row was measured over all eight crops and is zero
on every one of them.)

**The labels are the binding resource, and it is not their class
balance.** Look at the third row: dropping the certified labels leaves
the yellow signal *better* than the full configuration by both
measures — d' 2.480 against 2.459, cell error 0.0942 against 0.0963 —
and certifies nothing at all. The label prior does collapse
(0.106-0.112, against 0.43-0.49 when certified neighbours are in
reach), and the harness has a prior-correction knob built exactly for
that: **it does not rescue it either** (`--siblings furniture --labels
furniture --prior-correction`, eight crops, zero certificates). A PAVA
map fitted on 120 format sites per tile simply cannot price 3,976
payload cells, however it is re-based.

That makes this a **residue arm by construction**: it needs certified
yellow in reach. Which is precisely `tiles.local`'s eligibility shape —
uncertified, covered by evidence, at least one certified tile in the
neighbourhood.

### 4.4 Why the fully dead bands stay dead

H-a's target band sits at 12.8% cell error even at its own best offset.
The rung is r0850 — 3,520 information bits in 4,096, rate 0.859. The
live columns that do certify sit at 8.4%. The dead band is not below
the detector floor — d' 2.2 is a perfectly visible signal — it is
**above the code's floor**. Nothing on the receiver axis fixes that;
sheet H is the most aggressive colour rung ever printed and it has no
margin to spend.

---

## 5. Invocation

Always from the worktree root, always `PYTHONPATH=.`:

```sh
# the battery: five counted arms + the null, over the marginal blocks
PYTHONPATH=. env/bin/python -m measure.yask.harness \
    --case H-m1 --case H-m2 --case H-m3 --case H-m4 \
    --arms A0,A1,C0,C1,N0

# the seven-capture union (minutes per case, not seconds)
PYTHONPATH=. env/bin/python -m measure.yask.harness --case H-d --arms A2

# the two ablations of section 4.3
PYTHONPATH=. env/bin/python -m measure.yask.harness --case H-d \
    --arms A0,A1 --siblings furniture
PYTHONPATH=. env/bin/python -m measure.yask.harness --case H-d \
    --arms A0,A1 --labels furniture

# roll several reports into one table + the registration map
PYTHONPATH=. env/bin/python -m measure.yask.summarize \
    scratch/yask/reports/*.json
```

Exit code 2 on any wrong certificate. Reports land in
`scratch/yask/reports/` (gitignored), named for their cases AND their
arms and ablations so two invocations never overwrite each other.

**Cost and memory.** Nothing is decoded and no sheet is loaded: poses
come from the archived harvest and every pixel read is a window off a
read-only memmap. A single-capture case is ~40 s and ~700 MB resident;
the seven-capture union is ~15 minutes a case, same memory.

### A measured negative, so nobody repeats it

The first version of this harness took the obvious route: cut a crop,
run an ordinary `holo3 decode` on it, harvest the poses. It does not
work on an interior crop of a colour sheet. Case `H-smoke`
(4143×5156 px at 2400 dpi, 64 MB, cut with
`python -m measure.yask._cases --case H-smoke`) surveys into **21
fragments totalling 12,221 support cells** and places nothing, in ~3
minutes at 3 workers — against ONE region of 8,053,285 cells on the
same capture whole.

The pitch is found correctly (7.9996 px/cell, class 1/300). What fails
is `survey._adaptive_threshold`, an Otsu split on the tensor score: on
a whole sheet the two modes it separates are paper and print, and on a
crop cut entirely inside the printed field there is no paper, so Otsu
splits *within* the print and the support mask shatters.

Two ways out, and this harness took the second: cut crops that include
real page margin, or skip the decode and bring the poses. Bringing the
poses is also the better evidence — they are production's own, not a
crop's re-derivation of them.

---

## 6. Open questions, and what a production arm would need

### What this experiment did NOT establish

* **One sheet, one print, one engine.** Sheet H is a single AltaLink
  print from 2026-08-18. Nothing here is a population claim, a ladder
  move, or a rate promotion.
* **The crops are chosen, not sampled.** The four marginal blocks were
  chosen by a rule fixed before they ran, but the rule aims at the
  regime where the arm converts. The adds are counted out of the
  Y-uncertified tiles *in crops selected for being near the boundary* —
  not a sheet-wide rate.
* **No close.** These are certificates, not a recovered volume. Sheet H
  needs 5,277 symbols and the production harvest has 4,237; whether
  this arm's yield over the whole sheet closes it is unmeasured, and
  the fully dead columns say it probably does not.
* **Sibling values are the production run's, taken from the emitted
  payload** on the assumption that a certified address's bits are the
  emitted ones. The codec gate makes that overwhelmingly likely and
  section 4.3 shows the regressors are worth only about an eighth of
  the yield, but it is an assumption, not a measurement.
* **The union can lose a tile.** On H-m1 the seven-capture union gained
  three certificates over one capture and lost the one add. Equal-weight
  LLR summation across captures of very different resolution is the
  receiver's own rule, and it is not obviously the right one here.

### What a production residue arm would need

1. **A blind registration field, not a per-window scalar.** The A1
   estimator already recovers the printer's sinusoid from dust sites
   alone. That is the same object `PLANE-FIELDS` fits from certified
   ground truth and word/dust anchors — and this measurement says the
   dust sites carry enough on their own, in a band with **no** yellow
   certificates. That is the part most worth carrying over, and it
   belongs in that line, not in a new one.
2. **A per-plane spectral head.** The production colour lane fits an
   8-state QDA over (R, G, B) on furniture plus tiles certified in
   **all three** streams. In a failing band no tile is certified in all
   three, so a tile with C and M certified contributes **nothing** to
   the head today — `build_window_rows` requires `known.all(axis=1)`.
   Those cells are exactly the ones this arm's unmixing fit lives on.
   Letting two-of-three-known cells into the colour head, as regressors
   rather than as states, is the smallest production change this
   experiment suggests.
3. **A residue schedule, not a default.** Everything here acts on tiles
   the ordinary path failed, is gated by the same codec, and can only
   add — the toolbox doctrine's shape exactly. Priced above the payload
   band, armed on uncertified tiles with a certified yellow neighbour
   in reach (section 4.3 says that eligibility is not optional), and
   never run by default.
4. **A rate answer for the dead bands.** Section 4.4 is not a receiver
   problem. If sheet H's dead columns matter, they need a lower rung or
   a per-plane rate, not a better detector.

### Questions for the lead

* Should the blind dust-anchored offset estimator move into the
  `PLANE-FIELDS` line as a second evidence source, rather than becoming
  its own arm? It is the piece with the clearest carry-over.
* Sheet I (`r0700`, the volume that DID close) has the same dead-band
  structure at a gentler rate. Running this battery there would say
  whether the arm converts where the code has margin — this battery
  cannot answer that, because sheet H has none.
* Is the union rule worth a look? H-m1 says equal-weight summation over
  1200/2400/4800 dpi lanes is not always monotone.
