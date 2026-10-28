# E025 operational guide

Run commands from the repository root. Generation and analysis are safe local
actions. Printing consumes hardware and remains governed by
`.claude/rules/hardware.md`; do not send either job without explicit current-
session authorization.

## 1. Emit the two current pages

Monochrome:

```bash
env/bin/python experiments/025-channel-metrology/emit_e025.py \
  --preset hp-m281-bw
```

Color:

```bash
env/bin/python experiments/025-channel-metrology/emit_e025.py \
  --preset hp-m281-color
```

Outputs:

```text
experiments/025-channel-metrology/build/hp-m281-bw.ps
experiments/025-channel-metrology/build/hp-m281-bw_manifest.json
experiments/025-channel-metrology/build/hp-m281-color.ps
experiments/025-channel-metrology/build/hp-m281-color_manifest.json
```

Each PostScript file contains exactly one page. The command prints field/probe
counts, artifact size, and a nominal 10 mm capacity table. That table is only
for planning; scan analysis replaces it with measured edge margins.

Use `--capacity-only` to inspect planning capacity without writing artifacts:

```bash
env/bin/python experiments/025-channel-metrology/emit_e025.py \
  --preset hp-m281-bw --capacity-only
```

## 2. Choose addressing and requested grids

The defaults author the main fields at 600 dpi, include matched controls at
300/1200/2400, and request the authored 600×600 grid.

For a printer whose useful path may be 1200 dpi:

```bash
env/bin/python experiments/025-channel-metrology/emit_e025.py \
  --preset hp-m281-bw \
  --primary-grid 1200 \
  --comparison-grids 300,600,2400 \
  --request authored \
  --out scratch/e025/printer-x-bw-1200
```

Matched-pitch c factors are derived from the primary C2 pitch. Thus a
1200-primary job compares 300/C1 only when the ratio is representable and
uses the nearest positive integer otherwise. Always inspect the manifest's
exact grid/c identity.

`--request` accepts:

| value | behavior |
|---|---|
| `authored` | request primary-grid × primary-grid |
| `default` | omit `/HWResolution` entirely |
| `XxY` | make an explicit anisotropic request |

For an unknown printer, compare otherwise identical `default` and explicit
jobs. Do not infer useful resolution from readback alone.

## 3. Print protocol

Before an authorized print:

1. record printer, raw path, media, consumable state, requested grid, and
   artifact SHA-256;
2. confirm the job is the intended one-page K or color artifact;
3. use the verified raw PostScript path (`nc` or `lpr -o raw` as appropriate);
4. label the physical copy with a unique `sheet_id` outside science content;
5. inspect that both machine strips, corners, and edge probes reached paper.

Do not combine the K and color PostScript into one job. Their separation is an
operating-path control.

## 4. Reference scans for printer characterization

Use the best available scanner and record exact mode/DPI. Prefer lossless,
full-page, color-preserving capture with descreen, sharpening, auto contrast,
and automatic cropping disabled. A monochrome page may be scanned in grey and
RGB if scanner-mode effects are themselves of interest.

Example:

```bash
env/bin/python experiments/025-channel-metrology/analyze_e025.py \
  scratch/e025/hp-bw-reference.tiff \
  --manifest experiments/025-channel-metrology/build/hp-m281-bw_manifest.json \
  --scan-dpi 1200 \
  --printer-id hp-m281 \
  --scanner-id canon-reference \
  --scan-mode '1200-rgb-raw' \
  --role emitter \
  --sheet-id hp-e025-bw-copy1 \
  --media 'office-80gsm' \
  --consumable-state '2026-07-17' \
  --diag scratch/e025/hp-bw-reference-diag.png \
  --out scratch/e025/hp-bw-reference-report.json
```

The analyzer automatically decodes effective resolution from the redundant
machine strips. `--readback XxY` is only a manual fallback.

### Geometry mode (read this before quoting a small-cell number)

```text
--geometry field     # default; one constant lattice phase per field (v2)
--geometry window    # per-window phase (v3), --window-cells N to retune
```

Use `--geometry window` for any candidate whose cell is small relative to the
page warp — in practice everything at c1/c2/c3. On the first physical pair the
default mode reported `spatial/top/c3` at 11.40% and `grid-control/600-c2` at
43.04%; the same pixels under `--geometry window` read 0.44% and 3.86%. The
default is retained only for comparison with pre-2026-07-18 reports.

Window mode is a strict superset: windows that cannot solve their own geometry
fall back to the whole-field phase, so it never reads worse. It costs roughly
2-4x the runtime of field mode on large fields.

Do not crop to the printed marks. Preserve the whole scanner bed/page extent.
If a registered edge probe still lies partly outside the captured raster, the
analyzer records it as `unobservable`; it does not infer printer clipping.

### Full detector traces

Add:

```text
--trace-dir scratch/e025/hp-bw-reference-trace
```

This writes one compressed NPZ per channel field plus `index.json`. It can be
large, so traces are opt-in. The analyzer remains crop/chunk based for
memory-mappable high-resolution TIFFs.

## 5. Read the report

Important sections are under `metadata.e025`:

- `device_readback_strips`: both CRC results and live device fields;
- `geometry`: corner affine, scale/skew, plus residuals, and phase rails;
- `probes.printable_ticks`: physical ink boundary;
- `payload_safe_extent`: per-edge C2 decisions and usable rectangle;
- `probes.tone_metrology.fixed_profiles`: full-width/height density profiles,
  robust spans, and exact authored-coverage profiles;
- `probes.tone_metrology.deconfounded_models`: per-plane tone curve and
  separately fitted page-x/page-y density slopes;
- `probes.background`: ten controlled paper witnesses and R/G/B shading fit;
- `probes.plane_registration`: per-station CMY-minus-K registration vectors;
- `probes.morphology_frequency`: resolved/error metrics by shape/orientation;
- `field_summaries`: held-out BER/MI and exact FEC outcomes;
- `candidate_factorials`: matched motif, aspect, constellation, and emission
  path comparisons;
- `capacity`: raw, empirical-information, and confirmed coded estimates.

The solid-tick margin and payload-safe margin answer different questions. Use
the latter for payload capacity. Morphology rows also retain their bounded
local translation; this removes global-pose phase but not blur or deformation.
Payload-canary rows name the exact designated interior fields that set their
BER/MI threshold.

## 6. Build an emitter profile

One sheet is a survey, not a durable production law:

```bash
env/bin/python experiments/025-channel-metrology/profile_e025.py \
  scratch/e025/hp-*-reference-report.json \
  --kind emitter \
  --policy survey \
  --out scratch/e025/hp-emitter-profile.json
```

`production` requires three physical sheets and `archive` six. Those policies
also tighten worst BER and MI fraction and require exact coupon diversity.
An emitter profile also requires one exact reference-scanner footing. For
example, a 4800-dpi grey K capture and a 4800-dpi RGB color capture must be
profiled separately even when they came from the same Canon; merging them
would erase scanner-mode dependence.

## 7. Characterize a scanner

Choose the most robust, best-characterized physical E025 sheet. Do not reprint
it. Scan that same sheet on the target and reference scanners, using the same
`sheet_id`, then analyze target reports with `--role sensor`.

```bash
env/bin/python experiments/025-channel-metrology/profile_e025.py \
  scratch/e025/hp-flatbed-target-report.json \
  --kind sensor \
  --policy survey \
  --reference scratch/e025/canon-reference-report.json \
  --out scratch/e025/hp-flatbed-sensor-profile.json
```

The profiler requires identical stimulus digests and exact field sets. A
separately printed copy characterizes a different pipeline, not the scanner.

Run HP flatbed, HP ADF, Canon, and Xerox modes separately. Mode-dependent
scale, clipping, and color behavior are part of the result.

Where the scanner permits it, scan the same sheet at 0 and 180 degrees and
record orientation in `--scan-mode`/`--capture-id`. Page-fixed effects rotate;
scanner-fixed shading and transport effects do not. For printer profiles also
record cold-start versus warmed-up copy, tray, paper side/orientation, and the
printer/scanner leading edge. These repetitions add causal value without
spending page area, but only distinct physical prints count as independent
printer evidence.

## 8. Qualify an exact job path

Print and scan through the intended printer, paper, consumables, scanner, and
mode. Analyze with `--role pipeline`, then:

```bash
env/bin/python experiments/025-channel-metrology/profile_e025.py \
  scratch/e025/job-pipeline-*-report.json \
  --kind pipeline \
  --policy production \
  --out scratch/e025/job-pipeline-profile.json
```

A qualified profile may contain an advisory `receiver_hint`. It cannot lower
any receiver gate. Production layout furniture, fountain recovery, and final
payload SHA/CRC remain separate from E025's before-furniture capacity.

## 9. Synthetic preflight

```bash
HOLO_RUN_SLOW_TESTS=1 \
  env/bin/pytest -q tests/test_e025.py
```

The preflight emits and renders both pages, decodes the machine strips, scores
physical and random-field evidence, checks the measured synthetic rectangle,
recovers every FEC coupon word, and builds a profile.

Without the environment switch, the fast deterministic E025 tests still run
in the ordinary suite; only the roughly minute-long Ghostscript/analyzer
roundtrip cases are skipped.
