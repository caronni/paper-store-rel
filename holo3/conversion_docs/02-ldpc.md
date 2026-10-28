# 02 — LDPC inner code (construction, decode, framing, certification)

Sources of record (all in this worktree): `src/holo/core/ldpc/{construct,decode,tile,frame}.py`,
`src/holo/core/color_tile.py`, `src/holo/core/ldpc/data/*.json` (six files),
`src/holo/receive/{tiles,payload,color_attempts}.py`, `src/holo/format/{profiles,descriptor,families}.py`.
`holo2/src/holo2/format/ldpc/{construct,decode,tile}.py` are byte-verbatim carries of the
src/holo modules (only docstrings differ; data files diff-identical) — copy from either, prefer src/holo.

## 1. Purpose + exact inputs/outputs

Purpose: the ONLY stage that mints payload certificates. Turns per-tile soft LLRs into
CRC-32-certified user bits, per logical stream. Everything upstream (survey/pose/detect/
calibrate) only produces LLRs; everything downstream (metadata, fountain, close) only
consumes certified user bits.

Inputs (per attempt, all immutable snapshots — a pure job):
- K family: `llr_cells (64,64) float64`, house convention (positive = bit 1,
  `0.0` = erasure, NaN/±inf = caller fault, rejected), at tile-local cell coordinates,
  slot-raster order (row-major over the 64x64 tile).
- CMY7 family: `relative_state_scores (payload_cells, 6) float64` (six W-relative
  state scores per sequential payload cell) + `observed_slots (payload_cells,) bool`.
- CMY8 family: `level_llrs (payload_cells,) float64` for ONE plane (binary
  presence LLR of that plane's ink, house convention), + observed mask.
- Format facts: `rate_id` (K) or per-stream FEC bank (list of `(code_id, shortened_info_tail)`
  children), `site_cells (n_sites,) int64` strictly increasing in `[0,4096)`,
  slot-permutation params `(a_t, b_t)` ints, payload scramble bits `(64,64) uint8` (K),
  interleave permutation + dither bits (CMY7), per-stream dither bits (CMY8) —
  all derived by the keystream subsystem from `(seed, counter/plane/page)`.
- Decode params: `max_iters` (60 baseline / 150 retry), `alpha = 0.8`.

Outputs:
- K: `(ok, user_bits (cap,) uint8 | None, n_iters, syndrome_ok, crc_ok)` where
  `cap = k_bits - 32 - n_sites`; `user_bits[0]` = the metadata bit, `user_bits[1:]` =
  fountain symbol bits.
- Colour: per-child `(n_iters, syndrome_ok)` tuple + `(crc_invoked, crc_ok, certified_user_bits | None)`
  for the bank; same `[meta_bit | symbol]` layout per stream.
- Encode side (needed by refine/GT re-encode): `user_bits -> (4096,) uint8` tile cells (K),
  `user_bits -> sequential state slots` (colour).

## 2. Algorithm

### 2.1 Mother codes — data IS the format, expansion is fixed

Six frozen e-IRA QC-LDPC codes, n = `N_BITS = 4096`, `Z = 64`, `gap_min = 24`:

| rate_id | k_bits | m_bits | heavy_deg | kb | mb |
|---------|--------|--------|-----------|----|----|
| r0547   | 2240   | 1856   | 10        | 35 | 29 |
| r0550   | 2240   | 1856   | 10        | 35 | 29 |
| r0625   | 2560   | 1536   | 10        | 40 | 24 |
| r0700   | 2880   | 1216   | 10        | 45 | 19 |
| r0775   | 3200   |  896   |  8        | 50 | 14 |
| r0850   | 3520   |  576   |  6        | 55 |  9 |

r0547 and r0550 share k=2240 but are DISTINCT codes (independent construction draws).
The construction (seeded restart draws, acceptance rules (a)-(d), Fisher-Yates Pi — normative
record: `src/paperholo/ldpc.py` docstring) is NEVER re-run. The six winning draws live as
transparent JSON block descriptions in `src/holo/core/ldpc/data/<rate_id>.json` with fields:
`rate_id, n_bits, z, k_bits, gap_min, heavy_deg, restart, pi (m,), heavy_rows/heavy_shifts
(nh, heavy_deg), light_rows/light_shifts (kb-nh, 3), comment`. holo3 copies these six files
BYTE-IDENTICALLY (shas: r0547 d1439d31…, r0550 aaa7bce5…, r0625 b05aa66f…, r0700 e5a774af…,
r0775 a1260e98…, r0850 3f9fa520… — full values in holo2 `construct.py:8-25`).

Expansion (JSON -> bit-level edges), exact:
1. Circulant convention: `I(s)[a,b] = 1 iff b == (a+s) mod Z`.
2. For each info block-column c (heavy columns FIRST, then light), for each of its
   `(r, s)` pairs: edges `(chk = pi[r*Z + a], var = j*Z + (a+s) mod Z)` for
   `a = 0..Z-1`, `j` = running block-column index. Heavy columns first is
   load-bearing: payload fills info positions from the front, shortening eats the tail,
   so payload sits on the best-protected variables.
3. Accumulator H_a, bit-level dual diagonal: parity bit j (var `k+j`) in check j for
   all j in `[0,m)`, and parity bit j-1 (var `k+j-1`) in check j for j in `[1,m)`.
4. Lexsort edges by `(chk, var)` — this order IS the decode order.
5. Derived structures: `chk_starts (m,) int64` reduceat starts; `var_order (E,) int64`
   = stable argsort by var; `var_starts (n,) int64`; encode side: info edges
   (`var < k`) stably sorted by row -> `enc_info_col`, `enc_rows`, `enc_row_starts`.

Format pin (build-time verification, NOT runtime): sha256 over
`edge_chk.astype('<i4').tobytes() + edge_var.astype('<i4').tobytes()`:
r0547 `4cf6774a…6f4c9371`, r0550 `54c72b39…14ef477e`, r0625 `e98e6515…f059fb71`,
r0700 `b1ef32ed…5c3e5913`, r0775 `8b0ec36d…7eff0712`, r0850 `4be74ca9…22da33c7`
(full 64-hex values: `tests/holo/test_holo_ldpc.py:43-57`). Bump-don't-edit; a mismatch
is a format fork. NEVER store the pin next to the data (a self-stored hash guards nothing).

### 2.2 Encode (systematic)

`codeword = [info u (k,) | parity p (m,)]`. `s[enc_rows] = XOR-reduceat(info[enc_info_col],
enc_row_starts)`; `p = bitwise_xor.accumulate(s)` (the 1/(1+D) accumulator as one cumulative
XOR). Returns `(4096,) uint8`.

### 2.3 BP decode (the hybrid schedule)

Constants: `LLR_CLIP = 20.0`, `LLR_KNOWN = 1e9`, default `max_iters = 60`, `alpha = 0.8`.
House LLR convention: positive = bit 1, `llr = log P(1)/P(0)`, `0.0` = erasure
(first-class, propagates natively), ±inf = known bit.

1. `L = clip(llr, -20, +20)`; then positions where input was ±inf get ±`1e9`
   (finite stand-in — no inf−inf NaNs). Negate: internal convention positive = bit 0.
2. Pass 1: flooding normalized min-sum over the edge arrays, `alpha = 0.8`.
   Per iteration: hard = `(Ltot < 0)`; syndrome = XOR-reduceat over checks; EARLY EXIT
   on zero syndrome (n_iters counts completed update iterations; 0 if channel hard
   decisions already satisfy H). Check update: `v2c = Ltot[var] − c2v`; parity sign from
   count of negative v2c per check; extrinsic magnitude = min1, except at the (first)
   min-position where it is min2; `c2v = alpha * par_sign * sgn * ext`.
   Variable update: `Ltot = L + add-reduceat(c2v[var_order], var_starts)`.
3. On syndrome failure and `max_iters > 0`: ONE exact sum-product retry from the SAME
   channel LLRs (not the min-sum posterior). Tanh rule in log domain with exactly these
   clips: `tanh(clip(v2c, ±40)/2)`, `log(clip(t, 1e-300, 1.0))`,
   `exp(clip(lsum − lt, −700, −1e-16))`, `arctanh(clip(·, ±0.999999999999))`.
   Rationale (measured, exp 013 gate): at r0700 BSC p=0.035 (500 trials) min-sum alone
   4.0% BLER, sum-product 1.6% — min-sum is the fast path, sum-product the accuracy net.
4. Return `(syndrome_ok, hard (n,) uint8, n_iters_total_both_passes, extrinsic)`.
   Extrinsic = `posterior − CLIPPED channel` in house convention (the caller must not
   subtract its own unclipped LLR); exactly zero wherever BP never ran.
   `syndrome_ok` certifies `H@c == 0` ONLY — never payload.

### 2.4 K tile framing (v1 format law)

`TILE_CELLS = 64`, `N_CELLS = 4096`, `CRC_BITS = 32`. v1 invariant: mother-code n == tile
slot count, so transmitted count T = `4096 − n_sites` for every rung.

- `crc32_bits(bits)`: `zlib.crc32` over `np.packbits(bits)` (MSB-first, last byte
  zero-padded), emitted as 32 bits MSB-first big-endian.
- `tile_capacity = k_bits − 32 − n_sites`.
- `transmitted_positions = [0, k−n_sites) ++ [k, n)` ascending — shortening consumes the
  INFO TAIL only; parity is ALWAYS transmitted (no degenerate tiles).
- `cell_map(site_cells, a_t, b_t)`: `nonsite = sorted complement of site_cells in [0,4096)`;
  transmitted bit j lives at slot-raster cell `nonsite[(a_t*j + b_t) mod T]`.
  Requires `0 < a_t < T`, `0 <= b_t < T`, `gcd(a_t, T) == 1`. `(a_t, b_t)` come from
  `keystream.slot_perm_params(spec.seed, counter, T)` (keystream subsystem).
- `encode_tile`: `info = [user (cap,) | crc32_bits(user) | zeros(n_sites)]`, systematic
  encode, scatter `cw[transmitted_positions[j]] -> cells[cell_map[j]]`, site cells stay 0.
- `decode_tile`: `llr_code = zeros(4096)`; `llr_code[transmitted_positions] =
  llr_cells[cell_map]`; `llr_code[k−n_sites : k] = −inf` (known 0); decode; then
  `user = hard[:cap]`, `crc_ok = (hard[cap:cap+32] == crc32_bits(user))`;
  `ok = syndrome_ok AND crc_ok`. NEVER return user bits unless ok.

### 2.5 K attempt chain (receive side, `tiles.py`/`payload.py`)

Constants: `BASELINE_BP_MAX_ITERS = 60`, `RETRY_BP_MAX_ITERS = 150`, `BP_ALPHA = 0.8`.

1. Input `(64,64)` LLRs must be FINITE; NaN/inf is a detector/API fault, raise —
   erasure is spelled `0.0` and nothing else (an accepted inf once turned an entry
   excluded by the attempt floor into a maximum-strength decoder input).
2. Attempt floor (counting bound): `n_informative = count(llr != 0 on non-site cells)`;
   if `< k_eff_bits = k_bits − n_sites` return BELOW_FLOOR without decoding — fewer
   informative observations than unknowns cannot determine the codeword under ANY decoder.
3. Descramble: `llr *= (1 − 2*scramble_bits)` where scramble =
   `keystream.bits(seed, DOMAIN_PAYLOAD, plane, page, abs_y, abs_x)` at ABSOLUTE cell
   coordinates with site cells masked to 0; then re-zero site cells.
4. `decode_tile(llr.ravel(), rate_id, site_flat, a_t, b_t, max_iters, alpha=0.8)`.
5. On ok: mint certificate from `user_bits` (see 2.9). Record `n_iters, syndrome_ok, crc_ok`
   for accounting either way.

### 2.6 Colour framing — shortened bank + one outer CRC (`frame.py`)

A bank = ordered children `(code_id, shortened_info_tail)`; child transmitted positions =
`[0, k−s) ++ [k, n)`; bank transmitted bits = concatenation in child order. ONE CRC-32
across the concatenated active-information prefixes: `frame = [user (bank.user_bits,) |
crc32_bits(user)]`, split across children's active info in order, zero-fill tails, encode
each child. `bank.user_bits = sum(active_info) − 32`.

decode_frame:
1. Per child in order: scatter its slice of code LLRs to mother positions, pin
   `[active : k] = −inf`, `decode_soft(..., max_iters, alpha)`.
2. If ANY child syndrome fails: `crc_invoked = False`, `crc_ok = None`, no user bits
   (the CRC was provably not consulted this pass).
3. Else concatenate `hard[:active]` per child; `crc_ok` gates the last 32 bits;
   `certified_user_bits = frame[:−32]` iff crc_ok. `ok == bool(crc_ok)`.
4. `want_extrinsic=True` additionally returns the children's extrinsic gathered at
   transmitted positions, concatenated in code order — decode numerics bit-identical
   either way. The extrinsic never leaves the attempt (2.7).

### 2.7 CMY7 iterated demap-decode (`color_tile.py` + `color_attempts.py`)

Pack law: `CMY7_CELLS_PER_PACK = 4`, `CMY7_BITS_PER_PACK = 11` (2048 candidates over
7^4 = 2401 state tuples; codebook in `channel.py` — the detect/mapper spec). Payload cells
= 3976 -> 994 packs -> `n_code = 10934`.

1. Structural gate (cheap, before the expensive demapper): a pack is usable iff ALL 4
   slots observed; scatter `repeat(complete, 11)` through the INVERSE interleave
   (`code_support[interleave] = mapped_support`); every child must have
   `count(support) >= child.active_information_bits` — active tuple `(2240, 1883, 1883)`
   for the baked `cmy7-p120-v0` bank `(r0550, 0), (r0625, 677), (r0625, 677)`.
2. Demap once: `cmy7_demap_payload(scores, observed, bank, interleave, dither)` — incomplete
   packs emit exactly 0.0 for all 11 bits (an eleven-bit erasure); dither applied as sign
   flips `(1−2*dither)` around the soft demap; inverse interleave scatters back to code
   order. Re-gate: per-child nonzero-LLR count `>= active_information_bits`.
3. `cmy7_iterated_decode(code_llrs, …, max_iters, alpha=0.8, demap_iterations=3)`:
   decode_frame with `want_extrinsic = (demap_iterations > 1)`; then up to 2 more rounds:
   stop as soon as `ok`; `prior = clip(extrinsic, −LLR_CLIP, +LLR_CLIP)` (= ±20); re-demap
   with the prior folded into the pack metric and REMOVED again (the return stays
   extrinsic/channel-only; erased packs still exactly 0.0); decode_frame again.
   Per-child `n_iters` are SUMMED over all inner decodes; the returned outcome carries
   no soft output. `DEMAP_ITERATIONS = 3` is part of the decoder identity.
   At `demap_iterations == 1` this is byte-for-byte `decode_frame(code_llrs, …)`.
4. The demap<->BP loop is soft iteration INSIDE one attempt (RECEIVE-DESIGN 6.2a): no
   state escapes it, one certificate at most. It may invoke the frame CRC up to 3 times
   per attempt — a registered undetected-error-budget compromise
   (COLOR-UPLIFT-MEASUREMENTS §13.8), guarded empirically by the wrong-certificate audit.

### 2.8 CMY8 per-stream decode

Each plane C/M/Y is an independent binary stream: own bank (one child), own dither
(`keystream.cmy8_dither_bits(seed, stream_id, counter, n_code)`), own metadata bit and
fountain stream. Floor: `count(observed AND llr != 0) >= active_information_bits`.
Decode: `undithered = llrs * (1 − 2*dither)`; `decode_frame(undithered, bank, max_iters,
alpha=0.8)`. A certified sibling is never re-attempted (schedule per unresolved stream).
Dead plane degrades gracefully — this codec asymmetry (per-plane fallback vs cmy7's joint
pack) is the e032 ordering-inversion hypothesis; it is why CMY8 closed where CMY7 failed.

### 2.9 Certification — zero-wrong semantics

A tile certificate = `(page, tile_yx, stream_id, packed user_bits)`, content-addressed
(identity binds spec_id/seed + address + stream + bits; pack with
`np.packbits(bitorder="little")`), tagged with the producing plugin (source tag).
What certifies: K = child syndrome AND CRC-32; colour = ALL children's syndromes AND the
bank CRC-32. Undetected-error budget ~2^-32 per CRC invocation. Measured record backing
"zero-wrong": 0 wrong in 69,066,304 audited cells (colour-uplift campaign), 0 wrong in
850,177 GT-audited cells (e018 repass). CONFLICT LAW: two DIFFERENT certified values at
one `(address, stream)` is not a noise event — it is mixed sheets or an upstream fault;
FATAL by doctrine (HOLO-DESIGN §6.3), never resolved by voting. Check at merge time.
Re-encode service (refine/GT consumers): certified user bits -> printed tile
`encode_tile(...)` + word/filler overlay + scramble XOR — pure function of the
certificate identity, cache at most once.

### 2.10 Per-coding matrix/bank selection

The LDPC layer takes `rate_id` or a bank as INPUT; it never parses coding ids. The format
subsystem resolves:
- K codings: scalar `rate_id`; bank = one child `(rate_id, shortened = n_sites)`.
  `n_sites = 100 + n_filler` (K rows: n_filler = 0 -> 100).
- `cmy7-*-p120-v0`: baked bank `(r0550,0),(r0625,677),(r0625,677)`, n_sites 120 (20 dust).
- `cmy8-*-p120-v0/v1`: per-plane banks C=`(r0550,120)`, M=`(r0550,120)`, Y=`(r0547,120)`.
- v2 lattice / fossils: K and CMY8 banks are DERIVED — shortening = site count p; cmy8
  takes a rung triplet with equal k_bits (gen-v1 one-symbol-width law). Sheet I's fossil
  `L:c2-cmy8-r0700-p120-x1@3392x2368` uses `(r0700,120)` on all three planes:
  active 2760, user 2728, symbol 2727.

Arithmetic table (bit widths a builder can check against):

| coding class | T tx bits | active info | user bits | symbol bits | k_eff floor |
|---|---|---|---|---|---|
| K r0550 p100 | 3996 | 2140 | 2108 | 2107 | 2140 |
| K r0700 p100 | 3996 | 2780 | 2748 | 2747 | 2780 |
| cmy7 p120 (bank) | 10934 | 2240+1883+1883 | 5974 | 5973 | per child |
| cmy8 p120 r0550/r0547 (per stream) | 3976 | 2120 | 2088 | 2087 | 2120 |
| cmy8 p120 r0700 fossil (per stream) | 3976 | 2760 | 2728 | 2727 | 2760 |

### 2.11 Scheduling function (for the frontier loop; describes ORDER, not machinery)

Baseline attempt: first time a tile view reaches the informative floor (per stream).
Union attempt: when a new capture's evidence joins an unresolved tile. Retry tier: after
the ordinary tiers reach fixed point AND a cheap pre-close says the volume cannot close
yet — for each `(address, stream)` whose LATEST ordinary attempt failed (decoded but
syndrome/CRC failed, not below-floor) and holds no certificate, run EXACTLY ONE retry at
`max_iters = 150` over the SAME evidence snapshot (never tunnel past baseline evidence).
Tried-set floor: an attempt over an identical evidence set + identical decoder params is
never re-run; new evidence or the 60->150 bump is what re-arms a tile. Certified tiles
leave the frontier permanently (a certified sibling stream stays schedulable).

## 3. Copy-vs-rewrite table

COPY-AND-STRIP = keep numerics token-for-token, delete docstrings/comments/validation.

| What | Source | Verdict |
|---|---|---|
| six data JSONs | `src/holo/core/ldpc/data/*.json` | COPY BYTE-IDENTICAL (they ARE the format) |
| `_expand_edges` | `construct.py:100-126` | COPY-AND-STRIP (edge order = format law) |
| `load_code` derived-structure block (lexsort, starts, enc arrays) | `construct.py:181-209` | COPY-AND-STRIP; drop all structural validation (verify once in `_distill/verify` vs golden digests) |
| `LADDER` table | `construct.py:69-76` | COPY values; plain dict, drop MappingProxyType + `__post_init__` |
| `encode` | `decode.py:29-46` | COPY-AND-STRIP |
| `_bp_loop` | `decode.py:49-100` | COPY-AND-STRIP — hard-won numerics incl. every clip constant |
| `_run` clip/negate/hybrid retry | `decode.py:103-123` | COPY-AND-STRIP |
| `decode`/`decode_soft` | `decode.py:126-156` | fold into one function returning extrinsic always |
| `crc32_bits` | `tile.py:40-46` | COPY-AND-STRIP (format law) |
| `tile_capacity`/`transmitted_positions`/`cell_map` | `tile.py:49-96` | COPY-AND-STRIP; keep the gcd bijectivity check OUT (params come from keystream, correct by construction) |
| `encode_tile`/`decode_tile` | `tile.py:99-165` | COPY-AND-STRIP |
| bank transmitted_positions/encode_frame/decode_frame | `frame.py:89-259` | COPY-AND-STRIP; replace dataclass outcomes with plain tuples; drop `_binary_vector` and all input validation |
| `cmy7_encode_payload`/`cmy7_demap_payload`/`cmy7_iterated_decode` | `color_tile.py:68-217` | COPY-AND-STRIP (the prior fold/remove and erased-pack re-zero are load-bearing) |
| `cmy8_encode_payload`/`cmy8_decode_stream` | `color_tile.py:265-338` | COPY-AND-STRIP |
| K attempt chain (floor, descramble, decode call) | `receive/tiles.py:180-330`, `receive/payload.py:360-415` | REWRITE LEAN (keep constants 60/150/0.8, k_eff floor, finite-input law, `user[0]`=meta) |
| colour attempt gates | `receive/color_attempts.py:200-330` | REWRITE LEAN (keep both CMY7 gates + the demap-once-then-re-gate order) |
| re-encode printed cells | `receive/tiles.py:295-317` | REWRITE LEAN (compose from copied kernels) |
| bank/profile tables | `format/profiles.py:154-263` | COPY the numbers into holo3/format; drop validation + `_validate_frozen_profiles` (verify in `_distill/verify`) |
| construction/regeneration | `util/regen_holo_ldpc_data.py`, `src/paperholo/ldpc.py` | DO NOT PORT — the bridge stays in the main repo |

## 4. Measured-channel invariants that MUST survive

- BOUNDED LLR (018.7): every LLR crossing an API boundary is calibrated or bounded —
  uncalibrated ctx-GMM scores reach ~5e5 vs calibrated ≤ ln(n+1) ≈ 6.8, and the failure
  SELF-SELECTS (drifted windows lose calibration labels and shout loudest), poisoning the
  multi-capture union; fix measured +9 symbols, |LLR| max 692,895 -> 22.9.
- Decoder input clip ±20 / ±inf -> ±1e9: keeps one confidently-wrong cell from being
  unrecoverable by BP and kills inf−inf NaNs.
- Erasure is exactly 0.0; NaN/inf rejected at the tile boundary: an accepted inf once
  converted a floor-excluded entry into a maximum-strength input (fast pin
  `test_detect_unit`-era lesson recorded in `_as_tile_llrs`).
- Hybrid min-sum -> ONE sum-product retry, alpha 0.8, from CHANNEL LLRs: measured 4.0% vs
  1.6% BLER at the r0700 p=0.035 gate — dropping the retry costs real tiles; retrying from
  the min-sum posterior is a different (unmeasured) decoder.
- Early exit on zero syndrome: n_iters=0 fast path carries the whole clean-sim regime.
- 60 baseline / 150 retry iterations: the retry150 tier converts real marginal tiles
  (e029/e032 corpus); one retry per (address, stream) per evidence set — unbounded
  re-decode buys nothing (BP is deterministic).
- k_eff attempt floor: counting bound, not policy — below it no decoder can determine the
  codeword; skipping it wastes the BP budget on impossible tiles.
- Certification = syndrome AND CRC, colour = ALL children AND bank CRC; user bits never
  escape uncertified — the zero-wrong record (0/69M cells) rests on exactly this gate.
- Extrinsic never crosses an attempt boundary; prior clipped to ±20 (RECEIVE-DESIGN 6.2a):
  keeps attempts pure/reproducible and the CRC-exposure budget accountable.
- Demap loop stop-on-ok + summed n_iters + fixed DEMAP_ITERATIONS=3: the campaign's
  measured cmy7 wins (xerox c2-cmy7 686,859 B close) ran exactly this loop.
- Shortened tail pinned −inf (known 0), parity always transmitted: format law; getting the
  tail wrong silently halves the code's strength on every tile.
- Descramble BEFORE decode at absolute cell coordinates, site cells zeroed: the scramble is
  format law; sign-flip on LLRs (not bit XOR) preserves soft information.

## 5. What to DROP (aggressively)

- ALL runtime validation: `load_code` structural checks (pi permutation, shape/range,
  degree-1/unused-var), `LdpcSpec.__post_init__`, `_validated_site_cells`,
  `_binary_vector`, `_bits`, `_permutation`, `_cmy8_banks` checks, `frame.py` NaN/type
  guards, `FecChildProfile/FecBankProfile.__post_init__`, `_validate_frozen_profiles`.
  Replace with one `_distill/verify` script pinning edge digests + width arithmetic.
- `data_dir` test seam and cache-bypass logic in `load_code`; MappingProxyType; the
  module-global `_CODE_CACHE` dict (see §6 — preload instead).
- Attempt records/ledgers: `TileAttemptRecord`, `AttemptState/AttemptStage` enums,
  `stream_attempt_identity`, durable attempt ids, `decoder_profile`, source_sha256/lane_id
  plumbing, component_block_ids/dependency_certificate_ids threading — holo3 keeps only
  per-plugin counters (attempts, certs, n_iters, cpu-seconds) and the tried-set key.
- `effective_demap_iterations()` env hatch / force-null contract: hardcode 3.
- `ChildDecodeOutcome`/`FrameDecodeOutcome`/`TileFraming` dataclasses -> plain tuples.
- `cmy7_decode_payload` and `cmy8_decode_payload` convenience wrappers.
- `CertificateConflict` class hierarchy — keep the comparison + fatal raise at merge, one line.
- `_PRINTED_CELLS_CACHE` mint-once machinery — recompute on demand or one plain dict in the
  single-writer merge thread.
- Everything journal/resume/replay, holo2 dispatch markers, pull-model wake plumbing,
  observer callbacks (`retry_open`), advisory pre-close bookkeeping beyond one boolean.
- The regen bridge, paperholo construction code, restart draws, RNG — holo3 never
  constructs a code.
- holo2's `solve/tiles.py` variants — same constants, nothing extra to take.

## 6. Data-structure needs for holo3/data.py

Consumes:
- `TileView` (per attempt, immutable): address `(page, ty, tx)` + counter, `stream_id`,
  family tag, LLR payload — K: `(64,64) float64`; CMY7: `(3976, 6) float64` scores +
  `(3976,) bool` observed; CMY8: `(3976,) float64` per plane (plane-native: one view per
  unresolved plane) — plus the evidence-set key (capture ids + detector params) for the
  tried-set.
- Format snapshot: per-stream bank tuple `((code_id, shorten), …)`, `rate_id` (K),
  `n_sites`, `site_flat (n_sites,) int64`, seed; keystream products precomputed per tile:
  `(a_t, b_t)`, scramble `(64,64) uint8` (K), interleave `(10934,) int64` + dither
  `(10934,) uint8` (CMY7), dither `(3976,) uint8` per plane (CMY8).

Produces (FACTS, merged single-writer):
- `Certificate`: `page:int, tile_yx:(int,int), stream_id:str, user_bits:bytes`
  (little-bitorder packed), `n_user_bits:int`, `source:str` (producing plugin tag).
  Metadata bit = bit 0 of the unpacked user bits.
- `TileRecord` (accounting/diag): address, stream_id, outcome enum
  {certified, failed, below_floor}, `n_iters:int`, `syndrome_ok:bool|None`,
  `crc_ok:bool|None`, tier {baseline, union, retry150}.

Stateful/shared — make snapshots or reductions:
- Code table: preload ALL needed rungs at startup into an immutable dict
  `{rate_id: Code}` (frozen arrays, read-only) BEFORE workers start — no lazy cache under
  free-threading. `Code` arrays should be read-only views.
- Keystream per-tile products: pure functions of (seed, counter) — compute inside the job
  or precompute per page; no shared memo dict.
- Certificate map + conflict check: single-writer merge only.

## 7. Pitfalls/incidents

- 018.7 LLR honesty bug (the founding incident of §4's first invariant): clipping at the
  decoder HIDES the symptom; the fix is calibration-side honesty (PAVA's 1/(n+2) clamp,
  `clamp_for(n) = log(n+1)`; downstream clamps `CTX_LLR_CLAMP = 12.0`,
  `DEGENERATE_LLR_CLIP = 2.0` colour). The decoder's ±20 clip is a backstop, not the fix.
- Truth-path trap (018.7, hours lost): the slot raster is NOT codeword order — GT/forensic
  tooling must pair `cell_map` with `transmitted_positions`, and any truth path must first
  validate on CERTIFIED tiles (expect ~4% raw BER, not ~50%).
- Extrinsic definition trap: `_run` returns extrinsic w.r.t. the CLIPPED channel input;
  a caller subtracting its own unclipped LLR double-counts up to the clip differences.
- e012 dtype fork: every JSON expansion array is explicitly `int64`; a missing dtype in
  any seeded/derived integer path forks a stream. Never retype constants from prose —
  copy the code.
- Self-stored hashes guard nothing (2026-07-19 review): the JSON `comment` mentions its
  own provenance but the pin lives externally; keep it that way in `_distill/verify`.
- e032 ordering inversion: discovery/channel tiers do not predict receiver outcomes even
  in ORDER (cmy7 ranked better, failed; cmy8 closed). Never gate bank selection on
  channel-ladder numbers.
- CRC exposure compromise: 3 CRC invocations/attempt for cmy7 (§13.8) — do not "improve"
  by iterating more without reopening the undetected-error budget.
- r0547 vs r0550: same k, different codes. A builder who dedups by k_bits forks the
  Y-stream of every cmy8-v0 sheet.
- Site cells are slot-raster indices in `[0,4096)` INSIDE the tile; scramble/filler use
  ABSOLUTE page cell coordinates. Mixing the two frames decodes nothing, plausibly.
- Alpha and max_iters were part of durable attempt identity in src/holo (ruling 3.4/§13a);
  holo3 drops the identity machinery but MUST keep the values pinned (0.8, 60/150) —
  they are part of the measured closes.

## 8. Open questions for the contract author

1. Data file home: `holo3/format/ldpc_data/*.json` proposed. Carry all six rungs, or only
   the four the acceptance corpus touches (r0547/r0550/r0625/r0700)? Recommend all six
   (ladder parity, ~trivial bytes).
2. Retry150 as a frontier cost tier: confirm retry is spelled as a higher-cost tier of the
   same tile job keyed by (evidence-set, max_iters), not a separate pass — and that the
   pre-close short-circuit (skip retries when the fountain already closes) is kept.
3. decode API shape: one `decode(llr, code, max_iters, alpha) -> (ok, hard, n_iters,
   extrinsic)` (extrinsic always computed — it is nearly free) vs the two-function split.
   Recommend one function.
4. Does any ARM need decoder soft output across the plugin API (plane_fields/color_field
   are dial-off arms; the colour closes predate them)? If yes, the extrinsic must still
   die at the attempt boundary — spell the arm API as "re-attempt with new LLRs", never
   "continue from posterior".
5. Certificate `source` tag granularity: plugin name only, or plugin+tier
   (e.g. `tiles/retry150`)? Diag panes historically wanted the tier split.
6. Conflict policy under threads: merge-thread fatal raise on differing packed bits at one
   (address, stream) — confirm abort-the-run (holo1 doctrine) vs refuse-the-tile.
7. Metadata bit: confirm the metadata plugin consumes `user_bits[0]` from certificates
   (per stream for cmy8) and the fountain consumes `user_bits[1:]` — i.e. certificates
   carry the FULL user frame, undissected.
8. `n_informative` for CMY7 is the physical observed-cell count while the gate uses
   pack-structural support — keep both numbers in TileRecord or just the gate verdict?
