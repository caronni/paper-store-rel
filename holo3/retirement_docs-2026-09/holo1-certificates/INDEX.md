# holo1 certificate freeze — Phase 0.3

Extracted with the validated slice path of `measure/parity/extract_holo1_certs.py`
(mmap + string-aware bracket scan of the top-level `"certificates":[` array
only -- no `load_session`, no evidence decompression, no receiver run of any
kind). One state at a time, strictly serial, each run under `/usr/bin/time -l`.
Tree: `29d9a8d76ca8`. Interpreter: `env/bin/python` from the repo root,
`PYTHONPATH=src` (unused by this script outside `--crosscheck`, set per the
task's interpreter rule regardless).

Two batches, 28 states total:
- **Batch 1** (17 states): `scratch/e028`, `scratch/in`, `scratch/e030`,
  `scratch/plane-fields/{qual,policy-detach,prefix-repair}`,
  `scratch/xerox-v1-20260818` -- the raw print-day counting runs plus the
  plane-fields line's sheet-I/H states.
- **Batch 2** (11 states, `cu-*.json`): `scratch/color-uplift/full/*` -- the
  colour-uplift campaign's PK-FINAL re-decodes, i.e. the best-on-record yield
  the v1 receiver ever reached on these sheets.

**Total wall across all 28 extractions: 267.8 s** (batch 1: 242.2 s, batch 2:
25.6 s). **Largest peak RSS: 15.266 GiB** (sheet H, `sheetH-multi-pf`, batch 1)
-- under the 20 GB stop rule at every step; nothing was aborted. No batch-2
state came close: the largest, `cu-xerox-c2-cmy8-pkfinal` (1.27 GB file),
peaked at 2.418 GiB.

## Index (all 28 states)

Sizes are decimal (MB = 1e6 B, GB = 1e9 B); RSS is binary (GiB = 2^30 B),
matching what `/usr/bin/time -l` reports.

| name | state path | size | n_certificates | by stream | wall (s) | peak RSS (GiB) | byte-identical to | matches |
|---|---|---:|---:|---|---:|---:|---|---|
| `e029-hp-c2-r0700-k` | `scratch/e028/holo-c2-r0700-q07-ink-counting/receive.state` | 8.21 MB | 1940 | main:1940 | 0.15 | 0.037 | -- | **YES** parity step 2 (1940) |
| `xerox-c2-cmy7-counting` | `scratch/in/holo-xerox-c2-cmy7-counting-receive.state` | 1.664 GB | 83 | main:83 | 3.11 | 1.575 | -- | N/A (note 1) |
| `xerox-c3-cmy7-counting` | `scratch/in/holo-xerox-c3-cmy7-counting-receive.state` | 138.0 MB | 720 | main:720 | 0.75 | 0.186 | -- | **YES** parity step 3 (720) |
| `xerox-c2-cmy8-q05-counting` | `scratch/in/holo-xerox-c2-cmy8-q05-counting-receive.state` | 1.309 GB | 5370 | C:1776, M:1839, Y:1755 | 19.34 | 2.619 | -- | **YES** parity step 4 (5370) |
| `xerox-c2-k-counting` | `scratch/in/holo-xerox-c2-counting-receive.state` | 9.43 MB | 1930 | main:1930 | 0.15 | 0.038 | -- | **YES** parity step 5 (1930) |
| `hp-c2-cmy7-counting-failed` | `scratch/in/holo-hp-c2-cmy7-counting-receive.state` | 2.22 MB | 0 | (none) | 0.05 | 0.026 | Group A (see below) | N/A |
| `e030-hp-c3-cmy8-q05-partial` | `scratch/e030/holo-c3-cmy8-q05-counting/receive.state` | 633.8 MB | 663 | C:620, M:43 | 1.56 | 0.645 | -- | N/A (matches CLAUDE.md e030: 663, C620/M43/Y0) |
| `e030-hp-c2-cmy8-q05-hardfail` | `scratch/e030/holo-c2-cmy8-q05-counting/receive.state` | 81.1 MB | 0 | (none) | 0.21 | 0.099 | -- | N/A |
| `plane-fields-qual` | `scratch/plane-fields/qual/receive.state` | 3.953 GB | 5549 | C:1959, M:1961, Y:1629 | 32.06 | 5.742 | -- | N/A (note 2) |
| `plane-fields-policy-detach-cmy8-pkfinal` | `scratch/plane-fields/policy-detach/cmy8-pkfinal.state` | 159.7 MB | 15 | C:15 | 0.39 | 0.172 | Group B (see below) | **NO** -- not 5,466 (note 3) |
| `plane-fields-policy-detach-cmy7-counting` | `scratch/plane-fields/policy-detach/cmy7-counting.state` | 2.22 MB | 0 | (none) | 0.07 | 0.026 | Group A | N/A |
| `plane-fields-prefix-repair-smoke-hp-c2-cmy7` | `scratch/plane-fields/prefix-repair/smoke-hp-c2-cmy7.state` | 2.22 MB | 0 | (none) | 0.06 | 0.026 | Group A | N/A |
| `sheetI-c2-cmy8r0700-q090-4mm` | `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/receive.state` | 3.684 GB | 5297 | C:1895, M:1958, Y:1444 | 29.44 | 5.322 | -- | **YES** parity step 7 (5297) |
| `sheetI-c2-cmy8r0700-q090-4mm-4800` | `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm-4800/receive.state` | 3.652 GB | 4977 | C:1836, M:1876, Y:1265 | 19.99 | 4.508 | -- | N/A |
| `sheetI-multi-pf` | `scratch/xerox-v1-20260818/I-multi-pf/receive.state` | 5.712 GB | 5639 | C:1952, M:1961, Y:1726 | 34.25 | 7.268 | -- | N/A |
| `sheetI-multi-pf2` | `scratch/xerox-v1-20260818/I-multi-pf2/receive.state` | 5.418 GB | 5667 | C:1958, M:1961, Y:1748 | 43.82 | 7.511 | -- | N/A |
| `sheetH-multi-pf` | `scratch/xerox-v1-20260818/H-multi-pf/receive.state` | 15.000 GB | 4144 | C:1682, M:1906, Y:556 | 56.80 | 15.266 | -- | N/A (r0850, not sheet I's r0700; note 5) |
| `cu-xerox-c2-cmy7-pkfinal` | `scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/receive.state` | 0.702 GB | **1559** | main:1559 | 3.35 | 0.829 | -- | **YES** parity step 6 (1559) AND best-on-record 1,559 |
| `cu-xerox-c2-cmy8-pkfinal` | `scratch/color-uplift/full/xerox-c2-cmy8-pkfinal/receive.state` | 1.267 GB | **5466** | C:1802, M:1867, Y:1797 | 18.40 | 2.418 | -- | **YES** best-on-record 5,466 |
| `cu-xerox-c3-cmy7-pkfinal` | `scratch/color-uplift/full/xerox-c3-cmy7-pkfinal/receive.state` | 0.052 GB | **810** | main:810 | 0.61 | 0.108 | -- | **YES** best-on-record 810 |
| `cu-xerox-c2-k-pkfinal` | `scratch/color-uplift/full/xerox-c2-k-pkfinal/receive.state` | 9.43 MB | 1930 | main:1930 | 0.15 | 0.038 | -- | matches `xerox-c2-k-counting` count (1930), different file (note 6) |
| `cu-hp-c2-k-pkfinal` | `scratch/color-uplift/full/hp-c2-k-pkfinal/receive.state` | 8.21 MB | 1940 | main:1940 | 0.15 | 0.037 | -- | matches `e029-hp-c2-r0700-k` count (1940), different file (note 6) |
| `cu-hp-c3-cmy8-pkfinal` | `scratch/color-uplift/full/hp-c3-cmy8-pkfinal/receive.state` | 0.888 GB | 796 | C:740, M:56 | 2.33 | 0.892 | -- | N/A -- higher than e030's 663 but still Y:0, still OPEN (note 7) |
| `cu-hp-c2-cmy8-pkfinal` | `scratch/color-uplift/full/hp-c2-cmy8-pkfinal/receive.state` | 159.7 MB | 15 | C:15 | 0.23 | 0.172 | Group B (see below) | N/A -- resolves note 3 |
| `cu-hp-c2-cmy8-control-price` | `scratch/color-uplift/full/hp-c2-cmy8-control-price/receive.state` | 81.1 MB | 0 | (none) | 0.15 | 0.099 | -- (close in size to `e030-hp-c2-cmy8-q05-hardfail` but NOT identical, sha differs) | N/A |
| `cu-hp-c2-cmy7-pkfinal` | `scratch/color-uplift/full/hp-c2-cmy7-pkfinal/receive.state` | 2.224 MB | 0 | (none) | 0.06 | 0.026 | -- (distinct from Group A and from `-repin`, sha differs) | N/A |
| `cu-hp-c2-cmy7-pkfinal-repin` | `scratch/color-uplift/full/hp-c2-cmy7-pkfinal-repin/receive.state` | 2.224 MB | 0 | (none) | 0.06 | 0.026 | -- (distinct from Group A and from `-pkfinal`, sha differs) | N/A |
| `cu-hp-c2-cmy7-control-price` | `scratch/color-uplift/full/hp-c2-cmy7-control-price/receive.state` | 2.22 MB | 0 | (none) | 0.07 | 0.026 | Group A | N/A |

### Byte-identical groups (sha256-confirmed before re-extracting)

- **Group A** (`4042d3fb6d67a7b8b9abd365ec2a2852949f2a572f090f954c22571f4f9bfb3e`,
  2,222,275 B, 0 certificates -- the M281 HP c2-cmy7 hard fail): `hp-c2-cmy7-counting-failed`
  (`scratch/in/holo-hp-c2-cmy7-counting-receive.state`),
  `plane-fields-policy-detach-cmy7-counting`
  (`scratch/plane-fields/policy-detach/cmy7-counting.state`),
  `plane-fields-prefix-repair-smoke-hp-c2-cmy7`
  (`scratch/plane-fields/prefix-repair/smoke-hp-c2-cmy7.state`), and now
  `cu-hp-c2-cmy7-control-price`
  (`scratch/color-uplift/full/hp-c2-cmy7-control-price/receive.state`) --
  **four copies of the same file under four names**, all 0 certificates.
- **Group B** (`3a8e227927a7104546d755b3adea96838a7d3ad94abc506d90631895073a41af`,
  159,654,582 B, 15 certificates, all stream C, close `status: open`):
  `plane-fields-policy-detach-cmy8-pkfinal`
  (`scratch/plane-fields/policy-detach/cmy8-pkfinal.state`) and
  `cu-hp-c2-cmy8-pkfinal`
  (`scratch/color-uplift/full/hp-c2-cmy8-pkfinal/receive.state`) --
  **the batch-1 file is a copy of the HP (M281), not xerox, c2-cmy8 PK-FINAL
  attempt** (note 3).

Checked and confirmed **not** identical despite close sizes or matching
certificate counts: `cu-hp-c2-cmy8-control-price` vs
`e030-hp-c2-cmy8-q05-hardfail` (81,096,426 vs 81,096,384 B, different sha,
both 0 certs); `cu-hp-c2-k-pkfinal` vs `e029-hp-c2-r0700-k` (8,206,666 vs
8,206,654 B, different sha, both 1940 certs); `cu-xerox-c2-k-pkfinal` vs
`xerox-c2-k-counting` (9,429,565 vs 9,429,553 B, different sha, both 1930
certs); `cu-hp-c2-cmy7-pkfinal` vs `cu-hp-c2-cmy7-pkfinal-repin` (2,224,400
vs 2,224,413 B, different sha, both 0 certs). All other pairs differ in file
size, which alone rules out byte-identity.

## Exit criterion: the six parity columns

`parity.json`/`PARITY.md` cite six holo1 counts: **1,940 / 720 / 5,370 /
1,930 / 1,559 / 5,297**.

| step | label | parity.json holo1.n | holo1.by_stream | reproduced by | result |
|---|---|---:|---|---|---|
| 2 | e029 HP K (c2-r0700) | 1940 | main:1940 | `e029-hp-c2-r0700-k` (also `cu-hp-c2-k-pkfinal`, same count, different file) | EXACT MATCH |
| 3 | xerox c3-cmy7 | 720 | main:720 | `xerox-c3-cmy7-counting` | EXACT MATCH |
| 4 | xerox c2-cmy8 | 5370 | C:1776/M:1839/Y:1755 | `xerox-c2-cmy8-q05-counting` | EXACT MATCH |
| 5 | xerox c2-k (c2-r0700) | 1930 | main:1930 | `xerox-c2-k-counting` (also `cu-xerox-c2-k-pkfinal`, same count, different file) | EXACT MATCH |
| 6 | xerox c2-cmy7 (PK-FINAL) | 1559 | main:1559 | **`cu-xerox-c2-cmy7-pkfinal`** (batch 2) | EXACT MATCH -- close sha `5963b9d1...` and length 686859 also match parity.json's harvest record exactly |
| 7 | sheet I pooled cmy8 | 5297 | C:1895/M:1958/Y:1444 | `sheetI-c2-cmy8r0700-q090-4mm` | EXACT MATCH |

**All 6 of 6 parity states now reproduce exactly.** Batch 1 alone reproduced
5 of 6 (step 6 was not among its 17 states); batch 2's
`cu-xerox-c2-cmy7-pkfinal` (`scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/
receive.state`) is the file `parity.json` itself names as its step-6 source,
and it reproduces 1,559 exactly, closing the gap.

## Exit criterion: the three best-on-record counts

| best-on-record | reproduced by | result |
|---|---|---|
| 1,559 (c2-cmy7, colour-uplift PK-FINAL) | `cu-xerox-c2-cmy7-pkfinal` | **EXACT MATCH** (this is the same number as parity step 6 -- PARITY.md's "best on record" for c2-cmy7 IS its parity source) |
| 5,466 (c2-cmy8, colour-uplift PK-FINAL) | `cu-xerox-c2-cmy8-pkfinal` | **EXACT MATCH** -- 5466 certs, C:1802/M:1867/Y:1797, close `status: verified`, payload sha `f13c34db...` len 718413 (identical payload sha to the 5,370-cert counting-run state -- same underlying payload, higher yield) |
| 810 (c3-cmy7, colour-uplift PK-FINAL) | `cu-xerox-c3-cmy7-pkfinal` | **EXACT MATCH** -- 810 certs, close `status: verified`, payload sha `4f68dbf9...` len 301600 (identical payload sha to the 720-cert counting-run state) |

**All 3 of 3 best-on-record counts are now reproduced exactly**, all three
by states newly extracted in batch 2 under `scratch/color-uplift/full/`.
Batch 1 could not reach any of them (they live one directory deeper than
batch 1's 17-state list looked, as the coordinator's batch-2 message noted).

## Close records reached by the slice (PK-FINAL states)

Per state, whatever the slice's `"close":{...}` lookup returns -- this is
what PARITY.md's "verified sha" column rests on:

| state | close status | payload sha256 | payload length |
|---|---|---|---:|
| `cu-xerox-c2-cmy7-pkfinal` | verified | `5963b9d16abca48d66a05f80eb137ce76624b8fdedb48ce13c3ee0cf8f24c993` | 686859 |
| `cu-xerox-c2-cmy8-pkfinal` | verified | `f13c34db6c96796e65c812b7bb99e7618625e49a34640fcee58bc4627e38ecca` | 718413 |
| `cu-xerox-c3-cmy7-pkfinal` | verified | `4f68dbf932324aa85c1af576b9724504eb5dff85039a66a062ff9c9adc4e50c2` | 301600 |
| `cu-xerox-c2-k-pkfinal` | verified | `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af` | 465580 |
| `cu-hp-c2-k-pkfinal` | verified | `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af` | 465580 |
| `cu-hp-c3-cmy8-pkfinal` | **open** | null | null |
| `cu-hp-c2-cmy8-pkfinal` | **open** | null | null |
| `cu-hp-c2-cmy8-control-price` | **open** | null | null |
| `cu-hp-c2-cmy7-pkfinal` | **open** | null | null |
| `cu-hp-c2-cmy7-pkfinal-repin` | **open** | null | null |
| `cu-hp-c2-cmy7-control-price` | **open** | null | null |
| `xerox-c2-cmy7-counting` (batch 1, 83 certs) | **open** | null | null |
| `xerox-c3-cmy7-counting` (batch 1, 720 certs) | verified | `4f68dbf932324aa85c1af576b9724504eb5dff85039a66a062ff9c9adc4e50c2` | 301600 |
| `xerox-c2-cmy8-q05-counting` (batch 1, 5370 certs) | verified | `f13c34db6c96796e65c812b7bb99e7618625e49a34640fcee58bc4627e38ecca` | 718413 |
| `e030-hp-c3-cmy8-q05-partial` (batch 1, 663 certs) | **open** | null | null |

**Every HP (M281) colour attempt in this entire 28-state set -- counting run,
control-price, PK-FINAL, and PK-FINAL-repin, across c2-cmy7, c3-cmy8, and
c2-cmy8 -- stays `close: open`.** None of the four c2-cmy7 HP states and
none of the three c2-cmy8 HP states ever certified enough to close; the
c3-cmy8 HP PK-FINAL (`cu-hp-c3-cmy8-pkfinal`) raised the counting run's 663
certificates to 796 (C:740/M:56, Y still 0) but also stayed open. This
matches CLAUDE.md's Y-starved-M281 pattern (e017, e030) and shows the
colour-uplift campaign's PK-FINAL runs did not overcome it on the HP engine
even where they helped materially on xerox.

## Notes on discrepancies and surprises

1. **The original batch-1 task's annotation "(PARITY 1,559)" on
   `scratch/in/holo-xerox-c2-cmy7-counting-receive.state` was wrong** (already
   reported after batch 1). Confirmed now: the true source of the 1,559 count
   is `cu-xerox-c2-cmy7-pkfinal`
   (`scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/receive.state`), exactly
   as `parity.json` names it, and its close record (verified, sha
   `5963b9d1...`, len 686859) matches parity.json's harvest record for step 6
   exactly. `scratch/in/holo-xerox-c2-cmy7-counting-receive.state` remains
   the e032 raw counting run at 83 certificates, close `open`.
2. **`scratch/plane-fields/qual/receive.state`** (5,549 certs) is still not a
   parity state; the reasoning from the batch-1 report stands (it is very
   likely the plane-fields W6 sheet-I qual post-state, "+252 certs" over the
   5,297 parity baseline).
3. **RESOLVED**: `scratch/plane-fields/policy-detach/cmy8-pkfinal.state`
   (batch 1) is now confirmed byte-identical (sha256
   `3a8e2279...`) to `scratch/color-uplift/full/hp-c2-cmy8-pkfinal/receive.state`
   (batch 2, `cu-hp-c2-cmy8-pkfinal`) -- **it is a copy of the HP (M281)
   c2-cmy8 PK-FINAL attempt, not the xerox one.** The real
   5,466-certificate xerox c2-cmy8 PK-FINAL decode lives at
   `scratch/color-uplift/full/xerox-c2-cmy8-pkfinal/receive.state`
   (`cu-xerox-c2-cmy8-pkfinal`), extracted in batch 2, and reproduces 5,466
   exactly with a verified close matching parity.json's step-4 payload sha.
4. Group A/B byte-identical files: see the dedicated section above.
5. **Sheet H uses a different format row than sheet I** (r0850, not r0700) --
   unchanged from the batch-1 report, not an error.
6. **Two counts (1930 for xerox K, 1940 for HP K) are each reached by TWO
   distinct, non-identical files** -- the print-day counting run and the
   colour-uplift PK-FINAL re-decode land on the exact same certificate count
   from different underlying sessions (both closing to the identical payload
   sha `e5021f8d...`, len 465580). Since the K format carries no colour
   uplift machinery, this is consistent with PK-FINAL simply re-running the
   same deterministic K receiver to the same result on the same capture, not
   a coincidence to be suspicious of.
7. **New finding**: `cu-hp-c3-cmy8-pkfinal` (796 certs, C:740/M:56/Y:0,
   close open) shows the colour-uplift campaign DID try to improve the HP
   c3-cmy8 volume beyond e030's 663-certificate counting run, gained 133
   more certificates, and still could not close it -- a negative result not
   previously called out in CLAUDE.md's e030 section or PARITY.md (which
   only discusses the xerox side of the colour-uplift campaign's PK-FINAL
   runs).
8. **`receiver_policy_id`** appears in all four K states (`e029-hp-c2-r0700-k`,
   `xerox-c2-k-counting`, `cu-hp-c2-k-pkfinal`, `cu-xerox-c2-k-pkfinal`) and
   nowhere else. The two batch-1 K states carry
   `scheduler=holo/phased-session/rung-major-v2-r-lanes`; the two batch-2
   (`cu-*-pkfinal`) K states carry
   `scheduler=holo/phased-session/rung-major-v4-u-lanes-codingaware` -- a
   scheduler version difference (v2 vs v4) between the original print-day
   counting sessions and the later colour-uplift-era re-decodes, otherwise
   identical policy strings. Not further diagnosed (would mean reading more
   than the slice).
9. No extraction errored across all 28 states; every one parsed with exactly
   one `"certificates":[` marker occurrence and zero duplicate work keys.

## Peak RSS by state (largest first, all 28)

| name | file size (decimal) | peak RSS (GiB) |
|---|---:|---:|
| sheetH-multi-pf | 15.000 GB | 15.266 |
| sheetI-multi-pf2 | 5.418 GB | 7.511 |
| sheetI-multi-pf | 5.712 GB | 7.268 |
| plane-fields-qual | 3.953 GB | 5.742 |
| sheetI-c2-cmy8r0700-q090-4mm | 3.684 GB | 5.322 |
| sheetI-c2-cmy8r0700-q090-4mm-4800 | 3.652 GB | 4.508 |
| xerox-c2-cmy8-q05-counting | 1.309 GB | 2.619 |
| cu-xerox-c2-cmy8-pkfinal | 1.267 GB | 2.418 |
| xerox-c2-cmy7-counting | 1.664 GB | 1.575 |
| cu-hp-c3-cmy8-pkfinal | 0.888 GB | 0.892 |
| cu-xerox-c2-cmy7-pkfinal | 0.702 GB | 0.829 |
| e030-hp-c3-cmy8-q05-partial | 633.8 MB | 0.645 |
| xerox-c3-cmy7-counting | 138.0 MB | 0.186 |
| plane-fields-policy-detach-cmy8-pkfinal | 159.7 MB | 0.172 |
| cu-hp-c2-cmy8-pkfinal | 159.7 MB | 0.172 |
| cu-xerox-c3-cmy7-pkfinal | 51.8 MB | 0.108 |
| e030-hp-c2-cmy8-q05-hardfail | 81.1 MB | 0.099 |
| cu-hp-c2-cmy8-control-price | 81.1 MB | 0.099 |
| xerox-c2-k-counting | 9.43 MB | 0.038 |
| cu-xerox-c2-k-pkfinal | 9.43 MB | 0.038 |
| e029-hp-c2-r0700-k | 8.21 MB | 0.037 |
| cu-hp-c2-k-pkfinal | 8.21 MB | 0.037 |
| hp-c2-cmy7-counting-failed | 2.22 MB | 0.026 |
| plane-fields-policy-detach-cmy7-counting | 2.22 MB | 0.026 |
| plane-fields-prefix-repair-smoke-hp-c2-cmy7 | 2.22 MB | 0.026 |
| cu-hp-c2-cmy7-control-price | 2.22 MB | 0.026 |
| cu-hp-c2-cmy7-pkfinal | 2.224 MB | 0.026 |
| cu-hp-c2-cmy7-pkfinal-repin | 2.224 MB | 0.026 |

Peak RSS never came close to the 20 GB stop rule at any point across either
batch. RSS tracks roughly 1.1-1.5x file size, not the certificate count --
the slice's own `buf.find(MARKER)` and its bracket-scan both walk mmap'd
pages sequentially from the file start, so page-in cost (and therefore RSS
via the page cache) scales with how far into the file `"certificates":[`
sits, not with array size. This holds across both batches: `cu-xerox-c2-cmy7-pkfinal`
(1559 certs, 0.7 GB file) peaked higher than `cu-hp-c3-cmy8-pkfinal` (796
certs, 0.89 GB file) despite fewer certificates, purely because of file size.
