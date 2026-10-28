# Full-domain cold-search gate rerun + 0.176 rival diagnosis

Mission: rerun the complete-domain measurement recorded in
docs/RECEIVE-DESIGN.md §12.1 item 2 on current code and diagnose the 0.176
rival. **Measurement only** — no gate, bar, floor, or budget was changed;
every option below is analysis, not implementation.

- Code under test: `main` @ `e2dfc80` (post-FFT-hoist, post-v0.23 frontier
  scheduler). Python 3.14.6, numpy 2.5.1, scipy 1.18.0, macOS (darwin),
  12 cores / 64 GiB.
- Harness: `bench_full_domain_rival.py` (worktree root, standalone bench,
  not pytest). `PYTHONPATH=src env/bin/python bench_full_domain_rival.py
  --mode {historical|survey} --pages 312`.

## 1. The historical record

The measurement lived in the excised qualification harness
`src/holo/receive/qualification/full_cold_profile.py` (added at `2079676`
"holo track 3: rebuild production receiver", removed by kiss cleanup
`e3026f1`; recoverable at `e3026f1^`). Its fixture:

- row `c3-r0550@2240x1536` via `make_spec("c3-r0550", "default")`
  (2240x1536 cells, 35x24 = 840 tiles/page, `max_pages` = 312,
  `n_filler` = 0 — the filler-free K geometry, 100 word sites / 4096-cell
  tile);
- target page = `max_pages // 2` = 156, patch = the 200x200-cell block of
  `V1ReferenceField.page(156).values` at cell origin (640, 512)
  (tile-aligned: 640 = 10·64, 512 = 8·64), mask all ones;
- synthetic deterministic evidence amplitude
  `0.55 + ((17y + 31x) % 29)/37` (the excised `_e022_cold_hoist._patch`);
- `correlate_patch` under `PROVISIONAL_V1_PLACEMENT_POLICY` cold budget
  (`max_hypotheses` = 5,281,117,920, `min_support` = 55/parity, historical
  E022 gate: search < 0.20, rival decoy > 0.20, gap >= 0.08,
  validation < 0.24).

It was an ideal **cell-domain reference patch**, not a rendered raster.
The pre-hoist run found the exact winner and recorded rival mismatch
0.176 (`rival_gap_failed`); the note survives in RECEIVE-DESIGN §12.1(2),
REASONING-LOG ("Honest qualification status"), HOLO-DESIGN,
`receive/placement/defaults.py::V1_PRODUCTION_QUALIFICATION_NOTES`, and
`.claude/memories/holo-track3-receiver.md`.

## 2. Post-hoist rerun, historical fixture (the record rerun)

`--mode historical --pages 312` (two runs, numbers bit-stable):

| quantity | value |
|---|---|
| hypotheses (complete domain) | 5,281,117,920 (== budget, not truncated) |
| exact true winner found | YES — page 156, origin (640,512), rot 0 |
| winner search / validation mismatch | 0.0000 / 0.0000 (0/439, 0/541 errors) |
| winner soft z | 20.248, `passes=True` |
| selected rival | page **283**, origin (128,1024), rot 0 |
| rival search mismatch | **0.1760** (78/439 hard = 0.1777) |
| rival validation mismatch | 0.4034 (219/541) |
| rival soft z | 13.120 |
| gate outcome | `rival_gap_failed` (0.1760 <= 0.20 decoy bar; gap 0.1760 >= 0.08 is fine) |
| wall (single `correlate_patch`) | 47.9 s / 47.2 s (two runs) |
| peak RSS (`ru_maxrss`) | 9,436 MiB (confirmed by `/usr/bin/time -l`: 9,893,855,232 B) |

**The 0.176 reproduces exactly on current post-hoist code** (0.1760).
The pre-hoist number was therefore not an artifact of the old convolution
path; the hoist is result-exact on the full domain too, as its three-page
fixtures claimed. Runner-up #1 is page 179, origin (1024,256), rot 0 at
0.1847 — also under the bar; #2 onward sit at 0.2146+.

Staged control (`--pages 32`, target 16, floor 49/parity): exact winner,
rival 0.2390 → **accepted**. The refusal emerges only as the domain grows
from 32 to 312 pages.

## 3. Production-path variant (`place_survey`, ideal render)

`--mode survey --pages 312`: ideal 600-dpi render of page 156 (real
`compose_page_cells` pilot field; deterministic seeded stand-in fountain
symbols — placement scores only pilot sites), 128-cell fragment cut at
cell (640,512), pasted on a 16-cell paper-margin canvas exactly as
`tests/holo/test_placement_null_battery.py` builds one; support claims the
printed fragment only, never the margin; `place_survey` with
`word_budget=None` (cold forced), pages 0..311.

| quantity | value |
|---|---|
| sampled window | origin (640,513), ~129 cells, support 158/212 per parity |
| exact true winner found | YES — page 156, origin (640,513), rot 0, search/validation 0.0000/0.0000, `passes=True` |
| selected rival | page **51**, origin (832,513), rot 0 — delta (+192, 0) cells = exactly (+3, 0) tiles |
| rival search mismatch | **0.1415** weighted (32/158 hard = 0.2025) |
| rival validation mismatch | 0.4235 |
| gate outcome | `rival_gap_failed`; then all four ~70-cell subdivision children die `insufficient_support`; **0 placements, 5 unresolved** |
| wall (whole `place_survey`) | 152.6 s (1 parent + 4 child full-domain sweeps) |
| peak RSS | 8,130 MiB |

Two supplementary measured facts:

- At the full-domain support floor (55/parity from e026 identifiability on
  H = 5.28e9), the ~70-cell subdivision children of this row (site density
  100/4096) have no eligible position anywhere — they are dead on arrival,
  yet each still paid a full ~29 s / 312-page FFT sweep before reporting
  `insufficient_support` (`correlate_patch` has no early-out when every
  orientation's eligibility map is empty; pre-existing behavior, noted as
  measurement only).
- The staged 32-page survey run is **accepted** (rival 0.2019), confirming
  the harness and the domain-scaling of the refusal.

## 4. Rival diagnosis — why 0.176 when d=27 "predicts" >= 0.27

The selected rival is **not** an overhang/clipped candidate, not a
low-support candidate, and not a same-page tile alias. It is a
**cross-page, tile-lattice-aligned, full-overlap alias**: delta from truth
(-512, +512) cells = (-8, +8) tiles, page 283 vs 156, full 200x200 overlap,
identical support 439/541, site-pattern alignment 1.000 (every selected
site reads a fragment pilot cell).

Mechanism, verified quantitatively by the bench:

1. **The address-word map is affine over GF(2) in the counter.** Verified:
   `word(c1) XOR word(c2) == word(c1 XOR c2) XOR word(0)` exactly — the
   per-counter scramble cancels in any pairwise XOR.
2. **The counter XOR is constant across the whole patch.** Truth counters
   span 131,288..131,363 (span 75, low 13 bits only). The rival's additive
   counter delta is 106,496 = 13·8192 (bits 13,15,16 only), so no carry
   crosses the span: every one of the 9 full tile pairs has the same
   counter XOR 0b011010000000000000, hence the **same difference codeword
   E** (measured deviation 0 in all 9 pairs).
3. **|E| = 31** — the code's spectrum row 31:119 (min distance 27 holds:
   measured full-word distance per pair is 31/100 in every full tile,
   overall hard mismatch 297/980 = 0.303 >= 0.27; the d=27 argument is not
   violated on the population it binds).
4. **The parity split of one codeword can be arbitrarily lopsided.** The
   100 within-tile site positions fall in fixed page-parity classes (tile
   pitch 64 is even): 45 search-class, 55 validation-class positions. E has
   only **8 of its 31 set bits in the search class**: deterministic search
   mismatch 8/45 = 0.1778 replicated in every full tile → measured hard
   78/439 = 0.1777, weighted 0.1760. Validation class carries 23/55 =
   0.418 → measured 0.4034.
5. **Extreme-value selection over the alias family finds the lopsided
   codewords.** The contained rot-0 lattice-aligned family has 209,664
   members at 312 pages; exhaustive scan of single-pair search-class XOR
   weights over that family bottoms out at **7/45 = 0.156** (page 175,
   tile (27,13) pairing). The bar sits at 0.20; the deterministic floor of
   this statistic on the complete domain is ~0.16–0.18. At 32 pages the
   family is ~10x smaller and the minimum observed was 0.239 — above the
   bar, which is why the refusal only appears at full domain.
6. The weighted statistic can dip **below** the hard-count floor: the
   survey-mode rival's hard search rate is 0.2025 but its weighted
   mismatch is 0.1415 (blur-induced amplitude variation is exploited by
   the argmax). Any future derived bar must model the weights, not just
   Hamming distance.

So: the d=27 argument holds for full 100-site words; the search statistic
sees only the frozen 45-position parity subclass, where the effective
minimum "distance" is `min over realizable constant-XOR deltas of the
search-class weight of E` — measured 8 (historical fragment), bounded
below by 7 in the single-pair family. The inherited 0.20 decoy bar was
qualified on paperholo E022-v2's single-sheet domain (~784 hypotheses,
no cross-page linear-alias family); on the complete 312-page domain the
alias family makes a sub-0.20 rival **certain**, not unlucky — while the
true winner remains uniquely clean (search AND validation 0.0000, rival
validation 0.40+, hard separation 297/980 vs 0/980).

The refusal is thus the bar doing exactly what it was frozen to do, on a
domain it was never qualified for; the yield loss is structural for
tile-aligned clean C3 fragments at full domain.

## 5. Options for the gate (ANALYSIS ONLY — nothing implemented)

1. **Domain-aware / code-derived decoy bar.** The alias family and its
   parity-restricted weights are computable properties of the address code
   and the declared page domain (min search-class weight of E over
   realizable patch-constant deltas; here 8/45, single-pair floor 7/45).
   A decoy bar placed below that floor (with the same gap rule) would have
   accepted both runs. Cost: the bar becomes format/domain-dependent and
   needs a fresh false-accept qualification; the weighted dip below the
   hard floor (0.1415 measured) means the derivation must include weight
   distributions.
2. **Support-conditional decoy bar.** Not supported by this measurement as
   the primary fix: the measured rivals have *full* support (439/541),
   identical to the winner — support conditioning alone would not have
   changed either outcome. It remains relevant for the separate
   low-support overhang tail (not the mechanism here).
3. **Validation-parity-aware rival rule.** The rival's validation mismatch
   (0.4034 / 0.4235) separates decisively from the winner's (0.0000), and
   `memo.candidate` already computes it. A rule refusing only rivals
   ambiguous in *both* parities (or gating on the winner-rival validation
   gap) would have accepted both runs with numbers already in hand. Risk:
   validation is the held-out winner-admission parity; consuming it in the
   rival rule spends held-out evidence and needs a disjointness argument
   plus requalification.
4. **Whole-word rival scoring for the decoy comparison only.** Score the
   rival over both parity classes (keep winner admission unchanged): the
   aliases then sit at their full-word distance (0.303 / 0.35 measured;
   >= 0.27 for pure aliases by d=27) and clear the existing 0.20 bar.
   Semantically the smallest change that restores the d=27 argument the
   bar's qualification implicitly leaned on, but it alters the frozen
   decision rule and therefore requires amendment + requalification.
5. **Coset-alias recognition (structural de-aliasing).** Lattice-aligned
   constant-XOR rivals are enumerable given the code; a rival whose
   identity delta lies in that family with mismatch consistent with its
   codeword weight is an address-code coset image of the winner, not
   evidence of placement ambiguity. Deepest conceptually, most new
   machinery.
6. **Status quo + Lane W.** Production compositions run with the word
   budget enabled; pure cold at full domain is the qualification rung and
   the v0.23 frontier scheduler already defers cold. Keeping the refusal
   costs full-domain cold-only yield (this measurement: 0 placements from
   a perfect 128-cell fragment) but changes nothing frozen.

## 6. Resource record (post-hoist, this machine)

- Historical fixture, one full-domain `correlate_patch`: 47–48 s wall,
  peak RSS 9.4 GiB. RSS is dominated by the invocation-local per-page
  `rfftn` transform cache (~24.9 MiB complex64 x 312 ≈ 7.6 GiB) plus 312
  cached reference pages (~1.1 GiB).
- `place_survey` cold-only on a 128-cell fragment: 152.6 s, 8.1 GiB —
  1 productive sweep + 4 structurally-empty child sweeps (see §3).
- Determinism: two full historical runs produced identical scores and
  identities.

## 7. Reproduction

```
ln -s env ./env   # if needed
PYTHONPATH=src env/bin/python bench_full_domain_rival.py --mode historical --pages 312 --top 16
PYTHONPATH=src env/bin/python bench_full_domain_rival.py --mode survey --pages 312
PYTHONPATH=src env/bin/python bench_full_domain_rival.py --mode historical --pages 32   # staged control
```

---

## ADOPTED (2026-07-31, RECEIVE-DESIGN v0.30 — user ruling)

The whole-word rival option was adopted: the decoy bar and winner gap now
evaluate whole-word mismatches, the decoy bar binding the minimum over the
complete historical rival set. Verification on this document's harness:
the complete 312-page domain ACCEPTS the exact winner (reason `accepted`,
winner search/validation 0.0000/0.0000; the former 0.176 rival measures
0.2980 whole-word, runner-up #2 0.3071 — both clear the unchanged 0.20
bar), 50.4 s / 9.0 GiB. The small-support end recovers too: the 44-degree
128-cell scrap (previously refused at rivals 0.147-0.177) accepts at the
true map, pose RMS 0.081 cells (`tests/holo/test_placement_null_battery_extended.py::
test_rot44_small_scrap_recovers_under_wholeword_rival_gate`).
