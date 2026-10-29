# CMY-DESIGN — the cmy family: two label-bit streams over the four-state single-toner alphabet (v0.3, 2026-10-11)

**Status: DESIGN of record — the GENERATOR BUILT and sim-qualified 2026-10-11 (W0 7bad672c, W1 128ed3cb, W2a 6926f6ef, §13), NOT printed; the receiver and analyzer sides unbuilt.** Every row
this document names is PROVISIONAL by construction (HOLO-DESIGN F14),
catalog-only, absent from FORMAT_ROWS, profiles, fossils and default
discovery, and reached only by an explicit `--format` (the p-axis
precedent). Nothing here is promoted or moves a normative document:
FORMAT-SPACE §19, HOLO-DESIGN v0.27 §13.38 and PRINTED-FORMAT §12.5 land
WITH THE BUILD (§13), the CMY8-POOLED-FOUNTAIN precedent.

**Provenance.** Branch `ccr-05e553a8-ciem1u`, rebased onto main
`4240a3c`, where the evidence branch `m281-screen-routes` is MERGED: every
source is a main path. Measurements of record:
`experiments/041-m281-screen-routes/results/measurements.json` and
`experiments/042-altalink-cell-encodings/results/measurements.json`
(`scale` → `<sheet>` → `bands`, a LIST selected by `b["name"]`; e041's
alphabet tokens carry route suffixes, `C-solid`, `M-solid`, normalized
before a label applies). Logs are cited by SECTION (e041 §041.5i, e042
§042.4, `docs/M281-COLOUR-2026-10-05.md` §6A). The per-plane d' values and
the solid-bar RGB readings (§2.5, §2.9, §7b) were **measured 2026-10-05,
recorded in the 2026-10-06 refutation, not in the committed extract**.
The names `cmyw`, `cmy4`, `cmy4-solid(C)` are RETIRED for `cmy` (RULED).

**v0.2** folds the furniture redesign (words '1' = C, '0' ∈ {W, Y};
M-heavy dust — supersedes D7, §2.5), the calibration law and cold-start
contract (supersede v0.1 §7c's calibration text and R11's second half,
§2.7, §7c), the two-channel structure (§2.9), the AltaLink X10/X11 read
(e042 §042.4), two external reviews (the branch author's, 2026-10-07; GPT
"Astra"'s, 2026-10-09) and a three-lens review of the v0.2 draft
(format/coding, receiver inference, analyzer/ops/qualification): each
finding applied where its evidence re-verified, otherwise declined or put
to the owner (§12). The rulings are recorded in place as the owner takes
them (R1–R20 and the analyzer's RA-1..RA-7 dispositioned, 2026-10-09/10,
§12); R11 (2026-10-10) REPLACED v0.2's
lo-first chain with hi-first, the cmy gate "A3's single held-out
improvement" with cmy8's three-way gate as it stands, "prior-barrier"
cells with certified cells read at fire time, and "the conditional maps
arrive at ≥ 2 tiles" with A4b's floors and the measurement (§2.5, §2.7,
§7c, §14.1).

**v0.3 (2026-10-11)** records the owner's rulings at the generator
build's opening review (§12). R22: the uneven first c2 probe stays on P1
and its close is proven before toner through holo3's grouped fountain
decoder driven from generator-built rows — the decoder that qualified
cmy8's column groups — so §11's print edge stands. R21: `--printer` is
REPURPOSED as the emission ENGINE selector and the legacy printer-derived
generation door (`--coding`/`--profile` × printer geometry, `make_spec`,
`hp-m281-ink`) retires onto the `L:` fossil rows, which already carry
their placement. R23: the emission is K's construct in colour — three
single-toner imagemasks at the engine's measured solid device-RGB values,
plain PostScript, no PJL, no HP operators, no palette, no bands; the
engine record is cmy8's shape (the route it honours + the three values);
§2.8 rewritten to it. R3 AMENDED: the dust balances each TILE's actual
word supply, a pure function of seed, counter and p, not expected
constants (§2.5). The same review corrected §2.4 and §4 to R4 as ruled,
added R4's probe row to §3.3, corrected the measured job-size range
(31.6–33.0 MB, S15 included), and the generator plan was rewritten
compact (v0.2) at the owner's ask. Nothing else moved.

**Decision map.** D1 → §2.0; D2 → §2.1; D3–D4 → §2.2; D5, D9 → §2.3;
D6 → §2.4; D7 (superseded) → §2.5; D8 → §2.6; D10 → §2.7; D11 → §2.8;
two-channel → §2.9; D20 → §3; D12 → §5; D13 → §6; D14 → §7; D15 → §8;
D18 → §9; D17 → §10; D19 → §11; D16 → §12; D21 → §13; D22 → §14.

---

## 0. The ask

The owner, 2026-10-06: "Inspect the m281 branch, and figure out what
c2-cmyw (also named cmy4 in places) is about, and how it should work with
planes and rungs. Then start your own branch and put down a design (we'll
call the encoding cmy from now on) and how generator and receiver and
analyzer need to be changed on a high level." And 2026-10-09: "how was/is
this done in cmy8?" (§7c), "is C actually the most robust cell … or is M
more robust?" (§2.5: C, narrowly; M a close second), and a deep
self-review driving to three workplans — generator, receiver, analyzer —
separate documents of record that cite this design. "Planes and rungs"
is §4: THREE toner planes, TWO certified streams, each its own rung.

## 1. What cmy is, and why

### 1.1 The alphabet

The four-state single-toner alphabet {W, C, M, Y}: every cell is white or
exactly one toner laid solid; no overlap state, no K. 2 raw bits per cell
— c2 279 raw b/mm², c3 124 (M281-COLOUR §5); three quarters of the cells
under ink. One square pitch: e042 §042.6's rectangular cells are out of
scope.

### 1.2 Why it exists — the M281's screener

The HP M281 is a 600×8 contone engine with its screen in the video path:
0 and 255 pass, anything the colour path moves off them is screened
(M281-COLOUR §1). The record READS the screener (three sheets, not a
mechanism; M281-COLOUR §2, e041 §041.5m) as a page-fixed column-region
switch spending a budget of COMPOSITE pixels (overlaps or K), 270–660
%·mm; no page whose every pixel is W or one solid toner has been
screened; region edges and budget form are unmeasured (M281-COLOUR §7);
the colour-count trigger is REFUTED (M281-COLOUR §6B'). So cmy is the one
SOLID-CELL colour alphabet the M281 lays unscreened from a whole page —
dot-mixed cmy8/cmy7 pages are unscreened too (S16 T2, S17 U1/U2) and
outrank c3-cmy (§9). The M281's cmy bands show no region structure and
no 165/188 lpi lattice, only a weak 212 lpi yellow screen on S14's
corner-cyan bands (e041 §041.5i, §041.5m); the AltaLink's sit at the
floor on every lattice (e042 §042.4).

### 1.3 What was measured (page scale, context-free, single sheets — NO promotion)

| pitch | sheet / band | state error | discernible | source |
|---|---|---|---|---|
| c3 | S14 A1 (corner cyan, matching default) | 0.06 % (Y 2.5 % best-threshold, C 0.00, M 0.01) | 1.991 b/cell = 123.5 b/mm² | e041 §041.5i |
| c3 | S14 B1 (matching off) / B2 (24 abutting tiles) | 0.09 % / 0.06 % | 123.3 / 123.5 | e041 §041.5i |
| c3 | S15 R8 (production palette, Smooth) | 0.33 % (single pose 3.3 %) | 121.8 | e041 §041.5k |
| c3 | S16 T3 / T11 / T14 | 0.06 / 0.06 / 0.12 % | 123.5 / 123.5 / 123.1 | e041 §041.5m |
| c3 | S17 U13 (4800 and 2400) | 0.08 % / 0.08 % | 123.3 | e041 §041.5o, §041.5p |
| c3 | **X11 (AltaLink, DeviceCMYK composite)** | 0.05 % | 1.994 b/cell = 123.6 | e042 §042.4 |
| c2 | S14 B3 (corner cyan, Detail, matching OFF) | 2.82 % | 1.791 b/cell = 249.8 (band MI; the loo confusion gives 1.797) | e041 §041.5i |
| c2 | S15 R9 (production palette, Detail) | 3.86 % (single pose 7.0 %) | 241.9 | e041 §041.5k |
| c2 | S16 T12 (production, Detail) | 4.00 % | 240.3 | e041 §041.5m |
| c2 | S17 U12 (production, Detail) | 6.43 % (4800) / 6.54 % (2400) | 1.592 b/cell = 222 | e041 §041.5o, §041.5p |
| c2 | **X10 (AltaLink, DeviceCMYK composite)** | 2.85 % (W→Y/M/C 2.8/2.2/2.1 %, inks 97.9–98.9 %; plane hard error C 1.4 / M 1.5 / Y 9.5 %) | 1.776 b/cell = 247.7 | e042 §042.4 |

c2 tracks the print's |Y−C| registration (0.49 / 0.67 / 1.13 / 2.35
dots on B3 / R9 / T12 / U12, monotone, e041 §041.5p); X10 at ~0.6 dot
reads 2.85 %, a fifth print on a second engine, on the same line (e042
§042.4). Scan mode changes no cell state FOR THIS CLASSIFIER (§9). c2
errors are one-sided — white reads a neighbour's colour (B3 W→Y 4.33 %,
U12 9.0 %) — and need per-plane poses (R8 0.33 vs 3.3 % single-pose, R9
3.86 vs 7.0 %). The classifier is context-free nearest-mean with
SUPERVISED poses and means, no bound on a blind receiver either way
(M281-COLOUR §7); the AltaLink's c2-cmy8 close at 308.6 b/mm² sits ABOVE
that band's 301 "discernible" (e042 §042.4).

### 1.4 Vocabulary (used exactly, everywhere below)

**PLANE** — a physical toner (C, M, Y) with its own registration page
field, photometry and failure physics. **STREAM** — a logical certified
unit: one LDPC codeword per tile, one rung, one fountain quota /
column-group share, its own certificates. **STATE** — the printed cell
value. In cmy8 stream == plane; in cmy two streams, three planes, four
states. The stack silently assumes stream == plane (§6–§8 list the
sites); separating them is the build's central job.

### 1.5 The numbering hazard

holo numbers states by presence bits, `C + 2M + 4Y`: W=0 C=1 M=2 CM=3 Y=4
CY=5 MY=6 CMY=7 (`src/holo/core/channel.py:33-49`). cmy is the SUBSET
{0, 1, 2, 4}, not a prefix (`STATE_NAMES[:4]` = (W, C, M, CM),
characterize's CM4, `src/holo/characterize/model.py:249-256`). Every
e041/e042 instrument numbers W=0 C=1 M=2 Y=3: index 3 is Y there and CM
in holo. The label bits (§2.2) are a THIRD encoding: C is id 1, label 11.

## 2. The design — format

### 2.0 Name (D1)

Family token `cmy` — `Family.CMY = "cmy"` in BOTH enums
(`src/holo/format/profiles.py:32-41`; `src/holo/receiver/format/identity.py:13-16`;
`is` does not cross the trees). RULED. Why the name (owner, 2026-10-08:
"since 'w' is in every alphabet, and cmy4 represents cmyw, using the name
cmy (in contrast to cmy8, and the to-be rewritten cmy7) appears to be the
best choice"): read unsuffixed, `cmy` is the three inks alone, beside
cmy8 (every combination) and cmy7 (every combination but one). Caveats: it breaks the cmy7/cmy8
state-count suffix convention; "CMY" already names the three-plane
family; `KCMY4`/`kcmy4` name OTHER alphabets
(`src/holo/characterize/model.py:272-278`, e025, a PCL mode), `CM4` is
{W,C,M,CM}. Seed-frozen forever (FORMAT-SPACE §6 law 1), no display alias;
the parse is exact-match (`src/holo/format/lattice.py:162`) and no
substring dispatch on "cmy" exists in `src/` or `analyzer/`. `cmyw`,
`cmy4` and `cmy4-solid(C)` are retired; `cmyw` as an alias is rejected
(R13). **Recorded, not cmy's problem (R13 CLOSED 2026-10-10,
corrected):** the seven-state erasure row (REDUCED-ALPHABET-ERASURE-ROWS)
is future exploration (§9.1); its spelling is decided when it is picked
up. The fossil catalogue does NOT block reuse of `cmy7` (v0.2 said it
did; withdrawn): the pack7 fossils are v1-namespace seeds
(`holo/v1/c2-cmy7-p120-v0/…`, `holo/v1/c3-cmy7-p120-v0/…`), byte-matched
and never parsed (`src/holo/format/fossils.py:7-9, :87, :102-106`), and a
`holo/v2/` seed cannot collide with them. What blocks `cmy7-…-v2` is the
grammar and the parsers: only v1 is defined
(`src/holo/format/lattice.py:67`; receiver `identity.py:121`), both
parsers refuse a cmy7 rung token in every generation (`lattice.py:192-195`;
receiver `identity.py:123-124, :398-401`), and FORMAT-SPACE §5 describes a
cmy7 generation as a re-baked pack7 bank, which the erasure row is not.

### 2.1 State space and alphabet (D2)

The physical state space stays the presence-bit numbering; cmy's alphabet
is `state_ids = (0, 1, 2, 4)`. The `CodecProfile` prefix law
(`src/holo/format/profiles.py:100-108`: a non-K alphabet must equal
`STATE_NAMES[:n]`) and the word/dust checks `in range(len(state_names))`
(`:109-111`, `:121-123`) become an explicit law over a NEW `state_ids`
field (only `state_names` exists, `:80`): for colour families an ascending
subset of the presence ids, word/dust states checked by membership; K
keeps ('W', 'K'); cmy7/cmy8 validate identically. Today's checks refuse
Y=4 and admit CM=3. Rejected: a compact 0..3 numbering — index 3 would
read as CM, silently, in every presence-native consumer
(`states_to_planes`, `channel.py:129-134`; the plane GT; the DeviceCMYK
route; context bins; swim; refine.color; `analyzer/frame.py:391`,
`analyzer/unmix.py:249`).

### 2.2 Streams and labelling — and the death map (D3, D4)

**Stream ids (D3).** Two LABEL-BIT streams, `hi` and `lo`; order (hi, lo)
= stream index (0, 1). Not plane letters, so every stream==plane site
fails LOUD (`KeyError` on `analyzer/types.py:24-25`, `analyzer/oracle.py:264`,
`COLOR_STREAM_AUX`). Bank ids `cmy-{hi,lo}-{rung}-p{p}-v1` (FORMAT-SPACE
§6) enter certificate identities (`src/holo/format/fossils.py:64-66,
74-75`); the ORDER fixes the pooled esi, the metadata index and the
dither aux — frozen at first print. Alternative: `a`/`b`. The receiver's
`StreamFact.plane` (`identity.py:127-134`) gets NO None sentinel: numpy
reads `x[:, None]` as a new axis, silently (`tiles.py:516` turns (3976, 3)
into (3976, 1, 3)); a label stream carries `label_index`, `dither_aux`
and a `plane` that RAISES (receiver W0, §7).

**Labelling (D4, format law, frozen table).** hi = [state ∈ {C, M}],
lo = [state ∈ {C, Y}]:

| label (hi, lo) | index (hi<<1)\|lo | state | presence id | inks |
|---|---|---|---|---|
| 00 | 0 | W | 0 | none |
| 01 | 1 | Y | 4 | Y |
| 10 | 2 | M | 2 | M |
| 11 | 3 | C | 1 | C |

"Cyan is white's antipode." (a) *Information.* On S14 B3's `confusion_loo`:
per-bit hard error 1.43 % (hi) / 2.03 % (lo), I(hi) 0.897, I(lo) 0.863,
BICM 1.760 b/cell vs the symbol MI 1.797 (M281-COLOUR §6A; I(bit) =
I(label bit; 4-ary hard decision)). W→Y flips lo only — why lo is the
weaker stream. B3 printed the corner cyan, SCREENED on the sheet's
PostScript bars, costless inside the random-cell bands (e041 §041.5i).
Across the four M281 c2 prints the C- and M-antipodes trade places within
0.003–0.020 b/cell; the Y antipode is worst on every print (B3 1.721 …
U12 1.472). **X10 repeats the ranking:** MI 1.782, BICM C-antipode 1.740,
M 1.739, Y 1.729, I(hi) 0.876 / I(lo) 0.865; X11 MI 1.994, BICM 1.993.
The invariant is "W and Y differ in ONE bit"; C vs M is noise-level; at
c3 the labelling is irrelevant. Reader arithmetic; the derivation is owed
as an artefact (§13).

(b) *Dead-toner mapping* — the deciding ground. A dead toner merges its
state into W:

| dead plane | merges | hi | lo | verdict |
|---|---|---|---|---|
| Y | Y (01) → W (00) | intact | wrong on the Y quarter (hard) / erased on the hi=0 half (known-dead) | **lo dies, hi survives**; words intact (Y word sites read W = '0') |
| M | M (10) → W (00) | wrong on the M quarter / erased on the lo=0 half | intact | **hi dies, lo survives**; words intact (no M in the word) |
| C | C (11) → W (00) | wrong / erased on the W∪C half | same | **both die — FATAL**, the words' '1' with them |

Half the bits erased exceeds the 1 − R_tx headroom of every frozen rung:
"dies" is literal (inferred). Y is the weakest, most often dead plane in
the record (the M281 weak-Y epoch; the M681's Y dead on two thirds of the
page, e039; sheet J's Y trailing, e035; X10's Y plane 9.5 % against C/M
1.4/1.5 %), and c2's dominant W→Y is Y-to-C misregistration (§1.3).
[2026-10-11: on fresh toner the M281's Y is clean — e043 §043.5: yellow bars
4–11, c3 Y plane error 0.08–0.17 %.] C is the K-quality plane and carries
the words' '1' (§2.5), so the fatal case
costs least there. Pinned by a digest golden like `CMY7_CODEBOOK`
(`tests/holo/test_channel_mapper.py`) AND by G11's document-written spec
vectors, so a wrong table cannot round-trip as common mode.

**Two-stage demap facts.** hi first, then lo given hi (W-vs-Y / C-vs-M):
I(lo|hi) = 0.8995; lo first, then hi (W-vs-M / C-vs-Y): I(hi|lo) =
0.9335 (S14 B3; X10 0.906 / 0.917, the same order). At the 0.07–0.11 gap
the hi-first second reaches only r0775; r0850 needs lo first (the RUNG pairing; the calibration chain is hi-first, R11), whose first
stream (lo, 0.863) fits r0700–r0775 (M281-COLOUR §6A; recomputed). A
conditioned pair sized at r0850 conditions **hi**. Soft, the raw bounded
QDA statistic reads I(hi) 0.935 / I(lo) 0.918 on B3 against these hard
0.897 / 0.863 (§14.3; `measure/cmy_calibration/`, R11).

### 2.3 Codewords and dither (D5, D9)

**One LDPC codeword per stream per tile (D5)**, cmy8's law: mothers
n = 4096, shortening = p, transmitted = 4096 − p, one bit per payload cell
per stream; user bits = k_bits(rung) − p − 32; S = k_bits − p − 33
fountain bits per stream per tile (`src/holo/format/families.py:166-169`).
Each codeword is XORed with its dither; a cell's two dithered bits go
through the label table to the state; the shared `DOMAIN_COLOR_CELL_ORDER`
permutation (stream-independent, as the analyzer's per-cell folds
require, `analyzer/calibrate.py:187-211`) places them.

**Dither (D9).** `DOMAIN_CMY8_DITHER = 13` (`src/holo/core/keystream.py:97`)
with aux = stream ordinal + 1 (hi → 1, lo → 2; hi draws cmy8's C aux under
a seed that spells the family, `descriptor.py:433-435`, receiver
`identity.py:490`), an INTEGER from the stream's index, never a name
lookup in `COLOR_STREAM_AUX` (pinned whole as {main:0, C:1, M:2, Y:3},
`test_h3_format_keystream.py:75-76`, `keystream.py:102-111`; it must not
grow). `cmy8_dither_bits` takes an int (`keystream.py:316-345`; receiver
copy unchecked, `src/holo/receiver/format/keystream.py:210-221`); one
helper per tree, `dither_aux(row, stream_id) = row.stream_ids.index(stream_id)
+ 1`, is bit-identical for cmy8 (`src/holo/format/profiles.py:308-318`), so the by-name
call sites (§6e, §7a) switch with no fork. `fountain_aux = None` (unused
on the pooled path, `src/holo/format/descriptor.py:66-71`; refused by a
pooled `VolumeCode`, `src/holo/core/fountain.py:310-317`). Domain 12
unchanged, domain 9's dust draw byte-identical; no new domain, for the
dither or anywhere (the word-zero keys extend domain 9's u range, R10,
§2.5).

### 2.4 Rungs, grammar and the column-group pairs (D6)

Each stream carries its own rung from the frozen LADDER (r0547 r0550 r0625
r0700 r0775 r0850; `src/holo/core/ldpc/construct.py:69-76`; "keep 547").
Grammar: rung arity 2, `r{hi}x{lo}` in STREAM order, the uniform pair
contracted (`r0850` = r0850x0850) — lawful because contraction is keyed
only on the family's fixed arity (FORMAT-SPACE §6). `families.py:55-61`
contracts; `lattice.py:176-177` / receiver `identity.py:383-384` expand
and need the ×2 CMY case (arity tables `lattice.py:125`,
`identity.py:123-124`). Uneven pairs pool through the n-generic
column-group law unchanged (`src/holo/core/column_groups.py:109-143`;
§3.2).

| canonical (= seed payload) | display |
|---|---|
| `1i200-cmy-r0850-p120-v1@35x24` | `c3-cmy-r0850@35x24` |
| `1i300-cmy-r0700-p120-v1@53x37` | `c2-cmy-r0700@53x37` |
| `1i300-cmy-r0775x0700-p120-v1@53x37` | `c2-cmy-r0775x0700@53x37` |

**First rows (R4, RULED 2026-10-09; §12).** `c3-cmy-r0850@35x24` (the
lossless page, the ladder's cap; every c3 print has I(bit) ≥ 0.97) and,
for c2, the PROBE `c2-cmy-r0775x0700@53x37` (hi at r0775, lo at r0700;
Z 19, 19:17, §3.2) — then up or down by the day's measured I(hi)/I(lo):
`c2-cmy-r0700@53x37` (uniform, Z = 1, tier 3 at q ≤ 1/2, BICM-safe on
FOUR of five prints: lo 0.863 B3, 0.821 R9, 0.8175 T12, 0.865 X10; not
U12 0.746) or the multi-print minimum `c2-cmy-r0700x0625@53x37` (U12's
I(hi) 0.805 / I(lo) 0.746; ladders sit on MULTI-SHEET MINIMA) — rate
algebra on a supervised context-free readout, a first-print start, not a
promotion (e037 standard). The probe is an UNEVEN pair; its pre-toner
round trip is R22's (§11). (v0.2's "owner's pick between r0700 and
r0700x0625" was the recommendation; R4 ruled the probe. Corrected
2026-10-11.)
**Conditioned pairs** (hi r0850 over lo r0700/r0775) are LAWFUL, not
ruled: they wait for G13 (§7e; R5 RULED). **Rate caveat:** R_tx = (k −
120)/3976 here vs the rung study's k/4096. **Ladder cap:** a lossless c3
page is capped at 6,734 fountain bits per site (r0850x0850); a higher
rung is NOT PROMISED (R15 RULED 2026-10-10: cmy uses the six frozen
rungs, scope not a format ceiling) and unstudied (RUNG-LADDER R1/R4 + a
sim gate), and r0850 already
carries a CRC-caught wrong-decode floor of 5 in 30,000 trials
(RUNG-LADDER-STUDY-2026-09-30 §7.4); "~0.95 → ~100 b/mm²" is a wish
(it would need I(bit) > 1.0 at r0850's 0.075-bit gap; not promised, R15).

### 2.5 Furniture: p120, the rotated word, M-heavy dust (D7 — superseded in v0.2)

**The rule.** A dead toner's state merges into W (§2.2), so a word site
may rotate its printed state only within the label class whose dead image
stays in the class: '0' may print W or Y (dead Y reads W, still '0'); '1'
prints C alone (a dead M would read W and flip the bit). v0.1's (W, C)
word left M and Y 5 dust anchors per tile; the rotation puts Y into the
words and frees the dust for M. **p = 120** (100 word sites + 20 dust),
frozen at first spelling (R12, RULED 2026-10-10: the family's input
default beside K 100, CMY7 120, CMY8 120; p always spelled in the id),
other p lawful by cmy8's rule exactly — p > 100, p ≤ min_stream(k_bits)
− 34, p == 100 refused (M appears only in dust, so p100 leaves M no
anchor) — with NO INHERITANCE (FORMAT-SPACE §11.4, §18); p120 shares site POSITIONS and the E022/E023
placement lineage with every printed p120 colour sheet (site seed keyed
on p only, `descriptor.py:270-272`, `identity.py:26-30`,
`P120_SITE_GOLDENS`); values and contrast are not inherited.

**The word.** The K word — BCH(127,50)→(100,23), 18-bit counter + 5
known-zero pads, d = 27, the `PLANE_K` scramble, the site lattice — is
untouched; only the value→state rendering changes: '1' = C, always; '0' =
the site's KEYSTREAM-PRESELECTED state from {W, Y} (R10, RULED
2026-10-10): ONE draw per (tile, site), a pure function of (seed, tile
counter, site index); address bit 0 prints the preselected state, 1
prints cyan. **The draw is on domain 9, not a new domain.** Domain 9
(`DOMAIN_COLOR_DUST_ORDER`: aux 0, major = tile counter, u = index,
v = 0, one 64-bit big-endian sort key from block bytes 0..7,
`src/holo/core/keystream_spec.py:25, 39-40`) is drawn by colour rows only
at u = 0..n_dust − 1 (`color_dust_permutation`, `keystream.py:283-287`;
`pilots.dust_state_values`, `pilots.py:206-245`). A cmy row's word sites
take u = n_dust + site index (site 0..99), one key per site: Y if the
key's TOP BIT (the MSB of block byte 0) is set, W otherwise. The dust
draw stays byte-identical for cmy8 and cmy; the domain's meaning extends
naturally ("the keystream that orders colour furniture states per
tile"); the fifteen-domain table keeps fifteen rows and one meaning per
row, and FORMAT-SPACE §19 records the u-range extension in one sentence
(§13). Word '0' and dust are now ONE idea: a keystream-preselected state
per furniture site, the word bit choosing between it and C (dust = the
no-bit case). n0 ≈ 50 because the 100 word sites carry near-uniform
scrambled bits (the 50 of BCH(127,50) is the dimension, a coincidence);
n0 varies with the counter, its range recorded at generator W2.
**The per-tile Y count is binomial** (mean ≈ 25, sd ≈ 3.5; fewer than 20
of either W or Y in ≈ 12 % of tiles — P(min(W, Y) < 20) ≈ 0.12 at 50
zeros, binomial, inferred): the variance v0.2 rejected a coin per site
for, choosing an EXACT per-tile split (the tile's '0' sites sorted by
key, the first ⌊n0/2⌋ Y) — that split is WITHDRAWN (R10): the per-site
form needs no sort, and a site's state does not depend on the other 99
sites' bits. The variance is ACCEPTED, harmless under the floors that
stand: the marginal calibration floors (6 labels per class, 2 states per
class, 3 per state, `receiver/plugins/color_model.py:22-24`) still clear
in one tile's held-out half at 15 Y (≈ 7 Y, ≈ 16 W); the page field's
anchor floor (`ANCHOR_MIN_SITES` 24, 4 minority,
`receiver/plugins/field_tiers.py:100-101`) is counted per (tile, plane)
template over the window's cells (`furniture_template`, `:255-277`;
`fields_collect.measure_window`, `:399-415`), where a 15-Y tile clears
the minority floor almost four times over; the analyzer's label-supply
arithmetic is in expectation (§8); and under R7 the W/Y choice is
invisible to addressing (both read '0' in R at 0.99 of white).
*Not domain 2* (the v0.2 draft's
mechanism): its frozen address is aux = plane, major = 0, u = site index
(`keystream.py:30, 86`; "identical for every tile (periodic)",
`pilots.py:159-163`), so a draw there is ONE 100-bit vector per row — a
fixed Y-eligible subset in every tile; a counter in its `major` re-means
a frozen field ("Never renumber — add", `keystream.py:83-84`); and "the Y
aux" is 2 under its 'CMYK'.index convention but 3 under `COLOR_STREAM_Y`
— and 3 is `PLANE_K` (`:100-111`), whose draw would print Y exactly where
codeword and scramble bits coincide. Auxes are spelled NUMERICALLY here.
*Not another domain* (R10): domain 10 or 11 (cmy7-only) re-purposed is
collision-free but gives a row two meanings by family; domains 14/15 are
the wrong shape (per stream, per block/page); domain 16, the v0.2
mechanism, is WITHDRAWN — no new domain, no new aux, no amendment to the
table's shape. *Not a fixed per-site subset* (no keystream): the same Y
pattern in every tile. The word keys get golden vectors in both trees, a
spec-mirror reference beside `color_dust_order_key`
(`src/holo/core/keystream_spec.py:89-93`), a drift row beside the dust
row (`test_h3_drift_format.py:184-185`; `AUX_BY_DOMAIN` unchanged, 9:
(0,), `:51-53`), their own golden beside the 1..15 table pin
(`test_h3_format_keystream.py:59-72`), tests that they vary with the
counter and differ from `value_scramble_bits(seed, PLANE_K)`, and a pin
that the dust draw at u < n_dust is byte-identical. The receiver learns
the preselection only after addressing (it needs the counter); the cold
path never needs it while the binarizing channel reads Y as '0' — R does
(Y 0.99 of white, R7 RULED): word sites carry only C, W and Y, so C vs
{W, Y} is the word bit (the hi bit there) and Stage-A and the word-bit reference
(`receiver/plugins/words.py:98-102`, `pose.py:231-280`) are unaffected
(§7b, R7, G10).

**The schema says it cmy8's way (simplified 2026-10-11, owner: "follow
cmy8's lead", "cleaner, more pythonic").** `CodecProfile.word_states`
stays a pair — `(W, C)` for cmy — mirrored by `FormatRow.word_states`
(`identity.py:149`) and recorded by the manifest (`src/holo/gen/
manifest.py:156`); the keyed W/Y choice at the '0' sites is the FAMILY's
rule inside the two furniture functions, which take the codec (or the
receiver's row) exactly as `dust_state_values` already does:
`color_word_states(row_seed, counters, codec)` renders
`np.where(values, one, zero)` — `values * 3` byte-identical for cmy7/cmy8
— and for `Family.CMY` sets the '0' sites whose domain-9 key has its MSB
set to Y (R10); `decode_color_word(states, row_seed, codec,
erasure_idx=None)` keeps today's refusal of any state outside the word's
lawful set ({W, Y, C} for cmy; {W, CM} for cmy8) and decodes `states ==
one`. No new profile fields, no law object, no flag. A second generator
reads the rule from PRINTED-FORMAT §12.5 and from the manifest's text
(`word_zero_rule`: domain 9, u = n_dust + site, MSB → Y). No renderer
consults `word_states` today (`color_word_states` hardcodes `values * 3`,
`src/holo/format/pilots.py:189-192`, receiver `:151-154`), so the codec
becomes a REQUIRED argument — a default would label un-migrated cmy words
CM, silently; every caller passes its own (gen `color_compose.py:188,
259`; receiver `color_sites.py:98`, `color_model.py:664`; analyzer
`residue.py:131`, `arms.py:881`, through the receiver's copy), and
`ROW_VALUE_GOLDENS` stay byte-identical. **Reading the word on paper is
the receiver's plugin's** (its word bits come from the R channel, R7, not
from `decode_color_word`); there an M read at a word site is a '1' (the
hi bit) — refusing on any M read would reject most c2 words (expected M
reads per word 0.82 / 0.76 / 0.71 / 1.19 / 0.94 on B3 / R9 / T12 / U12 /
X10). The rotation HELPS the BCH budget (t = 13): expected hi-channel word errors
2.35 → 1.60 (B3), 3.33 → 2.06 (R9), 3.21 → 2.09 (T12), 4.32 → 3.28
(U12), 2.56 → 1.85 (X10) — because a Y cell flips hi less often than a
W cell (B3 0.76 % vs 3.75 %), NOT because "a W→Y flip stops being an
error" (under hi-bit decoding it never was one); expectations at n0/2 W
and n0/2 Y per tile, which R10's binomial count leaves unchanged (reader
arithmetic on the committed `confusion_loo`, supervised poses).

**Why C for '1' (the owner's question): C, narrowly; M is a close
second.** The cell evidence is close: P(hi flip | C) vs P(hi flip | M) =
0.94 vs 0.25 % (B3, the screened corner cyan), 0.21 vs 0.31 (R9), 0.28 vs
0.36 (T12), 0.62 vs 0.89 (U12), 0.78 vs 0.57 (X10) — mixed, C ahead on
the three production-palette prints; `plane_hard_err_best` C ≤ M on all
five (0.68/1.24, 1.08/1.41, 1.12/1.41, 2.05/2.09, 1.38/1.53 %); d' C 11.6
/ M 5.6 / Y 3.1 at c3, 5.4 / 4.3 / 2.5 at c2 (S16 T11/T12; measured
2026-10-05, recorded in the 2026-10-06 refutation, not in the committed
extract). The W row (W→C vs W→M: 1.31 vs 2.45 % on B3, but 3.98 vs 2.48,
3.84 vs 2.30, 4.57 vs 3.46 on R9/T12/U12) measures white's encroachment,
not the '1' cell — the v0.2 draft's B3 citation is withdrawn. C is
decided by DEATH and SOLIDITY: on the re-screened M281 page C certified
839/840, M 61 (e038); the M281 lays C solid clean at (0,208,255), M only
at a displaced value with ~16 levels of yellow cross-talk (e041 §041.5).
M is the close second (sheet J M 2,749 vs C 2,738, e035; sheet I's M plane
complete, 1,961/1,961, e034). The '1' toner is the fatal plane: the one
least likely to die.

**Dust: the BALANCE LAW, PER TILE (R3, RULED 2026-10-09; AMENDED
2026-10-11, owner: "c w y m counts differ per tile, i take it. for each
tile, we _know_ a priori what the numbers will be, depending on format
string and pXXX. so, what's the problem? compute and cache, instead of
constants?").** Dust POSITIONS are tile-invariant; the domain-9
permutation varies dust STATES per tile (`pilots.py:123-134, 222-245`).
The dust MULTISET is a pure function of (row seed, tile counter, p): the
tile's word states are known a priori (the K word, the scramble, the
domain-9 preselection), so its word supply (n_C, n_W, n_Y; M 0) is
counted, and the n_dust = p − 100 dust sites are given one at a time to
the state with the lowest running total, ties broken in the order M, Y,
W, C, no majority cap; the fill order is the source vector, which domain
9 then permutes onto the dust sites as today (`pilots.dust_state_values`,
the same door and signature — it already takes the seed and the
counters). The generator renders the word states anyway, so the dust
costs nothing extra; the receiver computes both after addressing (it
needs the counter), and under R7 W/Y/M dust is invisible to addressing in
R. Typical multisets: at p120 twenty M in every tile whose min(n_W, n_Y)
≥ 20 (most tiles); in a tile with n_Y = 12 (the probe row's page minimum,
read 2026-10-11) M fills to 12, then M and Y alternate to the running
totals 16 : 16 — the dust multiset M 16, Y 4 — so
the rare Y-poor tile gets Y anchors exactly where a fixed law left it
none; from p ≈ 150 W and Y dust appear in every tile, C from about p200.
v0.2's EXPECTED supply (C 50, W 25, Y 25) was the recommendation; the
per-tile law replaces it (a second generator computes the same counts
from the same seed — no constants to agree on). `CodecProfile`'s
`dust_base_cycle` stays the cycle law's field (k/cmy7/cmy8
byte-identical); cmy's is `()`, and the balance law is the family's rule
inside `dust_state_values` (the profile's "dust sites need a cycle" check
exempts it). The membership check still applies. The law is spelled for a second
generator in PRINTED-FORMAT §12.5 (§13).

**Periodicity: conceded by the words, not by the dust (R3's reasoning,
2026-10-09).** The v0.2 draft's argument — a one-element cycle (M,)
"makes the permutation unobservable", every tile printing the same
20-cell magenta pattern at the 64-cell period, the "visually periodic
structure" DESIGN.md R3 forbids, so (M, M, M, Y) to keep the
permutation visible — is WITHDRAWN. The per-tile domain-9 permutation
does not remove the periodic structure: a spectral line at the tile
period has the amplitude of the mean per-position occupancy (the
EXPECTED image), and under the permutation each dust position holds M
in the multiset's M share of the tiles — line amplitude 1.0 all-M, 0.75
(M, M, M, Y), 0.5 (M, W). The words already do this: scrambled codeword
bits are near-uniform, so every word site is C in half the tiles, a
100-site lattice at 0.5 in the C plane on every colour row since v1
(DESIGN.md §5.2 records that site lattice as the format's one measured
concession to R3, and the receiver depends on it: the pitch vote, the
reference page). The furniture lattice is periodic by construction;
p120's dust adds twenty sites at 1.0 in M beside a hundred at 0.5 in C
(five times the sites). NOT a new concession; no R3 amendment needed.
The arithmetic replaces the owed M-plane spectral-line measurement
(generator W0(c), struck 2026-10-09); generator W1 pins it with the
law's multiset across p.

**Supply per tile (p120, the balance law, in expectation):** words C ≈ 50,
W ≈ 25, Y ≈ 25 (W and Y binomial per tile, R10; the probe row's n0 runs
36–65); dust M 20 in most tiles, an M/Y or M/W split where Y or W is
scarce (the per-tile law). By
`site_hash & 3` (131y + 17x, tile-invariant since
64 ≡ 0 mod 4; `receiver/lib/geometry.py:97-98`) the word sites fall
31/21/22/26 and the dust 4/6/7/3 into classes 0..3 (read-only count at
`holo/v1/sites/p120`):

| consumer | what it sees per tile | floor | one tile? |
|---|---|---|---|
| QDA, &1 split (`color_region_head.py:222-230`) | search 53 word + 11 dust; held-out 47 + 9 | every alphabet state on both sides | yes (`deterministic_fit_split`, `:164-182`) |
| hi marginal map L_hi (§2.7, R11 hi-first) on held-out furniture | per held-out half (&1 == 1: 47 word + 9 dust): class 0 {W ≈ 12, Y ≈ 12}, class 1 {C ≈ 23, M 9} | cmy8's 6 per class / 2 states / 3 per state (`color_model.py:22-24`) | yes (the floors); breaks even against the raw statistic at ~2 tiles' furniture on U12, ~8 on B3/X10 (logit evaluator, measured) |
| lo\|hi=0 (W vs Y), lo\|hi=1 (M vs C) | ONE state per class by construction | A4b's 40 fit labels / 6 per class + a DISJOINT 20-cell validation set, no diversity floor (`color_conditioning.py:99-101, 386-409`) | qualify under A4b's floors; measured not to pay below ~8 tiles' furniture (R11) |
| page-field furniture anchors | C 50, Y ≈ 25, M 20 (raw; effective lower, §7f) | `ANCHOR_MIN_SITES` 24, 4 minority (`field_tiers.py:100-101`) | raw yes |

**The furniture law is FAMILY-INDEPENDENT (owner, 2026-10-09).** The
word '1' state, the word '0' state set with its keyed rotation rule and
the dust multiset law are an axis of their own per row, chosen on
robustness, anchor supply and the death map; the payload family
constrains only the payload. In code the axis is `word_states` on the
codec/row plus the family's keyed rule, and `dust_base_cycle` or the
family's balance rule (above; CMY-RECEIVER-PLAN §3 I-3 mirrors the same
two function signatures); cmy is its first instance. Conversely cmy8's furniture may be
single-toner though its payload mixes, and the reduced-alphabet erasure
row — cmy8's per-plane codewords with CMY lost by a known-position
erasure, a seven-state payload alphabet — may put its words and dust in
ANY state the engine lays unscreened (CMY on the AltaLink included). The
carry-over to cmy8 and the erasure row is a `-v2` generation token per
family when picked up, owing one measurement: C against CM as the '1'
state on the AltaLink (CM is darker; C is the toner that decodes cold on
every engine). For eight states at 20 dust sites lowest-first gives
about three of each missing state, what the cycle gives today, so the
gain there is the word rotation ('0' in {W, Y} puts Y anchors on word
sites), not the dust.

### 2.6 The pooled fountain at n = 2 and the stream tier (D8)

cmy8 -v1's law verbatim (CMY8-POOLED-FOUNTAIN): esi = counter·2 +
stream_idx on domains 7/8 aux 0; stream-exact per-(block, page, stream)
quotas; k_total = 2·k_meta, the K field carries k_meta, metadata version
0; the metadata equation at LFSR index counter·2 + s
(`max_equation_index(2)` = 2^19, `src/holo/receiver/format/metadata.py:54-65`).
**Blocks and reserve count the POOL:** B_pooled = ceil(2·k_meta/16384)
(`n_blocks_for(k_total)`, `src/holo/core/fountain.py:142-146`, as the
pooled capacity paths pass it, `src/holo/core/capacity.py:137-138,
269-270`), reserve = 16 + bit_length(B_pooled·Z − 1) (`capacity.py:25-39`)
— k_meta 10,000, Z 1 → B_pooled 2 → reserve 17; one block iff k_meta ≤
8192. **Metadata floor (G5, a theorem plus a pin).** The LFSR is
maximal-length of degree 24 (`metadata.py:33-38`) and gcd(2, 2^24 − 1) =
1, so decimation by 2 keeps the primitive minimal polynomial: any 24
consecutive same-parity indices (one stream, 24 consecutive tiles) are
independent (0 deficiencies in 2,000 random windows, reader check);
v0.1's "the puncture breaks the consecutive-rank guarantee" is withdrawn.
Rank 24 needs 12 healthy tiles or 24 with a stream dead; the TRUST floor
(48 equations, a false-accept budget) 24 healthy or 48 — a fragment-size
cost against cmy8's 16 (§9).

**Tier 3 is a DEAD-STREAM tier**: dial-conditional at q ≤ 1/2 uniform,
below 1/2 uneven (§3.2), reported, never refused; it survives a dead Y
(lo) or a dead M (hi), a dead C is fatal at any dial. Every "plane tier" /
"dead_plane_ceiling" wording (`src/holo/gen/plan.py:45-47, 108-133`,
`src/holo/gen/manifest.py:31-33, 143`, `src/holo/cli_gen.py:250-252`, and
`cli_gen.py:128-130`'s "trust after 48 distinct tiles" → "48 distinct
equations, n_streams per healthy tile") reads "stream tier" for cmy, the
plane→stream map reported.

### 2.7 Evidence, calibration and the demap (D10)

**The durable evidence** is THREE W-relative state scores — log p(C)/p(W),
log p(M)/p(W), log p(Y)/p(W) — at ids (1, 2, 4), from the alphabet-masked
QDA (§7c), **calibrated at EVIDENCE time, one head per colour lane
(capture, level, page)** — cmy8's locus and cascade (R11, RULED
2026-10-10; the lane is `region_job`'s subject, API.md): the QDA, the
chain maps, the registration arm, the feature divisor and the context
matrix fitted once and applied to every window on the page — and summed
across captures as cmy7's and cmy8's stored evidence is
(`receiver/plugins/tiles.py:382-395`, no post-sum clamp; 0.0 the one
erasure spelling, `:424-430`). Scores put no mass on overlap states and
keep the joint information the two-stage demap needs. **The per-tile
levels are the EXISTING residue rows and nothing new:** `tiles.local`
reruns the head over the windows covering one failed tile; `tiles.swim` reads the neighbours' certified cells (planek stays cmy8-only, §7g; the cmy K view in its shape is §2.9b — superseded 2026-10-12 by R25's reading in receiver A7: planek reads a cmy label stream as the K view of its toners' summed presence, `plugins/plane_label.py`; kview as a separate row stays parked, R25a). No per-tile
standing fit, no new region type.

**Calibration through ONE chain-rule factorization (R11, RULED
2026-10-10: hi-first).** Three PAVA maps per lane — L_hi (the hi
marginal), L_{lo|hi=0} (W vs Y, on sY), L_{lo|hi=1} (M vs C, on
sC − sM) — fold back into scores exactly under equal priors:

```
sY = L_{lo|hi=0}
sM = L_hi + log(1 − σ(L_{lo|hi=1})) − log(1 − σ(L_{lo|hi=0}))
sC = L_hi + log σ(L_{lo|hi=1})      − log(1 − σ(L_{lo|hi=0}))
```

so the demap below returns hi, lo|hi=0 and lo|hi=1 as the calibrated maps
themselves, and lo and hi|lo as marginals of a calibrated joint (v0.1's
"per-stream LLRs fold back only in product form" holds for two MARGINAL
maps, not for a chain). Each map is fitted on the exact statistic it
calibrates (E017.5, `color_model.py:411-414`). **Why hi-first**
(measured on the e041/e042 scans, `measure/cmy_calibration/`, §14.2): in
the design's own rung pairing (lo at the lower rung certified alone, hi
at the top rung decoded given lo; §2.2) the two chains TIE on pages;
outside that pairing (both streams at r0850) hi-first wins, because lo is
certified almost only through a certified hi; and the dead-Y erasure law
needs L_hi, which hi-first fits as its first map — NO fourth map. v0.2's
reason for lo-first ("conditioning hi on a certified lo — the r0850
direction — then reads calibrated maps") is WITHDRAWN: under hi-first the
r0850-direction hi|lo forms are derived and measured equal to the fitted
ones within 0.003 bit under the logit evaluator (0.0005 with certified cells). **Lo-first is the
RECORDED alternative**, no longer the recommendation: L_lo,
L_{hi|lo=0} (W vs M), L_{hi|lo=1} (Y vs C), folded by the mirror —
sM = L_{hi|lo=0}; sY = L_lo + log(1 − σ(L_{hi|lo=1})) −
log(1 − σ(L_{hi|lo=0})); sC = L_lo + log σ(L_{hi|lo=1}) −
log(1 − σ(L_{hi|lo=0})).

*Population:* the held-out (`&1 == 1`) furniture with WORD SITES
ADMITTED — p120's 20 dust are all M under the balance law, so W, C and Y
labels come only from words until certificates — plus certified cells
read from the store at fire time; state-balanced in a NEW cmy-only
weighted PAVA entry, each of the four states carrying 1/4 of its map's
mass (§7c). Measured: the weighted entry beats cmy8's class-balanced fit
cold by +0.006 to +0.013 bit on the lo marginal (within ±0.003 of zero on the hi marginal, no interval below zero) and never loses; under class-balanced
weights it reproduces `fit_component_pava` bit for bit (pinned in the
instrument's smoke). *Evaluator:* cmy's maps interpolate the PAVA nodes
in LOGIT space (log p/(1 − p) linear in score between nodes, flat beyond
the end nodes) — inside the new cmy entry point; cmy8's `PavaMap` does
not change. holo3's `PavaMap.llrs` (`color_model.py:253-257`)
interpolates PROBABILITY linearly between block centroids; measured, that
costs 0.02–0.12 bit against the raw bounded statistic on every
near-separable pair (cmy's Y/C, M/C, W/M) and on every lossless c3 band at
page scale (0.065–0.12 bit), and about 0.03–0.07 bit of every cold loss;
logit interpolation of the same nodes reduces the c3 loss to ≤ 0.0032 bit
and removes hi-first's one losing page form. The same defect reaches
cmy8's own marginals: an OWED receiver line of its own (a null / A-B on
archived cmy8 states before any change to `color_model.py`), not R11's.

*Fallback, per map:* until a map qualifies, its piece is the region QDA's
uncalibrated statistic under the uniform L∞ bound of 20
(`CMY7_RELATIVE_SCORE_BOUND`, `color_region_head.py:31`) — the cold start
the owner stated; the bound binds on 52 % of B3's payload cells for raw
scores and on 0.0–0.1 % once a full chain is fitted. An unsupported or
collapsed STREAM emits exactly 0.0 in its marginal and both conditionals,
by the ERASURE LAW (§7c): dead lo — sY := 0, sC = sM := L_hi; dead hi —
sM := 0, sC = sY := L_lo, which under hi-first reads the raw bounded lo
statistic, no map — cmy8's doctrine that "a garbage LLR costs it a tile"
(`color_model.py:396-399`). The collapse detector (`fit_qda`'s
whitened-mean test in label space) misses 6–9 % of dead-Y regions at one
tile (detection 0.91–0.945, false collapse 0.000) and reaches ≥ 0.98 from
two tiles: receiver W3a must not make the erasure wait on that test
alone (a design detail owed there). *Floors:* cmy8's as they stand — the
marginal map under 6 / 2 / 3 (`color_model.py:22-24`), the conditional
maps under A4b's 40 fit labels / 6 per class plus a DISJOINT 20-cell
validation set (`color_conditioning.py:99-101, 386-409`). One tile's
furniture fits the QDA and clears the marginal floors (§2.5); the
conditional maps qualify under A4b's floors, measured not to pay below
~8 tiles' furniture. With the logit evaluator the marginal maps break
even against the raw statistic at about 2 tiles' furniture on U12 and
about 8 on B3 and X10; the conditional maps gain at most ~0.01 bit at page
scale. So the floors are not what protects yield cold — the gate is
(§7c). *Not taken: per-tile-first calibration* — a tile's own 120
furniture cells through a low-parameter map before any page fit: a
receiver-doctrine change, not an R11 item; a lone tile's furniture cannot
carry a nonparametric map (measured; `plane_k.py`'s docstring says the
same from the other direction, "A PAVA map fitted on 120 format sites per
tile cannot price 3,976 payload cells") (§10). *Rejected: calibration
at ATTEMPT time* (the v0.2 draft): the attempt reads `TileCut`s of
`values` and `observed_flat` only
(`tiles.py:84-91`) and SUMS every capture before decoding (`_combine`,
`attempt_tile`, `:382-395, 531-558`) — no per-region map means anything
after that sum (E017.5's foreign score axis, 50 % BER); the lse marginals
do not commute with it, the linear conditionals only over calibrated
components. Uncalibrated rows plus a map id, calibrated per component in
`_combine`, is new tiles/store/resume machinery — recorded, not chosen.
**Two captures** (measured, RECORDED as an owed line, cmy8-inherited, not
R11's): the cmy8 sum of stored scores over one sheet's 2400 and 4800
captures reads below the best single capture on every chain (fallback
I(hi) 0.787 vs 0.870) by overconfidence, not lost information — a
recalibration oracle on the sum reads 0.880; consistent with the
multi-scan law (print-correlated errors).
*As built 2026-10-12 (receiver A8):* `src/holo/receiver/plugins/color_chain.py`;
the as-built record and the clean-sim centroid finding are
CMY-RECEIVER-PLAN A8's.

**The demap** — format law, ONE function in `src/holo/core/channel.py`
beside `cmy8_raw_marginal_llrs` (`:154`), mirrored in the receiver's
`tile_codec`. With s_W = 0 and LLR = log P(1) − log P(0):

```
hi        = lse(sC, sM) − lse(0, sY)
lo        = lse(sC, sY) − lse(0, sM)
hi | lo=0 = sM − 0        hi | lo=1 = sC − sY
lo | hi=0 = sY − 0        lo | hi=1 = sC − sM
```

These are LABEL-bit LLRs; the codeword bit's LLR flips sign where the
stream's dither is 1 (as `cmy8_decode_stream` un-dithers). The
conditioning input is the sibling's LABEL bit = its re-encoded codeword
bit XOR its dither.

**Arity collision → an evidence KIND.** Width 3 equals cmy8's
(`receiver/plugins/tiles.py:72-73`) with other semantics, so "arity 3" is
never the discriminator: the evidence row carries a KIND
(CMY-RECEIVER-PLAN I-5 — CUT in the plan's v0.2, 2026-10-11 night: family dispatch suffices, an evidence kind waits for kview; the names stay as the vocabulary of this paragraph: K_LLR, CMY7_RELATIVE, CMY8_MARGINALS, CMY_SCORES,
CMY_PRODUCT_HI/LO; the product forms are §2.9's), frozen at receiver W0.
Pure reshapes (`swim.py:529`, `local_ctx.py:624`, `uplift.py:189`)
need no change. Column INTERPRETERS dispatch on the kind: the decode
(`tiles.py:516`), the region emission (`evidence_with_divisor`,
`color_region_head.py:316-338`, cmy8's detector path the seam),
provisional ink (`color_region_ctx.py:136-140`, a PREFIX alphabet: Y would
read as CM). Columns are ids (1, 2, 4) ascending (`channel.py:16-18`);
cmy8's "column s−1 = state s" (`:159-160`) does NOT hold. Mapper: 2
bits/cell.

### 2.8 Emission routes (D11) — R9 RULED 2026-10-09; the construct SIMPLIFIED by R23 and the selector ruled by R21, 2026-10-11

Emission is NOT identity (FORMAT-SPACE §2/§3; PRINTED-FORMAT §12:
"generators MUST emit the composite the chosen engine will honour"): the
format says "toner t on cell", a ROUTE says how an engine is asked for it.
The route never enters the format identity (FORMAT-SPACE §2.1, §3;
PRINTED-FORMAT §12.4); the GT (`src/holo/gen/emit.py:325-345`) stays the
C/M/Y dot planes on every route, `gt_sha` route-independent, `ps_sha` the
route's.

**Two routes, both in the generator's own idiom (R23, RULED 2026-10-11,
owner: "make the emission code pure .ps without pjl etc. same as k and
cmy8, and just emit data as an image mask (similar to cmy8, just not in
cmyk but rgb instead)").**

**(1) `cmyk1`** — today's 1-bit/component DeviceCMYK composite
(`put_cmyk_bitmap`, `src/holo/gen/ps.py:182-222`, called at
`emit.py:318`), byte-identical for every existing row; for cmy the
AltaLink/Canon route. e042's X10/X11 bands are exactly this construct
(`experiments/042-altalink-cell-encodings/ps_altalink_probe.py:164-167`),
printed and read: 2.85 % at c2, 0.05 % at c3 (e042 §042.4). On the M281
it is predicted SCREENED (the interpreter renders into an 8-bit RGB
contone device, 0/255 pass, M281-COLOUR §2; the corner cyan is screened
on PostScript, e041 §041.5i).

**(2) `rgb`** — K's construct in colour: THREE 1-bit imagemasks per page,
one per toner, each painted after `r g b setrgbcolor` with the ENGINE's
measured solid device-RGB value, white left unpainted (`PSDoc.put_bitmap`,
`ps.py:153-181`, with a colour argument; the K default byte-identical);
plain PostScript — PSDoc's DSC head and guarded `setpagedevice`, ASCIIHex
as every K page [corrected 2026-10-11: ASCII85, as built
(`emit._put_color_field`, `filt="ASCII85"`, the probes' `mask-a85`); K
pages stay ASCIIHex]; no PJL, no HP operators, no prologue, no palette, no
bands. Why not a 1-bit DeviceRGB composite "like cmyk1": its eight
corner colours are not the M281's solid points — the corner cyan
(0,255,255) is screened and the corner magenta (255,0,255) not solid on
PostScript (e041 S14, S10p2); only the displaced values (0,208,255) and
(240,0,192) lay solid, and three distinct R values cannot ride one bit per
component. Three masks carry any value at 1 bit per dot per plane: an
A4-4mm c2 page is ~12 MB raw, ~24 MB ASCIIHex [corrected 2026-10-11,
measured: 15,061,180 B ASCII85 for `c2-cmy-r0775x0700@53x37`, against
32,380,665 B for the same page on `cmyk1` — the printed-size ledger of
`tests/holo/test_cmy_emission.py`] — under cmy8's `cmyk1`
jobs (0.5 byte/dot, ~32 MB hex, printed on both engines) and under every
palette job e041 printed (31.6–33.0 MB). UNMEASURED as a construct on
the M281: every solid point was measured through 8-bit Indexed IMAGES
(S12–S17) and every imagemask printed there was K (T9, U14); the
mechanism predicts solid (the same pixel values reach the contone frame;
the screener acts on composite pixels and K, M281-COLOUR §2); one scratch
sheet with mask bars beside image bars settles it before P1 (the probe,
below). [2026-10-11: measured — masks RULED (e043 §043.5), the values
b005fae4, P1 printed as masks (e044).] The e041 Indexed construct
(8-bit `[/Indexed /DeviceRGB 3]`,
PJL-wrapped, the four guarded HP calls, 14 band images,
`experiments/041-m281-screen-routes/ps_mixture.py:81-83, 156-204`) is the
MEASURED fallback — recorded here, built only if the masks screen.
[2026-10-11: not needed — the masks print solid (e043 §043.5), the values
b005fae4, P1 printed without it (e044).]

**The engine record (R9's footing reduced to cmy8's shape — R21, R23;
owner: "like c2-cmy8 and c3-cmy8, just in RGB with fewer possible pixel
values (the 3 optimal unscreened toner edges, and white)").**
`src/holo/devices/registry.py`'s `Printer` (`:24-34`) gains two fields:
the colour route it honours (`cmyk1` | `rgb`) and, for `rgb`, the three
solid device-RGB values (W is unpainted paper): `hp-m281` → `rgb`,
C (0,208,255) [2026-10-11: C (0,176,255) since b005fae4, e043 §043.5; printed
in e044], M (240,0,192), Y (255,255,0) (e041 S14–S17; S15–S17's
production lookup, `ps_trigger.py:109-116`, `ps_reset.py:81`);
`xerox-altalink-c8245` → `cmyk1` (X10/X11 unscreened, e042 §042.4); a
NEW Canon iR-ADV C257/357 row → `cmyk1` (e040 §040.4d's unscreened colour
cells; no cmy page printed there). The VersaLink and the M681 get no cmy
entry (no evidence). **e043 (2026-10-11, experiments/043-m281-cmy-probe.md §043.3c)** measured the M281's plateaus at two-level steps: the engine adds a screened 212 lpi yellow component to cyan above G 190 and to magenta at every value (least at R 238–240, B 192–196), and dark dots to any yellow off the corner; the sheet's final proposal was C (0,184,255), M and Y unchanged; **sheets 2 and 3 (§043.5–043.6) moved it: the engine's added yellow is zoned by page position and, inside a cell field, the cyan value's — C (0,176,255) reads a quarter of (0,184,255)'s stipple at c2, a third at c3; the registry's `hp-m281` row carries C (0,176,255), M (240,0,192), Y (255,255,0) since b005fae4 ("Use our new numbers"), the one home of the values** — the owner's edit. No revisions, grades, halftone selections, prologues
or wrappers: a re-measured point is an edit to the registry with its
source in the entry's text, and the goldens that depend on the old value
move with cause in their ledger — a route is an emission fact, not
format law.

**The selector — `--printer ENGINE` (R21, RULED 2026-10-11, owner: "We
have L: legacy format strings that imply print formats. No other legacy
print will ever be done, if any at all. That means you can hardcode the
L: rows with the info you need, and completely trash the current use of
--printer. Repurpose it A-Z for our new use.").** Today `--printer` is
identity-bearing on the legacy path only: beside `--coding`/`--profile`
the printer's media and margin derive the page geometry and so the v1
seed (`src/holo/devices/profiles.py:75-89` `make_spec`;
`src/holo/cli_gen.py:39-85`), and FORMAT-SPACE §9's fence refuses it
beside `--format` (`cli_gen.py:50-54`). Every printed or golden-bearing
v1 identity is an `L:` fossil (`src/holo/format/fossils.py`, 14 rows),
and each fossil ALREADY carries its placement — A4 and its margin
(`Fossil.margin_mm`; `resolve_fossil_spec`, `:185-204`, rebuilds the
FormatSpec and refuses on a seed mismatch) — so the printer-derived
geometry is redundant with the catalogue. Ruled: (a) the legacy
generation door GOES — `make_spec`, `get_printer`, the
`--coding`/`--profile` selectors of `generate`/`capacity`, `registry -v`'s
per-printer derived geometry, the `hp-m281-ink` pseudo-printer (its
print, e029, is the fossil `c2-r0700@3392x2368`); `resolve_fossil_spec`
(`--format L:<id>`) is the ONE way a legacy FormatSpec is minted,
byte-identical by the fossil self-check; `PROFILES` survive as
documentation listed by `registry`; the fossil seeds and recipes, every
emission golden, the K manifest bytes and FORMAT_ROWS do not move.
(b) `--printer ENGINE` is the emission engine on every
`generate`/`capacity`, v2 and fossil alike: optional; never geometry,
never identity; the engine's record decides the route (no `--route`
flag); no engine named → `cmyk1`, today's default; the manifest's
`printer_id` carries the engine and, on `rgb`, the three values sent.
(c) FORMAT-SPACE §9 ("generation stops selecting printers") is amended
in §19 with the build: generation selects an ENGINE for emission, never a
geometry; the pseudo-printers §9 already slated for deletion go now.
(d) NOT this ruling's: the receiver's legacy decode door (`holo3 decode
--coding ID --printer ID`; `src/holo/receiver/format/identity.py`
`MARGIN_MM`, `coding_printer_ref`) and `characterize analyze --printer`
(the engine a discovery sheet measures — already the new meaning); the
receiver door's retirement onto `--format L:<id>` is the receiver plan's
(owed there); until it lands the two CLIs spell `--printer` differently,
each help text saying which.

**The solid points are PLATEAUS, not points** (recorded 2026-10-09 from
the e041 bar maps — S10p2/S11/S12/S14, swept in 16-level steps). CYAN on
PostScript: the corner (0,255,255) is SCREENED (lattice 97–130 on S14,
160 on S12) whether matching is on or off; (0,208,255) and (0,192,255)
are both SOLID (8 and 7–9), (0,224,255) half-way (40–49) — the plateau
spans at least G 192–208, its upper edge between 208 and 224, unmapped at
1-level resolution (e041 §041.5i); on the same bars (0,192,255) shows
less blue-channel absorption (B 202 vs 194), i.e. less foreign yellow.
MAGENTA: NOT solid at its corner (255,0,255) on either route measured;
solid along R ∈ {240, 255} × B ∈ [128, 192]; (240,0,192) the mildest
solid, carrying ~16 levels of yellow cross-talk; the finer B sweep is the
record's own owed item (e041 §041.5). YELLOW: solid along the whole
R = 255 row, (255,255,0) deep inside. The M and Y maps are PCL XL's sweep
(S10p2); on PostScript only the printed points are known. So the hp-m281
values are KNOWN-SOLID (every cell measurement, S15–S17, used them), not
known-optimal; C's G 208 and M's R 240 sit at the measured END of their
plateaus.

**The probe — an owner MEASUREMENT, not a generator wave (R9 (c) as
reduced).** For a new engine, beside its HCAL-R1 discovery sheet, a
scratch sheet (fiducials allowed, DESIGN.md R3) of solid bars: a ladder
of candidate device values per toner (16-level steps over the foreign
channels, 1–4-level steps around a known-solid value), read for solidity
against the engine's screen lattice by e041's S10p2 method (lattice peak
over ring median in 96-px windows, ≤ 18 unscreened;
`measure/e041_scale_readout.py:120-126, 440-494`;
`measure/e041_spectrum.py` when the lattices are unknown), the plateau's
edges on both sides, its MIDPOINT the registry value, the least-foreign-
toner point noted. For the M281 on P1's day, BEFORE the volume sheets:
the fine sweep around (0,208,255) and (240,0,192), and — the first
question — the same bars drawn as colour IMAGEMASKS beside Indexed-image
bars, since only the image form has been measured. [2026-10-11: done before
P1 — e043 §043.5, the values b005fae4, then e044.] The emitter is a
`measure/` script over e041's bar generators and `PSDoc.put_bitmap`; its
record goes into the engine's experiment log and the registry entry. The
owner's spectral-midpoint analysis (2026-10-09, "curious what we would
get") stays owed on it. A RECORD, not a cmy gate (§11).

**PCL XL — not abandoned (the record, 2026-10-09).** On the M281's PCL XL
route C and Y lay solid at their corners and M only at the displaced
values (S10p2); a per-object PCL XL job (S10p, 1,168 images) CRASHED the
formatter (HP 49; the novelty-budget rule); production stayed PostScript.
It remains a lawful route candidate per engine, an entry only when
measured (holo.gen has no PCL XL emitter today).

**K furniture is NOT in this design** (R14 RULED 2026-10-10, "no K for
now"): the alphabet has no K state; `cmyk1` writes K = 0 (PRINTED-FORMAT
§12), the `rgb` route paints three toners; a furniture-law option for a
later generation, not a ban.

**Unmeasured (2026-10-11).** The colour-imagemask construct on the M281
(the probe sheet before P1) [2026-10-11: measured — e043 §043.5, b005fae4,
e044]; a pure cmy page through `cmyk1` on the M281
(predicted screened; one page on P1's day would settle it, the design
does not need it); cmy on the Canon (`cmyk1`, by construction from e040).

### 2.9 The two-channel structure (new in v0.2)

Each label bit is near-linear in the scanner channels. On the S14 solid
bars (W 231/232/234, C 46/151/194, M 215/67/119, Y 229/219/88 RGB;
measured 2026-10-05, recorded in the 2026-10-06 refutation, not in the
committed extract): **hi = darkness in R+G** — (R+G)/2 reads C 98.5, M
141 against W 231.5, Y 224, margin ≈ 0.36 of white at the closest pair;
**lo = darkness in R+B−G** — C 89, Y 98 against W 233, M 267, margin ≈
0.58. In absorption space the four states are four affinely independent
points (a tetrahedron), so EVERY 2+2 labelling is linearly separable per
bit; the C-antipode makes hi ≈ aR + aG and lo ≈ aR + aB. Cross-talk is
not small (same bars): M darkens B by ~79 % of what Y does, C darkens G
by ~49 % of what M does (planek's sheet-H record: 60 %, `plane_k.py`
docstring). Solid-bar margins, not c2 cells: G10 measures them.

- **(a) Two views, one page.** Production reads ONE 4-state page (joint
  QDA, context, the chain). A K-like view reads each stream as a K page
  in a fitted linear channel (per-region LDA on furniture, STATE-balanced
  weights; the fixed R channel is addressing's, R7). Its labels come from
  the state→label map on reference states and certified projections (hi:
  C and M are 1; lo: C and Y are 1) — NEVER from word bits (a '0' printed
  Y is lo = 1), never from K's label source
  (`calibrate.format_reference_values`, `receiver/plugins/calibrate.py:117-152`,
  filler draws at extra sites — a colour row's extra sites are dust).
- **(b) The K view is a RESIDUE arm, not a cold-start reader.** planek —
  K machinery on an isolated colour channel — "certifies zero on every
  crop" once the certified neighbours' labels are removed: "A PAVA map
  fitted on 120 format sites per tile cannot price 3,976 payload cells"
  (`plane_k.py:1-60`). Scheduled in planek's shape, its rows are transient
  PRODUCT-FORM scores through the ordinary cmy attempt: a hi-view LLR L
  writes (sC, sM, sY) = (L, L, 0) — hi = L, both hi|lo = L, lo = 0
  exactly; a lo view writes (L, 0, L); no durable evidence, no new arity
  (planek's `transient_row`, `plane_k.py:535-553`); their KIND keeps joint
  consumers (conditioning, context bins) off them.
- **(c) The c2 context variable** is plausibly the neighbour's STATE (W
  takes a neighbour's colour): the per-plane 9-bin (keyed on the TONER,
  not on hi/lo) and a 4-ary neighbour-state context measured side by side.
- **(d) Per-hypothesis sampling.** `features_at` reads channel p at plane
  p's offset, one vector per cell (`receiver/plugins/color_region_anchor.py:127-165`);
  for one-hot states hypothesis s should read all three channels at s's
  own plane offset (W at the pose) — an M cell's blue absorption is
  otherwise read at Y's offset, one mechanical source of c2 W→Y. Measured
  side by side, adopted only on a held-out gain; ~3× colour sampling.
- **(e) Addressing is not on these channels.** R7 (RULED 2026-10-09)
  puts the addressing pose and the word bits on C isolation, the R
  channel (§7b); §2.9's two channels are the payload demap's and the K
  view's, (a)–(b).

## 3. Worked numbers

### 3.1 Exact widths at p120 (S = k − 153; user bits = k − 152)

| rung | k | user bits / stream | S / stream | R_tx = (k−120)/3976 |
|---|---|---|---|---|
| r0547 / r0550 | 2240 | 2088 | 2087 | 0.533 |
| r0625 | 2560 | 2408 | 2407 | 0.614 |
| r0700 | 2880 | 2728 | 2727 | 0.694 |
| r0775 | 3200 | 3048 | 3047 | 0.775 |
| r0850 | 3520 | 3368 | 3367 | 0.855 |

k from `construct.py:69-76`; the rest is the §2.3 law.

### 3.2 The column-group pair table (p120)

Replica of the law, CONFIRMED in-tree (`core.column_groups.column_groups`);
reserve at B_pooled = 1 (k_meta ≤ 8192; §2.6 for larger volumes).
**Golden owed per (pair, p).**

| pair (hi × lo) | Z | carried hi : lo | spare b/site | hi-dead ceiling | lo-dead ceiling | any-one | fountain bits/site | reserve |
|---|---|---|---|---|---|---|---|---|
| r0700 / r0775 / r0850 (uniform) | 1 | 1 : 1 | 0 | 1/2 | 1/2 | 1/2 | 5,454 / 6,094 / 6,734 | 16 |
| r0775x0700 | 19 | 19 : 17 | 0.74 | 17/36 | 19/36 | 17/36 | 5,773 | 21 |
| r0850x0775 | 21 | 21 : 19 | 0.67 | 19/40 | 21/40 | 19/40 | 6,413 | 21 |
| r0850x0700 (also the conditioned shape) | 21 | 21 : 17 | 1.33 | 17/38 | 21/38 | 17/38 | 6,093 | 21 |
| r0700x0547 | 17 | 17 : 13 | 1.65 | 13/30 | 17/30 | 13/30 | 4,812 | 21 |
| r0700x0625 (the c2 multi-print minimum, §2.4) | 17 | 17 : 15 | 0.82 | 15/32 | 17/32 | 15/32 | 5,133 | 21 |

Uneven pairs are spelled hi-heavy (orientation is immaterial to the law;
the measured channel wants hi ≥ lo on every c2 print). "hi-dead ceiling"
= the dial up to which every block survives hi dying
(`plane_tier_ceiling(0)`, `column_groups.py:71-76`); "site" = one tile
position across both streams. At p300 r0775x0700 is Z 26 (replica).

### 3.3 Bytes per A4 page (A4-4mm, q = 0.9 = 10 % repair tiles)

cmy8 and K figures are EXACT (`./confetti.py capacity --format <id>
--paper A4-4mm --source-fraction 0.9 --json`, 2026-10-06; src/ unchanged
since); cmy figures are EXACT too since 2026-10-12 (the same command at
generator W2b, `max_payload_bytes` at one page and `net_bits_per_mm2` at
that payload; c2-cmy8 r0700/r0850 and c3-cmy8 r0850 re-ran to the
byte) — the v0.2 ESTIMATES (the cmy8 row's bytes × (S_hi + S_lo) /
(S_C + S_M + S_Y)) kept in parentheses.
b/mm² is per CELL FIELD (`plan.py:77-86`): c2 3392 × 2368 cells at 2 dots
= 57,579 mm², c3 2240 × 1536 at 3 dots = 55,494 mm². e033/e036 quote the
same cmy8 bytes per A4 PAGE (62,370 mm²): sheet H 2,220,921 B = 284.9,
sheet I 1,798,761 B = 230.7 = this table's 308.6 / 249.9 (`plan.py:102`
calls 230.7 "field", wrongly; main's CLAUDE.md e036 bullet calls 284.9
"net field" — one line owed on main).

| row | bytes / page | b/mm² | kind |
|---|---|---|---|
| c2-cmy8-r0700@53x37 (1961 tiles) | 1,798,761 | 249.9 | exact |
| c2-cmy8-r0850@53x37 | 2,220,921 | 308.6 | exact |
| c2-cmy8-r0775x0775x0850@53x37 | 2,076,982 | 288.6 | exact (tier: "needs q <= 38/59") |
| c2-k-r0700@53x37 / r0850 | 600,183 / 740,023 | 83.4 / 102.8 | exact |
| **c2-cmy-r0700@53x37** | 1,197,117 | 166.3 | exact (estimate v0.2: ≈ 1,199,000, ≈ 166.6) |
| **c2-cmy-r0775x0700@53x37** (R4's first c2 PROBE; Z 19, 19:17) | 1,265,230 | 175.8 | exact (tier: "needs q <= 17/36"; estimate 2026-10-11: ≈ 1,269,000, ≈ 176.4 = 1,798,761 × 5,773 / 8,181) |
| c2-cmy-r0775@53x37 | 1,337,597 | 185.9 | exact (estimate v0.2: ≈ 1,340,000, ≈ 186.2) |
| c2-cmy-r0850@53x37 | 1,478,077 | 205.4 | exact (estimate v0.2: ≈ 1,481,000, ≈ 205.7) — no measured c2 print supports lo at r0850 (max I(lo) 0.865, X10) |
| c2-cmy-r0850x0775@53x37 (CONDITIONED, R5; not a first row) | 1,405,686 | 195.3 | exact (tier: "needs q <= 19/40"; estimate v0.2 from the cmy8 r0775x0775x0850 row: ≈ 1,408,000, ≈ 195.6) |
| c3-cmy8-r0700@35x24 (840 tiles) / r0850 | 766,932 / 946,932 | 110.6 / 136.5 | exact |
| c3-cmy7@35x24 | 552,466 | 79.6 | exact |
| c3-k-r0850@35x24 | 313,261 | 45.2 | exact |
| **c3-cmy-r0850@35x24** | 629,593 | 90.8 | exact (estimate v0.2: ≈ 631,000, ≈ 91.0) |
| c3-cmy-r0700@35x24 | 509,913 | 73.5 | exact (estimate v0.2: ≈ 511,000, ≈ 73.7) |

**Comparators on the M281:** 64.7 b/mm² (e029, c2-K r0700, lower source
fraction, field basis) is its certified record (on any engine: sheet H,
308.6 per field). The record's ranking after S17 (single prints, 10 %
repair; e041 §041.5o): c2-cmy 0.94–1.4 MB (167–196 at 2.8–4 %; ~130 at
6.4 %) ≈ c3 cmy7-dotmix + orientation ~1.0 MB (144) > c3 cmy7-dotmix 0.86
MB (124) ≈ c3 cmy8-dotmix 0.95 MB (136) > c2-K 0.60–0.74 MB > c3-cmy 0.63
MB (91) > c3-K 0.31 MB (45); the record's own c2-cmy ranges differ
(§041.5m, §041.5o, M281-COLOUR §6A). What each costs to BUILD is §9.

## 4. How it works with planes and rungs

**A tile, outward.** (1) ONE pooled fountain at n = 2 cuts the envelope
into symbols, esi = counter·2 + s (s = 0 hi, 1 lo); with uneven rungs the
wider stream's symbol is cut into Z column groups. (2) Per stream:
metadata bit + symbol → CRC → the LDPC codeword of THAT STREAM'S rung,
3976 transmitted bits at p120. (3) Each codeword XOR its dither (domain
13, aux s + 1). (4) Per cell the two dithered bits (hi, lo) index the
label table → presence id 0, 4, 2 or 1. (5) The domain-12 permutation
places the 3976 states. (6) Word sites get the K word, '1' = C, '0' =
the site's preselected W or Y (domain 9, u = n_dust + site, R10); dust
the balance-law multiset (twenty M at p120) under domain 9 (u < n_dust).
(7) `states_to_planes` gives three toner bitmaps — the GT. (8) The route
asks the engine for those toners.

**And back.** Scan → addressing on C isolation, the R channel (§7b) → the
pose, C's → the page field per (face, PLANE) under F_C ≡ 0 (§7f) → three
channels per cell at their planes' offsets → the alphabet-masked QDA →
the chain calibration per colour lane (capture, level, page) (§2.7) → summed across
captures → the demap → per-stream decode → a certificate (page, ty, tx,
stream) → the sibling's conditioned decode (§7e) → the pooled close.

| a PLANE (C, M, Y) owns | a STREAM (hi, lo) owns |
|---|---|
| a toner, its photometry and its colour-model class | one LDPC codeword per tile and its rung |
| its registration page field (one per face) | its dither (domain 13, aux s + 1) |
| context bins (neighbour toner is the physical bleed) | its fountain quota / column-group share, its esi parity |
| furniture anchors: C from words; Y from words (and dust from p127, the balance law); M from dust | its metadata equation (counter·2 + s) |
| its death physics (a dead toner reads W) | its certificates and its tier-3 survival |
| refine.color, swim's per-plane affines, field templates | its calibration map(s), the conditioned demap's input or output |

**The answer, in one paragraph.** Rungs belong to STREAMS, never to
planes. A plane's quality reaches a stream's rung only through the label
map: lo separates W from Y and M from C, so the dominant W↔Y confusion
and Y's registration set lo's rung; hi separates {W, Y} from {C, M}, so
M's and C's registration against white set hi's. Hence lo is the weaker
stream on every c2 print, a BICM pair with lo at or below hi's rung is
the first-row shape (R4's probe r0775x0700; uniform r0700 the fallback),
and a conditioned r0850 pair conditions hi. A plane's DEATH
reaches the streams through the same map: Y kills lo, M kills hi, C
kills both. Registration is fitted per plane, certification decided per
stream; nothing may index one by the other.

## 5. What does not change (D12)

Every existing golden — keystream (`tests/holo/test_keystream.py`,
`test_color_keystream.py`, `tests/golden_keystream_vectors.json`), LDPC
edge digests, the metadata LFSR (`test_metadata.py:49`), fountain digests
(`test_holo_fountain.py:95`, `test_pooled_fountain.py:197`),
`test_pilots.py:34`, `P120_SITE_GOLDENS`, `ROW_VALUE_GOLDENS`, the
emission goldens (`test_gen.py:120-215`, `test_pooled_gen.py:93-150`,
`test_column_groups.py:410-479`, `test_lattice_gen.py:146-154`,
`test_fossil_seeds.py:132-181`, `test_ps.py:24, 129`), the receiver's
aux/domain pins (`test_h3_format_keystream.py:59-76`), sim shas; the
k/cmy7/cmy8 constructors and singletons (`src/holo/format/profiles.py:282-338`; the cmy8
stream = plane self-check `:310-314` stays cmy8-only); `COLOR_STREAM_AUX`;
domains 1..15 and their address meanings (none appended; domain 9's u
range extends past n_dust for the cmy word keys, R10, its dust draw
byte-identical); the site seed; the pooled fountain's n = 1 and uniform-width
bit-identities (`src/holo/core/fountain.py:52-94`); FORMAT_ROWS,
profiles, fossils, default discovery (`src/holo/format/registry.py:38-58`).
holo has no layout version (HOLO-DESIGN.md:37-38): the record's
"layout_version bump" (M281-COLOUR §6A) is a new Family token + gen v1 +
new goldens. Pins that MOVE, the cause in their dated ledger:
`ARITY_BY_FAMILY` (`test_h3_plugins_tiles.py:341-343`) [1, 3, 6] → [1, 3,
3, 6]; `GOLDEN_CALL_SITES` (`test_h3_conventions.py:554`). `AUX_BY_DOMAIN`
(`test_h3_drift_format.py:51-53`) does NOT move (R10: no domain 16; 9:
(0,) stands).

## 6. Generator changes (src/holo) (D13)

High level; `docs/CMY-GENERATOR-PLAN.md` turns it into waves. Every
mechanism is ADDITIVE (a Family value, a constructor, an int aux, a
disjoint u range on domain 9 — no new domain, R10 — PSDoc methods
defaulting off, manifest blocks only for cmy rows or non-default routes).

| group | file | symbol | today | change | size |
|---|---|---|---|---|---|
| (a) | `format/profiles.py:32-41` | `Family` | closed {k, cmy7, cmy8} | append `CMY = "cmy"` | trivial |
| (a) | `format/profiles.py:100-123` | `CodecProfile.__post_init__` | prefix alphabet; word/dust `in range(len)` | colour alphabet = a SUBSEQUENCE of `STATE_NAMES` (cmy7/cmy8's prefixes and cmy's `(W, C, M, Y)` alike), a derived `state_ids` property, membership checks; the dust-cycle requirement exempts `Family.CMY`; no new field | small |
| (a) | `format/profiles.py:80-83`; `format/pilots.py:189-203` | the word law | `word_states: tuple[int, int]`; `color_word_states` hardcodes `values * 3` | `word_states` stays `(W, C)`; the keyed W/Y '0' is `Family.CMY`'s rule inside `color_word_states(row_seed, counters, codec)` / `decode_color_word(states, row_seed, codec, …)` — the codec a REQUIRED argument, cmy7/cmy8 byte-identical; no new fields (simplified 2026-10-11) | small |
| (a) | `format/profiles.py:44-63` | `StreamProfile` | `fountain_aux` must equal `COLOR_STREAM_AUX[id]` | cmy streams carry `None`; no table growth | trivial |
| (a) | `format/profiles.py:199-218`; `format/pilots.py:206-245` | the dust law | cmy7/cmy8 missing-state cycles through `dust_state_values` | cmy: the PER-TILE balance law (R3 as amended 2026-10-11) inside `dust_state_values` — the tile's word supply counted from its rendered word states, lowest running total first, ties M, Y, W, C, then the domain-9 permutation as today; cmy's `dust_base_cycle` is `()` and the balance law is the family's rule inside the function, no marker; cycle rows byte-identical | small |
| (b) | `format/families.py:110-170` (pattern) | `cmy_codec(rungs=(r_hi, r_lo), p=120)` (new) | k/cmy7/cmy8 only; cmy8 zips `PLANE_ORDER` (`:144-152`) | two label streams hi/lo, banks `cmy-{s}-{rung}-p{p}-v1`, `state_ids` (0,1,2,4), the §2.5 word law, evidence 3, mapper 2/1, transmitted == payload-cells assertion; refuse p == 100 as `cmy8_codec` does (`:129-136`), with cmy's own reason beside it: under the word law M appears only in dust, so p100 leaves the M plane with no anchor (R12); do NOT zip `PLANE_ORDER` | small |
| (c) | `core/channel.py` (after `:154-182`) | `CMY_STATE_IDS`, label table + inverse, `cmy_soft_demap` (new) | presence-bit cmy8 map, pack7 | frozen table indexed (hi<<1)\|lo, inverse refuses ids 3, 5, 6, 7; the §2.7 demap with an optional known-sibling input; digest-pinned AND checked against G11's spec vectors | small |
| (d) | `core/color_tile.py:40, 239-283` | `cmy_encode_payload` (new) | `CMY_STREAMS = PLANE_ORDER`; stream i → presence column i | two dithered frames → label map → presence-id states; `cmy8_decode_stream` (`:315-338`) reused per stream unchanged | small |
| (e) | `core/keystream.py:316-345`; `gen/color_compose.py:89` | dither call | aux by plane NAME 1..3 at every call site | `dither_aux(row, stream_id)` = stream index + 1 on domain 13 (bit-identical for cmy8); `COLOR_STREAM_AUX` untouched | trivial |
| (e) | `core/keystream.py:283-287` (beside `color_dust_permutation`), `keystream_spec.py:89-93` | `color_word_zero_mask(seed, counter, n_dust)` → (100,) bool (new; NO new domain, R10; named at W0) | domain 9 drawn at u = 0..n_dust − 1 only (`pilots.py:206-245`) | domain 9 (aux 0, major = counter, v = 0) at u = n_dust + site (0..99), one 64-bit key per site (`keys64`, `:221-226`), the zero state Y iff the key's MSB is set; the dust draw byte-identical; a spec-mirror reference beside `color_dust_order_key`; golden vectors in both trees | small |
| (f) | `format/pilots.py:189-203` | `color_word_states`, `decode_color_word` | `values * 3`; decode {0, 3}; codec ignored | render through the family's word rule inside the function, which takes the codec/row (the per-site domain-9 preselection for cmy, R10; cmy8 byte-identical); decode on the hi bit with erasures, the lawful-set refusal kept (W0 2026-10-11: no `WordLaw`, no `strict`). The p120 helpers (`:137-154`, receiver `:110-127`) are the call sites of `P120_SITE_GOLDENS` and the drift pins — untouched | small |
| (g) | `format/lattice.py:65, 125, 177, 213-230` | `_DEFAULT_SITES`, arity, `parse_coding_id`, `_coding_for_id` | arity {1, 0, 3}; ×3 for CMY8; `else` = cmy8 (`:219-221`); pooled = CMY8 (`:230`) | CMY: default p120 (R12), arity 2, uniform ×2, rung token required, an EXPLICIT branch — the bare `else` would hand cmy's pair to `cmy8_codec`, which refuses it loudly (`families.py:124-125`): fail-closed, but the branch is still required; pooled = family in {CMY8, CMY}; grammar docstring (rung order = stream order) | small |
| (g) | `format/descriptor.py:158-161` | `Coding._validate_v2` | pooled iff CMY8 | pooled iff family in {CMY8, CMY} | trivial |
| (h) | `gen/color_compose.py:67-99, 184-190, 258-261` | `_payload_states`, the word call | gate (CMY7, CMY8); word without codec | a `Family.CMY` branch → `cmy_encode_payload`; pass the codec's word law; geometry, permutation, metadata bits, dust are generic | small |
| (i) | `gen/emit.py:129-155, 209-222, 307-319` | `_emit_color_volume`, the engine | gate (CMY7, CMY8); always `put_cmyk_bitmap`; `printer_id` recorded only | widen the gate; the engine's record picks the route — `cmyk1` as today, `rgb` = three `put_bitmap` calls with the engine's solid values (R23); GT, out-dir and jobid unchanged | small |
| (i) | `gen/ps.py:153-181` | `PSDoc.put_bitmap` | the K imagemask, `0 0 0 1 setcmykcolor` | an optional `rgb` colour (`setrgbcolor` before the mask); default None = today's bytes | trivial |
| (i) | `gen/manifest.py:92, 137-168` | `printer_id`, renderer block, word law | hardcoded DeviceCMYK renderer; `word_states` as the furniture law (`:156`) | `printer_id` = the engine; the renderer block says `cmyk1` or `rgb` + the three values sent; `state_ids`, the word law and the dust law recorded; stream-tier wording; `cmyk1` bytes identical (the K manifest golden, `test_gen.py:139-143`) | small |
| (i) | `cli.py:129-161`, `cli_gen.py:39-85, 128-152, 160-220, 250-252, 297-340`; `devices/profiles.py:67-89` | `--printer` (repurposed, R21), `fit`, tier label; `make_spec`, `get_printer` | `--printer` = legacy geometry beside `--coding`/`--profile`, refused beside `--format`; `make_spec` mints legacy specs; `registry -v` prices profiles and derives per-printer geometry through it; fit skeletons k/cmy7/cmy8 | `--printer ENGINE` = the emission engine on every `generate`/`capacity`, v2 and fossil (the engine's record picks the route; unknown engine refuses; no `--route`); `--coding`/`--profile`/`make_spec`/`get_printer`/the derived geometry RETIRED, `resolve_fossil_spec` the one legacy door, `PROFILES` listed as documentation; fit skeleton `<pitch>-cmy-<r_hi>[x<r_lo>]@TYxTX`; "stream tier" | medium (net negative lines) |
| (i) | `devices/registry.py:24-34, 46-126, 85-108` | `Printer`, `PRINTERS`, `hp-m281-ink` | no emission field; the `hp-m281` colour text "NOT usable on any route tried" (`:71`); `hp-m281-ink` the e028 clip-geometry pseudo-printer | two fields on `Printer`: the colour route it honours and the three solid RGB values (R9 as reduced by R23, R21): `hp-m281` `rgb` (e041), `xerox-altalink-c8245` `cmyk1`, a NEW Canon iR-ADV row `cmyk1`; `hp-m281-ink` DELETED; the colour text states e041's outcome; the docstring names the record | small |
| (j) | `gen/plan.py:45-47, 108-133`; `core/capacity.py:206-336` | pooled tiers | n-generic, n ≥ 2 required (`capacity.py:249-251`); "dead plane" wording | no arithmetic change; family-aware tier report (plane→stream map) | small |
| (k) | tests (new goldens only, never edit one) | see right | parity table, smoke list, families tests are k/cmy7/cmy8 | cmy rows in `P_AXIS_EMISSION_ROWS` (`c2-cmy-r0700`, `c2-cmy-r0775x0700`, `c2-cmy-r0700-p300`, all @10x10) and the colour smoke list (`test_lattice_gen.py:215-298`); cmy emission goldens at 10x10 for both routes; label-table, dither, domain-9 word-key and word-rendering goldens; `cmy_codec` row tests (`test_families.py`); G11's spec vectors; a ghostscript gate: render the `rgb` PS, threshold back to the plane GT, 0 differing dots (how e041 verified its jobs) | medium |
| (l) | `docs/FORMAT-SPACE-DISPATCH.md` | the behaviour table | authored for K/C7/C8, names retired `src/holo/receive` sites | re-derived for a fourth family BEFORE code (derive-don't-patch), enumerating every `else` that would route cmy to cmy8 | medium |
| (m) | `qualification/color_distort.py:486-523`; `qualification/color_synthetic.py:33-37` | M281 sim; the subtractive mix | ≤ 8 RGB colours, threshold 128; the default mix is the identity (C subtracts only R) | the palette passes as is; a named measured-mix parameter set (the §2.9 cross-talk) and an independent two-plane offset helper owed (generator W5) — not a `color_distort` profile — so the sims are not cleaner than paper (§7h) | small |

Two test-side K-vs-else branches (`tests/holo/test_lattice_gen.py:295`,
`test_backbone_payload_gates.py:86, 134`) take cmy into the colour path
CORRECTLY; listed so the build does not "fix" them.

## 7. Receiver changes (holo3) (D14)

The format-law dedupe is NOT done (`src/holo/receiver/docs/RECEIVER-MOVE-PLAN.md`
§6); R8, narrowed: dedupe ONLY identity, pilots, tile_codec and keystream,
or none — otherwise every format item lands in the receiver's copies too.
**Frozen at receiver W0, before any builder starts** (owned by
`src/holo/receiver/docs/CMY-RECEIVER-PLAN.md`, cited by the other plans):
`StreamFact` (CMY-RECEIVER-PLAN I-2: `plane_index`, `label_index`,
`dither_aux`, a `.plane` that RAISES on a label stream); knowledge as an
allowed-state mask `(N, 8)`, plane and
label views DERIVED (d); the evidence KIND (§2.7); the calibration
interface (R11 RULED: hi-first, the weighted logit PAVA entry, the per-map
fallback, the erasure law; I-6); the published `PlaneField` set and gauge table (f);
the API.md update. **Cross-plan rule:** `certified_projection` keeps
cmy8's `(bits, known)` return byte-identical, the allowed-state view an
ADDITIONAL accessor; every wave touching `color_sites`, `pilots`,
`StreamFact`, `tile_codec` or `keystream` also runs `pytest analyzer/tests`
and the analyzer null-proof slice (§8) — the receiver lane collects
neither, and the offline scorer's gate 2 reads the plane-major projection
(`measure/yask/_truth.py:139-175`).

**(a) Format copies.**

| file | symbol | today | change | size |
|---|---|---|---|---|
| `format/identity.py:13-16, 118-124, 425-427` | `Family`, `_DEFAULT_SITES`, `_RUNG_ARITY`, the p == 100 refusal | K/CMY7/CMY8; arity 1/0/3; cmy8 refuses p == 100 | `CMY`, p120, arity 2; the receiver's cmy branch refuses p == 100 as cmy8's does (R12, the generator's `cmy_codec` mirrored) | trivial |
| `format/identity.py:127-134, 149` | `StreamFact`, `FormatRow.word_states` | `plane` a required int (stream index for cmy8, `:217`; `PLANE_K` for K/cmy7, `:207, 211`); a word-state pair | W0's `StreamFact`; the §2.5 word law; readers that branch: `tiles.py:516`, `color_sites.py:134-135`, `plane_k.py:687-688` (CMY8-gated); `words.py:51, 114`, `tiles.py:568` K-only | medium |
| `format/identity.py:84-109` | `CMY_PLANE_ORDER`, cycles, mapper units | "a cmy8 row's three streams ARE the planes" | `CMY_PLANE_ORDER` physical-only (`fields.py:59, 152`); `ALPHABET`, `STREAM_BITS` per family, the cmy cycle, mapper 2/1 | small |
| `format/identity.py:202-260` | `_streams_for`, `_make_row` | zips `CMY_PLANE_ORDER`, aux 1/2/3; `else` = CMY8 (`:239`), word (0, 3) | EXPLICIT CMY branches. **BLOCKING — the silent path, refused FIRST**: with only `_RUNG_ARITY[CMY] = 2` added, an explicit pair (parsed at `:398`) mints streams 'C'/'M' (aux 1/2), the cmy8 dust and word (`:239-244`) and an UNPOOLED row (`:492`) whose close runs per-stream domain-14/15 fountains — garbage, no error | small |
| `format/identity.py:383, 409-437, 490-492` | expansion, `_require_constructible`, `mint_format` | ×3; column groups and pooled CMY8-only | arity-generic; CMY needs ≥ 1 dust; column groups and pooled for {CMY8, CMY} | small |
| `format/keystream.py:9-46, 185-188, 210-221` | dither; the word-zero keys | aux by NAME (`KeyError` on 'hi'); domain 9 drawn at u < n_dust only | every dither call passes `StreamFact.dither_aux` (`plugins/tiles.py:521`, `plugins/color_sites.py:132`, `analyzer/frame.py:354`, `analyzer/mother.py:64`, `analyzer/planeview/patches.py:322, 414`); the word-zero key helper beside `color_dust_permutation` (`:185-188`), domain 9 at u = n_dust + site — no new domain (R10) — drift-pinned | small |
| `format/pilots.py:151-164`, `format/tile_codec.py:11, 336-357` | word render/decode; encode/decode | ×3, {0, 3}; 3-plane presence | the §2.5 law REQUIRED, decode on the hi bit; `cmy_encode_payload` + the demap with the known-sibling input — the GT re-encode lives here ONCE | medium |
| `format/close.py`, `fountain.py`, `metadata.py`, `store_folds.py` | pooled close | generic in `len(row.streams)` | none for n = 2; the comment at `close.py:544-547` ("streams exactly {C,M}") | trivial |

**(b) Addressing.** One pass per capture fits the one committed pose —
one pose record per capture by design (`plugins/place_pass.py:82-92`) —
and binarizes at the window MEDIAN (the phase, `plugins/pose.py:466`;
the word bits, `median_radiometrics`, `:583-593`). Under the rotated
word Y must read LIGHT. On the S14 bars (refutation-marked, §2.9) C
darkens R by 0.80 of white, M by 0.07, Y by 0.01 — R is a near-pure C
readout, no unmixing — and the word margin, C vs Y as '0', is 0.79 of
white in R against 0.54 in (R+G)/2 and 0.21 in equal luma (C 130 vs
Y 179). **R7, RULED 2026-10-09 (owner): C isolation — the R channel, a
per-family constant (cmy (1, 0, 0); K, cmy7, cmy8 keep the exact
equal-channel call, `lib/decimate.py:283-291`) — for BOTH the addressing
pose and the word bits; not (R+G)/2, not equal luma.** The pose fitted
on R is C's pose exactly, hence F_C ≡ 0 (f). **The thresholds follow**
(receiver W2): in R only C is dark — a quarter of the payload and about
half the word sites — so the window median lands inside the light
cluster, between M (0.93) and W/Y (0.99); `_fit_phase`
(`pose.py:447-499`) thresholds at the row's known dark fraction (or
between the two modes) for cmy, one rule in one function, the lattice
fit (gradients, `:388-427`) unchanged; the word bits are thresholded on
the WORD-SITE population (~50/50 by the scrambled codeword), not the
whole-window median. The channel reaches `place_pass._crop_luma` and the
platen backing (`intake.py:66-75`; `pose.py:321, 608`); **the survey
keeps equal luma (`survey.py:126-133`; the owner decides from G10's record).** Inferred, not
measured: the pose-mix arithmetic and the threshold claim come from the
M281 bar RGBs; the AltaLink's C/R contrast is not in the committed
extract (G10 covers X10/X11). `words.py` has no per-family channel or
dark table today; both are PLANNED (I-9). A fact snapshot carries no
version stamp or guard (`snapshot.py:20-22`): a resume across a channel
change would fold old poses in SILENTLY. **The dust reference is
mandatory work, whatever the channel** (not R7's choice):
`reference_page` writes dust by `INK_COUNT ≥ 2 → dark`
(`plugins/words.py:30-34, 106-110`) and the pose correlates over word AND
dust sites (`pose.py:646-657`), so every single-toner M dust cell would
be labelled light — 20 of 120 sites (p120's all-M dust, the balance law)
anti-correlated per tile; a per-family "dark in the addressing channel"
table (cmy: C, M) replaces the ink count. **Two R7 follow-ups found in
recording (2026-10-09), put to the owner:** (i) in R the M dust reads
0.93 of white, so at a word-site threshold (midway between C and W/Y) a
"dark" label on M dust anti-correlates 20 sites per tile — under R7 the
recommendation is to EXCLUDE dust from cmy's addressing reference (the
100 word sites carry C vs {W, Y} with a 0.79 margin; M dust carries a
0.07 margin in R either way), not to label it light; (ii)
`median_radiometrics` runs in `sample_segment` before stage A, so the
word-site population is unknown at cold start — the cold threshold is
the R-channel QUANTILE at the row's dark fraction (the same rule as
`_fit_phase`), and the word-site median applies only in the chain and
refine stages once the tile origin is known. The pose on R is C's to
within M's 0.07 cross-talk, not exactly.

**(c) Colour model and calibration.**

*How cmy8 does it (the owner's question).* At EVIDENCE time, per
colour lane (capture, level, page): a QDA on the &1 search side of the furniture, words
included (`color_region_head.py:222-247`); each plane's raw marginal
calibrated by a per-plane PAVA on dust plus prior-barrier certified cells,
words EXCLUDED ("structured W-heavy population", `:237-241`), floors
6 / 2 / 3 (`color_model.py:22-24, 339-385`); an unsupported plane emits
exactly 0.0 (`:396-408`); the stored evidence is three calibrated
marginals and the union sums them (`tiles.py:382-395`). Conditioning on a
certified sibling is A4b (`plugins/color_conditioning.py`), a supplemental
u-lane arm: maps STRATIFIED per (plane, conditioning pattern) — "a 2-vs-2
log ratio is a DIFFERENT statistic" — from CERT-CROSS cargo plus
furniture seen through the `&12` reveal field, floors 40 / 6 / 20, A3's
single held-out pre-gate, the region gate bypassed (`region_gate_forced`:
it refused on the DUST leg at all fourteen conditioned lanes, `:58-68`),
its selection bias a registered compromise. cmy7 carries relative scores
through a head (scale + six offsets) on the QDA's held-out rows split
again by &2 (`color_model.py:585-612`), the L∞ bound last. The
multi-state affine head (`Cmy7Head`) is not a cmy consumer (dropped
2026-10-09); an affine refinement on top of the chain maps, if R11 ever
wants one, gets its own name.

| file | symbol | today | change | size |
|---|---|---|---|---|
| `plugins/color_model.py:57-60` | `_CMY8_STATE_BITS` | one table as plane bits AND stream bits | `PLANE_BITS` (universal) + `STREAM_BITS[family]` (cmy8 = identity; cmy = {0:00, 1:11, 2:10, 4:01}) | small |
| `plugins/color_model.py:128-212` | `fit_qda` | classes 0..n−1, an empty class degenerate; collapse clipped by PRESENCE-bit XOR (`:176-189`) | alphabet-masked, presence-indexed (outside columns −inf); collapse re-keyed to LABEL space for cmy (W/Y, C/M → lo; W/M, C/Y → hi) — the presence XOR clips "plane 2" for W/Y and the HEALTHY lo for a dead M | medium |
| `plugins/color_region_head.py:222-253, 309-338` | `fit_detector`, `evidence_with_divisor` | `n_states = 7 if CMY7 else 8`, missing-state check over every id (every cmy region refuses); the cmy7 path refuses the region on any clip (`:251-253`) | checks over the alphabet ids; a cmy branch QDA → (context) → the chain calibration (§2.7) → L∞ bound, three scores out; a clip NEVER refuses a cmy region — the clipped stream is erased in score space (unsupported lo: sY := 0, sC = sM := L_hi; unsupported hi: sM := 0, sC = sY := L_lo) | medium |
| `plugins/color_model.py:260-280`, `lib/pava.py:331-339` | PAVA | `fit_component_pava` balances the BINARY classes internally, takes no weights; `class_balanced_weights` is per STATE (n 7) | a NEW weighted entry point, cmy only, STATE-balanced to the payload prior (1/4 each), its maps EVALUATED by interpolating the PAVA nodes in LOGIT space (linear in score between nodes, flat beyond the end nodes; R11 — `PavaMap.llrs`' probability-linear interpolation, `color_model.py:253-257`, costs 0.02–0.12 bit on near-separable pairs); cmy8 stays on `fit_component_pava` and `PavaMap`. It removes the within-class tilt: from furniture (p120, the balance law) hi's class 1 is C 50 : M 20 (M ~29 % vs the payload's 50 %) — a crude log(share/0.5) of −0.6 nats at the boundary until cargo dilutes it (inferred); lo's class 1 C 50 : Y ~25 (−0.4 nats) is lo-first's L_lo, not a map of the ruled chain; pinned by a synthetic C-heavy fit recovering the payload-prior map; measured +0.006 to +0.013 bit on the lo marginal (within ±0.003 of zero on the hi marginal, no interval below zero) over the class-balanced fit cold, bit-identical to `fit_component_pava` under class-balanced weights | small |
| calibration population | the chain maps | — | held-out (&1 == 1) furniture + certified cells read from the store at fire time, WORDS ADMITTED (K's rule; p120's dust is all M, so W, C and Y labels come only from words until certificates) and disjoint from the QDA's own 53 training word sites; state-balanced in the weighted entry; marginal map under 6 / 2 / 3, conditional maps under A4b's 40 fit labels / 6 per class + a DISJOINT 20-cell validation set (`color_conditioning.py:99-101, 386-409`) (R11) | small |
| `color_region_head.py:292-306` | region adoption gate | three-way, word and dust legs | cmy8's three-way gate as it stands, every leg published (R11, RULED 2026-10-10); cmy's dust leg is SINGLE-CLASS at p120 (all M), measured ≈ 0.2 of the three-way gate's refusals; the leg structure re-examined after the sim measures each variant's refusal rate (G13) — measured constraint: adopting maps on cold regions (≤ 8 tiles) LOSES; a gate that refuses cold and adopts at page scale ties the raw fallback cold and gains on pages | small |
| `plugins/color_pooled.py:162`, `color_arms.py:102-107` | `pooled_cell`, `arms_for_family` | CMY8, else the cmy7 path; CMY8 → A3 + A4b, other colour → A3 | family tables (cmy: the unpinned matrix over the alphabet; A3; A4b's stratified shape only if it pays — the conditioned decode itself is the `tiles.cond` row, R5, §7e) | small |
| `plugins/color_model.py:632-679`, `color_sites.py:98` | `reference_states`, projection furniture | words ×3 = CM | take the row [corrected 2026-10-11] (else every word site is CM, outside the alphabet) | small |
| `plugins/color_region_ctx.py:115-140, 318-375, 434-568` | `state_bits`, provisional ink, losses, curves | prefix `arange(n)`; stream LLR > 0 read as PLANE ink | iterate the alphabet; bins PLANE-native from the state posterior; the 4-ary neighbour-state context and per-hypothesis sampling measured (§2.9c, d) | medium |

`:222-253`, `color_pooled.py:162` and `color_arms.py:102-107` are what an
unhandled `Family.CMY` gets today: no crash, wrong behaviour.

**(d) Knowledge.** `WindowRows` carries the allowed-state mask; the PLANE
view is DERIVED, only true zeros (hi=0 → C=M=0; hi=1 → Y=0; lo=0 →
C=Y=0; lo=1 → M=0; both → the state), and the LABEL view likewise (bit s
known iff every allowed state agrees). Writing label bits into plane
columns, as `certified_projection` does for cmy8
(`plugins/color_sites.py:134-135`), would FABRICATE known C ink at M
cells — silently.

**(e) Certification and the two-stage demap.** An EXPLICIT CMY attempt
branch beside `_attempt_cmy8` (`tiles.py:510-558`): independent
per-stream (BICM) decodes from the summed scores in every ordinary stage
(`attempt_many`, `:698-713`). With a sibling certificate standing, the
other stream's conditioned forms are LINEAR in the summed scores, so they
commute with the cross-capture sum (under the hi-first chain, R11, lo|hi is
a calibrated map, hi|lo derived — measured equal to the fitted forms
within 0.003 bit under the logit evaluator (0.0005 with certified cells)). **R5, RULED 2026-10-09 (owner):** the
conditioned decode is a PRICED STAGE of the tile row in the family of
`tiles.scan` / `tiles.retry` — not a flag or dial, not a residue stage
at the top of the ladder, not in-job conditioning behind a switch. Row
`tiles.cond`, subject (page, ty, tx, stream). BORN by the stream's own
failed `AttemptFact` (as `tiles.retry` is born) AND the sibling's
`Certificate` in the window, whichever lands second. READS `attempt` and
the sibling's `tile` key: the certificate fold already emits (KEY_TILE,
page, ty, tx, stream_id) (`store_folds.py:973-975`), so the subscription
is DIRECT, as local_ctx / planek / swim subscribe to neighbours'
KEY_TILE (`local_ctx.py:899`, `plane_k.py:798`, `swim.py:727`); it does
not wait for the colour region's refit. PRICE: ordinary payload work,
PAYLOAD_COST 20 + RUNG_COST 2 × rung ordinal, the scan/union/retry
formula (`tiles_sched.py:41-42, 227, 252, 325-326`; SCHEDULE.md's ladder
lists those three at 20), never the 210–220 residue band (`tiles.uplift`
210·n, `tiles.local` 220). WORK: the stream's attempt with §2.7's
conditioned demap, the sibling's bits read from the window's
allowed-state set (I-4, CMY-RECEIVER-PLAN §3 — CUT in the plan's v0.2, 2026-10-11 night: the existing (bits, known) arrays carry a cmy certificate's knowledge losslessly through the true-zero table, review 3.6). RE-ARM: the tile-lane
generation, as every stage (`_scanned_at`, `tiles_sched.py:89-97`;
`_retry_eligible`, `:298-313`): a later capture, a field re-solve or a
region refit bumps the generation and the stage runs again at the new
one, at most once per generation. PRODUCES `AttemptFact | Certificate`,
an ordinary certificate; whichever stream certifies first, by any stage,
births the other's cond, so BOTH ORDERS fall out of one row. G13 stays
the gate (both orders, negative arms); the engine test is the row's
born/arm set. A4b's stratified shape at n = 2 (stream × {none, sibling
0, sibling 1}) for the derived direction only if it pays. *cmy8,
corrected* (v0.2 said a sibling that certifies later never re-arms the
stream; wrong): the colour region row reads KEY_PAGE_CERTS
(`color_region.py:765-771`), so every certificate re-arms its
`color_refit` (160 × head fits, `:58-67, 822-835`), fitted to the whole
certificate set (certified cells join the dust as PAVA labels,
`color_region_head.py:237-240`; certified planes enter the window as
known bits, `certified_projection`, `color_region.py:143`); the refit's
new evidence rows bump the tile-lane generation (`_advance_tile_lanes`,
`store_folds.py:888-909`, INV-G1), which re-arms `tiles.scan`, and a
tile with two of three planes certified keeps emitting
(`color_sites.py:46-50`). cmy8 lacks only the conditioned DEMAP; its
re-arm exists, indirectly and at refit latency. A
conditioned attempt re-verifies with the stream's own CRC: a wrong
sibling (never observed) is BOUNDED by the CRC-32 false-accept rate, not
excluded (conflicting certificates are fatal, `tiles.py:602-618`), and
the conditioned shape puts hi at r0850, the rung with the CRC-caught
syndrome floor (§2.4). D1's alarm is unchanged. *Built 2026-10-12
(receiver A6): `tiles_sched.COND_DESCRIPTOR` and `prepare_cond`, stage
`tiles.STAGE_COND150` (the retry's budget); the file:lines in this
paragraph are the 2026-10-09 tree's.*

**(f) Page field.** The gauge must follow the ink the POSE is fitted
from: readers sample each plane at pose + F_p and the per-window nuisance
t_w is applied by nobody (`plugins/color_region_anchor.py:127-165`).
cmy8's code states its premise ("the pose is fit from that ink, so it
sits between C and M by construction", `lib/plane_field.py:58-62`) and
hard-wires F_C + F_M = 0 (`:532-539`, `:719`) — on a cmy page M = −C,
false. **R7, RULED 2026-10-09 (owner): F_C ≡ 0, M and Y free (relative
to C); no weights, no weighted gauge, no G10 weight measurement.** The
addressing pose is fitted on C isolation (b), so it IS C's pose, exactly.
Under a mixed channel it would be a blend, not C's — the lattice from the
whole window's gradient, the phase from all cells against the median,
the patch refinement over word AND dust sites (`pose.py:388-427,
447-499, 730-806`), ~0.6 : 0.4 C : M in (R+G)/2 (bar arithmetic,
inferred) — which v0.2's recommended w_C F_C + w_M F_M = 0, weights from
G10, was there to absorb; withdrawn. In the per-plane (field column,
coefficient) table cmy8 (C +1, M −1 on column 0; Y column 1) stays
byte-identical; cmy C has no field column (coefficient 0: its rows inform
only the window nuisance), M on column 0 and Y on column 1, each free;
the C `PlaneField` is published as the zero field, so the analyzer's AI3
(a zero delta collapses to `committed` by name) reads it as committed by
name. Y stays out of the gauge (R reads Y at 0.01 of white): the
three-plane centroid PAGE-FIELD-DESIGN §2.3 refused never forms. Every
per-plane registration mechanism then measures its plane's displacement
FROM C: `fields`, the region head's registration arm
(`color_region_head.py:410`), `refine.color`'s per-plane sampling deltas
(`color_refine.py:207-229`), `tiles.planek`'s field-corrected read with
its x-only sweep (`plane_k.py:132-138, 359`), `tiles.swim`'s local
affine per plane per window (`swim.py:12-19`), and the analyzer's
per-plane poses (A3). `_plane_known` (`:776-787`), `fields.moved`
(`fields.py:255-260`) and the analyzer's per-(page, plane) read
(`analyzer/fixedpoint.py:160-168`) follow the W0 table. *Templates.* A
furniture template correlates ONE
channel per plane (`field_tiers.py:255-277`; `fields_collect.py:181-199`
→ `color_region_anchor.sample_plane`, `:96-109`): M dust in Y's template
(B, ~79 % of Y) and C words in M's (G, ~49 % of M) are labelled 0 yet
carry another plane's displacement — so a per-family cross-talk weight
table (weight 0 there; `measure` takes weights, `:383-410`) or unmixed
channels (`lib/spectral`), and §2.5's anchors become effective counts.
2026-10-12 (receiver A5, measured on the offset c3 stimulus at the
render's own pose): a THIRD zero, C in Y's template — C darkens B by 19 %
of Y, and tile (0, 0)'s furniture holds 48 C word sites against 26 Y
sites (39–62 against 17–35 a tile over the page); with the two zeros
alone Y's template read 0.81 dots past the plant. And the CERTIFIED
templates take the same weights: unweighted, C cells' 25 % share of a
certified tile read M 0.79 dots past the plant
(`field_tiers.CROSS_TALK_STATES`, CMY-RECEIVER-PLAN A5). A
certified template needs BOTH streams (`:223-252`), and lo is what fails
when Y is misregistered; the missing lever: on a hi-certified tile the
hi=0 half (~2,000 cells) is W vs Y, a clean two-level split in B — blind
W/Y bits there make a Y registration template (lawful in registration
templates only, `color_model.py:29-33`); lo=0 is W vs M in G. Measured
before relied on. *Registration at c2* is carried by the page field
(a smooth solve, the prior over the unmeasured region — 2.24 dots,
`field_tiers.py:165-180`, bounds what one tier's correlation SEES, not
what the field publishes), refine.color, and the swim (a per-plane local
affine within ±1 cell of the field's own value, `swim.py:138-150,
243-253`), measured together at 4.5 dots on the swim stimulus (field
alone 200/300, with swim 297/300, conversion_docs/MEASUREMENTS-2026-09-03.md;
PLANE-FIELDS §6.6); e041's c2 medians (|Y−C| 0.49 / 0.67 / 1.13 / 2.35
dots at 2.82 / 3.86 / 4.00 / 6.54 %, one print each, §041.5p) say c2
error tracks registration, not that any band is unreachable; R4 reads
U12 as "go down" (r0700 / r0700x0625). No reach promise (R17 DISCARDED).

**(g) Residue rows.** planek stays CMY8-only (`plane_k.py:721, 762, 804`);
its cmy analogue is §2.9b's K view; swim's floor sized by the alphabet
(`swim.py:174-190`); `tiles.local` and uplift-A3 unchanged; the readout
counts STREAMS (`diag/readout.py:48-57`) and gates field rows on family,
not `len(stream_ids)` (`:318`). [2026-10-12: the first sentence predates
R25 as receiver plan v0.3 reads it — planek is TRANSLATED for cmy, a label
stream read as the sum of its toners' isolated presences
(`receiver/plugins/plane_label.py`), and kview stays §2.9b's parked row
(R25a); as built in CMY-RECEIVER-PLAN A7.]

**(h) Sims and lanes.** A cmy stimulus set in the fixture cache (BICM at
10x10, the c2 row, dead-Y/M/C, the conditioned pair; `_h3_sims.py`
`:245-440`); `CACHE_KEY_INPUTS` (`test_h3_conventions.py:321-339`),
`GOLDEN_CALL_SITES` (`:554-598`), SCHEDULE.md. **G12 needs new
rendering:** `_h3_sims` displaces ONE plane along x in WHOLE dots
(interpolation blurs as well as moves, `_h3_sims.py:13, 437-446`) through
`render_color_scan`'s identity mix (`qualification/color_synthetic.py:33-37`);
sub-dot, two-plane, fragment-varying offsets need its fractional
`offset_xy` / `y_drift_xy` (`:44-52`). So: 0.5-dot steps as whole-pixel
shifts at `UPSAMPLE` (or interpolation with a zero-offset same-blur
control), `subtractive_rgb` from the measured bars, a 2–6-tile crop as
the K mixed-holes sims do, every new parameter keyed into the cache.

## 8. Analyzer changes (D15)

Order of work, a cmy8 NULL-PROOF after each step; the analyzer workplan
(`analyzer/CMY-ANALYZER-PLAN.md`) carries the waves. Today a hard gate
makes the analyzer cmy8-only (`analyzer/inputs.py:343-346`) and one table
identifies stream with plane (`analyzer/types.py:24-25`).

**Step 0, the null-proof instrument and lane (startable now).**
"Byte-identical ledgers" cannot hold and no comparison exists in
`analyzer/`: timing fields (header `seconds`, `fixedpoint.py:1088`; row
`diag.seconds`, `:974`; rung and mint `seconds`, `passfiles.py:70, 130`),
a per-process `pass_token` (`:795-798`), thread-order `mints.jsonl` and
`row_seq` (`ledgerio.py:140-200`), re-attacked keys written twice, a
wall-clock checkpoint, and float evidence reproducible only on one host
and BLAS (the walk-eval Δ ≈ 1e-12). So `analyzer ledger-diff` streams the
latest row per key and compares verdicts, certifying rule/rung/arm, user
bits, generation, predecessors, rung outcomes, blind evidence details and
n_discriminating_labels EXACTLY; excludes non-semantic fields by NAME
from a pinned list (a test fails on an unclassified new field); requires
a same-host baseline. **The lane (analyzer A0 hygiene; R18 DISCARDED 2026-10-10 — not a cmy ruling):** the I/J run dirs are `scratch/`
paths absent from a worker checkout (`analyzer/tests/_analyzer_fixtures.py:37-48`)
— their tests SKIP, so a green lane proves nothing about cmy8: a flag
makes absence a failure; a fixture-free cmy8 null-proof is built from a
cmy8 sim decode in the receiver fixture cache with a deliberate residue;
the bounded sheet-I residue test (22 keys, `test_analyzer_fixedpoint.py:555-575`)
is the real-pixel digest where the fixture exists; full H/I/J passes are
owner-hours at steps 2, 3 and 5 (baseline and candidate).

| step | file | symbol | today | change | size |
|---|---|---|---|---|---|
| 1 | `analyzer/alphabet.py` (new; imports only `holo.receiver.format`) | the blind family DESCRIPTOR | `STREAMS`/`PLANE_OF` (`types.py:24-25`), `oracle.py:264`'s private literal, `planeview/row.py:51`; three private word renderers (`residue.py:131` in `_furniture_only`, `arms.py:881`, planeview; the {0, 3} assumption at `planeview/row.py:132`, `planeview/patches.py:425`) | alphabet as presence codes, label map, stream ids and order from `row.streams`, the planes each stream's decision touches, the §2.5 word law (every renderer reads it), `sibling_state`, the discriminating predicate (cmy: hi ≠ lo, i.e. M and Y — Y word sites ~25 per tile plus all 20 dust (all M at p120), ~45 per tile, ~101 at halo 16; the SAME mask for both streams), default halos keyed by stream id (`types.py:841, 865, 915`; `HALO_CELLS` C/M 16, Y 32, `residue.py:67`; cmy takes the halo cmy8 gives its non-scarce planes, 16 for BOTH streams — cmy has no scarce stream, the smaller class ~45–50 cells per tile in both (§2.5) — 48 where the wide profiles widen, an operator axis (`--halo-cells`), no bar (RA-1, folded into R11 2026-10-10); cddcb87 moved the patch family's C/M halo 48 → 16 (`_PATCH_HALO`, `types.py:915`), Y 32 before and after), the L7c erase state (not 3, `ladder.py:504`), mixture-mode applicability (none, `patchfit.py:45`), word-arm applicability per PLANE (`types.py:622-627`). Ruling 11's word-site exclusion (`statecal.py:35-37, 145-163`; `patch.py:65-67, 455-456`; `calibrate.py:614-619`) becomes a COMPUTED predicate: drop a (site kind, sibling state) train population only if it is single-class under the family's word law — cmy8's rule exactly; for cmy word sites stay in lo\|hi=0 (W vs Y) and hi\|lo=1 (Y vs C), drop in lo\|hi=1 (C only) and hi\|lo=0 (W only); a table test per family; DESIGN §14 amended. Consequence (analyzer F1): with p120's dust (all M under the balance law) the analyzer's hi\|lo=0 and lo\|hi=1 per-state maps are one-class on furniture and fall to the pooled map until cargo, while production admits the same word rows (R11, state-balanced) and stays two-class — a deliberate divergence (ruling 11 guards per-state priors in the analyzer); that drop is cmy8's own behaviour in exactly this situation (target C: sibling state 0's word rows all W and its dust only C, state 1's all CM and its dust only M; `statecal.py:145-166` drops them and two of four per-state maps fall to the pooled map), carried over (RA-7, folded into R11 2026-10-10). Census arithmetic recorded: select-fold minority on a furniture-only footprint ≈ 8–11 against `SELECT_MIN_MINORITY` 40 (`calibrate.py:78, 82`) — arm selection refused cold until a neighbour is certified in BOTH streams, about cmy8's own cold behaviour | medium |
| 2 | `analyzer/frame.py:359-469` | `KnownFrame` | `(n, 3)` plane bits; the BLIND run-abort assertion in plane space, `known[inside, plane]` (`:417-425`), before the metadata injection (`:427-439`) | the allowed-STATE set with DERIVED plane and label views; the assertion in LABEL space, computed from the intersected allowed set (bit s known iff every allowed state agrees), never from a stored label mask — a plane-form write (C = 1 where lo = 1) determines hi with no label column written. Three mutation tests: a direct target-certificate leak, a plane-only inferential leak, and a sibling-only frame that must NOT fire (the existing test poisons with the target's own certificate only, `analyzer/tests/test_analyzer_frame.py:108-122`). Metadata injected as a label constraint. Every TARGET-LABEL read switches to the label view (`frame.py:444`, `patch.py:262-263`, `field2.py:459`, `autoknobs.py:881-888`, `patchlocal.py:190`, `unmix.py:391-414`, `arms.py:733, 1010-1016`); `residue.discriminating_mask` (`residue.py:141-153`, C/M/Y literals) moves into the descriptor. For cmy8 the allowed set is the product set — today's arrays byte-for-byte | large |
| 3 | `analyzer/arms.py:1188-1485` (`:1216`) | `evidence_for` | `plane = PLANE_OF[stream]`, one pose, one plane score | split: a per-PLANE pose stage (field/offset/affine/word/field2 per toner plane on the plane view; the word arm gives a C-plane pose; field2 re-keyed by plane with a target-free furniture frame) and a per-STREAM score stage (the generalized `head`, `unmix.py:330-368`: a restricted 4-state demapper evaluating each state hypothesis at its own plane's pose, marginalized through the label map, restricted by the other stream's known bit). Poses are NOT shared between a tile's hi and lo keys — each key's frame hides its own stream (`frame.py:207-239`), so a pose memo keyed without the target would leak; test: a poisoned cross-stream pose memo fires the assertion. Cost: three pose fits per key × two keys against cmy8's one per key (§9). The STATE model is separated from the per-plane projections: `spectral.fit_plane_mix` refuses only an exactly singular gram (`lib/spectral.py:143-170`); on noisy data a dead toner's column is small noise, ACCEPTED, its functional amplified noise — so a plane is gated dead on `PlaneMix.plane_snr` (`:96-100`, unused as a gate today) below a floor set on the dead-Y/M sims and recorded (a mechanism constant, not a bar, R19) — no receiver dead-stream fact exists (CMY-RECEIVER-PLAN I-1…I-11) — the dead stream refused BY NAME (lo for dead Y, hi for dead M), the other kept; dead-toner RECOVERY excluded from the first cut. Per-plane poses were the c2 lever (R9 3.86 % per-plane vs 7.0 % single-pose, e041 §041.5k; S14 B3's 2.82 % is per-plane, S14 prints no single-pose figure — the 4.73 % once cited here is U14 c2-K, §041.5p); the linear mixing model is exact for one-hot states, so W8's third-layer nonlinearity cannot occur. Three `sample.read_rgb` reads (`sample.py:515`), one per plane pose, its contract unchanged | large |
| 4 | `analyzer/statecal.py:73-123`; `combine`, `patch`, `pure`, `ladder` | sibling state, N_STATES | two sibling PLANES, 4 states | the other stream's known bit, 2 states; combine/patch/pure/L7c loop over the descriptor's N; the `mixture` mode and the `conditional` arm (`unmix.py:371-422`) REFUSED for cmy until re-derived. Policy: pure's F2 rule ("unknown sibling state = erasure", `pure.py:441-445`) would erase the WHOLE first stream of every tile | medium |
| 5 | `analyzer/fixedpoint.py:596-625` | `_retarget` | a certificate re-targets the tile's other streams (`:616-618`) and the 8 same-stream neighbours (`:619-625`), family-agnostic | the two-stage decode comes from this fixed point once the frame carries sibling-STREAM knowledge. FOR cmy ONLY (a descriptor flag, False for cmy8) also re-target the 8 neighbours' other stream — 16 neighbour keys + 1 per mint against 8 + 2 (§9); cmy8's set unchanged, its ledgers semantically identical (step 0). `_plane_field` (`:160-168`) hands all three planes' fields per W0's published set | small |
| 6 | `analyzer/oracle.py`, `truth.py`; `measure/crop_parity/_gt.py`; `measure/yask/_truth.py`, `_paths.py` | offline scoring | `oracle.py:264` plane literal; `_gt.reconstruct` refuses any family outside (CMY7, CMY8) — fail-closed, its pooled body n-generic (`_gt.py:123-126, 128-195`); gate 2 compares `certified_projection` with the plane-major field (`_truth.py:139-175`); `SCRATCH_IN` is machine 4's `scratch` (`_paths.py:28`) | oracle maps the emitted plane GT → states → label bits; `_gt` admits CMY with a stream-list test at n = 2 and column groups; gate 2 through the plane view (or the allowed-state view once (d) lands); a sim-dir-aware truth loader independent of machine 4 path. These `measure/` files are in the analyzer plan's seam map, with an owner | medium |
| 7 | `analyzer/planeview/row.py:143` | plane view | refuses non-CMY8 | keep refusing cmy (research door); `patches.py:265` files metadata at the PLANE index, right only for cmy8 | trivial |
| 8 | `analyzer/inputs.py:343-346` | family gate | `is not Family.CMY8` → refuse | flip LAST | trivial |
| 9 | `analyzer/tests/test_analyzer_fixedpoint.py:88-200` | the BLIND import-closure test | walks `analyzer.*` only; every other import skipped | the rule by GT DOOR, transitively — through `holo.receiver.*` too, since the dedupe (R8) may make receiver format modules import `holo.format`/`holo.core`: forbid `measure.*`, `holo.gen.*`, `holo.format.resolve` and any payload/manifest reader from run modules; allowlist the format law the dedupe may share (`holo.core.keystream`/`channel`, `holo.format.pilots`/`profiles`); a mutation test (a run module importing `measure.crop_parity._gt` fails it). Today only `truth.py` reaches `measure.*`/`holo.format` (`truth.py:91-93, 119-120, 187`) | small |

**Label supply** (inferred; in expectation, the per-tile Y count binomial
under R10): at halo 16 (~2.25 tiles) the dust plus Y
words give ~45 M and ~56 Y cells, over `spectral.MIN_PER_CLASS` = 25 (full
rows, `src/holo/receiver/lib/spectral.py:65-66, 143-150`) on furniture
alone. Close and export are row-driven and n-generic
(`analyzer/close.py:183-278`; `export_facts.py:313-343`): no change.

## 9. Costs and limits (D18)

- **2 b/cell vs cmy8's 3** at equal rung and pitch, the price of SOLID
  cells (dot-mixed rows carry more at c3, are closed at c2 on both
  engines, e041 §041.5o, e042 §042.4). **C death is fatal**, the words'
  '1' with it; tier 3 holds at q ≤ 1/2 only; the metadata trust floor is
  a FRAGMENT-SIZE cost, 24 healthy tiles against cmy8's 16 (§2.6).
- **c2 is print-registration-limited** (2.8–6.5 % over |Y−C| 0.49–2.35
  dots; X10 2.85 % at ~0.6). Levers: the per-plane field, context, and
  4800 dpi as a RECEIVER lever — S17's "no cell-state change" describes
  the context-free classifier, while 4800 bought the sub-dot pose (U4–U6
  4–8 pp, e041 §041.5p) and e034's added 4800 capture 14 of the last 17
  tiles. Registration is carried by the field, refine.color and the
  swim, together measured at 4.5 dots; no reach promise (§7f, R17).
- **The c3 page is ladder-capped** (6,734 fountain bits per site); **M has
  no word ink** (20 dust anchors at p120); one stream's certificate gives
  no plane template (§7f). **Successive demapping** reopens COLOR-DESIGN
  §4's out-of-scope MLC decoding on the decoder axis; a conditioned pair
  loses COLOR-DESIGN D2's independence and that stream's tier 3.
- **The evidence** is context-free supervised readout: five c2 prints on
  two engines, one per condition. **Engine reach**: the M281 is the
  customer; the AltaLink the floor and registration control (read); the
  Canon untested (e040); the VersaLink has no colour route, the M681
  untested (e039). **Analyzer cost** (estimate): ~2× cmy8's registration
  work per tile (three pose fits per key, two keys) and a fan-out of 16
  neighbour keys + 1 per mint against 8 + 2 (§8).

**Build cost against yield** (R20 DISCARDED 2026-10-10: cmy is the line
being built; the dot-mixed cmy8 route is §9.1's future exploration; the
numbers stay as single-print estimates). M281 single-print estimates, A4-4mm, 10 % repair (e041
§041.5o; M281-COLOUR §5):

| row | measured | est. net / page | reuses | generator | holo3 | analyzer |
|---|---|---|---|---|---|---|
| c3 cmy8 via a dot-mixed route | 3.2 % (S16 T2), 3.65 % (S17 U1) | ~0.95 MB, 136 b/mm² | cmy8 rows whole | the route | cell-model check (CMY cell 85 %) | route-aware truth |
| c3 cmy7 dot-mixed | 0.54 % (S17 U2) | ~0.86 MB, 124 | cmy8's three streams + the parked erasure row's allowed-state law (design only; its own spelling, §2.0) | small | erasure demap + cell model, small | small |
| c3 cmy7 dot-mixed + orientation | 2.4 % / 2.1–2.8 % (S17 U7); orientation 0.98 % on the AltaLink (X8, e042 §042.4) | ~1.0 MB, 144 (186 discernible) | its orientation bit is a stream over a DATA-DEPENDENT 3/7 of the cells — the stream≠plane split, harder than cmy's | large | large | large |
| **c3-cmy** | 0.06–0.33 % | ~0.63 MB, 91 — lossless | the fourth family | medium | medium–large | large |
| **c2-cmy** | 2.8–6.5 % | ~1.2 MB, 167 at registration ≤ 1 dot; ~130 at 6.5 % | the same family | — | + field, refine.color, swim, context (§7f) | — |

cmy's unique value: the lossless c3 page as archival-grade colour on the
engine that screens composites; the c2 ceiling where registration allows;
the stream≠plane split the orientation row would need anyway.

### 9.1 Future exploration (recorded 2026-10-09, owner; not in this workstream)

- **cmy7-by-erasure as a row** — the reduced-alphabet erasure row of
  docs/REDUCED-ALPHABET-ERASURE-ROWS.md: cmy8's per-plane codewords with
  CMY lost by a known-position erasure (seven payload states, 2.75
  b/cell, no joint symbol), the dot-mixed route its customer (0.54 % on
  S17 U2, the table above). Its spelling is decided when it is picked up
  (R13, §2.0): (a) a cmy8-family row carrying the allowed-state set and
  the order domain (the erasure note's lead option, its §5), (b) a new
  sibling token, or (c) `cmy7-…-v2` (FORMAT-SPACE §5/§6's text permits
  it, the code does not). Owes the greedy emitter and the replaying
  demap.
- **The dot-mixed cmy8 route** (R20 DISCARDED 2026-10-10) — the cmy8 rows
  whole, their overlap cells drawn from single-toner dots (3.2 % S16 T2,
  3.65 % S17 U1; ~0.95 MB per page, the table above, single-print
  estimates). Open, settled when it is picked up: is the overlap-cell dot
  layout a ROUTE (§9's reading) or a printed-FORMAT change with a
  layout_version bump (M281-COLOUR §6 B's reading)?
- **Furniture changes for cmy8 and cmy7-by-erasure** — the
  family-independent furniture law (§2.5) applied at a `-v2` generation
  token per family: a single-toner word '1' (C against today's CM, one
  AltaLink measurement owed: CM is darker, C decodes cold on every
  engine), the keyed '0' rotation over {W, Y} (Y anchors on word sites,
  the plane cmy8 keeps losing), and the balance-law dust (at 20 sites
  over eight states it gives about three of each missing state, what the
  cycle gives today — the gain is the word rotation). The erasure row's
  furniture may use CMY where the engine lays it unscreened. The payload
  codecs are untouched by any of it.

- **Block-edge PAVA nodes as an analyzer arm (recorded 2026-10-12, owner: "maybe note down as a possible mechanism for the analyzer").** R31 PASSED the same night: measured held out (measure/cmy_calibration/RESULTS-2026-10-12-evaluator.md), nodes at each PAVA block's first and last training score, logit-joined, remove the separable sims' squeeze completely and lose 0.0006–0.0062 bit/cell against the shipped centroid-logit on every c2 paper band (and refuse e044 A's cold region), so they are no receiver default. Where they could pay: as one evaluator ARM in the analyzer's arms × rules ladder (analyzer DESIGN §13), tried per (tile-stream, lane) where the fitted map is separable (two blocks at the clamp), paid for in certificates like every arm; the cmy analyzer plan (A0–A8) is unbuilt, so this waits for it.

## 10. Rejected shapes (D17)

1. **The 3-plane erasure row for A = {W + singles}**
   (REDUCED-ALPHABET-ERASURE-ROWS §3–§4): ε = 5/12 erasures per plane,
   1.750 b/cell, every frozen rung out (R_eff r0547 0.914 … r0850 1.466);
   the label design carries ~+20 % fountain bits per site (inferred).
2. **Per-toner-plane streams with a one-hot constraint** (constrained
   bits, M281-COLOUR §6A); **a joint 4-ary stream** (cmy7-shaped, no rung
   axis; cmy7 DEAD); **cmy8 with forbidden states** (no erasure
   accounting).
3. **Compact 0..3 numbering** (§2.1); **plane-letter stream ids** (§2.2);
   **a new dither domain, a grown `COLOR_STREAM_AUX`** (§2.3).
4. **The zero-state choice on domain 2, on a re-purposed cmy7 domain (10
   or 11), on domains 14/15 or on an appended domain 16; a fixed
   Y-eligible subset; the exact per-tile split** (§2.5, §12 R10, RULED
   2026-10-10 — the keyed coin per site on domain 9 is the ruled law, no
   longer a rejected shape; deterministic all-M dust is the balance law's
   p120 value, RULED 2026-10-09, its periodicity conceded by the words,
   not rejected); **'0' over {W, M, Y} read in R alone** (§7b, a placement
   fork).
5. **Attempt-time calibration** (§2.7); **the K view as a cold reader**
   (§2.9b).
6. **K furniture** in the -v1 rows (R14 RULED 2026-10-10 "no K for now": a later furniture-law generation, with PRINTED-FORMAT §14 amended); **a rung above r0850**
   — not promised (R15 RULED 2026-10-10; RUNG-LADDER R1/R4); **fixed stream ownership of column groups**
   (CMY8-COLUMN-GROUPS §7).
7. **Per-tile-first calibration** (R11, 2026-10-10; §2.7): a tile's own
   120 furniture cells through a low-parameter map before any page fit —
   discussed and NOT taken: a receiver-doctrine change, not an R11 item;
   a lone tile's furniture cannot carry a nonparametric map (measured;
   `plane_k.py`'s docstring from the other direction). **A marginal-only
   chain** (only L_hi fitted, the conditional pieces raw): the raw pieces
   drive the uniform ±20 divisor on 11–48 % of page cells and shrink the
   fitted marginal with them (cold B3 n = 1: −0.104 vs −0.083 bit for the
   map alone). Lo-first is NOT rejected: it is R11's recorded
   alternative (§2.7).

## 11. Qualification plan (D19)

Simulation before toner; every gate a functional expectation with a
deterministic outcome; rates and residuals recorded, never a bar (R19).
Each is a TEST (patch-scale, wall stated in its plan) or a RECORD (dated,
run once by the owner): whole-page existence proofs are records (the
test-diet ruling, 2026-09-20).

| gate | what | pass | kind |
|---|---|---|---|
| G1 | a 10x10 round trip per ruled row, BICM — uniform rows through the core decoder, every row (uneven pairs included) through holo3's grouped decoder — over the receiver's OWN row (`identity.resolve_format_ref`) since W3, 2026-10-12; W2a ran it over a generator-built RowLike (R22) | byte-exact | TEST |
| G2–G4 | dead-Y / dead-M / dead-C at q ≤ 1/2 | Y: closes, lo empty; M: closes, hi empty; C: stays OPEN | ONE 10x10 TEST |
| G5 | the n = 2 metadata floor | rank of 24 consecutive same-parity indices = 24; trust at 24 / 48 tiles | TEST |
| G6 | emission goldens per ruled row, both routes | frozen | TEST |
| G7 | gs render of the `rgb` route → plane GT | 0 differing dots | TEST (`HOLO_RUN_GS_TESTS=1`) |
| G8 | holo3 sim e2e in the fixture cache: BICM, dead-Y/M/C | byte-exact closes as G1–G4 | TEST, 10x10 [as built 2026-10-12, receiver A9: `c2-cmy-r0775x0700@10x10` at 2400 dpi, q = 0.35 under the pair's 17/36, each toner `dropped` — dead Y VERIFIED on hi alone, dead M on lo alone, dead C OPEN, nothing certified, the run done; the lane fit erases lo / hi; `src/holo/receiver/tests/test_h3_e2e_cmy_c2.py` and its ledger] |
| G9 | analyzer: step 0's semantic null-proof at each step (§8); then a cmy sim with an ENGINEERED residue under the ported controls (`analyzer/controls.py`): a positive control (certificates withheld in both streams, EVERY one re-minted blind, equal to the truth), `parity_sample` per stream (its outcome fixed by the stimulus), `frame_null` with the SIBLING stream's in-tile contribution from another tile (mints 0 — the two-stage's null), `null_arm` with a nonzero power denominator, 0 wrong | semantic-identical; every withheld certificate re-minted, 0 wrong; on real sheets the controls are dated records (`analyzer/controls.py`'s 0.70 / 20 / 0.80 stay cmy8's; cmy sets none) | TEST (one slow-lane test; a clean sim leaves no residue and passes "0 wrong" vacuously) |
| G10 | RESTATED by R7 (2026-10-09): archived S14/S17 (and X10/X11): per-site word error, {C} vs {W, Y}, at the WORD-SITE threshold in R (R7's channel) against (R+G)/2 and equal luma, c2, the worst print (U12); the pose's word-site hit rate on R with the dark-fraction phase threshold (§7b); the survey's pitch-vote channel (equal luma until G10). No weights (F_C ≡ 0, §7f) | none — the owner's dated record, gates nothing (R19) | RECORD, owner-run, before scratch/ is retired [overtaken 2026-10-11: scratch/ is off limits; G10 runs on the e043c bands and the e044 scans in scratch2, receiver plan v0.2 A2] (captures in the owner's scratch, `measure/e041_scale_readout.py:83-86`; **scratch/ is being retired (owner, 2026-10-09) — the evidence scans are kept but not at those paths, so G10 is scheduled BEFORE the retirement or re-pathed to the archive**) |
| G11 | spec vectors written from THIS DOCUMENT, independent of both trees: (hi, lo) → presence id → (C, M, Y); (seed, counter, site) → word-site state; the domain-9 word keys (u = n_dust + site) | the label-table digest and an emitted 10x10 page's plane GT agree | TEST, before any golden freezes (else a wrong table round-trips as common mode through G1/G8 and the analyzer) |
| G12 | cold start (below) | byte-exact; true counters; the planted displacement recovered, the tiles certify; 0 wrong | TEST at three offsets; the grid a RECORD |
| G13 | the conditioned decoder (below) | per seed and order, the pinned outcome | TEST |

**G12 — cold start, the main feasibility risk.** A 2–6-tile fragment, no
certificates, independent M and Y offsets over 0.5–2.4 dots varying
across it (§7h), a zero-offset control. The sim's supervised
context-free c2 confusion is PRINTED beside S14 B3's and U12's committed
`confusion_loo` for the reader, the W→neighbour asymmetry included — a
record, not a verdict. Expected (R19): the FULL synthetic 10x10 page decodes byte-exact under Z, A and B (a 2–6-tile crop sits below metadata trust and cannot close); on the crops, up to one cell of offset: tiles placed
with the true counter; the planted plane displacement RECOVERED through
the field and the swim and the tiles certify, each equal to the truth;
zero wrong certificates, the CRC exposure (consults × 2^-32) reported
beside the 0. Past one cell the same is an EXPECTED RECOVERY, a refusal
there a FINDING to report, not a pass (R17). Registration recovery (on
~32 mm a translation or tilt, nothing finer) and the field errors are
recorded. The construction (a 2400-dpi render, e041's estimator, named
conditions) is CMY-RECEIVER-PLAN W10's. [As built 2026-10-12, receiver
A9 (CMY-RECEIVER-PLAN A9; tests `src/holo/receiver/tests/test_h3_e2e_cmy_c2.py`,
the grid and the confusion `measure/cmy_coldstart/RESULTS-2026-10-12.md`):
the full page VERIFIED byte-exact under Z, A and B; every 1×2, 2×2, 2×3
scrap placed at its true counters, every certificate the truth, CRC
exposure ≤ 2.1e-7 over the grid, no scrap closing; under Z, A and B every
scrap tile certifies, the field reading M within 0.08 of A's plant (at
B 0.06–0.18 short) and Y within 0.10 of the plant except where Y and M
differ — there Y's read leans ~35 % toward M's (A's control: Y −0.13 for
−0.5), M's ink in Y's B channel (measured, `measure/cmy_coldstart/lean.py`);
**under C nothing certifies on any shape — the expected recovery refused,
a FINDING (R17)**: M past the 2.24-dot reach, swim failing from a zero
hint. The sim's W row 5.88 % against paper's 13.9–14.9 %: the stimulus is
easier than paper. The drift's "same-blur control" moves all three planes
by M's drift, so the pose absorbs it and every plane is interpolated
alike.] An analyzer
control with zero non-skipped trials FAILS (the null donor sits 8 tiles
away, `analyzer/controls.py:60, 283-290`); the fragment's own null is the
same pixels under another identity; below K, export-facts' consistency
checks nothing.

**G13 — the conditioned decoder, both orders.** Per order a channel
scaled from a measured confusion (B3- and U12-shaped), its rung and
scale chosen BEFORE the run on disjoint seeds — on the unscaled
confusions the conditioning gain (0.037 bit on B3, 0.054 on U12 at
2400; reader arithmetic) is under one rung step (~0.08), so a fixed rung
rarely separates the two decodes (construction: CMY-RECEIVER-PLAN W8): the
BICM attempt fails, the
conditioned one certifies, equal to truth — per seed the outcome fixed by
the stimulus and pinned as a measured pin (`assert_measured`, moved only with the cause in the module's ledger — a receiver-axis quantity, not a format golden; R19). A negative arm (another tile's
certificate, bit-flipped sibling bits) mints 0, CRC consults and
syndrome-valid CRC failures counted. [As built 2026-10-12, receiver A6:
the channel is scaled from e043c sheet 3's B1 and B14 count matrices, not
B3/U12; the other-tile arm mints 0; the 10 %-flipped arm minted ONE true
certificate in 125 attempts (420 of 3,976 bits flipped still decode to
the truth, CRC-verified) and is PINNED, not asserted empty — the owner's
word owed on this line: "no wrong certificate; tally pinned", or a
complemented sibling as a second true negative.] Both paths (§7e's `tiles.cond` row
at the payload price, its engine test the row's born/arm set and the
generation re-arm; analyzer step 5), through export-facts, no conflict.

**Sequencing — THE edge list** (→ = must land before; the three plans'
§8 cite it and add no edge of their own). [Generator wave names, 2026-10-11
(CMY-GENERATOR-PLAN v0.4): this list's generator W3 and W5 are its W2a, W6 its
W3, W7 its W4; its W1–W2 are its W1, and W4 splits into W2a (the `rgb` route
and its gs gate, the print edge) and W2b (the registry rows and R21's
retirement).] Start at once: generator W0
and W5, receiver W0 (its §3 is the contract from day 0), analyzer A0.
Rulings R1/R2/R6/R12 (all RULED 2026-10-09/10) →
generator W1 → W2 (+ R3, R10) → W3 (+ R4 for printed-size goldens) → W4
(+ R9). Generator W0 + W1 + W2 + receiver W0 → receiver W1 (analyzer
A1-pre rides its commit). Generator W3 + receiver W1 → generator W6 →
W7. Generator W3 → receiver W2 → W3a → W4 → W5 (the first cmy close) →
W3b. Generator W5 → receiver W6, receiver W10, analyzer A7b. Receiver W5
→ W6, W7, W8; W3b + W6 + W7 + W8 → W9 → W10. Receiver W0 → A1 (cmy8
descriptor); receiver W1 + generator W2 → A1 (cmy rows, G11's analyzer
leg). A1 + receiver W0 → A2a; A2a + receiver W5 → A2b → A3 (its `field`
register arm after receiver W6) → A4. A3 + receiver W8 (the frozen G13
channel table) → A5. Generator W3 + receiver W5 + R8 → A6. A1–A3 + A6 +
receiver W5 → A7a (BICM); A7a + A4 + A5 + receiver W10 + generator
W5 → A7b → A8. **THE PRINT EDGE (RULED 2026-10-10, owner: "obviosuly
the sheet depends on the generator. everything else is candyfloss."):**
generator W4 + the owner's go → P1, nothing else. Receiver W5 and W10
and analyzer A7b run BESIDE the print, not ahead of it; simulation
before toner is met by the generator's own gates (G1, G6, G7), all before
W4 exits; the sheet's read is what the print is for, not its
precondition (proofs off the print path, 2026-10-06). **R22 (RULED
2026-10-11, owner: "We reach toner with uneven rungs, like cmy8 does."):**
P1's c2 row is R4's UNEVEN probe, and G1 for it is the grouped close —
holo3's `fountain.Decoder` solves column-group codes (the core decoder
refuses them by design, `src/holo/core/fountain.py:628-632`), and at
generator W3 it is driven from generator-built rows through
`holo.receiver.format.close.close_volume`'s duck-typed `RowLike` (seed,
tile matrix, stream ids and widths, `fountain_aux` None, pooled) and
`CertificateLike` (minted as `tests/holo/_receive_free.py` mints them, the
row built from the FormatSpec instead of the receiver's identity), so no
receiver source and no receiver wave joins the print edge — the way
cmy8's column groups were qualified (its receiver slow-lane e2e), now for
the row that prints.
**Paper** (the owner's go per sheet): P1 the M281 — `c3-cmy-r0850@35x24`
and R4's c2 row, BOTH routes, one day, the c2 sheet scanned at 2400 AND
4800 under the survey's declared-line guard (`src/holo/receiver/lib/pitch_line.py`,
69361a0f); P2 the AltaLink (X10/X11 read; a volume only with a customer);
P3 the another-day control. NO promotion from single sheets.
**Emission probe** (R9 as reduced by R23; §2.8): an owner-run RECORD —
the measurement for every NEW engine's solid points, beside its HCAL-R1
pair; on P1's day, BEFORE the volume sheets, the M281's fine sweep AND
the mask-vs-image bars (the colour-imagemask construct is unmeasured
there, R23); its spectral-midpoint analysis stays OWED (owner
2026-10-09). NOT a gate for cmy (the hp-m281 values are measured, e041).
G7 stays the route's software gate.

## 12. Rulings (R1–R20 and RA-1..RA-7 dispositioned 2026-10-09/10; R21–R23 RULED and R3 amended 2026-10-11; each row carries the recommendation of record and the ruling)

| # | ruling | recommendation |
|---|---|---|
| R1 | stream ids | **RULED 2026-10-09 (owner):** `hi`/`lo` as the machine-internal stream labels, order (hi, lo) = (0, 1); `label_index`, `dither_aux`, a raising `.plane` (§2.2). The labels never enter the format string: canonical `1i300-cmy-r{hi}x{lo}-p{p}-v1@TYxTX`, display `c2-cmy-r0775x0700@53x37` / `c2-cmy-r0700@53x37` (uniform contracted); `hi`/`lo` appear only in derived names (bank ids `cmy-{hi,lo}-{rung}-p{p}-v1`, `StreamFact.stream_id`, certificates, ledgers, diag) — cmy8's `C`/`M`/`Y` at the same level. |
| R2 | labelling | **RULED 2026-10-09 (owner):** the C-antipode, W=00 Y=01 M=10 C=11, on the death map (a dead C is fatal under any labelling that puts C at 11; C survives the M281's re-screen, Y is the plane that dies); digest-pinned and G11-checked. Generator W0(e), the `measure/cmy_labelling/` artefact over the COMMITTED `confusion_loo` extracts, is the CONFIRMATION GATE: if it contradicts the antipode ranking before W1's golden freezes, R2 re-opens by name. |
| R3 | dust and R3 whiteness | **RULED 2026-10-09 (owner):** the BALANCE LAW — the n_dust = p − 100 dust sites given one at a time to the state with the lowest running total, from the row's expected word supply (C 50, W 25, Y 25, M 0 per tile), ties M, Y, W, C, no majority cap; domain 9 permutes the multiset per tile (`pilots.dust_state_values`, the same door). p120 twenty M; p150 M 34 Y 8 W 8; p200 M 50 Y 25 W 25 (four-way balance from p200); p300 M 75 Y 50 W 50 C 25. The periodicity argument is withdrawn: a tile-period line's amplitude is the mean per-position occupancy (all-M 1.0, (M, M, M, Y) 0.75, (M, W) 0.5), and the words already lay a 100-site lattice at 0.5 in C on every colour row (DESIGN.md §5.2's concession) — not a new concession, no R3 amendment. Generator W0(c) struck (the arithmetic, pinned with the multiset at W1); the cmy7 head dropped as a cmy consumer (§2.7, §7c); the furniture law family-independent (§2.5). **AMENDED 2026-10-11 (owner: "c w y m counts differ per tile, i take it. for each tile, we _know_ a priori what the numbers will be ... compute and cache, instead of constants?"):** the running totals start from the TILE's actual word supply (n_C, n_W, n_Y from the seed, the counter and the preselection), not from expected constants — the multiset a pure function of (seed, counter, p), computed where the word states are rendered; §2.5. |
| R4 | first rows | **RULED 2026-10-09 (owner): which sheet prints first is a print-day choice, not a format decision.** The first c2 PROBE is `c2-cmy-r0775x0700@53x37` (hi at r0775, lo at r0700; Z 19, 19:17, reserve 21, ≈ 5,773 fountain bits/site, ≈ 1.27 MB per A4-4mm page, estimate), then up or down by the measured I(hi)/I(lo) of the day's print — on the record r0775 wants I(hi) ≥ 0.85–0.89 and r0700 I(lo) ≥ 0.76–0.80: B3 and X10 clear both, R9/T12 sit in the gap band on hi, U12 fails both (the "go down" signal, r0700 or r0700x0625). c3 at r0850 whenever a c3 sheet is printed. The printed-size goldens follow the probe; the 10x10 goldens cover r0850, r0700, r0700x0625, r0775x0700, r0850x0700 and r0700-p300 regardless. Nothing is promoted. |
| R5 | the two-stage demap | **RULED 2026-10-09 (owner):** a PRICED STAGE of the tile row in the family of `tiles.scan` / `tiles.retry` — not a flag or dial, not a residue stage at the top of the ladder, not in-job conditioning behind a switch. Row `tiles.cond`, subject (page, ty, tx, stream); BORN by the stream's own failed `AttemptFact` AND the sibling's `Certificate` in the window; READS `attempt` and the sibling's `tile` key (the certificate fold already emits it, `store_folds.py:973-975` — direct, no wait for the region refit); PRICE ordinary payload work, PAYLOAD_COST 20 + RUNG_COST 2 × rung ordinal (`tiles_sched.py:41-42`), not the 210–220 residue band; WORK the stream's attempt with §2.7's conditioned demap on the sibling's bits from the window's allowed-state set (I-4), its own CRC verifying, conflicting certificates raising as today; RE-ARM by the tile-lane generation, at most once per generation; PRODUCES `AttemptFact \| Certificate` — whichever stream certifies first births the other's cond, both orders from one row. G13 the gate (both orders, negative arms), the engine test the row's born/arm set; A4b's stratified shape for the derived direction only if it pays (§7e, which also corrects v0.2's cmy8 re-arm claim). |
| R6 | dither keying | **RULED 2026-10-09 (owner):** domain 13 (`DOMAIN_CMY8_DITHER`), aux = stream index + 1 (hi → 1, lo → 2), passed as an INTEGER through `StreamFact.dither_aux` (I-2), never a name; no new domain, no new aux value. Verified: the core range-checks the dither aux to 1..3 and accepts an int (`src/holo/core/keystream.py:316-332`), the receiver copy accepts an int (`src/holo/receiver/format/keystream.py:210-213`), domain 13 at aux 1 and 2 is drift-pinned in both trees (`test_h3_drift_format.py:51-53`), one helper `stream_ids.index(id) + 1` reproduces cmy8's (1, 2, 3) exactly (`src/holo/format/profiles.py:312-318`), and cmy hi shares (13, 1) with cmy8 C but never bits (the seed spells the family). The pooled fountain is NOT R6's: a -v1 row runs on domains 7/8 at aux 0 with u = local·n + stream, `fountain_aux = None`. |
| R7 | addressing channel and gauge | **RULED 2026-10-09 (owner), against v0.2's recommendation ((R+G)/2; w_C F_C + w_M F_M = 0, weights from G10):** C ISOLATION — the R channel, a per-family constant (cmy (1, 0, 0); K/cmy7/cmy8 keep the exact equal-channel call, `lib/decimate.py:283-291`, `place_pass._crop_luma` `:82-92`) — for BOTH the addressing pose (the one committed placement per capture: the place pass and the platen backing, `intake.py:66-75`) and the word bits; not (R+G)/2, not equal luma. On the S14 bars C darkens R by 0.80 of white, M 0.07, Y 0.01; the word margin C vs Y is 0.79 of white in R, 0.54 in (R+G)/2, 0.21 in equal luma. The pose is C's exactly, so `fields`, the region head's registration arm, `refine.color`, `tiles.planek`, `tiles.swim` and the analyzer's A3 poses all measure from C. GAUGE F_C ≡ 0, M and Y free — no weights, no G10 weight measurement; the C `PlaneField` published as the zero field (AI3: committed by name). One mechanism change, receiver W2: `_fit_phase` thresholds at the row's known dark fraction (or between the two modes) for cmy, not the window median (`pose.py:466`), the lattice fit unchanged; the word bits at the word-site population. The survey keeps equal luma until G10, restated (§11); the dust dark table (cmy {C, M}) is not R7's. Inferred: the M281 bar arithmetic; the AltaLink's C/R contrast is not in the committed extract. Corrected on the way: under a mixed channel the pose is a blend, not C's; an equal-weight gauge misplaces C by (w_C − 0.5)(C − M) for a pose at w_C : w_M, not by half the C–M registration; a channel change does not make resume refuse — the snapshot has no version stamp or guard (`snapshot.py:20-22`), old poses would fold in silently; `words.py` has no per-family channel or dark table today (both PLANNED, I-9). §7b, §7f. |
| R8 | sequencing against the dedupe | **RULED 2026-10-09 (owner):** no sequencing gate in either direction — cmy is BUILT TO FIT THE PROJECT NATURALLY, and whatever that takes (generalising a dispatch, reshaping a type, abstracting a receiver copy into a shared module) is in scope of the build. The "narrowed vs none" framing is withdrawn: the four receiver copies cmy edits (identity, keystream, pilots, tile_codec) are 1,466 of the five copies' 1,611 lines, so "narrowed" was 91 % of the dedupe, and identity cannot be folded at all (it holds the receiver-only `StreamFact`/`FormatRow` and the sheet-J holo/v2 fossil, and its generator partners lattice/descriptor/resolve are outside analyzer A6's BLIND allowlist). Wherever copies persist they stay drift-pinned (the three slow-lane drift modules, the per-tree goldens, G11's document-written vectors, W1's encode-equality exit); the receiver import firewall and A6's allowlist follow the shape the build arrives at. The p-axis is no precedent either way: it touched neither copy of pilots. |
| R9 | emission | **RULED 2026-10-09 (owner):** §2.8 as written, WITH a per-engine calibrated emission footing. (a) An append-only `EMISSION_ROUTES` in a new `gen/routes.py`, a v2-only `--route`; `cmyk1` = today's 1-bit DeviceCMYK composite (`put_cmyk_bitmap`, `emit.py:318`), the default, byte-identical for every existing row; the indexed-RGB palette route (`rgb-palette`, spelling W4's) = e041's S15–S17 production construct (`ps_mixture.py:81-83, 156-204`): 8-bit `[/Indexed /DeviceRGB 3]`, the four guarded HP calls in order, the bare-name prologue, the PJL wrapper; Smooth c3 / Detail c2 / other pitches refused; one image per band of FOUR tile rows and the PJL job name from the jobid (both FIXED); the PS differing from e041's jobs only in title, creator and job name (the W4 byte audit); the GT stays the C/M/Y dot planes, `gt_sha` route-independent; an `emission_route` manifest block replaces the hard-coded DeviceCMYK renderer (`manifest.py:162-168`); the route never enters the identity (FORMAT-SPACE §2.1, §3; PRINTED-FORMAT §12.4). (b) The solid points are the route's PARAMETERS, not its name: the devices registry gains an emission footing per engine entry (route, points, halftone selection, prologue, evidence grade), keyed per ENGINE MODEL and PDL route, not brand — `hp-m281` `measured` (e041: C (0,208,255), M (240,0,192), Y (255,255,0), W (255,255,255); Smooth c3 / Detail c2); the AltaLink (X10/X11 unscreened, e042 §042.4) and the Canon iR-ADV (e040's unscreened colour cells, NO cmy page there) `cmyk1` `by-construction`, each pending a confirming page; no VersaLink/M681 entry. (c) A cmy EMISSION PROBE for any new engine, owner-run beside the HCAL-R1 sheet: solid-bar value ladders per toner, the S10p2 lattice score (≤ 18 unscreened), the plateau mapped at fine steps, the point at its centre, least foreign toner; its record in the engine's log and entry; its spectral-midpoint analysis OWED (owner, 2026-10-09). (d) The points are measured PLATEAUS (16-level sweeps): known-solid, not known-optimal, the 1-level edges unmapped (C's G 208 and M's R 240 at their plateaus' measured ends). (e) PCL XL NOT abandoned for complexity: C/Y solid at their corners, M only displaced; the per-object job crashed the formatter (novelty budget); S11 vs S12 cmy4 c3 1.4 vs 0.36 %, drift not separated; a lawful candidate per engine, an entry only when measured. (f) Unmeasured: a pure cmy page through `cmyk1` on the M281 (predicted screened; one page on P1's day, not needed), cmy on the Canon. §2.8, §11. **CONSTRUCT SUPERSEDED 2026-10-11 (R23):** the palette image, PJL wrapper, HP calls, prologue, band rule, route registry and footing revisions are replaced by K's imagemask construct in colour and two `Printer` fields; the selector is `--printer` (R21); the Indexed construct is the measured fallback; §2.8. |
| R10 | word rendering | **RULED 2026-10-10 (owner):** '1' = C always; '0' = the site's KEYSTREAM-PRESELECTED state from {W, Y} — ONE draw per (tile, site), a pure function of (seed, tile counter, site index): address bit 0 prints the preselected state, 1 prints cyan. The draw is on DOMAIN 9 (`DOMAIN_COLOR_DUST_ORDER`, aux 0, major = tile counter, v = 0, one 64-bit big-endian key from block bytes 0..7, `src/holo/core/keystream_spec.py:25, 39-40`), drawn by colour rows only at u = 0..n_dust − 1 until now (`keystream.color_dust_permutation`, `src/holo/core/keystream.py:283-287`; `pilots.dust_state_values`, `src/holo/format/pilots.py:206-245`): a cmy row's word sites take u = n_dust + site (0..99), Y iff the key's TOP BIT (the MSB of block byte 0) is set, W otherwise; the dust draw byte-identical for cmy8 and cmy; the domain's meaning extends to "the keystream that orders colour furniture states per tile"; the table keeps fifteen rows, one meaning each, and FORMAT-SPACE §19 (WITH THE BUILD) records the u-range extension in one sentence. Word '0' and dust are ONE idea: a keystream-preselected state per furniture site, the word bit choosing between it and C (dust = the no-bit case). WITHDRAWN everywhere: v0.2's EXACT per-tile split (sort the tile's '0' sites by key, the first ⌊n0/2⌋ Y) and domain 16 — no new domain, no new aux, no amendment to the table's shape. The per-site form needs no sort and a site's state does not depend on the other 99 sites' bits; the per-tile Y count becomes binomial (mean ≈ 25, sd ≈ 3.5; fewer than 20 of either W or Y in ≈ 12 % of tiles), harmless under the floors that stand: the marginal calibration floors 6/2/3 (`color_model.py:22-24`; ≈ 7 Y in one tile's held-out half at 15 Y), the page field's anchor floor `ANCHOR_MIN_SITES` 24 / 4 minority per (tile, plane) template (`field_tiers.py:100-101, 255-277`; a 15-Y tile clears 4 almost four times over), the analyzer's label supply in expectation; under R7 W and Y both read '0' in R (0.99 of white). Decode on the hi bit ({C, M} → 1, {W, Y} → 0), then BCH with erasures (unchanged); M reads on word sites not refused (0.71–1.19 expected per word); the receiver learns the preselection only after addressing (it needs the counter) — cold, the word read needs only that Y reads '0'. No word-law fields: `word_states` stays the pair (W, C), the keyed W/Y rule is the family's inside the furniture functions, which take the codec or row, and the manifest records it as text (`word_zero_rule`: domain 9, u = n_dust + site, MSB → Y) — *corrected 2026-10-11 (generator W0): this row said "the word-law fields stay (`word_one_state`, `word_zero_states`, `word_zero_rule` on profile, row, manifest; I-3)", which §2.5 as simplified the same day contradicts; receiver I-3 re-opened and amended to match.* n0 ≈ 50 because the 100 word sites carry near-uniform scrambled bits (the 50 of BCH(127,50) is the dimension, a coincidence); n0 varies with the counter, its range recorded at generator W2. Rejected: domain 10 or 11 re-purposed (collision-free, but a row with two meanings by family); domain 2 (per plane, major 0, no per-tile form); domains 14/15 (the wrong shape: per stream, per block/page); a fixed per-site subset, no keystream (the same Y pattern in every tile). The expected hi-channel word errors fall on all five c2 prints (B3 2.35 → 1.60, R9 3.33 → 2.06, T12 3.21 → 2.09, U12 4.32 → 3.28 on the M281, e041; X10 2.56 → 1.85 on the AltaLink, e042) because a Y cell flips hi less often than a W cell (B3 0.76 vs 3.75 %), NOT because a W→Y flip stops being an error (under hi-bit decoding it never was one) — reader arithmetic on the committed `confusion_loo`, supervised poses (§2.5, §14.3). **Code shape (2026-10-11):** the rule is `Family.CMY`'s branch inside `color_word_states(row_seed, counters, codec)` — no law object, no new profile field (§2.5). |
| R11 | calibration | **RULED 2026-10-10 (owner: "we follow cmy8"):** LOCUS AND CASCADE = cmy8's — evidence time, one head per colour lane (capture, level, page) (QDA, chain maps, registration arm, feature divisor, context matrix) fitted once and applied to every window on the page, the three stored W-relative scores summed across captures with no post-sum clamp (`tiles.py`); the per-tile levels are the EXISTING residue rows (`tiles.local` reruns the head over one failed tile's windows; `tiles.swim` reads the neighbours' certified cells; planek stays cmy8-only, §7g, the cmy K view in its shape is §2.9b) — no per-tile standing fit, no new region type. CHAIN hi-first — L_hi, L_{lo\|hi=0} (W vs Y, on sY), L_{lo\|hi=1} (M vs C, on sC − sM), folded by §2.7's hi-first formulas, exact under equal priors; lo-first RECORDED as the alternative (tie in the designed rung pairing; hi-first wins with both streams at r0850; the dead-Y erasure needs L_hi, no fourth map; v0.2's lo-first reason withdrawn — the derived hi\|lo forms equal the fitted within 0.003 bit under the logit evaluator (0.0005 with certified cells)). POPULATION: held-out (&1 == 1) furniture with WORD SITES ADMITTED, state-balanced in the NEW cmy-only weighted PAVA entry (1/4 of a map's mass per state), plus certified cells read from the store at fire time (+0.006 to +0.013 bit on the lo marginal (within ±0.003 of zero on the hi marginal, no interval below zero) over cmy8's class-balanced fit cold, never loses; bit-identical to `fit_component_pava` under class-balanced weights). EVALUATOR: the PAVA nodes interpolated in LOGIT space, flat beyond the end nodes, inside the cmy entry point; `PavaMap` (`color_model.py:253-257`) unchanged — its probability-linear interpolation costs 0.02–0.12 bit on near-separable pairs and 0.065–0.12 bit on lossless c3 bands (logit: ≤ 0.0032); the same defect in cmy8's marginals an OWED receiver line (null / A-B on archived cmy8 states first), not R11's. FALLBACK per map: the region QDA's uncalibrated statistic under the uniform L∞ bound 20 (`color_region_head.py:31`; binds on 52 % of B3's payload cells raw, 0.0–0.1 % fitted); an unsupported or collapsed STREAM exactly 0.0 in its marginal and both conditionals by the erasure law (dead lo: sY := 0, sC = sM := L_hi; dead hi: sM := 0, sC = sY := L_lo, the raw bounded lo statistic, no map); the collapse detector misses 6–9 % of dead-Y regions at one tile, ≥ 0.98 from two — W3a's erasure must not wait on it alone (owed). FLOORS cmy8's: marginal 6 / 2 / 3 (`color_model.py:22-24`), conditionals A4b's 40 fit labels / 6 per class + a DISJOINT 20-cell validation set (`color_conditioning.py:99-101, 386-409`); measured, the marginal maps break even at ~2 tiles' furniture on U12, ~8 on B3/X10, the conditional maps do not pay below 8 — the gate, not the floors, protects yield cold. GATE cmy8's three-way region adoption gate as it stands (`color_region_head.py:292-306`), every leg published; cmy's dust leg single-class at p120 (all M), ~0.2 of the three-way gate's refusals; the leg structure re-examined after the sim's refusal rates (G13), under the measured constraint that adopting maps on cold regions (≤ 8 tiles) LOSES and a gate refusing cold, adopting at page scale ties the fallback cold and gains on pages. FREEZES receiver mechanism only, no format law: receiver plan I-6 at receiver W0, re-openable by name; NOT a snapshot contract. UNBLOCKS receiver W0 (with R1, R2, R6, R10), then W3a → W5 → W3b. Not taken: per-tile-first calibration (a receiver-doctrine change, §10). The analyzer's ruling-11 drop of the same single-class word rows is cmy8's own behaviour carried over (RA-7, folded into R11 2026-10-10; §8 step 1). §2.7, §7c. |
| R12 | sites | **RULED 2026-10-10 (owner: "r12 like cmy8.", after asking "does cmy8 take p100?" — it refuses it at the constructor in both trees):** cmy's frozen input default is p120, added to the per-family defaults table beside K 100, CMY7 120, CMY8 120 (`lattice.py:65`; receiver `identity.py:118-119`); p is always spelled in the canonical id, so the seed is immune to the defaults table (FORMAT-SPACE §6 law 4). Lawful p = cmy8's rule exactly: p > 100 and p ≤ min_stream(k_bits) − 34 (FORMAT-SPACE §11.4/§18), no cmy-specific band; the cmy constructor refuses p == 100 as cmy8's does (`families.py:129-136`, "cmy8 needs at least one dust site (p > 100)"; receiver `identity.py:425-427`), with cmy's own reason beside it: under the word law M appears only in dust (word '1' = C, word '0' ∈ {W, Y}), so p100 leaves the M plane with no anchor at all. Why p120: the only furniture density any colour sheet has been printed at (every colour fossil is p120, `format/fossils.py:102-121`; no p-axis row ever printed); a p120 cmy row shares site positions and the E022/E023 placement lineage with those sheets (site seed `holo/v1/sites/p{p}`, receiver `identity.py:26-30`), not their values or contrast. A different p is a new lineage (word-site overlap with p120: 7/100 at p101, 5/100 at p300), so no placement or addressing number transfers; the dust multiset at any p is R3's balance law PER TILE (p120: 20 M in most tiles, split where a word-zero state is short — counters 28/30 of the 10x10 row give M 18 W 2 / M 18 Y 2; p300 counter 0: M 75 Y 50 W 55 C 20; §2.5 — corrected 2026-10-11 at generator W0, this row had an expected-supply multiset). Rejected: p100 (no M anchor); a higher default such as p150/p200/p300 (for cmy8 p120→p300 costs 56.25 % of one rung step in bytes, c2-cmy8@53x37 A4-4mm q = 0.5, 65,813 of 117,000 B, FORMAT-SPACE §18; cmy's per-stream ratio is the same arithmetic, inferred not measured; and it starts an unprinted lineage) — a row that wants a higher p names its own. OWED before any cmy row above p120 prints: the receiver's support-floor envelope `BER_ENVELOPE` 0.08 (`receiver/plugins/place.py:44`) was derived for cmy8's dust law — for cmy8 falsified above p ≈ 132 under a dead Y, toward false accept (P-AXIS-DESIGN §4, e(p) = (1/3)·n_dust/p); the crossover for cmy's dust law is NOT derived (cmy's dust is all M at p120 and its dead-Y word '0' stays '0') (§13). LOCKS format law per row (p in the id) and the frozen family default. UNBLOCKS generator W1 (with R1, R2, R6) — the CMY p120 default and the `cmy_codec` p == 100 refusal — and the 10x10 goldens including `c2-cmy-r0700-p300@10x10`, the lawful-p path (§6(k), R4). §2.5, §6(b). |
| R13 | the token | **CLOSED 2026-10-10 (owner: "r13. aha." — nothing to decide):** the family token is `cmy`, RULED 2026-10-06 ("we'll call the encoding cmy from now on"), in every canonical id (`1i300-cmy-r0775x0700-p120-v1@53x37`, §2.4) and the seed (`holo/v2/` + canonical, FORMAT-SPACE §6 law 1) — format law, no display alias; cmyw / cmy4 / cmy4-solid(C) retired. Caveat kept: `cmy` breaks the cmy7/cmy8 state-count suffix. The seven-state erasure row's spelling is NOT owed now (future exploration, §9.1); when it is picked up the options are (a) a cmy8-family row carrying the allowed-state set and the order domain (the erasure note's lead option, REDUCED-ALPHABET-ERASURE-ROWS §5), (b) a new sibling token, (c) `cmy7-…-v2` — FORMAT-SPACE's text permits it (§5, §6), the code does not: only v1 is defined (`lattice.py:67`; receiver `identity.py:121`), both parsers refuse a cmy7 rung token in every generation (`lattice.py:192-195`; receiver `identity.py:123-124, :398-401`), and §5 describes a cmy7 generation as a re-baked pack7 bank, which the erasure row is not. `cmyw` as an alias: rejected. CORRECTION (§2.0): the fossil catalogue is NOT what blocks reuse of the cmy7 token — the pack7 fossils are v1-namespace seeds (`holo/v1/c2-cmy7-p120-v0/…`, `holo/v1/c3-cmy7-p120-v0/…`), byte-matched and never parsed (`format/fossils.py:7-9, :87, :102-106`); a `holo/v2/` seed cannot collide with them; what blocks `cmy7-v2` is the grammar and the parsers. Unblocks nothing now; it is the precondition of I-1 `Family.CMY = "cmy"` (generator W1 step 3; receiver W1; analyzer A1); neither tree has a CMY enum member yet. §2.0, §9.1. |
| R14 | K furniture | **RULED 2026-10-10 (owner: "r14 no K for now"):** no K furniture (no word or dust site in K) in the cmy -v1 rows — recorded as a furniture-law option for a later generation (a `-v2` furniture law, §2.5's per-row furniture axis), NOT as a ban. K fiducials are not R14's question (DESIGN.md R3 excludes fiducials from every archive sheet). Why: the alphabet has no K state ({W, C, M, Y}, §1.1); the cmyk1 emitter writes K = 0 for every colour family (`src/holo/gen/ps.py:54-75, :188-193`; PRINTED-FORMAT §12) and the M281 palette route's lookup is 0:W 1:C 2:M 3:Y and refuses any other state (§2.8) — K furniture would need a new state, a palette entry or an imagemask, and receiver evidence for it; no record shows a decode that failed for lack of it; all three plans leave it out of scope; furniture is a per-row axis independent of the family (owner, 2026-10-09), so K can join later as a new generation without reopening cmy. NOT a reason: "K would screen the M281 page" — measured, one print: M281 sheet S16 band T6, 0.5 % image K in a cmyw image under TonerBlack, did not screen and read 0.17 % (e041 §041.5m; its reading 7: K under 1 % "is available"); only 10 % and 20 % K screened (T7–T9). Unmeasured: a sparse K IMAGEMASK (T9 was a 20 % mask), the K density of a K word layer against T6's 0.5 %, and K on a colour page on the AltaLink or the Canon. LOCKS what a cmy -v1 row prints — no K anywhere; reversible at no cost until the first print, after which K is a new generation. Unblocks nothing (the plans' out-of-scope lines stand). §2.8. |
| R15 | rung ceiling | **RULED 2026-10-10 (owner: "r15. bugger off. we have rungs, we use them. we get more rungs, we'll figure it out."):** cmy promises NO rung above r0850. cmy rows use the six frozen rungs (`src/holo/core/ldpc/construct.py:69-76`, the `LdpcSpec` of `:36-37`), r0850 (k 3520) on top. Scope, not a format ceiling: FORMAT-SPACE keeps the ladder appendable (`docs/FORMAT-SPACE.md:93`, "ladder appendable"; `:280-281`, "new rungs join by data + ladder entry, no grammar change"); if a rung is ever minted it is a new frozen mother code appended by data plus a `LADDER` entry, irreversible (RUNG-LADDER-STUDY R5), with the study's R1 naming and R4 construction lever still OWED and a sim gate (§2.4) — nothing of that is cmy's. Recorded beside it, READER ARITHMETIC, NOT A CLAIM: on the committed hard-decision confusions of all ten c3 bands (S14 A1/B1/B2, S15 R8, S16 T3/T11/T14, S17 U13 at 4800 and 2400, AltaLink X11; `confusion_loo` in the e041/e042 `measurements.json`), the per-stream hard-bit I(bit) runs 0.9703 (lo, S15 R8) to 0.9986 (hi, S16 T3), per-bit hard error ≤ 0.32 %; at r0850's 0.075-bit harness gap (RUNG-LADDER-STUDY:83, :817) the channel would support k/4096 ≈ 0.90–0.92, k ≈ 3686–3768, a few percent more user bits per stream; nothing above k 3520 was ever built or searched (the overnight search covered the frozen k and k 1216–1664 below the ladder, §7.4); r0850 shows CRC-caught syndrome-valid wrong decodes (5 in 30,000 trials, codec sim, RUNG-LADDER-STUDY:565, :580-583). A ~0.95 rung would need I(bit) > 1.0: stays a wish (§2.4). §10's item "a rung above r0850" reads "not promised (R15)". LOCKS nothing; UNBLOCKS nothing (all three plans already list it out of scope: CMY-GENERATOR-PLAN §5, CMY-RECEIVER-PLAN §5, CMY-ANALYZER-PLAN §5); every golden and stimulus uses r0850 or below. §2.4, §10. |
| R16 | design-only vs normative | **RULED 2026-10-10 (owner: "r16 follow your recommendation"):** this document stays the DESIGN OF RECORD until the build. The normative amendments — FORMAT-SPACE §19, HOLO-DESIGN v0.27 §13.38 (+ F4/F6/F8/F14/F15, §4.2/§5.3/§6.2), PRINTED-FORMAT §12.5 (+ its §4 aux/domain lines, §5 esi line), the LAYERS row, SCHEDULE.md, the devices text, the analyzer family section — land WITH THE BUILD, with the goldens and pinned numbers they describe: the format-law set (FORMAT-SPACE §19, HOLO-DESIGN §13.38 and its F items, PRINTED-FORMAT §12.5, the LAYERS row) in generator W7 (CMY-GENERATOR-PLAN W7: "design §13 ticked", Exit "§4's acceptance list checked"); the devices text in generator W4, SCHEDULE.md in receiver W9, the analyzer family section in analyzer A8, each with its wave. Precedent: CMY8-POOLED-FOUNTAIN's HOLO-DESIGN ledger entry landed with the implementation commits (2026-08-13, its status lines `:3-8`); the column-group pool "RULED + BUILT 2026-09-04" (FORMAT-SPACE §17, `:778`); the p-axis's §18 / §13.37 / PRINTED-FORMAT §6 + §12.1 "LANDED with the patch" (P-AXIS-DESIGN §7, `:294-312`). Reason: W7's checker requires every number in §19/§12.5 to equal a pinned test value; no cmy code, golden or spec-vector file exists yet (only cmy8's state enum, `src/holo/core/channel.py:43`). The design text is testable before code through G11's spec vectors written from it in generator W0. TWO documents move EARLIER, stated explicitly: FORMAT-SPACE-DISPATCH, re-derived before code in generator W0; API.md, frozen with the interfaces I-1..I-11 in receiver W0. Already on record and left in place: HOLO-DESIGN §12 "Deferred" carries the 2026-10-09 future-exploration pointer to §9.1 (`docs/HOLO-DESIGN.md:886-890`) — a deferral, not format law. Today's F14 covers only the six existing colour rows, provisional and catalog-only until paper/null qualification; every cmy row is the same. Rejected: amend now — the text would precede the W1 goldens it describes, need re-editing after each review wave, and break W7's number-equals-pin check. LOCKS process only (when the docs land), no format law, no code. UNBLOCKS nothing directly; W7 is gated by W6 green; R16 ratifies the timing W7 already plans. §13. |
| R17 | c2 reach | **DISCARDED 2026-10-10 (owner: "r17 discard. plane fields and planek/swim correction are additive, i thought, so together should reach well beyond 2.5 dots? also page field with incremental stretch in the y axis should also carry us beyond?"):** no reach promise and no re-derivation of field radii or the swim bound (the swim needs only receiver W9's alphabet floor); G12's condition C is an expected RECOVERY, a refusal a finding; no 2.24 band (G12 restated by R19). (2.24 dots = `measurement_reach_dots`, what one tier SEES, not a bound on the field's publication, `field_tiers.py:165-180`; the probe centred on the window pose through `lib/page_map`, `fields_collect.py:181-199, 399-414`; the swim a per-plane affine within one cell of the standing field's value, additive on the field, `swim.py:1-30, 138-150, 243-253, 357`, 4.5 dots: field 200/300, with swim 297/300, MEASUREMENTS-2026-09-03; refine.color re-poses windows from certified tiles; planek cmy8-only, `plane_k.py:721, 762, 804`, its cmy shape §2.9b. The threshold is a plane's offset from the WINDOW POSE, not \|Y−C\|.) Locks nothing; unblocks receiver W10's G12 as restated. §7f |
| R18 | the analyzer null-proof lane | **DISCARDED 2026-10-10 (owner: "r18 discard" — "this has nothing to do with generating or receiving cmy sheets?!"):** not a cmy ruling. The worker-lane question (absent real-pixel fixtures FAIL under a flag on the owner host; a fixture-free cmy8 sim pass for worker waves; the sheet-I residue fixed point an owner-host slow-lane test; full H/I/J passes owner-hours at steps 2, 3, 5) is the analyzer plan's own A0 hygiene; RA-6 stayed the analyzer's question (discarded 2026-10-10, R20's row). |
| R19 | registered numbers | **RULED 2026-10-10 (owner: "i don't give a hoot. this is not a kind of testing i condone. for me testing is about assuring expected functional behaviour, not about some number to be hit. happy for end-to-end tests and expected results, very worried abou tests that are percentages of something that can be gamed in all manner of ways. unhealthy tests, no?" — and, on agreement, "if you agree, then it should have been a card in the first place?"):** "gates pre-registered" WITHDRAWN; no numbers registered. Every cmy gate (§11 G1–G13; the plans' wave exits and acceptance tables) is a FUNCTIONAL EXPECTATION on a constructed, seeded stimulus with a deterministic outcome — byte-exact recovery, placement equal to the true counters, zero wrong certificates, an expected refusal or an expected recovery; none is a percentage, a rate, a residual bound or a count-of-N bar. Rates, residuals, confusion matrices and field errors are RECORDED beside the test; as a regression guard a MEASURED PIN (`assert_measured`, moved only with the cause in the module's dated ledger), never a gate. Paper readouts (G10) are the owner's dated records and gate nothing. G9: on the synthetic page every withheld certificate re-minted blind, equal to the truth, 0 wrong, the parity control's outcome fixed by the stimulus; on real sheets the controls are dated records (`analyzer/controls.py`'s 0.70 / 20 / 0.80 stay cmy8's; cmy sets none). G10: the ≤ 4 % bar gone. G11 unchanged (digest equality is functional). G12: byte-exact in Z/A/B, true counters, the planted displacement recovered through the field and the swim and the tiles certify (R17), 0 wrong; the sim's confusion PRINTED beside B3's and U12's — no τ, no "sim unfaithful" verdict, no 0.25 / 0.5-dot bar; field errors recorded. G13: per seed the outcome fixed — the tiles that need the sibling certify conditioned, both orders, the negative arms certify nothing — and pinned as a golden; the 3/32 / 29/32 counts gone. Receiver W3a (byte-exact on the raw fallback; state error and LLR-sign agreement recorded; \|s\| ≤ 20 the bound's definition), W6 (the planted displacement recovered, the tiles certify; the 0.12-dot difference recorded), W10, and analyzer A7a/A7b the same way; the dead plane an expected BEHAVIOUR (the dead stream erased, the page closing under the stream tier), its `plane_snr` floor a recorded mechanism constant. Why: the test-diet doctrine (2026-09-20; CLAUDE.md's Suite paragraph, SUITE-AUDIT §D.3) already made measured quantities records that move only with a dated cause and whole-page proofs dated records; the R19 card verified every cite and never asked whether a percentage bar is the right KIND of gate. LOCKS the gates' kind, no format law, no code; UNBLOCKS analyzer A7a (no numbers to wait on). §11, §12 R17. |
| R20 | build order against yield | **DISCARDED 2026-10-10 (owner, on the print edge: "obviosuly the sheet depends on the generator. everything else is candyfloss."):** cmy is the line being built, on §11's edge list; the card's "both-routes M281 sheet first, then pick" assumed cmy already built (that sheet IS P1), and its pick list offered the erasure row parked on 2026-10-09 as future exploration (§9.1, R13). The dot-mixed cmy8 route joins §9.1 beside cmy7-by-erasure, its route-or-format question open there; the yield table stays as single-print estimates (§3.3, §9). The print edge: generator W4 + the owner's go → P1 (§11). The analyzer's RA-1..RA-7 dispositioned the same day (analyzer plan §8): RA-1, RA-3, RA-4, RA-7 folded into R11 and cmy8's own analyzer rulings, RA-2, RA-5 the builder's calls, RA-6 discarded (standing lane doctrine). |
| R21 | `--printer` and the legacy generation door | **RULED 2026-10-11 (owner: "We have L: legacy format strings that imply print formats. No other legacy print will ever be done, if any at all. That means you can hardcode the L: rows with the info you need, and completely trash the current use of --printer. Repurpose it A-Z for our new use."):** the legacy printer-derived generation door RETIRES — `make_spec`, `get_printer`, the `--coding`/`--profile` selectors of `generate`/`capacity`, `registry -v`'s derived geometry, `hp-m281-ink`; the 14 `L:` fossils already carry their placement (A4 + margin) and `resolve_fossil_spec` is the one legacy door, every fossil emission golden, the K manifest bytes and the qualification digests unmoved, FORMAT_ROWS untouched; `--printer ENGINE` becomes the emission engine selector on every `generate`/`capacity` (v2 and fossil): optional, never geometry or identity, the engine's record decides the route (no `--route`), no engine → `cmyk1`; the record's two fields (route, solid RGB) live on `Printer`; FORMAT-SPACE §9 amended in §19 at W7 (§2.8). The receiver's legacy decode door is the receiver plan's. The recommendation of record had been a new `--engine` flag beside a refused `--printer`; the ruling reuses `--printer` and retires the meaning that made a second word necessary. Generator plan v0.2: W2. |
| R22 | the uneven probe on P1 | **RULED 2026-10-11 (owner: "We reach toner with uneven rungs, like cmy8 does."):** R4's probe `c2-cmy-r0775x0700@53x37` stays P1's c2 row and §11's print edge ("generator W4 + the owner's go, nothing else") stands; its pre-toner round trip (G1) is the grouped close through holo3's `fountain.Decoder` driven from generator-built rows at generator W3 — the decoder that qualified cmy8's column groups — not the core decoder (which refuses grouped codes by design) and not a receiver wave. The review's alternatives (receiver W1 + generator W6 on the print edge; a uniform c2 row first; a test-only grouped decoder in core) were not taken. Generator plan v0.2: W2's G1. |
| R23 | the emission construct | **RULED 2026-10-11 (owner: "Maybe we can/should make the emission code pure .ps without pjl etc. same as k and cmy8, and just emit data as an image mask (similar to cmy8, just not in cmyk but rgb instead)? this should take care of '8-bit Indexed DeviceRGB, PJL-wrapped, raw 9100' potentially not being available, loosing a pjl wrapper, job size concern." and "footing honesty: what is this about? again... like c2-cmy8 and c3-cmy8, just in RGB with fewer possible pixel values (the 3 optimal unscreened toner edges, and white)"):** the `rgb` route = three single-toner 1-bit imagemasks per page painted at the engine's solid device-RGB values (K's construct, `PSDoc.put_bitmap` with a colour), plain PostScript, no PJL, HP calls, prologue, palette or bands; the engine record = the route it honours + the three solid values (cmy8's shape); `--printer` alone selects (R21), no `--route`; the e041 Indexed construct recorded as the measured fallback, built only if the probe sheet shows the masks screened. The reading recorded with the ruling: a 1-bit DeviceRGB composite cannot carry the M281's displaced solid points (three distinct R values on one bit), hence masks; the colour imagemask is unmeasured on the M281 and the probe sheet precedes P1's volume sheets (§2.8, §11). |
| R24 | the addressing dark set (receiver I-9; the review's Q1) | **RULED 2026-10-11 night (owner: "address bits are what they are, dust is what it is, for address decode, placing, and cold … in close relation to how cmy8 works"):** no dark set to choose — the receiver reads the sites AS LAID in the channel it uses (R: word sites C dark, keyed W/Y light; dust M light), as cmy8's {CM, W} words are read in luma; the review's (a) {C} is this ruling's consequence, (c) {C, M} would read dust against the law. REASONING-LOG 2026-10-11 night. |
| R25 | the receiver's build order (the review's Q2) | **RULED 2026-10-11 night (owner: "starting with the engine being able to handle cmy, and then a minimal set of workers, and then do a trial decode … providing all cmy8 workers with a cmy translation should not be terribly hard, even if not perfectly calibrated"):** engine first (identity, the format-law copies, the fact shapes), the minimal worker set, a trial decode on the e044 c3 sheet (M1); the cmy8 rows get a cmy TRANSLATION through the label mapping, not new rows, calibration refined later; `tiles.cond` stands under R5. |
| R25a | kview | **RULED 2026-10-11 night (owner: "kview sounds interesting, and like a cmy adaptation of planek … parking kview until we understand if it is needed, or if it should maybe go to the analyzer instead is okay, let's just not forget about it"):** `tiles.kview` is a PARKED ROW of record (receiver plan A10), the analyzer a possible home (analyzer plan's note); planek's own translation (a toner's presence → the label bits) is the breadth principle's, not kview. |
| R26–R35 | pending (2026-10-12) | **PENDING 2026-10-12 (R31 RULED the same night, see its item):** ten rulings owed after the receiver's A9 and the two e044 decodes, collected one line each with where each is argued in CMY-RECEIVER-PLAN §5, "Open after A9 (2026-10-12)": R26 generator W2b part (ii) (the evidence recipes to `L:`, or a private copy of the old constructor; then the three retentions go); R27 the manifest "route" key for a named `cmyk1` engine (six manifest goldens: re-freeze or drop); R28 A3's erasure trigger `cmy_unsupported_streams`, its paper record owed; R29 A6's descriptor order, the `cond150` budget and the 10 %-flipped arm (G13's dated note, §11); R30 A7's cmy7 swim floor 64 → 56, cmy7's field rows, a harder residue stimulus, cmy8's `choose_offset` on clean pages; R31 the PAVA evaluator's block-edge nodes (an amendment to R11's evaluator clause) and the cmy8 logit A/B — MEASURED held out and **RULED 2026-10-12 (owner): PASSED** — "we pass on R31, it does not seem to pay at this stage, maybe note down as a possible mechanism for the analyzer?" The shipped evaluator (PAVA centroid nodes joined in logit for the cmy chain; `PavaMap.logit_interpolation` off for cmy8) stands; R11's evaluator clause is not amended; block-edge nodes are recorded as a candidate ANALYZER arm (CMY-DESIGN §9.1, analyzer DESIGN §13) — an alternative per-(tile-stream, lane) evaluator the analyzer's arms × rules ladder can try where a map is separable, paid for in certificates like every arm, never a receiver default. (measure/cmy_calibration/RESULTS-2026-10-12-evaluator.md: block-edge removes the separable sims' squeeze and reads 0.0006–0.0062 bit/cell below centroid-logit on every c2 paper band, 12 of 12 page fits; the cmy8 logit A/B stays open under R11); R32 A9's C refusal (R17's finding), A5's line for Y's lean toward M, the full-page Z/A as tests, the half-dot pin quantum, zlib for the frozen TIFFs; R33 the pricing line with paper numbers (experiments/044 §044.3, §044.4); R34 `--complete` runs of e044 A and B, the owner's go; R35 the M vectors (the field's re-arm, the p axis for M anchors, a dust-only anchor floor). |

## 13. Docs obligations (P-AXIS §7 style)

**LANDED:** v0.1 (2026-10-06) with the CLAUDE.md bullet, a REASONING-LOG
entry, `.claude/memories/cmy-family.md`, pointers in
REDUCED-ALPHABET-ERASURE-ROWS (and its §7 withdrawal) and COLOR-DESIGN D1;
this v0.2 with the CLAUDE.md bullet, the memory and a 2026-10-09
REASONING-LOG entry brought to v0.2's furniture and calibration, and the
three workplans (`docs/CMY-GENERATOR-PLAN.md`,
`src/holo/receiver/docs/CMY-RECEIVER-PLAN.md`, `analyzer/CMY-ANALYZER-PLAN.md`)
— all on this branch, 2026-10-09. The rulings of §12 are recorded in
place as the owner takes them (R1–R20 and RA-1..RA-7 dispositioned,
2026-10-09/10). **Timing (R16
RULED 2026-10-10):** this document is the design of record until the
build; the normative amendments land in generator W7 (= the plan's W4, written 2026-10-11) with the goldens
and pinned numbers they describe; FORMAT-SPACE-DISPATCH (generator W0,
before code) and API.md (receiver W0, frozen with I-1..I-11) land
EARLIER. **2026-10-11 (R21, R22):** FORMAT-SPACE §19 also records
`--printer` as the emission engine selector and the retirement of the
legacy generation door onto the fossil rows, amending §9's "generation
stops selecting printers" to "selects an ENGINE for emission, never a
geometry"; HOLO-DESIGN §8's "emission paths" line is confirmed; the
receiver plan owes the receiver-side retirement of `decode
--coding/--printer`; the generator plan (v0.2, rewritten compact 2026-10-11) carries the
retirement and the `rgb` route in its W2 and the R22 form of G1.
**On main:** the e036 bullet's "net field" for 284.9. **WITH THE BUILD:**
FORMAT-SPACE §19 (+ the devices footing's return to v2 emission,
keying-neutral, against §9, R9; + ONE sentence recording domain 9's
u-range extension for the cmy word keys, u = n_dust + site, R10);
HOLO-DESIGN v0.27 §13.38 + F4 / F6 / F8 / F14 / F15 + §4.2 / §6.2
(§13.38 and F15 with the route block and the per-engine emission footing,
R9); PRINTED-FORMAT
§12.5 (with the cmy dust law as a function of p, R3; the route block and
the per-engine emission footing — points, halftone selection, prologue,
evidence grade — R9; the word-zero preselection, R10) + the §4 aux line
and domain 9's u cell (no new row, R10) + §5's esi line;
CMY8-POOLED-FOUNTAIN §7, CMY8-COLUMN-GROUPS §12; a LAYERS row;
FORMAT-SPACE-DISPATCH BEFORE code;
API.md (W0); SCHEDULE.md; the devices text; an analyzer family section
(ruling 11 amended); PAGE-FIELD-DESIGN §2.3 amended per R7 (RULED
2026-10-09: the gauge follows the POSE's ink, not the word ink — for cmy
C alone, F_C ≡ 0, M and Y free; its "one ink" sentence restated) — receiver
W6; DIAG-DESIGN (stream-named panes, readout) — receiver W9;
RECEIVER-MOVE-PLAN §6 (the R8 ruling, either way) — receiver W1;
analyzer/PAGE-FIELD-PLAN §0 (the gauge per family, citing I-8) — analyzer
A8. **OWED MEASUREMENTS:** the labelling artefact (generator W0); G10;
the both-routes M281 sheet; the emission probe's fine sweep and
spectral-midpoint analysis (R9, §2.8; the M281's on P1's day); the
another-day control (the dust spectral line struck 2026-10-09, R3).
**OWED RECEIVER LINES (R11, not R11's to settle):** `PavaMap`'s
probability-linear interpolation in cmy8's own marginals (a null / A-B on
archived cmy8 states before any change to `color_model.py`); the
two-capture sum's overconfidence (cmy8-inherited, every chain); W3a's
erasure trigger (the collapse test alone misses 6–9 % of dead-Y regions
at one tile).
**BUILT (2026-10-11, branch `cmy-generator`; generator plan v0.4's
waves, which renumber this section's W-names — its header maps them):**
- [x] W0 — 7bad672c: the names frozen (`Family.CMY`, `CMY_STATE_IDS`,
  `CMY_LABEL_TO_STATE`, streams `hi`/`lo`, dither aux 1/2, fountain aux
  None, `color_word_zero_mask`) and G11's spec vectors typed from this
  text before the code (`tests/holo/test_cmy_vectors.py`, 36 pins);
  receiver I-3 re-opened by name and amended; R10/R12 and §6 rows
  corrected.
- [x] W1 — 128ed3cb: the format law (§2.1–§2.6): the alphabet law,
  `cmy_codec`, the grammar's explicit branches, the label table and
  `cmy_soft_demap`, the word key on domain 9, the word rule and the
  per-tile balance law inside the furniture functions,
  `cmy_encode_payload`; the 36 vectors pass, every existing golden
  unchanged.
- [x] W2a — 6926f6ef: emission and the print edge (§2.8, R21–R23): the
  `rgb` route, `--printer` beside `--format`, the manifest's cmy fields,
  emission goldens for six rows on both routes, printed-size goldens,
  G7 (gs, 0 differing dots), G1 by R22 (the grouped round trip through
  holo3's `close_volume`, byte-exact on every ruled row).
- [x] W2b part (i) — 69c1423d, 2026-10-12, branch `cmy-w2b` (merged
  0f60ad7c): R21's retirement minus three retentions kept for the
  evidence recipes; design §3.3's cmy rows exact. [ ] Part (ii), the
  three retentions, and the manifest "route" key: the owner's rulings
  R26, R27 (§12).
- [x] W3 — f0401b30, 2026-10-12, branch `cmy-w2b` (merged 0f60ad7c): G1 through the receiver's
  identity (`resolve_format_ref` → `close_volume`, byte-exact on every
  ruled row) and the dead-stream twin G2–G4 at each row's dial (dead Y,
  dead M close; dead C stays open); the rows' agreement pinned in the
  drift lane.
- [x] W4 — a7846d33, 2026-10-11: the normative documents (the status
  list below).
**STATUS 2026-10-12 — the lists above, item by item (shas on branch
`cmy-generator`; the receiver's waves per CMY-RECEIVER-PLAN v0.3, built
through A9):**
- [x] FORMAT-SPACE §19, with domain 9's u-range sentence and §9's engine
  amendment — a7846d33 (generator W4).
- [x] HOLO-DESIGN v0.27 §13.38 + F4/F6/F8/F14/F15 — a7846d33. [ ] §4.2 /
  §5.3 / §6.2 — open (not in W4's list; the plan's W4 record says so).
- [x] PRINTED-FORMAT §12.5 + the §4 aux line, domain 9's u cell, §5's esi
  line — a7846d33.
- [x] CMY8-POOLED-FOUNTAIN §7, CMY8-COLUMN-GROUPS §12, the LAYERS row —
  a7846d33.
- [x] FORMAT-SPACE-DISPATCH — a7846d33, with the W4 documents, i.e. after
  W0–W2a's code, not before it as R16 put it; its dated note brought to
  the retirement at 69c1423d.
- [x] API.md — d99ae099 (receiver A0, the streams paragraph), then each
  receiver wave through 6e8a61d0 (§2, §3, §5, §6, §6b).
- [x] SCHEDULE.md — regenerated from the descriptors at 826fe72f (A6,
  `tiles.cond`); the residue rows' cmy translation in its prose at
  f8df7b2e (A7, the generated block identical); regenerated equal at
  6e8a61d0 (A8).
- [x] the devices text — the `hp-m281` emission record 79332798, its
  values b005fae4, `hp-m281-ink` given the engine's route and values at
  6926f6ef, `color_route: str | None` and the `canon-iradv-c257` row at
  69c1423d.
- [x] PAGE-FIELD-DESIGN §2.3 per R7 — 0fe23a33 (receiver A5).
- [x] DIAG-DESIGN — §4's producer bill and the cmy lines, f8df7b2e
  (receiver A7).
- [ ] RECEIVER-MOVE-PLAN §6 (R8) — open, untouched on the branch.
- [ ] the analyzer family section and analyzer/PAGE-FIELD-PLAN §0 —
  open, with analyzer A8 (the analyzer plan's waves are unbuilt; its
  A1-pre sites rode receiver A1, aadf5353, and `calibrate`/`ladder` took
  the alphabet from the row at receiver A3, 00da184f).
- [x] the CLAUDE.md bullet — a7846d33, brought to the built state at
  46a2be6e. [ ] `.claude/memories/cmy-family.md` — open: last touched at
  a00d8b55 (2026-10-10), it still reads "unbuilt, unsimulated,
  unprinted".
- [x] REASONING-LOG — the 2026-10-11 entries (a7846d33; R24/R25 at
  598f19be, R25a at 46b8fe9c) and the 2026-10-12 entry.
- [ ] On main: the e036 bullet's "net field" for 284.9 — open (CLAUDE.md
  still reads "net field").
- OWED MEASUREMENTS: [ ] the labelling artefact — not built: no
  `measure/cmy_labelling/`, the generator plan v0.3/v0.4 carries no
  W0(e), and W1's goldens froze at 128ed3cb without it. [ ] G10 —
  deferred to before M1 (receiver plan A2); M1 and M2 placed and closed
  on R (experiments/044 §044.3, §044.4), the comparison mode not built.
  [ ] the both-routes M281 sheet — open: P1 printed the `rgb` route only,
  two 2400 captures per sheet, no 4800 capture in the record (§044.1). [x] the M281's emission
  probe — e043's three sheets (experiments/043-m281-cmy-probe.md; values
  applied at b005fae4); [ ] its spectral-midpoint analysis — still owed.
  [ ] the another-day control (P3) — open.
- OWED RECEIVER LINES: `PavaMap`'s interpolation in cmy8's marginals —
  the switch built at receiver A8 (6e8a61d0, `PavaMap.logit_interpolation`,
  off for cmy8), [ ] the A/B owed (R31); [ ] the two-capture sum — open,
  and cmy's own two-capture rows (`tiles.union`, `color.pooled_ctx`)
  unproven (receiver plan A7, A9); [x] W3a's erasure trigger — built at
  receiver A3 (00da184f, `cmy_unsupported_streams`), [ ] for the owner's
  look and its paper record (R28).
- [ ] The rulings R26–R35 (§12) — pending; CMY-RECEIVER-PLAN §5.
**OWED BEFORE ANY cmy ROW ABOVE p120 PRINTS (R12):** the derivation of
the receiver's support-floor envelope for cmy's dust law —
`BER_ENVELOPE` 0.08 (`receiver/plugins/place.py:44`) was derived for
cmy8's, which it fails above p ≈ 132 under a dead Y, toward false accept
(P-AXIS-DESIGN §4, e(p) = (1/3)·n_dust/p); cmy's crossover is not
derived (its p120 dust is all M, its dead-Y word '0' stays '0').

## 14. Provenance and record hygiene

### 14.1 Record hygiene (D22) — what this document does not inherit

| inherited claim | what this design holds | where |
|---|---|---|
| "benefits from 4800" (M281-COLOUR §6A) | no cell-state change FOR THE CONTEXT-FREE CLASSIFIER (§041.5p); a receiver lever (sub-dot pose; e034's +14 of 17) | §9 |
| the colour-count hypothesis | refuted (S16) and resolved on main (M281-COLOUR §6B') | §1.2 |
| "measurements on an unmerged branch" (v0.1) | merged into main 4240a3c; cited by path and SECTION | header |
| the two b/mm² bases | per field here; per page in e033/e036 and main's e036 bullet | §3.3 |
| the branch's two-stage pairing and c2 rung | hi-first reaches only r0775 on its second; r0850 needs lo first (the rung pairing, not the calibration chain, R11); the multi-print minimum is r0700x0625 | §2.2, §2.4 |
| the labelling's band | S14 B3: corner cyan, SCREENED on the bars, `false ColorSmartColorMatching` (`ps_scale.py:78-85, 287-288`); the dead-plane argument decides | §2.2 |
| "M (240,0,192) or (240,0,208)" | only (240,0,192) printed at page scale; ~16 levels of yellow cross-talk (e041 §041.5) | §2.8 |
| REDUCED-ALPHABET-ERASURE-ROWS §5 on the M281 | stale against e041; withdrawn by that note's §7 (2026-10-06) | §13 |
| the v0.1 brief's premises | "the one colour alphabet unscreened"; "an UPPER bound"; the addressing proxies; `plane: int \| None`; the bare-`else` hazard — corrected in v0.1 | §1, §7 |
| the v0.2 draft's premises (corrected on review, 2026-10-09) | the zero-state draw on domain 2; (M,) dust; (by the owner's R3 ruling, 2026-10-09) (M, M, M, Y) as the fix for periodicity and W0(c) — all-M returns at p120 as the balance law's value; the head's "10/10 on one tile"; attempt-time calibration; "six maps on one tile"; the B3 W row as C's robustness; the K view as a cold reader and its "50/50 C-vs-W" labels; "keep" the presence-bit clipping; F_C ≡ 0 under (R+G)/2; class_balanced_weights on an unweighted PAVA; a conditioned decode that "cannot" mint a wrong certificate; "every state ≥ 20" | §2.5, §2.7, §2.9, §7 |
| the v0.2 word law (R10's recommendation; corrected by the owner's ruling, 2026-10-10) | the EXACT per-tile split on an appended domain 16 → the per-site keystream preselection on domain 9 (u = n_dust + site, the key's MSB), the binomial per-tile Y count accepted under the standing floors; the R10 card's "a W→Y flip stops being an error" → a Y cell flips hi less often than a W cell (under hi-bit decoding a W→Y flip never was an error) | §2.5, §12 R10 |
| v0.2's calibration chain (R11's recommendation; corrected by the owner's ruling, 2026-10-10) | lo-first → hi-first, lo-first the recorded alternative; "conditioning hi on a certified lo reads calibrated maps" withdrawn (the derived hi\|lo forms equal the fitted within 0.003 bit, logit evaluator); the cmy gate as A3's single held-out improvement → cmy8's three-way gate as it stands; "prior-barrier certified cells" (v1 vocabulary) → certified cells read from the store at fire time; "the conditional maps arrive at ≥ 2 tiles" → qualify under A4b's floors, measured not to pay below ~8 tiles' furniture; per (capture, region) → per colour lane (capture, level, page); `PavaMap`'s probability-linear evaluation → logit-space interpolation in the cmy entry | §2.5, §2.7, §7c, §12 R11 |

### 14.2 Sources

The v0.1 brief, eleven subsystem maps and the v0.2 brief (scratch, not
committed): briefs over maps, v0.2 over v0.1, EXCEPT where the 2026-10-09
review's evidence, re-verified against the tree and the measurements,
overturned a v0.2-brief recommendation (14.1's last row); the lookup
map's free text is not used. Main at `4240a3c`: M281-COLOUR, the e041/e042
logs and generators, the two `measurements.json`,
`measure/e041_scale_readout.py`. Capacity runs (2026-10-06); one in-tree
`column_groups` call; one read-only site-class count. No decode, analyzer
pass or test lane. Code citations re-read on 2026-10-09 (the rebase moved
nothing under `src/` or `analyzer/`). R11's measurement (2026-10-10):
the instrument `measure/cmy_calibration/` (commits e2689c80, cebe7bf4 on
this branch) over the e041 S14/S17 and the AltaLink X1 scans, artefacts
in `scratch/cmy-calibration-20261010/` (not committed), the compact
extract `measure/cmy_calibration/RESULTS-2026-10-10.md`; three Opus
refuters and a Sonnet number check; every reading UNRATIFIED under the
protocol's stop rule (control C6 failed on the `PavaMap` interpolation
defect).

### 14.3 Reader arithmetic that is NOT a record claim

S14 B3's labelling numbers ARE the record's (M281-COLOUR §6A). Reader
arithmetic on the committed `confusion_loo`, labelled where used: the
per-print I(hi) / I(lo) (B3 0.897 / 0.863, R9 0.868 / 0.821, T12 0.866 /
0.8175, U12 0.805 / 0.746, X10 0.876 / 0.865) and conditionals; X10's MI
and BICM; §2.5's flip rates, W rows and word budgets; the rung fits; the
death map; the binomial tails; §3.3's cmy bytes and b/mm²; the pair table
(confirmed in-tree); the bar ratios, cross-talk and pose ink weights; the
metadata floors and the LFSR check; the analyzer's label supply; the
3-plane row's +20 %.
