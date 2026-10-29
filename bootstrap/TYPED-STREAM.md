# TYPED-STREAM v3: what the finder types, and what the programs answer (2026-10-23)

The typed part of the chain as it stands on 2026-10-23 (numbers brought to
CONVERGENCE-2026-10-23b.md, the candidate print of record v3): stage 1, the
program a.py typed from its listing; stage 2, the data sheet typed at a.py's
prompt, which yields b.py; and the screen b.py shows at stage 3, when it
reads the R2 pages and writes c.py. Stage names are ruling 34's (named by
the program each one yields, RECORD-2026-10-20.md:908). Companions:
stage1/README.md (the program, its subset audit and its search),
R2-FORMAT.md (the pages b.py reads), RECORD.md (the index of rulings). Every
count below is MEASURED and carries its pointer. This version was printed
and typed on 2026-10-23 (the print v2) and 2026-10-26 (the print v3); on
10-26 the typed a.py and the b.py it wrote are sha-equal to the chain's
(bootstrap/PAPER-2026-10-26.md). The print of record of 2026-10-20
(loader/, pages/leaf3.txt and leaf4.txt) carries this spec's v2 stream;
the promotion of the print v3 is the owner's ruling.

## Stage 1: the program, typed into a file

- The finder types the listing into a plain-text file named a.py with any
  editor and runs `python3 a.py` in the folder that holds it; line 1 reads
  the file by that name (`open('a.py').read().strip()`, ruling 6 of
  RECORD-2026-10-19.md). `.strip()` and text mode make a final newline,
  trailing blank lines and CRLF line ends irrelevant (MEASURED 2026-10-19;
  the CRLF-typed a.py is a leg of every stage1/e2e.py run, stage1/RESULTS.md
  "End to end"). A BOM or an editor's auto-indent are not absorbed.
- Size: 28 lines, 798 characters in the candidate print of record v3
  (CONVERGENCE-2026-10-23b.md; ruling 53's `,'big'` gone); before: 807 characters in the build of the stand-in bundle
  (stage1/RESULTS.md "The typed totals"; the default order tuple
  (0,1,2,3,4,6,8)); 805 characters when the R2 content is c.py and the
  shorter tuple (0,1,2,3,4,6) is chosen (stage3/RESULTS-2026-10-22.md §6,
  "The stage-1 chain"). The print of record's a.py was 29 lines, 826
  characters (PAPER-2026-10-20.md).
- The listing: Python's symbols, lowercase names, digits; capitals appear
  only inside the alphabet literal and in the reader's 4-glyph code of the
  uppercase build. Every space, leading and inside a line, is printed as a
  middle dot (ruling 30, RECORD-2026-10-20.md:727; 74 dots, stage1/RESULTS.md
  "The leaves"), one space per indent level, lines at most 72 characters.
  Each listing line carries its number and its 4-glyph code in the right
  margin. The listing leaf is set in Menlo (ruling 51,
  RECORD-2026-10-20.md:1324). The listing and the data sheet are bare: an
  identity line with the print date, no plate text (ruling 44,
  RECORD-2026-10-20.md:1172, which calls both "stage 1's leaves").
- Layout of the program: line 1 reads its own text; the definitions follow
  (the alphabet, the line check, the decompressor `d` with the order tuple
  as a defaulted parameter; ruling 43, items 3 and 7); then the main part:
  the self-dump, the data-entry loop, the decode, the assert, the write of
  b.py.

## What the finder sees from a.py

- **The self-dump.** For every line of its own text the program prints the
  line's number and its 4-glyph code (`1 MQVH` style, the number counted
  from 1). Each code must equal the code in the margin of the listing. A
  differing code names the line to fix; a dropped or extra line shifts every
  code after it. Python stopping before any code is printed names its own
  line.
- **The prompt.** The program then shows `[n]`, the number of the data line
  it expects (`input([n])`, ruling 1 of RECORD-2026-10-19.md). The data
  prompts continue the listing's numbering: with a 28-line a.py they start at
  `[29]` (the self-dump shares the counter; stage1/RESULTS.md "The a.py").
  A refused line brings the same `[n]` back.
- **The end.** After the last data line a.py decodes the data into the
  reader's text, asserts the reader's 4-glyph code and writes `b.py`. It
  prints nothing more. Silence is success; a traceback means a slip got
  through, and the remedy is to run a.py again and type the data again
  (nothing is kept between runs).

## Stage 2: the data sheet, typed at a.py's prompt

- Each data line is printed with its prompt number, then 60 glyphs in 12
  groups of 5, then the 4 check glyphs (ruling 4 of RECORD-2026-10-19.md;
  stage1/leaves.py). Spaces may be typed or left out: a.py strips them
  (ruling 2 of RECORD-2026-10-19.md). The last line is shorter.
- **Lines and glyphs.** In the candidate print of record v3
  (CONVERGENCE-2026-10-23b.md, c.py 24,176 B as the R2 content): 39 data
  lines (prompts 29 to 67), 2,335 glyphs in both cases, a typed total of
  3,289 / 3,289 lowercase / uppercase (3,286 / 3,287 at the first
  convergence, CONVERGENCE-2026-10-23.md, on the c.py before the repair).
  Earlier: under the reader as it stands (the grey padding
  of ruling 59 applied, changeset/RESULTS-2026-10-22.md §20): 40 data
  lines, 2,359 / 2,358 glyphs lowercase / uppercase, a typed total of
  3,326 / 3,325 with the stand-in bundle; 40 data lines (prompts 29 to 68),
  2,354 / 2,353 glyphs and 3,319 / 3,318 typed when the R2 content is c.py
  (§20, part 2). Before the padding: 2,368 glyphs and 3,335 / 3,335 under
  the reader of §19 (the literal `@`, ruling 58; §19 (A); 3,337 / 3,336 in
  §18); 42 lines and 3,465 / 3,463 with c.py and the reader of ruling 52
  (stage3/RESULTS-2026-10-22.md §6). The data sheet is one sheet (ruling
  44's 48 lines fitted one).
- **The alphabet** is base-32 Crockford, now UPPERCASE:
  `0123456789ABCDEFGHJKMNPQRSTVWXYZ` (no I, L, O, U), set in Andale Mono
  (ruling 51). Why uppercase: the OCR test of 2026-10-21 (ruling 42,
  RECORD-2026-10-20.md:986; pages/OCR-2026-10-21.md) found that uppercase
  removes q read as g, the phone camera's largest slip class on paper (7 of 19
  single-glyph slips, PAPER-2026-10-20.md), and that OCR does not pick the
  face; the owner picked Andale Mono uppercase on the paper-test set
  (ruling 51). Base 32 keeps one valid glyph per look-alike class; base 36
  was ruled out on that structural point (ruling 42). Glyphs typed in the
  other case fail the line check and are retyped (stage1/e2e.py injects
  them). A junk glyph on a line that passes its check becomes a silent −1
  digit and the run ends at the reader-code assert (stage1/RESULTS.md, the
  refuter's notes).
- **The line check (Horner).** For data line n with payload t (spaces
  removed, the 4 check glyphs excluded): start from c = n, then for each
  byte x of t, c = (x + c) · 1000003; the check glyphs are the alphabet's
  glyphs at c>>15&31, c>>10&31, c>>5&31, c&31, the low 20 bits of c
  (ruling 5 of RECORD-2026-10-19.md, multiply after add; ruling 6 of
  RECORD-2026-10-20.md keeps Horner at the keyboard and CRC-32 on the page).
  The self-dump uses the same function on each listing line with its line
  number; the reader's code is the same function over the whole decoded
  reader with n = 0.
- **What the check catches.** Single substitutions, transpositions at any
  distance and an unchanged line at the wrong prompt never pass (proved,
  ruling 5 of RECORD-2026-10-19.md; the stage1/ build's census, 0 of 343,227
  single errors, wrong numbers and transpositions pass, stage1/RESULTS.md
  "The identity test"). A random wrong line passes with 1 in 1,048,576.
  Stated and accepted (ruling 17, RECORD-2026-10-20.md:264): a line typed at
  the wrong prompt passes when its first glyph is also off by exactly the
  difference of the line numbers, 1 in 2,414 of such double slips; line n
  retyped at prompt n+1 with its first glyph one code point lower always
  passes.
- **Self-zeroing, known and out.** The check can be made self-zeroing (the
  encoder solves the four check glyphs so that the line's whole Horner value
  is 0 mod 2^20, and a.py tests `k(n,line)==0`): −37 characters in a.py, but
  37 % of lines at full strength have no 4-glyph solution and need a moved
  line break (RECORD-2026-10-20.md, "The a.py change list"). Item 5 of that
  list, ruled OUT by ruling 43 (RECORD-2026-10-20.md:1078) for the varying
  line length; the error probabilities would not have changed.
- **The data is one number.** The glyphs of all data lines, payload only, in
  order, are the base-32 digits of one integer x, the state of a
  big-integer rANS decoder (ruling 18, RECORD-2026-10-20.md:275). a.py's `d`
  decodes them into b.py with a.py's own text as the context primer; the
  model is cm2's count mixing; no window, no renormalisation, no length field.

## Stage 3 as the finder meets it: b.py reads the R2 pages

- The finder runs `python3 b.py` in the same folder and gives it photos of
  the R2 pages as P5 PGM files, one file name per line at the prompt
  `file: ` (ruling 46, RECORD-2026-10-20.md:1282). Frames may be whole pages
  or parts, in any orientation, pages in any order, several per page; b.py
  pools the chunks over the session (R2-FORMAT.md, Decoding). A typed 0/1
  grid of a page reaches b.py through the Plate's one-liner,
  r2reader/grid_to_pgm.py (ruling 49, RECORD-2026-10-20.md:1299).
- **The progress line** (ruling 56 as amended, RECORD-2026-10-20.md:1546;
  ruling 58, RECORD-2026-10-20.md:1738): one line per file, `N@ H/T`: N the
  bullseyes found in the frame (zero means shoot again; many with no new
  chunks means move the camera), `@` the target mark, H the distinct chunks
  held over the session, T the header's chunk count or `?` before a header
  is read; `cannot read` alone for a file that fails to load. Examples from
  the four phone photos of 2026-10-20: `15@ 204/557`, `15@ 408/557`,
  `9@ 557/557` (changeset/RESULTS-2026-10-22.md §18). No file name, no
  block count, no done flag: b.py exits after writing c.py.
- **The end.** When every chunk is held and the data's CRC-32 matches the
  header's, b.py decodes the data with the same decompressor primed by its
  own bytes, asserts the CRC-32 of the result against a baked constant B2
  (ruling 22, RECORD-2026-10-20.md:331) and writes c.py. A changed b.py (an
  editor's re-save, an extra newline) or pages compressed for another
  reader end in AssertionError and no file; pages of another payload add
  nothing (R2-FORMAT.md, Decoding, steps 4 and 7). Never open or re-save
  b.py.
- **Size of b.py's typed text.** 138 counted lines, 3,786 characters,
  longest 69, at both convergences (CONVERGENCE-2026-10-23.md §3; the
  re-run of CONVERGENCE-2026-10-23b.md left it unchanged); b.py itself
  4,487 B with N2 24176 / B2 3810813523. Before them 138 lines, 3,781 characters,
  longest 69 (count_reader.py, changeset/RESULTS-2026-10-22.md §20,
  2026-10-23: the grey padding of ruling 59 applied, the sampler's clamps
  gone and one image of mid-grey appended at load). Before it, 140 lines
  and 3,812 characters at §19 (A), where the progress line first spelled
  `@` as a literal, −2 / −1 typed against §18's `%c` of 64.

## The typed subset and its audits

- **a.py** (stage1/make_typed.py `audit`, run on every build; stage1/README.md
  "The typed subset"): no imports; no float or complex literal and no
  numeric literal but plain digits; no `/` or `/=` (`//` is fine, ruling 11
  of RECORD-2026-10-19.md); no `exec`/`eval`/`compile`; capitals only
  inside the alphabet literal and the reader's code; no identifier `l` and
  no lone `l`; no backslash, double quote or tab; exactly one print, the
  self-dump; the program ends with the assert and the write of b.py; the
  definitions bind exactly the alphabet, the line counter, the data
  number, the line check and `d`, the check above `d`; the b.py slice
  matches the definitions' offsets; lines at most 72, no trailing space.
  The builtins a.py calls are not audited.
- **b.py** (r2reader/count_reader.py, the typed region between the READER
  markers minus the shared block): flagged are lines over 72, `;` and `~`,
  an import, a float or complex literal, true division, a call to a builtin
  outside its list (`open` and `input` among the allowed) and a
  module-level binding of `d`, `q` or `k` (the print of record's loader
  names; the new a.py binds other letters, stage1/RESULTS.md "The a.py");
  the token N2 and the write of c.py are reported, not flagged. The
  character `@` is flagged as an operator or decorator and ALLOWED inside
  a string literal since 2026-10-23 (ruling 58; the ban anywhere was the
  hand-typed a.py's rule from the typist era, where `@` marked an
  indent).
- **Python floor 3.11** (ruling 53, RECORD-2026-10-20.md:1451):
  `int.from_bytes` and `to_bytes` default to big-endian from 3.11, so b.py
  drops its `'big'` arguments and a.py dropped its one in the first
  convergence (6 typed characters, 39da92bc). Nothing enforces the floor
  at run time: under an older interpreter b.py reports every frame `cannot
  read` (same section); a probe in a.py was refused (ruling 63, "probe
  means growth"), and sheet 1 says "Run a.py with Python >= 3.11" (ruling
  65).

## Print-time constants

a.py carries as literals the reader's byte count, its 4-glyph code, the loop
bound of the data prompts and the two offsets of the slice it copies into
b.py; b.py carries the decompressed length N2 of c.py and its CRC-32 B2.
They are specific to one print and set by the encoder's fixed point
(stage1/make_typed.py). The typed data lines change with every c.py,
because b.py bakes c.py's N2 and B2; the R2 pages change with every b.py,
because their payload decodes only against b.py's exact bytes (ruling 33,
RECORD-2026-10-20.md:879).

## Changes

- **v3, 2026-10-23.** Stage names of ruling 34 (a.py writes b.py from the
  data sheet of stage 2, b.py writes c.py from the R2 pages of stage 3);
  the a.py of bootstrap/stage1/ (rulings 43, 44); uppercase data glyphs in
  Andale Mono, the listing in Menlo (rulings 42, 51); the
  data prompts continue the listing's numbering; b.py's prompt `file: `,
  progress line `N@ H/T` and P5-only input with the grid one-liner
  (rulings 46, 49, 56, 58); b.py's grey padding of the image buffer
  (ruling 59); the Python 3.11 floor (ruling 53); the subset audits of
  both programs.
- **v2, 2026-10-20** (git d84a9637). The 29-line rANS loader writing r.py =
  its definitions + the reader; lowercase base-32; 3,895 typed in the print
  of record; the reader read PGM or 0/1 text and wrote b.py.
- **v1, 2026-10-19** (git 33736db8). One program typed into a file, the
  Horner check at four glyphs, base-32 lowercase, `[n]` prompt; the reader
  wrote r2.bin.
- **v0, 2026-10-18** (git 1628c23b). A 12-line checker typed unchecked,
  then checked lines with a 3-glyph position-weighted sum, `~` and `@` as
  newline and indent marks, `###` between code and data, `RUN` at the end.

The full texts of v0 to v2 are in git history at the commits named.
