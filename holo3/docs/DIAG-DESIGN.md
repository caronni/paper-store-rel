# holo3 diag — design (v1.0, 2026-08-29)

The operator surface for `holo3 decode`. Ruled in dialogue 2026-08-29
(Germano); supersedes the pane contents built at integration (62c5cc2)
while keeping that build's plumbing verbatim: append-only event list,
cursor fold, render-on-demand, revision-keyed refetch, loopback-only
stdlib HTTP server, inert failures. Viewer binds only with `--diag PORT`
(contract ruling 13-3); `events.jsonl` + `argv` + `report.json` + final
frames always land in the run dir (ruling 13-2).

## 0. Hard invariants (carried, not negotiable)

- Diag is a pure event consumer with exactly TWO interfaces: the
  append-only event stream (facts; emission from the engine merge path
  and from plugins via `JobResult.events` only), and the ONE-SLOT
  GAUGE (`StatBoard`) for the engine's present tense. The gauge is
  engine-owned and immutable-replace: the merge thread assigns a
  freshly built frozen `EngineStat` to the slot; the viewer thread
  reads the slot reference once and uses whatever snapshot it saw.
  No shared object is ever mutated in place (the free-threading
  discipline), and no third channel exists.
- No diag failure may change payload, status, or exit code. Every diag
  entry point is guarded; failures are one stderr line.
- Byte-identity: a run with the viewer on is byte-identical to the same
  run with it off.
- Never print zero where the fact is unavailable — say
  "unavailable before <producer>". A value becoming known must not move
  a row.
- Durable state owns fill colours; transient work is outline/stroke
  only. Deep red is reserved for contradiction and never painted
  without a contradiction producer.
- Frame revision is work-counted (`len(events)`), never a clock. The
  server reads no clocks; liveness and rate are client-side.
- Geometry rides events in the producer's native frame; the renderer
  applies exactly one transform.
- Events are values (scalars, tuples, small ndarrays). No live object
  ever crosses into diag.

## 1. Layout (ruled 2026-08-29)

```
rows      6 fixed status rows (+ conditional field/pose row)
now/last  two fixed text lines: jobs in flight · most recent completion
selectors capture links (pane A) · page links (panes B/C, bands)
A CAPTURE (png) | B PAGE (png) | C PAYLOAD (png) | SCHEDULER + CLOSE (html)
POSE band (png, half the bottom row) | FIELD band (png, the other half)
overflow worker detail (html)
sparkline: certified over session (client-side)
```

- Every `<img>` scales to page width (`width:100%`); native render
  width is generous (§6) — the operator's monitor is large, browser
  zoom is the zoom feature.
- All PNGs are rendered from the fold taken at the last `/status`
  poll. Each pane carries its own revision (bumped only by the event
  types that change it); the browser refetches a pane only when its
  revision moved, and the cache is keyed (pane, selector,
  pane-revision) — an unchanged pane is never re-rendered and keeps
  its coherent older frame (the holo1 per-page-revision precedent).
- SCHEDULER, CLOSE, rows, now/last are HTML rendered from `/status`
  JSON — selectable, quotable, no glyph rasterization cost.

## 2. The six-row status block

Fixed shape, one formatter feeding the shell, the stderr epilogue, and
`report.json`.

1. `format   <format_id> · <ty>x<tx> tiles · <n> possible · streams C,M,Y · PROVISIONAL`
2. `capture  <n> ingested · <sha12>… · regions <n> · support <cells> cells · calibrated <k>/<n>`
3. `frontier queued <n> [survey 1 · place 31 · tiles 180 …] · in flight <m> · workers <w>`
   — plain plugin names, never raw cost integers. Queued counts are
   heap entries (stale entries included; the label says "queued").
4. `work     jobs <n> · cpu <s> · certs by plugin [tiles:1391 · refine:238]`
5. `tiles    UNKNOWN n · ADDRESSED n · FLOOR n · ATTEMPTED n · CERTIFIED n [C a · M b · Y c]`
   — per-stream split on colour rows; FLOOR (below attempt floor) and
   ATTEMPTED (attempted-failed) are separate states (they imply
   different next work — restored v1 ruling).
6. `close    <status> · K <used>/<total> · metadata rank <r>/24 · equations <e>/48 · blocks <s>/<n>`
   — while no solve has run the row shows the counting projection
   instead: `symbols <have>/<K> · … · blocks ready <r>/<n>`.

Conditional rows follow the six, from the same formatter (`all_rows`);
`six_row_status` stays exactly six.

7. `fields   lane <ord>.<level> page <p> · C <m>d <n>t <verdict> · … · <k> lane-pages fitted`
   — the plane-field glance, on colour runs only: a K run has no
   per-plane field, which is a different statement from "none measured
   yet" and is not spelled the same way. Before a fit the row reads
   `off — pass --plane-fields …` or `unavailable before the first fit`;
   the refusing floor itself is named in the FIELD pane and in
   `report.json`, never abbreviated to a zero here.

## 3. Panes

The done-wash projects each certified tile through the placement's
own `native_affine` — the renderer applies exactly one transform, the
producer's (never a rebuilt origin+pitch composite).

### A CAPTURE (scan space; capture selector)

Shows what the segmenter did and what placement is doing, for ONE
capture at a time.

- Region mask drawn as a THIN OUTLINE including holes (from the
  survey's own support mask at `step_px`), tinted region hue; label
  `N.M` where N = capture ordinal (ingest order) and M = region index
  (survey already ranks by area, biggest first).
- Bounding box only while a job on that region/window is in flight; no
  box otherwise.
- Window rectangles, folded over levels per (capture, region, extent):
  - scheduled: thin outline labelled with the NEXT placement stage by
    name (ring / word_centre / word_rest / wide / cold_live /
    cold_rest) — cost as secondary text;
  - in flight: emphasized outline (the active bbox);
  - unresolved after a pass: stays visible with its next stage — a
    window is never refused, only re-priced, and the residue must stay
    visible;
  - DONE WINDOWS DISAPPEAR — on the accepted placement, or on the
    `WindowRetired` that carries the reason (2026-08-31: `done_covered`
    reaches the fold as a retirement cause, never as a settle);
    retired-after-subdivision parents disappear when their children
    appear.
- Done-wash (ruled 2026-08-29): CERTIFIED TILES PROJECTED BACK ONTO
  THE SCRAP — each fully certified page tile is mapped through its
  placement (inverse rotation, region frame, capture px) and washed
  pale green on the region. The scrap fills green tile by tile as
  certificates land; late-run pane A reads: washed = recovered,
  rectangles = outstanding work, bare = failed. (Supersedes the
  region-level won-wash.)
- Underlay: the survey preview (≤512 px, 1/99-percentile stretch,
  lightened) with "preview omitted by the survey" caption when absent.
- Per-pass refusals are not painted as terminal; refusal causes are
  tallied as text under the pane (cause → count), never one guessed
  cause.

### B PAGE (page space; page selector)

PAGE-DOMAIN 2026-09-01: page selectors are live ∪ `{0}` (the
`field_pages` pattern plus the page-0 prior), clipped against possible.
A single-sheet run never grows pane slots for pages 1..`max_pages-1`.
Tile denominators count live pages.

- Placed scraps shaded in their pane-A region hue at their page
  position, labelled `N.M` — regions of one capture may land on
  different pages; the identity travels.
- ADDRESS OVERLAY (the 13-5 word-fold, ruled 2026-08-29): per page
  tile, on the placed-support wash —
  - the NUMBER = observed sites toward the 100-bit address word
    (0..100), exact union across windows (OR of per-placement site
    masks);
  - the COLOUR (chip border) = word state: unseen / covered /
    word-solved (BCH decode validated, from `WordOutcome`) / conflict
    (deep red, sticky — painted only once a contradiction producer
    exists).
- Pending/unplaced windows never draw here (an unplaced window has no
  page position — the fabrication rule).

### C PAYLOAD (page space; page selector)

- One grid, per-stream segments interleaved within each tile chip
  (holo2 style — ruled 2026-08-29 over stacked per-plane grids).
- FIVE states per (tile, stream): unseen · addressed-reachable ·
  below-floor · attempted-failed · certified. `TileOutcome.result`
  already carries the three terminal ones; floor and failed get
  distinct chips (amber vs orange), certified green; unseen sibling
  segments stay neutral so partial stream success never reads as a
  whole-tile state.
- Evidence count printed per touched tile under the one-font rule
  (omitted pane-wide when it cannot fit).

### SCHEDULER (html)

holo2's worker pane re-aimed at holo3's frontier nouns. Per plugin:
queued · in flight · jobs done · certificates · cpu-s (bars scaled to
block max). Below: attempts histogram (workers by attempt count —
1 / 2 / 3-5 / 6-10 / >10; the re-work band = churn), stale-skip count,
retired-worker count, wakes per merge. Only numbers the engine
actually produces — no promises without producers.

### CLOSE (html)

- Headline: `VERIFIED · <bytes> · sha …` green, or close status.
- `metadata rank r/24 · distinct certified equations e/48 · trusted?`
- Per-(stream, block) bars `have/needed`, green when solved; counting
  consults (`CloseCheck.blocks_counting`) carry have/needed rows with
  `rank: null` — lazy rank: rank exists only where a solve ran, and a
  count-ready bar says "ready", never a rank.

### POSE band (page space; page selector; half the bottom row, native
render 2x the page-pane width so it scales cleanly) — new

Estimated-geometry display, field-pane class honesty rules:
- one glyph per placed window: a rotation tick (exaggerated ×E, E in
  the title) + colour for pitch/scale deviation from nominal; per
  capture staggered so multi-capture poses stay distinguishable.
- Derived from `PoseCommitted.native_affine` / `pitch_px` vs the
  format's nominal pitch at the capture's declared dpi.
- Deltas, not decode consequences — the band predicts nothing.
- Encoding iterates on sight (open presentation item).

### FIELD band (page space; page selector; the bottom row's other half,
same 2x native width as POSE) — built with its producer, 2026-08-31

The plane-fields arrow band, matched to v1's (user design 2026-08-21,
docs/PLANE-FIELDS.md §6.2): staggered exaggerated C/M/Y arrows over a
mid-grey base, BLACK = blind spot, dark green = done.

- One arrow per plane per BLOCK, drawn from the block centre, per-plane
  staggered 3 px against overdraw; C cyan / M magenta / Y gold, the
  stream palette both viewers use.
- Exaggerated, with the factor in the title: capped so no arrow reaches
  beyond 2 blocks on its OWN axis (per axis, so a mostly-x field keeps
  full-length arrows). Arrows stay isotropic in pixels, so the drawn
  direction is the measured direction. An illustration — no
  dots-per-pixel claim.
- A block is SHADED where any plane's delta reaches the writer's own
  publish floor, carried on the event rather than re-typed here. The
  shading IS the dead-band prediction.
- A block with no field data is split BY CAUSE: dark green where every
  tile in it is certified in every stream (nothing left to measure,
  benign), black otherwise (the actionable blind spot).
- Text block under the plot: the lane, page, certificate count, block
  geometry and factor, then one line per plane — median delta, sites,
  support tiles, residual, and PUBLISHED or the floor that refused it.
- Present only where a fit has landed (`status.panes.field` lists those
  pages); a run without the arm renders exactly the four panes it
  always did.

Producer: one `FieldFitted` event per fit, carrying every plane whether
or not it published, with the per-tile field block-pooled to at most
24x24 blocks — 15,552 bytes of array per event whatever the tile
matrix. A plane that never fitted reports None for every measurement,
so no consumer can print a zero the fit did not measure.

holo3's field is per lane-page, not one page-wide measurement as in v1:
the band draws the lane that fitted the page most recently and names
it, listing the others beneath. The certified-tile overlay is read off
the model's own tile states rather than riding in the event.

### now / last (html)

- `now`: the in-flight jobs (plugin · subject · stage · client-side
  "observed Ns ago"), or "idle — frontier empty" when nothing runs.
- `last`: the most recent `JobDone` with its headline numbers.
- Fixed two-line region; never a scrolling log.

### Client-side liveness

The shell keeps a session-local history of the certified count and
last revision movement across its 1 Hz polls: "last activity Ns ago"
plus a small sparkline. No server clocks.

## 4. Event contract (the producer bill)

Changed/new event types in `data.py` (all frozen dataclasses):

- `CaptureOpen` += `ordinal: int` (ingest order; the N of N.M).
  Producer: intake.
- `RegionMark` += `cells: np.ndarray` (the survey's own support mask,
  bool, at `step_px`), `step_px: int`. Producer: survey — publishes
  its record verbatim, no second decimation.
- `PoseCommitted` += `page_origin_yx: tuple[int, int]`, `rot_k: int`,
  `pitch_px: float`,
  `native_affine: tuple[float, float, float, float, float, float]` —
  the placement already holds all four; page-native reach is computed
  from origin + rot + extent (fixes the region-local ADDRESSED bug).
  Producer: place.
- `WindowSettled` — vocabulary is place's production strings
  (`pose_refused`, `insufficient_support`,
  `nothing_to_try`, `wide_refused`, `consult_refused`,
  `no_word_candidate_*`, `cold_refused_*`, `straddle_audit_refused`);
  diag groups them for display and tallies causes. Tests use the
  production vocabulary. AMENDED 2026-08-31: `done_covered` LEFT this
  vocabulary. Every settle is a refusal that leaves the window live;
  leaving the frontier is a `WindowRetired` with a cause. The pass could
  never emit `done_covered` anyway — the scheduler's own consult retires
  a done window one line before the job is built.
- NEW `WindowScheduled(capture, level_index, region_index,
  extent_cells, stage, cost)` — engine, emitted when a place worker is
  pushed with a stage different from the last one emitted for that
  window (first entry + escalations only).
- NEW `WindowRetired(capture, level_index, region_index,
  extent_cells, cause)` — engine, at place worker retire.
  AMENDED 2026-08-31: `cause` names the clause of
  `place_sched.place_retire_cause` that fired — `placed`, `exhausted`
  (the ladder ran out; subdivision replaced the parent) or
  `done_covered` (done-geometry). Retirement is the ONLY door the done
  gate has, so without the cause its firings were uncountable: four
  real-sheet runs read as "the gate never fires" while it was in fact
  suppressing 157 of sheet-I-first's 164 retirements.
- NEW `EngineStat(queued, inflight, stale_skips, retired,
  attempts_hist, wakes, inflight_jobs, consult_cpu_s, retire_causes)` —
  the engine's GAUGE, not an
  event stream: the engine writes the latest frozen snapshot into a
  one-slot `StatBoard` shared with the viewer (holo2's main-thread
  push doctrine; single writer, atomic reference reads), and appends
  exactly ONE final EngineStat event before RunDone so the run-dir
  record keeps the terminal state. In-flight jobs, the now-lines and
  pane A's active-window marks all read the gauge — there is no
  JobStarted event. All counters maintained incrementally (no
  bookmark sweeps); the attempts histogram counts each worker exactly
  once (bucket moves are transfers). AMENDED 2026-08-31:
  `retire_causes` tallies `WindowRetired.cause` — a GAUGE over that
  fact, in the same standing as `retired` beside it, not a second
  producer of it: `_retire_worker` derives the clause ONCE and feeds
  both the event and the tally. It exists because the alternative to a
  line in report.json was walking 1.9 M events (or folding a 1.8 GB
  snapshot) to ask whether the done gate fired.
- `JobDone.subject` carries the RAW subject value (one subject shape
  across the contract); the humanizer renders capture shas as
  ordinals everywhere.
- `CloseCheck` += `blocks_counting: bool` — true when no solve ran at
  this consult and the blocks are the incremental counting projection
  (have/needed, `rank=None`); metadata rank/n_unique ride `CloseCheck`,
  never the gauge.
- NEW `WordOutcome(page, ty, tx, errors, sites)` — place, for the
  accepted word-route candidate (sites = visible word sites of the
  decode, errors = BCH corrections).
- NEW `AddressCoverage(page, tiles: tuple[tuple[int, int, bytes], ...])`
  — place, at acceptance: per touched page tile, the 100-bit packed
  mask of word sites covered by this placement's audited cells; diag
  ORs masks per tile, displays popcount (exact union).
- `CalibrateAdopted` — unchanged, gains its consumer (row 2
  `calibrated k/n`; refusal reasons tallied in the pane-A text block).
- NEW `SnapshotReplayed(facts, certified)` — engine, once, at
  `--resume` fold time (after the captures, before any work): the
  per-family fact counts and the certificate total the fold left
  standing. Diag-only accounting; nothing in the engine reads it. A
  resumed run regenerates evidence but not events, so its tile map
  holds only this run's own outcomes — row 5 leads with `replayed N
  certificates · this run …` and the capture/payload panes carry the
  same line, rather than letting an empty grid read as an empty run
  (the never-print-zero law over a resume).
- `TileOutcome`, `CloseCheck`, `RunOpen`, `SurveyDone`, `JobDone`,
  `RunDone` — unchanged (diag stops collapsing floor into attempted).

## 5. Transport

- `/status` (1 Hz poll): folds `events[cursor:]`, returns rows,
  revision (= `len(events)` at fold), now/last, scheduler block, close
  block, capture list (`ordinal · sha12`), page list, per-pane
  revision.
- `/pane/<pane>-<selector>.png?rev=…` (selector = capture ordinal for
  the capture pane, page otherwise): rendered from the last `/status`
  fold, cached by (pane, selector, revision). A request for an unknown
  pane or selector 404s with a naming line.
- End of run: pin final panes for every capture/page BEFORE the server
  stops; bounded grace (~2.5 s) only if a browser ever connected —
  the e018 lesson (0/40 final frames seen without it).
- Run dir (always, `--diag` or not): `events.jsonl`, `argv`,
  `report.json` (rows + scheduler + close + captures), final pane
  PNGs.
- CLI epilogue: the six rows, the plugin table, the per-plane
  certificate split, and one close-shortfall line derived from the
  last `CloseCheck` ("open · block M#2 needs 41 more symbols").
- One CHURN ADVISORY line, only when a row is anomalous:
  `churn    color: 3.2 cpu-s/fire at price 15 · 4.0 fires/subject` —
  an end-of-run observation from the same fold as the six rows
  (`scheduler.churn` in `/status` and `report.json`, printed under the
  scheduler pane). A row is named when its cpu-per-fire exceeds 20x
  what its declared price predicts under the run's own median
  price→cpu scale, or when it fires more than 3 times per subject
  (`JobDone.cost` gives the price actually paid, `JobDone.subject` the
  subject count). REPORT-ONLY: never a cap, never an exit code, absent
  before `RunDone` and absent when no row is anomalous.

## 6. Rendering notes

- Native pane width scales with content (page panes:
  `max(700, 16·tiles_x)` px, clamped ≤ 2200; capture pane 900),
  browser fits to page width.
- Glyph masks cached; text in PNGs limited to labels and tile counts
  (the measured frame hot spot is glyph rasterization — everything
  tabular is HTML).
- Palette: carried semantic palette — certified green, below-floor
  amber, attempted-failed orange, addressed pale blue, done cyan,
  transient purple, contradiction deep red (sticky), region hues from
  the 12-hue table.

## 7. Not built (deliberate)

Websockets/frameworks; hover/click tile inspectors, tabs, fold-outs;
frame archives or history scrubbing (post-mortem = `events.jsonl` +
run-dir frames); HTML/SVG report family; resume seeding (no resume);
always-on serving; a BCH word-site pane (ruled 13-5 — folded into B);
any display fed by discovery-tier channel numbers; server-side clocks,
rate estimates, or ETAs.

## 8. Open items

- Pose-glyph encoding: iterate on sight (proposal: rotation tick ×E +
  scale colour).
- Conflict producer: the deep-red path ships with the first
  contradiction detector (certificate divergence or word
  disagreement), in the same change — never before.
- Field band arrow cap: v1's 2-blocks-per-axis is carried as-is. On a
  smooth field it chains consecutive arrows into a line, which reads as
  direction but not as magnitude; the magnitudes are in the text block
  and in `report.json`. Iterate on sight, like the pose glyph.
