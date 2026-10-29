# e042 — AltaLink density probes: states per cell on the engine that prints overlaps

Date: 2026-10-06. Engine: Xerox AltaLink C8245 (office), route `lpr -o raw` as
e035 (its own footing, never merged with raw9100). Scanner of record: Canon
flatbed 2400 RGB at home. Branch `m281-screen-routes` (worktree
`<worktree> generator in
`experiments/042-altalink-cell-encodings/`, jobs in `scratch/altalink-20261006/`.

STATUS: X1 PRINTED on the AltaLink, SCANNED and READ 2026-10-06/07 (042.4). VERDICT: states per cell at c2 is NOT the AltaLink's lever — dot-mixed pairs do not read at c2 (orientation at chance), K as an eighth state adds no bits at c2 (K ↔ CM), only dropping the three-toner cell helps (the seven-state alphabet 9.0 % vs cmy8's 14.2 % at +4 % discernible bits: cmy8's CMY cell and the confusions into it); at c3 the layout ORIENTATION reads at 0.98 % (two engines now) and adds +0.35 b/cell, but c3 stays below c2 on this engine. Single sheet, context-free: NO promotion. LATER THE SAME NIGHT AND AFTER (042.5, the 2026-10-09 addendum, 042.6): the 1200×2400-request discovery sheet (600×600 effective, the fifth engine), sheet D c2-K r0850 VERIFIED from one 2400 grey capture, sheet E c1-K 0 certificates from five captures (24.3 % raw at truth-fitted poses), and the rectangular-cell reading of the printed record (2×3 cells 0.17–0.87 % on five engines; 1×2 ≥ 11 % estimated). The whole e039 catch-all (default discovery pair + A–J) and the 1200×2400-request pair are PRINTED on the AltaLink; eleven of those fourteen sheets are unscanned (042.3). Branch `m281-screen-routes` merged to main 2026-10-08/10.

## 042.0 The question

The AltaLink prints toner overlaps solid and unscreened (e031), cell=1 is dead
both polarities (e031: a single 600-dpi dot 0.060 contrast, a single white hole
0.044), and its c2-cmy8 volumes close — r0700 with the receiver (e037), r0850
with the analyzer (e036, 285 b/mm² net, the record). e036 measured the
three-toner cell's third layer as the weak state (C under M+Y reads 2–4× worse
sheet-wide). c1 is dead, so c2 is the pitch floor and the density lever is
STATES PER CELL. The M281 campaign (e041 S16/S17) showed an overlap cell's dot
LAYOUT can carry a symbol (dot-mixed two-toner cells; their orientation at
~2 % at c3). X1 asks on the AltaLink:

1. do dot-mixed pairs (A on one half of the cell, B on the other) read as
   states distinct from the SOLID overlap of the same pair, at c2 and c3;
2. does their orientation (column vs row at c2; the oriented diagonal band at
   c3) carry a bit; does POSITION (which half) read at c2;
3. is K a better eighth state than the three-toner cell (cmy7 + K), and does
   K hurt its C/M/Y neighbours;
4. controls on the same sheet: cmy8 solid, cmy7 solid, cmyw c2/c3, K c2 — and
   the per-plane registration across the page from the readout's poses.

If everything reads: c2 at 12–15 states ≈ 3.6–3.9 b/cell ≈ 500–545 raw b/mm²
against cmy8's 418; the honest expectation is that the mixed c2 cells (2-dot
bars) sit at the engine's dead-dot margin and that position is a one-dot
phase at the registration limit.

## 042.1 X1 — the density probe (built 2026-10-06)

Footing: holo's AltaLink emission (`src/holo/gen/ps.py` PSDoc: guarded
setpagedevice at 600 dpi, one composite 1-bit/component DeviceCMYK image per
band, fiducials as K imagemasks) — the construct every AltaLink sheet of
record was printed with; the one content difference is a nonzero K sample on
K cells. Geometry = S17's (fourteen 4392 × 438 bands at x 283, y 283 + 462k;
S17's five fiducials; 4 × 47 readout windows per band), so
`measure/e041_scale_readout.py`, `e041_layout_readout.py` and
`e041_band_screen.py` run unchanged. Build and verification record: filled in
when the builder and refuter return (see the band table in the generator's
docstring).

Built 2026-10-06 11:30–12:05 (Opus builder, Opus refuter; workflow). Generator
`experiments/042-altalink-cell-encodings/ps_altalink_probe.py` (452 lines) +
`ps_altalink_verify.py` (~760); holo's `PSDoc` imported, src/holo untouched; a
local packer carries the K sample. Job `scratch/altalink-20261006/X1-altalink-probe.ps`
(27,313,727 B, sha `bf4c42d333b066692ed4b1e3a37b67194992d3646fcb2749e3240fc336b74b8e`),
manifest `X1-altalink-probe.manifest.json` (verification record embedded; `engine`
xerox-altalink-c8245, `route` lpr -o raw), bands `X1-altalink-probe-bands.npz`
(10,856,477 B, sha `63689d96e6ae07885cf693a70aae1b3ad262629ea30f236bed833bb909bf3d3b`;
jobid J=63689d96). 17 objects: three K imagemask fiducial groups (S17's squares),
fourteen `put_cmyk_bitmap` composite images 4392 × 438 (K samples nonzero only on K
cells). Draw: default_rng(55000 + k), `choice` over the alphabet, then `random` for
the layout index on X5/X6/X8/X13/X14.

| band | pitch | alphabet (states) | layouts | asks |
|---|---|---|---|---|
| X1 | c2 | cmy8 solid (W,C,M,Y,CM,CY,MY,CMY) | — | production alphabet, control, per-plane poses |
| X2 | c2 | cmy7 solid | — | the erasure-row reference |
| X3 | c2 | cmy7 + K | — | K as the eighth state; K's neighbours vs X2 |
| X4 | c2 | cmy8 + K (9) | — | K vs CMY discrimination |
| X5 | c2 | cmy8 + CMx/CYx/MYx (11) | mixed: col, row | mixed pair vs solid overlap; orientation |
| X6 | c2 | as X5 | mixed: col, row, col1, row1 | + position (which half) |
| X7 | c3 | cmy8 solid | — | c3 control |
| X8 | c3 | cmy8 + mixed (11) | band−0, band+0 (S17's 5:4 oriented bands) | orientation at c3 |
| X9 | c3 | cmy7 + K | — | K at c3 |
| X10 | c2 | cmyw | — | single-toner floor, registration |
| X11 | c3 | cmyw | — | single-toner floor at c3 |
| X12 | c2 | W/K | — | the K reference, drawn in the CMYK image |
| X13 | c2 | as X5, other seed | col, row | the key band ~156 mm lower on the page |
| X14 | c2 | everything: cmy8 + K + mixed (15) | col, row | the maximal c2 alphabet, 3.9 b/cell raw |

Verification (--verify, exit 0, 15 min): gs `bitcmyk` render = the page from planes and
from states+layouts+catalogue, 0 differing dots per plane (C, M, Y, K); replay through
holo's PSDoc line-identical except the Creator line and the K-carrying hex lines of
X3/X4/X9/X12/X14 (equal once K is cleared); all 2632 windows; dot counts (solid 4/9, c2 mixed
2:2, c3 band 5:4 with one isolated B dot, K cells K only, 0 K dots outside K cells and
fiducials); geometry; two builds identical; novelty vs holo's own generated cmy8 and K pages:
no new operator, name or line form — band-sized images, nonzero K samples, K masks on a
colour page; readout dry run on a clean synthetic: 0 state error in every band (MI = raw
bits: X5/X6/X8/X13 3.46, X14 3.59 b/cell), 0 layout/orientation/position error, K poses ok.
Refuter (own parser, own composition from the formulas, own render, PSDoc replay with its own
K packer, novelty vs its own reference pages, loader checks): NOT REFUTED, nothing to fix;
"a change of content, not of construct" for the AltaLink; the colour gap mixed-vs-solid in
the synth's toner model CM 138 / CY 158 / MY 117 RGB units, K vs CMY ~18 (what X4 asks).

OPERATOR NOTES: load A4 (the job asks 595.20 × 841.92 pt behind a guarded setpagedevice;
on Letter the bottom fiducials at 286 mm and X14's foot would be cut); `lpr -o raw` as e035.
READOUT CAVEATS carried: the instrument's K plane statistic (max(R,G,B) over every cell) is
polluted by CMY cells in shared bands (X4, X14) — read K from the state confusion, not the
plane line; the layout reader has no position axis — position comes from the per-state
confusion (right orientation, wrong entry); the MIC yellow dots (0.24/mm²) land on every
band; at c2 position is a one-dot phase at the registration limit.

## 042.2 Reference reprints (the e039 counting set)

The e039 candidate set (`experiments/039-xerox-versalink/generate_set.py`,
byte-identical regeneration; counting payload byte i = (i + 0x39 + k) mod 256)
printed on the AltaLink gives the per-engine table (e039 §039.4) its fourth
column with IDENTICAL content. Priority: C (c2-K r0700), D (c2-K r0850),
G (c2-cmy8 r0700), H (r0775), I (r0850); E (c1-K) and J (c1-cmy8) only as
cheap references — cell=1 is measured dead on this engine.
Decode economy (the session's suggestion of 2026-10-06, not a decision): decode C, D and I first, because
those three alone answer the archival-row (c2-K) and ceiling (c2-cmy8 r0850) questions, and take the rest of
the set only if the table is to be complete. The ceiling was already on paper here (e036, 042.4 reading 1), so
I repeats it with the counting content. The suggestion priced each decode at "hours", which the K sheets
measured did not bear out: E took 3 min 48 s from one 2400 capture (042.5); D's 2400 capture is stamped 01:51
and its payload 01:57 (file mtimes). D is VERIFIED (addendum 2026-10-09) and I is VERIFIED (addendum 2026-10-16/17), so C is the decode owed.

## 042.4 X1 READOUT (2026-10-07 00:10)

Instruments at 2400 (`measure/e041_band_screen.py`, `e041_scale_readout.py` + `e041_layout_readout.py`,
unchanged): fit 5/5 fiducials, rotation −0.095°, residual ≤ 0.198 mm; page white 232/231/231; 2632
windows read, 136 registration fallbacks (in the mixed-pair bands X5/X6/X14 and X4). Band screen:
every band at the floor on all three HP lattices (165: 4–6, 188: 5–9, 212: 4–7 against a shuffled floor
5.8 / p98 11.3) — the AltaLink screens nothing, and the solid-cell bands sit LOWER than the M281's cmyw
bands did (15–26 there: the M281's residual 212 lpi component on its solid cells is real and absent here).

| band | pitch | alphabet | state % (loo) | MI b/cell | discernible b/mm² | layout (orientation) | plane best % C/M/Y/K |
|---|---|---|---|---|---|---|---|
| X1 | c2 | cmy8 solid | 14.16 | 2.159/3.00 | 301.2 | — | 3.5 / 4.1 / 12.8 |
| X2 | c2 | cmy7 solid | **8.99** | **2.254/2.81** | **314.4** | — | 1.9 / 2.7 / 11.9 |
| X3 | c2 | cmy7 + K | 12.49 | 2.249/3.00 | 313.7 | — | 2.7 / 3.4 / 12.5 / 4.4 |
| X4 | c2 | cmy8 + K | 21.76 | 1.987/3.17 | 277.2 | — | 6.1 / 6.0 / 14.2 / 8.6 |
| X5 | c2 | cmy8 + mixed pairs | 29.55 | 1.845/3.46 | 257.4 | **39.2 %** (MI 0.03–0.04 b) | 5.6 / 5.1 / 13.5 |
| X6 | c2 | + position | 30.31 | 1.805/3.46 | 251.9 | 62.9 % of 4 (orientation 45 %) | 5.5 / 5.7 / 13.9 |
| X7 | c3 | cmy8 solid | 2.50 | 2.809/3.00 | 174.2 | — | 0.1 / 0.5 / 6.9 |
| X8 | c3 | cmy8 + mixed pairs | 8.98 | 2.902/3.46 | 179.9 | **0.98 %** (MI 0.91–0.93 b) → **3.155 b/cell = 195.6** | 0.3 / 0.5 / 5.3 |
| X9 | c3 | cmy7 + K | **2.16** | **2.831/3.00** | **175.5** | — | 0.1 / 0.2 / 6.1 / 2.0 |
| X10 | c2 | cmyw | 2.85 | 1.776/2.00 | 247.7 | — | 1.4 / 1.5 / 9.5 |
| X11 | c3 | cmyw | 0.05 | 1.994/2.00 | 123.6 | — | 0.0 / 0.0 / 3.9 |
| X12 | c2 | K | 2.91 | 0.826/1.00 | 115.3 | — | K 1.9 |
| X13 | c2 | as X5, lower on the page | 25.03 | 2.090/3.46 | 291.6 | 35.6 % | 3.0 / 3.9 / 11.0 |
| X14 | c2 | everything (15 states) | 31.80 | 1.919/3.58 | 267.8 | 42.1 % | 6.6 / 5.9 / 12.3 / 6.4 |

Per-plane poses vs C (readout medians, dots at 4 px/dot): M −0.03…−0.8 dy, −0.2…−0.5 dx; Y −0.1…+0.2
dy, −0.3…−0.6 dx; K within 0.15 — the AltaLink holds its colour registration to ~half a dot across this
page (the M281's S17: Y − C up to 2.3 dots).

What confuses (loo confusion rows, %):
- X1 cmy8 c2: C → CY 10.3, M → MY 11.6, CM → CMY 10.6, W → Y/M/C 5.6/5.2/4.3 — a FALSE EXTRA TONER (mostly
  Y) read on single and two-toner cells, and white taking a neighbour's colour. Y is the weak plane
  (12.8 % best-threshold) on this engine too.
- X2 (seven states: cmy8 WITHOUT the three-toner cell) c2: with no CMY state to fall into, the two-toner
  cells read CM 97.4, CY 96.2, MY 95.5 % (X1: 85.5 / 91.7 / 89.3, their losses were CM → CMY 10.6, MY → CMY
  5.6, M → CMY 4.9); the singles keep their false-Y (C → CY 8.9, M → MY 10.8) and W its 4+4+3 %. So cmy8's
  excess over the seven-state alphabet (14.2 vs 9.0 %) is the CMY cell itself (92.5 % correct) plus the
  confusions INTO it — e036's third-layer finding, seen context-free. The seven-state alphabet is the
  reduced-alphabet erasure row's (not the dead pack7 family's).
- X3 cmy7 + K c2: K ↔ CM 9.0 / 9.5 % mutual, K ← CY 4.3, K ← MY 2.5 — the dark states merge at c2; K adds a
  state and no information (2.249 vs 2.254 b/cell). X4 cmy8 + K: CMY ↔ K 19.3 / 11.9, CM → K 12.5 — worse.
- X5/X6/X13/X14 c2 mixed pairs: the mixed states read ~50 % correct (CMx → CM 11.8, C 8.2, M 7.0; MYx →
  MY 18.0), their orientation at 35–39 % (chance 50), position at chance, and they pull the solid states
  down with them (C 75.8, M 69.1 %). A 2+2 dot-mixed cell is not a state on this engine at c2 either
  (the M281: 18–24 %, S17 U8–U11).
- X8 c3 mixed pairs: the ORIENTATION of the A band reads at 0.98 % (CMx 0.94, CYx 0.89, MYx 1.11; MI
  0.91–0.93 of 1 b); the mixed STATE confuses with its majority single (CMx → C 8.3, CYx → C 6.8, MYx → M
  7.1) and with its solid overlap (CMx → CM 5.4, CYx → CY 6.3, MYx → MY 13.2): the engine under-prints the
  4-dot minority toner (cell=1 dead both polarities, e031), so the blend leans to A. Still +0.35 b/cell
  over cmy8 solid (3.155 vs 2.809; 195.6 vs 174.2 b/mm²).
- X9 cmy7 + K c3: K ↔ CM 3.7 / 4.2 % mutual, everything else ≥ 96.9 %; 2.16 % at 2.831 b/cell — the best
  8-state reading at c3 on this sheet (cmy8 solid 2.50 / 2.809).
- X10 cmyw c2: W → Y/M/C 2.8/2.2/2.1 %, inks 97.9–98.9 % — the one-sided white error of every cmyw c2 print,
  here with the registration tight (|Y − C| ≈ 0.6 dot): the fifth c2 cmyw print, 2.85 %, on the line the
  M281's four drew (2.82 % at 0.49 dot). X11 cmyw c3 0.05 %. X12 c2-K: W → K 5.4 %, K 99.6 % → 2.91 %
  (the M281's S17 U14: 4.6–4.7 %).

READINGS (one print, context-free hard decisions with supervised poses and class means — the receiver reads
better: the AltaLink's c2-cmy8 r0850 volume closed at 308.6 b/mm² net per field, ABOVE this readout's 301
"discernible" — the hard-decision MI is not an upper bound for a context-aware soft receiver; CLAUDE.md's
"channel gate is not the receiver"):
1. **States per cell at c2 is not the AltaLink's density lever.** Mixed pairs fail (as on the M281), K as
   the eighth state is bit-neutral (K ↔ CM), and cmy8 + K loses. The engine's ceiling stays c2-cmy8 at
   r0850 with the receiver + analyzer (e036); the lever there is the receiver, not the alphabet.
   The rung below has no AltaLink reading: r0775 has closed on one engine, the Canon (e039 sheet H,
   1,785,886 B at q = 0.8, only with the analyzer's maximal pass; e040 §040.4i). The AltaLink's own r0775
   print (the same sheet H, from the catch-all, 042.3) is printed and unscanned. At e033's q = 0.9 the row
   would carry 2,009,841 B against r0850's 2,220,921 B (`capacity --format c2-cmy8-r0775@53x37 --paper
   A4-4mm`, 2026-10-11).

   Avenue (2026-10-11, not planned): the column-group triplet `c2-cmy8-r0850x0850x0775@53x37` (ruled
   2026-09-04 as one of the two first uneven rows; built and sim-qualified, never printed, docs/CMY8-COLUMN-GROUPS.md
   F14) carries 2,147,689 B per A4-4mm page at q = 0.9 = 298.4 b/mm² per field (`capacity`, exact; plane tier
   "needs q <= 40/61"), against r0850's 2,220,921 B (308.6). On the AltaLink it lightens only Y, the weak plane
   here too (X1: 12.8 % best-threshold). On the Canon, where r0775 closed and r0850 did not (e040), it sits
   between the two. CMY-DESIGN §3.3's 2,076,982 B is the other spelling, `r0775x0775x0850`.
2. **The one alphabet change with a measured benefit: drop the three-toner cell.** The seven-state
   alphabet (cmy8 without CMY) reads 9.0 % at c2 against cmy8's 14.2 % at +4 % discernible bits — the reduced-alphabet erasure row's second measured
   customer (after the M281's dot-mixed cmy7, S17 U2). What it would buy on the AltaLink is receiver cost
   (r0850 closing without the analyzer's maximal pass), to be measured, not density.
3. **The in-cell orientation symbol is engine-independent**: 0.98 % on the AltaLink at c3 (2.1–2.8 % on the
   M281). It adds +0.35 b/cell at c3 (195.6 b/mm²), where c3 is below c2 on this engine anyway; at c2 it does
   not read. For the M281 it is the c3 lever (S17 U7); for the AltaLink it is a confirmation.
4. **cmyw**: c2 2.85 % and c3 0.05 % on a fifth engine-print pair — the solid single-toner alphabet is the
   cross-engine floor it was built to be; its c2 white-cell errors stand at tight registration, so context,
   not registration, is their lever on this engine.
5. **Registration**: the AltaLink holds M and Y to ~0.5 dot of C across the page (the e033 Y sinusoid's
   0.83-dot peak is the known worst case); the M281's 2.3 dots is the outlier among the engines measured.

NOT PRINTED from the plan at this hour: the e039 reference set (C/D/G/H/I, E/J) and the 1200×2400 discovery pair —
the operator's day; owed or dropped by his call. (Corrected 2026-10-10 by the operator: everything on the plan WAS printed that day, `lpr -o raw` — the
twelve-page catch-all `e039-all-pages.ps` (default discovery pair + A–J) and the 1200×2400-request pair; the
1200×2400-request B/W sheet, E and D were scanned the same night (042.5), the other eleven sheets are printed and
unscanned — 042.3.)

## 042.5 The 1200×2400 B/W discovery sheet and sheet E (2026-10-07)

**1200×2400-request B/W discovery sheet** (e039's `discovery-request-1200x2400/hcal-discovery-bw-…-08b064c74c115428.ps`,
AltaLink, `lpr -o raw`, A4; scan `scratch/e041/e041-altalink-1200x2400bw-2400.tiff`, 2400 RGB, sha
`a78d2f3f6491b388f7413d48f3fb14102f254c32f65f1bf69f9e2128ffe2b19a`). `confetti.py discover analyze … --scan-dpi 2400
--printer xerox-altalink-c8245 --print-path lpr-raw --media white-office-a4-60-80gsm --scanner canon-4800 --scan-mode
color-no-auto --print-session 2026-10-06-altalink` → `status ok`, 96 s, report
`scratch/e042/discovery/hcal-report-discovery-bw-copy0000-96335cb839a5ffa3.json`. Self-report CRC-clean (two regions,
consensus ok): Xerox AltaLink C8245 Color MFP, version 3021.101, LL3, A4 595×842, default AND effective HWResolution
(600, 600) — the 1200×2400 request REFUSED (the fifth engine under the law: M281, AltaLink, VersaLink (600 only),
Canon iR-ADV, HP M681). Every authored grid collapses onto the 600-dpi dot grid: the 2-dot-equivalent cells read
1.9–3.0 % whatever grid authored them (g300-c1 1.85, g600-c2 2.95, g1200-c4 2.39, g2400-c8 2.34, g1200×2400-c4×8
2.96 %), the 3-dot-equivalent ones 0.0–0.13 % (g600-c3 0.04, g1200-c6, g2400-c12, c6×12 0.13 %); at 600: c2 vertical
1.86 % / horizontal 3.09 % / diagonal 3.31 % (fragile by worst windows), c2×3 0.55 %, c3×2 0.72 %, c4 0.01 %, c1
unmeasurable; capacity bound at 4 mm margins ~7.06 Mbit. Flags not yet checked against e031: "registration: 49
observations, max 7.1 dots displacement" and "scanner adequacy: inadequate (solid_class)". Operator's verdict: the
discovery sheet is not worth its paper here — the AltaLink's payload sheets (c2-cmy8 r0850 verified) already answer
what its tiers rank; the 1200×2400 question is closed on five engines.

**Sheet E** (e039 counting set, `c1-k-r0700@106x74`, 7,844 tiles, 2,149,148 B; scan
`scratch/e041/e041-altalink-e-2400.tiff`, 2400 grey, sha `d159f47a9e7ab6bf1be6165870b52acf570a11eefb13dc84ced2a3a9a0850221`):
the operator's holo3 run (`./confetti3.py decode … --dpi 2400 --format c1-k-r0700@106x74 --max-pages 1 --workers 8
--diag 8023 --out scratch/e042/decode-E`) at 3 min 48 s / 1,560 cpu-s: ADDRESSED 165, ATTEMPTED 1,670, FLOOR 1,437,
UNKNOWN 4,572, CERTIFIED 0. Later reading (operator): 205 addressed, 0 certified; `--run-dir` was not given, so the run's state (`facts.npz`, 0 certificates) went to a fresh `holo3-` directory in the system temp folder (`holo3-at3ueqbv`; `src/holo/receiver/cli.py:136-137`) and was not kept.

RAW ERROR AT TRUTH-FITTED POSES (`measure/e042-c1-truth/c1_tile_error.py`, new: the field placed from the emitted
bitmap — coarse robust affine from 128-cell truth blocks, a quadratic field (513 blocks, residual rms 5.9 px = 1.5
cells: the page is non-smooth at c1 scale, as e040 found on the Canon), every 64-cell tile refined by its own truth
block within ±24 px; all 7,844 tiles placed; hard decision per tile, no context; results
`experiments/042-altalink-cell-encodings/results/measurements.json`, key `c1_truth_E`): page **24.3 %** mean (genie threshold; blind 24.3 %),
median 24.2 %, p10 22.0 %, p90 26.9 %, best tile 19.7 %, **no tile below 15 %**; d' ≈ 1.46 (ink 99 / blank 136 against
paper 230 — every c1 cell reads half its neighbours). Self-checks: the pose is right (200 random tiles, 25 sub-pixel
offsets ±1 px: the best offset beats the fitted pose by 0.2–0.3 pp, i.e. selection noise); aperture 1 px (raw pixel)
23.4 %, 3 px 24.3 %, 5 px 26.4 %; the 100 word sites per tile carry exactly the format's reference word (0 mismatches
in 24,000 sites). Address words: median 24 wrong sites of 100, min 7; **52 tiles** have ≤ 13 wrong sites (the
BCH(127,50) bound) at the true pose — the receiver's 205 ADDRESSED are more than the words a hard read can decode
because holo3 addresses every tile of a window once ONE word in it has posed the window (addresses follow from the
lattice), so the two counts measure different things (inference, not instrumented). The 52 word-addressable tiles'
payload error: 22.8 % mean (20.6–27.7 %). For scale: r0700 needs a raw error of roughly ≤ 4–5 %, the ladder's
bottom rung r0547 ≲ 8–9 %; 23 % hard is 0.22 bit per cell (BSC capacity) — 558 cells/mm² × 0.22 ≈ 123 b/mm² of
channel, as much as c2-K's, but only a code near rate 0.15–0.2 could use it, far below any rung (the rung-ladder
study's verdict on c1). The AltaLink's c1 matches the other engines' (21–22 % on the VersaLink and the Canon by
the e039 instrument, a different aperture and receiver placements).

**Sheet D** (`c2-k-r0850@53x37`): scan `scratch/e041/e041-altalink-d-2400.tiff` (2400 grey, sha `9b7972dd218615cc2d234e1a4aff1316b82944d8897f0235aac7fe5abc755a13`);
operator 2026-10-07: "running easy-mode from a single 2400 dpi grey scan", as expected (D verified on the VersaLink
and the Canon). Outcome owed. The most c1 addressing in the record (Canon iR-ADV: one word; M681: no placement;
VersaLink: 0 certificates) — an address word decodes where the local word-site error is under BCH(100,23)'s t = 13
(13 %), a payload certificate at r0700 needs roughly ≤ 4–5 % raw: addressed is not certifiable. Run in progress.

## 042.6 Rectangular cells: what the printed material already says (2026-10-08)

**2×3 and 3×2 dot cells (93 cells/mm², between c2's 139.5 and c3's 62)** are candidates on every HCAL-R1 B/W
discovery sheet (`bw-k2-g600-c2x3`, `-c3x2`; worst-state hard error, context-free, the analyzer's tier numbers —
channel numbers, not receiver performance):

| engine (report) | c2 | c2 vertical-half | c2 horizontal-half | **2 wide × 3 tall** | **3 wide × 2 tall** | c3 | c4 |
|---|---|---|---|---|---|---|---|
| HP M281 (e028) | 3.48 % | 5.29 | 6.57 | **0.27** | **0.27** | 0.00 | 0.03 |
| Xerox AltaLink (e031, default request) | 2.46 | 2.12 | 2.15 | **0.38** | **0.46** | 0.09 | 0.03 |
| Xerox AltaLink (042.5, 1200×2400 request) | 2.95 | 1.86 | 3.09 | **0.55** | **0.72** | 0.04 | 0.01 |
| Canon iR-ADV (e040, default / 1200×2400) | 2.48 / 2.11 | 3.03 / 2.64 | 4.64 / 4.39 | **0.26 / 0.21** | **0.57 / 0.56** | 0.05 / 0.06 | 0.00 |
| HP M681 (e039) | 4.82 | 5.66 | 4.42 | **0.72** | **0.87** | 0.10 | 0.03 |
| Xerox VersaLink, URF raster (e039) | 1.86 | 0.38 | 0.76 | **0.17** | **0.26** | 0.00 | 0.00 |

The rectangle reads 5–10× better than c2 and 3–10× worse than c3, everywhere; tall (2 wide × 3 tall) beats wide
on four of five engines (the M281 ties), in line with the half-cell shapes (vertical ink bars print better than
horizontal ones on most engines — development anisotropy). For K at the ladder's top (r0850 ≈ 0.73 net bit per
cell on this format, from `capacity` on c2/c3-K) a 2×3 row would carry ≈ 68 b/mm² net: +50 % over c3-K r0850
(45), −18 % against c2-K r0700 (83), at a raw error 5–10× below c2's (ESTIMATE; no rectangular row exists).

**1×2 and 2×1 dot cells (279 cells/mm²) were never printed.** ESTIMATED from the AltaLink's c1 page (sheet E,
truth-fitted poses, `measure/e042-c1-truth/c1_tile_error.py --emulate`: aligned cell groups whose truth is uniform
are read as one cell, per-tile genie threshold): 1 wide × 2 tall **11.3 %**, 2 wide × 1 tall **11.1 %** (c1 itself
24.3 %). The same estimate puts c2 (uniform 2×2 groups) at 1.1 % where the engine's real c2 reads 2.5–3.0 % — the
estimate is OPTIMISTIC (a uniform group in a random c1 field has half-inked neighbours, a real grid's neighbours are
whole cells), so a real 1×2 grid reads ≥ 11 %: past the bottom rung (r0547 needs ≲ 8–9 %), at best break-even with
c2 with a rate-0.4 code that does not exist (the rung-ladder study's c1 verdict, extended).
(Corrected 2026-10-17: r0547's measured hard p@1 % is 6.5 %, not ≲ 8–9 % (RUNG-LADDER-STUDY §2); and a
rate-0.4 code does exist in simulation — the rung-ladder confirm's k 1664 winner, p@1 % 11.1 %, unminted and not
loadable by production (§7.4). The verdict "past the bottom rung, at best break-even" stands.)

Orthogonality: in the FORMAT, cell geometry is a separate axis from the alphabet (k / cmy / cmy7 / cmy8), but the
format has ONE pitch today (a single reduced rational, square cells): rectangular cells need a per-axis pitch in
the identity grammar, the generator's geometry, the receiver's survey and pitch vote, placement and sampling. In the
CHANNEL they couple: development anisotropy and per-plane misregistration are axis-dependent (the M281's Y − C is
mostly along y: S17 U12 dy −2.33, dx +0.30 dots), so the best orientation can differ between K and colour.

Colour at 2×3 has never been printed. It is untested and worth one band. The session (2026-10-06/08; an assistant suggestion, not an owner ruling) proposed it as a robustness tier for worn or cut sheets, 1200-dpi scanners and the M281's colour, the one gap in the pitch ladder between "c3 works" and "c2 is registration-limited". On the M281 a tall cell would give margin along y, the axis where Y − C drifts (above). ESTIMATES, raw bits at 93 cells/mm² with zero errors: dot-mixed cmy7 = 93 × log2 7 ≈ 261 b/mm² (the 2+2-dot mixed cells that fail at c2 would become 3+3), and cmy (W/C/M/Y, 2 b/cell) ≈ 186. Nothing has been built. The cost is the format's single square pitch (above).

Follow-ups, not commissioned (2026-10-08): (a) the same `--emulate` 1×2 / 2×1 estimate on the other engines' c1-K
prints already scanned, no paper: the VersaLink (`scratch/<city>/i-c1-k-2400dpi[-grey].tiff`) and the Canon
(`v.tiff`, `--rot180`) at 2400; the M681's (`t.tiff`) is a 4800 capture with no placement, and the instrument assumes
2400 (`c1_tile_error.py:136`), so that one needs a scan-dpi argument first; (b) a real 2×3 band on the next probe
sheet in K, cmy and dot-mixed (hypothesis: a 3+3 dot-mixed cell might read where 2+2 did not, 042.4), to test the
rectangle beyond the discovery sheets' channel numbers.

## 042.3 Prints and scans

| id | when | what | route | notes |
|---|---|---|---|---|
| 042.1p | 2026-10-06 (office) | X1 | AltaLink C8245, `lpr -o raw`, A4 (operator; job sha `bf4c42d3…`) | operator 2026-10-10: `lpr -o raw`, no error reported |
| 042.1s | 2026-10-06 23:25 | scan of X1 | Canon 2400 RGB | `scratch/e041/e041-x01-2400.tiff` (1,718,864,112 B) sha `6e138436846f03474ecf02a5da1678133880c63022c9c5e059c33e4972b798e2`; readouts `scratch/e042/scale/`, `scratch/e042/band-screen/` (logs `scale-readout-X1.log`, `band-screen-X1.log`) |
| 042.2p | 2026-10-06 (office) | the twelve-page catch-all `scratch/versalink-20260916/e039-all-pages.ps` (sha `dab6e344…`, e039 §039.2a: the DEFAULT-request discovery pair, bw + color, then volumes A–J; per-page source shas in its `%` comments) and the 1200×2400-REQUEST discovery pair (`discovery-request-1200x2400/`; its B/W sheet is the one scanned in 042.5) | AltaLink, `lpr -o raw`, A4 (operator) | operator 2026-10-10: "all sheets were printed, just not all scanned yet" — scanned so far: the 1200×2400-request B/W sheet, E, D (042.2s, 042.5); printed and UNSCANNED: the default discovery pair, the 1200×2400-request colour sheet, A/B/C/F/G/H/J (ten sheets; I scanned 2026-10-16, next row) |
| 042.2s-I | 2026-10-16 11:33–12:04 | four scans of sheet I, the sheet re-laid between them | Canon 2400 RGB | `scratch2/e042-canon-i-6.10-2400-{a,b,c,d}.tiff` (machine 4), shas in the 2026-10-16/17 addendum; VERIFIED there |
| 042.2s | 2026-10-07 00:02 / 00:06 | scans of the 1200×2400 B/W sheet and of sheet E | Canon 2400 (RGB / grey) | shas in 042.5 |

## Addendum 2026-10-09 — sheet D VERIFIED; sheet E's 4800 run

**Sheet D** (042.5, "Outcome owed"): VERIFIED. The decode's payload `scratch/e042/decode-D` (657,042 B, 2026-10-07 01:57)
is byte-identical to the e039 set's emitted `payload-counting.bin` for D: both sha256
`fe8fa0b936c960fdf33647058704bb0aa1a63ef7e7ea070328be3ecb06b422d4` (decode-D hashed 2026-10-09; the emission's sha is
e039's, `experiments/039-xerox-versalink-candidate-set.md`).

**Sheet E, four 4800 grey captures** (2,291,818,718 B each, under `scratch/e041/`; sha256 from the raw-hash pass of 2026-10-09 (sha256 over the retained evidence)):

| capture | mtime | sha256 |
|---|---|---|
| `e041-altalink-e-4800-a.tiff` | 2026-10-07 20:23 | `dbf9a14b8f561a77c0f7962a8d88e3f546a0999047d40c6590ccd47390d82ad5` |
| `e041-altalink-e-4800-b.tiff` | 2026-10-07 20:32 | `67acf939b67961932edb220f31a5698cc0e9c882cf64b3544bf6a16a5d215f7f` |
| `e041-altalink-e-4800-c.tiff` | 2026-10-07 21:43 | `a9c802cc27a9e0ab56901c6358915321f14d9b7c7cb6bacbb285c6c0d212ddd0` |
| `e041-altalink-e-4800-d.tiff` | 2026-10-07 21:55 | `c54e74e63b9ec1e06e5c79346c2a5287e792448931143ab702d8dc2c74689e5f` |

Run `scratch/e042/E-run.37117` (`./confetti3.py decode` over `e041-altalink-e-2400.tiff` + the four 4800s, `--format
c1-k-r0700@106x74 --max-pages 1 --workers 8`; report 2026-10-08 04:51): **0 certificates**, close open; tiles
UNKNOWN 702 · ADDRESSED 58 · FLOOR 1,327 · ATTEMPTED 5,757 · CERTIFIED 0; cpu 157,992.8 s; 0 contradictions.
The owner made this run expecting nothing (his words, 2026-10-06: "I don't expect any form of success with E. Still want to try"). The stop rule given at launch: watch CERTIFIED on the diag, since one certificate could start a cascade, and stop if ADDRESSED climbs while CERTIFIED stays 0 after the first full pass. The run did NOT exhaust its frontier. At RunDone it still held 19,638 queued `place` jobs with none in flight (`report.json`; `argv` 2026-10-07 22:38, report 04:51, ≈ 6 h 13 min wall), and that is how an orderly operator stop ends: the loop leaves only with nothing in flight, and `_fill` keeps seating jobs while the frontier is non-empty (`src/holo/receiver/engine.py:187-205`, `:601-602`), so an exhausted run ends with 0 queued. Who stopped it, and whether the rule decided it, is not recorded.

OWED, not run: the truth-fitted raw error on the four 4800 captures. 042.5's 24.3 % comes from the 2400 alone
(`scratch/e042/c1-truth-E*/summary.json`: scan `e041-altalink-e-2400.tiff`, 4.0 px per cell). The instrument assumes a
2400 capture (`c1_tile_error.py:136`, nominal pitch from `scan_dpi=2400.0`; search radius and aperture in scan px),
so it needs a scan-dpi argument first. Offered 2026-10-07 during the E run ("in minutes", an estimate) and not taken
up. At 4 px per cell, alignment is the likeliest lever, so a materially lower raw error at 4800 is the one cheap
result that could reopen "c1 fails on a fourth engine" (a judgement, not measured).

## Addendum 2026-10-16/17 — sheet I `c2-cmy8-r0850@53x37` READ TO 5,878/5,883, CLOSE VERIFIED (machine 4)

**The AltaLink's print of the e039 set's I (1,973,446 B, q 0.8, K 4,689 of 5,883) closes with the
receiver alone from four 2400 captures — VERIFIED byte-exact, sha256
`0d248fb3404083ad2e67f3830d2190fb3ca6d24f3ae9c31e0c1681996ac3c2fd` == the e039 emission (§039.2a's
table, row I) — and reads to 99.9 % with the analyzer. The same bytes on the Canon iR-ADV gave 5
certificates from seven captures (e040 §040.4g). The second r0850 sheet on this engine after e033/e036's H.**

**Captures** (2026-10-16 11:33–12:04, Canon 2400 RGB, 28064×20416, 1,718,864,112 B each,
`scratch2/e042-canon-i-6.10-2400-{a,b,c,d}.tiff`; the sheet re-laid between captures — a sideways shift,
a 180° turn, a shift with a slight tilt; each capture is the full platen, so the lay of each is
recoverable from the scan itself, not logged):

| capture | sha256 |
|---|---|
| a | `1c09caf9b3b4aa7c53c0ba4892ba56e3097432c9eefcb3b577f347bb8ef75028` |
| b | `cebf7b50ed93fd31089a99bd33d2df1efba2879bc1c7f40fbacf7348e40f304a` |
| c | `41e1515ec46e5b1e9bd46734a9d0719f402812f583d8ada55657e40197194991` |
| d | `d8df72ba7b754952bda5fea28cd3e4cdefc8bceb17ce8e0f8c8ebcd0d25cb23e` |

**The chain** (machine 4, 14 workers, tree `2fa8fd5c`, `--format c2-cmy8-r0850@53x37 --max-pages 1`; run
dirs and logs under `scratch2/e042/`; every analyzer pass blind, `--targets residue`; the analyzer
bases: A1 over the receiver's `resume1.68258`, A2 over the A1 export's union, A3 over A2's stop-door
facts, A4 over the receiver's `I-M2/rundir.75784`):

| step | run | wall | cpu-s | +certs (C / M / Y) | total | close |
|---|---|---|---|---|---|---|
| receiver, no `--complete`, stopped by hand | `I-M1/rundir.66101` | 4 h 25 m | 195,827 | 4,633 (1,669 / 1,944 / 1,020) | 4,633 | open, 56 short |
| receiver `--resume` | `I-M1/resume1.68258` | 49 m | 35,889 | +59 (21 / 5 / 33) | 4,692 | **VERIFIED** at K+3 |
| analyzer lean (`--rules sum,best --reroll-only-arms head+offset,subtract+field,subtract+field+offset --rungs L0,L1,L2,L4`, 8 generations) | `I-A1` | 35 m | — | +395 (52 / 7 / 336) | 5,087 | verified |
| analyzer default battery, stopped at 315/796 (yield 10 in 12 min) | `I-A2` | 12 m | — | +10 (4 / 0 / 6) | 5,097 | verified |
| analyzer maximal (`everything+patch+pure`, halo 48/48/32, rungs L0–L7c, refit 2/26, cover 0.5, fixed point) | `I-A3` | 1 h 44 m | — | +778 (211 / 5 / 562) | 5,875 | verified |
| receiver `--resume --complete` over the A3 export | `I-M2/rundir.75784` | 9 m | 3,104 | 0 (8 attempted) | 5,875 | VERIFIED |
| analyzer maximal again, seed 20261017, over M2's facts (the re-target finding below) | `I-A4` | 5 m | — | +3 (3 / 0 / 0) | **5,878** | verified |

Receiver cpu 234,820 s (65 cpu-h) for 4,692; analyzer 2 h 36 m wall at 14 workers for 1,186 — every
analyzer certificate a redundant symbol: the A3 close's fountain consistency 5,875 symbols, 1,186
redundant, 0 inconsistent, proven; the envelope sha on every close.

**Per plane at the end: C 1,960 / M 1,961 / Y 1,957 of 1,961** — M complete. The 5 open keys are one
run on the right-hand edge column, tx 36, rows 23–28: C (23,36) and Y (23/26/27/28, 36); M certified
on all of them; 67–196 production attempts each, all failed; inside Y's dead band (below).

**The receiver's profile** (first run, 30-min snapshots): 2,187 at 0:30, 3,671 at 1:00, 4,010 at 1:30,
then +60–140 per half hour to 4,527 at 4:00 — the cheap rows (scan 2,272 + union 1,247 + retry 104 =
3,623) in the first 90 min, then `tiles.local` 159,585 cpu-s for 642 (249 cpu-s each) and planek
6,359 for 368. The resume's +59 came from planek 30 / scan 17 / union 9 / local 3 at 35,889 cpu-s —
the close was 56 symbols away and planek/swim still held 2,418 / 2,843 queued; the receiver's own
reach past 4,692 is UNMEASURED (it stopped at the close; e036's receiver stalled at 4,883 on H).
Two D1 address contradictions (capture a, tiles 16,29 and 17,29, word vs chain, 1.3 cells apart in y;
diagnostic, nothing quarantined, payload unaffected).

**What the analyzer read that the receiver could not: Y.** Of the 1,191 keys open at the close, Y 572
/ C 219 / M 5 (the receiver's Y 1,020 of 1,961 = 52 %, beside H's 1,013 at r0850 and e033-I's 1,119 at r0700); of
the analyzer's 1,186, Y 904. Y's bands at the close (census over covered columns): DEAD tx 0, 12,
31–36; marginal 9–15, 19–20, 25, 27–30 — two bands ~115 mm apart (tile pitch 5.42 mm), e033 §033.4's
Y-plane x-registration sinusoid again; the page field reads Y 0.64 ± 1.62 dots against C/M's
0.21 ± 1.22, support 100 % (the field pane's Y arrows swing across the page). C's marginal columns
12, 19–21, 36 (e036's third-layer C). Band phase NOT checked against the field. The maximal pass's
yield was the patch family: `patch+offset` alone 338 of 778 ("only this arm"), `patch+affine` 33,
L0 683 / L2 59 / L3f 20 / L1 16; the lean pass's 395 were L0 265 / L2 103 / L1 26 at
`subtract+offset` 141 / `global+offset` 86 / `subtract+field` 52 — the default battery's extra rules
and rungs (platt, corr, L3, L7) bought 10 in 315 keys, the patch arms 778 in 786.

**The per-plane record at c2 cmy8 on this engine, receiver only, four captures:**

| sheet, print day | rung | q | C | M | Y |
|---|---|---|---|---|---|
| H (e036's stall snapshot, 2026-09-01 run) | r0850 | 0.9 | 1,734 | 1,944 | 1,013 |
| I of this set (this run, at the hand stop) | r0850 | 0.8 | 1,669 | 1,944 | 1,020 |

Two prints, two days (08-18 and 10-06), two capture sets, the same split within 4 % — M at 1,944
on both (17 short of complete both times, likely the same edge tiles; not checked), C 4 % under, Y at
52 %. e046's premise (C one rung under M, Y two) rests on H alone in its table; this is its second
row, same engine, same answer.

**Rulings read off it (single sheet, NO promotion):**
- r0850 closes on the AltaLink with the receiver alone at q 0.8 from four 2400 captures; it did not
  on the Canon from seven (e040: "r0850 not at all on this channel" — the Canon's channel, not the
  rung). The emission is byte-identical, so the engine is the only variable left.
- At q 0.9 (K 5,277, H's) the sheet would also have closed WITH the analyzer (5,878 ≥ 5,277 by 601);
  the receiver alone is unmeasured there (e036's H stalled at 4,883 on seven captures).
- The receiver reaches the close; the analyzer's maximal pass is the yield engine for the page's
  last 20 %, as on the Canon's H (e040 §040.4i) — here in 1 h 44 m, not 40 h, over 786 keys and
  four captures. The hand-back run minted nothing (8 attempted, 9 min): nothing left for planek/swim;
  the pass after it minted 3 — not the seed: the re-target set misses cross-stream neighbours (below).
- The lean pass before the maximal one is cheap (35 min, +395) and keeps the maximal pass's targets
  down; the default battery in between was not worth its 12 min here.

**The re-seeded maximal pass (A4) is the surprising row, and the seed is not what it measured.** A3
had reached its fixed point (generation 7 re-attacked nothing) with the 8 keys open; the receiver's
hand-back minted nothing; then the SAME configuration over the receiver's refreshed facts, differing
only in `--seed` (which picks the calibration fold split, `fixedpoint.py:316`), certified 3 of the 4 C
keys in generations 0–1, at hard rungs (L2:damped 2, L3f 1, `patch+affine`). The ledgers say why:

| key | A3's last attempt | known C cells in the frame | sibling-known cells | A4's attempt | known C | sibling-known | verdict |
|---|---|---|---|---|---|---|---|
| (26,36,C) | gen 1 | 10,959 | 503 | gen 0 | 10,959 | 10,958 | certified L2 |
| (28,36,C) | gen 1 | 10,961 | 503 | gen 0 | 10,961 | 10,960 | certified L3f |
| (27,36,C) | gen 2 | 7,975 | 503 | gen 1 | 13,945 | 7,974 | certified L2 |
| (23,36,C) | gen 2 | 13,945 | 503 | gen 0 | 13,945 | 13,944 | open |

The C-plane halo was IDENTICAL between the two attempts of (26,36) and (28,36); what changed is the
frame's sibling cells (`frame.py:448`: a cell counts as a sibling regressor only when BOTH other
planes are known), 503 (furniture only) → ~11,000. The M of these tiles was minted by A3 itself in
generations 0–1 and the Y of their NEIGHBOURS in generations 5–6 — after the C keys' last re-attack.
DESIGN §6b re-targets a key when one of its 8 same-stream neighbours or its own tile's other streams
certifies (`fixedpoint._retarget`); a neighbour's certificate in ANOTHER stream re-targets nothing,
although it is exactly what fills the subtract/patch arms' regressors for C under M+Y (e036's
third-layer C). So A3's "fixed point" was a fixed point of its trigger set, not of the evidence: the
keys would have certified inside A3 had the cross-stream neighbours re-targeted them. This is the
mechanism behind e040 §040.4i's "fold first" and e037's fold-and-hand-back gains, now named. Y gained
nothing from the re-pass (its frames were already full at A3's generation 7: 8,313 known, 8,312
siblings, and failed again) — the 4 open Y keys are a true residue of this capture set.
OWED, analyzer line: widen `_retarget` to the 8-neighbourhood across all streams (or re-target on any
certificate that changes a key's regressor count), then re-measure the fixed point on this base; a
same-seed A/B over `I-M2/rundir.75784` (seed 20260903) separates the seed from the fold in 5 min and
is NOT run.

**Owed:** the truth-fitted raw cell error of this print on the same instrument as the Canon's I
(`measure/e039-cell-truth/cell_error.py`; the Canon read 15/21/25 % — the number that would put the
engine difference in channel terms); the colour discovery sheet of 10-06 is still unscanned (no
per-plane channel baseline for this print day); the 17 M tiles' identity against H's.
