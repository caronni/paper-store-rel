# store

The plugin ABI. Types live in [data](data.md); this is who is allowed
to write them, and how.

## What it is

Every mutable cell is a private dict behind a keyed accessor. Typed
folds are the only writers. A fold returns the `FactKey`s that
actually changed, which is what the engine uses to wake subscribers.

holo3: `store.py` is the single-writer merge target. Plugins never
assign `store._certificates[k] = …`. They return a `Certificate`; the
engine calls `_ingest` → `_fold`.

## What it is not

- The ontology. If a fact has no type in data, the store has nothing
  to fold.
- The journal. holo2 made the store a fold of a log. holo3 made the
  store the truth and the snapshot a dump of selected facts. holo4
  does not need a third persistence theory to start (see
  [resume](resume.md)).
- A bag. Open `dict[str, object]` is how illegal merges become
  representable.

## Cell-class (the mutator's job)

Store cells fall in four classes. The ordinal of a decision cell is a
property of the **schema**, not of the producing plugin.

| class | examples | write rule |
|---|---|---|
| frozen inputs | Capture, FormatRow, Window | set once |
| decision | Placement, LatticeSeed, RegionCtx, PlaneField | better-or-no-op via `_adopts(ordinal)` |
| derived | WindowEvidence, ColorEvidenceRow | change detection; pure function of decisions + inputs |
| append-only | Certificate, metadata equations | union; disagreeing certified bits are `IntegrityError` |

Plugins compute honest values. The mutator is the gatekeeper. This
was forced by two writers on placement: per-producer ordinals cannot
be ordered.

Comparability across *different evidence bases* is answered once per
cell in the schema (placement is basis-major so chain/word/cold
mismatch scalars are never compared). Region-ctx is still
quality-only and **open**: ctx logloss is non-monotone in evidence
size, so a later larger-base fit can lose and drop a whole apply
batch. Colour `ColorEvidenceRow` is still last-write-wins — the
fourth decision cell addendum 14 named and did not convert.

## FactKey vocabulary

Closed. Inverted at worker birth. A new key is a compatibility event
for every `reads` function.

holo3's lesson: add a key only when two plugins already smuggle the
same thing. `offsets_of` (sampling attach for fields/swim) is the
pattern — a seam, not a new truth plane.

Collections ("facts whose ids do not exist yet") are how a worker
subscribes to `page_certs` without naming the tiles. They are
derived from the append-only set, not a second copy of it.

## Laws

- Single-writer-by-domain, checked at descriptor-tuple construction.
- Commutative merge is declared per family (lattice seed: max
  support, tie to smaller window ordinal). Everything else is
  compare-and-swap / adopt-or-no-op.
- Cover indexes (window → tiles, colour-row → tiles) are store
  internals for fire-time assembly. They are not facts plugins mint.
- Done-geometry grids are a cache of certificates projected through
  committed poses. Invalidated on cert/pose change. Not a fact.

## Seams

store ← data (types, ordinals).
store ← engine (`_ingest` is the only caller of folds during a run;
resume folds through the same `_ingest`).
store → plugins as a read-only view at prepare time.

## holo4 stance

The store is where "exactly what plugins need, but not more" either
holds or dies. Growing it for one hungry arm is the 16th key. Starve
arms of new cells until the smuggling test passes. Data.md is the
place to argue for a new type; this file is the place to refuse a
fold.
