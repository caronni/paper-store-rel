# Holo generator and receiver software architecture

Status: descriptive map of the current `src/holo` implementation,
2026-07-29; module lists re-verified 2026-08-02 against the payload-rework
worktree (RECEIVE-DESIGN v0.38 — the Phase-4 file splits are LANDED:
`production.py` → `production_payload.py` + `production_close.py`, and
`_payload_windows.py` → `_payload_sampling.py` + `_payload_context.py` +
`_payload_reuse.py`). This note is intentionally smaller and less
normative than
[HOLO-DESIGN](HOLO-DESIGN.md) and
[RECEIVE-DESIGN](RECEIVE-DESIGN.md). Those documents win if this overview
becomes stale.

## 1. What “essential” means here

There are four useful boundaries:

1. **Format and numerical core** — determines the printed cells or turns
   scan evidence into certified symbols and SHA-verified payload bytes.
2. **Operational authority** — not encoded on paper, but required by the
   current product for safe selection, restart, multi-capture combination,
   conflict detection, and atomic publication.
3. **Detachable support** — presentation, convenience, and downstream
   diagnostic/audit projections; never the authoritative causal ledger.
   Removing it may require refactoring imports, but must not change printed
   cells, certificates, state, or recovered bytes.
4. **Qualification and provenance** — tests, synthetic channels,
   characterization, legacy comparisons, and physical-run tooling. This is
   outside runtime, but remains essential to making credible changes.

In this note, **nonessential** means outside boundaries 1 and 2 for a given
exact-format generate/decode operation. It does not mean useless or safe to
delete casually. Merely being absent from the paper format is not enough:
anything that changes certificate production or authoritative selection
remains part of boundary 1 or 2.

## 2. Production boundary and shared kernel

The two production paths share the format kernel but not their orchestration:

```text
                         format + core
                       /               \
payload -> gen -> printable pages     authenticated scans -> receive -> payload
```

The production generator, receiver, runtime, and CLI import neither
`paperholo` nor `experiments`. Legacy modules are imported only by
qualification and synthetic tooling; production contains independently owned
ports whose provenance is documented.

The shared, format-bearing packages are:

| Package | Responsibility |
|---|---|
| [`holo.format.descriptor`](../src/holo/format/descriptor.py) | `Coding` and `FormatSpec`: codec, cell size, streams, page geometry, format seed, tile addressing, and address-space limits |
| [`holo.format.profiles`](../src/holo/format/profiles.py) | Exact K/CMY7/CMY8 alphabets, furniture counts, logical streams, and shortened LDPC banks selected by each coding |
| [`holo.format.layout`](../src/holo/format/layout.py) | Exact 600-dpi media raster, payload field, borders, origin, and 64×64-tile grid |
| [`holo.format.pilots`](../src/holo/format/pilots.py) | Deterministic 100 BCH word sites, word values, and color dust furniture |
| [`holo.format.metadata`](../src/holo/format/metadata.py) | Addressed GF(2) equations carrying version and canonical `K` |
| [`holo.format.envelope`](../src/holo/format/envelope.py) and [`streamset`](../src/holo/format/streamset.py) | `{SHA-256, u32-BE length, payload}` framing and minimal-`K` arithmetic; color stream-major mapping and reassembly; close enforces canonical `K` and zero tail |
| [`holo.core.keystream`](../src/holo/core/keystream.py) | AES-CTR-derived format domains, block assignment, scrambles, permutations, and color schedules |
| [`holo.core.bch`](../src/holo/core/bch.py) | Shortened BCH address-word encode/decode |
| [`holo.core.ldpc`](../src/holo/core/ldpc) | Frozen LDPC matrices, framing, CRC, encoding, and belief-propagation decoding |
| [`holo.core.fountain`](../src/holo/core/fountain.py) | Fountain-v2 page/block assignment, symbol generation, rank accounting, and solve |
| [`holo.core.channel`](../src/holo/core/channel.py) and [`color_tile`](../src/holo/core/color_tile.py) | CMY state definitions and CMY7/CMY8 tile framing/mapping |

The selected printer record and named payload profile select a `FormatSpec`
and redundancy policy. Scanner registry entries are not consulted by
generation. Descriptive device facts and profile names are not themselves
printed bits; the resolved geometry, coding, and seed are.

## 3. Generator

The generator composition root is
[`cmd_generate`](../src/holo/cli.py). Its data flow is:

```text
payload bytes
  -> resolve coding + printer geometry + source fraction
  -> plan canonical K, fountain reserve, and whole page count
  -> wrap payload and split into source-symbol streams
  -> fountain-encode every page ESI
  -> compose addressed 64×64 cell tiles
  -> expand cells to 600-dpi device dots
  -> emit one PostScript file per page
  -> atomically publish the volume directory
```

### 3.1 Selection and planning

[`devices.profiles.make_spec`](../src/holo/devices/profiles.py) combines a
coding with printer media and payload-safe margins. The resulting
`FormatSpec` is the single geometry and format identity used downstream.

[`gen.plan`](../src/holo/gen/plan.py) computes:

- canonical source-symbol count `K`;
- fountain block count and rank reserve;
- the smallest whole-page count satisfying both global fragment capacity and
  every block's worst retained-page quota; and
- the per-stream `N-K` repair-row count. For multistream color this is not a
  physical repair-tile class: one ESI can be systematic in one stream and
  repair in another.

A named profile is a convenience bundle selecting a coding and `q`. The
resolved coding is format-bearing; `q` changes the emitted redundancy and
page count. The receiver needs neither the profile label nor `q`.

### 3.2 Envelope and fountain layer

For B/W, [`gen.emit.source_packed_for`](../src/holo/gen/emit.py) wraps the
payload and packs one source matrix. For CMY7/CMY8,
[`format.streamset`](../src/holo/format/streamset.py) maps one envelope into
one common `K` and ordered stream-major matrices.

One [`fountain.VolumeCode`](../src/holo/core/fountain.py) per logical stream
encodes the tile counters for each page. A counter is both the physical tile
address and the fountain ESI.

### 3.3 Tile composition

The B/W leaf is [`gen.compose`](../src/holo/gen/compose.py). For each tile it:

1. derives the absolute counter;
2. emits its BCH word at the 100 site cells;
3. derives the counter-addressed metadata bit;
4. frames `[metadata bit | fountain symbol]` with CRC and LDPC;
5. shortens and permutes the transmitted slots;
6. applies the absolute-address payload scramble; and
7. places the result into the page cell field.

The color leaf is
[`gen.color_compose`](../src/holo/gen/color_compose.py). CMY7 carries one
compound stream. CMY8 carries independent C, M, and Y streams with a common
`K`. Both prepend the same per-counter metadata bit to every logical stream,
add 100 word sites and 20 dust sites, then map encoded stream data to
canonical CMY states.

### 3.4 Physical emission and publication

Cells are solid-expanded to device dots. [`gen.ps`](../src/holo/gen/ps.py)
emits either:

- one K `imagemask` for B/W; or
- one 1-bit/component `DeviceCMYK` image for color, with K exactly zero.

The exact dot placement, component ordering, and 600-dpi operation are
essential to the current print path. The `PSDoc` class is replaceable only by
a backend proven to emit the same device-dot samples and placement with
equivalently qualified paint-path semantics: K `imagemask` versus one
composite CMYK image.

[`gen.emit`](../src/holo/gen/emit.py) is the driver. It stages the complete
volume, refuses overwrite, then publishes it with one rename. These are
operational safety properties, not on-paper format fields.

Every page currently also receives packed ground truth (`*_gt.npy`) and the
volume receives `manifest.json`. Both are useful for qualification and print
bookkeeping, but neither is consumed by the receiver. They are logically
nonessential even though the current driver emits them unconditionally.

## 4. Receiver

The exact-row receiver is assembled by
[`production_pipeline`](../src/holo/receive/production.py):

```text
authenticated native capture
  -> direct-from-native scale lanes
  -> E021 survey
  -> E022 placement + BCH address
  -> E023b K or color evidence + LDPC/CRC
  -> atomic lane barrier
  -> metadata + fountain-v2 + envelope/SHA close
```

[`receive.runtime`](../src/holo/receive/runtime.py) owns execution and typed
stage seams. [`receive.production`](../src/holo/receive/production.py)
(survey/address stages + pipeline composition),
[`production_payload`](../src/holo/receive/production_payload.py) (the K
payload driver),
[`production_close`](../src/holo/receive/production_close.py) (the gated
fountain-close stage), and
[`production_color`](../src/holo/receive/production_color.py) (the color
payload driver) adapt the numerical leaves into those seams.

### 4.1 Ingest and format selection

[`receive.scan`](../src/holo/receive/scan.py) opens the original gray or RGB
capture, preserves its dtype and channels, requires true scanner DPI, and
binds it to the SHA-256 of the original acquisition. The source is checked
again before a durable barrier.

With an explicit coding, the CLI constructs one exact `FormatSpec`. Without
one, [`receive.discovery`](../src/holo/receive/discovery.py) maintains
isolated registered-format branches, uses a native survey to prune
incompatible cell families, and runs the unchanged exact pipeline in each
surviving branch. This receiver discovery is not the `holo discover`
characterization command.

### 4.2 Direct-native scale cascade

[`receive.cascade`](../src/holo/receive/cascade.py) creates an exact-rational
coarse-to-fine lane plan. Every view is derived independently from the
authenticated native raster; one resampled lane is never treated as a new
physical acquisition or used to derive another lane.

The scheduler resumes at the first uncommitted lane. Each lane attempts
survey, address, and payload in order. A refusal stops it at a typed causal
prefix, which is still committed as one atomic barrier. Only certificates and
bounded pose facts from a coarser lane influence the next lane numerically;
raw likelihood evidence remains lane-scoped.

### 4.3 Survey: where useful paper evidence exists

[`receive.survey`](../src/holo/receive/survey.py) is the E021 leaf. It uses a
physical-footing structure tensor, adaptive thresholding, connected regions,
pitch voting, boundary refinement, support topology, and angle hints. Its
output says where placement work is justified; it does not assign page or
tile addresses.

### 4.4 Placement and BCH address

[`receive.place`](../src/holo/receive/place.py),
[`receive.placement`](../src/holo/receive/placement), and
[`receive.words`](../src/holo/receive/words.py) implement E022. They combine:

- continuation hints from prior lanes;
- local and chained placement;
- complete cold page/rotation/pose hypotheses when required;
- held-out winner/rival validation;
- BCH decoding of the 100 word sites; and
- known-position word aggregation.

The durable result contains accepted poses, continuation proposals,
runner-up hypotheses, and BCH conflicts in native coordinates.
Contradictory decoded addresses quarantine the contributing placements before
payload promotion.

### 4.5 Payload evidence, LDPC, and certificates

For B/W, [`receive.payload`](../src/holo/receive/payload.py) samples placed
windows, calibrates detector scores, freezes one owner for each physical page
cell, and turns owner evidence into compact per-tile blocks (the private
photometric leaves live in
[`_payload_sampling`](../src/holo/receive/_payload_sampling.py) — window
crop/filter/sample/calibrate + pool-law label routing,
[`_payload_context`](../src/holo/receive/_payload_context.py) — the
per-region context arm, and
[`_payload_reuse`](../src/holo/receive/_payload_reuse.py) — refined-
generation reuse). [`receive.production_payload`]
(../src/holo/receive/production_payload.py) drives the K schedule.
A certified-field pose refinement may replay changed regions once;
unchanged windows are reused.

For color, [`receive.color_payload`](../src/holo/receive/color_payload.py)
uses aligned RGB plus word/dust labels to calibrate CMY state or component
evidence; [`receive.color_refine`](../src/holo/receive/color_refine.py)
carries the certified pose-refinement arm and its region-granularity
refined recompute (COLOR-INTEGRATION-DESIGN §5.5).
[`receive.production_color`](../src/holo/receive/production_color.py)
then attempts CMY7's compound stream or CMY8's independent C/M/Y streams.
The first-order path can start with one decoded 100-site word plus its 20 dust
sites. Certified payload projections from prior committed barriers may
strengthen later lanes, but same-lane attempts never train themselves.

In both paths:

1. wholly terminal regions and owners are pruned inside the payload leaf,
   after survey and placement; mixed regions retain donor patches;
2. each physical acquisition is attempted independently;
3. independent captures at the same lane may be combined;
4. correlated scale views are never summed as independent evidence;
5. the ordinary LDPC pass runs at most 60 BP iterations;
6. a selective, provenance-distinct retry runs at most 150; and
7. a tile certificate exists only after syndrome and CRC success.

Compact evidence blocks, certificates, and quarantine are persisted
receiver-state records, not diagnostic detail; attempt and divergence
records are invocation-transient and fold to durable `SessionCounters` at
commit (they are never persisted). Divergence is an
observational, non-gating audit; quarantine actively controls promotion from
addressing into payload work.

The scale cascade, lower-lane hints, context calibration, certified
refinement, same-lane multi-capture unions, and BP150 do not define printed
bits. They nevertheless affect which certificates can be produced from a
given scan and are mandatory parts of the current numerical receiver policy.
Omitting one would reduce yield and change the policy identity; none is an
optional CLI switch.

### 4.6 State, barriers, and close

[`receive.session`](../src/holo/receive/session.py),
[`session_model`](../src/holo/receive/session_model.py),
[`state_codec`](../src/holo/receive/state_codec.py), and
[`session_validation`](../src/holo/receive/session_validation.py) implement
the
append-only session ledger, content-addressed evidence blobs, incremental
barrier validation, atomic save, and — on load — structural validation plus
close reproduction from the certified frontier (never a causal barrier
replay; the former `session_replay.py` is deleted — the kiss-5 ruling made
load structural, and the surviving pure checks live in
`session_validation.py` and `_runtime_validation.py`).

Persistence is not a mathematical requirement for a one-shot decoder, but it
is essential to the current promises of safe resume and legal multi-capture
combination.

[`receive.fountain_close`](../src/holo/receive/fountain_close.py) decodes the
metadata equations to version and `K`, constructs the per-stream/per-block
fountain decoders, solves the source rows, and unwraps the canonical envelope;
[`receive.production_close`](../src/holo/receive/production_close.py) is the
runtime close stage around it (the v0.33 close-attempt gate + the v0.36
conversion memo).
Payload bytes are returned only if SHA-256, canonical `K`, and zero padding
all verify. Conflicting certified evidence or a failed digest is terminal
integrity failure.

`--complete` changes only close scheduling: barriers skip intermediate
fountain work and one close runs after all requested captures and lanes.

## 5. Nonessential and supporting pieces

These components do not determine printed cells or authoritative recovered
bytes for an exact-format run:

- **Generator conveniences:** CLI presentation; `registry` and `capacity`
  command formatting; human-readable profile/evidence labels after coding
  and `q` are resolved; content-addressed output naming; DSC job title/ID;
  console/sidecar PS and ground-truth bookkeeping digests; ground-truth
  arrays; and the sidecar manifest. The planner/registries, in-band envelope
  SHA, and receiver's internally computed acquisition SHA are not optional.
- **Receiver diagnostics:** [`receive.diag`](../src/holo/receive/diag),
  [`_diagnostic_snapshots`](../src/holo/receive/_diagnostic_snapshots.py),
  [`_production_diagnostics`](../src/holo/receive/_production_diagnostics.py),
  [`close_progress`](../src/holo/receive/close_progress.py), JSONL, live
  HTML/HTTP, PNG/SVG panes, timing, and final reports. They are
  failure-isolated observers and return no values to numerical stages. The
  hooks are currently woven into production modules, and
  [`observer.py`](../src/holo/receive/observer.py) also owns production
  qualification status/warnings, so semantic optionality does not imply that
  these files can simply be deleted.
- **CLI wrapper:** a library caller may replace it. Automatic format
  discovery is bypassed only when the exact `FormatSpec` is supplied; it is
  operational authority for the default blind-decode path, not detachable
  presentation.
- **Standalone characterization:** [`holo.characterize`](../src/holo/characterize)
  (`holo discover`) measures print/scan paths but neither generates payload
  sheets nor decodes them.
- **Qualification tools:** [`holo.qualification`](../src/holo/qualification),
  [`receive.qualification`](../src/holo/receive/qualification), synthetic
  distortion, scrap generation, and Ghostscript checks exercise the
  production code but are outside it.
- **Legacy and evidence:** `src/paperholo`, `experiments`, and differential
  oracles are outside Holo-v1 execution. `paperholo` remains the reader for
  older formats and a qualification oracle; `experiments` remain the
  physical/numerical evidence record.
- **Maintenance and operations:** tests, golden vectors, docs, print/scan
  scripts, scrap packers, and LDPC-regeneration utilities are non-runtime.
  The generated frozen LDPC JSON tables are format-bearing; the utility that
  regenerates them is not.

Color modules are nonessential only to a deliberately B/W-only build. They
are essential for CMY7/CMY8. Likewise, PostScript is replaceable as a backend,
but an exact physical renderer is not; and persistent transport is avoidable
for one-shot decoding, but the state invariants are not avoidable for the
current resumable receiver.
