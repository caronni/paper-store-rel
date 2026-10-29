# engine

The machine. It does not know what a BCH word is. It does know what
is worth doing next, whether it has already been done, and when to
stop.

This is the other domain to get right early. holo1 serialized a
partial order and spent half its lane time on work whose uselessness
was knowable. holo2 named the model of computation and then buried it
in a journal. holo3 made it a descriptor loop with literal prices,
and a 12-hour soak showed what literals do. holo4 has to hold the
model and take cost seriously.

---

## 1. Model of computation

> Facts make work derivable; gates make it eligible; prices order it;
> spends make it happen once; terminality makes it stop.

Nothing else is mechanism. Phases, rungs, mop-up, "the colour
pipeline" are emergent from that chain, or they are a sequencer, which
is a defect.

Two work sources, one order:

- **Descriptor path.** A fact is ingested → matching descriptors
  birth workers on subjects → each worker has an inverted read-set →
  a change of a read key bumps `version` (a wake) → if eligible and
  not tried at this version, prepare a job at a cost.
- **Placement as a work source** (holo2 pull model, carried). Hints
  are not facts. A window consults committed poses at fire time,
  tries a route, subdivides on exhaustion. The engine sees this as
  one descriptor (`place`) with stages, or as a `WorkSource` peeking
  the same heap. Two APIs for one cost order is acceptable; two
  heaps is not.

There are no ladders. Cheap-first is a property of the numbers, not
of a `for stage in …` in the engine.

---

## 2. What the engine owns

- The frozen `DESCRIPTORS` tuple and the single-writer-domain check
  at construction.
- Birth: `born_by` × ingested fact → `subjects_of` → `WorkerBookmark`.
- The inverted `FactKey` index (materialized at birth; re-derived
  when a pose key is the worker's own subject).
- The frontier heap: `(cost, seq, plugin, stage, subject)`. Stale
  seats are skipped, not deleted in place.
- One-in-flight per bookmark; a mid-flight wake sets `pending` and
  re-queues after merge.
- `tried_version`: fire at most once per version. Resume has no
  tried-set (it is RAM); re-tries are waste, never wrongness.
- Fill: pop while `len(inflight) < workers`. `--workers 1` is the
  determinism oracle. `N>1` is payload-byte-identical; certificate
  *sets* at N>1 may be race-close dependent and must be named as
  such.
- Merge: main thread only. `_ingest` each fact, append events,
  account cpu/certs/poses/words, then close-consult and fill.
- Done-geometry consult: a place/calibrate/revisit worker whose
  window is fully certified on every stream is retired with cause
  `done_covered`. Payload rows are never gated (they act on
  uncertified tiles).
- Close consult: see [close](close.md). Not a descriptor.
- Accounting: jobs, cpu_s, certs, poses, words per plugin; attempt
  histogram; stale skips; wakes. Report-only until prices listen.
- Run lifecycle: intake (not a plugin) → descriptor loop to
  fixed-point or verified stop → snapshot → `RunResult`.

## 3. What the engine must not own

- Prices as *invented* numbers. holo3 went further: "engine owns no
  pricing at all; every price lives in the plugin." Isolation-wise
  that is clean. Cost-wise it is how `tiles.local` at 220 occupied
  13/14 workers at 1330 cpu-s/cert while planek (97 cpu-s/cert) sat
  at 3598 queued. **The engine owns the contract with cost.** Plugins
  propose a cost function; the engine is allowed to observe cpu_s
  and refuse to fill a row that has gone nonlinear. That is not a
  ceiling on a *domain* (L7: never narrow a search). It is a
  scheduler that can lose.
- Format algebra, LLRs, BCH.
- Plugin names as algorithms. `if plugin == "tiles.planek"` in the
  engine is a sequencer sneaking back.
- Durable scheduling state. Bookmarks, tried versions, the heap, the
  index: RAM. Crash loses no *facts*. It loses the worklist, which
  is re-derived.
- Diag rendering. It assigns a frozen `EngineStat` to a one-slot
  gauge and appends events. That is the whole interface.

---

## 4. Birth, wake, fire, merge

```
ingest(fact)
  fold → (changed, keys, kind)
  if changed:
      births(fact)           # new bookmarks
      touch(keys)            # version += 1, push

fill
  pop heap
  skip stale seat / retired / same tried_version
  retire() ? drop
  eligible() ? else continue
  stage() / cost() — if cost rose, repush, do not fire
  prepare() → Job
  attempts += 1
  submit

merge(future)
  for fact in result.facts: ingest(fact)
  events += result.events
  account cpu, certs, poses, words
  inflight clear; if pending: push
  maybe close-consult
  fill
```

Lost-wake is impossible if: commit (ingest) **then** ping (touch),
and claim **test-and-clear** then consult. A race costs one spurious
pass. holo2 proved this; keep it.

`reads` that include the worker's own pose key must re-derive on that
wake (the pose *is* the subject). Everything else uses the birth
read-set. Growing reads after birth is how the index lies.

---

## 5. Prices and the 12-hour problem

Prices are ordinals in one global order. holo3's table (illustrative,
not a freeze):

```
survey 10
calibrate / ctx / colour assembly 15
tiles.scan / union / retry 20
place 40–150 (stage ladder)
colour re-fit 160×n
pooled_ctx 170×n
fields 180×n
refine / revisit 200
uplift 210/220×n
local 220
planek 230×n
swim 240×n
```

+2 per finer rung so coarse-before-fine *emerges*. Dear residue gated
on dryness is the intended law: do not swim the page until scan/union
have had their chance. The r0850 soak violated the *spirit* because
local is cheap on the table and dear in cpu, and fill is greedy on
the table.

holo4 engine obligations, if this tree grows code:

1. **Accounting is first-class.** cpu-s/cert, fires/subject, cpu/fire
   vs declared price. Already computed; currently report-only.
2. **A row that has gone nonlinear can lose the fill.** Options
   (pick one, don't pick all): dryness gate that treats "local has
   N inflight and zero certs in the last K merges" as not-dry for
   cheaper residue; inflation of last_cost from measured cpu;
   a wall budget per residue row. Report-only is how 12 hours happen.
3. **Never a search ceiling.** Losing fill is not "this tile may
   never be attempted." It is "not now, while a cheaper-measured
   row exists."
4. **Close preemption stays off the heap.**

Churn detection (DESCRIPTOR-PLAN addendum 15) belongs here: a priori
job-count goldens on deterministic serial decodes, plus end-of-run
advisory. Never a cap that hides a bug by refusing to run it.

---

## 6. Done-geometry

A certificate plus its minting pose projects to scan pixels (or to
page cells, which is cheaper and almost as strong). A window whose
supported extent is fully certified on every stream is not posed,
not searched, not prepared. Cause `done_covered` is a first-class
retirement, distinct from `placed` and `exhausted`.

Address-space prune needs a pose (chicken-egg). Pixel/cell-space
does not. That is the whole idea.

Colour leak (OPEN-2026-08-31): colour evidence is per-lane, so
window-granular done-ness cannot suppress the colour *lane*. Endgame
CPU sits there. That is an engine/data question (what is "done" for
a multi-stream window?), not a new plugin.

Payload rows skip the gate: they exist to act on the uncertified
remainder.

---

## 7. Close consult

After a merge that grew certificates, and at exhaustion:

- If `--no-close`: observe, do not stop.
- If ordinary and metadata+fountain verify: stop, preempt inflight
  (or drain them without ingesting new work — pick one and pin it).
- If `--complete`: observe until the heap is empty of core rows
  (residue policy: either exhaust them too, or consult once at
  core-quiescence; name it).

Count-ready is a *necessary* condition (symbols ≥ K, rank 24, 48
equations). It is not sufficient. The SHA is sufficient.

`--complete` must not starve retry: in an earlier CMY8 defect, close-ready
blocked retry. Structurally impossible if close is not a competing
row and retry is just another eligible worker.

---

## 8. Concurrency

Jobs are pure. The store is not visible to them except as the
immutable snapshot `prepare` captured. Merge is the only mutation.

`--workers 1` = same code path, no pool required for correctness.
`--workers N` under free-threading: no locks if the above holds.
GIL-bound CPython is not an excuse to add a journal.

Certificate *set* at N>1 is allowed to differ in harvest (who won a
race to a tile) if and only if bits agree or the conflict is fatal.
Payload SHA must not depend on N. Say that in a contract test, not
in a comment.

In-flight at stop: drain or cancel. Cancel must not ingest a partial
JobResult. Drain is simpler and is what "pure jobs" buys.

---

## 9. Intake and snapshot as engine verbs

The engine *calls* intake before the loop and *calls* snapshot at
RunDone / `--resume` start. Neither is a descriptor. Resume folds
through `_ingest` so births and the index rebuild. Scheduling RAM
starts empty. See [intake](intake.md) and [resume](resume.md).

---

## 10. Seams

```
        intake
          │
          v
      ┌─────────┐  facts   ┌─────────┐
      │ engine  │<────────>│  store  │
      └─────────┘          └─────────┘
        │     │                   ^
        │     │ prepare           │ fold
        │     v                   │
        │   plugins ──────────────┘
        │
        ├─ close consult ─ format/close
        └─ events, gauge ─ diag
```

The engine imports descriptor, data, store, close, intake, snapshot,
the DESCRIPTORS tuple. It does not import `lib.bch`.

---

## 11. holo4 stance

Build the engine as if plugins will be hostile: they will propose
cheap prices for dear work, they will grow reads, they will try to
ask "am I last." The answers are: measured cost can demote a row;
reads are frozen at birth plus the one pose-key re-derive; lastness
is the heap being empty.

Do not rebuild holo2's journal to get resume. Do not rebuild v1's
phases to get coarse-first. Do not put close on the heap to make it
"just a plugin."

The test of this domain is not a clever scheduler. It is: a good
page certifies on scan/union/retry in minutes; a hard page's residue
cannot hostage the pool for 12 hours without the accounting page
screaming; a verified SHA stops the run; `--workers 8` does not
change the payload.
