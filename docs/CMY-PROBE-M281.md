# CMY-PROBE-M281 — the M281 emission probe sheet: design and workplan (v0.2, 2026-10-11)

**Status: DESIGN + WORKPLAN, nothing built, nothing printed.** One scratch
sheet on the HP M281 (fiducials allowed: DESIGN.md R3 binds archive
sheets), ONE PostScript job, printed before P1's cmy volume sheets. It
answers three questions:

1. **Mechanism.** Which lean constructs lay SOLID single toner,
   unscreened, as e041's 8-bit Indexed image did (S12–S17): three
   colour imagemasks (`setrgbcolor` then `imagemask`), a 2-bit Indexed
   image, an 8-bit Indexed image without the HP operators — all in plain
   PostScript, no PJL wrapper. The owner's standing question "would you
   prefer Indexed to a mask?" is answered by the sheet: 2-bit Indexed if it
   prints solid and lean (2 bits per dot, one object per page, the four
   values an explicit lookup, the image path the solid points were measured
   on), masks if only they do (3 bits per dot, K's idiom), 8-bit Indexed
   as the measured fallback (8 bits per dot).
2. **Colour points.** The edges of each toner's solid plateau along each
   device axis at two-level resolution, hence the MIDPOINT of the
   non-screening range — the "correct" RGB value for the registry — and the
   foreign-toner cross-talk inside it. Today's values are known-solid
   plateau ENDS: C's G 208 (224 half-way; below 192 never swept), M's R 240
   (224 not solid), M's B 192 (the finer B sweep is e041's own owed item);
   Y (255,255,0) deep inside (design v0.3 §2.8).
3. **Compactness and health.** Which encoding and depth the engine prints
   identically — ASCIIHex (every K page) or ASCII85 (every e041 palette
   job), 2 or 8 bits — and that the lean job (PSDoc's DSC head, guarded
   `setpagedevice`, `%%EOF`, nothing else) is the whole job.

**Decisions taken 2026-10-11 (owner):** one `.ps`, no PJL — iterate with
another sheet only if necessary; c2 bands only, no repeat bands ("it either
works or not"); the colour point is the midpoint of the non-screening
range, the MIC noise inside the floor; ladders stepped to find the
midpoint and the correct values; the scan protocol is the owner's;
experiment 043; no cmy format fragment — "this is a probe sheet. pieces of
it may flow into the discovery/characterisation sheet later"; 2-bit
Indexed IN ("it sounds smart").

Rulings served: R23 (the `rgb` route's construct — this sheet picks its
form), R9 as reduced (the probe is the owner's measurement; "I'd expect a
deeper spectral analysis for the exact solid midpoints"), R21 (`--printer`
carries the values the probe fixes). The owner prints and scans (hardware
rule); the record is `experiments/043-m281-cmy-probe.md`.

---

## 1. The record: measured and not

**Measured, this engine (e041, fresh toner).** Solid single toners
through 8-bit `[/Indexed /DeviceRGB 3]` images at C (0,208,255),
M (240,0,192), Y (255,255,0), PJL-wrapped, the four guarded HP image
calls (S12, S14–S17): cmyw c3 0.06–0.33 % lossless, c2 2.8–6.5 %
tracking |Y−C| registration (§041.5i, §041.5o). The plateaus at 16-level
steps (S10p2 on PCL XL; S12/S14 on PostScript): cyan solid at G 192 and
208, half-way at 224, screened at the corner 255, nothing below 192
swept; magenta solid along R ∈ {240, 255} × B ∈ [128, 192] (PCL XL), on
PostScript only (240,0,192) printed; yellow solid over the whole R = 255
row (§041.5, §041.5i). The screener: a per-column-region switch spending
a budget of COMPOSITE pixels (toner overlaps or K); every pixel a single
toner is never screened at any density; nothing job-level moves the
screen (M281-COLOUR §2; §041.5i, §041.5k). A K imagemask from
`src/holo/gen/ps.py`'s `put_bitmap` inside a palette job printed as
intended (S16 T9's overlay and bar A, `ps_trigger.py:46`); whole-field K
masks print on every K page (e029, e038). Sheet F's K-plane PostScript
printed identically bare and PJL-wrapped (F vs S1, §041.5). Engine
lattices: 165 lpi ±14.2°, 188 lpi ±71°/±19°, 212 lpi ±45°
(`measure/e041_scale_readout.py:128-131`); the M281's MIC grid is present
STATISTICALLY only (0.762 mm, invisible by eye, CLAUDE.md MIC bullet) —
at 33 lpi it is far from the screen lattices and inside the floor the
sheet's own white and scrambled bars set.

**Not measured.** A colour imagemask on this engine (every solid point
was measured through the image path; HP's interpreter may convert a
graphics-path colour differently from an image sample); a 2-bit Indexed
image; an UNWRAPPED palette job; an Indexed image without the HP calls;
ASCII85 as an imagemask data filter; the plateau edges at two levels and
C's lower edge; M's plateau on PostScript away from (240,0,192).

---

## 2. The arms

**Cell bands (the mechanism at cell scale), c2 only.** One seeded random
four-state cell field (uniform W/C/M/Y), the same field in every band so
the arms compare like with like:

| arm | construct | what it decides |
|---|---|---|
| M-hex | three imagemasks at the registry values, ASCIIHex | the mask route as the generator would emit it today |
| M-a85 | the same masks, ASCII85 (`currentfile /ASCII85Decode filter imagemask`) | the leaner mask encoding |
| I-2 | 2-bit Indexed image (`/BitsPerComponent 2`, `/Decode [0 3]`, hival 3), ASCII85, no HP calls | the smallest candidate |
| I-8 | 8-bit Indexed image, ASCII85, no HP calls | the fallback's leanest form |
| I-ref | S16's 8-bit Indexed image byte-faithfully — lookup, the four guarded HP calls, ASCII85 (e041's `image_lines`/`a85_lines`, `ps_trigger.py`, `ps_mixture.py:156-186`) | the measured control on the same sheet |

Band geometry is e041's so its readout applies unchanged: x 283, width
4392 dots, height 432, gap 24 (`ps_trigger.py:97-99`; 12 mm margins; a
band spans both column regions). Five bands.

**Bars (the colour points).** Imagemask bars 192 × 48 dots (8.1 × 2.0 mm;
e041's S10p2 shape was 93 × 24, one 96-px scan window), each painted at
one device-RGB value — the construct whose values production sends. For
each toner, one ladder along EACH device axis through the current
registry value, in steps of 2 over a span the 16-level maps say contains
both edges, steps of 4 where the map says the plateau is wide:

| toner | fixed | swept axis and span | bars |
|---|---|---|---|
| C | R 0, B 255 | G 160 → 236 step 2 | 39 |
| C | R 0, G 200 | B 192 → 255 step 4 (edge in B) | 17 |
| C | G 200, B 255 | R 0 → 32 step 4 | 9 |
| M | B 192, G 0 | R 220 → 255 step 2 | 18 |
| M | R 240, G 0 | B 150 → 230 step 2 (the owed fine sweep) | 41 |
| M | R 255, G 0 | B 150 → 230 step 4 | 21 |
| M | R 240, B 192 | G 0 → 32 step 4 | 9 |
| Y | R = G, B 0 | 200 → 255 step 4 | 14 |
| Y | R 255, G 255 | B 0 → 48 step 4 | 13 |
| Y | R 255, B 0 | G 192 → 255 step 4 | 16 |
| Y | G 255, B 0 | R 192 → 255 step 4 | 16 |

About 215 bars plus the three registry values as bars in every construct
of §2's table (15), in a grid at 10 mm pitch, 20 per row; value →
position by a seeded shuffle (no unseeded RNG), the manifest beside the
job. The ladders' spans and steps are the builder's to adjust against the
S10p2/S12/S14 maps, never coarser than 2 where an edge is expected.

**Controls.** Four white bars and two scrambled bars (random single-toner
dots at 1 dot/cell, no lattice) set the score's floor on THIS sheet (MIC
included); one screened control — a 50 % cyan tint as an 8-bit Indexed
image, the engine's own lattice as the score's positive reference (a
single toner at mid density spends no composite budget). Fiducials: S14's
five K fiducial images, drawn first (`pclxl_probe_sheets.py:24, 86-92`;
measured harmless beside solid cmyw bands on S14–S17).

**Sheet.** A4 at 600 dpi (4960 × 7016 dots), e041's section geometry.
Rows: fiducials; the five bands (~2,280 dots); the bar grid (~12 rows of
72 dots ≈ 900); the controls. Under e041's 6,732-dot last line with room
to spare.

---

## 3. The job

Plain PostScript through `PSDoc`: its DSC head, the guarded
`setpagedevice` (`<< /PageSize … /HWResolution [600 600] /Duplex false
>>`), `%%Page: 1 1`, the content, `showpage`, `%%Trailer`, `%%EOF`
(`ps.py:224-251`). No PJL, no prologue, no HP operators outside I-ref.
Every mask is `put_bitmap(bits, x, y, rgb=…)` in its own `gsave …
grestore`; the Indexed arms are `put_indexed_image(indices, lookup, x, y,
bpc)` (I-ref's bytes are e041's own lines). Operators: `imagemask`,
`image`, `ASCIIHexDecode`, `ASCII85Decode`, `[/Indexed /DeviceRGB 3 <…>]
setcolorspace`, `BitsPerComponent` 2 and 8 — all Level 2 law; no
`RunLengthDecode` or `FlateDecode` (a PostScript error aborts the page;
those two have no measured customer: with 2-bit Indexed a full A4 c2 page
is ~8 MB raw, ~10 MB ASCII85; masks ~12 MB raw, ~15 MB a85; 8-bit ~32 MB,
~40 MB; every job e041 printed was 31.6–33.0 MB).

**Health gate before the print (the e041 method).** gs `ppmraw -r600`
renders the job twice (default ICC, `-dUseFastColor`); per band and bar
the threshold (R < 128, G < 128, B < 128) → (C, M, Y) equals the GT
planes dot for dot, nothing painted outside the planned rectangles; a
strict `-sDEVICE=nullpage` run; the job's sha256 and byte count recorded
in the log.

**Novelty against the record.** `setrgbcolor` before `imagemask`;
ASCII85 on an imagemask; a 2-bit Indexed image; an Indexed image without
the HP calls; no wrapper; about 240 small imagemasks on one page
(PostScript text is thousands of glyph masks; S15 carried 58 images; the
1,168-object crash was PCL XL). Everything else is e041's or K's bytes.

---

## 4. Readout and decision

**Scan.** The owner's protocol (e041's default: Canon 2400 RGB; 2400 and
4800 agreed within 0.5 pp on cell readouts, §041.5p). The readout takes
the scans it is given.

**Instruments** (`measure/`): `measure/cmy_probe/readout.py` over e041's —
fiducial rectification, per-band hard cell error at per-plane poses with
confusion matrices and the in-band lattice score
(`measure/e041_scale_readout.py`); the bar score (the known-lattice peak
over the ring median in 96-px windows at the three lattices, ≤ 18
unscreened, the floor from this sheet's white and scrambled bars, the
positive reference the screened tint; `:120-131, 440-494`); per-bar mean
RGB (the cross-talk: the Y a magenta carries, the G drop in a cyan); and
the owner's spectral-midpoint analysis — each bar's full 2-D spectrum,
the lattice set plus off-band structure (`measure/e041_spectrum.py`'s
method), the edge placed where lattice power leaves the floor, the
midpoint between the two edges along each axis. A seeded synth
(`measure/e041_probe_synth.py`'s pattern) with planted edges, lattice and
cross-talk; the readout recovers each edge within one step and the
midpoints before any scan is read.

**Outputs.** Per bar: value, construct, mean RGB, score per lattice,
verdict. Per toner and axis: both edges, the midpoint, the cross-talk
along the plateau. Per band: hard cell error per plane, confusion,
lattice score, the per-plane pose offsets (|Y−C| on this print). Job
size per arm as printed and per full-page extrapolation. A proposed
`rgb_solid` triple (the midpoints) for the `hp-m281` registry entry with
its evidence line; the owner edits the registry (the generator's `rgb`
goldens then move with cause).

**OUTCOME 2026-10-11 (experiments/043-m281-cmy-probe.md §043.3–043.3c):**
printed, scanned and read the same day. The primaries print unscreened
in every construct along the whole width; the decisive instrument turned
out to be the whole-patch WHITENED spectrum per ink density against the
engine's screen families (`measure/cmy_probe/stipples.py`), not the 1 mm
lattice score: the M281 adds a screened 212 lpi YELLOW component to cyan
for G above 190 and to magenta at every value (least at R 238–240,
B 192–196, where its own 165 lpi screen begins), and dark 160/196 lpi dots
to any yellow off the device corner; that stipple rides inside the cell
fields at the registry values. Masks and images differ only in the
magenta's own-screen onset (lower on the image path). Final proposal of
the sheet: C (0,184,255), M (240,0,192) unchanged, Y (255,255,0)
unchanged. The construct choice (masks now, or 2-bit Indexed after a
sheet with Indexed bars at the corrected values) is the owner's.

**Decision** (the generator plan's §1 emission paragraph is written to
the outcome; both candidate methods are ~25 lines):

| outcome | the `rgb` route becomes |
|---|---|
| I-2 solid at the bars AND its band's cell error within the I-ref band's | one 2-bit Indexed image per page, ASCII85, lookup = the registry values, no HP calls — the smallest job |
| I-2 fails, masks solid at bars and bands | three imagemasks per page; ASCII85 if M-a85 ≡ M-hex, else hex |
| only the Indexed images solid | 8-bit Indexed: I-8's form if it matched I-ref, else S16's construct with the HP calls |
| masks solid only over part of a plateau | the registry takes the MASK plateau's midpoint if masks are the route, the image plateau's otherwise |
| the unwrapped job misbehaves (I-ref screened) | a second sheet, the identical job inside e041's wrapper — iterate, one `.ps` at a time |

---

## 5. Workplan

- **W0 — the production methods (0.5 d, Opus builder).** Two additive
  `PSDoc` methods, both default-off, every existing golden byte-identical
  (`test_ps.py`, every K and colour emission golden): `put_bitmap(bits,
  x_dots, y_dots, rgb=None)` (`ps.py:153-181`; `rgb` emits
  `f"{r/255:.6f} {g/255:.6f} {b/255:.6f} setrgbcolor"` in place of the
  `setcmykcolor` line) and `put_indexed_image(indices, lookup, x_dots,
  y_dots, *, bpc=2, filt="ASCII85")` (`[/Indexed /DeviceRGB hival <lookup>]
  setcolorspace`, an 8-bit or 2-bit ImageType 1 dict with `Decode [0
  2^bpc−1]`, the data packed MSB-first per row, byte-padded — the e041
  image block without its HP lines). New goldens for one coloured mask and
  one 2-bit image. Pulled forward from the generator plan's W2 so the
  probe sends production bytes. One commit on `cmy-generator`.
- **W1 — the emitter and the readout (1 d, Opus builder; Sonnet checker
  for the e041 constants and the manifest schema).**
  `experiments/043-m281-cmy-probe/probe_sheet.py`: seeded; bars and bands
  as FUNCTIONS over `PSDoc` (so the characterization sheet can take them
  later — the characterize package is import-firewalled from `holo.gen`,
  `tests/holo/test_characterize_boundaries.py:24-32`, so that hand-over is
  a ruling for its day, not this one's); I-ref's bytes from e041's own
  functions imported by path as e041's scripts do; writes `<tag>.ps`,
  `<tag>.manifest.json` (every bar and band: construct, value, rectangle,
  seed), `<tag>-gt.npz` (planes per band and bar, fixed zip timestamps);
  runs the gs gate; prints sha256 and size. `measure/cmy_probe/readout.py`
  and `synth.py`; the synth self-check's numbers in the commit message.
  One commit.
- **P — print and scan (the owner).** `scripts/print_plane.sh <tag>.ps` on
  the M281 (raw 9100, `PRINT_NC_WAIT=600`, `PRINT_BACKCHANNEL` as e041
  §041.14p), page count before and after, the sha confirmed; the scans;
  `experiments/043-m281-cmy-probe.md` opened with date, engine, media,
  toner epoch, job sha and size, scan files and shas.
- **W2 — the record (0.5 d, Opus reader).** The readout, its tables in the
  log, the §4 decision taken by the owner, the registry proposal, the
  generator plan's §1 emission paragraph written to the outcome.

Cost: ≈ 2 builder-days plus the owner's print-and-scan hour; one sheet,
another only if §4's last row fires.

---

## 6. Open items (the owner's) and concerns

**Open.** Only the ladders' exact spans and steps (§2; the builder adjusts
them against the e041 maps, never coarser than 2 at an expected edge).

**Concerns.**
1. The mechanism question is binary and only paper answers it: the
   graphics-path colour conversion for masks, and the 2-bit sample path,
   are each one bit of information. Every candidate and the measured
   control share one sheet, so the answer is clean either way.
2. A PostScript error aborts the whole page; hence Level 2 operators the
   engine has seen or that every Level 2 interpreter implements, and the
   gs render and `nullpage` runs before the print. The 2-bit image is the
   one construct with no measured sibling on this engine; it is lawful
   PostScript, and the page is a scratch sheet.
3. One print, one day: the c2 cell error carries this print's registration
   (|Y−C| ranged 0.5–2.3 dots across e041's prints); the solidity verdict
   and the midpoints do not.
4. About 240 small imagemasks on one page is a new object count for this
   engine's PostScript path (text is thousands of glyph masks per page;
   S15 carried 58 images; the crash was PCL XL at 1,168 objects).
5. The bands are 1.9 Mdots, not a whole-field 32 Mdot object; K pages
   print whole-field masks routinely, and the Indexed arms' size scales
   only the data.
6. After the readout the `hp-m281` registry values may change; the
   generator's `rgb` goldens move with that cause, recorded in their
   ledger.

## 7. Out of scope

P1 itself and any cmy format content; cmy8 or cmy7 arms; K in a colour
page (R14); PCL XL; other engines (the same emitter with a coarse 16-level
sweep is their day-one probe beside the HCAL-R1 pair — later, with the
import-firewall question of W1); the generator waves beyond W0's two
methods.

---

## 9. Sheet 2 (E043b) — the values, the construct, the cell boundaries (specified 2026-10-11 evening, owner's go: "Go for edits and sheet 2")

Sheet 1 answered the mechanism and found the engine's yellow component
(§043.3c); it left three things open, and sheet 2 is aimed at exactly
those. Smaller than sheet 1: the x question is answered, the far ladders
are known, the five identical bands taught nothing the first two did not.

**The registry edit that precedes it.** `devices/registry.py`'s `Printer`
gains `color_route: str = "cmyk1"` and `rgb_solid: tuple[tuple[int, int,
int], ...] | None = None` (C, M, Y order; W is unpainted paper) — the W2
fields, pulled forward; `hp-m281` becomes `"rgb"` with **(0, 184, 255),
(240, 0, 192), (255, 255, 0)** (sheet 1's final proposal, §043.3c) and a
colour text stating e041's and e043's outcome; `xerox-altalink-c8245`
stays `"cmyk1"`. The probe emitters read the values from the registry.

**Geometry and job.** As sheet 1: A4 at 600 dpi, e041's section geometry
(x 283, width 4392 dots, 12 mm margins), S14's five K-mask fiducials
first, plain PostScript through `PSDoc`, no PJL, measured operators only,
the gs gate before the print. Everything at the registry values.

**1. Values at two-level resolution, in both constructs** (bars 192 × 48
dots; every bar twice: `mask-a85` and `I-2`):
- cyan G 176 → 190 step 2 at (0, ·, 255): 8 values — the stipple-free
  band and its centre;
- magenta a two-dimensional grid R ∈ {236, 238, 240, 242} × B ∈ {188, 190,
  …, 198}: 24 values — the three stipples (yellow, cyan dots, the
  magenta's own screen) trade off against each other there;
- yellow (255, 255, 0) and B ∈ {8, 16, 24}: 4 values;
- the three registry triples once more as `I-8` and `I-ref` bars (6), and
  the controls: 4 white, 2 scrambled, 1 screened (50 % cyan tint).
About 85 bars, 20 per row at the 221-dot pitch, seeded positions.

**2. Pairwise cell checkerboards** — W/C, W/M, W/Y, C/M, C/Y, M/Y at c2
(2-dot cells) and at c3 (3-dot cells), twelve patches of 480 × 240 dots
(20.3 × 10.2 mm) in two rows of six, drawn as masks (one mask per toner
of the pair; W unpainted). A known periodic signal: its spectrum is exact
peaks, so dot gain per toner pair, bleed and plane offset at the cell
boundary read directly, and the whitened spectrum off the checkerboard's
own harmonics says whether the yellow stipple survives inside 85 and
127 µm cells of each toner.

**3. Cell bands at the registry values**, the sheet-1 field (seed 43) at
c2: `mask-a85`, `I-2`, `I-8`, `I-ref` (four bands, 432 dots); a new
seeded field (seed 45, 144 × 1464 cells) at c3: `mask-a85`, `I-2` (two
bands). c3 is the archival row and the stipple's 120 µm period sits at
its cell size.

**4. A dot-level set** per toner as masks, 96 × 96-dot patches: isolated
single dots on an 8-dot grid, 2 × 2 dots on an 8-dot grid, 1-on/1-off
vertical lines, 1-on/1-off horizontal lines, 2-on/2-off vertical lines —
fifteen patches in one row; a record of the mask path's smallest marks.

Height: fiducials + 6 bands (2,736) + checkerboards (528) + ~5 bar rows
(360) + the dot row (~120) + gaps ≈ 4,100 of 6,732 dots.

**Manifest.** Sheet 1's schema plus `"checkerboards": [{id, pair, cell_dots,
construct, x_dots, y_dots, w_dots, h_dots}]`, `"dots": [{id, toner,
pattern, x_dots, y_dots, w_dots, h_dots}]`, bands carrying `cell_dots`
and `gt_key` (`states_c2`, `states_c3`), and the registry values under
`lookup` as before. Tag `E043b-m281-cmy-probe2`.

**Readout (built with the sheet).** Bars: the whitened whole-patch
spectrum per ink density at the five screen families
(`measure/cmy_probe/stipples.py`) IS the verdict — clean iff every family
in every channel is at or below the sheet's own white-bar maximum plus
margin (sheet 1: 25); the magenta grid reported as a 4 × 6 table of
(yellow, cyan-dot, own-screen) ratios per construct, cyan as its G series,
yellow its four. Bands as sheet 1 (cell error at per-plane poses,
offsets) plus the whole-band families. Checkerboards: per patch the ink
fraction per toner plane against the nominal 50 % (dot gain per pair),
the 10–90 % transition width across the cell boundary in µm per toner
(density profiles folded on the known period), the offset between the
two toners' fundamentals in dots (registration per pair), and the
whitened families off the checkerboard's harmonics; a composite PNG per
pitch. Dots: contrast of on-dots against off per pattern and a zoom PNG;
a record. The synth gains a checkerboard case (period and planted offset
recovered).

**Decision it supports.** The construct: 2-bit Indexed if its bars and
bands match the masks' at the registry values, else masks (both are
~25 lines in the generator). The registry values: confirmed or moved by
two levels from the grid's joint minimum. The cell-boundary numbers go to
the receiver's colour model and the format's c2/c3 expectations, not to
the registry. One sheet; the same sheet on another day quantifies drift
of the edges if wanted (e041 saw (0,192,255) solid, sheet 1 on the onset).

**OUTCOME (2026-10-11 evening; the record is experiments/043-m281-cmy-probe.md
§043.5).** Printed (page 3411), scanned and read the same evening. Construct:
MASKS, RULED by the owner on the record ("image masks it is") — the 2-bit Indexed image path is screened by the magenta's own 165 lpi
screen at every one of the 24 grid values and doubles the cyan's yellow; the
mask path has a magenta plateau (row R 238, B 188–196) and the lower yellow.
Values: the engine's added yellow depends on the bar's PAGE POSITION —
in ZONES (x 12–45 and 96–140 mm active on this print, the second starting at
e041's ~108 mm region boundary; the owner's reading: the e041 screener acting
on the pipeline's yellow, region by region; a regression's linear x term
summarised it as ×0.23–0.44 per 100 mm) while the magenta's own screen does
not, so the two-level edges this section asked for are zone-confounded
wherever a value was printed once; the
proposal from both sheets, after the owner's eye and the speck axis it
forced into the instrument (sparse foreign dots the families do not see:
R 236/238 magenta carries 6–18 cyan specks/mm²), is C (0,176,255) or
(0,178,255), M (240,0,192) / (240,0,194) / (242,0,192) (the strongest
candidates, in the record's order), Y (255,255,0) agreed — NOT applied
to the registry, the owner's call, with a sheet 3 that replicates each
candidate value across the zones (and sweeps 1-level steps around the
16-multiples 176 / 192 / 240) as the confirmation.
Cell boundaries: dot gain +0.31–0.39 dots per edge at c2 and +0.19–0.39 at
c3 on single-toner boards (the two-toner boards' fractions carry the
unmix's edge bias and are not quoted); edge width 65–74 µm at c3 (the c2
number is the instrument's floor); M−C ≈ +1 dot in x; and the 212 lpi
yellow stipple sits where two TONERS meet (c3 boards 120–474) and barely
where a toner meets paper (33–93) — it rides inside every cell field at
the new values too (c2 bands 286–334, c3 372–390 in the Y density; 7–15 in
the C and M densities, the lattice control). The dot set: single dots lay
0.10 / 0.11 / 0.02 of a solid (C/M/Y), 2 × 2 blocks 0.39–0.49. Two
findings of the owner's eye are measured in the record: the left ~30 mm
of every band (2× cell error, darker, 2–3× the stipple, on both sheets)
and four lighter streaks at fixed x that only periodic 2-dot patterns show (on the paper by his eye; no rescan).
Item 2's c2 question (the stipple inside 85 µm cells) is answered by the c2
BANDS, not the c2 boards, whose own diagonal fundamental is 212 lpi at 45°.
The same instrument over e041's cmy strips (S14 at C (0,255,255): 942–2293
whole band; S17 at (0,208,255): 582–680) shows the stipple was always
there and has fallen with the cyan value; e041's "unscreened" meant no
165/188 lpi composite re-screen, which still holds (record §043.5).

## 10. Sheet 3 (E043c) — the candidates inside cell fields, across the zones (specified 2026-10-11 night; the owner: "measure out cyan and the others in more realistic c2 and c3 settings, and see what happens with screening. Sheet 3 is yours to print (one page)")

Sheets 1 and 2 placed each value in a solid bar at one seeded position; the
engine's added yellow turned out to depend on the page-fixed column zones
(x 12–45 and 96–140 mm active on sheet 2), and the stipple the format will
live with is the one INSIDE the cell field, not the bar's. Sheet 3 therefore
prints the candidate values as full-width random cmy cell fields — every
band crosses every zone — at both pitches, as masks (the ruled construct),
and asks per band: the 212 lpi yellow stipple whole-band and per 9.3 mm
slice, the specks in the foreign densities inside the cells, the cell error
per plane and per slice, the per-plane poses. One variable per band against
one base.

**Geometry and job.** As sheets 1–2: A4 at 600 dpi, x 283, width 4392 dots,
five K fiducials first, plain PostScript through `PSDoc`, no PJL, masks only
(`mask-a85`: three single-toner `imagemask`s per band, ASCII85). Tag
`E043c-m281-cmy-probe3`; seeds cells c2 47, cells c3 48, layout 49. Bands
336 dots tall (14.2 mm: 168 c2 cells, 112 c3 cells), 48-dot gaps, top to
bottom; the c2 field (168 × 2196) and the c3 field (112 × 1464) are each
one seeded field reused by every band of that pitch, so the bands of one
pitch differ only in their values (paired comparisons).

**The bands (15; base = C (0,176,255), M (240,0,192), Y (255,255,0)):**
| # | pitch | C | M | why |
|---|---|---|---|---|
| 1 | c2 | 176 | 240/192 | the base |
| 2 | c3 | 176 | 240/192 | the base |
| 3 | c2 | 178 | 240/192 | cyan candidate |
| 4 | c3 | 178 | 240/192 | |
| 5 | c2 | 184 | 240/192 | the registry today; sheet 2's bands |
| 6 | c3 | 184 | 240/192 | |
| 7 | c2 | 192 | 240/192 | past the in-zone edge: the stipple's slope |
| 8 | c3 | 192 | 240/192 | |
| 9 | c2 | 176 | 240/194 | magenta candidate |
| 10 | c3 | 176 | 240/194 | |
| 11 | c2 | 176 | 242/192 | the eye's row |
| 12 | c3 | 176 | 242/192 | |
| 13 | c2 | 176 | 238/192 | the speckled row: do cyan specks in M cells matter in a field |
| 14 | c2 | 176 | 240/192 | the base again, bottom of the page: drift along y |
| 15 | c3 | 176 | 240/192 | |
Y is (255,255,0) throughout. Each band's manifest entry carries its own
`lookup` {W, C, M, Y}; the manifest's top-level `lookup` is the base.

**The bars (as built: five rows of 48 dots below the bands, 72-dot row pitch, the first row 48 dots under the last band — three rows cannot hold them, the right zone takes two 192-dot bars per row at the 292 pitch; the columns are centred in each zone, left edges x 308 / 600 / 892, 2304 / 2596 / 2888, 3773 / 4065 dots):** the nine
values of the table — C 176 / 178 / 184 / 192 at (0,·,255), M (240,0,192) /
(240,0,194) / (242,0,192) / (238,0,192), Y (255,255,0) — each as a mask bar
at THREE page positions, one slot in each of the left zone (x 12–47 mm),
the middle zone (97–131) and the right (158–182), plus one white slot per
zone; the remaining slots empty. Bar `construct` =
`mask-a85@<x mm of the bar's left edge>` (so the readout's series and grid
tables keep the positions apart — a zone carries two or three labels; the
`zone` field carries the zone); the emitter's bar painter dispatches on the
`mask` prefix. Bar 192 × 48, seeded slot order within each zone; ids
`<toner>-<value>-<zone>`, whites `white-<zone>` with construct `none`.
BUILT 2026-10-11 night (`probe_sheet3.py`, test `tests/holo/
test_e043c_probe_sheet.py`): job `E043c-m281-cmy-probe3.ps` sha
`f2024456deda5f775a5859247c724ea8fbd25d9805f9fd475cea5d84efc57abc`,
10,324,054 B, 77 imagemasks and no other image operator, one
`setpagedevice` in the page setup, no PJL, no HP calls; last y 6379; the
gs gate passes (both colour paths 0 differing dots, nothing outside the
rectangles, nullpage clean, second build byte-identical).

**Manifest:** sheet 2's schema (`tag, dpi, page_dots_xy, seed_cells,
seed_cells_c3, seed_layout, lookup, fiducials, bands, bars, job`) without
`checkerboards`/`dots`; bands with `name, arm = "mask-a85", cell_dots,
rows, cols, gt_key ("states_c2" | "states_c3"), lookup, note`; bars with
`id, kind, toner, axis, rgb, construct, x_dots, y_dots, w_dots, h_dots,
gt_key, zone`. GT npz: `states_c2`, `states_c3`.

**Gate before the print:** `--check` as sheet 2 (gs 10 renders both colour
paths, 0 differing dots, nothing outside the planned rectangles, nullpage
clean, a second build byte-identical), the geometry checks (no overlap,
every rectangle inside the page less 4 mm), the job plain PostScript with no
PJL and no HP operators, and the tests of `tests/holo/test_e043c_probe_sheet.py`
(schema and counts, every band's lookup, the fields' seeds, the bar
positions in their zones, the gs gate under HOLO_RUN_GS_TESTS).

**Readout:** `measure/cmy_probe/readout.py` unchanged (bands by their
`cell_dots` and `gt_key`, bars by construct); the comparisons this sheet is
for: per band the whole-band `Y213@45` in Y with the C/M-density control,
the per-slice profile against the zones, the cell error per plane and per
slice with the 4 × 4 confusion (a foreign toner inside a cell shows there
as confusions and as that class's spread — the bars' speck axis does not
transfer to a field, where every density is some cell's own), |Y−C|; the
bars' verdicts and specks per zone beside them. Decision it supports: the registry's C and M values,
chosen for the lowest in-field stipple and specks across the zones at the
lowest cell error, with the c3 numbers (the archival pitch) weighed first.

**OUTCOME (2026-10-11 night; experiments/043-m281-cmy-probe.md §043.6).**
Printed, scanned and read the same night. Inside the cell fields the yellow
stipple is a cyan-value effect first: C (0,176,255) reads 54–77 at c2 and
109–129 at c3 against the registry's (0,184,255) 231 / 388 (sheet 2:
286–334 / 372–390), flat across the zones, with 178 half-way back up and
192 worst; at C 176 the magenta's choice is invisible at the stipple
((240,192), (240,194), (242,192) within one print's noise) and the speckled
row (238,192) costs +1.4 pp of c2 cell error. The c2 cell error stays
registration-limited (5.0–6.1 %, |Y−C| 1.35–1.82 dots); the c3 cell error
follows the cyan value (0.16–0.18 % at 176, 0.37 at 192). The bars agree
zone by zone. RULED and APPLIED ("Use our new numbers"): C (0,176,255), M (240,0,192) and
Y (255,255,0) in the registry's `hp-m281` row; the printed sheets 1 and 2
regenerate through `--lookup legacy-e043a` / `legacy-e043b`.
