# stage1/ — cm1, the bounded-table stage-1 CM (key `stage1`, 2026-10-18)

## Built
- `cm1_dec.py` (139 lines; 74 counted; no imports, floats or `/`):
  `decode(src, n, primer, k=22) -> bytes`. It is cmmix's family (orders
  0-4, 7-byte, word and line-above contexts, a match model, three
  integer logistic mixers, cmmix's coder), with bounded tables:
  - `T`: 2^k + 131,584 16-bit slots, each a 12-bit p << 4 | a 4-bit
    count. Orders 0/1 are direct. The other six contexts are hashed once
    per nibble into 16-slot buckets: slot 0 is a 16-bit check, lookup is
    2-way (t, t^16), and the bucket with the lower count is evicted.
  - `mt`: 2^(k-2) 32-bit positions. `W`: 1,184,256 int32 weights (fixed).
  - At k=22 the tables total 8.65 + 4.19 + 4.74 = 17.6 MB.
- `cm1_enc.py` is derived from the decoder's marked region, as in cmmix.
- Two known-answer vectors (k=16; primed k=18): `cm1_dec.py --kav` PASS.
- `bench.py` (harness), `results.jsonl` (every row below).

## Measured
Unprimed, in bytes. Time and peak RSS are for the T4 decode process.

| k | tables MB | T1 | T3 | T4 | T4 no-check | s | RSS MB |
|---|---|---|---|---|---|---|---|
| 16 | 5.2 | 2,980 | 7,930 | 143,932 | 154,987 | 86 | 19.7 |
| 18 | 5.8 | 2,835 | 7,196 | 124,409 | 136,360 | 84 | 20.0 |
| 20 | 8.2 | 2,796 | 6,930 | 116,210 | 125,025 | 86 | 23.2 |
| **22** | 17.6 | 2,792 | 6,896 | **112,999** | 117,760 | 85-97 | **32.2** |
| 24 | 55.3 | 2,791 | 6,894 | 112,075 | | 95 | 77.7 |
| ref 2^24 | | 2,799 | 6,950 | 114,762 | | 115 | 382.6 |
| cm2 | | 2,884 | 7,257 | 119,866* | | | 96 (T3) |

\* The task's figure, not re-run here.

- **Check byte:** it pays at every k: 4.2% on T4 at k=22, 7.7% at k=16.
  Without it, T3 is 8,549 at k=16 and 7,000 at k=22.
- **Round trips:** all byte-exact; identical under PYTHONHASHSEED 0/4242/
  random (T1; T4 k=22 under 4242). Edge inputs pass; random +1.6-1.8%.
- **Timings:** shared machine, 3 jobs at once, ±15%.
- **T4 ablations:** match table 2^20 at k=18 121,135; smaller mixers at
  k=22 114,855-119,597; slower rate 114,858.
- **T3 path, k=16 / 22:** 1-way reset 8,446 / 6,943; 2-way 7,906 / 6,929;
  direct o0/o1 7,754 / 6,927; 12-bit slot 7,724 / 6,896 (not on T4).
- **Primed** (primer.txt + cm1_dec.py), k=22: T1 2,504, T3 6,556.

## Recommendation: k = 22
On T4 it is 1.5% under the 2^24 reference and 5.7% under cm2, at a 32 MB
peak against 383 MB. k=20 saves 9 MB for +2.8%. k=24 buys 0.8% for
+45 MB. At k ≤ 18 it loses to cm2.

## Spec questions
1. The user said "not megabytes"; the task allows tens of MB. Under 1 MB
   this family cannot beat cm2 on T4: the mixer alone is 4.74 MB, and
   k=18 (5.8 MB) already loses.
2. `memoryview.cast` assumes 2/4/4-byte H/I/i. A Python without it needs
   list or bytearray storage (not built).
3. On overflow, int32 weights raise an error rather than wrap. That was
   never seen, but no bound is proven.
4. n and k travel out of band. The R2 glue must state both.
