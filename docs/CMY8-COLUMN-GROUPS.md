# CMY8-COLUMN-GROUPS — the width-heterogeneous pool (uneven rung triplets)

Status: **RULED 2026-09-04 (seven rulings, §9), BUILT the same day on
branch `cmy8-column-groups` and REVIEWED** — src/holo sheet generation
and the holo3 receiver, sim-qualified (§8); the review round's
dispositions are §10; NOT printed (F14: a mixed row is provisional
until a printed volume closes). The design was worked out
in dialogue the same morning (REASONING-LOG "2026-09-04 — CMY8 uneven
rungs: the column-group pool"); this is the "future cmy8 generation"
FORMAT-SPACE §5 / §15.3(1) reserved when the format-space build found
that one pooled fountain has one symbol width — ruled to live under
gen-v1, since no mixed identity was ever emitted and uniform identities
are untouched bit for bit. Scope ruled: **the src/holo v1 receiver and
holo2 are not touched** — a mixed row reaching the v1 receiver fails on
the profile's common-width property, holo2 keeps refusing the triplet,
and the cross-tree oracle records that as an intended divergence. Holo2
was retired 2026-09-05; §6 and §9 ruling 7 are now the record of that
divergence.
Successor of docs/CMY8-POOLED-FOUNTAIN.md (the -v1 pool), which it
extends and does not replace; every frozen-code claim below was read in
both trees and is marked **[verified]**.

## 0. The ask

Per-plane LDPC rungs for CMY8 — Y below C/M — under ONE pooled fountain
(one K, one block structure, one close), so that a weak-but-alive Y
buys its margin from its own parity cells, and a dead Y costs the pool
only Y's share. The id grammar already admitted `r{C}x{M}x{Y}`
(FORMAT-SPACE §6) and the constructors refused any triplet whose rungs
differed in `k_bits` — src/holo `families.cmy8_codec`, holo3
`identity._require_constructible` **[verified, now lifted]**.
INDEPENDENT-PLANES §H lists the Y lever (Y r0550, C/M r0700 — built
here with Y at r0547, the same width, ruling 6) as "blocked by the
gen-v1 width-class law". The measured motivation is on
the record: Y trails C/M by ~7% uniformly at r0547 (e035), Y dead bands
at r0700/r0850 (e033/e034, the x-registration sinusoid), Y dead on the
starved M281 (e017/e030).

## 1. Why the widths were locked — exactly two axes

Per plane and tile: user bits = k_bits(rung) − p − 32 (CRC), and the
fountain symbol width S = user bits − 1 (the metadata bit)
**[verified: holo3 `identity._streams_for`; src/holo
`profiles.StreamProfile.symbol_bits`]**. At p120:

| rung | k_bits | user bits | symbol width S |
|---|---|---|---|
| r0547 / r0550 | 2240 | 2088 | 2087 |
| r0625 | 2560 | 2408 | 2407 |
| r0700 | 2880 | 2728 | 2727 |
| r0775 | 3200 | 3048 | 3047 |
| r0850 | 3520 | 3368 | 3367 |

Every width is 320m + 167, so any two distinct widths are coprime — a
fact §3.9 turns on. The pooled fountain XORs whole symbols, so every
encoded symbol has one width S; at a fixed cell count per plane
(4096 − p) and a fixed S, the rate is fixed. Asymmetry therefore has
exactly two axes: change the bits a tile carries (this design), or
change the cells a codeword spans (§7: supertiles, cross-plane
borrowing, furniture — rejected or dominated).

## 2. The fundament: the pool is column-separable

Source symbols x_0..x_{K−1} are S-bit rows; the tile at symbol index e
carries y_e = ⊕_i G[e,i]·x_i with G's row a pure function of e (unit row
below K, dense keystream row above — fountain-v2, HOLO-DESIGN §7.2).
Bit column j of every y_e depends only on bit column j of the x_i. So a
block is not one linear system but S of them, one per bit position,
sharing the same G. The frozen solver is literally that: Gaussian
elimination on the packed generator rows with the symbol bits carried
along as values **[verified: holo3 `fountain._ge_solve_gf2`]**. Nothing
in the algebra requires every equation to carry every column.

Toy (K=3, S=4): rows a=(1,1,0), b=(0,1,1), c=(1,0,0) have rank 3;
x1=y_c, x2=y_a⊕y_c, x3=y_b⊕y_a⊕y_c, applied to bit 0, then bit 1, ….
If tile b arrives with only bits 0–1, columns 0–1 still solve and
columns 2–3 (rows a, c only, rank 2) leave x3 unknown there. That is
the whole mechanism and the whole hazard:

- **Encoded-side padding is not an option.** A padded bit is not a
  known value of the XOR; it is a false equation.
- **Padding the strong planes down to Y's width** is today's uniform
  triplet at Y's rung — it discards C/M capacity.
- **A fixed truncation is nearly useless.** If every Y tile carried the
  first S_Y columns, columns S_Y..S−1 would only ever see C/M rows and
  would have to close from C/M alone; Y's equations land where they
  are not needed.
- **Truncation with rotation is rate-optimal.** Cut S into Z column
  groups; C/M tiles carry all Z, a Y tile carries n_Y of them, which
  ones rotating so every group receives Y's share. Each group's system
  then has N_C + N_M + N_Y·n_Y/Z rows and must reach rank K: a Y tile
  counts as exactly the fraction of a symbol it carries. This is RFC
  6330's sub-block structure (same ESI row applied to Z column groups,
  decoded with one schedule), used here so that a tile may carry a
  SUBSET of the sub-blocks rather than for memory.

## 3. The design as ruled and built

Let the plane widths be S_p (from the rung triplet), S = max S_p the
pool's one symbol width, Z the group count, `bounds[g] = ⌊g·S/Z⌋` the
group boundaries (widths within one bit of each other — a RATIONAL
partition, ruling 2), and `carried[p]` the CONSECUTIVE groups a plane-p
tile holds: the largest n such that every cyclic window of n groups
fits in S_p. The heavy plane carries all Z with zero spare; a lighter
plane's tile ends with a few zero bits (at most the width difference
between windows) that the close ignores. Equal widths are Z = 1, every
tile carrying the whole symbol (§3.6). Both trees implement the law in
one function, `column_groups(widths)` **[verified: src/holo
`core/fountain.py`, holo3 `format/fountain.py`; cross-tree pinned]**.

### 3.1 The symbol algebra is unchanged

Source symbols stay S-bit rows, fixed slices of the padded envelope;
G's rows stay fountain-v2's unit/dense rows on `DOMAIN_FOUNTAIN_ROW`;
blocks stay `B = ceil(k_total/16384)` with the balanced contiguous
split. A tile's slot holds **one (row, group) pair**: group g of the
row's equation, i.e. bits `[bounds[g], bounds[g+1])` of y_row. A repair
tile's slots all carry the SAME row; a systematic tile's slots carry
unit rows, one per chunk (`VolumeCode.tile_slots`).

### 3.2 The chunk stream and the systematic fill

Work in chunks (= groups). A block's `K_b·Z` source chunks — chunk c is
group c mod Z of in-block source row c // Z — fill its tiles' slots
CONSECUTIVELY in the block's fill order (§3.3): tile t with n slots
takes chunk positions [c_t, c_t + n) where c_t counts the slots of all
earlier positions of the block. Consequences:

- every payload bit sits in exactly one systematic slot — no holes;
- a Y tile holds consecutive chunks, hence consecutive group residues;
  the groups it misses advance per tile, and balance over any segment
  is exact to ±1 for ANY capacity (a residue class is visited equally
  often over a cycle of Z/gcd(n, Z) tiles);
- a systematic Y tile may straddle two symbols — lawful, each chunk is
  its own unit row in its own group's system;
- the last systematic tile of a block may straddle the boundary K_b·Z;
  its slots past the boundary carry ZEROS and the close ignores them
  (ruling 3; at most one tile per block).

### 3.3 Repair tiles and the fill order

Once c_t ≥ K_b·Z the tile is a repair tile: row = K_b + (its rank among
the block's repair tiles — the same in-block numbering fountain-v2
uses), slot s carries group (c_t + s) mod Z of that row. The residue
rotation runs on through the straddler's zero chunks. The block's dense
rows ride the keystream exactly as today.

The **fill order** within a (page, stream, block) segment (ruling 4): the
frozen ASCENDING local tile index for a uniform triplet — every -v1
identity, printed sheet J included, stays bit-identical — and the
`DOMAIN_BLOCK_ASSIGN` KEY order (the argsort `page_assignment` already
computes to split the segment into blocks) for a mixed triplet. Why not
raster for mixed rows: the missed group is a period-Z pattern along a
raster row shifted per row by n_Y·tiles_x mod Z; at 37 or 53 tiles per
row every column band sees all groups, but at tiles_x ≡ 0 (mod Z) the
missed group is constant down a column and a vertical Y dead band (the
measured AltaLink failure shape) spares one group and hits the rest —
the worst group loses a factor Z/n_Y more, and the close is set by the
worst group. Pure random group picking was rejected: it keeps whiteness
but makes each group's Y count binomial, so the dead-plane tier would
be a probability instead of a guarantee. Round-robin over the key order
gives exact per-page quotas per group AND spatial whiteness.

### 3.4 K, the envelope, the metadata word — the -v1 law verbatim

`k_meta = source_symbol_count(len, n·S)`, `k_total = n·k_meta`, the
envelope padded to `k_total·S` bits and sliced row-major — exactly the
pooled rule with S the widest stream's width **[verified: src/holo
`streamset.pooled_pack_source` / `pooled_source_symbol_count`; holo3
`close._pooled_volume_code`, `k_total = n·decoded.k`]**. The K field
carries k_meta; the word's layout and the field's VALUE are unchanged;
the version-0 argument of the pooling ruling applies verbatim (row
identity precedes any read). The canonical-K close gate is unchanged in
shape (recompute k_meta from the recovered length, require equality and
zero padding). Per-stream metadata equations at index counter·n +
stream are untouched. The narrower streams carry less than n·S per
site — that is the planner's business (§3.7), not the envelope's.

### 3.5 The close

A certificate's user bits already hold the tile's whole field — no
schema change. ONE decoder per row lives inside the engine's close
progress for the whole run (review item F5, §10): every certificate is
fed to it as it arrives, its per-(block, group) rows and row counts are
kept incrementally, a close attempt eliminates only the groups still
open, and a solved group stays solved — the systematic shortcut fires
per group when all K_b unit rows of that group are present, else the
packed elimination runs on that group's rows with the slot bits as
values **[verified: holo3 `fountain.Decoder`, `close.CloseProgress`]**.
The count gate is the same object's row counts per (block, group); a
block is count-ready when every open group has K_b rows (`min_rows`,
below). The
conflict rule (different certified values at one tile ⇒ integrity
error, never first-wins) and the ingest width check (a tile's bits
must be its stream's width) are the decoder's.

**Status is one honest number per block** (review item F7, §10): a
`BlockStatus` names the SCARCEST open group — the one with the largest
deficit, where a group's deficit is K_b minus its rank if it ran an
elimination and minus its row count otherwise — and carries that
group's `rows`, its `rank` (None until it ran an elimination; a rank
is forgotten the moment the group gains a row), `short` (the rows it
still needs — the lower bound on symbols the block requires),
`groups_open` and `n_groups`; the close rows, the diag pane, the JSON
status and the CLI "needs" line all read `short`, and an uneven row's
line reads "block #0 short 19 rows in 3/17 groups". The count gate is
NOT that group: it is `min_rows`, the fewest rows any open group holds,
because after an elimination a rank-deficient group with K_b rows ties
on deficit with groups that still lack rows (second review pass, §10).
An attempt eliminates a group only when its row count changed since
that group's last failed elimination — the memo is per group, so a new
C tile does not re-run the groups a new Y tile did not touch. Measured
by that pass on random systems at K = 400: a group whose missing unit
rows are covered by exactly as many dense rows solves its first
elimination about 30% of the time, 58 / 77 / 88% with one, two, three
extra rows — so the first attempt at count-ready usually fails, and
until groups start closing each consult re-eliminates every open group
a new tile touches (about 4 s per consult for the lever at sheet J's K,
tolerable; the two-stage elimination stays the lever if a real run ever
shows it).

Cost, measured by the review at sheet size (one group's elimination,
95% unit rows unless noted): K = 1176 (the 53x37 lever golden at
q = 0.5) 0.03 s; K = 4020 (sheet J's K) 0.26 s; K = 5883 (a whole page
as source) 0.56 s; K = 5883 all rows dense (the C plane dead) 5.1 s.
Times Z per attempt in the worst case, once — the persistent decoder
means an attempt never repeats a solved group, and the systematic
shortcut is per group, so on a real capture (every golden's
systematic region ends inside the C plane) it fires only where every
C tile of a group certified. The two-stage elimination that reuses the
C/M rows across groups stays the parked optimization.

### 3.6 The degenerate case is today, bit for bit (the fork guard)

With every width equal: Z = 1, `carried = (1,)·n`, every tile holds one
whole symbol at the row `block_row_of` reports, repair rows = K_b +
rank, the frozen fill order, one solve per block, the -v1 reserve. The
general code at a uniform triplet is bit-identical to the frozen
derivation — pinned by the verbatim oracles of
`tests/holo/test_pooled_fountain.py` and `test_holo_fountain.py`, the
frozen -v1 emission goldens (`test_pooled_gen.py`), holo3's
`GOLDEN_ASSIGNMENT_99083` and its pooled bit-identity pins — every
golden value and oracle assertion untouched and green (the modules were
repointed at the split's names and the status record, nothing more).

### 3.7 Capacity — the three tiers with weights

Per group, per block, per page, a stream with quota q_p tiles of n_p
consecutive groups gives every group ⌊q_p·n_p/Z⌋ or ⌈…⌉ rows (exact:
consecutive residue runs), so with `r` the reserve, `L = ceil(q·P)`,
`N = Σ_p n_p` **[verified: `pooled_page_capacity_sufficient` /
`pooled_max_k_for_pages` with `groups=`]**:

1. global fragments: `k_total + B·r ≤ ⌊q · P·T·N / Z⌋`
   (symbol-equivalents; the hypergeometric ε caveat of §7.2 unchanged);
2. page tier: `ceil(k_total/B) + r ≤ L · Σ_p ⌊(T//B)·n_p/Z⌋`;
3. plane tier, any ONE dead plane, all pages present:
   `ceil(k_total/B) + r ≤ P · (Σ_p ⌊(T//B)·n_p/Z⌋ − max_p ⌊(T//B)·n_p/Z⌋)`
   — the HEAVIEST plane binds.

Dial ceilings: the any-one-plane tier holds up to `1 − max_p n_p / N`,
the dead-Y case alone up to `1 − n_Y / N`. The dial policy stays the
pooling ruling (enforced and reported `guaranteed` at or below the
any-plane ceiling, dropped from sizing and reported
`not-at-this-dial (needs q <= 30/47)`-style above). The manifest's
`column_groups` block carries every plane's ceiling and the mean spare
bits per site; `effective_k_over_n` counts a physical symbol as the
groups it carries over Z; `n_repair` is the physical symbols past every
block's systematic positions (k_total at one group).

### 3.8 Reserve (ruling 5)

`r = 16 + bit_length(B·Z − 1)`: Z per-group solves per block enter the
one union bound (`rank_reserve_for(B, solves_per_block=Z)` — the
keyword was `n_streams`; the -v0 rows pass 3 for their three per-stream
solves, uniform pools pass 1, so the name now says what it counts).
Conservative: the groups share most rows, so their failures are
positively correlated.

### 3.9 Choosing Z (ruling 2)

Z = the argmin over 2..32 of the mean spare bits per site,
`Σ_p (S_p − n_p·S/Z)`, ties to the smaller Z; equal widths short-circuit
to one group. The argmin has no cost term — only the cap bounds Z — and
per-attempt close cost is linear in Z (§3.5); on the ladder the minima
sit at 7–21, and a toy pair of widths can land on Z = 31 with one-bit
groups (the reasoning log records one). Zero waste with few groups is impossible on this ladder
(every width is 320m + 167, so widths are pairwise coprime), but the
residue falls fast: the light plane misses d groups whose width should
equal S − S_Y, a multiple of 320, so Z near S/160 lands within a bit or
two. Equal-width groups (the first draft) left 37 bits per site on the
top row; the rational partition leaves 0.67.

## 4. Worked examples (exact widths, p120; the two ruled rows)

| | r0700 / r0700 / r0547 (the §H Y lever) | r0850 / r0850 / r0775 |
|---|---|---|
| S_C = S_M, S_Y | 2727, 2087 | 3367, 3047 |
| Z, group widths | 17, 160–161 bits | 21, 160–161 bits |
| groups per tile C : M : Y | 17 : 17 : 13 | 21 : 21 : 19 |
| mean spare bits per site | 28/17 = 1.65 | 2/3 |
| mean fountain bits per site | 7539 | 9780 |
| vs uniform at the heavy rung | 8181 (−7.8%) | 10101 (−3.2%) |
| vs uniform at the light rung | 6261 (+20.4%) | 9141 (+7.0%) |
| dead-Y tier holds to q ≤ | 34/47 = 0.723 (was 0.667) | 42/61 = 0.689 (was 0.667) |
| any-one-plane tier holds to q ≤ | 30/47 = 0.638 (was 0.667) | 40/61 = 0.656 (was 0.667) |
| reserve per block at B = 1 | 21 (was 16) | 21 (was 16) |

Y is r0547, not r0550: same width, and r0547 is the established narrow
Y bank (ruling 6). Fountain bits per site are before fountain overhead;
what a rung step buys in Y margin is the tile codec's business (§5) —
INDEPENDENT-PLANES §H's "~4 pp Y margin" stands as its own estimate.

## 5. What does not change

p120 furniture, dust, BCH words and counters, slot permutation,
detection, registration, per-(tile, stream) LDPC certification (the
tile codec already produced per-stream widths — holo3 `StreamFact`
carries `user_bits`/`symbol_bits` per stream; src/holo
`color_compose._symbols_for_tile` validates each stream's width
**[verified]**), certificates and their schema, evidence and
done-geometry, the metadata word and its per-stream equations, every K
row, every cmy7 row, every uniform cmy8 triplet, every -v0 row, every
printed sheet, every golden. Where the differing redundancy lives: Y's
lower rung is more parity cells per tile, settled inside the tile; the
fountain's only job is to accept the narrower result without waste.

## 6. Costs and limits (recorded)

- The any-one-plane tier ceiling drops below (n−1)/n because C and M
  carry more of the pool than Y (§4); the dead-Y ceiling rises. Both
  are in the manifest; neither is silent.
- Solver: up to Z eliminations per block, each measured at sheet size
  in §3.5; under the persistent decoder a group is eliminated again
  only when its rows changed, and a solved group never; the two-stage
  form is the known optimization.
- Reserve grows by bit_length(Z) rows per block (§3.8).
- The systematic shortcut becomes per group; a straddling tile leaves
  one group of one symbol to a repair row.
- `source_row_of` / `generator_row` describe a one-group symbol and
  refuse a column-group code (a tile carries several rows there); so
  does the src/holo core `Decoder` (review item F1: fed a grouped
  code's own emission it had reported "solved" with a wrong matrix).
- The v1 receiver gets no message of its own (ruling 7): a mixed row
  fails on `common_user_bits` ("stream user widths differ"). holo2's
  own refusal stays; `tests/holo2_oracles/test_oracle_lattice.py`
  (deleted 2026-09-05 at a805888) moved the triplet from the shared
  refusals to `INTENDED_DIVERGENCES`, and `test_oracle_close.py`
  (deleted 2026-09-05 at a805888) declares the fountain and streamset
  carries `ORIGIN_MOVED`. Holo2 itself was retired the same day: this
  section and §9 ruling 7 are now the only record of the
  src/holo-vs-holo2 divergence, since the oracles that held it are
  gone.
- Physical qualification remains F14-gated.

## 7. Rejected shapes, with the reason each fails

- **A site-wide N-group symbol with fixed plane ownership of groups**
  (C: the first third, M: the second, Y: the rest): every Y group's
  system receives Y rows only; a dead Y kills the payload outright —
  the cmy7 joint-packing failure (e032) in a new coat. The per-site
  stride here is a FILL stride, never a symbol width.
- **Fixed slice, encoded-side padding, strong-plane padding** — §2.
- **Equal-width groups** — the first draft; the rational partition
  halves-to-zeroes its spare at every Z (§3.9).
- **Distinct ESIs per group** (K·Z narrow unknowns, one row per slot):
  the same information, but no shared-row structure, Z× the blocks,
  and the 18-bit K field overflows on large volumes.
- **Pure random group picking** — whiteness without exact quotas (§3.3).
- **Raster round-robin** — geometry luck at tiles_x ≡ 0 mod Z (§3.3).
- **Y supertile** (one Y codeword across k colocated sites): rates only
  r/k; cross-site certification; far too coarse for a 7% deficit.
- **Cross-plane cell borrowing** (Y's codeword takes C/M cells): fine-
  grained and fountain-free, but the C/M codewords get shorter and more
  fragile exactly when Y is dead and they are all that is left —
  strictly worse than today under plane death.
- **Moving furniture** (drop Y's address word for ~100 cells, a ~2.4%
  rate cut): small, and Y loses its own placement anchor.
- **Y at c3** — DOMINATED per INDEPENDENT-PLANES §H, and it changes
  Y's bits per tile, so it needs this mechanism anyway. Solving the
  width law once at the fountain unlocks every per-plane knob.

## 11. Z vs p — the ruled identities are p120-CONDITIONAL (2026-09-16)

§4's worked examples say "exact widths, p120" and mean it more strongly
than it reads. A stream's width is `S = k_bits − p − 33`, so every
width moves with the furniture density `p`, and `(Z, bounds, carried)`
is a pure function of the widths — which makes Z a function of `p` too.
Since the p axis became emittable and readable (FORMAT-SPACE §18,
HOLO-DESIGN §13.37), a triplet can be spelled at any lawful `p`, and
the grouping it gets is NOT the one ruled here. Computed through
`holo.core.column_groups`:

| triplet | p | widths C:M:Y | Z | carried | spare bits/site | dead-Y | any-one |
|---|---|---|---|---|---|---|---|
| r0700x0700x0547 | 120 | 2727:2727:2087 | 17 | 17:17:13 | 1.6 | 34/47 | 30/47 |
| r0700x0700x0547 | 172 | 2675:2675:2035 | 25 | 25:25:19 | 2.0 | 50/69 | 44/69 |
| r0700x0700x0547 | 244 | 2603:2603:1963 | 4 | 4:4:3 | 10.8 | 8/11 | 7/11 |
| r0700x0700x0547 | 300 | 2547:2547:1907 | 31 | 31:31:23 | 17.3 | 62/85 | 54/85 |
| r0850x0850x0775 | 120 | 3367:3367:3047 | 21 | 21:21:19 | 0.7 | 42/61 | 40/61 |
| r0850x0850x0775 | 172 | 3315:3315:2995 | 31 | 31:31:28 | 0.8 | 31/45 | 59/90 |
| r0850x0850x0775 | 244 | 3243:3243:2923 | 10 | 10:10:9 | 4.3 | 20/29 | 19/29 |
| r0850x0850x0775 | 300 | 3187:3187:2867 | 29 | 29:29:26 | 9.7 | 29/42 | 55/84 |

Z is NON-MONOTONE in `p`, and so is the waste: p244 collapses the Y
lever from 17 groups to 4 and RAISES its zero tails from 1.6 to 10.8
bits per site, while p172 costs the r0700 triplet +0.35 bits per site
(1.65 -> 2.00) and the r0850 one +0.14 (0.67 -> 0.81). That is the argmin doing its job — the partition that best
divides one width need not divide the shifted one — but it means the
identities §4 works out, the Z17 and Z21 of ruling 3, and the tier
ceilings in every table above are statements about p120 rows and about
nothing else.

Owed before any `p` row of a ruled triplet is minted: its own
`EMIT_GOLDENS` entry per (triplet, p). The mechanism itself needs
nothing — a triplet at p300 composes by construction under the same
code, verified at `c2-cmy8-r0700x0700x0547-p300@10x10` (3,796 cells,
tests/holo/test_color_compose.py) — but a golden is what makes an
emitted row a frozen one, and this table is the reason a p120 golden
cannot stand in for it. §7's rejected shapes and §9's rulings are
unaffected: they are about the ALGEBRA, which does not depend on `p`.

## 12. The cmy pairs — the same law at n = 2 (BUILT 2026-10-11, not printed)

The cmy family (docs/CMY-DESIGN.md v0.3 §2.4, §3.2; FORMAT-SPACE §19;
HOLO-DESIGN §13.38; branch `cmy-generator`, commits 128ed3cb and
6926f6ef) pools its two label-bit streams, `hi` and `lo`, through this
document's partition unchanged — the law is n-generic, nothing was
added to it. A uniform pair is the one-group case (Z = 1); an uneven
pair `r{hi}x{lo}` (the ruled ones hi-heavy) is partitioned by §3.9's
argmin.
Exact widths S = k_bits − p − 33; the ruled pairs at p120, pinned from
the design text in tests/holo/test_cmy_vectors.py:

| pair (hi × lo) | widths | Z | carried hi : lo | hi-dead ceiling | lo-dead ceiling | reserve (one block) |
|---|---|---|---|---|---|---|
| r0775x0700 (the first c2 probe, R4) | 3047 : 2727 | 19 | 19 : 17 | 17/36 | 19/36 | 21 |
| r0850x0775 | 3367 : 3047 | 21 | 21 : 19 | 19/40 | 21/40 | 21 |
| r0850x0700 | 3367 : 2727 | 21 | 21 : 17 | 17/38 | 21/38 | 21 |
| r0700x0547 | 2727 : 2087 | 17 | 17 : 13 | 13/30 | 17/30 | 21 |
| r0700x0625 | 2727 : 2407 | 17 | 17 : 15 | 15/32 | 17/32 | 21 |

As §11 found for the triplets, Z is p-conditional and non-monotone in
p: at p300 r0775x0700 → Z 26 (26 : 23), r0700x0625 → Z 31, r0850x0700
→ Z 29 (test_cmy_vectors.py); at p200 r0850x0700 collapses to Z 5
(tests/holo/test_column_groups.py). The column-grouped close of a cmy
row runs through holo3's grouped decoder (`close_volume` over a row
built from the FormatSpec, tests/holo/test_cmy_round_trip.py: every
ruled row byte-exact at 10x10); the core decoder still refuses a
column-group code (§10). The tiers read "stream" for cmy: the
`dead_stream_ceiling` manifest key, because a stream's death is a toner's
through the label table (dead Y → lo, dead M → hi, dead C → both).
