# Experiment 007 — office-printer discovery (DISC-1)

**Question.** What IS the unknown office printer as a data channel: native
addressable dpi (both axes), driver-path fidelity (raw-ish vs re-rasterized),
mono or color, dot morphology (isolated-dot survival, min line/hole widths,
checkerboard closure), tone transfer under stochastic dither, overlap/screen
behavior, transport signature r(x)/r(y), true printable area — AND whether
the RIP *grants a requested resolution* — all from ONE two-page job, with
the engine's own self-report printed on each page.

This is the anti-M281 job: everything measured at home (600 dpi native, raw
9100, /HWResolution [600 600]) is UNKNOWN here, so page 1 of `gen_disc1.py`
requests nothing the device could reject or misinterpret:

- **LanguageLevel 2 only**; no PJL, no vendor operators.
- **Page 1: NO /HWResolution operation before its showpage** — the device
  default rules; the machine strips *report* the default (RD) and effective
  (RE) resolution instead of asserting one. (Deliberate divergence from
  every home job.)
- **PageSize [595 842] inside a stopped guard only** (a rejecting or
  Letter-substituting RIP cannot kill the job; PS/IB fields report what was
  actually granted).
- **Margins ≥ 12 mm** for all content (unknown printable area); only the
  margin probes deliberately march past 12 mm, down to 4 mm, to *find* the
  boundary.
- Multi-resolution blocks address 300/600/1200 (page 1) and 1200/2400
  (page 2) grids via `psgen.put_bitmap(dpi=...)` — device-independent
  points, so every block is geometrically correct whatever the granted
  resolution.

**Page 2 = ACTIVE resolution probe**, blast-radius-isolated by the page
boundary: page 1 is complete and shipped before ANY resolution operation
executes. After page 1's showpage: a guarded resolution ENUMERATION — for
each r in 300/600/1200/2400, `<< /HWResolution [r r] >> setpagedevice`
inside a stopped guard, then a read-back of the granted x-value — ending
with the definitive guarded [1200 1200] request that page 2's content
prints under. The four read-backs are recorded as RQ300..RQ2400 in page 2's
strip payload (free-area keys before LAY, plus a PG=2 page marker —
stripdec's field parsing is byte-for-byte unaffected; RD still reports the
job-start default). Three outcomes, all informative: **refused** (RQ* = RE
= RD default — passive channel only), **granted-clean** (higher addressable
grid usable), **granted-but-corrupt** (RIP says yes but the raster breaks —
compare page-2 gratings/PN against the page-1 no-request control and the
fresh-label 600-grid c3 control on page 2 itself). Measured gs 10.x
behavior, encoded in the preflight: a CLI `-r` pins the device (all RQ*
read back the CLI value); without one, gs grants every trial.

**Artifact.** `gen_disc1.py` → `build/disc1.ps` (TWO pages) +
`build/disc1_manifest.json` + `build/disc1_gt/*.npy`. SEED
`paper-store/exp007-disc1`, J=854d2565, byte-identical regeneration,
sha-gated. 195 patches (165 page 1 + 30 page 2), 46 plus marks, 3.35 MB.
Page 1 is byte-for-byte the original single-page DISC-1 content (verified:
reconstructing a one-page job from the page-1 slice reproduces the v1 sha
`c9a42fba…`).

## Page-1 block inventory (what each block measures; positions in mm, top→bottom)

| block | where | measures |
|---|---|---|
| header labels | y 12–25 | human protocol; J/S/regen bootstrap |
| machine strip 1 / 2 | y 18.0 / 276.0, x 12 | print-time self-report: LL, RD (default res = native candidate), RE, PS, IB, PR, V, RV, SN; exp002 LAY=1 format, `stripdec.py` decodes unchanged. Module = max(3, floor(dpi/100)) dots (exp007 deviation from exp002's max(4, round(·)): fits 12 mm margins down to 300 dpi; stripdec self-scales). Two copies = damage margin + top/bottom transport comparison |
| corner marks | centers (14.7, 195.3) × (14.7, 282.3) | chiral rotation/mirror + global affine (gen_calpage geometry, byte-identical) |
| plus-mark lattice | 25.4 mm grid, free space (46 placed) | absolute physical-inch scale + warp field, resolution-independent |
| resolution ladder | rows y 27 / 38.5 / 50 (300/600/1200 grid), x 34–100 | per-grid 1-on/1-off + 2-on/2-off gratings H/V, isolated dots @8-dot pitch, single-width line pairs — which addressing grid the engine actually resolves; H/V anisotropy; Nyquist closure vs grid |
| morphology ladders | rows y 63 (600) / 74 (1200), x 34–136 | line widths 1–4 dots H/V, checkerboards 1×1/2×2, white holes 1–4 dots — dot gain, min-feature and min-white (the M281 analogs: +0.4 dot/edge, 1-dot features dead) |
| PN cell fields | y 86, x 34–141: c1..c6 @600 (12×12 mm), c2/c3 @1200 | raw cell BER vs cell size on this engine; GT saved for all 8 |
| tone wedge | y 103, x 34–181 | 10–90% seeded random-dot dither + 100% + paper gap: tone transfer WITHOUT beating against an unknown device screen (ordered dither would alias) |
| emission canaries | y 116, x 34–121 | C/M/Y/K single-plane imagemask solids; 15 mm CMY c3 `put_cmyk_bitmap` composite (3×50% planes, per-plane GT); C+M overlapping-mask pair — color vs mono, knockout/overprint behavior, re-screening fingerprint. On a mono engine these print grey/black/blank: that degradation is the datum |
| r(y) strip | x 15, y 27–274 (4 mm wide) | 3-on/3-off horizontal K lines: transport function along the feed axis (001-style instrument) |
| r(x) strip | y 269, x 21–195 (4 mm tall) | 3-on/3-off vertical K lines: fast-axis counterpart |
| margin probes | 9 ticks/edge, 2×2 mm, edge gap 12→4 mm in 1 mm steps | true printable boundary per edge (outermost surviving tick brackets it) |
| quiet zone | (150, 136) 30×30 | white/noise-floor reference, contamination hunt |
| END sentinel | y 280.4 | "END 854d2565 exp007 disc1" — stream-completeness check, LAST element |

Error containment (exp002 idiom): device query + payload + strips stream
before any inline-data bitmap; bitmaps small → large; the one cmyk composite
after all masks; sentinel last-in-page.

## Page-2 block inventory

| block | where | measures |
|---|---|---|
| enumeration + definitive request | stream, before page-2 content | RQ300/600/1200/2400 grants (payload-recorded); page prints under the guarded [1200 1200] request |
| header labels | y 12–25 | page marker + probe protocol/outcomes |
| machine strip 1 / 2 | y 18.0 / 276.0, x 12 | same LAY=1 format; payload preamble `PHCAL1;PG=2;RQ300=..;RQ600=..;RQ1200=..;RQ2400=..;` then the standard fields; RE = post-request grant, RD = job-start default |
| corner marks | page-1 positions | registration (p2/corner_*) |
| resolution rows | y 27 (1200 grid) / 38.5 (2400 grid), x 34–100 | 1-on/1-off + 2-on/2-off gratings H/V, isolated dots @8, line pairs — does the granted grid actually resolve |
| line-width ladder | y 50, x 34–92 (1200 grid) | widths 1–4 dots H+V at the definitive grid |
| PN fields | y 63: c2/c3/c4 @1200 (x 34–73) + c3 @600 control (x 74.5) | cell BER at the granted grid; the 600-control (fresh rng label) separates "page-2 raster corrupt" from "1200 features too fine" |
| END sentinel | y 280.4 | "END 854d2565 exp007 disc1 p2" — the job's LAST drawing op |

## Pre-flight (gates the print) — GREEN 2026-07-05 (v2, two-page)

`env/bin/python tests/test_disc1.py` and `pytest -q tests/test_disc1.py`
(9 tests): byte-identical regeneration; stream structure (%%Pages: 2, page 1
request-free, exactly one guarded PageSize request + exactly five guarded
/HWResolution operations ALL after page 1's showpage, both sentinels
last-in-page, ≤ 10 MB); geometry in 2400-grid units (bounds incl.
margin-probe exception, per-page disjointness with composite grouping,
labels clear); GT integrity; gs pnggray −r600 pixel-exact for pn600/c1..c6 +
morph600/chk1 (p1) and p2/pn600/c3_ctl (p2), −r1200 pixel-exact for
pn1200/c2 (p1) and p2/pn1200/c2 (p2); stripdec round-trips on both page
renders (p1 plain payload, p2 PG=2 + RQ*); and the enumeration plumbing
proof — gs WITHOUT a CLI −r grants every trial (RQ300..RQ2400 =
300/600/1200/2400, page 2 rasters at the definitive 1200), while a CLI −r
pins all read-backs to the CLI value. NOTE for 007.1: on the real RIP the
RQ read-backs may also be *lies* (granted in the pagedevice dict but not in
the marking engine) — that is exactly what the page-2 gratings/PN vs
controls disambiguate.

## Print protocol (at the office — NOT scripts/print_plane.sh)

1. ONE job, TWO sheets, A4, plain paper. Take `build/disc1.ps` (sha256 in
   the manifest; regen with `gen_disc1.py` if in doubt). Keep both sheets.
2. Most-raw path available, in order of preference:
   - raw queue: `lp -d <queue> -o raw disc1.ps` (or `lpr -P <queue> -o raw`);
   - direct socket if the printer exposes 9100 and policy allows:
     `nc <host> 9100 < disc1.ps`;
   - otherwise: print the .ps through any PostScript-capable driver at 100%
     scale, "fit to page" OFF, no duplex, default quality.
3. **Hand-note in pen on sheet 1's margin**: printer model, queue/driver
   name, which of the three paths was used, date. Mark sheet 2 "p2" if the
   printed header is illegible. (The strips record what the RIP says; the
   pen records what you did.)
4. Loupe sanity check before scanning: strips present top+bottom on BOTH
   sheets? Both END sentinels present ("... disc1" / "... disc1 p2")? Any
   block obviously blank/clipped? If page 2 is missing entirely, that is a
   datum (RIP died on the enumeration despite the guards) — page 1 is
   designed to survive it.
5. Log the run below: date, printer, path, media, oddities.

## Scan protocol

1. At home (known flatbed, exp001/002 characterization applies), BOTH
   sheets: 1200 dpi GREY **and** 1200 dpi COLOR (color mainly for sheet 1's
   canaries; grey suffices for sheet 2), flat, 0°,
   descreen/sharpen/auto-contrast OFF, all four page edges in frame (margin
   probes + corners live there).
2. Optionally the same scans on the OFFICE scanner (if it has a flatbed):
   cross-characterizes an unknown scanner against the page, and the home
   scanner against a second engine. Keep modes separate — never mix grey and
   color scans for absolute y (002.0b).
3. Scans into `scans/` (untracked), sha256-referenced in the run log below.
   Suggested names: `disc1-<printer>-<home|office>-p<1|2>-<grey|color>.png`.

## Analysis (TBD → 007.1)

007.1 will bring the analyzer: stripdec on all four strips (self-report vs
observed, RQ* enumeration verdict vs page-2 measured raster), granted-
resolution + scale from the plus lattice and grating FFTs, per-grid
resolution verdict (incl. page-2 1200/2400 rows vs the RQ claims), morphology
thresholds, PN BER vs cell on both pages (p2 c3@600 control vs p1 c3@600 =
did the resolution request change the 600-grid channel?), tone curve, canary
classification (mono/color, knockout/composite/screened), r(x)/r(y)
extraction, and the printable-area bracket from the margin probes.
Deliverable: a first ChannelParams draft for the office engine + a
go/no-go on whether it can carry archive sheets at all — and at WHICH grid.

## Run log

- 2026-07-05 — sheet built + preflight green (v1, single page).
  `build/disc1.ps` sha256
  `c9a42fba7f778293035e39eefbc31ee416d55850e2b9d9c0aa6439d8eb572017`
  (1 621 771 bytes, 163 patches, 46 plus marks). Superseded before printing.
- 2026-07-05 — v2: PAGE 2 active resolution probe added (enumeration
  RQ300..RQ2400 + definitive [1200 1200], all guarded, all after page 1's
  showpage; page-1 content verified byte-identical to v1). Preflight green,
  9 tests (incl. a Clean7Bit ASCII guard — first cut had a UTF-8 em-dash in
  a page-2 comment). `build/disc1.ps` sha256
  `fb58afc5b33126bf3bba9f46d250c738f62f1e5a320db9d5c43f5a5818991e7a`
  (3 349 831 bytes, 195 patches: 165 p1 + 30 p2). Not yet printed.

| 007.0 | 2026-07-05 ~22:45 | PRINTED home baseline (user-authorized): <host> raw 9100 via print_plane.sh, one job = TWO sheets (p1 default-res portable page, p2 active 1200 probe + RQ enumeration), 3,349,831 bytes, sha confirmed at send | build/disc1.ps | fb58afc5b33126bf3bba9f46d250c738f62f1e5a320db9d5c43f5a5818991e7a |

## 007.1 — HOME baseline results (2026-07-05, scans e007off-page-1/2)

Surprise #1: the sheet is DUPLEXED — the portable header (PageSize only, by
design) leaves Duplex to the device, and the M281's PJL default is
DUPLEX=ON. Pages 1+2 share one sheet front/back. Note for protocols: expect
duplexing on any printer with duplex defaults; page 2 carries a
duplex-backside confound (see below).

Strip bootstrap: 4/4 strips decode, CRC ok, full self-ID (PR=HP Color
LaserJet MFP M281fdw, LL=3, V=3017). Skews 0.10-0.41 deg. RQ enumeration
recovered from the raw payload (stripdec's `fields` dict only surfaces
known keys — parser nit, payload complete).

**M281 resolution claims, both layers, now complete:**
- PJL claims {300, 600} (005.0 recon).
- **PS claims {600, 1200}: RQ300=600 (300 REFUSED at PS!), RQ600=600,
  RQ1200=1200 (GRANTED), RQ2400=1200 (refused, sticky).** RD=600x600,
  RE=1200x1200 on page 2 — page 2 physically rendered under the grant.

**PN-field scores (affine+phase sampling, median rule, GT cell-downsampled):**

| field | page 1 (default 600) | page 2 (granted 1200) |
|---|---|---|
| pn600 c1/c2/c3/c4/c5/c6 | 36.1 / 14.1 / **0.89** / 0.63 / 0.83 / 3.0 % | — |
| pn1200 c2/c3 (c4) | 49.9 / 50.3 % (unreadable) | 49.7 / 49.5 / 49.5 % (unreadable) |
| pn600 c3 control | — | **10.5%** (12x worse than page 1's 0.89%) |

Reading: (1) the discovery instrument REDISCOVERS the known engine truths
blind — c1 dead, c2 marginal ~14%, c3+ solid — validating DISC-1 against
001/002 ground truth. (2) 1200-ADDRESSED content is unreadable on this
engine in BOTH modes. (3) Under the granted 1200 mode, even 600-addressed
content degrades 12x — "granted-but-broken" quantified, closing the 001
mystery loop (PS grants what PJL never claimed, and breaks). CONFOUND: page
2 is also the duplex BACK side; separating 1200-mode damage from
duplex-backside damage needs one disambiguation job (disc1 with Duplex
false, two sheets) — pending user go. (4) pn600/c6 at 3.0% > c4/c5 —
affine-only sampling drift across the patch is the likely cause, not
physics; discovery-grade tolerance.

Office protocol unchanged: print build/disc1.ps as-is tomorrow; if the
office default duplexes, the pair shares a sheet — fine, scan both sides.

## 007.2 — Xerox AltaLink C8245 SCANNER characterization (2026-07-06, same-sheet pair)

The home disc1 duplex sheet rescanned on the office Xerox at 600 dpi
(source TIFFs tiff_jpeg at ~0.075 bpp — heavy default compression; DOC.tif
and DOC(1).tif byte-identical, one sheet's scan missing). Same physical
sheet as the home 1200 scans => printer factored out entirely. Full numbers:
build/xerox_scanner_char.json. Highlights:

- Scale +0.3-0.6%, NEAR-ISOTROPIC (home flatbed is y-only) — different
  transport signature; residual rms 2.53 dots (~1.7x home, JPEG-limited).
- Strip bootstrap works on scanner #2 (p2 grey 2/2 CRC at native 600; p1
  COLOR path needs 2x upsampling before stripdec — now protocol). The p2
  y-stretched modules match the home read => print-side raster stretch of
  the granted-1200 mode, cross-scanner confirmed.
- **The key split: sampling is innocent, compression is guilty.** Matched-
  sampling control (home scan at 600) barely degrades (c3 0.89->1.46%);
  the Xerox path collapses c2 14->43%, c3 0.9->31%, c4 0.6->13% while c5/c6
  are untouched — default JPEG erases features below ~5 dots (~0.2 mm).
  Office scanner verdict: triage/self-ID/coarse blocks only, UNLESS its
  compression can be disabled (worth checking the scan-profile settings:
  TIFF-uncompressed/PNG/'highest quality' => possibly a usable 600 path).
- Paper noise std crushed to 0.7 (home ~2.5) with 8-px blockiness ratio
  1.68 — the JPEG signature, not a better sensor.

**007.2 addendum (third scan = E006-BW, e006bw-xeroxscan-col.png 5f074288…):**
with PROPER strip-tracked warp, the Xerox-600 path is far less destructive
than the crude-scorer PN numbers suggested: B1 c2 bands 13.6→19-20.6% hard
(+6pp, not +29), RLL 15.5→16.8% (+1.3pp only). The 007.2 PN table
overstates the Xerox penalty at c2-c4 — the affine+phase scorer has no
local warp and compounds with JPEG softening. Corrected reading: JPEG costs
~+6pp at c2, little at RLL-class features; fine-cell decode through this
path is degraded but not destroyed. NEW finding: the 16-context detector
MISFIRES on the JPEG channel (ctx 20.6% > hard 19.0% — block-correlated
errors violate the development-context model); use hard/global detection
on office scans. Strip lock 1.00; scale +0.2-0.4%; the 9.9MB TIFF (vs
2.6MB) shows fixed-quality JPEG spending bits on incompressible payload.

## 007.3 — office session handoff (2026-07-06)

USER ACTIONS at the office (Xerox AltaLink C8245, port 9100 exposed):
1. Printed the ENTIRE experiments/*/*/*.ps stimulus library on the AltaLink
   via raw 9100 (~a dozen sheets: gridtest, linetest, calpage, composite_
   probe, overlap2, modprobe, e004, e006bw, e006c, disc1). Full stimulus
   set now exists on a second engine. MOST NOT YET SCANNED.
2. Eyeball: LOOP-C color tint MUCH more uniform than home (healthy CMY).
3. Scanned 3 HOME-printed sheets on the AltaLink's own scanner (600 dpi,
   tiff_jpeg): disc1 p1 col, disc1 p2 grey, e006bw col (DOC*.tif ->
   scans/disc1p1-xeroxscan-col.png, disc1p2-xeroxscan-grey.png,
   e006bw-xeroxscan-col.png).
PLAN: bulk-scan the office-printed pile on the home M281 ADF (600 dpi) for
triage; home flatbed (1200) reserved for real numbers.

FINDINGS: see 007.1 (home baseline resolution probe), 007.2 + addendum
(AltaLink scanner characterization), build/xerox_scanner_char.json. Compact
engine-facts version lives in CLAUDE.md (SECOND ENGINE block).

OPEN (carried to next conversation):
- Bulk office-ADF triage of the printed library (self-ID + coarse gate +
  which sheets earn a flatbed pass).
- Home-flatbed 1200 scan of one office-printed DISC-1 = AltaLink resolution
  + emission ground truth AND the c3@1200-through-a-good-scanner Nyquist
  question (3 px/cell, 2x density vs c3@600 — nets positive or not?).
- AltaLink scan-profile check: can JPEG be disabled (uncompressed TIFF/PNG)?
  Sampling was proven nearly free, so a clean 600 path could be usable.
- Healthy LOOP-C: AltaLink color prints as the non-starved-Y measurement.
- Nyquist framing (durable): decode is synchronized-sampling of a KNOWN
  lattice, so 1 px/cell works while the cell fundamental stays < scan
  Nyquist; it fails by aliasing once it crosses. c2@600/600-scan = marginal
  inside (works, ~19% w/ JPEG); c2@1200/600-scan = at Nyquist (dead);
  c3@1200/600-scan = aliases (dead). px/cell ladder: 6 solid, 4 marginal,
  2 Nyquist-edge, <2 dead.

## 007.4 — bulk ADF triage of the office pile + flatbed scan inventory (2026-07-06)

**Triage method.** All 25 pile pages scanned on the home M281 ADF at 300 dpi
color (`scans/adf-triage/adf00..24.png`, renamed from `adf.png`/`adf N.png`).
Identification = printed header transcription + layout match vs 50-dpi gs
renders of all 18 library pages + NCC cross-correlation, each page verified
by an independent second pass (25/25 identified, all `certain`). Full
per-page records (headers verbatim, quality notes):
`scans/adf-triage/adf_ids.json`.

**Pile contents (25 = 18-page office library + 4 extra office prints + 3
home-printed sheets that rode along):**

| adf | page | engine |
|---|---|---|
| 00-05 | 001_patterns p1 K / p2 C / p3 M / p4 Y / p5 reg / p6 MIC-blank | Xerox |
| 06, 07 | gridtest, linetest | Xerox |
| 08 | calpage CAL-1 (strip echo `PR=Xerox AltaLink C8245`, V=3021.101) | Xerox |
| 09, 10, 11 | composite_probe, overlap2, modprobe | Xerox |
| 12 | e004 finalists (unmarked) | Xerox |
| 13, 21 | e006bw ×2 (identical rendering, Y canaries healthy both) | Xerox ×2 |
| 14, 22 | e006c ×2 (identical, Y healthy both — NOT the starved-Y home sheet) | Xerox ×2 |
| 15, 16 | disc1 p1+p2 pair (unmarked) | Xerox |
| 18, 19 | disc1 p1+p2 pair (pen "xerox") | Xerox |
| 17 | pilot_viz | Xerox |
| **20** | disc1 p1 — lighter greys, washed fine-pitch, duplex ghost squares | **HP M281** (the 007.0 duplexed sheet, front; back not ADF'd) |
| **23** | e004 finalists, pen **"First print"** | **HP M281** (the 004.0 sheet; attribution corrected by user 2026-07-06 — "First print" marks the HP output, NOT an office first print) |
| **24** | calpage CAL-1 (strip echo `PR=HP...M281fdw`, V=3017) | **HP M281** (the 002.0 CAL-1) |

Triage by-eye findings (300 dpi, to be quantified in 007.5):
- **AltaLink prints isolated 1-dot K marks** (001 p1 dot grids and linetest
  1-dot lines visibly present — the M281 erases both).
- **AltaLink honors overprint on per-plane mask paths**: composite_probe P3
  row (setoverprint+OPM) and ALL THREE overlap2 B-section CM probes print
  dark navy (overlap preserved) where M281/gs semantics knock out to the
  topmost plane. The Layer-0 emission-path freeze is M281-SPECIFIC.
- K-only pages print neutral K on the AltaLink (measured chroma ≈ scanner
  noise floor on adf00/13/16/20/21) — no CMY-composite black.
- Y healthy on every office sheet (plane page, canaries, calpage Y row).

**Flatbed scan inventory (home M281 flatbed, 1200 dpi, enhancements OFF,
all in `scans/`, all office-printed sheets):** 12 scans, one pass each
(loop pages: multi-scan 3-4x re-placed passes still pending).

| file | content | mode | sha256 (first 16) |
|---|---|---|---|
| xerox-cal-hp-scan.png | CAL-1 | color | 7c64d565b1906d1e |
| xerox-comp-hp-scan.png | composite_probe | color | 1d212c9bf0b96fa2 |
| xerox-disc-1a-p1-hp-scan.png | disc1 p1, pair A | color | d95bc60a990ae396 |
| xerox-disc-1a-p2-hp-scan.png | disc1 p2, pair A | color | 96714792089416a6 |
| xerox-disc-1b-p1-hp-scan.png | disc1 p1, pair B | color | 174ba660a0574a5b |
| xerox-disc-1b-p2-hp-scan.png | disc1 p2, pair B | color | 75ae2aa78145f225 |
| xerox-loop-bw-hp-scan.png | e006bw | grey | fdc06f554b5b11bb |
| xerox-loop-c-hp-scan.png | e006c | color | 1dccecf5ab2d479f |
| xerox-mic-blank-hp-scan.png | 001 p6 MIC blank | color | 7d910a2e7abf3e2a |
| xerox-overlap-hp-scan.png | overlap2 | color | 96666e33e83c7422 |
| xerox-e004-finalists-hp-scan.png | e004 (the UNMARKED Xerox sheet) | color | 862fb8a8d08f7677 |
| xerox-001-patterns-K-hp-scan.png | 001_patterns p1 (K) | color | a966a62c145ccc83 |

Workspace cleanup (2026-07-06): flatbed scans promoted scratch/ -> scans/;
ADF triage set -> scans/adf-triage/; the three office-scanner source TIFFs
renamed DOC*.tif -> scans/xeroxscanner-orig-{disc1p1-col,disc1p2-grey,
e006bw-col}-600.tif (originals of the 007.2/007.3 promoted PNGs; the trio is
now complete — p1 color, p2 grey, e006bw color); seven scratch files verified
byte-identical to their promoted scans/test-scan-* copies and deleted.

## 007.5 — pre-registered goals for the flatbed batch analysis (2026-07-06)

One agent thread per scan group; env/bin/python; measured-simulator/analyzer
reuse where entry points exist. Questions, stated before looking:

1. **DISC-1 office scoring (pairs A+B, p1+p2)** — the 007.1 pattern on the
   AltaLink: strip self-report (RD/RE/PS/PR + p2 RQ300..RQ2400 enumeration
   verdict), PN BER ladder both pages, morphology/wedge/canaries/margins
   blocks (unscored even for home — build `analyze_disc1.py`), r(x)/r(y).
   KEY QUESTION (open since 007.2): does office-printed c3@1200, scanned on
   the home 1200 flatbed (3 px/cell, 2x areal density), net POSITIVE vs
   c3@600? Pair A vs B = print-to-print stability for free.
2. **MIC hunt (001 p6 blank)** — 002.0a point-process pattern at 1200 color:
   does the AltaLink lay tracking dots? A yellow-dot lattice would be a
   channel contaminant AND a DESIGN R3 concern for archive sheets.
3. **CAL-1 office** — analyze_calpage on the AltaLink print: per-plane
   c3 BER, Y-plane health (vs home 0.55 rate / D 0.772), crosstalk matrix
   cond(A), banding, margins, drift. First ChannelParams draft for engine 2.
4. **LOOP-BW office** — analyze_e006bw with strip tracker (LEGAL geometry):
   B1 c2 + RLL band numbers on a healthy-K second engine; strip-vs-genie gap
   vs the home +5.8 pp; canary K vs same-day CAL.
5. **LOOP-C office** — analyze_e006c, 3-training-band loop protocol: THE
   healthy LOOP-C number (home starved-Y record low was 0.770 b/cell =
   47.7 b/mm²; CAL-1-class Y should beat it decisively). Blind-EM from
   on-page furniture (the 006.2 failure mode check on a healthy channel).
6. **Emission paths (overlap2 + composite_probe)** — quantify the triage
   finding at 1200: which paths knock out vs preserve overlap on the
   AltaLink; is preserved overlap CONTONE or SCREENED (FFT screen hunt, lpi/
   angle); single-plane mask bit-fidelity. Is there a PS escape hatch on
   THIS engine that the M281 lacks?
7. **e004 finalists office** — analyze_e004 four-class decode: A3/A4/B1/B2
   leaderboard on engine 2 vs home (A3 1.90 b/cell best / B1 92.8 / B2 82.2
   b/mm² day-2); does the multi-sheet-minima rate ladder tighten or widen?
8. **001-patterns-K office** — quantify the 1-dot-marks-print finding:
   isolated dot survival, Nyquist 1-on/1-off closure, edge gain per axis,
   H/V anisotropy, cell 1/2/3/6 field BER vs the M281 ladder (c1 dead /
   c2 11% / c3 2-3.7%). Is c1 or c2 ALIVE on the AltaLink?

Prior expectations to test against (from triage + 007.2): healthy CMY, dense
Dmax, isolated dots alive, overprint honored; risk items: unknown screen on
composite paths, JPEG-free this time (home flatbed), duplex show-through on
none (all office sheets single-sided pairs).

## 007.6 — flatbed batch RESULTS (2026-07-06, 9 analysis threads, single scan/sheet)

All numbers: office AltaLink prints, home-flatbed 1200 dpi single scans
(color, loop-bw grey), env analyzers; per-thread JSONs + scripts in the
session scratch `analysis/` dirs, durable reports in experiments/*/build/.
Headline leaderboard (b/mm² unless noted; home comparator in parens):

| metric | office | home |
|---|---|---|
| A3 7st-c3 cross-tile (e004) | **2.150 b/cell = 133.3 — new record** | 1.896 = 117.6 (004.0) |
| A4 {7+K}-c4 cross-tile | 2.685 = 93.6 | 2.458 = 85.7 |
| B1 c2-K ctx / recal (e004 tiles) | 5.48% / 0.760 = **106.1** | day-2 8.15% / 92.8; day-1 109 |
| B2 RLL i2w3 (e004 tiles) | 13.65%, 0.1489 b/dot = 83.1 | 13.83%, 0.1473 = 82.2 |
| LOOP-C page MI, loop-legal | **1.442 b/cell = 89.4** | 0.770 = 47.7 (starved-Y) |
| LOOP-BW B1 strips-alone ctx / MI | 7.32% / 0.680 = **94.8** | 13.59% / 68.2 single (73.5 4-scan) |
| CAL-1 c3 hard K/C/M/Y | 3.53/4.45/4.64/**5.51**% | 3.74-4.46/3.57/3.81/7.18% |
| K encode ladder (001 p1) | c1 31% / c2 12.7 / c3 2.60 / c4 1.36 | c1 dead / 11.2 / 2.03-3.74 / — |
| DISC-1 pn600 c3 (pairs A/B) | 2.50-3.09% (v4 2.57/2.69) | 2.67% v4 re-read (see corrections) |

**(1) DISC-1 / resolution: the AltaLink is a FIXED-600 PS device.** 10/10
strips CRC-ok (PR=Xerox AltaLink C8245, LL=3, V=3021.101, SN refused);
RD=RE=600×600 on every page; p2 enumeration RQ300=RQ600=RQ1200=RQ2400=600 —
every /HWResolution request silently refused, both directions (mirror image
of the M281, which grants 1200 and y-stretches). 1200-addressed content is
POINT-SAMPLED onto the 600 grid (pn1200/c2 ≡ pn600/c1 within 0.5 pp;
c4@1200 ≡ c2@600; c3@1200 = 24-26% deterministic alias floor). **The
pre-registered c3@1200 question closes NEGATIVE**: BSC framing 39-48 b/mm²
vs c3@600's 47-50 — no 1200 grid is reachable via PS to begin with (untested
residue: PJL/PCL paths). Print-to-print (pair A vs B): c3 Δ0.12-0.59 pp,
c2 Δ1.9 pp, print scale reproducible <0.01% — excellent same-day stability;
office x-scale is TRUE (px/dot 2.0000 vs home 2.005). Office r(x) wander
2.6-2.7 dots p2p (~1.7× home); r(y) steps scanner-side as known.

**(2) 007.1 RETROACTIVE CORRECTIONS (two independent scorers agree: rebuilt
007.1-scorer + v4 decoder, same e007off scans):**
- The **median-rule PN threshold has a deterministic class-imbalance error
  floor** (forces 50% ink); 007.1's c4 0.63%/c5 0.83%/c6 2.99% ARE that
  floor (true c4-c6 ≈ 0-0.35%); the "c6 3.0% = affine drift" note was wrong.
- Home **pn1200 fields are NOT ~50%/unreadable** — they read 24-31%, the
  same alias floor as the office (old scorer failed to phase-lock).
- Home **p2 c3_ctl is ~2.9-3.5%, not 10.5%** — the "granted-1200 mode
  degrades 600-addressed c3 12×" headline DOES NOT REPLICATE (same-
  instrument delta +0.9 pp, within office cross-page spread; the granted
  mode's real effect = the known raster y-stretch, geometry-level,
  trackable). **Queue item (d), the Duplex-false disambiguation print, is
  largely demotivated** (duplex-backside confound remains on the +0.9 pp).
- 007.1's official p1 c3 0.89% was a warp-lucky single-patch read (method-
  matched re-reads 2.4-5.6%; v4 2.67%) — M281 c3 history stays 2-3.7%.
- Triage's "isolated 1-dot marks PRINT" refined: isolated 1-dot DOTS are
  dead on the AltaLink too (2/49 sites = chance; 8-pitch grid depth 0.12,
  ~1% survive); 1-dot LINES resolve (contrast 0.25-0.28 both axes, vs home
  h-dead/v-marginal). c1 stays dead on both engines.
- **M281 margin fact TIGHTENS to ≤4 mm** (disc1 margin probes: all ticks to
  4 mm survive on all four edges, BOTH engines; CAL-1's ≤7.4 was never
  probed lower).
- analyze_disc1.py now EXISTS (900 lines, full-block scorer: strips+RQ,
  ladders, morphology, PN via v4, tone, canaries+screen-FFT w/ M281
  positive control, margins, r(x)/r(y), plus-lattice) — run on office A/B
  + home; reports in 007 build/.

**(3) Emission paths: engine 2 HAS the PS escape hatch the M281 lacks.**
P0 put_cmyk_bitmap, P3 (masks+setoverprint+OPM 1), S1/S2 (Separation masks),
S3 (DeviceN) are ALL overlap-preserving AND free of detectable re-screening
at 600-dot resolution (M281 165/212/224-lpi families at chance floor
7.5-11.9 dB where M281 controls read 20-28; textbook Adobe overprint
semantics — gs preflight predictions match exactly; the M281 was the
aberration). Bare masks (P1) and +setoverprint-only (P2) knock out on BOTH
engines. Only two weak grid-locked AltaLink textures: 200 lpi 0° at exactly
(1/3,0) cyc/dot (ON the c3/c6 lattices = harmless there, off-lattice at
c2/c4, 15-19 dB) + ~306 lpi y-banding (13-16 dB). Solids/contone carry a
finer engine screen set (188-211 lpi rotated on solids; 307/449-lpi line
textures on CAL mottle patches; 211 lpi 45° device contone screen) — but
the binary composite path is near-bit-faithful: composite c3 tax
-0.25/+0.20/+6.5 pp C/M/Y (home +5.2/+8.0/+16.8). Like-for-like 7-state
QDA (fold-optimistic both engines): c3 2.217 b/cell = 137.5 b/mm² vs home
1.479; {7+K}-c4 2.785 vs 2.074; c6 2.786 = alphabet-saturated. Consequence:
the 002.2-screened vs 003.0-mask dichotomy collapses on engine 2 — both
frameworks apply, the screen-tax term drops out; 003.0 dot-disjoint/void/
colored-pilot constructions port without the region-overlap trigger.
CMYK16 and multilevel stay REJECTED on engine 2 by measurement (16-state
1.826 < 8-state 2.208; 4-level K 0.853; grey3 c4 MI 1.258 = 43.9 b/mm²).

**(4) CAL-1 engine 2: healthy CMY quantified.** Y solid D 1.352 (home 0.77,
starved 0.37), Y rate 0.67 (home 0.55), Y drift 5× tighter (centre -0.59
dots, slope -0.35/100 mm vs -1.9); unmix cond(A_cmy) 1.83 (home 2.45);
8-state MI 2.208 vs home 1.76; K solid LIGHTER (D grey 1.09 vs 1.33 —
canary C fails, but solids↮cells per 005). Edge gain LOWER and flipped:
H>V (K 0.20/0.19, C 0.44/0.30, Y +0.41/+0.26 — Y now ADDITIVE, was
erosive) — **M281's V>H anisotropy is engine-specific; 006.1's tall-cell
advantage does NOT port** (loop-bw probe: wide 5.13% BEATS tall 6.83% on
the AltaLink). RET-like edge compensation is ON (canary F: thin strokes
thickened, slope -0.168). NEW transport term: ~30 mm gear-train ripple
family (2.5/5/7.5/10/15 mm harmonics, 0.15-0.21 dots) + 74 y-steps/page
(vs 3-7 same-scanner home) — print-frozen candidate, rotated-scan
attribution NOT yet run; banding 37.8 mm amp 0.0055 D SNR 4.2 = weak
candidate. M0 loader: params_from_calpage_report loads engine-2 PlaneParams
clean (geometry/morphology/screen models still M281 — engine-2 profile
beyond PlaneParams is future work). Same margin envelope (L6.0/T7.4/R7.4/
B6.4 mm); 300-dpi row everything-resolves; Nyquist 1-on/1-off closes solid
on BOTH engines; min-white 3 dots on BOTH (white erasure is the invariant;
office closures are MORE terminal — patterns-k ctx rescue at encode-c2 only
12.7→11.0% vs home 11.2→5.0, while e004-B1 ctx behaves home-like 10.8→5.5
— ctx-detector gains on engine 2 are field/position-dependent, do NOT
budget them from M281 numbers).

**(5) Loop pages: the loop protocol is engine-portable and the healthy
number is in.** LOOP-C: TRAIN-QDA on furniture bands 0/7/15 → 13 test
bands: acc 0.711, **MI 1.442 b/cell = 89.4 b/mm²** (bands 1.216-1.833;
weak bands are mid-page = strip-geometry variance, not Y-fade). Genie-
training parity REPLICATES (+0.11 pp acc / +0.005 MI — 2% furniture = full
labeled performance on a second engine). Y-attribution check passed (Y
solid D_b 1.32, flat down-page — unambiguously the office sheet). Blind-EM:
stale-prior init reproduces the 006.2 cluster-death failure (0.910, Y/CY
die); furniture init rescues only to 0.999 — **EM refinement itself walks
away from truth-derived centroids: loop receiver = furniture-QDA, skip EM
entirely** (006.2's fix necessary but not sufficient). Errors concentrate
on the Y-presence axis of the 7-state alphabet (W↔Y, C↔CY, M↔MY) even with
dense Y — per-cell Y modulation over another plane is the weak discriminator
on the composite path; engine-2 unmix (cond 1.83) not yet wired in. LOOP-BW:
strips-alone ctx 7.32% (genie 3.95% — office strips-alone BEATS home genie
7.77%); recal MI 0.680 = 94.8 b/mm² (best legal B1 on record, single scan);
the home 001.4 PAVA recal map transfers cross-engine at -0.022 MI. Strip-vs-
genie gap +3.37 pp (home +5.82), same mid-gap signature (BER doubles
108-168 dots from a strip) — **the between-strip refinement stage is worth
~3 pp on BOTH engines, still the top zero-print build**. RLL i2w3 16.6% ≈
home (dot-level dropout mechanism is NOT engine-specific — 004.0a's
constraint-consistent-dropout finding replicates); fill75 WORSE on office
(19.25%, anti-productive); grey3 better but still dead areally (43.9).
B1 miss/fa structure: miss HALVED (3.5 vs 7.0%), fa-dominant 2.15:1 —
white closure is the binding constraint on engine 2; page-edge row penalty
ABSENT (home rows 0/7 worst = M281 print-side, not scanner). B2: 13.65% /
0.1489 b/dot — **cross-engine stationary to 3 significant figures**;
82-86 b/mm² across 3 sheets, 2 engines = the rate-ladder anchor.
Multi-sheet minima: NO class minimum moves (all home-measured); engine 2
widens A3/A4/B1 upward, tightens B2.

**(6) MIC: the AltaLink lays yellow tracking dots — COLOR-PATH-GATED.**
K-only blank (001 p6): CLEAN at proven sensitivity (52 specks/57,298 mm² =
0.0009/mm², all periodicity stats at null; injection control 30/30 at
70 counts, 25/30 at 20) — Y-cleaner than M281 blanks. But CAL-1's quiet
zone: 226 yellow dots, 0.327/mm², x-period EXACTLY 2.032 mm = 48 dots,
autocorr z=44.7 (y-period > the 14 mm window, unresolved). Same-session
margin replication: disc1-p1 margins 0.34/mm² with the 48-dot x-period
signal (weak but above null p99); e004/loop-c margins scatter-dominated
(1.6-2.7/mm² Y-scatter, lattice diluted, inconclusive); grey scans
untestable. Working model: pages that engage the color path get the MIC
lattice (~0.6% of c3 cells host a dot), K-only pages do not. Channel
impact: absorbable (site-gated Y detection + outer code; pilot dust is
1.51/mm² = 4.6× denser), but it is a real new Y noise term AND a forensic
serial/timestamp marker on every color sheet from this engine (DESIGN R3:
archive sheets printed on the AltaLink are NOT anonymous). Unresolved lead
(flagged, not a fact): two weakly-coherent K-speck displacement vectors on
the blank (|v1|=37.9 mm scan-x, p=0.002 post-hoc) — roller-period spotting
candidate; zero-cost cross-sheet replication pending.

**(7) Instruments (durable):** analyze_disc1.py (new); median-rule floor
bug found+fixed (Otsu/gtmid alternatives); screen-FFT hunt re-banded
110-320 lpi off-axis with M281 positive control; cal_core corners-only
refit path for 4-landmark pages; e004/overlap2/composite analyzers ran
UNMODIFIED on engine 2 (report-naming collision handled: home reports
backed up + restored byte-identical, office reports saved as *_xerox.json);
stock-report cross-engine contaminations documented (M281-anchored
knockout gates, stale template prose, M281 crosstalk unmix = measured
harmful on engine 2 — all raw numbers recomputed same-engine).

**Caveats (batch-wide):** single sheet+scan per stimulus, one day, unknown
office media; genie-warp on everything except the loop pages (strips-alone
legal) — same footing as the home baselines they're compared to; A-track
MI is QDA fold-optimistic like-for-like; multi-scan combining (the cheapest
known lever) unapplied on office sheets — 3-4 re-placed passes of loop-c/
loop-bw/e004 are pending free upgrades; engine-2 day variance unmeasured
(B1 day-fragility is engine-1-evidence-only; office fa-dominant structure
says density drift would hit the same white-closure mode).

## 007.7 — zero-print measurement batch (2026-07-07, 4 threads, all data on disk)

Follow-ups to the 007.6 queue. Single-sheet/single-scan footing throughout
(same as the baselines compared against); scratch scripts + JSONs in the
session `zp/` dirs.

**(1) Between-strip refinement — BUILT, engine-CONDITIONAL, net +2 pp on
home only.** New durable module experiments/006-loop-pages/between_strip.py
(overlay, NOT yet wired into analyze_e006bw — deliberately, see below): it
replaces strip_tracker's linear inter-strip interpolation with a
self-clocked Y-BOW (the payload's own c2 lattice DFT'd at cell frequency in
inverse-affine dot coords per y-sub-band = dd_warp §5.1 phase, integer branch
+ reference pinned by the TWO bracketing sync strips, quality-weighted
quadratic forced to zero at both anchors, shrunk 0.75). GT never enters
(legal). Mechanism confirmed first with a GT-xcorr instrument: true dy(y)
BOWS up to -2.3 dots at mid-gap (>½ a c2 cell — hence the doubled BER;
linear interp is exactly zero at strip endpoints, worst mid-gap).
- HOME M281 (3 grey scans, e006bw): single-scan +1.6 pp mean B1 ctx (s2
  +1.05 / s3 +2.40 / s4 +1.33); the 120-168-dot-from-strip bin (worst under
  linear interp) improves most every scan — the gradient flattens as
  designed. **Multi-scan combining is the deployable story**: per-scan
  self-clock branch misses land on DIFFERENT bands, so combining averages
  them out and the gain GROWS — 3-scan B1 ctx 12.65→10.60%, MI 0.521→0.572
  = 72.6→**79.7 b/mm² (beats the 006.1 4-scan strips-alone 73.5)**. Closes
  ~28% single / ~35% 3-scan of the +5.82 pp gap; residual vs genie ~2.83 pp.
- **OFFICE AltaLink: HARMFUL (-4.5 pp, 7.32→11.86%)** — that print's <5-dot
  feature erosion (007.6) weakens the c2 lattice, so the self-clock picks
  wrong bows where strips are already near-genie. Global self-clock quality
  (0.025 office vs 0.031 home) does NOT separate the engines, so it can't be
  gated blindly — hence overlay-only, NOT wired into the pipeline. NEXT: a
  legal go/no-go gate before this graduates to a pipeline stage + preflight.
- Two discriminating tests shaped the design (verify-before-concluding):
  endpoint strip-disagreement does NOT predict mid-gap residual (corr -0.50,
  wrong sign — rejected that gate heuristic); an x-bow from the same lattice
  was catastrophic (the narrow x-sub-band of a 50%-random field has no
  lattice signal; the CCD comb is already carried by strip dx) — dropped,
  y-only. Falls SHORT of the ~3 pp aspiration: the c2 self-clock is
  genuinely noisy (random-payload lattice, weak DFT).

**(2) Cross-tile confirmation: 137.5 is REAL but does NOT displace 133.3 —
the gap is between-sheet variance.** Reproduced the 007.6 emission number
exactly (overlap2 sheet, 7st-c3 composite: fold-opt 2.2171 b/cell = 137.5,
acc .9028). Applied held-out spatial-fold discipline to the SAME field
(4×4 and 5×5 sub-blocks): 2.2141 = 137.3 — fold-optimism costs +0.003 b/cell,
so 137.5 survives discipline. On the e004 A3 sheet, all three disciplines
agree to 0.006 b/cell (cross-page 133.3 / within-patch 133.7 / same-fold
133.9). **The AltaLink composite path is near-perfectly stationary across
page position** — so the 137.3-vs-133.3 gap (4.0 b/mm²) is genuine
sheet-to-sheet variance between two physical prints, NOT a method artifact
(corroborated: the same two constructions differ by 0.42 b/cell at home —
overlap2 91.7 vs e004 117.6). Reconciled AltaLink composite-c3 =
**135 ± 2 b/mm²** (two same-day held-out sheets); the defensible RECORD
stays the conservative, stricter cross-page **133.3** (e004 A3, trains
across 8×8 page positions, larger dataset). c4 mirrors it: overlap2 7st-c4
cross-tile 92.1, {7+K}-c4 97.7 (vs e004 A4 93.6 — same ~4 b/mm² between-sheet
gap, cross-tile free). Multi-sheet minima unchanged.

**(3) Engine-2 unmix does NOT beat 1.442 — the 7-state composite is at the
QDA ceiling; Y-axis confusions are CHANNEL-limited.** Theory guard satisfied
empirically: naive linear-unmix-as-QDA-features is a provable no-op (3-feat
map bit-exact, 4-feat 1.65e-6 rel — the logdet shift is class-constant and
cancels in the uniform-prior argmax; C0 raw-QDA reproduces 1.4425 = the
007.6 1.442). Built the honest candidate — hierarchical Y-residual detector
(decide C/M on unmixed t_C/t_M, subtract predicted crosstalk into D_b,
re-decide Y on the residual): all variants LOSE (C2 1.3215, C2c 1.3168, C2b
1.2975 b/cell = ~82 b/mm²). Mechanism (from confusions): residual cancel
works where targeted (false-Y W→Y 12.9→4.3%) but pays 2× in missed-Y (Y→W
15.7→30.7% — a 1-D threshold is a weaker detector than full QDA) AND the
hard C/M cascade discards joint covariance, adding new C/M-axis errors
(CM→C 8.5→22.2%). Full 7-way QDA already exploits exactly that covariance;
since QDA is Bayes-optimal for Gaussian classes and STILL confuses the Y
pairs at 13-27%, the overlap lives in the feature space. **Reducing the
W↔Y, C↔CY, M↔MY confusions needs MORE FEATURES / a dedicated Y-modulation
carrier, not a linear recombination of the three densities.** Incidental:
grey channel is redundant-to-harmful for CMY here (rgb-only 1.4561 >
rgb+grey 1.4425).

**(4) MIC: y-period RESOLVED, cross-sheet CONFIRMED, K-vector lead
DISMISSED — and 007.6's own x-period corrected.** The unit cell is a
**~24×24-dot square grid (1.017×1.020 mm), axis-aligned 0°** — 007.6's
"48-dot / 2.032 mm x-period" was the 2ND HARMONIC of a 24-dot fundamental
(FFT: 24-dot z=98 dominates 48-dot z=23). The SAME 24-dot square cell, same
0° orientation, recurs on EVERY AltaLink color-path sheet (disc1a/b p1, CAL,
loop-c now clean at z=66, comp, overlap; density 0.24-0.53/mm²) with huge z
= fixed device pattern, not chance. Negative controls hold: K-only mic-blank
0.0017/mm² no lattice (~140× below), and — **NEW mechanism** — disc1 p2 (the
setpagedevice 1200-probe render) carries NO lattice at null density despite
36,700 mm² of blank, on BOTH pairs, while p1 (default-render, same job/sheet)
carries the dense one: **the MIC dots are laid in the AltaLink's DEFAULT
600-dpi render path; the setpagedevice/1200-probe path omits them** (both
print neutral K, so render-mode-gated not ink-gated). Super-tile
(payload repeat) ~31×16 cells = 31.5×16.3 mm (disc1a z=160, disc1b z=199,
replicated); ~100/496 slots filled → capacity CEILING ~360 bits fixed-weight
/ 496 raw per tile — ample for serial+timestamp, NOT decoded. The K-speck
37.9 mm displacement lead is DISMISSED: pre-registered |v|=37.9±3 mm, z≥6
test fails on the actual blank (best in-annulus count 8, z=4.7, along scan-y
not the lead's scan-x; 6/22244 bins tie it) — 007.6's p=0.002 was post-hoc
multiple-comparisons over tens of thousands of candidate vectors, chance
debris clustering, no roller period. DESIGN R3 restated: 0.24/mm² Y-plane
contamination = 6.3× SPARSER than pilot dust (1.51/mm²), blue-channel-only,
site-gated-absorbable — BUT AltaLink DEFAULT color prints carry a
machine-identifying tracking lattice (not anonymous); two visible
mitigations — the setpagedevice render path suppresses it, and K-only pages
get none.

**Queue impact:** (a) between-strip refinement BUILT (home +2 pp multi-scan,
office needs a legal quality gate before wiring — the gate is the new (a));
(b) 137.5 confirmed real, record stays 133.3, composite path proven
position-stationary; unmix ceiling reached → the Y-axis capacity lever is a
dedicated Y carrier (design item), not detection; MIC fully characterized
(24-dot cell, 31×16 super-tile, ~360-bit ceiling, default-render-gated) —
the mitigation lever (setpagedevice path suppresses MIC) is new; K-vector
lead closed. NEW: legal self-clock go/no-go gate for between_strip.py + its
preflight test; a dedicated Y-modulation carrier probe (the composite Y-axis
confusions are channel-limited); confirm the MIC render-mode gating by
reading the PostScript render paths (currently inferred from 007.1 labels).

## 007.8 — model-review corrections to 007.7 (2026-07-07, same day)

A skeptical re-review of the 007.7 thread outputs against the established
record found one factual error that had propagated into the headline
mechanism, two overstated attributions, and one buried free upgrade. All
verified against data on disk before recording. 007.7's text above stands
as written (historical); THESE CORRECTIONS GOVERN.

**(C1) MIC "render-mode gating" RETRACTED — the evidence supports per-page
COLOR-CONTENT gating.** The 007.7 mechanism ("laid in the default render
path; the setpagedevice path omits it → anonymity lever") rested on the
claim that disc1 p1 and p2 both print neutral-K content. FALSE: the disc1
manifest lists canary/solid_C, solid_M, solid_Y, cmy_c3_*, cm_overlap_* on
PAGE 1 — p1 has real C/M/Y content; p2 is all-K. With that confound seen,
every observation fits the simpler rule: **pages whose content engages the
color planes get the MIC lattice; K-only pages do not** (mic-blank clean,
disc1-p2 clean, disc1-p1 latticed, all full-color sheets latticed).
Render-mode gating is NOT established (would need a setpagedevice+color
page, not on disk — one-page office print if ever worth it). The anonymity
lever is the boring one: K-ONLY pages carry no lattice. Everything else in
the MIC thread survives review (24×24-dot cell, 48-dot = 2nd harmonic
correction, 31×16 super-tile ~360-bit ceiling, K-vector dismissal).

**(C2) Unmix conclusion SOFTENED + free upgrade surfaced.** "Y-axis
confusions are channel-limited, only a physical Y carrier can fix them" is
too strong. What is proven: linear recombination cannot help (QDA
invariance, verified empirically) and the QDA-FAMILY ceiling is reached.
But the thread's own incidental finding disproves the Gaussian premise:
**rgb-only QDA 1.4561 beats rgb+grey 1.4425** (+0.014 b/cell) — adding a
feature cannot hurt a correctly-specified Bayes detector, so QDA here is
misspecified (M channel clips at the scanner g-floor, 007.6). Corrected
reading: non-Gaussian detectors (per-class mixtures, quantile features)
are UNTESTED and are the cheap next probe BEFORE the dedicated-Y-carrier
design item. Free upgrade adopted: the best measured loop-legal LOOP-C
figure is **rgb-only 1.456 b/cell = 90.3 b/mm²** (same footing; 1.442 was
the rgb+grey protocol default).

**(C3) Cross-tile attribution corrected: "between-sheet variance" →
"within single-position sampling variance".** The Xerox A3 per-tile
same-fold spread is 2.058–2.262; the overlap2 field (ONE ~20 mm position)
reads 2.214 — comfortably inside. The thread's 0.006 discipline-delta
measured training scope, not the position luck of a single evaluation
field, so the 137.3-vs-133.3 gap needs no sheet-variance hypothesis at
all. Decision unchanged: **record stays 133.3** (16-position cross-page);
137.3 is a single-position draw from the same distribution.

**(C4) strip-refine caveats sharpened.** The frozen constants (shrink
0.75, deg 2, band 24) were calibrated once against genie ON THE SAME SHEET
the home gains are reported from (mitigated by the broad optimum, but
there is no second home e006bw sheet to confirm on). And the gate search
tried endpoint-disagreement and GLOBAL self-clock quality only — PER-BAND
gating (apply the bow only where that band's self-clock SNR clears a
threshold) is the untried natural candidate for the go/no-go item and
might rescue the office case rather than refusing it.

Process note (recorded as doctrine): any thread result that changes a
MECHANISM (not just a number) gets cross-checked against the established
record/manifests before entering CLAUDE.md — 007.6 did this (blank-vs-CAL
MIC, on/off-axis screens); the 007.7 synthesis did not, and C1 is the cost.

## 007.9 — engine comparison verdict + data sufficiency (2026-07-07)

**Verdict: the AltaLink is BETTER for color/density, EQUAL-CLASS for K
robustness, and operationally WORSE — with one honest asterisk (engine-2
day variance is a one-day sample).**

Per scheme (best labeled numbers, same footing per row):

| scheme | HP M281 (home) | Xerox AltaLink (office) | verdict |
|---|---|---|---|
| K cell ladder (raw) | c1 dead / c2 ~11-14% / c3 2.0-3.7% / c4 ~0.3-2% | c1 dead / c2 ~11-13% / c3 2.5-3.5% / c4 ~0.3-1.9% | EQUAL (ladder shape identical; no density unlock) |
| B1 c2-K genie-class | day-1 109, day-2 92.8 b/mm² (day-FRAGILE, page-edge structured) | 106.1 (one day; miss HALVED, fa-dominant; edge penalty absent) | EQUAL-class; Xerox cleaner structure, fragility UNKNOWN |
| B1 legal (strips) | 73.5 (4-scan) / 79.7 (3-scan + refinement) | 94.8 single scan | XEROX (cleaner print geometry helps legal sync most) |
| B2 RLL | 82.2-93.3 | 83.1 | EQUAL to 3 sig figs — engine-invariant anchor |
| A3 7st-c3 | 91.7-117.6 (screened composite, Y-fragile) | 133.3 cross-page RECORD (unscreened composite, healthy Y) | XEROX +13-45% |
| A4 {7+K}-c4 | 85.7 | 93.6-97.7 | XEROX (+9-14%; new K↔CM confusion) |
| full-page loop legal | 47.7 (starved-Y; healthy home UNKNOWN) | 90.3 (rgb-only) | XEROX (home not comparable until Y swap) |
| per-plane c3 isolated | K 3.7 / C 3.6 / M 3.8 / Y 7.2% | K 3.5 / C 4.5 / M 4.6 / Y 5.5% | mixed: home C/M slightly better, Xerox Y and balance better |
| geometry | x-scale +0.25%, V>H aniso, Y drift -4.9 dots | x TRUE scale, weak H>V, drift 5x tighter, print-to-print <0.01% | XEROX |
| emission paths | overlap ⇒ screened, no PS escape | 5 overlap-preserving unscreened paths | XEROX (structural) |
| operational | ours, deterministic access, MIC-free, PJL known | office access only, MIC on color sheets, fixed-600 PS, RET-on, media/consumables uncontrolled | HP |

Character difference in one line: the M281 is a *sloppier marker we fully
control and understand across days*; the AltaLink is a *cleaner, healthier
engine we don't control*, whose color path is structurally superior
(unscreened overlap + healthy Y) and whose K path matches ours.

**Data sufficiency — do we need more Xerox PRINTS?** For mode
characterization: NO for everything except day variance. The decisive gaps
and their costs:
1. **Day/consumable variance on engine 2 (NEEDS PRINTS — the only real
   print need):** rate ladders are set on multi-sheet MINIMA and we have
   ONE Xerox day. One verbatim reprint batch on a DIFFERENT day (e004.ps +
   e006c.ps + e006bw.ps, 3 sheets, sha-gated) bounds it. B1's white-closure
   fragility mechanism exists on the AltaLink too (fa-dominant) — a bad-day
   sample is the test.
2. Multi-scan upside on office sheets: SCAN-side only (3-4 re-placed
   passes of sheets already at home) — no print needed.
3. Healthy-home LOOP-C for a fair loop comparison: HOME print need (post
   Y-swap e006c reprint), not a Xerox one.
4. A3 self-clock legality on the unscreened AltaLink composite: existing
   scans suffice (zero-print analysis, queued).
5. Grey-mode CAL-1 scan (K channel-matched): scan-side only.
So: **one 3-sheet different-day Xerox batch closes characterization**; all
else is scan-side or home-side. Modes selected today would be provisional
on (1).

**Queue impact (prior 007.6 items still standing):** (b) office DISC-1 scoring DONE (incl. analyze_disc1.py;
morphology/wedge/canaries/margins now scored on home pair too); c3@1200
CLOSED negative; (d) Duplex-false print demotivated (user call to drop);
(c) LOOP-C healthy number DELIVERED by engine 2 — home Y-swap reprint now
only matters for M281-channel comparability; NEW items: MIC cross-sheet
replication + y-period (needs a >14 mm quiet window or margin-lattice fit);
engine-2 crosstalk unmix wiring (invalidate M281-matrix use); cross-tile
confirmation of the 137.5 emission ceiling; multi-scan office passes;
AltaLink PJL/PCL recon if 1200 is ever wanted (PS path closed); engine-2
simulator profile beyond PlaneParams (screen family, 30 mm ripple);
docs/LAYERS.md registry rows for the cross-engine measurements.
