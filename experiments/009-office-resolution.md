# Experiment 009 — office resolution unlock (ORES-1)

**Question.** The Xerox AltaLink C8245 specs 1200×2400 print, but 007.6 proved
its PostScript RIP is a FIXED-600 device: every `/HWResolution [1200 1200]
setpagedevice` is silently refused and 1200-addressed PS content is
point-sampled onto the 600 grid (c3@1200 → ~24–26% deterministic alias
floor). The spec resolution is unreachable *via PostScript*. The untested
residue, explicitly queued, is the OTHER command languages the raw 9100 port
accepts:

- **PJL** — `@PJL SET RESOLUTION=1200` (a job-level hint the RIP may honour
  where the PS operator was refused), and
- **native PCL raster** — `Esc*t1200R` / `Esc*t2400R` (a different imaging
  path entirely; the most likely place a true fine grid is exposed).

ORES-1 tickles both, over one small K-only job set, so a home/known-scanner
scan tells us whether any path unlocked a real >600 grid.

## Discriminating design

ONE logical K-only bitmap is emitted through several command paths at several
requested grids — the ONLY variable is the command path/grid. Every sheet
carries, side by side, each science field at BOTH the requested grid AND a
**600-equivalent CONTROL** (same physical size, built from genuine 600-dots by
integer upsample). The controls are a real 600 grid and MUST decode; a
requested-grid field decodes IFF the path exposed the finer grid. That is the
whole logic: **600-control survives always; grid-field survives iff unlocked.**

K-only / neutral throughout → no MIC yellow lattice (007.8), grey-scannable.

## Jobs (build/, sha-gated byte-identical; `python gen_ores.py`)

| job | file | language / grid | discriminates |
|---|---|---|---|
| J0 | ores_query.pjl | PJL INFO/DINQUIRE, **prints nothing** | what RESOLUTION values / languages the RIP admits (read-back captured) |
| J1 | ores_pspjl1200.job | `@PJL SET RESOLUTION=1200` + PostScript@1200 | does the PJL hint override what PS `setpagedevice` refused? (also snapshots `currentpagedevice /HWResolution` to the backchannel before showpage) |
| J2 | ores_pcl1200.pcl | native PCL raster `*t1200R` | the native PCL raster path at 1200 |
| J3 | ores_pcl1200_pjlres.pcl | J2 + `@PJL SET RESOLUTION=1200` | PCL raster with the PJL hint too (some RIPs need both) |
| J4 | ores_pcl2400.pcl | native PCL raster `*t2400R` | push past 1200 if 1200 unlocked |

Bitmap fields (each present @grid and @600-control): PN c3, PN c2; gratings
1-on-1-off and 2-on-2-off, H and V; isolated 1-dot @8-dot pitch; 4 chiral
corner marks (registration) + a block-digit resolution label (self-ID by eye).
Active band ≈ 60×46 mm at the requested grid, 8 mm white margin baked in
(inside the measured ≤4 mm printable border on both engines). Sizes: J1 ~2.6 MB,
J2/J3 ~1.3 MB, J4 ~5.1 MB, J0 142 B.

PCL raster detail: unencoded mono (`*b0M`), rows packed MSB-first with a set
bit = black (PCL default foreground); raster started at the left graphics
margin (`*r1A`), `*rC` + form-feed + UEL to close. The emitter is validated by
self-parsing the raster bytes back to the exact ground-truth bitmap (no
external PCL renderer needed — `gpcl6` has no fonts on the dev box).

## Analysis (`python analyze_ores.py <scan.png> [--grid 1200|2400]`)

Registers on the four corner crosses (isolated low-fill components → affine),
samples each field (bilinear at dot coordinates, block-mean per cell, Otsu
threshold), and reports per requested-grid field. **Requires `--scan-dpi`**
(the known scanner resolution) — without it the tool cannot tell a real
unlock from a merely scaled-up print and refuses to claim one.

**Pre-registered decision rule (frozen before any office scan; the geometry
gate was ADDED 2026-07-07 after the print photo — see run log):**
1. `CONTROL_MAX = 0.06` — a 600-control BER above this ⇒ **SUSPECT** (scan/
   registration bad), verdict withheld.
2. **absolute-scale gate:** device_dpi = `scan_dpi / (scan-px-per-grid-dot)`,
   from the fitted affine. If device_dpi < `0.75 × requested` ⇒
   **SCALED@~Ndpi (no density gain)** — the printer imaged at a COARSER grid,
   so the cells decode only because they printed BIGGER, not denser. This is
   NOT an unlock. (This is what the AltaLink PCL path does: images at ~600, so
   1200 content prints 2× oversize — it would otherwise read a false UNLOCKED.)
3. **scan-adequacy gate:** if `px-per-grid-dot × cell_dots < 2.5` ⇒
   **INDETERMINATE** — this scan can't resolve the cell (a 1200 grid on a
   1200 scan is only ~1 px/grid-dot; the finer grids NEED the Canon 4800).
4. `COLLAPSE_BER = 0.20` — grid BER ≥ this ⇒ **COLLAPSED** (PS alias floor
   ~0.24–0.26). grid BER ≤ `max(1.5 × control_BER, 0.03)` ⇒ **UNLOCKED**;
   else **MARGINAL**.
- gratings report percentile modulation depth (diagnostic only, no verdict);
  they alias below a 2×-the-grid scanner.

A real UNLOCKED verdict therefore requires ALL of: 600-control decodes,
device_dpi ≈ requested (printed at the fine grid, not scaled up), the scan
resolves the cell, AND low grid BER. Positive control (M0-style): a synthetic
scan built at 2 px/grid-dot with scan_dpi=2×grid reads device≈grid (honored)
and all fields UNLOCKED; the same image relabelled scan_dpi=grid reads
device≈600 and correctly flips to SCALED — the gate is proven both ways.

## Print protocol (office, raw 9100 to <ip>)

Use the bundled `run_ores.sh` (confirmation-gated, transparent). Order: J0
first (capture its reply), then J1–J4 one sheet each, pen-annotate the label +
date on each ejected sheet, keep them. The script also sends the 007.9
different-day characterization batch (e004/e006c/e006bw verbatim) — one Xerox
day is not enough to bound day/consumable variance (rate ladders go on
multi-sheet minima).

## Scan protocol — SCAN ON THE CANON 4800 (this matters)

**The scanner is the binding constraint for exactly the grids ORES tests.** A
1200-printed field on the home 1200 flatbed is 1 sample/dot: the requested-grid
PN fields are undersampled (c3@1200 = 3 px/cell, c2@1200 = 2 px/cell = at
Nyquist) and the 1-on-1-off@grid gratings alias to low contrast REGARDLESS of
whether the printer unlocked. So a home-flatbed ORES scan is a ROUGH SCREEN
only — a clean UNLOCKED verdict is not obtainable there, and a low grating
contrast there is meaningless (scanner Nyquist, not printer).

- **ORES sheets J1–J4: Canon 4800 dpi GREY** (4–8 px per requested dot; the
  only scanner that resolves the finer grids; J4@2400 REQUIRES it — 1200 dpi
  is at its Nyquist). Home flatbed at 1200 acceptable only as a first screen,
  and only the 600-CONTROL fields + the PN c3@1200 (marginally) are trustworthy
  there — ignore the @grid gratings on a 1200 scan.
- **007.9 batch (e004/e006c/e006bw): home flatbed 1200 dpi** as their own
  experiments specify (600-addressed content = 2 px/dot, fine) — color for
  e006c/e004, grey for e006bw.
- Flat, 0°, enhancements OFF, all four corner marks in frame, **scan UPRIGHT**
  (the analyzer does not read the chiral marks — a rotated/flipped scan
  misreads; see below). Keep `responses/ores_query_response.txt`. Then
  `analyze_ores.py <scan> --grid <1200|2400>` per sheet.

## Run log

- 2026-07-07 — built + preflight green. Job shas in build/ores_manifest.json.
- **2026-07-07 PRINTED all 4 ORES sheets on the AltaLink (office, raw 9100,
  <ip>); the phone photo of 2026-07-07 (scratch, archive-private), not yet scanned.**
  PRELIMINARY VERDICT FROM THE PHOTO (before any scan):
  - Sheet sizes grow monotonically: J1 (PS+PJL, correct size) < J2/J3 (PCL
    1200, ~2x oversize) < J4 (PCL 2400, ~4x oversize, CLIPPED — the "2400"
    label prints as "240", last digit off the page edge).
  - The size ratio equals the raster's pixel-count ratio exactly (1200=2x,
    2400=4x), which RULES OUT driver fit-to-page (that would equalise sizes)
    and points to: **the AltaLink ignores the PCL `*t<res>R` raster
    resolution and images every PCL raster at a fixed ~600 dpi** (each raster
    pixel -> one 600-dpi device dot, so 1200-addressed content prints 2x
    oversize, 2400 4x). PostScript sheet J1 printed at the correct (small)
    size because an imagemask is resolution-independent -> PJL SET
    RESOLUTION=1200 did not change PS geometry either.
  - Reading: **no resolution unlock on ANY 9100 path** (PS, PJL-hinted PS,
    PCL raster). PCL just SCALES the content up — no density gain (it is
    600-dpi content printed bigger, not 1200-dpi content printed denser).
    Consistent with 007.6's fixed-600 PS finding; extends it to PJL+PCL.
  - Scan will quantify the exact device dpi (measure a corner-mark cross:
    123 dots -> 2.6mm=honored / 5.2mm=600 / 10.4mm=300; the 2x/4x + clipped
    "2400" both say 600).
- **2026-07-07 ANALYZER HARDENED (the photo exposed a real gap).** The
  size blowup would have FOOLED the BER-only analyzer into a false UNLOCKED:
  it registers on the corner marks, which scale up with everything, so the
  affine absorbs the 2x/4x and the (correctly-structured, just-bigger) cells
  decode at ~0% -> "UNLOCKED", despite ZERO density gain. Fix: analyze_ores.py
  now takes `--scan-dpi` and infers the printer's device dpi =
  scan_dpi / (scan-px-per-grid-dot, from the fitted affine). New verdict
  order: SUSPECT (control failed) -> **SCALED@~Ndpi(no density gain)** when
  device_dpi < 0.75*requested (the printed-oversize case) -> INDETERMINATE
  when the scan itself can't resolve the cell (px/cell < 2.5) -> then the BER
  verdict (COLLAPSED / UNLOCKED / MARGINAL). Without --scan-dpi it refuses to
  claim an unlock (geometry unchecked). 4 new tests (honored->UNLOCKED,
  scaled-but-decodes->SCALED, under-resolved->INDETERMINATE, no-scan-dpi->
  geometry None); suite 100 passed.
- **2026-10-11 — addendum, the office run re-read** (evidence line,
  docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a). The ORES-1 run folder
  (README.txt, run_ores.sh) that sent the five ORES jobs (J0–J4) now sits
  beside this log at `office-run-2026-07-07/` (the printer's IP replaced by
  `<ip>`); the jobs published under 009 in the paperholo-era release of the
  evidence archive are byte-identical to the original run folder's `jobs/`
  (the jobs are not kept in git; they are published in the archive). J0
  (`ores_query.pjl`) was sent 2026-07-07 at 16:24 from machine 2, and the
  printer's reply file stayed empty (0 bytes; the file itself is not kept).
  The four ORES sheets were NEVER scanned: the verdict above rests on the
  2026-07-07 phone photo alone, whose crop is published under 009 in that
  release.

## Limitations

- No PCL renderer on the dev box (gpcl6 fontless) → PCL validated by
  byte-level self-parse against the GT bitmap, not by rendering; the physical
  1=black raster polarity is the PCL default but is first confirmed on the
  real print.
- Single sheet per job = provisional; the verdict is coarse (UNLOCK/COLLAPSE),
  not a rate measurement. If a path UNLOCKS, a full c3@that-grid rate study on
  MSEL-1 (exp 008) follows.
- **Requested-grid gratings (1-on-1-off@grid) alias below a 2x-the-grid
  scanner** — do not read them on the home 1200 flatbed for the @1200 fields;
  they are a Canon-4800 readout. The PN c3@grid-vs-control comparison is the
  primary discriminator.
- **Orientation:** the analyzer assigns corners by position and does NOT read
  the chiral satellite counts, so a 180deg/mirrored scan silently misreads
  (~50% -> SUSPECT). Scan upright; the marks ARE chiral, so the M1 fix is to
  route registration through cal_core.register (8-orientation brute force).
- **PCL raster origin:** the PCL jobs start the raster at the page origin (no
  cursor offset); corner marks sit 8 mm in (MARGIN_MM/2) to clear an unknown
  engine's unprintable border. If a novel printer still clips a corner,
  increase MARGIN_MM and regenerate.
- **`*t2400R` may be rejected/clamped** by some PCL RIPs (2400 is a nonstandard
  raster resolution) — a refused/clamped J4 is itself a datum (reads COLLAPSED).
- J0 read-back depends on the RIP replying on the 9100 backchannel; if it is
  silent, the printed J1 backchannel line + the strip RD/RE on any subsequent
  PS job still report the granted resolution.
