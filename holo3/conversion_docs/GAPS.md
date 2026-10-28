# Where holo3 misses what the old receiver got — tile by tile

Forensic reading of archived runs only. **No decode was run for this
analysis**; nothing in `holo3/` was touched. Sources: the old receiver's
saved session files, and the event logs of the two holo3 harvest runs the
parity worker already produced (`../parity/run-5`, `run-3`, `run-4` and
`run-6`). Volume 7 (the pooled sheet-I volume) is not covered: its
harvest was still running and owns the machine, so its session file was
deliberately left unopened.

## Words used here

- **tile** — one 64x64-cell payload block. A page is a grid of them: the
  black-and-white sheet is 53 rows x 37 columns (1,961 tiles), the c3
  colour sheet 35 x 24 (840), and the two big colour sheets (volumes 4
  and 6) 52 x 36 (1,872). Addresses below are `(page, row, column)`, so
  column 0 is one extreme edge of the sheet and the highest column the
  other. On the three-plane CMY8 volume an address also names a colour
  plane (C, M or Y), each decoded on its own.
- **certificate** — a tile whose bits were recovered and passed their
  internal check. Certified tiles are the yield measure. Both runs
  compared here closed byte-exact to the same payload, so a disagreement
  between them is about *how many* tiles each recovered, never about
  what a recovered tile said.
- **level** (also "resolution rung") — both receivers read each sheet at
  four resolutions, from 2 pixels per printed cell up to the scan's full
  16 (black-and-white sheet) or 12 (colour sheet). Level 0 is the
  coarsest, level 3 the finest. **The two receivers build this ladder by
  the same rule**, so level numbers are directly comparable.
- **stage** — a decode attempt runs the error-correcting decoder with a
  budget of 60 passes ("scan" stage) or, on a second try, 150 passes
  ("retry-150"). A third stage, "union", only applies when several
  separate scans of one sheet are combined; **both runs here used a
  single scan, so no union attempt exists on either side**.
- **evidence floor** — before decoding, a tile needs a minimum number of
  actually-observed payload cells. On the black-and-white sheet that
  threshold is **2,780 of 3,996 payload cells** (measured from the format
  itself). Below it, no decoder runs and the attempt is recorded as
  "below floor".
- **refinement** — a second look in which the receiver re-fits a window's
  geometry using tiles it has *already* certified nearby, then re-reads
  the stubborn tiles through the corrected geometry. Both receivers have
  such a mechanism.
- **lineage** — the old receiver stamps each certificate with the list of
  certificates its evidence depended on. A non-empty list is a durable,
  exact record that **this tile was won by refinement**, and names the
  neighbours it leaned on.

## What each side can and cannot tell us

This shaped the whole analysis and bounds the answer to question (a).

**The old receiver does not keep per-attempt records.** Its own code says
so ("attempt history is not persisted") — attempts are folded into
totals at save time. It also **discards a tile's evidence once that tile
certifies**: the black-and-white session file retains evidence for
exactly 31 tile addresses, which are exactly its 31 failures. So for the
tiles we care about — the ones it *certified* — there is no stored record
of which level read them, and no evidence left to re-examine.

I checked whether the stored certificate identifier could be reversed to
recover the answer. It is a hash of (address, stage, decoder settings,
evidence-block identifiers), and every input is available *except* the
evidence-block identifiers, which are content hashes of evidence that was
deleted. Recomputation is therefore impossible without re-running a
decode, which is out of scope. **Per-tile level attribution for the old
receiver is not recoverable — stated as a limit, not guessed at.**

What the old receiver *does* record exactly: the stage totals for the
whole sheet, the refinement lineage of every certificate, and every
window placement with its level.

**holo3 records much more.** Its event log has one row per attempt
(stage, outcome, decoder passes), and the job entry written immediately
after each attempt names the job's level. Pairing the two recovers
`(level, stage, outcome)` for every attempt. The pairing was verified:
**7,218 attempts on the black-and-white sheet and 3,399 on the colour
sheet paired with zero mismatches, zero unpaired rows, and no attempt
left without a level**; the per-level certified counts sum exactly to the
run's certified total (1,924 and 786).

## The headline

**Both receivers fail in the same place, and the disagreement is small and
entirely inside that place.**

On the black-and-white sheet the old receiver fails 31 tiles and holo3
fails 37. **29 of those failures are the same tiles.** Both failure sets
sit almost entirely in two extreme columns:

| | column 0 | column 21 | column 34 | column 36 |
|---|---:|---:|---:|---:|
| old receiver fails | 28 | 1 | 0 | 2 |
| holo3 fails | 32 | 1 | 1 | 3 |

The eight "missing" tiles and the two holo3-only tiles are the fringe of
that shared hard edge, not a new failure region.

**Second, the mechanism that separates the two on this sheet is
refinement, and specifically *where* refinement got applied.** The old
receiver won only **18** of its 1,930 certificates by refinement — and
**all 18 are in column 0**. holo3 certified **13 of those 18 with no
refinement at all** (7 of the 13 at the finest level, against a
population where only 4.7% of certificates come from the finest level —
holo3 leans on resolution where the old receiver leaned on geometry). The
**5 it did not get are 5 of our 8 missing tiles**.

## Black-and-white sheet (step 5) — the eight missing tiles

`h1` = old receiver, `h3` = holo3. "decoded-failed@" lists the levels
where a decoder actually ran and failed; "floor@" the levels where
evidence was too thin for any decoder to run.

| tile (row,col) | h1 lineage | h3 attempts | h3 outcome by level | h3 refinement over this tile | reading |
|---|---|---:|---|---|---|
| (10, 0) | **refined**, from 14 certified neighbours in columns 1–2 | 53 (2 at retry-150) | decoded-failed @0,1,2,3 | none | decode loss; the rescue holo1 used never ran |
| (28, 0) | **refined**, from 9 neighbours in columns 1–2 | 43 | decoded-failed @1,2,3 | 4 jobs, 2 adopted | refined *and* still failed |
| (48, 0) | **refined**, from 10 neighbours in columns 0–2 | 53 (2 retry) | decoded-failed @0,1,2,3 | none | decode loss; rescue never ran |
| (49, 0) | **refined**, same 10 neighbours | 53 (2 retry) | decoded-failed @0,1,2,3 | none | decode loss; rescue never ran |
| (52, 0) | **refined**, from 9 neighbours in columns 0–2 | 43 | decoded-failed @1,2,3 | none | decode loss; rescue never ran |
| (34, 0) | not refined (ordinary read) | 53 (2 retry) | decoded-failed @0; **below floor @1,2,3** | none | **evidence starvation** at the fine levels |
| (23, 34) | not refined | 51 | decoded-failed @1,2,3; below floor @0 | 4 jobs, 2 adopted | refined and still failed |
| (24, 36) | not refined | 51 | decoded-failed @0,1,2,3; below floor @0 | 4 jobs, 2 adopted | refined and still failed |

Every one of the eight **had a committed window placement at every
level** — so "no covering placement at all" is ruled out for all eight.
The old receiver likewise had placements over all of them at all four
levels.

Stage attribution, exact on both sides but at different resolution:

- Old receiver, whole sheet: **1,929 of its 1,930 certificates came from
  the 60-pass stage; exactly one came from the 150-pass retry.** (Which
  tile that one was is not recoverable — see the limits section.)
- holo3, whole sheet: 1,909 from the 60-pass stage, **15 from the
  150-pass retry**. So holo3 is *more* reliant on the retry, not less.

### Why the refinement did not reach five of them

holo3's refinement ran **144 jobs and adopted 63 revised geometries** on
this sheet. Sorting those jobs by where they sat: **120 jobs (59
adopted) on the high-column edge, only 24 jobs (4 adopted) on the
column-0 edge**, and the column-0 ones cover only page rows ≈22–33.

Our missing column-0 tiles are at rows 10, 28, 34, 48, 49, 52. **Only row
28 falls inside the band holo3 refined.** For rows 10, 34, 48, 49 and 52,
**no refinement job covered the tile at all** — while the old receiver's
lineage shows it rescued rows 10, 48, 49 and 52 by exactly that
mechanism, re-fitting from certified neighbours one and two columns
inward.

That is the sharpest statement this analysis supports: *the difference at
four of the eight tiles is not that holo3's refinement failed, it is that
holo3's refinement never got scheduled there.* Why it wasn't scheduled is
**inference, not measurement** — the eligibility rule requires a minimum
of already-certified material inside the window, and each window is
refined once per distinct set of certified neighbours, so the ordering in
which the column certified could plausibly gate it. holo3's refinement
emits no events of its own, so the run log cannot settle the reason.

### The two tiles holo3 gained (one line each)

- **(4, 0)** — the old receiver kept evidence for it at all eight of its
  reading lanes (3,813–3,866 observed cells each, all far above the 2,780
  floor) and still never decoded it; holo3 certified it at the **finest**
  level after 26 failed attempts, in 10 decoder passes.
- **(7, 0)** — likewise evidence at all eight lanes (seven at
  3,809–3,921 cells, one at 2,047) and no decode; holo3 certified it at
  the **coarsest** level in 4 passes after 12 failed attempts.

Both are tiles the old receiver tried hard and lost, so they are genuine
gains rather than bookkeeping differences.

## Colour sheet (step 3) — the four missing tiles

Here the answer is clean and mechanical.

**All four missing tiles were won by the old receiver through
refinement** — their certificates carry lineage of 601–710 dependent
certificates each. On this sheet the old receiver leaned on refinement
heavily: **387 of its 720 certificates carry lineage.**

**holo3 ran zero refinement jobs on this sheet.** Its refinement is
gated to black-and-white pages in code (`prepare_refine` returns early
unless the family is K), and the event log confirms the consequence: 144
refinement jobs on the black-and-white sheet, **0 on the colour sheet.**

| tile (row,col) | h1 lineage | h3 attempts | h3 outcome by level | reading |
|---|---|---:|---|---|
| (6, 22) | refined (681 deps) | 39 | decoded-failed @0,1,2,3; below floor @0 | decoder ran and lost at every level |
| (12, 19) | refined (601) | 39 | decoded-failed @0,1,2,3 | same |
| (29, 22) | refined (681) | 39 | decoded-failed @0,1,2,3 | same |
| (31, 23) | refined (710) | 39 | decoded-failed @0,1,2,3 | same |

All four had committed placements at all four levels. Three of the four
sit in the two outermost columns.

**The nuance that keeps this honest:** holo3 certified **383 of the other
387 refinement-lineage tiles anyway, without any refinement**. So
refinement is plainly not *required* for that population — these four are
the residue where it appears to have been decisive. That the four
missing tiles are exactly the refinement-lineage tiles holo3 missed is a
measured fact; that refinement is the *cause* is **inference**.

**A second, independent colour difference — measured:** holo3 never ran
the 150-pass retry on this sheet (**0 retry attempts in 3,399**), while
the old receiver spent **1,527 retry attempts there and won 8
certificates from them**. On the black-and-white sheet holo3's retry
worked normally (933 attempts, 15 certificates) and I could watch it
switch off: retries begin at the second certificate and **stop
immediately after the certified count crosses the number of symbols the
volume needs to close** (1,356) — exactly what the code says, since the
retry is only armed while the close is not yet countable. On the colour
sheet the volume needs only 404 symbols of 840 tiles, so that threshold
arrives very early. Whether the four missing tiles would have survived a
retry is **not known** — no such attempt exists to inspect.

## Volume 6 — the colour uplift sheet (c2-cmy7), 22 missing / 49 extra

This is the sheet the old receiver's colour-uplift campaign closed as its
pre-registered "print-frozen" negative control, and the only volume whose
gap crosses 1% (1.41%). Both sides read **the same physical capture**
(the old session and the holo3 run name the same capture identity), and
both closed byte-exact to the same 686,859-byte payload.

**What the old receiver leaned on: refinement, overwhelmingly.** 808 of
its 1,559 certificates carry refinement lineage, and **20 of the 22
missing tiles do** — with very large dependency lists (751–1,544 named
certificates each; colour refinement on this sheet leans on nearly
everything already certified within reach). The two without lineage are
**(0,3,35) and (0,7,35)**, both in the outermost column.

**The supplemental-arm question, answered as far as the archive allows.**
The old receiver's lane plan for this sheet has 14 lanes, and the last
two are the campaign's supplemental arms — `u03-off` and **`u03-a3`**,
both at the finest resolution only. Measured about the a3 arm:

- It **ran, and ran broadly**: it left evidence on **305 of the 313
  tiles** still uncertified at the end.
- It is a **re-read, not a re-sampling**: its observed-cell count is
  **identical to the refined finest lane's on all 305 tiles** (and to the
  `off` arm's on all 305). It contributes different photometry over the
  same cells.
- It has **no placements of its own** — 0 of the session's 1,804 poses
  belong to a `u03-*` lane — so it rides the finest *refined* lane's
  geometry.

That last fact is what bounds the answer. **Every single refined-lane
pose on this sheet carries dependencies — 472 of 472, without
exception**, while every ordinary and mop-up pose carries none. So a
certificate produced from a3 evidence *must* carry refinement lineage.
Therefore:

- **(0,3,35) and (0,7,35) cannot be a3-arm tiles** — they carry no
  lineage, so they came from an ordinary read. They are plain decode
  losses for holo3.
- The other **20 are the class that could contain a3 tiles**, and within
  that class the archive **cannot separate an a3 certificate from an
  ordinary refined one**: certificates carry no lane marker, and the
  evidence of certified tiles is deleted. The campaign's own record puts
  a3's whole-sheet contribution at ~15 of 1,559 certificates, so **at
  most 15 of the 20 could be a3 tiles, and possibly none** — the arm was
  aimed at exactly this kind of residue, which is why the upper bound
  cannot be tightened by proportional reasoning. Anyone who needs the
  exact split has to instrument a re-run; it is not in the file.

So the requested three-way split, honestly stated: **2 plain decode
losses, 20 refinement rescues of which at most 15 could have been won by
the supplemental photometry arm, and 0 tiles that are provably a3.**

**What holo3 did there.** Uniform and unambiguous: each of the 22 was
attempted **46–48 times**, and the decoder **ran and failed at all four
resolutions** on 21 of them (the exception, (0,51,8), was below the
evidence floor at the coarsest level and failed at the other three).
holo3 ran **no refinement at all on this sheet** — its refinement is
gated to black-and-white pages, and the run log confirms zero refinement
jobs. It *did* run the 150-pass retry here (1,028 attempts, 4
certificates), and I could again watch the gate: the last retry fires at
924 certificates against a close that needs 920 — the retry switches off
exactly when the volume becomes countable, as designed.

**The 49 extras, one line:** holo3-only tiles cluster in the very same
hard columns as the misses (11 at column 2, 9 at column 17, 10 at column
30, 5 at column 34), spread over the full page height, and are won
mostly at the two middle resolutions (35 of 49) — the two receivers are
trading tiles inside one shared hard population, not covering different
sheets.

## Volume 4 — the first CMY8 volume (c2-cmy8), 36 missing / 88 extra

Three colour planes are decoded independently here, so an address is
`(tile, plane)`. The 36 misses are 16 C, 18 Y and only 2 M — and they
touch just **33 distinct tiles of 1,872**. Both runs closed byte-exact to
the same 718,413-byte payload; holo3 ends ahead overall (5,422 vs 5,370).

**The single most telling fact: every one of the 36 is a lost *plane* at
a tile whose other planes holo3 recovered** — 23 of the 36 sit at tiles
where holo3 certified both other planes, 13 where it certified one. There
is no tile here that holo3 failed to address, place, or read; it lost one
colour channel at a time.

**What the old receiver leaned on.** 1,774 of its 5,370 certificates
carry refinement lineage, and **33 of the 36 misses do** (dependency
lists of 3,588–5,331). The three without lineage are all Y-plane tiles in
the top two rows — (0,0,24), (0,0,25), (0,1,23).

**What holo3 did.** Every miss was attempted **43–44 times** with the
decoder **running and failing at all four resolutions**; only two tiles
touched the evidence floor at all, at the coarsest level only. As on the
other colour sheets, holo3 ran **zero refinement jobs**.

**A retry gap that is larger than the whole miss list — measured.** The
old receiver spent **4,593 retry evaluations on this volume and won 80
certificates** from them. holo3 ran **30 retry attempts in the entire
run and won none**, all of them inside the first 3,000 log events. This
is not the "the tile certified meanwhile" explanation: after holo3's last
retry, **8,118 further decode failures occurred on plane-addresses that
never certified**, and not one of them armed a retry. The only other gate
in the code is close-countability, so the readiness flag evidently went
true at about **102 certificates of an eventual 5,422** and stayed true,
switching the longer attempt off for the rest of the run. On the
black-and-white sheet and on volume 6 that same flag released correctly
(retries stop at 1,371 against a 1,356 close, and at 924 against 920), so
this looks specific to the three-stream case — **but the flag itself is
not written to the log, so which branch set it is inference, and worth
one instrumented check.** 80 certificates is more than twice this
volume's 36-tile gap.

**The 88 extras, one line:** evenly spread across the three planes (32 C,
29 M, 27 Y) and won mostly at the two coarsest resolutions (67 of 88),
which is the ordinary shape of this sheet's yield rather than a rescue of
anything special.

## Consistency with the earlier holo2 record

`holo2/docs/CATCHUP-PLAN.md` (~lines 300–560) studied this same
black-and-white sheet against the same old-receiver session. Our findings
line up with it and extend it:

- It reports the gap as column-concentrated, not diffuse, and names
  column 0 as the hard population — *"the certified-feedback registration
  rescue, where the oracle per-cell owner assignment still reads 7–16%
  BER and certifies 3 of 21"*. **Our result is the same story**: the
  column is legible enough to attempt everywhere (holo3's decoder ran at
  nearly every level of nearly every missing tile) but too noisy to
  decode, and the only thing that has ever rescued parts of it is
  geometry re-fitted from certified neighbours.
- It names the three tiles holo2 certified that the old receiver could
  not: (0,5,21), (0,7,0), (0,27,36). **All three are in the old
  receiver's failure list here, confirming we are reading the same
  baseline sheet and state.** holo3 also certifies (0,7,0); it does not
  get (0,5,21) or (0,27,36), and it does get **(0,4,0)**, which that
  record does not name.
- Scale, for context only (cross-document, not re-measured by me): that
  record's holo2 gap on this sheet was 48 tiles, reduced to 19 after two
  fixes. **holo3's gap is 8.**

Nothing here contradicts the earlier record. The one genuinely new thing
is the *scheduling* observation — that holo3's refinement is 5:1 skewed
to the opposite edge and never covered four of the tiles the old receiver
rescued — plus the colour-sheet facts (no refinement, no retry) which
that record does not cover.

## What I did not measure

- **Which level the old receiver used on any individual tile.** Not
  recoverable from the archives, for the reasons in the limits section.
  Only the sheet-wide stage split is exact.
- **Which tile earned the old receiver's single 150-pass certificate**
  (black-and-white) or its eight (colour). Same reason.
- **Evidence quantity at the missing tiles, compared side by side.** The
  old receiver deleted the evidence when it certified them, and holo3's
  event log records the decoder's pass count but not its
  informative-cell count. The observed-cell figures quoted above are from
  tiles in the old receiver's *failure* residue, where evidence survives.
- **Why holo3's refinement was not scheduled** at the five column-0 rows.
  Its refinement writes no events; the code's eligibility and
  once-per-neighbour-set rules are a plausible explanation and are
  labelled as inference throughout.
- **Which of volume 6's 22 misses the supplemental photometry arm won.**
  Bounded (at most 15 sheet-wide, and 2 of the 22 excluded outright) but
  not resolved — see that section. Certificates carry no lane marker.
- **Why holo3's close-readiness flag went true early on volume 4.** The
  flag is not written to the event log and a skipped retry emits nothing,
  so the branch that set it is inference. The *consequence* — 30 retry
  attempts where the old receiver ran 4,593 and won 80 certificates — is
  measured.
- **Volume 7** (the pooled sheet-I volume). Its harvest was still running
  and owns the machine; its 3.5 GB session file was deliberately not
  opened, so no gap tiles exist to attribute there yet.

## Summary for the project owner

On the black-and-white Xerox sheet the two receivers are nearly
indistinguishable: they fail 29 of the same tiles, both almost entirely
in the sheet's two extreme columns, and the whole disagreement is eight
tiles the old receiver got and two it did not. Of those eight, five sit
in the hard left-hand column and the old receiver won four of them by a
specific trick — re-fitting the window's geometry from tiles it had
already certified one and two columns inward, then re-reading. holo3 has
that same trick and used it 144 times on this sheet, but it spent 120 of
those attempts on the opposite edge and only 24 on the hard column, never
touching four of the five rows in question; where it *did* apply it, the
tile still failed. A sixth tile failed differently — holo3's fine-level
windows gave it too few readable cells to even start decoding — and the
last two are opposite-edge tiles where holo3 refined and lost anyway.
Meanwhile holo3 rescued two tiles in that column the old receiver never
cracked.

Across all four colour volumes the story converges on **one switch and
one flag.** The switch: holo3's geometry-refinement pass — re-fitting a
window from tiles already certified around it — **is off for colour
pages**, gated to black-and-white in code, and the run logs confirm zero
refinement jobs on every colour volume. The old receiver depended on it
heavily there (about half its certificates on two of the sheets carry
refinement lineage), and **essentially every colour tile holo3 misses is
one the old receiver won that way**: all 4 on the c3 sheet, 20 of 22 on
the uplift sheet, 33 of 36 on the CMY8 sheet. The remainder are ordinary
decode losses at the sheet edges. On the uplift sheet the campaign's
extra photometry arm is a plausible contributor too, but the archive
cannot name its tiles — I could prove only that two of the 22 are *not*
its work and that at most 15 of the sheet's 1,559 certificates ever were.
The flag: holo3's "second, longer decode attempt" is armed only until the
volume has gathered enough tiles to close, and on the CMY8 volume that
flag went true after about 102 certificates of an eventual 5,422 —
switching the longer attempt off almost immediately. It ran 30 such
attempts where the old receiver ran 4,593 and won 80 certificates from
them, which is more than twice that volume's whole gap. On the other
three volumes the same flag released at the right moment, so this looks
specific to the three-plane case and deserves one instrumented check.

None of this is a correctness problem: all four volumes came back
byte-exact, and holo3 finishes **ahead on every colour volume** (786 vs
720, 1,586 vs 1,559, 5,422 vs 5,370) and just behind on the
black-and-white sheet (1,924 vs 1,930). Both receivers fail in the same
places and trade tiles inside those same hard columns. The
actionable list is short and concrete: turn on colour refinement, aim the
black-and-white refinement at the column that actually needs it, and
check why the close-readiness flag fires early on three-plane volumes.
