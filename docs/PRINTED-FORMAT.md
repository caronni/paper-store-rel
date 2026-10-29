# The printed format

An RFC-shaped description of what toner is allowed to mean, complete
enough that a second generator could be built. The first generator is
`src/holo` and remains authority. This note is the *layer cake*, not a
re-derivation.

Status: carried from `holo4/docs/PRINT.md` (a founding note, 2026-09-01
— untracked where it sat, and deliberately not duplicated into that
directory's archive, `docs/archive/holo4/README-ARCHIVE.md`) into
`docs/` on 2026-09-13 and corrected against the format authority —
every correction is listed in §16. It ranks **below**
`docs/HOLO-DESIGN.md` and `docs/FORMAT-SPACE.md`. Not a freeze. Where
this and `src/holo` disagree, the code and its goldens win, and this
file is wrong.

Normative companions already in that tree (do not fork them here):

- `src/holo/core/keystream_spec.py` — the printable AES/KDF/counter
  spec, stdlib only. It *is* §5 of this document, as code.
- `src/holo/core/ldpc/data/*.json` — the six mother codes, as
  transparent block descriptions. Produced by
  `util/regen_holo_ldpc_data.py` from paperholo's seeded construction.
  A page generator expands these files; it does not draw a new H.
- `tests/holo/` goldens — bump-don't-edit.

---

## 0. What kind of document this is

A generator spec is four different things mixed. Keep them labelled.

| kind | example | how an implementer treats it |
|---|---|---|
| **Convention** | MSB-first bits, big-endian integers, ink=1, origin top-left y-down in device dots, cell-edge affines | Write it once. Violate it anywhere and every golden fails. |
| **Math** | BCH over GF(2⁷), the degree-24 LFSR, 11-bit → four radix-7 digits, fountain GE | Implement from the algebra. Pin a vector. |
| **Algorithm** | quota-site construction, 16-bit rejection, affine slot perm, per-page fountain quotas, the e-IRA *draw* | Numbered procedure, no hidden consumption, no numpy dtype. |
| **Generated, then pinned** | the six LDPC JSON files | There is a generator (`util/regen_holo_ldpc_data.py`). A page encoder *expands* the committed JSON. Remaking the JSON is legal only through that construction (or an equivalent of it) and only if the independent edge-array goldens still match. A textbook IRA from this prose is a fork. |
| **Opaque pin** | fossil `L:` seed bytes | Copy the bytes. No generator is allowed to mint a new meaning for a string already printed. |

The 012.3 incident (a missing `dtype=` regenerated the "same" stream wrongly) is the generated-then-pinned failure mode: the algorithm existed; the consumption rule was not the one on paper.

The IETF instinct is right: a second implementation is the only
conformance test that matters. For this format the second
implementation already exists as `keystream_spec.py` vs OpenSSL
`keystream.py`, and as the receiver's copy-and-stripped kernels
(`src/holo/receiver/`, holo3 in the records). A generator
written from *this* note without those pins will look right and print
noise.

Receiver behaviour (PAVA, windows, prices) is not in this document.

---

## 1. The printed object

A **volume** is N pages of A4 (or other media). Each page is a
rectangle of **cells**. A cell has a physical pitch — an exact
rational of an inch, the only quantity in the format id. How many
*device dots* make a cell, and how many *scanner pixels* sample it,
are not format. They are the engine grid and the capture grid
(§2a).

Cells tile a **field** of `tiles_y × tiles_x` **tiles**, each tile
64×64 cells. Partial tiles do not exist. Slack between field and
payload-safe margin is split across the two borders; the odd device
dot goes to bottom/right.

What is *not* on the page: finder patterns, quiet zones, headers,
version bytes, a nonce, a printed seed. Identity is implicit. A
receiver that descrambles the wrong row gets coin-flip words.

Ink polarity: **nonzero = toner = bit 1**. K pages are a 1-bit
imagemask. Colour pages are three 1-bit planes C, M, Y (no K
payload). State ID of a colour cell is the presence integer
`C + 2·M + 4·Y` (W=0 … CMY=7).

---

## 2. Conventions (format-wide)

These are HOLO-DESIGN §13.12 and the emission contract. They apply to
every integer, every bit string, every bitmap.

1. Multi-byte integers are **big-endian**.
2. Bit strings are **MSB-first**: bit `j` of a byte sequence is
   `(byte[j // 8] >> (7 - j % 8)) & 1`.
3. `np.packbits` / zlib CRC packing on the format surface use that
   convention. The fountain *internal* GE packer is little-bit-order
   inside uint64 words and **must not** appear on paper or in an
   envelope.
4. Raster indices are `(y, x)`, origin **top-left**, y down, matching
   numpy. PostScript's bottom-left y-up conversion happens only at
   emission.
5. Coordinates:
   - **page cell** `(Y, X)` in `[0, 64·tiles_y) × [0, 64·tiles_x)`
   - **tile** `(ty, tx) = (Y // 64, X // 64)`
   - **in-tile cell** `(cy, cx) = (Y % 64, X % 64)`
   - **flat in-tile index** `cy·64 + cx` in `[0, 4096)`
6. Plane index in the keystream is `'CMYK'.index(plane)`; K = 3.
   Colour *stream* auxiliaries are a different table (§5).

---

## 2a. Pitch, engine grid, scan grid

Three different things (FORMAT-SPACE §2.5 and §4). Identity carries
only the first.

| quantity | lives | typical name |
|---|---|---|
| **physical pitch** | format id | `c2`, `1i300`, `1i50` — exact `n/d` inch |
| **engine grid** | generation / manifest | `engine_dpi`; `dots_per_cell = pitch × engine_dpi ∈ ℤ⁺` |
| **scan grid** | capture | declared scan dpi; `ppc = pitch × scan_dpi` |

Named classes are sugar for rationals that showed up on the measured
600-dpi engines. They are not a privileged grid, and they are never
canonical. **The canonical token is always the reduced rational**: the
parser accepts `c2`, `1i300` and `2i600` alike and normalizes all three
to `1i300`; `c2` is what gets printed back at a human (FORMAT-SPACE §4,
amended 2026-08-30). The reason is in the code — a class registry is
append-only, so preferring a registered name would let an append
re-spell an already-minted identity, and the canonical string *is* the
AES row seed. A 3-dot cell on a 1200-dpi engine is `1i400` (63.5 µm)
and needs no new class until someone wants a name; `1i400` stays that
sheet's canonical name whether or not the pitch later earns one.

```
Class   pitch         300 dpi    600 dpi    1200 dpi    2400 dpi
c1      1/600 in      —          1 dot      2 dots      4 dots
c2      1/300 in      1 dot      2 dots     4 dots      8 dots
c3      1/200 in      —          3 dots     6 dots      12 dots
c4      1/150 in      2 dots     4 dots     8 dots      16 dots
c12     1/50  in      6 dots     12 dots    24 dots     48 dots
c24     1/25  in      12 dots    24 dots    48 dots     96 dots
```

`c12` / `c24` are not currently registered class names; they are
written here as `N` dots @ 600 dpi = `N/600` inch (`1i50`, `1i25`).
Any positive reduced rational is a lawful pitch.

**Emission gate:** `dots_per_cell = pitch × engine_dpi` is a
positive integer, and that is the *only* gate. There is no
minimum-cell floor in the format (FORMAT-SPACE third-round ruling).
`c1 --dpi 600` emits if you ask.

**What 600 dpi is.** An artefact of the two qualified engines (HP
M281, Xerox AltaLink C8245): both are fixed-600 devices end to end.
A 2400 dpi printer prints the same `c2` sheet at 8 dots/cell; a 300
dpi printer prints it at 1 dot/cell. The format id does not change.
`/HWResolution` is RIP-talk for those engines — requesting `[1200
1200]` on them corrupts (M281) or point-samples (AltaLink). It is
not a format field. Never request a grid the engine has not been
shown to honour (DESIGN.md §9.1); that is device law, not toner
meaning.

**What actually binds** is the triangle pitch × engine × scanner,
plus morphology:

- **Print, 600 dpi xerography (measured):** isolated 1-dot cells do
  not develop (c1@600 dead both polarities); 1-dot *lines* do;
  Nyquist 1-on/1-off closes solid; min usable white ~3×3; ~+0.4
  dot/edge gain. **Fine end those engines handle well: 1i300
  (c2).** That is characterization, and it informs the operator; it
  does not refuse emission.
- **Scan:** c2 at 2 px/dot is sampling-limited; at 8 px/dot
  ctx+PAVA reads 2–5% on the same prints (016.2). The Canon of
  record has knife-edge MTF10 ≈ 17 lp/mm ≈ 860 dpi information
  ceiling (e028) — the optical reason the old decimate-to-1600
  doctrine existed. Footings are `ppc`, never a hardcoded 600.
- **Receiver (e021 survey):** one 340 µm tensor scale, converted
  through the caller's true scan dpi, was qualification-tested on c1,
  c2, c3, c8, c12 (global pitch votes correct on the held-out 4800-dpi
  matrix: 8.0 / 16.0 / 24.1 / 64.0 / 96.3 scanner px; at 1200 dpi the
  same five cells read 2 / 4 / 6 / 16 / 24 px). c12
  (= 1i50, 0.508 mm) is a coarse pitch current receivers handle
  comfortably; c12 mask IoU is the weak end of that ladder. That is a
  receiver ladder, not a format cap — the format bounds pitch neither
  from above nor from below, only by integrality.

The page *raster in device dots* is `media_mm × engine_dpi`,
byte-aligned. A4 @ 600 dpi happens to be 4960×7016; at another
engine dpi it is a different integer. The field in *cells* is what
the format id names (`@53x37`).

---

## 3. Identity

A canonical format id **is** the AES row-seed payload under
`holo/v2/`:

```
format-id  = coding-id "@" tiles_y "x" tiles_x
coding-id  = pitch "-" family [ "-" rungs ] "-p" sites "-v" gen

pitch   = reduced "NiD" (n/d inch), ALWAYS — class names are sugar (§2a)
family  = "k" | "cmy7" | "cmy8" | "cmy"        // cmy added 2026-10-11
rungs   = k: one "r0700"
          cmy8: uniform "r0700" or mixed "r0700x0700x0550" (C,M,Y)
          cmy: uniform "r0700" or mixed "r0775x0700" (hi,lo)
          cmy7: omitted (baked per generation)
sites   = ALWAYS spelled; an omission on *input* fills the frozen
          defaults k → p100, colour → p120
gen     = ALWAYS spelled; frozen default v1
```

(2026-10-11: the `cmy` lines are FORMAT-SPACE §19; the family is §12.5.
`c2-cmy-r0775x0700@53x37` is display for
`1i300-cmy-r0775x0700-p120-v1@53x37`.)

The row seed is `b"holo/v2/" || canonical-id.encode("ascii")`. The
canonical string is fully explicit and reads no mutable table: reduced
rational pitch, sites and generation always written out (uniform cmy8
triplets still contracted).

**Display is a different string.** The short spelling — registered
class name where one exists, defaults omitted, triplets contracted — is
what a person types and what every message, log, pane and CLI listing
shows. It is never stored and never seeded. Worked example:
`c2-cmy8-r0700@53x37` is display for the canonical
`1i300-cmy8-r0700-p120-v1@53x37`, and it is the latter the seed is made
of. The constructor refuses a non-canonical spelling outright, because
the coding id becomes the seed payload verbatim and a display spelling
would mint a second seed for one format. Parse normalizes; only the
canonical spelling is stored, so seed ↔ parameters stays bijective.

**Family seed** (site construction only, geometry-free):
`b"holo/v1/sites/" || family_id` (e.g. `p100`, `p120`). One lattice
serves every geometry of that density.

**Fossils.** Printed v1 identities that are not v2 grammar live in
`format/fossils.py`. They are matched **byte-exactly** under `L:`.
They never enter the parser. A generator of new volumes does not
emit fossils.

KDF prefix `holo/v1|` is a label, not a version claim. It does not
change when the identity namespace became `holo/v2/`.

---

## 4. The keystream

All format-defining bits are a pure function of address. There is no
stream cursor, no rejection state across calls (except the local
retry index `v` inside one draw), no numpy.

```
key         = SHA-256( b"holo/v1|" || seed )[0:16]     // FIPS 180-4
counter128  = [domain:8][aux:8][major:24][u:32][v:32][zero:24]   // BE
block       = AES-128-Encrypt(key, counter128)         // FIPS 197
bit         = block[0] >> 7                            // MSB of byte 0
```

Implement AES from FIPS-197 or call a library; it MUST match
`keystream_spec.aes128_encrypt_block` on the FIPS appendix vectors
and on the holo goldens.

**Bounded byte draw** (sites, slot-perm 8-bit form): scan block
bytes at `v = 0, 1, 2, …`; accept the first byte `b < 256 - (256 %
bound)`; return `b % bound`. Bound is in `1..=256`.

**Bounded 16-bit draw** (slot-perm, fillers): scan big-endian
byte-pairs of successive blocks the same way against
`65536 - (65536 % n)`.

### Domain table (byte 0 of the counter)

| id | name | aux | major | u | v | draw form |
|---:|---|---|---|---|---|---|
| 1 | payload scramble | plane | page | cell y | cell x | bit |
| 2 | pilot word values | plane | 0 | site index | 0 | bit |
| 3 | filler values | plane | page | cell y | cell x | bit |
| 4 | pilot sites | 0 | 0 | quota index | retry | bounded |
| 5 | filler sites | 0 | 0 | filler index | retry | 16-bit cells |
| 6 | slot-perm params | 0 | 0 | tile counter | retry | 16-bit |
| 7 | fountain rows | 0 | block | row | col word | 128 bits/block |
| 8 | block assignment | 0 | page | local tile | 0 | u64 BE key, bytes 0..7 |
| 9 | colour dust order | 0 | tile | base ordinal (dust, `u < n_dust`); cmy word site `n_dust + i` (2026-10-11) | 0 | u64 key; cmy word: bit |
| 10 | CMY7 interleave | 0 | tile | code-bit idx | 0 | u64 key |
| 11 | CMY7 dither | 0 | tile | wire-bit idx | 0 | bit |
| 12 | colour cell order | 0 | tile | state ordinal | 0 | u64 key |
| 13 | CMY8 dither | stream | tile | cell ordinal | 0 | bit |
| 14 | colour fountain row | stream | block | row | col word | packed like 7 |
| 15 | colour block assign | stream | page | local tile | 0 | u64 key |

Colour stream aux: `0` = CMY7 main, `1` = C, `2` = M, `3` = Y.
cmy (2026-10-11, §12.5) uses domain 13 at the INTEGERS `1` (stream
`hi`) and `2` (stream `lo`) — the stream's ordinal + 1, never a lookup
of the names above; it shares (13, 1) and (13, 2) with cmy8's C and M,
never their bits (the seed spells the family).

Domain 7/14 packed form: coefficient `c` of `(block, row)` is bit
`(c % 128)` of the block at `v = c // 128`.

One AES block per drawn *value* is the default (the ×128 waste is
accepted so there is no packing-order hazard). Domains 7 and 14 are
the documented exception.

---

## 5. Tile counter

```
c = page · tiles_per_page + ty · tiles_x + tx
```

18 bits. `0 <= c < 2^18`. This is the address-word message and the
ESI of a single-stream volume. Pooled CMY8 uses
`esi = c · 3 + stream_idx` instead, without changing `c`; pooled cmy
(2026-10-11, §12.5) uses `esi = c · 2 + s`, `s = 0` hi, `1` lo.

---

## 6. Pilot sites (family seed)

Every tile of a family carries the **same** 100 word-site positions.
Periodicity is load-bearing: Stage A removes the value scramble
under a phase hypothesis without knowing `c`.

**Quota construction.** Split the 64-cell axis at
`floor(i · 64 / 10)` for `i = 0..10`:

```
[0, 6, 12, 19, 25, 32, 38, 44, 51, 57, 64]
spans 6,6,7,6,7,6,6,7,6,7
```

Quota cell `q = qi·10 + qj` (raster) contributes exactly one site:

```
dy = bounded_draw(family_seed, domain=4, u=2q,     bound=span_y(qi))
dx = bounded_draw(family_seed, domain=4, u=2q+1,   bound=span_x(qj))
site(q) = (edge[qi]+dy, edge[qj]+dx)
```

Word codeword bit `i` is printed at site index `i`.

**Fillers (K, F extra known cells).** v1 rows launch at F=0. Draw F
collision-free cells by 16-bit rejection over `[0, 4096)` (domain 5,
`u = filler index`, `v = retry`), skipping word sites and earlier
fillers. `65536 % 4096 == 0`, so the modulus is unbiased.

**Dust (colour).** `n_dust = p - 100` extra sites from the same filler
construction under THAT `p`'s own family seed, `holo/v1/sites/p{p}`,
then sorted into canonical physical raster order (by `y·64+x`). Only
colour assigns *states* to them. **p120 (20 dust) is the printed case**
and the only one qualified on paper; every other lawful `p` is a
different site lattice, not this one with cells added (FORMAT-SPACE
§18).

---

## 7. Address words (row seed)

Message, 23 bits, MSB-first:

```
[counter : 18][zero pads : 5]
```

The five pads are identically zero under encoding. A data-dependent
pad would flip ~40 of 100 transmitted bits (parity spread) and
destroy the cold correlation template. The 2⁻⁵ pad check is a cold
gate at the receiver; the generator just writes zeros.

**Code.** Narrow-sense BCH over GF(2⁷), primitive polynomial
`0x89 = x⁷ + x³ + 1`, roots `α¹ … α²⁶`, designed distance 27,
generator degree 77. Full code BCH(127,50,t=13). Shorten by 27:
highest-order information positions `x¹⁰⁰ … x¹²⁶` are fixed 0 and
not transmitted. Transmitted word = coefficients of `x⁰ … x⁹⁹`.
Systematic: message bit `j` at position `77 + j`; positions `0..76`
are the parity remainder.

`g(x)` is derived from the cyclotomic root set, never stored. Pin
its digest. Errors-only decode is t=13; erasures `2e+f ≤ 26` live
inside the decoder (no caller budget).

**Printed word values** (K, plane aux=3):

```
printed[site i] = codeword[i] XOR bit(row_seed, domain=2, aux=3, major=0, u=i, v=0)
```

The scramble is **site-local and periodic** (same 100 bits on every
tile). Colour renders the same binary word as states W=0 / CM=3
(`printed_bit · 3`). *Corrected 2026-10-11:* that is CMY7 and CMY8;
cmy renders `1` as C and `0` as a keyed W or Y per site (§12.5).

---

## 8. Inner code (one tile)

Mother code: e-IRA QC-LDPC, `n = 4096 = 64²`, `Z = 64`. Six rungs;
`k_bits` is a multiple of 64:

| rung | k_bits | heavy column degree |
|---|---:|---:|
| r0547 | 2240 | 10 |
| r0550 | 2240 | 10 |
| r0625 | 2560 | 10 |
| r0700 | 2880 | 10 |
| r0775 | 3200 | 8 |
| r0850 | 3520 | 6 |

r0547 and r0550 share k and are **different codes** (independent
draws).

**Construction, then pin.** The mother codes are e-IRA: QC `H_d`
(heavy info columns first, degree 10/8/6 then degree 3; greedy
column draw with distinct rows, tap-gap floor ≥24, QC 4-cycle rule,
row-degree cap), a Fisher–Yates row interleaver `Π`, and a
**bit-serial** dual-diagonal accumulator. Textbook block-circulant
accumulators produced weight-8..10 codewords and undetected
syndrome-valid wrongs; that is why this draw exists and why
certification is CRC-32, not the syndrome.

The normative draw is `src/paperholo/ldpc.py` (`build_code`): seed
label `ldpc-v1/<rate_id>`, per-restart generator
`eira-H/restartR`, integers-only (no `.choice`). All six committed
rungs won at `restart = 0`. `util/regen_holo_ldpc_data.py` re-runs
that live construction, checks it against paperholo's `H_SHA`
anchors, and writes `src/holo/core/ldpc/data/<rung>.json`
byte-identically — `pi`, heavy/light rows and shifts, `restart`,
geometry. Demonstrated 2026-07-19.

A **page** generator does not re-draw. `holo.core.ldpc.construct`
only *expands* those JSON files to bit-level edges (no RNG). The
format identity pin is independent of the regen script: golden
digests over the canonical little-endian lexsorted edge arrays live
in `tests/holo/test_holo_ldpc.py` (bump-don't-edit). A mismatch
there is a format fork whether or not the JSON still "looks like"
an IRA.

So: implement LDPC encode/decode against the expanded JSON. Remake
the JSON only with the regen path (or a bit-exact twin of
paperholo's draw). Do not substitute a new construction.

**CRC-32.** zlib polynomial, over the user bits packed MSB-first
(`np.packbits`, last byte zero-padded), result as 32 bits MSB-first
big-endian. Trailer sits in the info word immediately after the
user bits.

**Info layout** (length `k_bits`):

```
[ user : S+1 ][ CRC-32 : 32 ][ shortened zeros : p ]
```

`p` = site count (100 K / 120 colour). Shortening consumes the
**info tail only**. Parity is always transmitted. No degenerate
tiles.

```
S = k_bits - 32 - p - 1     // −1 is the metadata bit
user = [ metadata bit ][ fountain symbol : S ]
```

At r0550/p100: `S = 2107`. Uniform across the page.

**Transmitted positions** (ascending): `[0, k-p) ++ [k, n)`.

**Slot permutation** (per tile, breaks the tile-invariant shorten).
Let `nonsite[0..T)` be the sorted complement of the site cells in
`[0, 4096)`, `T = 4096 − p`. Draw `(a_t, b_t)` from domain 6 at
`u = c`: scan 16-bit rejection values; `a_t` = first with
`gcd(a_t, T) = 1`, `b_t` = the next admissible value. Both in
`[0, T)`; `a_t ≠ 0`.

```
cell of transmitted bit j = nonsite[ (a_t · j + b_t) mod T ]
```

Site cells are **not** written by the LDPC mapper. The generator
overwrites them with word / filler / dust values after the payload
scatter. (Implementation order: zero the sites in the codeword
image, then paint furniture.)

---

## 9. Metadata bit

One LDPC user bit per tile (the first info bit). The 24-bit word

```
M = [version:1][K:18 BE][reserved zeros:5]
```

`version = 0` is fountain-v2. `K` is the source-symbol count of the
(one) fountain. On pooled CMY8, this field is `k_meta` and
`k_total = 3 · k_meta`; on pooled cmy (2026-10-11)
`k_total = 2 · k_meta`.

Tile `c` carries the equation `bit(c) = ⟨coefficient(c), M⟩` over
GF(2). `coefficient(c)` is LFSR state `c` (or, pooled,
`c·n_streams + stream_idx`) of the maximal-length degree-24
register

```
poly    = x^24 + x^4 + x^3 + x + 1     // 0x100001b
s'      = ((s << 1) & 0xffffff) XOR (0x1b if s & 0x800000 else 0)
s0      = 1
```

Integer bit `i` of the state multiplies `M[i]`. Every 24 consecutive
indices are a basis; arbitrary sets recover iff rank 24. The
receiver additionally requires 48 distinct equations before trust.
The generator just writes the honest parity of `M` against the
state.

---

## 10. Envelope and fountain

**Envelope**, then zero-pad to `K · S` bits:

```
stream = SHA-256(data) || len(data) as u32 BE || data
K      = ceil( 8 · (36 + len(data)) / S )     // canonical, minimal
```

Bits after the envelope through `K·S` are zero. A generator that
picks a larger K has produced a different volume; close will refuse.

**Pooled rows (§12.2) do that arithmetic at the aggregate width.**
With `n` streams of the one width `S`, let `S_agg = n·S`:

```
k_meta  = ceil( 8 · (36 + len(data)) / S_agg )   // the metadata field
k_total = n · k_meta                             // fountain source rows
```

The padded envelope is `k_meta · S_agg` bits — byte-identical padding
to the per-stream case — sliced **row-major** into `k_total` rows of
`S` bits: consecutive `S`-bit slices of one bitstream, deliberately
replacing `-v0`'s stream-major thirds. Blocks are the frozen rule
below, applied to `k_total`. The close gate recomputes `k_meta` from
the recovered length and requires equality and zero padding, the same
shape as the single-stream gate.

**Fountain-v2.** Systematic dense random-linear over GF(2).
`B = ceil(K / 16384)`. First `(K mod B)` blocks have `K_b = K//B + 1`
source rows; the rest `K//B`. Source rows of block `b` are a
contiguous slice of the packed envelope.

**Block assignment** (the occupancy law; not `ESI mod B`):

Let `T = tiles_per_page`, page `p`, local index `i = c % T`.

```
quota_b(p) = T//B + (1 if (b − p) mod B < (T mod B) else 0)
key(p, i)  = u64 BE of AES block domain 8 at (major=p, u=i, v=0)
```

Argsort the T keys (ties by `i`). The sorted tiles receive
`[0]*quota_0 ++ [1]*quota_1 ++ …`. Within `(page, block)`, ascending
local index takes consecutive in-block rows, starting after the
cumulative quota of that block on earlier pages.

Rows `r < K_b` are source (identity). Rows `r ≥ K_b` are repair:
coefficient `c` of column `c` is domain-7 packed bit `(b, r, c)`.

Pooled CMY8 (`n = 3`, the `-v1` rows) is **keyed like K** — domains 8
and 7, every family, colour included; pooled cmy (`n = 2`, 2026-10-11)
the same. Quotas and keys are per
`(page, stream)`:

```
quota_b(p, s) = T//B + (1 if (b − (p·n + s)) mod B < (T mod B) else 0)
key(p, i, s)  = u64 BE of AES block domain 8 at (major=p, u=i·n+s, v=0)
```

argsorted **within each stream's T keys**; within `(page, stream,
block)`, ascending local index takes consecutive in-block rows starting
at that block's cumulative quota over all earlier `(p, s)` pairs,
ascending. Repair coefficients ride domain 7 exactly like K. `n = 1`
reproduces the K assignment bit-exactly — that identity is the
format-fork guard. A dead plane then removes exactly its quota from
every block.

Domains **14 and 15 are not this construction.** They belong
exclusively to the `-v0` per-stream colour path, which runs one
fountain per plane and never pools; a pooled code refuses a `stream_id`
outright. The two are mutually exclusive: read the keying of the
generation the row names.

Whole-page loss is a **deterministic** recovery tier. Sub-page
fragments are hypergeometric. That is the holographic promise, as
printed.

Capacity planning (q dial, rank reserve `16 + bit_length(B·n − 1)`; for a column-group row `16 + bit_length(B·Z − 1)`, one close per (block, group) — docs/CMY8-COLUMN-GROUPS.md ruling 5)
is generator policy. It does not change what a given `(K, pages,
assignment)` means.

---

## 11. Payload scramble and cell paint (K)

For each non-site cell at page coordinates `(Y, X)` on page `p`:

```
printed = code_bit XOR bit(row_seed, domain=1, aux=3, major=p, u=Y, v=X)
```

Site cells: word values (§7), not payload. Filler sites (if F>0):
known bits from domain 3 at the cell address.

Expand each cell to `dots_per_cell × dots_per_cell` device dots
(`dots_per_cell = pitch × engine_dpi`). Place the field at
`origin_dots_yx` on the page raster (media × engine_dpi,
byte-aligned). Pack rows MSB-first, pad each row to a byte, emit
Level-2 PostScript `imagemask` at the engine's native grid. No
fiducials. Job title may carry an 8-hex jobid; it is not format.
`/HWResolution` in the PS, if present at all, restates the engine
grid the operator already chose — it does not encode pitch.

---

## 12. Colour families

Plane order is always C, M, Y. Words are W/CM on all colour rows
(addressing is Y-immune by construction). *Corrected 2026-10-11:* on
CMY7 and CMY8 rows; cmy words are C for `1` and W or Y for `0`
(§12.5), still Y-immune — a dead Y reads W, still `0`.

### 12.1 Dust states

Base cycle (missing states, canonical order):

- CMY7 (5): C, M, Y, CY, MY. 20 sites = four full cycles, no extras.
- CMY8 (6): C, M, Y, CY, MY, CMY. 20 sites = three cycles + two
  extras at cycle indices `(2c + j) mod 6` for `j = 0, 1`.

In general the vector is `n_dust // len(cycle)` full cycles in
canonical order followed by `r = n_dust % len(cycle)` address-keyed
extras at cycle indices `(r·c + j) mod len(cycle)` for `j < r`; the two
lines above are that law at the printed `n_dust = 20`, the only density
qualified on paper (FORMAT-SPACE §18). Domain 9 permutes that vector
onto the `n_dust` dust sites in physical raster order, keyed by tile
counter.

### 12.2 CMY8 (presence, independent planes)

Three independent inner codes, one per plane, same tile geometry,
same sites. Each plane's transmitted bits are dithered (domain 13,
stream aux 1/2/3) and mapped to that plane's presence bit. The
physical state is the OR of the three presences. Fountain is pooled
(§10). One plane may be empty; siblings remain.

User width `S` must match across the triplet (one fountain symbol
width) unless the row declares column groups. Mixed rungs of equal
`k_bits` (e.g. r0550 with r0547) are legal at one width.

**Uneven triplets: the column-group pool.** Ruled and built 2026-09-04,
under **gen-v1** and not a new generation, not printed:
`docs/CMY8-COLUMN-GROUPS.md` is the construction and this is only the
pointer. The pool is GF(2)-column-separable, so the widest plane's `S`
is carried as `Z` column groups and a lighter plane carries fewer
consecutive groups per tile, rotating over the fill; uniform triplets
are the one-group case and stay bit-identical, which is the fork guard.
First ruled rows: `r0700x0700x0547` and `r0850x0850x0775`. A generator
must read that document before emitting one — those identities are
lawful, not future work.

### 12.3 CMY7 (pack7, joint)

One joint user frame. Transmitted bits are interleaved (domain 10
sort keys) and dithered (domain 11). Consecutive groups of **11
bits, MSB-first**, map to **four** radix-7 digits, most-significant
digit first, values 0..6 = states W..MY. The 353 tuples that would
need digit 7 are never admitted; the codebook is

```
digit[k] = floor( word / 7^{3-k} ) mod 7     // k = 0..3, word in 0..2047
```

and the table, not the expression, is the mapper pin. Physical cells
of a pack are ordered by domain 12. A pack with any unobserved slot
is an 11-bit erasure at the receiver. There is no per-plane fallback.

### 12.4 Colour emission

One 1-bit/component DeviceCMYK image, K samples inserted as zero,
components interleaved C,M,Y,K per pixel, row padded to a byte
*after* the four-way interleave. Same engine grid as the K path,
same no-fiducials rule. Overprint vs screened-composite is a
**device** fact (M281 re-screens any overlap; AltaLink overprints).
The format does not encode a paint-path escape; generators MUST
emit the composite the chosen engine will honour. *Amended 2026-10-11:*
this composite is the `cmyk1` route, the default; a cmy row may instead
take the `rgb` route (§12.5) when the chosen engine's record names it.

### 12.5 cmy (two label-bit streams, single-toner cells) — added 2026-10-11

Built 2026-10-11, not printed, catalog-only (FORMAT-SPACE §19; design
of record `docs/CMY-DESIGN.md`; spec vectors written from that text
before the code, `tests/holo/test_cmy_vectors.py`). A cell is white or
carries exactly one toner: states W, C, M, Y = presence ids 0, 1, 2, 4.
No overlap state, no K.

**Streams.** Two, in this order: `hi` (index 0), `lo` (index 1). They
are the cell's LABEL bits, not planes:

```
hi = 1  iff  state in {C, M}
lo = 1  iff  state in {C, Y}
state = (W, Y, M, C)[(hi << 1) | lo]       // presence ids (0, 4, 2, 1)
```

Each stream is one independent inner code per tile (§8) at its own
rung — the id spells `r{hi}x{lo}`, one rung meaning both — shortened by
`p`, so `S = k_bits − p − 33` per stream. Each stream's transmitted bits
are XORed with domain 13 at aux `1` (hi) or `2` (lo); a payload cell's
two dithered bits index the table above; domain 12 orders the payload
cells as for every colour row. Fountain: pooled (§10) at `n = 2`,
`esi = c·2 + s`, `k_total = 2·k_meta`, metadata index `c·2 + s` (§9). An
uneven pair carries column groups (`docs/CMY8-COLUMN-GROUPS.md`; e.g.
`r0775x0700` at p120: `Z = 19`, carried 19:17).

**Furniture sites** are §6's: the 100 word sites and the
`n_dust = p − 100` dust sites of `holo/v1/sites/p{p}`. `p` is spelled
in the id; p120 is the input default and p100 is refused (M appears
only in dust).

**Word sites.** The binary word of §7, K-plane scramble included, is
painted per site `i`:

```
bit 1  →  C
bit 0  →  Y  if bit(row_seed, domain=9, aux=0, major=c, u=n_dust+i, v=0) == 1
          W  otherwise
```

Domain 9's dust order draws only `u < n_dust`, so the word keys never
touch it.

**Dust sites.** The fill vector is not a cycle (§12.1) but the BALANCE
LAW over this tile's own word states:

```
total[s] = count of state s among the tile's 100 word states   // total[M] = 0
for j in 0 .. n_dust−1:
    s = the first of M, Y, W, C whose total is lowest           // ties in that order
    fill[j] = s;  total[s] += 1
```

then domain 9 at `u < n_dust` permutes `fill` onto the dust sites in
physical raster order, exactly as §12.1 permutes a cycle vector. At p120
most tiles get twenty M; a tile short of W or Y gets a split (counter 30
of `c2-cmy-r0700@10x10`, Y 15 among its words: M 18, Y 2). A reader
recomputes both from the seed and the counter.

**Emission.** Either route; the GT is the C/M/Y planes on both.
`cmyk1` is §12.4. `rgb`, per page, three imagemasks over the same field
origin, in plane order C, M, Y:

```
(r/255) (g/255) (b/255) setrgbcolor      // that toner's engine value, 6 decimals
w h true [w 0 0 -h 0 h]                  // 1 = paint
currentfile /ASCII85Decode filter imagemask
<the plane's dot rows, MSB-first, each padded to a byte, ASCII85>
```

White is never painted; there is no PJL, no palette and no prologue
beyond PSDoc's head. The three `(r, g, b)` are the ENGINE's record, not
format: the devices registry's `Printer.rgb_solid`, which for the
registry's `hp-m281` row holds the values the e043 probe sheets
measured (`experiments/043-m281-cmy-probe.md` §043.3c, §043.5, §043.6).
The masks are opaque, so the route is lawful only where one toner per
cell is the whole alphabet: it refuses CMY7 and CMY8. Job size, A4-4mm
`c2-cmy-r0775x0700@53x37`: 15,061,180 B `rgb` against 32,380,665 B
`cmyk1` (`tests/holo/test_cmy_emission.py`).

---

## 13. Generator procedure (normative outline)

Given payload bytes, a canonical format id (or `L:` fossil), q, media
and margins:

1. Resolve identity → row seed, family seed, family, rungs, p, tile
   matrix, pitch. Fossils: look up, do not parse.
2. Wrap envelope; compute canonical K (and k_meta if pooled); refuse
   if K exceeds the 18-bit field or the q/page budget.
3. Build fountain assignment for every `(page, tile, stream)`.
4. For each tile counter `c`:
   1. Metadata bit = ⟨LFSR(index(c,s)), M⟩.
   2. Fountain symbol = source row or repair row of `(block, r)`.
   3. `user = metadata || symbol`; CRC; LDPC encode; slot-permute
      onto non-site cells.
   4. XOR payload scramble at absolute cell addresses.
   5. Paint word (and dust/fillers) onto site cells.
5. Rasterize cells → device dots at field origin.
6. Emit PS as §11/§12.4. Hash the artifact; that hash is the
   generator's claim, not a printed field.

A second generator is conformant iff it matches the goldens: one
full-page compose SHA per row, keystream vectors per domain, word
codewords for known counters, the 100-site pattern per family, the
canonical fountain assignment digest (stable-sort ties).

---

## 14. What a generator must not invent

- A version nibble in the address word. Format is the seed.
- A sequential RNG, a `dtype`, a packed AES that isn't domain 7/14.
- Global interleaving across tiles (destroys fragment locality).
- Partial edge tiles.
- K toner on a colour page.
- Fiducials, quiet zones, a human-readable seed on the data sheet
  (the Plate is a different object; see BOOTSTRAP-DESIGN).
- A new LDPC draw, a "simpler" BCH, `ESI mod B`. Remaking the
  committed JSON is `util/regen_holo_ldpc_data.py`, not a fresh IRA.

---

## 15. Pointers

| need | where |
|---|---|
| AES/KDF/counter, as code | `src/holo/core/keystream_spec.py` |
| BCH | `src/holo/core/bch.py` |
| LDPC JSON (expanded by holo, drawn by paperholo) | `src/holo/core/ldpc/data/` |
| LDPC regen | `util/regen_holo_ldpc_data.py` (`--check` is read-verify) |
| LDPC draw (normative docstring) | `src/paperholo/ldpc.py` |
| tile framing | `src/holo/core/ldpc/tile.py` |
| sites + words | `src/holo/format/pilots.py` |
| fountain assignment | `src/holo/core/fountain.py` (module docstring is the derivation) |
| envelope | `src/holo/format/envelope.py` |
| identity grammar | `src/holo/format/lattice.py`, `docs/FORMAT-SPACE.md` |
| CMY mapping | `src/holo/core/channel.py` |
| emission | `src/holo/gen/ps.py` |
| page field geometry (the printed field in cells; not the PAGE-FIELD registration field of `docs/PAGE-FIELD-DESIGN.md`) | `src/holo/format/layout.py` |
| pitch vs engine vs scan | `docs/FORMAT-SPACE.md` §4 |
| uneven cmy8 triplets | `docs/CMY8-COLUMN-GROUPS.md`, `src/holo/core/column_groups.py` |
| cmy (2026-10-11) | `docs/FORMAT-SPACE.md` §19, `docs/CMY-DESIGN.md`, `src/holo/format/families.py` (`cmy_codec`), `src/holo/format/pilots.py`, `src/holo/core/channel.py` (label table) |

The governing prose, if a conflict must be argued rather than
measured, is `docs/HOLO-DESIGN.md` as amended by
`docs/FORMAT-SPACE.md`, `docs/CMY8-POOLED-FOUNTAIN.md` and
`docs/CMY8-COLUMN-GROUPS.md`.

---

## 16. Corrections from the founding note (2026-09-13)

What changed when `holo4/docs/PRINT.md` was carried into `docs/`. Each
line is the claim as it stood, and the authority that overruled it.

The source note is not in this repository. It was untracked at the repo
root, and the archive of its directory does not duplicate it
(`docs/archive/holo4/README-ARCHIVE.md:7-8, 15-18`); its date and provenance
are tracked (`docs/archive/holo4/CHARTER.md:3, 9-11`,
`docs/archive/holo4/docs/README.md:3`), its text is not. So the "as it
stood" half of every item below is unverifiable from here. What a reader
*can* check is the text above against the authority cited — do that, and
treat this list as provenance, not proof.

1. **§2a, the pitch token.** The note said the parser canonicalizes
   `1i300` and `2i600` to `c2`. Backwards: the canonical token is
   always the reduced rational and class names are input/display sugar
   only. `docs/FORMAT-SPACE.md:116-118`;
   `src/holo/format/lattice.py:90-99` (`canonical_pitch_token`, with
   the append-only-registry reason) vs `:102-109`
   (`display_pitch_token`). The amendment is dated 2026-08-30
   (`docs/FORMAT-SPACE.md:13-15`), two days before the note.
2. **§3, identity.** The grammar made sites and generation optional in
   the string that becomes the seed. Canonical always spells both and
   always uses the reduced rational; the bracketed form is the
   *display* spelling, and the worked example is now carried:
   `c2-cmy8-r0700@53x37` → `1i300-cmy8-r0700-p120-v1@53x37`.
   `docs/FORMAT-SPACE.md:231-249`;
   `src/holo/format/lattice.py:7-18`, `:132-138`
   (`canonical_coding_id` appends `p{sites}` and `v{gen}`
   unconditionally), `:201-209` (`_coding_for_id` refuses a
   non-canonical spelling — "the coding id becomes the seed payload
   verbatim"). This was the note's dangerous error: the wrong spelling
   seeds a different AES key and prints noise.
3. **§10, pooled CMY8 keying.** The note put pooled quotas and keys on
   domains 15 and 14. Those are the `-v0` per-stream colour path, which
   never pools; the `-v1` pooled rows key like K on domains 8 and 7 for
   every family. `docs/CMY8-POOLED-FOUNTAIN.md:97-113` ("repair
   coefficients ride `DOMAIN_FOUNTAIN_ROW` exactly like K … `-v0`'s
   domains 14/15 are untouched"); `src/holo/core/fountain.py:310-318`
   (a pooled code refuses a `stream_id`) and `:425-437`;
   `docs/HOLO-DESIGN.md:323` (the amended domain-8 wording).
4. **§10, pooled K.** The note gave only `K = ceil(8·(36+len)/S)`,
   which is the wrong arithmetic on a pooled row. Added: `S_agg = n·S`,
   `k_meta = ceil(8·(36+len)/S_agg)`, `k_total = n·k_meta`, and the
   **row-major** slice of the `k_meta·S_agg`-bit padded envelope into
   `k_total` rows of `S` bits. `docs/CMY8-POOLED-FOUNTAIN.md:76-84`;
   `src/holo/format/streamset.py:198-235`.
5. **§2a, the coarse bound.** Dropped the appeal to "a later Windsurf
   analysis" putting a bound around `c24@600 = 1i25`. No such analysis
   exists anywhere in this repo; the measured c1–c12 receiver ladder
   beside it is kept. The only pitch gate is integrality
   (`docs/FORMAT-SPACE.md:143-145`, `src/holo/gen/sheet.py:18-22`).
6. **§0, tree names.** "holo3's copy-and-stripped kernels" now names
   `src/holo/receiver/`: holo3 moved there 2026-09-05 (`2099338`), the
   same day the v1 receiver `src/holo/receive` (`284ae3e`) and holo2
   (`a805888`) were deleted. Every path in §15 was checked against
   `git ls-files` and all of them still exist.
7. **§12.2 and §15, uneven triplets.** "Mixed widths are a future
   generation" was superseded three days after the note: the
   column-group pool is gen-v1, ruled and built 2026-09-04, with first
   rows `r0700x0700x0547` and `r0850x0850x0775` (not printed). Added as
   a pointer, not a re-derivation: `docs/CMY8-COLUMN-GROUPS.md:1-18`
   and `:468-471` (ruling 6); `src/holo/core/fountain.py:76-95`;
   `src/holo/core/column_groups.py`.
8. **Status block.** Rewritten to record the carry, the corrections,
   and the rank below `docs/HOLO-DESIGN.md` and
   `docs/FORMAT-SPACE.md`.

The next two are repairs the first carry did not make, in the section
items 1 and 5 had already worked over. They were found by reading §2a
against its own emission rule and against the e021 log.

9. **§2a, the pitch table at 300 dpi.** The two unregistered rows
   contradicted the emission rule printed three lines under them:
   `c12` = 1/50 in is **6** dots at 300 dpi (the table said 4) and
   `c24` = 1/25 in is **12** (the table said 8). Corrected from the rule
   itself, `dots_per_cell = pitch × engine_dpi`
   (`docs/FORMAT-SPACE.md:143-145`, `src/holo/gen/sheet.py:18-22`); the
   registered c1–c4 rows were right and agree with
   `docs/FORMAT-SPACE.md:121-126`.
10. **§2a, the e021 pitch ladder's footing.** The five px values are
    right; the dpi label was not. They are 4800-dpi readings, not
    1200: the held-out matrix is
    `experiments/021-payload-regions.md:374-378`, its fixtures are built
    at `cell_px = c_dots * 8  # 4800 / 600` and surveyed at `dpi=4800.0`
    (`experiments/021-payload-regions/qualify_e021.py:256, 266`), and
    the log's own conversion `c = measured_cell_pitch_px * 600 /
    scan_dpi` (`021-payload-regions.md:26-30`) plus the scale's two
    footings — 16.063 px @1200, 64.252 px @4800 (`:88-89`) — say it
    twice more. At 1200 dpi those cells read 2 / 4 / 6 / 16 / 24 px.

Everything else above was read claim by claim against code or a
normative doc and stands as written. Items 9 and 10 are what that kind
of reading misses when it trusts a table: this list records what was
checked and against what, and a claim it does not cite is one the next
reader should still check.
