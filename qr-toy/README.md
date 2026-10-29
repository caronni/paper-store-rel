# Single-frame LDPC toy

## What we are exploring

Can one of our printed LDPC frames serve as a small, self-contained data patch
that we can photograph and recover? This throwaway experiment takes the
existing K (black ink) tile, enlarges it to roughly 4 × 4 cm, and carries one
arbitrary 263-byte payload directly. It isolates the optical acquisition and
inner-code recovery problem from multi-page storage and fountain recovery.

Counting bytes (`00..ff,00..06`) make the demonstration easy to reproduce;
they are ordinary input, not a special encoding or a decoder hint. A standard
QR code carrying those same bytes provides a visual comparison of the geometry
and the overhead of its visible finder, timing and alignment patterns.
The QR side is illustration only; this folder does not implement QR decoding.

The practical questions are whether we can find the patch from its 103 known
cells, correct its photographed geometry, and recover all 263 bytes with a
valid LDPC syndrome and CRC. Pose bounds and optical corrections are exposed
so we can investigate failures with stepwise output and saved images.

**Implemented:** the 263-byte r0547 generator/decoder, a matching QR-H
illustration, and a separate r0775 FEC channel study. The later **3 × 3
r0775 layout with eight data tiles and one XOR tile is a proposal**, not a
mode implemented by these commands. It would also need a defined metadata
contract; see [RESILIENCE.md](RESILIENCE.md).

## Files and setup

| File | Role |
| --- | --- |
| `generate.py` | Emit a single direct-data LDPC tile as PS and PNG. |
| `decode.py` | Run image acquisition through certified tile-payload recovery. |
| `acquire.py` | Toy boundary detection, known-cell pose search and optical sampling. |
| `common.py` | Fix the format, dimensions, payload length and reference cells. |
| `compare.py` | Place a real QR-H encoding beside the LDPC tile at equal cell pitch. |
| `resilience.py` | Compare r0775 FEC simulations with exact v40-L RS channel calculations. |
| `test_qr_toy_*.py` | Synthetic round trips, failure paths, comparison and FEC study checks. |
| `records/` | Committed measurement records; generated rasters remain local. |
| `build/` | Ignored generated artifacts, decode records and optional QR dependency. |

Use the repository Python environment with its normal dependencies installed
(`numpy`, `scipy`, `Pillow`, and the existing codec dependencies). These scripts
locate `src/` themselves, so no separate package installation or `PYTHONPATH`
setting is needed. Only the comparison requires the optional `qrcode` library;
its installation command is below. Ghostscript is optional and is used to
check the emitted PS against the PNG in the test suite.
In the review environment `env/bin/python` is CPython 3.14.7 with the GIL
disabled; the commands below use that available environment.

## Generate and decode

Two command-line harnesses, run from the repository root using its environment:

```sh
env/bin/python qr-toy/generate.py --counting --out qr-toy/build/counting-new
env/bin/python qr-toy/decode.py qr-toy/build/counting-new/patch.png --out qr-toy/build/read-new

# An arbitrary file of exactly 263 bytes; counting is only a convenience.
env/bin/python qr-toy/generate.py input.bin --out qr-toy/build/arbitrary
env/bin/python qr-toy/decode.py photo.jpg --out qr-toy/build/photo-read
```

Use a fresh output directory for each invocation. `generate.py` emits `tile.ps`
and `tile.png` (centered on A4), `patch.png` (cropped with a four-cell white
border), `payload.bin`, and a provenance manifest. It does not send a print job.
Print the PS at actual size: the active tile is **40.64 × 40.64 mm**, 64 × 64
cells at 0.635 mm/cell, or 15 printer dots/cell at 600 dpi. The bordered patch
is 45.72 mm square. PNGs carry 600 dpi metadata; viewer/printer scaling can
override that metadata.

## Frame interpretation

Fixed format `1i40-k-r0547-p103-v1@1x1`; page 0, tile (0,0), supplied out of
band. `c15` is not a registered pitch alias. The mother LDPC code is (4096,
2240); shortening removes 103 information positions. The remaining 2137 bits
contain CRC32, one existing metadata bit, and **2104 payload bits = 263 bytes**.
The generator uses the existing composer with version 0 and K=1 solely to
supply that metadata bit. There is no fountain encoding, volume envelope,
file name, or variable-length framing. The decoder discards the metadata bit.
These are toy direct-data bytes, not an ordinary volume for the production CLI.

For this fixed address, all 103 reserved cells have known values: 100 address
word cells plus three filler cells. The acquisition search uses those values;
it does not decode/discover an arbitrary page address. Neither counting bytes
nor generator manifests are input to acquisition or decoding.

## Decoder steps and controls

1. Apply EXIF orientation, downsample to at most 1800 pixels on the long side,
   convert to grayscale. Camera EXIF DPI is ignored.
2. Optionally correct radial distortion and normalize illumination, then find
   ink components and estimate quadrilaterals from their outer edges.
3. Rectify each candidate onto a known sampling grid and run the existing
   production survey/segmenter. Save its input image and log its regions/pitch
   vote. **The survey is diagnostic in this toy:** its output does not seed
   placement or gate the subsequent search; zero regions explicitly logs a
   toy fallback. This is not the complete production receiver engine.
4. Search the 103 known cells over four rotations, reflection, translation,
   and scale, then refine all four corners. A homography corrects perspective.
5. Sample cell interiors with three aperture choices. Use production PAVA
   photometric calibration to obtain soft evidence, excluding unobserved known
   cells from calibration. Then run production tile descrambling, LDPC and
   CRC32 validation. The first stage allows 60 iterations per algorithm; a
   failed attempt gets the 150-iteration retry stage. Each stage may run
   min-sum followed by the existing sum-product fallback.
6. Only a certified frame writes `recovered.bin`. Report the SHA256, metadata
   bit, and hard cell disagreements against a re-encoding of the certified bits.

Each step prints elapsed time and writes `events.jsonl`; `report.json` records
settings, input hash, attempts, outcome, and the selected quadrilateral in
working-image coordinates. Each LDPC attempt records its pose and sampling
aperture. Candidate rectifications, `pose.png`, and
`sampled-cells.png` make geometry reviewable. Decoder exit codes: 0 certified,
2 failure, 3 certified but the optional expected-file comparison failed or
its input could not be read.

Useful experimental controls:

```sh
env/bin/python qr-toy/decode.py photo.jpg --out qr-toy/build/wider \
  --pose-radius 6 --max-side 2400 --flatten-lighting
```

`--pose-radius` (default 3, range 0.5–12) is the coarse translation radius in
cells and the corner-refinement bound around each selected seed. Scale seeds
are 0.96, 1, and 1.04. `--max-candidates` defaults to 3.
`--max-known-errors` defaults to 20/103: an experimental admission threshold,
not a qualified false-accept bound. Wider searches can still get trapped in
local minima. `--radial-k1` applies an explicitly supplied centered radial
pullback before segmentation, with source radius = output radius ×
(1 + k1 × normalized radius²); normalization radius is half the longest image
dimension. It does not estimate camera lens parameters.
Keep the complete tile inside the corrected image: the radial pullback fills
areas outside its source image with white and does not propagate a separate
source-validity mask. Edge-clipped captures using that correction are not
qualified by the current checks.

`--verify expected.bin` reads that file **only after** successful payload
recovery. A mismatch retains the certified bytes and returns 3. The production
calibrator's photometric held-out loss is logged, but those sites already
participated in pose fitting, so it is not independent acquisition validation.
CRC32 is an integrity check, not authentication.

## Validation and scope

```sh
env/bin/python -m pytest qr-toy -n 0 -q
```

Tests cover arbitrary data on a complete A4 raster; synthetic perspective,
rotation, blur, shading and noise; reflection plus 80 flipped unknown cells;
blank/random rejection; length checks; post-decode comparison independence;
and the PS/PNG binary ink-mask agreement at 600 dpi when Ghostscript is present.

This is a complete-tile experiment on a reasonably uncluttered background.
Strong lens distortion, curved paper, glare, occlusion, busy scenes and small
tiles are not qualified. Synthetic checks are not phone/printer qualification.
Core format and receiver code remain unchanged.

[Pre-commit review](REVIEW.md) records the fixes, final checks and the
pre-existing failures in the wider repository suite.

The initial eight harness checks passed, including the case combining
reflection, perspective, blur, shading, noise and 80 deliberately flipped
unknown cells. That is a synthetic example, not a measured correction limit.

Three photographs of the comparison **displayed on a monitor** also recovered
all 263 bytes at default settings. The most difficult example had 53 hard-cell
disagreements and required one LDPC iteration. These are successful individual
examples of display-to-camera recovery, not print-to-camera qualification or
a measured success rate. [Photo record](PHOTO-RUNS.md) preserves the input hashes,
original run metrics and commands. The three photographs are committed as
`photo-*-crop-q50.jpg` (2026-10-12): cropped to the comparison, everything around it
blacked out, metadata removed, re-encoded at JPEG quality 50; they decode to the
same payload (numbers in the photo record).

For a physical experiment, keep the complete patch and surrounding white
space visible, retain the original camera or scanner file, and decode it into
a fresh output directory. Start with defaults, inspect `pose.png`, candidate
rectifications and the step log, then change one setting per follow-up run.
Record printer identity, print scaling, capture device/settings, lighting,
distance and angle alongside the input and output hashes. Those physical
conditions cannot be inferred from the decoder's report. The next useful
evidence is repeated capture under recorded conditions, including real prints.

## Side-by-side QR illustration

```sh
env/bin/python -m pip install --target qr-toy/build/python-deps -r qr-toy/requirements-illustration.txt
env/bin/python qr-toy/compare.py --out qr-toy/build/comparison-new
```

The default uses the same 263 counting bytes for both codes. `--payload file`
accepts any 263-byte file. Python's `qrcode` library emits a standard QR in
explicit byte mode with level H correction: version 17, 85 modules across.
At the same 0.635 mm pitch, its active area is 53.975 mm square (59.055 mm
including the required four-module quiet zone), alongside our 40.64 mm tile.
Outputs include labeled `comparison.png`, A4 `comparison.ps`, standalone
`qr.png`, dimensions/provenance in `comparison.json`, and the LDPC artifacts.
The sizes compare geometry at equal pitch, not equal error correction capacity.

Existing counting-demo artifacts, when present in this checkout:

- [LDPC print sheet](build/counting/tile.ps) and [bordered patch](build/counting/patch.png).
- [Successful counting decode report](build/counting-decoded/report.json).
- [Side-by-side image](build/comparison/comparison.png) and [A4 print sheet](build/comparison/comparison.ps).

These `build/` files are not tracked; use the commands above to regenerate
them under fresh names. Print the comparison PS at actual size / 100% to
preserve the labeled dimensions. PNG display size on screen is viewer-dependent.

For the separate 2,953-byte comparison using r0775-p100 and a hypothetical
two-symbol fountain reserve, see [RESILIENCE.md](RESILIENCE.md). It includes
physical sizes and controlled noise/erasure calculations. The generator and
photo decoder above still use the original 263-byte r0547 toy contract.
