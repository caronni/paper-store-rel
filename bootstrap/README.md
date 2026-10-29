# bootstrap/: the deep-time recovery chain, stages 0 to 4 (index, 2026-10-26)

docs/BOOTSTRAP-DESIGN.md asks what the front leaves of every printed volume
must hold so that a finder centuries from now, with Python-class computing
and nothing but the paper, can rebuild paper-store and open the dense,
anonymous archive pages. Its answer is a ladder bound into every volume
under one law: nothing crosses the channel before its own specification has
crossed. This directory is that ladder built: each stage is a program the
finder obtains from the paper using only what the stage before delivered,
and each program reads the next carrier, from text typed by hand, to phone
photos of coarse pages, to flatbed scans of the archive pages.

Everything here was built and measured in simulation on machine 1 between
2026-10-18 and 2026-10-23 (the compressor exploration's figures of ruling 32
in a cloud container), and on paper three times: 2026-10-20, stages 1-3
with a stand-in content (PAPER-2026-10-20.md); 2026-10-23, the v2 print,
stages 1-3 closed and archive page 03 not read, which led to c.py's repair
(FINDINGS.md §15); 2026-10-26, the candidate print of record v3
(print-2026-10-23.pdf 4989446c…, ruling 67): THE WHOLE CHAIN CLOSED, a.py,
b.py and c.py sha-equal to the chain, the volume from eight 600 dpi scans,
payload.bin 78d9a4b4…, 321 files unpacked (PAPER-2026-10-26.md). One print,
one typist who designed the chain. The release as unpacked does not run
(no LDPC tables, no requirements file, flat names: FINDINGS.md §16). Every
number below is MEASURED unless marked ESTIMATE and carries its pointer.
Nothing is promoted; v3's promotion to the print of record is the owner's
ruling. The rulings are indexed in RECORD.md (1 to 68 of RECORD-2026-10-20.md
through 2026-10-26), the findings for a ten-minute reader are in
FINDINGS.md, the typed stream is TYPED-STREAM.md v3 and the page format
R2-FORMAT.md v1, the physical runs one line each in docs/EXPERIMENT-LOG.md,
and every open thread in docs/TODO.md, section Bootstrap.

The stages are named by the program each one yields (ruling 34,
RECORD-2026-10-20.md:908): stage 1 is the typed program a.py; stage 2 is the
data sheet typed at its prompt, which yields b.py; stage 3 is the R2
(bullseye) pages, read from phone photos by b.py, which yield c.py; stage 4
is the release, which c.py reads from the holo archive pages (the scanner
comes between stages 3 and 4). Stage 0 is the Plate.

| stage | the carrier | read by | what it yields |
|---|---|---|---|
| 0 | the Plate (deferred), printed text | the finder's eyes | the promise, CRC-32, the key, the conventions |
| 1 | the a.py listing | the finder, typing it into a file | a.py |
| 2 | the data sheet | a.py, at whose prompt it is typed | b.py |
| 3 | the R2 (bullseye) pages, phone photos | b.py | c.py |
| 4 | the holo archive pages, flatbed scans | c.py | the release, the paper-store tree |

The DIRECTORIES are named by program, not by stage: bootstrap/stage1/
builds a.py AND the data sheet of stage 2 (make_typed.py, e2e.py,
leaves.py); bootstrap/r2reader/ holds b.py, the program of stage 2 and the
reader of stage 3's pages; bootstrap/stage3/ holds c.py, the program of
stage 3 and the receiver of stage 4's pages.

## Stage 0: the Plate

What it is: the printed front matter in plain text, read by eye. The 10-18
draft states the promise, the CRC-32 as its one-line shift register (ruling
1 of RECORD-2026-10-18.md), the key and the conventions. The later rulings
list what it is OWED to state, none of it in the draft leaves yet: the
grid-to-PGM one-liner (ruling 49), the Python floor 3.11 (ruling 53), the
release volume's hash (ruling 39), one sentence on b.py's progress line
(ruling 56) and the reuse of letters across scopes in a.py
(stage1/RESULTS.md, "The a.py"). The for-print sheets 1-2 already carry
the floor, the one-liner and the progress-line sentence (rulings 62-66),
and the stage-4 pages print `RELEASE <commit>` and `n/15` in their margin
(0dfb3fed); the hash and the rest wait for the Plate (docs/TODO.md).

Files: plate/leaf1.txt, leaf2.txt, leaf2b.txt (the 10-18 panel's draft,
three leaves), plate/make_plate.py, plate/verify_plate.py, plate/NOTES.md,
plate/leaf1-2-notes.md.

Status: DEFERRED. The cut to one leaf was ruled on 2026-10-18 (ruling 2 of
RECORD-2026-10-18.md) and not made; ruling 38 (RECORD-2026-10-20.md:956)
puts the Plate and every printed text around stages 1 to 3 after those
stages are fixed. Leaf 2's typed-stream paragraphs still describe the
10-18 checker route. Test: `python3 verify_plate.py` from plate/ (it
re-derives every printed number from the printed rules; exit 0 = all
PASS).

## Stages 1 and 2: the a.py listing and the data sheet (bootstrap/stage1/)

What it is: at stage 1 the finder types the 28-line listing into a file,
runs `python3 a.py` and compares the self-dump codes with the listing's
margin; at stage 2 the finder types the data sheet's base-32 lines at a.py's
`[n]` prompt, and a.py's big-integer rANS decoder (cm2's model) turns them
into b.py. The
listing is printed in Menlo with every space a middle dot, the data sheet
in Andale Mono, uppercase (ruling 51, RECORD-2026-10-20.md:1324). The
finder's view is TYPED-STREAM.md.

Files (live, the source first; ruling 58's sources of truth, the
paragraph of RECORD-2026-10-20.md:1765): stage1/template.py (the
role-marked source), stage1/search.py, stage1/make_typed.py (a.py,
data.txt, codes.txt, b.py into build/stage1/<case>/),
stage1/gen_readable.py (the long form, a build output),
stage1/test_identity.py, stage1/e2e.py, stage1/leaves.py,
stage1/frozen_lower.json and frozen_upper.json; the codec typed/cm2_enc.py,
typed/cm2_dec.py, typed/kat_v2.py and kat_v2.json; the leaf renderers
pages/compose_leaves.py and pages/render_pdf.py.

Fonts and the QR library (untracked; provenance recorded 2026-10-27,
docs/PUBLIC-RELEASE-2026-10-22.md §11 D28): pages/render_pdf.py reads two
OCR-B faces by path, neither in git. The default face `ocrb` is the
standard's own OCR-B from Debian's fonts-ocr-b 0.3.1 (Skala's OCRB.otf from
Schwarz's METAFONT sources; public domain / permissive), read from
$OCRB_FONT or scratch/fonts/fonts-ocr-b-0.3.1/OCRB.otf. The face
`ocrb-redrawn` is Matthew Anderson's OCR-B (ocrb-2015-10-27.zip, once at
wehtt.am/ocr-b; the site is gone, the archived page is
https://web.archive.org/web/20190328152246/https://wehtt.am/ocr-b/ and the
zip https://web.archive.org/web/20190328152246if_/https://wehtt.am/ocr-b/ocrb-2015-10-27.zip),
licensed CC BY 4.0 with a non-commercial click-through at the download,
kept out of git for that reason and read from build/ocr/fonts/ or the zip
under scratch/fonts/. Without either face the renderer falls back to Menlo
and then to the system monospace faces it finds. The QR variant
(stage1/qr/make_qr.py) needs segno 1.6.6 and zxing-cpp 3.1.1 from a
directory named by QRLIBS; it was run once and its outputs and their shas
are committed.

Measured:
- The candidate print of record v3 (CONVERGENCE-2026-10-23b.md, ruling
  60's convergence re-run on the repaired c.py; ruling 67): a.py 28 lines, 798
  characters; typed 3,289 uppercase / 3,289 lowercase, 39 data lines
  (G 2,335); b.py 4,487 B; the upper long form committed as
  stage1/a_readable_upper.py; print-2026-10-23.pdf `4989446c…`
  (rebuild_v2.py --twice byte-identical). The first convergence
  (CONVERGENCE-2026-10-23.md, the c.py before the repair): 3,286 / 3,287.
- On paper, 2026-10-26: the owner typed sheets 1 and 2 of v3; a.py and the
  b.py it wrote are sha-equal to the chain's (720330aa…, 761138cd…)
  (PAPER-2026-10-26.md). Typing time not recorded.
- History, before the convergences: a.py 28 lines, 807 characters (stage1/RESULTS.md, "The typed totals",
  2026-10-21/22); 805 when c.py is the R2 content and the tuple
  (0,1,2,3,4,6) is chosen (stage3/RESULTS-2026-10-22.md §6).
- The typed total, a.py plus data glyphs plus 4 check glyphs a line, with
  the reader before the convergences (the grey padding of ruling 59 applied,
  r2reader/changeset/RESULTS-2026-10-22.md §20): 3,326 lowercase / 3,325
  uppercase on 40 data lines with the stand-in bundle; 3,319 / 3,318 on 40
  data lines with c.py as the content, at the tuple (0,1,2,3,4,6) (§20,
  part 2). Before the padding: 3,335 / 3,335 with the stand-in and the
  reader of §19 (A); 3,465 / 3,463 on 42 lines with c.py as the content
  and the reader of ruling 52, from an export of a9826d37
  (stage3/RESULTS-2026-10-22.md §6).
- On paper, 2026-10-20, the print of record: 3,895 typed (a.py 29 lines /
  826, 48 data lines) in about 40 minutes of keyboard time, every slip
  caught by the line checks (PAPER-2026-10-20.md).
- The leaves: one listing sheet and one data sheet, each with an identity
  line and the print date (ruling 44, RECORD-2026-10-20.md:1172).

Build and test (machine 1: env/bin/python, from
bootstrap/stage1/; stage1/README.md, "How to run"):

    python search.py --case lower --freeze --workers 4    # and --case upper
    python make_typed.py --case lower                     # and --case upper
    python test_identity.py --build ../build/stage1       # both cases; bare: build/sheets/stage1 (bootstrap/rebuild_v2.py's)
    python e2e.py --case lower                            # and --case upper
    python leaves.py [--paper-test]

Record: stage1/README.md, stage1/RESULTS.md; rulings 42 to 44, 51, 53 and
60 of RECORD-2026-10-20.md.

The print of record of 2026-10-20 lives beside it (v3 closed on paper on
2026-10-26; whether it becomes the print of record, and what then becomes
of loader/ and build.py, is the owner's ruling): loader/a.py, data.txt, codes.txt (the chain as printed and closed
on paper), loader/make_typed.py v3, loader/e2e_pipe.py,
loader/loader_readable.py; pages/leaf3.txt and leaf4.txt;
pages/r2/README.md and payload.json (the sidecars, payload.bin and
bundle.bin are build.py output, at tag bootstrap-pre-thinning-2026-10-23).
`python3 bootstrap/build.py` builds today's chain (today's reader under its
stage names, b.py the primer and c.py the output; the bundle of the current
R2-FORMAT.md, 4 R2 pages) into the gitignored bootstrap/build/build-py/ and
leaves the print of record as it is; `--record` would REPLACE the print of
record with that build (loader/README.md). Neither reproduces the 10-20
print: its bundle (55,550 B, 3 pages, still in bootstrap/build/bundle/)
holds R2-FORMAT.md as it was on 10-20.

## Stage 3: the R2 pages, read by b.py (bootstrap/r2reader/)

What it is: b.py, typed at stage 2 as data, reads phone photos of the R2
pages (P5 PGM; whole pages or parts, any orientation, pages mixed), pools
the chunks by global index, prints one line per file (`N@ H/T`, ruling 56
as amended, RECORD-2026-10-20.md:1546), and when the payload is complete
decodes it to c.py and checks its baked CRC-32. The page is R2-FORMAT.md
v1 as amended: 12-dot modules (0.508 mm), a timing lattice every 17th row
and column, fifteen circular-ring bullseyes in the body carrying the
68-bit header, 16×16-module blocks of 2-byte global chunk index + 26 data
bytes + CRC-32 bound to the header, three copies per chunk on a designed
placement and on different pages; 204 chunks = 5,304 B per page.

Files (live): r2reader/reader_lite_v1.py (the typed text, the source; the
search edits it), r2reader/reader_template.py, r2reader/gen_reader_long.py,
r2reader/reader_long_v1.py (the generated long form, ruling 48),
r2reader/test_reader_identity.py, r2reader/count_reader.py (the typed-subset
audit), r2reader/grid_to_pgm.py (the Plate's one-liner, ruling 49); the
page side r2/gen.py, r2/verify_grid.py, r2/camera.py, r2/damage.py,
r2/genie.py, r2/design_placement.py, r2/placement_stats.py,
r2/test_gen_v1.py, r2/xpage_e2e.py. r2reader/reader.py is the readable
lab reference and stand-in content, NOT b.py's long form (ruling 35,
RECORD-2026-10-20.md:924).

Measured:
- At both convergences (CONVERGENCE-2026-10-23.md, -23b.md): 138 counted
  lines, 3,786 characters, longest 69; N2 24176 / B2 3810813523 baked at
  the re-run's fixed point; the re-run's search winner was not taken
  (ruling (a): the upper case did not fall).
- The typed text: 138 counted lines, 3,781 characters, longest 69, with
  the grey padding of ruling 59 (changeset/RESULTS-2026-10-22.md §20,
  2026-10-23; 140 / 3,812 at §19 (A)); its long form 813 lines, identity
  test A to D PASS (§20).
- Reads identical, call for call, to the ruled text of ruling 52 on 129
  captures, through the composite, the progress line and the literal `@`
  (§17, §18, §19); with the grey padding identical call for call on 127 of
  129 captures and 191 of 199 break frames, the finder's threshold
  byte-identical on all, no chunk lost, the ten differences §19's (§20);
  acceptance sets A to I pass, set I's slot pass 170 of 172, the margin 8
  of 9, damage frames alone 16 of 16; the four phone photos of 2026-10-20
  close in both pools (§20).
- The typed reader's floor for a whole page, as measured on the 10-20 diet
  reader: 2 samples per module at blur σ 0.45, or 1.5 at σ 0.4
  (RECORD-2026-10-20.md, ruling 15's note). For the reader after the change
  set, the envelope edge at 1.5 samples per module and σ 0.40 closes in no
  text (the change-set section of RECORD-2026-10-20.md; changeset/RESULTS
  §11).
- The page: narrowest straight strip 46.30 mm at any angle, blot radius
  80 mm (ruling 19); any one page may be lost from a two-page payload on,
  any two from three (ruling 29).
- On paper, 2026-10-20: three R2 leaves photographed with a phone camera,
  two turned 90°, one in two halves; either half closes with the other two
  leaves; the output byte-identical to the bundle (PAPER-2026-10-20.md).
- On paper, 2026-10-23 and 2026-10-26: b.py read the two R2 pages of the v2
  and v3 prints from 300 dpi grey scans and wrote c.py byte-exact (typed3's
  c.py b4f7de22…; PAPER-2026-10-26.md, docs/EXPERIMENT-LOG.md).

Build and test (from the worktree root, env/bin/python):

    env/bin/python bootstrap/r2reader/count_reader.py bootstrap/r2reader/reader_lite_v1.py
    env/bin/python bootstrap/r2reader/test_reader_identity.py   # about 1 min
    env/bin/python bootstrap/r2/test_gen_v1.py                  # the generator's checks
    env/bin/python bootstrap/r2/xpage_e2e.py OUT [--seeds ... | --nearwhite]

The acceptance sets are r2reader/diet/w4_sets.py (`make`, `run NAME`,
`table`), run as the chain runs readers by r2reader/diet/w4_harness.py; the
change set's kept entry points wrap them: changeset/run_sets_cv.py,
sets_cmp_at.py, claims_cv.py (call for call; env CV_PRE/CV_CAND/CV_NAMES),
size_stage1.py (typed totals), time_pair.py, reroll_template_cv.py,
run_search_cv.py and apply_cv.py; the arms are at the tag
(bootstrap-pre-thinning-2026-10-23). When the typed text changes, the
template is re-rolled (changeset/reroll_template_cv.py), then
gen_reader_long.py, then the identity test (r2reader/NOTES.md).
w4_harness.parse and a few record instruments still read the older
progress words (§18, "Collateral edits").

Record: r2reader/NOTES.md, r2reader/changeset/RESULTS-2026-10-22.md §1 to
§20, R2-FORMAT.md; rulings 1 to 23, 29, 45 to 56, 58 and 59 of
RECORD-2026-10-20.md.

## Stage 4: the archive pages, read by c.py (bootstrap/stage3/)

What it is: c.py, written by b.py at stage 3, is a pure-Python receiver with
no imports for one holo row, c3-k-r0547-p100 at source fraction 0.5 (rulings
24 and 36; FORMAT_ID `holo/v2/1i200-k-r0547-p100-v1@35x24`). It reads
flatbed scans of the archive pages, closes the fountain volume, checks the
SHA-256, writes payload.bin, and when the payload is an `R3A1` container
decodes it with strong2 (a bounded context-mixing decoder) and unpacks the
ustar archive to flat names (stage3/README.md). The archive layer stays in
c.py as built (ruling 61, the owner, 2026-10-23); the release carrying its
own unpacker remains the release step's option (docs/TODO.md, Bootstrap).

Files (live): stage3/c_readable.py (the source of record, ruling 57,
58,868 B), stage3/c.py (generated, never edited), stage3/make_c.py,
stage3/sizes_c.py, stage3/unit_c.py, stage3/e2e_c.py,
stage3/lab/. The record it descends from: r3/receiver.py and
r3/arch/receiver_arch.py (2026-10-20).

Measured (stage3/RESULTS-2026-10-22.md §6 unless noted):
- c.py 24,176 B, 476 lines, sha256 `b4f7de22…`, CRC-32 3810813523, at the
  re-run convergence's fixed point (CONVERGENCE-2026-10-23b.md; make_c.py's
  two-cycle rule (d')): 10,130 / 10,133 B through cm2 = 2 R2 pages with
  478 / 475 B to spare, 390 chunks; T1 byte-exact at 8 / 13 scans (arch /
  arch40), page 03's six real scans 840 / 840 each.
- History: c.py 23,793 B, 460 lines, no import (stage3/README.md); 9,951 / 9,956 B
  through cm2 = 2 R2 pages with 657 / 652 B to spare under the b.py of
  a9826d37; under today's b.py 9,966 / 9,971 B, 642 / 637 B to spare
  (changeset/RESULTS-2026-10-22.md §20, part 2).
- The volume of the record's tree, made by holo's generator at the r0547
  row: 1,648,660 B, K/N 0.497, 15 pages (§3). From 1,200-dpi simulated
  scans pooled in shuffled order, c.py restores 321 of 321 files
  byte-exact: 8 pages to close, 1,141 s; with 40 % of every page's tiles
  blanked, 13 pages, 1,382 s. holo's own receiver VERIFIED the same volume
  (§3, 6,262 certificates).
- On paper, 2026-10-26: from 600 dpi grey pixma scans of the printed pages
  c.py closed the volume on the first eight (840/832, 840/840, 840/806,
  840/774, 839/802, 840/829, 840/840, 839/541 placed / certified; 6,264
  symbols of 6,260, page 8 decoded only until the count was met), every
  page `turn 180`, the dpi fallback firing once, a page fed twice changing
  nothing; payload.bin sha-equal to the container, 321 files unpacked
  (PAPER-2026-10-26.md). 300 dpi cannot read this row (1.5 px per cell).
- Per scanned page about 3 s to find the lattice, 4 s to place, 31 s to
  decode; the archive decode about 13 minutes and 1.4 GB on T1
  (stage3/README.md).
- With c.py as the R2 content the stage1/ chain (stages 1 and 2) passes end
  to end in both cases (§6).

Build and test (from the worktree root; stage3/README.md has the full
list):

    env/bin/python bootstrap/stage3/make_c.py [--workers 6]   # about 8 to 11 min
    env/bin/python bootstrap/stage3/make_c.py --provenance    # seconds
    env/bin/python bootstrap/stage3/unit_c.py                 # scan-free checks
    PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py volume
    PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py scans arch arch40
    env/bin/python bootstrap/stage3/e2e_c.py run arch bootstrap/stage3/c.py T1_c_arch
    env/bin/python bootstrap/stage1/chain_v2.py make lower --out DIR   # and e2e, pages, identity; rebuild_v2.py runs it

Record: stage3/README.md, stage3/RESULTS-2026-10-22.md, r3/README.md,
r3/arch/README.md, r3/AGING-2026-10-20.md; rulings 24 to 28, 36, 37, 57 and
61 to 68 of RECORD-2026-10-20.md. The deep review of c_readable.py as a
distillation of holo's K receiver closed 2026-10-23 (7b7c17f0,
stage3/review/); its gaps ruled (ruling 63) and repaired (8affb97b,
da0cd032).

## The release (what stage 4 yields)

What it is: the paper-store tree that c.py restores, which "then magically
has all imports available" (ruling 40, RECORD-2026-10-20.md:970); holo3
needs numpy, scipy, pillow and cryptography, which the tree does not carry
(same ruling). The tree itself is to be ruled; for now think paper/src
(ruling 41). The release moves independently of the frozen bootstrap: its
volume hash is to go into stage 0 as printed text (ruling 39, a decision;
the Plate is deferred and no leaf carries it yet) and nothing of it is
baked into stages 1 to 3 (same ruling).

The record's tree T1 = `src/holo/**/*.py` + `docs/**/*.md` (not
docs/archive/) + CLAUDE.md at commit 2115a595, 321 files, 9.28 MB, packed
to 1,648,648 B by strong2 = 15 archive pages (ruling 28); bootstrap/
itself is not in it (ruling 41). At HEAD 4a4b2f4d 67 files of that
selection differ (37 modified, 30 added). Printed and read on paper
2026-10-26 (above). Build: `stage3/e2e_c.py volume` makes the volume with
holo's generator.

THE GAPS, found on paper 2026-10-26 (FINDINGS.md §16): NEW, the selection
takes no non-.py file under src/holo, so the twelve LDPC code tables (JSON)
are missing and the archived holo3 dies at import; NEW, c.py writes flat
names and nothing on the sheets or in the archive restores the tree; KNOWN
(ruling 40: holo3's imports are not in the tree) and met in practice on
10-26, the archive carries no requirements file; the receiver's normative docs (src/holo/receiver/docs/) are not
in it. The fix is a selection law for the release tree plus a requirements
file inside the archive: a new container and new stage-4 pages, stages 1-3
untouched (ruling 39). The selection is the owner's ruling (docs/TODO.md).

## The records

Files named by the dated records and absent from the tree are at tag
bootstrap-pre-thinning-2026-10-23 (b149721d): `git show
bootstrap-pre-thinning-2026-10-23:PATH`. The thinning of 2026-10-23 and
its full cut list: ARCHIVE-INDEX-2026-10-23.md. The control rebuild on an
empty build/: CONTROL-REBUILD-2026-10-23.md.

- RECORD.md: the index of rulings, one line each.
- RECORD-2026-10-18.md: the 10-18 panels' measured record and its six
  rulings (this was RECORD.md until 2026-10-23).
- RECORD-2026-10-19.md: rulings 1 to 15 of 10-19, the stopwatch, the
  rejected explorations, the outside reader's feedback.
- RECORD-2026-10-20.md: rulings 1 to 68 (2026-10-20 to 10-26) with their
  reasons and the dated sections.
- REVIEW-2026-10-18.md, REVIEW-2026-10-19.md, REVIEW-2026-10-20.md: every
  builder, refuter and checker report verbatim.
- PAPER-2026-10-20.md and experiments/047-bootstrap-typed-rung-first-paper-close.md:
  the first close on paper (stages 1-3, a stand-in content).
- PAPER-2026-10-26.md: the first complete close on paper (stages 1-4, v3),
  with every file's sha256; docs/EXPERIMENT-LOG.md: every physical run,
  one line each.
- CONVERGENCE-2026-10-23.md (superseded) and CONVERGENCE-2026-10-23b.md:
  the two convergences; CONTROL-REBUILD-2026-10-23.md: the control
  rebuild.
- FINDINGS.md: what the week measured, one section per finding.
- TYPED-STREAM.md (v3) and R2-FORMAT.md (v1, amended): the two specs.
- loader/: the print of record's chain (the 29-line a.py, its encoder
  and e2e; the refuters at the tag).
- record-2026-10-18/: the stage-0 panel records and size extracts, the
  three test texts, the cm1 and cmmix codecs, T4's derivation scripts.
- typed/: cm2 v2's decoder, encoder and known answers; the 10-18 checker,
  typist and finder simulation.
- r2/: the R2 page generator, camera simulator and placement design.
- r3/: the 2026-10-20 R3 monolith round, its archival layer and the ageing
  survey.
- priorart/: the survey records and the Crinkler (crk_*) and ZPAQ (zp_*)
  ports (ruling 31).
- compressor-exploration/: the owner's parallel cloud session on cm2,
  cmmix and strong2 (rulings 32 and 33): the records (ASSESSMENT, LEVERS,
  four RESULTS); harness/cm2lab.py (used by stage1/search.py) and
  encoder-side/mono_final.py (used by stage3/sizes_c.py) stay; the labs
  are at the tag.
- r2reader/diet/: the 2026-10-20 ablation ladder's records and the
  acceptance harness (w4_sets, w4_harness, w4_ladder, w4_slots, w4_debug,
  w4_one, w4_env for the envelope frames, w4_lastpage as the provenance of
  set I's last page -- it reproduces it only with r2/gen.py at 1d309208 and
  run at HEAD overwrites the frozen build/w4/p2f4 --, build_rungs_v1.py); the rung copies at the tag (build_rungs_v1.py
  starts from the gitignored v1/r00_base.py, so it does not regenerate
  them on a clean checkout).
- r2reader/axes/: the unread up-left blocks traced to two one-sided
  tie-breaks (2026-10-22): the records and the up-left-bug instrument
  (instrument.py runs against git b544669e's reader; instrument_arms.py
  takes any text; run_all.py; measure.py, the paired driver, with the
  three fix arms its default reader set names, fix0, fix2 and fix2b);
  fix2s, the probe and run_arms at the tag.
- r2reader/ideation/: the 2026-10-22 ideation records (IDEAS,
  DIVERGENCE-d06, qr/README); the variants at the tag.
- r2reader/changeset/: the change set's record (RESULTS §1 to §20) and its
  instruments (the *_cv entry points and their layers, rw/;
  run_search_nod.py and run_search_both.py with the edit lists they
  search, reader_nod_edits.py and reader_edits_both.py: the name maps of
  one_bull.py's two arms).
- format-round/: three bullseye variants in two renderings, measured and not
  adopted (ruling 55; 2026-10-22): the records, gen/gen_variant.py +
  gen/verify_variant.py, gen/bullseye_profiles.py (the MEASURED profiles of
  its README), the measure/ harness and the three reader ports it opens (reader/reader_v1_rw.py, reader_v2_rw.py, reader_v3_rw.py); the
  rest of reader/ at the tag.
- pages/: OCR-2026-10-21.md (the data leaf's face and alphabet by OCR), the
  leaf composer and renderer, the leaves of record.
- stage3/review/: the deep review of c_readable.py (2026-10-23, closed; ruling 63).

## Compressor shelf

One entry per codec family measured this week, kept in place beside its
record (no file moved, no header added: every primed size was taken with
the decoder file itself in the primer). Sizes are as the records state
them; where a family was not measured on the three test texts, the
figure the record has is given instead.

Test texts (record-2026-10-18/fixtures/): T1_8k.py, T2_16k.py, T3_32k.txt,
primer.txt (the primer of every primed row).
Benchmark driver: r3/arch/bench.py (unedited; every dec_/enc_ unz() pair
in r3/arch: strong, strong2, the cm1k24 and cmmix twins, the seven cm2
pairs gen_cm2fam.py writes; TREE may be a path, e.g. a fixture file).

- cm1: record-2026-10-18/cm1/cm1_dec.py, record-2026-10-18/cm1/cm1_enc.py.
  Run: `python cm1_enc.py [cm1_dec.py] IN OUT [PRIMER] [k]`.
  cm1 (2026-10-18): cmmix model family with bounded, checked tables (orders
  0-4, 7-byte ctx, word, line-above, match; three integer logistic mixers;
  carry-less 32-bit coder); decode(src, n, primer, k), k = table bits; --kav
  self-test. Unprimed k=22: T1_8k 2,792 B, T3_32k 6,896 B, T2_16k not
  measured, T4 112,999 B (cm1/NOTES.md, results.jsonl). Primed (primer.txt +
  the decoder file): T1 2,504, T3 6,556 (NOTES.md:42). Arch twin k=24:
  r3/arch/dec_cm1k24.py, r3/arch/enc_cm1k24.py (`python
  bootstrap/r3/arch/bench.py cm1k24 T1|T2|PATH`): T1.tar 1,738,544 B
  (r3/arch/README.md:267).
- cmmix: record-2026-10-18/stage0-panel/cand/cmmix/dec.py,
  record-2026-10-18/stage0-panel/cand/cmmix/enc.py.
  Run, from that directory: `python enc.py [dec.py] IN OUT [PRIMER]`
  (default decoder: dec.py in the cwd, enc.py:52).
  cmmix (2026-10-18 stage-0 panel, 60-line budget): bitwise CM over orders
  0-4, hashed order 7, identifier, line-above and match contexts, three
  integer logistic mixers, carry-less 32-bit coder; decode(src, n, primer).
  Unprimed T1_8k 2,799 / T2_16k 4,513 / T3_32k 6,950 B (T4 114,762); primed
  2,542 / 4,203 / 6,629 (T4 114,177) (cand/cmmix/results.json;
  STAGE0-DECOMPRESSOR-MEMO.md:30). Arch twin: r3/arch/dec_cmmix.py,
  r3/arch/enc_cmmix.py (`python bootstrap/r3/arch/bench.py cmmix T1`):
  T1.tar 1,785,845 B (r3/arch/README.md:268).
- cm2 v1 (2026-10-18 range coder): typed/cm2_v1_dec.py, typed/cm2_v1_enc.py.
  Run: `python typed/cm2_v1_enc.py typed/cm2_v1_dec.py IN OUT [PRIMER...]`.
  cm2 v1: PAQ1-style count mixing, exact-key orders (0,1,2,3,4,6,8,12),
  lpaq1 carry-less coder; decode(s, n, primer). Unprimed T1_8k 2,884 /
  T2_16k 4,676 / T3_32k 7,257 B (T4 119,866); primed 2,633 / 4,372 / 6,914
  (T4 119,211) (stage0-panel/cand/cm2/NOTES.md:33, results.json; that copy
  is byte-identical to this file).
- cm2 v2 (2026-10-20 big-integer rANS; the chain decoder): typed/cm2_dec.py,
  typed/cm2_enc.py, typed/kat_v2.json.
  Run: `python typed/cm2_enc.py typed/cm2_dec.py IN OUT [PRIMER...]`.
  cm2 v2: cm2 counts with one big-integer rANS state (no clamp, window or
  renormalisation); the order tuple is data (stage1/template.py carries the
  same d). Not measured on the three test texts. Reader payload P1 1,292 B,
  bundle P2 4,855 B (typed/measure_v2-result.json, coder); decode quadratic
  in n.
- cm2 arch family (the cm2 row of the archive-codec table): the generator
  r3/arch/gen_cm2fam.py and r3/arch/derive_cm2.py (its encoders' import).
  Run: `python bootstrap/r3/arch/gen_cm2fam.py` writes the seven
  dec_cm2*/enc_cm2* pairs ({x,h}{rc,rans,blk} and xrc1) into r3/arch/,
  untracked (the tracked copies are at the tag), then `python
  bootstrap/r3/arch/bench.py cm2xrc T1`. cm2 orders, exact dict, range
  coder: T1.tar 1,761,165 B, 16 archive pages, 8.7 min, 25 GB growing with
  n (r3/arch/README.md:269).
- strong: r3/arch/dec_strong.py, r3/arch/enc_strong.py.
  Run: `python bootstrap/r3/arch/bench.py strong T1|T2|PATH`.
  strong (arch candidate D): cm1 + word bigram + two APM/SSE stages, k=24,
  unz(z). Not measured on the three test texts. T1.tar 1,705,470 B, 16
  archive pages, 12.6 min (r3/arch/README.md:266).
- strong2 (the archive codec of record): r3/arch/dec_strong2.py,
  r3/arch/enc_strong2.py, r3/arch/derive.py.
  Run: `python bootstrap/r3/arch/bench.py strong2 T1|T2|PATH`.
  strong2 (D2): strong + match-length/order-2 weight-set selection, k=28,
  ~0.9 GB tables; its region is embedded in r3/arch/receiver_arch.py
  (provenance). Not measured on the three test texts. T1.tar 1,648,648 B, 15
  archive pages, 13.1 min, 1.36 GB (r3/arch/README.md:265).
- Crinkler port: priorart/crinkler/crk_dec.py, priorart/crinkler/crk_enc.py.
  Run: `python bootstrap/priorart/crinkler/crk_enc.py ... (numpy)`.
  Faithful Python transliteration of Crinkler 4k/1k (ALTERED VERSION, zlib
  licence text in priorart/crinkler/README.md, which stays beside it). Not
  measured on the three test texts. Typed payload 1,745 B at SLOW; 1 MB of
  T1 270,864 B vs strong2 245,555 (priorart/crinkler/README.md:111-112,
  315-324).
- Crinkler, the crkpy member: priorart/crinkler/dec_crkpy.py,
  priorart/crinkler/enc_crkpy.py, priorart/crinkler/fam.py.
  Run: `m, _ = enc_crkpy.search(data[:65536], rule='crksat',
  subsets=enc_crkpy.SUB8); z = enc_crkpy.compress(data, m)` (the crkpy-sat8
  set of the headline; enc() with its defaults searches rule 'crk' over
  SUB24 and gives another size; no CLI; numpy); dec_crkpy defines unz(z) in
  the r3/arch harness's shape. The record's T1 driver, bench_arch.py with
  common.py, is at the tag.
  Crinkler's 4k model optimised for Python (ALTERED VERSION, the same
  licence). Not measured on the three test texts. T1.tar 1,918,411 B with
  the best model set found (+16.4 % over strong2), 18 archive pages;
  67-92 µs/byte in 520-540 MB (priorart/crinkler/README.md:76-86).
- ZPAQ port: priorart/zpaq/zp_dec.py, priorart/zpaq/zp_enc.py,
  priorart/zpaq/zp_configs.py.
  Run: `zp_enc.compress(data, row) (no CLI)`.
  Pure-Python ZPAQ level-2 block decoder and encoder (from libzpaq 7.15,
  public domain). Not measured on the three test texts. T1.tar max.cfg
  1,629,544 B, ours3 1,582,375 B (-4.0 % vs strong2), 15 pages; +1 R2 page
  in the monolith (priorart/zpaq/README.md:20-37, 161-167).
- bwt (2026-10-18 stage-0 panel): record-2026-10-18/stage0-panel/cand/bwt/
  dec.py and enc.py. Run, from that directory: `python enc.py IN OUT
  [PRIMER...]`, `python dec.py COMPRESSED OUT N [PRIMER...]`.
  BWT with direct binary CM on its output (3-input logistic mixer,
  recent-symbol match), carry-less 32-bit coder, 39 lines. Unprimed T1_8k
  3,146 / T2_16k 5,186 / T3_32k 8,204 B (T4 135,179); primed 3,121 / 5,152
  / 8,188 (cand/bwt/results.json, NOTES.md). dec_mtf and dec_tiny at the
  tag.
- ppm (the same panel): cand/ppm/dec.py and enc.py. Run, from that
  directory: `python enc.py IN OUT [PRIMER...]` (--d32 serves dec32.py, at
  the tag). PPM over orders 6..0, exact-context dict, full and update
  exclusion, 64-bit multi-symbol range coder, 25 lines. Unprimed 3,092 /
  4,989 / 7,810 (T4 143,879); primed 2,896 / 4,768 / 7,574 (T4 143,711)
  (cand/ppm/results.json, NOTES.md:27).
- lzdict (the same panel): cand/lzdict/dec.py and enc.py. Run, from that
  directory: `python enc.py IN OUT [PRIMER...]`. LZ77 over a primed
  window, Elias-gamma integer trees, LZMA-style binary range coder, an
  optimal parse, 20 lines. Unprimed 3,263 / 5,400 / 8,545 (T4 152,459);
  primed 3,098 / 5,205 / 8,299 (T4 151,835) (cand/lzdict/results.json).
  dec_raw at the tag.

## Open

Every open thread of the chain is one line in docs/TODO.md, section
Bootstrap, with its pointer (since 2026-10-26; the list that stood here is
in git at d60ec72b).

## Next actions (a possible set, 2026-10-26)

Not ruled, not ordered beyond what the pointers say:

- **The release tree** (FINDINGS.md §16; docs/TODO.md, Bootstrap, stage 4):
  the owner's ruling on the selection law, ruling 41 in full
  (RECORD-2026-10-20.md:978-982): "The tree is "the paper-store / holo
  release", to be ruled eventually; for now think paper/src, "but it will
  be more" (the readable sources of stages 1–3 do not travel in T1 today:
  bootstrap/ is not in it). Speculation recorded as such: a stage 4 in
  cmy8-r0850x0775x0700 to carry a lot more data." Three choices: all
  tracked files under src/holo (ESTIMATE ~26 pages), src/holo plus its data
  directories (ESTIMATE 16 pages), or all of src/ (438 files, 15.1 MB at
  2115a595, not sized); and a requirements file inside the archive; then
  trees.py, the strong2 size and page count, the simulated round trip, the
  new stage-4 pages from a current commit, and a print on his go. Stages
  1-3 do not move. The flat-name question and the self-unpacker (ruling
  61's option) are priced with it.
- **The whole-file check code for a.py**: deferred by ruling 68; folded
  into the next regeneration round.
- **The nine-page note**: at 600 dpi seven whole pages certify 5,723 of
  6,260, so the volume needs 8 pages at the mean and 9 at the worst page's
  rate (PAPER-2026-10-26.md); the Plate's "600 dpi or more" sentence with
  it.
- **The strip-adjacent tile**: locate the unplaced tile of d-05 and d-08
  (839 / 840) from the existing scans in scratch/typed3/, a c.py or holo3
  diag, on the owner's go.
- **The cold_rest receiver thread**: page-edge windows that hold the
  holo3 harvest's tail (docs/TODO.md, Receiver (holo3)).
- **The record habit**: every print or scan one dated line in
  docs/EXPERIMENT-LOG.md (engine, what, file, sha256); the routes of the
  10-20 and 10-26 prints asked once.
- **The evidence run**: scratch/typed3/ is on docs/evidence-archive/NEXT-RUN.md
  (the only paper evidence of the full close), beside typed/ and typed2/.
- **The merge to main**, on the owner's go: main has moved (370a1d68,
  CLAUDE.md), so CLAUDE.md meets once more; then the push.
