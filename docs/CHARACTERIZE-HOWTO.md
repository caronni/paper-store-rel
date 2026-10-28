# Printer discovery and calibration workflow

This instrument measures one exact printer, driver/path, media, request
footing, and scanner mode. It does not discover every hidden printer mode,
and it does not produce a production format profile by itself.
Here, `discover` means printer/scanner channel metrology, not receiver format
discovery.

## 1. Commands and help

The characterization commands are below the top-level `discover` router:

```sh
./confetti.py discover -h
./confetti.py discover emit -h
./confetti.py discover analyze -h
./confetti.py discover calibrate -h
./confetti.py discover combine -h
./confetti.py discover candidates -h
```

- `emit` writes the current B/W and/or color discovery jobs and manifests.
- `analyze` identifies one scanned sheet from HCAL-R1, measures it, and writes
  a page report.
- `calibrate` writes independently seeded, position-balanced pages for an
  explicit shortlist or candidates selected from discovery reports.
- `combine` takes conservative minima across compatible calibration copies.
- `candidates` prints the fixed current registry; use `--kind bw` or
  `--kind color` to filter it.

`candidates` is intentionally part of `discover`, not `registry`.
`confetti.py registry` describes production format/device rows; it does not
list scratch-sheet experiments or promote measurements. There are no hidden
or unwired characterization subcommands and no E025/Track-2 compatibility
mode.

## 2. Emit the default discovery pair

Use a new output directory for every bundle:

```sh
./confetti.py discover emit scratch/discovery-copy0
```

The output contains separate one-page B/W and color PostScript jobs, a
manifest for each page, and a bundle manifest. The default jobs omit
`/HWResolution`; this is the printer path's default-rendering footing.

Print each PostScript file as a one-page job through the path being measured.
Disable application-side “fit to page” or scaling. Record printer, driver or
raw path, media, supplies, date, and any operator setting in the box on the
sheet and in the run notes.

Each sheet has two separated HCAL-R1 strips. They combine minimal page
identity with live PostScript readback: language level; pre-request default
and post-request effective resolution; page size and imaging box;
duplex/tumble and color model; and product, version/revision, and serial where
available. This is provenance, not proof that the printer honored a request
or can resolve the corresponding cells.

### Optional Ghostscript preflight

Before sending a newly generated job to hardware, check that Ghostscript can
consume the complete PostScript stream:

```sh
gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=nullpage SHEET.ps
```

To inspect a full-page 600-dpi raster suitable for a software dry-run:

```sh
gs -q -dSAFER -dBATCH -dNOPAUSE \
  -sDEVICE=png16m -r600 -o SHEET.png SHEET.ps
```

Do not use the Ghostscript raster as printer evidence. It is an emitter and
analyzer dry-run with an ideal renderer.

## 3. Scan

Scan the complete physical A4 sheet at a known true capture DPI. Preserve
native bit depth where practical. Supply RGB or RGBA reflectance data for the
color page (or black-is-zero grayscale for B/W); CMYK, YCbCr, palette, and
other encoded color models are refused rather than guessed.
For high-resolution captures, use a single-page, contiguous uncompressed
TIFF so the analyzer can memory-map it. A compressed or tiled image whose
decoded raster would exceed 256 MiB is refused instead of being expanded
into RAM.
Disable automatic crop, geometric correction, sharpening, despeckle, and
adaptive contrast. Those settings may be measured later as their own scanner
footings.

**Inset the page ~5 mm from the platen origin on both axes** (028.2
protocol): all four physical paper edges then land in-frame with visible
background, which makes `geometry.paper_edges` able to separate
print-to-paper registration (feed offset/skew) from paper-on-platen
placement, and keeps the smallest edge probes observable. A page placed
flush loses its origin-side edges to the frame boundary.

A rescanned same physical sheet permits a manual scanner comparison: analyze
it under a separate scanner footing and compare capture, geometry,
quiet-zone, tone, and candidate fields. The tool intentionally does not merge
different scanner footings. A newly printed sheet mixes printer and scanner
variation.

## 4. Analyze each scan

The page manifest is optional. HCAL-R1 supplies the printed identity and
device provenance; physical conclusions come from the measured sheet:

```sh
./confetti.py discover analyze \
  scan-bw.tif scratch/reports --scan-dpi 1200 \
  --printer NEW-PRINTER --print-path DRIVER-OR-RAW --media STOCK \
  --scanner REFERENCE-SCANNER --scan-mode COLOR-NO-AUTO \
  --print-session 2026-07-24-A

./confetti.py discover analyze \
  scan-color.tif scratch/reports --scan-dpi-x 1200 --scan-dpi-y 1200 \
  --manifest scratch/discovery-copy0/hcal-discovery-color-....manifest.json \
  --printer NEW-PRINTER --print-path DRIVER-OR-RAW --media STOCK \
  --scanner REFERENCE-SCANNER --scan-mode RGB-NO-AUTO \
  --print-session 2026-07-24-A
```

Expected hard failures become a JSON report with `status: "refused"` and a
specific stage/code. The analyzer never clips an out-of-frame element into
plausible evidence. A refused report is still written and the command exits
with status 2, which makes refusal explicit to automation.

First inspect `machine_report`: at least one strip must decode, and every
valid strip must carry the same CRC-protected payload. `device_footing`
contains a digest over stable readback fields; its per-impression nonce is
retained in the strip record but deliberately excluded from that digest.
Treat default/effective resolution and `/ImagingBBox` as provenance. The
measured geometry, rulers, channel fields, and edges decide what was actually
printed.

On success the command prints the JSON status object followed by a
derived **operator summary block** (schema v4): device readback, highest
useful grid, the print margin (per-edge `printable_clip_mm`), payload
edge-flat gaps, the scanner-adequacy verdict with its failing gates, the
top shortlist candidates with whole-field/p95-window error and density
(equal-pitch clubs collapsed, spread shown), capacity at the measured
clip, and the registration/paper-edge status lines. The JSON report
stays the evidence record; the block is derived and never authoritative.

The main result is `summary.dpi_and_cells.grids`: for every authored grid it
lists the smallest provisionally usable tested cell by alphabet. The
`highest_useful_authored_grid_dpi` is local to this evidence footing and is
not a claim about manufacturer-native resolution. Also inspect:

- `equal_physical_pitch_controls` before crediting a higher authored grid
  (the shortlist already collapses equal-pitch twins to one physical
  candidate per club);
- `diagnostics.physical_ink_extent.printable_clip_mm` — THE print margin
  (layout-referenced clip line, ruling 2026-08-04) — and
  `payload_extent`'s BER-vs-gap curves with `edge_penalty` as the check
  against it; there is deliberately no "safe rectangle" verdict;
- `capacity_by_margin_mm` (capacity as a function of a chosen margin) and
  `rung_planning` (hard-decision single-copy ESTIMATE; binding rungs come
  from calibrate/combine);
- `registration_map` and `geometry.paper_edges` for displacement and
  print-to-paper registration;
- `tone_response`, full tone-profile traces, `morphology`, x/y phase rails,
  and the complete scanner-adequacy verdict — including the capture
  forensics: the phase-invariant blocking comb and slanted-edge sharpening
  checks gate; `capture_contrast_ratios` and `level_occupancy` are advisory
  (workplan W9/W10);
- per-grid/per-plane g1, g2, dots, and line-pair diagnostics;
- color-plane registration and selectivity, plus the matched-PRN screening
  summary on the color report. Read its C-only path, C+M path, and
  plane-content comparisons separately; they are descriptive until repeated;
- every refusal, incomplete exact reference, and window dispersion.

## 5. Emit calibration sheets

Shortlist up to eight provisionally usable candidates from each discovery
report:

```sh
./confetti.py discover calibrate \
  scratch/cal-copy1 \
  --from-report scratch/reports/hcal-report-discovery-bw-....json \
  --from-report scratch/reports/hcal-report-discovery-color-....json \
  --copy-index 1
```

The request footing must match the discovery report. Calibration gives every
candidate six position-balanced fields with a fresh copy seed. Edge canaries
use the selected smallest- and largest-pitch candidates. Emit later copies
with new copy indices.
Copies printed in one session measure sheet/content variation; they are not
independent day/consumable sessions.

Analyze calibration scans exactly as discovery scans, then combine matching
reports:

```sh
./confetti.py discover combine \
  scratch/cal-summary scratch/reports/hcal-report-calibration-....json \
  scratch/reports/hcal-report-calibration-....json
```

The combined result uses the worst position within each copy and the worst
copy, including the worst 4.7 mm window's Wilson upper bound. Combination
requires at least two different copy indices, the same
printer/path/media/scanner/mode and scanner-DPI footing, and a declared print
session on every report. It also requires the same stable HCAL-R1
device-footing digest; the impression nonce is excluded so separately printed
copies can combine. `source_evidence` binds each copy index to the exact
analysis-report digest, capture SHA-256, layout digest, and page-plan digest,
so the combined result remains auditable. Promotion into a production device
registry is a separate reviewed action.

## 6. Optional requested-resolution footings

Only after the default pair, emit a separate bundle such as:

```sh
./confetti.py discover emit \
  scratch/discovery-request1200 --request 1200
```

This asks the PostScript device for that resolution under `stopped`; it does
not prove the request was honored. Never merge its results with `default`,
another request value, another print path, or another media footing.
When emitting calibration from this footing, repeat `--request 1200`.

The tool does not perform E007/DISC-1-style trial enumeration inside the
science job. If several requested modes matter, emit, print, scan, and analyze
one separate bundle per request.

## 7. Explicit candidate selection

Inspect the fixed current registry with:

```sh
./confetti.py discover candidates
```

An explicit one-kind calibration must name the kind:

```sh
./confetti.py discover calibrate \
  scratch/cal-bw-copy1 --kind bw --candidate 1 --copy-index 1
```

Likewise, a single B/W or color `--from-report` needs `--kind bw` or
`--kind color`; the default `both` requires evidence for both page kinds.
Only successful current discovery reports are accepted by `--from-report`.
