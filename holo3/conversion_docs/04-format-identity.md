# 04 — Format identity + geometry (FORMAT-SPACE v2 lattice, fossils, page geometry)

Sources pinned at worktree eeeed7a. All paths relative to
<checkout>. This subsystem is ~90% declarative data +
string law. It produces the one immutable `FormatRow` snapshot every other
stage reads. Nothing in it is scheduled; nothing in it is mutable after
construction — build once in `cli.py` before the engine starts, share
read-only across workers.

## 1. Purpose, inputs, outputs

Purpose: turn the operator's format reference into the complete frozen
description of the printed sheet — AES seeds, codec algebra, stream layout,
tile grid, pilot/dust site lattice, slot permutation parameters — with zero
registry lookups at decode time and zero possibility of a format fork.

Inputs (CLI):
- `--format REF` where REF is either `L:<legacy-spec-id>` (byte-matched
  against the fossil catalogue, NEVER parsed) or a v2 format id
  `coding@TYxTX` (normalizing parse).
- OR the e029 sugar: `--coding <legacy-coding-id> --printer <printer-id>`
  (§2 step F). Mutually exclusive with `--format`.
- `--pages N` (int, default 1).

Outputs:
- `FormatRow` (frozen dataclass, §6): identity strings, `seed: bytes`,
  `family_seed: bytes`, `Family`, `tiles_yx`, `pitch_in: Fraction`,
  per-stream codec facts, pooled flag, page count.
- `SiteGeometry` (frozen, §6): word/filler/dust cell arrays (int64,
  read-only numpy), payload cell indices, derived per-tile constants.
- Pure functions: `tile_counter/tile_address`, `word_values`,
  `dust_state_values`, `slot_perm_params`, `cell_map`, streamset
  pack/unwrap. All are pure functions of (seed, counter, params) — safe to
  call inside worker jobs with no shared state.

Units/dtypes: pitch is exact `fractions.Fraction` inches, never float,
never mm. px/cell on a capture = `pitch_in * Fraction(str(float(dpi)))`
(exact rational; the `str()` round-trip is deliberate — the rational the
declared decimal names). Cell coordinates int64 `(y, x)`; flat in-tile cell
index = `y*64 + x` in `[0, 4096)`. All multi-byte integers big-endian, all
bit strings MSB-first (numpy packbits/unpackbits default order IS the
format's).

## 2. Algorithm

### A. Frozen substrate constants (one home each)

- `TILE_CELLS = 64` (tile edge, cells); `N_CELLS = 4096`.
- `COUNTER_BITS = 18`; `MAX_TILES = 1 << 18 = 262144`; `PAD_BITS = 5`;
  `MESSAGE_BITS = 23`. Address word = BCH(127,50,t=13) shortened to
  (100,23), true d_min = 27 EXACT.
- `N_QUOTA = 10`; `N_WORD_SITES = 100`; `METADATA_BITS_PER_TILE = 1`;
  `CRC_BITS = 32`.
- `PLANE_K = 3` (= `'CMYK'.index('K')`); colour plane aux for per-plane
  keystream draws: C=0, M=1, Y=2.
- Keystream domains (constants only; draw kernels are lib/aes_ctr's
  distill): payload=1, pilot_values=2, filler_values=3, pilot_sites=4,
  filler_sites=5, slot_perm=6, fountain_row=7, block_assign=8,
  color_dust_order=9, cmy7_interleave=10, cmy7_dither=11,
  color_cell_order=12, cmy8_dither=13, color_fountain_row=14,
  color_block_assign=15.
- Colour stream auxiliaries (frozen): main=0, C=1, M=2, Y=3.
- KDF: `key = SHA-256(b"holo/v1|" + seed)[0:16]` — the prefix is a KDF
  label, not a version claim; identical for v1 and v2 seeds.
- Seeds: v1 row seed = `f"holo/v1/{coding_id}/{cells_y}x{cells_x}".encode()`
  (CELL geometry, `/`-joined); v2 row seed = `b"holo/v2/" +
  canonical_format_id.encode()` (TILE geometry, `@`-joined); family seed =
  `f"holo/v1/sites/p{n_sites}".encode()` in BOTH namespaces (frozen
  template — versioning it is a fork; equal-density sheets share the
  measured site layout).
- LDPC LADDER (n_bits = 4096 for every rung; the mother-code matrices are
  the FEC distill's, but `k_bits` is identity algebra): r0547→2240,
  r0550→2240 (distinct code, same k), r0625→2560, r0700→2880, r0775→3200,
  r0850→3520.
- Pitch classes: c1=1/600 in, c2=1/300, c3=1/200, c4=1/150. Rational token
  `{n}i{d}` = n/d inch, reduced. Class name canonical where registered.
- `Family` enum, str-valued, format-frozen: K="k", CMY7="cmy7",
  CMY8="cmy8". THE ONLY dispatch key, ever.
- Physical states (colour): W=0, C=1, M=2, CM=3, Y=4, CY=5, MY=6, CMY=7;
  `PLANE_ORDER = ("C","M","Y")`; CMY7 alphabet = first 7 states.
- Dust base cycles (state ids): CMY7 `(1,2,4,5,6)`; CMY8 `(1,2,4,5,6,7)`.
- Mapper units: K 1 bit/1 cell; CMY8 3 bits/1 cell; CMY7 11 bits/4 cells
  (7^4=2401 > 2^11=2048).
- CMY7 baked joint bank (p120 only, gen v1): children
  `(("r0550",0), ("r0625",677), ("r0625",677))` → active info
  2240+1883+1883 = 6006, transmitted 4096+3419+3419 = 10934 = 994 packs ×
  11 bits; user = 5974, symbol = 5973.
- CMY8 per-plane banks: one child `(rung, p)` per plane; at p120
  transmitted = 3976 = payload cells; r0550/r0547 → user 2088, symbol
  2087; r0700 → user 2728, symbol 2727.
- K stream algebra: user = k_bits − 32 − p; symbol = user − 1; transmitted
  slots T = 4096 − p.
- Envelope: `{sha256:32B}{len:u32 BE}{data}`; `OVERHEAD_BYTES = 36`.

### B. v2 grammar (parse + canonical mint)

1. `format-id = coding-id "@" TY "x" TX`; split on LAST `@`
   (`rpartition`). Tiles regex `^([0-9]+)x([0-9]+)$`.
2. `coding-id = pitch "-" family ["-" rungs] ["-p" sites] ["-v" gen]`,
   split on `-`, tokens consumed IN ORDER (misorder refuses, never
   re-sorts). Regexes: pitch class `^c[0-9]+$`, rational
   `^([0-9]+)i([0-9]+)$`, rungs `^r[0-9]{4}(?:x[0-9]{4})*$`, sites
   `^p([0-9]+)$`, gen `^v([0-9]+)$`.
3. Defaults: sites K→100, CMY7/CMY8→120; gen→1. Rung arity: K=1, CMY7=0
   (forbidden token), CMY8=3 (a single rung expands to a uniform triplet,
   C,M,Y order). Mixed spelling `r0700x0700x0550` → `("r0700","r0700",
   "r0550")`.
4. Canonical string = shortest: class name over rational, defaults
   omitted, uniform triplet contracted (`rung_token`: uniform → the rung;
   else `"r" + "x".join(digits)`). Parser normalizes; only canonical
   strings are ever stored/printed; canonical id IS the v2 seed payload.
   **SUPERSEDED by contract amendment A-1 (2026-08-30): the canonical
   string is the FULLY EXPLICIT spelling — reduced rational pitch, sites
   and generation always spelled, uniform triplet still contracted —
   because the shortest form read mutable tables and a sanctioned edit to
   them re-keyed printed sheets. The shortest form survives as
   `display_id`, shown but never stored or seeded. As built, this spec's
   §B.4 describes `display_id`, not `row_id`.**
5. Constructibility (refuse at parse door): every rung ∈ LADDER; gen must
   be 1; sites ≥ 100 (p<100 reserved, e026 line); CMY7 → sites == 120
   exactly; CMY8 → sites > 100 (dust required) AND the rung triplet must
   share one `k_bits` (width-classed pool; r0550/r0547 mix lawfully,
   r0700x0700x0550 refuses); per-rung `k_bits − 32 − sites ≥ 2` (metadata
   bit + at least one symbol bit); TY,TX ≥ 1;
   `pages * TY * TX ≤ 262144`.

### C. Fossil catalogue (v1) — COPY VERBATIM AS DATA

Use the src/holo FOURTEEN-entry table (`src/holo/format/fossils.py:92-149`),
NOT holo2's twelve: holo2's sunset ruling dropped the two cmy8-v0 rows,
and holo3 acceptance targets 3 and 4 ARE those sheets. Seeds are literal
byte strings, spelled out in the module, never derived by a helper.
Lookup: strip one `L:` prefix, then exact dict match; near-miss refusal
may list same-coding entries. NEVER parse a legacy id.

| spec_id | tiles | seed | notes |
|---|---|---|---|
| c3-r0550@2240x1536 | 35x24 | holo/v1/c3-r0550/2240x1536 | K r0550 c3 |
| c2-r0550@3328x2304 | 52x36 | holo/v1/c2-r0550/3328x2304 | K |
| c2-r0700@3328x2304 | 52x36 | holo/v1/c2-r0700/3328x2304 | K |
| c2-r0700@3392x2368 | 53x37 | holo/v1/c2-r0700/3392x2368 | e029 + e032-K target |
| c2-cmy7-p120-v0@3328x2304 | 52x36 | holo/v1/c2-cmy7-p120-v0/3328x2304 | target 6 |
| c3-cmy7-p120-v0@2240x1536 | 35x24 | holo/v1/c3-cmy7-p120-v0/2240x1536 | target 3 |
| c2-cmy8-p120-v0@3328x2304 | 52x36 | holo/v1/c2-cmy8-p120-v0/3328x2304 | target 4, UNPOOLED |
| c3-cmy8-p120-v0@2240x1536 | 35x24 | holo/v1/c3-cmy8-p120-v0/2240x1536 | UNPOOLED |
| c2-cmy8-p120-v1@3328x2304 | 52x36 | holo/v1/c2-cmy8-p120-v1/3328x2304 | pooled twin |
| c3-cmy8-p120-v1@2240x1536 | 35x24 | holo/v1/c3-cmy8-p120-v1/2240x1536 | pooled twin |
| c2-cmy8-p120-v1@3392x2368 | 53x37 | holo/v1/c2-cmy8-p120-v1/3392x2368 | e033 D/E |
| c4-r0550@1664x1152 | 26x18 | holo/v1/c4-r0550/1664x1152 | K c4 (pitch 1/150) |
| c2-cmy8-r0700-p120-x1@3392x2368 | 53x37 | holo/v1/c2-cmy8-r0700-p120-x1/3392x2368 | sheet I, target 7, pooled, rungs r0700^3 |
| c2-cmy8-r0850-p120-x1@3392x2368 | 53x37 | holo/v1/c2-cmy8-r0850-p120-x1/3392x2368 | sheet H, pooled, r0850^3 |

Per-coding frozen bundles (params the sheet was printed under): pitch
(c2=1/300 etc.), family, rungs, sites, pooled flag. Critical bundle facts:
- v1 CMY8 rows (`-v0`, `-v1`, `-x1`) all use rungs `("r0550","r0550",
  "r0547")` for -v0/-v1 (Y is r0547 — a DISTINCT code at the same
  k_bits), `("r0700",)*3` for r0700-x1, `("r0850",)*3` for r0850-x1.
- POOLING IS DATA, NOT FAMILY (P13): `-v0` rows are UNPOOLED (three
  independent per-stream fountains, domains 14/15 with per-stream esi);
  `-v1`/`-x1` rows and every v2 cmy8 row are POOLED (one fountain over
  `esi = counter*3 + stream_idx`, stream-exact quotas). Identical tile
  codec both ways. Deriving pooled-ness from the family reads e030/e032's
  sheets with the wrong outer code.
- The frozen codec-id/bank-id strings (`cmy8-presence-p120-v0`,
  `cmy7-pack7-p120-v0`, the `-x1` names) existed to replay persisted
  certificate identities. holo3 has no resume, so DROP them; keep the
  spec_id as the only label.
- tiles_yx is FROZEN on the entry, never divided out of cells (deriving
  from the record cancels the constant and asserts nothing).

### D. Resolver (total, two routes)

1. `ref.startswith("L:")` → catalogue lookup → FormatRow from the frozen
   bundle, `row_id` = the `L:`-prefixed ref, `seed` = the frozen bytes.
2. else → v2 parse → mint via family constructor, `row_id` = canonical
   `coding@TYxTX`, `seed = b"holo/v2/" + row_id.encode()`.
Resolving a resolved id is a fixed point. No bare-legacy route, no
FORMAT_ROWS catalogue, no discovery hypothesis set — holo3 is always told
its format.

### E. Family constructors (params → stream facts)

- K: 1 stream `("main", symbol_bits = k_bits−32−p−1, fountain_aux None →
  domains 7/8, aux=0)`; word states (W=0, K=1); n_dust = 0; fillers =
  p − 100 known-value label cells.
- CMY7: 1 stream `("main", 5973, aux 0 on domains 14/15)`; word states
  (W=0, CM=3); n_dust = 20; the baked bank above; unpooled.
- CMY8: 3 streams `[("C", s, 1), ("M", s, 2), ("Y", s, 3)]` in
  PLANE_ORDER, s = k_bits(rung)−32−p−1 per plane; word states (W=0,
  CM=3); n_dust = p − 100; pooled per the bundle/v2 rule above.

### F. The e029 sugar (`--coding` + `--printer`)

Only one live (printer, margin) pair matters: `hp-m281-ink` → margin
4.5 mm, media A4 (210.0, 297.0) mm. Derivation (v1 legacy field law,
`derive_field`, all on the 600-dpi engine grid):
1. Page dots per axis: `8 * floor(mm / 25.4 * 600 / 8 + 0.5)` →
   A4 = (4960, 7016) (x, y).
2. `margin_dots = ceil(margin_mm / 25.4 * 600)` (4.5 mm → 107; 6.0 mm →
   142; 4.0 mm → 95).
3. Per axis: `cells = ((page_dots − 2*margin_dots) // cell_dots) // 64 *
   64`. hp-m281-ink c2: y = (7016−214)//2//64*64 = 3392, x =
   (4960−214)//2//64*64 = 2368 → 53x37 tiles.
4. Identity = the v1 seed law on those cells → `holo/v1/c2-r0700/
   3392x2368`, which IS fossil row 4. Implement the sugar as: derive
   cells → spell the legacy spec id → resolve through the catalogue
   (refuse if absent). Alternatively a 3-entry alias table
   `(coding, printer) → L:` line; either way ≤ 20 lines. Margin table to
   keep as data: default/hp-m281/xerox-altalink-c8245 → 6.0 mm,
   hp-m281-ink → 4.5 mm (src/holo/devices/registry.py:46-119; everything
   else in that registry is documentation — drop).

Reference geometry table (machine-checked against derive_field; embed as
a comment-free test fixture in `_distill/verify/`, not in holo3/):
A4-6mm: c2→3328x2304 (52x36), c3→2240x1536 (35x24), c4→1664x1152 (26x18);
A4-4mm/4.5mm: c2→3392x2368 (53x37), c3→2240x1536 (= 6 mm);
A3-4mm: c2→4864x3392 (76x53).

### G. Tile addressing

Flat counter `c = page * (TY*TX) + ty*TX + tx`; inverse by divmod;
0 ≤ c < 2^18. Vertical neighbour = ±TX in counter space. Word message =
counter as 18 bits MSB-first + 5 zero pads (pad gate: any nonzero pad →
refuse, 2^-5).

### H. Pilot site lattice (all draws keyed by the site seed — named
`family_seed` at build time, renamed `sites_seed` by amendment A-1; the
bytes `holo/v1/sites/pN` are unchanged)

1. Quota edges `[int(i*64/10) for i in 0..10]` =
   `[0,6,12,19,25,32,38,44,51,57,64]`, spans `(6,6,7,6,7,6,6,7,6,7)`.
2. Word site q (= qi*10+qj, raster order; site_index = q):
   `dy = bounded_draw(family_seed, domain 4, u=2q, bound=span_y[qi])`,
   `dx = bounded_draw(family_seed, domain 4, u=2q+1, bound=span_x[qj])`;
   cell = `(edges[qi]+dy, edges[qj]+dx)`. bounded_draw law (8-bit
   rejection): blocks at `(domain, aux=0, major=0, u, v=retry)`; scan
   block bytes 0..15; first byte `< 256 − (256 % bound)` → `byte % bound`;
   else retry += 1 (cap 64 → error).
3. Filler/dust site k (16-bit rejection, unbiased since 65536 % 4096 == 0):
   block at `(family_seed, domain 5, aux=0, major=0, u=k, v=retry)`; scan
   byte pairs (0,1),(2,3)..(14,15) big-endian → `cell = word % 4096` →
   `(cell//64, cell%64)`; skip if already taken (word sites + earlier
   fillers); next retry if block exhausted; cap 64. Sequential in k —
   collision set grows in k order (order is format law).
4. Dust (colour) = the filler draw under the p120 family seed, then
   REORDERED by stable argsort of flat index `y*64+x` (canonical physical
   raster order). Payload cells = sorted complement of (word ∪ dust) =
   3976 cells at p120.
5. LDPC shorten set = sorted flat indices of ALL sites (word + filler).
6. Word values: site-local scramble = `bits(row_seed, domain 2, aux=3
   (PLANE_K), major=0, u=0..99, v=0)` — ONE 100-bit vector, identical for
   every tile (periodicity is load-bearing for cold acquisition). Printed
   word bits = `bch_encode(message(counter)) XOR scramble`. Colour
   rendering: bit 0 → state W(0), bit 1 → state CM(3) (multiply by 3).
7. Filler values (K rows with p>100): `bits(row_seed, domain 3, aux=plane,
   major=page, u=cell_y, v=cell_x)` at absolute cell addresses.
8. Dust values: source vector = `n_dust // len(cycle)` full cycles ++
   extras `cycle[(extras*c + j) % len(cycle)]` for `j < extras =
   n_dust % len(cycle)` (c = tile counter). At p120: CMY7 = 4 full
   cycles, 0 extras; CMY8 = 3 full + 2 extras `(2c)%6, (2c+1)%6`. Then
   permute: `perm = lexsort((arange(n_dust), keys64(row_seed, domain 9,
   aux=0, major=c, u=arange(n_dust), v=0)))`; printed dust state at
   raster-ordered dust site i = `base[perm][i]`. (keys64 = big-endian
   uint64 of AES block bytes 0..7; ordinal tie-break is format law.)

### I. Per-tile affine slot permutation

1. `T = n_slots = 4096 − n_sites` (3996 at p100, 3976 at p120).
2. Transmitted codeword positions, ascending: `[0, k_bits − n_sites) ++
   [k_bits, 4096)` — shortening consumes the INFO TAIL only; parity is
   always transmitted.
3. Draw `(a_t, b_t)` from `(row_seed, domain 6, aux=0, major=0,
   u=tile_counter, v=retry)`: read big-endian 16-bit words from byte
   pairs (0,1)..(14,15); admissible when `w < 65536 − (65536 % T)`, value
   `w % T`; `a_t` = first admissible value with `gcd(value, T) == 1`;
   `b_t` = the NEXT admissible value (unconditioned, never the same word
   that set a_t); retry increments v; cap 64.
4. Application: transmitted bit j lives at in-tile cell
   `nonsite_cells[(a_t*j + b_t) % T]`, nonsite_cells = sorted complement
   of the shorten set. (`cell_map`, src/holo/core/ldpc/tile.py:81-97.)

### J. Streamset (envelope → per-stream source rows; solved rows → payload)

1. Common K (all mappings): `K = ceil(len(wrapped)*8 / sum(S_i))`
   (canonical minimal for the payload: `ceil((36+len)*8 / sum(S_i))`).
2. Stream-major (K rows and unpooled -v0 colour): zero-pad the wrapped
   envelope to `K*sum(S_i)` bits; stream i gets the contiguous `K*S_i`-bit
   slice, split into K rows of S_i bits. Bit boundaries, never byte-rounded.
3. Pooled (-v1/-x1/v2 cmy8): same padded bit stream; one common width S
   (equal per-stream widths, structural); `k_meta = K` as above;
   `k_total = n_streams * k_meta`; source row j carries envelope bits
   `[j*S, (j+1)*S)` row-major. `esi = counter*n_streams + stream_idx`.
4. Verified stop (both shapes), three independent gates: envelope
   len/SHA-256; K must equal the canonical minimum for the decoded
   length; every encoded bit after the envelope through the exact bit
   capacity must be zero. Total or nothing — wrong SHA is fatal, never
   partial.

## 3. Copy-vs-rewrite table

COPY-AND-STRIP (bit-exact format law; strip docstrings/guards only, keep
every numeric expression verbatim):

| What | Source | Lines |
|---|---|---|
| fossil table + bundles (14 rows) | src/holo/format/fossils.py | 92-149 (data), 31-34 (family seeds) |
| word site construction | src/holo/format/pilots.py | 53-74 |
| filler/dust site draws | src/holo/format/pilots.py | 77-134 |
| payload cell indices / shorten set | src/holo/format/pilots.py | 113-154 |
| word value scramble + encode/decode word | src/holo/format/pilots.py | 159-266 |
| dust value law | src/holo/format/pilots.py | 206-245 |
| bounded_draws (8-bit rejection) | holo2/src/holo2/format/keystream.py | 250-272 |
| slot_perm_params (16-bit rejection) | holo2/src/holo2/format/keystream.py | 275-317 |
| _item_permutation / color_dust_permutation | src/holo/core/keystream.py | 266-287 |
| transmitted_positions + cell_map | src/holo/core/ldpc/tile.py | 60-97 |
| envelope wrap/unwrap/source_symbol_count | src/holo/format/envelope.py | 26-93 |
| streamset pack/reassemble/unwrap (both shapes) | holo2/src/holo2/format/streamset.py | 123-482 (drop the isinstance walls, keep _write_bits/_nonzero_bits bit math verbatim) |
| derive_field arithmetic (page_dots_xy, margin, quantize, slack split) | src/holo/format/layout.py | 36-130 |
| pitch classes + grammar regexes + defaults | holo2/src/holo2/format/lattice.py | 140-160 |
| tile counter/address | src/holo/format/layout.py | 133-159 |
| CMY7 bank children + dust cycles + mapper dims | src/holo/format/profiles.py | 192-263; holo2/src/holo2/format/families.py | 70-98 |
| CMYState / STATE_NAMES / PLANE_ORDER | src/holo/core/channel.py | 33-50 |

REWRITE LEAN (shape is incidental; behavior spec'd above):
- Grammar parse/canonical mint: holo2/src/holo2/format/lattice.py:200-359
  as reference; drop ParsedFormat's re-derivation invariant, keep
  normalize-then-store-canonical.
- Resolver: holo2/src/holo2/format/resolve.py:98-168 → ~25 lines, two
  routes, no ResolvedRef type needed (return the FormatRow directly).
- FormatRow construction: holo2/src/holo2/format/registry_rows.py +
  families.py → one constructor per family, ~80 lines total, no
  cross-check methods, no TileFormat/FormatRowSpec dual-view split.
- e029 sugar: src/holo/devices/profiles.py:75-89 collapsed to the margin
  table + derive_field + catalogue resolve.

## 4. Measured-channel invariants that must survive

- d=27 addressing + pad gate: a wrong identity/geometry hypothesis
  descrambles every word to coin flips and refuses at the word gate —
  this IS the identity check; no other format verification is needed at
  decode time.
- Family seed frozen across the namespace split: equal-density sheets
  share the measured site layout, so the E022/E023 placement lineage
  (and every measured placement constant downstream) stays valid.
- Fossil ids byte-matched, never parsed: a legacy string re-parsed under
  new rules could normalize into a DIFFERENT seed (silent whole-sheet fork).
- Pitch is identity, dots are emission: px/cell = pitch_in x declared
  dpi, exact Fraction — never fit pitch from the page (page-derived pitch
  estimators fit channel wander as scale: 5.92 vs true 6.00).
- One physical format, two keystreams: a printed v1 sheet's v2 twin
  (`c2-k-r0700@53x37`) seeds under holo/v2/ — decoding a printed sheet
  requires the `L:` identity, always.
- Pooling not derivable from family in v1 (P13): -v0 sheets on paper are
  unpooled CMY8; wrong outer code = no close.
- Dispatch on Family enum only: identity-compare dispatch handed a
  freshly built -x1 colour row the K reference field (no dust), silently
  — the measured c4-row branch bug.
- Discovery/channel tiers never gate the resolver: e031/e032 measured
  that channel rankings do not even ORDER receiver outcomes.

## 5. What to DROP

- Both trees' import-time `_self_check` two-witness reconciliations, the
  recipe/record dual spelling, seed-golden second copies (goldens live in
  `_distill/verify/` scripts, not holo3/).
- `FormatRowSpec._agrees_with_its_codec`, `tile_format_for`'s six-way
  cross-verify, `format_row_for`'s build-and-byte-verify, ParsedFormat's
  canonicality re-derivation — one construction path makes them vacuous.
- The refusal catalogue (G1-G14/A1-A7 rows), `_legacy_hint` near-miss
  listings, error-taxonomy discipline, `colour_codec_refusal` (colour is
  CORE in holo3, the fatal colour door does not exist).
- `FORMAT_ROWS` / `DEFAULT_DISCOVERY_ROW_IDS` / `registered_format_rows`
  (no cold format discovery), `CODINGS` legacy name table, holo2's
  `LEGACY_REFS`, empty-coding_id fixture sentinel.
- Paper profiles / SheetLayout / `fit` / `--dpi` / emission integrality
  gate / manifest fields — generation-side; holo3 is decode-only. Keep
  only the margin table + derive_field for the sugar.
- Devices registry prose (capability strings, scanner records, notes);
  keep 4 printer_id → margin_mm pairs as one dict.
- Frozen codec-id/bank-id strings (`cmy8-presence-*`, `cmy7-pack7-*`,
  `-x1` bank names) — they existed for persisted-state identity replay;
  no resume, no journal, no schema, no policy ids in holo3.
- `L:L:` double-strip compat, bare-legacy compat route, off-600 "pending"
  refusals, `cell_dots` everywhere (dots never reach a receive path),
  `VALID_CELL_DOTS`, pooled/None fountain_aux revalidation in
  CloseStreamProfile, streamset's isinstance/TypeError walls,
  `lru_cache` (construct once at startup instead — caches are shared
  mutable state under free-threading).
- holo2's TileFormat/Coding/CodingParams/ParsedFormat/ResolvedRef type
  zoo → one FormatRow + one StreamFact.

## 6. Data structures (holo3/data.py or holo3/format/)

```
StreamFact(frozen): stream_id: str ("main"|"C"|"M"|"Y"),
  plane: int (K=3; C=0,M=1,Y=2 — the keystream aux for domains 1/2/3),
  fountain_aux: int (0 main / 1 C / 2 M / 3 Y; K uses domains 7/8 aux 0,
  colour uses 14/15), rung_children: tuple[tuple[str,int],...]
  ((rung, shortened) pairs), user_bits: int, symbol_bits: int.

FormatRow(frozen): row_id: str (canonical, L:-marked when legacy),
  display_id: str (amendment A-1), seed: bytes,
  sites_seed: bytes (named family_seed at build time, A-1),
  family: Family,
  tiles_yx: tuple[int,int], pitch_in: Fraction,
  (n_pages removed by PAGE-DOMAIN 2026-09-01)
  n_sites: int, n_dust: int, dust_base_cycle: tuple[int,...],
  word_states: tuple[int,int], streams: tuple[StreamFact,...],
  pooled_fountain: bool, bits_per_mapper_unit: int,
  cells_per_mapper_unit: int.
  Derived properties: cells_yx, tiles_per_page, payload_cells,
  n_transmitted_slots, tile_counter/tile_address.

SiteGeometry(frozen): word_cells_yx (100,2) i64, extra_cells_yx (F,2)
  i64 (fillers for K, dust raster-ordered for colour), shorten_flat
  (n_sites,) i64 sorted, payload_flat (payload_cells,) i64 sorted,
  all numpy arrays with writeable=False. Built once per row at startup
  (pure function of the site seed, `sites_seed`, x n_sites); shared
  read-only by every worker — never rebuilt in jobs.
```

Certificates carry `source` (plugin tag) per the charter; format
contributes `row_id` + stream_id + tile counter to certificate identity —
nothing format-side is hashed beyond those strings.

Thread-safety notes: every object above is immutable after startup.
`slot_perm_params`, `word_values`, `dust_state_values` are pure functions
of (seed, counter) — call them inside jobs freely; do NOT memoize them in
a shared dict (recompute or precompute per-page arrays in the snapshot).
The AES encryptor object is created per call (cheap) — never share a
cipher context across threads.

## 7. Pitfalls / incidents

- e012.3 phantom payload: a retyped draw (missing `dtype=`) forked the
  numpy stream — never reimplement a seeded draw from prose; copy the
  draw code and verify byte-exact against src/holo in `_distill/verify/`.
- c4-row `-x1` dust bug: identity-compare dispatch gave a colour row the
  K reference field silently. Family enum only.
- e033 §033.5: off-catalog colour resume died at "stream 'M' is not
  declared" because a row id meant something only while a table held it.
  holo3 keeps the resolver total (grammar + catalogue) even without
  resume — the CLI must reconstruct any acceptance identity from its
  string alone.
- holo2's catalogue is MISSING the two cmy8-v0 rows (sunset ruling G8);
  copying holo2's fossils.py verbatim fails acceptance targets 3/4. Copy
  src/holo's.
- Y stream of -v0/-v1 cmy8 rows is r0547, not r0550 — same k_bits,
  different parity matrix; swapping them decodes Y to garbage while C/M
  stay green.
- tiles_yx frozen on the fossil, never `cells // 64` (constant cancels;
  a changed TILE_CELLS would move both sides).
- The two spellings "c2-r0700" (legacy, no family token) vs "c2-k-r0700"
  (v2) are different namespaces with different seeds; error messages
  should point a bare-legacy typist at the `L:` form.
- Misdeclared identity (e033 misdeclared-dpi incident): the word gate
  refuses cleanly — do not add pre-checks that second-guess the declared
  format against channel measurements.
- `Fraction(str(float(dpi)))` — the decimal the operator declared, not
  the binary float's exact value; changing this shifts px/cell in the
  15th digit and desyncs long-field poses.
- Filler rejection is order-dependent (taken-set grows in k): vectorize
  only within the exact sequential law.
- streamset `_write_bits` OR-composes across byte boundaries at bit
  offsets — the shift/carry split is easy to break; copy it.

## 8. Open questions for the contract author

1. Where does `FormatRow` live — `data.py` (all frozen dataclasses in one
   place per the charter) or `format/`? Recommend `format/` with data.py
   re-exporting nothing (format is upstream of every plugin anyway).
2. The e029 sugar: derive_field route (30 copied lines, generalizes) or a
   3-entry `(coding, printer) → L:` alias dict (5 lines, closed)? Both
   pass acceptance 2; the alias dict is leaner but silently wrong if a
   new probe geometry ever appears.
3. Does diag want a human label for the codec (the dropped codec_id
   strings)? If yes, reuse `row_id` — do not resurrect the frozen name
   strings.
4. Should `SiteGeometry` also precompute per-tile `(a_t, b_t)` for all
   tiles of the page at startup (53x37 = 1961 counters, one vectorized
   call — the holo2 slot_perm_params is already batch-shaped), or leave
   it to the tiles plugin per job? Recommend precompute: it is
   page-global, read-only, and removes the only rejection-loop from the
   hot path.
5. v2 grammar scope: acceptance needs only the `L:` route plus the sugar;
   is the full v2 parse (rationals, mixed triplets) required for the sim
   capture (target 1), or will the sim sheet be emitted at a fossil
   identity? Keeping the full grammar costs ~120 lines; recommend keep.
6. Pages: all acceptance sheets are single-page. Is multi-page (`--pages`)
   in scope at all, or can n_pages=1 be assumed and the page term dropped
   from counters (keeping the algebra but not the CLI knob)?
