# HOLO2-MAP — every holo2 mechanism that changes what a decode does, mapped into holo3

**DRAFT for Gate B.** Nothing in code has changed; no receiver was run to produce it.

**Tree.** The brief's tree is `b8471fc` ("Merge canonical-identity"). Both trees were re-read at that commit or at the two commits after it — `104494e` (the diag fold split from its readout) and `29d9a8d` (the rebuilt venv). The dryness, pricing, evidence-and-ownership, completeness and both second-lens passes state their footing as `29d9a8d` and say why it does not move their citations: neither commit touches the engine loop, any price literal, or any placement module. Where a family's footing is stated in its own words it is quoted in that family's notes below.

## How these rows were derived

Each row is one mechanism that survives the filter rule — it enters the map if it changes which work runs, in what order, or what gets certified. Three passes produced it, and all three are carried here rather than flattened:

1. **A reader** (one per family, Opus) located holo2's mechanism and holo3's counterpart by `file:line` in both trees, classified the row, stated the implementation delta, quoted both sides' numbers from `ARTEFACTS.md` and the artefacts it licenses, and gave a recommendation. The seed ledger in `seeds/holo2-behaviour-ledger.md`, the holo3 build contract and grok's tables were used **only to name candidates**; every verdict was re-derived from the current code.
2. **A refuter** (one per family, Opus, lens "not equivalent / citation stale / the artefact does not say that") checked every CARRIED-IDENTICAL, CARRIED-DIFFERENT, DIVERGED and ABSENT row and returned one of three verdicts: *upheld* (corrections at most cosmetic), *reclassified* (the classification word must change), *rejected* (a claim that drives the row's delta or its ruling is wrong and must be rewritten before Germano sees it). Its corrections are reproduced verbatim under each row's Notes and applied to the classification.
3. **A second lens** (yield) ran on every DIVERGED row and wherever reader and refuter disagreed. Its `final_classification` and its ruling text win; where it overturns the refuter, the disagreement is printed above the row rather than deleted.

**Merge rules applied mechanically here, so they can be checked.** The final classification is the second lens's where one exists, otherwise the refuter's reclassification, otherwise the reader's. A row's ruling flag is the reader's, except that (a) every DIVERGED and every ABSENT row carries a ruling by `claude-plan.md` §7, (b) `evidence-ownership-11` loses its ruling because it is no longer an absence, and (c) `pricing-19` gains one on the refuter's instruction. Evidence status is the reader's except in the six places the refuter corrected it in so many words; each of those prints its correction inline. Every other sentence in a row is a verbatim field of one of the three passes.

**Two cautions that bind the whole map, stated once here and again in the rulings draft.** First, the placement family's head-to-head evidence — five of its rows and the strongest numbers in the map — is ONE artefact: four decodes of one 1000x1000-cell crop of one HP K capture at one worker with a synthetic rotation. Its own honest-gaps section asks for a second crop and a multi-worker rerun before any of it carries a ruling. Second, `ARTEFACTS.md` was still being rewritten while the readers ran, so its line numbers drift by a few lines in both directions and by 80+ lines in at least one place; both the refuter and the second lens re-pinned the anchors they used and recommend citing section anchors rather than line numbers. Both cautions are the passes' own words, not the merge's.

## The vocabulary, one line each

- **CARRIED-IDENTICAL** — bit-exact carry, pinned by an oracle test, a golden, or a recorded bit-exact verification.
- **CARRIED-DIFFERENT** — same intent, different implementation; always with the implementation delta and an equivalence-evidence status (PINNED / MEASURED / UNPROVEN).
- **DIVERGED** — behaviour differs in a way that touches yield or core behaviour; both sides' measured record; needs a ruling.
- **ABSENT** — not in holo3; yield relevance from evidence; ruling is port now / archive for later port / accept the loss.
- **HOLO3-ONLY** — new in holo3; listed, no action (two rows here nonetheless carry a ruling their reader asked for).
- **OUT-OF-FILTER** — self-test, safeguards, journal/replay/leases, validation, diag rendering; one appendix line, never analysed.

Evidence status on a CARRIED-DIFFERENT row: **PINNED** (a test or golden holds the two sides together) / **MEASURED** (an existing artefact shows equal-or-better yield) / **UNPROVEN** (with the artefact or costed run that would settle it).

## Summary

### Rows per classification per family

| family | CARRIED-IDENTICAL | CARRIED-DIFFERENT | DIVERGED | ABSENT | HOLO3-ONLY | OUT-OF-FILTER | rows | rulings |
|---|---|---|---|---|---|---|---|---|
| placement | 7 | 11 | 10 | 3 | · | · | 31 | 15 |
| evidence-ownership | 1 | 15 | · | 2 | 1 | · | 19 | 5 |
| refinement | · | 11 | 2 | · | 2 | · | 15 | 12 |
| done-gate | · | 9 | 1 | 1 | 2 | 1 | 14 | 7 |
| close | 2 | 8 | 2 | 2 | 1 | 1 | 16 | 4 |
| dryness | · | 2 | 4 | 2 | · | · | 8 | 6 |
| pricing | 6 | 10 | 1 | 2 | 2 | · | 21 | 9 |
| completeness | 3 | 13 | 1 | 3 | · | · | 20 | 6 |
| **total** | **19** | **79** | **21** | **15** | **8** | **2** | **144** | **64** |

### The rest of the shape

- Evidence status across all 144 rows: MEASURED 52, UNPROVEN 49, PINNED 33, n/a 10.
- Yield relevance across all rows: decides-certificates 72, decides-order-only 47, integrity 17, nothing observable 8.
- Rows carrying a ruling: **64** of 144. They are written out in `RULINGS-holo2-draft.md`.
- Rows the refuter reclassified: 14. Rows the refuter rejected an argument on: 3 (`dryness-01`, `dryness-06`, `extra-15`). Rows where the second lens overturned the refuter: 1 (`placement-13`).

## Placement

31 rows; 15 carry a ruling.

**Reader's family notes.** Scope and method. Every verdict was re-derived by reading both trees at main b8471fc; the seed ledger's dial column, the holo3 build contract and grok's rows were used only to name candidates. No receiver was run. Where a seed row's citation moved or its claim did not survive re-derivation, I say so in the row's notes (placement-06 and placement-02 both correct a claim I inherited).

Three structural findings a reader should take away before the rows. (1) The single largest mechanism difference in this family is not a gate or a price, it is the CONSULT REACH: holo3's cheapest placement stage already has the reach holo2 reserves for its gated, dearer wide tier, because `anchors_of` filters by capture and region only — no level filter, no direction filter — while holo2's ring is eight same-footing neighbours plus strictly coarser donors. Rows placement-01, -02 and -17 are three faces of that one change, and the only head-to-head measurement in the record (four decodes, one crop of a real HP K sheet, two synthetic angles, identical TIFFs to both receivers) says holo3 is ahead on unresolved windows, coarse-lane failure rate, certificates and wall on every arm, with zero wrong certificates on either side and a strict superset at 0.80 deg. (2) The placement family has almost NO cross-tree bit-exactness evidence. Of holo3's four drift modules, exactly one test touches this family (`test_geometry_window_layout_constants_and_starts_match_holo2`); the pose fit, the local search, the word sweep, the cold correlation and the audit are carried but pinned only by holo3's own in-tree goldens. Every CARRIED-IDENTICAL row here rests on a line-by-line reading plus a golden, not on an oracle. (3) The one place holo3 loosened a floor rather than tightening it is the per-flavour cold support floor (placement-11), and it is lawful — the flavour's partition is declared before the sweep, not derived from current pixels — and it was qualified byte-exact on a real archived capture.

What this family has that holo2 does not: the reach above, the calibration/pose split that stops a calibration refusal from retracting an accepted address (placement-22), the dynamic page domain with per-partition floors (placement-25, -11), the reach-based done gate on placed windows (placement-20), and an actual retirement path (placement-29). What it lost: the dryness gate (placement-26), quarantine's placement consumer (placement-23), the offered-distance ordering leg (placement-03), cold's residency lease (placement-12), and holo2's refusal-word gate on subdivision (placement-06).

Seed coverage: B15 (04), B16 (05), B17 (06), B18 (07), B19 (08), B20 (09), B21 (10), B22 (11), B23 (12), B26 (13, 14), B27 (15), B28 (16), B29 (01, 03), B30 (02), B31 (03), B32 (17), B33 (18), B34 (19), B35 (20), B54 (19), B63 (22). Also covered: B02/B03 (26), B04/B09/B10/B11 (27), B13 (28), B24/B25 (23), B36 (21), B62 (30). Grok-derived rows: the straddle-audit refusal path (06), declared-vs-voted pitch (24), the default page domain (25). Mechanisms found in the code that no seed names: the terminality/retire-cause set (29), the window layout lattice (31), and the Stage-A false-accept evaluation point (14).

Out of filter, one line each: `place.subdivides()` / `SUBDIVISION_DIRECT` / `NEVER_SUBDIVIDES` in holo3 are referenced only by a test and are dead in production (noted in row 06, not a row of their own); `RETIRE_UNKNOWN` is an unreachable name the engine writes only if the retire contract is ever violated; holo2's `PlacementDomainEnvelope` (B68), `pose_audit.predict_from_anchor` (B67), `SubjectSpec`/`LabelPool` (B66) and `capture/scale_space`'s memmap arm (B69) are built-unused in holo2 with no production caller, so they change nothing on either side; holo2's cold `page_progress` heartbeat (a no-silent-stages observer callback) is absent in holo3 and touches no search state.

Gaps I could not close from the record: G-08 (no measured number on any side for the straddle-audit path or the pitch refusal), G-09 (no holo3 realized done-gating rate on a real sheet), G-12 (`WIDE_ANCHORS = 8` never bound on either side). The head-to-head that carries most of this family's evidence is ONE crop of ONE HP K capture at --workers 1 with a synthetic platen angle; its own honest-gaps section says a second crop and a multi-worker rerun are the obvious next steps if any of it is to carry a ruling.

**Refuter's family notes.** THREE MECHANISMS NO ROW COVERS, all in-filter (they decide what gets certified).

(1) THE CHAIN LOCAL SEARCH ITSELF. holo3 place.py:409-439 (`local_search`) and holo2 pose_audit.py:395-445 are line-for-line the same kernel — the 7x7 neighbourhood from NEIGHBOR_RADIUS_CELLS=3, the `(-soft_z, origin_y, origin_x)` ordering, the non-finite-soft_z insufficient_support exit, and `accepted = best.passes and residual <= CONSISTENCY_CELLS(2)`. This is the accept rule for the cheapest and highest-volume route in the family and the map has no row for it; it belongs in as CARRIED-IDENTICAL with the two constants pinned (holo3 tests/test_h3_plugins_placement.py covers the constants, not the rule). Its absence also means CONSISTENCY_CELLS has no provenance anywhere in the map.

(2) THE BLIND POSE FIT AND ITS REFUSAL. `pose.fit_window_pose` / `pose.sample_segment` / `pose.address_core` (holo3 pose.py) are what produce `pose_refused` and `insufficient_support` — the two outcomes rows 06, 08 and 29 all turn on — and no row states where the fit lives, whether it is carried, or what pins it. Rows 06/08/29 reason about the CONSEQUENCES of a refusal without a row that owns the refusal.

(3) WHICH PIXELS PLACEMENT READS ON A COLOUR CAPTURE. `store.sampling_planes` (store.py:162-169) hands a place pass the single 'y' plane when one exists and otherwise the r/g/b triple, which `place._crop_luma` reduces. holo2 never decoded colour, so this is HOLO3-ONLY — but it decides the addressing evidence for every colour volume in the corpus and the map has no HOLO3-ONLY row in this family at all.

TWO SMALLER UNCOVERED SEAMS. (a) engine.py:461-466: a popped job whose freshly-recomputed cost EXCEEDS the price it was popped at is re-pushed instead of run — an anti-inversion rule with no holo2 counterpart named anywhere in the map. (b) engine.py:309-311: a wake for an already-seated worker at an unchanged cost does not refresh its heap position (the version bump still stands, so no wake is lost); worth one line in row 18.

A SYSTEMATIC CITATION PROBLEM. `holo3/retirement_docs-2026-09/ARTEFACTS.md` is untracked and was rewritten at 17:11 today, after the reader ran. Its line numbers in this map are off by -3 to +6 in both directions and are wrong in at least one place by 80+ lines (row placement-22's `:447` for the revisit figure, which lives at :528-531). Every ARTEFACTS.md cite in this family needs a mechanical re-pin before the rows are merged into HOLO2-MAP.md, and the map should cite section anchors (e.g. '§2.12') rather than line numbers into a file that is still being written. The residue-report and source-code cites, by contrast, all resolved within a couple of lines.

EVIDENCE-WEIGHT WARNING FOR THE RULINGS. Rows 01, 03, 17, 26, 27, 28, 29 all draw on ONE artefact — four decodes of one 1000x1000-cell crop of one HP K capture at --workers 1 with a synthetic (spline-interpolated, not platen) rotation. The report's own honest-gaps section (residue :805-813) says a second crop and a multi-worker rerun are prerequisites before any of it carries a ruling, and the two clauses of holo2's dryness gate that could matter (the in-flight term and the early-close case) are exactly the two that --workers 1 and a run-to-exhaustion cannot test. The reader states this per-row; it deserves to be stated once, loudly, in RULINGS.md.

BIT-EXACTNESS. The reader's structural finding (2) checks out: the only live cross-tree oracle touching this family is test_h3_drift_kernels.py:517 (window layout constants and starts). Rows 04, 05, 07, 13, 14, 21, 28, 31 rest on reading plus holo3's own goldens. I re-read both sides of every one of them and found no arithmetic difference — but 'verified by two readers' is not the same currency as the PINNED label suggests, and the maps should say so.

**Second lens (yield) family notes.** YIELD LENS, family total. Nine of the thirteen rows can change which tiles certify on the archived corpus; one is ordering only (placement-03); one is unobservable (placement-02); one is certificate-bearing only through another row's change (placement-13, which is the page-domain default). Every verdict was re-derived from both trees at HEAD 29d9a8d; no receiver was run.

FOUR ADJUDICATIONS. (1) placement-13: I OVERTURN the first refuter's reclassification. The record's own vocabulary (retirement_docs-2026-09/README.md:36-37) makes CARRIED-DIFFERENT mean 'different implementation', and the refuter concedes the code is line for line; the behavioural change lives entirely in one argument whose default is placement-25's delta. Reclassifying would put two rulings on one change. Correction to the refuter's wording too: at holo2's single-page default the rival set is not empty, only its cross-page half is. (2) placement-29: I UPHOLD the refuter on the parent half (holo3/engine.py:566-575 - `state.subdivided` is permanent, so the early return fires once and the next exhausted pass retires) but REJECT its consequence. The certificate-bearing half is the other one: retirement on too-little-support is absorbing in holo3 (store.py:603-605, engine.py:417), where holo2 keeps the window asleep and revivable, so the row is decides-certificates, not the reader's decides-order-only. Recommendation re-scoped onto that rule and the never-retiring-parent item struck. (3) placement-08: refuter UPHELD - version-relative dormancy (place_sched.py:104-106) makes the parent's second chance deferred, not blocked - with one addition: the deferral is not cosmetic, it puts the parent's area-wide correlation after all four children's, the most expensive ordering of the same attempts. (4) placement-02: the refuter's quarantine finding is FACTUALLY RIGHT but mis-scoped and unobservable - holo3 has no quarantine subsystem at all (API.md:758), so it belongs in an absent-subsystem row; and holo2's own record is zero contradictions in ~1,780 known-position reads, so the filter never removed an anchor. holo2's second clause (one pose per window) holds structurally in holo3 anyway (store.py:641 keeps one standing Placement per window).

EVIDENCE CONCENTRATION - state this once, loudly, in RULINGS.md. Rows 01, 03, 06, 17 and 29 all draw on ONE artefact: four decodes of one 1000x1000-cell crop of one HP K capture at one worker with a synthetic rotation. The report's own honest-gaps section asks for a second crop and a multi-worker rerun before any of it carries a ruling. Nothing here is a population.

ONE THING TO PUT IN FRONT OF GERMANO FIRST: placement-11. The per-flavour correlation floor is used twice - as the pre-search eligibility mask AND as the straddle-audit acceptance bar for anything the correlation route places (place.py:768 -> :788). So the reachable flavour's lower floor loosens a test that admits addresses, not only one that decides what is worth scoring. That is the only place in this family where holo3 made an acceptance bar looser than holo2's.

TWO CHEAP MEASUREMENTS, no paper needed: (a) placement-03's reopening brief - one archived K sheet decoded twice on holo3 without --complete, with and without a distance leg, compared on certificates at close; (b) placement-22 - count calibration refusals on an archived K decode and multiply by the tiles each covered, which bounds what holo2's atomic rule was discarding. Both are minutes of machine time on existing states.

CITATIONS: I re-pinned every ARTEFACTS.md line I used against the 17:11 rewrite (the head-to-head table is :415-422, the page-domain qualification :768, the revisit figure :528-531, bit-exactness :773). The file is untracked and still moving - the maps should cite section anchors (2.1, 2.12) rather than line numbers.


### placement-01 — Consult reach at the cheap tier — which already-placed windows may steer an unplaced one

**DIVERGED** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B29, B30, B31

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Which anchors a window is offered to extrapolate a pose from, and therefore whether it ever gets an address at all.

**holo2.** The ring tier's anchor population is `ring_targets` (the eight lattice neighbours on the window's OWN footing and region) plus `donor_sources` (windows on strictly COARSER footings whose extent contains this one). `donor_sources` skips any footing with `ppc >= target.ppc`, so a lane-0 (coarsest) window has no donors at all and can only ever consult its own eight lane-0 neighbours; information flows strictly coarse to fine. The offers are then sorted by the ratified distance (centre-to-centre cells over the window stride) and truncated to CONSULT_KEEP=8, minus the tried set.

*Where:* `holo2/src/holo2/solve/place_job.py:293-314`; `holo2/src/holo2/solve/place_shared.py:651-703`; `holo2/src/holo2/solve/place_shared.py:737-763`; `holo2/src/holo2/solve/place_job.py:317-372` · *dial:* live

**holo3.** `anchors_of` returns the standing placement of EVERY window of the same capture and region, at ANY level and ANY distance — no level filter and no direction filter. `consult_seeds` then applies the same distance sort and the same truncation to 8. So holo3's cheapest tier already has the reach holo2 reserves for its gated wide tier, and a coarse-lane window can be seeded by a fine-lane pose.

*Where:* `holo3/plugins/place_sched.py:62-75`; `holo3/plugins/place_sched.py:78-92`; `holo3/plugins/place.py:346-362`; `holo3/plugins/place.py:26-27`

*Scheduler row / doc:* SCHEDULE.md price ladder row `place / ring` (40); SCHEDULE.md:337-352 'The life of a decode'

**Implementation delta.** Anchor population: holo2 = 8 same-footing lattice neighbours + coarser-footing containers (directional, coarse->fine only); holo3 = every placed window of the capture+region at any lane, nearest 8 by the same distance metric. Same sort key, same truncation constant, same distance function; the set that is sorted differs. Fires at the same place (the cheapest placement stage) with the same price (40 + 2*lane_depth). The evidence each reads is the same committed-pose index; holo3 reads it unfiltered.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) unresolved windows left 155 (holo3) vs 196 (holo2) at 0.00 deg, 281 vs 397 at 0.80 deg; lane-0 (2 px/cell) failure 37.1% vs 54.6% and 58.3% vs 81.6%; certificates 112 vs 100 and 82 vs 56; zero wrong certificates on either side, and at 0.80 deg holo3's certificate set is a strict superset of holo2's — *artefact:* ARTEFACTS.md:407-433 (§2.1), backing scratch/sheetI-20260831/v2v3-placement-residue.md:25-33, :57-59
- (holo3) 28-80% of every lane-0 chain pose in four datasets comes from an anchor holo2's rule would never have offered: crop 0.00 deg 57 of 86 (66%), crop 0.80 deg 41 of 51 (80%), e029 whole sheet 101 of 354 (28.5%), sheet-H max-stack 1,672 of 3,091 (54.1%); lanes 2 and 3 are at 0.0% — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:382-395 (named by ARTEFACTS.md:436-440)
- (holo3) the cost of the same reach: one window fired 18 times against holo2's worst of 7; `ring` fires 2.7x per chain pose on sheet H (22,205 fires / 8,185 chain poses), 1.4x on xerox-k — *artefact:* ARTEFACTS.md:436-441; scratch/sheetI-20260831/v2v3-placement-residue.md:57-62, :443-449

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — the only direct head-to-head on identical material says the narrow reach is the worse of the two on every row, and the reach numbers point the same way on four independent datasets. The residue report's own recommendation is 'cap the repetition, not narrow the reach'. Record the tail cost as a separate, non-yield line of inquiry.

**Notes.**

*Reader:* The reach numbers are upper bounds: 'not reachable at that instant' is not 'never placed' (scratch/sheetI-20260831/v2v3-placement-residue.md:800-806). The head-to-head is one 1000x1000-cell crop of one HP K capture at --workers 1, with a synthetic platen angle (:786-822). Not a population.

*Refuter (upheld):* *Corrections:* Citation hygiene only. The strict-superset / zero-wrong claim is at scratch/sheetI-20260831/v2v3-placement-residue.md:54-56, not :57-59 (:57-63 is the tail/reach paragraph). The head-to-head table is :27-35, not :25-33. ARTEFACTS.md moved under the reader (untracked file, mtime 17:11): the §2.1 table is :415-422 and the reach paragraph :433-438, not :407-433/:436-440.

*Reason:* Both sides re-read at HEAD: holo2 place_job.py:293-314 (_anchor_plans) + place_shared.py:651-703/737-763 (ring_targets, donor_sources with `footing.ppc >= target.ppc` skip) and holo3 place_sched.py:62-75 (anchors_of, `_level` unused) + place.py:347-362 confirm the reach delta exactly as stated; every quoted number reproduces.

*Second lens (final: DIVERGED):* Reader upheld; the first refuter's corrections are citation hygiene only and I concur with them. Re-derived at HEAD: holo3/plugins/place_sched.py:62-75 (`anchors_of` filters on capture and region only, `_level` is unused) and holo3/plugins/place.py:346-362 (sort on (distance, candidate_id, affine), truncate to CONSULT_KEEP=8 at holo3/plugins/place.py:26) against holo2/src/holo2/solve/place_shared.py:737-763 (`donor_sources` skips any footing with `ppc >= target.ppc`). The reach delta is exactly as stated. Yield lens: this is the one row in the family with a direct measured certificate delta on real material (ARTEFACTS.md:415-422 = holo3/retirement_docs-2026-09/ARTEFACTS.md §2.1), so it decides certificates, not order.

---

### placement-02 — The WIDE consult tier and its regional least-squares affine seed (R-B)

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **nothing observable** · ruling needed **N** · seeds: B30

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether a window far from every placed neighbour gets one extra hypothesis — the page-average warp — before the ladder escalates to correlation.

**holo2.** A separate priced tier (120, GATED). It widens the anchor DISTANCE — every window of the region on every footing of the capture, nearest-8 — and adds one extra candidate: a least-squares affine fitted through the four extent corners of every committed pose on the region's majority page, refusing below two contributing poses or on a rank-deficient system. `WIDE_ANCHORS = 8` is deliberately the same number as CONSULT_KEEP, so only the reach widens.

*Where:* `holo2/src/holo2/solve/place_job.py:136-140`; `holo2/src/holo2/solve/place_job.py:305-314`; `holo2/src/holo2/solve/place_job.py:375-455`; `holo2/src/holo2/solve/place_tiers.py:163-166` · *dial:* live

**holo3.** The same tier at the same price, ungated, and `regional_seed` is a line-for-line carry (same corner correspondences, same majority-page rule with the lowest index breaking a tie, same two-pose floor, same numpy rank test, same seed id carrying the affine terms). Because holo3's ring tier already reaches the whole region at any lane and WIDE_ANCHORS == CONSULT_KEEP == 8, the wide pass adds nothing but the regional seed — the eight anchors it would offer are already in the window's tried set.

*Where:* `holo3/plugins/place.py:38`; `holo3/plugins/place.py:45`; `holo3/plugins/place.py:346-362`; `holo3/plugins/place.py:365-406`; `holo3/plugins/place_sched.py:85-90`

*Scheduler row / doc:* SCHEDULE.md price ladder row `place / wide` (120)

**Implementation delta.** Same code, same constants, same price; the tier's CONTENT collapses because row placement-01 moved its reach down to the ring tier. In holo3 `wide` is effectively 'try the regional affine, then arm cold' — `store.py:592-594` sets `cold_armed` off `wide_spent`, which is now the tier's main function. holo2's wide is additionally gated on global dryness; holo3's is not (row placement-26).

**Evidence status.** MEASURED

**Evidence.**

- (holo3) 94% of the crop control's 344 wide fires settled `nothing_to_try`; wide cpu 114 s of 9,866 s placement (1.2%) on sheet-H max-stack, 3 s of 486 s (0.7%) on e029, 0.4 s of 146 s (0.2%) on xerox-k — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:434-441, :443-449 (named by ARTEFACTS.md:436-441)
- (holo2) `WIDE_ANCHORS = 8` is UNMEASURED — 0 wide passes on all three arms — *artefact:* ARTEFACTS.md:465 (§2.1 holo2 side); ARTEFACTS.md:811 (G-12)

**Yield relevance.** nothing observable — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's — the tier still runs and still supplies the regional seed; only its redundant half is dead. Nothing to port.

**Notes.**

*Reader:* Neither tree has a measurement of the regional seed's own yield: holo2 never fired a wide pass, and holo3's wide fires are almost all `nothing_to_try`. So the R-B mechanism itself is untested on both sides. holo2's `solve/DESIGN.md` records the `regional_seed` docstring's 'v1 port' provenance claim as VERIFIED WRONG — it is holo2-original — and holo3 inherited both the code and the claim.

*Refuter (upheld):* *Corrections:* The delta is INCOMPLETE and the 'line-for-line carry' overstates it: holo2's regional_seed (place_job.py:424-432) skips a quarantined pose and reads `index.live_pose`; holo3's (place.py:365-406) consumes the raw `anchors_of` tuple with no quarantine filter. Add 'minus the quarantine filter (row placement-23)' to implementation_delta rather than leaving it only in row 23. The cold-arming line is store.py:594-596, not :592-594 (the residue report's :592-594 is stale too). ARTEFACTS' `WIDE_ANCHORS=8 UNMEASURED` row is :462, not :465; G-12 is :816, not :811.

*Reason:* Corner arithmetic verified equivalent (holo2 geometry.py:95-102 `origin + pitch*(i+0.5)` == holo3 place.py:372-379), as are the majority-page rule, the two-pose floor, the rank<3 refusal and the seed id; the only substantive omission is the quarantine filter.

*Second lens (final: CARRIED-DIFFERENT):* The first refuter is factually right and I confirmed it - holo2/src/holo2/solve/place_job.py:428-431 skips a quarantined pose and reads `index.live_pose(anchor.window_id)`, while holo3/plugins/place.py:365-406 consumes the raw `anchors_of` tuple with no such filter - but the correction is mis-scoped and, on the yield lens, empty. (a) holo3 has no quarantine subsystem at all (holo3/API.md:758 'No quarantine'), so this is one consequence of an absent-subsystem row, not a delta belonging to the wide tier. (b) It cannot fire on the archived corpus: the record is zero contradictory reads in ~1,780 known-position decodes (ARTEFACTS.md §2.11, citing docs/RECEIVE-DESIGN-EVIDENCE.md:492), so no pose was ever condemned and the filter never removed an anchor. (c) The other half of holo2's clause - one pose per window, so a revised anchor is not double-weighted - holds structurally in holo3 anyway: holo3/store.py:641 keeps exactly one standing Placement per window id, which is what `anchors_of` reads. So: add a one-line cross-reference to the absent-quarantine row and keep the classification.

---

### placement-03 — Ordering WITHIN a price class — the offered-seed-distance leg of the queue key (ruling R-A)

**DIVERGED** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B31

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Which of many equally-priced ready windows fires next; on a run that is preempted by a verified close, that is what gets certified.

**holo2.** The heap key is `(price, offered_distance, ordinal)`: within one price class, the window with the best AVAILABLE seed distance fires first (Dijkstra-flavoured frontier growth along the most confident edges), with an arrival ordinal bumped to the back on each wake so nothing starves. The distance is set by a ping or by the admission peek, and cleared at claim.

*Where:* `holo2/src/holo2/solve/place_slot.py:220-225`; `holo2/src/holo2/solve/place_sched.py:883-893`; `holo2/src/holo2/solve/place_sched.py:385-388` · *dial:* live

**holo3.** The frontier key is `(cost, seq, plugin, stage, subject)` — a monotone insertion sequence, no distance term. Within one price class holo3 is FIFO by last push: a window adjacent to a pose that just landed is worked at exactly the same priority as one nowhere near any anchor. The round-robin property survives (every push takes a fresh `seq`).

*Where:* `holo3/engine.py:314-319`; `holo3/plugins/place_sched.py:259-262`

*Scheduler row / doc:* SCHEDULE.md:1-34 (the engine's frontier: 'same-price rows are deliberate round-robin peers')

**Implementation delta.** holo2 carries a second sort leg (best offered seed distance) inside every price class; holo3 has none. holo2 derives the leg from a push (the ping carries the distance); holo3's consult is a fire-time query with no place to put a pre-computed distance. Nothing in holo3 reads or writes an equivalent quantity.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the distance leg is recorded as absent, and ranked lowest priority of seven findings ('R7 — the offered-distance leg') — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:270-282, :739-748 (the report ARTEFACTS.md:405-441 cites)
- (holo2) accepted consult distances are 0.0 x24 / 0.9812 x18 / 1.0 x14 and accepted rank is 0 on all 56 accepted offers — the nearest offer won every time — *artefact:* ARTEFACTS.md:459-460 (§2.1 holo2 side)

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's, and record the reopening brief. The measured head-to-head at --workers 1 shows holo3 ahead on certificates with the leg absent, and no artefact isolates the leg. It becomes yield-relevant only on a run that stops early (close preemption) — the costed measurement is a paired non-`--complete` decode of one archived K sheet with and without a distance leg, minutes on holo3.

**Notes.**

*Reader:* holo2's own OR-7 census says the leg never had to arbitrate: the nearest offer won every accepted contest, so its measured content on that corpus is nil.

*Refuter (upheld):* *Corrections:* holo3's heap push is engine.py:313-318 (the tuple literal at :316-318), not :314-319. The `accepted rank 0 on all 56` row is ARTEFACTS.md:460, not :459-460.

*Reason:* holo2 place_slot.py:220-225 `sort_key -> (price, distance, ordinal)` and holo3's `(cost, seq, plugin, stage, subject)` confirmed; nothing in holo3 computes or stores an offered distance, and R7 at residue :739-745 is the record.

*Second lens (final: DIVERGED):* Reader upheld, refuter's line-number fix accepted: the frontier key is the five-tuple built at holo3/engine.py:316-318, `(cost, self._seq, worker.plugin, stage, worker.subject)`, against holo2/src/holo2/solve/place_slot.py:220-225's `(price, distance, ordinal)`. Nothing in holo3 computes or stores an offered distance. Yield lens: order-only, with one boundary the reader did not draw - firing order is not certificate-neutral in general, because `insufficient_support` is an absorbing retirement in holo3 (holo3/store.py:603-605, and a retired worker is skipped at holo3/engine.py:417), and the support a fit reads depends on the region lattice seed standing at fire time (holo3/plugins/place.py:701-707). So an early fire can foreclose a window a later fire would have kept. That coupling is bounded by measurement: 4 windows retired in one head-to-head arm and 0 in the other.

---

### placement-04 — The tried-set floor — a pass's declared hypothesis domain (ruling Q1, the v1-parity withdrawal)

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B15

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** How strict the support floor is for THIS pass, and therefore whether a thinly-supported window may accept an address at all.

**holo2.** `pass_budget` prices the window's cumulative distinct hypotheses as `49 x max(1, tried + offered)` and nothing else. The withdrawn Stage-A term is documented in place: at the production Stage-A domain of 147,456 phases, two spent stages put the domain at 294,961, past the 250,530 knee where the floor crosses 30 -> 31, so it read 31 where v1 reads 30 and refused windows supported at exactly the E022 floor. `words_spent` still rides the qualification id but no longer prices anything.

*Where:* `holo2/src/holo2/solve/place_job.py:460-510` · *dial:* live

**holo3.** `pass_budget_hypotheses(tried, offered) = LOCAL_HYPOTHESES * max(1, tried + offered)` with `LOCAL_HYPOTHESES = (2*3+1)**2 = 49`. Same expression, same single term, no Stage-A term. `run_window_pass` computes it once per pass from `job.tried_count` and `len(seeds)` and derives the floor from it.

*Where:* `holo3/plugins/place.py:81-82`; `holo3/plugins/place.py:25`; `holo3/plugins/place.py:692-693`

*Scheduler row / doc:* 07-placement.md:76-84 (the gate/floor constants); no SCHEDULE.md row — this is inside the `place` job

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) `LOCAL_HYPOTHESES == 49`; `pass_budget_hypotheses(0,0) == 49`, `(0,8) == 49*8`, `(3,5) == 49*8` — *artefact:* holo3/tests/test_h3_plugins_placement.py:83-88 (`test_pass_budget_scales_with_tried_and_offered_hypotheses`, in-tree golden)
- (holo2) the withdrawn Stage-A deviation put min_support at 31 where v1 reads 30; knee at 250,530; the two-stages-spent pass at a domain of 294,961 — *artefact:* ARTEFACTS.md:462 (§2.1 holo2 side, citing MEASUREMENTS.md:1367-1368 and holo2 solve/DESIGN.md:649)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The pin is an in-tree golden, not a cross-tree oracle: no drift-test module compares holo3's placement budget against holo2's or v1's (the four drift modules cover format, BCH/LDPC/PAVA/geometry/decimate/owners, calibrate/refine/colour/tiles — ARTEFACTS.md:775-783). The expressions were compared by reading both.

*Refuter (upheld):* *Corrections:* None material. For completeness: holo2 wraps the product as `max(budget.max_hypotheses, domain)` (place_job.py:508) — a no-op since domain >= 49 — and validates its inputs; holo3's `pass_budget_hypotheses` (place.py:81-82) is the bare product. The Stage-A parity row is ARTEFACTS.md:464, not :462.

*Reason:* Both expressions read at HEAD are the same single term `49 * max(1, tried+offered)`; the withdrawn Stage-A term is documented-and-dead in holo2 (place_job.py:491-503) and absent in holo3.

---

### placement-05 — The derived support floor (L7b): `max(30, ceil(log2 H / (1 - h2(BER))) + margin)` per disjoint parity population

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B16

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** How many supported sites a hypothesis must clear before it may be accepted — the pre-pixel eligibility mask on every route.

**holo2.** `identifiability_support_floor(H, BER)` is e026's site-count law with the `error == 0` special case and `int(math.ceil(...))`; `AttemptBudget.min_support` floors it by `E022_SUPPORT_FLOOR_SITES = 30` and adds `support_margin_sites = 0`. `BER_ENVELOPE` is 0.08. Every constant carries a row in the OR9_FLOORS table with an origin and a source.

*Where:* `holo2/src/holo2/solve/place_admission.py:60-84`; `holo2/src/holo2/solve/place_admission.py:122-141`; `holo2/src/holo2/solve/place_model.py:217-230`; `holo2/src/holo2/solve/place_admission.py:208-315` · *dial:* live

**holo3.** `identifiability_support_floor` and `min_support_for` are the same two functions with the same arithmetic, the same `hypotheses == 1 -> 0` case and the same `math.ceil`. The constants are bare module-level literals (30, 0.20/0.20/0.08/0.24, 0.08, 0) instead of a provenance table.

*Where:* `holo3/plugins/place.py:16-22`; `holo3/plugins/place.py:62-78`

*Scheduler row / doc:* 07-placement.md:76-84

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) GATE_SEARCH_TRUE 0.20, GATE_RIVAL_DECOY 0.20, GATE_MINIMUM_GAP 0.08, GATE_VALIDATION_TRUE 0.24, E022_SUPPORT_FLOOR_SITES 30, BER_ENVELOPE 0.08, SUPPORT_MARGIN_SITES 0, WORD_FALSE_ACCEPT 1e-3 — all frozen as goldens; the whole domain table is reproduced from the closed-form expression — *artefact:* holo3/tests/test_h3_plugins_placement.py:31-46, :61-72

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* What holo3 lost is the OR9_FLOORS provenance table, not the arithmetic — a comment-carry item, not a behaviour row. The receiver stays PROVISIONAL on both sides: neither bound is a tail bound for the weighted mismatch statistic, and the declared false-accept target still owes the physical/null qualification.

*Refuter (upheld):* *Corrections:* The row calls the derived floor 'the pre-pixel eligibility mask on every route' and stops there; it is ALSO the straddle-audit bar (holo3 place.py:718 `audit_floor = floor` -> :788; holo2 place_job.py:714 passes the same `budget` into place_addressed -> place_shared.py:588). Add that, because it is what makes row placement-11's per-flavour change move an acceptance bar and not only a mask.

*Reason:* holo2 place_admission.py:122-141 + place_model.py:216-229 and holo3 place.py:62-78 are the same arithmetic with the same hypotheses==1 case, the same math.ceil and the same 30/0.08/0; the hard 30-site sample gate is carried identically too (holo2 place_shared.py:549, holo3 place.py:706).

---

### placement-06 — Window subdivision — WHEN four corner windows are added, and what happens to the refused parent (the straddle-audit refusal path)

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B17

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a refused rectangle is retried as four smaller ones, and whether the whole window still climbs to its next word stage.

**holo2.** `SUBDIVISION_REFUSALS = {pose_refused, straddle_audit_refused, cold_refused_cold_live, cold_refused_cold_rest}`, and subdivision fires ONLY from the dormant branch of `settle` (the ladder had nothing left) and only if the outcome is in that set. On a straddle-audit refusal holo2 deliberately deviates from v1: the WorkResult carries no `retire`, so the window re-arms and climbs to its next unspent word stage — the comment states this explicitly ('REST becomes eligible here where v1 never offered it'). Subdivision on that outcome therefore only happens when the ladder was already exhausted.

*Where:* `holo2/src/holo2/solve/place_job.py:170-214`; `holo2/src/holo2/solve/place_job.py:716-725`; `holo2/src/holo2/solve/place_sched.py:779-805`; `holo2/src/holo2/solve/place_subdivide.py:58-113` · *dial:* live

**holo3.** `_fold_place_outcome` subdivides DIRECTLY on `pose_refused` (and marks the window dormant) and on `straddle_audit_refused` (and ALSO re-pushes it, so it climbs to its next unspent stage). Every other non-accepted outcome goes to `_place_repush`, which subdivides on LADDER EXHAUSTION regardless of the refusal word. `insufficient_support` retires immediately and never subdivides. `place.SUBDIVISION_DIRECT`, `place.NEVER_SUBDIVIDES` and `place.subdivides()` exist but are referenced only by `tests/test_h3_plugins_placement.py:127-135` — the production path is the two explicit branches plus the exhaustion branch.

*Where:* `holo3/store.py:600-614`; `holo3/engine.py:514-533`; `holo3/engine.py:564-576`; `holo3/plugins/place.py:57-59`; `holo3/plugins/place.py:111-114`

*Scheduler row / doc:* SCHEDULE.md price ladder rows `place / ring..cold_rest`; no design doc names the subdivision trigger

**Implementation delta.** Straddle audit: v1 sends a refused centre candidate straight to subdivision and never to the rest sweep; holo2 does NOT subdivide there in the common case and re-arms the rest tier instead; holo3 does BOTH — it quarters the window immediately AND re-pushes it to the rest stage. holo3 is the union, not a point on the line between the two. Second delta: holo2 refuses to subdivide on any outcome outside its four-word set (`place_subdivide.py:98` returns without children), so a window that goes dormant on `wide_refused` / `consult_refused` / `no_word_candidate_*` / `nothing_to_try` with no cold flavour left to offer is left whole; holo3's exhaustion branch quarters it. Third delta: the outcome vocabulary is otherwise identical (same four words), and the child geometry is identical (row placement-07).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) F-04 CLOSED: the `run_subdivision` arm reproduces v1 exactly, 88 = 88 — *artefact:* ARTEFACTS.md:470 (§2.1 holo2 side)
- (holo3) subdivision is measured as actively harmful on the coarsest lane: at ppc 2 a 100-cell child reads a true 0.40 deg rotation as 0.56 deg (a 40% error) against 0.389 deg at 200 cells, because halving the window halves the FFT's frequency resolution while the fundamental stays pinned to the Nyquist bin; 1,150 of 1,448 orange chips in one run were 100x100 children — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:351-373 (the report ARTEFACTS.md:405-441 cites)
- (v1) the straddle-audit refusal path and declared-vs-voted pitch have NO measured number on any of the three sides — only code behaviour — *artefact:* ARTEFACTS.md:806 (G-08); restated ARTEFACTS.md:476-478

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's straddle behaviour (it is a strict superset of both predecessors: nothing is refused that either tree would have tried), but rule on the exhaustion-branch widening. The measured coarse-lane finding argues for gating subdivision on the refusal word — restoring holo2's set — and never subdividing on the coarsest lane at all. That is a receiver-axis change with a cheap null proof (the outcome set is already spelled in `place.SUBDIVISION_DIRECT`, currently dead code), so it is a 'port now' candidate rather than a loss to accept.

**Notes.**

*Reader:* The residue report states holo3 'subdivides on ladder exhaustion, whatever the outcome'; re-deriving both sides I find holo2 reaches the same place one wake later in the SPECIFIC case of an already-armed window with no offerable cold flavour (its `settle` calls `_arm_cold`, which returns False when already armed, and falls through to `_subdivide`) — but `place_subdivide.subdivide` then refuses the outcome word and produces no children. So the divergence is real, just narrower than the report's wording. I could not find any artefact that counts how often it fires.

*Refuter (upheld):* *Corrections:* ARTEFACTS cites: G-08 is :812 (not :806); the §2.1 closing line is :475-476 (not :476-478); F-04 `88 = 88` is :472 (not :470). The dead-code claim is exact — grep at HEAD shows place.SUBDIVISION_DIRECT / NEVER_SUBDIVIDES / subdivides() referenced only by tests/test_h3_plugins_placement.py:127-135.

*Reason:* store.py:601-614 confirms the three branches (pose_refused -> dormant+subdivide; straddle_audit_refused -> subdivide AND repush; everything else -> _place_repush) and engine.py:564-575 confirms exhaustion-subdivides-regardless. holo3's own conversion spec (conversion_docs/wave2-reports.md:67) says the opposite ('subdivides only on cold_refused_*'), so the row is a code-vs-spec divergence as well as a holo2 one.

*Second lens (final: DIVERGED):* Reader upheld with a narrowing I derived myself. Confirmed at HEAD: holo3/store.py:606-612 (pose_refused -> dormant plus quarter; straddle_audit_refused -> quarter AND re-push; everything else -> `_place_repush`) and holo3/engine.py:564-575 (on ladder exhaustion, quarter regardless of the refusal word), against holo2/src/holo2/solve/place_subdivide.py:98-99, which returns without children for any outcome outside its four-word set. The refuter's extra finding is right and worth keeping: holo3's own conversion spec (holo3/conversion_docs/wave2-reports.md:67) says the opposite of holo3's code. My narrowing: the exhaustion branch fires only after every rung is spent, and the correlation rungs are last in the ladder (holo3/plugins/place.py:41-48), so the outcome word at exhaustion is usually already `cold_refused_*`, which is inside holo2's set. The real divergence window is the window whose correlation rung was never offerable - it reaches exhaustion under a different word and holo3 quarters it where holo2 would not.

---

### placement-07 — Subdivision termination bounds and the corner-child geometry

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B18

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** How many extra windows the scheduling set can grow by, and where the four corners sit.

**holo2.** `subdivision_child_extents`: refuse at `depth >= SUBDIVISION_MAX_DEPTH (1)`; square side `max(min_window_cells (70), min(h,w)//2)`; refuse when that side cannot shrink the window; four corners in v1's order (TL, TR, BL, BR), overlapping in the middle whenever the floor raises the side above the half. A window subdivides at most once (`Slot.subdivided`). Children with zero supported cells and children outside the lattice are dropped. Set bounded by `plans + 4 x plans`.

*Where:* `holo2/src/holo2/solve/pose_fit.py:746-785`; `holo2/src/holo2/solve/plans.py:184-228`; `holo2/src/holo2/solve/place_admission.py:69-73`; `holo2/src/holo2/solve/place_slot.py:106-107` · *dial:* live

**holo3.** `pose.subdivision_child_extents` is the same expression line for line (MIN_WINDOW_CELLS = 70, SUBDIVISION_MAX_DEPTH = 1, same side formula, same refusal, same four corner order). `place.child_windows` drops corners outside the frame and corners with zero support, exactly as holo2's `child_window_plans` does. `WindowState.subdivided` makes it at most once; `_fold_window` refuses a duplicate window id.

*Where:* `holo3/plugins/pose.py:19-20`; `holo3/plugins/pose.py:814-830`; `holo3/plugins/place.py:249-275`; `holo3/plugins/place_sched.py:46-47`; `holo3/engine.py:514-520`

*Scheduler row / doc:* no design doc names it; the ladder is SCHEDULE.md's `place` row

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) children stay inside the frame and take a new depth — *artefact:* holo3/tests/test_h3_plugins_placement.py:262 (`test_child_windows_stay_inside_the_frame_and_take_a_new_depth`)
- (holo2) the 70-cell floor's cost, on record: it refuses a 64-cell clipped window whose ~4,096 supported cells clear the derived floor easily; v1 clipped edge windows of 193 and 131 cells were dropped under it on the differential's own arms — *artefact:* ARTEFACTS.md:467 (§2.1 holo2 side); holo2/src/holo2/solve/place_admission.py:276-284

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* holo2 has a `config.subdivide` dial in front of the same function; holo3 has none (always on). Neither tree pins the extents against v1 with an oracle test.

*Refuter (upheld):* *Corrections:* The v1-clipped-edge number (193 and 131 cells) is ARTEFACTS.md:470, not :467.

*Reason:* holo2 pose_fit.py:746-785 and holo3 pose.py:814-830 are the same five lines with the same constants (70 / depth 1 / max(min, min(h,w)//2) / same corner order); the only difference is holo2's `config.subdivide` dial, which the row already records.

---

### placement-08 — The parent's afterlife — a window whose four corners all failed arms COLD on its full extent

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B19

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether a subdivided parent gets one more, area-wide correlation attempt after its children give up.

**holo2.** `review_parents` runs after every settle over the `_parents` list (the reference only ever points down). A parent whose children have ALL reported a non-serving verdict is marked `cold_parked` and armed for cold on its full extent — correlation wants area. `child_verdict` treats three states: an exit reason in EXIT_SERVED (placed / done_covered / settled_placed) is a serve; anything else is a failure; a child neither ready nor in flight (DORMANT) counts as finished and failed, deliberately, so a parent is not blocked forever.

*Where:* `holo2/src/holo2/solve/place_subdivide.py:116-181`; `holo2/src/holo2/solve/place_slot.py:102-114`; `holo2/src/holo2/solve/place_sched.py:516-557` · *dial:* live

**holo3.** `_afterlife` is triggered from a CHILD's terminal event (`insufficient_support` retirement, or ladder exhaustion with no children of its own). It walks up through `WindowState.parent`, returns unless every child is retired (its own state or its bookmark), then un-retires the parent, clears its dormancy, sets `cold_armed` and re-pushes it. `afterlife_used` makes it at most once. Cold then runs on the parent's full extent, as in holo2.

*Where:* `holo3/engine.py:535-562`; `holo3/engine.py:564-576`; `holo3/store.py:602-607`; `holo3/plugins/place_sched.py:48-53`

*Scheduler row / doc:* no design doc names it

**Implementation delta.** Trigger direction and the dormancy clause. holo2 polls DOWN from a `_parents` list after every settle and counts a dormant child as failed; holo3 is pushed UP from a child's terminal fold and requires `child.retired or bookmark.retired` for every child. A child that refused its own pose fit (`pose_refused`) in holo3 goes dormant and subdivides into nothing (depth 1), and is neither retired nor re-pushed — so it never becomes 'settled' and the parent's afterlife never fires. holo2's `child_verdict` returns False for exactly that child and the parent arms. Everything else — the full-extent cold, the at-most-once bit, 'correlation wants area' — is the same.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) no artefact isolates the afterlife on either side; the only related measurement is that the correlation tier committed ZERO poses on all three archived whole-sheet runs (5,332 fires) while taking 13-65% of every placement second — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:409-425 (named by ARTEFACTS.md:436-441)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's, and record the dormant-child clause as a known narrowing. A parent whose corner refused its own fit is a window whose lattice could not be measured anywhere in that rectangle, and the archived evidence says a full-extent cold on such a rectangle buys nothing (zero poses in 5,332 fires on three whole sheets). Porting holo2's dormancy-counts-as-failure clause is a two-line change if the ruling goes the other way; the honest statement is that no artefact tells us which is right.

**Notes.**

*Reader:* I verified the blocking case by reading both trees' branch structure; I did not find a run in which it fires. The related question — whether cold on a full parent extent is worth anything at all — is row placement-26's evidence.

*Refuter (upheld):* *Corrections:* 'so it never becomes settled and the parent's afterlife never fires' is TOO STRONG and must be softened. Dormancy in holo3 is version-relative (place_sched.py:104-106): any write on the child's read set bumps `worker.version`, `dormant()` goes false and the child fires again; on a later ladder-exhausted pass `engine._place_repush` (engine.py:570-575) sets `state.retired = True` and calls `_afterlife`. The honest claim: holo3 DEFERS the parent's afterlife until every child has taken a terminal pass, and blocks it indefinitely only for a child that is never woken again; holo2's `child_verdict` counts a dormant child as failed immediately.

*Reason:* Read at HEAD: engine.py:535-562 (`settled = all(child.retired or bookmark.retired)`) plus engine.py:443-451 (a bookmark is retired only when `place_retire_cause` fires) confirm the narrowing exists, but engine.py:564-575 shows the state is recoverable, not absorbing.

*Second lens (final: CARRIED-DIFFERENT):* The first refuter is right and the reader's row is too strong; I confirmed both halves. Dormancy in holo3 is version-relative (holo3/plugins/place_sched.py:104-106: dormant only while the stored version equals the worker's current version), any write on the window's read set bumps that version (holo3/engine.py:419-424), and a later ladder-exhausted pass sets retired and calls the afterlife (holo3/engine.py:570-575). So the parent's second chance is DEFERRED until each child has spent its own full ladder - correlation included - not blocked. Correction to the refuter in turn: this is not merely a bookkeeping deferral, because the deferral puts the parent's area-wide correlation after every child's correlation, which is the most expensive possible order. Yield lens: the afterlife's only product is a correlation sweep, and correlation committed zero poses in 5,332 fires across the three archived whole-sheet runs - but it earned 34 of 377 and 52 of 327 poses on the two fragmentary crops (scratch/sheetI-20260831/v2v3-placement-residue.md:409-425), so on fragment-class material this can decide certificates.

---

### placement-09 — The two cold flavours and the fire-time derivation of each one's page set

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B20

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which pages a correlation sweep searches, and in what order the two sweeps are asked.

**holo2.** `live_pages(view)` = the pages with a committed pose, derived from the pose index and stored nowhere, memoised on the pose COUNT (monotone, so an equal count means an equal set). `cold_pages(row, flavour, live)` partitions the row's declared page domain into live and rest. A flavour whose set is empty right now is not offered at all — costlessly and never terminally (`ColdOffer` is re-derived at admit, claim and settle). `cold_live` is priced under `cold_rest` inside a rung, and cold's own 20-per-rung term keeps `rest(d) < live(d+1)`.

*Where:* `holo2/src/holo2/solve/place_cold.py:97-133`; `holo2/src/holo2/solve/place_sched.py:474-514`; `holo2/src/holo2/solve/place_slot.py:41-65`; `holo2/src/holo2/solve/place_slot.py:189-194` · *dial:* live

**holo3.** `cold_flavour_pages(page_domain, flavour, live_pages)` is the same partition. The live set is a store cell seeded `{0}` (counter 0 is page 0 on every matrix — the unique prior) and grown by `_fold_placement` whenever a committed placement names a new page, which bumps `KEY_LIVE_PAGES` and wakes every place worker. `ladder_stage` asks whether each flavour's partition is non-empty right now and skips an empty one without marking it, exactly as holo2 does. Cold is priced 250/260 (above refine and swim) instead of 140/150.

*Where:* `holo3/plugins/place.py:121-125`; `holo3/plugins/place_sched.py:95-101`; `holo3/plugins/place_sched.py:109-121`; `holo3/plugins/place.py:39-49`; `holo3/store.py:97`; `holo3/store.py:234-235`; `holo3/store.py:672-676`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:26-32 (ruling 3-4), :153-164 (§6 rest is last by price)

**Implementation delta.** Same partition, same fire-time derivation, same empty-flavour skip. Three deltas: (a) the live set is SEEDED with {0} in holo3 and empty in holo2 — PAGE-DOMAIN.md:62-65 calls the seed load-bearing, because without it the first cold on a word-failed single sheet is a full-possible REST sweep at the rest floor and small-support windows never rest-place; (b) the domain the partition is taken over is the full possible set in holo3 and `--pages 1` by default in holo2 (row placement-25); (c) the prices moved from 140/150 to 250/260, which reorders cold behind refine (200) and swim (240) — in holo2 refine at 200 is overtaken by cold_rest from rung 3 and cold_live from rung 4.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the merge qualification, 2026-09-02: base 1,357 certs / 2,517.3 cpu-s / 37,469 jobs; merged with --pages 1 (the null) 1,360 / 2,557.4 / 37,945; merged at default (133 possible pages) 1,356 / 1,639.8 / 23,855 — all three VERIFIED e5021f8d..., 465,580 B — *artefact:* ARTEFACTS.md:768 (§2.12)
- (holo3) a page whose words are all past BCH is placed by cold_rest, with no word-route pose anywhere on the sheet — *artefact:* holo3/tests/test_h3_page_domain.py:120-140 (`test_cold_rest_places_a_page_whose_words_are_past_bch`)
- (holo2) no page-domain measurement exists; holo2 ran --pages 1 with flavourless cold tried-ids — *artefact:* ARTEFACTS.md:767 (§2.12)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — the mechanism is the carry, the domain and the pricing are the deliberate changes and both are qualified (rows placement-25 and placement-27).

**Notes.**

*Reader:* holo2's `live_pages` scans the pose index; holo3 maintains the set incrementally in the fold. Both are monotone, so the answers agree.

*Refuter (upheld):* *Corrections:* None. (holo3's `_place_repush`/`ladder_stage` empty-flavour skip verified at place_sched.py:109-121 and place.py:92-108; the {0} seed at store.py:97 and its growth at store.py:674-676.)

*Reason:* The partition function, the fire-time derivation, the costless empty-flavour skip and all three deltas (the {0} seed, the domain, the 250/260 reprice) reproduce exactly, as do PAGE-DOMAIN.md:62-65 and ARTEFACTS.md:768.

---

### placement-10 — Cold's tried-set dedup granularity — per page, or per (flavour, page)

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B21

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a page swept once under `rest` may be swept again under `live` after a pose opens it — that is, whether a window gets a second, cheaper-floored look at the same page.

**holo2.** `TRIED_COLD = 'cold-page'` and `cold_tried_id(page) = f'cold-page/{page}'` — ONE namespace for both flavours, deliberately: 'a window has one rung, and a page swept at that rung was swept whichever flavour paid for it'. So a page swept as rest and later promoted to live is never re-swept.

*Where:* `holo2/src/holo2/solve/place_cold.py:83-92`; `holo2/src/holo2/solve/place_job.py:767-790` · *dial:* live

**holo3.** `cold_tried_id(page, flavour) = f'cold-page/{flavour}/{page}'` — per flavour. A page swept as rest and later live is swept again, at the live flavour's lower support floor.

*Where:* `holo3/plugins/place.py:55`; `holo3/plugins/place.py:117-118`; `holo3/plugins/place_sched.py:95-101`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:94-97 ('With rest (W3 only): cold tried marks become per-flavour')

**Implementation delta.** One string. holo2 dedups by page alone; holo3 by (flavour, page). The design doc gives the reason: 'a page swept as rest and later live deserves a live re-sweep at the lower floor; today's flavourless `cold-page/p` dedup was sound only under one shared floor' — and holo3's floors are per-flavour (row placement-11), so the flavourless key would now discard a strictly more permissive attempt. Cost: at most one extra sweep per (window, page) that gets promoted.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the per-flavour tried mark is stated as a consequence of the per-flavour floor, not measured — *artefact:* holo3/docs/PAGE-DOMAIN.md:94-97
- (holo2) the flavourless key is stated as sound because the two flavours partition the domain and live only grows; no yield or cost number — *artefact:* holo2/src/holo2/solve/place_cold.py:83-87

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — it is the correct pairing for the per-flavour floor, and it can only add attempts, never remove them (the no-ceilings rule).

**Notes.**

*Reader:* Yield-positive by construction under holo3's floors; a pure cost under holo2's single floor. The two changes (per-flavour floor, per-flavour tried mark) must move together.

*Refuter (upheld):* *Corrections:* None.

*Reason:* holo3 place.py:55/117-118 `cold-page/{flavour}/{page}` vs holo2 place_cold.py:83-92 `cold-page/{page}`; PAGE-DOMAIN.md:94-97 carries the stated reason verbatim.

*Second lens (final: DIVERGED):* Upheld; no disagreement between the two lenses. Confirmed: holo3/plugins/place.py:117-118 keys the tried mark `cold-page/{flavour}/{page}` against holo2/src/holo2/solve/place_cold.py:83-92's `cold-page/{page}`, and holo3/docs/PAGE-DOMAIN.md:94-97 carries the stated reason. Yield lens: certificate-relevant rather than cost-only, because the second sweep is not a repeat - it runs at the lower support floor of the other flavour (holo3/plugins/place.py:753-756), so it may accept an origin the first sweep's mask excluded. It can only add attempts, never remove them. Unmeasured on the archived corpus, where correlation committed no poses on whole sheets at all.

---

### placement-11 — The declared hypothesis count a cold sweep's support floor is derived from

**DIVERGED** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B22

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** How strict the cold route's support floor is — the pre-FFT eligibility mask, which decides which origins the correlation may even score.

**holo2.** `budgets.cold` is resolved ONCE, at scheduler construction, over the row's WHOLE declared page domain: `hypothesis_count((window_cells, window_cells), row.cells_yx, len(row.page_domain))`. Both flavours are handed that same budget, so a live-only or rest-only sweep attempts strictly fewer hypotheses than were declared — the union bound's own direction — and the derived support floor is the strictest one, never loosened by a small flavour set.

*Where:* `holo2/src/holo2/solve/place_cold.py:198-234`; `holo2/src/holo2/solve/place_model.py:704-712`; `holo2/src/holo2/solve/place_sched.py:226-229` · *dial:* live

**holo3.** `prepare_place` passes `cold_h_pages = len(all_pages)` — the size of THIS FLAVOUR'S partition, before the tried-set subtraction — and `run_window_pass` derives `declared = cold.hypothesis_count(window, cells_yx, cold_h_pages)` and `cold_floor = min_support_for(declared)`. So live and rest carry different floors: live's is smaller, and admits origins rest excludes.

*Where:* `holo3/plugins/place_sched.py:186-191`; `holo3/plugins/place.py:534`; `holo3/plugins/place.py:748-761`; `holo3/plugins/cold.py:15-32`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:26-32 (ruling 3), :114-152 (§5 floors price the address space)

**Implementation delta.** The H operand. holo2: one floor for both flavours, priced on the whole declared domain, computed once before any pixel. holo3: one floor per flavour, priced on that flavour's partition, computed at fire time from live state. The formula, the constants (30 / 0.08 / margin 0) and the union-bound direction are unchanged; only which page count enters H moves. The design doc names both rejected alternatives explicitly: one global floor from the live set would under-price rest, and pricing on the tried-REDUCED sweep subset would let a window burn the partition down and accept at a cheaper floor — holo3 prices on the full partition, not the untried subset, so neither hazard applies. Consequence stated in the doc: 'the floor stays the pre-FFT eligibility mask, so the live route's lower floor admits origins rest excludes — yield, not just cost.'

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the floor instances, derived from the tree's own functions at window 200x200, constants 30/0.08/0: 53x37 -> 43 (1 page) / 48 (10) / 54 (133 possible); 10x10 -> 36 (1) / 55 (2621); 7x7 -> 35 (1) / 56 (5349). The full possible set is ~2^18 counters on every matrix, so the full-rest floor is ~54-56 universally — *artefact:* holo3/docs/PAGE-DOMAIN.md:131-140; pinned holo3/tests/test_h3_plugins_placement.py:598-613 (`test_cold_floor_is_a_function_of_the_searched_address_space`)
- (holo3) a 10-page domain with live = {0}: the live partition prices its own size (floor 43) and the declared domain would price 48 — *artefact:* holo3/tests/test_h3_plugins_placement.py:615-627 (`test_live_partition_prices_its_own_size_not_the_declared_domain`)
- (holo3) the whole page-domain change closes byte-exact: default-domain arm 1,356 certs / 1,639.8 cpu-s vs the --pages 1 null 1,360 / 2,557.4, all VERIFIED e5021f8d..., 465,580 B — *artefact:* ARTEFACTS.md:768 (§2.12)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — it is a strictly more permissive floor on the live flavour, priced on the address space actually searched, with the two rejected alternatives named and the whole change qualified byte-exact.

**Notes.**

*Reader:* This is the one place a floor became LOOSER than holo2's. It is lawful because the flavour's partition is a declared quantity fixed before the sweep, not a current-evidence narrowing: PAGE-DOMAIN.md:147-151 states the L7 escape it stands on (independent authority = other windows' rival-priced placements, epoch = facts_version, rest keeps the complement fully priced).

*Refuter (upheld):* *Corrections:* Add the second consumer: the per-flavour floor is not only the pre-FFT mask, it becomes the straddle-audit floor for a cold-routed acceptance (holo3 place.py:768 `audit_floor = cold_floor` -> :788), which mirrors holo2 setting `budget = self._cold_budget` at place_job.py:706 before place_addressed. So the live flavour's lower floor loosens an ACCEPTANCE bar as well as an eligibility mask — that strengthens the 'yield, not just cost' reading and is the sharpest thing to put in front of Germano.

*Reason:* Verified at HEAD: prepare_place passes `cold_h_pages = len(all_pages)` (place_sched.py:186-189), run_window_pass derives `declared`/`cold_floor` at place.py:753-756, and PAGE-DOMAIN.md:131-140/:147-151 carry the instance table and the L7 escape exactly as quoted.

*Second lens (final: DIVERGED):* Upheld, and the first refuter's addition is the sharpest fact in the row - I confirmed it directly: holo3/plugins/place.py:768 sets `audit_floor = cold_floor` for a correlation-routed acceptance and holo3/plugins/place.py:788 passes it to the straddle audit, mirroring holo2/src/holo2/solve/place_job.py:706. So the per-flavour floor is not only the pre-search eligibility mask, it is also the acceptance bar for anything the correlation route places. That makes the reachable flavour's lower floor a genuine loosening of an acceptance test, which is the part Germano should see. Both must be stated in the ruling. Verified the operand at holo3/plugins/place_sched.py:186-189 (`cold_h_pages = len(all_pages)`, this flavour's partition) and the derivation at holo3/plugins/place.py:753-756.

---

### placement-12 — Cold's transform residency — the lease, the resource key, and the per-fire transform cache

**ABSENT** · evidence **MEASURED** · yield **integrity** · ruling needed **Y** · seeds: B23

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Nothing about yield today; it names the memory a concurrent cold sweep holds, which an admission gate would read.

**holo2.** A fire declares a page-weighted `Lease` on a `cold-transforms` ResourceKey widened by the reference field's printed interpretation but deliberately NOT by footing (the kernel correlates in the page's cell lattice, so transforms are rung-invariant). The engine takes the lease at arm and releases at disarm. The transform dict itself is an invocation local — a declared deviation from the plan, because sharing it would have meant editing the bit-exact-pinned kernel. No policy gates on the lease.

*Where:* `holo2/src/holo2/solve/place_cold.py:136-193`; `holo2/src/holo2/solve/place_sched.py:649-657`; `holo2/src/holo2/solve/cold.py:441-520` · *dial:* lease live; the admission policy is named-not-built

**holo3.** No lease, no resource key, no residency book. `page_transforms` is a per-fire invocation-local dict, exactly as in holo2's kernel. The memmapped transform store was adjudicated 2026-09-01 and NOT built: the per-page cold transform is 45.8 MiB measured at 53x37 and 5.95 GiB derived at 133 pages, and caching it buys 27% of a rest fire's wall on a tier that must not run on a healthy sheet.

*Where:* `holo3/plugins/cold.py:242-243`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:165-173 (§7 Rejected: the memmapped transform store); API.md:753-757 ('No journal, no bookmark persistence, no event replay, no leases')

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo3) per-page cold transform 45.8 MiB measured at 53x37, 5.95 GiB derived at 133 pages; caching buys 27% of a rest fire's wall (0.444 -> 0.324 s/page) — *artefact:* holo3/docs/PAGE-DOMAIN.md:165-173
- (holo2) cold cost: transform cache ~7.6 GiB + ~1.1 GiB reference pages, 47.9 s per patch — *artefact:* ARTEFACTS.md:464 (§2.1 holo2 side)
- (holo2) the lease is a declaration and not yet a budget: 'Leases / residency — declared, never gated. No number.' — *artefact:* holo3/retirement_docs-2026-09/seeds/holo2-behaviour-ledger.md (holo2-only machinery table, `core/work.py Lease`); holo2/src/holo2/solve/place_cold.py:177-193

**Yield relevance.** integrity — source: reader.

no yield content on either side; it is a memory-accounting declaration

**Recommendation.** accept the loss — the lease was never gated on in holo2 either, and the store it would have governed is adjudicated not-built with a reopening brief already written.

**Notes.**

*Reader:* Reopen only if a measured rest fire on a real capture is the wall (PAGE-DOMAIN.md:172-173). holo3's memory doctrine (one production decode at a time, 64 GB) is what the lease would have served.

*Refuter (upheld):* *Corrections:* API.md's 'No leases' bullet is :753-757 (correct) but the quarantine bullet is :758-759 and the C-7 list :760-763 — re-pin if the row's neighbours are cited.

*Reason:* holo3 cold.py:242-243 is an invocation-local dict as claimed; PAGE-DOMAIN.md:165-173 carries 45.8 MiB / 5.95 GiB / 27% (0.444 -> 0.324 s/page) verbatim; no lease, resource key or residency book exists anywhere in holo3.

---

### placement-13 — The whole-word rival gate (L8) — a decoded word must out-score its complete rival set on WHOLE words before any evidence is written

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates (only through row placement-25; this row's own code contributes none)** · ruling needed **N** · seeds: B26

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT → second lens CARRIED-IDENTICAL.

> **Unresolved disagreement.** The second lens OVERTURNS the refuter's reclassification: refuter said CARRIED-DIFFERENT, second lens rules CARRIED-IDENTICAL. The second lens wins by the merge rule; the disagreement is recorded, not resolved away.

**What it decides.** Whether a decoded address is admitted as a placement, and therefore whether every tile under it is read at that geometry.

**holo2.** `_rivals` builds two populations: the other decoded candidates minus the winner's own neighbourhood (same page, same rotation, within `neighbor_radius_cells` is the SAME answer), and the winner's own geometry on every OTHER declared page (the parity-concentrated cross-page alias the 0.176 diagnosis named). The decoy bar binds the MINIMUM whole-word mismatch over that set; an empty rival set scores 1.0 against the winner's search-class mismatch. Bars are the exact strict E022-v2 values 0.20 / 0.20 / 0.08 / 0.24 (2026-07-14).

*Where:* `holo2/src/holo2/solve/placement.py:159-256`; `holo2/src/holo2/solve/pose_audit.py:154-175`; `holo2/src/holo2/solve/place_admission.py:76-80` · *dial:* live

**holo3.** `words.word_rival_rows(winner, candidates, page_domain, radius)` is `_rivals` line for line — same two populations, same neighbourhood dedup, same insertion order. `_word_rival_bar` is `_rival_bar` line for line, including the empty-set fallback to `parity_score(..., 0)` against 1.0. Same four bars as bare literals. The one change: the `page_domain` handed in is the POSSIBLE set (up to `row.max_pages`), not a one-page default, so the cross-page alias population is now the real one.

*Where:* `holo3/plugins/words.py:299-327`; `holo3/plugins/place.py:449-489`; `holo3/plugins/pose.py:168-172`; `holo3/plugins/place.py:17-20`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:39-44 ('the W5 rival population is drawn from the possible set'); 07-placement.md:76-84

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) the four gate constants are frozen goldens (0.20 / 0.20 / 0.08 / 0.24) alongside E022_SUPPORT_FLOOR_SITES 30 and WORD_FALSE_ACCEPT 1e-3 — *artefact:* holo3/tests/test_h3_plugins_placement.py:31-46
- (holo3) the rival rows drop the winner and its local neighbourhood, and always offer every page as a decoy — *artefact:* holo3/tests/test_h3_plugins_placement.py:444-464
- (v1) the d=27 whole-word gate exists because a parity split can hide an alias in 7 of 45 sites — *artefact:* ARTEFACTS.md:474 (§2.1 holo1 side, citing src/holo/receive/placement/search.py:38)

**Yield relevance.** decides-certificates (only through row placement-25; this row's own code contributes none) — source: second lens (reader said: decides-certificates).

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Alias pressure scales with the declared page domain, so holo3's larger default domain makes this gate STRICTER than holo2's one-page default did — the rival population is now O(row.max_pages) whole-word scores per admission. That cost is stated at PAGE-DOMAIN.md:42-44 ('cheap at 133, still cheap at 2621, not free on a degenerate row').

*Refuter (reclassified):* *Corrections:* Move the sentence now sitting in `behaviour` ('the page_domain handed in is the POSSIBLE set ... so the cross-page alias population is now the real one') into `implementation_delta`, and state the consequence: the gate's rival population changes from empty (holo2's `--pages 1` default) to O(row.max_pages) whole-word scores per admission, so the SAME code admits a different set of words. Evidence stays PINNED for the kernel; the domain half points at row placement-25. Also: holo3 sorts anchors by a STRING pose id in `anchors_of`, which is irrelevant here but is the ordering that feeds regional_seed.

*Reason:* The row is internally inconsistent — it declares CARRIED-IDENTICAL with a null delta while its own behaviour field states a behavioural change in what the gate reads. Per the classification rule, a carried row whose run-time behaviour differs in what it reads is CARRIED-DIFFERENT. The code itself IS line-for-line (holo2 placement.py:159-255 == holo3 words.py:299-327 + place.py:449-489, including the empty-set 1.0 fallback and the identical `in_domain` pre-filter at holo2 placement.py:135-136 / holo3 place.py:475-476).

*Second lens (final: CARRIED-IDENTICAL):* I side with the READER against the refuter, on the record's own vocabulary. holo3/retirement_docs-2026-09/README.md:36-37 defines CARRIED-DIFFERENT as 'same intent, different implementation', and the refuter itself concedes the implementation is line for line - I re-read both: holo2/src/holo2/solve/placement.py:190-208 == holo3/plugins/words.py:299-326 (same identity dedup, same neighbourhood rule, same insertion order) and holo2/src/holo2/solve/placement.py:245-255 == holo3/plugins/place.py:457-467 (same empty-set fallback to 1.0, same four bars). The only thing that differs is an argument, `page_domain`, whose default is row placement-25's delta and whose scaling holo2's own docstring already anticipates (holo2/src/holo2/solve/placement.py:180-183). Reclassifying here would put a second ruling on one change. Also correct the refuter's wording: at holo2's single-page default the rival set is not empty - only the cross-page half is (the decoded-candidate half at holo2/src/holo2/solve/placement.py:193-206 still runs). Fix: keep CARRIED-IDENTICAL, move the domain sentence into a cross-reference to placement-25.

---

### placement-14 — The Stage-A false-accept refusal — the ceiling a word sweep is declared against

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B26

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether the word route runs on a given window at all.

**holo2.** `stage_a` refuses with `attempt_budget_exceeded` when the ACTUAL patch's `stage_a_hypotheses` exceeds `budget.max_hypotheses`, where that budget is the DECLARED ceiling computed once at scheduler construction from the nominal window shape (200x200 -> 147,456). `WordAttemptBudget` itself refuses at construction if `max_hypotheses * single_word_probability > familywise_false_accept (1e-3)`. So the union bound is checked once, against the declaration, and the per-pass test is 'is this patch bigger than what we declared'.

*Where:* `holo2/src/holo2/solve/words.py:388-427`; `holo2/src/holo2/solve/place_model.py:250-292`; `holo2/src/holo2/solve/place_sched.py:226-229` · *dial:* live

**holo3.** `stage_a` computes `hypotheses = stage_a_hypotheses(samples.shape)` from the ACTUAL patch and refuses when `hypotheses * SINGLE_WORD_PROBABILITY > WORD_FALSE_ACCEPT (1e-3)`. The union bound is evaluated per pass against the patch that is really being swept. `stage_a_hypotheses`, `_slot_grid`, `_slot_phase_capacity`, `_centre_slot`, `_slot_phase_shape` and the errors-first `(errors, slot_index, rot_k, phase_index)` candidate order are all byte-for-byte the same functions.

*Where:* `holo3/plugins/words.py:12-17`; `holo3/plugins/words.py:181-187`; `holo3/plugins/words.py:285-296`

*Scheduler row / doc:* 07-placement.md:76-84

**Implementation delta.** Where the union bound is evaluated. holo2 pre-declares a nominal ceiling and asks 'is the patch within it'; holo3 asks the patch's own union bound directly, every pass. Same constant (1e-3), same `SINGLE_WORD_PROBABILITY` (a pure function of the BCH ball size and the counter width), same kernel, same candidate order. The two agree for every patch at or below the nominal window; they differ only for a patch LARGER than 200x200, which holo2 would refuse outright and holo3 would judge on its own bound. No such patch exists (windows are clipped to WINDOW_CELLS).

**Evidence status.** PINNED

**Evidence.**

- (holo3) SINGLE_WORD_PROBABILITY 1.7209511801042833e-09, recomputed from the BCH ball and the 18-bit counter; WORD_FALSE_ACCEPT 1e-3 frozen — *artefact:* holo3/tests/test_h3_plugins_placement.py:49-58, :44-46
- (holo3) stage_a refuses a fragment whose budget exceeds the word bar; the hypothesis count is a pure function of the shape — *artefact:* holo3/tests/test_h3_plugins_placement.py:384-394, :426-442
- (holo2) word staging 3,627 -> 794 ms per word-succeeding window (the same number as v1's) — *artefact:* ARTEFACTS.md:463 (§2.1 holo2 side)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — it is the same bound evaluated on the thing that is swept rather than on a declaration about it; nothing reachable differs.

**Notes.**

*Reader:* The centre/rest staging (two cost classes, `_centre_slot` as the historical most-interior slot) is carried unchanged on both sides; holo3 spells it in `place_sched.WORD_STAGE_OF`.

*Refuter (upheld):* *Corrections:* The word-staging 3,627 -> 794 ms row is ARTEFACTS.md:465, not :463.

*Reason:* Verified at HEAD: holo2 words.py:419-421 tests `stage_a_hypotheses(patch) > budget.max_hypotheses` against a ceiling declared once, with the union bound checked in `WordAttemptBudget.__post_init__` (place_model.py:275-280); holo3 words.py:289-292 evaluates `hypotheses * SINGLE_WORD_PROBABILITY > 1e-3` per pass. Same constants, same kernel, same errors-first order, and STAGE_A_MIN_VISIBLE_SITES=90 is carried identically (holo2 words.py:368, holo3 words.py:263).

---

### placement-15 — R5 lattice-seed reduction — one reciprocal lattice seed per (capture, level, region), from the best-supported source

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **N** · seeds: B27

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** What prior a window whose own spectrum is too small (or whose blind fit failed the geometric gates) fits against — so, whether it poses at all.

**holo2.** A durable record with a declared transition law: `seed_rank = (-support, window_id)`, smallest wins, strict improvement only, enforced at the wall with a `CommitRefusal`. The proposing job binds the seed key as its ONE read key, because an unbound read-modify-write turns a concurrent loser into a fatal refusal. Only an UNCONDITIONED measurement may be proposed (a seeded or zoom-refitted window measures the seed back and must not re-propose it — the anti-laundering rule).

*Where:* `holo2/src/holo2/solve/lattice_seed.py:1-58`; `holo2/src/holo2/solve/lattice_seed.py:121-166`; `holo2/src/holo2/solve/place_job.py:571-602` · *dial:* live

**holo3.** `lattice_seed_ordinal = (support_cells, -window_ordinal)` and `_adopts` keeps the strict maximum — the same total order with the window ORDINAL as tie-break instead of the window id string. There is no wall and no refusal: the fold simply declines a worse proposal and the job's write is discarded. The anti-laundering rule is carried: `fit_window_pose` sets `measured = None if conditioned`, and `_seed_fact` writes only when `fit.unconditioned_seed` is not None.

*Where:* `holo3/data.py:84-95`; `holo3/store.py:690-700`; `holo3/store.py:44-46`; `holo3/plugins/place.py:492-506`; `holo3/plugins/place.py:608-618`; `holo3/plugins/pose.py:450-516`

*Scheduler row / doc:* SCHEDULE.md key family `lattice_seed` (written by LatticeSeed, read by place)

**Implementation delta.** Same law, different enforcement point and tie-break. holo2 enforces at the commit wall and must bind the key to avoid a fatal `CommitRefusal` under concurrency; holo3 enforces in the single-writer fold, so a losing proposal is a no-op and no key binding is needed. Tie-break: holo2's ResourceKey string vs holo3's window ordinal — both are values, not schedules, but they can pick different windows at equal support. The proposal SET is schedule-dependent in the zoom-refit corner on both sides (a window firing before any seed exists refits blind and proposes; one firing after abstains) — holo2 states the narrowing explicitly, holo3 inherits it silently.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) MEASURED failure mode of the unbound version: the spine fixture died at four workers, standing 39,896 cells refusing 39,748, before the key was bound — *artefact:* holo2/src/holo2/solve/place_job.py:592-593 (the comment carrying the measurement)
- (holo3) seed_rank prefers more support then the window id — *artefact:* holo3/tests/test_h3_plugins_placement.py:307-319

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — the fold-time single writer removes the failure mode the key binding existed to prevent, and the order is the same total order.

**Notes.**

*Reader:* `place.seed_rank` / `place.seed_supersedes` still spell holo2's `(-support, window_id)` form and are used only by the test; production adoption goes through `data.lattice_seed_ordinal`. That is a second, unused spelling of the same order with a DIFFERENT tie-break (window id vs window ordinal) — worth flagging as a trap, not a defect.

*Refuter (upheld):* *Corrections:* None.

*Reason:* Verified at HEAD including the trap: `data.lattice_seed_ordinal` (data.py:93-94, `(support_cells, -window_ordinal)`, max wins) is the only production adopter (store.py:696-697), while `place.seed_rank`/`seed_supersedes` (place.py:492-506, `(-support, window_id)`, min wins) are referenced only by test_h3_plugins_placement.py:307-314 — two spellings, different tie-breaks, exactly as the row says.

---

### placement-16 — The seed wake — a pass that superseded the lattice seed wakes the region's dormant windows

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **N** · seeds: B28

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a window whose own fit refused ever gets a second chance.

**holo2.** `_seed_ping` reads the pass's own WRITES for a `LatticeSeedRecord` and wakes every not-ready slot of that (footing, region). It is called on EVERY settle path, before the two that leave the set, precisely because a wake conditioned on failure loses the wake that matters — a window a gap away whose own fit refused and which no ring ping reaches.

*Where:* `holo2/src/holo2/solve/place_sched.py:837-856`; `holo2/src/holo2/solve/place_sched.py:705-711` · *dial:* live

**holo3.** `(KEY_LATTICE_SEED, capture, level, region)` is the first declared read of every place worker; `_fold_lattice_seed` returns that key on adoption and `_touch` bumps the version of every subscriber, re-pushing it. The seed fact rides the writes on every exit path of `run_window_pass` — `_seed_fact` is attached to the pose_refused, insufficient_support and every refusal `_settled(...)` call as well as to an acceptance.

*Where:* `holo3/plugins/place_sched.py:205-209`; `holo3/store.py:690-700`; `holo3/engine.py:411-424`; `holo3/plugins/place.py:608-618`; `holo3/plugins/place.py:702`

*Scheduler row / doc:* SCHEDULE.md key family `lattice_seed`

**Implementation delta.** Mechanism only: holo2 pushes an explicit ping from the writer; holo3 declares the key as a read and lets the engine's inverted index fan out. Both fire on every path a seed can be written on, both reach exactly the region's windows, both are order-independent. holo3's wake also survives a dormancy check by construction (`dormant()` compares the bookmark version against the version at which dormancy was recorded, so any bump revives).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) no yield or cost number on either side for this channel — *artefact:* ARTEFACTS.md:405-478 (§2.1 lists no seed-ping measurement)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — same coverage, declared rather than pushed.

**Notes.**

*Reader:* Part of the broader wake-channel row (placement-17); kept separate because the seed channel is the ONLY thing that can revive a window whose own fit refused, and both trees argue that case explicitly.

*Refuter (upheld):* *Corrections:* 'rides the writes on every exit path' should read 'on every exit path AFTER the pose fit': the three pre-fit exits (place.py:688 cold_refused, :691 nothing_to_try, :696 insufficient_support-on-no-crop) carry no seed because no fit has run. Verified sites: :704, :707, :776, :790 and the acceptance.

*Reason:* holo2's explicit `_seed_ping` on every settle path and holo3's declared-read fan-out (place_sched.py:205-209 first key, store.py:696-700 returning it, engine.py:410-424 `_touch`) cover the same set; dormancy is version-relative so the wake always revives.

---

### placement-17 — Park / dormancy and the wake channels — what re-arms a window that has nothing left to try

**DIVERGED** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B32, B28

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether an unplaced window is ever looked at again, and how often.

**holo2.** Three channels and no others (stamped VERIFIED SUBSUMED, 2026-08-17): the RING ping from an accepted pose to its own-footing lattice neighbours plus the FINER-footing windows its extent covers; the DONOR direction of the same push; and the SEED ping. A dormant window (`tier()` returns None, `_enqueue` clears `ready`) waits for one of those. RF1 revisions ping NOBODY — the re-read path deliberately does not ping, with the measurement recorded (pinging there woke the subdivision arm's dormant parent for three useless passes).

*Where:* `holo2/src/holo2/solve/place_sched.py:895-900`; `holo2/src/holo2/solve/place_sched.py:817-835`; `holo2/src/holo2/solve/place_sched.py:837-856`; `holo2/src/holo2/solve/place_sched.py:738-747` · *dial:* live

**holo3.** A place worker declares: the region's lattice seed; the GLOBAL `KEY_LIVE_PAGES`; `KEY_POSE_AFFINE` for each of its eight ring-neighbour extents at EVERY level of the capture; and `KEY_POSE_AFFINE` for its own extent at every OTHER level. Any write that moves one of those bumps the worker's version and re-pushes it. Dormancy is soft: `dormant()` holds only while the bookmark version equals the version recorded at the refusal, so every one of those bumps revives the window. Crucially, `refine` and `revisit` write revised Placements, and a moved affine bumps `KEY_POSE_AFFINE` — so pose REVISIONS wake placement in holo3 where they ping nobody in holo2.

*Where:* `holo3/plugins/place_sched.py:205-221`; `holo3/plugins/place_sched.py:104-106`; `holo3/engine.py:411-424`; `holo3/store.py:623-688`

*Scheduler row / doc:* SCHEDULE.md key families `pose_affine`, `lattice_seed`, `live_pages` (all read by `place`)

**Implementation delta.** holo3's wake set is a strict superset. (a) The ring reaches every lane, both directions, where holo2's push goes only to finer footings; (b) the global live-pages key wakes every place worker whenever any page becomes live; (c) refine/revisit pose revisions wake placement, which holo2 deliberately suppressed; (d) an anchor's candidate id carries its pose generation (`f'pose/{level}/{ordinal}/g{generation}'`), so a revision mints a candidate the window's tried set does not hold and `stage_of` answers `ring` again. Consequence: holo3's offer supply grows with the run and the re-fire loop has no natural end short of exhaustion.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the cost side: one window fired 18 times against holo2's worst of 7; `ring` fires 2.7x per chain pose on sheet H (22,205 fires / 8,185 chain poses) and 1.4x on xerox-k — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:57-58, :443-449 (report named by ARTEFACTS.md:405-441)
- (holo3) the yield side: the same reach is what places the coarse lane at all — 28-80% of every lane-0 chain pose across four datasets — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:382-395
- (holo3) net effect on identical material: 155 vs 196 and 281 vs 397 unresolved windows, 112 vs 100 and 82 vs 56 certificates, wall 842 vs 1,370 s and 786 vs 1,206 s — *artefact:* ARTEFACTS.md:415-424 (§2.1)
- (holo2) PL6 stamped VERIFIED SUBSUMED: 'No gap found ... the three real wake channels (ring, donor, seed) and none else stand pinned' — no yield number — *artefact:* holo3/retirement_docs-2026-09/seeds/holo2-behaviour-ledger.md B32 (row list; the claim re-derived from holo2/src/holo2/solve/place_sched.py:817-856)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's reach and rule separately on bounding the re-offer supply. The head-to-head says the broader wake wins on certificates and on wall; the residue report's own recommendation R4 is to bound the supply without touching the reach (for example, stop minting a fresh candidate id for a pose whose affine moved less than the search box). That is a cost fix, and it must be null-proved on certificates before it lands.

**Notes.**

*Reader:* This row and placement-01 are two halves of one mechanism (what is offered, and what wakes you to ask again); they are separated because a ruling could keep one and change the other. holo2's own '18 vs 7' fire-count comparison is from the residue report, not from holo2's own measurement battery.

*Refuter (upheld):* *Corrections:* Add one honest boundary the row does not draw: holo3's WAKE set is narrower than its CONSULT set. `_place_reads` (place_sched.py:205-221) subscribes only to the eight ring extents at every level plus the window's own extent at other levels, while `anchors_of` consults the whole region at fire time — so a distant pose does not wake a window, it only changes what that window sees when something else wakes it. That is what makes 'strict superset of holo2's wake channels' true without making the two mechanisms the same thing.

*Reason:* All four claims re-derived at HEAD: the read set (place_sched.py:205-221), the generation-carrying candidate id (place_sched.py:71-72), the global KEY_LIVE_PAGES subscription (:209), and refine/revisit revisions bumping KEY_POSE_AFFINE (store.py:630-662). `_touch` skips retired workers only (engine.py:417).

*Second lens (final: DIVERGED):* Reader upheld; the refuter's added boundary is correct and I verified it - holo3's WAKE set (holo3/plugins/place_sched.py:205-221) is narrower than its CONSULT set (holo3/plugins/place_sched.py:62-75): a window subscribes only to its eight ring extents at every level plus its own extent at other levels, so a distant pose changes what it sees without waking it. Also confirmed: the candidate identity carries the pose generation (holo3/plugins/place_sched.py:71-72), so a revised pose mints an identity the tried set does not hold, and refine/revisit revisions do bump the pose key (holo3/store.py:655-660). Yield lens: certificate-deciding, on the same measured head-to-head as row placement-01 - the two rows are one mechanism seen from two sides and must be ruled together.

---

### placement-18 — The claim/settle flag protocol — commit-then-ping, test-and-clear-then-consult, single ownership

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **integrity** · ruling needed **N** · seeds: B33

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a wake can be lost, and whether one window can be worked twice at once.

**holo2.** `claim` clears `ready` and raises `in_flight` before the fire reads anything; `settle` runs after the commit and then pings. The three-interleaving proof is stated in full: either the ping finds the bit clear and sets it (the pass re-runs with the new pose visible), or the claim cleared a bit already set and the pass's own consult reads the pose directly. `peek`/`claim` both refuse an in-flight window.

*Where:* `holo2/src/holo2/solve/place_sched.py:55-79`; `holo2/src/holo2/solve/place_sched.py:599-625`; `holo2/src/holo2/solve/place_sched.py:662-676` · *dial:* live

**holo3.** The same law, spelled generically for all seventeen rows: `worker.version` is the one-bit wake, `tried_version` is the tried-set floor (identical inputs never re-run), `inflight`/`pending` is single ownership, `seat_seq` is the heap tombstone. `_merge` folds facts before re-pushing, so a wake raised during a fire is honoured by `pending`. Every job reads current truth at fire time; nothing is captured at wake time.

*Where:* `holo3/engine.py:298-326`; `holo3/engine.py:433-474`; `holo3/engine.py:476-509`; `holo3/descriptor.py:56-65`

*Scheduler row / doc:* SCHEDULE.md:374-390 ('How this matches v2': one-bit wakes, fire-time consult, the tried-set floor)

**Implementation delta.** One in-memory protocol per family (holo2) vs one generic protocol the engine owns for every plugin (holo3). Same three properties, same ordering; holo3 adds `tried_version` (a version equality check that skips a fire whose inputs have not moved), which holo2 spells as the tried set plus the ready bit. Nothing about which windows are attempted changes.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) --workers N is payload-byte-identical (the acceptance gate); certificate-SET identity across N is explicitly dropped because floors read fire-time live state — *artefact:* holo3/docs/PAGE-DOMAIN.md:110, :175-182; API.md:746-749

**Yield relevance.** integrity — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Filed as integrity rather than yield: it decides nothing about which hypotheses are tried, only that a wake is not lost. Included because it is the substrate rows 01/17 rest on.

*Refuter (upheld):* *Corrections:* None. One mechanism worth naming in the row since it is part of the same protocol: `_push_worker` drops the push when a queued worker's recomputed cost equals its seat cost (engine.py:309-311) — the version bump still stands, so no wake is lost, but the heap position is not refreshed.

*Reason:* engine.py:298-326/433-474/476-512 carry the three properties (one-bit wake, single ownership, fire-time consult) generically; `tried_version` is the extra input-equality skip the row names.

---

### placement-19 — What a failed placement pass writes

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **integrity** · ruling needed **N** · seeds: B34, B54

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a refusal leaves a durable trace that a later run must respect — and therefore what a resume re-tries.

**holo2.** A failed pass writes NOTHING durable: no sequence number, no journal entry, no spend row, no subscription. Readiness, the tried set, the stage memory and the priority are all in memory. A resume rebuilds the set (plans minus placed minus covered, all ready, tried empty) and re-tries at worst — waste, never wrongness. The only durable window record is the OUTCOME (placed-by, or retired-with-reason).

*Where:* `holo2/src/holo2/solve/place_job.py:85-93`; `holo2/src/holo2/solve/place_job.py:708-709`; `holo2/src/holo2/solve/place_sched.py:9-21` · *dial:* live

**holo3.** Every pass — accepted or refused — folds a `PlaceOutcome` fact carrying the tried candidates, the spent stage, the wide/cold bits and the outcome word, which `_fold_place_outcome` reduces into the in-memory `WindowState`. A refused pass may also fold a `LatticeSeed`. `PlaceOutcome` is explicitly EXCLUDED from the snapshot ('scheduling bookkeeping rather than a decision'), so nothing about readiness, tried sets or stage memory survives a resume.

*Where:* `holo3/plugins/place_sched.py:145-164`; `holo3/store.py:575-621`; `holo3/snapshot.py:12-17`; `holo3/snapshot.py:49-58`

*Scheduler row / doc:* SCHEDULE.md:374-390 ('Deliberately NOT carried: v2's journal/replay/lease machinery'); API.md:753-757

**Implementation delta.** In-run shape only. holo2 returns a `WorkResult` the scheduler folds directly; holo3 makes the same information a fact that flows through the same `_ingest` path as everything else and is then dropped at snapshot time. The durable law — a refusal leaves no trace, a resume re-tries — is identical. One asymmetry: holo3's snapshot DOES carry `data.Window`, so subdivided children survive a resume, where a resumed holo2 parent re-subdivides and the kernel hands back the same extents. Same extents either way.

**Evidence status.** PINNED

**Evidence.**

- (holo3) PlaceOutcome is named in the snapshot's exclusion list as 'scheduling bookkeeping rather than a decision'; the include list is CaptureSurvey, Window, LatticeSeed, Placement, CtxOutcome, PlaneField, PooledColorCtx, Certificate — *artefact:* holo3/snapshot.py:12-17, :49-58

**Yield relevance.** integrity — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* B54's 'hints are scheduling annotations, never facts' holds on both sides; holo3 keeps the law while making the annotation travel as a typed fact, which is what lets the single-writer fold own the reduction.

*Refuter (upheld):* *Corrections:* None.

*Reason:* PlaceOutcome is folded in memory (store.py:575-621) and is absent from snapshot.py's include list; the durable law (a refusal leaves no trace) holds on both sides, and the one asymmetry named (Window survives the snapshot, so children persist) is correct.

---

### placement-20 — The done gate — a window whose work is already certified is never posed, sampled or searched

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B35

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which windows are removed from the frontier before any pixel is read.

**holo2.** Two doors, both pose-free: admission exits a window whose supported extent is contained in the region's done projection, and the fire asks the same question again before any pixel ('the lazy covered-exit'). Both use `DoneProjection.covers`: every SUPPORTED cell of the extent already done; an unsupported window is not done, it is dead. The exit is permanent.

*Where:* `holo2/src/holo2/solve/place_sched.py:354-356`; `holo2/src/holo2/solve/place_job.py:611-618`; `holo2/src/holo2/solve/tilemap.py:740-747` · *dial:* live

**holo3.** ONE door: `place_retire_cause` is consulted by `engine._fill` before `prepare` at every pop, so a done window is retired one line before its pass would have been built and the pass carries no second copy of the test (the deleted copy is documented at place.py:672-681). The predicate is richer than holo2's: an UNPLACED window is judged pose-free on the same projection (`window_extent_done`), while a PLACED one is judged on its exact TILE REACH — every tile the window could still contribute evidence to must be certified in EVERY stream. The same gate is reused by `calibrate` (eligibility) and `revisit` (eligibility, ahead of both its branches).

*Where:* `holo3/plugins/place_sched.py:229-256`; `holo3/store.py:437-486`; `holo3/plugins/place.py:509-515`; `holo3/plugins/place.py:672-681`; `holo3/plugins/calibrate.py:723-727`; `holo3/plugins/revisit.py:104-114`

*Scheduler row / doc:* SCHEDULE.md `place` row's `retire`; docs/DONE-GEOMETRY.md §4.6 (the supported-extent law), cited in store.py:449-472

**Implementation delta.** holo2 gates only on the pose-free extent projection and only on the place family. holo3 keeps that for unplaced windows and adds a reach-based test for placed ones (window reach + evidence reach, AND across streams), and extends the same gate to calibrate and revisit. It is strictly more retiring on placed windows and identical on unplaced ones. holo3 also stamps the retire CAUSE on a `WindowRetired` event, separating a done-geometry suppression from an accepted pose in the record.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) realized gating rate e029 45/1,273 = 3.5%, xerox 42/1,324 = 3.2%; last-decile concentration 44/45 = 97.8% and 42/42 = 100%; ZERO at ppc 4/1 and 8/1 — *artefact:* ARTEFACTS.md:575-579 (§2.4)
- (v1) the simulated counterfactual: 719 of 1,479 committed placements = 48.6% pixel-gateable; gated windows minted zero certificates, provably; the two are NOT a ratio (48.6% is simulated, 3.2-3.5% realized) — *artefact:* ARTEFACTS.md:573, :577 (§2.4)
- (holo3) windows retired 4 (holo3) vs 0 (holo2) at 0.00 deg, 0 vs 0 at 0.80 deg on the crop head-to-head — *artefact:* ARTEFACTS.md:416 (§2.1)
- (holo3) no holo3 realized done-gating rate on a real sheet is recorded — *artefact:* ARTEFACTS.md:808 (G-09)

**Yield relevance.** decides-order-only — source: reader.

it removes only work that provably cannot mint (gated windows minted zero certificates in v1's census), so it decides cost; it becomes yield-relevant only through the work it frees for a preempted run

**Recommendation.** keep holo3's — a superset of holo2's gate with the same supported-extent law, and the one place holo3 retires where holo2 leaves a member dormant forever.

**Notes.**

*Reader:* No fragment/confetti done-geometry census exists on any side; the 48.6% is one intact dense sheet, the gate's favourable regime (ARTEFACTS.md:582). G-09 is the missing holo3 number.

*Refuter (upheld):* *Corrections:* ARTEFACTS cites: the v1 simulated counterfactual is :575 (not :573), the retired-windows table row is :418 (not :416), G-09 is :813 (not :808).

*Reason:* One door confirmed (engine.py:449-451 asks `descriptor.retire` before `prepare`); the placed/unplaced split and the AND-across-streams reach test are at store.py:449-486; calibrate.py:723-727 and revisit.py:104-114 do reuse it, as claimed.

---

### placement-21 — Done-pixel projection through the LIVE pose (latest, never the union)

**CARRIED-IDENTICAL** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B36

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Which capture cells count as spent, and therefore which windows the done gate can retire.

**holo2.** One pose per posed window — the LATEST committed, never the union. Each window's whole extent is mapped through that pose's inverse affine to page cells, floored to tiles, and marked where the tile grid is done AND the region supports the cell. Ownership-freeze winners and losers both contribute, being different windows. The union was measured to over-claim by +860 cells on e029 and +588 on Xerox for revisions carrying zero evidence.

*Where:* `holo2/src/holo2/solve/tilemap.py:749-825` · *dial:* live

**holo3.** `project_done(poses, grids, origin, pitch, shape, support)` is the same loop with the same arithmetic: inverse affine, `tile_of_cell` on the floor, `marked & support`. `_region_done_poses` supplies exactly one pose per placed window — the standing `Placement`, which `_adopts` keeps by `placement_ordinal` (a refine route with a larger basis and better quality supersedes). The projection is cached on `(n_poses, generations, n_certificates)`.

*Where:* `holo3/plugins/tiles.py (project_done)`; `holo3/store.py:400-435`

*Scheduler row / doc:* no design doc names it; store.py:449-472 states the supported-extent law it serves

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo2) the union over-claimed +860 done cells on e029 and +588 on Xerox for revisions carrying zero evidence; under live-pose the projection moved DOWN -3,996 (e029) / -1,449 (xerox) — *artefact:* holo3/retirement_docs-2026-09/seeds/holo2-behaviour-ledger.md B36 (row list); re-derived from holo2/src/holo2/solve/tilemap.py:754-789 which carries the numbers

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The honest limit holo2 states applies to holo3 unchanged and is not restated there: a boundary sliver can move in EITHER direction under a revision, it is UNMEASURED at this pitch, and `done_covered` is permanent — so coverage that later recedes is not re-offered. That is a comment-carry candidate for holo3's `project_done` / `place_retire_cause`.

*Refuter (upheld):* *Corrections:* Give the holo3 anchor a line number: holo3/plugins/tiles.py:583-609 (`project_done`) and store.py:400-435 (`_region_done_poses` + the `(n_poses, generations, n_certificates)` cache).

*Reason:* Same loop, same inverse affine, same `tile_of_cell` on the floor, same `marked & support`; exactly one pose per placed window, kept by `_adopts(..., placement_ordinal)`.

---

### placement-22 — What a calibration refusal costs — does the accepted pose survive it?

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B63

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a calibration-poor edge window keeps its address (and therefore its coverage, its anchor value and any later refinement) or loses it entirely.

**holo2.** `emit_placement` fits the window's calibration BEFORE writing the pose. If the fit refuses, the whole emission is dropped — the already-accepted pose included, because `pose` has no write of its own before the calibration gate. The window commits no pose at all; the coverage and any future refinement it would have fed are simply lost. Recorded as carried v1 behaviour, 'not stated anywhere until now', and unfixed: splitting calibration into its own provider is what would fix it.

*Where:* `holo2/src/holo2/solve/place_shared.py:840-895` · *dial:* live (as a cost)

**holo3.** The pose is a fact of its own (`Placement`, folded by the `place` row) and `calibrate` is a separate descriptor born BY it. A refused fit folds a `WindowEvidence` with `accepted=False` and a `refusal_reason`; the placement stands, keeps steering neighbours, keeps contributing done pixels and stays refinable. The `revisit` row (price 200) then re-fires the calibrate body for exactly those windows whenever certificates land in their reach or the region context moves.

*Where:* `holo3/plugins/place.py:804-850`; `holo3/plugins/calibrate.py:307-329`; `holo3/plugins/calibrate.py:753-766`; `holo3/plugins/revisit.py:47-55`; `holo3/plugins/revisit.py:104-124`

*Scheduler row / doc:* SCHEDULE.md rows `place` -> `calibrate` (born by Placement) and `revisit` (SCHEDULE.md:126-128, 'a calibration-refused window re-fires the calibrate body ... v1's M-pass as a subscription')

**Implementation delta.** A structural split, not a numeric one. holo2 emits pose and calibration as one atomic block, so a calibration refusal retracts the pose; holo3 makes them two rows joined by a fact, so a calibration refusal is a recoverable state with its own second-chance row. The calibration fit itself, its gates and its refusal reasons are the v1 carry on both sides. holo3 is strictly more permissive: it can never lose an accepted address to a calibration refusal.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) no yield number: the cost is recorded as a discovered consequence with no census of how many windows it drops — *artefact:* holo2/src/holo2/solve/place_shared.py:886-895 (the comment); no row in ARTEFACTS.md §2.1 or §2.2
- (holo3) the revisit row's own yield on real captures is recorded as 0 of 593 in the pre-supersession forensics — *artefact:* ARTEFACTS.md:447 (the plan's seed row for `revisit`; POST-FORENSICS 'revisit 0/593')

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — it fixes the exact loss holo2 documented and could not fix without the split holo3 already has.

**Notes.**

*Reader:* The `revisit 0/593` figure is from the superseded 2026-08-30 receiver and measures the row's TOTAL yield, not this clause; no artefact counts calibration-refused windows on either side. It is the cleanest example in this family of a divergence that is a fix rather than a risk.

*Refuter (upheld):* *Corrections:* The `revisit 593 fires / 0 route=refine poses` figure is ARTEFACTS.md:528-531 (quoting PARITY.md:443-448), NOT ARTEFACTS.md:447 (which is the native-vs-decimated addressing row). Re-pin before this reaches RULINGS.md.

*Reason:* holo2 place_shared.py:886-895 carries the atomic-drop comment verbatim ('This refusal drops the WHOLE emission, the already-accepted pose included'); holo3's split is real — Placement is folded by `place` and calibrate is a separate descriptor born by it, with revisit re-firing the calibrate body.

*Second lens (final: DIVERGED):* Upheld; the refuter's only correction is a citation re-pin, which I confirmed - the '593 revisit fires, zero adopted poses' figure is at holo3/retirement_docs-2026-09/ARTEFACTS.md:528-531 quoting holo3/conversion_docs/PARITY.md:443-448, not at :447. The structural claim reproduces exactly: holo2/src/holo2/solve/place_shared.py:886-892 says in its own comment that a calibration refusal 'drops the WHOLE emission, the already-accepted pose included', while holo3 writes the pose as a fact of its own (holo3/plugins/place.py:804-818) and calibration is a separate row born by it, re-fired for refused windows at holo3/plugins/revisit.py:47-55. Yield lens: certificate-deciding on both counts - a dropped pose loses the tiles under it and its value as an anchor for its neighbours - and unmeasured on either side.

---

### placement-23 — Quarantine's placement-side consumer — a contradicted pose is never offered as a seed, and a placement whose own words contradict a standing pose emits nothing

**ABSENT** · evidence **MEASURED** · yield **integrity** · ruling needed **Y** · seeds: B24, B25

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Which anchors may steer a window, and whether a mis-addressed placement can write evidence at all.

**holo2.** `emit_placement` runs a known-position word reduce over this fire's own pilot reads at its own (capture, footing) scope BEFORE any evidence is proposed. A contradiction condemns both sides: the decoded placement is committed as a pose BORN QUARANTINED (retained so the fact names a record, emitting nothing) and every standing pose asserting that position, plus all of its evidence, is marked. `consult` and `regional_seed` both skip a quarantined pose. Jurisdiction is UNCERTIFIED material only; `project_done` does not read the flag, so a condemnation moves zero done pixels. The window is retired.

*Where:* `holo2/src/holo2/solve/quarantine.py:1-56`; `holo2/src/holo2/solve/place_job.py:353-370`; `holo2/src/holo2/solve/place_job.py:424-431`; `holo2/src/holo2/solve/place_shared.py:895-915`; `holo2/src/holo2/solve/place_job.py:732-746` · *dial:* live

**holo3.** absent

*Where:* _(no path given)_

*Scheduler row / doc:* API.md:757-758 ('No quarantine — word trust is one-way (W5 rival bar at admission), so `known_position_words` and its consumer are not built')

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (v1) the zero-contradiction invariant: 70/70 regions, all 925 pilot tiles, ZERO contradictory reads across ~1,780 attempted known-position decodes — *artefact:* ARTEFACTS.md:751-752 (§2.11), citing docs/RECEIVE-DESIGN-EVIDENCE.md:492 — 'the plan's citation resolves exactly'
- (holo2) holo2's own W5 measurement is a WALL COST, not a yield: 'the wave costs ~1.7 s against a bypassed baseline, +2%'; yield is 'zero contradictions on every healthy fixture' — L8's own expected silence — *artefact:* ARTEFACTS.md:754-756 (§2.11)
- (holo3) campaign-wide certificate audit on the v1 stack: 0 wrong certificates in 69,066,304 audited cells; and zero wrong certificates on either side of the holo2/holo3 head-to-head — *artefact:* ARTEFACTS.md:512 (§2.2); ARTEFACTS.md:427-429 (§2.1)

**Yield relevance.** integrity — source: reader.

**Recommendation.** accept the loss, and record why. Grok's hypothesis that quarantine is holo2's only unique yield lever has no measured yield behind it on either side (ARTEFACTS.md:758 states this in terms). The mechanism's whole recorded content is an expected silence on ~1,780 reads and a +2% wall; holo3's admission-time whole-word rival bar (row placement-13) is the same one-way trust argument enforced before a pose exists rather than after. If the ruling goes the other way, the port is a real package: the known-position reduce, the condemnation write, the consult filter and the never-rehabilitate law.

**Notes.**

*Reader:* This is filed under placement because both of its consumers are placement-path (the consult filter and the emission verdict), even though the marking is an evidence-family write. The v1 1,780-read invariant belongs to e022 and is quoted by holo2 as its own expected silence, not measured by holo2.

*Refuter (upheld):* *Corrections:* The 69,066,304-cell audit row is ARTEFACTS.md:490, not :512; the §2.11 rows are :753-756 and the closing verdict :758.

*Reason:* Both holo2 consumers confirmed at HEAD (consult's `is_quarantined` filter at place_job.py:352-357 and regional_seed's at :429-430); holo3's `anchors_of` has no equivalent and API.md:758-759 declares the mechanism not built. ABSENT is right.

---

### placement-24 — Declared-vs-voted printed pitch — what a survey does when the sheet disagrees with the format row

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a capture contributes any windows at all, on what cell lattice, and whether the run continues.

**holo2.** One capture-wide vote over the components' pitch crops, snapped to the candidate set (which always includes the declared row's pitch). A tie between the top two counts votes None. `region_view` then builds the cell lattice from the VOTED pitch, whatever the row declares; a None vote makes every region of that capture UNSCHEDULABLE and `window_plans_for` skips it, while the rest of the run proceeds. The vote is recorded and never compared against the declaration.

*Where:* `holo2/src/holo2/capture/survey.py:484-510`; `holo2/src/holo2/capture/survey.py:87-126`; `holo2/src/holo2/solve/plans.py:108-125`; `holo2/src/holo2/solve/plans.py:150-155` · *dial:* live

**holo3.** `survey_capture` raises a ValueError naming the capture, the voted pitch and the declared row the moment `voted_pitch is not None and voted_pitch != declared_pitch_in` — the whole run aborts. A None vote leaves `pitch_px` None, `_fold_survey` returns before building any frame, and that capture contributes no windows (the rest of the run proceeds). Frames are always built from the DECLARED `row.pitch_in`, never from the vote.

*Where:* `holo3/plugins/survey.py:700-714`; `holo3/store.py:536-560`; `holo3/plugins/place.py:164-192`

*Scheduler row / doc:* API.md:759-763 (the C-7 behaviours list names 'declared-vs-voted pitch refusal' as one of the six surviving guards)

**Implementation delta.** On disagreement: holo2 silently places on the voted pitch; holo3 refuses the run. On a None vote both drop the capture's windows and continue. On agreement both behave identically, except that holo3 derives the lattice from the declared rational pitch and holo2 from the vote (the same value, by then). The vote's own arithmetic — candidate set, snapping, the largest-line tie-break, the median pitch_px — is the same carried code on both sides.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) no measured number on any of the three sides — only code behaviour — *artefact:* ARTEFACTS.md:806 (G-08); ARTEFACTS.md:476-478 (§2.1 closing line)
- (holo3) the refusal is pinned as behaviour — *artefact:* holo3/tests/test_h3_plugins_intake_survey.py:356 (`test_survey_capture_refuses_a_declared_pitch_the_sheet_contradicts`)
- (v1) a related, real incident on record: the e033 misdeclared-dpi case (survey said c4, spec said c2) produced a clean refusal — *artefact:* CLAUDE.md experiment index, e033 (context, not a measurement of this code path)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's. A voted pitch that disagrees with the declared row means the operator named the wrong format; placing on the vote produces addresses in a lattice the format authority does not describe, and every certificate under it would be minted against a geometry nobody declared. A loud refusal that names both numbers costs one re-invocation; the alternative silently forks the run. Record the narrowing: a MIXED-pitch platen (two sheets of different codings on one scan) is refusable in holo3 and partially readable in holo2 — no artefact says such a capture exists.

**Notes.**

*Reader:* The 'the rest of the run proceeds' behaviour on a None vote is the same on both sides, so the divergence is only in the disagreement branch. holo2's `_pitch_vote` docstring already records a deliberate divergence from v1 in the same area (a c3 sheet whose 2x line dominates votes c3 in holo2 and a 6-dot lattice in v1) — three trees, three answers on this question.

*Refuter (upheld):* *Corrections:* None.

*Reason:* holo3 survey.py:706-710 raises on `voted_pitch is not None and voted_pitch != declared_pitch_in`; holo2 plans.py:111-124 builds the lattice from `candidate.pitch_in_vote` and returns an unschedulable RegionView on a None vote. The tie-votes-None rule is holo2 survey.py:505-506. The named test exists at test_h3_plugins_intake_survey.py:356.

*Second lens (final: DIVERGED):* Upheld; no disagreement. Verified both sides at HEAD: holo3/plugins/survey.py:706-710 raises the moment the voted pitch is not None and differs from the declared row, aborting the run; holo2/src/holo2/solve/plans.py:117-122 builds the cell lattice from `candidate.pitch_in_vote` regardless of what the row declares, and returns an unschedulable region on a None vote. Yield lens: this is the most extreme certificate consequence in the family in both directions - holo3 certifies nothing at all on a disagreement, holo2 certifies against a lattice nobody declared. The pinning test exists (holo3/tests/test_h3_plugins_intake_survey.py:356); no measurement exists on any of the three trees.

---

### placement-25 — The default page domain — how many pages placement may address without an operator flag

**DIVERGED** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Which addresses the word route may admit, which pages a cold sweep may reach, how large the rival population is, and how strict every cold floor is.

**holo2.** `DEFAULT_PAGES = 1`. A run with no `--pages` and no state builds its row with one page, so `row.page_domain == (0,)`: the word route can only admit page 0, the cross-page rival population is empty, `cold_live` is the whole domain after the first pose and `cold_rest` is empty. A multi-page volume needs the operator to type the count. Cold tried-ids are flavourless (row placement-10).

*Where:* `holo2/src/holo2/cli.py:105`; `holo2/src/holo2/cli.py:283-306`; `holo2/src/holo2/format/registry_rows.py:201-203`; `holo2/src/holo2/solve/place_cold.py:116-133` · *dial:* live

**holo3.** `page_domain = range(row.max_pages)` by default (133 at 53x37, 2621 at 10x10, 5349 at 7x7); `--max-pages N` caps it and `--max-pages 1` is the null-control spelling of holo2's default. The LIVE set seeds `{0}` and grows when a committed address word opens a page. Word admission accepts any POSSIBLE page and the rival population is drawn from the possible set (so a marginal word cannot instantiate a phantom page). cold.live sweeps live at `len(live)`'s floor; cold.rest sweeps the complement at `len(rest)`'s floor, strictly last by price.

*Where:* `holo3/store.py:76-79`; `holo3/store.py:97`; `holo3/plugins/words.py:228-230`; `holo3/plugins/place.py:470-489`; `holo3/plugins/place_sched.py:186-191`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md v1.0 §1 (the ruling, :18-45), §5 (floors price the address space, :114-152), §6 (rest is last by price, :153-164), §9 (CLI, :183-187)

**Implementation delta.** The default domain, and four things that follow from it: (a) the word route can open a page holo2 could never address; (b) the rival population is O(row.max_pages) whole-word scores per admission instead of empty; (c) cold's floors are per-partition and the live floor is materially lower than the full-domain one (43 vs 54 at 53x37); (d) an accepted consequence, stated in the design: small-support windows never cold-place into non-live pages — they wait for a word to open the page and re-arm on the `KEY_LIVE_PAGES` wake. holo3 also builds the per-page scramble plane on first touch rather than stacking the whole domain at store init (~7.7 MiB/page at 53x37).

**Evidence status.** MEASURED

**Evidence.**

- (holo3) merge qualification 2026-09-02, e029: base (pre-merge) 1,357 certs / 2,517.3 cpu-s / 37,469 jobs; merged --pages 1 (the null) 1,360 / 2,557.4 / 37,945; merged at default 133 possible pages 1,356 / 1,639.8 / 23,855. All three VERIFIED e5021f8d..., 465,580 B. The default-domain arm is 35% cheaper in CPU and 36% fewer jobs for -1 certificate — *artefact:* ARTEFACTS.md:768 (§2.12)
- (holo3) a three-page sim: the word route opens pages 0 and 2, never allocates the gap page 1, and never builds its scramble plane — *artefact:* holo3/tests/test_h3_page_domain.py:100-118
- (holo3) sheet J, the only real fragment material: 357 -> 657 certificates across a default-domain run and a --pages 100 resume, close OPEN both times — *artefact:* ARTEFACTS.md:770 (§2.12)
- (v1) cold cost at single-page domain ~1-3 s vs 30-48 s per avoided cold at large domains; v1's `cold_first_max_pages` default is 1; the e029 --complete tail spent 160 priced colds over 133-page sweeps = 7,200 cold-progress steps to mint 2 certificates — *artefact:* ARTEFACTS.md:764-766 (§2.12)
- (holo2) no page-domain measurement exists — *artefact:* ARTEFACTS.md:767 (§2.12)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — it is the newest merged work on main, qualified against its own null on a real archived capture with a byte-exact close, and it is the only one of the three trees that can address a multi-page or fragment volume without the operator knowing the answer in advance.

**Notes.**

*Reader:* The -1 certificate at default domain is within the run-to-run variation the same table shows (1,357 / 1,360 / 1,356) and is not attributed. The fragment case is where this should pay and sheet J is the only real material; it closed neither time, so the fragment yield claim is still open.

*Refuter (upheld):* *Corrections:* None.

*Reason:* store.py:77-79 (`bound = row.max_pages if request.max_pages is None`) and PAGE-DOMAIN.md §1 :20-37 confirm the default and the five sub-rulings; the merge-qualification triple at ARTEFACTS.md:768 reproduces digit for digit (1,357/2,517.3/37,469; 1,360/2,557.4/37,945; 1,356/1,639.8/23,855, all VERIFIED e5021f8d..., 465,580 B).

*Second lens (final: DIVERGED):* Upheld; the strongest-evidenced row in the family and no disagreement between lenses. Verified the default at holo3/store.py:77-79 (the domain is the row's full possible page count unless the operator caps it) against holo2/src/holo2/cli.py:105 (`DEFAULT_PAGES = 1`), and the three consequences I could check directly: word admission filters on the possible set (holo3/plugins/place.py:474-476), the rival population is drawn from it (holo3/plugins/place.py:453-455), and each correlation flavour prices its own share (holo3/plugins/place_sched.py:186-189). The merge-qualification triple reproduces digit for digit at holo3/retirement_docs-2026-09/ARTEFACTS.md:768. Yield lens: certificate-deciding by construction - it changes which addresses may be admitted at all - and measured net-neutral on certificates with a 35% CPU saving on the one real capture tested.

---

### placement-26 — The dryness gate — an expensive placement tier may not start while anything cheaper is ready or in flight

**ABSENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **Y** · seeds: B02, B03

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether wide and cold passes run before the cheap ladder and the payload queue have drained.

**holo2.** Exactly three placement tiers carry `gated=True`: wide_consult, cold_live and cold_rest (resample at 200 is deliberately NOT gated). A gated job is refused while `min(in_play) < job.cost`, where in_play is the queue head cost plus every in-flight cost in both books — instantaneous global dryness, measured at the moment of the offer. The ruling it implements is quoted verbatim in the code: 'if we devolve into let's run a cold search on everything remaining before all payload is decoded, we are going to burn ourselves.'

*Where:* `holo2/src/holo2/engine/orchestrator.py:387-395`; `holo2/src/holo2/solve/place_tiers.py:163-176`; `holo2/src/holo2/solve/place_sched.py:596-597`; `holo2/src/holo2/core/work.py:388-392` · *dial:* live

**holo3.** No gate and no `gated` field on the descriptor. `_fill` pops the cheapest ready job; cold is ordered last by price (250/260, above refine 200 and swim 240). PAGE-DOMAIN.md:153-164 states the replacement argument: 'An idle worker takes the cheapest ready job; there is no second gate ... Price, not a dryness cliff, is what keeps that off the ordinary path.'

*Where:* `holo3/engine.py:433-474`; `holo3/descriptor.py:36-51`

*Scheduler row / doc:* SCHEDULE.md:374-390 ('Deliberately NOT carried: ... and the admission gate (a v2 artefact, deleted by ruling — pure cost order)')

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo3) 'holo2's dryness gate saves nothing on a run that drains.' Both arms go to full exhaustion and a gate that only defers cannot remove work. holo2's first cold fire sits at 44% / 36% of its placement stream, holo3's at 53% / 44% — holo3's plain price ladder already reproduces the ordering at --workers 1 — *artefact:* ARTEFACTS.md:744 (§2.10), backing scratch/sheetI-20260831/v2v3-placement-residue.md:41-47, :555-572
- (holo2) NO yield or cost number exists for the gate itself; it is described only as mechanism and carries no instrumentation. Its predecessor (the quiescent gate) WAS measured away and deleted — *artefact:* ARTEFACTS.md:742-743 (§2.10)
- (holo3) what the gate would have been worth on a run that stops early: e029 closed byte-exact having spent 206 s (42% of its placement) on 157 cold fires that produced ZERO poses; on all three archived whole-sheet runs the correlation tier committed zero poses in 5,332 fires while taking 13-65% of every placement second — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:409-425, :565-572 (report named by ARTEFACTS.md:405-441)

**Yield relevance.** decides-order-only — source: reader.

a deferral cannot change what is certified on a run that drains; it changes what has been paid for when a close preempts

**Recommendation.** accept the loss as written, with a costed follow-up rather than a port. The measured head-to-head refutes the gate's stated purpose at --workers 1, and holo3's price ladder reproduces its ordering. Two clauses survive un-tested: the in-flight term (which only bites at --workers > 1) and the early-close case (worth 206 s of provably useless cold on e029). The cheapest test is a paired non-`--complete` decode of the archived e029 capture at --workers 8 with and without a cheapest-in-flight admission clause — minutes on holo3, zero yield risk because a deferral cannot remove work.

**Notes.**

*Reader:* holo3's own spec (13-engine-diag-cli.md:110-115, per the residue report) still SAYS the tiers should be gated; the gate was deleted at d399ba3. That is a live doc-vs-code contradiction inside holo3 and belongs in the comment/doc phase whichever way the ruling goes.

*Refuter (upheld):* *Corrections:* ARTEFACTS §2.10 cites: the measured holo3-vs-holo2 row is :746 (not :744) and the 'no number exists' rows are :744-745 (not :742-743).

*Reason:* holo2 orchestrator.py:389-395 (`if job.gated: ... min(in_play) < job.cost`) and exactly three `gated=True` tiers at place_tiers.py:163-176; holo3 has no gated field and no gate. Every quoted residue number (44%/36% vs 53%/44%; 5,332 fires / 0 poses; e029's 206 s / 42.4% / 157 fires) reproduces at residue :415-425 and :555-572.

---

### placement-27 — The placement price table: six tiers, two rung terms, the child premium

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B04, B09, B10, B11

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** The order the ladder is walked in, and where placement sits against payload, refinement and the residue rows.

**holo2.** ring 40 < word_centre 60 < word_rest 80 < wide 120 < cold_live 140 < cold_rest 150; `LANE_COST_PER_RUNG = 2` (a tie-break that reorders within a tier and never across one, spanning 8 over a five-rung ladder); `COLD_COST_PER_RUNG = 20` (a real price, big enough that `rest(d) < live(d+1)`); `CHILD_PREMIUM = 5`, stacking with the rung term so 8+5=13 fits inside the smallest 20-point inter-tier gap. The refine tier sits at 200, above cold — and the comment states the honest limit: refine is OVERTAKEN by cold_rest from rung 3 and cold_live from rung 4.

*Where:* `holo2/src/holo2/solve/place_tiers.py:100-241`; `holo2/src/holo2/solve/place_slot.py:197-218`; `holo2/src/holo2/engine/recipe.py:214-249` · *dial:* live

**holo3.** ring 40 < word_centre 60 < word_rest 80 < wide 120 < cold_live 250 < cold_rest 260, with the SAME `LANE_COST_PER_RUNG = 2`, `COLD_COST_PER_RUNG = 20` and `CHILD_PREMIUM = 5`. `stage_price(stage, lane_depth, depth)` is the one expression that adds every term, exactly as `Slot.price` is. The cold pair moved from 140/150 to 250/260, which puts it above refine (200), revisit (200), uplift (210/220), tiles.local (220), planek (230) and swim (240) — every recovery row now precedes correlation at every rung.

*Where:* `holo3/plugins/place.py:41-52`; `holo3/plugins/place.py:85-89`; `holo3/plugins/place_sched.py:259-262`

*Scheduler row / doc:* SCHEDULE.md price ladder (the generated block); SCHEDULE.md:337-373 'The life of a decode'

**Implementation delta.** Four of the six tier prices and all three terms are identical; the cold pair is re-priced +110 so that correlation is unconditionally the last thing tried. In holo2 the same intent is expressed as a gate (row placement-26) with cold at 140/150 — where cold_rest at rung 3 (210) already undercuts refine at 200. holo3 replaces the gate with the price, which is why the price had to move. Cold's rung term of 20 still makes `rest(d) < live(d+1)` (270 < 290) and the child premium still fits inside every inter-tier gap.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the whole ladder frozen as a golden: {ring 40, word_centre 60, word_rest 80, wide 120, cold_live 250, cold_rest 260}, monotone in lane depth and child premium, with the two rung terms pinned separately — *artefact:* holo3/tests/test_h3_plugins_placement.py:90-106
- (holo3) the ordering the re-price buys, measured: holo2's first cold fire at 44%/36% of its placement stream, holo3's at 53%/44% — *artefact:* ARTEFACTS.md:744 (§2.10)
- (holo2) PROVISIONAL, all of it: 'these are ORDERS ratified by the ruling, not measured costs' — *artefact:* holo2/src/holo2/solve/place_tiers.py:32-34, :149-152

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's — the re-price is what makes the deleted gate unnecessary, and the measured first-cold-fire position confirms it reproduces the intended order.

**Notes.**

*Reader:* Both tables are declared PROVISIONAL by their own authors; neither side's numbers are measured costs. holo3's `tiles.local` at 73% of the sheet-I run's CPU on machine 2 is the one recorded pricing anomaly on a real sheet, and it is not in this family (ARTEFACTS.md:735).

*Refuter (upheld):* *Corrections:* None.

*Reason:* holo2 place_tiers.py:120/133/240 and holo3 place.py:41-52 carry the same three terms (2 / 20 / 5); the six tier prices differ only in the cold pair (140/150 -> 250/260), and SCHEDULE.md:73-82 confirms cold now sits above refine 200, revisit 200, uplift 210/220, planek 230 and swim 240.

---

### placement-28 — Placement takes no re-work / aging term

**CARRIED-IDENTICAL** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B13

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Whether a window that has been re-consulted many times gets more expensive, and so falls behind fresher work.

**holo2.** Structurally absent: the aging band `max(base, 90 + 5*(n-1))` is a function of a DESCRIPTOR's durable spend row, and a work SOURCE spends nothing at the wall, so the ordinal is undefined for placement. `Slot.price` reads no attempt count. Stated as structural rather than a carve-out.

*Where:* `holo2/src/holo2/engine/recipe.py:408-420`; `holo2/src/holo2/solve/place_tiers.py:65-69`; `holo2/src/holo2/solve/place_slot.py:197-218` · *dial:* live

**holo3.** The engine hands `attempts` and `last_cost` to every cost function as data; `_place_cost` ignores both and returns `stage_price(stage, lane_depth, depth)`. So placement re-fires at a flat price forever, exactly as in holo2 — but here it is a choice the row makes, not a structural impossibility, since the escalation door is open to it.

*Where:* `holo3/plugins/place_sched.py:259-262`; `holo3/engine.py:303-305`

*Scheduler row / doc:* SCHEDULE.md:24-34 (the escalation door: 'A row that wants its re-runs to grow more expensive prices them itself'); the `place` row carries no `*n` in the ladder

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the flat re-fire price is what lets the re-fire loop run: one window fired 18 times, `ring` fires 2.7x per chain pose on sheet H — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:270-282, :443-449
- (holo2) the aging band's measured value on the families that DO carry it: attempts 1,248 -> 760 (-39%), worst key 11,820 -> 4,260 iterations (-64%), certified 160 -> 160 unchanged, wall 96.1 -> 49.1 s, three volumes byte-exact both sides — *artefact:* ARTEFACTS.md:724 (§2.9)

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's behaviour and open the escalation door as a separate, gated line. This is the residue report's strongest and most yield-safe finding (R1): pricing a placement re-fire by its own ordinal cannot refuse anything — it only queues a much-repeated window behind fresher work — and holo2's aging measurement on other families shows the pattern preserves the certificate count exactly while cutting attempts by a third. It is a holo3-side improvement, not a port.

**Notes.**

*Reader:* The two trees agree today. The row is here because the CONSTRAINT differs: holo2 cannot price placement re-fires (no spend row), holo3 can and chooses not to. That makes it a candidate rather than a carry.

*Refuter (upheld):* *Corrections:* None.

*Reason:* holo3 `_place_cost` (place_sched.py:259-262) takes `attempts` and `last_cost` and ignores both; holo2's `Slot.price` (place_slot.py:197-218) has no attempt term. Behaviour is identical today, so CARRIED-IDENTICAL is the right word even though the constraint differs.

---

### placement-29 — Terminality short of success — which refusals remove a window from the frontier

**DIVERGED** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a refused window is gone for good or merely asleep, and therefore how much work the tail of a run does.

**holo2.** Only five reasons EXIT the set: placed, settled_placed, done_covered, outside_the_reading_set, and the two retiring sampler refusals (unschedulable_region, region_not_materialized). `insufficient_support` does NOT retire. Everything else leaves the window a dormant member (`tier()` returns None, `_enqueue` clears the ready bit) — terminal in practice only because the ping supply is bounded.

*Where:* `holo2/src/holo2/solve/place_sched.py:902-905`; `holo2/src/holo2/solve/place_shared.py:496-556`; `holo2/src/holo2/solve/place_sched.py:895-900` · *dial:* live

**holo3.** Three causes: `placed`, `exhausted` (set by `insufficient_support`, or by ladder exhaustion when subdivision produced no children) and `done_covered`. `insufficient_support` retires. A ladder-exhausted window that DOES have children never retires — `_place_repush` returns early — and stays a live, re-armable bookmark for the rest of the run. `RETIRE_UNKNOWN` exists only as the name the engine writes if it is ever asked for a cause while no clause stands, which cannot happen on the production path.

*Where:* `holo3/store.py:602-607`; `holo3/engine.py:564-576`; `holo3/plugins/place_sched.py:26-34`; `holo3/plugins/place_sched.py:229-256`; `holo3/engine.py:361-386`

*Scheduler row / doc:* SCHEDULE.md `place` row's `retire`; the three causes are stamped on `WindowRetired`

**Implementation delta.** Two opposite-signed differences. holo3 is MORE terminal on `insufficient_support` (a window with fewer than 30 supported sites under its pose leaves outright, where holo2 keeps it as a dormant member that a better lattice seed could revive). holo3 is LESS terminal on a subdivided parent: a parent whose own ladder is empty but whose children exist is never retired and remains subscribed to every wake channel for the whole run. holo2 has no equivalent — its parents go dormant like anything else. Both trees leave the majority of unresolved windows asleep rather than retired; the causes are just spelled differently.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) windows retired: 4 (holo3) vs 0 (holo2) at 0.00 deg; 0 vs 0 at 0.80 deg. holo2 retires NOTHING on either arm and every survivor is parked by dormancy — *artefact:* ARTEFACTS.md:416 (§2.1); scratch/sheetI-20260831/v2v3-placement-residue.md:214-247
- (holo3) unresolved windows left: 155 vs 196 and 281 vs 397 — holo3 leaves fewer of them and pays a smaller share of its placement budget for them (49.2% vs 60.2%, 62.5% vs 75.4%) — *artefact:* ARTEFACTS.md:415-419 (§2.1)

**Yield relevance.** decides-certificates — source: second lens (reader said: decides-order-only).

no certificate is lost either way — a dormant window can still be revived — but the never-retiring parent is a standing cost and the insufficient_support retirement forecloses a revival a better seed could have bought

**Recommendation.** keep holo3's `insufficient_support` retirement (a pose that reads fewer than 30 supported sites is a statement about how much paper is under the rectangle, and v1 deliberately does not subdivide on it either), and treat the never-retiring subdivided parent as a defect to fix rather than a behaviour to keep: it should retire once its children have settled and its own afterlife has been used. That is a holo3-side change, not a port.

**Notes.**

*Reader:* The never-retiring parent interacts with row placement-08: because the parent stays live it can still be armed by the afterlife, so retiring it needs the afterlife to have run first. Neither behaviour has a yield number.

*Refuter (upheld):* *Corrections:* The claim 'a ladder-exhausted parent WITH children never retires and stays re-armable for the rest of the run' is WRONG at HEAD and must be corrected — it is inherited from the residue report's §1g, not derived from the code. engine.py:564-575: the early return fires only on the pass that CREATES the children (`if not state.subdivided: subdivide; if state.children: return`). `state.subdivided` is then permanently True, so the next ladder-exhausted pass falls through to `state.retired = True` plus `_afterlife`. The true divergence is one deferred retirement, not an immortal parent — and the recommendation ('treat the never-retiring parent as a defect to fix') should be re-scoped to 'the parent survives one extra wake cycle', which may not be worth a change at all.

*Reason:* Both exit vocabularies re-derived (holo2 place_sched.py:895-905 dormancy vs `_exit`; holo3 place_sched.py:26-34 + 229-256 three causes). The insufficient_support half of the divergence stands exactly as written; the subdivided-parent half does not.

*Second lens (final: DIVERGED):* The first refuter is right on the half it challenges and I confirmed it at HEAD: holo3/engine.py:566-575 shows the early return fires only on the pass that CREATES the children (`if not state.subdivided`), and `state.subdivided` is then permanently true, so the next exhausted pass falls through to retirement plus the parent's second chance. The reader's 'never retires' is inherited from the residue report and is wrong. But I part company on the consequence: the refuter calls the remaining divergence 'one deferred retirement, maybe not worth a change', and the certificate-bearing half of this row is the OTHER one, which stands entirely - retiring on too-little-support is absorbing in holo3 (holo3/store.py:603-605; retired windows are skipped for waking at holo3/engine.py:417 and can never be re-staged, holo3/plugins/place_sched.py:107-109), while holo2 keeps such a window asleep and revivable. So: correct the parent half out of the row, keep the row DIVERGED on the support half, and re-scope the recommendation onto it.

---

### placement-30 — The reading set — which rungs of a capture's resolution ladder place at all

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B62

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** How many windows exist, and therefore how much of the sheet is addressed at each sampling density.

**holo2.** A declared run-level policy composed from the recipe: `READING_ALL` (the default since H4-LANES stage 2) admits every rung, `RECIPE_V1_FINEST` a named alternative that admits only the finest. A window on an excluded lane exits permanently with `outside_the_reading_set`. Two placement entries may not disagree, and the value rides the session identity so a run under a different reading is a different lineage.

*Where:* `holo2/src/holo2/engine/recipe.py:468-477`; `holo2/src/holo2/solve/place_sched.py:206-216`; `holo2/src/holo2/solve/place_sched.py:322-330`; `holo2/src/holo2/solve/place_shared.py:210-250` · *dial:* live (READING_ALL); RECIPE_V1_FINEST is a named config

**holo3.** No knob. `_fold_survey` builds a frame and a full window plan for EVERY level of every capture, and the lane depth is the level index (0 = coarsest). Every rung places, always; the coarse-before-fine ordering is entirely the +2-per-rung price term.

*Where:* `holo3/store.py:536-560`; `holo3/plugins/place.py:195-221`; `holo3/plugins/intake.py:88-118`

*Scheduler row / doc:* SCHEDULE.md `place` row (born by Window); MULTIRES-SPEC (the ladder)

**Implementation delta.** holo3 hard-wires holo2's default. The alternative (finest-only) is not expressible. Nothing about which windows are created differs from a holo2 run at its own default.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) the flip to `all` was measured: run-streaming 86 -> 87 certificates (the first cross-lane exclusivity), fragment class 4/12 -> 12/12 whole pre-subdivision; measured cross-lane exclusivity is bidirectional on every measured pair — *artefact:* ARTEFACTS.md:466 (§2.1 holo2 side)
- (holo2) the '~95% coarse' prior was WITHDRAWN as a synthetic artifact; real coarse shares are e029 K 55.4%, e023c HP 89-92%, and e029's coarse lane alone (1,075) could not close K = 1,356 — *artefact:* ARTEFACTS.md:468 (§2.1 holo2 side)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — the measured evidence says every rung earns its place, and the excluded alternative was an operator bound on spend, not on yield (the same class as the already-ruled `--mopup`/`--refine` bounds).

**Notes.**

*Reader:* Filed here rather than in the pricing family because it decides which windows EXIST, not merely their order.

*Refuter (upheld):* *Corrections:* ARTEFACTS cites: the run-streaming 86->87 row is :469 (not :466) and the withdrawn '~95% coarse' row is :471 (not :468).

*Reason:* store.py:544-559 builds a frame and a full window plan for every level of every capture with no policy knob anywhere; holo2's READING_ALL default and RECIPE_V1_FINEST alternative confirmed. holo3 hard-wires holo2's default, as claimed.

---

### placement-31 — The window layout lattice — flush-shifted starts, the 8-cell layout floor, and the zero-support drop

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Where every window sits on a region, and which candidate rectangles are never created.

**holo2.** `window_starts(n, size=200, step=160, minimum=8)`: refuse below 8 cells, one start for an axis shorter than a window, otherwise the regular step with the LAST start pulled in so the final window ends flush against the far edge — v1's own lattice, restored by the 2026-08-15 window-alignment ruling to stop wasting tiles. A window supported by zero cells is dropped, counted exactly on the region's support grid rather than estimated off a subsample. `E022_LAYOUT_MIN_WINDOW_CELLS = 8` is the layout floor; the 70-cell floor is the SUBDIVISION retry floor and was never a layout floor.

*Where:* `holo2/src/holo2/solve/geometry.py:519-590`; `holo2/src/holo2/solve/plans.py:128-172`; `holo2/src/holo2/solve/place_admission.py:69-72`; `holo2/src/holo2/solve/place_admission.py:285-296` · *dial:* live

**holo3.** `window_starts` is byte-identical (same signature, same four lines, same constants 200 / 160 / 8). `window_plan` walks the same enumeration, computes the exact supported-cell count on the frame's support grid and drops a zero-support window. `region_frame` derives the cell grid from the declared pitch and refuses a region with no supported cell at all.

*Where:* `holo3/lib/geometry.py:7-10`; `holo3/lib/geometry.py:68-79`; `holo3/plugins/place.py:195-221`; `holo3/plugins/place.py:146-192`

*Scheduler row / doc:* 07-placement.md (the layout constants); no SCHEDULE.md row

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) geometry window layout constants and starts match holo2 (a live cross-tree oracle in the slow lane) — *artefact:* holo3/tests/test_h3_drift_kernels.py:517 (`test_geometry_window_layout_constants_and_starts_match_holo2`); ARTEFACTS.md:775-783 (§2.13)
- (holo3) the window plan tiles the region on the declared lattice and skips windows with no support — *artefact:* holo3/tests/test_h3_plugins_placement.py:220-248

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* This is one of the very few placement rows with a live cross-tree oracle. Per ARTEFACTS.md:785-793 (G-02) that oracle uses `pytest.importorskip`, so it will silently SKIP rather than fail once holo2 is deleted — the re-pin is already in the plan's Phase 2.3 bill.

*Refuter (upheld):* *Corrections:* None.

*Reason:* holo3 lib/geometry.py:68-78 is byte-identical to holo2's window_starts with the same 200/160/8, and the cross-tree oracle really exists at test_h3_drift_kernels.py:517-523 (constants plus every n in the swept range). The importorskip caveat in the notes is correct.

---

## Evidence and ownership

19 rows; 5 carry a ruling.

**Reader's family notes.** Scope: the mechanisms that decide which readings of a printed cell exist, which of them owns the cell, how it is calibrated, and which tile attempts are therefore made. Placement, refinement, the done gate, the close and pricing are only touched where they cross into ownership.

Three findings worth the merge's attention. (1) On the two mechanisms holo2 measured hardest — the owner freeze key and window-scoped context binning — holo3 is not a port of holo2 at all: it reproduces v1 directly, and is pinned doing so by live cross-tree tests. holo2's halo blob, its published per-member losses and its parent-loss fallback are all machinery its tile-shaped evidence forced on it; holo3's evidence is window-shaped, so none of it is needed and none should be ported. (2) The two genuinely absent mechanisms — same-capture cross-rung pooling and within-capture window-overlap pooling — are absent from BOTH trees for the same lawful reason (readings of one capture are not independent), and only the first has a measured prize (+2 e029 tiles, 16 of 78 below-floor gap tiles). It deserves a port brief as an additive residue row, not a route. (3) Quarantine's evidence-exclusion half leaves with holo2 entirely and has no measured yield on any side.

Stale seed entries corrected here: B69's 'built-unused' is wrong of the current holo2 code (`capture/ingest.py:302` calls `derive_footing_rasters`, which writes into a `w+` memmap); holo2's own `docs/DESIGN.md:670-676` is the stale text behind it and should be listed with the archive's doc-vs-code contradictions.

What I could not verify: no artefact anywhere measures holo3's context bin -1 share, its calibration refusal count, or the yield of holo2's filled-plane evidence sampling against v1's raw-crop sampling. All three are marked in their rows. One holo3-side cleanup found in passing: `plugins/calibrate.py:590-615 freeze_owners` has no production caller.

**Refuter, head_checked:** 29d9a8d

**Refuter's family notes.** MECHANISMS NO ROW COVERS. (1) holo3's region context is a BEST-VALIDATION-LOSS-WINS standing fact, not last-write-wins: `region_ctx_ordinal` (holo3/data.py:156-161) plus `_adopts` (store.py:44-46) refuse a worse re-fit, and `_fold_ctx_outcome`'s third branch (store.py:769-778) then re-applies the STANDING offsets to accepted rows that lost them via `apply_standing_context` (plugins/calibrate.py:520-528). This is holo3's structural equivalent of holo2's F1 parent-loss fallback and it bounds the 'transient marginal read' window in rows 03/05/14 to one fire, whatever the re-fit decides. It deserves its own row or at minimum a named paragraph in row 03. (2) THE EVIDENCE_FIT / EVIDENCE_READ SPLIT is the family's quietest load-bearing mechanism: a ctx write moves only printed_llr / heldout_logloss / ctx_adopted, classified read_changed and not fit_changed (store.py:708-731), so ctx cannot re-arm itself while every tile row does re-fire. holo2 spends a paragraph excluding the adoption collection by hand (calibration.py:616-618) to get the same property. (3) `revisit`'s calibrate branch cannot change a label-driven calibration refusal (see row 16 correction) — the one recovery path the family relies on is provably inert except when the pose moves, which is a different row's trigger. (4) COLOUR OWNERSHIP IS NOT SYMMETRIC WITH K in the fold: `_fold_color_row` (store.py:813-830) has no `accepted` concept, so a colour row always joins the tile cover, where a K row joins only if accepted (store.py:743). No row states this. (5) holo2's record is NOT silent on local context: kparity/RULINGS.md:606-622 carries a measured 2026-08-28 crop-battery finding that region-local context has K-side yield (15 `neither` + 7-9 `still_missing_v2` tiles certify) plus a user ruling keeping window-with-halo as the default. This falsifies the sweeping 'the terms ... do not occur anywhere in holo2's design record' in row 19 (and ARTEFACTS.md:666-667) — 'plane fields' also occurs at holo2/docs/kparity/RULINGS.md:574 and CATCHUP-PLAN.md:393. The substance (none of these are BUILT in holo2) survives; the wording does not, and row 04 loses real supporting evidence by it.

CITATION HYGIENE. The reader's ARTEFACTS.md anchors 496-504, 447, 469-471, 601, 612-624, 666-671, 701-706 all resolve exactly at HEAD; :520 and :527 have shifted to :555 and :563 (the content matches verbatim), and :750-752 should be :753. Every underlying primary source I sampled (DIVERGENCE-LEDGER.md:65-67, MEASUREMENTS.md:978-994, PARITY.md:448-455, SCHEDULE.md:451-479 and :504-520, MEASUREMENTS-2026-08-31.md:18-19,26-27,54-56,188-196, INDEPENDENT-PLANES.md:1193-1195,1223,1659, RECEIVE-DESIGN-EVIDENCE.md six-scan bullet) says what the row says, with the two exceptions logged above (the 1.56-2.11% truncation in row 02 and the pose-vs-certificate misreading in row 16).

AFTER THIS PASS NO ROW IS CLASSIFIED DIVERGED. The rows that carry ruling_needed=true and would be DIVERGED under a stricter reading of the word are 05 (holo3 can destroy an accepted reading; holo2 structurally cannot), 08 (mixed-ladder unions run at a different point in the ladder), 10 and 15 (both genuinely ABSENT), and 16. All five already route to RULINGS.md under the plan's rule, so the word choice does not change what Germano sees. Row 11 is the one row whose classification I reject outright.

WHAT WOULD SETTLE THE TWO OPEN ONES. Row 05: the archived `CalibrateAdopted` streams answer it as the reader proposes, keyed on (capture, 'level/region/patch-N'); with the `_refused_outside` re-entry path added to the row, a non-zero count is a one-line quality gate in `_fold_evidence`, not a design question. Row 08: no run needed — the divergence is one line (`min` -> `max` in store.union_rung_ordinal) and any change shows in the regenerated ladder (`python -m holo3 schedule`), exactly as the reader says; the only correction is that the min ranges over all captures, not the covering ones.

**Second lens (yield) family notes.** Second lens = yield, at HEAD 29d9a8d. I reproduced every load-bearing claim in code before ruling; nothing below rests on the reader's or the refuter's reading alone. SCORECARD: the refuter is upheld on all seven rows, including the one reclassification (11), and I add material on four. WHERE I GO BEYOND BOTH. (1) Row 03's durable context write-back is not merely a shape difference - it is what puts the CORRECTED held-out loss into the ownership sort key, and that key is the family's largest measured effect (26-29/30 e029 + 27/48 xerox, holo2/docs/kparity/DIVERGENCE-LEDGER.md:65). Rows 01 and 03 are one mechanism seen twice and should cross-reference. (2) Row 01's residual delta is narrower than either write says: both trees now key on the corrected per-window loss, so the tie-break can only bind on a bit-identical float64 tie and is effectively unreachable; the delta that can actually move a cell is the loss PROVENANCE, where holo2 borrows a parent's number (0 of 255 re-read poses had their own) and holo3 always has the window's own. holo3 is the exact side. (3) Row 04's two negatives are both weaker than quoted: holo2's zero was measured on fixture pages where test_honesty pins certified == tiles_per_page, so the corpus had no margin (holo2/docs/MEASUREMENTS.md:983-985); and holo3's own SCHEDULE.md calls its existence proofs constructed stimuli, not yield measurements. The real-paper number (213 certificates, sheet I) carries the row, and it carries a confound - the local fit and a longer decode attempt move together. (4) Row 09's only genuine yield exposure is the volume that never finishes (killed at 60.51 and 60.24 GiB), and I checked and rejected upgrading the row for it: holo2's reading set gates placement admission only, not ladder building, and the archive explicitly refuses to attribute holo3's memory growth. Flag it under the memory row instead. YIELD TALLY for the seven: five decides-certificates (01, 03, 04, 12, 16), one decides-order-only (09), one nothing observable (11). Of the five, only 04 has a real-paper number; 12 is mechanistically capable and measured by nobody on either side; 01 and 03 inherit holo2's measurement of the same key; 16 is decides-certificates only through the pose-retention half, and in holo3's favour. FOUND IN PASSING, not part of any disagreement: colour evidence rows have no accepted concept in the fold (holo3/store.py:813-830), so they always join a tile's cover where a black-plane row joins only when accepted - safe today only because every emitted colour row carries a real loss, and stated nowhere. NOTHING I CHECKED CONTRADICTS A REFUTER CORRECTION; the two places I would soften the refuter are row 09 (its 'nothing decides differently' is true only for volumes that complete) and row 16 (the pitch, not only the pose, can move a re-offered calibration - but the pitch is also one of calibrate's own declared reads, so the no-op conclusion stands).


### evidence-ownership-01 — Per-cell owner freeze key — who owns a cell when several windows read it

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B40, B41

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Which covering window's calibrated reading of a payload cell reaches the decoder when two or more windows of the same capture and rung both observed it.

**holo2.** Candidate pieces are sorted by (window_loss, pose_id) and the first candidate to name a cell owns it; `take = piece.observed & ~owned` reads masks only, so the contested cell's own value never chooses. `window_loss` is the held-out log-loss the covering window's ctx pool PUBLISHED for that pose in its adopted fit's params blob; a pool with no adopted fit publishes nothing and every one of its pieces carries `inf`, ranking after all published siblings (a declared non-v1 tie class). `ctx_apply.window_loss` adds a fallback: a live pose with no published loss borrows the minimum published loss of its extent's other generation.

*Where:* `holo2/src/holo2/solve/payload.py:781-833`; `holo2/src/holo2/solve/payload.py:805-806`; `holo2/src/holo2/solve/payload.py:709-778`; `holo2/src/holo2/solve/ctx_apply.py:117-165` · *dial:* live

**holo3.** `freeze_page_owners` reorders the candidate rows by the caller's `order_keys` and then takes `np.unique(cell_key, return_index=True)`, so the first row in that order owns each cell. K order key is `(heldout_logloss, window extent tuple, region_index, 0)` (`k_candidates`); colour is the same shape off `ColorEvidenceRow.heldout_logloss`. The loss is the window's OWN recomputed held-out log-loss, written into the standing evidence by `_corrected_row` after the region context is applied (or the pre-context marginal loss where the region refused), so every accepted window always has one and the `inf` class of holo2 does not arise.

*Where:* `holo3/lib/owners.py:8-50`; `holo3/plugins/tiles.py:190-215`; `holo3/plugins/tiles.py:218-243`; `holo3/plugins/tiles.py:267-288`; `holo3/plugins/calibrate.py:507-517`

*Scheduler row / doc:* SCHEDULE.md 'The life of a decode' — 'cut this tile's cells from the covering windows' evidence, per-cell owner by held-out loss (Wave 2: tiles.freeze deleted)'

**Implementation delta.** Same first-wins-by-quality rule, three differences. (1) Loss provenance: holo2 reads a per-member loss PUBLISHED in the pool's adopted-fit params blob (needing `window_loss`'s parent fallback when a re-read has outrun the re-fit); holo3 reads the loss the window itself carries on its standing evidence row, recomputed at every fit — no publication, no fallback, no `inf` class. (2) Tie-break: holo2 `pose_id` (window key + page + affine); holo3 the window extent tuple then region_index then a plane tag. Both are content-derived and total; v1's own tie-break (the E022 patch ordinal) is rebuildable in neither. (3) holo2's declared non-v1 tie class — an adopted-pool region beats a refused-pool region regardless of quality — does not exist in holo3, which is closer to v1 here.

**Evidence status.** PINNED

**Evidence.**

- (holo3) `freeze_page_owners` and its order-key handling are compared live against v1's `holo.receive.payload_model` and reproduce it on the key-sorted list — *artefact:* holo3/tests/test_h3_drift_kernels.py:656 (test_owners_freeze_page_owners_matches_v1_payload_model), :665 (test_owners_order_keys_reproduce_v1_on_the_key_sorted_list)
- (holo2) pose-id ordering handed the lowest extent 90.3-94.1% of contests; the cost of that order is 27 e029 + 27 xerox certificates — *artefact:* ARTEFACTS.md:496 -> holo2/docs/kparity/DIVERGENCE-LEDGER.md:65
- (holo2) v1's key rule rescues 26-29 of 30 e029 + 27 of 48 xerox, 0 regressions in 1,910 + 1,882 — *artefact:* ARTEFACTS.md:497 -> DIVERGENCE-LEDGER.md:65; CATCHUP-PLAN.md:416
- (holo2) competing poses disagree on 9.15% / 14.30% of cells — *artefact:* ARTEFACTS.md:498 -> holo2/docs/CATCHUP-PLAN.md:423
- (holo2) 0 of 4 pools on either real sheet had a fit that had seen a re-read's pieces; 0 of 255 xerox re-read poses had a published window loss; 0 of 6 re-read windows had a loss for their live pose while 6 of 6 had one for the parent — *artefact:* ARTEFACTS.md:502 -> holo2/src/holo2/solve/calibration.py:594-595, ctx_apply.py:133-135

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* The three-way pin is against v1, not against holo2 — no oracle compares holo3's freeze to holo2's. That is the right direction: holo2's own record says v1's key is the one worth 26-29 e029 tiles. `plugins/calibrate.py:590-615 freeze_owners` (the OwnedPageEvidence producer) has NO production caller in holo3 — dead evidence-ownership surface, worth deleting or wiring at the comment/cleanup phase.

*Refuter (upheld):* *Corrections:* Three fixes. (1) DELTA POINT (2) IS WRONG: 'v1's own tie-break (the E022 patch ordinal) is rebuildable in neither' is false for holo3 — holo3 carries `patch_ordinal` on every Placement and every WindowEvidence (holo3/data.py:103,129; set from the window plan ordinal at holo3/plugins/place_sched.py:143,153 and holo3/plugins/place.py:809) and ALREADY orders the region context fit by it (holo3/plugins/calibrate.py:541). holo3 declines v1's tie-break, it cannot rebuild it. Say that instead, and note that holo3's ordinal is a plan index while v1's patch_id is arrival order (src/holo/receive/payload.py:138-140), so they are not the same numbering. (2) The fourth order-key element is the literal 0 in BOTH production key builders (holo3/plugins/tiles.py:214 and :241) — the 'plane tag' the row describes exists only in `freeze_owners` (holo3/plugins/calibrate.py:609), the function the row's own note says has no production caller. With a constant fourth element, a K row and a colour row that tie on (loss, extent, region) fall to stable-sort order (K first, via `first_index` in holo3/plugins/tiles.py:262-263), not to a plane. (3) EVIDENCE_STATUS PINNED OVERCLAIMS. holo3/tests/test_h3_drift_kernels.py:656 and :665 pin `freeze_page_owners` and its order-key HANDLING against v1's `payload_model.freeze_page_owners` on a pre-sorted list (the test's own keys are synthetic: `(float, tuple, "g")` at :668). Nothing pins the key CONTENT, which is the row's entire delta. Split it: PINNED for the one-owner-per-cell primitive, UNPROVEN for the key. Also worth stating: the `inf` branch at holo3/plugins/tiles.py:212-213 is unreachable in production only because `_fold_evidence` puts accepted windows alone in the tile cover (holo3/store.py:740-745) — the row asserts 'does not arise' without naming that guard.

*Reason:* Both sides' code says what the row says; the freeze rule, the loss provenance and the absence of an inf class are all reproducible at HEAD.

*Second lens (final: CARRIED-DIFFERENT):* REFUTER UPHELD ON ALL THREE CORRECTIONS; I reproduced each at HEAD 29d9a8d. (1) holo3 does carry the plan ordinal on both Placement and WindowEvidence (holo3/data.py:103,129) and already sorts the region context fit by it (holo3/plugins/calibrate.py:541), so 'rebuildable in neither' is false - holo3 declines v1's tie-break, it is not unable to rebuild it; note that holo3's ordinal is a plan index while v1's is arrival order (src/holo/receive/payload.py:138-140). (2) The fourth key element is the literal 0 in BOTH production builders (holo3/plugins/tiles.py:214 and :241); the plane tag exists only in holo3/plugins/calibrate.py:609, and I confirmed by grep that freeze_owners has no production caller (only holo3/API.md:114, tests and conversion_docs/verify cite it). A K row and a colour row tying on (loss, extent, region) therefore fall to stable-sort order, K first via first_index at holo3/plugins/tiles.py:262-263, not to a plane. (3) The evidence status overclaims: holo3/tests/test_h3_drift_kernels.py:668 builds SYNTHETIC keys ((float, tuple, 'g')) and :656 passes no keys at all, so the tests pin the one-owner-per-cell reduction and the honour-the-caller's-order contract, never the key CONTENT, which is the row's whole delta. Split PINNED (primitive) / UNPROVEN (key). YIELD LENS: decides-certificates, and it is the family's largest measured effect - holo2/docs/kparity/DIVERGENCE-LEDGER.md:65 measures the corrected-per-window-loss key at 26-29/30 e029 + 27/48 xerox with 0 regressions in 1,910+1,882, while a geometric key scored 0/30. Both trees now key on that loss, so the RESIDUAL delta is narrower than the row implies: the tie-break can only bind on an exact float64 tie between two accepted windows, which needs bit-identical held-out inputs and is effectively unreachable; the delta that can really move a cell is the LOSS PROVENANCE, where holo2 must borrow a parent's published loss (measured: 0 of 255 xerox re-read poses had a published loss for their live pose, 6 of 6 had one for the parent) and holo3 always has the window's own. holo3 is the exact side. Refuter's guard note is also right and I confirmed it: the inf branch at holo3/plugins/tiles.py:212-213 is unreachable only because holo3/store.py:743-745 admits a window to the tile cover solely when fact.accepted, and holo3/plugins/calibrate.py:327 only sets a loss on the accepted path.

---

### evidence-ownership-02 — Window-scoped context binning (the neighbour-count bin a cell is corrected in)

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B42

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which of the nine neighbour-count bins each payload cell is corrected in, and therefore how many cells are corrected at all (bin -1 takes no correction).

**holo2.** holo2's committed evidence is TILE-shaped (one 64x64 LLR + observed mask per (pose, tile)), so binning off a piece alone makes the tile's whole border ring structurally bin -1. F1 fixed that by making each piece carry a durable one-cell halo (577 B instead of 512 B): `window_context_bins` rebuilds a 66x66 frame from the halo, runs the carried kernel on it, and returns the tile interior's bins. `_freeze_with_owners` assembles the component's bin array cell by cell from each OWNER's halo; if any owning piece has no halo the whole component falls back to tile-scoped bins (a pre-F1 state).

*Where:* `holo2/src/holo2/solve/ctx_apply.py:176-203`; `holo2/src/holo2/solve/ctx_apply.py:206-250`; `holo2/src/holo2/solve/payload.py:781-833`; `holo2/src/holo2/solve/payload.py:425-438` · *dial:* live

**holo3.** holo3 never cuts to tiles before binning. `context_neighbour_counts` runs the 3x3 convolution over the WINDOW's own `page_cells_yx` array, so window scope is structural and no halo blob exists; a cell with fewer than eight present neighbours is bin -1, which is only the window's own outer ring. `apply_context_offsets` then clips the corrected LLR to +/-CTX_LLR_CLAMP exactly as the carried kernel does. The tile cut later takes whatever the owning window already carried, so a cell is corrected in its owner's window's bin by construction.

*Where:* `holo3/plugins/calibrate.py:378-402`; `holo3/plugins/calibrate.py:531-580`; `holo3/plugins/calibrate.py:520-528`; `holo3/plugins/calibrate.py:405-411`

*Scheduler row / doc:* SCHEDULE.md row `ctx` (subject = region, price 15 + rung)

**Implementation delta.** Same scope, opposite direction of travel. holo2 had to ADD a durable per-piece halo and a per-owner bin assembly to reach window scope from tile-shaped evidence; holo3's evidence is window-shaped from the start, so window scope needs no blob, no halo, no fallback path and no mixed-scope refusal. Both leave the window's own outer ring at bin -1 (v1's answer too). holo3 has no pre-F1-shaped state to degrade to.

**Evidence status.** PINNED

**Evidence.**

- (holo3) context primitives (neighbour counts, bins, offset application) compared live against v1 `holo.receive.detect` — *artefact:* holo3/tests/test_h3_drift_receiver.py:292 (test_calibrate_context_primitives_match_v1_detect)
- (holo2) context bin -1 share 6.15% tile-scoped vs 1.56% window-scoped; forgone offsets +/-2.3...+/-3.0 nats; standalone rescue 8/30 e029 + 1/48 xerox — *artefact:* ARTEFACTS.md:499 -> holo2/docs/kparity/RULINGS.md:521-522; DIVERGENCE-LEDGER.md:66

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* The 1.56% v1 figure and holo3's structural ring share are the same quantity for a 200x200 window (~2% of cells); no artefact measures holo3's bin -1 share directly, but the mechanism is identical to v1's and pinned.

*Refuter (upheld):* *Corrections:* Two number/claim fixes. (1) The measured window-scoped share is 1.56-2.11%, not 1.56% — holo2/docs/kparity/DIVERGENCE-LEDGER.md:66 reads '6.15% tile-scoped vs 1.56-2.11% window-scoped' (ARTEFACTS.md:499 already truncates it to the low end and the row inherited that). Quote the range: its upper end brackets the ~2.0% geometric ring share of a 200x200-cell window (796/40000, holo3/lib/geometry.py:8), which makes the row's own inference tighter rather than weaker. (2) 'bin -1 ... is only the window's own outer ring' is not exact: `context_neighbour_counts` (holo3/plugins/calibrate.py:396-402) requires all eight neighbours PRESENT, and the window's cell set is the coverage-audited `local_cells_yx` (holo3/plugins/place.py:802), so every cell adjacent to a support hole inside the window is bin -1 as well. Same as v1, so nothing changes in the verdict, but the row should not claim the share is purely geometric.

*Reason:* Window-scoped binning is structural in holo3 exactly as described, and the primitives are pinned against v1 by a test that exists at HEAD.

---

### evidence-ownership-03 — Region context calibration — where the additive-logit correction is applied

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B43

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether the nine-bin region correction reaches the decoder input, and on which cells; and whether the durable evidence a run stores is marginal or corrected.

**holo2.** The correction is applied at DECODE ASSEMBLY and never to stored evidence: a piece's durable LLR is always the marginal one. `_decoder_input` freezes one footing's owners, then `component_corrections` groups the owned cells by their owner's (footing, region) pool and applies each pool's adopted offsets to just those cells, BEFORE any cross-capture sum (so L2 holds by construction). With no adopted fit anywhere the INPUT OBJECT IS RETURNED UNCHANGED — the refused path's bit-for-bit identity claim.

*Where:* `holo2/src/holo2/solve/payload.py:651-707`; `holo2/src/holo2/solve/ctx_apply.py:206-250`; `holo2/src/holo2/solve/ctx_apply.py:253-289`; `holo2/src/holo2/solve/calibration.py:394-464` · *dial:* live

**holo3.** The `ctx` row fits the same nine bins over the region's accepted windows on the same search/held-out parity split with the same floors and the same held-out gate, then WRITES the corrected LLR back into each window's standing `WindowEvidence.printed_llr` (`ctx_adopted=True`) and recomputes that window's held-out loss on the corrected values. A refused fit returns the base rows untouched, so `printed_llr` stays the marginal array. `tiles._combine` then sums already-corrected per-capture cuts, so the correction still precedes every cross-capture sum.

*Where:* `holo3/plugins/calibrate.py:531-580`; `holo3/plugins/calibrate.py:507-517`; `holo3/plugins/calibrate.py:459-487`; `holo3/store.py:702-748`; `holo3/plugins/tiles.py:332-341`

*Scheduler row / doc:* SCHEDULE.md row `ctx` (subject = region; born by WindowEvidence; produces CtxOutcome)

**Implementation delta.** Fit inputs, floors and gate are the same (both are v1's `fit_context`); the durability of the OUTPUT differs. holo2 keeps evidence marginal forever and corrects a transient decoder input per attempt, masked per owner region. holo3 folds the correction into the standing evidence row, so every downstream reader — tiles.scan/union/retry, tiles.local, uplift, planek, swim, the diag panes — sees corrected LLRs, and the per-owner region masking is unnecessary because each window belongs to exactly one region. One ordering consequence with no holo2 analogue: a `calibrate` re-fire (resample after a pose revision) rewrites `printed_llr` back to the marginal value and bumps EVIDENCE_READ, so a payload attempt can fire once on the uncorrected read before the region re-fits; the same key re-fires when ctx lands, so the loss is an extra attempt, not a lost one.

**Evidence status.** PINNED

**Evidence.**

- (holo3) region context decision compared live against v1's `fit_context`, including the floor cascade and every named refusal reason — *artefact:* holo3/tests/test_h3_drift_receiver.py:343 (test_calibrate_region_context_decision_matches_v1_fit_context), :399, :414
- (holo3) physical cell ids (the one-label-one-weight rule) match v1 `_payload_context` — *artefact:* holo3/tests/test_h3_drift_receiver.py:425
- (holo2) CA2 spent 4 fits per sheet and every one was ADOPTED, zero refusals; held-out log-loss deltas -0.052 to -0.094 — *artefact:* ARTEFACTS.md:500 -> holo2/docs/CATCHUP-PLAN.md:473-476
- (v1) all 70 eligible region fits adopt on both footings; held-out pilot log loss 0.08147 -> 0.05698 (dec), 0.09690 -> 0.07480 (native); 2x2 factorial baseline/BP/context/combined 742 / 747 / 749 / 757 — *artefact:* ARTEFACTS.md:484-485 -> docs/RECEIVE-DESIGN-EVIDENCE.md:611, :612

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* No artefact measures the transient marginal-read window (a scan firing between a resample and the region re-fit). It is bounded — the re-fit re-fires the same attempt key and the codec gate is unchanged — so it costs CPU, not certificates. holo2's 'a refused fit is the same array object' identity has no holo3 counterpart to break: holo3 simply never writes a corrected array on the refused path.

*Refuter (upheld):* *Corrections:* Three fixes. (1) CITATION GAP: the holo3 side cites holo3/store.py:702-748 (`_fold_evidence`), but the ctx write path is `_fold_ctx_outcome` at holo3/store.py:750-785 — cite it. (2) THE REGION CTX IS NOT LAST-WRITE-WINS, and the row's 'transient marginal read' account is incomplete because of it: `region_ctx_ordinal` (holo3/data.py:156-161) ranks adopted fits by validation loss, `_adopts` requires strictly greater (holo3/store.py:44-46), so a WORSE re-fit does not adopt — and the `elif standing.adopted` branch (holo3/store.py:769-778) then re-applies the STANDING offsets to every accepted row that lost them, via `calibrate.apply_standing_context` (holo3/plugins/calibrate.py:520-528). That is holo3's structural answer to holo2's parent-loss fallback and no row in this family mentions it. The marginal window therefore closes on the next ctx fire whatever that fire decides, which strengthens the row's 'costs CPU, not certificates'. (3) EVIDENCE_STATUS: PINNED is right for the decision and the primitives (holo3/tests/test_h3_drift_receiver.py:343,399,414,425) and wrong for the delta the row states — no oracle compares holo2's per-attempt masked correction with holo3's durable one. Split PINNED (fit) / UNPROVEN (durability). Worth adding as the reason the durability is safe: `apply_region_context` recomputes the marginal from scores/knots/probs (holo3/plugins/calibrate.py:550-551), never from `printed_llr`, so repeated adoptions cannot compound.

*Reason:* The fit inputs, floors, gate and the write-back are as described; the delta (transient vs durable correction) is real and correctly identified.

*Second lens (final: CARRIED-DIFFERENT):* REFUTER UPHELD ON ALL THREE CORRECTIONS, verified in code. (1) The citation gap is real: the ctx write path is holo3/store.py:750-785 (_fold_ctx_outcome), not :702-748 (_fold_evidence). (2) The region context is best-validation-loss-wins, not last-write-wins: holo3/data.py:156-161 ranks (adopted, -validation_logloss) and holo3/store.py:44-46 requires strictly greater, so a worse or refused re-fit cannot displace an adopted standing one; and the elif standing.adopted branch at holo3/store.py:769-778 re-applies the standing offsets, via holo3/plugins/calibrate.py:520-528, to every accepted row that had lost them. I traced all three branches - adopts, held, and re-apply - and in each the marginal row is corrected again, so the reader's 'transient marginal read' window is provably bounded to one attempt whatever the re-fit decides. (3) The evidence status must split: holo3/tests/test_h3_drift_receiver.py:343,399,414,425 pin the fit DECISION and the cell-id law against v1, and nothing compares holo2's per-attempt masked correction against holo3's durable one. The refuter's safety note also checks out: apply_region_context recomputes the marginal from scores/knots/probs (holo3/plugins/calibrate.py:550-551, via calibration_llr), never from printed_llr, so repeated adoptions cannot compound. YIELD LENS: decides-certificates, and the strongest reason is one neither the reader nor the refuter states. The durable write-back recomputes the window's held-out loss on the CORRECTED values (holo3/plugins/calibrate.py:511-517), and that recomputed number is exactly what the ownership sort keys on in row 01 - the mechanism measured at 26-29/30. holo3 gets the corrected loss into the freeze structurally; holo2 had to build a publication channel plus a parent-loss fallback to reach the same number. The second yield channel is reach: in holo3 every residue row (retry, local, uplift, swim, planek) reads corrected LLRs, where holo2's equivalents would read marginal ones.

---

### evidence-ownership-04 — Certified-label enrichment of a context fit (CA1)

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B44

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether a context fit is trained on ~100 format-known sites per tile or on the ~4,096 cells that certified neighbours re-encode — i.e. how well the detector correction is estimated where certificates are dense.

**holo2.** `CertifiedLabelSource` overlays the committed certificate frontier (each certificate re-encoded to its exact printed 64x64 field, mint-once cached, with a fatal check against the format field at known sites) onto the cold-legal reference field, so `region_populations` harvests ~40x the labels. It is a constructor dial on `CtxCalibrationProvider(certified_labels=...)`, defaulted False, and NO production root passes True; when enriching, the fit additionally subscribes to COLLECTION_CERTIFIED so a new certificate re-arms it.

*Where:* `holo2/src/holo2/solve/certified_labels.py:221-244`; `holo2/src/holo2/solve/certified_labels.py:247-330`; `holo2/src/holo2/solve/calibration.py:794-806`; `holo2/src/holo2/solve/calibration.py:604-616` · *dial:* default-off

**holo3.** The standing `ctx` row is NOT enriched — its reads are the region's evidence-fit keys alone, so no certificate can ever move it. The enrichment exists instead as the K arm of `tiles.local`: over the windows covering ONE failed tile, `label_values` builds labels from the format's own word/filler bits PLUS the cargo cells that certified NEIGHBOURING tiles re-encode (`refine.certified_fields`, the refinement row's label provenance verbatim), fits the same nine-bin correction on them, and re-reads that one tile at 150 iterations. The fit is transient; nothing standing is touched. Eligibility requires at least one certified neighbour, and the row subscribes to every certificate in the neighbourhood.

*Where:* `holo3/plugins/local_ctx.py:207-227`; `holo3/plugins/local_ctx.py:258-277`; `holo3/plugins/local_ctx.py:540-560`; `holo3/plugins/local_ctx.py:571-585`; `holo3/plugins/calibrate.py:735-741`

*Scheduler row / doc:* SCHEDULE.md 'Additive residue rows' -> `tiles.local` (price 220), K arm; and the `ctx` row's reads (evidence only, no certificate subscription)

**Implementation delta.** Same label material (certificates re-encoded through the printed format; no provisional decision is ever a label), opposite scheduling. holo2 offers it as an always-on region-wide replacement for the label field, behind a dial nobody flips, so its cost is paid on every fit of every region whether or not a tile needs it. holo3 spends it only where a tile has already failed, over that tile's covering windows only, at price 220 behind every refinement row, transient and additive — the row can only add certificates, never move a standing fit. holo3 therefore also gets the enrichment on COLOUR (where the local object is the whole region head), which holo2 has no reader for at all.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) wall 81.6 -> 137.4 s = +68%; yield on this corpus: ZERO; mechanism ~100 label cells -> 4,096 (~40x); ruling DIALED, DEFAULT OFF; v1 never fed certified reconstructions to the ctx/PAVA channel, so this is a holo2 EXTENSION, not parity — *artefact:* ARTEFACTS.md:503 -> holo2/docs/MEASUREMENTS.md:978, :983, :980-981, :994, :987-990
- (holo3) EXISTENCE (K): without the row 45 certificates and the volume is LOST; with it 15 fires, 48 certificates and the volume comes back byte-exact, a strict superset, zero wrong. EXISTENCE (colour): without 285, with 291 — +6, every one a C-stream certificate on a patch tile — *artefact:* ARTEFACTS.md:701 -> holo3/SCHEDULE.md:436-489
- (holo3) sheet I on machine 2: tiles.local minted 213 certificates at 73% of the run's CPU; the four-run chain's later runs read 26 then 2 — *artefact:* ARTEFACTS.md:703 -> holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:30-31; experiments/034-sheet-i-full-readout.md:89-93
- (v1) E9: local vs page-global calibration is a sharp measured NEGATIVE — ZERO certificates, every arm, both lanes, all 21 e029 residue tiles; page-global beat every halo. What paid was dense certified labels, not locality — *artefact:* ARTEFACTS.md:488 -> docs/INDEPENDENT-PLANES.md:1223, :1178-1179
- (v1) shipped K head granularity: photometry per window, calibration per window, context page-global — and neither head has ever seen a certified payload cell as a label — *artefact:* ARTEFACTS.md:489 -> docs/INDEPENDENT-PLANES.md:1193-1195

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* holo3's placement of the enrichment answers the exact objection holo2's fold ruling raised (an arm that cannot prove universal non-regression does not run universally): it is additive, residue-only and certificate-gated. The known mispricing stands — K and colour arms both cost 220 while drawing CPU that differs 20-fold (SCHEDULE.md:508-520) — but that is an ordering defect, already flagged.

*Refuter (upheld):* *Corrections:* The holo2 side is incomplete in a way that matters to the recommendation. holo2's record is NOT silent on local context: holo2/docs/kparity/RULINGS.md:606-622 records a crop battery of 2026-08-28 with a MEASURED K-side yield for region-local context ('15 `neither` + 7-9 `still_missing_v2` tiles certify on crops, GT-checked') and a user ruling that window-with-halo stays the default decode path. That is the closest holo2 analogue to `tiles.local`, it measured POSITIVE, and it belongs in this row's evidence (it also falsifies row 19's 'the term does not occur anywhere in holo2's design record'). Second: the row quotes v1's E9 negative but does not adjudicate it. E9 is 'LOCAL calibration (0/21 certificates; page-global is the best arm)' (docs/INDEPENDENT-PLANES.md:1659, :1223) while holo3's row is BOTH local AND certified-label enriched, and pays 213 certificates on sheet I (holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:26-27). State which measurement governs and why (residue-only + additive + certificate-gated is the difference), or the RULINGS entry inherits a contradiction. Minor: certified_labels.py:221-244 is `FormatOnlyLabels` (the default), not the overlay — the overlay is :247-330 alone.

*Reason:* The dial, the default, the absence of a production root passing True, and both holo3 arms are exactly as stated; every number checks against its source.

*Second lens (final: CARRIED-DIFFERENT):* REFUTER UPHELD; both corrections verified and both strengthen the reader's recommendation rather than weakening it. (1) holo2's record is NOT silent: holo2/docs/kparity/RULINGS.md:606-622 records a 2026-08-28 crop battery in which region-local context certified 15 previously-dead tiles plus 7-9 more, GT-checked, and a user ruling that region-local calibration, if built, enters as an ADDITIVE toolbox arm over the completed residue, certificate-gated, never as a change to the default path. That is a verbatim description of holo3's tiles.local, so holo2's own record ratifies holo3's placement of the mechanism; the reader lost real supporting evidence by omitting it. (2) The E9 tension must be adjudicated, not quoted: docs/INDEPENDENT-PLANES.md:1218-1230 measures arms that REPLACE the marginal head's label population and finds page-global beats every local scope with 0/21 certificates, while :1659 records that dense certified labels DID pay page-wide. holo3's arm is neither of E9's arms - it leaves the standing fit alone and adds a transient enriched local fit plus a longer decode attempt on an already-failed tile. Both measurements govern their own question and they do not contradict. (3) Minor confirmed: certified_labels.py:221-244 is the format-only default, the overlay is :247-330. YIELD LENS: decides-certificates, and it is the only row in this set with a real-paper number - 213 certificates on sheet I, machine 2 (holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:25-26), plus a constructed existence proof in which the volume is LOST at 45 certificates without the row and byte-exact at 48 with it (holo3/SCHEDULE.md:446-461). TWO HONESTY MARKS I ADD. holo2's 'zero yield' is corpus-limited, not a negative: holo2/docs/MEASUREMENTS.md:983-985 says test_honesty pins certified == tiles_per_page on those pages, so the corpus left the arm no margin to buy anything. And holo3's arm changes two things at once - the local enriched fit and a 150-iteration re-read - so the 213 is not attributed to the label enrichment alone; SCHEDULE.md itself calls the existence proofs constructed stimuli and not yield measurements.

---

### evidence-ownership-05 — Two generations of a window's evidence, and which one decodes

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B39

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a reading taken through a superseded pose and a reading taken through the revised pose can both own cells in one decoder input, and what happens to the older reading.

**holo2.** Both generations stay committed and stay in the attempt's READ-SET (a read-set may grow but never shrink), and the reduction is applied one layer in, on the DECODER INPUT: per (tile, window) keep only the pieces of the newest pose that HAS pieces — the live pose if it holds any, else all of them. The ctx pool harvests the same reduction so one physical label is never pooled twice at half weight. `index.live_pose` alone is explicitly refused: it would delete 4,392 / 4,117 pieces on the archived states.

*Where:* `holo2/src/holo2/solve/generation.py:118-152`; `holo2/src/holo2/solve/payload.py:597-649`; `holo2/src/holo2/solve/payload.py:291-304`; `holo2/src/holo2/solve/calibration.py:290-320` · *dial:* live

**holo3.** There is exactly ONE `WindowEvidence` per window id. A pose revision re-fires `calibrate`, which takes the resample branch — same page cells, same reference values, new sampling through the revised pose — and the fold REPLACES the standing row (last write wins), bumping EVIDENCE_FIT and/or EVIDENCE_READ. There is no generation ledger, no superseded copy, and therefore no rule to state: a superseded read and a live read cannot meet in one freeze because the superseded read no longer exists.

*Where:* `holo3/store.py:702-748`; `holo3/plugins/calibrate.py:641-673`; `holo3/plugins/calibrate.py:349-356`

*Scheduler row / doc:* SCHEDULE.md 'How this matches v2' — one standing fact per subject; `calibrate` row (born by Placement, retire=never)

**Implementation delta.** holo2 keeps both readings and reduces at read time; holo3 keeps one and overwrites. The safety property (no mixed generations in one freeze) is structural in holo3 and derived in holo2. The cost of holo3's choice is that a re-read is unconditionally authoritative: there is no quality gate on the replacement, and if a resample at a revised pose lands `accepted=False` the fold writes the refusal, `_update_cover` removes the window from every tile cover it fed, and the earlier accepted reading is gone. Because `resample_window` reuses the standing cells and labels, the label-driven refusals (`search_class_starved`, `heldout_starved`) cannot newly fire; the one reachable new refusal is `outside_raster` when the revised pose pushes the window's points off the raster edge.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) MEASURED: 4,392 / 4,117 pieces hang on a non-live pose, so index.live_pose would delete them all — 'newest that HAS pieces' is the IDENTITY on every pre-F2a state — *artefact:* seeds/holo2-behaviour-ledger.md B39 -> holo2/src/holo2/solve/generation.py:1-52; ARTEFACTS.md:520 (re-read population 269/1,228 e029 and 272/1,282 xerox)
- (holo3) no artefact — no run record counts `outside_raster` calibrate refusals, and no artefact measures a lost accepted evidence row — *artefact:* no artefact

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's, after a zero-cost check: the archived holo3 event streams already carry one `CalibrateAdopted` event per calibrate fire with its refusal reason (`scratch/holo3-overnight-events/*.jsonl.xz`, `scratch/sheetI-20260831/events-*.jsonl.xz`). Count the fires that refused `outside_raster` on a window that had previously been accepted. That is an `xz -dc | jq` pass over existing files — no decode, minutes of wall — and if the count is zero on every archived volume the row closes as MEASURED. If it is non-zero, the fix is a one-line quality gate in `_fold_evidence` (do not let a refusal replace an acceptance), not a generation ledger.

**Notes.**

*Reader:* holo2's whole `generation.py` + halo + parent-loss-fallback apparatus exists only because holo2 commits evidence per (pose, tile) rather than per window. None of it needs porting; what needs deciding is whether holo3's last-write-wins fold wants a floor.

*Refuter (upheld):* *Corrections:* Two additions that bound the exposure the row asks Germano to rule on. (1) The proposed event pass is feasible but keys differently than the row implies: `CalibrateAdopted` (holo3/plugins/calibrate.py:618-624) carries capture id, the string 'level/region/patch-N', accepted and reason — NOT the window id or extent — so the jq pass must pair fires on (capture, level, region, patch_ordinal). (2) A refusal is not necessarily terminal: `_refused_outside` writes an empty `page_cells_yx` (holo3/plugins/calibrate.py:331-337), so the NEXT calibrate fire on that window takes the `calibrate_window` branch rather than the resample branch (holo3/plugins/calibrate.py:661-668) and can re-accept if the pose moves back. Say so — it turns the row from 'evidence can be lost forever' into 'evidence is lost until the pose moves again', which is a materially cheaper ruling. Keep ruling_needed=true; this is one of the two rows in the family whose behaviour genuinely differs in outcome.

*Reason:* holo2 keeps both generations and reduces at read time; holo3 has one WindowEvidence per window and the fold overwrites it, and the row's identification of `outside_raster` as the one newly reachable refusal is correct against the code.

---

### evidence-ownership-06 — Union minting rule — a cross-capture LLR sum exists only where two distinct captures share a footing

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B45

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether the multi-scan sum is attempted at all for a tile, and which readings it sums.

**holo2.** `union_tags` groups a tile's resident evidence by ppc and answers only those ppc values reached by two or more DISTINCT capture SHAs; a union descriptor exists only for those, so the illegal single-capture sum has no descriptor to run under. The union's read-set is every resident piece at that ppc, which makes the contributor set the attempt's identity: a new capture at that ppc is a new attempt, not a bookkeeping field.

*Where:* `holo2/src/holo2/solve/payload.py:251-270`; `holo2/src/holo2/solve/payload.py:306-314`; `holo2/src/holo2/solve/payload.py:955-962` · *dial:* live

**holo3.** `_union_subjects` mints a (page, ty, tx, ppc) subject only where `cover_lanes` finds two or more distinct capture ids covering the tile at that ppc; `prepare_union` re-checks with `arms_union` at fire time and refuses otherwise. `assemble_union` takes at most one level per capture (`level_of_ppc`), and `intake.assert_ascending_ladder` refuses a capture whose ladder repeats a ppc — 'one lane per ppc per capture is the union-pairing law' enforced at ingest. `_combine` then sums the per-capture cuts.

*Where:* `holo3/plugins/tiles.py:754-762`; `holo3/plugins/tiles.py:291-301`; `holo3/plugins/tiles.py:322-323`; `holo3/plugins/tiles.py:664-680`; `holo3/plugins/intake.py:106-114`; `holo3/store.py:350-360`

*Scheduler row / doc:* SCHEDULE.md row `tiles.union` (subject = tile at one ppc, price 20 + rung) · *dial:* live

**Implementation delta.** Identical law, differently enforced. holo2 makes it a property of the derivable descriptor set (no legal sum, no descriptor); holo3 makes it a property of the subject plus a fire-time re-check, and additionally forecloses the failure mode at ingest by refusing a non-strictly-ascending ppc ladder. holo3's contributor set is not the attempt's identity by read-set but by `component_signature` recorded on the AttemptFact.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) sheet H seven-capture max-stack: tiles.union minted 1,818 of 4,237 certificates = 43% — the largest union yield anywhere in the record — *artefact:* ARTEFACTS.md:621 -> scratch/holo3-overnight-events/sheetH-maxstack-report.json -> rows[3]
- (holo3) first cross-dpi union certificates on paper: 1,508 of the 4,307 four-capture harvest — *artefact:* ARTEFACTS.md:622 -> holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:18-19
- (holo2) same-DPI union A 39/64, B 36/64, joint 40/64 (delta +1); 101 union descriptors spent, 14 certificates minted by the union route. Cross-DPI union (1200 + 2400): 39 / 39 -> 41/64 — *artefact:* ARTEFACTS.md:619-620 -> holo2/docs/MEASUREMENTS.md:733-747, :775-784
- (v1) multiview certificate union: dec 757, native 752, shared 740, dec-only 17, native-only 12, union 769 — all 769 GT-correct; view correlation r = 0.9697 over 6,049,897 paired observations — *artefact:* ARTEFACTS.md:612-613 -> docs/RECEIVE-DESIGN-EVIDENCE.md:615, :616

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* holo3's ingest-time ladder refusal is strictly stronger than holo2's runtime rule and is the reason 'one component per capture' can be assumed by `_combine`, `lane_order` and `attempt_sets` without re-deriving it.

*Refuter (upheld):* *Corrections:* Small completeness point: holo3 enforces the law at THREE points, not two — `_union_subjects` re-derives the >=2-distinct-capture test at birth (holo3/plugins/tiles.py:754-762), `arms_union` re-checks at fire time (holo3/plugins/tiles.py:322-323 via :668), and `assert_ascending_ladder` forecloses the repeat-ppc case at ingest (holo3/plugins/intake.py:106-114). The row names the first and third and the fire-time check; naming all three is what supports its own claim that `_combine`, `lane_order` and `attempt_sets` may assume one component per capture.

*Reason:* The two-distinct-captures law, the ingest-time ladder refusal and the one-level-per-capture assembly are all present and cited correctly.

---

### evidence-ownership-07 — The heavy 150-iteration retry — what arms it, and against which baseline

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B46

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which failed tile readings get a second, ten-times-longer belief-propagation pass, and over exactly which evidence.

**holo2.** A retry exists per FOOTING, per work key, and only where that footing's own SCAN ran a decoder and failed — the tile record's `baselined` set, which only the SCAN branch writes (`baseline = FootingId(self.scope) if stage is SCAN else None`). A below-floor scan writes neither an attempt nor a baseline, because no decoder ran. A failed UNION arms nothing. The rule was written after the 2026-08-11 review found that deriving retries from a tile-level ATTEMPTED flag armed BP-150 on footings whose baseline never ran.

*Where:* `holo2/src/holo2/solve/payload.py:963-969`; `holo2/src/holo2/solve/payload.py:570-573`; `holo2/src/holo2/solve/payload.py:563-569`; `holo2/src/holo2/solve/payload.py:122-131` · *dial:* live

**holo3.** The subject is born FROM the failing AttemptFact: `arms_retry` requires stage in {scan, union}, outcome `attempted_failed`, and no standing certificate. The subject carries the origin stage and the lane, so a failed scan retries that capture+level and a failed union retries that ppc's whole component set. `prepare_retry` rebuilds the components at fire time, recomputes the baseline `attempt_key` and refuses unless the store still records that exact key as FAILED. Below-floor attempts carry outcome `below_attempt_floor` and never arm.

*Where:* `holo3/plugins/tiles.py:326-329`; `holo3/plugins/tiles.py:779-792`; `holo3/plugins/tiles.py:683-707`; `holo3/plugins/tiles.py:310-319`; `holo3/store.py:803-811`

*Scheduler row / doc:* SCHEDULE.md row `tiles.retry` (born by AttemptFact, price 20 + rung; 'retries are ordinary work, never gated by close readiness') · *dial:* live

**Implementation delta.** Three differences. (1) holo3 ALSO retries a failed UNION at 150 iterations; holo2 arms retries only off failed scans. (2) The arming fact: holo2 derives retries from a durable `baselined` set on the tile record; holo3 derives them from the failing attempt itself, which makes the 'retry with no baseline' defect structurally impossible rather than fixed. (3) The baseline identity: holo2 re-runs 'the same LDPC attempts on the same evidence' by construction (the read-set is the footing's pieces); holo3 re-derives the components and refuses if the recomputed `attempt_key` (address, stream, stage, iteration budget, component signature) is not on record as failed — so a retry whose evidence has moved refuses and a fresh scan re-arms a fresh retry.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) below-attempt-floor matches the v1 refusal and never arms retry (live cross-tree pin) — *artefact:* holo3/tests/test_h3_drift_receiver.py:990 (test_below_attempt_floor_matches_the_v1_refusal_and_never_arms_retry); k-tile attempts match the v1 attempt records at :928
- (holo3) retry attempts rose 4.7x on step 2, 0->2,694 on step 3, 3.7x on step 5, 23x on step 6 (1,028 -> 23,881), 1.9x on step 7 — minting 50 / 0 / 21 / 13 / 99 certificates — *artefact:* ARTEFACTS.md:624 -> holo3/conversion_docs/PARITY.md:449-455
- (holo2) per-attempt caps: scan 641 attempts mean 91.2/120, union 88 mean 120.0/120, retry150 386 mean 299.2/300; OR-5 measured retry150 mean 299.2 against a cap of 300 and minted nothing — *artefact:* ARTEFACTS.md:616 -> holo2/docs/MEASUREMENTS.md:1439-1441; seeds/holo2-behaviour-ledger.md B46
- (v1) e029 +5 certificates from selective BP150 (1940/1961); xerox K +1; c3-cmy7 +8; c2-cmy8 +80 — *artefact:* ARTEFACTS.md:88-107 -> experiments/029-holo-v1-first-print.md:74-76; experiments/032-xerox-altalink-payload-volumes.md:86-88, :102-103, :118-119

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* holo3's extra union-retry is a genuine addition of work, not a carry; it is priced in the payload band, so it competes with ordinary scans rather than with refinement. The 23x attempt growth on xerox c2-cmy7 for 13 certificates is the one recorded case where it is visibly expensive; that volume is also the one flagged for wall (3.1x) and memory (57.96 GiB) — see G-25.

*Refuter (upheld):* *Corrections:* One precision fix to delta (3): the retry subject's payload differs by origin — `_retry_subjects` (holo3/plugins/tiles.py:779-792) stores (capture_id, level_index) for a scan origin and (None, ppc) for a union origin, which is why `_retry_cost` (holo3/plugins/tiles.py:811-815) has two branches and why a union retry re-derives the whole component set at fire time. The row's 'retries that ppc's whole component set' is right but reads as if one subject shape covered both.

*Reason:* arms_retry, the union retry, the fire-time baseline recomputation and the below-floor exclusion are all exactly as described; the PARITY numbers are exact.

---

### evidence-ownership-08 — Payload lane premium — what a decode over a given rung costs

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B47

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** The order in which a tile's readings are decoded: coarse rungs before fine ones, and the whole payload family before every placement rung.

**holo2.** `lane_premium` = LANE_COST_PER_RUNG (2) times the DEEPEST rung the attempt will read: a scan or retry has one footing, a union takes the max over the ppc's resident footings, on the stated principle that 'an attempt is not cheaper than its dearest component'. An empty footing set answers 0. COST_PAYLOAD 20 + 2*4 = 28 < 40 keeps payload under every placement rung.

*Where:* `holo2/src/holo2/solve/payload.py:317-336`; `holo2/src/holo2/solve/payload.py:940-969` · *dial:* live

**holo3.** A scan pays 20 + 2 * its own level index. A union pays 20 + 2 * `union_rung_ordinal(ppc)`, which is the MINIMUM level index among the captures that hold that ppc. A retry inherits its origin's formula.

*Where:* `holo3/plugins/tiles.py:749-751`; `holo3/plugins/tiles.py:774-776`; `holo3/plugins/tiles.py:811-815`; `holo3/store.py:344-348`

*Scheduler row / doc:* SCHEDULE.md price ladder — tiles.scan / tiles.union / tiles.retry at 20, same-price peers; 'Coarse rungs pay +2 per rung less than fine ones'

**Implementation delta.** holo2 prices a union by its DEAREST component (max depth); holo3 prices it by its CHEAPEST (min level index across captures at that ppc). The two agree whenever every contributing capture has the same ladder — the ordinary single-dpi case — and diverge exactly on mixed-dpi stacks, where holo3 runs the union earlier than holo2's rule would. Both keep the whole payload family under the cheapest placement rung.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) first cross-dpi union certificates on paper: 1,508 of the 4,307 — so the mixed-ladder case where the two rules differ does occur in production — *artefact:* ARTEFACTS.md:622 -> holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:18-19
- (holo2) 'an attempt is not cheaper than its dearest component'; 20 + 2*4 == 28 < 40 keeps payload under every placement rung — *artefact:* seeds/holo2-behaviour-ledger.md B47 -> holo2/src/holo2/solve/payload.py:319-333

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's. The two rules agree on every single-dpi stack and differ only on mixed-dpi unions, where holo3 runs the union earlier than holo2's 'not cheaper than its dearest component' rule would. Both run every attempt eventually, so nothing is forgone; if the ordering is ever wanted holo2's way it is a one-line change from min to max in store.union_rung_ordinal, visible in the regenerated ladder (python -m holo3 schedule). No run needed.

**Notes.**

*Reader:* Ordering only: both schemes run every attempt eventually, and neither gates. Settling it costs nothing beyond a note, because the ladder is regenerated from the plugin literals (`python -m holo3 schedule`) and any change would show there.

*Refuter (upheld):* *Corrections:* Two corrections. (1) `union_rung_ordinal` minimises over EVERY capture in the store that holds that ppc (holo3/store.py:345-348), not over the captures covering this tile — so a capture that contributes nothing to the tile can still make its union cheap. That widens the divergence the row describes beyond mixed-dpi stacks to any store whose captures have different ladder lengths. (2) 'Both keep the whole payload family under the cheapest placement rung' is arithmetic, not a rule: payload is 20 + 2*level (holo3/plugins/tiles.py:67,751) and the cheapest placement rung is 40 (holo3/SCHEDULE.md:66), so the property fails at level index >= 10; nothing in either tree enforces it. Also note `min(indices)` raises on an empty sequence — only the subject-minting guarantees it is non-empty.

*Reason:* min-vs-max is real: holo2 prices a union by max footing depth (holo2/src/holo2/solve/payload.py:334-336), holo3 by `store.union_rung_ordinal` = min level index (holo3/store.py:344-348).

---

### evidence-ownership-09 — The reading set — which rungs of a capture's ladder are read at all

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B62

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** How many independent decoding trajectories a single scan produces: one (the finest rung) or the whole ladder.

**holo2.** `reading_set` is DATA on the placement recipe entry, so it forks the session lineage by value; `READING_ALL` (the whole ladder) is the default since H4-LANES stage 2 and `READING_FINEST` is a named config a run must declare. The scheduler consults it at admission and exits a window with EXIT_OUTSIDE_READING_SET when its rung is not read. `RecipeSpec.reading_set` refuses two placement entries that disagree.

*Where:* `holo2/src/holo2/engine/recipe.py:85-110`; `holo2/src/holo2/engine/recipe.py:468-477`; `holo2/src/holo2/engine/recipe.py:536-549`; `holo2/src/holo2/solve/place_sched.py:318-330` · *dial:* live (READING_ALL); RECIPE_V1_FINEST is a named config

**holo3.** `build_levels` derives the whole ppc ladder for every capture at ingest and materialises every level's planes; `_fold_survey` then builds a region frame and a window plan for EVERY level of EVERY capture. There is no reading-set concept, no dial and no CLI flag — all rungs always place, and a run that read one lane is not expressible.

*Where:* `holo3/plugins/intake.py:89-114`; `holo3/lib/decimate.py:27-42`; `holo3/store.py:536-560`; `holo3/cli.py:26-43`

*Scheduler row / doc:* SCHEDULE.md 'The life of a decode' — 'Every (region x rung) then births its window grid'

**Implementation delta.** Same effective policy (the whole ladder), different status. holo2 makes it declared data that forks the lineage and can be narrowed; holo3 hard-wires it, so the narrow policy is unsayable and no lineage records the choice. The practical consequence is on cost, not yield: holo3 has no cheap way to restrict a 4800 dpi colour volume whose full ladder is what drives the recorded memory ceilings.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) H4-LANES stage 2 flipped the default to `all`; measured cross-lane exclusivity is bidirectional on every measured pair; run-streaming/lanes 86 -> 87 certificates (first cross-lane exclusivity), fragment class 4/12 -> 12/12 — *artefact:* ARTEFACTS.md:469 -> holo2/docs/MEASUREMENTS.md:1785-1786, :1788; seeds/holo2-behaviour-ledger.md B62
- (holo2) '~95% coarse' WITHDRAWN — real shares e029 K 55.4%, e023c HP 89-92%; e029's coarse lane alone (1,075) could not close K=1,356 — *artefact:* ARTEFACTS.md:471 -> holo2/docs/H4-LANES-PLAN.md:31-35
- (v1) native == decimated at addressing: 362 vs 363 tiles, 361 common, ZERO contradictions; peak RSS 6.2 vs 13.5 GB — *artefact:* ARTEFACTS.md:447 -> docs/RECEIVE-DESIGN-EVIDENCE.md:491
- (holo3) post-change peaks: step 3 15.8 -> 39.4 GiB; step 4 breached at both workers 8 (60.51) and workers 6 (60.24) — worker count is not the driver — *artefact:* ARTEFACTS.md (§2.9 memory row) -> holo3/conversion_docs/PARITY.md:451

**Yield relevance.** decides-order-only — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's

**Notes.**

*Reader:* The yield policy is identical and is the one holo2 measured its way to. What leaves with holo2 is the ability to DECLARE a narrower reading — worth one line in the map as an operator affordance, and the natural place to reach for if the memory ceilings (G-25) are ever attacked from the scheduling side.

*Refuter (upheld):* *Corrections:* The row contradicts itself on yield relevance and should be fixed before it reaches RULINGS: the delta says 'Same effective policy ... The practical consequence is on cost, not yield' and the notes say 'The yield policy is identical', but `yield_relevance` is set to `decides-certificates`. Nothing decides differently — holo3 always reads the whole ladder. Downgrade to decides-order-only (or an operator-affordance note under the 'capabilities that leave with the tree' heading), otherwise the map reports a certificate risk where its own text says there is none.

*Reason:* holo2's reading set is recipe DATA with a live default of READING_ALL and a named narrow config (holo2/src/holo2/engine/recipe.py:109-110,477,611); holo3 ingests and plans every level with no flag (holo3/plugins/intake.py:189-196, holo3/store.py:536-560, holo3/cli.py:25-43).

*Second lens (final: CARRIED-DIFFERENT):* REFUTER UPHELD, with a caveat the refuter did not raise and which I checked before agreeing. The row is self-contradictory as written - its delta says 'the practical consequence is on cost, not yield' and its notes say 'the yield policy is identical', while yield_relevance reads decides-certificates. I verified the policies are identical: holo3/store.py:543-560 builds a region frame and a window plan for EVERY level of EVERY capture, holo3/plugins/intake.py:89-104 derives the whole ladder at ingest, and there is no flag in holo3/cli.py; holo2's default is READING_ALL (holo2/src/holo2/engine/recipe.py:477, :548). Since holo3 always reads a superset that is the same set, no tile on any volume that COMPLETES can decide differently. Downgrade to decides-order-only. THE CAVEAT I CHECKED AND REJECTED AS AN UPGRADE: one archived volume yields zero certificates because it never finishes - xerox c2-cmy8 was killed at the memory ceiling at both workers 8 (60.51 GiB) and workers 6 (60.24 GiB), 0.27 GiB apart, so the reduced-worker fallback cannot rescue it (holo3/conversion_docs/PARITY.md:443-455), and it has no post-change measurement at all. A narrower reading is the one lever holo2 had and holo3 does not, which is a genuine yield exposure. It still does not upgrade the row, for two reasons I confirmed: holo2's reading set gates PLACEMENT ADMISSION only (holo2/src/holo2/solve/place_shared.py:210-238, place_sched.py:323), not ladder materialisation, so it would save the per-window evidence at coarse rungs and not the rasters, an unquantified fraction; and ARTEFACTS.md G-25 states outright that holo3's memory growth is not attributable from the artefacts, so naming this as the fix would be a guess dressed as a finding. Record it as a flagged exposure under the memory row, not as a certificate risk in this one.

---

### evidence-ownership-10 — Same-capture cross-rung pooling — summing one scan's rungs on a below-floor tile

**ABSENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B64

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether a tile that no single rung of a single capture can support is ever attempted with all four rungs' readings summed.

**holo2.** Not built and refused by ruling J2-4 ('v1 has NO same-capture cross-rung sum — a lane IS a rung'). `union_tags` keys on distinct capture SHAs, so several rungs of one capture can never mint a union; `_decoder_input` partitions a union's pieces by footing and sums one owner per footing, but the footings only ever come from distinct captures.

*Where:* `holo2/src/holo2/solve/payload.py:251-270`; `holo2/src/holo2/solve/payload.py:651-695` · *dial:* named-not-built (refused)

**holo3.** Absent, and by the same structure. `assemble_union` takes exactly one level per capture at the subject's ppc; `tiles.local`'s subject carries a ppc and its lane set is `cover_lanes(page, ty, tx, ppc)`, one lane per capture; `tiles.retry` inherits its origin's lane. Nothing anywhere sums two levels of one capture.

*Where:* `holo3/plugins/tiles.py:291-301`; `holo3/plugins/tiles.py:332-341`; `holo3/plugins/local_ctx.py:413-462`

*Scheduler row / doc:* SCHEDULE.md rows tiles.scan / tiles.union / tiles.local — every one scoped to a single ppc

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo2) REFUSED by ruling J2-4; the forgone yield is measured: summing the four corrected components certifies +2 e029 tiles no single footing closes ((42,9), (22,1)) and reaches the below_floor class — 16 of 78 gap tiles at 1.2-4.9% cell error refused for coverage — *artefact:* ARTEFACTS.md:504 -> holo2/docs/kparity/DIVERGENCE-LEDGER.md:67; ranked H3 in scratch/holo2-catchup/detect/DETECTION-GAP.md:113
- (holo3) the pooling amplitude window, measured at the codec: pooled closes from noise amplitude 1.2, winner-take-all union from 1.6, a single view from 2.4 — on synthetic independent noise, which is true across captures and false within one — *artefact:* ARTEFACTS.md:623 -> holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:183-199
- (holo3) the informative-floor ceiling: below it no AttemptFact is emitted, so no rescue row is ever born — a rescue row can only help a tile the receiver still tries — *artefact:* ARTEFACTS.md:706 -> holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:57-60

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** archive for later port, as an ADDITIVE residue row rather than an ordinary route. The measured prize is small but real and is concentrated exactly where nothing else can reach: +2 e029 tiles that no single footing closes, and access to a below-floor class that today emits no AttemptFact at all and therefore arms no rescue row. The reason both trees refused it is sound and must be carried into any brief: the rungs of one capture are area averages of the SAME pixels, so their LLRs are not independent and their sum is not a lawful likelihood — the amplitude measurement above says so explicitly ('true across captures and false within one'). That argues against making it a peer of tiles.union and FOR making it a last-resort residue row in the toolbox pattern: transient, uncertified-tiles-only, priced above every refinement row, with the zero-wrong audit as its only bar. Cost of the port: one plugin of roughly local_ctx's shape, no format change, no state schema change; cost of qualifying it: the existing crop batteries plus a sim existence proof, no full-sheet decode.

**Notes.**

*Reader:* The below-floor door is the sharper half of the case and neither tree's record states it: today the coarse rungs' readings of a hard tile are discarded individually as below-floor, so the tile is never ATTEMPTED and no rescue row is born for it. A cross-rung sum is the only mechanism in either tree that could clear that floor from one capture.

*Refuter (upheld):* *Corrections:* Three corrections. (1) Say explicitly in the row that the mechanism is absent from BOTH trees so ABSENT is not read as a holo3 regression — the word is defensible only because holo2 NAMED and refused it. (2) The reason holo2 records is v1-parity, not independence: DIVERGENCE-LEDGER.md:67 reads 'v1 has NO cross-rung sum - a lane IS a rung'. The independence rationale is holo3's, and it is recorded — holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:191-196 says the within-capture form 'was parked on exactly that physics (correlated fit noise, the regime where F1 o F6 measured equal-weight combining losing)'. Attribute each reason to the tree that holds it. (3) The port brief need not be designed from scratch: DIVERGENCE-LEDGER.md:67 already carries holo2's costed fix shape (a `ROUTE_POOL` capture-scoped route, equal weights, `_decoder_input`'s union branch verbatim, residue-only minting, priced COST_PAYLOAD + lane_premium over the deepest rung, k_eff floor unchanged). Cite it.

*Reason:* Absent from holo3 by structure (one level per capture in assemble_union / one lane per plan in local_ctx / retry inherits its origin), refused in holo2 by ruling J2-4, and the +2 e029 tiles and the 16-of-78 below-floor class are verbatim in holo2/docs/kparity/DIVERGENCE-LEDGER.md:67.

---

### evidence-ownership-11 — Within-capture window-overlap pooling — the readings the owner freeze throws away

**CARRIED-IDENTICAL** · evidence **MEASURED** · yield **nothing observable** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader ABSENT → refuter reclassified to CARRIED-IDENTICAL → second lens CARRIED-IDENTICAL.

**What it decides.** Whether the second, third and later windows that also read a cell contribute anything, or are discarded by the freeze.

**holo2.** Discarded. One owner per cell per (capture, footing): the best-calibrated window takes the cell and every other covering window's reading of it is dropped. The docstring is explicit that the per-cell form exists so a partially-observed piece falls through to the next pose, not so readings combine.

*Where:* `holo2/src/holo2/solve/payload.py:781-833`; `holo2/src/holo2/solve/payload.py:709-778` · *dial:* live

**holo3.** Discarded the same way: `np.unique(..., return_index=True)` over the quality-ordered rows keeps exactly one row per cell. The one place holo3 goes further is `tiles.local.attempt_sets`, which after the union attempt re-reads the residue tile once per LANE — but lanes are captures, not overlapping windows, so window overlap is still discarded.

*Where:* `holo3/lib/owners.py:36-48`; `holo3/plugins/tiles.py:267-288`; `holo3/plugins/local_ctx.py:433-462`

*Scheduler row / doc:* SCHEDULE.md 'The life of a decode' — 'per-cell owner by held-out loss'

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the only discarded evidence is WITHIN-capture window overlap (108 of 138 cover entries on the mixed sim had 2-9 covering windows) — *artefact:* ARTEFACTS.md:623 -> holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:183-199
- (holo2) competing poses disagree on 9.15% / 14.30% of cells; 30.9% of piece loads own no cell on the archived e029 store — *artefact:* ARTEFACTS.md:498, :501 -> holo2/docs/CATCHUP-PLAN.md:423; holo2/src/holo2/solve/payload.py:412
- (v1) campaign-wide certificate audit: 0 wrong certificates in 69,066,304 audited cells — *artefact:* ARTEFACTS.md:490 -> docs/COLOR-UPLIFT-MEASUREMENTS.md:3029

**Yield relevance.** nothing observable — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's (= holo2's = v1's). The same independence argument as row 10 applies with more force: two overlapping windows of one capture read the SAME pixels through two poses, so summing them double-counts. The measured fact that they disagree on 9-14% of cells is a statement about pose quality, which is what the freeze key already adjudicates, not about extra information. Record it in the map as a deliberate discard with its measured size (2-9 covering windows on most cover entries), so that a future 'why not pool the overlap' question has an answer with a number attached.

**Notes.**

*Reader:* Named by no seed row; found by reading both freezes. It is the mechanism holo3's own premise correction singles out as the ONLY evidence the receiver throws away, which makes it worth one explicit map row even though the recommendation is to change nothing.

*Refuter (reclassified):* *Corrections:* Reclassify ABSENT -> CARRIED-IDENTICAL and set ruling_needed=false. The row's own holo2 field says 'Discarded' and its recommendation says 'keep holo3's (= holo2's = v1's)', which is the definition of a carry, not an absence. The pin exists and should be named: holo3/tests/test_h3_drift_kernels.py:656 (`test_owners_freeze_page_owners_matches_v1_payload_model`) pins the reduction against v1's `payload_model.freeze_page_owners`; holo2's is holo2/src/holo2/solve/payload.py:805-830 (`take = piece.observed & ~owned`). Everything else in the row is worth keeping verbatim — the 108-of-138 cover-entry figure and the discard rationale are exact (holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:188-196) and are the answer to a future 'why not pool the overlap'. Best home is a sub-note under row 01, which already owns the freeze; if it stays a standalone row it must not be an ABSENT one.

*Reason:* Nothing is absent from holo3 here — holo2, holo3 and v1 all discard the overlap by the same one-owner-per-cell rule, so ABSENT is the wrong word and would put a non-divergence in front of Germano as a loss.

*Second lens (final: CARRIED-IDENTICAL):* REFUTER UPHELD; I reject the reader's ABSENT outright, for the same reason and one more. The mechanism is discarded by all three trees under the same rule - holo3/lib/owners.py:36-48 takes np.unique(keys, return_index=True) over quality-ordered rows, holo2/src/holo2/solve/payload.py:805-830 does take = piece.observed & ~owned, and v1's own docstring at src/holo/receive/payload.py:121 says 'Freeze one deterministic owner per payload cell; retain all windows'. In a holo2-to-holo3 map, ABSENT means present in holo2 and gone in holo3; here it is present in neither, so the label would put a non-difference in front of the reader as a loss. The row's own holo2 field says 'Discarded' and its recommendation says 'keep holo3's (= holo2's = v1's)', which is the definition of a carry. Reclassify to CARRIED-IDENTICAL and drop the ruling flag. YIELD LENS: nothing observable - there is no code difference between the trees on this mechanism, so it cannot change which tiles certify on the archived corpus. The unbuilt pooling could change certificates if someone built it, but that is a separate line of inquiry, not a conversion delta, and it must not be counted as one. TWO NUMBERS TO KEEP, both verified: 108 of 138 tile-cover entries on the mixed sim had 2-9 covering windows (holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:188-190), and the same parked line measured the pooling amplitude window at the codec - pooled closes from noise amplitude 1.2, winner-take-all union from 1.6, a single view from 2.4, on SYNTHETIC INDEPENDENT noise, 'which is true across captures and false within one' (:191-196). That second number is the physics answer to 'why not pool the overlap' and the reader did not cite it; it is the same reason equal-weight multi-scan combining lost to best-single before the detector de-correlated it on paper.

---

### evidence-ownership-12 — Where the pixels an evidence reading is taken from come from — prepared region planes vs per-window crops

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** The luma every payload cell's score is read off: whether unsupported pixels are replaced by the platen backing before the aperture, and how much memory a fire holds.

**holo2.** One PreparedRegion per (capture, region, footing): three float32 planes — filled (every unsupported pixel replaced by the platen backing), filtered (that image under one box aperture) and support — built streaming into files and mapped read-only, 12 bytes per region pixel. Every window read, address and payload alike, is an order-1 `map_coordinates` into `region.filtered` with `cval=region.backing`, plus a coverage read off `region.support` with a >0.85 per-cell gate. The design record says why: rebuilding v1's `prepare_region` per fire cost ~8 GB per array on the real sheet and SIGKILLed workers 4 and 8.

*Where:* `holo2/src/holo2/solve/prepared.py:1-100`; `holo2/src/holo2/solve/prepared.py:356-395`; `holo2/src/holo2/solve/pose_fit.py:690-716`; `holo2/src/holo2/solve/plane_pixels.py:1-24` · *dial:* live

**holo3.** No region-wide derived plane exists. The POSE path crops the window plus a halo out of the level's memmapped plane, fills unsupported pixels to the capture's platen backing, box-filters, samples with `cval=backing` and applies the same >0.85 coverage gate — the surviving cells become the placement's `local_cells_yx`. The CALIBRATE path then crops raw luma around the window's points (halo = ceil(0.7*pitch)+2), box-filters it and samples with `map_coordinates(order=1)` — no backing fill and no second coverage gate, because the support restriction already rode in on `local_cells_yx`.

*Where:* `holo3/plugins/calibrate.py:178-244`; `holo3/plugins/calibrate.py:359-375`; `holo3/plugins/place.py:585-605`; `holo3/plugins/pose.py:259-279`; `holo3/plugins/pose.py:535-558`; `holo3/plugins/place.py:806-808`

*Scheduler row / doc:* conversion_docs contract C-2 (per-window crops); SCHEDULE.md rows `place` and `calibrate`

**Implementation delta.** holo2 derives one filled, filtered, support-carrying plane per region and reads BOTH the pose fit and the evidence sampling out of it; holo3 keeps the fill and the coverage gate on the pose side only and samples evidence from a raw per-window crop. The visible consequence is at a support boundary: in holo2 the aperture over a supported cell near an edge averages the backing constant, in holo3 it averages whatever pixels are actually there (neighbouring scrap, platen, another sheet). holo3's behaviour here is v1's, pinned bit-for-bit; holo2's is holo2's own, adopted for memory reasons its record states plainly.

**Evidence status.** PINNED

**Evidence.**

- (holo3) window sampling compared live against v1 `_payload_sampling._window_crop`/`_sample_rows` at four pitches and angles, means and scores equal, filter signature equal; crop_luma matches the v1 raster laws — *artefact:* holo3/tests/test_h3_drift_receiver.py:165 (test_calibrate_window_sampling_matches_v1_payload_sampling), :197 (test_calibrate_crop_luma_matches_the_v1_raster_laws)
- (holo2) prepared-planes memory record: workers-8 and workers-4 both SIGKILLed (exit 137) on a 64 GB machine while serial survived; ingest holds ~19.5 GB resident; the gen-clean sibling completed 1,471 s serial at 95.3% utilisation — *artefact:* ARTEFACTS.md:666-671 -> holo2/docs/MEASUREMENTS.md:2308-2320
- (holo2) v1 clipped edge windows: 193 and 131 cells on the differential's own arms, dropped under the floor — *artefact:* ARTEFACTS.md:470 -> holo2/src/holo2/solve/DESIGN.md:337
- (holo3) the batteries are three orders of magnitude cheaper in memory than a full-sheet run (peak RSS 0.31-2.22 GiB) — *artefact:* ARTEFACTS.md:315-318 -> holo3/conversion_docs/overnight/ledger.jsonl

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* This is the one row where holo2 is the DIVERGENT tree and holo3 the faithful carry. No artefact measures the yield of holo2's filled-plane evidence sampling against v1's raw-crop sampling — holo2's own record justifies the prepared plane on memory and wall alone. Nothing about the fill should be ported. Worth carrying into COMMENT-CARRY: holo2's prepared.py docstring is the clearest statement in either tree of why a region-wide derived plane is dangerous under a worker pool, and holo3's per-window crop is the answer to it.

*Refuter (upheld):* *Corrections:* The attribution in the delta and the notes is wrong and reverses the row's own lesson. 'holo3's behaviour here is v1's ...; holo2's is holo2's own' is not what holo2's record says: holo2/src/holo2/solve/prepared.py:1-40 states the prepared plane reproduces v1's `pose_fit.prepare_region` BYTE FOR BYTE, 'pinned by a test that byte-compares the whole built plane against prepare_region's output'. So BOTH trees carry a v1 function; they carry DIFFERENT ones for the evidence read. v1 itself has two: `prepare_region` (fill to backing + aperture, the pose/address path, which is what holo2 routed evidence through) and `_payload_sampling._window_crop` (src/holo/receive/_payload_sampling.py:197-221 — raw crop, NO backing fill, cval = median(raw)), which is the evidence path and is what holo3 reproduces. Restate the delta as 'which v1 preparation each tree uses for evidence', which is sharper and still lands on 'nothing about the fill should be ported'. Minor: holo3's two sampling entry points differ in their unused `fill` (holo3/plugins/calibrate.py:209 median(raw) vs :244 0.0) — unobservable because every sample point lies inside its own crop by construction, but do not describe them as one path.

*Reason:* The pixel provenance really does differ as described, and holo3's evidence sampling is v1's, pinned live (holo3/tests/test_h3_drift_receiver.py:165,197).

*Second lens (final: CARRIED-DIFFERENT):* REFUTER UPHELD ON THE ATTRIBUTION, and the correction matters because the reader's version reverses the row's own lesson. holo2/src/holo2/solve/prepared.py:1-40 states plainly that its prepared plane reproduces v1's pose_fit.prepare_region byte for byte, pinned by a test that byte-compares the whole built plane; so holo2 is NOT diverging from v1 here, it is carrying a DIFFERENT v1 function. v1 has two preparations and I read both: prepare_region (fill unsupported pixels to the platen backing, then one box aperture - the pose and address path) and src/holo/receive/_payload_sampling.py:197-221 _window_crop (raw crop, no backing fill, cval = median(raw)) which is the EVIDENCE path. holo2 routes the evidence read through v1's pose preparation (holo2/src/holo2/solve/pose_fit.py:700-706 samples region.filtered with cval=region.backing); holo3 routes it through v1's evidence crop (holo3/plugins/calibrate.py:200-209, :246-251), pinned live at holo3/tests/test_h3_drift_receiver.py:165,197. So the delta is 'which of v1's two preparations each tree uses for the evidence read', which is sharper than the reader's framing and still lands on 'port nothing'. The refuter's minor point also checks out and is a non-issue: the two holo3 entry points pass different unused fill values (median(raw) at calibrate.py:209 versus 0.0 at :244), and it is unobservable because _crop_bounds derives the crop from the sample points themselves with a halo and the outside-raster guard refuses any window whose points leave the raster - so cval is never consulted. YIELD LENS: decides-certificates, unmeasured. Over a supported cell near a support boundary, holo2's box average includes the backing constant and holo3's includes whatever pixels are physically there - neighbouring scrap, platen, an adjacent sheet. That changes the cell's mean, hence its score (holo3/plugins/calibrate.py:254-259 normalises by the window median and mean-absolute-deviation), hence its LLR, hence whether the tile clears the codec. No artefact on either side measures the yield of the fill; holo2's own record justifies the prepared plane on memory and wall alone (workers 4 and 8 both SIGKILLed, about 8 GB per array per fire).

---

### evidence-ownership-13 — Derived-rung pixels on disk (the scale-space memmap arm)

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B69

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether the coarse rungs a run reads exist as real pixels, where they live, and whether a second run pays for them again.

**holo2.** `area_decimate_into` streams an exact-rational area average of the AUTHENTICATED NATIVE raster (never of another rung) chunk by chunk into a `w+` memmap; `write_footing_raster` publishes it atomically under a digest name in the `<state-dir>.prepared` sibling, and `derive_footing_rasters` is called from the ingest fire. A rung whose digest already stands costs one `stat`.

*Where:* `holo2/src/holo2/capture/scale_space.py:714-744`; `holo2/src/holo2/capture/footing_raster.py:154-174`; `holo2/src/holo2/capture/ingest.py:194-245`; `holo2/src/holo2/capture/ingest.py:299-303` · *dial:* live

**holo3.** `ingest_capture` opens one `np.lib.format.open_memmap` per (level, plane) under `<run_dir>/<capture12>/lNN-<plane>.npy`, copies the native planes and streams every other level's area decimation into its file. Same law — every level derived directly from the native raster, never recursively. Names are positional, not digests, and every invocation re-derives them.

*Where:* `holo3/plugins/intake.py:134-158`; `holo3/plugins/intake.py:164-210`; `holo3/lib/decimate.py:27-42`

*Scheduler row / doc:* SCHEDULE.md row `survey` / 'Ingest converts each scan into the resolution ladder'

**Implementation delta.** Same arithmetic, pinned bit-exact against holo2's own kernels. Two differences: (1) file identity — holo2 names a rung by a digest of everything its content is a function of and reuses it across sessions, holo3 names it positionally under the run directory and rebuilds it on every invocation, so a resume pays the whole decimation again; (2) holo3 also materialises the native level as a plane copy, which holo2 does not (it maps the source raster).

**Evidence status.** PINNED

**Evidence.**

- (holo3) the ppc ladder, AreaPixelTransform, box kernels (chunk-invariant), rational kernels and luma conversion are all compared live against holo2 `capture/scale_space` and `capture/scan` and are bit-exact — *artefact:* holo3/tests/test_h3_drift_kernels.py:546, :563, :584, :604, :616

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* The seed's 'built-unused' for B69 is STALE in two directions and both should be recorded. holo2's DESIGN.md:670-676 says 'scale_space's memmap arm has no production caller to flip' and 'derived footings hold no pixels in this tree', but `capture/ingest.py:302` calls `derive_footing_rasters` on every ingest and `footing_raster.py:167` writes into a `w+` memmap — the doc predates H4-LANES stage 1 and is one of the doc-vs-code contradictions the archive README should carry. And the arm is not absent from holo3 either: it is the whole of `intake.ingest_capture`.

*Refuter (upheld):* *Corrections:* One conditional the row drops: `derive_footing_rasters` runs only when the ingest fire was given a directory (holo2/src/holo2/capture/ingest.py:301, `if directory is not None`). Keep the correction, add the guard, so the archive README's doc-vs-code contradiction list is exact.

*Reason:* Both decimation arms are live and both derive every rung from the native raster; the digest-vs-positional naming difference and holo3's native plane copy are exactly as stated, and the stale-seed correction about `derive_footing_rasters` is right (holo2/src/holo2/capture/ingest.py:301-304 calls it, footing_raster.py:167 writes a w+ memmap).

---

### evidence-ownership-14 — A re-read re-fits the context pool it belongs to

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B41

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether the region correction and the ownership loss a re-sampled window is judged by were fitted over that window's new reading or over the superseded one.

**holo2.** F1 fix (b): the ctx fit's read-set names the (footing, region) EVIDENCE collection as well as the pose collection, so a member that gains PIECES without being a new pose re-arms the fit. F1 fix (a) covers the gap between the two commits: a live pose with no published loss falls back to the minimum published loss of its extent's other generation instead of `inf`.

*Where:* `holo2/src/holo2/solve/calibration.py:577-628`; `holo2/src/holo2/solve/ctx_apply.py:117-165` · *dial:* live

**holo3.** The `ctx` row's declared reads are `(KEY_EVIDENCE_FIT, wid)` for every window of the region. `_fold_evidence` bumps EVIDENCE_FIT whenever the window's cells, scores, knots, probs or marginal change — which a re-sample always does — so the region re-fits through the ordinary version floor. A window placed later adds its key to the standing ctx bookmark's read set at birth time (`engine._offer` grows an existing bookmark's reads), so the subscription is complete rather than frozen at first fire.

*Where:* `holo3/plugins/calibrate.py:739-741`; `holo3/store.py:702-748`; `holo3/engine.py:388-408`

*Scheduler row / doc:* SCHEDULE.md key family `evidence_fit` — written by CtxOutcome and WindowEvidence, read by `ctx`

**Implementation delta.** holo2 needed both halves (a new subscription key and a loss fallback) because the fit's output is published in a separate record that the freeze reads. holo3 needs only the subscription: the loss lives on the evidence row itself and is rewritten by the same fold, so there is no window in which a re-read has no loss and nothing to fall back to.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) MEASURED before the fix: 0 of 6 re-read windows had a loss for their live pose, 6 of 6 had one for the parent; 0 of 4 pools on either real sheet had a fit that had seen a re-read's pieces; 0 of 255 xerox re-read poses had a published window loss — *artefact:* ARTEFACTS.md:502 -> holo2/src/holo2/solve/calibration.py:594-595, ctx_apply.py:133-135
- (holo2) re-read census: 239/239 and 255/255 resampled, no refusals — *artefact:* ARTEFACTS.md:527 -> holo2/src/holo2/solve/place_sched.py:456

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* Nothing to port; the failure mode holo2 measured is unrepresentable in holo3. The one thing worth carrying is the fact itself — that a re-read which does not re-fit its region silently reverts the ownership key to a geometric preference — as a comment on `_ctx_reads`.

*Refuter (upheld):* *Corrections:* Two fixes. (1) `engine._offer` DOES NOT EXIST (grep is empty at HEAD). The function is `engine._births` (holo3/engine.py:387-408), which is the range the row already cites — fix the name before it becomes a comment in Phase 2. (2) Add the mechanism that makes the subscription non-looping, because it is the real reason holo3 needs no adoption-collection exclusion where holo2 states one (holo2/src/holo2/solve/calibration.py:616-618): a ctx write changes only `printed_llr`, `heldout_logloss` and `ctx_adopted`, which `_fold_evidence` classifies as read_changed and NOT fit_changed (holo3/store.py:708-731), so the ctx row cannot re-arm itself while `tiles.scan` (which reads both keys) does re-fire.

*Reason:* The ctx row subscribes to every window's evidence_fit key, the fold bumps it on any resample, and the birth path grows an existing bookmark's read set — so holo2's two-part fix has a one-part answer in holo3, as claimed.

---

### evidence-ownership-15 — Quarantine's evidence-exclusion consumer — refusing to decode readings from a contradicted placement

**ABSENT** · evidence **MEASURED** · yield **integrity** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether a reading taken through a placement that an address-word contradiction condemned is still decoded and still allowed to own cells and weigh in a calibration fit.

**holo2.** One predicate, three readers. `route_evidence_keys` filters condemned pieces out of the attempt's READ-SET before either branch, so the exclusion is total: a condemned piece is not merely skipped by the decoder, it is not part of the attempt's identity. `pool_members` and the pool assembly ask the same predicate. The condemnation is a write on the condemned keys, so an in-flight decode over evidence condemned mid-flight dies at the wall's existing staleness check. Terminality on both sides, never rehabilitated.

*Where:* `holo2/src/holo2/solve/quarantine.py:1-56`; `holo2/src/holo2/solve/payload.py:306-307`; `holo2/src/holo2/solve/calibration.py:243`; `holo2/src/holo2/solve/calibration.py:263` · *dial:* live

**holo3.** absent

*Where:* _(no path given)_

*Scheduler row / doc:* no row; no key family; `plugins/words.py:299-327 word_rival_rows` is the within-window rival bar and is a different mechanism

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (v1) the zero-contradiction invariant is e022's: 70/70 regions, all 925 pilot tiles, ZERO contradictory reads across ~1,780 attempted known-position decodes — *artefact:* ARTEFACTS.md:750-752 -> docs/RECEIVE-DESIGN-EVIDENCE.md:492
- (holo2) holo2's own measurement is a wall cost, not a yield: W5 quarantine unit 1,915, oracles 314, 39 verdicts, wall 79.0 s — the wave costs ~1.7 s against a bypassed baseline, +2%. Yield: 'Zero contradictions on every healthy fixture' — *artefact:* ARTEFACTS.md:754-757 -> holo2/docs/MEASUREMENTS.md:1345, :1384-1386, :1390
- (holo3) zero wrong certificates across all five completed crop batteries (285 target addresses) and zero out-of-bbox certificates; every close that ran stayed byte-exact — *artefact:* ARTEFACTS.md:317-318, :601 -> holo3/conversion_docs/crop-batteries/*-results.json; PARITY.md:441

**Yield relevance.** integrity — source: reader.

**Recommendation.** accept the loss, and record it. There is no measured yield behind quarantine on any of the three sides — v1's ~1,780-read invariant says contradictions do not happen, and holo2's own number is a 2% wall cost. The integrity role it plays is already covered twice over in holo3: the per-tile codec gate is an LDPC syndrome plus a CRC over a codeword whose slot permutation and scramble are keyed by the tile ADDRESS, so a reading through a wrong-address pose cannot certify, and `printed_cells_for` raises `IntegrityError` if a certified re-encode disagrees with the format field at a known site. What genuinely leaves is the ability to NOTICE the contradiction and say so — a diagnostic, not a gate. If it is ever wanted back, the cheap form is an event, not a state family.

**Notes.**

*Reader:* Named by no seed row in this family (the seeds put quarantine under placement, where its consult half lives); the payload and calibration consumers are evidence-ownership and are equally absent. grok's hypothesis that quarantine is holo2's one unique yield lever has no measured yield behind it on either side (ARTEFACTS §2.11's own conclusion).

*Refuter (upheld):* *Corrections:* Citation only: the v1 invariant sits at ARTEFACTS.md:753, not :750-752 (a section and table header). The primary source does carry the row's fuller wording — docs/RECEIVE-DESIGN-EVIDENCE.md's SIX-SCAN SESSIONS bullet has '70/70 regions and all 925 pilot tiles' and 'ZERO contradictory reads across ~1,780 attempted known-position decodes' — so cite that line directly rather than through the shifted ARTEFACTS anchor.

*Reason:* One predicate with three readers in holo2 (quarantine.py:1-55, payload.py:306-307, calibration.py:243,263) and nothing whatsoever in holo3 — grep for 'quarantin' and 'condemn' over holo3 production code returns empty; `words.word_rival_rows` is a rival-hypothesis enumerator, a different mechanism as the row says.

---

### evidence-ownership-16 — Tile cover membership — which windows are offered to a tile's freeze at all

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Which windows' readings are even candidates for owning a tile's cells, and therefore what a scan or union has to work with.

**holo2.** Evidence is committed per (pose, tile) as whole 64x64 cuts with an observed mask, and the attempt reads every non-quarantined piece of its footing (or its ppc). A window whose calibration refused commits NO evidence and no pose either (the carried v1 behaviour recorded as a cost), so it contributes nothing and is not visible as a refusal.

*Where:* `holo2/src/holo2/solve/payload.py:273-314`; `holo2/src/holo2/solve/place_shared.py:886-895` · *dial:* live

**holo3.** `_fold_evidence` recomputes the window's cover only from ACCEPTED evidence, and only over the window's PAYLOAD cells (`evidence_cover_cells` -> `payload_cell_mask`; colour uses `cargo_row_indices`). So a window that overlaps a tile only at word/filler sites never joins that tile's cover, and a refused window is dropped from every cover it previously fed. The refused window keeps its placement and is re-offered by the `revisit` row.

*Where:* `holo3/store.py:702-748`; `holo3/plugins/tiles.py:163-187`; `holo3/plugins/tiles.py:246-264`

*Scheduler row / doc:* SCHEDULE.md key families `evidence_fit` / `evidence_read` -> rows tiles.scan / tiles.union / tiles.retry / tiles.local

**Implementation delta.** holo2's candidate set is 'every committed piece of this footing that is not quarantined'; holo3's is 'every accepted window whose payload cells reach this tile'. Two consequences: a window contributing only format sites is a candidate in holo2 and not in holo3 (it can own nothing anyway, so this is bookkeeping, not yield); and a calibration refusal is a live, reversible state in holo3 (the window keeps its pose and `revisit` gives it another chance) where in holo2 it costs the pose as well.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) 'a calibration-poor edge window commits no pose either — coverage and any refinement it would have fed are lost'; splitting calibration into its own provider is what would fix it — unbuilt — *artefact:* seeds/holo2-behaviour-ledger.md B63 -> holo2/src/holo2/solve/place_shared.py:886-895
- (holo3) no artefact counts calibration refusals or their recovery by the revisit row on a real sheet; PARITY.md records revisit firing 593 times across five volumes and crediting zero certificates — *artefact:* ARTEFACTS.md (§2.3 zero-adoption finding) -> holo3/conversion_docs/PARITY.md:443-448

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's. holo3 is the better side here — a calibration refusal costs the window's evidence but not its pose, and the revisit row re-offers it — but the record only supports 'better in principle': revisit fired 593 times across five volumes and credited zero certificates (PARITY.md:443-448). Settle it the same zero-cost way as row 05, from the archived event streams: count CalibrateAdopted refusals per volume and how many of those windows later carry accepted evidence. An xz/jq pass over files already on disk; no decode.

**Notes.**

*Reader:* holo3 is the better side of this comparison — it does not lose the pose with the calibration — but the recovery path (`revisit`) has a measured zero credit on real sheets, so 'better in principle' is all the record supports. The refusal-drops-the-emission cost is holo2's and does not need porting; it needs recording as a thing holo3 already avoids.

*Refuter (upheld):* *Corrections:* Three fixes, one of which changes what the row should recommend. (1) NUMBER: 'revisit firing 593 times ... and crediting zero certificates' is not what the artefact says. holo3/conversion_docs/PARITY.md:448 says revisit fired 593 times 'producing 0 `route=refine` poses'. revisit's calibrate branch produces no pose at all, so that statistic can neither credit nor debit it — the row currently reads a pose statistic as a certificate statistic. (2) THE RECOVERY PATH IS A STRUCTURAL NO-OP, which settles the row without the proposed event pass: `prepare_revisit` -> `_revisit_calibrate` -> `calibrate.window_job` -> `resample_window` re-uses the standing cells AND the standing `reference_values` at the SAME placement (holo3/plugins/revisit.py:27-28,47-55; holo3/plugins/calibrate.py:349-356,661-668), so a label-driven refusal (`search_class_starved`, `heldout_starved`) is reproduced bit for bit; the only thing that can change the outcome is a pose move, and a pose move re-fires `calibrate` on its own read anyway (holo3/plugins/calibrate.py:719). So the measured zero is expected by construction, not an instrumentation gap, and the row should say that instead of 'better in principle'. (3) ATTRIBUTION: '(the carried v1 behaviour recorded as a cost)' mis-reads holo2's own comment, which says 'carried behaviour of the inline calibration block' (place_shared.py:890) — i.e. carried from holo2's earlier code, not from v1. v1 retains refused windows and their placements and filters `row.accepted` only at the freeze (src/holo/receive/payload.py:123-140), so holo3 matches v1 here and holo2 is the divergent tree. That makes the row's verdict stronger, not weaker.

*Reason:* The cover really is accepted-only and payload-cells-only in holo3 (holo3/store.py:740-745, plugins/tiles.py:163-176) while holo2's candidate set is every non-quarantined piece of the footing, and holo2 really does lose the pose with the calibration (place_shared.py:886-895).

*Second lens (final: CARRIED-DIFFERENT):* REFUTER UPHELD ON ALL THREE CORRECTIONS, and correction (2) settles the row and cancels the measurement the reader proposed. (1) The number is misread: holo3/conversion_docs/PARITY.md:448 says the re-offer row fired 593 times 'producing 0 route=refine poses'. Its calibration branch produces no pose at all (holo3/plugins/revisit.py:27-28 returns calibrate.window_job), so that statistic can neither credit nor debit it; the row currently reads a pose statistic as a certificate statistic. (2) The recovery path is inert by construction, which I traced end to end rather than inferring: prepare_revisit sends an unaccepted window to calibrate.window_job (holo3/plugins/revisit.py:47-53), which re-samples through resample_window using the STANDING page_cells_yx and the STANDING reference_values at the SAME placement (holo3/plugins/calibrate.py:659-665, :349-356), so a label-driven refusal such as search_class_starved or heldout_starved is reproduced bit for bit. The only inputs that can move the outcome are the pose affine and the region pitch, and BOTH are calibrate's own declared reads (holo3/plugins/calibrate.py:713-716), so calibrate re-fires on its own when either changes. The measured zero is therefore expected by construction, not an instrumentation gap, and the archived-event pass the reader proposed would only re-derive it. (3) The attribution is misread: holo2's comment at holo2/src/holo2/solve/place_shared.py:890 says 'carried behaviour of the inline calibration block', i.e. carried from holo2's own earlier code, not from v1. v1 retains refused windows and their placements and filters at the freeze (src/holo/receive/payload.py:118-140, 'retain all windows'), so holo3 matches v1 and holo2 is the divergent tree - which makes the row's verdict stronger. YIELD LENS: decides-certificates, in holo3's favour. The membership difference itself is bookkeeping - a window contributing only format sites can own nothing anyway. The pose-retention difference is real yield: porting holo2's behaviour would drop the pose of every calibration-poor edge window, losing its coverage and any refinement it could feed, which holo2's own ledger records as a cost. One asymmetry no row states and I confirmed: holo3/store.py:813-830 gives colour rows no accepted concept, so a colour row always joins the tile cover while a K row joins only when accepted (holo3/store.py:743). It is safe today only because every emitted colour row carries a real loss (holo3/plugins/color_region.py:297, :569); the None-valued internal rows never reach the store.

---

### evidence-ownership-17 — Attempt identity and the never-run-the-same-attempt-twice floor

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a tile reading that has already been decoded once is decoded again, and what counts as a different attempt.

**holo2.** The read-set IS the identity: an attempt names its work key, its evidence collection, exactly the pieces it decodes, its pools' calibration collections and each covering window's pose collection. A new piece, an adoption or a supersede moves the identity and re-arms the attempt; an unchanged one is idle by the spend-once test. Eligibility, not ordering, is the mechanism — an attempt that may not run yet has no descriptor.

*Where:* `holo2/src/holo2/solve/payload.py:461-523`; `holo2/src/holo2/solve/payload.py:47-56`; `holo2/src/holo2/solve/payload.py:881-931` · *dial:* live

**holo3.** Re-runs are governed by the bookmark's version floor: a worker fires only when its version has moved since its last try, and versions move on declared read keys. The attempt's own identity is `attempt_key` = (page, ty, tx, stream, stage, iteration budget, component signature) and is recorded with its outcome, but that record gates only the retry's baseline check, not re-firing.

*Where:* `holo3/plugins/tiles.py:310-319`; `holo3/store.py:803-811`; `holo3/engine.py:412-425`; `holo3/engine.py:450-456`

*Scheduler row / doc:* SCHEDULE.md 'How this matches v2' — 'the tried-set floor (identical inputs never re-run); fire-time consult (every job reads current truth, never wake-time state)'

**Implementation delta.** holo2 derives idleness from the content of the read-set (a hash of what the attempt reads); holo3 derives it from a monotone version counter on declared key families. holo3's `attempt_key` is coarser than holo2's read-set — it names the contributing (capture, level) pairs but not the evidence content — so two attempts over the same lanes with different evidence share a key and the later outcome overwrites the earlier. That is deliberate (the version floor is the whole staleness story, D6 addendum 6) and is why the corrected-vs-marginal re-attempt of row 03 is allowed to happen.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) F-17 residual measured: 1,677,186 descriptors offered to mint 1,768 workers; 4.95 s cum, 33% of the commit path — *artefact:* seeds/holo2-behaviour-ledger.md B60 -> holo2/src/holo2/engine/frontier.py:76-79; ARTEFACTS.md §2.9
- (holo2) W2 exit: wakes per commit 45.25 -> 0.71-0.82; stale discards (w8) 2,126 -> 14-41 — *artefact:* ARTEFACTS.md (§2.9 W2 exit walls) -> holo2/docs/MEASUREMENTS.md:2094-2103
- (holo3) both sims keep the wave-0 payload AND certificate set at workers 1 under --complete (49/49 and 279/279, certificate signatures byte-identical) across every D6 wave and the escalation-door change — *artefact:* holo3/SCHEDULE.md 'D6 waves 1-3'; holo3/conversion_docs/d6-baseline/{k,color}-w{1,8}.json

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* In-filter because it decides re-runs, but the yield question it could raise (a coarser attempt key suppressing a re-decode) does not arise: the key is not consulted to suppress work, only to answer the retry's 'did my baseline fail'.

*Refuter (upheld):* *Corrections:* Worth one added clause in support of the row's own 'the yield question does not arise': `_fold_attempt` returns an EMPTY key tuple (holo3/store.py:803-811), so an AttemptFact bumps no version family at all — the residue rows are born from it through `_births`, never woken by it. That is what makes the coarse key harmless, and it is the fact a Phase-2 comment would want.

*Reason:* Read-set-as-identity in holo2 (payload.py:461-523) and the monotone version floor plus a coarser attempt key in holo3 (engine.py:452-455, tiles.py:310-319, store.py:803-811) are both accurately described.

---

### evidence-ownership-18 — One payload job attempts every uncertified stream of its tile

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** How many decoder invocations a colour tile's reading costs, and whether a stream certified by another row is re-attempted.

**holo2.** One worker per work key, and the work key embeds the stream — so one fire decodes one stream. A race-loser still fires, reads CERTIFIED, contributes its observation and retires without touching a decoder. K-only in practice: holo2 never decoded colour.

*Where:* `holo2/src/holo2/solve/payload.py:441-459`; `holo2/src/holo2/solve/payload.py:525-575` · *dial:* live

**holo3.** The subject is the tile (not the tile-stream), and `prepare_scan`/`prepare_union` compute `_uncertified_streams` at fire time and attempt each of them over the one assembled cut, returning no job at all when none is pending. `tiles.retry`, `tiles.local`, planek and swim keep a per-stream subject.

*Where:* `holo3/plugins/tiles.py:621-634`; `holo3/plugins/tiles.py:637-661`; `holo3/plugins/tiles.py:664-680`

*Scheduler row / doc:* SCHEDULE.md 'Old engine vs descriptor engine' — 'colour tile jobs -49% (one job attempts all pending streams of a tile)'

**Implementation delta.** holo2 pays one fire (and one evidence assembly) per stream; holo3 assembles the cut once and runs the codec once per pending stream inside it, and re-reads the certified set at fire time so a stream another row certified is skipped without a fire. Same certificates, fewer assemblies.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) colour tile jobs -49% (one job attempts all pending streams of a tile), certificate sets identical (49/49 and 279/279), payload bytes identical — *artefact:* holo3/SCHEDULE.md 'Old engine vs descriptor engine' block
- (holo2) no colour number of any kind exists, by construction — *artefact:* ARTEFACTS.md:795+ G-17 -> holo2/docs/CAPABILITIES.md:43

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* Recorded compactly because it changes how much work runs; it cannot change which tiles certify.

*Refuter (upheld):* *Corrections:* None material.

*Reason:* prepare_scan/prepare_union compute `_uncertified_streams` at fire time and return no job when none is pending (holo3/plugins/tiles.py:637-680), `_attempt_many` runs the codec once per pending stream over one assembled cut, and retry/local/planek/swim all keep a per-stream subject (tiles.py:791, local_ctx.py:562, plane_k.py:610-622, swim.py:485-493). holo2's work key embeds the stream and a race-loser retires at payload.py:530.

---

### evidence-ownership-19 — Residue evidence tiers with no holo2 counterpart (tiles.local's per-lane pass, tiles.uplift, tiles.planek, tiles.swim)

**HOLO3-ONLY** · evidence **n/a** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → no refuter pass.

**What it decides.** Whether a tile that survived every ordinary reading is read again under a locally re-fitted head, a supplemental colour arm, a plane-isolated channel or a searched per-plane local affine.

**holo2.** None of these exist. The terms swim, planek, plane field, local context and uplift lane do not occur anywhere in holo2's design record, and holo2 has no colour reader at all.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** All are transient, additive and uncertified-tiles-only: they build a correction inside the job, feed one decoder input at the heavy budget through the unchanged codec, and discard it; none folds a WindowEvidence or a ColorEvidenceRow. `tiles.local` additionally reads its tile once as the union of covering lanes and then once per lane, stopping at the first certificate — the union wins an observation floor, the per-lane pass wins a vote.

*Where:* `holo3/plugins/local_ctx.py:433-462`; `holo3/plugins/local_ctx.py:595-615`; `holo3/plugins/uplift.py`; `holo3/plugins/plane_k.py`; `holo3/plugins/swim.py`

*Scheduler row / doc:* SCHEDULE.md 'Additive residue rows' (tiles.local 220, tiles.uplift 210/220, tiles.planek 230, tiles.swim 240)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo3) union vs per-origin for tiles.local: PER-ORIGIN WINS AND THE UNION NEVER WON ALONE — union 2 certificates (0 union-only), per-origin 6 (4 per-origin-only), N0 null 0, across 153 armed subjects on two sheet-I crops — *artefact:* ARTEFACTS.md:704 -> measure/local_ab/README.md:23-33
- (holo3) sheet I run 2: tiles.planek 281 certificates for 2,278 cpu-s = 8.1 cpu-s per certificate, 82% cascade, chains 7 generations deep — *artefact:* ARTEFACTS.md:702 -> experiments/034-sheet-i-full-readout.md:80-93
- (holo3) the swim: 137 jobs and 662.7 s, 20% of that run's 3,320 s, for 23 certificates; zero fires on both clean sims — *artefact:* holo3/SCHEDULE.md tiles.swim block

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* Listed for completeness of the evidence-ownership picture: these rows are where holo3 spends its evidence-ownership machinery today, and they are the reason several holo2 mechanisms (CA1 in particular) map across as re-scoped rather than dropped.

*Refuter:* this row was not put through the refuter pass.

---

## Refinement

15 rows; 12 carry a ruling.

**Reader's family notes.** Family-level. (1) THE FAMILY IS MEASURED SILENT ON BOTH SIDES IN OPPOSITE WAYS. holo2 adopted essentially every revision it proposed (270/275, 100%; zero gate flips in 237 re-scored revisions at margins ~1800x the threshold) and bought zero yield three ways; holo3 has adopted NOTHING on any real volume (0 route=refine poses across 717 refine + 3,899 refine.color + 593 revisit fires). The gate arithmetic is bit-exact across both trees and v1 (pinned). The only mechanism I found that could produce opposite adoption rates under one gate is refinement-02: holo2's refinement samples its baseline at a page cell's EDGE while holo2's production sampler reads the CENTRE, and holo3 samples the centre in both places. That is a code-derived hypothesis, not a measurement, and it should get a refuter lens and the cheap standalone check written into refinement-02's recommendation before any weight is put on holo2's refinement numbers. (2) The whole family's only measured yield is holo2's F1+F2 combined +27 e029 / +32 xerox at +112% / +386% wall (ARTEFACTS.md:560); the seed's F2-alone +13/+12 is explicitly superseded (ARTEFACTS.md:564). Nothing on holo3's side has a yield number, because it has never adopted. (3) THE ONE ARTEFACT THAT SPEAKS TO YIELD DIRECTLY IS ABOUT v1, NOT holo2: v1 won 18 of 1,930 xerox certificates by refinement, all in column 0; holo3 got 13 of those with no refinement at all and misses 5 of them, which are 5 of its 8 missing tiles (ARTEFACTS.md:123, :517-526). Whether holo3's refinement was even offered those five rows is inference, not measurement (G-10, ARTEFACTS.md:814), because holo3's refinement writes no events. That instrumentation gap is the single highest-value thing this family owes, and it is not a receiver run — it is an events change plus a re-read of captures already on disk. (4) Structural summary of the port: holo3 kept the fit (identical), kept the two-sided eligibility idea, kept the price band, kept the frozen-cell-set re-read, and dropped four holo2 constructs — the revision cap, the second-generation evidence rule, the separate resample tier, and quarantine — of which the first two are dissolved by holo3's one-placement/one-evidence store and the third is folded into calibrate at 15 instead of 200 (an earlier, cheaper re-read, which is a yield improvement, not a loss). Quarantine's absence is the placement family's row, not mine. (5) I could not verify: whether a non-refine re-placement can occur in holo3 and thus whether calibrate's resample branch can be reached with a stale cell set (refinement-07's recommendation names the check); and whether any holo3 producer of WindowEvidence can leave an accepted evidence without a heldout_logloss (refinement-10). (6) Stale citation found: the holo3 inventory seed describes plugins/refine.py as 'v1 == h2, character-identical per spec 08:69-80'. That is true of the fit arithmetic and false of local_segment/native_terms (holo3 adds the half cell) and of the entire descriptor half (subjects, reads, eligible, retire, cost), which holo2 spells as a provider plus a scheduler tier.

**Refuter's family notes.** Mechanisms no row covers. (1) THE DISPLACEMENT REACHES THE RE-READ, NOT JUST THE FIT. holo2/src/holo2/solve/resample.py:243 uses the same refine_fit.local_segment, so F2's re-read means are half a cell from generation zero's for the same cells — the family's two holo2 mechanisms (F1 fit, F2 re-read) share one defect, and every holo2 refinement number in the map is downstream of it. (2) THE REFINEMENT GATE AND THE DECODE DETECTOR PART COMPANY IN holo3. A ctx-adopted window's published loss is the context-corrected one (holo3/plugins/calibrate.py:507-517), but refine scores baseline and candidates through the marginal PAVA only (refine.py:436-441) — v1 applies the adopted offsets (src/holo/receive/certified_refine.py:703-715), holo2 deliberately does not. holo3 inherited holo2's choice without a doc line. (3) REVISIT'S PLACED BRANCH IS PROVABLY INERT (see refinement-15) — it is the same job calibrate re-fires at 15, priced at 200, woken by facts the job never reads. (4) THE ORDINAL'S ROUTE TERM IS INERT because place retires on `placed` (place_sched.py:224-226) — no ordinary placement is ever scheduled for a placed window, refined or not, so 'a refined placement can never be displaced' is a property of the place row's retire, not of placement_ordinal. (5) EVIDENCE_REACH IS FROZEN FOR LIFE in holo3: resample_window re-reads the standing evidence's cells (calibrate.py:349-356), so a window's evidence cell set never changes after its first calibration even as its pose moves and window_reach drifts; refine's eligible/retire read the frozen one and its subscription the moving one. Both trees freeze the cell set deliberately, so this is not a divergence — but nothing in the map says the two reaches can disagree indefinitely. (6) The family's single highest-value owed action remains G-10 instrumentation (per-fire refusal reasons on refine/refine.color), and it now has a companion that costs minutes and no run: re-price holo2's refinement record against the proved half-cell displacement before any of it is used to bound holo3.

**Second lens (yield) family notes.** Family-level, from the yield lens.

(1) THE MAP'S CENTRAL holo3 FACT IS A COUNTER DEFECT, AND BOTH PRIOR LENSES CARRIED IT. '0 route=refine poses' (cited in refinement-02 and refinement-04) is structurally impossible to observe: adoption is folded at holo3/store.py:786-800 without appending an event, and route='refine' is only ever written in the place accept path. holo3/conversion_docs/POST-FORENSICS.md:20-70 already retracts it; the reader cited that document's section A.1 while quoting the retracted headline from PARITY.md:448. Every row that leans on 'holo3 has never adopted' must be re-read.

(2) WHAT I MEASURED INSTEAD (no decode, ~30 min, read-only, from scratch/holo3-overnight-events/*.jsonl.xz): adoptions counted as JobDone.n_poses per refinement job. e029 240/932, e029-postfix 31/126, xerox-k 65/156, xerox-k-postfix 67/168, c3-cmy7 168/327, c2-cmy7 569/1269, sheet I 1844/5128. Chains: 154 windows adopted twice and 8 three times (c2-cmy7 12+1, c3-cmy7 15+3, sheet I 124+4, one twice-revised window on each of three K runs) — 162 windows past holo2's one-revision cap.

(3) THE FIRST YIELD CEILING holo3's REFINEMENT HAS. Mapping each adopted window's extent to the 64-cell tiles it covers and asking which of those tiles first certified AFTER the adoption: xerox-k-postfix 7 tile-certifications over 3 distinct tiles (795 of 823 tiles under refined windows were already certified), e029-postfix 10 over 3, e029 74 over 22, xerox-k 2 over 1. This is an UPPER BOUND, not an attribution — a later certification under a refined window can equally be the retry row or a finer level — and the ordering is journal order under 8 workers. It is still the strongest yield statement the family has on either side.

(4) THE PRICE MAKES THE LANE HARVEST-ONLY. Same capture, same format: the current tree's ordinary e029 decode (scratch/page-domain-qual/base-e029-run.64152, no --complete) closes verified at 1,357 certificates with ZERO refinement fires; the archived --complete decode of that identical capture fires 126, adopts 31, reaches 1,938. At price 200 refinement is drained after the close. Anyone reading holo3 refinement numbers must check for --complete first.

(5) holo2's HALF-CELL DISPLACEMENT IS REAL AND CLOSES ALGEBRAICALLY, no script needed: durable offset carries -M*(0.5,0.5) (place_shared.py:349), holo2's refinement re-origins without adding it back (refine_fit.py:419) and lands at o - M*(0.5,0.5); holo3 re-origins at corner+0.5 (refine.py:377) and lands exactly on o. It reaches the re-read too (resample.py:243). Its consequence is coherent with holo2's whole record — accept everything, buy nothing, done coverage down — but it no longer needs to explain an asymmetry that does not exist.

(6) OWED, ranked by value per hour: (a) emit the refusal reason and the adopted geometry delta from holo3's refinement (it writes no events at all today) — this is the G-10 instrumentation gap and it is an events change, not a run; (b) the composed-drift distribution for the 162 chained windows, from PoseCommitted plus the run states already on disk; (c) freeze holo2's side of the three-way constant pin before the tree is deleted, or the pin silently becomes two-way.

Counting convention for the summary: n_upheld counts rows whose classification I upheld (5); n_changed counts classification changes (1, refinement-01). Five of the six carry material evidence corrections regardless of classification.


### refinement-01 — The RF1 fit itself — labels, floors, two-stage search grid, tie-break, objectives, adoption gate

**CARRIED-DIFFERENT** · evidence **PINNED (opt-in slow lane)** · yield **nothing observable — on its own the row cannot change a single certificate: every kernel it names is asserted bit-equal across the three trees, and the one pixel-level difference belongs to refinement-02 and is scored there, not twice here** · ruling needed **N** · seeds: B37

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT → second lens CARRIED-DIFFERENT.

**What it decides.** Whether a proposed geometry is accepted, and therefore what geometry the payload is read through afterwards.

**holo2.** Carries v1's certified_refine arithmetic constant for constant: bounds +-0.15 deg / +-0.25 cell, a coarse grid of 27 points (0.15 deg, 0.25 cell) then a fine grid (0.05 deg, 0.0625 cell) around the coarse winner, contrast-then-loss tie-break, weighted log-loss on a block-stripe hold-out, and the three-clause adoption gate (held-out gain plus two pilot non-regressions at slack 0.005). Labels are format-known pilots plus certified printed cargo, weighted per block, with the 10**12 offset that keeps pilot and cargo blocks from sharing weight. refine.py re-exports every name so the split into refine_fit is a file-cap seam, not a second address.

*Where:* `holo2/src/holo2/solve/refine_fit.py:60-90`; `holo2/src/holo2/solve/refine_fit.py:140-186`; `holo2/src/holo2/solve/refine_fit.py:189-260`; `holo2/src/holo2/solve/refine_fit.py:262-300`; `holo2/src/holo2/solve/refine_fit.py:468-555`; `holo2/src/holo2/solve/refine.py:169-187` · *dial:* live

**holo3.** The same eighteen shared constants, the same 27-point coarse grid and fine grid, the same dedup-to-12-decimals candidate key, the same contrast-then-loss select_best, the same weighted log-loss and the same three-clause adoption_gate; labels are the evidence's own format reference values plus printed cells reconstructed from the certificates in reach. refine_window runs the identical order: support floors, the pilot-count floor, coarse grid, fine grid, best, then the gate.

*Where:* `holo3/plugins/refine.py:36-63`; `holo3/plugins/refine.py:117-201`; `holo3/plugins/refine.py:206-260`; `holo3/plugins/refine.py:313-368`; `holo3/plugins/refine.py:412-509`

*Scheduler row / doc:* SCHEDULE.md:51 (refine row); SCHEDULE.md:107-112 (refine debt row); conversion spec 08-pose-refine.md:69-80

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED (opt-in slow lane) — corrected in the merge: refuter: the pin is real and green at HEAD (37 passed) but is gated behind HOLO3_RUN_SLOW_TESTS, and its holo2 leg dies with the tree — plan step 2.3 schedules the freeze.

**Evidence.**

- (holo3) 18 shared constants asserted equal across holo3, v1 certified_refine and holo2 refine_fit — *artefact:* holo3/tests/test_h3_drift_receiver.py:440-454 (test_refine_constants_agree_across_all_three_trees)
- (holo3) stripe coefficients (104729, 1009, 9177) and cap hashes (11400714819323198485, 14029467366897019727) pinned literally — *artefact:* holo3/tests/test_h3_drift_receiver.py:457-463
- (holo3) block_validation / block_weights / support_metrics / deterministic_cap / select_pose_sites / pose_candidate / pose_objective / weighted_logloss / candidate_grid / fine_grid / select_best / adoption_gate / collect_labels all asserted array- or value-equal against v1 AND holo2 — *artefact:* holo3/tests/test_h3_drift_receiver.py:497-616 and the collect_labels join test at :627-660
- (v1) the refinement search box: ANGLE_LIMIT_DEG=0.15, PHASE_LIMIT_CELLS=0.25, MIN_POSE_PILOTS=30, MIN_HELDOUT_GAIN=1e-4, PILOT_MISMATCH_SLACK=0.005 — 17 constants, no provenance comment on any of them — *artefact:* ARTEFACTS.md:549

**Yield relevance.** nothing observable — on its own the row cannot change a single certificate: every kernel it names is asserted bit-equal across the three trees, and the one pixel-level difference belongs to refinement-02 and is scored there, not twice here — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's

**Notes.**

*Reader:* One scale difference that is NOT a divergence: holo2 fits and scores on negated raw luma in float64 (refine_fit.py:497-502), holo3 (like v1) normalises to (midpoint - raw)/spread in float32 (refine.py:300-311). Each tree is self-consistent because its PAVA knots were fitted on its own scale, and the two scales are related by a positive affine map, so the monotone map and the log-loss agree; the drift tests compare the scale-free pieces plus the gate. holo3 also folds an extra post-gate 'unchanged_affine' refusal (refine.py:505-507) that holo2 spells at the worker instead (see refinement-05). The holo3 inventory's claim that plugins/refine.py is 'v1 == h2, character-identical' (seeds/holo3-inventory.md, module map) is true of this row and NOT true of the geometry restatement (refinement-02) or the descriptor half.

*Refuter (reclassified):* *Corrections:* Keep every pin and every number; change the word and add two composed deltas. (1) The eighteen-constant / kernel equality IS real and green at HEAD: I ran `HOLO3_RUN_SLOW_TESTS=1 pytest holo3/tests/test_h3_drift_receiver.py -k refine` = 37 passed. But the module carries a lane gate (holo3/tests/test_h3_drift_receiver.py:41-45, `skipif not _h3_support.slow_lane()`, env HOLO3_RUN_SLOW_TESTS) — the row must say the pin is opt-in lane, and that its holo2 leg (`pytest.importorskip('holo2.solve.refine_fit')`, :37) dies with the tree, which plan step 2.3 already schedules as a freeze. (2) The pinned pieces are pure functions; the COMPOSED fit is not identical: holo3's refine_window (holo3/plugins/refine.py:412-509) samples its baseline through holo3/plugins/refine.py:378 (+0.5) and holo2's propose (holo2/src/holo2/solve/refine_fit.py:468-548) through refine_fit.py:419 (no +0.5) — measured half a cell apart, see refinement-02 — and holo3 adds the post-gate `unchanged_affine` refusal at refine.py:504-507 that holo2 spells at the worker (refine.py:428-457). (3) Line nits: the constants test is :450-454, the private-constant test :456-463, collect_labels :627-665. (4) The negated-raw-luma vs (midpoint-raw)/spread note is exact: holo2 refine_fit.py:497-502, holo3 refine.py:300-311 — verified.

*Reason:* Rule (e): a row whose two sides read different pixels is not CARRIED-IDENTICAL, even where every kernel it names is bit-pinned; the label would tell a deleter there is nothing to check here.

*Second lens (final: CARRIED-DIFFERENT):* I side with the refuter against the reader. The reader's own note already concedes the two composed fits read different pixels, which is exactly what CARRIED-IDENTICAL tells a deleter not to check. Verified at HEAD: the kernels are pinned (holo3/tests/test_h3_drift_receiver.py:450-454 constants, :456-463 private constants, :497-616 the array-equal kernels, :627-665 collect_labels), but the composition is not — holo3/plugins/refine.py:378 adds +0.5 to the baseline frame where holo2/src/holo2/solve/refine_fit.py:419 does not, and holo3 carries a post-gate refusal at holo3/plugins/refine.py:504-507 that holo2 spells in its worker at holo2/src/holo2/solve/refine.py:445-457. Two line nits in the reader's evidence confirmed (the constants test is :450, not :440). One durability point neither side raised as such: the pin is opt-in (holo3/tests/test_h3_drift_receiver.py:41-45, HOLO3_RUN_SLOW_TESTS) and its holo2 leg is a pytest.importorskip at :37, so deleting holo2 turns the three-way pin into a silent two-way one with no failure.

---

### refinement-02 — The window-local geometry restatement and the point the baseline is sampled at (local_segment / native_terms / sample_at)

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates — it decides whether an adopted revision moves production sampling toward the middle of a cell or a quarter-cell away from it, which is the difference between refinement buying tiles and refinement costing them; on the archived corpus it is holo2's numbers that change, not holo3's** · ruling needed **Y** · seeds: B37, B38

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Where on the raster the refinement's baseline and every candidate are read, and therefore what the adoption gate is comparing against.

**holo2.** local_segment restates the durable native affine in the rung's pixels and re-origins it at the observed cells' corner as origin = M @ corner + t, with NO half-cell term; sample_at then reads M @ (corner + local) + t. But holo2's durable page affine is deliberately EDGE-indexed: page_affine_terms subtracts linear @ (0.5, 0.5) precisely because 'v1's affine maps cell CENTRES ... holo2's maps cell EDGES - every holo2 sampler adds the sub-cell offset itself' (place_shared.py:328-333). The production sampler pose_fit.sample_segment is documented as 'one order-1 cell-centre read' and gets its centre from the fitted pose origin, whose phase search runs over [0.5, 1.5) cells (pose_fit.py:515).

*Where:* `holo2/src/holo2/solve/refine_fit.py:402-432`; `holo2/src/holo2/solve/refine_fit.py:435-448`; `holo2/src/holo2/solve/refine_fit.py:558-574`; `holo2/src/holo2/solve/place_shared.py:311-353`; `holo2/src/holo2/solve/pose_fit.py:689-716` · *dial:* live

**holo3.** local_segment sets origin = M @ (corner + 0.5) + t and native_terms inverts with the same + 0.5, so a local cell maps to the CENTRE of its page cell; calibrate.scan_points_yx likewise samples (cells + 0.5). refine's crop is calibrate.window_crop over exactly the points calibrate used, uniform-filtered with the same aperture, so the refinement baseline is the same read the standing evidence carries, cell for cell.

*Where:* `holo3/plugins/refine.py:370-387`; `holo3/plugins/refine.py:390-398`; `holo3/plugins/refine.py:401-409`; `holo3/plugins/calibrate.py:156-165`; `holo3/plugins/calibrate.py:201-209`; `holo3/plugins/calibrate.py:229-244`

*Scheduler row / doc:* SCHEDULE.md:51 (refine row)

**Implementation delta.** holo3 adds the half-cell term to the refinement's own frame conversion (refine.py:377, :394) and to the ordinary sampler (calibrate.py:161); holo2 adds it nowhere in the refinement path, while its durable affine has the half cell subtracted out at write time (place_shared.py:349-350). Reading holo2's code as it stands, its refinement baseline is therefore sampled half a cell up-left of the point generation zero read, and the +-0.25-cell search box cannot reach the point production actually samples; native_terms writes the winner back through the same offset frame, so an adopted holo2 revision shifts production sampling by whatever the search picked inside that displaced box. holo3 has no such gap: its baseline sample is the standing evidence's sample.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) RF1 adoption rate on the two real sheets: 270/275 revisions adopted, 100% — *artefact:* ARTEFACTS.md:556
- (holo2) zero adoption-gate flips in 237 re-scored revisions (89 e029 / 148 xerox), worst margin ~1800x MIN_HELDOUT_GAIN — *artefact:* ARTEFACTS.md:505
- (holo2) RF1 yield zero three ways: W2 resume +0/+0, W3 +0, W4 -1/+0; done coverage went DOWN -3,996 (e029) / -1,449 (xerox) cells — *artefact:* ARTEFACTS.md:556, ARTEFACTS.md:559
- (holo3) across five completed post-change volumes refine fired 717 times, refine.color 3,899 and revisit 593, producing 0 route=refine poses — zero, everywhere — *artefact:* ARTEFACTS.md:528-536 (PARITY.md:443-448; adjudicated in POST-FORENSICS.md:98-262 §A.1 'why the refusals are honest not a stuck gate')

**Yield relevance.** decides-certificates — it decides whether an adopted revision moves production sampling toward the middle of a cell or a quarter-cell away from it, which is the difference between refinement buying tiles and refinement costing them; on the archived corpus it is holo2's numbers that change, not holo3's — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's — and record the finding, because it re-weights every holo2 refinement number in this map. Costed check that needs no receiver run (tens of minutes, a standalone script under measure/): on one archived holo2 state, for a handful of committed poses, compare refine_fit.local_segment's baseline points against pose_fit.sample_segment's points for the same window, and assert the difference is (0, 0) or M @ (0.5, 0.5). A second, cheaper leg: assert holo3's refine baseline equals the standing WindowEvidence scores on a sim window (a holo3 unit test, not a decode).

**Notes.**

*Reader:* This is my own derivation from the current code on both sides, not a measured claim, and it deserves a refuter lens of its own. It is the only mechanism I found that explains the two receivers' opposite adoption rates under the SAME pinned gate arithmetic (holo2 100%, holo3 0%). If it holds, holo2's RF1 record (100% adoption, zero yield, done coverage down, the 'worst margin ~1800x' gate slack) is confounded and must not be used to bound holo3's refinement; if it does not hold, holo3's universal refusal needs a different explanation and G-10 (ARTEFACTS.md:814) becomes the thing to close. local_segment and native_terms are the ONLY refinement functions with no cross-tree pin (holo3/tests/test_h3_drift_receiver.py pins everything around them but not these two; the only local_segment test is the holo3-internal one at holo3/tests/test_h3_plugins_calibrate_refine.py:982).

*Refuter (upheld):* *Corrections:* Upgrade the row from derivation to proof, and fix one 'no pin' claim. (a) PROVED, no state needed: a 40-line pure-arithmetic script built a production AffinePose, wrote it through the ONLY writer of a placed pose's durable affine (holo2/src/holo2/solve/place_shared.py:311-353 `page_affine_terms`), and compared `refine_fit.local_segment`+`sample_at` points against `pose_fit.sample_segment`'s: delta = -A@(0.5,0.5) EXACTLY, for rot_k 0/1/2/3 (3 px at pitch 6). A second script compared holo2's and holo3's refine points for one identical durable affine: holo3 - holo2 = +(3,3) uniformly. The row's 'costed check on an archived state' is therefore already answered — replace it with these two scripts (minutes, no receiver run). (b) The row says local_segment/native_terms have NO pin and cites only test_h3_plugins_calibrate_refine.py:982. That is wrong for holo3: holo3/tests/test_h3_plugins_sampling_geometry.py is exactly this property, in the FAST lane, 46 tests green — `test_local_pose_points_agree_with_scan_points_yx` (:164-171, tol 1e-9 px, all six level scales), `test_local_pose_points_detect_a_planted_half_cell_slip` (:173-180), `test_a_half_cell_shift_survives_the_native_terms_round_trip` (:148-161), `test_scan_points_yx_reads_every_cells_own_block_value` (:95-101) and `test_a_half_cell_shifted_sampler_reads_the_neighbouring_cell` (:104-122, which demonstrates that a half-cell slip reads the NEIGHBOURING cell's value). holo3's half is PINNED, not UNPROVEN; only the causal claim (that this is why holo2 adopted 100%) stays UNPROVEN. (c) Add the two strongest corroborations the row misses: v1 has the guard holo2 dropped — src/holo/receive/certified_refine.py:746-753 raises RefinementIntegrityError unless the refinement baseline REPRODUCES the retained generation-zero raw means; and holo2's own tree asserts the property twice in prose that the code does not deliver — refine.py:118-120 ('the baseline logits this fire computes are, cell for cell, the LLRs the evidence pieces already carry') and refine.py:57-58 ('the fit's baseline therefore stays the geometry its evidence was actually sampled at'). (d) It is not two conventions: holo3/plugins/place.py:277-290 carries the SAME -linear@(0.5,0.5) as holo2, and both trees add it back in predict_from_page_affine (holo2 place_shared.py:402, holo3 place.py:307). One tree compensates in the refinement path, the other does not. (e) Reconcile with the only measured yield so nobody reads it as a contradiction: F1+F2 = +27/+32 (ARTEFACTS.md:560), and the ownership key ALONE is worth 27+27 (ARTEFACTS.md:496) — the re-read's share is at most +0 e029 / +5 xerox, consistent with a displaced re-read buying nothing. (f) Wording: '270/275 revisions adopted' reads as a ratio; it is 270 on e029 and 275 on xerox, both at 100% (ARTEFACTS.md:556).

*Reason:* I tried to refute it by execution and could not: the displacement is exactly -A@(0.5,0.5) in all four orientations, and holo2's own docstrings claim the property the code breaks.

*Second lens (final: DIVERGED):* Upheld, and I can strengthen it from derivation to closed arithmetic without any script. Both trees store the page geometry cell-EDGE indexed: holo2/src/holo2/solve/place_shared.py:349-350 and holo3/plugins/place.py:286 both subtract linear@(0.5,0.5) at write time. For rot_k=0 the durable offset is o - M*origin - M*(0.5,0.5); holo2's refinement re-origins at corner with no half cell (holo2/src/holo2/solve/refine_fit.py:419), giving local origin o - M*(0.5,0.5); holo3 re-origins at corner+0.5 (holo3/plugins/refine.py:377) giving exactly o, and inverts through the same +0.5 (holo3/plugins/refine.py:394). The gap is exactly -M*(0.5,0.5) — half a cell on the diagonal, three pixels at a six-pixel pitch, i.e. the corner where four cells meet. holo3's ordinary sampler agrees with its refinement sampler by construction (holo3/plugins/calibrate.py:161) and this is pinned in the FAST lane (holo3/tests/test_h3_plugins_sampling_geometry.py:166-180), so the reader's 'no pin' claim is wrong for holo3 and the refuter's correction stands. One correction to BOTH prior lenses: the row's motivating premise — 'holo2 adopts 100%, holo3 adopts 0%' — is false. holo3's zero came from a broken counter (holo3/conversion_docs/POST-FORENSICS.md:20-70): route='refine' is only ever written in the place accept path, so it is structurally zero. Measured from the archived event streams myself, holo3 adopts 24-75% of its refinements on real volumes. The defect in holo2 is proved; its role as the explanation of a phantom asymmetry is not.

---

### refinement-03 — Refinement eligibility — the e024 two-sided reach gate

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B37

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which windows are offered a pose revision at all, and therefore where refinement spend and any refinement yield can land.

**holo2.** Reach is derived, never recorded: one pass over the evidence index groups pieces by the pose that produced them, and the tile map partitions the tiles they name into certified and open. A pose is eligible when it has BOTH open tiles (something to gain on, e024's law) and certified tiles (the label channel RF1 needs), and its extent carries no revision yet. Quarantined poses and quarantined pieces are dropped in the same sweep, and expansion mints no descriptor at all for an ineligible reach.

*Where:* `holo2/src/holo2/solve/refine.py:198-242`; `holo2/src/holo2/solve/refine.py:245-318`; `holo2/src/holo2/solve/refine.py:461-482`; `holo2/src/holo2/solve/refine.py:624-638` · *dial:* live

**holo3.** The subject is the window, not a pose. reach_tiles derives the window's tile reach from its evidence page cells (store.evidence_reach) and reach_certified marks a tile certified when ANY stream of the row has a certificate for it. refine_eligible = 0 < |certified reach| < |reach| AND the certified reach strictly contains the adopted revision's basis; refine_exhausted (the retire predicate) fires when the whole reach is certified. Family.K only, and the standing evidence must be accepted.

*Where:* `holo3/plugins/refine.py:517-548`; `holo3/plugins/refine.py:551-558`; `holo3/plugins/refine.py:567-580`; `holo3/plugins/refine.py:636-656`; `holo3/store.py:217-223`

*Scheduler row / doc:* SCHEDULE.md:51, SCHEDULE.md:107-112 (the refine debt row), SCHEDULE.md:411-419 (the REFINE named problem)

**Implementation delta.** Subject and derivation: holo2 offers one descriptor per eligible (window, pose) grouped off the evidence index; holo3 offers one per window against the standing placement. Certified test: holo2 partitions per (page, ty, tx, stream) work key, holo3 collapses to per-tile 'any stream certified' — exact for K rows, which carry one stream, and the only rows this descriptor serves. holo3 adds a fourth clause holo2 has no counterpart for (certified reach must strictly outgrow the basis, refinement-04) and expresses 'nothing left to gain' twice: once in eligible and once as a retire predicate that removes the subject permanently. holo3 drops holo2's quarantine filter entirely, because holo3 has no quarantine machinery.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) post step 2 on e029: refine fires 106 -> 406 after the re-arm widening, revisit 0 -> 124, all crediting 0 certificates; the volume went 1940 -> 1938 (lost 2 at ty=42), wall 1.16x — *artefact:* ARTEFACTS.md:99
- (v1) on the xerox K sheet v1 won 18 of its 1,930 certificates by refinement and all 18 are in column 0; holo3 certified 13 of those 18 with no refinement at all; the 5 it did not get are 5 of holo3's 8 missing tiles — *artefact:* ARTEFACTS.md:123, ARTEFACTS.md:517-526
- (holo3) G-10: why holo3's refinement was not scheduled at the five column-0 rows v1 rescued is inference, not measurement — holo3's refinement writes no events — *artefact:* ARTEFACTS.md:814

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's gate, and close G-10 first: add per-fire refinement events (subject, reach sizes, refusal reason) to holo3's refine and refine.color rows — an instrumentation change, not a mechanism change — then re-read the xerox K events already in hand (scratch/holo3-overnight-events/xerox-k-postfix-events.jsonl.xz) plus one re-decode of that volume. Until then no one can say whether the five column-0 tiles were never offered, offered and refused on support, or refused on the gate.

**Notes.**

*Reader:* The two sides' eligibility is the same idea (open residue AND certified labels) and I could not find a case where the per-stream/per-tile collapse changes a K verdict. What is genuinely different is that holo3's refinement never even reports which clause closed the door, where holo2 names all three by string (extent_already_revised / no_uncertified_residue / no_certified_labels, refine.py:479-482). The colour lane's eligibility has no 'something to gain on' clause in eligible at all — it lives only in the retire predicate (color_refine.py:361-368); see refinement-14.

*Refuter (upheld):* *Corrections:* Both sides read correctly at HEAD (holo2 Reach at refine.py:198-242 / reaches at :245-318 / _gather's three named refusals at :465-482; holo3 refine_eligible refine.py:536-542, reach_certified :551-558, _refine_eligible :636-646, _refine_retire :649-656, store.evidence_reach store.py:221-223). Two small precisions worth carrying: holo3's reach is derived from the EVIDENCE's page cells, so a tile the window only clips by a sliver counts as a full member of both `len(reach)` and the retire test — holo2's piece-derived partition has the same property (a piece exists per observed (tile,stream)), so this is a match, not a delta; and the K-row 'any stream certified' collapse is exact because store.row.streams has one entry for K. The G-10 recommendation (add per-fire refusal events) is the right first move and is instrumentation, not mechanism.

*Reason:* Every clause of both gates reproduces at HEAD; the stated delta is complete and correctly worded.

---

### refinement-04 — How many times one window may be revised — holo2's one-revision-per-extent bar vs holo3's basis-gated chain

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates — the chain decides what geometry the payload is finally read through, and it is live on paper today: 162 windows across the archived runs have already taken more revisions than holo2's cap allows, 8 of them three** · ruling needed **Y** · seeds: B37, B39

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a window's geometry can be walked in several bounded steps as the certificate frontier grows, and how far it may drift from the placement that was accepted.

**holo2.** Reach.revised makes 'a revision is never itself eligible' structural: an extent whose window already holds more than one unquarantined committed pose offers no subject at all, neither the revision nor the parent. So one window holds at most two committed poses ever, and total drift from the accepted placement is bounded by one search box (+-0.15 deg, +-0.25 cell). The module states plainly that lifting the bar is a measurement nobody made, and that it would owe generation.py a pose ordinal.

*Where:* `holo2/src/holo2/solve/refine.py:210-242`; `holo2/src/holo2/solve/refine.py:304-317`; `holo2/src/holo2/solve/refine.py:473-480`; `holo2/src/holo2/solve/generation.py:34-49` · *dial:* live

**holo3.** There is no cap. An adopted revision records the certified tiles it was fitted against as Placement.refine_basis, and the window becomes eligible again as soon as the certified reach strictly contains that basis. Each new fit starts from the CURRENT (already revised) geometry, so successive bounded steps compose; the chain terminates only because the basis grows monotonically and the reach is finite.

*Where:* `holo3/plugins/refine.py:537-542`; `holo3/plugins/refine.py:512-514`; `holo3/data.py:112-120`; `holo3/store.py:791-801`

*Scheduler row / doc:* SCHEDULE.md:110-112 — 'A revised placement refines again only when its certified reach strictly outgrows the adopted revision's basis (the gated lift)'

**Implementation delta.** holo2: at most one revision per extent, ever, enforced at expansion and re-checked in the fire; cumulative drift <= one search box. holo3: unbounded chain, each step gated on the certified reach strictly growing; cumulative drift <= (number of certified tiles in reach) search boxes. holo3 also cannot detect an oscillation A -> B -> A, because it keeps no record of superseded poses (see refinement-05); such a cycle is adopted each time as long as the basis grew.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) A2 counted 269/1,228 (e029) and 272/1,282 (xerox) windows carrying two committed poses, and never a third — *artefact:* ARTEFACTS.md:555
- (holo3) 0 route=refine poses across 717 refine fires, 3,899 refine.color fires and 593 revisit fires on five completed volumes — no chain has ever started on a real volume — *artefact:* ARTEFACTS.md:528-536
- (holo3) colour sim (--complete): 14 refine.color fires, 2 adoptions, certificate set and payload byte-identical to the pre-lane baseline (279/279, zero wrong) — *artefact:* ARTEFACTS.md:657-663

**Yield relevance.** decides-certificates — the chain decides what geometry the payload is finally read through, and it is live on paper today: 162 windows across the archived runs have already taken more revisions than holo2's cap allows, 8 of them three — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's, with one guard added: refuse a revision whose composed drift from the ORIGINAL accepted placement exceeds the single search box, or (cheaper and exactly holo2's guard) refuse a candidate affine the window has already stood at. holo3's chain is the strictly more capable design and it is what the hard-column rescue case wants (SCHEDULE.md:411-419), but 'the search moved away and came back' is the one failure mode holo2 built a named counter for and holo3 cannot see.

**Notes.**

*Reader:* Both sides' evidence is thin in opposite ways: holo2 measured the cap holding (never a third pose) on states where nothing re-sampled, and holo3 has never adopted a first revision on a real volume, so the chain is untested outside the colour sim's 2 adoptions. holo2's own text calls lifting the bar 'a measurement (does a chain of two bounded +-0.25-cell revisions beat one?)' — holo3 lifted it without that measurement, which is exactly the kind of row the plan's principle 2 asks to be investigated rather than ticked.

*Refuter (upheld):* *Corrections:* Add one verified fact that closes a hole a reader would otherwise worry about: the chain cannot spin, because `certified_fields` (holo3/plugins/refine.py:117-127) keeps EVERY address in the certificates handed to it and prepare_refine builds those from exactly the certified reach (refine.py:577-583), so after an adoption `basis == certified_reach` and `set(current) > set(basis)` is false until a new tile certifies. Also worth stating: because the second fit's basis is strictly larger, `placement_ordinal` (holo3/data.py:116-119) adopts step n+1 UNCONDITIONALLY on the basis term — quality never gets a vote in a chain — which is the mechanical reason an oscillation A->B->A is invisible (the row says this; the ordinal is why). holo2's bar reproduces at refine.py:210-242 + generation.py:34-49 as described.

*Reason:* The cap-vs-chain difference is real, unmeasured on both sides, and touches what geometry the payload is read through.

*Second lens (final: DIVERGED):* Upheld as a divergence, but its evidence is inverted by measurement. Both the reader and the refuter record 'no chain has ever started on a real volume', resting on the zero-adoption line in the parity doc. That zero is a counter defect (holo3/conversion_docs/POST-FORENSICS.md:20-70): adoption is folded at holo3/store.py:786-800 without appending any event, so route='refine' cannot appear. I counted adoptions the honest way — JobDone.n_poses per refinement job — directly on the archived event streams in scratch/holo3-overnight-events/. Result: adoptions everywhere (e029 240 on 932 fires, e029-postfix 31/126, xerox-k 65/156, xerox-k-postfix 67/168, c3-cmy7 168/327, c2-cmy7 569/1269, sheet I 1844/5128), and chains are real: 152 windows took exactly two adoptions and 8 took three (c2-cmy7 12+1, c3-cmy7 15+3, sheet I 124+4, plus one twice-revised window on each of three K runs). holo2's cap would have refused all 162. The refuter's spin-proof is correct as far as it goes (holo3/plugins/refine.py:117-127 and :577-583 make basis == certified reach after an adoption), but 'cannot spin' is not 'does not walk': composed drift over three steps is up to 0.75 cell and 0.45 degrees.

---

### refinement-05 — The no-op guard — refusing a revision that did not move

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **integrity** · ruling needed **Y** · seeds: B37

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a fit that lands back on a geometry already in play is committed, and whether an oscillating search is visible.

**holo2.** Two guards after the gate, reported separately on purpose. 'pose_unmoved': the canonical affine equals the standing LIVE pose — the fit moved away and came back, since the worker always fits from the SUPERSEDED subject pose. 'pose_already_stands': the affine equals an EARLIER pose of the same extent that the live pose has moved past, which a rising count exposes as a search oscillating between two answers. Before the gate there is a third, cheaper refusal, 'active_pose_selected', when the grid winner is the base pose itself.

*Where:* `holo2/src/holo2/solve/refine.py:419-457`; `holo2/src/holo2/solve/refine_fit.py:538-541` · *dial:* live

**holo3.** Two refusals inside refine_window: 'active_pose_selected' when the grid winner equals the base pose, and 'unchanged_affine' after the gate when the recomposed native affine equals the standing placement's. A non-adopted Revision folds as a no-op (store.py:794-796 returns before touching the placement). There is no third check, because holo3 keeps no superseded poses to compare against.

*Where:* `holo3/plugins/refine.py:486-490`; `holo3/plugins/refine.py:504-507`; `holo3/store.py:791-797`

*Scheduler row / doc:* SCHEDULE.md:51

**Implementation delta.** holo2's 'pose_unmoved' and holo3's 'unchanged_affine' are the same test against the standing geometry, but they mean opposite things because the two trees fit from different baselines: holo2 fits from the superseded parent (so returning to the live pose is an oscillation), holo3 fits from the standing placement (so returning to it is simply 'no movement'). holo2's second half, 'pose_already_stands', has no holo3 counterpart at all: holo3's store keeps exactly one Placement per window, so an earlier revision's affine is not knowable. holo3 also compares recomposed native terms for exact float equality where holo2 compares canonicalised pose keys (POSE_TERM_DECIMALS rounding), so a sub-quantum revision that holo2 would collapse to a no-op is committed by holo3 as a distinct affine.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) 0 of 545 adopted revisions were no-ops at W2, with revisions unread — *artefact:* holo2/src/holo2/solve/refine.py:41-47 (module docstring; no artefact in ARTEFACTS.md carries this count)
- (holo3) no artefact — holo3 has adopted zero revisions on any real volume (ARTEFACTS.md:528-536), so neither refusal string has ever been exercised there — *artefact:* ARTEFACTS.md:528-536

**Yield relevance.** integrity — source: reader.

**Recommendation.** keep holo3's, and fold the missing half into refinement-04's guard rather than as a separate mechanism: a per-window set of affines already stood at is one small store field and restores 'pose_already_stands' for free, which is the only thing that makes a chained refinement's oscillation visible.

**Notes.**

*Reader:* The float-exact comparison at refine.py:505 is worth a second look at merge time: holo2 deliberately canonicalises before comparing because 'the canonical rounding is what can make a sub-quantum revision collapse onto the geometry it started from' (refine.py:429-434). holo3 has no canonical pose rounding at all — its placement identity is the window id, not the affine — so the trap holo2 named cannot be reproduced there, but the counter cannot be either.

*Refuter (upheld):* *Corrections:* (1) Say in one word that the second half is ABSENT, not merely different: `pose_already_stands` (holo2 refine.py:445-457) has no holo3 counterpart, because holo3 keeps one Placement per window; that half belongs on the RULINGS list as a port/accept decision, and the row's current wording buries it. (2) Line nit: the non-adopted no-op fold returns at holo3/store.py:790-791, not :794-796. (3) The float-exact vs canonical comparison is confirmed: holo2 canonicalises to POSE_TERM_DECIMALS = 6 (holo2/src/holo2/solve/keys.py:39, :113) before the key compare; holo3 compares recomposed native terms with `==` (refine.py:504-505). (4) The '0 of 545 adopted revisions were no-ops' number is at holo2/src/holo2/solve/refine.py:45-46 as the row says — a docstring, no artefact.

*Reason:* Both guards reproduce at HEAD and the delta is stated correctly; only the ABSENT half needs to be named so the ruling list catches it.

---

### refinement-06 — Live-pose derivation — which geometry of a window the rest of the tree reads

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates — adopting a revision overwrites the window's geometry AND replaces its standing evidence, with no way back; a revision that reads worse in truth costs that window's tiles and cannot be undone** · ruling needed **Y** · seeds: B36, B37

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Which pose every downstream reader (sampling, done projection, colour lanes, diag) uses for a revised window; equivalently, whether a superseded geometry survives at all.

**holo2.** Poses accumulate: an adopted revision writes a NEW PoseRecord at a new key and nothing is retracted. StoreIndex.live_pose is a read-time derivation, 'the latest committed pose for that extent wins' (RULING I3), and it is the ONLY spelling of it in the tree; quarantine is deliberately not filtered there so the readers that must refuse a condemned pose do it themselves. The done projection takes ONE pose per posed window, the live one, rather than the union — measured, because the union over-claimed +860 done cells on e029 and +588 on xerox for revisions that had sampled nothing.

*Where:* `holo2/src/holo2/solve/tilemap.py:575-594`; `holo2/src/holo2/solve/tilemap.py:596-610`; `holo2/src/holo2/solve/tilemap.py:741-825`; `holo2/src/holo2/solve/refine.py:23-28` · *dial:* live

**holo3.** There is exactly one standing Placement per window. A RefineOutcome is folded by rebuilding the placement with route=refine and the fitted basis and passing it through the ordinary _fold_placement, which adopts it only if placement_ordinal ranks it above the standing one: (route == refine, len(refine_basis), -quality). The superseded affine is overwritten and gone. An adopted revision bumps pose_affine, recomputes the window's page cells and tile reach, and bumps pose_route, lane_poses, region_pitch and live_pages as ordinary consequences.

*Where:* `holo3/store.py:623-687`; `holo3/store.py:791-801`; `holo3/data.py:95-120`; `holo3/store.py:449-488`

*Scheduler row / doc:* SCHEDULE.md:87-88 (pose_affine / pose_route written by Placement, RefineOutcome); SCHEDULE.md:51

**Implementation delta.** holo2: many poses, one derived winner, recency decides ('latest committed'). holo3: one pose, a RANKING decides — refine-route beats any non-refine placement unconditionally, then longer basis, then lower quality. Two consequences. (a) After a revision, no ordinary placement can ever move the window again, however much better it scores; in holo2 a later committed pose simply becomes the live one. (b) quality mixes units in the ordinal: place writes a pilot mismatch rate (place.py:817), refine writes a held-out log-loss (store.py:797-799); the route and basis terms dominate so it is inert today, but the third term compares unlike quantities. holo3 also has no equivalent of holo2's 'live_pose is not quarantine-filtered' clause because it has no quarantine.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) unioning parent and revision added +860 done cells on e029 and +588 on xerox for revisions carrying zero evidence; under live-pose the projection moved DOWN -3,996 (e029) / -1,449 (xerox) — *artefact:* ARTEFACTS.md:559 (RF1 done coverage went DOWN); the +860/+588 union figure has no ARTEFACTS.md entry — it is stated only at holo2/src/holo2/solve/tilemap.py:762-770
- (holo3) no artefact — no holo3 realized done-gating rate on a real sheet exists (GAP G-09) — *artefact:* ARTEFACTS.md:823 (G-09)

**Yield relevance.** decides-certificates — adopting a revision overwrites the window's geometry AND replaces its standing evidence, with no way back; a revision that reads worse in truth costs that window's tiles and cannot be undone — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's — one standing placement is the simpler and safer answer, and it makes holo2's whole live-pose/generation apparatus unnecessary. Two things to record rather than build: the quality unit mixing in placement_ordinal (data.py:118-120) wants a comment or a separate field, and 'a refined placement can never be displaced by a better ordinary placement' is a deliberate property that no doc states.

**Notes.**

*Reader:* B36's done-projection half belongs to the done-gate family and I have not adjudicated it here; what is mine is the derivation itself. holo2's honest limit on the projection (a boundary sliver in either direction, UNMEASURED, and done_covered is permanent) does not transfer, because holo3's done gate is cut from the evidence cover rather than projected through a pose (store.py:449-468).

*Refuter (upheld):* *Corrections:* Consequence (a) is mis-attributed and must be re-worded. 'After a revision, no ordinary placement can ever move the window again' is true but NOT because of the route term: holo3's place row retires on `placed` for EVERY window (holo3/plugins/place_sched.py:224-226 `_place_eligible` requires `not state.placed`; :246-247 RETIRE_PLACED), and revisit's place branch requires `not state.placed` (holo3/plugins/revisit.py:31-34). So after ANY first placement no ordinary placement is scheduled for that window at all, refined or not; a second non-refine Placement fact can only arrive from an in-flight race. The route term of placement_ordinal is therefore inert in both directions today — which is worth recording as such, since the row currently presents it as a live property. Also: G-09 is at ARTEFACTS.md:813, not :823. Verified as stated: `_adopts` is strict `>` (store.py:44-46); `_fold_refine_outcome` writes quality = candidate_logloss (store.py:794-796) and re-derives page cells, window reach, lane_poses, region_pitch, live_pages (store.py:655-687); holo2's live_pose is the single spelling (tilemap.py:575-592) and the +860/+588 union figure is at tilemap.py:764-767 with no ARTEFACTS entry, as the row says.

*Reason:* The mechanism and the recommendation stand; one load-bearing sentence credits the wrong mechanism for the observed property.

*Second lens (final: CARRIED-DIFFERENT):* Upheld, with the refuter's re-attribution accepted and one addition of my own. Verified: holo3 keeps one placement per window and admits a new one only if it ranks higher (holo3/store.py:623-630 with holo3/data.py:116-119), the refinement fold rebuilds the placement and re-derives page cells, reach, lane poses, region pitch and live pages (holo3/store.py:786-800, :655-687). The refuter is right that 'a refined window can never be re-placed' is NOT the route term's doing: holo3/plugins/place_sched.py:224-226 makes the place row ineligible the moment a window is placed, and retires it, so no ordinary placement is ever scheduled again for any placed window. The route term is inert in both directions. My addition, which neither lens states: the replacement is destructive in a second way — resampling resets the window's context calibration to unadopted (holo3/plugins/calibrate.py:328 vs :507-517), so between the re-read and the region's context row re-firing, that window's cells are read without the context correction. holo2's accumulate has its own measured cost (thousands of evidence pieces stranded on non-live poses), so this is a genuine trade, not a free simplification.

---

### refinement-07 — The re-read after a revision — when and at what price the revised geometry is actually sampled

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates — the re-read is the only path by which an adopted revision reaches a decoder at all; and I can now bound what it bought: at most 3 distinct tiles on each of the two archived black-and-white sheets, out of 795 tiles under refined windows that were already certified** · ruling needed **Y** · seeds: B38

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether an adopted revision changes anything at all, and how early in the price order the revised geometry reaches the decoders.

**holo2.** A separate scheduler tier. _needs_resample asks four clauses (the live pose owns no evidence, some other pose of the extent does, neither is condemned, the scheduler has not already answered for this geometry) and re-admits an already-exited window as a TIER_RESAMPLE slot at price 200 + the lane term — the same number RF1 itself pays, so the consequence cannot preempt the ladder the revision waited behind. The fire re-samples exactly the superseded generation's cell set through the live pose, hands it to the ordinary emission block (which re-fits the window PAVA), and drops only the redundant pose write. It retires whether it emitted or refused.

*Where:* `holo2/src/holo2/solve/place_sched.py:393-470`; `holo2/src/holo2/solve/place_sched.py:307-315`; `holo2/src/holo2/solve/place_sched.py:331-346`; `holo2/src/holo2/solve/resample.py:201-266`; `holo2/src/holo2/solve/place_tiers.py:179-198` · *dial:* live

**holo3.** There is no separate re-read row. calibrate declares pose_affine in its read-set, so an adopted revision re-arms the ordinary calibrate worker at 15 + 2 per rung. window_job branches: with standing evidence in hand it calls resample_window, which samples the STANDING EVIDENCE'S page cells at the new affine and reuses its format reference values, so the cell set is frozen and only the geometry moves; the PAVA is re-fitted and ctx_adopted resets to False. The new WindowEvidence replaces the old one and bumps evidence_fit / evidence_read, which re-arms every tile row over the window.

*Where:* `holo3/plugins/calibrate.py:641-673`; `holo3/plugins/calibrate.py:349-375`; `holo3/plugins/calibrate.py:717-720`; `holo3/plugins/calibrate.py:730-732`; `holo3/store.py:653-663`

*Scheduler row / doc:* SCHEDULE.md:42 (calibrate row, reads pose_affine), SCHEDULE.md:60 (price 15), SCHEDULE.md:87 (pose_affine written by RefineOutcome)

**Implementation delta.** Mechanism: holo2 re-admits the window to the placement scheduler through a bespoke door with a four-clause predicate and its own tier; holo3 gets the same effect from one declared read (pose_affine) on a row that already exists. Price and therefore timing: holo2 charges 200 + 2/rung, so the re-read waits behind the whole ladder exactly as the revision did; holo3 charges 15 + 2/rung, so the revised geometry is read almost immediately after adoption, before any remaining placement or payload work. Frozen cell set: both freeze it, holo2 by reading it back off the superseded pieces, holo3 by reading it off the standing evidence. Termination: holo2 bounds re-entries by an in-memory _placed_pose memo (and admits one extra pass per refusing window per resume); holo3 needs no memo because the job is idempotent in the standing facts and re-fires only when a read key moves. holo3 also has no quarantine clause and no 'never re-read condemned pieces' law, because it has no quarantine.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) re-read census: 239/239 and 255/255 'resampled', no refusals — *artefact:* ARTEFACTS.md:563
- (holo2) F2 resume +13 / +12 — and explicitly SUPERSEDED: these 'PREDATE R2/R3/R4 and must not be carried forward as the post-fix result' — *artefact:* ARTEFACTS.md:564
- (holo2) F1+F2 combined: +27 e029 / +32 xerox (1,911 -> 1,938; 1,882 -> 1,914) at +112% / +386% wall — *artefact:* ARTEFACTS.md:560
- (holo3) no artefact isolates the re-read: holo3 has adopted zero revisions on a real volume, so resample_window's refine-driven branch has never fired outside sims — *artefact:* ARTEFACTS.md:528-536

**Yield relevance.** decides-certificates — the re-read is the only path by which an adopted revision reaches a decoder at all; and I can now bound what it bought: at most 3 distinct tiles on each of the two archived black-and-white sheets, out of 795 tiles under refined windows that were already certified — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's — folding the re-read into calibrate removes a whole scheduler door, a four-clause predicate and an in-memory memo, and reading the revised geometry EARLIER is strictly better for yield (the revision's consequence stops being gated behind work the revision has already outranked). One thing to check before Gate B: holo3's resample branch fires on ANY pose_affine change, not only a refine adoption, so a re-placed window is re-read at the OLD evidence's cell set rather than at the cell set its new placement implies (calibrate.py:661-668 vs store.py:658-661, which does recompute _page_cells). Confirm that a non-refine re-placement can actually happen (placement_ordinal, data.py:118) and, if it can, decide whether the resample branch should be keyed on route == refine.

**Notes.**

*Reader:* holo2's +27/+32 is the ONLY measured yield the whole refinement family has on either side, and it is a combined F1+F2 number — it does not separate the revision from the re-read, and it was bought at +112%/+386% wall. The seed's +13/+12 for F2 alone is explicitly retracted by ARTEFACTS.md:564. Neither number can be carried as a prediction for holo3, both because the trees' baselines differ (refinement-02) and because holo3 spends nothing here today.

*Refuter (upheld):* *Corrections:* Three additions, one of them material. (1) MATERIAL: holo2's re-read is NOT 'exactly the superseded generation's cell set read through the live pose' — the cell set is exact, the POINTS are not. resample.py:243 calls the same displaced `refine_fit.local_segment`, so every re-read mean is read half a cell (=-A@(0.5,0.5)) from where generation zero read that cell (proved, refinement-02). Its own comment claims the opposite at resample.py:236-242 ('the only difference between these means and the committed ones is the geometry'). This re-weights the F2 leg of the family exactly as it re-weights F1, and the row must say so. (2) The +27/+32 must not be left attributable to the re-read: the ownership key alone is worth 27 e029 + 27 xerox (ARTEFACTS.md:496), so the combined F1+F2 figure leaves at most +0/+5 for this mechanism. (3) The row's own pre-Gate-B check is answerable now without a run: a non-refine re-placement is unreachable except by an in-flight race (see refinement-06), so keying holo3's resample branch on route == refine buys nothing today; what the race would produce is a re-read of the OLD evidence cells at the NEW affine while store._page_cells/_window_reach already hold the new ones (calibrate.py:658-663 vs store.py:655-661) — bounded, race-only, worth one sentence rather than a guard. Everything else verified: _needs_resample's four clauses (place_sched.py:394-470), RESAMPLE_TIER 200 + lane term (place_tiers.py:179-198), holo3's calibrate read-set (KEY_POSE_AFFINE, KEY_REGION_PITCH) at calibrate.py:715-720 and price 15 + 2*level at :730-732, the frozen cell set and ctx_adopted reset at calibrate.py:349-375 / :328.

*Reason:* The comparison as written credits holo2's re-read with a fidelity it does not have and with yield the ownership key earned.

*Second lens (final: CARRIED-DIFFERENT):* Upheld, with the refuter's material correction accepted and two evidence claims replaced by measurement. Verified: holo3 has no separate re-read row — the ordinary calibrate worker declares the window geometry in its read set (holo3/plugins/calibrate.py:715-720) at price 15 + 2 per level (:730-732), and its job branches to resample_window, which re-samples the standing evidence's own cells and reference values at the new geometry (holo3/plugins/calibrate.py:349-356). holo2 instead re-admits the window through a four-clause predicate into its own tier at price 200 (holo2/src/holo2/solve/place_sched.py:394-470, holo2/src/holo2/solve/place_tiers.py:179-198). The refuter is right that holo2's re-read is NOT the same points: it calls the displaced local_segment (holo2/src/holo2/solve/resample.py:243) while its own comment at :236-242 claims the only difference is the geometry. Two of the row's evidence lines are wrong and I replaced them from the archived streams: holo3's refine-driven re-read HAS fired on paper (every window with an adopted revision in the archived xerox and e029 runs shows further calibrate fires), and I measured an upper bound on what refinement bought — mapping each adopted window's extent to the tiles it covers and asking which of those tiles certified only AFTER the adoption gives at most 3 distinct tiles on xerox-k-postfix, 3 on e029-postfix, 22 on the richer e029 run and 1 on xerox-k. Upper bound, not attribution: a later certification under a refined window may equally be the retry row or a finer level.

---

### refinement-08 — Two generations of evidence, and which one decodes

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B39

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a superseded read and a live read can meet in one payload freeze, and whether a parent's reading survives a revision.

**holo2.** Both generations' pieces stay committed forever; live_generation reduces at the READ: per window, if the live pose holds at least one of the keys in hand, keep only its pieces, otherwise keep all of them. That is the identity on every state written before the re-read existed, which is why the rule is 'newest that HAS pieces' and not index.live_pose — reducing to the live pose alone would have deleted 4,392 / 4,117 pieces. The reduction is answerable from live_poses alone only because an extent carries at most two generations.

*Where:* `holo2/src/holo2/solve/generation.py:118-150`; `holo2/src/holo2/solve/generation.py:10-49`; `holo2/src/holo2/solve/payload.py:597-649`; `holo2/src/holo2/solve/resample.py:65-80` · *dial:* live

**holo3.** There is one WindowEvidence per window and a re-read replaces it in place; the parent's scores, knots and losses are overwritten and not recoverable. The property holo2's rule exists to buy — a superseded read and a live read never meeting in one freeze — holds by construction, with no reduction step, no ordinal and no generation vocabulary anywhere in the tree.

*Where:* `holo3/store.py:700-747`; `holo3/plugins/calibrate.py:658-668`; `holo3/plugins/tiles.py:206-245`

*Scheduler row / doc:* SCHEDULE.md:90-91 (evidence_fit / evidence_read written by WindowEvidence)

**Implementation delta.** holo2 keeps both readings on disk and adjudicates at read time; holo3 keeps one and adjudicates by overwriting. The invariant is the same and holo3's spelling is unconditional (it cannot be got wrong by a third generation), but holo3 loses the ability to fall back: if a revision's re-read is WORSE than the parent's, holo2 still has the parent's pieces committed (even if no reader currently prefers them) while holo3 has destroyed them. Certificates already minted are unaffected on both sides.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) 4,392 / 4,117 evidence pieces hang on a non-live pose on the two archived states; 269/1,228 and 272/1,282 windows carry two committed poses — *artefact:* ARTEFACTS.md:555
- (holo2) the first holo2-only tiles (0,42,3) e029 and (0,5,21), (0,7,0), (0,27,36) xerox — v1 retains uncertified evidence on all four — *artefact:* ARTEFACTS.md:562
- (holo3) no artefact — the branch has never fired on a real volume — *artefact:* ARTEFACTS.md:528-536

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's. The fallback holo2 retains is not actually used by any holo2 reader (live_generation prefers the live pose whenever it has pieces), so the loss is theoretical on holo2's own terms; v1's lane separation, where BOTH readings stay decodable and a certificate may still be minted from the base lane, is the real capability neither successor has, and that belongs to the W2 map.

**Notes.**

*Reader:* This row and refinement-04 are one design on holo2's side: 'newest that HAS pieces' is answerable without an ordinal ONLY because the revision cap holds. holo3 lifted the cap (refinement-04) and dissolved the problem (this row) at the same time, which is coherent — but it means the holo2 module that names the trap (generation.py:45-49, 'a THIRD generation would make this rule under-determined') has no holo3 anchor to point at, and the comment carry should not try to give it one.

*Refuter (upheld):* *Corrections:* Verified verbatim: live_generation's 'newest that HAS pieces' rule (holo2/src/holo2/solve/generation.py:116-148) and the module's own statement that a THIRD generation would make it under-determined (:45-49); holo3 has one WindowEvidence per window, replaced in place (store fold + calibrate.resample_window at calibrate.py:349-356). Nothing to change. One clarification worth a clause: holo3's re-read also destroys the parent's KNOTS and PROBS, not only its scores, which is what makes refinement-11's 'chained fits score through the re-fitted PAVA' unavoidable rather than a choice.

*Reason:* Both spellings reproduce at HEAD and the invariant claim is correct on both sides.

---

### refinement-09 — The region context fit must see the re-read's evidence

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B41

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether the context correction that is applied at decode assembly was fitted over the geometry the cells were actually read at.

**holo2.** The 2026-08-23 fix: the ctx fit names region_evidence_collection_key in its read-set, so the pieces a re-read commits bump that key and the pool re-fits over the live generation at its own price. The omission was measured, not theoretical — 0 of 4 pools on either real sheet had a fit that had seen a re-read's pieces, which is what made the live pose publish no held-out loss on exactly the windows the re-read had made decode-authoritative.

*Where:* `holo2/src/holo2/solve/calibration.py:577-628`; `holo2/src/holo2/solve/resample.py:39-54` · *dial:* live

**holo3.** The ctx descriptor's read-set is (evidence_fit, wid) for every window of the region, so a re-read's new evidence bumps evidence_fit and re-arms the region fit at 15 + 2/rung. The re-read also resets ctx_adopted to False on the fresh evidence (calibrate.py:328), so the corrected read is not carried over from the previous geometry.

*Where:* `holo3/plugins/calibrate.py:738-742`; `holo3/plugins/calibrate.py:768-781`; `holo3/store.py:735-747`; `holo3/plugins/calibrate.py:307-328`

*Scheduler row / doc:* SCHEDULE.md:44 / :62 (ctx row at price 15) and SCHEDULE.md:90 (evidence_fit read by ctx)

**Implementation delta.** Same intent, different plumbing: holo2 needed a bespoke collection key added at review time because its ctx fit subscribed to a pool rather than to the members; holo3's ctx already subscribes per member window, so the property is a consequence of the ordinary read-set rather than a fix. holo3 additionally clears the adopted-context flag on the fresh evidence, which holo2 has no counterpart for (its ctx correction lives outside the evidence record, applied at decode assembly).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) before the fix: 0 of 4 pools on either real sheet had a fit that had seen a re-read's pieces; 0 of 255 xerox re-read poses had a published window loss — *artefact:* ARTEFACTS.md:502
- (holo2) CA2 context fit on real sheets: 4 fits each sheet, every one ADOPTED, zero refusals, held-out log-loss deltas -0.052 to -0.094 — *artefact:* ARTEFACTS.md:499
- (holo3) no artefact isolates a re-read-driven ctx refit — *artefact:* ARTEFACTS.md:528-536

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — the subscription is already the right shape and needs no port. Worth one line in the map: holo2 paid a review cycle to discover this and holo3 gets it for free from per-member reads, which is the strongest single argument in this family for the declared-reads model.

**Notes.**

*Reader:* The ctx row re-fits the WHOLE region on any member's re-read, at 15 + rung, so on a sheet where refinement actually adopts, holo3 will pay noticeably more ctx fits than holo2 did (holo2 measured 4 per sheet). No artefact bounds that cost on holo3, and it will not show until refinement adopts something on a real volume.

*Refuter (upheld):* *Corrections:* Verified on both sides (holo2 calibration.py:577-600 names region_evidence_collection_key with the measured 0-of-4-pools justification; holo3 _ctx_reads is per-member (KEY_EVIDENCE_FIT, wid) at calibrate.py:739-742, ctx price 15 + 2*level at :748-750, ctx_adopted cleared on the fresh evidence at :328). Add one consequence the row understates: `_corrected_row` (calibrate.py:507-517) also REPLACES heldout_logloss with the context-corrected loss, so a re-read does not merely un-adopt the context — it reverts the window's published loss to the marginal one until the region re-fits, which is precisely the window the ownership key (refinement-10) reads.

*Reason:* Same intent, different plumbing, correctly stated; the subscription really is per-member at HEAD.

---

### refinement-10 — The owner-loss fallback for a pose with no published loss

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B41

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which window owns a contested cell in a payload freeze when the standing geometry has not published a held-out loss.

**holo2.** The other half of the 2026-08-23 pair: a live pose with no published loss falls back to its extent's SIBLING generation's loss instead of infinity. Measured before the fix: 0 of 6 re-read windows had a loss for their live pose, while 6 of 6 had one for the parent, so without the fallback exactly the windows a re-read had made authoritative sorted to the bottom of the ownership key.

*Where:* `holo2/src/holo2/solve/ctx_apply.py:117-166`; `holo2/src/holo2/solve/payload.py:781-833` · *dial:* live

**holo3.** The ownership key reads the standing evidence's heldout_logloss and falls back to infinity when it is None (tiles.py:212-213). The state holo2's fix exists for cannot arise: there is one evidence per window, a re-read re-fits and re-publishes the loss in the same fact, and there is no sibling generation to borrow from.

*Where:* `holo3/plugins/tiles.py:206-245`; `holo3/plugins/calibrate.py:292-328`; `holo3/store.py:700-747`

*Scheduler row / doc:* SCHEDULE.md:42 (calibrate publishes WindowEvidence carrying heldout_logloss)

**Implementation delta.** holo2 needed a cross-generation fallback because its poses and pieces are separate records that can be out of step; holo3 publishes geometry-derived scores and their held-out loss in one WindowEvidence fact, so 'the standing geometry has no loss' means the fit was refused, and infinity is then the right answer rather than a bug. No port is possible or meaningful.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) 0 of 6 re-read windows had a loss for their live pose while 6 of 6 had one for the parent; 0 of 255 xerox re-read poses had a published window loss — *artefact:* ARTEFACTS.md:502
- (holo2) the ownership key itself is worth 27 e029 + 27 xerox certificates against pose-id order — *artefact:* ARTEFACTS.md:496-497
- (holo3) no artefact — structural, verifiable by reading tiles.py:206-245 and calibrate.py:292-328 — *artefact:* ARTEFACTS.md:528-536

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's; record the row as closed by construction rather than as a carry, so a future reader does not go looking for the fallback and conclude it was dropped.

**Notes.**

*Reader:* The ownership key itself (B40) is the evidence-and-ownership family's row, not mine; what is mine is only the re-read's interaction with it. I could not find any holo3 path that leaves a standing accepted evidence without a heldout_logloss, but I did not exhaustively check the plane_k and colour producers of WindowEvidence (plugins/plane_k.py:412-421 does gate on it being non-None).

*Refuter (upheld):* *Corrections:* The row's open caveat can be closed and should be: holo3 has exactly ONE `WindowEvidence(` construction (calibrate.py:310) and exactly one accepted CalibrationFit (calibrate.py:288-290), which always carries a float loss; plane_k reaches evidence through the same calibrate.window_evidence (plane_k.py:397); the only `replace` on an evidence row is _corrected_row (calibrate.py:516-517), which sets the loss rather than clearing it. So 'an accepted standing evidence always publishes a heldout_logloss' is verified structurally, and the inf branch at tiles.py:212-213 really is unreachable for accepted rows. Keep the classification and the 'closed by construction' recommendation.

*Reason:* holo2's cross-generation fallback answers a state holo3 cannot reach, and I verified holo3 cannot reach it.

---

### refinement-11 — Which calibration the refinement scores through

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B37

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** The probability map applied to every candidate's sampled means, and hence the log-loss the adoption gate compares.

**holo2.** Generation-zero replay: the pose's evidence cites a frozen CalibrationRecord by key, and refine reads its PAVA knots and probabilities back out of the params blob. detect.Calibration also wants n_search, which the blob does not carry, so it is reconstructed as the smallest integer admitting the stored probabilities — sound rather than approximate, since llr reads only knots and probabilities. A window whose calibration cannot be replayed refuses 'no_generation_zero_calibration' before a pixel is read.

*Where:* `holo2/src/holo2/solve/refine.py:122-131`; `holo2/src/holo2/solve/refine.py:328-353`; `holo2/src/holo2/solve/refine.py:495-500` · *dial:* live

**holo3.** refine reads knots and probs straight off the STANDING WindowEvidence and calls calibration_llr with them; there is no n_search to reconstruct because holo3's llr does not take one. A window with no accepted evidence is refused in prepare_refine (refine.py:572-573) rather than inside the fit.

*Where:* `holo3/plugins/refine.py:436-441`; `holo3/plugins/refine.py:571-573`; `holo3/plugins/calibrate.py:292-328`; `holo3/lib/pava.py`

*Scheduler row / doc:* SCHEDULE.md:51 (refine reads evidence_fit, evidence_read)

**Implementation delta.** holo2 replays the FROZEN generation-zero fit (the calibration the pose's pieces were decoded under) and reconstructs a constructor argument to do it; holo3 uses whatever calibration the standing evidence currently carries. For a first refinement those are the same fit. For a chained refinement (refinement-04) they are not: holo3's second fit scores through the PAVA re-fitted at the first revision's geometry, which is arguably the right baseline but is a different quantity from holo2's, and holo2 could not reach the case at all because it capped the chain at one.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) no artefact — the replay is described only at holo2/src/holo2/solve/refine.py:122-131 — *artefact:* holo2/src/holo2/solve/refine.py:122-131
- (holo3) no artefact — holo3 has adopted zero revisions on a real volume, so no chained fit has ever been scored — *artefact:* ARTEFACTS.md:528-536

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — 'score through the calibration the current evidence was fitted under' is the only convention that stays coherent once chaining exists, and it removes a reconstruction step. Record the difference so nobody reads the chained fit as a generation-zero replay.

**Notes.**

*Reader:* holo3's arrangement also gives it the property holo2's docstring claims for itself but arguably does not have (refinement-02): because refine crops and filters with calibrate's own primitives over calibrate's own points, refine's baseline logits ARE the LLRs the standing evidence carries. I verified the crop bounds, aperture and interpolation match (calibrate.py:201-209 vs :229-244, both via _crop_bounds and _aperture_px); the only difference is the out-of-crop fill value (median of the raw crop for window_crop, 0.0 for sampled_window_means), which touches only points outside the crop.

*Refuter (upheld):* *Corrections:* Two precisions. (1) The row (and its notes) claim holo3's refine baseline logits ARE the standing evidence's LLRs. Measured: the two point sets agree to 4.5e-13 px but are NOT bit-identical (216 of 500 points exactly equal in a synthetic check) because the two paths compose the affine in a different order (calibrate.scan_points_yx does (cells+0.5)@M.T+t; refine goes through the re-origined local pose). The sampling primitives themselves ARE bit-identical: sampled_window_means and window_crop+sample_points returned max-abs-diff 0.0 on both of _lattice_indices' branches. Say 'to within float rounding', so nobody later writes a bit-exact pin that fails. (2) A mechanism the row omits: v1's refine applies the ADOPTED CONTEXT OFFSETS when the generation-zero detector is the context profile (src/holo/receive/certified_refine.py:703-715), holo2 deliberately does not (refine.py:135-140), and holo3 does not either — it scores through the marginal PAVA off evidence.knots/probs (refine.py:436-441) while the standing evidence's published loss, on a ctx-adopted window, is the CORRECTED one (calibrate.py:513-517). So holo3 sides with holo2 against v1 here, and the refinement gate optimises a different detector from the one the tiles decode through. That belongs in the row's delta.

*Reason:* The 'score through the current evidence's calibration' rule is stated correctly; the equality claim is float-approximate and the context arm is missing.

---

### refinement-12 — Re-arm and spend identity — what makes refinement ask again

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B37

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** How often a refinement fire is attempted as the certificate frontier grows; it orders and prices work rather than deciding a verdict, but it decides whether a late first chance is ever taken.

**holo2.** The worker's read-set is the pose key plus the GLOBAL certified collection, so any new certificate anywhere re-arms every eligible refinement descriptor: one spend per (pose, certificate-frontier version), k = 1, no 'at least k new certificates' tightening. The coarseness is deliberate and argued — a reach-scoped certified membership would be a new durable mechanism, and the cost of the coarse wake is descriptor arming, not spends, since an unchanged reach re-derives the same refusal.

*Where:* `holo2/src/holo2/solve/refine.py:380-403`; `holo2/src/holo2/solve/refine.py:41-47` · *dial:* live

**holo3.** Reach-scoped: the read-set is (evidence_fit, evidence_read, pose_affine, pose_route) for the window plus one tile key per (tile in the window's pose-derived reach, stream). Certificates outside the reach do not wake it. The gate that stops a re-fire from repeating work is the basis-superset clause, not a spend memo.

*Where:* `holo3/plugins/refine.py:622-633`; `holo3/plugins/refine.py:537-542`; `holo3/store.py:217-223`

*Scheduler row / doc:* SCHEDULE.md:107-112 — 'it subscribes to the certified tiles in its reach, both halves of its own evidence and its own pose, so any change to those re-fires it — including a first chance arriving late'

**Implementation delta.** holo2 wakes on the whole certificate frontier and relies on the fire's own refusal to be cheap; holo3 wakes only on the tiles in reach, plus its own evidence and pose. holo3's is strictly narrower and cannot miss a wake that matters, because a certificate outside the reach cannot change the label set or the residue. One asymmetry to note: holo3's reads use the POSE-derived window_reach while eligible, retire and prepare use the EVIDENCE-derived evidence_reach (refine.py:627 vs :641/:653/:576); the two differ after a pose moves and before the re-read lands, which is a deliberate over-declaration (extra wakes, never wrong results, per SCHEDULE.md:383-386).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) post step 2 on e029: the widened re-arm took refine fires 106 -> 406 and revisit 0 -> 124, all crediting 0 certificates, at 1.16x wall — *artefact:* ARTEFACTS.md:99
- (holo2) RF1 churn: +1,784 commits on e029 (+15.5%), +1,618 on xerox (+13.2%), for zero certificates; 274 expansions x 270 = 73,980 mints vs a dial-off control's 2 x 0 — *artefact:* ARTEFACTS.md:558

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's. The e029 post-step-2 number is the honest cost of the widening (4x the fires for 1.16x wall and no yield); it is cheap and it is what makes a late first chance reachable, which is the whole point of the REFINE named problem (SCHEDULE.md:414-419).

**Notes.**

*Reader:* holo2's churn number is the closest thing either side has to a bound on this mechanism's cost, and it is not transferable: holo2's fires ADOPTED (and each adoption commits), holo3's refuse. The comparison that would matter — cost per fire on a sheet where refinement adopts — does not exist on either side.

*Refuter (upheld):* *Corrections:* Verified: holo2's read-set is (COLLECTION_CERTIFIED, pose) with the module arguing for the global collection (refine.py:380-403); holo3's is per-window evidence/pose plus one key per (tile in window_reach, stream) (refine.py:622-633). Strengthen the row's 'cannot miss a wake' with the mechanism that makes it true: the engine RE-DERIVES a worker's reads whenever a KEY_POSE_AFFINE for its own subject moves (holo3/engine.py:415-421 in `_touch`, via `_rederive_reads` :341-358), and `_births` adds fresh keys to a standing worker (:394-401) — so the pose-derived reach subscription is refreshed exactly when the reach changes, which is why the window_reach/evidence_reach split is safe rather than merely over-declared.

*Reason:* Both re-arm identities are as described, and the narrower holo3 subscription is provably wake-complete at HEAD.

---

### refinement-13 — The price of refinement and its rung premium

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only — but with teeth: I measured that in an ordinary run that closes, holo3's refinement never fires at all, so this price is what makes the whole family a harvest-only lane today** · ruling needed **Y** · seeds: B37

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Where refinement sits in the drain order relative to cold search and the payload tail; ordering only, but it decides what work is still pending when a close preempts.

**holo2.** COST_REFINE = 200, above TIER_COLD_REST (150), the dearest tier the placement table declares, so 'after the ladder' is emergent rather than a phase. The descriptor carries the ordinary lane term (LANE_COST_PER_RUNG = 2 per rung), while cold passes carry COLD_COST_PER_RUNG = 20, so refine is OVERTAKEN by cold_rest from rung 3 (210 > 206) and cold_live from rung 4 — an inversion the module records as the open half of the price, reachable on any 4800-dpi capture.

*Where:* `holo2/src/holo2/engine/recipe.py:376`; `holo2/src/holo2/engine/recipe.py:593-597`; `holo2/src/holo2/solve/refine.py:634-637`; `holo2/src/holo2/solve/place_tiers.py:120-176` · *dial:* live

**holo3.** REFINE_COST = 200 flat, with no rung term at all — _refine_cost ignores stage, attempts and last_cost. Cold is repriced to 250/260 and still carries 20 per rung, so refinement now precedes cold unconditionally at every depth. Refinement shares the 200 seat with refine.color and revisit.

*Where:* `holo3/plugins/refine.py:67-69`; `holo3/plugins/refine.py:663-665`; `holo3/plugins/place.py:85-89`; `holo3/SCHEDULE.md:58-82`

*Scheduler row / doc:* SCHEDULE.md:73-75 (refine / refine.color / revisit all at 200) and SCHEDULE.md:84-85 (cold_live 250, cold_rest 260)

**Implementation delta.** Two changes compose. (a) holo3 drops the per-rung lane premium on refinement, so a coarse-rung and a fine-rung revision tie at 200, where holo2 drained coarse rungs first. (b) cold moved from 140/150 to 250/260, which removes the inversion holo2 flagged: in holo3 refinement always precedes cold, at every rung. holo3 also has no ageing/rework band on this row (SCHEDULE's '*n' marker is absent for refine), so a repeatedly-refusing refinement never gets dearer.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) price ladder: refine / refine.color / revisit 200; cold_live 250, cold_rest 260; calibrate / color / ctx 15; payload rows 20 — *artefact:* holo3/SCHEDULE.md:58-85
- (holo2) no artefact measures the refine/cold crossover; the inversion is stated only at holo2/src/holo2/engine/recipe.py:320-335 — *artefact:* holo2/src/holo2/engine/recipe.py:320-335

**Yield relevance.** decides-order-only — but with teeth: I measured that in an ordinary run that closes, holo3's refinement never fires at all, so this price is what makes the whole family a harvest-only lane today — source: second lens (reader said: decides-order-only).

**Recommendation.** keep holo3's. Removing the inversion answers the one open question holo2 left on this number, and the missing rung premium only matters if refinement ever becomes expensive enough to want coarse-first draining — which the zero-adoption record says it is not.

**Notes.**

*Reader:* Pricing is the pricing family's territory and I record this compactly. The one refinement-specific consequence worth carrying into the map: because holo3's re-read now costs 15 rather than 200 (refinement-07), the refinement price no longer covers its own consequence, which was holo2's explicit design ('charging the re-read LESS would let it preempt the ladder the revision itself waited behind', place_tiers.py:184-186). In holo3 the re-read DOES preempt that ladder, deliberately.

*Refuter (upheld):* *Corrections:* Numbers all check (holo2 COST_REFINE=200 recipe.py:376, RESAMPLE_TIER 200 place_tiers.py:179-198, LANE 2 / COLD 20 place_tiers.py:120-134, the crossover table recipe.py:314-335; holo3 REFINE_COST 200 flat refine.py:67-69 and _refine_cost :663-665, cold_live 250 / cold_rest 260 SCHEDULE.md:82-83 with COLD_COST_PER_RUNG still applied in place.stage_price :86-91). One interpretation must change: holo3 does NOT 'remove the inversion holo2 flagged' — it universalises it. holo2's ruled property is 'a revision fires only when nothing cheaper is ready' (refine dearest); its measured exception is that refine outranks cold from rung 3 up. holo3 prices cold ABOVE refine at every depth, so refinement precedes cold at rung 0 too: the exception became the rule, and holo2's open question ('raise COST_REFINE to 240 so the property is unconditional', recipe.py:328-334) was answered in the opposite direction. Keep the recommendation, restate the justification as a deliberate reordering (cold is now the desperate work at the top) rather than as a fix.

*Reason:* Every price is right; the sentence that justifies keeping holo3's inverts what holo2's ruling actually wanted.

*Second lens (final: CARRIED-DIFFERENT):* Upheld as order-only; the refuter's reinterpretation accepted; and I add the measurement that makes the row matter. Prices verified: holo3 refinement 200 flat with no level premium (holo3/plugins/refine.py:67-69, :663-665) against cold search 250/260 plus 20 per level (holo3/plugins/place.py:41-52, :85-89); holo2 refinement 200 plus 2 per level against cold 140/150 plus 20. The refuter is right that holo3 does not remove holo2's inversion, it universalises it — holo2 wanted refinement to be the last thing tried and recorded the crossover as a defect; holo3 answers the opposite way and makes cold the last thing tried. The measurement neither lens has: on the SAME capture and the same format, the current tree's ordinary e029 decode (scratch/page-domain-qual/base-e029-run.64152/argv, no --complete) closes verified at 1,357 certificates with ZERO refinement fires, while the archived full-harvest run of that identical capture (--complete, holo3/conversion_docs/overnight/ledger.jsonl step e029-postfix) fires refinement 126 times, adopts 31 and reaches 1,938. At price 200 the refinement seat is drained only after the payload has already closed.

---

### refinement-14 — refine.color — the colour refinement lane

**HOLO3-ONLY** · evidence **n/a** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter upheld.

**What it decides.** Whether colour windows get their geometry re-fitted against certified cargo, which the gap forensics attribute 53 of 58 colour-volume misses to.

**holo2.** Absent — holo2 never decoded colour at all. There is no colour refinement, no colour lane, and no counterpart mechanism to compare against.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** v1's color_refine numerics carried verbatim on top of K's shared search machinery: labels are per-plane presence bits (furniture contributes all three planes, certified cargo the planes its certificates reconstruct), the fit is K's two-stage grid on a frozen per-plane affine calibration minted from the baseline pose, and the gate is held-out improvement plus a furniture non-regression at slack 1e-9. It subscribes per stream to the certified tiles in its reach, to its own pose and to the lane's plane fields; eligibility is the basis-superset clause alone, with 'nothing left to gain' expressed only as the retire predicate. An adopted revision folds as an ordinary Placement with route refine, which re-fires the whole colour lane through the declared reads.

*Where:* `holo3/plugins/color_refine.py:81-115`; `holo3/plugins/color_refine.py:300-348`; `holo3/plugins/color_refine.py:351-368`; `holo3/plugins/color_refine.py:371-413`; `holo3/plugins/color_refine.py:415-481`

*Scheduler row / doc:* SCHEDULE.md:52 (refine.color row), SCHEDULE.md:113-125 (the refine.color debt row), SCHEDULE.md:400-403 and :417-421

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo3) colour sim (--complete): 14 fires, 2 adoptions; certificate set and payload byte-identical to the pre-lane baseline (279/279, zero wrong); workers 1 == 8 byte-identical — *artefact:* ARTEFACTS.md:657-663
- (holo3) 3,899 refine.color fires across the five completed post-change volumes, producing 0 route=refine poses; on c2-cmy7 and sheet I that is 788 and 2,950 colour-lane fires for no adoption — *artefact:* ARTEFACTS.md:528-536
- (v1) colour refinement cost with zero yield: ~550 s on the 20x2 scrap corpus, 986 window crop+grid fits across 16 barriers, ~94% of the payload bucket — *artefact:* ARTEFACTS.md:544

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** no action for the holo2 map

**Notes.**

*Reader:* Listed because it shares the 200 seat and the whole K search machinery with refine, and because its zero-adoption record is the larger half of the family's measured silence. The comparison that matters for it is v1's color_refine, which is the W2 map's row (GAPS attributes 53 of 58 colour misses to its absence; POST-FORENSICS §A.4 reconciles that with the zero-adoption finding).

*Refuter (upheld):* *Corrections:* Verified at HEAD: FURNITURE_LOSS_SLACK = 1e-9 (color_refine.py:60), the gate at :335-339, eligibility = `bool(reach) and set(reach) > set(basis)` with no residue clause (:359-362, descriptor :437-444), exhaustion only in retire (:365-368, :447-453), per-stream tile + plane-field reads (:420-434), the +0.5 present in the colour write-back too (revised_native_affine :171-184). Both cited holo3 numbers reproduce (ARTEFACTS.md:657-663 and :528-531). One addition for the map: the colour lane's basis is a tuple of (page,ty,tx,stream) CertKeys while K's is (page,ty,tx) triples, and both live in the same Placement.refine_basis whose LENGTH is a placement_ordinal term — harmless because family gates the rows, but it means `len(refine_basis)` is not comparable across families.

*Reason:* holo3-only, described accurately, nothing owed to the holo2 map.

---

### refinement-15 — revisit — the mop-up row, priced with refinement

**HOLO3-ONLY** · evidence **n/a** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter upheld.

**What it decides.** Whether a calibration-refused or never-placed window gets a second chance once its neighbourhood certifies.

**holo2.** Absent as a distinct mechanism. holo2's nearest equivalents are the park/dormancy wake channels (ring, donor, seed) in place_sched, which re-offer a ladder-exhausted window; a window whose emission refused simply exits.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** Born from a certificate. A placed window whose evidence was refused re-fires the calibrate body; a never-placed window re-fires a ring-stage place pass off untried seeds. Both are gated by the done gate ahead of either branch, and both are priced at refine's 200. It is v1's M-pass expressed as a subscription rather than a phase.

*Where:* `holo3/plugins/revisit.py:27-55`; `holo3/plugins/revisit.py:58-101`; `holo3/plugins/revisit.py:104-133`; `holo3/plugins/revisit.py:136-150`

*Scheduler row / doc:* SCHEDULE.md:53 (revisit row), SCHEDULE.md:126-128 (the revisit debt row), SCHEDULE.md:411-414 (MOP-UP)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo3) 593 revisit fires across the five completed post-change volumes, crediting 0 certificates; on e029 post step 2, revisit went 0 -> 124 fires for 0 certificates — *artefact:* ARTEFACTS.md:528-536, ARTEFACTS.md:99
- (holo3) POST-FORENSICS §A.3: revisit is the one genuinely zero row and it is honest — *artefact:* ARTEFACTS.md:533-536

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** no action for the holo2 map

**Notes.**

*Reader:* Included because it sits at the refinement price and is re-armed by the same certificate wakes; its comparison partner is v1's mop-up phase, which is the W2 map's row (POST-FORENSICS records revisit 0/593 against it).

*Refuter (upheld):* *Corrections:* Verified (revisit.py:27-55, :58-101, :104-133, :136-150; priced at refine's 200 via :127-133). Add a structural finding the row would want, because it is stronger than 'the zero is honest': revisit's PLACED branch cannot differ from what calibrate already produced. It calls calibrate.window_job (revisit.py:27-28), which on a window with standing non-empty evidence takes resample_window — a deterministic function of (pose_affine, region_pitch, raster, frozen cells, frozen reference values). Those are exactly calibrate's own declared reads (calibrate.py:715-720), calibrate NEVER retires (calibrate.py:762 `retire=_never`), and the certificates/region-ctx that wake revisit do not enter the job. So for a placed-but-refused K window, revisit re-runs at 200 what calibrate would have re-run at 15 whenever anything could have changed the answer; only the never-placed branch can produce something new. That makes 593 fires / 0 certificates a structural prediction, not just an observation — and it is a real ruling candidate (drop the placed branch, or give it an input calibrate does not have).

*Reason:* holo3-only and correctly described; the placed branch's zero is provable from the read-sets, not merely measured.

---

## Done projection and the done gate

14 rows; 7 carry a ruling.

**Reader's family notes.** SCOPE. Every done-related call site in both trees was enumerated by grep and read: holo2 has exactly three production sites (place_sched admission x2, place_job fire) plus a diag projection; holo3 has place retire, calibrate eligible, revisit eligible x2, fields retire, uplift eligible, color_refine's emission-mask prepare gate, and store's own two branches. No seed row named rows 11-14; they were found in the code.

WHAT MOVED, IN ONE SENTENCE. holo3 keeps holo2's law (a window whose supported extent is spent is never worked again) and its projection arithmetic, but replaces two gate doors with one consulted before every job is built, replaces the projected-extent test for placed windows with an exact tile-reach test, extends the gate from placement alone to calibration and the revisit pass, and states as pinned invariants two things holo2 held only by scope (fire-only suppression, monotonicity).

THE NUMBERS DO NOT COMPARE, and the record says so twice. v1's 48.6% is a simulated counterfactual over a receiver that never built the gate; holo2's 3.2-3.5% is a realized rate on a deployed gate, whose share a working gate drives down; holo3's 240/302 is a suppression rate over UNPLACED windows on one resumed sheet. Three different denominators. Dividing any pair is the category error holo2's own review already retracted once.

STALE CITATION FOUND. ARTEFACTS.md:582 and gap G-09 at :813 both state that no holo3 realized done-gating rate on a real sheet is recorded. holo3/conversion_docs/OPEN-2026-08-31.md:136-143 records 240 of 302 unplaced sheet-I windows suppressed with 0 jobs fired and a 302/302 replay agreement, produced by measure/donegeo_realstate.py; the conversion_docs 08-31 OPEN ledger is a licensed artefact source at ARTEFACTS.md:44. G-09 should be narrowed to 'no holo3 rate over the PLACED population' rather than closed.

THE ONE THING THAT LEAVES WITH holo2. No cross-tree oracle compares the two done projections. The affine primitives underneath them are pinned bit-exact (test_h3_drift_kernels.py:474-514) and the assemblies are textually equivalent, but the equivalence itself is a reading, not a pin, and after Phase 3 it can never be pinned. If a pin is wanted it costs seconds of slow-lane time and must be written before holo2 is deleted (row done-gate-01).

STILL OPEN ON BOTH SIDES, unchanged by holo3: no fragment or confetti done-geometry census exists anywhere, so every number in this family comes from intact dense sheets, which is the gate's favourable regime (ARTEFACTS.md:583). And the boundary sliver a pose revision moves in either direction is unmeasured on both sides (row done-gate-10) — holo3 removed it for placed windows and inherits it for unplaced ones.

**Refuter's family notes.** MECHANISMS NO ROW COVERS.

1. THE REGIME THE GATE CAN PAY IN. The family's numbers are all endgame or resume numbers, and the same OPEN ledger the reader licensed says why: on runs that start cold, placement finishes before certification starts — 97.6% of the seven-capture sheet-H stack's 9,866 place cpu-s (98.8% of the four-capture run's 4,551) was spent while ZERO tiles were done in all three streams, at most ~100 of 1,961 certified in ANY single stream (holo3/conversion_docs/OPEN-2026-08-31.md:144-152). No row states that the whole family is structurally worthless on a cold first run, which is the frame every ruling in it should be read in.

2. THE SIBLING MECHANISM NEITHER TREE HAS. The same ledger entry (OPEN-2026-08-31.md:152-158) names the gate that WOULD bite on the cold residue — a PLACEMENT-COVERAGE gate, retiring a window whose exact extent already carries a committed pose at another lane of the same capture — with a measured naive upper bound of 5,031 cpu-s (51% of place) sheet-H max-stack, 2,096 (46%) sheet-H mixed, 722 (91%) sheet-I first, 395 (47%) sheet-I resume-3. It is NOT built on either side and is a design ruling, so it is not a holo2 port row; but it is the largest done-adjacent number in the corpus and it belongs in RULINGS.md as a scheduled line, not lost between the maps.

3. TWO DOC/CODE CONTRADICTIONS IN holo3'S OWN DESCRIPTION OF THIS GATE. holo3/API.md:415-416 still describes place.done_covers as 'the in-job done-gate consult over the projection the engine hands in via WindowPass.done_cells'. WindowPass (place.py:518-534) has no such field, nothing hands a projection into a job, and test_h3_done_geometry.py:439-446 asserts the field's absence and that 'done_covers' does not appear in run_window_pass — the 2026-08-31 finding that an unreachable duplicate 'reads as a live gate that never fires'. Separately, tiles.done_covers (tiles.py:612-619) has no production caller at all (tests/test_h3_plugins_tiles.py:412, :418 only) while place.done_covers (place.py:509-515) is the live one. Both are Phase-2 comment-carry items: the API prose is the exact hazard the family's own event-stream false alarm taught.

4. WHAT LEAVES WITH holo2 BESIDES THE ORACLE. The reader is right that no cross-tree projection oracle exists, but the pins that DO exist are also holo2-shaped: test_h3_drift_kernels.py reaches holo2 through pytest.importorskip (:26-30) and is slow-lane gated (:32-35), so after deletion it skips silently rather than fails (ARTEFACTS.md:803, G-02). And holo2 carries the only done-coverage REPORTER in either tree — plane._done_coverage (plane.py:748-765) emits supported vs done cells and the run count per schedulable region, and diag/panes/model.py:345-352 renders its own projection. holo3 has no census surface for done coverage at all, which is precisely the instrument the row done-gate-10 settlement would want.

5. CACHE FANOUT, cost only, unmeasured: done_grid is cached per page but stamped with the GLOBAL certificate count (store.py:387-394), so one certificate anywhere invalidates every page's grid; done_cells is cached per (capture, LEVEL, region) although the value is level-independent, so a five-rung capture re-derives the same array up to five times. Neither is behaviour; both are worth one line in the map's cost column.

**Second lens (yield) family notes.** Lens = YIELD. Two rows move on this pass. done-gate-11 is DIVERGED and, on my lens, decides-certificates: the divergence needs only ONE already-covered corner among four (holo2 rests on ANY served child, holo3 only on a PLACED one), so it is far commoner than the four-covered-corners case the reader analysed, and with siblings exhausted the parent is not covered and a cold full-extent pass actually runs. done-gate-06 I keep as order-only, but with one indirect certificate channel named that neither the reader nor the refuter states: a placement is also an ANCHOR for neighbouring windows' seed consults (holo3/plugins/place_sched.py:61-75), so gating placement withholds a seed - the same caveat the coarse-lane census puts on its own upper bound. That channel is present in holo2's gate too, so it is a property of gating, not a tree difference. One correction to the refuter: for done-gate-06 the family gate on the K refinement row is the BIRTH gate (_refine_subjects, holo3/plugins/refine.py:617-620, returns nothing for a non-K row), which is stronger than the prepare-returns-None it cites. One mechanism fact no row on either side records, found while checking 11: the subdivision afterlife is triggered by a place OUTCOME fold (holo3/store.py:604-612), never by a retirement, so a parent whose LAST corner leaves through the gate at its pop is never woken - the afterlife is order-dependent, and that order-dependence is itself untested. Cross-cutting frame for every ruling here: on a cold first run the gate is structurally idle - 97.6% of the seven-capture sheet-H placement CPU was spent while zero tiles were certified in all three streams (holo3/conversion_docs/OPEN-2026-08-31.md:144-152) - so every number in this family is an endgame or resume number, and no ruling in it should be read as bearing on a cold run. The one instrument that can settle rows 04, 10 and 11 without paper is measure/donegeo_realstate.py at the repo root (not holo3/measure/), read-only over an archived sheet-I resume snapshot plus its events.


### done-gate-01 — The done projection: certified tiles mapped back onto a capture's own cells

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B36

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which cells of a capture are already spent — the fact every pose-free done test is asked against, so it decides which unplaced windows are ever attempted.

**holo2.** For one region, walk one pose per posed window; for each, take the region's cell-centre grid over the window's extent, push it backwards through the pose (inverse of the committed native affine), floor to page cells, ask which 64-cell tile that is, and OR in the tiles that are certified in every stream, intersected with the survey support mask. The result is a boolean cell array per region, derived on demand and never persisted. The cell centres come from a CellLattice object (origin + pitch*(index+0.5)); tile_of_cell is integer floor-division by 64.

*Where:* `holo2/src/holo2/solve/tilemap.py:750-823`; `holo2/src/holo2/solve/tilemap.py:704-721`; `holo2/src/holo2/solve/geometry.py:95-102`; `holo2/src/holo2/solve/geometry.py:300-303`; `holo2/src/holo2/solve/plane_views.py:275-291` · *dial:* live

**holo3.** The same arithmetic, line for line: inverse affine over origin+pitch*(arange+0.5) centres, floor, tile_of_cell, mask by the certified-in-every-stream tile grid and by support, OR-accumulate. The inputs are plain tuples — (page, extent_cells, native_affine) triples plus a dict of per-page done grids and the region frame's origin/pitch/shape/support — instead of a store index and a lattice object. store.done_cells assembles the triples from the standing placements of the capture+region across every level and caches the result per (capture, level, region).

*Where:* `holo3/plugins/tiles.py:583-610`; `holo3/plugins/tiles.py:567-580`; `holo3/store.py:400-435`; `holo3/lib/geometry.py:103-105`

*Scheduler row / doc:* SCHEDULE.md:562-582 (the done gate); docs/DONE-GEOMETRY.md §2/§4

**Implementation delta.** Algorithm and constants identical (same inverse-affine, same floor, same //64, same support AND, same OR accumulation; holo3's arange carries an explicit float64 dtype, holo2's promotes from int64 — same values). What differs is plumbing: holo2 reads poses through a StoreIndex and a CellLattice and caches one DoneProjection dataclass per region per generation; holo3 passes raw tuples and caches a bare numpy array stamped with maintained counters. Both pool every rung of a capture+region into one native-pixel projection, which is sound on both sides because the survey that defines a region is per capture, so all rungs share one cell lattice (holo2: window_plans_for over the same regions; holo3: store._fold_survey builds one frame per level from the same Region).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) affine family bit-exact between the trees: affine_matrix/affine_terms/invert_affine/apply_affine/shift_affine and rescale/compose all compared over random terms — *artefact:* holo3/tests/test_h3_drift_kernels.py:474-514 (slow lane) — the underlying geometry primitives ARE pinned; the projection assembly is not
- (v1) 719 of 1,479 committed placements (48.6%) pixel-gateable; gated windows minted zero certificates, provably — *artefact:* ARTEFACTS.md:94 and :575 -> docs/DONE-GEOMETRY.md:257-273

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's, and consider a costed pin before Phase 3: a cross-tree drift oracle comparing holo2.solve.tilemap.project_done against holo3.plugins.tiles.project_done over random poses/grids/support masks would take seconds in the slow lane and no receiver run, but it can only be written while holo2 exists. Without it the equivalence is a re-derivation by reading, not a pin.

**Notes.**

*Reader:* I re-derived equality by reading both bodies; they are textually equivalent modulo argument shape. holo3 caches done_cells per (capture, LEVEL, region) although the array is level-independent (the frame's native origin/pitch/shape/support are identical across levels), so a five-rung capture recomputes the same projection up to five times — cost only, no behaviour.

*Refuter (upheld):* *Corrections:* Test citation is off and under-stated: the affine pin is holo3/tests/test_h3_drift_kernels.py:472-494 (test_geometry_affine_family_matches_holo2 — affine_matrix/affine_terms/invert_affine/apply_affine/shift_affine) plus :497-512 (test_geometry_rescale_and_compose_match_holo2_place_shared), not :474-514. Add the expiry: that file reaches holo2 through pytest.importorskip at test_h3_drift_kernels.py:26-27 and is slow-lane-only (pytestmark at :32-35), so at Phase 3 the pin does not fail, it SILENTLY SKIPS (ARTEFACTS.md:803, G-02) — the 'primitives are pinned, only the assembly is not' half of this row has the same expiry date as the assembly, which strengthens the recommendation rather than weakening it. Two verifications the row asserts and I confirmed: (a) the level-independence that makes holo3's cross-level pooling sound — place.region_frame at holo3/plugins/place.py:164-193 derives origin_native_yx/pitch_native_px/shape_cells/support_cells from pitch_native = dpi*pitch_in only; scale/origin_level_yx/pitch_level_px are the only level-carrying fields, and done_cells (store.py:431-433) reads none of them, so the per-level cache key is redundant and the note 'cost only' stands; (b) holo2 pools across footings identically (plane_views.py:281-291 projects one region with view.lattice, and windows of every footing share window.region_id — tilemap.py:595-607). One unstated but harmless difference: holo2 short-circuits a non-schedulable region to a 1x1 false array (plane.py:560-566, plane_views.py:280-283) where holo3 returns None from done_cells (store.py:415-423); same answer at every caller.

*Reason:* Arithmetic equality re-derived line for line at HEAD; only the pin's citation and its post-deletion fate need fixing.

---

### done-gate-02 — One pose per window — the latest, never the union of an extent's poses

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **nothing observable on the archived corpus (the mechanism class is certificate-deciding, but the disagreement case is unreachable in holo3 today)** · ruling needed **Y** · seeds: B36

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** How much geometry a refined window is allowed to claim as spent; a union claim suppresses windows that no pixel was ever read for.

**holo2.** Every committed pose is retained as a record, so a revised window has several. StoreIndex.live_pose answers with the LATEST COMMITTED one for that window, and live_poses_of_region hands the projection exactly one pose per posed window. The docstring records both halves of the measurement that produced the rule and the honest limit: because the projection maps the whole extent through whichever pose it is handed and consults no evidence, a revision's done set is neither a subset nor a superset of its parent's — a boundary sliver in either direction, unmeasured.

*Where:* `holo2/src/holo2/solve/tilemap.py:576-608`; `holo2/src/holo2/solve/plane_views.py:284-291`; `holo2/src/holo2/solve/tilemap.py:766-796` · *dial:* live

**holo3.** holo3 keeps ONE Placement per window id and replaces it in place; a superseded pose is not retained at all, so a union is not expressible. Which pose stands is decided by a monotone ordinal, not by arrival: a refine-route placement beats an original, a longer refine basis beats a shorter, and ties break on higher quality (data.placement_ordinal, applied through store._adopts). _region_done_poses simply walks the standing placements of the region.

*Where:* `holo3/store.py:400-413`; `holo3/store.py:624-661`; `holo3/data.py:118-120`

*Scheduler row / doc:* SCHEDULE.md:562-572; no superseded-pose record exists in holo3's fact model

**Implementation delta.** holo2 picks the latest of several retained poses at read time; holo3 keeps only the adopted one at write time and adopts by an order-independent ordinal (refine-route, then basis length, then quality) instead of by commit order. Two consequences: (a) holo3's done projection cannot regress to a union even by accident, and its answer does not depend on the order two workers committed in; (b) where holo2's 'latest' and holo3's 'ordinal-max' would disagree — a later revision with a SHORTER certified basis or lower quality — holo3 keeps the earlier pose and holo2 would have taken the later one. Nothing in holo3 can produce that case today, because refine only re-fits on a strictly larger certified basis (refine.refine_eligible requires set(current) > set(basis)).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) unioning parent and revision added +860 done cells on e029 and +588 on Xerox, for revisions carrying zero evidence; under the live-pose rule the projection moved DOWN -3,996 (e029) and -1,449 (xerox) — *artefact:* ARTEFACTS.md:559 -> holo2/docs/MEASUREMENTS.md:1234-1236 (both figures are in that block; ARTEFACTS.md quotes only the negative half)
- (holo2) 269/1,228 e029 and 272/1,282 xerox windows carry two committed poses; 4,392 / 4,117 evidence pieces hang on a non-live pose — *artefact:* ARTEFACTS.md:547 -> holo2/docs/kparity/K-PARITY-CATALOG-draft.md:545-549
- (holo3) no artefact — no holo3 measurement of the done projection under the two adoption rules exists — *artefact:* no artefact

**Yield relevance.** nothing observable on the archived corpus (the mechanism class is certificate-deciding, but the disagreement case is unreachable in holo3 today) — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's. The measured hazard the rule exists to close (+860/+588 of unsampled geometry claimed as spent) is structurally impossible in holo3, and the ordinal makes the answer independent of commit order, which the pull-model race made a live concern in holo2. The residual — the unmeasured boundary sliver that a pose revision moves in both directions — is identical on both sides and is recorded on row done-gate-10.

**Notes.**

*Reader:* holo2's own docstring at tilemap.py:766-796 is the fullest statement of the rule and of its unmeasured limit; it is the strongest comment-carry candidate in this family.

*Refuter (upheld):* *Corrections:* Two factual fixes. (1) THE ORDINAL RUNS THE OTHER WAY. data.placement_ordinal (holo3/data.py:118-121) is (route == 'refine', len(refine_basis), -quality) and store._adopts (holo3/store.py:44-46) adopts on strictly greater, so a tie on route and basis length adopts the placement with the LOWER quality value — and `quality` holds a COST, not a score: place.py:817 sets quality=float(mismatch) and store.py:796-797 sets it to the refine revision's candidate_logloss. So write 'ties break on the lower quality value, which is a cost (patch mismatch at place.py:817, candidate logloss at store.py:797) — the better fit wins', not 'ties break on higher quality'. The row's conclusion is unaffected; the stated rule was inverted. (2) ARTEFACTS cite is wrong: the '269/1,228 e029 and 272/1,282 xerox / 4,392 / 4,117' row is ARTEFACTS.md:555, not :547 (:547 is the R-lane qualification row, 1,166 s CPU / 601 certificates). The underlying K-PARITY-CATALOG-draft.md:545-549 resolves exactly, including both figures. The +860/+588 union and the -3,996/-1,449 live-pose numbers are both in MEASUREMENTS.md:1234-1236 as cited, and ARTEFACTS.md:559 does quote only the negative half as the row says. Also verified: refine.revised_placement (refine.py:512-514) sets route=ROUTE_REFINE, and both refine_eligible (refine.py:537-542) and color_refine_eligible (color_refine.py:361-363) require a STRICTLY larger basis, so the row's 'nothing in holo3 can produce the disagreement case today' holds; the only other placement writer is the place row, which cannot fire twice on a window (place_retire_cause returns RETIRE_PLACED, place_sched.py:243-245).

*Reason:* Rule stated backwards (quality is a cost) and one artefact line misquoted; the mechanism and the recommendation survive both.

*Second lens (final: CARRIED-DIFFERENT):* The refuter is right on both points and I re-derived both. (1) The tie-break runs the other way than the reader wrote. data.placement_ordinal (holo3/data.py:118-121) returns (route == 'refine', len(refine_basis), -quality) and store._adopts (holo3/store.py:44-46) adopts on strictly greater, so on a tie of route and basis the placement with the LOWER quality number wins; and quality holds a COST, not a score - holo3/plugins/place.py:817 sets quality=float(mismatch), holo3/store.py:795-797 overwrites it with the re-fit's candidate log-loss. The better fit wins; the reader's 'ties break on higher quality' is inverted. (2) The re-read-population number is at ARTEFACTS.md:555, not :547 (:547 is the R-lane qualification row). The reader's conclusion survives both fixes, and I confirm its load-bearing claim: the case where holo2's 'latest' and holo3's 'best' would differ cannot be produced today, because refine.refine_eligible (holo3/plugins/refine.py:537-542) and color_refine.color_refine_eligible (holo3/plugins/color_refine.py:361-363) both demand a strictly larger certified basis, and the engine's one-job-in-flight rule (holo3/engine.py:444-446) plus RETIRE_PLACED (holo3/plugins/place_sched.py:242-243) stop a window ever committing two original placements. On yield: because the standing pose is what every sampler reads through, this mechanism is certificate-deciding in class - but with the disagreement case unreachable, nothing on the archived corpus moves.

---

### done-gate-03 — Where the gate is asked — admission and fire time in holo2, one door at the pop in holo3

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B35

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a done-covered window is ever created, posed, searched or woken; on the answer hangs every placement pass that window would have spent.

**holo2.** TWO doors. At admission (_consider) a window whose supported extent is covered exits to _exited as 'done_covered' and never becomes a slot — it is not priced, not enqueued and gets no admission consult peek; the re-read door is guarded by the same predicate. At fire time place_job.run asks it as the very first act, before a pixel is read or a seed derived, and retires the window durably. The predicate is DoneProjection.covers: every SUPPORTED cell of the extent must be done, and a window with no support at all is refused rather than called done.

*Where:* `holo2/src/holo2/solve/place_sched.py:354-356`; `holo2/src/holo2/solve/place_sched.py:339-344`; `holo2/src/holo2/solve/place_job.py:611-618`; `holo2/src/holo2/solve/plane.py:560-566`; `holo2/src/holo2/solve/tilemap.py:739-747` · *dial:* live

**holo3.** ONE door. Every surveyed window is born as a place bookmark; engine._fill consults descriptor.retire before descriptor.prepare at every pop, and place_retire_cause answers placed / exhausted / done_covered. A done window is retired one line before its pass would have been built, so it costs one pop and no consult, no seed derivation and no pass. The placement pass carries no second copy of the test, and a test pins that (test_the_placement_pass_carries_no_second_copy_of_the_gate).

*Where:* `holo3/plugins/place_sched.py:226-256`; `holo3/engine.py:449-451`; `holo3/store.py:449-487`; `holo3/plugins/place.py:509-515`

*Scheduler row / doc:* SCHEDULE.md:572-579 ('place consults it in retire'); place descriptor row

**Implementation delta.** holo2 refuses at two sites (admission, which prevents the slot existing, and fire, which retires it durably); holo3 refuses at one site that is consulted at every pop, first pop included, and therefore covers both roles. The costs holo2's admission door saves — pricing, enqueue, the R-A consult peek — holo3 saves at the pop instead, because the consult lives in prepare which retire precedes. The residual difference is bookkeeping: holo3 pays a bookmark and one pop per suppressed window where holo2 pays a predicate at the refresh. Ordering also differs slightly: holo2 asks pixels-attachable and reading-set before done; holo3 asks placed, then exhausted, then done.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) 240 of 302 unplaced windows suppressed on the sheet-I resumes, 0 jobs fired for any of them, the re-derived verdict agreeing with the run on all 302 both ways; the 62 survivors were held open by 16 tiles (C 3, Y 14) — *artefact:* holo3/conversion_docs/OPEN-2026-08-31.md:136-143 (measure/donegeo_realstate.py); the conversion_docs 08-31 OPEN ledger is a licensed source at ARTEFACTS.md:44
- (holo3) at the endgame shape the gate costs 0.7 us on the placed branch and 5.4 us on the pose-free one per pop, against the 95.5 us ring consult it replaces; calibrate pops that fire 49 -> 1, parked revisit pops that reach prepare 40 -> 0 — *artefact:* holo3/SCHEDULE.md:593-599 (measure/donegeo_saturation.py)
- (holo2) realized gating rate e029 45 / 1,273 = 3.5%, xerox 42 / 1,324 = 3.2%; off-census floor +44 / +11 — *artefact:* ARTEFACTS.md:577 -> holo2/docs/MEASUREMENTS.md:1246-1247
- (v1) 719 of 1,479 = 48.6% pixel-gateable, a SIMULATED counterfactual; not a ratio against holo2's realized rate — *artefact:* ARTEFACTS.md:575, :578 -> docs/DONE-GEOMETRY.md:257-273, holo2/docs/MEASUREMENTS.md:1249-1256

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* ARTEFACTS.md:582 and gap G-09 (:813) both say 'no holo3 measured gating rate on a real sheet is recorded'. That is STALE: OPEN-2026-08-31.md:136-143 records 240/302 on the sheet-I resumes from measure/donegeo_realstate.py, with a 302/302 replay agreement. ARTEFACTS.md should be corrected; the three rates are still not comparable to one another (simulated counterfactual vs two realized rates on different sheets and schedules).

*Refuter (upheld):* *Corrections:* Citation tightening only. holo3: place_retire_cause is place_sched.py:229-252 and _place_retire :255-256 (the row's :226-256 opens inside _place_eligible); engine.py:449-451 is exact (retire, then _retire_worker, then continue — ahead of the version floor at :452-455, eligible at :456, stage at :458 and prepare). holo2: the three window_is_done sites are place_sched.py:341 (the re-read guard), place_sched.py:354-356 (the admission exit) and place_job.py:611-618 (fire), all confirmed at HEAD. The stale-artefact finding is CORRECT and I reproduce it: OPEN-2026-08-31.md:139-142 records '240 of 302 unplaced windows suppressed, 0 jobs fired for any of them, the re-derived verdict agreeing with the run on all 302 both ways' from measure/donegeo_realstate.py, against ARTEFACTS.md:582 and G-09 at :813 both saying no such number exists. Keep the reader's own qualifier in the correction text: it is a re-derivation over archived sheet-I RESUME states, over the UNPLACED population — narrow G-09 to the placed population rather than closing it.

*Reason:* Both sides' code and every number check out at HEAD; only line anchors drift by a few lines.

---

### done-gate-04 — What 'done' means for a PLACED window — exact tile reach vs the projected extent

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B35, B36

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether a window that already carries a pose is judged spent, and hence whether it is re-sampled, re-fitted or refined again.

**holo2.** One predicate for every window, placed or not: project the region's live poses onto cells, then ask whether all supported cells of THIS window's extent are marked. A placed window is judged by the same projected-extent test as an unplaced one, so the test inherits the projection's boundary error (a cell near a tile edge can map differently under a revision).

*Where:* `holo2/src/holo2/solve/plane.py:560-566`; `holo2/src/holo2/solve/tilemap.py:739-747` · *dial:* live

**holo3.** Two branches behind one name. A PLACED window is judged on its exact tile reach — the derived window reach (from its page_cells, maintained at the placement fold) plus the evidence reach (maintained at the evidence fold) — every tile of which must be certified in every stream; tiles outside the page grid are ignored and a window with no on-page reach is not done. An UNPLACED window falls through to window_extent_done, the pose-free projection test, which is holo2's predicate.

*Where:* `holo3/store.py:449-487`; `holo3/store.py:437-447`; `holo3/store.py:655-661`; `holo3/store.py:730-740`

*Scheduler row / doc:* SCHEDULE.md:565-572; docs/DONE-GEOMETRY.md §4.6 (supported-extent law)

**Implementation delta.** For a placed window holo3 replaces a projected geometric containment test with an exact set test in page-tile space, using reaches derived at fold time from the same cells the evidence cover is cut from. It ignores off-page tiles (which can never certify) where holo2's extent test would count their cells as not-done unless unsupported. So holo3's placed branch can answer done where holo2's would not, and it does so without any projection error. The safety argument is a containment: tiles.evidence_cover_cells keeps a payload subset of page_cells_yx, so cover is a subset of reach and a done window has every tile it covers certified — pinned by test_every_tile_the_evidence_covers_lies_inside_the_gated_reach.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the certificate SET and the payload are identical on every sim (K 49, colour 279, degraded 4, mixed 49, null 0) and no row's job count grew when the gate landed — *artefact:* holo3/SCHEDULE.md:584-592
- (holo2) no artefact — holo2 never measured a placed-window done rate separately from the pose-free one — *artefact:* no artefact

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's. The exact-reach branch is strictly better founded than the projected-extent test it replaces (no boundary error, no unsupported-cell accounting) and its no-loss argument is a containment pinned by test rather than an approximation. The sim evidence is a same-tree A/B on the certificate set, not a real-sheet A/B; ruling wanted only to record that the real-sheet equivalence rests on the containment argument plus the sheet-I 302/302 replay agreement, not on a measured yield comparison.

**Notes.**

*Reader:* The two branches share one name, which is what SCHEDULE.md calls 'ONE derivation in the store'. holo3 also ships two copies of done_covers with swapped argument order — place.done_covers(done, support, extent) at plugins/place.py:509 (the one store uses) and tiles.done_covers(done, extent, support) at plugins/tiles.py:612. Both are correct; the duplication is a hygiene nit for the comment/cleanup phase, not a behaviour delta.

*Refuter (upheld):* *Corrections:* The implementation delta is understated in one direction and overstated in the other. (1) UNDERSTATED: the placed branch's reach is not 'the exact tile reach of the window' but the tiles of the cells the window ACTUALLY AUDITED — placement.local_cells_yx is np.argwhere(audited) (place.py:807-809), mapped and clipped by calibrate.window_page_cells (calibrate.py:717-724) — plus the evidence fit's own page_cells (store.py:737). Against holo2, which projects EVERY cell of the extent through the pose, that is the substantive difference and the reason the containment pin (evidence cover subset of page_cells) is the whole safety argument. (2) OVERSTATED: 'it ignores off-page tiles where holo2 would count them not-done' is nearly moot, because window_page_cells already drops cells outside the page (the `inside` filter at calibrate.py:721-724), so the on-page guard in window_fully_done (store.py:478-486) is defensive. And the asymmetry runs both ways: holo2's DoneProjection.covers exempts UNSUPPORTED cells (tilemap.py:740-748), while holo3's placed branch requires every reach tile certified with no support masking — so holo3 can answer not-done where holo2 answers done. That direction only costs work, so the no-loss argument survives, but the row should say so. (3) The duplication note is weaker than the truth: tiles.done_covers (tiles.py:612-619) has NO production caller at HEAD — only tests/test_h3_plugins_tiles.py:412 and :418 — it is dead code, and holo3/API.md:415-416 still documents an in-job consult 'over the projection the engine hands in via WindowPass.done_cells', a field that does not exist and that test_h3_done_geometry.py:440-442 explicitly forbids. That is a live comment-carry item for Phase 2, not a hygiene nit.

*Reason:* Classification and no-loss argument stand; the delta text mis-describes what the placed branch reads and calls dead code a duplicate.

*Second lens (final: CARRIED-DIFFERENT):* The refuter's three corrections are right and the first one matters most for yield, so I adopt them. The placed branch does NOT judge the window's whole extent: the reach is built from placement.local_cells_yx, which is np.argwhere(audited) (holo3/plugins/place.py:804-805), mapped and clipped by calibrate.window_page_cells (holo3/plugins/calibrate.py:145-153) and turned into tiles at holo3/store.py:661 plus the evidence fold at holo3/store.py:737. So holo3 asks about the tiles the window actually audited, where holo2 projects every supported cell of the extent (holo2/src/holo2/solve/plane.py:560-566). That is a strictly smaller set, so holo3 can declare a placed window done earlier. The refuter is also right that the off-page clause is nearly moot - window_page_cells already drops off-page cells at calibrate.py:151-153, so the guard at holo3/store.py:478-486 is defensive - and that the asymmetry runs both ways, since holo2 exempts unsupported cells (tilemap.py:739-747) while holo3's placed branch exempts none. I keep the reader's decides-certificates: earlier suppression is a real yield surface even though the direct loss is closed by the containment (evidence cover cut from the same cells), because the suppressed work is a re-fit whose only remaining consumer is the region context pool. On the dead-code point I agree with the refuter: tiles.done_covers (holo3/plugins/tiles.py:612-619) has no production caller, only tests, and holo3/API.md:415-416 still describes a consult that does not exist.

---

### done-gate-05 — The tile predicate underneath: certified in EVERY stream

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B35

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** When a tile counts as spent — the atom the whole gate is built from, and the reason a colour tile with one open plane never suppresses anything.

**holo2.** done_tile_grid walks the CERTIFIED cells rather than the tile grid (a profiled fix: 421,615 tile_done calls and 3.8 s on the gen-clean serial run) and marks a tile only where the format row's whole stream set is a subset of the streams certified there, clipped to the tile grid. Stream-general code, but holo2 never decoded colour, so in practice the row's stream set is one K stream.

*Where:* `holo2/src/holo2/solve/tilemap.py:704-721`; `holo2/src/holo2/solve/tilemap.py:698-702` · *dial:* live

**holo3.** The same law: build a per-tile set of certified stream ids for the page from the certificate dict, mark a tile where the row's wanted stream set is a subset and the indices are on the grid. Cached per page against the certificate count. This is the one place the gate becomes colour-aware, and it is what keeps 62 of 302 sheet-I windows open on 16 tiles.

*Where:* `holo3/plugins/tiles.py:567-580`; `holo3/store.py:387-394`

*Scheduler row / doc:* SCHEDULE.md:566-569 ('the AND across streams: a tile with C and M certified and Y open is NOT done')

**Implementation delta.** Same predicate, different source: holo2 reads a maintained certified_streams index on the StoreIndex; holo3 rebuilds a per-tile stream set from the certificate dict on each cache miss and caches the grid per page against len(certificates). No constant, threshold or ordering differs.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the 62 surviving sheet-I windows were held open by 16 tiles (C 3, Y 14) — the AND across streams, working — *artefact:* holo3/conversion_docs/OPEN-2026-08-31.md:142-143
- (holo2) no colour number of any kind exists for holo2, by construction — *artefact:* ARTEFACTS.md:817 (gap G-17)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* holo3's own pin is test_the_gate_holds_only_when_every_stream_of_the_tile_is_certified plus test_a_window_with_one_open_tile_in_its_reach_is_never_done. There is no cross-tree oracle; a comparison would be meaningless anyway because holo2 never ran a multi-stream row.

*Refuter (upheld):* *Corrections:* Two citations. G-17 ('holo2 has no colour number of any kind, by construction') is ARTEFACTS.md:824, not :817 — :817 is G-13 (holo1's placement/search.py). holo2's tile_done is tilemap.py:693-702 (the row's :698-702 names only the docstring tail and the return). Everything else verified exactly: done_tile_grid walks the certified cells with the 421,615-calls / 3.8 s profile note in its own docstring (tilemap.py:704-721); holo3 rebuilds the per-tile stream set from the certificate dict (tiles.py:567-580) and caches per page against len(certificates) (store.py:387-394); the AND across streams is pinned by test_the_gate_holds_only_when_every_stream_of_the_tile_is_certified (test_h3_done_geometry.py:149-165, asserting verdicts [False, False, True] over C/M/Y) and test_a_window_with_one_open_tile_in_its_reach_is_never_done (:167-175). The '62 held open by 16 tiles (C 3, Y 14)' is at OPEN-2026-08-31.md:141-142.

*Reason:* Predicate is the same law on both sides and the colour pin exists; only two line references are wrong.

---

### done-gate-06 — Scope — which work the gate is allowed to suppress

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only on every direct path; one indirect certificate channel (a suppressed placement is also a suppressed anchor for a neighbour's seeds) is unmeasured** · ruling needed **N** · seeds: B35

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** How much of the endgame the gate can retire: placement only, or placement plus calibration, plus the revisit pass, plus refinement.

**holo2.** PLACEMENT ONLY. window_is_done has exactly three call sites in the whole tree and all three are the placement scheduler and the placement job (the third is diag's own projection). Calibration, payload and evidence work carry their own terminality tests and never ask the done projection.

*Where:* `holo2/src/holo2/solve/place_sched.py:354-356`; `holo2/src/holo2/solve/place_job.py:611-618` · *dial:* live

**holo3.** place consults it in retire; calibrate and revisit in eligible; refine and refine.color carry no call because their own reach predicates already refuse every done window (pinned by test_the_two_refine_rows_already_refuse_every_done_window). The payload rows (tiles.scan / union / retry) are deliberately never gated — they act on uncertified tiles and keep their own subject-level refusal. A test enumerates the permitted call sites, so a new one is a charter violation rather than a golden to update.

*Where:* `holo3/plugins/place_sched.py:250`; `holo3/plugins/calibrate.py:723-728`; `holo3/plugins/revisit.py:34-38`; `holo3/plugins/revisit.py:104-115`; `holo3/plugins/refine.py:537-548`; `holo3/plugins/color_refine.py:361-368`

*Scheduler row / doc:* SCHEDULE.md:572-580; place / calibrate / revisit / refine / refine.color descriptor rows

**Implementation delta.** holo3 extends the gate from one family to four rows. Concretely: a placed window whose whole reach is certified stops being re-calibrated (holo2 would keep re-fitting it), stops being revisited on every neighbouring certificate, and is refused by both refinement rows. holo2 has no equivalent for any of these because its calibration and re-read paths never consult done-ness. The refinement refusal is a coincidence of predicates rather than a call: refine retires when every reach tile is certified, color_refine when every (tile, stream) pair is — for K these are the same condition as done, and refine/refine.color are family-disjoint (refine is K-only, color_refine is colour-only), so the ANY-stream spelling in refine.reach_certified cannot bite.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) K calibrate 60 -> 29 and ctx 14 -> 9; mixed calibrate 136 -> 111, ctx 28 -> 27, two union subjects no longer born; certificate SET and payload identical on every sim — *artefact:* holo3/SCHEDULE.md:584-592
- (holo3) at the endgame shape, calibrate pops that fire 49 -> 1 and parked revisit pops that reach prepare 40 -> 0 — *artefact:* holo3/SCHEDULE.md:596-599
- (v1) r00-r03 gated ZERO — the gate never touches live refinement work — *artefact:* ARTEFACTS.md:575 -> docs/DONE-GEOMETRY.md:257-265

**Yield relevance.** decides-order-only on every direct path; one indirect certificate channel (a suppressed placement is also a suppressed anchor for a neighbour's seeds) is unmeasured — source: second lens (reader said: decides-order-only).

**Recommendation.** keep holo3's

**Notes.**

*Reader:* The v1 census reading that 'the gate never touches live refinement work' is about R-lanes on a sheet where every refinement target was still open; it is not in tension with holo3's refine rows refusing done windows, which is the same statement from the other side (a done window has nothing left to refine).

*Refuter (upheld):* *Corrections:* Three fixes, two of them to the reasoning. (1) The holo2 sentence is garbled and should read: window_is_done has exactly three call sites — place_sched.py:341, place_sched.py:354, place_job.py:611 — plus the protocol declaration (view.py:201) and the implementation (plane.py:560). Diag does not call it; diag builds its OWN projection (diag/panes/model.py:345-352). There IS a fourth projection consumer the row misses, plane._done_coverage (plane.py:748-765), and it is reporting only — so 'PLACEMENT ONLY' survives as a claim about scheduling, which is what the row means. (2) 'the ANY-stream spelling in refine.reach_certified cannot bite because refine is K-only' is not how the code is gated: _refine_eligible and _refine_retire (refine.py:636-657) carry NO family test and do run on colour windows; the Family.K gate lives in prepare_refine (refine.py:574) and its reads (:617). It cannot bite because prepare returns None for non-K, so no job is ever built — not because the predicates are family-scoped. (3) For colour the refusal is not an eligibility predicate: color_refine_eligible (color_refine.py:361-363) has no '< full reach' clause at all (unlike refine_eligible at :537-542), so a fully-certified colour window is refused by _color_refine_retire -> color_refine_exhausted (color_refine.py:449-456, :366-369), which the engine asks BEFORE eligible, plus the emission-mask guard in prepare_color_refine (:384-388). test_the_two_refine_rows_already_refuse_every_done_window (test_h3_done_geometry.py:274-291) asserts exactly that shape — refine via _refine_eligible/_refine_retire, colour via _color_refine_retire only. The call-site golden is GATE_CALL_SITES = {calibrate 1, place_sched 1, revisit 2} (test_h3_done_geometry.py:58-62) with the extra assertion that plugins/tiles.py never appears; the SCHEDULE.md numbers (:584-599) all reproduce.

*Reason:* Scope extension is real and measured; two of the row's mechanism explanations name the wrong gate.

*Second lens (final: CARRIED-DIFFERENT):* I uphold the reader's classification and adopt two of the refuter's three mechanism corrections, one with a further fix. (a) The holo2 sentence is garbled: window_is_done has exactly three call sites, all placement (holo2/src/holo2/solve/place_sched.py:341, :354; place_job.py:611), plus the protocol at view.py:201 and the implementation at plane.py:560; the diagnostic viewer builds its own projection (holo2/src/holo2/solve/diag/panes/model.py:345-352) and there is a reporting-only consumer at plane.py:748-765. 'Placement only' survives as a claim about scheduling. (b) The refuter is right that the refinement rows are not gated by family-scoped predicates, but its own citation is one step short: the family gate is the BIRTH gate - _refine_subjects (holo3/plugins/refine.py:617-620) returns nothing for a non-K row, so no colour refinement subject exists at all, which is stronger than prepare returning None (holo3/plugins/refine.py:574). (c) For colour the refusal is a retire, not an eligibility clause: color_refine_eligible (holo3/plugins/color_refine.py:361-363) has no 'less than full reach' term, so a fully certified colour window leaves through _color_refine_retire (holo3/plugins/color_refine.py:449-456). On yield I stay with order-only: the suppressed work is by construction work on tiles that are already certified, and holo3's own note is that suppression is fire-only - the window keeps its standing evidence, its tile cover and its seat in the region context fit (holo3/SCHEDULE.md:580-583). The one channel that is not closed by construction is that a placement is also an anchor for neighbouring windows' seed consults (holo3/plugins/place_sched.py:61-75), so refusing to place a done window withholds a seed - the same caveat the coarse-lane census puts on its own upper bound (holo3/conversion_docs/OPEN-2026-08-31.md:152-158). That channel exists in holo2's placement gate too, so it is not a difference between the trees, only an unmeasured property of gating at all.

---

### done-gate-07 — Suppression is fire-only — a done window keeps every standing fact

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **integrity** · ruling needed **N** · seeds: B35

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether stopping future work on a window also removes its evidence from the region context fit and from the tile cover, which would move certificates rather than only work.

**holo2.** The done exit writes a WindowRecord with status RETIRED and reason 'done_covered' and drops the window from the working set. Nothing about evidence, poses or context pools is touched, so the window's existing observations keep serving the calibration pool and the payload freeze. The property holds by construction — the gate lives entirely in the placement scheduler — rather than by a stated invariant.

*Where:* `holo2/src/holo2/solve/place_job.py:848-873`; `holo2/src/holo2/solve/place_sched.py:354-356` · *dial:* live

**holo3.** Retirement clears the bookmark and its read subscriptions; no fact is removed. The invariant is stated and pinned four ways: a done window keeps its evidence, its cover and its certainty; the region context fit still pools it; a neighbour with an open tile keeps every row; and the payload rows stay live while a neighbour is done.

*Where:* `holo3/engine.py:360-386`; `holo3/tests/test_h3_done_geometry.py:216-272`

*Scheduler row / doc:* SCHEDULE.md:580-582 ('Suppression is fire-only')

**Implementation delta.** Same behaviour, different guarantee. holo2 gets it for free because the gate only exists in one family; holo3 had to state it because the gate reaches calibrate, revisit and both refinement rows, and it is enforced by four tests rather than by scope.

**Evidence status.** PINNED

**Evidence.**

- (holo3) test_a_done_window_keeps_its_evidence_its_cover_and_its_certainty, test_the_region_context_fit_still_pools_a_done_windows_evidence, test_a_neighbour_window_with_an_open_tile_keeps_every_row, test_the_payload_rows_stay_live_while_a_neighbour_window_is_done — *artefact:* holo3/tests/test_h3_done_geometry.py:216-273
- (v1) the design's own §5 clause: label/context furniture stays outside the gate; done means never again a payload observation target, not never sampled — *artefact:* docs/DONE-GEOMETRY.md:155-175

**Yield relevance.** integrity — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* This is the invariant that makes the whole family yield-safe; it is the one row in this family where holo3 is strictly better evidenced than holo2.

*Refuter (upheld):* *Corrections:* None material. All four named pins exist at test_h3_done_geometry.py:216, :238, :253, :263 (the block runs 216-273). holo2's _retire + _window_write are place_job.py:848-876. holo3's retirement clears only the bookmark and its read subscriptions (engine.py:359-386) and touches no fact. DONE-GEOMETRY.md:155-175 carries the §5 clause as quoted, verbatim on the halo line.

*Reason:* The one PINNED row in the family, and the pins are real and specific.

---

### done-gate-08 — Done is inviolable under quarantine — a condemnation moves zero done pixels

**ABSENT** · evidence **n/a** · yield **integrity** · ruling needed **Y** · seeds: B25

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether a word contradiction can un-spend geometry, which would both reopen retired windows and invalidate the projection's cache key.

**holo2.** project_done does not read the quarantined flag and does not import the quarantine module, so condemning a pose moves no done pixel and the cache key (committed poses x certified keys) stands unamended. Quarantine's whole jurisdiction is uncertified material — contradiction_writes skips a certified tile outright, on the ground that the certificate vindicates the geometry that read it. live_pose likewise does not filter condemned poses, deliberately: the readers that must refuse one ask is_quarantined themselves. The property is pinned by projecting a region before and after a condemnation and comparing the arrays.

*Where:* `holo2/src/holo2/solve/tilemap.py:750-823`; `holo2/src/holo2/solve/quarantine.py:22-35`; `holo2/src/holo2/solve/tilemap.py:586-591`; `holo2/src/holo2/solve/DESIGN.md:54` · *dial:* live

**holo3.** absent — holo3 has no quarantine mechanism at all, so there is nothing that could move done pixels and no invariant to hold. The done projection is a pure function of standing placements and certificates, and certificates are terminal (store._fold_certificate raises on a conflict and never removes one).

*Where:* _(no path given)_

*Scheduler row / doc:* holo3/API.md:757-758 — 'No quarantine: word trust is one-way (W5 rival bar at admission), so known_position_words and its consumer are not built'

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo2) 'Zero contradictions on every healthy fixture'; done coverage untouched, adversarially pinned; the W5 block is 236 lines — *artefact:* ARTEFACTS.md:756 -> holo2/docs/MEASUREMENTS.md:1384-1386, :1390
- (holo2) the invariant quarantine is built against is e022's, not holo2's: ~1,780 known-position reads across the six-scan sessions, zero contradictory — *artefact:* ARTEFACTS.md:753 -> docs/RECEIVE-DESIGN-EVIDENCE.md:492
- (holo2) holo2's own quarantine measurement is a wall cost, not a yield: ~1.7 s, +2% — *artefact:* ARTEFACTS.md:755 -> holo2/docs/MEASUREMENTS.md:1345

**Yield relevance.** integrity — source: reader.

**Recommendation.** accept the loss for this row alone — there is nothing to port here, because the invariant is a property of a mechanism holo3 does not have. The ruling that matters is the quarantine row itself, which belongs to the placement/evidence family; if quarantine is ever ported, this invariant (project_done must not read the marking) and its before/after array pin must be ported with it, or the projection's monotonicity and its cache key both break.

**Notes.**

*Reader:* holo3's monotonicity has a different foundation: certificates are terminal by fold, pinned by test_done_ness_is_monotone_through_further_folds. That covers the certificate half of holo2's cache key; the pose half is covered by row done-gate-10, not by this one.

*Refuter (upheld):* *Corrections:* holo3's API.md quote is at :758-759, not :757-758 (:753-757 is the no-journal bullet). A grep of the whole holo3 tree for 'quarantin' returns exactly that one line plus retirement_docs prose — the absence claim is total. Optionally add holo2/src/holo2/solve/records.py:356-364 to holo2's `where`: the PoseRecord docstring restates ruling 1 ('tilemap.project_done never asks: done pixels are certificate-backed') alongside quarantine.py:24-35 and DESIGN.md:54. Classification note: this row's own content changes no holo3 work (it is an invariant of a mechanism holo3 does not have), so it is a rider on the quarantine row rather than an independent ABSENT — which is exactly what the row's recommendation says. Keep it as written; the value is the pin recipe (project a region before and after a condemnation, compare arrays) surviving as a port precondition.

*Reason:* The invariant, the ruling and the total absence all verify; only the API.md anchor slips one line.

---

### done-gate-09 — The done cache and the staleness key it is stamped with

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **nothing observable - cost and ordering only; I re-checked the staleness key for a hole and found none** · ruling needed **N** · seeds: B36

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Only ordering and cost — but a key that missed a change would suppress a window on a stale projection, so it is also an integrity surface.

**holo2.** The projection is a function of two monotone counts — committed poses and certified work keys — so the cache is a per-generation map stamped with that pair; a commit that moved neither carries the whole map into the next generation instead of clearing it. The inheritance test runs once, on the first done() call of a generation, and a generation nobody asked passes its own inheritance along.

*Where:* `holo2/src/holo2/solve/plane_views.py:259-273`; `holo2/src/holo2/solve/plane_views.py:208-217`; `holo2/src/holo2/solve/plane_views.py:241-256`; `holo2/src/holo2/solve/plane.py:549-558` · *dial:* live

**holo3.** Two caches. done_grid is per page, stamped with the global certificate count. done_cells is per (capture, level, region), stamped with a triple maintained at the placement fold: the region's pose count, its cumulative affine-change count, and the global certificate count. All three components are monotone, so an equal stamp means an equal projection.

*Where:* `holo3/store.py:387-394`; `holo3/store.py:415-435`; `holo3/store.py:642-647`

*Scheduler row / doc:* SCHEDULE.md:614-618 (the endgame feeder fix: 'the suppressed codes come off the standing done_grid cache, done_cells stamps itself from maintained per-region counters instead of walking every placement')

**Implementation delta.** holo2 keys on two global monotone counts and inherits the map across generations of an immutable view; holo3 keys on a per-region pose/generation pair plus the global certificate count and mutates a dict on the single-threaded merge path. holo3's key is finer (a pose commit in another region does not invalidate this region) and detects a pose REPLACEMENT explicitly, which holo2 got for free because a revision was a new record and grew len(poses).

**Evidence status.** MEASURED

**Evidence.**

- (holo3) retire and eligible consult the reach through O(1) has_certificate lookups, 23 us measured, was 19,700; the same endgame drain went 632.8 s -> 0.950 s; both sims byte-identical at workers 1 and 8 — *artefact:* holo3/SCHEDULE.md:601-642
- (holo2) the index rebuild the same wave replaced: 1,921 full rebuilds, 54.5 s, 26.3% of the serial wall — *artefact:* holo2/src/holo2/solve/plane_views.py:134-136 (in-tree measurement, not in ARTEFACTS.md)

**Yield relevance.** nothing observable - cost and ordering only; I re-checked the staleness key for a hole and found none — source: second lens (reader said: decides-order-only).

**Recommendation.** keep holo3's

**Notes.**

*Reader:* holo3 recomputes the same array once per level of a capture+region because done_cells is keyed per level while the value is level-independent; cost only. holo2's caching is thread-safe by immutability (one generation per pin), holo3's by confinement to the merge thread — a difference in the concurrency model, not in the answer.

*Refuter (upheld):* *Corrections:* Evidence attribution. Neither number quoted on holo3's side isolates the done cache: '23 us, was 19,700' (SCHEDULE.md:613-615) is refine.color's tile-reach lookup and '632.8 s -> 0.950 s' (:629-631) is the frontier compaction. The only done-cells statement in that block is SCHEDULE.md:615-617 ('the suppressed codes come off the standing done_grid cache, done_cells stamps itself from maintained per-region counters instead of walking every placement'), and it carries no number. What actually earns the MEASURED status is the byte-identity clause at :631-633 ('Both sims byte-identical at workers 1 and 8'). Say that. The holo2-side cite is correct (plane_views.py:134-136: 1,921 full rebuilds, 54.5 s, 26.3% of the serial wall) and is in-tree, not in ARTEFACTS.md, as the row says. Mechanism verified with no staleness hole: the stamp is (n_poses, gen_total, len(certificates)) maintained in _fold_placement (store.py:642-647), and `affine_changed` (:630-639) includes a page change, so a pose that moves page invalidates. One cost-only fact worth the notes: done_grid is cached per page but stamped with the GLOBAL certificate count (store.py:387-394), so a certificate on any page invalidates every page's grid.

*Reason:* Cache and key are correct and hole-free; the cited numbers measure two neighbouring fixes, not this one.

*Second lens (final: CARRIED-DIFFERENT):* I side with the refuter on the evidence attribution and with the reader on everything else. Neither number the reader quoted measures this cache: '23 us, was 19,700' (holo3/SCHEDULE.md:613-616) is the colour refinement row's tile-reach lookup and '632.8 s -> 0.950 s' (holo3/SCHEDULE.md:629-631) is the frontier compaction. The only sentence about this mechanism is holo3/SCHEDULE.md:615-618 and it carries no number; what earns the row a measured status is the byte-identity clause at holo3/SCHEDULE.md:631-633. The holo2 cite is correct and in-tree (holo2/src/holo2/solve/plane_views.py:134-136). On the integrity question, which is the only way this row could touch yield, I re-derived the key and found no hole: the stamp is (poses in this region, cumulative affine changes in this region, global certificate count) maintained at the placement fold (holo3/store.py:642-647), and affine_changed at holo3/store.py:630-639 includes a page change, so a pose that moves page invalidates. All three components only grow. The cost notes the refuter adds are right: done_grid is per page but stamped with the global certificate count (holo3/store.py:387-394), so one certificate anywhere invalidates every page; and done_cells is keyed per capture/level/region although the value is level-independent - I confirmed independence at holo3/plugins/place.py:164-193, where the frame fields the projection reads derive from the printed pitch alone.

---

### done-gate-10 — Permanence — a done retirement against a projection that can recede

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates (in holo3's favour, and unmeasured on both sides)** · ruling needed **Y** · seeds: B35, B36

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** Whether a window retired as done is ever re-offered if the geometry that made it done later moves; a receding projection with a permanent retirement is a silent lost placement.

**holo2.** The admission exit is permanent for the session (a window in _exited is only reconsidered for a re-read, never for a done reversal) and the fire-time retirement is durable as a WindowRecord, which the resume rebuild then reads back. The docstring states the exposure openly: because a revision's affine differs from its parent's by up to the search box, done(revision) is neither a subset nor a superset of done(parent), the magnitude is a boundary sliver of order ~3 cells per revision, and it is UNMEASURED at this pitch.

*Where:* `holo2/src/holo2/solve/place_sched.py:302-306`; `holo2/src/holo2/solve/place_sched.py:354-356`; `holo2/src/holo2/solve/place_job.py:848-858`; `holo2/src/holo2/solve/tilemap.py:781-796` · *dial:* live

**holo3.** Within a run a retired bookmark is permanent — _touch skips retired workers — and the only un-retirement is the subdivision afterlife. Across runs it is not durable at all: a resume re-derives the whole ladder from the fact snapshot, so a window whose projection has receded is re-asked. For the PLACED branch recession is impossible (certificates are terminal and the reach only changes with the affine, which a done window no longer refines); for the pose-free branch a neighbour's pose revision can move the projection in either direction, exactly as in holo2.

*Where:* `holo3/engine.py:360-386`; `holo3/engine.py:535-557`; `holo3/store.py:449-476`; `holo3/snapshot.py`

*Scheduler row / doc:* SCHEDULE.md:562-572; holo3/API.md §10 ('Scheduling state is deliberately NOT durable')

**Implementation delta.** Same within-run permanence; different across runs. holo2 writes the done retirement into the durable record, so a resume inherits it; holo3 keeps no scheduling state and re-derives, so a resume re-asks the gate against the current facts. holo3 additionally removes the exposure for placed windows by judging them on an exact reach rather than a projected extent (row done-gate-04), leaving only the pose-free branch exposed — the same boundary sliver holo2 documents and neither side has measured.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) the sliver is 'a boundary sliver of the extent, on the order of W2's measured ~3 cells per revision' and 'UNMEASURED at this pitch' — holo2's own words — *artefact:* holo2/src/holo2/solve/tilemap.py:781-796; no number for it in ARTEFACTS.md
- (holo3) no artefact — no holo3 measurement of a receding pose-free projection exists — *artefact:* no artefact

**Yield relevance.** decides-certificates (in holo3's favour, and unmeasured on both sides) — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's, and record the residual as a known unmeasured exposure rather than closing it. A costed settlement exists and needs no receiver run: measure/donegeo_realstate.py already folds an archived snapshot and re-derives the gate's verdict per window, so a variant that re-derives window_extent_done before and after each pose revision in a sheet-I resume would bound the recession directly, in minutes of CPU on an existing state. That is the cheapest available answer to a question holo2 left open for a year.

**Notes.**

*Reader:* holo3's resume behaviour makes this strictly less dangerous than holo2's: a wrongly suppressed window returns on the next run. The one place holo3 un-retires within a run is the subdivision afterlife (row done-gate-11).

*Refuter (upheld):* *Corrections:* 'For the PLACED branch recession is impossible (certificates are terminal and the reach only changes with the affine)' is too strong. The placed reach is _window_reach (maintained at the placement fold, store.py:660) PLUS _evidence_reach (maintained at the evidence fold, store.py:737), so an evidence fit that lands AFTER the window retired can grow the reach and un-done it — and the place bookmark is by then permanently retired for the run (engine.py:417, :443). The gate refuses calibrate (calibrate.py:723-728) and revisit (revisit.py:34-38, :104-115) on a done window, so such a fold can only arrive from work already in flight; that makes the exposure small and, like the pose-free sliver, unmeasured — it does not make it impossible. Recommend the row say 'recession for the placed branch is confined to a fold from work already in flight' and keep UNPROVEN. Minor: place_sched.py:302-306 names only the head of the re-consideration block; the substance (_needs_resample guard, the del) is :306-314. The costed settlement proposal is sound and I confirm measure/donegeo_realstate.py exists as the instrument it names.

*Reason:* Row is right that holo3 is strictly safer across runs, but its within-run impossibility claim ignores the evidence half of the reach.

*Second lens (final: CARRIED-DIFFERENT):* The refuter is right that the reader over-claims, and the correction matters for my lens because it is the one place holo3 could lose. The placed reach is the union of the window reach maintained at the placement fold (holo3/store.py:660) and the evidence reach maintained at the evidence fold (holo3/store.py:737-738), so a late evidence fit can grow the reach and un-do a done window whose placement bookmark is already retired for the run (holo3/engine.py:359-386). I narrowed the exposure further than the refuter did: the calibration row that produces those fits computes its cells from the placement it was handed (holo3/plugins/calibrate.py:344), so a fit for an unchanged pose reproduces the same reach exactly; growth needs a fit built on an older pose landing after a revision, and the gate already refuses new calibration and revisit work on a done window (holo3/plugins/calibrate.py:721-724, holo3/plugins/revisit.py:104-110). So the right wording is the refuter's: recession on the placed branch is confined to a fold from work already in flight, not impossible. I keep decides-certificates, and add the reason the reader understates its own case: because holo3 keeps no durable scheduling state and re-derives the ladder from the fact snapshot, a window wrongly suppressed in one run comes back in the next - and the archived sheet-I readout WAS a four-run resume chain, so this is a difference the corpus could actually have exercised, in holo3's favour.

---

### done-gate-11 — Done as a subdivision verdict — whether a done child counts as having served the area

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates (holo3 does strictly more work than holo2 and may gain from it; the population is measured zero in holo2's recorded census on both real sheets, and that census is a lower bound)** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter reclassified to DIVERGED → second lens DIVERGED.

**What it decides.** Whether a subdivided parent whose four children were all suppressed as done gets its cold afterlife armed, i.e. whether an already-spent rectangle can still be offered a cold sweep.

**holo2.** EXIT_SERVED = {placed, done_covered, settled_placed}. A child that exited done_covered counts as having served its area, so child_verdict is truthy and the parent RESTS — its cold afterlife is never armed. Only when all four children refused about the rectangle does the parent get parked for cold.

*Where:* `holo2/src/holo2/solve/place_subdivide.py:50-55`; `holo2/src/holo2/solve/place_subdivide.py:140-154` · *dial:* live

**holo3.** _afterlife tests only 'any child placed' as the rest condition and 'all children retired' as the settle condition; a child retired for being done is settled but not placed, so the parent's afterlife fires — it is un-retired, cold-armed and re-pushed. At its next pop place_retire_cause asks window_fully_done on the parent, which for a parent whose four quarters are all done answers done as well (dropped children are dropped for zero support or off-frame, neither of which blocks done_covers), so the parent retires again with cause done_covered.

*Where:* `holo3/engine.py:535-557`; `holo3/engine.py:566-576`; `holo3/plugins/place_sched.py:245-256`

*Scheduler row / doc:* SCHEDULE.md:572-575 (the gate's only door is place's retire)

**Implementation delta.** holo2 encodes 'done means served' in the subdivision verdict; holo3 does not, and reaches the same end state one pop later by re-asking the gate on the parent. The cost is one un-retire, one re-push and one pop per fully-done subdivided parent; no cold pass is actually built, because retire precedes prepare.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) the subdivision-child done population is measured at 0/57 e029 and 0/15 xerox — no child on either real sheet was ever gated as done, so holo2's EXIT_SERVED clause never fired there — *artefact:* ARTEFACTS.md:579 -> holo2/docs/MEASUREMENTS.md:1258-1266
- (holo3) no artefact — no count of done-retired subdivision children exists for holo3 — *artefact:* no artefact

**Yield relevance.** decides-certificates (holo3 does strictly more work than holo2 and may gain from it; the population is measured zero in holo2's recorded census on both real sheets, and that census is a lower bound) — source: second lens (reader said: decides-order-only).

**Recommendation.** keep holo3's

**Notes.**

*Reader:* I re-derived the 'retires again at the next pop' conclusion by reading place.child_windows (children that fall off the frame or carry zero support are dropped, and neither case can leave a supported uncovered cell in the parent) — it is not measured. holo2's own numbers say the case never arose on either real sheet, which is why this stays an ordering note rather than a divergence.

*Refuter (reclassified):* *Corrections:* The load-bearing inference is false in general. pose.subdivision_child_extents (holo3/plugins/pose.py:815-831) returns four side x side CORNER squares with side = max(MIN_WINDOW_CELLS=70, min(h, w) // 2); they tile the parent only when h == w == 2*side. Full windows are 200x200 (WINDOW_CELLS=200, geometry.py:8), where side=100 and the quarters tile exactly — so the row's conclusion holds for the dominant case. A CLIPPED window does not: window_plan clips at the region edge (place.py:200-203), so a region narrower than 200 cells yields e.g. a 200x150 window with side=75, whose four corners leave rows 75..125 across the full width belonging to NO child. For such a parent, four done children do not imply a done parent: engine._afterlife (engine.py:535-560) un-retires it, sets cold_armed, and at the next pop place_retire_cause finds window_fully_done False, so a COLD placement pass RUNS on a rectangle holo2's EXIT_SERVED (place_subdivide.py:49-54, :143-155) would have rested. A cold pass is dear and can place — and hence certify — so this is not 'the same end state one pop later' and it is not decides-order-only. Set yield_relevance to decides-certificates (direction unknown; holo3 may do strictly more work and may gain from it), ruling_needed true, and replace the argument 'dropped children are dropped for zero support or off-frame, neither of which blocks done_covers' with the tiling condition. Evidence wording also needs care: MEASUREMENTS.md:1258-1266 gives 0/57 (e029) and 0/15 (xerox) as the ppc 2/1 SUBDIVISION-CHILD denominator plus 'ZERO at ppc 4/1 and 8/1'; 'no child on either real sheet was ever gated as done' is an inference over those two statements, and one of e029's 45 recorded hits is not accounted for by the 44/271 ppc 2/1 full-extent figure.

*Reason:* Reader's 'the parent retires again at the next pop' fails for any non-square (clipped) window, where holo3 arms a cold pass holo2 would never run.

*Second lens (final: DIVERGED):* I side with the refuter, and the divergence is wider than either side states. The refuter's counter-example is correct: pose.subdivision_child_extents (holo3/plugins/pose.py:814-831) returns four corner squares of side max(70, min(h,w)//2), which tile the parent only when it is square; window_plan clips windows at the region edge (holo3/plugins/place.py:196-201), so a 200x150 window yields 75-cell corners and leaves a band belonging to no child. But the reader's premise is wrong even before that. The two trees rest a parent on different conditions: holo2 rests it when ANY child served, and a done child counts as having served (holo2/src/holo2/solve/place_subdivide.py:49-54, :143-155); holo3's afterlife rests it only when a child was PLACED (holo3/engine.py:535-560). So the divergence needs only ONE done child among four, not four - and with three siblings exhausted the parent is plainly not covered, so at its next pop the check does not retire it (holo3/plugins/place_sched.py:229-252) and a cold full-extent placement pass runs where holo2 rested. A cold pass can place, and a placement can certify, so this is not order-only. Two further facts worth carrying: the afterlife is triggered by a place OUTCOME fold (holo3/store.py:604-612), so a parent whose last child left through the gate at its pop never wakes at all - the behaviour is order-dependent; and the reader's evidence line over-reads its source, since holo2/docs/MEASUREMENTS.md:1258-1266 gives 0/57 and 0/15 as the coarsest-rung subdivision-child denominator and separately says zero at the finer rungs, over a census the same document calls a lower bound.

---

### done-gate-12 — The colour gap — window-granular done-ness cannot suppress a per-lane colour row; the cell-level emission mask is the colour done gate

**HOLO3-ONLY** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter upheld.

**What it decides.** Whether the colour endgame stops. Nothing retires the colour evidence row, so the only done-ness colour gets is that certified tiles' cells are excluded from what the lane assembles and emits.

**holo2.** absent — holo2 has no colour path at all; its FORMATS can name colour rows but the codecs fail fatally, and no colour number of any kind exists for it.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** The colour lane subject is (capture, level, page) and its retire predicate is a constant False, so the row never retires. Done-ness enters two levels down: suppressed_tile_codes / emission_mask drop the cells of fully-certified tiles from every window's contribution to the region assembly and to the head fit, and color_refine refuses a window whose every (tile, stream) pair is certified and refuses to prepare when no cargo cell survives the emission mask. Window-granular suppression exists for colour only through the shared place / calibrate / revisit rows.

*Where:* `holo3/plugins/color_region.py:695-701`; `holo3/plugins/color_sites.py:46-70`; `holo3/plugins/color_region.py:363-372`; `holo3/plugins/color_region.py:515-527`; `holo3/plugins/color_refine.py:351-368`; `holo3/plugins/color_refine.py:381-389`; `holo3/store.py:396-398`

*Scheduler row / doc:* SCHEDULE.md:590-593 ('Colour's evidence row is per-LANE, so window-granular done-ness cannot suppress it — that is the gate's honest colour gap')

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the colour sim is unmoved job for job when the gate lands — every window there still touches one of its 21 open tiles — *artefact:* holo3/SCHEDULE.md:589-592
- (holo3) 'colour evidence is per LANE, so window-granular done-ness cannot suppress the colour lane's work — that is where colour endgame cost actually sits' — *artefact:* holo3/conversion_docs/OPEN-2026-08-31.md:128-131
- (holo2) holo2 has no colour number of any kind, by construction — *artefact:* ARTEFACTS.md:817 (gap G-17)

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's for this campaign, and record the gap as a scheduled line rather than a retirement blocker. It is not a holo2 port question — there is nothing on the holo2 side to port — but it is the one place in this family where a mechanism is known to be missing and its cost is named ('where colour endgame cost actually sits') with no number attached. The cheap first measurement is a per-lane cost census on an existing colour run's events; no decode.

**Notes.**

*Reader:* Two facts about the emission mask worth carrying: it is the ONLY done-ness colour assembly sees, and store.suppressed_codes (off the cached done_grid) and color_sites.suppressed_tile_codes (rebuilt from the certificate mapping) are two spellings of the same set, used by color_refine and color_region respectively. They agree today; nothing pins that they must.

*Refuter (upheld):* *Corrections:* Outside the mandated set (HOLO3-ONLY) but checked. G-17 is ARTEFACTS.md:824, not :817. The colour-gap bullet is OPEN-2026-08-31.md:128-130 (:131 opens the next bullet). _color_never_retire is color_region.py:700-701 (constant False) with _color_eligible at :695-698 — the pair as cited. The mask reaches further than the row says: emission masks are consumed not only by color_region.py:363-372 and :515-527 but by color_region_head.py:330, :407, :427 (the head fit) AND color_arms.py:104-109, :233-238 (the colour-uplift arms), so done-ness gates the uplift arms too. The 'two spellings' note is right and worth keeping; the one asymmetry is that color_sites.suppressed_tile_codes (color_sites.py:46-62) applies no on-grid clip where tiles.done_tile_grid (tiles.py:567-580) does — they agree while every certificate is on-grid, and nothing pins that.

*Reason:* Colour gap is real and correctly stated; the mask's consumer list is incomplete and one gap id is misnumbered.

---

### done-gate-13 — Page-level done retirement for lane-scoped rows

**HOLO3-ONLY** · evidence **n/a** · yield **decides-order-only** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter upheld.

**What it decides.** When the plane-field and colour-uplift lane rows stop being offered — a whole-page rather than a per-window done test.

**holo2.** absent — holo2 has no fields or uplift rows.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** fields retires its lane subject when the page's whole done_grid is True; uplift is eligible only while the page's done_grid is not all True, and retires on the negation of its own eligibility. Both read the same cached per-page grid the window gate is built on.

*Where:* `holo3/plugins/fields.py:796-797`; `holo3/plugins/uplift.py:310-316`

*Scheduler row / doc:* SCHEDULE.md:245-259 (fields), :129-149 (uplift)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo3) no artefact isolates the cost these two retire clauses save — *artefact:* no artefact

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* Listed for completeness: these are the only two places the done grid is used at page rather than window granularity, and they are the coarsest form of the same law.

*Refuter (upheld):* *Corrections:* Outside the mandated set but checked. fields._fields_retire is fields.py:796-797 exactly. uplift is :310-315 (_uplift_eligible) and :317-318 (_uplift_retire) — the row's :310-316 stops one line short of the retire clause it describes. Both read store.done_grid(page).all(), the same cached per-page grid the window gate is built on, as the row says.

*Reason:* Both page-level retirements verified verbatim; one citation is one line short.

---

### done-gate-14 — Recording the retirement cause (what a census can see)

**OUT-OF-FILTER** · evidence **n/a** · yield **integrity** · ruling needed **N** · seeds: B35

Classification trail: reader OUT-OF-FILTER → refuter upheld.

**What it decides.** Nothing about which work runs — but it decides whether the gate's rate is measurable at all, which is why holo2's realized rate is a lower bound.

**holo2.** The fire-time retirement writes reason 'done_covered' onto the durable WindowRecord and is countable; the admission-door hits set an in-memory _exited entry with no record, so they are invisible to a census. holo2's own writeup calls its 3.2-3.5% a LOWER BOUND and quotes an off-census floor of +44 (e029) and +11 (xerox).

*Where:* `holo2/src/holo2/solve/place_job.py:848-873`; `holo2/src/holo2/solve/place_sched.py:354-356` · *dial:* live

**holo3.** place_retire_cause returns the clause, not just its truth, and the engine stamps it on WindowRetired; the unreachable pass-side done_covered settle was deleted. Ordering still hides overlaps: a window that is both placed and done records 'placed', and one that is both exhausted and done records 'exhausted'.

*Where:* `holo3/engine.py:363-377`; `holo3/plugins/place_sched.py:226-247`

*Scheduler row / doc:* holo3/conversion_docs/OPEN-2026-08-31.md:132-143

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo2) off-census floor +44 e029 / +11 xerox, the same order of magnitude as the 45 / 42 recorded hits — *artefact:* ARTEFACTS.md:577 -> holo2/docs/MEASUREMENTS.md:1246-1247
- (holo3) a read-only pass over 1.9 M events found zero done_covered settles and read it as a dead gate — the wrong instrument; ANSWERED and CLOSED 2026-08-31 — *artefact:* holo3/conversion_docs/OPEN-2026-08-31.md:132-143

**Yield relevance.** integrity — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* One line, per the filter: recording only. It is worth carrying into the comment phase because the 'gate never fires' false alarm was caused precisely by reading an event stream that could not name the clause.

*Refuter (upheld):* *Corrections:* Outside the mandated set but checked. engine.py:359-377 is the retire-cause stamping (the re-ask comment at :365-369 explains why the clause is asked twice); place_sched.py:229-252 returns the clause. The ordering-hides-overlaps observation is exactly right: place_retire_cause returns placed, then exhausted, then done (place_sched.py:243-252). holo2's off-census floor +44/+11 and the 45/1,273 = 3.5%, 42/1,324 = 3.2% rates reproduce at MEASUREMENTS.md:1244-1247, and the writeup does call its own share a LOWER BOUND.

*Reason:* Recording-only row, and every number in it resolves.

---

## Close

16 rows; 4 carry a ruling.

**Reader's family notes.** Sixteen rows; two need a ruling on substance (close-12 integrity disposition, close-10 the forced final solve) and two are one-line rulings on drops (close-13 durable record, close-15 surplus audit). The family's headline finding: the close ALGEBRA is a clean carry on both sides (both pinned to v1, holo3 additionally pinned prefix-by-prefix against its own batch oracle), and every divergence is in the SCHEDULING and DISPOSITION shell around it. Three record corrections the map should inherit. (1) ARTEFACTS.md:600 quotes the PRE-P3-1 consult cost (1,358 consults = 34.1 s = 6.0% of wall) from holo2/src/holo2/solve/close.py:46-47 — that is the baseline P3-1 REMOVED; the post-build re-measurement on the same driver and sheet (1,358 consults = 0.74 s = 0.1% of wall, -46x; exactly two close_volume runs at 102 ms and 132 ms) is at holo2/src/holo2/format/DESIGN.md:166 and is not in ARTEFACTS.md. (2) There is NO direct holo2-vs-holo3 close pin — holo2 is pinned to v1 by tests/holo2_oracles/test_oracle_close.py and holo3 to v1 by holo3/tests/test_h3_drift_format.py, both via `pytest.importorskip`, so after the deletions the surviving leg silently skips (gap G-02, ARTEFACTS.md:803). (3) 05-fountain.md:191-192's claim that detach-to-open semantics are "meaningless without resumable state" is stale of the tree that shipped: holo3 has resumable state (facts.npz + --resume), it just has no durable close record. Nothing in the close family is measured on holo3 for COST — `EngineStat.consult_cpu_s` exists and is emitted but no artefact quotes a value on any sheet.

**Refuter's family notes.** MECHANISMS NO ROW COVERS. (1) THE CONSULT COST IS MEASURED, EIGHT TIMES OVER. The family notes and close-05/close-06 all assert holo3's consult cost is unmeasured. `scheduler.consult_cpu_s` sits in every archived holo3 report.json: sheet-H seven-capture max-stack 0.881 s (close OPEN with counting:false, so a real close_volume solve ran, inside a 121,967.7 CPU-s run); sheet-I chain 1.311 / 0.777 / 0.589 / 0.608 s; the three 2026-09-02 e029 runs 0.279 / 0.192 / 0.333 s. That settles close-10 and retires the family's one open cost question with no decode. (2) HOLO3 HAS A SECOND, EARLIER METADATA GATE THAT HOLO2 HAS NO COUNTERPART FOR. holo3/store.py:905-916 folds every certificate's metadata bit into `self._equations` and raises on opposite bits at one equation index — at INGEST, before any consult. Consequences no row states: `_MetadataGate.observe`'s own opposite-bit raise (holo3/format/close.py:319-321) is dead code in production because the store always fires first; and --no-close, which in holo2 provably never enters the close layer, aborts a holo3 run on the same contradiction. (3) DEFAULT MODE IS ALMOST UNEXERCISED ON PAPER IN HOLO3. Every archived holo3 real-capture decode ran --complete (holo3/conversion_docs/overnight/final-manifest.json; scratch/sheetI-20260831/argv-resume*) or --no-close (arms wave; scratch/angle-residue/*) EXCEPT three runs from 2026-09-02 (scratch/page-domain-qual/*, no close flag). Those three are the whole of holo3's real-capture evidence for close preemption (close-01) and for close-10's forced final — and all three verified inside the loop, so close-10's extra final solve has never fired on paper. They also give the cleanest cross-tree fact in the family: holo3 default-mode e029 = 1,357 certificates, identical to holo2's e029 K-stop of 1,357 (ARTEFACTS.md:595), against holo3 --complete 1,940 on the same sheet (PARITY.md:9). (4) ARTEFACTS.md:235 CARRIES A FLAG ERROR THE MAP WILL INHERIT. It attributes '--plane-fields --complete' to sheet-I run 1, taken from a run-dir argv that experiments/034:58-60 records as overwritten by a later launch; the log itself (:30) and MEASUREMENTS-2026-08-31.md:24 both say --no-close. ARTEFACTS.md:234 and :235 consequently describe the SAME 5,543-certificate run under two different close modes, and close-08 and close-09 each cite it as evidence for a different flag. Worth an ARTEFACTS.md correction, not just a map footnote. (5) SMALL, UNLISTED, OUT-OF-FILTER: holo3's `solve` guard requires n_certs > 0 (engine.py:598) where holo2's final consult calls close_volume(()) and writes an open record — a zero-certificate run ends the same way but reports differently; and holo3's unguarded `table[index]` (format/close.py:328) turns an out-of-range equation index into an IndexError that cli._decode does not catch (it catches only IntegrityError/ValueError/OSError), where holo2's coefficient_mask validated the range (format/metadata.py:173-176). Both are authorised by the 05-fountain.md:272-277 validation-wall drop.

**Second lens (yield) family notes.** Second lens = YIELD. Adjudication summary: the first refuter is upheld on every one of the eight disagreements, including all three reclassifications (close-04 and close-11 out of CARRIED-IDENTICAL, close-10 to DIVERGED); I reproduced each load-bearing claim in the code and in the archived artefacts rather than accepting it. Two findings the family should inherit. (1) THE COST QUESTION IS CLOSED WITH NO NEW RUN. scheduler.consult_cpu_s is in every archived holo3 report.json: sheet-H max-stack 0.881 s (close open with counting false, so close-10's forced solve DID fire on the largest colour volume in the record, inside a 121,967.7 CPU-s run); sheet-I chain 1.311 / 0.777 / 0.589 / 0.608 s; the three 2026-09-02 e029 runs 0.279 / 0.192 / 0.333 s. close-05, close-06 and close-10 all lose their 'unmeasured' notes. (2) THE SHEET-I RUN-1 FLAG ERROR IS SETTLED BY THE RUN'S OWN ARTEFACT, not only by the experiment log: scratch/sheetI-20260831/report-first.json carries close.status count_ready with counting true, and holo3/engine.py:629 emits deferred for every --complete look, so a --complete run cannot produce that label. ARTEFACTS.md:235 needs correcting; ARTEFACTS.md:234 and :235 currently describe the same 5,543-certificate run under two different close flags. On yield specifically: only close-08 (--complete) and close-09 (--no-close) carry a measured certificate consequence, and in both the holo2-to-holo3 delta is nil or operator-surface; close-01's cadence delta measures at exactly zero (holo3 default e029 1,357 = holo2 K-stop 1,357); close-10 costs under a second and changes nothing; close-12 changes nothing on the archived corpus but is the only row whose exposure, if it ever fires, is the total loss of a run's harvest. Recommended ports, in order: close-12's narrow half (write the products before the error escapes), close-11's frozen close pin, close-05's index range check. Everything else: keep holo3's.


### close-01 — Close preemption — a verified close ends the run out of band and abandons everything still queued or running

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: B55

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** When the run stops, and therefore how much certifying work is never done at all.

**holo2.** After every committed proposal (serial and pooled alike) `_apply` calls `_maybe_consult`; the close is asked out of band — no descriptor, no work id, no lease, no slot, no spend row. If the consult produces a terminal store state the run returns a terminal outcome immediately. In the pool, `_cancel` then does `pool.shutdown(wait=True, cancel_futures=True)`: queued fires are cancelled, started ones finish unread, and the count of abandoned fires is reported.

*Where:* `holo2/src/holo2/engine/orchestrator.py:643-646`; `holo2/src/holo2/engine/orchestrator.py:840-875`; `holo2/src/holo2/engine/orchestrator.py:315-329`; `holo2/src/holo2/engine/orchestrator.py:263-266`; `holo2/src/holo2/engine/DESIGN.md:213-229` · *dial:* live

**holo3.** After each batch of completed futures is merged, if certificates grew the engine consults the close on the main thread; a `verified` result breaks the loop. The `finally` clause then calls `executor.shutdown(wait=False, cancel_futures=True)`, so queued jobs are cancelled and running ones are abandoned unread while `_finish` writes the payload, snapshot and diag products. Same intent, same out-of-band shape; the close is deliberately not a scheduler row.

*Where:* `holo3/engine.py:189-211`; `holo3/engine.py:200-204`; `holo3/engine.py:209-210`; `holo3/SCHEDULE.md:357-359`; `holo3/API.md:604-613`

*Scheduler row / doc:* SCHEDULE.md header ("The close is NOT a row: it stays engine-held with its two gates") + SCHEDULE.md:357-359 ("race mode may end the run right here, cancelling everything pending")

**Implementation delta.** Three differences. (1) CADENCE: holo2 consults after EVERY commit (one proposal at a time at the wall); holo3 consults once per merged BATCH of completed futures, so at --workers N>1 up to N jobs' certificates land before the close is asked — preemption fires a little later and costs fewer consults. (2) WAIT: holo2's cancel joins the pool (`wait=True`) and counts the abandoned fires; holo3 does not wait and counts nothing (the interpreter's own executor atexit hook joins the threads later). (3) TRIGGER GUARD: holo3 only consults when `grew` is true (a certificate fact actually changed the store); holo2 consults unconditionally and lets the frontier-version compare refuse. None of the three changes which tiles can certify before the stop; they change WHEN the stop lands and what it costs to look.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) close preemption worth 3.7x (v1's 49.67 s -> 13.46 s) — v1's number; holo2 never re-measured it — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:602 (cites holo2/src/holo2/engine/DESIGN.md:492-494); gap G-29 at ARTEFACTS.md:839
- (holo2) H3bis real sheet 1,359 certified vs v1's 1,930 for the same 465,580 B, sha byte-identical — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:593
- (holo2) xerox K-stop 1,356 certificates / 410 s vs `--complete` 1,882 / 719 s; e029 K-stop 1,357 / 507 s vs `--complete` 1,911 / 1,127 s — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:594-595
- (holo3) sheet I run 1 was driven `--plane-fields --complete` (preemption deliberately off) and run 2 took the first VERIFIED close at 5,866; VERIFIED byte-exact 2445b95db5b49bf3, 1,798,761 B, three times — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:235
- (holo3) at --workers N>1 the race-mode close can fire at different frontiers, so the certificate set varies run to run (measured 84/90/80 certificates on identical code) while payload bytes stay identical — *artefact:* holo3/API.md:604-613 (no ARTEFACTS.md row; the API doc is the only record)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — the mechanism, the tradeoff and the operator remedy (`--complete`) are all present and exercised on the deepest read on record.

**Notes.**

*Reader:* The certificate-count difference between a preempted close and a completed run is a STOP-POLICY result on both sides, not an algorithm result (holo2/src/holo2/engine/DESIGN.md:496). Neither tree has measured holo3's own preemption saving; the 3.7x is v1's number carried through holo2's docs and is gap G-29. holo3 dropping holo2's `cancelled` counter is diag-only.

*Refuter (upheld):* *Corrections:* Classification, the three deltas and every holo2 cite are correct at HEAD (holo2/src/holo2/engine/orchestrator.py:643-646 consults per COMMIT inside the done-loop at :297-312; :324 shutdown(wait=True, cancel_futures=True); :325 counts the abandoned fires. holo3/engine.py:200-204 consults per merged BATCH, gated on `grew` from _merge's certs_grew at :485-512; :210 shutdown(wait=False)). TWO EVIDENCE ROWS MUST CHANGE. (1) WRONG: 'sheet I run 1 was driven --plane-fields --complete (preemption deliberately off)'. experiments/034-sheet-i-full-readout.md:30 records run 1 as `open (--no-close), 266-symbol margin`, and holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:24 says 'close skipped by --no-close'. ARTEFACTS.md:235 (and scratch/sheetI-20260831/argv-first) say --complete because that run dir's argv was OVERWRITTEN by a later resume launch — experiments/034 states this as its own provenance caveat at :58-60. Runs 2-4 were --complete (scratch/sheetI-20260831/argv-resume{,-2,-3}); so every VERIFIED close on sheet I came from --complete's exhaustion consult, not from preemption. (2) MISSING, and it is the row's only real holo3 preemption artefact — already inventoried at ARTEFACTS.md:104 and :768 but not recognised as default-mode: three e029 decodes run 2026-09-02 with NEITHER flag, i.e. preemption live — scratch/page-domain-qual/{base-e029-run.64152,merged-default-run.64831,merged-null-run.64562}/argv; all three VERIFIED e5021f8d... 465,580 B at 1,357 / 1,356 / 1,360 certificates (report.json -> close), against holo3 --complete 1,940 on the same sheet (holo3/conversion_docs/PARITY.md:9). holo3's own preemption tradeoff on e029 is therefore -583 certificates, and holo3's K-stop 1,357 EQUALS holo2's e029 K-stop 1,357 (ARTEFACTS.md:595) exactly — a same-sheet, same-mechanism cross-tree agreement the row should carry instead of the API.md 84/90/80 stub.

*Reason:* Mechanism and delta stand; the sheet-I flag attribution is refuted by the experiment log and the only real holo3 preemption evidence is missing.

*Second lens (final: CARRIED-DIFFERENT):* The refuter is right on both evidence points and I confirm the mechanism cites at HEAD. holo2 asks the close after every committed proposal (orchestrator.py:815-825 via _apply) and joins the pool counting abandoned fires (orchestrator.py:324-325); holo3 asks once per merged batch, gated on certs_grew (engine.py:196-204 with engine.py:485-512), and shuts down without waiting (engine.py:210). The sheet-I run-1 flag attribution in ARTEFACTS.md:235 is REFUTED by the run's own artefact, not just by the log: scratch/sheetI-20260831/report-first.json carries close.status count_ready with counting true, and holo3/engine.py:629 emits deferred for every --complete consult, so a --complete run cannot produce that label; experiments/034-sheet-i-full-readout.md:30 says --no-close and :58-60 records the argv overwrite (argv-first even carries the placeholder path /path/to/facts.npz). The missing artefact is real and decisive: scratch/page-domain-qual/{base-e029-run.64152,merged-default-run.64831,merged-null-run.64562}/argv carry neither close flag, so preemption was live, and all three verified 465,580 B at 1,357 / 1,356 / 1,360 certificates. On yield: the mechanism decides the stop and therefore the final certificate count (1,357 default vs 1,940 under --complete on the same sheet, holo3/conversion_docs/PARITY.md:9), but the holo2-to-holo3 DELTA measures at zero on that sheet - holo3 default 1,357 equals holo2's K-stop 1,357 (ARTEFACTS.md:595).

---

### close-02 — The three consult modes — observe / close / final — splitting the OBSERVATION from the DECISION

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B55

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a given look at the certified frontier may end the run, and what the operator is told while it may not.

**holo2.** Three mode strings are declared on both sides of the engine/solve import wall and pinned equal by a data test: `observe` counts and reports but never closes, `close` closes when the count gate opens, `final` closes now and skips the count gate. `Orchestrator._deferred` (= `--complete` or `--no-close`) is the single question both consult sites ask; mid-run it selects `observe`, at exhaustion it selects `final` (complete), `observe` (no-close) or `close` (default). Observe consults are counted separately as `observations` so the health rows' `consults` number keeps meaning a decision.

*Where:* `holo2/src/holo2/solve/close.py:111-117`; `holo2/src/holo2/solve/close.py:472-514`; `holo2/src/holo2/engine/consult.py:24-29`; `holo2/src/holo2/engine/orchestrator.py:815-825`; `holo2/src/holo2/engine/orchestrator.py:827-838`; `holo2/src/holo2/engine/orchestrator.py:877-889` · *dial:* live

**holo3.** There is no mode vocabulary and no protocol across a package wall: one boolean `final` plus the two request flags compose the same three behaviours inline in `_close_decide`. `solve = not no_close and n_certs > 0 and (final if complete else (ready or final)) and (final or close_is_new())`. The observation always runs (absorb + `count_progress`) whatever the flags say, and `_emit_close_check` labels the non-deciding look `deferred` (complete) or `count_ready`/`open`.

*Where:* `holo3/engine.py:586-612`; `holo3/engine.py:598-601`; `holo3/engine.py:614-637`

*Scheduler row / doc:* conversion_docs/05-fountain.md §2.6 ("Scheduling function — engine contract, no pull machinery"); CLOSE-PORT-SPEC.md:42-56 (the diag seam)

**Implementation delta.** holo2 makes the mode an explicit, testable vocabulary crossing an import firewall (engine names it, solve implements it, a data pin keeps the strings equal); holo3 folds the same three behaviours into one boolean expression on one class, because engine and format live in one tree and there is no wall to cross. Behaviourally identical for `observe` and for `--complete`'s deferred `final`. NOT identical in default mode's exhaustion consult — see close-10. Cosmetic: with BOTH `--complete` and `--no-close`, holo2 still reports reason `deferred` when the state is ready, holo3 reports `count_ready` (holo3/engine.py:628-631).

**Evidence status.** PINNED

**Evidence.**

- (holo3) golden close-status sequences per mode: default ("open","open","open","verified"); --complete ("deferred" x4, then the deciding consult); --no-close ("open","open","open","count_ready","count_ready") — *artefact:* holo3/tests/test_h3_engine_contract.py:85-88 with tests at :786-818
- (holo2) the three mode strings are pinned equal across the engine/solve wall by a data test — *artefact:* holo2/src/holo2/solve/close.py:28-30 naming holo2/tests/engine/test_close_vocabulary.py (no ARTEFACTS.md row)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — same three behaviours, pinned by goldens, with the wall-crossing ceremony correctly dropped.

**Notes.**

*Reader:* holo2's 2026-08-13 defect ("the operator watched certificates pile up beside 'K unknown'") is the reason the observation survives the deferral; holo3 reproduces that — the counting rows and metadata rank ride every CloseCheck regardless of mode (holo3/engine.py:607, :632-637). holo3 does not distinguish observations from decisions in any counter; its meter is `consult_cpu_s` instead.

*Refuter (upheld):* *Corrections:* No change. Verified: the three mode strings on both sides of the wall (holo2/src/holo2/engine/consult.py:24-29 and holo2/src/holo2/solve/close.py:112-115) with the data pin holo2/tests/engine/test_close_vocabulary.py:15-24 existing at HEAD; the single `_deferred` question at orchestrator.py:827-838 selecting observe mid-run (:823) and final/observe/close at exhaustion (:886-888); holo3's one-boolean fold at holo3/engine.py:598-601 and the `deferred` label gated on `complete and not no_close` at :628-631. Goldens exist and match the quoted sequences (holo3/tests/test_h3_engine_contract.py:85-89, tests at :786-812).

*Reason:* Every claim reproduced against current code on both sides.

---

### close-03 — Consult eligibility — refusing a look whose input has not moved, in one integer compare

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B55, B58

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Only how often the close is asked (ordering/cost); never what may certify.

**holo2.** The consumer names one derived key (`VolumeClose.frontier = COLLECTION_CERTIFIED`) whose VERSION is the certified membership count. The orchestrator records that version PER GATE SELECTOR in `self._consulted` and returns immediately when it has not moved, so the O(certified) materialisation happens only after the compare. Because certificates are terminal and immutable, an unmoved version means literally the same equations. An in-run dict, so a run that resumes a session asks the inherited frontier once.

*Where:* `holo2/src/holo2/engine/orchestrator.py:840-863`; `holo2/src/holo2/engine/orchestrator.py:111-115`; `holo2/src/holo2/solve/close.py:463-467`; `holo2/src/holo2/engine/consult.py:80-84` · *dial:* live

**holo3.** One engine field `_n_certs_at_last_consult`, initialised to -1, compared against `len(self._certificates)`; a non-final consult whose count is unchanged returns None before touching anything. The engine additionally only calls the mid-run consult when the merge batch actually changed a certificate (`grew`), so the compare is a second belt. `final=True` bypasses the compare entirely.

*Where:* `holo3/engine.py:171`; `holo3/engine.py:586-591`; `holo3/engine.py:195-201`

*Scheduler row / doc:* conversion_docs/05-fountain.md:176-178 ("Gate, in order: (a) certificate count grew since the last consult (the tried-set floor: remember n_certs_at_last_consult)")

**Implementation delta.** Same idea (membership count as the input digest, refused in integer time), different plumbing: holo2 reads a store version keyed by a resource key and remembers it per GATE SELECTOR (so the exhaustion gate has its own memory when deferred); holo3 keeps one plain integer and expresses 'the exhaustion gate always looks' as the `final` bypass. holo2 also separates `observations` from `consults` in its work counters; holo3 meters only `consult_cpu_s`. Neither can change which tiles certify — a refused consult has, by construction, the same input as the last one.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) close consult 1,358 consults = 34.1 s = 6.0% of wall, linear at ~30 us/certificate (the PRE-P3-1 baseline the eliminator removed) — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:600 (cites holo2/src/holo2/solve/close.py:46-47)
- (holo2) "a consult that decides nothing now costs no commit sequence number either (the spend row used to cost one per look)" — *artefact:* holo2/src/holo2/engine/DESIGN.md:223-226 (no ARTEFACTS.md row)

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's.

**Notes.**

*Reader:* One holo2 configuration surface has no holo3 counterpart: the close's gate is a RECIPE field (`RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD)`, holo2/src/holo2/engine/recipe.py:598), and `_maybe_consult` returns immediately if a recipe declared `GATE_EXHAUSTION` instead (orchestrator.py:816-817). Both shipped recipes declare GATE_COUNT_READY (recipe.py:598, :611), so the branch is never taken in production; holo3 hardcodes the equivalent. Not a yield row.

*Refuter (upheld):* *Corrections:* One citation nit: 'both shipped recipes declare GATE_COUNT_READY (recipe.py:598, :611)' — :598 declares it; :611 is RECIPE_V1_FINEST, which INHERITS the close entry unchanged (holo2/src/holo2/engine/recipe.py:611-617 rewrites only TASK_PLACE entries). Say 'inherits' rather than 'declares'. Everything else verified: the per-selector memory at orchestrator.py:111-115 and the compare at :856-859; holo3's single `_n_certs_at_last_consult` at holo3/engine.py:171,589-591 with the `final` bypass.

*Reason:* Correct as stated apart from one inherited-vs-declared citation.

---

### close-04 — The count gate — the cheap necessary condition that licenses a full close attempt

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **N** · seeds: B55, B56

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT → second lens CARRIED-DIFFERENT.

**What it decides.** Whether the expensive GF(2) solve runs at all on this look; not what can certify.

**holo2.** `_CloseState.ready` = `count_ready or metadata.terminal`: every fountain block of every stream has at least K_b distinct ESIs, OR the metadata system is in a state (inconsistent, malformed, unsupported at the trust floor) that only `close_volume` can turn into a durable answer. A `close`-mode consult that is not ready publishes the counting report and decides nothing. The batch twin `close_count_status` / `close_count_ready` exists in `format/` and is exported but has no production caller — it is the equivalence oracle.

*Where:* `holo2/src/holo2/solve/close.py:346-355`; `holo2/src/holo2/solve/close.py:488-499`; `holo2/src/holo2/format/fountain_close.py:502-570` · *dial:* live

**holo3.** `CloseProgress.ready` is the same disjunction and `count_progress()` returns it alongside the per-block have/needed rows. `_close_decide` uses it as the mid-run solve condition in default mode. `close_count_status` / `close_count_ready` / `close_count_progress` live in `format/close.py` with, by ruling, NO production caller — they are the batch oracles the incremental state is pinned against.

*Where:* `holo3/format/close.py:454-462`; `holo3/format/close.py:464-480`; `holo3/engine.py:596-601`; `holo3/format/close.py:213-293`

*Scheduler row / doc:* conversion_docs/05-fountain.md:178-183 (the count-only pass: "NO decoder, NO rank, NO coefficient rows"; metadata-terminal states report ready)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN — corrected in the merge: reader said PINNED; refuter: the named pin compares holo3's incremental state to holo3's OWN batch function, and no holo2-vs-holo3 count-gate pin exists anywhere.

**Evidence.**

- (holo3) the incremental state's `ready` equals `close_count_status(prefix, row)[0]` at EVERY prefix of a shuffled certificate stream, for all three families (k, cmy8, pooled) — *artefact:* holo3/tests/test_h3_close_state.py:78-96
- (holo3) count-readiness is checked against v1-emitted volumes across K, cmy7, cmy8-v0, pooled healthy and pooled dead-plane, plus the truncated/starved negatives — *artefact:* holo3/tests/test_h3_drift_format.py:703-822
- (holo3) pooled close: volume 7 closes ONLY with pooled-fountain algebra AND three pooled captures (single capture: shortfall 125) — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:605 (cites holo3/conversion_docs/14-acceptance.md:255-256)

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's.

**Notes.**

*Reader:* The gate is exactly NECESSARY, never sufficient: per-block rank can never exceed the per-block distinct-symbol count, so a solve refused by the gate could not have succeeded. That is what makes close-10's forced final solve a cost row rather than a yield row. Both trees keep the batch function as an oracle only; the symmetry is exact.

*Refuter (reclassified):* *Corrections:* `implementation_delta: null` is not defensible; it must state two things. (1) THE DISJUNCTION IS NOT THE SAME: holo2's `ready = count_ready or metadata.terminal` where `terminal` is `inconsistent OR (decoded and k_total is None)` (holo2/src/holo2/solve/close.py:243-246, :352-355) — an inconsistent system is a READY state that licenses a close attempt. holo3's `terminal` is only `result is not None and not result.ok` (holo3/format/close.py:354-356), because an inconsistency RAISES first (holo3/format/close.py:319-321 in observe, :341-344 in settle), so the inconsistent member of the disjunct is unreachable. The states over which the gate is evaluated therefore differ; the disposition itself is close-12's row, but the gate row may not claim bit-exactness. (2) the counts key is per stream on holo2 and a single "pooled" bucket on holo3 (holo3/format/close.py:386-389, :417-421). ALSO CORRECT THE EVIDENCE STATUS: the pin named (holo3/tests/test_h3_close_state.py:78-96) compares holo3's incremental state to HOLO3's own batch function `close_count_status`; no holo2-vs-holo3 count-gate pin exists anywhere, and no holo3 test imports holo2's or v1's close (checked: holo3/tests/test_h3_drift_format.py importorskips only holo.core.* / holo.format.*; test_h3_drift_receiver.py importorskips holo.receive.* but never fountain_close).

*Reason:* A row whose `ready` predicate has a different reachable domain on the two sides is not CARRIED-IDENTICAL with a null delta.

*Second lens (final: CARRIED-DIFFERENT):* The refuter's reclassification is correct and I confirm it in the code. holo2's readiness is count_ready OR metadata.terminal where terminal returns True on inconsistent at any count (holo2/src/holo2/solve/close.py:352 and :244); holo3's terminal is only 'a decoded result that is not ok' (holo3/format/close.py:355), because an inconsistency raises first, both at observe (close.py:319-321) and at settle (close.py:341-344). The disjunction is written the same way but is evaluated over a strictly smaller set of reachable states, so implementation_delta: null is not defensible; the counts key is also per stream on holo2 and a single pooled bucket on holo3 (close.py:386-389, :417-421). The evidence-status correction is also right: holo3/tests/test_h3_close_state.py:78-96 compares holo3's incremental state to holo3's own batch function, and no holo3 test imports any v1 or holo2 close (grep for fountain_close under holo3/tests returns nothing). On yield: the gate is exactly necessary - per-block rank can never exceed per-block distinct symbols - so a refused solve could not have succeeded; it decides only whether the expensive solve runs on this look. The one member of the disjunction that differs (inconsistent) has never fired on the archived corpus, so the delta itself is unobservable there.

---

### close-05 — P3-1 incremental metadata eliminator — the GF(2) echelon basis that turns K-discovery into O(new certificates)

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B56

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** When K becomes known and trusted, hence when the count gate can even be evaluated; and it is the one place a certified metadata contradiction is detected.

**holo2.** An augmented 25-bit integer echelon basis (bit 24 is the right-hand side, lowest set bit is the pivot), maintained one equation per new counter at <=24 integer XORs. Interpretation is never re-implemented: `settle()` calls the carried `decode_metadata` EXACTLY ONCE at the trust transition (rank 24 and >=48 distinct equations) and caches the verdict, because a full-rank system has one solution and no later equation can revise K. A duplicate counter with a disagreeing bit, or a redundant equation reducing to a nonzero right-hand side, sets `inconsistent`; `terminal` then reports that `close_volume` owes a durable answer.

*Where:* `holo2/src/holo2/solve/close.py:160-247`; `holo2/src/holo2/solve/close.py:189-210`; `holo2/src/holo2/solve/close.py:211-224`; `holo2/src/holo2/solve/close.py:226-246` · *dial:* live

**holo3.** Byte-for-byte the same algebra — same augmented 25-bit rows, same lowest-set-bit pivot, same one-call-to-decode_metadata-at-the-trust-transition, same rank-24/48-distinct floors, same rank cross-check against the carried elimination. Two differences: the coefficient row is read from `metadata.coefficient_table(max_index)` so the gate is constructed with the row's equation-index space (pooled rows use `equation_index`, not the bare counter), and a contradiction RAISES `data.IntegrityError` at the fold instead of setting a flag.

*Where:* `holo3/format/close.py:296-356`; `holo3/format/close.py:315-337`; `holo3/format/close.py:339-352`; `holo3/format/close.py:354-356`

*Scheduler row / doc:* CLOSE-PORT-SPEC.md:26-40 ("incremental GF(2) metadata eliminator ... contradiction TERMINAL AT FOLD (IntegrityError)"); 05-fountain.md §2.4

**Implementation delta.** Algebra, constants and the single-authority rule are identical. Two implementation deltas: (1) INDEX SPACE — holo3's gate is parameterised by `max_index` and observes `equation_index(counter, stream_idx, n)` for pooled rows, so it works for the colour families holo2's gate never reaches (holo2 observes the bare counter and its `max_index` defaults to MAX_COUNTER). (2) CONTRADICTION DISPOSITION — holo2 sets `inconsistent`, lets `terminal` become true, and lets the next `close_volume` write a durable integrity_failure; holo3 raises immediately (see close-12). holo2 also validates the counter range inside `coefficient_mask`; holo3 indexes the table directly (a dropped validation wall, 05-fountain.md:272-277).

**Evidence status.** PINNED

**Evidence.**

- (holo3) metadata rank and n_unique equal the batch elimination at every prefix, all three families; K known at rank 24 but not trusted until 48 distinct equations; malformed and unsupported words go terminal only at the trust floor — *artefact:* holo3/tests/test_h3_close_state.py:78-96, :118-131, :150-184
- (holo2) trust floor: rank 24 = unique word; 48 distinct equations = the false-accept floor, >=24 surplus parity checks, residual <= ~2^-24 — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:601 (cites holo2/src/holo2/solve/close.py:57-60)
- (holo2) post-P3-1 re-measurement on the real sheet: 1,358 consults = 0.74 s = 0.1% of wall (was 34.1 s = 6.0%, -46x); exactly two close_volume runs, n=1356 open 102 ms and n=1357 verified 132 ms — *artefact:* NO ARTEFACT in ARTEFACTS.md — the number lives at holo2/src/holo2/format/DESIGN.md:166 and supersedes the 34.1 s baseline ARTEFACTS.md:600 quotes

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — the algebra is identical and pinned prefix-by-prefix against the batch oracle; the pooled index space is a strict generalisation.

**Notes.**

*Reader:* ARTEFACTS.md:600 quotes the PRE-P3-1 cost (34.1 s / 6.0% of wall) from the close.py docstring, which is itself the baseline P3-1 removed. The post-build re-measurement (0.74 s, 0.1% of wall, -46x, same driver and sheet) is at holo2/src/holo2/format/DESIGN.md:166 and is NOT in ARTEFACTS.md. holo3 has never had the consult measured on a real sheet either; `EngineStat.consult_cpu_s` exists (holo3/engine.py:295, ARTEFACTS.md:873) but no artefact quotes a value.

*Refuter (upheld):* *Corrections:* Algebra and both deltas verified line by line (holo2/src/holo2/solve/close.py:189-224 vs holo3/format/close.py:315-352: same augmented 25-bit rows, same lowest-set-bit pivot, same rank-24 / 48-distinct floors, same single decode_metadata call at the trust transition, same rank cross-check; holo3 parameterised by `max_index` and fed `equation_index` for pooled rows; contradiction raises instead of flagging). The dropped validation wall is real: holo2 validates through `coefficient_mask` -> `_counter(counter, max_index)` (holo2/src/holo2/format/metadata.py:173-176) while holo3 indexes `coefficient_table(max_index)[index]` directly (holo3/format/close.py:328-329) — note holo3's table is memoised (holo3/format/metadata.py:44-54), so this is a validation drop, not a cost regression. ONE NOTE MUST GO: 'holo3 has never had the consult measured on a real sheet either; EngineStat.consult_cpu_s exists but no artefact quotes a value' is FALSE. `scheduler.consult_cpu_s` is in every holo3 report.json in the archive: scratch/holo3-overnight-events/sheetH-maxstack-report.json = 0.881 s (of 121,967.7 CPU-s); scratch/sheetI-20260831/report-{first,resume,resume-2,resume-3}.json = 1.311 / 0.777 / 0.589 / 0.608 s; scratch/page-domain-qual/*/report.json = 0.279 / 0.192 / 0.333 s.

*Reason:* Deltas and cites exact; the 'holo3 consult cost is unmeasured' note is contradicted by eight inventoried run reports.

*Second lens (final: CARRIED-DIFFERENT):* Upheld, and the refuter's one correction is confirmed by direct reading of the archive. I checked the algebra line by line: same 25-bit augmented rows, same lowest-set-bit pivot, same single call to decode_metadata at the trust transition, same rank-24 and 48-distinct floors, same rank cross-check (holo2/src/holo2/solve/close.py:189-224 vs holo3/format/close.py:315-352). The two deltas stand: holo3 is parameterised by max_index and feeds equation_index for pooled rows, and a contradiction raises instead of setting a flag. The dropped validation wall is real - holo2 range-checks through _counter (holo2/src/holo2/format/metadata.py:160-176) while holo3 indexes coefficient_table(max_index)[index] straight (holo3/format/close.py:328) - but it is unreachable for any real row, since max_index is derived from the row's own stream count and the counter from its tile matrix; and an out-of-range index would raise IndexError, which holo3/cli.py:184-187 does not catch. The retracted note is the important part: 'no artefact quotes a holo3 consult cost' is FALSE. scheduler.consult_cpu_s is in every archived report - 0.881 s (sheet H max-stack), 1.311 / 0.777 / 0.589 / 0.608 s (sheet I chain), 0.279 / 0.192 / 0.333 s (the three e029 runs). Yield: the gate decides when K becomes trusted, hence when a solve can first be attempted; the delta is nil for K rows and a strict generalisation for colour.

---

### close-06 — P3-1 distinct-ESI shortfall counters — the monotone per-block have/needed state built once at metadata trust

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B56

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** The cost of every look at the close (O(new) vs O(all)), and it supplies the per-block have/needed the operator and the schedule read.

**holo2.** `_StreamCounts` holds `have[block]` and a monotone `short` counter initialised to `code.n_blocks`, decremented when a block first reaches K_b; count-readiness is one integer compare per stream. One `VolumeCode` is built per stream at the moment K becomes trusted, never per consult. The gate reads only `(counter, stream, metadata bit)` off the tile records — ZERO payload-symbol blob reads happen before a close attempt; `certified_symbols` materialises the symbol arrays only when `close_volume` is actually going to run. `_CloseState` is explicitly disposable: a fresh instance rebuilds from the tile map in one pass, which is what a resume pays.

*Where:* `holo2/src/holo2/solve/close.py:249-268`; `holo2/src/holo2/solve/close.py:279-343`; `holo2/src/holo2/solve/close.py:302-330`; `holo2/src/holo2/solve/close.py:122-137` · *dial:* live

**holo3.** Same shape: `_StreamCounts` with `have[]` and a monotone `short`, `VolumeCode` built once per counts-key at metadata trust, counters bumped per fold, `count_ready` one compare per key. The state is a long-lived engine field (`_close_progress`) built on first consult, not rebuilt per look. Keys are per stream for K and unpooled multi-stream rows and a single `"pooled"` bucket over `esi = equation_index(counter, stream_idx, n)` for pooled rows.

*Where:* `holo3/format/close.py:359-370`; `holo3/format/close.py:380-444`; `holo3/format/close.py:396-424`; `holo3/engine.py:592-596`; `holo3/engine.py:602-605`

*Scheduler row / doc:* CLOSE-PORT-SPEC.md:24-40 ("a derived monotone close-state cell under the accessor doctrine — NOT holo2's disposable per-consult _CloseState"); 05-fountain.md §6

**Implementation delta.** Four deltas, all benign for K and all needed for colour. (1) KEYING: holo2 keys counters by stream and maps ESI = counter; holo3 keys by stream for unpooled rows and by a single `"pooled"` bucket with ESI = counter*n + stream_idx for pooled ones — a strict generalisation holo2 cannot reach (its colour rows refuse fatally at the codec long before a close composes). (2) SHORTFALL INIT: holo2 starts `short = code.n_blocks`; holo3 starts `short = sum(1 for k_block in code.k_per_block if k_block > 0)`. Inert in practice — `VolumeCode` splits K into ceil(K/16384) blocks with base = K // n_blocks >= 1, so no block is ever empty — but holo2's form would never become count-ready if one ever were. (3) SYMBOL SOURCE: holo2's certificates live as blobs in a store and are read only at a close attempt; holo3 holds `Certificate.user_bits` arrays in memory throughout, so 'zero blob reads before an attempt' is satisfied by there being no blob layer. (4) LIFETIME: holo2's state is disposable and rebuilt on resume; holo3's rides the run and a `--resume` replays the fact snapshot through the ordinary ingest path, which rebuilds it the same way on first consult.

**Evidence status.** PINNED

**Evidence.**

- (holo3) the incremental counters equal `close_count_progress` (have/needed per block, per stream) at every prefix for k, cmy8 and pooled, and a fresh state fed a prefix equals a grown state at that prefix — *artefact:* holo3/tests/test_h3_close_state.py:78-116, :194-205
- (holo2) the same equivalence is pinned at every prefix by holo2/tests/solve/test_close_state.py — *artefact:* holo2/src/holo2/format/DESIGN.md:166 (no ARTEFACTS.md row)

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's.

**Notes.**

*Reader:* Both sides pay an O(all-certificates) skip-scan per consult inside `absorb` (`if key in self._processed: continue`), not O(new) — holo2 measured that residual as 0.2 ms at n<=400 growing to 0.8 ms at n>900 (holo2/src/holo2/format/DESIGN.md:166) and attributed it to the index rebuild, not the close. holo3's `absorb(self._certificates)` has the identical shape. No holo3 artefact quotes a consult cost.

*Refuter (upheld):* *Corrections:* All four deltas verified. (2) SHORTFALL INIT checks out and so does the 'inert in practice' argument: holo3/format/fountain.py:26-27,100-103 give n_blocks = ceil(K/16384) and base = K // n_blocks, so base >= 1 for every K >= 1 and no block is ever empty. (3) and (4) verified (holo3 holds Certificate.user_bits in memory; --resume folds facts through the ordinary _ingest at holo3/engine.py:248-249,251-266). The O(all) skip-scan is present on both sides as stated. SAME CORRECTION AS close-05: 'No holo3 artefact quotes a consult cost' is false — see the eight report.json values listed under close-05. That also converts this row's cost story from asserted to measured.

*Reason:* Deltas correct; the closing cost note is refuted by existing artefacts.

*Second lens (final: CARRIED-DIFFERENT):* Upheld with the same cost correction. I verified all four deltas. The shortfall initialisation difference is genuinely inert: holo3's block split gives n_blocks = ceil(K/16384) and base = K // n_blocks, so base is at least 1 for any K of at least 1 and no block is ever empty (holo3/format/fountain.py:24-25, :100-103) - holo3's 'count only non-empty blocks' form and holo2's 'count all blocks' form agree everywhere reachable, and holo3's is the safer of the two. Symbol source and lifetime check out (holo3 holds user_bits in memory; --resume folds the snapshot through the ordinary ingest at holo3/engine.py:248-249 and :251-266, rebuilding the state on first consult). The skip-scan is O(all certificates) per consult on both sides (holo3/format/close.py:396-401). The refuter's correction lands: this row's cost story is no longer asserted, it is measured - the same eight report.json values, all under 1.4 s of consult CPU for an entire run. Yield: cost only; the counters compute identical readiness on both trees for every reachable state.

---

### close-07 — `close_is_new` — the exact re-close gate (a solved block never unsolves)

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B57

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Whether a repeat full close attempt could answer differently; pure cost avoidance, exact rather than heuristic.

**holo2.** After every `close_volume` run the state freezes an `_Attempt` (the set of solved (stream, block) pairs, the per-block have counts, and whether metadata was terminal). A later ready consult re-runs only if metadata has since turned terminal, or some block the last attempt could not solve has gained a distinct symbol. Adding GF(2) equations never lowers rank, so this is exact, not heuristic. A skipped consult still publishes the counting report with reason `no_new_answer`.

*Where:* `holo2/src/holo2/solve/close.py:357-381`; `holo2/src/holo2/solve/close.py:383-398`; `holo2/src/holo2/solve/close.py:270-277`; `holo2/src/holo2/solve/close.py:488-499` · *dial:* live

**holo3.** Identical predicate over an identical `_Attempt` record, keyed by the same counts-key convention as close-06 (pooled rows fall back to `"pooled"` when a block row carries no stream id). `record_attempt` is called on every attempt, and the engine's `solve` condition ANDs `close_is_new()` in every non-final consult.

*Where:* `holo3/format/close.py:373-377`; `holo3/format/close.py:482-497`; `holo3/format/close.py:499-509`; `holo3/engine.py:598-606`

*Scheduler row / doc:* CLOSE-PORT-SPEC.md:34-37 ("close_is_new = the cell's change predicate")

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) an open solve is not re-attempted without a new answer — close_volume is called exactly twice over five consults ([1, N_NEEDED]) with statuses (open, count_ready, count_ready, count_ready, open); and the gate re-arms on the metadata-terminal transition — *artefact:* holo3/tests/test_h3_engine_contract.py:854-862; holo3/tests/test_h3_close_state.py:207-240

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's.

**Notes.**

*Reader:* holo3 loses one honesty detail holo2 built deliberately: holo2's counting report says WHY a ready state was not decided (`deferred` under observe, `no_new_answer` under a gated close-mode re-attempt, solve/close.py:494-498); holo3's CloseCheck reports `count_ready` in both cases. Diag-only, but it is a real reporting regression if anyone reads the status string to tell the two apart.

*Refuter (upheld):* *Corrections:* The predicate is byte-for-byte the same logic (holo2/src/holo2/solve/close.py:357-381 vs holo3/format/close.py:482-497) and `record_attempt` matches (holo2 :383-398, holo3 :499-509). Two additions the row owes. (a) `implementation_delta` should not be null: the attempt key falls back to "pooled" on holo3 for pooled rows and to `spec.stream_ids[0]` on holo2 — identical for every row holo2 can run, a generalisation for the rows it cannot. (b) The evidence is holo3-INTERNAL: test_h3_engine_contract.py:854-862 and test_h3_close_state.py:207-240 pin holo3 against holo3's expectations; there is no cross-tree pin for close_is_new on either side. The lost `deferred` / `no_new_answer` reason distinction is correctly noted (holo2 solve/close.py:494-498 vs holo3 engine.py:628-631).

*Reason:* Same predicate at HEAD, but the row overstates the pin and hides the pooled-key generalisation.

---

### close-08 — `--complete` — defer the DECISION to the end while keeping the observation live

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B55

Classification trail: reader CARRIED-IDENTICAL → refuter upheld → second lens CARRIED-IDENTICAL.

**What it decides.** Whether the first solvable fountain state stops the run; directly, how many tiles get certified.

**holo2.** Stated as a stop condition, not a consult schedule: a solvable fountain state no longer stops the session, so the run continues until no worker can contribute on any recipe entry and then closes once. Mid-run consults run in `observe` mode, so K, the metadata rank and every block's have/needed stay live on the status view while the decision waits. The single deferred close runs at exhaustion in `final` mode, skipping the count gate.

*Where:* `holo2/src/holo2/engine/orchestrator.py:815-825`; `holo2/src/holo2/engine/orchestrator.py:877-889`; `holo2/src/holo2/cli.py:177-180`; `holo2/src/holo2/engine/DESIGN.md:236-253` · *dial:* live

**holo3.** `solve = ... (final if complete else ...)`: under `--complete` no mid-run consult ever solves, but every mid-run consult still absorbs, counts and emits a CloseCheck labelled `deferred`. When the frontier reaches fixed point (queue empty and nothing in flight) the loop exits and one `_close_consult(final=True)` runs the full close, skipping both the count gate and `close_is_new`.

*Where:* `holo3/engine.py:598-601`; `holo3/engine.py:205-208`; `holo3/engine.py:628-629`; `holo3/cli.py:35`

*Scheduler row / doc:* SCHEDULE.md:9-12 ("count_ready consult mid-run, exhaustion under --complete"); 05-fountain.md:188-189

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) golden `--complete` close statuses = four `deferred` mid-run consults then the deciding one, result verified — *artefact:* holo3/tests/test_h3_engine_contract.py:86-87, :796-802
- (holo2) `--complete` on the real sheets: xerox 1,882 certificates / 12,263 commits / 96.0% done coverage / 719 s; e029 1,911 / 11,513 / 97.5% / 1,127 s — against K-stops of 1,356 and 1,357 — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:594-595
- (holo3) sheet I run 1 (3x2400, --workers 12, --plane-fields --complete) ended `count_ready` at 5,543; the four-run resume chain reached 5,880/5,883 with the close VERIFIED byte-exact three times — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:235; experiments/034 headline at ARTEFACTS.md:225

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's.

**Notes.**

*Reader:* This is the flag that buys the certificate surplus preemption spends: holo2's own numbers are +526 (xerox) and +554 (e029) tiles for +75% and +122% wall. holo3's deepest read on record was driven this way. The 2026-08-13 ruling that the observation must survive the deferral is honoured on both sides.

*Refuter (upheld):* *Corrections:* The decision semantics are identical and verified: holo2's exhaustion consult under --complete is CONSULT_FINAL, which skips both the count gate and close_is_new (orchestrator.py:885-889 -> solve/close.py:485-499); holo3's `final=True` skips the count-growth compare, `ready` and `close_is_new` (engine.py:589-601). EVIDENCE MUST BE FIXED, same defect as close-01: 'sheet I run 1 (3x2400, --workers 12, --plane-fields --complete) ended count_ready at 5,543' is wrong — run 1 was --no-close (experiments/034:30; MEASUREMENTS-2026-08-31.md:24), and the row's OWN golden refutes it: a --complete run emits `deferred`, never `count_ready` (holo3/tests/test_h3_engine_contract.py:86-87 vs :88; holo3/engine.py:628-631). The correct holo3 --complete evidence is chain runs 2-4 (scratch/sheetI-20260831/argv-resume{,-2,-3}), all VERIFIED, plus the fact that EVERY archived holo3 real-capture parity decode ran --complete (holo3/conversion_docs/overnight/final-manifest.json: c2-cmy8, sheetH-mixed, e029-postfix, xerox-k-postfix). Optional: note that the OBSERVATION cadence still differs (per commit vs per merge batch, inherited from close-01) even though no decision does.

*Reason:* Semantics identical; the sheet-I evidence attributes a --no-close run to --complete and is contradicted by the row's own golden.

*Second lens (final: CARRIED-IDENTICAL):* The refuter upholds the semantics and refutes the evidence; I confirm both. The decision path is the same on each side: holo2's exhaustion consult under --complete runs in final mode, which skips the readiness gate and the new-answer gate (orchestrator.py:886-888 into solve/close.py:485-499); holo3's final=True does the same three bypasses in one expression (holo3/engine.py:598-601). The evidence defect is the same one as close-01 and the row's own golden settles it: a --complete run labels every mid-run consult deferred (holo3/engine.py:629, pinned at holo3/tests/test_h3_engine_contract.py:86-87), and sheet-I run 1's report carries count_ready with counting true (scratch/sheetI-20260831/report-first.json), which only --no-close produces. The correct --complete evidence is the sheet-I resume chain runs 2-4 (argv-resume, -2, -3) and the whole archived parity set, whose manifest shows --complete on every real-capture decode (holo3/conversion_docs/overnight/final-manifest.json). Yield: this is the flag that buys back what preemption spends - holo3 e029 1,357 default versus 1,940 under --complete, holo2 +526 and +554 on its two sheets - and the delta between trees is nil, apart from the observation cadence already priced in close-01.

---

### close-09 — `--no-close` — never enter a deciding consult; accumulate certificates and end OPEN

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B55

Classification trail: reader CARRIED-DIFFERENT → refuter upheld → second lens CARRIED-DIFFERENT.

**What it decides.** That the run never stops on a close, so every scheduled tile is attempted; and that no closing record is read, attempted or written.

**holo2.** Every consult, mid-run and at exhaustion, is `observe`: counting and the metadata rank stay live, nothing is decided and nothing is written, and the session ends OPEN with its certificates accumulated. The help text says outright that the flag forfeits close preemption. Because holo2's close is a DURABLE record, the CLI warns on stderr before the run that an existing terminal close is being skipped and becomes SUPERSEDED as soon as this run commits; the epilogue replaces the fountain-shortfall claim with an accumulation line, since an observe consult over a ready volume would otherwise print `deferred` — a wait that does not exist under this flag. `--no-close` never suppresses an integrity failure.

*Where:* `holo2/src/holo2/engine/orchestrator.py:117-129`; `holo2/src/holo2/engine/orchestrator.py:827-838`; `holo2/src/holo2/engine/orchestrator.py:886-888`; `holo2/src/holo2/cli.py:181-188`; `holo2/src/holo2/cli.py:594-599`; `holo2/src/holo2/cli.py:859-911` · *dial:* live

**holo3.** `solve` is False on every consult including the final one; absorb and `count_progress` still run, so the CloseCheck carries counts, metadata rank and per-block have/needed with `blocks_counting=True` and status `count_ready`/`open`. The run ends `status="open"`, payload None, exit code 2, with the snapshot and diag products written as usual. There is no durable close record anywhere in holo3, so there is nothing to skip, supersede or warn about.

*Where:* `holo3/engine.py:598`; `holo3/engine.py:614-637`; `holo3/cli.py:36`; `holo3/diag/readout.py:294-318`

*Scheduler row / doc:* 05-fountain.md:190-192 ("--no-close: never enter the close layer; report certificate counts + the count-only block reach, exit non-verified")

**Implementation delta.** The decision suppression and the surviving observation are identical. What differs is everything that hangs off holo2's DURABLE close: no pre-run 'your existing close is being superseded' warning, no epilogue distinction between an observed shortfall and a claimed one, and no notion of the session being left OPEN as a stored state. holo3's honesty requirement is met structurally instead — counting rows carry have/needed with `rank=None` by ruling, so the status line reads 'count_ready · all blocks count-ready', a count claim rather than a fountain-rank claim. holo2 also treats `--no-close` as implying `--complete`'s deferral through one shared `_deferred` property; in holo3 the two flags are independent booleans that happen to compose the same way, except that `--complete --no-close` labels the CloseCheck `count_ready` where holo2 labels it `deferred`.

**Evidence status.** PINNED

**Evidence.**

- (holo3) golden `--no-close` close statuses ("open","open","open","count_ready","count_ready"); result status open, payload None, certified == N_NEEDED — *artefact:* holo3/tests/test_h3_engine_contract.py:88, :805-812
- (holo3) the 2026-08-31 arms-wave sheet-I run was driven `--no-close` and reached 5,543 certificates — best on record at that moment — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:234
- (holo3) sheet H seven-capture max-stack, close OPEN, 4,237/5,277 certificates — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:251

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's — the yield-bearing half (never stop on a close, keep the observation) is carried exactly; the missing half is the operator surface of a durable-close model holo3 does not have (see close-13).

**Notes.**

*Reader:* holo2's 05-fountain-era note that "holo1's detach-to-open semantics are meaningless without resumable state" (05-fountain.md:191-192, and the DROP list at :267-271) is now stale of holo3's own tree: holo3 DOES have resumable state (`facts.npz` + `--resume`, holo3/engine.py:248-249, :653). What it does not have is a durable close record, which is close-13's row.

*Refuter (upheld):* *Corrections:* Both sides verified, including holo2's stderr supersede warning (cli.py:594-599), the epilogue's accumulation line replacing the fountain claim (cli.py:905-911 with the rationale at :862-882), and holo3's open/exit-2 path (engine.py:598, cli.py:204-206) and 'count_ready · all blocks count-ready' status line (diag/readout.py:302-305). The 5,543 --no-close attribution here is the CORRECT reading of the same run close-08 mislabels. ONE MISSING DIVERGENCE: holo3's --no-close does not fully 'never enter the close layer' in holo2's sense. holo3/store.py:905-916 enforces the metadata equation at INGEST and raises data.IntegrityError on opposite bits at one equation index, so a contradicted sheet ABORTS a --no-close holo3 run (exit 1, no products), where holo2's --no-close observe consult sets `inconsistent`, publishes it in the counting report (solve/close.py:429-431) and ends OPEN. close-12 covers the disposition in general but not this flag interaction, and holo2's help text 'no closing record is read, attempted or written' has no holo3 analogue precisely because the check moved upstream.

*Reason:* Correct and well-cited; add the ingest-gate interaction that makes holo3's --no-close abortable where holo2's is not.

*Second lens (final: CARRIED-DIFFERENT):* Upheld, and the refuter's added divergence is real and material. I verified holo3's --no-close never solves (the leading clause of holo3/engine.py:598) while still absorbing and counting, and ending open at exit 2 (holo3/cli.py:204-206). But holo3 carries a metadata contradiction check one whole layer upstream of the close: holo3/store.py:903 and :914 raise on conflicting certificates at one address and on opposite metadata bits at one equation index, at ingest, before any consult. So holo2's help-text promise that --no-close 'never enters the close layer' has no holo3 analogue: on a contradicted sheet a holo3 --no-close run aborts with no products, where holo2's observe consult records the inconsistency in the counting report and ends open. That is the one place where the flag's own contract differs, and the row should carry it rather than leaving it entirely to close-12. Yield: the mechanism decides certificates in the strongest way (never stop, attempt everything - the 5,543 sheet-I run and the 4,237-certificate sheet-H run were both driven this way); the tree-to-tree delta is operator surface plus that abort exposure, and neither has ever been observed to bite on the archived corpus.

---

### close-10 — The default-mode exhaustion consult — holo3 forces one unconditional full close at the end of every non-verified run; holo2 does not

**DIVERGED** · evidence **MEASURED** · yield **nothing observable** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter reclassified to DIVERGED → second lens DIVERGED.

**What it decides.** Nothing about certificates; it decides whether one full GF(2) solve over every block is paid at the end of every open run.

**holo2.** In default mode the exhaustion consult uses selector `GATE_COUNT_READY` — the SAME key the mid-run consults used — so the frontier-version compare refuses it whenever no certificate landed after the last mid-run consult, which at exhaustion is the normal case. Even when it does run, the mode is `close`, so the count gate and `close_is_new` still apply. Net: a default open run pays zero extra `close_volume` calls at the end.

*Where:* `holo2/src/holo2/engine/orchestrator.py:877-898`; `holo2/src/holo2/engine/orchestrator.py:856-859`; `holo2/src/holo2/solve/close.py:488-499` · *dial:* live

**holo3.** After the loop, if nothing verified, `_close_consult(final=True)` runs. `final` bypasses the count-growth compare, bypasses `ready`, and bypasses `close_is_new`, so `close_volume` is called unconditionally whenever at least one certificate exists — including on runs whose blocks are nowhere near count-ready.

*Where:* `holo3/engine.py:205-208`; `holo3/engine.py:586-606`

*Scheduler row / doc:* 05-fountain.md §2.6 (which specifies `--complete` as the one deferred close but does not say the default mode also forces one)

**Implementation delta.** holo3 collapsed holo2's three exhaustion modes (`final` for --complete, `observe` for --no-close, `close` for default) into one `final=True` call plus flag guards, and in doing so gave the DEFAULT mode `--complete`'s count-gate bypass. Because count-readiness is exactly necessary for a solve (per-block rank <= per-block distinct symbols), the forced attempt can never change the outcome — it can only return the same `open` verdict the counts already implied. It is therefore a pure cost: one full decoder build plus a GE per block. 05-fountain.md:193-195 prices GE at the 16384-row knee at ~1 min/block, so on a large multi-block colour volume the tail cost is minutes; on the K sheets it is the ~100 ms holo2 measured for its own open attempt.

**Evidence status.** MEASURED — corrected in the merge: reader said UNPROVEN; refuter and second lens both correct it — `scheduler.consult_cpu_s` sits in every archived holo3 report.json.

**Evidence.**

- (holo2) exactly two close_volume runs on the real sheet — n=1356 open (102 ms) and n=1357 verified (132 ms) — both necessary — *artefact:* NO ARTEFACT in ARTEFACTS.md; holo2/src/holo2/format/DESIGN.md:166
- (holo3) GE at the 16384-row knee is ~1 min/block; every physically closed colour volume to date has k_meta well inside the one-solve regime (e032: k_meta~918) — *artefact:* holo3/conversion_docs/05-fountain.md:193-195 (design note, not a measurement; no ARTEFACTS.md row)

**Yield relevance.** nothing observable — source: second lens (reader said: decides-order-only).

**Recommendation.** keep holo3's, and record the reason. The forced final attempt cannot change an outcome (the count gate is necessary), so this is a cost, not a yield gap; and it buys one real thing holo2's skip does not — an open run always ends with a genuine per-block RANK report rather than a counts-only one, which is what the operator reads to decide whether to add a capture. If the tail cost ever shows up on a big colour volume, the cheap fix is to AND `ready` into the final solve as well (one clause in holo3/engine.py:598-601). What would settle the cost: the `consult_cpu_s` field already on EngineStat, read off any existing open colour run's events — no new decode needed; the sheet-H max-stack event stream (ARTEFACTS.md:252) and the sheet-I `--no-close` arms-wave run both carry EngineStat rows, though `--no-close` suppresses the solve so only a default-mode open run measures it.

**Notes.**

*Reader:* Found in the code; no seed row names it and 05-fountain.md §2.6 does not describe it. It is the one place where holo3's close semantics are strictly not holo2's.

*Refuter (reclassified):* *Corrections:* TWO CHANGES. (1) CLASSIFICATION: this is not 'same intent, different implementation'. holo2's default-mode exhaustion consult reuses selector GATE_COUNT_READY (orchestrator.py:886) so the frontier-version compare refuses it in the normal case, and even when it runs, mode `close` still applies the count gate and close_is_new (solve/close.py:488-499): a default open run pays ZERO extra close_volume calls. holo3 calls _close_consult(final=True) unconditionally (engine.py:205-208) and `final` bypasses the count-growth compare, `ready` AND close_is_new (engine.py:589,598-601) — pinned as deliberate by holo3/tests/test_h3_engine_contract.py:865-870 `test_the_final_consult_ignores_the_close_is_new_gate`, which the row does not cite. The exhaustion DECISION differs and the row asks for a ruling; that is DIVERGED. (2) EVIDENCE: UNPROVEN -> MEASURED, and the cost objection dissolves. `EngineStat.consult_cpu_s` (holo3/engine.py:295, :580-584) is in every archived holo3 report.json. The largest colour volume on record — sheet-H seven-capture max-stack, 4,237 certificates, 121,967.7 CPU-s, close OPEN with `counting: false`, i.e. a real close_volume solve DID run — spent 0.881 CPU-s on every consult of the run INCLUDING that solve (scratch/holo3-overnight-events/sheetH-maxstack-report.json -> scheduler.consult_cpu_s). Sheet I: 1.311 / 0.777 / 0.589 / 0.608 s. e029 default-mode: 0.279 / 0.192 / 0.333 s. The 05-fountain.md:193-195 '~1 min/block at the 16384-row knee' fear is not realised at any k_meta in the record. Also correct the 'what would settle it' text: it says only a default-mode open run measures the forced solve — wrong, --complete's final consult is the SAME code path, and sheet H measures it. Recommendation stands (keep holo3's) but is now settled by measurement, and the proposed remedy (AND `ready` into the final solve) should be recorded as unnecessary rather than as a standing option.

*Reason:* The exhaustion decision genuinely differs and needs a ruling; and the cost it was flagged for is measured at under a second on the largest volume in the record.

*Second lens (final: DIVERGED):* The refuter is right twice and I confirm both in code and in the archive. On classification: holo2's default-mode exhaustion consult reuses the same gate key as the mid-run looks (orchestrator.py:886, GATE_EXHAUSTION only when deferred), so the frontier-version compare refuses it in the ordinary case, and even when it runs the mode is close, which still applies readiness and the new-answer gate (solve/close.py:488-499) - a default open run pays zero extra solves. holo3's final=True bypasses the growth compare, readiness AND the new-answer gate in one expression (holo3/engine.py:598-601), pinned deliberately by holo3/tests/test_h3_engine_contract.py:865. That is a genuinely different exhaustion decision and the row asks for a ruling, so DIVERGED is correct. On evidence: UNPROVEN to MEASURED is right and the archive is decisive - scratch/holo3-overnight-events/sheetH-maxstack-report.json shows close status open with counting false, meaning the forced solve DID run on the largest colour volume in the record (4,237 certificates, 121,967.7 CPU-s), and the run's entire consult budget was 0.881 CPU-seconds. The '~1 min per block at the 16384-row knee' fear is not realised anywhere in the record. Yield: none - the readiness gate is exactly necessary, so the forced attempt can only return the verdict the counts already implied; the only observable is tail cost and a richer final report.

---

### close-11 — `close_volume` — the carried decode: metadata to K, per-block fountain solve, stream reassembly, and the three unwrap gates

**CARRIED-DIFFERENT** · evidence **PINNED for the recovered payload bytes and the named refusal statuses; UNPROVEN for the result object and its diagnostics** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT → second lens CARRIED-DIFFERENT.

**What it decides.** The only recoverability truth in the system: whether these certificates are the payload. It is what a certificate is FOR.

**holo2.** A copy-and-adapt carry of `src/holo/receive/fountain_close.py`, exact math, with the holo2 firewall forbidding the import. Three branches — pooled (one code, ESI = counter*n + idx), single-stream, and unpooled multi-stream — then the envelope/canonical-K/zero-padding gates, total or nothing. Two doctrines are stated as load-bearing: THE STOP IS THE SHA NEVER A COUNT, and ALL ACCOUNTING PER BLOCK. Disagreeing certified equations are integrity-fatal, never voted. The pooled branches are carried verbatim and unexercised, because holo2 refuses colour rows fatally at the codec before a close can compose.

*Where:* `holo2/src/holo2/format/fountain_close.py:630-859`; `holo2/src/holo2/format/fountain_close.py:1-56`; `holo2/src/holo2/format/fountain_close.py:226-320`; `holo2/src/holo2/format/fountain_close.py:407-449` · *dial:* live (K only; the pooled/colour branches are built-unused)

**holo3.** The same three branches, the same ESI conventions, the same `_unwrap_gates` triple (SHA envelope, canonical minimal K, zero padding through the exact bit capacity), the same per-block reporting and the same fatal treatment of conflicting equations. Rewritten lean: the CloseSpec/CertifiedStreamSymbol validation walls, the counter-consistency check (holo3 derives the counter and never stores one), the three-way exception taxonomy and the D16 surplus audit are gone; `RowLike`/`CertificateLike` protocols replace the spec objects.

*Where:* `holo3/format/close.py:533-631`; `holo3/format/close.py:125-138`; `holo3/format/close.py:109-122`; `holo3/format/close.py:175-210`

*Scheduler row / doc:* 05-fountain.md §2.5 (steps 15-20) and §3 copy-vs-rewrite table (`close_volume` branch structure + unwrap gates from fountain_close.py:630-859); §4 the invariants that must survive

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED for the recovered payload bytes and the named refusal statuses; UNPROVEN for the result object and its diagnostics — corrected in the merge: refuter: the only close-vs-close oracle in the repo is holo2's (tests/holo2_oracles/test_oracle_close.py); holo3's close is pinned against v1 EMISSION, never against another close.

**Evidence.**

- (holo3) holo3's close recovers v1-EMITTED volumes byte-exact across K, colour single-stream, cmy8-v0 three-stream, pooled healthy and pooled DEAD-PLANE, and reproduces every named refusal (truncated, starved, corrupted, duplicate, conflicting, noncanonical K, nonzero padding, unsupported version) — *artefact:* holo3/tests/test_h3_drift_format.py:703-892 (43 tests; ARTEFACTS.md:781)
- (holo2) holo2's close == v1's close, byte-exact recovered payload, identical open/shortfall shape, identical refusals, over generator-truth fixtures read back by the real v1 tile decode — *artefact:* tests/holo2_oracles/test_oracle_close.py:1-21 and its 20 test functions (no ARTEFACTS.md row; ARTEFACTS.md:773-791 covers the drift-test family)
- (holo3) "Every close that ran stayed byte-exact. Five of five completed volumes recovered their payload sha exactly. The changes moved WHICH tiles certify; they never broke payload reconstruction" — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:604 (cites holo3/conversion_docs/PARITY.md:441)
- (holo1) the stop is the SHA, never a count; a stream that solves but fails its digest is a failed volume, never a partial one — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:589 (cites src/holo/receive/fountain_close.py:5-11)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's.

**Notes.**

*Reader:* There is NO direct holo2-vs-holo3 pin for the close: holo2 is pinned to v1 (tests/holo2_oracles/test_oracle_close.py) and holo3 is pinned to v1 (test_h3_drift_format.py), with v1 as the pivot. Both legs are `pytest.importorskip`, so after the deletions the holo3 leg SILENTLY SKIPS rather than fails — ARTEFACTS.md:786-791 and gap G-02 at :803. The holo3 leg is the one Phase 4 must convert into a frozen record, per plan §2.3/§10 step 4.3.

*Refuter (reclassified):* *Corrections:* THREE CHANGES. (1) `implementation_delta: null` contradicts the row's own holo3.behaviour field, which lists the removals. Move them into the delta and add two the row misses: `metadata_from_certificates` changed RETURN SHAPE (holo2 returns (version, k_total, diagnostics dict), fountain_close.py:226-230; holo3 returns (version, k_total, state string), close.py:175-210), and CloseResult gained `metadata_version` while losing holo2's per-block `rank_shortfall` (holo2 solve/close.py:150-153 reads it; holo3/data.py:494-501 has no such field). (2) THE PIN CLAIM IS WRONG IN KIND. tests/holo2_oracles/test_oracle_close.py IS a close-vs-close oracle: it imports holo.receive.fountain_close (:38) and runs both closes side by side (:323-400). holo3 has NO such test: test_h3_drift_format.py importorskips only holo.core.* and holo.format.* (:18-32) and never imports any close implementation; `grep -rn 'receive.fountain_close' holo3/tests` is empty. holo3's close is pinned against v1 EMISSION (generator truth, byte-exact recovery) plus its own refusal assertions — never against another close. The transitive holo2<->holo3 equivalence therefore holds for verified payload bytes and the named refusal statuses, NOT for the result object or its diagnostics. (3) COUNTS: '(43 tests)' is test_h3_drift_format.py's file total; only 6 test functions lie in :703-892. And test_oracle_close.py has 22 test functions, not 20.

*Reason:* The row's own text lists four removals and a protocol swap; and the only close-vs-close oracle in the repo is holo2's, not holo3's.

*Second lens (final: CARRIED-DIFFERENT):* The refuter's reclassification is correct on all three points and I reproduced each. The result protocol differs: holo2's metadata_from_certificates returns (version, k_total, diagnostics dict) at holo2/src/holo2/format/fountain_close.py:224-230, holo3's returns (version, k_total, state string) at holo3/format/close.py:175-210; holo3's result object gained metadata_version (holo3/format/close.py:47) and dropped holo2's per-block rank shortfall (holo3/data.py:494-501 has have/needed/rank/solved, so the shortfall is derivable but no longer published). The pin claim is wrong in kind, and this is the finding that matters: tests/holo2_oracles/test_oracle_close.py imports v1's own close at line 38 and runs the two closes side by side, 22 test functions; holo3 has NO close-to-close comparison anywhere - grep for fountain_close under holo3/tests returns nothing, and test_h3_drift_format.py imports only v1's core and format modules (:18-32). holo3's close is pinned against v1 EMISSION plus its own refusal assertions, which is a weaker guarantee. The count is also wrong: 7 test functions lie in the cited range, not 43. Yield: on the archived corpus nothing observable - five of five completed volumes recovered byte-exact - but the pin asymmetry is the family's real gap, compounded by both legs being skip-if-missing imports (ARTEFACTS.md:803).

---

### close-12 — What happens when the close finds an integrity failure — a durable terminal record versus an aborting exception

**DIVERGED** · evidence **UNPROVEN** · yield **nothing observable** · ruling needed **Y** · seeds: B55, B56

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a run that discovers contradicting certificates or a failed envelope keeps its work and its diagnostics, and whether the lineage is frozen against reruns.

**holo2.** A metadata contradiction sets `_MetadataGate.inconsistent`, which makes the state `terminal`, so the next consult runs `close_volume` and gets `integrity_failure`; the verdict's `Write(CLOSE_KEY, ...)` commits an ordinary durable `CloseRecord`, which freezes the session by itself, and the run returns a terminal outcome with an epilogue. A certificate conflict raised by the tile map mid-run is caught in `_run` and converted the same way by `_integrity_failure`. Every rerun of that state directory reports the same status; nothing is resumable.

*Where:* `holo2/src/holo2/engine/orchestrator.py:864-875`; `holo2/src/holo2/engine/orchestrator.py:900-922`; `holo2/src/holo2/solve/close.py:505-514`; `holo2/src/holo2/solve/close.py:226-246`; `holo2/src/holo2/engine/DESIGN.md:227-229` · *dial:* live

**holo3.** Contradictions are caught one layer EARLIER than holo2's: `_fold_certificate` refuses two different certificates at one address and opposite metadata bits at one equation index, raising `data.IntegrityError` at ingest; `_MetadataGate.observe`/`settle` raise the same at the close fold. A close result of `integrity_failure` is re-raised by `_close_decide`. Every one of those escapes `run()` uncaught, so `_finish` never runs: the CLI prints `holo3: integrity error: ...` and exits 1, and the run dir gets no events.jsonl, no report.json, no facts.npz.

*Where:* `holo3/engine.py:609-611`; `holo3/format/close.py:315-337`; `holo3/format/close.py:339-352`; `holo3/store.py:893-920`; `holo3/cli.py:184-186`

*Scheduler row / doc:* CLOSE-PORT-SPEC.md:26-29 ("contradiction TERMINAL AT FOLD (IntegrityError), replacing d427dce's swallow-into-no-rows"); 05-fountain.md:267-271 (resume/journal DROP list)

**Implementation delta.** holo2 makes an integrity failure a DELIVERED, durable, terminal fact: the record is committed through the ordinary write path, the diag surface is published in a `finally`, the epilogue explains, and the session is permanently frozen (a rerun cannot re-attempt). holo3 makes it an ABORT: the exception unwinds out of the engine before `_finish`, so the run's entire certificate harvest, its event log and its resumable snapshot are lost, and there is no operator surface beyond one stderr line. The two sides err in opposite directions — holo2 over-freezes (a SHA mismatch permanently condemns a lineage that more captures might have fixed), holo3 under-preserves (a contradiction discovered after hours of colour decoding throws that work away). holo3 does catch contradictions earlier, at the certificate fold, which limits the exposure window but does not change the disposition.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) an opposite duplicate is terminal at fold; a contradiction after rank 24 is terminal, not a revised K — *artefact:* holo3/tests/test_h3_close_state.py:134-161
- (holo1) the e028 verified-close trap: a retained VERIFIED close stores only SHA/length, so `CloseExecution(verified, payload=None)` trips the verified-payload invariant — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:591 (cites src/holo/receive/production_close.py:68-72)
- (holo2) no artefact records an integrity failure on any real volume, on any receiver — the corpus has five verified closes and two opens — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:590 (holo1 corpus); ARTEFACTS.md:604 (holo3: every close that ran stayed byte-exact)

**Yield relevance.** nothing observable — source: second lens (reader said: integrity).

**Recommendation.** port a narrow half now, and only that half: write the run-dir products (events.jsonl, report.json, facts.npz) BEFORE the exception escapes, so an integrity abort on an eight-hour colour run leaves a resumable snapshot and a diagnosable event log. Do NOT port holo2's durable terminal record or the session freeze — freezing a lineage on a SHA mismatch is the more dangerous half, and holo3's resume model (a fact snapshot, no policy state) makes re-deriving the close from the certificate set free. Cost: a `try/except data.IntegrityError` around the loop in `holo3/engine.py:184-211` that calls `_finish(None)` and re-raises, plus a test. No decode needed. Evidence that would inform it either way does not exist — no integrity failure has ever been observed on paper on any receiver.

**Notes.**

*Reader:* Note the doctrine asymmetry worth putting to Germano: holo1/holo2 treat 'the envelope SHA did not match' as TERMINAL for the lineage. On holo3 the same event is transient. Neither disposition has ever been exercised on a real sheet.

*Refuter (upheld):* *Corrections:* Both dispositions verified exactly: holo2's durable path (solve/close.py:505-514 -> Write(CLOSE_KEY, close_record_from_result(...)), orchestrator.py:900-922 for the CertificateConflict half, :924-948 for the frozen rerun) and holo3's abort path (store.py:902-915 at fold, format/close.py:319-321/341-344 at the close fold, engine.py:609-611 re-raising integrity_failure, cli.py:184-186 printing and exiting 1). TWO REFINEMENTS. (a) 'the run dir gets no events.jsonl, no report.json, no facts.npz' is right, but _start already wrote `argv` and `tree` into it (engine.py:214-224), so the abort is not traceless. (b) The recommendation should temper 'leaves a resumable snapshot'. A fold-time raise leaves a CONSISTENT set (the offending certificate was never folded), so _finish(None) there really would be resumable. But `_MetadataGate.settle`'s inconsistency (a redundant equation reducing to a nonzero RHS, close.py:341-344) is NOT caught by the store gate, so a snapshot written on that path holds the contradicting set and a --resume re-raises at its first consult: diagnosable, not continuable. Say 'diagnosable snapshot + event log' and name the two cases.

*Reason:* Correctly classified and cited; two precision fixes to the disposition description and the port recommendation.

*Second lens (final: DIVERGED):* Upheld, and both refinements are correct. I confirmed holo2's durable path (solve/close.py:505-514 committing a closing record through the ordinary write path, orchestrator.py:900-922 for the conflict half) and holo3's abort path (store.py:903 and :914 at ingest, format/close.py:319-321 and :341-344 at the close fold, engine.py:610 re-raising, cli.py:184-186 printing and exiting 1). Refinement (a) is right: engine.py:215 and :223 already wrote argv and the tree description, so the abort is not traceless - but the snapshot, the event log and the report are all written by _finish (engine.py:653), which the exception skips entirely. Refinement (b) is right and important: a raise from the ingest fold leaves a consistent certificate set, because the offending certificate was never folded, so a snapshot written there would resume cleanly; a raise from settle (a redundant equation reducing to a nonzero right-hand side, format/close.py:341-344) leaves the contradicting set in place, so a snapshot written there is diagnosable but not continuable. The recommendation must name both cases rather than promise resumability. Yield: nothing observable on the archived corpus - no integrity failure has ever been recorded on any receiver, and every close that ran was byte-exact - but the exposure if it ever fires is the total loss of a run's certificates, which would be the largest single yield event in the family.

---

### close-13 — The durable close record, the terminal-session freeze, and the close-detach property

**ABSENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** On a resume: whether a run re-derives the close or reads a stored answer, and whether an already-closed state may keep certifying.

**holo2.** A verifying close stages the payload as a blob and writes a `CloseRecord` carrying its ref; a terminal record freezes the session, and a later run reads the status off the STORE and re-reads the payload through the blob path with ref verification, reporting `resumed_terminal`. `--no-close` is the documented escape: it does not read the record and supersedes it on the first commit of the new run.

*Where:* `holo2/src/holo2/solve/close.py:503-514`; `holo2/src/holo2/engine/orchestrator.py:924-948`; `holo2/src/holo2/format/fountain_close.py:862-897`; `holo2/src/holo2/cli.py:585-599` · *dial:* live

**holo3.** Absent by design. holo3 persists FACTS (`facts.npz` at RunDone) and nothing else; a `--resume` folds them back through `_ingest` and the close is recomputed from scratch on the first consult. A verified run writes the payload to `--out` and the snapshot; a resumed run over the same facts recomputes the same close.

*Where:* `holo3/engine.py:639-662`; `holo3/engine.py:248-249`; `holo3/engine.py:251-266`

*Scheduler row / doc:* 05-fountain.md:267-271 (explicit DROP: "Resume/journal/replay: close_record_from_result, CloseRecord/BlobRef/DurableCloseStatus, certificate_frontier_sha256, terminal-record immutability"); SCHEDULE.md:382-385 (holo3's resume is one fact snapshot folded back through ordinary ingest)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo1) close detach is lossless — a close is a pure derivation from the certificate set and a later closing run recomputes it byte-exactly — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:592 (cites src/holo/receive/session.py:662)
- (holo3) the sheet-I four-run resume chain re-derived the close on every closing run: VERIFIED 2445b95db5b49bf3, 1,798,761 B, three times, over 5,543 -> 5,866 -> 5,866 -> 5,880 certificates — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:235 and :225
- (holo1) the e028 verified-close trap — the failure mode a retained close record creates — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:591

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** accept the loss — and note it is a gain, not a loss, for yield. Because the close is a pure derivation from the certificate set (holo1's own finding, ARTEFACTS.md:592), a stored close record buys nothing but the freeze, and the freeze is what `--no-close` existed to escape. holo3's resume chain proves the derivation on the deepest read on record. The one thing the record bought that holo3 has not replaced is the operator warning that an existing terminal answer is being set aside — meaningless without a stored answer.

**Notes.**

*Reader:* Mostly out-of-filter (journal/replay), included because the freeze does change whether a state may keep certifying. holo3's snapshot IS a durable resume surface, so 05-fountain.md:191-192's aside that detach semantics are "meaningless without resumable state" is stale of the tree that shipped.

*Refuter (upheld):* *Corrections:* No change. Verified: holo2's durable record and blob path (solve/close.py:503-514, format/fountain_close.py:862-895, orchestrator.py:924-948, cli.py:585-599) and holo3's facts-only persistence (engine.py:248-249, :251-266, :639-662; the explicit DROP list at holo3/conversion_docs/05-fountain.md:267-271). The 'stale aside' observation is right: 05-fountain.md:191-192 does say detach-to-open is 'meaningless without resumable state', and holo3 shipped facts.npz + --resume.

*Reason:* Absence confirmed in code and in the drop list; the resume evidence reproduces.

---

### close-14 — Colour reach of the close — pooled and multi-stream closes actually composing

**HOLO3-ONLY** · evidence **n/a** · yield **decides-certificates** · ruling needed **N** · seeds: B56

Classification trail: reader HOLO3-ONLY → refuter upheld.

**What it decides.** Whether any colour volume can be closed at all.

**holo2.** The pooled and multi-stream branches of `close_volume` are carried verbatim and stay UNEXERCISED: since the 2026-08-22 catch-up holo2 BUILDS pooled rows and every v2 cmy8 identity sets `pooled_fountain`, but `registry_rows.tile_format_for` refuses a colour row FATALLY long before a close composes. The incremental `_CloseState` is keyed per stream by bare counter and has no pooled ESI path at all, so it could not serve a pooled row even if one reached it.

*Where:* `holo2/src/holo2/format/fountain_close.py:28-36`; `holo2/src/holo2/format/fountain_close.py:663-700`; `holo2/src/holo2/solve/close.py:291-343` · *dial:* built-unused (colour); live (K)

**holo3.** All three branches are live and exercised on paper. The incremental state carries the pooled ESI convention through `metadata.equation_index` and a single `"pooled"` counts bucket, so the count gate, the shortfall counters and `close_is_new` all work for pooled rows.

*Where:* `holo3/format/close.py:553-619`; `holo3/format/close.py:380-444`; `holo3/format/close.py:146-172`

*Scheduler row / doc:* 05-fountain.md §2.5 step 16 and §4 ("Pooled verified-stop preempts the per-stream floor"; "Dead-plane close: a pooled volume must close byte-exact with ZERO certificates from one stream")

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo2) holo2 has no colour number of any kind, by construction — no wall, no certificate count, no yield for cmy7 or cmy8 on any sheet — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:824 (gap G-17)
- (holo3) pooled close: volume 7 closes ONLY with pooled-fountain algebra AND three pooled captures (single capture: shortfall 125) — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:605
- (holo3) sheet I VERIFIED byte-exact three times at 1,798,761 B; c2-cmy8 718,413 B and c3-cmy7 301,600 B in the holo1-corpus roster — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:235, :590

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** no action.

**Notes.**

*Reader:* Listed so the map does not read holo2's verbatim-but-dead pooled branches as parity. The generalisations in close-05 and close-06 exist for this row.

*Refuter (upheld):* *Corrections:* No change. holo2's fatal colour door is where the row says it is and says so itself: holo2/src/holo2/format/registry_rows.py:419-439 refuses any non-K family before the coding check, with the docstring at :426-436 naming it 'the fatal colour door'. holo3's three live branches at holo3/format/close.py:553-619 and the pooled counts bucket at :386-389 verified.

*Reason:* HOLO3-ONLY is correct; holo2's pooled branches are provably unreachable.

---

### close-15 — D16 surplus audit — re-encoding every certified symbol of every solved block to name disagreeing certificates

**ABSENT** · evidence **MEASURED** · yield **integrity** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Nothing about the run; it names, after a solve, which certificates a dependent row would have contradicted.

**holo2.** After a solve, `_surplus_audit` re-encodes each solved block's certified symbols from the solved source rows and reports which certificates disagree — the wrong-symbol cases the GF(2) solve masks in a dependent row. Explicitly PURE OBSERVATION: no solver state changes, no outcome authority, and any exception inside it returns an empty tuple so a defect can never convert a decodable volume into an error.

*Where:* `holo2/src/holo2/format/fountain_close.py:590-627`; `holo2/src/holo2/format/fountain_close.py:128-154`; `holo2/src/holo2/format/fountain_close.py:685, 698-699` · *dial:* live (report-only)

**holo3.** absent

*Where:* _(no path given)_

*Scheduler row / doc:* 05-fountain.md:281-283 (DROP: "D16 surplus audit (audit_solved_symbols, _surplus_audit, CloseSurplusInconsistency) — advisory-only, never outcome-changing (open Q1 offers it back as an optional diag)")

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo3) zero wrong certificates anywhere in the crop batteries and the yask ablation ladder; sheet I 5,880/5,883 with zero wrong — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:225, :259
- (holo1) zero wrong certificates in 69,066,304 audited cells across the colour-uplift campaign — *artefact:* CLAUDE.md colour-uplift bullet; the audit surface itself at ARTEFACTS.md:402 (crop batteries carry a wrong-certificate audit)

**Yield relevance.** integrity — source: reader.

**Recommendation.** accept the loss. By its own contract it can never change an outcome, and the wrong-certificate question is now answered by an independent instrument (the crop batteries' wrong-certificate audit, ARTEFACTS.md:402) against ground truth rather than against the solve. Nothing in the record has ever needed it: no wrong certificate has been found on any receiver.

**Notes.**

*Reader:* Included as a mechanism the seed rows do not name. Arguably out-of-filter (a safeguard with zero outcome authority); recorded as ABSENT so the drop is on the record rather than silent.

*Refuter (upheld):* *Corrections:* Verified absent: holo2/src/holo2/format/fountain_close.py:590-627 (_surplus_audit, with the zero-outcome-change catch at :623-626), :127-149 (CloseSurplusInconsistency) and the two call sites at :685 and :698-699; holo3 has no `audit_solved_symbols`, no `_surplus_audit` and no surplus type anywhere (grep over holo3/format and holo3/*.py is empty), and 05-fountain.md:281-283 is the explicit DROP. ONE ADDITION: holo2's re-close gate leans on the audit in prose — solve/close.py:362-364 argues a skipped consult is safe because 'the surplus audit of any skipped symbol still happens at the eventual deciding close'. Dropping D16 removes that supporting argument for close-07's gate (the gate remains exact on rank grounds; only the surplus-evidence rider goes).

*Reason:* Drop confirmed on both sides; add the close_is_new rider the drop also removes.

---

### close-16 — The close's report channel — the counting report and the CloseCheck event

**OUT-OF-FILTER** · evidence **n/a** · yield **integrity** · ruling needed **N** · seeds: B55, B56

Classification trail: reader OUT-OF-FILTER → refuter upheld.

**What it decides.** Nothing about work or certificates; it is what the operator and the diag panes read.

**holo2.** Plain JSON carried untouched into `RunOutcome.close` and the diag snapshot; the engine never sees a format object. `counting_report` publishes status/reason/K/metadata rank/unique/per-block have+needed/certified, with `metadata_inconsistent` present only when true, and the consult overrides `reason` for the two ready-but-undecided cases.

*Where:* `holo2/src/holo2/solve/close.py:140-157`; `holo2/src/holo2/solve/close.py:402-446`; `holo2/src/holo2/engine/consult.py:142-151` · *dial:* live

**holo3.** One frozen `CloseCheck` fact per consult carrying certified, symbols_used, k_total, metadata_rank, metadata_n_unique, blocks, status and `blocks_counting`. Counting rows carry have/needed with `rank=None`; solve rows carry the real rank.

*Where:* `holo3/data.py:495-513`; `holo3/engine.py:614-637`; `holo3/diag/readout.py:294-318`

*Scheduler row / doc:* CLOSE-PORT-SPEC.md:42-56 (the diag seam: CloseCheck stays the close channel; `blocks_fresh` deleted; `CloseBlockRow.rank -> int | None`; lazy rank is a standing ruling; metadata rank/n_unique ride CloseCheck, never the gauge)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.** _(no artefact cited)_

**Yield relevance.** integrity — source: reader.

**Recommendation.** no action

**Notes.**

*Reader:* Diag rendering. The one substantive carry is the lazy-rank ruling: counting rows never fabricate rank=0, which fixed a real dishonesty in the durable report (CLOSE-PORT-SPEC.md:48-50). The lost `deferred`/`no_new_answer` reason distinction is noted under close-07.

*Refuter (upheld):* *Corrections:* No change. holo3/data.py:494-513 and diag/readout.py:294-318 verified; CLOSE-PORT-SPEC.md:42-56 carries the diag seam including `blocks_fresh` deleted and `CloseBlockRow.rank -> int | None` exactly as quoted.

*Reason:* Correctly filtered out; the lazy-rank carry is real.

---

## The dryness gate

8 rows; 6 carry a ruling.

**Reader's family notes.** Read at main 29d9a8d (two commits past the brief's b8471fc: 104494e splits the diag fold from its readout, 29d9a8d rebuilds the venv - neither touches the engine loop, any price literal or any placement module, so every citation here is also valid at b8471fc). No receiver was run. THE HEADLINE FOR THE MERGE: the dryness gate is not the interesting divergence in this family. It is a DEFERRAL on both sides - it can move a fire later but never remove one - so it is provably inert on every run that drains to exhaustion, which is every run in the archived record except the three e029 closes; and on those three, nothing in the price band a gate would hold ever fired at all (the dearest place job on any arm was word_centre at 60). The measured head-to-head is on the same side: holo2 WITH the gate fired its first cold at 44%/36% of its placement stream, holo3 WITHOUT it at 53%/44%. What actually changed between the trees, and what the ruling should be about, is dryness-04 (cold moved from BELOW refinement to ABOVE every certificate-minting rescue row - reasoned, right on every number we have, and never once exercised, because only the three e029 arms have run on the new ladder and none reached cost 120) and dryness-07 (holo3's cold_rest now sweeps a whole page domain instead of one page: measured at 9,640 cpu-s and ZERO poses on the only fragment run in the record, half that run's entire CPU - a cost that neither the gate nor the reprice would have removed, because that run used --complete). Three numbers in this map are my own tabulations of event streams that ARTEFACTS.md inventories but does not break down (the per-stage place fires in the three page-domain-qual arms and in the two sheet-J runs); everything else cites ARTEFACTS.md or a tracked design doc, and where a figure has no artefact I have said so in the row.

**Refuter, convention:** upheld = row survives, corrections at most cosmetic. reclassified = the classification word must change. rejected = a claim that drives the row's delta or its ruling is wrong and must be rewritten before it goes to Germano; the classification word may still stand.

**Refuter, read_at:** main 29d9a8d, working tree clean except untracked claude-plan.md / confetti3.py / grok-plan.txt / holo3/retirement_docs-2026-09/ / holo4/

**Refuter's family notes.** MECHANISMS NO ROW COVERS. (1) THE FREE FIRST FIRE. fields.py:804-806 and color_pooled.py:188-190 price by `COST * attempts` with no attempts=0 guard, and the engine passes attempts=0 on the first push (engine.py:306; incremented only at fire, :470). So two rows the generated ladder advertises at 180*n and 170*n actually enter the heap at cost 0 on their first fire - cheaper than survey (10) and payload (20), i.e. first in the whole tree. Measured, not inferred: scratch/J-run.54028/events.jsonl carries `JobDone plugin=fields cost=0` (twice, plus 2 and 4 for the rung term) before any 180. Every other escalating row guards it (`* attempts if attempts else COST`: swim.py:547, plane_k.py:672, uplift.py:328/330) and color_region.py:731-732 guards it differently and deliberately (`fits = max(1, ...)`, with a docstring saying a lane that never fitted still pays a full first re-fit). The fields test only exercises attempts 1/2/3 (tests/test_h3_plane_fields.py:614-621), and SCHEDULE.md's generated ladder cannot show the n=0 case. Either a bug or an undocumented deliberate free entry; either way it belongs in this family, because it is the one place where a dear row jumps the whole price order. (2) THE PRICE OF A COLD FIRE IS INDEPENDENT OF THE SIZE OF ITS SWEEP (place.py:85-89 vs place_sched.py:186-190), so the one row on the ladder whose CPU scales with the page domain is the one row whose price does not - measured 13.9 s per rest fire against 1.13 s per live fire on the same J run, at prices 10 apart. That decoupling, not the missing gate, is what makes a large domain expensive. (3) HOLO3'S REAL REPLACEMENT FOR THE GATE IS THE FIRE-TIME FLOOR, and no row says so: engine.py:449-451 retire, :452-454 tried_version, :456-460 eligible/stage all DELETE or skip work at admission rather than deferring it - strictly stronger than a hold, and the reason the family's 'a deferral cannot remove work' premise is false. (4) WIDE IS GATED IN HOLO2 AND FREE IN PRACTICE: on J-run.54028 the wide band (costs 120-129) fired 851 times for 12.2 cpu-s and zero poses (1,327 fires / 4.7 s / 0 poses on J-run.52093), i.e. 14 ms a fire. If any part of the gate is ever ported, gating wide costs ordering for nothing measurable. (5) A SECOND STALE IN-TREE SPEC: the reader's notes name only holo2/docs/DESIGN.md:265; holo3/conversion_docs/wave2-reports.md:67 item (5) still states 'wide + both colds are GATED behind global dryness' with no supersession marker, and the residue report cites it as spec alongside 13-engine-diag-cli.md (which WAS annotated at :126 and :298-299). (6) HOLO2'S GATE HAS NEVER RUN IN A CONFIGURATION WHERE IT COULD FIRE. Every holo2/holo3 head-to-head in the record is --workers 1, and orchestrator.py:39/:221-222 puts --workers 1 on the serial path where nothing is ever in flight at _next() time. So the family has zero observations of the gate's only operative clause, on either tree - worth saying plainly in RULINGS.md, since it is the honest reason the ruling has to be made on design grounds rather than on numbers.

**Second lens (yield) family notes.** Second lens = yield. Read at main 29d9a8d (same tree as the refuter). No receiver was run; I re-tabulated four archived event streams read-only (scratch/J-run.54028, scratch/J-run.52093, and all three scratch/page-domain-qual arms) and every figure both earlier lenses relied on reproduced exactly: wide sweep 696 fires / 9,640.2 cpu-s / 0 poses / 49.5% of the fragment run, narrow 855 / 967.1 / 39 poses (1.13 s vs 13.85 s a fire); zero fires at or above cost 120 on all three whole-sheet arms, dearest 60; repeated payload decodes flat at 20/22/24 (2,231 fires); the swim's first two fires both at base (711 at 240-244, 185 at 480-484); and the plane-field row entering at cost 0 twice, once for an 8.4-second fit. THE FAMILY'S GOVERNING YIELD FACT, which neither earlier lens states and which changes how three rows must be written: in holo3 the order of firing DOES decide certificates, because a page-correlation pass is one-shot per window per flavour and both the pages it sweeps and the support it demands are computed at fire time from the live page set of that instant (holo3/plugins/place_sched.py:186-189 into holo3/plugins/place.py:753-757; the spent flags at holo3/store.py:596-600 are never cleared). holo3/docs/PAGE-DOMAIN.md:175-182 accepts this explicitly - certificate sets may differ across worker counts - so 'it only defers, therefore it is inert' is not available as an argument anywhere in this family. What IS safe, and is the right reason to keep holo3's no-hold behaviour, is that the work admission deletes is by construction work that can mint nothing (holo3/plugins/place_sched.py:229-252 with holo3/store.py:449-458). Two costings in the reader's recommendations are wrong and I corrected them in the entries: the proposed fragment re-run is about ONE wall-hour at six workers, not 5.4 (19,471 cpu-s over six workers; the two archived runs took 34 and 56 minutes by their own file timestamps), and the 'free' memory measurement does not exist because scratch/J-run.54028/report.json carries no peak-RSS field. Classification changes from the reader: dryness-05 to DIVERGED (siding with the refuter - repeated payload decodes are aged in holo2 and flat in holo3 - but reversing its implicature, since holo2's own aging measurement is certified 160 to 160 unchanged, i.e. cost only). One defect deserves fixing regardless of any ruling: the plane-field and pooled-colour rows have no guard on their first fire and therefore enter the heap ahead of every cheap row.


### dryness-01 — The dryness gate: an admission hold that stops expensive work from starting while cheaper work is still running

**ABSENT** · evidence **n/a** · yield **decides-certificates, but only on fragment material and only through placement floors; nothing observable on any archived whole-sheet K run** · ruling needed **Y** · seeds: B02

Classification trail: reader ABSENT → refuter REJECTED an argument (classification word stands) → second lens ABSENT.

> **Refuter verdict: REJECTED.** A claim that drives this row's delta or its ruling is wrong and must be rewritten before it goes to Germano. The corrections are under Notes; read the reader's text below only through them.

**What it decides.** Whether an idle worker may start an expensive placement pass now, or must leave its slot empty until the cheap work already in progress finishes.

**holo2.** holo2 has two books of work (a descriptor queue and the placement source) and admits whichever head is cheaper. A job the source marks 'gated' is then held back if anything cheaper is ready or in flight anywhere, including a running payload decode, because a certificate deletes placement work outright. Read carefully, the 'ready' half is already guaranteed by the head comparison two lines above (a cheaper ready job would have been admitted instead), so the gate's only operative content is the IN-FLIGHT clause: it refuses to start dear work while a cheaper fire is still running. When the gate holds, the fill loop breaks and the worker slot stays empty until something completes; the serial path re-enumerates and re-asks, so the hold is instantaneous rather than final and cannot deadlock.

*Where:* `holo2/src/holo2/engine/orchestrator.py:372-395`; `holo2/src/holo2/engine/orchestrator.py:398-417`; `holo2/src/holo2/engine/orchestrator.py:269-287`; `holo2/src/holo2/engine/orchestrator.py:149`; `holo2/src/holo2/engine/orchestrator.py:479`; `holo2/src/holo2/core/work.py:374-398`; `holo2/src/holo2/engine/DESIGN.md:150-161` · *dial:* live

**holo3.** absent. holo3's fill loop pops the cheapest ready job off one global heap and submits it, with no comparison against what is in flight and no hold of any kind. A gate WAS built on the page-domain branch at 9b15b48 (2026-09-01 22:42) as engine.dryness_holds(cost, inflight_costs) - hold any job costing 120 or more while a cheaper job is in flight, re-seat it and break out of the fill loop - and was DELETED 34 minutes later at d399ba3 (2026-09-01 23:16) together with its test, with cold repriced 140/150 to 250/260. Nothing in the current tree holds any job back; 'cold last' is a price, not a rule.

*Where:* `holo3/engine.py:433-475`

*Scheduler row / doc:* SCHEDULE.md:379-389 ('the admission gate (a v2 artefact, deleted by ruling - pure cost order)'); docs/PAGE-DOMAIN.md:153-164 (section 6)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo2) NO yield or cost number exists. The gate is described only as mechanism ... no instrumentation — *artefact:* holo3/retirement_docs-2026-09/ARTEFACTS.md:744 (section 2.10)
- (holo3) holo2's dryness gate saves nothing on a run that drains. Both runs go to full exhaustion, and a gate that only defers cannot remove work. Measured: holo2's first cold fire sits at 44%/36% of its placement stream, holo3's at 53%/44% — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:41-45 and :555-565, inventoried at ARTEFACTS.md:746
- (holo3) e029 whole sheet, verified 465,580 B: 157 cold_live fires, 206 s, 42.4% of placement CPU, 0 poses. sheet-H max-stack: 5,163 fires, 6,452 s, 65.4% of placement CPU, 0 poses. xerox-k: 12 fires, 19 s, 0 poses. On all three whole-sheet runs the correlation tier committed zero poses - 5,332 fires between them — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:409-425, inventoried at ARTEFACTS.md:251 and :746
- (holo3) three e029 arms on the merged tree (workers 8, close preempts): the dearest place fire on any arm is word_centre at cost 60. Zero fires at cost 120 or above on any arm - no wide, no cold_live, no cold_rest. All three VERIFIED e5021f8d..., 465,580 B — *artefact:* my own tabulation of scratch/page-domain-qual/{base-e029-run.64152,merged-null-run.64562,merged-default-run.64831}/events.jsonl, inventoried at ARTEFACTS.md:104

**Yield relevance.** decides-certificates, but only on fragment material and only through placement floors; nothing observable on any archived whole-sheet K run — source: second lens (reader said: decides-order-only).

**Recommendation.** Keep holo3's (no gate), and record the reason rather than the absence. The gate is a DEFERRAL: it can never remove a fire, only move it later, so on any run that drains to exhaustion - which is every --complete run and every run in the archived record except the three e029 closes - it changes nothing at all. It pays only where a verified close preempts the run before the dear band is reached; and on the one preempting workload in the record (e029, three arms, eight workers) nothing in the dear band ever ran, so there was nothing to defer. The counter-argument on the table (that the gate should be ported per holo3's own spec at conversion_docs/13-engine-diag-cli.md, which the tree contradicted for weeks) has already been answered in the tree: that spec clause was superseded at :126 and :298-299 and the contract at 00-contract.md:319 now states 'No dryness gate' explicitly. If Germano wants the in-flight clause back anyway, it is about ten lines and one test, and it is yield-safe by construction (a deferral cannot suppress a certificate on a run that drains) - but it should be priced against the one thing it cannot fix, which is DRY-07.

**Notes.**

*Reader:* The specs that demanded the gate are now marked superseded in-tree (13-engine-diag-cli.md:126, :298-299; 00-contract.md:319), so the 'spec divergence' the 2026-08-31 residue report recorded at its section 1c is closed on paper. One stale citation survives: holo2/docs/DESIGN.md:265 still calls cold 'gated on quiescence', which is wrong twice over - the quiescent gate was deleted and replaced by the dryness gate (ARTEFACTS.md:745). I could not find any instrumentation on either side that counts how often the gate actually held a job.

*Refuter (rejected):* *Corrections:* ABSENT is the right word and every citation and number in the row resolves exactly (verified: holo3/engine.py:433-475 has no hold of any kind; the gate existed only between 9b15b48 (2026-09-01 22:42, +DRYNESS_COST=120, +dryness_holds(), re-seat+break in _fill, +test_dryness_holds_the_expensive_band_behind_cheaper_inflight) and d399ba3 (23:16, gate and test deleted, cold 140/150 -> 250/260); holo2/src/holo2/engine/orchestrator.py:387-395 reads as described and the 'ready' half is indeed inert because line 385 already returned on a cheaper queue head and line 383 took the source's own cheapest job). TWO things must be rewritten. (1) THE CENTRAL ARGUMENT IS FALSE AS STATED: 'a gate is a DEFERRAL: it can never remove a fire, only move it later, so on any run that drains to exhaustion it changes nothing at all'. Both trees delete work AT FIRE TIME: holo3/engine.py:449-451 retires a popped worker before it fires (place_retire_cause -> window_fully_done), :452-454 skips it on the tried_version floor, :456-460 on eligible/stage. So deferring a dear fire behind a cheap one CAN remove it outright when the cheap fire's certificate retires the subject - which is exactly the gate's own stated rationale in holo2 (core/work.py:388-392, 'a gated job is admissible only when nothing cheaper is ready OR in flight'; orchestrator.py:379-381, 'an expensive placement pass must not begin while a payload fire that could delete its window is still running'). The honest statement is: the gate's value on a draining run is UNMEASURED, not zero. (2) THE HEADLINE HEAD-TO-HEAD DOES NOT SAY WHAT THE ROW SAYS IT SAYS. 'holo2 WITH the gate fired its first cold at 44%/36%, holo3 WITHOUT it at 53%/44%' was measured at --workers 1, and at --workers 1 holo2's gate is PROVABLY INERT: orchestrator.py:39 and :221-222 ('--workers 1 builds no pool and stays' serial), so at every _next() call in _pop_armed nothing is in flight, in_play holds only the queue head, and the queue head was already proved dearer than job.cost two lines above - min(in_play) < job.cost can never be true. The residue report itself says the milder version ('at one worker can hold at most one job', v2v3-placement-residue.md:565). So the number is real and it is NOT evidence that holo3's ladder reproduces the gate's ordering. Also add the residue report's own countervailing sentence, which the row omits: v2v3-placement-residue.md:566-570 says the gate 'is still worth having, for two other reasons: multi-worker runs, where the in-flight clause bites; and runs that close early'. The row's answer to the second (the three e029 arms, verified by me: scratch/page-domain-qual/*/events.jsonl have ZERO JobDone at cost>=120 on all three arms, dearest place fire cost 60) is sound; the first is simply unmeasured on both sides.

*Reason:* Classification ABSENT stands and every figure checks out, but the 'provably inert' argument that carries the ruling is contradicted by both trees' fire-time retire gate, and the one measured comparison was taken in the configuration where holo2's gate cannot fire.

*Second lens (final: ABSENT):* Refuter right on the mechanism, reader right on the verdict, both wrong on the reason. The reader's load-bearing premise ('a deferral can never remove a fire') is false: holo3/engine.py:449-451 retires a popped worker before it fires, :452-454 skips it on the evidence-version floor, :456-460 on eligibility and stage, and holo2 states that exact rationale at holo2/src/holo2/engine/orchestrator.py:379-381. But the refuter stops one step short: the work admission deletes is by construction work that can mint nothing - holo3/plugins/place_sched.py:229-252 retires a window only when it is already placed, exhausted, or fully done, and holo3/store.py:449-458 defines fully-done as 'can never mint anything again', monotone in the certificate frontier. So the deletion channel is yield-neutral and the verdict survives. The refuter's second correction is also right and is the one that matters for evidence: the 44%/36% vs 53%/44% head-to-head was taken at one worker, and at one worker holo2 takes the serial path (holo2/src/holo2/engine/orchestrator.py:221-222) where nothing is ever in flight at admission, so the min(in_play) < job.cost test at :390-394 can never be true - the number compares two price ladders, not gate against no-gate. NEITHER lens found the real certificate channel: a cold pass is one-shot per window per flavour (holo3/plugins/place.py:104-107 with holo3/store.py:596-600 setting the spent flags and never clearing them) and both the pages it sweeps and its support floor are fixed at FIRE time from the live/rest split of that instant (holo3/plugins/place_sched.py:186-189 into holo3/plugins/place.py:753-757). Delay that fire and it sweeps a different page set at a different floor. holo3/docs/PAGE-DOMAIN.md:175-182 says this outright - certificate sets may differ across worker counts because floors read fire-time live state - so 'a deferral changes nothing' is false twice over, and any ruling has to be made on design grounds because neither tree has ever observed the hold's only live clause.

---

### dryness-02 — Which work the gate holds back: three named passes versus a whole price band

**ABSENT** · evidence **n/a** · yield **decides-order-only** · ruling needed **Y** · seeds: B03

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** The reach of the hold - whether it applies only to the widened consult and the two page-correlation sweeps, or to every recovery pass above a price line.

**holo2.** The hold is DATA on the price table, not a threshold. Exactly three rows carry gated=True: wide_consult (120), cold_live (140) and cold_rest (150). The re-read pass (resample, 200) is deliberately not gated - place_tiers.py:189-197 argues that its price alone does the ordering, since it is the second half of a refinement that already waited behind everything. The scheduler copies the flag straight off the table onto every job it offers (place_sched.py:597), so the gate's reach is exactly whatever the table says and nothing else.

*Where:* `holo2/src/holo2/solve/place_tiers.py:153-177`; `holo2/src/holo2/solve/place_tiers.py:193-200`; `holo2/src/holo2/solve/place_sched.py:580-597`; `holo2/src/holo2/core/work.py:398` · *dial:* live

**holo3.** absent. While it existed (9b15b48 to d399ba3) holo3's version was a PRICE BAND, not a per-row flag: cost >= 120 held. On holo3's ladder that band is far wider than holo2's three rows - it covers wide (120), the colour lane refit (160), pooled colour context (170), plane fields (180), refine and refine.color and revisit (200), both supplemental colour arms (210/220), local context (220), plane-K (230), the swim (240) and both colds (140/150 at the time). So holo3's gate would have held nine recovery rows that holo2 never gated, including every certificate-minting rescue row. Today none of them is held.

*Where:* `holo3/engine.py:433-475`

*Scheduler row / doc:* the deleted engine.DRYNESS_COST = 120 (git show 9b15b48, git show d399ba3)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** n/a

**Evidence.**

- (holo3) tiles.local minted 213 certificates at 73% of the run's CPU on sheet I, machine 2; the four-run chain's later runs read 26 then 2, at about 3,000 cpu-s each — *artefact:* ARTEFACTS.md:703 and :735, citing holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:30-31 and experiments/034-sheet-i-full-readout.md:89-93
- (holo3) run 2 of the sheet-I resume chain added 323 certificates - tiles.planek 281, tiles.local 26, tiles.retry 10, tiles.swim 6 - and produced the first VERIFIED close; run 4 added 14 more (planek 9, local 2, swim 1, retry 1, union 1) — *artefact:* ARTEFACTS.md:235, scratch/sheetI-20260831/report-resume*.json
- (holo3) without tiles.local the K sim volume is LOST (45 certificates); with it, 48 certificates and the volume comes back byte-exact, a strict superset, zero wrong — *artefact:* ARTEFACTS.md:701, citing holo3/SCHEDULE.md:436-489

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** Keep holo3's (no gate). If the in-flight clause is ever ported per DRY-01, port holo2's SHAPE and not holo3's deleted one: a per-row boolean on the price declaration, set only on the two cold stages. A 120-price band would hold back the rows that actually mint holo3's late certificates - tiles.planek alone brought 281 of the 323 certificates that turned sheet I's first verified close, and tiles.local is the difference between a lost and a recovered sim volume. Holding those behind a cheap payload fire buys nothing and risks the endgame, which is precisely why holo2 kept its own re-read pass out of the gated set.

**Notes.**

*Reader:* holo2's three gated rows and holo3's nine-plus band were never compared on any run: holo3's gate lived 34 minutes and no decode was recorded on it. This row is a design-shape observation, not a measured one.

*Refuter (upheld):* *Corrections:* Verified: exactly three gated=True rows in holo2 (place_tiers.py:163 wide 120, :167 cold_live 140, :172 cold_rest 150), resample gated=False at :193-197, the flag copied straight onto the offered job at place_sched.py:597, and the deleted DRYNESS_COST=120 band (git show 9b15b48). All three evidence numbers resolve exactly (ARTEFACTS.md:701, :703, :235). Three corrections. (a) 'nine recovery rows' undercounts: by the current ladder (SCHEDULE.md:66-81) the >=120 band covers color.color_refit 160, color.pooled_ctx 170, fields 180, refine 200, refine.color 200, revisit 200, tiles.uplift 210/220, tiles.local 220, tiles.planek 230, tiles.swim 240 - ten plugin rows / eleven stages, plus wide and both colds. (b) TWO OF THEM WOULD NOT HAVE BEEN HELD ON THEIR FIRST FIRE: fields.py:804-806 (`FIELD_COST * attempts + RUNG_COST*subject[1]`) and color_pooled.py:188-190 (`POOLED_CTX_COST * attempts`) have no `if attempts else base` guard, and the engine passes attempts=0 on the first push (engine.py:306, incremented only at fire, :470), so their first fire prices at 0-4, below survey (10). Measured, not inferred: scratch/J-run.54028/events.jsonl contains JobDone plugin=fields cost=0 twice (and cost 2, 4), then 180/182/184, 360/362/364, ... (c) the argument that the re-read is deliberately ungated sits at place_tiers.py:178-192, not :189-197.

*Reason:* The shape claim (per-row flag vs price band) is correct and well-evidenced; only the row count and the two unguarded first fires need fixing.

---

### dryness-03 — One global cost order across every kind of work

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B01

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which job an idle worker picks up next, out of everything the receiver could do at that moment.

**holo2.** Two admission sources. Descriptors (payload, calibration, close) sit in a priced queue whose repetition is bounded by a durable spend row; placement lives in an in-memory source that keeps a ready flag per window and prices the ready ones itself. The orchestrator compares the two HEADS by cost and takes the cheaper, a tie going to the queue so the choice is a function of state and not of iteration order. Placement jobs take no identity in the ledger, so 'may this run again' is answered by the source's own ready bit and tried set rather than by the wall.

*Where:* `holo2/src/holo2/engine/orchestrator.py:372-395`; `holo2/src/holo2/engine/orchestrator.py:269-287`; `holo2/src/holo2/core/work.py:374-398`; `holo2/src/holo2/engine/DESIGN.md:99-111` · *dial:* live

**holo3.** One book. All seventeen descriptor rows, placement included, push onto a single min-heap keyed (cost, sequence), and the fill loop pops it until every worker slot is busy. Each row prices itself through a cost(store, subject, stage, attempts, last_cost) function; the engine holds no numbers at all. A worker whose price has changed since it was seated is re-pushed rather than run at the stale price (engine.py:461-467), and a stale seat is skipped. There is no second source, no ready flag protocol and no tie rule beyond the monotone sequence counter.

*Where:* `holo3/engine.py:298-327`; `holo3/engine.py:433-475`; `holo3/plugins/place_sched.py:259-262`

*Scheduler row / doc:* SCHEDULE.md:1-35 (the descriptor table and price ladder) and :375-389

**Implementation delta.** Same intent - one price order over everything, so cheap recovery always precedes dear search - realised with one heap instead of two books plus a head comparison. Consequences worth naming: (a) holo3's 'nothing cheaper is ready' is exact and global by construction, where holo2's is exact only because each book exposes its own cheapest head; (b) holo2's deliberate tie rule (equal price goes to the descriptor queue) becomes, in holo3, a first-come sequence number, so equal-priced rows are round-robin peers in arrival order, which SCHEDULE.md:22-23 states as deliberate; (c) holo2 must keep a separate in-flight cost map for the source (orchestrator.py:149,479) purely to feed the gate, and holo3 needs none because it has no gate; (d) holo3 re-prices a worker at fire time and re-pushes if the price went up, a check holo2 does not make because a descriptor's price is fixed at mint and wake time.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) holo3's plain price ladder already reproduces - in fact slightly improves on - holo2's gate ordering at --workers 1: holo2's first cold fire at 44%/36% of the placement stream, holo3's at 53%/44% — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:555-565, inventoried at ARTEFACTS.md:746
- (holo3) head-to-head on identical crops, two synthetic platen angles: certificates 100 vs 112 (straight) and 56 vs 82 (angled), holo2 first in each pair; at 0.80 deg holo3's certificate set is a strict superset of holo2's; zero disagreeing bit vectors on 99 and 56 shared addresses — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:27-37 and :494-553

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** Keep holo3's.

**Notes.**

*Reader:* The head-to-head was run at --workers 1 on both sides, which is the condition under which the two designs are expected to agree; no multi-worker head-to-head exists, and the report itself says so (section 8, 'honest gaps', :812).

*Refuter (upheld):* *Corrections:* One heap keyed (cost, seq) confirmed at engine.py:298-327 and :433-475; holo2's two-book head comparison at orchestrator.py:372-395 confirmed; SCHEDULE.md:22-23 does state same-price rows as deliberate round-robin peers. Correction to consequence (d): 'holo3 re-prices a worker at fire time and re-pushes if the price went up' misstates the mechanism. engine.py:461-466 compares descriptor.cost(FRESH stage) against descriptor.cost(SEATED stage) at the SAME instant with the same attempts and last_cost - so it can only trigger when the STAGE changed to a dearer one; a same-stage price that rose since seating is invisible to it and the job fires at its stale seat price. Re-seating on a price change happens at PUSH time instead (engine.py:305-313: recompute, `if cost == worker.seat_cost: return`, else re-seat at the new price). Second correction: the MEASURED evidence is fine for this row's own subject (one global order), but drop the phrasing that it 'reproduces holo2's gate ordering' - at --workers 1 holo2's gate cannot fire at all (see dryness-01), so the comparison exercises the price ladders, not the gate.

*Reason:* CARRIED-DIFFERENT and MEASURED both stand for the ordering claim; the fire-time re-price is a stage-freshness check, not a price-drift check.

---

### dryness-04 — Where the page-correlation search sits in the price order relative to refinement and the residue rescue rows

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: B02, B03

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Which recovery work has already run when a verified close cuts the run short - i.e. whether the last CPU before a close went into cold page searches or into the rows that actually mint late certificates.

**holo2.** cold_live is 140 and cold_rest 150, each plus 20 per rung of lane depth and 5 for a subdivided child; the re-read and the pose refinement both price at 200 flat plus 2 per rung. So on the coarsest lanes cold runs BEFORE refinement, and holo2's own comment (recipe.py:320-335) records the resulting inversion as an OPEN question for the user: refine at 200 is overtaken by cold_rest from rung 3 and by cold_live from rung 4, and making 'a revision fires only when nothing cheaper is ready' unconditional would want refine at 240, above the dearest cold pass at 235. holo2 has no residue rescue rows at all (no local-context, plane-K, swim or supplemental colour arms), so its dear end is just wide, cold, refine.

*Where:* `holo2/src/holo2/solve/place_tiers.py:153-177`; `holo2/src/holo2/engine/recipe.py:214-249`; `holo2/src/holo2/engine/recipe.py:376`; `holo2/src/holo2/engine/recipe.py:293-335` · *dial:* live

**holo3.** cold_live is 250 and cold_rest 260 (still +20 per rung, +5 for a child), which puts both above every other row in the tree: refine, refine.color and revisit at 200 flat, the two supplemental colour arms at 210/220, local context at 220, plane-K at 230, the swim at 240. Refinement now precedes cold unconditionally, at every lane depth, because refine carries no rung term at all. The move was made at d399ba3 in the same commit that deleted the gate, with the stated reasoning 'cold last by price ... the 120 band was extra policy on top of the prices'.

*Where:* `holo3/plugins/place.py:41-52`; `holo3/plugins/place.py:85-89`; `holo3/plugins/refine.py:68`; `holo3/plugins/revisit.py:131-133`; `holo3/plugins/uplift.py:91-92`; `holo3/plugins/local_ctx.py:95`; `holo3/plugins/plane_k.py:105-119`; `holo3/plugins/swim.py:105-107`; `holo3/plugins/fields.py:59`; `holo3/plugins/color_region.py:60`; `holo3/plugins/color_pooled.py:45`

*Scheduler row / doc:* SCHEDULE.md:57-81 (the price ladder) and :153-164 of docs/PAGE-DOMAIN.md (section 6, 'Rest is last by price')

**Implementation delta.** The same six-rung placement ladder in both trees, but cold's two rows move from below refinement to above everything. holo2: ring 40 < word 60/80 < wide 120 < cold 140/150 < refine 200. holo3: ring 40 < word 60/80 < wide 120 < refine/revisit 200 < uplift 210/220 < local 220 < planek 230 < swim 240 < cold 250/260. Two behaviour changes follow. First, holo3 resolves in the affirmative exactly the inversion holo2 left open in recipe.py:320-335 - 'a revision fires only when nothing cheaper is ready' now holds without exception - and it does so by moving cold up rather than refine up, which additionally puts every certificate-minting rescue row ahead of cold. Second, because holo3's residue rows re-price by their own fire ordinal (see dryness-05) while cold does not, a SECOND swim fire (480) or a second plane-K fire (460) now ranks behind cold, so the two ladders interleave on re-fires in a way neither tree has ever measured.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) on all three whole-sheet runs the correlation tier committed zero poses - 5,332 fires between them - while taking 13-65% of every placement second. Two of the three closed byte-exact anyway — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:409-425, inventoried at ARTEFACTS.md:746
- (holo3) on the only fragment material in the record (sheet J, one capture, --complete, workers 6) cold_live earned 15 poses over 1,334 fires and 1,743 cpu-s; on the --pages 100 resume it earned 39 poses over 855 fires and 967 cpu-s. Cold is not decorative on fragments — *artefact:* my tabulation of scratch/J-run.52093/events.jsonl and scratch/J-run.54028/events.jsonl, inventoried at ARTEFACTS.md:269-270
- (holo3) the three e029 arms on the current tree never fired a single job at cost 120 or above; the dearest place fire was word_centre at 60, and all three closed VERIFIED byte-exact — *artefact:* my tabulation of scratch/page-domain-qual/*/events.jsonl, inventoried at ARTEFACTS.md:104
- (holo2) no artefact: holo2 has no residue rescue rows, so no head-to-head on this ordering is possible and none exists — *artefact:* ARTEFACTS.md:744 (section 2.10 records no holo2 number of any kind)

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** Keep holo3's, and record it as reasoned-but-unmeasured. The direction is right on every number we have: cold minted zero poses in 5,332 whole-sheet fires, while the rows now placed ahead of it minted 281 (plane-K), 213 and 26 (local context) and 6 (swim) certificates on real paper. But the reprice has never been exercised: the ONLY runs on the 250/260 ladder are the three e029 arms, and none of them reached cost 120, so no fire in the archived record has ever been ordered by the new numbers. What would settle it costs nothing new to print: re-run the sheet-J fragment resume (the only material where cold earns poses) on the current tree without --complete, and compare the certificate count and the cold pose count against scratch/J-run.54028. That is one holo3 decode of about 5.4 wall-hours at workers 6 by the archived timing - a receiver run, so it belongs in RULINGS.md as a costed proposal, not in this campaign.

**Notes.**

*Reader:* Every archived holo3 run except the three e029 page-domain arms was made with cold at 140/150, i.e. BEFORE refinement and before every residue row. That includes sheet H max-stack, sheet I on machine 2 and the four-run chain, the crop head-to-head, and all three sheet-J runs. Any statement about how the current ladder behaves on colour or on fragments is therefore extrapolation. The sheet-I 'tiles.local at 73% of CPU' anomaly (ARTEFACTS.md:735) was measured with cold cheaper than tiles.local; under the new ladder that ordering is unchanged (local 220 still precedes cold 250), so the anomaly is not a consequence of the reprice.

*Refuter (upheld):* *Corrections:* DIVERGED is right and the ladder is exactly as stated (place.py:41-52 cold 250/260 + COLD_COST_PER_RUNG 20 + CHILD_PREMIUM 5 at :85-89; refine.py:663-665 flat 200 with no rung term; revisit.py:131-133; uplift 210/220; local_ctx 220; plane_k 230; swim 240; d399ba3 is the commit and its message is quoted correctly). holo2's open inversion is at recipe.py:304-335 as described. THE SECOND BEHAVIOUR CHANGE IS OFF BY ONE FIRE: 'a SECOND swim fire (480) or a second plane-K fire (460) now ranks behind cold' is wrong. swim.py:545-549 and plane_k.py:665-673 read `base = COST * attempts if attempts else COST`, and the engine passes attempts=0 on the first push and 1 on the second (engine.py:306, :470), so fires 1 AND 2 both cost the base and the first price above cold is the THIRD fire (swim 480, planek 460). Measured in scratch/J-run.54028/events.jsonl: tiles.swim JobDone costs {240:211, 242:251, 244:249, 480:50, 482:66, 484:69, 720:50, ...} - 711 fires at base against 185 at 2x; tiles.planek {230:146, 232:160, 234:160, 460:15, ...}. The interleaving the row describes is real, it just starts one fire later. Also: the implementation_delta's holo3 ordering omits the three colour rows that sit between wide and refine (color_refit 160, pooled_ctx 170, fields 180) and the fact that fields' and pooled's FIRST fires price at 0 (see dryness-02), i.e. two nominally-dear rows enter at the cheap end.

*Reason:* The reprice, the direction and the ruling stand; the re-fire arithmetic is off by one fire and the ladder listing is incomplete.

*Second lens (final: DIVERGED):* Upheld with the refuter's arithmetic correction, which I reproduced independently. The ladder is as the reader states (holo3/plugins/place.py:41-52 and :83-89 for the rung and child terms; refine flat at 200 in holo3/plugins/refine.py:663-665; the rescue rows at 210-240), and the direction of the move is right. The reader's claim that a SECOND expensive rescue fire outranks the correlation search is off by one fire: holo3/plugins/swim.py:545-549 and holo3/plugins/plane_k.py:665-673 read 'base times attempts if attempts else base', and holo3/engine.py:306 hands the count in at push time while :470 increments it only at fire, so fires one and two both price at base and the third is the first above the correlation rows. Measured by me in scratch/J-run.54028/events.jsonl: the swim shows 711 fires at 240/242/244 and 185 at 480/482/484. Yield lens: this row genuinely decides certificates, and for a reason stronger than the reader's zero-poses argument - the correlation search is one-shot per window and reads the live page set and its support floor at fire time (holo3/plugins/place_sched.py:186-189 into holo3/plugins/place.py:753-757), so putting every certificate-minting rescue row ahead of it changes what that single search sees, not merely when it happens. The reader's proposed settling run is also mis-costed: 19,471 CPU-seconds at six workers is about one wall-hour, not 5.4 (the two archived runs took 34 and 56 minutes by their own file timestamps), which makes it a much easier ask.

---

### dryness-05 — The escalation door: making repeated expensive work drain last without refusing it

**DIVERGED** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B02

Classification trail: reader CARRIED-DIFFERENT → refuter reclassified to DIVERGED → second lens DIVERGED.

**What it decides.** Whether a job that has already failed several times keeps competing at its original price, or sinks behind fresher work - the mechanism that now does the job the dryness gate was reached for.

**holo2.** One term in a single price function, read off the durable spend ledger. A first attempt prices at its own class; a re-attempt is LIFTED to max(base, 90 + 5*(n-1)) plus its lane term, unbounded, so the seventh re-attempt crosses the widened consult and the eleventh crosses cold. It is a horizon, never a wall: nothing is refused and no domain is narrowed. It is deliberately family-blind and therefore does NOT touch placement, because the ordinal is a spend-ledger quantity and placement jobs spend nothing at the wall - the exemption falls out of the architecture rather than a carve-out. So in holo2 it prices payload re-decodes and the calibration and pose re-work families, and nothing else.

*Where:* `holo2/src/holo2/engine/recipe.py:251-291`; `holo2/src/holo2/engine/recipe.py:379-420` · *dial:* live

**holo3.** Each row prices its own re-runs; the engine hands over the fire ordinal and the last price as data and interprets neither. Five rows multiply by the ordinal - the colour refit (160*n), pooled colour context (170*n), plane fields (180*n), both supplemental arms (210*n/220*n), plane-K (230*n) and the swim (240*n). Placement does not (place_sched.py:259-262 ignores attempts entirely), nor do refine, revisit, the payload rows or local context. Escalation is multiplicative, so a second swim costs 480 and a third 720 - it crosses cold on the very first repeat, where holo2's additive band took seven repeats to cross wide.

*Where:* `holo3/plugins/swim.py:545-549`; `holo3/plugins/plane_k.py:663-672`; `holo3/plugins/uplift.py:325-333`; `holo3/plugins/fields.py:804-806`; `holo3/plugins/place_sched.py:259-262`; `holo3/plugins/refine.py:663-665`; `holo3/plugins/tiles.py:749-751`; `holo3/engine.py:24-35 (as documented at SCHEDULE.md:24-35)`

*Scheduler row / doc:* SCHEDULE.md:24-35 (the escalation door) and the '*n' marks in the price ladder at :57-81

**Implementation delta.** Same principle - repetition is priced, never capped, and no domain is ever narrowed - with three concrete differences. (1) HOME: holo2 puts the term in one engine-wide price function keyed on a durable spend row; holo3 puts it in each plugin's own cost function keyed on the engine-supplied fire ordinal, so which rows escalate is a per-row decision rather than a ledger property. (2) SHAPE: additive-with-a-floor (max(base, 90+5(n-1))) versus multiplicative (base*n). The multiplicative form is far steeper - one repeat doubles the price - so holo3's dear rows fall behind cold immediately, whereas holo2's re-work band stayed under cold for ten repeats. (3) COVERAGE: holo2 escalates payload re-decodes and never placement; holo3 escalates neither payload re-decodes (tiles.retry stays flat at 20+2 per rung) nor placement, but does escalate six colour and residue rows holo2 does not have. The net effect on the question this family asks: holo3 has no in-flight hold, but it does have a steeper-than-holo2 mechanism that pushes hopeless repeat work behind everything, which is where the dear-work-drains-last behaviour now comes from.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the sheet-H colour lane burned 38,512 CPU-s (31% of the run) on an escalating-refit ladder that the repricing fix then killed — *artefact:* ARTEFACTS.md:736, citing holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:16-17, instrument measure/h3_repricing.py
- (holo2) the OR-5 census found that nothing bounds re-arming: the worst work key ran 61 BP attempts for 11,820 iterations - 6.2x one full walk of its own ladder - and never certified; a per-key ceiling was proposed and REJECTED on the grounds that current evidence may reorder work, never narrow a domain — *artefact:* quoted in holo2/src/holo2/engine/recipe.py:251-266 citing holo2/docs/MEASUREMENTS.md 'OR-5'; no independent artefact row in ARTEFACTS.md
- (holo3) placement re-fires are NOT escalated on either side; the residue report's strongest ranked finding (R1) is to open that door, measured as one window firing 18 times against holo2's worst of 7 — *artefact:* scratch/sheetI-20260831/v2v3-placement-residue.md:600-631 and :62-66

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** Keep holo3's, and note the open item rather than closing it. The multiplicative form has one measured success (the sheet-H colour refit ladder, 31% of a run, killed by repricing) and no measured failure. What is genuinely open is the row NEITHER tree has: placement re-fires are unpriced in both, and that is the strongest-evidence recommendation in the 2026-08-31 residue report (its R1, 'yield-safe by construction'), still listed as an unactioned proposal at holo3/conversion_docs/OPEN-2026-08-31.md:36-37. That is a holo3 improvement rather than a holo2 carry, so it should leave this map as a separate line of inquiry, not as a retirement blocker.

**Notes.**

*Reader:* Overlaps the pricing family, which owns the full cost table; I carry only the half that bears on 'what holds dear work back now that no gate does'. I could find no artefact that measures the multiplicative escalation against an additive one - the sheet-H number measures repricing versus no repricing, not one shape versus the other.

*Refuter (reclassified):* *Corrections:* Two things. (1) THE SHAPE CLAIM IS WRONG, and it is the row's central comparison: 'Escalation is multiplicative, so a second swim costs 480 and a third 720 - it crosses cold on the very first repeat, where holo2's additive band took seven repeats to cross wide.' In fact fires 1 and 2 cost the same (guard `* attempts if attempts else COST`, swim.py:547, plane_k.py:672, uplift.py:328/330) and the first crossing is at fire 3 - measured above in J-run.54028. 'One repeat doubles the price' should read 'two repeats double it'. Relatedly, 'Five rows multiply by the ordinal' then lists seven stages across six modules; and fields.py:806 / color_pooled.py:190 do NOT carry the guard, so their first fire is free (JobDone cost 0 measured for fields). The engine.py:24-35 citation is an import block; the door is engine.py:306 (attempts handed to cost) and :470 (incremented at fire), documented at SCHEDULE.md:24-35. (2) RECLASSIFY, and split the coverage half out into its own row. The row buries under 'COVERAGE' the largest ordering difference in this family: holo2 ages PAYLOAD RE-DECODES into the 90+5(n-1) band (recipe.py:379-420, family-blind by construction), and holo3 does not - tiles.py:818-820 `_retry_cost` returns PAYLOAD_COST + RUNG_COST*rung flat, forever, measured flat in J-run.54028 (tiles.retry costs {20:692, 22:812, 24:727}). That is not a like-for-like re-implementation, it is a mechanism holo2 has and holo3 lacks on the single biggest certificate-minting row: on the base e029 arm tiles.retry is 9,556 of 37,469 jobs and 1,531.3 of 2,517.3 cpu-s = 60.8% of the run (scratch/page-domain-qual/base-e029.log). And holo2 has a MEASURED number for it that the row does not carry: ARTEFACTS.md:725 (MEASUREMENTS.md:947-948) - aging on the real sheet cut commits 37%/41% and the close verified with 3,970 / 3,702 deferred re-attempts never fired. Be honest in the new row that holo3 bounds retry repetition differently rather than not at all: the tried_version floor (engine.py:452-454) plus `_retry_retire`/`_retry_eligible` (tiles.py:806-812) stop a retry re-arming until its evidence version moves.

*Reason:* Same-intent framing hides a behaviour difference on a yield-bearing row (payload re-decode aging, measured in holo2, absent in holo3), and the multiplicative-shape comparison that carries the row is off by one fire.

*Second lens (final: DIVERGED):* I side with the refuter's reclassification but reverse its implicature. The word must change: holo2 ages repeated payload decodes into a rising band (holo2/src/holo2/engine/recipe.py:379-420) and holo3 does not - holo3/plugins/tiles.py:809-814 returns a flat price forever, which I confirmed measured in scratch/J-run.54028/events.jsonl (2,231 retry fires at exactly 20, 22 and 24, no other price). That is a mechanism one tree has and the other lacks on its single biggest certificate-minting row, so DIVERGED, not CARRIED-DIFFERENT. The refuter's shape correction is also right and I reproduced it (first two fires at base, third at double). Where the refuter over-reaches is in framing the missing aging as a yield exposure on the biggest row: holo2's own measurement of aging is certified 160 to 160 UNCHANGED with three volumes byte-exact on both arms (ARTEFACTS.md:725 citing holo2 MEASUREMENTS.md:1563-1570), i.e. holo2 measured its own aging as a pure cost mechanism. From the yield lens holo3's flat price is if anything the safer side - the cheapest row is the one that mints most certificates, so it fires first and keeps firing - and its cost is visible and bounded: repeated payload decodes are 60.8% of the base whole-sheet run's CPU. holo3 also bounds repetition differently rather than not at all (holo3/engine.py:452-454 evidence-version floor, holo3/plugins/tiles.py:801-807 eligibility and retirement), so the comparison is 'aged by price' against 'gated by evidence', not 'bounded' against 'unbounded'.

---

### dryness-06 — What a verified close abandons, and what --complete does instead

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **nothing observable** · ruling needed **N** · seeds: B02

Classification trail: reader CARRIED-DIFFERENT → refuter REJECTED an argument (classification word stands) → second lens CARRIED-DIFFERENT.

> **Refuter verdict: REJECTED.** A claim that drives this row's delta or its ruling is wrong and must be rewritten before it goes to Germano. The corrections are under Notes; read the reader's text below only through them.

**What it decides.** When the run stops, and therefore how much queued expensive work is never paid for - the only condition under which an admission hold can save anything at all.

**holo2.** The close is a recipe entry with two gates, count_ready and exhaustion. A verified close preempts: the pool is cancelled, the cancelled fires are counted and disarmed, and the run returns. --complete defers the close to exhaustion, so the whole ladder drains first. A run that reaches quiescence without a close ends OPEN and resumable, never as a failure.

*Where:* `holo2/src/holo2/engine/orchestrator.py:245-267`; `holo2/src/holo2/engine/orchestrator.py:315-328`; `holo2/src/holo2/engine/recipe.py:122-131`; `holo2/src/holo2/cli.py:178-190` · *dial:* live

**holo3.** Same two gates, engine-held rather than a row. A certificate-growing merge triggers a close consult; a verified result breaks the loop and the executor is shut down with cancel_futures=True, abandoning both the in-flight jobs and the whole remaining heap. --complete defers every solve to the final consult, so the heap drains to exhaustion first. --no-close observes counts only.

*Where:* `holo3/engine.py:184-211`; `holo3/engine.py:586-620`

*Scheduler row / doc:* SCHEDULE.md:9-11 ('the close is NOT a row: it stays engine-held with its two gates') and :350-357

**Implementation delta.** The same two-gate law and the same preemption semantics, one held by a recipe entry and the other by the engine loop. The delta that matters here is not the mechanism but what sits in the abandoned heap: holo3's frontier at a preempting close contains rows holo2 does not have (refine, revisit, tiles.local), and holo3 abandons them silently while holo2 counts and journals its cancelled fires.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) e029 on the merged tree at default page domain: at the verified close, frontier queued 2901 [place 897, refine 350, revisit 622, tiles.local 986, tiles.scan 46], in flight 7, workers 8. The null arm left 2953 [place 905, refine 350, revisit 631, tiles.local 971, tiles.retry 60, tiles.scan 36]; the pre-merge base arm 2892 [place 920, refine 322, revisit 631, tiles.local 958, tiles.retry 4, tiles.scan 57] — *artefact:* scratch/page-domain-qual/{merged-default,merged-null,base-e029}.log line 3, inventoried at ARTEFACTS.md:104
- (holo3) the same three arms: 23,855 jobs / 1,639.8 cpu-s at default domain against 37,945 / 2,557.4 for the null - 35% cheaper in CPU and 36% fewer jobs for one fewer certificate, all three VERIFIED e5021f8d..., 465,580 B — *artefact:* ARTEFACTS.md:768 and :104
- (holo3) both sheet-J runs and the sheet-H max-stack ran --complete and drained to exhaustion (frontier queued 0, in flight 0), so no deferral could have saved anything on any of them — *artefact:* scratch/J-run.52093/report.json, scratch/J-run.54028/report.json, scratch/holo3-overnight-events/sheetH-maxstack-report.json, inventoried at ARTEFACTS.md:251,269-270

**Yield relevance.** nothing observable — source: second lens (reader said: integrity).

**Recommendation.** Keep holo3's. The close family owns the mechanism; this row exists only to fix the number that decides the dryness question - about 2,900 jobs are abandoned at a preempting close on a healthy K sheet, and not one of them is in the price band any gate would have held.

**Notes.**

*Reader:* No head-to-head exists on a preempting close: the one head-to-head in the record (the 2026-08-31 crop pair) ran both trees to exhaustion, and running holo2 on e029 to compare would be a forbidden receiver run. Overlaps the close family - defer to it on anything beyond the abandoned-work count.

*Refuter (rejected):* *Corrections:* The mechanism description is accurate on both sides (engine.py:184-211 run loop, cancel_futures=True at :210; :586-620 _close_decide with the count gate, --complete deferring to final, --no-close observing counts) and EVERY number reproduces exactly against the three logs (base 2892 [place 920 / refine 322 / revisit 631 / tiles.local 958 / tiles.retry 4 / tiles.scan 57] in flight 5; null 2953 [905/350/631/971/60/36] in flight 2; default 2901 [897/350/622/986/46] in flight 7; jobs 37,469 / 37,945 / 23,855 and cpu 2,517.3 / 2,557.4 / 1,639.8 re-tabulated from each arm's events.jsonl; all three VERIFIED e5021f8d..., 465,580 B). Two claims must go. (1) 'holo3 abandons them silently while holo2 counts and journals its cancelled fires' is false: holo3 prints the entire abandoned frontier broken down by plugin plus the in-flight count in its run banner (diag/readout.py:96, pinned by tests/test_h3_diag.py:356) - it is the very line the row's own evidence quotes - whereas holo2 counts only the cancelled IN-FLIGHT fires (orchestrator.py:483-486, `self._work.cancelled += len(inflight)`), i.e. holo3 reports more, not less. (2) THE RECOMMENDATION'S LOAD-BEARING SENTENCE IS WRONG: 'about 2,900 jobs are abandoned at a preempting close on a healthy K sheet, and not one of them is in the price band any gate would have held.' On the default arm 1,958 of the 2,901 queued jobs are refine 350 + revisit 622 + tiles.local 986, priced 200/200/220 - squarely inside holo3's own deleted cost>=120 band. The sentence is true only of holo2's three-row gated set (wide/cold_live/cold_rest). What IS true, and is the fact the row should carry, is that none of those queued dear jobs ever FIRED on any of the three arms (zero JobDone at cost>=120, verified), so a gate would have been a no-op there for want of anything to defer.

*Reason:* Numbers exact and the close mechanism correctly described, but the row asserts holo3 is silent where it is in fact the more verbose side, and its headline recommendation sentence is false for holo3's own 120 band.

*Second lens (final: CARRIED-DIFFERENT):* The refuter is right on both corrections and I verified both. holo3 is the more verbose side, not the silent one: the run banner prints the whole abandoned frontier broken down per row plus the in-flight count (holo3/diag/readout.py:88-97), which is precisely the line the reader quoted as its own evidence - see scratch/page-domain-qual/merged-default.log line 3 - while holo2 counts only the cancelled in-flight fires (holo2/src/holo2/engine/orchestrator.py:483-486). And the recommendation's headline sentence is false as written: of the 2,901 jobs abandoned on the default arm, 1,958 are refinement (350), revisit (622) and local context (986), all priced 200 to 220, squarely inside holo3's own deleted expensive band; the sentence is true only of holo2's three held rows. The surviving fact is the stronger one anyway and I re-verified it in all three event streams: zero jobs at or above 120 ever FIRED on any arm, so a hold would have had nothing to defer. Yield lens: the close mechanism itself is the same two-gate law on both sides and its difference decides nothing observable - a preempting close fires only on a verified byte-exact recovery, so every abandoned job is surplus by construction; what differs in the abandoned pile is which rows exist at all, which is other rows' business.

---

### dryness-07 — How big the expensive band is: the page set a cold search sweeps

**DIVERGED** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B02, B03

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** How much CPU one cold pass costs, and therefore whether the dear band is a rounding error or half the run - the thing that actually determines whether holding it back is worth anything.

**holo2.** Two cold flavours per rung: live sweeps the pages this session already has a committed pose on, rest sweeps the declared page domain minus those. In practice holo2 was always run with --pages 1, so the live set was the whole domain and the rest partition was empty - the cold_rest row exists but has never swept anything. Its tried marks are flavourless, so a page swept as rest could not be re-swept as live.

*Where:* `holo2/src/holo2/solve/place_tiers.py:85-88`; `holo2/src/holo2/solve/place_sched.py:103-112` · *dial:* live

**holo3.** The page domain is dynamic: the live set seeds {0} and grows as decoded address words open pages; the possible set defaults to every addressable page of the format row (133 at 53x37, 2,621 at 10x10, 5,349 at 7x7) and is capped by --max-pages. cold_live sweeps the live set, cold_rest the complement, each priced on its own partition size, and tried marks are per-flavour so a rest-swept page can be re-swept as live at the lower floor. So cold_rest is now a real, very large pass rather than an empty one, and holo3 answers it with price alone - 260, last in the tree - plus the observation that a healthy non---complete run closes before it is ever the head of the heap.

*Where:* `holo3/plugins/place.py:117-127`; `holo3/plugins/place_sched.py:95-101`; `holo3/plugins/cold.py:230-272`; `holo3/plugins/cold.py:124-150`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:18-45 (section 1, the ruling), :114-152 (section 5, floors price the address space), :153-164 (section 6, rest is last by price)

**Implementation delta.** holo2's cold sweeps one page; holo3's rest flavour sweeps up to 133 (default) or 5,349 (a small matrix, unbounded). That is a change of two to three orders of magnitude in the cost of a single fire, made on the receiver axis with no format change, and it is the reason a dryness gate was reached for at page-domain W3 in the first place. holo3's stated defence is that price keeps it off the ordinary path and the close preempts first - which is true for a healthy sheet that closes, and false for --complete and for anything that does not close.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) sheet J, --pages 100 --complete, workers 6: cold_rest fired 696 times for 9,640 cpu-s and ZERO poses - 49.5% of the entire run's 19,471.3 cpu-s. cold_live on the same run: 855 fires, 967 cpu-s, 39 poses — *artefact:* my tabulation of scratch/J-run.54028/events.jsonl and report.json, inventoried at ARTEFACTS.md:270
- (holo3) the same volume at a single-page domain (J-run.52093, rest partition empty): cold_live 1,334 fires, 1,743 cpu-s, 15 poses, out of 11,397.6 cpu-s total - and 357 certificates against the resume's 657 — *artefact:* my tabulation of scratch/J-run.52093/events.jsonl and report.json, inventoried at ARTEFACTS.md:269
- (holo3) unbounded rest on a sheet that never closes is a derived 60-85 cpu-hours (A4 extrapolation, census times per-fire cost); the archived census showed about 5.2k whole-sheet fires for zero poses — *artefact:* holo3/docs/PAGE-DOMAIN.md:159-164; the census half resolves to v2v3-placement-residue.md:409-425 (5,332 fires), the cpu-hour figure has no artefact of its own
- (holo1) the e029 done-geometry census: the --complete tail spent 160 priced colds over 133-page sweeps, 7,200 cold-progress steps, to mint 2 certificates; v1's cold_first_max_pages defaulted to 1 — *artefact:* ARTEFACTS.md:764,766, citing docs/DONE-GEOMETRY.md:268-273 and docs/PLACEMENT-IMPROVEMENTS.md:328-341

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** Keep holo3's price ordering, but put the real question to Germano, because it is not the gate: on the one measured large-domain run, cold_rest cost half the run for nothing, and NEITHER a dryness gate NOR the reprice would have saved a second of it - both are deferrals, and that run drained under --complete. The only levers that remove the cost are (a) --max-pages, which already exists and is per-run, (b) making cold_rest opt-in under --complete, or (c) leaving it and telling operators to bound the domain. My recommendation is (c) plus one documentation fix: docs/PAGE-DOMAIN.md:157-164 says price keeps rest 'off the ordinary path' and names --complete as the exception in half a sentence; the sheet-J measurement should be written into that section as the instance, so the next operator sizes --max-pages before a --complete fragment run. Note the yield side is real and points the other way for the LIVE flavour: cold_live earned 15 and 39 poses on the two fragment runs, so nothing here argues for weakening cold generally.

**Notes.**

*Reader:* Both sheet-J runs predate the reprice (tree 1faa7a2, cold at 140/150) and used the old --pages spelling, so the cold_rest cost is measured at the old price. On a --complete drain the price does not change the total, so the 9,640 cpu-s figure carries over unchanged; on a preempting run it would move later. Overlaps the page-domain family, which owns the domain design; I carry only the cold-band cost.

*Refuter (upheld):* *Corrections:* DIVERGED stands and the two big measurements are exact - I re-tabulated both event streams: J-run.54028 cold_rest 696 fires / 9,640.3 cpu-s / 0 poses out of 19,471.3 total (49.5%) and cold_live 855 / 967.2 / 39 poses; J-run.52093 cold_live 1,334 / 1,743.0 / 15 poses out of 11,397.6, no cold_rest costs at all (RunOpen pages=1), certificates 357 vs 657. Both runs are --complete --workers 6 (argv verified). holo2's side checks out too (place_cold.py:90-93 flavourless cold_tried_id, :116-133 the partition and its degenerate single-sheet case; ARTEFACTS.md:767 for '--pages 1 in practice'). THREE corrections. (a) 'cold_live sweeps the live set, cold_rest the complement, EACH PRICED ON ITS OWN PARTITION SIZE' is wrong: place.py:85-89 stage_price is flat 250/260 + 20/rung + 5/child and knows nothing about how many pages the fire will sweep. What the partition size sets is the SUPPORT FLOOR - place_sched.py:186-190 passes `cold_h_pages = len(all_pages)` into the hypothesis count (PAGE-DOMAIN.md:114-152, 'Floors price the address space' is a metaphor about the floor, not the price). This matters for the family and no row says it: a rest fire over 133 pages and one over 2 are scheduled at the SAME price while costing wildly different CPU (measured 9,640 cpu-s over 696 rest fires = 13.9 s/fire against 1.13 s/fire for live). (b) the live set does not grow 'as decoded address words open pages' - store.py:669-676 grows it inside the Placement fold, i.e. on any committed pose, exactly like holo2's place_cold.live_pages; the real difference from holo2 is that holo3 SEEDS it with {0} (store.py:97) where holo2 derives it purely from poses, so before the first pose holo2's rest partition is the whole domain and holo3's is the domain minus page 0. (c) --pages is retired in favour of --max-pages (PAGE-DOMAIN.md:184-186), which is what the recommendation should name.

*Reason:* The cost measurement and the ruling stand; the price/floor conflation and the live-set provenance are wrong, and the price-independent-of-sweep-size fact is the mechanism the row is circling without naming.

*Second lens (final: DIVERGED):* Upheld, with the refuter's correction accepted and extended. The reader's phrase 'each priced on its own partition size' is wrong: the price is flat (holo3/plugins/place.py:41-52 and :83-89 know nothing about how many pages a fire will sweep). What the partition size sets is the support floor - holo3/plugins/place_sched.py:186-189 passes the partition's page count into the hypothesis count and holo3/plugins/place.py:753-757 turns it into the minimum support the search demands. That is the yield mechanism, and holo3/docs/PAGE-DOMAIN.md:141-152 says so in its own words: the live route's lower floor admits origins the rest route excludes, 'yield, not just cost'. So this row decides certificates directly - the same window with the same evidence can be accepted at a small declared domain and refused at a large one - and the refuter is right that the decoupling of price from sweep size, not the missing hold, is what makes a large domain expensive. I re-tabulated both fragment runs independently and every figure holds exactly: rest 696 fires / 9,640.2 processor-seconds / 0 poses / 49.5% of the run, live 855 fires / 967.1 / 39 poses (1.13 s a fire against 13.85). One fact neither lens carries, from the same run's report: poses landed on 28 distinct pages while the rest route committed none, so on the only fragment material in the record every page was opened by decoded address words, not by the wide sweep. And the reader's costing of its own follow-up is off by a factor of five: 19,471 processor-seconds at six workers is about one wall-hour, and the two archived runs took 34 and 56 minutes.

---

### dryness-08 — Nothing bounds how many expensive page searches run at once, and each one accumulates memory in proportion to the pages it sweeps

**DIVERGED** · evidence **UNPROVEN** · yield **decides-certificates (a run killed for memory certifies nothing further; no other channel)** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether a large-domain run survives to be certified at all, on a machine whose recorded peaks already sit close to its ceiling.

**holo2.** No explicit bound either. The gate makes gated work start only when the machine is otherwise dry, and two gated jobs at the SAME price can still run side by side (the test is min(in_play) < job.cost, so an equal price does not hold), so all workers can end up on cold together. In practice this never mattered: holo2 ran at a one-page domain, so a cold fire held one page's transform.

*Where:* `holo2/src/holo2/engine/orchestrator.py:269-287`; `holo2/src/holo2/engine/orchestrator.py:387-395` · *dial:* live

**holo3.** No bound on concurrent dear fires. Inside one cold fire, the per-page transform cache (cold.py:242) is keyed by page and never evicted for the length of the sweep, so a fire over the whole rest partition accumulates one transform per page. The design record measures the per-page transform at 45.8 MiB at 53x37 and derives 5.95 GiB at 133 pages, and rejects a cross-fire cache on the grounds that the tier must not run on a healthy sheet - which is true of a healthy closing sheet and not of --complete.

*Where:* `holo3/engine.py:433-475`; `holo3/plugins/cold.py:242-262`; `holo3/plugins/cold.py:124-143`

*Scheduler row / doc:* docs/PAGE-DOMAIN.md:165-173 (section 7, the rejected transform store)

**Implementation delta.** The divergence is not a bound that was removed; neither tree ever had one. It is that the same absent bound now guards a quantity two to three orders of magnitude larger, because holo3's cold_rest sweeps a whole page domain where holo2's swept one page. Concretely: N workers all in cold_rest hold up to N times (pages swept) times 45.8 MiB simultaneously, against holo2's N times 45.8 MiB.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the per-page cold transform is complex64, 45.8 MiB measured at 53x37, 5.95 GiB derived at 133 pages — *artefact:* holo3/docs/PAGE-DOMAIN.md:167-169; NOT carried in ARTEFACTS.md
- (holo3) recorded peak RSS on real runs: sheet I baseline 48.8 GiB (and 47.86 GiB on the surviving re-run); post-change memory steps breached at 60.51 and 60.24 GiB, 0.27 GiB apart at workers 8 and 6, so worker count is not the driver — *artefact:* ARTEFACTS.md:231 and :737, citing PARITY.md:18,451 and POST-FORENSICS.md:496-621
- (holo3) counter-evidence: sheet J ran 696 cold_rest fires over a 100-page domain at workers 6 under --complete and finished, producing a report — *artefact:* scratch/J-run.54028/report.json, inventoried at ARTEFACTS.md:270
- (holo3) the machine is 64 GB and one production decode at a time is the standing rule; three instruments at once already killed a sheet-H decode — *artefact:* no artefact in ARTEFACTS.md; recorded as a working rule in the user's memory index (feedback-memory-budget)

**Yield relevance.** decides-certificates (a run killed for memory certifies nothing further; no other channel) — source: second lens (reader said: decides-certificates).

**Recommendation.** Keep holo3's, and record the exposure rather than building a bound. The one measured instance (100 pages, 6 workers, --complete) survived, and inventing a concurrency cap would be a ceiling on an evidence pass, which is the one thing the standing rule forbids. What is cheap and honest instead: note in docs/PAGE-DOMAIN.md section 7 that the per-fire cache is page-domain-scaled and that the memory ceiling, not the price, is what bounds --max-pages on a --complete run. If Germano wants a number, the settling measurement is free - re-read the peak RSS the sheet-J resume already recorded, if its run directory or the overnight ledger carries one; I could not find an RSS field in scratch/J-run.54028/report.json.

**Notes.**

*Reader:* The accumulation is my reading of the code (cold.py:242 builds the dict outside the page loop at :253 and nothing clears it), not a measured allocation. Two of the four rotations share a padding key and therefore share one transform, so the per-page cost is one or two transforms, not four. Late fires sweep only untried pages, so only the first rest fire on a window pays the full domain.

*Refuter (upheld):* *Corrections:* The code reading is right: cold.py:242 builds `page_transforms` outside the page loop at :253, keyed (page, pad_y, pad_x, fshape), never cleared for the length of the sweep; there is no bound on how many dear jobs run at once; 45.8 MiB / 5.95 GiB are verbatim from PAGE-DOMAIN.md:167-169; the RSS figures are verbatim from ARTEFACTS.md:231 (I checked its own source: conversion_docs/overnight/ledger-run3.jsonl step='sheet-I' does record peak_rss_gib 48.8) and :737. Three additions. (a) holo3 DOES have one concurrency bound, just not a global one: engine.py:445-447 defers a popped worker whose (plugin, subject) is already in flight, so the N-workers-in-cold_rest case needs N distinct windows - which is the ordinary case, so the arithmetic survives. (b) 'No explicit bound either' undersells holo2: holo2 built the ACCOUNTING half - place_cold.py:177-193 declares a page-weighted residency lease per cold fire, core/work.py:537-564 LeaseBook takes/releases it at arm/disarm and publishes residency to the observer, and the docstring states the policy is deliberately unbuilt pending measurement ('inventing its policy now would be a fabricated default'). holo3 has no lease of any kind and dropped the concept by ruling (SCHEDULE.md:382 'Deliberately NOT carried: v2's journal/replay/lease...', 07-placement.md:419 'drop leases/keys'). Leases are OUT-OF-FILTER by the plan's own §4 list, so this is a clause to add, not a new row - but the row should not claim the two sides are symmetric here. (c) since only untried pages are swept (place_sched.py:95-101) and the key includes the padding group, the worst case is the FIRST rest fire on a window, at one or two transforms per page.

*Reason:* Reading of the code and every quoted number are correct; the holo2 side needs the lease/residency clause and holo3's per-subject in-flight bound named.

*Second lens (final: DIVERGED):* Upheld; I re-read the code and both of the refuter's additions are right and worth carrying. The cache is built once per fire outside the page loop and never cleared (holo3/plugins/cold.py:242 with the sweep at :253), and nothing bounds how many expensive fires run at once. holo3 does have one bound the reader missed - holo3/engine.py:445-447 defers a job whose row and subject are already in flight - but that only forces the concurrent fires onto distinct windows, which is the ordinary case, so the arithmetic stands. The reader's 'no explicit bound either' undersells holo2, which built the accounting half and left the policy deliberately unwritten (holo2/src/holo2/solve/place_cold.py:177-193 and holo2/src/holo2/core/work.py:537-564); holo3 dropped the concept by ruling (holo3/SCHEDULE.md:382). Yield lens: this is the only row in the family whose failure mode is total rather than marginal - a run killed for memory certifies nothing further - and the recorded peaks leave little headroom (48.8 GiB on the sheet-I baseline, two later breaches at 60.5 and 60.2 GiB on a 64 GB machine). The counter-evidence is real and single: 696 wide fires over a 100-page domain at six workers finished and produced a report. I confirmed the reader's note that that run's report carries no memory figure - there is no peak-RSS field in scratch/J-run.54028/report.json - so the free measurement it proposed does not exist.

---

## Pricing

21 rows; 9 carry a ruling.

**Reader's family notes.** SCOPE. Twenty-one rows: the seven seeds B04-B14 that name a constant, B47, B48, B61, plus six mechanisms found in the code that no seed names (the queue's seat model and pop-side re-price guard, the within-price tie-break, the escalation door and its colour-fit ordinal, the re-read's price, the tiles.local mispricing, and the durable half of the tried-set floor). The dryness GATE itself is another family's row; pricing-02 covers only what the reprice 140/150 -> 250/260 does to the order.

THE HEADLINE. The cost SCALE is carried essentially intact — survey/ingest 10, calibrate 15, payload 20, ring 40, word 60/80, wide 120, refine 200, LANE 2, COLD 20, CHILD 5, and the identical one-line price formula (tier + rung x depth + child) — and both sides pin their own literals with a golden. Three things are not carried: the two cold prices (140/150 gated -> 250/260 ungated, DIVERGED), the uniform rework/aging band (ABSENT, deleted by user ruling 2026-08-29), and the fire-count tripwire (ABSENT). One thing is new: the escalation door, where six residue rows price their own re-runs multiplicatively.

WHAT THE PRICING FAMILY CAN AND CANNOT DECIDE. Under --complete the queue drains and price is order-only for every row here; the exceptions are the rows that can suppress work outright (the tried-set floor, pricing-15) or end the run (the tripwire, pricing-14). Under a PREEMPTING close every price is yield-visible, because whatever has not fired when the payload verifies is never minted: the licensed e029 pair on the current tree closes at 1,356 vs 1,360 certificates with the payload byte-exact both ways (ARTEFACTS.md:768), which is the size of that effect on one healthy K sheet.

DOC CONTRADICTIONS FOUND. (1) holo3/conversion_docs/13-engine-diag-cli.md:118 still declares COLD_LIVE 140 / COLD_REST 150 and 'REWORK_BASE 90, REWORK_STEP 5' as the holo3 cost table 'verbatim'; the tree has 250/260 and no rework term. 00-contract.md:317-322 was amended in place and is current. (2) The build contract's cost line and DESCRIPTOR-PLAN.md:218-227 disagree about rework in the same repository; D6-EXECUTION.md:111-119 records the reconciliation. Neither is a verdict for this map, only context.

WHAT I COULD NOT VERIFY. No cross-tree oracle compares the two cost scales (no holo3/tests/test_h3_drift_*.py names recipe.py or place_tiers.py), so every CARRIED-IDENTICAL row here rests on two independent goldens plus reading, not on a bit-exact comparison. No artefact measures any single price on either side; ARTEFACTS.md:744 says so explicitly for the gate, and both trees call their numbers PROVISIONAL orders. Two of my holo3 evidence citations (SCHEDULE.md:538-560 and :601-642) sit in the same generated-evidence section ARTEFACTS.md:283 licenses but a few lines past the :426-520 range it names; flagged rather than silently widened.

**Refuter's family notes.** MECHANISMS NO ROW COVERS. (1) THE FIRST-PUSH ZERO PRICE (detailed under pricing-19) is the one finding here that could change a real run's order: holo3/plugins/fields.py:806 and color_pooled.py:190 omit the `if attempts else` guard their four sibling escalating rows carry, so both are pushed at cost 0 the first time — cheaper than survey (10) — instead of the 180/170 the ladder, SCHEDULE.md and the golden all advertise. Colour-only, which is why no K artefact shows it. The one-line fix and the RULINGS question are written into that row. (2) THE ESCALATION ORDINAL IS SESSION-LOCAL. holo3's `attempts` lives on the in-memory bookmark (holo3/descriptor.py:59) and a `--resume` mints fresh bookmarks from the fact snapshot (engine.py:251-266), so every escalating row restarts at its base price on each resume. The four-run e034 chain is four fresh escalation ladders. Nothing in the map says so, and it interacts with pricing-15's recommendation to keep the re-offer-everything resume. (3) THE CLOSE CONSULT'S PRICE. holo2 schedules the close as an ordinary priced recipe entry — RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD) at holo2/src/holo2/engine/recipe.py:598, i.e. it competes in the same cost order at 20 behind a count-ready gate. holo3 runs the consult out of band, engine-held and unpriced (SCHEDULE.md:355-357; it is not one of the 17 ladder rows). The close FAMILY owns the mechanism, but the fact that one tree prices it and the other does not is a pricing fact and no row states it. (4) A `stage()` that turns None leaves a standing seat in place (holo3/engine.py:302-304 returns before the seat is cleared); the pop then discards it via the `fresh_stage is None` branch at :457-459. Harmless today, but it is a second way a heap entry outlives its price, and pricing-17 describes the seat model as if supersession were the only one. VERIFICATION FOOTING. Every holo2 and holo3 file:line in this family was opened at HEAD 29d9a8d; every ARTEFACTS.md line cited by the reader resolves and says what the row quotes; the three page-domain-qual logs and their argv files were read directly rather than through ARTEFACTS. The reader's own honesty flags are correct and I confirm them: no cross-tree oracle compares the two cost scales (none of holo3/tests/test_h3_drift_{declared,format,kernels,receiver}.py names recipe.py, place_tiers.py or place_slot.py), no artefact measures any single price on either side, and SCHEDULE.md:538-560 / :601-642 do sit past the :426-520 range ARTEFACTS.md:283 licenses. One error the reader inherited rather than made: ARTEFACTS.md:104 and :768 call the null arm `--pages 1`; the recorded argv says `--max-pages 1`.

**Second lens (yield) family notes.** YIELD LENS, THE ONE STRUCTURAL FINDING. Across the whole archived corpus exactly three runs end with work unfired: the three e029 page-domain arms in scratch/page-domain-qual/, each closing VERIFIED with ~2,900 jobs still queued. Those are the only runs where any price can decide which tiles certify. Every other stored run drains to 'frontier queued 0 - in flight 0' (both sheet-J runs, all four sheet-I runs), and on a run that drains price is order-only by construction. Now cross that with which rows the three preempting arms exercise: their scheduled placement stages are ring, word_centre and word_rest ONLY - no wide, no cold - and being a K sheet they run no colour row, so no escalating row either. The rows that DO exercise wide and cold (sheet J: 1,334 and 850 wide pushes, 1,330 and 847 cold_live, 696 cold_rest) and the escalating colour rows (sheets J and I) are all on runs that drain. CONSEQUENCE: of the six rows checked, only pricing-09 - the missing rework/aging band - can change which tiles certify on material we hold, because the population it would have damped (payload re-fires at 6-11 per subject, 19,841 of 23,855 jobs) is exactly what is still queued when e029 verifies. pricing-01, -02, -06, -08 and -19 are order-only on this corpus. The corpus does show what an ordering change is worth at a preempting close: 1,360 -> 1,356 certificates on the same capture with the payload byte-exact.

A CAVEAT THAT APPLIES TO BOTH DELETED MECHANISMS. holo3's null-proofs for the aging deletion and for the escalation door were both taken at one worker under --complete (SCHEDULE.md:538-560) - a draining run, the one regime in which a pricing change cannot move a certificate. They are honest evidence that nothing else broke; they are not evidence about yield. The same is true of holo2's aging measurement, taken on runs that also drained.

TWO STALE DOCUMENTS. holo3/conversion_docs/13-engine-diag-cli.md:113-118 still declares the cold prices 140/150 and REWORK_BASE 90 / REWORK_STEP 5 as holo3's cost table 'verbatim'; and 00-contract.md:319, which was amended in place to 250/260 and 'No dryness gate', still carries 'REWORK max(tier, 90+5*(n-1))' two clauses earlier, while a test forbids the engine from owning any such name. Both should be corrected with the map.

ONE INHERITED ERROR. ARTEFACTS.md:104 and :768 write the null arm's flag as --pages 1; the recorded argv in scratch/page-domain-qual/merged-null-run.64562 says --max-pages 1.

VERIFICATION FOOTING. All source read at HEAD 29d9a8d. Beyond re-opening every path:line, I derived the stage tallies myself from the events streams of the three e029 arms and both J runs, and re-derived every dispatch-price mean from the stored report.json churn lines of sheets I and J - that is where the price-0 finding stops being an arithmetic argument and becomes a measurement.


### pricing-01 — The ordinary placement price table (ring 40 / word centre 60 / word rest 80 / wide 120) and the one-line price formula

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B04, B05

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT → second lens CARRIED-DIFFERENT.

**What it decides.** In what order a window's four ordinary placement routes are tried against every other job in the receiver.

**holo2.** Six priced placement classes are declared as data, with the four ordinary ones at 40/60/80/120. A window's price for a tier is computed in exactly one place: tier cost + that tier's rung term x the window's lane depth + the child premium if it is a subdivision child. The same four numbers are spelled a second time on the engine's side because neither package may import the other, and a data test pins the two spellings equal.

*Where:* `holo2/src/holo2/solve/place_tiers.py:153-166`; `holo2/src/holo2/solve/place_slot.py:197-217`; `holo2/src/holo2/engine/recipe.py:215-218`; `holo2/tests/engine/test_cost_vocabulary.py:46-58` · *dial:* live

**holo3.** The same four literals live in one dict keyed by stage name, and `place.stage_price` is character-for-character the same expression: stage cost + (cold rung term if a cold stage else lane term) x lane depth + child premium if depth. Only one spelling exists; the engine never sees a number, it calls `descriptor.cost`.

*Where:* `holo3/plugins/place.py:41-47`; `holo3/plugins/place.py:85-89`; `holo3/plugins/place_sched.py:259-262`

*Scheduler row / doc:* SCHEDULE.md price ladder rows 40/60/80/120 (SCHEDULE.md:66-69); SCHEDULE.md:337-373 'The life of a decode'

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) (40, 'place', 'ring'), (60, 'place', 'word_centre'), (80, 'place', 'word_rest'), (120, 'place', 'wide') — *artefact:* holo3/tests/test_h3_schedule.py:18-43 (LADDER_GOLDEN, asserted against the generated ladder at :140-143) plus the SCHEDULE.md fenced-block golden
- (holo2) ring 40 / word_centre 60 / word_rest 80 / wide 120, two spellings pinned equal — *artefact:* holo2/src/holo2/solve/place_tiers.py:153-166 + holo2/tests/engine/test_cost_vocabulary.py:46-58

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Both sides call their numbers PROVISIONAL orders, not measured costs (place_tiers.py:32-34; SCHEDULE.md:20-22). No artefact measures any of the four. The identity is of constants and of a formula, not a bit-exact kernel: no cross-tree oracle compares the two cost scales (verified: no holo3/tests/test_h3_drift_*.py names recipe or place_tiers).

*Refuter (reclassified):* *Corrections:* The four constants and the price formula ARE identical and pinned, but the row calls all four routes 'ordinary' and claims identity of 'in what order a window's four ordinary placement routes are tried against every other job'. That is false for wide: holo2/src/holo2/solve/place_tiers.py:163 declares TIER_WIDE(120) with gated=True, and holo2/src/holo2/engine/orchestrator.py:387-395 refuses a gated job admission while anything cheaper is READY or IN FLIGHT in either book. holo3 has no gate on wide at all (holo3/engine.py:433-474 `_fill` pops the cheapest ready job, full stop; holo3/plugins/place_sched.py:264-266 `_place_eligible` is placed/retired only). holo2's own seed ledger says so explicitly: retirement_docs-2026-09/seeds/holo2-behaviour-ledger.md:13 (B03) 'Exactly three tiers carry gated=True: wide_consult, cold_live, cold_rest'. So: (a) drop the word 'ordinary' for wide and state the delta 'wide's admission gate is not carried; the gate's ruling belongs to the dryness family (B02/B03)'; (b) pricing-02's holo2 sentence 'both carry gated=True' should read 'wide, cold_live and cold_rest carry gated=True'. Also strengthen the evidence: a SECOND live holo3 pin exists that the row does not cite — holo3/tests/test_h3_plugins_placement.py:88-103 goldens stage_price at depth 0 for all six stages {ring 40, word_centre 60, word_rest 80, wide 120, cold_live 250, cold_rest 260} and pins both rung terms and the child premium.

*Reason:* wide is admission-gated in holo2 and ungated in holo3, so when it fires differs; that is CARRIED-DIFFERENT, not IDENTICAL.

*Second lens (final: CARRIED-DIFFERENT):* The first refuter is right and I reproduced it at HEAD 29d9a8d: holo2 declares the wide route gated (holo2/src/holo2/solve/place_tiers.py:163 TierPrice(TIER_WIDE, 120, True, ...)) and refuses a gated job admission while anything cheaper is ready or in flight (holo2/src/holo2/engine/orchestrator.py:387-395), while holo3 has no such refusal anywhere - an idle worker takes the cheapest ready job (holo3/engine.py:433-443). So the reader's word 'ordinary' is wrong for wide and CARRIED-DIFFERENT is the right label. I narrow the delta further than the refuter does: the 'anything cheaper is READY' half of holo2's test is already enforced by the head comparison two lines above (orchestrator.py:382-384 returns 'queue' whenever the cheaper book wins), so the gate's only additional force is the 'cheaper is IN FLIGHT' clause. At one worker nothing is in flight when a job is popped, so the gate is provably inert there and the two trees run the same sequence; it bites only under concurrency. On the yield axis the difference is not observable on the archived corpus: the three e029 arms in scratch/page-domain-qual/ never schedule a wide pass at all (stage tallies over their events.jsonl are ring / word_centre / word_rest only), and the two runs that do reach wide - scratch/J-run.52093 with 1,334 wide pushes and scratch/J-run.54028 with 850 - both end with 'frontier queued 0 - in flight 0' and the close still open, i.e. they drain, where price cannot change a certificate set. Prices and formula themselves are identical and double-pinned (holo3/tests/test_h3_plugins_placement.py:90-96 goldens all six stage prices at depth 0).

---

### pricing-02 — The two cold prices — 140/150 gated behind global dryness vs 250/260 ordered last by price

**DIVERGED** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **Y** · seeds: B04, B05, B10

Classification trail: reader DIVERGED → refuter upheld → second lens DIVERGED.

**What it decides.** Whether, and how early, a window may run a whole-page correlation sweep; and therefore how much of the sheet's cheap work is done before the dearest search starts.

**holo2.** cold_live costs 140 and cold_rest 150, each +20 per rung, and both carry gated=True. A gated job is refused admission while anything cheaper is READY or IN FLIGHT in either book, so cold can only start on a globally dry receiver. The pair therefore sits below refine (200) at shallow rungs: cold_rest overtakes refine from rung 3 and cold_live from rung 4, an inversion holo2's own pin records and leaves OPEN.

*Where:* `holo2/src/holo2/solve/place_tiers.py:167-176`; `holo2/src/holo2/engine/recipe.py:225-226`; `holo2/src/holo2/engine/orchestrator.py:372-395` · *dial:* live

**holo3.** cold_live costs 250 and cold_rest 260, still +20 per rung, and there is no gate anywhere in `_fill`: an idle worker takes the cheapest ready job, full stop. The reprice puts both cold flavours above every other row in the tree including refine (200) and the swim (240 on its first fire), so the dryness property the gate used to enforce is now produced by the price alone.

*Where:* `holo3/plugins/place.py:41-47`; `holo3/engine.py:433-474`

*Scheduler row / doc:* SCHEDULE.md:81-82 (cold_live 250, cold_rest 260, the two dearest rows in the tree); docs/PAGE-DOMAIN.md:153-163 '§6 Rest is last by price'

**Implementation delta.** Two changes at once. (1) The numbers moved 140/150 -> 250/260 (docs/PAGE-DOMAIN-WORKPLAN.md:100-107 records the move; conversion_docs/13-engine-diag-cli.md:118 still declares the holo2 numbers 'verbatim', and conversion_docs/00-contract.md:317-319 was amended in place to 250/260 + 'No dryness gate'). (2) The admission refusal was built and then deleted (2026-09-01). Consequence for the cost order: in holo2 a deep cold sweep could be admitted while a refine descriptor waited (refine 200 vs cold_rest 210 at rung 3, cold_live 220 at rung 4); in holo3 refine, revisit, refine.color, the uplift arms, planek and the swim's first fire all precede every cold pass at every rung. Consequence for what fires at all: holo2's gate could hold a cold pass back indefinitely while cheap work kept arriving; holo3's price cannot, it only queues it later.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) NO yield or cost number exists for the gate; it is described only as mechanism — *artefact:* ARTEFACTS.md:744
- (holo2 vs holo3) "holo2's dryness gate saves nothing on a run that drains." Both arms go to full exhaustion; holo2's first cold fire sits at 44% / 36% of its placement stream, holo3's at 53% / 44% — holo3's plain price ladder already reproduces the ordering at --workers 1 — *artefact:* ARTEFACTS.md:746 (scratch/sheetI-20260831/v2v3-placement-residue.md:41-47)
- (holo3) Zero cold_rest events at the default page domain on the real healthy e029 sheet — *artefact:* holo3/docs/PAGE-DOMAIN-WORKPLAN.md:120-123; the run is the licensed scratch/page-domain-qual/merged-default arm at ARTEFACTS.md:768
- (holo3) merged default (133 possible pages) 1,356 certs / 1,639.8 cpu-s / 23,855 jobs vs merged --max-pages 1 1,360 / 2,557.4 / 37,945 — all VERIFIED e5021f8d…, 465,580 B — *artefact:* ARTEFACTS.md:768
- (holo1) cold cost at single-page domain ~1-3 s vs 30-48 s per avoided cold at large domains — *artefact:* ARTEFACTS.md:766 (docs/PLACEMENT-IMPROVEMENTS.md:328-341)

**Yield relevance.** decides-order-only — source: second lens (reader said: decides-certificates).

**Recommendation.** keep holo3's — the only head-to-head says the gate saves nothing on a draining run and that the plain ladder reproduces the ordering, and holo3's cold at 250/260 makes the ruled property (refine after everything cheaper) unconditional where holo2's inverted on the two deepest cold rungs. Record the doc contradiction: conversion_docs/13-engine-diag-cli.md:118 still declares 140/150 'verbatim' and is stale against the tree.

**Notes.**

*Reader:* The gate mechanism itself belongs to the dryness-gate family reader; this row covers only the PRICES and what the reprice does to the order. Cold pricing is yield-relevant, not merely order-relevant, in two ways: it decides which windows are still unplaced when a close preempts (the e029 default arm ends with 276 UNKNOWN / 16 ADDRESSED tiles), and at large page domains a rest sweep is the dearest thing the receiver can do (PAGE-DOMAIN.md:160-163 derives ~60-85 cpu-hours for unbounded rest on a sheet that never closes — an extrapolation, not a measurement).

*Refuter (upheld):* *Corrections:* DIVERGED stands and every price, doc and run number resolves. Three fixes. (1) THE IMPLEMENTATION-DELTA SENTENCE INVERTS THE ARITHMETIC: 'in holo2 a deep cold sweep could be admitted while a refine descriptor waited (refine 200 vs cold_rest 210 at rung 3, cold_live 220 at rung 4)'. At rung 3 cold_rest is 210 > refine 206, so cold_rest is the one that waits. The inversion lives at the SHALLOW rungs: cold_live 140/160/180 and cold_rest 150/170/190 at d=0/1/2 all sit under refine 200/202/204, so a shallow cold could start ahead of a ready refine; the inversion ENDS at rung 3 for cold_rest and rung 4 for cold_live, which is exactly what the holo2 comment at holo2/src/holo2/engine/recipe.py:349-357 means by 'overtaken'. The row's own holo2 prose ('the pair sits below refine at shallow rungs') is right; only the delta sentence is backwards. (2) Citation: holo3/conversion_docs/13-engine-diag-cli.md:117 carries 'COLD_LIVE 140, COLD_REST 150'; :118 carries 'REWORK_BASE 90, REWORK_STEP 5'. Cite the block as :113-118, not :118 for both. (3) The flag is `--max-pages 1` (verified in scratch/page-domain-qual/merged-null-run.64562/argv); ARTEFACTS.md:104 and :768 both write `--pages 1` and are the ones that are wrong — worth a line, since the row quotes those cells. Independently verified at HEAD: holo3/plugins/place.py:41-47 = 250/260, no `gated`/`dryness` name anywhere in holo3 outside docs; holo3/docs/PAGE-DOMAIN.md:153-163 §6 verbatim; conversion_docs/00-contract.md:316-320 amended to 250/260 + 'No dryness gate'; merged-default.log = 1,356 certs / 1,639.8 cpu-s / 23,855 jobs / UNKNOWN 276 · ADDRESSED 16, merged-null.log = 1,360 / 2,557.4 / 37,945, both VERIFIED e5021f8d…

*Reason:* Classification and evidence hold; one sentence of the delta reverses which side waits at rungs 3-4.

*Second lens (final: DIVERGED):* DIVERGED stands; I confirm both the refuter's arithmetic correction and its citation fixes, and I downgrade the reader's yield label from decides-certificates to decides-order-only on the evidence we hold. The reader's delta sentence does reverse the inversion: at footing depth 3 holo2's cold_rest is 150+60=210 against refine's 200+6=206, so cold is the one that waits; the inversion is at the SHALLOW depths (140/150 under 200) and ends at depth 3-4, exactly as holo2's own comment at holo2/src/holo2/engine/recipe.py:349-357 says. Verified at HEAD: holo3/plugins/place.py:41-47 carries 250/260 and no gate name exists in holo3 outside documentation. On yield: cold IS exercised on the stored corpus - scratch/J-run.52093 pushes 1,330 cold_live, scratch/J-run.54028 pushes 847 cold_live and 696 cold_rest - but both those runs drain to an empty frontier with the close open, so no certificate can turn on their order. The only stored runs that end with work unfired are the three e029 arms (close VERIFIED with 2,892 / 2,953 / 2,901 jobs still queued), and those never schedule a cold pass at all. So there is no run in the corpus where the cold price can change which tiles certify. I also sharpen the head-to-head the reader leans on: because holo2's gate is inert at one worker (see pricing-01), the measured 44%/36% versus 53%/44% first-cold-fire positions at --workers 1 are a PRICE effect, not a gate effect - which strengthens 'the plain ladder reproduces the ordering' rather than merely illustrating it. Finally, the 1,356-versus-1,360 pair the reader cites is a page-domain result, not a cold-price result: no cold pass fired in either arm, so it licenses 'ordering changes certificates at a preempting close' generally, not anything about 250/260.

---

### pricing-03 — COST_PAYLOAD = 20 — payload is the cheapest recovery and undercuts every placement rung

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: B06, B47

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Whether a tile whose evidence has arrived is decoded before more windows are placed — i.e. whether certificates (and with them the close consult and the done gate) exist early in a run at all.

**holo2.** A payload attempt costs 20 plus its lane term, so at the deepest realistic ladder it is 20 + 2*4 = 28, still under the cheapest placement rung (40). The constant was AMENDED from 40 after a real nine-platen run measured payload starving above placement. Both feedback loops (close preemption and the done projection) depend on it.

*Where:* `holo2/src/holo2/engine/recipe.py:191-214`; `holo2/src/holo2/engine/recipe.py:589`; `holo2/tests/engine/test_cost_vocabulary.py:60-110` · *dial:* live

**holo3.** All three ordinary payload rows declare PAYLOAD_COST 20 and add RUNG_COST 2 per rung, so the whole payload band is 20..28 and sits under place's ring at 40. tiles.retry is priced identically to tiles.scan — a retry is ordinary work in holo3, not re-work.

*Where:* `holo3/plugins/tiles.py:66-69`; `holo3/plugins/tiles.py:749-751`; `holo3/plugins/tiles.py:774-776`; `holo3/plugins/tiles.py:811-816`

*Scheduler row / doc:* SCHEDULE.md:63-65 (tiles.retry / tiles.scan / tiles.union all at 20, marked same-price round-robin peers)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo2) payload above placement starves: 2,529 ready workers, 1,287 armed payload, 431 fires, ZERO tiles attempted, zero certified; COST_PAYLOAD = 20 undercuts every placement rung (20 + 2*4 == 28 < 40) — *artefact:* ARTEFACTS.md:722
- (holo3) (20, 'tiles.retry', 'payload'), (20, 'tiles.scan', 'payload'), (20, 'tiles.union', 'payload') — *artefact:* holo3/tests/test_h3_schedule.py:22-24 (LADDER_GOLDEN); first-fire price pinned at :157-192

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The interleave property (payload at any realistic depth under every placement tier) is separately pinned on holo2 (test_cost_vocabulary.py:93-110) and holds arithmetically on holo3 by the same numbers. The retry half of the band differs in its aging, not its base price — see pricing-09.

*Refuter (upheld):* *Corrections:* Citation off by one: the three 20-priced payload rows are holo3/tests/test_h3_schedule.py:23-25 (line 19 is survey at 10), not :22-24. Everything else verified: holo3/plugins/tiles.py:67 PAYLOAD_COST=20, :751/:776/:814-815 all add RUNG_COST*rung; holo2/src/holo2/engine/recipe.py:214 COST_PAYLOAD=20 with the amendment comment at :191-213; the interleave pin holo2/tests/engine/test_cost_vocabulary.py:93-110 exists; the starvation number resolves at ARTEFACTS.md:722.

*Reason:* Constants, formula and both pins verified identical; only a line citation slipped.

---

### pricing-04 — COST_INGEST = 10 — a declared scan converted to its resolution ladder as priced work vs holo3's up-front intake

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B07

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a second or third capture's conversion overlaps decoding of the first, or blocks it; and how much raster is resident before any job runs.

**holo2.** Each declared scan is minted as one ingest descriptor priced at 10, below every other class, because it is the work that creates all other work. The provider's derivation chain admits scan N+1 only once scan N's record stands, so exactly one survey is in flight whatever the pool width and the raster transient is bounded without a gate. A pooled run therefore overlaps the next capture's conversion with placement on the capture that just landed.

*Where:* `holo2/src/holo2/engine/recipe.py:168-177`; `holo2/src/holo2/engine/recipe.py:580` · *dial:* live

**holo3.** Intake is not a scheduled row at all: `_start` calls `_intake_run` once and converts every declared scan to its full ladder of per-plane rasters before the frontier exists, then folds the Captures. The cheapest priced row is `survey` at a flat 10, one fire per capture. So the 10 survives as a price; the streaming property does not.

*Where:* `holo3/engine.py:102-109`; `holo3/engine.py:229-247`; `holo3/plugins/intake.py (ingest_captures)`; `holo3/plugins/survey.py:30-31`; `holo3/plugins/survey.py:807-809`

*Scheduler row / doc:* SCHEDULE.md:59 (survey, price 10, the cheapest row); SCHEDULE.md:339-341 'Ingest converts each scan into the resolution ladder and the survey finds the printed regions'

**Implementation delta.** holo2 mints one priced descriptor per scan and lets the pool interleave conversion with decoding, one capture in flight at a time. holo3 does all conversion serially in `_start`, before the first job, and prices only the survey. Inputs differ (holo2: a declared scan is a work subject; holo3: captures are constructor input), when it fires differs (holo2: any time the queue reaches 10; holo3: before the loop), and the memory shape differs (holo3 holds every capture's ladder for the whole run; holo2's transient is one capture wide).

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) survey 1 job, 8.51 cpu-s of 1,639.8 cpu-s total on the one-capture e029 default-domain run (the intake conversion itself is not accounted in any plugin row) — *artefact:* scratch/page-domain-qual/merged-default.log, licensed at ARTEFACTS.md:104 and ARTEFACTS.md:734
- (holo2) no ingest wall or memory number of its own; the nearest record is the prepared-planes doctrine (ingest ~19.5 GB resident; workers-8 and workers-4 both SIGKILLed on a 64 GB machine while serial survived) — *artefact:* ARTEFACTS.md:668-672

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's, and record the gap. What would settle it: a multi-capture holo3 run already writes per-plugin cpu in report.json but attributes nothing to intake, so the discriminating number is a wall split on an existing multi-capture invocation (e.g. the sheet-H four-capture argv at ARTEFACTS.md:256) — a receiver run, therefore out of scope for this campaign; the cheap alternative is one instrumented line in `_start` on the next real decode.

**Notes.**

*Reader:* Relevant to memory, not only order: holo3's largest colour runs already sit near the machine's kill line (step 4 breached at both workers 8 and workers 6, ARTEFACTS.md:737), and up-front intake of every capture's ladder is one contributor the artefacts cannot separate (G-25). This row does NOT claim a yield effect; on a single-capture run the two designs are indistinguishable.

*Refuter (upheld):* *Corrections:* None load-bearing. Verified: holo3/engine.py:229 calls `_intake_run` inside `_start` before the frontier exists, holo3/engine.py:102-109 delegates to plugins/intake.ingest_captures, and holo3/engine.py:230-232 keeps every capture's rasters resident for the run (`self._rasters`, `_planes_by_lane`); survey is a flat 10 with no rung term (holo3/plugins/survey.py:29-31, :807-809). holo2's ingest entry is RecipeEntry(TASK_INGEST, …, COST_INGEST) at holo2/src/holo2/engine/recipe.py:580 with the streaming rationale at :168-177. Optional precision: cite survey.py:29-31 rather than :30-31 (STAGE_SURVEY is on :29).

*Reason:* The streaming-vs-up-front delta and the UNPROVEN status are both correct at HEAD.

---

### pricing-05 — COST_CALIBRATION = 15 — a context/photometry fit undercuts the tiles it improves

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B08

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Whether a region's tiles are decoded with a calibrated detector the first time, or marginal-then-re-armed.

**holo2.** The ctx fit entry is priced at 15, between ingest (10) and payload (20), so on every lane it runs before the tiles it corrects. A premature fit refuses cheaply on the carried pool floors. Refits are deliberately not special-cased: they enter the general re-work band through work_price.

*Where:* `holo2/src/holo2/engine/recipe.py:178-190`; `holo2/src/holo2/engine/recipe.py:585-586` · *dial:* live

**holo3.** calibrate and ctx both charge 15 + 2 per rung. holo3 adds a third row at the same price: colour lane ASSEMBLY (first evidence for placed windows the lane has never covered) also costs 15 + rung, however many times it happens, because it is first work. The three are declared round-robin peers.

*Where:* `holo3/plugins/calibrate.py:59-61`; `holo3/plugins/calibrate.py:730-732`; `holo3/plugins/calibrate.py:748-750`; `holo3/plugins/color_region.py:59-63`; `holo3/plugins/color_region.py:719-730`

*Scheduler row / doc:* SCHEDULE.md:60-62 (calibrate, color, ctx — three same-price peers at 15); SCHEDULE.md:150-171 (colour assembly always costs 15 + rung)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) (15, 'calibrate', 'calibrate'), (15, 'color', 'calibrate'), (15, 'ctx', 'calibrate') — all marked shared-price peers — *artefact:* holo3/tests/test_h3_schedule.py:19-21
- (holo2) COST_CALIBRATION = 15, pinned to sit between ingest and payload — *artefact:* holo2/tests/engine/test_cost_vocabulary.py:363 (test_calibration_sits_between_ingest_and_payload)
- (holo3) e029 default-domain run: calibrate 3,168 jobs / 22.38 cpu-s, ctx 92 jobs / 215.01 cpu-s (2.34 cpu-s per fire at price 15, 46.0 fires per subject) — *artefact:* scratch/page-domain-qual/merged-default.log, licensed at ARTEFACTS.md:104/:734

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The constant is carried; the REFIT half is not (holo2 ages refits into the 90+ band, holo3 does not) — that delta lives in pricing-09. The churn line above shows the untamed refit population on a real sheet: 46 fires per ctx subject, 215 cpu-s, at a price that never rises.

*Refuter (upheld):* *Corrections:* Citation off by one: the three 15-priced rows are holo3/tests/test_h3_schedule.py:20-22, not :19-21 (line 19 is survey at 10). Numbers re-read from the artefact and exact: scratch/page-domain-qual/merged-default.log 'calibrate 3168 22.38', 'ctx 92 215.01', churn 'ctx: 2.34 cpu-s/fire at price 15 · 46.0 fires/subject'. holo2 pin test_cost_vocabulary.py:363 exists as named.

*Reason:* Constant, position in the scale and both pins verified; one citation slipped by a line.

---

### pricing-06 — LANE_COST_PER_RUNG = 2 — footing progression as a price, not a gate

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B09

Classification trail: reader CARRIED-IDENTICAL → refuter upheld → second lens CARRIED-IDENTICAL.

**What it decides.** That a coarse rung's work is tried before the same work on a finer rung, without any phase or barrier machinery.

**holo2.** Every ordinary tier adds 2 per rung of depth above its capture's coarsest lane. The term is deliberately small: the deepest realistic ladder is five rungs, so it spans 8, and 8 + the 5-point child premium is under the smallest inter-tier gap of 20 — it reorders within a tier and never across one. It replaced a `quiescent` gate that held finer footings closed.

*Where:* `holo2/src/holo2/solve/place_tiers.py:102-120`; `holo2/src/holo2/solve/place_slot.py:216-217`; `holo2/src/holo2/solve/payload.py:317-336` · *dial:* live

**holo3.** The same value 2 is declared once in place.py for placement and separately in each payload/calibration/colour plugin as its own RUNG_COST, and added to the level index (0 = coarsest, ladders are asserted strictly ascending in ppc). Same size, same role, same non-crossing property against the 20-point gaps.

*Where:* `holo3/plugins/place.py:50`; `holo3/plugins/place.py:85-89`; `holo3/plugins/tiles.py:68`; `holo3/plugins/calibrate.py:60`; `holo3/plugins/color_region.py:61`

*Scheduler row / doc:* SCHEDULE.md:344-347 ('Coarse rungs pay +2 per rung less than fine ones, so the whole sheet places coarse-to-fine without any phase machinery')

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) '12-7 keep LANE_COST_PER_RUNG=2' (build contract pin); first-fire price at rung 0 pinned per row — *artefact:* holo3/conversion_docs/00-contract.md:297; holo3/tests/test_h3_schedule.py:157-192
- (holo2) the lane term never crosses an ordinary inter-tier gap — *artefact:* holo2/tests/engine/test_cost_vocabulary.py:111-158

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* holo3 restates the literal 2 in six modules rather than importing one name (place.py:50, tiles.py:68, calibrate.py:60, color_region.py:61, fields.py:60, uplift.py:93, local_ctx.py:96, plane_k.py:120, swim.py:107). Nothing pins them equal to each other; a future edit could fork one silently. Worth a comment-carry note, not a ruling.

*Refuter (upheld):* *Corrections:* The note undercounts its own list. There are NINE spellings of the literal 2, not six: holo3/plugins/place.py:50 (LANE_COST_PER_RUNG), calibrate.py:60, color_region.py:61, fields.py:60, tiles.py:68, uplift.py:93, local_ctx.py:96, swim.py:108 (not :107), plane_k.py:120 (all `RUNG_COST: int = 2`). Nothing pins them equal — confirmed: holo3/tests/test_h3_descriptor.py:94-99 pins that the ENGINE owns none of these names, which is the opposite guarantee. Change 'six modules' to 'nine modules' and fix swim.py:107 -> :108.

*Reason:* Value, role and non-crossing property carried; the fork-risk note has the wrong count and one wrong line.

*Second lens (final: CARRIED-IDENTICAL):* Upheld, and the refuter's count correction is right: there are nine spellings of the literal 2, not six - holo3/plugins/place.py:50 (named LANE_COST_PER_RUNG) plus RUNG_COST in calibrate.py:60, color_region.py:61, fields.py:60, tiles.py:68, uplift.py:93, local_ctx.py:96, swim.py:108 (the reader wrote :107) and plane_k.py:120. Nothing pins them equal to each other. Two things the first pass missed that belong on this row. First, the non-crossing guarantee holo2 pins is stated against 20-point gaps, and holo3's ladder now has 10-point gaps among its dear rows (160/170/180 and 210/220/230/240): a five-rung ladder spans 8, so the property still holds, but the margin fell from 7 to 2 and a six-rung ladder would break it, with no test watching. Second, one row has no rung term at all - holo3/plugins/color_pooled.py:190 returns POOLED_CTX_COST * attempts and nothing else - so within a page its footings are priced equal and ordered by arrival instead of coarse-first. Neither changes the carry verdict; both are holo3-only facts worth recording. The 5-point gap between calibration at 15 and payload at 20, which the lane term does cross at depth 3, is NOT a delta: holo2 has the identical two constants (recipe.py:190 and :214) and the identical term.

---

### pricing-07 — COLD_COST_PER_RUNG = 20 — cold's rung is a real price, and rest(d) < live(d+1)

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B10

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** That both cold flavours of one rung are asked before the next rung's first, so a sheet's cheap correlation questions are exhausted before dearer ones.

**holo2.** Cold's rung term is 20, ten times the lane term, because a cold fire IS its transform and a finer rung buys a strictly worse deal for the same arithmetic. At 140/150 the property holds: rest(d) = 150 + 20d < 160 + 20d = live(d+1). Spelled twice (solve and engine) with a data test pinning them equal.

*Where:* `holo2/src/holo2/solve/place_tiers.py:122-133`; `holo2/src/holo2/engine/recipe.py:228-239` · *dial:* live

**holo3.** COLD_COST_PER_RUNG = 20, applied by the same `stage_price` branch on COLD_STAGES. At the repriced 250/260 the ordering property survives unchanged: rest(d) = 260 + 20d < 270 + 20d = live(d+1), and with the child premium the four prices of a rung still ascend without crossing into the rung above.

*Where:* `holo3/plugins/place.py:51`; `holo3/plugins/place.py:85-89`

*Scheduler row / doc:* SCHEDULE.md:81-82

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo2) a rung's four cold prices ascend and never cross the next rung — *artefact:* holo2/tests/engine/test_cost_vocabulary.py:234-271
- (holo3) COLD_COST_PER_RUNG 20 declared in the contract cost table alongside LANE 2 and CHILD 5 — *artefact:* holo3/conversion_docs/00-contract.md:317-319

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The constant carries; the base prices it rides on do not (pricing-02). holo3 has no test asserting the rest(d) < live(d+1) relation — the holo2 pin has no counterpart; the ladder golden pins the base prices only. Worth one line in the comment carry.

*Refuter (upheld):* *Corrections:* The note ('holo3 has no test asserting the rest(d) < live(d+1) relation … the ladder golden pins the base prices only') understates what is pinned. holo3/tests/test_h3_plugins_placement.py:102-103 asserts stage_price('cold_live',1,0) - stage_price('cold_live',0,0) == place.COLD_COST_PER_RUNG, and :90-94 goldens cold_live 250 / cold_rest 260 — so both inputs to the relation are live pins and rest(d)=260+20d < 270+20d=live(d+1) follows arithmetically. Only the RELATION itself is unasserted, which is a much smaller gap than the note claims. Verified otherwise: holo3/plugins/place.py:51 COLD_COST_PER_RUNG=20 applied by the COLD_STAGES branch of stage_price (:85-89); holo2 place_tiers.py:133 + the pin at test_cost_vocabulary.py:234-271.

*Reason:* Constant and property carried; the 'nothing pins it' note is too strong against test_h3_plugins_placement.py.

---

### pricing-08 — CHILD_PREMIUM = 5 — a subdivision child pays a little more at every rung

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B11

Classification trail: reader CARRIED-IDENTICAL → refuter upheld → second lens CARRIED-IDENTICAL.

**What it decides.** That any whole window's pass at a rung outranks any child's pass at the same rung: the sheet is exhausted before it is specialised.

**holo2.** A child pays +5 on top of its rung term, so the two stack; 8 (deepest lane span) + 5 = 13 fits inside one 20-point inter-tier gap, which makes 'exhaust before specialising' provable rather than hoped. The 2026-08-18 reversal extended the premium to the cold pair as well.

*Where:* `holo2/src/holo2/solve/place_tiers.py:216-240`; `holo2/src/holo2/solve/place_slot.py:216-217` · *dial:* live

**holo3.** CHILD_PREMIUM = 5 added by the same expression whenever the window's depth is non-zero, cold stages included. Identical value, identical stacking, identical reach.

*Where:* `holo3/plugins/place.py:52`; `holo3/plugins/place.py:85-89`

*Scheduler row / doc:* SCHEDULE.md:66-82 (the place rows; the premium is inside `stage_price`, not a separate ladder row)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo2) the child premium is the only thing depth adds; it stacks on the lane term — *artefact:* holo2/tests/engine/test_cost_vocabulary.py:272-339
- (holo3) CHILD_PREMIUM 5 in the contract cost table — *artefact:* holo3/conversion_docs/00-contract.md:317-318

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Subdivision itself (when a child is born) belongs to the placement family; this row is the price only. No holo3 test pins the stacking property.

*Refuter (upheld):* *Corrections:* THE NOTE IS FALSE AS WRITTEN. 'No holo3 test pins the stacking property' — holo3/tests/test_h3_plugins_placement.py:96-101 asserts, for EVERY stage in place.STAGE_COST including both cold flavours, that stage_price(stage, 0, 1) == stage_price(stage, 0, 0) + place.CHILD_PREMIUM. That pins the premium's value, its reach to cold (the 2026-08-18 reversal) and its additivity. What is genuinely unpinned is (a) the premium stacking WITH a non-zero lane depth (no test evaluates stage_price(stage, d>0, 1)) and (b) the 8+5=13 < 20 bound that makes 'exhaust before specialising' provable. Rewrite the note to say that. Constant verified: holo3/plugins/place.py:52 CHILD_PREMIUM=5, added by the `+ (CHILD_PREMIUM if depth else 0)` term at :85-89; holo2 place_tiers.py:240 with the reversal comment at :216-239.

*Reason:* Classification right, but the row's 'nothing is pinned' note is refuted by a test in the same suite it cites elsewhere.

*Second lens (final: CARRIED-IDENTICAL):* Upheld, and the refuter is right that the reader's note is false as written: holo3/tests/test_h3_plugins_placement.py:99-101 asserts for every stage, cold included, that a child's price is the whole window's price plus the premium, which pins the value, the additivity and the reach to cold. What is genuinely unpinned is the premium stacked on a non-zero footing term and the 8+5<20 bound. I add the check neither pass made, which is the one that could have been broken by the cold reprice: holo2's cold-pair stacking property is that a child's live sits under its own footing's rest and a child's rest sits under the next footing's live. Under holo3's 250/260 with the same +20 per footing and the same +5, that is 255 < 260 and 265 < 270 - the property survives the reprice intact, so the 2026-08-18 reversal is carried in substance and not only in the constant. Verified at HEAD: holo3/plugins/place.py:52 CHILD_PREMIUM = 5, applied by the '+ (CHILD_PREMIUM if depth else 0)' term at :85-89; holo2/src/holo2/solve/place_tiers.py:240 with the reversal recorded at :216-239.

---

### pricing-09 — The rework/aging band max(base, 90 + 5*(n-1)) + premium — a re-attempt's price grows with its own spend history

**ABSENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B12, B08, B47

Classification trail: reader ABSENT → refuter upheld → second lens ABSENT.

**What it decides.** How soon a job that already fired and failed is allowed to fire again, and therefore how much accumulated evidence each re-attempt gets. It is the only thing on either side that damps an unbounded re-arm loop.

**holo2.** A first attempt prices exactly as its class declares. Any re-attempt is LIFTED (max, never an addend) into a band starting at 90 and growing 5 per prior attempt, read at the WAKE off that descriptor's own durable (work_id, route) spend row. The first re-attempt lands between word rest and wide; the band crosses wide at the 7th, cold_live at the 11th and refine at the 23rd. It is deliberately unbounded — a per-key ceiling was proposed and REJECTED on the L7 ground that current evidence may reorder work but never narrow a domain.

*Where:* `holo2/src/holo2/engine/recipe.py:251-291`; `holo2/src/holo2/engine/recipe.py:379-420`; `holo2/src/holo2/engine/orchestrator.py:704-736`; `holo2/src/holo2/engine/worklist.py:107-121` · *dial:* live

**holo3.** There is no engine-side aging: `_push_worker` pushes at exactly `descriptor.cost(...)`. Eleven of the seventeen rows ignore the `attempts` argument entirely and re-fire forever at their declared price — including every payload row, calibrate, ctx, refine, refine.color, revisit and tiles.local. Six rows price their own re-runs multiplicatively instead (see pricing-19), which crosses cold on their SECOND fire rather than the 11th.

*Where:* `holo3/engine.py:298-326`; `holo3/plugins/tiles.py:749-751`; `holo3/plugins/tiles.py:811-816`; `holo3/plugins/calibrate.py:730-732`; `holo3/plugins/refine.py:663-665`; `holo3/plugins/local_ctx.py:597-599`

*Scheduler row / doc:* SCHEDULE.md:24-34 (the engine hands `attempts` and `last_cost` to the plugin and interprets neither) and SCHEDULE.md:543-546 (the aging formula deleted, 2026-08-29 ruling)

**Implementation delta.** holo2: one uniform engine rule over every queue-scheduled family, additive (+5/ordinal), floored at 90, read from a durable ledger, so a re-attempt is dearer than every word pass and eventually dearer than cold. holo3: no uniform rule; the door exists (`cost(store, subject, stage, attempts, last_cost)`) but the ordinary work rows do not walk through it, so a payload retry costs 20 + rung on its first fire and on its fiftieth, ahead of every placement pass every time.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) aging: attempts 1,248 -> 760 (-39%), BP-running 1,115 -> 588 (-47%); worst key 61 -> 22 BP attempts / 11,820 -> 4,260 iterations (-64%); certified 160 -> 160 UNCHANGED; heaviest certified lifetime 548 -> 17; wall 96.1 -> 49.1 s with 3 volumes VERIFIED byte-exact both sides — *artefact:* ARTEFACTS.md:724
- (holo2) aging on the real sheet: commits -37% / -41%, close verifies with 3,970 / 3,702 deferred re-attempts unfired — *artefact:* ARTEFACTS.md:725
- (holo2) band crossings: REWORK_BASE 90 + REWORK_STEP 5*(n-1) crosses wide at the 7th re-attempt, cold at the 11th, reaches COST_REFINE 200 at the 23rd — *artefact:* ARTEFACTS.md:726
- (holo3) deleting the inherited aging formula: 'The K sim is unmoved job for job; the colour sim re-interleaves its tail (retry 83 -> 52, scan 223 -> 208, color 21 -> 24 fires) for the same certificates' — payload bytes and certificate sets identical to the wave-0 baseline (49/49 and 279/279) — *artefact:* holo3/SCHEDULE.md:538-546 (the same generated section ARTEFACTS.md:283 licenses at :426-520; these lines sit just past that range)
- (holo3) e029, current tree, default page domain: tiles.scan 13,838 jobs / 403.08 cpu-s / 773 certs (6.9 fires per subject at price 20) and tiles.retry 6,003 jobs / 911.94 cpu-s / 583 certs (6.1 fires per subject at price 20) — together 19,841 of 23,855 jobs and 1,315 of 1,639.8 cpu-s; the --max-pages 1 arm reads 11.2 and 10.0 fires per subject — *artefact:* scratch/page-domain-qual/{merged-default,base-e029}.log, licensed at ARTEFACTS.md:104 and :734

**Yield relevance.** decides-certificates — source: reader, upheld by the second lens.

**Recommendation.** keep holo3's, and record the cost honestly. The user's 2026-08-29 ruling is explicit that the engine may not age cost ('cost is a scheduling function, nothing the engine itself determines or influences', DESCRIPTOR-PLAN.md:218-227), and holo2's own measurement says aging bought CPU at zero yield on its corpus — so porting it back would be re-opening a ruling, not closing a gap. What the map should carry instead: the re-fire population is large and untamed on a real holo3 sheet (6-11 fires per payload subject, 42-46 per ctx subject), and if that cost is ever worth damping, the escalation door already in the descriptor signature is where it belongs — in the plugins' own cost(), never back in the engine.

**Notes.**

*Reader:* Two honesty caveats. (1) holo2's 'zero yield cost' is measured on holo2's tree and corpus; nothing measures what aging would cost holo3, where a preempting close ends the run and deferring a cheap payload re-attempt behind the word bands can change which certificates exist at that moment. (2) holo3's own deletion evidence is sim-only (49/49 and 279/279 certificates); no real-sheet A/B of the aging deletion exists on either tree. A costed settlement would be one e029 decode with a rework term restored in the payload rows' cost() versus the current tree — a real-capture receiver run (~5-10 min each on holo3 per ARTEFACTS.md:104's 1,639-2,517 cpu-s), i.e. out of scope for this campaign.

*Refuter (upheld):* *Corrections:* ABSENT is right and the mechanism reading is exact (holo3/engine.py:298-308 pushes at descriptor.cost() with no lift; holo3/tests/test_h3_schedule.py:113 REWORK_GONE + :195-200 pin the engine owns no pricing name; DESCRIPTOR-PLAN.md:218-229 is the ruling; D6-EXECUTION.md:111-119 the reconciliation). ONE NUMBER IS MISLABELLED: 'the --max-pages 1 arm reads 11.2 and 10.0 fires per subject' — 11.2/10.0 are the BASE (pre-merge tree) arm, scratch/page-domain-qual/base-e029.log. The actual --max-pages 1 arm (merged-null.log, argv confirms the flag) reads tiles.scan 10.8 and tiles.retry 10.3 fires/subject (ctx 44.5, calibrate 13.4). pricing-14 labels the same pair correctly as 'base arm', so the two rows currently contradict each other. All other counts re-derived from merged-default.log and exact: 13,838+6,003 = 19,841 of 23,855 jobs; 403.08+911.94 = 1,315.02 of 1,639.8 cpu-s. Verified 11 of 17 rows ignore the attempts argument, by name: survey, place, calibrate, ctx, tiles.scan, tiles.union, tiles.retry, tiles.local, refine, refine.color, revisit.

*Reason:* Row and recommendation hold; one cited fire-count pair belongs to a different arm than the label says.

*Second lens (final: ABSENT):* Upheld as ABSENT, and I confirm the refuter's label correction - 11.2 and 10.0 fires per subject are the base (pre-merge) arm in scratch/page-domain-qual/base-e029.log; the --max-pages 1 arm reads 10.8 and 10.3, and the default-domain arm 6.9 and 6.1. This is the one row in the family whose difference can change which tiles certify on the corpus we hold, and my reason is sharper than the reader's. Of every stored run, exactly three end with work unfired - the three e029 arms close VERIFIED with 2,892 / 2,953 / 2,901 jobs still queued - and those arms are made almost entirely of the very population holo2's aging band would have damped: tiles.scan and tiles.retry are 19,841 of 23,855 jobs and 1,315 of 1,639.8 CPU-seconds on the default arm, every one of them priced at 20 whether it is that subject's first fire or its eleventh. Lifting a re-fire into a 90-and-rising band would put it behind the word routes, so at the instant the payload verifies a different set of tiles would have been read. The corpus already shows the size of such an effect: a scheduling change that fires no cold pass at all still moved the count 1,360 -> 1,356 on the same capture with the payload byte-exact. I also add a second stale document the reader missed: holo3/conversion_docs/00-contract.md:319 still declares 'REWORK max(tier, 90+5*(n-1))' as a build pin, alongside 13-engine-diag-cli.md:118 - while the tree has no rework name at all and a test forbids one.

---

### pricing-10 — Placement takes no aging term, structurally

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: B13

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** That a window's repeated placement passes are bounded by its own ladder and tried set rather than by a growing price.

**holo2.** The re-work ordinal is a spend-ledger quantity, and the placement WorkSource spends nothing at the wall, so the ordinal is undefined for it. The engine expresses this without any family knowledge: a spend row is built only when `armed.source is None`. Placement repetition is bounded by the ready bit and the tried set instead.

*Where:* `holo2/src/holo2/engine/recipe.py:408-420`; `holo2/src/holo2/engine/orchestrator.py:630-631`; `holo2/src/holo2/solve/place_tiers.py:65-69` · *dial:* live

**holo3.** `_place_cost` takes `attempts` and ignores it: a window's price is its stage, its lane depth and its child premium, nothing else. Repetition is bounded by the stage ladder (each stage spends once), the per-page cold tried ids and the retire predicates.

*Where:* `holo3/plugins/place_sched.py:259-262`; `holo3/plugins/place.py:85-89`

*Scheduler row / doc:* SCHEDULE.md:66-82 (place's six stage prices carry no ordinal mark)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) escalating rows golden = {color, color.pooled_ctx, fields, tiles.uplift, tiles.planek, tiles.swim} — place is not among them — *artefact:* holo3/tests/test_h3_schedule.py:45-47 + :210-217

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The two sides reach the same behaviour from opposite directions: holo2 because placement has no spend row, holo3 because no row ages unless it prices its own ordinal. Trivially preserved.

*Refuter (upheld):* *Corrections:* None. Verified: holo3/plugins/place_sched.py:259-262 takes `attempts` and never reads it; holo3/tests/test_h3_schedule.py:45-47 + :210-217 derive the escalating set by AST and place is not in it; holo2/src/holo2/engine/recipe.py:408-420 makes the ordinal a spend-ledger quantity and place spends nothing (seed B13).

*Reason:* Same behaviour on both sides, reached by different routes; the golden named exists at HEAD.

---

### pricing-11 — COST_REFINE = 200 — pose re-work priced at the top, 'after the ladder' as an emergent property

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B14

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** When a certificate-labelled pose revision (and, in holo3, the mop-up and colour refinement rows that share its price) is allowed to fire relative to placement, payload and cold work.

**holo2.** The refine entry declares 200, above cold_rest (150), the dearest tier any other family declares, and is NOT gated — the price alone makes 'after the ladder' emergent instead of a phase. A refine descriptor carries the ordinary lane term (200 + 2d), and the entry's own comment prints the crossover table: refine is overtaken by cold_rest from rung 3 and cold_live from rung 4, both reachable at 4800 dpi, and the aging band lifts other families past 200 from their 24th re-fire.

*Where:* `holo2/src/holo2/engine/recipe.py:293-376`; `holo2/src/holo2/engine/recipe.py:597`; `holo2/src/holo2/solve/refine.py:637` · *dial:* live

**holo3.** REFINE_COST 200, flat: no lane term, no ordinal, and three rows share it as declared round-robin peers (K refinement, colour refinement, the mop-up revisit row). Because cold now costs 250/260, refine precedes every cold pass at every rung unconditionally — the property holo2 could only claim through rung 2.

*Where:* `holo3/plugins/refine.py:68-69`; `holo3/plugins/refine.py:663-665`; `holo3/plugins/color_refine.py:59`; `holo3/plugins/color_refine.py:463-465`; `holo3/plugins/revisit.py:131-133`

*Scheduler row / doc:* SCHEDULE.md:73-75 (refine / refine.color / revisit, three same-price peers at 200); SCHEDULE.md:391-407 'How this keeps the spirit of v1'

**Implementation delta.** Same constant, three differences. (1) holo2 adds the lane term (200 + 2d) so refine subjects on coarse rungs go first; holo3 is flat, so refine subjects fire FIFO within the price. (2) holo2's refine re-attempts age past 200 from the 24th re-fire; holo3's never move. (3) The crossover with cold disappears in holo3 because cold was repriced to 250/260 — holo2's own pin records that inversion as OPEN for the user, and holo3's reprice closes it in the direction the ruling wanted.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) refine outranks every declared tier cost and every ordinary pass at every depth; cold_rest overtakes it from rung 3 and cold_live from rung 4 (MAX_LANE_DEPTH = 4, reachable at 4800 dpi) — *artefact:* holo2/tests/engine/test_cost_vocabulary.py:404-470
- (holo3) (200, 'refine', 'refine'), (200, 'refine.color', 'refine'), (200, 'revisit', 'refine') — marked shared-price peers — *artefact:* holo3/tests/test_h3_schedule.py:33-35
- (holo3) across the five completed post-change volumes `refine` fired 717 times, `refine.color` 3,899 and `revisit` 593, producing 0 route=refine poses — zero, everywhere — *artefact:* ARTEFACTS.md:528-531

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's. The flat price makes the ruled property unconditional and no artefact suggests the lane term ever mattered for refinement. What would settle the (1)/(2) deltas: nothing cheap — refinement adopted nothing at all on five volumes (ARTEFACTS.md:528-531), so its ordering is currently unobservable, and holo3's refinement writes no events (G-10). Record as UNPROVEN-because-unexercised rather than proposing a run.

**Notes.**

*Reader:* The zero-adoption finding is adjudicated as honest refusals rather than a stuck gate (POST-FORENSICS §A.1, ARTEFACTS.md:531-535). Yield-relevance is recorded as order-only for the PRICE; refinement's own yield is the refinement family's row.

*Refuter (upheld):* *Corrections:* None load-bearing. All three deltas verified: holo3/plugins/refine.py:663-665, color_refine.py:463-465 and revisit.py:131-133 all return a FLAT REFINE_COST (refine.py:68 = 200) with no rung term and no ordinal; holo2 mints its refine descriptor with premium=LANE_COST_PER_RUNG*footing_depth (holo2/src/holo2/solve/refine.py:634-637) and work_price lifts it past 200 from the 24th re-fire (recipe.py:379-420, comment :349-357). Ladder golden lines :33-35 are exact. The zero-adoption evidence resolves at ARTEFACTS.md:528-532 verbatim (717 / 3,899 / 593, zero route=refine poses).

*Reason:* Every claimed delta reproduced from current code; UNPROVEN-because-unexercised is the honest status.

---

### pricing-12 — The payload lane premium of a UNION attempt — dearest component vs shallowest rung ordinal

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B47

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Where a cross-capture union attempt sits inside the 20..28 payload band, i.e. whether it is decoded before or after the single-capture attempts on the same tile.

**holo2.** `lane_premium` takes the MAXIMUM depth over the footings the attempt will read, on the stated principle that 'an attempt is not cheaper than its dearest component'. A scan or a retry is scoped to one footing and takes that footing's depth; a union takes the max over the ppc's resident footings; an empty set answers 0.

*Where:* `holo2/src/holo2/solve/payload.py:317-336`; `holo2/src/holo2/solve/payload.py:933-970` · *dial:* live

**holo3.** `_union_cost` is PAYLOAD_COST + 2 * `store.union_rung_ordinal(ppc)`, and that helper returns the MINIMUM level index among the captures that reach this ppc. Scan and single-capture retry take the level index directly, exactly as holo2 does; only the union (and the union-origin retry, tiles.local, tiles.planek and tiles.swim, which reuse the same helper) take the min.

*Where:* `holo3/plugins/tiles.py:774-776`; `holo3/store.py:344-348`

*Scheduler row / doc:* SCHEDULE.md:65 (tiles.union at 20, the payload band)

**Implementation delta.** max over component depths (holo2) vs min over the captures' level indices for that ppc (holo3). On the ordinary case — every capture declared at one dpi — the two are identical, because one ppc sits at the same index on every ladder. They differ only on a MIXED-dpi stack, where the same ppc is a coarse rung of the finer capture and a fine rung of the coarser one: holo2 charges the dearest reading, holo3 the cheapest, so holo3 schedules cross-dpi unions earlier by up to 8 cost points inside a 20..28 band.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) first cross-dpi union certificates on paper: 1,508 of the 4,307 four-capture (2x1200 + 2x2400) sheet-H harvest — *artefact:* ARTEFACTS.md:622 (holo3/conversion_docs/MEASUREMENTS-2026-08-31.md:18-19)
- (holo2) cross-DPI union (1200 + 2400): 39 / 39 -> 41/64; joint = exact union of the two singles' sets — *artefact:* ARTEFACTS.md:620

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's, and record the delta. The whole payload band is 20..28 and sits under every placement rung on both sides, so the reordering is confined to payload work on mixed-dpi stacks; no artefact shows it mattering. If a ruling wants the stated principle back it is a one-line change (max instead of min) with a golden-price consequence for tiles.union/local/planek/swim.

**Notes.**

*Reader:* Mixed-dpi stacks are not hypothetical — the sheet-H four-capture and seven-capture runs are exactly this shape (ARTEFACTS.md:251-257). I could not find any comment in holo3 stating the intent of `union_rung_ordinal`; the name reads as 'the canonical rung of this ppc' rather than as a deliberate reversal of holo2's rule, so this may be an unnoticed drift rather than a decision.

*Refuter (upheld):* *Corrections:* max-vs-min verified exactly (holo2/src/holo2/solve/payload.py:334-336 `max(depths) if depths else 0`; holo3/store.py:344-348 `min(indices)`). TWO THINGS THE ROW UNDERSTATES, both from store.py:344-348. (1) `union_rung_ordinal(ppc)` iterates EVERY capture in the store, not the captures that reach THIS tile — holo2's max is over the footings the attempt will actually read. So on a mixed-dpi stack holo3's price can be set by a capture that is not a component of the attempt at all; the delta is wider than 'min instead of max over the same set'. (2) holo2 answers 0 for an empty footing set by an explicit and reasoned clause; holo3's `min([])` would raise ValueError. Neither changes the recommendation, but the delta paragraph should say both. Cross-dpi evidence resolves at ARTEFACTS.md:620 and :622, and the sheet-H four-capture shape (2x1200 + 2x2400) at ARTEFACTS.md:256.

*Reason:* Direction of the reversal confirmed; the scope of the reversal is larger than the row states.

---

### pricing-13 — Eligibility, not ordering, is the mechanism — no route sequencer for recovery work

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B48

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** That an attempt which may not run yet simply has no queued job, instead of sitting in a ladder waiting its turn. It bounds what the scheduler can be asked to order.

**holo2.** The payload provider's `expand` enumerates, per open work key, exactly the attempts the durable facts support: one scan per resident footing that observed the key, one union per ppc two distinct captures reached, one retry150 per footing whose own baseline ran a decoder and failed. Route order is never scheduled; 'writing a sequencer is a defect'.

*Where:* `holo2/src/holo2/solve/payload.py:881-931`; `holo2/src/holo2/solve/payload.py:933-970`; `holo2/src/holo2/core/work.py:60-71` · *dial:* live

**holo3.** Each recovery route is its own descriptor row born by a fact type (scan/union from evidence rows, retry/local/uplift/planek/swim from a failed AttemptFact), with a static stage and an `eligible` predicate; a job that may not run is never born or is refused at the pop. The one ladder that survives is `place`'s per-window stage bookmark, which both trees have.

*Where:* `holo3/descriptor.py:36-49`; `holo3/engine.py:387-408`; `holo3/engine.py:433-474`; `holo3/plugins/tiles.py:817-856`

*Scheduler row / doc:* SCHEDULE.md:6-12 ('births come from born_by + subjects_of … fire = retire -> version floor -> eligible -> prepare'); SCHEDULE.md:374-389

**Implementation delta.** Same law, different expression: holo2 derives a set of descriptors from durable facts at each refresh (one provider, a per-key memo on object identity); holo3 declares one descriptor per route whose `born_by` fact type is the derivation, and re-asks `eligible` at every pop. holo3's version is finer-grained — retry, local, uplift, planek and swim are five separate rows where holo2 had one payload family with three routes — which is what lets each carry its own price.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) certificate parity against holo1 on six full-harvest volumes: e029 1940/1940 matched 1940 miss 0; xerox K 1930/1924; c3-cmy7 720/786; c2-cmy8 5370/5422; c2-cmy7 1559/1586; sheet I 5297/5326 — *artefact:* ARTEFACTS.md:98, :121, :138, :153, :174, :231
- (holo3) 285 target addresses across five completed crop batteries, zero wrong certificates on either side — *artefact:* ARTEFACTS.md:317

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* No artefact isolates this rule on either side; the parity/battery numbers measure the composed receivers, and are cited here only to say the descriptor-per-route expression has not cost the tree its certificate sets. The gate holo3 deliberately dropped in this area — v1's close-readiness gate on retries — is the payload family's row, not this one (holo3/plugins/tiles.py:326-329, SCHEDULE.md:421-424).

*Refuter (upheld):* *Corrections:* None. Verified: holo3/descriptor.py:37-49 is the ten-field descriptor with `eligible`, `stage` and `cost`; holo3/engine.py:387-408 births workers from born_by/subjects_of; :445-460 re-asks retire/version/eligible/stage at the pop; holo3/plugins/tiles.py:324-328 `arms_retry` is the retry's derivation and SCHEDULE.md:356 states retries are never gated by close readiness. Minor: the retry-gate cite is tiles.py:324-328, not :326-329.

*Reason:* Same law, finer-grained expression; the parity numbers cited resolve and are correctly labelled as composed-receiver evidence.

---

### pricing-14 — The fire-count tripwire — max_fires_per_worker = 256, charged at arm time

**ABSENT** · evidence **UNPROVEN** · yield **integrity** · ruling needed **Y** · seeds: B61

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether a non-converging wake graph stops the run loudly or simply runs forever at cost.

**holo2.** Every fire is counted per rendered worker id and charged after the idle test and before dispatch, so a pool cannot outrun it; exceeding 256 raises FireCountTripwire and kills the run. It is declared as an observability tripwire, not a semantic bound: set well above the expected wake-graph depth so a non-converging fixpoint is loud instead of slow. Both admission sources are charged the same way.

*Where:* `holo2/src/holo2/engine/recipe.py:423-431`; `holo2/src/holo2/engine/orchestrator.py:505-537` · *dial:* live

**holo3.** Absent. `worker.attempts` is incremented and bucketed into a histogram (1 / 2 / 3-5 / 6-10 / >10) for the diag EngineStat, and the run summary prints cpu-s per fire and fires per subject, but nothing raises and nothing is bounded. A runaway wake loop would show as a growing '>10' bucket and be visible only to whoever is watching.

*Where:* `holo3/engine.py:46-54`; `holo3/engine.py:268-276`; `holo3/engine.py:278-296`; `holo3/engine.py:470-471`

*Scheduler row / doc:* no SCHEDULE.md paragraph; the observable is the diag `attempts_hist` and the run log's churn line (fires per subject)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) no artefact records the tripwire ever firing; its own comment calls it an observability tripwire rather than a semantic bound — *artefact:* holo2/src/holo2/engine/recipe.py:427-431
- (holo3) e029 default-domain run: ctx 46.0 fires per subject, calibrate 9.1, tiles.scan 6.9, tiles.retry 6.1 (base arm: 42.5 / 14.3 / 11.2 / 10.0) — *artefact:* scratch/page-domain-qual/{merged-default,base-e029}.log, licensed at ARTEFACTS.md:104/:734

**Yield relevance.** integrity — source: reader.

**Recommendation.** accept the loss. The measured fire counts on a real holo3 sheet peak around 46 per subject, an order of magnitude under holo2's 256, and holo3 already publishes the per-subject fire count in both the diag pane and the run summary. Porting it back would mean re-introducing an engine-side abort, which the same 2026-08-29 ruling that deleted the aging term pushed out of the engine.

**Notes.**

*Reader:* By the vocabulary this could be filed OUT-OF-FILTER as a safeguard; it is written as a full row because the brief names B61 and because the abort does change what a run produces (it ends it). Nothing in holo3 would notice a wake graph that fails to converge except the operator.

*Refuter (upheld):* *Corrections:* None. Verified: holo2/src/holo2/engine/recipe.py:423-431 PriceTable.max_fires_per_worker = 256 with the observability-tripwire comment; charged in orchestrator.py:519-538 `_charge`, after `_bind` and before dispatch, keyed on the rendered worker id, raising FireCountTripwire. holo3 has attempt_bucket at engine.py:44-52 and `_note_attempt` at :268-276 feeding the diag histogram only; nothing raises. The base-arm fire counts (42.5 / 14.3 / 11.2 / 10.0) are correctly attributed here — unlike pricing-09.

*Reason:* Absence confirmed in code; the 'accept the loss' recommendation rests on measured fire counts an order of magnitude under 256.

---

### pricing-15 — The tried-set floor — identical inputs never re-run — and whether that memory is durable

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **Y** · seeds: B48, B12

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a woken job actually fires. Within a run it is the only thing that stops a wake from re-running work on unchanged inputs; across a resume it decides whether a second pass re-does everything.

**holo2.** An attempt's identity is its whole read-set bound to the version of every key in it; the durable spend ledger refuses a repeat at the same identity and `fold_refusal` requires at least one read key to have ADVANCED (and none to have regressed) before a re-fire is lawful. Because the ledger is journalled, a resumed session does not re-run what a previous session spent.

*Where:* `holo2/src/holo2/core/identity.py:70-130`; `holo2/src/holo2/engine/orchestrator.py:539-559` · *dial:* live

**holo3.** One integer per bookmark: any touched subscription bumps `worker.version`, and a pop whose `tried_version == version` is skipped as stale. There is no durable spend memory at all — `--resume` folds a fact snapshot through the ordinary `_ingest` path, which mints fresh bookmarks with fresh versions, so a resumed run re-offers every job and is bounded only by the done-geometry, certified-tile and decision-cell refusals.

*Where:* `holo3/descriptor.py:52-65`; `holo3/engine.py:410-424`; `holo3/engine.py:452-455`; `holo3/engine.py:251-266`; `holo3/snapshot.py:1-58`

*Scheduler row / doc:* SCHEDULE.md:374-389 ('Kept, now declarative: … the tried-set floor (identical inputs never re-run)'); API.md §9a, the lean resume

**Implementation delta.** Per-read-key versions with a monotone advance test and a durable ledger (holo2) vs one per-worker counter and no durable memory (holo3). Within a run the floors are equivalent in intent, but holo3's is coarser: any subscribed key moving re-arms the whole worker, where holo2 checks each key's version and refuses a re-fire in which nothing advanced. Across a resume they are opposite: holo2 would decline the spent work, holo3 deliberately re-offers it — which is what the e034 four-run chain is built on.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the e034 resume chain: 5543 -> 5866 -> 5866 -> 5880; run 3 is the control, +0 for 1,039 jobs / 4,193 cpu-s, still VERIFIED; run 4 adds the 4800 capture for +14 — *artefact:* ARTEFACTS.md:235
- (holo2) no artefact measures a holo2 resume that adds a capture; 'union on paper via an add-a-scan resume is unmeasured in BOTH trees' — *artefact:* ARTEFACTS.md:842 (G-32)

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's. The re-offer-everything resume is the mechanism the deepest read on record used (+323 on run 2, +14 on run 4 after a fourth capture), and its cost is measured and modest (run 3's control paid 4,193 cpu-s for +0). Record the trade rather than porting the ledger: a durable spend memory would have made the e034 chain cheaper and the sheet-J resumes too, but it is the thing that would have to be built, not carried, since holo3 has no journal.

**Notes.**

*Reader:* SCHEDULE.md calls this 'the tried-set floor' in the v2-comparison section; the seed ledger uses the same words for a different mechanism (B15, the rival gate's 49 x (tried + offered) support floor), which belongs to the placement family. Both readings are legitimate; this row is the scheduling one.

*Refuter (upheld):* *Corrections:* Both sides verified: holo2/src/holo2/core/identity.py:73-79 (attempt_identity) + :108-129 (fold_refusal: no key may regress and at least one must advance) + orchestrator.py:552-556 (`ledger.is_spent` refusal); holo3/descriptor.py:53-65 (one `version`/`tried_version` pair per bookmark), engine.py:410-424 (`_touch` bumps version on any touched key), :452-455 (the stale skip), :251-266 (`_replay` folds the snapshot through the ordinary `_ingest`). ONE ADDITION worth carrying: holo3's `attempts` is equally non-durable, so on every resume each escalating row's ordinal restarts at 0 and the six dear rows re-fire at their base price — the e034 four-run chain (ARTEFACTS.md:235) is four fresh escalation ladders, not one. That is part of the same trade the row recommends keeping, and it is not stated anywhere in the map.

*Reason:* Within-run and across-resume deltas both reproduced; the e034 numbers resolve exactly.

---

### pricing-16 — One global cost order across two admission sources vs a single frontier

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B04, B05

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which of two competing heads the next fire is taken from — and therefore whether placement and everything else really compete on one scale.

**holo2.** Placement work is not descriptors: it lives in a separate WorkSource with its own heap, so admission compares two heads by cost and the cheaper wins, a tie going to the queue so the choice is a function of state rather than iteration order. The gated-tier rule is the one extra clause on top of that comparison.

*Where:* `holo2/src/holo2/engine/orchestrator.py:372-395`; `holo2/src/holo2/engine/worklist.py:136-151`; `holo2/src/holo2/solve/place_slot.py:219-225` · *dial:* live

**holo3.** There is one min-heap keyed (cost, seq, plugin, stage, subject) and one bookmark table; `place` is an ordinary descriptor row like the other sixteen. No second source, no tie rule, no gate clause: pop the cheapest, FIFO within a price.

*Where:* `holo3/engine.py:166`; `holo3/engine.py:298-326`; `holo3/engine.py:433-436`

*Scheduler row / doc:* SCHEDULE.md:6-12 and :337-373 — every plugin is a descriptor row and there is one frontier

**Implementation delta.** Two priced sources merged at admission (holo2) vs one priced heap (holo3). The cost order is the same order; what disappears is the tie-to-the-queue rule and the possibility of the two books disagreeing about what is cheapest. holo3's place row keeps the per-window stage bookmark that made holo2 want a separate source, but expresses it as `stage()` on one descriptor.

**Evidence status.** MEASURED

**Evidence.**

- (holo2 vs holo3) one 1000x1000-cell crop of the e029 sheet at two synthetic platen angles, four decodes: unresolved windows left 196/155 and 397/281; certificates 100/112 and 56/82; wall 1,370/842 s and 1,206/786 s; zero wrong certificates on either side, and at 0.80 deg holo3's certificate set is a strict superset of holo2's — *artefact:* ARTEFACTS.md:415-433

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The cited head-to-head measures the whole placement stack, not this rule alone; it is the only direct holo2-vs-holo3 comparison that exists and it runs in holo3's favour, so no reason to suspect a loss here.

*Refuter (upheld):* *Corrections:* None. Verified: holo2/src/holo2/engine/orchestrator.py:372-395 `_next` compares two heads, tie to the queue, with the gated clause as the one extra rule; holo3/engine.py:166 declares one heap and :313-316 pushes (cost, seq, plugin, stage, subject). The head-to-head table resolves verbatim at ARTEFACTS.md:415-425 (100/112, 56/82, 1,370/842 s, 1,206/786 s, strict superset at 0.80 deg).

*Reason:* One-frontier claim verified in code; the only direct comparison that exists runs in holo3's favour.

---

### pricing-17 — Queue mechanics of a re-price — lazy deletion plus a re-wake set vs one seat per bookmark and a pop-side re-price guard

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B12

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** How many stale queue entries a woken worker leaves behind, and whether a job can execute at a stage dearer than the price it was queued at.

**holo2.** `admit` re-prices on every wake and `push` reads the cost book at push time, leaving stale heap entries that `pop` and `head_cost` skip (lazy deletion). A worker whose own fire is still out is held in a re-wake set and re-delivered by `release` at the current price. Nothing re-checks the price at the pop.

*Where:* `holo2/src/holo2/engine/worklist.py:107-134`; `holo2/src/holo2/engine/worklist.py:178-182`; `holo2/src/holo2/engine/orchestrator.py:770-800` · *dial:* live

**holo3.** A bookmark holds ONE live heap entry (its seat, identified by the push sequence): a same-price re-push keeps the standing seat and its FIFO position, a re-price supersedes it, and a dead seat costs its pop one integer comparison counted as a stale skip. On top of that the pop re-asks `stage()` and refuses to fire when the fresh stage's cost exceeds the price the entry was popped at — it re-pushes instead.

*Where:* `holo3/engine.py:298-326`; `holo3/engine.py:433-466`; `holo3/descriptor.py:64-65`

*Scheduler row / doc:* SCHEDULE.md:601-642 'The endgame feeder fix (2026-08-30)'

**Implementation delta.** holo2 keeps every superseded push and pays the retire chain at each of their pops; holo3 keeps one seat per bookmark and adds a pop-side guard that holo2 has no equivalent of (holo2 arms whatever popped, at the price it was pushed with). The guard matters because holo3's place row walks a stage ladder under a single bookmark: without it a window queued at ring could execute a cold sweep.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the lazy-deletion frontier held ~300 entries per bookmark on the live sheet; at the measured endgame shape (5,344 certificates, 1,124 bookmarks) the same drain went 632.8 s -> 0.950 s; both sims byte-identical at workers 1 and 8 — *artefact:* holo3/SCHEDULE.md:601-642 (the section ARTEFACTS.md:283 licenses; these lines sit past the cited :426-520 range)
- (holo3) the clean colour sim's fire counts moved and a three-way control attributes every moved row to the compaction alone: colour 12 -> 9, place 684 -> 670, tiles.scan 291 -> 194, tiles.retry 140 -> 59, refine.color and revisit unmoved — 'those fires bought nothing this sim run kept' — *artefact:* holo3/SCHEDULE.md:634-642
- (holo2) 0 retired ids popped in 7,029 pops, measured across serial, pool and replay (the dead retirement re-test) — *artefact:* holo2/src/holo2/engine/worklist.py:22-23

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* holo3's own record says the compaction removed fires that 'bought nothing this sim run kept' — a sim, not a sheet, and the honest reading is that a stale cheap entry could in principle have adjudicated first and fired something. Certificate sets and payloads were byte-identical through the change, which is the strongest statement available.

*Refuter (upheld):* *Corrections:* Seat model verified exactly (holo3/engine.py:309-316: same-price re-push returns and keeps the seat, a re-price supersedes; :437-440: a dead seat costs one integer comparison counted as a stale skip). ONE PRECISION FIX: the pop-side guard at holo3/engine.py:461-465 does NOT compare against 'the price the entry was popped at' — it compares descriptor.cost(fresh_stage) against descriptor.cost(stage), BOTH recomputed with the current worker.attempts/last_cost, and re-pushes when the fresh stage is dearer. The two coincide today because attempts cannot change while a worker sits in the heap, but the row should describe what the code compares. Both SCHEDULE.md quotes (:601-642, :634-642) are verbatim and the honesty flag about them sitting past ARTEFACTS.md:283's licensed :426-520 range is correct.

*Reason:* Mechanism and numbers verified; the guard's operands are described loosely.

---

### pricing-18 — The within-price tie-break — nearest available seed distance vs arrival order

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B04

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which of several equally-priced placement passes runs first: the one nearest an already-placed neighbour, or the one that arrived first.

**holo2.** The placement heap key is (price, offered seed distance, arrival ordinal): within one price class the window with the closest committed-pose anchor goes first, and the arrival ordinal keeps anything from starving. That is the ruled R-A behaviour — Dijkstra-flavoured frontier growth along the most confident edges.

*Where:* `holo2/src/holo2/solve/place_slot.py:219-225`; `holo2/src/holo2/solve/place_sched.py:883-893` · *dial:* live

**holo3.** `offered` survives as a BOOLEAN only — it selects the ring stage when any untried consult exists — and the heap key is (cost, seq): pure FIFO within a price. No distance term reaches the scheduler, so equally-priced ring passes fire in the order their bookmarks were pushed.

*Where:* `holo3/plugins/place_sched.py:113-118`; `holo3/engine.py:313-318`

*Scheduler row / doc:* SCHEDULE.md:22 ('same-price rows are deliberate round-robin peers')

**Implementation delta.** A three-term heap key with the anchor distance in the middle (holo2) vs a two-term key (holo3). The information holo3 drops is real — the consult's own anchor ordering — and it is the one ordering rule of holo2's placement scheduler that has no holo3 expression.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) accepted consult distances 0.0 x24 / 0.9812 x18 / 1.0 x14; accepted rank is 0 on all 56 — the nearest offer won every time — *artefact:* ARTEFACTS.md:460
- (holo2 vs holo3) head-to-head on identical crops: certificates 100/112 (0.00 deg) and 56/82 (0.80 deg), holo3's set a strict superset at 0.80 deg; 'measured head-to-head on identical material holo2 is the worse of the two' — *artefact:* ARTEFACTS.md:415-425

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The mechanism (which anchors a consult offers, and in what order) belongs to the placement family reader; this row records only the SCHEDULING key. holo2's own measurement says the nearest offer won every accepted contest, which is what makes the ordering look valuable — but the only head-to-head measurement puts holo3 ahead without it, so I record no gap.

*Refuter (upheld):* *Corrections:* None. Verified: holo2/src/holo2/solve/place_slot.py:219-225 `sort_key` returns (price, distance, ordinal) and place_sched.py:883-893 pushes (cost, distance, ordinal, window_id); holo3/plugins/place_sched.py:113 reduces `offered` to a bool that only selects STAGE_RING, and the engine's key is (cost, seq, …) at engine.py:313-316. ARTEFACTS.md:460 quoted exactly.

*Reason:* The dropped middle term of the heap key is real and correctly stated; the no-gap conclusion rests on the one head-to-head.

---

### pricing-19 — The escalation door — plugin-owned multiplicative re-pricing on six rows, and the colour lane's own fit ordinal

**HOLO3-ONLY** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter reclassified to HOLO3-ONLY → second lens HOLO3-ONLY.

**What it decides.** How fast a row that a growing certificate frontier wakes again and again drifts behind cheaper work; and, for the colour lane, whether cheap assembly work is charged the escalation of a fit it never performed.

**holo2.** absent — holo2 has one uniform additive aging rule in the engine (pricing-09) and no per-family pricing at all; a provider cannot price its own re-runs.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** The engine hands `attempts` (the bookmark's fire ordinal) and `last_cost` to every cost function as DATA and interprets neither. Six rows use it multiplicatively: color re-fit 160 x head fits, pooled_ctx 170 x n, fields 180 x n, uplift 210/220 x n, planek 230 x n, swim 240 x n. The colour lane deliberately prices off its own store-held count of head FITS rather than fires, because assembly fires are fires and pricing off them starved colour payload work until placement was exhausted (defect fixed 2026-08-30).

*Where:* `holo3/descriptor.py:45`; `holo3/engine.py:306-308`; `holo3/plugins/color_region.py:719-732`; `holo3/plugins/color_pooled.py:188-190`; `holo3/plugins/fields.py:804-806`; `holo3/plugins/uplift.py:325-332`; `holo3/plugins/plane_k.py:665-673`; `holo3/plugins/swim.py:545-548`

*Scheduler row / doc:* SCHEDULE.md:24-34 (the door), :150-171 (colour assembly vs re-fit), :129-149 (uplift), :245-259 (fields), :261-335 (swim)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo3) escalating rows golden: color (160), color.pooled_ctx (170), fields (180), tiles.uplift (210, 220), tiles.planek (230), tiles.swim (240) — derived from each row's own cost function — *artefact:* holo3/tests/test_h3_schedule.py:45-47 + :210-217
- (holo3) with the escalation door open both sims keep the wave-0 payload AND certificate set (49/49 and 279/279, signatures byte-identical) and get them with FEWER fires (color 15 -> 12, tiles.scan 305 -> 291, tiles.retry 147 -> 140): 'the escalation collapses wake storms the flat price used to serve one at a time' — *artefact:* holo3/SCHEDULE.md:548-560
- (holo3) the sheet-H colour lane burned 38,512 CPU-s (31%) on an escalating-refit ladder that the repricing fix then killed — *artefact:* ARTEFACTS.md:736

**Yield relevance.** decides-order-only — source: reader, upheld by the second lens.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Two things a future reader should know. (1) Multiplicative escalation crosses the cold ceiling on the SECOND fire of every one of the six rows (160x2=320, 170x2=340, 180x2=360, 210x2=420, 230x2=460, 240x2=480, all above cold_rest 260), where holo2's additive band needed eleven re-attempts to pass cold — so a second visit to any residue row is genuinely last. (2) `last_cost` is passed to every cost function and read by NO plugin (verified by grep): half the door is dead parameter today.

*Refuter (reclassified):* *Corrections:* The classification word stands (holo2 has no analogue) but the BEHAVIOUR STATEMENT IS WRONG in two ways, and the second is a defect that belongs in RULINGS.md. (1) FIRST-PUSH ZERO PRICE. The engine pushes a newly born bookmark with worker.attempts == 0 (holo3/descriptor.py:59 default 0; holo3/engine.py:403-408 births then calls _push_worker; :470 increments only at dispatch). Four of the escalating rows guard that case — holo3/plugins/uplift.py:328-330, plane_k.py:672, swim.py:547 all read `base = COST * attempts if attempts else COST` — but TWO DO NOT: holo3/plugins/fields.py:806 `return FIELD_COST * attempts + RUNG_COST * subject[1]` and holo3/plugins/color_pooled.py:190 `return POOLED_CTX_COST * attempts`. Measured directly against the tree (env/bin/python, holo3.plugins): fields costs 0 at attempts=0 / 180 at attempts=1; color.pooled_ctx costs 0 at attempts=0 / 170 at attempts=1. So on their first push these two rows are the CHEAPEST work in the receiver — below survey's 10 — not the 180/170 the ladder advertises. Nothing catches it: holo3/schedule.py:escalating_prices is an AST scan, and holo3/tests/test_h3_schedule.py:157-192 ('a declared price is what the row charges on its FIRST FIRE') passes attempts=1, which is the second push. Both rows are colour-only (fields.py:_fields_subjects returns () for Family.K or a disabled dial; color_pooled requires >=2 captures), which is why no K log shows it. (2) THE 'SECOND FIRE' ARITHMETIC IS OFF BY ONE. With attempts = fires-so-far, fire n is queued at attempts = n-1, so for uplift/planek/swim fires 1 AND 2 both charge the base (210/230/240) and the cross above cold_rest 260 happens on the THIRD fire (420/460/480); for fields and pooled_ctx the sequence is 0 -> base -> 2*base, also crossing on the third. Only `color`, whose ordinal is store-held head fits (color_region.py:719-732), can cross on its second re-fit. Rewrite the note accordingly and add a RULINGS entry: 'is the fields / color.pooled_ctx first-push price of 0 intended, or a missing `if attempts else` guard?' — the one-line fix is to copy the guard the other four rows carry, and it would change the order in which colour multi-capture runs do their dearest work.

*Reason:* Two of the six escalating rows price at 0 on their first push, and the escalation bites a fire later than the row says.

*Second lens (final: HOLO3-ONLY):* HOLO3-ONLY stands and I confirm both of the refuter's corrections against the tree - and then confirm the first one from stored measurements, which neither pass did. The zero first price is real: holo3/plugins/fields.py:806 and color_pooled.py:190 omit the 'if attempts else' guard their four siblings carry (uplift.py:328-330, plane_k.py:672, swim.py:547), and the engine pushes a newly born worker with an attempt count of 0 (holo3/engine.py:403-408, incremented only at dispatch, :470). It is not only arithmetic - it is in the archive. The diagnostic churn line reports the MEAN price at which a plugin's jobs were dispatched (holo3/diag/readout.py:337), and those means match the unguarded sequence exactly: sheet I's first run reports the plane-field row at 6.0 fires per subject and mean price 452, which is the average of 0/180/360/540/720/900 plus the footing term (the guarded sequence would read 482), and the pooled colour context at 8.0 fires and mean 595, the exact average of 0 through 1190 in steps of 170. The second resume reports the plane-field row at '160 cpu-s/fire at price 2 - 1.0 fires/subject': a single 160-CPU-second fit dispatched at price 2, below survey's 10, the cheapest work in the receiver. In the same J run the guarded swim row reports mean 530, the exact average of 240/240/480/720/960 plus 2 - so the guarded and unguarded rows are distinguishable in one stored file. On yield the defect is bounded: a plane field is adopted only if it beats the standing one on certificate count (holo3/data.py:232, store.py:869-877), so an early thin fit is always superseded and cannot poison later evidence, and every colour run in the corpus drains. It costs one mistimed 96-364 CPU-second fit per subject per session, including on every resume, since the attempt count is session-local.

---

### pricing-20 — What the re-read after a pose revision costs

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B14

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** When the re-sample of a window whose pose was just revised actually happens relative to everything else.

**holo2.** The re-read is its own priced class, TIER_RESAMPLE, deliberately outside the placement ladder and priced at 200 — RF1's own number, because it is RF1's other half. Charging it less would let it preempt the ladder the revision itself waited behind; charging it more would split one mechanism across two places in the order. It carries the ordinary lane term and is not gated.

*Where:* `holo2/src/holo2/solve/place_tiers.py:90-98`; `holo2/src/holo2/solve/place_tiers.py:179-197` · *dial:* live

**holo3.** There is no re-read row and no re-read price. An adopted revision folds a Placement carrying the new affine, which bumps `pose_affine`; that wakes the window's `calibrate` worker, which re-samples at the ordinary calibration price of 15 + rung. The revised geometry is therefore read back near the front of the queue, not at the back.

*Where:* `holo3/plugins/refine.py:512-514`; `holo3/plugins/calibrate.py:730-732`

*Scheduler row / doc:* SCHEDULE.md:107-124 (the refine debt rows: 'An adopted revision folds as a Placement with route refine, which re-fires the whole colour lane … through the ordinary declared reads — no bespoke wiring')

**Implementation delta.** A dedicated 200-priced re-read tier (holo2) vs re-use of the ordinary calibrate row at 15 + rung (holo3). The delta is 185 cost points and a reversal of intent: holo2 deliberately keeps both halves of the refinement mechanism at the same place in the order, holo3 treats a revised pose as ordinary new geometry and re-reads it before almost everything else.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) re-read census: 239/239 and 255/255 `resampled`, no refusals; the re-read population is 269/1,228 e029 and 272/1,282 xerox windows carrying two committed poses — *artefact:* ARTEFACTS.md:563 and :555
- (holo3) no artefact: refine adopted zero revisions on all five post-change volumes, so the re-read has never fired on a measured holo3 run — *artefact:* ARTEFACTS.md:528-531

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's. Re-reading revised geometry early is defensible on its own terms (a corrected pose makes every tile it covers cheaper to decode), and the mechanism is currently unexercised, so there is nothing to measure. Record it so that if refinement ever starts adopting on paper, the price of its second half is a known, deliberate choice rather than an accident of re-use.

**Notes.**

*Reader:* The refinement family reader owns the mechanism (holo2's separate resample fire vs holo3's placement fold); this row covers only the price and is written to be merged with theirs.

*Refuter (upheld):* *Corrections:* None. Verified: holo2/src/holo2/solve/place_tiers.py:179-197 RESAMPLE_TIER at 200 with the 'RF1's own number' rationale, registered in TIER_PRICE at :199-201 and deliberately gated=False; holo3 has no re-read row — holo3/plugins/refine.py:512-514 `revised_placement` folds a Placement with route=refine, which bumps pose_affine and wakes the window's calibrate worker at 15 + rung (holo3/plugins/calibrate.py:730-732; SCHEDULE.md:117-124). The 185-point delta and the reversal of intent are stated correctly, and ARTEFACTS.md:555 and :563 resolve verbatim.

*Reason:* The dedicated 200-priced tier really is gone and the ordinary calibrate row really is what re-reads; UNPROVEN is honest given zero adoptions.

---

### pricing-21 — The known mispricing — the K and colour arms of tiles.local both priced 220 while drawing CPU that differs twentyfold

**HOLO3-ONLY** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter upheld.

**What it decides.** Nothing about eligibility; it decides only where two very differently-priced kinds of work sit in the order, and it is the one pricing defect holo3 records against itself.

**holo2.** absent — holo2 has no colour path of any kind, by construction, so it has no analogue and no colour number anywhere.

*Where:* _(no path given)_ · *dial:* named-not-built

**holo3.** One row, two arms: the K arm re-fits a nine-bin context curve over the covering windows, the colour arm re-runs the entire colour head. Both are priced at 220 + rung. The tree states plainly that this is a known mispricing, flagged and not patched, because deriving a second constant would be inventing one.

*Where:* `holo3/plugins/local_ctx.py:92-97`; `holo3/plugins/local_ctx.py:597-599`

*Scheduler row / doc:* SCHEDULE.md:193-243 (the tiles.local row) and SCHEDULE.md:501-520 (per-tool accounting)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo3) K arm 15 fires / 3.25 CPU-s / 3 certs = 1.08 s per certificate = 8% of run CPU; colour arm 33 fires / 141.3 CPU-s / 6 certs = 23.6 s per certificate = 47% of run CPU — ~20x dearer per fire; both priced at 220 and that is a KNOWN MISPRICING, flagged not patched — *artefact:* ARTEFACTS.md:705 (holo3/SCHEDULE.md:508-520)
- (holo3) tiles.local minted 213 certificates at 73% of the sheet-I run's CPU on machine 2 — the one recorded holo3 pricing anomaly on a real sheet — *artefact:* ARTEFACTS.md:735

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Recorded because the pricing map would be dishonest without it, and because ARTEFACTS G-24 (ARTEFACTS.md:831) lists it as an open gap. The tree's own stated fix is the cost-fed scheduler the toolbox doctrine asks for, which holo3 does not have; that is a design line, not a retirement item.

*Refuter (upheld):* *Corrections:* None. Verified: holo3/plugins/local_ctx.py:95-96 LOCAL_COST=220 / RUNG_COST=2 and :597-599 prices both arms identically; ARTEFACTS.md:705 reproduces the per-tool accounting exactly (K 15 fires / 3.25 CPU-s / 3 certs; colour 33 / 141.3 / 6; 0.217 vs 4.28 s per fire = 19.7x) and :735 / :831 (G-24) resolve. Worth adding one observed datum: on the licensed e029 default-domain run tiles.local never fired at all — 986 of the 2,901 frontier entries were still queued at the preempting close (scratch/page-domain-qual/merged-default.log, frontier line) and the row is absent from that run's plugin table. On a K sheet that closes, the mispricing is invisible; it bills on the colour sheets that do not.

*Reason:* The one self-recorded holo3 pricing defect, with both artefact numbers exact.

---

## Completeness pass (modules no family row cited)

20 rows; 6 carry a ruling.

**Reader's family notes.** COMPLETENESS PASS over holo2/src/holo2/{solve,capture,format,engine}. Thirty-four of the eighty-one modules in those four directories are cited by no row and no modules_cited entry of the seven family reader files (close, done-gate, dryness, evidence-ownership, placement, pricing, refinement — 124 rows between them). All thirty-four were read. Twenty-four of them are cited by the twenty rows above; the remaining ten are listed in out_of_filter. (capture/records.py, solve/records.py, solve/keys.py and solve/families.py are named-as-plumbing modules that nonetheless hold real mechanisms — the tile join, the pose quantum, the page-domain validator and window terminality — so those four are rows, not out_of_filter lines, and the plumbing halves are named in each row's notes.)

SEED ROWS STILL UNCOVERED after this pass, all of them in modules that ARE cited by an existing row so outside this pass's brief, listed so the merge can decide: B49 (spend-once / read-set identity, core/identity.py — core/ is outside the four directories), B50 (merge-declared keys projected out of the staleness test, core/commit.py — the tile-join half is extra-14), B51 (CRC false-accept exposure counting, solve/payload.py:339-366), B52 (L6 no self-training, solve/tiles.py:404-415), B53 (L7 never narrow a domain, engine/recipe.py:379-420), B59 (continuous admission and cancel-after-terminal, engine/orchestrator.py:245-330), B65 (deciders / block-level DONE, named-not-built), B66 (SubjectSpec / LabelPool durable surfaces, built-unused; SubjectSpec lives in core/records.py), B67 (pose_audit.predict_from_anchor, built-unused), B68 (PlacementDomainEnvelope, built-unused). B53 in particular is a LAW rather than a mechanism and holo3's PAGE-DOMAIN.md:147-151 argues its own escape from it explicitly — worth a row in the merge even though its module is cited.

TWO ROWS I WOULD PUT IN FRONT OF GERMANO FIRST. extra-05: holo3's intake silently casts anything wider than uint8 into a uint8 plane store, where holo2 refuses a 16-bit / 4-channel / multi-page capture by name — a few lines to fix, and the failure it prevents is silent rather than loud. extra-17: holo3's facts.npz carries no identity at all, so a resume cannot notice it is folding another sheet's facts; stamping the format row id alone would close it without reintroducing the by-value policy comparison the lean-resume ruling deliberately dropped.

extra-16 (the address-word contradiction) should be ruled TOGETHER with the three consumer rows already written as ABSENT (placement-23, evidence-ownership-15, done-gate-08) — they are one line, and without the producer none of the consumers has anything to consume.

**Refuter's family notes.** MECHANISMS NO ROW COVERS. (1) PIXEL QUANTISATION ACROSS THE RASTER BOUNDARY. holo3 stores every plane as uint8 on disk — the native level is a uint8 copy (intake.py:134-137) and every decimated level is rounded and clipped to uint8 (lib/decimate.py:113-119, :174-194) — where holo2 freezes the native array at its own dtype and hands out float32 crops on demand (scan.py:210-219). Every detector in the two trees therefore reads differently-quantised pixels below the finest level, and no row in any of the eight family files states it. It is also what makes extra-05's silent 16-bit cast unrecoverable rather than merely unvalidated. (2) THE SURVEY/LATTICE CARRY HAS NO PIN AT ALL. This is the largest finding of the pass. holo3's structure-tensor score and pitch measurement are character-identical carries of holo2's leaves, but the only cross-tree test covering them (test_h3_drift_declared.py:234-268) compares shared uppercase CONSTANTS and would pass unchanged if the arithmetic were rewritten; the oracle the rows cite (tests/holo2_oracles/test_oracle_survey.py) pins holo2 against holo.receive, not holo3. Since Phase 3 deletes holo2 and Phase 4 deletes holo.receive, the window to write one array oracle over one fixture crop closes with them. This belongs in the Phase-2 suite-preparation package (claude-plan.md §8 step 2.3) alongside the drift-test freezes, not in the map as a no-action row. (3) SUBSCRIPTION GROWTH AT BIRTH. holo3/engine.py:393-402: a birth-matching fact for a bookmark that already stands re-derives that worker's reads and EXTENDS its subscriptions. That is the only place besides _rederive_reads (:341-358) where the wake graph changes shape after a worker exists, and no row names it. (4) A TIED PLACEMENT IS SILENTLY DROPPED. store.py:44-46 uses strict `>` on placement_ordinal, so a revision whose ordinal ties the standing one is discarded even when the affine moved, with no event, no counter and no diag trace. See extra-15. (5) THE RETIRE CAUSE IS ASKED TWICE. engine.py:363-372 re-asks place_retire_cause after the retire predicate already returned true, with a comment arguing the two agree because no ingest intervenes. The argument is sound today and load-bearing; if a second descriptor is ever given a cause it has to be remade. (6) THE Q2 REFUSAL AS A MECHANISM. intake.py:227-233 refuses one source declared at two DPIs in a run — holo3's only enforcement of the e023b physical-evidence invariant, with no holo2 analogue. extra-05 mentions it in passing; nothing in the map treats it as the mechanism it is. COVERAGE CHECK: I unioned every module citation across all eight reader files and all 81 modules of holo2/src/holo2/{solve,capture,format,engine} are cited somewhere — the completeness pass's coverage claim holds. SCHEMA ISSUE AFFECTING TWO ROWS: extra-04 and extra-20 are both classified DIVERGED with ruling_needed:false, which §7 does not permit; extra-04 should lose the classification, extra-20 should gain the ruling.

**Second lens.** This family had no second-lens pass; its rows carry the reader's and the refuter's judgement only.


### extra-01 — How new work is discovered — asking every producer for its whole frontier again after each commit, versus creating a job the moment the fact it works on exists

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **N** · seeds: B60

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a newly-possible job is found by re-asking every producer to list everything it could do, or by the arrival of the one fact that gives that job a subject — and therefore how much work the scheduler does per commit before any decoding happens.

**holo2.** After any structural commit the engine asks every recipe entry's providers to re-list their ENTIRE frontier, because a provider cannot know which of its keys the commit moved. Each returned descriptor is looked up in the admitted/declined tables and dropped if already handled. Two exact optimisations keep that affordable: the provider's descriptor OBJECT is pinned per (entry, provider) so an unchanged re-offer is skipped by identity, and the recipe-entry stamp is applied only after the already-handled test so a dropped offer never rebuilds a frozen dataclass.

*Where:* `holo2/src/holo2/engine/frontier.py:37-64`; `holo2/src/holo2/engine/frontier.py:67-109`; `holo2/src/holo2/engine/frontier.py:151-175`; `holo2/src/holo2/engine/orchestrator.py:770-800` · *dial:* live

**holo3.** There is no enumeration pass. Every fact folded into the store is offered to the seventeen descriptors; a descriptor whose `born_by` matches names the subjects it creates, and each new subject gets exactly one bookmark, created once. Everything after that is a wake: a fact key that changed bumps the version of the workers subscribed to it through an inverted index. A commit therefore costs O(subscribers of the keys that moved), never O(all possible work).

*Where:* `holo3/engine.py:387-408`; `holo3/engine.py:410-424`; `holo3/engine.py:426-431`; `holo3/descriptor.py:64-65`

*Scheduler row / doc:* SCHEDULE.md:5-11 ('births come from born_by+subjects_of, wakes are version bumps through the inverted FactKey index built from reads')

**Implementation delta.** holo2 pulls (ask everyone what exists, drop what is known); holo3 pushes (the fact that makes work possible creates the worker). Inputs differ: holo2's expansion reads the whole store through each provider's own derivation, holo3's birth reads one fact. When it fires differs: holo2 re-enumerates after every structural commit, holo3 only on the birth-matching fact type. The re-offer skip and the entry-stamp ordering are pure holo2 repairs to a cost holo3 never incurs; conversely holo3's births can only ever create a worker whose birth fact has landed, so a provider that would have derived work from a JOIN of several facts must declare one of them as the birth type and subscribe to the rest.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) a serial gen-clean run offered 1,677,186 descriptors to mint 1,768 workers, the other 1.68 M costing 4.95 s = 33% of the commit path — *artefact:* ARTEFACTS.md:732
- (holo2) wakes per commit 45.25 -> 0.71-0.82; stale discards (w8) 2,126 -> 14-41; real sheet serial 632 -> 290 s — *artefact:* ARTEFACTS.md:729
- (holo2 vs holo3) four decodes over one 1000x1000-cell crop of the e029 sheet: certificates 100/112 and 56/82; wall 1,370/842 s and 1,206/786 s; zero wrong on either side — *artefact:* ARTEFACTS.md:415-433

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* No artefact isolates the enumeration mechanism alone on either side; the head-to-head measures the whole stack. The holo2 numbers are the cost of its own design, not a comparison. Nothing here is at risk of a yield loss: holo3 cannot fail to create a worker whose birth fact landed, and the wake index is what re-arms it.

*Refuter (upheld):* *Corrections:* holo3/descriptor.py:64-65 is `seat_seq`/`seat_cost` (the frontier-seat fields), not the birth mechanism the row describes; cite descriptor.py:44-65 (WorkerBookmark) or engine.py:298-334 (_push_worker/_repush) instead. The holo3 behaviour column omits one live path: _births ALSO re-derives a standing bookmark's read set and EXTENDS its subscriptions (holo3/engine.py:393-402), so a birth-matching fact is not always a no-op for an existing worker. Everything else verified: 17 descriptors at engine.py:55-73, the fact-driven births/wakes/_ingest at :387-431, holo2's total re-enumeration at frontier.py:37-64 with the identity skip at :67-109 and the post-test entry stamp at :112-149 (admit is :151-175). All three ARTEFACTS numbers are exact at :732, :729 and :415-422. Keep evidence_status MEASURED only with the row's own caveat promoted out of `notes`: the head-to-head measures the whole stack, and nothing in the record isolates enumeration.

*Reason:* Both sides' code and all three numbers check out; only a mis-aimed line cite and one omitted birth path.

---

### extra-02 — What happens to work a producer offers but cannot do yet — a permanent refusal, a refusal that sleeps on a named wake key, or no vocabulary at all

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **N** · seeds: B60

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether an offered job that is not yet doable is remembered as permanently dead, parked until a named fact moves, or simply re-asked on every wake.

**holo2.** A provider answers a descriptor with a worker or a Decline. A permanent decline goes into a table the engine never removes from, so the work is never offered again and the re-offer skip may drop it by identity forever. A non-permanent decline is parked with the wake keys the provider named; when one of those keys moves the engine un-parks it and the offer is re-made. Anything that is neither a worker nor a decline is a protocol violation and raises.

*Where:* `holo2/src/holo2/engine/frontier.py:112-148`; `holo2/src/holo2/engine/orchestrator.py:540-559` · *dial:* live

**holo3.** There is no decline. A bookmark exists from birth to retirement; at each pop the engine asks `retire` (terminal — the bookmark is dropped and its subscriptions unwound), then a version floor (has anything this worker reads moved since it last tried?), then `eligible`, then `stage`, then `prepare`. A worker that is merely not-yet-doable falls out at `eligible` or `prepare` and stays subscribed; its next wake re-asks. Only `place` records WHY it retired.

*Where:* `holo3/engine.py:433-474`; `holo3/engine.py:360-385`; `holo3/plugins/place_sched.py (place_retire_cause)`

*Scheduler row / doc:* SCHEDULE.md:9-10 ('fire = retire -> version floor -> eligible -> prepare')

**Implementation delta.** holo2 makes the producer name the wake keys of a refusal; holo3 makes every worker declare its read keys up front and derives the same wake from them, so a refusal needs no vocabulary. The cost delta is that a holo3 worker that will never be doable keeps being popped and re-refused until something retires it, where holo2's permanent decline removes it once; the correctness delta is the other way — a holo2 provider that named the wrong wake key loses the wake, which is the failure mode holo3's read-key subscription cannot have.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) stale skips are counted per run (EngineStat.stale_skips) and the retire causes are tallied per cause; no run report in the record breaks out how many pops end at eligible/prepare with no work done — *artefact:* holo3/engine.py:278-296

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The settling artefact would be an existing holo3 events.jsonl: JobDone rows minus pops is not recorded, so this cannot be quantified from the archive without new instrumentation. No yield risk identified — a refused pop writes nothing on either side.

*Refuter (upheld):* *Corrections:* The quoted fire sequence is short by two steps that exist in code: holo3/engine.py:433-474 runs retire -> version floor -> eligible -> STAGE -> a cost re-check that can repush instead of firing (:453-461) -> prepare. Quote SCHEDULE.md:9 as the abbreviation it is. Second: 'a holo3 worker that will never be doable keeps being popped and re-refused' is bounded, not continuous — the version floor at engine.py:456-458 short-circuits any pop where nothing it reads has moved, so the cost is one re-pop per wake, not a spin. Verified: no Decline vocabulary anywhere in holo3; only `place` records a cause (engine.py:363-377 + place_sched.place_retire_cause:229-252, RETIRE_UNKNOWN at :34).

*Reason:* Mechanism and classification right; the fire sequence and the cost statement are both understated.

---

### extra-03 — Attaching a capture to a resumed run BY RECORD — its surveyed regions and footings without its pixels

**ABSENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether a resumed run can keep using the geometry of a capture whose image file is not handed to this invocation, and therefore whether the evidence and poses that cite that capture stay addressable.

**holo2.** A region record durably carries the survey's support grid (origin, step, extent) beside its mask blob, so the survey's own SupportMask, bbox and area can be rebuilt exactly from the store. On resume every capture the store knows and this invocation was NOT handed is rebuilt from records alone, with no file opened and nothing committed. A capture whose pixels ARE present is built by ingest instead and its fresh survey wins. A region whose parent capture record is missing is refused, not skipped, because that is a corrupt state.

*Where:* `holo2/src/holo2/capture/catalog.py:50-70`; `holo2/src/holo2/capture/catalog.py:73-90`; `holo2/src/holo2/capture/catalog.py:93-145`; `holo2/src/holo2/capture/catalog.py:18-22` · *dial:* live

**holo3.** absent. holo3's resume folds a facts.npz whose first family is CaptureSurvey, and the survey fold looks its capture up in a store built from THIS invocation's declared scans. Dropping a capture from the declaration on a resume raises a bare KeyError, and the file says that was ruled knowingly on 2026-08-30: the operator re-declares every capture on every run, so no guard is built.

*Where:* `holo3/snapshot.py:27-32`; `holo3/snapshot.py:65-111`; `holo3/engine.py:229-249`

*Scheduler row / doc:* SCHEDULE.md:337-373 ('the life of a decode'); snapshot.py's own header

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the e034 four-run resume chain re-declared its captures on every run and added the 4800 capture only at run 4 (+14 certificates); no run in the record resumed with fewer captures than it had — *artefact:* ARTEFACTS.md:235
- (holo1) a `--complete` resume of sheet I crashed at LOAD ('stream M is not declared'), state undamaged — the nearest thing in the record to a resume that could not re-open its own inputs — *artefact:* ARTEFACTS.md:224

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** keep holo3's — but record the consequence. The two designs need different things: holo2 stores evidence durably and therefore must be able to name a capture without its pixels; holo3 stores only decisions and regenerates evidence from the rasters, so it needs every capture file on every resume by construction. The loss is real but narrow: a holo3 resume cannot proceed at all if one of its multi-gigabyte TIFFs has moved, where holo2 would carry on with the rest. Accept it, and say so in the resume documentation.

**Notes.**

*Reader:* Not a yield loss on any archived volume — every recorded resume had all its captures. It becomes a loss the first time an archive outlives its scans, which is exactly the deep-time case docs/BOOTSTRAP-DESIGN.md exists for.

*Refuter (upheld):* *Corrections:* Add the code that makes the KeyError claim checkable rather than quoting the docstring for it: holo3/store.py:543 `capture = self._captures[fact.capture_id]` inside _fold_survey is the raise; snapshot.py:27-32 only records that it was ruled. Principle 1 says the docstring ruling is context, not the verdict — the verdict is that line. holo2 side verified in full at catalog.py:50-70 (region_from_record), :73-90, :93-145 (the orphan-region refusal at :130-134) and the fresh-survey-wins rule at :18-22.

*Reason:* ABSENT is correct and both sides' citations are exact; only the evidence for the crash should come from code, not from the ruling comment.

---

### extra-04 — What a capture's pixels ARE once ingested — one grey plane, or three colour planes

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader DIVERGED → refuter reclassified to CARRIED-DIFFERENT.

**What it decides.** Whether colour information survives the raster boundary at all, and therefore whether any per-plane read is even expressible downstream.

**holo2.** Ingest accepts grey or RGB and validates the shape, but every consumer crop goes through `crop_luma`, which reduces RGB to a single float32 plane by the equal-channel mean. The three channels are kept in the frozen native array and are reachable only through `crop_native`, which no solve path calls. This is where holo2's colour blindness is enforced: the receiver below this line has one plane per capture, always.

*Where:* `holo2/src/holo2/capture/scan.py:73-77`; `holo2/src/holo2/capture/scan.py:210-219`; `holo2/src/holo2/capture/scan.py:88-111` · *dial:* live

**holo3.** Intake keeps the three RGB planes as three separate on-disk rasters per level for a colour family, and derives a single luma plane only when the format row's family is K. The derived-plane choice is a function of the declared format family, so a colour row's per-plane heads read r/g/b directly and the K path costs exactly one plane.

*Where:* `holo3/plugins/intake.py:120-121`; `holo3/plugins/intake.py:124-131`; `holo3/plugins/intake.py:161-195`; `holo3/lib/decimate.py:264-272`

*Scheduler row / doc:* SCHEDULE.md:339-341 ('ingest converts each scan into the resolution ladder'); the colour rows of the ladder table

**Implementation delta.** holo2 collapses colour at the raster boundary and cannot express a per-plane read; holo3 makes the collapse conditional on the declared family and keeps the planes otherwise. This is not a scheduling or detector difference — it is the reason holo2 has no colour receiver at all, and it means no holo2 mechanism in the colour half of the map can be compared side by side.

**Evidence status.** MEASURED

**Evidence.**

- (holo2) colour codings in holo2 are 'identities nameable and rows buildable at the format layer', with the verified column empty of any decode; 'cmy8 sheets have no reader by design' — *artefact:* ARTEFACTS.md:628-634
- (holo3) the colour volumes holo3 does read: xerox c2-cmy8 5,422 certificates, xerox c2-cmy7 1,586, xerox c3-cmy7 786-815, sheet I 5,880/5,883 with zero wrong — *artefact:* ARTEFACTS.md:153, ARTEFACTS.md:174, ARTEFACTS.md:139, ARTEFACTS.md:225

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Recorded for completeness of the map, not as a gap to close: nothing here needs porting in the holo2 -> holo3 direction. It is the single line of code that explains why every colour family in this map has 'holo2: none, by construction' as its holo2 column.

*Refuter (reclassified):* *Corrections:* (1) DIVERGED with ruling_needed:false is not a state the plan allows — claude-plan.md §7 gives every DIVERGED row a RULINGS.md entry. The row's own notes say nothing needs porting, so the honest word is CARRIED-DIFFERENT: both trees turn a file into readable planes, holo3's collapse is family-conditional and a strict superset. (2) 'the K path costs exactly one plane' is FALSE for any 3-channel capture: holo3/plugins/intake.py:183-188 writes all three RGB planes at the native level via native_plane_names(3) regardless of family; only the decimated levels get the single luma plane (derived_planes at :125-131). (3) The cited holo3/lib/decimate.py:264-272 (luma_f32 / plane_mean_luma_f32) is the READ-time reduction used by survey.py:75, place.py:554 and calibrate.py:181-182 — not the ingest derivation, which runs through _decimate_plane -> area_decimate_into -> _uint8_integer_box_rows:113-114 / _uint8_rational_rows:184-186. Those are where the equal-channel mean actually happens on the ingest path, and they match holo2's _raw_luma (scan.py:73-77) in semantics.

*Reason:* Nothing is owed in the holo2->holo3 direction, so DIVERGED overstates it; and the K-path cost claim is wrong at the native level.

---

### extra-05 — Capture identity, the refusals at ingest, and re-authenticating the source file before anything durable is written

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **integrity** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Which acquisitions count as one capture (and therefore what a cross-capture sum is entitled to sum), and whether a source file that changed mid-run can poison committed evidence.

**holo2.** The SHA-256 of the encoded source bytes IS the capture identity, and the docstring states the consequence: re-encoded, resized or cropped copies have different byte identities but are correlated evidence and must not be submitted as independent acquisitions. Ingest refuses a multi-page TIFF, a 4-channel image, a non-real dtype, non-finite pixels, an unreadable PIL mode, and a file whose stat tuple moves while it is being opened. Before any durable retention the raster re-authenticates its path: a matching (dev, ino, size, mtime_ns) memo skips, any difference escalates to a full byte re-stream and SHA compare.

*Where:* `holo2/src/holo2/capture/scan.py:352-396`; `holo2/src/holo2/capture/scan.py:36-71`; `holo2/src/holo2/capture/scan.py:221-264`; `holo2/src/holo2/capture/scan.py:286-313` · *dial:* live

**holo3.** The capture id is the same SHA-256 of the file bytes. holo3 adds the Q2 refusal — the same source declared at two DPIs in one run is refused by name, because a corrected DPI renames every lane the evidence cites. It drops the rest: no dtype, channel-count, finiteness or multi-page checks, no open-time stat comparison, and no re-authentication before writing, because holo3 copies every plane into its own run-dir memmaps at intake and never reads the operator's file again.

*Where:* `holo3/plugins/intake.py:35-39`; `holo3/plugins/intake.py:42-62`; `holo3/plugins/intake.py:172-207`; `holo3/plugins/intake.py:213-241`

*Scheduler row / doc:* SCHEDULE.md:339-341; intake is not a scheduled row

**Implementation delta.** Same identity function, different guard set and a different reason for the guards. holo2 keeps reading the operator's file for the whole run and therefore has to re-authenticate it; holo3 copies the pixels once into uint8 memmaps under the run directory and reads only those, which makes the source-changed hazard structurally unreachable after intake. What holo3 genuinely drops is the input-validation set: a 16-bit or 4-channel or multi-page TIFF that holo2 refuses by name is silently cast into uint8 planes by `target[y0:y1] = source`.

**Evidence status.** UNPROVEN

**Evidence.**

- (v1) the multi-scan law: never double-count the same physical capture (raw plus its decimation) in one state; one ordinary state freezes one DPI — *artefact:* CLAUDE.md channel-facts list; e023b physical-evidence invariant
- (holo3) no artefact — no run in the record used a 16-bit, 4-channel or multi-page capture. The three archived TIFFs whose headers I read directly are uint8 (a header read, not a decode, and not an ARTEFACTS.md row) — *artefact:* no artefact

**Yield relevance.** integrity — source: reader.

**Recommendation.** port now, cheaply: a handful of refusals at holo3's `load_native` (dtype real-numeric, channels in {1,3}, one TIFF page, and a named refusal rather than a silent cast for anything wider than uint8). It is a few lines, it costs nothing at run time, and the failure it prevents is silent — a 16-bit scan currently becomes garbage pixels rather than an error, and the receiver would report it as a hard sheet.

**Notes.**

*Reader:* The settling run is not a decode: open one 16-bit TIFF through holo3's intake and compare a plane against the source (seconds). No such capture exists in the corpus today, so this is a latent capability loss, not a measured one.

*Refuter (upheld):* *Corrections:* Strengthen one clause: a multi-page TIFF is not merely unrefused, it is silently READ AS PAGE 0 — holo3/plugins/intake.py:43-47 `tiff.pages[0].asarray(...)` — so the failure is a wrong capture, not a cast. Add that a 4-channel array survives load_native (only a singleton third axis is squeezed at :61-62), is labelled channels=3 at :174, and has its fourth channel silently dropped by native_plane_names(3). All four holo3 citations verified, including the Q2 refusal at :227-233 and the absence of any dtype/finiteness/stat guard; holo2's refusals verified at scan.py:88-111 and the re-authentication at :221-264.

*Reason:* Every claim reproduces at HEAD; the recommendation to port a handful of refusals stands and the silent-failure argument is if anything understated.

---

### extra-06 — The structure-tensor score that finds where the printed field is on a platen (E021 region survey, the scoring leaf)

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT.

**What it decides.** Which parts of a scan are treated as printed payload at all — every window, pose and certificate downstream lives inside a region this score found.

**holo2.** The raster is box-decimated to about 4 px per cell, two truncated Gaussian stages build the structure tensor, and the smaller eigenvalue is block-averaged onto the survey grid. The whole platen is scored in 256-cell tiles with an exact halo equal to the two filters' compact support, so a tiled score equals a whole-image score. One local adaptation is declared: the tiles run sequentially, which the module argues is bit-identical to the original's single-worker path.

*Where:* `holo2/src/holo2/capture/_survey_tensor.py:27-33`; `holo2/src/holo2/capture/_survey_tensor.py:44-75`; `holo2/src/holo2/capture/_survey_tensor.py:110-117`; `holo2/src/holo2/capture/_survey_tensor.py:144-213`; `holo2/src/holo2/capture/_survey_tensor.py:132-141` · *dial:* live

**holo3.** The same leaf, inlined into the survey plugin: identical constants (4.0 work cells, 0.22 derivative, 0.30 tensor, 256-cell tiles), the same two-stage filter, the same halo derivation and the same overlap-safe tiling. The one difference is the input: holo3 reads the plane store's uint8 luma directly, where holo2 divides a 16-bit raster's luma by 256 first.

*Where:* `holo3/plugins/survey.py:59-63`; `holo3/plugins/survey.py:99-155`; `holo3/plugins/survey.py:162-199`

*Scheduler row / doc:* SCHEDULE.md ladder row `survey` at price 10; descriptor `SURVEY_DESCRIPTOR` (survey.py:812)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN — corrected in the merge: reader said PINNED; refuter: the cited gate is a shared-CONSTANT check that would pass unchanged if the arithmetic were rewritten, and the cited oracle pins holo2 against holo.receive, not holo3.

**Evidence.**

- (holo3) holo3.plugins.survey vs holo2.capture.survey is a declared constant pair with a floor of 15 shared constants and an empty allowed-divergence set — any value that parted company fails the gate — *artefact:* holo3/tests/test_h3_drift_declared.py:207,224,239
- (holo2) the carry is pinned cross-tree by tests/holo2_oracles/test_oracle_survey.py — *artefact:* holo2/src/holo2/capture/survey.py:1-30

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The amplitude convention is the one real difference and it is inert on this corpus (every archived capture is 8-bit, so holo2's /256 branch never fires); it is carried as its own row, extra-05. `_feature_luma` has no holo3 counterpart at all.

*Refuter (reclassified):* *Corrections:* THE NAMED PIN DOES NOT PIN THIS. holo3/tests/test_h3_drift_declared.py:234-268 compares only equally-NAMED uppercase module constants of comparable type, with a shared-count floor; it asserts nothing about the structure-tensor arithmetic, and it would pass unchanged if _minor_eigen_work were rewritten. The cited lines are also wrong: :207 is the closing paren of CONSTANT_PAIRS, :224 is the calibrate-vs-detect floor, and the survey pair is at :205 with its floor 15 at :229. The second citation, tests/holo2_oracles/test_oracle_survey.py, pins holo2 against holo.receive (its docstring line 1) and cannot be evidence for holo3's carry. Grep of holo3/tests: 'survey' appears in the drift tests only in that constants file — NO bit-exact oracle for this leaf exists anywhere in holo3. Substance survives: I read both leaves and the arithmetic is character-identical (_minor_eigen_work, _block_mean, _tensor_halo_cells, the tile loop and the ext-edge clause at holo3/plugins/survey.py:117-199 vs holo2/src/holo2/capture/_survey_tensor.py:44-213). The real delta is therefore (a) the input: holo2's _feature_luma (:132-141) divides by 256 above luma_max 512 and holo3's NativeView.crop_luma (survey.py:72-79) has no such branch — compounded by holo3's intake having already truncated any 16-bit source to uint8; and (b) two dropped guards (tensor_geometry's finite/positive check at _survey_tensor.py:37-38, the tile-shape RuntimeError at :206-208). WHAT WOULD SETTLE IT: one array oracle comparing holo3's _whole_tensor_score against holo2's on a fixture crop — seconds to run, no receiver run — and it MUST be written before Phase 3 deletes holo2, or this carry becomes permanently unverifiable.

*Reason:* CARRIED-IDENTICAL/PINNED is unsupported: the cited gate is a shared-constant check and the cited oracle compares the wrong pair of trees.

---

### extra-07 — Measuring the printed cell pitch from a crop — the gradient-comb spectrum, the probe ladder, and the largest-harmonic-consistent selection rule

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter reclassified to CARRIED-DIFFERENT.

**What it decides.** What cell pitch a region is read at, which fixes the whole sampling geometry of every window inside it.

**holo2.** The printed field has a spectral null at the cell rate, so the gradient magnitude is measured instead, Hann-windowed and transformed. Each probe pitch is a band-limited argmax with a contrast measured against the in-band median. Credible lines above contrast 30 are de-duplicated, and selection starts at the LARGEST credible period and takes the first line every other credible line is an integer division of — not the loudest peak, because harmonics routinely beat the fundamental. A mixed spectrum that names no fundamental falls back to the strongest line. The survey overrides the module's nine probes with thirteen (adding 48/64/96/128 px).

*Where:* `holo2/src/holo2/capture/lattice.py:25-37`; `holo2/src/holo2/capture/lattice.py:74-135`; `holo2/src/holo2/capture/lattice.py:138-228`; `holo2/src/holo2/capture/survey.py:136-139` · *dial:* live

**holo3.** The identical leaf inlined: the same thirteen probes, contrast floor 30, 2048 px measurement window, 0.08 ratio tolerance, 0.02 dedup tolerance, the same radial floor and one-octave band, the same largest-harmonic-consistent rule and the same strongest-line fallback. Error style differs: holo2 raises LatticeNotFound carrying the best pitch it saw, holo3 returns None.

*Where:* `holo3/plugins/survey.py:46-57`; `holo3/plugins/survey.py:202-234`; `holo3/plugins/survey.py:236-281`; `holo3/plugins/survey.py:301-313`

*Scheduler row / doc:* SCHEDULE.md ladder row `survey`; PAGE-DOMAIN.md is silent on pitch

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN — corrected in the merge: reader said PINNED; refuter: same constants-gate failure as extra-06.

**Evidence.**

- (holo3) the survey constant pair gate (>=15 shared constants, empty allowed-divergence set) covers PITCH_PROBES_PX, CONTRAST_FLOOR, MEASURE_WINDOW_PX, RATIO_TOLERANCE and DEDUPE_TOLERANCE — *artefact:* holo3/tests/test_h3_drift_declared.py:207,224,239
- (holo1) the doctrine this leaf exists to satisfy: page-derived pitch estimators fit channel wander as scale (5.92 vs a true 6.00), so the pitch is snapped to a candidate set rather than trusted raw — *artefact:* holo2/src/holo2/capture/survey.py:393-441

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* What the two trees do with the measured pitch — snap it to a candidate set, and what happens when the sheet disagrees with the declared row — is placement-24's row, already written and classified DIVERGED. This row is only the measurement underneath it.

*Refuter (reclassified):* *Corrections:* Same pin failure as extra-06: test_h3_drift_declared.py:234-268 is a shared-constant gate, not a bit-exact pin, and the line numbers should be :205/:229. NUMBER NOT WHERE THE ROW SAYS: the '5.92 vs a true 6.00' fact is not at holo2/src/holo2/capture/survey.py:393-441 — that docstring is _snap_pitch and contains no such number. It lives at holo3/conversion_docs/08-pose-refine.md:333-335 and 06-intake-survey.md:186-191. Two omissions from the delta: holo3's _estimate_lattice (plugins/survey.py:202-233) returns (pitch, contrast) only, DROPPING the angle that holo2's estimate_lattice returns and folds into the mod-90 convention (lattice.py:133, :219-221); and holo3's _measure_cell_pitch returns only `strong`, dropping the raw `candidates` list holo2 carries (lattice.py:226). Verified as equal: the thirteen probes (holo2 overrides its nine-probe module default from survey.py:136-139, exactly as the row says), the four floors, the largest-harmonic-consistent rule, the strongest-line fallback, and the _pitch_vote composition (holo2 survey.py:471-482 vs holo3 survey.py:301-314 take the same max over strong+chosen). Same settling artefact as extra-06, written before holo2 goes.

*Reason:* The pin is a constants gate, the doctrine number is cited to a place that does not hold it, and two outputs of the leaf are dropped in holo3.

---

### extra-08 — The pilot address-word code — shortened BCH(127,50,t=13) -> (100,23) over GF(2^7)

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Which printed address words decode at all, and with how many corrected errors — the single gate between a candidate window pose and a legal tile address.

**holo2.** Carried verbatim from v1: primitive polynomial 0x89, roots alpha^1..alpha^26, generator degree 77, designed distance at least 27, shortened by 27 to a 100-bit transmitted word carrying a 23-bit message (an 18-bit tile counter plus 5 known-zero pads). Every executable line is stated to be the original's, and the module declares itself format-axis: a changed bit stops printed sheets decoding.

*Where:* `holo2/src/holo2/format/bch.py:1-22` · *dial:* live

**holo3.** The same code with the same constants, plus the erasure-decode form. Every entry point is pinned bit-for-bit against v1 and, for the batch path, against holo2 as well.

*Where:* `holo3/lib/bch.py:8-12`; `holo3/lib/bch.py:75-109`; `holo3/lib/bch.py:203-249`; `holo3/lib/bch.py:324-357`

*Scheduler row / doc:* conversion_docs/01-bch.md:41-52 (the constant register); read by plugins/words.py and plugins/place.py

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) decode_many is asserted bit-identical to v1's scalar decoder AND to holo2's batch decoder over 2,000-200,000 random and near-codeword words, with a same-decode comparison per row — *artefact:* holo3/tests/test_h3_drift_kernels.py:216-244
- (holo3) the erasure budget boundary agrees on both sides at 26 and 27 erasures — *artefact:* holo3/tests/test_h3_drift_kernels.py:200-214
- (holo2) pinned character for character against holo.core.bch by tests/holo2_oracles/test_oracle_tiles.py — *artefact:* holo2/src/holo2/format/bch.py:3-8

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* _(none)_

*Refuter (upheld):* *Corrections:* None material. Verified at HEAD: test_h3_drift_kernels.py:218-246 asserts same_decode against BOTH v1's scalar decoder and holo2's batch decoder over _n(400,60_000)+_n(1600,140_000) = 2,000 fast / 200,000 slow words, and :202-215 is the 26/27 erasure boundary against v1. Worth noting for the map that the holo2-side citation (test_oracle_tiles) pins holo2-vs-v1 and is not needed here — holo3 is pinned to both trees directly in the one test, which is what makes this row genuinely PINNED where extra-06/07 are not.

*Reason:* The pin exists, is at the cited lines, and asserts exactly what the row claims.

---

### extra-09 — The batched form of the address-word decode used by the Stage-A slot sweep, and the scalar oracle behind it

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-order-only** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Nothing about which words decode — it decides how much CPU the single dearest stage of the receiver costs, and whether a scalar reference implementation stays reachable.

**holo2.** A separate module that imports the carried scalar BCH's tables, constants and syndrome kernel and re-expresses only the ROUTING, so the sweep that calls it 147,456 times per window pays numpy dispatch once per batch instead of once per candidate. Two cards: a batched Chien search first, then a lockstep Berlekamp-Massey. The scalar path remains THE ORACLE and the batch is behind `PlacementConfig.batched_word_sweep`, which defaults True. The bar is stated as bit-identity, never a tolerance.

*Where:* `holo2/src/holo2/format/bch_batch.py:1-40`; `holo2/src/holo2/solve/place_model.py:344-348`; `holo2/src/holo2/solve/place_job.py:686`; `holo2/src/holo2/solve/words.py:411` · *dial:* live

**holo3.** There is one bch module and the batch form IS the decoder: `_syndromes_many_words`, `berlekamp_massey_many`, `chien_root_mask` and `decode_many` are ordinary functions with no dial, and the scalar `decode` sits beside them as the single-word entry point rather than as a switchable arm.

*Where:* `holo3/lib/bch.py:111-201`; `holo3/lib/bch.py:251-305`; `holo3/lib/bch.py:306-323`; `holo3/lib/bch.py:324-357`

*Scheduler row / doc:* conversion_docs/01-bch.md:50 credits holo2 format/keystream.py:56-66; SCHEDULE.md's `place` rows are the caller

**Implementation delta.** Same arithmetic, different packaging: holo2 keeps the fast path in a separate module behind a config flag so the carried format-axis file stays untouched and the scalar path stays an oracle; holo3 folds the batch kernels into the one bch module and deletes the switch. The consequence is that holo3 has no in-tree A/B arm — the equivalence is held by the cross-tree drift test rather than by a runnable control.

**Evidence status.** PINNED

**Evidence.**

- (holo3) holo3's berlekamp_massey_many and chien_root_mask are asserted array-equal to holo2's on dirty syndromes over 2,048-8,192 words — *artefact:* holo3/tests/test_h3_drift_kernels.py:246-266
- (holo2) the Stage-A word sweep measured ~72% of ALL receiver CPU, of which _chien_roots was 30.0% and _berlekamp_massey 25.1%; the batched decode went 106 ms -> 36 ms at H=4096 and its GIL-free fraction 0.15 -> 0.95 — *artefact:* ARTEFACTS.md:728; holo2/src/holo2/format/bch_batch.py:13-24

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The dial is worth naming in the comment carry: holo2 states the reason for keeping a scalar oracle reachable (the carried file is format-axis and a batch rewrite of it would be a fork). holo3 satisfies the same need with the cross-tree pin, which is fine only while holo2 exists to be compared against — after the deletion the pin becomes a one-time record against v1's scalar decoder alone.

*Refuter (upheld):* *Corrections:* None material. Verified: test_h3_drift_kernels.py:249-266 array-equal on sigma/terms/length and the Chien mask over _n(2048,8192) words; holo3/lib/bch.py holds one module with no dial (batch kernels at :111-121, :251-305, :306-323, decode_many at :324; scalar decode at :203); the two callers are plugins/words.py:260 (batch) and format/pilots.py:166-167 (scalar + erasures). ARTEFACTS.md:728 carries the 72%-of-all-CPU figure exactly. The note about the pin becoming one-sided after holo2 is deleted is correct and should be carried into PRESERVATION.md, not just the map.

*Reason:* Packaging delta stated correctly and the cross-tree pin is real at the cited lines.

---

### extra-10 — The printed tile format: where the pilot and filler sites are, which cell carries which codeword bit, and the per-address keystream that descrambles them

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Which cells are read as pilots, which as payload, and what value each one is compared against — the whole map from a posed window to a decodable codeword.

**holo2.** Every 64x64 tile carries the same 100-site pilot pattern drawn from a 10x10 quota grid with the exact boundary table, plus the BCH address word; the site pattern is deliberately periodic because the cold-start correlation template depends on it. Payload cells are permuted per tile by an affine slot map and their values scrambled by AES-128-CTR keyed as a pure function of the address (SHA-256 KDF, a 16-byte counter with named domain/aux/major/u/v fields). holo2 carries eight of the fifteen domains — the six the K tile chain needs plus the close's fountain pair; the colour domains 9-13 are explicitly not carried.

*Where:* `holo2/src/holo2/format/format_v1.py:380-551`; `holo2/src/holo2/format/pilots.py:52-62`; `holo2/src/holo2/format/pilots.py:65-120`; `holo2/src/holo2/format/pilots.py:132-162`; `holo2/src/holo2/format/keystream.py:56-79`; `holo2/src/holo2/format/keystream.py:83-183` · *dial:* live

**holo3.** The same construction, with all fifteen keystream domains and the colour dust/word-state surface present. One receiver-axis change from the page-domain wave: the payload scramble plane for a page is derived on first touch and memoised, rather than stacked for the whole domain at store init — the printed values are unchanged, only when they are computed.

*Where:* `holo3/format/pilots.py:8-18`; `holo3/format/pilots.py:21-99`; `holo3/format/keystream.py:9-23`; `holo3/format/keystream.py:41-135`; `holo3/format/tile_codec.py:108-158`; `holo3/format/identity.py:430-520`

*Scheduler row / doc:* conversion_docs/03-keystream-metadata.md:145-153; 04-format-identity.md:49-52; PAGE-DOMAIN.md:74-79 (the scramble plane is now built per page on first touch)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) eleven keystream tests assert byte-identity with v1 across the KDF, the domain constants, the counter construction and refusals, blocks/bits, keys64, fountain rows, colour fountain and block assignment, item permutations, dither bits, the bounded-draw ladder and slot-perm coprimality — *artefact:* holo3/tests/test_h3_drift_format.py:74-246
- (holo3) pilot site construction, colour site construction, word values and decode (including refusals) all match v1; tile addressing matches v1's layout on the e029 row — *artefact:* holo3/tests/test_h3_drift_format.py:358-444, :521-533
- (holo2) the pilots and format_v1 carry is pinned by tests/holo2_oracles/test_oracle_tiles.py, which cross-checks every value against the real v1 FormatSpec — *artefact:* holo2/src/holo2/format/format_v1.py:12-16; holo2/src/holo2/format/pilots.py:7-8

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Both trees are pinned to v1 rather than to each other, which is the stronger statement. holo3's per-page scramble derivation is the only behavioural change on either side and it is receiver-axis by construction (PAGE-DOMAIN.md's §3 edit 6, ~7.7 MiB per page at 53x37 against a ~1 GB full stack).

*Refuter (upheld):* *Corrections:* NUMBER WRONG: holo2 carries TEN of the fifteen keystream domains, not eight — 1..8 plus DOMAIN_COLOR_FOUNTAIN_ROW=14 and DOMAIN_COLOR_BLOCK_ASSIGN=15 at holo2/src/holo2/format/keystream.py:56-65 (they are what its carried-but-dead pooled streamset reaches). Only 9-13 are uncarried, which the row already says correctly. Also holo3/format/identity.py:430-520 overruns the file (518 lines); the range that matches the row's description is :430-518 (resolve_format_ref through scramble_plane, the per-page memo at :508-518). Everything else verified: the three pin ranges are real (eleven keystream tests at :74-246, pilots at :358-444, tile addressing at :521-533) and PAGE-DOMAIN.md:74-79 says exactly what is quoted.

*Reason:* Carry and pins are sound; one domain count is off by two and one line range overruns the file.

---

### extra-11 — The fountain code itself — block assignment from the tile counter, generator rows, and the incremental GF(2) solve

**CARRIED-IDENTICAL** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-IDENTICAL → refuter upheld.

**What it decides.** Which certified tiles contribute to which block, when a block becomes solvable, and therefore when a volume can close.

**holo2.** Carried verbatim from v1, restricted to the coding core a close needs: the frozen ESI -> (block, row) derivation with per-page exact quotas and a keystream shuffle, the packed Gauss-Jordan solver and the incremental decoder. The generator-side planning surface (rank reserve, q fraction, page capacity) is deliberately not carried. streamset carries the multistream and pooled mappings, including pooled_unwrap_solved, even though holo2 has no colour reader to reach them.

*Where:* `holo2/src/holo2/format/fountain.py:101-110`; `holo2/src/holo2/format/fountain.py:116-121`; `holo2/src/holo2/format/fountain.py:156-194`; `holo2/src/holo2/format/fountain.py:260-488`; `holo2/src/holo2/format/streamset.py:47-105`; `holo2/src/holo2/format/streamset.py:187-286` · *dial:* live (K); the pooled and multistream halves are built-unused

**holo3.** The same frozen derivation and the same solver, with the multistream and pooled paths live and exercised: sheet I closes only with pooled-fountain algebra and three pooled captures.

*Where:* `holo3/format/fountain.py:14-30`; `holo3/format/fountain.py:45-73`; `holo3/format/fountain.py:78-171`; `holo3/format/fountain.py:172-300`; `holo3/format/close.py`

*Scheduler row / doc:* conversion_docs/05-fountain.md:40-42; CLOSE-PORT-SPEC.md:18-41 (v1 algebra plus holo2's _CloseState restyled)

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** PINNED

**Evidence.**

- (holo3) volume-code assignment matches v1's fountain, packed generator rows match v1's generator row, and a pooled single-stream code is bit-identical to the K form on both sides — *artefact:* holo3/tests/test_h3_drift_format.py:580-632
- (holo3) closes of v1-emitted K, colour single-stream, cmy8 three-stream and pooled (healthy and dead-plane) volumes all verify byte-exact — *artefact:* holo3/tests/test_h3_drift_format.py:703-802
- (holo3) vol 7 closes ONLY with pooled-fountain algebra AND three pooled captures (single capture: shortfall 125) — *artefact:* ARTEFACTS.md:605

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The close's own scheduling — preemption, consult modes, the incremental eliminator — is the close family's rows (close-01..close-15). This row is only the coding underneath them. holo2's pooled streamset is carried-but-dead, which is the H7 leaf-sync status the seed records; nothing to port.

*Refuter (upheld):* *Corrections:* None. All three pins verified by name at HEAD: test_h3_drift_format.py:580/599/632 (volume-code assignment, pooled-single-stream bit-identity, packed generator rows) and :703/714/735/789 (K, colour single-stream, cmy8 three-stream, pooled healthy + dead-plane closes). ARTEFACTS.md:605 carries the vol-7 pooled statement verbatim.

*Reason:* Every cited pin exists at the cited line and asserts the claimed property.

---

### extra-12 — Colour codec construction — how a cmy7/cmy8 row's streams, FEC banks and symbol widths are derived, and what happens when a colour row is asked to decode

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader HOLO3-ONLY → refuter reclassified to CARRIED-DIFFERENT.

**What it decides.** Whether a colour format row can be named, built and then actually read.

**holo2.** holo2 carries the full FORMAT-SPACE grammar and the colour family constructors — plane order, dust cycles, mapper-unit widths, bank children, stream layouts — so a colour identity resolves and a colour row is buildable. Dispatch is on the Family enum and nothing else, which the origin measured the cost of getting wrong. But the pilot module's colour surface (dust sites, word states, dust schedules) and the keystream's colour domains 9-13 are deliberately not carried, so instantiating a colour codec fails fatally by design.

*Where:* `holo2/src/holo2/format/families.py:70-101`; `holo2/src/holo2/format/families.py:276-360`; `holo2/src/holo2/format/family.py:1-45`; `holo2/src/holo2/format/pilots.py:5-9`; `holo2/src/holo2/format/keystream.py:47-52` · *dial:* built-unused (a colour row is nameable and buildable, never decodable)

**holo3.** The whole colour stack is present and live: dust sites, colour word states, the cmy7 codebook and soft demapper with three demapping iterations, cmy8 per-stream decode, and six scheduler rows that only exist for colour.

*Where:* `holo3/format/identity.py:14-19`; `holo3/format/pilots.py:78-99`; `holo3/format/keystream.py:17-21`; `holo3/format/tile_codec.py:9-33`; `holo3/plugins/color_model.py`; `holo3/plugins/color_region.py`

*Scheduler row / doc:* SCHEDULE.md rows `color`, `color.pooled_ctx`, `refine.color`, `tiles.planek`, `tiles.swim`; 10-colour-heads.md, 11-colour-planes-ctx.md

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo2) colour codings are nameable and buildable at the format layer with the verified column empty of any decode — *artefact:* ARTEFACTS.md:628-634
- (holo3) campaign colour reach: xerox c2-cmy8 5,422, xerox c2-cmy7 1,586, sheet I 5,880/5,883, zero wrong certificates across 285 target addresses in five crop batteries — *artefact:* ARTEFACTS.md:153, :174, :225, :316-317

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Listed so the map does not look silent about the largest structural difference between the trees. No action: the direction of travel is entirely holo2 -> nothing.

*Refuter (reclassified):* *Corrections:* HOLO3-ONLY contradicts the row's own holo2 column, which cites four live holo2 files: holo2/src/holo2/format/families.py:276-360 really does derive cmy7/cmy8 banks, dust cycles, mapper-unit widths and stream layouts, and family.py dispatches on the Family enum. What is holo3-only is the READER, not the construction. Either retitle the row to its decode half or split it in two. Second correction: SEVEN scheduler rows are colour-gated, not six — `color`, `color.pooled_ctx`, `refine.color`, `fields` (holo3/plugins/fields.py:778 exits on Family.K), `tiles.uplift` (color_arms.py:94-96 returns no arms for K), `tiles.planek` and `tiles.swim` (both gate on Family.CMY8, plane_k.py:618). The row names five and says six. Verified as stated: holo2's pilots.py:1-9 declares the colour surface deliberately uncarried, so a colour codec there fails fatally by design.

*Reason:* The label says holo3-only while the row's own evidence shows the format-layer half is carried and live in holo2.

---

### extra-13 — Which printed row a decode assumes — the v2 identity grammar, the frozen legacy catalogue, and the rule that decides between them

**CARRIED-DIFFERENT** · evidence **PINNED** · yield **decides-certificates** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** What geometry, seed, rung and stream set every later stage reads the sheet under; a wrong resolution is a decode of the wrong format.

**holo2.** Two routes only: an `L:`-prefixed reference is matched byte-exactly against a frozen catalogue of whole legacy identities and resolved straight onto its seed, never parsed; anything else goes through the normalising v2 grammar, where the canonical format id IS the AES seed. The `L:` marker selects the route before any parsing, so a legacy string can never reach the parser. holo2 keeps twelve fossils, having dropped the two cmy8-v0 rows by its own sunset ruling, and it refuses a bare legacy spelling by name.

*Where:* `holo2/src/holo2/format/lattice.py:101-166`; `holo2/src/holo2/format/resolve.py:1-60`; `holo2/src/holo2/format/fossils.py:1-25`; `holo2/src/holo2/format/format_v1.py:248-270` · *dial:* live

**holo3.** The same two routes and the same seed-is-the-id law, with fourteen fossils — holo3 keeps the two cmy8-v0 rows that holo2 dropped, matching src/holo, because e030 and e032 printed them.

*Where:* `holo3/format/identity.py:20-21`; `holo3/format/identity.py:221-429`; `holo3/format/identity.py:430-497`

*Scheduler row / doc:* conversion_docs/04-format-identity.md:49-52; CLI `--format REF`

**Implementation delta.** Same grammar, same precedence rule, same seed derivation; the catalogues differ by exactly the two cmy8-v0 identities holo2 retired and holo3 kept. That is a coverage difference, not an arithmetic one: every identity both trees hold resolves to the same seed bytes.

**Evidence status.** PINNED

**Evidence.**

- (holo3) fossil seed bytes equal v1 on every shared identity, and equal holo2 on all twelve it kept; the site seeds FAMILY_SEED_P100 and FAMILY_SEED_P120 are identical across all three trees — *artefact:* holo3/tests/test_h3_drift_declared.py:285-305
- (holo3) the fossil-count difference is a DECLARED divergence with a live checker: holo3 14 identities, holo2 12, the two dropped rows named — *artefact:* holo3/tests/test_h3_drift_declared.py:68-75, :120-123
- (holo3) v2 grammar resolution matches v1 on every tested reference; fossil row fields match v1 resolution per identity — *artefact:* holo3/tests/test_h3_drift_format.py:445-514

**Yield relevance.** decides-certificates — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The two dropped identities are exactly the e030 hp cmy8 rows and the e032 xerox c2-cmy8 row family — volumes holo2 could not read anyway. Nothing to port; the pin is the point.

*Refuter (upheld):* *Corrections:* None. Verified at HEAD: test_h3_drift_declared.py:285-306 (fossil seeds equal v1 on every shared id, equal holo2 on exactly 12, both site seeds identical across all three trees) and the declared-divergence entry at :68-75 / :120-123, whose predicate asserts len(holo3)==14 and len(holo2)==12 and names both dropped rows by id. test_h3_drift_format.py:445-514 covers the grammar and fossil-field comparisons.

*Reason:* Three real pins, all at the cited lines, all asserting the claimed facts.

---

### extra-14 — What happens when two jobs certify the same tile at once — a commutative join that keeps both, versus a compare-and-swap that discards the loser

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **integrity** · ruling needed **N** · seeds: B50

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a certificate produced by a job that lost a race survives, and whether two decoders that disagree about one tile are caught.

**holo2.** The tile record's whole algebra is one join, applied twice: a fire joins its gain onto the snapshot it read, and the wall re-joins that proposal onto whatever now stands. Certified content is carried verbatim, the observed-by and baselined footing sets union, and two agreeing certificates are corroboration — the standing mint keeps provenance and the loser's observation still merges in. Two DISAGREEING certified contents raise CertificateConflict. Before the join, a race loser's proposal was thrown away on the tile key's version, which is exactly the compare-and-swap this replaces.

*Where:* `holo2/src/holo2/solve/records.py:509-556`; `holo2/src/holo2/solve/records.py:559-590`; `holo2/src/holo2/solve/families.py:40-76`; `holo2/src/holo2/core/commit.py:382-439` · *dial:* live

**holo3.** There is no race to join: worker jobs are pure and every fact is folded on the single main thread as its future completes. `_fold_certificate` is the same law — an identical second certificate is a no-op that keeps the first one's source, and a disagreeing one raises IntegrityError, as does an opposite metadata bit at the same equation index. The observed-by/baselined set halves have no counterpart; holo3 tracks baselining per attempt fact instead.

*Where:* `holo3/store.py:893-920`; `holo3/engine.py:476-512`; `holo3/engine.py:184-211`

*Scheduler row / doc:* SCHEDULE.md:5-11 (the engine folds each job's facts on the main loop); D6-EXECUTION.md is the store's build record

**Implementation delta.** Same law, different reason for needing it. holo2 commits from many threads and therefore needs a merge that is idempotent, commutative and associative so a proposal can be re-applied at the wall; holo3 folds serially on the main loop, so the corroboration/conflict rule is a plain dictionary check. holo3 additionally checks the metadata bit at the equation index, which holo2 does at the close instead. The provenance rule is the same on both sides (first mint wins the source field, second is a no-op).

**Evidence status.** MEASURED

**Evidence.**

- (holo2) the commutative merge is recorded with no yield number and two eliminated failure modes: an integrity-failure kill on a lawful run, and silent last-write-wins on concurrent observation gains — *artefact:* holo2/src/holo2/solve/records.py:509-541; the seed ledger's holo2-only machinery table
- (holo3) the worker-count byte-identity baseline: K 49/49 and colour 279/279 certificates at --workers 1 and 8, same payload sha, same certificate signature — *artefact:* ARTEFACTS.md:281
- (both) zero wrong certificates across 285 target addresses in five completed crop batteries, and 0 wrong in 69,066,304 audited cells campaign-wide — *artefact:* ARTEFACTS.md:316-317, :490

**Yield relevance.** integrity — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* holo3's serial fold makes the whole class of problem unreachable rather than solving it, which is the stronger position; but it also means holo3's worker-count independence rests on the fold being serial, and PAGE-DOMAIN.md:176-181 explicitly narrows that promise to payload byte-identity (certificate SETS may now differ across worker counts because floors read fire-time live state). Worth naming in the ruling as a property that changed hands.

*Refuter (upheld):* *Corrections:* None material. holo3/store.py:893-920 verified line for line: identical second certificate is a no-op keeping the first source (:899-901), disagreement raises IntegrityError (:902-904), and the opposite-metadata-bit check at the equation index is at :905-916 exactly as the row says. The fold is on the main loop (engine.py:426-431 called from _merge at :476). The PAGE-DOMAIN caveat is real and quoted correctly — the supersession row is :110 and the Determinism section :175-181.

*Reason:* Both sides verified; the caveat about worker-count independence changing hands is the row's strongest contribution and it is accurate.

---

### extra-15 — How close two fitted geometries have to be before they count as the same pose

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter REJECTED an argument (classification word stands).

> **Refuter verdict: REJECTED.** A claim that drives this row's delta or its ruling is wrong and must be rewritten before it goes to Germano. The corrections are under Notes; read the reader's text below only through them.

**What it decides.** Whether a refit that moved only by fitter noise creates a second durable geometry (with its own evidence, its own ownership claim and its own done projection) or is absorbed into the one that already stands.

**holo2.** A pose IS its (window, page, six affine terms), so the affine is part of the durable key. The terms are rounded to six native-pixel decimals at construction and negative zero is normalised, so key and value cannot disagree and the fitter's noise terms (measured max 9.74e-7) collapse into one key instead of minting distinct ones. The quantum was ratified on 2026-08-15 after a measurement showing noise collapses while a real 3.245e-5 term stays 32 quanta wide.

*Where:* `holo2/src/holo2/solve/keys.py:36-39`; `holo2/src/holo2/solve/keys.py:106-114`; `holo2/src/holo2/solve/keys.py:68-71`; `holo2/src/holo2/solve/records.py:41-44` · *dial:* live

**holo3.** There is no pose key. A Placement is stored per window and the live one is chosen by `placement_ordinal` — refine-route last, then basis length, then quality. Two fits of one window are two Placements whichever way they differ, and the no-op guard that refuses a revision that did not move is the refine plugin's own, applied before the fact is emitted rather than at a key.

*Where:* `holo3/data.py:97-120`; `holo3/plugins/refine.py`; `holo3/store.py (placements per window)`

*Scheduler row / doc:* SCHEDULE.md key family `pose_affine`; conversion_docs/08-pose-refine.md:69-80

**Implementation delta.** holo2 makes 'the same geometry' a property of the address space (round, then the key collides); holo3 makes it a property of the producer (refuse to emit a revision that did not move). The practical difference is what happens to a fit that moved by MORE than the guard but less than anything downstream can use: holo2 mints a second pose with its own evidence lineage, holo3 appends a Placement and re-orders. The refinement family already records the no-op guard (refinement-05) and the live-pose derivation (refinement-06); this row is the address-space half neither covers.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo2) pose canonicalisation is recorded as a W0-B measurement: fitter noise terms measured max 9.74e-7 collapse at six decimals while 3.245e-5 stays 32 quanta wide — *artefact:* holo2/src/holo2/solve/records.py:41-44; holo2/src/holo2/solve/DESIGN.md:54
- (holo3) no artefact — no run report counts Placements per window, so the rate at which holo3 stores near-duplicate geometries is unmeasured — *artefact:* no artefact

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* Reads as harmless: holo3's refine no-op guard is stricter than a 1e-6 rounding, and every yield-bearing consequence of pose multiplicity (which geometry decodes, which owns a cell, what the done projection uses) is already a row in the refinement and evidence families.

*Refuter (rejected):* *Corrections:* THE HOLO3 COLUMN IS FALSE. holo3 does NOT keep two Placements for one window: holo3/store.py:623-641 holds ONE standing placement per window id (`self._placements[wid] = fact`) and admits a new one only when `_adopts` (store.py:44-46) finds the ordinal STRICTLY greater. So (a) 'Two fits of one window are two Placements whichever way they differ' is wrong; (b) 'holo3 appends a Placement and re-orders' is wrong — it replaces or discards; (c) the delta's conclusion inverts: for a fit that moved by more than the refine no-op guard, holo2 mints a SECOND durable pose alongside the first, while holo3 SUPERSEDES the standing one, bumps _pose_gen and fires KEY_POSE_AFFINE (store.py:654-662), which invalidates the evidence derived under the old geometry. A third consequence the row misses entirely: because the comparison is strict `>`, a revision that TIES the ordinal is dropped even when the affine moved, silently and with no event. Cite store.py:44-46 and :623-688, and data.py:118-120 for placement_ordinal (which is consumed by max, so refine-route WINS, then longer basis, then higher quality — the row's 'refine-route last' reads backwards). The holo2 column is exact and verified: POSE_TERM_DECIMALS=6 at keys.py:37-39 with the ratification note, canonical_affine_terms at :106-114, POSE_SPEC at :68-71, and records.py:39-42 / DESIGN.md:54 carry 9.74e-7 and 3.245e-5 / 32 quanta verbatim (DESIGN.md:54 adds a line the row should quote: 'Canonicalisation, not deduplication: equivalent-fit jitter (1.2e-3) is orders above any addressing-safe quantum').

*Reason:* The row's holo3 mechanism does not exist as described — holo3 stores one placement per window and supersedes rather than accumulates.

---

### extra-16 — The address-word contradiction as a durable fact — a legally decoded word that names a tile the geometry says is somewhere else

**ABSENT** · evidence **MEASURED** · yield **integrity** · ruling needed **Y** · seeds: B24, B25

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether the receiver has any way to notice that two placements disagree about what is printed at one position, and what the scope of that disagreement is.

**holo2.** When a word decodes legally — inside the BCH radius with five clean zero pads — but names a counter different from what the standing placements at that position claim, the receiver mints a fact keyed on the contradicted position at one footing. It carries BOTH sides' full contributor sets: the placements whose reads produced the decode, and the placements already asserting that position. Both sides are condemned identically and neither is voted on. The fact is complete at mint and frozen: a later write that revised it would be out-voting the containment after the fact.

*Where:* `holo2/src/holo2/solve/contradiction.py:33-49`; `holo2/src/holo2/solve/contradiction.py:52-126`; `holo2/src/holo2/solve/contradiction.py:128-163`; `holo2/src/holo2/solve/quarantine.py:171-194` · *dial:* live

**holo3.** absent. holo3 has integrity checks for two disagreeing CERTIFICATES and for opposite metadata bits, but nothing that compares a decoded address word against the addresses standing placements already assert, and no fact to record such a disagreement.

*Where:* _(no path given)_

*Scheduler row / doc:* no descriptor row; the term does not occur in holo3's production code

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** MEASURED

**Evidence.**

- (holo1) the expected silence: 70/70 regions, all 925 pilot tiles, ZERO contradictory reads across ~1,780 attempted known-position decodes — *artefact:* ARTEFACTS.md:444
- (holo2) quarantine cost about +2% of the verdicts wall (~1.7 s); yield zero contradictions on every healthy fixture — *artefact:* the seed ledger's holo2-only machinery table, row 'Quarantine (PL7)'
- (both) zero wrong certificates on either side at either platen angle in the holo2-vs-holo3 head-to-head, and zero wrong across 285 targets in five crop batteries — *artefact:* ARTEFACTS.md:430-432, :316-317

**Yield relevance.** integrity — source: reader.

**Recommendation.** accept the loss, and record the reason. The mechanism has never fired on healthy material in either tree's whole measured record, it cost holo2 ~2% of its wall, and the certificate layer is proof-carrying — a wrong pose fails CRC rather than producing a wrong certificate, which is what the zero-wrong audits actually test. What is genuinely lost is the diagnostic: on a sheet where addressing goes wrong (the hp c2-cmy7 refusal, 47 word matches on a 60.3% footprint) holo2 would have a named fact and holo3 has only counters. If a cheap version is ever wanted, PAGE-DOMAIN.md:194-197 already parks the adjacent idea (a CRC refuse on a certified-looking placement retrying the search's runner-up) and says it reopens with quarantine tooling.

**Notes.**

*Reader:* Three consumer-side rows already exist (placement-23, evidence-ownership-15, done-gate-08, all ABSENT). This row is the PRODUCER: without it none of those consumers has anything to consume, so the four should be ruled together as one line rather than separately.

*Refuter (upheld):* *Corrections:* Fill the empty holo3 `where` with the tree's own admission: holo3/docs/DIAG-DESIGN.md:30-31 and :153 reserve deep red for contradiction and say it is 'never painted without a contradiction producer' — holo3 stating in its own living doc that the producer is absent, which is better evidence than a grep. Second, source the cost number properly: '+2% of the verdicts wall (~1.7 s)' is at holo2/docs/MEASUREMENTS.md:1345 ('W5 quarantine ... 39, wall 79.0 s (the wave costs ~1.7 s against a bypassed baseline, +2%)'), not 'the seed ledger'. Verified as stated: holo2/src/holo2/solve/contradiction.py:33-49 keys the fact on the contradicted position at one footing, :52-126 carries both sides' contributor sets, :128-141 freezes it, :144-155 declares both sides as references; grep over holo3's production tree finds no contradiction producer. ARTEFACTS.md:444 reproduces the 70/70 regions, 925 tiles, ~1,780 reads exactly.

*Reason:* ABSENT is correct on current code, the recommendation is proportionate, and the join with placement-23 / evidence-ownership-15 / done-gate-08 is the right handling.

---

### extra-17 — Whether a resume is allowed to reuse durable facts written under a different policy, price table, provider set, format row or page domain

**ABSENT** · evidence **UNPROVEN** · yield **integrity** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader ABSENT → refuter upheld.

**What it decides.** Whether stale facts from an earlier build silently join a new run's evidence, or the run refuses to open.

**holo2.** The session identity is the envelope header: format row id, receiver policy id, the recipe's entries AS DATA (task classes, footing selectors, gates, prices, arms), the ordered provider ids, and the declared page domain. The store compares the whole value on resume, so a moved gate, a re-ordered provider binding or a changed price is a refused open — loud and un-migrated, never a quiet reinterpretation. The policy id itself was forked once, on purpose, when the placement family changed, which made every state directory under the old name refuse to open.

*Where:* `holo2/src/holo2/engine/records.py:1-25`; `holo2/src/holo2/engine/records.py:29-45`; `holo2/src/holo2/engine/session.py:41-56`; `holo2/src/holo2/engine/session.py:203-248` · *dial:* live

**holo3.** absent, and stated as such: 'there is no version stamp, no format guard and no integrity check — a snapshot is an operator's own run product, and the operator is trusted with it.' `_replay` folds every fact through the ordinary `_ingest` with no comparison against the run's declared row, price table or bound.

*Where:* `holo3/snapshot.py:19-25`; `holo3/snapshot.py:166-179`; `holo3/engine.py:248-266`

*Scheduler row / doc:* conversion_docs/ARMS-2026-08-31.md:162-173 and RULINGS:41-48 (the lean resume); API §9a

**Implementation delta.** _(the reader recorded no delta — see the classification and the two behaviour fields above)_

**Evidence status.** UNPROVEN

**Evidence.**

- (holo3) the e034 four-run resume chain: 5,543 -> 5,866 -> 5,866 -> 5,880, close VERIFIED byte-exact three times; run 3 was a +0 control — *artefact:* ARTEFACTS.md:235
- (holo3) PAGE-DOMAIN.md's own supersession table records that the page bound is 'a per-run admission filter — no resume guard, no stored policy', deliberately — *artefact:* holo3/docs/PAGE-DOMAIN.md:36-37, :112
- (holo1) the adjacent failure the record does hold: an off-catalog colour resume died at 'stream M is not declared' because a row id only meant something if a table in that build still held the row — *artefact:* ARTEFACTS.md:224

**Yield relevance.** integrity — source: reader.

**Recommendation.** port a minimal form now: stamp the format row id and the tree describe string into facts.npz and refuse (by name) a resume whose declared row differs. That is two fields and one comparison; it costs nothing and it closes the one failure mode that would be invisible — folding another sheet's certificates into this run and closing on them. Do NOT port the full holo2 identity (recipe entries and provider ids by value): holo3's arms wave moved eight rows in 24 hours, and a by-value policy comparison would have invalidated every archived facts.npz each time, which is precisely the cost the lean-resume ruling was avoiding.

**Notes.**

*Reader:* The risk is asymmetric: a mismatched resume cannot produce a WRONG certificate (certificates are proof-carrying and the close verifies a SHA), but it can waste a long run, and a facts.npz from a different tile matrix would fold certificates at coordinates this row does not have. No artefact records such an incident on holo3.

*Refuter (upheld):* *Corrections:* One citation fix: the supersession row that records 'no resume guard' is holo3/docs/PAGE-DOMAIN.md:111 ('C-8 | no resume | untouched; the bound is per-run'); :112 is C-2 about memmaps. The :36-37 quote is exact. Verified: snapshot.py:19-25 states the no-guard position, :166-179 is a bare npz write/read with no stamp of any kind, and engine.py:251-266 folds every fact through the ordinary _ingest with no comparison against the declared row. The recommendation (stamp the row id + tree describe, refuse by name, do NOT port the by-value recipe comparison) is well-aimed: the by-value half is exactly what holo2's session identity does at engine/records.py:29-45 and it is what would have invalidated every archived facts.npz during the arms wave.

*Reason:* ABSENT is correct on current code and the minimal-port recommendation is the cheapest thing that closes the one invisible failure.

---

### extra-18 — Not re-reading a capture a lineage has already read — the ingest attempt as a spendable, durable fact

**CARRIED-DIFFERENT** · evidence **UNPROVEN** · yield **decides-order-only** · ruling needed **Y** · seeds: B07

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a resumed run re-opens, re-hashes, re-surveys and re-converts every declared capture before it can do any new work.

**holo2.** One spendable attempt per declared scan, whose identity is the resolved path plus the operator's DPI, so the ledger's spend row is the durable statement 'this lineage has already read these bytes at this DPI'. The frontier mints only the FIRST declared scan whose capture record does not stand, so scan N+1 becomes expandable only when scan N has landed — one survey in flight whatever the pool width — and a resume finds nothing to mint at all because the records already stand.

*Where:* `holo2/src/holo2/solve/ingest.py:54-99`; `holo2/src/holo2/solve/ingest.py:101-128`; `holo2/src/holo2/solve/ingest.py:1-42` · *dial:* live

**holo3.** Every declared capture is re-hashed, re-decoded and re-written as a fresh ladder of per-plane uint8 memmaps in `_start`, before the frontier exists and before the snapshot is folded — on every run, including every resume. There is no memo, no record of a previous conversion and no way to say 'this one is already prepared'.

*Where:* `holo3/engine.py:102-109`; `holo3/engine.py:229-247`; `holo3/plugins/intake.py:161-241`

*Scheduler row / doc:* SCHEDULE.md:339-341; intake is not a descriptor row

**Implementation delta.** holo2 makes ingest durable work with an identity and a spend row, so a resume skips it entirely; holo3 makes it an unconditional constructor step. What that costs is a full SHA-256 pass plus a decode plus the whole decimation ladder per capture per run — v1 measured one SHA-256 pass over a 6.8 GB TIFF at about 19.1 s, and holo3 additionally writes every level of every plane. On the e034 chain that conversion ran four times over the same three (then four) captures.

**Evidence status.** UNPROVEN

**Evidence.**

- (holo1) the phased-schedule residual traced to re-authentication: the whole +169 s residual is eight extra source re-authentications, one SHA-256 pass over a 6.8 GB TIFF costing about 19.1 s — *artefact:* ARTEFACTS.md:715
- (holo3) no artefact — intake is not a plugin row, so its cost appears in no report.json plugin table; the four-run sheet-I chain's per-run walls are recorded but not decomposed — *artefact:* ARTEFACTS.md:235

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's, and measure once if resume latency ever bites. The costed measurement is cheap and is not a receiver run: time `intake.ingest_captures` alone on the sheet-I three-capture set (one process, minutes) and compare against the recorded resume walls. Note that holo3's design makes the skip harder than holo2's — holo3's derived planes live in the run directory, so a skip needs the plane files to persist and be re-validated, which is a real feature, not a flag.

**Notes.**

*Reader:* pricing-04 already covers the OVERLAP consequence of the same difference (holo2 interleaves conversion with decoding, holo3 does not). This row is the RESUME consequence, which pricing-04 does not state: holo2 pays the conversion once per lineage, holo3 once per invocation.

*Refuter (upheld):* *Corrections:* None material. holo2's one-at-a-time frontier verified verbatim at solve/ingest.py:77-99 ('The FIRST declared scan whose capture record does not stand'), and the spend identity at :101-128. holo3 side verified: _start calls _intake_run BEFORE the frontier exists and before _replay (engine.py:229-249), ingest_captures re-hashes every declared path (intake.py:224-225) and ingest_capture rewrites every plane with open_memmap mode='w+' (:134-137) — no existence test, no memo, and the run directory differs per run so the files cannot be reused. The row correctly declines to promise a number where none exists.

*Reason:* Both sides reproduce exactly; the recommendation to keep holo3's and measure only if latency bites is right, and the measurement named is genuinely not a receiver run.

---

### extra-19 — Where a page outside the run's page domain is refused — at the commit wall on the pose, or at job admission on the word

**CARRIED-DIFFERENT** · evidence **MEASURED** · yield **integrity** · ruling needed **N** · seeds: no seed (found in the code)

Classification trail: reader CARRIED-DIFFERENT → refuter upheld.

**What it decides.** Whether a placement that addresses a page the run was not told about can become a durable fact.

**holo2.** The page domain is declared once per lineage and lands in the session identity, so it is part of what a resume compares. solve's record families are then bound to it at composition: the pose family's structural validator refuses, by name, any pose whose page is outside the declared set. The refusal is at the wall, so no path in the tree can commit an out-of-domain geometry however it was derived. An empty domain registers no gate, which is what a unit test wants.

*Where:* `holo2/src/holo2/solve/families.py:382-394`; `holo2/src/holo2/solve/families.py:396-410`; `holo2/src/holo2/engine/records.py:38-45` · *dial:* live

**holo3.** The domain is dynamic. `possible` is every addressable page of the row (2^18 // tiles_per_page, capped by `--max-pages`), the LIVE set seeds {0} and grows when an address word commits a placement on a new page, and the filter is a job-side admission test in the word route rather than a wall-side validator. There is no stored domain, no resume guard, and the possible set is per-run.

*Where:* `holo3/store.py (page_domain = possible)`; `holo3/plugins/place.py (word admission filters page in possible)`; `holo3/format/identity.py:121 (max_pages)`

*Scheduler row / doc:* PAGE-DOMAIN.md:18-45 (the ruling), :59-84 (the build), :103-113 (supersessions)

**Implementation delta.** holo2 declares the domain up front and enforces it at the wall as a property of the record; holo3 derives it and enforces it at admission as a property of the job. The sets themselves differ by orders of magnitude (holo2: what the operator typed; holo3: every counter the 18-bit space addresses, ~133 pages at 53x37 and ~2621 at 10x10), and holo3's live/possible split is what makes the two cold flavours priceable. The refusal LOCATION matters for one thing only: a holo3 route other than the word route that derived an out-of-possible page would not be caught by a wall.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) the e029 page-domain qualification: base 1,357 certificates / 2,517.3 cpu-s; merged with --pages 1 (null) 1,360 / 2,557.4; merged default (133 possible pages) 1,356 / 1,639.8 — all three VERIFIED byte-exact — *artefact:* ARTEFACTS.md:104
- (holo3) floors price the address space: the full-rest floor is ~54-56 on every matrix, and the live route's lower floor admits origins rest excludes — yield, not just cost — *artefact:* holo3/docs/PAGE-DOMAIN.md:114-145

**Yield relevance.** integrity — source: reader.

**Recommendation.** _(the reader gave none)_

**Notes.**

*Reader:* The scheduling half of this — how big the domain is by default and what a cold sweep covers — is placement-25, dryness-07 and placement-11, all already written and two of them DIVERGED. This row is only the enforcement point, added because no row cites solve/families.py.

*Refuter (upheld):* *Corrections:* The holo3 `where` carries no line numbers; supply them: store.py:77-79 (page_domain = range(bound), bound = row.max_pages or --max-pages), :97 (_live_pages seeded {0}), :234-235, :674-676 (the live set grows at the placement fold); place.py:470-476 (word admission filter), :121-125 (cold flavours over live/rest), :346-362 and :365-372 (consult and regional seeds ALSO filter anchors by page_domain, which the row's 'in the word route' understates); identity.py:120-122 (max_pages = MAX_TILES // tiles_per_page). One factual fix: the live set grows on ANY Placement fold, not only 'when an address word commits a placement' — a refine or consult placement on a new page grows it too (store.py:674-676). The 'no wall' half of the delta is confirmed: _fold_placement (store.py:623-688) contains no page-domain check of any kind. holo2's wall-side validator verified at families.py:382-394 with the empty-domain clause at :396-404. ARTEFACTS.md:104 reproduces all six numbers exactly.

*Reason:* Enforcement-point delta is right and the numbers are exact; only the citations and one growth-path detail need sharpening.

---

### extra-20 — Whether a window that has been retired can ever come back

**DIVERGED** · evidence **MEASURED** · yield **decides-order-only** · ruling needed **Y** · seeds: no seed (found in the code)

Classification trail: reader DIVERGED → refuter upheld.

**What it decides.** Whether a window the scheduler gave up on can be re-armed later by new evidence.

**holo2.** A window record whose status is RETIRED is terminal at the commit wall: any write that changes it raises StateRegression, naming the retirement reason. Retirement is therefore a durable, irreversible statement about that window, and the only way back into the frontier is a different window.

*Where:* `holo2/src/holo2/solve/families.py:84-107`; `holo2/src/holo2/solve/records.py:228-244` · *dial:* live

**holo3.** Retirement is a scheduling state, not a record, and it is reversible: `_afterlife` un-retires a parent window when all four of its children have settled without placing, restoring its subscriptions and re-pushing it with cold armed. The retire predicate is re-asked at every pop, so a window whose retire cause stops holding simply stops retiring.

*Where:* `holo3/engine.py:360-385`; `holo3/engine.py:535-562`; `holo3/engine.py:564-576`

*Scheduler row / doc:* SCHEDULE.md:9-10 (retire is asked at each pop); PAGE-DOMAIN.md:143-145 (small-support windows wait for a word to open a page and re-arm via the live-pages wake)

**Implementation delta.** holo2 makes retirement a durable terminal fact (an appeal is unrepresentable); holo3 makes it a revocable scheduler bit and revokes it in exactly one place, the parent's cold afterlife. The direction is towards holo3 doing MORE work, not less, so this is not a yield loss; what changes is that holo3 has no durable record of a window having been given up on, so a census of retirement causes exists only in the event stream of the run that produced it.

**Evidence status.** MEASURED

**Evidence.**

- (holo3) retire causes are tallied per cause and emitted as WindowRetired events with the cause named; the counter appears in EngineStat — *artefact:* holo3/engine.py:360-377, :278-296
- (holo2 vs holo3) windows retired in the head-to-head: holo2 0 / holo3 4 at 0.00 degrees, 0 / 0 at 0.80; unresolved windows LEFT 196/155 and 397/281 — *artefact:* ARTEFACTS.md:415-421

**Yield relevance.** decides-order-only — source: reader.

**Recommendation.** keep holo3's

**Notes.**

*Reader:* placement-29 covers which refusals remove a window from the frontier and is already DIVERGED; this row adds only the durability question (a record versus a bit) and the one un-retirement path, which placement-08 covers on the cold side.

*Refuter (upheld):* *Corrections:* SCHEMA: a DIVERGED row with ruling_needed:false is not a state claude-plan.md §7 allows — every DIVERGED row gets a RULINGS.md entry. Set ruling_needed true and carry the existing recommendation ('keep holo3's') into it; the classification word itself is right. Mechanism verified exactly: holo3/engine.py:535-562 un-retires the parent — afterlife_used, cold_armed, dormant_since=None, retired=False, and the bookmark's own retired flag cleared with _retired_count DECREMENTED at :558-561 and its subscriptions re-registered — and _place_repush at :564-575 is the one caller. holo2's terminal law verified at families.py:84-107 (StateRegression naming the retirement reason). ARTEFACTS.md:415-422 gives 0/4 retired and 196/155, 397/281 unresolved exactly as quoted.

*Reason:* Behaviour difference is real and correctly described; only the ruling flag contradicts the row's own classification.

---

## Appendix — OUT-OF-FILTER

Plumbing: self-test, safeguards, journal/replay/leases, validation, diag rendering. One line each, never analysed. Two of these are full rows in the families above because a seed named them; the rest are the completeness pass's module list and the readers' own asides.

**Rows classified OUT-OF-FILTER.**

- `done-gate-14` — Recording the retirement cause (what a census can see): Nothing about which work runs — but it decides whether the gate's rate is measurable at all, which is why holo2's realized rate is a lower bound.
- `close-16` — The close's report channel — the counting report and the CloseCheck event: Nothing about work or certificates; it is what the operator and the diag panes read.

**Modules the completeness pass read and filed as plumbing** (`holo2/src/holo2/{solve,capture,format,engine}`).

- `holo2/src/holo2/capture/__init__.py` — package surface — re-exports only; no mechanism of its own.
- `holo2/src/holo2/capture/records.py` — record schema (CaptureRecord, FootingSpec, RegionRecord) and their key specs; the one behaviour it enables — rebuilding a survey's support grid from the store without pixels — is extra-03's row.
- `holo2/src/holo2/solve/__init__.py` — package surface — re-exports and the record-family list; no mechanism.
- `holo2/src/holo2/format/__init__.py` — package surface — re-exports.
- `holo2/src/holo2/format/envelope.py` — the payload wire layout {sha256}{len}{data} and its canonical-K / zero-tail gate; carried verbatim from v1 and already mapped as close-11 (the three unwrap gates). holo3 folds the same 36-byte overhead into format/close.py, which is a declared divergence with a live checker.
- `holo2/src/holo2/format/close_spec.py` — a narrow read-only view of the format facts a close touches, split out purely for holo2's 1000-line cap; every value is sourced from format/metadata.py and format/family.py.
- `holo2/src/holo2/engine/__init__.py` — package surface — re-exports.
- `holo2/src/holo2/engine/observe.py` — diag observation — mints one frozen snapshot of the run for the viewer on the main thread; decides nothing and holds no state, by its own contract.
- `holo2/src/holo2/engine/snapshot.py` — the counted view types the observer publishes (CommitLedger, RunSnapshot, QueueView, WorkerView); diag rendering, explicitly excluded by the filter.
- `holo2/src/holo2/engine/replay.py` — replay of a recorded commit ordering and crash recovery; the filter excludes journal/replay/leases, and holo2's own record claims debugging value with no yield number (cost 2.51x the free run).

**Named in passing by the readers, one line each.**

- placement reader: `place.subdivides()` / `SUBDIVISION_DIRECT` / `NEVER_SUBDIVIDES` in holo3 are referenced only by a test and are dead in production (noted inside row placement-06); `RETIRE_UNKNOWN` is an unreachable name the engine writes only if the retire contract is ever violated; holo2's `PlacementDomainEnvelope` (B68), `pose_audit.predict_from_anchor` (B67), `SubjectSpec`/`LabelPool` (B66) and `capture/scale_space`'s memmap arm (B69) are built-unused in holo2 with no production caller, so they change nothing on either side; holo2's cold `page_progress` heartbeat (a no-silent-stages observer callback) is absent in holo3 and touches no search state.
- evidence-ownership reader, correcting a seed: B69's "built-unused" is wrong of the current holo2 code — `capture/ingest.py:302` calls `derive_footing_rasters`, which writes into a `w+` memmap; holo2's own `docs/DESIGN.md:670-676` is the stale text behind it and should be listed with the archive's doc-vs-code contradictions.
- evidence-ownership reader, found in passing on the holo3 side: `plugins/calibrate.py:590-615 freeze_owners` has no production caller.
- close refuter: holo3's `solve` guard requires `n_certs > 0` (`engine.py:598`) where holo2's final consult calls `close_volume(())` and writes an open record — a zero-certificate run ends the same way but reports differently; and holo3's unguarded `table[index]` (`format/close.py:328`) turns an out-of-range equation index into an `IndexError` that `cli._decode` does not catch, where holo2's `coefficient_mask` validated the range. Both are authorised by the `05-fountain.md:272-277` validation-wall drop.
- done-gate refuter, cost only, unmeasured: `done_grid` is cached per page but stamped with the GLOBAL certificate count (`store.py:387-394`), so one certificate anywhere invalidates every page's grid; `done_cells` is cached per (capture, LEVEL, region) although the value is level-independent, so a five-rung capture re-derives the same array up to five times.

## Appendix — Seed rows not mapped

Nine of the 69 rows in `seeds/holo2-behaviour-ledger.md` §1 are cited by no row above. The reason in each case is the readers' own, quoted from their family notes. B50 is NOT in this list: it is cited by `extra-14`.

| seed | name | why no row cites it |
|---|---|---|
| B49 | Spend-once / read-set identity | completeness reader: the mechanism lives in `holo2/src/holo2/core/identity.py`, and `core/` is outside the four directories that pass covered (`solve`, `capture`, `format`, `engine`). |
| B51 | CRC false-accept exposure counting (L5) | completeness reader: its module (`solve/payload.py:339-366`) IS cited by an existing row, so it fell outside the completeness pass's brief; listed so the merge can decide. |
| B52 | L6 no self-training | completeness reader: same reason — `solve/tiles.py:404-415` is cited by an existing row. |
| B53 | L7 never narrow a domain | completeness reader: `engine/recipe.py:379-420` is cited by an existing row. Flagged as the one that matters: B53 is a LAW rather than a mechanism, and holo3's `PAGE-DOMAIN.md:147-151` argues its own escape from it explicitly — worth a row in the merge. |
| B59 | Continuous admission and cancel-after-terminal | completeness reader: `engine/orchestrator.py:245-330` is cited by existing rows (close-01, dryness-06 both read the cancel path). |
| B65 | Deciders / block-level DONE | completeness reader: named-not-built in holo2 — documented, no code, so there is nothing on either side to compare. |
| B66 | `SubjectSpec` / `LabelPool` durable surfaces | placement + completeness readers: built-unused in holo2 with no production caller (and `SubjectSpec` lives in `core/records.py`), so it changes nothing on either side. |
| B67 | `pose_audit.predict_from_anchor` | placement reader: built-unused in holo2, no production caller. |
| B68 | `PlacementDomainEnvelope` | placement reader: built-unused in holo2, no production caller. |

The other 60 seeds are cited by at least one row; the completeness pass separately confirms that all 81 modules of `holo2/src/holo2/{solve,capture,format,engine}` are cited somewhere across the eight families.
