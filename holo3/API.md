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
durable fact snapshot (`facts.npz`) that `--resume` folds back through the
ordinary store merge before intake (§9a).
Format law (BCH, LDPC, keystream/AES, fountain algebra, metadata LFSR, slot
permutation) is copy-and-stripped from the v1/holo2 sources, bit-exact, and
verified against them by the `_distill/verify/` scripts. Normative
companions: `_distill/00-plan.md` (charter) and `_distill/00-contract.md`
(rulings, frozen surfaces, cost table); this file describes the committed tree.

## 1. Module map

```
holo3/
  data.py        frozen dataclasses only: cross-plugin facts + the 10 diag events
  lib/
    bch.py       BCH(127,50,t=13) shortened to (100,23), d_min=27; scalar + batched decode
    ldpc.py      six e-IRA QC-LDPC rungs, BP decode (min-sum then sum-product), encode
    ldpc_data/   byte-identical copies of src/holo/core/ldpc/data (r0547..r0850)
    pava.py      stack-PAVA calibration, ordered context offsets, loglosses, sigmoid
    geometry.py  affines (cell-edge convention), window starts, the 131/17 parity hash
    decimate.py  integer-box u8 area decimation, ppc ladder, luma laws (E018 order)
    owners.py    freeze_page_owners — one owner window per page cell, total order
  format/
    keystream.py AES-128-ECB counter keystream; domains 1-15; draws, perms, dithers
    metadata.py  degree-24 LFSR equations, GF(2) elimination, decode_metadata
    pilots.py    word/filler/dust site construction, word encode/decode, dust values
    identity.py  Family, FormatRow, SiteGeometry, v2 id grammar, 14-row fossil catalogue
    tile_codec.py tile/frame encode+decode, cmy7 pack7 soft demap, cmy8 stream decode
    fountain.py  the column-group law (ColumnGroups, column_groups, TileSlots), VolumeCode (quotas/shuffle/row_of, pooled esi, tile_slots), the per-(block, group) GF(2) Decoder + BlockStatus
    close.py     envelope unwrap + three gates, stream reassembly, close_volume
  plugins/       one module per stage, pure entry functions + a frozen
                 PluginDescriptor at the bottom (its scheduling contract):
                 intake, survey, words, place (+ place_sched — the place
                 plugin's scheduling half, 1000-line split), cold, pose,
                 calibrate, color_model, color_region (+ color_region_anchor,
                 color_region_ctx — area-internal splits), tiles, refine,
                 color_refine (the colour refinement lane), revisit (the
                 mop-up row)
  diag/          event-fed only: model (accumulators/status/report), panes (A-D), server
  store.py       the accessor store: every mutable cell is a private dict
                 behind a keyed accessor, typed folds are the only writers
                 and return the FactKeys a fact really changed
  engine.py      orchestrator core: DESCRIPTORS tuple, generic births/wakes
                 via the inverted FactKey subscription index, frontier heap,
                 one-in-flight bookmarks, single-writer merge, accounting,
                 close consult; owns no pricing at all
  descriptor.py  the plugin/scheduler contract: the closed 13-family
                 FactKey vocabulary, PluginDescriptor, WorkerBookmark
                 (every price lives in the plugins; the engine only pops)
  schedule.py    the derived schedule table `python -m holo3 schedule`
                 prints: resolved price ladder, per-row subscription
                 families read off the `reads` functions, write families
                 off the store folds that type each fact
  cli.py         decode + schedule surface
  __main__.py    python -m holo3
```

No holo3 production module imports holo2/paperholo/src-holo. Plugins import
only data.py, lib/, format/, and the two pinned surfaces P5→P6 and P7→P8.

## 2. Data model (holo3/data.py — all frozen dataclasses)

Units are in the names: `_px` pixels of the named raster, `_cells` format
cell coordinates, `_yx` (row, col), `_in` inches, `ppc` pixels per cell,
`dpi` declared scan resolution. `pitch_in` is a `Fraction` (inches per cell).

Capture side:

- `Level` — one rung of a capture's decimation ladder: `index` (0 = coarsest,
  2 ppc; last = native), `ppc: Fraction`, `scale: Fraction` (native px per
  level px, exact rational), `shape_px`, `label` (e.g. `l00-2ppc-600dpi`).
- `Capture` — one ingested scan: `capture_id` (from the file sha256; duplicate
  shas fold), `path`, `dpi`, `shape_px`, `channels` (1 or 3),
  `platen_backing` (median border luma, u8 scale), `levels`, `plane_dir`
  (run-dir directory of per-plane `.npy`).
- `PlaneRaster` — one plane at one level: `plane` in {g, y, r, g, b};
  `open()` returns a read-only mmap view (each worker opens its own).
- `Region` / `CaptureSurvey` — survey output: active regions (`cells` support
  grid at `step_px`, `extent_px`, `area_mm2`, `median_tensor_score`) and the
  voted pitch (`pitch_class: Fraction | None`, `pitch_px`); `pitch_class
  None` means no windows on that capture.

Placement side:

- `Window` — unit of placement work; `window_id = (capture_id, level_index,
  region_index, extent_cells)`, `extent_cells = (y0, y1, x0, x1)` in region
  cells; `supported_cells`, `depth` (subdivision), `lane_depth` (scale-space
  lane), `ordinal`.
- `LatticeSeed` — R5 best-supported lattice-seed reduction rows per region.
- `Placement` — a committed pose: `page`, `rot_k` (quarter turns),
  `page_origin_yx` (cells), `native_affine` (6-tuple cell→native-px, cell-edge
  convention), `pitch_px`, `route` (producing route tag), `local_cells_yx`.

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
- `PlaneResidual` — per-plane linear registration residual: `intercept_xy`,
  `slope_xy`, `n_anchors`.
- `PlaneField` — per-(capture, level, page, plane) registration-delta field
  in printed DOTS over the page's tile grid: `delta_dots_xy` (ty, tx, 2),
  `support`, `n_certificates`, `n_sites`, `residual`,
  `median_delta_dots`. A quality-ordered decision cell — the store's fold
  adopts on `(n_certificates, -residual)` and no-ops a worse re-fit — read
  by the colour lane and `refine.color` as a per-cell sampling offset
  through the `offsets_override` seam. Written only under
  `--plane-fields` (default off); with the dial off the family is never
  written and the accessors return nothing.
- `ColorEvidenceRow` — per-window colour feature rows: `values` (N, arity) f32.
  There is no stored tile-evidence fact: a tile attempt cuts its cells from
  the immutable `WindowEvidence`/`ColorEvidenceRow` arrays at fire time
  (arity 1 K llr / 6 cmy7 relative scores / 3 cmy8 marginal llrs), and the
  cut is densified to f64 `(4096, arity)` only inside the attempt.

Outcome side:

- `Certificate` — `(page, ty, tx, stream_id, user_bits, source)`; `user_bits`
  u8 `(user_bits,)` undissected: `[0]` = metadata bit, `[1:]` = fountain
  symbol; the counter is always derived via `FormatRow`. `source` is the
  producing plugin/tier (`"tiles/scan"`, `"tiles/union"`, `"tiles/retry150"`,
  `"tiles/local150"`, `"refine/rf1"`, later `"color/a3"`). Different bits at one
  (page,ty,tx,stream) = `IntegrityError`, exit 1; identical duplicate = no-op
  keeping the standing source.
- `AttemptFact` — one decode attempt: `stage` in
  scan/union/retry150/local150,
  `outcome` in below_attempt_floor/attempted_failed/certified,
  `n_informative`, `n_iters`, `syndrome_ok`, `crc_ok`, `components`
  (the sorted (capture_id, level_index) signature the attempt ran over —
  the producer publishes what it knows, so the retry row births from the
  fact alone).
- `JobResult(facts, events, cpu_s)` — every plugin entry returns this.
- `PluginRow` — accounting row, frozen: jobs, cpu_seconds, certificates,
  poses, words. The engine tallies in plain dicts and mints frozen rows for
  RunResult/diag.
- `CloseBlockRow` — per-block close progress; `format/close.CloseResult.blocks`
  emits these directly (no format-side twin).
- `RunResult(status, payload, payload_sha256, certified, plugin_rows)`.

## 3. Events and panes

`Event` is a union of frozen types (16; the table abridges to the ones that
carry pane content — `test_h3_descriptor.py` holds the full golden);
engine/merge appends them to an append-only list, diag folds
`events[cursor:]` with no locks (C-11). Diag can never change payload,
status, or exit code.

| Event | Fields (abridged) | Consumed by |
|---|---|---|
| `RunOpen` | format_id (canonical row_id), display_id (short spelling, for the pane), pages, tiles_yx, stream_ids, n_captures, workers | status row 1, catalog |
| `CaptureOpen` | capture, dpi, shape_yx, channels, duplicate, levels_ppc | pane A, row 2 |
| `SurveyDone` | capture, regions (RegionMark…), pitch_class, preview underlay | pane A, row 2 |
| `PoseCommitted` | capture, level, region, extent_cells, page, route, mismatch, accepted | panes A+B (addressed reach) |
| `WindowSettled` | capture, level, region, extent_cells, state | pane A window rectangles |
| `CalibrateAdopted` | capture, pool_id, adopted, reason | status detail |
| `TileOutcome` | page, ty, tx, stream_id, source, result, bp_iters | pane B chips, row 5 |
| `JobDone` | plugin, subject, cost, cpu_s, n_certificates/poses/words | pane C accounting bars, rows 3-4 |
| `CloseCheck` | certified, symbols_used, k_total, metadata_rank/n_unique, blocks (CloseBlockRow…), status | pane D, row 6 |
| `RunDone` | status, payload_sha256, n_bytes, certified | pane D, row 6 |
| `FieldFitted` | capture, level_index, page, tiles_yx, block_tiles_yx, publish_floor_dots, planes (FieldPlaneFit…) | FIELD band, the conditional `fields` row |

`FieldPlaneFit` carries one plane's fit whether or not the writer published
it — median delta, sites, residual, support, the refusing floor by name, and
the field block-pooled to at most 24x24 blocks (15,552 bytes of array per
event, whatever the tile matrix). A plane that never fitted reports None for
every measurement, never zero.

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
(refuses nonzero pads), `color_word_states` / `decode_color_word` (states
0/3), `dust_state_values(row_seed, counters, dust_base_cycle, n_dust)`.

`format/identity` — `Family` enum (K/CMY7/CMY8), dispatch everywhere.
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
  (`StreamFact(stream_id, plane, fountain_aux, rung_children, user_bits,
  symbol_bits)`), pooled_fountain, bits/cells per mapper unit; derived:
  cells_yx, tiles_per_page, max_pages, payload_cells, n_transmitted_slots,
  tile_counter/tile_address. K stream `fountain_aux is None`; colour
  main=0, C/M/Y=1/2/3 — the close dispatches on `is None`. `sites_seed`
  is the frozen `holo/v1/sites/pN` bytes (accessor rename; src/holo still
  spells `family_seed`).

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
groups_open, n_groups, and min_rows — the count gate).

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
  `n_groups`; the decoder's `BlockStatus` additionally holds that
  group's `rows` and the block's `min_rows`, the count gate, which stay
  decoder-side. `metadata_rank` /
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
  domains).
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
- `color_model` (P5→P6 surface, src/holo names): `blind_component_bits`,
  `fit_qda` -> frozen `QdaModel`, `qda_log_scores`, `cmy7_relative_scores`,
  `cmy8_marginal_llrs`, dust-PAVA fit + support qualification
  (`fit_cmy8_detector`), `fit_cmy7_head` -> (head|None, reason) via Newton,
  `reference_states(row, page, cells_yx)`.
- `color_region` — `region_job(row, geometry, windows: RegionWindow…,
  label_windows, planes (r,g,b PlaneRaster), certificates, StackConfig,
  capture_id, level_index)` per (capture, level, page): anchoring/NCC/
  Theil–Sen registration, ownership + split, the calibrated-head arm ladder
  (A0/A1 -> head+satfloor30 -> ctx matrix), emission (L-inf 20 /
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
  scan/union/retry150 stages), certificate mint with GT re-encode + the
  C-7 known-site `np.array_equal` check, `printed_cells_for(row,
  geometry, page, ty, tx, user_bits) -> (64,64)u8` (the P8 surface),
  `merge_certificate` (conflict -> IntegrityError), `done_tile_grid` +
  `project_done` (the ONE done projection) + done-grid helpers.
- `refine` (P8) — RF1, core and always on: certified labels + floors +
  coarse/fine pose grids + adoption gate (`MIN_HELDOUT_GAIN`) + re-read via
  `revised_placement`; eligibility-gated (`refine_eligible`: certified +
  uncertified in reach), priced 200. K windows only — colour windows get
  `refine.color`.
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

## 6a. Engine wiring (engine.py)

The store (store.py) holds ALL domain state behind keyed accessors —
private dicts, accessors the only door (grep-provable: no `store._X`
outside store.py) — and the engine holds ALL scheduling state; plugins
stay pure. Each plugin row is a frozen `PluginDescriptor` declared at the
bottom of its module (`name, subject_kind, born_by, subjects_of, reads,
eligible, stage, cost, retire, prepare, produces, prices`);
`engine.DESCRIPTORS` is the collected tuple and the engine knows nothing
else about any plugin — `stage` names an opaque per-row stage,
`cost(store, subject, stage)` returns the price in the plugin's own
literals. `python -m holo3 schedule` prints the derived table;
`holo3/SCHEDULE.md` carries that block verbatim plus its prose.
Single-writer-by-domain is verified at startup (no two descriptors share
a produced fact type, except Certificate's source tags and same-prefix
rows like tiles.*; revisit declares the four types its delegated
place/calibrate bodies emit and is exempted by name — `REARM_PLUGINS` —
so its fires are accounted honestly without tripping the check).

Lifecycle: FOLD (typed store update) returns the FactKeys the fact
REALLY changed — value compare for scalars/small tuples,
`np.array_equal(…, equal_nan=True)` on written array cells; an unchanged
write touches nothing. BIRTH matches the fact against `born_by`,
enumerates `subjects_of`, evaluates `reads`, registers the
WorkerBookmark in the inverted index and pushes at price (a birth that
finds a standing bookmark only adds the fresh read keys). WAKE bumps
each subscribed bookmark's version and pushes at its CURRENT price (the
row's `cost` aged by the engine's one law, `max(cost, 90+5*(n-1))`,
FIFO-per-price seq); FIRE pops cheapest, retires (unregisters) if
`retire(store, subject)`, skips on the version floor, records the
version, then `eligible` -> `prepare` -> submit pure job (`None` =
costless skip). AT MOST ONE JOB IN FLIGHT PER WORKER: a wake landing
mid-flight sets the bookmark's pending bit and the worker re-pushes when
its result merges — merge order per subject equals preparation order, so
there is no stale-write class and no lane_generation. The version floor
is the ENTIRE staleness story: there are no content digests, stamps, or
attempt sets anywhere (D6 addendum 6); a re-fire on genuinely new
data is ordinary work at its declared price. The place ladder's stage state (tried
candidate ids, stage/wide/cold spends, subdivision, dormancy, parent
afterlife) is a store cell (`place_stage` accessor, `WindowState`,
touched as `("place_stage", wid)`); dormancy is a recorded worker
version compared at fire time, cleared by any later wake. Prepare
functions never write state.

THE DONE GATE (2026-08-30, docs/DONE-GEOMETRY.md in this
architecture): `store.window_fully_done(wid)` is true when every tile
the window could still contribute evidence to is certified in EVERY
stream — placed windows on their derived reach against `done_grid`,
unplaced ones on `window_extent_done` (the region's projected
`done_cells` covering the supported extent; off-page tiles ignored).
Certification is terminal, so the verdict is monotone and the
suppression cannot cost a certificate. `place` consults it in retire,
`calibrate` and `revisit` in eligible; `refine`/`refine.color` need no
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
  len(refine_basis), -quality)`. Basis-major: an adopted revision
  outranks any original (its held-out gate is the proof), and a larger
  basis outranks a smaller one, so mismatch scalars from the chain,
  word and cold searches are never compared across evidence bases.
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
  quality-only. Note the refusal is not confined to the ctx cell: the
  gate precedes the fact's evidence re-fold, so a refusal that is not
  also `held` (same adopted flag AND identical offsets — the escape
  that lets an unchanged re-fit still deliver its rewrites) drops the
  whole `apply_region_context` batch, not just the ctx cell, and a
  window that joined the region after the best-scoring fit can never
  receive context correction.
NOT converted: the colour decision, which survives the deletion of the
RegionColorModel fact as `ColorEvidenceRow` (it carries a non-optional
`heldout_logloss`, the quality field the law asks for) and whose fold
is still bare change-detection last-write-wins, gated only by its
producer's stack gates. Addendum 14 names four decision cells; this is
the fourth. No disposition has been ruled.

Engine-owned laws: window/patch ordinals are plan-derived per (capture,
level) — cumulative `window_plan` bases in region order, children at
`plan_total + parent.ordinal*4` (ruling 10); the lattice-seed cell is a
declared commutative merge — max support wins, ties to the smaller
producing-window ordinal (no byte compares); region pitch is the median
over the region's placements, recomputed at placement folds — a change
touches `("region_pitch",…)` and re-arms every sampled window of the
region (fixed-point deterministic); the RF1 crop reuses calibrate's
`window_crop` median-fill
convention (ruling 11); the colour `RegionWindow` is built from
`Placement` in color_region (rotation-composed level-frame affine, +0.5
cell-centre shift, `pose_points` matmul spelling — ruling 14); the
certificate fold is the first line of the opposite-metadata-bit defense
(close's raise stays as the belt, ruling 5). Certificate-growing merges
trigger the close consult (count gate, then `progress.close()`;
`--complete` defers, `--no-close` observes); VERIFIED cancels pending futures and
returns. The close is NOT a descriptor.

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
  word_rest 80, wide 120, refine/refine.color/revisit 200, cold_live 250,
  cold_rest 260 (PAGE-DOMAIN 2026-09-01: cold last by price, above
  swim; no dryness gate); +2 per rung (+20 per rung cold), +5 child.
  The engine owns no numbers: cost is a scheduling function of
  the plugins alone (ruling 2026-08-29; the rework-aging formula was a
  holo2 artifact, deleted). `python -m holo3 schedule` prints the
  resolved ladder with the same-price peers marked.
- Memory: per-window crop+filter (C-2), sparse tile evidence (C-5), one
  read-only mmap view per worker per plane.

## 8. Arm doors and the schedule-on-residue law

Arms (u-lanes, color_field, A3/A4b) are NOT built in v1; the doors they
need ARE. One door is now WALKED THROUGH: the `fields` row fits a
per-plane registration field and the colour samplers read it through
`offsets_override` (dial `--plane-fields`, default off — see `PlaneField`
in §3 and the `fields` bullet in SCHEDULE.md). The rest stand open:

- `offsets_px: (N,2)f64 | None = None` on every point-sampling helper
  (`pose.sample_segment`, `calibrate.scan_points_yx` and the
  calibrate/resample window entries, `refine.sample_at`/`refine_window`).
  `None` is bit-identical to no arm. This is the plane-fields door.
- `offsets_override` + the NCC block edge in colour registration
  (color_region; ruling 11-6). Arms attach at sampling, never at placement.
  A SECOND door now stands beside the mapping: `offsets_of`, a callable
  handed the head's own `WindowRows`. Same tier, one rung more specific
  than the standing plane fields and one less than the mapping, and it
  exists because an arm that derives its offsets from cell POSITION
  should not have to reproduce the row order the head will build —
  `plugins/swim.py` walks through it. `None` is bit-identical to no arm.
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
             [--diag PORT] [--run-dir DIR] [--resume STATE_FILE] --out FILE
```

Exactly one `--dpi` per scan (positional order, each capture at its own
declared dpi — mixed-resolution runs are legal); duplicate scans fold by
sha; the same source at two different dpis refuses (Q2); `--out` refuses
to overwrite; `--max-pages N` caps the possible page domain (absent =
all addressable pages of the row; `N < 1` and `N > row.max_pages`
refused by name; `--max-pages 1` is today's null control). `--format` and `--coding/--printer` are mutually
exclusive. `--complete` defers the close until the frontier is exhausted;
`--no-close` observes only (diagnostics). Prints the six-row status block,
the per-plugin accounting table, and on success `VERIFIED <n> bytes sha256
<hex>`. Payload written atomically. Exit 0 verified / 2 open / 1 error. Invoke as
`env/bin/python -m holo3 …` (no console script is installed).

**Test lanes.** `env/bin/python -m pytest holo3/tests -q` is the fast
lane (~50 s, no decodes; the gate at every commit).
`HOLO3_RUN_SLOW_TESTS=1` adds the sim decodes (~5 min; the K/colour/mixed
/degraded/local-patch existence proofs and the churn tripwires).
`HOLO3_RUN_ORACLE_SWEEPS=1` on top adds the heavy colour pairs and the
widened matrices (~3.5 h serial: uplift ~75 s, local_ctx ~11 min,
field-yield ~66 min, swim ~1.7 h, rotations ~5 min); run it per module,
one heavy module at a time (memory budget).  Every derived capture is a
content-blind transform of a base render pinned by sha, so a format-id
change re-keys them all: run every lane, not the fast one.  The wall
tripwire (`_h3_support.WALL_BUDGET_S`) is wall-clock and permanently
tripped on all three lanes; read the `N failed` line, not the exit code.
Never edit a test module while a lane is running from the same tree
(source-inspecting tests re-read from disk).  Record of the 2026-09-03
re-key repair: conversion_docs/MEASUREMENTS-2026-09-03.md.

### 9a. `--resume` (the fact snapshot)

Every run dumps its durable facts once, at RunDone, into `<run-dir>/
facts.npz`: surveys, windows, lattice seeds, placements (affines and
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
payload stands (a fact the writer cannot encode is still fatal).

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
env/bin/python -m holo3 decode sim.tiff --dpi 1200 \
  --format c3-cmy8-r0550x0550x0547@10x10 --out sim.bin

# e029 K, the --coding/--printer sugar route (== --format L:c2-r0700@3392x2368)
env/bin/python -m holo3 decode e029-scan1.tiff e029-scan2.tiff \
  --dpi 4800 --dpi 4800 --coding c2-r0700 --printer hp-m281-ink --out e029.bin
# -> VERIFIED 465580 bytes

# xerox cmy7 (fossil route; -v0 colour identities resolve ONLY via L:)
env/bin/python -m holo3 decode xerox-canon-c3-cmy7-2400dpi.tiff --dpi 2400 \
  --format L:c3-cmy7-p120-v0@2240x1536 --out c3cmy7.bin   # -> 301600 B

# xerox cmy8
env/bin/python -m holo3 decode xerox-canon-c2-cmy8.tiff --dpi 4800 \
  --format L:c2-cmy8-p120-v0@3328x2304 --out c2cmy8.bin   # -> 718413 B

# sheet I: pooled cmy8 fossil, three captures
env/bin/python -m holo3 decode I.tiff I-displaced.tiff I-displaced2.tiff \
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
  `known_position_words` and its consumer are not built.
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
- **No caps on evidence passes** — a cap that reduces yield is wrong
  (no-ceilings rule); passes are priced by the cost tiers instead.
