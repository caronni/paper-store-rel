# diag — DESIGN

The observer: status service, panes, published artifacts. diag reads
anything and is read by nothing but the composition root. It is strictly
downstream, strictly disposable and strictly state-inert.

Constitution: `holo2/docs/DESIGN.md`. Public surface + rationale: the
`__init__.py` docstring.

## Purpose

- **`status`** — `StatusProvider` (the instants the run publishes,
  formatted as JSON on the reader's own thread), `FrameCache`
  (pane frames composed on demand, cached per `(page, capture,
  revision)`), `serve` (a daemon-thread HTTP endpoint), `finalize`
  (terminal frames swapped in at the end of a run).
- **`panes/`** — the derived pane model, the palette/canvas primitives,
  the four panes and the composed frame, the browser shell, and the
  on-disk artifacts written to the `<state-dir>.diag/` sibling.

## Public surface

`holo2.diag.__all__` = `StatusProvider`, `finalize`, `serve`, pinned by
`holo2/tests/test_surfaces.py`. `panes` is imported by `status` at import
time and is not re-exported; tests and the renderer import
`holo2.diag.panes` directly. **Pillow is a hard dependency, not an
optional one**: a tree without it fails at `import holo2.cli` rather
than degrading to a silently pane-less observer (the freshness doctrine
bans the compat branch that used to do the degrading). diag declares no
exceptions — it raises none across a package boundary, because a failure
here is swallowed by construction.

## Owned record families

**None.** Nothing in diag may write durable state.

## The laws diag enforces, and where

| law | where |
|---|---|
| **L12** observer boundary | the whole package. The provider only *reads* what the run published to it and the store; it calls nothing back into a running scheduler; the endpoint only serves bytes; every failure on this side is swallowed rather than raised into the receiver (a snapshot the run could not mint arrives as `session_error`, exactly as the pull path used to report it) |
| **L11/L12** no clocks | frame identity is the store's commit sequence (`PaneSource.revision` is that number wearing a frame-facing name, never a new fact), and HTTP responses use `send_response_only` precisely so the stdlib does not stamp a `Date` header. Precisely: no holo2 FRAME reads a clock, which is what the `clock_watch` pin measures. `DiagServer.stop`'s `join(5.0)` and `serve_forever`'s 0.5 s poll do read the stdlib's — they are transport lifecycle, outside every frame and every receiver path |
| **L15** status honesty | the panes report OPEN as OPEN and name the refusal reason; a run with no addressable region says so |

Two structural rules the pane model keeps rather than assumes: it builds
its OWN `StoreIndex`, `TileMap` and done projection instead of borrowing
the session's derived views, and it must be able to fail (a render
racing a commit is retried once, then reported into the frame — which is
only inert because the objects it damaged were its own). The first rule
was originally a RACE argument (a render thread warming the plane's
lazy caches would mutate something the committer owns); W-S wave 1
removed that hazard — the plane's views are immutable per generation and
built under their own lock — and the rule STANDS on the second reason
plus independence: the observer owns what it damages, and a private
index costs one pass over sorted keys and couples the surface to
nothing.

**Always on** (user ruling 2026-08-09): every run serves the status
surface on `--diag-port` (default 8024). A busy port is a reported,
swallowed non-event, never a run difference.

**How the observer finds the run**: the only mechanism is the explicit
`bind_plane`, which `cli.decode` calls with the session's derived plane
— named wiring that cannot degrade silently when an attribute shape
moves. The discovery fallback that used to walk `vars(orchestrator)`
behind the snapshot callable is GONE: it bound whichever member quacked
first and *nulled* `_frames` on every member that did not, so in
production order it threw away the explicit binding (and its underlay
memo) and only worked back by attribute-declaration luck.

**How a status is produced — PUSH, not pull.** The orchestrator mints a
frozen `RunSnapshot` on the MAIN thread at a commit boundary, and only
when a poll has set the wanted flag (`StatusProvider.wants_snapshot`);
`status()` formats the last instant it was handed. The pull it replaced
ran the derivation on the HTTP thread, iterating the scheduler's live
collections — a race the observer had no business taking, and one L12
could only swallow after the fact. The scheduler's collections are still
main-thread-only, and under continuous admission (W-S) the instant is
minted BETWEEN admissions, so it never shows a half-applied commit. The trade is declared staleness: a status is the run as of its
last commit.

**One owner for the commit counts.** The run hands the provider its
`CommitLedger` and every commit in the session is counted there once —
ingest's included (they are parked here until the run adopts the ledger,
never tallied twice). The stream publishes the session total and the
run's own `scheduled_commits` subset under two different names, which is
what ended the measured 472-vs-471 disagreement where the six-row block
printed the stream's count over the orchestrator's ratio.

**What diag publishes under its own names**: `revision` is
`store.commit_seq` (frame identity, not a second counter), and
`ready_by_family` in `report.json` repeats the engine snapshot's own
`by_family` — B4 put the glossary word on both sides, so diag translates
nothing here. `sleeping_by_subscription_key`
counts subscription-key KINDS, not keys — pane C's label says so.

## What the surface must answer

The dataflow model raises worker/queue questions v1 never had to, and
the surface exists to answer them: ready-queue depth and composition;
running / sleeping / retired workers, sleeping keyed by subscription;
per-worker fire counts; wakes-per-commit and useful-re-run ratio; cold
candidates and transform-cache refcount/residency; tile-map,
done-coverage and close progress.

## Measured facts diag relies on

- **Status-first is a measured discipline, not taste**: status publish
  0.3–0.5 ms vs 61–118 ms for a rendered frame (v1 measured). The status
  channel never waits behind a render, and a frame is recomposed exactly
  when the receiver has committed something — a work-counted throttle.
- **The H3 diagnostics ARE the measurement instrument**: every number in
  `holo2/docs/MEASUREMENTS.md` §M-3.1–3.5 (wakes/commit, useful-rerun
  ratio, stale discards, round width) is read observer-side from this
  surface. An observer that cannot see the fixpoint cannot debug it —
  M-3.1's two read-set defects were found through the trace and the
  counters, not by reading code.
- The live panes were watched by the user through the H3bis real runs,
  and the finalize artifacts were pinned by test
  (`holo2/measure/test_diag_panes_e2e.py`) — deleted with the measure
  cleanup. The session-LESS half survives
  (`holo2/tests/diag/test_diag_panes.py::
  test_finalize_without_a_session_still_writes_what_it_has`), but the
  real-decode finalize-artifact claim itself has no surviving holder —
  history has the driver.

## TO-FIX — diag's ledger

**F-nn** = the adversarial review with its severity scale; **D-n** = the
founding-design deviations indexed in `holo2/docs/DESIGN.md` §15.

| id | defect | where | sev |
|---|---|---|---|
| DG-1 | **CLOSED** (WP-5/1). Was: the "done-gated" population bar read `workers["declined_done_gate"]`, which nothing had published since R1, so the AMBER bar was permanently 0; `report.json` emitted the same dead key as `null` while omitting both real numbers. Now pane C draws two bars — `declined` (AMBER) and `re-offerable` (ORANGE) — and the report carries `declined` + `declined_pending` under their real names, because a permanent decline and a re-offerable one mean different things. Pairs with the engine's `declined_by_reason` (WP-4/12) | `panes/render.py`, `panes/publish.py` vs `engine/orchestrator.py:775-776` | HIGH |
| DG-2 | **CLOSED** (WP-5/13). Was: `PaneModel.notes` was derived at five sites in `panes/model.py` and read NOWHERE, while pane A printed one fixed "no surveyed region is schedulable" for all three causes — including a reopened terminal session, whose real reason is that it ingests nothing. L15 was being broken by the surface whose stated job is naming refusals. Pane A now prints the derived notes and falls back to the generic line only when there are none | `panes/render.py` pane A | MEDIUM |
| DG-3 | **CLOSED** (WP-5/9). Was: `diag/__init__.py` and this document claimed `panes` is imported lazily because "Pillow is optional at call time". It is a hard dependency (`pyproject.toml`), the guard turned a broken install into a silently degraded observer, and the freshness doctrine bans the compat layer. The guard and its five branches are gone; a tree without Pillow now fails at `import holo2.cli` | `diag/status.py`, `diag/__init__.py` | LOW |
| DG-5 | **CLOSED** (the elegance wave). Was: `commits`/`wakes` tallied by two owners bumped in the same breath — `DiagCounters` here (fed by ingest too) and `_Counters` in the orchestrator — which measurably disagreed (472 vs 471 on the bench) while `status_rows` printed the stream's count beside the orchestrator's ratio, and pane C plus the CLI epilogue printed the other number under the same word. Now one `CommitLedger` counts every commit of a session once, publishes the total and the run's `scheduled_commits` subset under two names, and both surfaces read one instant. The same change replaced the cross-thread pull with a main-thread push and deleted the clobbering discovery walk | `status.py`, `panes/render.py` vs `engine/snapshot.py` | HIGH |
| DG-4 | the surface promises this document makes and nothing answers: **cold candidates** and **transform-cache refcount/residency** (below, "What the surface must answer") have no producer anywhere — no orchestrator snapshot key, no pane. `LeaseBook.residency()` exists but no production descriptor declares a `Lease`. Either the promise retires or the producers land; both are post-campaign (W-D/D14, with the deciders) | this file, "What the surface must answer" | LOW |
| F-22.3 / D5b | progress is not observable in real time: a long fire is bounded but invisible, because quanta publish at fire end. Publishing them through a failure-swallowing observer queue is what makes "no silent stages" a live signal rather than only a tripwire (the debt is `engine`'s, the mechanism `core`'s, the surface diag's) | `core/work.py` `ProgressSink` | HIGH |

**Pane maturation is deliberately deferred** (WORKPLAN H8): the
e023c-style pane viewer and transport port land only if the status view
proves insufficient on real runs. It has not yet. Not a defect.

## Carried leaves

The panes are cloned in vocabulary from `src/holo/receive/diag` and
rewritten to holo2's nouns (capture / tile map / worker queue / close).
Nothing here is oracle-pinned against `src/holo`: an observer has no
byte-exact contract to keep.
