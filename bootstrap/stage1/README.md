# stage1/ — the new a.py (ruling 43 of 2026-10-21), beside the print of record

**State, 2026-10-26.** The candidate print of record v3 below CLOSED ON
PAPER: the owner typed its sheets 1 and 2, and a.py and the b.py it wrote
are sha-equal to build/sheets/stage1/upper/ (720330aa…, 761138cd…); the
chain ran through c.py to the unpacked archive (bootstrap/PAPER-2026-10-26.md).
Its promotion to the print of record is the owner's ruling. Open threads:
docs/TODO.md, section Bootstrap.

**State, 2026-10-23, late** (CONVERGENCE-2026-10-23b.md). The candidate
print of record v3 (bootstrap/CONVERGENCE-2026-10-23b.md, ruling 60's
convergence re-run on the repaired c.py; ruling 67): a.py is 28 lines, 798 characters,
and types 3,289 characters in the uppercase print (3,289 lowercase) with 39
data lines; b.py is 4,487 B (a[39:591] + the reader's 3,935 B); c.py is
24,176 B (sha b4f7de22…, CRC-32 3810813523), coded under b.py at a.py's
default tuple (0,1,2,3,4,6) into 10,133 B (lowercase 10,130) = 2 R2 pages
with 475 B spare (478), 390 chunks (204 + 186); make_c.py scores c.py under
the chain b.py and, the chain and the pipeline forming a two-cycle, keeps
the member whose chain prints smaller (its rule (d'), ruling 67 of 2026-10-26);
bootstrap/rebuild_v2.py regenerates the sheets byte for byte
(print-2026-10-23.pdf 4989446c…). The upper case's long form is committed
as stage1/a_readable_upper.py (test_identity.py's `committed` step proves
it); the QR codes of stage1/qr/ are regenerated for this a.py and data.
make_typed.py's frontier records a tuple without a fixed point of the loop
bound instead of dying on it. The paragraph below is the state before the
convergences.

**State, 2026-10-23** (RECORD-2026-10-20.md through ruling 61). a.py is 28
lines, 807 characters with the stand-in content at the tuple
(0,1,2,3,4,6,8), 805 with c.py as the content, where the frontier picks
(0,1,2,3,4,6) (stage3/RESULTS-2026-10-22.md §4, §6). The leaves print in
UPPERCASE, the alphabet 0123456789ABCDEFGHJKMNPQRSTVWXYZ, the listing in
Menlo and the data leaf in Andale Mono (ruling 51), bare: the identity line
with a date stamp, no plate text (ruling 44). The typed total with
today's b.py (the grey padding of ruling 59 applied) is 3,326 lowercase /
3,325 uppercase on 40 data lines with the stand-in bundle, and 3,319 /
3,318 on 40 data lines with c.py as the content
(r2reader/changeset/RESULTS-2026-10-22.md §20, parts 1 and 2), against
this folder's first build of 3,827 / 3,826 (RESULTS.md) and the print of
record's 3,895. On the way: 3,337 / 3,336 at §18, 3,335 / 3,335 at §19
(the literal `@` of ruling 58); with c.py as the content 3,465 / 3,463
under the ruled b.py of a9826d37, before b.py's composite and progress
line (stage3/RESULTS §6). This folder's chain (stages 1 and 2) passes both
cases at every step.
The floor is Python 3.11 (ruling 53). The sources, as recorded in ruling
58 (the owner's confirmation owed): `template.py` is the source,
`make_typed.py` renders a.py and `gen_readable.py` the long form,
`test_identity.py` binds them. Done since: the convergence (ruling 60,
twice; ruling 67), the rebuild through rebuild_v2.py, `,'big'` removed,
the page bound the constant R2_PAGES_BOUND = 3 (ruled (b) for the 23b run),
the tuple (0,1,2,3,4,6) in use (the frontier's choice; no owner ruling was
recorded, both convergences and the print rest on it), the long form
committed (a_readable_upper.py). Open: docs/TODO.md, section Bootstrap
(the Crinkler masks, the whole-file check code of ruling 68, the sources'
confirmation, the promotion of v3). The
body below is the record of 2026-10-21/22; where it names the standard
OCR-B as the typeface, ruling 51 has since chosen Menlo and Andale Mono.

Stage 1 of the bootstrap is the typed program `a.py` (ruling 34: the stages
are named by the program each one yields). The finder types the listing
(leaf 3) into a file, runs it, checks the self-dump codes; at stage 2 the
finder types the data lines (leaf 4, the data sheet) at the `[n]` prompt,
and a.py decodes the stage-2 program and writes it as **`b.py`** (the
print of record calls it r.py). At stage 3 b.py reads phone photos of the
bullseye pages and writes the stage-3 receiver as **`c.py`** (the print of
record's reader writes b.py). The directories are named by program: this
folder builds a.py and its listing AND the data sheet of stage 2
(`make_typed.py`, `e2e.py`, `leaves.py`); b.py lives in `r2reader/`, c.py
in `stage3/`.

The print of record (`loader/a.py`, closed on paper 2026-10-20,
`PAPER-2026-10-20.md`; v3, closed on paper 2026-10-26, is its candidate
successor, the owner's ruling owed) and everything `bootstrap/build.py`
writes are not touched by this folder. Its outputs go to `build/stage1/` (gitignored).

## What ruling 43 takes, and where it lives

| item | what | where |
|---|---|---|
| 1 | every space of the listing shown as a middle dot, leading and interior | `pages/compose_leaves.py` `leaf3(dots='all')`, `leaves.py` |
| 2 | the loader writes `b.py`; the reader's output becomes `c.py` | `template.py`; the reader copy `build/stage1/reader_e2e.py` |
| 3 | `k()` and the alphabet above `d()` (the b.py slice starts with them) | `template.py` |
| 4 | the baked constants (reader length, reader code, loop bound, slice) by the fixed point | `make_typed.py` (`pack`, `template.bake`) |
| 7 | `def d(x,n,r,w=(...))`, the default tuple searched per run | `make_typed.py` (`frontier`) |
| 8 (explored) | the alphabet uppercase: both cases built | `--case lower|upper` everywhere |
| 10 | the rewrite search over a.py's own text | `template.CANDIDATES`, `search.py` |
| 11 | a.py's single-letter names searched jointly with the reader's text | `search.py` (names passes) |
| typeface | the standard OCR-B, by path; the redrawing a variant | `pages/render_pdf.py` faces |

OUT and not built: the numeric self-zeroing check, the look-alike map, the
`u=1` merge as a change (it is one candidate spelling of the search, and
loses), base 36, base 58, a binary read of a.py, persistence, junk guards,
the Crinkler masks (item 12, not this round).

## The files

- `template.py` — the ONE source. `TEMPLATE` is the typed program with every
  identifier written as a capitalised ROLE (`Check`, `Dec`, `Pairs`, ...) and
  placeholders for the alphabet, the tuple and the baked constants; the
  frozen rewrite candidates (`CANDIDATES`); the role → letter map of the
  print of record (`BASE_LETTERS`) and the long form's names
  (`LONG_NAMES`); the scope analysis that says which roles may share a
  letter.
- `search.py` — items 10 and 11. Reproducible: no RNG, a fixed order, the
  candidate list frozen in `template.py`. `--freeze` writes
  `frozen_<case>.json` (the edits and the letters), which `make_typed.py`
  reads.
- `make_typed.py` — v4 of `loader/make_typed.py` (v3's fixed point, base-32
  data lines, Horner checks and proofs kept). Builds `a.py`, `data.txt`,
  `codes.txt`, `b.py`, `readable.py`, `build.json`, `sizes.txt` into
  `build/stage1/<case>/`, after its proofs (units, KATs, the known-answer
  program run as typed and as long form) and a second, byte-compared build.
- `gen_readable.py` — the de-minifier: the long form `readable.py` from the
  same template text (descriptive names, one statement per line, four-space
  indents, comments). Ruling 35: the long form must be functionally
  identical, so it is generated, never edited.
- `test_identity.py` — the identity test: a.py is the template renamed;
  readable.py is the generator's output and its ast (names mapped back) is
  the template's; both, fed `data.txt`, give the same screen and a
  byte-identical b.py (== the build's); `k()` equal on 1,000 random byte
  strings and line numbers; `d()` equal on three payloads.
- `e2e.py` — the end to end per case: the R2 pages re-encoded against the
  new primer, rendered, the typing simulated (LF pipe, CRLF-typed a.py on a
  second interpreter, a pty), each typed b.py run over the three renders
  (c.py == the bundle of record), and the CRLF-re-saved b.py negative.
- `leaves.py` — leaves 3 and 4 per case, the PDF, and `--paper-test` (the
  owner's phone test of the data leaf's face).
- `frozen_lower.json`, `frozen_upper.json` — the search's choice per case.

## How to run (machine 1: `env/bin/python`, from `bootstrap/stage1/`)

    python search.py --case lower --freeze --workers 4     # ~6 min each case
    python search.py --case upper --freeze --workers 4
    python make_typed.py --case lower                      # ~1 min each case
    python make_typed.py --case upper
    python test_identity.py --build ../build/stage1        # both cases; bare: build/sheets/stage1 (bootstrap/rebuild_v2.py's)
    python e2e.py --case lower                             # pages, renders, typing, reads
    python e2e.py --case upper
    python leaves.py --paper-test                          # both cases + the paper-test PDF

`make_typed.py` without a `frozen_<case>.json` falls back to the template's
base spelling and the letters of record, with a warning.

## The typed subset (what a.py may contain)

Integers only; no imports; no floats; no `/` (`//` is fine); builtins only
(`open`, `len`, `sum`, `min`, `range`, `enumerate`, `print`, `input`, and the
methods of str/bytes/int/dict); no `exec`/`eval`; lowercase names (capitals
only inside the alphabet literal, uppercase case); no identifier `l` or lone
`l`; no backslash, double quote or tab; one space per indent level; lines ≤
72; no trailing space; one print (the self-dump); the program ends with the
assert and the write of `b.py`. `make_typed.audit()` checks these rules on
every build, all but two: the builtins a.py calls and the indent width are
not audited. It also checks what the template fixes: the definitions bind
exactly their five roles, `k` above `d`, and the b.py slice matches their
offsets. Comprehensions keep their own scope (Python 3): the searched
letters may reuse a letter inside a comprehension, as the print of record
already does (`q`, `y`).

## The objective

The TYPED TOTAL = a.py characters + data glyphs + 4 check glyphs per data
line, newlines not counted (the record's 3,895 counts the same way). Every
character of a.py is typed raw, so a spelling that saves a character saves a
typed character; a.py is also the cm2 primer of the data lines, so its
spelling and its letters move the data glyphs at no a.py cost.

The search decides on the SMOOTH total (a.py characters + ideal bits × (1 +
4/60) / 5), so a candidate is not taken or refused by where a glyph or a line
boundary happens to fall; every stage also reports the EXACT total (the real
encoder, base-32 digits, 4 per started line). The exact coder is
`typed/cm2_enc.py`; `search.py` proves once per run that it equals the
exploration's mirror `compressor-exploration/harness/cm2lab.py` (the same
state x) and that the typed `d()` decodes that x to the reader.

## The candidate list (frozen, `template.CANDIDATES`)

Each is an equivalent spelling of the same statements; a candidate whose
target another rewrote does not apply.

- `selfdump-counter` — the self-dump counts with the data counter
  (`for t in a.splitlines():print(n,k(n,t));n+=1`): the prompts continue the
  listing's numbering, `[L+1]` … (L = a.py's lines).
- `update-split`, `update-split-b` — the counter update as two statements
  (`c[1-y]=min(...);c[y]+=1` or `c[y]+=1;c[1-y]=min(...)`).
- `sum-inline` — `s=sum(p)` moved into the `else` branch, its only reader.
- `part-double`, `part-double-b` — `u=2*u+y` as `u+=u+y` / `u=u*2+y`.
- `hist-minus`, `hist-mod` — `u&255` as `u-256` / `u%256`.
- `num-order` — `v=v*32+...` as `v=32*v+...`.
- `find` — `q.index(c)` as `q.find(c)` (the line passed its check first).
- `slot-cmp` — `y=o>=p[0]` as `y=p[0]<=o`.
- `state-order` — `...-p[0]*y` as `...-y*p[0]`.
- `out-is-num` — the decoded reader bound to the data's number variable.
- `u1-merge` — item 13 as a spelling: `u=1` merged into the init and the
  history line.
- `masks-merge` — the masks line merged into the init line.
- `alpha-check-order` — `def k` above the alphabet line (both above d).
- `enum-paren-sum`, `enum-paren-dump` — `for(q,c)in` as `for q,c in`.
- `yc-list` — `for y in(0,1)` as `for y in[0,1]`.
- `boost-first`, `boost-gt` — `c[y]<<q+(c[1-y]<1)` as `c[y]<<(c[1-y]<1)+q`;
  `(c[1-y]<1)` as `(1>c[1-y])`.
- `min-order` — `min(c,c//4+2)` as `min(c//4+2,c)`.
- `xor-y`, `xor-yc` — `1-y` as `y^1` in the update / in the weights.
- `check-order` — `n=(n+c)*K` as `n=(c+n)*K`.
- `pos-gt` — `if i<m` as `if m>i`.
- `range-order` — `range(m+n)` as `range(n+m)`.
- `check-swap` — `if k(...)==t[-4:]` as `if t[-4:]==k(...)`.
- `assert-literal-first` — `assert k(0,r)=='...'` as `assert'...'==k(0,r)`.
- `line-inc-last` — `n+=1` after the digit loop.
- `bit-shift` — `r[i]>>7-j&1` as `r[i]<<j>>7&1`.
- `init-perm-*` — the five other orders of `m,t,h=len(r),{},0`.
- `alpha-perm-*` — the five other orders of the alphabet/counter line.

The names (item 11): coordinate descent over every role but `d` (the reader
calls `d`), every legal letter (a–z without `l`) and the swap with the one
conflicting role holding it, until a pass changes nothing (5 productive
passes for lowercase, 6 for uppercase in this build); then
the rewrite candidates again (add any not taken, drop any taken), then names
once more if anything moved. Legal = no two roles of one scope share a
letter, except the pairs whose lives do not overlap (`template.SHAREABLE`).
Every result is proved by running it (make_typed's proofs, the identity test,
the e2e), not by the scope analysis alone.

## The order tuple (item 7)

`make_typed.frontier` packs a.py for each tuple of the frontier (0,1,2,3,4,6)
… (0,1,2,3,4,6,8,12,16) and takes the lowest typed total among the tuples
whose R2 payload keeps the record's page count (3): the unchanged reader
calls `d(x,N2,primer)` and so decodes the R2 pages with a.py's default
(the record's change list: "typed characters first, c.py's pages a
constraint"). When b.py later passes its own tuple for the R2 pages, the
constraint goes and the default is the typed-total minimum.

## Results

`RESULTS.md`.
