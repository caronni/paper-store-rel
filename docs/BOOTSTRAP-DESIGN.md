# BOOTSTRAP-DESIGN — the deep-time preface (recovery without us)

**v0.1, 2026-07-10. Speculative design, zero print, NO format changes.**
Companion to DESIGN.md (R3 anonymity / R5 registry doctrine, §10.2 trilemma),
PILOTS-DESIGN (window code), FEC-DESIGN, FOUNTAIN-DESIGN. Provenance: a
4-agent design workflow run 2026-07-10 — format-kernel audit of
src/paperholo + docs (verified spot-checks below), hostile red-team
(23 failure modes, 9 circularity findings), independent rung arithmetic,
and a web-verified deep-time-precedent survey. MEASURED/ESTIMATE labels as
usual; everything here is design unless labeled MEASURED.

## The question

Assume the year ~3026. Finders hold a few bound volumes of our printed
output; the paper survived (or was recopied). They can recreate our
general technology — granted for this exercise: Python-class computing —
but paper-store itself must be rebuilt from the pages alone. What must the
first ~30 leaves of every volume contain so that the dense, anonymous
archive pages open?

The answer is a **four-rung ladder** bound into every volume, governed by
one law and carrying one non-speculative repo finding.

## The finding that is NOT speculative: the keystream liability

Every covert bit on a printed archive sheet flows through ONE function,
`modulation.rng` (src/paperholo/modulation.py:19-26):

    BLAKE2b(seed + label, digest_size=16) -> little-endian int
      -> numpy Philox key (no SeedSequence, counter 0)
      -> Generator.integers(...)

— pilot site offsets, pilot value scramblers, the payload keystream, the
LDPC H-construction, the fountain repair rows: all of it. And the
**normative spec of that stream lives outside the source tree**: it is
numpy's internal bounded-draw consumption pattern, where the `dtype`
kwarg forks the stream (the payload keystream is the one
`dtype=np.uint8` draw, modulation.py:36; everything else is default
int64). We already lived the failure once — the 012.3 phantom-payload
incident (`integers()` without `dtype=np.uint8`, pilots.py comment) *was*
the drifted-reimplementation rehearsal: clean-looking sheet, permanent
noise, no gradient to debug against. A finder holding the complete
printed source plus a semantics-drifted numpy regenerates the wrong
streams; because the PILOTS derive from the same function, acquisition
itself fails (the BCH gate rejects every hypothesis — there is no unkeyed
fallback, by design).

Fixes, in two halves:

1. **Non-breaking (spawned as a task 2026-07-10, separate session):**
   a pure-Python, numpy-free bit-exact reference of the whole chain
   (BLAKE2b keying, Philox-4x64-10, the exact bounded-draw rule per
   draw-form used in the codec) + pytest vs numpy byte-for-byte for every
   (seed, label, draw-form) actually used + checked-in golden vectors
   for the e016 volume seed. After this, the repo specifies its own
   scrambling.
2. **Format-axis (OPEN, user decision, layout_version bump):** the
   existing TODO at modulation.py:9 — swap BLAKE2b/Philox for per-cell-
   address AES-CTR, a construction whose complete spec fits on one
   printed page and is independently re-implementable from public
   standards. The bootstrap argument upgrades this TODO's priority from
   "standard crypto is nicer" to "the archive's readability by anyone
   who is not us depends on a printable keystream spec."

**Corollary — R3 inverts under deep time.** The seed's absence from the
pages (anonymity, R3/R5) is a feature today and a single point of TOTAL
loss over centuries: an archive designed so pages read as noise without
the seed *is nothing but noise* if the seed dies. The volume descriptor
(seed, rate_id, compose spec, data_len — fountain.py VolumeSpec) must
exist as a designed, replicated, overt PRINTED object — the preface —
not as a registry row in a git repo. The preface is deliberately
non-anonymous; that is R3's bill coming due.

## The ladder (one-page core)

**The monotone law: nothing crosses the channel before its own
specification has crossed.** No seed, no PRNG, no compression, and no
external library (numpy is contraband until rung 3 delivers it) until its
source or spec is already in the finder's hands. Each rung is decodable
using only what lower rungs delivered, plus a stated minimum of
technology; each rung opens with a known-answer block whose expected
output is printed beside it (the "Voyager circle": a decoder that has not
reproduced the golden block does not proceed).

| Rung | Leaves | Carrier | Net yield | Decoder | Minimum gear |
|---|---|---|---|---|---|
| R0 Plate | 2 (x2 copies) | typography | ~9 KB prose/tables | eyes | none |
| R1 Listing One | 3 | printed source text | ~8 KB, hand-typed | a keyboard, 4-6 h | any computer |
| R2 Coarse | 5 | 0.508 mm modules (12 dots) | ~7.0 KiB/page | the typed R1 program | any >=0.75 MP camera; or loupe + ~60 h |
| R3 Mid | 16-20 | 0.254 mm cells (c6) | ~37.7 KiB/page (duplicated) | R2's payload | ~300 dpi flatbed-class / 3 MP |
| Archive | the volume | c2/c3, anonymous | ~340 KB/page (MEASURED, e016) | R3's payload | 2400-4800 dpi precision scanner |

~30 leaves total; K-only carbon toner throughout (outlives dyes, carries
no MIC tracking dots — MEASURED 007.7/007.8: AltaLink K-only pages are
clean — and stays legible in IR on browned paper); blank versos (toner
blocking cannot ghost data onto facing pages); >=20 mm gutter and >=10 mm
trim margins (rebinding guillotines eat 5-10 mm/century); every leaf
carries an overt header (volume / rung / leaf n-of-m) because bindings
fail and leaves shuffle. On a 500-leaf volume: ~6% overhead.

Hash chain (Merkle, forward): the Plate prints the CRC-32 of Listing
One's text; Listing One's payload ends with the CRC of the coarse
payload; the coarse payload contains the hash of the mid payload; the mid
payload contains the hash of every archive volume. **Hash domains are
declared on the Plate: hashes cover payload bytes only** (a page cannot
contain the hash of itself — the red-team's fixed-point catch). The Plate
is certified by nothing but its worked examples and cross-copy
comparison, and says so. SHA-256 enters only at R3 (as printed reference
code + FIPS vectors); below that, CRC-32 only — corruption down there is
accident, not adversary.

## R0 — THE PLATE (2 leaves, duplicated front + back matter)

Pure typography, ~72 chars x 63 lines/leaf (~4.5 KB text-equivalent
each). Ordered: promise, then proof, then conventions — the red-team's
bluntest finding is that the SOCIAL failure is fatal: a finder who cannot
see within minutes what is inside and that the method works shelves the
book as decoration.

1. **Promise:** what the archive contains and how many bytes; the effort
   ladder stated plainly ("one hour: 64 marks by pencil; one day: a
   200-line program; one week: everything; fragments the size of a
   fingernail carry their own address").
2. **Proof:** an 8x8 golden block at 1 mm modules, decoded step by step
   beside it (marks -> binary -> numbers -> letters). Hand-reproducible
   in minutes; doubles as the imaging self-test ("if this block fails,
   fix the light, not the code" — specular toner gloss under flash reads
   as white).
3. **Grounding, in dependency order:** the 100 mm scale bar defines
   length (print 2362 dots at 600 dpi and STATE the true 99.992 mm —
   the bar is the unit's definition; ratios over absolutes, paper
   breathes +-0.5%). A counting primer grounds numerals — rows of dots
   beside each digit glyph, positional notation by worked grouping, hex
   as sixteen rows — because the bar grounds length and *nothing else
   grounds "7"*. Then the 128-entry ASCII table: glyph, decimal, and an
   8-mark binary strip per row (triple self-stating; slashed zeros,
   distinct case forms), closed by a printed digits-bearing pangram
   whose CRC is given, so glyph->byte is testable end-to-end.
4. **Conventions:** ink=1 (pictogram), raster arrows drawn ALONG the
   golden block's read path, MSB-first bytes — plus the 16-hypothesis
   trial table (8 dihedral orientations x 2 polarities) as pictograms:
   bit-sense and mirror ambiguity resolved by mechanical trial, no
   language needed.
5. **CRC-32, fully specified:** poly 0x04C11DB7 (reflected form
   0xEDB88320), init 0xFFFFFFFF, final xor 0xFFFFFFFF; a complete
   bit-level trace of a 2-byte example (every shift shown), the 256-entry
   table in hex, three vectors including crc32("123456789") = 0xCBF43926.
   Table AND trace: a wrong implementation gets a gradient, not a red
   light.
6. **THE KEY:** the volume seed in hex (e016: 24 bytes,
   `paper-store/exp016-arch3`), on both Plate copies and nowhere else,
   with the sentence explaining that the dense pages are noise without
   it — deliberately — and that this line is the price.
7. **Custodial directive:** dry, dark, cool; no adhesive repairs; COPY
   this volume and verify the copy against the golden block. The book
   crosses ten centuries as ~5 generations of copies, not as one miracle
   of paper. Damage advisory (3 lines): mirror ghosts are facing-page
   transfer — decode the sharp-edged original; browned paper: carbon
   marks reappear under raking/transmitted/IR light; corner targets are
   redundant, any 2 of 4 suffice.

## R1 — LISTING ONE (3 leaves, the program you type)

~200 lines (~8 KB) in OCR-B, one statement per line, in a deliberately
tiny Python subset: NO imports at all, no floats, no negative modulo,
explicit while loops — written so it degrades into executable pseudocode
if Python-the-language is lost (a printed 12-rule semantics annex covers
indent-as-block, integer division, case sensitivity, evaluation order).

The proven channel is COMPUTE!'s MLX (1983-88): humans move kilobytes
through their fingers reliably IFF errors are caught per line. Margin
per line: line number + **hand-computable position-weighted checksum**
(sum of i x codepoint mod 997 — position-weighted because MLX's first,
position-insensitive checksum passed transpositions and had to be
revised), with one line hand-worked on the Plate. This breaks the
circularity the red-team caught: if margin checksums were CRC-32, the
finder would verify their typed CRC implementation with checksums only
that implementation can check. CRC-32 certifies the whole file only
after the CRC routine itself passes the Plate's printed trace. Python's
invisible-whitespace hazard: the **indent depth is printed as a leading
digit on every line** — whitespace transcribed as data. Honest typing
estimate, printed: 4-6 hours.

What it does (~170 lines, budget-audited): read a CONSTRAINED PGM P5
(maxval 255, no comments, single separators; complete 4x4 example
printed as hex beside its picture — constrain, don't describe); find
2-of-4 corner bullseyes; affine from 3 corners (full homography blows
the budget — the coarse pages instead print the requirement "press flat
under glass"); re-center every row between the two vertical perimeter
clock tracks (~20 lines — this is what actually absorbs warp and lens
distortion); global threshold from the bullseyes' own ink/paper
samples; nearest-neighbor sampling; majority-of-3; CRC per block; emit
bytes.

## R2 — COARSE pages (5 leaves)

Module = 12x12 engine dots = 0.508 mm — sized against OUR measured
morphology (the luxury no other deep-time project had): 12x above
isolated-dot death, 4x above the <3-dot white-closure floor, edge gain
at 3% of module width (MEASURED floors, exp 001). Grid 360x520; furniture
= 4 bullseyes (13x13) + perimeter clock track + 1 header row = 2,792
modules; 3x repetition with the three copies in different page thirds
(damage is spatially coherent across neighboring leaves AND page
positions — duplicates get position TRANSPOSITION and maximal leaf
separation); 64-byte blocks + CRC-32. **Net 7,168 B/page ~= 7.0 KiB**
(honest accounting; the first sketch's ~8 was 15% optimistic). At 12-dot
modules the error regime is damage-dominated, not channel-dominated, so
majority+CRC genuinely suffices — no correcting code needed at this rung.

Capture: 2 samples/module = 100 samples/inch = a 0.75-megapixel
photograph of the page — any camera that will ever exist again; a
50-spi-class device shoots 2x2 overlapping quarters. **Advertised
zero-camera floor** (one printed sentence): 0.508 mm sits ~7x above
naked-eye acuity; ruled overlay + ~1.5 bit/s sustained = ~12 h/page,
~55-60 h for the rung (ESTIMATE) — brutal, finite, and its entire job is
to exist. Cross-copy visual comparison stands in for CRC until any
computer exists.

Payload (~30 KB over 5 leaves): `mid_decoder.py` (~25 KB, **pure Python
— numpy has not crossed yet**; the red-team killed "numpy allowed" here
as a monotone-law violation), the mid-format one-page spec, the ASCII
table repeated as bytes (printed self-check), the hash of R3's payload.

## R3 — MID pages (16-20 leaves)

Cell = 6x6 dots = 0.254 mm (c6 — 2x the proven c3 cell; design-point raw
BER 0.2-0.5% ESTIMATE, bracketed by MEASURED c4 0.4-1.4% and c6 ~0-0.35%,
exps 007.6/007.1). Grid 720x1040, 8-cell frame -> 704x1024 data cells =
90,112 raw B/page. Overt border + bullseyes + tick marks every 32 cells:
+-0.5% hygroexpansion is 3.6 cells cumulative across 720 — per-tick-span
resampling is MANDATORY, a global affine cannot hold this pitch
(MEASURED distortion class, exp 001/002.0b).

**The forced correction (the one real trap in the first sketch):
CRC-only + duplication is dead on arrival at this pitch.** At 0.2% raw
BER a 128-byte CRC block survives with p = 0.998^1024 ~= 13% -> 87%
per-copy block failure. A correcting code is REQUIRED: interleaved
RS(255,223) t=16 over GF(256), depth-8 byte interleave (foxing bursts),
4-byte CRC inside each codeword (219 user + 4 CRC + 32 parity). At the
design BER: lambda ~= 4.05 byte-errors/codeword, P(>16) ~= 1.3e-6 —
clean. An RS decoder (GF tables + Berlekamp-Massey + Chien + Forney) is
~200 lines inside mid_decoder's 25 KB budget, and stays monotone: it
arrives as printed source, decoded by a rung that needed only majority
votes. 353 codewords/page -> 77,307 user B single-copy; every block on 2
well-separated leaves -> **net 38,653 B/page ~= 37.7 KiB**. Payload
~600-650 KB -> 16-20 leaves (duplicate only the decoder-critical core if
20 offends: ~14 leaves). Each R3 leaf carries a resolution/moire
self-test wedge with a printed pass rule — a photographed (not scanned)
page can sit at a silent alias floor, exactly our pn1200 24-31%
experience (MEASURED, 007.1/007.6).

**R3 payload manifest** (what must cross; sizes MEASURED 2026-07-10):
- the complete src/paperholo tree + DESIGN/PILOTS/FEC/FOUNTAIN/LAYERS
  docs = 535,386 bytes (19 source files + 5 docs, `wc -c`);
- the pure-Python keystream reference + PRINTED golden vectors (first
  256 keystream bits for (volume seed, plane K, page 0); the BLAKE2b
  digest of the seed; one pilot tile's codeword before/after scramble;
  one decoded LDPC tile) — so a rebuilt stack is testable stage by
  stage against ink;
- vendored pure-Python fallbacks for the scipy calls in
  acquire/place/ldpc (fftconvolve, ndimage labeling, sparse matvec —
  ~50 lines each) + an environment dossier (exact versions, IEEE-754
  binary64 stated);
- the format registry WITH seeds (formats.py rows — the seeds' first
  legal machine-readable appearance: the full source has now crossed);
- the measured-channel dossier: what 21st-century laser engines did to
  dots (isolated-dot death, white closure, edge gain, scanner comb,
  hygroexpansion). The finder decodes through OUR channel; our channel
  facts are part of the format.

After R3 the finder runs acquire-v2 blind, the pilots hand them absolute
addresses, the fountain absorbs every leaf the centuries ate, and the
chain closes byte-exact — the same 361,833-byte certification of run
016.2, executed a millennium late.

## The irreducible format kernel (what R3 must convey; audited + spot-verified)

Facts a from-scratch decoder cannot re-derive (format axis; everything
decoder-axis — orientation search, warp tracking, detection, LLRs — is
re-derivable and needs nothing printed; the BCH gate arbitrates
hypotheses exactly as designed):

- **Master PRNG** (modulation.py:19-26): BLAKE2b-128(seed+label) ->
  LE int -> Philox key -> Generator; PLUS numpy's per-dtype bounded-draw
  consumption (uint8 draws buffered per 64-bit word; int64 not). The
  payload keystream is the one dtype=np.uint8 draw; label =
  bytes([plane]) + page_le32, plane index = 'CMYK'.index -> K=3.
- **Pilot sites p60b6** (pilots.py): label b"pilot-sites-v2" (SHARED by
  v3 — no v3 site label, contract), off = integers(0,6,(10,10,2)) at
  default dtype; site raster s = by*10+bx; period 60, block 6, 100
  sites/tile, density 1/36.
- **Pilot values**: BCH codeword XOR ks_P, label b"pilot-values-v{2,3}"
  + b"/" + plane letter; the v3 label IS the format identity (no
  version/plane fields printed — R5 implicit signaling; wrong hypothesis
  = coin flips, MEASURED 0/200k FA).
- **BCH v3**: GF(2^7) prim poly 0x89, n=127 k=50 t=13, roots
  alpha^1..26, shorten 27 -> (100,23), d>=27, systematic (parity
  x^0..x^76, message x^77..x^99), bit i = coeff of x^i; g(x) DERIVED,
  not stored. v2 = (127,64,t=10) -> (100,37), e011 only (never printed).
- **v3 message**: 23 bits MSB-first = [18-bit flat counter][5 zero pads,
  reject gate]; c = page*tiles_per_page + ty*tiles_x + tx; tile geometry
  (tiles_x, tiles_per_page) is a format-descriptor constant, NOT
  recoverable from a fragment.
- **Composition** (compose.py): cell = cell_dots^2 solid dots (kron),
  ink=1; field top-left (230,178) dots on the A4 600-dpi grid (not
  load-bearing for decode — pilots give absolute addresses); payload bit
  i <-> i-th non-pilot cell in C-order raster, XOR keystream at ABSOLUTE
  cell coords. Formats: kcell-c3 (2220,1500), kcell-c2 (3300,2220).
- **LDPC** (ldpc.py, normative docstring): e-IRA QC, n=4096, Z=64,
  derived deterministically from seed b"ldpc-v1/<rate_id>" + label
  b"eira-H/restart<R>" — volume-seed-INDEPENDENT public constants;
  Fisher-Yates row perm + greedy per-column draw (2 draws/attempt, every
  rejected attempt still consumed its draws), tap-gap/4-cycle/row-load
  rules, heavy columns first (0.30, deg 10/8/6), dual-diagonal
  accumulator, I(s)[a,b]=1 iff b=(a+s)%Z. Ladder k = {2240, 2560, 2880,
  3200, 3520}. Tile framing: 64x64 cells incl. partial edge tiles;
  shortened slot = off-page or pilot site; shorten-map position rule
  (descending {k-1..} for shortened, ascending complement for
  transmitted); CRC-32 = zlib.crc32 over MSB-first packed payload,
  emitted 32 bits MSB-first.
- **Fountain** (fountain.py): symbol = interior tile's first S user
  bits (S = min interior cap); geometric ESI t = page*n_interior +
  local, block = t mod n_blocks, i = t // n_blocks; source rows = unit
  vectors, repair row = integers(0,2,K_b) at default dtype, label
  b"fountain-v1/row/" + block_le32 + i_le32 from the VOLUME seed;
  bytes<->bits via MSB-first unpackbits.
- **Endianness rules**: integers inside PRNG labels LE; bit-packing
  MSB-first; BCH polynomial domain LSB-first (bit i = x^i); LDPC restart
  counter decimal ASCII. A wrong endianness anywhere forks a BLAKE2b
  digest and fails silently and totally.
- **Volume descriptor**: (n_pages, data_len_bytes, seed, ldpc_rate_id,
  compose_spec). Never on the data pages. THE PREFACE IS ITS HOME.

## Deep-time precedents (what each contributes; web-verified 2026-07-10)

- **Long Now Rosetta Disk**: the magnification gradient IS the
  instruction manual — each readability rung physically points at the
  next. Our ladder is its digital descendant.
- **GitHub Arctic Code Vault**: spec + retrieval-software source ride
  every reel in human-readable frames — right idea; thin bridge (no
  graded rung between readable spec and dense frames). Our R1/R2 are
  that bridge.
- **Westinghouse 1939 Book of Record**: replicate the KEY wider than
  the payload (3,000+ library copies); treat natural language as a
  decaying channel. Our Plate duplication + custodial recopy directive.
- **Crypt of Civilization**: shipped physical readers (and a language
  teaching machine) — machines seize; ship the machine as information.
  Our R1 is the reader, as text.
- **Voyager record cover**: units from physical invariants + the
  first-decode-is-a-circle known-answer test. Our scale bar + golden
  blocks at every rung.
- **Sandia/WIPP markers (SAND92-1382)**: graded message levels I-IV,
  each complete at its own complexity — the rhetoric inverted (they
  repel, we invite).
- **Memory of Mankind**: separate the pointer from the payload;
  replicate the pointer cheaply (ceramic tokens). Our Plate = the token.
- **Cauzin Softstrip**: a dead 1980s paper barcode was decoded in 2021
  from flatbed scans BECAUSE the printed format documentation survived —
  the direct existence proof for this whole document.
- **COMPUTE!'s MLX**: kilobytes through human fingers work IFF per-line
  checksums with immediate feedback; first-version checksum passed
  transpositions (fixed) — hence our position-weighted sum.
- **KEO** (never launched): minimize the technology cliff at every rung;
  and deep-time projects die of not shipping far more often than of
  media decay. v0.1 frozen now beats v1.0 never.

## Substrate honesty

The code survives 1000 years; office paper survives ~100-200 (acid
hydrolysis). Our e016 sheet would not make the trip. A real deep-time
volume is ISO 11108 cotton-rag permanent paper (verify toner fusing on
rag stock before trusting it — one-variable hardware probe if ever
needed), and the ACTUAL 1000-year mechanism is the Plate's recopy
directive: ~5 custodial generations of verified copies, not one miracle
of paper. Fused carbon toner outlives the sheet it sits on; the bootstrap
rungs, K-only and coarse, are the most archival objects in the volume.

## Repo residue (action items, all zero-print)

1. **Keystream printable-spec** — reference + tests + golden vectors:
   task spawned 2026-07-10 (running in a separate session). AES-CTR swap
   = format-axis decision, OPEN (modulation.py:9 TODO).
2. **Volume-descriptor doctrine**: any real archival deployment needs
   the descriptor (seed included) as a designed overt key sheet — a
   DESIGN.md §5/§9 amendment candidate, alongside the R3 deep-time
   inversion note.
3. **scipy imports in acquire/place/ldpc** are quiet bootstrap debt;
   same instinct that kept torch out of the sim. Low priority; note only.
4. **This document is the printable-record skeleton**: if a PREFACE-1
   sheet is ever built, its gen_/analyze_ pair starts from the R0-R3
   specs above (R2/R3 geometries are printable today on the M281 —
   12-dot and 6-dot features are deep inside the measured envelope).

## Appendix A — red-team failure modes (condensed; severity, countermeasure)

| # | Scenario | Sev | Countermeasure |
|---|---|---|---|
| 1 | Acid paper dies in 100-200 y | FATAL | ISO 11108 rag stock + printed recopy directive (LOCKSS by custodians) |
| 2 | Finder shelves the book (no visible promise/proof) | FATAL | Plate p.1 = inventory + 10-minute golden-block demo + effort ladder |
| 3 | Keystream unreproducible on drifted numpy | FATAL | pure-Python reference in R3 payload + printed golden vectors (see finding) |
| 4 | numpy/scipy semantics drift ("they know Python" is approximate) | major | mid_decoder pure-Python; vendored scipy fallbacks; env dossier; printed intermediate vectors |
| 5 | Language death (1000 y ~= Old English gap) | major | 4-6 parallel languages + pictorial primer carries the load-bearing claims language-free |
| 6 | Nothing grounds numerals (bar grounds length, not "7") | major | counting-dots primer before first numeral use; hex as base-16 extension |
| 7 | CRC-32 variant hell (~16 plausible knob settings) | major | bit-level trace + 256-entry table + 3 vectors incl. 0xCBF43926 + stored-byte-order shown in place |
| 8 | Python semantics unspecified below R3 | major | 12-rule semantics annex at R1; listing avoids every subtle construct; imports BANNED |
| 9 | Per-line CRC = circular; 200 unchecked lines = 4-10 bad | major | hand-computable weighted sum mod 997; indent depth printed as a digit; honest 4-6 h estimate |
| 10 | ASCII table self-confusables (O/0, l/1, case) | major | slashed-zero OCR face; binary strip per glyph; pangram-with-digits + printed CRC |
| 11 | Gutter/rebinding eats margins | major | >=20 mm gutter, >=10 mm trim, nothing load-bearing in outer 10 mm |
| 12 | Water/foxing damage coherent across leaves AND positions | major | duplicate with position transposition + front/back-matter separation |
| 13 | Binding fails, leaves shuffle across volumes | major | overt per-leaf header (volume/rung/n-of-m); block index inside CRC-protected payload |
| 14 | Plate has no FEC | major | print twice per volume + every-volume replication; cross-copy majority |
| 15 | Self-hash fixed point ("rung prints its own hash") | major | hash domains = payload bytes only; Plate certified by worked examples, stated |
| 16 | SHA-256 needed before it can be implemented | major | CRC-32 only through R2; SHA-256 enters at R3 as printed reference + FIPS vectors |
| 17 | Toner blocking/transfer ghosts onto facing pages | major | blank versos; "mirror ghost" advisory line |
| 18 | Photograph (not scan) -> demosaic/JPEG moire alias floor at R3 | major | moire wedge + pass rule on every R3 leaf (our pn1200 24-31% floor is the template) |
| 19 | Bit-sense inversion / mirror scan / RTL reading order | minor | 16-pictogram trial table (8 dihedral x 2 polarity); raster arrows on the golden block |
| 20 | IR-readability overclaim (charring kills carbon contrast) | minor | demote to advisory; raking + transmitted light listed first; no rung BUDGETS on IR |
| 21 | Specular toner gloss under flash reads white | minor | imaging pictogram (diffuse light, no flash); golden block = imaging self-test |
| 22 | PGM P5 edge cases (maxval>255, comments, whitespace) | minor | constrained dialect mandated + 4x4 hex example; listing rejects deviations |
| 23 | Library stamps/tape land on corners and margins | minor | any-2-of-4 bullseye rule; no-marking pictogram; one corner is sacrificial |

## Appendix B — circularity audit (all resolved in v0.1)

1. Self-hash fixed point -> hash domains declared (A15).
2. Numeral grounding -> counting primer inside R0, before first use (A6).
3. Per-line CRC bootstrap -> hand-computable weighted sum; CRC validated
   against the Plate trace first (A9).
4. Python semantics at R1 -> annex + subset discipline + imports banned (A8).
5. numpy at R2 -> mid_decoder pure-Python; the monotone law extended to
   "no external library before its spec/source has crossed" (A4).
6. scipy at R3 -> vendored pure-Python fallbacks in the payload (A4).
7. Keystream spec outside the tree -> the headline finding; reference +
   printed vectors (A3).
8. IEEE-754/FFT conventions -> stated in the env dossier + printed
   intermediate vectors (soft circularity; threshold-tolerant pipeline).
9. Image acquisition presumed -> the R2 loupe fallback stated in print
   converts a technology dependency into a labor cost.

Monotone law otherwise verified end to end: first seed use is decoding
the archive proper, after the registry crosses; compression is absent
below R3; the forward hash chain is authorable (freeze all payloads
before printing anything).

## Appendix C — rung arithmetic (honest numbers)

Usable area 182x277 mm (A4, 10 mm margins, 18 mm gutter). R2: 360x520 =
187,200 modules - 2,792 furniture = 184,408; /3 = 61,469 bits; blocks
64+4 CRC -> 112 x 64 B = 7,168 B/page. 30 KB payload -> 5 leaves. R3:
704x1024 = 720,896 bits = 90,112 B raw; 353 x RS(255,223) -> 77,307 user
B single-copy; x2 duplication -> 38,653 B/page. 535 KB measured kernel +
~100 KB additions -> 16-20 leaves (14 with core-only duplication).
Capture: R2 = 0.75 MP/page (2 samples/module); R3 = 3.0 MP/page (2
px/cell). Loupe floor: 61,469 bits at 1.5 bit/s ~= 11.4 h/page. Archive
endpoint for contrast: e016 MEASURED 361,833 B certified = 55.1 b/mm2.
All ESTIMATE except where labeled MEASURED.
