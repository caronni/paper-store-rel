# stage1/ — results of the first build (2026-10-21, machine 1)

*2026-10-26: a 10-21/22 record. The refuter is at the end of this file; the paper-test set was printed 2026-10-22 (rulings 44, 51); the v3 chain was typed and closed on paper 2026-10-26 (bootstrap/PAPER-2026-10-26.md). Open threads: docs/TODO.md, Bootstrap.*

Every number here is MEASURED on machine 1 (CPython 3.14t, `env/`) unless it is
marked ESTIMATE. One build per case, one typist simulation, no paper.
Outputs are in `build/stage1/` (gitignored); logs in `build/stage1/logs/`.

## The typed totals

Typed total = a.py characters + data glyphs + 4 check glyphs per data line,
newlines not counted (the record's rule).

| | a.py lines | a.py chars | data lines | data glyphs | check glyphs | **typed total** | vs print 3,895 | vs build of record 3,894 |
|---|---|---|---|---|---|---|---|---|
| print of record (`loader/`, N 4,564, bundle 50,533 B) | 29 | 826 | 48 | 2,877 | 192 | 3,895 | — | — |
| build of record (`build/loader/`, N 4,565, bundle 55,550 B) | 29 | 826 | 48 | 2,876 | 192 | 3,894 | −1 | — |
| **stage 1, lowercase** | 28 | 807 | 48 | 2,828 | 192 | **3,827** | −68 | −67 |
| **stage 1, uppercase** | 28 | 807 | 48 | 2,827 | 192 | **3,826** | −69 | −68 |

Stage 1 is built on the build of record's reader and bundle (N 4,565, N2
55,550, B2 2,700,258,880), so −67 / −68 is the like-for-like gain. The two
cases differ by one glyph (ideal 14,140 vs 14,134 bits): within rounding, not
a reason to pick a case. Both cases chose the same edits and the same letters.

Where the gain comes from (lowercase; uppercase in brackets), exact totals:

| step | total | change |
|---|---|---|
| template base (items 2, 3, 7, the letters of record) at the record's tuple | 3,896 [3,895] | +2 [+1] against 3,894 (item 3's −1 and item 7's default parameter, about +4 characters, net) |
| the same at the chosen tuple (0,1,2,3,4,6,8) | 3,889 [3,888] | −7 |
| the rewrite search (item 10), greedy | 3,860 [3,859] | −29 |
| the name search (item 11), until a pass changes nothing (5 productive passes lower, 6 upper) | 3,830 [3,829] | −30 |
| rewrites again, then names again | 3,827 [3,826] | −3 |

So the a.py text saves 19 typed characters (826 → 807) and the primer effect of
the text and the letters saves 44 data glyphs (2,872 → 2,828).

## The a.py (lowercase; uppercase differs only in the alphabet and the code 'FPFF')

    o=open('a.py').read().strip().encode()
    k,z,r=0,'0123456789abcdefghjkmnpqrstvwxyz',1
    def b(c,p):
     for x in p:c=(x+c)*1000003
     return''.join(z[c>>s&31]for s in(15,10,5,0))
    def d(x,y,p,m=(0,1,2,3,4,6,8)):
     z=[256**h-1 for h in m]
     m,s,a=len(p),0,{}
     for i in range(m+y):
      t=1
      for j in range(8):
       u=[a.setdefault((s&q,t),[0,0])for q in z]
       g=[1+sum(r[y]<<s+(r[1-y]<1)for(s,r)in enumerate(u))for y in(0,1)]
       if m>i:k=p[i]>>7-j&1
       else:b=sum(g);n=x%b;k=n>=g[0];x=x//b*g[k]+n-g[0]*k
       for r in u:r[k]+=1;r[k^1]=min(r[k^1],r[k^1]//4+2)
       t+=t+k
      s=s<<8|t%256
     return s.to_bytes(m+y,'big')[m:]
    for t in o.splitlines():print(r,b(r,t));r+=1
    while r<77:
     s=input([r]).replace(' ','')
     if s[-4:]==b(r,s[:-4].encode()):
      for c in s[:-4]:k=k*32+z.find(c)
      r+=1
    y=d(k,4565,o)
    assert b(0,y)=='fpff'
    open('b.py','wb').write(o[39:599]+y)

The baked constants, from the fixed point: the reader is 4,565 bytes, its
check code is `fpff` (`FPFF` in uppercase), the loop bound is 77, and b.py is
the slice a[39:599] followed by the reader (5,125 B). The numbering
consequence of item 10: a.py has 28 lines (the `sum-inline` spelling drops
one), so the data prompts run **[29] … [76]**, not the [30] … [77] the change
list expected from a 29-line a.py. The leaf-4 header says so.

The audit passed on both builds: integers only, no imports, no floats, no
`/`, builtins only, no `l`, lines ≤ 72 (longest 68), capitals only in the
alphabet and the reader code. Scope reuse that a reader of the listing must
know (and that the stage-0 text must state): `y` is the byte count of d() and
also the variable of the `for y in(0,1)` comprehension; `s` is the history
and also the index inside `enumerate`; `r` is the line counter (module), a
counter pair (in d) and the pair in the comprehension; `b` is the check (module)
and the weight sum (local to d); `z` is the alphabet (module) and the masks
(local to d). Comprehension scope is Python 3's rule, and the print of record
already relied on it (`q`, `y`).

## The order tuple (item 7), per run

| tuple | lower total | upper total | R2 payload (lower / upper) | R2 pages |
|---|---|---|---|---|
| (0,1,2,3,4,6) | 3,824 | 3,823 | 15,940 / 15,938 B | 4 |
| **(0,1,2,3,4,6,8)** — chosen | **3,827** | **3,826** | 15,834 / 15,831 B | 3 (78 / 81 B headroom) |
| (0,1,2,3,4,6,8,12) | 3,831 | 3,830 | not computed | |
| (0,1,2,3,4,6,8,12,16) (the record's) | 3,836 | 3,835 | not computed | |

Three pages hold 15,912 B. The reader is unchanged, so it decodes the R2
pages with a.py's default tuple; the rule (the record's change list: "typed
characters first, c.py's pages a constraint") takes the lowest total whose
R2 payload keeps the record's 3 pages. The short tuple is 3 characters
cheaper and costs a fourth bullseye page. Once b.py passes its own tuple for
the R2 pages (not this task), the constraint goes and the short tuple wins
by 3. The search itself ran at the tuple the base chose, (0,…,8).

## The searches (items 10 and 11)

Coder: `typed/cm2_enc.py`, the exact encoder. Agreement proved at the start of
each search run on one case (the base a.py and the reader, long tuple):
cm2_enc's state equals the exploration's mirror `cm2lab.encode_x` (the same
integer, 14,362 bits lower / 14,359 upper, ideal 14,362.49 / 14,359.33), and
the typed d() decodes it to the reader. Wall: 273 s lower, 314 s upper, 4
workers.

Reproducibility: the previous builder's frozen lowercase choice
(`frozen_lower.json`, made before its interruption on an earlier state of the
code) was rerun from scratch with the current code and one more candidate
(`bit-shift`): the same 13 edits and the same 37 letters, the same exact total
3,827. The single-candidate gains moved slightly between the two code states
(`selfdump-counter` −10.39 → −9.75 smooth); the choice did not. The earlier
files are kept as `build/stage1/lower/{frozen_lower,search}.prev.json`.

Each candidate alone against the base (letters of record, tuple (0,…,8)):
a.py characters, the smooth change (decisions), the exact change.

| candidate | a.py chars | lower smooth | lower exact | upper smooth | upper exact | taken |
|---|---|---|---|---|---|---|
| `selfdump-counter` | −10 | −9.75 | −10 | −9.75 | −10 | yes |
| `update-split` | −4 | −4.30 | −5 | −4.28 | −4 | no (its twin taken) |
| `update-split-b` | −4 | −5.13 | −6 | −5.10 | −5 | yes |
| `sum-inline` | −2 | −2.33 | −3 | −2.30 | −2 | yes |
| `part-double` | −1 | −0.09 | −1 | −0.08 | 0 | yes |
| `part-double-b` | 0 | +0.01 | 0 | +0.01 | 0 | no |
| `hist-minus` | 0 | +0.58 | 0 | +0.58 | 0 | no |
| `hist-mod` | 0 | −0.54 | −1 | −0.54 | −1 | yes |
| `num-order` | 0 | +0.83 | 0 | +0.83 | +1 | no |
| `find` | −1 | −3.55 | −4 | −3.51 | −3 | yes |
| `slot-cmp` | 0 | +0.18 | 0 | +0.18 | 0 | no |
| `state-order` | 0 | +1.90 | +1 | +1.90 | +2 | no |
| `out-is-num` | 0 | +0.96 | 0 | +1.02 | +1 | no |
| `u1-merge` (item 13 as a spelling) | +3 | +3.04 | +3 | +3.14 | +3 | no |
| `masks-merge` | 0 | −0.23 | −1 | −0.32 | 0 | no |
| `alpha-check-order` | 0 | +0.06 | 0 | +0.07 | 0 | no |
| `enum-paren-sum` | 0 | −0.34 | −1 | −0.33 | 0 | no |
| `enum-paren-dump` | 0 | −0.67 | −1 | −0.66 | −1 | no (its target gone) |
| `yc-list` | 0 | +0.20 | 0 | +0.11 | 0 | no |
| `boost-first` | +1 | +1.48 | +1 | +1.49 | +1 | no |
| `boost-gt` | 0 | +0.57 | 0 | +0.57 | 0 | no |
| `min-order` | 0 | −0.16 | −1 | −0.16 | 0 | no |
| `xor-y` | 0 | −1.78 | −2 | −1.85 | −2 | yes |
| `xor-yc` | 0 | −1.03 | −1 | −1.06 | −1 | no (+0.9 after the others) |
| `check-order` | 0 | +0.41 | 0 | +0.41 | 0 | yes (in the re-pass, −0.004) |
| `pos-gt` | 0 | −0.40 | −1 | −0.40 | 0 | yes |
| `range-order` | 0 | +0.46 | 0 | +0.46 | 0 | no |
| `check-swap` | 0 | −2.62 | −3 | −2.59 | −3 | yes |
| `assert-literal-first` | −1 | −1.20 | −2 | −1.19 | −1 | taken, then dropped in the re-pass (−1.27 / −1.48 for dropping) |
| `line-inc-last` | 0 | −0.06 | −1 | −0.06 | 0 | yes (in the re-pass) |
| `bit-shift` | +1 | +0.65 | 0 | +0.67 | +1 | no |
| `init-perm-021` | 0 | −0.79 | −1 | −0.79 | −1 | yes |
| `init-perm-102` | 0 | −0.16 | −1 | −0.16 | 0 | no |
| `init-perm-120` | 0 | +1.42 | +1 | +1.42 | +1 | no |
| `init-perm-201` | 0 | +0.93 | 0 | +0.93 | +1 | no |
| `init-perm-210` | 0 | +0.86 | 0 | +0.86 | +1 | no |
| `alpha-perm-021` | 0 | −0.55 | −1 | −0.55 | −1 | no (the 201 order taken) |
| `alpha-perm-102` | 0 | −0.09 | −1 | −0.07 | 0 | no |
| `alpha-perm-120` | 0 | −0.28 | −1 | −0.26 | 0 | no |
| `alpha-perm-201` | 0 | −1.24 | −2 | −1.22 | −1 | yes |
| `alpha-perm-210` | 0 | −0.25 | −1 | −0.24 | 0 | no |

Single gains do not add up: the greedy pass re-evaluates each candidate on the
current text (`build/stage1/<case>/search.json`, `greedy`). The names: 39
letter moves (lowercase) / 36 (uppercase) over the passes; the first pass
alone −29.8 / −30.7 smooth, the later passes −3.0 / −3.2 together. The descent is
a local optimum; a wider name search (pairs of moves, restarts) was not run.
The u=1 merge (item 13) costs +3 as a spelling, as the record measured.

## The identity test (ruling 35)

`test_identity.py`, both cases, PASS:
- mechanical: a.py is the template renamed, byte for byte; readable.py is the
  generator's output; the long form's ast with its names mapped back to roles
  is the template's ast;
- the program: a.py and readable.py side by side, fed data.txt at the
  prompts: the same screen, and b.py byte-identical between the two and to
  the build's b.py (5,125 B);
- k(): typed and long form equal (and equal to the formula) on 1,000 random
  byte strings with random line numbers;
- d(): equal on three payloads — the reader from data.txt's number (4,565 B,
  primer a.py, the default tuple), a 3,000 B text primed with b.py, a KAT
  vector of 258 B at the long tuple passed as `w`.
make_typed.py's own proofs passed on both builds (30 random round trips at the
chosen and the long tuple through the typed d, the long form's d and the
reference `typed/cm2_dec.py`; the six KATs; 3,000 checks against the
formula; the Horner census, 0 of 343,227 single errors, wrong numbers and
transpositions pass; the known-answer program typed and long, the wrong-code
negative) and the second build was byte-identical to the first.

## End to end (e2e.py), both cases: ALL PASS

| | lower | upper |
|---|---|---|
| R2 payload (cm2 of the bundle, primed with the new b.py, tuple (0,…,8)) | 15,834 B, 3 pages, 609 chunks (204/204/201), 78 B headroom | 15,831 B, 3 pages, 609 chunks, 81 B headroom |
| gen.py / verify_grid.py | exit 0 / PASS | exit 0 / PASS |
| typing: 58 lines typed for 48, 10 refused (6 look-alikes, the other case, doubled, dropped, a far line) | PASS | PASS |
| pipe, env python, a.py typed LF: self-dump == codes, prompts, silence, b.py == build, KATs | PASS | PASS |
| pipe, homebrew python3, a.py typed CRLF (the CRLF positive) | PASS | PASS |
| pty, env python, no final newline | PASS | PASS |
| b.py over the nominal renders (blur 0.30, seed 1), one run | p0: 676 blocks, 601/609 chunks; p1: 677 blocks, 609/609 done | p0: 666 blocks, 591/609; p1: 678 blocks, 609/609 done |
| c.py == build/bundle/b.py (55,550 B) | PASS (both interpreters) | PASS (both interpreters) |
| the CRLF-re-saved b.py negative | exit 1 at AssertionError, no c.py | the same |

The reader closes after two of the three frames and never reads the third, as
the build of record's chain does. Wall: 127 s lower, 110 s upper, run side by
side.

The reader of the e2e is `build/stage1/reader_e2e.py`: a copy of
`r2reader/reader_lite_v1.py` (untouched) with **two** file literals changed,
not one: its primer read `open('r.py','rb')` → `open('b.py','rb')` (the file
a.py now writes) and its output `open('b.py','wb')` → `open('c.py','wb')`.
Ruling 34 names the two. N2 and B2 are baked by make_typed as before.

## The leaves (item 1 and the typeface)

- `build/stage1/<case>/leaf3.txt`, `leaf4.txt`, `leaves.pdf` (leaf 3, leaf 4 on
  two sheets, the three R2 pages each with its nominal render: 9 sheets), set in
  the standard OCR-B (`scratch/fonts/fonts-ocr-b-0.3.1/OCRB.otf`, by path).
- Every space of the listing is a middle dot, leading and interior: 74
  dots, the same count as the print of record's 74 spaces; one of them is the
  space inside the literal `' '`, which shows as `'·'`. The
  header says "Each · is ONE SPACE: type one space for every ·, at the start
  of a line and inside it alike".
- The standard OCR-B has no middle-dot glyph (U+00B7): render_pdf draws any
  missing glyph from Menlo, centred in the face's cell on its baseline. The
  redrawn OCR-B, Andale Mono and Menlo have the dot.
- The paper test, `build/stage1/paper-test/data-leaves.pdf` with
  `index.txt`: "pp. 1-2 upper Menlo; pp. 3-4 upper Andale Mono; pp. 5-6 upper
  OCR-B standard (fonts-ocr-b 0.3.1); pp. 7-8 upper OCR-B redrawn (Anderson
  2015); pp. 9-10 lower OCR-B standard". Each sheet's grey header names the
  case and face by the file name. No face fell back to Menlo.
- `pages/compose_leaves.py`: `leaf3(dots='all', head=...)`, `leaf4(head=...,
  first=...)`; defaults are the print of record's. `pages/render_pdf.py`:
  faces `ocrb` (default of stage 1), `ocrb-redrawn`, `andale`, `menlo`, the
  missing-glyph fallback, and `render()` split from `main()`. Backwards
  compatibility, checked: with the HEAD versions and the new ones, leaf3 and
  leaf4 texts from `loader/` are identical (and equal to `pages/leaf3.txt` and
  `leaf4.txt`); every rendered sheet of leaf 1, 2, 2b, 3, 4 and an R2 page with
  its caption is pixel-identical. The PDF bytes differ only in the /Title
  object, which PIL fills from the output file's basename; two runs of HEAD's
  render_pdf into the same file name give byte-identical PDFs (the refuter's
  correction of this note's first claim; the module's "byte-identical
  rebuilds" comment holds for a fixed file name).

## What the previous builder left, and what I kept

Kept as it was: `search.py`, `e2e.py`, `test_identity.py`, the compose_leaves
change, the template's structure and candidates, make_typed's fixed point,
frontier and proofs. Changed: one candidate added (`bit-shift`, not taken);
`make_typed.audit` refused the uppercase build for the reader code `'FPFF'`
(capitals outside the alphabet literal) — it now allows the reader code;
`gen_readable` lost the alphabet comment when the parallel assignment was
reordered (it now hangs the comment on the first target that has one) and
notes the shared counter of the self-dump; `render_pdf` took the redrawn OCR-B
as default — the standard OCR-B is now the default and the redrawing a
variant, with Andale and Menlo, and the missing-glyph fallback; `leaves.py`
got `--face`, `--paper-test`, a 73-column header line rewrapped; two unused
imports. Both searches rerun, both frozen, both builds, the identity test,
both end to end and the leaves made from scratch in this session.

## What was not done

- The Crinkler masks (item 12): not this round.
- The R2 pages' own tuple from b.py's call (the constraint on the short tuple
  goes then): not this task.
- The end to end covers the nominal renders only, not build.py's 57-capture
  set, the damage set or phone frames.
- No Opus refuter has read this build; no paper, no phone-camera shot (the paper
  test is ready for the owner's go).
- The name search is coordinate descent with swaps, a local optimum; the
  reader's own names and text are untouched (the reader is the payload as it
  stands).
- `bootstrap/build.py`, the print of record, `loader/`, `pages/leaf3.txt`,
  `leaf4.txt`, `build/loader`, `build/bundle`, `build/r2`: not touched, not run.
- Nothing committed.

## The refuter's and the checker's findings (2026-10-22), and what was done

An Opus refuter reproduced every headline (the totals, the chain in both
cases, the identity test failing on three mutations, the search reversions
+4/+3/+1/+2, the frontier, the leaves' dots and faces, the tree hygiene):
no blockers, no majors, seven minors. A Sonnet checker found four
discrepancies in this note and the README. All corrected here:
- the PDF-reproducibility claim was wrong (only the /Title differs; withdrawn
  above);
- the name search runs until a pass changes nothing, not "at most 4"
  passes (5 productive passes lower, 6 upper; README and the totals row);
- the later passes' gain is −3.0 / −3.2, the a.py text saving 19 (826 → 807);
- noted, not changed: the chosen tuple (0..8) is second on the frontier by
  3 characters, held by the page constraint until b.py passes its own
  tuple (the owner's call); the e2e reader copy needs two literals
  (`'r.py'` → `'b.py'` for its primer, `'b.py'` → `'c.py'` for its output),
  both the stage-2 change of ruling 34; `z.find` for `q.index` (−1) turns a
  junk glyph on a line that passes the check into a silent −1 instead of a
  ValueError — the run ends at the reader-code assert either way; the
  searches rank by a smooth ideal-bits proxy (one taken edit, check-order,
  likely buys nothing exact) and the name search is single-move coordinate
  descent; y, s, r, b and z each have a module-level and an inner binding,
  correct under Python 3 scope and already relied on by the print of
  record — the stage-0 prose must say so; codes.txt carries five summary
  lines after the 28 codes (cosmetic).

## The leaves made bare (2026-10-22, ruling 44)

The owner's three points on the first paper-test set: the data sheet needs
no middle dots (true: they are the listing's; no problem on the data sheet),
the listing was missing from the set, and the plate text is deferred — keep
the header lines, drop the viewing-render line, add a date stamp. So
`leaves.py` now writes each leaf with its identity line and the date
(`VOLUME {V}  R1 LEAF 3  THE PROGRAM    2026-10-22`), no prose (`--prose`
restores it), and `render_pdf.render()` takes a `header` argument ('' for
stage 1; None keeps the print of record's grey line). The data leaf is one
sheet without the prose. The paper-test PDF holds the listing and the data
leaf per (case, face), ten sheets, each identity line naming its face and
case within 72 columns (a longer line would shrink the sheet's font);
`preview-NN.png` beside it. The print of record's three sheets render
pixel-identical through the modified renderer (MEASURED, image hashes).
