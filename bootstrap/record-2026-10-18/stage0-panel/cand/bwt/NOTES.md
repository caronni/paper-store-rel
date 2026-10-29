# bwt — stage-0 Burrows-Wheeler decoder

**Files.** `dec.py`/`enc.py` primary (39 lines, 1,837 chars); `dec_mtf.py` (27);
`dec_tiny.py` (23, no priming); each with its `enc_*.py`. Container: 4-byte
primary index + coder bytes; n printed beside it.

**T3 (unprimed/primed):** tiny 8,652; mtf 8,370/8,326; cm 8,204/8,188 (bzip2 8,464).

**Coder (all).** Carryless 32-bit binary arithmetic coder: `m = a + ((z-a)>>k)*p`,
bit 1 iff `x <= m`; while top bytes of a, z agree shift in a byte (`z` fills with 255);
encoder flushes one byte `(a>>24)+1`, decoder pads with zeros.

**Counters.** `[p, d]` from `[32768, 3]`: bit 1 `p += (65536-p)*2//d`, bit 0
`p -= p*2//d`, then `d = min(d+2, cap)` (rate 1/(count+1.5)).

**dec.py model (coder ii, no MTF).** Bit tree c = 1..255, MSB first. Counters: order-0 `c`;
order-1 `(b, c)`; match `(e, min(run,15))`, where `e` = 1+expected
bit if the partial byte agrees with the last byte b, 3+bit if with the last *different*
byte f, else 0. Caps 31/31/255. Logistic mixer, weights per node c (3 x 21845, 16.16):
`p = Q[clamp(sum w_i*S[p_i>>4] >> 16)]`, `w_i += S_i*((y<<12)-p) >> 11`
Q = integer Euler of the logistic ODE (`j=2^31; j += j*(2^32-j)>>40`),
S its inverse, default -2048. **mtf model (coder i):** MTF rank, bit tree, average of
counters `(min(prev rank,2), c)` cap 63 and `(min(zero-run,7), c)` cap 513.

**Priming.** Model-only warm-up over the primer's BWT (suffixes sorted bytewise, each
emits its preceding byte): 2 lines, 0.2-1.9 % (T1 most), ~0 on T4.
Prepending the primer to the block LOSES (T1 3,146 -> 6,918): its symbols must be coded.

**Plate must print:** container layout; the coder's rules; counter update; Q
recurrence + S inversion; context keys and caps; mixer init/rate; inverse BWT = stable
sort of positions by byte, `i = T[i]; out[k] = L[i]`; primer sort rule. Widths: a, z, x,
m 32-bit unsigned; `j*(2^32-j)` 64-bit; weights signed, |w| < 2^21 measured on T4, so
the dot product needs 64 bits; `>>` arithmetic.

**Memory.** n bytes + n-entry LF vector (4n fixed-width), ≤ 66K counters. Python
peak 188 MB on T4; the primer sort holds ~h²/2 bytes of slices (port: sort indices).

**Next 10 lines buy ~1 %:** third match slot (T3 −0.4 %), APM on (e, run) (−0.4 %),
order-2 input (−0.25 %). BWT at 8–32 KB is near its ceiling (ppmd/lpaq beat it ~10 % on
T2). Cheapest per line: dec_mtf, 27 lines, within 2 % of dec.py on T1–T3.
