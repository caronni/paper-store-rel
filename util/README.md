# Standalone scrap packing

`scrap_pack.py` is a local, standalone utility for extracting payload-textured
scraps from one scan, reviewing the result, and writing a compact lossless
raster. It imports no `paperholo`, `holo`, or experiment code.

## Install and run

Install the repository requirements into a virtual environment, then run:

```bash
env/bin/python util/scrap_pack.py INPUT.tiff --cell-px 24
env/bin/python util/scrap_pack.py INPUT.png --cell-px 8 -o packed.png
```

The tool prints and normally opens a loopback-only review page. The page shows
all expanded extraction boxes and offers only **Approve and export** or
**Cancel**. Nothing is written before approval. `--no-open` prints the URL
without launching a browser; `--force` permits replacement of an existing
output after approval.

## Detector scale

`--cell-px` is the nominal payload-cell pitch in input pixels, not image DPI.
For a known architecture and scan resolution:

```text
cell_px = scan_dpi * c / 600
```

| Input | `--cell-px` |
|---|---:|
| c3 at 4800 dpi | 24 (default) |
| c2 at 4800 dpi | 16 |
| c3 at 1600 dpi | 8 |
| c3 at 1200 dpi | 6 |
| c2 at 1200 dpi | 4 |

The default is therefore specific to c3 at 4800 dpi. Arbitrary images often
do not carry enough provenance to infer the right value.

The detector is deliberately coarse and texture-based. Each connected
component becomes one native-pixel rectangle, expanded by
`--margin-cells` (four cells by default). This absorbs internal texture holes
and supplies the implicit margin. `--min-blocks` controls the smallest coarse
component retained. Text, rules, calibration targets, and other two-axis
texture can trigger candidates, so approval is load-bearing rather than
ceremonial.

## Input and output contract

- One single-image TIFF or PNG.
- Unsigned 8- or 16-bit gray, RGB, or RGBA samples.
- TIFF must use MINISBLACK or RGB photometric semantics and top-left
  orientation. TIFF alpha must be unassociated. CMYK/Separated, YCbCr,
  MINISWHITE, associated-alpha, and other TIFF interpretations are rejected
  instead of being silently rewritten. Normalize them explicitly to RGB first.
- RGBA is composited over white for detection and review; the original four
  channels and samples are retained in the packed output.
- Crops may be translated and rotated by 90 degrees. They are never resampled.
  Sample values, integer depth, and channel count are preserved exactly.
- Expanded source rectangles can overlap, in which case their shared pixels
  intentionally appear in both packed crops. Margins at source edges clip to
  the available raster.
- The packer searches several deterministic rectangle layouts. It produces a
  compact layout, not a mathematical proof of the globally smallest canvas.
- PNG output tries several maximum-level lossless strategies. TIFF output
  tries zstd/deflate with and without a reversible predictor. “Smallest” means
  the smallest verified candidate tried inside the selected output container;
  PNG and TIFF are not compared against each other.
- DPI, ICC profiles, gamma, EXIF, orientation, and other ancillary metadata are
  not carried into the packed file. The raster samples are the preserved
  artifact.

## Corpus overview helper

`scrap_pack_overviews.py` runs the same loader, detector, and packer over a
tree and writes a mirrored review corpus:

```bash
env/bin/python util/scrap_pack_overviews.py \
  --root /path/to/paper \
  --output scratch/scrap-pack-all-overviews
```

It creates one `*.overview.png` per source plus `index.html`, `inputs.txt`,
`manifest.csv`, and a detailed resumable `manifest.jsonl`. Each PNG shows the
boxed source beside a bounded sample of the proposed packing geometry.

**The helper never writes a native packed target.** Its right pane is only a
memory-safe preview, even when the source TIFF is several gigabytes. Generate
an actual target with `scrap_pack.py` and approve it. Overview trees belong
under ignored `scratch/` and are disposable.

Pitch inference in the helper is conservative: an explicit `Nppc` path token
wins; otherwise an unambiguous c2/c3 token plus path or image DPI is used; all
other files get the standalone default 24 and record that provenance. By
default administrative trees are skipped. `--include-admin` includes virtual
environments, caches, and `.claude/worktrees`; `.git` and the output tree are
always excluded.

## Verification

```bash
env/bin/pytest -q tests/test_scrap_pack.py tests/test_scrap_pack_overviews.py
```

The tests cover 8/16-bit gray, RGB, and RGBA behavior; TIFF semantic rejection;
alpha-aware detection; cell-scaled margins; exact rotated composition;
lossless PNG/TIFF round trips; bounded previews; approval cancellation; pitch
inference; exhaustive discovery boundaries; and explicit CMYK overview status.
