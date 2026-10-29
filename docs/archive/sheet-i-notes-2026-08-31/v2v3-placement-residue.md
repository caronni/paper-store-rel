# The coarse-lane placement residue: holo2 vs holo3

Read-only audit plus a measured head-to-head, 2026-08-31.

Instruments (all new, all under `measure/`, nothing under `src/holo`,
`holo2/src` or `holo3/` touched):

| file | what it does |
|---|---|
| `measure/angle_residue.py` | cuts the crop, synthesises the platen angle, runs one arm |
| `measure/angle_residue_h2.py` | runs holo2's own CLI with a placement census wrapped around its scheduler |
| `measure/angle_residue_census.py` | reads both sides' recorded artifacts into one table |
| `measure/angle_residue_nyquist.py` | probes each receiver's own coarse-lane lattice fit |

Artifacts: `scratch/angle-residue/`.

---

## 0. The verdict up front

**The hypothesis is REFUTED on the mechanism it names, and measured
head-to-head on identical material holo2 is the worse of the two.**

Four decodes, one crop of a real HP K sheet, two synthetic platen angles,
each tiff handed unchanged to both receivers (§5):

| | holo2 0.00 | holo3 0.00 | holo2 0.80 | holo3 0.80 |
|---|---:|---:|---:|---:|
| unresolved windows left | **196** | 155 | **397** | 281 |
| windows *retired* | **0** | 4 | **0** | 0 |
| lane-0 (2 px/cell) failure | **54.6%** | 37.1% | **81.6%** | 58.3% |
| placement cpu on unresolved windows | **60.2%** | 49.2% | **75.4%** | 62.5% |
| correlation tier's share of placement cpu | 69.7% | 67.8% | **83.2%** | 78.6% |
| certificates | 100 | **112** | 56 | **82** |
| wall | 1,370 s | **842 s** | 1,206 s | **786 s** |

* **holo2 does not resolve or retire these windows.** It retires *nothing*
  — `counts_end["retired"] == 0` on both arms — and every survivor is
  parked by *dormancy*, with `tier() is None`. It leaves more of them than
  holo3, and it pays a larger share of its placement budget for them.
* **holo2's dryness gate saves nothing on a run that drains.** Both runs
  go to full exhaustion, and a gate that only *defers* cannot remove
  work. Measured: holo2's first cold fire sits at 44%/36% of its
  placement stream, holo3's at 53%/44% — holo3's plain price ladder
  already reproduces the ordering at `--workers 1` (§5b).
* **The refusal is inherited and identical in both trees.** At 2 px/cell
  the printed cell fundamental sits on the Nyquist bin of
  `np.fft.rfft2`'s last column, where `|X[+ky, N/2]| == |X[−ky, N/2]|`,
  so the magnitude argmax cannot recover the *sign* of the platen
  rotation. Measured (§2): at ppc 2 both receivers return `|θ|` for every
  θ; at ppc 4 and 8 both return θ correctly 10/10; the two trees agree to
  the printed digit. **No scheduling change on either side can turn a
  mirrored coarse window into a placed one.**
* **Zero wrong certificates on either side at either angle** (0
  disagreeing bit vectors on 99 and 56 shared addresses); at 0.80 deg
  holo3's certificate set is a strict superset of holo2's.

What holo3 *does* have that holo2 does not is a longer **tail** — one
window fired 18 times against holo2's worst of 7 — driven by a
region-wide, bidirectional consult reach whose offer set never dries
(§1a). But that same reach is what places the coarse lane at all:
28-80% of every lane-0 chain pose in four datasets comes from an anchor
holo2's rule would never have offered (§3).

So the proposal should **cap the repetition, not narrow the reach**, and
the real fix for the residue is the coarse-lane fit, not the scheduler
(§7).

---

## 1. Lifecycle of a window whose chain consult keeps failing

### 1a. The two reaches — the finding that explains the re-fire loop

This is the single largest mechanism difference, and it is not about
gating.

**holo2's ring consult reaches 8 same-lane neighbours plus *coarser*
lanes only.**

```
place_job.py:293-314  _anchor_plans(view, plan, wide=False)
                      -> (*ring_targets(view, plan), *donor_sources(view, plan))
place_shared.py:688   ring_targets: view.window_plans(plan.footing_id)   # SAME footing
place_shared.py:752-758  donor_sources: skip footing if footing.ppc >= target.ppc
place_shared.py:727-729  donor_targets: skip footing if footing.ppc <= source.ppc
```

`donor_sources` keeps only **coarser** footings; `donor_targets` (the
ping direction) keeps only **finer** ones. A lane-0 window (`ppc = 2`,
the coarsest) therefore has **no donor sources at all** and can only
ever consult its own eight lane-0 neighbours. Symmetrically, a lane-3
pose pings only lanes finer than lane 3 — i.e. nobody. **In holo2,
information about poses flows strictly coarse → fine, and a coarse-lane
window can never be seeded or woken by a fine-lane pose.**

**holo3's ring consult reaches the whole region, at every lane.**

```
place_sched.py:62-75   anchors_of(store, wid):
                         for owid in store.placements():
                             if owid[0] != capture_id or owid[2] != region_index: continue
                       # NO level filter, NO direction filter
place.py:346-362       consult_seeds(...): sort by distance, keep
                         WIDE_ANCHORS if wide else CONSULT_KEEP
place.py:26-27         CONSULT_KEEP = 8 ; WIDE_ANCHORS = 8      # the SAME number
```

Two consequences:

1. **holo3's ring tier IS holo2's wide tier.** In holo2 the wide tier's
   whole content is "nearest-K anchors *at any distance*, every footing
   of the capture" (`place_job.py:307-314`), priced at 120 and **gated**
   (`place_tiers.py:163-166`). holo3 spends that reach at the ring tier,
   priced 40 and ungated; the only thing its `wide` adds is the
   regional-affine seed (`place_sched.py:86-90`). Since
   `WIDE_ANCHORS == CONSULT_KEEP == 8`, holo3's `wide` is nearly a no-op:
   in the measured run it fired 344 times and settled `nothing_to_try`
   almost every time (§3).
2. **The offer set never dries.** Anchor ids carry the pose generation
   (`place_sched.py:72`: `f"pose/{level}/{ordinal}/g{generation}"`), and
   `untried_consult` subtracts the tried set (`place_sched.py:78-92`).
   Every fine-lane pose that lands anywhere near a dead coarse window —
   and every pose *revision* by `refine`/`revisit`, which bumps the
   generation — mints a fresh candidate id, so `stage_of(offered=True,…)`
   returns `ring` again (`place.py:92-99`) and the window re-fires. The
   supply of fresh seeds grows with the run.

### 1b. What re-arms a window

**holo3** — the engine's generic read-set fan-out. A place row declares:

```
place_sched.py:201-217  _place_reads:
    (KEY_LATTICE_SEED, capture, level, region)
    (KEY_LIVE_PAGES,)                                   # a GLOBAL key
    for level in capture.levels:                        # EVERY lane
        for other in ring_neighbour_extents(...):  (KEY_POSE_AFFINE, (cap, level, region, other))
        if level.index != level_index:             (KEY_POSE_AFFINE, (cap, level, region, extent))
engine.py:411-425       _touch: any write to a declared key -> version += 1, _push_worker
store.py:652-660        a Placement whose affine moved bumps KEY_POSE_AFFINE
```

So a lane-0 window is woken by pose commits *and pose revisions* on its
ring extents at **all four lanes**, by any lattice-seed improvement in
its region, and once by the live-pages key. `refine` and `revisit` write
pose facts (`refine` 105 poses, `revisit` 28 in the measured control
run) and every one of those is a wake.

**holo2** — one explicit ping, from accepted placement poses only.

```
place_sched.py:817-835  _ping(view, plan): ring_targets + donor_targets, only slots still in the set
place_sched.py:837-856  _seed_ping: a superseding lattice seed wakes that (footing, region)'s dormant slots
place_sched.py:738-747  the re-read path pings NOBODY — "a re-read commits no pose … revised by
                        a family that pings nobody. MEASURED: pinging here woke the subdivision
                        arm's dormant parent for three passes"
```

There is no engine subscription for placement at all
(`orchestrator.py:426-449`: *"No spend-once test and no subscription —
the source owns 'may this run again?'"*).

### 1c. When wide / cold may fire

**holo2 — gated, exactly:**

```
place_tiers.py:163-176   TIER_WIDE (120)  gated=True
                         TIER_COLD_LIVE (140), TIER_COLD_REST (150)  gated=True
place_sched.py:596-597   SourceJob(..., gated=TIER_PRICE[tier].gated)
orchestrator.py:389-395  if job.gated:
                             in_play = queue in-flight costs + source in-flight costs + queue head cost
                             if in_play and min(in_play) < job.cost: return None
orchestrator.py:398-417  _pop_armed re-enumerates providers on a dry queue BEFORE letting a gated tier in
```

Predicate: *a gated job may not start while anything cheaper is ready
**or in flight**, anywhere.* Note what that adds over a plain price
order: by the time `_next` reaches the `job.gated` branch it has already
returned `"queue"` if anything cheaper was READY, so the **only** thing
the gate contributes is the **in-flight** clause and the re-enumeration
in `_pop_armed`. At `--workers 1` that clause can hold at most one job,
which is exactly what §5 measures. Payload (20 + 2·d) sits below every
placement rung by ruling (`place_tiers.py:20-26`), so cold cannot run
while a tile decode that might delete the window is still going.

**holo3 — ungated.** `engine._fill` pops the heap head and runs it:

```
engine.py:434-475  while len(inflight) < workers and frontier:
                       cost, seq, plugin, stage, subject = heappop(frontier)
                       ... no gate, no in-flight comparison ...
                       future = executor.submit(job)
engine.py:317-319  heappush(frontier, (cost, seq, plugin, stage, subject))
```

This is a **spec divergence, not a design choice**. holo3's own
conversion spec says otherwise:

> `holo3/conversion_docs/13-engine-diag-cli.md:110-115` —
> *"a. FILL: … GATING — a job with cost >= 120 (wide/cold/refine band) is
> admitted only if no cheaper job is ready or in flight (the Q3+Q6 rule:
> 'a cold search on everything remaining before all payload is decoded
> burns us')."*

and again in `wave2-reports.md:67` item (5): *"wide + both colds are
GATED behind global dryness incl. payload drain"*.

With `--workers 1` the heap order already gives "nothing cheaper
**ready**"; what is missing is the **in-flight** clause and the
re-enumeration. With more workers the gap widens.

### 1d. Terminal states

**holo3** (`place_sched.py:225-248`, `engine.py:361-386`):

| clause | set where | leaves `WindowRetired.cause` |
|---|---|---|
| `placed` | `store.py:664-666` on an accepted Placement | `placed` |
| `exhausted` | `store.py:603` (`insufficient_support`) **or** `engine.py:575` (ladder empty *and* subdivision produced no children) | `exhausted` |
| `done_covered` | `store.window_fully_done` (`store.py:447-486`) | `done_covered` |

**A window whose ladder is exhausted but which *has* children never
retires** — `engine._place_repush` returns early:

```
engine.py:565-576
    if ladder_stage(...) is not None: repush; return
    if not state.subdivided:
        self._subdivide(state)
        if state.children: return          # <-- the parent stays live, forever re-armable
    state.retired = True
```

**holo2** (`place_sched.py:902-905` `_exit`, and its callers): `placed`,
`settled_placed`, `done_covered`, `outside_the_reading_set`, and the two
*retiring* refusals `unschedulable_region` / `region_not_materialized`
(`place_shared.py:521,530`). Everything else stays a member and goes
**dormant** — `tier()` returns `None`, and `_enqueue` clears the ready
bit and does not push (`place_sched.py:895-900`). Dormancy is not an
exit, but with a bounded ping supply it is terminal in practice.

Note the one place holo3 is *more* terminal: `insufficient_support`
retires in holo3 (`store.py:602-604`) and does **not** in holo2
(`place_shared.py:550` returns a refusal with no `retire`).

### 1e. Subdivision

Both quarter a window at most once, one generation deep, with a 70-cell
floor, into the same four corner extents
(`pose.subdivision_child_extents` 814-830 vs `plans.child_window_plans`).
Both charge a child `CHILD_PREMIUM = 5` on every tier.

The gate differs:

* **holo2** subdivides only on an outcome in `SUBDIVISION_REFUSALS`
  (`place_subdivide.py:98`) = `{pose_refused, straddle_audit_refused,
  cold_refused_cold_live, cold_refused_cold_rest}`, and only from the
  dormant branch of `settle` (`place_sched.py:779-804`).
* **holo3** subdivides on *ladder exhaustion, whatever the outcome*
  (`engine.py:565-576`). `place.subdivides()` (`place.py:111-114`) and
  `place.NEVER_SUBDIVIDES` (`place.py:59`) exist and are **never called
  anywhere in holo3** — dead code. In practice the ladder only empties
  after cold, so the two mostly coincide; the divergence bites when a
  cold flavour has no pages to sweep (`stage_of`'s
  `cold_live_ready`/`cold_rest_ready` are false) and holo3 quarters a
  window holo2 would have left whole.

### 1f. The heap key

| | holo2 | holo3 |
|---|---|---|
| key | `(price, offered_distance, ordinal)` — `place_slot.py:220-225` | `(cost, seq, plugin, stage, subject)` — `engine.py:317-319` |
| distance leg | **yes** (ruling R-A: Dijkstra-flavoured frontier growth along the most confident edges) | **absent** |
| re-fire price | flat, `Slot.price` has no attempt term (`place_tiers.py:65-69`: *"PLACEMENT takes no term"*) | flat, `_place_cost` ignores `attempts` (`place_sched.py:255-258`) |
| round-robin on wake | ordinal bumped to the back (`place_sched.py:888-891`) | new `seq` on every push (`engine.py:314-316`) |

holo3's frontier is therefore FIFO within a price class. A window
adjacent to a pose that just landed is worked at exactly the same
priority as one nowhere near any anchor.

### 1g. Side by side

| question | holo2 | holo3 |
|---|---|---|
| **(a) when may wide/cold fire** | gated: not while anything cheaper is ready **or in flight** (`orchestrator.py:389-395`); tiers declared `gated=True` (`place_tiers.py:163-176`) | ungated: whenever it is the frontier head (`engine.py:434-475`). Spec says it should be gated (`13-engine-diag-cli.md:110-115`) |
| **(b) what re-arms it** | `_ping` from an **accepted pose** to its own-footing ring + **finer** footings; `_seed_ping` on a better lattice seed. RF1 revisions ping nobody | any write to a declared read key: `KEY_POSE_AFFINE` on ring extents at **every lane** + the same extent at every other lane, `KEY_LATTICE_SEED`, the global `KEY_LIVE_PAGES` — and `refine`/`revisit` pose revisions all bump it |
| **(b′) seed reach at the cheap tier** | 8 own-lane neighbours + **coarser** lanes covering it. A lane-0 window sees only lane 0 | nearest 8 of **every pose in the region at any lane**; ids carry the pose generation, so revisions mint fresh untried seeds |
| **(c) terminal refusal short of success** | `unschedulable_region`, `region_not_materialized` (durable `WindowRecord(RETIRED)`); `insufficient_support` does **not** retire. Everything else = **dormancy**, revived only by a ping whose supply is bounded | `insufficient_support` retires; ladder-exhausted-with-no-children retires. A ladder-exhausted parent **with** children never retires and stays re-armable for the rest of the run |
| **(d) subdivision** | 4 corners, depth ≤ 1, ≥70 cells, +5 premium; **gated** on `SUBDIVISION_REFUSALS` | identical geometry and premium; **ungated** — fires on ladder exhaustion whatever the outcome. `place.subdivides()` is dead code |
| **(e) end of run** | survivors sit in `_slots` dormant (`tier() is None`), heap holds tombstones only | survivors sit as live `WorkerBookmark`s with no frontier seat; any later key bump would re-push them |

---

## 2. The refusal itself is inherited — the coarse-lane fit probe

`measure/angle_residue_nyquist.py` renders a printed cell lattice at a
chosen pixels-per-cell, rotates it by ±θ, and asks **each receiver's own**
`lattice_reciprocal` what rotation it sees
(`holo3/plugins/pose.py:333-372`, `holo2/src/holo2/solve/pose_fit.py:408`).
10 seeded trials per cell, 200-cell windows — the production window size.

```
ppc=2.0  window=200 cells (400 px)  trials=10
  theta |                 holo3 fitted |                 holo2 fitted
  -0.80 |   med  +0.798  sign-ok 10/10 |   med  +0.798  sign-ok 10/10
  -0.40 |   med  +0.390  sign-ok 10/10 |   med  +0.390  sign-ok 10/10
  +0.00 |   med +27.282  sign-ok 10/10 |   med +27.282  sign-ok 10/10
  +0.40 |    med  +0.389  sign-ok  0/10 |    med  +0.389  sign-ok  0/10
  +0.80 |    med  +0.798  sign-ok  0/10 |    med  +0.798  sign-ok  0/10

ppc=4.0 and ppc=8.0: every angle, every trial, both trees — sign-ok 10/10,
magnitude correct to three decimals (-0.800 / -0.400 / -0.000 / +0.400 / +0.800).
```

Read it as: **at 2 px/cell the fit returns `|θ|` — the magnitude is right
to about 0.01 deg, the sign is a constant `+`.** The "10/10" on the
negative rows is not a success: it is the mirror happening to land on the
right sign there, and the same constant `+` scores 0/10 on the positive
rows. At 4 and 8 px/cell the sign is recovered every time, at every angle.
The two receivers agree to the printed digit at every cell of the table,
because the fit is the same ported code.

The mechanism is arithmetic, not tuning. `lattice_reciprocal` takes
`np.abs(np.fft.rfft2(gradient))` and argmaxes it inside a radial band.
At `ppc = 2` the cell fundamental is `1/2 = 0.5` cyc/px, which is
`rfftfreq`'s **last** column; for even N that column is
Hermitian-symmetric, so `|X[+k_y, N/2]| == |X[-k_y, N/2]|` and the
argmax is a coin flip between `+θ` and `−θ`. `_normalize_reciprocal`
(`pose.py:322-330`) then canonicalises what it was handed and cannot
recover what the magnitude spectrum destroyed.

**Consequence for the residue.** A mirrored window fits its own lattice
at `−θ` while the page really sits at `+θ`, so its sampling grid shears
by `2·θ` across the window: `200 · tan(2 × 0.8°) = 5.6` cells at 0.8 deg,
against a `NEIGHBOR_RADIUS_CELLS = 3` search box and a
`CONSISTENCY_CELLS = 2` acceptance budget (`place.py:23-24`). No origin
in the box can clear the gate — which is exactly the `consult_refused`
that is 92-100% of every recorded residue. At 0.06 deg the same
arithmetic gives 0.42 cells, mostly survivable, which is why the
straight captures fail at 6-13% instead of 95%. The measured curve
(post-mortem §5) is what a doubled-angle shear predicts.

**This is the load-bearing finding for the proposal: no scheduling
change — holo2's gate, holo2's reach, a placement-coverage gate, a
dryness rule — can turn a mirrored coarse window into a placed one.**
Scheduling can only decide how much the refusal costs. holo2 is not
better at placing these windows; the probe says it is exactly as bad.

### 2a. Subdivision makes the coarse lane strictly worse

The same probe at 100 cells — the size a subdivided child gets — with
everything else unchanged:

```
ppc=2.0  window=100 cells (200 px)  trials=8
  -0.80 | med +0.781  (truth 0.800)      +0.40 | med +0.561  (truth 0.400)
  -0.40 | med +0.561                     +0.80 | med +0.781
```

The mirror is still there **and the magnitude degrades** — a true 0.40 deg
reads as 0.56 (a 40% error) at 100 cells against 0.389 at 200 cells,
because halving the window halves the FFT's frequency resolution while the
fundamental stays pinned to the Nyquist bin. **Quartering a refused
coarse-lane window cannot help it and provably hurts the fit.** holo3
produces four such children on every ladder exhaustion
(`engine.py:565-576`) — that is the 4x chip inflation the post-mortem
measured (ord6: 1,150 of 1,448 orange chips were 100x100 children), and it
is entirely waste on lane 0.

---

## 3. What holo3's region-wide reach is BUYING

Before recommending that holo3 adopt holo2's bounded reach, it has to be
priced. `measure/angle_residue_census.reach_report` replays the pose
stream in order and asks, at each accepted **chain** commit, whether an
anchor holo2 would have offered existed yet — a same-lane ring neighbour,
or a coarser lane whose extent contains this one. Three datasets:

| dataset | chain poses | not reachable under holo2's rule | lane 0 specifically |
|---|---:|---:|---:|
| this report's crop, 0.00 deg (HP K) | 323 | 62 (19%) | **57 of 86 (66%)** |
| this report's crop, 0.80 deg (HP K) | 261 | 41 (16%) | **41 of 51 (80%)** |
| e029 whole sheet (HP K, 1 capture) | 1,226 | 101 (8.2%) | **101 of 354 (28.5%)** |
| sheet-H max-stack (7 captures, 0.06–1.05 deg) | 8,185 | 1,748 (21.4%) | **1,672 of 3,091 (54.1%)** |

Lanes 2 and 3 are at 0.0% on both sheets — the fine lanes place
themselves. **The coarse lane is a net CONSUMER of fine-lane poses**, and
between a quarter and four fifths of every lane-0 chain pose holo3
commits comes from an anchor holo2's directional rule would never have
offered.

This is an upper bound on the loss (a window denied an anchor at time T
may be placed later by a different one), but it is measured on four
independent runs and it points the same way in all four — **and §5
closes the loop directly: holo2, which HAS the narrow reach, failed
54.6% / 81.6% of its coarse lane on the identical tiffs against holo3's
37.1% / 58.3%.**

**So: holo3's ungated region-wide ring reach is both the re-fire engine
and the coarse lane's only real supply of addresses.** Any proposal that
narrows the reach trades yield for CPU. Any proposal that keeps the reach
but caps how often the same window may re-consult it does not.

---

## 4. What the ungated tiers actually cost, on recorded runs

Read off the archived event files with the same cost-inversion the census
uses (`stage_for_cost`): a `JobDone`'s recorded `cost` names the stage
exactly, because parent prices are even and a child adds 5.

| run | outcome | total job cpu | place cpu | `cold_live` fires | `cold_live` cpu | share of place | **poses cold produced** |
|---|---|---:|---:|---:|---:|---:|---:|
| sheet-H max-stack (7 captures, cmy8) | open | 121,968 s | 9,866 s (8.1%) | 5,163 | 6,452 s | **65.4%** | **0** |
| e029 whole sheet (HP K) | **verified, 465,580 B** | 3,149 s | 486 s (15.4%) | 157 | 206 s | **42.4%** | **0** |
| xerox-k whole sheet | **verified, 465,580 B** | 5,590 s | 146 s (2.6%) | 12 | 19 s | 13.0% | **0** |
| this report's crop, 0.00 deg | open | 802 s | 383 s (47.8%) | 241 | 260 s | **67.8%** | 34 of 377 |
| this report's crop, 0.80 deg | open | 763 s | 494 s (64.7%) | 363 | 388 s | **78.6%** | 52 of 327 |

**On all three whole-sheet runs the correlation tier committed zero
poses — 5,332 fires between them — while taking 13-65% of every placement
second.** Two of the three closed byte-exact anyway.

The crops are the counter-example and it matters: a crop is *fragmentary*
(62 and 80 tiny regions against a whole sheet's **one**, no page-wide
address chain), and there cold earned 34 of 377 and 52 of 327 poses. So
the finding is **not** "cold is useless" — it is
"cold earns nothing where the chain reaches, and holo2's gate is a
DEFERRAL, not a refusal, so it cannot take that away."

The rest of the ladder on the same runs:

| run | `ring` fires | `ring` cpu | `wide` fires | `wide` cpu |
|---|---:|---:|---:|---:|
| sheet-H max-stack | 22,205 | 1,934 s (19.6%) | 3,800 | 114 s (1.2%) |
| e029 | 2,040 | 215 s (44.3%) | 127 | 3 s (0.7%) |
| xerox-k | 1,134 | 117 s (80.1%) | 12 | 0.4 s (0.2%) |

Two things fall out:

* **`wide` is a near-no-op in holo3** and its only real function is to
  set `wide_spent`, which arms cold (`store.py:592-594`). 94% of the
  crop control's 344 wide fires settled `nothing_to_try` — because
  `WIDE_ANCHORS == CONSULT_KEEP` and the ring already tried those eight
  anchors, so a wide pass has only the regional-affine seed left to try
  and usually not even that. holo3's ladder is therefore
  *cheap-ring → words → free-pass → expensive-cold*, with nothing
  between the ring and cold that actually widens anything.
* **`ring` fires 2.7x per chain pose on sheet H** (22,205 fires,
  8,185 chain poses), 1.4x on xerox-k. That ratio is the re-fire loop of
  §1a-2 showing up as arithmetic.

### 4a. The Nyquist column, shown

The top spectral peaks inside the fit's own eligibility annulus, for the
same lattice rotated ±0.8 deg (`_windowed_gradient` + `np.fft.rfft2`,
both receivers' own code path):

```
ppc=2.0 theta=+0.8   fy=+0.00750  fx=0.50000  |X|=433.1   <-- last column
                     fy=-0.00750  fx=0.50000  |X|=433.1   <-- last column
ppc=2.0 theta=-0.8   fy=+0.00750  fx=0.50000  |X|=432.6   <-- last column
                     fy=-0.00750  fx=0.50000  |X|=432.6   <-- last column

ppc=4.0 theta=+0.8   fy=-0.00375  fx=0.25000  |X|=8605.4
ppc=4.0 theta=-0.8   fy=+0.00375  fx=0.25000  |X|=8601.2
```

At `ppc = 2` the `+fy` and `−fy` peaks carry **the same magnitude to four
significant figures**, and the spectrum at `+0.8` is indistinguishable
from the spectrum at `−0.8`. The argmax tie is broken by array scan
order, not by the data. At `ppc = 4` there is one peak and its sign is
the rotation's.

---

## 5. The measured head-to-head

**Material.** There is no angled K capture on this machine — the two
local K captures are the e029 HP sheet
(`scratch/e028/hp-canon-c2-ink-counting.tiff`, Canon 4800 grey,
`L:c2-r0700@3392x2368`) at **0.061 deg** and the xerox-k sheet at
**0.046 deg**, both at the straight end of the sheet-H ladder. So the
angle is synthesised (task option c): **one** 1000x1000-cell crop
(16,010 x 16,034 px, 257 MB) is cut once from the e029 capture and copied
through the **same** order-3 spline `affine_transform` with the **same**
half-pixel sampling offset at 0.00 and 0.80 deg, so interpolation blur is
a constant and rotation is the only variable. Both receivers are handed
the identical tiff. `--workers 1`, `--no-close`, one decode at a time.

### 5a. Same material, both receivers — the operator's claim, tested

| | **holo2** 0.00 | **holo3** 0.00 | **holo2** 0.80 | **holo3** 0.80 |
|---|---:|---:|---:|---:|
| wall | 1,369.5 s | **842.4 s** | 1,206.1 s | **785.8 s** |
| peak RSS observed | ~7.4 GB | ~1.5 GB | ~7 GB | ~1.4 GB |
| **certificates** | 100 | **112** | 56 | **82** |
| poses committed | 338 (+261 re-reads) | 377 | 287 | 327 |
| **windows retired** | **0** | 4 (`done_covered`) | **0** | **0** |
| **unresolved at end** | **196** | **155** | **397** | **281** |
| of those, subdivided children | 139 (71%) | 106 (68%) | 294 (74%) | 202 (72%) |
| **lane-0 failure rate** | **54.6%** | **37.1%** | **81.6%** | **58.3%** |
| lanes 1 / 2 / 3 | 27.4 / 28.2 / 25.7% | 23.0 / 27.4 / 22.0% | 40.2 / 40.2 / 38.9% | 39.4 / 39.4 / 38.9% |
| place fires | 1,957 | 1,763 | 2,692 | 2,224 |
| place cpu | 365.7 s | 383.4 s | 566.7 s | 493.9 s |
| fires on unresolved windows | 807 (41.2%) | 730 (41.4%) | 1,591 (59.1%) | 1,178 (53.0%) |
| **cpu on unresolved windows** | **220.2 s (60.2%)** | **188.6 s (49.2%)** | **427.1 s (75.4%)** | **308.4 s (62.5%)** |
| `cold_live` fires / cpu | 232 / 254.9 s (**69.7%** of place) | 241 / 259.9 s (**67.8%**) | 445 / 471.5 s (**83.2%**) | 363 / 388.1 s (**78.6%**) |
| `wide` fires / cpu | 360 / 1.0 s | 344 / 0.6 s | 606 / 1.3 s | 514 / 0.6 s |
| max fires on one window | 7 | 18 | 6 | 10 |
| mean fires per unresolved window | 4.12 | 4.71 | 4.01 | 4.19 |
| first `cold` fire (place-fire ordinal) | #860 / 1,957 (44%) | #926 / 1,763 (53%) | #967 / 2,692 (36%) | #978 / 2,224 (44%) |

**Read that top to bottom and the operator's hypothesis does not
survive.** On identical material, at both angles, holo2

* leaves **more** unresolved windows than holo3 — 196 vs 155 straight,
  **397 vs 281** angled,
* fails **more** of the coarse lane — 54.6% vs 37.1% straight,
  **81.6% vs 58.3%** angled,
* **retires nothing at all**: its entire residue leaves by *dormancy*,
  never by a verdict (`counts_end["retired"] == 0` on both arms, and
  every surviving slot has `tier() is None`). holo3 at least retires
  four windows through the done gate on the straight arm,
* spends a **larger** share of its placement seconds on windows that end
  unresolved — 60.2% vs 49.2% straight, **75.4% vs 62.5%** angled,
* spends the **same or more** on the correlation tier: 232 fires /
  69.7% of place straight (holo3: 241 / 67.8%), 445 fires / **83.2%**
  angled (holo3: 363 / 78.6%),
* in 1.5-1.6x the wall time, at ~5x the memory, for **fewer
  certificates** — 100 vs 112 straight, **56 vs 82** angled.

The one thing holo3 does worse is the **tail**: one holo3 window fired 18
times against holo2's worst of 7 (10 vs 6 on the angled arm). That is the
re-fire loop of §1a-2, and it is real — but it is a tail, not the bulk.
The bulk of both receivers' residue cost is the *same* thing: an
effectively ungated correlation tier grinding on windows whose coarse-lane
fit is mirrored.

**Zero wrong certificates on either side, at either angle.** Comparing
the two receivers' certified user-bit vectors on shared addresses
(`measure/angle_residue_certs.py`, reading holo3's `facts.npz` and
holo2's store):

| arm | shared | holo3-only | holo2-only | **disagreeing bit vectors** |
|---|---:|---:|---:|---:|
| 0.00 deg | 99 | 13 | 1 | **0** |
| 0.80 deg | 56 | 26 | 0 | **0** |

At 0.80 deg holo3's certificate set is a strict superset of holo2's.

### 5b. Why holo2's gate changes nothing here

Both runs go to **full exhaustion** — holo2's own epilogue says *"no
worker can contribute on any recipe entry — the session is exhausted"* —
and a gate that only **defers** cannot save work in a run that drains.
Measured: holo2's first cold fire sits at 44% (straight) / 36% (angled)
of the placement stream; holo3's at 53% / 44%. **holo3's plain price
ladder already reproduces — in fact slightly improves on — holo2's gate
ordering at `--workers 1`.** The gate's remaining content (§1c) is the
in-flight clause, which at one worker can hold at most one job.

The gate's value is therefore *not* what the hypothesis assumed. It is
still worth having, for two other reasons: multi-worker runs, where the
in-flight clause bites; and runs that **close early**, where deferred
cold work is never paid at all — e029 closed byte-exact having spent
206 s (42% of its placement) on 157 cold fires that produced zero poses
(§4).

### 5c. What the angle costs, per receiver

| 0.00 → 0.80 deg | holo2 | holo3 |
|---|---|---|
| unresolved | 196 → **397** (+103%) | 155 → **281** (+81%) |
| lane-0 failure | 54.6% → **81.6%** | 37.1% → **58.3%** |
| place cpu | 366 → 567 s (+55%) | 383 → 494 s (+29%) |
| cold cpu | 255 → 472 s (+85%) | 260 → 388 s (+49%) |
| certificates | 100 → 56 (−44%) | 112 → 82 (−27%) |

Direction and rough magnitude match the sheet-H angle ladder in the
post-mortem, at a smaller angle on a much smaller field — and holo3
degrades **less** than holo2 on every row.

*Caveat on this pair.* The rotated raster also changed what the survey
found: **80 regions and 936,585 supported cells** against **62 regions
and 1,125,432** on the straight arm. Part of the angled arm's extra
difficulty is that, not placement. The A/B between *receivers* at a fixed
angle is clean — identical tiff, one variable — but the A/B between
*angles* is not purely angle.

---

## 6. Findings for the proposal, ranked by evidence strength

Yield is sacred, so every row says what it could suppress.

### R1 — Open the escalation door on placement re-fires. *(strongest, and yield-safe by construction)*

**Evidence: direct.** holo3's placement price ignores the fire ordinal
(`place_sched.py:255-258`), and its offer set does not dry (§1a-2), so a
refused window can be re-consulted without limit — 22,205 ring fires for
8,185 chain poses on sheet H, up to 18 fires on one window in the crop
control, 5,959 `consult_refused` settles over 1,448 windows in the
original post-mortem.

holo2 exempts placement from its re-work band *for a stated reason*
(`place_tiers.py:65-69`): *"this table prices a work SOURCE, whose
repetition is bounded by the ready bit and the tried set"*. **That
premise is false in holo3** — the tried set does not bound anything when
the anchor id carries the pose generation and the anchor pool is the
whole region.

holo3 already has the mechanism, already ruled, already in production on
two rows: `uplift.py:325-331` and `plane_k.py:665-673`, both documented
as *"the escalation door … Nothing is capped — the row may fire as often
as new evidence justifies — it just drifts behind cheaper work each
time."*

**What holo3 would adopt:** make `_place_cost` multiply (or add a band
to) the price by `attempts`, exactly as `_uplift_cost`/`_planek_cost` do.

**What it risks:** nothing is refused, so no window that would have
certified is suppressed — the tail simply sinks below productive work.
The only real risk is *ordering*: a late, genuinely-good seed reaches a
much-re-fired window later than it does today. On a run that reaches
dryness the outcome is identical; on one that closes early, the deferred
fire is deferred past a close it was not contributing to.

### R2 — Implement the dryness gate holo3's own spec already requires.

**Evidence: direct and recorded.** `13-engine-diag-cli.md:110-115` and
`wave2-reports.md:67` item (5) both specify it; `engine._fill`
(`engine.py:434-475`) does not implement it. Cold is 13-65% of placement
CPU on the archived runs and produced **0 poses in all three whole-sheet
runs** (§4).

**But the measured value is smaller than it looks (§5b).** In the
head-to-head, holo2 *with* the gate fired cold at 44%/36% of its
placement stream and holo3 *without* it at 53%/44% — holo3's plain price
ladder already orders cold as late or later, and both runs drained to
exhaustion, where a deferral saves nothing. The gate pays only where the
run stops before placement dries: the verified e029 decode spent 206 s
(42% of its placement) on 157 cold fires that produced zero poses.

**What holo3 would adopt:** the `gated` flag on the descriptor's price
row plus the in-flight clause of `orchestrator._next`
(`orchestrator.py:389-395`), and the re-enumeration of
`_pop_armed:398-417`.

**What it risks:** on *fragmentary* material cold is not decorative — it
earned 34 of 377 poses on this report's 62-region crop, and confetti
sessions are fragmentary by definition. Because the gate is a
**deferral**, a run that reaches dryness still fires every cold pass it
would have fired, so the fragment case is protected by construction. The
real exposure is a run killed or closed before dryness: there, a cold
pose that would have been found is not. Given that both verified sheet
runs found zero cold poses, that exposure looks small — but it is a
population claim on n = 3 and should be re-measured on a confetti state
before the flip.

### R3 — Do **not** narrow holo3's consult reach to holo2's.

**Evidence: direct, four datasets (§3).** Between 28.5% and **80%** of
every lane-0 chain pose holo3 commits comes from an anchor holo2's
ring+coarser-donor rule would never have offered. The coarse lane is a
net consumer of fine-lane poses; holo2 forbids that direction outright
(`place_shared.py:727-729,752-758`).

**And the head-to-head confirms the consequence.** holo2, whose reach is
the narrow one, failed **54.6%** of its coarse lane on the straight crop
and **81.6%** on the angled one, against holo3's 37.1% and 58.3% on the
identical tiffs — and produced 12 and 26 fewer certificates.

This is the one place where "adopt holo2's mechanism" would trade yield
for CPU, and it is exactly the lane the operator is worried about.
**Recommendation: keep the reach, cap the repetition (R1).**

### R4 — Bound the re-offer supply without touching the reach.

Two surgical changes, both with holo2 precedent:

* **One steer per anchor WINDOW, not per pose generation.** holo3's
  candidate id is `pose/{level}/{ordinal}/g{generation}`
  (`place_sched.py:72`), so every adopted refinement of a neighbour
  mints a fresh untried trial. holo2 ruled this the other way (I3,
  `place_job.py:342-353`): *"ONE STEER PER ANCHOR WINDOW: its LIVE
  pose"*, keyed on the pose id, with the reason spelled out —
  offering both spends two of the eight slots on one neighbour and
  weights it twice.
  *Risk:* a revision that genuinely moves the affine is never retried.
  Mitigation: keep the generation in the id only when the affine moved
  by more than the ±2-cell consistency budget — below that the search
  box already covers the difference.
* **Do not wake a place row on a pose REVISION.** holo2 records this as
  measured: *"pinging here woke the subdivision arm's dormant parent for
  three passes that offered it a seed it had already tried"*
  (`place_sched.py:738-747`). holo3 wakes on every `RefineOutcome` that
  moves an affine (`store.py:652-660` → `engine._touch`).
  *Risk:* low — the revised pose still steers a window that fires for
  another reason.

### R5 — Gate subdivision, and never subdivide on the coarsest lane.

**Evidence: direct.** `place.subdivides()` and `place.NEVER_SUBDIVIDES`
exist in holo3 and are called from nowhere (`place.py:57-59,111-114`);
`engine._place_repush` quarters on ladder exhaustion whatever the
outcome. And the fit probe at 100 cells (§2a) shows subdivision makes the
coarse-lane fit **strictly worse** — the mirror persists and the
magnitude error grows from 0.011 to 0.161 deg.

Subdivision is the 4x chip inflation the post-mortem measured (1,150 of
ord6's 1,448 orange chips were children).

**What holo3 would adopt:** wire the predicate that already exists, and
add "not at `lane_depth == 0` while the fit is sign-degenerate".
*Risk:* a coarse-lane window that a quarter would have placed is not
quartered. The probe says that window does not exist at ppc 2; the
discriminating test is an A/B decode counting lane-0 child poses.

### R6 — The placement-coverage gate: real, but smaller than advertised, and it interacts with R3.

Recorded upper bounds (`OPEN-2026-08-31.md`): 51% / 46% / 91% / 47% of
place CPU. Measured here on the crop control: 20 unresolved windows whose
**exact extent** another lane already posed (37.4 s, 9.8% of place), 59
under the looser **covered-by** rule (81.7 s, 21%).

**What it risks — and this is new information for that ruling.** The
OPEN doc already flags "a suppressed coarse pose may be the seed a
neighbour consulted". §3 makes that concrete: because holo3's ring is
region-wide, a lane-0 pose is in *every* lane's nearest-8 candidate pool,
not just lane 0's. Retiring lane-0 windows therefore removes anchors from
the whole region's supply. The gate suppresses *unplaced* windows, so it
cannot remove an existing anchor — but it can prevent one from ever
existing. Discriminating test remains an A/B decode.

### R7 — The offered-distance leg. *(lowest priority)*

holo3's heap key is `(cost, seq)`; holo2's is
`(price, offered_distance, ordinal)`. The effect is bounded: within one
pass holo3 already sorts its eight seeds by distance
(`place.py:360-362`), so what is lost is only the cross-window ordering.
Worth noting, not worth building first.

---

## 7. The thing none of the above fixes

**R1-R7 are all about cost.** The refusal is a fit defect at 2 px/cell
(§2, §4a) and it is holo2's defect too. Four ways out, none built, in
rising order of invasiveness:

1. **Try both sign hypotheses at ppc 2.** The fit already produces
   `frequencies`; at the coarsest lane, run the downstream search for
   both `±fy` and keep whichever clears the parity gate. Strictly a
   superset of what is tried today, so it **cannot** lose a window —
   the only cost is up to 2x the search on one lane.
2. **Move the coarsest rung off Nyquist.** `MINIMUM_PPC` is exactly 2 in
   both trees (`holo3/lib/decimate.py:9`;
   `holo2/.../scale_space.py:147-150`). A floor of, say, 5/2 puts the
   fundamental at 0.4 cyc/px, off the last column, at a modest cost in
   the coarse lane's speed advantage.
3. **Inherit the sign from a committed neighbour.** The chain consult
   already holds a neighbour's page affine before it predicts; its
   rotation sign could seed `fit_window_pose` the way `prior_f` already
   seeds the peak search (`pose.py:338-344`).
4. **Drop the ppc-2 lane** and measure what it costs. Cheapest to try,
   most likely to lose yield — lane 0 returned 179 certificates on the
   post-mortem's worst capture.

Option 1 is the one that cannot lose a window, and it is the one to
price first.

---

## 8. Honest gaps

* **The Nyquist probe is synthetic.** It renders an ideal binary cell
  lattice, area-decimates it and rotates with `ndimage`; a printed sheet
  has toner blur, development anisotropy and scanner MTF. The *mirror*
  is an arithmetic property of `rfft2`'s last column and does not depend
  on the material, but the exact failure rates on paper do. The sign
  convention is inferred from the ppc 4/8 rows, where it is unambiguous
  and consistent across 80 trials.
* **The head-to-head is on a CROP, and a crop is not a sheet.** The
  survey finds **62 regions** on this 1000x1000-cell crop against **1**
  on a whole sheet, so the crop's placement problem is 62 separate
  bootstraps. That is why cold earned 34 poses here and 0 on every
  archived sheet run. The A/B comparisons *within* the crop are sound —
  identical material, one variable — but the absolute levels are not a
  sheet's.
* **The angle is synthetic.** No angled K capture exists on this
  machine: the two local K captures are e029 at 0.061 deg and xerox-k at
  0.046 deg. The angle was introduced by an order-3 spline
  `affine_transform` applied identically (same half-pixel sampling
  offset) to every arm, so interpolation blur is a constant and the
  angle is the only variable — but it is not a platen.
* **The reach numbers are upper bounds.** "Not reachable under holo2's
  rule *at that instant*" is not "would never have been placed": a
  different anchor could arrive later. §5's head-to-head is the A/B that
  settles the direction (holo2's narrower reach does fail more of the
  coarse lane on identical material) but not the exact magnitude.
* **Only one crop, one location, one sheet.** Four decodes on one
  1000x1000-cell rectangle of one HP K capture. The two receiver-vs-
  receiver comparisons are each one paired observation, not a
  population; a second crop from a different part of the sheet — and one
  from the xerox-k capture — would cost about an hour each and is the
  obvious next step if any of this is to carry a ruling.
* **`--workers 1` throughout.** That is the setting under which holo2's
  gate has the least to do (§5b). A multi-worker rerun is where the
  in-flight clause would show whatever it is worth.
* **`cold` produced 0 poses in three whole-sheet runs.** That is n = 3,
  all K or cmy8 on one format row, and none of them a confetti session.
* **holo2's per-lane totals are approximate.** The census wrapper sees a
  window when it first *fires*; holo2 exits a window admitted already
  placed or already covered without ever claiming it
  (`place_sched.py:331-357` writes `_exited` directly, not through
  `_exit`). The live counts, the fire ledger and the CPU are exact; the
  denominators are not.

## 9. Appendix — reproducing this

```sh
# material: one 1000x1000-cell crop of the e029 HP K sheet (Canon 4800 grey),
# copied at 0.00 and 0.80 deg through the SAME order-3 spline
PYTHONPATH=. env/bin/python -m measure.angle_residue cut --angles 0.00 0.80

# one arm at a time (memory doctrine: one production decode at a time)
PYTHONPATH=. env/bin/python -m measure.angle_residue run --angle 0.00 --side holo3 --workers 1
PYTHONPATH=. env/bin/python -m measure.angle_residue run --angle 0.00 --side holo2 --workers 1

# the censuses
PYTHONPATH=. env/bin/python -m measure.angle_residue_census
PYTHONPATH=. env/bin/python -c \
  "from measure.angle_residue_census import reach_report; \
   reach_report('scratch/angle-residue/holo3-a0.00')"

# the fit probe, both receivers in one process
PYTHONPATH=holo2/src:. env/bin/python -m measure.angle_residue_nyquist --trials 10
PYTHONPATH=holo2/src:. env/bin/python -m measure.angle_residue_nyquist --cells 100 --trials 8
```

holo2 is driven through `measure/angle_residue_h2.py`, which wraps four
seams of `PlacementScheduler` (`__init__`, `claim`, `settle`, `_exit`)
and `WindowJob.run` on the class objects of that process only, then calls
holo2's own `cli.main`. One caution for anyone re-using it: the
orchestrator calls `settle` **twice** per pass (once on the abandon path
with `result is None`), so pass counts must come from the fire ledger,
not the settle ledger.

**Artifacts kept** (`scratch/angle-residue/`, 1.4 GB): the two crop
tiffs, both holo3 run dirs (`events.jsonl`, `report.json`, `facts.npz`,
diag panes), both holo2 `state/` + `census.json`, and the two summary
JSONs. The holo2 `state.prepared/` raster caches (5.5 GB and 4.6 GB) were
deleted — they regenerate from the crop.
