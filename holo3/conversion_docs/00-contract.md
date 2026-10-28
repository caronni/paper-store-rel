# holo3 — THE CONTRACT (frozen before build; every builder reads this AND 00-plan.md AND its own spec)

This document rules every open question the distill specs raised, pins the
module map with file ownership, and freezes the cross-module surfaces.
Where a spec and this contract disagree, the contract wins. Where v1
(src/holo) and holo2 numerics disagree on the receive path, **v1 wins** —
v1 is the only tree that closed the acceptance volumes — EXCEPT the
explicitly adopted holo2 pieces listed in C-1.

## C. Cross-cutting rulings

- **C-1 holo2 adoptions** (everything else receive-side follows v1):
  batched BCH (`bch_batch`), the W5 whole-word rival bar + cross-page
  rival set, R5 best-supported lattice-seed reduction, cell-frame
  flush-shifted window starts, the engine cost scale (verbatim numbers),
  done projection + sparse done grid, the pooled-close/count-ready shapes,
  metadata/keystream carries (character-identical to v1 anyway), the diag
  pane paint/HTTP skeleton.
- **C-2 Per-window crops, no prepared regions.** All sampling (pose fit
  spectral crop, phase, cell reads, calibration, colour features) follows
  v1's per-window crop+filter discipline (halo absorbs the boundary; the
  parity numerics ARE per-crop). holo2's `prepared.py` memmap triples are
  NOT built. Memory stays bounded per job; no 12 B/px disk budget.
- **C-3 v1 scores convention everywhere**: `(midpoint − means)/spread`
  float32 (every constant spelled `np.float32`). PAVA knots are fitted on
  it; RF1 logits go through it. holo2's raw `−means` form is not used.
- **C-4 Parity/hash family**: the literal spelling `(131*y + 17*x)` with
  `&1` (fit split), `&2` (head sub-split), `&4/&8` (reveal codes) lives
  ONCE in `lib/geometry.py`. Never re-derive, never "simplify" to (y+x).
- **C-5 Evidence memory shape**: sparse per (capture, tile):
  `values float32 (n_observed, arity)` + `observed_flat uint16 sorted`
  (arity 1/6/3). Densify to float64 `(4096, arity)` only inside an attempt.
- **C-6 Certificate**: frozen dataclass `(page:int, ty:int, tx:int,
  stream_id:str, user_bits: np.ndarray u8 (user_bits,), source:str)`.
  Full user frame undissected: `user_bits[0]` = metadata bit,
  `user_bits[1:]` = fountain symbol; counter always DERIVED via FormatRow.
  `source` = plugin/tier tag: `"tiles/scan"`, `"tiles/union"`,
  `"tiles/retry150"`, `"refine/rf1"`, later `"color/a3"` etc.
  Conflict (different bits at one (page,ty,tx,stream)) = FATAL, one
  IntegrityError, exit 1. Identical duplicate = no-op keeping the standing
  source.
- **C-7 The two checks that STAY** (behaviour, not guards): keystream
  `counters()` field-range refusal (out-of-range must never wrap into a
  valid different stream) and the format-known-site `np.array_equal` at
  certificate re-encode mint (e012 tripwire). Also kept as copied law: the
  rejection-draw retry cap 64, `f > 26` / `2e+f <= 26` erasure budget,
  duplicate-page-cell and conflicting-label errors inside fits, the
  declared-vs-voted pitch-class refusal (e033), finite-only LLRs at the
  tile boundary. Everything else validation-shaped is dropped.
- **C-8 No resume, no quarantine, no known-position word reads, no
  divergence audit, no certified-label enrichment, no D16 surplus audit,
  no env hatches, no policy ids.** Word trust is one-way and the
  quarantine consumer is gone, so `known_position_words` is not built.
  PAGE-DOMAIN 2026-09-01: `--max-pages` is a per-run admission bound,
  not a stored policy; C-8 is untouched.
- **C-9 RF1 refinement is CORE and always on** (no `--refine` flag);
  eligibility-gated (certified + uncertified in reach) and priced at 200
  it costs nothing when useless. E022 placement-time refinement is part of
  the place tail, always on. Arms (u-lanes, plane_fields, color_field,
  A3/A4b) are NOT built in v1; when built they get a repeatable
  `--arm NAME` flag and schedule on the residue per §6.2a; the API doors
  they need (per-plane per-cell offset in the samplers, offsets_override
  in colour registration, arm tag on TileEvidence, source tag on
  certificates) ARE built now.
- **C-10 Intake is u8 + integer decimation factors only.** The rational/
  bigint kernels are not built; a non-integer ladder factor refuses. Sim
  captures are emitted at 1200 dpi so their ladders are integer.
- **C-11 Diag**: engine/merge appends frozen events to an append-only
  list; diag folds `events[cursor:]` (no locks). The 10-event list and
  A–D pane mapping of spec 13 §2c are adopted verbatim. HTTP viewer binds
  only with `--diag PORT`; end-of-run `report.json` + final frames +
  `events.jsonl` + one argv line always land in the run dir. Diag can
  never change payload/status/exit code.
- **C-12 Determinism**: every ordering on values, never arrival order —
  freeze key `(heldout_logloss, window-extent-tuple, plane)`; R5 seed
  reduction; sorted capture shas in unions; sorted work keys in tiers.
  `--workers N` must be payload-byte-identical for all N.
  PAGE-DOMAIN 2026-09-01: C-12's letter is payload-byte-identical;
  certificate-SET identity across `--workers` is dropped (floors read
  fire-time live state). No e2e may promise cert-set identity across N.
- **C-13 pyflakes**: `env314t/bin/pyflakes holo3/` clean is a merge gate
  for every wave.
- **C-14 Charter enforcement**: no comments, no docstrings, no asserts,
  type hints everywhere, units in names, ≤1000 lines/file (split signal),
  numpy dtypes explicit on every seeded/derived array. `_distill/` is
  exempt (verify scripts may have comments).

## M. Module map + ownership (builder = one bullet; do not touch others' files)

```
holo3/
  data.py            (contract author) cross-plugin frozen dataclasses + events
  lib/
    bch.py           B1  GF tables, scalar encode/decode/decode_erasures, batched decode_many
    ldpc.py          B2  code expansion/load (eager all six), BP decode, encode
    ldpc_data/*.json B2  byte-identical copies of src/holo/core/ldpc/data
    pava.py          B7  stack-PAVA, generalized-PAVA blocks, _solve_offset,
                         canonical two-branch sigmoid, weighted/binary loglosses,
                         class_balanced_weights, interp+logit LLR map, clamp_for
    geometry.py      B7  affine terms/invert/apply, Fraction pixel-rescale law,
                         compose_to/from_native, window_starts, parity hash family,
                         rotated_points, tile_of_cell
    decimate.py      B7  AreaPixelTransform, u8 integer-box decimation (+rgb),
                         luma laws (equal-channel mean, E018 order)
    owners.py        B7  freeze_page_owners (shared K/colour)
  format/
    keystream.py     B3  kdf, counters, blocks, bits, keys64, bounded_draws,
                         slot_perm_params, payload_bits, fountain_rows_bits (+colour),
                         item permutations (dust/interleave/cell order), dithers,
                         block-assign keys
    metadata.py      B3  LFSR table, equation_index/max_index, decode_metadata
    pilots.py        B4  word/filler/dust/colour site constructions, value scramble,
                         word_values, decode_word, color_word_states/decode_color_word,
                         dust_state_values, color_payload_cell_indices
    identity.py      B4  Family enum, FormatRow, StreamFact, SiteGeometry, LADDER,
                         v2 grammar (full, incl. mixed triplets), fossil catalogue
                         (src/holo's FOURTEEN rows), resolve_format_ref, e029 sugar
                         (margin dict + derive_field), tile_counter/address
    tile_codec.py    B5  crc32_bits, transmitted_positions, cell_map, encode/decode_tile,
                         bank encode/decode_frame, cmy7 codebook + soft demap +
                         demap_payload + iterated_decode (DEMAP_ITERATIONS=3),
                         cmy8_decode_stream, states/planes helpers
    fountain.py      B6  VolumeCode (quotas/shuffle/row_of, pooled esi), Decoder
                         (add_symbol conflict law, packed GE, _failed_at memo)
    close.py         B6  envelope try_unwrap + source_symbol_count, streamset
                         reassembly (stream-major + pooled) + the three gates,
                         metadata_from_certificates, close_count_ready, close_volume
  plugins/
    intake.py        P1  scan ingest, sha, per-plane .npy, ladder derivation, platen backing
    survey.py        P1  E021 survey (tensor, log-Otsu, pitch vote+snap, refinement)
    words.py         P2  Stage-A slot sweep, legality gates, word admission + W5 rival bar
    place.py         P2  reference field, ScoreMemo, chain/local search, admission
                         algebra, straddle audit call, the unified per-window job ladder,
                         subdivision, neighbour relation, done-gate consult
    cold.py          P2  the bit-exact FFT correlation sweep
    pose.py          P3  per-window crop/fit (lattice+prior_f, phase), sample_segment,
                         E022 batched refine, audit_segment, lattice-seed protocol
    calibrate.py     P4  K sampling (v1 _scores), per-window PAVA, region ctx detector,
                         K evidence emission + freeze
    color_model.py   P5  blind EM, QDA (double ridge), cmy8 marginals + dust PAVA,
                         cmy7 head fit (Newton), reference states
    color_region.py  P6  anchoring/NCC/Theil–Sen registration, ownership+split,
                         arm ladder (A0/A1 -> head+satfloor30 -> ctx matrix), emission
                         (L-inf 20 / marginal+clip+PAVA), pool-law masks, label rows
    tiles.py         P7  freeze->TileEvidence, K + colour attempt chains, certificate
                         mint + re-encode GT + known-site check, scan/union/retry150
                         scheduling facts, tilemap/done-grid helpers
    refine.py        P8  RF1 (labels, floors, grids, adoption gate, re-read)
  engine.py          (integrator) frontier loop, merge, wake, accounting, close consult
  diag/
    model.py         P9  event accumulators + the fold (A-2)
    readout.py       P9  six-row block, advisories, selectors, /status JSON (A-2)
    report.py        P9  events.jsonl + report.json (A-2)
    panes.py         P9  paint primitives, panes A-D, composed frame, pin_panes
    server.py        P9  stdlib HTTP viewer (loopback, no-store)
  cli.py             (integrator) decode surface
  __main__.py        (integrator)
```

## S. Frozen cross-module surfaces (build against these exactly)

- `lib/bch`: `encode(msg: (23,)u8) -> (100,)u8`; `decode(word: (100,)u8)
  -> tuple[(100,)u8, int] | None`; `decode_erasures(word, erasure_idx)
  -> ... | None`; `syndromes(word) -> (26,)u8`;
  `decode_many(words: (H,100)u8) -> list[tuple[np.ndarray,int] | None]`.
  All tables module-eager.
- `lib/ldpc`: `CODES: dict[str, Code]` eager for all six rungs; `Code`
  frozen (edge arrays, starts, var_order, enc arrays, k_bits, n_bits=4096);
  `decode(llr: (4096,)f64, code, max_iters: int, alpha: float=0.8) ->
  tuple[bool, (4096,)u8, int, (4096,)f64]` (syndrome_ok, hard, n_iters,
  extrinsic — always computed); `encode(info: (k,)u8, code) -> (4096,)u8`.
- `format/keystream`: signatures per src/holo/core/keystream.py verbatim
  (seed-first, domain constants exported). No memo dicts; pure functions.
- `format/identity`: `resolve_format_ref(ref: str) -> FormatRow` (string
  door); `mint_format(*, pitch, family, rungs, sites, gen, tiles_yx) ->
  FormatRow` (parameter door; v2 resolve parses then mints; fossils never
  mint). `coding_printer_ref(coding_id: str, printer_id: str) -> str`
  (returns the legacy `L:` spelling via derive_field);
  `build_site_geometry(row: FormatRow) -> SiteGeometry`;
  `scramble_plane(row, geometry, page)`.
  `FormatRow`: row_id, display_id, seed, sites_seed, family, tiles_yx,
  pitch_in (Fraction), n_sites, n_dust, dust_base_cycle, word_states,
  streams (tuple[StreamFact]), pooled_fountain, bits/cells per mapper unit;
  derived: cells_yx, tiles_per_page, max_pages, payload_cells,
  n_transmitted_slots, tile_counter/tile_address. Page domain is a
  receiver bound, not a row field (PAGE-DOMAIN).
  `StreamFact`: stream_id, plane, fountain_aux, rung_children, user_bits,
  symbol_bits. `SiteGeometry`: word_cells_yx, extra_cells_yx, shorten_flat,
  payload_flat, per-tile slot-perm `(a_t, b_t)` spanning counter space,
  scramble memo filled per page on first touch.
- `format/tile_codec`: `decode_tile(llr_flat, rate_id, site_flat, a_t,
  b_t, max_iters, alpha) -> (ok, user_bits|None, n_iters, syndrome_ok,
  crc_ok)`; `encode_tile(user_bits, rate_id, site_flat, a_t, b_t) ->
  (4096,)u8`; `decode_frame(...)`, `cmy7_iterated_decode(...)`,
  `cmy8_decode_stream(...)` per spec 02.
- `format/metadata`: `decode_metadata(equations: dict[int,int], max_index)
  -> MetadataResult(ok, version, k, rank, n_unique, inconsistent)`.
- `format/close`: `close_count_ready(certs, row) -> bool`;
  `close_volume(certs, row) -> CloseResult`. Pure over snapshots; runs on
  the merge thread only. NOTE: sheet I (acceptance 7) IS pooled — the
  pooled esi/quota/metadata path is REQUIRED core here (spec 12 Q8's
  premise was wrong; the tile stage still carries zero pooled code).
- Sampler door (pose.sample / calibrate sampling / colour features): every
  point-generation helper accepts `offsets_px: (N,2)f64 | None = None`
  per plane (None = bit-identical). This is the plane-fields arm door.
- Engine job protocol: each plugin exposes pure entry functions taking
  frozen snapshots and returning `JobResult(facts: tuple, events: tuple,
  cpu_s: float)`; engine.py wires them concretely (no dynamic registry).

## R. Rulings on the specs' open questions (spec-Q -> ruling)

01-1 pilots.py is the single home for site construction. 01-2 dust
schedule in pilots.py. 01-3 confirmed: decode_many is the only batch API.
01-4 gate constants live in plugins/place.py. 01-5 whole-word rival is
the only rival rule. 01-6 the contract carries the erasure-search ban;
code carries no path. 01-7 known-position reads NOT BUILT (C-8).

02-1 all six rungs. 02-2 retry150 = tier of the same job, pre-close
short-circuit kept. 02-3 one decode function. 02-4 arms re-attempt with
new LLRs only. 02-5 source = plugin/tier (C-6). 02-6 conflict aborts the
run. 02-7 confirmed full user frame. 02-8 AttemptFact keeps one
n_informative int; the gate verdict is the outcome enum.

03-1 keep counters() range check (C-7). 03-2 keep the retry-64 cap.
03-3 no incremental eliminator. 03-4 store page/ty/tx, derive counter.
03-5 engine precomputes per-(plane,page) scramble planes into
SiteGeometry. SUPERSEDED PAGE-DOMAIN 2026-09-01: scramble per page on
first touch, memoized beside the reference cache. 03-6 (rank, n_unique)
suffices. 03-7 confirmed, domains freeze at 1–15.

04-1 FormatRow lives in format/identity.py. 04-2 derive_field route.
04-3 row_id is the label — AMENDED 2026-08-30 (A-1): `display_id` is the
short spelling shown to people; `row_id` is the canonical seed payload.
04-4 precompute per-tile (a_t,b_t). 04-5 keep
the full v2 grammar (sim ids need it, incl. the mixed triplet).
04-6 `--pages N` (default 1) declares the page domain; no `--page` flag.
SUPERSEDED PAGE-DOMAIN 2026-09-01: `--max-pages N` caps the possible
set; default unbounded (`row.max_pages`); `--max-pages 1` is the
null-control spelling.

05-1 D16 audit dropped. 05-2 keep `--no-close` diagnostics-only.
05-3 lazy rank. 05-4 rebuild-per-consult + count-growth gate + _failed_at.
05-5 shortfall->frontier coupling deferred. 05-6 identity.py pins
symbol_bits via LADDER algebra. 05-7 metadata.py owns decode_metadata.
05-8 fossils carry pooled flags; sheet I resolves pooled (see S/close).

06-1 integer-only intake (C-10). 06-2 survey once per capture at native;
divergence accepted. 06-3 y.npy per sub-native level, native luma at crop
time. 06-4 no M rows; frontier re-eligibility subsumes mop-up.
06-5 platen_backing = Capture scalar. 06-6 mixed DPIs refuse.
06-7 keep the declared-vs-voted refusal; pitch None => no windows on that
capture. 06-8 keep K-on-RGB luma.

07-1 holo2 W5 rival bar (empty cross-page set on 1-page domains).
07-2 cell-EDGE affine convention repo-wide. 07-3 full multi-rung cascade
from day one. 07-4 refine owns the re-read; wake via facts_version.
07-5 one luma addressing pass; plane deltas are arm-side. 07-6 quarantine
dropped entirely. 07-7 cold_first_max_pages dropped. SUPERSEDED
PAGE-DOMAIN 2026-09-01: reborn as the `{0}` live prior. 07-8 page
domain from --pages. SUPERSEDED PAGE-DOMAIN 2026-09-01: possible =
range(min(row.max_pages, bound)); live seeds `{0}` and grows.
07-9 arms attach at sampling, not placement.

08-1 v1 scores convention (C-3). 08-2 both refinements core, no flag
(C-9). 08-3 R5 reduction. 08-4 cell-frame starts; payload-level parity is
the bar. 08-5 dirty tiles via facts_version wake. 08-6 no prepared planes
(C-2). 08-7 offset door blessed (S). 08-8 poses plane-common.

09-1 v1 scores. 09-2 literal 131/17 spelling in lib/geometry (C-4).
09-3 per-window crop+filter (C-2). 09-4 ctx fit = pure job over region
snapshot + version int; merge discards stale. 09-5 latest evidence only.
09-6 colour keeps pool-law masks; K simplifies to always-sample + drop
done at assembly. 09-7 keep both heldout-loss spellings (copied).
09-8 ctx keys (capture, footing, region); cross-lane forbidden.
09-9 freeze_page_owners in lib/owners.py.

10-1 attempt acceptance 6 with core; A3 arm only if the close falls
short (known risk, recorded). 10-2 retry keyed (address, stream, stage,
evidence-epoch); demap_iterations fixed 3. 10-3 colour union = plain
same-lane per-capture block sum. 10-4 keep label rows (parity).
10-5 drop the baseline fit. 10-6 RegistrationAnchors not built.
10-7 calibration upstream of persistence (blocks hold calibrated LLRs).
10-8 keep only the hoisted count floors.

11-1 region refit re-arms on certified-label growth + level open
(facts_version). 11-2 u-lanes not in v1. 11-3 KEEP CONTEXT_MAX_LABELS=
40000 (fidelity pin; revisit post-parity). 11-4 the region job derives
KnownField from its own cert snapshot. 11-5 satfloor in the ladder; head
fit exports (head, reason). 11-6 offsets_override + NCC block edge is the
arm API. 11-7 no force-null; variant=off config only. 11-8 emission
suppression inside the region job from its snapshot.

12-1 freeze at emission (v1), ctx before freeze. 12-2 divergence audit
dropped; acceptance verify script instead. 12-3 keep the known-site mint
check (C-7). 12-4 moot (no quarantine). 12-5 retry reads the engine's
cached count-ready answer. 12-6 sparse evidence (C-5). 12-7 keep
LANE_COST_PER_RUNG=2. 12-8 corrected: sheet I IS pooled; pooling is
close-side only.

13-1 keep --complete. 13-2 keep events.jsonl + argv line. 13-3 viewer
only with --diag PORT. 13-4 risk accepted (see 10-1). 13-5 pane C =
accounting; word states fold into B. 13-6 holo2 cost numbers verbatim.
13-7 place publishes the neighbour relation; tilemap the tile reach.
13-8 no --refine; future arms get --arm NAME.

14-1 `_distill/verify/run_acceptance.py` + manifest JSON drives the
serial acceptance. 14-2 both routes: --coding/--printer sugar AND
--format L:. 14-3 the reconstructed Vol-6 invocation is the target;
holo1 rerun only as a debugging aid. 14-4 sim at 1200 dpi, u8 tiff,
holo1-oracle-confirmed once, then pinned. 14-5 Vol 3 is the workers A/B
sheet. 14-6 byte-exact close is the bar; counts recorded not gated.
14-7 hp-canon-c2-cmy7 refusal added as acceptance step 9.

## E. Engine contract (spec 13 §2b adopted with these pins)

Cost table verbatim: SURVEY 10, CALIBRATE 15, PAYLOAD 20, RING 40,
WORD_CENTRE 60, WORD_REST 80, WIDE 120, REFINE 200, COLD_LIVE 250,
COLD_REST 260; LANE_COST_PER_RUNG 2, COLD_COST_PER_RUNG 20, CHILD_PREMIUM 5,
REWORK max(tier, 90+5*(n-1)). No dryness gate (PAGE-DOMAIN 2026-09-01:
deleted; an idle worker takes the cheapest ready job; cold is last by
price). Tried-set floor by
facts_version[subject]. Merge single-writer; wake = version bumps via the
place neighbour relation + tile reach + region pools + close residue.
Close consult after certificate-growing merges (count-gate first, full
solve on ready; --complete defers; --no-close observes); VERIFIED cancels
pending futures and returns. Payload written atomically (tempfile+fsync+
link+dir-fsync). Exit 0 verified / 2 open / 1 error.

## CLI (final surface)

`holo3 decode SCAN... --dpi F [--dpi F ...] (--format REF | --coding ID
--printer ID) [--max-pages N] --out FILE [--workers N] [--complete]
[--no-close] [--diag PORT] [--run-dir DIR]`
Exactly one --dpi per scan; duplicates by sha fold; mixed DPIs refuse;
--out refuses to overwrite. Prints the six-row block, the per-plugin
accounting table, and on VERIFIED `VERIFIED <n> bytes sha256 <hex>`.

## V. Build-time verification duty (every builder)

Each wave-1 builder writes `_distill/verify/verify_<module>.py` runnable
with `env314t/bin/python` from the worktree root with
`PYTHONPATH=.:src` — it imports BOTH holo3 and the oracle (src/holo /
holo2 modules) in one process and proves bit-exactness (byte-equal
arrays, exact floats where the spec says bit-identical): BCH spectrum +
g(x) sha + batch==scalar on random words; LDPC edge digests + decode
parity on random LLR vectors incl. erasures; keystream draws vs
keystream_spec goldens across every domain/draw form; pilots sites/words/
dust for p100+p120 and a colour seed; fossil table equality vs src/holo;
derive_field reference table; tile_codec encode/decode round-trips vs
src/holo on random users + cmy7 demap parity; fountain assignments
(quotas/shuffle/row_of) vs src/holo for K, -v0 colour, pooled, and the
n=1 identity; close on synthetically certified full volumes (all three
families + pooled + dead-Y pooled). Report the verify output in your
return. Verify scripts are throwaway quality but must actually run green.

## W2. Wave-2 addendum (binding on plugin builders; reflects the built wave-1 tree)

Wave-1 modules exist and are committed — READ their actual code for exact
names before importing; the frozen surfaces held, with these built facts:

- `lib/bch`: `encode/decode/decode_erasures/syndromes/decode_many` plus
  `message_from_word`, `syndromes_many`, module constants (N_WORD, K_MSG,
  T…). `decode_many` is the only batch API; callers guarantee u8 0/1.
- `lib/ldpc`: `CODES[rate_id] -> Code`; `decode(llr, code, max_iters,
  alpha=0.8) -> (syndrome_ok, hard, n_iters, extrinsic)`; exports
  `LLR_CLIP=20.0`, `LLR_KNOWN`, `N_BITS`, `Z`.
- `format/tile_codec`: `decode_tile(...) -> (ok, user|None, n_iters,
  syndrome_ok, crc_ok)`; frame calls return the 6-tuple `(ok, children,
  crc_invoked, crc_ok, certified_user_bits, extrinsic)` with children =
  ((n_iters, syndrome_ok), …); `cmy7_iterated_decode`,
  `cmy8_decode_stream`, `cmy7_encode_payload`/`cmy8_encode_payload` (GT
  re-encode kernels), `encode_tile` (K GT), `DEMAP_ITERATIONS=3`.
  Attempt constants `BASELINE_BP_MAX_ITERS=60 / RETRY_BP_MAX_ITERS=150 /
  BP_ALPHA=0.8` are DEFINED IN plugins/tiles.py, nowhere else.
- `format/pilots`: `dust_state_values(row_seed, counters,
  dust_base_cycle, n_dust)` — pass `row.dust_base_cycle`, `row.n_dust`.
- `format/identity`: `resolve_format_ref(ref, n_pages=1)`,
  `coding_printer_ref(coding, printer)`, `build_site_geometry(row)` ->
  SiteGeometry(word_cells_yx, extra_cells_yx, shorten_flat, payload_flat,
  slot_a, slot_b, scramble_planes). K stream fountain_aux is None
  (colour: main=0, C/M/Y=1/2/3) — fixed post-B4; the close dispatches on
  `is None`.
- `format/close`: `close_volume(certs, row) -> CloseResult`,
  `close_count_ready(certs, row) -> bool`, `close_count_status(...)`;
  never raises; pooled k_total handled inside. The ONLY integrity
  exception is `format.fountain.FountainIntegrityError`; the engine maps
  it and the C-6 certificate-conflict raise onto exit 1. OPPOSITE
  metadata bits at one equation index must be caught by the ENGINE's
  certificate merge (dict-shaped equations cannot represent it).
- `lib/decimate`: K sub-native luma rungs MUST go through the 3-D
  `area_decimate` path (float64 RGB mean then float32 box — the frozen
  E018 order); never luma_f32-then-decimate.
- `lib/pava`: exports `CTX_LLR_CLAMP`; `apply_context_offsets` (the ±12
  clamp application) is built in plugins/calibrate.py.
- `lib/owners.freeze_page_owners(order_keys=…)`: keys must be TOTAL
  (heldout_logloss, window-extent-tuple, plane) per C-12.

P5 -> P6 colour surface (P5 builds these in color_model.py with src/holo
names, plain-array args; P6 imports them): `blind_component_bits`,
`fit_qda` -> frozen QdaModel(means, cholesky factors, logdets,
degenerate, clipped_planes), `qda_log_scores`, `cmy7_relative_scores`,
`cmy8_marginal_llrs`, cmy8 dust-PAVA fit + support qualification
(per-plane maps + supported flags), `fit_cmy7_head` -> (head|None,
reason) with Cmy7Head.apply, `reference_states(row, page, cells_yx)` ->
(states i8, kind i8) built on pilots.

P7 exposes `printed_cells_for(row, geometry, page, ty, tx, user_bits)
-> (64,64) u8` (K GT re-encode + word/filler overlay + scramble XOR +
the C-7 known-site check); P8 (refine) consumes it plus data.Placement +
data.WindowEvidence (knots/probs drive lib.pava.calibration_llr).

Engine wiring contract for every plugin: expose PURE module-level entry
functions over (immutable snapshots) -> facts/events tuples; NO engine
imports, NO cross-plugin imports except the pinned P5->P6 and P7->P8
surfaces and data.py/lib/format. In your structured report, LIST the
exact entry-point signatures + the wake conditions (which fact changes
re-arm your jobs) — the integrator wires engine.py from those lists.

Integration amendment (driver ruling 13): the built P1/P2/P3-internal
imports are RATIFIED — survey→intake, place→{pose, words, cold}, cold→pose,
pose→words; color_region's two private splits (color_region_anchor.py,
color_region_ctx.py) are likewise ratified as area-internal modules.

Wave-2 verify duty: oracle-parity for every copied numeric kernel where
the source module imports under env314t (src/holo receive modules and
holo2 solve modules mostly do); focused synthetic fixtures where it does
not; P7 additionally proves an end-to-end mini-loop per family (format
encode -> clean/noisy evidence -> attempt -> certificate == truth,
incl. below-floor and retry150 arming); P9 proves render/serve smoke on
synthetic events. pyflakes clean, no comments/docstrings in holo3/.

## A. Amendments after the build

- **A-1 Canonical vs display identity (2026-08-30, landed onto
  PAGE-DOMAIN 2026-09-02).** Frozen surface S and ruling 04-3 are
  amended. The canonical v2 spelling — the string the seed is made of —
  is FULLY EXPLICIT: reduced rational pitch `{n}i{d}`, sites and
  generation always spelled, uniform rung triplets still contracted. The
  short spelling survives as `display_id`. The two constructors are
  `resolve_format_ref(ref)` (string, including fossils) and
  `mint_format(*, pitch, family, rungs, sites, gen, tiles_yx)`
  (parameters, v2 only). v2 resolve parses then mints. The seed is
  `FormatRow.seed`; there is no `str -> bytes` seeder.

  WHY: the previous canonical form was the SHORTEST spelling, which
  reads `_CLASS_BY_PITCH` and the two defaults tables. A sanctioned
  edit re-keyed an already-minted identity. Measured: appending
  `c5 = 1/120` (five dots at 600 dpi) turned `1i120-k-r0550@7x7`
  into `c5-k-r0550@7x7`.

  SURFACE: `FormatRow` gains `display_id`; `family_seed` is renamed
  `sites_seed` (bytes `holo/v1/sites/pN` unchanged). `_DEFINED_GENS`
  replaces `gen != _DEFAULT_GEN`. Fossils: `display_id == row_id`.
  PAGE-DOMAIN shape is kept: no `n_pages` field, scramble lazy via
  `scramble_plane`.

  CROSS-TREE: src/holo (`parse_format_id` / `mint` / `make_format`) and
  holo2 (canonicalizer + `display_id`) land in the same change. holo3
  sim sheets are RENDERED by src/holo.

  NOT TOUCHED: `conversion_docs/verify/` is the frozen wave snapshot.

- **A-2 The diag fold and its readout split (2026-09-02).** `diag/model.py`
  passed the 1000-line seam signal, and the seam it names is real: the
  module held both `events -> model` and `model -> presentation`. Split
  three ways along that seam, no behaviour change (fast lane and the K
  sim run-dir products byte-identical):

  - `diag/model.py` — the tile-state alphabet, `DiagModel`, `fold`.
  - `diag/readout.py` — rows, advisories, selectors, `status`.
  - `diag/report.py` — `write_events_jsonl`, `build_report`, `write_report`.

  `pin_panes` moved to `panes.py`, where the pane renderer already lives.
  The `TILE_*` ranks moved from `panes.py` to `model.py`: they are the
  alphabet stored in `tile_states`, and `panes` keeps only the chip
  colours keyed by them (it re-exports the names, so `panes.TILE_*`
  still resolves).

  WHY IT IS MORE THAN A SPLIT: the dependency now runs one way,
  `model <- readout <- panes/fields_pane/report`. Before, `model`
  imported `panes` for the ranks while `panes` and `fields_pane` needed
  four readout functions, so both dodged the cycle with function-body
  imports. All four are ordinary module-level imports now. `model` is a
  leaf inside `diag`.

  NOT TOUCHED: `conversion_docs/verify/` is the frozen wave snapshot;
  `panes` still imports `fields_pane` lazily (a separate cycle, not this
  seam).
