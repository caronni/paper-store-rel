# paper-store: setup, first run, usage

The manual behind the front page (`README.md`): what to install, how to read a format
id, the first run on a published scan, generating and decoding your own sheet, the test
lanes, the document map, the evidence releases, and the note on references. Every
command here was run on this tree. The measured results, with the failures, are in
`RECORD.md`.

## Status

- The receiver, holo3 (`confetti3.py decode`), is **PROVISIONAL**; every run says so.
- Every physical result below is **one printed sheet**. There is no success rate over
  repeated prints and no promotion of any LDPC code rate ("rung"), margin or receiver setting.
- The format is pre-freeze, identity v1; colour rows are provisional (`docs/HOLO-DESIGN.md`).
- The HP M281's colour results before its toner change of 2026-09-13 were made with a weak
  yellow cartridge and are ruled invalid (`experiments/038-sheet-f-m281-fresh-toner.md`).
- Not measured: real shredder output (`docs/PILOTS-DESIGN.md` section 14). No pilot density
  other than the defaults (p100 black, p120 colour) has been printed or qualified on paper
  (`docs/P-AXIS-DESIGN.md`).

## What you need

CPython 3.14, best the free-threaded build (`python3.14t`), which the receiver's workers gain
from, and one virtualenv, `env/`, at the repository
root; do not `pip install -e` anything, the tree runs from `src/` in place. Ghostscript
(`gs`) for generated PostScript and `djxl` (libjxl) for the evidence. Production decodes
want a 64 GB machine, one at a time (`src/holo/receiver/docs/API.md` section 9); the memory
of the small first-run decode below was not recorded. `confetti.py` and `confetti3.py` start
with `#!env/bin/python`, so they run from the repository root, spelled below as
`env/bin/python confetti3.py`.

```sh
python3.14t -m venv env && env/bin/pip install -r requirements.txt
env/bin/python -c "import sys; print(sys._is_gil_enabled())"   # prints False
```

## Reading a format id

`c2-cmy8-r0700@53x37` reads: cell pitch `c2` = 1/300 inch (2 dots of a 600 dpi engine; `c3`
= 1/200, `c4` = 1/150); family `cmy8`, three independent binary planes (`k` is black only,
`cmy` one toner per cell, `cmy7` the three toners coded jointly as one of seven cell
states); LDPC rung `r0700` (k 2880 of n 4096; six rungs, r0547 to r0850); 53 x 37 tiles of
64x64 cells. The grammar is `PITCH-FAMILY[-RUNGS][-pSITES][-vGEN]@TYxTX`; ids starting with
`L:` are legacy fossils that keep old sheets readable (`docs/FORMAT-SPACE.md`). The source
fraction `q` is the share of tiles that carry source data: at 0.5, about any half of the
printed tiles recovers the file. A tile-stream is one tile on one colour plane. A decode
closes once the fountain has K certified tile-streams; a full readout certifies all of them.

## First run: decode a published scan

The evidence releases carry the scans, print jobs and payloads of experiments 001-042, as
packed on 2026-10-10. Experiment 039 generated ten test volumes, sheets A to J, and printed
them on several engines; experiment 040 is the Canon's print and scan of them. A good first
run is e039 sheet A, the smallest: `c4-k-r0700@26x18` (468 tiles, `q` 0.8), a 122,892-byte
counting payload (a deterministic byte pattern), printed on a Canon imageRUNNER ADVANCE and
scanned once in grey at 1200 dpi. Fetch these files of the release
`paper-store-evidence-holo-2026-10` (about 80 MB): select them in your torrent client, or
append `paper-store-evidence-holo-2026-10/` and the path to the webseed URL given in
`docs/evidence-archive/TORRENTS.md`.

```text
MANIFEST.sha256
MANIFEST.tsv
tools/unpack.sh
headers/040-canon-iradv__canon-iradv__A__captures__A-canon-1200grey-aa.tiff.tiffhdr
040-canon-iradv/canon-iradv/A/captures/A-canon-1200grey-aa.tiff.jxl
039-xerox-versalink/set/A/emission/payload-counting.bin
```

The capture is lossless JPEG XL of the pixel block; `tools/unpack.sh` joins it with its
header into the scanner's TIFF byte for byte (run it with `sh`: a download does not keep the
execute bit; 143238878 and `398ee3d6…` are the row's `raw_bytes` and `sha256_raw` in
`MANIFEST.tsv`). With `EV` set to the release directory, from the repository root:

```sh
(cd "$EV" && shasum -a 256 -c --ignore-missing MANIFEST.sha256 &&
 sh tools/unpack.sh 040-canon-iradv/canon-iradv/A/captures/A-canon-1200grey-aa.tiff.jxl \
   headers/040-canon-iradv__canon-iradv__A__captures__A-canon-1200grey-aa.tiff.tiffhdr \
   143238878 040-canon-iradv/canon-iradv/A/captures/A-canon-1200grey-aa.tiff &&
 shasum -a 256 040-canon-iradv/canon-iradv/A/captures/A-canon-1200grey-aa.tiff)  # 398ee3d6…
env/bin/python confetti3.py decode \
  "$EV/040-canon-iradv/canon-iradv/A/captures/A-canon-1200grey-aa.tiff" \
  --dpi 1200 --format c4-k-r0700@26x18 --max-pages 1 --workers 8 \
  --run-dir runs/sheetA --out sheetA.bin
shasum -a 256 sheetA.bin "$EV/039-xerox-versalink/set/A/emission/payload-counting.bin"
```

Expected: `VERIFIED 122892 bytes sha256 930d4d07…`, exit 0 (2 means still open, 1 an
error), and both files hash the same. The record's run closed at 363 certificates against
K 358 in 97 cpu-seconds (`experiments/040-canon-iradv.md`; not re-measured on this release).
The HP M681's print closed from one scan too (`experiments/039-xerox-versalink-candidate-set.md`;
in the release, `039-xerox-versalink/m681/A/captures/`). `--dpi` is the scan's true
resolution, one per scan; `--out` refuses to overwrite; `--run-dir` keeps the state for a
resume (the process id is appended), else it goes to a temporary folder. The full CLI is
`src/holo/receiver/docs/API.md` section 9.

Next steps up, each VERIFIED from one 1200 dpi grey scan: e039 sheet C `c2-k-r0700@53x37`
(532,882 B, Canon, 3,313 cpu-seconds), e039 sheet D `c2-k-r0850@53x37` (657,042 B,
VersaLink). Colour is heavier: the receiver alone closed experiment 033's sheet I from one
2400 dpi scan in 2,005 s wall, 22,335 cpu-seconds on 12 workers, measured 2026-09-21 on an
earlier receiver build, not re-measured on this release
(`src/holo/receiver/docs/LIFECYCLE-MEASURED-2026-09-21.md`).

## Generate and decode your own sheet

Start in software: `scripts/demo.sh` generates a 500-byte volume, renders it with
Ghostscript at 600 dpi, simulates a 1200 dpi scan (`holo.qualification.color_distort`) and
decodes it; it needs a fresh directory each time. `holo.qualification.scrap_scan` cuts a
scan into simulated scraps (`docs/SCRAP-SCAN-TOOL.md`). A simulated success is not a paper
result. Then size the field (the tile area inside the margins), pick a format and `q`:

```sh
scripts/demo.sh build/demo-1                              # the simulated round trip
env/bin/python confetti.py fit --pitch c3                 # A4, 6 mm margins: 35x24 tiles
env/bin/python confetti.py capacity --format c3-k-r0550@35x24 --source-fraction 0.5
env/bin/python confetti.py generate myfile.bin --format c3-k-r0550@35x24 \
  --source-fraction 0.5 -o build/mysheet
env/bin/python confetti.py generate myfile.bin --format c2-cmy8-r0700@53x37 \
  --paper A4-4mm --printer xerox-altalink-c8245 --source-fraction 0.8 -o build/mycolour
```

`c3-k-r0550` at `q` 0.5 matches the `resilient` dial of `confetti.py registry` (listed as
the legacy coding `c3-r0550`), measured with the v1 stack on the HP M281 (e016, e018) and
provisional for holo format v1 (`src/holo/devices/profiles.py`). A c3 black sheet the holo
record read from paper is `c3-k-r0700@35x24` at `q` 0.8 (e039 sheet B, 225,218 B, Canon).
`capacity` prints the largest payload a page holds; `generate` writes one PostScript file
per page plus a ground-truth bitmap. `--printer` (`xerox-altalink-c8245`, `canon-iradv-c257`, `hp-m281`)
selects how colour is asked of that engine, never the geometry.

Printing, as the record did it: send the PostScript unmodified to a 600 dpi engine,
preferably over the raw socket (port 9100; `scripts/print_plane.sh FILE HOST`, after a typed
`yes`), with colour management, halftoning, resolution enhancement and toner save off. Do
not ask the engine for a resolution other than its native grid unless
`docs/PRINTED-FORMAT.md` shows that engine honouring it. Colour pages carry the engine's
yellow tracking dots.

Scanning: the whole sheet with all four paper edges in the frame, grey for black pages and
RGB for colour; auto-crop, geometric correction, sharpening, despeckle and adaptive contrast
off; an uncompressed TIFF at high resolutions (`docs/CHARACTERIZE-HOWTO.md`, which also
covers `confetti.py discover` for a new printer and scanner pair). Submit the scanner's own
file and declare its true dpi; holo3 never guesses it (`src/holo/receiver/cli.py`;
`experiments/039-xerox-versalink-candidate-set.md` section 039.4). The record used 1200 or
2400 dpi for c2 and c3; 600 dpi grey has read c3 black pages (`bootstrap/PAPER-2026-10-26.md`).

When a decode stalls short of K, the analyzer re-reads the tiles holo3 left uncertified,
issues certificates only through the same parity and CRC-32 gate, and hands them back as a
snapshot the receiver resumes from (`RUN` is the `--run-dir` name with its process id):

```sh
PYTHONPATH=src:. env/bin/python -m analyzer ladder --run-dir RUN --out build/pass1
PYTHONPATH=src:. env/bin/python -m analyzer export-facts --snapshot RUN/facts.npz \
  --ledger build/pass1/ledger.jsonl --out build/facts-1.npz
env/bin/python confetti3.py decode SCANS... --dpi ... --format ... \
  --run-dir runs/resume1 --out sheet.bin --resume build/facts-1.npz
```

The resume must name the same scans as the run the snapshot came from. The analyzer is
heavy (a pass on experiment 033's sheet H peaks near 50 GB); run one at a time and never
beside a decode. Manual: `analyzer/README.md` section 2.

## Tests

```sh
env/bin/python -m pytest                                  # default lane, 8 workers
env/bin/python -m pytest src/holo/receiver/tests -q       # receiver fast lane, no decodes
HOLO3_RUN_SLOW_TESTS=1 env/bin/python -m pytest src/holo/receiver/tests -q  # + sim decodes
env/bin/python -m pytest tests --ignore=tests/holo -q     # the paperholo (v1) lane
```

`HOLO_RUN_GS_TESTS=1` adds the Ghostscript gates; the receiver lane calls `git ls-files`.

## Where to look next

- Normative: `docs/HOLO-DESIGN.md`, `docs/FORMAT-SPACE.md`, `docs/PRINTED-FORMAT.md` (what
  toner means); `src/holo/receiver/docs/API.md` and `SCHEDULE.md` (holo3);
  `analyzer/README.md`, `analyzer/DESIGN.md`; `bootstrap/README.md`, `docs/BOOTSTRAP-DESIGN.md`.
- Design background: `docs/PILOTS-DESIGN.md`, `docs/P-AXIS-DESIGN.md`, `docs/FEC-DESIGN.md`,
  `docs/FOUNTAIN-DESIGN.md`, `docs/COLOR-DESIGN.md`, `docs/RUNG-LADDER-STUDY-2026-09-30.md`
  (the shipped LDPC ladder); `docs/LDPC-LADDER-V2.md` is a design whose code is not here.
- The record: `experiments/NNN-*.md`; `docs/EXPERIMENT-LOG.md`, one line per physical run
  since 2026-10-19; `docs/TODO.md`, open threads.
- History: `docs/DESIGN.md` (the v1 spec), `src/paperholo`, `docs/RECEIVE-DESIGN.md` and
  `docs/archive/` (retired receivers), `src/holo/receiver/docs/retirement_docs-2026-09/`.
- A toy, separate from the pipeline: `qr-toy/README.md`.

## Evidence releases

Two torrents, webseed only, MIT. The `.torrent` files, magnets, hashes and the webseed URL
are in `docs/evidence-archive/TORRENTS.md`. Open the `.torrent` files in the client rather
than the magnets: a magnet needs a peer to supply the metadata first, and these torrents have
no tracker. Every file can also be fetched over plain HTTPS from the webseed URL.

| release | experiments | bytes | files |
|---|---|---:|---:|
| `paper-store-evidence-paperholo-era` | 001-026 | 38,186,288,448 | 223 |
| `paper-store-evidence-holo-2026-10` | 027-042 (as of 2026-10-10) | 138,636,254,196 | 536 |

Their READMEs name this repository's tag `release-1-export`. Every paperholo-era decode
driver they name is in this tree (`docs/evidence-archive/REGENERATION-2026-10-22.md`
section 5). Holo-era decodes have not been re-measured on this release.

## A note on references in the tree

This is a squashed export of a private repository: the first commit is the tree of
2026-09-04 that still carries the v1 and holo2 receivers, the second the tree at release.
Commit shas, tags and branch names cited in the documents resolve only in the private
repository. The regeneration spans are in `docs/evidence-archive/REGENERATION-2026-10-22.md`
(paperholo era) and `measure/evidence_regen/README.md` (holo era). That README's verdicts
were measured in the private repository, on the machine holding the archive: its driver
compares against the build record's hash table `docs/evidence-archive/hashes-retained.tsv`
(`--hashes`), which this export does not carry, else against archived files in that
machine's layout (`--root`), and runs each family in a `git worktree add --detach` of its
commit. The generators of the rows marked `main` are in this tree. Files the record names
but does not carry were
withheld as working papers. Angle-bracket tokens stand for removed private strings:
`<ip>`, `<host>`, `<home>`, `<tmp>`, `<volume>`, `<city>`, `<repo>`, `<checkout>`,
`<conversation>`, `<SERIAL>`, `<worktree>`, `<user>`, `<office>`, `<evidence>`,
`<work>`, `<scratchpad>` and `<dir>`; "machine N" names a workstation. A few of these
swallowed a closing backtick or bracket where they were written. Scripts that recorded
their own interpreter path, working directory or host name into a manifest will do so
on your machine too.

## Licence

MIT, the text in `LICENSE` at the repository root; the evidence releases carry the same
notice. Written by Germano.
