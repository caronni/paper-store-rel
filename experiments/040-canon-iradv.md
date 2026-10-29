# e040 — Canon iR-ADV C257/357 (<city>): the 1200x2400 request refused, single dots alive

Date: 2026-09-24. Engine: **Canon imageRUNNER ADVANCE C257/357**, firmware
3017.104, PostScript LanguageLevel 3 — identified by the printer's own
HCAL-R1 self-report, read from a phone photo (040.2). Print path: `lpr -o
raw` through an AirPrint queue on the operator's Mac (CUPS → IPP; the Canon
accepted raw PostScript on that door) — footing `lpr-raw`, the e031 kind,
NOT raw9100. Media: US Letter (the report says page 612x792 pt). Scanner: none on site; every number below is from phone
photos (phone camera, 12 MP + two 50 MP frames).

STATUS: **BOTH DISCOVERY PAIRS PRINTED (e039's default pair and its
1200x2400-request pair) + SHEET J (c1-cmy8), NOT SCANNED.** Three of the
four report strips photographed decoded CRC-clean; the resolution verdict is
the printer's own, on both 1200x2400 sheets.
Single sheet, new engine — NO promotion.

## 040.1 What was printed

e039's second discovery pair, `discover emit --request 1200x2400 --kind
both`: the B/W sheet asks `/HWResolution [1200 2400]` in its setpagedevice
and draws its five resolution-block columns at 300 / 600 / 1200 / 2400 /
1200x2400 source dots (28 x 1.5 mm strips at x 28/59/90/121/152 mm, y
195–206 mm of the A4 layout: g1-v, g1-h, g2-v, g2-h, dots, line-pair); the
morphology rows and everything else are 600-dpi layout. Whether the colour
sheet was printed too: OPERATOR TO FILL (two 50 MP photos of a colour
random field exist, 040.4).

## 040.2 The self-report, read from a phone photo — THE VERDICT

Photo `photo-2026-09-24-1.jpg` (12 MP, the bottom report strip at
~9.7 px per module, hand-held, bowed): rectified by its own border bars,
illumination-flattened, decoded by the instrument's `decode_report_image`
(`experiments/040-canon-iradv/report_from_photo.py`); six of
eight enhancement variants return the SAME CRC-valid 160-byte payload
(flatten alone: 1 parity repair, 0 XOR; unsharp/RL: 0/0):

| field | value |
|---|---|
| identity | stage discovery, kind bw, copy 0, request_code 5 (= 1200x2400), layout_digest_128 `1a7bfc713efd52be3a96da4987287de5` (== the emitted sheet's) |
| product / version | `iR-ADV C257/357` / `3017.104`, LanguageLevel 3 |
| default_resolution | (600, 600) |
| **effective_resolution** | **(600, 600)** — the `[1200 2400]` request was NOT honoured; the interpreter kept 600x600 |
| page_size_points | (612, 792) = US Letter |
| process_color_model | DeviceCMYK; duplex false |
| print_nonce | 1079582489 |

The second photo (`photo-2026-09-24-2.jpg`, 9.1 px per module, softer) never
decodes — sync wrong in all four rows, 38 bad bytes of 164 under every
enhancement: at this scale the reader's half-pixel aperture is inside the
lens blur. Rule of thumb from the pair: a strip needs ≥ ~10 px per module
AND focus; a 50 MP frame of the strip alone would give ~40.

So on this Canon, as on the AltaLink (e007.6/e009), a PostScript
`/HWResolution [1200 2400]` request is silently refused and the page images
at 600. The resolution block's 1200/2400/1200x2400 columns will therefore
show 600-grid point-sampling of finer content (not yet photographed —
photo 1 is the 300-dpi column: two rows of dots across the strip, ~41
along it = pitch 8 at 300).

## 040.3 Morphology, from photos 2 and 3 (600-dpi layout)

- **Single 1-dot isolated dots PRINT** (the `morph/isolated_dots/8` panel,
  second from the right above the microtext row): a faint but complete
  regular lattice on the paper — the first engine in the record with
  cell=1 visibly alive on a PostScript path (M281 e025 and AltaLink e031:
  dead both polarities). Contrast low (faint); 1-dot white holes: NOT yet
  inspected.
- 2-dot isolated dots print as a clean lattice; 2-dot white holes in the
  solid block are OPEN; 1-on-3-off and 2-on-6-off gratings crisp;
  2-dot-stroke microtext "HCAL 012345" legible; solids dense.
- Resolution block, 300-dpi column: 1-on-1-off gratings resolved as lines.

## 040.4 Colour, two 50 MP photos — INCONCLUSIVE

`photo-2026-09-24-50mp-1.jpg`, `…-50mp-2.jpg`: sheet J's c1-cmy8 field —
ONE DOT PER CELL PER PLANE, 42 µm cells.
Both are out of focus at dot level (the second less so: discrete cyan /
magenta / yellow / red / green / blue / dark blobs at roughly cell scale, no
diagonal line screen visible — the LOOK of per-plane cells, not of the
VersaLink's screened mush — but not a verdict). Owed: a sharp close-up
(tele-macro, ≥ 8 px per cell) or the loupe on the pure C/M/Y patches.

## 040.4a The four report strips (`photo-2026-09-24-4.jpg`, 8160x6144, ~15.7 px per module)

One frame of the stacked sheets holds four machine-report strips. Read with
`report_from_photo.py` (raw variant, CRC-clean, 0 errors where it decodes):

| strip in the photo | sheet | request | effective resolution | page device | nonce |
|---|---|---|---|---|---|
| 1 (top, under "END … bw") | B/W discovery, **1200x2400 request** (digest `1a7bfc71…`) | code 5 = [1200 2400] | **(600, 600)** | 612x792 = Letter | 1079582489 (== photo 4's) |
| 2 (under "END … color") | **colour** discovery, 1200x2400 request (digest `81b279f7…`) | code 5 | **(600, 600)** | 612x792 = Letter | 1079605569 |
| 3 | **colour** discovery, **DEFAULT request** (digest `af63bd28…` == e031's colour layout) | code 0 | (600, 600) | **595x842 = A4** | 1079621240 — decoded only after handing the decoder its two border bars (a glare gap breaks the instrument's one-continuous-run bar rule; the tool now falls back to the row-profile bars) |
| 4 (bottom) | B/W discovery, **DEFAULT request** (digest `cbcab84f…` == e028/e031's) | code 0 | (600, 600) | **595x842 = A4** | 1079620315 |

THE MECHANISM the page-device field exposes: every discovery sheet asks
`/PageSize [595.28 841.89]` (A4) in its guarded `setpagedevice`; the
1200x2400 sheets ask `/HWResolution [1200 2400]` in the SAME dictionary.
The default sheet came back A4; the two 1200x2400 sheets came back Letter,
the printer's default. So on the Canon the combined request FAILED AS A
WHOLE (the `stopped` guard swallowed the error and the page stayed at its
defaults, Letter at 600) — the resolution was refused with an error, not
silently substituted while honouring the page size. Same measured law as
the AltaLink (e007.6/e009), a different failure mode. All four sheets of
e039's two discovery pairs were printed, and all four photographed strips
read. Also: the chat-sized 2000-px copy of this frame (~3.8 px per module)
STILL decoded strip 1 in the raw variant — the reader's floor is lower than
040.2's rule of thumb when the strip is level and in focus.

## 040.4b Sheet J (c1-cmy8) from the two 50 MP frames — one null, one cut off

holo3 `c1-cmy8-r0700@106x74`, `--max-pages 1 --no-close`, 2 workers, RGB
TIFF captures, per-frame pitch from the survey's own estimator: frame
`photo-2026-09-24-50mp-1.jpg` 9.09 px per cell (5455 dpi; the survey votes 1/300 at 2600–
2727, so 5455 is its consistent run), frame `photo-2026-09-24-50mp-2.jpg` 4.35 px per cell
(2609 dpi, accepted silently; 2500/2720 "no snap", proceeding). Outcomes:
5455 on the first frame = NULL (support 171,819 cells ≈ 42 tiles, 1,144
placement jobs, 1,318 cpu-s, 0 poses, 0 words) — the softer frame at dot
level; 2609 / 2500 / 2720 on the second frame = KILLED BY THE 1,200 s CAP
before a status block (support 1,153,397 cells ≈ 280 tiles; placement
had not finished) — no address word in 20 minutes of placement. RULING
(Germano, 2026-09-24): that is enough — no re-run, nothing more started;
phone photos of a one-dot-per-cell colour sheet are not a capture. The
scanner is the instrument for this sheet.

## 040.4c Sheet E (c1-k-r0700@106x74) scanned — 21 % raw cell error, NOT RECOVERED (2026-09-30)

The Canon's print of e039 sheet E, scanned on the Canon flatbed at 2400
dpi grey (`scratch/<city>/v.tiff`, placed 180° — every placement rot_k
2). holo3 `--max-pages 1 --workers 8 --diag 8023` on machine 1, main tree:
ONE address word, 430 chained poses, 1,896 tiles attempted, 0
certificates in 35,641 cpu-s (457,516 jobs); stopped by one SIGINT on
Germano's ruling once the per-tile error was measured
(`scratch/<city>/run-E-canon.33065`).

Raw hard cell error against the emitted field
(`measure/e039-cell-truth/cell_error.py`, median threshold, from the
run's own placements): **21.3 % over 9,459,168 placed cells; per tile
(1,753 tiles with ≥ 90 % of their cells placed) min 17.3 %, p5 18.4 %,
median 20.2 %, p95 26.4 %, max 35.3 % — no tile below 15 %.** Inked
cells 125.6 vs blank 172.5 (the faint single dots of 040.3). r0700
needs roughly 5 % hard (8–10 % with soft decisions and context), so no
tile is within reach and `tiles.local` (price 220, never fired — starved
by the flat-priced retry band on main) could not have changed that.
c1-K now fails on all three engines tried: VersaLink 21.5–22.0 % (e039),
HP M681 no placement at 4800 (e039), this Canon 21 %.

Would a 4800 rescan help? Measured by DEGRADING instead (same 9,459,168
placed cells, `v.tiff` box-averaged): 600 dpi (1 px/dot) 27.2 %, 1200
(2 px/dot) 22.6 %, 2400 as scanned (4 px/dot) 21.3 % — the steps shrink
4.6 → 1.3 pp, so 4800 would buy well under a point (~20.5–21 %), against
the ~8–10 % r0700 needs and a best tile of 17.3 %. The limit is the print
(faint single dots), not the sampling; no 4800 rescan. Side result: an
area read (4x4 px box per dot) is WORSE than the centre point, 24.7 vs
21.3 % — the dot's edge already bleeds into its neighbours at 2400.

## 040.4d The four discovery sheets scanned, and two payload volumes VERIFIED (2026-10-01)

Canon flatbed, 2400 dpi (B/W grey, colour RGB), `scratch/<city>/`:
`w.tiff` B/W 1200x2400 request (hand-labelled "Canon image runner <city>, <ip>"), `x.tiff` B/W default, `y.tiff` colour default,
`z.tiff` colour 1200x2400. Letter stock trims every page: the 1200x2400
sheets (rendered on Letter, 612x792) lost their TOP pair of chiral
corners and top report strip, the default sheets (rendered A4, 595x842)
their BOTTOM pair, bottom strip and end sentinel. Production `discover
analyze` refused all of them (`corner_registration_failed`, two corners;
x then `page_integrity_unobservable`, end sentinel).

**Placed from every visible mark** —
`experiments/040-canon-iradv/analyze_visible_marks.py`
(diagnostic, not promotable): production registration, or a similarity
through the two surviving corners; then the full affine REFITTED over the
corners plus every resolved internal `geometry_plus` mark (all 10 resolved
on all four sheets), twice (24- then 12-dot search); a trimmed end
sentinel let through and recorded (`trimmed_sentinel_override`). Refit rms
7.0–9.5 px at 2400 (~2 printer dots); registration-map residual max
4.5–6.7 dots (from 14.1 on the two-corner start). All four analyse `ok`.

Self-reports — one strip per sheet decodes CRC-clean (0 parity / sync /
xor errors), the other is trimmed: all four `iR-ADV C257/357` fw
3017.104, PS 3, DeviceCMYK, default AND effective (600, 600), simplex,
no serial / imaging bbox. Request code 5 (1200x2400) on w, z with page
612x792 (Letter, the Canon's own choice under that request); code 0
(default) on x, y with page 595x842 (A4, trimmed by the Letter stock).
Print nonces (the printer's `realtime` clock, ms): w 1079582489, z
1079605569 (+23.1 s), x 1079620315 (+14.7 s), y 1079621240 (+0.9 s) —
the 1200x2400 pair first, the default pair back to back (one job).

| B/W, 600 grid | w (1200x2400 req) | x (default) |
|---|---|---|
| c3 | solid 0.06 % | marginal 0.05 % (window 1.0 %) |
| c2x3 (2 wide, 3 tall) | **solid 0.21 %** | marginal 0.26 % |
| c3x2 | marginal 0.56 % | marginal 0.57 % |
| c2 imagemask / vertical / horizontal | 2.1 / 2.6 / 4.4 % | 2.5 / 3.0 / 4.6 % |
| c2 diagonal | fragile 5.9 % | fragile 6.3 % |
| c4–c6 | solid 0 % | solid 0 % |
| c1 | unmeasurable (geometry) | unmeasurable |

600-grid rulers: dots 1.5 % fail; 1-on/1-off fail; 2-on/2-off pass
horizontally (h 7.6 / 5.2 %), fail or barely pass vertically (v 19.2 /
28.1 %) — the axis OPPOSITE to the <city> sheets (feed direction vs scan
orientation not separated).

Colour (raw PS, cells unscreened): pure C/M/Y solid at c3 and up (C 0.03
%, Y c3 0.40 % marginal); cm4 c3 solid 0.11–0.22 %; stress C/M/Y/K c2
1.4–2.7 % marginal; **CMY7 MEASURED for the first time on this trip** —
c2@300 1.7–1.8 %, c6@1200 1.7–3.1 %, c3@600 2.9–3.5 % (marginal–fragile);
**CMY8** c2@300 4.4–4.6 %, c3@600 6.6 % (z), c6x12 7.3–8.0 % (fragile);
cmy7/cmy8 at 1-dot-equivalent pitch fragile–collapsed; 9–11 candidates
still unmeasurable (geometry). Tone range C 0.58, M 0.45–0.47, Y
0.41–0.44, K 0.67–0.68 — a HEALTHY Y (cf. the HP's 0.29); selectivity
C 0.38, M 0.19, Y 0.37. Plane registration vs K: medians within 26 µm,
spread up to 182–252 µm down the page (the non-affine twist, ~6 dots).

**Payload volumes from the same scan batch — both VERIFIED, sha ==
the e039 emission** (engine: the Canon — confirmed by Germano 2026-10-01,
"scan v and forward are all <city>"):

- `aa.tiff`, 1200 grey: **sheet A `c4-k-r0700@26x18` VERIFIED 122,892 B**
  (sha `930d4d07…`), 363 certificates vs K 358, 97 cpu-s.
- `ab.tiff`, 2400 grey: **sheet B `c3-k-r0700@35x24` VERIFIED 225,218 B**
  (sha `16225eb249228312f8c07c5aed5d8f2ae01801ddc186c670fd697ef107667397`),
  660 certificates vs K 656, 292 cpu-s — the first sheet B recovered.
- `ac.tiff`, **1200 grey (2 px/dot): sheet C `c2-k-r0700@53x37` VERIFIED
  532,882 B** (sha `3cb654e1…` == emission), 1,552 certificates = K
  (scan 1,270, retry 282), 3,313 cpu-s. Raw hard cell error 7.3 % (inked
  99.0 vs blank 189.1, 7,140,766 cells). The HP's copy of C (e039,
  `s.tiff`, 2400) measures 8.4 % (87.2 vs 163.5) and needed retries for
  two thirds of its certificates (scan 520 / retry 1,035): the Canon prints
  c2 cleaner, and 1200 dpi is enough for c2 on it. (VersaLink sheet D,
  r0850, 1200: 5.8 %.)
- **Sheet D `c2-k-r0850@53x37` VERIFIED 657,042 B** (sha `fe8fa0b9…` ==
  emission) — TWO captures. `ad.tiff` (1200 grey) alone stalled: 1,418
  certificates of K 1,552 after 13,354 cpu-s (scan 821, retry 566,
  `tiles.local` 10 — the local row did fire, late), +13 in its last half
  hour; raw hard cell error 4.7 % (inked 97.0 vs blank 190.9, 7,491,161
  cells). Resumed from that snapshot with `ad-2400.tiff` (2400 grey, a
  rescan of the same sheet) as a second capture: +135 certificates in
  2,659 cpu-s — **70 of them `tiles.union`** (evidence summed across the
  two captures), 55 retry, 10 scan — closed at 1,553 vs K 1,552. The union
  certificates also prove the rescan is the same physical sheet. At r0850
  the 1200 capture alone is not enough on this engine (c2 at r0700, sheet
  C, closed from 1200 alone); the second capture is the lever, as e034's
  4800 was for sheet I.
  Raw cell error of the 2400 capture at the poses the run CLOSED with:
  8.0 % (6,118,081 cells; inked 98.1 vs blank 189.3) — NOT comparable to
  the 1200's 4.7 %: 235 of its 243 placements were fitted at the coarsest
  level (2 px/cell) and the run closed before refining any (800 refine
  jobs queued); no global shift helps (best ±4 px search: 0); a cell-area
  read is worse than the centre point on both captures (1200: 4.7 → 6.9 %,
  2400: 8.0 → 8.8–10.8 %). A fair 2400 number needs refined poses.
- **Sheet J `c1-cmy8-r0700@106x74`, `ae.tiff` (4800 RGB, 8 px/dot) — DATA
  PRESENT, NOT READABLE.** holo3: survey accepted the declared pitch;
  3,193 `place` jobs, 0 words, 0 poses in 13 cpu-min. Checked by hand
  against `page000_gt.npy` on the un-truncated top-left corner: a
  high-passed FFT cross-correlation of the rendered truth (256x256 cells
  from 32 cells in) with the scan peaks at 18–30 sigma in every plane
  (the dots ARE where the truth says — not the VersaLink J's screen
  mush); per-plane pose fits on the 128x128 corner block: C corr 0.25,
  M 0.34, Y 0.29; inked vs blank 159/173, 144/162, 123/139; raw hard
  cell error **C 40.0 %, M 35.3 %, Y 38.1 %** (≈ 0.03–0.07 bit/cell vs
  the 0.7 r0700 needs). PLANES MISREGISTERED at c1 scale: per-plane
  origins y 646.5 (C) / 658.5 (M) / 650.5 (Y) px — M 1.5 dots below C,
  Y 0.5 — x within 4.5 px; px/cell 7.99–8.01. A one-pose-for-all-planes
  reader is reading M from the wrong cells. The field begins ~50–60 px
  above the first-dark-row edge (a threshold artefact; the fit is from
  the truth). The vertical colour band (greenish left, violet from ~3 in
  across the capture) seen on the HP's sheet F appears on this Canon
  sheet too; the Canon's discovery sheets showed a healthy Y page-wide —
  cause open.

Single sheets — NO promotion.

## 040.4e Sheet J from ONE isolated plane — not addressable (2026-10-01)

Question (Germano): filter the centre quarter of `ae.tiff` for C alone or
M alone and see whether THAT is addressable. The prior art is
`measure/yask/` (Y as K on sheet H), which never self-addressed: Y has no
address bit (the colour word renders states {0, 3}). C and M each carry
the word, so a single-plane read is possible in principle, and the
receiver's one-pose luma read (words.addressing_plane; place.py:654)
suffers twice on this sheet — M sits 1.5 dots below C (040.4c) and every
Y payload dot is luma noise.

Instrument, `measure/e040-plane-isolation/` (MEASUREMENT ONLY, truth in
the loop): `fit_planes.py` fits a per-plane affine truth-cell -> scan-px
from 70 FFT-correlated blocks per plane (z >= 12; **affine rms 16.8–17.3
px = 2 cells, quadratic 9.6–9.8 px — the page is non-affine at c1 scale**)
and a pixel mixing model on locally registered blocks, m0 (154, 150,
142), mC (−28, −7, −1), mM (0, −22, −12), mY (2, 1, −16), residual sd
24–30 — SNR ≈ 1 per pixel; `render_planes.py` unmixes the centre quarter
(20416x28064 px) into C, M, Y greys (160 − 40 s; the first rendering,
255(1 − s), clipped 74 % of pixels and holo3's survey cut it into 117
regions) plus luma and `C-as-rgb` / `M-as-rgb` synthetic captures;
`addressability.py` reads each tile's 100 word sites through the
receiver's 6-px aperture at the plane's pose refined per tile by truth
correlation (±48 px), thresholds over all 4,096 tile cells, and counts
errors against `words.reference_page`; `synthetic_region.py` is its null.

Verified by a fan-out (14 variants, three refuters, Haiku/Sonnet/Opus
workers after a false start on Fable): the null reads a perfect
synthetic C plane at **0 errors on all 2,106 tiles** (global pose; the
per-tile refinement on a perfect plane costs p95 13 / max 25 errors,
rms 2.5 px — its template is rotation-unaware); an independent
nearest-pixel re-read agreed to the tile (median 28 = 28, max diff 4);
the code refuter found and I fixed a per-tile-median threshold that
charged |ones − 50| on a perfect read, a sign error in the sub-pixel
correction, raw-pixel sampling where the receiver averages a 6-px
aperture, and over-claiming "the receiver accepts" for the BCH t = 13
bound (placement's soft-mismatch gates, rival gap and dust-site
references are stricter: 13 errors in one parity half ≈ 0.26 > 0.20).

Word-site errors per tile (of 100; 2,101–2,106 tiles of the quarter;
BCH bound 13):

| rendering @ geometry | aperture | min | p5 | median | p95 | ≤ 13 | ≤ 20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C @ C, local | 6 px | 13 | 22 | **29** | 37 | 1 | 53 |
| C @ C, local | 1 px | 12 | 21 | 29 | 37 | 2 | 95 |
| M @ M, local | 6 px | 9 | 21 | **29** | 36 | 1 | 77 |
| M @ M, local | 1 px | 9 | 21 | 28 | 36 | 1 | 97 |
| luma @ mean, local (the receiver's read) | 6 px | 13 | 21 | **30** | 40 | 1 | 88 |
| C @ C, global affine only | 1 px | 16 | 28 | 44 | 55 | 0 | 14 |
| Y @ Y (no word in Y) | 6 px | 29 | 40 | 48 | 56 | 0 | 0 |
| C, shuffled words | 6 px | 30 | 41 | 48 | 56 | 0 | 0 |
| C, sites read one cell right | 6 px | 18 | 27 | 34 | 42 | 0 | 2 |

**Neither C nor M is addressable stand-alone.** Isolating a plane buys 1
point of median over luma (29 vs 30): the misregistration and the Y
noise are not the limit, the dots are — inked minus blank is 43–46 grey
levels on a rendering whose per-pixel noise sd is ~45, and the 6-px
aperture does not help (29 either way), so the noise is per DOT (printed
or not), not per pixel. The one-cell-right control at 34 (not 48) shows
the ink of a dot bleeding into its neighbour cell. 1–2 tiles in 2,100
reach the BCH bound; the receiver's gates would pass fewer. The blind
receiver on the clipped C-as-rgb capture (port 8023, 8 workers): survey
117 regions, 3,440 place jobs, 0 words, 0 poses, stopped — moot under
the ceiling and not repeated on the unclipped rendering.

Not tried, and what each would cost: a rotation-aware per-tile template
(≤ 2 points of median, from the null); a soft read with the receiver's
own calibrated LLRs instead of a hard threshold (the receiver already
does this and found no word); more captures summed (the dot dropout is
print-frozen, 018.7 / F1∘F6 — a second capture of the same sheet buys
little against correlated errors).

## 040.4f Sheet G `c2-cmy8-r0700@53x37` from the Canon — 2,817 of 4,689, handed to machine 4 (2026-10-01)

The first colour certificates of the trip. `af-<city>-c2-cmy8-0700-2400.tiff`
(2400 RGB) alone, holo3 `--max-pages 1 --workers 8 --diag 8023`, survey
one region: slow start (18 certificates at 27 cpu-min, 717 tiles below
the floor), then **1,909 certificates (C 834 / M 518 / Y 557)** when
stopped by one SIGINT after ~2.4 h wall (`run-G-af.73610`, finished run
dir with report.json / events.jsonl / rasters, 2.2 GB). Resumed from that
snapshot with `af-<city>-c2-cmy8-0700-4800.tiff` (4800 RGB) as a second
capture: +908 (C 303 / M 440 / Y 165) in ~1.7 h → **2,817 of K 4,689**
(5,883 tile-streams), metadata rank 24/24, close open; stopped by one
SIGINT for the move (`run-G-af-both.75489`, finished, 11 GB with both
captures' rasters, facts.npz 116 MB). Next, on machine 4: the analyzer
ladder on the residue (default battery, `--fixed-point --max-generations
8`), export-facts, holo3 resume with both captures. The identity is
settled by the certificates themselves (AES seed = format id), not by
the metadata rank.

**CLOSED on machine 4, 2026-10-02 — sheet G VERIFIED 1,598,326 B, sha
`dde5f4f5c577f51b645dd0d45f01f950f2124c92828d1778cd96e6e74efa4372` ==
the 039.2 emission**: the first colour volume recovered on this trip and
the first from the Canon. The chain: analyzer pass 1 on the two-capture
run dir (default battery, 14 workers, interrupted at 969/2,733 keys after
23 min: +578, **65 % of residue keys certified** — sheet H's passes ran at
a few %; decode time 16,721 of 18,883 per-key seconds, the per-arm
accounting in the chat record and below) → export → holo3 resume with
SIX captures (2400, 4800, two re-placed 2400s `b`/`c`, two crosswise
2400s `q1`/`q2`): 3,395 → 3,739 in ~1.5 h (union 135, local 86, retry
86, scan 37) → pass 2 on that run dir (lean profile `--rules sum,best
--reroll-only-arms head+offset,subtract+field,subtract+field+offset
--rungs L0,L1,L2,L4`, 1.0–1.2 s/key on six lanes, 21 GB): generation 0
+1,092 of 1,811, generation 1 +520 over 681 re-attacks → **5,351, the
close VERIFIED by the pass itself** (K 4,689). Then holo3 `--complete`
over the six captures: +9 in 76,739 cpu-s (local 2 at 24,505 s, swim 2
at 27,508 s, planek 5 at 5,272 s — the rescue rows exhausted at 21
cpu-hours for nine) → **5,360 of 5,883 tile-streams**.

The residue (census on the `--complete` run dir): 523 open = **333
NEVER PRINTED** (tile rows 50–52 entire, 111 each — the bottom of the A4
page the Letter stock trimmed; reachable ceiling 5,550, so 5,360 is
96.6 % of the paper) + 190 covered (row 49, the cut edge, 91; rows
47–48 27; row 0 7; two streaks at tx 9 and 15; C 77 / M 52 / Y 61; 173
live, 17 marginal). The maximal pass (`everything+patch+pure`, wide
halo, L3f + refit knobs, cover 0.5) runs on those 190 at 29 GB and
climbing.

**End state, 2026-10-02: 5,508 of 5,550 printed tile-streams (99.2 %
of the paper, 93.6 % of the format), close VERIFIED three times
(pass 2, the maximal pass, every export).** The maximal pass
(`everything+patch+pure`, wide halo, L3f + refit knobs, cover 0.5; 14
workers, 38.9 GB peak, 2 h 05): +112, +28, +7, +1, +0 over five
generations = **148 of the 190 covered residue**, the lean pass's 65 %
per key now 78 % on the hardest keys. The 42 left are ONE BAND in the
verdict maps (`scratch/analyzer/G-af-max/verdict-{C,M,Y}.png`): tile
row 49 in all three planes — the last printed row, cut by the Letter
trim line — plus nothing else. Pass A (same profile, seed 20261002,
`open-after`): +0. The final `--complete` receiver resume
(run-G-af-complete2, 2026-10-02 12:28-12:44 on machine 4, 14 workers, all
six captures re-declared from the final-facts snapshot) replayed 5,508,
closed VERIFIED on the same sha, and minted NOTHING: 4,575 jobs, 2.6
cpu-hours, 0 certificates on every row — swim 294 jobs / 0.8 h, local
281 / 0.7 h, planek 276 / 0.2 h, retry 1,646 / 0.1 h, the pooled colour
context 12 / 0.1 h. Germano's reading of the maps stands as the
sheet's verdict: a half-printed tile has no complete reading to give,
and the only lever left would be reading row 49's surviving cells off
centre, not worth it on G. **The sheet is exhausted at 5,508 of 5,550.**
The snapshot of record is
`scratch/analyzer/G-af-final-facts/facts.npz` (5,508 certificates, the
run-G-af-complete1 snapshot + the maximal pass's ledger); the
complete2 run dir adds no certificate to it.

**The Canon's colour registration, read from the page field** (the
six-capture snapshot's `PlaneField` facts, 53x37 tiles, support
1,850/1,961; gauge F_C + F_M = 0, so the field is plane-relative, the
paper's own motion absorbed per window): C against M along the process
direction (page y) is a SINUSOID down the page, **period 93 mm,
peak-to-peak 1.58 dots** (±0.8 dot = ±34 µm), zero near 30, 115 and 220
mm, extremes near 85, 170 and 265 mm; Y against the C/M midpoint
oscillates at its own phase, 0.8 dots p-p (period 101–117 mm on a
53-row series). Lateral (page x): a constant C−M offset of +0.5 dot
along the page plus a PARABOLA across it — 0 at both edges, +0.78 dot
at the centre. Skew C vs M: 0.09 dot over the page width (0.02 mrad),
i.e. corrected by the engine. Mechanical reading: a 93 mm circumference
is a Ø 29.6 mm roller — the OPC drum of a tandem engine — and each
colour's drum carries its own eccentricity phase, so plane pairs beat
against each other at the drum period; the cross-page parabola in dx is
a scan-linearity (f-theta) difference between two laser units; the
constant lateral offset a registration residual. The same class as the
AltaLink's Y x-registration sinusoid (e033: 0.83 dot peak, ~100 mm
period). The receiver's one field per (page, plane) tracked it at 94 %
support; loudest residual per capture: the 4800 and the crosswise q2.

The trim-line row, measured (Germano asked whether the survey eats
cells there): on the 2400 capture the bottom-most covered page cell is
tile row 49, cell 59 of 64, and the ink ends 7 px = 0.9 cell = 0.07 mm
below it — the survey's support stops within one cell of the paper's
edge, nothing is eroded. Row 49 is physically cut at cell ~60, so each
of its tiles is missing its last 4 cell rows = 256 of 4,096 cells, a
6.25 % erasure on top of the channel; rows 46–48 certified 37/37 in all
three planes, row 49 **M 33, C 18, Y 18 of 37** — the plane with the
cleanest cells on this engine survives the erasure, the other two mostly
do not. At most one cell row (cell 60, ~90 % on paper, its centre just
past the ink edge) is a boundary-convention loss; the rest is paper. The
numbers on the payload pane's chips are attempt counts per tile
(diag/model.py `tile_evidence`), not cells: row 49's open tiles were
attempted 178–402 times.

Analyzer defect found on the way (owed a CLI guard, main untouched):
`--ctx-mode local5` (and `page`) with any patch-family arm crashes a
worker with `UnmixError: patch modes need a read context` — the local
context fit calls `unmix_score` without the pixel context the W8 modes
need (arms.py:996 → unmix.py:447); a killed pass writes nothing, so
the combination costs a whole pass. Local5 runs only with the
non-patch `everything` arms.

Pass-1 arm accounting (decode seconds / first-success certificates):
selected arm under `sum` 846 s / 374; `best` 901 / 34; re-roll
head+offset 1,231 / 38, subtract+field 1,482 / 40,
subtract+field+offset 1,389 / 29, subtract+affine 1,066 / 17,
global+offset 1,331 / 16, project+committed 1,590 / 13; `platt` +
`corr` 1,644 / 8; re-roll conditional+offset 1,167 / 3,
subtract+committed 1,576 / 4, raw+committed + subtract+word +
subtract+offset 2,498 / 1. Rungs: L0 2,319 s / 385, L2 damped 2,454 /
133, L1 5,680 / 27, L3 + L7 1,434 / 1. One sheet, one pass — this
print's profile, not a ruling.

## 040.4g Sheet I `c2-cmy8-r0850@53x37` — the rung confirmed, the channel G's, two certificates (2026-10-02)

Six 2400 captures (`ag-<city>-c2-cmy8-0850-{a,b,c,d,qa,qb}-2400.tiff`,
28064x20416 RGB) on machine 4, `run-I-ag.83920`, 14 workers, declared
`c2-cmy8-r0850@53x37`. Addressing was clean from the start (4,369
placements over all six captures at the 30-minute safety snapshot) and
no tile certified: all 5,550 attempted, 0 certificates after 93,725
retry jobs. The question was the rung — the address field is keyed by
the site seed, which every cmy8 row at p120 shares, so clean addressing
says nothing about r0775 vs r0850. The truth-based tool answered it
(`measure/e039-cell-truth/cell_error.py` on capture a, sha ffb75a06…,
the snapshot's own placements, 7,531,072 placed cells):

| emission | C | M | Y |
|---|---|---|---|
| I (r0850) | 15.2 % | 20.7 % | 24.6 % |
| H (r0775) | 50.1 % | 50.1 % | 49.4 % |
| G (r0700) | 50.0 % | 50.0 % | 49.4 % |

The sheet IS the r0850 print. Then the receiver minted two C
certificates from the retry row (193,234 retry jobs, 23,000 cpu-s), which
is the rung's own proof: they decrypted under the r0850 seed.

**The channel is G's.** The same instrument on G's capture that closed
(`af-…-2400`, from the G snapshot of record) reads C 14.2 / M 20.2 /
Y 25.5 %; capture b of I reads 11.4 / 18.2 / 22.9 %. Per tile, through
the receiver's 6-px aperture at the best integer pose within ±2 px
(`measure/e039-cell-truth/tile_error_map.py`, genie threshold per tile,
NEW instrument, measurement only):

| capture | C median | M | Y | tiles under 8 % (C / M / Y) |
|---|---|---|---|---|
| G af-2400 | 9.8 % | 13.6 % | 21.4 % | 399 / 2 / 0 of 1,838 |
| I ag-a-2400 | 10.2 % | 13.9 % | 21.0 % | 253 / 5 / 0 of 1,830 |
| I ag-b-2400 | 8.9 % | 12.8 % | 20.1 % | 518 / 3 / 0 of 1,811 |
| G af-4800 (aperture 11, ±4 px) | 9.1 % | 12.2 % | 20.4 % | 584 / 13 / 0 of 1,827 |

Same print, same scanner, same channel within capture-to-capture
spread; pixel statistics and centre crops agree. The rung ladder's
hard-decision thresholds at 1 % block error are 3.5 % for r0700 and
1.0 % for r0850 (docs/RUNG-LADDER-STUDY-2026-09-30.md): the receiver's
soft, context-corrected read is far better than this instrument's hard
read — G certified ~1,850 tiles from its scan and retry rows on this
channel — but the rung step is 3.5x, and the same channel at r0850
gives 2. The 4800 capture of G reads about one point better than its
2400s on this instrument, not a rung's worth.

**What was run on I, in full** (machine 4, 14 workers):

| step | run | captures | result | cpu |
|---|---|---|---|---|
| receiver | `run-I-ag.83920` | six 2400 | 2 certificates, both C, from `tiles.retry` | 15.8 h |
| analyzer lean line | `I-ag-pass1` | the same snapshot | 0 minted in 268 keys, stopped | — |
| receiver resume, both 4800s | `run-I-ag-4800.84525`, `.84563` | eight | ended before the first snapshot; the run dirs hold only argv and tree, the cause is not in the record | — |
| receiver resume, one 4800 | `run-I-ag-4800.84567` | six 2400 + `ag-…-a-4800` | +3 C (scan 1, retry 1, union 1) = **5 certificates**, metadata rank 5/24 | 10.1 h |

The `a-4800` capture surveyed cleanly on the pre-guard survey; the
second 4800 (`b-4800`) never entered a completed run. NOT RECOVERED,
5 of 4,689: every certificate cyan, the plane with the best hard read
(15 %). The maximal analyzer pass — the one that took H from 2,986 to
5,023 — was never run on I: by the owner's call, 2026-10-05 ("i don't
plan to run 0850"). With five certificates there is almost no
neighbourhood for the patch arms to learn from, which is what carried
H; that is a judgement, not a measurement.

## 040.4h Sheet H `c2-cmy8-r0775@53x37` — 1,665 of 4,689 and the survey's pitch vote at 4800 (2026-10-02/03)

Four 2400 captures (`ah-<city>-c2-cmy8-0770-{a,b,c,d}-2400.tiff`; the
file names say 0770, the row is r0775), `run-H-ah.84978` on machine 4, 14
workers: **610 certificates** (C 227 / M 167 / Y 216) in 59.8 cpu-h and
265,711 jobs — scan 73, retry 367, union 12, local 110, planek 48 —
against G's first run's 224 at one cpu-hour and 1,250 at two (one
capture there, four here). At the first reading (53 certificates, one
cpu-hour) M stood at ZERO while Y, the plane with the worst hard read,
had 18; the analyzer's lean line (`--rules sum,best --reroll-only-arms
head+offset,subtract+field,subtract+field+offset --rungs L0,L1,L2,L4`,
14 workers, Ctrl-C after 6.6 GB of ledger) took it to **1,665 (C 457 /
M 637 / Y 571)**, +1,055, M from the worst plane to the best — so the
registration sinusoid is not binding at r0775. The close needs 3,024
more of 4,689. "Inside the envelope", barely: r0775's hard threshold is
1.5–1.8 % against r0700's 3.5 % and r0850's 1.0 %.

**The two 4800 captures refused the resume** (`ah-…-{a,b}-4800`,
56128x40832): `survey of capture 0075a802e3f0 voted printed pitch 1/600
in, but the declared format row is 1/300 in`, and the same for
d03e36f701c7 when run alone — both full 4800 rasters of the right sheet
(hashes matched to the files; the 16-px cell line dominates their
centre spectra at 10–13x the median, the 8-px dot line at 3x, exactly
as G's 4800 capture that surveyed cleanly the day before). Reproduced
crop by crop with the survey's own functions: eight of nine 2048-px
crops of a-4800 vote 1/300; the one at the page centre — the ONE crop
the survey judges a whole-page component on — carries strong lines
{11.31, 8.00, 4.76} px (the lattice diagonal 16/√2, the dot pitch, a
higher diagonal) and no 16-px line above the contrast floor of 30, so
the harmonic-consistency rule finds nothing, the loudest line wins and
alone snaps: 1/600. Why the fundamental is invisible there: the vote's
contrast is peak over the probe band's median, that background rises
with pitch, and a 2048-px window holds 128 periods of 16 px — ~15
against the floor of 30, which `_measure_cell_pitch`'s own comment
predicts; only probe 8's band could lift it and that probe returns one
bin, which the diagonal takes. Sheet H's 16-px line is 1.15–1.8x its
8-px line in luma where G's is 4–5x (plane misregistration moving edge
energy from the cell rate to the dot rate is the plausible reason, not
measured). The misdeclared-dpi catch (e033.2, a raster declared at half
its dpi) is a whole-class comparison that cannot tell a c2 sheet's dot
lattice from a 2x dpi error, and it aborts the run. The vote's one
earlier failure of the same shape was e039 sheet F (a one-axis screen).

The night's workaround: `experiments/039-xerox-versalink/
decode_declared_pitch.py` (the vote abstains, RULINGS D5's fallback
takes the declared pitch). THE FIX, on branch `survey-pitch-vote`
(worktree `<worktree> commits f4aa80f0 +
330de9e5; MERGED to main 2026-10-03 at 69361a0f, the worktree and
branch dropped), after two Opus readers (design
history; the estimator) and one Opus builder: `src/holo/receiver/lib/
pitch_line.py` asks the one question a FINER vote raises — is the
DECLARED lattice on the page: a thin ring (±4 %) of the same
gradient-magnitude spectrum at the declared pitch, the loudest bin and
its perpendicular partner (±3°), the weaker over the ring median, read
on a 4096-px window (`LINE_WINDOW_PX`) — and `survey_capture` lets a
finer vote proceed when that line is present in a strict majority of
the regions that can judge (then the capture is surveyed again with the
declaration trusted, so its products are a forced capture's,
refinement included; pinned), refuses with the contrast in the message
when it is absent, and refuses a COARSER vote exactly as today (the
e033.2 direction never consults the line). `--dpi-force DPI`, a
per-scan twin of `--dpi` in the same order, makes the survey take the
declared pitch outright for that scan (`Capture.dpi_forced`, re-declared
every run, no snapshot change; the fallback warning names the cause).
Measured on the real files over the share, five 4096 windows per
capture: H's declared line 11.0–20.4, G's 19.9–25.2, empty rings (20, 24,
40 px and the lattice's own 2P, 4P) at most 4.85 → `LINE_FLOOR 7.0`,
PROVISIONAL (at 2048 the same windows read H 5.7–11.5 against a null of
3.72 over 136 rings, the thin margin that moved the window). On the
run's own component-centre crops the vote still says 1/600 and the
guard accepts. Lanes on the branch: receiver fast 1,959 passed, slow
2,233 passed (99 s), default suite 1,520, the CLI door 4; one contract
pin moved with a dated note (`DECODE_REQUEST_FIELDS` gains
`dpi_forced`, as every field addition before it). Not yet run on the
machine 4 against the real 4800 captures: that is the acceptance test.

## 040.4i Sheet H `c2-cmy8-r0775@53x37` VERIFIED 1,785,886 B — 5,024 of 5,550 (2026-10-03/05)

**Close VERIFIED byte-exact, sha256 `82a20fdced6df76ced43c5e751aa419bf8e8a8d019258c801ca16755e82ebbe7`
== the e039 emission** (offline scorer, sha-gated against the generation
manifest), first by the maximal analyzer pass's own close at 5,023, then
by the receiver (`run-H-ah-eight.36238`) at 5,024 — K 4,689, metadata
rank 24/24, one block. The second colour volume from the Canon, and the
r0775 point of its ladder. The chain, all on machine 4, 14 workers, the six
captures (four 2400, two 4800):

| step | run | certificates | gain |
|---|---|---|---|
| receiver, four 2400 | `run-H-ah.84978` | 610 | |
| analyzer lean pass 1 | `H-ah-pass1` | 1,665 | +1,055 |
| receiver, six captures (4800s added) | `run-H-ah-six.87334` | 2,048 | +383 |
| analyzer lean pass 2 | `H-ah-pass2` | 2,778 | +730 |
| receiver, `--complete` | `run-H-ah-seven.89176` | 2,828 | +50 |
| analyzer lean pass 3 | `H-ah-pass3` | 2,986 | +158 |
| analyzer maximal pass | `H-ah-max` | 5,023 | +2,037 net |
| receiver, `--complete` | `run-H-ah-eight.36238` | 5,024 | +1 |

The lean line is `--rules sum,best --reroll-only-arms
head+offset,subtract+field,subtract+field+offset --rungs L0,L1,L2,L4`;
the maximal pass is `--profile everything+patch+pure --halo-cells
C=48,M=48,Y=32 --rungs L0,L1,L2,L4,L3,L3f,L7,L7c --knob refit_rounds=2
--knob refit_max_evidence=26 --cover-fraction 0.5`, targets `open-after`
pass 3's ledger (2,564 keys). **The maximal pass:** eight generations,
+1,061 / +654 / +292 / +124 / +40 / +12 / +7 / +5 = 2,195 minted, 143,300 s
wall (39.8 h), peak RSS 64.95 GB (machine 4 has 128 GB). By rung: L0 1,147,
L2 damped@300 472 + layered@300 153, L3f 302, L1 114, L4 6, L3 1; the
patch arms carried ~95 % of it (`reroll:patch+offset` and `patch+affine`
alone and combined). **Pass 3's 158 keys were minted AGAIN by the
maximal pass** (126 in generation 1, 30 in 2, 2 in 3): `open-after`
selects generation 0's targets only, the fixed point's re-attacks pick
open keys of the run dir, where pass 3's certificates were never
folded — identical bits (export-facts deduplicated them, first wins,
no conflict), but the pass had none of them as neighbours in
generation 0 and spent re-attacks on them. Fold first (export-facts +
union-base) when a ledger's certificates should be context. My mid-run
"5,165" double-counted those 158.

**The receiver's rescue rows paid nothing at this stage:** the seventh
run (`--complete`) 115 cpu-h for 50 (local 45 cpu-h for 6, swim 43 for
25, planek 15 for 11); the eighth 55.9 cpu-h for ONE (planek), replaying
5,023 and attempting the 526 open. The analyzer's maximal pass is the
yield engine at r0775 on this engine.

**How close to the edge (pass 3's ledger, offline scorer against the
emission):** 158 certificates checked, 0 wrong; of 229,675 rung attempts
on the 2,567 keys it left open, the exit hard vector was 1–9 bits wrong
on 6, 10–99 on 369, 100–499 on 200,156, ≥ 500 on 28,974 — the LDPC
waterfall: a tile decodes or ends hundreds of bits off, so bit-flipping
(L4, 6 of 2,195) has nothing to work with; what moved those keys to zero
in the maximal pass was the read (patch arms) and certified neighbours.

**The residue: 526 of the 5,550 printed tile-streams** (rows 50–52 are
trimmed by Letter, 0 certified there): C 247 / M 208 / Y 71; row 49, the
trim line, 70; the interior 456 sits in BANDS — rows 5–7 (58), 21–29
(203), 40–42 (52) — C- and M-heavy, about 17 tile rows (~92 mm) apart,
which is the spacing of this engine's C-vs-M drum sinusoid (040.4f's
page field, 93 mm); the phase is NOT checked against the field. The
receiver's survey of the two 4800 captures ran under the
`decode_declared_pitch.py` wrapper (vote suppressed), so the merged
declared-line guard has still not met a real 4800 survey.

## 040.5 Owed (state 2026-10-05)

- The 2026-09-24 print path (raw PS by `lpr -o raw` through AirPrint, or
  `print_plane.sh` to 9100) and the media stock — unrecorded.
- A photo of the resolution block's three right-hand columns and the
  1-dot white-hole panel under the loupe (040.3).
- Sheet H VERIFIED (040.4i); its residue bands against the page
  field's C-vs-M phase (a check, not a run); the survey guard's
  acceptance test on a real 4800 capture, still owed (H's 4800 surveys
  ran under the wrapper); the analyzer's `open-after` re-attacks keys
  the named ledger already certified (040.4i) — a fold-first note in
  the README or the targets excluded from re-attack too; sheet I
  stopped at 5 certificates, the maximal pass not run (owner,
  2026-10-05; 040.4g).
- The survey's pitch vote (040.4h): `LINE_FLOOR` is one engine, one
  scanner — recalibrate the null on the next engine before trusting it;
  the coarser-side check (a 2P / 4P ring test) that would catch a 4800
  raster declared 2400 on an H-like capture, which passes the vote today
  and under the guard (the readers' 18-case emulation classified every
  case with it, not built); `_estimate_lattice` reads the lattice's
  diagonal (1,1) peaks as pitches (11.31 = 16/√2), which is what defeats
  the harmonic rule on these crops — a direction-aware estimator is the
  deeper fix; the first-pass regions of an accepted capture are refined
  at the harmonic and thrown away, one survey pass wasted per accepted
  capture.
- The Canon's F (c3-cmy8) — printed, not scanned; the one e039 print
  left on this engine.
- A `canon-iradv-c257` registry row / footing for `discover analyze`
  (the four reports carry `--printer canon-iradv-c257` as a free label).
- Analyzer: a CLI guard refusing `--ctx-mode local5|page` with any
  patch-family arm (040.4f); the `everything+patch+pure` pass's
  per-arm accounting for this sheet, as pass 1's was done.
- Receiver: the `--complete` rescue rows spent 21 cpu-hours for nine
  certificates on G, and 171 cpu-hours for 51 on H (040.4i), on
  residues the analyzer then read at 78 % and 85 % — the
  schedule's rescue band is mispriced against a fold-and-hand-back
  loop (the 2026-09-30 pricing study's line, memory
  project-rework-band-2026-09-30).
- The 1-cell-row boundary at a trim line: the survey's support stops at
  the last cell whose centre is on paper; a half-cell margin would add
  ~64 cells to each cut tile (040.4f) — measure before building.
