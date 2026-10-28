# Standalone scrap scan generator

`holo.qualification.scrap_scan` is a TIFF-in/TIFF-out experiment tool. It
turns one caller-supplied printed-page raster into one or more scan-sized
pages containing torn, rotated, separated scraps.

It is deliberately not part of generation or reception. It has no format
knowledge, tile knowledge, corpus, manifest, printer/scanner registry, or
sidecar. It does not invoke Ghostscript, `color_distort`, or the receiver.

## Contract

- Input is one single-frame uint8 grayscale or RGB TIFF.
- The TIFF must declare one square pixels-per-inch resolution.
- Output has the same pixel dimensions, sample mode, and DPI as the input.
- `--pages A` emits exactly `A` independent scan pages.
- `--scraps B` places exactly `B` independently planned scraps on each page.
- Rotated scrap bounds retain a one-millimetre gap; paper never overlaps.
- Existing output files are never overwritten.
- One seed reproduces the same source crops, contours, rotations, placement,
  shadows, creases, and folded-back flaps.

With one page, the output path is used literally. Multiple pages insert
numbered suffixes:

```text
scan.tiff, --pages 1  -> scan.tiff
scan.tiff, --pages 3  -> scan-001.tiff
                         scan-002.tiff
                         scan-003.tiff
```

Large inputs and outputs are disk-backed. The renderer samples one bounded
row stripe at a time; a 4800-dpi scan page is not materialized in heap memory.
Outputs are uncompressed TIFFs so that they remain directly memory-mappable.

## Use

```console
PYTHONPATH=src env/bin/python -m holo.qualification.scrap_scan \
  INPUT.tiff OUTPUT.tiff \
  --pages 3 --scraps 14 --seed 20260727
```

The defaults were chosen after inspecting the E018/E021 physical confetti:
they mix strips, quadrilaterals, pulled-corner triangular pieces, rough torn
edges, arbitrary rotations, paper shadows, creases, and occasional
pale folded-back regions. The scans are examples for geometric scale and
shape only; no scratch image is installed as production data and the defaults
are not a hardware profile.

Explicit controls are intentionally few:

```console
--size-mm MIN MAX          scrap long-edge range
--tear-mm MM               typical contour displacement
--fold-probability P       probability of a crease
--flap-probability P       probability that a crease folds paper back
--shadow-strength P        paper-shadow opacity
```

Every scrap selects an independent rectangular area of the source page
behind its irregular paper mask. The tool does not promise complete source
coverage; missing payload, repeated source areas across output pages, and
blank source margins are useful receiver conditions. If the requested count
and size range cannot fit without overlap, generation refuses and asks the
caller to reduce `--scraps` or `--size-mm`.

## Relation to printer/scanner distortion

`scrap_scan` owns only physical-fragment layout. `color_distort` owns raster
degradation and sampling. Neither silently invokes the other.

For convenient receiver material, either compose an already transformed TIFF
at its scan DPI:

```console
PYTHONPATH=src env/bin/python -m holo.qualification.color_distort \
  perfect-r600.tiff full-r1200.tiff \
  --profile nominal --seed 41 --output-dpi 1200

PYTHONPATH=src env/bin/python -m holo.qualification.scrap_scan \
  full-r1200.tiff scraps-r1200.tiff \
  --pages 2 --scraps 14 --seed 42
```

or compose at 600 dpi and transform the resulting page afterward. These are
synthetic pipeline choices, not claims of exact physical process ordering.
The tools stay separate so experiments can make that choice explicitly.
