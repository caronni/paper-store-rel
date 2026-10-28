# FOUNTAIN-DESIGN — Layer 4, the outer code (M3, multi-page)

**v0.1, 2026-07-08.** Companion to DESIGN.md §7 (normative: rateless outer
code, geometric ESI, no headers; R2: any area fraction ≥ f recovers all,
payload ≤ f × capacity) and FEC-DESIGN (Layer 3, whose CRC-certified tiles
are this layer's symbols). Implementation src/paperholo/fountain.py;
measurement = experiment 015 (f-sweep). MEASURED/ESTIMATE labels as usual.

## The one-page core

Layer 4 makes the archive holographic in the only sense the trilemma left
available: **any sufficient subset of certified tiles, from any pages or
fragments in any order, reconstructs the entire volume.**

1. **Symbol = one interior tile's payload slice.** S = the minimum
   interior-tile user capacity at the volume's LDPC rate (a few bits below
   the typical cap; the difference is zero-padded inside the tile CRC).
   Edge/partial tiles carry no symbol (fountain-inert, ~2.3% of capacity on
   the c3 page — the v1 simplicity tax).
2. **Geometric ESI, zero headers.** Global interior-tile index t (page,
   tile-raster order) → block b = t mod n_blocks, in-block index
   i = t ÷ n_blocks. Round-robin interleave means any spatial region hits
   every block near-uniformly — that is what converts "any area fraction"
   into "every block gets its share of symbols". Identity comes entirely
   from the pilot-decoded address; nothing is written in-band.

   **CORRECTION (2026-07-19, external review of holo): the
   "any spatial region hits every block near-uniformly" claim is FALSE
   for multi-block volumes** — `b = t mod n_blocks` is periodic and
   aliases against the page raster, so an exact-q spatial crop can starve
   half the blocks (measured: a half-page column crop at q=0.5 starved
   16/32 blocks). It never bit here because every PRINTED v3 volume was
   single-block (K ≤ 4096). holo format v1 replaces this with per-page
   exact block quotas + a keystream shuffle (fountain-v2, HOLO-DESIGN
   §7.2); this doc describes the paperholo/layout_version-3 fountain and
   is retained as the single-block record.
3. **Systematic dense random-linear fountain over GF(2)** (fountain-v1 —
   a DECLARED stand-in for DESIGN §7's "RaptorQ": same function class,
   provable instead of standardized; RFC 6330 stays a registry-entry swap,
   payload-interpretation format only). In-block symbols i < K_b are the
   source data itself (zero-damage volumes read directly, no decode);
   repair symbols are seeded dense GF(2) combinations
   (rng label `fountain-v1/row/<block>/<i>`), unbounded i ⇒ **rateless**:
   more repair pages can be printed later against the same source, no
   re-encode. Source-first layout puts data on early pages, repair on late
   pages.
4. **Decode = bit-packed Gaussian elimination per block** on certified
   symbols only (F9 upstream owns cleanliness — the fountain layer assumes
   error-free symbols by architecture; a corrupted-but-certified symbol is
   a 2⁻³² event). Overhead is provable: P(block fails | K+δ random
   symbols) ≈ 2^−δ; expected excess ≈ 1.6 symbols/block. Per-block
   diagnostics (received/rank/needed) make partial recovery honest.
5. **Volume descriptor** (n_pages, data length, rate id, geometry) is
   public knowledge like the seed — it rides the format registry/bootstrap
   sheet (R5). In-band replicated metadata (e.g. on the fountain-inert
   edge tiles) is declared future work.

R2 arithmetic this makes literal: a volume with K_total source symbols and
N total symbols recovers from any ≈ K_total(1+ε) certified tiles wherever
they sit ⇒ the design fraction f ≈ K/N ÷ (tile certification rate inside
fragments). Experiment 015 measures the achieved f against that bound.

## Format constants (fountain-v1)

- S = min interior-tile user capacity over the volume (deterministic).
- ESI: t over interior tiles in (page, tile-raster) order; b = t mod B,
  i = t ÷ B; B = ceil(K_total / 4096); K_b balanced.
- Repair row bits: rng(seed, b"fountain-v1/row/" + block_le32 + i_le32),
  dense Bernoulli(1/2) over K_b.
- Golden-anchored (generator-row hashes for a fixed spec) in tests.
- Page budget bound: the pilot counter caps pages per volume at
  (2¹⁸−1) ÷ tiles_per_page (283 at the c3 geometry, 128 at c2).

## What experiment 015 measures (sim, zero print)

1. Multi-page blind volume round-trip (first full-stack recovery:
   modulation → pilots → LDPC → fountain).
2. **The R2 f-sweep**: random fragment windows totaling area fraction f
   across a sim volume → certified tiles → volume decode success vs f;
   measured f-threshold vs the K/N ÷ certification-rate bound, incl. the
   lost-whole-page case.
3. Overhead at volume scale (excess certified tiles needed beyond K).
4. Rateless growth check: decode from a volume printed as data-pages-now,
   repair-pages-later (two encode invocations, same source).

## MEASURED (015.0, 2026-07-08 — full numbers experiments/015-volume-fsweep.md)

8-page volume, K/N = 0.551, r0550, 25.4 mm blind fragments: **exact
recovery at f\* ≈ 0.70–0.78 measured area fraction** (sharp transition:
0/25 at 0.67, 25/25 at 0.78); the entire gap to the ideal K/N bound is the
fragment-boundary symbol yield (79.6% at this fragment size — predicted
threshold 0.69, observed there). Lost-whole-pages: exact from 6/8.
Fountain overhead ~0 (GE flips where symbols cross K; codec curve
29.5/77.5/97.5/100% at K/+2/+5/+16 matches theory). Wrong certifications:
0 across the run. First full-stack blind recovery (modulation → pilots →
LDPC → fountain) in tests: 2-page volume, one page rotated, byte-exact.
Design consequence: f\* − K/N is a FRAGMENT-SIZE effect, not a code cost —
larger pieces/whole sheets sit at the bound; K/N is the archive's
redundancy dial.

## Open questions (honest list)

1. Fountain-inert edge tiles (~2.3%) — reclaim via sub-symbol packing or
   in-band volume metadata, later.
2. Fragment-rate coupling: fragment tiles certify best at r0550 (013/F4)
   while density wants r0700 — mixed-rate volumes (robust rungs on repair
   pages?) are unexplored.
3. GE at very large volumes: B grows with K_total, per-block K ≤ 4096 keeps
   decode seconds-class; a peeling/inactivation decoder is the upgrade path
   if volumes reach many thousands of blocks.
4. True RFC 6330 RaptorQ as a registry entry — if/when a vetted pure-python
   implementation is worth the maintenance.
