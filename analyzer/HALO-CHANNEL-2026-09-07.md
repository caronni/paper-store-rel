# The halo × channel matrix, and the walk that reads it (2026-09-07)

Six blind passes over one target list settle what `cddcb87` left open, and
two ledgers say WHY the self-discovery walk changes its mind when the halo
moves.  The finding is not about the halo and not about the channel set:
**the walk's data budget is a profile constant while its model size is
chosen per population, and its objective is scored on a population that is
four times easier than the cargo it will price.**  Both defects are
measured below, in the walk's own ledgers, at one code state.

Single sheet, single stream, one print day, one generation, one target
list.  **This pins nothing and promotes nothing** (CLAUDE.md's rule;
APPROACHES §4.0 ruling 1).  What it does is rule where the next build
goes, and record plainly that `cddcb87` stands.

Record of the runs: `APPROACHES-2026-09-06.md` §6.9 (the H48 offline
isolation `cddcb87` was made on), §6.11 (the R-row wave) and §6.12 (this
matrix, the walk isolation and the ridge repair); `W8-2026-09-06.md`
§3.2, §5.  Artefacts: `scratch/analyzer/W8-halo/` (the three halo-48
cells, `FIXED-auto`, `matrix.txt`, `run-halo.sh`, `logs/`),
`scratch/analyzer/W8-owed/` (the three halo-16 cells),
`scratch/analyzer/W8-walk/` (N0–N4 and the two anchors) and
`scratch/analyzer/W8-ridge/` (the ridge repair).

**Read §5.5 before §5.**  It carries the first run of the configuration
that actually ships, the independent review of this build, and the
BLOCKER that review found: W4's chosen regulariser was published in
every ledger and never reached the filter that was fitted.  Three
sentences in §3(a), §5.2 and §5.4 are corrected in place from it.

## 1. What was measured

153 open C tile-streams of `scratch/holo3-H-with-facts-7-run.32018`
(`scratch/analyzer/W8/C-open.list`; denominators **98 dead / 23 marginal /
32 live**), `--profile patch`, one generation, `--workers 14`, no
`--fixed-point`.  Every certificate scored offline against
`scratch/analyzer/H14-pass1/payload.bin`.

**One code state, verified.**  `git diff --name-only cddcb87..HEAD --
'*.py'` is EMPTY: the three commits since `cddcb87` touch three `.md`
files and no Python anywhere.  The three halo-16 cells were therefore NOT
re-run — their ledgers are at HEAD's analyzer code byte for byte — and
the three halo-48 cells ran at `5f7026b`.

| halo (C) | `patch_channels=r` | `patch_channels=auto` (the profile) | `patch_channels=rgb` |
|---|---|---|---|
| **16** — the profile default since `cddcb87` | **109** (64d / 18m / 27l)<br>3,178 CPU s | **115** (68d / 19m / 28l)<br>4,849 CPU s | **128** (77d / 22m / 29l)<br>8,217 CPU s |
| **48** — `--halo-cells 48` | **104** (53d / 22m / 29l)<br>13,678 CPU s | **127** (73d / 23m / 31l)<br>24,628 CPU s | **127** (74d / 23m / 30l)<br>35,272 CPU s |

**710 certificates checked across the six, 0 wrong, 0 false accepts**,
every close `verified: true` at payload sha `0ad329fb…` = the emission's.
*(Corrected 2026-09-07 from 971, which was §6.11's eight R-rows (613)
plus the three halo-48 cells (358) — a real total over eleven passes,
but not "the six".  The six cells' own checked counts are
109+115+128+104+127+127.  Zero wrong and zero false hold either way,
and every later count in this document that read 971 is corrected with
it.)*
Peak RSS 32.5 / 37.4 / 39.6 GiB at halo 16 against 37.5 / 46.9 / 47.1 at
halo 48 — the wide halo's two expensive cells sit barely above the
machine gate's own 45 GB floor, so this matrix cannot be run two at a
time on this machine.

**Set relations.**  Exactly two of the fifteen pairs are containments —
H16-red ⊂ H16-rgb (+19: 13d/4m/2l) and H48-red ⊂ H48-auto (+23) — and the
other thirteen are crossings.  Down a channel column with the halo as the
only knob: red 109 → 104 (loses 19, gains 14), auto 115 → 127 (loses 3,
gains 15), rgb 128 → 127 (loses 7, gains 6).  H48-rgb and H48-auto both
mint 127 and differ by **4 certificates EACH WAY** — an equal count is
not the same set, and no note may say "auto reaches rgb at halo 48".
Six-way: **intersection 89, union 135 of 153**; 46 certificates depend on
which cell you ran and **no single configuration reaches the union**.

Three readings the artefacts do NOT support, recorded so nobody makes
them: H48-auto's certified set is bit-identical to X1's 127 (same
73/23/31 split, zero keys either way) but X1 ran pre-`cddcb87` and
APPROACHES §6.11 forbids reading an R-row against an X-row — a
coincidence worth knowing, not a measurement, and nothing here rests on
it.  The six `score.md` files are offline and light (no `--run-dir`, no
`--gt-dir`), so their cell-error and by-state tables are EMPTY by
construction: **this matrix carries no offline cell-error column**, and
the channel axis's cell error at halo 48 is a separate `score --run-dir
--gt-dir --halo-cells 48` pass that has not been run.  And `--halo-cells
48` sets ALL THREE planes (`cli.py`), so the new headers say
`{'C':48,'M':48,'Y':48}` where X1's `wide-halo` profile said
`{'C':48,'M':48,'Y':32}` — inert on this list (every target is a C
stream and the C entry is 48 either way — `fixedpoint._halo_for` looks the
halo up per stream) but not inert for a Y-plane or mixed re-run, and §5
repairs it.

## 2. The mechanism, from the two `auto` ledgers

Everything in this section is computed over the **3,538 (row, lane)
patch evidence blocks in each `auto` ledger** — the same population and
the same block count in both, one definition throughout
(`scratch/analyzer/W8-owed/R3-auto/ledger.jsonl` and
`scratch/analyzer/W8-halo/H48-auto/ledger.jsonl`).

### 2.1 The data budget, and why no floor survives it

`n_labels` and `n_fit_rows` do not depend on the channel knob, so a halo
row's three cells share them; only the feature count and the ratio move.

| | halo 16 | halo 48 | ratio |
|---|---|---|---|
| `n_labels` median (mean; min–max) | 1,770 (2,072; 130–5,241) | 8,195 (9,130; 343–21,625) | **4.63×** |
| `n_labels_search` median (the fold the walk scores on) | 451 | 2,073 | 4.60× |
| per-state `n_fit_rows` median, s0/s1/s2/s3 | 196 / 194 / 198 / 197 | 942 / 942 / 955 / 958 | **4.8×** |
| labels per feature, red (144), mean over blocks | 2.31 / 2.27 / 2.33 / 2.33 | 10.70 / 10.70 / 10.82 / 10.83 | 4.6× |
| labels per feature, rgb (432), mean over blocks | **0.77 / 0.76 / 0.78 / 0.78** | **3.57 / 3.57 / 3.61 / 3.61** | 4.6× |
| labels per feature at the geometry the walk actually CHOSE, median (state3) | 1.37 | 3.14 | — |

(The task that commissioned this record quoted per-state fit labels
1,045/1,008/896/914 and 249/217/153/174 and ratios 2.1–2.4 / 0.35–0.58.
The FIELD is right — `n_fit_rows` inside each `patch_states/<state>`
block — but those are one exemplar block's values, and not from the block
the quoted `n_labels` came from.  The pooled numbers above are the ones
that reproduce; the direction and the crossing of 1.0 at halo 16 stand,
the exact ratios do not.)

**RGB at halo 16 is fitted at 0.76–0.78 labels per parameter — fewer
labels than features, in every sibling state — and it is the best cell in
the matrix (128).**  That single fact refutes the whole family of
"hold labels-per-feature above a target" repairs: any floor at or above
0.78 forbids the configuration that won, and any floor below it is
unmeasured, i.e. a pin.  The matrix bounds the useful range downward at
0.77 and supports no floor at all.

### 2.2 The franchise — a fifth of the three-ink populations never voted

New here, and the largest single mechanism.  `patch._choose_axes` refuses
the walk when the population's own SEARCH-fold labels are below
`calibrate.SELECT_MIN_MINORITY` (40 minority labels) and returns **the
INHERITED axes** — `patchspec`'s module constants, i.e. B1's guess, i.e.
red.  `_record_auto` then writes those inherited values into
`auto_choices` beside a reason in `auto_refused`, so a pooled count over
`auto_choices` reads an inheritance as a choice.

| | halo 16 | halo 48 |
|---|---|---|
| state3 populations | 3,186 | 3,334 |
| walk REFUSED (`below_minority_floor`) → inherited red | **674 (21 %)** | **2 (0.06 %)** |
| of the walks that ran: red / rgb | 2,047 / 465 (**19 % rgb**) | 1,244 / 2,088 (**63 % rgb**) |
| agnostic tier: refused | 126 of 3,196 | 2 of 3,192 |
| agnostic, of walks that ran: red / rgb | 1,924 / 1,146 | 339 / 2,851 |

The decomposition reproduces the published pooled figures exactly:
2,047 + 674 = 2,721 = APPROACHES §6.11's "red 2,721 (85 %)" on state3,
and 1,924 + 126 = 2,050 = its agnostic "red 2,050 (64 %)".  **So the
record's "the search picks red 85 % of the time on the three-ink state"
is corrected here: on 21 % of those populations the search picked
nothing.**  At halo 16 the run is not discovering its own truth on a
fifth of the population this whole line exists for — it is inheriting a
pin, which is the exact thing the SELF-DISCOVERY ruling was written
against.

### 2.3 The bar moves with the halo; the walk's own objective does not

Reconstructing each block's running baseline at the moment the channel
axis was walked (the inherited loss, or the loss of the samples/window
value the walk had already adopted) and comparing it with the `rgb`
candidate's own recorded loss:

| population | halo | rgb measured BETTER | median (base − rgb), nats | rgb better **and refused** | rgb adopted |
|---|---|---|---|---|---|
| state3 | 16 | 60 % of walked blocks | **+0.0091** | 1,033 (41 % of walked) | 465 (19 %) |
| state3 | 48 | 86 % | **+0.0281** | 772 (23 %) | 2,088 (63 %) |
| agnostic | 16 | 80 % | +0.0109 | 1,305 | 1,146 (37 %) |
| agnostic | 48 | 98 % | +0.0153 | 283 | 2,851 (89 %) |
| state0 | 16 | 49 % | −0.0007 | 875 | 277 (12 %) |
| state0 | 48 | 73 % | +0.0115 | 1,168 | 1,281 (38 %) |

The adoption rule is `autoknobs.paired_verdict`: adopt when the paired
mean gain clears `calibrate.SELECT_SE_MULTIPLE` = 2 standard errors of
the per-label difference.  **That bar is a function of the label count**
— SE ∝ n^(−1/2), and the walk's own fold carries 4.6× more labels at
halo 48, i.e. a bar 2.15× lower for the same effect.  The table is what
that predicts: on the three-ink state the walk's objective points the
same way at both halos (median gain positive at both), and only its
ability to clear its own bar moves.  At halo 16 it measures rgb better
and refuses it on **1,033 of 2,512** walked state3 populations.

So, stated exactly: **at HEAD the halo's certificate value is not a
data-budget effect on the filter — it is an effect on the CRITERION and
on the franchise.**  The configuration that runs is the only column the
halo helps, and it helps it by letting a wrong-population objective
clear its own bar often enough to accidentally choose the right model.

### 2.4 The objective's population is four times easier than the cargo

The walk scores held-out log loss on the halo's search-fold labels.  Those
labels are the furniture of the tiles the footprint touches and the
projected cargo of the neighbours **that certified** — a sample selected
on exactly the quantity being measured.  Their difficulty, from the same
ledgers (`patch_states/<state>/admission/error_crossfit`, the population's
own out-of-fold error):

| | state0 | state1 | state2 | **state3 (three-ink)** |
|---|---|---|---|---|
| halo 16, median cross-fit error | 0.0296 | 0.0263 | 0.0216 | **0.0356** (p90 0.0833) |
| halo 48, median cross-fit error | 0.0213 | 0.0187 | 0.0162 | **0.0202** (p90 0.0471) |

Against them, the population the arm exists for: the dead band's
three-ink C cells, measured offline at **0.152–0.171** (W8 §3.1's S-rows,
§6.9's H48 score).  **The walk optimises a population 4.3–4.8× easier
than the cargo it will price**, and on cells read at 3 % two candidate
filters that differ by 4.4 points of cell error on the cargo differ by
0.009 nats there — inside its own noise.  The offline row says the same
thing from the other side: rgb takes the three-ink cells 0.171 → 0.127
(R +0.10), and rgb is worth +19 certificates, while the walk's own
objective can only see +0.009 nats.

This is not a new defect.  It is the SAME defect the pure path had, ruled
on 2026-09-06 (APPROACHES §4.0 ruling 15, DESIGN §14.5, fixed in
`583b482`): "the halo's error, ~3 %, on cells that measure ~15 % — a
certified neighbour's cells are EASIER than the tile's cargo, so the
halo's number is a floor, not an estimate."  The ruling then was to price
from the TILE's own populations.  The walk was never given the same
treatment, and §3 gives it.

### 2.5 A third, smaller thing the ledgers say

`autoknobs.AXIS_ORDER` is a single coordinate pass, geometry → channels →
features → shrinkage, so **the channel axis is always judged at the
inherited regulariser** and the ridge is chosen afterwards, for the
channel set already fixed.  The walk then moves the shrinkage off 1e-2 on
12–18 % of populations, and it moves it UP (1e-1) more often for
populations that chose rgb than for those that chose red — at halo 48,
20 % against 7 % on state3 (at halo 16, 14 % against 11 %).  Weak, but
one-directional and free to fix: the richer model asks for more ridge and
is only allowed to ask after it has already lost the vote.

## 3. The ruling

### (a) The data budget is NOT chosen by moving the halo

**The halo does not become an auto axis, and no labels-per-feature target
is adopted.**  Three measured reasons and one structural one:

1. **At a fixed model the wide halo is neutral-to-harmful and costs
   4.3×**: red 109 → 104, rgb 128 → 127, at 4.30× and 4.29× the CPU and
   +7–8 GiB of peak RSS.  This is the certificate-level version of
   §6.9's offline isolation (dead-band M+Y 0.1518 → 0.1640, worse on 5 of
   7 lanes past 2 SE).
2. **Growing the halo to afford a model is exactly the move the matrix
   refutes.**  A rule that widened the halo whenever labels-per-feature
   fell below any target ≥ 0.78 would take H16-rgb (128, 8,217 CPU s) to
   H48-rgb (127, 35,272 CPU s): −1 certificate for 4.3× the machine.
3. **No floor is supported.**  The best cell in the matrix runs at
   0.77 labels per parameter.  Every floor the matrix can reach is
   refuted; anything below is a pin, which §4.0 forbids.
4. **Structurally, the halo is not walkable by this machinery at all.**
   Every other auto axis is compared PAIRED over one fixed row set
   (`patch.py` cuts the row set at the walk's widest geometry for exactly
   this reason).  The halo DEFINES the row set: two halo candidates do
   not have a common evaluation population, so a paired verdict between
   them is not available.  The nearest legitimate test — fit at each
   candidate halo, evaluate both on the SMALLEST candidate's search-fold
   rows — is well defined, and is recorded in §5 for whoever reopens the
   question with a second sheet; it costs the WIDE halo's price by
   construction (the crops must be opened at the widest candidate), which
   is the 4.3× the matrix says buys nothing.

**But the model IS fitted to the budget — through the regulariser, which
is the only knob that can absorb p > n without dragging the population
with it.**  *(This sentence was false in the code until `3a661fe`: the
walk chose the ridge and `patch._population` fitted at the spec's
inherited constant, so the model was compared at its own ridge and
DEPLOYED at another's.  Found by review, fixed and re-measured the same
day — §5.5.  The ruling stands as written; what changed is that the
code now does it.)*  Ruled: the shrinkage axis stops being the last stop of a
coordinate pass and becomes an INNER minimisation nested under every
other candidate's evaluation, so no candidate is ever judged at another
candidate's ridge (§4, W4).  It is nearly free: the normal equations are
already cached per (population, cross-fit half) at the widest geometry
(`patchcache.FeatureBank.selection_moments`), a shrinkage change is a
diagonal add and a solve, and the `gemm` is shared.  `labels_per_feature`
stays a published DIAGNOSTIC and acquires exactly one mechanical duty:
when it is below 1.0 at the candidate's own geometry the shrinkage
candidate ladder extends upward by one rung, because that is the regime
where the ridge is doing the work of the missing rows.  No target, no
veto: the run still chooses.

### (b) The criterion changes, in three named ways

All three run on the **SEARCH fold**, where DESIGN §4.8 puts every
within-arm search and where the walk already lives.  The select fold
stays untouched — `select_arm`, `platt`, `platt-state` and `best` keep
arbitrating on labels nothing here minimises.

**W1 — the walk's held-out loss is weighted to the TARGET TILE'S OWN
CARGO.**  Per (tile, lane, plane) the run builds a blind profile of the
cells it is actually going to price — the target tile's own observed
cargo cells — over two covariates: the sibling state
(`statecal.sibling_state`, a fact of the two SIBLING planes) and a
difficulty bin from the incumbent box-mean score
(`patchfit.fallback_population`'s own standardised `subtract` score, the
same function called, not copied; small |score| = near the decision
midpoint = hard, which is precisely what the third layer does to a C cell
— MEASUREMENTS-2026-09-06-C-THIRD-LAYER §3).  Each of the walk's
search-fold labels is then importance-weighted so the halo's histogram
over those bins matches the cargo's, and `paired_verdict` takes weighted
means and a weighted (Kish) standard error.  For a per-state walk the
state covariate is already exact and the difficulty bins do the work; for
the state-agnostic tier — which pools states, and which flips hardest
with the halo (36 % → 89 %) — both covariates do.
*The tile-wide APERTURE walk is not weighted, by construction* (amended
2026-09-07 after the build; this sentence used to name it beside the
agnostic tier).  The aperture walk runs at step 0, BEFORE the fallback
of step 1, and it MOVES the values the fallback is computed from — so
the difficulty covariate the profile is built on does not exist yet when
it votes, and a profile for it would have to be built at a pre-aperture
read.  §4.3 already builds the profile after step 1 for exactly that
reason and the code says so at `patch.py`'s step 0; this paragraph now
says so too, and §6's "the two that flip hardest with the halo" is
therefore about the agnostic tier alone.
*Why it is blind*: the cargo cells of the target tile carry NO
target-plane bit by construction (DESIGN §4.5's run-abort assertion:
`known[in_tile & cargo, target_plane].sum() == 0`), so the profile
consumes no fold and no label — it is a histogram of an unlabelled
population's covariates.  The sibling state comes from the sibling
planes' certified bits, never the target's own, exactly as the per-state
tiers already do.  The weights multiply the losses of halo labels; they
restrict no hypothesis and enter no certificate.
*Why this and not a label-free cargo objective*: the label-free route was
tried by the pure path and measured failing by 5× on paper (§6.9's
P0-fixed).  Reweighting a labelled population toward the target's blind
covariates keeps real labels under the loss.

**W2 — a population that cannot afford its own vote inherits a
DISCOVERY, not a pin.**  When `minority_ok` refuses a per-state walk, the
run takes the axes of the POOLED walk over the same (tile, lane, plane)'s
labelled search-fold rows — which under W1 is already weighted to the
cargo's own state histogram — and only when the pooled walk itself
refuses does the module constant apply.  The pooled walk already exists:
it is the state-agnostic tier's walk, which runs on 96 % of blocks at
halo 16; it moves earlier in `patch_score` and is memoised so the tier
reuses it instead of walking twice.  The ledger says which of the three
happened (`auto_source` ∈ `own` / `pooled` / `inherited`).
*Argument*: 674 of 3,186 state3 populations at halo 16 (21 %) currently
take the pin, against 2 of 3,334 at halo 48 — the halo's whole `auto`
advantage is franchise, and the franchise can be restored without a
pixel more.

**W3 — on the CHANNEL axis the nesting decides the burden of proof.**
`red ⊂ rgb` literally: the same 144 columns plus 288 more.  Today the
inherited (leaner) candidate keeps every tie and every undecidable
comparison, so the bar's operating point — which §2.3 shows is a function
of the label count — is applied against the richer model only.  Ruled:
for the channel axis the paired test runs in the direction
`autoknobs.admit`'s third clause already uses — **the richer candidate is
adopted unless the leaner one wins by `SELECT_SE_MULTIPLE` standard
errors** on the same paired, W1-weighted losses.
*Argument, from this matrix and nothing else*: the loss is one-sided.
Under-richness costs 13–19 certificates (auto 115, red 109, against rgb
128); over-richness costs 0 on this list (red ⊂ rgb strictly at halo 16;
at halo 48 rgb gains 25 and loses 2); and **710 certificates were checked
across the six cells with 0 wrong and 0 false accepts** (1,807 over the
whole wave), so the axis is
pure yield — a richer filter cannot mint a wrong certificate, the gate
decides that.  Cost is explicitly not a constraint (§4.0).
*Scope, deliberately narrow*: **the channel axis only.**  The matrix
isolated exactly one axis.  Window and samples keep ties-to-inherited,
because ties-go-richer on every axis would run the walk to 2.0 cells × 16
samples × rgb = 3,072 features on ~200 labels — a configuration nothing
in this record has measured — while the 128 that argues for this change
was measured at the inherited geometry with the lean tie-break on those
axes.  Whether the same asymmetry holds for window and samples is OPEN
(§5) and needs its own matrix.
*This is not a pin*: it changes a RULE, not a value.  `patch_channels`
stays `"auto"`; on a sheet where the extra channels are noise the paired
test will show harm and the lean model wins.  What is removed is an
arbitrary asymmetry that was itself an unmeasured pin — "the module
constant keeps every tie".

### (c) The patch profiles' halo default

**Stays `{'C': 16, 'M': 16, 'Y': 32}`** — `arms.HALO_CELLS`, production's
own halo, `types._PATCH_HALO` as `cddcb87` set it.  The halo is not
chosen by the run (a), so it remains an operator axis with production's
value as its default; `--halo-cells` stays the escape hatch and
`wide-halo` keeps 48/48/32 for continuity with X1.  Supporting numbers
beyond §3(a): at halo 16 the ceiling measured on this list (128) is above
anything halo 48 reaches (127), at 23 % of the CPU and 7–8 GiB less peak
RSS — which matters, because 46.9–47.1 GiB is at the machine gate's own
floor.

### (d) `cddcb87` STANDS

The matrix decides it, and the record says so plainly.  For a fixed
channel set the wide halo loses at certificate level in both columns
(109 → 104, 128 → 127) exactly as §6.9's offline isolation said it would,
at 4.3× the CPU.  The one column where 48 wins is `auto`, by 12, and
§2.2–§2.3 show that win is franchise and bar, not filter quality: the
walk votes on 100 % of populations at 48 and 79 % at 16, its objective
has the same sign at both, and 41 % of the walked three-ink populations
at halo 16 measure rgb better and refuse it.  Once (b) lands, the 48
column has nothing left to buy on this evidence.

The REASON is narrower than the change: `cddcb87` was made on an offline
cell-error isolation run with the red channel set only, and the
certificate evidence for the configuration that actually runs
contradicted it — that contradiction is now explained, and it was never
about the halo.  **Pre-registered reversal condition**: if the fixed walk
at halo 16 (§4's N4) lands materially below 127 on these 153 rows, then
the halo's franchise effect is NOT fully explained by W1–W3, 48 buys
something real, and the default reopens with the halo as a candidate — to
be recorded here either way.  **MEASURED 2026-09-07: N4 = 127.  The
condition does not trigger and `cddcb87` stands — §5.4.**

## 4. The build spec

Constraints: ≤ 1,000 lines per file (`wc -l` before committing; new
mechanism goes in a new module if a file would cross), pyflakes clean,
the lane green (`env314t/bin/python -m pytest analyzer/tests -q -n 8`;
691 passed / 69 skipped at `5f7026b`), blindness test-enforced (nothing
reachable from a run command imports `analyzer.truth`/`oracle`/`score`),
every draw a hash of an explicit seed, no RNG.

### 4.1 New module — `analyzer/walkeval.py` (~300 lines)

Sizes at HEAD: `patch.py` 848, `autoknobs.py` 742, `cli.py` 970,
`types.py` 998.  The mechanism goes in a new module; `patch.py` and
`autoknobs.py` take dispatch lines only (target: `patch.py` ≤ 900).
`walkeval` may import numpy, `holo.receiver.*`, `calibrate`, `patchfit`,
`patchcache`, `statecal`, `types`; it must NOT import `patch`,
`autoknobs`, `arms` or `unmix` (cycles), nor `truth`/`oracle`/`score`
(the closure test picks the new module up automatically).

```python
@dataclass(frozen=True)
class CargoProfile:
    """The blind covariate histogram of the cells a filter will price."""
    bins_by_state: Mapping[int, np.ndarray]   # cargo share per bin, per state
    edges: np.ndarray                          # difficulty bin edges (|z|)
    n_cargo_by_state: Mapping[int, int]
    n_bins: int
    centre: float                              # fallback midpoint used
    scale: float

def cargo_profile(fallback: np.ndarray, *, observed: np.ndarray,
                  in_tile: np.ndarray, cargo: np.ndarray,
                  state: np.ndarray, known_target_fit: np.ndarray,
                  values: np.ndarray, min_per_class: int,
                  n_walk_labels: int) -> CargoProfile
```
* the difficulty statistic is `abs(z)` where `z` is
  `patchfit.fallback_population(fallback, rows_observed, known_target &
  folds.fit, values, spec.min_per_class)[0]` — the incumbent box-mean
  score centred at its own fit-fold class midpoint and scaled by its
  fit-fold sd.  One call over ALL observed rows, so halo and cargo sit on
  one footing.  Its `centre`/`scale` and the `centred_on` reason are
  published.
* `n_bins = min(4, max(1, n_walk_labels // 25))` — DERIVED, not pinned:
  the median block's search fold at halo 16 carries 451 labels over the
  four states (~110 each) and `SELECT_MIN_MINORITY` is 40, so a bin below
  ~25 labels cannot carry a paired difference.  Edges are quantiles of `abs(z)` over the target's
  own observed cargo cells of that state (all of them — no labels).

```python
def cargo_weights(profile: CargoProfile, *, state_of_row: np.ndarray,
                  z_of_row: np.ndarray, pooled: bool
                  ) -> tuple[np.ndarray, dict]
```
* `w_i ∝ cargo_share(bin_i[, state_i]) / halo_share(bin_i[, state_i])`,
  mean-normalised.  `pooled=True` (the agnostic walk — the aperture walk
  is unweighted, §3(b)) also matches the STATE histogram; a per-state walk matches bins only.
* **Variance budget, argued not picked**: the weights are clipped at the
  smallest `c ≥ 1` on a bisection that keeps the Kish effective sample
  size `ESS = (Σw)² / Σw²` at or above `n/2`.  The bar the correction has
  to live inside is 2 SE ∝ n^(−1/2); halving the effective count costs
  √2 in that bar, which is less than the 2.15 the halo change moves it
  (§2.3), so the correction may not spend more than the effect it is
  correcting.  `ESS`, the clip and `unmatched_cargo_fraction` (cargo mass
  in bins with no halo label) are recorded; above 0.5 unmatched the
  weighting REFUSES with a reason and the walk runs unweighted — a
  refusal, never a fabricated number.

```python
def paired_verdict(base, candidate, *, weights=None,
                   direction="adopt_if_better") -> dict
```
* `autoknobs.paired_verdict`'s arithmetic with weights: weighted mean of
  `base − candidate`, weighted SE, the `SELECT_SE_MULTIPLE` bar,
  `pava.CAL_MIN_HELDOUT` floor on the raw count.  `direction`
  `"keep_unless_worse"` returns `adopted=True` unless the LEANER side
  clears the bar.  Returns `mean_difference`, `standard_error`, `ess`,
  `n`, `adopted`, `reason`.  `autoknobs.paired_verdict` becomes a
  thin call into it with `weights=None`, `direction="adopt_if_better"`
  — byte-identical behaviour, pinned by a test.

### 4.2 `analyzer/autoknobs.py` (dispatch)

* `choose(...)` takes `weights: np.ndarray | None`, `verdict:
  Callable[..., dict]` (defaulting to today's) and
  `nested: Mapping[str, tuple]` naming the axes whose candidates are
  ordered by richness (`{"channels": ((0,), (0, 1, 2))}` only).  For a
  nested axis the comparison runs `direction="keep_unless_worse"` from
  the leanest incumbent upward.  With `weights=None` and `nested={}` the
  function is byte-identical to today's.
* `SHRINKAGE_CANDIDATES` gains one upward rung used ONLY when the
  candidate's own `n_fit_rows / n_features < 1.0`
  (`SHRINKAGE_UNDERDETERMINED_RUNG = 1.0`).
* `AXIS_ORDER` loses `"shrinkage"`; shrinkage becomes an inner
  minimisation inside every axis's `evaluate` (W4): each candidate is
  scored at `argmin` over its own shrinkage ladder, so no candidate is
  judged at another's ridge.  The extra cost is one `solve` and one
  `apply` per (candidate, shrinkage) — the `gemm` is shared through
  `selection_moments`.  The optimism this introduces is equal in count
  across candidates, stays on the search fold, and is stated in the
  module docstring.

### 4.3 `analyzer/patch.py` (dispatch)

* build the `CargoProfile` once per `patch_score` call, after step 1's
  fallback and before step 5;
* hoist the pooled (agnostic) walk to a lazily-memoised
  `_pooled_axes()`; `_choose_axes` returns
  `(axes, losses, detail, source)` with `source` in
  `own`/`pooled`/`inherited`; a `minority_ok` refusal takes
  `_pooled_axes()` instead of `inherited_axes`;
* `_record_auto` publishes what it currently drops: `auto_source`,
  `n_walk_labels`, `walk_ess`, `walk_bins`, `walk_unmatched`, the walk's
  `adopted` map and `baseline_logloss`, and a NEW sibling field
  `auto_verdicts[tag][label] = {mean_difference, standard_error, ess, n,
  adopted}`.  `auto_losses` keeps its `{label: float}` shape — three
  tests read it as floats, and `calibrate.py:917` reads
  `auto_choices` truthiness for `searched_knobs`, which must stay true
  for a pooled walk as well;
* `patch_states/<state>/labels_per_feature` is published at the CHOSEN
  geometry as well as the inherited one
  (`labels_per_feature_chosen = n_fit_rows / n_features`).  Today the
  field divides by the INHERITED width (144) while the population may
  have been fitted at 256 or 432 — the whole budget argument is read off
  this number and it must name its denominator.

### 4.4 Knobs — three, all operator-only

| knob | values | shipped as built | after §4.6's gate (§5.3) |
|---|---|---|---|
| `walk_weighting` | `none` \| `cargo` | `none` | `none` — REFUSED on its own isolation (−3) |
| `walk_franchise` | `inherit` \| `pooled` | `inherit` | **`pooled`** — passed (+4) |
| `walk_direction` | `adopt-if-better` \| `nested-richer` | `adopt-if-better` | **`nested-richer`** — passed (+6) |

None of the three is `"auto"`-able: they name HOW the run decides, not
what is measured, and a rule cannot be chosen by the rule it defines —
the same carve-out `autoknobs`' docstring already makes for the unmix
mode, the register arm and the train scope.  W4 (nested shrinkage) is not
a knob: it is a strict improvement in the same objective and lands
unconditionally, with a test that a run whose shrinkage is NAMED is
unaffected.

### 4.5 Two repairs the run set earned

* `--halo-cells` takes a per-plane spelling: `--halo-cells 48` keeps
  today's meaning (all three planes) and `--halo-cells C=48,M=48,Y=32`
  names them.  Parser `frame.parse_halo_cells` — `frame.py` is 408 lines
  and already owns `tile_footprint`'s halo; `types.py` (998) cannot
  import it and keeps its literal.  Without this a Y-plane or mixed-stream
  re-run of this matrix is not comparable to X1's `wide-halo`.
* provenance: the header's `knobs_from` must not read `profile:patch+cli`
  when the only CLI word was `--halo-cells` (H48-auto's header says
  exactly that, and a reader diffing that field alone would call it a
  knob-pinned run).  Add `halo_from` beside it and keep `knobs_from` for
  knobs.

### 4.6 The isolation, pre-registered

Same base, same `C-open.list`, `--profile patch`, one generation,
`--workers 14`, halo 16, one run at a time behind the machine gate
(≤ 1 other heavy analyzer/receiver process, ≥ 45 GB free+inactive),
`/usr/bin/time -l` kept, `git rev-parse HEAD` recorded at each launch,
each scored offline against `H14-pass1/payload.bin`:

| run | knobs |
|---|---|
| N0 | none — the NULL PROOF |
| N1 | `--knob walk_weighting=cargo` |
| N2 | `--knob walk_franchise=pooled` |
| N3 | `--knob walk_direction=nested-richer` |
| N4 | all three |

**Gate — regression meaning only** (W8 ruling 3: no gate is a tuning
target):
1. zero wrong and zero false accepts under the offline scorer in every
   run (the standing gate);
2. **N0 reproduces R3-auto's 115 exactly, key for key** — with every knob
   off the code path must be byte-identical, which is also what lets
   H16-red's 109 and H16-rgb's 128 stand as anchors without re-running
   them;
3. N4's certified set ⊇ N0's — no certificate lost.

Reported, not gated: where N1–N4 land between 115 and 128, the per-state
choice histogram, the refusal counts (which W2 should collapse toward
zero), `ESS`, and CPU.  A mechanism whose isolation regresses is refused
and recorded as a measured negative; the default flip applies only to the
mechanisms that pass, and it changes RULES, never a knob value.

### 4.7 Tests (all fast; the lane must stay green and under its wall)

* **null proof**: with the three knobs off and shrinkage NAMED,
  `patch_score`'s detail and score are `np.array_equal` to a recorded
  fixture of the pre-change path; `autoknobs.paired_verdict` unchanged.
* **blindness**: the new module is a root of
  `test_analyzer_fixedpoint.py::test_no_module_reachable_from_a_run_command_imports_truth_or_oracle`;
  a test asserts `walkeval` imports neither `patch` nor `arms`; a test
  asserts the cargo profile reads NO target-plane label (feed a frame
  whose in-tile cargo bits are all unknown — the §4.5 assertion's own
  condition — and check the profile is unchanged when those bits are
  flipped in a copy).
* **covariate recovery** (synthetic): a halo drawn 80/20 easy/hard and a
  cargo drawn 20/80; the weighted mean of a planted per-label loss equals
  the cargo-weighted mean within 1e-9, and `ESS ≥ n/2`.
* **franchise**: a population below `SELECT_MIN_MINORITY` takes the
  pooled axes and records `auto_source="pooled"`; with the pooled walk
  also refused it records `"inherited"` and returns the module constants.
* **direction**: on a tie the nested axis adopts the richer candidate; on
  a planted 3-SE advantage for the leaner one it refuses it; the
  non-nested axes still keep ties-to-inherited.
* **shrinkage nesting**: a candidate whose best ridge is 1e-1 is scored
  at 1e-1, and the underdetermined rung appears only when
  `n_fit_rows < n_features`.
* **CLI**: `--halo-cells 48` still sets all three planes;
  `--halo-cells C=48,M=48,Y=32` parses; the header carries `halo_from`
  and `knobs_from` separately.
* **determinism**: two in-process runs give `np.array_equal` scores and
  identical `auto_verdicts`.

## 5. The isolation, as run (2026-09-07)

Built at `8356aae`, run at `8356aae` — `git rev-parse HEAD` recorded at
every launch and at every exit, all seven identical.  Same base
(`scratch/holo3-H-with-facts-7-run.32018`), same list
(`scratch/analyzer/W8/C-open.list`, 153 open C tile-streams),
`--profile patch`, one generation, `--workers 14`, halo 16, one run at a
time behind the machine gate (0 other heavy processes, 77-78 GB
free+inactive at every gate), `/usr/bin/time -l` kept.  Every run scored
offline against `scratch/analyzer/H14-pass1/payload.bin` with no
`--run-dir` and no `--gt-dir`.  Artefacts: `scratch/analyzer/W8-walk/`
(`run-walk.sh`, `walkmatrix.py`, `matrix.txt`, `logs/`).  (The runners and readers
retired 2026-10-09; their result stands above.)

| run | knobs | certified | scored | wrong | false | CPU s | peak GiB |
|---|---|---|---|---|---|---|---|
| **N0** | none | **118** | 118 | 0 | 0 | 9,315 | 38.2 |
| **N1** | `walk_weighting=cargo` | **115** | 115 | 0 | 0 | 9,328 | 38.7 |
| **N2** | `walk_franchise=pooled` | **122** | 122 | 0 | 0 | 9,227 | 38.2 |
| **N3** | `walk_direction=nested-richer` | **124** | 124 | 0 | 0 | 10,549 | 38.2 |
| **N4** | all three | **127** | 127 | 0 | 0 | 10,454 | 38.1 |
| A-red | `patch_channels=r` | 109 | 109 | 0 | 0 | 5,424 | 32.8 |
| A-rgb | `patch_channels=rgb` | **128** | 128 | 0 | 0 | 21,422 | 40.0 |

A-red and A-rgb are §1's two channel-pinned cells RE-RUN at this code
state, which §4.6 did not ask for and this record needed: `cddcb87`'s
runs left `patch_shrinkage="auto"`, so W4 moves them too and reading
N4 against them would be reading across code states, which §6.11
forbids.  **Their certificate sets came back BIT-IDENTICAL to
`R3-red`'s 109 and `R3-rgb`'s 128 — the same keys, zero either way** —
so W4 is inert on a channel-PINNED run on this list and the six-cell
matrix of §1 may be read against this wave after all.  That is also the
thing gate clause 2 existed to protect, measured instead of assumed.

**Set relations, all at one code state.**  N1 ⊂ N0 strictly (−3).
N2 = N0 +5/−1, N3 = N0 +7/−1, N4 = N0 +10/−1.  **N4 ⊂ A-rgb STRICTLY**:
the fixed walk mints 127 of the hand-pinned rgb run's 128 and nothing
outside it, missing only `(0, 45, 30, C)`, at **49 % of A-rgb's CPU** —
and **N4 ⊃ A-red strictly** (all 109).  N0 does not contain A-red (it
loses 2), so the walk only stops crossing the lean cell once W2 and W3
are on.  Against `H48-auto` N4 is 127 to 127 and differs by 6 EACH WAY:
an equal count is not the same set, and no note may say the two agree.
Union over the seven 130, intersection 105.

### 5.1 The gate, clause by clause

1. **Zero wrong, zero false accepts — PASSED.**  606 certificates
   checked across N0-N4 (843 including the two anchors), 0 wrong, 0
   false accepts, every close verified at the emission's payload sha.
2. **N0 reproduces R3-auto's 115 exactly — FAILED as written; what it
   protected is MET.**  N0 mints 118 (+5/−2 against R3-auto's 115), and
   the cause is structural and was visible in the spec: W4 lands
   UNCONDITIONALLY (§4.4: "not a knob") while `--profile patch` leaves
   `patch_shrinkage="auto"`, so the knobs-off path is not the
   pre-change path — it is the pre-change path plus W4.  The clause and
   §4.4 cannot both hold, and §4.4 is the ruling.  What clause 2 was
   protecting is the anchors, and the anchors were measured directly
   above: bit-identical.  **So the clause's failure is W4's effect,
   isolated by construction** (the null proof pins that with the ridge
   NAMED the score is byte-identical, so W4 is the only difference):
   **W4 alone is +3 certificates (5 gained, 2 lost — a crossing, not a
   containment) for 1.92× the CPU**, and it moves the channel choice
   toward `rgb` on every state (three-ink 15 % → 22 %, agnostic
   36 % → 44 %) exactly as §2.5 predicted — the richer model asks for
   more ridge and could not ask until it had already lost the vote.
3. **N4 ⊇ N0 — FAILED, by one key.**  N4 gains 10 and loses
   `(0, 47, 30, C)`, which is in NEITHER A-red nor A-rgb: it is a key
   only a MIXED per-population choice mints, not a red key lost to a
   move toward rgb.  Recorded as the regression it is.

### 5.2 What the walk did, from the ledgers

The refusal counts are identical in all five runs (state0 818, state1
790, state2 714, state3 674 of ~3,160 populations each, agnostic and
tile 126) — nothing here touches `minority_ok`, only what happens after
it.  The per-(state, source) histograms, over the same 3,538 patch
evidence blocks §2 uses:

| run | three-ink state: own/r | own/rgb | pooled | inherited | labels per feature, CHOSEN |
|---|---|---|---|---|---|
| N0 | 1,802 (57 %) | 710 (22 %) | — | 674 (21 %) | 1.34 |
| N1 | 1,803 (57 %) | 709 (22 %) | — | 674 (21 %) | 1.34 |
| N2 | 1,802 (57 %) | 710 (22 %) | 674 (21 %), of which 247 rgb | — | 1.32 |
| N3 | 132 (4 %) | 2,380 (75 %) | — | 674 (21 %) | 0.79 |
| N4 | 124 (4 %) | 2,388 (75 %) | 674 (21 %), of which 660 rgb | — | **0.47** |

* **W2 does exactly what §2.2 said was missing.**  `inherited` goes to
  zero on every per-state row and the franchise is restored without a
  pixel more: 674 three-ink populations that had never voted now carry
  the pooled walk's discovery, and 247 of them (37 %) carry `rgb` where
  the module constant carried `r`.  It is also very slightly CHEAPER
  than N0 (9,227 against 9,315 CPU s) because the pooled walk is
  memoised and the tier at step 6 reuses it.
* **W3 moves the three-ink state from 15 % rgb to 95 % of the
  populations that voted**, and the chosen labels-per-feature falls —
  median 0.71–0.84 per state at N3, and 0.46–0.49 once the franchise is
  on too (N4), against §2.1's best cell `H16-rgb` at median 0.45–0.47.
  It costs 13 % more CPU.
  *(Corrected 2026-09-07: this bullet read "falls to 0.79 — the 0.77
  §2.1 measured for the best cell", which COMPARED A MEDIAN TO A MEAN.
  N3's 0.79 is the median of `labels_per_feature_chosen`; `H16-rgb`'s
  0.76–0.78 is the MEAN of `labels_per_feature`, whose median is
  0.45–0.47.  Like for like the direction and the crossing of 1.0 both
  stand, and the walk that lands on the best cell's budget is the
  SHIPPED pair, not N3.)*
* **W1 is a measured NEGATIVE in isolation.**  Weighted, the walk shifts
  slightly TOWARD red (agnostic rgb 44 % → 42 %) and mints 3 fewer
  certificates, a strict subset.  The weighting itself is healthy — ESS
  median 119 of a median 128 rows (ratio median 0.99 — the variance
  budget almost never binds), unmatched cargo mass median 0.000, no
  refusals — so this is not a broken correction, it is a correction
  that does not pay on this sheet at this base.
  *(Corrected 2026-09-07.  This bullet read "On top of W2+W3 it is
  +4/−1 (N3 124 → N4 127)".  **N3 is the DIRECTION ALONE** — it has no
  franchise — so N3 → N4 turns on W1 AND W2 together and that +4/−1 is
  their joint effect, not W1's.  The isolation W1-on-top-of-the-shipped-
  pair was run the same day, §5.5's `FIXED-auto`: its certified set is
  **EQUAL to N4's, key for key, 0 either way**, so `walk_weighting=cargo`
  over the shipped defaults is exactly **0 gained / 0 lost**.  The whole
  124 → 127 belongs to W2's franchise on top of W3.  That STRENGTHENS
  the refusal — the weighting costs nothing and buys nothing here — and
  it retires §6's open question as posed, which rested on a number that
  does not exist.  W1 is not inert on the MECHANISM, only on the
  outcome: `FIXED-auto` and N4 reach the same 127 keys by different
  routes (first-success rungs L0 118 / L2 7 / L4 1 / L1 1 against N4's
  L0 120 / L2 5 / L4 1 / L2:layered 1, and per-state histograms that
  differ by tens of populations), so "the weighting does nothing" is
  the wrong sentence.)*

### 5.3 Disposition

Per §4.6 ("a mechanism whose isolation regresses is refused and recorded
as a measured negative; the default flip applies only to the mechanisms
that pass"):

* `walk_franchise` **ships `pooled`** (+4, and it restores the franchise
  the SELF-DISCOVERY ruling was written for);
* `walk_direction` **ships `nested-richer`** (+6);
* `walk_weighting` **stays `none`** — refused on its own isolation and
  kept as a knob.  *(Amended 2026-09-07: this bullet cited "+4/−1 in
  composition" and asked why the weighting only pays once the franchise
  and the direction are fixed.  It does not pay there at all — §5.5's
  `FIXED-auto` is the shipped pair without it and mints N4's exact 127
  keys — so the refusal now rests on "−3 alone and 0 in composition",
  which is a stronger reason than the one it was made for.  What is
  still open is narrower and is in §6: the weighting MOVES the walk
  (the rungs and the per-state histograms differ) and lands in the same
  place, and no run in this record says why.)*
* W4 is not a knob and stands; naming `patch_shrinkage` restores the old
  path exactly, which the null proof pins.

`test_analyzer_walkeval.py` records W3's own price on the synthetic
stimulus, where green and blue carry nothing for a C cell at one sibling
state: the paired test reads a TIE, the tie goes to the richer model, and
state 0's held-out d′ falls about a tenth (14.7 → 13.4, against the box
mean's 8.9).  Where the paired test can SEE the harm — states 1 and 3 in
the same run — the lean model still wins.  That is the rule working as
ruled, and it is in a test so nobody meets it as a surprise.

### 5.4 The pre-registered reversal on `cddcb87`

> "if the fixed walk at halo 16 (§4's N4) lands materially below 127 on
> these 153 rows, then the halo's franchise effect is NOT fully
> explained by W1-W3, 48 buys something real, and the default reopens
> with the halo as a candidate — to be recorded here either way."

**N4 lands at 127.  The condition does not trigger and `cddcb87`
stands.**  *(Amended 2026-09-07: N4 is all THREE knobs, including the
one §5.3 refuses, so the reversal was evaluated on a configuration that
does not ship.  The configuration `--profile patch` actually produces —
`pooled` + `nested-richer`, weighting off — was not in the N0–N4 set;
it was run the same day (§5.5's `FIXED-auto`) and lands at **127**
also, key for key N4's, so the condition still does not trigger and the
clause is now discharged on the run that ships.  The ridge repair of
§5.5 then re-ran the same configuration once more and lands at 127
again.)*  The reason is measured rather than argued: the halo-48
`auto` column's +12 was franchise and bar, and once the franchise and
the burden of proof are fixed the halo-16 walk reaches the same count at
42 % of the wide halo `auto` cell's CPU (10,454 against 24,628) and
7-9 GiB less peak RSS — and, unlike `H48-auto`, it does so inside
`A-rgb`, the best cell the matrix has.  (That containment is N4's and
`FIXED-auto`'s, against an anchor from the same code state.  After the
ridge repair BOTH move, and at that state the walk is AHEAD of the
pinned cell — `RIDGE-auto` 127 against `RIDGE-rgb` 126, crossing —
§5.5.)  What the halo still buys is the 6 keys `H48-auto` holds
that N4 does not, against the 6 N4 holds that it does not: a crossing,
not a gain.

**One sheet, one stream, one print day, one generation, one target
list.**  This promotes nothing and pins nothing (CLAUDE.md; §4.0 ruling
1).  Two defaults moved because a pre-registered gate said they would if
they passed, and both are RULES about how a run reads its own evidence,
not values read off this sheet.

### 5.5 The validation, the review, and the ridge nobody applied

Two things happened after §5 was written: the SHIPPED configuration was
run for the first time (§5 measured N0–N4 and neither of the two
in-between cells), and an independent review read the build against this
document.  Both are here; the second found a blocker in the mechanism
§3(a) is about.

**`FIXED-auto` — the configuration `--profile patch` produces**
(`pooled` + `nested-richer`, weighting off), at `d35e73d`, same base,
same 153 rows, same gate (0 other heavy processes, 77 GB free+inactive;
`head_at_launch == head_at_end`).  **127 certified** (76 dead / 22
marginal / 29 live), 127 checked, **0 wrong, 0 false accepts**, close
verified at the emission's sha, 10,416 CPU s, 864 s wall, 38.0 GiB peak.
Header `knobs_from 'profile:patch'` AND `halo_from 'profile:patch'` —
both §4.5 repairs live, no spurious `+cli`.  **Its certified set is
EQUAL to N4's, key for key**, which is what retires §5.2's attribution
of the weighting's +4 (above) and discharges §5.4's reversal clause on
a run that ships.  It is a STRICT SUBSET of `A-rgb`'s 128 (missing
`(0,45,30,C)`, the same key N4 missed) and a STRICT SUPERSET of
`A-red`'s 109.

**The review's blocker: W4's chosen ridge never reached the fitted
filter.**  `autoknobs.choose` minimises the regulariser inside every
candidate, publishes the winner in `auto_choices`, and returns it in
`axes` — and `patch._population` then fitted the population through
`patchfit.fit_population`, which reads `spec.shrinkage`, the INHERITED
constant.  Measured on the `World` fixture with every filter axis auto:
the walk chose `{state0: 0.1, state1: 0.01, state3: 0.01, agnostic:
0.001}` and **every deployed fit ran at 0.01**.  So §3(a)'s central
sentence — "the model IS fitted to the budget through the regulariser"
— and §5.2's reading of `labels_per_feature_chosen` 0.47 as "the ridge
doing the work of the missing rows" were **false in the code**: the run
paid 1.92× the CPU for a value it discarded, and
`SHRINKAGE_UNDERDETERMINED_RUNG` was added for a p > n regime the
deployed filter never saw.  The defect predates this build (`git show
a75c8c1:analyzer/patch.py` line 488 is the same lone use of
`spec.shrinkage`); W4 made it load-bearing.  Fixed at `3a661fe`, with a
test that the ridge the ledger publishes is the ridge the population
was fitted at — it fails on the pre-fix tree — and the new
`shrinkage_fitted` field beside `labels_per_feature_chosen`.

**`RIDGE-auto` — the same shipped configuration with the fix**, at
`3a661fe`, same base, same list, same gate (0 other heavy processes, 78
GB free+inactive; HEAD did not move).  Its ONLY behavioural difference
from `FIXED-auto` is that the fit is handed the population's own
`axes["shrinkage"]`, so the pair is a one-variable isolation of the
blocker.  (Three other findings landed in the same commit — W1's weights
reaching the inner ridge, the cargo bin derivation, and the
`DIRECTION_KEEP` zero-variance branch.  The first two are inert with the
weighting off, and the third needs a paired difference that is EXACTLY
constant across at least ten held-out labels, which no real log-loss
vector is; so "one variable" is exact up to that edge and nothing else.)

| run | knobs | certified | dead/marg/live | checked | wrong | false | CPU s | wall s | peak GiB |
|---|---|---|---|---|---|---|---|---|---|
| `FIXED-auto` (ridge discarded) | none | 127 | 76 / 22 / 29 | 127 | **0** | **0** | 10,416 | 864 | 38.0 |
| **`RIDGE-auto` (ridge applied)** | none | **127** | 76 / 22 / 29 | 127 | **0** | **0** | **10,357** | 857 | 38.6 |
| `A-rgb` (ridge discarded) | `patch_channels=rgb` | 128 | 77 / 22 / 29 | 128 | **0** | **0** | 21,422 | 1,644 | 40.0 |
| **`RIDGE-rgb` (ridge applied)** | `patch_channels=rgb` | **126** | 74 / 22 / 30 | 126 | **0** | **0** | 21,216 | 1,641 | 39.9 |

The pinned column was re-run too, because the repair moves it as well and
reading the walk against an anchor from the other code state is what
§6.11 forbids.  **`RIDGE-rgb` LOSES two**: `A-rgb` +`(0,35,4,C)` (live)
−`(0,19,30,C)`, −`(0,38,30,C)`, −`(0,45,30,C)` (all dead).  So applying
the ridge is a crossing at par on `auto` and a **net −2 on pinned rgb**,
and the honest headline is the pair at ONE code state:

> **`RIDGE-auto` 127, `RIDGE-rgb` 126** — the self-discovering walk is
> one certificate AHEAD of the hand-pinned channel set, at 49 % of its
> CPU, and crosses it (`auto` holds `(0,19,30)` and `(0,33,30)`, both
> dead; `rgb` holds `(0,35,4)`, live).  §5's headline was "127 of the
> hand-pinned rgb cell's 128, strictly inside it"; at the repaired code
> state the containment is gone and the ordering is inverted.  One
> sheet: this does not promote the walk any more than the old sentence
> promoted `rgb`.

**On `auto` the count does not move and the SET does**: shared 126,
`RIDGE-auto` mints `(0, 33, 30, C)` and loses `(0, 38, 30, C)`, both
dead-band — a crossing of one key each way, at **−0.6 % CPU** (the
minimisation was always being paid for; only the fit changed).  Three
things follow that the count hides:

1. **`(0, 33, 30, C)` is outside the six-way matrix's union.**  The
   matrix's intersection stays 89 and its union 135 of 153; with
   `RIDGE-auto` the union is **136**.  No configuration in this record —
   neither halo, neither pinned channel set, none of N0–N4 — had ever
   minted that key.  It is the first certificate in the wave that comes
   from the filter being FITTED differently rather than CHOSEN
   differently.
2. **The walk did not move; the filter did.**  The per-(state, source)
   channel histograms are `FIXED-auto`'s to within twelve blocks of the
   agnostic tier (3,038 → 3,026 own/rgb, a downstream effect of tiles
   that no longer reach step 6 at all), the refusal counts are
   identical, and `labels_per_feature_chosen` is identical to two
   decimals (median 0.47 / 0.46 / 0.49 / 0.48).  That is the expected
   shape: every candidate was ALREADY compared at its own ridge, so the
   choice was right and only the deployment was wrong.
3. **The certificates arrive earlier in the ladder.**  First-success
   rungs L0 **124** / L2:damped@300 2 / L1 1, against `FIXED-auto`'s L0
   118 / L2 7 / L4 1 / L1 1; and the two-arm rule
   `patch+committed|patch+offset` carries 111 of the 127 against 84,
   with the three-arm rule that needs `subtract+offset` falling 38 → 12.
   Six more tiles close at the base rung on filters that read well
   enough not to need the rung machinery.  That is a filter-quality
   signal at a fixed certificate count — and the pinned column moved the
   same way (L0 122 of 126 against `A-rgb`'s 121 of 128), so it is a
   property of the repair and not of the `auto` column.

**And the cost side, stated plainly.**  The repair is not free: it is
+0 in count on `auto`, **−2 on pinned rgb**, and the mechanism it moves
is large.  On `RIDGE-rgb`'s three-ink populations **22 % are now fitted
at the underdetermined rung 1.0 and 46 % at 0.1**, where before the
repair every one of them was fitted at the inherited 0.01 — the walk had
been choosing those ridges all along and nothing was applying them.  The
three keys it loses are all dead-band and the one it gains is live,
which points at the defect this whole document is about: **the ridge is
now chosen by the same objective §2.4 measures as 4.3–4.8× easier than
the cargo**, so on the hardest cells the regulariser it picks is the
halo's answer and not the cargo's.  That is a hypothesis from the
histograms, not a measurement; the discriminating run is W1 (which
weights exactly that objective) over the repaired tree, and it is in §6.
What is measured is the pair of counts and that the ordering inverted.

**Disposition of every review finding.**

| # | finding | verdict | disposition |
|---|---|---|---|
| 1 | W4's chosen ridge never reaches the fitted filter | **CONFIRMED** (probe above) | FIXED at `3a661fe`; re-measured as `RIDGE-auto`; §3(a)'s W4 sentence is true of the code from that sha and was not before |
| 2 | the end-to-end permutation control runs `WALK_OFF` while asserting a shipped-path property | **CONFIRMED** — under the shipped defaults state0/1/3 all come back `(0,1,2)` on a pure-noise page | test parametrised over both directions; the channel assertion is kept for `adopt-if-better`, and under `nested-richer` the control asserts what IS invariant (baseline at log 2, `patch_fitted_states == ()`, every cell to the box mean).  The tie-to-richer on noise is the ruling's own rule and is now pinned as such |
| 3 | W1's cargo weights do not reach the inner ridge minimisation | **CONFIRMED** by code (`score()` used the plain mean; `losses` and `baseline_logloss` likewise) | one decision loss now (`walkeval.weighted_mean`), and `auto_detail.loss_population` names its population.  Inert under the shipped defaults, so N0/N2/N3/`FIXED-auto`/`RIDGE-auto` are unaffected; **N1 and N4 were measured with the weighting half-applied** and their numbers stay as run, with that caveat |
| 4 | `DIRECTION_KEEP` adopts a uniformly WORSE richer candidate at exactly zero variance | **CONFIRMED** (probed: base 0.10, candidate 0.90 → `adopted True`) | a constant difference is read by its sign now; ties still go richer; both directions tested at exactly `se == 0`.  Latent, not live: real log-loss vectors do not have zero variance |
| 5 | the aperture walk's exemption from W1 lives only in a code comment | CONFIRMED | §3(b) W1 and DESIGN §14.4 amended; §4.1's ordering reason is spelled out where the promise was made |
| 6 | `patchspec` / README read as if the pre-registered gate was cleared | CONFIRMED | both say **net** +4 (+5/−1) and **net** +6 (+7/−1) now, name clause 1 as the one that applied and passed, and point at §5.1 for clauses 2 and 3 |
| 7a | `n_bins` derived from the TILE-WIDE label count, applied to per-state walks | CONFIRMED | the derivation divides by `WALK_POPULATIONS` (the four sibling states partition the labels); unchanged at the median block (451 → 4 bins), and it is the small blocks it protects.  Inert under the shipped defaults |
| 7b | a pooled-inheriting population also inherits the pooled ridge, chosen at ~4× its rows | CONFIRMED, and LIVE since finding 1 was fixed | recorded, not repaired: the population is there because its own search fold cannot carry a paired verdict, so it has nothing to re-minimise on, and a rule that scaled the inherited ridge by the row ratio would be the kind of pin §4.0 forbids.  It inherits the whole discovery or nothing.  §6 carries it |
| 8 | `CargoProfile.detail` is dead bookkeeping | CONFIRMED | published as `patch_walk_profile`, so the derived bin count is readable from a real run's ledger |
| 9 | `patchwalk.pooled_axes` names `inherit` as the shipped franchise | CONFIRMED (it is `pooled`) | docstring corrected |
| 10 | the commits' "every touched file under the 1000-line cap" over-reads, given a 1,780-line test file | CONFIRMED as prose | DESIGN §0.4's cap is about mechanism modules; the claim is scoped to those in this build's commit message.  `test_analyzer_patch.py` is pre-existing debt |

Two findings the review raised and could NOT break, recorded because
they were the ones it pushed hardest on: BLINDNESS holds (the closure
test roots every analyzer module, so `walkeval` and `patchwalk` are
covered automatically; the cargo profile reads no target-plane label
inside the tile and is bit-identical when those bits are flipped), and
FOLD DISCIPLINE holds (every walk scores `folds.search`; the select fold
is untouched).  Certification is unchanged throughout, so none of this
can mint a wrong certificate — 1,223 certificates checked across
N0–N4 (606), the two anchors (237), `FIXED-auto` (127), `RIDGE-auto`
(127) and `RIDGE-rgb` (126), **0 wrong, 0 false accepts**.

Artefacts: `scratch/analyzer/W8-halo/FIXED-auto{,-score}` and
`scratch/analyzer/W8-ridge/RIDGE-{auto,rgb}{,-score}` (ledgers, closes,
payloads), `logs/<run>.{out,err,meta}` with `/usr/bin/time -l` and the
launch/exit HEAD (identical at launch and exit for all three),
`logs/gate.log` (0 other heavy processes, 77–78 GB free+inactive at
every gate), the runners `run-fixed.sh` / `run-ridge.sh`, and the
comparisons `fixed-matrix.txt` / `matrix.txt` from `fixedmatrix.py` /
`ridgematrix.py`.  (The runners and readers retired 2026-10-09; their result stands above.)

**One sheet, one stream, one print day, one generation, one target
list.**  Nothing here promotes a default or pins a value.

## 6. What stays open

* **The union is not reachable.**  Intersection 89, union 135 of 153; 46
  certificates depend on the cell.  The cheap battery does not help — red
  ⊂ rgb at halo 16, so carrying both channel sets as two arms buys
  nothing — and the extra 6–7 over H16-rgb's 128 live across the HALO
  (H16-rgb ∪ H48-rgb = H16-rgb ∪ H48-auto = 134), i.e. they cost the wide
  halo's 4.3×.  Recorded, not proposed.
* **The window and samples axes** have not had this matrix.  W3's
  direction flip is deliberately channel-only; whether ties should go
  richer on geometry is unmeasured and would change the geometry the 128
  was measured at.
* **Why W1 moves the walk and not the outcome.**  *(Rewritten
  2026-09-07: this item asked "why does the cargo weighting only pay in
  composition", on a +4/−1 that turned out to be W1 and W2 together —
  §5.2.  Over the shipped pair the weighting is exactly 0 gained / 0
  lost.)*  Alone the cargo weighting is −3 and a strict subset; over the
  shipped defaults it mints N4's exact 127 keys.  But it is NOT inert on
  the mechanism — the first-success rungs and the per-state histograms
  differ by tens of populations — so the open question is now the
  narrower one: a correction that is healthy on every published number
  (ESS ratio median 0.99, unmatched 0.000, no refusals) moves which
  filter each population deploys and lands on the same certificates.
  Nothing here says whether that is this sheet's dead band being
  insensitive or the correction being too small to matter.  The
  discriminating run is W1 over the new defaults, PRE-REGISTERED on a
  second sheet rather than re-based on this one — and it must now be
  re-based anyway, because the weights reach the inner ridge from
  `3a661fe` and the bins are derived per walking population (§5.5,
  findings 3 and 7a): **N1 and N4 measured a half-applied weighting.**
* **The pooled-inherited RIDGE** (§5.5, finding 7b).  A population that
  takes W2's franchise takes the pooled walk's regulariser too, and the
  pooled walk chose it at roughly four times the rows — and, since
  `3a661fe`, that ridge is what the inheriting population is FITTED at.
  It cannot re-minimise (its own search fold is why it is here), and a
  rule that scaled the inherited ridge by the row ratio would be a pin.
  21 % of the three-ink populations are in this branch; nothing measures
  what it costs.
* **The one key the ridge repair bought is outside every cell measured
  here** — `(0, 33, 30, C)`, in none of the six matrix cells, none of
  N0–N4 and neither anchor (§5.5).  The ledger carries the
  per-population verdicts and now `shrinkage_fitted`, so which
  population's ridge minted it is answerable without a re-run.
* **WHY THE APPLIED RIDGE COSTS THE PINNED COLUMN THREE DEAD-BAND
  TILES** (§5.5).  `RIDGE-rgb` fits 22 % of its three-ink populations at
  the underdetermined rung and 46 % at 0.1, where before the repair
  every one was fitted at the inherited 0.01 — and it loses three
  dead-band certificates and gains one live one.  The natural reading is
  that the regulariser is now chosen by the objective §2.4 measures as
  4.3–4.8× easier than the cargo, i.e. that W4 handed the criterion
  defect a second lever.  It is a hypothesis from two histograms.  The
  discriminating run is W1 over the repaired tree — which is the same
  run the item above owes — so the two questions have collapsed into
  one, and it is the wave's next measurement.
* **The one key N4 loses** — `(0, 47, 30, C)`, in neither A-red nor
  A-rgb, so it is minted only by a mixed per-population choice.  Nothing
  in this record explains which population, and the ledger carries the
  per-population verdicts now, so it is answerable without a re-run.
* **W4's cost.**  The inner ridge minimisation is 1.92× the CPU of the
  coordinate pass on the `auto` column and 2.6× on the pinned `rgb` one
  (21,422 against `R3-rgb`'s 8,217), for +3 on `auto` and +0 on the
  pinned cells.  Applying the ridge it chooses costs nothing on top
  (`RIDGE-auto` 10,357 CPU s against `FIXED-auto`'s 10,416) and is worth
  a crossing of one key plus six more certificates at the base rung
  (§5.5) — so the 1.92× is now buying a filter and not only a
  comparison, which is a better bargain than §5.1 could state but still
  a measured 1.92×.  Cheaper forms exist (warm-start the ladder, or
  minimise only where `n/p < 1`); none is measured.
* **The paired halo test**, for whoever reopens (a) with a second sheet:
  fit each halo candidate on its own fit fold, evaluate BOTH on the
  smallest candidate's search-fold rows, pair there.  It is the only
  comparison between halos this machinery can make honestly, and it costs
  the widest candidate's crops.
* **No offline cell-error column** exists for this matrix (§1).  If the
  channel axis's cell error at halo 48 is wanted it is a separate
  `analyzer score --run-dir --gt-dir --halo-cells 48` pass.
* **The difficulty covariate is one choice among several.**  `abs(z)` on
  the incumbent box-mean score is motivated by the third-layer
  measurement (a flat 60 % deficit compresses the cell toward the
  midpoint) and is candidate-independent, but position in the page (the
  dead band is a column phenomenon) and the local sibling-ink context are
  equally blind and untried.
* **Memory**: 46.9–47.1 GiB peak at halo 48 against a 45 GB gate.  A
  wider halo, or a Y-stream version of this matrix (which starts at 32),
  should be assumed to need the machine alone.
* **One sheet, one stream, one print day, one generation.**  Nothing here
  promotes a default or pins a value, and the SELF-DISCOVERY ruling
  forbids pinning `rgb` or a halo from it — which is exactly why the
  ruling is about the walk's objective, its franchise and its burden of
  proof, and not about which of the six cells won.
