# e045 — the M281's left-of-page band, measured per x slice on scans already on disk

Date: 2026-10-12 evening. Engine: HP Color LaserJet Pro M281fdw "<host>" (home), fresh toner epoch
(2026-09-13); the prints are the 2026-10-11 ones — e043 sheet 3 (E043c, raw 9100) and e044 A (c2) and B (c3)
(`lpr -o raw`). Scanner: the Canon flatbed at 2400 RGB (the "hp-scan" captures). NOTHING PRINTED, NOTHING
SCANNED: every number below is read from scans already on disk. Instrument `measure/e045_left_band/` (cells,
slices, spectra, sheet3, analyze, figure); artefacts `scratch/e045/` (not committed).

STATUS: sheet 3 READ per 5 mm slice (§045.3, the first table); the page-vs-scanner question ANSWERED on e044's
two 180°-turned second captures (§045.4): the 18.2 mm error spikes are the SCANNER's (platen-fixed), the
per-plane y steps are the PRINT's (page-fixed). The seams on every Canon capture since 2026-07-20 (§045.6); the
10-05/06 prints have no cyan step at ~33 mm and no band (§045.7); sheets 1 and 2 put the step and the band on
the ENGINE'S STATE of 10-11, not on construct or cyan value (§045.8); the reading §045.9, the owner's questions
§045.10, owed §045.11. RECORD DONE 2026-10-13 on the owner's word: the e044 capture note, the CLAUDE.md
entries and this log merged to main the same day. Single sheets of one engine — NO promotion.

## 045.0 The question

e044 §044.5: on the 2026-10-11 cmy single-toner mask prints the cell error is 1.5–3× higher over page x
~4–36 mm (and again ~107–135 mm). Three readings, to be separated per x slice:

- **(a) a registration step** — the excess goes away at local per-plane poses, separation flat; a
  receiver-model matter (the page field's smoothing length);
- **(b) a rendering loss fixed in the print** — separation lower on the left with fogged whites, at every cyan
  value;
- **(c) the screening reading** — separation lower only where the 212 lpi stipple is zoned (present at cyan
  184/192, absent at 176).

The e041 screening research (docs/M281-COLOUR-2026-10-05.md §2; e041 §041.5m) adds tests: the screener
switches per PAGE-FIXED column region (edges at the page left and ~107–108 mm) after a composite-pixel budget
(270–660 %·mm) that white before content lengthens. If the zone is a region's start state, its end should MOVE
with the content's composite budget (the yellow the colour path adds to cyan grows ~3× from 176 to 192 on sheet
3, §043.6) and with the lead-in white (content from 12 mm on sheet 3, 4.7 / 7.5 mm on e044); the middle edge
should sit at ~107–108 mm on every band.

## 045.1 Runs

| run | when | what | command | result |
|---|---|---|---|---|
| 045.1r | 2026-10-12 19:00 | sheet 3, all 15 bands | `PYTHONPATH=src:. env/bin/python -u -m measure.e045_left_band.sheet3 --scan scratch/E043-m281-cmy-probe3-a-scan.tiff --manifest scratch/e043c/jobs/E043c-m281-cmy-probe3.manifest.json --gt scratch/e043c/jobs/E043c-m281-cmy-probe3-gt.npz --summary scratch/e043c/readout/summary.json --out scratch/e045/sheet3 --workers 10` (scan sha256 `85894c27…` == `scratch/e043c/scan.sha256`) | 661 s, ~3 GB; `slices.csv` (band × 5 mm), `profile_1mm.csv`, `windows.csv`, `subwindows.csv`, `paper.csv`, `summary.json`, `sheet3.log`; the sampler reproduces read_window's cells to 0.17–0.29 grey levels per channel |
| 045.1a | 19:15 | zones, edges, regression | `… -m measure.e045_left_band.analyze --dir scratch/e045/sheet3` | `zones.csv`, `edges.json`, `regression.json`, `analyze.log`; `first-table.txt` |
| 045.1f | 19:30 | the figure | `… -m measure.e045_left_band.figure --dir scratch/e045/sheet3 --png scratch/e045/sheet3-left-band.png` | per-plane y offset vs x (median over the 15 bands); c2 error per 1 mm at the readout's and at local poses |
| 045.1p | 19:40, re-run 21:10 | the platen test | first ad hoc, then the kept module: `… -m measure.e045_left_band.platen --manifest scratch/e044/jobs/E044-A-manifest.json --gt scratch/e044/jobs/E044-A-page000_gt.npy --scan …/E044-A-c2-cmy-r0775x0700-hp-scan.tiff --scan …-scan-2.tiff --out scratch/e045/platen` and the same for B (`platen.log`, per capture `-platen.csv/.json`); the module reproduces the ad hoc numbers to the digit | A-2 and B-2 were scanned TURNED 180° (OR-ed peak 0.44 / 0.60 rot180 vs 0.07 / 0.06 as-is); §045.4 |
| 045.1s | 21:00–23:30 | the scanner seams | `… -m measure.e045_left_band.seams detect|archive|table|cost …` (Opus builder; the archive captures rebuilt under `/tmp/e045-seams` by the release's `tools/unpack.sh`, sha256_raw checked, deleted after; commands in `scratch/e045/seams/README.md` and `archive_commands.sh`) | 16 captures, `seams.csv`, `cost.json`; §045.6 |
| 045.1e | 21:00–23:40 | the 10-05/06 prints | `… -m measure.e045_left_band.e041 sheet|summarize …` on S14, S15, S17 rebuilt under `/tmp/e045-e041` (sha256_raw `198a2521…`, `2f79036a…`, `f708339b…`; deleted after; commands in `scratch/e045/e041/README.md`) | §045.7 |
| 045.1d | 23:50 | sheets 1 and 2 | `… -m measure.e045_left_band.sheet3 --scan scratch/E043-m281-cmy-probe-a-scan.tiff --manifest scratch/e043/jobs/E043-m281-cmy-probe.manifest.json --gt scratch/e043/jobs/E043-m281-cmy-probe-gt.npz --summary scratch/e043/readout2/summary.json --out scratch/e045/sheet1` and the same for sheet 2 (`scratch/e043b/…`, `readout/summary.json`, `--out scratch/e045/sheet2`); the per-band table by a short script in the session (`scratch/e045/day-vs-construct.txt`) | 246 s, 284 s; §045.8 |

## 045.2 The instrument

Per band (sheet 3): the readout's own windows (bands.read_window, 36 cells, per-plane poses within ±3 dots of
the window's OR-ed registration — or of the NOMINAL pose where that registration is under its bar), then the
same windows re-read with the 3 × 3 window-neighbour prior (the e044 readout's pass 2), then each window's 2 × 2
sub-windows of 18 cells posed again. One box sampler (`cells.sample_field`: the cell's central half at the
plane's pose, R for C, G for M, B for Y) reads every pose arm:

| arm | poses |
|---|---|
| read | the readout's (its own X: the e043 band numbers) |
| win | the windows with the neighbour prior |
| local (`finex`) | the sub-window poses CROSS-FITTED by halves: the pose fitted on a sub-window's top 8 rows reads its bottom 9 and the reverse (one guard row); `fine` is its in-sample twin, 0.1–0.5 pp better: the in-sample optimism is small |
| diff | C at its window pose, M and Y at C's plus the window differential smoothed by a 6.7 mm Gaussian (the page field's 30 mm transfer, PAGE-FIELD-DESIGN; an emulation, not the solve) |
| common, aff | every plane at C's pose; one affine per plane over the page |

Per 5 mm slice: four-state hard error with a genie colour table (`band` = one per band, the readouts'; `slice` =
one per slice); per plane in its own channel the white (W cells) and ink levels, d', the best-threshold error; a
neighbour model (a cell's own-channel value on its four neighbours' states: intercepts = white and ink with
all-white neighbours; per neighbour state the N − S and W − E spill asymmetry); the window offsets M − C, Y − C;
the whitened screen families (the e043 stipple instrument: 212 lpi in Y, 165, 188); bare paper in the 2.03 mm
gaps between the bands (their central 1 mm).

## 045.3 Sheet 3 per slice — the first table

c2, pooled per cell (genie colour tables; `read` = the readout's poses and one table per band, i.e. the e043
number; `win`, `local` = slice tables; d' per plane in its own channel at local poses; W_G, W_B = the mean W
cell in G and B; paper G = the inter-band gaps; offsets in printed dots, + = down the page; Y213 = the 212 lpi
stipple in the Y density, noise 5–16 per slice):

| x mm | read | win | local | d'C | d'M | d'Y | W_G | W_B | paper G | M−C dy | Y−C dy | Y213 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **cyan 176 (B1 B9 B11 B13 B14)** |
| 12–17 | 8.96 | 6.45 | 6.53 | 4.04 | 4.02 | 3.67 | 174.7 | 173.5 | 230.4 | −2.00 | −1.76 | 11 |
| 17–22 | 8.69 | 7.58 | 6.81 | 4.19 | 4.00 | 3.52 | 174.7 | 172.5 | 229.8 | −1.82 | −1.74 | 7 |
| 22–27 | 7.31 | 5.96 | 5.82 | 4.29 | 4.04 | 3.72 | 174.3 | 172.2 | 229.8 | −1.80 | −2.24 | 10 |
| 27–32 | 6.43 | 5.51 | 5.45 | 4.26 | 4.18 | 3.85 | 175.5 | 174.8 | 229.5 | −2.23 | −1.92 | 12 |
| 32–37 | 7.93 | 7.53 | 6.36 | 4.16 | 4.12 | 3.62 | 177.7 | 174.4 | 229.7 | −1.22 | −0.94 | 12 |
| 37–42 | 4.12 | 3.93 | 3.85 | 4.97 | 4.70 | 4.02 | 181.4 | 176.8 | 229.8 | −0.55 | −0.50 | 14 |
| 47–52 | 4.43 | 4.37 | 4.21 | 4.77 | 4.57 | 4.00 | 181.1 | 178.4 | 229.8 | −0.90 | −0.91 | 8 |
| 102–107 | 5.28 | 4.72 | 4.51 | 4.47 | 4.53 | 4.03 | 178.0 | 177.7 | 229.4 | −0.39 | −0.48 | 9 |
| 112–117 | 6.13 | 5.44 | 5.24 | 4.53 | 4.33 | 3.71 | 176.7 | 177.4 | 229.3 | 0.75 | 0.46 | 11 |
| 117–122 | 7.75 | 6.51 | 6.52 | 4.46 | 4.21 | 3.39 | 175.8 | 173.9 | 229.3 | 0.70 | −0.42 | 13 |
| 122–127 | 8.08 | 7.27 | 7.42 | 4.27 | 4.19 | 3.30 | 178.4 | 175.7 | 229.0 | 0.59 | −0.50 | 14 |
| 187–192 | 3.96 | 3.98 | 3.81 | 5.25 | 4.54 | 4.02 | 180.9 | 179.1 | 229.3 | 0.45 | 0.01 | 12 |
| **cyan 192 (B7)** |
| 12–17 | 7.89 | 6.50 | 6.90 | 3.80 | 3.97 | 3.69 | 173.2 | 170.9 | 230.4 | −2.06 | −2.15 | 37 |
| 22–27 | 7.75 | 6.45 | 6.80 | 4.18 | 3.90 | 3.47 | 173.7 | 169.3 | 229.8 | −1.90 | −2.68 | 34 |
| 37–42 | 4.02 | 3.77 | 3.90 | 4.79 | 4.67 | 3.99 | 180.9 | 174.4 | 229.8 | −0.56 | −0.88 | 22 |
| 122–127 | 8.77 | 7.94 | 8.27 | 4.08 | 4.08 | 3.14 | 177.6 | 173.1 | 229.0 | 0.81 | −0.67 | 33 |

Every slice and band: `scratch/e045/sheet3/first-table.txt`, `slices.csv`; zone means `zones.csv`; the figure
`scratch/e045/sheet3-left-band.png` (top: each plane's y offset against its own 40–100 mm level, median over
the 15 bands; bottom: c2 error per 1 mm at the readout's and at local poses, the scanner seams ticked).

What the sheet says — every item after the three refuters of 045.5, their corrections folded in:

1. **The readout's pose failures are a small part, except at the very edge.** In the readout's first pass 7 M
   and 8 Y of 320 c2 LEFT windows stopped on the ±3-dot search edge, every one after its OR-ed registration
   had failed (the planes then searched around the nominal pose; their true M/Y dy −2.9…−4.3 dots), mostly in
   the first window column of B1, B9 and B14; MID had none. On one colour table the neighbour prior moves the
   pooled C176 LEFT error 7.13 → 6.61 % (MID 4.90 → 4.75); it dominates only in B1's first slice (11.99 →
   5.78 %). The per-slice colour table is worth more on the left than the prior: band → slice table 7.86 →
   7.13 % on the LEFT against 4.99 → 4.90 % in MID (0.42–0.94 pp per band vs 0.04–0.16) — a level shift
   confined to the left zone.
2. **An excess survives local poses on every c2 band.** LEFT/MID at local poses per band 1.26–1.47 (B11 1.26,
   B5 1.27, B1 1.30, B13 1.31, B3 1.40, B7 1.40, B14 1.44, B9 1.47); pooled c2 LEFT 6.20 / MID 4.55 % at cyan
   176, 5.47 / 3.90 at 178, 6.04 / 4.75 at 184, 6.61 / 4.71 at 192. At c3: 0.27 / 0.11 at 176 (B2 2.3×, B15
   2.0×), 0.52 / 0.12 at 178, 0.57 / 0.14 at 192 — but **no resolvable excess at c3 cyan 184** (B6: 0.13 vs 0.11
   %, 29 vs 65 errors). Cyan value is confounded with band y (176 pools five bands, the others are one band
   each at their own y): the spread within cyan 176 (1.26–1.47) brackets every other value, so the sheet
   excludes a proportional dependence on the stipple, not a weak one.
3. **Separation is lower on the left at local poses, in all three planes:** c2 cyan 176 d' C 4.19 vs 4.59, M 4.07
   vs 4.55, Y 3.68 vs 3.98, uniform over all five LEFT slices and stepping between the 32–37 and 37–42 mm slices
   (d'C 4.13 → 4.92). The field's W cells are 4–5 levels darker in G and B on the left, but **mostly by spill
   from inked neighbours**: W cells with four white neighbours differ by 0.5–4.5 levels in G at c2 and not at all
   at c3 (w0 R/G/B 220.1/218.7/220.6 left vs 220.1/219.0/221.2 mid). **Bare paper is flat** (gaps R 229.45 vs
   229.28, G 229.85 vs 229.62) and the GT coverage per zone is identical, so it is not fog and not flare (the
   page left of the field is blank). The ink differs: with all-white neighbours C is lighter on the left (c2 p0
   107.6 vs 105.8 in R), M and Y darker (113.5 vs 116.3 in G, 129.4 vs 133.7 in B) — the density gradient e041,
   e043 and §044.5 recorded.
4. **Inked neighbours spill as much everywhere, only the direction changes.** A W cell read in G at magenta's
   pose darkens by ~22 levels more next to a cyan cell on one side than on the other in every zone (vector
   magnitude 22.4 / 20.0 / 22.0 / 22.8, LEFT / MID / MIDZ / RIGHT at c2): along y on the left (M − C dy −1.8),
   along x elsewhere (M − C dx +1.2–1.7). The left is set apart by the direction of the displacement, not its
   size; whether a y displacement costs more than an x displacement at c2 (the M281's development anisotropy)
   is untested.
5. **Each plane steps in y by about one 600-dpi line at fixed page x, plane by plane.** Against each plane's own
   level (figure, top; independently re-measured by a refuter with a strip cross-correlation that does not use
   this instrument, R and G alike for cyan): C −1.0 dot at 31.5–34.5 mm (per band −0.83…−1.18), C −1.2 at
   106.5–110 (−1.10…−1.59), Y −1.0 at 112.5–115.5 (−0.80…−1.34), in all 15 bands, M flat at those x. More steps
   elsewhere (C ~152, ~186; M ~26, ~45, ~69–70; Y ~21, ~42, ~69, ~167; M and Y together at ~69–70 mm). Between
   steps the drift is COMMON to the three planes (the page/scan bow against the fiducial affine). So the "left
   zone" is the stretch where cyan has not yet stepped while M and Y sit 1.5–2.5 dots from it in y; the middle
   zone's excess starts where Y steps (~114–116 mm; 110–114 is at baseline) and ends near Y's next step (~167).
6. **The offsets account for part of it, model-dependently.** Within the LEFT zone the error rises with |M − C|
   and |Y − C| in y (quartiles 6.12 / 6.81 / 6.96 / 7.70 %), in MIDZ with |M − Y| in y (5.01 → 8.91). The
   share of the zone excess they explain depends on the specification (LEFT 20–60 %, MIDZ 76–85 %), so no single
   share is quoted. Matched on offsets (vector |M−C|, |Y−C| < 1.6, |M−Y| < 0.6 dots; band-table error at local poses; re-run
   by the author from subwindows.csv) the c3 left excess nearly vanishes (0.18 vs 0.10 %, n 131 / 915) while ~60 % of
   the c2 left excess remains (5.52 vs 4.11 %, n 183 / 1,880, against 6.90 vs 4.57 unmatched).
7. **Where the band ends, and where it starts.** Cyan's first step, at 31.5–34.5 mm, is the band's end on
   every band of sheet 3 (lattice resolution ±0.8 mm) and on all four e044 captures (045.4). The error's own
   edge wanders (21.5–33.5 mm left, 107.5–116.5 mm middle) because the scanner seams of 045.4 sit at 35.7 and
   108.7 mm on this placement. The band's START is not measurable on these sheets: the offsets are constant from
   the first printed cell (12 mm here, 4.7 / 7.5 mm on e044) to cyan's step, and bare paper shows nothing.
8. **The screener.** No composite re-screen in any zone of any band (165 and 188 lpi at 8–13, noise). At cyan
   176 the 212 lpi stipple sits at its noise in LEFT and MID alike (9–12) while the c2 excess is 1.30–1.44×; at
   184/192 the stipple is resolved and zoned (LEFT and MIDZ above MID). The zones coincide with the e041
   screener's page-fixed geometry: cmyk5 ran unscreened over 12–35 and 108–142 mm (S14), K/red switched on at
   35.1–39.1 mm (S16 T7–T9), the region boundary is ~107–108 mm (S15, S9b rot180). Cyan's two steps sit at
   those x. A shared x, not a tested link; and the "composite budget moves the edge" test of 045.0 does not
   discriminate (single-toner cmy content never switched e041's screener, and the stipple's amplitude is not a
   composite-pixel count).

## 045.4 Page or scanner: the 180°-turned second captures of e044

All three primary scans put page x = 0 within 0.5 mm of the same platen position (sheet 3 −0.85, e044 A −0.55,
B −1.01 mm), so the primaries alone cannot separate a page-fixed effect from a platen-fixed one. The e044 `-2`
captures can: both were scanned TURNED 180° (the centre windows' OR-ed peak 0.44 / 0.60 rot180 vs 0.07 / 0.06
as-is; the receiver's facts say rot_k 2 for every placement of both, M3 and M4) — the record never said so
(§044.1 "kept for the receiver").

- **The 18.2 mm error spikes are the scanner's.** On every capture the three colour channels jump together in x
  by −0.5…−0.9 dots every 18.29 mm. On B the jumps fall at page x 16.6 + 18.3k mm, on the turned B-2 at
  12.0 + 18.3k; in platen coordinates both are one lattice, and A / A-2 likewise (16.9 + 18.3k vs 10.8 + 18.3k).
  The seam columns also stand out on bare paper, as a step in column level (up to 1.5 grey levels) and noise —
  the first draft's "bare paper shows no column anomaly" tested the column mean against a 61-column median and
  was wrong (refuter, 2026-10-12, §045.6). e041's per-column spikes (U14 and every c2 band: 18, 53, 72, 107,
  127, 146, 162, 181 mm) are the same lattice on that placement. The lattice across the archive, its size and
  what it costs: §045.6.
- **The per-plane steps are the print's.** On all four e044 captures cyan steps by −0.7…−1.0 dot between page
  x 32.6/33.7 and 36.7/37.2 mm and again at 107–110 mm, yellow at ~114–116, magenta at neither; M − C dy is
  −1.4…−2.7 left of cyan's step and −0.2…−1.1 right of it — on the turned captures too, where the page's left
  edge lay at the platen's right end. Sheet 3, printed the same night, has the same steps at the same page x.

## 045.5 The refutation (three Opus refuters, read-only; the workflow record of the session)

Instrument, statistics and claims lenses on the eight claims of the first draft. Upheld: the separation drop
and flat paper, the neighbour asymmetries' numbers, the per-plane steps (independent re-measure). Weakened and
corrected above: the pose-failure share (item 1: the slice table, not the prior, is the larger left term), "at
every cyan value" (fails at c3 184), "W cells darker" (spill), the spill as the left's cause (same size in every
zone), fixed edges as evidence against the screener (non-discriminating), the regression's single share
(specification-dependent), page-vs-platen (decided by the turned captures). Instrument defects recorded, NOT
yet repaired (045.7): the regression uses the band-table error and in-sample offsets; the edge finder is locked
to the sub-window lattice; windows.csv keeps no pass-1 offsets; the cross-fit's half fits and its fallback rate
are not written; the halves' evidence mask is laid at the window's mean pose (C sits 1.4–1.5 dots from it on the
left edge); the scanner seams are not modelled by any arm; the diff arm cannot represent a step; zones are a
hard-coded LEFT < 35, MIDZ 107–137 rather than the measured steps.

## 045.6 The Canon flatbed's seams, across the archive (2026-10-12 night)

`measure/e045_left_band/seams.py` (Opus builder, Opus refuter): a detector without ground truth — the seam
columns from the column edge energy against its running median, the jump from the cell lattice's phase along the
scan columns per block of rows — validated on sheet 3 and the four e044 captures against §045.4's ground-truth
positions (within 0.2–1.0 mm, inside that method's sub-window), then run on archived Canon captures rebuilt
under /tmp from the evidence release (sha256_raw checked, deleted after). Outputs `scratch/e045/seams/`
(`seams.csv`, one `<label>.json` per capture, `cost.json`, `cost_cells.csv`, `README.md` with the commands).

| capture | date | dpi, mode | lay | seams | jump, printed dots |
|---|---|---|---|---|---|
| e027 charsheet1 | 2026-07-20 | 4800 grey | as printed | 8 / 11 | −0.83 |
| e029 c2-K | 08-04/05 | 4800 grey | as printed | 11 / 11 | −0.84 |
| e033 H | 08 | 1200 RGB | as printed | 11 / 11 | −0.87 |
| e033 H | 08 | 2400 RGB | as printed | 11 / 11 | −0.83 |
| e033 I | 08 | 4800 RGB | as printed | 11 / 11 | −0.82 |
| e036 H | 09-03/04 | 2400 RGB | crosswise | 11 / 11 | −0.79 |
| e035 J (copy 2) | 09-02/03 | 2400 RGB | as printed | 10 / 11 | −0.83 |
| e038 F print 1 | 09-13/14 | 2400 RGB | as printed | 10 / 11 | −0.84 |
| e040 G | 10-02 | 2400 RGB | as printed | 11 / 11 | −0.84 |
| e041 S14 | 10-05 | 2400 RGB | as printed | 10 / 11 | −0.84 |
| e042 D c2-K | 10-06/09 | 2400 grey | as printed | 11 / 11 | −0.92 |
| e043 sheet 3, e044 A, A-2, B, B-2 | 10-11 | 2400 RGB | as printed / turned 180° | 10–11 / 11 | −0.84…−0.86 |

- **The same scanner columns on every capture since the earliest one in the release:** 1559|1560 + 1728k at
  2400 dpi (779|780 + 864k at 1200, 3119|3120 + 3456k at 4800), i.e. 16.51 + 18.288k mm from the scan's left
  edge; 18.288 mm = 0.72 in exactly. Sixteen captures, prints of three engines (M281, AltaLink, Canon iR-ADV),
  grey and RGB, as printed, crosswise and turned. Canon scans before e027 are not in the release, so "since
  2026-07-20" is the honest bound.
- **Each seam has its own fixed jump** (median over the captures, printed dots, k = 0…10): −0.92, −1.00, −0.79,
  −0.76, −0.82, −0.71, −0.75, −0.86, −0.88, −0.94, −0.88; spread across captures 0.03–0.07 (independently
  re-derived by the refuter within 0.06). The three colour channels jump together (0.03–0.09 dots apart). The
  jump's own width is not resolved below the fit's gap (~0.85 mm). The "stretch between seams" the first form of
  the module reported is circular (measured against the capture's own mean pitch) and is withdrawn.
- **What it costs a cell readout** (sheet 3 re-read per cell, 15 bands × 10 seams; replaces §045.4's first
  estimate): 18.288 mm is exactly 432 printed dots — six 36-cell c2 windows, four c3 windows — so the seam sits at
  the same place in every window (cell ~27 of 36 at c2, ~6 at c3). At c2 the window's 9-cell minority side, read
  at the other side's pose, carries +6.7…+6.9 pp over the 0.76 mm right of the seam (+4.4 pp in the next 0.25 mm,
  +0.7…+1.8 on the majority side); at c3 +0.24…+0.90 pp over 0.75 mm. Nothing outside the window holding the
  seam; fake seams at the same window phase half a period away show nothing (the refuter's control). With
  cross-fitted 18-cell sub-windows the c2 excess is +6.2…+6.5 pp over 0.5 mm. These are the e045 instrument's
  windows; what the production receiver pays is not measured.
- **Moving the sheet between captures:** sideways, along the platen's width (the scan's x), by half a period,
  9.14 mm, puts each capture's seams farthest from the other's; any shift whose remainder modulo 18.288 mm lies
  between one window and one period minus a window works (3.1–15.2 mm for 3 mm c2 windows, 4.6–13.7 mm for 4.6 mm
  c3 windows: 9.1 ± 4.5 mm covers both). Shifts near 0, 18.3, 36.6 mm do not help; moving along y does nothing;
  a 180° turn is no substitute (it moved B's seams 4.6 mm in page x). Alternatively the lattice is fixed in scan
  columns and visible on bare paper, so a reader can cut its pose windows at the seam columns instead.
- Refuter corrections folded in: three engines, not four; sixteen captures, not seventeen; "channels", not
  "planes"; the spike locates the seam and stands on bare paper; `excess_profile` groups by a rounded period
  index (minor, owed).

## 045.7 The prints of 2026-10-05/06 (e041 S14, S15, S17; Canon 2400 RGB, rebuilt under /tmp)

`measure/e045_left_band/e041.py` (Opus builder, Opus refuter): the page fitted on the five fiducials; the
four-state single-toner bands (S14 A1/B1/B2 c3, B3 c2; S15 R8 c3, R9 c2; S17 U12 c2, U13 c3) through sheet3's
path; per-plane window and sub-window poses on the cmy8, cmyk5 and dot-mixed bands from their own dot planes;
U14 (c2 K) per slice. Outputs `scratch/e045/e041/` (README.md, report.txt, steps.csv, plane_profile.csv,
screen_events.csv, zones.csv, S14/ S15/ S17/).

- **No cyan step at ~33 mm on these prints.** Cyan per band across 26–43 mm: −0.37…+0.23 dots on all 20 colour
  bands of S14/S15/S17, against −0.76…−1.27 on all 15 bands of sheet 3 (the refuter's re-derivation without the
  reference subtraction). Cyan does step at 109.5 mm (−0.9…−1.3; every band of all four sheets), 156 and
  190.5 mm; yellow at 112.5 mm (sheet 3: 115.5); magenta not at 109–113. Magenta and yellow drop together by
  0.5–0.9 at 49.5–51 and 75 mm on these prints against ~26, 44 and 69–70 mm on sheet 3: those move between print
  days (the drops at ~18 and 34.5 mm sit within ~1 mm of this placement's seams and are not counted). K (U14)
  has no y step.
- **So no left band on these prints, by this measure.** At local poses the four-state c2 bands read LEFT/MID
  1.16–1.25× as built; with the seam slices (±2 mm of the lattice) and each band's first 5 mm excluded the
  refuter finds 1.10× (S14 B3), 1.08× (S15 R9), 0.93× (S17 U12) — not distinguishable from a gradient, where
  sheet 3's non-seam slices drop sharply at 37 mm. The first 5 mm of every band read higher on all three sheets
  (a band-edge effect or a narrow engine strip, unresolved). Left and middle offsets differ by at most 0.25 dot
  (S17's whole page sits at Y − C −1.7…−2.0, M − C −0.8…−1.0, left and middle alike).
- **U14 (K only).** At the readout's poses 6.04 / 4.36 / 4.08 % (left / middle / right of 107 mm); at local poses
  with slice tables 4.88 / 3.99 / 3.92, a smooth left-high gradient of about half its first size, no K step.
  Isolated white flat (213.9 vs 214.6), isolated K ink darker on the left (104.0 vs 108.8 vs 110.5). Its
  correlations with the white-cell spread and mean are partly circular (they feed d'); only the darkening per K
  neighbour is partly independent, 8 % stronger on the left.
- **The screen against the steps (S15 R1–R7, S14 A2/A3/B4).** cmy8 from 12 mm: on at 21.1–22.2 mm, reset at
  105.1–105.7, on again at 119.7–120.4; S15 R5 (cmy8 from 50 mm): clean to ~95, fully screened by 102.2, reset at
  107.1, on again at 118.1; cmyk5: on at 34.6–34.9, reset at 106.5–107.4, on again at 141.2–142.1. The reset sits
  2–4 mm left of cyan's 109.5 mm step; the cmyk5 switch-on shares x with a magenta/yellow drop and a seam; every
  other switch-on and re-switch-on, and yellow's step, coincide with nothing. The switch-on moves with the content
  and the white before it (21, 35, 102 mm); the steps do not. A shared position at the reset, no tested link.
- Defects recorded (owed): seam and band-start slices not masked in `zone_rows`; edge steps from a changing band
  set in `find_steps` (spurious steps at 15 mm in `steps.csv`); slice tables fitted and scored on the same cells
  (conservative); `cells.py` cannot take a band's dot planes, so `e041.py` carries its own window readers.

## 045.8 Day or construct: sheets 1 and 2 of e043 (2026-10-11; the instrument of §045.2 unchanged)

The 10-05/06 prints differ from sheet 3 in three ways at once: the day, the construct (8-bit Indexed images
against masks) and the cyan value (208/255 against 176–192). Sheets 1 and 2 of e043 were printed on 10-11 like
sheet 3, and each carries BOTH constructs on one print: sheet 1 at cyan 208 — e041's value — in M-hex and M-a85
masks and I-2, I-8 and I-ref Indexed images; sheet 2 at cyan 184 in a85 masks and the three Indexed images, c2
and c3. Read by `sheet3.py` (a band without its own colour lookup takes the sheet's; the 1 mm gaps get a smaller
inset), outputs `scratch/e045/sheet1/`, `scratch/e045/sheet2/`; the per-band comparison
`scratch/e045/day-vs-construct.txt`. Per band, the raw cyan dy step from 26–32.5 to 36.5–43 mm (median over
sub-window rows, no reference subtracted: the planes' common bow adds about +0.5…+0.9 over that span, as M and Y
show), and the left / middle error at local poses with each band's first 5 mm and ±2 mm of every scanner seam
masked:

| sheet (all 10-11) | cyan G | construct | cyan step at ~33 mm | M, Y over the same span | c2 LEFT / MID, masked | c3 |
|---|---|---|---|---|---|---|
| 1 | 208 | masks (B1, B2) | −0.87, −1.15 | +0.56…+0.87 | 1.12, 1.29 | — |
| 1 | 208 | Indexed I-2, I-8, I-ref | −1.19, −1.09, −1.03 | +0.33…+0.70 | 1.35, 1.11, 1.24 | — |
| 2 | 184 | mask (B1; c3 B5) | −0.83 (c3 −1.03) | +0.34…+0.85 | 1.24 | 3.7 |
| 2 | 184 | Indexed I-2, I-8, I-ref (c3 B6 I-2) | −1.13, −1.24, −1.14 (c3 −1.04) | +0.34…+0.69 | 1.16, 1.34, 1.45 | 2.5 |
| 3 | 176–192 | masks, 15 bands | −0.76…−1.27 | +0.14…+0.94 | 1.25–1.42 | 1.2–4.3 |
| S14, S15, S17 (10-05/06) | 208 / 255 | Indexed, 20 colour bands | −0.37…+0.23 | — | 0.93–1.10 | — |

Every band of the three 10-11 sheets steps (cyan also steps at ~110 mm and yellow at ~114 mm on every band of
all of them), whatever its construct or cyan value, and carries the left excess; the 10-05/06 prints, at e041's
cyan and in the construct sheet 1's I-bands share, do not step at ~33 mm and carry no band. **The cyan step at
~33 mm, and the left band with it, is a state of the engine on 10-11, absent on 10-05/06 — not the construct,
not the cyan value.** It held over the day (sheet 1 ~12:20, sheet 2 ~16:00, sheet 3 evening, e044 ~22:45).
The density gradient (C ink lighter, M and Y darker on the left) is on the 10-05/06 prints too (§045.7), so it
is not what makes the band. What changed the engine between the days is not measured (a colour-plane
registration calibration would be one candidate; untested).

## 045.9 The reading (single sheets of one engine; 2026-10-12 night)

- **The left band is printed misregistration of one plane.** The M281 lays each colour's rows with steps of
  about one 600-dpi line at fixed page x, plane by plane. On the 10-11 prints cyan steps at ~33 mm; to its left
  cyan sits 1.5–2.5 dots from magenta and yellow in y, to its right within about half a dot. That stretch is the
  band. The middle zone is the same with yellow: it steps at ~114 mm and stands about a dot from magenta until
  its next step near 167 mm.
- **It belongs to the engine's state, not to our content:** present on every band of three 10-11 sheets in both
  constructs and at cyan 176–208, absent on the 10-05/06 prints at e041's cyan in the same construct (§045.8).
  The step at ~110 mm is there on both days.
- **Hypothesis (a), registration step:** yes, but printed, so local poses do not undo it. At c3 the offsets
  explain the excess (it nearly vanishes at matched offsets); at c2 about 60 % remains at matched offsets in
  §045.3 item 6, yet no band exists where the step does not, so that residual belongs to the step too (that a y
  offset costs more than an x offset at c2 is the candidate, untested; S17's whole page sits 1.7–2.0 dots Y − C
  in y and reads higher everywhere).
- **Hypothesis (b), rendering loss:** no. Bare paper is flat, isolated whites barely differ, and the left density
  gradient exists on the 10-05/06 prints without a band.
- **Hypothesis (c), screening:** no. No composite re-screen on any of these pages; the stipple is at noise at
  cyan 176 where the band is; the band does not move with where the content starts (4.7, 7.5 and 12 mm), while
  the screener's first switch-on does (21, 35, 102 mm, §045.7). The screener's page-fixed reset at ~105–107 mm
  sits 2–4 mm from cyan's ~109.5 mm step: a shared neighbourhood, no tested link.
- **K needs no colour for its own gradient:** U14 has a smooth left-high gradient at local poses (4.9 vs 4.0 %)
  and no step — a single plane has nothing to step against; a different, smaller effect.
- **The scanner** adds its own fixed seams every 18.288 mm (§045.6), which made the first edges look sharper and
  the e041 per-column spikes; they are not the band.

## 045.10 The owner's questions of 2026-10-12 night, answered

- *The evidence folder* `<home>/src/evidence/paper-store-evidence-holo-2026-10/041-m281-screen-routes`:
  used read-only; S14, S15 and S17 rebuilt under /tmp with the release's `tools/unpack.sh`, sha256_raw checked,
  deleted after; nothing in the folder written.
- *The strips that began 50 mm from the left (S15 R5) and still switched to screening after a while, and again
  after the middle:* the screener's first switch-on follows the content's start and the white before it (12 mm
  start: on at ~21 mm; cmyk5 at ~35 mm; R5 from 50 mm: on at ~95–102 mm); its reset at ~105–107 mm and its
  re-switch-on (~118–120, ~141 for cmyk5) do not. The left band does not behave like the switch-on: its end
  stayed at ~33–36 mm on sheets whose content began at 4.7, 7.5 and 12 mm, and on 10-05/06 there was no band at
  all although the same screener behaviour was there. The only shared x is the reset beside cyan's ~110 mm step.
- *The scanner artefact:* the jump is in x (along the sensor, across the platen), not in y, at the same 11
  scanner columns on every Canon capture in the release since 2026-07-20 (§045.6); about 0.84 printed dots; it
  costs one pose window at each seam (≤ 3 mm at c2, ≤ 4.6 mm at c3); shift the sheet sideways by ~9 mm (any
  4.6–13.7 mm) between captures.

## 045.11 Owed (on the owner's word)

1. The instrument defects of §045.5, §045.6 and §045.7 (seam and band-start masking in the zone tables, the
   regression on slice-table error with cross-fitted offsets, step finding per band, pass-1 offsets written,
   `cells.py` taking a band's dot planes).
2. e044 A, A-2, B, B-2 per slice (the turned captures as the page-vs-platen test for the error zoning).
3. The y-versus-x offset cost at c2, at matched offset size.
4. The engine state: whether the per-plane steps move after the M281's colour calibration (a print-and-scan
   question for the owner's go); the same probe before and after would answer it.
5. The scanner seams for the receiver: what they cost its placement, and pose windows cut at the seam columns.
6. DONE 2026-10-13 (the owner: "document all the outstanding pieces"): e044 §044.1 carries the capture note
   that both `-2` captures were scanned turned 180°, and §044.5 a pointer to this record; CLAUDE.md's scanner
   facts carry the Canon seams and the ~9 mm sideways re-placement, its channel facts the M281's per-plane y
   steps, its 044 entry the measured reading, and the 045 index entry exists.

