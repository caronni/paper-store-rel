# holo1 <-> holo3 certificate-level parity

Matching payload-tile decode is the parity measure, not the fountain close: a close stops at the first sufficient symbol surplus, so its margin can hide per-tile weakness. Both sides below are FULL HARVEST -- holo1's recorded full re-decode states vs holo3 run with `--complete` (close deferred to exhaustion).

Sanity: both trees close byte-exact to identical payloads (the manifest sha column), so bit-level certificate conflicts are excluded by construction. Address parity is the yield measure.

| volume | holo1 | holo3 | matched | missing | extra | miss % | verified sha |
|---|---:|---:|---:|---:|---:|---:|---|
| e029 HP K (c2-r0700) | 1940 | 1940 | 1940 | 0 | 0 | 0.00% | OK (465580 B) |
| xerox c3-cmy7 | 720 | 786 | 716 | 4 | 70 | 0.56% | OK (301600 B) |
| xerox c2-cmy8 | 5370 | 5422 | 5334 | 36 | 88 | 0.67% | OK (718413 B) |
| xerox c2-k (c2-r0700) | 1930 | 1924 | 1922 | 8 | 2 | 0.41% | OK (465580 B) |
| xerox c2-cmy7 (PK-FINAL) | 1559 | 1586 | 1537 | 22 | 49 | **1.41% FLAG** | OK (686859 B) |
| sheet I pooled cmy8 | 5297 | 5326 | 5193 | 104 | 133 | **1.96% FLAG** | OK (1798761 B) |

**FLAG: holo3 misses >1% of holo1's certificates on: xerox c2-cmy7 (PK-FINAL), sheet I pooled cmy8**

`holo1` above is the certificate count in the state that could actually be read. Two of those states predate the colour-uplift campaign, whose PK-FINAL re-decodes reached higher on the SAME archived scans -- the per-volume sections carry that number as `best on record` so the comparison is not oversold.

## How the two sides were obtained

- **holo1**: `extract_holo1_certs.py` mmaps the state and parses ONLY the top-level `"certificates"` array. A full `load_session` decompresses every inlined evidence block (~7x the file size in RAM; measured 931 MB peak for the 131 MB colour state), which the 3.5 GB sheet-I state does not survive alongside anything else. The slice path was cross-checked against a real `load_session` on two states (K and colour) and produced the IDENTICAL sorted address list both times.
- Every holo1 state's own close record is `verified`, with a payload sha equal to the acceptance manifest's. That is what licenses the bit-level sanity claim above -- it is measured here, not assumed.
- **holo3**: `TileOutcome` rows with `result=certified`, deduped on (page, ty, tx, stream_id). Deduping matters on the pooled multi-capture sheet: step 7 emitted 6072 certified rows for 5326 distinct addresses, because the same tile re-certifies from more than one capture.
- All six holo3 runs used `--complete`, which gates the close solve to `final=True`, so the work loop cannot break early on a sufficient-surplus close and runs to exhaustion. The final close still happens, so every `verified sha` above is a real close.

Step 7 needed two attempts. The first died at ~33 min with the guard AND the decode both gone, no output and no RSS kill recorded. Re-running it detached (double-fork + setsid) survived 1h52m to a verified close at a 47.86 GiB peak, and a sibling watcher process was independently killed at ~40 min -- so the first death was the harness reaping a long background task, not memory. Both attempts ran at `--workers 8`, so step 7 is on the SAME footing as the other five; no reduced-worker refooting was needed. Record: `step7-ledger.jsonl`.

## step 2 -- e029 HP K (c2-r0700)

- holo1 state: `scratch/e028/holo-c2-r0700-q07-ink-counting/receive.state`
- holo1 format row: `c2-r0700@3392x2368`
- holo1 certs by stream: {'main': 1940}
- holo1 epoch: PK-FINAL full re-decode; best on record 1940 (1940/1961 = 98.9%, the e029 headline)
- holo3 harvest: exit 0, wall 655.7 s, child max RSS 12.75 GiB, 465580 B, sha_ok=True
- holo3 certs: 1940 by stream {'main': 1940}
- holo3 TileOutcome rows: {'tile_outcome_rows': 7375, 'results': {'below_attempt_floor': 852, 'certified': 1940, 'attempted_failed': 4583}}
- matched 1940 / holo1-only 0 (0.00%) / holo3-only 0
- holo1-only by stream: {}
- holo3-only by stream: {}

## step 3 -- xerox c3-cmy7

- holo1 state: `scratch/in/holo-xerox-c3-cmy7-counting-receive.state`
- holo1 format row: `c3-cmy7-p120-v0@2240x1536`
- holo1 certs by stream: {'main': 720}
- holo1 epoch: e032 print-day counting run; best on record 810 (colour-uplift PK-FINAL reached 810 on this sheet; the readable state holds the e032 run at 720)
- holo3 harvest: exit 0, wall 891.9 s, child max RSS 15.82 GiB, 301600 B, sha_ok=True
- holo3 certs: 786 by stream {'main': 786}
- holo3 TileOutcome rows: {'tile_outcome_rows': 3399, 'results': {'below_attempt_floor': 318, 'certified': 786, 'attempted_failed': 2295}}
- matched 716 / holo1-only 4 (0.56%) / holo3-only 70
- holo1-only by stream: {'main': 4}
- holo3-only by stream: {'main': 70}
- miss geometry: cols tx=22:2; 1/4 on the outer ring of the 35x24 tile matrix; 4 distinct tile positions
- holo1-only addresses (page, ty, tx, stream), up to 40:

```
  0   6  22 main
  0  12  19 main
  0  29  22 main
  0  31  23 main
```
- holo3-only addresses, up to 40:

```
  0   0   9 main
  0   0  20 main
  0   0  21 main
  0   1   0 main
  0   1  22 main
  0   3   0 main
  0   3   9 main
  0   3  20 main
  0   3  21 main
  0   4   0 main
  0   4  21 main
  0   5  21 main
  0   5  23 main
  0   6  21 main
  0   7   0 main
  0   7  20 main
  0   7  22 main
  0   8   0 main
  0   8  20 main
  0   8  22 main
  0   9   0 main
  0   9  21 main
  0  10  21 main
  0  10  23 main
  0  11   0 main
  0  11  20 main
  0  11  21 main
  0  12   0 main
  0  12  21 main
  0  12  23 main
  0  13  20 main
  0  13  21 main
  0  13  23 main
  0  14   0 main
  0  14  21 main
  0  14  23 main
  0  15  20 main
  0  15  21 main
  0  15  22 main
  0  16   0 main
```

## step 4 -- xerox c2-cmy8

- holo1 state: `scratch/in/holo-xerox-c2-cmy8-q05-counting-receive.state`
- holo1 format row: `c2-cmy8-p120-v0@3328x2304`
- holo1 certs by stream: {'C': 1776, 'M': 1839, 'Y': 1755}
- holo1 epoch: e032 print-day counting run; best on record 5466 (colour-uplift PK-FINAL reached 5466; the readable state holds the e032 run at 5370)
- holo3 harvest: exit 0, wall 3494.6 s, child max RSS 45.95 GiB, 718413 B, sha_ok=True
- holo3 certs: 5422 by stream {'C': 1792, 'M': 1866, 'Y': 1764}
- holo3 TileOutcome rows: {'tile_outcome_rows': 16522, 'results': {'below_attempt_floor': 616, 'certified': 5422, 'attempted_failed': 10484}}
- matched 5334 / holo1-only 36 (0.67%) / holo3-only 88
- holo1-only by stream: {'C': 16, 'M': 2, 'Y': 18}
- holo3-only by stream: {'C': 32, 'M': 29, 'Y': 27}
- miss geometry: rows ty=0:4 ty=1:3 ty=4:3 ty=32:3; cols tx=23:11 tx=33:5 tx=22:4 tx=6:4; 7/36 on the outer ring of the 52x36 tile matrix; 33 distinct tile positions
- holo1-only addresses (page, ty, tx, stream), up to 40:

```
  0   0  20 C
  0   0  22 C
  0   0  24 Y
  0   0  25 Y
  0   1   3 Y
  0   1  18 Y
  0   1  23 Y
  0   2   6 C
  0   4   3 C
  0   4  22 C
  0   4  23 C
  0   5  23 C
  0   6   5 C
  0   7   0 Y
  0   9   7 Y
  0   9  23 C
  0  10  23 C
  0  11   6 Y
  0  13  23 Y
  0  14  23 C
  0  16  33 Y
  0  16  35 C
  0  17  23 C
  0  17  23 Y
  0  18  23 C
  0  28   6 Y
  0  28  22 C
  0  29   6 Y
  0  30   8 Y
  0  30  22 C
  0  32  23 Y
  0  32  33 M
  0  32  33 Y
  0  33  33 M
  0  33  33 Y
  0  51   5 Y
```
- holo3-only addresses, up to 40:

```
  0   0   2 C
  0   0   5 M
  0   0  19 Y
  0   0  21 C
  0   0  23 M
  0   2   5 C
  0   2  22 C
  0   3   5 C
  0   3   5 Y
  0   4  20 M
  0   4  25 M
  0   5   5 Y
  0   5   6 C
  0   6   5 Y
  0   6  20 M
  0   7   5 Y
  0   7  25 M
  0   8   0 Y
  0   9  20 Y
  0  10   4 C
  0  13   0 Y
  0  13  33 Y
  0  15  20 M
  0  16  23 M
  0  17   7 Y
  0  18   7 Y
  0  19   3 C
  0  19   4 C
  0  19   4 Y
  0  19   5 C
  0  19   5 Y
  0  20  20 M
  0  20  22 M
  0  21  20 M
  0  23   0 M
  0  23   0 Y
  0  23   3 C
  0  23   5 C
  0  23  20 M
  0  23  23 M
```

## step 5 -- xerox c2-k (c2-r0700)

- holo1 state: `scratch/in/holo-xerox-c2-counting-receive.state`
- holo1 format row: `c2-r0700@3392x2368`
- holo1 certs by stream: {'main': 1930}
- holo1 epoch: e032 print-day counting run; best on record 1930 (1930/1961 = 98.4%)
- holo3 harvest: exit 0, wall 814.9 s, child max RSS 14.05 GiB, 465580 B, sha_ok=True
- holo3 certs: 1924 by stream {'main': 1924}
- holo3 TileOutcome rows: {'tile_outcome_rows': 7218, 'results': {'below_attempt_floor': 882, 'certified': 1924, 'attempted_failed': 4412}}
- matched 1922 / holo1-only 8 (0.41%) / holo3-only 2
- holo1-only by stream: {'main': 8}
- holo3-only by stream: {'main': 2}
- miss geometry: cols tx=0:6; 7/8 on the outer ring of the 53x37 tile matrix; 8 distinct tile positions
- holo1-only addresses (page, ty, tx, stream), up to 40:

```
  0  10   0 main
  0  23  34 main
  0  24  36 main
  0  28   0 main
  0  34   0 main
  0  48   0 main
  0  49   0 main
  0  52   0 main
```
- holo3-only addresses, up to 40:

```
  0   4   0 main
  0   7   0 main
```

## step 6 -- xerox c2-cmy7 (PK-FINAL)

- holo1 state: `scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/receive.state`
- holo1 format row: `c2-cmy7-p120-v0@3328x2304`
- holo1 certs by stream: {'main': 1559}
- holo1 epoch: colour-uplift PK-FINAL; best on record 1559 (the pre-registered print-frozen negative control, closed at 686,859 B)
- holo3 harvest: exit 0, wall 2740.5 s, child max RSS 56.34 GiB, 686859 B, sha_ok=True
- holo3 certs: 1586 by stream {'main': 1586}
- holo3 TileOutcome rows: {'tile_outcome_rows': 17197, 'results': {'below_attempt_floor': 1069, 'certified': 1586, 'attempted_failed': 14542}}
- matched 1537 / holo1-only 22 (1.41%) / holo3-only 49
- holo1-only by stream: {'main': 22}
- holo3-only by stream: {'main': 49}
- miss geometry: rows ty=4:3 ty=3:2 ty=46:2 ty=51:2; cols tx=30:6 tx=3:4 tx=27:3 tx=1:2; 5/22 on the outer ring of the 52x36 tile matrix; 22 distinct tile positions
- holo1-only addresses (page, ty, tx, stream), up to 40:

```
  0   0  20 main
  0   1   3 main
  0   2   3 main
  0   3   1 main
  0   3  35 main
  0   4   3 main
  0   4  27 main
  0   4  28 main
  0   5   1 main
  0   7  35 main
  0  11   3 main
  0  19  27 main
  0  24  30 main
  0  36  30 main
  0  37  30 main
  0  39  30 main
  0  45  30 main
  0  46  27 main
  0  46  30 main
  0  50   7 main
  0  51   7 main
  0  51   8 main
```
- holo3-only addresses, up to 40:

```
  0   0  26 main
  0   0  29 main
  0   0  33 main
  0   2  30 main
  0   3  30 main
  0   7  30 main
  0   9  27 main
  0  10   2 main
  0  10  30 main
  0  11  27 main
  0  12  30 main
  0  13  30 main
  0  14   2 main
  0  16  20 main
  0  17  30 main
  0  18  30 main
  0  19   2 main
  0  19  20 main
  0  20  17 main
  0  20  34 main
  0  21  34 main
  0  22   3 main
  0  22  30 main
  0  23   2 main
  0  24  33 main
  0  25  16 main
  0  27   2 main
  0  27  17 main
  0  29   2 main
  0  29  16 main
  0  29  17 main
  0  31   2 main
  0  31  30 main
  0  31  34 main
  0  32   2 main
  0  32  34 main
  0  33  34 main
  0  34  17 main
  0  35   2 main
  0  36  17 main
```

## step 7 -- sheet I pooled cmy8

- holo1 state: `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/receive.state`
- holo1 format row: `c2-cmy8-r0700-p120-x1@3392x2368`
- holo1 certs by stream: {'C': 1895, 'M': 1958, 'Y': 1444}
- holo1 epoch: plane-fields W6 pooled run; best on record 5297 (M 1958 / C 1895 / Y 1444; dead-Y bands expected on this sheet)
- holo3 harvest: exit 0, wall 6701.4 s, child max RSS 47.86 GiB, 1798761 B, sha_ok=True
- holo3 certs: 5326 by stream {'C': 1898, 'M': 1958, 'Y': 1470}
- holo3 TileOutcome rows: {'tile_outcome_rows': 238701, 'results': {'below_attempt_floor': 2477, 'certified': 6072, 'attempted_failed': 230152}}
- matched 5193 / holo1-only 104 (1.96%) / holo3-only 133
- holo1-only by stream: {'C': 26, 'M': 2, 'Y': 76}
- holo3-only by stream: {'C': 29, 'M': 2, 'Y': 102}
- miss geometry: rows ty=2:5 ty=0:4 ty=5:4 ty=9:4; cols tx=30:16 tx=11:10 tx=19:10 tx=10:8; 5/104 on the outer ring of the 53x37 tile matrix; 101 distinct tile positions
- holo1-only addresses (page, ty, tx, stream), up to 40:

```
  0   0   2 C
  0   0  24 Y
  0   0  26 Y
  0   0  29 C
  0   1  26 Y
  0   2   5 C
  0   2   7 Y
  0   2  26 Y
  0   2  30 C
  0   2  30 Y
  0   3  29 Y
  0   4  29 Y
  0   4  30 Y
  0   5  24 Y
  0   5  26 Y
  0   5  30 C
  0   5  30 Y
  0   6  27 Y
  0   7  26 Y
  0   9   7 Y
  0   9  29 Y
  0   9  30 C
  0   9  30 Y
  0  12  30 C
  0  13  10 Y
  0  13  11 Y
  0  13  30 C
  0  13  31 C
  0  14  19 Y
  0  15  27 Y
  0  15  28 Y
  0  16  10 Y
  0  17   9 Y
  0  18   2 Y
  0  18  11 Y
  0  18  31 C
  0  19  18 Y
  0  20  10 Y
  0  20  11 Y
  0  20  32 M
```
- holo3-only addresses, up to 40:

```
  0   0  19 Y
  0   1  17 Y
  0   1  19 Y
  0   2   2 Y
  0   2  17 Y
  0   2  18 Y
  0   2  19 Y
  0   3   0 Y
  0   3   5 C
  0   3  18 Y
  0   4   5 C
  0   4  17 Y
  0   4  30 C
  0   5  15 Y
  0   6  17 Y
  0   6  29 Y
  0   7   0 Y
  0   7   2 Y
  0   7   9 Y
  0   7  15 Y
  0   7  17 Y
  0   7  30 Y
  0   8  17 Y
  0   8  19 Y
  0   8  26 Y
  0   8  30 Y
  0   9  15 Y
  0   9  16 Y
  0  10  10 Y
  0  10  19 Y
  0  11   9 Y
  0  11  10 Y
  0  11  19 Y
  0  11  29 Y
  0  12   2 Y
  0  12   9 Y
  0  12  19 Y
  0  13   5 C
  0  13  16 Y
  0  13  17 Y
```

## Post-change adjudication (holo3 HEAD f4a18ea)

Re-harvest of all six volumes on the descriptor engine: retries never close-gated, a widened `refine` re-arm, the new `revisit` row, and the new `refine.color` lane carrying v1's numerics verbatim. Same rules as the baseline batch -- strictly serial, `--complete`, `--workers 8`, one decode at a time -- run from a single daemonized driver so the harness could not reap it mid-batch, with 5 s RSS sampling against a 58 GiB kill line.

| volume | holo1 | pre | post | miss pre | miss post | recovered | lost | wall x | peak GiB | sha | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| e029 HP K (c2-r0700) | 1940 | 1940 | 1938 | 0 | 2 | 0 | 2 | 1.16 | 15.35 | OK | FAILED |
| xerox c3-cmy7 | 720 | 786 | 815 | 4 | 0 | 4 | 0 | 1.39 | 39.44 | OK | EXCEEDED |
| xerox c2-cmy8 | 5370 | - | **none** | - | - | - | - | - | >60.5 killed | - | NO MEASUREMENT |
| xerox c2-k (c2-r0700) | 1930 | 1924 | 1927 | 8 | 5 | 3 | 0 | 0.68 | 12.6 | OK | PARTIAL |
| xerox c2-cmy7 (PK-FINAL) | 1559 | 1586 | 1564 | 22 | 26 | 8 | 39 | 3.1 | 57.96 | OK | FAILED |
| sheet I pooled cmy8 | 5297 | 5326 | 5439 | 104 | 34 | 73 | 13 | 2.03 | 48.09 | OK | MET |

### Verdict against the pre-registered expectations

- **e029 HP K (c2-r0700) — FAILED**: pre-registered 'stays 1940 exact' -- lost 2, gained 0; both losses at ty=42, the documented HP weak-horizontal band.
- **xerox c3-cmy7 — EXCEEDED**: pre-registered 'recovers some of its 4' -- recovered ALL 4, reaching exact parity with holo1.
- **xerox c2-cmy8 — NO MEASUREMENT**: killed at the 58 GiB ceiling at BOTH workers 8 (60.51 GiB) and workers 6 (60.24 GiB).
- **xerox c2-k (c2-r0700) — PARTIAL**: pre-registered 'from 8 toward ~3' -- reached 5 (recovered 3, lost 0), including two of the tx=0 rescue-column tiles the widened refine targeted.
- **xerox c2-cmy7 (PK-FINAL) — FAILED**: pre-registered 'toward its 22' -- regressed to 26 (recovered 8, lost 39).
- **sheet I pooled cmy8 — MET**: pre-registered 'toward its 104' -- reached 34, dropping below the 1% flag line; Y 1470 -> 1559.

**Every close that ran stayed byte-exact.** Five of five completed volumes recovered their payload sha exactly. The changes moved WHICH tiles certify; they never broke payload reconstruction.

**The refinement rows adopted nothing, on any volume.** Across the five completed volumes `refine` fired 717 times, `refine.color` 3899 times and `revisit` 593 times, producing 0 `route=refine` poses -- zero, everywhere. Certificates are minted only by the tiles rows, and the refinement rows' whole contribution is supposed to arrive as an adopted revised placement, so a zero adoption count means they contributed no certificate anywhere in this batch. On c2-cmy7 and sheet I that is 788 and 2,950 colour-lane fires for no adoption -- the runaway signature this batch was told to watch for.

**Where the certificates actually came from.** Retry attempts rose steeply everywhere -- 4.7x on step 2 (1,500 -> 7,037), 0 -> 2,694 on step 3, 3.7x on step 5, 23x on step 6 (1,028 -> 23,881), 1.9x on step 7 -- but the per-source certified counts show the retry row minting only 50 / 0 / 21 / 13 / 99 certificates on steps 2/3/5/6/7. Notably it minted NONE on step 3, the volume that reached exact parity: there the whole gain sits in `tiles/scan` (786 -> 815) on a larger attempt count (3,399 -> 3,840). So the retry un-gating is real and does mint certificates on four volumes, but it does not by itself explain step 3, and with zero refinement adoptions the events in hand do not isolate what re-fired those extra scans. Attributing step 3's gain would need instrumentation this batch does not carry -- stated as an open question rather than guessed.

**Memory is the batch's hard limit.** Post peaks ran well above baseline (step 3 15.8 -> 39.4 GiB; step 6 56.3 -> 57.96, within 0.04 GiB of the kill line). Step 4 breached at BOTH workers 8 (60.51) and workers 6 (60.24) -- 0.27 GiB apart, so worker count is not the driver and the prescribed reduced-worker fallback cannot rescue that volume on this machine.

**Wall cost.** Step 6 crossed the 2.5x tripwire (3.1x, 8,487 s) and was logged rather than killed -- a killed volume measures nothing, and it is the flagged volume. Step 7 ran 2.03x (13,580 s). Steps 2/3 ran 1.16x/1.39x and step 5 came in FASTER than baseline at 0.68x.

### post step 2 -- e029 HP K (c2-r0700)

- verdict: **FAILED** -- pre-registered 'stays 1940 exact' -- lost 2, gained 0; both losses at ty=42, the documented HP weak-horizontal band
- expectation as pre-registered: stays 1940 exact
- harvest: wall 761.9 s (1.16x baseline), peak 15.35 GiB, 465580 B, sha_ok=True
- certificates: pre 1940 -> post 1938 (holo1 1940)
- by stream: pre {'main': 1940} -> post {'main': 1938}
- vs holo1: matched 1938, missing 2 (0.10%), extra 0; miss by stream {'main': 2}
- vs baseline: recovered 0 of the baseline's misses, lost 2 it had held
- miss geometry: rows ty=42:2; 0/2 on the outer ring of 53x37; 2 distinct tiles
- new rows: {'refine': {'fires_post': 406, 'fires_pre': 106, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'refine.color': {'fires_post': 0, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'revisit': {'fires_post': 124, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}}
- colour lane: {'refine_color_fires': 0, 'refine_route_adoptions': 0, 'fires_per_adoption': None, 'pathological': False}
- pose routes: pre {'chain': 1317, 'word': 2} -> post {'chain': 1325, 'word': 2}

| row | jobs pre | jobs post | | source | attempts pre | attempts post |
|---|---:|---:|---|---|---:|---:|
| `calibrate` | 4276 | 6714 | | `tiles/retry150` | 1500 | 7037 |
| `ctx` | 0 | 67 | | `tiles/scan` | 5875 | 10224 |
| `place` | 1879 | 2254 | | | | |
| `refine` | 106 | 406 | | | | |
| `revisit` | 0 | 124 | | | | |
| `survey` | 1 | 1 | | | | |
| `tiles` | 7572 | 0 | | | | |
| `tiles.freeze` | 0 | 234 | | | | |
| `tiles.retry` | 0 | 7037 | | | | |
| `tiles.scan` | 0 | 10224 | | | | |

- lost vs baseline (page, ty, tx, stream), up to 40:
```
  0  42  12 main
  0  42  15 main
```

### post step 3 -- xerox c3-cmy7

- verdict: **EXCEEDED** -- pre-registered 'recovers some of its 4' -- recovered ALL 4, reaching exact parity with holo1
- expectation as pre-registered: recovers some of its 4 misses
- harvest: wall 1242.7 s (1.39x baseline), peak 39.44 GiB, 301600 B, sha_ok=True
- certificates: pre 786 -> post 815 (holo1 720)
- by stream: pre {'main': 786} -> post {'main': 815}
- vs holo1: matched 720, missing 0 (0.00%), extra 95; miss by stream {}
- vs baseline: recovered 4 of the baseline's misses, lost 0 it had held
- new rows: {'refine': {'fires_post': 0, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'refine.color': {'fires_post': 161, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'revisit': {'fires_post': 37, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}}
- colour lane: {'refine_color_fires': 161, 'refine_route_adoptions': 0, 'fires_per_adoption': None, 'pathological': False}
- pose routes: pre {'chain': 631, 'word': 8} -> post {'chain': 621, 'word': 8}

| row | jobs pre | jobs post | | source | attempts pre | attempts post |
|---|---:|---:|---|---|---:|---:|
| `color` | 43 | 104 | | `tiles/retry150` | 0 | 2694 |
| `place` | 751 | 756 | | `tiles/scan` | 3399 | 3840 |
| `refine.color` | 0 | 161 | | | | |
| `revisit` | 0 | 37 | | | | |
| `survey` | 1 | 1 | | | | |
| `tiles` | 3442 | 0 | | | | |
| `tiles.freeze` | 0 | 70 | | | | |
| `tiles.retry` | 0 | 2694 | | | | |
| `tiles.scan` | 0 | 3840 | | | | |

### post step 4 -- xerox c2-cmy8

- verdict: **NO MEASUREMENT** -- killed at the 58 GiB ceiling at BOTH workers 8 (60.51 GiB) and workers 6 (60.24 GiB)
- expectation as pre-registered: gains from unstarved retries + colour refinement, toward its 36
- no post events: the volume never completed.

### post step 5 -- xerox c2-k (c2-r0700)

- verdict: **PARTIAL** -- pre-registered 'from 8 toward ~3' -- reached 5 (recovered 3, lost 0), including two of the tx=0 rescue-column tiles the widened refine targeted
- expectation as pre-registered: misses shrink from 8 toward ~3 (widened refine + revisit target the never-refined rescue rows)
- harvest: wall 554.7 s (0.68x baseline), peak 12.6 GiB, 465580 B, sha_ok=True
- certificates: pre 1924 -> post 1927 (holo1 1930)
- by stream: pre {'main': 1924} -> post {'main': 1927}
- vs holo1: matched 1925, missing 5 (0.26%), extra 2; miss by stream {'main': 5}
- vs baseline: recovered 3 of the baseline's misses, lost 0 it had held
- miss geometry: cols tx=0:4; 5/5 on the outer ring of 53x37; 5 distinct tiles
- new rows: {'refine': {'fires_post': 311, 'fires_pre': 144, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'refine.color': {'fires_post': 0, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'revisit': {'fires_post': 33, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}}
- colour lane: {'refine_color_fires': 0, 'refine_route_adoptions': 0, 'fires_per_adoption': None, 'pathological': False}
- pose routes: pre {'chain': 1336, 'word': 6} -> post {'chain': 1304, 'word': 6}

| row | jobs pre | jobs post | | source | attempts pre | attempts post |
|---|---:|---:|---|---|---:|---:|
| `calibrate` | 3522 | 3945 | | `tiles/retry150` | 933 | 3472 |
| `ctx` | 0 | 85 | | `tiles/scan` | 6285 | 6428 |
| `place` | 1639 | 1598 | | | | |
| `refine` | 144 | 311 | | | | |
| `revisit` | 0 | 33 | | | | |
| `survey` | 1 | 1 | | | | |
| `tiles` | 7375 | 0 | | | | |
| `tiles.freeze` | 0 | 118 | | | | |
| `tiles.retry` | 0 | 3472 | | | | |
| `tiles.scan` | 0 | 6428 | | | | |

### post step 6 -- xerox c2-cmy7 (PK-FINAL)

- verdict: **FAILED** -- pre-registered 'toward its 22' -- regressed to 26 (recovered 8, lost 39)
- expectation as pre-registered: toward its 22 misses
- harvest: wall 8486.7 s (3.1x baseline), peak 57.96 GiB, 686859 B, sha_ok=True
- certificates: pre 1586 -> post 1564 (holo1 1559)
- by stream: pre {'main': 1586} -> post {'main': 1564}
- vs holo1: matched 1533, missing 26 (1.67%), extra 31; miss by stream {'main': 26}
- vs baseline: recovered 8 of the baseline's misses, lost 39 it had held
- miss geometry: rows ty=4:3 ty=3:2 ty=7:2 ty=19:2; cols tx=3:8 tx=27:3 tx=1:2 tx=35:2; 4/26 on the outer ring of 52x36; 26 distinct tiles
- new rows: {'refine': {'fires_post': 0, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'refine.color': {'fires_post': 788, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'revisit': {'fires_post': 82, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}}
- colour lane: {'refine_color_fires': 788, 'refine_route_adoptions': 0, 'fires_per_adoption': None, 'pathological': True}
- pose routes: pre {'chain': 1381, 'word': 8} -> post {'chain': 1400, 'word': 8}

| row | jobs pre | jobs post | | source | attempts pre | attempts post |
|---|---:|---:|---|---|---:|---:|
| `color` | 57 | 102 | | `tiles/retry150` | 1028 | 23881 |
| `place` | 1597 | 1616 | | `tiles/scan` | 16169 | 27171 |
| `refine.color` | 0 | 788 | | | | |
| `revisit` | 0 | 82 | | | | |
| `survey` | 1 | 1 | | | | |
| `tiles` | 17247 | 0 | | | | |
| `tiles.freeze` | 0 | 79 | | | | |
| `tiles.retry` | 0 | 23881 | | | | |
| `tiles.scan` | 0 | 27171 | | | | |

- lost vs baseline (page, ty, tx, stream), up to 40:
```
  0   0  26 main
  0   0  29 main
  0   0  33 main
  0   4  34 main
  0   5   3 main
  0   7   1 main
  0   9  27 main
  0  10   2 main
  0  10  30 main
  0  12  30 main
  0  13  30 main
  0  17  30 main
  0  18  30 main
  0  19   2 main
  0  19  17 main
  0  20  16 main
  0  20  17 main
  0  20  30 main
  0  20  34 main
  0  22  30 main
  0  23   2 main
  0  27   2 main
  0  28   2 main
  0  28  34 main
  0  29   2 main
  0  29  16 main
  0  29  17 main
  0  32  34 main
  0  33  34 main
  0  34   3 main
  0  34  17 main
  0  36   3 main
  0  36  17 main
  0  37   3 main
  0  38   3 main
  0  38  17 main
  0  45  28 main
  0  51  16 main
  0  51  17 main
```

### post step 7 -- sheet I pooled cmy8

- verdict: **MET** -- pre-registered 'toward its 104' -- reached 34, dropping below the 1% flag line; Y 1470 -> 1559
- expectation as pre-registered: toward its 104 misses
- harvest: wall 13579.8 s (2.03x baseline), peak 48.09 GiB, 1798761 B, sha_ok=True
- certificates: pre 5326 -> post 5439 (holo1 5297)
- by stream: pre {'C': 1898, 'M': 1958, 'Y': 1470} -> post {'C': 1921, 'M': 1959, 'Y': 1559}
- vs holo1: matched 5263, missing 34 (0.64%), extra 176; miss by stream {'C': 12, 'M': 1, 'Y': 21}
- vs baseline: recovered 73 of the baseline's misses, lost 13 it had held
- miss geometry: rows ty=13:4 ty=35:3 ty=47:3 ty=20:2; cols tx=30:9 tx=10:5 tx=27:4 tx=29:3; 0/34 on the outer ring of 53x37; 33 distinct tiles
- new rows: {'refine': {'fires_post': 0, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'refine.color': {'fires_post': 2950, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}, 'revisit': {'fires_post': 317, 'fires_pre': 0, 'certificates_credited_post': 0, 'certificates_credited_pre': 0}}
- colour lane: {'refine_color_fires': 2950, 'refine_route_adoptions': 0, 'fires_per_adoption': None, 'pathological': True}
- pose routes: pre {'chain': 3373, 'word': 23} -> post {'chain': 3282, 'word': 23}

| row | jobs pre | jobs post | | source | attempts pre | attempts post |
|---|---:|---:|---|---|---:|---:|
| `color` | 151 | 326 | | `tiles/retry150` | 113994 | 215565 |
| `place` | 4238 | 4237 | | `tiles/scan` | 90227 | 165891 |
| `refine.color` | 0 | 2950 | | `tiles/union` | 34480 | 65069 |
| `revisit` | 0 | 317 | | | | |
| `survey` | 3 | 3 | | | | |
| `tiles` | 238848 | 0 | | | | |
| `tiles.freeze` | 0 | 303 | | | | |
| `tiles.retry` | 0 | 215565 | | | | |
| `tiles.scan` | 0 | 156045 | | | | |
| `tiles.union` | 0 | 62269 | | | | |

- lost vs baseline (page, ty, tx, stream), up to 40:
```
  0  10  10 Y
  0  11  19 Y
  0  21  17 Y
  0  25  10 Y
  0  27  10 Y
  0  27  27 Y
  0  35  28 C
  0  35  29 Y
  0  36  28 C
  0  36  29 Y
  0  41  28 Y
  0  43   9 Y
  0  47  16 Y
```


## Supersession (2026-08-31)

These baselines describe the receiver of 2026-08-30 evening. Within
24 hours eight arms and three structural fixes landed (see
ARMS-2026-08-31.md) and the full-sheet numbers moved past every table
here (sheet I 5,445 -> 5,543 with the plane field still effectively
off). The batteries stand as the record of THAT receiver; the deep
per-tile analysis over their run dirs was skipped by the lead-approved
lean wrap as describing a receiver that no longer exists. Fresh
baselines start from the first current-tree full-domain runs.
