# Initial display-to-camera recoveries

The user supplied three original JPEGs of the comparison image displayed on
a monitor. All were 3072 × 4080 pixels and decoded with the default settings
at working resolution 1355 × 1800. No lighting flattening or radial correction
was requested. These are display-to-camera observations, not printer tests.

The table records the original runs, before the code-review fixes. Wall times
are from those runs and are not performance thresholds.

| Input JPEG | Known-cell errors at pose | Hard-cell disagreements after certification | LDPC iterations | Original wall time |
| --- | ---: | ---: | ---: | ---: |
| `photo-2026-09-08-a.jpg` | 0/103 | 0/4096 | 0 | 1.53 s |
| `photo-2026-09-08-b.jpg` | 0/103 | 0/4096 | 0 | 1.80 s |
| `photo-2026-09-08-c.jpg` | 1/103 | 53/4096 | 1 | 1.81 s |

Each run certified exactly 263 bytes with payload SHA256
`53b36d69b0619f1b3e7c81c760e3b65ea872047977b7e13f58e921ab01d7ba59`,
matching the counting input. The production survey reported zero regions for
the winning candidate in the first two images; the toy known-cell search
still recovered the pose. In the third image it reported 12 regions and the
1/40 pitch vote for the winning candidate.

Hard-cell disagreements compare a brightness threshold with the certified
frame re-encoding. They are not the number of LDPC decisions changed; the
decoder uses calibrated soft evidence. The third image contains visible
screen moiré, but this record does not identify a unique cause for each error.

With the original JPEGs present in `qr-toy/` (under the generic names this record uses since 2026-10-27), replay into fresh directories:

```sh
env/bin/python qr-toy/decode.py qr-toy/photo-2026-09-08-a.jpg --out qr-toy/build/replay-222241
env/bin/python qr-toy/decode.py qr-toy/photo-2026-09-08-b.jpg --out qr-toy/build/replay-222316
env/bin/python qr-toy/decode.py qr-toy/photo-2026-09-08-c.jpg --out qr-toy/build/replay-224206
```

[Machine-readable record](records/photo-runs.json) retains the input hashes,
settings, selected pose, decoder attempts and outcomes. Original JPEGs and
generated diagnostic PNGs remain local, following the repository's separation
of generated/capture artifacts from source and measurement records. No capture
distance, display scaling or printer characteristics should be inferred from
the nominal 40.64 mm print dimensions.

## 2026-10-12 — the committed copies

The three original JPEGs are no longer kept here. Committed instead are copies
cropped to the white comparison frame (the panel on the monitor, the card in
the third photo), with everything outside the frame's outline blacked out,
all metadata removed (no EXIF, GPS or XMP; the embedded colour profile, which named the camera's maker, was dropped losslessly on 2026-10-27, and the hashes below are of the files as committed since; replayed on them the same day: the three rows reproduce exactly), and
re-encoded at JPEG quality 50 with 4:2:0 chroma (5.0 MB → 2.1 MB for the three).
The table above and `records/photo-runs.json` describe the uncropped originals;
on 2026-10-12 replays of those originals with the current code reproduced the
table (0/103 and 0/4096, 0/103 and 0/4096, 1/103 and 53/4096).

| Committed JPEG | sha256 | Known-cell errors at pose | Hard-cell disagreements after certification | LDPC iterations |
| --- | --- | ---: | ---: | ---: |
| `photo-2026-09-08-a-crop-q50.jpg` | `f7d41cc2bca9bd10af9f5090e7ce81fbc1c1e1c7c6b6db0cdfc6cc9cd173d814` | 0/103 | 0/4096 | 0 |
| `photo-2026-09-08-b-crop-q50.jpg` | `1acd045371133715eeaa83a9497a42f9f2ca958b721e2811c75064000b0aeff4` | 0/103 | 2/4096 | 0 |
| `photo-2026-09-08-c-crop-q50.jpg` | `cc2408c25953ccc2db1a843810a68dcb1b2ea5086f02d0e33c462a34fc56dd63` | 0/103 | 122/4096 | 1 |

Each certified exactly 263 bytes with payload SHA256 `53b36d69…` as above.
The differences from the original table come mostly from the crop, not the
compression: without the surrounding screen the search settles on a different
pose candidate, and the crops at JPEG quality 95 gave 0, 2 and 108 hard-cell
disagreements; quality 75, 60 and 50 then moved only the third photo's count
(110, 118, 122). Hard-cell disagreements remain a brightness-threshold
diagnostic, not decoder decisions.

```sh
env/bin/python qr-toy/decode.py qr-toy/photo-2026-09-08-a-crop-q50.jpg --out qr-toy/build/replay-222241-q50
env/bin/python qr-toy/decode.py qr-toy/photo-2026-09-08-b-crop-q50.jpg --out qr-toy/build/replay-222316-q50
env/bin/python qr-toy/decode.py qr-toy/photo-2026-09-08-c-crop-q50.jpg --out qr-toy/build/replay-224206-q50
```
