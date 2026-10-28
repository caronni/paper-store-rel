# engine — DESIGN

Scheduling: session lineage, recipe, orchestrator. The engine knows
protocols, gates, routes and prices — never a concrete solver, a format
leaf or a pixel reader. Imports `core` ONLY, including the work
protocol.

Constitution: `holo2/docs/DESIGN.md`. Public surface + rationale: the
`__init__.py` docstring.

## Purpose

Three modules, three duties:

- **`session`** — one open session: its `SessionIdentity`, its state
  directory, one `CommitEngine` over one `Store`, terminality, and the
  cache invalidation a commit implies (the `warm` read barrier it used to
  drive died with the round, W-S). It does NOT own the derived world
  it schedules over; that arrives as a `Plane` built by the composition
  root, and the engine relays it to providers and workers as
  `core.SolveView`. Two choices DESIGN is silent on: the plane is built
  by a FACTORY rather than passed in (the store is created here, may be
  resumed and may be terminal, and the plane derives from it — a factory
  is the shortest way to keep that order without the engine importing
  anything that knows a pixel); and the blob read lock lives on the
  PLANE, where the concurrent readers are (§10.1) — the session reads
  through the same door.
- **`recipe`** — orchestration policy as typed data. An ordered list of
  frozen constants: task class, footing selector, prices, gate, arm. No
  DSL, no config file, no construction from strings — and since the
  identity law the ENTRIES themselves land in `SessionIdentity`, so a
  policy change forks the lineage by value instead of relying on a
  hand-bumped id. `Recipe.label` and `RecipeEntry.label` are display
  only; a descriptor stamps the entry's label as provenance, which
  `work_id` deliberately excludes.
- **`orchestrator`** — the ready queue, the fixpoint, and close
  preemption.

The loop is deliberately small because everything that could have been
control flow is a fact instead: *what may run* is enumeration over the
recipe's entries asking each family's providers to expand the frontier;
*what will run* is the ready set, refilled by commit wakes; *what may
not run again* is the spend-once test; *when to stop* is a verified
close (preemptive) or quiescence of every worker across every entry.

**Vocabulary is stage-free** (user ruling 2026-08-10): descriptors,
gates, routes and prices — no scheduler-visible phase, pass, lane or
mop-up. What v1 carried as stages survives as properties of ordinary
work: eligibility (a decline that names its wake), identity (footing and
contributor sets inside the read-set), and price.

## Public surface

`holo2.engine.__all__`, pinned by `holo2/tests/test_surfaces.py`.
Since B4 it declares no exception type: `FireCountTripwire` and
`NoProviderError` are raised and handled inside the engine, and
`test_error_taxonomy.py` derives DECLARED from `__all__`, so either is
declared in the same diff as the first cross-package handler. The engine's
layering debt is EMPTY (`holo2/tests/test_layering.py`): R1 removed the
`engine → format` edge by moving the close behind an interface; R2
dissolved `runtime.py` and with it the `engine → capture`/`solve` edges.
The `Plane` and `CloseConsult`/`CloseVerdict` protocols are declared
HERE and satisfied by `solve.plane.SessionPlane` and `solve.VolumeClose`
— dependency inversion, so the requirement lives with the requirer. The
plane's class is named by its own module because B4 took it off solve's
surface: the engine binds the object, never the type.

Strict typing: `core`, `engine` and `cli` are the mypy perimeter
(`holo2/tests/test_typing.py`, worklist B12); the remaining packages
join as they are touched.

## Owned record families (R3)

| family | kind | version | invariant |
|---|---|---|---|
| `SessionIdentity` | `None` | 1 | the envelope header — format row id, receiver policy id, recipe id, declared page domain. The registry's one keyless family: the store decodes `envelope["session"]` through it . Declares no transition and no references (F-08/F-07): it is frozen at creation, is not stored at a key, and binds its lineage BY VALUE rather than by pointing at records |

The engine names no other record type anywhere. What it reads off the
plane is core types or JSON — including the terminal consumer's close
report, which it carries through untouched because it has no business
typing a fountain state.

## The laws engine enforces, and where

| law | where |
|---|---|
| **L5** a certificate conflict is terminal, never voted | the rule is `solve`'s and the wall is `core`'s; the engine owns the FACT it becomes (F-11) — `Orchestrator._integrity_failure` commits `CloseRecord(integrity_failure)` and the run ends on it |
| **L7** current evidence may reorder work, never narrow a domain | the recipe's gates and prices order; a decline parks and names its wake; nothing here truncates a rival set |
| **L10** batching invariance | RE-SCOPED by R9 (2026-08-15): under continuous admission the wall commits in COMPLETION order, so a live run at `--workers k > 1` is NOT a deterministic function of the state it started from. What is invariant is the FIXPOINT — an exhaustive run reaches the same certificate set and the same bytes at every pool size, because spend-once + per-item determinism make the work schedule-independent — plus two exact lanes: `--workers 1` (the serial heap order, unchanged) and replay of any recorded ordering (byte-exact envelope). Cost accounting (versions, `commit_seq`, spends, stale discards) was always order-dependent and now varies more |
| **L11** determinism split | per-item determinism is the worker's; scheduling order is free. The concurrent phase WRITES NOTHING — commits happen on the main thread only |
| **L12** observer boundary | the orchestrator publishes a snapshot; the observer reads it and can fail without touching the run |
| **L15** status honesty | quiescence is an OPEN, resumable, honest partial state — never a failure. Terminal states are immutable |

## The scheduling contract, stated once

These are also the choices where DESIGN is silent that the modules'
docstrings name and point here for; the argument lives here, once.

- **There are TWO admission sources, and ONE cost order** (H4 W2, the
  pull model). A `Provider` mints DESCRIPTORS whose eligibility is a
  durable fact and whose repetition is bounded by a spend row at the
  wall. A `core.WorkSource` keeps a monotone-shrinking set of subjects in
  memory, each with a readiness flag, and prices the ready ones; its
  repetition is bounded by the flag protocol (a claim test-and-CLEARS, so
  one subject has one owner) and by the source's own tried set, not by
  the ledger. One source exists today — placement
  (`solve.place_sched.PlacementScheduler`) — and the engine knows nothing
  about it beyond the protocol. `_next` compares the two heads by COST
  and takes the cheaper, a tie going to the queue so the choice is a
  function of state and not of iteration order. `admit` is the source's
  `expand`: it is called from the same refresh, per recipe entry.
- **A DESCRIPTOR IS PRICED TWICE OVER ITS LIFE** (H5, 2026-08-19, re-work
  aging). `_workers` is monotone and `offer` skips an admitted work id, so
  a descriptor is MINTED once and re-queued many times: the price it was
  admitted at would otherwise be the price it kept forever. Both places
  the cost book is written now go through `Orchestrator.price` — the mint
  (`frontier.admit`) and the WAKE (`_absorb`) — and the third term that
  makes the second call worth making is the RE-WORK ORDINAL, read off the
  descriptor's own `(work_id, route)` spend row. Two consequences worth
  naming: a re-attempt is dearer than the attempt before it, so re-work
  drains after the cheaper bands; and the source path is untouched,
  because a source job takes no spend row at all, which is how the ruling
  that placement takes no term is kept without the engine knowing what
  placement is.
- **ENUMERATION IS UNCONDITIONAL; PROGRESSION IS A PRICE** (user ruling,
  AMENDED 2026-08-17). Every work entry expands at every refresh. The
  `quiescent` gate this replaces skipped an entry's whole expansion while
  anything cheaper was ready or in flight, and it was the mechanism for
  coarse-before-fine footing progression: a finer window was not created
  until the coarse ones were done, so it met the §6 done gate at CREATION
  time. That was recipe-v0 machinery, never adjudicated, and its stated
  justification — hint flow follows enumeration order — died with the
  pull model, where hints do not exist and a fire consults committed
  poses whatever order it runs in. What replaces it is pricing, in the
  source that owns the work: a finer-footing window enters the scheduling
  set as soon as its geometry does and pays the LANE TERM
  (`place_sched.LANE_COST_PER_RUNG`, `2` per rung above its capture's
  coarsest — a flat premium of 1 until H4-LANES stage 2 re-spaced the
  scale for a five-rung ladder) on top of every tier it runs, declared as
  data beside the tier table and held strictly below the tier spacing so
  it reorders within a rung and never across one. Exhaust-the-sheet-before-
  specializing is then a property of the ONE global order rather than an
  exemption granted to one entry — and the window that never needed
  working exits by coverage, as it always did, one cheap pass later. Gone
  with the gate: `RecipeEntry.quiesces` (streaming ingestion's exemption
  from an exemption), `Orchestrator._cheaper_in_play` and
  `Worklist.cheapest_in_play`. The work-gate vocabulary is now one value
  wide, `GATE_ALWAYS`, which is what says at the type level that nothing
  defers.
- **A GATED job waits for global dryness, INSTANTANEOUSLY measured**
  (rulings Q3+Q6). A source may mark a job `gated`, and a gated job may
  not start while anything cheaper is READY OR IN FLIGHT anywhere —
  including pending payload, because certificates create done-exits that
  DELETE placement work outright ("if we devolve into 'let's run a cold
  search on everything remaining' before all payload is decoded, we are
  going to burn ourselves"). Dryness is instantaneous, not final: the
  gate re-evaluates every time `_next` is asked, so bounded waste
  replaces a finality condition that would deadlock. Both halves of "in
  play" count, the queue's and the source's, for the same reason F-22.1
  gave: a commit re-enumerates from inside one fire's admission while its
  slot-mates still run.
- **A source job binds an identity but takes no spend and no
  subscription.** The source owns "may this run again?", so there is
  nothing for the ledger to hold and a failed pass commits NOTHING — an
  empty batch is never committed at all, which keeps the ordering journal
  a record of work that produced something. The identity is still taken
  at arm time, over the short list of keys whose transition laws could
  REFUSE the job's writes (R5's lattice seed), because the wall
  re-derives every proposal's identity: what the binding buys is the
  ordinary stale discard instead of a fatal `CommitRefusal`.
- **Commit, THEN settle** — the ordering the pull model's whole lost-wake
  argument rests on. `_commit` applies the batch and absorbs its wakes
  before `_settle` hands the pass back to its source, so a window the
  settle pings consults a pose index that already holds the pose that
  woke it. `_disarm` settles again with `None` (the abandoned-fire path:
  a cancelled pool slot, a replay proposal dropped past the tail), which
  a source must therefore make idempotent per claim.
- **Staleness is waste, never error.** A proposal commits only if the
  read-set RE-DERIVED still binds the identity it holds; otherwise it is
  discarded and its worker re-armed. A source job takes the same test
  over its much smaller read-set, and is re-offered by its source rather
  than pushed back onto the queue.
- **Arming and admission are main-thread-only.** `read_keys` and the
  idle test run serially before dispatch, because the identity must bind
  against one frozen version map for the staleness test to mean anything;
  commits run there too (L11). That is the measured Amdahl floor (M-3.3),
  and moving arming into the pool needs a versioned read-set snapshot — a
  later question than H3's.
- **Admission is CONTINUOUS, not batched** (R9, ruled 2026-08-15; W-S).
  Up to `--workers` fires are in flight; whichever finishes first is
  admitted at the wall immediately and its slot is refilled by
  pop-and-arm. The round barrier it replaced was grounded in no user
  proposal, was convicted by F-22.4, and was also the plane's read
  barrier — which is why W-S replaced the memory model with it (below).
  Out-of-order admission is safe by the §7 re-derivation, not by
  ordering. Two riders belong to the same rule: a wake that reaches a
  worker whose own fire is still in flight is HELD until that fire lands
  (arming a worker twice would run two fires against one identity —
  under the barrier the deferral was structural), and a terminal outcome
  CANCELS the fires still in flight rather than admitting them, because
  close preemption is worth 3.7x and paying for the stragglers would
  spend it back.
- **The memory model under continuous admission** (W-S). Commits are
  main-thread-only and a fire pins ONE generation of the plane's derived
  views, so the only state a pool thread reads live is the store's own
  record/version/blob tables. Immutable records + GIL-atomic dict
  lookups + the §7 identity re-derivation at admission mean a fire that
  read newer-than-pinned state yields, at worst, a discarded proposal —
  never corruption. The argument is stated once, in `orchestrator.py`'s
  opening docstring; `solve/plane.py` owns the generation mechanism.
- **`--workers 1` takes the sequential path verbatim** (no pool), and is
  therefore the exact-determinism ORACLE lane.
- **The close is a TERMINAL CONSUMER, not a provider** (worklist B12,
  ruled 2026-08-12). The consult is orchestrator-timed — a verified
  close preempts everything, so queue-ordering it would defeat its own
  3.7x purpose — and the tree half-admitted the rest: it was never
  queued, never priced, and was bound slotless into `_inflight` under a
  work id nothing scheduled. It now arrives as `CloseConsult`, declared
  here and handed in by the composition root. Its eligibility is the one
  thing the provider costume ever really bought: the consumer names its
  `frontier` key, whose VERSION is the certified membership count, so a
  consult is refused in one integer compare and the O(certified)
  materialisation happens after that gate. The engine records the
  version per gate in-run; a consult that decides nothing now costs no
  commit sequence number either (the spend row used to cost one per
  look).
- **A terminal answer is read off the store, not off the worker.** A
  verifying close writes a terminal `CloseRecord`, which freezes the
  session by itself; the run ends on `session.terminal`.
- **Re-enumeration is total after any structural commit** — O(windows +
  tiles), which H3's corpora make free and a real page will re-measure.
- **The fire-count tripwire raises.** DESIGN calls it observability; it
  is wired as a loud failure because in a fixpoint system an exceeded
  count is a wake-graph bug, and a silent one would be found by nobody.
  It is charged at ARM time, so a pool cannot outrun it.
- **`--complete` is a stop condition, not a consult schedule** (user
  spec 2026-08-09): a solvable fountain state no longer stops the
  session; the session runs until no worker can contribute on any recipe
  entry, then closes once. The net effect matches v1's deferred close;
  the semantics are stated on the stop condition, so nothing about
  consult timing changes.
- **A consult has a MODE, and `--complete` observes** (2026-08-13, with
  P3-1). The mid-run consult under `--complete` used to be skipped
  entirely, which suppressed the OBSERVATION along with the decision —
  the operator watched certificates pile up beside "K unknown". The
  three modes are `observe` (count and report, never close — what
  `--complete` runs per frontier move), `close` (close when the count
  gate opens — the ordinary run), and `final` (skip the count gate — the
  exhaustion consult). Observe consults are counted as `observations`,
  deciding ones as `consults`, so every HEALTH row's consult number
  keeps meaning what it measured. The strings live on both sides of the
  engine↔solve wall and a data pin keeps them equal
  (`test_close_vocabulary.py`, the footing-selector precedent).
- **THREE CLOSE POLICIES, ONE AXIS** (`--no-close`, user ruling
  2026-08-22; the axis is *when may the close layer be entered?*).
  Greedy closes per commit; `--complete` defers the DECISION to the
  exhaustion consult; `--no-close` never enters a deciding mode at all —
  no closing record is read, attempted or written, and the session ends
  OPEN with its certificates accumulated. Both flags answer ONE question
  (`Orchestrator._deferred`), which is what makes `--complete` alongside
  legal and redundant rather than contradictory: `--no-close` already
  implies the deferral, because a greedy per-barrier close would
  contradict never-close. `observe` stays alive under it for the reason
  the bullet above gives — the DECISION is suppressed, the observation is
  not. Four consequences worth naming:
  - the policy is a per-run argument and NOT in `SessionIdentity`. That
    is the point: one state directory accumulates under `--no-close` and
    closes under an ordinary run later, which a lineage fork would make
    impossible.
  - what makes that resume possible is the FOLD, not a write. The store
    opens with `skip_close`, takes no close record and is therefore not
    terminal, so the wall admits commits with its first rule untouched
    (`core/DESIGN.md`, "What the fold admits of a CLOSE"). The rule that
    keeps the resulting journal lawful under every policy is the lead's:
    *a close is terminal only while it is the last word* — a close with
    commits after it is SUPERSEDED, dropped at the fold, and recomputed
    by the next closing run, which APPENDS a new record beside the old
    line rather than rewriting anything. An `integrity_failure` close is
    the one exception and refuses, because it is the only durable trace
    of a write the wall refused rather than a derivation (F-11). Setting
    a TERMINAL close aside is OPERATOR-VISIBLE and is said before the
    run, not after it (`cli.open_receiver` reads
    `store.unadmitted_close`): the skip becomes durable — the close
    SUPERSEDED — the moment this run commits anything, and nothing else
    in the run would ever say so.
  - a `--replay` must run under the close policy the journal was recorded
    under (`engine/replay.py` states the contract and enforces what a
    non-deciding policy CAN enforce). Two halves and one stated blind
    spot: the skipped close line — an exemption that cannot check the
    entry it leaves standing IS a close, because that check is the
    close's own settled batch id and computing it is deciding; and the
    named refusal for a journal whose close is SUPERSEDED, which is not
    walkable whole under any policy (`--no-close` halts on the same
    entry), so the refusal offers the auditable PREFIX instead.
    Crash recovery is the same machinery, and its CLOSING direction is
    guarded there too: a tail accumulated past a superseded close is
    refused up front with the two-run remedy, because re-earning it
    greedily re-decides the close mid-tail and the operator would
    otherwise meet the divergent-refold refusal, whose own named remedy
    (delete the state directory) would destroy the accumulation.
  - it FORFEITS close preemption, the biggest scheduling win there is
    (3.7x). By construction — that is the mode's purpose — and the flag's
    help text says so out loud.

  The word is SKIPPED or SUPERSEDED, never "detached": `detached` already
  means a capture the store holds facts for and this run holds no pixels
  for.
- **Exhaustion is an outcome, not a failure.** Every worker idle across
  every entry ⇒ session open-and-exhausted: an honest partial state,
  resumable when new captures arrive. Terminal states are immutable.
- **A certificate conflict is DATA, and ends the run as a durable fact**
  (F-11, 2026-08-13). Every `CommitRefusal` is fatal — a writer that
  proposes an unlawful state is defective and the crash is the feature —
  with exactly one exception, because exactly one of them is something
  LAWFUL code produces: two independent decodes contradicting each other
  on one work key, from a ~2^-32 CRC false accept or a scissors session
  that mixed two physical sheets. Nothing is wrong with the writer
  there; the data contradicts itself, and L5 says a certificate is never
  voted on. So `_run` catches `CertificateConflict` — that class alone,
  never `CommitRefusal` broadly — and `_integrity_failure` commits
  `CloseRecord(integrity_failure)` carrying the conflict's own message,
  which already names the key and what differed. B13's executed shape:
  deliver what is deliverable, then terminal; mid-run nothing is
  deliverable, so the fact IS the delivery. Three things then cost
  nothing extra: RESUME (a terminal close freezes the session at the
  commit wall, so a later run reports the record and writes nothing),
  the OUTCOME (`_terminal_outcome` reads it off the store like every
  other terminal answer), and the REPORT (the close dict the snapshot
  already publishes — no second channel). The catch sits on `_run`
  rather than at the three commit sites because those three ARE one
  site: serial, pool and replay all commit on the main thread (L11).

- **MARKER-DRIVEN since H4 W2** (the second concurrency ruling,
  2026-08-16; the loop lives in `engine/replay.py`, split out of the
  orchestrator at the same time — following a recorded ordering is a
  second control loop with its own vocabulary, and nothing in the live
  one reads it). The journal records a payload-free START MARKER at
  every dispatch, so a replay launches the pass a marker NAMES against
  the store as of that position instead of re-deriving an order from its
  own queue. That is what makes a POOLED ordering replayable at all: a
  fire dispatched before a neighbouring commit and landing after it has
  no expression in commit order, and the pre-marker loop met it as a
  `ReplayError` or as the journal's tail refusal. Four rules, all ruled:
  - a marker with NO matching commit is a NON-COMMITTING pass, and it is
    one everywhere — mid-ordering (a failed pull pass) and at the
    crashed tail alike. It is replayed for its in-memory effects only
    (tried set, stage memory, acceptance floor) and the work re-arms
    LIVE afterwards; recovery never invents a commit the ordering did
    not record;
  - a marker whose pass cannot even be re-armed at the recovered state —
    its window since placed or done-covered, or a resume that offers no
    placement at all — is simply a no-op pass. Lawful, not an error.
    **But it is now NOTED** (2026-08-17): one such marker says nothing,
    while a marker unarmed AND an ordering left unexhausted AND a
    capture the plane holds with no pixels at all say the same thing
    together — this invocation's INPUTS cannot re-earn this tail, so the
    live run will fold something else at a position the journal already
    holds. Recovery refuses there
    (`replay._require_the_inputs_the_tail_needs`), naming the captures
    and both remedies (the scan files, or an intact
    `<state-dir>.prepared` sibling), because the alternative is meeting
    it downstream as the raw divergent-refold refusal — true, and
    useless, since the remedy is an input and not a repair. That law is
    untouched and still fires for every other cause; this one is
    strictly upstream and strictly narrower, and the engine QUOTES the
    capture identifiers (`Plane.detached_captures`) rather than
    interpreting them;
  - a held pass is matched to a commit by its SETTLED id, because the
    journal records batches as the wall MERGED them (ruling 1);
  - a commit no pass produced is a scheduler-side one (a sleeping
    worker's read-set re-declaration) and is re-derived in place; the
    close's own verdict is made by the caller, out of band as always.

  A cache frame moved with them: a frame is a RESUME POINT, so it is
  taken only where no dispatch is outstanding (`core/store.py`
  `_frame`). Serial runs are unaffected — the pass that just committed
  is the only one there was — and a pooled crash gets a boundary its
  replay can honour instead of markers stranded behind the memo. The
  price is the cache doctrine's own: a saturated pool reaches few clean
  cuts, so its memo lags and a crash re-earns a longer tail.

  **Scope of the claim, measured.** The mechanism is pinned exactly on
  doubles that stage the interleaving (`tests/engine/test_replay.py`: a
  pooled ordering replays byte-for-byte, its journal comes back entry
  for entry, and the same ordering with its markers stripped fails
  loudly), and so is pooled crash-cut recovery. On the REAL provider
  stack the pooled audit was IMPROVED BUT NOT CLOSED —
  `measure/test_pool_e2e.py::test_a_recorded_ordering_replays_byte_exactly`
  failed 3/3 runs before markers and passed some runs after them; that
  file was deleted with the measure cleanup and this real-provider-stack
  measurement has no surviving holder — history has the driver. The
  residue it found is a placement pass that re-proposes differently at
  its own recorded position: a pass whose inputs are not fully
  determined by (store state, dispatch position). That is open work on
  the pull model's in-memory scheduling state, not on the journal.
- **Crash recovery IS replay** (F-16, 2026-08-13). Persistence is
  journal-authoritative: the store fsyncs one entry per commit and
  memoises the state only at the cadence, so a crash leaves the RECORD
  ahead of the MEMO by at most one cadence window. `Orchestrator._run`
  therefore calls `_recover` before the live loop: if
  `store.ordering()` is longer than `store.journal_position`, the tail is
  RE-EARNED — the same `_follow_recorded` loop `--replay` uses, over the
  same cursor, verifying every commit against the id the journal holds
  for that position. Three consequences worth stating, because each was
  a choice:
  - the tail is re-executed, never re-decided. Per-item determinism
    (L12: no clocks, seeded draws, value-bound policy) regenerates the
    content; position-by-position batch-id equality is the check. This
    is F-24's tie between replay and durable state, and it is why the
    two paths are one function rather than two that agree.
  - recovery is SERIAL (`_pool_size` is 1 for its duration) because a
    recorded ordering is one thread's, and it is bounded by the cadence,
    so the pool loses nothing measurable: on the spine e2e, recovery
    re-earned 8 commits of a 424-commit run.
  - proposals produced past the tail are handed back to the queue rather
    than committed. They are exactly what the live loop is about to
    re-arm, and a proposal is not a commitment.
  A run needs no flag for this and an operator sees nothing: a clean
  exit leaves `commit_seq == len(ordering)`, so the whole mechanism
  costs one integer compare. Gate:
  `holo2/measure/verdicts/test_durability.py` cuts one cache frame off a
  finished session and drives it again — same state, same journal bytes,
  same payload — and then does it a second time with ZERO scans, which
  closes the volume from durable evidence alone.

  KNOWN HOLE, on the ledger and NOT closed by W2: a recorded commit can
  fail to re-earn when its descriptor is no longer ENUMERABLE at the
  state the resume starts from — the known case is a payload spend that
  wrote nothing, whose work key the resumed frontier does not offer
  again. The wall stages its cut on a frame boundary that re-earns and
  says so; a future change that moves the tail across such a commit
  fails there, and the fix is this item, not a re-pin.

  SECOND CASE, measured 2026-08-17 when payload was repriced below the
  placement rungs: a recorded PLACEMENT commit cannot re-earn on a
  NO-PIXEL resume (the pass needs a raster; a sleeping pass invents no
  commit, the fold diverges from the recorded tail, the journal
  refuses). Payload-first pricing puts placement last by construction,
  so a crash cut now lands in placement territory typically, not
  occasionally — the durability verdict's no-pixels arm is RED on
  exactly this, per its own pre-registration. The claim as it stands
  today: a CLEAN-shutdown state resumes with no pixels (the flushed
  frames cover everything); a CRASH-cut state may need its declared
  scans back to re-earn the tail. Fix direction awaits the user's
  ruling on this item.

## Measured facts engine relies on

All from `holo2/docs/MEASUREMENTS.md` (H3 bench, toy workers — the
invariance results transfer, the ratios do not):

- **eager beats phased, by a mechanism DESIGN names** (M-3.5): identical
  certificate sets, identical payload, identical BP-attempt counts;
  phasing costs 2.0x wall and 2.2x placement fires. A placement→payload
  barrier withholds exactly the facts that make placement stop.
- **the pool knee is 8** on a 10-core machine (M-3.3): 5.27x wall,
  3.62x per fire, 12 flat-to-worse with 10.9% stale discards. Round
  width tracked the pool exactly, so the limit was not queue starvation.
  Threads, not processes — a process pool cannot help a serial arm step
  and would cost proposal serialization and bulk re-mapping. MEASURED ON
  THE BARRIER: W-S's A/B re-runs it (workers ∈ {1,2,4,8} both sides), and
  the stale-discard rate is expected to rise — priced in fires, never
  correctness.
- **read-set breadth is paid in re-armed workers** (M-3.2): the cost is
  not wakes-per-commit (1.74 → 1.84 across the sweep) but how many
  commits exist at all. Useful-rerun ratio is the diagnostic: 9.4% at
  region scope, 17.3% at one stride.
- **the recipe v0 priors** — one of which was never a measured record at
  all. It said the coarse lanes mint ~95% of certificates and that the
  coarse-first order is cold-count-optimal because hint flow follows
  order. AMENDED 2026-08-17: the stated MECHANISM of the second half does
  not survive the pull model — there are no hints, and a consult reads
  committed poses whatever order it fires in — which is why the
  `quiescent` gate it justified is deleted and coarse-before-fine is a
  price (`place_sched.LANE_COST_PER_RUNG`) instead. CORRECTED at H4-LANES
  stage 2: the ~95% is a SYNTHETIC ARTIFACT (a 2026-07-31 non-closing
  A/B, 575/604 at 41.3% payload coverage) and is withdrawn. Real captures
  read 27.0% (hp c3-cmy8), 46–54% (xerox c3-cmy7), 55.4% (e029's K sheet,
  whose coarse lane alone could NOT close: 1,075 against K = 1,356) and
  89–92% (the e023c HP sheets). Coarse-first is a COST argument, never a
  yield prediction — `engine/recipe.py`'s docstring carries the citations.
- **payload starves below placement on a large domain** (measured
  2026-08-17, real nine-platen scrap demo, pool 8): 2,529 ready workers
  with 1,287 armed payload, and after 431 fires ZERO tiles attempted and
  zero certified, because placement work on a sheet that size never
  dries and `COST_PAYLOAD` sat above every ordinary placement rung. Both
  feedback loops are dormant in that state: no certificate means no
  close preemption, and no certificate means no done pixels, so coverage
  stays 0.0% and no placement window ever exits by coverage either.
  Payload is now the cheapest RECOVERY (8, above ingest and below every
  placement tier).
- **close preemption is the biggest scheduling win**: 3.7x on the
  synthetic regime (v1's number — 49.67 s → 13.46 s,
  `docs/PHASED-SCHEDULE.md`; holo2 has not re-measured it) — and 1,359
  vs v1's 1,930 certificates for the same recovered bytes on the real
  sheet (MEASUREMENTS §H3bis). That is a stop-policy result, not an
  algorithm result.
- **replay is exact and it earned its keep** (M-3.1): getting a threaded
  run to replay serially found two real read-set defects in the toy
  placer — holes in per-item determinism a serial run cannot expose.

## Open ruling LOCAL to engine

**OR-8** (worker pool: threads vs process pool) is answered by
measurement and awaits a user ruling: threads, default 8; reopen only if
a real H4/H5 leaf is measured holding the GIL.

## TO-FIX — engine's ledger

**F-nn** = the adversarial review with its severity scale; **D-n** = the
founding-design deviations indexed in `holo2/docs/DESIGN.md` §15.
Adjudication is H3.5's.

| id | defect | where | sev |
|---|---|---|---|
| F-21 | scheduler lifecycle is represented three ways — SEVEN in-RAM collections (`_workers`, `_entry_of`, `_ready`, `_heap`, `_retired`, `_declined`, `_pending`) plus `_running` and now `_inflight`, `WindowRecord` PENDING/ACTIVE/SLEEPING/RETIRED durably, subscriptions a third partial one. Retirement changes an in-memory set and never unsubscribes, so a certified payload worker's durable subscription becomes a permanent ghost. Shape: one transient `WorkRegistry[WorkId] -> WorkStatus` with explicit reasons, rebuilt from durable facts and spends on resume; persist domain dispositions, not scheduler state. The *reason-publication* half is DONE — `_pending` carries the decline reason and `snapshot()` publishes `declined_by_reason` beside `declined`/`declined_pending`; the unification is deferred (its ghost-subscription half is not safe alone: unsubscribing a retiring worker inside its own commit needs solve to decline a done window permanently at mint time first) | `orchestrator.py` | HIGH |
| F-22.1 | CLOSED (2026-08-10, `_inflight` + `_earlier_ready`): quiescence counted only READY, so a quiescence-gated entry could be enumerated while higher-priority work was armed or running. `_bind` records `WorkId -> entry_index` in `_inflight` and `_disarm` clears it at the commit and at both stale-discard sites, so ARMED and RUNNING count too. RE-VERIFIED under continuous admission (W-S), where the hole would be wider — a commit re-enumerates from inside the admission of ONE fire while its slot-mates still run — and `_inflight` covers it unchanged; pinned by `test_pool.py::test_a_quiescent_entry_waits_for_the_last_in_flight_fire`. Conservative by construction: a deferred enumeration is picked up by the drain-time refresh. AMENDED 2026-08-17 (pricing ruling): the quiescent gate that consumed this answer is DELETED, and with it `_cheaper_in_play` and that pool test. The finding's substance is untouched and still enforced — the surviving instantaneous-dryness rule is the GATED TIER's, which reads the same two books (`Worklist.head_cost` and `Worklist.inflight`, plus the source's own in-flight map) and is pinned by `test_pool.py::test_a_gated_job_waits_for_cheaper_work_ready_or_in_flight` and `::test_a_gated_job_counts_the_sources_own_in_flight_work` | `orchestrator.py` `_bind` / `_next` | HIGH |
| F-22.2 | fairness is accidental: heap priority is strictly `(entry index, worker id)`, so a deep placement stream can starve eager payload and digest-like ids become the within-class policy. Per-entry queues with weighted/deficit fairness and cost classes are the shape | `orchestrator.py` heap | HIGH |
| F-22.3 / D5b | progress is not observable in real time — `ProgressSink` publishes nothing while a worker runs, and `emit(0)` after arbitrary work satisfies the tripwire. The mechanism is `core`'s, the surface `diag`'s, the debt engine's. **NOTE (2026-08-12, user discussion): when this channel lands, the close's COUNTING numbers (the not-ready consult's metadata rank / K / per-block counts) are its natural first tenant** — they are progress, not verdict; the 2026-08-12 report-on-verdict solution stands until then, and a direct solve→diag event path stays FORBIDDEN (it would re-open the dual-observer-feed disease the snapshot unification cured) | `core/work.py`; `diag` | HIGH |
| F-22.4 | **CLOSED by W-S (2026-08-15, R9)**: the round waited for every future before committing anything, so one slow worker blocked its round-mates and delayed a newly solvable close. Both halves landed — continuous admission (`_fill`/`_admit_completed`: a completed fire is admitted at once, its slot refilled) and cancellation-after-terminal (`_cancel`: `shutdown(cancel_futures=True)`, straggler proposals counted as `cancelled` and never admitted). The ruled shape is FULL CONTINUOUS; the armed-order middle this row recommended was rejected (head-of-line blocking kept, run-determinism lost anyway) | `orchestrator.py` `_run_pool` | HIGH |
| F-14 | **POLICY HALF CLOSED** (identity law, 2026-08-11): `SessionIdentity` carries the recipe's ENTRIES and the ORDERED provider ids as data, so a moved gate, a changed price, a new arm or a re-ordered provider binding is a whole-value mismatch `Store.open` refuses — no digest, and no hand-typed `recipe_id` to forget to bump (`Recipe.label` is display). The review's "hash that structure" recommendation is deliberately not taken: the structure IS the identity. Residue: algorithm/decoder VERSIONS and material numerical constants still reach nothing — that is the `DecoderManifest` half, and R3's record manifest is its schema half | `recipe.py`, `records.SessionIdentity`, `cli.decode` | HIGH |
| F-17 | every tile/capture/region/window/pose write is classified structural and triggers total re-enumeration; invalidate and re-expand only the affected providers | `orchestrator.py` refresh; `registry` structural flags | BLOCKER (scale) |
| F-24 (orchestrator half) | **stands, and is now load-bearing** (F-16, 2026-08-13): the same `_follow_recorded` loop is crash recovery, so the gap below is a gap in the recovery path too. What it says: replay applies the proposal the recorded ordering asks for WITHOUT re-running `_is_current` on it (`_run_replay`: the cursor's expected batch id is popped from `pending` and committed; only the OTHER held proposals are re-checked afterwards), and the assembly prefix the recorded ordering carries is consumed positionally and never verified — `holo2/measure/test_pool_e2e.py` documented the gap as `len(ordering) > outcome.commits` before it was deleted with the measure cleanup; this gap has no surviving holder — history has the driver. Divergence is loud only where the batch id differs, not where a stale batch id happens to match | `orchestrator.py` `_run_replay` | MEDIUM |
| lease mutation in the concurrent phase | CLOSED (2026-08-10): `_propose` took and released `LeaseBook` entries from the pool thread while `snapshot()` may read `residency()` from the diag thread — read-modify-write on a plain dict, and a contradiction of L11's "the concurrent phase writes nothing". Latent (no production descriptor declares a `Lease`), HIGH the day one does. Take moved into `_bind` and release into `_disarm`, both main-thread, so the fire stays bracketed and residency is deterministic | `orchestrator.py` `_bind`/`_disarm` | MEDIUM |
| unsynchronized observer snapshot | `cli.main` serves diag on a daemon thread whose handler calls `snapshot()` outside any lock while the main thread mutates `_ready`, `_workers`, `fires_by_worker` and `store.subscriptions()`; `RuntimeError: dictionary changed size during iteration` is reachable on any poll and L12 merely swallows it into `status["session_error"]`. The fix is publishing an immutable snapshot from the main thread at commit boundaries — the natural home for the live progress channel (F-22.3) | `orchestrator.py` `snapshot`; `cli.py` | MEDIUM |
| resumed-terminal `certified` | CLOSED (2026-08-10): `_terminal_outcome` reported `certified=0` on a resume, so re-running a verified session printed "0 certified tiles" while `_exhausted` reported the frontier. `commits`/`fires` are run-scoped and stay zero on a resume; `certified` is a property of the state and is now read off the view either way | `orchestrator.py` `_terminal_outcome` | MEDIUM |
| F-02 | the bind/execute split is not built (binding on the scheduler thread producing immutable inputs, execution in the pool with no live index). R1 narrowed the worker's input to a typed read-only view and staged its blobs; W-S made the DERIVED half immutable (a fire pins one generation of the plane's views) and STATED the residue as a memory model rather than leaving it a convention — the concrete plane still exposes `store`, so record/version/blob reads are live, and their safety rests on immutable records + GIL-atomic lookups + the §7 re-derivation at admission. That argument is sound but it is an argument, not a structure: the row stays open until execution genuinely has no live index | `orchestrator.py`; `solve/plane.py` `store` | BLOCKER |

**Direction recorded, not built**: the DECIDERS
(`holo2/docs/DESIGN.md`) — the orchestrator collects work descriptors
and offers them to deciders answering "reasonable?" and "at what cost?",
with LAW (spend-once, done-gate, residue-targeting, interference)
staying in engine and commit, and desirability becoming tunable
measurement-fed policy. Block-level DONE is its negative half. Both are
user proposals of 2026-08-10 with implementation deliberately after the
refactor; the constraint that survives into any implementation is that
deciders reorder and park but never forbid (L7), and that a verdict is a
pure function of committed state — never of queue timing or clocks.
