# 12 — Tile decode path + payload assembly (slots → certificate → close input)

Sources of record: `holo2/src/holo2/solve/{tiles,records,payload,tilemap,close,certified_labels,families}.py`,
`src/holo/receive/{production_payload,payload_engine,evidence,evidence_blocks,records,color_attempts}.py`.
Kernel-level law (LDPC framing, CRC, banks, demap loop) is owned by `02-ldpc.md`; keystream
draws by `03-keystream-metadata.md`; addressing/site lattice/slot-perm params by
`04-format-identity.md`; fountain algebra, metadata→K, envelope gates and the close consult
by `05-fountain.md`. This spec owns the layer that CONNECTS them: frozen per-tile evidence →
attempt schedule → Certificate → tilemap → close input, one stream-generic path for K/CMY7/CMY8.

## 1. Purpose + exact inputs/outputs

Purpose: the only stage that turns evidence into certified truth, and the only producer of
the close's inputs. Everything here is a pure function of (format row, tile address, frozen
evidence snapshot); certificates are terminal and immutable.

Inputs (per attempt job — an immutable snapshot):
- `address: (page:int, ty:int, tx:int)`; `stream_id: str`; `stage ∈ {scan, union, retry150}`.
- Frozen per-capture tile evidence (see §6), one tensor per contributing capture:
  - K: `(64,64) float64` calibrated bounded LLRs, positive = ink = bit 1, `0.0` = erasure,
    finite only. Tile-local raster order (row-major).
  - CMY7: `(64,64,6) float64` W-relative state scores per cell (order = the six non-W states
    as `channel.CMY7_STATE_NAMES`; detect-side law).
  - CMY8: `(64,64,3) float64` per-plane marginal presence LLRs in plane order `("C","M","Y")`
    (`channel.PLANE_ORDER`).
  - plus `(64,64) bool` observed mask per capture (which cells this capture's owner windows saw).
- Format facts (from the format subsystem): `TileFormat`-equivalent view with
  `seed: bytes(16)`, `family_seed: bytes`, `family ∈ {K, CMY7, CMY8}`, `rate_id` (K) or
  per-stream FEC bank, `n_sites` (= 100 + n_filler for K; 120 for p120 colour),
  `n_transmitted_slots = 4096 − n_sites`, `tile_user_bits`, `symbol_bits = tile_user_bits − 1`,
  `payload_cells` (colour), `tiles_yx`, `tiles_per_page = ty*tx`,
  `max_pages = 2^18 // tiles_per_page`, `stream_ids`, and
  `tile_counter(page,ty,tx) = page*tiles_per_page + ty*tiles_x + tx` (04 §G).

Outputs:
- `Certificate` per certifying attempt (§6 for exact fields) — the ONLY object that leaves
  this stage with payload content.
- Attempt facts for accounting/diag: `(address, stream, stage, state, n_informative,
  n_iters, syndrome_ok, crc_ok, child_outcomes)`, state ∈
  {below_attempt_floor, attempted_failed, certified}.
- Tilemap updates (merge-side): certified set, per-address unresolved streams, done grid.
- Close input: `tuple[CertifiedStreamSymbol]` = for each certificate,
  `(counter=tile_counter(page,ty,tx), page, ty, tx, stream_id, symbol=user_bits[1:],
  metadata_bit=int(user_bits[0]))`. Counter is DERIVED, never stored.
- Final: `close_volume` (05) → verified payload bytes; CLI prints `sha256(payload)`.

## 2. Algorithm

### 2.1 Stream/family dispatch (the stream-generic engine, family unification 2026-07-30)

ONE certificate shape, one tilemap, one attempt schedule, one close-input mapping for all
three families. Per-family facts (all constants):

| family | stream_ids | evidence arity | decode leaf | per-stream user_bits layout |
|---|---|---|---|---|
| K    | `("main",)`      | 1 | `attempt_k_tile` (2.3)      | `[meta_bit | symbol]` |
| CMY7 | `("main",)`      | 6 | cmy7 demap+iterated (2.4)   | `[meta_bit | symbol]` |
| CMY8 | `("C","M","Y")`  | 3 | cmy8 per-stream (2.4)       | `[meta_bit | symbol]` per stream |

Work key = `(page, ty, tx, stream_id)`. A tile address is DONE only when every stream of the
row is certified; a certified sibling stream is never re-attempted, the other streams stay
schedulable (`unresolved_streams(address)`).

### 2.2 Ownership freeze (one owner per cell per capture — L3)

Runs at evidence emission, per capture, before any tensor reaches an attempt (v1's placement
in the colour authority; holo2 re-derived it at decode assembly — pick emission, it is the
one that closed colour). Rule, exact:

1. Candidate pieces = the overlapping placed windows covering the tile in THIS capture, each
   with its calibrated cell values, its observed mask, and its window's context-corrected
   held-out log-loss (every accepted window HAS one — `evidence_blocks._origin_for_window`
   refuses `None`).
2. Sort candidates by `(heldout_logloss, deterministic_tiebreak)` ascending. v1's tiebreak is
   the E022 patch ordinal (arrival order, not rebuildable); holo3 declares a content-derived
   total order instead (window extent tuple, then plane) — the holo2 F1 precedent.
3. Walk in order: `take = piece.observed & ~owned; owner[take] = piece.values[take];
   owned |= take`. The contested cell's OWN value never chooses an owner; an owned cell
   scored exactly 0.0 stays 0.0 (a measured erasure — PAVA emits it at p=0.5), never
   re-assigned to a later pose.
4. Result: one `(values, observed)` tensor per (capture, tile). Cells no piece observed are
   0.0 with observed=False.

MEASURED: ordering by geometry (lowest pose id) instead of held-out loss handed the
worse-calibrated window 90.3–94.1% of contests and cost 27 e029 + 27 xerox certificates;
best-calibrated-first rescued 26–27 with ZERO regressions (holo2 DETECTION-GAP §3).

### 2.3 K attempt chain (numbers in 02 §2.4/2.5; this is the call order)

Given the frozen tensor `x` (scan: one capture; union: element-wise SUM of ≥2 distinct
captures' tensors, summed in a deterministic capture order — sorted by capture sha):

1. `n_informative = count(x != 0 on non-site cells)`; site mask from
   `pilots.site_cell_indices(family_seed, n_filler)` (04 §H), cached per family.
   If `n_informative < k_eff = k_bits − n_sites`: BELOW_FLOOR, no decoder, no CRC.
2. Descramble at ABSOLUTE cell addresses: `scr = keystream.bits(seed, DOMAIN_PAYLOAD, plane,
   page, yy, xx)` for `yy = ty*64..ty*64+63` × `xx = tx*64..`, site cells masked to 0;
   `x *= (1 − 2*scr)`; re-zero site cells. Cache the scramble per (plane, page, ty, tx) —
   descramble + re-encode + retry revisit it.
3. `(a_t, b_t) = keystream.slot_perm_params(seed, counter, n_transmitted_slots)` (04 §I).
4. `decode_tile(x.ravel(), rate_id, site_flat, a_t, b_t, max_iters, alpha=0.8)` —
   `max_iters = 150` iff stage is retry150 else `60`. decode_tile owns the slot-permutation
   inversion and the info-tail shortening (02); NEVER duplicate them here.
5. `ok = syndrome_ok AND crc_ok` → user_bits `(tile_user_bits,)` uint8 → Certificate.
   Otherwise ATTEMPTED_FAILED with `(n_iters, syndrome_ok, crc_ok)` kept for accounting.

### 2.4 Colour attempt chain (`color_attempts.py:217-367`; kernel numbers in 02 §2.6-2.8)

The colour slot-order inversion — THE "slot-raster ≠ codeword order" law for colour
(`_sequential_payload`, `color_attempts.py:149-166`), exact:

1. `payload_flat = pilots.color_payload_cell_indices(family_seed)` — the p120 lattice's
   payload cells as flat tile indices (04 §H).
2. `physical = tensor.reshape(4096, arity)[payload_flat]`;
   `physical_observed = observed.reshape(4096)[payload_flat]`.
3. `order = keystream.color_cell_permutation(seed, counter, payload_cells)`;
   `sequential[order] = physical` (SCATTER, not gather — inverting the emission's
   address-keyed cell order); same scatter for observed.
4. `n_informative = count(observed)` (physical observed payload cells).

CMY7 (single stream "main"):
5. Structural gate BEFORE the expensive demapper: a pack usable iff all
   `CMY7_CELLS_PER_PACK = 4` slots observed; `mapped_support = repeat(complete, 11)`;
   scatter through the REAL inverse interleave `code_support[interleave] = mapped_support`
   (`interleave = keystream.cmy7_interleave_permutation(seed, counter, transmitted_bits)`);
   every child must reach `active_information_bits` of support (`(2240,1883,1883)` for the
   baked bank). Fail → BELOW_FLOOR.
6. `cmy7_llrs = cmy7_demap_payload(sequential, observed, bank, interleave, dither)` with
   `dither = keystream.cmy7_dither_bits(seed, counter, transmitted_bits)`; RE-GATE on
   per-child nonzero-LLR counts (`_children_meet_floor`, `color_attempts.py:200-214`).
7. `cmy7_iterated_decode(..., max_iters, alpha=0.8, demap_iterations=3)` (02 §2.7). The
   demap↔BP loop lives INSIDE one attempt; extrinsic never escapes; `n_iters` sums children
   over all passes; `demap_iterations=3` is part of the decoder identity.

CMY8 (per stream, only unresolved streams attempted):
5. `plane = stream_ids.index(stream_id)`; floor:
   `count(observed & (sequential[:, plane] != 0)) >= active_information_bits`.
6. `cmy8_decode_stream(sequential[:, plane], bank, cmy8_dither_bits(seed, stream_id,
   counter, transmitted_bits), max_iters, alpha=0.8)` (02 §2.8).

Both: certify iff all children's syndromes AND the bank CRC pass; record per-child
`(n_iters, syndrome_ok)` pairs (`child_outcomes`) for diag.

### 2.5 Certificate mint + user-bit packing (format law)

`user_bits` is a `(profile.user_bits,)` uint8 0/1 vector. Persistent/packed form (if data.py
packs): `np.packbits(user_bits, bitorder="little")`, padding bits zero; unpack with
`np.unpackbits(..., bitorder="little")[:user_bits]` (`records.py:35-50, 222-225`). NOTE the
bit-order zoo: certificate packing is LITTLE; CRC-32 input packing and envelope/stream
packing are MSB-first (02 §2.4, 05 §2.5). Never mix.

Zero-wrong stack (what makes a certificate trustworthy, each independent):
- addressing: the tile's counter came from a BCH(127,50) address word at true d=27 (01) —
  a mis-addressed tile needs ≥14 hard word errors to alias;
- inner: LDPC syndrome (all children) AND CRC-32 over the user bits (~2^-32/attempt;
  CMY7 demap loop may expose the CRC up to 3×/attempt — registered compromise, 02 §2.7);
- close: per-block GF(2) solve + surplus-symbol audit + envelope sha256 over the whole
  payload (05 §2.5.18). Measured record: 0 wrong in 69,066,304 audited cells.

CONFLICT LAW (merge-time, fatal): two certificates at one work key with differing user bits
= mixed sheets or an upstream fault — raise, never vote, never tie-break by recency
(`records.py join_tiles:542-549`, `CertificateStore.add:314-321`, HOLO-DESIGN §6.3). An
identical duplicate (race corroboration) is a no-op keeping the standing source tag.

### 2.6 Attempt schedule (the scheduling FUNCTION for the engine's frontier loop)

Per (address, stream), in cost order — describes gating/order only, no pull machinery:

1. SCAN: first time a capture's frozen evidence for the tile reaches the floor — one attempt
   per (capture, address, stream), over that capture's tensor alone. Each new capture's
   evidence for an unresolved tile arms a fresh scan (v0.27 lesson: scan reads ONLY the one
   capture's evidence, never the merged frontier).
2. UNION: when ≥2 DISTINCT captures (distinct source scans, same declared dpi footing) hold
   evidence on an unresolved (address, stream): one attempt over the element-wise sum. A new
   capture joining re-arms the union (new evidence set = new attempt).
3. RETRY150: after scan/union reach fixed point AND the close is not count-ready (05 §2.6
   cheap pass): for each (address, stream) whose LATEST ordinary attempt was
   ATTEMPTED_FAILED (decoded, failed — not below-floor) and holds no certificate, exactly
   ONE retry at max_iters=150 over the IDENTICAL evidence snapshot of that failed attempt —
   never tunnelling past baseline evidence (`payload_engine.py:264-302` asserts the
   component set is unchanged).
4. Tried-set floor: an attempt is keyed by (address, stream, stage, evidence-set epoch,
   decoder params); identical key never re-runs. New evidence (a new capture, an arm's
   supplemental emission, a refine re-emission) bumps the epoch and re-arms scan/union;
   only the 60→150 bump arms retry.
5. Certified work keys leave the frontier permanently; a certified address with unresolved
   sibling streams stays in it for those streams only.
6. Cost tiers: scan < union < retry150; within a tier, deterministic address order
   (sorted work key). Payload attempts price below placement expansion at equal depth
   (holo2 measured ranking); an attempt over deeper-lane (finer-ppc) evidence prices above
   a coarse one (`LANE_COST_PER_RUNG = 2` per rung — keep the constant if scale-space lanes
   carry rungs, else drop).

Threading: each attempt is a pure job over its snapshot; results (attempt facts +
certificate) are FACTS merged serially by the main thread. Payload is worker-count
independent because certificates commute (conflict = fatal either way) and counters are sums.

### 2.7 Tilemap (single-writer, in-memory, derived)

Plain dicts owned by the merge thread; workers receive immutable snapshots.

- `certs: dict[(page,ty,tx,stream), Certificate]` — the authority.
- `failed: set[(page,ty,tx,stream)]` (latest ordinary attempt failed) — the retry frontier's
  domain; `attempt_epoch: dict[work_key, int]` — the tried-set floor.
- `unresolved_streams(address) = tuple(s for s in stream_ids if (…,s) not in certs)`.
- `done_tile_grid(page) -> (tiles_y, tiles_x) bool`: True where EVERY stream certified
  (iterate certified cells, not the grid — `tilemap.py:704-721`).
- Done projection (§6 gate feeding the placement/scheduling side, `tilemap.py:750-823`):
  per (capture, region), `done` bool over the region's cell lattice; for each placed
  window's pose: map the window extent's cell CENTRES
  (`origin + pitch*(idx+0.5)`) through `invert_affine(pose.native_affine)` to page cells,
  `ty,tx = floor(cell)//64`, mark cells landing in fully-certified tiles AND supported;
  OR into `done`. A window whose whole supported extent is done is never scheduled again
  (`DoneProjection.covers`: all-unsupported = dead, not done). One pose per window — with
  refine arms, the LATEST adopted pose replaces (never unions with) its parent's projection
  (measured: union over-claimed +860/+588 cells on e029/xerox).

### 2.8 Certified re-encode (GT service for refine/detect labels)

`printed_cells_for(spec, address, user_bits) -> (64,64) uint8` — the K printed field,
bit-exact Track-1 recreation (`tiles.py:249-271, 380-401`):
1. `cells = ldpc_tile.encode_tile(user_bits, rate_id, site_flat, a_t, b_t)` (02 §2.4).
2. Overlay the address word: `tile[word_cells_yx] = pilots.word_values(seed, counter,
   plane)[0]` (01/04).
3. Overlay filler (if `n_filler > 0`): `tile[fy,fx] = keystream.bits(seed,
   DOMAIN_FILLER_VALUES, plane, page, ty*64+fy, tx*64+fx)`.
4. XOR the page scramble: `tile ^= _tile_scramble_bits(page, ty, tx)`.

Mint once per certificate (~4 KB) — compute at merge time when the certificate lands and
keep it beside the certificate (no shared mutable cache in worker threads). GT at all 4096
cells (site values reproduce EXACTLY because the scramble is zeroed at sites); the substrate
refine correlates against and the detector labels from. Colour has NO full-field re-encode
in core (v1 refuses non-K, `records.py:263-265`); colour certified-state projection is a
detect-side leaf needed only by dropped audits/arms.

### 2.9 Close input assembly + envelope

After each merge that grew `certs` (and at fixed point), the main thread may consult the
close (05 §2.6 owns the gate/modes). Input assembly, exact
(`close.py certified_symbols:122-137` / `records.py certificate_for_close:182-201`):
for every certificate, emit `CertifiedStreamSymbol(counter=tile_counter(page,ty,tx), page,
ty, tx, stream_id, symbol=user_bits[1:], metadata_bit=int(user_bits[0]))`. One consult per
certified frontier, never per stream (a per-stream consult could report a partial close).
Metadata→K, per-block counts, GF(2) solve, stream reassembly, and the three envelope gates
(`{sha256:32B}{len:4B BE}{data}`, canonical minimal K, zero tail padding) are all 05's.
`verified` → payload bytes out, print sha256, stop the frontier loop.

## 3. Copy-vs-rewrite table

COPY-AND-STRIP (bit-exact format law or measured numerics; strip docstrings, validation
walls, identity plumbing; keep every number and ordering):

| what | source file:lines |
|---|---|
| K site geometry + k_eff floor | holo2/src/holo2/solve/tiles.py:119-144 |
| absolute payload scramble derivation (site-zeroed) | tiles.py:147-174 |
| slot-perm param fetch | tiles.py:177-182 |
| descramble + informative count | tiles.py:203-214 |
| K printed-field re-encode (word+filler+scramble) | tiles.py:249-271, 380-401 |
| `attempt_k_tile` chain (floor→descramble→decode→certify) | tiles.py:317-377 |
| freeze walk `take = observed & ~owned`, order `(loss, tiebreak)` | holo2/src/holo2/solve/payload.py:781-833 |
| union component order + per-footing sum | payload.py:677-695 |
| certificate→close-symbol mapping (`symbol=user[1:]`, `meta=user[0]`) | src/holo/receive/records.py:182-201; holo2 close.py:122-137 |
| user-bit little-endian pack/unpack | src/holo/receive/records.py:35-50, 222-225 |
| conflict law (differing bits at one key = fatal) | holo2 records.py:542-549; src/holo records.py:308-321 |
| colour physical→sequential inversion (payload_flat + scatter by color_cell_permutation) | src/holo/receive/color_attempts.py:149-166 |
| CMY7 structural pack gate + inverse-interleave scatter | color_attempts.py:243-258 |
| per-child active-information floor | color_attempts.py:200-214 |
| colour attempt flow (gate→demap→iterated/stream decode→facts) | color_attempts.py:217-367 |
| union tensor sum in sorted capture order | src/holo/receive/evidence_blocks.py:779-803 |
| scan→union→(preclose)→retry150 stage semantics + retry-baseline pin | src/holo/receive/payload_engine.py:159-304 |
| done projection (centres→inverse affine→tile grid→support AND) | holo2/src/holo2/solve/tilemap.py:750-823 |
| sparse done_tile_grid | tilemap.py:693-721 |
| certified-frontier conflict collation (if labels arm kept) | holo2/src/holo2/solve/certified_labels.py:157-179 |
| format-known-site agreement check (e012 tripwire, see §8) | certified_labels.py:364-389 |

REWRITE LEAN (fresh code, keep only semantics): the attempt job wrapper (one function per
family behind one `decode(evidence, stream_id, stage)` signature), Certificate/TileMap
dataclasses (no __post_init__ walls), the frontier scheduling function (2.6), attempt/diag
counters, close consult glue. `RecordingLeaf`/`AttemptLeaf`/`EngineRun`,
`RealPayloadProvider/Worker`, `CertificateStore`, `StoreIndex.updated` all collapse into
~150 lines of plugin + engine-merge code.

## 4. Measured-channel invariants that MUST survive

- Bounded LLR (018.7, L2): each capture's calibrated output is bounded by its PAVA label
  count BEFORE any sum; no post-sum clamp — a fixed clamp changes reliability ratios and
  was never qualified.
- Finite-only, `0.0` = erasure: an accepted `inf` once turned a below-floor entry into a
  maximum-strength decoder input (the one input check that stays).
- Attempt floor `n_informative >= k_eff` before ANY decode — fewer observations than
  unknowns cannot determine the codeword; also the CRC-exposure saver.
- One owner per cell per capture, ranked by context-corrected held-out loss on
  FORMAT-KNOWN sites — geometry-ranked ownership measurably cost 54 certificates; the
  cell's own value never picks its owner (self-confirmation).
- Union only over ≥2 DISTINCT physical captures at one declared dpi; never raw+decimated
  of one capture, never cross-arm/lane sums (print-correlated errors defeat equal-weight
  combining until the ctx detector de-correlates — F1∘F6 law).
- Retry150 decodes the IDENTICAL baseline evidence — retry must not tunnel past what the
  failed attempt saw, or it is a different (uncounted) attempt.
- Certificate conflict is FATAL, never voted (zero-wrong is a doctrine, not a statistic).
- CMY8 per-plane independence (graceful dead-plane degradation) vs CMY7 joint packing is
  the e032 ordering-inversion mechanism — never gate colour attempts on discovery-tier
  rankings (channel gate ≠ receiver).
- CMY7 demap↔BP exchange stays INSIDE one attempt; extrinsic never escapes; erased packs
  emit exactly 0.0 across all passes.
- Slot-raster ≠ codeword order, both families: K via the affine slot permutation, colour
  via payload lattice + address-keyed cell permutation + interleave. GT only via re-encode
  from the format chain, never retyped or re-derived by hand (e012).
- Certified re-encode is exact GT at all 4096 cells — the labels/refine substrate; conflicts
  with the format field at a known site mean wrong address or forked keystream, not noise.

## 5. What to DROP (aggressively)

- The whole durable-record apparatus: journal/commit wall/transition laws
  (`families.py` entirely), MintRef/read-set identities, spend ledger, `crc_exposure`
  bookkeeping, `attempted_work_keys`, attempt_id/certificate_id sha identities
  (`stream_attempt_identity`, `stream_certificate_identity`, `sha256_parts_be`) — no
  resume means in-memory dedup by plain keys suffices; the source tag replaces provenance
  hashes.
- `StoreIndex` copy-on-write maintenance, collections/wake subscriptions, provider
  expand/mint/decline machinery, the F-17 frontier memo, `TileState` display enum,
  `WindowRecord`/`PoseRecord`/`EvidenceObservation` families (poses/windows live in the
  place subsystem's own data).
- EvidenceBlock BINARY serialization (magics, _Reader, content sha, natural-number codec,
  `to_bytes/from_bytes`), `blocks_from_frontier`, `blocks_from_owner_pages`,
  mop-up supersession (`validate_block_supersession`, `supersede_with_committed`,
  `apply_mopup_supersession`, `SupersessionDrops`, `winner_codes`) — mop-up lanes were a
  resumable-session construct; holo3's cascade emits each capture's evidence once.
- DIVERGENCE AUDIT: DROP from src/holo/receiver/ (`certificate_divergence`, `color_divergence`,
  DivergenceRecord, PayloadArtifact/PayloadProduct). It is non-gating advice whose one job
  (empirically guarding the CMY7 CRC-exposure compromise and mixed-sheet detection) is
  better served by a `_distill/verify/` script run at acceptance against the real corpora.
- holo2's incremental close state (`_MetadataGate`, `_StreamCounts`, `_CloseState`,
  `close_is_new`) — 05's count-only ready pass + consult-on-growth replaces it; the
  echelon-basis eliminator is an optimization for 1,358 consults/run that holo3's
  consult-after-merge cadence does not need.
- Certified label ENRICHMENT of calibration pools (`CertifiedLabelSource`,
  `FormatOnlyLabels`, `CertifiedFrontier` caching, `LABEL_KIND_CERTIFIED`) — measured +68%
  fit cost, ZERO yield on every corpus; keep only `printed_cells_for` (2.8) as the pure GT
  function; the enrichment is a future arm behind the same function.
- Advisory preclose closure plumbing (`preclose` callback, `terminal_close`) — the engine's
  own close consult (2.9) plays this role; retry gating reads the same count-ready answer.
- Quarantine/contradiction records and evidence exclusion filters (`is_quarantined`,
  W5 machinery): an address-word contradiction in holo3 is a place-subsystem event; its
  evidence is simply not emitted (see §8 Q4).
- All `_validate_boundary`/`_identity`/`_sha256`/`_nonnegative` walls, `readonly_array`
  wrapping, `decoder_profile` strings, `child_outcomes` cross-checks, halo blob
  shape-versioning (`ring_masks`, `pack_piece_observation`, `unpack_piece_halo`) — the ctx
  halo, if the detect subsystem carries it, travels as plain arrays inside the job, not as
  packed blobs.

## 6. Data-structure needs for src/holo/receiver/data.py

All frozen dataclasses, plane-native, numpy fields immutable by convention:

- `TileKey = tuple[int, int, int, str]` (page, ty, tx, stream_id).
- `Certificate`: `page:int, ty:int, tx:int, stream_id:str, user_bits:np.uint8 (user_bits,)`,
  `source:str` (producing plugin, e.g. "tiles/scan", "tiles/union", "tiles/retry150",
  "refine/…"), `stage:str`. Derived: `metadata_bit = int(user_bits[0])`,
  `symbol = user_bits[1:]`, `counter` via the format row. No id hash, no packed form unless
  memory demands it (then little-endian packbits, 2.5).
- `TileEvidence` (per capture × tile, post-freeze): `capture_id:str (sha256)`,
  `page,ty,tx:int`, `values: float32 (n_observed, arity)` + `observed_flat: uint16
  (n_observed,)` sorted (compact — the measured memory shape for 22 GB colour decodes), or
  equivalently dense `(64,64,arity) float32` + `(64,64) bool`; `arm:str` (lane/arm tag —
  scan/union sum only within one arm). Densify to float64 at the attempt boundary only.
- `AttemptFact` (event/counter, transient): key, stage, state, n_informative, n_iters,
  syndrome_ok, crc_ok, child_outcomes, wall seconds — consumed by diag + per-plugin
  accounting, never re-read for decisions except the failed→retry frontier bit.
- `TileMap` (engine-owned, single-writer): `certs: dict[TileKey, Certificate]`,
  `printed: dict[TileKey, np.uint8 (64,64)]` (K, minted at merge),
  `failed: set[TileKey]`, `epoch: dict[TileKey, int]`, per-page done grids.
  Workers get read snapshots; merge applies the conflict law (2.5).
- `CertifiedStreamSymbol` (close input, 05's shape): counter, page, ty, tx, stream_id,
  symbol (uint8 bits), metadata_bit.
- Stateful/shared things the contract must make snapshots or reductions: the tilemap (facts
  merge), the tried-set/epoch map (merge-side), the printed-cells mint (merge-side), the
  per-(plane,page,tile) scramble/geometry caches (pure functions of format facts — safe to
  memoize per worker or precompute once at startup; do NOT share a mutable dict under
  free-threading).

ARM API needs (do not spec as core): plane_fields / color_field / supplemental u-lanes act
upstream of this stage — they emit ADDITIONAL or REPLACEMENT `TileEvidence` (new arm tag or
new epoch for a capture×tile). The tile stage needs only: (a) evidence epochs so arm
emissions re-arm attempts; (b) the arm tag kept out of union sums across arms; (c)
`printed_cells_for` exposed for refine's certified correlation targets. The colour closes
predate all arms — none of 2.2–2.5 may depend on an arm being present.

## 7. Pitfalls / incidents (docs + memories)

- e012 phantom payload: hand-rolled seeded draws forked the numpy stream (missing dtype=).
  Every keystream consumption here goes through the carried keystream module; GT via
  re-encode only. Golden keystream vectors pin it at build time.
- 018.7 LLR honesty: an unbounded calibrated LLR reached the decoder as ±inf and certified
  from evidence the floor had excluded — hence finite-only + bounded-at-source (L2).
- v0.27 second-capture crash: passing the merged frontier as the SCAN input minted scan
  attempts over prior captures' components; scan is one capture, union is the frontier
  (`production_payload.py:426-431` comment block is the record).
- 2026-08-02 starved-window crash: building provenance for UNREFERENCED (refused) windows
  crashed the first real capture retaining one — mint owner facts only for windows that
  actually own cells (moot if provenance is dropped, instructive if kept).
- Truth-path discipline: `make_data` payloads drift (self-referential); slot-raster ≠
  codeword order — validate any GT reconstruction against certified tiles FIRST before
  using it to judge evidence.
- holo2 F1 fallback trap: a window without a published held-out loss ranked `inf` and lost
  every contested cell regardless of quality. holo3 avoids the class by requiring every
  accepted window to carry its loss at emission (v1's contract).
- CMY7 support scatter direction: `code_support[interleave] = mapped_support` — gathering
  instead of scattering silently misgates children.
- Below-floor is NOT a failed baseline: no decoder ran, so it must not arm retry150
  (deriving retries from tile-level "attempted" armed BP-150 on never-decoded footings —
  the 2026-08-11 review P1).
- e029: certification failures were NOT edge-dominated (interior banding rows) — no
  edge-only shortcuts in the frontier order.
- Bit-order zoo (2.5): little-endian certificate packing vs MSB-first CRC/envelope packing
  — a swapped order is a silent format fork that the CRC will "catch" as 100% decode
  failure, wasting a debugging day.
- Two certified decodes AGREEING via different routes is corroboration (keep the standing
  source), not a conflict — only differing bits are fatal.

## 8. Open questions for the contract author

1. Freeze placement: this spec puts the ownership freeze at evidence emission (v1 style,
   per capture) so the tile stage consumes one-owner tensors. Confirm against the
   detect/place distill so the seam is declared exactly once — including where the H5/F1
   ctx correction is applied (v1: whole-window correction BEFORE the freeze; the tile stage
   must receive already-corrected values either way).
2. Divergence audit disposition: DROP from src/holo/receiver/ recommended here, with a
   `_distill/verify/` divergence script for acceptance runs 2–7. Confirm, since it was the
   registered empirical guard for the CMY7 CRC-exposure compromise.
3. Format-known-site agreement check on certified re-encode (certified_labels.py:364-389):
   keep as one `np.array_equal` at mint time (cheap, catches wrong-address/forked-keystream
   catastrophically early), or verify-time only? Charter's no-guards rule vs zero-wrong
   doctrine — needs a ruling.
4. Contradiction/quarantine: with no durable state, does an address-word contradiction
   (place subsystem) need to retract already-emitted evidence from the tilemap frontier, or
   is refusing future emissions enough? (holo1's terminal-ingest guard is the precedent;
   certificates already minted are certificate-backed and stand.)
5. Retry gating epoch: "close not count-ready" requires the metadata→K count pass at
   frontier fixed point. Confirm the engine consults close once per merge batch (05 §2.6)
   and the retry tier reads that cached answer, so no plugin ever imports the fountain.
6. Compact vs dense evidence in memory: sparse `(values, observed_flat)` float32 (the
   measured 22 GB shape) vs dense `(64,64,arity)` float32 per capture×tile. Recommend
   sparse for colour at 2400/4800 dpi corpora, dense acceptable for K sheets — pick one for
   data.py.
7. `LANE_COST_PER_RUNG = 2`: keep only if the scale-space cascade distill keeps rung-depth
   lanes; otherwise the attempt cost tiers collapse to scan<union<retry.
8. Pooled cmy8 -v1 rows: close-side ESI mapping (counter*3+idx) is 05's; the tile stage is
   identical (same per-stream banks/streams). Confirm no acceptance target needs -v1 so the
   tile stage carries zero pooled-specific code.
