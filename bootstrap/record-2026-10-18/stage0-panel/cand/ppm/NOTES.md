# ppm: stage-0 PPM, dec.py = 25 counted lines

**Model.** Contexts are the 6..0 preceding bytes (primer + output so far),
one dict keyed by the exact context bytes (no hashing); a table maps byte to
count: a new byte enters at 2, each repeat adds 4. Escape weight
2*distinct-1 (PPMD with a half-count discount; order 0 has no escape and
starts with all 256 bytes at count 1). Decoding walks orders 6..0 (an empty
context escapes for free). Full exclusion of every byte seen
in a higher context. Update exclusion: update orders 6 down to the first
table already holding the byte. No rescaling.

**Coder.** Multi-symbol range decoder, x < g < 2^64, g starts at 1;
before each decode `while g < 2^56: x = x<<8 | next byte`; then
w = g // total, walk cumulative weights, x -= cum*w, g = f*w. Encoder
propagates carries into its output, drops the always-zero first byte and
flushes 7 bytes. A 32-bit build (dec32.py, 27 lines) adds halving at
total 60000; same sizes ±6 B.

**Plate must print:** the ASCII table (already there); "context = last k
bytes, k = 6..0"; the count rule (new 2, +4, order 0 all 256 at 1); escape
= 2*distinct-1, none at order 0; exclusion and update-exclusion in one
sentence each; the range-decoder recurrence with its two constants
(2^56, 64-bit); symbol order inside a table = first-insertion order (a
reimplementer must copy it); the primer rule (decoder first
replays primer bytes through the model without decoding).

**Measured** (primed = primer.txt + own dec text): T1 2,896 / T2 4,768 /
T3 7,574 / T4 143,711 (xz 145,264). T4 decode 6.6 s, encode 4.1 s.
Orders on T1/T3 primed: K2 3,237/10,761, K3 2,956/8,445, K4 2,895/7,827,
K6 2,892/7,572 — order costs no lines; K5–6 is the knee. The primer buys
only ~6 % on T1 (3,092 -> 2,896).

**Next lines (measured, dec_plus.py, 38 lines):** SEE on the escape
(cells [escapes, visits] per order × min(distinct,3) × len(bin(total)),
shrunk to the PPMD prior with weight 16) plus PPMd-style inheritance
(new byte enters at 2 + 8c/n from the order where it was found): +13
lines buy T1 -2.7 %, T3 -2.3 %, T4 -2.1 % (2,817 / 7,401 / 140,654).
Removing exclusion or update exclusion saves 2 lines each and costs
4–8 %. Beyond that, T1's cost is order-1/2 coding in fresh contexts,
which only mixing (CM) attacks.
