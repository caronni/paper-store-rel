# CONTROL-REBUILD-2026-10-23 — the chain rebuilt from the master objects on an empty build/

*2026-10-26: §4's gaps 1-3 were closed by 47dfbab5 and 5a884cee (R2_PAGES_BOUND = 3; T1 from the blobs of 2115a595; build.py --record opt-in), gap 4 in part (font sha256 in MANIFEST.txt); §4.5's six refuter scripts and the libzpaq clone are gone from /tmp (lost). Live list: docs/TODO.md, Bootstrap.*

A control, run 2026-10-23 15:47–16:20 on machine 1 (<host>, 10 cores,
64 GB) in a fresh worktree (`<worktree>
branch `claude/control-rebuild-820837` cut from `ccr-200d7187-roznny` at
01b66196, the thinning commit) whose `bootstrap/build/` did not exist at the
start. The question, the owner's: does the complete chain regenerate the
19-page candidate print of record v2 from the committed master objects
alone; is every stage's long form present or generable and correct; and are
the compressor experiments the records cite still around and runnable.
Interpreter `env/bin/python` = CPython 3.14.8
free-threading (GIL off), numpy 2.5.2, scipy 1.18.1, pillow 12.3.0,
python_minifier 3.4.0; ghostscript 10.08.0. The lead's worktree
(`<worktree> same HEAD) was read for COMPARISON only
(its `build/sheets/{MANIFEST.txt,SHA256SUMS}`, `build/stage3/e2e/T1/vol`,
`build/r3/arch/e2e_arch/T1/`); nothing was written there and no byte of
it was copied into this build. Walls are single runs under whatever else
the machine was doing (two other heavy jobs for part of the time); none is
a measurement of the chain. Nothing printed, nothing promoted.

## The three verdicts

1. **The chain regenerates the print of record v2 byte for byte from the
   master objects** — `print-2026-10-23.pdf` sha256
   `1d6a76977ddf413401d08bfa0e33eb2eac94ed7fd25af4ffda3bc5f90e80fcca`,
   19 pages, 29,076,189 B, and every other PDF, preview, a.py, data.txt,
   b.py and R2 page identical to the lead's — **but not by
   `rebuild_v2.py` alone**: on the empty build/ it stops at its first
   step, and two build/ inputs had to be made first. (a) `build/r2/
   payload.json`, read by `stage1/make_typed.py` for ONE integer, the R2
   page bound; `bootstrap/build.py` writes it (and rewrites seven tracked
   files of the 10-20 print of record with different content, restored
   here, not committed). Today that integer is 4, where the lead's run and
   the tracked `pages/r2/payload.json` say 3; the bound reaches only the
   text "(record N)" / "(bound N)" of codes.txt, sizes.txt and
   MANIFEST.txt, nothing printed. (b) The stage-4 volume's input, the
   record's T1 container (`build/r3/arch/e2e_arch/T1/container.bin`,
   78d9a4b4…), which `stage3/e2e_c.py` COPIES from a build/ record
   directory an empty build/ does not have — **regenerated here from
   master objects**: the tar from the git blobs of commit 2115a595
   (byte-identical, d1aaf1dd…), the container by the encoder derived from
   `r3/arch/receiver_arch.py` at HEAD (byte-identical, 774 s). So the
   chain is self-contained in git plus one 13-minute encode; what is
   missing is the script that says so (§4).
2. **Every long form is present or generable and correct.** a.py:
   `gen_readable.py` + `test_identity.py` PASS both cases (bare and on
   the rebuild); b.py: `reader_long_v1.py` is `gen_reader_long.py`'s
   output byte for byte, `test_reader_identity.py` A–D PASS; c.py:
   `make_c.py --provenance` PASS (6 hunks), `make_c.py --workers 6`
   regenerates the committed `stage3/c.py` byte for byte (92c48a39…,
   472 s), `unit_c.py` ALL OK; `r2/test_gen_v1.py` 80 of 80.
3. **Every member of the compressor shelf runs today and round-trips
   byte-exact on T1_8k.py and T3_32k.txt**; every cited size reproduces,
   except cm1 primed T1 (2,501 against 2,504), which git explains: the
   decoder text, half of the primer, was reformatted in 3cd56e52 after the
   measurement (§3.1). The records' instruments: of about
   143 cited experiment rows, about 19 have every instrument at HEAD,
   about 94 need at least one instrument that is at the tag only, and
   about 30 cite an instrument that is in neither place (cloud-container
   scratch paths, third-party binaries, unnamed in-memory probes) — and
   six of those "neither" scripts plus a libzpaq clone are on machine 1's
   /tmp right now and nowhere in git (§3.2).

## 1. The complete chain from the master objects

### 1.1 `rebuild_v2.py` on the empty build/ (15:47:58)

    env/bin/python bootstrap/rebuild_v2.py

Exit 1 after 0.12 s at step `make-lower` (quoted from the terminal; the
step log `build/sheets/logs/make-lower.out` was overwritten by run 1):

    File "bootstrap/stage1/make_typed.py", line 559, in main
        pages_max = r2_pages_of_record()
    File "bootstrap/stage1/make_typed.py", line 466, in r2_pages_of_record
        return json.load(open(R2_RECORD))['pages']
    FileNotFoundError: [Errno 2] No such file or directory: '.../bootstrap/build/r2/payload.json'

That is the only build/ input of steps 1 and 2 (make, pages); step 3
(sheets) needs the volume of §1.3–1.4. `make_typed.py` uses the file for
one value, `['pages']`, the page bound of its frontier (make_typed.py:70,
466, 473–489): among the order tuples of `template.FRONTIER` it takes the
lowest typed total whose R2 payload keeps `r2_pages <= pages_max`.

### 1.2 `bootstrap/build.py`, the 10-20 print's pipeline (15:49:27, 153 s wall, 2.08 GB, exit 1)

Run as the only producer of `build/r2/payload.json`, knowing it rewrites
tracked files (build.py's docstring; ARCHIVE-INDEX "build.py rewrites
tracked files when run"). Default reader `r2reader/reader_lite_v1.py` =
today's typed reader (writes c.py, ruling 34 and the 10-22 change set);
the bundle = R2-FORMAT.md as a docstring + `r2reader/reader.py`, the
stand-in content.

| stage | result |
|---|---|
| 1 reader audit | lines 138, chars 3,786, longest 69, N2 tokens 1, writes c.py |
| 2 bundle | build/bundle/b.py 60,242 B sha b45c28c9… (R2-FORMAT.md 29,995 + reader.py 30,240 + 7) |
| 3 typed + sizes | a.py 29 lines / 826 chars; data 41 lines / 2,567; typed 3,393; r.py 4,503 B; reader N 3,934, code 1mk3, orders (0,1,2,3,4,6,8,12,16); equivalence PASS |
| 4 pages | **payload 17,175 B on 4 pages** (capacity 21,216, headroom 4,041), chunks 661, verify_grid PASS → `build/r2/payload.json` **pages 4** (the file's sha 11466973…; its `payload_sha256` field, the 17,175-B payload.bin, da4f70d5…) |
| 5 renders | 113 captures, 7 s |
| 6 reads | **0 of 22 whole-page sets closed**: the reader held 661/661 chunks on every one and wrote c.py; build.py looks for b.py. "b.py as a reader" rc 1, `NameError: name 'N2' is not defined` (the stand-in reader.py has no N2) |
| 7 e2e | 16 PASS, 8 FAIL — the same cause (b.py expected; the reader's progress 'file: 15@ 661/661' is read); 7b typed chain: a.py rc 0, self-dump == codes, r.py == build/loader/r.py, pages 'done', **b.py absent → NOT CLOSED**; CRLF negative FAIL (FileNotFoundError b.py) |
| 8 leaves, 9 records + sums | ran; 250 files in build/SHA256SUMS |

So build.py at HEAD runs through but FAILS its own closing checks, as the
README says ("its default reader no longer closes the print of record's
build"), and it still writes every build/ product the other tests read
(payload.json, bundle/b.py, loader/r.py, readers.json, the r2 frames).

**The tracked-file rewrites (not committed).** `git status` after the run:
7 tracked files modified, 23 untracked files under `pages/r2/`. Every one of
the seven differs from HEAD:

| file | HEAD sha256 | after build.py | what moved |
|---|---|---|---|
| loader/a.py | 70f51b9e3b7cff29… | 1331e8fb23bfaf5d… | `while n<49` → `<42`; `d(v,4564,a)` → `d(v,3934,a)`; `'y98y'` → `'1mk3'` |
| loader/data.txt | 2ab3226c44d1aa98… | 76d76a774c1e2bbe… | 48 → 41 data lines (today's reader, 3,934 B) |
| loader/codes.txt | f690e65407fd4d57… | 7e2dea3c24f59ee7… | the codes of the above |
| loader/loader_readable.py | b795d78132211163… | 11a7f1a0b305cee0… | the baked constants |
| pages/leaf3.txt, leaf4.txt | d76dfc651f13cbb1…, 09aa3618ccfb2d75… | 170dae520a0a49e6…, 008f3043b79b7664… | the leaves of today's chain |
| pages/r2/payload.json | aca2b468d77322a3… (pages 3, payload 14,472 B, bundle 50,533 B) | 1146697317b72416… (pages 4, 17,175 B, bundle 60,242 B) | the record of the pages |

The diff (387 lines) and the untracked list are kept in this session's
scratch; the tree was restored with `git checkout -- bootstrap/loader
bootstrap/pages` and `git clean -f -- bootstrap/pages/r2`, and
`git status` was clean before every later step. FINDING: build.py at HEAD
does NOT regenerate the print of record of 2026-10-20 — `loader/a.py`,
`data.txt`, `codes.txt` at HEAD are that day's reader's (N 4,564, 48 data
lines, code y98y; last changed in d84a9637), kept as fixtures by the
owner's amendment 1 of the thinning — and the page bound it hands
`make_typed.py` is whatever the stand-in bundle costs on the day it runs:
3 on 10-20 (bundle 50,533 B), 3 in the lead's later run (55,550 B), **4
today** (60,242 B). What grew is R2-FORMAT.md, the bundle's docstring —
20,286 → 25,303 → 29,995 B — while `reader.py` is 30,240 B throughout
(each bundle = R2-FORMAT.md + 30,240 + 7). The bound is not a committed
constant, and it is read for nothing but the frontier's gate and the
"(record N)" text (make_typed.py:489, 521, 530; the chosen tuple needs 2
pages, so the gate never bound here).

### 1.3 The stage-4 volume's input: the record's T1 container, REGENERATED

`stage3/e2e_c.py` (lines 39, 44–45, 55–62) copies `build/r3/arch/e2e_arch/
T1/{container.bin, T1.tar}` into `build/stage3/e2e/T1/` and asserts sha256
78d9a4b4… / d1aaf1dd…; an empty build/ has neither. How they were made
(r3/arch/README.md "The container", arch_pack.py, trees.py, RECORD ruling
28): T1 = `src/holo/**/*.py` + `docs/**/*.md` without `docs/archive/` +
`CLAUDE.md` from `git ls-files`, sorted; ustar, regular files only, mode
0644, mtime 0, uid/gid 0, empty names, padded to 10,240 (`trees.make_tar`);
container = `R3A1` + 8-byte length + CRC-32 of the tar + the strong2 coder's
bytes, the encoder derived mechanically from `receiver_arch.py`'s own
decoder text (`arch_pack.arch_encoder` → `derive.make_encoder`). The lead's
`container.json`: `tar_identical_to_builders` true, `coder_source
build/r3/arch/coded/strong2.T1.tar.z` (the measuring builder's encode,
`--reuse`), written 2026-10-20 16:53.

**Is it regenerable at HEAD?** `trees.pick('T1', trees.tracked())` at HEAD
selects the same 321 paths as the tar, and 318 of them are byte-identical;
three differ in content: `CLAUDE.md`, `docs/BOOTSTRAP-DESIGN.md`,
`docs/REASONING-LOG.md` (the "three of its 321 files have changed" of
stage3/README.md). All 321 blobs match the tree at commits d84a9637
(2026-10-20 06:42) through 2115a595 (17:55, the archival-layer commit of
ruling 28) — five commits. So `trees.py` cannot remake the tar from the
WORKING TREE at HEAD (ARCHIVE-INDEX, "trees.py cannot remake that tar at
HEAD"), but git can:

    # scratch regen_t1_container.py: trees.make_tar's construction over
    # `git show 2115a595:PATH` for trees.pick('T1', ls-tree 2115a595),
    # then arch_pack.coder_bytes(tar) with the encoder derived from
    # r3/arch/receiver_arch.py at HEAD; written under build/r3/arch/e2e_arch/T1/
    files at 2115a595 321
    tar 9523200 B sha256 d1aaf1ddd2c1007fefa315320eeef570c1e4677f24f070f8af4d9be191785846 MATCH
    container 1648660 B sha256 78d9a4b461923351ec0aa3bfd670104cb6c2def1e207a5db813fa4110c90168e MATCH encode_s 773.9

778 s wall (769.8 s user), max RSS 1,463,631,872 B (the 1.4 GB tables).
The encoder derived at HEAD reproduces the measuring builder's bytes
exactly, as the record claimed for its own re-encode ("Encoder determinism
and neutrality"). **The container is therefore a function of master
objects in git — the 321 blobs of 2115a595 and `receiver_arch.py` — plus 13
minutes; no bytes were imported from the lead's worktree.** What the tree
lacks is the recipe: the commit is named nowhere, and `e2e_c.py` knows only
the shas (§4, gap 2).

### 1.4 The volume (16:02:26, 11.9 s, 381 MB)

    PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py volume

15 pages of `c3-k-r0547@35x24` (A4-6mm; FORMAT_ID
`holo/v2/1i200-k-r0547-p100-v1@35x24`), each page's gs bitcmyk K plane
`field_identical` true, `ink_outside_field` 0. `build/stage3/e2e/T1/vol` =
46 files (manifest.json + 15 × {.ps, .k.npy, _gt.npy}), **all 46
byte-identical to the lead's vol**; ps shas p0 f1ec571bd9a4 … p14
f956e20a4e81 as the MANIFEST lists them.

### 1.5 `rebuild_v2.py`, run 1 (16:03:13–16:04:45, 92.3 s wall, 87.5 s user, exit 0)

Inputs: the seven texts at HEAD, `build/r2/payload.json` from build.py
(pages 4), the regenerated volume. Steps (`build/sheets/logs/`):

| step | result |
|---|---|
| make-lower / make-upper | b.py 4,486 B = a[39:591] + reader 3,934; R2 payload 9,944 / 9,947 B, 2 pages (record 4); orders (0,1,2,3,4,6); N 3934, C 39, G 2332 / 2333, codes ernd / ERND; a.py 28 lines / 798 chars; typed 3,286 / 3,287 |
| pages-lower / pages-upper | gen_rc 0, verify_grid PASS, chunks 383 [204, 179], capacity 10,608 |
| sheets | stages 1–2 sheet, 2 R2 pages, 15 archive pages (payload 1,648,660 B sha 78d9a4b4…, k_total 6,260, 12,600 symbols); every 1-bit page round-tripped through ghostscript pixel-exact (R2 2, archive 15, chain 17 of 19, print 17 of 19); QR inputs: qr-a 826 B == a.py (upper); qr-d 2,606 B == the data lines of data.txt (upper) AS PRINTED (print_sheets.py:97–100 `data_lines()`: the 39 lines with two spaces before each check, +78 B over the 2,528-B file; sha 5c10ee99…). The MANIFEST's "zxingcpp 3.1.1: … equal to the input" is the stored `decode` field of the committed stage1/qr/qr.json (print_sheets.py:107, 447), not a read-back performed here — zxingcpp is not installed in env/ and rebuild_v2.py does not run stage1/qr/make_qr.py |

**Against the lead's reference** (`build/sheets/SHA256SUMS`, 55 lines):
50 identical, 5 differ — `MANIFEST.txt`, `stage1/{lower,upper}/codes.txt`,
`stage1/{lower,upper}/sizes.txt` — and those differ only in the text
"(record 4)" / "(bound 4)" against "(record 3)" / "(bound 3)": one line in
each codes.txt (line 33) and sizes.txt (line 5), two lines in MANIFEST.txt
(40 and 42, the lower and the upper case) — diffed file by file against
the lead's. Identical: every PDF, every preview, a.py, data.txt, b.py,
readable.py, leaf3/4.txt, leaves.pdf, every pbm and grid.txt, both
payload.bin. (Counts corrected after the refutation pass: the record first
said 56 lines and 51 of 56.)

| file | sha256 | pages | bytes |
|---|---|---|---|
| print-2026-10-23.pdf | 1d6a76977ddf413401d08bfa0e33eb2eac94ed7fd25af4ffda3bc5f90e80fcca | 19 (gs pdfpagecount) | 29,076,189 |
| chain-2026-10-23.pdf | e13dac6bad829b0feefb856fb23bc57d3977144a4ab254b54e4857405c56dc55 | 19 | 27,132,599 |
| stage4-archive-pages.pdf | 40272f41191b25ab60dd026ecc4bf19d7317a253fbd5637285c24b66ee725483 | 15 | 23,399,536 |
| stage3-r2-pages.pdf | dcaf5310ac7e6b211bb2324650f896c6a538c2c0b074cecedf85ec02ae582bac | 2 | 475,726 |
| stages1-2-listing-data-upper.pdf | 1172e2c93006111e19797cff9a55c2f9db173db40615f0ff342e0547f6cfbc3c | 2 | 1,393,693 |
| a.py (upper) | c38c70a7deec94e4799f29c277624b687a161be0ca11381ab0ef25d6d90416b2 | | 826 |
| b.py (upper) | 808378e3cc126acb31309610aba543ad66247de314bb2f33e6e399bc37838819 | | 4,486 |
| a.py (lower) / b.py (lower) | ddb3b9947476cbad… / b86502fb230bef55… | | 826 / 4,486 |
| stage3/c.py (the tree's, the R2 content) | 92c48a39f9eb115908921c5bdbe060ec8987903abaa4f0ef6efbfbfbfb30d3b7 | | 24,080 |

`chain_v2.py identity lower|upper --out build/sheets/stage1` (16:06:02,
2.0 s each): PASS mechanical / program / functions, both cases (terminal
output; no log file kept).

### 1.6 The page bound A/B and the determinism rerun

**The page bound A/B** (16:14:15–16:15:46, 90.8 s): `build/r2/payload.json`
replaced by the tracked `pages/r2/payload.json` (the 10-20 print's record,
pages 3 — the archive index's proposed re-point), `rebuild_v2.py --out
bootstrap/build/sheets-bound3`, then build.py's file (pages 4) put back.
Result: every PDF identical again (print 1d6a7697…), and now **54 of the
lead's 55 SHA256SUMS lines identical, the codes.txt and sizes.txt included**;
the one remaining difference is MANIFEST.txt, which differs in exactly one
line — line 46 names the `--out` directory (`build/sheets-bound3/…` for
`build/sheets/…`). With the bound 3 and the default `--out`, the manifest
would be byte-identical to the lead's. So the lead's MANIFEST is reproduced
in full once the bound is the committed 3, and the only non-master input of
run 1 was that integer.

**Determinism, run 2** (16:15:46–16:17:16, 90.5 s, exit 0; bound 4 again,
into `build/sheets` over run 1's output): `rebuild_v2.py` compared its new
MANIFEST.txt and SHA256SUMS against run 1's — "byte-identical to the
previous run" for both.

### 1.7 Provenance of every input the final PDF rests on

| input | where it comes from | state in this control |
|---|---|---|
| stage1/template.py | git, HEAD | 3d342f496acdd1902f0354d19a1772b76ef500f33979528cc75f869b6376d0f1 |
| stage1/frozen_lower.json, frozen_upper.json | git (the frozen spellings of search.py; searches not run) | 767a3ee64e1507088727e6fd4e6e3a0af43be2eb907918d0d83fcd89a3c8b79f, 5af8e8d34fc149bdff9481338a5171637bca38a9f091958279046726b6a248c3 |
| r2reader/reader_lite_v1.py (b.py's text) | git | b77779b46444c7f3370f75258f49fb28d65fbdfd2003b100e6df347e750e04b2 |
| stage3/c.py (the R2 content) | git; regenerated identically by make_c.py from stage3/c_readable.py be95e6ea… (§2) | 92c48a39f9eb115908921c5bdbe060ec8987903abaa4f0ef6efbfbfbfb30d3b7 |
| stage1/qr/qr-a.pbm, qr-d.pbm (the QR bitmaps of ruling 62; refused by print_sheets.py if a.py or data.txt moved) | git | 9a242d33abf7301163010e6d26e5f3f9d02807f3300da52d446e2b6cf4fd4666, 5a4e9e11f5fae7bed486dbb676290747ebbf88d36e60bef9807a6f4944b99364 |
| r2reader/grid_to_pgm.py (its last line quoted on sheets 1 and 2) | git | 5d9a2ade4fe3d5c72d1cc8f6e00102ac4ae0112398b9d9ffd6a7c2d9a5f6d0b4 |
| the stage code: bootstrap/rebuild_v2.py itself (its DATE default 2026-10-23 is in the file names and headers), stage1/{chain_v2,make_typed,gen_readable,e2e,leaves,make_sheets_v2,print_sheets}.py, stage1/qr/qr.json (the QR versions and the stored decode text, print_sheets.py:107, 117, 447), typed/{cm2_enc,cm2_dec}.py + kat_v2.json, r2/{gen,verify_grid,camera,placement_stats}.py, pages/{render_pdf,compose_leaves}.py (compose_leaves lays out the listing and data leaves, leaves.py:30, 121–122), r3/arch/receiver_arch.py + arch_pack.py + derive.py + trees.py, stage3/e2e_c.py + r3/arch/e2e_arch.py + r3/make_test_volume.py, src/holo (the generator) | git, HEAD 01b66196 | (list completed after the refutation pass) |
| build/r2/payload.json ['pages'] (the frontier's page bound) | **build/ only**: bootstrap/build.py (pages 4 today; 3 in the lead's run and in the tracked pages/r2/payload.json aca2b468…) | reaches the "(record N)" text only, never the paper |
| build/stage3/e2e/T1/vol (the 15 archive pages) | e2e_c.py volume at HEAD over the T1 container | regenerated, 46/46 == the lead's |
| build/r3/arch/e2e_arch/T1/container.bin (the stage-4 payload, 1,648,660 B) | **build/ only in the tree's own recipe**; here: the 321 blobs of commit 2115a595 + the encoder derived from receiver_arch.py at HEAD (13 min) | regenerated byte-exact 78d9a4b4… |
| the environment | CPython 3.14.8t, numpy 2.5.2, scipy 1.18.1 (make_test_volume.py:28), pillow 12.3.0, python_minifier 3.4.0 (make_c only), ghostscript 10.08.0 (zxingcpp is NOT in env/ and not used by the rebuild; the MANIFEST's zxingcpp text is qr.json's), and the FONTS `/System/Library/Fonts/Menlo.ttc` and `/System/Library/Fonts/Supplemental/Andale Mono.ttf` (pages/render_pdf.py:61–62: a missing face falls back to Menlo with a warning) | machine 1's; the listing and data sheets' pixels depend on these two system fonts, which no master object carries |

## 2. The long forms

| program | item | command | wall | result |
|---|---|---|---|---|
| a.py | bare lane (stand-in bundle, bound 4) | `cd bootstrap/stage1; python make_typed.py --case lower` / `--case upper` | 40.2 s / 40.3 s | PASS both: equivalence units + KATs + known answer, census 0 of 343,227; frontier chose (0,1,2,3,4,6), typed 3,287 (upper); R2 of the stand-in 17,353 B, 4 pages (record 4) |
| a.py | the long form | `python gen_readable.py --case lower` / `upper` | untimed | wrote build/stage1/{lower,upper}/readable.py |
| a.py | identity, bare | `python test_identity.py` | 4.0 s | PASS lower and upper: mechanical (a.py == template renamed; readable.py == gen_readable; long-form ast == template ast), program (same screen, 29 lines; b.py 4,486 B byte-identical), functions (k on 1,000 random strings; d on 3 payloads). ARCHIVE-INDEX's lane-c note ("run bare reads the stale build/stage1 and fails") did not reproduce here — but this build/ started empty, so no stale build/stage1 existed; the note's failure mode was not exercised |
| a.py | identity, on the rebuild | `python bootstrap/stage1/chain_v2.py identity lower|upper --out bootstrap/build/sheets/stage1` | 2.0 s each | PASS both cases (§1.5) |
| b.py | the long form | `python bootstrap/r2reader/gen_reader_long.py --check` | 0.1 s | "reader_long_v1.py: the generator's output" — the committed long form (9824918749efa482…) is generated byte for byte |
| b.py | identity A–D | `python bootstrap/r2reader/test_reader_identity.py` (fixtures: build.py's output of today — readers.json N2 60242 B2 667444896, build/loader/r.py, build/bundle/b.py, the 4 stand-in pages' frames) | 22.9 s wall / 87 s cpu (terminal output; no log file kept) | PASS A (typed text = template renamed, 4,426 B, 174 roles), PASS B (reader_long_v1.py = the generator's output, 809 lines), PASS C (both capture sets close "15@ 661/661", c.py == the bundle 60,242 B on each), PASS D (6 long-form mutations and 3 template mutations each fail) |
| c.py | provenance | `python bootstrap/stage3/make_c.py --provenance` | 1.6 s | PASS: (a) make_arch.build(False) byte-identical to r3/arch/receiver_arch.py (58,348 B, 81509e92…); (b) retarget r0550 → r0547, checks == holo r0547 edges (14,611), FORMAT_ID holo/v2/1i200-k-r0547-p100-v1@35x24, minified-g differs from the record's in exactly 2 literals → build/stage3/c_retarget.py 58,363 B bbef84ea…; (f) c_retarget.py → c_readable.py = 6 hunks (docstring 3, code 3 pure insertions, 3 print calls), ast-identical otherwise. Note: the record's minified-g form (build/r3/arch/forms_arch/receiver_arch.minified-g.py) is absent in an empty build/, so make_c.py:445 checks only its length, 24,460 B |
| c.py | generation | `python bootstrap/stage3/make_c.py --workers 6` | **471.8 s wall**, 722 s cpu, max RSS 2.11 GB | primer = chain_v2 make upper (orders (0,1,2,3,4,6), N2 24080); M1 30 aliases, 10,685.8 → 10,614.9 B ideal, ast-equivalent; M2 351 bindings renamed, bijective, 10,119.4 B; M3 45 attributes, → 9,946.3 B; M1 → c.py 375 bindings + 45 attributes, bijective; no import; **c.py 24,080 B sha256 92c48a39… identical to the committed c.py** (git status clean) |
| c.py | scan-free checks | `python bootstrap/stage3/unit_c.py` | 8.6 s | ALL OK: synthetic (5 files byte-exact), badcrc (refused, payload.bin only), plain — on c_readable.py and on c.py (Receiver = Am, main = Ap) |
| R2 pages | the generator | `python bootstrap/r2/test_gen_v1.py` | 118.5 s, 1.02 GB | **80 checks, 80 passed**; two counted PASS as skips: "camera v0 regression (skipped: no 10-19 build)", "refusal: forged payload (skipped: build/refute-format absent)" |
| the volume | `e2e_c.py volume` | §1.4 | 11.9 s | 15 pages field_identical, == the lead's |

Not run here (owner's rule, no receiver runs on real scans; and the
simulated-scan qualification is the record's, 20–25 min and 5 GB):
`e2e_c.py scans arch arch40` and `e2e_c.py run …`; the data of record is
CONVERGENCE-2026-10-23.md §4 (321/321 files on T1_c_cv_92c48a39).

## 3. The compressor experiments

### 3.1 The shelf, run

An Opus operational runner (per .claude/rules/workers.md) ran every member
of bootstrap/README.md's "Compressor shelf" on T3_32k.txt and T1_8k.py,
encoder then decoder in a separate process, round trip checked with `cmp`,
in the condition each record cites ("primed" = primer.txt followed by the
codec's own decoder file, as the records did it), one run at a time, load
4–6 (two other heavy jobs). Environment: CPython 3.14.8t, numpy 2.5.2,
<host>, 2026-10-23 15:53–16:15 CEST. **Every member runs today and
every round trip was byte-exact.** Every number the shelf cites for these two
texts reproduces exactly, except one, explained below. The full tables with
every command, wall and file:line citation are Appendix B.

| member | condition | T3 / T1 (B) | against the record |
|---|---|---|---|
| cm1, k=22 | unprimed | 6,896 / 2,792 | equal (cm1/NOTES.md, results.jsonl) |
| cm1, k=22 | primed | 6,556 / **2,501** | T3 equal; **T1 cited 2,504** (cm1/NOTES.md:42) |
| cmmix | unprimed | 6,950 / 2,799 | equal (record-2026-10-18/stage0-panel/cand/cmmix/results.json; "cand/" below = that directory) |
| cmmix | primed | 6,629 / 2,542 | equal |
| cm2 v1 | unprimed | 7,257 / 2,884 | equal (cand/cm2/NOTES.md:33; the size is the file minus its 4-byte n header) |
| cm2 v1 | primed | 6,914 / 2,633 | equal |
| cm2 v2 (the chain decoder) | unprimed | 7,240 / 2,886 | NEW — the README says "Not measured on the three test texts" |
| cm2 v2 | primed | 6,867 / 2,632 | NEW |
| bwt | unprimed / primed | 8,204 / 3,146 — 8,188 / 3,121 | equal (cand/bwt/results.json) |
| ppm | unprimed / primed | 7,810 / 3,092 — 7,574 / 2,896 | equal (cand/ppm/results.json) |
| lzdict | unprimed / primed | 8,545 / 3,263 — 8,299 / 3,098 | equal (cand/lzdict/results.json) |

**The one mismatch, cm1 primed T1 2,501 against the cited 2,504 (−3 B),
explained and confirmed in git:** commit 3cd56e52 (2026-10-18 16:11) split
one line of `stage1/cm1_dec.py` (now `record-2026-10-18/cm1/cm1_dec.py`,
moved in 76f817d2) into two —
`T[t] = pt + (((y << 12) - pt) * R[nt] >> 16) << 4 | nt + (nt < 15)` became
`pt += …` and `T[t] = pt << 4 | …` — the same arithmetic (the unprimed sizes
are equal), but the decoder text is the second half of the primer, so the
primed size moved. Priming with the earlier text,
`b05d4066:bootstrap/stage1/cm1_dec.py`, gives 2,504 and 6,556, the cited
figures. The record's number is right for the text it had.

**The archive-codec unz() pairs through `r3/arch/bench.py`** (fixture path
as TREE; unprimed, bench's `enc()` takes no primer; `gen_cm2fam.py` wrote
the seven cm2 pairs as untracked files, benched, then deleted — `git status
--short bootstrap/r3/arch` clean before and after). All NEW numbers: the
README cites these families on T1.tar only.

| codec | T3 / T1 (B) | note |
|---|---|---|
| cm1k24 | 6,898 / 2,795 | 4 B over the bare cm1 k=24 (6,894 / 2,791): the 4-byte output length these decoders read from the coded data (dec_cmmix.py:10) |
| cmmix twin | 6,954 / 2,803 | 4 B over the panel's cmmix, same reason |
| strong | 6,972 / 2,825 | |
| strong2 | 6,989 / 2,835 | decode peak 1.36 GB (the 2^28 tables) |
| cm2xrc | 7,247 / 2,892 | |
| cm2xrc1 | 7,261 / 2,888 | 4 B over cm2 v1 |
| cm2hrc | 7,251 / 2,891 | |
| cm2xrans | 7,248 / 2,892 | |
| cm2hrans | 7,253 / 2,893 | |
| cm2xblk | 7,247 / 2,893 | |
| cm2hblk | 7,252 / 2,893 | |

On texts this small strong and strong2 come out LARGER than cm1k24 and
cmmix; strong2's lead is on record at archive scale only (T1.tar, 1,648,648
B, r3/arch/README.md:265).

**The prior-art ports** (all NEW numbers, unprimed; zp_enc and enc_crkpy
have no CLI and were driven from small scripts in the scratch directory
following the README's snippets):

| member | T3 / T1 (B) | encode wall T3 / T1 | note |
|---|---|---|---|
| Crinkler port, `crk_enc.py` CLI (SLOW, 100 hash tries) | 7,347 / 2,890 | 676 s / 149 s | sizes include its "C4" container; no primed row (the CLI takes no primer, and T3 alone took 11 min) |
| crkpy member (README's snippet: `search(…, rule='crksat', subsets=SUB8)`) | 7,369 / 2,915 | 94 s / 17 s | |
| ZPAQ `max` | 7,061 / 3,068 | | whole block, headers included |
| ZPAQ `ours3` | 7,093 / 3,214 | | 2.33 GB peak RSS |

Failures: none from any codec. (The runner's first bwt/ppm/lzdict attempt
exited 127 from its own zsh harness not splitting the command string; those
rows were discarded and re-run under bash; only the bash rows are
reported.) `bench.py` appended 22 rows to the gitignored
`build/r3/arch/bench.jsonl` and left its coded `.z` files under
`build/r3/arch/coded/`. No tracked file was touched; the 14 generated
`dec_/enc_cm2*` files were deleted.

### 3.2 The records' instruments (an Opus reader's audit; every status checked with `git ls-files --error-unmatch` at HEAD and `git cat-file -e bootstrap-pre-thinning-2026-10-23:PATH`; the per-record tables are Appendix A)

Records read: compressor-exploration/{README, ASSESSMENT-2026-10-20,
LEVERS-2026-10-21, measure-2026-10-20/results, archive-14-pages/RESULTS,
encoder-side/RESULTS, strong2-integer-tricks/RESULTS, typed-arms/RESULTS}.md;
priorart/{SURVEY, REVIEW}-2026-10-20.md, priorart/{crinkler,zpaq}/README.md;
record-2026-10-18/README.md, stage0-panel/{STAGE0-DECOMPRESSOR-MEMO,
STAGE0-CRITIQUE}.md, every cand/*/NOTES.md and cm1/NOTES.md; r3/arch/
README.md (the codec table and the Files section).

**Counts** (a hand tally over Appendix A, ±3): 143 cited experiment rows;
about 19 with every instrument at HEAD (most of those still need
gitignored build/ inputs or a regenerated T1/T4); about 94 needing at
least one instrument that is at the tag only; about 30 with at least one
instrument in neither place (a refuter's recount of Appendix A: 141 rows,
19 / 93 / 29 — inside the stated ±3; two of the 19 "HEAD" rows are n/a or
gitignored outputs). Distinct instrument files: HEAD ≈ 45,
TAG-ONLY ≈ 330 (about 100 of them arm/variant/sweep scripts), NEITHER ≈ 20
locations.

**Runnable now at HEAD** (with the stated inputs): compressor-exploration/
harness/cm2lab.py (inputs are build/ products of the 7dd8a9a6 tree, pinned
by sha only); encoder-side/mono_final.py (an OUTPUT of the pipeline, not the
pipeline); typed/count_lines.py, typed/cm2_v1_{dec,enc}.py; build.py;
r3/measure.py; r3/arch/{measure_arch, trim_probe, make_arch}.py (need
build/loader/r.py and python_minifier); r3/arch/{bench, trees, derive,
arch_pack, test_arch, e2e_arch, gen_cm2fam, derive_cm2}.py and
dec/enc_{strong2, strong, cm1k24, cmmix}.py; r3/make_test_volume.py;
record-2026-10-18/scripts/{cm2b_enc, closure, strip}.py and the fixtures;
cand/{cmmix, bwt, lzdict, ppm}/{dec, enc}.py and cm1/cm1_{dec, enc}.py
(codecs only — every driver is cut); priorart/crinkler/{crk_dec, crk_enc,
fam, dec_crkpy, enc_crkpy}.py and priorart/zpaq/{zp_dec, zp_enc,
zp_configs}.py (codecs only — drivers cut).

**At the tag only**: compressor-exploration/measure-2026-10-20/scripts/
{run_one, baselines, cpp_codecs, assemble, csloc}.py; typed-arms/{lab, arms,
final, screen, report, typesim}.py and sim_*/; the whole encoder-side
pipeline ({reader_v2_encoder, a_rw2, r_rw2, rewrites, run_rewrites, names,
names2, run_reader_names, run_reader2, run_mono_names, mono_inl, mono_inl_rn,
mono_inline, mono_exact, attr_est, attr_greedy, ev, rn2, rn_all, rn_lower,
rw1, rw2, search, search2, chain, diffread, prim, mono_test,
dec_arch_derived}.py, data_rw2.txt, cm2h.c, cm2c.c, cm2lib.c — copies of
names2/search2/ev/cm2h.c/mono_inline live at HEAD under stage3/lab/);
strong2-integer-tricks/*.py; archive-14-pages/{mk_arms, run, derive, pre,
orders, dedupe_lpaq, inarch, r2cost, dec_strong2}.py, arm_*.py, diffs/,
chk/; literature/order.py; refuters/**; workflows/*.js + agent-results;
loader/review/{experiments, hand_search, alphabets, common, names}.py;
priorart/crinkler/{build_typed, r2, bench_arch, run_faithful, speed, oos,
search_fam, test_roundtrip, common}.py; priorart/zpaq/{zp_tiny, test_zp,
bench_zp, measure_r2_zp, typed_zp, summary_zp}.py; r3/arch/{pages,
measure_r2, refs, stdlib_time, runq, summary, show, show_e2e, e2e,
test_unpack, mk_k, mk_cm1, mkvariants, mkvariants2, sizes_probe}.py,
dec/enc_cm2{x,h}{rc,rans,blk}.py + dec/enc_cm2xrc1.py, unp_*.py;
record-2026-10-18/scripts/bench_pip.py, cm1/bench.py, cand/cm2/{dec,enc}.py
(byte-identical copies at HEAD: typed/cm2_v1_{dec,enc}.py, the same blob),
cand/cmmix/{dec40, measure, kav, tune, tunep, wmax, wrapcheck, sp*, spab*,
spm, spt4a, t4}.py, cand/bwt/{dec_mtf, dec_tiny, enc_mtf, enc_tiny, measure,
rt2}.py, cand/lzdict/{dec_raw, measure}.py, cand/ppm/{dec32, dec_plus,
enc_plus}.py, every cand/*/refute/*.py, refute-typed/*, refute-r2/*.
Several of these hardcode cloud paths (`/home/user/paper-store`,
`<tmp>`) — typed-arms/lab.py, s2full.py, the crinkler probes,
the panel's measure.py/rt.py, cm1/bench.py — and would not run as restored.

**Cited but in neither place**: the third-party codecs lpaq1, paq8l, paq1,
fpaq0, fpaq0f2, upkr, DMC, Nayuki PPM and the xz/zstd CLI runs (cloud
container; excluded by compressor-exploration/README.md:102–105);
`<tmp>` (ASSESSMENT:304) and
`.../litm/split.py` (the JSZap split, LEVERS:266) with the litm and refuter-2
paq8l/lpaq1 per-rung ceilings (LEVERS:270, 283–291; their numbers survive
only in the tag's workflows/agent-results JSON);
`<tmp>` (the memo's own-text
priming) and the critic's in-memory runs; unnamed probes at ASSESSMENT:93,
126, 159, 208, cm2 NOTES:44–47, lzdict NOTES:35–37, the ppm orders sweep
(NOTES:29–31), bwt NOTES:38–40, the cm1 ablation variants; the
r3/arch/README.md:321–322 stdlib+os 10,238 B one-off; the crinkler
leaf-size driver (README:616–620); and the priorart refuters' scripts
`refute_crk/{rt_other, t1_crkpy}.py`, `rz/{run_mod, rt_untuned, maxlite,
oos}.py` and the `ext/zpaq/src/libzpaq.cpp` clone under
`<tmp>
— **in no commit, but still on machine 1's /tmp at the time of the audit
(priorart/zpaq/test_zp.py:22, at the tag, hardcodes that clone's path); a
/tmp clean-up loses them.**

Also found: ARCHIVE-INDEX:20's "Every file named by a dated record and
absent from the tree is at that tag" is false for the NEITHER items; two
records list cut files as present (record-2026-10-18/README.md:21
`bench_pip.py`, r3/arch/README.md:45 `show_e2e.py`); `r3/arch/pages.py`
(holo's page planner, tag-only) produced the archive-page count in four
records (the arch codec table, crinkler, zpaq, archive-14); the current
`build.py` and `trees.py` do not reproduce the 7dd8a9a6 payloads or the
9,533,440 B T1 the compressor sessions measured (compressor-exploration/
README.md:84–98 pins those by sha only); T4 must be rebuilt from a checkout
of main 2fa8fd5 (closure.py + strip.py, at HEAD).

## 4. The gaps and what each needs

1. **`build/r2/payload.json` — the page bound (make_typed.py:70, 466).**
   Today's build.py hands 4 where every record says 3. It reaches only
   codes.txt/sizes.txt/MANIFEST.txt text, so the paper is unaffected, but
   the rebuild of record cannot be re-run on a clean checkout without
   build.py and its tracked-file rewrites, and its MANIFEST.txt then
   differs from the lead's. The archive index's proposal stands and is
   now sharper: re-point make_typed.py's R2_RECORD at the tracked
   `pages/r2/payload.json` (pages 3, the committed record) — one line,
   but fragile, since build.py rewrites that tracked file whenever it runs
   (§1.2) — or make the bound an explicit argument of rebuild_v2.py / a
   constant in make_typed.py. The owner's call; nothing changed here.
2. **The T1 container (e2e_c.py:39, 44–45, 55–62).** Regenerable, as
   §1.3 shows, from the git blobs of 2115a595 plus 13 minutes of
   encoding, but no script in the tree does it: `arch_pack.py T1` tars the
   WORKING TREE (three files moved) and `e2e_c.py` only copies and
   sha-checks. Cheapest fixes, in order of bytes: (a) a `--commit` for
   `arch_pack.py` / `trees.py` (tar from `git show COMMIT:PATH`) and the
   commit 2115a595 named in `e2e_c.py` beside the two shas, with the
   13-minute encode run when the copy is absent (about 20 lines, 0 B of
   data); (b) committing `container.bin` + `T1.tar` as provenance
   (1,648,660 + 9,523,200 B = 11.2 MB; the lead's 1.65 MB figure is the
   container alone, but as the code stands `e2e_c.py volume` goes through
   `prepare()`, which copies and sha-checks BOTH files (e2e_c.py:55–67,
   184–188), so the container alone would need a code change; logically
   the tar is only the truth for the scan runs' unpacked files); (c) naming the commit in
   stage3/README.md only (0 B, 0 lines; the operator does what §1.3 did).
   The owner's call; this control did (c)'s work by hand.
3. **build.py rewrites tracked files and no longer closes** (§1.2). Its
   products are still the fixtures of test_reader_identity.py (PASS on
   them) and the only source of the page bound. Either a `--no-record`
   flag (ARCHIVE-INDEX's proposal) or gap 1's re-point removes the need
   to run it for the rebuild at all.
4. **The system fonts.** Menlo and Andale Mono come from machine 1's
   /System/Library/Fonts (render_pdf.py:61–62); the listing and data
   sheets' bitmaps are a function of those font files, which the tree does
   not carry. A rebuild on another machine reproduces the R2 and archive
   pages (pure bitmaps) but not necessarily sheets 1–2 pixel for pixel.
   Recording the two files' sha256 in the MANIFEST would at least detect
   it.
5. **The compressor records' instruments** (§3.2): the six refuter
   scripts and the libzpaq clone on /tmp are the only cited instruments
   that can still be saved; the owner decides whether into the tree (under
   priorart/) or into the evidence archive. The two README lines naming
   cut files (record-2026-10-18/README.md:21, r3/arch/README.md:45) and
   ARCHIVE-INDEX:20's sentence want a correction.
6. **Not a gap, a note:** `make_c.py`'s calibration against the record's
   minified-g form is skipped on an empty build/ (the form lives under
   build/r3/arch/forms_arch/, made by r3/arch/measure_arch.py at the tag's
   state); the length check 24,460 B held.

## 5. Walls (single runs, under load)

| step | wall |
|---|---|
| rebuild_v2.py on the empty build/ (fails) | 0.12 s |
| build.py | 152.8 s |
| T1 tar from git + strong2 encode | 778.3 s (encode 773.9 s) |
| e2e_c.py volume | 11.9 s |
| rebuild_v2.py run 1 | 92.3 s |
| make_typed.py bare, per case | 40.2 / 40.3 s |
| test_identity.py bare | 4.0 s |
| chain_v2.py identity, per case | 2.0 s |
| gen_reader_long.py --check | 0.1 s |
| test_reader_identity.py | 22.9 s |
| r2/test_gen_v1.py | 118.5 s |
| make_c.py --provenance | 1.6 s |
| make_c.py --workers 6 | 471.8 s |
| unit_c.py | 8.6 s |
| rebuild_v2.py, bound 3 into build/sheets-bound3 | 90.8 s |
| rebuild_v2.py run 2 (determinism) | 90.5 s |
| shelf: crk_enc.py T3 / T1 | 676 s / 149 s |
| shelf: crkpy T3 / T1 | 94 s / 17 s |
| shelf: the rest | seconds each (Appendix B) |

**The refutation pass** (after the first commit 8865bb73): four Opus
refuters by lens (the chain's numbers; code and provenance; long forms and
shelf; the audit and the stance) and one Sonnet citation checker, read-only
over this record and the logs. 96 findings: 77 STANDS, 12 REFUTED (two
slips were caught by two lenses each; all corrected in this revision and
named where they were: the 55-line count,
the two-line MANIFEST diff, payload.json's sha, the QR input and the
zxingcpp text, R2-FORMAT.md not reader.py, the volume's need of T1.tar, the
provenance table's omissions, six not five /tmp scripts), 7 UNVERIFIABLE
(terminal-only outputs, now marked as such; the lane tallies 13 / 19 / 21 /
17 refuter findings and 26 citations). Every file:line citation in
§1–5 checked (26 of 26 resolve). No finding touched a sha, a PDF, the
provenance of the container, or a verdict.

Scratch kept for this session only (not committed): the regeneration
script, every log, build.py's 387-line diff and the lead's reference copies,
under the session scratchpad; `bootstrap/build/` of this worktree holds
every regenerated artefact (gitignored, ephemeral by the owner's word).

## Appendix A — the records audit, per record (the Opus reader's tables, verbatim)


### CE/README.md
| cited at | experiment | instrument | status | runnable-now note |
|---|---|---|---|---|
| CE/README.md:53 | cm2 ideal bits + exact rANS size; decode_ref of a.py's d() | CE/harness/cm2lab.py | HEAD | runnable; inputs (a_build.py, typed_reader.bin, r.py, monolith) are build/ products of 7dd8a9a6, not committed |
| CE/README.md:73-78 | build of record reproduced for payloads | build.py | HEAD | current build.py builds the 10-23 chain, not 7dd8a9a6's payloads |
| CE/README.md:79-80 | minified monolith forms 10,599 B | r3/measure.py, ARCH/measure_arch.py | HEAD | need build/loader/r.py (gitignored) + python_minifier |
| CE/README.md:94-96 | T1.tar / T1.shar / 1-2 MB prefixes | ARCH/trees.py | HEAD | regenerates from git ls-files of the CURRENT tree (T1 differs from 9,533,440 B) |
| CE/README.md:102-109 | public codecs lpaq1/paq8l/paq1/fpaq0/fpaq0f2/upkr | compiled third-party binaries | NEITHER | excluded by the README itself; cloud container only |

### CE/measure-2026-10-20/results.md (session-1 runner)
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :3-9 | fixture pins (T2, T4 rebuilt) | CE/measure-2026-10-20/scripts/run_one.py, assemble.py; T4 via R18/scripts/closure.py+strip.py over a checkout of 2fa8fd5 | scripts TAG-ONLY; closure/strip HEAD | T4 not committed (sha in R18/fixtures/SHA256SUMS-derived) |
| :13-16 | cm2 / cmmix repro, RSS | run_one.py; R18 cand/cm2/{dec,enc}.py; cand/cmmix/{dec,enc}.py | run_one TAG-ONLY; cand/cm2 dec/enc TAG-ONLY at that path (byte-identical HEAD copies typed/cm2_v1_{dec,enc}.py, same blob); cand/cmmix HEAD | runner at tag only |
| :17-28 | lpaq1, fpaq0, fpaq0f2, upkr (incl. primed by difference, line counts) | scripts/cpp_codecs.py, csloc.py + compiled binaries | scripts TAG-ONLY; binaries NEITHER | not runnable without rebuilding third-party codecs |
| :28-51 | zlib/deflate/bz2/xz/lzma2/zstd/brotli/ppmd | scripts/baselines.py | TAG-ONLY | needs zstandard/brotli/pyppmd |
| :13-16 "count_lines MEASURED" | decoder line/char counts | typed/count_lines.py | HEAD | runnable |

### CE/ASSESSMENT-2026-10-20.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :5 | 16 cm2/cmmix sizes reproduced | measure-2026-10-20/scripts/* | TAG-ONLY | |
| :7-10 | 822 uncounted comment chars | typed/count_lines.py (+ unnamed count) | HEAD | |
| :23,25,31,43,47 | PAQ1 weights +0.7 %, paper update +0.8 %, no boost +2.8 %, x4 +1.1 %, PAQ1 rules +4.1 % | CE/refuters/session1-logic/cmvar2.py (record names <tmp> :305) | TAG-ONLY (outputs out_*.txt also TAG) | |
| :24, :304 | superseded mis-ported variant | <tmp> | NEITHER | |
| :76 | best-of-254 sparse masks ≤5 B, weight retune 0 | refuters/session1-crinkler-probes/{cost,greedy,wscan}.py | TAG-ONLY | hardcode /home/user/paper-store/... fixture path |
| :81-91 | T3 table: upkr, DMC, Nayuki PPM, fpaq0, paq8l, LZW | cpp_codecs.py (upkr, fpaq0); DMC/Nayuki/paq8l run by survey worker and refuter with external sources | cpp_codecs TAG-ONLY; rest NEITHER | LZW itself UNVERIFIED in the record |
| :93 | 64-bit PAQ1 port 10,286 (dropped) | unnamed port | NEITHER | |
| :95-104 | lpaq1 / paq8l unprimed + primed by difference, 1.64 GB | cpp_codecs.py + binaries; refuter's paq8l run | TAG-ONLY / NEITHER | |
| :105 | PPMd o16 primed | baselines.py | TAG-ONLY | |
| :106 | fixed-weight logistic probe | refuters/session1-crinkler-probes/logi.py | TAG-ONLY | hardcoded /home/user path |
| :126 | cm2 zipped 680-710 B, deflate 515 B | unnamed | NEITHER | |
| :159 | Canterbury: cm2 vs xz -9e | unnamed | NEITHER | |
| :208, :219 | decay sequence; order-7 reach / no_o7 | unnamed (MEASURED) / cmmix results.json | NEITHER / output HEAD | |
| :214 | cmmix squash/stretch table check | refuters/session1-code/t1.py (record names refute-code/t1.py :306) | TAG-ONLY | |
| :215 | full-res stretch 6,948 vs 6,950 | R18 cand/cmmix ablation scripts sp*.py/spabl*.py; output ablation_T3_dec60.txt | scripts TAG-ONLY; output HEAD | |
| :244 | lpaq1 T4 gap 3.7 % | cpp_codecs.py | TAG-ONLY | |
| :254-255 | cm2 RSS 44 MB T1, 1.19-1.21 GB / 62-68 s T4 | refuters/session1-code/rss.py | TAG-ONLY | |
| :257 | bounded cm2 dict +6 % / +57 % (RECORDED) | R18/scripts/cm2b_enc.py | HEAD | T4 input must be rebuilt (closure.py+strip.py over 2fa8fd5) |
| :262 | cmmix peak 301-384 MB | run_one.py | TAG-ONLY | |

### CE/LEVERS-2026-10-21.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :21 | baseline 3,894 | harness/cm2lab.py | HEAD | build/ inputs of 7dd8a9a6 |
| :23, :41 | slice-constant correction; independent harness | refuters/v2-code-measurement/h.py | TAG-ONLY | |
| :29-36 | REV counter/order/naming results (RECORDED) | loader/review/experiments.py, hand_search.py (+common.py, names.py) | TAG-ONLY | REVIEW.md itself HEAD |
| :37, :387 | Crinkler masks -32 (RECORDED) | PA/crinkler/build_typed.py | TAG-ONLY | |
| :43-95 | typed-lab arms (primer_d_last, q-q//4, q-(q>6), word, SSE, screened losers) | CE/typed-arms/{lab,arms,final,screen,report,typesim}.py, sim_*/ | TAG-ONLY | lab.py hardcodes <tmp> |
| :73 | word arm on rw2 (refuter 1) | refuters/v2-code-measurement/h.py (+ word*.py) | TAG-ONLY | |
| :99-115 | rw2 reader 3,788 | CE/encoder-side/{reader_v2_encoder,a_rw2,r_rw2,rewrites,run_rewrites,names,names2,run_reader_names,run_reader2,rn_*}.py, data_rw2.txt | TAG-ONLY | |
| :112 | 11 frames + b.py identical | encoder-side/chain.py, diffread.py | TAG-ONLY | |
| :117-121 | short tuple 3,778 / 3,777 | refuters/v2-code-measurement/rshort.py; v3-logic-record-literature/{rt.py,a_rw2_short.py}; v4-editor/m.py | TAG-ONLY | v3/v4 paths assume the container layout |
| :128-131 | monolith +7, b.py +7 with rw2 r.py | encoder-side lab (run_mono_names.py etc.) | TAG-ONLY | |
| :158-166 | one-integer rANS, block reset, coder CPU | CE/strong2-integer-tricks/{dec_s2rans,dec_s2rblk14/16/18,coder_bench,coders,dt,unz_rans*,unz_rblk16*,m_r2}.py | TAG-ONLY | |
| :171-178 | exact dicts R2/bytes/RSS | strong2-integer-tricks/{dec_s2exact,_2,_3,unz_exact*,sizes,rt_unz}.py | TAG-ONLY | |
| :183 | strong2 match hash = order 6 | ARCH/dec_strong2.py (read) | HEAD | analysis |
| :188 | cmmix-exact as typed d() 4,239 | strong2-integer-tricks/{cmx_d.a.py,typed_eval,tlab,tlab2}.py | TAG-ONLY | |
| :194-213 | CRH, AQC, OL, M2, SP, APM*, losers, C1+CRH | CE/archive-14-pages/{mk_arms,run,derive,pre}.py, arm_*.py, diffs/, r2cost.py | TAG-ONLY | base codec ARCH/{dec,enc}_strong2.py HEAD |
| :218 | strong2 whole T1 1,650,065 B | refuters/v2-code-measurement/s2full.py (+s2full.log) | TAG-ONLY | hardcodes /home/user/paper-store; ARCH/enc_strong2.py HEAD does the same job |
| :221-224 | paq8l -8 on T1 1,502,611 | paq8l binary; log archive-14-pages/ceil/paq8l_full.log | binary NEITHER; log TAG-ONLY | |
| :235-240 | exec route 9,655 / d-copy 9,825 | strong2-integer-tricks/{r2_exec,arch_dec_cost,r2_under}.py; archive-14-pages/inarch.py | TAG-ONLY | |
| :266 | JSZap-style identifier split +0.9..+3.2 % | <tmp> | NEITHER | |
| :270, :283-286 | paq8l / lpaq1 ceilings per rung (typed, monolith, b.py) | litm runs of external binaries (difference method) | NEITHER | numbers only in tag's workflows/agent-results/03-lab-v2/04-lit_gap-fill.json |
| :288-291 | paq8l on rw2 / mono_final (refuter 2) | v3-refute-logic paq8l runs | NEITHER (no script; v3 t.py/rt.py are cm2lab-only) | |
| :353, :393 | monolith pipeline 10,599 → 9,876 | encoder-side/{run_mono_names,names,names2,mono_inl*,mono_exact,attr_est,attr_greedy,ev}.py; mono_test.py | TAG-ONLY; product encoder-side/mono_final.py HEAD | mono_final.py is the output, not the pipeline |
| :359 | bootstrap/ not in T1 | ARCH/trees.py | HEAD | |
| :361 | leaves/plate priming of b.py | encoder-side/prim.py (+primer_ideal.json) | TAG-ONLY | |
| :370 | shar under lpaq1 -2.7 KB | archive-14-pages/pre.py (+ lpaq1 binary) | TAG-ONLY / NEITHER | |
| :374-375 | file order | archive-14-pages/orders.py; CE/literature/order.py | TAG-ONLY | |
| :377 | dedupe +8 B | archive-14-pages/dedupe_lpaq.py | TAG-ONLY | |

### CE/typed-arms/RESULTS.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :3-88 | ~80 arms, typed/mono/T3, round trips | typed-arms/{lab,arms,final,screen,report}.py | TAG-ONLY | lab.py path <tmp> |
| :12-88 "rt" + stage-1 sims | typing simulation, finalists | typed-arms/typesim.py, sim_*/{a,r}.py | TAG-ONLY | |

### CE/encoder-side/RESULTS.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :3 | C ideal-bits kernel = cm2lab to 1e-9 | cm2h.c, cm2c.c, cm2lib.c | TAG-ONLY | |
| :5-14 | typed reader renames + 48 rewrites | reader_v2_encoder.py, rewrites.py, run_rewrites.py, names*.py, run_reader_names.py, run_reader2.py, rn_*.py, search*.py | TAG-ONLY | |
| :16-19 | chain exact, 11 frames, b.py | chain.py, a_rw2.py, data_rw2.txt, r_rw2.py, diffread.py | TAG-ONLY | |
| :23-30 | monolith 10,599 → 9,876 | run_mono_names.py, mono_inl*.py, mono_exact.py, attr_*.py | TAG-ONLY | mono_final.py (result) HEAD |
| :32-36 | scan-free test_arch-style checks | mono_test.py | TAG-ONLY | |
| :40-58 | primer composition | prim.py | TAG-ONLY | |

### CE/strong2-integer-tricks/RESULTS.md
| cited at | experiment | instrument | status |
|---|---|---|---|
| :7-8 | R2 baseline, T1 prefixes | sizes.py, model_pass.py (+ ARCH/measure_r2.py method) | TAG-ONLY |
| :10 | typed baseline 3,894 | typed_eval.py / cm2lab.py | TAG-ONLY / HEAD |
| :12-36 | rANS forms A/B/C, coder CPU, block reset | dec_s2rans.py, unz_rans*.py, coder_bench.py, coders.py, dt.py, dec_s2rblk*.py, unz_rblk16*.py, m_r2.py | TAG-ONLY |
| :38-52 | exact dicts | dec_s2exact*.py, unz_exact*.py, sizes.py, rt_unz.py | TAG-ONLY |
| :54-62 | exec / d-copy route | r2_exec.py, arch_dec_cost.py, r2_under.py | TAG-ONLY |
| :64-68 | cmmix-exact typed | cmx_d.a.py, tlab.py, tlab2.py, typed_eval.py | TAG-ONLY |

### CE/archive-14-pages/RESULTS.md
| cited at | experiment | instrument | status |
|---|---|---|---|
| :9 | strong2 1/2 MB | ARCH/bench.py + {dec,enc}_strong2.py (or lab run.py) | HEAD (bench) / TAG-ONLY (run.py) |
| :10-12 | xz, lpaq1, paq8l ceilings | external binaries; logs ceil/*.log, *.time | NEITHER (binaries); logs TAG-ONLY |
| :16-36 | 16 strong2 arms, C1, C1+CRH | mk_arms.py, run.py, derive.py, arm_*.py, diffs/*.diff, chk/old_*.py | TAG-ONLY |
| :17-31 R2 col, :53 | R2 deltas, decoder in archive | r2cost.py, inarch.py | TAG-ONLY |
| :39-41 | order, shar | orders.py, pre.py | TAG-ONLY |
| :42-44 | dedupe | dedupe_lpaq.py | TAG-ONLY |

### PA/SURVEY-2026-10-20.md
No measured experiment of its own (:12 "I downloaded no software and ran none"); :277 "82 µs/B" is RECORDED from r3/arch. No instrument.

### PA/crinkler/README.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :26-48, :402-417 | typed variants (crk, sparse-vs 3,863, crkhash, cm2 hybrids) | build_typed.py, common.py | TAG-ONLY | codec fam.py HEAD; common.py reads build/loader, build/bundle, build/r3/arch |
| :302-305 | final_reset rebuild | build_typed.py, fam.py (CRK_FINAL_KEEP) | TAG-ONLY / HEAD | |
| :313-328 | round trips (payload/bundle/monolith/1-2 MB/empty/random) | run_faithful.py, bench_arch.py, test_roundtrip.py; crk_dec.py, crk_enc.py | drivers TAG-ONLY; codecs HEAD | |
| :337-358 | CRC-32C check value, reciprocal reduction | refuter computation | NEITHER (in <tmp> refute_crk) | |
| :437-450 | out-of-sample z | oos.py | TAG-ONLY | |
| :462-470 | search without fee, weights-only | search_fam.py (search.jsonl) | TAG-ONLY | |
| :484-517 | R2 bundle/monolith, --retune | r2.py | TAG-ONLY | |
| :539-585 | archive 1/2 MB, crkpy, 2x2 estimator test | bench_arch.py; dec_crkpy.py, enc_crkpy.py | driver TAG-ONLY; codecs HEAD | enc_crkpy imports crk_enc+fam (HEAD) |
| :588-602 | crkpy whole T1 1,918,411 / 1,944,034, 18 pages | bench_arch.py; ARCH/pages.py | TAG-ONLY | |
| :616-620 | decoder-region leaf sizes | r3/measure.py method (driver unnamed) | HEAD (method) / NEITHER (driver) | |
| :625-657 | speeds, cm2 v2 quadratic fit | speed.py | TAG-ONLY | |

### PA/zpaq/README.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :19-29, :436-456 | R2 cost of strong2/zp_dec/zp_tiny/exec route | measure_r2_zp.py (imports ARCH/measure_r2.py) | both TAG-ONLY | needs build/loader/r.py |
| :31-62, :156-168 | T1 rows, decode times, RSS | bench_zp.py; zp_dec.py, zp_enc.py, zp_configs.py | driver TAG-ONLY; codecs HEAD | |
| :63-70 | refuter's speed-cut maxlite probes | <tmp> | NEITHER (still on machine 1 /tmp) | |
| :72, :484-491 | plain interpreter speed | zp_tiny.py | TAG-ONLY | |
| :175-177 | 14/15-page lines | summary_zp.py + ARCH/pages.py | TAG-ONLY | |
| :179-190, :564-604 | 1 MB proxies, how `ours` was found | bench_zp.py, zp_configs.py | TAG-ONLY / HEAD | |
| :380-411 | tables, compiler, round trips, two decoders | test_zp.py; libzpaq.cpp clone | test TAG-ONLY; clone NEITHER (<tmp> hardcoded at test_zp.py:22, still on machine 1 /tmp) | |
| :498-547, :644 | typed stage rows, stale ours fix | typed_zp.py | TAG-ONLY | |
| :623-627 | 37.6 GB peak | typed_zp.py | TAG-ONLY | |
| :663 | refuter OOS on ALL.tar | rz/oos.py | NEITHER (machine 1 /tmp) | |

### PA/REVIEW-2026-10-20.md
| cited at | experiment | instrument | status |
|---|---|---|---|
| :115-134 | crk refuter re-run, T1 encode 1,944,034 | <tmp> scripts, rt_other.py, t1_crkpy.py} | NEITHER (exists on machine 1 /tmp today) |
| :134 | page counts | ARCH/pages.py | TAG-ONLY |
| :241-278 | fix round | bench_arch.py, oos.py, test_roundtrip.py | TAG-ONLY |
| :419-458 | zpaq refuter, 70 round trips, maxlite | .../scratchpad/rz/{run_mod.py, rt_untuned.py, maxlite.py, oos.py} | NEITHER (machine 1 /tmp) |
| :506-527 | stale row re-run, 37.6 GB | typed_zp.py | TAG-ONLY |
| :560-609 | checker vs jsonl | reads build/priorart/{crinkler,zpaq}/*.jsonl | outputs gitignored (build/) |

### R18/README.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :13-20 | fixtures T1-T3, primer; T4 derivation | fixtures/*; scripts/closure.py, strip.py | HEAD | T4 needs main 2fa8fd5 checkout |
| :21-22 | library baselines | scripts/bench_pip.py | TAG-ONLY | README still lists it as present |
| :22-23 | bounded cm2 +6 % / +57 % | scripts/cm2b_enc.py | HEAD | |
| :24-27 | build-panel refuters | refute-typed/*.py, refute-r2/*.py | TAG-ONLY (only conformance.json, refute-r2/NOTES.md HEAD) | |

### R18/stage0-panel/STAGE0-DECOMPRESSOR-MEMO.md
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :20-30 | Pareto table (9 candidates) | decoders: cand/cm2/{dec,enc}.py (TAG-ONLY at path; HEAD copy typed/cm2_v1_*), cand/{cmmix,bwt,lzdict,ppm}/{dec,enc}.py (HEAD), dec_plus/enc_plus (cm2), dec_tiny/dec_mtf/enc_* (bwt), dec40 (cmmix), dec_raw (lzdict) (TAG-ONLY); drivers cand/{bwt,cmmix,lzdict}/measure.py, cand/{cm2,cmmix}/rt.py, rt2.py (TAG-ONLY); typed/count_lines.py (HEAD) | mixed | drivers hardcode <tmp> |
| :31 | ceiling row | BRIEF (not re-run) | n/a | |
| :35-39 | cm2-o2, bwt-mtf, ppm-plus | cand/cm2/dec_o2.py, bwt/dec_mtf.py, ppm/dec_plus.py | TAG-ONLY | |
| :96-104 | primer worth | per-candidate drivers | TAG-ONLY | |
| :112-120 | own-text priming (synth) | <tmp> | NEITHER | |
| :122 | primer fragility | cand/lzdict/refute/primer_fragility.py | TAG-ONLY | |
| :151, :155 | KAV; random +8 % | cand/cm2/enc.py (HEAD copy typed/cm2_v1_enc.py); cand/cm2/refute/edge.py | TAG-ONLY path + HEAD copy / TAG-ONLY | |

### R18/stage0-panel/STAGE0-CRITIQUE.md
| :7, :15-17, :26 | node counts, KAV mutation runs, T3-prefix check | critic's in-memory runs | NEITHER (":45 I wrote no files") |

### R18 cand NOTES and cm1/NOTES.md
| cited at | experiment | instrument | status |
|---|---|---|---|
| bwt/NOTES.md:3-7 | three bwt variants T3 | dec.py, enc.py (HEAD); dec_mtf, dec_tiny, enc_mtf, enc_tiny, measure.py, rt2.py (TAG-ONLY) | mixed |
| bwt/NOTES.md:26,32,36,38-40 | priming, |w|, 188 MB, next-10-lines | measure.py / unnamed | TAG-ONLY / NEITHER |
| cm2/NOTES.md:29-35 | cm2, orders 0-2, +9 lines on T1-T4 | dec/enc (TAG-ONLY path; HEAD copy typed/cm2_v1_*), dec_o2, dec_plus, enc_plus, rt.py, rt2.py (TAG-ONLY) | mixed |
| cm2/NOTES.md:44-47 | SSE 0 %, adaptive weights, more orders | unnamed sims | NEITHER |
| cmmix/NOTES.md:24-37 | T3 ablation, 2^22, APM | sp0..sp28.py, spab*.py, spm.py, spt4a.py, t4.py, tune*.py, measure.py (TAG-ONLY); ablation_T3_dec60.txt HEAD, other outputs TAG | TAG-ONLY |
| cmmix/NOTES.md:41-43 | wrap mod 2^64, |w|<2^17 | wrapcheck.py, refute/wrap64_dec.py, wmax.py | TAG-ONLY |
| cmmix/NOTES.md:45-48 | dec40 | dec40.py | TAG-ONLY |
| lzdict/NOTES.md:19-29 | optimal parse, dictionary, raw variant | enc.py, dec.py (HEAD); measure.py, dec_raw.py (TAG-ONLY) | mixed |
| lzdict/NOTES.md:35-37 | measured negatives | unnamed | NEITHER |
| ppm/NOTES.md:16-17, :27-37 | dec32, orders K2-K6, dec_plus | dec.py, enc.py (HEAD); dec32, dec_plus, enc_plus, refute/rt.py (TAG-ONLY); no orders driver | mixed / NEITHER (orders sweep) |
| cm1/NOTES.md:21-31, :33-43 | k sweep, check byte, ablations, primed | cm1_dec.py, cm1_enc.py, results.jsonl (HEAD); bench.py (TAG-ONLY, hardcodes <tmp> cmmix_ref_{dec,enc}.py TAG-ONLY at path (same blobs as cand/cmmix/{dec,enc}.py, HEAD) | mixed |

### ARCH/README.md (codec table :263-270 and Files :34-57)
| cited at | experiment | instrument | status | note |
|---|---|---|---|---|
| :265 | strong2 1,648,648 B, 13.1 min, 1.36 GB | bench.py, dec_strong2.py, enc_strong2.py, derive.py | HEAD | T1 regenerated from current tree differs |
| :266 | strong k=24 | dec_strong.py, enc_strong.py (HEAD); mk_k.py (TAG-ONLY) | HEAD | |
| :267 | cm1 k=24 | dec_cm1k24.py, enc_cm1k24.py (HEAD); mk_cm1.py (TAG-ONLY) | HEAD | |
| :268 | cmmix | dec_cmmix.py, enc_cmmix.py | HEAD | |
| :269 | cm2 exact dict + range coder, 25 GB | dec_cm2xrc.py, enc_cm2xrc.py | TAG-ONLY; regenerable by gen_cm2fam.py + derive_cm2.py (HEAD), byte-identity not verified here | |
| :270 | xz -9e, stdlib 0.3 s | refs.py, stdlib_time.py | TAG-ONLY | |
| :263 archive pages col | holo planner | pages.py | TAG-ONLY | used by four records |
| :263 R2 col | decoder+unpacker R2 cost | measure_r2.py, unp_{tarflat,taros,sharflat,sharos}.py | TAG-ONLY | |
| :274-276 | ALL 69.3 MB extrapolation | trees.py (HEAD), refs.py, stdlib_time.py, pages.py (TAG-ONLY) | mixed | |
| :148-156 | trims | trim_probe.py (imports measure, make_arch) | HEAD | needs build/loader/r.py |
| :194-228 | T1 e2e 4 runs, T2 smoke | e2e_arch.py, make_test_volume.py, arch_pack.py, test_arch.py (HEAD); show_e2e.py (TAG-ONLY, listed in Files :45) | mostly HEAD | needs ghostscript, src/holo, 13+ min |
| :239-251 | form sizes | measure_arch.py, r3/measure.py | HEAD | build/loader/r.py, python_minifier |
| :316-322 | stdlib+os 10,238 B one-off | unnamed | NEITHER | |
| :325 | shar -2.3 KB | bench.py on trees.py's T1.shar | HEAD | |
| :54-56 | other harness | runq.py, summary.py, show.py, e2e.py, test_unpack.py, refs.py | TAG-ONLY | |

## Appendix B — the shelf runner's tables, verbatim (every command, wall and citation)

### Compressor shelf: measured 2026-10-23

Environment: CPython 3.14.8 free-threading build (GIL disabled), numpy 2.5.2, host <host>,
Fri 2026-10-23 15:53 CEST. Interpreter env/bin/python. Load was about 4-6 on 10 cores
(two other heavy jobs were running); every run here was sequential.
Tree: worktree control-rebuild-820837 at 01b66196. No tracked file was touched.

Notation: B = bootstrap/, F = B/record-2026-10-18/fixtures, P = the interpreter above.
- **Primed** means the record's convention: primer.txt followed by the codec's own decoder file
  (cm1 NOTES.md:42, STAGE0-DECOMPRESSOR-MEMO.md:17, ppm/lzdict results.json "primed_means").
  - cm1 and cmmix take one primer file, so the two files were concatenated into scratch files
    (primer_cm1.bin, primer_cmmix.bin).
  - The other codecs take a list of primer files, which was passed as is.
- **Round trip**: `cmp` of the decoder's output against the input. The decoder always ran in a
  separate process.
- **Wall**: the encode and decode walls, in seconds, under load.
- **The arch rows (bench.py)** are unprimed, since enc(data) takes no primer. bench.py's coded
  size is len(z) including its container.

### cm1 (B/record-2026-10-18/cm1, run from that directory, k=22 default)
Commands:
- encode: `P cm1_enc.py cm1_dec.py F/T IN.z [PRIMER]`
- decode: `P cm1_dec.py IN.z N OUT [PRIMER]`

| text | condition | round trip | size B | wall s enc/dec | cited B (file:line) | equal? |
|---|---|---|---|---|---|---|
| T3_32k | unprimed k22 | PASS | 6,896 | 2.2/2.2 | 6,896 (cm1/NOTES.md:26; README:353) | yes |
| T3_32k | primed k22 | PASS | 6,556 | 3.1/3.1 | 6,556 (cm1/NOTES.md:42) | yes |
| T1_8k | unprimed k22 | PASS | 2,792 | 0.6/0.6 | 2,792 (cm1/NOTES.md:26) | yes |
| T1_8k | primed k22 | PASS | **2,501** | 1.5/1.5 | 2,504 (cm1/NOTES.md:42) | **NO (−3 B)** |

Why T1 primed is 3 B off: the decoder text was edited after the measurement.
- Commit 3cd56e52 split one line of cm1_dec.py into two. The model is unchanged: the unprimed sizes
  are equal.
- The primed figure was taken with the earlier text. Priming with the b05d4066 version of
  stage1/cm1_dec.py (via `git show`, into scratch) and encoding with today's decoder gives
  **T1 2,504 and T3 6,556**, the cited numbers exactly.
- The encode was run only for this check, not decoded.

### cmmix (cand/cmmix, run from that directory)
Commands:
- encode: `P enc.py dec.py F/T IN.z [primer_cmmix.bin]`
- decode: `P dec.py IN.z N OUT [primer_cmmix.bin]`

| text | condition | round trip | size B | wall s | cited B (file:line) | equal? |
|---|---|---|---|---|---|---|
| T3_32k | unprimed | PASS | 6,950 | 2.5/2.5 | 6,950 (cand/cmmix/results.json:13) | yes |
| T3_32k | primed | PASS | 6,629 | 3.3/3.2 | 6,629 (results.json:19) | yes |
| T1_8k | unprimed | PASS | 2,799 | 0.8/0.8 | 2,799 (results.json:11) | yes |
| T1_8k | primed | PASS | 2,542 | 1.6/1.5 | 2,542 (results.json:17) | yes |

### cm2 v1 (B/typed, run from B)
Commands:
- encode: `P typed/cm2_v1_enc.py typed/cm2_v1_dec.py F/T IN.z [F/primer.txt typed/cm2_v1_dec.py]`
- decode: `P typed/cm2_v1_dec.py IN.z OUT [same primers]`

Size = file − 4 B: the CLI prepends n, and the record counts len(src) (cand/cm2/results.json
"size_note").

| text | condition | round trip | size B | wall s | cited B (file:line) | equal? |
|---|---|---|---|---|---|---|
| T3_32k | unprimed | PASS | 7,257 | 1.4/1.4 | 7,257 (cand/cm2/NOTES.md:33) | yes |
| T3_32k | primed | PASS | 6,914 | 1.8/1.8 | 6,914 (NOTES.md:33) | yes |
| T1_8k | unprimed | PASS | 2,884 | 0.4/0.4 | 2,884 (NOTES.md:33) | yes |
| T1_8k | primed | PASS | 2,633 | 0.8/0.8 | 2,633 (NOTES.md:33) | yes |

### cm2 v2 (B/typed, run from B)
Commands:
- encode: `P typed/cm2_enc.py typed/cm2_dec.py F/T IN.z [F/primer.txt typed/cm2_dec.py]`
- decode: `P typed/cm2_dec.py IN.z OUT N [same primers]`

The README says "Not measured on the three test texts" (README:383), so every size below is a
**NEW number, measured today**.

| text | condition | round trip | size B | wall s | cited B | equal? |
|---|---|---|---|---|---|---|
| T3_32k | unprimed | PASS | 7,240 | 4.3/3.5 | none | n/a (new) |
| T3_32k | primed | PASS | 6,867 | 4.7/4.1 | none | n/a (new) |
| T1_8k | unprimed | PASS | 2,886 | 0.7/0.6 | none | n/a (new) |
| T1_8k | primed | PASS | 2,632 | 1.1/1.1 | none | n/a (new) |

### r3/arch unz() pairs via bench.py (unprimed; run from the worktree root)
Command: `P bootstrap/r3/arch/bench.py CODEC bootstrap/record-2026-10-18/fixtures/T`. It encodes,
decodes in a fresh process and compares. Its rows were appended to the gitignored
bootstrap/build/r3/arch/bench.jsonl, and its coded files went to bootstrap/build/r3/arch/coded/.

| codec | text | round trip | size B | wall s enc/dec | dec RSS MB | cited B on this text | equal? |
|---|---|---|---|---|---|---|---|
| cm1k24 | T3_32k | PASS | 6,898 | 2.1/2.1 | 104 | none on the shelf; cm1 k=24 raw 6,894 (cm1/results.jsonl:24) | +4 B = the 4-byte n in unz's container |
| cm1k24 | T1_8k | PASS | 2,795 | 0.5/0.5 | 104 | none; cm1 k=24 raw 2,791 (results.jsonl:14) | +4 B, same reason |
| cmmix (twin) | T3_32k | PASS | 6,954 | 2.3/2.3 | 323 | none; panel cmmix 6,950 | +4 B (dec_cmmix.py:10 reads n from z[:4]) |
| cmmix (twin) | T1_8k | PASS | 2,803 | 0.7/0.7 | 313 | none; panel 2,799 | +4 B |
| strong | T3_32k | PASS | 6,972 | 2.8/2.8 | 216 | "Not measured" (README:397) | NEW |
| strong | T1_8k | PASS | 2,825 | 0.9/0.8 | 216 | "Not measured" | NEW |
| strong2 | T3_32k | PASS | 6,989 | 2.9/2.9 | 1,360 | "Not measured" (README:404) | NEW |
| strong2 | T1_8k | PASS | 2,835 | 1.0/1.0 | 1,360 | "Not measured" | NEW |
| cm2xrc | T3_32k | PASS | 7,247 | 1.5/1.5 | 203 | only T1.tar cited (README:390) | NEW |
| cm2xrc | T1_8k | PASS | 2,892 | 0.4/0.4 | 70 | — | NEW |
| cm2xrc1 | T3_32k | PASS | 7,261 | 1.3/1.4 | 130 | — | NEW |
| cm2xrc1 | T1_8k | PASS | 2,888 | 0.3/0.3 | 60 | — | NEW |
| cm2hrc | T3_32k | PASS | 7,251 | 2.2/2.2 | 443 | — | NEW |
| cm2hrc | T1_8k | PASS | 2,891 | 0.6/0.6 | 416 | — | NEW |
| cm2xrans | T3_32k | PASS | 7,248 | 1.5/1.5 | 203 | — | NEW |
| cm2xrans | T1_8k | PASS | 2,892 | 0.4/0.4 | 70 | — | NEW |
| cm2hrans | T3_32k | PASS | 7,253 | 2.2/2.2 | 443 | — | NEW |
| cm2hrans | T1_8k | PASS | 2,893 | 0.6/0.6 | 416 | — | NEW |
| cm2xblk | T3_32k | PASS | 7,247 | 4.3/3.3 | 203 | — | NEW |
| cm2xblk | T1_8k | PASS | 2,893 | 0.6/0.5 | 70 | — | NEW |
| cm2hblk | T3_32k | PASS | 7,252 | 5.1/4.1 | 443 | — | NEW |
| cm2hblk | T1_8k | PASS | 2,893 | 0.9/0.8 | 416 | — | NEW |

Two observations, made by comparison only (no cause tested):
- cm2xrc1 (v1 orders) gives 7,261 / 2,888. That is the cm2 v1 CLI's 7,257 / 2,884 plus 4 B, the
  same container offset as the twins above.
- On these small texts, strong and strong2 come out *larger* than cm1k24 and cmmix. strong2's
  advantage is recorded at archive scale only (T1.tar).

### Crinkler port (B/priorart/crinkler; crk_enc.py CLI, SLOW mode, 100 hash tries by default)
Commands:
- encode: `P B/priorart/crinkler/crk_enc.py F/T IN.z`
- decode: scratch drv/crk_unz.py, which calls `crk_dec.unz(z)`. crk_dec has no CLI.

The record has no figures for these texts (README:410), so the sizes are NEW. Each includes the
"C4" container. Primed was **NOT run**: the CLI takes no primer, and T3 alone cost 11 min to encode.

| text | condition | round trip | size B (packed) | wall s | cited | equal? |
|---|---|---|---|---|---|---|
| T3_32k | unprimed | PASS | 7,347 (7,315) | 676.3/5.3 | none | n/a (new) |
| T1_8k | unprimed | PASS | 2,890 (2,860) | 148.6/1.2 | none | n/a (new) |

### Crinkler crkpy member (enc_crkpy / dec_crkpy, with fam.py)
Driver: scratch drv/crkpy_run.py, which follows the README snippet:
- `m, _ = search(data[:65536], rule='crksat', subsets=SUB8)`, then `compress(data, m)`;
- `dec_crkpy.unz` in a fresh process.

Unprimed: the API has no primer. Not measured on the texts in the record (README:422), so the
sizes are NEW.

| text | condition | round trip | size B | wall s | cited | equal? |
|---|---|---|---|---|---|---|
| T3_32k | unprimed, crksat/SUB8 | PASS | 7,369 | 93.9/1.6 | none | n/a (new) |
| T1_8k | unprimed, crksat/SUB8 | PASS | 2,915 | 16.9/0.3 | none | n/a (new) |

### ZPAQ port (B/priorart/zpaq)
Driver: scratch drv/zp_run.py, which runs `zp_enc.compress(data, row)` and then `zp_dec.unz` in a
fresh process.
- Rows run: `max` and `ours3`, the two the shelf cites.
- Sizes are the whole block: tag, model header (198 B for max, 373 B for ours3 per the README),
  segment, stream and trailer.
- Unprimed. Not measured on the texts in the record (README:429), so the sizes are NEW.

| row | text | round trip | size B | wall s enc/dec | peak RSS | cited | equal? |
|---|---|---|---|---|---|---|---|
| max | T3_32k | PASS | 7,061 | 4.3/4.4 | 0.30 GB | none | n/a (new) |
| max | T1_8k | PASS | 3,068 | 1.1/1.1 | 0.30 GB | none | n/a (new) |
| ours3 | T3_32k | PASS | 7,093 | 7.3/7.5 | 2.33 GB | none | n/a (new) |
| ours3 | T1_8k | PASS | 3,214 | 2.0/2.0 | 2.33 GB | none | n/a (new) |

### bwt / ppm / lzdict (cand/{bwt,ppm,lzdict}, each run from its directory)
Commands:
- encode: `P enc.py F/T IN.z [F/primer.txt dec.py]`
- decode, bwt and ppm: `P dec.py IN.z OUT N [primers]`
- decode, lzdict: `P dec.py IN.z N OUT [primers]`

The sizes are file sizes. bwt's include its 4-byte primary index, as the record counts them.

| member | text | condition | round trip | size B | wall s | cited B (file:line) | equal? |
|---|---|---|---|---|---|---|---|
| bwt | T3_32k | unprimed | PASS | 8,204 | 0.7/0.7 | 8,204 (cand/bwt/results.json:41) | yes |
| bwt | T3_32k | primed | PASS | 8,188 | 0.9/0.9 | 8,188 (:47) | yes |
| bwt | T1_8k | unprimed | PASS | 3,146 | 0.3/0.3 | 3,146 (:17) | yes |
| bwt | T1_8k | primed | PASS | 3,121 | 0.4/0.4 | 3,121 (:23) | yes |
| ppm | T3_32k | unprimed | PASS | 7,810 | 0.2/0.3 | 7,810 (cand/ppm/results.json:13) | yes |
| ppm | T3_32k | primed | PASS | 7,574 | 0.2/0.3 | 7,574 (:19) | yes |
| ppm | T1_8k | unprimed | PASS | 3,092 | 0.1/0.1 | 3,092 (:11) | yes |
| ppm | T1_8k | primed | PASS | 2,896 | 0.1/0.1 | 2,896 (:17) | yes |
| lzdict | T3_32k | unprimed | PASS | 8,545 | 2.6/0.1 | 8,545 (cand/lzdict/results.json:41) | yes |
| lzdict | T3_32k | primed | PASS | 8,299 | 2.7/0.1 | 8,299 (:47) | yes |
| lzdict | T1_8k | unprimed | PASS | 3,263 | 0.7/0.1 | 3,263 (:13) | yes |
| lzdict | T1_8k | primed | PASS | 3,098 | 0.8/0.1 | 3,098 (:19) | yes |

### Runnable now / not runnable
- **Runnable now, all byte-exact on T1_8k and T3_32k:** cm1, cmmix, cm2 v1, cm2 v2, cm1k24 twin,
  cmmix twin, strong, strong2, the seven cm2 arch pairs, crk_enc/crk_dec, crkpy, ZPAQ (max,
  ours3), bwt, ppm, lzdict.
- **Not runnable:** none. Notes:
  - crk_enc's CLI takes no primer, and its default 100 hash tries cost 11 min on 32 KB.
  - zp_enc and enc_crkpy have no CLI and were driven from scratch scripts.
  - My first attempt at bwt/ppm/lzdict failed (exit 127) because of my own harness: zsh did not
    word-split the command string. The rows were re-run under bash, and only the bash rows are
    reported.

### Generated untracked files
- `gen_cm2fam.py` wrote 14 files into bootstrap/r3/arch/:
  - dec_cm2xrc.py, dec_cm2xrc1.py, dec_cm2hrc.py, dec_cm2xrans.py, dec_cm2hrans.py,
    dec_cm2xblk.py, dec_cm2hblk.py;
  - enc_cm2xrc.py, enc_cm2xrc1.py, enc_cm2hrc.py, enc_cm2xrans.py, enc_cm2hrans.py,
    enc_cm2xblk.py, enc_cm2hblk.py.
- All 14 were DELETED after benching.
- `git status --short bootstrap/r3/arch` was clean before and is clean after. No __pycache__ was
  left.
- Left in place, gitignored: bootstrap/build/r3/arch/bench.jsonl (22 rows appended) and
  bootstrap/build/r3/arch/coded/*.z.
- Everything else is in this scratch dir.
