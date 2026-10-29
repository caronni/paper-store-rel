# loader/ — the typed rung, v3 (rulings of 2026-10-19, amended through 2026-10-20: Horner line check, definitions-then-reader, cm2 v2 with a big-integer rANS decoder)

Type leaf 3 into `a.py` and run it. Check the codes, then type leaf 4 at
`[n]`. After a silent exit, run `python3 r.py` and give it the R2 pages; it
writes `b.py`.

## Files and the one command
- `a.py`, `data.txt`, `codes.txt`: the print of record — whatever
  `make_typed.py` built last (it always copies them here, whatever `--out`
  says). The final build: the diet reader `r2reader/reader_lite_v1.py`
  (sha b273cf3a…; N 4,564 once its tokens are in), bundle 50,533 B, three
  pages — made by
  `bootstrap/build.py`; loader/rebuild.py's make_typed output is
  byte-identical to it (a.py, data.txt, codes.txt, r.py).
- `python3 loader/rebuild.py` re-runs everything on the stand-in (with the
  snapshot bundle build/w3/payloads/bundle_b.py for its N2 and B2);
  `python3 loader/rebuild.py --reader PATH --bundle PATH [--page PATH ...]
  [--done TEXT] [--orders] [--no-record]` on a real reader: make_typed, the
  KATs, the e2e on every interpreter (all pages through one r.py run, and the
  CRLF negative), refute5, and with `--orders` the order-tuple frontier on
  that reader and bundle; `--no-record` builds and tests in build/w3/loader
  only and leaves loader/ alone. Logs: build/w3/rebuild/.
- `make_typed.py` encodes, proves and writes `OUT/r.py` and `OUT/build.json`
  (the reader file, the bundle, N2 and B2 it built from); `e2e_pipe.py`
  types; `standin.py` derives the stand-in reader; `refute5/` refutes the
  build in build/w3/loader (run it through rebuild.py, or with `LOADER_OUT`
  = another make_typed `--out`);
  `refute5/crc-not-taken/` keeps the CRC line check the owner did not take.
- The coder lives in `typed/`: `cm2_dec.py` (readable decoder, the order
  tuple), `cm2_enc.py` (encoder), `kat_v2.json` + `kat_v2.py`, the
  measurements `measure_v2.py`, `measure_v2_final.py`,
  `measure_v2-result.json`; the 10-18 range coder as `cm2_v1_*.py`.
- `bootstrap/build.py` runs this typed chain as its stage 7b (a.py typed,
  r.py, both pages, b.py == the bundle); `pages/compose_leaves.py` reads N,
  the loop bound, the reader code and the slice numbers from this a.py.

## The program (a.py v3, 29 lines)
1. Line 1, `a=open('a.py').read().strip().encode()`: the program's own text
   as bytes, read in text mode (so CRLF and the editor's end of file cannot
   matter).
2. The SHARED DEFINITIONS: `d(x,n,r)`, the cm2 v2 decoder (15 lines);
   `q,n,v='0123…xyz',1,0` (the alphabet and the data loop's start values);
   `k(n,t)`, the line check over bytes.
3. The MAIN part: the self-dump `for(i,t)in enumerate(a.splitlines(),1):…`,
   the data loop, `r=d(v,N,a)`, `assert k(0,r)=='code'`,
   `open('r.py','wb').write(a[39:END]+r)`.

Lowercase names only, no exec, no final print, no `/` (`//` is fine), no
backslash or double quote, lines ≤ 72, one space per indent level, merged
assignments, baked print-time constants.

## cm2 v2: the rANS decoder
- **What x is.** The data lines spell one integer in base 32, 5 bits per
  glyph, most significant first; the loop builds it as `v=v*32+q.index(c)`.
  That integer IS the coder's state x: the whole compressed reader, nothing
  else — no length, no padding, no container.
- **How a bit decodes.** For every bit the model gives two weights p0, p1
  (s = p0 + p1). Bit 0 owns the slots [0, p0) of `x % s`, bit 1 the slots
  [p0, s): `s=sum(p)`, `o=x%s`, `y=o>=p[0]`, then `x=x//s*p[y]+o-p[0]*y`
  takes the bit out of x. A bit of probability p_y/s costs about log2(s/p_y)
  bits of x. The encoder (typed/cm2_enc.py) pushed the bits in reverse from
  x = 0, so x never grows (it stays the same on a 0 bit while x < s) and is
  exactly 0 after the last one. The primer's bytes (a.py's own text) come
  first and only train the model: their bits are read, not decoded.
- **The model** is cm2's, unchanged in its counts: per bit, one counter pair
  per order o in (0,1,2,3,4,6,8,12,16), keyed by (the last o bytes of the
  whole history h, the bits of the current byte behind a leading 1); the
  last o bytes are the mask `h&256**o-1` (the same key as `h%256**o`, which
  is far slower: 298 s against 4.8 s on the page of the reader.py build);
  p_y = 1 + Σ count_y << (index + [count_other == 0]); after the bit
  count_y += 1, count_other = min(count_other, count_other // 4 + 2).
  **ONE table for all orders: the key omits the order.** Where two orders'
  keys coincide (trailing zero bytes, e.g. at the start) they share one
  counter pair, summed once per order in p and updated once per order. A
  decoder that keeps one table per order does not interoperate (the
  refuter's counterexample: "hello, finder\n" with an empty primer).
- **Time and memory.** Decoding costs O(primer) + O(N·|x|): every decoded
  bit divides x. The page before the B2 tail (N2 43,111, primer 5,034 B, x
  100,009 bits) took 9 s and about 450 MB on machine 1 (the refuter's
  measurement); the final r.py reads the three final pages and decodes the
  50,533 B bundle in 16.6–21.9 s (the e2e below, reading included); the
  loader's own decode of the 4,564 B reader takes 0.38–0.51 s.
- **Why no S.** The 10-18 range coder needed its coder byte count S to know
  where the coded bytes ended and to restore their leading zeros. Here the
  typed number is the state itself: its digits are exactly what is needed,
  and N (the reader's length) says when to stop. No window, no
  renormalisation, no 12-bit clamp — Python's integers hold x whole.
- **A wrong x** decodes to N bytes of other text; the reader check (`k(0,r)`)
  then fires the assert, and nothing is written. Measured (refute5/safety5):
  621 wrong x, none raises, none passes, x never grows; a wrong x decodes in
  the right one's time (median 0.37 s against 0.37 s).

## The check (Horner, kept)
`k(n,t)`: for each byte c of t, n = (n + c) × 1000003 (unbounded: the low
20 bits are the 10-19 mod-2^20 value), then 4 glyphs q[n>>15&31]
q[n>>10&31] q[n>>5&31] q[n&31]. n = the 1-based line number for listing
lines and data lines; 0 for the reader's whole text. For lines up to 72
glyphs: no single substitution, no transposition at any distance (ASCII:
safe to distance 4,095) and no wrong line number passes; a random wrong line
passes with probability 1/1048576.
**Stated property (the wrong-prompt slip), DETERMINISTIC:** the line number
and the first glyph are multiplied alike, so data line n typed at prompt m
passes whenever its FIRST glyph is moved by exactly n − m code points. Line n
retyped at [n+1] with its first glyph one code point lower always passes, as
does line n+1 at [n] with its first glyph one higher. Among next-prompt
lines with one random wrong glyph that is about 1 in 2,360 (37 of 87,420 on
the final data), 1 in 2,414 if the wrong glyph may also fall on the check.
A slip whose moved glyph falls OUTSIDE the alphabet (v → u) passes the check
and then crashes the entry with ValueError at `q.index` — every typed line
is lost (21 of the 94 ±1 slips on the final data). The double-substitution
passes are one deterministic pattern too: distance 2, the changes ±52 then
±44 (with printable characters also ±(26, 22) and ±(78, 66)), since K² ≡
40,329 mod 2^20. The owner kept Horner over the CRC check that closes the
slip (refute5/crc-not-taken/).

## The constants and who bakes them
| | where | baked by |
|---|---|---|
| N, the reader's bytes | `r=d(v,N,a)` | make_typed, from the reader text |
| C, the data lines | `while n<C+1:` | make_typed's fixed point (C sits in the primer) |
| G, the glyphs | not in a.py: the data's length | the encoder: the digits of x; C = ceil(G / 60) |
| the reader code | `assert k(0,r)=='code'` | make_typed: k(0, reader text) |
| START = 39, END = 608 | `a[39:608]` | make_typed's template: line 2's offset and the first `for(` line's; asserted fixed across the fixed point |
| N2, the bundle's bytes | the reader's tail | make_typed replaces the reader's NAME token N2 before the fixed point (`--bundle`: its length) |
| B2, the bundle's CRC-32 | the reader's tail assert | make_typed replaces the NAME token B2 with the CRC-32 (decimal) of the `--bundle` file, before the fixed point; a reader without B2, or B2 without `--bundle`, is refused |
| the order tuple | `z=[256**q-1 for q in(…)]` | typed/cm2_dec.py (one source for the typed d, the readable d, the encoder, the KATs) |
**The final build** (`r2reader/reader_lite_v1.py`, sha b273cf3a…; bundle
50,533 B; three pages, payload 14,472 B): N 4,564, C 48 (loop bound 49),
G 2,877 (x of 14,381 bits), code `y98y`, N2 50,533, B2 327,353,449, START
39, END 608, orders (0,1,2,3,4,6,8,12,16); r.py 5,133 B = definitions 569 +
reader 4,564. Typed: a.py 29 lines / 826 characters + data.txt 48 lines /
3,069 characters = **3,895**.

## r.py and the reader's contract
- r.py = `a[39:608]` (a.py's lines 2 .. the line before the first that
  starts with `for(`) + the decoded reader, written in BINARY; its bytes are
  the primer of the page's compression (make_typed writes them to
  `OUT/r.py`).
- Reserved names: **d, q, k** — the reader may use them and must not define
  them; n and v come along and may be rebound; `e` is not shared (the reader
  binds its own `e='big'` if it wants one: a shared e was measured 3 typed
  characters dearer).
- The reader carries its own CRC-32 in its typed text.
- The tail decompresses the page data, computes first, CHECKS, writes last:
  `w=d(int.from_bytes(data,'big'),N2,open('r.py','rb').read())`, then
  `assert <its CRC-32>(w)==B2`, then `open('b.py','wb').write(w)`. rANS
  decodes EVERY x to N2 bytes without an exception, and the page's CRC
  covers only the compressed data; b.py is checked by the baked B2 assert.
  A changed or foreign r.py (re-saved with CRLF, an extra final newline,
  another print's page) thus ends in an AssertionError, with no b.py,
  instead of "done" and garbage (the refuter measured both: a CRLF r.py
  gave 481/481 done and a b.py that does not compile; an extra newline gave
  43,111 newlines).
- `open('r.py','rb')` and `open('a.py')` are relative to the current
  directory: run both programs in the folder that holds them, and never open
  or re-save r.py.
- make_typed takes the reader as: the region `# BEGIN READER` … `# END
  READER` if present (else the whole file), minus every block from the exact
  line `#--- shared with the loader (not typed) ---` through `#--- end
  shared ---`, with every NAME token `N2` and `B2` replaced (`--bundle
  PATH`: its length and its CRC-32).

## What the finder's setup can break (the refuter's table)
| what | what happens |
|---|---|
| a BOM at the start of a.py | line 1's code differs |
| tabs, or 4-space auto-indent | every indented line's code differs |
| a blank line inside | every code after it differs |
| a.py saved under another name, or run from another directory | FileNotFoundError at line 1 (or an older a.py in the current directory is dumped instead) |
| Ctrl-D at a prompt | EOFError: all typed data lost |
| data piped from a file with CRLF | every line refused |
| Python older than 3.5 | 3.0–3.1 fail at `to_bytes` AFTER all data is typed; 3.2–3.4 fail at r.py's `a(*f(s),hd,20)`: the chain's floor is 3.5 |
| a one-character typo in a.py | 55 % are SyntaxErrors (Python names the line; wrong in 0.5 %), 8 % crash in lines 1 and 17–21, 4 % corrupt the dump itself, 3 hang, 32 % show only their own line's code differing |
| a slipped data line (above) | passes the check; outside the alphabet it crashes the entry at `q.index` |

## The e2e's checks (e2e_pipe.py)
a.py typed line by line (LF, CRLF, no final newline, blank lines after);
the data with injected faults (twins o/l/i/u/s/z, a capital, a doubled, a
dropped and a wrong-position line refused; group spaces, a trailing space
and the last line as printed accepted). Per interpreter (env 3.14t, homebrew
3.14; with `--more` also 3.9, 3.10, 3.13, 3.14t): self-dump == codes.txt
(and the check recomputed independently), the [n] prompts as injected,
silent exit, r.py == definitions + reader == make_typed's r.py, the typed
d decodes the KAT vectors, and ONE `r.py` run fed every `--page` in turn:
exit 0, the last progress line ends `done` (`--done TEXT` to change it; the
diet reader prints `… chunks 557 / 557 done`), b.py == the bundle. A missing
page leaves the data open and fails the run. THE NEGATIVE: the same r.py
re-saved with CRLF line ends, fed the same pages, must exit 1 at the
reader's B2 assert and write no b.py. One pty run checks the echo.

**The final run** (`rebuild.py --no-record`, the final reader and bundle,
the three nominal-b030 pages): ALL PASS, 64/64 checks.
| interpreter | a.py typed as | loader decode | r.py: 3 pages + b.py | CRLF r.py |
|---|---|---|---|---|
| env 3.14.8t | LF | 0.43 s | 557/557 done, b.py == bundle (50,533 B), 17.5 s | exit 1, AssertionError, no b.py |
| homebrew 3.14.8 | CRLF | 0.38 s | same, 16.6 s | same |
| 3.9.6 | no final newline | 0.49 s | same, 21.9 s | same |
| 3.10.22 | blank lines after | 0.51 s | same, 19.7 s | same |
| 3.13.16 | LF | 0.39 s | same, 16.8 s | same |
| 3.14.8t | CRLF | 0.43 s | same, 17.2 s | same |
| pty (env) | no final newline | — | — | — |
Every pipe run: 58 lines typed (48 data + 10 refused), self-dump == codes.txt,
the prompts as injected, silent exit, r.py == definitions + reader ==
make_typed's r.py, the 6 KAT vectors decoded by the typed d. The B2
machinery is also checked on its own by refute5/b2check5 (a synthetic reader
with the ruled tail passes and fails its CRLF r.py at the assert; a twin that
does not assert B2 is caught).

## refute5, the last run (the final build, rebuild.py --no-record)
- census5: 0 of 18,615 single substitutions / wrong line numbers and 0 of
  324,612 ASCII transpositions pass for lines ≤ 72; literally 0 of 247,032 /
  60,256 / 18,360; the slip pattern (wrong number + first glyph moved by
  n − m) 1,957 of 1,957.
- selfdump5: every one-character error in every a.py line changes its code:
  0 of 77,644 substitutions, 81,225 insertions, 826 deletions, 756 swaps,
  7,395 wrong numbers; a.py's k agrees with the retyped check on all.
- double5 (the final data.txt, 48 lines): double substitutions 214 of
  81.5 M (2.75 × 2^-20; printable ASCII 4,288 of 733 M, 6.1 ×); payload ×
  check 0 of 11.1 M; insertions 0 of 99,744, deletions 0 of 3,069; line n at
  prompt n+1 with one wrong glyph 37 of 87,420 (444 × 2^-20, the stated
  slip), at any other prompt 657 of 4.10 M (168 ×); Monte Carlo 0.3–5.6 ×
  2^-20 on six classes, the slip class 434 × 2^-20 (1 in 2,414).
- safety5: 620 wrong x — none raises, all give 4,564 bytes, only the right x
  passes; wall time median 0.36 s, slowest 0.41 s, against 0.37 s for the
  right x; x never grows; the counter table 222,304 entries against its
  bound 390,096.
- b2check5: PASS — the token rules (no B2 → refused; B2 as a string, not a
  NAME → refused; B2 without a bundle → refused; N2 without one → refused)
  and the B2 tail end to end on the synthetic reader.
- consts5: every expectation — N 4,564, C 48, G 2,877 (no leading 0 glyph,
  C = ceil(G/60)), code `y98y`, the slice [39, 608], the orders, B2 ==
  327,353,449 == the bundle's CRC-32 and N2 == its length, the fixed point
  (encode(reader, a.py) == x exactly, 14,381 bits), the definitions' bindings
  (d, k, n, q, v), a.py's k and d alone, and make_typed's r.py.

## Counts
| | program | data | typed |
|---|---|---|---|
| v1 of record (10-19, range coder, reader_lite) | 37/1,066 | 34/2,123 | 3,189 |
| v2 evening build (range coder, stand-in) | 36/1,075 | 35/2,183 | 3,258 |
| v3 (rANS, stand-in reader_lite, 3,093 B) | 29/826 | 35/2,201 | 3,027 |
| v3, the diet reader before its B2 tail (4,465 B) | 29/826 | 47/2,960 | 3,786 |
| v3, reader_lite_v1 with the B2 tail, before the R2-FORMAT text fixes | 29/826 | 48/3,070 | 3,896 |
| **v3, final: reader_lite_v1, bundle 50,533 B (N 4,564)** | **29/826** | **48/3,069** | **3,895** |
The final build is byte-identical to build.py's (a.py, data.txt, codes.txt,
r.py: asserted by cmp in the last rebuild).
The order tuple, the keys, the spellings and the timings behind v3:
typed/measure_v2-result.json (stand-in); on the diet reader before its B2
tail and its bundle, build/w3/measure_v2-rebuild.json: every tuple gave 47
data lines and 3 pages (the shortest tuples save 9 typed characters, no
line), so the tuple stayed, and the frontier is settled (ruling).
