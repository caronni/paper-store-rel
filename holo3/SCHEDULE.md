# holo3 — the global scheduling table

One row per plugin descriptor (frozen `PluginDescriptor` instance at the
bottom of its plugin module; `holo3/plugins/place_sched.py` is the place
plugin's scheduling half, split under the 1000-line law). The engine
imports the tuple in `holo3/engine.py:DESCRIPTORS` and knows nothing else
about any plugin: births come from `born_by`+`subjects_of`, wakes are
version bumps through the inverted FactKey index built from `reads`,
fire = retire -> version floor -> eligible -> prepare. The close is NOT a
row: it stays engine-held with its two gates (count_ready consult
mid-run, exhaustion under `--complete`). Work knows only "always"
(the v2 recipe gate law).

The block below is GENERATED — reprint it with `python -m holo3 schedule
[--format REF]` and paste it back; a golden test fails when the two
disagree. Nothing in it is hand-maintained prose: the rows come from the
descriptors, the reads column from each row's `reads` function read
against the closed key vocabulary in `holo3/descriptor.py`, the written-by
column from the store folds that type each fact, and the ladder from the
price literals each plugin declares (D6 addendum 10). The engine owns
no numbers at all — cost is a scheduling function of the plugins alone;
same-price rows are deliberate round-robin peers.

The engine hands `cost(store, subject, stage, attempts, last_cost)` two
pieces of accounting as DATA and interprets neither: `attempts` is the
bookmark's fire ordinal so far, `last_cost` the price this worker was
last pushed at. A row that wants its re-runs to grow more expensive
prices them itself — the escalation door, opened by the 2026-08-29 night
rulings. A row whose re-runs are not all the same KIND of work keeps its
own ordinal in the store instead of pricing off `attempts` (the colour
lane, below). A `*n` in the ladder is derived, not asserted: the table
reads the row's own cost function and marks the declared price it
multiplies by an ordinal — the engine's argument, or a local name the row
binds from a read on its own store.

```
descriptor rows (17)
name              subject    born by                          produces                                           reads
----------------  ---------  -------------------------------  -------------------------------------------------  ------------------------------------------------------------------------------------
survey            capture    Capture                          CaptureSurvey                                      —
place             window     Window                           Placement|LatticeSeed|PlaceOutcome                 lattice_seed, live_pages, pose_affine
calibrate         window     Placement                        WindowEvidence                                     pose_affine, region_pitch
ctx               region     WindowEvidence                   CtxOutcome                                         evidence_fit
color             lane       Placement                        ColorEvidenceRow|ColorCtxPopulation|ColorLaneFit   lane_poses, page_certs, plane_field, pooled_ctx
color.pooled_ctx  page_rung  ColorCtxPopulation               PooledColorCtx                                     color_pop
tiles.scan        tile       WindowEvidence|ColorEvidenceRow  AttemptFact|Certificate                            color_row, evidence_fit, evidence_read
tiles.union       tile       WindowEvidence|ColorEvidenceRow  AttemptFact|Certificate                            color_row, evidence_fit, evidence_read
tiles.retry       tile       AttemptFact                      AttemptFact|Certificate                            color_row, evidence_fit, evidence_read
tiles.local       tile       AttemptFact                      AttemptFact|Certificate                            color_row, evidence_fit, evidence_read, tile
fields            lane       Certificate                      PlaneField                                         lane_poses, page_certs
refine            window     Placement                        RefineOutcome                                      evidence_fit, evidence_read, pose_affine, pose_route, tile
refine.color      window     Placement                        RefineOutcome                                      plane_field, pose_affine, pose_route, tile
revisit           window     Certificate                      WindowEvidence|Placement|LatticeSeed|PlaceOutcome  evidence_fit, evidence_read, lane_poses, pose_affine, region_ctx, region_pitch, tile
tiles.uplift      lane       AttemptFact                      AttemptFact|Certificate                            lane_poses, page_certs
tiles.planek      tile       AttemptFact                      AttemptFact|Certificate                            color_row, plane_field, tile
tiles.swim        tile       AttemptFact                      AttemptFact|Certificate                            color_row, lane_poses, plane_field, tile

price ladder (plugin literals, cheapest first; * = same-price peers; *n = the row re-prices by its own ordinal)
     10  survey           survey
     15  calibrate        calibrate    *
     15  color            calibrate    *
     15  ctx              calibrate    *
     20  tiles.retry      payload      *
     20  tiles.scan       payload      *
     20  tiles.union      payload      *
     40  place            ring
     60  place            word_centre
     80  place            word_rest
    120  place            wide
  160*n  color            color_refit
  170*n  color.pooled_ctx pooled_ctx
  180*n  fields           fields
    200  refine           refine       *
    200  refine.color     refine       *
    200  revisit          refine       *
  210*n  tiles.uplift     uplift_a3
    220  tiles.local      local        *
  220*n  tiles.uplift     uplift_a4b   *
  230*n  tiles.planek     planek
  240*n  tiles.swim       swim
    250  place            cold_live
    260  place            cold_rest

key families (16)
family         written by (fact)                       read by (row)
-------------  --------------------------------------  ---------------------------------------------------------------------------
pose_affine    Placement, RefineOutcome                place, calibrate, refine, refine.color, revisit
pose_route     Placement, RefineOutcome                refine, refine.color
place_stage    PlaceOutcome, Placement, RefineOutcome  —
evidence_fit   CtxOutcome, WindowEvidence              ctx, tiles.scan, tiles.union, tiles.retry, tiles.local, refine, revisit
evidence_read  CtxOutcome, WindowEvidence              tiles.scan, tiles.union, tiles.retry, tiles.local, refine, revisit
color_row      ColorEvidenceRow                        tiles.scan, tiles.union, tiles.retry, tiles.local, tiles.planek, tiles.swim
color_pop      ColorCtxPopulation                      color.pooled_ctx
pooled_ctx     PooledColorCtx                          color
region_pitch   Placement, RefineOutcome                calibrate, revisit
region_ctx     CtxOutcome                              revisit
lattice_seed   LatticeSeed                             place
lane_poses     Placement, RefineOutcome                color, fields, revisit, tiles.uplift, tiles.swim
page_certs     Certificate                             color, fields, tiles.uplift
tile           Certificate                             tiles.local, refine, refine.color, revisit, tiles.planek, tiles.swim
live_pages     Placement, RefineOutcome                place
plane_field    PlaneField                              color, refine.color, tiles.planek, tiles.swim
```

Debt rows carried in this build (rulings 2026-08-29):

- `refine` re-arm widening: it subscribes to the certified tiles in its
  reach, both halves of its own evidence and its own pose, so any change
  to those re-fires it — including a first chance arriving late (Wave 1
  deleted the attempt digest; the version floor is the whole story).
  A revised placement refines again only when its certified reach
  strictly outgrows the adopted revision's basis (the gated lift).
- `refine.color` (the colour lane, v1's `color_refine` numerics
  verbatim): labels = per-plane presence bits — furniture (word/dust)
  contributes all three planes, certified cargo the planes its
  certificates reconstruct; the fit is K's two-stage grid on a frozen
  per-plane affine calibration minted from the baseline pose; the gate
  is held-out improvement plus the furniture non-regression (slack
  1e-9). It subscribes per stream to the certified tiles in its reach
  and to its own pose; the two v1 crop-free pre-gates (no certified
  cargo / certified-complete) refuse before any pixel read. An adopted
  revision folds as a Placement with route `refine`, which re-fires
  the whole colour lane (color -> ColorEvidenceRow -> tiles.scan)
  through the ordinary declared reads — no bespoke wiring.
- `revisit` (the mop-up row): a calibration-refused window re-fires the
  calibrate body, a never-placed window re-fires a ring-stage place
  pass, when certificates land in reach or the region ctx changes —
  v1's M-pass as a subscription instead of a phase.
- `tiles.uplift` (the supplemental residue row, RECEIVE-DESIGN §6.2a):
  v1's two u-lane ARMS, scheduled rather than gated. A3 re-fits
  per-window photometric gain/offset maps toward the region QDA's class
  means; A4b restricts a plane's marginal to the states its CERTIFIED
  sibling planes allow. Born from a failed tile, subject = the
  lane-page (both arms fit at REGION scale, so a per-tile subject would
  pay one region derivation per residue tile for an identical result),
  eligible while the page carries an uncertified residue — A4b
  additionally only on tiles that keep a certified sibling, and never
  for a single-stream coding, which has nothing to condition on. The
  correction is TRANSIENT: it is re-derived in memory, used for the
  decoder input, attempted at the heavy 150-iteration budget through
  the unchanged codec, and discarded. No `ColorEvidenceRow` is written
  and no standing cell is touched, so the row is purely additive and
  monotone by construction — it only ever attempts addresses that carry
  no certificate. It prices itself at 210 (a3) and 220 (a4b) by its own
  fire ordinal, so a row woken again and again by a growing frontier
  drifts behind cheaper work. No adoption gate, no applicability floor;
  the zero-wrong audit is the only bar. On both sims it fires ZERO
  times — its price puts it last and by then the page is done, which is
  the designed behaviour; its yield case is the real-sheet residue.
- `color` assembly vs re-fit: the lane does two different kinds of work
  and prices them apart. ASSEMBLY — first evidence for placed windows
  the lane has never covered — always costs 15 + the rung premium,
  however many times it happens, because it is first work and belongs
  ahead of cold placement, not behind it. It applies the STANDING head
  to the debt windows and fits nothing (so it publishes no context
  population and weighs no pooled head: both belong to the fit, and
  every fit still does them). A RE-FIT — the lane settled, every placed
  window covered, and evidence, certificates, plane fields or the
  pooled head moved — pays 160 x the number of head fits the lane has
  actually performed (160, 320, 480 …) plus the rung premium. The
  colour context head fits on every label the region owns — the
  40,000-label subsample is gone (ruling 2026-08-29 night; K's context
  was never capped) — so a re-fit is a real and growing cost, and a lane
  woken again and again drifts behind cheaper work instead of thrashing
  at a flat price. The ordinal is a store cell the fold maintains, never
  the bookmark's fire count: assembly fires are fires, and pricing off
  `attempts` charged the escalation for fits that were never performed,
  which is what starved colour payload work until placement was
  exhausted (defect fixed 2026-08-30). Nothing caps the lane: it may
  re-fit as often as new evidence justifies, it simply queues later
  each time.
- `color.pooled_ctx` (the first supplemental colour arm, branch
  `holo3-ctxmatrix`): one printed page seen by several captures is one
  channel seen several times, so the per-(state, plane) context matrix
  is fitted ONCE from every capture's labels for that page at that rung
  and offered to each lane as a candidate. Subject = (page, ppc); born
  only when a SECOND capture publishes a context population for the
  same page and rung, so a single-capture run never has the row at all.
  Price 170 x its own fire ordinal — above the payload band, below
  refinement. Each lane adopts the pooled head only if it beats that
  lane's own head on that lane's own held-out labels under the standing
  three-way gate (total strictly better, neither furniture leg worse),
  so a pooled fit that does not help is a no-op, never a worse head;
  the pooled cell itself is a decision cell the store gatekeeps by
  `data.pooled_ctx_ordinal` (adopted > refused, then lanes, then rows,
  then loss). Bins are NOT pooled — the ink map has to describe THAT
  capture's optics (INDEPENDENT-PLANES §2.12 (g), a three-capture
  consensus column measured worse than one capture's own) — and no
  pooled curve is fitted on a row any contributing lane holds out.

Additive residue rows (the toolbox doctrine, docs/TOOLBOX-INVENTORY §1):

- `tiles.local` (the local-head row, price 220): it re-fits, over the
  windows that cover ONE failed tile, whatever the standing receiver
  fits region-wide, and re-reads that tile alone under the result at
  the heavy 150-iteration budget. Two arms, one row.
  K ARM: the standing `ctx` row fits ONE nine-bin neighbour-count
  correction per REGION and applies it everywhere; this arm fits the
  same correction over the covering windows alone, on labels those
  windows can prove — the format's own word and filler bits plus the
  cargo cells that certified NEIGHBOURING tiles re-encode (`refine`'s
  label provenance, verbatim).
  COLOUR ARM: colour has no separate context row. `color_region` fits
  the WHOLE head per lane and page in one job — QDA class model, the
  CMY8 detector calibration or the CMY7 head, the registration
  residuals, the feature divisor and the state x plane x bin context
  matrix — and applies it to every window on the page. So for colour
  the region-wide object is the entire head, and this arm runs that
  same job (verbatim numerics, verbatim gates) over the covering
  windows alone. That is literally what a crop does, which makes it
  the bigger lever of the two.
  Both fits are TRANSIENT: built in the job, feeding one decoder input,
  then discarded. Neither folds a WindowEvidence or a ColorEvidenceRow,
  neither touches the standing region ctx cell, and neither displaces
  the attempt the ordinary rows make; the codec gate is the same LDPC
  syndrome + CRC + ground-truth-bound identity, so the row can only
  add. Eligibility is structural, never a bar: uncertified + covered by
  evidence + at least one certified tile in the neighbourhood (ONE
  certified stream is enough — K has only one, and a colour tile with
  two of three planes certified still projects those two as known
  cells). With no certified neighbour there are no extra labels, so
  there is nothing for the row to do. The neighbourhood is not a chosen
  radius: it is exactly the tiles the covering windows cover, read from
  the store's own evidence reach and colour-row cover (the window grid
  bounds that at ⌈(WINDOW_CELLS−1)/TILE_CELLS⌉ = 4 tiles). It
  subscribes to both halves of every covering window's evidence, to
  every covering colour row, and to every certificate in that
  neighbourhood, so new evidence, a re-fitted colour lane or a new
  certified neighbour re-fires it through the ordinary version floor.
  Price 220 = it pays a calibrate-class fit (15) and a payload attempt
  (20) on top of a pose the refinement rows at 200 may still move under
  it, so it queues behind all of them. Its yield case is the
  crop-parity residue on real sheets, not the sims.
  MEASURED PRIOR, carried deliberately: on K, the neighbouring arm that
  re-fits the per-window MARGINAL head locally is a measured negative —
  zero certificates over e029's complete 21-tile residue at both lanes,
  with page-global beating every halo (docs/TOOLBOX-INVENTORY §6.13).
  What paid there was dense certified labels, not locality; the K arm
  carries those labels into the one fit that is still region-wide.
  Colour is the opposite case and the record says so: the per-window
  photometric map (§6.5, A3) measured +46 certificates on hp c3-cmy8
  and +6/+7 as a supplemental lane, because colour's class model IS
  region-wide and a window's own photometry is not the region's.

The `fields` row (dial `--plane-fields`, DEFAULT OFF) is the third
generation of the plane-fields line: one per-plane registration-delta
field per colour lane-page, fitted from the page's own format truth
(every word/dust site of an addressed tile, plus the payload cells of
tiles certified in all three streams) by a locally weighted least-squares
solve on photometric normal equations, smoothed in tile space and ridged
to zero where no evidence reaches. The cell is quality-ordered —
`(n_certificates, −residual)`, the mutator gatekeeps, a worse re-fit is a
no-op — and the row prices its own re-fits at 180 x fire ordinal because
it subscribes to every certificate on its page. Readers are the colour
lane and `refine.color`, through the standing cell at fire time; the
field only moves WHERE those two sample, and the colour stack's own
held-out gate still decides whether the corrected features are adopted,
so a bad field costs nothing but the fit. With the dial off no worker is
ever born and nothing writes the family: the run is byte-identical.

- `tiles.swim` (the per-plane local-affine rescue, price 240 x its own
  fire ordinal, COLOUR ONLY) is where that field stops. Even speaking
  honest dots the field is a smoothed TRANSLATION statistic — one delta
  per tile, pooled over a two-tile Gaussian, LINEARISED around the
  incumbent with half-dot probes, ridged toward zero, clamped at 2.0
  dots and published only above its own quarter-dot floor — so it
  cannot express a displacement past its clamp, cannot follow structure
  sharper than its bandwidth, and answers exactly zero where evidence is
  thin. Over the windows covering ONE failed tile this row searches, per
  plane, for the full local affine in printed dots — translation plus
  the four linear terms, `d(u) = t + M u` on the window's normalised
  coordinates — that maximises the likelihood of the cells the receiver
  can PROVE. No linearisation (direct search on the objective itself),
  no shrinkage, no smoothing, no publication floor; the search is seeded
  from the standing field's own value at that window and the result
  re-reads that one tile at the heavy budget through the unchanged
  codec.
  THE OBJECTIVE is the profile Gaussian log-likelihood with the
  photometry concentrated out: `l = −(n/2) log(1 − eta^2)`, eta the
  correlation ratio of the sampled channel against the PRINTED STATE of
  each cell, with one free level per state re-fitted at every candidate.
  Re-fitted, not frozen: a level table fixed at the starting pose is a
  target the starting pose matches by construction, and the search
  would refuse to leave it.
  THE LABELS are the design. Every cell in the objective is proven
  before the search starts — the format's own word and dust furniture,
  whose three plane bits are a function of the address, plus the cargo
  of NEIGHBOURING tiles whose certificates re-encode through the
  printed format. The target tile's own cargo, the bits the correction
  will be judged by, takes no part. That is the difference from the
  blind loop INDEPENDENT-PLANES section 2.12 measured: feeding the
  decoder's own decisions back reached 44% of the oracle at best, lost
  half of that on the second iteration and certified nothing; this
  objective has no fixed point to chase and the row searches once.
  Furniture alone is enough, so the row works in a dead band where
  nothing has ever certified — which is exactly why its eligibility
  carries NO certified-neighbour clause where `tiles.local` does:
  uncertified, colour, covered by a placed colour window.
  TRANSIENT and monotone, on the same law as `tiles.local` and
  `tiles.uplift`: the affines are built in the job, reach the head
  through the position-based `offsets_of` seam (handed the head's own
  rows, so an offset can never misalign), feed one attempt and are
  discarded; the row emits only `AttemptFact` and `Certificate`, a
  plane the search refuses is read at exactly the offsets the standing
  lane would have used, and the zero-wrong audit is the only bar.
  THE BOUND is derived, not chosen: one printed CELL of translation
  measured FROM the hint (half of it for the linear terms at the window
  edge), because past a cell a plane's ink is in the NEXT cell — an
  addressing question the pose rows own — and the format's pseudorandom
  cell states make a whole-cell slip score near zero rather than
  compete. The search resolves to a quarter of a capture pixel. Price
  240 because it does everything `tiles.local`'s colour arm does at 220
  and adds a raster search in front of it; the ordinal escalates because
  a growing certified frontier re-arms the row with more labels.
  MEASURED 2026-08-31 on the three-tier tree
  (`test_h3_swim_existence`, three decodes of one emitted page with
  plane Y displaced by a FOUR-dot sinusoid — past the pose search's
  quarter cell, past the field's 2.0-dot clamp, and past what its
  linearised probes can measure): with `--plane-fields` ON and this row
  dropped the receiver certifies 299/300, and the one tile it misses
  survives `tiles.local`, `tiles.planek` AND `tiles.retry`; with the row
  it certifies 300/300 and its certificate signature is BYTE-IDENTICAL
  to the in-register control's. The amplitude has been re-derived twice
  — every repair to the field pushed it up (3.0 pre-units-fix, 3.5
  post-fix, 4.0 post-median-publication), which is the licence working
  as stated: this row's job is whatever the field of the day still
  cannot express. COST, honestly: 137 jobs and 662.7 s, 20% of that
  run's 3,320 s, for 23 certificates — a harder page means more residue
  tiles and each pays a full local head fit plus the search. It is the
  dearest row in the tree and at this amplitude it looks it. The band
  has a ceiling too, and it bounds every residue row: past it the Y
  stream falls below the informative floor, nothing is ATTEMPTED, and no
  residue row is born at all. On both clean sims the row fires ZERO
  times and the decode is byte-identical to a tree without it,
  cross-checked against an unmodified checkout.
  RE-DERIVED 2026-09-04 (record: conversion_docs/MEASUREMENTS-2026-09-03.md,
  design: docs/PLANE-FIELDS.md §6.6). The b8471fc re-key made the
  four-dot page's one missed tile a tile `tiles.local` reaches, so this
  row's marginal gain fell to zero; the stimulus moves to 4.5 dots by the
  yield principle. Measured there, field ON: with the row dropped the
  receiver certifies 200/300 — Y = 0, its tiles attempted, retry, local
  and planek each firing 100 jobs and certifying none; with the row,
  297/300. The 97 certificates that exist only with the row present: 20
  minted by the row itself, 73 by `tiles.local`, 4 by `tiles.scan`. The
  claim is the causal one: without the swim the plane stays at zero.
  Reach, per plane: the field's 2.0-dot clamp plus this row's one-cell
  bound (3.0 at c3), about five dots; the binding ceiling is the arming
  gate above — this row, like retry and local, is born only from FAILED
  attempts — and at 5.0 only `tiles.scan` fires, no rescue row is born,
  and nothing helps (200/300 either way). The signature claim changes
  with the page: the row's arm no longer reproduces the control byte for
  byte at 300/300; every certificate it mints is the control's, bit for
  bit — zero wrong — at 297 of 300.

## The life of a decode, told through the table

Ingest converts each scan into the resolution ladder and the survey
finds the printed regions — one worker each, price 10, fired once.
Every (region x rung) then births its window grid, and each window gets
a `place` worker whose bookmark walks the placement ladder: consult the
ring of already-placed neighbours (price 40), decode address words in
the centre then the rest of the window (60/80), widen the consult
(120), cold-search the page by correlation (250/260). Coarse rungs pay
+2 per rung less than fine ones, so the whole sheet places
coarse-to-fine without any phase machinery. An accepted placement
births the window's `calibrate` worker (15+rung): sample cells, fit the
score-to-probability map, hand evidence to the region `ctx` worker
(the context detector, one per region). Each tile the evidence covers
births `tiles.scan` (20+rung), which assembles its decoder input at
fire time — cut this tile's cells from the covering windows' evidence,
per-cell owner by held-out loss (Wave 2: `tiles.freeze` deleted);
a second capture's evidence births
`tiles.union`; a failed attempt births `tiles.retry` at the same
price — retries are ordinary work, never gated by close readiness (the
v2 gate law). Certificates wake three things: the fountain-close
consult (engine-held; race mode may end the run right here, cancelling
everything pending), the refinement worker of every window covering
the tile — `refine` for K windows, `refine.color` for colour windows
(price 200: re-fit the window's geometry against the now-known printed
cells, re-read, let ordinary decoding re-run), and the
`revisit` worker (also 200) — the mop-up row — which gives
calibration-refused or never-placed windows a fresh chance once their
neighbourhood is certified. Last of all, at 210 and 220, the
`tiles.uplift` row re-reads whatever residue survived everything
cheaper through one of the two supplemental colour arms. The queue
simply drains; when it is empty and nothing is in flight, the run is
over (exhaustion = exit). Dearest of all, at 240, `tiles.swim` searches
each covering window for a per-plane local affine and reads the tile
once more through it — the last thing tried, on what nothing else
could reach.

## How this matches v2 (the dataflow rewrite)

Kept, now declarative: one-bit wakes (version bumps, no payload);
fire-time consult (every job reads current truth, never wake-time
state); the tried-set floor (identical inputs never re-run); the
monotone price-ordered worklist; the two-gate close law (work knows
only "always"; count_ready and exhaustion belong to the close alone);
commutative facts + single-writer merge = payload identical for any
worker count. Deliberately NOT carried: v2's journal/replay/lease
machinery (holo3's resume is one fact snapshot dumped at RunDone and
folded back through the ordinary `_ingest` path — no journal, no
bookmark persistence, no event replay; API.md §9a), its mechanical
read-set capture
(replaced by declared `reads`, materialized once at worker birth —
over-declaring is safe: extra wakes, never wrong results), and the
admission gate (a v2 artefact, deleted by ruling — pure cost order).

## How this keeps the spirit of v1 (the receiver that closed everything)

v1 ran phases: rung-major sweeps, then mop-up, then refinement, then
supplemental passes, each seeing the settled state of the last. holo3
reproduces each as an emergent property of prices and subscriptions:
rung-major = the +2/rung price step; "refinement sees the maximal
certificate frontier" = price 200 puts it after everything cheaper AND
its per-tile subscriptions re-fire it as the frontier grows; mop-up =
the revisit row's certificate-driven second chances; the retry tail =
ordinary priced work that naturally runs late. The colour refinement
lane v1 ran on every colour close is now the `refine.color` row
(v1's `color_refine` numerics carried verbatim; the gap forensics
attributed 53 of 58 colour-volume misses to its absence). v1's
supplemental u-lane arms a3 and a4b are now the `tiles.uplift` row
below, scheduled rather than gated. The `color.pooled_ctx` row is a
supplemental colour arm that is NOT one of v1's — v1 fitted its context
matrix per (capture, lane, region) and never pooled captures at all.

## The three named problems, mapped

- MOP-UP: was a dropped v1 phase; now the `revisit` row. A window that
  failed calibration or never placed re-fires when certificates land in
  its reach — subscription, not phase.
- REFINE: was one-shot per certificate state and blind to late
  eligibility; now subscribed to the certified tiles in its reach, its
  own evidence and its own pose, so any change — including a late first
  chance — re-fires it. The hard-column rescue chains v1 won become
  reachable. Colour windows get the same treatment through
  `refine.color` (per-stream certificate reach, no evidence half —
  colour labels derive from certificates and format truth alone).
- UNION/RETRY: union births mechanically from a second capture's
  evidence; retries arm on every ordinary failure and are never
  suppressed by close readiness (the measured CMY8 starvation is
  structurally impossible now).

## Evidence so far (sims; real sheets pending)

The colour refinement row, on the colour sim (--complete): 14 fires,
2 adoptions; certificate set and payload byte-identical to the
pre-lane baseline (279/279, every certificate re-checked against the
emit ground truth through the projection — zero wrong), workers 1 == 8
byte-identical; each adoption re-fired color ->
tiles.scan through the declared reads alone. The sim's open tiles are
evidence-limited, not pose-limited, so the adoptions add nothing
there — the lane's yield case is the real-sheet misses. K sims never
fire the row.

The local-context row (`tiles.local`), 2026-08-30. NULL: on both clean
sims at workers 1 under `--complete` the payload is byte-identical to
the pre-row tree (K sha `59495601d00fa781…`, colour
`ddf7acebcd86ae52…`), the certificate sets are unmoved (49/49 and
279/279), and EVERY per-plugin job count is unmoved — the row is never
eligible on the K sim and never arms on the colour one. On the
degraded K capture it fires twice for two extra failed attempts and
zero certificates: that capture blanks everything outside a central
box, so its residue is evidence-limited, not context-limited.
EXISTENCE: a derived capture that gives the raster of window (0, 0) its
own channel — a 5 px directional smear and its own noise (sd 49) over
cells [0, 200)² of the frozen K render, the other eight windows
untouched — is decoded twice in the same tree, once with the row and
once with the row removed from `DESCRIPTORS`. Without the row: **45
certificates and the volume is LOST** (the metadata never reaches its
trust threshold). With it: 15 fires, **48 certificates and the volume
comes back byte-exact**, the three gained tiles being (0,0), (0,2) and
(2,0) — a strict superset, zero certificates lost, zero wrong against
the clean `--complete` run, and workers 1 == 8 on the payload bytes.
That is the row's whole claim: a context fitted over a region that is
eight-ninths one channel and one-ninth another is wrong for the ninth,
and re-fitting the ninth on its own recovers tiles nothing else in the
tree can. It is a constructed stimulus, not a yield measurement: the
real-sheet case is the crop-parity residue on e029 and xerox-K.

The COLOUR arm of the same row, 2026-08-30. NULL: the clean colour sim
at workers 1 under `--complete` keeps its payload sha
`ddf7acebcd86ae52…`, its 279/279 certificates and every per-plugin job
count with the arm live, and the row fires zero times there — that
sim's residue is below the attempt floor at the page edges, and the row
arms only on FAILED attempts. EXISTENCE: a derived capture gives window
(0, 0) of the colour sim its own PLANE GEOMETRY — the R channel, the
one cyan absorbs, sampled 5 px = 0.83 cell off in x over cells
[0, 200)², plus that window's own noise (sd 60), the other fifteen
windows untouched. The mechanism is the measured one: e033 found a real
per-plane x-registration sinusoid on the AltaLink, and `color_region`
fits ONE residual per plane over the whole page as a function of
page-y, so a jump confined to one window is averaged away there and is
exactly representable by a fit over that window alone. Without the row:
**285 certificates**. With it: 33 fires, **291 certificates** — +6, and
every one of the six is a **C-stream certificate on a patch tile**
((0,0), (0,1), (1,0), (1,1), (2,0), (2,1)), i.e. the gain lands on the
misregistered plane and nowhere else. Zero lost, zero wrong against the
EMITTED page (`color_region.certified_projection` re-projected onto the
generator's own ground truth), payload byte-exact and identical at
workers 1 and 8. Both runs close here — the colour fountain has surplus
— so this is a certificate superset, not a rescued volume; its
attribution is the sharper half.
WHAT THE COLOUR SIM WOULD NOT DO, recorded because it bounds the claim:
three other local anomalies were measured and the region head absorbed
all of them without losing a certificate — contrast compressed to 35%
on all three channels, a 160-level per-plane photometric offset (QDA's
per-class covariance simply widens to cover it), and a 0.67-cell
per-plane registration jump on its own. The colour sim's channel is
binary and unblurred (sd 127.5) with 36-pixel aperture averaging, so it
carries an enormous margin; only geometry plus noise together take the
margin away. Read the +6 as an existence proof of the MECHANISM, never
as a yield estimate.
LANE: the three colour-patch decodes cost ~490 s of the 140 s slow-lane
budget on a loaded machine (the K trio ~130 s), so they are gated behind
`HOLO3_RUN_ORACLE_SWEEPS` — the widened matrix — and the ordinary slow
lane keeps the K proof. One deleted line per fixture reverses that.

PER-TOOL ACCOUNTING, from the two patch runs' own `PluginRow`s (the
doctrine's currency — cost per certificate, measured, never assumed):

| arm    | fires | CPU s | s/fire | certs | s/cert | share of run CPU |
|--------|------:|------:|-------:|------:|-------:|-----------------:|
| K      |    15 |  3.25 |  0.216 |     3 |   1.08 |  3.25/38.5 =  8% |
| colour |    33 | 141.3 |  4.283 |     6 |  23.6  | 141/300  =  47%  |

The colour arm is ~20x dearer per fire because it re-runs the ENTIRE
colour head — QDA, detector calibration, registration residuals, feature
divisor, context matrix — where K re-runs one nine-bin curve. Its 23.6
CPU-s per certificate is in the same family as the record's own
marginal costs (COLOR-UPLIFT §13's 22.5 s each), so it is not out of
band, but both arms are priced at 220 and that is now a KNOWN
MISPRICING: price is a scheduling order and 220 puts both behind
refinement, which is right, while the CPU they draw differs 20-fold.
Deriving a second constant would be inventing one; the honest fix is
the cost-fed scheduler the toolbox doctrine asks for
(TOOLBOX-INVENTORY §1 condition 3), which holo3 does not have. Flagged,
not patched.

Old engine vs descriptor engine, AS MEASURED AT THE DESCRIPTOR
CHANGEOVER (a historical comparison — three of its four mechanisms have
since been replaced, and the numbers are not re-derivable from today's
tree): payload bytes identical, certificate sets identical (49/49 and
279/279). Job-count drift, each explained AT THAT TIME:
black-and-white calibrate −40% (input digests skipped refits whose
inputs had not changed), colour tile jobs −49% (one job attempts all
pending streams of a tile), retries +54% fires (epoch-keyed
re-arming — the behavior the CMY8 harvest starved for), revisit +4
fires (new row, no output change on clean sims). Since superseded by
D6: the input digests and the evidence epoch are BOTH GONE — the
version floor is the entire staleness story (addendum 6), and there
are no content digests or stamps anywhere in the tree. Real-sheet
trials (full harvests, same sheets as the parity table) adjudicate the
debt rows' yield.

D6 waves 1-3 (store accessors + key schema, `tiles.freeze` deleted, cost
unification): payload bytes and certificate sets identical to the wave-0
baseline on both sims at workers 1 (49/49 and 279/279) at every wave,
workers 8 payload-identical. Wave 3 briefly kept a rework-aging
formula inherited from holo2; the 2026-08-29 ruling deleted it — a
re-fired worker pushes at exactly its declared cost. The K sim is
unmoved job for job; the colour sim re-interleaves its tail (retry
83 -> 52, scan 223 -> 208, color 21 -> 24 fires) for the same
certificates.

The escalation door + the label cap (2026-08-29 night rulings): both
sims keep the wave-0 payload AND the wave-0 certificate set at workers 1
under `--complete` (49/49 and 279/279, certificate signatures
byte-identical), and both payloads at workers 8. The colour context fit
now reads every label — up to 144,249 of them on this sim, where the cap
allowed 40,000, and 672 of the 1,380 curve fits were being subsampled —
for the same certificates. It got them with FEWER fires than the same
tree without the change (color 15 -> 12, tiles.scan 305 -> 291,
tiles.retry 147 -> 140, place/revisit/refine.color unmoved): the
escalation collapses wake storms the flat price used to serve one at a
time. Each surviving fit is dearer; the two wall measurements available
differ by less than this machine's own load noise on the day. The K sim
is unmoved job for job — nothing K-side reads the fire ordinal.

The done gate (2026-08-30, docs/DONE-GEOMETRY.md adapted to this
architecture): a window whose whole tile reach is certified in EVERY
stream can never mint anything again, so no row of it is posed,
sampled, re-fit or revisited. ONE derivation in the store,
`window_fully_done` — the placed branch reads the derived window and
evidence reach against the standing `done_grid` (the AND across
streams: a tile with C and M certified and Y open is NOT done), the
unplaced branch projects the region's committed poses onto the
window's supported extent (`window_extent_done`, the pose-free half
`place`'s retire already spelled out). Tiles outside the page grid
carry no payload and can never certify, so they are ignored. `place`
consults it in retire, `calibrate` and `revisit` in eligible — plugin
refusals through the ordinary seams, the engine untouched; standing
queue entries retire by refusing at their pop. `refine` and
`refine.color` carry no call: their own reach predicates already
refuse every done window (pinned in test_h3_done_geometry.py, so a
drift off the law fails loudly). The payload rows are never gated —
they act on UNCERTIFIED tiles and keep their own subject-level refusal.
Suppression is fire-only: a done window keeps its standing evidence,
its tile cover and its seat in the region context fit, so the live
neighbours it shares a region with lose nothing.

Measured at workers 1 under `--complete`, against a pristine checkout:
the certificate SET and the payload are identical on every sim (K 49,
colour 279, degraded 4, mixed 49, null 0) and no row's job count grew.
K calibrate 60 -> 29 and ctx 14 -> 9 (the non-complete serial pin
moves 45 -> 29 with every other row job for job); mixed calibrate
136 -> 111, ctx 28 -> 27, and two union subjects that were born and
never fired are no longer born; the colour sim is unmoved job for job
(every window there still touches one of its 21 open tiles). Colour's
evidence row is per-LANE, so window-granular done-ness cannot suppress
it — that is the gate's honest colour gap. At the endgame shape (48 of
49 tiles certified, 49 placed + 40 parked windows) the gate costs
0.7 us on the placed branch and 5.4 us on the pose-free one per pop,
against the 95.5 us ring consult it replaces: calibrate pops that fire
49 -> 1, parked revisit pops that reach prepare 40 -> 0
(`measure/donegeo_saturation.py`; the yield harness is
`measure/donegeo_parity.py`).

The endgame feeder fix (2026-08-30): the live c2-cmy8 harvest at 95.6%
certified measured the main thread at 99.6% CPU for 25+ minutes feeding
nobody — 644 frontier entries drained, 6 jobs fired, ~1.4 s per pop,
all eight workers at zero. Two mechanisms, both read from the code
before the profiler confirmed them. (1) retire runs before the version
floor, and refine.color's retire recomputed the window's tile reach
from its ~40,000-cell page_cells array on every pop — np.unique(axis=0)
costs 18.7 ms a call in its structured sort, eligible recomputed it a
third time, and prepare then scanned every certificate three separate
ways (the certificates() copy, reach_streams, suppressed_tile_codes)
and sorted every placement for one pitch median. The reach is now a
store cell derived exactly where page_cells is derived (the placement
fold's affine change; the evidence fold's fit change), retire and
eligible consult it through O(1) has_certificate lookups (23 us
measured, was 19,700), the suppressed codes come off the standing
done_grid cache, done_cells stamps itself from maintained per-region
counters instead of walking every placement, and the sorted placement /
window / certificate-key / color-row views are cached against their
append-only key sets. reach_tiles itself now uniques one numeric key
instead of structured rows — output-identical, 0.40 ms. (2) The
lazy-deletion frontier held every superseded push — ~300 entries per
bookmark on the live sheet — and every one of them paid the retire
chain at its pop. A bookmark now holds ONE live entry (the seat; its
token is the push seq): a same-price re-push keeps the standing seat
and with it the FIFO position that adjudicated first under lazy
deletion, a re-price supersedes the seat, and a dead seat costs its pop
one integer comparison, counted as a stale skip. The version floor, the
push-side pending bit and the pop-side one-in-flight rule (D6 addendum
8a) are untouched. Microbench at the measured endgame shape (5,344
certificates, 1,124 bookmarks, the wake-stacked frontier): the same
drain went 632.8 s -> 0.950 s. Both sims byte-identical at workers 1
and 8 (payload sha, certificate signature, addresses, per-cert bits);
the degraded capture's pinned serial job counts unmoved; the K sim
unmoved job for job. The clean colour sim's fire counts moved, and a
three-way control attributes every moved row to the compaction alone
(the derived-cells half re-run on the stock engine is fire-for-fire
identical to its base): colour 12 -> 9, place 684 -> 670, tiles.scan
291 -> 194, tiles.retry 140 -> 59, refine.color and revisit unmoved —
under lazy deletion a stale cheap entry popping after a re-price
version-bumped its bookmark through _repush and manufactured an extra
adjudication that could fire; those fires bought nothing this sim run
kept.
