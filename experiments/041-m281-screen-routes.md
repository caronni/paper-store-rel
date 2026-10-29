# e041 — M281 screen-defeat ladder: can a composite colour page reach the drum unscreened?

Date: 2026-10-04. Engine: HP CLJ Pro M281fdw `<host>` (<ip>),
toner C/M/Y 100 %, K 80 % (web portal, same day). Scanner of record: Canon
flatbed 2400 RGB. Branch `m281-screen-routes` (worktree
`<worktree> drivers in
`experiments/041-m281-screen-routes/`, jobs in `scratch/m281-routes-20261004/`.

SYNTHESIS OF RECORD: docs/M281-COLOUR-2026-10-05.md (engine facts, sheets,
instruments, capacity table, avenues and how they pay, open questions).

STATUS (2026-10-06): the campaign's measurements are complete through S17 and
written up; the synthesis of record is docs/M281-COLOUR-2026-10-05.md.
Seventeen sheets printed (S1–S17 less S13; S10p and S4 printed nothing), every
one measured; sections 041.4–041.5p below are the measured record in order.
HEADLINES: the M281 is a 600×8 contone engine with the screen in its video
path and no PDL door; single toners lay solid, every engine overlap is
screened; the screener is a per-page-fixed-region switch that spends a
budget of composite pixels (270–660 %·mm) and ignores colour count; cmyw
(white or one solid toner per cell) is never screened — c3 lossless (0.06 %),
c2 2.8–6.5 % tracking the print's Y−C registration; DOT-MIXED overlaps are
never screened — cmy8 at c3 3.2–3.7 %, cmy7 at c3 0.54 % (170 b/mm²), and the
overlap cell's layout ORIENTATION carries a bit at ~2 % (cmy7 + orientation
3.0 b/cell = 186 b/mm²); phase and amplitude do not; c2 dot-mixed, cmyk, K
overlays and screen steering are closed; K-only pages are immune. Scan mode
(2400 vs 4800) changes no cell state. Single sheets, context-free hard
decisions: NO promotion.

WHERE THE DATA LIVES: this log and the synthesis carry every number the
findings rest on. Generators and verifiers: `experiments/041-m281-screen-routes/*.py`
(every job regenerates byte-identically; shas in `results/JOB-SHA256.txt`);
instruments: `measure/e041_*.py`; `experiments/041-m281-screen-routes/results/`
keeps only the provenance table (README.md: sheet → job sha → page count → scan
sha256) and `measurements.json`, a ~250 KB extract of the readouts (per band the
errors, mutual information, poses, confusion matrices and layout scores; the
band-screen profiles; mixture configs; probe ranking; back channels). The full
readout outputs regenerate from the scans; the scans (1.7–6.9 GB each) stay in
`scratch/e041/` on the machine next to the printer.

## 041.0 The question, and why these rungs

e038 measured, with fresh toner, that the M281 renders a DeviceCMYK
composite contone and re-screens it (e002's device screens in every tile:
R/G 3.62 dots ±14° = 165 lpi, B 2.83 dots 45° = 212 lpi) at a rendering
contrast that leaves M and Y under their rungs everywhere but one 4–5 mm
band. The receiver-side ceiling (genie context) is below the rate, so the
fix is upstream of the scanner: either a job path that reaches the drum
without the contone step, or the engine's rendering contrast.

Reconnaissance 2026-10-04, read-only (`scratch/m281-pjl-20260914/
response.txt`, the printer's web portal): PJL `INFO VARIABLES` exposes
`BITSPERPIXEL=8 [1,2,4,8]`, `RET`, `DENSITY 1–5`, `ECONOMODE`,
`RESOLUTION 300/600`, `PERSONALITY`; no halftone or edge-control
variable. `INFO CONFIG` lists LANGUAGES PCLXL, COPY, NATIVEOFFICE,
PWG_RASTER, URP, PCL, PDF, POSTSCRIPT. The web portal offers calibration
timing, sixteen per-colour density sliders (all 0) and a PostScript
error-page toggle — nothing about halftoning. So the levers are PJL and
the language choice, not the portal.

**Same bits on every rung.** Every job carries sheet F's page
(`L:c3-cmy8-p120-v1@2240x1536`, counting payload 586,932 B, sha
`0da0afe445b9b0fa…`, GT `page000_gt.npy` sha `a9420188d346c787…`), so
each print decodes under the one fossil id and e038's stripe instrument
(`measure/stripe_f.py`: screen peak per channel, d' per plane) is the
readout. One variable per sheet.

| rung | job | what changes | verification before toner |
|---|---|---|---|
| S1 | `S1-pjl-bpp1.ps` | original PostScript wrapped in `@PJL SET BITSPERPIXEL=1` + `RET=OFF` | PostScript body byte-identical to F's |
| S2 | `S2-banded-halftone.ps` | ONE sheet, F's rows in three bands: tile rows 0–11 default halftone (control), 12–23 Type 3 (1x1 threshold 0x80), 24–34 Type 1 (600 lpi, angle 0, identity spot) — the halftone is graphics state, so control and candidates share the engine pass | gs bitcmyk 600 dpi render identical to F's (sha `8e8e5a3a52942188…`) |
| S3 | `S3-pcl-cmy3.pcl` | PCL 5c planar bilevel raster, Esc*r-3U (C, M, Y planes; the mode HP documents for colour LaserJets), no PostScript RIP | gpcl6 render vs GT, 0 differing dots per plane (§041.2) |
| S3b | `S3b-pcl-kcmy4.pcl` | the Esc*r-4U (K,C,M,Y) form — candidate only: -4 may be out of range on a LaserJet (blank or plane-shifted sheet) | gpcl6 placement 0 dots; Y unprovable in gpcl6's -4U palette |
| S5 | `S5-alphabet.ps` | the ALPHABET sheet: F's cmy8 rows (tile rows 0–11 and 24–34) above and below a band of e030's c3-cmy7 rows (12–23) at their native addresses — same tile matrix and placement, default halftone, one engine pass; decode each band under its own fossil id (`L:c3-cmy8-p120-v1@2240x1536`, `L:c3-cmy7-p120-v0@2240x1536`); the spliced GT for the optical instruments in `S5-alphabet-gt/` | gs render == row-splice of the two sources' renders (0 differing rows) |
| S6 | `S6-maxescape.ps` | F through EVERY PostScript door the printer answered to (§041.2 queries): `setpagedevice /ProcessColorModel /DeviceCMYK /PixelDepth 1`, the HP adaptive-halftoning operators false, `(Off) HPColorTrapping`, `false ColorSmartColorMatching`, `(NoAdj)` on the three ColorSmart adjustments, a Type 3 1x1 threshold halftone; two 50 %/60 % cyan WITNESS patches in the bottom border (default screen vs threshold) | gs render: field rows byte-identical to F; witness A 50 % screened, B uniform solid |
| S7a / S7b | `S7a-media-heavy.ps` / `S7b-media-cardstock.ps` | F with `/MediaType (Heavy)` / `(Cardstock)` in the setpagedevice dict — the engine's media profile (transfer and fuse conditions) as the one variable; a lever test on the BAND, not a screen route | gs renders identical to F |
| S3c | `S3c-pcl-cid-cmy.pcl` | PCL 5c Configure Image Data `Esc*v6W 01 02 01 01 01 01` (device-dependent CMY, direct by plane, 1 bit) ahead of the S3 planar raster — the documented device-CMY planar form | gpcl6 render byte-identical to S3's (0 differing dots); controls: no CID → C as K and M/Y dropped, illegal depth refused, Device RGB → the complement (§041.2) |
| S9 / S9b | `S9-pclxl-bilevel.pclxl` / `S9b-pclxl-dither1x1.pclxl` | PCL XL class 3.0, eRGB 16-entry palette (the eight states as RGB corners, 4-bit indexed pixels), SetColorTreatment eNoTreatment (2.1), adaptive halftoning and trapping eDisable, neutral axis eProcessBlack, halftone method eHighLPI (S9) or a downloaded 1x1 threshold 0x80 (S9b); PJL BITSPERPIXEL=1 — the "bilevel source is not dithered" clause as a route | gpcl6 10.08 ppmraw + bitrgb: C/M/Y 0 differing dots, render sha == S3's; negative controls refused per operator (§041.2) |
| S8 | `S8-rot180.ps` | F turned 180° ON THE PAGE (`595.2 841.92 translate 180 rotate` ahead of F's own translate/scale): the field is centred to the dot (margins 176 / 148 dots both sides), so the ink lands on the SAME device pixels with the content mirrored — the band-position test: paper-fixed → content tile column 11, content-fixed → 12 | gs bitcmyk: every plane == rot180 of F's render, 0 differing dots, footprint rows 148–6867 / cols 176–4783 on both, ink counts == GT; refuter (Opus) not refuted (§041.2) |
| S4 | `S4-pwg-cmyk8.pjl` | PWG raster cmyk_8 (0/255 per colorant, K 0) on 9100 — WITHDRAWN 2026-10-04 (§041.2: IPP says no pwg-raster, no CMYK URF) | libcups header read-back + own PackBits decode vs GT: 0 differing px (worker report, §041.2) |

Readout per sheet: 2400 RGB scan → `measure/stripe_f.py` on a holo3 run
dir (screen peaks present/absent per channel is the binary answer; then
d' per plane) → holo3 certificates per plane. A rung with no screen peaks
and C/M/Y separation near C's 4.8 page-wide is the resurrection.

Not printed and why: 300 dpi (`RESOLUTION=300`) is the same bitmap
pixel-replicated by the engine, with interpolation and coarser screen
sets as the only possible differences — a fifth rung only if S1 fails.

## 041.1 Jobs (built 2026-10-04)

| tag | bytes | sha256 | built by |
|---|---|---|---|
| S1-pjl-bpp1.ps | 31,208,448 | `95f09ab9d1b1b6ab…` | make_ps_variants.py |
| S2-sethalftone-type3.ps | 31,208,437 | `97afd19862c25e6e…` | make_ps_variants.py — superseded by the banded sheet, not printed |
| S2b-sethalftone-type1.ps | 31,208,446 | `1e410cb0da76158a…` | make_ps_variants.py — superseded, not printed |
| S2-banded-halftone.ps | 31,209,133 | `be647e0a1c2e05b6…` | make_banded_halftone.py; gs render sha == F's |
| S3-pcl-cmy3.pcl | 11,753,490 | `cdcfa5e4447d0fc4…` | pcl_planar.py --planes 3 (worker) |
| S3b-pcl-kcmy4.pcl | 15,671,254 | `faa030a427d3e93c…` | pcl_planar.py --planes 4 (worker); candidate |
| S5-alphabet.ps | 31,209,028 | `b0240b8ff3482889…` | make_alphabet_sheet.py; spliced GT sha `254452692388dfd7…` |
| S6-maxescape.ps | 31,209,216 | `2a3f43d0fc5789a6…` | make_maxescape.py |
| S7a-media-heavy.ps | 31,208,323 | `17151c35f0799f91…` | make_media_variants.py; `/MediaType (Heavy)` — a PPD name |
| S7b-media-cardstock.ps | 31,208,327 | `d5f1f817abd0ca25…` | make_media_variants.py; `/MediaType (Cardstock)` — NOT a PPD name (§041.4) |
| S3c-pcl-cid-cmy.pcl | 11,753,503 | `c523382625a9fbae…` | pcl_planar.py --mode cid-cmy (worker); gpcl6 render sha == S3's |
| S9-pclxl-bilevel.pclxl | 15,485,388 | `2f34bc008464db4c…` | pclxl_bilevel.py --variant base (worker) |
| S9b-pclxl-dither1x1.pclxl | 15,485,400 | `fe764ab598809d06…` | pclxl_bilevel.py --variant dither1x1 (worker) |
| S8-rot180.ps | 31,208,347 | `8d4e2b2b77f73cc6…` | make_rotated_sheet.py (workflow builder); gs render sha `2add345492792bca…` |
| S4-pwg-cmyk8.pjl / .pwg | 15,103,009 / 15,102,892 | `d65970ab6927e6e4…` / `b9876f9263bc0326…` | pwg_job.py (worker); verified, WITHDRAWN |

## 041.2 Worker verification records

**S4 (worker, 2026-10-04):** A4 cmyk_8 PWG built straight from `page000_gt.npy` at (148,176), K = 0; header read back through libcups field by field (600x600, 4960x7016, ColorSpace 6, chunky 32 bpp, A4, quality 4); the PackBits coding decoded by the worker's own strict decoder AND by `cupsRasterReadPixels`: 0 differing pixels per plane, 0 octets outside {0,255}, ink counts == GT (C 15,499,179 / M 15,490,098 / Y 15,123,663). Deterministic on re-run. Unverified: the `ENTER LANGUAGE=PWG_RASTER` keyword, device-colour handling of cmyk_8 (the VersaLink printed it as K luminance, e039 039.3t).

**IPP Get-Printer-Attributes (read-only, 2026-10-04, `scratch/m281-routes-20261004/ipp-attributes.txt`):** document-format-supported = image/urf, application/PCLm, application/octet-stream, application/pdf, application/postscript, application/vnd.hp-PCL, application/vnd.hp-PCLXL, image/jpeg — NO image/pwg-raster; urf-supported = V1.4, CP99, W8, OB10, PQ3-4-5, ADOBERGB24, DEVRGB24, DEVW8, SRGB24, DM1, IS1, MT1-2-3-5-12, RS600 — no CMYK; printer-resolution-supported 600 dpi only. Ruling: S4 withdrawn from the ladder (a 15 MB job on a format the engine does not list is a garbage-page risk); the file stays as a last-resort gamble. URF DEVRGB24 / DEVW8 noted as a possible later rung (device RGB, no colour management claimed; K-only W8 was bit-faithful on the VersaLink).

**PostScript capability queries (2026-10-04, zero paper, `query/ps-capability-query{,2,3}.ps` → `…response{,2,3}.txt`; each a PJL-wrapped PostScript job without showpage, read back on the 9100 channel):** product "HP Color LaserJet MFP M281fdw", PostScript version 3017, LanguageLevel 3. `HalftoneMode` = 0 (job halftones honoured): a Type 3 1x1 threshold and a Type 1 600 lpi `sethalftone` and a 20 lpi `setscreen` are all accepted and read back. Default `currenthalftone` type 2, `currentscreen` 60 lpi / 0°. Page device: `ProcessColorModel DeviceRGB`, `PixelDepth 8`, `PreRenderingEnhance`/`PostRenderingEnhance` false, HWResolution 600 — i.e. the interpreter renders into an RGB contone pipeline and the engine converts and screens below it. `setpagedevice` ACCEPTS `/ProcessColorModel /DeviceCMYK /PixelDepth 1` for the job, read back together with HWResolution 600. HP driver operators present (operatortype): `HP{Image,Graphics,Text}AdaptiveHalftoning` take a boolean (`false` ok), `HPColorTrapping` takes a string (`(Off)` ok; integers/booleans typecheck), `ColorSmartColorMatching` a boolean, `ColorSmart{Image,Graphics,Text}Adjustment` a string (`(NoAdj)` ok; `/NoAdj`, integers, booleans typecheck); `HPColorSmart` absent. System parameters (read only, never set — they persist in NVRAM): `DefaultScreening 2`, `SMGphaseX/Y 7/10`, `MGphaseX/Y 0/0`, `ENHphaseX/Y 0/0`, `StartupMode 1`. These are the inputs of S6.

**S3 (worker, 2026-10-04):** emitter `pcl_planar.py` (`--planes {3,4}` at build time; since the S3c build `--mode {cmy3,kcmy4,cid-cmy}`, `--planes` kept as an alias — S3 and S3b rebuild byte-identically under both spellings; deterministic, pyflakes clean). Job: UEL, `@PJL ENTER LANGUAGE=PCL`, `EscE Esc&l26A Esc&l0O Esc&l0L Esc&u600D Esc&l0E Esc*t600R Esc*r-3U Esc*r0F Esc*r4608S Esc*r6720T Esc*p34x148Y Esc*b0M Esc*r1A`, 6720 rows of C (`Esc*b576V`), M (`V`), Y (`Esc*b576W`), `Esc*rC EscE`, EOJ. Placement (148,176) checked against page000.ps. SIMULATION: gpcl6 10.08 `-lPCL5C -r600 -sDEVICE=ppmraw` (a stub TrueType font is needed for gpcl6 to start; the job draws no text): the -3U palette renders the eight states as clean primaries, so the job's own render splits back into planes — C/M/Y 0 differing dots each against the GT, ink counts == GT, 0 ink outside the field, no offset; isolation renders per plane also 0. Coordinate rules confirmed in gpcl6: X origin = logical page left edge (A4 offset 142 dots, HP's table), Y origin = top margin (hence `Esc&l0E`), `Esc&u600D` honoured. UNVERIFIED on the printer: a C+M+Y cell is palette index 7 "black" and may be laid with K toner instead of the three colour toners (the sheet measures this; it is not a defect of the job); whether the M281 colour-matches or halftones palette primaries; its A4 logical-page offset; `Esc*t600R` support. The -4U job (S3b) keeps its first build byte for byte; gpcl6 cannot prove its Y plane (its -4U palette renders Y black).

**S3c (worker, 2026-10-04 22:03):** the S3 job with the CID short form `Esc*v6W 01 02 01 01 01 01` (colour space 1 = device CMY, pixel encoding 2 = direct by plane, 1 bit per plane) in place of `Esc*r-3U`; everything else S3's (`Esc*r0F` kept, PJL job name `E041-S3C-PCL-CID-CMY`). 11,753,503 B, sha `c523382625a9fbae…`, three builds one sha, manifest beside it. gpcl6 10.08 implements CID PEM 2 device CMY: read-back 6720 rows × 3 planes × 576 B == GT; all eight states render as clean primaries (the -3U palette: C+M+Y = black); isolation renders C/M/Y 0 differing dots, ink counts == GT, first ink at (148,176); full render 0 differing dots, 0 ink outside the field — render sha `0d3e274a…` IDENTICAL to S3's, so the simulator cannot tell the two routes apart; only the sheet can. Controls built into `--verify` (pass = all three palettes differ from the job's): no CID → default palette (C prints black, M/Y dropped); illegal PEM 2 depth (byte 3 = 8) → gpcl6 refuses the CID and falls back to that default palette; byte 0 = 0 (device RGB) → the exact complement. gpcl6 accepts bits-per-index 0 for PEM 2 (not enforced). UNVERIFIED on the printer: whether the M281 accepts CID PEM 2 device CMY at all (a refusal looks like the no-CID control: C as K, M/Y gone, or the raster skipped); whether 1-bit device CMY is laid as that toner alone, unscreened and unmatched, or converted through RGB and the default render algorithm (`Esc*t#J` is not sent); whether C+M+Y is three colour toners or K; and S3's own unknowns (A4 logical-page offset 142 dots, `Esc*t600R`, `Esc&u600D`).

**S9 / S9b (worker, 2026-10-04 22:11):** emitter `pclxl_bilevel.py` (374 lines, pyflakes clean; imports the GT loader, placement check, stub font and geometry from `pcl_planar.py`; `--variant {base,dither1x1}`, `--omit {treatment,adaptive,trapping,neutral,halftone}` for ablations, `--verify`; every control in one `controls()` table with its protocol class and citation). Stream (little-endian, after `) HP-PCL XL;3;0`): BeginSession 600×600 eInch, ErrorReport eBackChAndErrPage (the printer prints an error page naming a refused operator — remove by a one-line edit); OpenDataSource eBinaryLowByteFirst; BeginPage portrait eA4Paper eDefaultSource; SetColorSpace eRGB, PaletteDepth e8Bit, a 16-ENTRY palette (the class 2.0 spec sizes it by ColorDepth, 2^4 × 3 bytes; gpcl6 refuses 8 entries with ImagePaletteMismatch; entries 8–15 white, never used) — sent BEFORE the controls because SetColorTreatment binds to the current colour space; SetColorTreatment eNoTreatment; SetAdaptiveHalftoning / SetColorTrapping AllObjectTypes eDisable; SetNeutralAxis eProcessBlack; SetHalftoneMethod per object type eHighLPI (S9) or DitherMatrixSize 1×1 eUByte e8Bit with one threshold 0x80 (S9b); SetCursor (176,148); BeginImage eIndexedPixel e4Bit 4608×6720 (e1/e4/e8 are the only depths; 4-bit is the smallest that carries eight indices; rows 2,304 B); 105 ReadImage blocks of 64 rows, eNoCompression; EndImage/EndPage/CloseDataSource/EndSession. PJL: UEL, JOB NAME, SET RESOLUTION=600, SET BITSPERPIXEL=1, ENTER LANGUAGE=PCLXL, stream, UEL, EOJ, UEL. Jobs: S9 15,485,388 B sha `2f34bc008464db4c…`, S9b 15,485,400 B sha `fe764ab598809d06…`, manifests beside them; three builds one sha each. gpcl6 10.08: own read-back of the stream (operators, attributes, cursor, contiguous blocks, 0 differing dots per plane); renders on ppmraw and bitrgb — 7014×4960, every pixel an RGB corner, C/M/Y 0 differing dots at (148,176), ink counts == GT, 0 ink outside the field, no messages, render sha `0d3e274a…` == S3's and S3c's. gpcl6 accepted every class 3.0 operator, so the planned 2.1-only fallback (S9c) was not built (if wanted: header class 2;1, the 1x1 dither as the halftone row, `--omit adaptive --omit trapping --omit neutral`). Negative controls: an out-of-enumeration value on SetColorTreatment / SetAdaptiveHalftoning / SetNeutralAxis / SetHalftoneMethod → IllegalAttributeDataType naming the operator; reserved tag 0x9a rejected; the header class is NOT checked (`9;9` passes), so gpcl6 cannot vouch for the M281 accepting `3;0`. Dropped as a pass criterion: gpcl6's own colour-managed pkmraw path turns a cyan cell into ~73 % white / 21 % cyan / 7 % cyan+yellow — what colour management does to these jobs if the printer applies it despite eNoTreatment; it says nothing about the M281. Spec errata found: the 3.0 tag table marks 0x92/0x94 reserved beside their own definitions; its Appendix F prints UnitsPerMeasure as 114 (137 everywhere else). UNVERIFIED on the printer: class 3.0 acceptance and operators 0x92/0x94 (a refusal should yield an error page, not a sheet); whether eNoTreatment, the disables, eProcessBlack, eHighLPI or the 1x1 dither are honoured (the spec lets a device read a dither matrix and ignore it); whether BITSPERPIXEL=1 applies; whether the engine still screens 0/255 RGB; what index 7 (RGB black = C+M+Y) becomes, K toner or process colour (the default brush black and ROP 252 leave the image unchanged in gpcl6).

**S8 (workflow: Opus builder + Opus refuter, 2026-10-04 ~22:50):** `make_rotated_sheet.py` splices ONE 43-byte line after `gsave /DeviceCMYK setcolorspace`: `595.200000 841.920000 translate 180 rotate` — in PLRM order it composes before F's `21.12 17.76 translate` / `552.96 806.4 scale`, so every user point maps (x, y) → (595.2 − x, 841.92 − y); the field box [21.12, 574.08] × [17.76, 824.16] pt is its own mirror (595.20 − 574.08 = 21.12; 841.92 − 824.16 = 17.76), i.e. 176 + 4608 + 176 = 4960 and 148 + 6720 + 148 = 7016 dots. Job 31,208,347 B (F + 43), sha `8d4e2b2b77f73cc6…`, deterministic (two builds, cmp identical); the first 11 lines and everything after the inserted line byte-identical to F. gs 10.08 `-r600 -sDEVICE=bitcmyk -g4960x7016`: F's render sha `8e8e5a3a52942188…` (== the recorded one), S8's `2add345492792bca…`; K empty on both; C/M/Y each 0 differing dots against `np.rot90(F, 2)` (against the unrotated F ~15.5 M per plane, so the check is not vacuous); footprint rows 148–6867, cols 176–4783 on both; ink counts C 15,499,179 / M 15,490,098 / Y 15,123,663 == GT. The refuter re-ran its own gs renders and the byte comparison, worked the discrimination: the page centre 104.987 mm is the boundary between paper columns 11 and 12; on S8 paper column p carries content column 23 − p; a paper-fixed band (108–113 mm) reads as CONTENT column 11, a content-fixed one as content column 12 (now at paper 96.97–101.97 mm); both inside one whole column, ~3 mm from the centre boundary; `e041_gt_compare.py` detects the turn on the centre tile and reports content columns (nx − 1 − tx under rot180), whichever way the sheet is laid on the glass. Confound noted, not a refutation: an image under a 180° CTM may take a different interpreter path on the M281 — it could move screen strength or placement by a dot, not a 4–5 mm band by an 8.128 mm column. Note for the record: `make_banded_halftone.py` has no bitcmyk unpacker despite its docstring; the one in `scratch/m281-routes-20261004/_verify/refute.py` was copied, not imported.

## 041.3 Prints and scans

Scope of "standing go": the operator's "print without prompt" (2026-10-04, row 041.9p; rows 041.12p–041.14p and §041.5's "print each when ready on the standing go" lean on it) was a go given in that session for that session's e041 sheets. It does not waive .claude/rules/hardware.md: every print needs explicit confirmation in the current session.

| run | date | sheet | path | details |
|---|---|---|---|---|
| 041.1p | 2026-10-04 ~12:30 | S1 | `scripts/print_plane.sh` raw 9100 | sent 31,208,448 B, sha `95f09ab9…` confirmed by the script. Operator's eye: "looks very promising"; a vertical band down the middle with more yellow |
| 041.1s | 2026-10-04 12:40 | scan of S1 | Canon 2400 RGB | `scratch/e041/e041-s1-2400.tiff` (1.72 GB) sha `65cce4550247c6b9bf96…` |
| 041.1s' | 2026-10-04 13:05 | S1 rescanned, sheet turned 180° | Canon 2400 RGB | `scratch/e041/e041-s1-2400-180deg.tiff` sha `bf2a1d91451d7d630f5a…` — the gradient control (printer vs scanner) and the second capture |
| 041.1d | 2026-10-04 ~14:13 | S1 decode, both captures | holo3 `--format L:c3-cmy8-p120-v1@2240x1536 --dpi 2400 --dpi 2400 --workers 8 --diag 8023`, run dir `scratch/e041/S1-run.29391` (operator-launched; `.29378` was a mis-named attempt) | at 13 min: 830 certified (C 801 / M 28 / Y 1), calibrated 11/11, close open |
| 041.6p | 2026-10-04 ~20:45 | S6 | `scripts/print_plane.sh` raw 9100, sha `2a3f43d0…` | operator: "visually it has a very different feel" |
| 041.6s | 2026-10-04 20:54 / 21:02 | S6 scanned twice (re-placed) | Canon 2400 RGB | `scratch/e041/e041-s6-2400.tiff` sha `268816eebb15f7a2…`, `e041-s6-2400-b.tiff` sha `99158ace39a80619…` |
| 041.6d | 2026-10-04 ~20:56 | S6 decode, both captures | holo3, run dir `scratch/e041/S6-run.45561` (operator-launched) | at 9 min: 268 certified (C 227 / M 41 / Y 0), 2,209 attempted, calibrated 7/8 |
| 041.7p | 2026-10-04 ~22:10 | S7a | `scripts/print_plane.sh` raw 9100, sha `17151c35…` | sent 31,208,323 B — F with `/MediaType (Heavy)`; the ONE variable is the media profile |
| 041.8p | 2026-10-04 ~22:12 | S7b | same, sha `d5f1f817…` | F with `/MediaType (Cardstock)`; queued behind S7a |
| 041.7s | 2026-10-04 21:57 | scan of S7a | Canon 2400 RGB | `scratch/e041/e041-s7a-2400.tiff` sha `9025aabd1d49c6db…` (landed at the repo root, moved) |
| 041.8s | 2026-10-04 22:05 | scan of S7b | Canon 2400 RGB | `scratch/e041/e041-s7b-2400.tiff` sha `d40ca8f1528f77cb…` (same) |
| 041.9p | 2026-10-04 ~22:48 | S3c | `scripts/print_plane.sh` raw 9100 (operator's standing go "print without prompt"; the script's `yes` supplied through `expect`), sha `c523382625a9fbae…` confirmed by the script | sent 11,753,503 B — PCL 5c CID device CMY |
| 041.10p | 2026-10-04 ~22:49 | S9 | same, sha `2f34bc008464db4c…` confirmed | sent 15,485,388 B — PCL XL 3.0 bilevel, eNoTreatment; an error page instead of a sheet = the class/operators refused |
| 041.11p | 2026-10-04 ~22:52 | S8 | same, sha `8d4e2b2b77f73cc6…` | sent 31,208,347 B — F turned 180° on the page, the band-position test |
| 041.9s | 2026-10-04 23:55 | scan of S3c | Canon 2400 RGB | `scratch/e041/e041-s3c-2400.tiff` sha `6a603cfda6d9ae3b…` (laid the other way round: the instrument reads rot180) |
| 041.10s | 2026-10-05 00:03 | scan of S9 | Canon 2400 RGB | `scratch/e041/e041-s9-2400.tiff` sha `7f73adbf4741c40d…`; operator: "looks *very* different" |
| 041.11s | 2026-10-05 00:12 | scan of S8 | Canon 2400 RGB | `scratch/e041/e041-s8-2400.tiff` sha `0d747c15be6d9f76…` |
| 041.12p | 2026-10-05 ~00:20 | S9b | `scripts/print_plane.sh` raw 9100 (standing go), sha `fe764ab598809d06…` confirmed | sent 15,485,400 B — S9 with the downloaded 1x1 threshold matrix (0x80) as the halftone method |
| 041.12s | 2026-10-05 00:38 | scan of S9b | Canon 2400 RGB | `scratch/e041/e041-s9b-2400.tiff` sha `22ff018fc965d1a9…` (laid the other way: rot180) |
| 041.13p | 2026-10-05 ~03:05 | S10p | `scripts/print_plane.sh` raw 9100 (standing go), sha `0e2f5e5fb1f921ae…` confirmed by the script | sent 2,092,746 B — the PCL XL RGB probe sheet (§041.5); an error page instead of a sheet names the refused operator (eSRGB is the one candidate, drawn last) |
| 041.13p' | 2026-10-05 ~10:20 | S10p RESULT | — | NOTHING PRINTED. PJL INFO STATUS read "Dokument wird gedruckt" (10023) for ~2 min, then "Bereit" with PAGECOUNT unchanged at 3397: the formatter processed the job and discarded the page, no error sheet (the ErrorReport back channel was lost when the socket closed after 10 s idle). Resent ~10:40 through the wrapper with the connection held open (`PRINT_NC_WAIT=900 PRINT_BACKCHANNEL=…`, the wrapper extended on the branch for it): the panel showed **HP 49 SERVICE ERROR** (a formatter firmware crash), power cycle required, nothing on the back channel. The job as built CRASHES the M281's formatter; it is not to be resent. |
| 041.14p | 2026-10-05 11:27 | S10p2 (banded probe) | `scripts/print_plane.sh` on the branch, raw 9100, `PRINT_NC_WAIT=600 PRINT_BACKCHANNEL=scratch/e041/S10p2-backchannel.txt` (standing go), sha `3bfe4add94c3a493…` confirmed | sent 23,473,742 B; printer Ready before (page count 3397) and after (3398 at 11:28) — ONE PAGE PRINTED, no error; back channel empty (0 B) |
| 041.15p | 2026-10-05 12:48 | S11 (mixture probe) | wrapper on the branch, raw 9100, back channel held (`scratch/e041/S11-backchannel.txt`), sha `b89f6883b942be5c…` confirmed | sent 26,455,613 B; Ready before (3398) and after (3399 at 12:50) — ONE PAGE PRINTED, no error; eTonerBlack accepted by the firmware (the twin `S11t…` sha `db78c5a4…` stays unprinted) |
| 041.16p | 2026-10-05 ~12:52 | S4 = S13 (PWG raster cmyk_8, F's page, `@PJL ENTER LANGUAGE=PWG_RASTER`) | wrapper on the branch, back channel held (`scratch/e041/S4-backchannel.txt`), sha `d65970ab6927e6e4…` | sent 15,103,009 B; outcome below |
| 041.16p' | 2026-10-05 12:53 | S4 RESULT | — | NOTHING PRINTED; the back channel (`scratch/e041/S4-backchannel.txt`, 513 B) carries the renderer's refusal three times: `PWG_RASTER Error — Subsystem: RENDERER — Error: InternalError 0xc8 — File Name: PWGRasterPageHeader — Line Number: 551`. The PWG personality exists on this firmware and parses the stream; its PAGE HEADER parser refuses ours (cmyk_8, ColorSpace 6, 32 bpp — the one thing the job asked for). No crash: status Ready after. The last device-CMYK door is CLOSED by the firmware's own message. |
| 041.17p | 2026-10-05 13:08 | S12 (PostScript twin of S11) | wrapper on the branch, raw 9100, back channel held (`scratch/e041/S12-backchannel.txt`, 0 B), sha `3ec2a2ee040112df…` confirmed | sent 9,185,360 B; Ready before (3399) and after (3400 at 13:09) — ONE PAGE PRINTED, no PostScript error on the back channel: Detail ColorSmartImageHalftone, TonerBlack HPImageNeutralAxis, Off HPColorTrapping and false HPImageAdaptiveHalftoning all accepted in a printing job |
| 041.15s | 2026-10-05 13:28 | scan of S11 | Canon 2400 RGB | `scratch/e041/e041-s11-2400.tiff` sha `0e7bea7c9c38f251…` (landed in the worktree root, moved); readout `scratch/e041/mixture/S11-pclxl-mixture-{patches.csv,summary.json}`, log `mixture-readout-S11.log` |
| 041.17s | 2026-10-05 13:39 | scan of S12 | Canon 2400 RGB | `scratch/e041/e041-s12-2400.tiff` sha `76d6f3c0a34407c7…` (landed in the worktree root, moved); readout `scratch/e041/mixture/S12-ps-mixture-*`, log `mixture-readout-S12.log`; bar lattice for both sheets `mixture/S11-S12-bar-screen.json` |
| 041.18p | 2026-10-05 14:16 | S14 (page-scale probe, PostScript) | wrapper on the branch, raw 9100, back channel held (`scratch/e041/S14-backchannel.txt`), sha `6081414085e91257…` confirmed | sent 32,386,996 B; page count 3400 → 3401, Ready, no error — ONE PAGE PRINTED |
| 041.18s | 2026-10-05 14:45 | scan of S14 | Canon 2400 RGB | `scratch/e041/e041-s14-2400.tiff` sha `198a25215496096620d6…`; operator: "A2 shows the familiar vertical band; A3 and the second cmyk5 band also show vertical bands, at the very left and at the known position, but much wider"; screen profile `scratch/e041/band-screen/` (`measure/e041_band_screen.py`, log `band-screen-S14.log`), page readout `scratch/e041/scale/` (log `scale-readout-S14.log`) |
| 041.19p | 2026-10-05 15:49 | S15 (reset probe, PostScript, S14 footing) | wrapper on the branch, raw 9100, back channel held (`scratch/e041/S15-backchannel.txt`, 0 B), sha `43c195288ab43e98…` confirmed | sent 33,030,058 B; page count 3401 → 3402 at 15:51, Ready, no error — ONE PAGE PRINTED |
| 041.19s | 2026-10-05 16:02 | scan of S15 | Canon 2400 RGB | `scratch/e041/e041-s15-2400.tiff` sha `2f79036a1c7c893531b537dc57936a592b0466c19c3542d776b038366bae76fe`; operator: "the 5 cm shifted row is super weird"; screen profile `scratch/e041/band-screen/S15-ps-reset-*` (log `band-screen-S15.log`), page readout `scratch/e041/scale/S15-ps-reset-*` (log `scale-readout-S15.log`) |
| 041.20p | 2026-10-05 18:03 | S16 (trigger probe, PostScript, S15 footing + one K imagemask) | wrapper on the branch, raw 9100, back channel held (`scratch/e041/S16-backchannel.txt`, 0 B), sha `1ccf884a64b13dc5…` confirmed | sent 32,515,467 B; page count 3402 → 3403 at 18:06, Ready, no error — ONE PAGE PRINTED (the imagemask did not fault) |
| 041.20s | 2026-10-05 18:18 | scan of S16 | Canon 2400 RGB | `scratch/e041/e041-s16-2400.tiff` sha `61a2d2786804169f4a564f9276d534fdcbf3ee0623cb9aeb111e3c4aaaa781db`; screen profile `scratch/e041/band-screen/S16-ps-trigger-*` (log `band-screen-S16.log`), page readout `scratch/e041/scale/S16-ps-trigger-*` (log `scale-readout-S16.log`; readout now also carries the whole-cell reading `*_wholecell`, additive — S15 re-run: original columns identical) |
| 041.21p | 2026-10-06 00:12 | S17 (layout probe, PostScript, S16 footing; one K imagemask data band) | wrapper on the branch, raw 9100, back channel held (`scratch/e041/S17-backchannel.txt`, 0 B), sha `02bea73e842b0d76…` confirmed | sent 31,583,218 B; page count 3403 → 3404 at 00:16, Ready, no error — ONE PAGE PRINTED |
| 041.21s | 2026-10-06 00:55 | scan of S17 | **Canon 4800 RGB** (the first 4800 capture of the campaign; classic TIFF, 6,875,455,728 B, 56128 × 40832, its 32-bit StripByteCounts wrapped — tifffile reads by shape) | `scratch/e041/e041-s17-4800.tiff` sha `6fd8222b8392806f1782da8fadad936b0b189cd88df5629970fc9e4f6cc74194`; screen profile `scratch/e041/band-screen/S17-ps-layouts-*` (log `band-screen-S17.log`, `--scan-dpi 4800`), page readout `scratch/e041/scale/S17-ps-layouts-*` (log `scale-readout-S17.log`; readout with the layout axis, `measure/e041_layout_readout.py`) |
| 041.21s' | 2026-10-06 09:27 | rescan of S17 | Canon 2400 RGB (same sheet, re-placed) | `scratch/e041/e041-s17-2400.tiff` sha `f708339b14bcbe5687a2926ceda165bdbf1c67d0f1158f70a3460f0da3fd5496`; readouts `scratch/e041/scale-2400/`, `scratch/e041/band-screen-2400/` (logs `scale-readout-S17-2400.log`, `band-screen-S17-2400.log`) |
| 041.14s | 2026-10-05 11:40 | scan of S10p2 | Canon 2400 RGB | `scratch/e041/e041-s10p2-2400.tiff`; readout run by the operator 11:41 → `scratch/e041/probe/S10p2-pclxl-rgb-probe-{patches.csv,summary.json}` |
| 041.13s | 2026-10-05 00:46 | scan of S1dash-notriple (the cmy7/cmy8 session's sheet: S1's wrapper, F with every payload CMY triple reduced to two inks, printed by that session) | Canon 2400 RGB | `scratch/e041/e041-s1dash-notriple-2400.tiff` sha `953e3e474c7a1e2e…`; job + GT in `scratch/m281-routes-20261004/S1dash-notriple*` |
| (S2, S3, S3b) | | built, HOLD — not printed; S5 withdrawn (cmy7 dead end, ruling 2026-10-05) | | |

## 041.4 Results

**S1 (`@PJL SET BITSPERPIXEL=1` + `RET=OFF`): NEGATIVE — no measurable
change.** Instrument `measure/e041_screen_map.py` (scan-space, no receiver,
no truth: per 768-px block the FFT power at the two known screen lattices
over the ring median, and the block's mean R/G/B), run identically on
the S1 scan and on e038's F capture (`scratch/e041/maps/`, montage
`montage-F-vs-S1.png`, profiles in `maps-S1.log` / `maps-F.log`):

| whole-field median | F (2026-09-13) | S1 |
|---|---|---|
| 165 lpi screen, G | 470 | 462 |
| 212 lpi screen, B | 1227 | 1240 |
| 165 lpi screen, R | 280 | 309 |
| mean R / G / B | 129.3 / 123.5 / 126.0 | 131.8 / 125.2 / 129.0 |

The screens are present at the same strength over the whole page, the
rendering band is at the same column (block 11, screen in G 131 vs 121,
in B 538 vs 557, both prints), the same left-to-right darkening (B 134 →
120 on F, 139 → 120 on S1; G 131 → 119 / 135 → 118) and the same weaker
columns (blocks 1, 3, 10–11, 19, 21). S1 is 2–3 levels lighter overall
(print-to-print). The operator's "vertical band with more yellow" is the
rendering band: mean B and G dip there because M and Y lay denser; it is
not a second screen and not a new feature. The screen covers the entire
printout on both sheets — there is no unscreened region to speak of.
Either the variable is not honoured for PostScript jobs or the 1-bit
render path still screens the composite; the print cannot tell which.
No decode run (the certificates would replicate e038's; the screen
question is answered in scan space).

**S6 (every PostScript door at once): NEGATIVE, and worse than S1.** Same
instrument (`maps-S6.log`): the 165 lpi screen is FOUR TIMES STRONGER than
on S1 (R median 1,243 vs 309; G 1,856 vs 462), the 212 lpi family about the
same (B 1,048 vs 1,240), and the page is lighter in every channel (mean R/G/B
152/140/138 vs 132/125/129 — less toner per cell). The band is still at
block 12 (G 537 against ~2,000 around it). The decode (two captures, at
9 min) had C 227 / M 41 / Y 0 where S1 had C ~800 at the same age.
**The witnesses settle the mechanism:** both border patches printed as the
same ~50 % screened tint (mean R 159.5 vs 159.7; 165 lpi peak/ring 16k and
17k; paper 231) — the 60 % patch under the one-cell threshold did NOT come
out solid. The interpreter accepted every operator, and the engine screened
the result anyway with its own 165/212 lpi screens: the halftoner sits
BELOW the PostScript interpreter, in the formatter/engine, and no
graphics-state halftone reaches it. `PixelDepth 1` / `DeviceCMYK` were
accepted as page-device keys without changing what reaches the drum.
What DID change is the tone mapping: turning ColorSmart matching and
adjustment off (`false ColorSmartColorMatching`, `(NoAdj)`) made every cell
lighter and the screen more open — the default adjustment was helping,
not hurting. Which of the five doors did that is not separated (one
sheet, five changes, by design: the resurrection was the hypothesis).

**Query 4 (zero paper):** the string-taking HP operators accept ANY string
(`(xyz)` ok) — the operand is type-checked, not value-checked, so an unknown
value is silently ignored or defaulted. Three more operators exist:
`ColorSmart{Image,Graphics,Text}Halftone` (the driver's Halbtöne Detail /
Smooth selection per object type — a lever on WHICH engine screen is used);
`setcolorrendering`, `findcolorrendering`, `setblackgeneration`,
`setundercolorremoval` are live (`{ pop 0 }` accepted for both). 52 other
guessed names absent.

**Query 5 (zero paper, media):** `setpagedevice /MediaType` accepts and
reads back ANY string (`(xyz)` included) and `/MediaWeight 200` likewise —
acceptance is not validation; the names the firmware maps are HP's PPD
names (`Heavy` is one, `Cardstock` is NOT — the PPD's list is under S7 at the end of §041.4). The web portal's
Papiersorten page maps paper TYPES to the engine's print MODES: Normal,
Normal2, Leicht, Extra leicht, Schwer, Karton, Leicht glänz., Hochglanz,
Glänz. schwer, Transparenz, Etikett, Folie opak (currently Rough → Schwer,
HeavyRough → Karton, Bond → Normal2, the rest Normal).

**The band, re-read 2026-10-04 evening (operator, raking light):** gloss is
homogeneous across S1 — the band is "noticeably more yellow, same grain".
That rules out a fusing band (no gloss stripe, and fusing adds no yellow).
What fits denser M/Y on the dots + cleaner whites + same grain + one x for
all planes + the lateral density gradient is the shared TRANSFER nip
(secondary transfer roller / belt): better contact or field at that x
moves more toner from belt to dot and scatters less into the whites; a
pressure or field gradient across the same nip gives the gradient. Lever
if right: the engine's media profiles (transfer voltage, nip behaviour) —
S7 below.

**S7 built** (`make_media_variants.py`: `S7a-media-heavy.ps` with
`/MediaType (Heavy)`, `S7b-media-cardstock.ps` with `/MediaType (Cardstock)`,
F's image data unchanged, gs renders identical to F; one variable each),
printed 22:10 / 22:12 without a panel prompt — the result is at the end of
this section.

**S1 vs S6 against the ground truth, two instruments (2026-10-04 night).**
Record instrument (`measure/e039-cell-truth/cell_error.py`, holo3 placements,
hard read per cell, whole page; `cell-error-S1.log` / `-S6.log`):

| plane / channel | S1 inked / blank | S1 error | S6 inked / blank | S6 error |
|---|---|---|---|---|
| C / R | 94 / 169 | 13.3 % | 121 / 182 | 18.4 % |
| M / G | 104 / 146 | 24.4 % | 120 / 158 | 26.0 % |
| Y / B | 117 / 139 | 35.3 % | 129 / 145 | 40.2 % |

New instrument (`measure/e041_gt_compare.py`: receiver-free — orientation
detected on the centre tile, a page affine from six anchors, per-tile
FFT registration to the C plane, M/Y refined within ±6 px, a 0.5-cell box
per cell, binned by true state; `gt-compare-S1.log` / `-S6.log`), mean
R/G/B per state over ~420k cells each:

| state | S1 R/G/B | S6 R/G/B |
|---|---|---|
| W | 175/152/148 | 185/163/156 |
| C | 77/129/143 | 95/136/150 |
| M | 166/106/123 | 183/127/132 |
| CM | 97/106/129 | 134/119/128 |
| Y | 177/148/123 | 187/161/137 |
| CY | 86/132/128 | 105/137/140 |
| MY | 171/109/105 | 183/131/120 |
| CMY | 100/111/117 | 125/124/126 |

Paper ≈ 231. Medians: S1 d' C 5.37 / M 3.15 / Y 1.92, hard error 7.0 /
15.3 / 28.7 %; S6 4.40 / 2.60 / 1.71 and 11.4 / 19.3 / 37.2 %. Reading:
S6 lifted every level — whites by 7–11 (less background), single inks by
10–21 (less density), overlaps by 25–37 (C under M: R 97 → 134). The
"different feel" is less toner everywhere, most of all on overlaps; the
whites' gain is smaller than the inks' loss. The OVERLAP TAX is visible
on both sheets: C alone R 77 but 97 under M and 100 under M+Y on S1 — a
faithful print would not change cyan's red absorption when magenta is
added, so the overlapped planes are being moved off 0/255 before the
screen (the research reader's reading of the 600x8 contone pipeline, see
below). The band is in both lateral profiles (S1 col 12: M d' 4.36 vs
~3.1, Y 3.24 vs ~1.9; S6 col 12: M 4.00 vs ~2.6) — independent of the
colour-path change. The first S1 scan is rotated 180° relative to the
truth (the instrument detects it; the receiver never cared).

**Web research 2026-10-04 (Opus reader; sources cited in its report, PPDs
and PDFs in the session scratchpad):** (1) the M278–M281 PostScript PPD
(HPLIP, `*PSVersion (3010.107) 3`) passes BARE NAMES — `Off HPColorTrapping`,
`NoAdj ColorSmartImageAdjustment`, `Smooth`/`Detail ColorSmart*Halftone`,
`TonerBlack`/`ProcBlack HP*NeutralAxis` — and offers Edge Control (Off /
Light / Normal / Max), Halftone (Smooth default / Detail), RGB emulation
(MatchScreen default / PhotoQuality / AdobeRGB / Vivid / NoAdj), neutral
greys per object (images default ProcessBlack), 31 MediaType strings;
nothing about PixelDepth, RET or print quality. (2) The device id ends
`RES=600x8`: an 8-bit contone engine with the screen in the video path
below every PDL — 0 and 255 pass the screen unchanged, so single-plane
masks print faithfully and anything the colour path moves off 0/255 is
screened. (3) PJL BITSPERPIXEL is documented "for PCL 6 only". (4) PCL 5c
on the 4500-class subset: no snap-to-primaries (`Esc*t#J` 0/3/15/18 only),
no dither download; CID `Esc*v6W 01 02 01 01 01 01` = device-dependent
CMY, direct by plane, 1 bit each — the documented device-CMY planar form
(S3c, building). (5) PCL XL (no CMYK): "if the source pixel intensity is
bi-level, the dithering process is not performed"; class 2.1
SetColorTreatment eNoTreatment; class 3.0 SetHalftoneMethod 1x1 user
dither, SetAdaptiveHalftoning eDisable, SetColorTrapping eDisable,
SetNeutralAxis eProcessBlack (S9, building). (6) Nothing documents
`DefaultScreening` or the SMG/MG/ENH phases. (7) No field report of
unhalftoned colour planes on this engine family.

**Query 6 (zero paper):** the bare names ARE strings on the device (`Off`
→ "Off", `NoAdj` → "NoAdj", `Smooth`, `Detail`, `TonerBlack`, `ProcBlack`
all defined as strings; `Basic` undefined), so S6's string operands were
the PPD's values after all — S6 stands as the full PostScript test. No
CMYK ink-set emulation operators exist on this firmware; the three
`HP*NeutralAxis` operators do (TonerBlack / ProcBlack accepted).
`PostRenderingEnhance` cannot be turned on (reads back false after the
4700-style REValue dict). Halftone resources: EnhancedHalftone,
ClusterHalftone, DefaultHalftone600, DefaultHalftone; ColorRendering:
Default/Enhanced(600), ClusterCRD, Perceptual/Relative/Saturation.SWOP.none.

**The gradient is the printer's** (S1 rescanned turned 180°, same
instrument, `maps-S1rot.log`): the strip mirrors from block 11 to block 12
(23 − 11) as any printed feature must, and the darkening mirrors with it —
unrotated mean B 139 (left) → 120 (right), rotated 121 (left) → 133
(right); G 135 → 118 and 120 → 128. A scanner gradient would have stayed
on the scanner's right. So the engine lays M and Y denser toward one
side of the page (the side at x ≈ 190 mm on that first S1 scan's axis —
CORRECTED 2026-10-05: the GT comparison found that scan turned 180° against
the content, so the dense side is the content's LEFT, x ≈ 20 mm, the edge
that carries S9's 3 mm border band below) on top of the strip. The weaker secondary columns (blocks 1, 3, 19, 21 on
the unrotated scans) do not mirror cleanly and are not the printer's.

**S7a (`/MediaType (Heavy)`) and S7b (`/MediaType (Cardstock)`): NEGATIVE —
the media profile moves neither the screen nor the band.** Both scans
through the same two instruments (`screen-map-S7a.log` / `-S7b.log`,
`gt-compare-S7a.log` / `-S7b.log`, maps in `maps/S7a-*` / `S7b-*`):

| whole-field median | S1 | S7a Heavy | S7b Cardstock |
|---|---|---|---|
| 165 lpi screen, G | 462 | 554 | 479 |
| 212 lpi screen, B | 1240 | 927 | 1178 |
| mean R / G / B | 131.8 / 125.2 / 129.0 | 131.7 / 126.9 / 131.2 | 131.5 / 125.9 / 128.4 |

| plane | S1 d' / hard error | S7a | S7b |
|---|---|---|---|
| C | 5.37 / 7.0 % | 5.21 / 8.0 % | 5.09 / 7.7 % |
| M | 3.15 / 15.3 % | 3.06 / 16.2 % | 3.08 / 16.1 % |
| Y | 1.92 / 28.7 % | 1.70 / 31.1 % | 1.91 / 28.1 % |

Per-state means within 4 levels of S1 on both sheets (S7a's overlaps 2–5
levels lighter: CMY 104/116/122 against 100/111/117; its Y cells 3 levels
less yellow, B 126.9 against 123.4). The band is at tile column 12 on
both (M d' 4.38 / Y 3.05 on S7a, 4.19 / 2.96 on S7b, against ~3.0 / ~1.8
beside it; S1 4.36 / 3.24), the screen collapses inside it exactly as
before (165 lpi G 121 / 109 against 540–680 around it), and the lateral
M/Y gradient is there (mean B 122 → 135 on S7a, 124 → 131 on S7b; these
scans lie the other way round from the first S1 scan, so it is the same
side of the page). The instrument's print-to-print noise is F against S1:
2 % on the 165 lpi G median, 1 % on the 212 lpi B. S7b sits inside it
(+4 % / −5 %), S7a outside (+20 % on the 165 lpi energy, −25 % on the
212 lpi, Y d' −0.22): the Heavy profile reaches the page, a little, and
in the wrong direction; S7b is a third F print under S1's conditions —
consistent with the PPD finding below that `Cardstock` is not a name the
firmware maps, so the job most likely ran in the default mode. Neither
moves the band by a column or changes its depth. The transfer-nip reading
of the band is not refuted (a profile need not change the nip at that x),
but the one lever the profile offers is spent. For the ladder: the screen
is in the video path, the media profile is below it, and the band is a
fixed-x engine feature that neither the colour path (S6) nor the media
profile (S7) touches.

**PPD media names (research reader, second pass):** the M278–M281
PostScript PPD's `/MediaType` strings are Plain, Light, Intermediate,
Mid Weight, Heavy, Extra Heavy, Heavy Gloss, Extra Heavy Gloss, Card
Glossy, Transparency, Labels, Letterhead, Envelope, Heavy Envelope,
Preprinted, Prepunched, Color, Bond, Recycled, Rough, Heavy Rough, Gloss
Film and the HP-branded names (HPEcoSmartLite, HP Matte 90/105/120/160,
HPCoverMatte, HP Glossy 130/160/220, HP Tri Glossy 160); Unspecified is
`/MediaType null`. `Cardstock` is not among them. The portal maps
HeavyRough → Karton, so `/MediaType (Heavy Rough)` is the spelling that
reaches the Karton mode — if that is ever worth a sheet; S7a says the
profile axis is not where the screen is.

**S3c (PCL 5c CID device CMY): NEGATIVE — screened exactly like the
PostScript path, and M worse.** Screen map (`screen-map-S3C.log`): 165 lpi
G 598 (S1 462), 212 lpi B 635 (S1 1240), mean R/G/B 128.5 / 129.9 / 119.2
— the page is more yellow than S1 everywhere (W state B 136 against 148,
Y state B 110 against 123), i.e. the CID route lays MORE yellow, not a
cleaner one. Spectrum (`measure/e041_spectrum.py`, `spectra-offband.log`,
a 2048-px window at scan (13000, 4500)): the same lattices as S7b — R 164 lpi
+14° ×2198, G 164 lpi −14° ×3460, B 211 lpi +45° ×3941. GT comparison
(`gt-compare-S3C.log`, orientation rot180 — the sheet was laid the other
way): d' C 4.22 / M 1.83 / Y 1.66, hard error 5.4 / 23.2 / 22.3 % (S1 5.37 /
3.15 / 1.92; 7.0 / 15.3 / 28.7 %); the band at content column 12 (M 3.19 /
Y 3.01). The CMY state reads 91 / 110 / 100 — the same composite as S1's
100 / 111 / 117, NOT a neutral K: the three-toner "black" is three
toners, no K substitution on this route either. So PCL 5c device CMY
enters the same colour pipeline as PostScript DeviceCMYK and comes out of
the same screens; what differs is a yellow-heavier tone mapping. The -3U
palette form (S3) would render identically in gpcl6 and there is no
reason left to print it.

**S9 (PCL XL 3.0, eRGB corners, eNoTreatment, SetHalftoneMethod eHighLPI,
every disable): DIFFERENT — the first job whose halftone selection reached
the engine, and still screened.** The operator's eye said "very different";
the instruments say: (1) the 165 lpi ±14° screen is ABSENT over the whole
page (screen map 5.6 in every channel and column = the noise floor; S1 462;
`screen-map-S9.log`); (2) in its place a FINER screen set at 188 lpi: R
(cyan) 188 lpi +71° ×5451–7823, G (magenta) 188 lpi −71° ×8052–9807 with its
second axis 189 lpi +18° ×1727–2949, B 188 lpi −71° and the old 212 lpi
±45° family at ×1252–1677 (yellow stays on the 45° screen, 6× weaker than on
S1: screen map B 211 against 1240); 266 lpi ±63° side peaks
(`spectra-offband.log`, both windows); (3) the page is lighter in every
channel (mean R/G/B 146.0 / 144.7 / 139.5 against S1's 131.8 / 125.2 /
129.0; whites 188 / 169 / 156 against 175 / 152 / 148); (4) cyan is the
crispest of the campaign — d' 5.29, hard error 2.1 % (S1 7.0 %), C cells
R 93 on whites of 188; (5) magenta is WASHED OUT — d' 1.69 (S1 3.15), hard
error 21.4 %, M cells G 139 on whites of 169; (6) yellow as before — d' 1.74
(S1 1.92), hard error 22.8 %; (7) the overlap tax halves (C under M: R 93 →
103, S1 77 → 97); (8) the band is at content column 12 as on every sheet
(M d' 2.61, Y 2.98 against 1.7 beside it), and on this sheet it is DARKER
than its surroundings in all three channels (mean 135 / 134 / 130 against
146 / 145 / 139) with the 212 lpi residue gone inside it (B 22 against
~200) — the same "more toner on the dots" signature, now visible as
darkness because the rest of the page is lighter. In the 2400 dpi crops
(`maps/spectra/S9-w0-crop.png` against `S7b-w0-crop.png`) the grain is
finer, individual small dots stand apart and more paper shows between
them, where S7b's clusters merge into blobs. Reading: `SetHalftoneMethod
eHighLPI` selected the engine's high-lpi screen set (188 lpi) in place of
the 165/212 lpi set the PostScript path uses — the FIRST job-level
halftone control on this engine that changed what reaches the drum (every
PostScript door left the screen untouched). It is still a screen, and M
pays for the finer clusters. The decisive sheet is now S9b: the same job
with a DOWNLOADED 1x1 threshold matrix (0x80) as the halftone method — if
the engine takes a downloaded matrix the way it took the eHighLPI
selection, the page binarises; the spec lets a device read the matrix and
ignore it, and that is what the sheet measures. Also owed from S9: whether
the PJL `BITSPERPIXEL=1` on this job did anything (no separate control —
a S9 without it is one sheet).

**S8 (F turned 180° on the same device pixels): THE BAND IS THE ENGINE'S —
fixed to the paper, not to the content.** GT comparison
(`gt-compare-S8.log`; the scan reads rot180, i.e. the sheet lay on the glass
the same way round as S7a/S7b): the band is at CONTENT column 11 — M d'
4.34 / Y 2.95 at column 11 against 3.15 / 1.96 at column 12 and ~3.2 / 1.9
elsewhere — exactly the paper-fixed prediction (the refuter's §041.2
arithmetic: paper 108–113 mm mirrors onto content column 11). Screen map
(`screen-map-S8.log`): in SCAN space the band stays at block 12, 108.4 mm
(165 lpi G 97 against 430–550 beside it), where S7a/S7b had it on the same
glass orientation. Both readings agree: whatever the content, the engine
renders a 4–5 mm stripe at one x on the paper at high contrast. Everything
else on S8 is S1: 165 lpi G 426 (S1 462), 212 lpi B 1118 (1240), mean R/G/B
131.7 / 125.5 / 127.5; d' C 5.09 / M 3.12 / Y 1.91, hard error 6.6 / 15.8 /
27.7 %; per-state means within 3 levels of S1 — the 180° CTM changed
nothing in the rendering. The lateral M/Y gradient also stays with the
paper (scan-space mean B 123 → 130 left to right on this glass
orientation, as S7a/S7b). Eight sightings now (F ×3, S1, S6, S7a, S7b, S8),
one paper x, two contents: the "content-driven" reading is dead. What the
band IS remains open — a transfer-nip or ITB feature at that x is the
working hypothesis; the fuser is unlikely (gloss), not excluded. It is not
a lever we can reach from a job (S6, S7 say so).

**S9's other marks (operator, by eye: "a second darker vertical band at one
page border, horizontal bands at varying thickness and length at the top
and bottom"; measured 2026-10-05 00:30 — 1 mm and 0.25 mm profiles in
`fine-profiles-S9-S7b.log`, maps `maps/S9-{top,bottom}40mm-{R,G,B}-0p25mm.png`
and `S9-whole-G-1mm.png`, S7b beside them):** (1) the border band is REAL
and sharp — the field's first 3 mm at the content's left edge read G 122
against 136–138 from 4 mm inward (15 levels, the central band's own depth),
where S7b has 117 against 119–121 (3 levels, the ordinary edge roll-off);
it sits on the M/Y-dense side of the lateral gradient (S9 G 136 → 143 left
to right at 1 mm resolution, S7b 119 → 125) and, like the central band,
shows as darkness because the rest of the page is lighter. (2) The
horizontal bands are at the scanner's floor: with every vertical structure
removed, the 0.25 mm row means over the top and bottom 40 mm have a sd of
0.8–1.5 levels per channel; the only rows beyond 3 sd are −3 to −6 levels
(1–2 % of reflectance), ≤ 0.5 mm thick, at 1.3, 4.3, 7.6 and 24–27 mm from
the field's top and 37.8 mm from its bottom (G and B; R only at 1.3 and
24.6 mm) — faint full-width lines; no band of a millimetre or more
anywhere; the blank margins above and below the field are flat (231–236)
to the paper edge. What the eye reads as bands is either these 1–2 % lines
(the eye integrates a full-width line that a row mean dilutes) or a
gloss/texture structure the flatbed's diffuse light does not return — a
raking-light photograph would tell; the 2400 scan cannot. Neither mark
touches the cells: S9's per-column error profile is flat outside the
central band.
CORRECTED 2026-10-05 01:00 (the operator sees the bands on the sheet, no
scanner involved, and names one: "at the bottom right, from the centre
band out to the border, a 2 mm band as dark as the vertical band"): the
row-mean test above diluted a half-width band and skipped the last 1 mm.
Per 0.25 mm row and quarter of the width (`S9-bottom40mm-*`): at 1.5–2.3 mm
from the field's bottom the right two quarters read G 130–139 against
143–148 on the left two — a band ~1 mm thick (0.25 mm sampling), right
half only, starting at the central band, 10–15 levels deep = as dark as
the central band; at 1.3 mm from the top the right quarter reads 133
against 141–148 (a thinner piece, top right). So the eye is right and the
first instrument pass was wrong: the pieces are real, at the field's
edges, of different thickness and length, and the "floor" statement is
withdrawn.

**Are the dark pieces unscreened pieces? (operator's reading; measured
2026-10-05 00:50 with a third instrument, `measure/e041_screen_fine.py`,
whose CALIBRATION WAS WRONG — the correction and the valid measurement
follow this paragraph, which is kept as written:
in 128-px blocks at 0.68 mm steps, the strongest off-axis peak in the
140–240 lpi annulus over the annulus median — ANY screen, not the two
known lattices; `fine-screen-*.log`, maps `maps/*-fine-screen.png`,
`*-fine-mean.png`).** Calibration: a pixel-scrambled copy gives 7 (noise);
an UNSCREENED print — the AltaLink's sheet H, c2-cmy8 r0850, 2400 — gives
20 flat across the page (`fine-screen-altalinkH-G.log`; the cell structure
itself leaves that much), so 20 is "no screen" on a real print. Field
medians: S7b 29, S9 32, S1dash 37, S9b 81. In the central band: S7b 24,
S9 24, S1dash 27, S9b 33 — against 30–40 (S7b/S9/S1dash) and 85–90 (S9b)
beside it. In S9's bottom-right piece the right-half row median falls to
25–28 (from 31–34) while the block mean falls to 139 (from 147). Reading:
in the dark pieces the screen's periodic energy drops to within a few
points of the unscreened control (on S9b from 88 to 33, four fifths of it
gone), and the 2048-px band spectra of S7b/S9/S3c show the same: 165 lpi
peaks at ×30–100 inside the band against ×1,400–3,500 outside. The
operator's reading stands in substance — the dark pieces are where the
screen is (nearly) NOT applied and the cells print solid: dense ink, clean
whites, the lattice gone — which is also why M and Y certify there and
nowhere else on F, and why e038 measured M 8 % / Y 10 % hard error inside
the stripe against 15 / 20 % outside. What this says about the mechanism:
a transfer nip cannot remove a lattice; a stage that applies the screen
to some regions of the page raster and not to others can — and HP has
patented exactly such a stage: US9171239B2 "Processing image data strips
in columnar regions" (overlapping left/middle/right column regions, each
through RGB→CMYK conversion, scaling, enhancement and halftoning, state
saved and restored between columns, overlaps cropped and stitched; laser
printers named, the M281 and the column width not — the outside
reviewer's find, 2026-10-05 03:00); a boundary or state-restore fault in
that pipeline gives a narrow vertical region at a fixed raster x and odd
pieces at the top and bottom of adjoining regions — the central
band (fixed raster x, every sheet since e038), the 3 mm left-edge strip
(S9), the top-right and bottom-right pieces of different thickness and
length (S9) look like the footprint of the engine's video-path halftoner
missing pieces of the page: a DIGITAL artefact of the rendering/exposure
pipeline, not a physical one. S8 cannot separate the two (a raster
position is as paper-fixed as a nip); the "transfer nip" paragraphs above
are superseded by this reading, which is now the working hypothesis. Why
M and Y inside the band still read 8–10 % and not C's 2 % is open.

**CORRECTION 2026-10-05 02:10 — the fine map's generic annulus metric is
NOT valid at the c3 pitch.** Its "unscreened = 20" came from a c2 AltaLink
print; the same metric on an UNSCREENED c3 AltaLink print (e032's
c3-cmy7, `scratch/in/xerox-canon-c3-cmy7-2400dpi.tiff`,
`fine-screen-altalinkC3cmy7-G.log`) reads 34 flat across the page — the
same as S7b (29), S9 (32) and S1dash (37). The c3 cell pitch (200 lpi)
sits inside the 140–240 lpi annulus; its sinc nulls pull the annulus
median down and inflate the ratio whether or not a screen is present (the
readout builder measured the same on synthetic cells: 62 for ideal 12-px
cells, 7 for noise). So every fine-map number in the paragraph above and
the "within a few points of the unscreened control" reading are VOID; the
instrument stays in measure/ as a tool for c2 prints and as the record of
the mistake. The LATTICE-SPECIFIC measurements were never affected (the
coarse screen map and the 2048-px spectra read peaks at known frequencies
AND angles, which no cell grid produces), and the question was re-measured
the valid way: the known lattice's peak over its own ring median in
1.0 mm windows (96 px; S7b: 165 lpi ±14° in G, 212 lpi ±45° in B; S9:
188 lpi at −71°/+18° in G and +71°/−19° in R, 212 lpi in B; the floor of
this statistic is ~5–6, e.g. S9's absent 212 lpi reads 5–7 everywhere),
means over 21–39 windows:

| where | S9 188 lpi G | S9 188 lpi R | S7b 165 lpi G | S7b 212 lpi B | mean G (S9 / S7b) |
|---|---|---|---|---|---|
| central band (103 mm) | 5.9 | 4.6 | 6.5 | 12.4 | 127 / 121 |
| beside it (90 / 125 mm) | 19.4 / 18.3 | 11.5 / 13.3 | 13.0 / 14.1 | 24.0 / 25.7 | 145–147 / 126–128 |
| bottom-right piece (1.9 mm up, right half) | 6.9 | 3.7 | 6.3 | 10.7 | 135 / 130 |
| same row, left half (no piece) | 17.3 | 9.5 | 8.2 | 20.1 | 146 / 127 |
| 5 mm and 9 mm up, right half | 15.7 / 15.9 | 17.5 / 14.6 | 14.4 / 14.3 | 21.3 / 16.5 | 146 / 128–130 |
| S9 left strip (1.5 mm in) | 5.6 | 3.9 | — | — | 121 |
| S9 8 mm / 20 mm in | 13.3 / 15.2 | 9.3 / 9.2 | — | — | 139 |

In every dark piece — the central band, S9's 3 mm left strip, the
bottom-right piece on BOTH sheets — the engine's own lattice falls to the
floor of the statistic (5–7 against 13–19 around it); on S7b the yellow
45° screen only halves (10.7–12.4 against 20–26). The operator's reading
stands, now on valid evidence: the dark pieces are where the screen is
not applied (M/Y cells solid; Y partly), and the mechanism reading
(a stage that screens some regions of the page raster and not others —
digital, not a nip) stands with it. Lesson for the record: a generic
"any periodic structure" statistic must be calibrated at the SAME cell
pitch as the print it judges; the lattice-specific one needs no such
calibration.

**S9b (S9 with a DOWNLOADED 1x1 threshold matrix, 0x80, as the halftone
method): NEGATIVE as a bypass — the matrix is ignored, and the selection
falls back to the PostScript screen set at full strength.** Screen map
(`screen-map-S9b.log`): 165 lpi G 1,780 (S1 462, S9 5.6, S6 1,856), 212 lpi
B 704; spectra (`spectra-S9b.log`): R 164 lpi +14° ×5,620, G 164 lpi −14°
×9,731, B 211 lpi +45° ×4,738 — exactly S6's picture, the 188 lpi set of S9
gone; fine map median 81 (S9 32). The page is lighter still (whites
181/167/167); the GT comparison (`gt-compare-S9b.log`, rot180 on the
glass): **C d' 6.27, hard error 0.7 % — the best cyan in the record (S9
2.1 %, S1 7.0 %); M d' 1.66 / 21.4 %; Y d' 1.56 / 26.3 %**; band at content
column 12 (M 2.78 / Y 2.81); M/Y registration against C 0.3–0.8 px (every
other sheet 5.8 px, 0.06 mm — noted, not explained). Per-state: W 181/167/
167, C 79/142/164, M 184/127/145, CM 89/116/148, Y 183/167/135, CY 86/142/
140, MY 184/125/120, CMY 86/105/114. Reading of S9 + S9b together: PCL XL
`SetHalftoneMethod` SELECTS between the engine's screen sets (eHighLPI →
188 lpi; a user matrix → the default 165/212 set, strong) and nothing
downloads; the eRGB → engine conversion gives cyan its full 255 (hence
0.7 %) but leaves magenta and yellow partial, so they are screened and
wash out whichever set is chosen — the cells' G/B contrast is S1's (M Δ40
vs 46) but their spread doubles (ink sd 27 vs 18). The PCL XL route is
therefore: a near-perfect C plane, two screened M/Y planes, a selectable
screen. Open on this route: whether a palette with magenta/yellow NOT at
the RGB corners (e.g. (255,0,255) replaced by whatever the engine maps to
255 M alone — a probe page of candidate RGB values per toner would tell)
reaches full M/Y; and the PJL BITSPERPIXEL=1 ablation.

**S1dash-notriple (the cmy7/cmy8 session's sheet, S1's route, triples
removed from the payload; measured here for screening only, 2026-10-05
01:00):** screened exactly like S1 — screen map 165 lpi G 569 (S1 462, F
470), 212 lpi B 1,286 (S1 1,240); spectra the same lattices (R 164 lpi
+14° ×1,390–1,800, G 164 lpi −14° ×3,900–4,400, B 211 lpi +45° ×6,700–9,800)
— no new lattice, nothing missing; fine map median 37 (S1-class);
whole-field mean R/G/B 133.1 / 123.5 / 137.0 against S1's 131.8 / 125.2 /
129.0 — the removed triples leave the page 8 levels bluer (less yellow)
and slightly less green; the band at block 12 as always (165 lpi G 124
against 570–670). Removing the triples does not change what the engine
does to the page; the cell-level reading against its own GT
(`S1dash-notriple-gt/page000_gt.npy`, `gt-compare-S1dash.log`) is that
session's to judge.
RULING (operator, 2026-10-05 ~02:20): cmy7 — and the triple-free variants
with it — is a DEAD END on this engine; that line is closed. The S5
alphabet sheet (cmy8 + cmy7 rows) is withdrawn from the hold list.
Fallback named for the case that colour cannot be made to work at all: a
cmy4-class alphabet (white + the three single toners, no overlap states),
for which the cmy7 session's independent-plane generation findings keep
their value — not yet.

## 041.5 S10p — the PCL XL RGB probe sheet (designed 2026-10-05 01:20, operator's go)

The lever S9/S9b left open: the engine's device-RGB → toner table gives
cyan its full 255 at the RGB corner (0,255,255) — 0.7 % cell error — but
magenta and yellow only a partial, screened coverage at theirs. Whether
some other RGB value reaches 255 M or 255 Y alone is a measurement, not a
guess: ONE probe sheet sweeps the values, an instrument picks the winner
per state, then S10 re-emits F through PCL XL with the winning palette.

Design (built by two Opus builders in parallel from one manifest contract,
refuted by an Opus reader before printing; generator
`experiments/041-m281-screen-routes/pclxl_probe.py`, readout
`measure/e041_probe_readout.py`): the S9 job skeleton (class 3.0, eRGB,
eNoTreatment, disables, eProcessBlack); every patch its own 1-bit indexed
image with a two-entry palette [white, the RGB]: a 93 × 93-dot square of a
seeded random c3 cell pattern (31 × 31 cells, 50 % ink — what matters is
how single cells render, not tint density) over a 93 × 24-dot solid bar
(the achieved coverage). Values: per single toner the own channel at 0 and
the two foreign channels swept 255 → 128 in steps of 16 (81) plus the own
channel at 16/32/48 (3); per overlap the free channel swept 255 → 128 (9)
against the two zero channels at 0/16/32 (27); CMY at 0/16/32 grey; white
once — 337 values, each under THREE halftone methods (the untouched
default, eHighLPI as S9, the 1×1 matrix as S9b), the eight exact corners
replicated at four more slots each, and riders under the default method:
the corners as VECTOR fills (object type), in eSRGB (the colour-managed
reference), and with SetNeutralAxis eTonerBlack (K or composite for the
triple). Layout: 5.5 × 6.5 mm slots by a seeded shuffle inside x ∈ [12, 98]
∪ [118, 198] mm and y ∈ [12, 285] mm — the engine's rendering stripe at
98–118 mm, the 3 mm edge strips and the top/bottom 12 mm EXCLUDED so a
value and a position cannot be confused; five solid (0,0,0) fiducials
(a scratch sheet may carry them, DESIGN R3) for the readout's affine.
Readout per patch: solid-bar RGB; the pattern registered to its seed by
cross-correlation and sampled per cell → own-channel d' and hard error;
foreign-channel contamination against the page white; lattice energy in
the 140–240 lpi annulus (20 = unscreened print, 7 = noise, 30–90 = the
engine's screens). Winner per state = the RGB with the highest own-channel
d' and contamination and lattice at their floors; cyan at its corner is
the built-in positive control and must top its table. Outcomes: a palette
that reaches full M and Y → S10; or a measured cap below 255 for M/Y at
every RGB in the swept neighbourhoods → a coarse global RGB grid is the
next search, and only its failure closes PCL XL as a colour route. The
solid bar beside each pattern separates WHERE a cap sits: bar solid but
cells screened → a small-mark or spatial stage; both partial across the
neighbourhood → an endpoint limit in the separation; a displaced RGB
fixing both → a usable inverse mapping whatever the cause. Round 4 adds
24 ENCODING riders at the eight corners (4-bit indexed with S9's palette,
direct 8-bit RGB, direct 1-bit-per-component RGB; X20 p. 85/177) so the
sheet's own anchors tie back to S9's one large 4-bit image: the sweep is
small 1-bit indexed images, and a corner that behaves differently from S9
would otherwise be ambiguous between value, encoding and object size.

**Build record (2026-10-05 01:20–03:00, three refutation rounds before
paper):** generator `pclxl_probe.py` (imports S9's encoders, parser and
render from `pclxl_bilevel.py`; every patch one e1Bit indexed image with a
two-entry palette, 93 × 117 dots — pattern over bar; the vector riders
draw the full pattern as one Rectangle per run of inked cells, 1,925 in
all; five raster fiducials; 1,218 slots, seeded shuffle 41, pattern seed
41000 + id); readout `measure/e041_probe_readout.py` (five-fiducial
similarity fit under either orientation, refuses above 0.3 mm residual;
per patch the solid-bar RGB, the pattern registered to its seed by FFT
cross-correlation and sampled per cell → per-channel d' and hard error,
foreign-channel contamination against the patch's own white frame, the
lattice statistic beside a shuffled control; ranking per (target, method,
kind) by own-channel d', lattice and contamination printed, never sorted)
with `measure/e041_probe_synth.py` painting any manifest into a posed,
blurred, noisy 2400 dpi scan — smoke-tested on the full layout under
rot180 + shift + 0.3° + 0.4 % scale + blur 3 px + noise 8: 5/5 fiducials,
0.002 mm residual, 1,147/1,147 read, 0 own-channel hard error, RGB to the
unit, contamination within 1 of construction. Round 1 (generator built,
refuter NOT refuting the bytes but naming two must-fixes): gpcl6 keeps the
brush across SetColorSpace against X20 p. 85, so the vector riders' white
brush had rendered 737 later patches white — fixed by a black brush after
every vector patch; eSRGB is in no spec (gpcl6 accepts ColorSpace value 6
only); must-fix 1: the eSRGB riders sat before two thirds of the sheet and
each took a SetColorTreatment whose precondition is eRGB (X21 p. 22) — an
engine error there (ErrorReport eBackChAndErrPage aborts the job) would
have lost 748 scattered patches; must-fix 2: adaptive halftoning, trapping
and neutral axis were set once per page while X30 p. 10–11 gives them the
same per-colour-space postcondition the generator already honoured for
the treatment — S9's full control block now follows EVERY SetColorSpace
(1,153 of them). Round 2 added the treatment witness (14 patches, kind
treatdefault: the corners and six mid values with NO SetColorTreatment,
from an outside reviewer's note) and moved eSRGB last; the refuter
confirmed every byte, geometry and render claim again and REFUTED the
witness: ColorTreatment is persistent graphics state (X21 p. 24 default
eScreenMatch, X30 p. 5; SetColorSpace resets only pen and brush, X20
p. 85), so a witness emitted after the matrix1x1 PopGS inherits the
eNoTreatment of the last vector rider — null by construction, and the
generator's own verifier could not see it because it had written the
wrong model (treatment cleared on SetColorSpace) into its checker. Round 3: the
witness group moved to the head of the page (ops 3–114, before the page
head's first SetColorTreatment at op 116 and the first SetHalftoneMethod
at op 5581), the verifier rebuilt on the spec's persistent-state model
(16 verdicts, 10 mutation tests including the previous build's order —
the new verifier FAILS the previous build with 14 treatment mismatches,
as it should); job sha `d7dd4ac9b6f00990…`, 1,749,666 B, same byte
multiset as round 2, render sha `bfb9e25b…` unchanged, every patch field
unchanged; the refuter's third pass, with its own tokenizer, state trace
and render: NOTHING TO FIX. Round 4: the 24
encoding riders at the eight corners (kinds enc4bit / encdirect8 /
encdirect1 — eIndexedPixel e4Bit with S9's 16-entry palette, byte-identical
to the palette in S9's own printed stream; eDirectPixel e8Bit; eDirectPixel
e1Bit, 3 bits per pixel MSB-first R,G,B, rows padded to 4 bytes per X20
p. 179: 48 / 280 / 36 B per 93-px row) in the DEFAULT group under
eNoTreatment; the verifier decodes every image under its own encoding
with its own decoder, 12 mutation tests (a direct1 row padded to 35 B and
a wrong palette index are caught); gpcl6 accepts all three and renders
0 differing dots; the fourth refutation (own tokenizer, decoder, state
walker, render, slot grid; the 24 rider spans cut out of the new stream
leave the previous job byte for byte): NOTHING TO FIX. FINAL JOB:
`S10p-pclxl-rgb-probe.pclxl` 2,092,746 B, sha
`0e2f5e5fb1f921aed042895f1903210ef5f451fc4e5b42bf63d796a11c987c2e`,
manifest `aefbfcef…`, 1,171 patches + 5 fiducials (default 433 / highlpi
369 / matrix1x1 369; pattern 1,107, vector 8, srgb 8, tonerblack 10,
treatdefault 14, enc4bit 8, encdirect8 8, encdirect1 8; 47 slots free),
13,242 operators, render sha `e156780d…`. Advisory accepted as an
ASSUMPTION rather than a fifth round: S9 itself printed under eHighLPI,
and the encoding riders sit under the default method only, so the tie
back to S9 assumes the encoding effect does not depend on the halftone
method (the indexed1 corners under highlpi, 5 replicates, carry the
method half of the comparison). The W corner's three encoding riders
carry no pattern (ink = blank = white) and are checked as all-white. The
M281's bit and component order for direct 1-bit pixels is unspecified
(X20 is silent); a different reading prints visibly garbled, not
ambiguous.

**ON THE PRINTER (2026-10-05 10:20 / 10:40): the four-times-refuted job
CRASHES THE FORMATTER.** First send: "Dokument wird gedruckt" for two
minutes, then Ready with the page count unchanged — page discarded, no
error sheet. Second send with the back channel held open: HP 49 SERVICE
ERROR, power cycle, nothing on the back channel. Every refutation round
checked the job against the SPEC and against gpcl6; none asked the
question that mattered — how far the stream strays from what THIS
firmware has demonstrably accepted (S9/S9b: one page, one SetColorSpace,
one 4-bit indexed image in 64-row blocks, one halftone setting). The
crashed job had 1,168 images each with its own colour space, palette and
control block, three PushGS/PopGS pairs, 1,933 vector rectangles, a
colour-space value no spec lists, 1-bit and 8-bit direct-pixel images and
369 repeated dither-matrix downloads. Which of these the M281 cannot
digest is unknown and will not be bisected on its firmware. LESSON for
the record: a job for an engine with a crash-prone formatter is designed
by NOVELTY BUDGET — enumerate every operator, attribute, value and
structure not present in a stream that printed, keep that list to what
the experiment needs, and have the refuter audit that list, not only the
spec. Round 5 (running): the same sweep rebuilt as `pclxl_probe_banded.py`
— no position replicates (337 values × 3 methods + the 14 witnesses =
1,025 patches), NINE band images of four slot rows (8-bit indexed, 768-byte
palettes, ≤ 114 colours each, methods interleaved D,H,M / M,D,H / H,M,D
over the page) plus the witness band drawn first, the default bands drawn
before any SetHalftoneMethod, eHighLPI set once, the matrix once, no
PushGS, no vector / sRGB / toner-black / direct-pixel riders; the novelty
list against S9/S9b computed by tokenizer diff and refuted as the first
priority. The wrapper `scripts/print_plane.sh` on this branch now takes
`PRINT_NC_WAIT` and `PRINT_BACKCHANNEL` to hold the socket and capture the
back channel (an error report that arrives after 10 s idle was lost).

`pclxl_probe.py` (1,163 lines, over the 1,000-line split signal) stays
whole as the dated record of the job that crashed the formatter (HP 49),
the evidence behind the novelty-budget rule; owner, 2026-10-08: "keep the
pcl probe". It is also a live dependency: `pclxl_probe_sheets.py`,
`pclxl_probe_banded.py`, `pclxl_mixture.py` and the five PostScript
generators (`ps_layouts`, `ps_mixture`, `ps_reset`, `ps_scale`,
`ps_trigger`) import its constants and helpers (`DPI`, `mm`, `dots`, and
for the PCL XL drivers the slot grid, patterns and patch raster).

Round 5 result (`pclxl_probe_banded.py`, 902 lines): 13 e8Bit indexed
images (witness band, three fiducial strips, nine bands of 577–578 rows ×
4,286 dots in 64-row blocks), 166 operators, 23.5 MB (S9 15.5 MB — e8Bit
for ~24 % fewer pixels), palettes ≤ 114 of 256 used, sha `5d1f52c0…`;
gpcl6 0 differing dots over all 1,025 patches; the NOVELTY against
S9/S9b computed by tokenizer diff and confirmed by the refuter's own:
ColorDepth e8Bit, a 768-byte palette (uint16 array length), several
images with their own SetColorSpace and cursor, two halftone settings in
one job issued after images, the untreated witness first, short last
blocks — no new operator, no new operator×attribute pair. The refuter:
crash risk none beyond that list; ONE ambiguity — the four-op control
block was issued once after the witness while twelve later images had
bare SetColorSpace calls; X21 p. 22 / X30 p. 9–11 tie the controls to the
current colour space and S9's own order was SetColorSpace → controls →
image, so a firmware that resets on SetColorSpace would print every band
under its defaults and void the witness. Round 6 (running): every image
carries S9's preamble in S9's order, the band's halftone method re-issued
per band (three matrix downloads instead of S10p's 369), and — the
owner's fallback — a `--only M` form (84 magenta values × 3 methods + the
C corner and W as controls + a 3-patch witness; seven images: witness,
three fiducial strips, three bands) built and verified beside it, to
print only if the full sheet fails.

Round 6 result: every image after the witness carries S9's preamble byte
for byte in S9's order (SetColorSpace, treatment, adaptive, trapping,
neutral axis, then S9's eHighLPI bytes or S9b's matrix bytes per band);
the state at every image is identical under the persistent model, the
reset-controls-on-SetColorSpace model and the reset-everything model; the
five control-placement bigrams of round 5 are gone. Full sheet
`S10p2-pclxl-rgb-probe.pclxl` 23,473,742 B, sha
`3bfe4add94c3a493f9504155df6855bae13aff8547111b6d2ba1c5d274b744e1`, 13 images,
214 operators, render sha `4a5ac538…` (unchanged from round 5); M-only
`S10p2M-pclxl-rgb-probe-M.pclxl` 8,605,258 B, sha `876382e236819067…`, 7 images,
261 patches. Novelty against S9/S9b, confirmed by the refuter's own
tokenizer: e8Bit, the 768-byte palette with its uint16 length, three
bigrams inherent to several images and the untreated witness, the
allowed structures, plus two the refuter added — row padding exercised
(4286 → 4288 bytes; S9's 2,304-byte rows needed none; spec-mandatory) and
blocks up to 293 KB (S9 147 KB). Refuter: nothing to fix. Readout note
from it: S9b found the downloaded matrix ignored, and on this sheet the
matrix bands follow highlpi bands, so an ignored download may leave them
under highlpi rather than the default — the readout compares each matrix
band with BOTH other methods instead of assuming either.

**S10p2 READOUT (scan 11:40, `measure/e041_probe_readout.py`, 5/5 fiducials,
residual ≤ 0.12 mm, 1,021 of 1,025 patches registered, page white
230/231/233): THE RGB TABLE WAS NEVER THE CAP — every state prints nearly
bit-faithfully in isolation.** Corner anchors, own-channel d' / hard
error / solid-bar level:

| state (corner) | default | eHighLPI | matrix | on the full S9/S9b page |
|---|---|---|---|---|
| C (0,255,255) | 8.17 / 0.0 % / R 50 | 7.28 / 0.1 % | 6.75 / 0.3 % | 2.1 % / 0.7 % |
| M (255,0,255) | 5.40 / 0.6 % / G 81 | 7.38 / 0.0 % | 7.73 / 0.0 % | 21.4 % / 21.4 % |
| Y (255,255,0) | 6.13 / 0.3 % / B 90 | 6.17 / 0.5 % | 6.82 / 0.2 % | 22.8 % / 26.3 % |
| CM (0,0,255) | 5.16 / 1.1 % | 4.90 / 1.1 % | 4.95 / 1.0 % | — |
| CY (0,255,0) | 5.68 / 0.7 % | 5.80 / 0.4 % | 3.96 / 2.5 % | — |
| MY (255,0,0) | 5.58 / 0.8 % | 4.64 / 1.9 % | 4.91 / 0.7 % | — |
| CMY (0,0,0) | 4.77 / 2.3 % | 5.87 / 1.0 % | 4.89 / 2.2 % | — |

The sweep around the corners moves d' by at most ~2 (M best (240,0,208)
9.04 default, (240,0,240) 9.40 highlpi; Y best (224,240,0) 8.42; C best
(0,240,176) 9.03) with no value a cliff — the off-corner winners add a
little of a third toner (e.g. (255,0,160) = M + some Y) and their small
marks lose less density than the pure corner's (M cells G 88 against the
corner's 108 at the same solid-bar level 73–81); worst anywhere are the
own-channel-at-48 values, 2–9 %, as expected. No position dependence:
band means of d' for C 6.8–7.3, M 6.5–7.0, Y 6.3–7.0 over all nine bands,
top to bottom, under all three methods. Treatment witness against its
eNoTreatment twins: within ±1 d' either way (M 5.80 vs 5.40, Y 7.29 vs
6.13, C 8.04 vs 8.17, CY 4.46 vs 5.68) — eNoTreatment does nothing
measurable on single-colour marks. Method: for M the two non-default
methods beat the default (7.4–7.7 vs 5.4), for C the default is best; the
matrix bands behave like a method of their own (CY corner 3.96 there), so
whatever state they printed under, it is not simply highlpi. In the 2400
dpi crops (`scratch/e041/probe/S10p2-crops.png`) the magenta and yellow
cells are crisp squares on clean white.

**What this means.** S9 printed the SAME eight RGB corners, through the
same PCL XL path, with the same controls, and read M at 21 % and Y at 23 %
cell error; the probe reads them at 0–0.6 %. The difference is not the
value, not the treatment, not the method, not the position on the page,
and not the encoding (8-bit indexed here, 4-bit there — the cyan corner
reads 0.0–0.3 % under both). It is what surrounds a cell: on the probe
every patch is ONE state on white (50 % of its cells inked with one
colour); on the data page every cell's neighbours are other states and
the planes overlap. The engine's degradation of M and Y is a NEIGHBOURHOOD
effect — a stage that acts on colour mixtures or colour edges (the
colour-to-colour processing the pipeline applies to multi-colour
regions, or a physical interaction of adjacent toners), not a per-pixel
table. The 'overlap tax' measured on S1/S6/S9 (C alone R 77, under M 97,
under M+Y 100) was the first sighting of the same thing. Consequence for
the plan: S10 (F through PCL XL with a 'better palette') would change
nothing — the full-page corners are already the values that print
perfectly in isolation; the next probe varies the NEIGHBOURHOOD, not the
value (see §041.6).

**REFINED by the operator's eye and the SOLID BARS (2026-10-05 12:30).** The
operator read the crops: the magenta corner "shows screening in the solid
block and above", (240,0,208) "looks almost solid", cyan solid, yellow
solid but splotchy, blue "clearly screened, two colours, red channel
displaced", red "orange, vertical striping", CMY "three toners, not K".
The pattern squares cannot settle solid-vs-screened (the c3 cell grid
confounds any lattice statistic), but every patch's SOLID BAR is a uniform
93 × 24-dot area where the engine's lattice (165 lpi ±14°, 188 lpi ±71°/
±19°, 212 lpi ±45°, each at its known frequency AND angle, peak over ring
median in 96-px windows, own channel) is a clean test: scrambled control
5.9 (p98 8.8), white paper 19, so ≤ 18 = unscreened (`S10p2-bar-screen.json`,
bar crops `probe/S10p2-bars.png`):

| state | corner bar | unscreened values exist? | least screened, default |
|---|---|---|---|
| C | 7 / 12 / 6 — SOLID | yes: the whole G = 255 row and most of G ≥ 224 | (0,255,160) 4, (0,224,255) 6 |
| M | 66 / 118 / 60 — SCREENED | yes: R ∈ {240, 255} × B ∈ {128 … 192}, 16–20 of 84 | (240,0,176) 4, (255,0,160) 5, (255,0,144) 5, (240,0,192) 7 |
| Y | 11 / 12 / 13 — SOLID | yes: the whole R = 255 row, most of R ≥ 224 | (255,192,0) 6, (240,240,0) 7 |
| CM | 230 / 222 / 169 — SCREENED | NO (min 26–29, the dark blues) | (0,0,160) 26 |
| CY | 52 / 41 / 23 — screened | NO (min 23–26) | (0,224,0) 26 |
| MY | 15 / 18 / 22 — borderline | the corner only | (255,0,0) 15 |
| CMY | 37 / 42 / 60 — screened | NO | — |

(scores default / eHighLPI / matrix). Reading: on this engine's RGB path a
SINGLE toner can be laid solid — cyan and yellow at their corners, magenta
NOT at its corner (the engine maps (255,0,255) to a partial, screened M)
but at a displaced value that adds a little yellow: (240,0,192) is the
mildest solid magenta (bar G 71 against the corner's 81, cells G 87
against 108, d' 8.2 / 8.0 / 7.8 under the three methods, foreign B drop in
inked cells 96 against the corner's 80, i.e. 16 levels of yellow
cross-talk for a solid plane). The TWO-toner overlaps are screened at
every swept value (red at the corner is borderline), and the triple is
screened. This is the mechanism behind the overlap tax and behind the data
page's M/Y failure: in cmy8 the M plane is inked in the M, CM, MY and CMY
states — three of the four are overlaps, screened partial toner; the C
plane's own state is solid and its absorption strong, so C survives. The
isolation result above stands (0.6 % at the screened corner because the
half-cell centre box averages the screen), and the neighbourhood reading
stands, now with the mechanism named: a screened partial cell beside
other states is what fails on the page. CONSEQUENCE: the overlap-free
alphabet (cmy4: W + C + M + Y, no two-toner cells) printed with the solid
values — C (0,255,255), M (240,0,192), Y (255,255,0) — is the one colour
alphabet this engine can lay WITHOUT a screen anywhere; whether it
survives the mixed neighbourhood is exactly what the mixture probe
measures, and it measures cmy8 (corner palette and solid-M palette)
beside it. The operator's by-eye notes and the bar measurement agree on
every item; the one thing the eye added that the first ranking missed is
the corner magenta's screen.

**Operator's bar reading (12:45), item by item:** M corner "clearly
screened with white"; (240,0,192) "a hint of yellow in the magenta";
(255,0,160) "yellow dot pattern visible, overall more orange"; CM corner
"very red-blue screen"; MY corner "vertical orange striping, very
visible"; C corner "solid, only MIC shining through". Matches the bar
scores; the red corner's vertical line structure is a 1-D screen the
lattice set does not name, so its score of 15 flatters it. The yellow in
the solid magentas is the Y component the conversion adds, itself
screened; along the solid edge it grows as B falls — (240,0,208) score 12
is the least-yellow value that is already unscreened in G, (255,0,192)
14 and (240,0,192) 7 next; a finer sweep of B between 192 and 224 at
R 240/255 would place the edge.

**Operator's question (12:45): can the input be pre-distorted so the
screener produces exactly the bitmap we want?** Two answers. (1) The
literal inverse — choosing contone values so the fixed threshold arrays
yield a chosen dot pattern — needs each colorant's threshold array to the
dot, its phase against the page raster (the NVRAM `SMGphaseX/Y`) and its
stability job to job, none of which is measured; and for overlaps the
conversion caps both colorants near ~70 %, so a CM dot would print only
where BOTH arrays' thresholds fall under the cap — a moiré set, not a free
choice. Fragile, and unnecessary given (2). (2) The robust inverse: never
give the screener anything to screen. 0 and 255 pass the threshold
unchanged, so a page whose every pixel is WHITE or a SINGLE toner at its
solid value — C (0,255,255), Y (255,255,0), M at the solid edge — is
printed bit-faithfully (up to the small screened Y the magenta value
carries). Overlap states, if wanted at all, become DOT-LEVEL MIXTURES
inside the cell (a c3 CM cell = a 3×3 checker of solid-C and solid-M
dots, 5 + 4; CMY three-way) — the engine sees only single-toner pixels,
the receiver sees a cell with each plane at about half strength, a
deterministic state the per-state colour matrix can model, at a margin
cost the probe can price. Consequences: cmy4 (W, C, M, Y) at c3 or at
c2 becomes a 1-bit-faithful alphabet on this engine — cmy4-c2 is 2 bits
per 4 dots = 0.5 bit/dot, twice c2-K and two thirds of the AltaLink's
cmy8-c2 record — and "dot-mixed cmy8" is the candidate that keeps 3
bits/cell. Both go on the mixture probe as arms beside engine-overlap
cmy8.
 Residuals recorded, not fixable on this
sheet: the eSRGB group's halftone is the default only if the M281's PopGS
restores HalftoneMethod; no spec says whether a page that hits an error is
still ejected; the vector riders' default halftone is MediumLPI against
the raster default LowLPI (X30 p. 5), so vector vs raster confounds object
type with screen; the readout's generic lattice column is NOT calibrated
at the c3 pitch (the correction above) and is read against the sheet's own
cyan anchors; the matrix1x1 group prints under whatever halftone state
PopGS leaves (S9b says the matrix itself is ignored).

## 041.5b S11 — the mixture probe (built 2026-10-05 13:05–13:30)

Generator `experiments/041-m281-screen-routes/pclxl_mixture.py` +
`pclxl_mixture_arms.py` on the banded construction (S10p2's machinery,
S10p2's bytes unchanged — rebuilt to the same sha); readout
`measure/e041_mixture_readout.py` + `e041_mixture_synth.py` (state error by
a nearest-mean RGB classifier over the arm's alphabet, leave-one-out on
the patch and cross-replicate; per-plane d'/hard error with C→R, M→G,
Y→B, K→max(R,G,B), cells carrying K left out of the C/M/Y plane statistics;
four side-by-side comparisons: c3 vs c2, palette, neutral axis, engine
overlap vs dot mix). 22 ARMS (A01–A22: the single-toner controls {W,M}
solid/corner, {W,C}, {W,Y}, {W,K}; the pairs {W,C,M}, {W,M,Y}, {W,C,Y};
cmy4 with M-solid (240,0,192), M-solid2 (240,0,208) and M-corner at c3,
cmy4 solid/solid2 at c2; cmyk5 at c3 and c2 (K through eTonerBlack bands);
{C,M} without white; cmy8 with engine overlaps at the corner palette (S9's)
and with M-solid at c3, corner at c2; cmy8 with DOT-MIXED overlaps at c3
(CM/CY/MY a 5+4 checker, CMY 3+3+3 by (r+c) mod 3) and c2 (2+2 diagonal,
CMY 2C+1M+1Y); a cmy4 control in the toner-black bands), each at two ink
fractions (uniform; white-heavy P(W)=0.5), under default and eHighLPI,
three replicates spread over the page thirds: 258 patches, twelve band
images (process-black bands of six slot rows, toner-black bands of one)
+ three fiducial images = 15 images, 235 operators, 26,455,613 B, sha
`b89f6883b942be5cad31701f5f23c02c9fd0a6172d9d54b3b3bd949037b842b7`,
patterns npz `cdc1103c…` (258 state maps + dot-level planes). Verified:
stream read-back (every preamble byte-equal to S9's, the six toner bands
differing in the one neutral-axis byte), every band decoded == the page
composed from manifest + npz, gpcl6 0 differing dots, zones, determinism,
S10p2 and S10p2M rebuilt unchanged. NOVELTY against S10p2 ∪ S9 ∪ S9b, by
two independent tokenizers: ONE token — SetNeutralAxis value 0
(eTonerBlack) — plus allowed structure (15 images, 885-row bands). The
refuter: nothing to fix; recommendation taken: a ZERO-NOVELTY TWIN,
`S11t-pclxl-mixture-twin.pclxl`, the same bytes with the six toner-black
values set back to 1 (K arms then print as the CMY composite), kept as the
fallback if eTonerBlack brings the 49 error back. Readout smoke on the
real manifest painted at blur 3 / noise 8 / rot180 / 0.25°: 258/258
registered, state error 0 on every c3 configuration, c2 overlap arms
0.02–0.05 (blur cross-talk at 8-px cells in the synthetic).

## 041.5c S12 — the PostScript twin of S11 (built 2026-10-05 13:35–13:55)

`experiments/041-m281-screen-routes/ps_mixture.py` reads the S11 manifest
and npz and emits the SAME page as PostScript: the PJL wrapper of S1 minus
the BITSPERPIXEL/RET lines, F's setpagedevice line verbatim, a prologue
defining the HP bare names only where the interpreter lacks them (gs),
then the 15 images in S11's draw order, each inside gsave/grestore as an
8-bit `[/Indexed /DeviceRGB hival <lookup>]` image (ASCII85, white index 0
packed as `z`, 9.2 MB for 26.4 MB of raster), placed by translate/scale at
0.12 pt per dot with the row order of F's ImageMatrix; before every image
the HP controls in S11's order — `ProcBlack|TonerBlack HPImageNeutralAxis`,
`Smooth|Detail ColorSmartImageHalftone` (default → Smooth, eHighLPI →
Detail: the PPD's own halftone selection, never printed before), and, on
the refuter's finding that S11 disabled trapping and adaptive halftoning
before every image while the PS defaults leave Edge Control on, `Off
HPColorTrapping` and `false HPImageAdaptiveHalftoning` (both measured
accepted, both printed in S6) — all behind `where` guards. The ONE control
that differs from S11 is ColorSmart matching, left at the device default
(S11 ran eNoTreatment; S10p2 measured it null on single-colour marks, S6
measured matching-off as worse under DeviceCMYK) — recorded, so a colour
shift between the sheets is not read as an interpreter effect. Verified:
every image equals S11's plan image by image; gs 10.08 ppmraw render 0
differing dots against the page composed from the S11 npz AND against
S11's own gpcl6 render (7,014 common rows; PostScript's A4 is 7,016 rows,
the two extra white); ASCII85 round-trips; the stub run logs exactly four
HP calls then the image for each of the 15 images (60 calls); the byte
audit against S1/F; determinism; the mixture readout's loaders on the S12
manifest (same patches, same npz by reference; the readout's
`patterns_path` now honours a manifest's `patterns_npz.file`). Job
`S12-ps-mixture.ps` 9,185,360 B, sha
`3ec2a2ee040112dfdb1940d1cbac9f15f38bb8d41b88daa8ba40543cfd1a3826`. The
refuter (own PS parser, own ASCII85 decoder, own gs render, own stub
loggers): on image content and geometry S12 IS the S11 page; nothing
blocking; the two decisions above were its.

## 041.5d S11 READOUT (2026-10-05 13:30) — the alphabet question answered at c3, a page-scale question opened

`measure/e041_mixture_readout.py`: 5/5 fiducials, residual ≤ 0.21 mm, 258/258
patches registered (max shift 0.24 mm), page white 231/233/235. Figure of
merit = the leave-one-out state error of a nearest-mean RGB classifier
over the arm's alphabet (the cross-replicate error agrees within noise
everywhere). Means over three replicates, uniform fraction unless said:

| alphabet, cell, palette | default | eHighLPI | note |
|---|---|---|---|
| {W,M} c3, M-solid / M-corner | 0.000 / 0.000 | 0.000 / 0.000 | the probe's singles, confirmed |
| {W,C} / {W,Y} / {W,K} c3 | 0.001 / 0.002 / 0.000 | 0.000 / 0.000 / 0.000 | K through eTonerBlack prints SOLID alone |
| {C,M} c3, no white | 0.000 | 0.000 | white neighbours are not needed |
| {W,C,M} / {W,M,Y} / {W,C,Y} c3 | 0.013 / 0.006 / 0.065 | 0.001 / 0.001 / 0.023 | all the C–Y 0.065 is one right-edge replicate (0.153 at x 189) |
| **cmy4 c3, M-solid (240,0,192)** | **0.0024** (white-heavy 0.008) | 0.057 (= 0.000 / 0.046 / 0.125 at x 62 / 162 / 184) | the overlap-free alphabet survives the mixed field |
| cmy4 c3, M-solid2 (240,0,208) / M-corner | 0.003 / 0.0024 | 0.014 / 0.007 | the palette does not matter at c3 |
| cmy4 c3 in eTonerBlack bands | 0.0024 (wh 0.004) | 0.007 (wh 0.005) | eTonerBlack leaves C/M/Y untouched |
| **cmyk5 c3** | **0.006** (wh 0.009) | 0.014 (wh 0.024) | K plane 0.1–1.3 %; the fifth state nearly free |
| cmy4 c2 (solid / solid2) | 0.067 / 0.065 (wh 0.094 / 0.107) | 0.042 / 0.034 (wh 0.080 / 0.162) | see the confusion below |
| cmyk5 c2 | 0.139 (wh 0.094) | 0.261 (wh 0.113) | W↔K joins the confusion |
| cmy8 c3, engine overlaps, S9's palette | 0.040 (wh 0.031) | 0.084 (wh 0.078) | M→MY 7.9 %, CM→C 8.5 %: the overlaps lose |
| cmy8 c3, engine overlaps, M-solid | 0.127 (wh 0.091) | 0.109 (wh 0.034) | M-solid's yellow pulls M toward MY — worse for cmy8 |
| cmy8 c3, DOT-MIXED overlaps | 0.068 (wh 0.025) | 0.046 (wh 0.115) | CMY reads 75 % (→ CM/CY/MY), pairs 91–94 % |
| cmy8 c2, engine / dot-mixed | 0.320 / 0.253 | 0.297 / 0.314 | dead |

**Position (the right edge).** cmy4 c3's state error is 0.3 % over x < 100 mm,
1.3–1.9 % over 100–175 mm and 5 % over 175–200 mm, carried entirely by the
yellow plane (d' 3.2 → 1.8 left to right; C and M flat). [CORRECTED
2026-10-05 14:30, see §041.5f: this is yellow-to-cyan MISREGISTRATION
seen through a single-pose readout, not a yellow density loss; "yellow
starvation" was a wrong mechanism word — the operator sees none, and
yellow alone on white reads the same across the page.] Every high-variance
configuration in the table is one right-edge replicate (A09 highlpi:
0.000 at x 62, 0.046 at 162, 0.125 at 184; A08: 0.153 at x 189; A20
white-heavy highlpi: 0.29 at x 184; A13: 0.32 at x 179). Method: at c3
the default screen set beats eHighLPI by 2–3× on every alphabet
(0.0024 vs 0.007 on A11, 0.003 vs 0.014 on A10, 0.006 vs 0.014 on cmyk5,
0.0024 vs 0.007 on A22); at c2 eHighLPI is the better one (0.042 vs 0.067).

**c2.** The cmy4 error at c2 is one-sided: C/M/Y cells read 97.8–99.6 %
right, WHITE cells 83–87 % — a white cell between inked 85 µm cells reads
as its neighbour's colour (W → C 5.7 %, → Y 4.8 %, → M 2.5 % under
eHighLPI). That is toner spread plus scanner blur at 8 px per cell, a
CONTEXT problem, exactly what the receiver's context detector models, and
not what a context-free nearest-mean classifier can see; the 3–7 % here is
an upper bound for the production reader. cmyk5 at c2 adds W↔K (3–5 %)
and is out.

**Readout caveat.** The per-plane midpoint hard error of the Y plane reads
0.1–0.3 wherever magenta is in the alphabet, because magenta's own blue
absorption lands in the Y plane's blank class; the best-threshold column
(0.04–0.10) and the state classifier are the honest numbers.

**THE PAGE-SCALE QUESTION.** Arm A17 is S9's construction exactly — the
eight states with engine overlaps, S9's palette, c3, PCL XL — and reads
M 2.8 % / Y 10 % per plane and 4 % state error in 3.9 mm patches, where
the same content as S9's full page read M 21 % / Y 23 %. The same route,
the same values, the same cells, the same neighbourhoods inside a patch:
a 5–7× difference between a small patch on a mostly white page and a page
covered edge to edge. Whatever degrades the data page is PAGE-SCALE, not
cell-scale: either physical — the developer/transfer system starved by
~50 % area coverage on three colours across the whole page (the lateral
yellow gradient and the right-edge losses fit a supply picture) — or
digital — the formatter degrading a large incompressible raster (the
probe page is 7 % noise, the data page 100 %), which would also fit the
stripe as a processing-region seam. This supersedes the plain
"neighbourhood" reading: the neighbourhood matters (overlaps lose 4–8 %
at c3), but the full-page collapse is something else, and it may hit
cmy4 on a full page too. NEXT SHEET (S14, the SCALE probe): the cmy4-solid
and cmyk5 alphabets (c3 and c2) and the cmy8 alphabet as blocks of
growing size — 4, 8, 16, 32, 64 mm and one 100 × 100 mm block — and the
same total noise area once as many small patches with white gaps and once
as one block, placed so that the page's fill fraction varies by region;
the readout per block and per position separates contiguous-object size
(digital) from page coverage (physical). Until it is read, cmy4-c3's
0.24 % is a patch number, not a page number.

## 041.5e S12 READOUT (2026-10-05 13:45) — PostScript is as good as PCL XL, or better, for the solid alphabets

Same readout, same 258 patch ids at the same positions (5/5 fiducials,
residual ≤ 0.11 mm, 258/258 registered). Mean leave-one-out state error
per alphabet family over all fractions, methods and replicates, S11 PCL XL
| S12 PostScript:

| alphabet | S11 PCL XL | S12 PostScript |
|---|---|---|
| single toners on white, {C,M} | 0.000–0.001 | 0.000–0.001 |
| {W,C,M} / {W,M,Y} / {W,C,Y} c3 | 0.004 / 0.007 / 0.024 | 0.0005 / 0.005 / 0.003 |
| **cmy4 c3** | 0.014 | **0.0036** |
| **cmyk5 c3** | 0.013 | **0.0053** |
| cmy8 c3, engine overlaps / dot-mixed | 0.074 / 0.063 | 0.077 / 0.068 |
| cmy4 c2 | 0.081 | 0.055 |
| cmyk5 c2 | 0.152 | 0.118 |
| cmy8 c2 | 0.25 / 0.27 | 0.21 / 0.24 |

S12 is better on 110 patches, worse on 49, equal on 99. The gain on cmy4/cmyk5
is largest where S11 was weak — the right half of the page (cmy4 c3 over
x 150–200 mm: 2.8 % → 0.8 %, Y d' 2.27 → 2.67) and the finer screen (S11
eHighLPI 0.057 vs S12 Detail 0.006 on A09) — and magenta d' rises 5.3 → 6.1
everywhere. Overlap alphabets are not helped (cmy8 c3 4–8 % either way;
PostScript moves the loss from Y to M). The ONE control difference was
ColorSmart matching (left on in S12), and the solid bars show what it does:

| bar colour | lattice S11 | lattice S12 | solid RGB S11 → S12 |
|---|---|---|---|
| C (0,255,255) | 9 — solid | **160 — SCREENED** | 49/154/205 → 74/168/185 |
| M-solid (240,0,192) | 7 | 9 — solid | 217/71/121 → 217/71/126 |
| M-corner (255,0,255) | 61–76 | 95–114 — screened | |
| Y (255,255,0) | 9–15 | 9–12 — solid | |
| K, toner black | 8–9 | 7–8 — solid | 54/52/52 both |

(lattice floor ~18.) ColorSmart's default matching maps the cyan corner to
a lighter, greener, SCREENED cyan; magenta-solid, yellow and K stay solid.
Cyan has so much margin (d' ~10) that the screened cyan costs nothing in
a patch — but on a full page it is the kind of partial toner that S9
lost. Caveat: S11 and S12 were printed 20 minutes apart, one sheet each, in
the same positions — print-to-print drift is not separated from the route.
CONSEQUENCES: (1) production can stay PostScript — the generator changes
its image from 1-bit DeviceCMYK planes to an 8-bit indexed DeviceRGB
palette image, and the HP operators (neutral axis, ColorSmart halftone
Smooth/Detail, trapping off, adaptive off) go into the prologue; (2) the
cyan entry under matching-on needs either `false ColorSmartColorMatching`
(the PCL XL footing, where the corner is solid) or a displaced cyan that
matching maps to solid — a dozen values on the next sheet decide it;
(3) the S14 scale probe is built in PostScript with the solid palette and
matching off, with a matching-on arm, so it settles the page-scale
question on the production route.

## 041.5f The right-edge "yellow" effect is PLANE REGISTRATION (2026-10-05 14:30)

Operator: "yellow starvation is not a thing". Measured, S11 and S12: yellow
ALONE on white ({W,Y}, arm A04) reads Y d' 6.9 / 7.3 / 7.8 / 7.7 over x 0–50 /
50–100 / 100–150 / 150–200 mm (S12 6.9 / 7.4 / 8.1 / 7.7) — no loss to the right;
the solid yellow bars read B 87–92 everywhere. What falls to the right is
the Y plane INSIDE cmy4 mixtures (Y-cell B 110 → 127, d' 3.2 → 2.3), and the
reason is registration: per-plane cross-correlation of each plane's dot mask
against its own channel on 60 cmy4/cmyk5 patches of S11 gives Y − C offsets
of dy −1.7 / −3.2 / −3.7 / −5.0 scan px (4 px = 1 dot, 12 px = one c3 cell)
over the four x bins, single patches up to −10 to −11 px (nearly a whole c3
cell) at x 184 mm, while M − C stays within ±2 px on average. The mixture
readout registers each patch on all planes OR-ed (dominated by the dark
cyan), so yellow cells are sampled off-centre where yellow drifts — an
INSTRUMENT limitation; a yellow-only patch registers on yellow and reads
clean. Consequences: (1) every M/Y number from the mixture readout in
mixed alphabets is an UPPER bound on the error (the production receiver
fits one registration field per plane — the PAGE-FIELD line — and would not
pay this); (2) the "right edge costs 5 %" statement is withdrawn as a print
property; (3) the engine's Y-to-C misregistration of 1–2.5 dots, varying
across the page, is itself a format fact: at c2 (2-dot cells) it exceeds
half a cell, so c2 colour requires per-plane poses; (4) the readouts get a
per-plane registration step and S11/S12 are re-read before any number in
them is used for a decision.

## 041.5g Data densities, systematically (2026-10-05 14:30; CORRECTED 14:50)

600 dpi = 558 dots/mm². Cells per mm²: c1 558, c2 139.5, c3 62.0, c4 34.9. Bits
per cell: K 1, cmy4 2, cmyk5 2.32, cmy8 3 (engine overlaps or dot-mixed
overlaps: the in-cell pattern axis). Raw bits/mm² = cells × bits/cell.

CORRECTION (operator: "c3-cmy8 is at least as good as c3-K — we get C
everywhere and a few M"). The first version of this table scored every
alphabet with the Fano floor log2 M − h(p) − p·log2(M−1) on the JOINT state
error. That floor assumes a wrong cell is wrong in a uniformly random way;
for cmy8 it is badly wrong, because cmy8 is coded as three INDEPENDENT
binary planes (the presence codec, one LDPC per plane) and its errors sit
in M and Y while C stays clean — a cell with a wrong M still delivers its C
bit. The full-page cmy8 row ("32–56 b/mm², below K") came from that error.
The table now uses the MUTUAL INFORMATION of the measured hard-decision
confusion matrix (joint, uniform-fraction patches, S12 PostScript) — still a
lower bound (hard decisions, no context, single pose) — and, for full pages,
the per-plane binary capacities, which is how the cmy8 codec actually reads:

| cell | alphabet | raw b/mm² | measured | discernible b/mm² (lower bound) |
|---|---|---|---|---|
| c1 | any | 558–1674 | K dead on the M281 (isolated dots do not print); 21–22 % on two other engines | — |
| c2 | K | 139.5 | ~2–5 % page level (e016.2); c2-r0700 certified on paper (e029) | ~100–120 |
| c2 | cmy4 | 279 | 3.5 % state error | 244 |
| c2 | cmyk5 | 324 | 15 % | 208 |
| c2 | cmy8 engine / dot-mixed | 418.5 | 26 % | 250 / 240 |
| c3 | K | 62 | 0.0–0.02 % | 62 |
| c3 | cmy4 | 124 | 0.28 % | 122 |
| c3 | cmyk5 | 144 | 0.59 % | 141 |
| c3 | cmy8 engine / dot-mixed | 186 | 10.4 / 7.0 % | 153 / 161 |
| c3 | cmy8 engine, FULL PAGE, PCL XL (S9) | 186 | per plane C 2.1 / M 21 / Y 23 % | ≥ 82 (C 0.85 + M 0.25 + Y 0.23 bits/cell) |
| c3 | cmy8, FULL PAGE, PostScript DeviceCMYK (F/S1) | 186 | per plane C 13 / M 24 / Y 35 % hard; C certified 839/840 tiles at 0.55 bits/cell, M 61, Y 31 | ≥ 47 on hard decisions; ≥ 34 of PAYLOAD from C alone, = K c3 at the same rung, plus what M and Y add (e038 ceilings ≤ 0.37–0.47 / 0.28–0.41 bits/cell) |
| c4 | any | 35–105 | not measured on the M281 | — |

Reading: full-page cmy8 c3 is at least K c3 even on the worst route,
because its cyan plane alone is a K-quality plane and M/Y add something on
top; on PCL XL it is ~1.3× K c3 on hard decisions alone. The page-scale
loss is real but it is a loss of the M and Y planes, not of the format.
Further caveats: the patch rows are 3.9 mm patches on a mostly white page
(S14 measures each alphabet at page scale); the c2 rows are context-free
and single-pose (§041.5f), both pessimistic; a real code needs margin
above any of these (the holo rungs use 55–85 % of a cell's raw bits).

## 041.5h S14 — the page-scale probe (built 2026-10-05 13:55–14:15, printed 14:16)

`experiments/041-m281-screen-routes/ps_scale.py` on S12's footing (PostScript,
8-bit indexed DeviceRGB images, the four HP calls per image; S12 rebuilt
unchanged): seven FULL-WIDTH noise bands (x 12–198 mm, crossing the stripe on
purpose) covering 74 % of the page, two palette strips, three fiducial
images, 37 images. Bands, top to bottom: A1 cmy4-solid c3 | B1 the same with
matching off | B2 the same as 24 abutting 183-dot images cut from one raster
| A2 cmy8-engine c3 with S9's palette | A3 cmyk5 c3 (TonerBlack) | B4 cmyk5 c3
matching off | B3 cmy4-solid c2 (Detail) matching off | A-strip | B-strip.
Section A = matching at the device default (S12's footing), section B =
`false ColorSmartColorMatching` before every image (printed before only in
S6, under DeviceCMYK); section A is DRAWN first so a matching state that
outlived grestore could not reach back into it. The strips carry solid bars
of C, M-solid, M-corner, Y, CM, CY, MY, CMY, K and twelve cyan candidates
under each matching setting — the cyan (0,255,255) bar is the matching
witness (A screened / B solid = per-image control works; both solid = a
page-global latch; both screened = no effect). States iid uniform per band
from default_rng(51000 + band index); 2,867 readout windows (31 × 31 c3 cells,
46 × 46 c2 cells). Refuted once: the job correct in every check, but the
first layout put section A at y 12–133 mm and B at 134–284, confounding
matching with page position — rebuilt with the same rasters and seeds
PLACED as above (draw order unchanged), re-verified (gs render 0 differing
dots against the page composed from manifest + npz, stub HP-call sequence
exact, byte audit vs S12, all windows checked, geometry, determinism, S12
unchanged). Job 32,386,996 B, sha
`6081414085e912573a970c5b1ab6c0c939373f2e0e751e21c6582958af3e0689`, bands npz
`0a45dea8…`. Readout `measure/e041_scale_readout.py` (+ `e041_scale_synth.py`);
its single-pose registration is being replaced by per-plane poses before any
S14 number is used (§041.5f).

## 041.5i S14 READOUT (2026-10-05 15:10) — cmy4 HOLDS AT PAGE SCALE; cmy8 and cmyk5 do not, and the screener is a per-region switch

Page readout with PER-PLANE poses (the readout fix of 15:00: each plane
registered on its own unmixed coverage, ±12 px around the joint pose; the
single-pose numbers kept beside), 2,867 windows, 5/5 fiducials:

| band | alphabet, cell | matching / objects | state error (window loo mean) | per plane (best threshold) | MI b/cell → b/mm² | S12 patch, same alphabet |
|---|---|---|---|---|---|---|
| A1 | cmy4 c3 | default / 1 | **0.06 %** | C 0.00 M 0.01 Y 2.5 % | 1.991 → **123.5** | 0.00 % |
| B1 | cmy4 c3 | off / 1 | 0.09 % | C 0.00 M 0.01 Y 2.8 % | 1.989 → 123.3 | |
| B2 | cmy4 c3 | off / 24 tiles | 0.06 % | C 0.00 M 0.01 Y 3.0 % | 1.992 → 123.5 | |
| B3 | cmy4 c2 (Detail) | off / 1 | **2.8 %** | C 0.7 M 1.2 Y 10.4 % | 1.791 → **249.8** | 1.9 % |
| A2 | cmy8 c3, S9's palette | default / 1 | **32.5 %** | C 0.14 M 18.8 Y 21.2 % | 1.634 → 101.3 | 5.1 % |
| A3 | cmyk5 c3 | default / 1 | **17.0 %** | C 0.14 M 8.4 Y 14.9 K 4.0 % | 1.532 → 95.0 | 1.3 % |
| B4 | cmyk5 c3 | off / 1 | 16.1 % | C 0.14 M 7.6 Y 14.5 K 4.2 % | 1.573 → 97.5 | |

(MI = mutual information of the band's state confusion; c3 = 62 cells/mm²,
c2 = 139.5.) cmy4 at c3 is LOSSLESS AT PAGE SCALE (0.06–0.09 % over three
full-width bands; no position effect in x or y); at c2 it reads 2.8 %, a
context-free single-cell classifier, ≈ 250 b/mm² of mutual information —
four times K c3. cmy8 reproduces S9's page-scale collapse on the PostScript
route (5 % in patches → 32 % across the page; C untouched) and still
carries 101 b/mm², above K c3 (the operator's point). cmyk5 collapses too
(1.3 % → 17 %), although its four non-white colours are cmy4's plus solid K.
Colour matching off changes nothing (A1/B1, A3/B4); 24 abutting tiles
change nothing (B1/B2).

**Where the engine screens (`measure/e041_band_screen.py`: per 2.7 mm column
the known-lattice peak over its ring median, floor 5.9 / p98 11.4):** the
cmy4 bands carry NO 165/188 lpi screen anywhere (4–6, the floor) and a weak
212 lpi yellow screen (30–45 left → 25–30 right — the small screened yellow
component inside the PostScript-matched cyan and inside M-solid). A2 (cmy8)
is screened (165 lpi ~40, 212 lpi ~90) everywhere EXCEPT x 12–20 mm and
108–117 mm. A3 and B4 (cmyk5) are screened (165 ~20, 212 ~90) except x
12–35 mm and 108–142 mm — the wider bands the operator saw. The state
error follows the screen column for column: A3 reads 1–2 % over 12–30 mm,
6–7 % over 112–140 mm, 21–26 % elsewhere; A2 6–9 % over 12–20 mm, 10–16 %
over 108–117 mm, 34–36 % elsewhere. READING (a hypothesis, stated as one):
the engine processes the page in column regions with boundaries at the
left edge and at ~108 mm (the stripe of every sheet since e038); each
region STARTS unscreened and a content-driven switch turns screening on
after a distance that depends on the content — ~8 mm for cmy8, ~25–35 mm
for cmyk5, never for cmy4 over 186 mm. The HP columnar-pipeline patent
(US9171239B2) describes exactly such column regions with per-region state;
what flips the switch is not known — two-toner overlap cells in cmy8, K
cells (or the TonerBlack image) in cmyk5. Whether a white gap or an object
boundary resets it is S15's question (the operator's idea).

**Bars.** The cyan corner (0,255,255) is SCREENED on the PostScript route in
both strips (lattice 97–130) — `false ColorSmartColorMatching` has no
per-image effect on it (the witness reads "both screened"); two of the
twelve cyan candidates are SOLID in both strips: (0,208,255) (R 46 G 151 B
194, score 8) and (0,192,255) (R 45 G 151 B 202, score 7–9); (0,224,255) is
half-way (40–49); M-solid (240,0,192), Y, K and the CMY composite are solid;
CM, CY, MY are screened. The production cyan on PostScript is (0,208,255).
In the cmy4 noise bands the screened corner cyan shows no lattice (the
screened 85 % cyan's holes are too small to survive in random 3 × 3 cells)
and costs nothing measurable; the solid value removes the question.

**Registration** (per-plane poses): M − C within ±1 px median, Y − C within
−3…+3 px varying with x, K − C −2 to −5 px vertical — every plane needs its
own pose at c2.

## 041.5j S15 — the reset probe (built 2026-10-05 15:00–15:45, printed 15:49)

The question (operator, after S14): do thin white column gaps, object boundaries or an image that starts
away from the page's left edge reset the screener's per-region switch? Generator
`experiments/041-m281-screen-routes/ps_reset.py` (S14's emitter, `ps_scale.emit_job` now takes the wrapper
and header; S14 and S12 rebuild byte-identically). Job `scratch/m281-routes-20261004/S15-ps-reset.ps`
(33,030,058 B, sha `43c195288ab43e98387883ce9b5b1af6a66b08264ce9c27a9553c3094503206c`), manifest
`S15-ps-reset.manifest.json` (S14's schema + `gaps`, `variant`), bands `S15-ps-reset-bands.npz`
(sha `151ebb89…`). Every band section A (device-default matching), S14's HP call sequence, fiducials = S14's.
Nine bands, top to bottom, c3 Smooth h 708 dots unless stated:

| band | alphabet | variant | what it asks |
|---|---|---|---|
| R1 | cmy8-engine | one image | control |
| R2 | cmy8-engine | 24 abutting images of 183 dots (7.75 mm) | object boundary (tiles shorter than cmy8's ~8 mm lead-in) |
| R3 | cmy8-engine | one image, 1-cell (3-dot) white columns every 10.03 mm from 16.9 mm | thin gap |
| R4 | cmy8-engine | one image, 8-cell (24-dot) white columns every 20.07 mm from 22.0 mm | wide gap |
| R5 | cmy8-engine | one image starting at 50.04 mm | image-relative vs page-fixed regions (146 vs 108 mm) |
| R6 | cmyk5 TonerBlack | as R3 | thin gap, long (25–35 mm) lead-in |
| R7 | cmyk5 TonerBlack | 24 tiles as R2 | object boundary, long lead-in |
| R8 | cmy4 with solid cyan (0,208,255), M (240,0,192), Y | one image | production palette at c3 |
| R9 | cmy4 solid cyan, c2 Detail, h 588 | one image | production palette at c2 |

Builder verification (one `--verify` command, exit 0): gs render 0 differing dots against the page
composed from manifest + npz; stub run 58 images × the four HP calls, no ColorSmartColorMatching; byte
audit against S14; all 2844 windows; geometry; two identical builds; S14/S12 rebuild shas; both readouts
run on a clean synthetic of S15 (state error 0 in every band). `measure/e041_band_screen.py` heat maps now
pad each band by its start (R5). Without the pad, the shortest band's column count (`e041_band_screen.py:146`)
would have drawn R5 (108 columns from 51.5 mm) at the page edge and cut 28 columns (~38 mm) off the right of the
others. S14's pads are all 0 according to its columns CSV (every band's first column is at 13.42–13.44 mm, with
136 columns each). This was not checked by a re-run: S14's heat maps (14:51) predate the fix. Refuter (Opus, own parser, own composition, own gs
render, novelty diff against S14/S12): NOT refuted, nothing must be fixed. Its optional notes, accepted
as caveats rather than fixed: (1) cmyk5 has no one-image control on this sheet — if R6 AND R7 both stay
unscreened throughout, "both reset" cannot be told from "cmyk5 not screened on this print" except by
S14's A3/B4 and by the cmy8 half's same-sheet pattern; (2) R5 mixes an image edge with a 38 mm white
lead-in (R2 = edge without white, R4 = white without edge separate most outcomes); (3) the job's DSC
title says "S14 PostScript reset probe" (cosmetic; the PJL job name is right); (4) the scale readout has
no S15 comparison table — R1 vs R2–R5 and R6 vs R7 are read from the bands/windows CSVs and the
band-screen column profiles.

## 041.5k S15 READOUT (2026-10-05 16:30) — nothing resets the switch; white BEFORE the content lengthens the unscreened run

Instruments: `measure/e041_band_screen.py` (known-lattice scores per 2.7 mm column; shuffled floor median
5.8, p98 11.7) and `measure/e041_scale_readout.py` (per-window state error, per-plane poses). Fit: 5/5
fiducials, rotation −0.024°, residual ≤ 0.146 mm. The readout has no S15 comparison table; the per-column
profiles below are the window medians from `S15-ps-reset-windows.csv` (window centres, 5 mm bins).

State error % (loo, median over windows) by page x:

| band | 15 | 20 | 25–90 | 95 | 100 | 105 | 110 | 115 | 120–195 |
|---|---|---|---|---|---|---|---|---|---|
| R1 cmy8 control | 11 | 32 | 34–36 | 35 | 36 | 17 | 11 | 15 | 33–38 |
| R2 cmy8 24 tiles | 11 | 31 | 34–37 | 34 | 35 | 19 | 12 | 14 | 34–38 |
| R3 cmy8 1-cell gaps | 13 | 34 | 33–37 | 33 | 33 | 16 | 11 | 14 | 33–40 |
| R4 cmy8 8-cell gaps | 11 | 22* | 25–36* | 36 | 30* | 19 | 13 | 15 | 22–38* |
| R5 cmy8 from 50 mm | – | – | 8–10 (50–90) | 15 | 30 | 24 | 12 | 30 | 35–40 |
| R6 cmyk5 1-cell gaps | 4 | 3 | 4 (25), 11 (30), 18–24 | 21 | 24 | 10 | 7 | 7 | 6–7 to 130, 13 (135), 22–27 |
| R7 cmyk5 24 tiles | 6 | 4 | 6 (25), 13 (30), 19–25 | 25 | 24 | 12 | 9 | 9 | 7–9 to 130, 12 (135), 20–25 |
| R8 cmy4 solid C c3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0–1 | 0–1 |
| R9 cmy4 solid C c2 | 7 | 4 | 3–5 | 3 | 3 | 5 | 4 | 4 | 3–7 |

(*) R4's dips sit in the columns holding its white gaps (white cells read right), not a reset; the lattice
profile shows no dip there.

The lattice profile (212 lpi, the same reading in 165 lpi) says the same: R1–R4 unscreened 12–~20 mm and
~107–~118 mm, screened elsewhere; R6/R7 unscreened 12–~33 mm and ~107–~137 mm; R5 unscreened from its start
at 50 mm to ~92 mm (score 20–23 against 80–100 screened), mixed 95–100, screened by 105, unscreened again at
110–115, screened from 120; R8/R9 never screened (flat).

Band summaries (MI from the band confusion, discernible b/mm²): R1 32.2 % 100.7; R2 32.1 % 101.9; R3 32.4 %
100.8; R4 30.5 % 103.3; R5 25.0 % 112.4 (8–10 % over its first 43 mm); R6 18.0 % 91.6; R7 18.2 % 89.7;
R8 0.33 % (single pose 3.3 %) 121.8 of 124; R9 3.86 % (single pose 7.0 %) 241.9 of 279. Window grid for R5:
rows r0–r6 all unscreened (6–11 %) from 52 to 91 mm, 12–19 % at 95–99, 21–36 % at 103 — the end of the
run is a ramp of ~10 mm, not a clean edge, and the bottom row starts worse (13–19 % at 52–60).

READINGS (one print):
1. Object boundaries do NOT reset the switch: 24 abutting 7.75 mm images (R2, R7) behave exactly like one
   image (R1, R6), for cmy8 and for cmyk5.
2. White column gaps do NOT reset it once it is on: 1-cell (R3, R6) and 8-cell (R4) gaps change nothing.
3. The regions are PAGE-FIXED: R5's second unscreened run sits at ~107–118 mm like everyone's, not at
   50 + 95 = 145 mm.
4. White BEFORE the content in a region lengthens the unscreened run: R1 (content from 12 mm) runs
   ~8–10 mm; R5 (content from 50 mm, white before it) runs ~43 mm. That is ~0.9 mm more run per mm of
   white, from two points. The second region (no white before it in any band) runs ~11 mm (cmy8) and
   ~28 mm (cmyk5), about region 1's lengths — so each region starts with a head start and white before the
   content adds to it. A running budget per page-fixed region, consumed by content (cmy8 faster than
   cmyk5, cmy4 never empties it) and refilled by white, describes all of S14 and S15; it is a reading of
   two sheets, not a mechanism (memory rule: no mechanism words without a test).
5. The production cmy4 palette (solid cyan (0,208,255)) holds at page scale on a second print: c3 0.33 %,
   c2 3.86 %, no position effect. Both read a little worse than S14's cmy4 (0.06–0.09 %, 2.82 %) —
   different print, cyan value and page position, uncontrolled.
6. What the operator sees in R5: 43 mm of unscreened cmy8 (crisp cells, black triples, saturated colour
   noise) — the longest unscreened cmy8 at page scale so far — ending in a ragged ~10 mm transition.

WHAT IT PAYS: if the white credit is linear and white placed BEFORE the switch also counts mid-region,
cmy8 can stay unscreened at about half content and half white (0.9 mm of content per mm of white plus the
head start): ~53 % of a region's width, ~80 b/mm² discernible at c3 — below cmy4's 123.5. cmyk5's slower
drain gives ~two thirds content, ~87 b/mm² — also below. The white route maps the mechanism; it is not a
capacity route on these numbers. The capacity question left in avenue B is the colour count (a dot-mixed
cmy8 with four palette colours).

## 041.5l S16 — the trigger probe (built 2026-10-05 16:50–17:55, printed 18:03)

The question (after S15): what trips the switch — the COLOUR COUNT of an image (reading a: 4 colours never,
5 or more do) or a per-region BUDGET spent by overlap/K PIXELS and refilled by white (reading b: cmy8 at
50 % overlap cells runs ~8–10 mm, cmyk5 at 20 % K ~25–35 mm — about 5 overlap-or-K cell·mm either way)?
Does an object OUTSIDE the image's palette count? Does white AFTER the switch refill? And the first
composite-cell alphabets. Generator `experiments/041-m281-screen-routes/ps_trigger.py` +
`ps_trigger_verify.py` (S15's footing by import; S15/S14/S12 rebuild byte-identical). Job
`scratch/m281-routes-20261004/S16-ps-trigger.ps` (32,515,467 B, sha
`1ccf884a64b13dc5fad7667af667861cd3179daf0ae23ead04658bf20638d2b8`), manifest `S16-ps-trigger.manifest.json`
(per band: states, lookup, cell_layouts, draw rule, extra_fraction, asks), bands `S16-ps-trigger-bands.npz`
(sha `3c09dcc0…`, dot-level planes). ONE NEW CONSTRUCT, deliberately: a K imagemask in holo's frozen idiom
(`src/holo/gen/ps.py` put_bitmap, line for line: `0 0 0 1 setcmykcolor`, `w h true [w 0 0 -h 0 h]`,
`currentfile /ASCIIHexDecode filter imagemask`) — printed as K on this engine in e029, new in this prologue.
22 objects (20 images, 2 masks; S15 had 58). Fourteen full-width bands 4392 × 432 dots (144 c3 cells,
4 × 47 windows) at x 283, y 283 + 456k (432 + 24; the manifest's 283, 739, 1195 …; a slip read 492k here until 2026-10-11), then a 24-dot strip at y 6667; "cmy4-solidC" = W, C-solid (0,208,255),
M-solid (240,0,192), Y; seeds default_rng(53000 + k); the "+p" bands draw 4 states then overwrite a fraction
p with the 5th (rng.random < p):

| band | content | neutral | asks |
|---|---|---|---|
| T1 | cmy8-engine (S9 palette) | Proc | screen-behaviour control (= S15 R1) |
| T2 | cmy8 DOT-MIXED: overlaps = DOTMIX3 single-toner dot layouts (CM 5 C + 4 M …); lookup = T11's four entries | Proc | colour count AND the capacity candidate (3 b/cell): both readings say unscreened |
| T3 | cmy4-solidC + an UNUSED 5th lookup entry red (hival 4, index 4 never drawn) | Proc | does the lookup's size count? |
| T4 | cmy4-solidC + 0.5 % red (MY engine overlap) cells | Proc | (a) screens ~25–35 mm; (b) never |
| T5 | cmy4-solidC + 20 % red | Proc | the red twin of T8: red pixels vs K pixels as the spender |
| T6 | cmy4-solidC + 0.5 % K | Toner | (a) screens; (b) never |
| T7 | cmy4-solidC + 10 % K | Toner | (a) ~25–35 mm; (b) ~50 mm |
| T8 | cmyk5-solidC (20 % K), one image | Toner | series top; the one-image cmyk5 control S15 lacked (cyan differs from S14 A3's) |
| T9 | cmy4-solidC image (TonerBlack, no (0,0,0)) + ONE K imagemask on 20 % of the cells (W in the image) | Toner+mask | does an object outside the palette count? vs T8 (one object) and T14 (no mask) |
| T10 | AMPLITUDE: {W, C/M/Y × 3/6/9 dots}: 3 = middle column, 6 = left+middle, 9 = full | Proc | composite cells: do the levels separate? |
| T11 | cmy4-solidC c3 | Proc | production control (= S15 R8) |
| T12 | cmy4-solidC c2 Detail | Proc | production control at c2 (= S15 R9) |
| T13 | cmy8-engine as TWO images with an OBJECT-FREE 20 mm block at 60–80 mm | Proc | does white after the switch refill? vs T1 |
| T14 | cmy4-solidC, TonerBlack, no K | Toner | the K series' p = 0 under TonerBlack (041.5i named the TonerBlack image itself as a candidate) |
| strip | bar A K imagemask 600 × 24 at x 283; bar B (0,0,0) TonerBlack image at 1000; bar C (0,0,0) ProcBlack image at 1717 | — | what the mask lays: toner K or process black |

Build history: a first build (13 bands at 468, red/K at 0.5 and 5 %, T9 under ProcBlack, T13's block as
white pixels inside one image) passed its refutation on correctness; the refuter's four DESIGN points were
accepted and applied before print: (1) under reading (b) 5 % trips the screen only beyond ~100 mm, past
both regions — the series was mis-scaled (now 0.5 / 10 / 20 %); (2) the K series had no zero under
TonerBlack (T14 added; 14 bands at 432); (3) T9's base image under TonerBlack so T9 vs T8 differs only by
the object split and T9 vs T14 only by the mask; (4) T13's white made object-free, the kind S15 R5 measured.
Second refutation (own parser, own composition, own gs render, imagemask idiom line by line, novelty diff
vs printed S15 ∪ S14, readout loaders): NOT refuted, nothing to fix; crash risk of the mask judged low (the
realistic failure a PostScript error discarding the page — it did not happen: page printed, back channel
empty). Caveats carried into the readout: a SCREENED T9 is ambiguous (per-region K vs the stacked-object
re-screen of e002's hypothesis vs what the mask lays; only an unscreened T9 is decisive); the red series is
all ProcBlack and the K series all TonerBlack (T14 vs T11 isolates the neutral call at p = 0 only); T13's
refill is readable only as yes/no (27 mm remain before the 107 mm boundary; a credit ≥ ~17 mm looks like a
reset), and its windows w12/w17 contain block cells (deflated error — read the lattice profile there and
exclude the bare-paper columns from band_screen); T4/T6's extra state is sparse (singleton loo floor; T6's K
plane under PLANE_MIN_INK so K cells read at the OR-ed pose) — detect screening from the cmy4 cells and the
lattice; T10's levels all ink the middle column, which the readout's centre box (cell_px//2) samples — a
whole-cell feature is owed before T10 is read; bands are 432 tall (S14/S15 684–942): anchor onsets within
this sheet; the three bars are all (0,0,0) — tell them apart by mean RGB and lattice.
Not in these caveats (added 2026-10-11): the readout windows tile each band from its top-left in whole
31 × 31 c3 / 46 × 46 c2 cells (93 / 92 dots), so four window rows cover 372 / 368 of a band's 432 dots and
the bottom 60 dots (20 c3 cell rows) / 64 dots (32 c2 cell rows, T12) of every band, 13.9 / 14.8 %, never
reach `e041_scale_readout` — 041.5m's state errors, MI and b/mm² describe each band's top 372 / 368 dots.
The lattice column is `e041_band_screen`'s, which reads the whole band height inside its 24-px insets.
`ps_trigger.py:13` and its manifest note (:490) say "144 c3 / 216 c2 cell rows = 4 window rows of 31 / 46
cells" without the remainder (4 × 31 = 124, 4 × 46 = 184).

Left off S16 on purpose (the design message of 2026-10-05): (1) a third white-credit point (an image
starting at 30 mm), because the white route does not pay whatever the credit law is (041.5k, WHAT IT PAYS).
The credit for white before the content (~0.9 mm per mm) therefore rests on S15's two points by choice.
(2) Guard-ring cells, held back until T10 showed whether dot counts separate. T10 then read adjacent levels
at 8–15 % (041.5m item 6), and the synthesis parks composite cells below dot-mixed cmy8
(docs/M281-COLOUR-2026-10-05.md §7). No guard-ring band has been printed. (3) Any c2 cmy8 band, because S12
A21 (c2 dot-mixed) read 22–30 % state error at patch scale (single pose; 16–24 % leave-one-out,
results/measurements.json). S17 printed that band at page scale and closed c2 dot-mixed (041.5o item 3).

## 041.5m S16 READOUT (2026-10-05 18:45) — the screener counts composite PIXELS per page-fixed region, not colours; dot-mixed cmy8 at c3 is UNSCREENED at page scale and reads 3.2 % = 171.8 b/mm²

Instruments: `measure/e041_band_screen.py` (shuffled floor median 5.9, p98 11.8) and `measure/e041_scale_readout.py`
(now with the additive whole-cell reading; S15 re-run: original columns identical). Fit 5/5 fiducials,
rotation +0.036°, residual ≤ 0.115 mm; 2616 windows read, the 16 all-white windows of T13's block skipped.

Lattice score (212 lpi, max over R/G/B, median of windows, 5 mm bins; cmyw bands sit at 15–26 on this
metric, T1's screened zone at 80–110, the clean synthetic at 18–31) and state error % (loo, window median):

| band | content | lattice by x | state error by x | band state % / MI b/cell / b/mm² |
|---|---|---|---|---|
| T1 | cmy8-engine control | unscreened 12–20 and 107–118, screened elsewhere (= S15 R1) | 10 → 30–37; 12–18 at 105–115 | 32.2 / 1.630 / 101.1 |
| **T2** | **cmy8 DOT-MIXED** | **flat 26–40 everywhere — no region structure, no 107 mm dip: UNSCREENED** | **2–6 everywhere** | **3.22 / 2.771 / 171.8** |
| T3 | cmyw + unused 5th lookup entry | flat 15–26 | 0 | 0.06 / 1.992 / 123.5 |
| T4 | cmyw + 0.5 % red | flat 12–26 | 0–1 | 0.46 / 2.016 / 125.0 |
| T5 | cmyw + 20 % red | on at ~30 mm (177–190 — the strongest screen on any sheet), off 107–~130, on from ~140 | 1–2 → 19–26 from 35; 5–7 at 110–130 | 17.2 / 1.494 / 92.7 |
| T6 | cmyw + 0.5 % K (TonerBlack) | flat 13–26 | 0 | 0.17 / 2.018 / 125.1 |
| T7 | cmyw + 10 % K | on at ~40 mm (55 at 40, 98 at 45), off 107–~145, on from ~150 | 1–6 → 20–24 from 45; 6–11 at 110–145 | 14.5 / 1.542 / 95.6 |
| T8 | cmyk5 20 % K, one image | on at ~37 mm (30 at 35, 65 at 40), off 107–~140 | 2–3 → 19–25 from 35; 4–10 at 110–135 | 16.7 / 1.500 / 93.0 |
| T9 | cmyw + 20 % K as a separate IMAGEMASK | on at ~35 mm (29 at 35, 50–57 from 40), off 107–~140, weaker screen in region 2 (29–38) | 1–3 → 21–25 from 35; 4–12 at 110–135; 27–33 from 150 | 19.1 / 1.471 / 91.2 |
| T10 | amplitude 10 states (3/6/9 dots) | flat 5–9 (the lowest of all) | 13–22 everywhere | 15.6 / 2.597 / 161.0 (whole-cell reading WORSE: 25.9) |
| T11 | cmyw c3 production | flat 14–26 | 0 | 0.06 / 1.992 / 123.5 |
| T12 | cmyw c2 Detail production | flat 7–13 | 2–8 | 4.00 / 1.723 / 240.3 |
| T13 | cmy8, object-free white 60–80 | screened 20–55 (92–97); AFTER the block 16–28 at 80–95, 42 at 100, 79 at 105 | 30–35 → 8–9 at 80–95, 20 at 100, 17 at 105 | 27.8 / 1.731 / 107.3 |
| T14 | cmyw under TonerBlack, no K | flat 11–24 | 0 | 0.12 / 1.985 / 123.1 |

Switch-on positions (first of three consecutive 2.7 mm columns ≥ 45; lead-in = distance from the region's
start, 12 or 107 mm; "budget" = lead-in × content fraction):

| band | composite fraction | region 1 onset / lead-in / budget | region 2 onset / lead-in / budget |
|---|---|---|---|
| T1 cmy8 | 50 % | 18.8 / 6.8 mm / 341 %·mm | 116.2 / 9.2 / 461 |
| T5 red | 20 % | 29.6 / 17.6 / 353 | 131.1 / 24.1 / 482 |
| T7 K | 10 % | 39.1 / 27.1 / 271 | 147.3 / 40.3 / 403 |
| T8 K image | 20 % | 36.4 / 24.4 / 488 | ~140 by state error / ~33 / ~660 (lattice weak: 166 at threshold 45) |
| T9 K mask | 20 % | 35.1 / 23.1 / 461 | ~140 by state error / ~33 / ~660 (lattice never ≥ 45) |
| T13 after the 20 mm block | 50 % | — | off at 80, on again at 100.0: 19.9 mm run |

Bars (96-px windows, mean RGB / own-channel lattice score): TonerBlack (0,0,0) image 45.8/49.7/52.2, 18.6;
ProcBlack (0,0,0) image 45.5/49.8/52.9, 25.0; the K IMAGEMASK 53.0/50.9/50.9, 7.6 — the mask lays a
NEUTRAL, unscreened black (toner K); the two image blacks are identical to each other and slightly blue
(a loupe comparison of the three bars is owed: is the TonerBlack image bar rich black?).

READINGS (one print):
1. **The colour-count reading is REFUTED; the composite-pixel budget stands.** A 5-entry lookup with an
   unused entry (T3), 0.5 % red cells (T4) and 0.5 % K cells (T6) never screen anywhere; 10 % and 20 %
   do, after lead-ins whose product with the content fraction is 270–660 %·mm in every band and both
   regions (cmy8 at 50 %: 341/461; red 20 %: 353/482; K 10 %: 271/403; K 20 %: 461–488 / ~660). Red
   (an MY overlap pixel) spends what K spends. The budget is a count of composite pixels per page-fixed
   region, within a factor ~2 over 10–50 % content; 0.5 % would need ~900 mm. (Description of two
   sheets; the mechanism word "budget" stays a reading.)
   **Qualifier 2026-10-11:** "red spends what K spends" is unseparated from the neutral call. The red series
   (T3–T5) ran all under ProcBlack and the K series (T6–T9, T14) all under TonerBlack (the build caveat
   above, not carried into this reading). T5 vs T8 changes red-vs-K and the neutral call together, and
   T14 = T11 isolates TonerBlack only at p = 0. The budget law is checkable on the TonerBlack series
   alone: onsets at 10 % (T7) and 20 % (T8, T9's mask), 0.5 % (T6) never screening, and T14's zero. The
   two (0,0,0) image bars read identical (the loupe check is owed), which hints that the call may not change
   what an image lays, but it does not separate the two. Owed control: a red series under TonerBlack or a
   K series under ProcBlack.
2. **An object outside the image's palette counts the same**: T9 (K from a separate imagemask over a
   4-colour image) switches on at 35 mm like T8 (36 mm, one image). The screener sees the composed
   raster. The K-overlay door is closed; T9 is the ambiguous-if-screened band and it screened.
   [CORRECTED 2026-10-11: "the screener sees the composed raster" is not established. A SCREENED T9 (on at
   35 mm, T8 at 36) cannot separate the three causes this section's own build caveat (041.5l) named: the
   mask's K spending the region budget like image K, the stacked-object re-screen of e002's hypothesis, or
   what the mask lays (bar A: a neutral black, where both image blacks read slightly blue). No stacked overlay
   without K was printed: T9 is S16's only stacked band, and S17's mask (U14) has no image beneath it. What
   stands: 20 % K from a separate imagemask screens like 20 % image K, so the K-overlay door is closed
   either way.]
3. **White AFTER the switch refills it**: T13's screen is OFF again right after the 20 mm object-free
   block and cmy8 runs 19.9 mm before it switches on — about 1 mm per mm of white, as S15's 0.9. (Width
   and object-free-ness were changed together; S15 R4's 3.4 mm in-image gaps did not reset.)
   [Qualifier 2026-10-11, the pre-registered caveat (041.5l) carried to the result: after the 60–80 mm
   block only 27 mm remain before the 107 mm boundary, and a credit of ≥ ~17 mm looks like a reset. T13's
   19.9 mm run (on again at 100.0 mm) is past that, so T13 answers "does white after the switch refill"
   with yes, but gives no rate. The ~1 mm per mm rests on S15's white BEFORE the content alone (two
   points, 041.5k reading 4: ~0.9).]
4. **TonerBlack by itself does nothing** (T14 = T11), and the lookup's size does nothing (T3 = T11).
5. **Dot-mixed cmy8 at c3 is the capacity result of the campaign.** Every pixel is a single toner, so the
   budget is never spent: unscreened over the whole width, 3.22 % state error (S12 patch: 6–8 %), MI
   2.771 of 3 b/cell = 171.8 b/mm² discernible, against cmyw c3's 123.5 and K c3's 62. The confusion is
   all in the three-toner cell (3 dots of each toner): CMY read 84.9 % (→ CM 6.1, CY 4.9, MY 3.0); the
   two-toner dot-mixed cells read 96–98 %, singles and white ≥ 99.3 %. Per plane (as cmy8's codec sees
   it) the errors are ~1 %: at the frozen ladder r0775–r0850 per plane, i.e. **the EXISTING c3-cmy8 format
   at r0850 = 947 kB per A4 page (136 b/mm² net at 10 % repair)**, with a generator-side change only (the
   overlap states drawn as DOTMIX3 cells) and the receiver's cell model told about half-coverage planes.
   A 7-state variant without CMY (the parked reduced-alphabet erasure row, docs/REDUCED-ALPHABET-
   ERASURE-ROWS.md) now has a measured customer: it would trade 0.19 b/cell for the weak state.
6. Composite amplitude cells (T10) separate, but weakly: adjacent levels confuse 8–15 % (3↔6 and 6↔9),
   non-adjacent and cross-toner < 0.5 %; 15.6 % state error, 2.60 of 3.32 b/cell = 161 b/mm² — below
   dot-mixed cmy8 at five times its error. The whole-cell feature read WORSE (25.9 %) than the core box:
   the +0.4 dot/edge gain fills the core on every level and the whole cell adds neighbour paper. Parked.
   The whole cell wins nowhere. In results/measurements.json `state_err_loo_wholecell` lies above the core
   box's `state_err_loo` on every band of S16 and of S17 (2400 and 4800): T2's dot-mixed overlaps 13.3 vs
   3.2 %, cmyw c3 T3/T11/T14 0.78/0.79/1.05 vs 0.06/0.06/0.12 %, cmyw c2 T12 8.7 vs 4.0 %. The state errors
   this log quotes are the core box's. `*_wholecell` is the additive second column (S15 re-run over its
   2,844 windows: original columns identical).
7. Sparse K and red cells on a cmyw page read solid and cost nothing (T4 0.46 %, T6 0.17 %): K furniture
   (fiducials, pilots) at < 1 % density is available inside a cmyw or dot-mixed page.
   [Qualified 2026-10-11: what T4/T6 measured is sparse cells at 0.5 % in the image, nothing more.
   Fiducials are not on offer: DESIGN.md R3 keeps them off every archive sheet. Pilot furniture is
   denser than 1 %: p120 puts 120 of a tile's 4,096 cells (2.9 %) on sites. By reading 1's
   270–660 %·mm that would switch the screen on ~90–225 mm into a region, an estimate from the
   10–50 % bands that is valid only within reading 1's factor ~2. CMY-DESIGN R14 (owner, 2026-10-10,
   "no K for now") puts no K furniture in cmy -v1. Unmeasured: a sparse K imagemask, and a K word
   layer's density against T6's 0.5 %.]
8. Production cmyw, third print: c3 0.06 % (T3, T11), 0.12 % (T14); c2 Detail 4.0 % (S14 2.8, S15 3.9).
   T1 reproduces S15 R1 exactly (32.2 % / 32.2 %; same region edges).
9. T2's TEXTURE (operator: "very fine, contrast-rich diagonal dark/bright lines in some colours"): a 283 lpi
   lattice at BOTH ±45° (90 µm = 3 dots per cell along each diagonal) that only T2 carries — peak over ring
   median 176 / 136 in G, 305 / 287 in R, 53 / 168 in B at x 150 mm; T1 3–6, T11 8–17, T14 6–13; nothing at
   the dot alternation itself (424 lpi: 10, as every band) and none of the engine's 165/188/212 lattices.
   It is the DOTMIX3 layouts: the first toner of a two-toner cell sits on (r+c) even = the X of both
   diagonals, the second on the plus; the CMY cell puts each toner on one diagonal stripe. The 42 µm dots
   are below the scanner's resolution (the cells read as blends), the 3-dot diagonal period is not, and
   the +0.4 dot/edge gain joins diagonal neighbours into lines — dark C/M diagonals against the lighter
   complement, in the overlap cells only. Harmless to the state readout (3.2 %), but a strong periodic
   45° lattice a per-plane own-mask correlation can slip along by one dot: T2's M/Y poses vs C read −5 px
   where every solid-cell band reads −1 to −2 — the holo3 cell model for dot-mixed pages should take its
   pose from solid cells or a mask that breaks the diagonal. Avoidable at the generator: a layout per cell
   from the keystream (neighbours not continuing one diagonal), or X for one state and plus for the next,
   spreads the energy — a band for the next sheet beside the 7-state variant.

RANKING ON THE M281 (A4-4mm, 10 % repair; net b/mm² over the cell field): c2-cmyw 1.2–1.4 MB (167–196,
r0700 / r0775+r0850, 2.8–4.0 % raw, context detector and 4800 owed) > **c3-cmy8 dot-mixed 0.95 MB (136,
r0850, ~1 % per plane, existing format)** > c2-K 0.60–0.74 MB (83–103) > c3-cmyw 0.63 MB (91, capped by
the top rung). c2 dot-mixed cmy8 is not a candidate (S12 A21: 22–30 % at patch scale).

## 041.5n S17 — the layout probe (built 2026-10-05 22:28–23:11, printed 2026-10-06 00:12; to be scanned at 4800 dpi)

The questions (after S16 and the operator's: "couldn't we use those stripes — presence/absence/phase — to
transmit information?"): can the ORIENTATION and the PHASE of a dot-mixed overlap cell's layout carry
bits on top of its state; is the 7-state dot-mixed alphabet (no three-toner cell) the better c3 row; do c2
dot-mixed cells read with column or row pairs where S12's diagonal pairs read 30–56 %; and the controls
at 4800 dpi: cmyw c2/c3 and c2-K on the same sheet. Generator
`experiments/041-m281-screen-routes/ps_layouts.py` + `ps_layouts_verify.py` (S16's footing by import;
S16/S15/S14/S12 rebuild byte-identical). Job `scratch/m281-routes-20261004/S17-ps-layouts.ps` (31,583,218 B,
sha `02bea73e842b0d76802c8caf57860a464470bf1d02ad484e83c8373c89772fac`), manifest `S17-ps-layouts.manifest.json`
(per band `layout_catalogue` {state: [{id, orientation, phase, grid}]}, `layout_draw`), bands
`S17-ps-layouts-bands.npz` (sha `3c858d9d…`; `states_`, `layouts_` = index into the cell's state's
catalogue, `planes_` at dot level). 17 objects: 3 fiducial images, 13 band images (one hival-3 lookup
W/C-solid/M-solid/Y byte-identical to S16 T11's; ProcBlack; Smooth, Detail on U12 only), 1 K imagemask
(U14, holo's put_bitmap idiom as S16; 50 % K, no image beneath). Fourteen bands 4392 × 438 (146 c3 cells,
4 × 47 windows) at x 283, y 283 + 462k, last end 6727; seeds default_rng(54000 + k): states by `choice`, then
for U3–U7 `u = random((rows, cols))`, layout = floor(u · n_candidates(state)).

Layouts (r row, c col from the cell's top-left; d = c − r; a = r + c): two-toner X = A on (r+c) even (S16);
CMY stripes "−" = (C,M,Y)[((r+c) + phase) mod 3], "+" = (C,M,Y)[((c−r) mod 3 + phase) mod 3]; two-toner
ORIENTED BAND 5:4: "+"0 A on d ∈ {0,1}, "+"1 d ∈ {−1,0}, "−"0 a ∈ {2,3}, "−"1 a ∈ {1,2} (B's four dots
include one 4-isolated corner: "+"0 (0,2), "+"1 (2,0), "−"0 (2,2), "−"1 (0,0)); A = the first toner of the
state's name. c2: DIAGONAL pairs (S12's DOTMIX2), COLUMN pairs (A = column 0), ROW pairs (A = row 0);
c2 CMY (U10 only) = ((C,M),(Y,C)).

| band | content | asks |
|---|---|---|
| U1 | c3 cmy8 dot-mixed, S16 T2's layouts | control (= T2, other seed) |
| U2 | c3 cmy7 dot-mixed, X layouts | the reduced-alphabet erasure-row candidate |
| U3 | c3 cmy8, X two-toner; CMY stripes random orientation | one orientation bit on CMY cells |
| U4 | c3 cmy8, oriented bands random orientation; CMY random orientation | orientation on every overlap cell |
| U5 | c3 cmy8, orientation "−", random phase (bands 2, CMY 3) | phase readability |
| U6 | c3 cmy8, random orientation and phase (two-toner 4, CMY 6 layouts) | the keystream-style candidate |
| U7 | c3 cmy7, oriented bands random orientation | 7 states + orientation — the likely production row |
| U8 / U9 / U11 | c2 cmy7 dot-mixed, column / row / diagonal pairs | which 2×2 layout prints |
| U10 | c2 cmy8 dot-mixed, diagonal pairs incl. CMY | S12 A21 at page scale |
| U12 / U13 | cmyw c2 Detail / c3 | production controls at 4800 |
| U14 | c2-K, one imagemask, W/K uniform | the archival row at 4800 on the same sheet |

Builder verification (--verify, exit 0, 16:42 wall): both gs renders 0 differing dots against the page
composed from states + layouts + catalogue and from planes; no dot carries two toners; stub log 82 lines
exact; byte audit vs S16; mask block = put_bitmap line for line (3766 lines); 2632 windows; dot counts
(X 5:4, bands 5:4 with exactly one isolated B dot, stripes 3:3:3, c2 pairs 2:2, c2 CMY 2:1:1); draws
re-derived from the seeds equal the npz; geometry; determinism; rebuild shas; readout dry run on a clean
synthetic (state errors 0 everywhere but U3 loo 0.27 % — a state drawn with two layouts is one class with
a mixed mean on single windows; cross/band 0). Refuter (Opus; own parser, own composition from the
formulas, own gs render, put_bitmap regeneration, novelty diff vs printed S16 ∪ S15): NOT refuted, nothing
to fix; novelty = the JOB NAME/Title/Creator lines and the 4392 × 438 sizes only; the mask risk judged low
(S16 T9's mask printed in this prologue; e029's whole-page mask was 17× larger). Printed without fault.
What the two renders prove (`render_checks` in `ps_trigger_verify.py` / `ps_layouts_verify.py`): the
"0 differing dots" is the `-dUseFastColor` render against the composed pages. gs 10.08's default ICC paints
the imagemask's `0 0 0 1 setcmykcolor` as (35,31,32), so the two renders differ exactly on the mask bits:
393,147 dots on S16 (T9's 378,747 K-cell dots + bar A's 600 × 24) and 962,572 on S17 (= U14's K-cell dots).
The default render matches the objects painted with that value at 0 dots (manifests'
`verification.1_render`, `scratch/m281-routes-20261004/`). gs knows none of the HP operators (the stub
only logs the calls), so a render proves the page as drawn, not what the engine does with it.

Readout caveats carried (refuter's): fit per-plane poses from the SOLID cells, never from dot-mixed cells
(S16 T2's −5 px lattice slip); phases are 1-dot translations of one pattern and the measured per-plane
misregistration is up to ~1 dot with steps at ~77 and ~112 mm — read orientation/phase error against the
local misregistration vector; a centre-box reader cannot answer the layout questions (the centre dot of a
CMY "−p" cell changes toner with phase) — whole-cell templates against the catalogue grids, class means
pooled across windows (U6 has 22 classes, 20–44 cells each per window); U4 vs U3 and U7 vs U2 change the
two-toner family AND per-cell mixing together — only the per-layout confusion inside a band separates
them; U14 at 50 % K should switch the screen on 5–13 mm into each region by S16's budget (0/255 pixels
pass unchanged; read it as an x profile; check its black against S16 bar A); U10's CMY cell has isolated
single M and Y dots (expected poor); U8/U9 are biased by x/y pose error in a centre-box reader; one
print — band differences of a fraction of a percent are confounded with y position; the F2/F3 refine
windows come within ~5 dots of U14's corner.

Note added 2026-10-11 to the "local misregistration vector" caveat: what counts is its DIRECTION. A plane
shifted along a layout's stripes (Δr + Δc = 0 for "−", Δr = Δc for "+" and the oriented bands) keeps its
stripe membership and only moves dots across the cell edge; a shift across them moves its dots onto the
neighbouring toner's stripe, and one dot of it is exactly a phase step. §041.5o item 2 correlates the
orientation error only with the magnitudes |Y−C| (U6, r = +0.44) and |M−C| (U4, r = +0.29) and with x.
The across-stripe component is the reading still owed with the pose refinement. This is geometry from
the layout formulas above, not a measurement.

The readout side (4800-dpi capable, layout decoding) is being built in parallel; its record follows when
the scan is read. Process note: the workflow gated the sheet's refutation on the readout builder's
end-to-end 4800 proof (a 7.6 GB synthetic, ~1 h) — the sheet waited an hour for nothing; refuted and
printed off a separate agent. Lesson in memory (`feedback-proofs-off-the-print-path`).

## 041.5o S17 READOUT (2026-10-06 01:45, the first 4800 dpi capture) — cmy7 dot-mixed at c3 reads 0.54 %; ORIENTATION is a symbol (2 %), PHASE is not; c2 dot-mixed closed; cmyw c2 is registration-limited

Instruments at `--scan-dpi 4800` (8 px per dot): `measure/e041_band_screen.py` (15.5 min, 8.6 GB) and
`measure/e041_scale_readout.py` + `measure/e041_layout_readout.py` (42.6 min, 9.4 GB; the layout decision:
poses from the SOLID cells only, a forward model with neighbour-bleed removal, three decision-directed
passes, scored against `layouts_<band>` GIVEN the true state). Fit 5/5 fiducials, rotation −0.065°,
residual ≤ 0.149 mm; 2632 windows read, 54 registration fallbacks (U8/U9).

SCREEN: no band is screened — every dot-mixed band at c3 and c2, both cmyw controls, and the c2-K band
(flat at the floor, 4–6: a K-only band is 0/255 in every pixel, so the switch has nothing to act on —
why the K volumes always printed clean under the same screener). U9 (c2 row pairs) alone shows two
stretches of raised 212 lpi score (30–34 at 35–45 and 75–110 mm vs 7 elsewhere) with NO matching change in
its state error (22–23 % throughout): a texture, not the screen.

| band | content | state % (loo) | MI b/cell | b/mm² | layout given state |
|---|---|---|---|---|---|
| U1 | cmy8 dot-mixed, S16 layouts | 3.65 | 2.741/3.00 | 169.9 | — |
| **U2** | **cmy7 dot-mixed, X layouts** | **0.54** | **2.748/2.81** | **170.4** | — |
| U3 | cmy8, CMY stripes random orientation | 2.90 | 2.800 | 173.6 | orientation 1.71 % (CMY cells, n 22,923; MI 0.88 b) → +0.11 b/cell = 180.5 |
| U4 | cmy8, oriented bands + CMY, random orientation | 5.69 | 2.639 | 163.6 | orientation 10.0/10.4/10.2 % (CM/CY/MY), 16.8 % (CMY) → +0.24 = 178.5 |
| U5 | cmy8, fixed orientation, random phase | 6.92 | 2.573 | 159.5 | phase 12.0/13.1/11.5 % (two-toner, of 2), 17.9 % (CMY, of 3) → +0.27 = 176.4 |
| U6 | cmy8, random orientation and phase | 7.06 | 2.569 | 159.3 | layout 18.9 % (orientation 10.5, phase 13.6); MI 1.12–1.17 b of 2–2.58 → +0.57 = 194.6 |
| **U7** | **cmy7, oriented bands, random orientation** | **2.37** | **2.639/2.81** | 163.6 | **orientation 2.8/2.4/2.1 % (CM/CY/MY; MI 0.81–0.85 b) → +0.36 b/cell = 3.00 b/cell = 185.8** |
| U8 | c2 cmy7, column pairs | 20.2 | 1.715/2.81 | 239 | — |
| U9 | c2 cmy7, row pairs | 22.6 | 1.599 | 223 | — |
| U10 | c2 cmy8, diagonal pairs + CMY | 23.6 | 1.830/3.00 | 255 | — |
| U11 | c2 cmy7, diagonal pairs | 18.3 | 1.788 | 250 | — |
| U12 | cmyw c2 Detail | **6.43** (S14/15/16 at 2400: 2.8/3.9/4.0) | 1.592/2.00 | 222 | — |
| U13 | cmyw c3 | 0.08 | 1.989 | 123.3 | — |
| U14 | c2-K imagemask | 4.56 (hard, context-free) | 0.739/1.00 | 103 | — |

READINGS (one print, one capture):
1. **The 7-state dot-mixed alphabet is the c3 colour row.** Dropping the three-toner cell takes the state
   error from 3.65 % (U1) to 0.54 % (U2) at the same discernible bits (170.4 vs 169.9 b/mm²); every state
   reads ≥ 98.9 % (CM → C 0.9, CY → C 0.6, MY → M 0.5: the 4-dot minority toner under-read). Per plane
   ~0.2 %. This is the reduced-alphabet erasure row with its first page-scale measurement: at r0775 with
   erasures (≈ plain r0850's budget) ~860 kB per A4 page, 124 b/mm² net, on the robust c3 footing.
2. **Orientation carries a bit; phase does not (yet).** Where the layout decision has good poses it
   reads 1.7 % (U3, CMY stripes) and 2.1–2.8 % (U7, oriented two-toner bands): U7 = 7 states at 2.4 % +
   one orientation bit on 3/7 of the cells at 2.5 % = 3.00 b/cell = 185.8 b/mm² discernible, ~1.0 MB
   per page at the ladder (orientation stream at r0775: +15 % over the plain 7-state row). The oriented
   band layout costs state accuracy against the X (U7 2.4 % vs U2 0.54 %). Phase — a one-dot shift of the
   same pattern — reads 12–18 % (U5), and the all-random U6 19 %: the per-plane misregistration measured on
   this page (M−C −0.3…−1.1 dots and Y−C −0.5…−2.1 dots in y, +0.1…+0.9 in x, varying with x AND y) is of
   the order of the phase step. U6's orientation error correlates with |Y−C| (r = +0.44; 6.7 % at small
   offsets vs 14.1 % at large), U4's with |M−C| (r = +0.29; 7.7 vs 15.8 %) and is x-structured (1–10 %
   left of 65 mm, 16–28 % at 70–130 mm) — the decision is pose-limited (per-window poses from solid cells;
   the readout axis: local or pooled pose refinement should bring U4/U6 toward U7). U4 vs U7 differ in the
   CMY state's presence (its stripes are the worst-read layout, 16.8 %) and in page y.
3. **c2 dot-mixed is closed.** Column (20.2 %), row (22.6 %) and diagonal pairs (18.3 %; 23.6 % with the
   CMY cell) all fail the same way: the two-toner 2+2 cells read 73 % and even solid single-toner 2×2
   cells only 87–89 % (W 86.6 %: → Y 4.3, MY 3.7 — neighbours' ink under a 1–1.5-dot misregistration at
   2-dot cells). Discernible 223–255 b/mm² at errors no rung closes.
4. **cmyw c2 on this capture reads 6.4 %, worse than its three 2400 readings (2.8/3.9/4.0 %).** The
   per-plane poses in U12 (solid cells, honest): Y − C = −1.7…−3.4 DOTS and M − C −0.4…−1.75 dots along
   the band (the largest misregistration of the campaign; S16 T12 at y ≈ 236 mm had Y −1.1 dots; U12 sits
   at y 227–246 mm — CORRECTED 2026-10-06 09:50: this item first said 258–276 mm, "the bottom of the
   page", a band-index slip; U12 sits where S16 T12 sat), and the confusion is W → Y 9.0, C 4.6, M 3.5 % —
   white cells taking a shifted neighbour's ink. ANSWERED by the 2400 rescan (041.5p): not the scan mode,
   not the page position — the print's per-plane registration.
5. **c2-K on the same sheet: 4.56 % hard, context-free, at 8 px/dot** (the archival row; the record's
   ctx + PAVA reading at this sampling is 2–5 %); MI 0.74 b/cell = 103 b/mm².
6. **4800 dpi buys registration precision, not cell contrast.** c3 states read as at 2400 (U1 3.65 vs S16
   T2 3.22, different print); cells are soft blobs at 8 px/dot — the scanner's ~860 dpi information
   ceiling (e028 knife-edge) is the limit. What 4800 gave is the sub-dot pose that the layout decision
   needs and a cleaner picture of the per-plane registration field.
7. Per-plane registration on this page (readout medians, dots): M − C from −0.1 to −1.75 in y, Y − C from
   −0.2 to −3.4 in y, both drifting with x (a +0.4-dot x-offset hump at 90–130 mm) and varying band to band
   down the page (the "growing toward the page bottom" first written here rested on the band-index slip
   of item 4; withdrawn). A format at c2 cannot read W cells without per-plane fields and context; at c3
   the margins absorb it (U2 0.54 %, U13 0.08 %).
8. **Not read: T2's texture** (041.5m item 9), the question behind U6, "the keystream-style candidate"
   (041.5n). The band screen scores only the engine's 165/188/212 lpi lattices
   (`measure/e041_band_screen.py:38-40`), so no S17 band has a 283 lpi ±45° peak-over-ring-median score;
   U6 against U1 (T2's layouts, other seed) is owed from the captures already in hand, no paper. Whether a
   random per-cell layout removes the diagonal lattice is unknown, and the generator knob (a keystream
   layout per cell, or X/plus alternation) has no disposition. The one-dot pose slip the lattice threatened
   does not reach a readout that takes per-plane poses from solid cells (041.5n caveats); U6's layout
   itself reads 18.9 %, pose-limited (item 2).

RANKING ON THE M281 after S17 (A4-4mm, 10 % repair, net b/mm²; single prints): c2-cmyw 0.94–1.4 MB
(167–196 at 2.8–4 %, 2400; ~130 at this capture's 6.4 %) ≈ **c3 cmy7-dotmix + orientation ~1.0 MB (144,
2.4 % / 2.5 %)** > c3 cmy7-dotmix ~0.86 MB (124, 0.54 %) ≈ c3 cmy8-dotmix 0.95 MB (136, 3.7 %) > c2-K
0.60–0.74 MB (83–103) > c3-cmyw 0.63 MB (91, 0.08 %) > c3-K 0.31 MB (45). The c3 colour rows are the ones
with margin; c2-cmyw's standing now depends on the registration question (item 4).

## 041.5p S17 at 2400 vs 4800 (2026-10-06 09:50) — the scan mode changes no cell state; 4800 helps only the pose-limited layout reading; cmyw c2 tracks the print's Y − C registration

The same S17 sheet rescanned at 2400 (re-placed on the glass) and read with the same instruments at
`--scan-dpi 2400` (fit 5/5, residual ≤ 0.162 mm; 2632 windows):

| band | state % 2400 / 4800 | layout err (orient/phase) 2400 / 4800 |
|---|---|---|
| U1 cmy8 dot-mixed | 3.76 / 3.65 | — |
| U2 cmy7 dot-mixed | 0.57 / 0.54 | — |
| U3 | 2.96 / 2.90 | 1.73 / 1.71 (orientation) |
| U4 | 5.71 / 5.69 | 15.6 / 11.9 (orientation) |
| U5 | 6.92 / 6.92 | 21.8 / 13.7 (phase) |
| U6 | 7.00 / 7.06 | 24.8 (14.1/17.4) / 18.9 (10.5/13.6) |
| U7 | 2.36 / 2.37 | 2.74 / 2.46 (orientation) |
| U8–U11 c2 dot-mixed | 20.6 / 23.1 / 23.9 / 18.7 vs 20.2 / 22.6 / 23.6 / 18.3 | — |
| U12 cmyw c2 | **6.54 / 6.43** | — |
| U13 cmyw c3 | 0.08 / 0.08 | — |
| U14 c2-K | 4.73 / 4.56 | — |

1. **Scan mode is not a factor for cell states**: every band agrees within 0.5 pp, c2 included. The
   4800 question for STATES is answered: no gain on this scanner (its ~860 dpi optical ceiling).
2. **4800 helps the layout decision exactly where it is pose-limited**: U4/U5/U6 lose 4–8 pp at 2400; U3
   and U7, whose poses are good, read the same. The orientation symbol on the U7 row is scan-mode-robust
   (2.5–2.7 %).
3. **cmyw c2's 6.5 % is the print, not the scan and not the page position.** U12 sits at y 227–246 mm,
   where S16 T12 sat (224–243 mm) — the record's "page bottom" was a band-index slip (041.5o item 4,
   corrected). Across the four cmyw c2 bands printed so far the state error tracks the band's Y − C
   registration (readout medians, solid-cell per-plane poses, dots):

   | band | y (mm) | Y − C (dy, dx) | |Y − C| | M − C dy | state % |
   |---|---|---|---|---|---|
   | S14 B3 | 236–267 | +0.24, +0.42 | 0.49 | +0.08 | 2.82 |
   | S15 R9 | 260–285 | −0.04, +0.67 | 0.67 | −0.05 | 3.86 |
   | S16 T12 | 224–243 | −1.11, +0.22 | 1.13 | −0.55 | 4.00 |
   | S17 U12 | 227–246 | −2.33, +0.30 | 2.35 | −1.14 | 6.54 / 6.43 |

   Monotone in four points, one print each; the per-plane registration varies print to print by more
   than a cell at c2. The readout already samples each plane at its own per-window pose, so what remains
   is physical (a Y dot displaced by > 2 dots lands on a neighbour cell — overlaps the engine then prints
   as it likes) plus the within-window variation of the shift. Levers: the receiver's per-plane page field
   (finer than per window) and context; on the format side nothing at c2. c2-cmyw's standing is
   print-registration-dependent: 2.8–4 % on three prints, 6.5 % on the fourth.

## 041.6 Owed

[2026-10-11: the list below is the operator's ruling of 2026-10-05 13:00, written before S11 was read, and is SUPERSEDED. S11 and S12 were built, printed and read (§041.5b–e); S4 = S13, the PWG raster job, was refused by the firmware's own renderer (041.16p'). `Detail` was tried on S12. The ramp page, the partition line, `settransfer` and phases 2–3 were never run as written: the screener findings (§041.5i–m) overtook them, and so did the band's "digital gap" hypothesis. What is owed at the campaign's end (CLAUDE.md's e041 entry and the synthesis, docs/M281-COLOUR-2026-10-05.md §7): pose refinement for the layout reading; 2×3 cells (e042 §042.6); the dot-mixed cmy7 format (generator layouts + receiver cell model); the `cmy` format (docs/CMY-DESIGN.md v0.2 and its three workplans); another-day controls, S14 printed again first; the loupe on S16's three black bars (§041.5m); the readout tidy-ups (synthesis §7).]

RULED 2026-10-05 13:00 (operator): the three capacity axes stand (cell size
and in-cell pattern; alphabet; code rate + furniture); the screening
dimension continues with, in order, (1) S11 the mixture probe — with K as a
fifth solid state (cmyk5 = {W,C,M,Y,K}, K through SetNeutralAxis
eTonerBlack, log2 5 = 2.32 bits/cell, a packed codec like cmy7's; K
absorbs all three channels so the fifth state is cheap in margin) and the
dot-mixed overlaps; (2) S12 route equivalence — the same patches as a
PostScript indexed-DeviceRGB image, deciding whether production stays
PostScript with a palette change; (3) S4/S13 PWG raster cmyk_8 over 9100
(the verified `S4-pwg-cmyk8.pjl`, sha `d65970ab6927e6e4…`, F's page as
device CMYK 0/255, `@PJL ENTER LANGUAGE=PWG_RASTER`), the last door to solid
overlaps, with the back channel held open. Print each when ready on the
standing go; the operator scans.

- S10p2 MEASURED: every state prints at 0–2 % cell error in isolation; the
  RGB value is not the lever and S10 is withdrawn. NEXT (S11, the MIXTURE
  probe, same banded construction): patches whose cells are drawn at
  random from an ALPHABET, one alphabet per patch — {W,M}, {W,Y}, {W,C},
  {W,C,M}, {W,M,Y}, {W,C,Y}, {W,C,M,Y}, {C,M} (no white), {C,M,Y}, the
  four overlaps with white, and the full eight-state F alphabet — at two
  or three ink fractions, under the three methods, replicated; readout =
  per plane d'/hard error against the known pattern as a function of the
  alphabet. It tells WHICH neighbours cost M and Y (another plane's cells
  beside them, overlap cells, or white's absence) and whether a reduced
  alphabet (the cmy4 fallback: W + single toners, no overlaps) survives
  the engine — the first measurement that can price cmy4 against cmy8 on
  this printer before any format work. Palettes to carry: cmy8-corners
  (S9's), cmy8-solidM (M → (240,0,192)), cmy4-solid (C (0,255,255),
  M (240,0,192), Y (255,255,0)); the bar-screen map says the single toners
  can be solid and no overlap can, so the expected outcome is cmy4 clean
  and cmy8 failing in its overlap states whatever the palette. S3 / S3b / S2-banded stay on
  hold; S3 has no reason left to print (S3c); S5 WITHDRAWN (cmy7 ruled a
  dead end 2026-10-05).
- The unscreened pieces, after the sweep: (i) a RAMP page — tint ramps
  (10/25/50/75/90 %) of C, M and Y across the full width and height —
  shows every unscreened piece at a glance AND separates "halftoning
  skipped" (the ramp prints as a step function in the piece) from
  "values forced to solid upstream" (the ramp prints solid); (ii) the
  PARTITION line from the columnar-pipeline reading: one image against
  several abutting images with identical pixels, white padding that moves
  the bounding box but not the marks, ReadImage block height — one
  variable per sheet; if partitioning moves, multiplies or widens the
  unscreened region, it is a route, not a defect. S4 (PWG
  cmyk_8 on 9100 through `ENTER LANGUAGE=PWG_RASTER`) stays a last-resort
  gamble, not a refusal: the IPP format list does not speak for the 9100
  personality list, which names PWG_RASTER.
- The band: S8 says raster/paper-fixed, the fine map says (nearly)
  unscreened — the working hypothesis is now a DIGITAL gap in the engine's
  halftone pass (see the corrected reading in §041.4); the tint probe page
  above is the test; a K-only sheet (C, c2-K) tells whether the K path has
  it.
- Two zero-cost witnesses on the next PostScript sheet: `Detail` against
  `Smooth` on the three `ColorSmart*Halftone` operators (untested; a
  screen-SELECTION lever, not a bypass) and a step `settransfer` (the
  interpreter's last device-value stage after the ColorSmart conversion;
  tells whether anything below ColorSmart and above the video path is
  reachable from a job). Each needs its own tint patch beside the field.
- Phase 2 on a winning rung: the e028 colour discovery sheet through that
  route (decides cmy8 vs a triple-free variant), then sheet E (c2 CMY8
  q 0.9) or D.
- Phase 3 if every rung screens: density sliders (M/Y midtone and shadow
  up, highlights down), the column-group pool for c3.

## Addendum 2026-10-09 — capture hashes

Correction: S8's scan (`scratch/e041/e041-s8-2400.tiff`, row 041.11s) is sha256
`7d393eb85cdeb1ed0843b61865b7f25788c515a961b1eb6bca014afbeebe8041`; the `0d747c15be6d9f76…` in that row is wrong,
`results/README.md` is right. Full sha256 for the rows that carry a prefix or none, from the raw-hash pass of 2026-10-09 (sha256 over the retained evidence)
(1,718,864,112 B each, under `scratch/e041/`):

| row | capture | sha256 |
|---|---|---|
| 041.7s | `e041-s7a-2400.tiff` | `9025aabd1d49c6db50ae6126c5d7b11c606a37b45ff8f9653f109280fa302369` |
| 041.8s | `e041-s7b-2400.tiff` | `d40ca8f1528f77cbe2c15fea0f46f659e455e76753a626327bb6fb56e5c640f0` |
| 041.9s | `e041-s3c-2400.tiff` | `6a603cfda6d9ae3b07f1a6118fb651ad8066bca2395f081b99f3df69f07b53c1` |
| 041.11s | `e041-s8-2400.tiff` | `7d393eb85cdeb1ed0843b61865b7f25788c515a961b1eb6bca014afbeebe8041` |
| 041.14s | `e041-s10p2-2400.tiff` | `2c4110633e1e6dd714341f5f8368066ba95b2180879557ea5ecf27577a4707c1` |
| 041.15s | `e041-s11-2400.tiff` | `0e7bea7c9c38f251215319bd73c8a8bf93eb96d7992dd8a070210835b62dab07` |
| 041.17s | `e041-s12-2400.tiff` | `76d6f3c0a34407c7c502752f9a5d5e169dbc9d638609aeca2327d6cc36156cc1` |
| 041.18s | `e041-s14-2400.tiff` | `198a25215496096620d677d90bc4dfbb54dae364c9ebc6d2751d1ab43593b303` |
