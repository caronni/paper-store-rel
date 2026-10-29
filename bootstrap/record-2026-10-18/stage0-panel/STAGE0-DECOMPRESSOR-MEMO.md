# Stage-0 decompressor: the five candidates, synthesized (2026-10-18)

**Labels.**
- **MEASURED**: a refuter reproduced it.
- **CLAIMED**: the builder alone reported it. **CLAIMED (synth)** is one unrefuted run of mine.
- **ESTIMATE**: arithmetic or judgement.
- **BRIEF**: a baseline taken from the brief and not re-run.

Nothing here is promoted. There is one fixture set, and the constants were tuned on it.

All five refuters reproduced every size, line count, known-answer vector (KAV) and round trip to the byte. All five found the output identical under PYTHONHASHSEED 0 and 4242. Only ppm's verdict was CORRECTED, and the corrections were to its prose. Every size below is therefore MEASURED. Timings are MEASURED to within about 10%, on a shared machine.

## 1. Pareto table

- "Lines" and "chars" are count_lines output.
- Sizes are bytes, unprimed/primed.
- The primer is primer.txt followed by the candidate's whole dec file.
- n is carried out of band; carrying it in the stream would add about 3 B.

| candidate | lines | chars | T1 u/p | T3 u/p | T4 p | decode T3/T4 s |
|---|---|---|---|---|---|---|
| lz-raw (no coder) | 15 | 496 | 3,562/3,250 | 9,334/8,902 | 169,158 | 0.03/0.36 |
| lzdict | 20 | 739 | 3,263/3,098 | 8,545/8,299 | 151,835 | 0.1/1.6 |
| bwt-tiny | 23 | 905 | 3,323/3,323 | 8,652/8,652 | 144,321 | 0.35/4.2 |
| ppm25 | 25 | 920 | 3,092/2,896 | 7,810/7,574 | 143,711 | 0.27/6.6 |
| **cm2** | **25** | **1,010** | **2,884/2,633** | **7,257/6,914** | **119,211** | 3.6/62 |
| cm2-plus | 34 | 1,465 | 2,860/2,612 | 7,160/6,794 | 115,669 | 5.1/74 |
| bwt-cm | 39 | 1,837 | 3,146/3,121 | 8,204/8,188 | 135,184 | 2.7/26 |
| cmmix40 | 39 | 1,863 | 2,803/2,575 | 7,072/6,804 | 125,504 | 4.2/87 |
| cmmix | 48 | 2,302 | 2,799/2,542 | 6,950/6,629 | 114,177 | 6.2/112 |
| ceiling (BRIEF, unprimed) | | | xz 3,336 | xz 8,544, bzip2 8,464 | xz 145,264, ppmd 122,234, lpaq1 110,661 | |

Further variants, all MEASURED (primed T3 / T4):

| variant | lines | T3 | T4 |
|---|---|---|---|
| cm2-o2 | 25 | 10,137 | 220,954 |
| bwt-mtf | 27 | 8,326 | 141,064 |
| ppm-plus | 38 | 7,401 | 140,654 |

There is no ppmd or lpaq1 baseline for T1 or T3. On T2, lpaq1 is 4,666 and cm2 is 4,676 unprimed.

The front, on lines against primed T3, is lz-raw → lzdict → cm2 → cm2-plus → cmmix. Every other candidate is dominated.

- **lz-raw**: the cheapest to type and the most readable as pseudocode. With no arithmetic coder, a bug gives partly correct output. It is 29% worse than cm2 on T3.
- **lzdict**: about xz on T1–T3, and 5% worse than xz on T4.
- **bwt-\***: dominated everywhere. It cannot use a primer (0.2–1.9%). Drop.
- **ppm25**: the same lines as cm2 and 90 fewer chars, but 9.5% worse on T3 and 21% worse on T4. It carries the spec subtlety on table keying and insertion order that its refuter corrected.
- **cm2**: the knee. It beats xz everywhere and ppmd on T4, with no hash and no tables. The order tuple is data: the order-2 build costs the same lines and is always worse.
- **cm2-plus**: +9 lines buy 0.8% (T1), 1.7% (T3) and 3.0% (T4).
- **cmmix**: +23 lines buy about 4% on T1–T4 over cm2. Its weights are unclamped and it needs a 123-bit constant.

## 2. The typed listing

The scheme types stage 0 plus about 120 chars of base32 glue (ESTIMATE). It then types the remaining 6,500 B as base32, at 1.6 chars per byte, using T1's MEASURED ratio. The other ~1.5 KB is typed plain either way. All rows are ESTIMATEs.

| candidate | remainder compressed (B) | typed chars | vs 6,500 plain |
|---|---|---|---|
| lz-raw | 2,579–2,826 | 4,742–5,139 | −27 to −21% |
| lzdict | 2,458–2,589 | 4,793–5,002 | −26 to −23% |
| ppm25 | 2,298–2,453 | 4,717–4,966 | −27 to −24% |
| **cm2** | 2,089–2,288 | **4,473–4,792** | −31 to −26% |
| cm2-plus | 2,073–2,269 | 4,902–5,216 | −25 to −20% |
| cmmix | 2,017–2,221 | 5,650–5,976 | −13 to −8% |

Each range runs from primed to unprimed. The realistic case for cm2 is primed with its own text only: T1 is 2,776 (CLAIMED (synth); round trip verified), which gives about 4,655 chars, −28%.

What it saves:
- In characters it pays. cm2 saves about 1,850 of roughly 8,000 typed chars, close to a quarter of the 4–6 h.
- cm2 breaks even at about 2.3 KB of downstream text.
- A second typed stage does not pay. lz-raw unpacking cm2 would need a ratio below 0.32 on 1 KB of novel code.
- Extra model lines cost more to type than they save on 6.5 KB.

What the numbers leave out:
- **Typing rate.** Base32 cannot be chunked, so it is typed more slowly and with more errors than source. The rate is unmeasured. At 1.4× slower per character, the saving is a wash in hours. This measurement is owed before any ruling.
- **Degradation.** R1 promises to "degrade into executable pseudocode". Under compression only stage 0 still does. The roughly 170-line R2 reader becomes opaque until stage 0 runs, which makes stage 0 a single point of failure. An arithmetic coder gives a red light, not a gradient. The cure is the Plate's own CRC doctrine, table plus trace (§5).
- **Typos.** The per-line checksums catch typos in compressed text equally well. An uncaught one, though, destroys every later byte, and the whole-file CRC detects it without localizing it. There are about 55 base32 lines against about 160 source lines, so fewer checksums to work.
- **Style.** The 25 lines lean on comprehensions, `setdefault` aliasing and parallel assignment. Written in R1's explicit-loop style, cm2 is about 35–40 lines and 1,300 chars (ESTIMATE). That costs about 300 of the saved chars.

## 3. R2

Today R2 holds about 30,000 B at 7,168 B/page: 4.19 pages on 5 leaves. That is about 60 h by loupe at 12 h/page, or 47.6 h prorated by bits. The compressed sizes use T3's primed ratio (MEASURED); everything else in the table is an ESTIMATE.

| candidate | bytes | pages | leaves | loupe h (prorated) | h saved (per leaf / prorated) |
|---|---|---|---|---|---|
| lz-raw | 8,150 | 1.14 | 2 | 12.9 | 36 / 35 |
| lzdict | 7,598 | 1.06 | 2 | 12.1 | 36 / 36 |
| ppm25 | 6,934 | 0.97 | 1, 3% margin | 11.0 | 48 / 37 |
| **cm2** | 6,330 | 0.88 | 1, 12% margin | 10.1 | 48 / 37 |
| cmmix | 6,069 | 0.85 | 1 | 9.6 | 48 / 38 |

The prorated hours barely differ between candidates. The leaf count is what differs, and only the context-mixing (CM) candidates fit on one leaf with margin. T3 is a stand-in, so watch the 12% margin.

## 4. The primer

**Worth** (MEASURED, full primer):

| candidate | T1 | T3 | T4 |
|---|---|---|---|
| cm2 | −8.7% | −4.7% | −0.5% |
| cmmix | −9.2% | −4.6% | |
| ppm | −6.3% | −3.0% | |
| lzdict | −5.1% | −2.9% | |
| bwt | ~0 | ~0 | |

The primer pays where payloads are small, which is exactly R1 and R2.

**Source.** This is the brief's soft spot. "In the finder's hands" means on paper, not as bytes.
- For the R1 remainder, the free bytes are only what was typed plain: stage 0 and the glue. primer.txt exists only if the finder types the Plate.
- For R2, the free primer is all of decoded Listing One (about 8 KB of Python) plus stage 0. primer.txt is a fair stand-in there.

**Own text** (cm2, CLAIMED (synth), T1 round trip verified):

| primer | T1 | T3 |
|---|---|---|
| dec.py alone | 2,776 (−3.7%) | 7,168 (−1.2%) |
| primer.txt alone | 2,680 | 6,936 |
| both | 2,633 | 6,914 |

The decoder's own text matters most where it is the only primer, which is the realistic R1 case. The refuters measured core-only priming against the whole file: it costs 0.5–1.1%.

**Fragility.** A primer that is one byte off decodes to garbage silently (MEASURED, lzdict refuter). The design already contains the fix. The Plate prints the CRC-32 of Listing One's text, and that CRC implies a canonical byte form: indent digits expanded, LF, trailing newline. Define the primer as those bytes, and have the finder check the CRC before priming.

## 5. What the Plate must print for cm2

The 25 lines sit in Listing One. The Plate or its annex adds about 30–35 lines at 72 chars, about half a leaf (ESTIMATE):

1. **Semantics, about 8 lines.**
   - Parallel assignment reads the old values.
   - `setdefault` returns the stored node, which is mutated in place.
   - A bool is 0/1 in arithmetic, shifts and indexing.
   - Precedence, by worked cases: `h & q | q + 1` is `(h&q)|(q+1)`; `b - a >> 12` is `(b-a)>>12`; `x >> 7 - j & 1` is `(x>>(7-j))&1`.
   - `int.from_bytes` is big-endian.
2. **Widths, 3 lines.**
   - a, b, x are 32-bit (M = 0xFFFFFFFF).
   - s0 and s1 are 64-bit; `s1*4094` needs about 50 bits.
   - Counts stay below 2^32 under 512 MiB (CLAIMED).
   - All shifts are on non-negative values.
3. **Model, 3 lines.**
   - Contexts are exact: key `((h&q)|(q+1))<<8|c0`, with q = 2^(8o)−1. There is no hash and there are no table sizes; any collision-free map conforms.
   - D = 12 = the largest order.
   - Memory is 1.25 GB in CPython on T4 (CLAIMED), trivial at R2 scale.
4. **Container, 3 lines.**
   - n is printed.
   - The first 4 bytes seed x.
   - Reads past the end return 0.
   - The flush is the single byte (a>>24)+1.
   - The output CRC-32 is printed.
5. **Primer, 2 lines:** the canonical recipe and its CRC.
6. **KAV and trace, about 14 lines.**
   - enc(b'paper-store bootstrap') = `8fa930ac238dfe22189944d48f83d7`, 15 B, unprimed (MEASURED).
   - One primed vector.
   - The first 12 coding steps as (i, j, p, a, b, x, y), so a wrong port gets a gradient.

The refuter found no coder ambiguity. Edge cases round-trip, and random input expands 8% (MEASURED).

## 6. Recommendation

**One stage: cm2 (25 lines) as stage 0.**
- It is the knee on every fixture.
- It is 9–17% under ppm25 at equal lines, and within about 4% of the 48-line cmmix.
- It is the only sub-30-line candidate that puts R2 on one leaf with margin: 5 leaves → 1, about 37–48 loupe-hours saved (ESTIMATE from MEASURED ratios).
- Its Plate burden is semantics, not constants.

**No stage 1 for the ladder.**
- The mid decoder can call the stage-0 function it already holds.
- At T4's ratio, R3's ~625 KB becomes about 93 KB, roughly 3 leaves against 16–20. At the brief's 1.5 MB it is about 6 leaves (ESTIMATE). This is the largest saving on the table.
- cmmix buys about 4% (MEASURED, T4) and changes no leaf count (ESTIMATE).
- A full-strength compressor belongs to the archive volumes, which R3's source can carry.

The owner's "multi-stage with a fixed dictionary" survives as the dictionary: the canonical Listing One text, which is free. A typed multi-stage chain does not pay (§2).

**Open rulings:**
1. Compress Listing One's remainder (about −28% chars, ESTIMATE) or keep R1's pseudocode promise? Measure a base32 typing rate first. A hybrid is possible: type compressed, and print the R2 reader plain for reading only.
2. cm2 in R1's explicit-loop style (about 35–40 lines), or keep the idioms and extend the annex?
3. The canonical primer recipe, and what the Plate's Listing One CRC covers under compression.
4. cm2-plus (+9 lines) if a real R2 payload lands above 0.95 page.
5. The fixtures were the tuning set. Re-measure on the real mid_decoder.py and Listing One before any ruling is final.

Files:
- Candidates: <tmp>
- My priming runs: <tmp>
