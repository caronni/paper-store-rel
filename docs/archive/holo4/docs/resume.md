# resume

A fold, not a log.

## What it is

At RunDone, dump a selected set of **facts** to
`<run-dir>/facts.npz`. `--resume` loads that file through the
ordinary `_ingest` path so births, the FactKey index, and the
certificate set rebuild. Evidence that is derived is *not* in the
file; it regenerates when the core rows fire again (or it is cheap
enough to persist — that is a size decision, not a third store).

holo3 reversed an early "no resume" charter ruling into this lean
snapshot: no format guard, no source-hash, no drift awareness. A
dropped capture crashes. Compression is DEFLATE. `SnapshotReplayed`
is a diag event so status does not print CERTIFIED 0.

## What it is not

- holo2's journal. Replay of decisions is a different machine. It
  was the right answer to envelope-snapshot tax and the wrong
  cognitive load for a laptop decoder.
- Scheduling state. Bookmarks, tried versions, heap seats do not
  survive. They re-derive. Re-trying a version is waste.
- A migration. Schema identity is the fact-type set. Unknown types
  refuse; they do not skip.

## What belongs in the snapshot

Durable, expensive to recompute, or load-bearing for identity:

- surveys, windows, lattice seeds, placements
- region ctx, pooled ctx, plane fields (if the dial wrote them)
- certificates, metadata equations
- capture list (SHAs). A SHA that is not among this run's scans is
  the dropped-capture crash.

Not in the snapshot (regenerate or RAM):

- WindowEvidence / ColorEvidenceRow (unless measured as a wall
  problem)
- frontier, bookmarks
- events (the jsonl is the audit; the npz is the fold)

## Laws

- Same `_ingest` as live facts. A resume-only writer is a second
  store.
- No awareness of "are we the same binary." G2: editing source must
  not invalidate state. A format *row* mismatch may crash; a git
  hash must not.
- `--no-close` / `--complete` are invocation-local. They are not
  bits in the npz. A resumed run takes the flags of *this* CLI.

## Seams

resume → store/engine (`_ingest`).
resume ← data (which types are in `FAMILIES`).
resume ↛ diag except `SnapshotReplayed`.

## holo4 stance

This is enough. Do not add a journal to make resume "correct" under
`--workers N`. Payload identity is the SHA. Harvest differences at
N>1 are already an engine contract. A snapshot that cannot round-trip
certificates and placements is broken; a snapshot that cannot
round-trip the heap is working as designed.
