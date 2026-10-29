# 046 — the first cmy8 THREE-WIDTH column-group sheet: c2-cmy8-r0775x0850x0700@53x37 on the Xerox AltaLink C8245

STATUS: GENERATED 2026-10-12 (job + GT + payload byte-identical by
`experiments/046-altalink-cmy8-three-width/generate_set.py --verify`);
PRINTED by the owner on the AltaLink on 2026-10-13 (`lpr -o raw`); SCANNED
the same day (Canon 2400 RGB, two captures, the sheet turned 180° between
them); **DECODED: VERIFIED
byte-exact, 1,782,790 B, sha256 `f8c0be63…` == the counting payload — the
receiver alone closed at 5,165 certificates, and the receiver + four analyzer
passes + one receiver resume read 5,878 of the 5,883 tile-streams (C 1,958 /
M 1,959 / Y 1,961)**, every close of the chain VERIFIED, every certificate
equal to the emission (§046.2–§046.6, 2026-10-13, machine 4; analysis on machine 1,
`measure/e046_three_width/`). Single sheet — NO promotion.

The owner's ask (2026-10-12): "i want to do a counting sheet in c2-cmy8 on the
office printer with uneven rungs … what 3 rungs would you propose for the 3
planes?" — then "Generate a .ps for c2-cmy8-r0775x0850x0700@53x37", and on the
sim gate: **"We won't sim decode. We'll just scan the sheet and see!"** — so
this row goes to toner without the 10x10 round trip the ruled two-width rows
had (docs/CMY8-COLUMN-GROUPS.md §4; its generator-side partition and the
grouped `close_volume` law are the same code, the receiver's grouped close
has run on paper once, e044 sheet A at Z 19). This is the second column-group
print of any family (e044's cmy pair r0775x0700 was the first) and the first
cmy8 one, the first with three distinct widths.

## 046.0 What is printed, and why these rungs

`c2-cmy8-r0775x0850x0700@53x37` on A4-4mm, `--printer xerox-altalink-c8245`
(the `cmyk1` route: one DeviceCMYK `image` at 600 dpi, 32,380,671 B),
`--source-fraction 0.8`: C at r0775, **M at r0850**, Y at r0700. Capacity
1,782,790 B = uniform r0775's 1,785,886 within 0.2 % — uniform r0775's payload
with the parity moved from the plane that does not need it to the plane that
does. Pool: K 4,236 symbols over one page (K/N 0.796), symbol 3,367 bits,
**Z 21 column groups of 160–161 bits, carried per tile C 19 / M 21 / Y 17**,
spare 2 bits per site; dead-plane ceilings q ≤ C 2/3, M 12/19, Y 40/57 (none
holds at q 0.8 — a counting sheet, like e044's). Payload: e039's counting rule
byte[i] = (i + 0x39 + k) mod 256 with k = 2 (e044's sheets were 0 and 1);
sha256 `f8c0be63…`. Job sha256 `45bcedaf…`; gs 10 parses it (nullpage clean,
0.9 s); 1 `image`, 1 `/DeviceCMYK setcolorspace`, 0 `setcmykcolor`, 0
`imagemask`, 1 `%%Page`. Files: `scratch/e046/jobs/E046-A-page000.ps`,
`E046-A-manifest.json`, `E046-A-page000_gt.npy`;
`scratch/e046/payloads/counting-A-c2-1782790.bin`; digests
`scratch/e046/JOB-SHA256.txt` and the experiment folder's copy.

The rungs follow the AltaLink's per-plane record at c2 cmy8 (certified of
1,961 per plane):

| sheet, run | rung | C | M | Y |
|---|---|---|---|---|
| H, the receiver's stall, four captures (e036, 2026-09-01) | r0850 | 1,734 | 1,944 | 1,013 |
| I, one capture, interrupted (e037, 2026-09-07) | r0700 | 1,786 | 1,928 | 1,119 |
| e039-set I, four captures, the receiver's hand stop 56 short of its close (e042 addendum 2026-10-16/17, q 0.8) | r0850 | 1,669 | 1,944 | 1,020 |
| J's whole second copy, of 3,922 (e035, 2026-09-03) | r0547 | 3,871 | 3,876 | 3,798 |

M was complete first on H and I and stood at 99 % at r0850 on the receiver of
2026-09-01 — r0850 is M's measured rung. C reached 88 % at r0850 and its last
rows were e036's third-layer finding (C under M+Y has no dot core; C's dead
band in tile columns 30–31 fell last, to the analyzer's patch discriminant,
which the receiver has no row for) — one rung down, 320 more parity bits per
tile for those cells. Y stood at 52 % and 57 % before the page field; its
x-registration sinusoid (e033 §033.4, 0.83 dot, ~100 mm) is the page field's
job now (PAGE-FIELD-PLAN: sheet I meets B3), but Y also trails by 2 % at r0547
where no bands exist and e042's context-free X1 calls Y the weak plane (12.8 %
best-threshold, a FALSE EXTRA Y the main confusion) — two rungs down, to the
rung where the AltaLink read Y to 1,961. The alternatives priced (q 0.8,
53x37, A4-4mm): uniform r0850 1,973,446 B; the ruled r0850x0850x0775 1,907,790
(C on the rung where the receiver alone stalled on C — an analyzer sheet
again); r0850x0850x0700 1,845,921; **r0775x0850x0700 1,782,790**; uniform
r0775 1,785,886; uniform r0700 1,598,326; the ruled Y lever r0700x0700x0547
1,470,498. The only sheet in the record above 2 MB is e033's H, uniform r0850
at q 0.9, 2,220,921 B (e036).

Controls that exist without a print: the e039 set's AltaLink sheets G, H, I
(uniform c2-cmy8 r0700 / r0775 / r0850, `lpr -o raw`) are printed and
unscanned (e042 §042.3); H is the r0775 per-plane baseline on this engine for
the current receiver.

## 046.1 Runs

| run | when | what | command | result |
|---|---|---|---|---|
| 046.1g | 2026-10-12 18:00 | generate | `PYTHONPATH=src env/bin/python ./confetti.py generate --format c2-cmy8-r0775x0850x0700@53x37 --paper A4-4mm --printer xerox-altalink-c8245 --source-fraction 0.8 -o build/e046/A build/e046/payloads/counting-A-c2-1782790.bin` on main `4708714a`; regenerated byte-identically by `generate_set.py --verify` | job `45bcedaf…` 32,380,671 B, GT 12,048,512 B, manifest; K 4,236, Z 21 (19/21/17) |
| 046.1p | 2026-10-13 (the owner) | print | the owner: `lpr -o raw` to the AltaLink C8245 (the `lpr-raw` footing, as sheets G–J of e033/e039), `scratch/e046/jobs/E046-A-page000.ps` | one sheet |
| 046.1s | 2026-10-13, before 17:03 (machine 1's copies carry file times 16:48 and 17:00) | scan | the owner, Canon 2400 RGB, whole sheet, two captures, the sheet TURNED 180° between them (the owner; a 180° turn does not move the Canon's seams off the same page positions, ~9 mm sideways does — CLAUDE.md's multi-scan line, e045 §045.6) → on machine 4 `scratch2/e046-c2-cmy8-r0775x0850x0700-scan.tiff` and `…-scan-2.tiff`; copies on machine 1 in `scratch/e046/` | `…-scan.tiff` 1,718,864,112 B, 20416 × 28064, sha256 `da9d42c24f331dc52735a599768d8c6592bb3bd114ae325526a1d800b43e4f1f` (receiver ordinal 1, placed at rot_k 2 = turned 180°); `…-scan-2.tiff` 1,718,864,112 B, 20416 × 28064, sha256 `62d7dd052cbe64180636bfd4619e286bffe52e45a4d4fc904e9282d4783c4bfc` (ordinal 0, rot_k 0) |
| 046.1d = M1 | 2026-10-13 17:03 → one ctrl-C ~20:05 (the owner's account; no log carries a clock), orderly drain of 13 in-flight jobs (`decode.log`) | decode, the receiver | on machine 4, tree `pre-v1-v2-deletion-491-g2fa8fd5c` (main `2fa8fd5c`); the tree file records the shipped adoption mode `HOLO3_COLOR_ROW_ADOPT=last` (`engine.py` writes the effective mode on every run); argv as recorded: `confetti3.py decode scratch2/e046-c2-cmy8-r0775x0850x0700-scan-2.tiff scratch2/e046-c2-cmy8-r0775x0850x0700-scan.tiff --dpi 2400 --dpi 2400 --format c2-cmy8-r0775x0850x0700@53x37 --max-pages 1 --complete --workers 14 --diag 8023 --run-dir scratch2/e046/M1/rundir --out scratch2/e046/M1/payload.bin` (output teed to `scratch2/e046/M1/decode.log`; run dir `rundir.40735`) | **VERIFIED, 5,165 certificates (C 1,457 / M 1,788 / Y 1,920)**, 173,051 jobs, 135,058 cpu-s; 3,632 jobs queued at the stop (§046.2) |
| 046.1a1 | 2026-10-13 evening | analyzer, default battery, one generation | reconstructed from the ledger and mints headers (every analyzer command in this table is; machine 4 shell lines were not copied): `PYTHONPATH=src:. env/bin/python -m analyzer ladder --run-dir scratch2/e046/M1/rundir.40735 --targets residue --workers 14 --out scratch2/e046/A1` (11 arms, rules sum/best/platt/corr, rungs L0 L1 L2 L4 L3 L7a L7b, cover 0.9, generations ≤ 1); then `export-facts --snapshot scratch2/e046/M1/rundir.40735/facts.npz --ledger scratch2/e046/A1/ledger.jsonl --out scratch2/e046/A1-export/facts.npz` (the export manifest names the snapshot and ledger) and `union-base … --out scratch2/e046/A1-union` | +212 (C 85 / M 98 / Y 29), close verified at 5,377; 1,203 s wall, 7.77 GiB peak |
| 046.1a2 | 2026-10-13 evening | analyzer, default battery, fixed point | `ladder --run-dir scratch2/e046/A1-union --targets "open-after scratch2/e046/A1/ledger.jsonl" --fixed-point --max-generations 8 --workers 14 --out scratch2/e046/A2`; export onto A1's export → `scratch2/e046/A2-export/facts.npz`, union base `scratch2/e046/A2-union` | +47 (20 / 18 / 9) over 4 generations to the fixed point; verified at 5,424; 1,248.6 s, 8.06 GiB |
| 046.1a3 | 2026-10-13 ~20:54 → 21:38 (checkpoint 21:24:02 at 0:30:01) | analyzer, the maximal pass | `ladder --run-dir scratch2/e046/A2-union --targets "open-after scratch2/e046/A2/ledger.jsonl" --profile everything+patch+pure --halo-cells C=48,M=48,Y=32 --rungs L0,L1,L2,L4,L3,L3f,L7,L7c --cover-fraction 0.5 --fixed-point --max-generations 16 --workers 14 --out scratch2/e046/A3` (the header: 19 arms, rules + platt-state, knobs branches=state, ctx_state, refit_rounds 2, refit_max_evidence 26, patch_selftrain_rounds 4, re-roll on L0–L2); export → `scratch2/e046/A3-export/facts.npz` | +438 (395 / 40 / 3), all 16 generations, 1 key pending at the cap; verified at 5,862; 2,606.9 s, 11.19 GiB |
| 046.1m2 = M2 | 2026-10-13 night | decode, the receiver resumed | the M1 tree and adoption mode; argv as recorded: `confetti3.py decode scratch2/e046-c2-cmy8-r0775x0850x0700-scan-2.tiff scratch2/e046-c2-cmy8-r0775x0850x0700-scan.tiff --dpi 2400 --dpi 2400 --format c2-cmy8-r0775x0850x0700@53x37 --max-pages 1 --complete --workers 14 --diag 8023 --run-dir scratch2/e046/M2/rundir --out scratch2/e046/M2/payload.bin --resume scratch2/e046/A3-export/facts.npz` (run dir `rundir.42487`) | replayed 5,862, +1 (tiles.union, M), VERIFIED at 5,863; ran to an empty queue, 3,126 jobs, 5,092.5 cpu-s |
| 046.1a4 | 2026-10-13 night | analyzer, the maximal pass again | A3's configuration on `--run-dir scratch2/e046/M2/rundir.42487 --targets residue --max-generations 32 --out scratch2/e046/A4` | +15 (1 / 14 / 0) over 13 generations to the fixed point; verified at 5,878; 613.7 s, 8.81 GiB; not exported |

Artefacts: on machine 4 under `scratch2/e046/` (`M1/`, `M2/`, `A1`–`A4/` with
their multi-GB `ledger.jsonl`, the exports and union bases); copied to machine 1
as `scratch/e046/runs/` without the ledgers and without rasters. Analysis
(2026-10-13, machine 1, four Opus measurers, no decode and no ladder pass):
`measure/e046_three_width/` (README there lists the four modules), outputs
in `scratch/e046/analysis/{receiver,analyzer,spatial,truth}/`.

## 046.2 — M1: the receiver alone, both captures, `--complete`, stopped by hand: VERIFIED at 5,165 (2026-10-13, machine 4)

The owner's run on machine 4 (the 046.1d row), main `2fa8fd5c`, both 2400 dpi
captures, 14 workers, launched 17:03 and stopped with one ctrl-C at about 20:05
(both times the owner's account — the log carries no clock; the receiver
drained its 13 in-flight jobs into the snapshot, `decode.log`). **Close
VERIFIED, 1,782,790 bytes, sha256 `f8c0be63…` == the counting payload, on 5,165
certificates of 5,883 tile-streams (C 1,457 = 74.3 % · M 1,788 = 91.2 % · Y
1,920 = 97.9 % of 1,961 each); K 5,165 against 4,236, metadata rank 24/24,
every one of the 21 column groups solved at the drain (4,649–4,676 rows
each).** 173,051 jobs, 135,058.0 cpu-s; both captures calibrated (9/9). The
certificates first seen in the events, the facts snapshot and RunDone are the
same 5,165 keys. Numbers below are `measure/e046_three_width/receiver_run.py`'s
(`scratch/e046/analysis/receiver/receiver_run.json`), the clock is cumulative
JobDone cpu-s in event order.

| row | jobs | cpu-s | certificates (C / M / Y) | cpu-s per certificate | first / last certificate at cpu-s |
|---|---|---|---|---|---|
| `tiles.scan` | 28,193 | 2,494.9 | 2,167 (563 / 500 / 1,104) | 1.15 | 33 / 12,925 |
| `tiles.union` | 14,090 | 1,308.8 | 1,097 (294 / 362 / 441) | 1.19 | 3,474 / 12,815 |
| `tiles.retry` | 69,890 | 8,955.4 | 83 (22 / 27 / 34) | 107.9 | 348 / 13,818 |
| `tiles.local` | 30,075 | 113,089.9 | 1,490 (553 / 779 / 158) | 75.9 | 14,529 / 132,572 |
| `tiles.planek` | 2,560 | 2,918.2 | 328 (25 / 120 / 183) | 8.9 | 88,182 / 134,896 |
| `tiles.swim` | 0 | 0 | 0 | — | — |
| `refine.color` | 24,637 | 4,913.6 | 0 (1,514 poses) | — | — |
| the rest (color 219, color.pooled_ctx 6, place 3,373, fields.collect 4, fields 2, survey 2) | 3,606 | 1,377.1 | 0 | — | — |

**Where the cpu went.** `tiles.local` took 83.7 % of the run (113,090 of
135,058 cpu-s), 93–98 % of every 10,000 cpu-s window from 30k to 90k. scan,
union and retry minted all of theirs by 13,818 cpu-s (retry's last, the 3,347th
certificate — the first snapshot line, "3347 certificates", sits there); after
that only local and planek minted. local's yield per 10,000 cpu-s window, from
the window ending at 20k on: 434 (10k–20k; its first certificate at 14,529),
153, 253, 282, 171, 60, 63, 45, 8, 11, 6, 2, 2 — from 80k to the stop local's
last 74 certificates for 51,145 cpu-s of `tiles.local` (691 cpu-s each), while
the run minted 402 in that span (planek 328). `tiles.retry` 69,890 jobs for 83
(the standing price question, as e044 §044.7). By plane over the run: at 10k
cpu-s C 740 / M 721 / Y 1,516; at 20k 1,117 / 1,065 / 1,599; at 60k 1,364 /
1,580 / 1,696; at the stop 1,457 / 1,788 / 1,920 — Y was 77 % read at 10k
cpu-s, C and M climbed through `tiles.local` for the rest of the run.

**The swim never ran, the planek late.** `tiles.swim` took 5,818 seats at cost
240–244 from 32.6 cpu-s on and ran 0 jobs; 1,750 were queued at the stop.
`tiles.planek` (seats at cost 230–460, every job it ran at 230–232) ran its
first jobs between 80k and 90k cpu-s, first certificate at 88,182, and had
1,773 queued at the stop; `tiles.local` ran at 220–224 the whole run;
`tiles.uplift` 12 seats, 0 jobs. Frontier at the stop: 3,632 queued (color 6,
fields.collect 2, place 101, planek 1,773, swim 1,750), 0 in flight. So M1 is
NOT a receiver-alone ceiling for this sheet: two residue rows had most of
their work unrun when it stopped (e044 §044.6/§044.7 ran to the drain; this
did not).

**The close: counted at 31 %, ready at 53 %.** Replayed certificate by
certificate through the receiver's own `CloseProgress` with the row's pool (Z
21 groups of 160/160/161 bits, carried C 19 / M 21 / Y 17, symbol widths 3,047
/ 3,367 / 2,727 bits — the pool's S; a tile-stream's user bits are one more,
3,048 / 3,368 / 2,728, the per-stream metadata bit ahead of the symbol, as
`truth_check.py` builds them and the facts carry them), checked against the
run's own CloseCheck events:

| milestone (K 4,236) | certificate | cpu-s | share of the run | the run's own CloseCheck |
|---|---|---|---|---|
| pooled symbols ≥ K | 4,236 | 41,944 | 31.1 % | 4,236 at 41,948 — scarcest group 3,792 rows, 444 short |
| every group ≥ K rows (count-ready) | 4,709 | 71,148 | 52.7 % | 4,709 at 71,155 |
| first prefix that solves VERIFIED (`close_volume`, binary search) | 4,709 | 71,148 | 52.7 % | — (`--complete`: 4,242 CloseChecks deferred, 1 verified at the drain) |

After count-ready the run minted 456 more (local 128, planek 328; C 66 / M 184
/ Y 206) over 63,910 cpu-s, 47.3 % of the run. The tipping keys were M tiles
from `tiles.local` both times. At the drain the groups held 4,649–4,676 rows;
which plane binds which group was not split out.

**ESTIMATE — the q 0.9 count, a count argument only, not a decode.** The q 0.9
row (2,006,275 B by `confetti.py capacity --source-fraction 0.9`) has K 4,767.
Replaying M1's certificates against that K: the pooled count reaches 4,767 at
certificate 4,767 (80,523 cpu-s), but the groups are NEVER count-ready in M1
— the scarcest ends at 4,649 rows, 118 short. After the whole chain (M2's
5,863) the scarcest group stands at 5,302 rows, above 4,767. A q 0.9 sheet
would carry other symbols on the same tiles; this says only that M1's
per-group row counts would not have reached its K and the chain's would.

**The page field: two solves, both before the payload rows' second phase.**
`fields` ran 2 jobs and `fields.collect` 4 (2 more queued at the stop);
FieldSolved at 13,891 and 13,990 cpu-s — before `tiles.local`'s first
certificate at 14,529 — and never again over the remaining ~121,000 cpu-s and
1,818 certificates. Converged (155 passes), support 1,961 / 1,961 / 1,958
tiles; the readout's C 0.448 ± 1.489, M 0.448 ± 1.489, Y 0.316 ± 1.959 dots is
the median magnitude ± the median prior-scale uncertainty (e044 §044.7's
note), C and M equal under the cmy8 gauge F_C + F_M = 0
(`lib/field_gauge.py`). Residual energy against expected, per capture: ordinal
0 (`62d7dd…`, scan-2) C 177.1/199.7, M 171.1/198.2, Y 146.4/159.6; ordinal 1
(`da9d42…`) C 124.4/204.8, M 116.9/202.1, Y 89.7/160.8 — the same ordering in
M2 (182.3 / 178.4 / 141.0 against 107.9 / 102.5 / 82.9). Recorded, not read.

Run metadata: `color_row_adopt: last` (RunOpen and the tree file; `engine.py`
records the effective mode on every run, `last` is the shipped default — not
evidence the variable was set).
Some TileOutcome "certified" events re-certify an already certified key (union
731, scan 59, local 1); they are not counted. Artefacts on machine 4:
`scratch2/e046/M1/` (`decode.log`, `payload.bin`, `rundir.40735/` — argv,
tree, report.json, events.jsonl, facts.npz, the panes); on machine 1
`scratch/e046/runs/M1/`. Single sheet — NO promotion.

## 046.3 — The analyzer passes and the hand-back: 5,165 → 5,878 (A1–A4, M2; 2026-10-13, machine 4)

The loop of analyzer/README §2 on M1's run dir: `--targets residue`, then
`open-after` the previous pass's ledger, each pass's mints folded by
`export-facts` into a new snapshot and a `union-base` run dir for the next,
the receiver resumed once from A3's export (M2), and the maximal pass once
more on M2's run dir (A4, not exported). Numbers:
`measure/e046_three_width/analyzer_passes.py`
(`scratch/e046/analysis/analyzer/analyzer_passes.json`) over the copied mints,
ledger.md, close.json, export manifests and ladder logs; its replay of each
fixed point's re-target sets (`analyzer.fixedpoint._retarget`: the 8
neighbouring tiles and the tile's other two planes) reproduces every logged
per-generation pending count. The ladder logs' "GB" is GiB (A3's checkpoint:
11,116,216,320 B = "10.35 GB").

| pass | base | targets C / M / Y | generations, stop | certificates C / M / Y | wall | peak RSS | wall per attempt | wall per certificate |
|---|---|---|---|---|---|---|---|---|
| A1 default, 1 generation | 5,165 | 718 = 504 / 173 / 41 | 1; cap, 211 re-attacks left | **212** = 85 / 98 / 29 | 1,203 s | 7.77 GiB | 1.68 s | 5.7 s |
| A2 default, fixed point | 5,377 | 506 = 419 / 75 / 12 | 4; fixed point (g3: 4 re-attacks, +0) | **47** = 20 / 18 / 9 | 1,249 s | 8.06 GiB | 2.14 s | 26.6 s |
| A3 maximal, cap 16 | 5,424 | 459 = 399 / 57 / 3 | 16; cap, 1 key pending | **438** = 395 / 40 / 3 | 2,607 s | 11.19 GiB | 4.16 s | 5.9 s |
| M2 receiver resume | 5,862 | 21 open | ran to an empty queue | **1** = 0 / 1 / 0 | — | — | — | 3,126 jobs, 5,092.5 cpu-s |
| A4 maximal, cap 32 | 5,863 | 20 = 4 / 16 / 0 | 13; fixed point | **15** = 1 / 14 / 0 | 614 s | 8.81 GiB | 17.5 s | 40.9 s |

Cumulative: M1 5,165 (1,457 / 1,788 / 1,920) → A1 5,377 (1,542 / 1,886 / 1,949)
→ A2 5,424 (1,562 / 1,904 / 1,958) → A3 5,862 (1,957 / 1,944 / 1,961) → M2
5,863 (1,957 / 1,945 / 1,961) → **A4 5,878 (1,958 / 1,959 / 1,961)**. Four
passes, 712 analyzer certificates (C 501 / M 170 / Y 41) in 5,672 s of wall
(the ledgers' 1,203.2 + 1,248.6 + 2,606.9 + 613.7), 1 h 34.5 min; the analyzer
records walls only (no CPU total, README §3), so its column is never added to
the receiver's cpu. Per generation (C / M / Y): A2 g0 15/17/8 (1,052 s), g1
4/1/1, g2 1/0/0, g3 +0; **A3 g0 266/22/1 (1,694 s), g1 118/4/1 (412 s), g2
11/1/1 (121 s), g3–g15 one M each (373 s together)**; A4 g0 0/2/0 (246 s), g1
1/1/0, g2–g12 one M each (270 s). 0 refused in every generation. Worker seconds
of the minted rows: A1 1,378 (median 2.9), A2 406 (3.9), A3 12,070 (25.1), A4
325 (17.3); the failed rows' seconds are in the uncopied `ledger.jsonl`.

**Attribution (first-success marginals — the ladder stops at the first
certificate and the re-roll runs in battery order; none of this is a
leave-one-out).** Rungs over all 712: L0 632 (A1 178, A2 28, A3 412, A4 14), L2
damped@300 36, L2 layered@300 15, L3f 18 (A3 16 + 1, A4 1), L1 11. Rule `sum`
first on 637 (A1 163, A2 37, A3 422, A4 15). By arm family: the classic battery
(A1 + A2) 259 = C 105 / M 116 / Y 38; the patch family (patch+*, rings,
mixture; A3 + A4) 449 = C 395 / M 52 / Y 2; field2 non-patch arms 3 (M 2, Y 1);
one C on a mixed classic+patch set. A3's 395 C: L0 378, L3f.r0 11, L2 damped 5,
L2 layered 1; 394 on patch-family sets and 1 on a mixed set. Arm-set
memberships (a certificate's set names every arm that certified it at that
rung, so these overlap — 700 memberships over A3's 438): patch+affine 289 / 27
/ 2 (C / M / Y; 121 on patch+affine alone), patch+committed 125 / 8 / 0,
patch+field2+offset 116 / 9 / 0, patch+offset 98 / 7 / 0, rings+offset 5 / 10 /
0. A1's, counted the same way: subtract+affine 44 / 61 / 2, subtract+offset 37
/ 30 / 15 (Y 15 of 29 on it alone), conditional+offset 20 / 12 / 0,
global+offset 11 / 11 / 2. Pass order and arm family are CONFOUNDED: A1/A2 had
no patch arms and ran first on the easier residue, and A3 changed more than the
arms against them — halo C=48, M=48, Y=32 (none in A1/A2), cover 0.5 (0.9), the
rule platt-state, rungs L3f and L7c, the knobs branches=state, ctx_state,
patch_selftrain_rounds 4, refit 2 / 26, and the re-roll-only pure arms — so
nothing here says the classic arms could not have taken A3's keys or the
reverse (§046.6 lists the isolation passes that would). What the bands say: of
the C tile-streams in DEAD columns (the analyzer's class,
`analyzer/residue.py:241`: certified fraction < 0.25 AND its Clopper-Pearson
one-sided 95 % upper bound < 0.25, on the pass's base — after M1 C's tx 12, 13,
14 and 27, 52 + 52 + 51 + 53 = 208 open; tx 28 at 9 of 53, upper bound 0.278,
is marginal) A1 took 1 of 208, A2 0 of 207, **A3 205 of 207**; of C's marginal
rows A3 took 166 of 168.

**The cascade.** A3 generations ≥ 1 minted 149, 139 of them with a same-plane
4-neighbour among their triggers, the other 10 diagonal; g2 took the corners
(0,0,12–13,C) and (0,0–1,29,C); Y (0,30,15,Y) (g2) followed (0,31,15,Y) (g1);
(0,32,15,M) (g1) → (0,32,15,C) (g2) in A3, each with a same-plane diagonal
trigger beside the cross-plane one ((0,31,14,M), (0,33,14,C)); and (0,32,14,M)
in A4 g0 → (0,32,14,C) in g1, triggered across planes alone. A2's 7 chained
certificates all had a same-plane 4-neighbour trigger ((0,4,16,C) → (0,3,16,C)
→ (0,2,16,C)). **Tile column 0 of M fell one row per generation**: open on 51
of 53 rows after M1 (rows 48 and 49 certified), A1 + A2 took 7 and A3 g0 14
(rows 52, 44, 43, 40–36, 7–3, 0); A3 g1 took rows 41, 42 and 35 (row 35
triggered by g0's row 36); from g2 on each generation took the next row up the
page and nothing else in that column — g2 row 34 … g15 row 21 — and A3 stopped
at its cap with (0,20,0,M) pending. M2 attempted it and did not certify it. A4
took it in g0 and walked on, g1 row 19 … g12 row 8, where row 7 (A3 g0) closed
the gap; (0,8,0,M) had been re-attacked in A3 g1 and A4 g0 without success
before row 9 certified. That chain, rows 35 → 8, is 28 certificates over 28
consecutive generations of two passes, each triggered by the row before it in
the same plane: 27 of the 28 certified with patch+affine in the arm set (row 16
on patch+committed alone), rungs L0 24, L3f 3, L2 layered 1 (read from the
mints rows).

**M2, the hand-back.** The receiver resumed from A3's export replayed 5,862
certificates (697 of them the analyzer's: L0 618, L2 damped 36, L2 layered 15,
L3f.r0 16, L1 11, L3f.r1 1), 1,887 placements, 3 page fields; ran 3,126 jobs,
5,092.5 cpu-s, to an empty queue; **minted one: (0,12,7,M) by `tiles.union`**
at 1,807 cpu-s. Its rescue rows minted nothing: `tiles.local` 329 jobs / 1,461
cpu-s, `tiles.swim` 218 jobs (cost 240–964) / 1,342 cpu-s, `tiles.planek` 247
/ 294 cpu-s, `tiles.retry` 756 / 81.5. VERIFIED at 5,863 (scarcest group 5,302
rows). The field solved four times: the first (3,244 cpu-s) on one capture's
residual rows, support C 1,958 / M 1,961 / Y 1,960, C/M 0.404 ± 1.765, Y 0.357
± 2.276 dots; solves 2–4 on both captures, support 1,961 on every plane, C/M
0.433 ± 1.486, Y 0.324 ± 1.927. Beside e037, uncontrolled: there the receiver
resumed from the folded facts took the four the analyzer had refused, at the
cheapest rung; here the hand-back bought one tile and the second maximal pass
fifteen — another sheet and rung, two captures against one, and e037's base
an interrupted 22-minute run on `74d7711-dirty` whose residue rows had barely
run.

**Nothing is wrong — four kinds of evidence.**

| close | status | symbols | redundant / consistent / inconsistent | metadata |
|---|---|---|---|---|
| M1 | VERIFIED | 5,165 | — | rank 24/24 |
| A1 | verified | 5,377 | 13,074 / 102,030 / **0** | rank 24 |
| A2 | verified | 5,424 | 13,985 / 102,941 / **0** | rank 24 |
| A3 | verified | 5,862 | 22,381 / 111,337 / **0** | rank 24 |
| M2 | VERIFIED | 5,863 | — | rank 24/24 |
| A4 | verified | 5,878 | 22,715 / 111,671 / **0** | rank 24 |

(1) Every close of the chain recovers sha256 `f8c0be63…` == the payload file
(re-hashed on machine 1). (2) Fountain consistency over the pooled block, counted
per (symbol, column group) over the 21 groups (n_redundant = n_consistent − 21
× 4,236): 0 inconsistent and 0 excluded in every analyzer close and every
export. (3) Exposure, bound 0.01 each: A1 213 distinct consultations, E[false
accepts] 4.96e-8; A2 48, 1.12e-8; A3 430, 1.00e-7; A4 16, 3.73e-9; 0
contradictions refused in all four ledgers; exports `snapshot_facts_unchanged`
with 0 skipped or duplicate keys. No key of the 712 carries a second
certificate from a disjoint capture ("corroborated" 0 in every ledger's
independent-agreement table); that says nothing about which capture's lanes a
certificate's evidence came from — the lanes come from both. (4) **The truth
check: 0 wrong against the emission**
(`measure/e046_three_width/truth_check.py`,
`scratch/e046/analysis/truth/truth_check.json`). The emitted user bits per
tile-stream were rebuilt through the generator's own calls (the pooled packing,
the fountain with `groups=spec.column_groups`, each plane cut to its width, the
per-stream metadata bit) and proven by re-rendering the page through
`compose_color_page_cells` byte-identical to `page000_gt.npy` (sha256
`bf25f728…915f4` = the file = the manifest's `gt_sha256`); widths C 3,048 / M
3,368 / Y 2,728 bits. Checked / wrong per source: M1 facts 5,165 / 0; M2 facts
5,166 receiver + 697 analyzer / 0; A1 mints 212 / 0; A2 47 / 0; A3 438 / 0; A4
15 / 0 — 11,740 checks over 5,878 distinct keys, the bits-wrong histogram
empty; M1's 5,165 sit in M2 bit-identical, the 697 imported equal their mint
rows. **The analyzer's own offline scorer cannot score this row**:
`analyzer.truth.load_truth` → `measure/crop_parity/_gt.reconstruct` builds the
pooled `fountain.VolumeCode` without `groups=spec.column_groups` (`_gt.py:134`;
`holo/gen/emit.py:324` passes it) and does not cut each stream to its width, so
it returns 3,368 bits (user bits, metadata bit included) on all three planes (C
and Y the wrong width on 1,961 of 1,961, M the right width with different bits
on 1,961 of 1,961), and `analyzer score --ledger
scratch/e046/runs/A1/mints.jsonl …` dies at `analyzer/oracle.py:94` (`could not
broadcast … (3400,) into (2760,)`). A defect, measured. The
ledgers' controls and parity sections say NOT RUN.

**FIXED the same day (machine 1, commit `ad357a82`, merged to main):**
`_gt.reconstruct` now passes `groups=spec.column_groups` and cuts each stream
to its own width, as `emit.py` does. On this row it equals `truth_check.py`'s
render-proven emission on all 5,883 tile-streams (C 3,048 / M 3,368 / Y 2,728
bits); `analyzer score --gt-dir build/e046/A` on the A1–A4 mints checks 212 /
47 / 438 / 15, 0 wrong (the truth check's four counts); gates 1–3, called
directly on the M1 and M2 snapshots, pass (5,165 and 5,863 certificates, 0
mismatches; gate 2 on 96 tiles, 1,179,648 cells), where the old code refused
C and Y as outside the GT domain. `score --run-dir` itself needs the capture
rasters, which are on machine 4 (§046.6). Uniform pooled rows reconstruct
byte-identically to the old code (`c3-cmy8-r0550x0550x0547@10x10` at one and
two pages, `c2-cmy8-r0700@10x10`, the sheet I and sheet H fossils). Regression
test `analyzer/tests/test_analyzer_truth_groups.py`: the generator's user
bits recorded as `emit_volume` composes each tile, against `load_truth`, on
the ruled lever `c3-cmy8-r0700x0700x0547@10x10` and this triplet at 10x10;
both fail on the old code.

## 046.4 — Where the residue was, and the page field

`measure/e046_three_width/residue_field.py`
(`scratch/e046/analysis/spatial/residue_field.json`) on the 53 × 37 tile grid:
`ty` along page y (the long axis, 287.2 mm), `tx` along page x (the short
axis, 200.5 mm), one tile 5.419 mm, the matrix 4.91 mm from the top and 4.74
mm from the left edge. Which page axis is the AltaLink's process direction was
not measured here. Figure:
**`scratch/e046/analysis/spatial/residue_field.png`** — per plane C, M, Y:
certified after M1 (dark = certified) / which stage certified each tile (M1
grey, A1 blue, A2 cyan, A3 green, M2 orange, A4 magenta, open red) / the final
open; bottom row M dx, M dy, Y dx, Y dy of M2's field (red +, blue −; C = −M).

**After M1.** A band = a run of tile columns whose certified fraction is more
than 2 binomial sd below the plane's page mean.

| plane | page mean | column bands (certified fraction) | edge share of the residue |
|---|---|---|---|
| C | 0.743 | **tx 12–15 (0.019 / 0.019 / 0.038 / 0.358), 65–87 mm from the matrix origin; tx 26–30 (0.434 / 0.000 / 0.170 / 0.434 / 0.396), 141–168 mm**; tx 9 0.528, tx 0 0.566; rows 0–5 0.486–0.595 | 9.9 % |
| M | 0.912 | tx 0 **0.038** (2 of 53), tx 36 0.491; tx 14–15 0.604 / 0.717, tx 7 0.698; row 0 0.568 | 55.5 % |
| Y | 0.979 | tx 0 0.472 only (every other column ≥ 0.943); rows 0, 30, 32 at 0.865 / 0.919 / 0.919 | 80.5 % |

C's open 504 were 258 in tile columns 8–16 and 203 in 26–31 (tx 27 open on 53
of 53 rows); C columns 1–4, 6, 17–25, 34 and 35 read 1.000. M's and Y's open
were mostly the page edge (M tx 0 51 open, tx 36 27; Y 28 of 41 in tx 0). Where
the analyzer's certificates went: A3's 395 C were 176 in tx 12–15 and 162 in tx
26–30 — the two bands; A1's 85 C over tx 0 18, 5 1, 7 6, 8 2, 9 7, 10 3, 11 1,
14 1 (its one dead-column C), 15 7, 16 1, 26 7, 29 3, 30 11, 31 8, 32 4, 33 2,
36 3; M's A1 98 over tx 0 6, 1 1, 7 14, 8 4, 9 7, 10 1, 13 1, 14 11, 15 8, 16
6, 17 1, 28–33 1/1/3/2/1/1, 35 8, 36 21, then A3 31 and A4 13 in tx 0; Y's A1
29 (21 in tx 0), A2 9, A3 3 at tx 15. At the end C 0.9985, M 0.999, Y 1.000.

**The final five**, all inside C's bands, each tile with Y certified:

| tile (ty, tx) | plane | mm from the matrix origin (y, x) | planes certified on the tile | same-plane neighbours open after M1 | analyzer attempts A1/A2/A3/A4 |
|---|---|---|---|---|---|
| (30, 15) | C | (165.3, 84.0) | Y | 5 of 8 | 1/1/4/1 |
| (30, 15) | M | (165.3, 84.0) | Y | 4 of 8 | 1/2/3/1 |
| (31, 15) | C | (170.7, 84.0) | Y | 5 of 8 | 1/1/3/2 |
| (31, 15) | M | (170.7, 84.0) | Y | 5 of 8 | 1/1/3/2 |
| (50, 27) | C | (273.6, 149.0) | M, Y | 6 of 8 | 1/1/2/1 |

The Y of (30,15) and (31,15) certified only in A3 (g2, g1). (0,31,15,C/M) were
attempted again in A4 g1–g2 after (0,32,14,M) and (0,32,14,C) certified. M2
attempted all 20 then open. How far off they ended (unsatisfied checks per
rung) is in the uncopied `ledger.jsonl`; A4's whole-pass histogram of 2,281
rung outcomes: 0 unsatisfied 223, 5–9 60, 10–49 23, 50–99 231, 100–499 1,744.

**The page field** (M2's snapshot; M1's within 0.05 dots rms, Pearson
0.978–0.993; |F_C + F_M| = 0.0 on both; support 100 %): F_C dx +0.353 ± 0.140,
dy −0.252 ± 0.111 dots (mean ± spatial sd), M = −C; F_Y dx +0.179 ± 0.275, dy
−0.063 ± 0.197. Along page x every component carries one period: C dx 94 mm,
amplitude 0.166 dots (R² 0.78), C dy 95 mm, 0.142 (0.96); Y dx 92 mm, 0.329
(0.80; profile peak-to-peak 0.84–0.87), Y dy 96 mm, 0.235 (0.97). Along page
y: C ≤ 0.04 dots, no clean period; Y dx a trend, Y dy 189–203 mm, 0.12. The
gauge-free pair C − M = 2 F_C: mean (+0.78, −0.47) dots on M1's field,
(+0.71, −0.50) on M2's; on M1's, its ~94 mm profile along x 1.04 dots
peak-to-peak in x and 0.72 in y. Beside the record:
e033 §033.4 measured sheet I's Y x-offset at 0.83 dot peak, ~100 mm, against a
GT-anchored affine frame (not this gauge; e033 does not say whether its
"peak" is an amplitude); here Y dx along page x is 92 mm, 0.33–0.34 dots
fitted amplitude. e040 measured the Canon
iR-ADV's C − M at 93 mm, 1.58 dots p-p along its process direction; here 94 mm
along page x. Two engines, two gauges, one sheet each — figures side by side,
not a comparison.

**C's residue lines up with the field; M's and Y's do not.** C certified after
M1 against the M1 field: per column Spearman with |F_C,y| = +0.80 (n 37), per
tile with the C − M y offset −0.607 (n 1,961); the p-values the module prints
(2.8e-9, 1e-197) assume independent columns and tiles, which a field this
smooth does not give — nominal only. By octile of C − M y
(lower edges −0.95 … −0.12 dots) C's certified fraction is 0.963, 0.963,
0.967, 0.992, 0.902, 0.600, 0.400, **0.159** — C failed where C and M sit
closest in y (dead columns 12 / 13 / 27 at F_C,y −0.039 / −0.057 / −0.068
dots; the fully read columns 1–4 and 17–25 at −0.23 to −0.40). In the figure
C's two stripes are the near-white stripes of M dy. **Confounded:** on the same
M1 field C's certified fraction tracks other offsets per column nearly as
closely — Spearman with Y − C x +0.77, with Y − M y −0.77, against C − M y's
−0.80 (`certified_after_M1_vs_pairwise_offsets`); by octile of Y − C x (low
to high) C's certified fraction is 0.278, 0.465, 0.686, 0.702, 0.935, 0.976,
0.963, 0.939. The field barely varies along y (C ≤
0.04 dots), so there is no within-column contrast to separate the offsets;
this sheet cannot say which, if any, goes with the C failures. M and Y: per-column
|field| correlations 0.006–0.27 (nominal p ≥ 0.11), per tile |ρ| ≤ 0.13. The
Canon's seams (every 18.288 mm) were not mapped: the tiles were not projected
into scan pixels. Both captures lie 180° apart on the glass (rot_k 0 and 2)
and the bands are open in their union, i.e. neither capture's reading
certified those tiles; per-capture certification was not split out.

## 046.5 — The reading

**Per plane against the AltaLink's earlier sheets — uncontrolled.** Of 1,961
per plane, the receiver alone:

| sheet, run | rungs C / M / Y | captures | receiver | run length, cpu | C | M | Y |
|---|---|---|---|---|---|---|---|
| **e046 M1** (stopped, swim unrun) | r0775 / r0850 / r0700 | 2 | page-field receiver, `2fa8fd5c` | ~3 h wall (the owner's account), 135,058 cpu-s | **1,457 (74.3 %)** | **1,788 (91.2 %)** | **1,920 (97.9 %)** |
| H, e036 run of 2026-09-01 | r0850 uniform | 4 | before the page field (merged 2026-09-12) | ≥ 557,426 cpu-s at a snapshot ~12 h in (4,690 then; e036) | 1,734 (88.4 %) | 1,944 (99.1 %) | 1,013 (51.7 %) |
| I, e037 (interrupted) | r0700 uniform | 1 | before the page field, `--plane-fields` | ~22 min wall; local 55 jobs, planek and swim 0 (e037) | 1,786 (91.1 %) | 1,928 (98.3 %) | 1,119 (57.1 %) |

The rows differ in print (e046 printed by 2026-10-13; H and I are e033's prints
of 2026-08-18), print day and toner state, captures (2 / 4 / 1), receiver tree
(the page-field receiver here; I's run on the per-lane fitter,
`--plane-fields`; e036 records no field flag for H's run), CPU and run length
(the table's column), dial (q 0.8 here, q 0.9 there; the dial moves K, not a
tile's rung) and the rungs themselves — and M1 was stopped with `tiles.swim`
unrun and 1,773 planek jobs queued. With that said, what was measured: **Y at
r0700 read 97.9 %** with no interior column band (tx 0 the only one) where H
and I, at r0850 and r0700, read 52–57 % before the page field. Against I the
rung is held (r0700 both); print, registration, captures (2 against 1),
receiver tree and CPU differ, so that row does not isolate the page field
either; against H the rung differs too. **M at r0850 read 91.2 %**, against
99.1 % on H at the same rung; 55.5 % of M's open were on the page edge, column
0 at 2 of 53. **C at r0775 read 74.3 %**, the worst plane — below H's 88.4 %
one rung higher and I's 91.1 % one rung lower. C's receiver count at r0775 is
below both; what the rung did for C cannot be read from this comparison.

**What C's deficit is, measured:** two bands of tile columns (the 2-sd bands of
§046.4; the analyzer's dead class is the narrower tx 12–14 and 27), tx 12–15
and 26–30, 0–43 % certified after M1 while 16 other columns read 1.000; open in
the union of two captures lying 180° apart on the glass; a C failure that
tracks, column by column, the place where the C − M y offset nears zero (and,
equally, a Y − C x offset — confounded on this sheet); 205 of 207 dead-band C
read by A3 — 204 on patch-family arm sets, 1 ((0,18,14,C)) on the mixed set
conditional+offset|patch+offset — and 1 of 208 by the default battery in A1
(first-success marginals from sequential passes on different bases, two
captures; not the measurement of e036 W8 on sheet H, whose 0 by the default arm
`subtract+offset` and 96 by the patch arm alone, on 153 open C, were
single-configuration isolation passes over 13 captures); and every one of those
certificates equal to the emission. **What it is not:** not a format-axis loss
on this sheet (C ends at 1,958 of 1,961, 0 wrong), and not, from these data,
shown to be e036's third-layer finding — no cell-level readout was run, and C's
dead columns here (the analyzer's class after M1: tx 12–14 and 27; tx 28
marginal) are not e036's (30–31). Whether a single capture alone fails the same
columns, and whether the scanner's seams fall on them, was not measured.

**The maximal pass on this engine now.** On two captures it took 438 of 459
targets (95.4 %) in 43 min of wall at 11.19 GiB, 16 generations; the default
battery took 259 of 718 (36 %) in 41 min over two passes — different target
sets (A3's 459 were what A1/A2 left), not comparable rates; and A4 15 of 20 in
10 min. Beside the record, not controlled: e040's H on the Canon iR-ADV (six
captures, 2,564 targets) +2,195 in 39.8 h at 64.95 "GB" (the ladder log's unit
as e040 quotes it; for A3 here that unit is GiB, e040 does not say); e037's
sheet I default battery 97.8 % of its residue in 40 min (one capture, 12 arms,
a base whose residue rows had barely run). In M1, `tiles.local`'s last 74
certificates cost 51,145 cpu-s (the run minted 402 in that span, planek 328).

## 046.6 — Open

**The five left:** (0,30,15,C), (0,30,15,M), (0,31,15,C), (0,31,15,M) and
(0,50,27,C) — C/M of two adjacent tiles at band 1's edge column and one C in
band 2's worst column, Y certified on all three tiles, M on the last; 5–7
analyzer attempts each, 1 receiver resume over all of them. The volume does
not need them.

**Options the owner could choose (costs from the measured walls; every forward
figure is an ESTIMATE):**

| option | the question it answers | cost |
|---|---|---|
| Receiver resume from A4's export (`export-facts --snapshot scratch2/e046/M2/rundir.42487/facts.npz --ledger scratch2/e046/A4/ledger.jsonl --out scratch2/e046/A4-export/facts.npz`, then M2's argv with `--resume` on it) | does any receiver row take any of the five with A4's 15 now certified beside them ((0,32,14,C/M) touch (0,31,15)); one receiver snapshot holding all 5,878 (today: M2's facts + A4's mints) | M2 started on 21 open and ran to an empty queue at 20 in 3,126 jobs, 5,092.5 cpu-s; a resume over 5 open is estimated at that order |
| Receiver-alone completion: resume from M1's own `facts.npz`, no analyzer facts, to the drain | the receiver-axis number for this sheet, comparable with e044 §044.6/§044.7 — what the never-run `tiles.swim` (1,750 queued) and the queued planek (1,773) add | ESTIMATE, a floor: M2's per-job prices (swim 6.16, planek 1.19 cpu-s/job) give ~13,000 cpu-s for the queued swim and planek work alone — but a resume rebuilds its queue from the facts (M2 on 21 open re-ran scan 396, union 326, retry 756 and local 329 jobs) and `tiles.local`, running at 220–224 ahead of planek (230) and swim (240), took 83.7 % of M1's cpu, so the run would cost more by an unmeasured amount; the one measured resume on this sheet is M2's 5,092.5 cpu-s on 21 open |
| Analyzer controls (README §2.3/§5: `controls --parity 100 --null 5 --frame-null 3 --withhold-run-mints` on M1's run dir) | parity and nulls with power denominators for this sheet's regime — the false-accept question for the configurations that minted here (the 712 are already scored 0 wrong against the emission) | not measured on this sheet; parity 100 per stream at A1's 1.68 s per attempt ≈ 10 min, the nulls a multiple of that (estimate); 8–11 GiB as the passes |
| Isolation passes (README §2.10) on the dead-band C, on A2's union base (before A3): `patch+offset` alone, `subtract+offset` with `branches=state`, `--profile patch --no-reroll`, `--profile pure`, each `--targets "band:dead+stream:C"` | which mechanism the 205 dead-band C need at r0775 on this engine — the first-success attribution cannot say (pass order and arm family confounded); the W8 matrix on a second sheet | ~207 keys × 2–4 s ≈ 7–14 min wall per pass, ~10 GiB (estimate from A1–A3; W8's single-configuration passes I0, I7, I1 on 153 rows took 118–135 s of wall on thirteen captures, I6 (default + patch + L3f) 319 s; W8 gives walls for scale only, its measure is CPU — 1,149–1,436 cpu-s for those three) |
| Another capture: a 4800, and/or a 2400 re-placed ~9 mm sideways (the Canon seams, 18.288 mm apart) | are the five capture-bound (e034: one added 4800 capture bought 14 of sheet I's last 17); corroboration of the 712 by a disjoint capture (0 today); whether C's bands read with a third capture | the owner's scan; a receiver resume over three captures (no measurement for this sheet: M1's two captures from scratch cost 135,058 cpu-s; a 4800 capture is ~4× the pixels, estimate), then analyzer passes whose per-key wall grows with captures (sheet J: 2.8× per key from four to ten captures) |
| ~~Fix the offline scorer's grouped path~~ DONE 2026-10-13, `ad357a82` (§046.3) | `analyzer score` scores column-group rows; this sheet's 712 mints 0 wrong | — |
| `analyzer score --run-dir` on machine 4, one pass at a time against its own run dir (A1 on M1's `rundir.40735`, A2 on `A1-union`, A3 on `A2-union`, A4 on M2's `rundir.42487`), with the full `ledger.jsonl` files and `--gt-dir` | gate 1 on each run dir's snapshot; the default arm's evidence recomputed for every row the passes attacked, failed rows included — cell error, d′, AUC, R and the waterfall per plane and band, and the bits-wrong-at-exit histogram the uncopied ledgers hold | ESTIMATE: 718 + 506 + 459 + 20 = 1,703 rows of one-arm evidence over two captures, below the passes' walls (A1–A4 1,203 / 1,249 / 2,607 / 614 s with up to 19 arms), peak near the passes' 8–11 GiB; needs main at or after `ad357a82` on machine 4 and the generation dir rebuilt there by `generate_set.py --verify` |

The first row was REQUESTED by the owner the same night ("give me one more
export/receiver invocation, and then one more analyzer invocation"): A4's
export, a receiver resume (M3) and the maximal pass on M3's run dir (A5) —
their record is owed when they land. Also open from this record: the
uncopied `ledger.jsonl` files on machine 4 hold the failed rows' seconds and
per-key rung outcomes that §046.3/§046.4 could not read.
