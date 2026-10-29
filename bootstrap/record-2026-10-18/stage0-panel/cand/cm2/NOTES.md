# cm2: stage-0 count-mixing decoder, 25 typed lines

**Model** (PAQ1-style; no tables, no stretch/squash). Orders are
(0,1,2,3,4,6,8,12) with EXACT contexts: key `(ctx_o | 2^(8o)) << 8 | c0`.
There is no hash to specify; any collision-free map works. Each node
holds [n0,n1]. Order i has weight 2^i, doubled if the node is
deterministic:
`s1 = 1 + sum(n1 << (n0==0) << i)` (s0 likewise), and
`p = s1*4094 // (s0+s1) + 1`, so p lies in [1,4095].
Update: `n_y += 1`, `n_!y = min(n, n//4+2)`.
The order tuple is data: orders (0,1,2) run the same 25 lines.

**Coder**: lpaq1 carry-less 32-bit. `xm = a + ((b-a)>>12)*p`; y=1 takes
[a,xm]. Bytes shift out while the top bytes of a and b are equal. The
decoder seeds x from 4 bytes and pads the source with 4 zeros. The
encoder flushes one byte, (a>>24)+1. n travels out of band.

**Priming**: primer bits update the model and are not coded.

**What the Plate prints**: the 25 lines, plus the Python semantics they
use:
- `>>` and `//` on non-negative ints, and bool as 0/1;
- `dict.setdefault`, `enumerate`, `int.from_bytes(..,'big')`;
- buf is prefixed with D=12 zero bytes, so no index is negative.

Masks: a, b and x are 32-bit (M); s0 and s1 fit in 64 bits.
Memory: 1.2 GB on T4 in CPython, about 100 MB in C.

**Measured** (bytes, unprimed/primed):

| | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| cm2, 25 lines | 2884/2633 | 4676/4372 | 7257/6914 | 119866/119211 |
| orders 0-2 only | 3282/3117 | 5899/5727 | 10271/10137 | 220970/220954 |
| +9 lines | 2860/2612 | 4633/4328 | 7160/6794 | 116359/115669 |

The 25-line version beats xz on every fixture and ppmd on T4. On T2 it
is level with lpaq1.

**Next 10 lines (measured)**: dec_plus.py (+9 lines) adds an
identifier-word context and a match model (last 6 bytes, weight
min(L,32)<<5). It gains 0.8% on T1, 1.3–1.7% on T3 and 2.9% on T4.

Simulated on T3:
- SSE stage: 0%.
- Adaptive count-domain weights: −0.3%.
- More orders: −0.2%.

At 8–32 KB the model is limited by how fast it learns. Lines spent on
the model buy about 1%. The primer is free and buys 5–9%. So type the
25 lines and spend the effort on the primer text.
