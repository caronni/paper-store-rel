# measure/evidence_regen — do the archived print jobs regenerate from their tagged trees?

The owner's rules of 2026-10-09: printed jobs are kept with the Python that
regenerates them, checked by checking out the tagged tree and regenerating
bit-identically (rule 3); `*_gt.npy` are deleted because they are derivable
from the PostScript (rule 4). This package checks both, plus two derived-scan
side checks. It reads the archive and never writes into it; nothing is deleted.

    PYTHONPATH=src:. env/bin/python -m measure.evidence_regen regen --work DIR --hashes TSV [--family 'ID|glob' ...]
    PYTHONPATH=src:. env/bin/python -m measure.evidence_regen gt
    PYTHONPATH=src:. env/bin/python -m measure.evidence_regen side [--only decimated|x2]
    PYTHONPATH=src:. env/bin/python -m measure.evidence_regen tags

Run from any checkout (a worktree has no `env/`: use the main checkout's
interpreter). `--root` is the archive root, default the main checkout (its
`scratch/`, `scans/`, `build/` and the experiments' `build/` dirs). Reports go
to `build/evidence-regen/` (`verdicts.tsv`, `gt.tsv`, `side*.tsv`); they are
regenerable and stay out of git.

- `families.py` — the table: per family the commit, the steps, the archived
  files it must re-make, the tag. Not-regenerable rows carry their reason.
- `runner.py` — one `git worktree add --detach` per commit under `--work`
  (patch applied where named), steps run with the worktree as cwd and
  `PYTHONPATH=<wt>/src:<wt>`, outputs into `--work/out/<family>`, sha256
  against the hash TSV by archived path (else the archived file on disk),
  worktree removed after its last family. Verdicts: `byte-identical`,
  `differs` (a JSON file names its differing keys), `not-produced`,
  `not-runnable` (the step's error), `not-regenerable` (the reason).
- `_emit_fossil.py` — main's python fossil route (`resolve_format_ref` +
  `emit_volume`); `confetti.py generate --format L:…` is refused at main.
- `_git_show.py` — `git show REF:PATH > OUT` from this checkout: a step that
  needs a script as it stood at an older commit (the e025 -v1 emitter).
- `clean_decode_e018b.py` — the e018b payload out of its published page,
  clean domain (the e018b row's first step).
- `gt_check.py` — every GT array against its job through `util/ps_gt.py`.
- `side_checks.py` — e018's 1600-dpi decimations and the `scans/*-x2.png`.

## Verdicts — 2026-10-09, machine 1, regen wall 286 s (`--hashes` = the archive's retained-file TSV)

| family | tree | archived files | verdict |
|---|---|---:|---|
| e029 K ink page (= e033 B) | main 53451bc4 | 4 | 4 byte-identical |
| e030 colour -v0 pages (4) | main | 16 | 16 byte-identical |
| e033 A–I, emitting tree | bcd352c1 | 40 | 40 byte-identical |
| e033 via f1bc0d0f + c4-row-and-xerox-4mm.patch | f1bc0d0f | 40 | 32 byte-identical; H, I not-runnable (`unknown coding 'c2-cmy8-r0850-p120-x1'`: the patch has no x1 rungs) |
| e033 at main (catalog CLI with a same-field printer row; A/H/I fossil route) | main | 30 | 24 byte-identical (every PS and GT); 6 manifests differ in `printer_id`/`margin_mm` only (the substituted row) |
| e035 sheet J pages + duplex splice | 8260257d | 7 | 7 byte-identical (`duplex.ps` a954bb8e… included) |
| e039 set A–J + default discovery pair + `e039-all-pages.ps` (+ e028's discovery copy) | main | 52 | 52 byte-identical |
| HCAL discovery 1200x2400 pair | main | 5 | 5 byte-identical |
| e039 IPP renders (URF, PDF, PWG, stencils, probe pages, sRGB chart) | main | 33 | 25 byte-identical (all ten sheets' renders, all probe pages, the chart); 8 differ — every render of a discovery sheet, see below |
| e041 S1–S17 jobs, bands npz, S1dash/S5 GT (from the regenerated F and e030 c3-cmy7) | main | 35 | 35 byte-identical |
| e042 X1 job + bands | main | 2 | 2 byte-identical |
| e027 charsheet-1 | 41acf2eb | 3 | 3 byte-identical |
| e025 hp-m281-{bw,color} | main | 4 | 4 byte-identical |
| paperholo e001–e017 generators (19) + the five office-bundle copies | main | 808 | 808 byte-identical (jobs, manifests, every `_gt` array, ores PCL/PJL) |
| build/demo volume | main | 7 | 7 byte-identical |
| sim 1i150-k-r0547-p100-v1@7x7 | main | 4 | 4 byte-identical |
| local-ab sim color-hard-emit (+ its four variant copies) | 63126a89 | 16 | 16 byte-identical |
| 2026-10-26: e018-tar, the CORE `recovered_e018.tar.gz` (main's `gen_e018.py` copied in, `make_targz()`) | eb5174e9 | 1 | 1 byte-identical |
| 2026-10-26: e018 page + manifest (main's `gen_e018.py`, `make_targz()` replaced by e018-tar's bytes) | main 4d594e24 | 2 | 2 byte-identical |
| 2026-10-26: e018b c2/c3 pages + manifests, re-emitted from the payload decoded out of the published pages | main 4d594e24 | 4 | 4 byte-identical |
| 2026-10-26: scratch/fullpage-*.ps + manifests (`regen_fullpage.py --write-gt`) | main 4d594e24 | 4 | 4 byte-identical |
| 2026-10-26: e025 hp-m281-{bw,color}-v1 (9df37bf1's `emit_e025.py` + `e025_common.py` against main's library) | main 4d594e24 | 4 | 4 byte-identical |
| pre-print-day HCAL emissions | — | — | not-regenerable: dirty-tree emissions (nearest dce153f9), no tracked sha |
| scratch/test_pattern.ps, e039 ps-probe{,-pjl}.ps | — | — | hand-written: their own source |
| build/holo-c2-r0550@3328x2304 | — | — | not-regenerable: payload unknown |
| e039 invalid-039.3c | — | — | not-regenerable: made by the pre-039.3e pbmraw tools |
| e041 S11t | — | — | no generator; the archived S11/S11t differ in exactly 6 bytes (0 → 1) |

**2026-10-26 — the five rows marked 2026-10-26** (machine 1, wall 36 s, the
e018b decodes 23 s + 6 s of it), run from a worktree (branch
`evidence-regen-foldin`) with the main checkout's interpreter:

    PYTHONPATH=src:. <main checkout>/env/bin/python -m measure.evidence_regen regen --work DIR \
        --hashes docs/evidence-archive/hashes-retained.tsv --root ROOT \
        --family e018-tar --family e018 --family e018b --family fullpage --family e025-v1

`ROOT` must be laid out like the published paperholo-era release for e018b,
whose inputs are the published jobs
`ROOT/018b-payload-sheet/{c2,c3}/jobs/e018b-*.ps` + `_manifest.json`; every
expected sha of the five rows comes from the hash TSV. The recovered e018b
image (the Lena test image, withheld under D1) lands under `--work`; never
commit it. `regen` runs families in table order, so e018-tar (the producer)
precedes e018. The e018 payload tar is recoverable two more ways: from the
page itself (the e018 sessions decoded it byte-exact, e018 log §018.0) and
from any of the four 2026-07-10 trees `eb5174e9`, `56918373`, `e98346df`,
`f8de66eb` (`06a8134c` changed `formats.py`/`place.py` and broke it); the
e018 row also runs at every tree from `f3b71a6d` (2026-07-08) on. The
fullpage payload arrays are written (`--write-gt`) but not compared: the hash
TSV does not list them. The fullpage compare's expect list is literal, so its
archived dir (`scratch/`, the owner's live tree when `--root` is the main
checkout) is looked up file by file, never walked.

**2026-10-22 — four not-regenerable rows overturned by measurement** (the
span sweep over 84 trees, `span_sweep.py`; record
`docs/evidence-archive/REGENERATION-2026-10-22.md` §2 and §4): e018, e018b,
fullpage and e025 -v1 are measured rows of the table above since 2026-10-26;
the spans and the four hoops are in the record. Also measured: every
`paperholo-*` family and e025 are byte-identical from their generator's
first commit through main with no hole (e017's one hole is a side-branch
commit that predates the generator), and
`ores_pspjl1200.job`, absent from the hash table, equals the release's
`MANIFEST.sha256` entry when regenerated at main.

**The eight e039 discovery renders are not reproducible by design.** The
HCAL discovery PostScript draws `realtime` (its `NONCE`) into both machine
strips at render time, so ghostscript produces different strips on every run:
two `urf_raster.py` renders of the same PS today differ from each other, and
the decoded pixels of the archived and the fresh render differ only inside the
two strips (bw URF: 2,556 px in ten clusters at y 347–382 and 6630–6665 dots;
colour PDF: 2,232 px at y 300–400 and 6600–6700). The sent files are the
record; the PS they came from regenerates byte-identically (e039-set row).

Where a `byte-identical` row's expected sha came from the archived file on
disk rather than the TSV (`expected_from=disk`), the claim is "regenerates the
bytes on disk"; the TSV lists the retained files, so every GT array is a disk
row.

## GT check — 810 arrays

- **holo layout, 43 files** (`pageNNN_gt.npy` of e028/e029, e030, e033 A–I,
  e035 J, e039 A–J, the sims, build/demo, build/holo-c2-r0550, charsheet-1,
  e041 S1dash/S1dash-alldust/S5): **43 gt-derivable**. S5 is three stacked
  DeviceCMYK images composed first.
- **paperholo dot arrays: 687 gt-derivable** (equal to a whole bitmap or CMYK
  plane, or to the crop at the manifest's rectangle; e009's rectangles are
  relative to its one logical bitmap).
- **label arrays (`*_states`, `*_levels`, `*_cells`, e009 `pn_*`, e010 motif
  maps): 73 derivable-via-cell-map** — the job's dot planes determine every
  label cell by cell, the map being the generator's alphabet;
  **1 not-derivable**: `003…/modprobe_gt/S3_base_cells.npy` (one printed cell
  pattern carries two labels: the base pattern under the pilot voids);
  **4 not-checked**: `009…/ores_gt/pn_*_2400.npy` live only in
  `ores_pcl2400.pcl` (PCL raster; the parser reads PostScript).
- **payload symbol arrays: 2 not-derivable** —
  `scratch/fullpage-{bw-kcell-c2,color-a3-7st-c3}_gt/*_payload.npy`.

The five label arrays the job cannot settle (S3_base_cells, the four
`pn_*_2400`) regenerate byte-identically from their generators (the
gen_modprobe and gen_ores rows above).
The two fullpage payload arrays are the only GT files that are neither
derivable from their PS nor regenerable. (2026-10-11: they are regenerable
the same way, via experiments/007-office-disc/regen_fullpage.py at the tag
evidence/fullpage-20260707@cb2a8ffb — they are its seeded symbol draw; the
driver passes write_gt=False, so it does not write them to disk.
2026-10-26: the fullpage row runs it at main with `--write-gt`, which writes
them; they are not in the hash TSV and are not compared.)

## Side checks

| derived | check | verdict |
|---|---|---|
| `scratch/e018/decimated-{1,1-2nd,2,2-2nd,3,3-2nd}_1600.tiff` (6) | `decimate_scan.decimate` (/3) of the 4800 capture, pixels | 6 identical |
| same | file sha256 of `tifffile.imwrite` (tifffile 2026.8.23) | 6 byte-identical |
| `scans/{disc1p1-xeroxscan-col,disc1p2-xeroxscan-grey,e006bw-xeroxscan-col}-x2.png` (3) | 2x nearest neighbour of the source PNG | 3 differ |
| same | `scipy.ndimage.zoom(float32, 2, order=1, grid_mode=False).astype(uint8)` (scipy 1.18.1) | 3 identical |

The x2 kernel is recorded nowhere (e007 007.2 says only "COLOR path needs 2x
upsampling"); it was found by search and matches every pixel of all three.
Decimation wall 94 s (memory-mapped, 3,072-row bands); x2 wall 62 s.

## Tags (lightweight, `evidence/<family>-<commit date>@<sha8>`; pushed to origin 2026-10-10)

Only trees something regenerates from byte-identically carry a tag of this family; bookmarks
that nothing checks were dropped on 2026-10-10 in favour of the tags that already existed.

| tag | pins |
|---|---|
| `evidence/main-regen-20261009@53451bc4` | every family run at main; the receiver the archive READMEs' decode commands run at |
| `preserve/e033-rung-rows-bcd352c` | the emitting tree of e033 A–I (pre-existing tag; the duplicate `evidence/e033-original-…` was dropped) |
| `evidence/e033-patch-base-20260818@f1bc0d0f` | the parked-patch route (f1bc0d0f has dec3cb52's src/holo) |
| `evidence/sheet-j-generation-20260902@8260257d` | e035 sheet J and its duplex job |
| `evidence/charsheet1-20260720@41acf2eb` | e027 charsheet-1 |
| `evidence/local-ab-sim-20260831@63126a89` | the local-ab sim emission |
| `evidence/fullpage-20260707@cb2a8ffb` | the two 2026-07-07 fullpage capacity-demo pages: `paperholo.encodings` at this commit with the payload from `np.random.default_rng(20260707)` (driver recovered from the genesis-week transcripts 2026-10-10; byte-identical on re-run). [2026-10-22: the tag is NOT needed — the driver reproduces both pages at every tree from cb2a8ffb through main, manifests and payload arrays included once it writes its ground truth; docs/evidence-archive/REGENERATION-2026-10-22.md §4.3] |
| `evidence/e018-20260710@eb5174e9` — OWED TO MINT, not minted (2026-10-26) | the e018-tar row's tree: the e018 payload tar regenerates there; `tags` would create it from the family table |
| `pre-v1-v2-deletion` (80041d52, 2026-09-04) | the last tree holding both the v1 receiver (`src/holo/receive`) and `holo2/` — the pre-existing tag that replaces the dropped `evidence/v1-receiver-…` and `evidence/holo2-…` bookmarks |

Dropped 2026-10-10, nothing regenerates from them: `evidence/hcal-v2-20260731@1430af0c` (the pre-print-day
HCAL emissions came from a dirty tree and do not regenerate; the note stands in the family table).
