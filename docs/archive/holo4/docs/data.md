# data

The ontology. If it is not a type here, the rest of the machine is
improvising.

This is the domain to get right before engine, and the one holo2 named
as two truth planes. holo3 implemented it as `data.py`: frozen
dataclasses only, facts and events in one file, units in the names.
holo4 keeps the ontology even if the file layout changes.

---

## 1. Why this is a domain

Plugins, store, and engine all failed in previous trees by *meaning
different things with the same words*. "Plane" was a colourant, a
truth plane, and a session object. "Lane" was a scheduling stratum
and then retired. "Codec" meant a record serializer, a printed
family, and a coding row.

Data is the place those collisions are made unrepresentable. A
`Certificate` is not a `Placement`. An `Event` is not a fact. A
`Window` is not a tile. If a plugin needs a tuple that is not one of
these, either the ontology is incomplete or the plugin is smuggling.

holo2's constitution put this as law: **physical plane** (authenticated
rasters, survey, pixels) vs **logical plane** (the tile map). Solving
is correspondence. Everything else is machinery and carries no truth
of its own. That cut is still the right one. holo3 flattened the tile
map into certificates + fire-time cuts, and dropped a stored
tile-evidence fact (`tiles.freeze` deleted). The planes remain.

---

## 2. Four kinds of value (do not collapse)

| kind | what it is | who writes | durable? |
|---|---|---|---|
| **frozen input** | Capture, Level, PlaneRaster, FormatRow, Window geometry | intake / format / survey-as-birth | snapshot yes |
| **fact** | Placement, evidence, Certificate, RegionCtx, PlaneField, … | plugin job → store fold | snapshot yes (selected) |
| **event** | PoseCommitted, TileOutcome, JobDone, CloseCheck, … | engine merge, from facts or accounting | `events.jsonl`; not resumed as law |
| **scheduling annotation** | WorkerBookmark, tried version, frontier seat | engine, in memory | **no**. Resume re-derives. |

holo2's expensive lesson: promoting hints to durable facts produced
HintState hair and 45 wakes/commit. Demoting them collapsed that.
holo4 does not store a worklist.

**Reductions** (quantized histograms, sufficient statistics) are a
fifth kind that must not become facts: worker-side compression of
evidence so the merge thread never sees a per-cell dump. They die
with the job unless a fold turns them into a named fact (RegionCtx,
PooledColorCtx).

---

## 3. Identity and keys

Units in names: `_px`, `_cells`, `_yx` (row, col), `_in`, `ppc`,
`dpi`, `_dots`. A bare `size` is a bug. Pitch is a `Fraction` of an
inch, never a privileged 600.

| thing | identity |
|---|---|
| capture | SHA-256 of source bytes (`capture_id`) |
| footing / level | `(capture_id, level_index)` with `ppc: Fraction` |
| region | `(capture_id, region_index)` at a level's step |
| window | `(capture_id, level_index, region_index, extent_cells)` |
| tile / work key | `(page, ty, tx, stream_id)` |
| certificate | the work key; bits are the payload |
| format | AES seed / fossil `L:` |

`extent_cells = (y0, y1, x0, x1)` in *region* cells. Windows overlap;
done-geometry is why a window can be COVERED without being PLACED.

Stream is the granularity of LDPC certification and of fountain
`(stream, block)` accounting. K: one stream `"main"`. CMY8: C, M, Y
independent. CMY7: one joint stream. Terminality is per stream.

---

## 4. Physical types

**Level.** One rung of one capture's decimation ladder. Index 0 =
coarsest (historically 2 ppc); last = native. `scale` is native px
per level px, exact rational. Direct-from-native area decimation;
never a pyramid of pyramids.

**Capture.** One ingested scan: id, path, declared dpi, shape, channel
count (1 or 3), platen backing, levels, directory of plane `.npy`.
Duplicate SHAs fold.

**PlaneRaster.** One plane at one level. `open()` is a read-only mmap.
Each worker opens its own view. Plane names are photometric (`g`,
`y`, `r`, `b`) not colourant — colourant identity lives on the
logical side after a pose exists.

**Region / CaptureSurvey.** Survey product: support grid, area, tensor
score, at most one pitch vote per capture. Survey does not read
pilots. `pitch_class is None` means no windows.

These are frozen inputs. Plugins do not improve a Capture. They may
mint Regions (survey is a plugin that *produces* a survey fact once).

---

## 5. Placement types

**Window.** The placement work unit. Supported-cell count, subdivision
depth, lane depth, ordinal. Born from survey + geometry, not from a
hint ledger.

**LatticeSeed.** Per-region reduction of competing lattice hypotheses
(R5): max support, tie to smaller producing-window ordinal. A
declared commutative merge, not last-write-wins.

**Placement.** A committed pose: page, `rot_k`, page origin in cells,
native affine (6-tuple, cell-edge convention), `pitch_px`, route tag,
local cell coordinates, quality, refine basis. This is geometry
authority. It is not a content claim.

Decision ordinal (schema-owned):

```
(route == refine, len(refine_basis), -quality)
```

Basis-major: an adopted revision outranks any original; a larger
basis outranks a smaller one. Chain/word/cold mismatch scalars are
never compared across evidence bases. That is why two writers can
touch placement at all.

Integer cell offset is addressing's job. Photometric or spectral
objectives must not mint it.

---

## 6. Evidence types

**WindowEvidence (K).** Per-window calibrated scores: page cells,
v1-convention scores `(midpoint−means)/spread`, PAVA curve, search
count, marginal and printed LLR, accepted/refusal, held-out logloss
(ownership key), ctx adopted. Bounded. A refusal is a null with a
reason, not a zero array that looks like p=0.5.

**RegionCtx.** 9-bin ordered offsets per (capture, level, region),
adopted flag, validation logloss. Decision cell; quality-only ordinal
is **provisionally** `(adopted, -logloss)` and is known to be
non-monotone in evidence size. Open ruling: quality-only vs
evidence-base-major. A refused later fit can drop a whole apply
batch.

**ColorEvidenceRow.** Feature rows, not LLRs. Arity is family (1 / 6 /
3). Held-out logloss present; fold in holo3 is still last-write-wins.
That is the fourth decision cell the cell-class law named and did not
convert.

**ColorCtxPopulation / PooledColorCtx.** Cross-capture pooling of
(state, plane, bin) populations for a page/rung. Bins are *not*
pooled (ink map is capture-optical). Each lane adopts only if it
beats its own held-out head.

**PlaneField.** Per-(capture, level, page, plane) translation delta in
**printed dots** on the tile grid, with support, residual, site
counts. Quality ordinal `(n_certificates, -residual)`. Default off:
if the dial is off the family is never written. Attach at sampling
(`offsets_of`), never at placement.

**Not a type: stored tile evidence.** Fire-time `TileCut` from covering
windows, owner by held-out logloss. Revisable until certification.
holo3 deleted `tiles.freeze` because both ancestors stored something
the attempt could re-cut. Do not bring it back for resume convenience;
resume regenerates evidence (see [resume](resume.md)).

---

## 7. Outcome types

**Certificate.** `(page, ty, tx, stream_id, user_bits, source)`.
`user_bits[0]` is the metadata bit; `[1:]` is the fountain symbol.
`source` is the producing plugin/tier. Same key, different bits →
`IntegrityError`. Same bits → no-op, standing source kept
(corroboration). Append-only. This is content authority.

**AttemptFact.** One budgeted BP try: stage, outcome
(`below_attempt_floor` / `attempted_failed` / `certified`),
informative count, iters, syndrome/CRC flags, component signature
`(capture, level)*`. Retry births from this fact. FLOOR vs ATTEMPTED
are different next-work, which is why the tiles status row splits
them.

A certificate is not an attempt that went well. An attempt can fail
forever; a certificate cannot be revised. NeedMap / done-geometry
consume certificates, not attempts.

**JobResult.** `(facts, events, cpu_s)`. The only thing a job returns.
Facts go through folds. Events go on the append-only list. cpu_s is
accounting, not a fact.

**IntegrityError.** Mixing sheets, disagreeing certificates, multi-writer
domains, algebraic inconsistency in metadata. Exit 1. Never voted
away.

---

## 8. Events

Events are values for the observer: RunOpen, CaptureOpen, SurveyDone,
PoseCommitted, WindowSettled, WindowRetired (with *cause*: placed /
exhausted / done_covered), TileOutcome, JobDone, CloseCheck, FieldFitted,
RunDone, SnapshotReplayed, …

Rules (from DIAG-DESIGN, load-bearing here because the types live
next to facts in holo3):

- No live object crosses into diag.
- Never print zero where the fact is unavailable.
- Frame revision is `len(events)`, never a clock.
- `SnapshotReplayed` is accounting so a resumed run does not print
  CERTIFIED 0 over a verified close. The engine must not *read* it
  for control flow.

Whether events stay in the same module as facts is a file-size
question. They must not become a second store.

---

## 9. Laws the types have to make true

- **Candidate / committed / certified.** Hints and rival poses cannot
  corrupt evidence. Committed poses may sample. Certificates may
  label and suppress. A candidate is cost only.
- **One SHA, one capture.** Footings of one capture are correlated.
  Footings of different captures may combine as bounded LLRs after
  ctx de-correlation.
- **Per-stream terminality.** CMY8 Y empty does not kill C.
- **No tile-shaped evidence fact.** Assembly is a cut, not a freeze.
- **Cell-class.** Decision ordinals live on the value (`placement_ordinal`,
  `region_ctx_ordinal`, `plane_field_ordinal`, `lattice_seed_ordinal`).
  If you cannot compute the ordinal from the fact alone, the schema
  is not ready.

---

## 10. What data must not grow into

- A god-module of helpers. Ordinals that are one-liners may sit next
  to the class; geometry kernels go to lib.
- Plugin-private structs that leak into the store. If only `tiles.local`
  understands it, it is not data.
- Version stamps of source code (G2). Schema version of *this*
  ontology is allowed; hashing `engine.py` is not.
- A parallel "debug" type for every fact. That is an event, or it is
  nothing.

---

## 11. Seams

data ← intake, format (inputs).
data ← plugins (facts, via store).
data → store (the only writer), engine (birth types, close inputs),
diag (events).

The closed `FactKey` list is *store/descriptor* vocabulary about
these types, not a second ontology. When a new type needs a key, the
argument starts here ("is this a fact?") and ends in
[store](store.md) ("does anyone already smuggle it?").

---

## 12. holo4 stance

Write the types until illegal states are hard to spell. Then stop.
The engine should be able to run a decode knowing only: inputs, the
fact union, JobResult, IntegrityError. Every other name is a plugin's
problem or a store cache.

Open inheritances to resolve in this domain, not in a plugin:

- region-ctx ordinal (quality vs evidence-base)
- ColorEvidenceRow as a real decision cell
- whether events share the module with facts
- PlaneFieldTiers as event (already) vs the temptation to persist
  nested dictionaries
