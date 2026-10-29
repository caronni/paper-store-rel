# bootstrap/priorart/zpaq: ZPAQ as the archive decoder (2026-10-20, machine 1)

Prior-art study, simulation and harness only: nothing printed, nothing
promoted, no tracked file outside this directory touched. The upstream
source (libzpaq/zpaq 7.15 by Matt Mahoney, public domain under the
Unlicense; divsufsort by Yuta Mori, MIT, not used here) was read and never
built or run. Upstream pointer (recorded 2026-10-27, the owner's ask):
the 7.15 release archive https://mattmahoney.net/dc/zpaq715.zip (index
https://mattmahoney.net/dc/zpaq.html); no copy of the archive is kept in the
project, and its sha256 is owed until one is fetched on the owner's go. Every number is labelled MEASURED (this session, machine 1,
`env/bin/python`, CPython 3.14.8 free-threaded,
the interpreter the arch record used), ESTIMATE or EXTRAPOLATION.
Derived outputs are in `bootstrap/build/priorart/zpaq/` (bench.jsonl,
r2.jsonl, typed.jsonl, summary.json, coded/, forms/, logs/).

## The answer

**No: ZPAQ's structure is worse for us than strong2 on R2 bytes and on
decode time, and equal on archive pages. The flexibility it buys can be had
more cheaply without a VM.**

**R2 bytes: worse.** One more R2 page (MEASURED, measure_r2.py's method).

| decoder in the monolith | added over the receiver (cm2 B) | monolith (cm2 B) | R2 pages |
|---|---|---|---|
| strong2 | 1,183 | 10,598 | 2 |
| ZPAQ, our translating decoder | 2,889 | 12,304 | 3 |
| ZPAQ, smallest plain interpreter we could write | 2,030 | 11,445 | 3 |

- The receiver leaves 1,193 B spare under the 2-page line (10,608 B).
- No ZPAQ decoder we wrote fits there. Nine component types and a
  virtual machine are more code than one fixed model.

**Archive pages: equal.** T1 stays at 15 pages (MEASURED).

- The strong ZPAQ configs compress T1 better than strong2:
  - Mahoney's max.cfg: 1,629,544 B, −1.2 %;
  - libzpaq's level 5: 1,628,217 B, −1.2 %;
  - our configs: `ours` 1,610,701 B (−2.3 %), `ours2` 1,585,132 B
    (−3.9 %), `ours3` 1,582,375 B (−4.0 %).
- 14 pages needs ≤ 1,544,395 B, 6.3 % under strong2. None reaches it.
- The gain comes from the MODEL, not from ZPAQ's structure:
  - longer contexts (orders 12-24);
  - a second match model;
  - more mixing and SSE.
  A fixed strong2 grown the same way would gain the same.
  ESTIMATE: not measured.
- libzpaq's faster levels are worse than strong2 on T1:
  - level 4: 16 pages;
  - level 3 (BWT): 18;
  - mid: 16;
  - min: 19.

**Decode time: worse.** On T1, pure Python, same interpreter, same loaded
machine (MEASURED):

| decoder | decode time | vs strong2 |
|---|---|---|
| strong2 | 837 s (14 min) | |
| max | 1,287 s (21 min) | 1.5× |
| ours | 1,610 s (27 min) | 1.9× |
| level 5 | 1,722 s (29 min) | 2.1× |
| ours2 | 1,904 s (32 min) | 2.3× |
| ours3 | 2,079 s (35 min) | 2.5× |

- These are configs chosen for ratio. A config cut back for speed does
  not close the gap: the refuter took max and replaced its sparse ICMs
  (and in a second probe also the order-6 ISSE and the word ICM/ISSE) by
  constants. On 1 MB of T1 that gave 244,559 B in 121.7 s and 255,184 B
  in 108.3 s, against strong2's 245,555 B in 82.7 s (the refuter's
  MEASURED, same interpreter, not re-run here). At strong2's ratio ZPAQ
  stays at about 1.45× or slower. A config rebuilt without the constant
  placeholders might narrow that a little.
- That is with the model translated to straight-line Python. A plain
  interpreter is about 2.1× slower again (MEASURED on 100 KB). For max
  that would be about 45 min for T1 (EXTRAPOLATION).
- Memory: every library config and Mahoney config uses less than
  strong2's 1.36 GB (97-419 MB). Our configs use 1.39-2.23 GB: tables
  sized for T1.

**Future flexibility: yes, but only inside ZPAQ's vocabulary.**

- What it buys:
  - A new model is a new header, 28-373 B per block here, decoded by the
    unchanged R2 interpreter.
  - Shown here: the one `zp_dec.py` decodes every row. Going from max to
    `ours2` (−2.7 % on T1) changed only the model header (198 → 323 B).
- What it does not buy: a model with a different mechanism (another mixer,
  counter or SSE, a 2-layer network, anything the nine component types
  cannot express) still needs new R2 code.
- What it costs: a third R2 page now, and 1.5-2.5× the decode time at
  equal or better ratio.
- What it is worth to us is small. The four-rung ladder is bound into
  every volume (docs/BOOTSTRAP-DESIGN.md, "The question"), so every new
  volume prints its own R2 pages anyway. A stronger model later, a
  strong3, can simply go into the next volume's R2 pages. Keeping the R2
  pages unchanged only matters inside one volume, and one volume has one
  archive model. The same holds for the exec route below.

**The cheaper route to the same property:** ship the decoder itself in the
archive. Measured and estimated:

- The finder's machine runs Python, so the archive's first bytes can be a
  length and the decoder's source. The monolith runs it and calls it on
  the rest: a 4-line `unz` plus a 2-line, minifier-safe spelling of exec.
- R2 cost: 214 B (MEASURED). That is 2 R2 pages with 979 B spare under the
  line, against 10 B spare for strong2 measured the same way.
- Archive cost: the decoder's source.
  - strong2 minified is 2,133 B (MEASURED), giving a container of
    1,650,797 B, still 15 pages (ESTIMATE from the measured page limit).
  - zp_dec + ours would be about 1,617,200 B, 15 pages (ESTIMATE).
- This is strictly more general than ZPAQ: any Python, any mechanism,
  ZPAQ itself included. The price is that the decoder is no longer
  printed in R2's plain sight but in the archive. It is as protected
  there as the data it decodes.

**Typed stage: no.** Characters counted as the record counts them (a.py's
826: newlines not counted).

- **The decoder.** A ZPAQ interpreter in place of a.py's cm2 decoder:
  - our hand-compacted interpreter is 4,854 characters (MEASURED, all nine
    components and the machine, no post-processor);
  - it cannot yet train on a primer; that would add about 80 characters
    (ESTIMATE, §3.3);
  - d() in a.py is 423 (MEASURED, newlines not counted; the Crinkler
    study's `d_chars` 390-391 counts a narrower region of the same
    function — two scopes, not two measurements);
  - so about +4,510 typed characters.
- **The reader payload** in a ZPAQ config:
  - primed with a.py, as cm2 v2 is (non-standard for ZPAQ): 2,828 digits
    under `ours3`, 2,831 under `ours2`, 2,834 under `ours`, 2,840 under
    max, 2,852 under level 4, 2,920 under mid. cm2 v2 needs 2,877 (all
    MEASURED). The best ZPAQ payload saves 49 digits.
  - unprimed: 3,063-3,136 for every config but min.
  - The model's header must be typed too: 114 digits (mid) to 597
    (`ours3`). With the header counted, level 4 and mid are the cheapest
    data.
- **Total:** about 8,560 (level 4) to 8,990 (`ours3`) typed characters
  against today's 3,895 (ESTIMATE).

## Headline table

T1 = src/holo + docs + CLAUDE.md as ustar, 9,523,200 B, 321 files. All
MEASURED in this session, every T1 row round-tripped byte-exact.

**Load.** machine 1 was shared (load average 9-10 on 10 cores), so times are
walls under load. Where CPU time was recorded it is within 1 % of the wall.
The record's strong2 decode was 785 s (its 13.1 min,
bootstrap/r3/arch/README.md); this session's 837 s is the same decoder on
a loaded machine.

**Column meanings.**

- *bytes*: the whole ZPAQ block: tag, model header, segment header, coded
  stream, trailer.
- *pages*: holo's planner on that size + 16 B of R3A1 container (+12 for
  strong2, as in the record).

| row | what | n | header B | T1 bytes | vs strong2 | archive pages | decode T1 | µs/B | peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| strong2 | the record's decoder (fixed model) | — | — | 1,648,648 | — | 15 | 837 s | 87.9 | 1,360 MB |
| min | Mahoney min.cfg | 2 | 28 | 2,077,402 | +26.0 % | 19 | 99 s | 10.4 | 97 MB |
| mid | Mahoney mid.cfg | 8 | 71 | 1,734,016 | +5.2 % | 16 | 447 s | 46.9 | 172 MB |
| max | Mahoney max.cfg | 22 | 198 | 1,629,544 | −1.2 % | 15 | 1,287 s | 135.2 | 307 MB |
| level 3 | libzpaq `x4,3ci1` (BWT + order 0-1, IBWT in PCOMP) | 2 | 31 + 123 PCOMP | 1,962,231 | +19.0 % | 18 | 108 s | 11.3 | 208 MB |
| level 4 | libzpaq `x4,0ci1,1,1,1,2awm` | 9 | 104 | 1,727,172 | +4.8 % | 16 | 485 s | 51.0 | 163 MB |
| level 5 | libzpaq level 5 (no period found in T1) | 25 | 296 | 1,628,217 | −1.2 % | 15 | 1,722 s | 180.8 | 419 MB |
| ours | max + order 6 + column model + T1-sized tables + order-2 SSE | 27 | 276 | **1,610,701** | **−2.3 %** | 15 | 1,610 s | 169.0 | 1,391 MB |
| ours2 | ours + order 12, a second match on order 16, the above-right byte | 30 | 323 | **1,585,132** | **−3.9 %** | 15 | 1,904 s | 199.9 | 1,694 MB |
| ours3 | ours2 + orders 16 and 24, a third match on order 32 | 33 | 373 | 1,582,375 | −4.0 % | 15 | 2,079 s | 218.3 | 2,233 MB |

**R2.**

- strong2 costs 1,183 B and stays at 2 pages.
- Every ZPAQ row is decoded by the same `zp_dec.py`: 2,889 B, 3 pages.
  The plain interpreter `zp_tiny.py` costs 2,030 B, also 3 pages.

**The page lines** (holo's planner, MEASURED): 15 pages hold ≤ 1,655,012 B
of container, 14 pages ≤ 1,544,395 B.

**The 1 MB proxies** (the first 1,000,000 B of T1, the configs sized for
T1, MEASURED):

| row | bytes | decode |
|---|---|---|
| strong2 | 245,555 | 88.2 s |
| max | 244,013 | 142.2 s |
| level 5 | 244,349 | 191.0 s |
| ours_v0 (first design) | 244,743 | 170.9 s |
| maxcol | 242,878 | |
| ours | 242,614 | |
| ours2 | 241,479 | |
| ours3 | 241,534 | |

In `bench.jsonl` the first 1 MB row named `ours` (244,743 B) is ours_v0
under its first name.

## 1. How ZPAQ works (read from the source)

Pointers are `libzpaq.cpp:LINE` and `libzpaq.h:LINE` in the 7.15 tree.

### 1.1 The level-2 block format

A ZPAQ stream is a sequence of independent blocks; each block carries its
own model.

| bytes | field | reference |
|---|---|---|
| 13 | optional locator tag `37 6B 53 74 A0 31 83 D3 8C B2 28 B0 D3`. `findBlock` scans for a rolling hash of tag + `zPQ`, so the reference decompressor needs it | `Compressor::writeTag` 2776, `Decompresser::findBlock` 2247 |
| 3 | `zPQ` | `Compressor::startBlock` 2841 |
| 1 | level: 1, or 2 when the block has no components. libzpaq writes 1 for every modeled block so that level-1 decoders still read it | 2850, 2265 |
| 1 | 1 = ZPAQL | 2266 |
| 2 | hsize, little-endian: the length of everything after these two bytes up to and including the HCOMP end byte | `ZPAQL::read` 887 |
| 5 | hh hm ph pm n: log2 sizes of H and M for HCOMP and for PCOMP; n = number of components | 896 |
| ... | n components, each a type byte and its arguments (`compsize[] = {0,2,3,2,3,4,6,6,3,5}`), then a 0 | 714, 899-910 |
| ... | HCOMP: ZPAQL bytecode, then a 0 | 912-926 |
| per segment | `01`, filename, `00`, comment, `00`, `00` (reserved), the arithmetic-coded stream, `00 00 00 00`, then `FD` + 20-byte SHA-1 or `FE` | `startSegment` 2871, `endSegment` 2947, `readSegmentEnd` 2348 |
| 1 | `FF` = end of block | `endBlock` 3000 |

The coded stream:

- **Coder.** A binary arithmetic coder over 32-bit `low`/`high`, MSB-first
  bytes (`Decoder::decode` 2104, `Encoder::encode` 2402). `low += (low == 0)`
  after each shift guarantees that four zero bytes never occur inside the
  stream, which is what lets `skip` (2158) find the segment end without
  decoding.
- **End of stream.** Before every byte an end-of-segment bit is coded with
  probability 0 (`decompress` 2127; cost ≈ 0). After it, 8 bits MSB first,
  each with p = 2·predict() + 1 out of 65,536.
- **The post-processor.** The first decoded byte(s) say whether there is one
  (`PostProcessor::write` 2195): `00` = none, or `01`, a 2-byte length and
  the PCOMP bytecode. The bytecode is itself compressed by the block's own
  model. The data that follows is then run byte by byte through PCOMP,
  and once more with 2^32 − 1 at the end.

### 1.2 The components (Predictor::init 1723, predict0 1854, update0 1954)

**Bits and contexts.**

- `c8` is the partial byte with a leading 1.
- `hmap4` is that partial byte split into nibbles.
- `p[i]` is component i's prediction in the stretched domain, an integer in
  −2048..2047 that stands for ln(p/(1−p))·64.

**Tables.**

- squash and stretch: `ssquasht` 1441, `stdt` 1613.
- dt[i] = 2^17/(2i+3)·2: 1308.
- dt2k[i] = 2048/i: 1272.
- The bit-history state table: `sns` 726, 253 states. Each state is a
  bounded pair (n0, n1) plus the last bit, and each entry gives
  (next if 0, next if 1, n0, n1).

**Hashed slots.** ICM and ISSE share `find` (2072). It looks up the
context hash (H[i] + 16·c8) once per nibble, in rows of 16 bytes:

- byte 0 is an 8-bit check;
- bytes 1..15 are the bit histories of the nibble's 15 partial states.

It tries 3 adjacent rows. On a miss it replaces the one with the lowest
priority, where the priority is the state in byte 1.

| type | args | state | predict | update |
|---|---|---|---|---|
| CONST 1 | c | none | (c−128)·4 | none |
| CM 2 | s, limit | 2^s × 32 bit: a 22-bit probability and a 10-bit count | cxt = (H[i] xor hmap4) mod 2^s; p = stretch(pr >> 17) | pr += (err·dt[count]) & −1024; count +1 up to 4·limit |
| ICM 3 | s | hash rows (16·2^(s+2) bytes) of bit histories; a 256-entry history → probability map | p = stretch(map[history] >> 8) | history ← next(history, y); map += (y·32767 − map>>8) >> 2 |
| MATCH 4 | s, b | a 2^s index of positions by H[i]; a 2^b history buffer; match length (≤ 255), offset, predicted bit | the predicted bit with strength 2048/len, 0 when there is no match | a mismatch ends the match; at a byte boundary it looks the context up and counts the match length backwards |
| AVG 5 | j, k, w | none | (p[j]·w + p[k]·(256−w)) >> 8 | none |
| MIX2 6 | s, j, k, rate, mask | 2^s 16-bit weights | w by (H[i] + (c8 & mask)); a weighted average of p[j], p[k] | w += (err·rate>>5)·(p[j]−p[k]) >> 13, clamped to 0..65535 |
| MIX 7 | s, j, m, rate, mask | 2^s × m 20-bit signed weights | a dot product of p[j..j+m−1] with the context's weights, >> 16, clamped | w += (err·rate>>4)·p >> 13, clamped to ±2^19 |
| ISSE 8 | s, j | hash rows as for ICM; 256 weight pairs | a bit history picks (w0, w1): p = (w0·p[j] + w1·64) >> 16 | both weights by the error; history ← next |
| SSE 9 | s, j, start, limit | 2^s × 32 probability/count cells | p[j] quantised to 32 steps and interpolated between neighbours; the context is H[i] + c8 | the nearer cell trained like CM |

The last component's squash(p) is the coded probability.

### 1.3 The ZPAQL machine (ZPAQL::execute 1041-1263; libzpaq.h 609-680)

**State.**

- 32-bit registers A B C D, a 1-bit flag F, 256 registers R0..R255;
- H: 2^hh 32-bit words; M: 2^hm bytes;
- B and C index M (`*B`, `*C`); D indexes H (`*D`).

**When it runs.**

- HCOMP runs once per byte, with the byte in A.
- Its outputs are H[0..n−1], the per-component contexts.
- Every value persists across calls.

**Opcodes.** The encoding is regular:

- 0-63: unary operations on one operand (X<>A, X++, X--, X!, X=0,
  X=R n), plus JT, JF, R=A n, JMP, HALT, OUT, HASH, HASHD;
- 64-119: X=Y, including Y = an immediate byte;
- 128-239: A op= Y for + − × / % & &~ | ^ << >> == < >;
- 255: LJ, a 16-bit absolute jump.

**Hashing.** HASH is A = (A + *B + 512)·773 and HASHD is
*D = (*D + A + 512)·773.

**Jumps.** Short jumps are relative to the next instruction.

**Swaps.** A swap with an M byte keeps A's high 24 bits: the XOR-swap on a `U8&`, libzpaq.h:1073.

### 1.4 What the method levels generate

**makeConfig** (libzpaq.cpp 6887-7517) turns a method string into ZPAQL
source. For example `x4,0ci1,1,1,1,2awm` reads as:

- block size 2^4 MiB, no preprocessing;
- an order-0 ICM, then ISSEs of orders 1, 2, 3, 4 and 6;
- a match model;
- a word model;
- a mixer.

**Context generation.**

- HCOMP keeps the history in M, filling backward.
- It keeps the position of each byte value's last occurrence in H[255+v].
- Every component's context comes from that history and those positions.

**compressBlock** (7543) expands the levels. The archiver (`zpaq.cpp`
2183-2186, 2427-2510) adds an estimated redundancy R (0..255) and
text/exe flags t, so that type = 4R + t:

- **level 1:** store, or LZ77 with bit-packed codes (a PCOMP does the decoding);
- **level 2:** LZ77 with a longer search;
- **level 3:** BWT + `ci1` for text or highly redundant data (the IBWT runs
  in PCOMP), else LZ77 + an order 0-1 CM;
- **level 4:** `ci1,1,1,1,2a` [+`w`] `m` for type < 900, else BWT;
- **level 5:** the long `w2c0,1010,255i1c256ci1,1,1,1,1,1,2a` + periodic
  contexts found by scanning the data + `c0,2,0,255i1c0,3,0,0,255i1c0,4,0,0,0,255i1mm16ts19t0`.

**The classic configs.** Compressor::startBlock(level) (2793-2832) carries
Mahoney's classic min.cfg, mid.cfg and max.cfg compiled:

- **min:** orders 2 and 4, an ICM and an ISSE;
- **mid:** an ICM-ISSE chain of orders 0-4 and 6, a match and a mixer;
- **max:** 22 components:
  - a constant;
  - an ICM-ISSE chain of orders 0-5 and 7;
  - a match on order 8;
  - a word ICM and a word-bigram ISSE;
  - ICMs on bytes 2, 3 and 4 alone, and one on the bytes 215/216 back;
  - two mixers (7 bits of order 1, and order 0);
  - two SSE stages, order 0 and order 1, each mixed back with MIX2.

For T1 (9,523,200 B, arg0 = 4, membits 24) the levels give:

- level 3 `x4,3ci1`;
- level 4 `x4,0ci1,1,1,1,2awm`;
- level 5 `x4,0w2c0,1010,255i1c256ci1,1,1,1,1,1,2ac0,2,0,255i1c0,3,0,0,255i1c0,4,0,0,0,255i1mm16ts19t0`
  (the periodic analysis finds no period in T1).

## 2. What was built

| file | what |
|---|---|
| `zp_dec.py` | **The decoder.** Pure Python, no imports; the region between `# BEGIN DECODER` / `# END DECODER` is what a monolith would carry. All nine components, HCOMP, PCOMP. It translates the block's model and its ZPAQL to Python source and executes it (exec spelled minifier-safe, §3.1): one straight-line function per block, each ZPAQL basic block an `if k==addr:` arm. The state table, squash and stretch are computed (see below). |
| `zp_enc.py` | **The encoder side.** A port of libzpaq's ZPAQL compiler, a disassembler, a port of `makeConfig` (preprocessing 0 and 3) and of the level expansion, the suffix-array BWT (numpy), and `compress()`. That writes a conforming block: tag, `zPQ`, header, one segment (empty filename, the size as comment), `FE` (no SHA-1) and `FF`, as libzpaq's `compressBlock` writes them with its defaults (`compute_sha1=false`, libzpaq.h:294; libzpaq.cpp 7704-7729). The encoder is not a second copy of the model: the decoder's generated source is rewritten in five marked places (`encoder_source`). |
| `zp_configs.py` | **The configs measured.** min, mid and max are our disassembly of libzpaq's built-in bytes. The `ours*` rows were written for this study. |
| `zp_tiny.py` | **A plain interpreter.** Hand-compacted, no code generation, no PCOMP (4,854 characters without newlines): the typed-stage estimate, and a second implementation by the same builder (a check against slips in the code generation, not against a shared misreading). |
| `test_zp.py` | **The checks.** `tables`, `compiler`, `tiny`, `roundtrip`. |
| `bench_zp.py` | **Encode/decode timing**, `bootstrap/r3/arch/bench.py`'s method. |
| `measure_r2_zp.py` | **The R2 cost,** `bootstrap/r3/arch/measure_r2.py`'s method, imported from it. |
| `typed_zp.py` | **The typed stage** under ZPAQ configs. |
| `summary_zp.py` | **Archive pages** of the T1 rows, holo's planner via `bootstrap/r3/arch/pages.py`, plus the 14- and 15-page lines by bisection. |

**The declared subset (zp_dec.py):**

- one block, one segment;
- no journaling archive (jDC transactions, fragment tables, dedup), no
  stored (n = 0) blocks;
- the SHA-1 trailer is not checked (the R3A1 container has a CRC-32);
- malformed input is not diagnosed.

**zp_enc.py's preprocessing:** no LZ77 (levels 1, 2, the LZ77 branches of
3 and 4) and no E8E9.

### 2.1 Conformance: what was checked, and how

All MEASURED:

- **Tables.**
  - The bit-history state table is generated from rules: the older
    libzpaq StateTable constructor's num_states / discount / next_state,
    reconstructed. It equals all 1,024 entries of libzpaq 7.15's `sns`.
  - Squash and stretch come from their defining formulas with Python's
    float `**`. They equal `ssquasht` / `stdt` and libzpaq's own DEBUG
    checksums (3887533746, 2278286169).
  - dt and dt2k equal theirs.
- **The compiler.** Our disassembly of libzpaq's three built-in models,
  recompiled by our compiler, is byte-identical to the 28 / 71 / 198
  bytes in `Compressor::startBlock`. So the compiler, the disassembler
  and the header layout agree with libzpaq on real configs. This covers
  raw jumps (`jt`/`jf`/`jmp` with numeric offsets, as our disassembly
  writes them) but not the structured control flow (`if`/`else`/`endif`,
  `do`/`while`, `ifl`/`elsel`) that the `ours*` configs and the
  generated level configs use. That part of the compiler
  (`zp_enc._compile_comp`, zp_enc.py 122-194) was checked against
  `Compiler::compile_comp` (libzpaq.cpp 2575-2690) by reading only: no
  reference bytes exist for a config that uses it. The round trips do not
  check it either, since encoder and decoder run the same compiled bytes.
- **Two implementations.** `zp_tiny.py` is a second, plain interpreter,
  written by the same builder. It decodes the same blocks as `zp_dec.py`,
  byte-identical, for min, mid, max, level 4 and ours (30 KB of T1). That
  catches slips in `zp_dec.py`'s code generation; a misreading of
  libzpaq shared by both would pass. Conformance with libzpaq rests on
  reading.
- **Round trips, byte-exact**, for every row (`test_zp.py roundtrip`) on:
  empty, 1 byte, 4 KB random, the page bundle b.py (50,533 B).
- **The first 1 MB of T1**, byte-exact: min, mid and level 4 in
  `test_zp.py`; max, level 5 and ours_v0 in `bench_zp.py`.
- **T1 itself**, byte-exact for every row of the headline table.

**What could not be verified (nothing upstream was run):**

- that libzpaq or `zpaq x` decodes our blocks, or that we decode theirs;
- that the JIT path libzpaq uses by default (`assemble_p`, `assemble`)
  computes what the interpreted `predict0` / `update0` / `execute`
  compute: we followed the interpreted path;
- that `make_config` produces the same bytes as libzpaq's `makeConfig`
  (only the three built-in configs have reference bytes);
- the archiver's redundancy/type analysis (`zpaq.cpp` 2427-2510), so which
  of level 3/4's branches `zpaq a -m4` would pick for T1. The rows assume
  the CM branches. compressBlock switches level 4 to BWT (`x4,3ci1`, the
  level 3 row) when type ≥ 900 (libzpaq.cpp 7637-7643), and a tree as
  redundant as T1 may land there, so the level 4 row may not be what
  `zpaq a -m4` writes;
- the float tables on another platform: Python's `**` could differ from C's
  `exp`/`log` in the last bit elsewhere. The checksum test above is the
  guard. The decoder could carry it as an assert, about 60 B (ESTIMATE);
- the BWT: our suffix array vs divsufsort's. Both are the unique suffix
  order, but only our own round trip checks it.

## 3. Measurements

### 3.1 R2: the decoder inside the R3 monolith (`measure_r2_zp.py`, MEASURED)

**Method.** `bootstrap/r3/arch/measure_r2.py`'s method, imported from it:

- receiver.py + the decoder region + the flat ustar unpacker, with the glue
  `unpack(unz(v.payload))`;
- minified-g;
- cm2 v2 primed with `build/loader/r.py`.

The receiver alone: minified-g 22,011 B, cm2 9,415 B. Two R2 pages hold
10,608 B.

| row | decoder region: lines / bytes / minified | monolith minified-g | cm2 | R2 cost | R2 pages |
|---|---|---|---|---|---|
| strong2 + unpacker (re-measured) | 86 / 3,951 / 2,133 | 24,473 | 10,598 | 1,183 | 2 |
| ZPAQ `zp_dec.py` + unpacker | 180 / 9,238 / 6,492 | 28,843 | 12,304 | 2,889 | 3 |
| the same without PCOMP | 172 / 9,059 / 6,373 | 28,723 | 12,257 | 2,842 | 3 |
| ZPAQ `zp_tiny.py` (plain interpreter) + unpacker | 114 / 4,975 / 4,812 | 27,140 | 11,445 | 2,030 | 3 |
| no decoder: exec the decoder shipped in the archive + unpacker | 6 / 178 / 135 | 22,491 | 9,629 | 214 | 2 |
| `zp_dec.py` with the literal builtin `exec` (the trap below) | 178 / 9,171 / 6,647 | 33,679 | 13,086 | 3,671 | 3 |

**A measuring trap found on the way.** python-minifier stops renaming
every module-level name of the whole file once the builtin name `exec`
(or `eval`, `locals`, `globals`, `vars`) appears anywhere in it
(python-minifier's own source in site-packages,
`python_minifier/rename/resolve_names.py`, `namespace.tainted`).

- The receiver's 22 KB then minify without renamed globals: +4.8 KB of
  minified text, +782 B of cm2. That is a cost of the minifier, not of the
  decoder.
- `zp_dec.py` therefore spells exec as
  `type(lambda: 0)(compile(s, '', 'exec'), g)()`.
- Anyone adding exec to the monolith later should know this.

**No ZPAQ decoder fits the 2-page margin.** The receiver's spare is
1,193 B. The smallest ZPAQ decoder written here, a plain interpreter
compacted by hand, costs 2,030.

- A ZPAQ decoder restricted to the components a chosen config uses (ICM,
  ISSE, MATCH, MIX, MIX2, SSE for max/ours) would save perhaps 10-15 %
  (ESTIMATE).
- That would no longer be a ZPAQ decoder: a future config with CM or AVG
  would not decode.

### 3.2 Decode speed

- **Every row** is in the headline table: wall seconds for T1 in a fresh
  process, and µs per input byte.
- **The plain interpreter against the translating decoder**, same blocks,
  100 KB of T1 (MEASURED, CPU seconds):

  | config | zp_dec.py | zp_tiny.py |
  |---|---|---|
  | mid | 45.8 µs/B | 95.4 µs/B |
  | max | 134.8 µs/B | 290.9 µs/B |

  The translation to Python source buys a factor of about 2.1.
- **Per component and bit** (MEASURED from the table): about 0.7-0.8 µs,
  roughly linear in the number of components. A model like `ours` (27
  components, 8 bits a byte) costs about 170 µs/B. strong2 does its 10
  inputs, mixer and APMs in one hand-fused loop, at 88 µs/B.

### 3.3 The typed stage (`typed_zp.py`, MEASURED)

**Payload.** The reader text `make_typed.reader_text()` builds (4,564 B,
the payload of record), 5 bits per base-32 digit, 60 digits per line.

**cm2 v2 re-measured:** 14,381 bits = 2,877 digits = 48 lines, equal to
build.json.

**The two ZPAQ measures:**

- **Unprimed:** the coded stream alone.
- **Primed:** the coded bytes of (a.py's text + reader) minus those of
  (a.py's text) alone. That is the reader's cost after the model has
  trained on a.py, as cm2 v2's priming does.

| config | unprimed digits | primed digits | primed lines | model header (would be typed too) |
|---|---|---|---|---|
| cm2 v2 (the record) | — | 2,877 | 48 | — (in a.py) |
| min | 4,074 | 3,746 | 63 | 28 B ≈ 45 digits |
| mid | 3,136 | 2,920 | 49 | 71 B ≈ 114 digits |
| max | 3,066 | 2,840 | 48 | 198 B ≈ 317 digits |
| level 4 | 3,063 | 2,852 | 48 | 104 B ≈ 167 digits |
| level 5 | 3,077 | 2,848 | 48 | 296 B ≈ 474 digits |
| ours_v0 | 3,013 | 2,796 | 47 | 264 B ≈ 423 digits |
| ours | 3,063 | 2,834 | 48 | 276 B ≈ 442 digits |
| ours2 | 3,064 | 2,831 | 48 | 323 B ≈ 517 digits |
| ours3 | 3,063 | 2,828 | 48 | 373 B ≈ 597 digits |

(level 4/5 here at libzpaq's block size for a 4.6 KB input, arg0 = 0;
the `ours*` headers do not depend on the input. Re-measured after the
review; the earlier table gave `ours` the figures that belong to
`ours_v0`, the first draft of the config. `ours_v0` is not a T1 row.)

**The typed decoder.** Counted without newlines, as the record counts
a.py's 826 (make_typed.py: "newlines not counted").

- `zp_tiny.py`'s region is 4,854 characters, 113 lines (MEASURED). It is
  a plain interpreter with all nine components and the machine except
  OUT; a ZPAQL interpreter needs at least that to read an arbitrary
  config.
- It cannot train on a primer, which the primed rows above assume. That
  takes a primer argument, a branch that takes the bit from the primer
  instead of the coder, and a start for the coder after the primer:
  about 80 characters (ESTIMATE, by analogy with d()'s `if i<m:` branch).
- It replaces d(), 423 characters in build/loader/a.py (MEASURED).
- Restricting it to the components the reader's config uses might save
  25-35 % (ESTIMATE). That would no longer be a general ZPAQ decoder.

**ESTIMATE of the typed total.** Program for every config: a.py 826 −
d() 423 + 4,854 + priming about 80 = about 5,337.

| config | data: header + payload digits | lines | check glyphs | total |
|---|---|---|---|---|
| level 4 | 167 + 2,852 = 3,019 | 51 | 204 | ≈ 8,560 |
| mid | 114 + 2,920 = 3,034 | 51 | 204 | ≈ 8,575 |
| max | 317 + 2,840 = 3,157 | 53 | 212 | ≈ 8,706 |
| ours | 442 + 2,834 = 3,276 | 55 | 220 | ≈ 8,833 |
| ours2 | 517 + 2,831 = 3,348 | 56 | 224 | ≈ 8,909 |
| ours3 | 597 + 2,828 = 3,425 | 58 | 232 | ≈ 8,994 |

Today: 3,895.

**Verdict.** The best ZPAQ model (`ours3`) saves 49 digits on the payload
against cm2 v2. The decoder costs about 4,500 characters more and the
model header 114-597 digits.

### 3.4 How `ours` was found (1 MB proxies, then T1)

1. **ours_v0**: strong2's inputs written as a ZPAQ model. It had:
   - an ICM-ISSE chain on orders 0-4, 6 and 7;
   - a match;
   - word and word bigram;
   - the column model;
   - two sparse contexts;
   - three mixers by order 0, 1 and hashed order 2, mixed again;
   - two SSE stages.

   It lost to max on 1 MB (244,743 against 244,013).
2. **maxcol**: max.cfg plus the column model, with M widened to 64 KB.
   The column model: an ICM on (byte above, column capped at 40) and an
   ISSE on (byte above, byte 1).
   242,878 on 1 MB (−0.5 % against max).
3. **ours**: maxcol plus several changes:
   - order 6 in the chain;
   - a full-byte order-1 mixer and SSE (max uses 7 bits);
   - a third SSE stage on hashed order 2, with its MIX2;
   - tables sized for a 9.5 MB block (ISSE 2^20-2^22 rows).

   242,614 on 1 MB; on T1 1,610,701 (−1.2 % against max, −2.3 %
   against strong2).
4. **ours2**: ours plus:
   - an order-12 ISSE;
   - a second match model on order 16;
   - an ICM on the bytes above and above-right with byte 1.

   241,479 on 1 MB (−0.5 % against ours); on T1 1,585,132 (−1.6 %
   against ours). The long contexts pay three times more on T1 than on
   1 MB: the tree repeats across files.
5. **ours3**: ours2 with:
   - ISSEs on orders 16 and 24 chained after order 12;
   - a third match model on order 32;
   - H widened to 64 entries.

   241,534 on 1 MB (flat against ours2); on T1 1,582,375 (−0.17 %
   against ours2). The returns have run out along this axis: three more
   components buy 2.8 KB.

The HCOMP column code in `zp_configs.py` keeps the positions of the last
two line feeds in R0/R1. The byte above is M[R1 + column], capped at the
last line feed when the line above is shorter, as strong2 does.

### 3.5 How to run

From the worktree root, with the record's interpreter:

```
PY=env/bin/python
$PY bootstrap/priorart/zpaq/test_zp.py all                  # tables, compiler, tiny, round trips (about 10 min)
$PY bootstrap/priorart/zpaq/bench_zp.py ours T1              # encode + decode T1 (about 1 h)
$PY bootstrap/priorart/zpaq/bench_zp.py ours T1 1000000 --arg0 4   # the 1 MB proxy
PYTHONPATH=src $PY bootstrap/priorart/zpaq/measure_r2_zp.py  # R2 rows (about 5 min)
$PY bootstrap/priorart/zpaq/typed_zp.py ROW                  # one typed-stage row per process (see below)
PYTHONPATH=src $PY bootstrap/priorart/zpaq/summary_zp.py     # archive pages of the T1 rows
```

`typed_zp.py` with the nine rows of §3.3 in one process peaked at
37.6 GB resident (MEASURED, `/usr/bin/time -l`, 31 s): the `ours*`
configs carry tables sized for T1 whatever the input, and each row builds
an encoder and a decoder three times. Run one row per invocation.

`test_zp.py tables` and `compiler` read libzpaq.cpp from the scratchpad
clone as data, and are skipped if it is absent. Encoding the level-3 row
needs numpy (the suffix array).

## 4. The refuter's findings and what was done

One Opus refuter re-ran the R2 rows, the 1 MB proxies, the tables, the
compiler check, the two-decoder check and the typed stage, did 70 round
trips on payloads the configs were not tuned on (all byte-exact), and read
`zp_dec.py` against libzpaq.cpp. No blockers. The answer stands.

**Major: the typed table's `ours` row was stale. Fixed.**

- The table gave `ours` 3,013 unprimed / 2,796 primed digits. Those are
  the figures of `ours_v0`, the config's first draft: typed.jsonl was
  written at 20:08, zp_configs.py last changed at 21:53.
- Re-run on the current configs (MEASURED, this session): `ours` 3,063 /
  2,834, `ours2` 3,064 / 2,831, `ours3` 3,063 / 2,828; `ours_v0` 3,013 /
  2,796 exactly as before; min, mid, max, level 4, level 5 and cm2 v2's
  2,877 unchanged. The stale file is kept beside the new one as
  `typed.stale-2008.jsonl`.
- §3.3 and the answer now carry every row. The best ZPAQ payload saves
  49 digits against cm2 v2, not 81.

**Minors.**

| finding | what was done |
|---|---|
| Two counting conventions: a.py's 826 leaves out newlines, d()'s 438 and zp_tiny's 4,967 counted them. The estimate also left out the code a primed ZPAQ decode needs. | Recounted without newlines (MEASURED): d() 423, zp_tiny 4,854 (113 lines). Added about 80 characters for priming (ESTIMATE). The typed total is now about 8,560-8,990 by config (ESTIMATE), against 3,895. |
| "Jumps included" overstated the compiler check: it never exercises `if`/`else`/`do`/`while`/`ifl`. | §2.1 now says the structured control flow is checked by reading only. |
| `zp_tiny.py` was called independent; the same builder wrote both. | Reworded in §2 and §2.1: it catches slips in code generation, not a shared misreading. |
| The flexibility premise is weak: the ladder is bound into every volume, so each volume prints its own R2 pages. | Said in the answer, for ZPAQ and for the exec route. |
| "1.5-2.5×" covers only configs chosen for ratio. | The refuter's speed-cut max probes are in the answer (his MEASURED, not re-run): at strong2's ratio about 1.45× or slower. |
| Level 3/4 rows assume the CM branches; level 4 switches to BWT for type ≥ 900. | Pointer to libzpaq.cpp 7637-7643 added under "could not verify". |
| The monolith is 10,598 B here against the task's 10,599, so 10 B spare against the record's 9. | A 1 B re-measure difference; the refuter got 10,598 too. Left as measured. |
| The `ours*` configs were tuned on T1. | The refuter's out-of-sample check on 1 MB of ALL.tar outside T1 (his MEASURED, encode only): strong2 184,091, max 181,300 (−1.5 %), `ours2` 177,336 (−3.7 %). The ratio advantage carries over; nothing to correct. |

**Found while fixing.** Re-running `typed_zp.py` with all nine rows in one
process peaked at 37.6 GB resident (MEASURED), over this study's 8 GB
per-process limit; it ran 31 s and finished. The `ours*` tables are sized
for T1 whatever the input. §3.5 and the script's docstring now say to give
one row per invocation.
