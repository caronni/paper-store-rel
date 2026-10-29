# CMY8-POOLED-FOUNTAIN — one stream-mixed outer code for CMY8 (-v1 rows)

Status: **design ADOPTED by user rulings 2026-08-13; implementation in
progress; rows land append-only, catalog-only, provisional** (F14
unchanged — paper qualification remains open and hardware-gated).
Execution plan: `docs/CMY8-POOLING-PLAN.md`. The HOLO-DESIGN ledger entry
and the COLOR-INTEGRATION-DESIGN §8.3 supersession row land with the
implementation commits. Provenance: the 2026-08-13 dead-plane dialogue,
recorded as REASONING-LOG "Session 2026-08-13 — CMY8 fountain pooling
and the dead-plane trade". The four adopted rulings are §0.
Verification pass 2026-08-13: every frozen-code
claim in §2 checked against src/holo (all HOLD); the corrections it
forced are marked **[verified …]** below.

## 0. Adopted rulings (2026-08-13)

1. **Append `-v1` rows** (`c2-cmy8-p120-v1`, `c3-cmy8-p120-v1`); the
   `-v0` rows stay in the catalog and stay decodable — the e030/e032
   printed sheets and the COLOR-UPLIFT eight-capture qualification corpus
   remain living regression anchors. The per-stream fountain/close path
   is retained for `-v0` exactly as it is.
2. **Stream-exact block quotas**: block membership is quota'd per
   (block, page, stream) and keystream-shuffled within — dead-plane loss
   becomes a DETERMINISTIC promise tier, not a probabilistic one.
3. **Per-stream metadata equations bundled** (the "Q2" question):
   equation index `eq = counter·n_streams + stream_idx` replaces the
   replicated per-tile bit — same 1-bit cost, 3× equation density,
   fragment metadata floor drops from ~48 to ~16 CMY8 tiles.
4. **Simulation-only qualification this session**; printing is a later,
   separately user-gated act.
5. **Dial policy (ruled 2026-08-14):** pooled rows accept any legal q;
   the plane tier is DIAL-CONDITIONAL — enforced in sizing and
   "guaranteed" at q ≤ (n−1)/n, dropped from sizing and loudly reported
   "not at this dial" above; never a refusal. Supersedes the refusal
   wording below where they conflict.

## 1. The problem (measured, not hypothetical)

Format v1 CMY8 carries one envelope through three independent per-stream
fountains (C, M, Y), stream-major sliced at common K
(COLOR-INTEGRATION-DESIGN §8.3). Every stream must independently reach
rank K_b in every one of its blocks; the Y stream's symbols live
exclusively in Y ink. Consequently **a completely failed plane is fatal
at any K/N**: zero Y certificates ⇒ Y never reaches rank ⇒ reassembly
refuses — while K/N = 0.5 was tolerating a 50% loss *within* each
stream. The redundancy axis pointed only within streams, never across
planes.

The scenario is on our own record: e017's colour print failed on the
Y-starved M281; e028 measured Y as the weak cartridge (tone 0.351 vs K
0.656); e030's first CMY8 pages on that engine recovered NEITHER volume.
Y is also the archival-risk plane (azo fade). Plane-common failure is a
*known correlated damage mode* — the same class as whole-page loss, which
fountain-v2 already handles with a deterministic quota tier. This design
gives plane loss the same treatment.

§8.3 excluded exactly this ("bit striping, different K values, different
q values, and pooled ESI numbering are not part of the format") as
"deliberately simple". That recorded ruling is superseded FOR THE -v1
ROWS by this design; `-v0` keeps its recorded semantics.

## 2. The design

Let T = tiles_per_page, n = n_streams (3), S = per-stream symbol bits
(`common_symbol_bits`; equal across streams by construction),
S_agg = n·S.

### 2.1 One pooled fountain

- **Symbol index**: `esi = counter·n + stream_idx`, stream order =
  `spec.stream_ids` (C, M, Y). Page-local symbol `u = local_tile·n + s`;
  symbols per page = n·T. `esi // (n·T) == counter // T` (pages align).
- **K**: `k_meta = source_symbol_count(len, S_agg)` — numerically
  identical to today's common per-stream K — and `k_total = n·k_meta`.
  The padded envelope is `k_meta·S_agg` bits (byte-identical padding to
  -v0), sliced **row-major** into `k_total` rows of S bits (replacing the
  stream-major thirds). Blocks own contiguous source rows exactly as in
  fountain-v2.
- **Metadata word unchanged** (`[version:1][K:18][reserved:5]`, version
  0): the K field carries `k_meta` (< 2¹⁸ always); pooled semantics are
  row-scoped (`k_total = n·K_field`). Canonical-K close gate: recompute
  `k_meta` from the recovered length; require equality and zero padding —
  the same shape as today.
- **Blocks**: `B = ceil(k_total/16384)`, balanced contiguous split — the
  frozen rule, applied to `k_total`.

### 2.2 Stream-exact assignment (the deterministic plane tier)

Generalizing the frozen fountain-v2 page assignment; **n = 1 must
reproduce it bit-exactly** (that identity is the format-fork guard):

- per (page p, stream s), block b receives quota
  `quota_b(p,s) = T//B + (1 if (b − (p·n + s)) mod B < T mod B else 0)`
  — the remainder rotates over the flattened (page, stream) index;
  n=1 ⇒ the frozen `(b − p) mod B`;
- shuffle: `keys64(seed, DOMAIN_BLOCK_ASSIGN, 0, page, u, 0)` with
  `u = local_tile·n + s`, argsort **within each stream's T keys**;
  n=1 ⇒ the frozen draw (u = local tile index);
- `row_of`: within (page, stream, block), ascending local tile index
  receives consecutive in-block rows starting at the block's cumulative
  quota over all earlier (page, stream) pairs, ascending (p, s);
- repair coefficients ride `DOMAIN_FOUNTAIN_ROW` exactly like K.

Domains 7/8 are REUSED with amended wording ("u = page-local symbol
index; equals the local tile index for single-stream rows"); no new
domain numbers; no collision (new row seeds). `-v0`'s domains 14/15 are
untouched.

Result: any single plane's death removes **exactly its quota — one
n-th of every block, deterministically**; spatially local damage remains
hypergeometrically white across blocks as before; whole-page loss removes
proportional amounts of every block as before. **[verified — two scope
notes]**: the pooled tier-2 inequality (L·n·(T//B)) is the stream-exact
STRENGTHENING of the frozen bound, not the naive nT substitution (which
would be weaker: L·floor(nT/B)); and rotation balance is a per-block
totals property — when n divides B the extras concentrate on aligned
(page, stream) pairs, which is harmless to every tier (each carries the
T//B floor) but is not a per-stream fairness claim.

### 2.3 Capacity promise — three tiers, the third dial-conditional

With r = rank_reserve_for(B), L = ceil(q·P), pooled rows enforce tiers
1 and 2 always and tier 3 at any dial that can carry it (§0 ruling 5):

1. global fragments: `k_total + B·r ≤ floor(q·P·T·n)`
2. page tier: `ceil(k_total/B) + r ≤ L · n·(T//B)`
3. **plane tier (new)** — all pages present, any ONE dead plane:
   `ceil(k_total/B) + r ≤ P · (n−1)·(T//B)`

(3) binds at q ≲ (n−1)/n ≈ 0.66 — **[verified 2026-08-13]** the exact
threshold is q > (n−1)/n · β with β = B(T//B)/T (≥ 1−(B−1)/T), so
4-decimal dials down to ~0.662 can shave a few symbols on real
geometries; 2-decimal dials are safe to 0.66. At or below that ceiling
the planner sizes with tier 3 in force and REPORTS the tier
`guaranteed`; above it the tier is dropped from sizing, the volume
fills to the true dial, and every report (plan, manifest
`pooled_fountain.plane_tier`, `capacity`, `generate`) says
`not-at-this-dial (needs q ≤ 2/3)`. Which side of the ceiling applies
is **[verified] POLICY, not a consequence of the predicates**: tier 3's
budget grows with P, so a plan loop enforcing it above the ceiling
would "meet" any dial only as a silent ~⅔-fill volume — enforcement
there buys pages, not the promise. P1's predicate does not decide;
`enforce_plane_tier` is the planner's explicit rule (P3) and is pinned
as such.

The combined page+plane tier (retain only ceil(qP) pages AND lose a
plane) is deliberately NOT enforced. **[verified — stated plainly]**: as
a self-consistent dial cap it would collapse toward q = 4/(3P) (0.22 at
P=6, 0.09 at P=15), so planned pooled volumes VIOLATE the combined
guarantee at essentially every ordinary multi-page dial; the reported
margin is negative there, not comfortable. The plane promise is
**all-pages-present only**, and the fragments+dead-plane combination has
no tier at all — the probabilistic fragment tier simply loses one plane's
worth of budget. Recorded, not chosen.

Reserve parity **[verified 2026-08-13 — the original "no capacity or
compute regression anywhere" was WRONG in corners; corrected]**:
`B_pooled = ceil(n·k_meta/16384) ∈ {n·B_v0−2, n·B_v0−1, n·B_v0}`, so
"same solve count, same block sizes" holds only when the ceilings align
(~1/3 of k values). Measured consequences: total RESERVE is pooled ≤ -v0
always (favorable, e.g. k_meta=16385: 72 vs 114 symbols); CAPACITY has
corner deficits up to ~45 symbols ≈ 0.1% at floor-states of B_pooled —
including q=0.5 on the real 1872-tile c2 geometry — never in pooling's
favor beyond the reserve saving; COMPUTE: every k_meta ≤ 5461 pools into
ONE solve of 3·k_meta vs three solves of k_meta, up to ~9× more GE work,
still inside the recorded ~1-minute knee at the 16384 bound — and every
physically closed CMY8 volume to date (e032's 718 KB is k_meta ≈ 918)
sits in exactly that regime. The gain is where symbols land; the price
is these corners, pinned by P1's reserve-parity test with documented
numbers.

### 2.4 Per-stream metadata equations

The tile's three stream codewords stop carrying the SAME equation
(consistency copies, no rank) and carry **distinct equations**: for
(counter c, stream s), the coefficient row is LFSR state
`c·n + s` (table extended to n·2¹⁸ states, ~3 MiB, ≪ the 2²⁴−1 period).
Every 24 consecutive (c,s) indices are consecutive LFSR states ⇒ rank 24
— the frozen property carries verbatim (s₀ = 1 ≠ 0, companion map
invertible). K and CMY7 rows have n = 1 ⇒ index = c, **bit-identical**
(note: CMY7's fountain rides domains 14/15 at aux 0 — "bit-identical"
means its path is untouched, not that it exercises the generalized n=1
path; only K rows do). The 48-distinct-equation trust floor is
unchanged and now reachable from ~16 pooled tiles — **[verified] in the
dead-plane scenario itself the floor is ~24 tiles**, because puncturing
every third index breaks the consecutive-rank guarantee (the P2 pin
carries a dead-plane variant). Inconsistency detection survives through
the overdetermined GF(2) solve (algebraic inconsistency stays
integrity-fatal).

### 2.5 What does not change

p120 furniture and dust, BCH words/counters/placement, detection and
registration, per-(tile, stream) LDPC certification and certificates,
evidence/done-geometry, slot permutation, CMY7 (one joint stream), all K
rows, everything `-v0`. The pooling is entirely an outer-code mapping:
streams remain wholly independent at and below LDPC — which is also the
cleaner abstraction the metadata bundling completes.

## 3. Why this shape (recorded rationale)

- **Plane loss joins page loss as a deterministic tier** because it is a
  measured correlated mode, and the house philosophy is that known
  correlated modes get quota guarantees, not hypergeometric luck.
- **Pooling is free**: same GE work, same reserve, same capacity at equal
  promises; the per-stream design's only unique product was per-stream
  close accounting, which was never user-meaningful (reassembly needs
  all bytes regardless).
- **Simpler than -v0 where it counts**: one VolumeCode, one pack, one
  close decoder; the "deliberately simple" objection inverts once the
  K-code path is reused verbatim (n_streams=1 identity).
- **Fragment metadata floor** drops ~3× via the bundled equation change
  at zero printed cost — directly serving the smallest-recoverable-
  fragment mission.

## 4. Costs and limits (recorded)

- The plane-tier promise holds only up to the q ceiling (~0.66) on
  pooled rows; higher dials are planned honestly at the true fill with
  the tier reported absent, never silently degraded (§0 ruling 5,
  2026-08-14). A pooled row that promised the plane tier at every dial
  would be a new ruling.
- Per-stream fountain close accounting disappears for -v1 (per-stream
  certificate counts remain as diagnostics).
- `-v0` sheets (e030/e032) stay on `-v0` forever; both paths coexist,
  dispatched by row.
- Partially dead planes: the deterministic tier covers total plane loss;
  a *weak* plane consumes the ordinary per-block margins like any other
  loss (now shared across the pool rather than concentrated in one
  stream — strictly better than -v0 at every severity).
- Paper qualification: none of this changes F14 — the rows are
  catalog-only provisional until physical qualification; the dead-plane
  gate lands in simulation this session.
- **RULED 2026-08-14 (user): the version field STAYS 0.** Rationale, in
  the user's words: "if you can read it, you are already doing the right
  thing, and the content of the metadata word has not changed" — the
  word is only readable through row-specific seeds and equation indices,
  so row identity is necessarily established before the K field could be
  interpreted; a version bit would signal something the reader must
  already know. The word's layout and the K field's VALUE (k_meta) are
  unchanged; only row-scoped consumer arithmetic differs. §7.2's
  version-field precedent is thereby scoped to swaps a reader could
  otherwise misread — pooling is not one. BOOTSTRAP consequence: no new
  preface fact — the row id the R3 preface already must carry (seeds and
  geometry were never re-derivable) determines pooled semantics; the
  version bit stays in reserve for a true word-layout change.

## 6. Successor — the width-heterogeneous pool (RULED + BUILT 2026-09-04)

The one constraint this pool imposes on the format lattice — one symbol
width per pool, so gen-v1 cmy8 triplets must share `k_bits`
(FORMAT-SPACE §5, found during the format-space build) — has a design
that lifts it without touching anything above the fountain:
docs/CMY8-COLUMN-GROUPS.md. The pool is GF(2)-column-separable; a mixed
triplet carries the one symbol width as Z column groups, the lighter
plane carrying fewer groups per tile in keystream-ordered rotation.
§2.1–2.4 here are unchanged for uniform triplets (n_p = Z is
bit-identical — the same fork-guard shape n = 1 was for this document);
the tiers of §2.3 become weighted, the reserve grows to B·Z solves, the
dead-Y ceiling rises and the any-one-plane ceiling falls. Ruled (seven
rulings, §9 there) and built on branch `cmy8-column-groups` for src/holo
generation + the holo3 receiver, sim-qualified; the v1 receiver and
holo2 untouched; nothing printed. Holo2 was retired 2026-09-05 without
ever taking this up; see CMY8-COLUMN-GROUPS.md §6/§9 for the record.

## 7. Second customer — the cmy family at n = 2 (BUILT 2026-10-11, not printed)

The cmy family (docs/CMY-DESIGN.md v0.3; FORMAT-SPACE §19; HOLO-DESIGN
§13.38; branch `cmy-generator`, commits 128ed3cb and 6926f6ef) reuses
this pool unchanged with n_streams = 2: its two streams are the cell's
label bits `hi` and `lo`, not planes, so esi = counter·2 + s (s = 0 hi,
1 lo) on domains 7/8 at aux 0, stream-exact per-(block, page, stream)
quotas, k_total = 2·k_meta with k_meta in the metadata K field, and the
metadata equation at LFSR index counter·2 + s (§2.4). Decimation by 2
keeps the degree-24 LFSR primitive, so 24 consecutive same-parity
indices reach rank 24: recovery at 12 healthy tiles or 24 with one
stream dead, trust (48 distinct equations) at 24 or 48 — pinned in
tests/holo/test_pooled_format.py. Blocks and the reserve count the pool
(B = ceil(2·k_meta / 16384); reserve 16 / 17 / 17 at k_meta 8,192 /
8,193 / 10,000 on a uniform pair, tests/holo/test_cmy_emission.py). The
third tier of §2.3 is a dead-STREAM tier for cmy and is reported so: a
dead Y loses `lo`, a dead M loses `hi`, a dead C loses both. Uneven
pairs pool through the column-group successor (§6). `fountain_aux` is
None on both streams; domains 14/15 are not used. Nothing here changes
for cmy8; F14 holds for cmy too — in no catalog row, PROVISIONAL,
nothing printed.
