# HOLO-DESIGN — the v2 library (`src/holo`) and printed format v1

Version 0.25, 2026-09-04 — **column-group pool for uneven CMY8 rung
triplets** (§13.36; design, rulings and build record:
docs/CMY8-COLUMN-GROUPS.md; F8 amended). v0.24 (2026-08-13) appended the
pooled-fountain CMY8 -v1 rows (§13.35). Body
otherwise the leaned v0.23 current-truth-once text (semantics identical
to v0.21, 2026-07-28). Every body section states the current rule exactly
once; the per-version history (v0.1 pre-build lock through v0.21) lives as
the decision ledger in §13, one entry per amendment with its document-version
tag, with full amendment text in git history and docs/REASONING-LOG.md.
Status: **working pre-freeze contract**. The user explicitly ruled
on 2026-07-21 that this is not freeze time; printed-format identity remains
v1 while its not-yet-frozen contract is corrected. The design dialogue of
2026-07-19 is recorded in
docs/REASONING-LOG.md, "Session 2026-07-19 (holo v2 design)"). This document is normative for everything under
`src/holo`. Deviations require an explicit amendment here, never silent
divergence. The measured channel record (CLAUDE.md experiment bullets) and
`experiments/026-pilot-density-subsample/DESIGN-NOTES.md` (the encoding-
geometry converged bundle) are the evidence base; where this document fixes a
choice the record left open, the rationale is stated inline.

---

## 1. Scope and relationship to paperholo

- `src/holo` is a **fresh start**: v2 library plus production executables.
  Its production generator/receiver/runtime/CLI graph imports nothing from
  `paperholo`, and `paperholo` imports nothing from it. Qualification-only
  differential oracles may import historical code but never enter production.
  Code moves into production only by **ingestion** — copy, adapt, re-test
  against new golden vectors — never by reference. No compatibility layers,
  shims, or production backreferences.
- holo reads and writes **format v1 only**. `paperholo` remains the reader
  for printed layout_version 2-4 sheets forever. Physical v3/v4 archives are
  not holo's problem.
- Functionality, in build order:
  1. **Generation** — payload sheets in format v1 (e018b's role).
  2. **Read-back** — the e021→e023c receiver chain re-architected for
     format v1.
  3. **Characterization, standalone current tool** — printer/scanner
     discovery and calibration in `holo.characterize`. It is independent of
     E025/Track-2 code and has no import path to generation or read-back.
     Promotion of measured results into the device registry remains a
     separate reviewed action.

## 2. Ground rules (binding on all holo code)

- **G1 — file size.** No source file exceeds ~1000 lines. Split into
  sub-modules at natural seams; the package map (§8) budgets for this.
- **G2 — no source-code identity in state.** Persistent state never
  contains hashes or fingerprints of source-code files, module bytes, entry
  points, or runtime library versions, and loading state never polices code
  identity. Editing source must never invalidate state. What state MAY
  contain: a state **schema version** (hand-bumped integer; loader refuses
  incompatible schemas cleanly), **format row ids**, content-identified
  **semantic receiver policy**, an exact **page-hypothesis axis**, and
  **content hashes of artifacts** (scan files, payloads, emitted PS) — those
  identify interpretation or data, not code. Journalling/provenance ceremony
  beyond this belongs to experiments and artifacts, not the library.
- **G3 — documented decisions, narrow APIs, no dead code.** Every
  non-obvious constant carries its provenance. Public API per module is
  small and typed. Measured-history device facts live in the registry as
  DATA, not as code paths. No backward-compatibility branches.
- **G4 — determinism.** All format-defining randomness flows from the
  format row's default public seed through the v1 keystream (§5). No other
  RNG touches anything printed. Ground truth is derived from the generator
  module or extracted from renders — never retyped draws (012.3 incident
  rule).
- **G5 — measurement discipline carried.** Simulation before toner; one
  variable per hardware run; numbers carry footing labels (supervised vs
  blind, genie vs legal geometry); rate/profile decisions on multi-sheet
  minima; pre-registered envelopes for qualification. Confidence from the
  2026 experiment record carries — v1 freezes on it and re-qualifies with
  code (user decision, 2026-07-19).
- **G6 — efficiency is a requirement, not a cleanup.** The receiver is
  designed around the spatial work model of §9.4 (coarse-first, frontier
  ordering, memoization, incremental masks, streaming rasters, lean state).

**Validation-boundary rule (user ruling 2026-07-30, v0.23):** validation
lives at TRUST BOUNDARIES — persistence load, capture/CLI ingest, barrier
retention, the observer boundary — plus the measured-doctrine guards
(never-sum-same-capture, one-owner, retry-no-tunnelling, conflict-fatal).
Interior call-to-call verification is the type system's and the test
suite's job and is judged as READING burden, not only runtime; hot-loop
re-checks of static properties are pruned only after a harness
measurement. Durable-record ``__post_init__`` walls stay — they are the
mechanized cross-session discipline. CRC/syndrome/SHA/goldens are the
product, never in pruning scope.

## 3. Format v1 — decision ledger

| # | Decision | Value | Rationale anchor |
|---|----------|-------|------------------|
| F1 | Tile grid | one 64×64-cell grid; pilots colocated in every payload tile; no partial tiles | e026 converged bundle |
| F2 | Word system | **C1 — BCH address words kept** | addendum 6, confirmed 2026-07-19 |
| F3 | Word code | BCH(127,50,t=13)→(100,23), d≥27; message = 18-bit counter + 5 known-zero pads | v3 code, measured; pads all zero (§4.3) |
| F4 | Pilot sites | K uses exact-100 `p100`; provisional color uses exact-120 `p120` = the 100-site word plus 20 deterministic dust sites | §4.2, §13.23 |
| F5 | Inner FEC | n=4096 e-IRA mother code, rate ladder {r0550..r0850}, uniform count-shortening, CRC-32 per tile | FEC-DESIGN, ldpc.py provenance |
| F6 | Metadata channel | 1 LDPC user bit per tile; M = version(1)+K(18)+reserved(5) = 24 bits; counter-addressed dense GF(2) equation from the specified degree-24 LFSR; recover at rank 24 and trust after ≥48 distinct equations. Pooled -v1 rows (§13.35): one DISTINCT equation per stream at index counter·n_streams + stream_idx (n=1 rows bit-identical at index = counter); the K field carries k_meta (k_total = n·k_meta) | §6, §13.16, §13.35 |
| F7 | Payload envelope | `{sha256:32B}{len:4B BE}{data}{zero-pad}` inside the fountain stream (§13.12) | §7.1 |
| F8 | Fountain | **fountain-v2** (§7.2, §13.10): per-page exact block quotas + keystream shuffle (NOT ESI mod B), BLOCK_K_MAX 16384, reserve(B)=16+⌈log₂B⌉/block — multistream general form reserve = 16 + bit_length(B·n_streams − 1) per block (union bound over all B·n_streams independent solves; CMY8 n_streams = 3; `capacity.rank_reserve_for`); two-tier promise (whole-page loss deterministic, fragments q+ε). Pooled -v1 colour rows (§13.35) run ONE fountain over esi = counter·n_streams + stream_idx with stream-exact per-(block,page,stream) quotas on domains 7/8: plane loss joins page loss as a THIRD deterministic tier, DIAL-CONDITIONAL — the planner enforces it and reports it guaranteed at q ≤ (n−1)/n, drops it from sizing and reports it absent above (§13.35, 2026-08-14) — reserve = one solve per block. **Column groups (§13.36, 2026-09-04):** a cmy8 triplet whose rungs differ shares the widest plane's symbol width as Z column groups (rational partition, `column_groups`); a narrower plane's tile carries fewer consecutive groups, rotating over the key-order fill; the close solves per (block, group); tiers weighted by groups carried, the heaviest plane binding tier 3; reserve = 16 + bit_length(B·Z − 1); uniform triplets are the one-group case, bit-identical | 2026-07-19 review occupancy finding; §13.35; §13.36 |
| F9 | Keystream | AES-128-CTR as a pure function of address; KDF = SHA-256(seed‖label)[:16]; no numpy/Philox/BLAKE2b in format-defining paths | §5 |
| F10 | Format signaling | implicit — trial descramble against registry rows; no version fields in words; page geometry folded into value-scramble labels (pilot values AND payload) | §4.5, §5.3 |
| F11 | Page geometry | per-(printer, media, cell) registry rows: largest 64-multiple field inside measured margins, slack split across the 4 borders | user decision; §4.1 |
| F12 | Counter width | 18 bits + 5 pads (262,144 tiles; ≈140 c2 / ≈312 c3 A4 pages per volume; cold gate 2⁻⁵) | user decision |
| F13 | Instance identity | none in-band; fixed default public seed per format row; cross-sheet mixing is *detected* (conflicting certificates are fatal), not prevented | §6.3 |
| F14 | Color | six provisional catalog-only rows: CMY7/CMY8 × c2/c3 per-stream (-v0) plus the pooled-fountain CMY8 -v1 pair (§13.35); all absent from default discovery until exact paper/null qualification | COLOR-INTEGRATION-DESIGN, §13.23, §13.35 |
| F15 | Emission | K keeps one whole-page imagemask; color emits one composite DeviceCMYK object with zero K; PostScript at 600 dpi, no fiducials/headers (R3) | Layer-0 freeze, §13.23 |
| F16 | Slot mapping | per-tile permutation of code-slot→cell mapping (affine, tile-keyed) to break colocation's tile-invariant shorten pattern | addendum 7 item 7; §4.5 |

Status note: REASONING-LOG addendum 7 (external review, same day) renames
the e026 bundle **leading-candidate** and lists an 8-item pre-freeze
qualification battery. The 2026-07-19 "freeze now" wording is superseded by
the user's explicit 2026-07-21 ruling in §13.16: v1 is still pre-freeze. The
8 items remain v1 qualification content (§11). Technical/synthetic portions
are exercised; physical/null/real-sheet portions remain open.

What v1 deliberately fixes relative to v3: the 60/64 dual lattice and all of
its addressing machinery; fountain-inert edge tiles (2.3–2.6% tax) and
degenerate tiles (eliminated by construction); seed-dependent S; the
PERIOD/BLOCK divisibility bug; the out-of-band sidecar (self-describing
sheets); the sequential keystream and its consumption-semantics hazard
class; the tiles_x page-width acquisition hole (closed by F10).

## 4. Format v1 — geometry, pilots, words

### 4.1 Page geometry

For a format row (printer/media class, cell size c ∈ {c2, c3}):

- printable rectangle = media size minus the registry's measured per-edge
  **payload-safe margins** (maximize; provenance required — canary-measured
  payload-safe reach, not ImagingBBox, not solid-ink reach);
- field = largest (64·ty) × (64·tx) cell rectangle inside it;
- slack per axis is split across the two borders as evenly as the dot grid
  allows (odd remainder goes to bottom/right).

Until a device's payload-safe rectangle is qualified (E025 Phase C debt),
rows use the existing 6.0 mm margin policy — the base 64-quantum fields
below already fit it (resulting borders c3 6.26/7.46 mm, c2 7.61/7.46 mm;
addendum 7 item 4). Any extent growth beyond that is gated on E025-style
payload-safe edge canaries (which have not certified even the current c2
edges), and a zero-cost 3–3.5 mm margin-ladder strip rides the first v1
print of each device.

Example rows (A4, 6.0 mm policy — illustrative until Phase C):

| row | field cells | tiles/page | tile pitch | pages/volume (2^18) |
|-----|------------|-----------|-----------|---------------------|
| a4-c2 | 3328 × 2304 | 52×36 = 1,872 | 5.42 mm | 140 |
| a4-c3 | 2240 × 1536 | 35×24 = 840 | 8.13 mm | 312 |

### 4.2 Pilot sites

- Exactly **100 sites per 64×64 tile** (floor density 100/4096 = 2.44%),
  positions drawn once per format family from the default public seed via a
  quota construction (10×10 virtual sub-cells with seeded jitter; exact
  rejection rules spelled out in the keystream spec, §5.4). The same
  pattern repeats in **every** tile — periodicity is load-bearing for
  cold-start acquisition (site-local scrambling; PILOTS-DESIGN §6.3). The
  square-quota trick of p60b6 does not survive at 64; the new construction
  is part of the v1 spec and gets its own golden vectors AND a normative
  construction battery — e026's thinning results do not qualify any
  particular exact-100 pattern (addendum 7 item 6; the v1 pilot-stripe bug
  is the precedent).
- Site positions are geometry-independent (tile-local) and shared across
  all geometry rows of one cell size: one lattice acquisition serves every
  row; rows differ in value scrambles only.
- **Filler sites** (dust-precedent known-value label sites, same
  construction, own label) raise density above the floor per profile:
  density = (100+F)/4096. Each filler site shortens the tile code like a
  pilot site. Requirements on any site set: exact count (uniform S),
  quota-class spatial uniformity (warp observability, calibration
  coverage), seeded non-repeating values. (v0.2 build: fillers are
  collision-free uniform 16-bit-rejection draws; quota-izing them is open
  until a density rung above the floor is actually qualified; registry
  rows launch at F = 0.)
- Provisional color rows use the separate `p120` family: the same
  100-position BCH word role plus 20 collision-free deterministic
  known-state dust positions. CMY7 dust covers the five non-W/non-CM legal
  states four times each; CMY8 uses three of each missing state plus two
  counter-balanced extras. The binary E021/E022 reference projects word
  `W/CM` to `0/1` and projects dust to one iff at least two ink components
  are present. Only word sites enter BCH decoding. Exact multistate word and
  dust labels become color registration/detector furniture after promotion.
- Per-tile user capacity at rate r with F filler sites:
  `S = k_bits(r) − 32 − 100 − F − 1` (the −1 is the metadata bit, §6).
  At r0550/F=0: **S = 2107** bits/tile, identical for every tile — no
  min-over-tiles, no seed dependence.

### 4.3 Address words

- Message = 18-bit flat counter `c = page·tiles_per_page + ty·tiles_x + tx`
  + **5 zero pads**, code = BCH(127,50,t=13)→(100,23), d≥27. All pads are
  known-zero under the BCH encoding: every printed pilot bit is predictable
  a priori from (row, seed) alone. (The recorded pad-bit descriptor idea is
  REJECTED — measured: flipping any single pad bit changes 39–40 of the
  100 transmitted word bits (parity spread, verified for all 5 pads;
  addendum 7 item 2) — a data-dependent message bit would destroy ~40% of
  the tile's cold-predictable correlation field. 2026-07-19.)
- Word dividends retained (all load-bearing, e023 design record): O(1)
  cold-start self-addressing; big-piece page-set enumeration; d≥27 as the
  placement decoy floor and cross-format arbiter; certifiable partial reads
  (2e+f≤26, erasure fill at known positions only); the 2⁻⁵ pad gate;
  pencil-and-paper bootstrap of a tile.
- Word values are scrambled site-locally with a periodic (per-tile-position)
  keystream so Stage A can remove the scramble under any phase hypothesis
  (§6.3 mechanism carried).

### 4.4 Slot mapping (colocation hazard + mitigation)

Colocation makes the shorten pattern tile-invariant: without countermeasure
the SAME LDPC variable nodes sit at the same in-tile positions on every
tile, so a page-wide banding/edge gradient loads identical code structure
everywhere — count-only capacity is not count-only BLER (addendum 7
item 7). v1 therefore permutes the mapping from TRANSMITTED code
positions to non-site cells **per tile**: transmitted bit j (position
order = info head then parity; shortening always consumes the info tail,
so parity is never punctured) lives at `nonsite_cells[(a_t·j + b_t) mod
T]`, T = 4096 − n_sites. (a_t, b_t) come from the keystream's unbiased
16-bit rejection scan with gcd(a_t, T) = 1 (T is not a power of two —
the v0.1 "a_t odd" form applied only to power-of-two moduli). Two-line
spec, random access preserved, zero printed cost. Effectiveness is part
of the v1 qualification battery (correlated-raster replay + real-sheet
yield, §11).

### 4.5 Implicit format signaling

No version/geometry fields anywhere in the printed bits. A receiver
hypothesis is a complete registry row; the row's value-scramble labels
(which include the page geometry, §5.3) either yield decodable words or
coin flips. Wrong cell size fails pitch/lattice ID; wrong row fails the
word gate (2⁻⁵ pads + BCH); wrong payload interpretation fails CRC. The
value-layer pairwise distance floor (d≥27 class) is a format invariant —
any future value-layer change must preserve it.

## 5. Keystream v1 (format-defining)

### 5.1 Construction

All format-defining bit streams are pure functions of address:

```
key          = SHA-256(b"holo/v1|" || seed_bytes)[0:16]
block(addr)  = AES-128-Encrypt(key, counter128(addr))
bit(addr)    = block(addr)[0] >> 7         # MSB of byte 0
```

One byte-order doctrine (format-wide, §13.12): every multi-byte integer
field is big-endian, every bit string is MSB-first — bit j of a byte
sequence is `(byte[j // 8] >> (7 - j % 8)) & 1`. This covers the counter
fields, the envelope length, the metadata word, source-symbol packing,
raster packing, and the two bulk keystream draws (fountain coefficients
MSB-first per block; block-assignment sort keys big-endian). No
LSB-first form exists anywhere on the format surface.

There is no separate label layer (v0.2 simplification): ONE key per seed;
stream separation lives in the counter's domain byte, and family-vs-row
separation lives in the seed naming convention (§4.5-style
`holo/v1/row/<row_id>` vs `holo/v1/sites/<family_id>`).

The frozen registry seeds are public, so the default profile is whitening,
not encryption. A high-entropy secret seed would make the address streams
computationally private, but that alone is not a complete confidentiality
mode: v1 has no per-volume nonce, keyed authentication, key identifier, or
secret manifest/state contract, and reuse at the same addresses repeats the
stream. A future private profile must derive row/family subkeys from a master
secret plus public row identity and a unique volume nonce, while retaining an
explicit bootstrap path. It must not serialize the master secret.

- One AES block per drawn value. The ×128 bit waste is accepted for spec
  minimalism: there is **no packing order, no consumption state, no
  rejection sampling, no dtype** anywhere in the common path. (A full c2
  page ≈ 7.3 M cells ≈ milliseconds through an OpenSSL-backed AES; the
  pure-Python reference does it in seconds, acceptable for verification.)
- `counter128(addr)` is a structured 128-bit block, fixed layout:
  `[domain:8][aux:8][major:24][u:32][v:32][zero:24]`, big-endian fields;
  per-domain (aux, major, u, v) meanings (cell y,x; site index; fountain
  block/row/column; etc.) are the domain table in
  `holo/core/keystream.py` and its printable spec `keystream_spec.py`.
- Bounded draws (only the site/filler constructions need them) take bytes
  from the block with an explicit two-line rejection rule written in the
  spec — ours, not a library's.
- Primitives: **AES-128 (FIPS-197)** and **SHA-256 (FIPS 180-4)** — two
  universal, textbook-eternal standards. No BLAKE2b, no Philox, no numpy
  RNG in any format-defining path. Production uses the `cryptography`
  wheel; a ~200-line pure-Python AES + the label registry is the normative
  reference-as-code with golden vectors (the keystream_ref pattern,
  re-minted for v1).

### 5.2 Why (recorded rationale)

The v3 chain's effective spec was numpy's draw-layer internals (Lemire
rejection, cross-call carry, per-call uint8 buffers) — pinned by
spec-as-code, but the 012.3 stream-fork incident is that hazard class live,
and streams were sequential (fragments had to regenerate page-prefix
streams). Function-of-address removes the hazard class structurally, gives
fragments random access to exactly their own cells, and reduces the
BOOTSTRAP "printable keystream spec" liability to one paragraph plus public
standards.

### 5.3 Domain registry (initial)

| domain | keyed by | periodic? |
|--------|----------|-----------|
| 1 payload scramble | row seed (carries **page geometry**), plane, page, cell y/x | no — absolute cell address |
| 2 pilot word values | row seed (carries **page geometry**), plane, site index | yes — periodic per tile position (site-local scrambling) |
| 3 filler values | row seed, plane, page, cell y/x | no — absolute cell address |
| 4 pilot site construction | family seed — **geometry-free**, shared across cell sizes (v0.2: family = density rung only, e.g. `p100`) | n/a (one pattern per family, repeated every tile) |
| 5 filler site construction | family seed | n/a |
| 6 slot-perm params | row seed, tile counter | per tile |
| 7 fountain rows | row seed, block, row, column | no |
| 8 fountain block assignment | row seed, page, page-local symbol index (u = local_tile·n_streams + stream_idx; = the local tile index for single-stream rows); bytes 0..7 as one 64-bit BE sort key | no |
| 9 color dust order | row seed, tile counter | per tile |
| 10 CMY7 interleave | row seed, tile counter | per tile |
| 11 CMY7 dither | row seed, tile counter, transmitted-bit ordinal | per tile |
| 12 color payload-cell order | row seed, tile counter | per tile |
| 13 CMY8 dither | row seed, stream auxiliary, tile counter, cell ordinal | per tile/stream |
| 14 color fountain rows | row seed, stream auxiliary, block, row, column | no |
| 15 color block assignment | row seed, stream auxiliary, page, local tile index | no |

Plane convention: aux = 'CMYK'.index(plane); the K plane (= 3) is the
established scalar-plane convention. Color stream auxiliaries are frozen
separately as `main=0`, `C=1`, `M=2`, and `Y=3`; row seeds distinguish
CMY7/CMY8 and c2/c3.

Geometry in the *value* streams (pilot AND payload, via the row seed)
closes the tiles_x page-width hole at the word gate: a wrong-geometry
hypothesis coin-flips every word and refuses at Stage A instead of dying
late in LDPC. Geometry-free *site* seeds keep lattice acquisition shared
across all rows of a density family.

### 5.4 Golden vectors

Golden set: keystream vectors for every used domain (including production
versus pure-reference equality and a frozen key stream for domain 8), the
canonical fountain assignment digest (including stable sort tie-breaking),
the 100-site pattern per family, word codewords for known counters, and one
full-page compose sha per row. Once the user freezes the format, these pin the
PRINTED FORMAT; before that point an intentional in-place re-freeze requires a
recorded amendment such as §13.16. Goldens never gate state loading (G2).

## 6. Metadata channel (the fountain sidechannel)

### 6.1 Transport

Each tile donates **one LDPC user bit** (the first info bit before the
symbol bits): cost 1/2108 ≈ 0.05% of capacity. The bit is LDPC-protected
and arrives CRC-certified with its tile. Tile with counter `c` carries
the addressed equation
`bit(c) = parity(coefficient(c) & word_mask(M))`. Exactly one metadata bit
is carried per tile.

### 6.2 Content

`M = [version:1][K:18][reserved-zero:5]` — 24 bits.

- **version**: payload-interpretation version (fountain-v2 = 0). This is
  the one thing implicit signaling cannot carry (pilot acquisition never
  touches payload interpretation); 1 bit now, the 5 reserved bits are its
  headroom.
- **K**: source-symbol count; fits 18 bits by construction (K ≤ addressable
  tiles = 2^18). K determines the minimum page count
  `ceil(K / tiles_per_page)`; repair symbols extend beyond K, rateless. In a
  -v0 per-stream multistream row, `N-K` is the repair-symbol count in each
  logical stream; no physical color tile has one global source/repair
  classification. In a pooled -v1 row (§13.35) the K field carries
  k_meta, the one fountain has k_total = n_streams·k_meta source symbols,
  and repair counts are pool-global, never per stream.
- **Address rows:** `coefficient(c)` is state c of the maximal-length
  degree-24 LFSR with primitive polynomial
  `x^24 + x^4 + x^3 + x + 1` (`0x100001b`), initial state 1, recurrence
  `s' = ((s << 1) & 0xffffff) XOR (0x1b if s & 0x800000 else 0)`.
  Integer coefficient bit i multiplies M[i]. Every 24 consecutive counters
  have rank 24. Arbitrary address sets recover iff their rows reach rank 24;
  the format does **not** promise every arbitrary set of 24 tiles is a basis.
- **Trust rule:** solve all distinct `(counter, certified_bit)` equations over
  GF(2), require rank 24 and at least 48 distinct counters, then validate the
  reserved zeros and K. The 48 floor supplies at least 24 surplus consistency
  equations in the normal full-rank case. Hundreds of returned tiles are the
  expected operating regime. Equal duplicate observations are no-ops;
  opposite duplicates or any algebraically inconsistent certified system are
  integrity-fatal, never voted away.
- No separate CRC on M; no nonce (user decision). Each equation arrives behind
  its tile CRC, so the residual error class is CRC false acceptance (~2⁻³²).

`K` supplies only a lower bound on printed extent. `M` does not encode
`n_pages` or the generation repair fraction, and neither the highest observed
counter nor the highest decoded page identifies a terminal page. The optional
generation manifest records `n_pages` for bookkeeping, but it is not currently
in-band receiver authority. Exact receiver page-domain semantics are in
`RECEIVE-DESIGN.md` §5.3.

### 6.3 Instance identity

Fixed public seeds mean two same-profile sheets have identical pilots. If
two sheets with different payloads are mixed in one decode state, their
certified tiles conflict at identical addresses — a **detected, fatal**
condition (certificate bit-conflict), not silent corruption. Two prints of
the same payload are identical sheets; mixing is harmless. Hence: no
in-band nonce; the never-combine rule becomes an error message instead of
a doctrine.

## 7. Payload interpretation

### 7.1 Envelope

The fountain source stream is `{sha256:32B}{len:4B BE}{data}` zero-padded
to K·S bits (§13.12: the length is an unsigned 32-bit big-endian integer —
the metadata K:18 cap makes any volume beyond ~2²⁷ bytes unrepresentable,
so u32 already carries ~60× headroom; the generator refuses payloads that
do not fit the field). Bit order (format-axis): stream bytes unpack
MSB-first per byte into one flat bit string, sliced row-major — source
symbol k = bits [k·S, (k+1)·S); the decoder inverts with MSB-first packing
before the envelope parse. The generator wraps; the decoder unwraps. `K` is
canonical and minimal: `K = ceil(8·(36+len)/S)`, and every bit after the
envelope through K·S is zero. Closure refuses a SHA-valid envelope whose K is
noncanonical or whose padding is nonzero. Verified stop is fully in-band:
fountain rank complete → solve → parse envelope and verify SHA-256 over
`data[0:len]` → canonical-K/padding gate → done. Rank/symbol counts are never
a stop condition; a wrong SHA is fatal, not partial success. An optional
sidecar manifest may still be emitted for convenience; nothing requires it.

### 7.2 Fountain — fountain-v2 (block assignment revised, §13.10)

Systematic dense random-linear over GF(2); ALL tiles bear symbols (no
inert edge tiles). The **block assignment** is the load-bearing part, and
it is NOT `ESI mod B`: that aliased against the page raster, so exact-q
spatial crops starved blocks and the "any q of tiles recovers all"
promise was false for every multi-block volume (measured: a half-page
column crop at q=0.5 starved 16 of 32 blocks). fountain-v2:

- **BLOCK_K_MAX = 16384** — the GE feasibility knee (~1 min/block
  decode); B ≤ ⌈K/16384⌉, so even a full 140-page c2 volume is ≤ 12
  blocks. No code family avoids blocking at full-print K (dense GE is
  K³; RFC 6330 caps a source block at K=56,403), so occupancy is ours to
  own regardless.
- **Per-page exact block quotas + keystream shuffle.** Each page carries
  an exact quota `T//B` (±1, rotating by page) of every block's tiles,
  placed within the page by a keystream-derived shuffle
  (DOMAIN_BLOCK_ASSIGN 64-bit sort keys). Consequences: losing any set of
  **whole pages** down to q removes proportional amounts of every block —
  a **deterministic** recovery tier; sub-page fragments concentrate
  **hypergeometrically** with no periodic aliasing — a **probabilistic**
  tier, q + ε. Added redundancy pages carry every block's quota, so extra
  pages provably help **all** blocks, never only finished ones (the false
  v1 claim, now true and tested).
- **Rank reserve scales with B**: `reserve(B) = 16 + ⌈log₂ B⌉` per block,
  so the union bound over B blocks keeps the **volume** failure ≈ 2⁻¹⁶
  (a flat 16/block gave only ≈ B·2⁻¹⁶ ≈ 2⁻¹⁰ at B=48). Multistream
  general form (live in `capacity.rank_reserve_for`, the keyword is
  `solves_per_block`): `reserve = 16 +
  bit_length(B·n_streams − 1)` per block — the union bound runs over all
  `B·n_streams` independent solves (CMY8's three streams each solve their
  own B blocks); at `n_streams = 1` this is exactly `16 + ⌈log₂ B⌉`.
- Source data maps to blocks **contiguously** (block b owns source rows
  [offset_b, offset_b+K_b)); repair coefficients ride the packed fountain
  keystream (128 coefficients/AES block, DOMAIN_FOUNTAIN_ROW).

RFC 6330 RaptorQ remains a payload-interpretation swap signaled by the
metadata version field — no page change. Certified-conflict rule
(§6.3): two different values at one ESI raise FountainIntegrityError.
Capacity tables are **promise-grade** and enforce both bounds. For T tiles per
page, P emitted pages, B blocks, r = reserve(B), and L = ceil(qP):

`K + B·r <= floor(q·P·T)` and
`ceil(K/B) + r <= L·floor(T/B)`.

The first is global fragment capacity. The second is the worst quota of every
block under any retained set of L whole pages. Both are required.

### 7.3 Capacity (a4-c2 example, r0550, F=0)

Per page: 1,872 tiles × 2,107 bits = 3.944 Mbit ≈ 493 kB of symbol space.
For a fixed page count, the generator enumerates every feasible block-count
interval and takes the largest K satisfying both §7.2 inequalities; feasibility
is not monotone when B changes, so a binary search over K is invalid. All
budget arithmetic is exact rational (`Fraction(str(q))`); dirty-float dials
are refused (§13 item 9). Payload
bytes are `floor(K·2107/8) − 36` (36 = envelope). For a requested payload, the
planner begins at the global lower bound and adds whole pages until the shared
two-bound predicate succeeds. Exact tables come from `holo capacity` and are
part of the generator qualification tests. Planner regression pins (§13.16):
the real off-by-one-page cases `(K,T,P,q)=(99083,1872,106,.5)` and
`(157041,1872,120,.7)` (107 and 121 pages required), plus the non-monotone
B-boundary at `(T,P,q)=(840,307,.7)`.

## 8. Registries

Three distinct concepts (do not conflate; keep each minimal — "don't
overbuild the spine"):

- **Device registry** (`holo/devices/`): printers and scanners as measured
  capability records, seeded from the 2026 record and extended by
  characterization runs. Printer: engine facts (native dpi, emission
  paths, media sizes), per-edge payload-safe margins **with provenance and
  footing labels**, viable cell sizes with BER class, color status, MIC
  status, day-variance notes. Scanner: dpi modes, px/cell footing ladder,
  mode constraints (never-mix modes, JPEG warnings), platen size. Every
  number carries its footing (supervised-metrology vs blind-receiver).
  The registry ships the LOCKED conservative `default` printer (600 dpi,
  6 mm margins, A4, b/w only) plus structured per-printer `usable_dpi` /
  margins-with-footing / `bw` / `color` capability fields (§13 item 8a).
- **Payload profiles** (`holo/devices/profiles.py`): the user taxonomy —
  **rocksolid / resilient / high-volume / max** — keyed per
  (printer, scanner-class), each resolving to (cell size, LDPC rung,
  fountain K/N, pilot density F, grain promise). Profiles are name-keyed
  (coding + source fraction + evidence + priced-on context) and resolve
  against any printer's geometry at plan time. B/W values get made up
  from measured system performance and marked provisional until the
  matched-payload rung control prints (018b.5); only r0550 is
  physically established today. "Measured" grades mean measured-on-v3-
  legacy; every v1 manifest is stamped provisional until a v1 print
  qualifies (§13 item 10).
- **Format registry** (`holo/format/descriptor.py` + `registry.py`): two
  axes, never conflated (§13 item 8a) — **Coding** rows (`c3-r0550`,
  `c2-r0550`, `c2-r0700`: cell size, rung, pilot density; printer-
  independent per-tile facts; the `-fN` filler suffix returns only when a
  density rung above the 2.44% floor is qualified) × printer-derived
  **geometry** (margins from the device registry) = FormatSpec, with row
  seed `holo/v1/<coding>/<cells_y>x<cells_x>` (geometry stays in the
  seed — the wrong-geometry word-gate mechanism, §5.3 — now derived).
  A format row carries (row id, cell size, page geometry, density rung,
  plane set, rate, default public seed, keystream labels); color adds the
  four provisional `-p120-v0` catalog rows (F14). Rows are append-only; a
  printed sheet's row is immutable forever.

## 9. Library architecture

### 9.1 Package map (target; every file well under 1000 lines)

```
src/holo/
  core/
    keystream.py      AES-CTR keystream, label registry, KDF
    keystream_spec.py pure-Python AES reference + golden-vector checks
    bch.py            (127,50)->(100,23) word code (ingest from paperholo)
    ldpc/
      construct.py    e-IRA mother codes loaded from FROZEN DATA files
                      (data/*.json: pi + per-column rows/shifts + restart
                      as TRANSPARENT integer arrays; structural
                      validation at load; format pinned by external
                      goldens in the test file; regenerate/verify via
                      util/regen_holo_ldpc_data.py — no RNG, no Philox
                      anywhere in holo)
      decode.py       min-sum + sum-product retry, erasures
      tile.py         64-grid shorten masks, per-tile framing, CRC-32
    channel.py        canonical CMY state/presence projection
    color_tile.py     CMY7 compound pack7 and CMY8 stream tile leaves
    fountain.py       fountain-v2 core + ESI + two-tier page capacity
  format/
    descriptor.py     FormatRow dataclass
    registry.py       append-only row registry
    layout.py         page-fill derivation, slack rule, tile atlas
    pilots.py         exact-100 construction, filler sites, word encode
                      plus provisional p120 color word/dust furniture
    metadata.py       24-bit word + addressed LFSR placement/GF(2) recovery
    envelope.py       {sha256}{len}{data} wrap/unwrap + verified stop
    streamset.py      CMY8 common-K stream-major split/reassembly
  devices/
    registry.py       printer/scanner capability records (data-driven)
    profiles.py       payload profile resolution
  gen/
    plan.py           options explorer / capacity / profile resolution
    compose.py        cell field assembly (payload+pilots+filler+metadata)
    ps.py             K imagemask or color composite DeviceCMYK emission
    manifest.py       optional sidecar + GT emission
  receive/
    scan.py           authenticated native ingest; mmap + bounded raw-luma crops
    survey.py         physically denominated E021 support survey
    placement/        E022 geometry, reference, search, model, policy/default data
    place.py          E022 orchestration, chaining, complete-domain routing
    words.py          BCH Stage-A/readout and attempt-budget arithmetic
    detect.py         historical PAVA/context detector implementation
    color_detect.py   equal-prior QDA plus tie-pooled class-balanced PAVA
    color_registration.py  shared-pose C/M/Y residual fit
    color_projection.py    certified known-component reconstruction
    color_payload.py  aligned RGB sampling, registration and color evidence
    color_attempts.py CMY7 bank / CMY8 stream BP attempt leaf
    evidence*.py      immutable cell evidence + physical-capture provenance
    payload*.py       E023b ownership, calibration and evidence formation
    _payload_*.py     private sampling / region-context / refined-reuse leaves
    tiles.py          pure LDPC attempts, CRC certificates, retry profiles
    certified_*.py    certificate-labelled pose cascade/refinement
    scale_space.py    direct-from-native area views and coordinate transforms
    cascade.py        E023c coarse-to-fine schedule and NeedMap barriers
    observer.py       detached events plus provisional status/warning
    runtime.py        typed ingestion/scheduling/commit harness
    session*.py       authenticated append-only state, replay and validation
    records.py        durable/transient record adapters
    fountain_close.py metadata rank, per-block fountain close, SHA stop
    production.py     Track-3 composition root + survey/address stages
    production_payload.py K payload stage driver
    production_close.py   gated fountain-close stage
    production_color.py provisional color payload orchestration
    diag/             downstream JSONL/HTML/SVG observers
    qualification/    source-local, stage-by-stage qualification programs
  characterize/      standalone discovery/calibration plans, emitter,
                     bounded raster/geometry, held-out analyzer, summaries
  cli.py              `holo` entry: generate | capacity | decode | registry
                      | discover (characterization routing only)
```

### 9.2 State model (lean — G2)

Decode starts with a receiver-wide discovery state. It freezes the append-only
format-row candidate set and one cross-row hypothesis envelope before reading
the first raster, retains authenticated capture facts and one native E021
`c` decision per capture, and owns isolated exact-row branches. A voted c may exclude an
incompatible cell family for that capture, but never selects a rate or
geometry row. A row is recognized only after it produces a CRC-certified
tile; a second recognized row is an integrity-fatal format conflict. Candidate
trials and every nested exact-row level barrier are committed through the same
atomic discovery root, so trial order and restart cannot choose the format.
The native survey verifies that a path did not change before its first commit;
every row branch is then pinned to that same SHA. Resume authenticates the
stored source facts and reuses the retained c decision without numerically
rerunning the native discovery survey. Candidate exclusion is derived from
that decision and the immutable row; no prune ledger is persisted.
Receiver-wide CRC exposure is the sum of `decoder_invoked` attempt records
over all branches, including losing rows.

Each exact-row branch retains only the causal state needed for replay:
`{format_row_id, receiver_policy_id, page_hypotheses, captures with complete
scale plans (including v0.33 mop-up entries) and level artifact prefixes,
survey regions, poses, typed BCH conflict quarantine records, pose
proposals, losers, parked mop-up windows, compact evidence blocks,
tile attempts, certificates, divergence, close}`. The state-envelope schema
version binds this shape. Capture records bind the authenticated original-
acquisition SHA-256, true DPI, canonical real-numeric dtype, shape, and
channels. Certificates store the packed user bits and their minting
provenance; the address counter, bit length, and certified metadata bit are
derived from the active format and packed bits.

Load fully replays typed references and conflicts. Once an exact row is known,
format-bound validation also reconstructs scale policy, page/counter law,
payload-site legality, BP policy and cost bounds, and certificate identity
and exactly reproduces the recorded close from the certified frontier before a
resume can return. Public save with default validation and every public load
perform this registered-row validation; a synchronized runtime barrier may
skip the quadratic full-state pass only after its delta has been incrementally
validated. `run_receive` separately refuses a semantic policy or exact
page-hypothesis mismatch. No source-code/module fingerprints. Atomic writes
(temp+fsync+replace), duplicate-capture no-op, resumable. Raw native rasters and
scale views remain regenerable from authenticated captures and are not stored
in state.

### 9.3 Evidence doctrine

- Bounded-LLR invariant: raw detector scores never cross an API boundary.
  CMY7 evidence is CALIBRATED, THEN BOUNDED (color-uplift 2026-08-10;
  normative detail RECEIVE-DESIGN §6.2a): a scalar-temperature + 6-offset
  head fitted on held-out region scores
  (`cmy7cal-temp7-heldout-subsplit-satfloor30`) maps each cell's six
  W-relative QDA scores first, and the historical uncalibrated path
  survives only as the head's registered refusal fallback. The L∞ bound
  applies LAST either way: scores `r` map to `r/max(1, ||r||_infinity/20)`
  before durable float32 evidence.
  This one positive factor preserves all seven-state orderings and signs
  relative to W=0 while bounding every per-acquisition component to
  `[-20,+20]`; componentwise saturation is forbidden. A legal `N`-source
  same-lane union may sum to `20*N` and is not bounded again. The bound
  policy is identified by `cmy7linf20`. CMY8 uses the corrected tie-pooled,
  class-balanced component PAVA in §13.26, corrected since color-uplift by
  the multi-state context matrix and — in supplemental u-a4b lanes only —
  KnownField-conditioned marginals over certified siblings (RECEIVE-DESIGN
  §6.2a); K evidence remains unchanged.
- Physical-evidence invariant: one admitted source is one original scanner
  acquisition identified solely by its authenticated source SHA-256; internal
  diagnostic `capture_id` fields are aliases for that SHA, not an operator
  identity. External resizes, decimations, crops, rotations, or other derived
  rasters are unsupported. Holo constructs deterministic scale views
  internally; they retain the source identity, stay in separate lanes, and
  never sum. Distinct physical acquisitions may sum their already bounded
  calibrated LLRs only within the same lane.
- Staged merge: per-scan one-owner, certified-tile union first, cross-scan
  LLR sum only for stragglers.
- Calibrate-or-refuse; search/validation parity split; eroded-core
  emission; one-way word trust; straddle audit by binomial impurity.
- Hard fragment-support floors are **route-specific and derived from the
  complete declared attempt domain**, not a blanket constant (addendum 7 item
  5). For each disjoint search and held-out validation parity, Track 3 uses
  `max(30, ceil(log2(H)/(1-h2(p_max))) + margin)`. The 30-site term is the
  retained executable E022 minimum; the second term is e026's necessary
  identifiability bound, not a false-accept tail proof. At the current
  provisional `p_max=0.08` and zero margin, one local neighborhood remains 30,
  a row-known one-page cold search is 41 (C3) or 42 (C2), and the complete
  three-row discovery envelope is 57 on **each** parity. Exact current domains,
  route definitions, limitations, and qualification duties are normative in
  `RECEIVE-DESIGN.md` §5.3.
- A word decode fixes page/address only for its word-seeded local verification;
  it does not shrink the durable cold page domain. Explicit legal pages may
  narrow the request only when declared before the attempt and frozen in the
  session contract. A highest-seen page or counter is a lower bound on extent,
  not an upper bound, and cannot lower a current or prior attempt's floor.
  Seen-page scheduling may generate a proposal, but authoritative cold
  acceptance still needs the complete legal rival set and full-domain floor
  unless independent authority first narrows the legal domain
  (`RECEIVE-DESIGN.md` §5.3).
- Known-position BCH contradictions use the persisted promotion firewall in
  `RECEIVE-DESIGN.md` v0.7 §5.4. After the final selected per-site word vote,
  every contributing E022 placement is retained for audit but loses
  continuation hints, payload sampling/LLRs, evidence blocks, attempts,
  certificates, and certified refinement. Clean placements continue. NeedMap
  remains certificate-derived; later fresh placement may recover, while old
  quarantined evidence is never auto-rehabilitated. This selective rule is an
  intentional departure from historical session abort, not a claim of exact
  reference behavior. Refusals remain harmless in both.
- Certificates are the sole cross-lane bit authority. Bounded accepted/losing
  pose proposals may cross as non-authoritative hints and must pass on current
  pixels; LLRs never cross correlated lanes. Conflicting certified bits are
  fatal; CRC attempts are ledgered; verified stop is §7.1.

### 9.4 Spatial work model (G6 — measured efficiency requirements)

- **Coarse-first is the schedule**: the E023c result (a 2-ppc lane alone
  verified whole volumes) makes the scale cascade the default work order,
  not an option.
- Easy-frontier ordering: place/decode dense, easy regions first;
  correlation as component-seeder for the rest.
- Memoized placement scoring (94–96% of probes were duplicates in E022).
- Incremental, site-granular pending masks (no full-bitmap rebuilds).
- Residual-need skipping at the decoder boundary (~40% CRC-call savings at
  zero output change).
- Streaming / memory-mapped rasters; never load a 2.3 GB TIFF. Every scale
  lane is area-resampled directly from native—never recursively or per-window;
  numerical stages use bounded crops and subpixel reads through local poses.
- Payload sampling is genuinely per-window: K uses one bounded E022 window
  crop/filter, and color uses a bounded native crop, local scale probe, and
  per-anchor raw/corrected footprints with aperture halo. Region-wide
  detector and residual fits consume the resulting small samples; they do not
  require a union bounding-box raster or a crop cache spanning many windows.
- Bounded vector kernels replace per-cell Python setup where the same order
  and authority are explicit: E022 row alignment, window-local 3×3
  neighborhoods, stable owner selection, provenance replay checks, and the
  CMY7 exact candidate marginals. Their working arrays are scoped to the
  current window, page frontier, or tile—not raster pixels or session history.
- Lean states (§9.2); no per-append quadratic validation.

### 9.5 Known-bug annotations (noted, not blind-fixed — components are
re-architected)

| legacy site | class | v2 disposition |
|---|---|---|
| pilotsearch.py:60 min_support gates offset not fragment | gate semantics | subsumed by the mandatory fragment-support floor (§9.3) |
| feedback.py:720 broken x-split | arithmetic | E024 loop not ported (§10.3) |
| cascade.py:185 sorted-tie crash | scheduler | scheduler rewritten (§9.4) |
| analyze_e025 missing bundle_id check | validation | current `holo.characterize` binds compact HCAL-R1 identity, regenerated canonical page digest, and optional manifest independently |
| E023c 16-bit→uint8 saturation | ingest | receive/scan.py handles 16-bit natively |
| E021 featureless-platen region minting | detector | flat/null refusal and historical behavior regression-checked; real-v1 physical audit remains §11 |

## 10. Functionality tracks

### 10.1 Generation (build first)

`holo generate`: payload file + (printer, scanner-class or profile) → resolved
format row + rung + K/N → envelope → fountain → per-tile LDPC (+ metadata
bit) → compose (pilots + filler + payload) → PS + optional manifest + GT.
`holo capacity` explores the option space (cell × rung × K/N × density)
with promise-grade numbers and evidence grades per option. Emission gate:
Ghostscript render == GT dot-exact, zero ink elsewhere (e018b test
pattern, re-minted). Output: content-addressed volume DIRECTORIES, staged
and atomically renamed; existing directories are refused (no
overwrite/mixing). Profile override is forbidden (custom = explicit
`--coding`); the manifest carries profile / evidence / printer /
provisional flag, and each manifest page records the SHA-256 of the
canonical C-order, big-bitorder packed GT bytes plus the packed shape and
bit order — convenience metadata only, never decode input (§13 items 10,
16).

### 10.2 Read-back (built second; current)

The e021→e023c chain re-architected for v1 colocation: survey → per-window
pose placement (same-level chain → lower hint → Stage-A word seed → cold
correlation) → detector/calibration → tile certification → cascade lanes → addressed
metadata solve → fountain → verified stop. The colocated grid collapses the
pilot-tile/LDPC-tile bookkeeping (one atlas, one counter). The E024
feedback loop is NOT ported (measured ≈0 yield post-cascade); the state
retains what a future bounded seam/piecewise-pose pass would need
(dependency-complete evidence, loser-hypothesis ledger) without any loop
machinery.

### 10.3 Characterization (standalone current instrument)

`./confetti.py discover` routes to the isolated characterization instrument,
which owns discovery emission, calibration emission, blind scan analysis,
and conservative multi-copy aggregation. The default output is a separate
one-page B/W/color pair with no resolution request.
Optional requested resolutions are distinct evidence footings. Candidate
identity retains the B/W-or-color page path, authored x/y DPI, x/y cell size,
alphabet/planes, symbol shape, emission path, and request.

The analyzer starts from chiral corners and two separated compact HCAL-R1
strips. Each strip pairs the minimal static facts needed to regenerate the
current page with guarded live pre/post-request device readback. The latter is
provenance, while scanned geometry, rulers, fields, and edges are physical
authority. Local phase fit, phase certification, detector training, and
untouched reporting use four disjoint populations.

The B/W discovery page includes matched/frontier grids, multilevel K, shape,
and rectangular-cell controls. Color includes pure planes, CM4, triple-free
CMY7, CMY8, one-hot K/C/M/Y, and direct-versus-overprint emission paths.
Both retain the useful E025 geometry/transport, full grid-ruler,
scanner-adequacy, edge, tone, and morphology diagnostics. The analyzer reports
per-grid smallest usable cells, equal-physical-pitch controls, absolute scale,
physical and payload-safe edges, and color registration/selectivity/screening.
It supplies no algorithm to `holo.gen` or `holo.receive`, contains no payload
compatibility coupon, and cannot promote a production profile automatically.
Its full contract is `CHARACTERIZE-DESIGN.md`.

## 11. Qualification plan

- Golden vectors: keystream domains, site pattern, word codewords, compose
  sha per row (format identity only — G2).
- Unit + property tests per module; clean-channel coded round-trip
  byte-exact (gen → sim → receive); sim runs scope-declared (known c2
  white-closure gap).
- Receiver qualification re-uses the e023 pattern: pre-registered gate
  pairs (zero-wrong AND yield-on-frozen-denominator) on synthetic states
  first, real scans second.
- The addendum-7 pre-freeze list remains the v1 qualification content. Current
  technical/synthetic batteries cover construction vectors, pad/word
  predictability, support arithmetic, receiver stage regressions, state,
  diagnostics, and compact round trips. Still outstanding are the physical
  v1 null/yield gate, support margin and BER freeze, correlated-raster plus
  real-sheet slot-permutation yield, payload-safe edge canaries before extent
  growth, and a thinned null battery before any density change.
- Hardware: first v1 print carries the margin-ladder strip; the
  matched-payload rung control (r0550/r0625/r0700) qualifies non-floor
  rungs; profiles graduate from provisional on multi-sheet minima.

## 12. Deferred / out of scope (recorded so they stay decisions)

- Color default promotion (F14): CMY7/CMY8 software rows are present, but
  exact modulation/cell-size/device/print-path/scanner footings, p120
  placement/null behavior, coded paper yield, and aggregate discovery cost
  must qualify before any row enters default discovery. Alternative color
  features, context models, partial CMY7 packs, and richer registration
  remain measured optimizations, not pre-built policy (§13.23).
- RaptorQ swap (metadata version field is its signal), mixed-rate volumes,
  sub-symbol packing.
- Erasure-aware Stage-A search (FA budget re-derivation owed first).
- Feedback loop (E024 class), seam-aware piecewise pose.
- Thinned-density freeze below/above defaults pending the thinned null
  battery + second-sheet replication (registered risks, ride first prints).

## 13. Decision ledger — v0.2–v0.21 amendments (compressed 2026-07-30)

One entry per amendment. Each keeps its item number (external references
cite "§13.N"), its document-version tag and date, the decision, and any
constant, measured number, retraction, or rejected alternative not restated
in the body. Where an amendment superseded body text, the body above states
the final form. Full amendment text lives in git history and
docs/REASONING-LOG.md. Supersession chains: item 6's metadata placement →
item 16; items 13–15 (Track-2 / first Track-3) → item 17, code deleted in
item 20; item 17's availability boundary → item 18; item 19's
archive/storage clauses → item 22 and its frame cadence → item 32; item
23's calibration detail and terminal color wipe → item 26; v0.18's
verified-continuation reading of `--complete` → item 31.

1. **LDPC mother codes frozen as data** (v0.2; final form §9.1): six
   rungs extracted once from paperholo's construction, verified against
   its golden edge SHAs; no Philox or construction RNG in holo; the
   printable spec of H = the data files + the 10-line expansion rule in
   construct.py.
2. **Slot permutation over transmitted positions** (v0.2; final form
   §4.4 — T non-power-of-two, unbiased 16-bit gcd rejection scan,
   shortening on the info tail, parity never punctured).
3. **No label layer in the keystream** (v0.2; final form §5.1/§5.3): one
   AES key per seed; domain byte + seed naming replace the v0.1 label
   table.
4. **Site family shared across cell sizes** (v0.2; final form §5.3):
   tile-local, cell-size-free; family id = density rung (`p100`).
5. **Filler-site construction** (v0.2; final form §4.2): collision-free
   uniform 16-bit-rejection draws; quota-izing open; rows launch at
   F = 0.
6. **Metadata word** (v0.2): [version:1][K:18][reserved:5]; K = 2^18 not
   representable (K < 2^18; the rank reserve makes K = N impossible
   anyway). The v0.2 `counter mod 24` placement is SUPERSEDED by item
   16's counter-addressed LFSR channel; §6.2 is the current form.
7. **Build status** (v0.2, 2026-07-19): Track 1 (gen) BUILT — src/holo
   core/format/devices/gen/cli; suite tests/holo green incl. FIPS-197
   anchors, frozen keystream/site goldens, byte-exact clean-channel
   round trip (gen → words → metadata → slot-permuted LDPC → fountain →
   envelope, 30% tile loss), wrong-geometry word-gate refusal, and the
   Ghostscript emission gate.
8a. **Registry reshape + identity fork** (v0.2, user review, same day;
   final form §8): the old `a4-c2-r0550-f0` rows conflated CODING
   (printer-independent per-tile facts) with GEOMETRY (a printer fact);
   split into Coding × printer-derived geometry = FormatSpec, seed
   `holo/v1/<coding>/<cells_y>x<cells_x>`; LOCKED `default` printer;
   name-keyed profiles. CLI: `gen`→`generate`, `--row`→`--coding`,
   plain-language help, "S" jargon → payload-bits-per-tile. Since
   NOTHING was printed this was a FREE pre-print identity fork — all six
   golden vectors (keystream ×3, compose ×3) re-frozen under the new
   seeds; after the first physical print such a fork is forbidden.
9. **First adversarial review round** (v0.2; 4 lenses, 13 agents): 5
   confirmed majors fixed same-day — (a) keystream domain/plane table on
   BOTH spec surfaces (keystream.py docstring + keystream_spec.py
   constants, drift-pinned by test); (b) payload source-stream bit order
   documented (emit + §7.1); (c) REAL BUG: float floor(q·N) loses whole
   symbols at exact rational boundaries (measured floor(0.35·187200) →
   65519), crashing plan_volume — all budget arithmetic now exact via
   Fraction(str(q)), dirty-float dials refused, boundary sweep test;
   (d) multi-page round trip added (source symbols spanning the page
   boundary, metadata votes across pages); (e) c2 rows pinned — compose
   goldens for a4-c2-r0550/r0700 + full byte-exact c2-r0700 round trip.
   4 findings refuted on verification. Suite 110.

10. **§13.10 fountain-v2 + fix batch** (v0.2, second external review,
    2026-07-19; final form §7.2). P0 CONFIRMED (numbers reproduced
    exactly against the code): fountain-v1's `block = ESI mod B` aliased
    against the page raster, so exact-q spatial crops starved blocks —
    the multi-block "any q of tiles" promise was FALSE (all PRINTED
    volumes to date were single-block and unaffected). Rebuilt as
    fountain-v2; crop battery (whole-page loss deterministic, column
    strip + random subset occupancy) tested at max volume, both c2 and
    c3; format-axis change, free pre-print (goldens re-frozen). Fix
    batch, final forms §6.2/§8/§9.1/§10.1: (a) content-addressed volume
    directories (`with_suffix` bug gone); (b) `decode_metadata` treats
    ANY certified-copy disagreement as integrity failure, not a
    majority; (c) profile override forbidden + manifest provenance; (d)
    Coding validates payload>0 + duplicate ids; LDPC goldens moved to
    the TEST file over canonical `<i4` bytes (npz self-hash ignored —
    structural validation only, endian-safe); (e) keystream striped
    (peak RSS ~150 MB vs the review's 619 MB), fountain repair packed
    128-coeff/block. Profile "measured" grades mean measured-on-v3-
    legacy; every v1 manifest stamped provisional until a v1 print
    qualifies. Suite 120.

11. **LDPC provenance closed** (v0.2, 2026-07-19, user challenge "can we
    regenerate these?"): demonstrated FIRST that paperholo's live seeded
    construction reproduces all six golden H matrices (every rung MATCH
    at restart 0; its ldpc.py docstring stays the normative record incl.
    the measured falsification history of the textbook variants); the
    six data files converted from opaque npz to TRANSPARENT pretty-JSON
    block descriptions (readable, diffable, 8–17 KB — literally
    printable format constants, settling the deep-time argument for
    published codes); bridge committed as util/regen_holo_ldpc_data.py
    (`--check` proves the committed files match a fresh regeneration);
    provenance pointers in construct.py. Published matrices re-examined
    and REJECTED: nothing published exists at n=4096 with our ladder;
    5G NR lifting imports base graphs + rate matching; the whole
    measured record lives on THESE codes — a swap = format fork + full
    requalification for zero measured gain.

12. **§13.12 Endianness harmonization + envelope shrink** (v0.2,
    2026-07-19, user review "8-byte length field — silly"; final forms
    §5.1/§7.1). (a) Envelope length 8B LE → 4B BE — the metadata K:18
    field caps a volume at 262,143 source symbols (~69 MB), so a u64
    length had 37 structurally-zero bits and misstated the format's
    scale to a from-scratch decoder; u32 keeps ~60× headroom; `wrap()`
    refuses overflow (checked before buffering); OVERHEAD_BYTES 40 → 36.
    (b) ONE BYTE-ORDER DOCTRINE format-wide: `bit(addr)` moved LSB → MSB
    of block byte 0 and DOMAIN_FOUNTAIN_ROW packed coefficients
    LSB-first → MSB-first, eliminating the last two LSB-first islands;
    MSB-first coincides with numpy's default bitorder, so a
    reimplementation that forgets the flag is right by default; the GE
    core's internal `<u8` packing is explicitly NOT format surface.
    (c) Goldens re-frozen through the live modules (payload-256,
    pilot-values-100, three compose-page SHAs changed; slot-perm-16 +
    the p100 site pattern verified UNMOVED — byte-level draws, the
    built-in cross-check that only bit extraction flipped);
    spec==production re-verified on the flipped forms. (d) Freeze-point
    ruling (user): the format freezes when the user DECLARES it frozen —
    first print does not implicitly freeze; pre-declaration re-freezes
    remain logged identity forks like this one.

**Historical architecture notice.** Items 13–15 preserve the decisions and
measurements of the original Track-2 and first Track-3 phases. Their
shared-kernel/promotion plan and early receiver framing are superseded by
item 17; the Track-2 code was deleted 2026-07-23 (item 20). They are not
current dependency or qualification claims.

13. **§13.13 Track-2 build: charsheet-1 + supervised analyzer** (v0.2,
    2026-07-19, user go; HISTORICAL — code deleted, item 20). NOT
    format-axis: char sheets are instruments; a sheet change is a new
    sheet version, never a coding fork (e025 pages stayed valid for
    their captures; e025's measured lessons cross as doctrine, its
    51-field surface does not). Sheet elements (K-only, per-printer
    geometry, frozen 1:1 imagemask path): (a) 3×3 position-stratified
    c2+c3 keystream-PRND grid (~26 mm; position variance = the measured
    dominant axis); (b) coupon strips = 6 real format tiles per coding
    (c2-r0550, c2-r0700, c3-r0550) composed by the PRODUCTION compose
    path (virtual page-0 counters, zero symbols, k=1) — code-path
    confirmation, not tight BLER; (c) 4-edge canary gap ladder {3.5,
    4.25, 5.0, 5.75} mm + 12 mm same-edge references, c2 stress + c3
    robust arms, 2 replicates, 6×6 mm patches (e025 lesson: payload-safe
    ≠ ink reach; Phase-G lesson: replication + robust arm so the
    rectangle can always resolve); (d) solid ticks 2.0–6.0 mm; (e) 4
    recorded paper witnesses; (f) 4 corner L-marks + a 24-dot-cell ID
    row (orientation from whole-page coarse correlation over 4
    rotations). EXCLUDED with reasons: morphology/resolution probes
    (engine discovery — msel/e025's job), tone/density ramps (solid
    decoupled from the cell channel, 005), machine strips w/ PJL
    readback (print provenance = log discipline), phase rails
    (supervised per-window correlation needs none), color (F14).
    Fields rode DOMAIN_PAYLOAD under instrument seed b"holo/v1/char1"
    (major = element index); coupons rode their coding's REAL row seed.
    Analyzer lessons that carry: 48-cell windows + per-8-row BAND
    y-refinement (128-cell windows were built first and read 3× the
    genie BER against the measured stepped-warp sim; step pitch
    ~4.7 mm); train on EVEN-parity cells, certify on ODD (fallbacks
    counted — strict-superset rule); one box prefilter ~0.7 pitch +
    bilinear cell-centre reads (e022 radiometrics); detector =
    per-window EMPIRICAL MIN-ERROR threshold on train parity
    (midpoint-of-class-means was built first and measured
    CATASTROPHICALLY wrong on the skewed developed channel: 9.8% vs
    0.04% on the zero-warp sim c3 field — edge gain drags the white
    tail under the ink mode); ALL headline stats on validation parity
    only; coupons decode through the real word+LDPC+CRC path at fixed
    |LLR|=5; supervised = an upper bound on the channel, never a
    blind-receiver claim (e025 doctrine); qualification by a simulator
    truth harness (paperholo channel simulator in TESTS ONLY). Its
    first pre-registered canary rule (pass on the Wilson-95 lower bound
    vs 2× reference upper + 1 pp) was SUPERSEDED as anti-conservative —
    the operative rule is item 14 (b).

14. **§13.14 Track-2 external review executed** (v0.2, 2026-07-20; 10
    findings, 9 confirmed by independent reproduction — the reviewer's
    exact numbers matched, incl. 12/49+12/25 parity-flipped windows and
    the 17.8 GB float64 plane). Fixes, all landed with tests: (a) F1
    THREE-WAY SPLIT — fit / certification / reporting populations by
    two independent bits of the (131y+17x) hash over ELEMENT-GLOBAL
    indices; reporting cells consulted by nothing. IN-BUILD INCIDENT,
    recorded: the first second-hash used a different odd-coefficient
    linear form which is the SAME bit-0 function ((y+x)&1) —
    certification came out identically empty, every lock fell back to
    (0,0), only the full-warp channel exposed it (c3 28.8%); a
    partition unit test pins disjoint/cover/balance. Honest post-fix
    numbers: full-warp c3 0.43→0.56% (+0.13 pp; the reviewer's one-seed
    A/B predicted +0.108), c2 12.9→13.3% (+0.40 pp vs predicted +0.44);
    geometry residual c3 +0.50 pp. (b) F2 CANARY RULE v2 — the old rule
    passed on the Wilson LOWER bound ("not proven bad ⇒ safe",
    anti-conservative) with no reference health gate: a 50%-BER channel
    and missing references both certified margins (reproduced). v2:
    pass requires the pooled UPPER bound under the bar, per-replica
    floors, a healthy reference (n>=1500, upper<=0.20, all replicas
    present), completeness enumerated from plan constants; unobservable
    is fail-closed; the claim string says payload_safe only when
    everything holds. (c) F3 CALIBRATE-OR-REFUSE — hard gates
    (orientation margin>=1.15, 4/4 corners NCC>=0.15 and rms<=6 px,
    observable references, printed ID MATCH) return a refused report
    with NO measurements; out-of-frame content is per-element
    unobservable, never clipped (the old tick/ID reads scored missing
    paper as printed evidence). (d) F4 BINDING — printed ID = sync +
    24 bits of sha256 over the canonical layout, not name strings;
    load_sheet verifies GT sha + PS sha + recomputed identity (forged
    printer_id/bbox refuses); reports carry scan
    sha256/dtype/shape/source, content-addressed, never overwritten.
    (e) F5 per-crop float32 darkness over a native-dtype raster
    (4800 dpi ~18 GB float64 → ~raw size; true tiled/mmap RasterSource
    deferred to the track-3 kernel, user ruling). (f) F7 tie-realizable
    thresholds; F8 coupon verdicts split (ldpc_exact_genie + strict
    word_and_payload_exact); F9 permuted canary gap orders +
    Latin-square coupon strips + 3 replicas on long edges; F10 layout
    GOLDEN frozen (gt sha 56082b2e…, ps sha 510e4f91…) + refusal
    battery (wrong-ID, crop, noise, tampered PS/manifest, dead
    references, report overwrite). DEFERRED with reasons:
    records/profile/promotion = batch E (per-edge margin registry
    schema); detector Arm 2 after track 3 (user ruling: the production
    receiver becomes arm 3). Suite: tests/holo 153.

15. **§13.15 Sequencing ruling** (v0.2, user, 2026-07-20; HISTORICAL):
    TRACK 3 BUILDS BEFORE the generic characterization instrument — the
    shared kernel's most demanding consumer is the receiver; the
    instrument's ranking arm (arm 3 = production replay) only exists
    once track 3 does; track 3 is the critical path and produces the
    first v1 prints (with the §11 riders). The generic-instrument
    design of that date (experiments/025-channel-metrology/DESIGN-V3.md
    v0.2; substrate ruling: src/holo implementation with paperholo/e025
    as TEST ORACLES — the keystream_ref pattern) waited on the track-3
    kernel and was later replaced by the independent instrument (item
    20). Track-3 design = docs/RECEIVE-DESIGN.md + evidence base
    docs/RECEIVE-DESIGN-EVIDENCE.md (859 machine-extracted items,
    8-reader sweep over e021–e024 + legacy receivers). RETRACTION
    preserved: RECEIVE-DESIGN v0.1's headline ("colocation inverts
    acquisition — no absolute-valued pilot field in v1") was FALSIFIED
    by the design's own adversarial panel against the format code
    (pads-zero ⇒ every printed pilot bit is predictable a priori; the
    legacy field was structurally identical). Corrected ruling
    (RECEIVE-DESIGN v0.2 §1): TWO LANES over one cold-predictable
    field — Lane W word self-addressing as the measured-economics
    default (a Stage-A word seed must still pass the ordinary disjoint
    pilot gate; known-position words are one-way consistency
    observations) + Lane C seed-predicted-field correlation as the cold
    seeder and sub-word fragment lane from day one (certified cells
    boost reference density, they do not enable the lane); legacy
    size-based routing stays dead.

16. **§13.16 Track-1 correction, in-place v1 alteration** (v0.3, user
    ruling, 2026-07-21). The printed identifier remains v1; no
    compatibility branch, format-version bump, or legacy
    payload-generator mode — explicitly permitted because the format is
    not yet frozen. Supersedes item 6's placement rule and sharpens item
    10's capacity claim: (a) Domain-8 conformance gap closed — the
    production block-assignment stream already matched the pure-Python
    reference; the omission was TEST coverage only (now in the constant
    table, block/64-bit-key equality cases, frozen key-stream digest,
    and canonical full assignment digest incl. stable sort; no
    algorithm changed). (b) Metadata placement changed: the `counter
    mod 24` certified-copy channel → the §6.2 counter-addressed LFSR
    equation channel (word layout and one-bit-per-tile budget
    unchanged); placement + recovery live together in
    `format/metadata.py` — the generator and close adapter call that
    module, never duplicate the arithmetic; trust floor = full-rank
    recovery + 48 distinct equations; compose goldens intentionally
    re-frozen; the already-emitted charsheet-1 instrument remains
    quarantined legacy composition, not a payload-format compatibility
    mode. (c) Planner repaired — the original enforced only
    average/global fragments while the fountain prose promised the
    worst retained whole pages clear every block with reserve; the
    shared predicate is now the two §7.2 inequalities; regression pins
    in §7.3; fixed-page maximum enumerates block intervals,
    requested-payload planning increments pages to safety. (d)
    Envelope/K binding enforced — canonical minimal K + zero padding;
    close rejects a SHA-valid payload under a forged larger K or
    nonzero padding (§7.1); the payload digest alone binds neither. (e)
    Sidecar auditability — per-page packed-GT SHA-256 + shape + bit
    order, convenience only, never decode input (§10.1). (f) Track-3
    migration boundary: persisted metadata evidence must retain
    `(counter, certified_bit)`, not a residue `bit_index`; coefficient
    rows, rank, and check shortfall are derived; any in-progress
    pre-freeze `MetadataVoteRecord(bit_index=counter%24)` schema is
    superseded and must be migrated/bumped by Track 3, never silently
    reinterpreted.

17. **§13.17 Track-3 clean reconstruction and Track-2 quarantine** (v0.4,
    user rulings, 2026-07-21). The first `src/holo/receive` attempt was
    reviewed against E021–E023c, their implementation notes, and the old
    `paperholo` chain, then REPLACED IN PLACE — no compatibility adapter,
    alternate ideal-capture production path, or retained dead receiver.
    Operative design = `RECEIVE-DESIGN.md` (current version per its own
    header; v0.15 at this entry's date); this item's
    binding rules are carried forward by §§9–10 and RECEIVE-DESIGN §§2–8:
    algorithmic fidelity before novelty (the E021/E022/E023b/E023c
    algorithms are the starting point; mechanical improvements may change
    work and representation but never admission or decoded results;
    numerical changes need a design amendment + comparative qualification
    first); colocation removes plumbing, not evidence requirements
    (RECEIVE-DESIGN §2 — colocation does NOT make position observable,
    justify capture-wide photometric normalization, eliminate the full
    address domain, or let certified cells seed their own first
    acquisition; no legacy 60/64 lattice bridge); no normalized-darkness
    receiver (the Track-2 capture-wide percentile convention is neither
    an E021 principle nor a Track-3 dependency); Track 2 suspect and
    isolated (import-graph-enforced; resolved by deletion, item 20); one
    production runtime (certificates alone cross-lane bit authority,
    proposals non-authoritative, same-capture views never sum, `--diag`
    never on the numerical path); no hidden or arbitrary result-changing
    resource ceilings (format/page domains complete by default; the
    explicit retained historical portfolios remain algorithm semantics —
    eight lower hints total with up to two runners, two losing
    hypotheses per region; explicit user page hypotheses = a separate
    exact session axis); explicit qualification boundary — no v1
    physical/null placement qualification has frozen a production
    policy; the v0.4 refuse-before-ingest availability rule is
    superseded by item 18, but its qualification conclusion is not, and
    it is no license to invent constants or weaken a gate.

18. **§13.18 Operational provisional receiver policy** (v0.5, user
    ruling, 2026-07-21). Production decode may run before the physical
    v1 qualification completes — an availability decision, not an
    algorithm or evidence upgrade. The active stand-in is the former
    qualification-only row copied unchanged: familywise alpha `1e-3`,
    assumed true-channel BER envelope `0.08`, `HISTORICAL_E022_GATE`
    (`search < 0.20`, `validation < 0.24`, `rival > 0.20`, winner gap
    `>= 0.08`), support margin zero, word alpha `1e-3`, same
    qualification identifiers; default and explicit selection share one
    semantic pipeline identifier. Evidence status is separate,
    non-semantic, and always explicit (no implicit `qualified` default);
    every composition built by the current production root is
    `provisional`, and changing that label cannot fork policy identity,
    scores, state, or decoded bytes. Every provisional run emits
    `ProvisionalReceiverWarning` before state load/creation or raster
    access (CLI installs an `always` filter, so resumes warn every
    invocation); `--diag` initializes lazily after the warning, receives
    a first-class `receiver.provisional` event, and carries
    status/blockers into its final report; malformed diagnostic history
    or observer failure stays non-authoritative. The warning names BOTH
    open duties: the physical/null false-accept, true-BER, and
    support-margin freeze; and the prior pre-final-hoist clean 312-page
    C3 result — exact winner found but the inherited rival gate refused
    mismatch `0.176` — with the post-hoist full-domain yield/resource
    run still outstanding; no bar is weakened to hide that result.
    Obsolete Track-2/discarded-receiver-API tests removed; the ordinary
    Holo suite invokes the source-local E021/E022/E023/E023b/E023c,
    state, policy, diagnostic, isolation, and production-round-trip
    qualifications through current public seams; direct current-API
    tests retain native-ingest contracts, noisy/wrong-page/erased tile
    certification, and a K=61 repair/shortfall/SHA fountain close.
    Landing validation: Holo suite 192/192; repository 880 collected —
    sandbox-safe run 873 passed + 1 expected skip with six historical
    HTTP diagnostic viewers deselected (need a localhost bind; those
    exact six pass 6/6 with permission). No product failure hidden by
    the split run.

19. **§13.19 Track-3 causal diagnostics** (v0.6, 2026-07-22;
    `RECEIVE-DESIGN.md` v0.6 §10 was normative; archive/storage clauses
    superseded by item 22, frame cadence by item 32; current contract =
    RECEIVE-DESIGN v0.15 §10, which carries the detail). Review found
    the v0.5 surface had observer isolation but had lost the historical
    causal instrument. Restored, typed and lazy — never an alternate
    receiver: headless builds no fine snapshots; no raster, mutable
    store, or `SessionState` enters an observer, timing, digest, or
    policy id; per-block `CloseProgress` is a lazy factory inside the
    fine-snapshot exception boundary, never authority; adapter failures
    disable only the observer. The four-pane historical language returns
    with v1 authority; GT/BER/qualification labels never enter
    production panes. Cold reconstruction is honest, never cosmetically
    complete (unavailable facts say so — never zero-filled; no NeedMap
    or geometry synthesized from weaker state; one complete scale ladder
    per persisted capture). Detector policy is not a diagnostic option:
    every production lane hard-wired to registered `ctx-pava-v1`
    (`pava-v1` = internal historical primitive/qualification arm, not a
    CLI selection). Locked no-follow directory-relative inode binding;
    loopback binds `127.0.0.1`, exact-Host-checked, detached current
    bytes only. Performance corrections preserved semantics: repeated
    full committed-snapshot rebuilds removed (projected C3/C2 campaigns
    ≈ 41/18 million record conversions), unused ~256 MiB block bitmaps
    removed, all-attempts×all-blocks scans replaced by exact per-page
    frontier indexes; a proposed retained cache of full 64×64 attempt
    views REJECTED (crossed the numerical/observer boundary, multi-GiB).
    Post-hardening validation: tests/holo 341 in 127.74 s (+1 loopback
    skip passing with permission); repository 1,030 collected in
    1128.01 s — 1,022 passed, six sandbox-denied historical binds
    (6/6 in 67.53 s with permission), two loopback skips (passing with
    permission); diagnostic qualifier 9/9; production round-trip 4/4
    (fine/headless authoritative parity, restart, rotation,
    observer-failure isolation); Track-2 quarantine +
    compile/diff/source-size checks passed; no experiment source
    changed. Real-v1 operator usefulness, full-volume render/RSS
    measurements, and the numerical physical qualification gates
    remained outstanding, disclosed as provisional.

20. **§13.20 Independent characterization instrument** (v0.7,
    2026-07-23; current contract = §10.3 + CHARACTERIZE-DESIGN.md /
    CHARACTERIZE-HOWTO.md, which carry the instrument detail). The
    quarantined `holo.track2` package and its isolation program are
    DELETED — no compatibility import, manifest upgrader, or retained
    obsolete test path. The new `holo.characterize` is a clean build
    (fixed candidate registry, overlap-refusing B/W + color layouts,
    HCAL-R1 self-report, typed physical probes, held-out measurement,
    conservative summaries, calibration aggregation); discovery reports
    usable authored DPI and tested cell sizes without treating request,
    driver readback, or manufacturer claims as physical truth, and the
    E007/E025 audit restored the useful geometry/transport/grid/edge/
    adequacy/morphology/tone diagnostics while active resolution
    enumeration, legacy transports, FEC/rate atlases, and receiver
    coupons stay outside. Calibration aggregation requires a matching
    stable device-self-report digest; the per-impression nonce binds
    redundant strips but is excluded from that digest so independently
    printed copies can combine. Production
    core/devices/format/gen/receive and paperholo unchanged;
    `holo/cli.py` only routes `discover`; static import tests enforce
    both directions of the boundary. Synthetic qualification qualifies
    plumbing only — every printer/media/path/scanner footing still
    needs physical discovery and independently seeded calibration
    before profile promotion.

21. **§13.21 Selected-contributor BCH promotion firewall** (v0.8,
    2026-07-25; normative detail = RECEIVE-DESIGN §5.4; summary §9.3). A
    legal known-position BCH counter contradicting an accepted
    placement's implied counter is no longer diagnostic-only and no
    longer aborts the lane/session: after the final lane word vote,
    exactly the contributing independently fitted E022 placements are
    quarantined — a promotion decision, not retroactive placement
    rejection (poses durable; no continuation hint, proposal,
    calibration/LLR, owner, evidence block, attempt, certificate, or
    refinement from quarantined patches; clean placements continue;
    NeedMap stays certificate-derived; old quarantined evidence never
    auto-rehabilitated). State keeps sorted typed conflict records; the
    quarantine set is the contributors' derived union, never a second
    stored fact; replay binds contributors and rejects
    quarantined-origin payload evidence. Semantic component identities
    changed; schema-11 state intentionally refused without a
    compatibility guess. REJECTED alternatives: session-fatal abort
    (unnecessarily destructive once contributors are attributable);
    tile/site-only quarantine (too narrow for a possibly wrong window
    pose); diagnostic-only handling (affirmative address contradiction
    must not reach payload). Historical incidence: ZERO contradictory
    decodes in 1,780 attempted real-confetti reads and zero wrong final
    certificates — the firewall covers an unobserved tail; its
    synthetic/adversarial tests do not replace a format-v1 physical
    measurement of conflict incidence, false-quarantine rate, or
    receiver-yield impact.

22. **§13.22 KISS authority and operational diagnostics** (v0.9,
    2026-07-26; diagnostic contract detail = RECEIVE-DESIGN §10).
    Receiver schema 17 / discovery schema 8 with NO compatibility reader
    (schema later 19, item 23). Root discovery retains authenticated
    capture facts + the voted `c` only; candidate exclusion is derived —
    no prune ledger, stored reason, or duplicate root E021 record.
    Pipelines complete by construction (explicit policy-identified
    components, qualification supplies complete fakes; no
    deferred/missing-processor dispositions). Numerical records store
    causal inputs, conclusions derived (word status, site/erasure
    counts, attempt/certificate counters, decoder parameters,
    certificate bit length, divergence address/rate, expected counter —
    all recomputed from retained facts + the active format); lower-hint
    certificate lineage is a typed field, not a parsed diagnostic
    string; dead echoes removed; the qualified survey floor, two-PPC
    scale floor, bounded hint portfolio, and BP60/BP150 profiles are
    fixed doctrine, not fake configuration. Format-bound load
    reconstructs all omitted policy facts (incl. the two-pass BP cost
    bound and BCH expected counter) before terminal resume; capture
    facts share canonical dtype/channel validation; certified refinement
    rejects a noncanonical frozen `rot90` rather than normalizing
    corrupt authority. Diagnostics = operational visualization, not a
    second resumable state machine (fresh per-invocation event log,
    atomically replaced current files, one terminal bulk projection,
    optional explicit loopback, final report from committed state; NO
    manifest, receipt, epoch, history-gap ledger, frame archive, resume
    reconciliation, or implicit server; the live shell does not
    advertise a final-report path until publication succeeded; a
    terminal one-row discovery root uses the ordinary exact-row no-op
    bootstrap, a multi-row integrity conflict never resumes an open
    child). Diagnostic failure removes only presentation — never
    barriers, attempts, certificates, close state, authoritative digest,
    or recovered bytes.

23. **§13.23 Provisional CMY7/CMY8 integration** (v0.10, 2026-07-26;
    normative color contract = `COLOR-INTEGRATION-DESIGN` +
    `COLOR-IMPLEMENTATION-PLAYBOOK`, which carry the modulation,
    registration, and evidence detail; calibration detail + terminal
    color wipe superseded by item 26; p120 furniture form in §4.2). Four
    immutable catalog-only rows `c{2,3}-cmy{7,8}-p120-v0` — NOT default
    discovery candidates (F14). CMY7 = one compound `main` stream
    (frozen natural-radix 11-bit-to-four-base-7-cell mapper, three-child
    FEC bank, one shared CRC); CMY8 = independent C/M/Y
    FEC/certificate/fountain streams with common metadata `K`, common
    source fraction `q`, exact stream-major envelope slicing. Generation
    keeps the ordinary envelope/metadata/fountain/page authority and
    selects only the numerical codec leaf; canonical C/M/Y presence
    planes + one composite DeviceCMYK object with zero K (F15); K
    generation, imagemask bytes, seeds, rows, and numerical leaves stay
    exact. Only the 100 indexed word sites enter BCH decoding; a
    contradiction invokes item 21 before any color product escapes.
    Receiver: color scale lanes decimate per channel directly from the
    authenticated native RGB acquisition (aligned luma places, aligned
    RGB colors; shared E022 pose; word/dust/pre-lane-certificate-seeded
    per-plane dot-domain registration, candidates deterministically
    bounded to 512 per class and plane — bounds registration NCC only,
    never detector training or held-out validation); provisional
    detector = the equal-prior full-covariance QDA leaf (CMY7 six joint
    W-relative scores + the item-24 bound; CMY8 marginalized to C/M/Y +
    component PAVA per item 26). Evidence: one compact block (mask +
    `N×6`/`N×3` values) per `(source SHA, lane, address)`; `scan` then
    same-lane `union` at BP60; only the latest eligible ordinary failure
    enters automatic BP150, ledgered `retry150`; raw evidence never
    crosses scale lanes. The stream coordinate landed without a
    compatibility loader → state schema 19; a certificate suppresses
    only its stream (per-address retirement rule, open AND terminal —
    item 26). Close: one fountain decoder per declared stream, common
    metadata verified, deterministic reassembly, ordinary envelope.
    Qualification helpers: an independent synthetic plane model +
    `holo.qualification.color_distort` (600-dpi RGB TIFF → 1200/4800
    dpi; identity unless effects explicitly requested; `nominal`/
    `stress` overridable shortcuts, characterized `hp-m281-flatbed-cmy`
    and K-plane `hp-m281-flatbed-k`, both 1200-only; no Ghostscript/
    generator/receiver/corpus/manifest/registry). Software coherence only: every color row stays
    provisional until its exact printer/emission/media/scanner footing
    passes blind coded paper close, zero-wrong-certificate,
    damage/combination, and aggregate discovery/null gates.

24. **§13.24 CMY7 durable-evidence bound** (v0.11, 2026-07-26; current
    form §9.3, policy id `cmy7linf20`). The historical seven-state QDA
    leaf remains an exact transient production-local port; at the CMY7
    detector-to-evidence adapter only, each cell's six W-relative score
    vector `r` becomes `r/max(1, ||r||_infinity/20)` before float32
    persistence — one uniform positive factor bounding every component
    to `[-20,+20]` while preserving all component orderings and signs
    relative to W's fixed zero. Six independent componentwise clips are
    NOT equivalent (they can tie strong state hypotheses and change the
    hard state decision) and are forbidden. Each physical acquisition is
    bounded independently; a legal union of `N` distinct same-lane
    source blocks may reach `20*N` per component — no second union
    clamp. Does not alter CMY8 or K (the CMY8 calibration correction is
    item 26).

25. **§13.25 Color certificate-divergence accounting** (v0.12,
    2026-07-26). Divergence stays a non-gating operational comparison in
    the existing generic certificate/block count record: one record per
    known certificate × same-address compact block on the published live
    frontier, deduplicated by content identities. CMY8 compares the
    expected component reconstructed from the named certificate stream
    with the sign of the block's corresponding C/M/Y evidence column
    (missing siblings do not participate); CMY7 reconstructs the exact
    compound printed tile and compares its state with
    `argmax([W=0, C..MY relative scores])`. While a compact block body
    is live, barrier validation and load replay reconstruct both counts
    exactly; after ordinary per-address retirement, its cryptographic
    block identity + causal certificate reference remain auditable
    without retaining numerical observations solely for diagnostics;
    terminal close adds no separate retirement (item 26). Snapshots,
    detail, and reports include the certificate stream; K keeps its
    scalar comparison, durable records, report fields, and snapshot
    shape unchanged.

26. **§13.26 Post-review color receiver correction and direct software
    gate** (v0.13, 2026-07-27; normative detail = COLOR-INTEGRATION-
    DESIGN + RECEIVE-DESIGN §6.2). Calibration keeps the wire fixed and
    separates estimators: `p120`, its W/CM address word, dust-state
    schedule, and golden vectors unchanged; word AND dust rows
    train/validate the equal-prior eight-state QDA; component PAVA uses
    DUST ROWS ONLY [as shipped: dust PLUS prior-barrier CRC-certified
    complete-state payload rows — sanctioned by RECEIVE-DESIGN §6.2,
    policy family `dust20-priorcert-…`; BCH word rows still stay out of
    PAVA; recorded 2026-08-02] — equal scores pooled before isotonic
    regression,
    equal total weight per binary label per component (dust rows are
    balanced for C and M but carry Y in two-thirds of rows; word rows
    influence QDA scores but neither enter nor balance PAVA; zero/0.5
    anchor + finite clamp remain). Absent color evidence stays absent
    independently: a component collapse guard emits exact-zero LLRs for
    that component only, a globally degenerate fit an all-zero `N×3`;
    CMY8 eligibility counts ACTUAL nonzero LLRs against the row's
    active-information count; CMY7 needs ≥ 2,240/1,883/1,883
    structurally supported positions in A/B/C (item 27), then the same
    actual-nonzero floors per child post-demap; physical cell counts or
    `complete_packs*11` are NOT eligibility substitutes. Sampling
    bounded without fragmenting the fit (final form §9.4). Ordinary
    close at two deliberate boundaries: ≤1 advisory pre-BP150 close per
    ordinary color batch on a pure necessary count gate (metadata
    complete; every declared stream ≥ K distinct certified ESIs; every
    block ≥ its authoritative `K_b`; never a substitute for rank,
    reassembly, or envelope SHA; terminal advisory skips retry150); the
    completed lane barrier performs the authoritative persisted
    post-BP150 close; no per-certificate or in-retry close; `--complete`
    suppresses both (item 31). Ordinary live frontier, no special
    terminal lifecycle (schema 19; per-address retirement, same rule
    open and terminal; no global wipe). Format-derived dispatch: the
    row's stable `codec_id`, never Python object identity; planner
    `N-K`/CLI reporting mean repair symbols PER LOGICAL STREAM; public
    save/load = full replay + format-derived validation + exact close
    reproduction (final form §9.2). Direct software seam (opt-in,
    slow): `HOLO_RUN_GS_COLOR_RECEIVER=1` pytest
    `-k closes_through_standalone_tiff_transformer` composes generator →
    Ghostscript → standalone TIFF transformer → real receiver CLI →
    byte-exact close → strict reload for every color row; restores no
    corpus builder, corpus manifest layer, or production distortion
    shortcut. Software qualification only — all four color rows remain
    provisional, catalog-only, absent from default discovery.

27. **§13.27 CMY7 structural attempt pre-gate** (v0.14, 2026-07-27).
    Complete-pack presence is a cheap structural fact, not a soft value:
    expand each complete pack to its eleven supported mapped positions,
    scatter that Boolean vector through the exact inverse interleaver,
    split at the declared child transmitted widths, and refuse BEFORE
    soft demapping if any child cannot reach its active-information
    count. Passing grants no decoder attempt — the tile is soft-demapped
    exactly once, inverse dither/interleaving produces the aggregate
    code-LLR vector, and every child must independently meet the same
    floor on ACTUAL nonzero LLRs before the three-child decoder sees it.
    Cost scheduling only; no printed format, evidence meaning,
    certificate authority, or qualification change.

28. **§13.28 Bounded receiver vectorization** (v0.15, 2026-07-27). E022
    authoritative-row alignment via integer-key array matching; 3×3
    neighborhoods via one window-local lookup; color owner selection
    keeps the same loss/patch-ordered first owner through canonical
    concatenation + first-occurrence selection; provenance replay
    validation batched by origin window — Python per-cell work replaced
    by bounded arrays while preserving row order, selected evidence,
    refusal semantics, and durable provenance. CMY7 still scores
    exactly the 2,048 legal mapper candidates: per pack subtract one
    common maximum, exponentiate normalized weights, dense-reduce all
    eleven one/zero partitions (the common normalization cancels from
    every LLR; an extreme finite row that underflows either partition
    uses the direct log-domain reduction for that row only; the
    candidate bank is bounded to one tile and released after demapping).
    A mathematical/behavioral implementation equivalence with a modest
    bounded working set — no printed-format, receiver-policy, evidence,
    ownership, certificate, or qualification change.

29. **§13.29 Operator-first live diagnostics** (v0.16, 2026-07-27;
    `RECEIVE-DESIGN.md` v0.10 §10 normative — incl. the six-row status
    block, pane semantics, full palette table, and coverage
    definitions; presentation-only, no printed format, schema, policy,
    event-order, evidence, certificate, close, digest, or byte change).
    The four-pane causal language stayed useful but the live browser
    had become an audit dump displacing the spatial progress an
    operator follows; replaced by the fixed operator composition:
    six-row text block (format; scrap-region progress + labelled
    payload-area coverage; scale lane; address; LDPC incl. distinct
    `retry150` certificate births; metadata K/fountain) above four
    equal A4 portrait panes A/B/C/D with stable legends; no tabs,
    progress bars, fold-outs, event prose, raw hashes, or provenance
    labels. Operator counts are derived, never new authority (scrap
    classification once per live `(capture, lane, region_id)` — the
    placement-hypothesis ledger is not a scrap count; actual decoder
    calls exclude below-floor evaluations; `+BP150` = certificates
    minted by `retry150`; symbols and rank shown separately against K,
    neither replacing envelope/SHA verification; unknown/cold values
    shown as such, never zero). Coverage = union of unique
    geometrically reached payload cells over registered payload cells
    on the selected page (area-weighted at cell granularity; distinct
    from the old tiles-touched count and from continuous whole-A4
    physical coverage; cold geometric reach unavailable, durable tile
    reach not relabelled). One visual grammar (green certified … amber
    below-floor … deep-red double-border conflict; certified and
    conflict can never share color or border); CMY8 gets an ordered
    labelled C/M/Y state rail + per-stream summaries, never a generic
    purple partial tile. Auditability stays detached and complete
    (scalar log, one terminal machine-detail snapshot, final
    JSON/HTML/SVG report; machine detail unavailable during processing,
    no browser fold-out route).

30. **§13.30 Operator review of the live diagnostic** (v0.17,
    2026-07-28; `RECEIVE-DESIGN.md` v0.11 §10.3 normative;
    observer-only). The first integrated live run exposed presentation
    defects, not receiver defects. Fixes (detail in §10.3): white shell
    + revision-keyed image replacement (no black flash, current frame
    visible until its replacement decodes); legends = color/outline
    sample + plain label, no one-character state-glyph column anywhere;
    piece identities reserved for every surveyed region before
    placement and shared by A/B (an unresolved scrap cannot compress or
    renumber later pieces); Pane C prints the numeric observed BCH-site
    count on every touched tile; accepted Pane-B placements use their
    solid piece outline immediately (redundant thin, active focus cyan,
    purple limited to genuinely current proposals/continuations, no
    false green legend fill); CMY8's LDPC row reports calls,
    certificates, BP150 births, failures, and below-floor counts per
    stream plus fully certified physical tiles; `session.complete`
    publishes a final selected-page revision — with a connected
    browser, normal finalization waits only until that revision is
    served or a bounded deadline expires, the acknowledgement bound to
    the revision atomically paired with the returned image bytes, not
    the requested query number; no browser = no delay; explicit/error
    close immediate. Piece numbers, observed-bit numbers, basis labels,
    and C/M/Y labels remain (identity or data, not accessibility
    duplication). No numerical path, printed format, persisted state,
    certificate, close gate, digest, or recovered byte changes.

31. **§13.31 Invocation-only final-close deferral** (v0.18 recorded a
    verified-continuation interpretation, now SUPERSEDED; corrected
    v0.19, 2026-07-28; `RECEIVE-DESIGN.md` v0.14 §8.1 normative).
    `--complete` = defer fountain checking/solving until the acquisition
    request is exhausted, nothing else: ordinary stopping unchanged
    without it; with it, all requested capture/lane barriers run and
    persist while the session stays open, no barrier fountain
    check/solve, color advisory preclose suppressed too; ONE common
    close phase at the very end (an exact session against its final
    certificate frontier, or discovery's uniquely recognized branch
    only — never per candidate row or capture-shaped child). Terminal
    states never reopen (`verified` / `integrity_failure` /
    `unsupported_metadata` immutable; load/hash/save fountain-free
    under the flag; retained terminal closes reproduced immutably;
    unrecognized/conflicted discovery roots make no fountain call).
    Invocation-only: absent from semantic pipeline identity and durable
    state; no other survey/placement/NeedMap/retry/evidence/
    certificate/discovery/format/persistence policy touched; schema
    19 / discovery 8 / format identity / recovered bytes unchanged.

32. **§13.32 Bounded live diagnostic hot path** (v0.19, 2026-07-28;
    `RECEIVE-DESIGN.md` v0.14 §10 normative). A full C3 multi-capture
    run showed observer work could dominate receiver wall time (fine
    events synchronously rebuilt multi-megabyte detail + full four-pane
    PNGs) — observer non-authority is not enough, the operator path
    must be operationally bounded. Live state compact (scalar JSONL
    append + incremental view delta + atomic compact status; never
    walks or serializes bulk arrays); fine progress cannot force a
    frame storm (region/context/refinement events obey the ordinary
    throttle; only a bounded set of coarse lifecycle milestones may
    force frames; identical pane bytes need not rewrite); bulk detail
    terminal-only (one immutable snapshot at finalization; live
    endpoints report unavailable; the committed final report stays a
    separate terminal projection covering the declared page domain).
    Authority and failure isolation unchanged.

33. **§13.33 Result-exact receiver pruning and deferred projection**
    (v0.20, 2026-07-28; `RECEIVE-DESIGN.md` v0.14 §§7, 8.2, 10
    normative). Work is avoided only where exact result identity is
    established: a certified `(page, tile_y, tile_x, stream)` is
    rejected before a dense `TileAttemptView` or LDPC call is
    constructed; scan/union grouping omits terminal keys; compact
    barrier evidence retains unresolved work; a retry divergence pass
    revisits only retry-minted certificates; NO pre-placement pixel or
    regional-context pruning is licensed by this rule. Refinement
    reuses generation-zero window evidence byte-for-byte for unchanged
    regions/windows (integer crop/filter signature change →
    conservative region recompute); a differential oracle requires
    exact equality through capture evidence, dependency blocks,
    attempt/certificate/divergence ledgers, and the canonical barrier
    delta. A partially computed refinement generation never replaces
    the last complete panes (presentation only). Deferred barriers may
    decode metadata K and count distinct legal ESI symbols WITHOUT
    instantiating a fountain decoder/rank/solve; rank stays explicitly
    deferred to the sole final close, whose memoized snapshot feeds
    `close.check` and `session.complete`. No second meaning for
    `--complete` (item 31).

34. **§13.34 Structurally qualified color start, terminal-work pruning,
    placement-view lifecycle** (v0.21, 2026-07-28; `RECEIVE-DESIGN.md`
    v0.15 §§6.2, 8.2, 10 normative). (a) CMY8 has NO aggregate
    300-label cliff: first-order QDA on exact word/dust furniture with
    deterministic disjoint search/held-out partitions + sparse-state
    repair; each PAVA map consumes all 20 trusted dust labels on the
    fitted QDA axis; C, M, Y qualify independently (six labels per
    binary class, two nuisance states per class, three labels per
    counted nuisance state) — exactly the one-tile p120 dust base, so
    ONE decoded 100-site BCH word plus its dust can start first-order
    payload decode; unsupported components emit exact-zero LLRs while
    siblings stay usable; tie-pooled equal-binary-class zero-anchored
    PAVA + the finite `ln(N+1)` bound unchanged; no raw-QDA fallback.
    (b) Certificate reuse is barrier-pure: a CRC certificate may
    strengthen registration/calibration on a LATER lane; current-lane
    certificates are never fed back before commit (preserves the
    prior-barrier causal law, avoids a redundant second pass); partial
    CMY8 certificates stay component-only; certificate work conflicts
    rejected before any terminal fast path. (c) Terminal payload work
    is physically absent: wholly terminal regions skip sampling,
    context fitting, certified refinement, region progress, compact
    blocks, and decode; mixed regions keep all donor windows (they can
    affect an unresolved neighbour) but terminal owner rows are removed
    before block formation; partial CMY8 tiles retain only
    missing-stream eligibility; block formation streams one tile-sized
    group at a time; differential tests require unresolved evidence and
    results byte-identical. (d) Pane B lane lifecycle (§10.3.3): active
    lanes show placement metadata (union boundary, piece number,
    runners/refusals/proposals); at the committed barrier it disappears,
    leaving stable scrap-colored support; cross-lane piece identity by
    deterministic normalized scan-geometry matching, never the
    independently sorted region index (ambiguous split/merge geometry
    gets fresh identities); completed support composited once into the
    fixed panel-resolution cache at commit; completed-only frames show
    no lane metadata; Pane D draws no rail for wholly unseen tiles and
    states C/M/Y ordering once in the legend. Receiver and presentation
    policy identities change; printed format v1, keystreams, LDPC/CRC
    authority, fountain semantics, and recovered payload bytes do not;
    the four color rows remain provisional pending the existing
    physical qualification gates.

35. **§13.35 Pooled-fountain CMY8 -v1 rows** (v0.24, 2026-08-13; design
    + adopted rulings + qualification record:
    docs/CMY8-POOLED-FOUNTAIN.md; execution docs/CMY8-POOLING-PLAN.md;
    dialogue: REASONING-LOG "Session 2026-08-13 — CMY8 fountain pooling
    and the dead-plane trade"). APPEND-ONLY rows `c2-cmy8-p120-v1` /
    `c3-cmy8-p120-v1` (same CMY8 CodecProfile as -v0 — detection,
    certification, and the receiver payload path are untouched by
    construction; catalog-only, F14): ONE pooled fountain over
    `esi = counter·n_streams + stream_idx` on domains 7/8 with
    stream-exact per-(block, page, stream) quotas (the generalized
    assignment is BIT-IDENTICAL at n_streams = 1 — oracle-pinned; the
    -v0 per-stream fountain, domains 14/15, is retained verbatim for
    the printed e030/e032 sheets and the uplift corpus); k_meta =
    the -v0 canonical common K in the metadata K field, k_total =
    n·k_meta (envelope padding byte-identical, row-major S-bit
    slicing); per-stream metadata equations at LFSR state
    counter·n + stream (3× equation density; fragment metadata floor
    ~48 → ~16 tiles healthy, ~24 with one plane dead — punctured
    indices lose consecutive-rank, pinned both ways); capacity =
    THREE enforced tiers (global, stream-exact page tier
    L·n·(T//B), plane tier P·(n−1)·(T//B)) with the q dial capped at
    (n−1)/n as PLANNER POLICY (tier-3 budget grows with P, so page
    inflation could otherwise launder any dial at ~⅔ fill; capacity
    queries refuse instead of quoting dishonest fills). Measured
    corners recorded: B_pooled ∈ {3B−2..3B}, reserve pooled ≤ -v0
    always (16385: 72 vs 114), capacity corner deficits ≤ ~0.1%,
    one-solve regime k_meta ≤ 5461 (every physically closed CMY8
    volume to date). Gates landed (all simulation): dead-Y-everywhere
    E2E through the production receiver closes byte-exact with zero Y
    certificates while the -v0 control stays OPEN; nine-row backbone
    net; gs+distortion chain closes both -v1 rows; fragment-boundary
    crop; frozen row goldens. Measured novelty: pooled verified-stop
    preempts BELOW the -v0 per-stream floor (c2 closed at
    C:48/M:47/Y:47 — no per-stream rank requirement exists). RULED
    2026-08-14 (user): the version field STAYS 0 — the word is only
    readable through row-specific seeds/equation indices, so row
    identity precedes any K-field interpretation ("if you can read
    it, you are already doing the right thing"); word layout and
    K-field value unchanged; §7.2's version-bit precedent is scoped
    to swaps a reader could otherwise misread; no new R3-preface
    fact (the row id the preface already carries determines pooled
    semantics). Physical qualification remains open (F14 unchanged);
    holo2's carried fountain/streamset leaves sync separately.
    AMENDED 2026-08-14 (user ruling, design note §0 ruling 5): the q
    ceiling is no longer a refusal — pooled rows accept any legal dial
    and the plane tier is DIAL-CONDITIONAL, enforced in sizing and
    reported `guaranteed` at q ≤ (n−1)/n, dropped from sizing above it
    so the volume fills to the true dial, with the status reported
    loudly everywhere (plan, manifest `pooled_fountain.plane_tier`,
    `capacity`, `generate`); the predicates take an explicit
    `enforce_plane_tier` keyword and stay pure.
36. **§13.36 Column-group pool for uneven CMY8 rung triplets** (v0.25,
    2026-09-04 — designed, RULED (seven rulings) and BUILT the same day
    on branch `cmy8-column-groups`; design + rulings + build record
    docs/CMY8-COLUMN-GROUPS.md; FORMAT-SPACE §17; dialogue
    REASONING-LOG "2026-09-04 — CMY8 uneven rungs: the column-group
    pool"). The §13.35 pool XORs whole symbols, which is why gen-v1
    cmy8 triplets were width-classed (FORMAT-SPACE §5, now lifted). The
    pool is GF(2)-column-separable — the frozen solver eliminates the
    generator rows once and carries the symbol bits as values — so the
    widest plane's width S is carried as Z column groups of a RATIONAL
    partition (`bounds[g] = floor(g·S/Z)`, widths within one bit; Z =
    argmin of the mean spare bits per site over Z ≤ 32, ties to the
    smaller Z — the heavy plane's spare is zero by construction, the
    light plane's a bit or two); a lighter plane carries the largest
    run of consecutive groups that fits its width; chunks fill a
    block's tiles consecutively in the block-assignment KEY order
    (uniform rows keep the frozen ascending order — bit-identical, the
    fork guard), so the light plane's groups rotate with exact per-page
    quotas and spatial whiteness; source chunk c of a block is group
    c mod Z of in-block row c // Z; a tile past K_b·Z carries one repair
    row (K_b + rank) over its groups; a straddling tile carries zeros
    past the boundary; the K law is -v1's verbatim (k_total = n·k_meta,
    envelope k_total·S bits); the close solves per (block, group) and
    gates on the fewest rows any open group holds; tiers weighted by groups carried (dead-Y
    ceiling rises, any-one-plane ceiling falls — the heavy planes bind
    — both in the manifest's `column_groups` block); reserve
    16 + bit_length(B·Z − 1) (`rank_reserve_for(solves_per_block=)`).
    Worked (exact widths S = k_bits − p − 33): r0700x0700x0547 → Z 17,
    17:17:13, 1.65 spare bits/site, ceilings 30/47 any-plane and 34/47
    dead-Y; r0850x0850x0775 → Z 21, 21:21:19, 0.67 bits/site, 40/61 and
    42/61. Rejected with reasons: encoded-side padding, fixed
    truncation, a site-wide symbol with fixed plane ownership (dead Y
    fatal — the cmy7 joint-packing failure), equal-width groups,
    distinct ESIs per group, pure random picking, raster round-robin,
    supertiles, cross-plane cell borrowing, furniture moves. SCOPE
    RULED: src/holo generation + holo3 receiver; the v1 receiver and
    holo2 untouched (v1 fails a mixed row on `common_user_bits`; the
    holo2 oracles carry `INTENDED_DIVERGENCES` / `ORIGIN_MOVED`).
    Qualification (all simulation): the law table + hand-written
    argmin, slot-map coverage, straddler, balance, key-vs-frozen order,
    encoder vs slot oracle, weighted tiers by hand, planner, manifest,
    three frozen emission goldens; holo3 cross-tree drift of the law
    and slot map, src/holo emission decoded by holo3, per-group solves
    vs the naive GE oracle, dead-narrow-stream and dead-heavy-stream
    closes, the binding count gate; the slow-lane e2e sim pair (the Y
    lever at 10x10 in register and with Y printing nothing — both
    verified byte-exact, the second with zero Y certificates) and the
    three-page lever whose systematic region reaches the Y plane.
    REVIEW ROUND same day (design §10): the core src/holo decoder
    refuses a column-group code; the grouping is
    `FormatSpec.column_groups`; `core/fountain.py` split into
    column_groups / capacity / fountain; holo3 keeps one decoder per
    run inside the close progress (solved groups persist; measured
    close cost at sheet size recorded) and reports a `BlockStatus`
    (rows and rank of the scarcest-by-deficit open group, short, groups
    open, min_rows = the count gate); the close rows, diag, JSON status
    and CLI carry rank / short / groups open / n_groups. F14 unchanged: nothing printed.
