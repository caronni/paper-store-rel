# The widened matrix's whole-page colour existence proofs — retired 2026-09-20

Status: RECORD. Nothing here is a test any more. This file is where the
measured content of `test_h3_swim_existence.py`, `test_h3_color_field_yield.py`
and the colour half of `test_h3_plugins_local_ctx.py` went when the repo owner
ruled them out of the tree, and it is written so that a later reader who wants
those numbers — or wants to re-derive that stimulus — does not have to go
through git to find them. The last commit that carried the code is
`65dc78a9037b85d1ee0c699cb964193385a31874` (main, 2026-09-20); the 5.2-dot
re-derivation in section 2b and the 2026-09-20 re-pins in section 4 were
uncommitted working-tree edits on top of it, made the same day, and are carried
here because they exist nowhere else.

## 1. The ruling, and what it cost

The repo owner, 2026-09-20, verbatim:

> I agree this code should leave the test trees. I don't see what they actually
> test, that a simple patch-based regression test does not already ascertain (or
> could be ascertaining) at much much lower cost, if at all.

The cost that provoked it. The receiver's widened matrix
(`HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1`) took 96 minutes at `-n 8`
on 2026-09-20, and almost all of it was whole-page colour existence proofs:

| retired | what it ran | cost |
|---|---|---|
| `test_h3_swim_existence.py` | three serial decodes of a steeply displaced top-rung colour page | ~2 h |
| `test_h3_color_field_yield.py` | the two-dot displaced pair, three serial decodes | ~66 min |
| the colour local-patch arms in `conftest.py` | four colour decodes of a one-window damaged patch | ~8 min |

The third had already argued itself out of a job: its own ledger has said since
2026-09-07 that the tier's gain on that stimulus is ZERO, so the four decodes
bought a measurement that had stopped measuring anything.

What replaces them is what the ruling names: the K local-patch arms — a 49-tile
K page with one window given a directional smear and its own noise, three
decodes of a few seconds each — which stay in `test_h3_plugins_local_ctx.py`
(section 7).

## 2. The swim existence module's ledger

`src/holo/receiver/tests/test_h3_swim_existence.py`. Its module docstring WAS
the measured record of every re-derivation of that stimulus — 3 -> 3.5 -> 4 ->
4.5 -> 5.2 dots — so it is carried whole, in both of its last two states.

### 2a. As `65dc78a9` carried it (the 4.5-dot ledger)

```text

The swim's reason to exist, end to end, against the field itself.

One emitted top-rung colour page rendered twice: every plane in
register, and plane Y displaced along x by a mean-zero sinusoid of
FOUR dots, one cycle down the page.  Same emit, same shape,
same period and the same noise draw as the two-dot pair
`test_h3_color_field_yield` uses — the ONE variable is the amplitude,
and the field is given its best shot: it is always on (the dial retired
2026-09-07 with the page field), so the swim is asked for exactly the
tiles the field, running, still missed.

RE-DERIVED TWICE, and the history is the point rather than an
embarrassment.  The first version ran at three dots against a field
that applied a ninth of what it fitted; the units fix made the field
honest and that residue VANISHED.  Re-bracketed at 3.5, and then the
anchortier line's median-across-planes publication took the
plane-common part out, left Y a cleaner differential, and THAT residue
vanished too.  Each repair to the field pushed the number up, which is
exactly what this row's licence says should happen: the swim's job is
whatever the field of the day still cannot express, so the stimulus is
re-derived whenever the field changes.

The band has a ceiling as well as a floor, and the ceiling is worth
naming because it bounds every residue row and not just this one: on
the pre-anchortier tree four dots put the Y stream below the
informative floor, so no tile was ever ATTEMPTED, no `AttemptFact` was
emitted, and no residue row was born at all.  A rescue row can only
help a tile the receiver still tries.  The better field puts Y back
inside that floor at four dots, which is how this bracket exists.

WHY AMPLITUDE, AND NOT SHARPNESS.  A step looks like the better
separator on paper — the field pools over a two-tile Gaussian truncated
at 3.5 sigma, a seven-tile reach on a ten-tile page, so it cannot
follow an edge.  MEASURED 2026-08-31, and it is not: a two-dot,
one-cycle SQUARE WAVE costs this page exactly ONE certificate with the
field switched off (299/300, payload byte-exact), because a one-cycle
square wave has a large linear component and the colour lane's own
{1, y} per-plane page-fraction residual absorbed it before any rescue
tier was reached.  Only a mean-zero full-cycle SINUSOID is orthogonal
to that residual, which is why the sinusoid is the stimulus of record
here and in the two-dot pair.  (RE-POINTED 2026-09-08: that residual
retired with W3a, I7 — the colour lane reads at the page field or at
the pose now — so the square wave's cheapness is a 2026-08-31
measurement on a tree that no longer exists, and the sinusoid is kept
because re-deriving the stimulus would move every number in this file
and in `test_h3_color_field_yield.py`.  The sentence here used to point
at a test named for that arithmetic; no such test exists in this tree,
and the pointer is dropped rather than invented.)

Amplitude, in contrast, separates the swim from the whole standing
stack at once and by construction: the window pose search reaches a
quarter cell (`refine.PHASE_LIMIT_CELLS`, 0.75 dots here), the field
reaches as far as its ESTIMATOR does — the anchor tier's Y radius less
its saturation margin, 2.24 dots — and past that it degrades rather
than saturating, while the swim's bound is a full cell measured FROM
the field's own number.

Three decodes, all at workers 1 with `--complete`.  MEASURED
2026-08-31 on the merged tree, and pinned below:

    steep-control       in register, swim dropped   300/300, byte-exact
                        (since 2026-09-03 the two-dot pair's own control
                        decode, shared — same raster, argv and hold-out)
    steep-fields        field ON, swim dropped      299/300, byte-exact
    steep-fields-swim   field ON, swim ON           300/300, byte-exact

The one the field missed is Y at (2, 4), and it survived ALL THREE
cheaper rescue rows — the field-only arm spent 45 `tiles.local`, 19
`tiles.planek` and 9 `tiles.retry` certificates' worth of grinding and
still could not have it.  The swim recovers exactly that tile, and its
certificate signature (every address AND every user-bit vector) is
BYTE-IDENTICAL to the in-register control's: `c31d3d1453c0ac71…`,
against the field-only arm's `afa1d7eb1646e744…`.

WHAT THE FIELD REPAIRS CHANGED, since this row predates both.  The
swim now composes with a working field instead of standing in for a
broken one: median correction 0.375 dots on the in-register planes and
0.562 on Y, with Y reaching the full 3.000-dot bound where the hint
needs the most help.  That is the designed composition — the field
carries the bulk and the bound is measured from it.

COST, honestly, because it moved the wrong way: 137 jobs and 662.7 s,
20% of that run's 3,320 s, against 2.7% at the previous bracket.  A
harder page means more residue tiles, each paying a full local head fit
plus the search, and the row converts 23 certificates for it.  It is
the dearest row in the tree and at this amplitude it looks it.

WORKERS, measured on the previous bracket and not re-run here (a fourth
decode does not fit the lane): at workers 8 the swim fires more jobs
and mints more certificates than the serial run while `tiles.local`
mints fewer — the schedule differs, so which row reaches a tile first
differs, and the rows trade work between them.  The run still reaches
the control's count with the payload AND the whole certificate
signature identical to the serial run's.  The standing law asks only
for payload bytes at w8; this clears the stronger bar, and the trade is
the clearest evidence that these rescue rows are interchangeable on the
easy tiles and only the swim reaches the hard one.

BROKEN BY THE b8471fc RE-KEY, 2026-09-03, AND THE AMPLITUDE LADDER IS
EXHAUSTED.  Read this before touching anything here.

`test_every_rescued_certificate_was_minted_by_the_swim_itself` fails,
and it is right to.  Measured on the re-keyed page, same argv and
hold-out as the fixtures:

    field alone         299/300      field + swim   300/300
    rescued             ONE address, Y at (9, 3)
    minted by           tiles/local150 — NOT THE SWIM
    swim-run by source  local150 61, planek150 4, scan 217, swim150 18

The swim still mints 18 certificates, but every one of them is an
address the field-only arm ALSO certified: its MARGINAL contribution on
this stimulus is now ZERO, and its presence only changes which row
reaches a tile first.  That is exactly the coincidence
`test_every_rescued_certificate_was_minted_by_the_swim_itself` exists to
catch, so there is nothing here to re-pin.

WHAT ACTUALLY MOVED, precisely: not the row, not the field — nothing in
src/holo/receiver/plugins changed in that merge — and not even the COUNT.  The field
still misses exactly one tile, 299/300, as it did above.  It is a
DIFFERENT tile.  The old one was Y at (2, 4), which survived all three
cheaper rescue rows; the re-key redrew the page and the tile the field
now misses, Y at (9, 3), is inside `tiles.local`'s reach.  The stimulus
stopped separating the swim from the cheaper rows.

THE INTEGER-PEAK LADDER IS CLOSED BY MEASUREMENT; the amplitude itself
is not whole-dot bound.  `_h3_sims.plane_x_shift_dots` rounds the
sinusoid PER ROW — no interpolation at any amplitude; this constant was
3.5 until b928312 through that same function.  What held
`STEEP_AMPLITUDE_DOTS` at 4.0 was two fast-lane pins: this module's own
`peak == 4` and `test_h3_color_field_yield`'s `STEEP == SHIFTED + 1.0`;
5.0 fails both, 4.5 the second.  The next whole PEAK above four is
five.  Measured 2026-09-03 at five dots, both
arms, same argv (`scratchpad`-driven, `_h3_sims.render_hard_pair` at the
new amplitude, nothing in this tree edited):

    field alone 200/300   field + swim 200/300   rescued 0
    every certificate from tiles/scan; the ONLY row that fires is
    tiles.scan — tiles.swim, tiles.local, tiles.planek and tiles.retry
    all fire ZERO times

That is the ceiling this docstring already names, hit exactly: Y drops
under the informative floor, no tile is attempted, no AttemptFact is
emitted, and no residue row is born at all.  A rescue row can only help
a tile the receiver still tries.  So the ladder has three rungs and all
three are taken — three dots is `test_h3_color_field_yield`'s stimulus
(the swim recovers that page unaided), four no longer separates, five is
past the floor.  Fractional amplitudes between them are renderable —
4.5 rounds to a wider ±4 plateau, 4.51 to 4.99 to a narrowing 5-dot band
— and 4.5 is MEASURED SEPARATELY BELOW; episode 2's width rejection was
at two dots with the dial off, an expectation and not a closure.

    4.5 dots: field alone 200/300 — Y = 0, but NOT under the floor as
    at five: tiles.retry, tiles.local and tiles.planek each fire 100
    jobs — the count of Y tiles — and certify none (confirming run,
    2026-09-04).  Field + swim 297/300: the swim mints 20 Y tiles; the
    other 77 land through tiles.local (73) and scan (4).  The swim is
    causal for 97 certificates and the source test above would count
    20 of them.  A live rung — for a stronger claim than this module
    made ("without the swim the plane is dead"): same axis, different
    assertion.

RE-DERIVED TO 4.5, 2026-09-04, by the yield principle.  4.5 is where
the swim buys the most: with the field running and the swim dropped the
whole Y plane is lost — 200/300, its tiles attempted by retry, local and
planek (100 jobs each, the count of Y tiles) and every attempt failed —
and with the swim in the schedule it comes back to 297/300.  The swim
mints 20 of the 97; the other 77 arrive through tiles.local (73) and
plain scan (4).  So the claim this module now makes is the causal one,
not the per-certificate one: every rescued address exists only with the
swim in the schedule, because without it a hundred attempts fail and
none certifies.  The exact-page audit below keeps its zero-wrong half
(every certificate the swim arm mints is the control's, bit for bit)
and drops completeness, which 4.0 had by luck: 297 of 300 at 4.5.

ORACLE-SWEEP gated for the same reason the two-dot pair is: the
degraded capture is the most expensive decode in the tree and this
adds three more.  Run them with

    HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1 \
        python -m pytest src/holo/receiver/tests/test_h3_swim_existence.py -q

The out-of-pytest driver that ran the same arms plus the field-hint
ablation, `measure/h3_swim.py`, retired at W6 with the `--plane-fields`
dial it switched and the pre-W2 fitter it imported.
```

Its measured constants at that state:

```python

# the top-rung colour sim is a c3 page: three printed dots to a cell
CELL_DOTS = 3
DISPLACED_STREAM = "Y"
PLANE_STREAMS = ("C", "M", "Y")
SWIM_SOURCE = tiles.source_tag(tiles.STAGE_SWIM150)
RESCUE_ROWS = ("tiles.swim", "tiles.local", "tiles.planek", "tiles.retry")
# measured 2026-09-04 at 4.5 dots (see the docstring)
RESCUED_BY_SOURCE = {SWIM_SOURCE: 20,
                     tiles.source_tag(tiles.STAGE_LOCAL150): 73,
                     tiles.source_tag(tiles.STAGE_SCAN): 4}
FIELD_ONLY_RESCUE_JOBS = {"tiles.swim": 0, "tiles.local": 100,
                          "tiles.planek": 100, "tiles.retry": 100}
SWIM_ARM_CERTIFIED = 297
```

### 2b. The 5.2-dot re-derivation, uncommitted, 2026-09-20

Measured the same day the ruling landed, off the ladder in section 5: the page
field merged 2026-09-12 rescues 4.5 dots outright, so every number in 2a went
vacuous at once and the stimulus was re-derived a fourth time. This docstring
never reached a commit.

```text

The swim's reason to exist, end to end, against the field itself.

One emitted top-rung colour page rendered twice: every plane in
register, and plane Y displaced along x by a mean-zero sinusoid of
5.2 dots, one cycle down the page.  Same emit, same shape,
same period and the same noise draw as the two-dot pair
`test_h3_color_field_yield` uses — the ONE variable is the amplitude,
and the field is given its best shot: it is always on (the dial retired
2026-09-07 with the page field), so the swim is asked for exactly the
tiles the field, running, still missed.

RE-DERIVED FOUR TIMES NOW, and the history is the point rather than an
embarrassment.  The first two, in this paragraph; 4.0 -> 4.5 and
4.5 -> 5.2 have their own dated entries below.

The first version ran at three dots against a field
that applied a ninth of what it fitted; the units fix made the field
honest and that residue VANISHED.  Re-bracketed at 3.5, and then the
anchortier line's median-across-planes publication took the
plane-common part out, left Y a cleaner differential, and THAT residue
vanished too.  Each repair to the field pushed the number up, which is
exactly what this row's licence says should happen: the swim's job is
whatever the field of the day still cannot express, so the stimulus is
re-derived whenever the field changes.

The band has a ceiling as well as a floor, and the ceiling is worth
naming because it bounds every residue row and not just this one: on
the pre-anchortier tree four dots put the Y stream below the
informative floor, so no tile was ever ATTEMPTED, no `AttemptFact` was
emitted, and no residue row was born at all.  A rescue row can only
help a tile the receiver still tries.  The better field puts Y back
inside that floor at four dots, which is how this bracket exists.

WHY AMPLITUDE, AND NOT SHARPNESS.  A step looks like the better
separator on paper — the field pools over a two-tile Gaussian truncated
at 3.5 sigma, a seven-tile reach on a ten-tile page, so it cannot
follow an edge.  MEASURED 2026-08-31, and it is not: a two-dot,
one-cycle SQUARE WAVE costs this page exactly ONE certificate with the
field switched off (299/300, payload byte-exact), because a one-cycle
square wave has a large linear component and the colour lane's own
{1, y} per-plane page-fraction residual absorbed it before any rescue
tier was reached.  Only a mean-zero full-cycle SINUSOID is orthogonal
to that residual, which is why the sinusoid is the stimulus of record
here and in the two-dot pair.  (RE-POINTED 2026-09-08: that residual
retired with W3a, I7 — the colour lane reads at the page field or at
the pose now — so the square wave's cheapness is a 2026-08-31
measurement on a tree that no longer exists, and the sinusoid is kept
because re-deriving the stimulus would move every number in this file
and in `test_h3_color_field_yield.py`.  The sentence here used to point
at a test named for that arithmetic; no such test exists in this tree,
and the pointer is dropped rather than invented.)

Amplitude, in contrast, separates the swim from the whole standing
stack at once and by construction: the window pose search reaches a
quarter cell (`refine.PHASE_LIMIT_CELLS`, 0.75 dots here), the field
reaches as far as its ESTIMATOR does — the anchor tier's Y radius less
its saturation margin, 2.24 dots — and past that it degrades rather
than saturating, while the swim's bound is a full cell measured FROM
the field's own number.

Three decodes, all at workers 1 with `--complete`.  MEASURED
2026-08-31 on the merged tree, and pinned below:

    steep-control       in register, swim dropped   300/300, byte-exact
                        (since 2026-09-03 the two-dot pair's own control
                        decode, shared — same raster, argv and hold-out)
    steep-fields        field ON, swim dropped      299/300, byte-exact
    steep-fields-swim   field ON, swim ON           300/300, byte-exact

The one the field missed is Y at (2, 4), and it survived ALL THREE
cheaper rescue rows — the field-only arm spent 45 `tiles.local`, 19
`tiles.planek` and 9 `tiles.retry` certificates' worth of grinding and
still could not have it.  The swim recovers exactly that tile, and its
certificate signature (every address AND every user-bit vector) is
BYTE-IDENTICAL to the in-register control's: `c31d3d1453c0ac71…`,
against the field-only arm's `afa1d7eb1646e744…`.

WHAT THE FIELD REPAIRS CHANGED, since this row predates both.  The
swim now composes with a working field instead of standing in for a
broken one: median correction 0.375 dots on the in-register planes and
0.562 on Y, with Y reaching the full 3.000-dot bound where the hint
needs the most help.  That is the designed composition — the field
carries the bulk and the bound is measured from it.

COST, honestly, because it moved the wrong way: 137 jobs and 662.7 s,
20% of that run's 3,320 s, against 2.7% at the previous bracket.  A
harder page means more residue tiles, each paying a full local head fit
plus the search, and the row converts 23 certificates for it.  It is
the dearest row in the tree and at this amplitude it looks it.

WORKERS, measured on the previous bracket and not re-run here (a fourth
decode does not fit the lane): at workers 8 the swim fires more jobs
and mints more certificates than the serial run while `tiles.local`
mints fewer — the schedule differs, so which row reaches a tile first
differs, and the rows trade work between them.  The run still reaches
the control's count with the payload AND the whole certificate
signature identical to the serial run's.  The standing law asks only
for payload bytes at w8; this clears the stronger bar, and the trade is
the clearest evidence that these rescue rows are interchangeable on the
easy tiles and only the swim reaches the hard one.

BROKEN BY THE b8471fc RE-KEY, 2026-09-03, AND THE AMPLITUDE LADDER IS
EXHAUSTED.  Read this before touching anything here.

`test_every_rescued_certificate_was_minted_by_the_swim_itself` fails,
and it is right to.  Measured on the re-keyed page, same argv and
hold-out as the fixtures:

    field alone         299/300      field + swim   300/300
    rescued             ONE address, Y at (9, 3)
    minted by           tiles/local150 — NOT THE SWIM
    swim-run by source  local150 61, planek150 4, scan 217, swim150 18

The swim still mints 18 certificates, but every one of them is an
address the field-only arm ALSO certified: its MARGINAL contribution on
this stimulus is now ZERO, and its presence only changes which row
reaches a tile first.  That is exactly the coincidence
`test_every_rescued_certificate_was_minted_by_the_swim_itself` exists to
catch, so there is nothing here to re-pin.

WHAT ACTUALLY MOVED, precisely: not the row, not the field — nothing in
src/holo/receiver/plugins changed in that merge — and not even the COUNT.  The field
still misses exactly one tile, 299/300, as it did above.  It is a
DIFFERENT tile.  The old one was Y at (2, 4), which survived all three
cheaper rescue rows; the re-key redrew the page and the tile the field
now misses, Y at (9, 3), is inside `tiles.local`'s reach.  The stimulus
stopped separating the swim from the cheaper rows.

THE INTEGER-PEAK LADDER IS CLOSED BY MEASUREMENT; the amplitude itself
is not whole-dot bound.  `_h3_sims.plane_x_shift_dots` rounds the
sinusoid PER ROW — no interpolation at any amplitude; this constant was
3.5 until b928312 through that same function.  What held
`STEEP_AMPLITUDE_DOTS` at 4.0 was two fast-lane pins: this module's own
`peak == 4` and `test_h3_color_field_yield`'s `STEEP == SHIFTED + 1.0`;
5.0 fails both, 4.5 the second.  The next whole PEAK above four is
five.  Measured 2026-09-03 at five dots, both
arms, same argv (`scratchpad`-driven, `_h3_sims.render_hard_pair` at the
new amplitude, nothing in this tree edited):

    field alone 200/300   field + swim 200/300   rescued 0
    every certificate from tiles/scan; the ONLY row that fires is
    tiles.scan — tiles.swim, tiles.local, tiles.planek and tiles.retry
    all fire ZERO times

That is the ceiling this docstring already names, hit exactly: Y drops
under the informative floor, no tile is attempted, no AttemptFact is
emitted, and no residue row is born at all.  A rescue row can only help
a tile the receiver still tries.  So the ladder has three rungs and all
three are taken — three dots is `test_h3_color_field_yield`'s stimulus
(the swim recovers that page unaided), four no longer separates, five is
past the floor.  Fractional amplitudes between them are renderable —
4.5 rounds to a wider ±4 plateau, 4.51 to 4.99 to a narrowing 5-dot band
— and 4.5 is MEASURED SEPARATELY BELOW; episode 2's width rejection was
at two dots with the dial off, an expectation and not a closure.

    4.5 dots: field alone 200/300 — Y = 0, but NOT under the floor as
    at five: tiles.retry, tiles.local and tiles.planek each fire 100
    jobs — the count of Y tiles — and certify none (confirming run,
    2026-09-04).  Field + swim 297/300: the swim mints 20 Y tiles; the
    other 77 land through tiles.local (73) and scan (4).  The swim is
    causal for 97 certificates and the source test above would count
    20 of them.  A live rung — for a stronger claim than this module
    made ("without the swim the plane is dead"): same axis, different
    assertion.

RE-DERIVED TO 4.5, 2026-09-04, by the yield principle.  4.5 is where
the swim buys the most: with the field running and the swim dropped the
whole Y plane is lost — 200/300, its tiles attempted by retry, local and
planek (100 jobs each, the count of Y tiles) and every attempt failed —
and with the swim in the schedule it comes back to 297/300.  The swim
mints 20 of the 97; the other 77 arrive through tiles.local (73) and
plain scan (4).  So the claim this module now makes is the causal one,
not the per-certificate one: every rescued address exists only with the
swim in the schedule, because without it a hundred attempts fail and
none certifies.  The exact-page audit below keeps its zero-wrong half
(every certificate the swim arm mints is the control's, bit for bit)
and drops completeness, which 4.0 had by luck: 297 of 300 at 4.5.

RE-DERIVED TO 5.2, 2026-09-20, by the yield principle again, and by
the licence rather than in spite of it: the PAGE FIELD
merged 2026-09-12 and it rescues four and a half dots outright.  Every
number above went vacuous at once — field alone 300/300, field + swim
300/300, nothing rescued, nothing to attribute — which is the failure
mode this module is built to have rather than a regression to chase.

The ladder, both arms, same argv and hold-out as the fixtures,
`_h3_sims.render_hard_pair` driven from a scratchpad with nothing in
this tree edited, workers 1 and `--complete`:

    4.5   field alone 300/300           the field has the whole step
    5.0   field alone 200/300, Y = 0    retry 400, local 600, planek 500
                                        jobs on the dead plane and not
                                        one Y certificate; the swim arm
                                        was ABANDONED at 105 minutes of
                                        wall without a result, so what
                                        it buys here is NOT measured
    5.2   field alone 200/300, Y = 0    retry 500, local 700, planek 700
                                        jobs, no Y; field + swim 231/300,
                                        31 Y tiles back, payload
                                        byte-exact on both arms  <== taken

5.2 is the rung where the swim buys the most OF THOSE MEASURED ON BOTH
ARMS, which is weaker than the principle asks for: 5.0 may buy more and
nobody knows.  What decided it in the end is the wall — 5.2's swim arm
took 2,484 s where 5.0's had burned 6,300 and was still running, and a
stimulus the oracle lane cannot finish is not a stimulus.  Re-opening
5.0 is a costed run, not a guess.

The CEILING moved with the field, exactly as this docstring says it
must.  Five dots was PAST the informative floor on the 2026-09-03 tree —
Y never attempted, no residue row born — and on this one five dots is
attempted and ground over by three rows, which is what leaves a band to
stand in at all.  The band's floor is the field estimator's reach (2.24
dots) and its roof is one printed cell past it (5.24), and inside that
band the rounded per-row shift peaks at five dots everywhere from 4.55
up: what the amplitude actually dials is how MANY of the 1920 rows sit
at the peak, 91 at 4.55 against 321 at 5.2.  So the "integer-peak
ladder" the entry above closed is closed for good, and the live dial is
the width of the plateau.

WHAT THE SWIM MINTS HERE, and the honest shape of the claim: 5 of the 31
carry its own source tag and 26 arrive through `tiles.planek`.  The
causal claim is unchanged and is the one the goldens hold — with the
swim dropped, planek fires 700 jobs at that plane and certifies NONE of
it, so all 31 exist only because the swim is in the schedule — but the
per-certificate claim is now the smaller half it was at 4.5, not the
larger.  The rescued page is a strict sub-page of the in-register
control (231 of 300, `swim - control` empty).

ORACLE-SWEEP gated for the same reason the two-dot pair is: the
degraded capture is the most expensive decode in the tree and this
adds three more.  Run them with

    HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1 \
        python -m pytest src/holo/receiver/tests/test_h3_swim_existence.py -q

The out-of-pytest driver that ran the same arms plus the field-hint
ablation, `measure/h3_swim.py`, retired at W6 with the `--plane-fields`
dial it switched and the pre-W2 fitter it imported.
```

And its constants at that state:

```python

# the top-rung colour sim is a c3 page: three printed dots to a cell
CELL_DOTS = 3
DISPLACED_STREAM = "Y"
PLANE_STREAMS = ("C", "M", "Y")
SWIM_SOURCE = tiles.source_tag(tiles.STAGE_SWIM150)
RESCUE_ROWS = ("tiles.swim", "tiles.local", "tiles.planek", "tiles.retry")
# measured 2026-09-20 at 5.2 dots (see the docstring); at 4.5 these read
# 20 / 73 local / 4 scan, 100 jobs a row, and 297 certified
RESCUED_BY_SOURCE = {SWIM_SOURCE: 5,
                     tiles.source_tag(tiles.STAGE_PLANEK150): 26}
FIELD_ONLY_RESCUE_JOBS = {"tiles.swim": 0, "tiles.local": 700,
                          "tiles.planek": 700, "tiles.retry": 500}
SWIM_ARM_CERTIFIED = 231
```

### 2c. The stimulus module's own frozen-render ledger

From `_h3_sims.py`, the block that froze the pair's renders and derived the
steep amplitude — the bracket history (3.0 pre units-fix, 3.5 post, 4.0, 4.5,
5.2) as the stimulus module carried it. The two-dot pair's own constants
(`SHIFTED_*`, `HARD_*`, `render_hard_pair`, `make_color_hard`) STAY in the tree:
`measure/local_ab/_sim.py` builds its simulated control from them, so what is
deleted here is only the fixture-side half — the frozen render digests, the
`EXPECTED_*` gates and the steep amplitude.

```python
# frozen 2026-08-30: the top-rung colour pair, one emit rendered twice.
# The payload and the CONTROL are unchanged by the 2026-08-31 re-harden
# — the control render does not depend on the displacement at all, which
# is why the control's own yield still speaks for both amplitudes — and
# only the shifted render was re-frozen (2 dots -> 3).
HARD_PAYLOAD_SHA256 = (
    "7902836205689f47c7c2d80c53023b1a31442720b86d175d677e6b71f66155c9")
CONTROL_TIFF_SHA256 = (
    "d1531ec4109235fa5bd470efb25294e322d4f09595723ff56a6e26bd8c89ffe2")
SHIFTED_TIFF_SHA256 = (
    "31ed036ae09bf516d1675d0930f07488d99ef4869997747077f4e397deb0a5ab")
EXPECTED_HARD: dict[str, str] = {
    HARD_PAYLOAD_NAME: HARD_PAYLOAD_SHA256,
    CONTROL_TIFF_NAME: CONTROL_TIFF_SHA256,
    SHIFTED_TIFF_NAME: SHIFTED_TIFF_SHA256,
}

# frozen 2026-08-31 at twice the amplitude, re-derived 2026-09-03 to 4.5
# dots by the yield principle (MEASUREMENTS-2026-09-03.md): the SAME emit,
# period, noise draw and SHAPE as the two-dot pair above.  Amplitude is the one dial
# that separates the standing per-plane machinery from a bounded direct
# search, and four dots is past the whole standing stack at once: past
# `refine.PHASE_LIMIT_CELLS` (a quarter cell, 0.75 dots here) and past
# the field's ESTIMATOR — the anchor tier's Y radius less its saturation
# margin, 2.24 dots (RE-POINTED 2026-09-07: the clamp this used to name
# is retired with the publish gate, I8).  Past that reach the field does
# not saturate, it DEGRADES: the correlation aliases onto a nearer peak
# and reads 1.124 dots of four and 1.699 of five (measured, the swim
# module's own table), where at three it refuses and reads zero.
#
# THE NUMBER IS BRACKETED BY MEASUREMENT AND IT HAS MOVED TWICE, which
# is the honest thing to record about it.  Each bracket was re-run on
# the tree of the day, the field running and the swim dropped:
#
#   pre units-fix   3.0 dots leaves 17 tiles (field applied 1/cell_dots
#                   of what it fitted)
#   post units-fix  3.0 closes 300/300, 3.5 leaves 2, 4.0 puts Y below
#                   the informative floor so nothing is ATTEMPTED
#   post anchortier 3.5 closes 300/300 (the median-across-planes
#                   publication takes the plane-common part out and
#                   leaves Y a cleaner differential), 4.0 leaves 1 —
#                   and Y is attemptable again at four dots, which the
#                   previous tree could not manage at all
#
# Every repair to the field pushed this number up, and that is the
# measurement, not an inconvenience: the swim's licence is whatever the
# field of the day still cannot express, so the stimulus has to be
# re-derived whenever the field changes.  A tile that is never
# attempted never births a residue row — no rescue tier can be reached
# there, this one included — so the band has a ceiling as well as a
# floor, and 4.5 dots is inside both today.
#
# The in-register control is byte-identical to the two-dot pair's — the
# amplitude only touches the displaced render — and the sha below
# records that it is.
# RE-DERIVED 2026-09-04, 4.0 -> 4.5.  At 4.0 the re-keyed page left the
# field one tile short and tiles.local took it; the swim's marginal gain
# was zero.  At 4.5 the field alone loses the whole Y plane and the swim
# brings it back (200 -> 297; it mints 20 and opens 73 for local).  The
# per-row shift stays whole dots (peak 4, banker's rounding); the
# amplitude never was.  Record in test_h3_swim_existence.
# RE-DERIVED 2026-09-20, 4.5 -> 5.2, by the same principle and for the
# reason the principle exists: the page field merged 2026-09-12 and it
# rescues 4.5 dots outright — field alone 300/300, the swim's marginal
# gain zero, every pin below vacuous.  At 5.2 the field alone loses the
# whole Y plane again (200/300, zero Y, with retry, local and planek
# grinding 500, 700 and 700 jobs on it) and the swim brings 31 tiles
# back, 5 of its own minting and 26 through the planek sweep it
# unblocks.  The rounded per-row shift peaks at FIVE dots anywhere from
# 4.55 up; what the amplitude dials above that is how many rows sit at
# the peak — 91 of 1920 at 4.55, 275 at 5.0, 321 at 5.2 — and the roof
# is 5.24, the field estimator's reach plus one printed cell.  Ladder
# and the rung abandoned for wall in test_h3_swim_existence.
STEEP_AMPLITUDE_DOTS: float = 5.2
STEEP_TIFF_SHA256 = (
    "652e05e6160a868cd9aff4041d7abf40619ea440812fa20328db3e7f3eacd298")
EXPECTED_HARD_STEEP: dict[str, str] = {
    HARD_PAYLOAD_NAME: HARD_PAYLOAD_SHA256,
    CONTROL_TIFF_NAME: CONTROL_TIFF_SHA256,
    SHIFTED_TIFF_NAME: STEEP_TIFF_SHA256,
}
```


## 3. The field-yield pair's ledger

`src/holo/receiver/tests/test_h3_color_field_yield.py`. Five dated episodes of a
stimulus that rotted three times because the receiver got better, plus four
measured refusals (shape, evidence, starving the labels, an absolute offset)
that exist so nobody spends those afternoons again. Carried whole; the only
uncommitted change to it on 2026-09-20 was the cross-reference to the swim
module's new amplitude (`STEEP_AMPLITUDE_DOTS` = 5.2, 4.5 before it), which is
the version below.

```text

The plane field's reason to exist, end to end.

One emitted top-rung colour page, rendered twice: every plane in
register, and plane Y displaced along x by a rounded sinusoid (3 dots
peak, one full cycle down the page — the AltaLink's measured
Y-registration defect in miniature).  Both carry the same seeded noise,
so the difference between them is the displacement and nothing else.
`tiles.swim` is held out of all three decodes; the ruling and the
condition that expires it are the last two sections here.

THIS STIMULUS HAS NOW ROTTED THREE TIMES, EVERY TIME BECAUSE THE
RECEIVER GOT BETTER.  The rot looks the same each time: the displaced
page starts certifying everything the control does, `costs_certificates`
fails on its own "no longer exercises the mechanism" message, and the
field has nothing left to buy back.  WHEN THAT HAPPENS THE REPAIR IS TO
RE-HARDEN THE STIMULUS AND RE-PIN — never to loosen a pin, never to
delete the module.  What is protected here is the question, not the
numbers.

ONE RETIREMENT TO READ THE OLD EPISODES THROUGH (2026-09-08).  Episodes
2 to 4 below reason about the colour lane's own {1, y} per-plane
page-fraction residual — what it absorbs, and therefore which stimulus
shapes are attributable to the field.  That residual was RETIRED
2026-09-07 (W3a, invariant I7): the lane reads at the page field or at
its pose and carries no model of its own.  The episodes are kept as
written because they record decisions taken while it stood; where one
of them settles a stimulus question by what the residual would eat, the
question is open again against the page field, and the entry says so
where it matters (see the ABSOLUTE OFFSET paragraph in episode 4).

EPISODE 1, written 2026-08-30, 2-dot peak: dial off 284/300, the 16
losses all Y; dial on 300/300, byte-identical to the control.

EPISODE 2, 2026-08-31.  Same stimulus, dial off, 300/300 — nothing left
to buy, because `tiles.local`'s COLOUR arm had landed and minted ten
certificates it had never had the chance to mint here.  (The first
reading of that blamed `tiles.planek`, whose blind ±2.0-dot sampling
search matched the injected amplitude; `--drop` refuted it — planek
never fired at two dots.  A plausible mechanism that matches the
numbers is still a hypothesis; that one cost an afternoon.)  The repair
was HEIGHT: three dots, the first whole dot above planek's blind search
and above what the colour head's local re-fit absorbs.  Width was
measured in the same pass and rejected — widening the crests makes the
page EASIER, because a locally constant per-plane offset is exactly what
the head's own {1, y} residual eats.

EPISODE 3, 2026-08-31, hours later.  Three dots, dial off, every row
live: 300/300 AGAIN.  `tiles.swim` — the per-plane local-affine rescue —
landed after episode 2's re-pin and recovers this page unaided.
Measured on this tree at workers 1, `--complete`:

    dial off, every row live   300/300, ledger
                               {'tiles.local': 86, 'tiles.planek': 5,
                                'tiles.scan': 202, 'tiles.swim': 7}
                               against episode 2's
                               {'tiles.local': 84, 'tiles.planek': 1,
                                'tiles.scan': 202} — seven minted by the
                               new row and six more out of the frontier
                               it opened.  With the row in the schedule
                               the dial then buys nothing at all: 300
                               against 300, and `tiles.retry` fires 208
                               times with the field and 208 without.

AND THIS TIME THERE IS NO FOURTH DOT.  Episode 2's repair was to climb
one dot; episode 3 went looking for the next rung and measured that the
ladder has exactly one at c3.

WHY: `tiles.swim`'s translation bound is ONE PRINTED CELL measured from
the standing field's value (`swim.translation_bound_dots` is literally
`cell_dots_of(row)`).  This is a c3 page, so that bound is 3.000 dots —
EXACTLY the injected peak, and exactly a point on the search's own
coarse grid (`local_affine.COARSE_STEPS_PER_SIDE` = 2, so the first pass
evaluates ±bound and ±bound/2).  With the dial off the hint is zero and
the row searches ±3 dots around zero: the stimulus is inside its reach
with no margin at all.  The next whole dot up is
`test_h3_swim_existence`'s own stimulus (`STEEP_AMPLITUDE_DOTS` = 4.5
since the 2026-09-03 re-derivation),
where the field is the row that comes up short.  Four dots was measured
here anyway, with every row live, because a repair has to be rejected on
numbers: dial OFF the page loses the WHOLE Y plane (200/300, zero Y)
with NO rescue row firing at all — Y falls under the informative floor
and a rescue row can only help a tile the receiver still tries — and
dial ON it closes 300/300 with `tiles.swim` minting 23 of them.  So four
dots would satisfy the yield tests, and it is refused for three measured
reasons: the render is byte-identical to the swim module's own stimulus,
the dial-off arm exercises NO rescue row at all (a worse loss of
coexistence than holding one row out), and the close is the field's and
the swim's jointly, which is not this module's question.  The field's
usable band and the swim's blind band are the same band, one dot wide,
both ends are already taken, and the displacement is whole dots by
construction (`_h3_sims.plane_x_shift_dots` — a fractional shift would
have to be interpolated, and interpolation blurs the plane as well as
moving it, which is two changes at once).

FOUR OTHER DIRECTIONS WERE MEASURED AND ALL FAILED.  They are recorded
so nobody spends the afternoon again:

  SHAPE — the one that looked most promising, and the one CLOSED BY
  MEASURING THE OPERATORS THEMSELVES.  The standing proposal is
  curvature at the window scale: the field is a per-tile translation
  pooled over a two-tile Gaussian, the swim a six-parameter affine over
  a 200-cell window, and since a window is 3.125 tiles against a
  bandwidth of 2.0 the field's own resolution is FINER than the window —
  so a displacement curving inside one window ought to be the field's to
  express and not the affine's.  Run against the real
  `plane_field.solve_equations` and the real `geometry.window_starts` on this
  page at 3 dots (commit d86feab, "field-yield e3: the curvature
  direction, closed by measuring the operators"; the instrument runs in
  about a second and moves by itself if either operator is repaired):

      cycles   field response   field residual   affine residual
        0.5        0.915             0.96          0.38 max / 0.25 mean
        1.0        0.769             1.07          0.37 / 0.33
        1.5        0.718             1.70          0.92 / 0.55
        2.0        0.549             2.58          1.34 / 1.08
        3.0        0.309             3.14          1.83 / 1.21

  The affine's residual is the SMALLER one at every frequency and the
  gap WIDENS with frequency, and neither side is handicapped — the field
  gets ideal noiseless anchor-form equations, the affine gets the exact
  unbounded least-squares fit, so both halves are upper bounds for their
  own side.  Frequency is not free to choose either: a non-integer cycle
  count leaves the displacement a nonzero mean (1.932 dots at half a
  cycle, exactly 0 at 1, 2 and 3), and a mean is what the colour lane's
  own {1, y} page-fraction residual absorbs before any rescue tier is
  reached.  A separate model over the bounded affine and the clamped,
  bilinearly read-back field agrees shape for shape — sine 3 dots 1
  cycle field 1.05 / affine 0.46, 1.5 cycles 1.75 / 0.92, 2 cycles 2.54
  / 1.34, triangle 0.82 / 0.32, dither-rounded 1.03 / 0.51, 4 dots 2.00
  / 0.67 — the affine smaller on every shape and in every tile row.  It
  has to be: the field's advantage is pooled evidence and never
  resolution, and its ridge, clamp and bandwidth make it the coarser
  model.  Raising the frequency hurts the FIELD first, which is episode
  2's "height bites, width doesn't" seen from the other side.  DO NOT
  BUILD A CURVATURE STIMULUS.

  EVIDENCE — sensor noise, on the theory that six parameters fitted per
  window degrade faster than two per tile pooled over a page.  Measured,
  dial off, every row live, same 3-dot displacement: sd 12 -> 300/300,
  sd 24 -> 300/300, sd 36 -> 300/300.  Tripling the noise costs the
  displaced page NOTHING; the residue tier just works harder
  (`tiles.local` 298 -> 367 -> 376 fires).  The in-register control
  certifies 300/300 at sd 36 too, all of it on `tiles.scan`.  And the
  direction is BACKWARDS: at sd 24 the FIELD's own Y fit falls from the
  1.1-2.0 dots it reads at sd 12 to 0.52 and refuses to publish, while
  the page still closes off the residue tier.  The pooled estimator is
  the one that loses.

  STARVING THE ROW'S LABELS — the precondition-starving family, and the
  one architectural difference that really does separate the two rows:
  the swim's objective floor is PER WINDOW (`MIN_OBJECTIVE_CELLS` = 64
  proven cells, `MIN_LIVE_STATES` = 2, `MIN_STATE_CELLS` = 8 each) where
  the field's level table is fitted over the whole page's measuring
  pass.  Unreachable from a stimulus, and by a wide margin: this format
  lays 120 furniture cells per tile (100 word + 20 dust), a window
  covers 9.77 tiles, so a window carries about 1,172 address-derived
  proven cells — 18x the floor — before a single tile has certified.
  Furniture is a pure function of the address, `_swim_eligible` has no
  certified-neighbour clause on purpose, and working on furniture alone
  in a band where nothing has certified is the regime the row was built
  for.  Starving it means taking the INK away, which is a contrast
  problem rather than a registration one, and the field cannot fix that
  either.  (Starving the certified COLLAR does deny `tiles.local` and
  `tiles.planek`, which need certified neighbours — but not the row that
  is actually absorbing this stimulus.)

  AN ABSOLUTE OFFSET — a page-constant or {1, y} ramp on the displaced
  plane, to push the swim past its bound while the lane's own residual
  eats the extra.  Settled in the source without spending a decode:
  `color_region_anchor.features_at` reads each plane at exactly the
  offset it is handed and at nothing else (before 2026-09-07 the same
  door was `features_with_page_fraction`, which took an offsets override
  INSTEAD of the residual rather than on top of it — the conclusion here
  is the one that survived its retirement), and the field's own
  measurement is absolute from the committed pose —
  `fields_collect.measure_anchor` correlates the format's furniture
  where the format says it is and never at a standing field — so
  anything added to the absolute displacement is charged to the same
  budget the sinusoid is charged to, and the reach that budget runs out
  at is the estimator's (RE-POINTED 2026-09-07: this paragraph named the
  first pass's sampling at the standing field and a 2.0-dot clamp; both
  went with the publish gate and the normal-equation fitter, I8).

THE REPAIR, 2026-08-31: hold `tiles.swim` out of all three decodes
(`conftest.FIELD_YIELD_HELD_OUT`), and pin the hold-out to the constant
that forces it rather than leaving it a habit.

Dropping a row is the weakest repair available here — it stops testing
that row's coexistence with the field — so it is taken only for the ONE
row whose licence covers this stimulus completely, and only after the
alternatives above were measured rather than argued.  The other four
rescue rows stay in the schedule and keep working the page:
`tiles.retry`, `tiles.local`, `tiles.planek` and `refine.color` all fire
in both arms, `tiles.local` and `tiles.planek` mint in both, and their
exact counts are pinned below.  The whole-tier drop that `test_h3_plugins_local_ctx` uses would
also delete this module's second product, so the minimum is the right
cut.  This is the day's standing ruling applied, not a new one: "no
stimulus retains certificate headroom against the residue arms, measured
four independent ways" (conversion_docs/RULINGS-2026-08-31.md), and the
local-ctx repair of the same morning — re-scope to the measured truth,
and pin the restoration condition.

Held out, and measured at workers 1 (`--complete`) on this tree:

    in register, dial off      300/300 certificates, payload byte-exact,
                               all 300 minted by `tiles.scan`
    displaced,   dial off      287/300 — the 13 losses are ALL Y and
                               form one contiguous band: tile row 2
                               columns 6-9, and nine of tile row 3's ten
    displaced,   dial on       299/300 — twelve of the thirteen bought
                               back, no address the control did not
                               certify, and the one it misses is
                               Y (3, 0)

and the hold-out costs exactly that tile and nothing else: with
`tiles.swim` PUT BACK and the dial on, the same page closes 300/300 with
the row minting ONE certificate — Y (3, 0) — and every other count
identical (`tiles.local` 86 certificates from 369 fires either way,
`tiles.planek` 11 from 14).  So the row's whole marginal value here,
once the field is running, is the single tile the field leaves; with the
field OFF it is the entire stimulus.  That asymmetry is the ruling.

TWELVE OF THIRTEEN, not thirteen, and that changed with the anchortier
merge rather than with this stimulus.  The 2026-08-31 median-publication
ruling ("publish p - median(all three planes)") took the plane-COMMON
part out of what the field publishes, and on this page that common part
— ~0.97 dots of pose-versus-ink bias, visible on all three planes of the
clean sim — was doing most of the ordinary read's work.  Episode 2's
dial-on ledger had `tiles.scan` minting 288 of 300; on this tree it
mints 202, exactly what the dial-off run mints, and the field's whole
gain now arrives through the rows that RE-READ — `tiles.planek` 1 -> 11
and `tiles.local` 84 -> 86, which is the twelve, exactly.  The ruling is
right and stands; the price it
charged on this page had not been read by anything until now.  That is
also why the work pins below no longer collapse: the field converts
thirteen hopeless tiles into twelve rescuable ones, and each rescue pays
a full local head fit, so `tiles.local` and `refine.color` RISE with the
dial on while the two rows that undo a registration error blind —
`tiles.planek`'s ±2-dot search and plain `tiles.retry` — recede.

EPISODE 4, 2026-09-03, the page moved, not the receiver.  The
canonical-identity merge (b8471fc) made the canonical
id — which is the AES row seed — the explicit spelling, so the emitted
page re-keyed.  Nothing in src/holo/receiver/plugins changed.  Re-measured, all
three arms, same argv and hold-out:

    control 300, dial off 290, dial on 300.  The displacement costs
    TEN (all Y, floor 8), and the field buys back all ten — the
    dial-on page is the control's page exactly, so the shortfall
    above is now EMPTY and "twelve of thirteen" is ten of ten.
    Dial-off ledger {local 81, planek 9, scan 200} against episode
    3's {84, 1, 202}; dial-on {90, 10, 200}.  Rescue jobs keep the
    episode-3 shape: local 435 -> 513 and refine.color 470 -> 539
    rise with the dial, planek 67 -> 30 and retry 220 -> 210 recede.

EPISODE 5, 2026-09-07: the DIAL IS GONE and the arm came back as a
scheduling HOLD-OUT.  The page field is always on for a colour family
(design §2.8), so "dial off" is now the same argv with the field's two
rows dropped as well (`conftest.FIELD_ROWS_HELD_OUT`), which is the
instrument this module already used for `tiles.swim`.  Measured, three
decodes, workers 1, `--complete`:

    control 300/300, all `tiles.scan`
    displaced, field HELD OUT   290/300, {local 81, planek 9, scan 200}
    displaced, field running    300/300, {local 55, planek 20,
                                          retry 10, scan 215}

The displacement costs TEN and the field buys back all ten — the same
shape episode 4 measured through the dial, from an arm that no longer
needs one.  `tiles.retry` mints here for the first time in this module's
record (ten), which is what the ledger is for.

The stimulus still discriminates — the floor holds with margin — so this
is a re-measure of the same question, not a fourth rot and not a loosened
pin.  DIAL_ON_SHORTFALL stays a golden, at empty, so losing ground fails
as loudly as gaining it did; the case is renamed off the count.  The
edge tile the field could not reach was not "the field growing" — it is
a different tile on a re-drawn page.

WHAT WAS NOT DONE, deliberately: the overlap witness is not a fourth
decode.  `test_h3_plugins_local_ctx` keeps its substitution measured
with an extra arm; this lane cannot afford one, so the witness is the
episode-3 ledger recorded above — and it is the FIRST thing to
re-measure when this module next fails (done 2026-09-03, episode 4).

WHY THIS LANE: the degraded capture is the most expensive decode in the
tree — its rescue tiers grind for tens of minutes of CPU at workers 1
against a 140 s budget for the entire slow lane.  Three decodes cannot
live there.  Run it with

    HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1 \
        python -m pytest src/holo/receiver/tests/test_h3_color_field_yield.py -q

(1:04:25 on machine 4, 2026-09-07, three decodes serial).
`measure/h3_plane_fields.py` used to drive the same arms without pytest;
it was RETIRED at W6 with the pre-W2 fitter and the `--plane-fields`
dial it called.
```

Its measured constants, with the comment blocks that date every re-pin:

```python

DISPLACED_STREAM = "Y"
PLANE_STREAMS = ("C", "M", "Y")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
Y_PLANE = 2

# Every rescue row, named, including the two that fire zero times here —
# because a zero is a verdict.  `tiles.uplift` never fires on this page
# at all.  `tiles.planek` is named because episode 2 was lost to
# assuming it did the rescuing when at two dots it never fired either —
# at three it does, 56 times for one certificate.  `tiles.swim` is named
# because episode 3 HOLDS IT OUT (`conftest.FIELD_YIELD_HELD_OUT`), so
# its zero below is the hold-out itself, pinned as behaviour rather than
# as configuration.
RESCUE_ROWS = ("tiles.retry", "tiles.local", "tiles.uplift",
               "tiles.planek", "tiles.swim", "refine.color")

# The addresses the field cannot buy back on this page, pinned rather
# than tolerated.  If this set empties, the field has grown and the
# module should say so; if it grows, something has regressed.
#
# EMPTY since 2026-09-03 (episode 4): the field buys back all ten.
SHORTFALL_AGAINST_CONTROL: list[tuple[int, int, int, str]] = []

# The floor the re-hardened stimulus has to clear, on the arm that can
# LOSE: the same capture with the field's two rows held out
# (`conftest.FIELD_ROWS_HELD_OUT`).  A FLOOR, not a golden: the
# unfielded page may certify more than it did the day this was measured
# — that is the receiver getting better — but not so much more that the
# field has nothing left to buy back.  When it trips, the receiver has
# outgrown the stimulus a FOURTH time and the drill is in the module
# docstring, which records the four re-hardening directions already
# spent; start by reading those.
#
# RE-POINTED 2026-09-07 (episode 5).  It stood on the dial-off arm, and
# when the dial went the two tests that read it came to compute the SAME
# set — `len(control - displaced) >= 8` beside
# `control - displaced == []`, which cannot both hold and did not: the
# always-on field buys back everything and the floor failed at zero.
# The set the floor asks about is the one a receiver WITHOUT the field
# loses, so that is the arm it reads now.
MIN_LOST_TO_THE_DISPLACEMENT: int = 8

# What the band has to READ on the page whose Y plane was displaced by a
# 3-dot sinusoid.  A floor on the measurement, not a publish gate: the
# page field has no floor (I8), and this is the retired one's quarter
# dot kept as the scale at which a registration error starts costing
# cells — a band reading less than this on THIS page is reporting noise.
MIN_DISPLACED_MEDIAN_DOTS: float = 0.25

# EPISODE 5, 2026-09-07: the dial is gone.  The page field is always on
# for a colour family, so there is no second decode of the displaced
# capture to compare against — off-vs-on became control-vs-displaced,
# and what the three ledgers below pin is one displaced run's own work.
# The "what does the field buy" question now belongs to the superset
# proof W3 writes here (bar B7): the displaced page's certificate set
# against the in-register control's.

# WHICH ROWS MINT THIS PAGE'S CERTIFICATES — the pin episode 2 teaches.
# The module rotted silently because a row that had never minted a
# certificate here started minting ten, and nothing was reading the
# ledger; the yield tests only ever saw a total.  A row appearing,
# vanishing or moving in these tables is the loud version of that.  It
# is not a printed-format fork and not a number to quietly refresh: it
# is the signal to re-measure the stimulus and then decide whether it
# still discriminates at all.
#
# Re-measured 2026-09-03 (episode 4); the decision above was taken on
# evidence — the floor still holds — so this is the same question re-read.
# RE-MEASURED 2026-09-07 (episode 5, W3a: the one mapping, the residual
# model retired, the plane-as-K sweep unconditional).  The TOTAL is
# unmoved at 300 and the page still closes byte-exact; what moved is who
# mints: `tiles.local` 55 -> 78, `tiles.planek` 20 -> 6, `tiles.retry`
# 10 -> 1, `tiles.scan` 215 unchanged.  The ordinary read now carries
# the page field, so tiles that used to reach a rescue row are certified
# a rung earlier and the dear rows mint less.  W2 carried these two
# tables forward from the dial-on tree without running the lane; these
# are the first numbers measured on this tree.
# RE-PINNED 2026-09-09 off the W8 sweeps rerun (the re-derived solve, the
# solve row's retirement fixed): the same 300 certificates, 54 of them
# moved DOWN the ladder — `tiles.scan` 215 -> 269 and `tiles.local`
# 78 -> 25, `tiles.retry` 1 -> 0 — because the field the cheap rows read
# now stands earlier and closer to the injected truth (§5.1 of the
# plan: sheet I's four-capture amplitude 0.916x -> 0.955x).
# RE-PINNED 2026-09-12 off the W9 oracle run and a six-way in-process
# bisect (the lead's, plan W9): the same 300 certificates, nine of them
# moved DOWN the ladder — `tiles.scan` 269 -> 262, `tiles.planek` 6 -> 3,
# `tiles.local` 25 -> 34, `tiles.retry` 0 -> 1 — and the ONLY repair of
# the wave that moves them is R2, the robust loss iterated to its fixed
# point instead of three passes (reverting R2 alone restores both
# tables exactly; reverting R1, R5, R6 or R7 changes nothing).  The
# converged field still reads the injected band and the run still
# recovers the payload byte for byte (the tests above), so this is the
# specified estimator's rung distribution, not a yield change.
CERTIFICATES_BY_ROW: dict[str, int] = {
    "tiles.local": 34, "tiles.planek": 3, "tiles.retry": 1,
    "tiles.scan": 262}

# The field's SECOND product, which no test read until episode 2, and
# which episode 3 had to restate.  Until the median-publication ruling
# the dial COLLAPSED these counts (`tiles.local` 251 -> 20,
# `refine.color` 494 -> 44) because the field's plane-common part made
# the ordinary read succeed outright.  With that part no longer
# published, the field instead makes hopeless tiles RESCUABLE, so the
# rows that pay for a rescue rise and only the blind registration rows
# recede.  Same drill as above when these move: re-measure, then decide
# whether the stimulus still discriminates.
# Re-measured 2026-09-03 (episode 4); the shape described above is intact.
# RE-MEASURED 2026-09-07 (episode 5, W3a): every rescue row does LESS
# work for the same 300 certificates — `tiles.retry` 288 -> 265,
# `tiles.local` 482 -> 153, `tiles.planek` 83 -> 30 — and only
# `refine.color` rises, 419 -> 466, because a pose refit is what the
# field now makes worth trying.  `tiles.swim` stays 0: it is the
# hold-out.  Same drill as above when these move.
# RE-PINNED 2026-09-09 off the same W8 rerun: about half the rescue work
# for the same 300 certificates (retry 265 -> 135, local 153 -> 98,
# planek 30 -> 18, refine.color 466 -> 142) — the field made the cheap
# rows certify what the rescue rows used to.  `tiles.swim` stays 0, the
# hold-out.
# RE-PINNED 2026-09-12 off the same W9 run, R2 again by the bisect above:
# the rescue rows do MORE work for the same 300 (retry 135 -> 145, local
# 98 -> 105, refine.color 142 -> 184, planek unchanged at 18), the price
# of the nine tiles the scan rung no longer reads at first attempt.
RESCUE_JOBS: dict[str, int] = {
    "tiles.retry": 145, "tiles.local": 105, "tiles.uplift": 0,
```

## 4. The colour local-patch ledger

From `src/holo/receiver/tests/test_h3_plugins_local_ctx.py`, the whole colour
section header and its goldens, including the 2026-09-20 re-pin made that
morning (`tiles.local` 39 -> 34, `tiles.planek` 24 -> 25, yields unmoved),
which never reached a commit either. This is the ledger that says, in its own
words, that the numbers below stopped being an existence proof on 2026-09-07:
the ordinary colour lane reading through the page field recovers by itself the
nine C tiles that used to need a residue row.

```python

# --- the colour existence proof: one window's own plane geometry ------
#
# Colour has no separate context row: `color_region` fits the WHOLE head
# per lane and page — QDA class model, CMY8 detector calibration, the
# registration residuals, the feature divisor and the context matrix —
# and applies it to every window.  The colour patch capture gives window
# (0, 0) its own plane geometry: the R channel (the one cyan absorbs) is
# sampled 5 px = 0.83 cell off in x, with the window's own noise.  The
# region fits ONE residual per plane as a function of page-y, so a jump
# confined to one window is averaged away there; a fit over that window
# alone represents it exactly.  The gain is therefore expected to land
# on the C stream of the patch tiles, and it does.
#
# THE CLAIM WAS RE-SCOPED 2026-08-31, AND THE ROW IS NOT AT FAULT.
# What this proof asserted until then was EXCLUSIVE — "without this row
# the same tree stops three certificates short".  That is now false, and
# the honest repair is to stop asserting it rather than to keep failing
# on it.  Measured through `measure/h3_plane_fields.py --sim
# color-patch --drop` (that driver retired at W6), current main,
# workers 1, `--complete`:
#
#   every row live                     294 certs; tiles.local 15 fires,
#                                      6 certificates
#   `tiles.planek` dropped             294, BIT-IDENTICAL — planek does
#                                      not fire while local is present
#   `tiles.local` dropped alone        294, and `tiles.planek` fires 6
#                                      times and mints THE SAME 6
#   the WHOLE residue tier dropped     288 — C 92, the six are gone, no
#   (the control this module now uses) tier row fires, and NO OTHER row
#                                      has learned the rescue
#
# So `tiles.local` still earns its six certificates; what broke is the
# CONTROL.  `tiles.planek` (merged after these goldens were taken)
# substitutes for the row exactly, so `gained = on - off` went empty
# against a control that dropped `tiles.local` alone.
#
# THE EPISODES, dated:
#
#   written 2026-08-30   EXCLUSIVE claim: without `tiles.local` the same
#                        tree stops three certificates short.  True when
#                        written — it was the only row that could do
#                        this.
#   measured 2026-08-31  OVERLAP: `tiles.planek` merges, and on this
#                        capture it does the same job.  The exclusive
#                        claim is now FALSE, not merely unproven.
#   re-scoped 2026-08-31 TIER claim: the residue tier collectively earns
#                        these six certificates.  The control drops the
#                        whole tier (`conftest.COLOR_PATCH_RESIDUE_TIER`)
#                        and loses all six, so the claim is measured, not
#                        assumed.  What the row does INSIDE the tier is
#                        pinned separately and exactly: local mints the
#                        six, no other residue row fires while it is
#                        present, and planek covers for it precisely when
#                        it is dropped.
#
#   re-keyed 2026-09-03  THE FIRST TWO CLAUSES ABOVE NO LONGER HOLD:
#                        the b8471fc re-key made this page harder, and
#                        with every row present local mints six of the
#                        nine and planek three (C (0,2), (1,2), (2,2));
#                        planek fires 15 against local's 43, where it
#                        fired zero.  The TIER claim and the overlap
#                        case are untouched — the control still drops
#                        the whole tier and loses every gained address.
#                        Content, not mechanism.
#
# This weakens no truth.  The exclusivity that no longer exists stops
# being asserted; everything that IS true — the yield, the attribution,
# the overlap — is pinned harder than before.  If a re-hardened stimulus
# ever puts the rescue back out of planek's reach,
# `test_dropping_the_local_row_alone_only_hands_the_work_to_planek`
# fails and the exclusive claim can be restored deliberately.
#
# A stimulus outside planek's rescue family would be the other repair —
# planek does per-plane spectral isolation plus a blind +-2.0-dot
# x-shift search, so a REGISTRATION defect is exactly what it covers —
# but FIVE DIRECTIONS WERE MEASURED AND ALL FAILED (same instrument,
# all-rows-live, `tiles.local` certificates in brackets):
#
#   x-shift  8 px   285 certs, C 89   local fires 36 [0], planek 36 [0]
#   x-shift 11 px   273,       C 89   local 12 [0],      planek 12 [0]
#   y-shift  5 px   297               local 3 [0],       planek 3 [0]
#   y-shift  9 px   285,       C 89   local 36 [0],      planek 36 [0]
#   y-shift 13 px   288,       C 90   local 36 [0],      planek 36 [0]
#   smear  s=3 px   297               neither row arms at all
#   smear  s=5 px   297               neither row arms at all
#   smear  s=7 px   285,       C 89   local 45 [0],      planek 45 [0]
#
# Escalating the displacement does not move the rescue from planek to
# local: past about 6 dots the damaged tiles are lost to BOTH rows.
# Moving it to y leaves every row's family at once (planek searches x
# only, and the local head's registration fit does not recover y here
# either).  A directional smear — the shape the K proof above uses, and
# the one structurally outside both planek's translation family and
# uplift's photometric one — is either too weak to arm anything or
# strong enough to lose the tiles outright.  `tiles.local`'s COLOUR arm
# has a narrow rescue window on this stimulus family and the original
# 5 px x-shift is inside it; so, now, is planek.  A stimulus in local's
# window and out of planek's is still worth having — a colour analogue
# of the K patch's own local-context defect, at a magnitude between
# "arms nothing" and "loses the tile" — but it is a separate line, and
# the tier claim above does not wait on it.

# Re-measured 2026-08-31 against the TIER control.  The count of gained
# certificates is unchanged at six, but they are a DIFFERENT six: the
# old golden read three tile rows by two columns, and the receiver now
# earns two rows by three columns (four addresses overlap).  Both sets
# lie inside the patch window, which spans tiles 0-3 on each axis.
#
# RE-MEASURED AGAIN 2026-09-03 for the b8471fc re-key: 294 -> 280 with the
# tier, 288 -> 271 without; the nine are a strict superset of the old six
# (tile row 2 joins rows 0 and 1), all on the misregistered C plane inside
# the patch window; `off - on` empty.
#
# THE TIER'S GAIN WENT TO ZERO HERE, 2026-09-07 (W3a, the page field on
# the ordinary read; re-measured on that tree and ruled 2026-09-08).  The
# control moved 271 -> 280 and the tier arm did not move at all: the
# ordinary colour lane, now reading through the page field, recovers by
# itself the nine C tiles that used to need a residue row.  Nothing was
# lost — `off - on` is still empty — and the fires moved the way that
# story predicts (`tiles.local` 43 -> 39, `tiles.planek` 15 -> 24).
#
# RE-MEASURED 2026-09-20 on the merged page-field receiver, and only the
# FIRES moved: `tiles.local` 39 -> 34, `tiles.planek` 24 -> 25, against
# 280 with the tier and 280 without, `off - on` still empty and the gain
# still nothing.  Every yield fact this ledger turns on is where W3a left
# it.  Those W3a numbers were taken mid-line: W7 through W9 landed after
# them, and two of that wave's repairs are exactly what the residue rows
# arm against — the robust page solve now iterates to its own fixed point
# where it ran three passes, and `plane_k`'s admission tries the field,
# the pose, then the field's declared shifts (8b8d68f3).  Five fewer
# local arms and one more planek sweep on an unchanged page is what a
# different field looks like from here, and this lane is oracle-sweep
# gated, which is why that wave's own re-pins never reached it.  NOT
# bisected: the only plugin commits since the merge are the int16
# `local_cells_yx` (2026-09-13) and the row-derived dust count
# (2026-09-16), both carrying their own byte-identity proofs at this
# row's p120, and neither was re-run against this capture.
#
# So the numbers below are a MEASUREMENT, not an existence proof any
# more.  On THIS stimulus the residue tier has nothing only it can do,
# and the tier's existence proof is OWED on a harder page — a W6 item,
# and a costed one: it needs decodes of the hard pair, which no lane
# below the oracle sweeps runs.  The pins stay because a tier that
# starts gaining again here is exactly what the day this stimulus is
# re-derived looks like, and it must move a number rather than pass.
COLOR_PATCH_CERTIFIED = 280
COLOR_PATCH_CONTROL_CERTIFIED = 280
COLOR_PATCH_GAINED: tuple[tuple[int, int, int, str], ...] = ()
COLOR_PATCH_FIRES = 34

# The cross-row ledger this episode teaches.  The module never noticed
# planek arriving because nothing here read any row but `tiles.local`.
# This pin is the loud version: while the row under test is present, NO
# other residue row fires on this capture, so a new row that starts
# firing moves a number instead of silently taking the proof's
# certificates the moment the control drops one row.  Measured
# 2026-08-31 on current main at workers 1.
#
# A fires count cannot see who MINTS; the split is pinned by source in
# COLOR_PATCH_GAINED_BY_SOURCE below.
# RE-MEASURED 2026-09-07 (W3a): 43 -> 39 and 15 -> 24.  `tiles.planek`
# fires MORE and mints nothing, because the page field is now where its
# sweep starts and it always sweeps.  RE-MEASURED 2026-09-20 on the
# merged line: 39 -> 34 and 24 -> 25, same page, same yields — the
# ledger above says what moved the field under them.
COLOR_PATCH_RESIDUE_FIRES: dict[str, int] = {
    "tiles.local": 34, "tiles.planek": 25, "tiles.uplift": 0}
# who mints the tier's gain, by certificate source (2026-09-03; EMPTY
# since 2026-09-07 because there is no gain here to attribute)
COLOR_PATCH_GAINED_BY_SOURCE: dict[str, int] = {}
COLOR_PATCH_TILES = tuple((ty, tx) for ty in range(4) for tx in range(4))
```

## 5. The amplitude ladder measured on 2026-09-20

The last measurement these modules produced, and the reason section 2b exists.
Each arm is one serial `--complete` decode of the shifted render of the hard
pair at the named amplitude, the field always on; `fields` holds `tiles.swim`
out, `fields-swim` does not, `control` is the in-register render. Artefacts are
in this session's scratchpad under `ladder/a<amplitude>/`; the numbers below are
read off each run's own `report.json` and the driver's `summary.json`.

| rung | arm | certificates | C / M / Y | status | wall |
|---|---|---|---|---|---|
| 4.6 | fields | 292 | 100 / 100 / 92 | close open — killed at 03:28 | — |
| 4.65 | fields | 252 | 100 / 100 / 52 | close open — killed at 03:28 | — |
| 4.75 | fields | 240 | 100 / 100 / 40 | close open — killed at 03:28 | — |
| 5.0 | fields | 200 | 100 / 100 / 0 | VERIFIED byte-exact, Y lost entirely | — |
| 5.0 | fields-swim | — | — | not completed: abandoned at 105 min without a result, killed 2026-09-20 ~05:05 | >6,300 s |
| 5.2 | fields | 200 | 100 / 100 / 0 | VERIFIED byte-exact, Y lost entirely | 1,186.6 s |
| 5.2 | fields-swim | 231 | 100 / 100 / 31 | VERIFIED byte-exact — the swim buys 31 | 2,483.7 s |
| 5.2 | control | 300 | 100 / 100 / 100 | VERIFIED byte-exact | — |

Read it as the swim's licence, measured: at 5.2 dots the field alone loses the
whole displaced plane and grinds it — `tiles.local` 700 jobs, `tiles.planek`
700, `tiles.retry` 500, no Y certificate — and with the swim in the schedule 31
of those 100 tiles come back (`tiles.swim` 306 jobs, `tiles.local` 987,
`tiles.planek` 357, `tiles.retry` 181, `revisit` 46). A live but PARTIAL rescue,
and the payload is byte-exact on both arms because the fountain does not need
the Y plane. The three rungs at 4.6 to 4.75 were killed by their own builder at
03:28 once 5.0's field-only arm showed the plane lost there; they never closed,
so their counts are what stood at the kill and not a result.

## 6. What was deleted, and where it last lived

Everything below was carried by
`65dc78a9037b85d1ee0c699cb964193385a31874` (main, 2026-09-20) and, where
section 2b and section 4 say so, by uncommitted edits on top of it.

**Two modules, whole.** `test_h3_swim_existence.py` (412 lines, 10 tests) and
`test_h3_color_field_yield.py` (810 lines, 16 tests).

**54 tests in all**, by module: swim existence 10, field yield 16,
`test_h3_plugins_local_ctx.py` 13 (the whole colour section, plus the K
capture's constructor echo), `test_h3_degraded_sim.py` 4,
`test_h3_e2e_sims.py` 3, `test_h3_e2e_column_groups.py` 2,
`test_h3_e2e_rotations.py` 2, `test_h3_e2e_modes.py` 2,
`test_h3_e2e_p_axis.py` 1, `test_h3_plugins_calibrate_refine.py` 1. One test
was renamed rather than deleted: the degraded run's zero-wrong audit, which
now reads the printed page (`..._agrees_with_the_printed_page`) instead of a
second decode of the clean sim.

**Fourteen fixtures**, all of them whole-page colour decodes or their
stimuli: `sim_color_hard`, `sim_color_hard_steep`, `decode_hard_control`,
`decode_hard_shifted`, `decode_hard_shifted_unfielded`,
`decode_steep_control`, `decode_steep_fields`, `decode_steep_fields_swim`,
`sim_color_local_patch`, `decode_color_local_patch_w1`,
`decode_color_local_patch_off_w1`, `decode_color_local_patch_no_residue_w1`,
`decode_color_local_patch_w8`, and — found by the conventions gate, which
derives the published-fixture set from the conftest and refuses an
unreached one — `decode_color_w1_fields`, whose only consumer was the field
yield module and whose argv was `decode_color_w1`'s exactly.

**From the stimulus module** `_h3_sims.py`: `make_color_hard_steep_pair`,
`STEEP_AMPLITUDE_DOTS`, `STEEP_TIFF_SHA256`, `EXPECTED_HARD_STEEP`. What
STAYS, because `measure/local_ab/_sim.py` and `measure/h3_repricing.py` read
it and the hygiene gate proves they do: `make_color_hard`,
`render_hard_pair`, `make_color_hard_pair`, `capture_color_hard`,
`EXPECTED_HARD` with the two render digests, every `HARD_*` and `SHIFTED_*`
constant, the displacement shapes and `shift_plane_x`.

**Constants and helpers**: the colour patch's whole ledger
(`COLOR_PATCH_*`, 14 names across the conftest and the local-ctx module),
the two serial job tables (`K_SERIAL_JOB_COUNTS`,
`COLOR_SERIAL_JOB_COUNTS`) and the degraded run's (`JOB_COUNTS`, replaced by
the three per-row pins `REFINE_FIRES` / `RETRY_FIRES` / `LOCAL_FIRES`),
`NULL_WALL_BUDGET_S`, `NOT_PINNED_PENDING_D6`, `RESCUE_ROWS` in two modules,
and the field-yield ledgers `CERTIFICATES_BY_ROW`, `RESCUE_JOBS`,
`SHORTFALL_AGAINST_CONTROL`, `MIN_LOST_TO_THE_DISPLACEMENT`,
`MIN_DISPLACED_MEDIAN_DOTS` (all five verbatim in section 3).

**Claims retired with them**, in one line each, because a deleted assertion
should be nameable:

| claim | where it was |
|---|---|
| the swim certifies tiles the field cannot, and the plane is dead without it | swim existence, sections 2a/2b |
| the field buys back what a 3-dot displacement costs, row by row | field yield, section 3 |
| the residue tier collectively earns the colour patch's certificates (gain zero since 2026-09-07) | local-ctx colour section, section 4 |
| the six frozen sim renders reproduce their shas | five e2e modules — `_h3_fixture_build._materialise` verifies the same digests on both its paths |
| the K and colour serial runs' per-plugin job counts | e2e sims — re-pinned for intended changes each time, payload byte-exact throughout |
| the blank-paper null decode finishes inside 10 s | e2e modes — a wall pin whose session tripwire is retired |
| three constructor echoes: the degraded, K-patch and colour-patch captures are derived, not artefacts | degraded sim, local-ctx — each read back what the conftest had just constructed |
| the D6 deletion notes still name live symbols | calibrate/refine — thirteen fast-lane tests call `refine.certified_reach` outright |
| the K rotation witness parametrizes four frames; the witness fixtures are published | e2e rotations — the sha table's own pins moved into the raster test; `PUBLISHED_FIXTURES` is derived from the conftest now |

**Nothing else names these.** Two `measure/` instruments read the stimulus
(above). The retired names appear in records that stay as written:
`src/holo/receiver/docs/PAGE-FIELD-PLAN.md` (§323, §751, §1064, §1908 on
`COLOR_SERIAL_JOB_COUNTS`), `PAGE-FIELD-W8-CHARTER-2026-09-08.md`,
`SCHEDULE.md`, `SUITE-AUDIT-2026-09.md`, `DIAG-MERGE-NOTES.md`,
`conversion_docs/DIAG-REVIEW-FINDINGS.md`,
`conversion_docs/MEASUREMENTS-2026-08-31.md`,
`conversion_docs/tiles-pool-parked.patch`,
`retirement_docs-2026-09/{COMMENT-CARRY,DELETION-LOG,HOLO1-MAP}.md`,
`seeds/holo3-inventory.md`, `docs/PAGE-FIELD-DESIGN.md` and the two 2026-09
external reviews under `docs/reviews/`. They are dated records of what was
true when they were written; none of them is a pointer a reader can follow
to running code any more, and this file is where that code went.

## 7. What stays, and what the widened matrix is now

THE PATCH-BASED REGRESSION the ruling names is the K local-patch section of
`test_h3_plugins_local_ctx.py`: one window of the 49-tile K page given a
directional smear (5 px, the process-direction ISI) and its own noise at a
searched sd of 35, decoded three ways — `decode_k_local_patch_w1`,
`decode_k_local_patch_off_w1` (the row dropped) and
`decode_k_local_patch_w8`. Six tests hold it: the row fires
(`LOCAL_PATCH_FIRES` 7), its certificates are a strict superset of the same
tree without it, the control really ran without the row, the gain is the
decisive tile (48 with, 47 without, `LOCAL_PATCH_GAINED` (0, 2, 1) — and 48
is the metadata quorum, so the last certificate IS the volume), every
certificate carries the clean run's bits, and the row is deterministic at
eight workers. Seconds, not hours, and it fails loudly on a real change.

The `tiles.swim` and page-field rows keep their unit coverage —
`test_h3_plugins_swim.py`, `test_h3_field_*.py`, `test_h3_page_map.py` — and
the page field keeps its four frame decodes in `_h3_fixtures_field.py`. What
no longer exists anywhere is a whole-page colour proof that one residue row
buys certificates another cannot; that claim is now a measurement in this
file rather than a lane.

The widened matrix after this diet still runs: the serial clean colour
decode (`decode_color_w1`), the colour serial close at the source-symbol
rank, the mixed-capture pooled decode (`decode_k_mixed_w8`), the serial
`--complete` K harvest, the two widened colour rotations, the four
page-field frame decodes and the widened BCH and drift corpora.

MEASURED after the diet, on machine 1, 2026-09-20, one run each, cache warm:

| lane | command | before | after |
|---|---|---|---|
| widened matrix | `HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1 … -q` (`-n 8`) | 96 min | **398.4 s (6 min 38 s)**, 2,237 passed, 1 xfailed |
| slow lane | `HOLO3_RUN_SLOW_TESTS=1 … -q` (`-n 8`) | 107.8 s pinned, wall 140 s | 105.2 s, 2,203 passed, 34 skipped |
| fast lane | `… -q` (`-n 8`) | 15 s wall | 13.6 s, 1,929 passed, 308 skipped |

A fourteen-fold cut on the widened matrix, and the two cheaper lanes are
where they were. The first slow lane after this change cost 133 s rather
than 105: editing `_h3_sims.py` moves the content-keyed fixture cache key, so
every stimulus re-renders once — expected, and gone on the next run.

What is left at the top of the widened matrix is honest work, and its two
dearest rows are now SETUPS rather than calls: `test_h3_refine_guard`'s
colour refinement decode at 282 s and `decode_color_w1` at 267 s, each built
per xdist worker. If the matrix needs to come down again, that pair is where
to look, and the question to ask of them is this file's question — what does
the decode prove that a patch could not.

