# 03 — Keystream (AES-128-CTR by address) + metadata channel

Subsystem spec for holo3 `format/keystream.py` + `format/metadata.py`.
Authority chain: `src/holo/core/keystream.py` (gen side, read-only) is THE
format authority; `src/holo/core/keystream_spec.py` is the stdlib-only
normative mirror (golden-vector pinned by the main worktree's
`tests/holo/test_keystream.py`) — use it as the bit-exact oracle in
`_distill/verify/`. holo2's `format/keystream.py`/`format/metadata.py` are
character-for-character carries of the same algebra (holo2 lacks
`payload_bits` and the colour domains 9–13 helpers; src/holo has them all).

## 1. Purpose + inputs/outputs

Every format-defining pseudorandom surface — payload scramble, pilot word
values, filler values, site constructions, slot-permutation parameters,
colour permutations/dithers, fountain repair rows, block-assignment keys —
is one pure function of (seed, address). No sequential stream, no
consumption state, no numpy RNG anywhere. Any fragment regenerates exactly
its own slice. The metadata channel recovers `(version, K)` from one
CRC-certified LDPC user bit per tile (per stream on colour rows) via a
degree-24 LFSR GF(2) system.

Keystream inputs: `seed: bytes` (non-empty; the format id IS the seed),
`domain: int` (0..255), `aux: int` (0..255), and int64 address arrays
`major` (0..2^24-1), `u`, `v` (0..2^32-1) that numpy-broadcast against
each other. Outputs: `blocks -> (N,16) uint8`; `bits -> (N,) uint8 0/1`;
`keys64 -> (N,) uint64`; `bounded_draws -> (N,) int64 in [0,bound)`;
`slot_perm_params -> (a,b) int64 arrays`; `fountain_rows_bits ->
(n_rows, n_cols) uint8`; permutations `-> (size,) int64` source-index
order (`output = input[perm]`).

Seeds supplied by the format-identity module (see distill 02/format):
- legacy row seed: `f"holo/v1/{coding_id}/{cells_y}x{cells_x}".encode()`
  (e.g. `b"holo/v1/c2-r0700/3392x2368"`);
- v2 row seed: `b"holo/v2/" + spec_id.encode()`;
- fossil seeds: verbatim frozen byte strings from the fossil table
  (`src/holo/format/fossils.py`) — byte-matched, never re-derived;
- family seed: `f"holo/v1/sites/p{n_sites}".encode()` — `b".../p100"` (K),
  `b".../p120"` (colour). Site constructions (domains 4/5) key on the
  FAMILY seed (lattice acquisition shared across rows); everything else
  keys on the ROW seed.

Metadata inputs: iterable of `(equation_index: int, bit: 0|1)` from
certificates. Output: `(version, k, rank, n_unique, inconsistent)` —
holo3 keeps exactly the fields the close gate and diag consume.

## 2. Algorithm

### 2.1 KDF and counter (format law, all constants)

1. `key = SHA-256(b"holo/v1|" || seed)[0:16]` — AES-128 key. KDF prefix
   is `b"holo/v1|"` for BOTH namespaces (v2 identity lives in the seed
   payload, not the prefix).
2. Counter block, 16 bytes, ALL fields big-endian:
   `[0]=domain  [1]=aux  [2:5]=major (24-bit)  [5:9]=u (32-bit)
   [9:13]=v (32-bit)  [13:16]=zero`.
3. `block(addr) = AES-128-Encrypt(key, counter(addr))` — FIPS-197. ECB
   over structured counters == CTR with an explicit counter. Implement
   with `cryptography` (OpenSSL); chunk AES calls at `_CHUNK_BLOCKS =
   1<<20` counters (16 MiB) so peak memory is chunk + output.
4. `bit(addr) = block(addr)[0] >> 7` (MSB of byte 0).
5. `keys64(addr)` = big-endian uint64 of block bytes 0..7.
6. ONE BYTE-ORDER DOCTRINE (§13.12): every multi-byte field big-endian,
   every bit string MSB-first — bit j of a byte string is
   `(byte[j//8] >> (7 - j%8)) & 1`; numpy's default
   `packbits/unpackbits` bitorder ("big") is the format's. No LSB-first
   spelling exists anywhere on the format surface.

### 2.2 Domain table (frozen; never renumber, only add)

Plane index = `'CMYK'.index(plane)`: C=0 M=1 Y=2 K=3 (`PLANE_K = 3`).
Colour stream aux: 0=CMY7 "main", 1=CMY8 C, 2=CMY8 M, 3=CMY8 Y.

| # | name | aux | major | u | v | draw form |
|---|------|-----|-------|---|---|-----------|
| 1 | payload scramble | plane | page | cell y | cell x | 1 bit |
| 2 | pilot word values | plane | 0 | site idx | 0 | 1 bit |
| 3 | filler values | plane | page | cell y | cell x | 1 bit |
| 4 | pilot sites | 0 | 0 | quota idx | retry | bounded draw |
| 5 | filler sites | 0 | 0 | filler idx | retry | bounded draw |
| 6 | slot-perm params | 0 | 0 | tile ctr | retry | 16-bit rejection |
| 7 | fountain rows | 0 | block | row | col word | packed 128 bits |
| 8 | block assignment | 0 | page | local tile | 0 | keys64 |
| 9 | color dust order | 0 | tile ctr | base ordinal | 0 | keys64 perm |
| 10 | CMY7 interleave | 0 | tile ctr | code-bit idx | 0 | keys64 perm |
| 11 | CMY7 dither | 0 | tile ctr | wire-bit idx | 0 | 1 bit |
| 12 | color cell order | 0 | tile ctr | state ordinal | 0 | keys64 perm |
| 13 | CMY8 dither | stream | tile ctr | cell ordinal | 0 | 1 bit |
| 14 | color fountain row | stream | block | row | col word | packed 128 bits |
| 15 | color block assign | stream | page | local tile | 0 | keys64 |

K rows use domains 1,2,3,4,5,6,7,8. CMY7 uses 2*,4,5,9,10,11,14,15 at
aux=0; CMY8 uses 2*,4,5,9,12,13,14,15 with streams at aux 1..3 for
13/14/15. (*colour word/dust VALUES come via the pilots module's
state-draw functions over the row seed — the addressing distiller owns
them.) Colour NEVER uses domains 1/3/6: colour whitening = keyed
permutations + dither bits inside the tile codec, not a page scramble.

### 2.3 Draw forms

7. **Bounded draw** (domains 4/5; `bounded_draws(seed, domain, u, bound)`
   with `1 <= bound <= 256`): `limit = 256 - (256 % bound)`; scan block
   bytes 0..15 of `block(domain, 0, 0, u, retry)` starting at retry=0;
   the FIRST byte `b < limit` yields `b % bound`; if all 16 bytes reject,
   retry with v=retry+1. (The retry>64 runaway raise in the original is a
   guard — see §5.)
8. **16-bit rejection scan** (domain 6; `slot_perm_params(seed,
   tile_counter, n_slots)`, `2 <= n_slots <= 65536`): read big-endian
   16-bit words from block bytes (0,1),(2,3)..(14,15) of
   `block(6, 0, 0, tile_counter, retry)`, retry=0,1,...; word w is
   admissible iff `w < 65536 - (65536 % n_slots)`, value `w % n_slots`.
   `a_t` = the FIRST admissible value with `gcd(value, n_slots) == 1`;
   `b_t` = the NEXT admissible value after a_t was taken (a word consumed
   for a_t never doubles as b_t), unconditioned. Non-admissible or
   non-coprime words are consumed and skipped in scan order. Permutation:
   `slot j -> (a_t*j + b_t) % n_slots` over transmitted code positions,
   `n_slots = 4096 - n_sites` (3996 for K p100).
9. **Packed fountain rows** (domains 7/14; `fountain_rows_bits(seed,
   block_index, rows, n_cols)` / colour variant with stream aux):
   coefficient c of (block, row) = bit `c % 128` MSB-first of the AES
   block at `v = c // 128`; implement as `np.unpackbits(blocks.reshape(
   n_rows, n_words*16), axis=1, bitorder="big")[:, :n_cols]` with
   `n_words = ceil(n_cols/128)`.
10. **Key-sort permutation** (domains 9/10/12; `_item_permutation`):
    `keys = keys64(seed, domain, 0, tile_counter, arange(size), 0)`;
    `perm = np.lexsort((arange(size), keys))` — ordinal tie-break makes
    key collisions fully specified. Sizes come from the codec profile
    (p120-v0 values: dust 20, CMY7 interleave 10934, colour cells 3976).
11. **Dither bits** (11/13): `bits(seed, dom, aux, tile_counter,
    arange(transmitted_bits), 0)` (CMY7 aux=0 size 10934; CMY8 per-stream
    aux 1..3 size 3976).
12. **Page scramble** (K only): `payload_bits(seed, plane, page,
    (h_cells, w_cells))` = domain-1 bits at ABSOLUTE cell coordinates,
    generated row-stripe-wise. Gen: `field ^= scramble & ~site_mask`
    (site cells excluded). Receive: per-tile scramble
    `bits(seed, 1, plane, page, abs_y, abs_x).reshape(64,64)` with site
    cells zeroed; LLR descramble = `llr * (1.0 - 2.0*scr)` then site
    cells forced to exactly 0.0 (erasure). Filler cells (domain 3, K rows
    with n_filler>0 — none in the printed record) carry
    `bits(seed, 3, plane, page, abs_y, abs_x)` verbatim, unscrambled.

### 2.4 Metadata channel (format law F6)

13. Word `M` = 24 bits: `M[0]=version`, `M[1:19]=K` big-endian (M[1] is
    K's MSB), `M[19:24]=reserved zeros`. Constants: `METADATA_BITS=24`,
    `K_BITS=18`, `MAX_K=2^18`, `VALID_VERSIONS=(0,1)`, receiver
    `SUPPORTED_METADATA_VERSIONS={0}`, `COUNTER_BITS=18`,
    `MAX_COUNTER=2^18`, `MIN_METADATA_EQUATIONS=48`.
14. Word-as-integer mask packs M[i] at INTEGER BIT i (LSB-first packing
    of word index): `mask = sum(M[i] << i)`. Do not confuse with the BE
    K field inside the word — both orders coexist, both are law.
15. LFSR: degree-24, primitive polynomial x^24+x^4+x^3+x+1
    (`LFSR_POLYNOMIAL=0x100001B`, feedback `0x00001B`), initial state
    `0x000001` = equation index 0. Step:
    `s' = ((s << 1) & 0xFFFFFF) ^ (0x1B if s & 0x800000 else 0)`.
    `coefficient(c)` = state after c steps. Materialize once as a uint32
    table of length `max_index` (~1 MiB single-stream, 3 MiB pooled),
    read-only.
16. Channel bit of equation index c: `parity(word_mask &
    coefficient(c))` = `(mask & coeff).bit_count() & 1`.
17. Tile counter is FLAT and page-global: `c = page*tiles_per_page +
    ty*tiles_x + tx`, `c < 2^18`. The equation uses the FULL counter,
    never the local tile index.
18. Equation index per family: single-stream rows (K, CMY7, CMY8 -v0)
    use `index = counter`, bound `MAX_COUNTER`. Pooled rows (CMY8 -v1,
    `pooled_fountain=True`) use `index = counter*n_streams + stream_idx`
    (stream_idx = position in `spec.stream_ids`), bound
    `n_streams * 2^18` (must stay < 2^24-1, so n <= 63). CMY8 -v0
    REPLICATES the counter's equation across its three streams
    (consistency copies, zero extra rank); -v1 carries three DISTINCT
    equations per tile. Every 24 consecutive indices are consecutive
    LFSR states => rank 24 (frozen property; s0=1 != 0).
19. Placement in the tile: the metadata bit is LDPC user bit 0 of each
    stream codeword; `user[0]=meta_bit`, `user[1:]=fountain symbol`
    (`symbol_bits = tile_user_bits - 1`). Decode extracts it the same
    way: certificate carries `metadata_bit = user[0]`, `symbol =
    user[1:]`.
20. Recovery (`decode_metadata(observations, max_index)`):
    a. Deduplicate by index; two certified bits that DISAGREE at one
       index => integrity failure, terminal (never voted).
    b. For each unique index in SORTED order build the 25-bit augmented
       row `coeff | (bit << 24)`; reduce into an echelon basis keyed by
       the LOWEST set bit (pivot = index of lowest set coefficient bit;
       XOR against existing basis rows until placed or zero). A row that
       cancels to zero with rhs 1 => algebraic inconsistency, terminal.
    c. rank = len(basis). If rank < 24: incomplete (report rank).
    d. Back-substitute pivots 23..0: `bit(pivot) = rhs(row) ^
       parity(coeffs(row) & solution_so_far)` (valid because each basis
       row's non-pivot bits are all HIGHER than its pivot).
    e. Content gates, in order: reserved bits M[19:24] all zero; K != 0;
       `n_unique >= 48` (the L9 trust floor — >= 24 surplus consistency
       equations under full-rank reception); version in {0}.
21. K semantics by family: K rows and CMY7 — word K field = k_total of
    the single fountain. CMY8 -v0 — the common per-stream k_total (all
    three streams pack with one K). CMY8 -v1 pooled — the field carries
    k_meta; receiver returns `k_total = n_streams * k_meta` (2026-08-14
    ruling: version stays 0; row identity precedes any read).
22. Fragment floors (measured/pinned, docs/CMY8-POOLED-FOUNTAIN.md §2.4):
    single-stream rows need 48 certified tiles; pooled rows reach the
    48-equation floor from ~16 healthy tiles (3 eq/tile); with one dead
    plane ~24 tiles — puncturing every third index breaks the
    consecutive-rank guarantee, so the floor is measured, not derived.

## 3. Copy-vs-rewrite table

COPY-AND-STRIP (bit-exact format law; strip validation/docstrings only,
never touch arithmetic). All from `src/holo` (the authority):

| what | source | disposition |
|------|--------|-------------|
| kdf | src/holo/core/keystream.py:127-131 | copy |
| counters (BE packing) | keystream.py:134-166 | copy; see §8 Q1 on range checks |
| blocks (ECB-as-CTR, chunked) | keystream.py:169-198 | copy |
| bits (MSB of byte 0) | keystream.py:201-218 | copy |
| keys64 | keystream.py:221-226 | copy |
| payload_bits (stripe gen) | keystream.py:229-245 | copy |
| fountain_rows_bits (packed) | keystream.py:248-263 | copy |
| _item_permutation (lexsort tie-break) | keystream.py:266-280 | copy |
| colour perms/dithers (dom 9-13) | keystream.py:283-345 | copy; drop type guards |
| color_fountain_rows_bits / block_assign | keystream.py:348-374 | copy |
| bounded_draws (rejection rule) | keystream.py:377-399 | copy; §8 Q2 on cap |
| slot_perm_params (16-bit scan, gcd) | keystream.py:402-444 | copy; §8 Q2 |
| metadata constants + _lfsr_step | src/holo/format/metadata.py:48-68 | copy |
| equation_index arithmetic | metadata.py:91-132 | rewrite lean (one line: c*n+s); keep bound n*2^18 < 2^24-1 |
| _coefficient_table | metadata.py:135-147 | copy |
| coefficient mask lookup | metadata.py:162-178 | rewrite lean (table[idx]) |
| _solve_word back-substitution | metadata.py:257-266 | copy |
| decode_metadata elimination core | metadata.py:307-356 | copy loop bodies; strip observation type-validation (307-327) |
| word content extraction (version/K/reserved) | metadata.py:269-291 | rewrite lean; keep gate ORDER |
| scramble-at-absolute-cells + LLR descramble | src/holo/receive/tiles.py:193-254 | copy arithmetic (`&~site_mask`, `x*(1-2*scr)`, site:=0.0); rewrite caching |
| observation mapping + pooled k | src/holo/receive/fountain_close.py:163-185,218-223 | rewrite lean; keep pooled/-v0 selection exactly (mirror of gen color_compose.py:112-135) |
| meta bit = user[0], symbol = user[1:] | src/holo/receive/records.py:182-201 | rewrite lean |

REWRITE LEAN (semantics kept, code fresh): metadata state holder + dirty
flag; certificate -> observation adapter; diag event emission.

## 4. Measured-channel / doctrine invariants that MUST survive

- Certified equations are never out-voted: any disagreement (duplicate
  index, opposite bit, or algebraic inconsistency) is terminal — a CRC-32
  certificate makes conflict a 2^-32-class event = mixed sheets or an
  upstream fault, not noise (HOLO-DESIGN §6.3).
- 48-distinct-equation trust floor before believing K (L9) — rank 24
  alone can be reached by a small consistent-but-wrong set; the >= 24
  surplus equations are the integrity margin.
- Receiver accepts metadata version 0 ONLY — a structurally valid future
  version through today's decoder would silently reinterpret data.
- Wrong-geometry hypotheses descramble to coin flips and refuse at the
  word gate — the row seed carries geometry; this is WHY format id = seed
  and why there is no separate label layer.
- All randomness from the keystream module or render-extraction, never
  retyped/hand-rolled draws (012.3 phantom-payload incident: one missing
  dtype forked the numpy stream; v1 keystream therefore has NO numpy RNG).
- One byte-order doctrine everywhere (§13.12 — goldens were re-frozen
  once over this; any LSB-first spelling is a format fork).
- Site cells are excluded from scramble AND forced to exact 0.0 erasure
  in the descrambled LLRs — gen/receive mask consistency is what the
  qualification pin (re-encoded printed cells == gen page slice) rests on.
- Dead-plane pooled floor ~24 tiles is a verified pin — do not "improve"
  it back to 16 by reasoning from the healthy case.

## 5. DROP (aggressive)

- ALL input validation: isinstance/TypeError/ValueError walls in both
  modules (metadata.py's _counter/_word_bits/_word_mask guard cascade,
  keystream's n_cols/size/stream type checks, CertifiedStreamSymbol
  __post_init__, _validate_close_certificate, validate_certificate_record,
  attempt/certificate identity hashing — sha256_parts_le/be,
  attempt_identity, dependency_identity, content-addressed
  TileCertificateRecord and its little-endian packbits serialization).
  holo3 certificates are in-memory frozen dataclasses.
- MetadataDecode's diagnostics dressing: reason strings, state-machine
  strings ("incomplete"/"malformed"/"unsupported"/"ready"),
  supported_versions echo, by-stream cert counts, rank_shortfall/
  check_shortfall properties. Keep: version, k, ok, rank, n_unique,
  inconsistent.
- `metadata_progress` / CloseProgress §10.4 observer projection
  (src/holo/receive/fountain_close.py:226-300) — deferred-close
  scaffolding; the frontier loop consults the plain decode.
- holo2's incremental metadata eliminator
  (holo2/src/holo2/solve/close.py:161-216ff) — a pull-model consult
  optimization. holo3: full `decode_metadata` re-run when the equation
  set grew since last consult (echelon over <= ~5.6k 25-bit rows is
  microseconds).
- `functools.cache`/`lru_cache` decorators as carried: the per-tile
  scramble cache (tiles.py:192) and slot-perm cache are unbounded shared
  mutable state — see §6 threading note; recompute or per-worker cache.
- The retry>64 "rejection runaway" raises in bounded_draws /
  slot_perm_params (guards per charter; P(16 rejects)^64 is
  astronomically unreachable) — pending §8 Q2.
- Encode side of metadata (`encode_metadata`, `tile_bit`, `tile_bits`) —
  holo3 is decode-only; re-encode of printed cells consumes the RECOVERED
  user bits (metadata bit already inside), never the word. Keep the
  encode functions only in `_distill/verify/` oracles.
- keystream `__all__` exports, MappingProxyType ceremony, docstrings.

## 6. Data-structure needs (holo3/data.py)

- `Certificate` (frozen): `counter:int, page:int, ty:int, tx:int,
  stream_id:str` ("main"|"C"|"M"|"Y"), `symbol: np.ndarray` uint8
  `(symbol_bits,)`, `metadata_bit: int`, `source: str` (producing-plugin
  tag). Address redundancy (counter vs page/ty/tx) collapses to counter +
  derived; keep both only if plugins want them precomputed.
- `MetadataState` (single-writer reduction, owned by the merge thread):
  `equations: dict[int, int]` (equation_index -> bit), `dirty: bool`,
  cached result `(version, k_total, rank, n_unique, inconsistent)`.
  Merge op per new certificate: map to equation index (pooled: `c*n+s`),
  insert; opposite bit at an existing index => terminal integrity
  failure. Consult (main thread only): if dirty, run decode_metadata,
  cache, clear dirty. `k_total` stored family-adjusted (pooled:
  n_streams * k_meta) so the fountain consumer never sees k_meta.
- Spec fields consumed here: `seed: bytes`, `family_seed: bytes`,
  `plane: int` (K=3), `n_streams: int`, `pooled_fountain: bool`,
  `stream_ids: tuple[str,...]`, `tiles_yx`, `tiles_per_page`,
  `tile_user_bits`, `symbol_bits`, `n_sites`,
  `n_transmitted_slots = 4096 - n_sites`.
- Threading: every keystream function is pure (fresh Cipher encryptor per
  call — `cryptography` encryptor objects are NOT shareable across
  threads). The LFSR coefficient table is build-once immutable — build at
  engine start for the row's max_index, pass read-only. Per-tile scramble
  (4096 domain-1 bits) is recomputed inside each job or memoized in a
  per-worker dict — never a global functools.cache under free-threading.
  MetadataState is FACTS-merge only; decode runs on the main thread.
- Diag events: `metadata_update(rank, n_unique, k, inconsistent)` emitted
  on consult transitions (rows pane / close gate).

## 7. Pitfalls / incidents

- 012.3: ground truth via the gen module or extract-from-render, never
  retyped draws — a missing `dtype=` forked the numpy stream and produced
  a 50%-payload phantom with clean pilots. The addressed-AES design
  exists to make this class impossible; do not reintroduce sequential or
  numpy-RNG draws anywhere.
- §13.12 endianness harmonization: the format went through one deliberate
  golden re-freeze to purge LSB-first spellings. `np.packbits` default
  bitorder is correct; the ONE exception in the old code is the
  certificate-record serialization (`bitorder="little"`,
  records.py:222) — that is journal surface, dropped in holo3; do not
  copy it into anything format-facing.
- The word-mask packs M[i] at integer bit i (LSB-first) while K inside
  the word is big-endian across M[1..19] — conflating the two orders is
  the easiest silent metadata fork.
- Scramble addresses are ABSOLUTE page-cell coordinates (e016
  align_to_field bug class); tile-local scramble decodes sim tile (0,0)
  and nothing else.
- `slot_perm_params`: b must not reuse the word that produced a
  (`~take_a` in the vectorized form) — a scalar re-implementation that
  lets one word serve both forks every tile's permutation.
- CMY7 rides domains 10/11/14/15 at aux=0 ("main") — "bit-identical to
  n=1" for metadata means its path is untouched, not that it exercises
  the pooled arithmetic; only K rows use domains 7/8.
- CMY8 -v0 vs -v1: same tile codec, same seed spelling except the
  coding_id; the ONLY metadata differences are equation replication vs
  distinct indices and k_total vs k_meta in the word. Selecting by
  `pooled_fountain` (a family/row fact) — never by sniffing content.
  e030/e032 printed sheets are -v0 forever.
- `decode_metadata` processes ALL supplied equations before accepting a
  full-rank word — early-out at rank 24 skips the surplus consistency
  checks and silently weakens the integrity gate (holo2's incremental
  eliminator §settle preserved this; a lean rewrite can lose it).
- Metadata equations come ONLY from certificates (CRC-certified user
  bit 0). Never feed uncertified/soft bits into the eliminator.
- Counter address space: counters representable by BCH (< 2^18) can lie
  beyond `max_pages * tiles_per_page`; the address gate upstream rejects
  them — the metadata module itself only needs `index < max_index`.
- 64 GB budget: `blocks` chunking at 1<<20 counters is what keeps
  full-page keystream regeneration bounded; keep it.

## 8. Open questions for the contract author

1. `counters()` field-range checks: the original raises on out-of-range
   major/u/v ("a format bug, never silently wrapped"); the charter bans
   guards, but dropping them makes a buggy caller silently wrap into a
   VALID different stream. Keep this one check as format law, or trust
   call-site construction?
2. `bounded_draws`/`slot_perm_params` retry cap (>64 raise): drop per
   charter (unreachable), or keep as the one hang-preventing loop bound?
3. Confirm: no incremental metadata eliminator — full re-elimination on
   dirty consult is the holo3 shape (cost is negligible at sheet scale).
4. Certificate address redundancy in data.py: counter only (derive
   page/ty/tx via tiles_yx) or both precomputed?
5. Scramble memoization: per-worker dict, engine-precomputed per-page
   scramble planes (h_cells x w_cells bits, ~1 MB/page — cheap), or
   always recompute per job? (Affects detect/tiles plugin API, not
   format.)
6. Does the diag rows pane want per-stream metadata-equation counts on
   colour rows (the dropped `n_certificates_by_stream`), or is
   (rank, n_unique) enough?
7. plane_fields / color_field arms: no keystream API impact found — they
   consume poses/LLRs, not draws. Confirm the arms need no extra draw
   forms so the keystream surface can freeze at domains 1-15.
