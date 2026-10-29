# Experiment 025 — systematic physical-channel metrology

**Status: forward E025 layout v2 built and synthetic-preflighted; first HP
M281 K/color pair printed and analyzed through Canon 4800-dpi reference scans
on 2026-07-17. Both one-sheet survey profiles are honestly unqualified.**

> **2026-07-18 — analyzer v3.** The 2026-07-17 channel numbers for small cells
> were dominated by the analyzer's geometry model, not by the printer. One
> constant lattice phase per field cannot track a page whose required phase
> leaves the +/-0.48-cell search box (up to +2.28 cells) and drifts within a
> single field (up to 2.49 cells). Re-sampling the same pixels per window takes
> `spatial/top/c3` from 11.40% to **0.44%** and `grid-control/600-c2` from
> 43.04% to **3.86%**. Use `--geometry window`; several 2026-07-17 claims are
> retracted in [RESULTS.md](RESULTS.md). The remedial plan and what is still
> undone is [WORKPLAN-analyzer-v2.md](WORKPLAN-analyzer-v2.md).

E025 consolidates printer, scanner, color, morphology, geometry, printable-
extent, random-channel, and production-code checks into two dense one-page
instruments. It answers:

1. how far a printer/path/media/consumable state can be pushed when observed
   by a declared reference scanner;
2. how much of one frozen physical sheet a target scanner/mode preserves;
3. whether an exact current printer→paper→scanner path is feasible for a
   selected channel and code rate.

The live design does not decode the superseded LDPC-atlas sheets. Their source
and manifests remain in Git history.

## Components

- `e025_common.py` — fixed seed, exact channel registry, patterns, and GT;
- `emit_e025.py` — one-page K or color generator and planning capacity table;
- `analyze_e025.py` — machine-strip decode, geometry/probe/channel/FEC scoring,
  payload-safe extent, measured capacity, diagnostics, and optional traces;
- `profile_e025.py` — emitter/sensor/pipeline aggregation and advisory hint;
- `DESIGN.md` — rationale, page anatomy, and rejected shortcuts;
- `SCHEMA.md` — manifest, strip, report, trace, and profile contracts;
- `HOWTO.md` — operational commands;
- `RESULTS.md` — synthetic and later physical results.

## Two pages, not a page per mode

`hp-m281-bw` is a true K-only job. `hp-m281-color` contains CMY and K controls.
They are separate because adding color can change the printer operating path.
Each is exactly one A4 page.

Both pages include:

- two CRC-protected print-time device strips;
- independent physical-ink and payload-safe edge probes;
- chiral corners, internal warp marks, and x/y phase rails;
- fixed-level full-width density profiles plus position-permuted tone-response
  strips;
- controlled paper-white witnesses; on color, nine distributed K/C/M/Y
  registration targets and four feed-direction density lanes;
- H/V gratings, line/space morphology, dots, holes, checkerboards, slanted
  edges, and raster microprint;
- large deterministic state fields;
- equal-pitch controls across authored addressing grids;
- small actual house-LDPC confirmation coupons.

The K page has 51 fields and 136 probes. It concentrates area on C1/C2/C3
evidence while retaining smaller C4/C6 controls, and includes matched C2
solid/diagonal/horizontal/vertical motifs plus C1xC2/C2xC1 aspect controls.
The color page has 47 fields and 200 probes. It contains pure K/C/M/Y C2,
CM4, exact CMY8, a KCMY one-hot four-state candidate, matched-grid controls,
and an independent CMY8 OPM path.

## Coordinate law

Authored grid, c factor, requested grid, print-time readback, and measured
recovery are separate facts. Equal physical pitch does not imply equal RIP
behavior:

```text
300/c1 = 600/c2 = 1200/c4 = 2400/c8   (nominal pitch only)
```

The emitter accepts a primary grid and arbitrary comparison grids. A device's
reported `/HWResolution` is retained in the machine strip but never promoted
to recoverable resolution without field evidence.

## Fixed seed and primary evidence

The public seed is:

```text
paper-store/e025/channel-metrology-v2
```

It never depends on a payload or hash. Random fields are balanced exact state
stimuli. Their held-out state/bit errors, MI, location, and optional full
traces are the primary channel evidence. LDPC coupons confirm production-code
compatibility; two words per level/rate are not presented as a precise BLER
curve.

The analyzer has explicit arms for every physical addition: deconfounded tone
models and fixed-level profiles, paper-background shading fits, CMY-to-K
registration residuals, morphology scoring, and held-out BER/MI for the
shape/aspect/constellation factorials. No target is visual-only.

## Printable area and capacity

Solid ticks measure physical ink reach. C2 random canaries measure the
payload-safe margin at each edge. The analyzer takes the smallest gap whose
canary and every more-inboard canary pass, then computes a conservative usable
rectangle.

Capacity rows report:

- raw bits in that measured rectangle;
- empirical information from the worst held-out MI;
- coded bits for exact passing coupons;
- explicit warning that production furniture and outer fountain overhead are
  not yet subtracted.

This replaces the historical assumption of a fixed 200×287 mm printable A4
area.

## Measurement and profile boundaries

- An emitter profile is printer/path/media/consumables *through one declared
  reference scanner*.
- A sensor profile compares scans of the same physical `sheet_id`; a reprint
  is a different pipeline.
- A pipeline profile binds the exact intended path and may emit a disposable
  receiver hint.
- Hints can never lower placement, LLR, LDPC, fountain, or CRC gates.
- The current independent-calibration QDA detector does not automatically
  certify E023b or another production detector.

See [HOWTO.md](HOWTO.md) for commands and [DESIGN.md](DESIGN.md) for the full
reasoning record.

2026-10-09: the Phase A decisive test (`phase-a/plot_field_maps.py`, `shift_recovery_test.py`,
`perband_phase_probe.py`; RESULTS.md) was retired from scratch/e025/ into `phase-a/`; it reads
`e025/` (traces, reports, captures) under `--evidence-root` and writes `build/phase-a/`.

2026-10-09: inputs renamed to the published archive paths. `perband_phase_probe.py` reads, under
`--evidence-root` (the archive root), `paper-store-evidence-paperholo-era/025-channel-metrology/`
`bw-01/captures/bw-01-canon-4800grey-rot180.tiff`, `color-01/captures/color-01-canon-4800rgb.tiff`
(both published as `.tiff.jxl`, rebuilt by the release's `tools/unpack.sh`) and
`records/analysis/rerun-{bw,color}-report.json`; `plot_field_maps.py` reads the two reports. The
detector traces (`trace-bw/`, `trace-color/`) are NOT in the published archive (tier delete,
regenerable): `plot_field_maps.py` and `shift_recovery_test.py` read them from
`build/trace-{bw,color}/` and refuse by name until they are regenerated with `analyze_e025.py
--trace-dir build/trace-{bw,color}` on the published captures, every other option mirrored from the
published rerun report's metadata (WORKPLAN-analyzer-v2.md §3 step 1).

## 2026-10-22 — the superseded `-v1` atlas pair regenerates at main

The two jobs of the first E025 layout (`hp-m281-bw-v1.ps`, `hp-m281-color-v1.ps`
and their manifests; printed once on 2026-07-16, never scanned into the record,
superseded the next day; published in the paperholo-era evidence release under
`025-channel-metrology/{bw-v1,color-v1}/jobs/`) are remade from the current tree
by the first version of this directory's two emitter files run against main's
library (measured 2026-10-22, `docs/evidence-archive/REGENERATION-2026-10-22.md` §4.4):

```text
git show 9df37bf1:experiments/025-channel-metrology/emit_e025.py   > build/v1/emit_e025.py
git show 9df37bf1:experiments/025-channel-metrology/e025_common.py > build/v1/e025_common.py
PYTHONPATH=src:. env/bin/python build/v1/emit_e025.py --preset hp-m281-bw-v1    --out build/v1/hp-m281-bw-v1
PYTHONPATH=src:. env/bin/python build/v1/emit_e025.py --preset hp-m281-color-v1 --out build/v1/hp-m281-color-v1
```

PS `88f96b6d…` / `7e9a7edf…` and manifests `8c3f2f6c…` / `5b423f11…` come out
byte-identical. Nothing decodes those two sheets, by design (RESULTS.md, "the
previously printed LDPC-atlas pair belongs to the superseded implementation").
The live pair, `bw-01` / `color-01`, is `emit_e025.py --preset hp-m281-bw` /
`hp-m281-color` at main, byte-identical from `dac54673` (2026-07-17) on.
