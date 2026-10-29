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
  --output build/scrap-pack-overviews
```

It creates one `*.overview.png` per source plus `index.html`, `inputs.txt`,
`manifest.csv`, and a detailed resumable `manifest.jsonl`. Each PNG shows the
boxed source beside a bounded sample of the proposed packing geometry.

**The helper never writes a native packed target.** Its right pane is only a
memory-safe preview, even when the source TIFF is several gigabytes. Generate
an actual target with `scrap_pack.py` and approve it. Overview trees belong
under the ignored `build/` and are disposable.

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

## Ground truth from a print job

`ps_gt.py` recovers a holo page's ground truth from its PostScript alone: the
K `imagemask` rows and the 1-bit DeviceCMYK image carry the dots verbatim, so
the packed array `holo.gen.emit` saves beside a page (`pageNNN_gt.npy`) is a
re-parse, not a render. It imports nothing from `holo`.

```bash
env/bin/python util/ps_gt.py page000.ps --list
env/bin/python util/ps_gt.py page000.ps --out page000_gt.npy --expect-sha256 <manifest gt_sha256>
```

`--out` needs exactly one bitmap on the page and refuses a CMYK page with any
K sample; `--expect-sha256` refuses to write unless the array matches the
manifest. `measure/evidence_regen` uses the parser to check every archived GT
array (holo and paperholo) against its job; `util/tests/test_ps_gt.py` pins it
on a 10x10 K and colour emission.

## Evidence-archive packer

`util/evidence_pack/` builds the published evidence archive of
`docs/EVIDENCE-ARCHIVE-2026-10-08.md` (§3 tree, §4 manifest, §5 compression,
§7 privacy, §11 brief). Standalone like the scrap packer: no `holo` or
`paperholo` imports; it needs `cjxl`/`djxl` (libjxl), `jpegtran` and
`jxl-oxide` on PATH.

THREE PLACES, nothing else (owner's rule, 2026-10-09: "public evidence,
committed github code, trash"):

| what | where |
|---|---|
| the two torrent roots, exactly what goes to B2 and into the torrents | `evidence/paper-store-evidence-paperholo-era/` (001–026), `evidence/paper-store-evidence-holo-2026-10/` (027–042) |
| the packer, its tests, this README | committed under `util/` |
| the review directory: hard links, renders, `redactions.json`, drafts, `REVIEW.md`, `INDEX-draft.tsv`, `.scrub.diff` sidecars, `MANIFEST-local-<release>.tsv`, `RELEASE-TREE-<release>.md`, `pack-written-<release>.txt`, encoder work files | `build/evidence-review/` (trash once the archive is published) |

A release root holds exactly the files its `MANIFEST.tsv` places on disk:
captures (`.jxl`, or raw where the TIFF rule refuses JPEG XL), `headers/`,
jobs, emission, one bundle per experiment holding its records, reports and
figures, `MANIFEST.tsv`, `MANIFEST.sha256`, `README.md`, `INDEX.tsv`,
`tools/unpack.sh` and `LICENSE`. `evidence/` holds
the two release roots and nothing else; `pack` starts from an empty
`evidence/` (it refuses any other entry there, and a release root that already
exists unless `--fresh`).

The release-time run, from the repository root:

```bash
# 1. the review directory (hard links + renders + drafts; ~9 min fresh,
#    ~2 min when the renders exist); redactions.json is created only if missing
env/bin/python -m util.evidence_pack arrange --mode review \
    --repo . --tables docs/evidence-archive \
    --hashes scratch/evidence-prep/hashes-retained.tsv --out build/evidence-review/
# 2a. the DRY stage, for the owner's review of the tree as it will ship (≈ 3 min
#     on machine 1, 5 GB peak: no capture is encoded, the 26 bundles are, xz -9e,
#     8 at a time); then read build/evidence-review/RELEASE-TREE-*.md
env/bin/python -m util.evidence_pack pack --dry --only ALL \
    --repo . --tables docs/evidence-archive \
    --hashes scratch/evidence-prep/hashes-retained.tsv \
    --out evidence/ --review-dir build/evidence-review/ \
    --licence-file docs/evidence-archive/LICENSE
# 2b. the torrent roots (≈ 7 h for ALL), on the owner's go after that review;
#     --fresh replaces the dry tree. Reads the tables, the sources and
#     build/evidence-review/redactions.json, nothing else of the review directory
env/bin/python -m util.evidence_pack pack --fresh --only ALL \
    --repo . --tables docs/evidence-archive \
    --hashes scratch/evidence-prep/hashes-retained.tsv \
    --out evidence/ --review-dir build/evidence-review/ \
    --licence-file docs/evidence-archive/LICENSE
# 3. the gate
env/bin/python -m util.evidence_pack verify --out evidence/
# consumer side
env/bin/python -m util.evidence_pack unpack X.tiff.jxl --header headers/X.tiffhdr -o X.tiff
```

- `arrange --mode review --out DIR` writes the review directory (never
  `evidence/`, never a packed root): `DIR/<release>/` with captures as HARD
  LINKS to the originals (editing one edits the original),
  `<capture>.review.png` (four 8 mm edge strips at ~150 dpi over a ~1600 px
  full-page view, block-averaged from a memmap), red 50 % boxes and
  `<capture>.review-redaction.png` (1:1) for every box in `DIR/redactions.json`
  (seeded once with the eleven boxes the owner approved 2026-10-09,
  `arrange.KNOWN_REDACTIONS`; that file is the authority — edit it, re-run),
  scrubbed text records with `<file>.scrub.diff`, byte copies of jobs, payloads
  and figures, `MANIFEST-draft.tsv`, `REVIEW.md` (counts, renames, redactions,
  scrub substitutions, published names that hit the scrub set, coverage) and
  `DIR/INDEX-draft.tsv`. Sources are never written. arrange does not prune a
  file whose row left the tables: a fresh `DIR` gives an exact review.
- `pack --only DIR… | ALL` re-derives everything from the tables at run time
  (`rename_map.tsv`, `figures_shortlist.tsv`, `record_*.tsv`,
  `hashes-retained.tsv`) and refuses before writing anything when a planned
  file cannot be placed, a redaction key matches no published source, a
  `KNOWN_REDACTIONS` capture has no box, or a published name or manifest cell
  hits the scrub set (a path is never scrubbed: rename it in `rename_map.tsv`).
  Lossless JPEG XL e7 for every TIFF that is one uncompressed contiguous 8-bit
  strip at the end of a single-IFD file (else raw), `headers/<capture>.tiffhdr`,
  white-outs from `--review-dir`'s `redactions.json` (`redacted-jxl-e7`, no raw
  sha published), PNG eXIf/iTXt/tEXt/zTXt strip, scrub, the manifests, README,
  INDEX, `tools/unpack.sh`, and `LICENSE` copied byte for byte from
  `--licence-file` (its first line `MIT License` names it: README and the
  MANIFEST.tsv header say "MIT, see LICENSE"). `--fresh` removes exactly the
  files a previous pack wrote (its MANIFEST.tsv, or the review directory's
  `pack-written-<release>.txt` of a run that died before its manifest) and
  refuses when anything else is in the root. Every run writes
  `RELEASE-TREE-<release>.md` into the review directory: the release root as a
  tree, each file's published bytes, directory subtotals, totals equal to the
  MANIFEST.tsv rows.
- BUNDLES (the owner's ruling of 2026-10-09: "there is a lot of clutter in the
  tree"; `util/evidence_pack/bundle.py`): every file whose first role directory
  under its experiment directory is `records/`, `reports/` or `figures/`, at
  any depth (per-sheet ones included), ships as a member of ONE archive per
  experiment directory, `<NNN-…>/records-<NNN-…>.tar.xz`, its member path
  relative to the experiment directory (`tar -xJf records-<NNN-…>.tar.xz`
  inside it restores exactly the manifest's paths). Each member is first
  written exactly as it would be published alone (scrubbed, chunk-stripped,
  cropped) into `<review-dir>/pack-work/bundles/` (removed after), then tarred:
  GNU format (pinned), regular-file members only, sorted, mtime 0, uid/gid 0,
  no owner names, mode 0644, no pax headers, one xz stream from Python's lzma
  at preset 9 | PRESET_EXTREME (`xz -9e`) — the same inputs give the same
  bytes. MANIFEST.tsv keeps one row per member (`published_path` = the
  extracted path, its own bytes, sha and codec, and the new `bundle` column
  naming the archive) and one row for the archive (codec `tar-xz`, `bundle`
  empty, `raw_bytes` / `sha256_raw` = the uncompressed tar); `MANIFEST.sha256`
  lists the archive and its members, so `sha256sum -c --ignore-missing
  MANIFEST.sha256` (Linux; `shasum -a 256 -c --ignore-missing` on macOS)
  passes before and after extraction. INDEX.tsv and the README table count
  members as files of their directory, the archives in a `bundles` column, and
  the bytes on disk; the release README explains bundles and carries an
  "Integrity" section with those two one-liners. Captures, `headers/`, `jobs/`,
  `emission/` and every top-level file stay as files; pack refuses a capture
  planned under records/, reports/ or figures/. `RELEASE-TREE-<release>.md`
  shows a bundle as one line with its bytes and its members indented under it
  (read from the archive) with their own bytes in parentheses; its totals add
  `bundles`, `bundle members`, `bundle member bytes` and `files after
  extracting every bundle`. `arrange --mode review` is unbundled and its
  MANIFEST-draft.tsv has no `bundle` column.
- `pack --dry` (the owner's hold of 2026-10-09: "hold the pack until i have
  re-reviewed the 'tree-for-release' version") writes the same release roots
  without the capture encode: jobs, emission, records (scrubbed), figures
  (chunks stripped), the bundles, `headers/<capture>.tiffhdr`, LICENSE, README,
  INDEX and `tools/` for real, and every capture as a ZERO-BYTE placeholder
  under its published name (`X.tiff.jxl` where the TIFF rule admits JPEG XL,
  redacted ones included; `X.tiff` / `X.png` where it publishes as is). Its
  MANIFEST.tsv rows are complete but for a capture's `published_bytes`,
  `sha256_published` and `sha256_pixels`; MANIFEST.tsv, README.md and INDEX.tsv
  carry `stage: dry (captures are placeholders; not a release)` at the top
  (INDEX and the README table then count expected bytes); no `MANIFEST.sha256`
  is written. In `RELEASE-TREE-<release>.md` a placeholder shows its source
  bytes and the bytes expected at the measured raw-TIFF-to-JPEG-XL ratios
  (`util/evidence_pack/tree.py` `JXL_RATIOS`: colour 4800 2.37, colour 2400
  2.16, grey 1200 1.66, grey 2400/4800 2.5; a colour or grey dpi without a
  measurement takes the nearest measured dpi's ratio and says so; every other
  codec 1.0). `verify` refuses a dry tree; `pack` refuses it like any existing
  root; `pack --fresh` removes exactly what the dry run wrote (its
  MANIFEST.tsv, or its `pack-written-<release>.txt`) and packs for real.
- The manifest's cross-row columns come from the tables only, empty where
  none states a value (`util/evidence_pack/describe.py`): `format_ref` = the
  `seed` of the sheet's emission `manifest.json` (its own directory, a
  `job = NNN/<dir>/jobs` record name, or the experiment's sheet of the same
  name; empty for every paperholo-era sheet); `print_copy` from a `copyN` /
  `printN` directory or capture name; `derived_from` for a derivative "PNG of
  the TIF"; `same_platen_as` from a record note "same platen as <take>";
  scanner, dpi and mode from the capture name; engine, route, month and role
  from the record tables.
- The encoder sees a PNM: an APFS clone (`cp -c`) of the TIFF whose header
  bytes are overwritten by a same-length PNM header padded with a comment, so
  `cjxl --streaming_input` streams without copying a pixel (the clone lives in
  the review directory, on the same volume as the sources). libjxl 0.12.0's
  streaming PNM reader refuses a named pipe (it needs a seekable file); the
  FIFO route is the fallback and runs without `--streaming_input` (whole image
  in RAM). Both give the same codestream (pinned in
  `util/tests/test_evidence_pack.py`).
- `verify --out evidence/` refuses a dry tree (it still reports strays, checks
  the bundles and greps with the scrub set there, ≈ 4 min on the full tree; no
  capture is decoded, no other file hashed), and fails on any entry of
  `evidence/` that is not a release root, any file, directory or symlink under
  a release root that its MANIFEST.tsv does not place on disk (a stray file is
  a leak path; a loose file under an experiment's `records/`, `reports/` or
  `figures/` is always a stray, extracted bundle members included), a missing
  fixed file or licence notice, any bundle that does not hold exactly the
  members whose rows name it (streamed through tarfile over lzma, never
  extracted: each a regular file at a plain relative path under those three
  directories, nothing escaping the experiment directory, canonical header,
  bytes and sha as its row; the archive's own sha and the uncompressed tar's
  `sha256_raw` / `raw_bytes`), any capture whose header + djxl pixels miss
  `sha256_raw` (`sha256_pixels` + `sha256_published` for a redacted one, which
  must publish no raw sha), any JXL whose jxl-oxide decode differs (a missing
  jxl-oxide fails unless `--no-oxide`; it is read as a float32 numpy array on
  its stdout, hashed as 8-bit samples, because jxl-oxide 0.12's PNG writer
  refuses more than 2**32 bytes of pixels — the 2026-10-10 crash on the first
  4800 dpi RGB capture), any decoder failure of either decoder (a failure line
  for that file, the run goes on), any sha that disagrees with the
  manifest or `MANIFEST.sha256` (which must list every bundle member under its
  extracted path), and any scrub-set hit in a text file, PNG chunk or TIFF
  header sidecar, bundle members included. A Finder `.DS_Store` is a stray.