# 05 — Fountain outer code + close (functional spec)

Subsystem: `holo3/format/fountain.py`, `holo3/format/streamset.py`,
`holo3/format/envelope.py`, `holo3/plugins/close.py`. Decode-only: holo3
never generates volumes (sim captures are emitted by src/holo tooling).

## 1. Purpose + inputs/outputs

Purpose: turn the run's certified tiles into verified payload bytes, or an
honest non-success. One consult = pure function over a snapshot.

Input (consumed from data.py, all plane-native):
- Certificate set: for each certified (tile, stream): `page:int, ty:int,
  tx:int, stream_id:str` ("main" | "C" | "M" | "Y"), `user_bits:
  np.ndarray uint8 shape (S+1,)` values {0,1} — `user_bits[0]` = the tile's
  metadata bit, `user_bits[1:]` = the S-bit fountain symbol. `source:str`
  tag is pass-through (accounting only; the close is arm-agnostic —
  plane_fields/color_field certificates enter identically).
- Format surface (from the format-identity subsystem; the CloseSpec view):
  `seed:bytes` (= the format id / AES seed), `tiles_yx:(int,int)`,
  `family: Family(K|CMY7|CMY8)`, ordered `stream_profiles:
  ((stream_id:str, symbol_bits:int, fountain_aux:int|None), ...)`,
  `pooled_fountain:bool`. Pitch/cells/FEC/media never reach the close.

Output: `CloseResult` — `status: "open"|"verified"|"integrity_failure"|
"unsupported"`, `payload: bytes|None` (non-None iff verified),
`k_total:int|None`, `blocks: tuple[(block:int, needed:int, have:int,
rank:int, solved:bool, stream_id:str|None)]`, `symbols_used:int`,
`reason:str|None`, `metadata_version:int|None`; plus diag events.
Verified/integrity_failure/unsupported are terminal for the run.

## 2. Algorithm

### 2.0 Keystream primitives consumed (owned by the keystream distill; values pinned here so nothing is guessed)

- KDF: AES-128 key = `sha256(b"holo/v1|" + seed)[:16]`; AES-128-ECB over
  structured 16-byte counters = the format's CTR.
- Counter block layout (all BE): byte0=domain u8, byte1=aux u8, bytes2-4=
  major u24, bytes5-8=u u32, bytes9-12=v u32, bytes13-15=zero.
- Domains: `DOMAIN_FOUNTAIN_ROW=7` (aux=0, major=block, u=row, v=column
  word), `DOMAIN_BLOCK_ASSIGN=8` (aux=0, major=page, u=page-local symbol,
  v=0), `DOMAIN_COLOR_FOUNTAIN_ROW=14`, `DOMAIN_COLOR_BLOCK_ASSIGN=15`
  (aux = stream). Stream aux: `main=0, C=1, M=2, Y=3`.
- `keys64(seed,domain,aux,major,u,v)`: big-endian uint64 of AES block
  bytes 0..7.
- Repair coefficients (packed draw): coefficient c of (block b, row r) =
  bit `c % 128`, MSB-first, of the AES block at (domain, aux, major=b,
  u=r, v=c//128). K/pooled use domain 7 aux 0; CMY7/-v0 colour use domain
  14 at the stream's aux (CMY7 = aux 0 on domain 14, NOT domain 7).

### 2.1 ESI space and family/version dispatch

Flat tile counter `c = page*T + ty*tiles_x + tx`, `T = tiles_y*tiles_x`;
18-bit cap (`MAX_TILES = 2**18`, F12). Dispatch (row identity decides —
never the metadata version, which STAYS 0 on pooled rows, ruled
2026-08-14):

| rows | streams | fountains | ESI | domains |
|---|---|---|---|---|
| K (all rungs) | "main" | 1 | counter | 7/8 |
| cmy7-p120-v0 | "main" (aux 0) | 1 | counter | 14/15 |
| cmy8-p120-v0 (e030/e032 sheets) | C,M,Y (aux 1,2,3) | 3 independent, common k_total | counter, per stream | 14/15 |
| cmy8 -v1 / v2 / sheet-I fossil (`pooled_fountain`) | C,M,Y | 1 pooled | `counter*n + stream_idx` (stream order C,M,Y) | 7/8 |

Pinned widths: CMY7 S=5973 (user 5974); CMY8 per-stream S=2087 (user
2088), equal widths structural for pooling. K rungs' S comes from the
registry row (registry distill carries the exact values).

### 2.2 Block structure (fountain-v2, frozen)

1. `BLOCK_K_MAX = 16384`. `B = ceil(k_total / 16384)` (0 for k_total=0).
2. Balanced split: `base, rem = divmod(k_total, B)`; `K_b = base+1` for
   b < rem else `base`. Block b owns global source rows
   `[offset_b, offset_b+K_b)`, offsets cumulative in block order.
3. Per-(page p, stream s) quota: `quota_b(p,s) = T//B + (1 if
   (b - (p*n + s)) % B < T % B else 0)`; n=1 reduces to the frozen
   `(b - p) % B` — the n=1 bit-identity is the format-fork guard.
4. Shuffle: 64-bit sort key per local tile — K/pooled:
   `keys64(seed, 8, 0, page, local_tile*n + stream, 0)`; -v0 colour:
   `keys64(seed, 15, aux, page, local_tile, 0)`. `order =
   np.argsort(keys, kind="stable")` WITHIN each stream's T keys (stable =
   ties by ascending local tile). The sorted tiles receive the block list
   `[0]*quota_0 ++ [1]*quota_1 ++ ...` ascending b.
5. `row_of`: within (page, stream, block), ascending local tile receives
   consecutive in-block rows starting at the block's cumulative quota over
   all earlier segments `seg = p*n + s`, ascending.
6. Rows `r < K_b` are SOURCE (identity row e_r → global source row
   `offset_b + r`); `r >= K_b` are repair, defined for every larger row
   (rateless). Repair rows are dense ~K_b/2 (§2.0 draw).

### 2.3 Incremental decoder (per VolumeCode)

7. `add_symbol(esi, bits)`: pack to `ceil(S/8)` bytes (MSB-first,
   np.packbits default). Identical duplicate → ignore (return False).
   DIFFERENT value at a seen ESI → FountainIntegrityError, FATAL — mixed
   sheets or upstream fault, never voted (both sides CRC-certified,
   2^-32 class).
8. Per block, attempt solve only when `have >= K_b` AND have grew since
   the last failed attempt (`_failed_at` memo). Deterministic GE input
   order: symbols sorted by (in-block row, esi) ascending.
9. Systematic fast path: all K_b source rows present → stack their
   symbol bits, no GE.
10. Else bit-packed Gauss-Jordan over GF(2): generator rows packed 64
    columns per little-endian-bit uint64 word (INTERNAL packing only —
    the format-wide bit order is MSB-first; never let the little order
    cross an API). Column-order partial pivot, first available row, full
    reduction (pivot rows become unit vectors so the value side IS the
    solution). Values packed alongside and XORed with the rows. rank==K_b
    → solved (K_b, S) source bits; else record rank, stay open.
    Repair-row fill uses one bulk AES draw per block + a 256-entry
    byte-bit-reversal table to convert MSB-first draw bytes into the
    little-packed matrix; mask the last byte to K_b bits (`kb & 7`).
11. Solved blocks are cached; `try_solve` returns the full (k_total, S)
    source matrix only when every block solved, else None.

### 2.4 Metadata → K (consumes format/metadata's `decode_metadata`)

12. Word: 24 bits `[version:1][K:18][reserved:5]`, version 0 the only
    supported one ("unsupported" close status otherwise). LFSR channel:
    degree-24, polynomial 0x100001B (feedback 0x1B), initial state 1;
    equation for index i = LFSR state i; every 24 consecutive indices have
    rank 24. Trust floor: `MIN_METADATA_EQUATIONS = 48` distinct indices.
13. Each certificate donates one GF(2) equation `(index, user_bits[0])`:
    unpooled index = counter (`max_index = 2**18`); pooled index =
    `counter*n + stream_idx` (`max_index = n * 2**18`). -v0 CMY8 streams
    REPLICATE the counter's equation (consistency copies, no extra rank);
    pooled streams carry DISTINCT equations (3x density; dead-plane
    metadata floor ~24 tiles because puncturing every third index breaks
    the consecutive-rank guarantee).
14. Inconsistent certified system → MetadataIntegrityError → close status
    integrity_failure. rank<24 or <48 distinct → open ("incomplete").
    Decoded K field: unpooled `k_total = K_field`; pooled `k_meta =
    K_field`, `k_total = n * k_meta`.

### 2.5 The close (one consult)

15. Snapshot the certificates. Metadata step (14). No K → open /
    unsupported / integrity_failure as above.
16. Build decoder(s) and load every certificate's symbol (shape must be
    (S,) for its stream; counter derived from (page,ty,tx) — holo3 never
    stores a separate counter, so no counter-consistency check exists):
    K/CMY7: one code, ESI=counter. -v0 CMY8: one code PER stream (same
    k_total, that stream's aux/domains), certificates filtered by
    stream_id. Pooled: ONE code with n_streams=3, ESI=counter*3+idx.
    Any FountainIntegrityError during load → status integrity_failure.
17. `try_solve` each decoder. Not all solved → status open; report
    per-block (needed, have, rank, solved, stream_id or None — pooled and
    K have one unattributed block space) and the summed rank shortfall.
18. All solved → unwrap with THREE independent gates (all must pass or
    status integrity_failure, never partial):
    a. Envelope: stream = MSB-first packing of source bits;
       `{sha256:32B}{len:4B BE}{data}`, OVERHEAD_BYTES=36;
       sha256(data[0:len]) must equal the header. The parser ignores
       trailing bytes BY DESIGN, so gates b and c are separate.
    b. Canonical minimal K: `source_symbol_count(len(payload), S_eff) =
       ceil((36+len)*8 / S_eff)` must equal the metadata K.
       S_eff: K/CMY7 = the stream's S; -v0 CMY8 = sum of stream widths
       (6261); pooled = sum too (k_meta compared, = k_total//n).
    c. Zero padding: every encoded bit after the envelope through the
       exact bit capacity `k*S_eff` must be 0, and
       `(36+len)*8 <= capacity` (the final packed byte's storage-only
       zero bits must not masquerade as envelope bits).
19. Stream reassembly before (18): K/CMY7 `np.packbits(source.ravel())`.
    -v0 CMY8: concatenate the three solved (K, S_i) matrices in declared
    stream order C,M,Y at BIT boundaries (never byte-rounded) — the
    stream-major slice of one padded envelope. Pooled: the k_total rows
    ARE the envelope row-major; concatenate rows in order. Bit writer:
    packbits(chunk, "big") then OR into the destination at `bit_offset`
    with the two-shift straddle (`>> shift` and `<< (8-shift)`).
20. All gates pass → status verified, payload returned, sha printed.

### 2.6 Scheduling function (engine contract — no pull machinery)

- The close is NEVER a frontier job: it runs serially in the main thread
  after a merge, over the immutable certificate snapshot.
- Gate, in order: (a) certificate count grew since the last consult
  (the tried-set floor: remember `n_certs_at_last_consult`); (b)
  `close_count_ready` — cheap count-only pass: metadata solvable and, per
  block space, distinct ESIs >= K_b for every block (build the VolumeCode
  mapping, count `block_of(esi)` hits; NO decoder, NO rank, NO
  coefficient rows). Metadata-terminal states (inconsistent, malformed,
  unsupported) report ready so the real close materialises the terminal
  result. Passing says nothing about rank or SHA.
- On ready: run the full close (2.5). verified/integrity_failure/
  unsupported → stop the frontier loop. open → continue; per-block
  shortfalls are scheduling ADVICE only (may prioritise regions, never
  stop or declare anything).
- `--complete`: skip all mid-run consults; one close after the frontier
  reaches fixed point (avoids repeated GE on big-K sheets).
- `--no-close`: never enter the close layer; report certificate counts +
  the count-only block reach, exit non-verified. (holo1's detach-to-open
  semantics are meaningless without resumable state — see open Q2.)
- Cost note: GE at the 16384-row knee is ~1 min/block; every physically
  closed colour volume to date has k_meta well inside the one-solve
  regime (e032: k_meta≈918).

## 3. Copy-vs-rewrite table

COPY-AND-STRIP (bit-exact format law or hard-won numerics; strip
docstrings/validation walls, keep every number and ordering):

| what | source (file:lines) |
|---|---|
| `BLOCK_K_MAX`, `_WORD`, `_REVERSE_BYTE` | holo2/src/holo2/format/fountain.py:101-110 |
| `n_blocks_for` | fountain.py:116-120 |
| `_pack_bits_2d` / `_unpack_bits_2d` | fountain.py:135-153 |
| `_ge_solve_gf2` (pivot order = law of determinism) | fountain.py:156-188 |
| `unpack_rows` | fountain.py:253-255 |
| `VolumeCode` block split + domains (init tail) | fountain.py:288-331 |
| `quotas` / `_cum_quota` / `page_assignment` / `block_row_of` | fountain.py:332-419 |
| `Decoder.add_symbol` conflict rule + `_block_items` order | fountain.py:510-555 |
| `_packed_generator_rows` (bulk draw + byte reversal + tail mask) | fountain.py:557-607 |
| `_solve_block` / `try_solve` | fountain.py:652-746 |
| envelope constants + `source_symbol_count` + `_parse`/`try_unwrap` | src/holo/format/envelope.py:26-93 (drop `wrap`) |
| `_write_bits` / `_nonzero_bits` | holo2/src/holo2/format/streamset.py:355-377,412-432 |
| `reassemble_solved` / `unwrap_solved` gates | streamset.py:380-409,435-481 |
| `pooled_symbol_bits` / `pooled_unwrap_solved` | streamset.py:187-196,229-284 |
| `metadata_from_certificates` observation mapping | holo2/src/holo2/format/fountain_close.py:226-320 |
| `_volume_code`/`_pooled_volume_code`/`_pooled_esi` dispatch | fountain_close.py:407-449 |
| count-only block reach + `close_count_status` | fountain_close.py:452-555 |
| `close_volume` branch structure + unwrap gates | fountain_close.py:630-859 |
| keystream: `kdf`/`counters`/`blocks`/`keys64`/`fountain_rows_bits`/colour variants | holo2/src/holo2/format/keystream.py:83-198,221-247 (keystream distill owns) |
| metadata constants + LFSR + `equation_index`/`max_equation_index` | holo2/src/holo2/format/metadata.py:59-110 (metadata distill owns) |

REWRITE LEAN: `CertifiedStreamSymbol` (becomes data.py Certificate — no
__post_init__ wall, no stored counter), `CloseSpec` (a thin view of the
holo3 format row), `CloseResult`/`CloseBlockProgress` (plain frozen
dataclasses, no validators), the scheduling consult (2.6), the exception
taxonomy (ONE IntegrityError class suffices), diag event emission.

## 4. Measured-channel invariants that MUST survive

- THE STOP IS THE SHA, NEVER A COUNT (L9): rank/symbol counts are advice;
  a solve that fails its digest is a failed volume, never partial bytes.
- ALL ACCOUNTING PER BLOCK (F6, measured): a global symbol count is
  duplicate-gameable and calls volumes finished while a block lacks rank.
- Conflicting certified values at one ESI are FATAL, never voted: both
  sides carry CRC-32, so disagreement is mixed sheets, not noise.
- Canonical-K + zero-padding + capacity gates alongside the SHA: the
  envelope parser alone ignores trailing data, so a wrong-K solve could
  otherwise verify.
- n_streams=1 bit-identity of the pooled generalization: the format-fork
  guard — K rows must produce byte-identical assignments through the
  generalized code path.
- Pooled verified-stop preempts the per-stream floor (measured: c2-v1
  closed at C:48/M:47/Y:47, impossible for -v0): attempt the close on
  pooled counts, never on per-stream floors.
- Dead-plane close: a pooled volume must close byte-exact with ZERO
  certificates from one stream (dead-Y gate, streams exactly {C,M}) —
  no code path may require every stream to appear.
- Discovery/channel tiers never gate the close (e031/e032 inversion):
  the close is the only recoverability truth; attempt whenever counts
  suffice.

## 5. DROP (aggressively)

- All generator planning surface: `rank_reserve_for`, `q_fraction`,
  `source_budget`, `max_k_for`, `retained_pages`,
  `page_capacity_sufficient`, `max_k_for_pages`, `pooled_page_capacity_
  sufficient`, `pooled_max_k_for_pages`, the two/three-tier promise
  arithmetic, the plane-tier dial (`enforce_plane_tier`, q ceilings) —
  decode never consults any of it; the tiers exist in where symbols LAND.
- All encode surface: `pack_source`, `pack_bit_slice`, `encode_symbols`,
  `generator_row` (only `_packed_generator_rows` is used in decode),
  streamset `pack_source`/`pack_payload`/`pooled_pack_*`,
  `envelope.wrap`, `PackedSource`/`PackedSourceSet`.
- Resume/journal/replay: `close_record_from_result`, `CloseRecord`/
  `BlobRef`/`DurableCloseStatus`, certificate_frontier_sha256, terminal-
  record immutability, `--no-close` detach-to-open semantics,
  `metadata_progress`/`CloseProgress`/`count_only` observer projection
  (holo1 §10.4), deferred-close D8 shortfall baselines.
- Validation walls: every `__post_init__` in CertifiedStreamSymbol/
  CloseBlockProgress/CloseSurplusInconsistency/StreamSet/CloseSpec,
  `_validate_close_certificate` (counter is derived, not stored, so the
  binding check has nothing to check), `_validated_stream_count`,
  `_validated_k`, `_validate_bit_values`, `_validate_solved` shape walls,
  isinstance/bool-rejection ceremony throughout.
- `Decoder.rank_status` lazy `_rank_cache` machinery — compute exact rank
  only inside a consult's report for blocks that failed a solve; keep the
  `_failed_at` skip memo (cheap, prevents repeated GE).
- D16 surplus audit (`audit_solved_symbols`, `_surplus_audit`,
  `CloseSurplusInconsistency`) — advisory-only, never outcome-changing
  (open Q1 offers it back as an optional diag).
- The `CertifiedSymbolConflict` vs `FountainIntegrityError` vs
  `MetadataIntegrityError` taxonomy → one exception class + a phase tag
  in the result.
- holo2's `close_spec.py` provenance scaffolding; `codec_id` string
  labels (family enum is the dispatch key).

## 6. data.py needs

Consumes:
- `Certificate` (frozen): `page:int, ty:int, tx:int, stream_id:str,
  user_bits: np.ndarray uint8 (S+1,)` (bit 0 = metadata bit, 1: = symbol),
  `source: str` (producing plugin tag; pass-through). One certificate per
  (tile, stream): a CMY8 tile yields up to three.
- Format-row view: `seed, tiles_yx, family, stream_profiles
  ((stream_id, symbol_bits, fountain_aux), ...), pooled_fountain`.

Produces:
- `CloseResult` as in §1 (frozen dataclass; blocks tuple as plain frozen
  rows). Engine keeps `n_certs_at_last_consult:int` + the last
  CloseResult (main-thread only — the ONLY state this subsystem holds
  between consults; make it an engine field, not module state).
- Diag events: `close.consulted {ready, n_certs}`, `close.result
  {status, k_total, per-block rows, symbols_used, reason}`.

Threading: the consult is a pure function of (certificate snapshot,
format row); Decoder instances are consult-local. Nothing shared, nothing
locked; run it in the single-writer merge thread.

## 7. Pitfalls (from docs/memories)

- Bit-order fork risk: the GE packing is little-bit-order INTERNAL; the
  format is MSB-first everywhere (§13.12). `_REVERSE_BYTE` bridges the
  AES draw into the packed matrix — copy it, never re-derive.
- e012 lesson (never-handroll-seeded-draws): explicit dtypes on every
  keystream/argsort array (`np.int64`, `np.uint64`, `np.uint8`); a
  missing dtype forks the stream silently.
- `np.argsort(..., kind="stable")` is load-bearing: tie order = ascending
  local tile is format law.
- CMY7 is single-stream but rides domains 14/15 at aux 0 — routing it
  through K's domains 7/8 is a silent format fork that still "decodes"
  garbage.
- Pooled rows: metadata K field carries k_meta, NOT k_total; version
  stays 0 (ruled 2026-08-14) — row identity, never the version bit,
  selects pooled semantics.
- -v0 metadata bits are replicated per stream (same equation index);
  feeding them as distinct pooled indices breaks the trust floor and the
  rank math.
- A FountainIntegrityError raised mid-load must land as a terminal
  integrity_failure CloseResult, not a crash (e018 sheet-mixing class).
- Stream boundaries in -v0 reassembly are BIT boundaries, never rounded
  to bytes; the straddle writer's two shifts are exact.
- `used_bits > capacity` check exists because the final packed byte holds
  up to 7 storage-only zero bits — without it they masquerade as envelope
  bits.
- Solve-skip memo: without `_failed_at`, every consult repeats GE on an
  unsolvable block (~1 min at the 16384 knee).
- 2026-08-13 doc lesson: the tier-2 pooled inequality is the stream-exact
  strengthening, not naive nT substitution — irrelevant to decode, but do
  not "restore" planning code from the doc's formulas.

## 8. Open questions for the contract author

1. D16 surplus audit: drop entirely, or keep as an optional diag pass?
   It is advisory-only, but zero-wrong audits were campaign currency
   (69M cells). Recommend: optional diag plugin, off by default.
2. `--no-close` without resumable state: keep as a diagnostics-only run
   mode (counts + block reach, no payload), or drop the flag and let
   `--complete` cover the "don't close mid-run" need? Recommend keep,
   diagnostics-only.
3. Open-status rank reporting: exact GE rank per unsolved block on every
   consult, or count-only (`needed - have` floor) until a block's have
   >= needed solve fails? Recommend the latter (rank only where a solve
   actually ran) — matches holo2's lazy ruling.
4. Persistent incremental Decoder across consults vs rebuild-per-consult:
   rebuild is stateless/simple; incremental saves repeated GE on huge-K
   sheets. Recommend rebuild + the count-growth gate (the physically
   closed corpus is all small-K).
5. May per-block shortfall feed frontier prioritisation (block_of maps
   ESIs to page-local tiles)? Doctrine says advice-only; is it worth the
   coupling in v1 of holo3?
6. Confirm the registry distill pins symbol_bits S for every K rung and
   both colour codecs (the close validates symbol shape and computes
   canonical K from S).
7. Where does `decode_metadata` (LFSR GF(2) solve, rank/consistency
   reporting) live — the metadata/format distill, as assumed here? This
   spec consumes its `(ok, version, k, rank, inconsistent, reason)`
   surface plus `equation_index`/`max_equation_index`.
