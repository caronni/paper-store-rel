# plugins

The only place new retrieval ideas are allowed to land.

## What it is

One frozen `PluginDescriptor` per row: name, subject kind, birth,
reads, eligible, stage, cost, retire, prepare, produces. The engine
knows nothing else. A job is a pure function over a snapshot; it
returns `JobResult(facts, events, cpu_s)`.

Two **stability classes**. The engine must not care. Humans must.

**Core rows** (freeze-grade): survey, place, calibrate / ctx / colour
assembly, tiles.scan / union / retry, maybe refine. These are how a
good print of a known format becomes certificates. Changing them is
a receiver-policy event.

**Residue rows** (schedule-on-residue, monotone, default-off or dear):
fields, planek, swim, local, uplift, pooled_ctx, revisit. These are
how a hard sheet's last hundreds of tiles move. They fire only on
uncertified addresses (or they are not residue). They may lose on
price.

## What it is not

- A phase. v1's scan→union→retry and chain→word→cold are prices and
  eligibility, not sequencers. Writing a sequencer is a defect.
- A home for format kernels or for store folds.
- One cognitive object. "It's just another plugin" is how the 18th
  descriptor arrives.

## Descriptor contract (inherited shape)

- `born_by` + `subjects_of` — workers appear when a fact of those
  types is ingested.
- `reads` — inverted once at birth into the engine's subscription
  index. Staleness is a version bump, not a stored hint.
- `cost(store, subject, stage, attempts, last_cost)` — the plugin
  owns the number. The engine only pops. That split is right for
  isolation and currently wrong for cost (see [engine](engine.md)):
  literals do not see cpu-s/cert.
- `produces` — single-writer-by-domain. Two prefixes writing the same
  fact type is an integrity error at construction, except a declared
  re-arm row (`revisit`).
- Prepare sees the store; the job does not mutate it.

## Laws

- Residue is monotone: an arm that cannot prove universal
  non-regression does not have to win a global A/B. It only runs
  where nothing is certified yet.
- Held-out refusals are bit-exact nulls.
- A plugin computes honest values. The store's mutator adopts or
  no-ops. Plugins do not own ordinals (cell-class law).
- Fire-time assembly: no stored tile-evidence fact. The attempt cuts
  cells from covering windows at prepare/job time.

## Seams

plugins → data types, mechanisms, lib, format.
plugins → store only through returned facts.
plugins ↛ engine internals (no "am I the last worker").
The generated schedule table (`SCHEDULE.md` in holo3) is the
documentation of this domain. Protect it like `ldpc_data`.

## holo4 stance

New detection = a new row, or it does not ship. Core rows freeze on
a corpus snapshot. Residue rows publish best-on-record and can be
priced off the machine. Do not grow `place` to avoid adding a row.
Do not add a row to avoid pricing the ones you have.
