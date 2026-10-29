# holo3 API

holo3 is the from-scratch lean receiver for the holo printed format: decode
only, scans in, payload out, sha printed. Where src/holo (v1) and holo2
numerics disagree on the receive path, v1 wins — v1 is the only tree that
closed the colour acceptance volumes — except the explicitly adopted holo2
pieces (batched BCH, W5 rival bar, R5 seed reduction, cost scale, done
projection, diag skeleton; contract C-1). It runs on free-threaded Python
3.14 (`env/bin/python`, GIL off): jobs are pure functions over immutable
snapshots, all mutation happens in a single-writer merge on the main thread.
There is no journal — the run dir holds a disposable plane cache plus one
durable fact snapshot (`facts.npz`, with its predecessor kept as
`facts.npz.bak` after the first cadence write) that `--resume` folds back
through the ordinary store merge before intake (§9a).
Format law (BCH, LDPC, keystream/AES, fountain algebra, metadata LFSR, slot
permutation) was copy-and-stripped from the v1/holo2 sources, bit-exact, and
verified against them by the `conversion_docs/verify/` scripts — retired with
the v1 receiver 2026-09-05 (`284ae3e`); the frozen legs and one-time records
live in `retirement_docs-2026-09/PRESERVATION.md` §1–§2. Normative
companions: `conversion_docs/00-plan.md` (charter) and `conversion_docs/00-contract.md`
(rulings, frozen surfaces, cost table); this file describes the committed tree.

## 1. Module map

```
src/holo/receiver/
  data.py        frozen dataclasses only: cross-plugin facts + the diag events
  snapshot.py    the fact snapshot — written on the --snapshot-every
                 cadence (default 30 min), on SIGUSR1 and at finish,
                 atomically with the predecessor kept as facts.npz.bak;
                 folded back through the ordinary store merge on --resume
  lib/
    bch.py       BCH(127,50,t=13) shortened to (100,23), d_min=27; scalar + batched decode
    ldpc.py      six e-IRA QC-LDPC rungs, BP decode (min-sum then sum-product), encode
    ldpc_data/   byte-identical copies of src/holo/core/ldpc/data (r0547..r0850)
    pava.py      stack-PAVA calibration, ordered context offsets, loglosses, sigmoid
    geometry.py  affines (cell-edge convention), window starts, the 131/17 parity hash
    decimate.py  integer-box u8 area decimation, ppc ladder, luma laws (E018 order)
    owners.py    freeze_page_owners — one owner window per page cell, total order
    local_affine.py  per-plane local affine corrections + the bounded search (swim, tiles.local)
    plane_field.py   per-plane registration-delta fields in tile space (the fields row's model)
    field_gauge.py   the field's gauge from the pose's ink, the row's word its proxy: (field column, coefficient) per plane
    page_map.py      THE mapping: page cell -> field -> pose -> pixel, and the two frame conversions
    spectral.py  plane isolation: one printing plane read as a black-and-white page (planek)
  format/
    keystream.py AES-128-ECB counter keystream; domains 1-15; draws, perms, dithers
    metadata.py  degree-24 LFSR equations, GF(2) elimination, decode_metadata
    pilots.py    word/filler/dust site construction, word encode/decode, dust values
    identity.py  Family, FormatRow, SiteGeometry, v2 id grammar, 14-row fossil catalogue
    tile_codec.py tile/frame encode+decode, cmy7 pack7 soft demap, cmy8 stream decode, the row's derived tables (plane_bits, stream_bits, stream_toners)
    fountain.py  the column-group law (ColumnGroups, column_groups, TileSlots), VolumeCode (quotas/shuffle/row_of, pooled esi, tile_slots), the per-(block, group) GF(2) Decoder + BlockStatus
    close.py     envelope unwrap + three gates; CloseProgress = one persistent
                 decoder set per run, per-(block, group) count gate, close();
                 close_volume = the standalone close (analyzer's `analyzer
                 close`, the measure harnesses);
                 close_count_progress is the test oracle
  plugins/       one module per stage, pure entry functions + a frozen
                 PluginDescriptor at the bottom (its scheduling contract).
    the K spine: intake, survey, words, place (+ place_sched — the place
                 plugin's scheduling half, 1000-line split), cold, pose,
                 calibrate, tiles (+ tiles_sched — the three ordinary
                 payload rows' scheduling half, 1000-line split), refine
    contradiction  the D1 alarm: a word-routed placement that contradicts a
                 standing one (diagnostic only, called from the place fold)
    the colour stack: color_sites (format-truth site geometry),
                 color_model, color_region (+ color_region_anchor,
                 color_region_ctx, color_region_head — area-internal
                 splits; head = fitting a region's detector and reading
                 with it), color_chain (cmy's hi-first calibration chain,
                 worn in the head slot, R11), color_pooled (the pooled
                 context arm), color_refine (the colour refinement lane)
    the supplemental arms (§8): color_arms (the A3/A4b ladder,
                 override-only), color_photometry (A3 per-window
                 photometric gain/offset), color_conditioning (A4b
                 KnownField-conditioned marginalization, CMY8 only),
                 uplift (tiles.uplift — the residue row that runs them)
    the residue toolbox: local_ctx (tiles.local — re-read one failed
                 tile under a locally fitted head), plane_k (tiles.planek
                 — one plane read as a K page; + plane_label, its cmy
                 translation: a label stream as its toners' isolated
                 reads summed), swim (tiles.swim — the
                 per-plane local-affine rescue), fields_collect
                 (fields.collect — one capture's page-field measurements)
                 and fields (the fields row — one solved field per
                 printed face) + field_tiers (their evidence tiers and
                 the no-double-count law)
  diag/          event-fed only: model (accumulators), readout (status rows,
                 advisories, the status dict the server polls), report (the
                 event journal + report.json), panes (A-D), fields_pane
                 (the FIELD band), server
  store.py       the accessor store's READ half: every mutable cell is a
                 private dict behind a keyed accessor, plus the done
                 geometry derived from the certificate frontier
  store_folds.py the WRITE half (the 1000-line split): the `_fold`
                 dispatch and the typed folds, the only writers, each
                 returning the FactKeys a fact really changed and the
                 accounting family it belongs to
  engine.py      orchestrator core: DESCRIPTORS tuple, generic births/wakes
                 via the inverted FactKey subscription index, frontier heap,
                 one-in-flight bookmarks, single-writer merge, accounting,
                 close consult; owns no pricing at all
  operator.py    the operator's doors (the 1000-line split, 2026-09-17):
                 OPERATOR_SIGNALS and OperatorDoors (arm/disarm, the
                 handler, the loop-top service with the safety-snapshot
                 cadence), and the run's products — the atomic fact
                 snapshot, the diag run-dir dump, the live viewer and the
                 status rows.  Takes part in no scheduling decision
  sched_trace.py the scheduler instrument, DEFAULT OFF (`HOLO3_SCHED_TRACE=1`
                 arms it at `_start`): the wake fan-out, the push and pop
                 funnels, engine-thread wall by category, per-fire input
                 digests and a per-bookmark ledger, written under
                 `<run_dir>/sched-trace/` with its summary.json.  Read by
                 no scheduling decision, appends no event; reducers and
                 the operator's manual in measure/sched_trace/
  sched_trace_folds.py  its sibling at the 1000-line seam: fold-time
                 records of the two loss-carrying evidence cells
                 (`ColorEvidenceRow`, `WindowEvidence`), adopted or
                 refused, armed with the trace
  descriptor.py  the plugin/scheduler contract: the closed 13-family
                 FactKey vocabulary, PluginDescriptor, WorkerBookmark
                 (every price lives in the plugins; the engine only pops)
  schedule.py    the derived schedule table `python -m holo.receiver schedule`
                 prints: resolved price ladder, per-row subscription
                 families read off the `reads` functions, write families
                 read off store_folds by parsing its fold methods
  cli.py         decode + schedule surface
  __main__.py    python -m holo.receiver
```

No holo3 production module imports holo2/paperholo/src-holo. Plugins import
only data.py, lib/, format/, and the two pinned surfaces P5→P6 and P7→P8.

## 2. Data model (src/holo/receiver/data.py — all frozen dataclasses)

Units are in the names: `_px` pixels of the named raster, `_cells` format
cell coordinates, `_yx` (row, col), `_in` inches, `ppc` pixels per cell,
`dpi` declared scan resolution. `pitch_in` is a `Fraction` (inches per cell).

Capture side:

- `Level` — one rung of a capture's decimation ladder: `index` (0 = coarsest,
  2 ppc; last = native), `ppc: Fraction`, `scale: Fraction` (native px per
  level px, exact rational), `shape_px`, `label` (e.g. `l00-2ppc-600dpi`).
- `Capture` — one ingested scan: `capture_id` (from the file sha256; duplicate
  shas fold), `path`, `dpi`, `shape_px`, `channels` (1 or 3),
  `platen_backing` (median border luma; R for a family addressed on R (cmy,
  A2 2026-10-12)), `levels`, `plane_dir`
  (run-dir directory of per-plane `.npy`).
- `PlaneRaster` — one plane at one level: `plane` in {g, y, r, g, b};
  `open()` returns a read-only mmap view (each worker opens its own).
- `Region` / `CaptureSurvey` — survey output: active regions (`cells` support
  grid at `step_px`, `extent_px`, `area_mm2`, `median_tensor_score`) and the
  voted pitch (`pitch_class: Fraction | None`, `pitch_px`); `pitch_class
  None` means the vote tied or nothing snapped — the capture is surveyed
  and framed at the DECLARED pitch anyway, with a stderr warning and a
  `SurveyPitchFallback` event (D5, 2026-09-04).  A vote that CONTRADICTS
  the declared row still refuses the run.

Placement side:

- `Window` — unit of placement work; `window_id = (capture_id, level_index,
  region_index, extent_cells)`, `extent_cells = (y0, y1, x0, x1)` in region
  cells; `supported_cells`, `depth` (subdivision), `lane_depth` (scale-space
  lane), `ordinal`.
- `LatticeSeed` — R5 best-supported lattice-seed reduction rows per region.
- `Placement` — a committed pose: `page`, `rot_k` (quarter turns),
  `page_origin_yx` (cells), `native_affine` (6-tuple cell→native-px, cell-edge
  convention), `pitch_px`, `route` (producing route tag), `local_cells_yx`
  (N,2) i16 — window-LOCAL cells, non-negative and bounded by the window
  extent, minted only by `place.local_cells_of`, which refuses a
  coordinate int16 cannot hold. The width is storage, not format law:
  this one array is 94–98% of a fact snapshot's bytes (measured
  2026-09-13), snapshots written before it carry i64 and still read back
  as i64, and every reader coerces before arithmetic because a page
  origin added to these does not fit i16.

Evidence side:

- `WindowEvidence` — K calibration product per window: `page_cells_yx`
  (N,2) i64, `scores` (N,) f32 in the v1 convention (midpoint − means)/spread,
  `reference_values`, PAVA curve (`knots`, `probs`), `n_search`,
  `marginal_llr`/`printed_llr` f64, `accepted` + `refusal_reason`,
  `heldout_logloss` (the ownership ordering key), `ctx_adopted`.
- `RegionCtx` — 9-bin context-detector offsets per (capture, level, region),
  `adopted`, `reason`.
- `OwnedPageEvidence` — the oracle-parity spelling of the owner law
  (`calibrate.freeze_owners`); no production caller — tile ownership is
  assembled at attempt fire time in tiles (`TileCut`, plugin-internal).
- `WindowRows` — colour/refine row bundle: `scan_points_yx`, `states`,
  `furniture_kind`, `known_component_bits`/`_mask`, `heldout_logloss`.
- `PlaneField` — per-(page, plane) registration-delta field in printed
  DOTS along the PAGE axes over the page's tile grid: `delta_dots_xy`
  (ty, tx, 2), `support`, `n_observations`, `n_captures`, `ordinal`. One
  field per printed FACE (docs/PAGE-FIELD-DESIGN.md §2.2): the capture,
  the level and the lane are axes the evidence pools over, never axes of
  the key. A decision cell ordered by `ordinal`, the page's observation
  clock at solve time — a solve over more evidence supersedes one over
  less and an identical clock is a no-op. The clock survives a resume: a
  restored field carries the clock it was solved at and the fold never
  lets the page's own sit below it, so the resumed run's first
  collection outranks the snapshot. Read by the colour lane,
  `refine.color`, `tiles.planek` and `tiles.swim` as a per-cell sampling
  offset. Always written for a colour family; refused at the descriptor
  for `Family.K`, which has one plane and no differential. The three
  planes are one statement under the row's GAUGE, which follows the ink
  the pose is fit from, read off the word as its proxy
  (`lib/field_gauge.word_planes(row.word_states[1])`, PAGE-FIELD-DESIGN
  §2.3 as amended 2026-10-12, CMY-DESIGN R7):
  cmy8 and cmy7, word C+M, `F_C + F_M = 0` and Y free; cmy, word C,
  `F_C ≡ 0` — C published as the zero field with zero uncertainty, known
  by name — and M and Y free, each relative to C (CMY-RECEIVER-PLAN A5,
  I-8).
- `FieldObservations` — per-(capture, page) measurements the solve pools:
  row columns `tile_code`, `plane`, `delta_dots_xy`, `weight`, `source`
  and `window`, a window table (`window_ids`, `window_generation`,
  `window_gauge_dots_xy`), and the ordinal's two store-counted numbers,
  `n_certificates` and `pose_work`. `delta_dots_xy` is the measurement
  in page axes BEFORE the gauge and the window table carries the gauge
  it is read through (`fields_collect.gauged_deltas`), so a row a
  re-collection carries can be re-gauged over the window's whole row set
  instead of staying in the gauge of the collection that made it. The
  window table is also the memo key: a row is carried only while its
  tile is still measured through THAT window at THAT pose generation.
  DERIVED, not durable: a resume re-declares the placements and
  certificates it is measured from, so `fields.collect` re-arms and
  re-measures.
- `ColorEvidenceRow` — per-window colour feature rows: `values` (N, arity) f32.
  There is no stored tile-evidence fact: a tile attempt cuts its cells from
  the immutable `WindowEvidence`/`ColorEvidenceRow` arrays at fire time
  (arity 1 K llr / 6 cmy7 relative scores / 3 cmy8 marginal llrs / 3 cmy
  W-relative state scores C, M, Y), and the cut is densified to f64
  `(4096, arity)` only inside the attempt. A stream reads its level LLRs
  through `tiles.stream_llrs(row, fact, sequential, sibling=None)`: a
  toner stream its column (`fact.plane`), a label stream
  `cmy_soft_demap(sequential, fact.label_index, sibling)`; a cmy lane's
  unsupported label stream is already EXACTLY 0.0 there, erased in score
  space at evidence time (A3, 2026-10-12).

Streams (2026-10-12, CMY-RECEIVER-PLAN I-2). Every key that ends in a
stream — `Certificate`, `AttemptFact`, the tile keys `(page, ty, tx,
stream)` — names it by its `stream_id`, the row's
`StreamFact.stream_id` (§5). A stream is a TONER stream or a LABEL
stream. A toner stream's bits are one toner's presence: K's and cmy7's
`main` (the K plane), cmy8's `C`/`M`/`Y` (planes 0/1/2); it has a
`plane`. A label stream's bits are one bit of the cell's two-bit state
label: cmy's `hi` (label bit 0, state ∈ {C, M}) and `lo` (label bit 1,
state ∈ {C, Y}), docs/CMY-DESIGN.md §2.2; it belongs to no toner, and
`StreamFact.plane` RAISES `StreamHasNoPlane` on it — never a `None`
sentinel, which numpy reads as a new axis. A plane is a property only
toner streams have. Since A1 (2026-10-12) a cmy row carries two label
streams, `hi` and `lo` (label_index 0/1, dither aux 1/2, no fountain aux);
every `.plane` reader that a cmy decode reaches is converted (A3 tiles —
`tiles.stream_llrs`; A4 the projection, below; A7 `tiles.planek`, which
reads a stream's toners through `plane_k.stream_toners`, §6).

Knowledge (2026-10-12, CMY-RECEIVER-PLAN A4, O7). What certificates say
about a tile's printed cells is `color_sites.certified_projection(row,
geometry, page, ty, tx, certificates) -> (bits, known)`, (64, 64, 3)
u8/bool in C, M, Y order, or None where no stream of the tile is
certified. Word and dust sites are known on all three planes from the
format. A payload cell's knowledge is ONE consistency rule for cmy8 and
cmy: its allowed states are the alphabet's (`row.state_ids`) whose bit
on every certified stream (`tile_codec.stream_bits(row)`: a toner
stream's plane bit, a label stream's label bit) is that stream's
certified bit there (`color_sites.certified_stream_bits`, the re-encoded
frame XOR the dither, in the codec's sequential order), and a plane is
known where every allowed state agrees on it, at the agreed value. cmy8:
a certified plane is known, the others not (byte-identical to the
per-plane write it replaced); cmy: one label stream knows only TRUE
ZEROS (hi 0: C and M; hi 1: Y; lo 0: C and Y; lo 1: M), both know the
state; a cmy7 certificate owns the whole state. No mask and no label
view: the two arrays carry every PLANE-WISE consequence of a
certificate, and that is all a reader here asks — a lone label bit 1
(hi: C or M inked; lo: C or Y) is not representable plane by plane,
and no receiver reader needs it (`tiles.cond` re-encodes the sibling's
bits, A6). A reader that takes the
known bits PLANE by plane uses them as they stand — true zeros are true
(the context bins, `refine.color`'s labels, `fields`' certified
template, which wants its plane known on all 4,096 cells, so a single
cmy stream builds none); a reader that names a STATE requires all three
planes known first (`build_window_rows`' resolved `states`, the swim's
complete cells, the analyzer's regressors).

Outcome side:

- `Certificate` — `(page, ty, tx, stream_id, user_bits, source)`; `user_bits`
  u8 `(user_bits,)` undissected: `[0]` = metadata bit, `[1:]` = fountain
  symbol; the counter is always derived via `FormatRow`. `source` is the
  producing plugin/tier (`"tiles/scan"`, `"tiles/union"`, `"tiles/retry150"`,
  `"tiles/cond150"`, `"tiles/local150"`, `"refine/rf1"`, later
  `"color/a3"`). Different bits at one (page,ty,tx,stream) =
  `IntegrityError`, exit 1; identical duplicate = no-op keeping the
  standing source.
- `AttemptFact` — one decode attempt: `stage` in
  scan/union/retry150/cond150/local150,
  `outcome` in below_attempt_floor/attempted_failed/certified,
  `n_informative`, `n_iters`, `syndrome_ok`, `crc_ok`, `components`
  (the sorted (capture_id, level_index) signature the attempt ran over —
  the producer publishes what it knows, so the retry row births from the
  fact alone) and `generation` (the tile-lane or footing counter the job
  READ, reported back by the plugin and stamped per attempt set; the
  STORE owns the counters). Not snapshotted, defaulted to 0.
  Two derived ledgers fold it: `attempt_verdict` — the newest
  `(outcome, generation)` per `(page, ty, tx, stream, stage, lane)`,
  last-write-wins, which `tiles.retry` compares for "still current" —
  and `attempt_ever_failed_at_footing`, the MONOTONE half per `(page,
  ty, tx, stream, stage, ppc)`, which is the residue rungs' franchise
  and the one thing their arming reads: a failure arms a stream and
  only a certificate takes it out (a re-read that comes back
  `below_attempt_floor` replaces the verdict but may not de-arm the
  rung; 2026-09-21 review), and a lane that failed and then left the
  cover keeps the stream armed (since 2026-10-03, `9b67d896`; external
  review claim 2). The lane-keyed failure ledger it replaced
  (`attempt_ever_failed`) was still written on every failure and read
  by nothing; it was deleted 2026-10-18 (SCHED-LIFECYCLE-REVIEW D11).
  Neither ledger is snapshotted; both start empty on a resume, with the
  fact they fold. The two
  generation counters, `tile_lane_generation` and `union_generation`,
  are both maintained cells bumped by `_advance_tile_lanes`; the footing
  one is NOT a sum over the current cover, because a lane leaving one
  takes its term with it and an `==` test may never see an old value
  return.
- `JobResult(facts, events, cpu_s)` — every plugin entry returns this.
- `PluginRow` — accounting row, frozen: jobs, cpu_seconds, certificates,
  poses, words. The engine tallies in plain dicts and mints frozen rows for
  RunResult/diag.
- `CloseBlockRow` — per-block close progress; `format/close.CloseResult.blocks`
  emits these directly (no format-side twin). Since 2026-10-12 it also
  carries the decoder's per-column-group counts in group order,
  `group_rows` / `group_rank` / `group_solved` (empty on a hand-built
  row: the producer gave none, never zero rows).
- `RunResult(status, payload, payload_sha256, certified, plugin_rows)`.

## 3. Events and panes

`Event` is a union of frozen types (19; the table abridges to the ones that
carry pane content — `test_h3_descriptor.py` holds the full golden);
engine/merge appends them to an append-only list, diag folds
`events[cursor:]` with no locks (C-11). Diag can never change payload,
status, or exit code.

| Event | Fields (abridged) | Consumed by |
|---|---|---|
| `RunOpen` | format_id (canonical row_id), display_id (short spelling, for the pane), pages, tiles_yx, stream_ids, n_captures, workers, family (the row's `Family` value, 2026-10-12: the `fields` rows' gate) | status row 1, catalog |
| `CaptureOpen` | capture, dpi, shape_yx, channels, duplicate, levels_ppc | pane A, row 2 |
| `SurveyDone` | capture, regions (RegionMark…), pitch_class, preview underlay | pane A, row 2 |
| `SurveyPitchFallback` | capture, declared_pitch_in, pitch_px, n_regions | report `capture_facts[].pitch_fallback` |
| `PoseCommitted` | capture, level, region, extent_cells, page, route, mismatch, accepted | panes A+B (addressed reach) |
| `WindowSettled` | capture, level, region, extent_cells, state | pane A window rectangles |
| `CalibrateAdopted` | capture, pool_id, adopted, reason | status detail |
| `TileOutcome` | page, ty, tx, stream_id, source, result, bp_iters | pane B chips, row 5 |
| `JobDone` | plugin, subject, cost, cpu_s, n_certificates/poses/words | pane C accounting bars, rows 3-4 |
| `CloseCheck` | certified, symbols_used, k_total, metadata_rank/n_unique, blocks (CloseBlockRow…), status | pane D, row 6 |
| `RunDone` | status, payload_sha256, n_bytes, certified | pane D, row 6 |
| `FieldSolved` | page, revision, tiles_yx, block_tiles_yx, planes (FieldPlaneRow…), residual_by_capture_plane, passes, converged | FIELD band, the `fields` row |

`FieldPlaneRow` carries one plane's solved field — median delta, median
uncertainty, whether any template reached the plane at all, support
tiles, observations, captures, whether the gauge HOLDS it at the pose
(`held`, 2026-10-12: cmy's C, zero by name, its support no statement
about its field; `fields.moved` ignores its support mask), and the field
block-pooled to at most 24x24 blocks (22,464 bytes of array per event for the
three planes, whatever the tile matrix). Every plane is published, including
one no observation reached: that one reads zero everywhere with no support,
which is the honest answer and the one the readers sample at (I6). There is no
publish floor and no refusal (I8). `residual_by_capture_plane` is the
`(capture_id, plane, energy, expected, count)` diagnostic that names a footing
disagreeing with the page rather than with itself, and names the PLANE it
disagrees on: summed across planes first, two healthy word planes hid a Y
plane out by a factor of 8 (W8 R-F). `revision` is the evidence revision the
page stood at when it was solved — reported, never read back; it replaced the
residual trigger, which W8 retired with the machinery that fired on it.

Panes (one composed PNG frame per page): A CAPTURE (tinted survey regions
over the decimated underlay, window rectangles), B PAGE (per-tile chips
UNKNOWN/ADDRESSED/ATTEMPTED/CERTIFIED, per-stream segments), C ENGINE
(frontier tiers + the per-plugin accounting rows), D CLOSE (close status,
K used/total, metadata rank m/24, per-block bars). The HTTP viewer (stdlib,
loopback-only, no-store) binds only with `--diag PORT`; `report.json`, final
frames, `events.jsonl`, and one argv line always land in the run dir.

## 4. lib/ public surfaces

`lib/bch` — module-eager tables. Constants: `N_FULL=127, K_FULL=50, T=13,
D_MIN=27` (exact; spectrum 27:3, 28:8, 31:119, 32:247), `SHORTEN_BY=27,
N_WORD=100, K_MSG=23, N_PARITY=77, GF_PRIM_POLY=0x89`.
- `encode(msg: (23,)u8) -> (100,)u8`; `message_from_word(word) -> (23,)u8`
- `decode(word: (100,)u8) -> ((100,)u8, n_errors) | None`
- `decode_erasures(word, erasure_idx) -> … | None` (budget `2e+f <= 26`)
- `syndromes(word) -> (26,)u8`; `syndromes_many((H,100)) -> (H,26)u8`
- `decode_many(words: (H,100)u8) -> list[((100,)u8, int) | None]` — the only
  batch API (vectorised Berlekamp–Massey + Chien); callers guarantee u8 0/1.

`lib/ldpc` — `N_BITS=4096, Z=64, LLR_CLIP=20.0, LLR_KNOWN=1e9`.
`CODES: dict[str, Code]` eager for all six rungs r0547/r0550/r0625/r0700/
r0775/r0850 (`LADDER` in identity.py gives k_bits: 2240/2240/2560/2880/
3200/3520). `Code` is frozen (edge arrays, starts, var_order, encoder arrays).
- `decode(llr: (4096,)f64, code, max_iters, alpha=0.8) -> (syndrome_ok,
  hard (4096,)u8, n_iters, extrinsic (4096,)f64)` — input clipped to
  ±LLR_CLIP, ±inf mapped to ±LLR_KNOWN; normalized min-sum first, sum-product
  rescue on failure; extrinsic always computed.
- `encode(info: (k,)u8, code) -> (4096,)u8`.

`lib/pava` — v1 calibration kernels. `calibration_probability(scores, knots,
probs)` / `calibration_llr(...)` (interp + logit), `clamp_for(n) = log1p(n)`,
`sigmoid`, `probability_logloss`, `class_balanced_weights(states, n_classes=7)`.
Ordered context machinery: `_pava_nodes`, `_solve_offset`,
`_ordered_context_offsets`, `_binary_logloss` (imported directly by
calibrate — lean tree, no re-export layer). Constants: `N_CONTEXT_BINS=9`,
`CTX_OFFSET_LIMIT=4.0`, `CTX_LLR_CLAMP=12.0` (the ±12 clamp is applied in
plugins/calibrate.apply_context_offsets), CAL/CTX support floors.

`lib/geometry` — `TILE_CELLS=64, WINDOW_CELLS=200, WINDOW_STEP_CELLS=160`.
Affine helpers on 6-tuples (cell-edge convention repo-wide): `affine_matrix/
affine_terms/invert_affine/apply_affine/shift_affine`, `rescale_pixels`
(Fraction-exact), `compose_to_native/compose_from_native`, `window_starts`
(flush-shifted), `rotated_points`, `tile_of_cell`. The parity/hash family
lives HERE and only here: `site_hash(y,x) = 131*y + 17*x`, `site_parity =
&1` (`&2` head sub-split, `&4/&8` reveal codes) — never re-derive (C-4).

`lib/decimate` — intake is u8 + integer factors only (C-10).
`AreaPixelTransform(source_per_output: Fraction)` with point/affine transforms
both directions; `area_decimate{,_into,_rgb}` (integer box; non-integer factor
raises); `auto_ppc_levels(dpi, pitch_in)` builds the 2-ppc-up ladder;
`luma_f32`, `plane_mean_luma_f32`. K sub-native luma rungs go through the 3-D
`area_decimate` path (f64 RGB mean, then f32 box — the frozen E018 order),
never luma-then-decimate.

`lib/owners` — `freeze_page_owners(candidates, page_shape_yx, order_keys)`:
one owner window per page cell, first writer wins after sorting by the TOTAL
key `(heldout_logloss, window-extent-tuple, plane)` (C-12).

`lib/page_map` — THE mapping between page space and the raster (I7).
`plane_delta_dots(field, page_cells_yx)` evaluates one standing
`PlaneField` per cell, bilinear on the tile grid, in PAGE-axis dots;
`raster_points(points, page_linear, delta_dots_xy, cell_dots)` and
`raster_point_grid(points, page_linear, offsets_dots_xy, cell_dots)`
displace sample points by a per-cell delta and by S uniform offsets;
`page_axes(delta, rotation)` / `local_axes(delta, rotation)` convert
between the page axes and one window's own. `RegionWindow` carries the
two matrices (`page_linear`, `rotation`). Time-free, numpy only; the
inverse is one Newton step and has no caller yet.

`lib/local_affine` — the bounded per-plane local-affine search
(`plugins/swim.py` is its only caller). `Affine(translation, linear)` in
printed DOTS over `unit_coordinates`, the window's normalised (x, y)
coordinates, so a linear entry IS the dots it adds at the window edge.
`state_groups(states)` partitions provable cells by printed state once;
`correlation_ratios(groups, sampled)` scores K candidates at a time with
the per-state LEVELS re-fitted for each — freezing them would score the
search against its own starting read. `profile_log_likelihood(eta, n)` =
`-(n/2) log(1 - eta^2)`, the Gaussian likelihood with the photometry
concentrated out. `search` is translation first (full grid over the bound
at half the bound, then halving rings to `resolution`), then ONE sweep of
coordinate descent over the four linear terms; strict improvement to move,
fixed candidate order, no random draws, no raster and no clock.

## 5. format/ public surfaces

`format/keystream` — the format id IS the AES seed. `kdf(seed)` = SHA-256 of
`b"holo/v1|" + seed`, first 16 bytes; AES-128-ECB over 16-byte counters
`(domain, aux, major:3B, u:4B, v:4B)`. `counters()` refuses out-of-range
fields — an out-of-range address must never wrap into a valid different
stream (C-7). Domains frozen 1-15. Draw forms: `blocks`, `bits`, `keys64`,
`payload_bits(seed, plane, page, cells_yx)` (K scramble planes),
`fountain_rows_bits` / `color_fountain_rows_bits`, `bounded_draws` (rejection
sampling, retry cap 64), `slot_perm_params(seed, tile_counter, n_slots) ->
(a, b)` per tile, `color_dust_permutation`, `cmy7_interleave_permutation`,
`cmy7_dither_bits`, `color_cell_permutation`, `cmy8_dither_bits`,
`color_block_assign_keys`.

`format/metadata` — 24-bit word: 1 version bit + 18 K bits + 5 known-zero.
`decode_metadata(equations: dict[int,int], max_index) -> MetadataResult(ok,
version, k, rank, n_unique, inconsistent)`; degree-24 LFSR coefficient rows,
GF(2) elimination; trust (`ok`) requires rank 24 AND `n_unique >=
MIN_METADATA_EQUATIONS = 48` distinct certified equations AND `version in
SUPPORTED_METADATA_VERSIONS` (frozenset {0}) — the version gate lives
inside the decoder, and close maps a full-rank unsupported version to
status `unsupported`. `equation_index(counter, stream_idx, n_streams)`,
`max_equation_index`.

`format/pilots` — `N_WORD_SITES=100` quota-grid word sites,
`word_site_cells_yx` / `filler_site_cells_yx` / `dust_site_cells_yx` /
`color_payload_cell_indices` site constructions; `encode_word(counter)` (18-bit
counter + 5 zero pads through BCH), `word_values` (scramble-XORed),
`decode_word(values100, row_seed, plane, erasure_idx) -> counter | None`
(refuses nonzero pads), `color_word_states(row_seed, counters, row)` /
`decode_color_word(states100, row_seed, row, erasure_idx=None)` (the row's
word pair: W/CM for cmy7/cmy8, C against the keyed W/Y for cmy — the lawful
set is the pair plus Y), `dust_state_values(row_seed, counters, row)` (the
cycle for cmy7/cmy8, the per-tile balance law for cmy; A1, 2026-10-12);
`color_word_zero_mask`, `plane_bits(row)`, `stream_bits(row)`, `cmy_soft_demap`.

`format/identity` — `Family` enum (K/CMY7/CMY8/CMY since A1), dispatch everywhere
(dicts whose KeyError names the family; the elif/else sites raise the same).
- Two constructors, one seed: `resolve_format_ref(ref: str) -> FormatRow`
  (string door) and `mint_format(*, pitch, family, rungs, sites, gen,
  tiles_yx) -> FormatRow` (parameter door). v2 resolve parses, then calls
  mint. Fossils are byte-matched and never minted. The seed is
  `FormatRow.seed`; there is no `str -> bytes` seeder.
- Two id spaces on the string door: the v2 grammar
  `pitch-family[-rungs][-pN][-vN]@TYxTX` and the `L:` fossil catalogue —
  fourteen seed-byte-frozen v1 identities plus the one v2-namespace row
  (sheet J, FORMAT-SPACE §8 row 15), matched byte-exactly, never parsed
  (all e029/e030/e032/sheet-I/sheet-J rows). The page domain is a receiver
  bound (`DecodeRequest.max_pages`), not a row field.
- **Canonical vs display (2026-08-30).** `row_id` is the CANONICAL v2
  spelling and `seed == b"holo/v2/" + row_id`: pitch always the reduced
  rational `{n}i{d}`, sites and generation always spelled, uniform rung
  triplets contracted. It reads no mutable table. `display_id` is the
  short spelling — class name where registered, defaults omitted — shown
  by diag/`schedule`/messages; never stored, never seeded. Both spellings
  resolve to the same row. Fossils carry `display_id == row_id`.
  `RunOpen` records both: `format_id` is the canonical `row_id`,
  `display_id` is the short spelling shown in the pane.
- `coding_printer_ref(coding_id, printer_id) -> str` — the e029 sugar: A4 +
  `MARGIN_MM[printer]` through `derive_field` to the legacy `L:` spelling.
- `build_site_geometry(row) -> SiteGeometry(word_cells_yx, extra_cells_yx,
  shorten_flat, payload_flat, slot_a, slot_b)` — per-tile slot permutation
  spans counter space (`max_pages * tiles_per_page`); K scramble planes
  are empty at init and filled per page on first touch
  (`identity.scramble_plane`). Arrays frozen read-only.
- `FormatRow`: row_id, display_id, seed, sites_seed, family, tiles_yx,
  pitch_in,
  n_sites, n_dust, dust_base_cycle, word_states, streams
  (`StreamFact`, below), pooled_fountain, bits/cells per mapper unit;
  derived: cells_yx, tiles_per_page, max_pages, payload_cells,
  n_transmitted_slots, tile_counter/tile_address. `sites_seed` is the
  frozen `holo/v1/sites/pN` bytes (accessor rename; src/holo still spells
  `family_seed`).
- `StreamFact(stream_id, plane_index, fountain_aux, rung_children,
  user_bits, symbol_bits, label_index, dither_aux)` (reshaped
  2026-10-12, CMY-RECEIVER-PLAN I-2; receiver-only, built only in
  `_streams_for`, copied by the analyzer's plane view). Exactly one of `plane_index` (a toner stream: K/cmy7
  `main` on `PLANE_K` = 3, cmy8 C/M/Y on 0/1/2) and `label_index` (a
  label stream: cmy hi/lo on 0/1) is set, refused otherwise at
  construction. `plane` is a property: `plane_index` on a toner stream,
  `StreamHasNoPlane(TypeError)` naming the stream on a label stream.
  `fountain_aux`: K `None`; colour main=0, C/M/Y=1/2/3 — the close
  dispatches on `is None` (cmy's pooled -v1 streams will carry `None`).
  `dither_aux`: the domain-13 per-stream dither aux, the stream index +
  1 (cmy8 C/M/Y 1/2/3, cmy hi/lo 1/2; design R6), passed as an integer;
  `None` for K and cmy7 (cmy7 dithers on domain 11, aux 0). Until A1 the
  two dither callers (`tiles._attempt_cmy8` — `tiles._attempt_stream`
  since A3 — and `color_sites.certified_projection` —
  `color_sites.certified_stream_bits` since A4) passed the stream NAME,
  which resolves to the same aux for C/M/Y.

`format/tile_codec` — `DEMAP_ITERATIONS=3` lives here; the attempt constants
`BASELINE_BP_MAX_ITERS=60 / RETRY_BP_MAX_ITERS=150 / BP_ALPHA=0.8` live in
plugins/tiles.py, nowhere else — every decode entry takes `max_iters`/`alpha`
explicitly, no defaults.
- `decode_tile(llr_flat, rate_id, site_flat, a_t, b_t, max_iters, alpha) ->
  (ok, user|None, n_iters, syndrome_ok, crc_ok)`; `encode_tile` (K GT).
- Frame calls return the 6-tuple `FrameOutcome = (ok, children, crc_invoked,
  crc_ok, certified_user_bits, extrinsic)`, children = ((n_iters,
  syndrome_ok), …): `decode_frame`/`encode_frame` over a `Bank =
  ((rate_id, shorten), …)`.
- cmy7: `CMY7_CODEBOOK` (2048, 4) base-7, `cmy7_soft_demap` (max-star with
  logaddexp fallback), `cmy7_demap_payload`, `cmy7_iterated_decode`
  (extrinsic prior clipped to ±LLR_CLIP between demap passes),
  `cmy7_encode_payload` (GT re-encode).
- cmy8: `cmy8_decode_stream` (per-plane, dither-signed), `cmy8_encode_payload`.
- Shared: `crc32_bits`, `tile_capacity`, `transmitted_positions`, `cell_map`,
  `states_to_planes`/`planes_to_states`, `cmy7_map`.

`format/fountain` — `BLOCK_K_MAX=16384`, `MAX_COLUMN_GROUPS=32`.
`column_groups(widths) -> ColumnGroups` is the column-group law
(docs/CMY8-COLUMN-GROUPS.md; one group at equal widths). `VolumeCode(k_total,
s_bits, seed, tiles_per_page, stream_id=None, fountain_aux=None,
n_streams=1, groups=None)`: per-page exact block quotas, keystream shuffle,
`block_row_of(esi)` (the fill position), `tile_slots(esi) -> TileSlots`
(the (row, group) pairs and bit edges a tile carries),
`systematic_positions(block)`; a colour stream (`stream_id` given) HONORS
the passed `fountain_aux` — identity's `StreamFact.fountain_aux` is
authoritative, never re-derived from the stream name. Pooled cmy8 is the
same code with `n_streams=3` and `esi = tile_counter*3 + stream_idx`; an
uneven triplet passes its `groups`, and a narrower stream's tile carries
consecutive column groups of the widest width.
`Decoder`: `add_symbol(esi, symbol_bits) -> bool` (conflicting values raise
`FountainIntegrityError` — the ONLY integrity exception format-side),
`try_solve() -> (k_total, s_bits)u8 | None` (packed GF(2) elimination per
(block, group), a group re-eliminated only when its row count changed,
solved groups kept; the Decoder persists across consults inside
`CloseProgress`), `block_status() -> tuple[BlockStatus, ...]` (per block:
have, needed, the scarcest-by-deficit open group's rows / rank / short,
groups_open, n_groups, min_rows — the count gate — and, per group in
group order, `group_rows` (every row a carrying tile brought, counted on
past the solve; an open group's rows are its pending items),
`group_rank` (K once solved, a failed elimination's until the group
gains a row, else None) and `group_solved`; every group of a block
needs `needed` rows; a one-group row has one entry).

`format/close` — runs on the merge thread. Envelope
`{sha256:32B}{len:4B BE}{data}`.
- `close_count_status(certs, row) -> (ready, counts|None)`;
  `close_count_ready(certs, row) -> bool` — the cheap count gate.
- `close_volume(certs, row) -> CloseResult(status, payload, k_total, blocks,
  symbols_used, reason, metadata_version)`, status in {verified, open,
  unsupported, integrity_failure}. Three unwrap gates: envelope sha, canonical
  K (`source_symbol_count(len, symbol_bits) == k`), zero padding bits.
- `metadata_from_certificates(certs, row)` — pooled rows use per-stream
  equation indices; opposite bits at one index raise (dict-shaped state; the
  engine's certificate merge must catch equal-index conflicts first).
- `CloseProgress` — the derived monotone close-state cell (P3-1 port,
  rebuilt in the column-group round, docs/CMY8-COLUMN-GROUPS.md §3.5): one
  metadata equation absorbed per certificate fold (`absorb`), the
  `Decoder`(s) built once at metadata trust and kept for the run — every
  certificate is fed to them as it arrives, so `count_ready` is the
  decoders' own per-(block, group) row counts, `close()` eliminates only
  the groups still open (solved groups persist), and `close_is_new` is
  the change predicate (an open attempt improves only on a symbol gain
  in an open block or metadata turning terminal). Close rows
  (`CloseBlockRow`) carry the block's `have` (tiles), `needed`, the
  scarcest-by-deficit open group's `rank` (None until it ran an
  elimination) and `short` (rows it still needs), `groups_open` /
  `n_groups`, and the per-group `group_rows` / `group_rank` /
  `group_solved` (2026-10-12, for the diag's group list); the decoder's
  `BlockStatus` additionally holds the scarcest group's `rows` and the
  block's `min_rows`, the count gate, which stay decoder-side.
  `metadata_rank` /
  `metadata_n_unique` ride CloseCheck. The engine's two consult meter
  reads accumulate into `EngineStat.consult_cpu_s`. `close_volume` and
  `close_count_*` are pure wrappers over a fresh `CloseProgress`.

RAISING: the snapshot functions above (`close_count_*`, `close_volume`) are
pure and never raise — integrity failures become results. `CloseProgress` is
the exception, deliberately: a metadata contradiction is TERMINAL AT FOLD
(ruling, close-state port) and `_MetadataGate.observe`/`settle` and
`CloseProgress._ingest` raise `data.IntegrityError` rather than swallowing it
into no-rows. `engine._close_decide` calls `progress.absorb` uncaught, so this
aborts the decode by design. Recorded, not adjudicated: absorb runs before the
`no_close` branch, so `--no-close` now inherits that abort path where the old
code only computed an `inconsistent` flag for display and continued.

## 6. Plugin layer

Every plugin exposes PURE module-level entry functions over immutable
inputs returning facts/events; engine.py wires them concretely (no dynamic
registry). The P1/P2/P3-internal imports (survey→intake, place→{pose, words,
cold}, cold→pose, pose→words) and color_region's two private splits are
ratified by contract amendment (driver ruling 13):

- `intake` — `ingest_captures(...)`: sha, per-capture declared dpi, per-plane
  `.npy` per ladder level (`build_levels`, exact-rational area kernel for
  off-grid scales), platen backing scalar, the ascending-ladder invariant,
  the Q2 refusal (same source sha at two declared dpis in one run is fatal;
  identical (sha, dpi) stays the duplicate drop). K-on-RGB luma.
- `survey` — `survey_capture(capture, planes, ...) -> CaptureSurvey` + event:
  structure-tensor regions, log-Otsu threshold, pitch vote + snap with the
  declared-vs-voted refusal (e033), boundary refinement. Once per capture, at
  native.
- `words` — `stage_a(...)`: slot sweep over `decode_many`, legality gates,
  W5 whole-word rival bar (`word_rival_rows`; empty cross-page set on 1-page
  domains). `ReferenceField` is n_dust-GENERIC: its site cells are the row's
  own (`word_site_cells_yx` + `dust_site_cells_yx(sites_seed, row.n_dust)`),
  so its mask and values agree with `identity.build_site_geometry` at every
  lawful `p`, not only at the printed p120 (FORMAT-SPACE §18; pinned in
  test_h3_plugins_placement.py).
- `place` — window plan/subdivision/ring neighbours, seed algebra
  (`consult_seeds`, `seed_supersedes`), the unified per-window job ladder
  (`run_window_pass`), gate constants (`min_support_for`, tier pricing),
  `done_covers` (the in-job done-gate consult over the projection the engine
  hands in via `WindowPass.done_cells` — the ONE projection lives in tiles).
- `cold` — `correlate_patch(...)`: the bit-exact FFT correlation sweep.
- `pose` — `fit_window_pose` (spectral lattice + phase, per-window crop),
  `sample_segment`, `refine_patch_pose` (E022 batched refine, always on),
  `audit_segment`, `ScoreMemo`.
- `calibrate` — K sampling in the v1 scores convention, per-window PAVA
  (`calibrate_window`/`resample_window` -> `WindowEvidence`), region ctx
  detector (`apply_region_context`, 9 bins, ±12 clamp). `freeze_owners` is
  kept as the oracle-parity spelling only — production cell ownership is
  decided at tile-attempt fire time, in tiles (driver ruling 8; ownership
  revisable until certification, D6 Wave 2).
- `color_sites` — format-truth site geometry, no store and no state:
  cargo site/cell masks, `suppressed_tile_codes` (a tile is suppressed
  only when EVERY stream is certified), `emission_mask`, and the
  knowledge pair `certified_stream_bits(row, fact, counter, certificate)`
  / `certified_projection` (§2, Knowledge).
- `color_model` (P5→P6 surface, src/holo names): `blind_component_bits`,
  `fit_qda` -> frozen `QdaModel`, `qda_log_scores`, `cmy7_relative_scores`,
  `cmy8_marginal_llrs`, dust-PAVA fit + support qualification
  (`fit_cmy8_detector`), `fit_cmy7_head` -> (head|None, reason) via Newton,
  `reference_states(row, page, cells_yx)`.  `fit_component_pava(scores,
  labels, weights=None)`: each binary class carries half the mass;
  `weights` (per row, cmy's chain passes state-balanced ones) spread a
  class's half over its rows, scaled by the class's heaviest row, so no
  weights or class-balanced weights are the unweighted fit bit for bit
  (cmy8 and A4b pass none).  `PavaMap.logit_interpolation` (constructor
  field, default False = the nodes joined in p, cmy8's bytes): True joins
  them linearly in log p/(1 - p), flat beyond the end nodes — set by
  cmy's chain only; the cmy8 logit line is its own owed A/B (2026-10-12,
  CMY-RECEIVER-PLAN A8).
- `color_chain` (cmy, R11; CMY-DESIGN §2.7): `fit_cmy_chain(scores,
  columns, kinds, site_keys, erased, bound) -> ChainFit` on the region
  QDA's held-out side (word sites admitted, dust, certified cells), split
  by `color_model.head_sub_split` into the maps' fit side and a disjoint
  validation side: three state-balanced logit PAVA maps — L_hi on the hi
  marginal, L_{lo|hi=0} on sY, L_{lo|hi=1} on sC - sM, each on the form
  `tile_codec.cmy_soft_demap` hands its consumer — floors cmy8's 6/2/3
  (marginal) and A4b's 40/6 + 20 validation rows (conditionals), an
  unqualified map's piece the raw statistic under the bound; adopted
  through cmy8's three-way gate (4-state NLL, total / word / dust, raw
  vs chain, every leg on the `ChainFit`; the dust leg is single-class at
  p120, all M).  `CmyChain.apply` folds the three back into (sC, sM, sY)
  (`fold_hi_first`, exact under equal priors).  Erasure: a dead lo fits
  L_hi alone, a dead hi takes no chain (reason `hi_erased`).  The head
  SLOT is `DetectorFit.head` (cmy7's `Cmy7Head` or cmy's `CmyChain`,
  renamed from `cmy7_head` at A8), applied in `evidence_with_divisor`
  before the context matrix, the erasure and the bound; cmy's
  `detector` stays None.  `StackResult.chain` carries the fit record.
- `color_region` — `region_job(row, geometry, windows: RegionWindow…,
  label_windows, planes (r,g,b PlaneRaster), certificates, StackConfig,
  capture_id, level_index)` per (capture, level, page): anchoring/NCC/
  Theil–Sen registration, ownership + split, the calibrated-head arm ladder
  (A0/A1 -> head+satfloor30, cmy's chain in that slot -> ctx matrix),
  emission (L-inf 20 /
  marginal+clip+PAVA), pool-law masks; facts = `ColorEvidenceRow` per open
  window (the fit verdict rides the `CalibrateAdopted` event; the
  RegionColorModel fact is deleted).
- `tiles` (P7) — fire-time tile assembly (D6 Wave 2, no stored freeze):
  `assemble_tile` reach-consults the covering windows/colour rows via the
  store's cover maps and cuts this tile's cells from their immutable
  evidence arrays, per-cell owner by held-out loss via `lib/owners` at
  tile scope (order key total: heldout_logloss, extent_cells,
  region_index, plane); `assemble_union` = the same cut for every capture
  whose ladder holds one exact-rational ppc — union subjects are
  `(page, ty, tx, ppc)`, minted only where >=2 distinct captures hold
  evidence at that ppc (a capture's own rungs never pair; the ladder is
  strictly ascending, so one lane per ppc per capture).
  `attempt_key(page, ty, tx, stream, stage, components)`
  keys the retry idempotence floor on the (capture_id, level_index)
  component signature; `attempt_tile` (K + colour chains;
  scan/union/retry150/cond150 stages; `sibling=` a certified label
  stream's sequential bits, which `stream_llrs` hands to cmy's
  conditioned demap and refuses on a toner stream; `attempt_many` passes
  it to every listed stream, and only `tiles.cond` lists one),
  certificate mint with GT re-encode + the C-7 known-site
  `np.array_equal` check, `printed_cells_for(row, geometry, page, ty,
  tx, user_bits) -> (64,64)u8` (the P8 surface),
  `merge_certificate` (conflict -> IntegrityError), `done_tile_grid` +
  `project_done` (the ONE done projection) + done-grid helpers.
- `refine` (P8) — RF1, core and always on: certified labels + floors +
  coarse/fine pose grids + adoption gate (`MIN_HELDOUT_GAIN`) + re-read via
  `revised_placement`; eligibility-gated (`refine_eligible`: certified +
  uncertified in reach), priced 200. K windows only — colour windows get
  `refine.color`. The gate scores the CONTEXT-CORRECTED detector by default
  (RULINGS D3, v1's `_fixed_detector_logits`): where the window's own evidence
  carries the region's adopted context, `context_logits` re-bins the eight-
  neighbour ink counts over each scored pose's own cells and adds the region's
  nine offsets before the held-out logloss and the pilot-mismatch clauses. The
  candidate SEARCH still ranks on the marginal fit, and `--refine-gate marginal`
  restores the pre-D3 gate byte-for-byte. Reads the region ctx cell through
  `store.region_ctx`; no declared read of its own (a decision that changes what
  a window is read with rewrites that window's evidence row, which the row
  already subscribes to).
- `color_refine` (`refine.color`) — the colour refinement lane (v1
  color_refine numerics verbatim): flattened (cell, plane) presence-bit
  labels (furniture all three planes via reference states, certified cargo
  via `color_region.certified_projection` through `build_window_rows`), K's
  two-stage grid on a frozen per-plane affine calibration from the baseline
  pose, adoption gate = held-out gain + furniture non-regression
  (`FURNITURE_LOSS_SLACK` 1e-9); v1's two crop-free pre-gates (no certified
  cargo / certified-complete) refuse in prepare; adopted revisions fold as
  Placements with route `refine` and re-fire the colour lane through the
  ordinary declared reads. Emits `refine.RefineOutcome` (shared writer
  domain `refine`), priced 200, never fires on a revision.
- the residue rows on cmy (2026-10-12, CMY-RECEIVER-PLAN A7; CMY-DESIGN
  R25): cmy8's rows TRANSLATED through the label mapping, not new rows.
  `tiles.planek` reads a stream's TONERS, `plane_k.stream_toners(row,
  stream_id)` over `tile_codec.stream_toners` — the planes whose presence
  bits sum to the stream's bit over the row's alphabet: a cmy8 toner
  stream its own plane, cmy's hi (C, M) and lo (C, Y), K's and cmy7's
  `main` none (the birth gate `plane_k.readable`). A label stream's job
  is `plane_label.label_job`: each toner read by `plane_k.plane_reads`
  at its own plane field on the PROJECT readout (`label_toner=True`;
  `isolated_scores`/`heldout_loss_at`/`choose_offset` take `mode=`,
  default subtract = cmy8's bytes), the presences summed, priced by the
  K calibration against `plane_k.stream_labels` (the label on cells whose
  three planes are proven), written into every toner column
  (`transient_row(read, evidence, toners, arity)`: (L, L, 0) for hi,
  (L, 0, L) for lo, which `cmy_soft_demap` reads as exactly L) and
  attempted as that stream's codeword. `tiles.swim`'s level table and
  objective floor are the row's alphabet's (`swim.state_levels(states,
  values, state_ids)`, `swim.min_objective_cells(row)`: cmy's four
  states 32 cells, cmy8's eight 64). `tiles.local` runs cmy as it stands
  (R11): its colour arm is `color_region.region_job`. `tiles.uplift`
  stays unborn for cmy (`color_arms`, CMY: ()).

## 6a. Engine wiring (engine.py)

The store (store.py) holds ALL domain state behind keyed accessors —
private dicts, accessors the only door (grep-provable: no `store._X`
outside store.py and store_folds.py) — and the engine holds ALL
scheduling state; plugins
stay pure. Each plugin row is a frozen `PluginDescriptor` declared at the
bottom of its module (`name, subject_kind, born_by, subjects_of, reads,
eligible, stage, cost, retire, prepare, produces, prices`);
`engine.DESCRIPTORS` is the collected tuple and the engine knows nothing
else about any plugin — `stage` names an opaque per-row stage,
`cost(store, subject, stage)` returns the price in the plugin's own
literals, and `retire(store, subject)` returns the CAUSE the row stopped
for — a string of the row's own vocabulary, or `None` while it lives —
which the engine tallies (`EngineStat.retire_causes`) and stamps on
`WorkerRetired` without ever reading it.

**THE READ-SET LAW (2026-09-21).** A worker's declared reads are FIXED
AT BIRTH and are its true inputs: `reads` is evaluated when the fact
that creates the work is folded, and nothing re-derives it for a
standing worker on a wake (`test_h3_lifecycle` asserts that over
engine.py's own source; `rederive_on` existed for one day and the
amendment took it out). The ONE way a live worker's reads grow is a
RE-BIRTH: its birth fact folded again means its inputs may have grown
with it -- a re-placed window has a new reach and possibly a new page
-- and `engine._births` finds the standing bookmark and appends the
fresh keys. Keys the row no longer needs stay subscribed, because
over-declaring costs a wake and under-declaring loses a re-arm; they go
when the row retires, and a RETIRED row takes no new ones — a birth
fact folded after it left is counted and dropped, never re-subscribed.
Every DERIVED relation -- which tiles a window
reaches, which windows a tile's certificate concerns, which parent a
child's settling concerns -- belongs to the STORE, which routes a
change to the key its owner already holds, rather than to a
subscription the row has to keep re-deriving.
`python -m holo.receiver schedule` prints the derived table;
`src/holo/receiver/docs/SCHEDULE.md` carries that block verbatim plus its prose.
Single-writer-by-domain is verified at startup, WITHOUT EXEMPTIONS
since 2026-09-21 (no two descriptors share a produced fact type, except
Certificate's source tags and same-prefix rows like tiles.*). `revisit`
was the one exemption — it declared the four fact types its delegated
place/calibrate bodies emitted — and dissolving that row emptied
`REARM_PLUGINS`, which went with it. engine.py now spells no plugin
name at all, and `test_h3_lifecycle` asserts exactly that.
`store.merging_sleep_version(subject)` is the ONE engine-provided
input-revision accessor a fold may read (since 2026-10-03, `1d5f7a81`):
it answers the merging job's bookmark version, or None when anything
woke that bookmark while the pass was in flight, and it is what makes
dormancy lawful (a recorded version compared at fire time) without
giving the store a second, private notion of scheduling state. No fold
reads a bookmark otherwise — `store.worker_version(plugin, subject)` is
read by a ROW (`place_sched.dormant`, comparing the stamp at fire time),
never by `store_folds`, and `test_h3_lifecycle`
(`test_no_fold_reads_an_engine_bookmark_by_plugin_name`) asserts it.

Lifecycle: FOLD (typed store update) returns the FactKeys the fact
REALLY changed — value compare for scalars/small tuples,
`np.array_equal(…, equal_nan=True)` on written array cells; an unchanged
write touches nothing. BIRTH matches the fact against `born_by`,
enumerates `subjects_of`, evaluates `reads`, registers the
WorkerBookmark in the inverted index and pushes at price (a birth that
finds a standing bookmark only adds the fresh read keys). WAKE bumps
each subscribed bookmark's version and pushes at its CURRENT price (the
row's own `cost`, FIFO-per-price seq — the engine does no arithmetic on
a price; engine-side aging was deleted 2026-08-29). A PUSH consults
`retire` FIRST (2026-09-21) and unregisters on a cause, before the row
prices itself: a wake that leaves the price unchanged returns at
`seat_stands` and is never popped, so a clause that came true while the
row sat on a standing seat would otherwise wait for a pop it may never
get — measured on sheet H, where `place` took 35,418 wakes and retired 0
windows in 36 minutes. THE PRECONDITION IS MONOTONICITY: a `retire`
that can go false again would kill a live row, so each row's clause is
monotone in the certificate frontier (`tiles.uplift`'s was narrowed to
its monotone half for this, its window test staying in `eligible`).
FIRE pops cheapest, consults `retire` again, skips on the version floor,
records the version, then `eligible` -> `prepare` -> submit pure job
(`None` = costless skip). Every seat and every retirement is one generic
event — `WorkerSeated(plugin, subject, stage, cost)` when a NEW seat is
minted at a (stage, cost) the row was not last emitted at, and
`WorkerRetired(plugin, subject, cause)` — and the window views filter
them on `plugin == "place"`. AT MOST ONE JOB IN FLIGHT PER WORKER: a wake landing
mid-flight sets the bookmark's pending bit and the worker re-pushes when
its result merges — merge order equals preparation order WITHIN ONE
(plugin, subject), which is why no bookmark carries a lane_generation.
That is not a whole-CELL property (corrected R6, 2026-09-09): the
placement cell has three producers — place and refinement (two
rows; `revisit` was a fourth until 2026-09-21) — and every fold is ranked against the placement STANDING AT MERGE
TIME, not the one its job was prepared from (a revision is rebuilt from
it), so the cell's ordinal is what orders those writers. The version floor
is the engine's ENTIRE staleness story: there are no content digests and
no tried-input sets anywhere (D6 addendum 6); a re-fire on genuinely new
data is ordinary work at its declared price. There IS one stamp, outside
the version floor and owned by the payload rows, not the engine:
`AttemptFact.generation`, the tile-lane or footing counter a verdict was
decoded at (§2). `tiles.retry` fires while its baseline is failed AT the
current generation, `tiles.cond` once per generation, and the chain head
skips a cut it already read at the current generation —
`tiles_sched._scanned_at` (scan, since `162f1227`) and `_unioned_at`
(union, since 2026-10-18, SCHED-LIFECYCLE-REVIEW D2). A wake on such a
row is still a wake; the stamp decides only whether `prepare` has
anything to read. The place ladder's stage state (tried
candidate ids, stage/wide/cold spends, subdivision, dormancy, parent
afterlife) is a store cell (`place_stage` accessor, `WindowState`,
touched as `("place_stage", wid)`) — and since 2026-09-21 `place` READS
that key, so the ladder climb is an ordinary wake and the engine carries
no place code at all: `_place_repush` is gone, and THE QUARTERING IS A
RUNG (`place.STAGE_SUBDIVIDE`, priced at the ring's 40) rather than a
fold that creates facts — its pixel-free job returns the four child
`Window` facts, which carry their parent's id, and the outcome that
marks the parent subdivided. The rung is offered ARMED (the two
refusals that quarter on the spot) or LAZY (every rung spent), never to
a window under the subdivision floor, and always behind RING, so a seed
that arrived while the window waited is tried before it is cut up. A
parent's afterlife reaches it on ITS OWN `place_stage` key: the STORE
routes a child's settle into the parent's state (`_settle_child`) and
emits that key when the last child settles without a pose, or when one
places and cancels the afterlife for good — the parent subscribes to
nothing of its children, which is what the read-set law above requires
("settled" is counted from the folds alone, so a child the done gate
retired does not count — deliberately, since a done quarter is already
read). A parent with live children
latches `state.retired` like any spent ladder, but its BOOKMARK is held
by `place_sched.afterlife_owed`: un-retiring a WindowState is a store
write, un-retiring a bookmark would be an engine call from a fold, so
the row the afterlife will need must never leave. `afterlife_owed`
reads the parent's state alone and goes false the moment the afterlife
is used or a child places. Dormancy is
a recorded worker version compared at fire time, cleared by any later
wake — measured from AFTER the fold's own place_stage wake, because that
key is one of `place`'s own reads and a window that put itself to sleep
would otherwise be woken by the fact that put it there (a livelock, found
on the colour sim). A window that OWES a quartering is not asleep: that
rung is work it holds, not work it waits for, and it goes back to sleep
on the same terms once the rung has run. Prepare
functions never write state.

THE DONE GATE (2026-08-30, docs/DONE-GEOMETRY.md in this
architecture): `store.window_fully_done(wid)` is true when every tile
the window could still contribute evidence to is certified in EVERY
stream — placed windows on their derived reach against `done_grid`,
unplaced ones on `window_extent_done` (the region's projected
`done_cells` covering the supported extent; off-page tiles ignored).
Certification is terminal, so the verdict is monotone in the
certificates and the suppression cannot cost a certificate. `place`
consults it in its stage (since 2026-10-03; in retire before, cause
`done_covered`) — the unplaced verdict runs through the region's latest
adopted poses and can shrink under a revision, so the store keeps the
last verdict per unplaced window and emits `(window_done, wid)` for one
an adopted affine re-opens — and `calibrate` in eligible; `refine`/`refine.color` need no
call (their own reach predicates already refuse), and the payload rows
are never gated. Suppression is fire-only — standing evidence, tile
cover and the region context fit are untouched.

THE CELL-CLASS LAW (DESCRIPTOR-PLAN addendum 14, ratified 2026-08-29
night): store cells are quality-ordered DECISION cells, DERIVED cells
(plain change detection), append-only sets, or frozen inputs. For a
decision cell the ORDINAL IS A PROPERTY OF THE CELL SCHEMA, not of any
producer, and `store._adopts` is the gatekeeper: better-or-no-op, with
the cell's own deterministic tie-break. Plugins only compute honest
values. The schema must answer, once per cell, how values fitted on
DIFFERENT EVIDENCE BASES compare. Three cells are converted, with their
answers in `data.py`:
- placement — `placement_ordinal = (route == ROUTE_REFINE,
  basis_field_revision(refine_basis), certificates in refine_basis,
  -quality)`. Route-major: an adopted revision outranks any original
  (its held-out gate is the proof); then the basis, so mismatch scalars
  from the chain, word and cold searches are never compared across
  evidence bases. FIELD-MAJOR OVER THE COUNT (R6, 2026-09-09): a colour
  basis names the page field it was fitted through as well as its
  certificates — `data.FIELD_BASIS_KEY`, the one string-headed entry,
  excluded from the count — and two poses fitted through different
  fields had their losses measured through different sampling
  geometries, so depth and loss do not compare either. A candidate
  fitted on FEWER certificates may therefore displace one fitted on
  more: the proof is the producer's held-out comparison against the pose
  standing when its job was prepared, through the field that job was
  prepared with — not the newer revision, and not the field standing at
  the merge, which is why the race between producers is settled here and
  not by a preparation order. An older field never displaces a newer one,
  and the row stays eligible while basis and page disagree, so that work
  returns at the current field instead of being lost. A K basis carries
  no marker, reads revision 0 and keeps its pre-R6 order exactly.
- lattice seed — the declared commutative merge below: max support
  wins, ties to the smaller producing-window ordinal.
- region ctx — `region_ctx_ordinal = (adopted, -validation_logloss)`.
  QUALITY-ONLY, and this is the one cell whose comparability question
  is ANSWERED PROVISIONALLY. OPEN FOR RULING (raised by the law's own
  build, 9a15a51, and recorded here so it does not live only in a
  commit body): ctx quality is measurably NON-MONOTONE over growing
  evidence (0.0201-0.0216 oscillation), so a later fit made on a larger
  evidence base can score worse and be refused. Zero certificate effect
  on the sims; unproven on real sheets. The choice is an
  evidence-base-major ordinal (the placement/seed precedent) versus
  quality-only. Since 2026-10-03 (`037440da`) a refusal costs the
  decision and nothing else: a `CtxOutcome` carries no rows, and a
  refused decision folds as nothing (no key, no row touched). The
  correction lives at the FOLD HEAD — `_fold_evidence` reads every
  accepted, uncorrected `WindowEvidence` through the region's standing
  adopted decision as it arrives (`calibrate.apply_standing_context`,
  idempotent), so a window that joins the region after the best-scoring
  fit is corrected by that fit — and an ADOPTED decision is stored and
  then caught up over every accepted row standing in the region at
  merge (`_fold_ctx_outcome`). The `held` escape and the batch drop of
  the job's prepare-time rewrites (last-write-wins over any newer fit
  that merged while the ctx ran) went with that commit.
NOT converted: the colour decision, which survives the deletion of the
RegionColorModel fact as `ColorEvidenceRow` (it carries a non-optional
`heldout_logloss`, the quality field the law asks for) and whose fold
is still bare change-detection last-write-wins, gated only by its
producer's stack gates. Addendum 14 names four decision cells; this is
the fourth. No disposition has been ruled — but it has now been
MEASURED, on two paper sheets and the sims
(measure/sched_trace/LOGLOSS-2026-09-20.md, the fold trace
`sched_trace_folds` and the measurement hatch `HOLO3_COLOR_ROW_ADOPT`):
the colour row is written exactly TWICE per window in a whole run (one
assembly, one lane head fit), so it does not oscillate — 0 sign changes
on both sheets, 96.6% / 87.7% of second writes improve the loss. The
`WindowEvidence` cell DOES oscillate on a K page (sim: 38 sign changes
in 48 re-emissions, an uncorrected value alternating with a corrected
one). And the comparison the law asks for is not yet well posed for
either cell: labels are format truth PLUS this run's certificates, so
every re-fit is scored on a LARGER held-out population than the row it
displaces. An evidence-base-major ordinal, as `placement_ordinal`
already uses, is the shape that question points at. The ruling is
Germano's; nothing in the tree anticipates it and the default fold is
unchanged.

Engine-owned laws: window/patch ordinals are plan-derived per (capture,
level) — cumulative `window_plan` bases in region order, children at
`plan_total + parent.ordinal*4` (ruling 10); the lattice-seed cell is a
declared commutative merge — max support wins, ties to the smaller
producing-window ordinal (no byte compares); region pitch is the median
over the region's placements, recomputed at placement folds — the key
`("region_pitch",…)` is touched only when the median moves the
`calibrate.sampling_pair` (halo, aperture) it is read through (since
`037440da`), and re-arms every sampled window of the region
(fixed-point deterministic); the RF1 crop reuses calibrate's
`window_crop` median-fill
convention (ruling 11); the colour `RegionWindow` is built from
`Placement` in color_region (rotation-composed level-frame affine, +0.5
cell-centre shift, `pose_points` matmul spelling — ruling 14); the
certificate fold is the first line of the opposite-metadata-bit defense
(close's raise stays as the belt, ruling 5). Certificate-growing merges
trigger the close consult (count gate, then `progress.close()`;
`--complete` defers, `--no-close` observes); VERIFIED breaks the loop and
finishes at once. It does NOT drain: the jobs still in flight (at most
one per worker) keep running to their end on the executor's threads,
their facts are never merged or snapshotted, and the process exits when
they return — `executor.shutdown(cancel_futures=True)` has nothing to
cancel, since nothing is queued beyond the in-flight set. An orderly
STOP is the other way round (since `80194fac`): the first signal stops
scheduling and DRAINS, merging every in-flight result, then runs the
deciding consult; a second signal abandons. The close is NOT a
descriptor.

## 6b. Row lifecycle (T3, 2026-09-21)

**The invariant.** *A row is born by the fact that CREATES its work and
re-armed by the facts that CHANGE its input; nothing is re-armed by
facts whose change cannot alter its output.*

Eighteen rows (`tiles.cond` joined 2026-10-12, CMY-RECEIVER-PLAN A6).
`reads` is the key FAMILY set `python -m holo.receiver schedule`
derives from the row's own `reads` function — SCHEDULE.md's generated
block is the authority and this table is its lifecycle reading. `retire` is the
row's own cause vocabulary; the engine tallies
the strings and never branches on them.

| row | subject | born by | reads (kinds) | stage(s) | retire cause(s) | produces |
|---|---|---|---|---|---|---|
| `survey` | capture | Capture | — | survey | `surveyed` | CaptureSurvey |
| `place` | window | Window | lattice_seed, live_pages, place_stage, pose_affine, **window_done** | ring, **subdivide**, word_centre, word_rest, wide, cold_live, cold_rest | `placed`, `exhausted` (`done_covered` until 2026-10-03: the done gate suppresses through the stage since) | Placement \| LatticeSeed \| PlaceOutcome |
| `calibrate` | window | Placement | pose_affine, region_pitch | calibrate | — (lives while the window is sampled) | WindowEvidence |
| `ctx` | region | WindowEvidence | evidence_fit | calibrate | — | CtxOutcome |
| `color` | lane | Placement | lane_poses, page_certs, plane_field, pooled_ctx | calibrate, color_refit | — | ColorEvidenceRow \| ColorCtxPopulation \| ColorLaneFit |
| `color.pooled_ctx` | page_rung | ColorCtxPopulation | color_pop | pooled_ctx | — | PooledColorCtx |
| `tiles.scan` | tile (per lane) | WindowEvidence \| ColorEvidenceRow | color_row, evidence_fit, evidence_read | payload | `certified` | AttemptFact \| Certificate |
| `tiles.union` | tile (per footing) | WindowEvidence \| ColorEvidenceRow | color_row, evidence_fit, evidence_read | payload | `certified` | AttemptFact \| Certificate |
| `tiles.retry` | tile-stream + origin | AttemptFact | **attempt** | payload; retry_cmy (cmy) | `certified` | AttemptFact \| Certificate |
| `tiles.cond` | tile-stream + origin (retry's) | AttemptFact \| Certificate | attempt, tile | payload | `certified` | AttemptFact \| Certificate |
| `tiles.local` | **tile-lane** | AttemptFact \| WindowEvidence \| ColorEvidenceRow | **attempt** (scan, union), tile; on colour plane_field, **pose_affine** | local | `certified` | AttemptFact \| Certificate |
| `fields.collect` | capture_page | Placement \| Certificate | lane_poses, page_certs | collect | `page_done` | FieldObservations |
| `fields` | page | FieldObservations | field_obs | solve | — | PlaneField |
| `refine` | window | Placement | evidence_fit, evidence_read, pose_affine, pose_route, tile | refine | `reach_exhausted` | RefineOutcome |
| `refine.color` | window | Placement | plane_field, pose_affine, pose_route, tile | refine | `reach_exhausted` | RefineOutcome |
| `tiles.uplift` | lane-page + arm | AttemptFact | lane_poses, page_certs, plane_field | uplift_a3, uplift_a4b | `page_done` | AttemptFact \| Certificate |
| `tiles.planek` | tile-stream | AttemptFact \| WindowEvidence \| ColorEvidenceRow | **attempt** (scan, union), plane_field, **pose_affine**, tile | planek | `certified` | AttemptFact \| Certificate |
| `tiles.swim` | **tile-lane** | AttemptFact \| WindowEvidence \| ColorEvidenceRow | **attempt** (scan, union), plane_field, **pose_affine**, tile | swim | `certified` | AttemptFact \| Certificate |

`produces` is the descriptor's declaration, which the single-writer
check reads. `place`'s four CHILDREN come out of the subdivide RUNG's own
job (§6a), ahead of the outcome that marks the parent — not out of a
fold. The paragraph first written here, with `store_folds._subdivide`
minting them at fold time, described the tree before the 2026-09-21
amendment (LIFECYCLE §1a) and stood stale until 2026-10-03.

Bold entries are what 2026-09-21 and the 2026-10-03 repair wave
changed. The shape of the change is one thing throughout: every residue
row used to subscribe to the RAW EVIDENCE its predecessor reads —
`tiles.retry`'s read set was literally `tiles.scan`'s — so the ladder
existed only at birth and the rungs ran each other's work concurrently.
Now `tiles.retry` reads its own baseline verdict, and the three residue
rows (`tiles.local`, `tiles.planek`, `tiles.swim`) read the CHAIN
HEAD's verdicts only — scan and union, `local_ctx.READ_STAGES` (since
`162f1227`; a retry150 failure ARMS all three and a local150 failure
ARMS `tiles.swim` only, through the footing ledger, waking nothing, its
cut not being the one they build) — plus
the inputs each alone has (the page field, the neighbourhood's
certificates, and for the sampling rows the poses they sample through:
`tiles.local` on colour since 2026-10-03, `tiles.planek`, `tiles.swim`).
The same three are re-born by `WindowEvidence` / `ColorEvidenceRow`
(`local_ctx.COVER_BIRTH_FACTS`, `c078d307`), which only EXTENDS a
bookmark their stages already armed with the new cover's reads, never
creates one; `tiles.swim` is one subject per tile-lane since `50a7395e`
(one fit reads every armed stream), `tiles.planek` stays per
tile-stream. INV-G1 is what makes dropping the evidence keys safe: every
generation bump happens inside a fold that also emits a key the chain
head holds, so the head re-decodes and its new verdict re-arms the
rungs.

FIVE rows have no retire cause at all and that is correct: `calibrate`,
`ctx`, `color`, `color.pooled_ctx` and `fields` each stay live as long
as their subject exists, because a later pose, evidence set or
observation can always change what they would publish. They leave the
frontier through `stage() -> None` and the version floor instead.

`revisit` was one more row until 2026-09-21; §6a says why it went.

On a cmy page (2026-10-12, CMY-RECEIVER-PLAN A7) `tiles.planek` is born
for both label streams by the same failed verdict as on cmy8 — its gate
is "the row has streams planek can read", not the family — and reads
the page field of BOTH toners its stream sums (`plane_field` keys for
C and M on hi, C and Y on lo); `tiles.swim` and `tiles.local` are born
as on cmy8. Of the colour rows a ONE-capture page reaches, `tiles.uplift`
is the one that never seats a cmy subject; `tiles.union` and
`color.pooled_ctx` need two captures and were MEASURED on cmy on
2026-10-12 — machine 4's two-capture `--complete` runs of e044's sheets
(§044.6 sheet B: union 64, pooled_ctx born, 25 fits; §044.7 sheet A:
union 62) — so the "unproven" of A9 is history; what is still owed is one
bounded two-capture sim record on the slow lane (the receiver plan §5).

`tiles.cond` (CMY-DESIGN R5) is the conditioned label stream: a label
family only (`tiles_sched._label_sibling` is None for every toner
stream, so K, cmy7 and cmy8 never birth it), the retry's subject but
the SCAN's price -- 20 + 2 x rung on every family (`tiles_sched._cond_cost`),
while the cmy retry sits at 241 + 2 x rung (`retry_cmy`, the owner's price
balance, 2026-10-18: above the residue rows' first fires, below cold
placement; `tiles_sched.RETRY_CMY_COST`) -- its baseline the stream's current ordinary verdict `failed` OR
`below_attempt_floor` (`tiles_sched.COND_BASELINES`, `_baseline_cut`;
`tiles.retry` keeps `failed` alone, `RETRY_BASELINES` — the 2026-10-12
implementation review's F2: the sibling's certificate changes the
evidence, so a below-floor marginal is a baseline for conditioning and
not for a retry), BORN by that verdict with the sibling already certified
OR by the sibling's certificate with that verdict standing and current,
whichever lands second; it reads the retry's key and the sibling's
`tile` key, is eligible at most once per generation (a conditioned
verdict of any outcome at the cut's current generation holds it, as
`_scanned_at` holds the scan), and decodes at the retry's budget
(`cond150`) with the sibling's label bits re-encoded from its
certificate (`color_sites.certified_stream_bits`).

NOTED, NOT CHANGED — `color`'s stage duality. One row carries two
different kinds of work under one bookmark: the per-window assembly
debt at `COLOR_COST` and the whole-head refit at `COLOR_REFIT_COST ×
fits`, selected in `_color_stage`. Its `cost` therefore has to read a
store cell to avoid pricing the refit off assembly fires. Two kinds of
work under one bookmark is what forces that, and splitting them is a
separate piece of work with its own measurement.

## 7. Threading model

- Jobs are pure functions over frozen snapshots (window id, capture ref,
  pose/calibration snapshots, params). No locks anywhere.
- Results split into FACTS (certificates, poses, words, equations, counters,
  events — merged serially by the single writer; commutative, so the payload
  is independent of worker count) and REDUCTIONS (calibration evidence
  reduced worker-side to sufficient statistics, never raw per-cell dumps).
- Wake = one-bit version bumps through the inverted FactKey index, fed by
  accessor change-detection at the write; the version floor at pop is the
  only staleness mechanism. Dirty tiles and region refits re-arm the same
  way (rulings 08-5, 11-1).
- Determinism law C-12: every ordering is on values, never arrival order —
  ownership key `(heldout_logloss, window-extent-tuple, plane)`, R5 seed
  reduction, sorted capture shas in unions, sorted work keys in tiers.
  `--workers N` is PAYLOAD-BYTE-identical for all N. That claim is scoped
  to the payload: `--workers 1` runs are fully deterministic end to end
  (certificate sets, job counts, events) and are the reference for every
  gate; at `--workers N>1` the race-mode close can fire at different
  frontiers, so the CERTIFICATE SET and job counts vary run to run
  (measured 84/90/80 certificates on identical code) while the recovered
  payload bytes stay identical. PAGE-DOMAIN 2026-09-01: fire-time floors
  on a growing live set make intermediate certificate sets
  schedule-dependent across N even without the race-mode close. Never
  gate on a workers-N certificate set.
- Priced frontier, each literal owned by its plugin: survey 10,
  calibrate/ctx/color 15, payload 20, ring 40, word_centre 60,
  word_rest 80, wide 120, refine/refine.color 200, retry_cmy 241
  (tiles.retry on the cmy family only, 2026-10-18), cold_live 250,
  cold_rest 260 (PAGE-DOMAIN 2026-09-01: cold last by price, above
  swim; no dryness gate); +2 per rung (+20 per rung cold), +5 child.
  The engine owns no numbers: cost is a scheduling function of
  the plugins alone (ruling 2026-08-29; the rework-aging formula was a
  holo2 artifact, deleted). `python -m holo.receiver schedule` prints the
  resolved ladder with the same-price peers marked.
- Memory: per-window crop+filter (C-2), sparse tile evidence (C-5), one
  read-only mmap view per worker per plane.

## 8. Arm doors and the schedule-on-residue law

Arms (u-lanes, color_field, A3/A4b) are NOT built in v1; the doors they
need ARE. One door is now WALKED THROUGH: the `fields` row solves a
per-page, per-plane registration field and every colour sampler reads it
through `lib/page_map` (always on for a colour family — see `PlaneField`
in §3 and the two `fields` bullets in SCHEDULE.md). The rest stand open:

- `offsets_px: (N,2)f64 | None = None` on every point-sampling helper
  (`pose.sample_segment`, `calibrate.scan_points_yx` and the
  calibrate/resample window entries, `refine.sample_at`/`refine_window`).
  `None` is bit-identical to no arm. This is the COLD-SEARCH door: what
  fills it is `page_map.raster_points` from a page hypothesis, and until
  a hypothesis holder wants per-channel templates nothing passes it
  (PAGE-FIELD-DESIGN §2.8, PAGE-FIELD-PLAN §3).
- `offsets_override` in colour registration (color_region; ruling 11-6).
  Arms attach at sampling, never at placement.
  A SECOND door now stands beside the mapping: `offsets_of`, a callable
  handed the head's own `WindowRows`. Same tier, one rung more specific
  than the standing plane fields and one less than the mapping, and it
  exists because an arm that derives its offsets from cell POSITION
  should not have to reproduce the row order the head will build —
  `plugins/swim.py` walks through it. Not passing one is bit-identical to
  no arm. The callable answers PER PLANE and may not answer `None`: that
  spelling belongs to `field_offsets` and means the whole PAGE has no
  solved plane, which drops the region's corrected arm; a window with
  nothing of its own to contribute answers `(None, None, None)` and is
  read at its own pose while the region keeps its arm (2026-09-08).
- The evidence-lane tag (`TileEvidence.arm`) died with the stored freeze
  (D6 Wave 2, fire-time assembly); when an arm lands it re-cuts that door
  as an evidence-side lane on the facts it emits. Arms re-attempt with
  new LLRs only.
- `Certificate.source` — the producing plugin/tier; pane C and the per-plugin
  accounting price every arm individually.

The law (RECEIVE-DESIGN §6.2a heritage): an arm that cannot prove universal
non-regression schedules on the RESIDUE — only subjects the core left
uncertified — and is therefore monotone by construction; one certificate
pays its cost. When built, each arm gets a repeatable `--arm NAME` flag;
there is no `--refine` flag because RF1 and E022 refinement are core.

## 9. CLI

```
holo3 decode SCAN... --dpi F [--dpi F ...] (--format REF | --coding ID --printer ID)
             [--max-pages N] [--workers N] [--complete] [--no-close]
             [--refine-gate context|marginal]
             [--diag PORT] [--run-dir DIR] [--resume STATE_FILE] --out FILE
```

Exactly one `--dpi` per scan (positional order, each capture at its own
declared dpi — mixed-resolution runs are legal); duplicate scans fold by
sha; the same source at two different dpis refuses (Q2); `--out` refuses
to overwrite; `--max-pages N` caps the possible page domain (absent =
all addressable pages of the row; `N < 1` and `N > row.max_pages`
refused by name; `--max-pages 1` is today's null control). `--format` and `--coding/--printer` are mutually
exclusive. `--complete` defers the close until the frontier is exhausted;
`--no-close` observes only (diagnostics). `--refine-gate` picks the detector
the black-and-white refinement adoption gate scores (default `context`; see
the `refine` bullet in §6). Prints the six-row status block,
the per-plugin accounting table, and on success `VERIFIED <n> bytes sha256
<hex>`. Payload written atomically. Exit 0 verified / 2 open / 1 error. Invoke as
`env/bin/python -m holo.receiver …` (no console script is installed).

**Test lanes.** `env/bin/python -m pytest src/holo/receiver/tests -q` is the fast
lane (~14 s, no decodes; the gate at every commit).
`HOLO3_RUN_SLOW_TESTS=1` adds the sim decodes (~25 s warm, ~95 s cold:
since 2026-09-20 decode records live in the content-keyed fixture cache
beside the stimuli; the K/colour/mixed/degraded/local-patch
regressions).  `HOLO3_RUN_ORACLE_SWEEPS=1` on top — both flags — adds
the widened matrix (~2 min warm: the serial colour decode, the page-field
frames, the rotations, the wider BCH and drift corpora).  The whole-page
colour existence proofs that made it a 96-minute lane were RETIRED
2026-09-20 by the owner's ruling; their ledgers are in
WIDENED-MATRIX-RETIREMENT-2026-09-20.md.  Every derived capture is a
content-blind transform of a base render pinned by sha, so a format-id
change re-keys them all: run every lane, not the fast one.  The
session-wall tripwire that once failed a lane over its budget was
RETIRED 2026-09-20 (it tripped on load, never on a mechanism
regression): the exit code is authoritative again, and the measured
walls are CLAUDE.md's reference numbers, not gates.
The null between two trees (2026-10-12, CMY-RECEIVER-PLAN A0):
`python -m holo.receiver.tests._h3_decode_diff BASE_CACHE HEAD_CACHE`
pairs two slow lanes' cached decode records by label (each side run
with its own fresh `HOLO3_FIXTURE_CACHE`; a cache holding one label
twice is refused) — deterministic records (workers 1, `--complete`)
exactly on status, exit code, payload sha, certificates and attempt
outcomes, pooled ones on the outcome and the certificates both sides
hold — and names the first differing certificate; exit 0 identical, 1
differs. It is calibrated head against head before it gates a wave.
Never edit a test module while a lane is running from the same tree
(source-inspecting tests re-read from disk).  Record of the 2026-09-03
re-key repair: conversion_docs/MEASUREMENTS-2026-09-03.md.

### 9a. `--resume` (the fact snapshot)

Every run dumps its durable facts into `<run-dir>/facts.npz` — on the
`--snapshot-every` cadence (default 30 min), on SIGUSR1, and at RunDone;
each write is atomic and keeps the previous generation as `facts.npz.bak`
(main `31d786f`). The snapshot holds: surveys, windows, lattice seeds, placements (affines and
routes), the standing region context fits, plane fields, the pooled colour
context and every certificate — in that fold order. Nothing bulk is in it:
window/colour evidence, context populations and attempt memos are a pure
function of the rasters and a pose, so they regenerate.

`--resume <state-file>` folds that file through the ordinary `_ingest`
path once the captures are in, and then the run proceeds normally on
whatever captures the CLI declares — the same ones, or the same ones plus
new sheets. There is no separate replay path: births come from
`subjects_of` at fold time, wakes from key bumps, derived cells (window
reach, done grids, tile cover) from the same folds that always maintain
them. The rework is bounded by machinery that already exists —
done-geometry refusals, certified-tile refusals, decision-cell no-op
adoption — so a resumed run is residue-only.

There is no format guard, no version stamp and no integrity check on the
file: a snapshot is an operator's own run product, and the operator
re-declares the captures on every run exactly as always. Dropping a
capture from that declaration crashes on the fold, with the traceback
naming the missing id — ruled acceptable 2026-08-30, no guard built.

The file is DEFLATE-compressed (`np.savez_compressed`), ruled 2026-08-30
on a measured 9.3x with a 0.27 s cost at exit; re-measured on the sim
corpus at 9.21–9.30x over five states (K 8,903,331 -> 959,453 B). The
reader is unchanged — `np.load` takes stored and deflated members
alike, so snapshots written before that ruling still resume. The final write is
best effort: an OSError at exit is named on stderr and the recovered
payload stands (a fact the writer cannot encode is still fatal). An
OSError between the write's two renames leaves `facts.npz.bak` and
`facts.npz.tmp` with no `facts.npz`; resume from the `.bak`.

Without `--run-dir` the run dir is a fresh `tempfile.mkdtemp(prefix="holo3-")`
in the system temp folder (`cli.py:136-137`): its `facts.npz` is real but
unrecorded and goes with the temp folder, which is how e042's first sheet-E
run lost its state (2026-10-07). Every recorded run names `--run-dir`, and
the given path is a BASE — the pid is appended (`run_dir_for`,
`cli.py:98-99`), e.g. `scratch/e042/E-run.37117`. One SIGINT stops orderly
with the in-flight jobs drained into the store; a second abandons the drain
(`operator.py`, `OperatorDoors`).

A resumed run appends ONE event, `SnapshotReplayed(facts, certified)`,
at fold time: per-family counts and the certificate total the fold left
standing. It is diag accounting only — nothing in the engine, store or
schedule reads it — and it exists because a resumed run's own tile
outcomes are empty, so without it the status block prints CERTIFIED 0
over a verified close.

Worked examples, one per acceptance family (scan corpus lives in the main
worktree `scratch/`, read-only):

```sh
# sim capture (v2 grammar id; sim is emitted at 1200 dpi so ladders are integer)
env/bin/python -m holo.receiver decode sim.tiff --dpi 1200 \
  --format c3-cmy8-r0550x0550x0547@10x10 --out sim.bin

# e029 K, the --coding/--printer sugar route (== --format L:c2-r0700@3392x2368)
env/bin/python -m holo.receiver decode e029-scan1.tiff e029-scan2.tiff \
  --dpi 4800 --dpi 4800 --coding c2-r0700 --printer hp-m281-ink --out e029.bin
# -> VERIFIED 465580 bytes

# xerox cmy7 (fossil route; -v0 colour identities resolve ONLY via L:)
env/bin/python -m holo.receiver decode xerox-canon-c3-cmy7-2400dpi.tiff --dpi 2400 \
  --format L:c3-cmy7-p120-v0@2240x1536 --out c3cmy7.bin   # -> 301600 B

# xerox cmy8
env/bin/python -m holo.receiver decode xerox-canon-c2-cmy8.tiff --dpi 4800 \
  --format L:c2-cmy8-p120-v0@3328x2304 --out c2cmy8.bin   # -> 718413 B

# sheet I: pooled cmy8 fossil, three captures
env/bin/python -m holo.receiver decode I.tiff I-displaced.tiff I-displaced2.tiff \
  --dpi 2400 --dpi 2400 --dpi 2400 \
  --format L:c2-cmy8-r0700-p120-x1@3392x2368 --out sheetI.bin  # -> 1798761 B
```

The workers A/B check (acceptance 8) is one invocation run twice with
`--workers 1` and `--workers 8`: identical payload bytes (payload only —
the workers-8 certificate set is race-dependent, see §7), >= 3x wall
clock; one production decode at a time (64 GB machine).

## 10. What holo3 deliberately does not have

- **No journal, no bookmark persistence, no event replay, no leases** —
  resume is one fact snapshot folded through the ordinary merge (§9a).
  Scheduling state is deliberately NOT durable: a window that never
  placed walks its ladder again, against a region that now knows more
  poses than it did.
- **No quarantine** — word trust is one-way (W5 rival bar at admission), so
  `known_position_words` and its consumer are not built. The ALARM is
  (ruling D1, 2026-09-04, `plugins/contradiction.py`): when an adopted
  word-routed placement names a printed position a standing placement of
  the same capture puts somewhere else — their page-cell mappings a whole
  cell or more apart at a shared paper point, or on different pages — the
  place fold emits a `Contradiction` event, prints one loud stderr line
  and counts it in diag. It is diagnostic only: nothing is condemned,
  excluded, repriced or unplaced, and the certificate gate stays the only
  bar. The neighbour set is the ring relation `place_sched._place_reads`
  already subscribes to, so the check is O(neighbours) per placement.
- **No defensive guards/asserts** — only the C-7 behaviours remain (counter
  range refusal, known-site mint check, retry-64 caps, erasure budget,
  declared-vs-voted pitch refusal, finite-only LLRs at the tile boundary);
  everything else validation-shaped is dropped as dead weight.
- **No prepared regions** — v1's per-window crop+filter IS the parity
  numerics; holo2's memmap triples bought disk (12 B/px) and complexity, not
  accuracy.
- **No generate side** — src/holo generate is the format authority; holo3
  only reads. Sim stimuli are emitted with src/holo tooling as data.
- **No divergence audit, D16 surplus audit, certified-label enrichment, env
  hatches, policy ids** — consumers deleted; acceptance verifies by script.
- **No rational/bigint intake kernels** — u8 + integer decimation only; a
  non-integer ladder factor refuses (C-10).
- **No same-capture cross-rung pooling** — one scan's rungs are never
  summed on a below-floor tile (ruled 2026-09-04, retirement RULINGS D2):
  the rungs' errors are correlated, which is the never-sum-the-same-
  capture law, and the gain holo2 computed for it (+2 e029 tiles; 16 of
  78 gap tiles sit below the attempt floor at every rung) is small and
  probably subsumed by the analyzer's yield. If it is ever wanted it is
  an ADDITIVE residue row, measured first on the archived event streams,
  never an ordinary route.
- **No caps on evidence passes** — a cap that reduces yield is wrong
  (no-ceilings rule); passes are priced by the cost tiers instead.
