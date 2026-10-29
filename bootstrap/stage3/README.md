# stage3/ — c.py, the stage-3 program (2026-10-22)

**State, 2026-10-26.** c.py `b4f7de22…` met paper: written by the typed
b.py from the printed R2 pages (sha-equal to this folder's c.py), it read
600 dpi pixma scans of the printed archive pages and closed the T1 volume on
the first eight (6,264 symbols of 6,260; placed 840 or 839 a page,
certified 541-840), payload.bin sha-equal to the container `78d9a4b4…`,
321 files unpacked; the dpi fallback fired once (`no tile placed at 1200
dpi, trying 600 dpi`), a page fed twice changed nothing, every page
`turn 180` (bootstrap/PAPER-2026-10-26.md). Ruling 37's 600 dpi holds on
paper; 300 dpi cannot read this row (1.5 px per cell). The unpacked
release does not run (new on paper: no LDPC tables, flat names; known
since ruling 40 and met in practice: no requirements file; FINDINGS.md §16). Whether this promotes c.py is the owner's ruling. Open
threads: docs/TODO.md, section Bootstrap.

**State, 2026-10-23, late — superseded by the state above, kept as
history** (CONVERGENCE-2026-10-23b.md: ruling 60's
convergence re-run on the repaired c.py). c.py is **24,176 B, 476 lines, no
import (sha256 `b4f7de22…`, CRC-32 `e3246653` = 3810813523)**, the member
kept by make_c.py's two-cycle rule (d'), RULED 2026-10-26 (ruling 67): it is
the pipeline's output under the chain of `c0ffe2a5` (N2 24163), and under
its own chain the output is `c0ffe2a5` again (the pipeline under `c0ffe2a5`'s
chain writes `b4f7de22` and under `b4f7de22`'s writes `c0ffe2a5`; the
member with the smaller own print is kept, typed 3,289 / 3,289 for both,
R2 10,133 against 10,147 B upper); through cm2 **10,130 / 10,133 B = 2 R2
pages with 478 / 475 B spare** under the chain's lower / upper b.py
(4,487 B), 390 chunks; T1 byte-exact at 8 scans (arch) and 13 (arch40),
page 03's six scans 840 / 840 each. The paragraph below is the state
before the re-run.

**State, 2026-10-23** (RECORD-2026-10-20.md through ruling 65). c.py is
24,163 B, no import (sha256 `c0ffe2a5…`, CRC-32 `8b2b48d9`), generated
from `c_readable.py` (61,569 B, sha256 `8f0dd6a6…`, the source of record,
ruling 57) for the row c3-k-r0547-p100 (ruling 36), since the repair of
2026-10-23 and its third pass (the lattice search, the per-tile retry,
LDPC alpha 0.8, the neighbouring-dpi fallback, one progress line;
committed in 8affb97b and da0cd032; RESULTS-2026-10-22.md "The repair of
2026-10-23"): through
cm2 10,144 / 10,147 B = 2 R2 pages with 464 / 461 B spare under the
chain's current lower / upper b.py (`build/sheets/stage1/`, 4,486 B,
which bake the PREVIOUS c.py's length and CRC; sizes_c.py's CHAIN rows
read them since the third pass); the printed page 03 (scratch/typed2)
reads 840 placed / 840 certified on its six scans, at two dpi hints off
by −4 / +5 %, and declared at the wrong standard dpi (1200 for a 600
scan and the reverse, through the fallback), and the T1 simulation
closes byte-exact (RESULTS, the third pass). Before the third pass:
24,043 B, `8a1f412d…`, CRC `3fb94a3c`, cm2 10,052 / 10,055 B (556 / 553
spare). The rest of this
paragraph is the c.py before the repair: 24,080 B, 459 lines, `92c48a39…`,
CRC `3acc4add` (the convergence commit 39da92bc), 9,944 / 9,947 B cm2 under
today's chain primers, 664 / 661 B spare; the generation before it, 23,793 B
`c26869af…`, was 9,951 / 9,956 B = 2 R2 pages with 657 / 652
B spare under the ruled b.py of a9826d37; under today's b.py (the
composite, the progress line, the literal `@` and the grey padding since,
r2reader/changeset/RESULTS-2026-10-22.md §17 to §20) it is 9,966 / 9,971 B,
2 pages, 642 / 637 B spare (§20, part 2). Qualified in
simulation: 321 of 321 files byte-exact from the plain scans (8 pages to
close, 1,141 s) and from the 40 %-blanked set (13 pages, 1,382 s); holo's
own receiver VERIFIED the same volume (RESULTS-2026-10-22.md §3, §6). The
stage1/ chain (stages 1 and 2) with c.py as the content passes both cases
at 3,465 / 3,463 typed under the same b.py of a9826d37, and at 3,319 /
3,318 under today's (changeset/RESULTS §20, part 2). The archive layer
(strong2 and the flat-name ustar unpacker) stays as built (ruling 61, the
owner, 2026-10-23). Since closed: the deep review (2026-10-23,
`review/REFUTER-2026-10-23.md`, RECORD-2026-10-20.md:1844; ruled by 63 and
65, repaired); ruling 37's 600 dpi (the review's simulation and paper,
2026-10-23 and 10-26); the pipeline re-scored under the chain's b.py (both
convergences); the page bound (R2_PAGES_BOUND = 3) and the tuple
(0,1,2,3,4,6). Still open (docs/TODO.md, Bootstrap): the c4, `_os` and
channel variants; the rough-channel re-qualification; payload.bin as a
self-unpacker (the release step's option under ruling 61); the T1 tree is
the record's (67 files of its selection differ at HEAD 4a4b2f4d).

**Source of record: `c_readable.py`** (ruling 57, 2026-10-22). c.py is
GENERATED from it by `make_c.py`; `make_c.py --provenance` shows that
c_readable.py is the record's receiver_arch.py after the scripted retarget
plus two documented hand changes. Edit c_readable.py, never c.py.

Stage 3 of the bootstrap (RECORD-2026-10-20 ruling 34) is **`c.py`**: the
program the typed reader `b.py` writes after it has read the R2 pages from
phone photos. c.py is the R3 monolith receiver with its archival layer
(`bootstrap/r3/arch/receiver_arch.py`, the record of 2026-10-20). It is
pure Python with no imports. It does five things:

1. reads PGM scans of the holo K sheets that carry the release (stage 4);
2. closes the fountain volume;
3. checks the SHA-256 and writes `payload.bin`;
4. if the payload is an `R3A1` container, decodes it (the context-mixing
   decoder, about 13 minutes and 1.4 GB for T1) and checks its CRC-32;
5. unpacks the tar to flat names (`%2F` for `/`), printing every path.

Three things differ from the record's monolith:

- **The row is r0547** (ruling 36), not r0550. That means the FORMAT_ID
  string `holo/v2/1i200-k-r0547-p100-v1@35x24`, the LDPC table packed from
  `src/holo/core/ldpc/data/r0547.json`, and five comment and docstring
  mentions of the rung.
- **Hand changes in the source** (ruling 57): the docstring names the
  program c.py (it said b.py; ruling 34), and two silent stretches print
  progress (the section below); since 2026-10-23 the lattice search (the
  address word as arbiter over candidate lattices at three trial pitches)
  and the per-tile retry (RESULTS "The repair of 2026-10-23").
- **The text is the monolith pipeline's output.** The pipeline is
  minified-g → M1 → M2 → M3, scored under the new primer, which is the
  ruled b.py text.

c.py costs **10,130 B of cm2**, which fits 2 R2 pages with 478 B to spare
(the lowercase chain; uppercase is 10,133 B, 475 spare), at the re-run
convergence's fixed point (CONVERGENCE-2026-10-23b.md); 10,144 / 10,147 B
(464 / 461 spare) after the third
pass of the repair of 2026-10-23; after its second pass 10,052 / 10,055 B
(556 / 553 spare). Before the repair, 9,944 / 9,947 B (664 / 661 spare, the c.py of
39da92bc); the generation before, 9,951 / 9,956 B (657 / 652 spare); before the
progress lines 9,887 / 9,890 B (721 / 718 spare). Up to the repair,
simulation only; the repair was measured on page 03's prints; c.py
`b4f7de22…` closed the T1 volume from real scans on 2026-10-26. Nothing is
promoted.

## What the progress lines print

Inside a scan (about 40 s each), before the existing one-line summary,
which is unchanged, one line once a cell lattice has placed the page's
tiles (since the third pass; before it, one line per candidate lattice
tried and a second for the placement):

```
NAME: cell lattice found, 840 tiles placed, decoding
NAME: page 3, turn 0, tiles placed 840/840, decoded 840, certified 840; ...
```

When nothing places at the dpi given, the scan is searched again at the
other standard resolutions (600, 1200, 2400, nearest first), each with a
line before it:

```
NAME: no tile placed at 1200 dpi, trying 600 dpi
NAME: cell lattice found, 840 tiles placed, decoding
```

During the archive decode (about 13 minutes after `archive: decoding`), a
heartbeat every 5 % of the archive's bytes (the decoder's output loop):

```
archive: decoding
archive: 5% decoded
...
archive: 100% decoded
```

Then the paths, as before. Measured on the simulated plain scans: lattice
~3 s, placement ~4 s, decoding ~31 s per page (placement ~18 s on a 40 %
blanked page); a heartbeat every 36–44 s. The prompt `scan (PGM file
[dpi]; empty line ends): ` has no newline, so on a piped stdin the first
phase line follows it on the same line.

Cost: 3 print calls, +194 B of c.py text; +59 B of cm2 on the minified text
(the strings), +64 / +66 B on c.py under the chain's lower / upper primers
(the remaining 5–7 B: the rename search's different local optimum on the
new text). RESULTS-2026-10-22.md §6 has every number.

## Files

| file | what |
|---|---|
| `c_readable.py` | **The source of record** (ruling 57): the readable long form, 61,569 B, sha256 `8f0dd6a6…` (the repair of 2026-10-23 with its third pass, committed in da0cd032; after the second pass 60,862 B, `cedcce43…`; before the repair 58,868 B, `be95e6ea…`). Edited by hand; every edit beyond the documented changes needs `make_c.py`'s PROVENANCE_HUNKS, REPAIRED and its checks moved with it. |
| `c.py` | The deliverable: 24,176 B, 476 lines, sha256 `b4f7de22…`, CRC-32 `e3246653` (the re-run convergence's fixed point, CONVERGENCE-2026-10-23b.md; after the repair's third pass 24,163 B, `c0ffe2a5…`, CRC `8b2b48d9`; after the repair's second pass 24,043 B, 470 lines, `8a1f412d…`, CRC `3fb94a3c`; before the repair 24,080 B, 459 lines, `92c48a39…`, CRC `3acc4add`; the generation before that 23,793 B, `c26869af…`). Generated from c_readable.py, never edited by hand. |
| `make_c.py` | The ONE generation: c_readable.py → minify → pipeline → static equivalence → `c.py` (when the output differs from the tree's c.py, the pipeline is run again under the output's own chain; a two-cycle keeps the member with the smaller own print, step (d'), 2026-10-23), plus `build/stage3/forms/` and `build/stage3/make_c.json`. `--provenance`: the link from the record (below), into `build/stage3/c_retarget.py` and `build/stage3/provenance.{diff,json,log}`. |
| `lab/` | The encoder lab, copied: `names2.py`, `search2.py` and `cm2h.c` from `r2reader/changeset/rw/`, which are identical to `compressor-exploration/encoder-side/`'s; `mono_inline.py` from encoder-side; and `ev.py` = rw's ev.py with the library built into `build/stage3/lab/`; its docstring's default orders (0,1,2,3,4,6,8) are overridden by make_c.py to the chain's (0,1,2,3,4,6) (make_c.py:129-130). |
| `sizes_c.py` | Exact cm2 sizes by the chain's coder (`typed/cm2_enc.encode`) for every form under the new, chain (`build/sheets/stage1/<case>/b.py`, the current chain build) and old primers. It also runs the same pipeline on the r0550 text. Writes `build/stage3/sizes.json`. |
| `e2e_c.py` | The R3 record's end to end (`r3/arch/e2e_arch.py`, reused) at the r0547 row: volume, the arch / arch40 scans, the runs, and holo's own receiver on the same pages. |
| `unit_c.py` | The record's scan-free checks (`r3/arch/test_arch.py`, adapted to renamed forms as `mono_test.py` did): synthetic ustar, wrong CRC, plain payload, on both forms. |
| `chain_c.py` | At tag bootstrap-pre-thinning-2026-10-23, superseded by `stage1/chain_v2.py` (`make|e2e|pages|identity CASE --out DIR [--tree DIR]`, which `rebuild_v2.py` runs). It was `stage1/make_typed.py` and `stage1/e2e.py` with their BUNDLE constant pointed at c.py; `stage1/` itself is untouched. `--tree DIR` runs them from an exported bootstrap/ tree (when another line is editing the reader in the worktree). |
| `RESULTS-2026-10-22.md` | Every number. |

## How c.py is generated

```
env/bin/python bootstrap/stage3/make_c.py [--workers 6]    # ~8-11 min
env/bin/python bootstrap/stage3/make_c.py --provenance     # seconds
```

**The generation** (no argument) reads `stage3/c_readable.py` and nothing
of the record but the minifier's calibration text:

1. **(b') The source's checks.** Its expanded parity checks equal holo's
   `load_code('r0547')` edge set minus the shortened tail (14,611 edges),
   and its FORMAT_ID equals holo's seed for `c3-k-r0547@35x24`.
2. **(c) Minify** with `r3/measure.py`'s `minify(src, True)`. The
   calibration: on the record's receiver_arch.py it reproduces the record's
   24,460 B minified-g form byte for byte. Docstrings and comments do not
   reach c.py.
3. **(d) The pipeline.** The primer is the chain's upper `b.py` with the
   tree's c.py itself as the content (`stage1/chain_v2.py make upper`, the
   frozen spelling, tuple (0,1,2,3,4,6), rebuilt every run into
   build/stage3/stage1_chain/), and, when the output differs, the
   partner's chain for the two-cycle step (d') (make_c.py:28-52, ruling
   67). Before the convergence of 2026-10-23 it was the stand-in build's
   lower b.py at (0,1,2,3,4,6,8), sha256 `d29737a8…`, 4,700 B. Three steps:
   - **M1:** the minifier's module aliases are inlined, greedily;
   - **M2:** one windowed sweep of scope-exact local renames;
   - **M3:** the program's own attribute and method names, longest first.

   Ties keep the current text. The C mirror's scores do not depend on the
   worker count, so the output does not either.
4. **(e) Static equivalence.**
   - **M1:** the ast of the input, with each removed alias's module-scope
     occurrences replaced by its value, equals the output's ast.
   - **M2 and M3:** a parallel ast walk finds identical node types,
     constants and operators. Names are related by a bijection between
     names2's scope-resolved bindings, with builtins fixed, and attributes
     by a bijection that method names follow.
   - c.py compiles and contains no `import` statement and no `__import__`.

   The dynamic check is the end to end below.

Run twice from c_readable.py (488 s and 489 s, 6 workers), make_c.py gave a
byte-identical c.py; with (d') a run builds the partner chain too, 964 s and
1,154 s, twice byte-identical (CONVERGENCE-2026-10-23b.md).

**The provenance** (`--provenance`) makes the one hand-made link visible:

1. **(a)** `make_arch.build(False)` rebuilds receiver_arch.py in memory. It
   is asserted byte-identical to `r3/arch/receiver_arch.py`; nothing is
   written to `r3/`.
2. **(b) Retarget.**
   - **The table.** `r3/pack_ldpc.py`'s packing is re-implemented here,
     because the script itself rewrites r3/receiver.py. It is calibrated by
     re-packing r0550.json to the exact table receiver_arch carries.
   - **Checks on the JSON:** n 4096, k 2240, Z 64, 10 heavy + 25 light
     column blocks, every digit inside its radix.
   - **The text edits:** the rung's seven non-table spots, each matched
     exactly once.
   - **Checks on the result:** the edges and FORMAT_ID as in (b'), and its
     minified-g differs from the record's in exactly two literals
     (FORMAT_ID, LDPC_TABLE). → `build/stage3/c_retarget.py` (58,363 B,
     sha256 `bbef84ea…`, the former derived readable form).
3. **(f) The diff** c_retarget.py → c_readable.py, printed hunk by hunk
   without context, must be exactly `PROVENANCE_HUNKS` = 20 hunks (19
   after the repair's second pass, 6 before the repair of 2026-10-23):
   - five inside the module docstring: the naming (c.py, not b.py), the two
     sentences that describe the progress lines, the dpi sentence (with
     the fallback) and stage 2's lattice clause;
   - fifteen in code: ONE at module level, `ALPHA_LINE`, the LDPC_ALPHA
     literal 0.75 → 0.8 and nothing else on its line (rulings 63 and 65);
     every other changed line (old side and new) inside one of the six
     `REPAIRED` functions (`Scan.__init__`, `Scan.aperture`,
     `Scan.find_lattice`, `Scan.track`, `Receiver.read_scan`,
     `Receiver.decode_tile`) or the one pure insertion in `unz`, the
     heartbeat; three print calls added (the progress line, the dpi
     fallback's line, the heartbeat), none removed;
   - with both docstrings, the heartbeat and the six repaired functions
     dropped, and the retarget's alpha set to 0.8, the two trees are
     ast-identical: nothing else in the logic changed.

   Edited the source again? Move `PROVENANCE_HUNKS` and the checks with the
   change, and say so in the RESULTS.

## How to re-run the qualification

From the worktree root:

```
PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py volume              # holo generate c3-k-r0547@35x24 q 0.5, gs K plane == GT
PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py scans arch arch40   # make_test_volume.simulate, the record's seeds
env/bin/python bootstrap/stage3/e2e_c.py run arch   bootstrap/stage3/c_readable.py T1_readable
env/bin/python bootstrap/stage3/e2e_c.py run arch   bootstrap/stage3/c.py T1_c_arch            # ~20-25 min, 1.5 GB
env/bin/python bootstrap/stage3/e2e_c.py run arch40 bootstrap/stage3/c.py T1_c_arch40
PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py holo3 arch 4         # holo's receiver on the same 15 pages
env/bin/python bootstrap/stage3/unit_c.py                                    # scan-free: synthetic / badcrc / plain
env/bin/python bootstrap/stage3/sizes_c.py                                   # exact cm2 sizes, every form x primer
env/bin/python bootstrap/stage1/chain_v2.py make lower --out DIR    # and upper: stage1/ (stages 1 and 2) with c.py as the R2 content
env/bin/python bootstrap/stage1/chain_v2.py e2e lower --out DIR     # and upper: pages, typing, b.py reads -> c.py (rebuild_v2.py runs make, pages, identity)
# while another line edits r2reader/ or stage1/: export HEAD and run from it
git archive HEAD bootstrap | tar -x -C bootstrap/build/stage3/head-SHA
mkdir -p bootstrap/build/stage3/head-SHA/bootstrap/build
ln -s $PWD/bootstrap/build/r2 bootstrap/build/stage3/head-SHA/bootstrap/build/r2
env/bin/python bootstrap/stage1/chain_v2.py make lower --out DIR --tree bootstrap/build/stage3/head-SHA/bootstrap
```

**The container is the record's T1.** That is
`build/r3/arch/e2e_arch/T1/container.bin`, sha256 `78d9a4b4…`, 321 files,
copied with its sha checked. The archive layer does not depend on the row,
so there is no re-encode while the record's copy is present. The truth for
the unpacked files is the
record's `T1.tar`: at HEAD 4a4b2f4d 67 files of its selection differ from
2115a595 (37 modified, 30 added). Both are made from git: `T1.tar` from the blobs of commit 2115a595
(`T1_COMMIT` in `e2e_c.py`; `r3/arch/arch_pack.py T1 --commit 2115a595`),
the container by the encoder derived from `r3/arch/receiver_arch.py`. When
`build/r3/arch/e2e_arch/T1/` lacks them (an empty `build/`), `e2e_c.py`
makes both there, 13 minutes and 1.4 GB, and checks the same two shas
(CONTROL-REBUILD-2026-10-23.md §1.3).

All outputs go to `bootstrap/build/stage3/` (gitignored); the e2e outputs
alone take about 5 GB.
