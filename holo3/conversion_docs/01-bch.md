# 01 — BCH kernel + address words (functional spec for holo3)

Sources read end-to-end:
- `src/holo/core/bch.py` (393 lines) — the scalar codec, format law.
- `holo2/src/holo2/format/bch.py` — VERIFIED character-identical executable
  body to src/holo (diff of both bodies: identical). Either is the copy source.
- `holo2/src/holo2/format/bch_batch.py` — the vectorized batch path (holo2
  only; src/holo has no equivalent).
- `src/holo/format/pilots.py` (colour authority, has the colour word surface)
  vs `holo2/src/holo2/format/pilots.py` (K-only carry).
- Word-sweep callers: `src/holo/receive/words.py`,
  `holo2/src/holo2/solve/words.py`; gate constants
  `src/holo/receive/placement/model.py`; `docs/FULL-DOMAIN-RIVAL-ANALYSIS.md`.

## 1. Purpose + inputs/outputs

Purpose: the pilot address-word code. Every 64x64-cell tile prints one
BCH(127,50,t=13) codeword shortened to (100,23) at 100 fixed in-tile sites;
the 23-bit message is an 18-bit flat tile counter + 5 known-zero pads. The
kernel (a) encodes counters to 100-bit printed-site values, (b) decodes
sampled hard bits back to counters (errors-only t=13, or errors+erasures at
known positions), (c) provides the vectorized batch decode that IS the cold
placement sweep's hot kernel, (d) defines the match/mismatch semantics
placement scores against.

Types (all numpy):
- word: `(100,)` uint8, values 0/1; index i = coefficient of x^i.
- message: `(23,)` uint8 0/1.
- syndromes: `(26,)` uint8 (GF(2^7) elements); batched `(H, 26)` uint8.
- batch words: `(H, 100)` uint8 0/1.
- counter: python int in `[0, 2^18)`.
- seeds: `family_seed: bytes`, `row_seed: bytes` (from format identity; the
  format id IS the AES seed — see the format reader).
- site cells: `(100, 2)` int64 (y, x) in CELL units within the 64x64 tile.
- scalar decode result: `tuple[(100,) uint8, int] | None` (corrected word,
  n errors corrected).
- batch decode result: `list[tuple[np.ndarray, int] | None]`, row-aligned.

## 2. Algorithm, every constant valued

Constants (format law, frozen):
- `GF_PRIM_POLY = 0x89` (x^7+x^3+1, primitive over GF(2^7)); `_ORDER = 127`.
- `N_FULL=127, K_FULL=50, T=13, D_MIN=27, SHORTEN_BY=27, N_WORD=100,
  K_MSG=23, N_PARITY=77`.
- `TILE_CELLS=64, N_QUOTA=10, N_WORD_SITES=100, COUNTER_BITS=18, PAD_BITS=5,
  MESSAGE_BITS=23, PLANE_K=3` ('CMYK'.index('K')).
- Keystream domains consumed (values from holo2 `format/keystream.py:56-66`):
  `DOMAIN_PILOT_VALUES=2` (aux=plane, major=0, u=site index, v=0),
  `DOMAIN_PILOT_SITES=4` (aux=0, major=0, u=quota index, v=retry),
  `DOMAIN_FILLER_SITES=5`.
- Verification pins: sha256(generator_poly().tobytes()) =
  `a0be5064cfef57b2a84aaadbd7bd13b9772b1259fa041c25af0d7bde4922b684`
  ((78,) uint8 coeffs ascending); g(x) as int (bit i = coeff x^i) =
  `0x2c9352aa6cc054468311`. Pin the sha in a build-time verify script;
  NEVER store g(x) literals in code — always derive (rule from the golden).
- TRUE min distance of the counter codebook is 27 EXACT. Low weight spectrum
  of `encode_word(delta)` over all nonzero 18-bit deltas (re-verified this
  session, exhaustive 262,143): 27:3, 28:8, 31:119, 32:247, 35:1613,
  36:2668, 39:9551, 40:13205. Pairwise distances equal these weights because
  the word map is affine in the counter (step 8).

Steps:

1. GF tables: exp `(127,)` uint8, log `(128,)` int64. x=1; for i in 0..126:
   exp[i]=x; log[x]=i; x<<=1; if x & 0x80: x ^= 0x89. (log[0] unused.)
2. Generator: root set = union of 2-cyclotomic cosets mod 127 of r=1..26
   (11 cosets: C1,C3,C5,C7,C9,C11,C13,C15,C19,C21,C23; 77 roots). g(x) =
   product over SORTED roots of (x + alpha^r), computed in GF(2^7) with the
   exp/log tables; result collapses to binary, degree 77, g[0]=g[77]=1.
3. Encode (systematic): m_int = sum m[j]<<j (j=0..22); parity =
   (m_int << 77) mod g over GF(2) (`_polymod2`: repeatedly XOR g shifted to
   the leading bit); word[0..76] = parity bits LSB-at-0, word[77+j] = m[j].
   Counter packing: msg[i] = (counter >> (17-i)) & 1 (MSB-first at
   msg[0..17]); msg[18..22] = 0. Decode side unpacks the same way
   (`counter = (counter<<1) | msg[i]`).
4. Syndromes: matrix A[j-1, i] = exp[(j*i) % 127], shape (26,100) uint8,
   j=1..26, i=0..99. S = XOR-reduce of A's columns at the word's set bits;
   all-zero word -> zeros. Batched: process rows in 4096-row blocks;
   `block[:,None,:] * A[None,:,:]` then `bitwise_xor.reduce(axis=2)`
   (multiplication is exact selection on binary input).
5. Berlekamp–Massey (scalar, GF(2^7)) — copy `src/holo/core/bch.py:236-275`
   verbatim. Load-bearing clauses: discrepancy sum bound
   `min(lfsr_len, len(c_poly)-1)`; `d == 0` -> `shift += 1` only; length
   change iff `2*lfsr_len <= n` (`<=`, the equality case CHANGES length — a
   `<` is a different decoder); the length-change branch snapshots
   `prev = c_poly[:]` BEFORE extending c_poly; both branches XOR
   `alpha^(log d - log b_disc) * b_poly` in at offset `shift`; on change
   `lfsr_len = n+1-lfsr_len; b_poly = prev; b_disc = d; shift = 1`, else
   `shift += 1`; return trims trailing zeros. Returns (sigma ascending
   trimmed, L).
6. Chien: pow matrix P[i,j] = (-(i*j)) % 127, (127, 27) int64. vals[i] =
   XOR over nonzero sigma[j] of exp[(log sigma[j] + P[i,j]) % 127]; roots =
   positions with vals==0 over ALL 127 positions.
7. Decode acceptance — THE FIVE RULES (`bch._decode_syndromes:298-312`),
   every clause required:
   R1 all-zero syndrome -> (word.copy(), 0), BM never runs.
   R2 refuse if `L > 13` OR `len(sigma)-1 != L` (second clause reads the
      TRIMMED locator).
   R3 refuse if Chien root count over all 127 positions != L, OR any root
      >= 100 (a correction in a shortened position).
   R4 flip the roots, re-syndrome the corrected word, refuse if any nonzero
      (sigma that passed R2/R3 can still fail to be a binary error pattern).
   R5 report errors = int(L) (R3 already forced == root count).
8. decode_erasures (errors AND erasures, known positions only) — copy
   `src/holo/core/bch.py:346-393`. erasure_idx unique-sorted; out-of-range
   raises; `f > 26` -> None; `f == 0` -> plain decode. Two trials: fill all
   erasures with 0, then 1; decode each; e_out = corrections at NON-erased
   positions; ACCEPT only if `2*e_out + f <= 26` (budget ENFORCED INSIDE,
   no caller knob — e022 v2.1 bug class); best = min e_out. Uniqueness:
   two accepted codewords would be < d apart.
9. Address-word layer (`pilots.py`):
   - Site construction (family_seed): quota edges
     `[0,6,12,19,25,32,38,44,51,57,64]` (= floor(i*6.4)), spans
     `6,6,7,6,7,6,6,7,6,7`; quota cell q = qi*10+qj raster order; dy =
     bounded_draw(family_seed, DOMAIN_PILOT_SITES, u=2q, span_y(qi)), dx =
     same with u=2q+1, span_x(qj); site = (y0(qi)+dy, x0(qj)+dx);
     site_index = q; codeword bit i prints at site_index i. Fillers/dust:
     16-bit rejection over 4096 tile cells (65536 % 4096 == 0, unbiased),
     8 tries per block then retry+=1, runaway cap 64; dust = 20 filler
     draws re-sorted by flat index y*64+x (stable argsort).
   - Value scramble (row_seed): `keystream.bits(row_seed,
     DOMAIN_PILOT_VALUES, plane, 0, arange(100), 0)` — one bit per
     site_index, IDENTICAL for every tile (periodic; removable under any
     phase hypothesis). Printed value = encode_word(counter) XOR scramble.
     Seed asymmetry is deliberate: sites key from the geometry-free family
     seed (shared lattice acquisition), values from the row seed (wrong
     geometry -> coin flips -> word gate refuses).
   - decode_word: XOR scramble -> decode (or decode_erasures) -> pad gate
     `msg[18:].any() -> None` (the authoritative 2^-5 gate) -> unpack
     counter MSB-first.
   - Colour surface (src/holo ONLY; needed for acceptance 3/4/6/7):
     `color_word_states = word_values * 3` (state 0 = W, state 3 = CM);
     `decode_color_word` refuses unless shape (100,) and every state in
     {0,3}, then decodes `(states == 3)`. Dust-state schedule
     (`dust_state_values`, cycle law + domain-9 permutation) is colour
     furniture — assign to the colour/format reader (open question 2).
10. Batched decode (`bch_batch.decode_many`) — the sweep kernel. Derived
    tables (import-time, from the scalar's own tables): `_EXP2` = exp
    doubled (254,); `_POISON = 254`; `_EXPZ` = _EXP2 zero-padded to 512
    (so EXPZ[s] = exp[s % 127] for s < 254, 0 at/past 254 — "zero operand
    contributes nothing" as an index, not a branch); `_LOGZ` = log int16
    with log[0] = 254; `_SIGMA_WIDTH = 14` (T+1); `_BM_WIDTH = 27` (2T+1,
    a PROVED bound on the connection polynomial, bch_batch.py:161-185);
    `_POW_COLUMNS = ascontiguousarray(chien_pow[:, :14].T)` (14, 127)
    int16; `CHIEN_BLOCK_ROWS = 4096` (memory ceiling ~1.6 MB/block, never
    a limit).
    - Lockstep BM (`berlekamp_massey_many:205-413`): state arrays over H
      rows: sigma (H,27) u8 init [1,0..], auxiliary (H,54) u8 with
      permanently-zero left half and aux[:,27]=1 (shift-padded: the
      scalar's `c_poly[i+shift] ^= b_poly[i]` becomes one gather at
      `27 + i - shift`), sigma_len/auxiliary_len/lfsr_len/shift int16
      (init 1/1/0/1), b_disc u8 init 1. THE TWO-STEP COLLAPSE: loop
      `for step in range(0, 26, 2)` — every odd step's discrepancy is
      provably zero for syndromes of BINARY words (S_2j == S_j^2 by
      Frobenius), so run 13 even steps and end each with
      `shift = 2 if change else shift+2` (own rule then the skipped
      step's +1; the +2 is NOT optional — a shift short by one lands the
      whole update one coefficient low). Discrepancy: rows[:,step] XOR
      XOR-reduce of EXPZ[LOGZ[sigma[:,1:step+1]] + synd_log[:,step-1::-1]]
      masked by column <= min(lfsr_len, sigma_len-1), poison elsewhere.
      change = nonzero & (2*lfsr_len <= step). Snapshot previous
      sigma/sigma_len BEFORE the XOR update; masked writes via np.where.
      Trim: trimmed = 27 - argmax over reversed (sigma!=0 & col<sigma_len).
      Returns (sigma (H,27) u8, trimmed int64, lfsr_len int64) with
      `sigma[h,:trimmed[h]]` element-identical to the scalar's list.
      PRECONDITION: syndromes of 0/1 words ONLY — arbitrary syndrome rows
      get a WRONG locator silently; the scalar BM stays the general one.
    - Batched Chien (`chien_root_mask:416-447`): (S,14) locators -> (S,127)
      bool mask; per coefficient j: values ^= _EXP2[log[c_j] + P_cols[j]]
      * (c_j != 0); flatnonzero(mask[s]) == scalar `_chien_roots`.
    - Routing (`decode_many:450-509`): validate 0/1 -> batch syndromes ->
      partition clean rows (R1) -> lockstep BM on dirty rows -> R2 mask
      `(L <= 13) & (trimmed-1 == L)` -> slice sigma[:, :14] (zero past
      trim by R2) -> Chien mask -> R3 mask `(rowsum == degree) &
      ~roots[:,100:].any(axis=1)` -> corrected = words ^ roots[:, :100]
      -> R4 batch re-syndrome, keep clean -> out[row] =
      (corrected.copy(), int(degree)). Bit-identical to scalar
      decode_many by construction; the bar is bit-identity, NEVER a
      tolerance.
11. Match/mismatch semantics for placement (kernel only; sweep geometry,
    budgets, and the accept/refuse policy are reader 07):
    - COLD CANDIDATE: descramble the 100 gathered hard bits, full BCH
      decode; a decode surviving the per-word legality gates IN THIS ORDER
      is a candidate: (a) five-zero-pad gate `msg[18:].any() -> refuse`,
      (b) page-domain gate `page >= max_pages -> refuse` where
      `(page, ty, tx) = divmod chain: page, rem = divmod(counter,
      tiles_per_page); ty, tx = divmod(rem, tiles_x)`;
      `max_pages = 2^18 // tiles_per_page`, (c) `errors > 13 -> refuse`.
      Per-phase visibility floor: >= 90 of the 100 sites visible
      (`place_admission.py:309`, value 90) — a per-phase protection
      applied to the SURVIVING candidate, never a mask gate, and
      visibility does NOT turn hidden samples into erasures at the cold
      rung. Candidate priority = ascending (errors, slot_index, rot_k,
      phase_index). errors IS the printed-word Hamming distance (scramble
      XOR preserves distance; the accepted zero-pad message re-encodes to
      the corrected word).
    - TEMPLATE CHECK: expected printed bits for a hypothesized (pose,
      counter) are exactly `encode_word(counter) ^ scramble` at the 100
      site cells; the placement statistic is the evidence-weighted
      mismatch of observed vs expected. Kernel facts placement leans on:
      the word map is AFFINE over GF(2) in the counter (`word(c1) ^
      word(c2) == encode_word(c1 ^ c2)` — the scramble cancels pairwise),
      so tile-lattice-aligned cross-page aliases share ONE constant
      difference codeword E; full-word mismatch of any alias >= 27/100
      (the spectrum above), but the search parity class alone can see as
      little as 7-8/45 of E's weight — so rival/decoy comparison MUST be
      whole-word (both parity classes; src/holo v0.30
      `V1_WHOLEWORD_RIVAL_GATE`, model.py:82-95) to keep the d=27 floor.
      E022 gate bars for reference (owner: reader 07): true 0.20, decoy
      0.20, gap 0.08, validation 0.24; support floor 30/parity.
    - KNOWN-POSITION READ (a CHECK, not a search): per site, keep ONE
      strongest read per capture chosen by the deterministic key
      `(-|evidence|, pose_id_str, bit)` (holo2 R7b); sum votes in sorted
      (capture_id) order with weight `max(|evidence|, 1e-3)`, sign
      `(1 if bit else -1)`; printed[site] = vote >= 0. Unobserved sites =
      erasures; if f > 26 no decode is attempted; else decode_erasures for
      the error count AND `pilots.decode_word` as the authoritative pad
      gate (both must succeed). certified = decoded == expected counter;
      conflict = legal decode naming a DIFFERENT tile; None = neither and
      NEVER vetoes an independently accepted placement (word trust is
      one-way).
12. Stage-A false-accept arithmetic (recorded here, owned by 07):
    p_single = 2^18 * sum_{i=0..13} C(100,i) / 2^100 = 1.721e-9
    (sphere = 8,322,009,263,697,336); family-wise bound = H * p_single;
    a 200x200 window declares H = 9 slots x 64x64 phases x 4 rot =
    147,456 -> 2.54e-4.

## CPU coverage of the batch path

Measured (holo2 GIL diagnosis, real K sheet): the ONE `decode_many` call in
the cold word sweep = ~72% of ALL receiver CPU. Inside it: `_chien_roots`
30.0% of total, `_berlekamp_massey` 25.1%, `_as_words` 0/1 validation 7.0%
of pool samples. The batched Chien card landed first and left BM as 83% of
the remaining batched decode (89 ms of 106 per 4096-row batch); the
lockstep BM card removed that. So bch_batch covers the ENTIRE sweep-decode
kernel (syndromes, BM, Chien, re-check all array-batched); the residual
Python is per-row result assembly + the legality gates. The scalar path's
other uses (known-position reads, erasure decodes) are O(tiles), not
O(147k/window) — negligible. holo2's thread ceiling was 1.01x under the
GIL; holo3 on 3.14t gets real parallelism, but the batched arm is still
mandatory — it is the difference between 9 slots/window being free and
being the whole run.

## 3. Copy-vs-rewrite

| Block | Verdict | Source |
|---|---|---|
| Constants + GF tables + `_polymod2` | COPY-AND-STRIP | `src/holo/core/bch.py:45-58,63-78,89-94` |
| `_cyclotomic_root_set`, `generator_poly` | COPY-AND-STRIP (drop asserts, keep derive-not-store) | `src/holo/core/bch.py:120-158` |
| `encode`, `message_from_word` | COPY-AND-STRIP | `src/holo/core/bch.py:163-181` |
| `_synd_matrix`, `syndromes`, `_syndromes_many_words` | COPY-AND-STRIP (4096 blocking kept) | `src/holo/core/bch.py:186-222` |
| `_berlekamp_massey`, `_chien_pow_matrix`, `_chien_roots`, `_decode_syndromes`, `decode` | COPY-AND-STRIP | `src/holo/core/bch.py:236-325` |
| `decode_erasures` (budget inside) | COPY-AND-STRIP | `src/holo/core/bch.py:346-393` |
| bch_batch derived tables + widths | COPY-AND-STRIP (make all module-level eager) | `holo2/src/holo2/format/bch_batch.py:119-185` |
| `berlekamp_massey_many` | COPY-AND-STRIP (drop the width RuntimeError; bound 27 stays) | `holo2/src/holo2/format/bch_batch.py:355-413` (body) |
| `chien_root_mask` | COPY-AND-STRIP | `holo2/src/holo2/format/bch_batch.py:431-447` (body) |
| batched `decode_many` | COPY-AND-STRIP; make it THE only batch API | `holo2/src/holo2/format/bch_batch.py:460-509` (body) |
| pilots constants + quota edges | COPY-AND-STRIP | `src/holo/format/pilots.py:45-55` |
| `word_site_cells_yx`, `filler_site_cells_yx`, `site_cells_yx`, `site_cell_indices` | COPY-AND-STRIP | `src/holo/format/pilots.py:58-120` |
| `dust_site_cells_yx`, `color_site_cells_yx`, `color_payload_cell_indices` | COPY-AND-STRIP (colour closes need them; home per Q1/Q2) | `src/holo/format/pilots.py:123-154` |
| `value_scramble_bits`, `encode_word`, `word_values`, `decode_word` | COPY-AND-STRIP | `src/holo/format/pilots.py:159-186,248-266` |
| `color_word_states`, `decode_color_word` | COPY-AND-STRIP | `src/holo/format/pilots.py:189-203` |
| `dust_state_values` | COPY-AND-STRIP if this reader's; else colour reader | `src/holo/format/pilots.py:206-245` |
| known-position vote arithmetic (R7b deterministic form) | COPY semantics, rewrite lean — MUST use the holo2 deterministic version, not src/holo's | `holo2/src/holo2/solve/words.py:445-547` |
| Stage-A sweep wrapper (slot grid, gather, sort, gates) | REWRITE LEAN (geometry to reader 07; gates per step 11) | ref `holo2/src/holo2/solve/words.py:192-427` |
| `WordAttemptBudget` | REWRITE: keep the two formulas as a plain function; drop the dataclass/validation | `src/holo/receive/words.py:71-79` |
| scalar `decode_many` | DROP (batched is the only batch path; scalar `decode` stays for singles) | — |

## 4. Measured-channel / format invariants that MUST survive

- d_min = 27 EXACT, spectrum 27:3/28:8/31:119/32:247 — every decoy floor,
  the placement margin, and the pad-gate false-accept math price off it.
- Errors-only decode at FULL t=13, no caller-supplied max_errors — a weaker
  caller budget once silently disabled erasure fills (e022 v2.1).
- `2e + f <= 26` enforced INSIDE decode_erasures — same incident; the knob
  must not exist.
- Erasures ONLY at known positions, NEVER in hypothesis search — the
  Stage-A false-accept budget is derived for full-support words
  (HOLO-DESIGN §12 / PILOTS-DESIGN §14).
- Per-phase visibility floor 90/100 — the qualified per-phase protection;
  it is not an erasure source and not a window mask gate.
- Pad gate is authoritative and FIRST among the legality gates — 2^-5 of
  random decodes die here; reordering changes the audited refusal counts.
- Whole-word rival scoring for decoy comparison — parity-class mismatch
  bottoms at 7/45 for constant-XOR aliases; only both classes restore d=27
  (measured, FULL-DOMAIN-RIVAL-ANALYSIS; colour closes ran with v0.30).
- Batched arm bit-identity with the scalar — bar is identity, never
  tolerance; proven at build time against src/holo outputs
  (`_distill/verify/` script), then the scalar oracle machinery is gone.
- BM `2*lfsr_len <= n` with `<=`; the trimmed-length refusal clause; the
  R4 re-syndrome — each independently kills real miscorrections.
- Lockstep BM binary-word precondition — guaranteed by construction at the
  gather (hard bits from a binarized plane), never by runtime checks.
- Sites from family_seed, values from row_seed — wrong-geometry hypotheses
  must descramble to coin flips (the format's own refusal mechanism).
- Word trust is one-way: certified words seed/label; failures never veto
  an independently accepted placement.

## 5. DROP (aggressively)

- The `_cache` dict + lazy init + `# type: ignore` returns: build exp/log,
  synd matrix, chien pow, gpoly, and all bch_batch tables EAGERLY at module
  import as plain module constants. Thread-correct by construction (3.14t),
  no locks, no idempotence questions.
- All `_as_word`/`_as_words` shape/0-1 ValueErrors and every assert
  (gf_tables primitivity, gpoly degree, site uniqueness) — inputs are
  guaranteed by construction; the build-time verify script is the check.
- The width RuntimeError tripwire in lockstep BM (proved unreachable,
  bch_batch.py:163-185 carries the proof; _BM_WIDTH=27 itself stays).
- Scalar `decode_many` and the dual-arm `batched_sweep` switch,
  `PlacementConfig.batched_word_sweep`, the oracle/equivalence measure
  harness, cross-tree differential pins — build-time verification only.
- `WordAttemptBudget` dataclass with __post_init__ validation and
  `qualification_id` provenance strings; `admission_datum`/OR9 indirection
  (literal 90), `_carried_int`, `_is_cell_count`/`_stage_shape` validation,
  SlotStage "centre"/"rest" staging (pull-scheduler spend staging — the
  holo3 frontier sweeps whole windows), `StageAResult.reason` audit strings
  (emit a diag event instead), `AddressPatchLike` seams.
- holo2's carry docstrings, provenance essays, and the entire quarantine/
  contradiction/journal plumbing around KnownWord.
- src/holo's order-dependent known-position vote (first-seen tie-break,
  insertion-order float sum) — superseded by R7b; do not copy it.
- `decode_erasures`' erasure-index range ValueError (construction
  guarantees 0..99) — keep the f>26 refusal and the 2e+f budget (those are
  format law, not guards).

## 6. holo3/data.py needs

Consumed (from format identity / registry): `family_seed: bytes`,
`row_seed: bytes`, `plane: int` (K=3; colour planes for colour words),
`tiles_yx: (int,int)`, `tiles_per_page: int`, `max_pages: int`
(= 2^18 // tiles_per_page), `tile_counter(page,ty,tx)` /
`tile_address(counter)` as pure functions of tiles_yx.

Produced FACTS (frozen dataclasses, merged single-writer):
- `WordCandidate`: capture_id, plane, window_id, oriented_origin_yx
  (int,int) cells, rot_k int, counter int, page int, tile_yx (int,int),
  errors int, page_origin_yx (int,int), source tag.
- `KnownWordRead`: page, tile_yx, expected_counter, decoded_counter
  (int|None), errors (int|None), n_erasures int, contributors
  (sorted tuple), source tag. Semantics: certified / conflict / silent.

Consumed observation shape (produced by detect/pose plugins):
- `PilotObservation`: capture_id str, pose_id (orderable), page, tile_yx,
  site_index int (0..99), bit int, evidence float (signed magnitude).

Stateful/shared: NOTHING. Every kernel function is pure over immutable
inputs; the only module state is the eagerly-built read-only tables. Word
jobs (a window's sweep, a tile's known-position read) are pure jobs;
candidates/reads are facts for the serial merge. The known-position vote
must reduce over a SNAPSHOT of observations with the R7b deterministic
ordering, or workers-8 vs workers-1 payloads diverge (acceptance 8).

## 7. Pitfalls / incidents

- e022 v2.1: caller-passed erasure budget silently disabled fills — the
  reason the budget lives inside the decoder and no knob exists.
- 014.4 gate-constants-vs-construction-floors: a pre-registered decoy bar
  >0.35 was IMPOSSIBLE — the spectrum imposes a 0.257-0.342 decoy floor.
  Any new bar must respect the code's algebra.
- 2026-07-29 exhaustive correction: sampled min distance 32 (400 pairs)
  was wrong; TRUE min is 27 mult 3. Never quote the sampled figure.
- Full-domain rival: cross-page constant-XOR alias, search-class weight
  8/45 -> weighted 0.1415 rival, certain (not unlucky) at 312-page domain;
  fixed by whole-word rival scoring, NOT by raising bars.
- R7b: float vote sums in arrival order + first-seen tie-breaks made
  known-position words harvest-order-dependent; invisible in single-capture
  echoes. holo3's thread model makes this a live bug, not a latent one.
- Lockstep BM on non-binary-word syndromes returns a WRONG locator
  silently — the binary premise is a theorem about the input gate; holo3
  keeps the theorem true by construction (u8 0/1 hard bits at the gather).
- The skipped odd BM step still increments shift — the +2 collapse is
  arithmetic, not tidiness; +1 lands every update one coefficient low.
- Import-order: bch_batch tables derive from bch's; in holo3 build both in
  one module (or ordered top-level statements), eagerly.
- 012.3 phantom payload: scramble/site draws must come from the real
  keystream implementation, never retyped literals; a missing dtype forks
  a stream.
- holo2 carried only the K word surface; the colour closes (e032, uplift,
  sheet I) all ran through src/holo's colour word functions — copy those
  from src/holo, not holo2.
- errors == printed-word Hamming distance only because the scramble is a
  fixed XOR; anything that re-keys the scramble per-tile breaks the
  candidate-ordering semantics (and the format — don't).

## 8. Open questions for the contract author

1. Single home for pilot site construction (word/filler/dust cells): this
   spec claims it for holo3/format/pilots because Stage A and template
   prediction consume positions; confirm the lattice/geometry reader (or
   keystream reader) does not also claim it.
2. Who specs the colour dust-state schedule (`dust_state_values`,
   `CodecProfile.dust_base_cycle`, domain-9 permutation) — this reader or
   the colour-format reader? It is word-adjacent furniture but keyed by
   codec profile.
3. Confirm: batched `decode_many` is the ONLY batch API and the scalar
   survives only as `decode`/`decode_erasures` for singles (no dual arms,
   no switch) — bit-identity proven once in `_distill/verify/`.
4. Where do the E022 gate constants (0.20/0.20/0.08/0.24, floor 30) and
   the union-bound formula live — data.py constants or plugins/place? They
   are recorded here but the decision rule is reader 07's.
5. Confirm holo3 adopts whole-word rival scoring as the ONLY rival rule
   (src/holo v0.30; the colour closes predate plane-fields but not v0.30),
   retiring the historical parity-class-only decoy comparison entirely.
6. Erasure-assisted Stage A stays forbidden as doctrine — should the
   contract pin this in prose (data.py docnote is banned: no comments), or
   is the absence of the code path the pin?
7. `known_position_words` scope: one (capture, footing) per reduce (holo2
   ruling 4). Does the holo3 merge ever want a cross-capture word vote, or
   does multi-capture union stay strictly at the certificate layer?
