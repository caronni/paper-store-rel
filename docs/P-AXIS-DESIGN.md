# Furniture density axis (pXXX) — v0.3, re-based on main @ a63ef788 (2026-09-16)

MERGED to main at b635eb23 on 2026-09-20 (Germano's order); branch and
worktree dropped; not pushed, not printed, nothing promoted.

STATUS (narrow, 2026-09-16): what LANDED on branch `p-axis` is the §1
patch (two function bodies), its pins, one sim volume per family at
p300, and SIX docs — FORMAT-SPACE §5 + the new §18 (the amendment of
record), HOLO-DESIGN §4.2 + ledger §13.37, CMY8-COLUMN-GROUPS §11,
src/holo/receiver/docs/API.md, PRINTED-FORMAT §6/§12.1 with pointers in
COLOR-INTEGRATION-DESIGN and COLOR-IMPLEMENTATION-PLAYBOOK, and
REASONING-LOG. Merge is Germano's. NOT landed and not decided by the
landing: §7's remaining obligations (itemised there), the value case of
§3, the workplan of §5, and every ruling of §6 but R1, R4, R13 and R14.
Nothing is promoted, and no `p` but 120 has been printed or qualified
on paper.

RE-BASE BANNER. v0.2 was written against 2d56e5a. Since then (185
commits): the v1 receiver (src/holo/receive) and holo2 were DELETED
(284ae3e, a805888); holo3 MOVED to src/holo/receiver (package
holo.receiver, 2099338) and still carries bit-exact copies of the
format law beside holo.core/holo.format — their DEDUPE is the declared
next line (RECEIVER-MOVE-PLAN §6); PAGE-FIELD replaced plane-fields
(1d8cd832; unconditional for colour; its furniture template already
reads dust per plane); column groups are on main; the analyzer exists;
e036/e037/e038 landed (sheets H and I at 100%, I from ONE 2400
capture; the M281's whole weak-Y colour record INVALIDATED by ruling
2026-09-14 and the M281 shown to re-screen colour with fresh toner);
the venv is env/ (ruled 2026-09-16). v0.3 = v0.2 put through a
five-lens adversarial currency review (10 skeptic checks, 9
confirmed) and the author's own runtime-composed verification of the
patch. Every `holo3/…` path is now `src/holo/receiver/…`. The two
source reviews (scratch/sheetI-20260831/review-cmy8-p-axis-plan{,-rev3}.md)
(2026-10-12: those reviews and the two sheet-I notes beside them are committed
under docs/archive/sheet-i-notes-2026-08-31/; the scratch copies are gone.)
stand unchanged.

## 0. Verdict

**The minimal healthy patch is two function bodies, ~10 lines, in
two packages, with zero edits to either copy of pilots.py** — and it
is verified on today's tree: byte-identical reference arrays and
writer geometry at p120 for cmy8, cmy7, K and the sheet-I fossil;
correct at p300 (30,000/30,000 sites, mask == build_site_geometry,
writer payload set == receiver payload set, 3,796 cells; the uneven
column-group triplet likewise). The mechanism half of v0.2 survives
to the byte. **The value half eroded**: the confetti scrap-floor
argument is aimed at the wrong population and probably has the
wrong SIGN; the cold-floor benefit and the faint-yellow risk are one
quantity through one function and the benefit inverts under dead Y;
no engine that can print a colour row today wants a plane-UNIFORM
rate dial (e038 asks for per-plane rungs = column groups); and the
harness behind every fragment number is lost. What survives, all
measurable without toner: the K axis (already emits and decodes,
zero code), page-field Y-anchor supply ×10 (a benefit on an OPEN
page-field item, unclaimed in v0.2), and p as the only built-in way
to reach a rate BELOW the ladder's bottom rung. **Ship the patch +
the K sim ladder + the pre-registered record, then stop and rule.**

## 1. The patch (verified 2026-09-16 by runtime composition)

**Receiver — one line**, src/holo/receiver/plugins/words.py:66, the
colour branch of `_site_cells`:
```
return (pilots.word_site_cells_yx(row.sites_seed),
        pilots.dust_site_cells_yx(row.sites_seed, row.n_dust))
```
No signature change, no `SiteGeometry` re-plumb (v0.2's version
would have broken the analyzer seam pin at
analyzer/planeview/patches.py seam 5 and measure/accel/op_bench.py:244
— both untouched by this form). Recorded fact behind the pin below:
today `ReferenceField` CONSTRUCTS over a silently wrong mask (12,000
of 30,000 sites at p300) and dies only on first page touch.

**Writer — one function**, src/holo/gen/color_compose.py:105-109,
`_color_geometry` derives locally (5 lines out, 9 in): word cells,
`dust_site_cells_yx(spec.family_seed, spec.n_dust)`, flats, an
`occupied` bool over 4096, `np.flatnonzero(~occupied)`. Both copies of
pilots.py untouched — their `color_site_cells_yx` /
`color_payload_cell_indices` then have ZERO production callers in
either tree (grep-verified); the v1 copy's `payload.size != 3976`
assertion becomes unreachable. Those two dead p120 helpers (and the
assertion) are the DEDUPE's to delete, not this patch's.

**Pins that land with it** (~15 lines, three test modules):
1. Invariant: for every registered row and one p≠120 row,
   `_site_mask(row)` equals the mask built from
   `identity.build_site_geometry(row)` — the missing did-it-bite pin
   that turns the silent-mask fact into a loud one.
2. Cross-copy at p≠120: `dust_site_cells_yx(P120_SEED, 200)` and
   `site_cell_indices(P120_SEED, 200)` agree between
   holo.receiver.format.pilots and holo.format.pilots — today NO pin
   can see a p≠120 divergence between the copies (the drift pins
   compare at P120 only, and they are slow-lane).
3. `capacity` and `generate` agree on emittability for every family ×
   lawful p (today cmy8 is the ONLY family where they disagree:
   capacity prices p300 at 41,989 B, generate exits 1).

**Fork guards already in the tree**: tests/holo/test_column_groups.py
`EMIT_GOLDENS` (ps sha per ruled row), tests/holo/test_color_format_
profiles.py `P120_SITE_GOLDENS`, tests/holo/test_color_compose.py tile
digests; plus the P120 drift pins (slow lane).

**What the patch does NOT do**: no constructor refusal on receiver
grounds (a receiver constant must not become format law; the
constructibility rules live in TWO copies, families.py and
receiver/format/identity.py:409-437, so any refusal is a two-file
policy change — R4); no guards; no change to the luma projection,
dust's chartered roles, the extras law, cmy7 (p120-locked in both
copies), or any golden.

## 2. Ordering and gates

**p-axis FIRST, dedupe SECOND** (new ruling R13): the patch touches
neither pilots.py, so it neither blocks nor is blocked by the dedupe;
after it, the dedupe of that pair is a deletion.

**Gate, on this checkout (env/bin/python; PYTHONPATH=src for
scripts)**, in order: `env/bin/pyflakes src/holo analyzer measure
util` (baseline 17 lines, 16 in src/holo/characterize + descriptor.py:40
— gate = nothing new); `env/bin/python -m pytest -q` (default suite:
tests/holo + analyzer/tests + util/tests at -n 8 — NOTE it is RED on
main for the three walk-eval pins CLAUDE.md lists as owed: either
land that re-pin first or name the three node ids as the unchanged
baseline, never inherit an ambiguous red); `env/bin/python -m pytest
tests --ignore=tests/holo -q` (paperholo); `env/bin/python -m pytest
src/holo/receiver/tests -q` after the `-n 0` warm-up of
test_h3_e2e_sims.py; **`HOLO3_RUN_SLOW_TESTS=1` — mandatory, it is the
only lane that compares the two copies of the format law and runs
the import firewall**; `HOLO3_RUN_ORACLE_SWEEPS=1`;
`HOLO_RUN_SLOW_TESTS=1` (the seven-coding real-payload gate net);
one archived p120 colour state replaying bit-identically. Branch +
worktree; merging is Germano's.

## 3. What the axis buys, re-priced against e035–e038

- **K**: emits and decodes on the unpatched tree; the whole ladder
  p∈{100,150,200,300} is lawful; measured now: placement is ~99% of K
  cpu at p300, so what a sim ladder buys is a CPU curve until the arm
  runs on fragments. K is engine-agnostic and MIC-free — the only
  print candidate this document keeps.
- **Confetti scrap floor (the v0.2 headline) — probably NEGATIVE**:
  e035's census says 86% of the 20.1% never-attempted tile-streams
  were ADDRESSED and died at the per-TILE payload-coverage attempt
  floor, which p relieves by ~2.2 pp at r0547 while raising the tiles
  needed to close by ~9.4%. The close-floor column (§4, owed) must be
  computed against e035's archived facts BEFORE any other claim, in
  R3's unit, and its sign stated.
- **Cold floor and the faint-Y wall are one quantity**: both flow
  through the luma proxy in `words.reference_page`; the ×1.6 z gain
  and ×2.5 area gain hold ONLY while dust reads at the channel error
  (healthy Y) — under dead Y the dust leg reads at 1/3 error at every
  p and the benefit INVERTS. Hence R7 (per-channel dust in that one
  function) is a PRECONDITION of any colour benefit, not an option.
  And the wall is narrower than v0.2 said: the page-field's furniture
  template already reads dust per plane; only the pose/cold luma
  reference still collapses it — a one-function A/B, not a P2 arm.
- **Calibration unit**: measured nulls on healthy sheets (receiver
  source comment; analyzer ceiling). Surviving width = scraps between
  the survey floor (9 mm² ≈ 1,255 c2 cells) and the p120 PAVA unit
  (96² = 9,216 cells). Narrow; state it as such.
- **Page-field Y-anchor supply — the one NEW, measurable, unclaimed
  benefit**: Y-inked dust per tile 12-14 (p120), 48 (p172), 96
  (p244), 132-134 (p300); the page field's Y evidence IS the dust,
  and sheet H's Y sits at 0.122 vs the 0.12 bar — an open item p
  bears on directly, measurable in sim.
- **Rate below the ladder** — the claim that got STRONGER: shortening
  by p is the only built-in way to an effective rate under the bottom
  rung without minting codes (r0550: 0.525 → 0.503 at p300). It is
  plane-UNIFORM, so it serves a uniformly-marginal page (K; a future
  engine weak in all planes) — NOT the M281, whose measured problem is
  per-plane asymmetry (M/Y under their rungs, C fine) = the column-
  group pool's design case. **Colour p-row ranks BELOW the
  column-group row for any print day.**
- **The e037 standard**: the record's one "format-axis losses"
  finding was overturned by receiver-axis work on the SAME capture.
  No rung/p promotion may be argued from rate-vs-cell-error algebra;
  the receiver residue must first be shown exhausted on the same
  capture (analyzer fixed point + resume). The +0.7 pp threshold
  claim is re-priced under that standard (and is i.i.d.-only).
- **Column groups**: Z is NON-MONOTONE in p; p244 collapses
  r0700x0700x0547 from 17 groups to 4 (zero-tail waste up an order
  of magnitude). Of v0.2's three rungs only **p172** keeps the ruled
  triplets near their ruled waste; p244/p300 are dominated. p ×
  uneven-triplet works by construction under the same patch (verified
  3,796 cells); owed: one EMIT_GOLDENS row per (ruled triplet × p)
  and a Z-vs-p note in CMY8-COLUMN-GROUPS.md. R8's selection rule
  must score spare_bits_per_site beside the user-bit cost.
- **Engine**: colour p is AltaLink-only until the M281's re-screen is
  answered (PJL recon + sethalftone, owed); every M281 Y number in the
  record is invalid; the yellow-luma-weight trigger of the wall is
  STILL unmeasured anywhere.

## 4. Numbers ([tree] only; the v0.2 [harness] rows are LOST)

| row (user bits/tile/plane) | p120 → p300 | eff. rate |
|---|---|---|
| r0550 | 2088 → 1908 (−8.62%) | 0.525 → 0.503 |
| r0700 (real sheet c2@53x37, A4-4mm, q=0.5) | 2728 → 2548 (−6.60%); 997,023 → 931,210 B | 0.686 → 0.671 |
| r0850 | 3368 → 3188 (−5.34%) | 0.847 → 0.840 |

Cost p120→p300 = **56.25% of one rung step, rung-independent** (180
of 320 user bits; 65,813 of 117,000 sheet bytes); in per-cell
effective rate it is 28.0% (r0550) → 18.5% (r0700) → 9.0% (r0850).
Candidate rungs at r0550: p172 −2.49%, p244 −5.94%, p300 −8.62%.
Constructibility: cmy8 r0550 p∈[101,2206] contiguous; p100 refused.
Degeneracy is measurable only at p101–102 (a plane's dust carries
zero ink); above that the p101–119 band is a quota-charter question,
and p110 prices HIGHER than p120. Pooled furniture error e(p) =
(1/3)·n_dust/p under dead Y: 0.056 (p120), 0.081 (p132), 0.200
(p250), 0.222 (p300) — the AUDIT/GATE bars (pose.py:65 AUDIT_GOOD,
place.py:25-26 GATE_SEARCH_TRUE/GATE_RIVAL_DECOY) are violated
directly at p≥250; BER_ENVELOPE (place.py:33) is not a bar but the
assumed error inside the support-floor formula — it is FALSIFIED
above p≈132 (the floor is 2.5× too small at p300 under dead Y),
silently, toward false accept. Parity checks that survive shortening:
n−k = 1856 (r0550), 1216 (r0700), 576 (r0850). Word lattice shared
p120↔p300: 5/100 sites (no qualification inheritance). Owed to this
table: the close-floor column against e035's facts; the Z-vs-p table
per ruled triplet; the MIC ratio stated per PITCH (c2: 2.2–21.6× as
marks; at c3 the p120 figure falls BELOW the AltaLink's MIC density).
ONE UNREPLICATED OBSERVATION, recorded because it is the only surprise
the 2026-09-16 sims produced: an exploratory decode of
`c3-cmy8-r0550-p300@10x10` (12,000 B, one render, 8 workers) fired the
D1 address-word contradiction alarm ONCE — two windows of one capture
claiming page 0 tile (2,4) at rot 0 by the word route, their extents
overlapping, 1.20 cells apart in y — and quarantined nothing, the close
verifying byte-exact with 54 certificates. It did not replicate: the
shipped c2 stimulus fired none in two repeats (report `contradictions
0`), and a p120 control over the same payload and render path fired
none. D1 is diagnostic by ruling and the payload is unaffected either
way; the p-axis e2e deliberately does NOT assert
contradiction-freedom, because a first-sighting alarm under an
8-worker schedule is a race to be characterised, not a pin.

LOST (rebuild in measure/ before quoting): cold-placeable/searchable
floors, the 32²/96² calibration unit, the +0.7 pp threshold.

## 5. Workplan — collapsed

**P0 — price, refuse, pre-register (no code; 1 day).** The rate
statement WITH the close-floor column vs e035; the constant census
re-derived on the page-field tree (rate-type vs count-type, and the
count split by what it counts: word sites p-invariant, furniture
∝ p, payload ∝ 4096−p; incl. field_tiers ANCHOR_MIN_SITES /
ANCHOR_MIN_PER_CLASS, fields.py MIN_DELTA_DOTS, CERTIFIED_RADIUS_CELLS,
analyzer/calibrate.py:82); the Z-vs-p table; the NON-CLAIM paragraph
carrying the e037 standard; pre-registered envelopes.
**P0-K — the free K sim ladder (2 days, zero code, zero toner).**
**P1 — the patch (1 day; needs R1, R13, and the walk-eval baseline).**
§1 + its three pins + §2's gate. If R4 is yes, the refusal in BOTH
constructibility copies with a pin that they agree.
**P4 — STOP and rule.** Options split K vs colour: STOP / RECEIVER-ONLY
/ K ROW / COLOUR ROW (colour only after the one-function A/B).
UNSCHEDULED, each with its blocker: the per-channel dust A/B in
`words.reference_page` (blocked on R7 only — cheap); P0-M archived
metrology, AltaLink-only, reporting the dust error AFTER the page
field (blocked on the engine ruling R14 and a costed run inventory);
sim qualification (blocked on P0-M's trigger); prints (K twin only;
competes with the M281 re-measure set, the sethalftone probe, and
the unprinted column-group rows).

## 6. Rulings (recommendation in parentheses)

R1 The repair inside the format authority: src/holo/gen/color_compose.py
   `_color_geometry` (~9 lines) + src/holo/receiver/plugins/words.py
   `_site_cells` (1 line) + ~15 lines of pins; pilots.py untouched in
   both trees; gated by EMIT_GOLDENS / P120_SITE_GOLDENS / tile
   digests. (Yes.)
R2 The grain promise, in sites and mm. (Open since e026.)
R3 The exchange rate, in bytes, AFTER the close-floor column and the
   zero-capacity rivals are priced. (Not before; likely negative for
   confetti.)
R4 p101–119: refuse p≤102 on the measured mechanism, or the whole
   band on the quota charter stated as policy — two files either way.
   (≤102 on mechanism.)
R6/R7 Per-kind gate populations (a FIX) + per-channel dust in the one
   remaining function, additive, superset-proved — R7 is the
   precondition of every colour benefit. (Yes to both; R5's cap
   dissolves into R6.)
R8 A p ladder with a selection rule that scores column-group spare
   beside user-bit cost; p172 the only surviving colour candidate.
R9 Scope = src/holo/gen + src/holo/receiver; p × uneven triplets IN
   by construction, goldens owed; analyzer prose refresh only (its
   code is p-generic; seam 5 unaffected by the one-line form).
R11 K independently — now the ONLY print candidate. (Yes.)
R12 Quota-ize the large dust draw now that a rung above the floor is
   proposed, or defer explicitly.
R13 NEW: p-axis lands before the pilots dedupe. (Yes.)
R14 NEW: colour p is AltaLink-only; the trigger measurement is a
   one-engine measurement and says so. (Yes.)
R15 NEW: the red walk-eval baseline — re-pin first, or name it.
Dropped: R5 (a receiver cap in format law — never), R10 (moot for
colour after e038; re-pose on K with a stated pitch if ever needed).

## 7. Docs obligations — dispositioned 2026-09-16

LANDED with the patch:

- **FORMAT-SPACE §18** (new) — the amendment of record: mechanism, the
  NO-INHERITANCE corollary, the rate note including "below the bottom
  rung", the capacity/generate parity, the p101–119 ruling on §11.4's
  bound, the Z-vs-p table, the non-claims; **§5** points to it.
- **HOLO-DESIGN §4.2** row-relative + **ledger §13.37**; v0.25 → v0.26.
- **CMY8-COLUMN-GROUPS §11** — Z vs p, with the ruled identities
  declared p120-conditional and a golden owed per (triplet, p).
- **src/holo/receiver/docs/API.md** — the reference field is
  n_dust-generic.
- **PRINTED-FORMAT §6 + §12.1** — the generic dust law for a second
  implementer, p120 named as the printed and only qualified case; with
  one-line pointers where COLOR-INTEGRATION-DESIGN §4.2 and
  COLOR-IMPLEMENTATION-PLAYBOOK §1.3 state 20 dust as fact.
- **REASONING-LOG** — the dated entry (why two derivations, how the two
  failures differed, the rulings, and that nothing is promoted).
- **RECEIVER-MOVE-PLAN §6** — the pilots pair's dedupe is now a
  deletion; **SUITE-AUDIT §D** — an `_h3_sims*.py` edit moves the
  content cache key; **analyzer/DESIGN.md** — the three word-level
  edits R9 promised.

NOT OWED: **SCHEDULE.md** is generated from the descriptors and no
descriptor moved — regenerating it would be a no-op diff.
**CLAUDE.md's Commands block** was fixed on main at 4337b364 (the venv
ruling); the flag is stale.

STILL OWED, none of it blocking the patch and none of it done:

- **PILOTS-DESIGN** — the v4 re-derivation and the per-kind floor;
  it is the pilot-design record and still reads p120-only.
- **FORMAT-SPACE-DISPATCH** — the dispatch rows for a `p` that is not
  120.
- **DESIGN.md R3** — the conceded structure is "a hidden 2.5%-density
  site pattern" (:164) and p300 furniture is 7.3% of cells; an
  amendment is owed BEFORE a high-`p` sheet is printed.
- **BOOTSTRAP-DESIGN** — how a finder learns `p` (it is in the
  identity, but the deep-time preface does not say so).
- **PAGE-FIELD-DESIGN** — the Y-anchor supply against `p` (§3's one
  new measurable benefit; unclaimed and unmeasured).

## 8. Retired from v0.2, for the record

The v1-receive guard and "structurally p120" rationale (no v1
receiver exists); holo2 INTENDED_DIVERGENCES (no holo2); the
plane-fields sequencing clause (merged as page-field, which changed
sides — its Y evidence IS the dust); the "never written down" claim
(COLOR-DESIGN:301-303, PILOTS-DESIGN:1604-1607 wrote it); the
SiteGeometry re-plumb (collides with the analyzer seam); the "drop the
n_dust default" sentence (adds asymmetry to the pair about to be
deduped, and no production path reaches it); the M281 0.0110 citation
(invalidated epoch); every [harness] number (lost); "18.5%" as the
cost (r0700-only); "all 1856 parity checks" (r0550-only).
