# cm2 and cmmix: where they come from, how they compare with public codecs, how good the evidence is, how they work, and what limits them

**Labels.** RECORDED means the number comes from the repo record under `/home/user/paper-store/bootstrap/record-2026-10-18/`. When a recorded number comes from `bootstrap/RECORD.md`, that file is named. MEASURED means one of this session's workers or refuters ran it, outside the repo. PUBLISHED means a public source, with its URL. ESTIMATE means arithmetic or judgement.

The measurement runner reproduced all 16 cm2/cmmix sizes byte for byte and verified every round trip. It also reproduced every recorded baseline (MEASURED). So the RECORDED cm2 and cmmix sizes below are MEASURED as well.

**Caveat on every source-size number.** count_lines.py skips comment-only lines (`bootstrap/typed/count_lines.py:2-3,7`).
- cmmix's counted region contains 13 comment lines, 822 chars, that are not counted (MEASURED). Eleven of them (dec.py:7-17) are spec the Plate must carry.
- cm2's counted region has no comments. Its spec lives in the docstring and NOTES, also uncounted.
- So "25 lines / 1,010 chars" and "48 lines / 2,302 chars" both under-count what must be typed, and not by the same amount.

### 1. Are cm2 and cmmix wholly self-invented?

No. Both are compact rebuilds of published PAQ-family parts.
- cm2's builder says so: NOTES.md:3 "PAQ1-style", NOTES.md:13 "lpaq1 carry-less", dec.py:2 "(lpaq style)".
- cmmix's builder names no source for the design that shipped. cmmix NOTES.md:47-48 says "lpaq-style" only about the next step, which was never built (bit histories plus a state map). cmmix's lpaq1 lineage is inferred from the code.

**cm2, element by element:**
- **Bitwise counting model.** Each context holds an [n0, n1] count pair. The model sums counts across orders and adds a bland "+1" prior. This follows PAQ1 (Mahoney 2002), whose rule is p(1) = Σc1/Σc with a bland model c0 = c1 = 1 (PUBLISHED, https://mattmahoney.net/dc/paq1.pdf; paq1.cpp:95-96).
  - The PAQ1 program does not store plain integer pairs. It stores a 244-state probabilistic Counter with randomized transitions (paq1.cpp:380-412, PUBLISHED). The "n/2+1" rule is the paper's idealization, rule (3).
  - The partial-byte convention (c0 with a leading 1) is fpaq0/lpaq1's. The PAQ1 paper only says "the 0 to 7 bits of the partially read byte".
- **Order weights.** cm2 weights each order by 2^index. PAQ1 weights by n², where n is the order and n−1 the number of context bytes (paq1.cpp:744-745 `wt=(i+1)*(i+1)`, PUBLISHED).
  - Putting PAQ1's weights, (context bytes + 1)², into cm2 costs +0.7% on T3 (MEASURED by a refuter: model-only ideal code length, unprimed, 7,302 against 7,250).
  - The draft's earlier +1.3% used (tuple index + 1)², which is wrong for orders 6, 8 and 12 (36/49/64 instead of 49/81/169).
- **Nonstationary update.** cm2 sets the opposite count to min(n, n//4+2). PAQ1 rule (3) sets it to n/2+1 when n > 2 (PUBLISHED). Swapping the paper's rule into cm2 costs +0.8% on T3 (MEASURED; the probe uses exact counts, not PAQ1's state counter).
- **Deterministic-node doubling.** cm2 multiplies a context's count by 2 when the other count is 0.
  - **Not in the source code of PAQ1 or paq2 to paq6** (MEASURED, grep). PAQ1 has no zero-count branch in predict (paq1.cpp:743-749).
  - **Crinkler** has `boost = (prob[0]==0 || prob[1]==0) ? 2 : 0`, applied as a left shift, i.e. x4 (PUBLISHED, CompressionState.cpp:80-85, https://raw.githubusercontent.com/runestubbe/Crinkler/master/source/Compressor/CompressionState.cpp).
  - **oneKpaq** lists the trick as "PAQ1 count boosting" (PUBLISHED, https://github.com/temisu/oneKpaq).
  - **paq8l** multiplies by 64 in its StateMap init: `if (n0==0) n1*=64; if (n1==0) n0*=64;` (PUBLISHED, paq8l.cpp:1302-1303, https://mattmahoney.net/dc/paq8l.zip). lpaq1's StateMap init is flat.
  - **Effect.** Removing the boost from cm2 costs +2.8% on T3 (MEASURED).
  - **Provenance.** The cm2 reader recalled the boost as PAQ1's, from memory. That is wrong about PAQ1's code. But it matches oneKpaq's public name for the trick and PAQ1's stated reason: the paper weights "roughly by n²/tp(0)p(1)… favoring long runs". The best public statement: the explicit zero-count boost first appears in Crinkler's code, and the demoscene names it after PAQ1's rationale.
- **Coder.** The carry-less 32-bit coder follows fpaq0/lpaq1 almost verbatim in its interval update, xm = a+((b−a)>>12)·p, and in its renormalization test (shift out while the top bytes agree). Its initialization matches lpaq1 exactly (dec.py:15 against lpaq1.cpp:755-759). The panel coders differ from lpaq1 in three ways (PUBLISHED, https://mattmahoney.net/dc/lpaq1.zip):
  - **Low-bits correction term.** lpaq1 adds `((x2-x1&0xfff)*p>>12)`. cm2 and cmmix both drop it.
  - **p adjust.** lpaq1 applies `p+=p<2048`. Neither panel coder does.
  - **Flush and padding.** lpaq1 flushes one byte, x1>>24 (:764), and its decoder pads with 0xFF. cm2 flushes (a>>24)+1 and pads with zeros (enc.py:36, dec.py:13). cmmix's encoder drops the 4 leading zero bytes, writes the shortest valid tail of 0-4 bytes and trims trailing zeros (cmmix/enc.py:35-48). That saves about 1-4 B over cm2's container (ESTIMATE).
  - **Line numbers.** The refuters disagree by one line. One places the correction term at lpaq1.cpp:719 and the p adjust at :718; two place them at :720 and :719. Read the citation as :719-720.
- **Nearest whole-design precedent: Crinkler.** It shares cm2's linear count-sum in the PAQ1 manner, power-of-2 weights, byte-mask contexts over the last 8 bytes, the zero-count boost, and no hash collision detection (PUBLISHED, https://mattmahoney.net/dc/dce.html §4.3.8: "based on PAQ1 (linear mixing) with sparse models and static weights tuned by the compressor… Model weights are powers of 2").
  - **oneKpaq** is the logistic-mixing variant of the same idea: boosted counts fed into a logistic mixer, hashless, weights on a 1/2^n scale (PUBLISHED, README). It is not a linear twin of cm2.
  - **Neither appears in the record** (MEASURED, grep). So cm2 is a re-derivation of a known demoscene design that the record does not cite. Whether it is *independent* cannot be shown: the builders were LLM agents whose training data probably include Crinkler.
- **The panel's own work:**
  - exact bignum dict keys with an order sentinel bit, so no hash has to be specified;
  - the constants: orders (0,1,2,3,4,6,8,12), the //4+2 cut, x2 rather than x4 (x4 alone with cm2's update rule is +1.1% on T3, MEASURED), and the 4094 scaling;
  - priming with the typed text;
  - the 25-line integer-only Python form.

  All three measured departures from PAQ1 help on T3. Together, PAQ1's rules (faithful weights, paper update, no boost) are +4.1% worse: 7,550 against 7,250 (MEASURED, model-only ideal code length, T3 unprimed). The draft's earlier +5.7% came from the mis-ported weights. But the departures were tuned on the same fixtures they were measured on.

**cmmix, element by element.** It is mostly lpaq1 (PUBLISHED, https://mattmahoney.net/dc/lpaq1.zip):
- **Shared conventions.** The same c0 convention, and the same 12-bit squash/stretch scale with an inverse table. lpaq1 builds squash as a 33-point interpolated table and stretch as its gap-filled inverse (lpaq1.cpp:192-230).
- **Adaptive rate.** The rate is 1/(n+c), as in lpaq1's StateMap with 1/(n+1.5) via dt = 16384/(2i+3) (lpaq1.cpp:300-335). cmmix uses c = 1.2, caps n at 30, and applies the rate directly to slots rather than to bit-history states.
- **Mixer.** Logistic mixing as in lpaq1 (lpaq1.cpp:392-437).
  - lpaq1 selects one weight set by an order and match-length bucket, `m.set(order+10*(h[0]>>13))` (lpaq1.cpp:670-689). Its training uses err·7 with rounded >>16.
  - cmmix's three selectors are its own (c0 plus match flag; (c1, c0); an order-2 hash with c0). Selecting by c0 is paq8-style. Its update is S·g>>10 with no rounding.
- **Word context.** A reset-on-non-member run hash, as in lpaq1.cpp:642-644. lpaq1 hashes letters only, case-folded, as (h+c)·56. cmmix hashes [0-9A-Za-z_], unfolded, as (wh+c+1)·773 (dec.py:33).
- **Match model.** Heavily simplified from lpaq1's MatchModel (lpaq1.cpp:502-590). lpaq1 keeps two hash heads, verifies by counting backward and caps at MAXLEN 62. cmmix keeps one 6-byte hash, does no verification and caps at 15.
- **Line-above plus column context.** From paq8l's wordModel (paq8l.cpp:1753-1777, PUBLISHED), simplified.
- **The panel's own work:**
  - squash built by forward-Euler integration, because exp is outside the subset;
  - a 10-bit stretch table;
  - three selected weight sets summed inside one dot product. This was not found in lpaq1 or paq8l; novelty beyond those two sources is unverified;
  - tuned constants.
- **Dropped from lpaq1:** bit-history states, APM/SSE and checksummed buckets.

### 2. Are there better public decompressors at this size?

There are four public axes. Only the fourth is close to this project's axis, and it was not measured.

**(a) Machine-code bytes (demoscene).**
- Crinkler: 210-220 B of x86-32 (PUBLISHED, https://mattmahoney.net/dc/dce.html §4.3.8). The authors are Rune L. H. Stubbe and Aske Simon Christensen; DCE misspells the name "Ashe". Do not take a date from DCE: it says 2010, and Crinkler is older (from memory, unverified).
- oneKpaq: 128-165 B (PUBLISHED, README).
- kkrunchy CM: about 1.5 KB (PUBLISHED, https://fgiesen.wordpress.com/2011/01/24/x86-code-compression-in-kkrunchy/). The CM depacker is public, as x86 asm in https://github.com/farbrausch/fr_public/tree/master/kkrunchy_k7 (depacker.asm, model_asm.asm) (PUBLISHED). The `kkrunchy/` directory holds the LZ-era version, which is what one researcher read.
- Shrinkler (Aske Simon Christensen/Blueberry, Amiga): LZ with context-modelled bits and a range coder. It is the parent of upkr ("losely based on Shrinkler", PUBLISHED, https://github.com/exoticorn/upkr). Its decoder size is unverified.
- ZX0: about 68 B standard Z80 decoder, the minimal-decoder LZ anchor (community-PUBLISHED, https://www.msx.org/nl/node/62438?page=1; not checked against the primary repo). It sits below lz-raw on the "smallest decoder" end of the front.
- These are the right scale and objective (decoder plus payload), but the payloads are executables. No text-corpus table is published.
- **Implication.** This is the closest axis in design. Its one lever cm2 lacks is an encoder that picks masks and weights per payload and ships them as header bytes. A probe adding the best of 254 sparse masks to cm2 gained at most 5 B on T1 (−0.2%), and retuning the weight shifts gained nothing (MEASURED; in-sample, T1 only, one mask added). Other researchers' 1-3% figures are ESTIMATE only.
- Crinkler also trades memory for size: no collision detection, and "the hash table is made very large, usually 256 MB or 512 MB" (PUBLISHED, DCE §4.3.8). That is the public precedent for cm2's exact-dict memory cost (§5).
- ZPAQ/ZPAQL is the general public form of the per-payload model lever: "the decompression code is stored in the archive", as sandboxed ZPAQL bytecode, with a separate reference decoder unzpaq206.cpp (PUBLISHED, https://mattmahoney.net/dc/zpaq.html). Its decoder size is unmeasured.

**(b) Source lines in C or scripting languages (educational and research).**
- **No public decoder near cm2's size (≤ about 25 lines / 1 KB) was run on the fixtures.** That includes fcm1, lzw 0.2, Crinkler, oneKpaq and Roadroller. Every public codec that was run is about 3-90x larger in source (MEASURED; the smallest is upkr's 86 C code lines). So "nothing public is both smaller and better" is untested, not shown.
- Results on T3, unprimed:

| Codec | T3 bytes | Label | Source size |
|---|---|---|---|
| upkr | 8,561 | MEASURED | 86 C code lines (MEASURED) |
| DMC (dmc.c) | 9,653 | MEASURED | 195 non-blank non-comment of 261 (MEASURED; another count said 218) |
| Nayuki Python PPM, best order | 10,758 | MEASURED | – |
| LZW | 14,223 | UNVERIFIED (no artifact or log found by a refuter) | – |
| fpaq0 | 20,073 | MEASURED | – |
| paq8l -8 | 6,233 header-free (round-trip verified) | MEASURED | 2,171 non-blank non-comment of 3,575 (MEASURED) |

- **Dropped row:** a 64-bit PAQ1 port gave 10,286 on T3. That is almost certainly a port defect, since PAQ1's rules inside cm2's frame give about 7,550 ideal. It is not evidence that PAQ1 loses.
- **upkr** has no Python unpacker. Its README lists C, arm/riscv asm, z80 and DOS unpackers in the repo, plus external Lynx, Jaguar, 8080 and 6502 ones (MEASURED/PUBLISHED). The task's premise that it has one was wrong.
- **lpaq1** is 846 lines, 484 of them non-blank non-comment (MEASURED twice; the 620 count has no stated method). It is about 20x cm2 in source.
  - Unprimed, header-free: lpaq1 2,912 / 4,658 / 6,994 / 110,653 against cm2 2,884 / 4,676 / 7,257 / 119,866 for T1 / T2 / T3 / T4. So cm2 is −1.0%, +0.4%, +3.8% and +8.3% against lpaq1 (MEASURED).
  - The memo RECORDS lpaq1 with its 8 B header: T2 4,666 and T4 110,661 (memo:31, :41).
  - Primed with cm2's primer: lpaq1 2,527 / 4,194 / 6,548 against cm2 2,633 / 4,372 / 6,914. cm2 is 4.2-5.6% larger.
  - Primed with cmmix's primer: lpaq1 2,523 / 4,196 / 6,553 against cmmix 2,542 / 4,203 / 6,629. cmmix is 0.2-1.2% larger.
  - The two primed comparisons above are MEASURED by the difference method and are ESTIMATE-grade *as primed decoders*: stock lpaq1, upkr, LZMA and paq8l cannot be primed without code changes. So the record's claim that cmmix beats lpaq1 on small files holds unprimed only.
- **paq8l -8** is the measured public ceiling, not lpaq1 (MEASURED by a refuter; T1/T3 round-trip byte-exact, 1.64 GB).
  - Header-free unprimed: T1 2,677, T3 6,233. That is 7-14% below cm2 unprimed.
  - Primed by the difference method with cm2's 9,282 B primer: 2,336 / 3,830 / 5,788. Against that, cm2 primed is +12.7 / +14.2 / +19.5% larger and cmmix primed is +8.8 / +9.7 / +14.5% larger. The primed runs were compressed only, with no round trip.
  - paq8l unprimed on T3 (6,233) already beats cmmix primed (6,629).
- **PPMd o16** with cm2's primer gives 2,672 / 4,377 / 6,979. cm2 primed is 0.1-1.5% smaller, roughly a tie (MEASURED, difference method).
- **Fixed-weight logistic probe.** A probe gave 3,030 / 7,558 against cm2's 2,882 / 7,250 on T1 / T3. All four are model-only ideal code lengths; cm2's coded sizes are 2,884 / 7,257. The probe used one global float weight vector, not a context-selected logistic mixer, so it says nothing about Roadroller- or oneKpaq-class mixers.
- **Kaseorg's 267-byte Python order-0..16 predictor** is the nearest predictor-only golf. It is scored 2L + mispredictions and has no coder (PUBLISHED, https://codegolf.stackexchange.com/questions/152856).

**(c) Benchmarks that count decompressor size.**
- **Hutter Prize.** Counts the zipped compressor (or compressor plus twice the decompressor) plus the archive, on enwik9, 1 GB (PUBLISHED, https://hutter1.net/prize/hrules.htm).
- **LTCB.** PUBLISHED, https://mattmahoney.net/dc/text.html.
- **Calgary Challenge.** 7,700 B PPMd-compressed decompressor archive + 572,465 B data + 5 B overhead = 580,170 B, a PAQAR-based entry by Rhatushnyak, 2010 (PUBLISHED, http://mailcom.com/challenge/). mattmahoney.net/dc/calgary.html lists only the total.

All three work on payloads of 3 MB to 1 GB, where a 1-2 KB decoder is noise. The smallest LTCB CM/DMC rows (PUBLISHED; s = zipped source, x = zipped executable):

| Codec | Size | Model |
|---|---|---|
| fcm1 | 1,116 s | order 0-1 (Muraviev 2008) |
| dmc | 2,220 s | DMC |
| hook v0.2 | 2,556 s | DMC variant, 208.2 MB on enwik9 against dmc's 222.6 MB |
| PX v1.0 | 3,054 s | PAQ1, fixed weights (Muraviev 2006) |
| fpaq2 | 3,429 s | CM |
| mtari 0.2 | 4,156 s | CM |
| smac 1.20 | 4,356 x | CM |

cm2's counted region zips to about 680-710 B, depending on whether the markers and filename are included; raw deflate is 515 B (MEASURED). The earlier 705 B and 649 B figures were measured on different inputs and do not contradict each other. Either way cm2 sits in the lzw 0.2 (671 s) and ghost (696 sd) tier, where every public entry is far weaker in model class.

**(d) Decoder-plus-data golf scored by source size — the nearest objective match, UNMEASURED.**
- **golf.horse's wordlist board** scores the whole JS program, decoder plus data. Roadroller's minimal decoder "was initially adapted from a golf.horse submission… by Hasegawa Sayuri" (PUBLISHED, https://github.com/lifthrasiir/roadroller README). golf.horse returned 503, so its scores and rules were not fetched.
- **Cemetech wordlist contest:** decompressor plus compressed list, in eZ80 code (https://www.cemetech.net/forum/viewtopic.php?p=297424; known only from a search summary, thread not opened).
- **Roadroller** is a sparse-context logistic CM in JS, tuned per input by simulated annealing, "similar to Crinkler". Its defaults are 12 contexts, up to 150 MB, aimed at "typical 30 KB input", and the README suggests smaller learning rates below 10 KB (PUBLISHED, README).
- Roadroller was not run on T1-T3. That run is cheap and owed. Its emitted decoder line was not measured either, so the "~600-900 JS chars" figure remains an ESTIMATE.

**Concrete candidates:**
- **At 25 lines:**
  - (i) Crinkler-style cm2 with sparse masks and weights in the header, about 25-28 lines (ESTIMATE). The measured gain so far is ≤0.2%, so confidence that it wins by much is low.
  - (ii) Constant-level variants are not candidates, because both measured worse on T3: faithful PAQ1 rules +4.1%, and x4 boost alone +1.1%. Crinkler's whole rule set (x4 plus halving update) is +4.7% (all MEASURED, model-only, in-sample).
  - (iii) DMC in 25-35 lines (ESTIMATE). Unlikely to win: dmc.c is +33% against cm2 on T3 unprimed.
  - (iv) A Roadroller- or oneKpaq-style context-selected logistic mixer. Untested; the global-weight probe in (b) does not bear on it.
  - Overall: no *measured* public design beats cm2 at 25 lines, but the nearest public decoders and axis (d) were never run. That is untested, not "medium confidence".
- **At 48 lines:**
  - (i) Roadroller as an integer port, with annealed sparse contexts plus cmmix's match model: 30-38 lines plus 5 (ESTIMATE, unverified).
  - (ii) oneKpaq's existing design (boosted counts into a logistic mixer), ported.
  - (iii) lpaq1's bit histories. The cmmix NOTES estimate about 25 more lines (RECORDED), which goes past 48.
  - Measured public codecs ahead of cmmix at 8-32 KB: lpaq1 primed (about 0.2-1.2%, ~10x the source) and paq8l (9-15% primed, ~45x the source by non-blank lines). Low confidence either way about what fits in 48 lines.

### 3. How do we know ours are the best at these sizes?

We do not. The record supports only "Pareto-best among the panel's five families, on its own fixtures". The memo's front is lz-raw → lzdict → cm2 → cm2-plus → cmmix (RECORDED, memo:42).

**What evidence exists:**
- in-panel comparison, with refuters reproducing every size;
- full-size public tools used only as output ceilings;
- this session's MEASURED comparisons in §2:
  - cm2 ties PPMd primed and is 4-6% behind lpaq1 primed;
  - cmmix is within about 1% of lpaq1 primed;
  - paq8l is ahead of both: 13-20% ahead of cm2 primed, 9-15% ahead of cmmix primed;
  - both panel codecs beat every LZ and BWT codec measured;
- on five Canterbury files (asyoulik, cp.html, fields.c, grammar.lsp, xargs.1), cm2 is 12-20% smaller than xz -9e in the .xz container. Per file: cp.html 12.2%, the others 18.3-20.4% (MEASURED). Against raw xz the figures are 11.5-18.6%;
- a cmix comparison, "18-29% below cm2", is only partly supported. Byron Knoll's per-file Canterbury table (PUBLISHED, https://www.byronknoll.com/cmix.html) states no version, and the latest listed release is v21. "v20" is unsupported, and the per-file figures used were not recorded.

**What is missing:**
- No public tiny decoder has been ported into the subset and counted with count_lines.py.
- No run on axis (d): golf.horse, Roadroller.
- There are only two independent sources: T1 is a prefix of T2, and T3 is a prefix of T4 (RECORDED, and MEASURED by the runner).
- The constants were tuned on these fixtures (memo:36).
- The primer is by the same author and is Python. The real Plate text is not Python.
- Primed sizes include about 860 B of untyped harness (RECORDED, cm2/refute/notes.txt:7).
- Public baselines were run unprimed only, until this session. All primed public figures are difference-method approximations.
- Nobody has reimplemented cm2 from the Plate text alone.
- Typing and error rates are unmeasured.
- The T4 regeneration recipe is underspecified: confetti3.py prepended, /diag/ and /docs/ excluded (MEASURED).

**Deep-time bootstrap precedents** (PUBLISHED; none cited in the record):
- Nguyen & Kay, "The Cuneiform Tablets of 2015": a one-page VM spec (Chifir) plus a program, and Rosenthal's critique of it (https://blog.dshr.org/2016/03/long-tien-nguyen-alan-kays-cuneiform.html). A third-party implementer reports the Chifir spec is incomplete, with unspecified behaviours (https://permacomputing.net/Chifir/). That is a direct parallel to the spec gaps in §5.
- IBM's Universal Virtual Computer (https://en.wikipedia.org/wiki/UVC-based_preservation).
- The GitHub Arctic Code Vault on piqlFilm, with its five-language Guide and the Tech Tree (e.g. https://www.infodocket.com/2020/07/16/github-archive-program-the-journey-of-the-worlds-open-source-code-to-the-arctic/). piql's own preservation-VM page returned 404, so its content is unverified.

**What a rigorous test would be:**
1. **Freeze the objective:** typed decoder chars, plus Plate annex and known-answer-vector (KAV) chars, plus base-32 payload chars. Payload includes any per-payload header and the out-of-band n (about +3 B). Apply the subset rules with time and memory caps. Evaluate per payload rung (R1 ~6.5 KB, R2 ~30 KB, R3), with the decision rule stated in advance.
   - The rung matters: at R1, cmmix's typed total of 5,650-5,976 chars loses to cm2's 4,473-4,792 (RECORDED ESTIMATE, memo §2).
   - The annex differs by candidate: cm2 needs about 30-35 annex lines (memo §5); cmmix needs the 123-bit K, the multiply semantics and the precedence rules (cmmix REFUTE-NOTES "Spec gaps" 1-7).
2. **Build a held-out set:** Python by other authors, non-Python Plate-like text, the real mid_decoder.py and Listing One. Freeze all constants before running anything on it.
3. **Port public designs into the subset at fixed budgets:**
   - **25-line slot:** Crinkler-style masks and weights in the header, with an encoder-side greedy search; a faithful PAQ1 core; DMC; and fcm1 as a negative control.
   - **48-line slot:** oneKpaq, a Roadroller integer port plus match, PPM with exclusion and SEE (ppm-plus exists at 38 lines), and cmmix plus a verified match.
   - Each port gets its own Opus builder and refuter.
   - **Faithfulness gate:** each port must reproduce its public reference's output, or ideal code length within a stated tolerance, on a reference input before it counts. The 10,286 B PAQ1 "port" shows why.
   - **Tuning parity:** every candidate, the incumbents included, gets the same tuning budget on a tuning set separate from the held-out set.
4. **Keep out-of-budget references,** primed with the identical primer: paq8l (or paq8px/cmix), lpaq1 and PPMd.
5. **Report each held-out file separately,** with the spread across files rather than single numbers.
6. **Have someone reimplement each finalist from the Plate alone.**

Even then, the result is an empirical upper bound within the searched families. The absolute question is uncomputable (Kolmogorov).

### 4. How cm2 and cmmix work

**cm2** (`/home/user/paper-store/bootstrap/record-2026-10-18/stage0-panel/cand/cm2/dec.py`):
- **Contexts (:12).** Masks ms = (1<<8o)−1 for o in (0,1,2,3,4,6,8,12).
- **Buffer and init (:13-15).** buf = 12 zero bytes + primer + n bytes. The source is padded with 4 zero bytes. x is the first 4 bytes, read big-endian.
- **History (:17).** h = int.from_bytes(buf[i:i+12]). c0 starts at 1 and becomes c0·2+y after each bit (:33).
- **Key (:19).** key = ((h&q)|(q+1))<<8 | c0, stored as an exact dict entry. The sentinel bit keeps keys distinct across orders and c0 values; keys stay below 2^105.
- **Mix (:20-21).** s1 = 1 + Σᵢ n1ᵢ·2^i·(2 if n0ᵢ=0 else 1), and symmetrically for s0. i is the index into the order tuple.
- **Probability (:22).** p = s1·4094//(s0+s1)+1, which lies in [1,4094]. NOTES.md:9 says [1,4095], which is slightly loose. Since p ≤ 4094, xm never reaches b.
- **Coder (:26-30).** xm = a+((b−a)>>12)·p; y = x ≤ xm. While a>>24 == b>>24: a = a<<8&M, b = b<<8&M|255, x = x<<8&M|s[k].
- **Primer (:23-24).** Primer bits are read from buf, not decoded, and still train the model.
- **Update (:31-32).** n_y += 1; n_¬y = min(n_¬y, n_¬y//4+2).
  - From 1000 the opposite count decays 1000 → 252 → 65 → 18 → 6 → 3 → 2 → 2. Once nonzero it never falls below min(n, 2) (MEASURED). PAQ1's rule has the same floor of 2; Crinkler's floors at 1.
  - So once a node has seen both bit values it can never be "deterministic" again. The x2 boost fires only on nodes that have never seen the other bit.
- **Flush and container.** The encoder flushes (a>>24)+1 (enc.py:36), which is valid with zero padding. n travels out of band.

**cmmix** (`/home/user/paper-store/bootstrap/record-2026-10-18/stage0-panel/cand/cmmix/dec.py`):
- **Tables (:19-24).** For x in 0..4095: sq[x] = s>>20, then s += s·((4096<<20)−s)>>40, starting from s = 1,460,000; st[sq[x]>>2] = x−2048.
  - Max squash error is 0.985/4096. sq spans 1..4094, so p is never 0 or 4096. Every st entry is written, and st spans −1778..2047 (MEASURED).
  - Last-write-wins gives each 4-wide bin its largest x. That biases stretch upward by up to one bin and makes the ends asymmetric (st[0] = −1778, st[1023] = 2047). The cost is negligible: a full-resolution st gives 6,948 against 6,950 on T3 (RECORDED, cmmix/ablation_T3_dec60.txt:13 per one refuter; another refuter's grep did not find it, so the source is disputed).
- **History (:28-32).** h is the last 7 bytes.
- **Word hash (:33).** wh = (wh+c+1)·773·((K>>c)&1) & 0xFFFFFFFF, where K is a 123-bit mask selecting exactly [0-9A-Za-z_] (MEASURED).
- **Line context (:34-35).** r = b[min(pl+i−ls, ls−1)]<<8 | min(col,40).
- **Context vector (:36).** H = [0, orders 1-4, wh, r, h·G>>9]. The "order 7" entry actually reaches only about 6.25 bytes, because the slot uses only bits 9..49 of h·G (MEASURED). Its ablation costs 10 B on T3: no_o7 6,960 against 6,950 (RECORDED).
- **Slot (:41).** ((H·8+q)·G>>20) + c0·P & (2^24−1). There is no collision check.
- **Match (:37-39, :42, :65).**
  - mt maps a 6-byte hash to the last position;
  - a table hit counts as length 1, with no verification;
  - length is capped at 15;
  - input slot = M − 2·ml − predicted bit;
  - with no live match, the input still reads slot M or M−1, from a stale or zero pointer;
  - the match is killed on the first wrong bit.
- **Mixer inputs (:43-47).** S = st[T[slot]>>6] for 9 inputs. d = Σ(w+u+2v)·S >> 18, clamped to ±2047, and p = sq[d+2048]. The weight sets are selected as:
  - w by c0 + 256·match-flag;
  - u by (c1, c0);
  - v by an 8-bit order-2 hash with c0.

  Their index ranges do not overlap; W has 131,584 entries.
- **Counters (:57-59).** T += ((y<<16)−T)·R[N]>>16, with R[n] = 655360//(10n+12) (54,613 down to 2,100) and N capped at 30.
- **Mixer update (:60-63).** All three selected sets get += S·((y<<12)−p)>>10.
- **Coder (:51-55).** lpaq1's coder without the low-bits term or the p adjust. It renormalizes first and starts from zero.

### 5. Artificial limitations

**Line budget.**
- cm2 has no match model, no word model, no SSE and no learned weights. cm2-plus adds word and match for +9 lines by count_lines (its docstring says +10). The gain is 0.8% on T1, 1.3% unprimed / 1.7% primed on T3, and 2.9-3.0% on T4 (RECORDED: cm2 NOTES.md:35, :41-42; memo:52).
- cmmix lacks bit histories and APM:
  - APM was tried: 4 lines for −0.07% (RECORDED, cmmix NOTES.md:37);
  - the gap to lpaq1 on T4 unprimed is 3.7%, 114,762 against 110,653 (MEASURED);
  - adding bit histories would take about 25 lines of states plus a StateMap (RECORDED estimate).
- Extra lines cost typing: cmmix's typed total of 5,650-5,976 chars loses to cm2's 4,473-4,792 (RECORDED ESTIMATE). Neither total includes the uncounted spec comments and annex.

**Typed subset.**
- Without floats or imports, squash/stretch must be built in integers. The line cost to cmmix is about 6 lines (ESTIMATE; no record source found). Full-resolution stretch would save about 2 B on T3 (RECORDED per one refuter; disputed, see §4). Not worth lifting.
- The subset does not forbid integer tables, so cm2's lack of a logistic domain is a budget choice, not a subset limit.

**Design choices.**
- **cm2's exact dict.** Memory is unbounded.
  - Peak RSS on T1: 44 MB unprimed (MEASURED). The record gives 56 MB unprimed and 103 MB primed (RECORDED, cm2/results.json).
  - On T4: 1.19-1.21 GB, and decode takes 62-68 s (MEASURED).
- **Bounding cm2's dict was tried only one way:** an unchecked multiplicative hash, with no checksum and no probing (record-2026-10-18/scripts/cm2b_enc.py:15).
  - That costs +6% on T3 at 2^24 (7,725 against 7,257) and +57% on T4 at 2^22 (188,105 against 119,866); 2^20 gives 270,940 (RECORDED, bootstrap/RECORD.md:322-325).
  - A checksummed or bucketed map in the PAQ1 or lpaq1 style (PAQ1: 8-bit checksum plus 3-way probing, paq1.cpp:129-135) was never tried. Bounded cmmix (cm1) loses only about 1.5% at 2^22 (RECORDED, RECORD.md:322-328).
- **cm2 order reach.** Max order is 12, and D is hardcoded rather than derived.
- **cm2 weights.** The 2^index weights are fixed and tied to tuple position.
- **Coder (both).** Carry-less, without lpaq1's low-bits term. When b−a < 2^12, (b−a)>>12 = 0, so xm = a and the prediction is ignored outright. The total coder overhead is small: cm2 on T3 is 7,257 B coded against 7,250 B ideal, about 7 B (0.1%) including the flush (MEASURED against RECORDED).
- **cmmix tables.** Hash slots have no checksum, and match slots share the hashed table. 2^22 slots cost +57 B (RECORDED, cmmix NOTES.md:37; the fixture is not stated, probably T3: m22 7,007 against 6,950 in results.json). Peak memory is 301-384 MB (MEASURED).
- **cmmix match.** It is unverified, uses one hash, and is capped at 15.
- **cmmix weights.** They are unclamped: |w| < 2^17 has been observed, not proven.
- **cmmix porting.** Products need at least unsigned 64-bit arithmetic, wrapping or exact; both give identical bytes (RECORDED, dec.py:7; REFUTE-NOTES:21). A port to C's signed types would hit undefined behaviour on overflow, and 32-bit products break. The wrap is provably harmless because only low bits ≤ 49 are consumed (analysis of dec.py:36, :38-39, :41). The 123-bit K constant is a typo risk.

**In-sample tuning.**
- All constants were tuned on T1-T4, which amount to two sources.
- The primer gain of 5-9% is same-author and Python.
- cmmix's small-file win over lpaq1 disappears once both are primed (MEASURED, difference method).
- The fix: per-payload parameters in the stream (the Crinkler/ZPAQ pattern) plus held-out evaluation.

**Spec gaps.**
- Python semantics carry the meaning:
  - setdefault aliasing;
  - parallel assignment;
  - bool as int;
  - Python operator precedence, e.g. `b[mp]>>7-j&1==y`;
  - floor shifts on negatives;
  - last-write-wins st;
  - sequential updates to colliding slots.
- The 15-byte KAV still passes with the bug `x < xm`, which corrupts output from T1 byte 89 on (RECORDED, STAGE0-CRITIQUE.md:15-16). The fix is a primed vector of ≥1 KB, a step trace, and a CRC every ~1 KB.

**Inherent to the class.**
- Linear count mixing (cm2) cannot learn which orders are reliable.
- Small files are limited by learning speed, so the primer buys more than extra model lines.
- Arithmetic coding gives no error gradient: one typo destroys everything after it.
- Incompressible input expands: cm2 turns 6,000 random bytes into 6,480, +8% (RECORDED, cm2/refute/notes.txt:6). Not measured for cmmix.

### Closing table

| Codec | Source size (excludes uncounted spec/annex) | T1 primed | T3 primed | Nearest public comparator (size) | Comparator T1 / T3 primed |
|---|---|---|---|---|---|
| cm2 | 25 lines / 1,010 chars (RECORDED, MEASURED) | 2,633 (RECORDED = MEASURED) | 6,914 (RECORDED = MEASURED) | lpaq1, 484 C++ code lines (MEASURED); Crinkler, 210-220 B x86, no text numbers (PUBLISHED, dce.html) | lpaq1: 2,527 / 6,548 (MEASURED, difference method, same primer, ESTIMATE-grade as a primed decoder) |
| cm2 | same | same | same | PPMd o16 (library) | 2,672 / 6,979 (MEASURED, difference method) |
| cm2 | same | same | same | paq8l -8, 2,171 code lines (MEASURED); out-of-budget ceiling | 2,336 / 5,788 (MEASURED, difference method, cm2's primer, compressed only; unprimed 2,677 / 6,233 round-trip verified) |
| cm2-plus | 34 lines / 1,465 chars (RECORDED) | 2,612 (RECORDED) | 6,794 (RECORDED) | PX v1.0, 3,054 B zipped source (PUBLISHED, text.html) | not run |
| cmmix | 48 lines / 2,302 chars (RECORDED, MEASURED); plus 822 chars of in-region spec comments not counted (MEASURED) | 2,542 (RECORDED = MEASURED) | 6,629 (RECORDED = MEASURED) | lpaq1, 484 code lines (MEASURED); Roadroller, ~600-900 JS chars (ESTIMATE, unmeasured) | lpaq1: 2,523 / 6,553 (MEASURED, cmmix's primer, difference method) |
| upkr (public LZ) | 86 C code lines (MEASURED) | 3,016 (MEASURED, difference method, ESTIMATE-grade as primed) | 8,258 (same) | – | – |
| LZMA2 tuned (public) | library | 2,968 (MEASURED, difference method, ESTIMATE-grade: Python's lzma has no preset-dictionary API) | 8,071 (same) | – | – |

Work files from this session are in the scratchpad:
- `<tmp>`
- `<tmp>` (its PAQ1 weight variant is mis-ported; superseded by the refuters' re-runs)
- the refuters' re-runs: `<tmp>` (cmvar2.py, out_*.txt, p8/)
- the code refuter's `refute-code/` directory (var2.py, t1.py): its exact location was not reported, and it is presumed to sit under the same scratchpad.

Nothing under `/home/user/paper-store` was modified.