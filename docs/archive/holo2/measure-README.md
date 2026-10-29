# holo2/measure — measurement drivers, NOT tests

**Nothing here runs under bare `pytest`** (the folder is outside
`testpaths`), and that is the point — the user's ruling, 2026-08-16:
"tests that take 10-40 minutes are not tests." What lives here now is
`verdicts/`, four equivalence harnesses (`refine_equivalence.py`,
`bch_equivalence.py`, `index_equivalence.py`,
`fit_phase_equivalence.py`), two CENSUS drivers (`or5_or7_census.py`,
`v1_side_by_side.py` — W6's owed numbers, below), and this README.

The two kinds differ in what they are FOR, and the distinction is worth
keeping: an equivalence harness asks *are these two implementations one
answer* and fails loudly when they are not; a census driver asks *what
did the receiver actually do* and its output IS the deliverable. A census
still has to earn its pass — both below carry self-checks that fail the
run when the instrument stopped observing anything — but a green census
is a measurement, not a proof.

## The equivalence harnesses

All four follow one shape, set by the first: a `__main__` script run BY
PATH, which INTERCEPTS the real calls of real decodes, runs both arms of
a switchable twin on identical inputs, compares them exactly, and returns
the ORACLE's answer so the decode never runs on the arm under
measurement. None is collectable and none is on the suite's clock; each
is run when its kernel is touched.

### `refine_equivalence.py` — the pose refinement's two arms

Not a verdict, not a test, and not collectable as either — it is a
`__main__` script the operator runs by path, self-locating so it needs no
`PYTHONPATH=` prefix:

```
env/bin/python holo2/measure/refine_equivalence.py
```

It proves that the pose refinement's two arms — the scalar 7x9x9 grid and
its batched twin, chosen by `PlacementConfig.batched_refine` — are
BIT-identical, never approximately so. It intercepts the real
`refine_patch_pose` calls of six real decodes, runs both arms on the
identical inputs, and compares the winner, the selection margin, the
held-out mismatches and the whole emitted `SegmentSample` array for
array; the decode itself always proceeds on the OLD arm, so the twin
never influences the population it is measured on. ~46 s, and it borrows
`verdicts/_fixtures.py`'s builders rather than growing its own.

Its own ruling is the user's, 2026-08-16: *"keep the old one around,
maybe you also want to use it for equivalency testing — but not as a
standard test, mind you."* So it is run when either refinement kernel is
touched, and never on the suite's clock.

### `bch_equivalence.py` — the Stage-A word decoder's two arms

```
env/bin/python holo2/measure/bch_equivalence.py [--fault NAME]
```

It proves that `format.bch.decode_many` (the CARRIED scalar path, and the
oracle) and `format.bch_batch.decode_many` (the twin, chosen by
`PlacementConfig.batched_word_sweep`) are one decoder — same verdicts,
same corrected words, same error positions, same counts, same order —
over THREE populations: the intercepted Stage-A batches of five real
decodes (~380 k candidate rows), a seeded synthetic set that reaches
every acceptance clause on purpose (including a truncated full-length
codeword whose locator roots land in the SHORTENED positions), and —
since the lockstep BM card — ~29 k BARE SYNDROME rows compared at
Berlekamp-Massey's own boundary, because the five acceptance rules can
MASK a BM divergence (two different locators that both refuse are the
same decode). `--fault list` names the deliberate breakages; a faulted
run must fail, which is how the harness earns its pass. ~45 s.

Population (c) exists because bare syndrome rows are a strictly larger
space than the syndromes of 100-bit words, and the difference is
measured rather than argued: on 8,192 real Stage-A syndrome rows the
locator degree never passes 15 and BM's trimmed-degree refusal fires
ZERO times, while the bare set reaches degree 26, the 27-coefficient
width bound, and that refusal 320 times. Its corners are constructed,
not hoped for — a single nonzero syndrome at every position (a provable
leading run of zero discrepancies, since an ``L = 0`` step's tap loop is
empty), and syndromes generated FROM a chosen connection polynomial by
its own LFSR at every degree 1..26.

The BM faults are injected by recompiling `bch_batch`'s REAL SOURCE with
one textual substitution (`lockstep_from_source`), so the broken arm is
the shipped code minus exactly one clause — the trim, the `<=` in the
length-update condition, the zero-operand poison, the b-polynomial
snapshot order, the shift offset, the discrepancy ratio, the
zero-discrepancy mask. All seven bite. Two REDUNDANCY PROBES use the
same mechanism pointed the other way: mutations expected to change
NOTHING, because the loop invariant makes the tap bound they remove
unreachable. Both were silent on every row of every population — which
is the measurement behind keeping that clause anyway, since what is
being reproduced is the scalar's arithmetic, not its invariant's
consequences.

Two findings it records rather than hides. The scalar decoder's final
syndrome re-check is UNREACHABLE from any 100-bit word (a binary word's
syndromes satisfy `S_2j = S_j^2`, which forces every Forney error value
to 1), so a sub-population drives that branch directly by planting a
legal locator into BOTH BMs — two plants since the lockstep card, as the
twin no longer calls bch's. And the intercepted population had been DEAD
since `batched_word_sweep` was flipped ON: the harness hooks
`bch.decode_many`, which a default decode no longer calls (measured: 4
twin calls, 0 oracle calls on a clean `c3-r0550` page). `force_oracle_arm()`
pins the receiver to the oracle for the run. The emptiness guard in
`main` was there and would have said so; nothing had re-run it.

### `index_equivalence.py` — the maintained derived views (F-17)

```
env/bin/python holo2/measure/index_equivalence.py
```

The third harness, and the only one whose oracle is not a kernel but a
REBUILD. Two views that used to be recomputed from the whole durable
store at every commit are now maintained from the commit's own
`changed_keys` — `solve.tilemap.StoreIndex` (advanced in
`SessionPlane.invalidate`) and the H3bis payload frontier
(`RealPayloadProvider.expand`'s per-key memo). Both keep their
from-scratch producer, and here it is the oracle: at every commit of
every arm the driver builds `StoreIndex.build(store)` beside the
maintained index and compares it field for field, and at every expansion
it re-runs the provider's derivation with an EMPTY memo beside the
memoized one and compares the descriptor tuples. Order is compared
exactly wherever order is consumed (the two grouped read-set views and
the descriptor sequence); the per-kind dicts' ITERATION order is
deliberately not compared, because nothing reads it (the audit is
choice 5 in `solve/tilemap.py`).

Four arms — a clean page, the e032 channel warp, a banded page whose
right quarter kills the word code, and a two-sheet volume where two
pages share one store. ~55 s plus the injections (~97 s whole driver,
measured W3 2026-08-23: 1,244 commits compared, 476 expansions, 24,571
descriptors, 0 divergences).

`live_poses` joined the compared fields at W3 (tilemap choice 8) — the
"latest committed pose for that extent wins" derivation, whose
maintained form has to equal the builder's first-write walk. The banded
arm is where that bites: RF1 is on by default now, and it commits six
revisions there.

Three fault injections close it, and each MUST be caught: one indexed
key withheld from a delta, a whole commit's delta withheld, and the
frontier memo's identity test forced to accept. A run where any of them
is not caught fails as loudly as a real divergence, and an injection
that compares nothing at all fails too — the harness has to earn its
pass.

TWO THINGS THIS DRIVER GOT WRONG AND W3 FIXED (2026-08-23), both found
by running it rather than by reading it: it died at the first commit of
the first arm on `SessionPlane.store`, which has not existed since the
H4 W2 wall landed (so nobody had run it since), and its two DELTA
injections fired at a fixed commit ordinal whose delta carries no
indexed key at all — so they withheld nothing and were reported NOT
CAUGHT. They fire on the first commit that carries an indexed key now.
A fixed ordinal is a fixture the fixtures move out from under. The stale-memo injection rides the BANDED arm on purpose: it is
the only fixture where scans fail, so a key's attempts genuinely grow
after its first expansion, which is the only condition under which a
stale memo can be wrong.

### `fit_phase_equivalence.py` — the phase grid's DELETED batched arm

```
env/bin/python holo2/measure/fit_phase_equivalence.py [--fault NAME]
                                                      [--arms N]
```

**The only harness whose twin is not in `src`.** The window fit's 8x8
phase grid reads 128 `map_coordinates` calls; a twin stacking them into
two was built behind a switch, proved bit-identical, measured — and
DELETED, because it does not pay:

| | |
|---|---|
| kernel | 7.27 → 6.82 ms (**1.07x**) |
| gen-clean serial | 115 s OFF → 116 s ON (no gain) |
| gen-clean W4 | 51 s → 48 s (inside the pooled band) |
| share of serial wall | 622 fits × 7.3 ms = **3.9%** |

The mechanism is the objective's own `stride = round(max(cells) / 40)`,
which holds the grid at ~40x40 for ANY window — so the 128 calls carry
~1,600 points each, far past where scipy's per-call setup matters.
Batching pays at N ≤ 400 (1.28x) and N ≈ 100 (1.61x), and
`min_window_cells` is 70 (stride 2, N=1,225), so that regime is
unreachable by construction. Do not re-open without changing the stride
law first. The one asset the arm keeps is its GIL-free fraction — **f
0.58 vs the shipped kernel's 0.42** — which is why the evidence is
preserved here: if the free-threaded 3.14t card is taken, the arm is
proved and can be re-priced instead of rebuilt.

So `TWIN_BODY` in this file IS the deleted arm, verbatim, and the
harness substitutes it into the shipped file (the two-step BM card's
`GENERAL` pattern). Every intercepted `_fit_phase` call runs THREE ways
— the SHIPPED function, an ORACLE RECONSTRUCTION (the file plus one line
publishing the score matrix the kernel keeps to itself), and the TWIN
RECONSTRUCTION — and the decode always proceeds on the shipped answer.
Two comparisons per call: **faithfulness** (shipped vs reconstruction —
a reconstruction that has drifted proves nothing, so it is checked every
call, not assumed) and **equivalence** (oracle vs twin, at the tapped
interpolated planes, the 64-entry score matrix and the phase answer),
plus the whole `WindowFit` and the window re-read per fitted window.
~30 s, six arms.

The risk axis is LENGTH, not geometry: the reduction is the one part the
arm does not batch, because each hypothesis scores only the sites its
own phase put over `coverage > 0.9` and numpy's pairwise sum blocks by
length. So on the first fit of every prepared region the harness re-runs
the same real window through a ladder of SLANTED support cuts — ragged
on purpose, so the 64 hypotheses of one call reduce subsets of differing
length — from a full window down through the 16-site gate to one nothing
can score. The run refuses to pass if that ladder did not span both
sides of the gate, if no call was ragged, or if any objective went
without its faithfulness check.

Seven injections: four break the ARM (float32 coordinate stack, a
batched reduction, a raised site gate, transposed hypothesis order) as
substitutions of `TWIN_BODY`; one breaks the SHIPPED source the oracle
is built from (a comparison that only looks one way is not one), and it
is also the standing argument for comparing the SCORE MATRIX rather than
just the answer — measured, it moves one score of 64 without moving the
argmax, so the phase, the planes and the faithfulness check all stay
silent and only the score comparison catches it; `compare-blind` blinds
the comparator with a real fault live and must then see nothing. The
seventh, `twin-factored-coords`, is a PROBE rather than a fault and is
expected to be SILENT: distributing the phase through the matmul moves
22-30% of the coordinates by up to 4.5e-13 px and ZERO of 204,800
interpolated values, because the planes are `float32`. The arm keeps the
shipped expression anyway — identity by construction beats identity by
luck — and if that probe ever bites, the observability floor moved.

## `tile_differential.py` — the v1/holo2 certificate-set differential (W1)

```
env/bin/python holo2/measure/tile_differential.py \
    --v1-state PATH --h2-state DIR --format L:c2-r0700@3392x2368 \
    --label e029 --out scratch/holo2-catchup/real/differential-e029.md
```

RULINGS I6 ("root-cause FIRST"): reads a v1 state file and a holo2 state
directory for the SAME sheet, READ-ONLY (v1 via `load_session`, holo2 via
`Store.open` directly — never `cli.open_receiver`, never a commit), and
attributes every tile in the symmetric difference of their certificate
sets. v1's side: every lane whose pose covers the tile (coverage, not
minting attribution — ordinary rung / mop-up / refinement, via
`holo.receive.cascade.lane_kind`), its footing, the covering pose's
window — the finest provenance a COMPLETED v1 state actually retains
(the per-attempt SCAN/RETRY150 stage is not durable there, and WHICH
covering lane actually minted the certificate is not durable either;
see the module docstring). holo2's side: the tile's rank
(`solve.tilemap.tile_state`: NEVER-ADDRESSED / ADDRESSED-NOT-ATTEMPTED /
ATTEMPTED-FAILED / CERTIFIED), every payload `SpendRecord` against its
work key (route, footing, outcome, attempts, exposures — never pruned,
unlike v1's folded counters), and every covering pose/window reachable
via the evidence index.

Pinned by `tests/holo2_oracles/test_oracle_tile_differential.py` (a
hand-built two-tile fixture pair, self-contained — no real decode). A
census driver in the README's sense: its output IS the deliverable
(`scratch/holo2-catchup/real/differential-{e029,xerox}.md`), and it
gates nothing. ~4.5 s per real pair.

## `rf1_resume.py` — RF1's yield by RESUME (W2)

```
env/bin/python holo2/measure/rf1_resume.py \
    --state scratch/holo2-catchup/real/e029-state-complete-rf1 \
    --scan scratch/e028/hp-canon-c2-ink-counting.tiff \
    --dpi 4800 --format L:c2-r0700@3392x2368 --label e029 --workers 8 \
    --expect-sha e5021f8d… --out scratch/holo2-catchup/real/rf1-e029.md
```

RULINGS I5/I2 ("RF1 is priced, not gated"; "the parity harness is
state-driven"): RESUMES an exhausted holo2 state in-process with the
production roster and ONE substitution — `refine.PoseRefineProvider(row,
revise=True)` — and prices what the dial buys. The dial is a constructor
flag and is not in `SessionIdentity` (`providers_identity` reads
`provider_id` alone), so the resume is lawful; the driver CHECKS that
field by field with `Store.peek_identity` before it opens anything, and
STOPS rather than forking if it moved.

It COMMITS, by design — run it against a COPY (`cp -Rc` clones the state
directory and its `.prepared` sibling on APFS for free), never against
the exhausted originals W4/W5 read. Two phases, because an exhausted
`--complete` state is TERMINAL and a terminal session commits nothing
(`orchestrator.py:212`): phase 1 opens with `--no-close` (the user's
2026-08-22 skip-on-ingestion ruling) and runs to exhaustion with RF1
live; phase 2 re-runs the same roster with the ordinary close policy so
the volume closes and the payload comes back for its sha compare.

Records, all flag-labelled in the report header: certificates and
PoseRecords before/after (read-only `Store.open`), poses per WINDOW
EXTENT (the grouping RULINGS I3 is about) for the poses this run minted
and for the whole collection, refine expansions/descriptors/fires, the
outcome histogram, the no-op share split into `unmoved_own` versus
`collides_existing`, fires per pose, **the spend ledger before/after per
family** (rows/attempts/CRC exposures — the row that distinguishes
"nothing ran" from "work ran and lost"; `certified +0` alone cannot),
per-phase commits/fires/wall, and the six operator rows each phase
published — including **done coverage**, which MOVES when a revision is
committed even though nothing sampled through it (`solve/tilemap.py`
`project_done` unions ALL committed poses; W2 review, 2026-08-23).

`--no-revise` is the DIAL-OFF CONTROL: the same arm with RF1 at its
production default, on its own copy of the same state. A resume re-offers
its scheduling set on open, which on the Xerox sheet moved the payload
ledger by itself — so the control is what separates resume churn from
RF1's yield.

Pinned by `holo2/tests/test_rf1_resume_classifier.py` — the two silent
classifiers only (window-extent grouping, and the no-op split), no
decode.

## `resample_resume.py` — F2a's RE-READ by RESUME (F2a)

```
env/bin/python holo2/measure/resample_resume.py \
    --state scratch/holo2-catchup/real/f2/e029 \
    --scan …/hp-canon-c2-ink-counting.tiff --dpi 4800 \
    --format L:c2-r0700@3392x2368 --label e029 --workers 8 \
    --expect-sha e5021f8d… --out …/resample-e029.md
```

`rf1_resume.py`'s idiom pointed at the OTHER half of the mechanism — it
IMPORTS that module's preflight, identity check and window grouping
rather than restating them. W2 measured what a pose revision costs when
nothing reads it; this measures what happens once the re-read does
(ruling J2-3).

What it adds: the certified TILE SETS before and after (a count cannot
see a swap, and "zero regressions" is the bar — the live-generation
reduction means a revision that reads WORSE costs the tiles its parent's
reading would have won); the re-read census, taken by wrapping
`resample.resample_window` where `place_job` reads it (calls the real
function, changes no argument and no result, removed in a `finally`);
the two generations counted in the store (poses per extent, and how many
poses OWN evidence — the mechanism's own signature); and, with
`--column`, one named tile column reported separately, which is a
POPULATION UNDER STUDY and never a bar.

RUN IT ON A COPY. It resumes and therefore WRITES, and the archived
`--complete` states are the corpus every other instrument reads.

## `parity_k.py` (+ `parity_k_report.py`) — THE K PARITY HARNESS (W4)

```
env/bin/python holo2/measure/parity_k.py --sheet all \
    --out scratch/holo2-catchup/real/parity-k.md
```

RULINGS I1 (the user's bar: *"K performs as well or better than src/holo
on each available / parseable K scan, and all synthetic scrap
'scans'"*) and I5 (*"the parity harness is STATE-DRIVEN for v1"*). One
ROW per declared K sheet: v1's certificates and payload sha, holo2's
certificates and payload sha, Δ = holo2 − v1, a zero-wrong mark on each
side against the GOLDEN sha, the holo2 wall, and the tile lists of the
symmetric difference (via `tile_differential.run` — W1's instrument,
called as a library, so there is one differential in the tree and not
two).

**The two sides are asymmetric by ruling.** v1 is READ from its archived
`receive.state` where one exists and is never re-run on paper; the run
FLAGS it reports are the state's own lane kinds, because `--mopup` and
`--refine` are exactly what put `mopup`/`refine` lanes in a capture
plan. holo2 runs FRESH through the operator path (`./confetti2.py
--format <id> --complete --workers 8`) and never by resume — W3's
`COST_REFINE` 90 → 200 is a `recipe_entries` value and those bind
`SessionIdentity` by value, so every archived holo2 state refuses this
build at identity. Where NO v1 state exists (the verdicts' rendered
fixture pages) both trees run on the same pixels, v1 at its full harvest
`--complete --mopup --refine`.

**It never decodes a real sheet twice.** Every holo2 arm writes
`<state-dir>.parity.json` and ADOPTS it on re-invocation; deleting that
file is the only way to ask for a second decode. Rows that adopted carry
a `*` on their wall. The sidecar records argv, wall, epilogue, exit
code, the prepared-plane counts on both sides of the decode, and the
TREE AND DIALS the decode ran under (`git rev-parse HEAD`, a dirty flag,
`COST_REFINE`, `PoseRefineProvider.revise`), and the report renders each
row's flags from its own sidecar — not off the live tree, which would
relabel an adopted row after a reprice.

A declared arm may also adopt an existing `.prepared` sibling by APFS
clone — the planes are content-addressed on everything they are a
function of, so a clone of the same capture's planes is byte-identical
to what the run would build. Whether the adoption actually HIT is
measured, never asserted: the file count is taken before and after the
subprocess and the row reads *"N of M reused, K built by this run"*.
Only a row with K = 0 may be read as a SOLVE wall — the W4 review found
the demo row building 36 planes inside its 12,251 s wall while the
hand-off called all three big rows a 100% hit.

**The bar is scored over TWO populations, printed apart.** RULING I1
names the K scans and the synthetic scraps; the three verdicts fixture
pages are this harness's own addition, and a single combined score reads
better than the ruled one. `fx-channel` is the verdicts' run-channel
PAGE decoded at the default cascade recipe — run channel itself decodes
at `RECIPE_V1_FINEST`, so that row is not the verdict's own parity.

**Rendering lives in `parity_k_report.py`**, split at HANDOFF-W4 §6's
named seam when the review fixes pushed the single file past 1,000
lines. It imports nothing from the harness: rows arrive duck-typed and
the dial state and the refine-off baseline table are parameters.

The DECLARED LIST is the census: every `*.state` under
`<repo>` enumerated and its `format_row_id` read
(2026-08-23) — 25 states, five of them the K row `c2-r0700@3392x2368`,
the other twenty colour. Two of the five are duplicate harvests of
subjects already listed (the colour-uplift PK-FINAL K states) and their
certificate SETS are identical to the two named rows, measured. The
module docstring carries the exclusions and their reasons.

Pinned by `tests/holo2_oracles/test_oracle_parity_k.py` — the flags
census over EVERY capture plan (mutation-checked against a
`captures[0]`-only reading), the three-valued zero-wrong statement,
`_epilogue_int`'s bracket anchor (the `coverage`-anchored mutant
publishes `97` where `7823516` belongs), and the declared list's own
consistency. No decode.

## `done_gate_savings.py` — done-gate savings against the v1 census (W5)

```
env/bin/python holo2/measure/done_gate_savings.py \
    --state e029=scratch/holo2-catchup/real/parity/h2-e029 \
    --state xerox=scratch/holo2-catchup/real/parity/h2-xerox \
    --out scratch/holo2-catchup/real/done-gate.md
```

RULINGS I7's W5 item: "done-gate savings measured against the census
prediction (48.6% placements / 85–90% tail)"
(`docs/DONE-GEOMETRY.md` §8a, v1's e029 harvest, 2026-08-05). READ-ONLY,
same standing as `tile_differential.py` — `Store.open` directly through
`tile_differential.open_h2_store`, nothing written.

**v1's 48.6% is a SIMULATED counterfactual, not a realized rate** — v1
never built the gate, so §8a's harness re-derives per placement whether
its extent WOULD have been fully done ("every approximation biases
AGAINST gating"). holo2's number below is a working, DEPLOYED gate's
realized retirements — the opposite kind of quantity, and NOT a ratio
against v1's: a gate that works drives its own realized share DOWN,
because a window it catches never reaches the population being counted.

holo2 has TWO door-exit sites for "this extent is already fully done",
and this driver can see only one of them. `place_job.py:606-608` — a
`PlaceWindowJob` that already fired discovers the extent is done and
retires with a durable `WindowRecord` (`status = RETIRED`,
`retired_reason = "done_covered"`) — the ONLY site counted below.
`place_sched.py:478-480` — the scheduler's OWN admission door
(`_Scheduler._consider`) checks the same thing BEFORE a job is ever
created, and on a hit just marks the window in an in-memory `_exited`
dict and returns; nothing converts that into a `WindowRecord`. Per its
own docstring: "a done-covered window ... is never created, never posed
and never woken." This is almost certainly the PRIMARY site by
volume — a plan whose extent is already done at admission never
becomes a job at all — and it is invisible to any census over a
finished `Store`.

So this driver measures a LOWER BOUND, in holo2's OWN terms rather than
transplant v1's phase table: **committed placements** = every durable
`WindowRecord` (a window that reached a terminal outcome — placed or
retired, some named reason) — NOT the direct analog of v1's
"placements" column, since v1 had no admission-time gate at all while
holo2's most common gate exit leaves no record; **pixel-gated share** =
`done_covered` retirements over that population, a lower bound on the
gate's real activity; **per-rung** groups by `WindowRecord.footing_id`'s
ppc suffix, the closest durable analog to v1's per-level table, split
full-extent windows from subdivision children (a different, smaller
population with no lineage field to key its size split on); **the
tail** has no phase boundary to key on, so it is defined POSITIONALLY
over `StoreIndex.windows`' commit order (exact here, because a window
key is written EXACTLY ONCE — `records.py`'s v5 "OUTCOME ONLY" ruling)
— reported by decile plus fixed last-10/20/30% cuts, named as a proxy
for v1's phase-based tail and not asserted to be the same thing.

**Measured on the two W4 fresh `--complete` states**
(`scratch/holo2-catchup/real/parity/h2-e029`, `h2-xerox`):
recorded pixel-gated share is **45/1273 (3.5%) on e029, 42/1324 (3.2%)
on xerox** — a LOWER BOUND, not "7% of v1's rate" (the two are not
commensurable; see above). **The recorded population is itself
incomplete at the coarsest rung**: e029's full-extent window count is
271 at ppc 2/1 against 315 at every finer rung on the SAME single
region — a floor of **44 plans that resolved at the admission door and
left no record**, the same order of magnitude as the 45 recorded gate
hits. Xerox: 319 vs 330, floor of **11**. holo2's own ladder placements
(1273/1324) are also LARGER than v1's own ladder rows (l00+l01+l02+l03 =
1,172) — v1's extra placements are its m00 tail (279) and r-lanes (28),
phases holo2 has no analog for, not evidence that holo2 "re-attempts a
window" less often per rung.

The CONCENTRATION pattern does echo v1's tail finding, on the RECORDED
population: on both sheets essentially all recorded gating sits in the
LAST DECILE of window commit order (34.6% / ~30% gated there, ~0% in
deciles 0-8) and concentrates on the COARSEST rung (ppc 2/1 full-extent:
16.2% / 12.2% gated; ppc 4/1 and 8/1: 0% on both sheets; ppc 16/1: 0.3%
/ 0.9%) — the opposite rung v1's own l00 (2ppc) saw zero gating on. Two
competing readings, both offered as hypotheses and not measured
further: holo2's pull scheduler has no barrier forcing the coarsest
rung to finish first (so some 2/1 windows land late); OR the coarse-rung
concentration is partly an artifact of which coarse windows leave a
record at all (the 44/11 unattributed windows are the SAME order of
magnitude as the 45/42 recorded ones). Full table and the per-sheet
breakdown, including the unattributed floors: `scratch/holo2-catchup/
real/done-gate.md`.

**A denominator caveat, inherited from W1's limitation 2, IN ADDITION TO
the door-exit gap above**: a window that never reaches a terminal
outcome (stays dormant, never re-offered again) also leaves NO durable
record and is not counted — the total here is a LOWER BOUND on "windows
this run touched" for two independent reasons, exact only for "windows
this run RESOLVED via a job that fired".

Pinned by `holo2/tests/test_done_gate_savings.py` (4 tests, no
`holo`-import needed — a plain dict-backed store stub is the whole
fixture) — the gate-reason classification, the ppc-suffix rung grouping
(two capture prefixes on one rung must fold into one row), and the
commit-order (not sorted-key) tail slice, all three mutation-checked.

## The census drivers (W6's two owed numbers)

Both were built for H4-PLAN §4's gate items and both borrow
`verdicts/_fixtures.py`'s builders rather than growing their own, so
their captures are the verdicts' own content-addressed cache entries and
not a second rendering of the same parameters. Their numbers live in
`holo2/docs/MEASUREMENTS.md`; re-run either when the thing it counts
moves.

### `or5_or7_census.py` — the BP budget and the consult radius

```
env/bin/python holo2/measure/or5_or7_census.py [--arms A,B,...]
                                               [--rows N] [--quiet]
```

Three serial `--complete` decodes (channel, banded, banded declared
twice), instrumented at four seams, answering both numbers H3 could not
produce:

* **OR-5** — how many belief-propagation iterations one payload work key
  burns across its whole lifetime under re-arming frontiers, and where a
  per-key ceiling would have to sit. M-3.5 measured OR-5's eager/phased
  half on toys and recorded that this half was unanswerable there,
  because a toy decoder never fails.
* **OR-7** — the pull model's counterpart to the push era's bucket
  question: the distances at which consult offers were actually ACCEPTED,
  and whether `CONSULT_KEEP = 8` ever starved a placement.

**It records an observability gap rather than routing around it.** holo2
does not make the iteration count durable — `TileAttempt.n_iters` is
transient (DESIGN §5.5), the `SpendRecord` carries outcome and a monotone
exposure counter and nothing else, and no event carries it either. v1
folds `StageTally.bp_iterations` into its durable `SessionCounters` per
stage, so the same question is a state read there and an interception
here. The driver intercepts `solve.tiles.attempt_k_tile` and attributes
each call to its work key by wrapping `RealPayloadWorker.run` around it;
**nothing in `src` changed**, and nothing in `src` can read the number
back afterwards.

Its OR-7 half carries an ORACLE in the `fit_phase_equivalence` sense: the
untruncated consult, reconstructed from the shipped source minus exactly
the `[:K]` clause, checked against the shipped answer on EVERY call (the
shipped list must be the oracle's own prefix). A run whose oracle drifted
fails, because a reconstruction that no longer reconstructs measures
nothing.

### `v1_side_by_side.py` — both receivers, one page, labeled

```
env/bin/python holo2/measure/v1_side_by_side.py [--arms A,B]
                                                [--v1-workers N]
                                                [--skip-cli]
                                                [--cli-timeout S]
```

H4-PLAN §4 item 2's table: accepted poses and certificates for holo2 and
for `src/holo`'s own receiver on the SAME rendered fixture pages. **A
comparison and never a bar** (WORKPLAN:359-361) — holo2 stops at
solvable, v1 harvests to plan exhaustion; equal payload SHAs are the
claim and equal certificate counts are not.

The v1 side runs IN PROCESS through `run_receive` on the fixture's own
`FormatSpec`, one level up from the door `verdicts/test_v1_parity.py`
already uses for placement — because the comparison wants v1's
`--workers` and its counters in this process.

**The operator arm's old finding is SUPERSEDED** (C4, RULINGS G5,
2026-08-22). It used to record that `./confetti.py decode` took
`--coding`/`--printer` and had no flag for a tile grid or a media size,
so it could not spell an 8x8-tile page at all and timed out at 600 s
against the registry's A4 row. The fixtures are v2 identities now and
`src/holo`'s decode parser takes `--format ID`, so the arm names the
exact page (`--format c2-k-r0700@8x8`) and is a real decode of the same
pixels. It is RUNNABLE, not run: C4 changed no receiver and took no new
operator-path number (`--skip-cli` turns it off; it is the expensive
half).

## The H5 P3 qualification drivers (and their authored channel)

H5-PLAN P3's four owed measurements. Census-class: their output IS the
deliverable, their numbers live in `holo2/docs/MEASUREMENTS.md`, and
**none of them gates anything**. Both borrow `verdicts/_fixtures.py`'s
builders, so their sharp renders are the verdicts' own cache entries.

### `_h5_context_channel.py` — the authored channel, not a driver

A sibling module both drivers import (the standing of
`bch_equivalence_populations.py`: no `__main__`, measures nothing alone).

It exists because of a fact P1 measured and P3 must not re-discover: **on
UNIFORM cell error the held-out ctx gate refuses every fit** — correctly,
since uniform error carries no context signal. So a ctx measurement built
on `render`'s own `cell_error_rate` reports a refusal and calls it a
profile. This module authors error that IS context-correlated, by
applying ONE GAUSSIAN PSF to the warped sheet rather than by hand-rolling
a flip rule: a point-spread function is where E023b's context bias
actually comes from, so the monotone-in-neighbour-ink-count shape the
carried arm assumes falls out instead of being tuned in. Its docstring
states every parameter, gives the equivalent MTF10 beside e028's measured
Canon figure (the fixture is deliberately softer), and records the three
fixture shapes that were measured and rejected on the way — including the
one that matters most, that **the cliff which binds these pages is
PLACEMENT and not payload**.

### `h5_union_gain.py` — arms (a) and (b), real decodes

```
env/bin/python holo2/measure/h5_union_gain.py [--arms A,B] [--quiet]
```

Three SERIAL `--complete` decodes per arm (A alone, B alone, A+B), ~342 s
for both. (a) is the UNION-GAIN direction against a pre-registration
stated in the docstring before the arm was ever run; (b) changes exactly
one variable — the second acquisition's resolution — and is the first
measured **mixed-resolution** union, legal because a footing's identity
is its ppc and the two ladders share rungs. The driver adjudicates its
own pre-registration and FAILS the run on a loss, on a vacuous arm (no
fit adopted, no union spent, no headroom) and on the subtler vacuity of
an arm whose uncertified tiles carry no evidence at all — there is
nothing for any acquisition count to sum.

### `h5_aperture_ctx.py` — arms (c) and (d), cell-level, no decode

```
env/bin/python holo2/measure/h5_aperture_ctx.py [--arms A,B]
                                                [--px-per-dot N]
                                                [--format ID]
```

~6 s at 1200 dpi, ~20 s at 2400. No decode, deliberately: yield depends
on placement, scheduling and the fountain, and these two questions are
only about the CELL READ. The pose is therefore TRUTH — `render` returns
the affine it warped under — and is never re-fitted ("don't measure known
quantities"). (c) is the pair-matched decimated-vs-native aperture over a
sensor-noise ladder, with the native rung as an exact identity control
the driver fails on; (d) is the ctx gain per rung over a channel-softness
sweep. Both prove a fit adopted rather than assuming it.

## `crop_cases.py` (+ `crop_cases_report.py`) — the crop-case generator (HANDOFF-CROP A)

```
env/bin/python holo2/measure/crop_cases.py --sheet all
```

HANDOFF-CROP's stated purpose, verbatim: *"the point here is to go from
13h runs to minutes instead"* / *"or seconds."* Cuts small crops (native
capture pixels, no resample) around every tile of interest out of the
two real e029/xerox K captures, so the residue lines (tx=0, F3–F10,
toolbox) iterate on crops instead of full sheets. Computes four TARGET
classes per sheet from three certificate sets — `flipped` (the F1/F2
line's negative→positive tiles), `still_missing_v2` (v1 has, holo2
still lacks), `v1_missing` (holo2 has, v1 never did), `neither`
(headroom for both) — recomputed from states where one exists
(`load_session` for v1, `tile_differential.open_h2_store` for holo2,
read-only) and cross-checked against the recorded differential
markdown's own header counts; the one approximate class (`flipped`)
concedes its overlap with `v1_missing` by a stated ruling rather than by
silent arithmetic (module docstring). Clusters targets by tile-space
gap, splits long clusters, adds a halo, and maps cell space to capture
pixels through ONE global affine per sheet fit from the v1 state's
committed poses — SPEED knobs (`--merge-gap-tiles`, `--max-span-cells`,
`--halo-cells`), never evidence caps: every target lands in exactly one
case, asserted. Both-certified tiles fully inside a crop (minus a
32-cell rim) are recorded as CONTROLS, reported per crop, never a class.

Writes, per sheet, under `scratch/holo2-catchup/crops/<sheet>/`
(gitignored): the `cases.json` manifest Deliverable B codes against
exactly, the `<case_id>.tiff` crops, and `cases-census.md` (also printed
to stdout) — the class table with its cross-check numbers, the affine
fit and its residuals, and per-case sizes/controls. Measured at build
time: e029 15 cases / 50 targets / 1.58 GB, wall 10.3 s; a FINISHER-pass
re-run to a scratch out-root reproduced the e029 census byte-for-byte
(module content unchanged by the `crop_cases_report.py` split below).

**The census renderer lives in `crop_cases_report.py`** — the
`parity_k_report.py`/`crop_harness_report.py` seam, taken at the
1,000-line signal (FINISHER pass, 2026-08-28: `crop_cases.py` was 1,097
lines; `render_census` moved out verbatim, parameterized on
`px_pad_cells`/`control_rim_cells` rather than reaching back for the
generator's constants). Pure formatting; imports nothing from the
generator.

Pinned by `tests/holo2_oracles/test_oracle_crop_cases.py` (class-set
disjointness and computation from synthetic cert sets, clustering+split
determinism and full-coverage assertion, the manifest schema round-trip,
the control-selection rim rule) — there and not under `holo2/tests`
because this driver imports `holo` (it reads v1 states; the firewall
exempts exactly this directory).

## `crop_harness.py` (+ `crop_harness_gt.py`, `crop_harness_report.py`) — both receivers on a crop (HANDOFF-CROP B)

```
env/bin/python holo2/measure/crop_harness.py                # both sheets
env/bin/python holo2/measure/crop_harness.py \
    --manifest scratch/holo2-catchup/crops/e029/cases.json \
    --case e029-c01 --side h2                                # smoke scale
```

Runs BOTH receivers, SERIALLY, fresh on any Deliverable-A crop —
v1 (`confetti.py decode … --no-close --complete --mopup --refine
--workers 4`), h2 (`confetti2.py … --no-close --workers 4 --diag-port
8061`, off the production 8024/8025 port) — and scores every target and
control tile's crop verdict against the manifest's recorded full-sheet
verdict. No full-sheet decode is reachable from this file; it only
decodes the crop files a manifest names.

**SIDECAR ADOPTION**, the `parity_k` rule sharpened for the inner loop:
each run writes `<runs>/<case_id>/<side>.sidecar.json` (argv, crop sha,
receiver TREE OBJECT hash, receiver dirty-diff sha, wall, exit,
summary); a re-invocation adopts iff crop sha + tree + dirty sha all
match, else it wipes that SIDE's run artifacts and decodes fresh. The
tree component is scoped to the SIDE'S OWN subtree (`HEAD:src` for v1,
`HEAD:holo2/src` for h2, not the repo `HEAD`) — deliberately, because
keying on `HEAD` would re-decode every v1 crop after every holo2 commit,
which is the loop this instrument exists to kill; `repo_head` is still
recorded, informationally. `--fresh` forces a re-decode of the SELECTED
side(s) only (`--side`) — a bug the FINISHER pass found and fixed
(`process_sheet`'s per-side loop, 2026-08-28): a bare `fresh=fresh`
poisoned the non-selected side's adoption too, so `--side h2 --fresh`
reported v1 "stale"/side-unavailable even though v1 was never touched;
fixed to `fresh=fresh and side_selected`, verified against a real crop
(v1 stayed adopted, h2 alone re-decoded).

**GROUND TRUTH lives in `crop_harness_gt.py`** — the second 1,000-line
seam (FINISHER pass, 2026-08-28: the prior build session died
mid-split, leaving both an inline copy in `crop_harness.py` and the
polished `crop_harness_gt.py` file; the inline copy was deleted and
every call site re-pointed at `crop_harness_gt.*`, `crop_harness.py`
826 lines after). The golden payload is re-encoded through `src/holo`'s
own generation path (`fountain`/`envelope`/`metadata`, stopped at the
user-bit boundary) into per-tile truth for the WHOLE tile domain, then
VALIDATED against every v1-certified tile on BOTH archived sheets before
any comparison runs — `GTValidationError` refuses the whole report on
any mismatch (exit 3). Measured (FINISHER smoke, 2026-08-28): 1,940/1,940
(e029) and 1,930/1,930 (xerox), zero mismatches, both sheets validated
inside the same invocation regardless of which manifest was passed.

**Rendering lives in `crop_harness_report.py`** (the `parity_k_report.py`
seam taken up front, not at the cap): wrong certificates at the top
loudly (expected zero), control flips reported and never gated, uplift
rows (a crop certificate on a target the same receiver missed at
full-sheet scale) flagged distinctly and GT-checked.

**FINISHER smoke result** (case `e029-c15`, the smallest by px area with
≥1 target and ≥1 control — 1 `flipped` target, 15 controls, 7947x5894 px
/ 47 MB): first run v1 45.9 s / h2 14.0 s (exit 2 both — expected under
`--no-close`), zero wrong certificates, target tile `(52, 2)` certified
both sides matching the full-sheet record, controls 15/15 reproduced
both sides, zero flips; second invocation adopted both sidecars, 4.4 s
wall, no re-decode.

Pinned by `tests/holo2_oracles/test_oracle_crop_harness.py` (the
adoption predicate's exact three-key match — `repo_head` MUST NOT
participate; the GT gate's raise-on-mismatch path, now against
`crop_harness_gt.*`; the rank-vocabulary refusal; uplift firing on
exactly `still_missing_v2`/`neither`; the three-valued control tally) —
same `holo`-import standing as `crop_cases.py` above.

## The batteries' epitaph

The eleven decode batteries (`test_real_e2e`, `test_spine_e2e`,
`test_crash_recovery_e2e`, `test_resume_without_pixels_e2e`,
`test_pool_e2e`, `test_diag_pane_source_e2e`, `test_diag_panes_e2e`,
`test_health_spine`, `test_prepared_evidence_e2e`,
`test_provider_contracts`, `test_differential_placement`) and the four
helper kits they stood on (`_cli_kit.py`, `_differential_kit.py`,
`_provider_kit.py`, `_real_fixtures.py`) were deleted with the measure
cleanup (user ruling: they were left to rot, several already broken, and
duplicated by the five verdicts below). Git history is the archive —
resurrect from it on need; nothing here reconstructs a battery from a
description.

## THE VERDICTS (`holo2/measure/verdicts/`)

Eight verdicts over FIVE shared decodes (was four, briefly, between the
run-union merge, 2026-08-17 — a wall-time ruling folded run union into
run streaming's own third scan; see `conftest.run_streaming` — and W3's
subdivision wave, which added a fifth decode and an eighth verdict) —
the design law is the user's: "many execute the same things — run once,
check multiple things after the run." Run channel (channel-arm page)
carries byte-exact + v1 pose parity + crash-cut re-earn +
resume-without-pixels, all on one decode; run banded (banded page)
carries the seeded-search verdict; run partial (two-sheet partial)
carries close-honesty; run streaming (both sheets, pool of two, sheet 0
scanned a second time under a narrow band) carries the
mid-run-acquisition ordering claims AND, on that second scan of sheet 0,
the correlated-evidence law's lawful half; run subdivision (a page faded
across x, legible at 100 cells and not at 200) carries the subdivision
verdict — one 200-cell edge window runs its whole ladder while three of
its four 100-cell corners place, the ruled shape exactly.

**A NINTH VERDICT joined at C5** (2026-08-22, RULINGS G6 —
`test_operator_path.py`), and it is the one that does not share a
decode, because the decode is its subject: it drives `cli.main` with an
ARGV, on the spine page's own format id and nothing else, and asserts
exit 0 with the recovered object byte-equal to the emitted payload —
then resumes that state with no identity argument at all. Every seam
between the typed string and the bytes is on that path exactly once
(resolve, row, providers, source, close, publish), and every one of them
is invisible to the stubbed-decode pins in
`holo2/tests/test_cli_surface.py`, which is the only place the argument
surface can be pinned (that tree may not import the generator). Clean
render, smallest fixture, ~10 s: the channel is run channel's subject,
not this one's.

Cadence: the full verdicts at WAVE END exactly —

```
env/bin/python -m pytest holo2/measure/verdicts -q
```

Package hand-off and pre-merge run only the round-trip check —

```
env/bin/python -m pytest holo2/measure/verdicts/test_roundtrip.py -q
```

Run the verdicts by themselves — never mixed into a `testpaths`
invocation (see the no-conftest-shadowing note below).

This root may import both packages: the pages are emitted by the real
`src/holo` generator and decoded by holo2 (the firewall,
`holo2/tests/test_firewall.py`, walks `holo2/src` AND `holo2/tests` and
forbids a `holo`/`paperholo` import in either).

## No `conftest.py` outside `verdicts/`, and there must not be one

Pytest's prepend import mode imports by BASENAME, so a second
`conftest.py` under `testpaths` shadows `holo2/tests/conftest.py` in
`sys.modules` and breaks collection tree-wide — while every per-suite
command stays green. `holo2/tests/test_conventions.py::
test_test_module_basenames_are_unique` covers every `*.py` under
`testpaths`, not only `test_*.py`, so the trap is mechanical rather than
folklore.

`verdicts/conftest.py` is the ONE exception and it is safe on its own
terms: nothing under `testpaths` collects `holo2/measure/verdicts`, so
that file is imported only by a run that names the verdicts directly —
which is why the ruling says to run it BY ITSELF and never mixed into a
`testpaths` invocation. The mechanical guard cannot cover it (it walks
`testpaths`), so the discipline is the invocation, stated here and in the
verdicts' own docstring. `_fixtures.py` (carved from the deleted
`_real_fixtures.py`) lives alongside `conftest.py` inside `verdicts/`, so
no `sys.path` surgery is needed to reach it — pytest's own basedir
insertion already covers it.

## Rendered pages are cached on disk; decodes never are

A render is a pure function of its parameters and its dot field, so
`verdicts/_fixtures.py` content-addresses it into a gitignored
`holo2/.fixture-cache/` and copies it out on a hit — once per
parameter set ever. Measured (pre-cleanup, still true of the mechanism):
renders cost ~1.7 s cold and ~0.01 s warm, byte-identical.
`RENDER_CACHE_VERSION` is the one thing the key cannot content-address
(the module's own arithmetic) and is bumped by hand. Nothing about a
DECODE is cached anywhere: every verdict runs the receiver for real,
every time. `HOLO2_E2E_FIXTURE_CACHE=` (an empty value) turns the cache
off, which is how a run proves the renders still reproduce from their
parameters alone.

## `H4-measurements/` — the H4 wave's records (not tooling)

The 21 drivers + 11 run chains that produced the W1/W2-exit, parallelism-
cards, GIL-diagnosis and F-16/F-17 numbers, with their logs, counters,
profiles and the four written reports — preserved verbatim from
`scratch/holo2-demo/` when it was trashed (2026-08-23). Historical
record: absolute paths into retired worktrees, not on the import-
resolution guard (that glob is non-recursive on purpose), never run by
anything. `H4-measurements/README.md` maps driver → measurement.
