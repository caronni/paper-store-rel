# CONVERGENCE-2026-10-23b — ruling 60's convergence re-run on the repaired c.py

*2026-10-26: committed in 8b2ad284 (an Opus refuter ran on it: "not a fixed point until the owner rules on (d')"); ruled by ruling 67; printed and closed on paper 2026-10-26, PAPER-2026-10-26.md. "Nothing committed, nothing printed", "(uncommitted)" and "No Opus refuter" below are as of the run.*

The repair of c.py (8affb97b, its third pass da0cd032: c.py 24,163 B
`c0ffe2a5…`, CRC-32 2334869721) moved c.py's length and CRC, which b.py
bakes as N2 / B2, so the fixed point of CONVERGENCE-2026-10-23.md
(c.py 24,080 B `92c48a39…`) was re-opened.  This note re-runs that
procedure (its §1 and §6) on HEAD 64289524 under two rulings of the owner
given for this run: (a) **the reader winner**: step (2) is taken when the
exact typed total FALLS in the upper case (the print's case, ruling 51),
the lower case allowed to rise by one; (b) the page bound is the constant
`R2_PAGES_BOUND = 3` of stage1/make_typed.py.  One Opus builder,
2026-10-23 21:46–23:45, on machine 1, other sessions' processes running: no
wall below is a measurement.  Nothing committed, nothing printed.

**Two deviations from the procedure as written, both the builder's, both
for the owner's ruling** (§3): the convergence does not terminate under
the procedure as written (c.py's step is a two-cycle), and HEAD's chain
build did not run at all (a tuple without a fixed point of the loop
bound).

## 1. The rounds (measured; typed total = a.py chars + data chars incl. 4 check glyphs a line)

Staging tree build/converge/v3/tree/bootstrap (`git archive` of HEAD with
build/{bundle,loader,r2,r3} and the repository's src/ linked), every
intermediate build under build/converge/v3/rN/; the working tree untouched
until the fixed point.  Steps (1) and (2) under the UPPER chain build at
(0,1,2,3,4,6), as in the record.

| step | c.py | reader | a.py | lower: typed (a.py + data, lines, G) | upper: typed | R2 lower / upper (2 p of 5,304 B) |
|---|---|---|---|---|---|---|
| start (HEAD 64289524) | 24,163 B `c0ffe2a5`, CRC 2334869721 (10 digits) | `b77779b4`, N 3,935 | 798 ch | 3,289 (798 + 2,491, 39 l, 2,335) | 3,289 (798 + 2,491, 39 l, 2,335) | 10,144 / 10,147 B, spare 464 / 461 |
| r1 (1) c.py | make_c_cv under the start's upper b.py `faa868a8` (N2 24163), 465 s: **24,176 B `b4f7de22`**, CRC 3810813523 (10 digits); cm2 10,133 (the tree's c.py 10,147 under the same primer): taken | | | 3,289 | 3,289 | **10,130 / 10,133** |
| r1 (2) reader | | run_search_cv under r1's upper a.py `720330aa`: −3.5 bits ideal (a local `a` → `u` in two functions, `(min(..)+max(..))//2` for `..>>1`, the CRC line's operands swapped `3988292384*(s&1)^s>>1`); exact 3,289 → **3,289** upper, 3,289 → 3,290 lower: the upper case does not fall, **not taken** under ruling (a) | | (3,290) | (3,289) | |
| r1 (3) search | | | search_v2 both cases: the same edit set and letters as the frozen spellings, the edits in another order; a.py byte-identical in both cases: **not written** | 3,289 | 3,289 | |
| r2 (1) c.py | make_c_cv under r1's upper b.py `761138cd` (N2 24176), 482 s: **24,163 B `c0ffe2a5`** = the start's c.py, cm2 10,147 against `b4f7de22`'s 10,133 under that primer — a **two-cycle**; by the rule of §3 `b4f7de22` stays | | | | | |
| r2 (2), (3) | | the inputs are round 1's (c.py, reader, spellings), so round 1's own results: nothing | | | | |
| check | the generator itself, make_c.py with the rule (d'), on the staging tree holding `b4f7de22` (1,065 s): "two-cycle … kept: the tree's", c.py unchanged | | | | | |

**The fixed point** (under §3's rule): c.py **24,176 B, sha256
`b4f7de22ebf2af09194dbbf8aff2678d33de333686dcd46348d1ed5b348eb881`, CRC-32
3810813523 (`e3246653`)**, 476 lines; the reader, both frozen spellings and
the template unchanged.  **Typed 3,289 lower / 3,289 upper** (798 + 2,491,
39 data lines 29–67, G 2,335 both); b.py 4,487 B (a[39:591] + the reader's
3,935 B); R2 10,130 / 10,133 B = 2 pages, **478 / 475 B spare** of 10,608,
390 chunks (204 + 186).  Against the start: typed ±0 / ±0, R2 −14 / −14 B.
Against the previous fixed point (c.py `92c48a39…`, 3,286 / 3,287 typed,
9,944 / 9,947 B, 661 B spare upper): +3 / +2 typed and +186 B of R2 — the
repair's price (c.py +96 B of text, B2 now 10 digits where it had 9: the
CRC lottery of the record's §2).

## 2. Ruling (a) in this run

The reader search found the same kind of winner the record's round 3 did
(one local respelled, the `//2` spelling, here also one operand swap),
but at this c.py it saves no glyph in the upper case (x 11,675 → 11,673
bits, G 2,335 both) and costs one in the lower: under ruling (a) it is not
taken.  No claims run was needed for a text not taken; the claims gate of
§4 compares the applied text with the previous fixed point's.

## 3. The deviations (builder's; RULED 2026-10-26 as one, ruling 67: "i think this is exactly the right choice" — the print is no longer conditional)

**(i) The two-cycle of c.py.**  make_c's pipeline is greedy and its output
depends on the primer through N2 / B2: under the chain of `c0ffe2a5` it
writes `b4f7de22`, under the chain of `b4f7de22` it writes `c0ffe2a5`
(and under the chain of the second-pass c.py `8a1f412d…`, make_c.py's own
run of da0cd032, `c0ffe2a5`).  "Until a round changes nothing" never
arrives: every round's step (1) flips c.py.  The rule adopted, as
make_c.py's new step (d'): when the pipeline's output X differs from the
tree's c.py A, the chain is built again with X as the content
(build/stage3/stage1_chain_partner/) and the pipeline run under ITS b.py;
if that gives A back, A and X are a two-cycle and the member whose own
chain is the smaller print is kept — the upper case's exact typed total,
then its R2 payload bytes (what the R2 pages carry), A on a tie;
otherwise X is written as before.  Here `b4f7de22` (3,289, 10,133 B)
against `c0ffe2a5` (3,289, 10,147 B): `b4f7de22`.  That make_c.py on either
member keeps `b4f7de22` is INFERRED from the round-1 and round-2 logs (the
rule was run only with `b4f7de22` in the tree, where it writes nothing); its wall
doubles whenever the output differs from the tree's (two pipelines,
964–1,154 s here).  Longer cycles are not detected (X is written and the
convergence's next round would see them).  The forms of the kept c.py's
own lineage are build/stage3/forms/r0547.*, the partner's r0547.partner.*;
make_c.json carries `two_cycle`.  The alternatives not taken: a gate "take
X only if it codes smaller under the current primer" (it would refuse a
c_readable.py change that costs bytes), and keeping HEAD's `c0ffe2a5`
(no generator run reproduces either member without a rule).

**(ii) A tuple without a fixed point.**  stage1/chain_v2.py make upper on
HEAD's texts with HEAD's c.py died in make_typed.pack, `no C fixed point
near the estimate`, at the frontier tuple (0,1,2,3,4,6,8,12): its a.py
codes the reader into 40 lines when the loop bound says 36–39 and into 39
when it says 40–42.  frontier() packs every tuple, so the whole build
failed — and with it make_c.py's own primer step (the same chain build),
on HEAD as committed.  The tuple is not the chosen one (3,304 at the fixed
point, 15 above).  Fix: pack raises `NoFixedPoint` (an AssertionError);
frontier records `{orders, total: None, no_fixed_point: true}` for such a
tuple and chooses among the rest; the stdout line says "no C fixed point".
Tuples with a fixed point: unchanged (at the fixed point every tuple has
one, and the builds are byte-identical to the staging rounds').  (ii) is
NOT inert at the fixed point: rule (d') always builds the partner chain of
`c0ffe2a5`, whose upper frontier holds the tuple without a fixed point, so
make_c.py cannot reproduce `b4f7de22` without NoFixedPoint.  (i) and (ii)
are therefore ONE ruling, not two.

## 4. Gates on the fixed point (the working tree after applying)

| gate | result |
|---|---|
| chain_v2.py make, both cases (build/converge/v3/final/stage1) | equivalence PASS both (units, KATs, the known answer typed and long form, census 0 of 343,227 single errors pass); typed 3,289 / 3,289; a.py 28 lines, 798 chars, longest 68; 39 data lines; reader code ev6f / EV6F; a.py, b.py, data.txt byte-identical to round 1's builds |
| identity (chain_v2.py identity), both | PASS mechanical, program (29 lines, b.py 4,487 B byte-identical), functions; and the new `committed` check (upper) |
| e2e (chain_v2.py e2e), both | **ALL PASS / ALL PASS**: LF pipe, CRLF-typed a.py on /opt/homebrew/bin/python3, pty; b.py reads lower `15@ 389/390`, `15@ 390/390`, upper `15@ 390/390` from page 0; c.py == the bundle (24,176 B); the CRLF b.py negative exit 1 at the B2 assert; headroom 478 / 475 B, 390 chunks (204 + 186), verify_grid PASS |
| count_reader | lines 138, chars 3,786, stripped 3,572, longest 69, N2 tokens 1, writes c.py True (unchanged) |
| claims (claims_cv.py; pre = HEAD's reader `b77779b4`, cv = the applied text, the same bytes — the gate is satisfied trivially, the reader did not move; the c.py-dependent coverage is e2e's 390/390 and the scans) | **identical call for call on 129 of 129 captures**, threshold 129/129, chunks lost none, new errors none; **--brk 199 of 199** |
| acceptance sets A–I, slot pass, margin, damage (run_sets_cv.py --names build/pad/names-pad.json; CV_FINAL=build/converge/v3/final) | all pass; slots 170/172 (missed (3,14), (12,16)); margin 8/9; damage alone 16/16; sets_cmp_at.py against build/pad and against the previous fixed point's run: **63 cases, 0 differ**, 75 lines.  (Without `--names` the slot spy raises KeyError 'ld' on every frame — the reader spells ld as cb — and set I fails 0/172: an invocation error of this builder's first run, kept as sets-nonames.out) |
| the photos (primer scratch/typed/r.py, N2 50533 / B2 327353449) | alone `15@ 204/557`, `15@ 204/557`, `9@ 149/557`, `6@ 149/557`; pools 1,2,3 and 1,2,4 close at `557/557`, c.py == scratch/typed/b.py |
| the `cannot read` session (cannot_cv.py, CV_PRE = HEAD's reader) | pre and cv identical: `15@ 204/557`, `cannot read`, `15@ 408/557`, `cannot read`, `9@ 557/557`; exit 0, c.py == scratch/typed/b.py |
| reader long form | gen_reader_long.py --check: the generator's output; reroll_template_cv.py --old HEAD's reader: 0 roles respelled, reader_template.py byte-identical; test_reader_identity.py **A–D PASS** (809 lines, longest 79) |
| make_c.py, twice | both runs: (d') two-cycle, `c0ffe2a5` (typed 3,289, R2 10,147) generates the tree's `b4f7de22` (3,289, 10,133), kept the tree's; c.py identical; make_c.json identical but for the wall (1,154 s, 964 s) |
| make_c.py --provenance | PASS: 20 hunks (5 docstring, 15 code: LDPC_ALPHA 1, decode_tile 3, read_scan 3, Scan.__init__ 1, aperture 1, find_lattice 5, track 4, unz 1), 3 print calls added |
| unit_c.py | ALL OK (synthetic / badcrc / plain) |
| e2e_c.py run arch stage3/c.py T1_c_v3_b4f7de22 | **PASS**: payload.bin byte-exact `78d9a4b4…`, **321 of 321 files** byte-exact, tar order, CRC never wrong, closed after **8** scans; wall 1,267 s, RSS 1,512 MB (under load) |
| e2e_c.py run arch40 … T1_c_v3_b4f7de22_40 | **PASS**: byte-exact, 321 / 321, **13** scans, 1,490 s |
| the six real scans (scratch/typed2, read-only, symlinked; each in its own directory, `NAME DPI` then an empty line) | 03-b-1200, 03-c-1200, **03-1200 at its declared 1200**, 03-b-600, 03-c-600, 03-600: **840 placed, 840 certified each**, one lattice line each, 43–54 s |
| stage1/test_identity.py + test_stage4_header.py (pytest, on build/sheets/stage1) | 6 passed |
| default repo suite | 1925 passed, 87 skipped |

## 5. The sheets (build/sheets/, `rebuild_v2.py --twice --date 2026-10-23`)

The previous print (HEAD's) moved to build/sheets/prev-print-64289524/.
The date given is 2026-10-23: the clock had not turned when the rebuild
ran (23:36).  **MANIFEST.txt and SHA256SUMS (70 files) byte-identical
between the two runs**; every 1-bit page round-tripped through ghostscript
pixel-exact (R2 2, archive 15, chain 17 of 19, print 17 of 19); the fonts
lines without warning; sheets 5–19 carry the margin header
`BOOTSTRAP     RELEASE 2115a595 - STAGE 4 PAYLOAD C3-K-R0547 Q=0.5     2026-10-23`
and `n/15`; the stage-4 PDF and the headed PostScript byte-identical to the
previous print's (they carry the release, not c.py).  The first attempt
refused at print_sheets.paragraphs' pin `pages['chunks'] == 383` (the
owner's text quotes the build's chunk count, `9@ 150/N`); moved to 390 with
its cause in a comment.

| file | sha256 | pages | bytes |
|---|---|---|---|
| **print-2026-10-23.pdf** | **4989446cc969edae50f57d4d8b175cf935b33a4829743a413465035ceb24fd4f** | 19 | 29,138,870 |
| chain-2026-10-23.pdf | ac5a898bbc2e9548ccd6b104c291455dc5194a35435df5beb2b5882e47bdc328 | 19 | 27,184,859 |
| stages1-2-listing-data-upper.pdf | 898395dde1d26a5507a4813c83607d8cd556c446637f02826f2186f6405d040e | 2 | 1,393,764 |
| stage3-r2-pages.pdf | 81d871fbe6726d59965f62f9b44d8907efedac8ddfe8d96c2ec4858fcbc7f8a6 | 2 | 475,750 |
| stage4-archive-pages.pdf | 931126cd2e94d9a5710a78e2ea870d738fd15d127f891daea5c922e2bfd10f0a (unchanged) | 15 | 23,450,954 |
| a.py (upper) | 720330aa996e0a5a21628e7086884f1ad0379b4d7c83401067b59e6afa4c8436 | | 826 |
| data.txt (upper) | b29bc54970fc549876be0597d3e0f8da2158d472a29d45875bbc56c7b181d2e5 | | 2,530 |
| b.py (upper) | 761138cd19f93f33c2be86adea114e672fb43b2c9b27b2cc931f2c6a409b35ea | | 4,487 |
| R2 payload.bin (upper) | ae22aad45585bc1121e43dda37126e4c36f83b51c622e5dc422687889edb4108 | | 10,133 |
| a.py (lower) | 73be6bf96f1b50fd9badc63e75095498859aa9a51804c4aa5b5f6a7f536a8dbd | | 826 |
| b.py (lower) | d57d8ec2e81d9a50f4e381880741f04103368d06525e0380b16aafb316f11bc1 | | 4,487 |
| R2 payload.bin (lower) | d44b3ac1a5eedb169dc826ddeaf73ccbb9d4e6883495dc53920400580c770b6f | | 10,130 |

**The QR codes** (stage1/qr/, regenerated by make_qr.py --s1 the final
build, level L, ruling 65; a second run byte-identical): qr-a = a.py, 826
B, version 20, mask 3, pbm `e7ee2c22…`; qr-d = the 39 data lines as typed,
2,608 B (`fd3ac80e…`, from data.txt `b29bc549…`), version 38, mask 7, pbm
`6e7bd3cf…`; qr.json `80ec3771…`.  zxing-cpp 3.1.1 decodes both
**byte-equal** from print-2026-10-23.pdf rendered by ghostscript at 600
and at 150 dpi and from the previews preview-print-01/02.png.

**The long form of a.py, committed** (ruling 58, item (d) of this run):
stage1/a_readable_upper.py (7,836 B) = an 11-line header ending at a
marker line + the build's upper readable.py byte for byte;
stage1/test_identity.py's new step 5 (`committed`) asserts it (negative
controls: a one-space edit of the body and a missing marker both fail).

## 6. Files changed (uncommitted)

stage3/c.py (the fixed point); stage3/make_c.py (pipeline() factored out of
main(), primer(bundle, chain), (d') the two-cycle rule, its docstring);
stage1/make_typed.py (NoFixedPoint); stage1/a_readable_upper.py (new);
stage1/test_identity.py and chain_v2.py (the committed check);
stage1/qr/qr-a.pbm, qr-d.pbm, qr.json, README.md (regenerated, numbers);
stage1/print_sheets.py (the chunk pin 383 → 390; the 3,036 B note);
stage1/make_sheets_v2.py and rebuild_v2.py (the pointer to this note);
r2reader/changeset/run_sets.py (to_pgm runs the argument-free
grid_to_pgm.py of b149721d in a scratch directory — before, any stale
cache entry crashed it; the two stale grids regenerate byte-identical),
run_sets_cv.py and cannot_cv.py (CV_FINAL / CV_PRE overrides, defaults
unchanged); this note; README.md, stage1/README.md, stage3/README.md,
R2-FORMAT.md, TYPED-STREAM.md (the numbers).  apply_cv.py and
reroll_template_cv.py were not needed (the reader did not move).

## 7. Not run

holo's own receiver on the pages; the text-page (listing sheet) runs of
c.py and the wrong-dpi / hint rows of the repair's record; §16's F5 seven
captures (inside the 129 claims); the padding spy; sizes_c.py; the
lowercase sheets rendered; build.py; slow lanes, prints, scans.  No Opus
refuter on this run.
