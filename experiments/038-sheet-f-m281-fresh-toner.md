# e038 — sheet F reprinted on the M281 with fresh toner: NOT recovered, and why

Date: 2026-09-13 (prints, first scan, first decode) / 2026-09-14 (analyzer,
resume, measurements). Engine: HP CLJ Pro M281fdw `<host>`
(<ip>; its hostname had reverted to the factory `<host>` and was
restored by the operator the same day). Scanner: Canon flatbed, 2400 dpi RGB.
Tree: first decode on `83564aed` (main before the 09-13 cleanup), everything
after on `e25f352b`. Instruments and this log on branch `stripe-f-analysis`
(worktree `<worktree>

STATUS: **NOT RECOVERED** — 941 of 2,520 tile-streams after receiver +
analyzer + resume (C 839/840, M 61, Y 31), close open, 1,309 symbols short.
Single sheet, one capture decoded, provisional receiver: nothing promoted.

**Identity — read this before citing any number.** The file printed is
e033's sheet F PostScript, `scratch/xerox-v1-20260818/F-c3-cmy8v1-q090-4mm/
page000.ps` (sha `3c02f797e26d16cc…`, matches its manifest), identity
`L:c3-cmy8-p120-v1@2240x1536` (c3, CMY8 pooled -v1, rungs C/M r0550, Y r0547,
35x24 = 840 tiles, q 0.9, K/N 0.893, counting payload 586,932 B sha
`0da0afe445b9b0fa…`, field borders 6.27/7.45 mm). e033 printed that file on
the AltaLink; that sheet is STILL UNSCANNED. The sheets here are three NEW
physical copies printed on the M281 — the same bits, a different engine.
Never combine a capture of these with a capture of the AltaLink sheet, and
never combine the three M281 copies with each other in one state (the
sheet-J rule: one physical sheet per state).

## 038.0 Why F, and why now

Toner replaced on the M281 on 2026-09-13: the C, M and Y cartridges (K not
replaced). The M281's whole colour record was in the weak-Y epoch (e017,
e028, e030, e031, e032's M281 sheet). Ruling, Germano 2026-09-14: **every
result impacted by the weak-Y epoch is invalidated, overprint-behaviour
verdicts included; re-measure.** F was chosen as the first fresh-toner sheet
because it is the only page-size c3 CMY8 file on disk with a live outer
code (the e030 c3 file is a -v0 row: readable through the fossil route,
never to be generated again).

## 038.1 Prints and scans

| run | date | action | details |
|---|---|---|---|
| 038.0p | 2026-09-13 | print 1 | `scripts/print_plane.sh …/F-c3-cmy8v1-q090-4mm/page000.ps` (raw 9100; the printer had to be addressed as `<host>` until renamed). Media: the operator's usual white 90 g/m² A4 stock (as e028), same tray |
| 038.0s | 2026-09-13 15:52 | scan of print 1 | Canon 2400 RGB → `scratch/hp-canon-13.9-F-c3-cmy8-v1-2400dpi-a.tiff` (1.72 GB) sha `a6bd836b7d4f9ee3…` |
| 038.1p, 038.2p | 2026-09-13 | prints 2 and 3 | same file, same path (after the printer's diagnostic pages, which looked flawless by eye); the stripe of §038.3 is at the same place on all three |
| 038.2s | 2026-09-13 18:26 | scan of print 3 | `scratch/hp-canon-13.9-F-c3-cmy8-v1-2400dpi-3rdpagr.tiff` sha `89d44e64c5070df7…` — NOT decoded (operator expectation: identical to print 1 by eye, the band included) |
| (print 2) | | | not scanned |

## 038.2 Decode chain (print 1, one capture)

1. **holo3** (`hp-F-20260913.96911`): `./confetti3.py decode <tiff-a> --dpi 2400
   --format L:c3-cmy8-p120-v1@2240x1536 --max-pages 1 --workers 8 --diag 8023`.
   Calibration 4/4; the page addressed everywhere (1,632 tile-streams
   attempted). **931 certified: C 839 / M 61 / Y 31**; metadata rank 24/24;
   close open, 1,319 short of K = 2,250. Page field: C 0.35 ± 1.80, M 0.34 ±
   1.76, Y 1.08 ± 2.64 dots (median ± uncertainty), Y's residual 2.6x
   noise. D1 fired once (tile 32,21; quarantined nothing).
2. **analyzer** (`scratch/analyzer/F1-pass1`, 6.1 h): profile
   `everything+patch+pure` with all 21 built arms spelled, rungs
   `L0,L1,L2,L4,L3,L3f,L7,L7c`, refit knobs, fixed point (3 generations).
   **+10 tile-streams** (first-success: subtract+offset 3, patch+offset 2,
   patch+affine 2, global+offset 1, head+offset 1, subtract+affine 1; the
   re-roll paid for 4). Census and controls were NOT run.
3. **export-facts** → `scratch/analyzer/F1-export/facts.npz`: 931 + 10 = 941,
   fountain consistency 0 inconsistent.
4. **holo3 resume** (`hp-F-20260914-resume.27132`, same capture, tree
   `e25f352b`): replayed 941, **+0**; tiles.local / planek / swim each ran
   9,252 jobs (11.0 / 8.5 / 13.7 k cpu-s) and minted nothing; 10.4 cpu-h
   in all. NOT RECOVERED, 941, 1,309 short.

Baseline against the old toner (e030, the c3-cmy8 -v0 sheet at q 0.5, one
4800 capture): C 620 → 839, M 43 → 61, Y 0 → 31.

## 038.3 Measurements — the stripe, the screen, the ceiling

Instruments (branch `stripe-f-analysis`, `measure/stripe_f*.py`), all
read-only over the run dir and the emitted truth (the analyzer's truth
loader and the GT bitmap unpack agree bit for bit; the placement mapping
validated first on certified C tiles, corr(C bit, R) = −0.92). Figures and
numbers in `scratch/hp-F-20260913-stripe/`.

**(a) The whole page is re-screened.** Every tile's 2-D spectrum has
discrete peaks: R and G at 3.62 dots ±14°, B at 2.83 dots, 45° — e002's
device screens (165 lpi ±14°, 212 lpi 45°). The composite DeviceCMYK path
is rendered contone and re-screened on this engine WITH FRESH TONER, so the
layer-0 re-screen is engine behaviour and survives the toner ruling.

**(b) Where M and Y certified: one band.** All 31 fully-certified tiles are
in tile column 12. At 1 mm resolution the band is 4–5 mm wide, at
108–113 mm from the paper's left edge (paper centre 105 mm), 4 mm ramp on
its left, sharper on its right; immediately left of it (96–100 mm) M and Y
are WORSE than baseline; a separate 3 mm C-only dip at 119–121 mm. Same
place on all three prints; the printer's own diagnostic pages show
nothing by eye.

**(c) What differs in the band** (single-ink vs white cells in the plane's
sensitive channel, each plane at its own best registration):

| plane | d' band / outside | white level | ink level | screen peak/ring |
|---|---|---|---|---|
| C in R | 4.9 / 4.8 | 0.664 / 0.660 | 0.289 / 0.303 | 204 / 260–370 |
| M in G | 4.0 / 3.1 | 0.621 / 0.603 | 0.322 / 0.352 | 120 / 450–630 |
| Y in B | 3.0 / 2.0 | 0.634 / 0.590 | 0.416 / 0.444 | 585 / 1000–1550 |

Registration is not the discriminator (per-plane offsets differ by a
fraction of a dot; the correlation at the best offset is still worse
outside). In the band the screen clusters fill into solid cells and the
whites stay clean; outside, M and Y print as partial clusters with fogged
whites. C renders like the band everywhere. Crosstalk: cyan into G −0.09,
magenta into B −0.17. Cause: a shared engine element (same x for all three
planes, so not the cartridges); which one is not decidable optically.

**(d) The receiver-side ceiling** — supervised cell classifiers with the
emitted truth, trained on even tile rows, tested on odd, all cell states:

| classifier, outside the band | M err (cap ≤) | Y err (cap ≤) |
|---|---|---|
| production aperture, one threshold | 21.3 % | 32.7 % |
| 3-channel QDA | 20.9 % | 26.2 % |
| ridge-LDA, 3x3-cell RGB patch | 15.9 % | 20.1 % |
| + C plane's neighbourhood (blind-available) | 15.5 % (0.37 bit) | 19.7 % (0.28) |
| + screen-phase features / per-phase branches | 15.5 % | 19.7 % |
| 9x9-cell window | 15.9 % | 20.2 % |
| 9x9 + GENIE (every neighbour's true state, all planes) | 12.0 % (0.47) | 14.1 % (0.41) |
| one-hidden-layer network, any context | never below the LDA | |
| rung required | 0.55 | 0.547 |
| inside the band, same genie | 6.4 % (0.66) | 7.2 % (0.63) |

The genie row bounds every HMM / MRF / turbo / network scheme (they can at
best supply the neighbours' states). Outside the band the M and Y cells
carry less than their rungs even then; the threshold error is flat across
the cell's phase against the screen (the moiré is not the loss); the wide
window adds nothing over 3x3. The loss is print-frozen. Consistent with
the resume: planek/swim +0.

## 038.4 Readings (single sheet, provisional receiver)

- The M281's fresh-toner colour channel: C at 98–100 % on a re-screened c3
  composite; M and Y unreadable at r0550-class rungs except where the
  engine renders them at high contrast. Not a toner fact any more.
- On cmy7 (asked from another line): the failure here is NOT concentrated
  on triple cells — outside the band single-ink M cells are at 8.6 %,
  M under C 17.5 %, under both 23 %; Y alone 15 %, under C 21 %, both 26 %.
  Every state fails the rate; a triple-free alphabet would not change it,
  and cmy7's joint symbol has no per-plane fallback to keep C's 839.
- Levers: (1) engine rendering contrast — PJL variable reconnaissance
  (query prepared, unsent: printer unresponsive on 09-14, needs a power
  cycle; `scratch/m281-pjl-20260914/query.pjl`, send from the operator's
  shell, the app sandbox cannot reach the LAN), then a `sethalftone` /
  `setscreen` sheet (never tried on either engine); (2) format — lighter
  M/Y rungs: outside the band Y fits an r0400-class rung and M about r0450
  with C at r0550 or better = the column-group pool's design case
  (docs/CMY8-COLUMN-GROUPS.md, built, never printed).

## 038.5 Owed

- The e028 colour discovery sheet re-take on fresh toner (the pre-registered
  probe; re-takes Y density 0.0110 → ?).
- PJL reconnaissance, then the `sethalftone` sheet (one variable each).
- NOT owed: the AltaLink F sheet of e033 stays unscanned by ruling (Germano
  2026-09-14) — with H and I read to 100 % and J's confetti close, another
  AltaLink CMY8 sheet is redundant. Any cmy8-vs-cmy7 question on that
  engine is answered by the H/I/J record and e032.
- Registry text for `hp-m281` ("color: NOT usable: CMY triple toxic") is a
  weak-Y-epoch verdict; its amendment is the user's.

## Artefacts

`scratch/hp-F-20260913.96911/` (first run: facts.npz, report.json, events,
panes), `scratch/analyzer/F1-pass1/` + `.log`, `scratch/analyzer/F1-export/`,
`scratch/hp-F-20260914-resume.27132/`, `scratch/hp-F-20260913-stripe/`
(summary.md, metrics.json, discriminant.json, lateral.json, features caches,
patches.png, fft2_montage.png, lateral_dprime.png, lateral_levels.png,
hist_*.png, psd_*.png, profile_*.png, wide.log), `scratch/m281-pjl-20260914/`.
Memories: `.claude` project memory `project-m281-toner-state`,
`project-m281-pjl-recon`.
