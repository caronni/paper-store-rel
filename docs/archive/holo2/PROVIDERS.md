# PROVIDERS — the solve-side provider census (R1 step 0)

DRAFT for adjudication (2026-08-10). REFACTOR-WORKPLAN R1 step 0, spec-before-protocol;
document only. Every future consumer/producer of the work protocol, written down BEFORE the
protocol is frozen, so R1 items 1–3 are validated against the whole
roster and not against today's n=2 (`solve/toys.py` — deleted at H4 W1b —, `solve/placement_h3bis.py` +
`solve/payload_h3bis.py` — one module until R2 split it). **Source of
truth** is the merged `src/holo` receiver (colour-uplift landed, `ce430e3`); the PLACEMENT
leaves are frozen since 2026-08-02 (byte-identical through HEAD — W0 errata; colour-uplift
touched none of them). W0 errata note, 2026-08-15, AMENDED 2026-08-16: PL1/PL2's "spatial bucket"
subscription framing was called a foreclosure R10's push reversed — and then the PULL MODEL
reversed the push in turn (`solve/DESIGN.md`, "The placement family is ONE JOB pulled from a
scheduling set"; `holo2/docs/H4-W2-PLAN.md`, "THE PULL MODEL"). Neither framing survives:
nobody subscribes to a neighbourhood AND nobody pushes at one — a ready window consults the
committed poses it can see, at the moment it fires. PL1/PL2/PL3 carry per-row stamps below;
the rows themselves are KEPT as census history, because what they enumerate (inputs,
identities, spend granularities) is the before-picture this wave's measurements are against. Paths default to
`src/holo/receive/`, DESIGN sections are `§n`, review findings `F-nn`, open rulings `OR-n`,
measured numbers carry their source. Everything under **Spend** is a PROPOSAL for user ruling
(reviewer Q5). A *provider* expands durable facts into work descriptors and yields workers;
*subject* = what a descriptor is about; *route* = one way of attempting
the subject (one descriptor, one spend each — there are no ladders,
root DESIGN §3a); *scope* =
footing/lane/arm/region. **[corr]** amends the workplan roster.

## 1. Placement providers

### PL1 — placement/chain
Place a window from accepted neighbour poses in transport range, nearest-first
(`place.py:1237-1305`) — the cheapest rung. **Id** window / `chain` / footing. **In** anchor
poses in the window's spatial bucket, own window+region, done-reach tile keys. **Out**
PoseRecord (existence = audit witness §5.3) + evidence; audit refusal → PL5. **Spend** one
(window, `chain`, identity) per anchor-frontier version; 49 poses per anchor
(`_chain_budget` `:217-242`), never truncated — the derived support floor grows instead.
**Sched** worker; re-arms per new anchor.
**SUPERSEDED — DESCRIPTOR ROW DEAD, ALGORITHM ALIVE** (H4 W2's pull model, ruled and swept
2026-08-16). This row was BUILT on 2026-08-16 as `place_chain.ChainPlacementProvider`
(provider id `place-chain-v1`; descriptor = family `place`, subject = the window key, route
`chain`), reading its window's own durable `HintState` — and the redesign the same day
deleted the provider, the worker, the descriptor, the spend identity over hint versions and
the hint family itself (`solve/hint_state.py`, `solve/place_chain.py`, and
`place_shared.hint_writes`/`push_target_keys`, all removed from the tree). WHAT THIS ROW
DESCRIBES NOW: the CONSULT tier of the one placement job (`place_job.consult`) — the
committed poses this window can see, extrapolated through
`place_shared.predict_from_page_affine`, sorted by the ratified distance, truncated to 8,
minus the window's TRIED set; the 49-per-seed domain is unchanged and still never truncated
(the derived floor grows instead), and the kernel is still v1's `_chain_search`. There is no
spend row, no hint-state version to bind and no ring keys to bind either: the read-modify-write
that needed them is gone, so the concurrent-pusher collision the built row priced dissolved
with it. Eligibility is not expansion any more — every unfinished window is IN the scheduling
set, and an empty consult simply falls through to the word tier.
**PL2 (`lower_hint`) IS SUBSUMED, NOT BUILT**: a cross-footing donor is an ENTRY in the
consult's own portfolio at distance 0 (H4-W2-PLAN item 6, the one-currency ruling), so there
is no second route, no `inherited_hint_id` and no two-loser ledger — the fire-time query
replaced it.

### PL2 — placement/lower_hint (cross-footing) — SUBSUMED INTO PL1's CONSULT (H4 W2)
Place from a coarser footing's committed poses as a distance-ranked portfolio
(`_rank_lower_hints` `place.py:147-182`). **Id** window / `lower_hint` / (footing, donor).
**In** donor accepted poses + the retained two-loser-per-region ledger (`:320-341`). **Out**
as PL1 plus `inherited_hint_id`. **Spend** one (window, `lower_hint`, identity); domain 49 ×
portfolio, capped at `MAX_LOWER_HINTS = 8`; over-budget refuses the whole route, never a
prefix (`:1313-1315`). **Sched** worker below PL1.
**SUPERSEDED with PL1** (the pull model): a donor is one more anchor a consult sees, scored 0
by the ratified distance — `place_shared.donor_sources` in the consulting voice,
`donor_targets` in the pinging one.

### PL3 — placement/word (staged Stage A)
BCH slot decode with no prior geometry: centre slot first, widen on failure
(`place.py:1340-1352`); measured 3,627→794 ms per word-succeeding window. **Id** window /
`word` / (footing, stage ∈ {centre, rest}). **In** own sampled cells, format row, page
domain — no neighbour poses, so this seeds an anchor-free page. **Out** as PL1. **Spend**
one per (window, `word`, stage): only the centre call declares hypotheses, the rest call
adds zero; domain 147,456 for 200×200 (`words.py:162-164`). **Sched** worker.
**SUPERSEDED — DESCRIPTOR ROW DEAD, ALGORITHM ALIVE** (H4 W2's pull model, 2026-08-16). It
was BUILT on 2026-08-15 (H4 W1) as `placement.WordPlacementProvider`, provider id
`place-word-v1`, descriptor = (family `place`, subject = the window key, route `word`,
`scope.profile` = the stage), with the two stages gated on a durable `WindowRecord.SLEEPING`
because a spend row carries no version and work gated on one could never be woken (the PY3
lesson). The pull model has no descriptor to gate and no wake to arrange, so the provider and
the worker are DELETED and the staging is one boolean in `place_sched._Slot`: the two stages
are two COST CLASSES in the tier table, not two spends, and `WindowRecord` v5 no longer has a
status to stage on. WHAT SURVIVES, byte-for-byte: the Stage-A sweep plus the coupled
whole-word rival gate, as a function — `placement.decode_word_address`, called by the job
when its consult comes up EMPTY. A refused FIT still writes nothing, and the window still
re-arms when R5's `LatticeSeedRecord` appears or improves — through `place_sched._seed_ping`
now, where a read-set subscription used to do it. The stand-in `placement_h3bis`
(region-seeded sweep, one route `h3bis-word`) and `wordgrid` were DELETED with the W1 row and
have not come back.

### PL4 — placement/cold (correlation sweep) **[corr]** — BUILT AS TWO TIERS, NO PROVIDER (H4 W4)
Full-domain FFT correlation over pages × rotations (`placement/search.py:429-729`; the route
string is `correlation`, driver `run_cold`). **[corr]** per-window work with a page-batched
inner loop, NOT a batched pass over windows: `correlate_patch` runs once per window, the
region loop fires one cold per iteration (`place.py:1647-1653` — W0 errata: the bare `:1647` mis-resolved to search.py), the fan-out is over pages
(`search.py:571-578`). **Id** window / `cold` / (footing, page domain, size class, rotation)
= §8.1's cache key. **In** support mask + page-domain hypothesis set + the interference halo
it must be quiescent against. **Out** as PL1; refusal → PL5. **Spend** one (window, `cold`,
identity) = one full page×rotation sweep. **Sched** worker **plus a leased shared
resource**: the page-transform cache is invocation-scoped today (`search.py:405-407`), §8.1
makes it refcounted (~7.6 GiB for the 312-page domain, 47.9 s/patch, ~1–3 s/window at P=1).
Eligibility = cheap routes spent AND neighbourhood quiescent; concurrency = a greedy
interference-independent set, best-supported first, on memory-weighted slots.

**BUILT** (H4 W4, 2026-08-17/18 — `place_cold.py` + `place_tiers.py`, the carried kernel in
`cold.py` called and never edited). Like PL5 and PL6 it landed with NO provider and no
descriptor: cold is two TIERS of the one per-window job, so the row above is corrected on
four points rather than superseded. **Two flavours per rung, not one route** — `cold_live(d)`
= the pages this session already has a committed pose on, `cold_rest(d)` = the declared domain
minus those; the two sets PARTITION the domain, derive at fire time from committed poses and
are stored nowhere, and an empty flavour is skipped costlessly and never terminally (ruling 2).
**Priced, not gated** — 140+20·d / 150+20·d against wide's 128 at its deepest lane, with
`rest(d) < live(d+1)`, so a rung's cheap questions are exhausted before the next rung's are
asked; the "neighbourhood quiescent" precondition is the global DRYNESS gate the tier table
already carries, and the `quiesces` gate itself was deleted at H4-LANES. **The cache key is
WIDER and footing-FREE** — the kernel correlates in the cell lattice every rung shares, so
transforms are rung-invariant and the key is widened by the reference field's printed
interpretation instead (W4 plan amendment A2, recorded rather than silently followed); the
lease is `core.work.LeaseBook`, taken at bind and released on all three exits, and typed since
`LeasedWorker` (W5 item 4). **It is now PL5's trigger** — `place_job.SUBDIVISION_REFUSALS` is
`cold_refused_<flavour>`, v1's `run_cold` → `refuse_unplaced` → subdivide order restored, with
v1's two direct sites kept as `SUBDIVISION_DIRECT`. Pins: `tests/solve/test_cold.py` (23
exactness checks against direct `fftconvolve`), `tests/solve/test_place_cold.py` (the wiring),
`tests/engine/test_pool.py` (the pull-path lease) and one real firing decode
(`measure/verdicts/test_subdivision.py`).

### PL5 — placement/subdivision children — LANDED AS A SCHEDULER ESCALATION, NO PROVIDER (H4 W3)
A refusing window manufactures corner children that become new windows
(`placement/geometry.py:564-595`); triggers are `pose_refused`, `audit_refused` and cold
refusal. **Id** child window (parent + split lineage in the id, §10.2); children re-run the
whole ladder. **In** the parent's refusal + extent. **Out** durable child window specs.
**Spend** none — a frontier expansion committed with the parent's refusal; children carry
their own route spends. **Sched** NOT a worker. Depth cap 1, `min_window_cells = 70` —
§8.2/OR-9 replaces that constant with the derived floor.
**LANDED WITH NO PROVIDER OR DESCRIPTOR** (H4 W3, F-04 CLOSED — `solve/DESIGN.md`):
subdivision shipped as the pull model's own last escalation, four more in-memory scheduling-
set members born on an eligible refusal (`place_subdivide.subdivide`,
`plans.child_window_plans`) — never a provider, so the row above is corrected on three
points, not superseded outright. **No lineage in the id** — a child is named by `window_key`
from its own extent exactly like any laid-out window ("A window's split lineage is not part
of its id", `records.py`; the no-lineage ruling is `plans.child_window_plans`'s own
docstring); depth is scheduler-side stage memory (`_Slot.subdivided`), never a durable field.
**Cold IS the trigger since W4** (this clause replaces W3's "not a trigger yet", 2026-08-18):
`place_job.SUBDIVISION_REFUSALS` is now exactly the cold pair's own refusals
(`cold_refused_live` / `cold_refused_rest`), and v1's other two call sites — a fit that never
posed, an audit that refused an accepted address — are `SUBDIVISION_DIRECT`, quartering on the
spot because neither window has a correlation left to run. W3's ladder refusals
(`consult_refused`, `wide_refused`, `no_word_candidate_*`) left the set with them, so a window
correlates BEFORE it is quartered, exactly as v1 does. The growth mechanism itself moved to
`place_subdivide.py` at W6 (the file-cap seam); the scheduler keeps `_subdivide` as its entry
point. **Needs is not M3** — F-04 closed the other way: PL5 owned
`SubjectSpec` and did not use it, so a resumed parent simply re-subdivides and the kernel
names the same children; no durable subject was ever needed.

### PL6 — placement/defer→park **[corr]** — SUBSUMED INTO THE SCHEDULER'S DORMANCY (H4 W3)
A window exhausting the cheap ladder is *deferred* (`place.py:344-361`); at phase end with
`park=True` it becomes a durable **parked** fact (`:1603-1622`) that a later mop-up rebuilds
bit-exactly as its deferred set (`place_mopup` `:654-711`). **[corr]** "defer" in the roster
is this state, not a route. **Id** window / `park` / footing. **In** the window's spent
routes + extent. **Out** ParkedWindowRecord, explicitly non-terminal (`:1658-1661`).
**Spend** none — a status write; the re-offer of the expensive routes is PL4's spend at a
later scope. **Sched** in holo2 this is the §9 quiescence gate plus PL4 eligibility, not a
durable phase.
**VERIFIED SUBSUMED, NOT BUILT** (H4 W3 — H4-W3-PLAN §3 ruled this a verification wave, not
a construction one). `park=True`/`ParkedWindowRecord`/`place_mopup` never landed: a
ladder-exhausted window in holo2 simply goes dormant (`place_sched._Slot.ready = False`),
which already IS the deferred state, durable nowhere. Re-offer is the ordinary ring/donor/
seed ping (`_ping`, `_seed_ping`) — the SAME channels PL1's consult uses — never a periodic
re-pass; nothing in the scheduler polls or sweeps ("time" is not a wake channel). A
subdivided window's afterlife (PL5 above) rides the identical mechanism:
`place_subdivide.review_parents`
marks a parent `cold_parked` once every child has failed or been covered, a bit that gates
nothing and wakes nothing on its own (a child's exit updates ONLY this bookkeeping, never
the parent's ready bit), and a later ring/donor/seed ping still buys the parent an ordinary
whole-window pass at its FULL extent — v1's "consume parked windows at the base aperture"
(`place_mopup`, `place.py:674`), with no separate phase, provider or durable row. Pinned
`tests/solve/test_place_sched.py`'s park-verification block (does-not-wake-on-an-unrelated-
commit/coverage/iteration, does-wake-on-ring/donor/a-later-ping, cold-park-then-revive, and
full-tree quiescence).

### PL7 — placement/quarantine port
A BCH address contradiction quarantines the *contributing placements*, not the window: a
`KnownWord` whose counter disagrees marks all its `contributor_patch_ids`
(`placement/model.py:585-598`). **Id** (page, tile) contradiction / `quarantine` /
contributor pose set. **In** known-position words over all observations (`place.py:1688`).
**Out** the conflict fact; contributors' hints dropped and their evidence excluded from
payload while the PoseRecord is retained (`model.py:601-607,660-665`). **Spend** one per
(contradiction, contributor-set version). **Sched** a reduce over the word frontier;
src/holo never returns a quarantined contributor (W0 errata: the mechanism is model.py:643-665 — the AddressResult validator + payload filter — plus session.py:431-445's lane accumulator; place.py:800-804 is docstring prose).

**BUILT — AND IT IS NOT A PROVIDER** (H4 W5, 2026-08-18). There is no descriptor and no
spend: the reduce is part of the fire that would emit the placement, so it runs where its
inputs are (`place_shared.emit_placement` -> `quarantine.word_verdict`) and costs one
harvest plus one BCH decode per word position the window covers. Measured on the verdicts
gate's three shared decodes: 80.11 s bypassed vs 81.83 s live, ~+2%.
**Id** the contradicted position at one footing (`contradiction.contradiction_key`) —
ruling 4's scope made structural. **In** this fire's pilot reads under the audited core
(`pose_audit.observations_for_segment`, stamped with the pose that made them), reduced by
`words.known_position_words`. **Out** the `WordContradiction` fact plus the condemnation:
the standing side marked in place with ALL of its evidence, the arriving side committed
BORN QUARANTINED and emitting no evidence at all, and the window retired
(`word_contradiction`). **Never returns**: `place_job.consult` offers no marked pose and
`payload.route_evidence_keys` reads no marked piece — one predicate,
`quarantine.is_quarantined`, because "never offered" and "never decoded" must not drift.
**Staleness**: the condemnation IS the version bump on the condemned keys, so an in-flight
reader dies at the wall's existing check (ruling 3, no new mechanism). **Jurisdiction**:
UNCERTIFIED material only — a certified position is vindicated by its certificate and a
conflict there is the fatal layer's case (ruling 1), which is also why
`tilemap.project_done` never reads the marking and a condemnation moves zero done pixels.

## 2. Payload providers

### PY1 — payload/K SCAN
Judge each acquisition by itself: one frozen one-owner view per (address, capture), LDPC+CRC
(`payload_engine.py:213-243`). **Id** work key (page,ty,tx,stream) / `scan` / footing.
**In** the observation pieces on this key at this footing. **Out** certificate (terminal,
L5) or a failed attempt. **Spend** one (key, `scan`, footing, evidence-frontier identity) =
one CRC exposure at BP-60 (`solve/tiles.py:54`). **Sched** worker; eager (§8.3, no
placement→payload barrier); whole-corpus BP+CRC ~38 s vs hundreds of seconds of placement.
**BUILT** (2026-08-11, `payload.RealPayloadProvider`): one descriptor per RESIDENT
footing that holds evidence on the key, scope = the footing id. Derivation output is sorted
(ppc, footing) for determinism only — execution order is the queue's, and no payload
semantics may depend on it (§3a).
**THE SUPERSEDE WAKE** (F1, 2026-08-23, ruling J2-3): the read-set also names each covering
WINDOW's pose collection, derived by key arithmetic from the attempt's own pieces. So when a
revision becomes the live pose of an extent the standing attempt goes stale and the window's
UNCERTIFIED tiles act again at their turn — priced like any other payload attempt, no phase
and no barrier; a certified tile has retired and is not woken. This is the minimal half:
until an emitter re-samples through a revised pose (`refine.py:52-56`), the re-armed attempt
reads the same pieces and reaches the same answer. **F2 owes** the re-sample emitter and the
live-generation scoping of the freeze candidates and the ctx pool — per (tile, window) keep
only the pieces of the NEWEST pose that HAS pieces, never `index.live_pose` (which today
would delete 4,392 / 4,117 pieces, because the live pose is the one with none).

### PY2 — payload/cross-capture UNION
Sum equal-ppc frozen views from ≥2 *distinct* captures (`payload_engine.py:245-259`). **Id**
work key / `union` / ppc (the D1 correspondence). **In** the complete same-lane retained
frontier at that ppc — every contributing evidence key across captures. **Out** certificate
+ contributor set. **Spend** one (key, `union`, ppc, contributor-set identity): the
contributor SET, not one pose, is the identity — src/holo keeps `component_block_ids`.
**BUILT** (2026-08-11), and the adjudication item 4 below answers itself: the attempt's
READ-SET is its component evidence keys, and the read-set IS the §7 identity, so set-keying
is free and a new capture at that ppc is a new identity by construction. The certificate also
keeps the full component pose set (`MintRef.contributors`) for quarantine provenance.
**Sched** worker; the union is minted only where ≥2 DISTINCT captures observed the key, so L2
is eligibility and not a branch inside a fire (`payload.union_tags`).

### PY3 — payload/selective RETRY150
Exactly one BP-150 retry of the latest failed ordinary view per (address, stream), never
tunnelling past its baseline evidence (`payload_engine.py:266-296`). **Id** work key /
`retry150` / the baselined footing (hash-free — the identity law forbids a digest id; the
footing IS the baseline's name). **In/Out** as PY1 over the baseline's exact component set.
**Spend** one (key, `retry150`, footing, evidence identity); retry-always bought 1 tile per
branch for ~50k BP iterations, one retry costs 121.3 ms/tile (§8.3). **Sched** worker;
suppressed by a terminal advisory pre-close (`:261-264`); OR-5 owes the per-key ceiling.
**BUILT** (2026-08-11), REVISED same day after the adversarial review's P1: eligibility keys
on the tile's **`baselined`** set — the durable PER-FOOTING fact that THIS footing's scan ran
a decoder and failed — never on the tile-level ATTEMPTED state, which cannot say which
baseline failed and armed BP-150 on footings whose baseline never ran (and, worse,
below-floor scans wrote ATTEMPTED with no decoder run at all; they now write neither
ATTEMPTED nor a baseline). Still per footing, still gated on a versioned tile fact and never
on a spend row (a spend has no version, so an attempt gated on the ledger could never be
woken).

### PY6 — the RE-READ (placement tier `resample`, F2a)
Not a provider: a priced tier of the placement work source, because the subject is a WINDOW
and the work is a window pass, and because a provider family would need a recipe entry —
which rides `SessionIdentity` BY VALUE and would fork every archived state's lineage.
**Id** the window key; the pass is `solve/resample.resample_window`. **In** the window's
LIVE pose (`StoreIndex.live_pose`) and the page cells the SUPERSEDED generation observed,
read back off its own pieces. **Out** one evidence piece per tile at the LIVE pose's key,
plus that window's fresh PAVA fit — the ordinary `place_shared.emit_placement`, so the
calibration is v1's `_payload_reuse:311-322` and the halo is F1's, with no second spelling
of either. It carries no `sample`, so the W5 pilot firewall stays shut: v1's committed poses
"never re-enter the firewall word pool" (`place._committed_patch`). **Elig** placed AND its
live pose owns no evidence AND another pose of the extent does AND that pose is not
condemned AND the scheduler has not already answered for this geometry — one re-read per
LIVE POSE, emitted or refused, memoised on the committed pose count. **Sched** priced at
`RESAMPLE_TIER` = 200 = `COST_REFINE`: RF1's own number, because this is RF1's other half.
It pings nobody (it commits no pose). **What the old evidence does**: nothing is retracted —
the superseded pieces stay committed and stay in the attempt's read-set, and the LIVE
GENERATION rule (`solve/generation.py`, applied at `payload._pieces` and
`calibration._pieces_by_pose`) is what stops them owning cells. It is v1's lane separation
without lanes; it is deliberately NOT in the read-set, because a read-set may not shrink
(`core.identity.fold_refusal`) — MEASURED, it refused a real spend on the verdicts corpus.

### PY4 — payload/CMY7 joint stream
One packed base-7 stream per tile: one payload stream, no per-plane fallback. e032: it
FAILED on both engines while CMY8 closed, inverting the discovery ranking (mechanism is a
hypothesis, not measured). **Id** work key with `stream = main`; routes as PY1–PY3; scope =
coding. **In/Out** as PY1–PY3 over a 7-state alphabet. **Spend** identical granularity to
PY1–PY3 — the symbol is ~2.9× more cells, so the cost per spend differs, not the accounting.
**Sched** as PY1–PY3; A4b is unschedulable here (no sibling plane).

### PY5 — payload/CMY8 per-plane streams
Three independent presence-bit streams C/M/Y, each with its own LDPC equation and graceful
degradation; CERTIFIED is per work key, so a tile with only C certified is NOT done (§5.2).
**Id** (page,ty,tx,stream ∈ {C,M,Y}) — three subjects per physical tile; routes as PY1–PY3.
**In** `unresolved_streams(address)` is the frontier query. **Out** per-stream certificates.
**Spend** one per (stream, route, identity): three independent route sets on one tile.
**Sched** as PY1–PY3; a plane's certification wakes CA6, not only the close.

## 3. Calibration providers (reduces)

### CA1 — calibration/PAVA marginal (per window)
The unweighted stack-PAVA score→probability map, fit on SEARCH-parity labels and scored on
the disjoint HELDOUT parity (`solve/detect.py:250`). **Id** pool (scope = window) /
`pava-v1` / footing. **In** the window's label sites (format words + filler, later +
certified reconstructions) + the label-pool version. **Out** CalibrationRecord. **Spend**
one fit per (window, label-pool version). **Sched** reduce; fit-or-refuse, never loss-gated
(`detect.py:246-248`); floors 10/class, 10 held-out.
**The "later" LANDED (H5 P2, 2026-08-18 — `solve/certified_labels.py`), on CA2's pool.**
A certified tile's user bits, re-encoded through the format, are ground truth at all 4096
of its cells, so `CertifiedLabelSource` publishes the cold-legal field OVERLAID with the
committed certificate frontier and `calibration.region_populations` — unchanged, it only
ever read `sites`/`values` — labels from it. Two fatal disagreements, both naming the tile:
`CertificateConflict` (two certified fields at one address, v1's carried law) and
`CertifiedLabelError` (a re-encode contradicting the format at a format-known site — live,
since the payload scramble is zeroed at site cells, so a healthy certificate reproduces
word/filler bit-exactly). Mint-once twice over: per certificate by content address, and per
frontier keyed on the certified work-key tuple (certificates are terminal, L5). Re-arm is
`COLLECTION_CERTIFIED` in the fit's read-set — the collection the tile family already
declares, so no new wake kind — deliberately global, with the re-work band absorbing the
churn; a payload decode still re-arms on ADOPTION only. Quarantine is NOT applied to the
frontier: done is inviolable, and a condemned pose is a judgement about geometry.
**A CARRY BOUNDARY worth stating**: the RE-ENCODE is v1's (`certified_refine`'s
`CertifiedTileLabels`, byte-pinned in `tests/holo2_oracles/test_oracle_certified_labels.py`),
but the COMPOSITION is holo2's — v1 feeds certified reconstructions to POSE REFINEMENT
(RF1) and never to a calibration fit, whose one label channel is
`_payload_sampling.format_reference_values` with cargo at −1. The site-parity split
`(131y+17x)&1` is therefore kept for the enriched sites too; v1's block-wise holdout
(`certified_refine._block_validation`) belongs to that other fit, with its own weights.
Pins: `holo2/tests/solve/test_certified_labels.py`.

### CA2 — calibration/K ctx arm (per region)
The nine-bin ordered additive-logit correction, fitted and held-out gated per region
(`solve/detect.py`, `N_CONTEXT_BINS = 9`). Bin −1 = incomplete 8-neighbourhood: those cells
keep their marginal LLR untouched on apply and are *refused* as fit input (`:318-340`).
**Id** pool (scope = region) / `ctx-pava-v1` / footing. **In** every accepted window's
labelled cells + provisional ink for the neighbour counts. **Out** CalibrationRecord
(adopted or refused). **Spend** one fit per (region pool, member-set version): one pooled
pass, 9 block solves. **Sched** reduce; strictly gated (`candidate_loss < baseline_loss`);
floors 80/20 search, 40/10 validation.
**BUILT** (H5 P1, 2026-08-18 — `solve/calibration.py`, the carried `detect` arithmetic
called and never edited). `CtxCalibrationProvider` mints one descriptor per (footing,
region) with a committed live member: subject = the pool key, route `ctx-pava-v1`, scope =
the footing, recipe entry `calibration` at 15 + the lane term. The member-set half of the
spend identity IS the worker's read-set (§7): the pool key, the (footing, region) pose
collection (`keys.region_pose_collection_key` — the pose family's second M4 membership), the
(footing, region) EVIDENCE collection (`keys.region_evidence_collection_key` — the evidence
family's second membership, added at the F2a review 2026-08-23) and the member pose keys, so
a new placement re-arms the fit, a RE-READ re-arms it (it commits pieces at a live pose and
deliberately no pose record, so before that key existed nothing the fit read moved and v1's
"replay the affected region's coupled fit", C4 §3.3(5), never happened — MEASURED: 0 of 4
pools on either real sheet had a fit that had seen a re-read's pieces), a condemnation kills
it mid-flight, and REFITS age into the re-work band by `work_price` with no special casing.
The evidence collection buys no wake on the ordinary path: an emission commits its pose and
its pieces in ONE batch, so it bumps where the pose collection already bumped. The fit is
adopt-or-refuse INSIDE the fire — no arm chain (M8 unneeded here) — and a refusal commits its
reason as a refused CalibrationRecord. ADOPTED pool fits join
`keys.calibration_collection_key(pool)` — the ONE region-scoped key a payload decode
subscribes to, versioned on ADOPTION only — and the correction applies at DECODE ASSEMBLY
(`payload.RealPayloadWorker._decoder_input` -> `calibration.apply_component_context`):
evidence keeps its marginal LLRs forever, each footing's frozen component is corrected over
the cells each region's poses own BEFORE any cross-capture sum, and no adopted fit anywhere
returns the identical array object. **Since F1 (2026-08-23, ruling J2-2) the bins are
WINDOW-scoped, as v1's are**: each cell is binned in its OWNER's window, reconstructed from
the one-cell context halo `place_shared` writes beside every piece's cell mask
(`records.ring_masks`/`pack_piece_observation` -> `calibration.window_context_bins`), so a
tile's 252-cell border ring stops being structurally −1 (MEASURED 6.15% of cells against
v1's 1.56-2.11%). A piece written before F1 carries no halo and its component falls back to
the tile-scoped derivation, unchanged. The fit ALSO publishes, in the same params blob, the
per-member-window held-out loss the ownership freeze ranks by (ruling J2-1, DESIGN L3);
neither addition moves a record family, because the halo rides the leading-bit-compatible
observed blob and the losses ride the params array's length. Pins:
`tests/solve/test_calibration.py` (pool assembly, adopt/refuse, duplicates-weigh-one, the
staged adoption race), `tests/solve/test_freeze_ownership.py` (the freeze key, the window
scope, the blob layouts) and `tests/holo2_oracles/test_oracle_ctx_apply.py` (the applied
tensor byte-compared against v1's own code — BOTH scopes since the F1 review, 2026-08-23:
the tile-scoped fallback, and a whole 200x200 window at a non-tile-aligned origin whose
interior tiles go through halo -> `window_context_bins` -> apply and byte-compare against
v1's corrected window sliced to that tile).

### CA3 — calibration/colour A0+A1 (region detector + registration) **[corr]**
A region QDA (7 or 8 states) and its refit on registration-corrected features
(`color_stack.py:549-911`, arms `:609`/`:615`). **[corr] A2 (per-window registration): CLOSED as a measured negative (PK6, 2026-08-10) — do not build (W0 errata)** — `:86-87` records it as owed; `:569,:596` pass then `del` its declared input.
**Id** pool (scope = region; one region = one page) / `a0`,`a1` / (coding, lane). **In** the
owner selection = KnownField furniture + certified payload cells. **Out** the region
detector fit + plane residuals. **Spend** one per (region pool, arm, label version): 1 or 2
QDA fits. **Sched** reduce; A1 replaces A0 only through the standing gate `_improves`
(`:374-387`, three-way on furniture/word/dust held-out loss, slack 1e-9); refusal falls back
to the predecessor bit-exactly — the same model and array objects survive (`:326-330`).

### CA4 — calibration/colour A3 (per-window photometrics)
Six parameters per window (RGB gain + offset), weighted LS toward the incumbent QDA's class
means, shrunk toward identity (`color_locality.py:15,554`). **Id** pool (scope = window) /
`a3` / (region incumbent id, arm). **In** incumbent class means + own-window search cells.
**Out** per-window maps and, if any adopted, one region refit. **Spend** one per window map
**plus one separate spend for the region refit** — src/holo fits every window
unconditionally, paying one wasted region QDA fit when none is adopted
(`color_stack.py:635-637`). **Sched** reduce; **unreachable from the standard ladder** —
only an arm override reaches it (`:649`), see CA8.

### CA5 — calibration/colour A4 (CMY7 kind head)
`s' = a·s + b`, one scale + six offsets, damped projected Newton on the QDA's held-out side
(`color_calibration.py:18-22,322`); CMY7 only. **Id** pool (scope = region) / `a4` / coding.
**In** the QDA's held-out furniture population. **Out** `Cmy7Head` or an explicit null with
a reason. **Spend** one per (region pool, incumbent version): one Newton solve (≤50
iterations) plus one extra scoring pass over the deployment population for the saturation
floor (0.30, `color_stack.py:249,721`). **Sched** reduce; two pre-gates on two different
populations before the standing gate — the floor's measured harm case is 295 live
certificates a strict subset of the null arm's 333 (`:225-227`).

### CA6 — calibration/colour A4b (KnownField-conditioned marginals)
Per-(plane, conditioning-pattern) calibration over twelve strata: a plane's marginal
conditioned on its CERTIFIED sibling planes (`color_conditioning.py:25-28,708`); CMY8 only.
**Id** pool (scope = region) / `a4b` / (plane, pattern) stratum. **In** certified sibling
components (KnownField, `known_field.py:63-84`) + masked furniture reveals; a cheap arity
pre-count decides whether to gather at all (`color_stack.py:762-770`). **Out** per-stratum
conditioned heads. **Spend** one per (region pool, stratum, certified-frontier version) —
strata are separately identifiable and the pre-count is the cheap gate. **Sched** reduce;
woken by sibling-plane certification (PY5), not by placement; region gate measured but
forced when the arm runs (`:749-758`); unreachable except through CA8.

### CA7 — calibration/colour A5 (per-state context matrix)
One monotone 9-bin curve per (state, plane): offsets `(C,3,9)`, up to 24 curves, 3
coordinate-ascent sweeps (`color_context.py:130-136,610`); **Id** pool (scope = region) /
`a5` / coding. **In** word + dust + prior-barrier certified cells, binned by neighbour ink.
**Out** per-(state, plane) curves. **Spend** one per (region pool, incumbent version); cost
= one region-wide ink pass (`color_stack.py:834-836`) plus up to 3×states×3 curve fits,
labels capped at 40,000; `:841-843` records that hoisting the two count floors above the ink
map is owed — a descriptor-level gate gives it free. **Sched** reduce; per-curve pre-gate
then a region three-way gate. Wrong pooling's cautionary case: the retired pooled-per-plane
K port, adopted in 0 of 17 lanes for 8,648 s CPU (`color_context.py:26-31`).

### CA8 — the u-lane law as a RECIPE capability (not a provider)
An arm that cannot prove universal non-regression is not gated — it is SCHEDULED over the
uncertified residue, where per-address retirement makes it monotone by construction
(`lane_uplift.py:1-28`). Since PK-CLEAN it is the ONLY way CA4 and CA6 run at all. The arm
lives in the *lane identity*, never an ambient flag: `u<NN>-<arm>-...`, arms
`("off","a3","a4b")` in plan order; ORDER IS LOAD-BEARING — `off` runs first so a ladder
change cannot strand a tile the old path certified. K schedules none; a single-stream coding
drops `a4b` (a measured zero: 70 s wall for 0 certificates, `cascade.py:51-73`). **Id**
(holo2 shape) a RecipeEntry carrying `arm_override`, whose value enters every descriptor it
mints — so its spends are independent and a resumed state reads the arm from the descriptor,
not from a flag. **In/Out/Sched** none of its own — it re-schedules CA4/CA6/PY1–PY3 over the
residue. **Spend** none; the override is a *scope* field on those descriptors.

## 4. Refinement providers

### RF1 — refinement/K certified refine
One bounded pose revision for one window, fitted against labels reconstructed from certified
tiles (`certified_refine.py:735`); it refines the **pose only** — generation-zero
calibration is replayed frozen (`:677-702`). **Id** pose / `refine-k` / certificate-frontier
id. **In** the accumulated certificate frontier from *prior* barriers only (`:105`), own
pose, own window evidence. **Out** a *proposal*: a revised pose (transient in src/holo) that
an ordinary payload rerun from pixels must follow. **Spend** one per (pose,
certificate-frontier version); the search is a fixed two-stage grid, not an iteration — no
max-passes knob. **Sched** worker; §6's eligibility rule applies (refine only where the
reach touches uncertified residue — e024 measured ≈ zero yield otherwise); src/holo has no
such K-path gate, so holo2's is new work.
**BUILT, LIVE BY DEFAULT since W3 (RULING I2, 2026-08-23; DIALLED OFF at H5 P4, 2026-08-18 —
`solve/refine.py` + `solve/refine_fit.py`, the carried `certified_refine` arithmetic
transcribed and never edited.)**
`PoseRefineProvider` mints one descriptor per eligible (window, pose): subject = the pose
key, route `refine-k`, scope = the footing, recipe entry `refine` at **`COST_REFINE = 200`**
— the TOP of the price scale, above `cold_rest` (150, the dearest tier any other family
DECLARES), so a revision fires only when nothing cheaper is ready and "after the ladder" is
emergent rather than phased (W3, RULING I2, 2026-08-23; it was `REWORK_BASE == 90` at H5 P4,
where it fired as soon as the word bands drained). Scoped by the W3 review, 2026-08-23:
a cold pass carries a rung term ten times refine's (`COLD_COST_PER_RUNG` 20 vs
`LANE_COST_PER_RUNG` 2), so the property holds against every declared cost, every ordinary
pass at every depth, and cold through rung 2 — `cold_rest` overtakes refine from rung 3 and
`cold_live` from rung 4, both reachable at 4800 dpi. The crossover depths are pinned in
`tests/engine/test_cost_vocabulary.py`; making the property unconditional would want 240. A revision of committed geometry has no first-attempt reading either way
(calibration's 15 is the mirror image; both are one `work_price`). The certificate-frontier half of the spend identity IS
the worker's read-set (§7): `COLLECTION_CERTIFIED` plus the pose key, so a new certificate
re-arms and a condemnation kills the fire mid-flight, and nothing else can move (evidence is
frozen, and a pose's affine is its own name). ELIGIBILITY is two-sided and derived from the
tile map alone — uncertified residue in reach (the e024 gate) AND certified material in
reach (RF1's label channel is certified cargo) — so a pose with nothing to buy mints
nothing at all. Labels come from P2's `CertifiedLabelSource` unchanged; the pilot/cargo
split is the base field's site mask subtracted from the enriched one. Output is a
PROPOSAL: a NEW `PoseRecord` at a NEW key, the standing pose untouched, no certificate and
no evidence written — no new record kind, since a revised pose is a pose.
**THE DIAL, and the measurement behind it.** `revise=True` by default, since W3 (RULING I2,
2026-08-23) — at H5 P4 it was `revise=False` (the H5 P2 precedent: built, byte-pinned,
binding deferred), and `revise=False` is retained as a dial/control arm (mints nothing at
all, so a run that binds it costs no descriptor, spend, or wake). The plan expected the
eligibility gate to make RF1 a no-op on the synthetic corpus; it is a no-op only at the END,
because MID-RUN every pose has both certified labels and uncertified residue, and at H5 P4's
price of 90 the family fired as soon as the word bands drained. Measured there with
`revise=True`: **verdicts 30 green / 9 moved** (durability 3, honesty 1, seeded 3, v1-parity
2) — no wrong certificate and no moved close, every one of the nine the SAME structural
collision: a revision commits a second `PoseRecord` on one window extent (that is the
proposal shape) and the corpus asserted one pose per window extent. **The two H6 rulings
this measurement left owed were both ANSWERED at W3, RULING I2/I3, 2026-08-23**: (1) the
BARRIER TRANSLATION — v1 refines against "the accumulated certificate frontier from PRIOR
BARRIERS ONLY" (`certified_refine.CertificateFrontier`), a post-barrier pass over a settled
frontier, and holo2 has no barriers by design; answered by PRICE, not a phase (RULING I2):
at `COST_REFINE = 200`, above every other family's dearest tier, a revision fires only when
nothing cheaper is ready, so "after the ladder" is emergent — at H5 P4's 90 it fired early,
which is why the question looked like it needed a barrier. (2) whether one window may carry
more than one committed pose — ANSWERED YES (RULING I3): it may, nothing is retracted, and
the corpus assertions were re-pinned as ONE LIVE POSE per extent (`tilemap.StoreIndex.
live_pose`, the read-time derivation every consumer now reads), which is the ruling, not a
loosening. See `solve/refine.py`'s class docstring and RULINGS.md §I2–I4a for the full
record; measured yield on real sheets with the live binding is +0 certificates on both K
captures (W2/W3/W4), for +19.5%/+90% wall — see `docs/MEASUREMENTS.md`'s H6 HEALTH row.
**AND THAT +0 WAS RF1'S OTHER HALF MISSING, NOT RF1** (F2a, ruling J2-3, 2026-08-23). A
revision was committed and nothing ever sampled through it, so the payload route went on
decoding evidence read at the geometry the revision says is wrong (A2: 269/272 revised
windows, ZERO evidence on the live pose). The RE-READ is now the placement source's
`resample` tier (`solve/resample.py`) and the same resumes measure **+13 (e029, 1,910 ->
1,923) and +12 (Xerox c2-bw, 1,882 -> 1,894) certificates, ZERO lost, payload byte-identical
on both**, for +366 s / +444 s of phase-1 wall. One clause moved here with it:
`Reach.revised` — an extent that already carries a revision offers no subject at all, which
is "a revision is never itself eligible" made structural now that a revision HAS evidence,
and what bounds an extent at two generations.
**The fresh `--complete` re-run confirms it's not a resume artifact** (F2-parity,
2026-08-24, tree `01541a5`): six fresh decodes with F1's ownership key and F2's re-read
both live measure **+27 certificates on e029 (1,911→1,938) and +32 on xerox
(1,882→1,914)** against the same refine-off baselines — 60 of the 83 W4-line gap tiles
closed, zero wrong, both payloads byte-identical — for **+112%/+386% wall** (e029
1,127→2,385 s; xerox 719→3,494 s). Both sheets remain short of the v1 anchors (2 and 16
tiles respectively); the price/dial question is CLOSED (RULINGS §L1, user, 2026-08-24):
`revise=True` stays the default, at `COST_REFINE` as built — "it earned its keep"; under
the default K-stop policy the close preempts it (`holo2/docs/WORKPLAN.md` §H6,
`holo2/docs/CATCHUP-PLAN.md` "The parity re-run"). The RF1-alone (no re-read) +0-certificate figure above is superseded for
yield purposes by this pair — RF1's mechanism (a priced pose proposal) was never the
missing half; F2's re-read was.
Pins: `holo2/tests/solve/test_refine.py` (bounds at the boundary, both pilot gates and the
held-out gate on adopt and refuse arms, eligibility and re-arm, done-inviolable, the dial)
and `tests/holo2_oracles/test_oracle_refine.py` (every constant and every carried function
byte-compared against v1's own, plus an end-to-end `refine_segment` comparison whose
REVISED AFFINE byte-matches).

### RF2 — refinement/colour refine (region-granular reuse)
As RF1 for a colour window (`color_refine.py:416`), with two **crop-free** pre-gates that
refuse before any pixel read: nothing left to gain (every covered payload tile fully
certified, `:785-794`) and no certified cargo (`:796-815`). **Id** colour window/patch /
`refine-color` / (region, page). **In** certified colour projections + furniture states.
**Out** revised poses **plus the affected set** — adoption granularity is the REGION: one
adopted window forces re-derivation of every placement in its (region, page) (`:642-675`),
and unaffected regions contribute nothing. **Spend** one per (window, frontier version) for
the fit; the region recompute is a SEPARATE descriptor (subject = (region, page)), so one
adopted window ⇒ one region delta is priced once. **Sched** worker + a region-scoped
follow-on reduce; post-barrier, single-pass.

## 5. The close

**NOT a provider family** (worklist B12, RULED 2026-08-12). CL1/CL2 below
are the close's *behaviour* and stay accurate as such; the R1 sentence
that made it a provider does not. The close is the engine's TERMINAL
CONSUMER (`engine.orchestrator.CloseConsult`, implemented by
`solve.VolumeClose`): it expands nothing, mints no descriptor, takes no
work id, holds no lease and writes no spend row. What survives of "Id /
Spend" below is one integer the ENGINE records — the version of the
consumer's declared `frontier` key (`collection:certified`), consulted
only when it moves, which is the same eligibility the spend test gave
and is why the O(1) arming claim (M11) still holds.

### CL1 — close/K single-stream
Certified tiles → metadata → K → fountain-v2 per block → envelope → **the stop is the SHA,
never a count** (`fountain_close.py:1-27,505`). R1 item 3 makes this a provider, which
removes the engine→format edge. **Id** the close key / `consult` / stream set. **In** every
certified tile key — the read-set is exactly those keys (`engine/orchestrator.py:596-600`).
**Out** CloseRecord (OPEN | VERIFIED(sha, bytes_ref) | INTEGRITY_FAILURE | UNSUPPORTED;
terminal is immutable §5.5). **Spend** one per certified-frontier identity — which makes
re-consulting an unchanged frontier idle by the ordinary §7 test. **Sched** preemptive: a
verified close beats everything (measured 3.7×, §9); cost O(certified tiles) per frontier
change, and src/holo's relief is a per-(stream, block) shortfall baseline making a skip
provably open (`production_close.py:52-95`) — derived, not a spend.

### CL2 — close/multi-stream
One decoder per stream, all of which must solve (`fountain_close.py`, the
`len(spec.stream_profiles) != 1` branch); per-(stream, block) accounting throughout, since a
global symbol count is duplicate-gameable (measured, F6). **In/Out** as CL1. **Id** as CL1
with scope = the stream tuple; per-stream decoders are NOT separate subjects (the SHA is
over the assembled volume). **Spend** one per certified-frontier identity, exactly as CL1 —
a per-stream spend could report a partial close. **Sched** as CL1; the count gate reports
metadata-terminal states as *ready* so the consult materialises their exact durable result
(`:435-447`).

## 6. Capture-side providers

### CP1 — capture/incremental attachment
Add a capture to a live session, or resume with one detached (src/holo: a phased per-capture
plan with a durable prefix, `runtime.py:278-300`). **Id** capture sha256 / `attach` / the
interpretation (declared DPI → footing ladder). **In** an authenticated raster + the durable
capture catalogue. **Out** CaptureRecord, FootingSpecs, RegionRecords + masks — a *frontier
expansion* creating the window subjects PL1–PL7 need. **Spend** none: ingest and survey are
idempotent and content-addressed. **Sched** not a worker in R1; the hard requirements are
that payload work runs with no raster attached and that physical work whose raster is
detached SLEEPS on an attachment dependency instead of disappearing (F-05).

### CP2 — capture/multi-capture union frontier (F1∘F6)
Maintain the retained same-lane evidence frontier PY2 consumes
(`payload_engine.py:245-259`). Measured law: equal-weight combining LOSES to best-single on
a global detector and WINS after the ctx detector de-correlates bias; 3–4 scans/sheet is the
knee (CLAUDE.md). **Id** the (page,ty,tx,stream,ppc) accumulator; no route of its own.
**In** each capture's frozen per-footing view at that ppc. **Out** nothing durable —
derived, and footing-in-key makes an illegal cross-aperture sum unrepresentable (§5.4).
**Spend** none; the spend is PY2's. **Sched** a COLLECTION whose membership must be
subscribable (M4): a new capture's evidence must wake PY2 on keys whose ids did not exist
when PY2 declared its read-set.

## 7. Observers (outside the work protocol)

**OB1 diag panes/status** (`holo2/src/holo2/diag/status.py`) reads the commit stream, an
orchestrator snapshot callable and the store, read-only, failures swallowed; it must answer
queue depth/composition, running/sleeping/retired, sleeping-by-subscription-key, fire
counts, wakes-per-commit, useful-rerun ratio, **cold candidates and transform-cache
refcount/residency**, tile-map/done/close progress (§10.3). **OB2 finalize** (`:566`) swaps
live frames for terminal ones at termination. **OB3 trace auditor**
(`holo2/src/holo2/core/trace.py`) records commit ORDERING plus sampled digests — the honesty
canary for L11 and for producer change flags. **Spend** none: observers are not providers
and must never need a work identity. **Sched** none; the protocol's only duties toward them
are the no-silent-stages contract (`core/work.py`, §10.3) and making PL4's cache lifecycle
observable.

## 8. Protocol validation

### 8.1 The minimal R1 protocol under test
- **P1 Declaration** — a provider declares (task family, the frontier resources it
  expands from, a descriptor id scheme). Descriptor = (recipe-entry identity, family,
  subject key, route/profile, footing/scope).
- **P2 Expansion** — `expand(view) -> descriptors`, incremental over its declared
  frontiers; the engine enumerates providers, never branching on a family name.
- **P3 Worker input** — a read-only `SolveView`: typed store queries, bounded raster
  crops, format row, frontier reads. No store, commit engine, index, clock, blob append.
- **P4 Proposal** — staged blobs + fact writes + one spend (descriptor, identity,
  outcome); the commit authority re-derives the read-set and materialises accepted blobs.

### 8.2 Every census row against P1–P4

| Row | P1 | P2 | P3 | P4 | Needs |
|---|---|---|---|---|---|
| PL1 chain | ok | ok | ok | ok | M1, M4 (BUILT H4 W2; M4 is now the hint KEY, not a bucket) |
| PL2 lower_hint | — | — | — | — | subsumed into PL1 at H4 W2: a donor is an entry in one portfolio |
| PL3 word | ok | ok | ok | ok | M1 (stage as route) |
| PL4 cold | ok | ok | ok | ok | M1, M2, M5 |
| PL5 subdivision | — | — | — | — | landed with no provider/descriptor at all (H4 W3, F-04 CLOSED): four in-memory scheduling-set members named by `window_key`, never a durable subject — `SubjectSpec`/M3 unminted (`solve/DESIGN.md` F-04) |
| PL6 defer→park | — | — | — | — | subsumed into the scheduler's own state at H4 W3 (verified, not built — H4-W3-PLAN §3): a ladder-exhausted window simply goes dormant and re-offers only on the ring/donor/seed ping (`place_sched._Slot.ready`, `cold_parked`), never a provider — pinned `tests/solve/test_place_sched.py` |
| PL7 quarantine | ok | ok | ok | ok | M7, M10 |
| PY1 K SCAN | ok | ok | ok | ok | M1, M4, M6 |
| PY2 UNION | ok | ok | ok | ok | M1, M4, M10 |
| PY3 RETRY150 | ok | ok | ok | ok | M1 |
| PY4 CMY7 | ok | ok | ok | ok | M1 |
| PY5 CMY8 | ok | ok | ok | ok | M1 |
| CA1 PAVA | ok | ok | ok | ok | M6, M7 |
| CA2 K ctx | ok | ok | ok | ok | M4, M6, M7 |
| CA3 A0/A1 | ok | ok | ok | ok | M6, M7, M8 |
| CA4 A3 | ok | ok | ok | ok | M7, M8, M9 |
| CA5 A4 | ok | ok | ok | ok | M7, M8 |
| CA6 A4b | ok | ok | ok | ok | M4, M7, M8, M9 |
| CA7 A5 | ok | ok | ok | ok | M7, M8 |
| CA8 u-lane | — | — | — | — | M9 (recipe capability) |
| RF1 K refine | ok | ok | ok | ok | M2, M4, M7 |
| RF2 colour refine | ok | ok | ok | ok | M2, M7 (region follow-on) |
| CL1 close K | ok | ok | ok | ok | M6, M11 |
| CL2 close multi | ok | ok | ok | ok | M6, M11 |
| CP1 attachment | ok | ok | — | ok | M3, M12 |
| CP2 union frontier | — | — | — | — | M4 (a collection) |
| OB1–OB3 | — | — | — | — | none; must not be forced in |

No row is refused by P1–P4; twelve capabilities are missing *below* the protocol, and four
rows (PL5, CA8, CP2, OB1–OB3) are deliberately NOT providers.

### 8.3 Missing capabilities (what / why / smallest form)
- **M1 Per-route descriptors** — 12 rows attempt one subject; key the engine's
  worker/declined/spend tables by the descriptor tuple, not the subject.
- **M2 Re-offerable declines** — PL4's cold gate, PL6's park→mop-up and RF1/RF2's
  closure gate become eligible later: `Decline(wake_on=keys)`, no permanent declined set.
- **M3 Provider-minted subjects** — PL5 children and CP1 captures/regions must enter the
  authoritative domain: a durable subject-spec fact + a versioned collection key (F-04).
- **M4 Collection-membership resources** — subscribe to a collection, not today's members
  (PY1/PY2, CA2/CA6, PL1, CP2): one versioned bucket key per collection (OR-7).
- **M5 Leased shared resources** — PL4's transform cache needs scheduler-owned
  refcounting, memory weighting and an interference rule: a lease around a fire.
- **M6 Staged blobs in the proposal** — CA1–CA7, PY1–PY5 and CL1/CL2 all emit bulk:
  `WorkResult.blobs` plus ref rewrite at commit.
- **M7 Non-window, non-tile subjects** — pools, poses, (region,page), close, captures,
  contradictions: the subject key becomes any `ResourceKey`.
- **M8 Ordered arm ladders with refuse-to-predecessor** — CA3–CA7 are a greedy stack:
  scope carries the incumbent calibration id and refusal commits a reason.
- **M9 Arm-override scope from the recipe** — CA4/CA6 are otherwise unreachable and the
  u-lane law forbids an ambient flag: `RecipeEntry.arm_override` in descriptor scope.
- **M10 Contributor sets in provenance** — PY2 unions captures, PL7 quarantines a
  contributor set: `MintRef` takes the descriptor digest + contributors (F-06).
- **M11 Cheap derived gate for the close** — a derived close-progress view keyed by
  frontier digest, read before the O(certified) consult (§9 choice 1).
- **M12 Capture attachment as a dependency** — an attachment resource per capture, so
  resume-with-B-only cannot fail on A's footings and physical work sleeps (F-05).

### 8.4 What R1 built (2026-08-10)

The protocol landed as `core/work.py` (descriptors, providers, workers, proposals) plus
`core/view.py` + `solve/view.py` (the read-only worker input). Where each capability
stands:

| Cap | Form in the tree | Consumer today |
|---|---|---|
| M1 | `WorkDescriptor.route`; the engine's worker/decline/spend tables key on `work_id` = (family, subject, route, scope) | every provider; **the payload family mints one descriptor per route since 2026-08-11** |
| M2 | `Decline(reason, wake_on=())`; `wake_on` sleeps the descriptor and re-offers it, empty is permanent | placement (attachment), unit-tested |
| M3 | `SubjectSpec` record + `collection:subjects/<family>`; a subject fact expands the domain | test-only split provider (no production subdivision) |
| M4 | per-family `collections` declarations (R3: `core.registry`) + resource-table counters: `collection:evidence/<key>`, `collection:certified`, `collection:captures`, `collection:poses/<window>` | payload (evidence arrival), placement (`collection:poses/<window>` since W-B B7, 2026-08-12 — the M4 hole closed), the terminal consumer's frontier (`collection:certified`, M11) |
| M5 | `Lease` + `LeaseBook`: refcount + weight held around a fire, published in the snapshot. NO admission control | declared; the cold route prices it |
| M6 | `WorkResult.blobs` staged via `stage_array`/`stage_bytes`; `CommitEngine` materialises accepted ones and REFUSES a batch referencing bulk it does not hold | every writing worker |
| M7 | descriptor subject is any `ResourceKey` | close (close key), split (subject key) |
| M8 | `WorkScope.incumbent` | data only |
| M9 | `RecipeEntry.arm` → `ExpansionRequest.arm` → `WorkScope.arm` | data only |
| M10 | `MintRef.contributors`, plus `route` + `decoder_profile` (tile family v2) | the payload UNION populates the set; every attempt names itself and its decoder |
| M11 | close read-set = `collection:certified` (its version is the member count, exact because certificates are terminal), so a consult arms in O(1) | close |
| M12 | `attachment_key(capture)` + decline-with-wake when a raster is detached | placement; the record schema is R3's |
| — | **W1 addendum**: the `place` family's read-set now names `collection:poses/<window>` for the window and its siblings PLUS `collection:certified` (the §6 gate's other half, exact and O(1) where an unplaced window can derive no page reach), and NOT sibling window records — a sibling's own verdict cannot move this window's gate. W2's per-region done summary (OR-7) replaces the frontier key with a precise one |

**Per-route payload descriptors landed 2026-08-11** (PY1-PY3 above): SCAN/UNION/RETRY150
no longer run inside one fire, so one CRC-bearing attempt is one spend and the lineage's
false-accept exposure is a COUNT (`payload.crc_exposure`, published on the plane and in
the orchestrator snapshot) instead of the estimate over fires the review objected to. No
protocol change was needed — the descriptor already carried a route, exactly as R1 planned.
The certificate-set and payload byte-equality of both e2e gates is what says the decode
semantics are unchanged.

Deliberately NOT built: any calibration or refinement provider (their families do not exist
yet). **AMENDED at H5 P1 (2026-08-18): the calibration family exists — CA2 above is BUILT
as `solve/calibration.CtxCalibrationProvider`; CA1's enrichment (certified reconstructions)
is P2's, the colour arms CA3–CA7 stay H7's, and refinement stays unbuilt.**
**AMENDED again at H5 P2 (2026-08-18): the enrichment is BUILT
(`solve/certified_labels.py`, CA1 row above) and lands on CA2's region pool, which is the
only calibration pool that exists — CA1's own per-window PAVA provider is still unbuilt,
so "CA1's enrichment" names the census ROW the label channel comes from, not a provider.**

## 9. Adjudication list

**Spend granularity (Q5), one ruling per provider.** Every **Spend** above is a proposal;
the contested ones:
1. PL3 — `centre` and `rest` as two spends or one? Two make the staging resumable.
2. PL4 — one spend per (window, page-domain version), or per (window, page) so a
  per-scrap page collapse is priced?
3. PL5 — children spend nothing themselves; confirm.
4. PY2 — **ANSWERED by the build**: the union's read-set is its component evidence keys and
  the read-set IS the identity, so it is contributor-SET keyed without a separate mechanism;
  a new capture at that ppc is a new identity, which is the intended re-run.
5. PY3 + OR-5 — the per-key attempt ceiling under re-arming frontiers.
6. PY5 — confirm the per-plane spend is the CRC-budget unit.
7. CA4 — per-window map spends + one region-refit spend (proposed), vs one region spend.
8. CA6 — per-stratum spends (proposed) vs one region spend.
9. CL1/CL2 — one spend per certified-frontier identity, explicitly NOT per stream (a
  per-stream spend could report a partial close).
10. CP1 — ingest/survey spend nothing (proposed) but must expand the frontier.

**Rulings this census surfaces.**
11. **Cold is per-window, not a batched pass** — the roster conflicts with §8.1 and with
  src/holo; correct it (PL4).
12. **A2 (per-window registration) does not exist** — declared and unread. Keep it in the
  roster as owed, or drop it?
13. **Is refinement a provider or a recipe phase?** src/holo makes it a lane R(Lk),
  post-barrier and single-pass; §9 calls it a later entry.
14. **Is the u-lane a recipe capability (CA8, proposed) or a provider?** Either way, M9.
15. **Close preemption vs close-as-provider** (R1 item 3) — a queue-ordered close defeats
  its own 3.7× purpose. May the engine fire it out of band?
16. **Quarantine terminality** (OR-10/L8) — port src/holo's never-return rule, or reopen?
17. **Which of M1–M12 land in R1.** M1/M2/M6/M7 look irreducible; M3/M4/M5/M10/M11/M12
  are arguably R2–R3 and review-round work.
18. OR-9 (derived window floors) and OR-11 (children zero-padding into the cold cache
  shape) are inputs to PL4/PL5 and stay open.
