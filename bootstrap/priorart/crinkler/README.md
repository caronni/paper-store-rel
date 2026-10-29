# bootstrap/priorart/crinkler: Crinkler, transliterated to Python and then optimised for it (2026-10-20, machine 1)

The owner's task: "pull crinkler and transliterate, then optimize to python
-- see if it becomes equivalent to our solution in size / performance."

Crinkler is the compressing linker for 4 KB and 1 KB Windows intros by Aske
Simon Christensen and Rune L. H. Stubbe. Its upstream tree (commit
f74d964b of 2026-08-05, version 3.0a) was read only; nothing of it was
built, run, imported or copied. The files that port Crinkler's code
(`crk_dec.py`, `crk_enc.py`, `dec_crkpy.py`, `enc_crkpy.py`, and the search
in `fam.py`, the d texts in `build_typed.py`) are marked as ALTERED
VERSIONS in their headers. The zlib licence is at the end of this file.

Simulation and measurement only. Nothing is printed, nothing is promoted,
no tracked file outside this directory is changed. Every number below is
MEASURED on machine 1 with the free-threaded CPython 3.14.8 of the main
checkout's `env/` (`env/bin/python`; this worktree
has no `env/` of its own), in this session, unless it says ESTIMATE or
EXTRAPOLATION. The machine was shared
(load 7-9 on 10 cores), so the walls are under load.

## The answer

**Typed stage: equivalent in size and in speed; not better.**

- Crinkler's model written for Python types **3,896 characters** against
  the build of record's 3,895.
  - With Crinkler's VERYSLOW search it types 3,884; with VERYSLOW and its
    1k counter rule, 3,874.
  - Its decoder runs at cm2's speed: 69-71 µs/byte against cm2's 74 in
    one session, 70.6 against 77.9 in the refuter's. The difference is
    inside the run-to-run spread on a loaded machine, and the Crinkler
    family uses 7 models where cm2 uses 9, so "equivalent" is what the
    numbers show, not "faster".
- Crinkler's hashed table (CRC32C hashing into a table of 8-bit counters,
  with five changes from Crinkler listed under `crkhash` in 3(a), all of
  which helped it) types **4,055 (+160)** and decodes 4.5 times slower.
  Crinkler's exact hash would type more, so +160 is a lower bound.
- The one idea that pays is **compressor-searched sparse context masks
  and weights, typed as data**. cm2 with that idea types **3,863: 32
  characters fewer (0.8 %)**. The split is +35 characters of decoder
  text against -67 characters of data lines. It transfers into cm2 at that
  price and no further.
- Crinkler's other knobs, put into cm2 one at a time, all lose (+38 to
  +162 characters):
  - its counter rule;
  - its x4 boost;
  - its base probability 10.

**R2 stage: equivalent in pages; the bundle grows, the monolith shrinks.**

- Every Crinkler-family variant keeps the page bundle at 3 R2 pages and
  the R3 monolith at 2 (the single-knob cm2 hybrids push the monolith to
  3).
- The masks chosen on the typed payload over-fit it:
  - the bundle grows 336-638 B (731 B for the hashed form);
  - the monolith shrinks 49-196 B.
- A model searched on each input (Crinkler's own way) still loses on the
  bundle (+65 B). It wins 399 B (3.8 %) on the monolith, but the reader
  would have to carry about 250 characters of masks. (These two figures
  are the `--retune` rows, which leave out z. The transliteration's own
  search, with its 32-bit coder, gives 14,679 / 10,326 B with its 37-byte
  container, and would also need Crinkler's arithmetic decoder in r.py,
  which is not counted either.)

**Archive stage: not equivalent in size; equivalent in speed once
optimised.**

- On 1 MB of T1, Crinkler's model gives 268-271 KB. The others give:
  - strong2: 245.6 KB, so Crinkler is +9.2 to +10.3 % (the wrap-mode run,
    270,864 B, is the +10.3; the saturating runs +9.2 to +9.6);
  - cm1 k24: 252.4 KB;
  - cm2 with exact contexts: 261.9 KB.
- On 2 MB it gives 526.3 KB. strong2 gives 470.2 KB, so Crinkler is +11.9 %,
  and the gap grows with size.
- **On the whole of T1 (MEASURED after the refuter's round, round trip
  byte-exact), crkpy gives 1,918,411 B with the best model set found
  (+16.4 % over strong2's 1,648,648) and 1,944,034 B with the first
  round's set (+17.9 %): 18 archive pages against strong2's 15.** 17
  pages hold at most 1,876,247 B (holo's planner), so no set searched here
  comes near 17. Its weights are fixed for the whole input; strong2 mixes
  adaptively per context, and the gap grows with the input.
- The Python-optimised decoder (crkpy) gives the transliteration's bytes
  (269,243 against 269,185 for the same models). It runs at 67-92 µs/byte
  in 520-540 MB (T1: 10.6-14.0 min):
  - strong2: 84 µs/byte in 1.36 GB, re-measured;
  - cm2 exact: 55 µs/byte in 5.65 GB, re-measured;
  - Crinkler as transliterated: 199-206 µs/byte in 1.5 GB;
  - cm2 v2: about 2,460 µs/byte at 1 MB, quadratic (EXTRAPOLATED).
- **Its speed and memory are equivalent to ours; its size is not.**

**Where Crinkler's ideas go:**

- The searched sparse masks and weights transfer into cm2 at the typed
  rung (-32 characters), and nowhere else.
- Crinkler's counters, boost and base do not transfer.
- Its fixed hashed table is the right shape for memory at archive scale.
  Its CRC32C chain is the wrong hash for text and speed in Python; one
  big-integer multiply-modulo per model keeps the table at Python speed
  (crkpy).

### Headline table

| stage | currency | cm2 v2 (record) | Crinkler as transliterated | Crinkler optimised for Python | best hybrid "cm2 + Crinkler idea" |
|---|---|---|---|---|---|
| typed | characters typed (a.py + data lines) | **3,895** (826 + 3,069) | 4,055 (1,036 + 3,019), Crinkler's hashed table with a modified hash (crkhash) | 3,896 (853 + 3,043); VERYSLOW 3,884; VERYSLOW + 1k rule 3,874 | **3,863** (861 + 3,002), cm2 + searched masks + weights |
| typed | coded payload bits | 14,381 | 14,134 | 14,254 / 14,161 / 14,147 | 14,069 |
| typed | decode µs/byte | 73.9 | 336.2 | 68.8 / 71.1 / 70.1 | 73.4 |
| R2 | page bundle B (R2 pages) | 14,472 (3) | 15,203 (3); own search per input: 14,679 with container (3), decoder not counted | 14,943 (3) | 14,808-14,979 (3) |
| R2 | R3 monolith + arch B (R2 pages) | 10,599 (2) | 10,507 (2); own search: 10,326 with container (2), decoder not counted | 10,527 (2) | 10,403 (2) |
| archive | 1 MB of T1, bytes | cm2 exact 261,936; strong2 245,555 (both re-measured, = record) | 270,864 (wrap), 269,185 (saturate) | 269,243; best set 268,119 | — |
| archive | 2 MB of T1, bytes | cm2 exact 502,747; strong2 470,169 (record) | 526,304 (saturate) | 526,384 | — |
| archive | T1 bytes (pages) | strong2 1,648,648 (15), cm2 exact 1,761,165 (16) (record) | not run (about 33 min decode, EXTRAPOLATION) | **1,918,411 (18)** best set; 1,944,034 (18) first-round set; MEASURED, round trip exact | — |
| archive | T1 decode | strong2 13.1 min, 1.36 GB (record) | — | 10.6 min, 540 MB (best set); 14.0 min (first-round set) | — |
| archive | decode µs/byte, 1 MB | cm2 exact 54.7; strong2 83.7; cm2 v2 ≈ 2,460 (EXTRAPOLATION) | 199.0 / 205.5 | 70.5-92.0 | — |

(typed: the decoder in every column carries cm2 v2's big-integer rANS
coder; R2: each variant coded with its own d, primed with its own r.py;
"own search" = Crinkler's search run on that input, with its 32-bit coder;
the typed speeds are one session's best of 3 under load 7-9 and move by
about 5 % between sessions.)

## 1. Crinkler's model in our terms

Pointers are into the upstream tree `source/` (Compressor/ = the C++ model
and search, Crinkler/modules/ = the x86 decompressors).

### 4k mode: the default, header30.asm + Compressor/

**Contexts.**

- A model is one byte, its mask over the 8 preceding bytes: bit 7 is 1
  byte back, bit 0 is 8 bytes back (`MAX_CONTEXT_LENGTH = 8`,
  Compressor.h:9).
- The context is the masked bytes plus the bits of the current byte so
  far, behind a leading 1 (cm2's `u`).
- Hash: `ModelHash` (Model.cpp:21-40; asm header30.asm:224-234) runs
  `crc32` (SSE4.2, CRC-32C, no inversion):
  - first over u;
  - then over each selected byte, 1 back first;
  - starting from a seed = the mask byte | the remaining weight-mask bits
    & 0xFFFFFF00 (CompressionStream.cpp:51-60).
- The decoder decodes one start bit with u = 0 before the data
  (ModelHashStart, Model.cpp:5-19; CompressionStream.cpp:62-71).

**Table.**

- One table of `HN = hashsize / 2` slots (prime), two 8-bit counters per
  slot, no check bits, so collisions share counters (header30.asm:251-254
  `div ecx`; Crinkler.cpp:465).
- Default HASHSIZE is 500 MB (main.cpp:223-224; the manual's "100" is
  stale), so HN = 262,143,977.
- **The compressor tries 100 smaller prime sizes** and keeps the one that
  compresses best (OptimizeHashsize, Crinkler.cpp:293-358; HASHTRIES
  default 100, main.cpp:225-226).
- The table is cleared at each part boundary (header30.asm:243-249).

**Counters.**

- After a bit y: `c_y += 1` (wraps 255 → 0, or stays at 255 with
  /SATURATE); `c_other >>= 1` if `c_other > 1`.
  - Compressor: UpdateWeights, CompressionState.cpp:51-54.
  - asm: header30.asm:281-294.
  - The saturate patch: Crinkler.cpp:422-427.

**Weights and combination.**

- `p_y = 10 + sum over models of c_y << (w + 2)` if either counter of that
  context is 0, else `c_y << w`. That is a x4 boost for a deterministic
  context (CompressionStream.cpp:121-142; header30.asm:256-274).
- Base probability 10 (DEFAULT_BASEPROB, Compressor.h:10;
  header30.asm:204-210).
- Weights are 0..9 (MAX_MODEL_WEIGHT, Compressor.cpp:15), at most 21
  models (Compressor.cpp:14).
- The weights travel as a 32-bit unary-coded mask, ModelList.cpp:64-117:
  - 1 = weight + 1;
  - 0 = a model at the current weight;
  - the parity of the low byte tells the decoder whether another part
    follows.
- No mixer learns anything: the weights are fixed per part, chosen by the
  compressor.

**Coder.**

- 32-bit binary arithmetic coder, AritCode.cpp:34-71:
  - bit 1 owns the low part, `threshold = size * p1 // (p0 + p1)`;
  - renormalise while size < 2^31;
  - output bits LSB-first in each byte, carries propagated back
    (PutBit, :19-32);
  - termination AritCodeEnd :73-90.
- The decoder is header30.asm:69-180 (`bt`, `mul`, `div`).
- The size estimates count in 1/256 bit (BIT_PRECISION, Compressor.h:11),
  with a 4096-entry log table (aritcode.h:28-42).

**Model search.** ApproximateModels4k, Compressor.cpp:164-274:

- It visits the 256 mask bytes in bit-reversed order of 0..255.
  - For each, it tries the current set plus that mask.
  - **OptimizeWeights** (:77-131) is a coordinate search: one weight ±1
    at a time, round-robin, until a full round brings nothing.
  - If the set got smaller, every older model is tried for removal, each
    removal re-optimising the weights.
- SLOW keeps the single best set. VERYSLOW keeps 3; an ELITE flag keeps
  the best lineage alive.
- FAST sets every weight to the mask's popcount (:64-75). INSTANT uses a
  fixed 11-model list (:147-162).
- The estimator (CompressionState.cpp:56-149,
  CompressionStateEvaluator.cpp:27-205):
  - It precomputes, for all 256 masks, the per-bit (right, total) counts
    with exact contexts (FindEntry compares the bytes; no collisions).
  - It evaluates a weight change incrementally, in packages of 64 bits,
    with float32 products and a cubic log2 polynomial (:150-160).
  - Each model costs 8 bits, plus 48 bits of header (:49, :196).
- The manual (doc/manual.txt:526-540) gives the time: SLOW takes "up to
  some tens of seconds for a typical 4k"; VERYSLOW 5-10× more.

**Code/data model sets.** The executable is split into parts, each with
its own model list and weights, compressed one after another:

- the parts (Crinkler.cpp:1382-1404, manual :338-343):
  - **Code**;
  - an optional **Text**, when there are ≥ 500 B of text and ≥ 500 B of
    other data;
  - **Data**;
- the context bytes run on across the boundary; the hash table does not
  (CompressionStream.cpp:84-88; header30.asm:243-249);
- the section order inside the parts is searched too (ORDERTRIES,
  EmpiricalHunkSorter).

### 1k mode: /TINYHEADER, header22_1k.asm + Compressor.cpp:276-840

- **No hashing at all.** For every bit, the decoder scans every earlier
  position and keeps the ones whose masked bytes and current-byte prefix
  match. That is exact contexts at O(n²) time (manual :578-588).
- Model k (0..32) is the byte mask `(k - 1) & 255` over the 8 previous
  bytes. Model 32 (mask 31, the last 5 bytes) is always on; the others are
  bits of a 32-bit model mask.
- Counters are unbounded: on a match `c_y += 1`,
  `c_other = (c_other + 1) >> 1`.
- `n_y = sum c_y * (boost if a counter is 0 else 1)`.
- `P(1) : P(0) = n_1 + b0 : n_0 + b1`, two base probabilities 4..8.
- Search (ApproximateModels1k, :738-840):
  - start with all 32 models on;
  - switch off the model whose removal helps most, until none helps;
  - every candidate gets the best of 7 boosts × 25 base-probability pairs
    (Evaluate1K, :651-736).
- Same coder as 4k, no start bit. Training starts at byte position -1, a
  zero byte (:308, the asm's `dec esi`).

### Crinkler next to cm2 v2, knob by knob

| | cm2 v2 (typed/cm2_dec.py) | Crinkler 4k |
|---|---|---|
| contexts | 9 contiguous orders 0, 1, 2, 3, 4, 6, 8, 12, 16 bytes | ≤ 21 searched byte subsets of the last 8 |
| context store | exact dict, key (h & mask, u), unbounded memory | hashed table of 8-bit pairs, no check, fixed memory |
| weights | fixed: weight = order index 0..8 | searched per input, 0..9, typed as data |
| boost | x2 when the other count is 0 | x4 |
| update of the other count | min(c, c // 4 + 2) | c >> 1 if c > 1 |
| base | 1 | 10 |
| coder | big-integer rANS, exact, quadratic | 32-bit arithmetic coder, linear |
| parameters per input | none (one model for everything) | masks + weights (+ hash size) |

## 2. The transliteration

- **`crk_dec.py`** (pure Python, no imports) is the decompressor of both
  modes.
  - 4k (`unpack4k`): CRC32C table, the slot table as a bytearray, the
    weight-mask parse, the start bit, parts with the table cleared between
    them, the 32-bit arithmetic decoder.
  - 1k (`unpack1k`): exact contexts in a dict. The counts are the asm's;
    the algorithm is not its quadratic scan.
  - Two marked EXTENSIONS: a primer (bytes that only train the model) and
    our container (`parse`) instead of the exe header.
- **`crk_enc.py`** (numpy) is the compressor side.
  - The 4k coder (`compress4k`, `Enc` = AritCode with PutBit carries).
  - The estimator `State` (ApplyModel for all 256 masks, then incremental
    sizes).
  - `approximate4k` (ApproximateModels4k with OptimizeWeights:
    INSTANT/FAST/SLOW/VERYSLOW, ELITE, the removal pass, including the C++
    detail that a rejected removal leaves the trial's weights on the other
    models).
  - `optimize_hashsize` (OptimizeHashsize).
  - The 1k compressor and search (`model_data1k`, `evaluate1k`,
    `approximate1k`, `compress1k`).
- `run_faithful.py` drives both on one input and decodes in-process.

**Simplified, and why:**

- **The estimator's log2.** The float32 polynomial is replaced by float64
  `log2` (exactness). Near-ties may resolve differently, so the chosen
  model sets need not be Crinkler's.
- **Search sample.** On large inputs the model search runs on the first
  64 KB. Crinkler searches the whole input; it is built for 4 KB.
- **Hash tries.** 3 for payload, bundle and monolith (100 for the VERYSLOW
  payload row); 0 on the archive prefixes (each try is a full Python
  compression).
- **The search's last step** (`fam.search`, used by the typed rows and by
  crkpy's own search): upstream's final OptimizeWeights (Compressor.cpp:269)
  starts from ApproximateWeights (:83), every weight reset to the mask's
  byte count. The first round kept the searched weights instead, without
  saying so (the refuter found it). It now follows upstream
  (`CRK_FINAL_KEEP=1` restores the first round). Rebuilt with upstream's
  step, all eight searched typed variants choose the same z, to the
  literal, and type the same counts (MEASURED,
  `final_reset/build_*.log`), so no number in this README moves.
  `crk_enc.approximate4k` was faithful here from the start. Not ported:
  upstream's guard that turns an empty model set into one order-0 model
  (Compressor.cpp:262-266); no searched set here came out empty.
- **Not ported:** section reordering (ORDERTRIES/EmpiricalHunkSorter), the
  call transform, imports, the PE header, EvaluateSize4k (the hunk
  sorter's estimator), the parallelism.

**Round trips** (`run_faithful.py`, `bench_arch.py`, byte-exact, MEASURED):

| input | mode | raw | coded (packed) | decode |
|---|---|---|---|---|
| typed payload (primer = a.py) | SLOW, 3 hash tries | 4,564 | 1,745 | 0.92 s |
| typed payload | VERYSLOW, 100 hash tries | 4,564 | 1,742 (17 models; 460 s to compress) | 0.89 s |
| typed payload | 1k | 4,564 | 1,773 | 0.25 s |
| page bundle (primer = r.py) | SLOW | 50,533 | 14,642 | 11.1 s |
| R3 monolith + arch (primer = r.py) | SLOW | 24,460 | 10,289 | 5.4 s |
| 1 MB of T1 | SLOW (64 KB sample), wrapping counters | 1,000,000 | 270,864 | 199 s |
| 1 MB of T1 | SLOW, /SATURATE | 1,000,000 | 269,185 | 206 s |
| 2 MB of T1 | SLOW, /SATURATE | 2,000,000 | 526,304 | 412 s |
| empty | SLOW | 0 | 0 | |
| 1 byte | SLOW | 1 | 1 | |
| 4,096 random bytes | SLOW | 4,096 | 4,128 (one order-0 model) | |
| `test_roundtrip.py` | 3 model lists × 2 table sizes × saturate on/off, a primer, 2 parts; 1k with 3 model masks; crkpy; the family's cm2 configuration == cm2 v2 (same x) | empty, 1 B, 300 random B, 1,500 B | | all exact, 4 s |

**Faithfulness is argued by reading, not by running Crinkler** (it is a
Windows linker with x86 decompressors). The encoder and decoder here
mirror each other, which the round trips prove; that they mirror
*Crinkler* is argued line by line in the file headers.

**What I could not verify:**

1. That `_mm_crc32_u8` does no pre- or post-inversion. The polynomial is
   settled: `crk_dec.CRC` with the standard initial value and final
   inversion gives 0xE3069283 on "123456789", the CRC-32C check value
   (MEASURED after the refuter's round). That the instruction itself
   inverts nothing still rests on reading the Intel definition; not checked
   against hardware.
2. That the 1k decoder gives `b0` to bit 1 and `b1` to bit 0. Taken from
   the compressor's `AritCode(&as, n1 + b0, n0 + b1, 1 - bit)`
   (Compressor.cpp:629); the asm's register roles were not traced to the
   end.
3. SETTLED after the refuter's round (computed, exhaustively over the
   critical h of each residue class): `CompressFromHashBits`'s
   reciprocal-multiply reduction (CompressionStream.cpp:101-106, 123-124)
   equals `h % N` for every 32-bit h at the default N = 262,143,977, and at
   99,999,989, 52,428,767 and 999,983. It does NOT hold at 53 of the 100
   smaller primes OptimizeHashsize tries (Crinkler.cpp:316-319), nor at
   67,108,859: there, 1 to 8 of the 2^32 hash values get a quotient one too
   large, so the compressor keys that context as (h % N - N) mod 2^32
   while the decoder's `div` keys it h % N. Those keys only meet the tiny
   table's exact compare, so the compressor would separate two contexts
   the decoder merges: a possible encoder/decoder mismatch in Crinkler
   itself, at a rate of at most 2e-9 of hash values. Our port uses `%` on
   both sides and is not affected.
4. The part-termination parity in the asm (`or al,[esi]; jpo`). It is
   ported from ModelList.cpp, not from the asm.
5. Bit-identity of whole packed files with real Crinkler output. That
   needs Crinkler: our model sets come from our float64 estimator, and
   the container is ours.

## 3. Optimised for Python, in our currencies

### (a) Typed

**How it was built** (`build_typed.py`):

- The program is the build of record's (make_typed's TYPED) with `d`
  replaced:
  - the line check, the self-dump, the data loop and the r.py
    definitions slice `a[39:END]` all stay;
  - the reader calls `d(x, N2, r.py)` unchanged, so r.py's contract is
    unchanged;
  - only END moves, by the length of `d`.
- The payload is reader_lite_v1.py with N2 and B2 baked (4,564 B,
  code y98y), primed with the program's own text.
- The parameters of each model k sit inside `d` as one decimal literal
  `z = [M_k*16 + w_k, ...]`: M_k is an integer byte mask over the
  history, w_k the weight. Hex is refused by the typed subset (audit:
  plain decimal literals only). `h & q >> 4` is the mask and `q & 15` the
  weight. They are typed, and counted in a.py's characters.
- The parameters come from Crinkler's search (fam.search =
  ApproximateModels4k + OptimizeWeights over any candidate list). Its
  objective is coded bits plus the parameters' text at 300/64 bits per
  character. A data character carries 5 bits, and 4 check glyphs ride on
  each 60 digits.
- The rest is make_typed's own logic, in our copy:
  - the C fixed point;
  - 60 base-32 digits + 4 check glyphs per data line;
  - make_typed.audit (line ≤ 72, no capitals, …);
  - the program run as a.py in a temp dir on the known-answer stdin (a
    doubled line, a typo, group spaces, a trailing space): transcript,
    exit 0, r.py == definitions + reader.
  - Every row below passed all of it.
- The control row `cm2` reproduces the build of record exactly (3,895,
  G 2,877, slice a[39:608]).

| variant | what | a.py chars (d) | payload bits | G digits | data lines | data chars | **typed** | vs 3,895 | split: text / data |
|---|---|---|---|---|---|---|---|---|---|
| cm2 | the record (control) | 826 (390) | 14,381 | 2,877 | 48 | 3,069 | **3,895** | 0 | |
| crk | Crinkler's model for Python: dict contexts, masks searched over the last 8 bytes, weights 0..9, x4 boost, base 10, halving rule; SLOW | 853 (417) | 14,254 | 2,851 | 48 | 3,043 | **3,896** | +1 | +27 / -26 |
| crk-vs | the same, VERYSLOW (width 3) | 859 (423) | 14,161 | 2,833 | 48 | 3,025 | 3,884 | -11 | +33 / -44 |
| crk1k | Crinkler's 1k counter rule (c + 1) >> 1, masks up to 24 bytes | 846 (410) | 14,224 | 2,845 | 48 | 3,037 | 3,883 | -12 | +20 / -32 |
| crk1k-vs | the same, VERYSLOW | 852 (416) | 14,147 | 2,830 | 48 | 3,022 | 3,874 | -21 | +26 / -47 |
| crkhash | Crinkler's hashed table with a modified hash: CRC32C into 99,999,989 slots of saturating 8-bit counters, mask bytes typed (five changes from Crinkler, below) | 1,036 (600) | 14,134 | 2,827 | 48 | 3,019 | 4,055 | +160 | +210 / -50 |
| sparse | cm2 + searched masks (last 8 bytes + orders 9..24) + weights 0..12 | 857 (421) | 14,111 | 2,823 | 48 | 3,015 | 3,872 | -23 | +31 / -54 |
| sparse-cs | the same, search started from cm2's 9 orders | 857 (421) | 14,139 | 2,828 | 48 | 3,020 | 3,877 | -18 | +31 / -49 |
| **sparse-vs** | the same, VERYSLOW | 861 (425) | 14,069 | 2,814 | 47 | 3,002 | **3,863** | **-32** | +35 / -67 |
| cm2+k1 | cm2 with Crinkler's 1k counter rule only | 814 (378) | 14,612 | 2,923 | 49 | 3,119 | 3,933 | +38 | -12 / +50 |
| cm2+crkrule | cm2 with Crinkler's 4k halving rule only | 821 (385) | 14,655 | 2,931 | 49 | 3,127 | 3,948 | +53 | -5 / +58 |
| cm2+boost4 | cm2 with Crinkler's x4 boost only | 828 (392) | 14,660 | 2,932 | 49 | 3,128 | 3,956 | +61 | +2 / +59 |
| cm2+base10 | cm2 with Crinkler's base 10 only | 827 (391) | 15,129 | 3,026 | 51 | 3,230 | 4,057 | +162 | +1 / +161 |
| cm2+k1+boost4 | both | 816 (380) | 15,076 | 3,016 | 51 | 3,220 | 4,036 | +141 | -10 / +151 |

(a.py chars do not count newlines, as in the record. "split" = a.py
characters minus 826 / data characters minus 3,069.)

**`crkhash` is not Crinkler's hash as it is.** It differs in five ways,
each of which the build history shows helping it (15,593 → 14,134 bits,
MEASURED, `build_typed.py`'s docstring):

1. it hashes the partial byte u last; Crinkler hashes it first
   (Model.cpp:27-28);
2. its seed is (mask byte × 16 + weight) << 8; Crinkler's is the remaining
   weight-mask bits OR the mask byte (CompressionStream.cpp:51-60);
3. it has 99,999,989 slots, not 262,143,977;
4. its counters saturate (Crinkler's /SATURATE); Crinkler's default wraps;
5. it codes with cm2's big-integer rANS, not Crinkler's 32-bit coder.

A typed loader with Crinkler's exact hash would type more than 4,055, so
the +160 is a lower bound and the conclusion is conservative.

**Out of sample** (`oos.py`, MEASURED after the refuter's round, first
8 KB of three files the search never saw, no primer, bytes of the coded
integer):

| file | cm2 v2 | sparse-vs | crk |
|---|---|---|---|
| R2-FORMAT.md (prose) | 3,075 | 3,102 (+27) | 3,090 (+15) |
| TYPED-STREAM.md (prose) | 2,554 | 2,743 (+189) | 2,770 (+216) |
| r3/receiver.py (code) | 3,071 | 3,067 (-4) | 3,078 (+7) |

The payload-tuned z loses on prose and ties on code. The -32 characters
of sparse-vs are only there if z is searched again (about 60 s) whenever
the reader changes. The refuter's own run (another primer) gave the same
picture: +29, +182, -3.

**Reference points, not typed loaders.**

- Crinkler as transliterated, with its own 32-bit coder and header, codes
  the payload in 1,745 B = 13,960 bits (16 models, SLOW). With VERYSLOW
  and 100 hash tries it codes 1,742 B. Its 1k mode codes it in 1,773 B.
- Typing those would cost the CRC/table text of `crkhash` plus Crinkler's
  arithmetic decoder with a bit reader. The 13,960 bits would save 174
  bits against `crkhash`'s 14,134, about 37 typed characters.
  **ESTIMATE:** the decoder and bit reader take at least 60 characters.
  Not built.
- Without a fee on the parameters, the search reaches 14,027 bits (crk,
  21 models) and 13,916 bits (cm2 + sparse, 21 models). The masks then
  cost 246-252 characters instead of 66-78: a loss of about 140 typed
  characters (`search.jsonl`).
- cm2's 9 masks with searched weights only: 14,354 bits, 27 fewer
  (search estimate, not built). The first round priced the weights at
  138 characters of z literals. Typed as a short weight string they
  would cost about 20-25 characters (ESTIMATE). 27 bits are about 6 data
  characters, so it still loses, by about 15-20.

**What would change in a.py.** Exactly the body of `d`:

- `z` becomes a list of literals;
- `h&q` becomes `h&q>>4`;
- `enumerate(g)` becomes `zip(z,g)` and `<<q` becomes `<<(q&15)`;
- for the crk rows, `1+sum` becomes `10+sum`, `+(c[1-y]<1)` becomes
  `+2*(c[1-y]<1)`, and the update becomes `c[1-y]>>(c[1-y]>1)` (or
  `c[1-y]+1>>1`).

The program's structure, the reader and the r.py contract are unchanged
(the slice end moves from 608 to 628-644; crkhash 828).

### (b) R2

`r2.py`:

- Each variant's own `d` (z unchanged) codes the page bundle (b.py,
  50,533 B) and the R3 monolith with the archival layer.
  - The monolith is `receiver_arch.minified-g.py`, 24,460 B, as
    measure_arch.py builds it; cm2 gives 10,599 B on it, the record.
- Each is primed with the variant's own r.py.
- It decodes with the `d` its a.py defines; all round trips are exact.
- R2 page = 5,304 B.

| variant | bundle B | pages | monolith B | pages | decode bundle |
|---|---|---|---|---|---|
| cm2 (record) | **14,472** | 3 | **10,599** | 2 | 12.3 s |
| crk | 14,943 | 3 | 10,527 | 2 | 13.5 s |
| crk-vs | 15,106 | 3 | 10,550 | 2 | 12.4 s |
| crk1k | 14,954 | 3 | 10,518 | 2 | 12.5 s |
| crk1k-vs | 15,110 | 3 | 10,527 | 2 | 13.2 s |
| crkhash | 15,203 | 3 | 10,507 | 2 | 88.4 s |
| sparse | 14,979 | 3 | 10,403 | 2 | 12.7 s |
| sparse-cs | 14,808 | 3 | 10,430 | 2 | 13.4 s |
| sparse-vs | 14,964 | 3 | 10,432 | 2 | 13.1 s |
| cm2+k1 | 14,758 | 3 | 10,850 | **3** | 13.2 s |
| cm2+crkrule | 14,790 | 3 | 10,888 | **3** | 13.1 s |
| cm2+boost4 | 14,765 | 3 | 10,932 | **3** | 13.7 s |
| cm2+base10 | 14,840 | 3 | 10,776 | **3** | 12.9 s |
| *z searched on the input itself (`--retune`, 21 models, no fee)* | | | | | |
| sparse + own z | 14,537 | 3 | 10,200 | 2 | 16.3 s |
| crk + own z | 14,657 | 3 | 10,240 | 2 | 17.2 s |
| crk1k + own z | 14,654 | 3 | 10,239 | 2 | 16.3 s |
| *Crinkler as transliterated (own search, 32-bit coder, primer = the record's r.py)* | | | | | |
| crk_enc SLOW, packed bytes | 14,642 | 3 | 10,289 | 2 | 11.1 s |
| crk_enc SLOW, with its 37-byte container (masks, weight mask, hash size) | 14,679 | 3 | 10,326 | 2 | |

The `--retune` and own-search rows are not counted the way the typed rows
are. The `--retune` rows leave out z. The own-search rows would also need
Crinkler's 32-bit arithmetic decoder in r.py, which is not counted. Page
counts do not change either way.

- **The bundle** is half prose (R2-FORMAT.md as its docstring) and half
  readable reader code. Every Crinkler member loses on it, even with
  masks searched on the bundle itself. cm2's nine contiguous orders up to
  16 bytes are the more robust prior there.
- **The monolith** (minified code) is where searched sparse masks help:
  - -196 B with the typed payload's masks;
  - -399 B (3.8 %) with its own.
- A per-input z costs 249-305 characters of literals in the reader
  (`d(x,N2,r,[...])`).
  - **ESTIMATE:** at the payload's 3.15 bits per character that is about
    165-200 typed characters, to save 399 B of R2 that changes no page
    count.

### (c) Archive

`bench_arch.py` uses r3/arch/bench.py's method in our copy: encode timed,
decode in a fresh process (timed, peak RSS), byte-exact. A full T1 decode
of the transliteration would take about 33 min (EXTRAPOLATION from 205
µs/byte), over the 30-minute line, so it is measured on 1 MB and 2 MB
prefixes. crkpy decodes T1 in 11-14 min, so after the refuter's round
it is measured on the whole of T1. (The first round extrapolated it too,
which the task's rule did not allow.)

`dec_crkpy.py` / `enc_crkpy.py` are Crinkler's model optimised for
Python as an archival decoder (pure Python, no imports, fixed memory):

- the CRC32C chain becomes one big-integer multiply-and-modulo of the
  masked history (deterministic integer arithmetic, no table, no
  `hash()`);
- masks over up to 24 bytes;
- saturating 8-bit counters in one bytearray of 262,143,977 slot pairs
  (Crinkler's default table);
- Crinkler's 32-bit coder;
- the model list in the container.

| codec | 1 MB coded | ratio | 2 MB coded | decode µs/B | peak RSS | notes |
|---|---|---|---|---|---|---|
| strong2 (record's winner) | 245,555 | 0.2456 | 470,169 (record) | 83.7 | 1,360 MB | 1 MB re-measured here, bytes identical to the record |
| cm1 k24 | 252,368 | 0.2524 | 487,393 | 64.8 (record) | 107 MB (record) | record, not re-measured |
| cm2 exact dict + range coder (cm2xrc) | 261,936 | 0.2619 | 502,747 (record) | 54.7 | 5,653 MB | 1 MB re-measured here |
| Crinkler transliterated, wrapping | 270,864 | 0.2709 | — | 199.0 | 1,540 MB | SLOW on the first 64 KB, 21 models |
| Crinkler transliterated, /SATURATE | 269,185 | 0.2692 | 526,304 | 205.5 / 205.7 | 1,540 / 1,560 MB | 21 models |
| crkpy, the /SATURATE row's models | **269,243** | 0.2692 | **526,384** | 92.0 / 87.7 | 520 / 523 MB | the same model at 2.2-2.3× the speed and a third of the memory |
| crkpy, its own search (fam, 24-byte candidates) | 277,167 | 0.2772 | — | 76.4 | 520 MB | picks masks over 12 and 14 bytes (see below) |
| crkpy, own search, estimator saturating at 255 (`crkpy-sat`) | 279,607 | 0.2796 | — | 74.8 | 520 MB | after the refuter's round; picks a 14-byte mask at weight 7 |
| crkpy, own search, Crinkler's 256 candidates (`crkpy-8`) | 268,429 | 0.2684 | — | 74.4 | 520 MB | after the refuter's round |
| crkpy, own search, 256 candidates + saturating estimator (`crkpy-sat8`) | **268,119** | 0.2681 | — | 70.5 | 520 MB | after the refuter's round; the best set found here, 17 models |
| crkpy, own search, 67,108,859-slot table | 314,668 | 0.3147 | — | 74.0 | 148 MB | collisions (ESTIMATE: 17 models over 8 M bits give tens of millions of contexts, against 67 M slots without check bits) |

**Why crkpy's own search picked a worse set.** The first round blamed
the search's estimator for not saturating its counters, without testing
that. The 2 × 2 above tests it (1 MB of T1, MEASURED):

| candidates | estimator unbounded | estimator saturating |
|---|---|---|
| 24-byte list (256 subsets + orders 9..24) | 277,167 | 279,607 |
| Crinkler's 256 subsets of the last 8 bytes | 268,429 | 268,119 |

Saturation gains 310 B with Crinkler's candidates and loses 2,440 B
with the long ones. The cause is the long masks: on the 64 KB
sample the search takes contexts over 12 to 14 bytes, and on 1 MB they
cost 8.7-11.5 KB. Whether that is the sample over-fitting or long contexts
crowding the table without check bits is not separated.

**T1 (MEASURED after the refuter's round).** crkpy on the whole tar
(9,523,200 B), encode and then decode in a fresh process, byte-exact:

| model set | T1 bytes | vs strong2 | archive pages | encode | decode | peak RSS |
|---|---|---|---|---|---|---|
| `crkpy-sat8`'s (searched on 64 KB, the best at 1 MB) | **1,918,411** | +16.4 % | **18** | 729 s | 636 s (66.8 µs/B) | 540 MB |
| the transliteration's /SATURATE set (first round) | 1,944,034 | +17.9 % | **18** | 868 s | 838 s (88.0 µs/B) | 540 MB |

(The refuter's encode of the second row gave the same 1,944,034 B.)
Holo's planner (`pages.py`) fits at most 1,876,247 B in 17 pages. The
first round's two extrapolations (1,845,800 B = 17 pages for a constant
ratio, 1,931,400 B = 18 pages for a growing gap) both fall short of what
was measured. The "17" reading is wrong. Against strong2 the gap grows
with size: +9.2 % at 1 MB, +11.9 % at 2 MB, +16.4 % at 9.5 MB with the
best set.

- The record's T1 rows are:
  - strong2: 1,648,648 B = 15 pages;
  - cm1: 1,738,544 = 16;
  - cm2 exact: 1,761,165 = 16;
  - xz: 2,149,928 = 20.
- Decode of T1:
  - crkpy: 10.6-14.0 min in 540 MB (MEASURED, load 6-15 on 10 cores);
  - the transliteration: about 33 min in 1.56 GB (EXTRAPOLATION, linear
    from the 2 MB rate);
  - strong2: 13.1 min in 1.36 GB (record, measured).
- The leaves:
  - The archive pages are 18 against strong2's 15 (+3 pages, MEASURED).
  - The decoder's region alone, minified-g and cm2 v2 primed with r.py
    (MEASURED, `measure.py`'s method on the region only):
    - crkpy: 52 lines, 417 B;
    - strong2: 86 lines, 1,080 B;
    - cm1 k24: 73 lines, 937 B.
  - **ESTIMATE:** swapping strong2 for crkpy in the monolith would free
    about 660 B of R2 (10,599 → about 9,940 B). That is still 2 pages, so
    nothing offsets the 3 extra archive pages.

### (d) Speed

Decode µs per byte, this interpreter, this session (MEASURED unless
marked).

| decoder | typed payload (4,564 B, primer ~0.85-1.1 KB) | 1 MB of T1 |
|---|---|---|
| cm2 v2 (typed d, big-integer rANS) | 73.9 (refuter: 77.9) | ≈ 2,460 (EXTRAPOLATION: 41 min; fit below) |
| cm2 linear variant (cm2xrc: exact dict, 32-bit range coder) | — | 54.7 (5.65 GB) |
| strong2 (the archive's codec) | — | 83.7 (1.36 GB) |
| Crinkler family in Python (crk / crk-vs / crk1k / sparse …) | 68.8-73.4 (refuter: crk 70.6, sparse-vs 74.6) | — (dict memory: about 5.6 GB per MB, as cm2xrc) |
| crkpy (archival form) | — | 70.5-92.0 (whole T1: 66.8-88.0) |
| crkhash (Crinkler's hashed table, modified hash, typed) | 336.2 (refuter: 332.0) | — |
| Crinkler transliterated (crk_dec, 4k) | 201.8 (incl. the 500 MB table clear) | 199.0-205.5 |
| Crinkler transliterated (crk_dec, 1k) | 55.3 | — |

- **On the typed payload** the coder is not the cost: x has 14 kbit.
  Every dict variant runs at cm2's speed, about 0.33 s for the reader.
  The few per cent between them are inside the spread between two
  sessions on a machine under load 7-9 (best of 3 each), and the Crinkler
  family runs 7 models against cm2's 9. "Equivalent" is shown; "faster"
  is not.
- **On 1 MB**, cm2 v2's big integer reaches 2 Mbit, and every bit costs a
  divmod over it.
  - MEASURED on T1 prefixes (encode / decode): 25 KB 4.3 / 3.3 s
    (132 µs/B); 50 KB 13.6 / 10.1 s (201); 100 KB 47.5 / 33.5 s (335);
    200 KB 163 / 113 s (566).
  - Least squares fit: t ≈ 9.2e-5 n + 2.37e-9 n² s, which gives about
    2,460 s at 1 MB and about 60 h for T1 (EXTRAPOLATION).
- **What crkpy shows about speed:** the transliteration's cost is the
  CRC32C chain (up to 9 table steps per model per bit). One big-integer
  multiply-modulo per model per bit brings it to 2.2-2.3× faster, with
  the same bytes.

## 4. Transfer: each Crinkler idea in cm2

| idea | hybrid | typed | R2 bundle / monolith | verdict |
|---|---|---|---|---|
| searched sparse masks + weights (the model search typed as data) | sparse, sparse-cs, sparse-vs | **-18 to -32** | +336 to +507 / -167 to -196 B, pages unchanged | pays at the typed rung only; the masks fit the text they were searched on |
| the same, searched per input | sparse + own z | (reader +249-286 chars of z) | +65 / -399 B | not worth its typed cost |
| Crinkler's 4k counter rule (halving) | cm2+crkrule | +53 | +318 / +289 B (monolith → 3 pages) | does not transfer |
| Crinkler's 1k counter rule (c + 1) >> 1 | cm2+k1 | +38 | +286 / +251 B (→ 3 pages) | does not transfer alone; inside the Crinkler family it beats the halving rule by 10-13 |
| x4 boost | cm2+boost4 | +61 | +293 / +333 B (→ 3 pages) | does not transfer |
| base probability 10 | cm2+base10 | +162 | +368 / +177 B (→ 3 pages) | does not transfer |
| searched weights on cm2's 9 orders only | (search estimate) | -27 bits (about 6 characters) for about 20-25 characters of weights (ESTIMATE) | — | does not pay |
| hashed fixed table (Crinkler's memory model) | crkhash; crkpy | +160 | bundle +731 B | costs text and speed in Python; bounds memory at archive scale (520 MB vs cm2xrc's 5.6 GB per MB) |

**Why each knob fails alone:** cm2's weights (order index 0..8) were tuned
together with its own counter rule, boost and base. Changing one knob
detunes the others. Crinkler's knobs only work in Crinkler's searched
weights.

## The refuter's findings and what was done

An Opus refuter re-ran the headline numbers on the same interpreter and
reproduced all of them. It found no blockers, one major and ten minors.

| # | finding | what was done |
|---|---|---|
| major | crkpy's T1 decode takes about 14 min, under the task's 30-minute line, so T1 had to be measured, not extrapolated. Its own encode gave 1,944,034 B = 18 pages, outside the extrapolated 1.85-1.93 MB. | Measured, with encode and decode and a byte-exact round trip: 1,944,034 B (the refuter's number), 838 s decode, 540 MB. Then a better model set: 1,918,411 B, 636 s. Both are 18 pages (17 hold at most 1,876,247 B). The answer and the tables now say 18, MEASURED; the "17" reading is withdrawn. 3(c). |
| minor | `crkhash` was called "Crinkler as it is" but differs from Crinkler in five ways, all in its favour. | Renamed "Crinkler's hashed table with a modified hash"; the five changes are listed in 3(a); +160 is called a lower bound. |
| minor | `fam.search`'s last weight optimisation kept the searched weights; upstream resets them to the byte count first. Undeclared. | Fixed to upstream's step (`CRK_FINAL_KEEP=1` restores the old one). All eight searched typed variants were rebuilt: the same z to the literal and the same typed counts, so nothing moves. Declared in section 2. |
| minor | The R2 "own search" figures leave out the 37-byte container and the decoder; the `--retune` rows leave out z. | The container sizes (14,679 / 10,326) are in the headline table and in 3(b), with the uncounted decoder named. |
| minor | The typed speed claim "69-71 vs 74" is a best of 3 under load; the refuter got cm2 77.9, crk 70.6. "Faster" is not shown. | Both sessions' numbers are in the tables; the text says "equivalent", not "faster", and names the 7-vs-9 models. |
| minor | The cause given for crkpy's own search picking a worse set (the estimator does not saturate) was untested. | Tested with a 2 × 2 at 1 MB (3(c)). The hypothesis is wrong: saturation gains 310 B with Crinkler's candidates and loses 2,440 B with the long ones. The long masks over 12-14 bytes cost 8.7-11.5 KB. With Crinkler's 256 candidates the search finds 268,119 B, the best set of the study, which was then measured on T1. |
| minor | Two "could not verify" items can be settled (the CRC polynomial; the reciprocal reduction at the default size). | Settled in section 2. The CRC table gives the CRC-32C check value. The reciprocal reduction holds at the default size, but fails for 1-8 of 2^32 hash values at 53 of the 100 sizes Crinkler's hash-size search tries: a possible, very rare, mismatch inside Crinkler itself, which does not affect this port. |
| minor | "Not better in bytes" at R2 overstates; every Crinkler-family variant makes the monolith smaller. | The R2 summary now says the bundle grows and the monolith shrinks. |
| minor | The weights-only estimate charged 138 characters of z; typed as a short string they would cost about 20-25. | Re-priced (ESTIMATE): it still loses, by about 15-20 characters. |
| minor | Out of sample the payload-tuned z loses on prose and ties on code. | Re-measured (`oos.py`) for sparse-vs and crk; the table is in 3(a). The -32 holds only if z is searched again whenever the reader changes. |
| minor | The commands named `env/bin/python` from the worktree root, but this worktree has no `env/`. | The commands and the header name `env/bin/python`. |

What is still not verified: bit-identity with real Crinkler output, the
assembly's bit-reader start and termination, and that `crc32` does no
inversion. All three need Crinkler or the hardware instruction to run.

## Files

| file | what |
|---|---|
| `crk_dec.py` | the transliterated decompressor, 4k + 1k, pure Python, no imports (ALTERED VERSION) |
| `crk_enc.py` | the transliterated compressor: coders, estimator, ApproximateModels4k/OptimizeWeights, OptimizeHashsize, 1k search (ALTERED VERSION) |
| `fam.py` | the Crinkler family for Python and its cm2 hybrids: per-mask predictions, Crinkler's search over any candidate list, the exact coder |
| `build_typed.py` | typed loaders through make_typed's fixed point, audit and a.py proof |
| `r2.py` | the R2 currency (and `--retune`) |
| `dec_crkpy.py`, `enc_crkpy.py` | Crinkler's model optimised for Python as an archival codec (ALTERED VERSION) |
| `bench_arch.py` | the archive currency on T1 prefixes |
| `run_faithful.py` | one input through the transliteration, round trip |
| `search_fam.py` | the search experiments of the first round (rows in search.jsonl) |
| `speed.py` | decode speeds; cm2 v2's quadratic fit |
| `test_roundtrip.py` | scan-free round trips (4 s) |
| `oos.py` | a typed variant's payload-tuned z against cm2 v2 on files the search never saw |
| `common.py` | the inputs and counters from the repository |

**How to run** (from the worktree root, with PY =
`env/bin/python`, the main checkout's
free-threaded 3.14.8: this worktree has no `env/`; outputs go to the
gitignored `bootstrap/build/priorart/crinkler/`, or to `$CRK_OUT`):

```
$PY bootstrap/priorart/crinkler/build_typed.py cm2 crk crk-vs crk1k crk1k-vs crkhash sparse sparse-cs sparse-vs cm2+k1 cm2+crkrule cm2+boost4 cm2+base10 cm2+k1+boost4
$PY bootstrap/priorart/crinkler/r2.py cm2 crk ... ; ... r2.py sparse crk crk1k --retune
$PY bootstrap/priorart/crinkler/run_faithful.py payload|bundle|monolith|empty|one|random:4096|1k:payload [MODE] [HASHTRIES]
$PY bootstrap/priorart/crinkler/bench_arch.py crk|crk-sat|crkpy|crkpy-sat|crkpy-8|crkpy-sat8|strong2|cm2xrc N [SAMPLE|reuse:CODEC/N/SAMPLE]
    e.g. the T1 row: bench_arch.py crkpy 9523200 reuse:crkpy-sat8/1000000/65536
$PY bootstrap/priorart/crinkler/speed.py typed ; speed.py cm2v2 N ...
$PY bootstrap/priorart/crinkler/oos.py [VARIANT [N]]
PYTHONPATH=src $PY bootstrap/r3/arch/pages.py BYTES        (archive pages, holo's planner)
CRK_FINAL_KEEP=1 ...   the first round's search (keeps the searched weights in the last step)
```

**Derived outputs:**

- the jsonl logs: typed, r2, faithful, arch, speed, search, oos;
- `final_reset/` (the typed rebuilds with upstream's last search step);
- `typed/VARIANT/{a.py,data.txt,r.py,build.json}`;
- `coded/`, `logs/`.

## Licence of the upstream (zlib), kept with the altered versions

```
Crinkler - compressing linker for Windows
Copyright (c) 2005-2026 Aske Simon Christensen and Rune L. H. Stubbe.

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.
2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.
3. This notice may not be removed or altered from any source distribution.
```

The files `crk_dec.py`, `crk_enc.py`, `dec_crkpy.py` and `enc_crkpy.py`
are altered versions in the sense of clause 2. `fam.py` and
`build_typed.py` carry Crinkler's search and model ideas re-expressed for
cm2's typed rung.
