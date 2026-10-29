# cmmix: bitwise CM + integer logistic mixing (dec.py 48 lines, dec40.py 39)

**Model.** Bits are coded MSB-first, and c0 is the partial byte. Each slot
holds a 16-bit probability T and a hit count N (at most 30). Contexts:
exact orders 0-4, hashed order 7 (`h*G>>9`), an identifier run (bitmask
K), and the line above plus the column. dec.py adds a match model: a 6-byte hash
gives the last position, and min(len,15) plus the predicted bit picks a
slot. Slot index = `((H*8+q)*G>>20) + c0*P & (2^24-1)`, with G=0x9E3779B1
and P=0x6F4F2A1.

**Mixing.** Inputs are stretch(T). Weight sets are picked by c0 (plus a
match flag), by (c1,c0), and in dec.py by an 8-bit order-2 hash. The sets
are summed, clamped to +-2047 and squashed. Update:
`w += S*((y<<12)-p) >> 10`, with init 16384.

**Tables.** squash by integer Euler steps from s=1460000 (error under
1/4096); stretch by inversion. Rate R[n] = 655360//(10n+12).

**Coder.** A carry-less 32-bit binary arithmetic coder that renormalizes
first, with x1=x2=x=0 at start. It drops 4 leading zero bytes and writes
the shortest tail. n comes from outside the payload (+3 B if carried
inside). enc.py is generated from the decoder text.

**T3 ablation, unprimed** (full = 6950 B):

| Removed | Cost | Lines saved |
|---|---|---|
| match | +105 | 5 |
| word | +182 | 1 |
| line-above | +47 | 2 |
| order 0 | +121 | 0 |
| mixer 2 | +76 | 0 |
| mixer 3 | +6 | 2 |
| both extra mixers | +190 | 2 |
| adaptive rate | +1505 | about 1.5 |

Mixer 3 costs 6 B on T3 but saves 1.6% on T4. 2^22 slots cost +57 B. APM (4 lines, -0.07%) dropped.

**What the Plate prints.** The listing is the specification. Beyond it,
the Plate states: MSB-first bytes, that n is given, the primer order, and
that multiplies may wrap mod 2^64 (checked byte-identical). Weights are
not clamped: |w| < 2^17 was observed, so 32-bit weights are safe in
practice, not by proof.

**The next 10 lines.** For dec40, adding the match model (+5) and mixer 3
(+2) gives dec.py: -1.7% on T3 and -9% on T4. For dec.py, every addition
measured gains under 0.1% per line. The next real step is lpaq-style bit
histories with a state map (~25 lines).
