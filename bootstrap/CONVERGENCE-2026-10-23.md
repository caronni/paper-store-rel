# CONVERGENCE-2026-10-23 — the three searches to their fixed point (ruling 60)

*2026-10-26: superseded by CONVERGENCE-2026-10-23b.md (the re-run on the repaired c.py, ruling 67); kept as written.*

The owner, 2026-10-23 (ruling 60): "we have the time, do the full
convergence before generating the pdf of stage 1-3. consider this going for
the next version of record, assuming the review of c does not show
deficiencies / gaps."  Ruling 53 (a.py's `,'big'` goes, floor 3.11) and
ruling 61 (c.py keeps its archive layer) applied.  One Opus builder,
2026-10-23 01:30–03:30, on machine 1, other sessions' processes running (a holo
receiver decode at ~3 cores and 19 GB the whole time): no wall below is a
measurement.  Nothing committed, nothing printed.

**The caveat of ruling 60 is not met yet.** The deep review of c.py's source
(stage3/review/, commit 7b7c17f0, landed during this run) reports four
confirmed reach gaps in c_readable.py and asks for the owner's rulings.
This set is the candidate print of record v2 *as c_readable.py stands
today*; any change to c_readable.py changes c.py, hence b.py's baked N2/B2,
hence re-opens the convergence (the procedure in §6 re-runs it).

## 1. The circle and the round

- c.py is make_c.py's pipeline (minified-g → M1 → M2 → M3) scored under a
  primer; the chain's R2 payload is cm2(c.py, b.py, a.py's default tuple),
  so the primer that matters is **the chain's b.py** = a.py's slice + the
  reader with c.py's length and CRC-32 baked (N2/B2). make_c.py scored under
  the stand-in build's lowercase b.py at (0,1,2,3,4,6,8).
- the reader's search scores the reader under a.py (stage 1's primer); the
  earlier runs used the lowercase a.py of the stand-in build at
  (0,1,2,3,4,6,8).
- a.py's search scores the typed total, which includes the data lines = the
  reader coded under a.py; the reader text carries c.py's N2/B2.

One round = (1) c.py under the current chain b.py; (2) the reader's search
under the current a.py, applied only if the exact typed total drops and the
text reads identically call for call on the 129 captures; (3) a.py's search
(both cases) with c.py as the content and the current reader, the frozen
spellings replaced only if the total drops; `,'big'` removed once, before
round 1's step 3. **Primer case and tuple:** steps (1) and (2) score under
the UPPERCASE chain build (the case of record, ruling 51) at the tuple the
chain's frontier chooses with c.py as the content, (0,1,2,3,4,6) (a choice
made here; the earlier runs used lowercase). **Gate of step (2):** the
exact typed total must not rise in either case and must fall in one (the
precedent of RESULTS §19, where a rewrite priced +1 in the lower case was
not taken). The page bound of the frontier stays the record's (3 pages,
build/r2/payload.json).

The rounds ran in a staging tree (build/converge/tree/bootstrap, a `git
archive` of HEAD with build/r2, bundle, loader, r3 linked), so the working
tree was untouched until the fixed point; every intermediate build is under
build/converge/rN/.

## 2. The rounds (measured; typed total = a.py chars + data chars incl. 4 check glyphs per line)

| step | c.py | reader | a.py | lower: typed (a.py + data, lines, G) | upper: typed (a.py + data, lines, G) | R2 lower / upper (2 p, 5,304 B each) |
|---|---|---|---|---|---|---|
| start (§20, 13fae4cf) | 23,793 B c26869af, CRC 221663327 (9 digits) | 4677ed3f, N 3,929 | 805 ch | 3,319 (805 + 2,514, 40 l, 2,354) | 3,318 (805 + 2,513, 40 l, 2,353) | 9,966 / 9,971 B, spare 642 / 637 |
| r1 (1) c.py | **24,089 B a68e72a2**, CRC 1032542605 (10 digits): cm2 9,941 under the start's upper b.py (the tree's c.py 9,971) | N 3,930 | 805 | 3,320 (+1) | 3,319 (+1) | 9,935 / 9,940 |
| r1 (2) reader | | **search −25.5 bits**: moves cb, fr, f, v; 4 locals; 3 tuple orders; N 3,939; claims 129/129 identical: taken | | 3,315 | 3,314 | 9,935 / 9,940 |
| r1 (3a) `,'big'` | | | 799 (−6) | 3,309 | 3,308 | 9,938 / 9,943 |
| r1 (3b) search | | | **798**, new spellings (search tuple (0,1,2,3,4,6)): taken | 3,291 (798 + 2,493, **39 l**, 2,337) | 3,292 (798 + 2,494, 39 l, 2,338) | 9,944 / 9,950 |
| r2 (1) c.py | **24,110 B 6ed1aa7c**, CRC 1290702766: cm2 9,948 (r1's c.py 9,950) | | | 3,291 | 3,292 | 9,943 / 9,949 |
| r2 (2) reader | | **search −22.6 bits**: 3 locals, comm, 2 shifts, flip; N 3,935; claims 129/129: taken | | 3,290 | 3,288 | 9,944 / 9,949 |
| r2 (3) search | | | 798, new letters: taken | 3,288 | 3,287 | 9,947 / 9,949 |
| r3 (1) c.py | **24,080 B 92c48a39**, CRC 986467037 (9 digits): cm2 9,947 (r2's c.py 9,949) | N 3,934 | | **3,286** (798 + 2,488, 39 l, 2,332) | **3,287** (798 + 2,489, 39 l, 2,333) | **9,944 / 9,947** |
| r3 (2) reader | | search −2.9 bits (a local a → u in two functions; `(min(..)+max(..))//2` for `..>>1`); exact 3,287 / 3,286 (lower +1, upper −1): **not taken** | | (3,287) | (3,286) | |
| r3 (3) search | | | upper: the spelling itself; lower: the same edits and letters in another order, a.py byte-identical; no drop: **not written** | 3,286 | 3,287 | |
| check (1) | make_c_cv under r3's chain b.py (808378e3): **24,080 B 92c48a39, byte-identical** | | | | | |

**The fixed point is reached in round 3**: round 3 changed c.py only, and
the round after it changes nothing — its step (1) under round 3's b.py
regenerates c.py byte for byte (the check row; and make_c.py itself, twice,
§4), and its steps (2) and (3) are round 3's own (the same three texts in).
Total movement, start → fixed point: **3,319 / 3,318 → 3,286 / 3,287 typed
(−33 / −31), 40 → 39 data lines**, a.py 805 → 798 characters; c.py
23,793 → 24,080 B of text, 9,971 → 9,947 B of R2 payload (upper), still 2
pages with 661 B spare (lower 664).

What moved the most: the a.py search re-run at the tuple the chain actually
chooses with c.py, (0,1,2,3,4,6) (the frozen spellings were searched at the
stand-in's (0,…,8)): −17 / −16 in round 1 alone. A finding for the record:
**c.py's CRC-32 is a ±1 typed-character lottery** — B2 is baked as a decimal
literal, 9 or 10 digits by chance (round 1's and round 2's c.py had 10 digits,
the start's and the fixed point's 9); the pipeline scores R2 bytes and does
not see it.

The upper case's round-3 reader winner (3,286 upper / 3,287 lower) is the
owner's call if he wants the print's case one character lower; taking it
re-opens a round (b.py changes, so c.py's primer changes).

## 3. The fixed point's texts (applied to the tree)

| file | before (13fae4cf) | after |
|---|---|---|
| stage1/template.py | f5d6c689… | **3d342f49…** — the one edit, `Hist.to_bytes(Len+Count,'big')` → `Hist.to_bytes(Len+Count)` (the single `'big'` and the single `to_bytes` of TEMPLATE, asserted), and three docstring lines: d's to_bytes takes the default byte order, a.py and the b.py it writes need Python ≥ 3.11 |
| stage1/frozen_lower.json | e9434c24… | **767a3ee6…** (round 2's search) |
| stage1/frozen_upper.json | 7adfbe29… | **5af8e8d3…** (round 2's search) |
| r2reader/reader_lite_v1.py | 4677ed3f… (9,554 B) | **b77779b4…** (10,472 B): the typed region of rounds 1 and 2 (rw/common.put_back), one header paragraph added (changeset/apply_cv.py; the old text saved as build/converge/final/reader_before.py) |
| r2reader/reader_template.py | 2a08d8ad… | **d7b5b15c…** — TEMPLATE re-roled and ROLE_TABLE re-lettered and re-ordered by changeset/reroll_template_cv.py (below) |
| r2reader/gen_reader_long.py | — | **b6ad92ce…** — two COMMENTS keys follow the new tuple orders (`Bulls: Bulls_P, Bulls_X, Bulls_Y =`, `Walk: Walk_Cell, Walk_Placed =`), their text reordered to match; nothing else |
| r2reader/reader_long_v1.py | 1c3b48b8… (813 lines) | **98249187…** (809 lines), regenerated |
| stage3/c.py | c26869af… (23,793 B) | **92c48a39f9eb115908921c5bdbe060ec8987903abaa4f0ef6efbfbfbfb30d3b7** (24,080 B, CRC-32 986467037), one atomic copy (cp + mv) at 02:40:30, logged in build/converge/final/c_swap.log |
| stage3/make_c.py | 6718e859… | **7cf1aa93…** — the primer: the chain's upper b.py (stage1/chain_v2.py make upper with the tree's c.py as the content, rebuilt every run into build/stage3/stage1_chain/, asserted to carry the tree's c.py's length) at (0,1,2,3,4,6) (ev.Handle's default set to it), and c.py written atomically and only when it differs |

The reader's respelling, as the re-roll measured it: 7 roles respelled
(Axes_A c→sz, Bits_Check p→r, Combs_Bit y→sz, Fit_Pitch p→r, Grey_Y p→r,
Read_Grey r→z, Walk_Placed f→p), no module-level name moved, five
definitions moved (cb and fr to the top, f after ax, v before sp and ft),
eight equivalent spellings (tperm ×3, comm `(x+t)*16`, shift `r>>8` and
`>>8` for `//256`, flip `t>23`). count_reader: lines 138, chars 3,786,
stripped 3,572, longest 69, N2 tokens 1, writes c.py True (before 138 /
3,781 / 3,567 / 69).

reroll_template_cv.py carries the roles by MATCHING rather than by the
hand-kept SCOPES / FROM_LINE / AT tables of reroll_template{,_comp,_prog,_pad}.py:
the old TEMPLATE and the new region are walked in parallel (definitions by
name, other statements in order), admitting exactly rewrites.py's moves
(commutative swap, single-comparison flip, tuple permutation, shift);
proved by role → letter a function, rename(TEMPLATE, letters) == the region,
and test_reader_identity.py.

## 4. Gates on the fixed point (the tree after applying)

| gate | result |
|---|---|
| stage1/make_typed.py, both cases, c.py as the content (stage1/chain_v2.py make → build/converge/final/stage1) | equivalence PASS both (units, KATs, the known-answer program as typed and as long form, census 0 of 343,227 single errors pass) on env python 3.14.8; **typed 3,286 lower / 3,287 upper**; a.py 28 lines, 798 chars, longest 68; 39 data lines (29–67); reader code ernd / ERND; slice a[39:591]; b.py 4,486 B; orders (0,1,2,3,4,6); a.py, b.py, data.txt byte-identical to round 3's builds |
| stage1/test_identity.py (chain_v2.py identity) | both cases PASS: mechanical, program (same screen, b.py byte-identical 4,486 B), functions |
| stage1/e2e.py both cases (chain_v2.py e2e) | **ALL PASS / ALL PASS**: LF pipe on env python, the CRLF-typed a.py on /opt/homebrew/bin/python3 (3.14.8, ≥ 3.11), the pty; b.py reads `15@ 382/383`, `15@ 383/383`; c.py == stage3/c.py (24,080 B); the CRLF b.py negative exit 1 at the B2 assert, no c.py; R2 9,944 / 9,947 B, 2 pages, headroom 664 / 661 B, 383 chunks (204 + 179), verify_grid PASS |
| count_reader | pass (above) |
| claims, §20's text vs the fixed point's (changeset/claims_cv.py; names unchanged) | **identical call for call on 129 of 129 captures**, threshold identical 129/129, chunks lost none, new errors none; **--brk: 199 of 199** break frames identical, threshold 199/199 (rounds 1 and 2 each also 129/129 against their own pre-step text) |
| acceptance sets A–I, slot pass, margin, damage alone (changeset/run_sets_cv.py; sets_cmp_at.py against build/pad) | all pass; slots 170/172 (missed (3,14), (12,16)), per partial frame identical; margin 8/9; damage alone 16/16; **63 cases, 0 differ**, 75 lines compared |
| the photos (primer scratch/typed/r.py as b.py, N2 50533 / B2 327353449) | alone `15@ 204/557`, `15@ 204/557`, `9@ 149/557`, `6@ 149/557`; pools 1,2,3 `15@ 204/557`, `15@ 408/557`, `9@ 557/557` and 1,2,4 … `6@ 557/557`: **both close, c.py == scratch/typed/b.py (579e5f1c…)**; identical to §20's line for line |
| the `cannot read` session (changeset/cannot_cv.py) | pre and cv identical: `15@ 204/557`, `cannot read`, `15@ 408/557`, `cannot read`, `9@ 557/557`; exit 0, c.py == scratch/typed/b.py |
| long form | reroll_template_cv.py, gen_reader_long.py, test_reader_identity.py: **A–D PASS** (A: 4,426 B byte for byte, 174 roles; B: 809 lines, longest 79; C: both sets close at `file: 15@ 607/607`, c.py == bundle; D: 6 + 3 mutations seen) |
| make_c.py, twice (the chain primer) | both runs: (b') checks == holo r0547 edges (14,611), FORMAT_ID holo/v2/1i200-k-r0547-p100-v1@35x24; M1 30 aliases, ast-equivalent; M2 351 bindings renamed, bijective; M3 45 attributes; M1 → c.py 375 bindings + 45 attributes, bijective; no import; **c.py 92c48a39… identical to the tree's, both runs** (486 s, 473 s) |
| unit_c.py | ALL OK: synthetic / badcrc / plain on c_readable.py and c.py |
| scan qualification (stage3/e2e_c.py run arch stage3/c.py T1_c_cv_92c48a39) | **PASS**: 15 arch pages (1200 dpi, shuffled), closed after 8 scans at 301 s; volume SHA-256 78d9a4b4… == the T1 container, payload.bin byte-exact; archive CRC right (no `CRC-32 wrong`); **321 of 321 files byte-exact**, paths printed in tar order; exit 0; wall 1,142 s, decode+CRC 786 s, max RSS 1,512 MB (build/stage3/e2e/T1/result_T1_c_cv_92c48a39.json; under load) |

## 5. The sheets (build/sheets/, rebuilt by bootstrap/rebuild_v2.py)

The interim set of 13fae4cf moved to build/sheets/interim-13fae4cf/.
`rebuild_v2.py --twice`: **MANIFEST.txt and SHA256SUMS (49 files)
byte-identical between the two runs.** Every 1-bit page rendered back by
ghostscript at 600 dpi equals its source pixel for pixel (stage 3, the R2 pages: 2; stage 4, the
archive pages: 15; chain: 17 of 19; the chain's two text sheets are grey).

| file | sha256 | pages | bytes |
|---|---|---|---|
| stages1-2-listing-data-upper.pdf | 1172e2c93006111e19797cff9a55c2f9db173db40615f0ff342e0547f6cfbc3c | 2 | 1,393,693 |
| stage3-r2-pages.pdf | dcaf5310ac7e6b211bb2324650f896c6a538c2c0b074cecedf85ec02ae582bac | 2 | 475,726 |
| stage4-archive-pages.pdf | 40272f41191b25ab60dd026ecc4bf19d7317a253fbd5637285c24b66ee725483 | 15 | 23,399,536 |
| chain-2026-10-23.pdf | e13dac6bad829b0feefb856fb23bc57d3977144a4ab254b54e4857405c56dc55 | 19 | 27,132,599 |
| a.py (upper) | c38c70a7deec94e4799f29c277624b687a161be0ca11381ab0ef25d6d90416b2 | | 826 |
| data.txt (upper) | c21673a0dceb7934b70e5dee7550ed21c5091ddb4f5658f8c446cb30b1fd2d6a | | 2,528 |
| b.py (upper) | 808378e3cc126acb31309610aba543ad66247de314bb2f33e6e399bc37838819 | | 4,486 |
| R2 payload.bin (upper) | 785d134a2c065d92d6f991bdb431ecfbb976ce6ee03ba1aab4be00f6502ed31a | | 9,947 |
| a.py (lower) | ddb3b9947476cbadac0015c20d569f6052f0daec38e8db5615b151c4bf8126c5 | | 826 |
| b.py (lower) | b86502fb230bef5536b85db611a0efbb2aa3b5388abad5177ba7d863e132add0 | | 4,486 |
| R2 payload.bin (lower) | 1938607497af817ce1c6fdf2e0ea5106da4e1063765eef374a5f85ddd8226aac | | 9,944 |

- stages1-2-listing-data-upper.pdf: leaf 3, the listing in Menlo (28 lines, every space a
  middle dot, the codes), head `VOLUME {V}  R1 LEAF 3  THE PROGRAM
  2026-10-23`; leaf 4, the data in Andale Mono (lines 29–67), head `VOLUME
  {V}  R1 LEAF 4  THE DATA    2026-10-23`; one sheet each, 300 dpi.
- stage3-r2-pages.pdf: the 2 R2 pages of gen.py at 600 dpi, 1 bit, each with
  its caption `VOLUME {V}  R2 LEAF n OF 2    2026-10-23` 2 mm below the grid.
- **stage4-archive-pages.pdf: the archive pages did not change** (they carry
  the release, the record's T1 container 78d9a4b4…, not c.py): the same
  volume build/stage3/e2e/T1/vol, each page checked against its imagemask
  and manifest shas, and the 15 pages **pixel-identical** (ghostscript,
  600 dpi) to the interim PDF's. Its BYTES differ from the interim's
  55a3efdc…, and the interim's bytes were not reproducible: Pillow's PDF
  writer stores a 1-bit page as its group-4 TIFF minus the 8-byte header,
  so the stream carries libtiff's IFD, which holds a byte libtiff leaves
  uninitialised (measured: two saves of the same pages differed in that one
  byte). make_sheets_v2.py cuts that TIFF to the strip alone: the stream is
  the G4 data, deterministic, the same pixels.
- chain-2026-10-23.pdf: all 19 in order at 600 dpi; previews preview-01..19.png.

These are viewing PDFs: a print of record goes through scripts/ as an
imagemask job (.claude/rules/hardware.md); nothing of this set has been printed.

## 6. The entry point and the tools

`bootstrap/rebuild_v2.py [--out DIR] [--vol DIR] [--date D] [--twice]`
regenerates the candidate print of record v2 from the committed texts and
frozen spellings: stage 1 both cases with c.py as the content
(stage1/chain_v2.py make, make_typed's fixed point, proofs and second
byte-compared build), the R2 pages both cases (chain_v2.py pages: e2e.py's
page step), the sheets (stage1/make_sheets_v2.py), MANIFEST.txt and
SHA256SUMS; it asserts byte identity against a previous run's manifest found
in OUT, or between its two runs with --twice, and prints the diff if not. It
runs no search (the spellings are frozen, c.py is the committed text) and
touches neither build.py nor bootstrap/loader/. The stage-3 volume is an
input (stage3/e2e_c.py volume's output, checked page by page), not rebuilt.

To re-run the convergence after a c_readable.py change: make_c.py (now under
the chain primer) → stage1/chain_v2.py make (both) → changeset/run_search_cv.py
(+ chain_v2.py make with --reader, claims_cv.py) → stage1/search_v2.py (both,
CV_* environment) → back to make_c, until a round changes nothing; then
apply_cv.py, reroll_template_cv.py, gen_reader_long.py,
test_reader_identity.py, rebuild_v2.py.

New files: stage1/chain_v2.py, stage1/search_v2.py, stage1/make_sheets_v2.py,
stage3/make_c_cv.py, r2reader/changeset/{run_search_cv, names_cv, claims_cv,
apply_cv, reroll_template_cv, run_sets_cv, cannot_cv}.py, rebuild_v2.py, this
note. Outputs (gitignored): build/converge/ (tree/, r1–r4/, final/ with
reader_before.py, the before-images, logs/, claims/, sets/, cannot/,
stage1/), build/sheets/, build/stage3/stage1_chain/, build/stage3/make_c.json
(the previous record's copy in build/converge/final/make_c.prev-c26869af.json).

## 7. Not run

Walls (load from other sessions). The arch40 (40 %-blanked) scan run of
c.py and holo's own receiver on the pages (only the plain set, as asked).
§16's F5 seven captures (inside the 129 claims). The padding spy. sizes_c.py
(make_c_cv.py and make_typed report the exact cm2 sizes used here). The
lowercase sheets (built and e2e-passed, not rendered). build.py, slow lanes,
prints, scans.

## 8. For the lead to fold in (not edited here)

R2-FORMAT / the READMEs, one sentence:

> The candidate print of record v2 (bootstrap/CONVERGENCE-2026-10-23.md,
> ruling 60's fixed point, pending the owner's rulings on the c.py review of
> 7b7c17f0): a.py is 28 lines, 798 characters, its d calling to_bytes
> without the byte order (Python ≥ 3.11), and types 3,287 characters in the
> uppercase print (3,286 lowercase) with 39 data lines; b.py is 4,486 B
> (a[39:591] + the reader's 3,934 B); c.py is 24,080 B (sha 92c48a39…,
> CRC-32 986467037), coded under b.py at a.py's default tuple (0,1,2,3,4,6)
> into 9,947 B (lowercase 9,944) = 2 R2 pages with 661 B spare, 383 chunks
> (204 + 179); make_c.py now scores c.py under that chain b.py, and
> bootstrap/rebuild_v2.py regenerates the sheets byte for byte.

## 9. Addendum (the lead, 2026-10-23): the sheet files renamed to ruling 34's stages

The refuter caught the builder's old stage numbering in the sheet names
(the R2 pages as stage 2, the archive pages as stage 3). make_sheets_v2.py
and rebuild_v2.py now name them stages1-2-listing-data-upper.pdf,
stage3-r2-pages.pdf, stage4-archive-pages.pdf and chain-DATE.pdf; the
manifest's wording follows. Rebuilt with `rebuild_v2.py --twice` on a
clean directory: byte-identical between the two runs (the first attempt
refused, as designed, against the old-named manifest still present). The
table above carries the renamed files' shas; the PDF bytes differ from
the builder's only through the file names the PDFs carry, every 1-bit
page pixel-identical (ghostscript, 17 of 19). The superseded old-named
set sits in build/sheets/superseded-oldnames/, the pre-convergence
interim set in build/sheets/interim-13fae4cf/.
