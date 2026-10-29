# lzdict: LZ77 over a primed window, stage 0 (20 typed lines)

**Model.** The window starts as the primer. Each token is an integer `l`,
coded under the previous token's class (start / literal / match). `l = 1` is
a literal, coded as `256 + byte` in a literal tree. `l >= 2` is a match,
followed by its distance `d`; the copy may overlap. The encoder keeps
`l <= 255`.

**Integers.** Interleaved Elias-gamma: `v = k = 1; while bit(b+k): v =
2v + bit(b+64+v)`. A continuation bit is keyed by depth, a data bit by its
tree node. Tree-keying both cost 7 % on T3.

**Coder.** LZMA-style binary range decoder. Start r = 1, x = 0. Before each
bit, while r < 2^24, shift in one byte. `t = (r>>12)*P`, `y = x >= t`.
`P += ((1-y)*4096 - P >> s) + y`, with s = 4 for keys below 4096 and 5 for
distances. P starts at 2048 and stays in [16, 4081]. All values are 32-bit.
`src` is padded with 8 zero bytes.

**Encoder.** Builds Pareto matches from 1- and 2-byte tables plus a 3-byte
chain 128 deep. It runs a backward DP over the 3 states, with bit prices
taken from the previous pass's coder, for 12 passes. Optimal parsing beats
greedy by 3.1 / 4.1 / 5.8 % on T1/T2/T3 unprimed and by 5.0 / 5.3 / 6.2 %
primed.

**Dictionary.** The primer saves 5.1 % (T1) and 2.9 % (T3); raw 8.8 / 4.6 %.

**raw variant (15 lines).** No entropy coder: gamma(l), literals 1 + 8 bits,
distances Exp-Golomb order 9, exact DP; 9 % (T1) and
7 % (T3) bigger than main.

**Plate must print:** 2^24, 12, 2048, shifts 4/5 at 4096; key bases
512·min(prev, 2), 1536, 4096, data +64; byte order; overlap copy; window =
primer, output = what follows it.

**Measured negatives (unprimed):** ROLZ order-1 +11–22 %; repeat-last
distance +1 % (21 reps in 4,006 matches); previous-byte literal contexts
+0.2–2.5 %; distance keyed by length class ±0.3 %.

**Next 10 lines.** Main lands on xz -9e on T3 (8,545 against 8,544) and is
5 % worse on T4. The context changes I measured inside the LZ give at most
0.6 %. My unmeasured estimate is a few percent from 10 more lines. A
context-mixing stage 1 carried on R2 buys more.
