# Refutation of cmmix (dec.py 48 lines, dec40.py 39 lines)

All runs are under `nice -n 10`, with system python3 3.13, using the harness `rh.py`. The harness loads only `enc.make_encoder` and `decode` from each decoder file, by path. Logs are in `small.log`, `big.log` and `big40.log`.

## Reproduced exactly
- count_lines: dec.py has 48 lines and 2302 chars, dec40.py has 39 lines and 1863 chars. Neither has violations.
- Every claimed size reproduced to the byte, primed and unprimed, for T1–T4 and both variants. Primed means primer.txt followed by the variant's whole file.
- Round trips are byte-exact on:
  - T1–T3 for both variants, primed and unprimed
  - T4 primed for both variants
- T4 unprimed was only encoded, to check its size; it was not decoded.
- Hash seeds 0 and 4242 give identical compressed bytes from two encoder runs, and identical decoded output:
  - T1–T3: both variants, primed and unprimed
  - T4 primed: dec.py only
- Known-answer vectors reproduce for both variants.
- The CLI decode path (`python3 -I dec.py ...`) is byte-exact on T1.
- Timings are close to the claims:
  - T4 primed, dec.py: decode 110 s, encode 112–115 s
  - T4 primed, dec40.py: decode 78 s
  - T3 primed decode: 6.8 s for dec.py, 4.9 s for dec40.py
- The 64-bit wrap claim holds. A copy of dec.py with every hash multiply masked to 2^64 (`wrap64_dec.py`) gives identical bytes on T1 and T2.
- Tables:
  - sq is monotone, its maximum step is 4, sq[2048] is 2048, and its maximum error is 0.985/4096.
  - Every entry of st is written.
  - K is exactly [0-9A-Za-z_].

## Adversarial reading
- The counted region is self-contained: no globals, no hidden tables, and nothing is imported in it.
- No test content leaks. The longest substring that dec.py, dec40.py or enc.py shares with any T file is 22–31 chars of generic Python, such as `if __name__ == "__main__":`.
- The primer sizes count the untyped harness and docstring. If the primer is only primer.txt plus the counted region:
  - with comments: T1 2553 (+11), T2 4212 (+9), T3 6658 (+29)
  - code lines only: T1 2584 (+42), T2 4248 (+45), T3 6671 (+42)
- Constants were tuned on T1–T4 (tunep.py and the ablations). The small-file wins over lpaq1 are in-sample.

## Spec gaps: what the Plate must add for a bit-exact second implementation
1. Python operator precedence. `b[mp] >> 7 - j & 1 == y` means `((b[mp] >> (7-j)) & 1) == y`; read with C precedence it decodes wrongly.
2. `>>` floors on negative values (arithmetic shift) in the T, w and d updates.
3. Booleans are 0/1 integers, `a or b` returns a value, and tuple assignment evaluates the right-hand side first.
4. When two slots in X collide, the updates run in order. The st table is filled last-write-wins.
5. K is a 123-bit constant. A fixed-width implementation needs a table or two 64-bit words.
6. Multiplies must be unsigned modulo 2^64; signed overflow is undefined behaviour in C. No bound on the weights is proven.
7. The container: the 4 leading zero bytes are implied, and both the tail and the zero padding are implied. n is external (+3 B if carried). The primer is defined as the exact file bytes.
