# e044 — the first cmy format sheets on the M281 (P1): a c2 and a c3 counting volume

Date: 2026-10-11 night. Engine: HP Color LaserJet Pro M281fdw "<host>"
(home), fresh toner epoch (2026-09-13). Route: **`lpr -o raw` to the CUPS
queue `HP_Color_LaserJet_MFP_M281fdw__<host>_`** — the owner's instruction
("use lpr -o raw"), a footing of its own as e031/e032/e035 were on the
AltaLink (`lpr-raw` ≠ raw9100; never merge the two). Generator: branch
`cmy-generator` at a7846d33 (W0 7bad672c, W1 128ed3cb, W2a 6926f6ef, W4
a7846d33), the registry's `hp-m281` row C (0,176,255) M (240,0,192)
Y (255,255,0) from e043 (b005fae4). Design docs/CMY-DESIGN.md v0.3; the
print edge docs/CMY-GENERATOR-PLAN.md v0.4 W2a; FORMAT-SPACE §19.

STATUS: GENERATED, PRINTED (2026-10-11 night; PAGECOUNT 3412 → 3414), SCANNED (two captures each) and READ truth-fitted 2026-10-12 (§044.2): sheet A (c2) 5.830 % hard cell error = the probe's bands at these values, sheet B (c3) 0.571 % = 3.3× the probe's, the excess at the page's left where this print's magenta sits 1.3–2.8 dots low; no re-screen through CUPS; both pages non-affine at the dot level. The decode waits for the receiver's cmy waves. The receiver cannot
decode a cmy page yet (receiver W0–W5 owed): the first measurement is the
printed field against the GT with the e043 instruments. Single sheets —
NO promotion; every cmy row PROVISIONAL, catalog-only.

## 044.0 What is printed

Two counting volumes (e039's rule: `byte[i] = (i + 0x39 + k) mod 256`, k the
sheet's index, A = 0, B = 1), each filling its page at q = 0.8
(`--source-fraction 0.8`), A4 at 4 mm, the `rgb` route (three single-toner
ASCII85 `imagemask`s per page, no PJL, no HP operators):

| sheet | row | payload | job |
|---|---|---|---|
| A | `c2-cmy-r0775x0700@53x37` (the design's first c2 probe row, R4/R22) | `counting-A-c2-1123545.bin`, 1,123,545 B = the row's capacity at q 0.8, sha `8682fe0a85cdb83ec39e035c27399b2c7a7533c9a304a743cba958553c9a2133` | `page000.ps` 15,061,432 B, sha `8b9864e91b65e9ebdf64ccb88eb2557cd4dd042d66eab34d58480c93b52aa086`; K = 2,950 symbols, K/N 0.794, 1,961 tiles; stream tier not at this dial (needs q ≤ 17/36) |
| B | `c3-cmy-r0850@35x24` (the archival pitch at the top rung) | `counting-B-c3-558886.bin`, 558,886 B = the capacity at q 0.8, sha `3310f2171e2e79ee229214475809403008cafdad3b11b09203baa8e6df0d84f1` | `page000.ps` 14,181,472 B, sha `9d341eea502835c67058b1b6e10250f6e5a6c5e4df365cadd907675a951960fc`; K = 1,328, K/N 0.790, 840 tiles; needs q ≤ 1/2 for the dead-stream tier |

The payloads and jobs are derived (regenerable byte-for-byte by
`experiments/044-m281-cmy-first-print/generate_set.py --verify` against its
`JOB-SHA256.txt`) and not committed; the printed copies, their manifests
and ground truth (`*_gt.npy`) are in `scratch2/e044/jobs/` as `E044-A-*`
and `E044-B-*`, the payloads in `scratch2/e044/payloads/`, the previews in
`scratch2/e044/previews/`; the scans go to `scratch2/e044/captures/`, the
readouts to `scratch2/e044/readout/`.

## 044.1 Runs

*Path note, 2026-10-12 evening:* every `scratch2/…` path in this log (and in
§044.2–§044.6, the plan and the cmy RESULTS files) now reads `scratch/…` — the
old `scratch/` tree left for the evidence archive that day and `scratch2/` was
renamed in its place; the files themselves did not move.

*Capture note, 2026-10-13 (measured in e045 §045.4):* both `-2` captures were
scanned TURNED 180° on the glass — the centre windows' OR-ed registration
peak is 0.44 (A-2) and 0.60 (B-2) turned against 0.07 / 0.06 as-is, and the
receiver's facts carry rot_k 2 for every placement of both in M3 and M4 —
while the primaries lie as printed. The pairs are therefore a page-vs-platen
test on disk: the per-plane y steps stay at the same page x on all four
captures (printed), the Canon's seam lattice moves (scanner; e045 §045.6).


| run | when | what | command | result |
|---|---|---|---|---|
| 044.1g | 2026-10-11 22:34 | generate both | `PYTHONPATH=src env/bin/python ./confetti.py capacity --format c2-cmy-r0775x0700@53x37 --paper A4-4mm --printer hp-m281 --source-fraction 0.8 --json` → max_payload_bytes 1,123,545 (c3 row: 558,886); payloads by the rule above (`numpy`, 2 lines); `./confetti.py generate --format c2-cmy-r0775x0700@53x37 --paper A4-4mm --printer hp-m281 --source-fraction 0.8 -o build/p1/c2 build/p1/payloads/counting-A-c2-1123545.bin` and `./confetti.py generate --format c3-cmy-r0850@35x24 --paper A4-4mm --printer hp-m281 --source-fraction 0.8 -o build/p1/c3 build/p1/payloads/counting-B-c3-558886.bin` (from the worktree: `PYTHONPATH=src env/bin/python ./confetti.py …`, the worktree has no env/) | the two jobs above; each 3 `imagemask`, 3 `setrgbcolor`, 0 `setcmykcolor`, 0 PJL, 1 `%%Page`; gs 10.08 parses both (nullpage clean), 40 dpi previews `scratch2/e043c/p1-c2-preview-40dpi.png`, `p1-c3-preview-40dpi.png` |
| 044.1p | 2026-10-11 ~22:46 | print both | `lpr -o raw -P HP_Color_LaserJet_MFP_M281fdw__<host>_ build/p1/c2/page000.ps` then the c3 page, from the owner's terminal; PJL `INFO STATUS`/`PAGECOUNT` by `nc -w 30 <host> 9100` before and after | `Bereit`, PAGECOUNT 3412 before (sheet 3 was 3411 → 3412), **3414 after = TWO PAGES PRINTED** (CUPS jobs 108 and 109, 15,062,016 and 14,182,400 B queued, the queue empty after; the owner confirmed the pages); `Bereit`, ONLINE |
| 044.1s | 2026-10-11 23:08–23:34 | scan | the owner's protocol (Canon 2400 RGB, whole sheet), two captures per sheet | `scratch2/e044/captures/E044-A-c2-cmy-r0775x0700-hp-scan.tiff` (1,718,864,112 B, 20416 × 28064) and `E044-B-c3-cmy-r0850-hp-scan.tiff` (1,718,864,112 B) = the primaries of this readout; `…-scan-2.tiff` (A 1,718,864,112 B; B 578,363,392 B compressed, the same 20416 × 28064) kept for the receiver, unread here (the owner: "ignore the -2.tiff for now"); sha256 of the primaries in `scratch2/e044/captures.sha256` |
| 044.1r | 2026-10-11 night → | readout | TRUTH-FITTED (no fiducials on a format page): per-plane affines by truth correlation (measure/e040-plane-isolation/fit_planes.py's method), hard cell error and the 4 × 4 confusion at the per-plane poses with a per-page colour table, per-tile error map, x/y profiles, the whitened families per slice (the `lpr -o raw` footing's screening check), against sheet 3's bands at the same values — `measure/e044_cmy_truth/readout.py` (geometry and cells) + `screening.py` (the spectra; its CLI re-reads sheet 3's bands as the control), outputs `scratch2/e044/readout/{A,B,control-e043c}/` + README with the command lines; ~465 s and 7.7 GB per sheet, a re-run byte-identical | §044.2: A 5.830 % (= sheet 3's c2 bands), B 0.571 % (3.3× the probe's c3, all of it left of ~115 mm where M−C dy is −1.3…−2.8 dots); no re-screen on the CUPS route; the page not affine (±2–3 dots along y); a decode when the receiver's cmy waves land |

## 044.2 The truth-fitted readout (2026-10-12; `measure/e044_cmy_truth/`, an Opus worker; the numbers are the instrument's)

A format page has no fiducials, so the poses come from the truth: each plane's dot pattern correlated with its density channel (C ← R, M ← G, Y ← B) per 36-cell window (the e043 band reader's `read_window`), an affine and a quadratic fitted per plane (the e040 instrument's method restated — its module sits in a hyphenated directory and cannot be imported), hard four-state decisions with one colour table per page, the whitened families per 336-dot strip (the size of a sheet-3 band) with the cell lattice excluded at the page rotation. Peak memory 7.7 GB, 465 s per sheet, a re-run byte-identical. A first pass read 69 left-edge windows of sheet A at the nominal pose (their OR-ed peaks under the band reader's bar) and gave those tiles 29–35 %; a second pass with each window's 3 × 3-neighbour offset as the prior fixed it (page 5.97 → 5.83 %, worst tile 34.7 → 15.6 %); 68 windows stay at the prior, 15 C poses on the ±3-dot search edge.

**Geometry.**
| | A (c2) | B (c3) |
|---|---|---|
| page rotation / skew | −0.012° / −0.042° | −0.032° / −0.047° |
| scale x / y | 1.00104 / 1.00109 | 1.00105 / 1.00112 |
| M−C median (dy, dx) dots, p10…p90 of dy | (−0.15, +1.26), −1.56…+1.02 | (−0.92, +1.23), −2.37…+0.25 |
| Y−C median (dy, dx), |Y−C| | (−0.74, +1.18), 1.59 | (−0.41, +1.13), 1.47 (|M−C| 1.67) |
| affine / quadratic rms per plane (px) | 7.3–8.0 / 6.3–6.6 | 8.1–8.7 / 7.0–7.3 |
Neither page is affine, even with a quadratic: the residual is 1.86 / 2.06 dots rms and swings ±2–3 dots along y over 15–30 mm (print or scanner — the `-2` captures would tell, unread). A lateral bow: M−C dx runs 0.39 (left) → 1.61 (125–150 mm) → 1.21 (right), Y−C dx 0.12 → 1.55 → 0.96; M−C dy is −1.6…−1.9 dots over the left 35 mm on A and −2.5…−2.8 on B.

**Cell error** (per-plane poses, one colour table per page; sheet 3's bands at the same values beside):
| | cell % | C / M / Y % | per state W / C / M / Y % | W→C / M / Y % |
|---|---|---|---|---|
| A c2 | **5.830** | 2.448 / 1.938 / 2.904 | 14.93 / 0.71 / 2.82 / 4.97 | 4.98 / 3.62 / 6.33 (63.7 % of all errors in W cells) |
| e043c B1 / B14 (c2) | 5.63 / 5.81 | 2.48 / 1.93 / 2.61; 2.41 / 1.79 / 3.12 | 13.9 / 1.06 / 2.94 / 4.61; 14.6 / 1.01 / 2.47 / 5.13 | 5.06 / 3.50 / 5.34; 4.54 / 3.23 / 6.87 |
| B c3 | **0.571** | 0.187 / 0.133 / 0.312 | 1.89 / 0.01 / 0.17 / 0.22 | 0.54 / 0.33 / 1.03 (82.6 % in W cells) |
| e043c B2 / B15 (c3) | 0.176 / 0.166 | 0.071 / 0.026 / 0.090; 0.072 / 0.027 / 0.084 | 0.48 / 0 / 0.04 / 0.18; 0.44 / 0 / 0.04 / 0.18 | 0.25 / 0.06 / 0.18; 0.23 / 0.06 / 0.15 |
A across x: 10.05 % at 5–15 mm, 8.49, 7.06, then 4.7–5.5 %, rising to 7.39 / 6.80 % at 115–135 mm — e043's zones, where sheet 3's B1 has them (10.64 % at 12–21 mm, 7.08 / 7.14 % at 114–133). A down y: 4.3–7.1 %, tracking Y−C dy (Spearman −0.87); tiles median 5.40 %, worst 15.6 %, all in the left column. B across x: 1.2–1.9 % over 7–36 mm, 0.4–0.66 % over 36–115 mm, 0.11–0.24 % right of 115 mm; sheet 3's B2 reads 0.04–0.4 % at the same x; B's error follows M−C dy across x (Spearman −0.86); tiles median 0.29 %, worst 4.96 %. READ AS: the c2 page reads like the probe's bands in level, per-plane split, W-row and zones; the c3 page carries 3.3× the probe's error, all of it left of ~115 mm where this print's magenta sits 1.3–2.8 dots low and the stipple is ~1.5×, probe level to the right — print-to-print registration and the route cannot be separated with one sheet per route.

**Screening (the `lpr -o raw` footing).** No 188 lpi screen anywhere (per strip max 18–23, whole-field 1.9–2.3 = that spectrum's floor). c2: 165@14 per strip median 14–15, max 22 in C and Y, 38 in M in two strips (the left three slices 5/4/3 against 2 in the whole-field spectrum) — a weak component at the edge of noise. c3: 165@14 per strip C 145 median / 202 max, M 79/130, Y 49/95 — and sheet 3's c3 bands carry the same (published C 159/181, M 94/88; the control's re-read 184/201 and 90/95; whole-field C 93, M 54, Y 36 against sheet 3's 154, 64, 40; per slice at noise, max 34): a c3-field property of this engine at these values, not a new re-screen. The 212 lpi yellow stipple in Y: A per strip 77/109, per slice 16/89, the whole-field per slice 16 and 14 over the left 20 mm and 5–10 elsewhere; B per strip 108/177, per slice 24/76, 13–17 left of ~110 mm and 6–12 right of it; sheet 3 published 54–79 (c2) and 109–129 (c3). The CUPS raw route changed nothing the instrument can see.

**Dot level** (mean RGB at the per-plane poses, density over paper (230, 231, 233)): A — W cells (187, 177, 175), density 0.09–0.12: the 2-dot whites are already contaminated; C 0.377 in R; M 0.355 in G and 0.224 in B; Y 0.306 in B. B — W (199, 190, 191), 0.06–0.09; C 0.462; M 0.419 / 0.247; Y 0.357.

**Instrument notes.** The published sheet-3 whole-band stipple values and the control's re-read differ by up to ~25 % (B1 68 vs 54, B11 125 vs 98): the crop corners differ slightly and these peak ratios are that sensitive — per-sheet comparisons go through one instrument. The scanner's identity behind "hp-scan" in the capture names is not in the record (the Canon flatbed of record is assumed).

**What it means for the decode.** Hard decisions at 5.83 % put sheet A below the r0775 rung's hi-bit margin (the receiver plan's reader arithmetic); soft evidence, context and the conditioned stage are the receiver's answer, untested. Sheet B at 0.57 % hard is inside the top rung's margin by a wide mark; the receiver's first real target (M1).

## 044.3 — M1: sheet B DECODED, VERIFIED BYTE-EXACT (2026-10-12, machine 1)

The first decode of a real cmy page, from the ONE 2400 dpi capture
`scratch2/e044/captures/E044-B-c3-cmy-r0850-hp-scan.tiff` (sha256
`aeeca25c…`), through the production receiver at the merged tree
`0f60ad7c` (receiver A0–A5: addressing on R, cmy7's score lane, the one
knowledge rule, the page field under F_C ≡ 0; run from the frozen
worktree `<worktree> since removed):

```
PYTHONPATH=src:. env/bin/python confetti3.py decode \
    scratch2/e044/captures/E044-B-c3-cmy-r0850-hp-scan.tiff \
    --dpi 2400 --format c3-cmy-r0850@35x24 --workers 8 --diag 8023 \
    --out scratch2/e044/M1/run1
```

**Close VERIFIED: 558,886 bytes, sha256 `3310f217…` == the counting
payload `counting-B-c3-558886.bin` (§044.1).** Launched 07:45:27,
closed 08:19 — 34 min wall, 6,344.6 cpu-s, 26,805 jobs at 8 workers,
peak RSS ~3.6 GB observed. Tile-streams certified 1,332 of 1,680 (hi
656 · lo 676) against the close's 1,328 needed at q 0.8 — a 4-symbol
surplus, so the run stopped at the close with 1,335 jobs still queued
(`tiles.local` 567, `tiles.swim` 731, `refine.color` 11, `place` 21,
`color` 4, `fields.collect` 1); 348 tile-streams attempted and not
certified, 0 below the floor, 0 unknown. Certificates by row:
`tiles.local` 956, `tiles.scan` 371, `tiles.retry` 5 — the local-context
row carried the page, the scan 28 %. Metadata rank 24/24, equations
1,332/48, blocks 1/1. The page field (support 80 %, revision 975, 58
passes): C 0.00 ± 0.00 (the gauge origin), M 1.12 ± 2.27, Y 1.30 ± 2.15
dots — the readout's M−C +1.23 / Y−C +1.13 dots in x (§044.2) recovered
as the field's page means, with the left zone's spread in the ±. The
survey voted no printed pitch (tie or no snap) and proceeded on the
declared 1/200 in (the D5 fallback); the D1 address-contradiction alarm
fired once (window 0.0 vs the standing window over tile (2,5)'s cells,
diagnostic only; the payload is unaffected). Churn: `color` 0.774
cpu-s/fire at 41.8 fires per subject; `refine.color` 4,794 jobs, 1,278.6
cpu-s, 487 poses adopted; `tiles.retry` 10,896 jobs for 5 certificates
(1,610.9 cpu-s) — the retry row's price is the first cost question this
page raises. Artefacts: `scratch2/e044/M1/rundir/` (events.jsonl 15 MB,
facts.npz, the five panes, report.json, argv, tree — copied out of the
receiver's temp run dir), `scratch2/e044/M1/decode.log`.

Against the gate measurement (`measure/cmy_calibration/
RESULTS-2026-10-12-scorelane.md`: at the truth poses 840/840 tiles both
streams; with a converged field's offsets 768–800): the receiver reached
666 tiles' worth of streams (1,332 / 2) before the close ended the run
UNEXHAUSTED — `tiles.local` and `tiles.swim` had 1,298 jobs queued; what
the whole page would read is a `--complete` run, not taken. The second
capture (`…-hp-scan-2.tiff`) was not used.

Single sheet, single capture — NO promotion. First cmy volume from
paper; first colour volume from the M281 since the toner swap.

## 044.4 — M2: sheet A (c2) DECODED, VERIFIED BYTE-EXACT (2026-10-12, machine 1)

The first decode of a real c2 cmy page, from the ONE 2400 dpi capture
`scratch2/e044/captures/E044-A-c2-cmy-r0775x0700-hp-scan.tiff` (sha256
`2fd8430b…`), through the production receiver at `6e8a61d0` (A0–A8:
addressing on R, cmy7's score lane, the one knowledge rule, the page
field under F_C ≡ 0, `tiles.cond`, the translated residue rows, the
calibration chain), launched on the owner's word from the frozen
worktree `<worktree> (since removed):

```
PYTHONPATH=src:. env/bin/python confetti3.py decode \
    scratch2/e044/captures/E044-A-c2-cmy-r0775x0700-hp-scan.tiff \
    --dpi 2400 --format c2-cmy-r0775x0700@53x37 --workers 8 --diag 8023 \
    --out scratch2/e044/M2/run1
```

**Close VERIFIED: 1,123,545 bytes, sha256 `8682fe0a…` == the counting
payload `counting-A-c2-1123545.bin` (§044.1).** Launched 11:49:09,
closed 12:58 — 70 min wall, 22,058 cpu-s, 66,347 jobs at 8 workers,
peak RSS ~9.4 GB observed. Tile-streams certified 3,135 of 3,922
(hi 1,458 · lo 1,677) against the close's 2,950 at q 0.8; the symbol
count was reached at 3,118 with the block still NOT ready — every one
of the pooled fountain's 19 column groups was still open, the scarcest
16 rows short: each group needs ~K rows from the tiles that carry it,
a hi tile carries all 19 groups and a lo tile a rotating 17 of them, so
lo's 1,671 certificates counted 17/19 each toward every group
(1,447 + 1,671 × 17/19 ≈ 2,942 per group, reader arithmetic); the
close came 17 certificates later. (Corrected 2026-10-12: a first
reading here spoke of "the two groups only hi carries" — wrong; the
rotation spreads the light stream's deficit over all groups, the
REASONING-LOG entry of the day records the withdrawal.) Replayed from
the run's certificates in mint order into a fresh close (the diag's
per-group listing, built the same day on the owner's ask), the state at
3,118 was: 19/19 groups open, rows per group 2,934–2,952 against 2,950,
the scarcest group 14 at 2,934 (16 short) — and at 3,134 group 14 alone
stood 1 short. 787 tile-streams attempted and
not certified, 0 below the floor; 4,004 jobs still queued at the close
(`tiles.planek` 2,141, `tiles.swim` 1,380, `tiles.local` 405). Certificates
by row: `tiles.local` 2,875 (92 %), `tiles.scan` 182, `tiles.cond` 75 —
the conditioned decode's first certificates on paper — `tiles.retry` 3.
Metadata rank 24/24, blocks 1/1. **Cost:** `tiles.retry` ran 25,575 jobs
and 4,304 cpu-s for 3 certificates; `tiles.local` 9,175 jobs and 11,735
cpu-s for 2,875; `refine.color` 11,432 jobs (888 poses adopted) for none
directly. The page field solved TWICE (revision 1222, 18 passes, support
71 %) and never again: `fields.collect` is priced 180 × its fire ordinal
and sat behind the 210–220 residue rows for the rest of the run — the
arrows on the field pane are an early solve. Its page means: C 0 (the
gauge), M 1.00 ± 2.34, Y 1.36 ± 2.29 dots (the readout's M−C +1.26 /
Y−C +1.19 in x, §044.2, with the page's spread in the ±).

**The left band.** Certified tile-streams per tile column (one column =
128 dots = 5.43 mm; 106 possible per column):

| columns | x on the page | certified | share |
|---|---|---|---|
| 0–5 | 4–36 mm | 226 / 636 | 36 % (23, 33, 37, 43, 42, 48) |
| 6–18 | 37–107 mm | 1,258 / 1,378 | 91 % |
| 19–22 | 107–129 mm | 321 / 424 | 76 % (col 20: 65) |
| 23–36 | 129–204 mm | 1,330 / 1,484 | 90 % |

The two dips are the engine's zones of e041/e043 (the stipple zones at
x 12–45 and 96–140 mm; the e041 screener's column regions), not the
page's geometry: §044.2 put the per-plane registration at its BEST at the
left edge (M−C 0.4 dot against 1.6 mid-page) while the cell error was its
worst there (10 % in the first 10 mm, the leftmost tile column 14–16 %).
A page-wide colour head cannot follow a zoned engine, which is why the
tile-local refit carried this decode. Artefacts: `scratch2/e044/M2/
rundir/` (events.jsonl, facts.npz, the five panes, report.json, argv,
tree — copied out of the receiver's temp run dir), `scratch2/e044/M2/
decode.log`. Single sheet, single capture — NO promotion. First c2 cmy
volume from paper: 1,123,545 B over the A4-4mm c2 cell field of
57,579 mm² (CMY-DESIGN §3.3) = 156.1 b/mm² at this sheet's q 0.8; the
row's §3.3 figure at q 0.9 is 1,265,230 B = 175.8 b/mm². (Corrected
2026-10-12: a first reading quoted ≈ 167 and §3.3's 1,197,117 B, which
is the r0700 row's.)

## 044.5 — The left band across the fresh-toner reprint records (a reading, 2026-10-12)

A reading of e028/e029 (K controls), e038, e041, e043 and e044 by five
Opus readers and one synthesizer, on the owner's question whether the
left band M2 could not certify (x 4–36 mm, 36 % against 90 %, §044.4) is
one page-fixed engine behaviour across the HP reprint-era prints. A
reading of the records, not a measurement; the synthesizer's table is
in the session record, the findings are these.

- **x is the laser's fast-scan axis** (e001:36/58; e002's 90° rescan put
  the y-wander in the transport), so a band at fixed x down all 53 tile
  rows sits at the start or end of every scan line, not at the lead edge.
  No record says which end the laser starts from, nor that every sheet
  was fed the same way round.
- **Where the band ends is only agreed by the two e044 sheets** (a step
  at 34.8–36.7 mm on A and B); e043b puts it at 40–45 mm, e043 sheet 1
  at 12–21, e041's composite bands at 19–39 mm MOVING with the composite
  share. Where it starts was never measured (colour content begins at
  12 mm on the probes, 4.7–7.5 mm on e044). A single fixed zone is not
  established.
- **K-only pages show no left zone** (e029 at tile resolution, old
  toner; e041's U14 flat on the screen statistic; fresh-toner K error by
  x is UNMEASURED).
- **The sign contradicts across constructs.** Composite pages read
  BETTER in both zones (e038's M/Y band at 108–113 mm; e041's region 1
  UNSCREENED over the first 7–27 mm, S14 A2 6–9 % against 34–36 %); the
  single-toner pages of 2026-10-11 read WORSE there; e041's own
  single-toner bands (10-05/06) were flat or better on the left. Three
  things differ between those and e043/e044 and none is separated: the
  day's engine state, the cyan value (255/208 against 184/176), the
  construct (indexed image against masks).
- **Two zones recur**, left and middle (96–115 mm onward: e038, e041,
  e043b, e043 sheet 1, e044 A and M2's dip); e044 B has no middle
  excess.
- **The one feature on every fresh-toner colour print measured for it
  is density**, gradual (M/Y denser toward x ≈ 20 mm: e041 incl. the
  09-13 F, e043 4–7 levels darker, e044 a few levels), whereas e044's
  error steps at 35 mm.
- **Registration is NOT ruled out — a correction to §044.4's reading.**
  "Registration best at the left edge (0.4 dot)" is the x component
  only. The y component is LARGEST at the left: M−C dy −1.6…−1.9 on A
  against −0.6…+1.0 mid-page, −2.5…−2.8 on B with a step at 36.7 mm, so
  Y−C reaches ~1.8–2.3 dots on the left against 1.5–1.8 mid-page
  (reader arithmetic). A 1.2–1.5-dot step over ~10 mm is what the page
  field, smoothed to pass a 100 mm wave, leaves as residual; 69 left-
  edge windows failed M2's first pose pass. The owner's "different
  screening at the beginning" is measured on composite pages (e041's
  region 1) and UNMEASURED as the cause of e044's band: for it, the
  stipple 2–3× there (e043b, e044 A); against it, the excess survives at
  C 176 where the stipple is gone, and e044 found no 188 lpi screen.
- **The discriminating measurement, on scans already on disk:** per
  5 mm slice of e043c sheet 3 (one sheet, one day, only the cyan value
  changing across bands), then e044 A/B — per plane in its own channel,
  the ink-vs-white separation at the slice's OWN best per-plane pose, the
  white and ink levels, the 212/165 lpi power and the y-offsets, set
  against the cell error at the readout's pose. Separation flat across x
  and the excess gone at local poses → a registration step (printer-made,
  a receiver-model matter); separation lower on the left with fogged
  whites at every cyan value → a rendering loss fixed in the print;
  lower only where the stipple is zoned → the screening reading. The
  same per-slice error on e041's U14 K band says whether the zone needs
  colour at all. Not run.

*Measured 2026-10-12 (e045, experiments/045-m281-left-band.md §045.3–§045.9):*
the band is printed misregistration of one plane. On the 10-11 prints (e043
sheets 1–3, this log's A and B) cyan steps by about one 600-dpi line in y at
~33 mm page x; left of it cyan stands 1.5–2.5 dots from magenta and yellow,
right of it within about half a dot — at every cyan value 176–208, in masks
and Indexed images alike. The 10-05/06 prints (e041 S14/S15/S17, cyan 208 in
the Indexed construct) have no such step and no band: an engine state of
10-11, not a property of the content. The middle dip is yellow's step at
~114 mm against magenta. Not screening (the band survives at cyan 176 with
the stipple at noise and does not move with the content's start), not fog
(bare paper flat). The readout's own left-edge error was inflated by pose
searches that stopped at ±3 dots, and by the Canon's seams (e045 §045.6).

## 044.6 — Sheet B READ TO 100 % on machine 4: both captures, `--complete` (2026-10-12)

The owner's run on machine 4 (128 GB), the merged main `2abb8316`, both 2400
dpi captures of sheet B, every row drained:

```
PYTHONPATH=src:. env/bin/python confetti3.py decode \
    scratch2/E044-B-c3-cmy-r0850-hp-scan.tiff \
    scratch2/E044-B-c3-cmy-r0850-hp-scan-2.tiff --dpi 2400 --dpi 2400 \
    --format c3-cmy-r0850@35x24 --max-pages 1 --complete --workers 14 \
    --diag 8023 --run-dir scratch2/e044/M3/rundir --out scratch2/e044/M3/payload.bin \
    2>&1 | tee -i scratch2/e044/M3/decode.log
```

**1,680 of 1,680 tile-streams (hi 840 · lo 840) — the whole page; close
VERIFIED, 558,886 bytes, sha256 `3310f217…` == the counting payload; K
1,680 against 1,328.** Launched 14:18, the payload written 14:41 — about
24 min wall at 14 workers, 61,091 jobs, 12,660.7 cpu-s (M1 on machine 1, one
capture to the close: 34 min, 6,345 cpu-s for 1,332). Both captures
calibrated (12/12 lane fits); the first capture again took the survey's
no-vote fallback. Certificates by row: `tiles.local` 1,034, `tiles.scan`
388, `tiles.cond` 131, `tiles.union` 64, `tiles.swim` 36, `tiles.planek` 16,
`tiles.retry` 11 — the first paper mints for `tiles.union`, `tiles.swim`
and `tiles.planek` on a cmy page, and `color.pooled_ctx` born for the first
time on cmy (25 fits, 104.7 cpu-s, minting nothing itself by design), so
the two-capture rows the receiver plan listed as unproven on cmy have
run. The page field solved TEN times (`fields.collect` 11 fires, 592 cpu-s;
`fields` 10, 6.4 cpu-s) to support 100 %: C 0 (gauge), M 1.42 ± 1.74,
Y 1.30 ± 1.74 dots (M1's two solves had stopped at 71 % support, M 1.12 ±
2.27, Y 1.30 ± 2.15 — *dated note 2026-10-18: the two solves at 71 %
support were M2's, sheet A (§044.4); M1 reached 80 % support (revision
975, §044.3), and the M and Y figures here are M1's*) — once the payload rows ran dry, the 180 × ordinal
price no longer held the field back. Cost: `tiles.retry` 26,661 jobs and
3,084.5 cpu-s for 11 certificates (M1: 10,896 for 5), the standing price
question; `tiles.local` 2,188 jobs, 3,545 cpu-s for 1,034. Artefacts on
machine 4: `scratch2/e044/M3/` (`decode.log`, `payload.bin`, `rundir.30447/`
— the receiver suffixes `--run-dir` with its pid). Single sheet — NO
promotion; the first cmy page read to 100 %.

## 044.7 — Sheet A (c2) READ TO 99.5 % on machine 4: both captures, `--complete` (2026-10-12)

The owner's run on machine 4, the merged main `2abb8316` (the M3 tree), both
2400 dpi captures of sheet A, every row drained:

```
PYTHONPATH=src:. env/bin/python confetti3.py decode \
    scratch2/E044-A-c2-cmy-r0775x0700-hp-scan.tiff \
    scratch2/E044-A-c2-cmy-r0775x0700-hp-scan-2.tiff --dpi 2400 --dpi 2400 \
    --format c2-cmy-r0775x0700@53x37 --max-pages 1 --complete --workers 14 \
    --diag 8023 --run-dir scratch2/e044/M4/rundir --out scratch2/e044/M4/payload.bin \
    2>&1 | tee -i scratch2/e044/M4/decode.log
```

**3,904 of 3,922 tile-streams (hi 1,948 · lo 1,956 of 1,961 each); close
VERIFIED, 1,123,545 bytes, sha256 `8682fe0a…` == the counting payload; K
3,904 against 2,950, every one of the 19 column groups at rank 2,950 (3,697–
3,698 rows each) when the deferred close was consulted at the drain.**
Launched 14:48, the payload written 15:58 — about 70 min wall at 14 workers,
150,835 jobs, 43,103.6 cpu-s (M2 on machine 1, one capture to the close: 70 min
at 8 workers, 66,347 jobs, 22,058 cpu-s for 3,135). Certificates by row:
`tiles.local` 3,252, `tiles.scan` 232, `tiles.swim` 184, `tiles.cond` 118,
`tiles.union` 62, `tiles.planek` 48, `tiles.retry` 8. hi trailed lo by 219 on
M2 (1,458 vs 1,677) and by 8 here — the second capture and the residue rows
closed the stream gap the one-capture run showed.

**The left band is reachable.** Tile columns 0–5 (x 4–36 mm), 36 % certified
on M2, are at 618 of 636 = 97.2 % here, every other column 106/106 = 100 %.
The band's certificates by row: local 373, swim 152, planek 34, cond 29, scan
27, union 3 — the swim's largest cmy yield so far sits in the band, which is
what the residue rows are for; the 18 uncertified tile-streams are 14 in tile
column 0 (the outermost 5.4 mm, x 4–9 mm: rows 9, 15, 16, 18–20, 43–45, 52,
hi on all of them, lo on 16, 44, 45, 52) and 4 in tile row 52 (the last row
along the page, columns 1, 4, 5). So on this receiver with two captures the
band is an edge loss of one tile column, not a format-axis loss; the stripe
line (§044.5, branch `m281-stripe`) keeps the question of WHY the band reads
worse, which this run does not answer.

**Under `--complete` the close is counted, not solved, until the drain.** The
diag read `close deferred (counting)`, then `groups 0/19` (solved groups) and
`groups open 19/19` while every group was count-ready from ~3,480
certificates on; `symbols 3098/2950` with every group short earlier in the run
was the same display reading certificates where an uneven pair's honest K
line is the scarcest group's rows (a lo tile counts 17/19 toward each group).
Two display nits for the diag, on the owner's word: `solve deferred` instead
of `groups 0/19` under counting, and the per-group rows as the K line for an
uneven pair (recorded in the receiver plan §5).

The page field: 23 passes, converged, support 99 % (M 1,942 and Y 1,933 of
1,961 tiles), C 0 (gauge), M 1.36 ± 1.90, Y 1.36 ± 1.92 dots — the readout's
figure is the median magnitude ± the median prior-scale uncertainty, not the
field's spread (the spatial sd of dx is 0.40 dots); `fields.collect` 17 fires,
700.9 cpu-s, `fields` 14 fires, 70.7 cpu-s; against §044.4's two solves at
71 % support. Costs: `tiles.retry` 66,045 jobs and 8,648 cpu-s for 8
certificates (M2: 25,575 for 3; the owner's stance stands — a per-encoding
data point, never a cap); `tiles.local` 10,621 jobs, 17,916 cpu-s for 3,252;
`refine.color` 18,507 jobs, 3,861 cpu-s, 1,605 poses. `HOLO3_COLOR_ROW_ADOPT=
last` in the run's environment (the tree file records it). Artefacts on the
machine 4: `scratch2/e044/M4/` (`decode.log`, `payload.bin`, `rundir.30630/` —
`report.json`, `facts.npz`, `events.jsonl`, the panes); mirrored on machine 1 as
`scratch/e044/M4/{facts.npz,report.json,decode.log}` and, for sheet B,
`scratch/e044/M3/{facts.npz,report.json,decode.log}`. Both e044 sheets are
now read whole or to one edge column from two captures each; single sheets —
NO promotion.

## 044.8 — The two sheets' page fields compared: across the page the same, along it one roller out of phase (2026-10-12)

The owner's question ("how similar are the page fields for c2 and c3 on the
machine 4?"), then his model ("the two pages were printed right one after the other,
and the toner rolls probably were at different starting points" — a linear
shift along y). Instrument `measure/e044_cmy_truth/compare_page_fields.py`
over the two runs' final `facts.npz` (§044.6 sheet B, 30 passes, support
100 %; §044.7 sheet A, 23 passes, 99 %): both `PlaneField`s put on one 2 mm
grid from the page centre (the tile matrices are centred by the layout, so
the frames agree within ~2 mm), compared where both have measured support
(12,834 cells); x = the short page axis (210 mm, across the process
direction), y = the long axis (297 mm, along it); displacements of M and Y
against C in printed dots (F_C ≡ 0). Figure
`scratch/e044/fields-A-c2-vs-B-c3.png` (rows M dx, M dy, Y dx, Y dy;
columns A, B, A − B).

| plane, component | mean A (c2) | mean B (c3) | rms A − B | Pearson |
|---|---|---|---|---|
| M dx | +1.08 | +1.02 | 0.22 | 0.83 |
| Y dx | +1.04 | +1.01 | 0.25 | 0.79 |
| M dy | −0.13 | −0.78 | 0.99 | 0.57 |
| Y dy | −0.51 | −0.28 | 0.88 | 0.30 |

**Across the page the two prints carry the same field.** M and Y sit about
one dot toward +x of C on both sheets, with the same bow across the short
axis: +0.3–0.4 dots at the −x edge, +1.4–1.5 at the centre-right, +0.9–1.1 at
the +x edge, for both planes (20 mm bins: M dx A +0.43 +0.51 +0.68 +1.01 +1.21
+1.45 +1.50 +1.40 +1.24 +1.06, B +0.37 +0.61 +0.69 +1.02 +1.33 +1.17 +1.36
+1.23 +1.01 +1.12). Means within 0.06 dots, rms difference 0.22–0.25 dots =
under an eighth of a c2 cell: the engine's scan-direction registration is a
stable property two pages apart.

**Along the page each print is a different phase of one wobble.** The y
profiles (mean over x) of dy carry a sinusoid of period 69–75 mm, amplitude
0.50–0.61 dots on both sheets and both planes (M: A 73 mm 0.50, B 69 mm 0.54;
Y: A 73 mm 0.59, B 71 mm 0.61; R² 0.56–0.64; dx carries a weaker 61–65 mm
component of 0.05–0.16 dots). M and Y are IN PHASE within a print (A +124°/
+132°, B −139°/−126° at 72 mm): under the gauge the wobble that both show
against C is C's roller or an element common to all three, and the field
cannot say which. Between the prints the phase differs by 97–107° = 19–21 mm,
and the whole M plane sits 0.65 dots further along the process direction on A
than on B.

**The owner's model holds.** Evaluating B's field at y + s for s in [−40, 40]
mm and removing one constant per plane, the residual against A has one clean
minimum for both planes at the same place: M dy rms 0.74 → 0.35 at s = −21
mm (r 0.57 → 0.91), Y dy 0.85 → 0.31 at s = −23 mm (r 0.30 → 0.91); one
COMMON shift s = −23 mm with an offset and a skew per plane gives rms 0.33,
r 0.90/0.91, offsets M +0.70 and Y −0.15 dots, skews −0.04 and −0.10 dots per
100 mm of x (nothing: the planes are not rotated differently between the
prints). The dx fields prefer the same sign of shift more weakly (−14/−17 mm,
rms 0.22 → 0.18 and 0.24 → 0.17). The 23 mm is a third of the 70 mm period,
the phase fit's 19–21 mm. If the period is a circumference (Ø ≈ 22 mm by
arithmetic) a 23 mm advance between consecutive pages means a page pitch of
n turns ± 23 mm — 297 mm of paper plus a 14 or 38 mm gap — consistent with
back-to-back printing, not a proof of it. Left after the shift: rms 0.31–0.35
against the dx floor of 0.16–0.18, the honest print-to-print residual. (On the
live snapshot read while the c2 run was at 61 % M support, A's M wobble came
out at half B's amplitude — the prior's pull where the evidence was thin; at
99 % support the amplitudes agree.)

So the M281's colour registration between two consecutive prints decomposes
into a stable bow across the page, a stable ~70 mm wobble along it with a
per-print phase, a per-print constant per colour, and a third of a dot of
residual. The page field solves all of it per page, which is why both sheets
read whole; where the decomposition could matter is a sparse page — with the
period known, phase and offsets are four numbers per print, and a prior that
knows the period would fill holes like the M gaps of the live snapshot better
than the pull-to-zero does (a design observation in the receiver plan §5, not
a request). Two sheets of one engine, both e044's — NO promotion.
