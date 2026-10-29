# Experiment 031 — Xerox AltaLink C8245, first HCAL-R1 discovery pair

Status 2026-08-06: **both sheets measured, both on the production path.**
The colour sheet analysed clean. The B/W sheet initially **refused** at
`corner_registration_failed`; the refusal was root-caused to an **analyzer
defect on a good print**, recovered first through a read-only diagnostic
harness, and then fixed properly — W8a landed the same day and the sheet now
analyzes with all four corners, so **the harness report is superseded**
(§031.1). Nothing here is promotable: single copy, discovery stage,
scanner-adequacy verdict `inadequate`, and a print path that is not the
repo's mandated socket-9100.

This is the first time the current `discover`/HCAL-R1 instrument has been
pointed at the office AltaLink. The prior AltaLink record (experiments
003/004/007) came from different instruments.

## 1. Evidence footing

- Engine: **Xerox AltaLink C8245** (office). Live readback (§4) reports
  `Xerox AltaLink C8245 Color MFP`, LanguageLevel 3, version `3021.101`,
  revision 1, `DeviceCMYK`.
- Print date/session: **2026-08-05**, `2026-08-05-A`, Europe/<city>. The
  operator hand-wrote `Xerox 5.8.26` on the B/W sheet, visible in the capture.
- **Print path: `lpr -o raw`.** This is a CUPS queue, NOT the
  `scripts/print_plane.sh` raw JetDirect socket 9100 that CLAUDE.md mandates
  for data sheets. Recorded as footing `lpr-raw`. See §4 — the sheets
  themselves establish that genuine PostScript reached the interpreter, but
  the footing is not the registry's `raw9100` and must not be merged with it.
- Media: white office A4, operator reports 60–80 g/m² ("sheets feel a bit
  flimsy"), exact stock not recorded. Footing `white-office-a4-60-80gsm`.
- Scanner: Canon 4800 flatbed, the scanner of record. B/W sheet grey, colour
  sheet RGB, no auto-crop/sharpen/contrast. Footings `grey-no-auto` /
  `color-no-auto`.
- Stimulus: the standard `discover emit` default pair, `request_code=0`,
  `request_dpi=null`. **The B/W sheet's `layout_digest` is byte-identical to
  e028's** (`cbcab84fda635e5d8af3eaf0…`), so the K-channel cross-engine
  comparison against the M281 is exactly like-for-like.

### Captures

| Sheet | Bytes | SHA-256 |
|---|---:|---|
| `scratch/in/xerox-canon-cal-bw.tiff` | 2,291,818,718 | `65e8bf50d93d82ecd5ddaebf6aae5b5a8af0b2dd354b3071a6adf4e3dbc4ad42` |
| `scratch/in/xerox-canon-cal-color.tiff` | 6,875,455,728 | `e468bd26f991484e9ddfa114cb01febc1eea9619fa86ac929ef493698de564c0` |

Both are one 40,832 × 56,128 image at true 4800 × 4800 dpi, uncompressed,
one contiguous full-height strip, top-left orientation; B/W is 8-bit
BlackIsZero grey, colour is 8-bit RGB chunky.

### Capture protocol deviation

The sheet was placed **flush into the platen origin corner and slightly
overhangs it** (~1 mm on both origin edges), against the 028.2 protocol which
requires a ~5 mm inset so all four paper edges land in frame. Consequence:
`geometry.paper_edges` reports `top: not-visible`, and **the top printable
clip is unmeasured** (§5). Left/right come back `sparse`.

## 2. Analysis commands and outcomes

```sh
env/bin/python confetti.py discover analyze \
  scratch/in/xerox-canon-cal-bw.tiff scratch/e031/reports --scan-dpi 4800 \
  --printer xerox-altalink-c8245 --print-path lpr-raw \
  --media white-office-a4-60-80gsm --scanner canon-4800 \
  --scan-mode grey-no-auto --print-session 2026-08-05-A
```
→ `status: refused`, `corner_registration_failed`, exit 2. Report
`scratch/e031/reports/hcal-report-refused-unknown-copy0000-869f47828e9eb9fc.json`.

```sh
env/bin/python confetti.py discover analyze \
  scratch/in/xerox-canon-cal-color.tiff scratch/e031/reports --scan-dpi 4800 \
  --printer xerox-altalink-c8245 --print-path lpr-raw \
  --media white-office-a4-60-80gsm --scanner canon-4800 \
  --scan-mode color-no-auto --print-session 2026-08-05-A
```
→ `status: ok`, exit 0, `highest_useful_authored_grid_dpi [600, 600]`.
Report `hcal-report-discovery-color-copy0000-82abef068de7c651.json`
(file SHA-256 `e4b1482589b85a7d253937c87edf0c08b3ceef823b9fc7bfb0f9ebc663d66b79`).

**This colour report is the production-path evidence record for e031.**

## 3. The B/W refusal — an analyzer defect, not a bad print

`found chiral corners [3, 4]; need at least 3`. Corners 1 (top-left) and 2
(top-right) were lost.

### They are not clipped and not faint

- Predicted at (13.9, 13.1) mm and (194.1, 12.5) mm — well inside frame.
- Both marks are visually complete at full resolution: full crosses, correct
  satellite counts and chirality.
- Stroke continuity, robustly re-centred, all four corners of all three
  sheets (Xerox B/W, Xerox colour, M281 B/W e028): **every arm continuous**,
  gap fraction 0–3.1%, effective widths 25–28 scan px against a nominal 24.
  The top corners are 7–11% lighter than the bottom pair; nothing more.
  (`scratch/e031/stroke-continuity.json`.)

### Root cause

`detect_chiral_corners` derives the satellite search scale from the
component's own bounding box:

```
local_scale_x = width / nominal_w
```

On corner 1 the 300-dpi analysis thumbnail thresholds the horizontal arm
short, giving `h=60, w=36` against a nominal 61.5 — so `local_scale_x`
collapses to **0.585**, the expected satellite radius shrinks with it, and the
first satellite misses by **5.24** against a tolerance of 2.25. Zero
satellites match, and the candidate is dropped before it can compete.
Forcing the scale to 1.0 finds it at error **0.87**.

Corner 2 (`h=44, w=57`) fails for the same reason plus, as first written
here, "a second-order effect: truncating one arm displaces the projection
centroid used as the cross centre". **That second half is WRONG — see
§031.1.** It came from a bug in my own diagnostic, which located the cross
with a plain pixel centroid while the shipped `_component_center` is a
peak-region estimator already immune to a shortened arm. Corner 2 needed
only the scale fix, like corner 1.

Two independent routes agree the print is fine:
1. Forcing satellite scale to 1.0 at the stock 300-dpi thumbnail recovers
   corner 1 → corners [1,3,4], enough to register.
2. Raising the registration thumbnail to `target_dpi=400` recovers exactly
   the same set, [1,3,4].

Control: the Xerox colour sheet and the M281 B/W sheet find all four corners
at 300, 400 and 600 dpi thumbnails.

**Proposed fix (analyzer axis, no reprint, no emitter change):** derive the
satellite search scale from the un-truncated axis (or the nominal) rather
than the raw bbox — **that half landed, see §031.1** — and take the cross
centre from the intersection of the two strokes rather than the component
projection centroid — **that half was retracted, it was never needed.**
Filed as W8 in docs/CHARACTERIZE-WORKPLAN.md.

### Harness recovery — DIAGNOSTIC ONLY

`scratch/e031/harness_bw_recover.py`
(SHA-256 `65419d823629c7977f12ba6c7d5d995db93bce6c1cd6dae4c3eaa8b8e16dcd6d`)
monkeypatches exactly one thing — the registration thumbnail `target_dpi`,
300 → 400 — and runs the stock pipeline. Everything downstream samples at
native resolution through the fitted affine.

Report: `scratch/e031/reports-harness/hcal-report-discovery-bw-copy0000-f1e31d2b3944bf66.json`
(file SHA-256 `0aee4cdbe99268cbf7dc64e799d1003ecfc2feb2826952df710e4eb3c75ff3a2`),
with a `HARNESS-README.md` sidecar. The analyzer's own semantic-digest check
refused an attempt to annotate the report in place — the caveat lives beside
it, not inside it.

**This report must never be fed to `discover calibrate --from-report`,
`discover combine`, or any registry promotion.**

> **SUPERSEDED 2026-08-06 by §031.1.** W8a landed and the sheet now analyzes
> on the production path with all four corners. Cite
> `reports-w8/hcal-report-discovery-bw-copy0000-c4fd8826a63743f7.json`, not
> the harness. The harness numbers below are kept as the record of the
> refusal era.

Degradations to keep in mind when reading its numbers:
- 3-corner registration ⇒ the affine fits the corners exactly and
  `corner_fit_rms_layout_dots` is 0.000 by construction, i.e. meaningless.
- `internal_plus` residual rms/max **4.414 / 8.716** layout dots (e028:
  2.540 / 3.212); `registration_map` max displacement 10.8 dots (colour
  sheet: 5.8).
- Two 3-position candidates lost a position to `geometry_uncertified`
  (`matrix/4/p0`, `matrix/5/p0`), so `bw-k2-g600-c2` and `bw-k2-g600-c3` are
  `evidence_complete: false` and therefore not `provisional_usable` — an
  evidence-completeness artifact of the degraded registration, **not** a
  channel verdict. Every single-position row is evidence-complete.

## 4. Identity, device readback, and the print-path question

Both sheets: 2/2 strips valid, magic + CRC pass, **zero** xor repairs, parity
errors, sync errors or row-XOR errors; one distinct payload each.

| Field | Xerox (both sheets) | M281 e028 |
|---|---|---|
| product | `Xerox AltaLink C8245 Color MFP` | `HP Color LaserJet MFP M281fdw` |
| language level / version / rev | 3 / `3021.101` / 1 | 3 / `3017    ` / 1 |
| default → effective resolution | 600×600 → 600×600 | 600×600 → 600×600 |
| process colour model | **DeviceCMYK** | DeviceRGB |
| page size | 595×842 pt | 595×842 pt |
| serial / ImagingBBox | null / null | null / null |
| stable footing digest | `3c365e18e47e9f88b09a…` | `73d115359642ddb57c76…` |
| per-impression nonce | 5429797 (colour), 5408691 (B/W) | 1778767580 |

**The `lpr -o raw` concern is answered by the evidence.** The HCAL-R1 strips
carry readback executed *by the device's own PostScript interpreter*. A CUPS
filter chain that rasterised or re-rendered the job could not have produced a
live product string, language level, and effective-resolution report. Two
different nonces under one stable footing digest = two genuine impressions
from one device state.

Two limits stand anyway: `serial: null` means the footing binds a **model,
not a unit**; and the job requested no `/HWResolution`, so the 007.6/009
resolution-refusal question is untested here.

`integrity_gate`: all six paper witnesses visible and clean on both sheets.

## 5. Geometry and printable margin

Colour sheet: orientation r0, not mirrored, rotation −0.108°, shear 0.012°,
scale ×1.000943 / ×1.001430, all four corners found (contrast 0.353–0.373,
crossness 1.0), internal plus 10/10.

### Printable clip

`printable_clip_mm`, two independent sheets:

| Edge | Xerox colour | Xerox B/W (harness) | M281 e028 |
|---|---:|---:|---:|
| top | *1.339 (NOT MEASURED)* | *1.339 (NOT MEASURED)* | 4.247 |
| bottom | 1.923 | 2.050 | 4.247 |
| left | 1.966 | 2.057 | 4.194 |
| right | 3.949 | 3.853 | 4.279 |

Two separately printed sheets agreeing within 0.13 mm per edge is a strong
cross-check — but read the ladder, not the scalar:

- **top is censored, not measured.** Its five innermost ticks are
  `unobservable` (the sheet's top edge is off-raster, §1), and 1.3389 is
  simply the midpoint of `clip_bounds_mm` `[0.0, 2.678]`. It is not evidence.
- bottom/left rest on a single `partial` tick at 1.5 mm with `full` at
  2.0 mm, and fall ~0.10–0.14 mm *below* their own `clip_bounds_mm` lower
  bound of 2.067.
- right is the best-supported edge: `absent` through 2.5 mm, `partial` at
  3.0 (0.223) and 3.5 (0.568), `full` at 4.0.
- M281 for contrast is a clean boundary on all four edges: `absent` through
  3.0, `partial` at 3.5/4.0, `full` at 5.0 — matching its hand-measured
  4.13–4.28 mm.

**The defensible per-edge product is `safe_gap_mm` = {top 2.5, left 2.0,
right 4.0, bottom 2.0}**, and the right edge binds. `clip_scope` states the
measurement "convolves the engine margin with this impression's
print-to-paper registration", so the ~2 mm left/right asymmetry is
**unresolved** between engine margin and image placement on the sheet.

### Capacity consequence is small

At a uniform 4.0 mm margin the imageable area is 202 × 289 = 58,378 mm²
against 198 × 285 = 56,430 mm² at the locked 6.0 mm policy — **+3.45%**.
That is not worth changing engine and margin in the same step.

### Plane registration — read with care

`plane_registration` reports per-target offsets from K of up to ~115 µm
(worst: Y). **This is an upper bound contaminated by page geometry.**
layout.py:615 places the K/C/M/Y registration crosses of one target
4 mm apart in x (`x_mm = x + 4.0 * plane_index`), so the K→Y baseline is
12 mm; over that distance the page's own warp (registration_map max
displacement 5.83 layout dots ≈ 0.25 mm) leaks into the "plane offset".
The report contains **no** per-window per-plane phase measurement, so the
decode-relevant plane registration is **not measured on this pair**.

## 6. K channel — the clean cross-engine comparison

Identical stimulus (same `layout_digest`), same Canon footing, and K was the
*healthy* plane on the M281 (K tone range 0.656; only Y was starved), so this
comparison is legitimate. Worst-window figures are 95% Wilson upper bounds.

| candidate | pitch mm | b/mm² | Xerox err (U95) | Xerox win (U95) | M281 err (U95) | M281 win (U95) |
|---|---:|---:|---:|---:|---:|---:|
| `g300-c1` | 0.085 | 121.8 | 1.76 (2.00) | 4.16 (**6.11**) | 2.61 (2.89) | 5.72 (**7.92**) |
| `g1200-c4` | 0.085 | 120.7 | 1.91 (2.15) | 3.31 (**5.17**) | 3.05 (3.35) | 5.93 (8.29) |
| `g600-c2-horizontal` | 0.085 | 119.3 | 2.06 (2.32) | 6.84 (9.28) | 6.57 (7.00) | 9.67 (12.37) |
| `g600-c2-vertical` | 0.085 | 118.4 | 2.17 (2.43) | 3.90 (**5.88**) | 5.29 (5.68) | 8.35 (10.99) |
| `g600-c2` (square) | 0.085 | 116.4 | 2.48 (2.67) | 6.69 (8.92) | 3.48 (3.70) | 6.81 (9.02) |
| `g600-c2x3` | 0.085×0.127 | 89.6 | 0.42 (0.58) | 1.37 (**3.16**) | 0.27 (0.41) | 1.64 (**3.53**) |
| `g600-c3x2` | 0.127×0.085 | 88.7 | 0.52 (0.69) | 1.33 (**2.87**) | 0.27 (0.40) | 1.12 (**2.59**) |
| `g600-c3` | 0.127 | 61.5 | 0.08 (0.15) | 0.37 (2.08) | 0.00 (0.07) | 0.00 (1.47) |

Bold = clears the 8% worst-window gate.

**Calibrated statement.** The 84.7 µm equal-pitch club's
`position_variance_worst_error_spread` is **0.87 pp** (Xerox) / 0.92 pp
(M281). The Xerox club sits about one position-variance unit lower in
whole-field error, and clears the 8% worst-window gate on 2 of 4 measured
club members against 1 of 5 (marginally) on the M281. It is an improvement,
not a transformation, on single-copy single-position-per-row evidence.

**Registry note.** The `xerox-altalink-c8245` registry row says
"c2 ~12% raw (007.6)". Measured here: 1.50% (colour-sheet stress-K) and
2.06–2.48% (B/W sheet). That line is **stale rather than wrong** — the ~12%
is a legacy 2 px/dot figure, and CLAUDE.md already records c2 as
sampling-limited with ctx+PAVA reading 2–5% at 8 px/dot on Canon. `c1 dead`
stands (§8).

Authored grids: 300 and 600 `addressable: true`; 1200, 1200×2400 and 2400
`addressable: false`. Highest useful authored grid **600×600**, scale
nominal. The 1200/2400 rows that do measure are 600-dpi cells in disguise —
their physical pitch equals a 600-grid rung.

## 7. Colour

### Tone response — Yellow is a working plane here

| plane | Xerox range | Xerox corr | M281 range | M281 corr |
|---|---:|---:|---:|---:|
| K | 0.631 | 0.9941 | 0.656 | 0.9928 |
| M | 0.586 | 0.9948 | 0.520 | 0.9930 |
| C | 0.542 | 0.9953 | 0.643 | 0.9886 |
| **Y** | **0.515** | 0.9928 | **0.351** | 0.9727 |

Zero monotonicity violations on all four planes, both engines. The
end-to-end range understates the real difference — the **low-coverage**
regime is what a presence alphabet lives in:

| plane | Xerox density at 25% coverage − paper | M281 same |
|---|---:|---:|
| C | 0.0900 | 0.1085 |
| M | 0.1027 | 0.0734 |
| K | 0.0981 | 0.0821 |
| **Y** | **0.0714** | **0.0110** |

The M281's Y is essentially flat until 50% coverage. That is the quantitative
explanation of e030's Y-empty CMY8 failure, and the quantitative case that
the AltaLink does not repeat it.

`color_selectivity` intended-minus-worst-other density: **Y 0.485** (best of
the three), C 0.381, M 0.232.

### Plane overlap works — the sharpest result on the pair

The matched-PRN `devicecmyk-plane-content` control adds M content to C on the
identical emission path:

| | Δ off-GT excess energy | Δ strongest artifact ratio | direction |
|---|---:|---:|---|
| **AltaLink** | **−0.016125** | **−87.04** | lower-off-ground-truth-energy |
| **M281** | **+0.012282** | +13.91 | higher-off-ground-truth-energy |

This is the instrument-level counterpart to the M281 layer-0 freeze
(002.x/003.0: any region overlap of planes triggers a screened contone
re-screen) and its documented absence on the AltaLink (overprint works,
textbook Adobe — 007.x). The report labels the screening block descriptive,
single matched control, `requiring repeat prints before attribution`.

### Colour candidate ladder (selected)

| candidate | pitch mm | b/mm² | err (U95) | win (U95) | tier | usable |
|---|---:|---:|---:|---:|---|---|
| `cmy8-g600x600-c2x2` | 0.085 | 315.1 | 12.17 (12.89) | 17.67 (20.68) | fragile | – |
| `cmy7-g600x600-c2x2` | 0.085 | 322.6 | 7.74 (8.34) | 11.33 (13.88) | fragile | – |
| `cm4-g600x600-c2x2` | 0.085 | 217.0 | 7.02 (7.59) | 10.92 (13.45) | fragile | – |
| `cmy8-g600x600-c3x3` | 0.127 | 177.2 | 1.79 (2.27) | 3.56 (6.26) | marginal | **Y** |
| `cmy7-g600-c3-opm1` | 0.127 | 168.9 | 1.00 (1.38) | 2.26 (4.59) | marginal | **Y** |
| `cmy7-g600x600-c3x3` | 0.127 | 167.5 | 1.22 (1.64) | 2.98 (5.57) | marginal | **Y** |
| `cm4-g600x600-c3x3` | 0.127 | 123.3 | 0.11 (0.28) | 0.34 (1.92) | **solid** | **Y** |
| `pure-c-g600x600-c3x3` | 0.127 | 61.7 | 0.03 (0.16) | 0.36 (2.01) | **solid** | **Y** |
| `pure-m-g600x600-c3x3` | 0.127 | 61.8 | 0.03 (0.16) | 0.34 (1.90) | **solid** | **Y** |
| `pure-y-g600x600-c3x3` | 0.127 | 60.8 | 0.20 (0.41) | 0.73 (2.63) | **solid** | **Y** |
| `stress-k-g600-c2` | 0.085 | 124.1 | 1.50 (1.78) | 2.44 (3.87) | marginal | **Y** |
| `stress-y-g600-c2` | 0.085 | 115.6 | 2.58 (2.95) | 4.08 (5.87) | marginal | **Y** |

CMY7 is the more *consistent* alphabet — 5/5 equal-pitch replicates clear the
gate against 2/5 for CMY8. Do **not** state a CMY7-beats-CMY8 density
ordering from this sheet: the net-planning gap turns on one symbol error in
one of twelve windows and inverts under a p95-only reading.

The 31 provisionally-usable candidate rows collapse to **15 distinct
codings** once equal-pitch clubs are folded.

### THE STANDING CAVEAT ON ALL OF THE ABOVE

These are **hard-decision, per-cell, small-field, single-position channel
measurements. They are not receiver performance.** The same print day
recovered a **c2 CMY8 volume, state `verified`** (§10) on this engine, in the
regime this sheet calls fragile at 12.17%. The receiver brings per-window
pose, ctx+PAVA, plane calibration, LDPC and fountain; CLAUDE.md already
records the gap ("c2 ~11–14% at 2px/dot… at 8px/dot ctx+PAVA reads 2–5%").

**Use the discovery ladder to RANK rungs and to detect genuinely DEAD ones.
Never quote a candidate tier as a recoverability prediction.**

## 8. Morphology — isolated 1-dot at 600 dpi, both polarities

Measured by folding each probe over its own lattice period (~1000 periods),
sampled on the layout grid through the fitted affine so rotation does not
smear the fold; reflectance normalised to each probe's own paper white
(`scratch/e031/diag_morph.py`, figure `e031-single-dot.png`).

| feature | Xerox core / field | contrast | M281 core / field | contrast |
|---|---|---:|---|---:|
| **1×1 black dot** (pitch 8) | 0.893 / 0.953 | **0.060** | 0.938 / 0.950 | **0.013** |
| 2×2 black dot (pitch 12) | 0.663 / 0.949 | 0.286 | 0.582 / 0.944 | 0.362 |
| 3×3 black dot (pitch 16) | 0.512 / 0.952 | 0.440 | 0.426 / 0.948 | 0.522 |
| 4×4 black dot (pitch 20) | 0.458 / 0.952 | 0.494 | 0.342 / 0.944 | 0.602 |
| **1×1 white hole** (pitch 8) | 0.278 / 0.234 | **0.044** | 0.470 / 0.402 | **0.068** |
| 2×2 white hole (pitch 12) | 0.960 / 0.493 | 0.467 | 1.009 / 0.478 | 0.531 |
| 3×3 white hole (pitch 16) | 1.053 / 0.325 | 0.728 | 1.040 / 0.301 | 0.739 |
| 4×4 white hole (pitch 20) | 1.027 / 0.267 | 0.760 | 1.009 / 0.258 | 0.752 |

The analyzer's own 600-grid ruler agrees from a different estimator:
`dots` density separation 0.0144 (Xerox) / 0.0058 (M281), correlation
0.221 / 0.079, `passed: false` both.

Findings:

- **`cell=1 dead` CONFIRMED on the AltaLink**, both polarities. A single
  600-dpi black dot yields 6.0% contrast (Xerox) / 1.3% (M281); a single
  white hole never opens at all (4.4% / 6.8%) — the solid closes over it.
- **The 2×2 step is a cliff, not a slope**: black ×4.8 (Xerox) / ×28 (M281),
  white ×10.6 / ×7.8.
- **The engines fail asymmetrically.** The AltaLink is 4.6× better on an
  isolated black dot; the M281 is 1.5× better on an isolated white hole. The
  AltaLink lays a little ink where the HP lays none, and its solid is
  visibly more mottled. More dot gain, softer development.
- **Isolated-feature morphology and dense-field performance rank the two
  engines oppositely.** For a binary presence alphabet the binding number is
  the worse polarity: at 2 dots that is 0.286 (Xerox) vs **0.362** (M281) —
  yet the Xerox's c2 *field* error is 2–3× better. The explanation is
  neighbour interaction, not isolated contrast: at the 300 grid the M281's
  1-on/1-off vertical ruler collapses to **45.28%** (separation 0.026, corr
  0.101, fail) where the AltaLink reads **4.80%** (separation 0.238, corr
  0.874, pass).

CAVEAT on the ladder itself: it varies feature size **and** lattice pitch
together (1@8, 2@12, 3@16, 4@20 dots). Size and spacing are **not**
separated; the 1×1-vs-2×2 gap mixes a 2× size change with a 1.5× pitch
change. Separating them is a stimulus change, not an analysis one.

### Grid rulers, K plane

| diagnostic | Xerox err / sep / corr | M281 err / sep / corr |
|---|---|---|
| 300 grid `dots` | 0.71% / 0.139 / 0.696 **pass** | 1.30% / 0.071 / 0.473 **pass** |
| 300 grid `g1-h` | 2.69% / 0.264 / 0.900 pass | 0.29% / 0.223 / 0.926 pass |
| 300 grid `g1-v` | 4.80% / 0.238 / 0.874 **pass** | **45.28% / 0.026 / 0.101 FAIL** |
| 300 grid `g2-v` | 7.09% / 0.374 / 0.885 pass | 17.99% / 0.346 / 0.739 pass |
| 600 grid `dots` | 1.33% / 0.014 / 0.221 **FAIL** | 1.47% / 0.006 / 0.079 **FAIL** |
| 600 grid `g1-h` | 44.77% / 0.015 / 0.152 FAIL | 32.62% / 0.032 / 0.405 FAIL |
| 600 grid `g1-v` | 40.41% / 0.026 / 0.218 FAIL | 31.22% / 0.035 / 0.435 FAIL |
| 600 grid `g2-h` | 5.66% / 0.230 / 0.852 pass | 8.63% / 0.187 / 0.811 pass |

"Nyquist 1-on/1-off closes solid" confirmed on the AltaLink. The historical
H-vs-V anisotropy direction claims are **not** re-derived here: the mapping
between the `g1-h`/`g1-v` probe convention and the older
tall-cell/development-anisotropy language has not been checked, and should be
before either is cited against the other.

## 9. Yellow tracking dots (MIC) — the instrument is blind; measured directly

**The report cannot see them.** Zero occurrences of yellow/tracking/MIC/
lattice in 3 MB of JSON. Its only sparse-mark statistic,
`dark_fraction_below_0_80`, is Rec.709 luma with a 7.2% blue weight — the
*solid* Y patch on this very sheet has luma median 0.8215, i.e. 100% yellow
coverage barely crosses the threshold. Absence of evidence only.

Direct measurement on the blue deficit `(R+G)/2 − B` over blank paper
(`scratch/e031/diag_mic.py`, strict census in-line; figure
`mic-blue-deficit.png`):

- **0.210 dots/mm²** over 1,944 mm² of blank margin (409 dots, area ≥150 px,
  threshold = median + 8×IQR). Repo record 007.7/007.8: ~0.24 dots/mm².
- dot diameter median **163 µm**.
- lattice sites at **~1.016 mm = 24 dots @ 600 dpi**, exactly the recorded
  cell; in-row nearest-neighbour median 1.997 mm ⇒ roughly 22% site
  occupancy, consistent with an encoded pattern.

**A first, looser-threshold pass over the same area returned 0.583 dots/mm²
and was WRONG** — it admitted paper fibre specks (median blob 39 px vs the
real dots' 748 px). Recorded here so the number is not re-derived carelessly.

Whatever this costs per payload cell is already inside the measured pure-Y
c3 error of 0.20% / 0.73% on this sheet. The K-only anonymity lever stands.
**Untested here:** whether a *K-only* AltaLink page is clean — the B/W sheet
was captured in greyscale, where yellow is nearly invisible. A colour rescan
of the B/W sheet would settle it for this firmware.

## 10. Same-print-day payload volumes (recorded, NOT analysed in this experiment)

Decoded in a separate session; facts taken from each state's
`.diag/report.json`. Listed here because they bound the interpretation of
§7's channel ladder.

| state | format | status | recovered |
|---|---|---|---:|
| `holo-xerox-c2-cmy8-q05-counting` | `c2-cmy8-p120-v0@3328x2304` | **verified** | 718,413 B |
| `holo-xerox-c2-counting` | `c2-r0700@3392x2368` | **verified** | 465,580 B |
| `holo-xerox-c3-cmy7-counting` | `c3-cmy7-p120-v0@2240x1536` | **verified** | 301,600 B |
| `holo-xerox-c2-cmy7-counting` | `c2-cmy7-p120-v0@3328x2304` | open | — |
| `holo-hp-c2-cmy7-counting` | `c2-cmy7-p120-v0@3328x2304` | open | — |

**A c2 CMY8 volume closed VERIFIED on the AltaLink** — the coding and engine
combination e030 could not recover on the M281. That is the headline of the
print day and it is owed its own experiment log; this file does not claim
it.

## 11. Scanner adequacy — `inadequate`, and mostly common-mode

All four captures (2 engines × 2 page kinds) fail the same two gates:

| gate | Xerox colour | Xerox B/W | M281 B/W | M281 colour | limit |
|---|---:|---:|---:|---:|---|
| compression: quiet high-pass noise (8-bit counts) | 0.671 | 0.844 | 0.853 | 0.662 | ≥ 1.0 **fail** |
| compression: entropy blockiness 8px | 1.016 | 0.995 | 1.004 | 1.002 | < 1.25 pass |
| solid_class (`scanner/c3`) dot error | 0.0796 | 0.0796 | 0.1191 | 0.1518 | < 0.05 **fail** |
| marginal_class (`scanner/c2`) dot error | 0.1380 | 0.1626 | 0.1765 | 0.2000 | < 0.18 |
| identity | pass | pass | pass | pass | |

- **The compression gate fails on all four captures for a reason unrelated
  to compression.** Every file is uncompressed and blockiness is far under
  its ceiling; the gate fails purely on its noise floor. Two engines, both
  page kinds, same verdict ⇒ scanner-footing or gate, not printer.

  > **CORRECTION 2026-08-06 — the mechanism first written here was wrong.**
  > This section originally read "the gate is reading oversampling as
  > smoothing", implying the statistic itself was confounded. It is not.
  > An independent FFT estimate of the per-pixel white-noise plateau
  > reproduces the gate's own figure closely (0.808 vs its 0.844 on the
  > B/W sheet; 0.812 vs 0.853 on the M281's) — **the gate measures the
  > right quantity, and the noise floor genuinely is 0.47–0.81 counts.**
  > The defect is the fixed ≥1.0 threshold, not the measurement. Why the
  > floor is sub-count — a quiet sensor against a bright, low-contrast
  > target, versus in-backend averaging — is NOT settled by our data and
  > must not be asserted. Full measurement and the revised plan:
  > docs/CHARACTERIZE-WORKPLAN.md W9.
- `solid_class` **is** printer-sensitive: Xerox 0.0796 vs M281 0.119–0.152.
  The AltaLink is closer to passing but still fails.
- The Xerox B/W and colour sheets give identical solid_class values to four
  significant figures, which is itself evidence the probe is scanner-limited.

**What the verdict blocks:** printer qualification, registry-row promotion,
production receiver margins, and any clean separation of printer failure
from capture-footing failure.

## 12. Corrections made during this analysis

Recorded because each was a plausible wrong answer that measurement killed.

1. **"The top-left cross's horizontal arm is 97% missing."** Wrong — a
   mis-centring artifact. The similarity fit through the two *found* corners
   extrapolated 50–100 px of error to the far end of the page, outside the
   ±40 px refinement window, so the profile was sampled off the stroke. With
   a ±300 px robust search every arm is continuous.
2. **"The top corner marks printed lighter / there is a weak band at the top
   of the page."** Not supported: contrast at corners 1/2 is 0.756/0.716
   against 0.736/0.751 at corners 3/4.
3. **"c2 colour is a wall on this engine."** Wrong as a payload claim — see
   §7's standing caveat and §10.
4. **MIC density 0.583 dots/mm².** Wrong — threshold too loose, see §9.
5. **"463 fully certified colocated windows show per-plane phase
   0.60–0.72 dots."** No such field exists in the report; the numbers match
   the K-plane transport phase rails (x 0.453 / y 0.704). Dropped.

## 031.1 — W8a landed; the B/W sheet analyzes on the production path (2026-08-06)

Zero print, analyzer axis, same capture. Branch
`worktree-w8-corner-detector`; full plan status in
docs/CHARACTERIZE-WORKPLAN.md W8.

**The fix is one expression.** `detect_chiral_corners` seeded the satellite
search radius per-axis from the cross component's own bounding box, so a
threshold-clipped arm dragged that axis's scale down with it. It now seeds
from the longer axis:

```python
local_scale = max(width / nominal_w, height / nominal_h)
```

The mark is square by construction and `nominal_w`/`nominal_h` already carry
the per-axis sampling DPI, so a per-axis disagreement is truncation rather
than anisotropy; thresholding can only shorten an arm, which makes the longer
axis the better span estimate. Corner 1 went from missing its only satellite
by 5.24 (tolerance 2.25) to matching at 0.15.

**Result: all four corners, not the three the plan predicted.** Controls
unchanged — the e031 colour sheet and the e028 M281 B/W sheet keep all four
corners at identical centres, contrast, crossness and inward.

Production report:
`scratch/e031/reports-w8/hcal-report-discovery-bw-copy0000-c4fd8826a63743f7.json`.

| | harness (3 corners) | production (4 corners) |
|---|---:|---:|
| `corner_fit_rms_layout_dots` | 0.000 (exact fit ⇒ meaningless) | 3.068 |
| `internal_plus` residual rms / max | 4.414 / 8.716 | **2.688 / 5.138** |
| registration max displacement | 10.77 dots | **6.52 dots** |
| candidates measured | 24 | **26** |
| `geometry_uncertified` failures | 3 candidates | **none** |
| clip left / bottom / right (mm) | 2.057 / 2.050 / 3.853 | **2.015 / 1.945 / 3.980** |

Two consequences worth carrying forward:

1. **The §3 evidence-completeness caveat is gone.** Every
   `evidence_complete: false` disappeared, so `bw-k2-g600-c3` now reads
   `solid` and provisionally usable as its error numbers always deserved
   (0.09% whole-field, 0.35% p95 window), and `bw-k2-g2400-c8` and
   `bw-k2-g1200x2400-c4x8` become usable. §6's headline c2 comparison is
   unaffected — those rows were already evidence-complete.
2. **The B/W and colour sheets now agree on the print margin to within
   0.05 mm** (B/W 2.015 / 1.945 / 3.980 against colour 1.966 / 1.923 /
   3.949), where the harness disagreed by up to 0.19 mm. That materially
   strengthens §5's two-sheet cross-check. The top edge is still censored.

**One metric moved the wrong way, stated plainly:** the `marginal_class`
scanner probe reads 0.1857 against its 0.18 bar and now fails, where the
harness read 0.1626 and passed (colour sheet: 0.1380). Across our three
captures this gate straddles its own bar, so treat it as a straddle rather
than a verdict flip; the page verdict was `inadequate` either way, now on
three gates instead of two. No mechanism is claimed for the move.

**W8b retracted.** The plan asserted that corner 2 additionally needed a
stroke-intersection centre because a truncated arm displaces the projection
centroid. That was an artifact of my own diagnostic, not of the shipped
code: `diag_rootcause.py` located the cross with a plain pixel centroid,
while `detect_chiral_corners` uses `_component_center`, a peak-region
estimator already immune to a shortened arm. Measured on the capture, the
truncated corners report their satellites at (+17.6,+17.3) and
(+17.2,−17.2)/(+28.9,−29.7) layout dots against the authored 18/30 — the
shipped centre was correct throughout. This is the same failure mode as
§12's items 1 and 4: a hand-rolled probe aimed slightly wrong, believed for
longer than it should have been.

## 13. What this experiment does NOT license

- No registry promotion, no margin change, no coding promotion.
- No printer qualification: scanner adequacy `inadequate` on both captures.
- Single copy, single position per candidate row, discovery stage,
  `production_receiver_claim: false`.
- The B/W numbers come from a patched registration path and are diagnostic.
- The print path is `lpr-raw`, not `raw9100`; do not `combine` these reports
  with any socket-9100 footing.
- Media stock is not exactly recorded.

## 14. Owed

1. ~~**W8 corner-detector fix** — then re-analyze the B/W capture on the
   production path and supersede the harness report.~~ **DONE 2026-08-06,
   §031.1** (W8a landed, W8b retracted, harness superseded).
2. **Payload experiment log** for the same-day AltaLink volumes, especially
   the verified c2 CMY8 (§10). No paper.
3. ~~**Scanner-adequacy compression gate**~~ **DONE 2026-08-06 in two
   stages** — W9 recalibrated the noise floor from measurement (neither of
   the originally proposed fixes survived: the statistic was right, the
   threshold wrong), then W10 retired the blank-paper spectral advisory and
   added structured-feature checks (phase-invariant comb, slanted-edge
   overshoot, ruler contrast ratios). docs/CHARACTERIZE-WORKPLAN.md W9/W10.
4. **Registry note**: the `xerox-altalink-c8245` row's "c2 ~12% raw" is
   stale. Left untouched here deliberately — editing it is a promotion
   decision, not an analysis one.
5. **Re-scan with the 5 mm platen inset** to measure the top clip and settle
   the left/right asymmetry. Scan only, no print.
6. **Colour rescan of the B/W sheet** to test the K-only-is-MIC-clean claim
   on this firmware. Scan only, no print.
7. Separate feature size from lattice pitch in the morphology ladder — a
   stimulus change, so a future emit.

## Artifacts

**Tracked harnesses** (`experiments/031-xerox-altalink-discovery/`, run from
the repo root) — these are cited as method by docs/CHARACTERIZE-WORKPLAN.md
and so are version-controlled rather than left in gitignored `scratch/`:

- `w8_verify_corners.py` — W8's real-capture regression bar. Pins the eight
  control corner centres from the pre-fix run and exits non-zero if any
  moves. Demonstrably discriminating: **red on a tree without W8a** (e031
  B/W finds only [3,4]), **green on one with it**.
- `w9_capture_forensics.py` — W9's measurement: spectral knee, white-noise
  plateau, histogram occupancy and gzip ratio on a blank-paper patch of four
  captures. Its section A is marked CONFOUNDED in the file header and must
  not be reused; its section B knee reading was later retracted as
  patch-unstable (header note, workplan W9 second pass).
- `w10_structured_capture_checks.py` — W10's threshold derivation: comb on
  clean blank patches vs JPEG controls at any phase/scale, and slanted-edge
  overshoot on the two real B/W edges vs an optics-scale unsharp control.
  Exits non-zero if the shipped constants stop sitting between clean and
  degraded with margin.

The remaining diagnostics below stay in `scratch/e031/` deliberately: they
are the record of how the diagnosis went, not re-runnable method.

`scratch/e031/`: `reports/` (production colour report + the refused B/W
report), `reports-harness/` (diagnostic B/W report + README),
`capture-shas.txt`, `stroke-continuity.json`, `morph.pkl`, and the read-only
diagnostics `diag_corners.py`, `diag_gates.py`, `diag_ink.py`,
`diag_rootcause.py`, `diag_strokes.py`, `diag_strokes2.py`,
`diag_thumbdpi.py`, `diag_mic.py`, `diag_morph.py`, `harness_bw_recover.py`,
plus figures `e031-summary.png`, `e031-pitch-ladder.png`,
`e031-single-dot.png`, `e031-single-dot-raw.png`, `mic-blue-deficit.png`.
(2026-10-09: `diag_mic.py`, `diag_mic2.py`, `diag_morph.py`, `diag_strokes.py`,
`diag_strokes2.py`, `fig_morph.py`, `fig_morph_raw.py` moved to
`experiments/031-xerox-altalink-discovery/`; `diag_corners.py`, `diag_gates.py`,
`diag_ink.py`, `diag_rootcause.py`, `diag_thumbdpi.py`, `harness_bw_recover.py`
retired 2026-10-09, their result stands above.)
