# core — DESIGN

The algorithm-free machine: facts, storage, commit, identity, the work
protocol. core knows no printed format, no pixels and no solver, and it
imports nothing but stdlib and numpy. Everything here is mechanism;
every domain meaning is declared into it by the package that owns it.

Constitution: `holo2/docs/DESIGN.md` (laws L1–L15, glossary). Working
rules: `holo2/docs/ENGINEERING.md`. Public surface + rationale: the
`__init__.py` docstring.

## Purpose

One sentence per duty:

- **name** a durable fact (`ResourceKey`, the typed ids, `BlobRef`);
- **store** it without knowing its shape (`registry`, `codec`, `store`,
  `blobs`);
- **commit** it — the single serial point, transactional, versioned
  (`commit`);
- **bind** what a computation read, so it is attempted at most once
  (`identity`, `resources`);
- **offer** the protocol a provider and a worker implement (`work`,
  `view`);
- **record** the ordering an observer needs to replay a run (`trace`).

## Public surface

`holo2.core.__all__`, pinned by `holo2/tests/test_surfaces.py`; the
error taxonomy is part of it (`holo2/tests/test_error_taxonomy.py`),
pared by B4 to the seven types another package actually catches — the
law derives DECLARED from `__all__`, so the eight core raises and
handles alone (`BlobError`, `CodecError`, `DuplicateWrite`,
`SilentStage`, `SpendConflict`, `StoreError`, `TerminalSessionError`,
`UnknownRecordError`) rejoin with their first cross-package handler.
Cross-package code imports from `holo2.core`, never from a submodule
(`holo2/tests/test_layering.py`). core depends on nothing: it is the
root of the DAG, and that is the whole reason it can be reviewed and
replaced alone.

## Owned record families (R3)

core owns the *mechanism* and exactly two families of its own.

| family | kind | version | invariant |
|---|---|---|---|
| `SubjectSpec` | `subject` | 1 | a provider-minted work subject (M3); opaque to core beyond its family and its collection. Declares NO references (F-07's relational half): its parent is an opaque provider string, not a key. F-08 (2026-08-13): FROZEN under its id (`_subject_transition`) — work identities and spends stand on it, and a different subject is a different id. F-07 (same day): the id IS the key (`require_own_key`), so a subject filed under another's name — which would re-aim every descriptor and spend that resolves it — is refused at the wall and at load |
| `CloseRecord` | `close` | 1 | terminality. `OPEN` is replaceable; `VERIFIED`/`INTEGRITY_FAILURE`/`UNSUPPORTED` are immutable and freeze every later commit — for whatever close the fold ADMITS into the live table (2026-08-22, OR-13: a SKIPPED or SUPERSEDED close never reaches it; see "What the fold admits of a CLOSE" below, and note that the record itself is neither rewritten nor deleted by either rule). Declares NO family transition on purpose (F-08): its law IS the commit wall's terminality check, one wall, stated once. No key check either (F-07): the session's close is the singleton `CLOSE_KEY` and has no parts to disagree about. No references either: it names a payload by CONTENT ADDRESS — bulk, which the wall checks separately — and no keyed record. Its writers are the close consult and — since F-11 — the orchestrator's integrity path, which is why the record is core's rather than solve's |

Every other family belongs to the package that WRITES it —
`capture.RECORD_FAMILIES`, `solve.record_families()`,
`engine.RECORD_FAMILIES` — and the composition root builds one registry
(`core.compose`).

**Deviation, declared** (R3): `CloseRecord` is written by the close
provider in `solve`, so writer-ownership would put it there. It lives
here because the *law* is core's — a terminal close freezes the session
— and neither core nor engine may import solve. The clean fix is an
integrity hook that lets a package register a freeze rule with its
family; that is review-round work, not a locality question.

### The registry and its manifest — the whole migration policy

A `RecordFamily` carries: `kind`, `version`, `validate` (structural,
run on every proposed write AND on every record read back), `transition`
(the rule between the record standing at a key and the one proposed for
it), `collections` (membership resources a fact joins, M4), and
`structural` (does a write of this family expand the work frontier?).

The registry's **manifest** — every family name and version, sorted —
is the store's schema identity. A state whose manifest is not the
build's is refused at open, naming the families that moved. That is
DESIGN §"deliberately absent" made local: a subsystem changes its own
record and bumps its own version; no other package's code moves, and
there is no migration decoder anywhere.

Two laws that used to be core's by name and are now family data:
the tile map's "CERTIFIED is terminal, certified content never changes"
(a `transition`), and "a pose's page is in the declared domain" (a
`validate` closed over the session's page domain at composition time).

## The laws core enforces, and where

| law | where |
|---|---|
| **L5** certificate conflict is terminal, never voted | `commit` → `registry.check_transition` → the tile family's own transition (which lives in `solve`). core owns the wall and the `CertificateConflict` type; `solve` owns the rule; `engine` owns the terminal FACT it becomes (F-11) — it is the one refusal at this wall that lawful code produces, so it is DATA rather than a defect, and the run records `CloseRecord(integrity_failure)` and stops instead of raising |
| **L7** current evidence may not narrow a domain | structural: a worker cannot write, so it cannot shrink its own frontier; only `WorkResult` facts reach the store |
| **L10** batching invariance | `commit` bumps a version **iff content changed**; a no-op commit burns no sequence number; cost accounting may be order-dependent, facts may not |
| **L11** per-item determinism | `work` forbids clocks/RNG in the library (`holo2/tests/test_conventions.py`); the trace's sampled digests are the honesty canary |
| **L12** observer boundary | `trace` is append-only, disposable and read by nobody in the receiver path |
| **L13** validation at trust boundaries only | walls at commit atomicity (spend ⇔ outcome), blob presence, registry structural validation; everything else is types + tests |
| **L15** status honesty | `CloseRecord` statuses are the only verdicts; `OPEN` is not a failure |

## The mechanism, stated once

**Read-sets are attempt identity.** A worker declares the exact keyed
inputs it consumes; `AttemptIdentity = tuple of (key, version-at-read)`.
A `(worker, route, identity)` is attempted at most once, and the spend
becomes durable iff its outcome does. The idle test is an integer
compare — no hashing. Versions are issued by the commit authority and
are durable, so identities survive resume and trace replay.

**A work id is a structure** (the identity law, 2026-08-11). `WorkId` is
`(family, subject key, route, scope)` — values, not a rendered string —
so the ledger's rows, the subscription index's keys and the ready
queue's heap entries are all keyed by something injective BY
CONSTRUCTION. That closes HARDENING-SYSTEMIC-REVIEW P1 (the old id
dropped the subject's KIND and joined parts with an unescaped `/`, so
two different subjects could alias one durable spend);
`tests/core/test_identity_law.py` carries the review's own collision
pairs. `str(WorkId)` is the display rendering, and nothing parses it.

**A record key is DECLARED, not hand-built** (2026-08-12). The two
structural rules that make key embedding injective — fixed arity per
kind, variable-length components last — are executable: a kind declares
its shape as a `KeySpec` of `KeyField`/`KeyEmbed` slots, and
`build_key`/`parse_key` walk it. The kind-and-arity guard four of solve's
builders each spelled out by hand now lives once, next to the rules it
enforces; the named per-kind wrappers stay in the owning package, where
the reasoning for each key's shape belongs. Slot ORDER is the spec's own
data, because the kinds genuinely disagree about where an embedded id
sits (a window's is in the middle, an evidence key's at the end, a pose's
and a hint's at the start). Gate: every existing key spelling renders
byte-identically through the declarative path
(`tests/solve/test_key_injectivity.py`).

**The ledger folds to the latest** (D1, ruled and landed 2026-08-10). It
holds ONE row per `(worker, route)`: the newest identity spent, its
outcome, and how many attempts the pair has made. Spend-once is
unchanged in effect — versions are monotone and issued by the commit
authority, so an identity the fold dropped can never be proposed again —
and the ledger checks that premise instead of assuming it: a proposed
identity must read every key at or above the version the held one did
(a key absent from a read-set counting as `ABSENT_VERSION`, exactly as
`attempt_identity` reads a key the store does not hold) and must advance
at least one. A worker whose read-set SHRINKS therefore refuses loudly
instead of re-arming forever on an identity nothing remembers. No
digests anywhere: versions remain the identity mechanism. The envelope's
spend section is O(live workers), not O(attempts), and its persisted
shape is `schema_version` 3 — an older state refuses at open (pre-freeze
rule, no migration decoders).

**Wakes.** A commit's changed-key set joins the subscriber index. A
*changed key* includes a derived collection whose membership grew (M4),
which is how a brand-new fact wakes a worker that could not have named
its id (review F-03, smallest form).

**Staleness is waste, never error.** A proposal commits only if the
read-set RE-DERIVED still yields the identity it holds; a read-set is a
query, and a commit can add a key to it without touching anything the
worker named.

**A declared JOIN replaces compare-and-swap where the algebra is one**
(H4 W2's first concurrency ruling, 2026-08-16). `RecordFamily` gained a
FOURTH hook beside validate/transition/references: `merge(key, current,
proposed) -> merged`. Where a family declares it, `commit.apply` settles
those writes against the record the store CURRENTLY holds — an atomic
fetch-and-union inside the serial section it already had, microseconds of
set work, no lock anywhere near a worker — before anything is adjudicated
or identified. Three consequences the tests pin:

- **the proposal IS the operation input.** For a join semilattice that is
  the definition, not a shortcut: a fire's carry is already `snapshot ⊔
  gain`, and `current ⊔ proposal` is the same value from any snapshot
  because ⊔ is idempotent, commutative and associative and a snapshot
  always sits below what stands. Nothing extra crosses the wall;
- **the POST-MERGE batch is what is identified and journaled** — state
  transfer, so a replay re-applies the recorded result verbatim instead
  of re-deriving a join against a store it has moved past. With no race
  the merged record IS the proposed one, so a serial run's batch ids do
  not move at all;
- **the staleness test stops asking about that key.**
  `CommitEngine.is_current` projects merge-declared kinds out of both
  sides. The DURABLE spend identity is untouched — what a worker read is
  what it spent — so only the admit-or-discard decision moves.

The hooks COMPOSE in one direction: merge first, then the family's
ordinary validator and transition, on the MERGED record — which turns a
declared transition into the join's post-condition. A contradiction the
join cannot resolve is the OWNER's exception, passed through unwrapped
(the tile map's `CertificateConflict` has to reach F-11's terminal-fact
path, not the crash path). One family declares it today: the tile map
(`solve/DESIGN.md`, "the tree's ONE commutative family").

**Blobs are staged, not appended.** Since R1 a worker returns
`WorkResult.blobs`; the commit authority materialises the accepted ones
and refuses a batch that references bulk it does not hold — resolved
against staged + stored while the delta is still being derived, so a
batch naming bulk nobody carried refuses without touching the sidecar. A
discarded proposal leaves no orphan.

**Publication is one act** (the publication-order law, root DESIGN §6,
2026-08-11). `commit.apply` derives and validates the COMPLETE delta
before anything moves: writes adjudicated against their families'
**key-aware** validators and transition rules, the collection membership
those writes grow (that derivation runs the owning package's callback and
can refuse, so it happens here), spends pre-checked, bulk references
resolved. Then the resource table publishes, and the store publishes from
the same delta. Nothing fallible runs afterwards. Two consequences: a
refused batch leaves nothing durable AND nothing moved in memory, and the
store's one remaining failure — the snapshot, which is durability rather
than semantics — cannot leave the table disagreeing with it, because the
table went first (F-18). `holo2/tests/core/test_publication.py` carries
the review's own probe and a restart at every failure point.

**Persistence is journal-authoritative** (F-16, built 2026-08-13).
`state = fold(inputs, code, ordering)`, so nothing in a state directory
is authoritative — the tree's own laws (per-item determinism, L12's
no-clocks, seeded draws, value-bound policy, batch-id-verified replay)
already pay for re-deriving it, and the archive is the paper. The
directory is therefore two files with two different jobs:

- **`journal`** — the fold's STARTING POINT (schema version, family
  manifest, session identity by value) on line 1, then ONE ENTRY PER
  COMMIT AND PER DISPATCH, appended and fsynced where it happened. 65
  bytes a commit; **measured 217 KB for a real 3,408-commit sheet**, and
  0.053 ms of fsync per commit (0.2 s over that sheet). It is the
  durable record. **H4 W2 added the second entry shape** (schema 7): a
  payload-free START MARKER, `>` plus the dispatched work's identity,
  whose POSITION is the snapshot prefix the fire it names read. Commit
  order alone cannot say what a pooled fire saw — it was launched at one
  position and lands, possibly, many commits later — so recording the
  dispatch is what makes pooled `--replay` and pooled crash recovery
  exact. Markers FOLD TO NOTHING (ordering, not facts: the no-no-op-facts
  ruling is untouched), and they roughly double the entry count of a run
  whose passes mostly commit. **Line 1 is READABLE ON ITS OWN** since C5
  (2026-08-22, RULINGS G6): `journal.read_starting_point` reads that line
  and nothing else, and `Store.peek_identity` runs the open path's own
  gate over it, so a caller can ask what a state IS without opening it —
  which is what lets an operator resume without retyping the identity the
  state already holds. No lock, and that is a property of the file: line
  1 is written once at create and only ever appended past, so a live
  writer cannot tear it, where an exclusive lock would make a read-only
  question refuse exactly while a decode is running.
  **SEAM SIGNAL, DECLARED HERE rather than met as a red test:
  `store.py` now stands at 1000 lines EXACTLY** — the cap
  `holo2/tests/test_conventions.py::test_file_length_cap` enforces —
  because `Store.peek_identity` landed in it (C5). The next editor of
  that file is blocked before writing a line, so the split is owed
  BEFORE the next edit rather than forced as its side effect. The seam
  that presents itself is THE STARTING POINT: `starting_point`,
  `_require_starting_point`, `_require_manifest` and
  `_STARTING_POINT_FIELDS` (~100 lines) into `core/starting_point.py`.
  It takes `StoreError`'s home with it — every one of those functions
  raises it, and `holo2/tests/core/test_store.py` imports that name from
  `holo2.core.store` — so where the class lives is decided in the same
  diff. Line 1's FILE half already sits in `journal.py` for this same
  reason; this is the rest of one seam, not a second one.
- **`cache`** — the fold's MEMO: append-only length-prefixed delta
  frames, one per `snapshot_every` commits **taken where no dispatch is
  outstanding** (H4 W2: a frame is a RESUME POINT, and a resume point
  has to be a clean cut through the dispatches, or a pass's marker sits
  behind the boundary while its commit sits ahead of it) and one at
  close, each carrying the journal position it covers, newly interned
  keys, the records and spend rows that moved since the last frame.
  Whole-file rewrite is ABOLISHED. **Measured 20.1 MB where the envelope was 476
  MB** on the same sheet, with a median frame append of 28 ms (max 801
  ms) against the 4.7 s the envelope rewrite cost, and a 2.8 s load
  against 9.9 s.

Three rulings inside that shape:

1. **Subscriptions are DERIVED, not stored.** A fired worker's read-set
   IS its spend row's identity keys — one read of one worker's keys
   becomes both, in one commit — and the duplicate was 143 MB of the old
   envelope. Verified before it was built: on a real sheet, 2,251 spend
   rows, 2,251 subscriptions, identical worker sets, identical key sets,
   zero differences. The ONE writer that does not pair them — a
   re-offerable decline parks a descriptor on wake keys without
   attempting anything — rides each frame as an override row (`null`
   when the ledger explains the read-set, which is every row on the
   measured sheet).
2. **The load path validates nothing it reads** (rider r1). Open is a
   GATE — schema version, family manifest, session identity by value,
   and cache position ≤ journal length — and past it the memo is
   trusted. A disposable cache has exactly two honest states, trusted or
   re-folded; per-record re-validation at load was the store guarding
   against itself, and it is deleted (F-08's at-load halves with it).
   The wall is the unique point where unlawfulness is catchable; replay
   is what proves faithfulness. The one surviving open-path check is
   F-13's residue, which is a statement about the SIDECAR beside the
   cache, not about the memo.
3. **Interning ids are FILE-LOCAL WIRE ENCODING, never identity.** The
   cache numbers keys in first-use order to stop writing a 200-byte key
   once per spend row; the key PARTS are carried in full, once, and the
   values stay the identity (the hash-free identity law). Nothing
   outside `cache.py` may hold, store or compare an intern id.

**Freshness, not migration, for the identity a state names** (C2,
2026-08-22, RULINGS G1). Line 1's session identity carries
`format_row_id`, and since that ruling a LEGACY printed format is
spelled `L:c2-r0700@3392x2368` everywhere holo2 writes it — the row id,
the persisted identity, the placement policy id that embeds row ids.
A state directory written before that date holds the bare spelling and
**refuses at identity on resume**: open is a gate that compares the
session identity BY VALUE, and a bare legacy id is a value this build no
longer produces. That is deliberate and is the cheaper half of the same
argument the rest of this section makes — nothing in a state directory
is authoritative, the archive is the paper, and every holo2 state is
re-earnable by re-running the fold. The alternative was accepting two
spellings of every printed sheet for ever, which is exactly the
"one format, two seeds" hazard the legacy catalogue exists to make
unrepresentable. No `SCHEMA_VERSION` bump: the schema did not change,
one of its VALUES did.

A crash leaves the journal ahead of the cache. That tail is RE-EARNED by
replay (`engine/DESIGN.md`, "Crash recovery IS replay"), which makes
crash recovery and the `--replay` audit one code path — F-24, closed
inside this build.

**What the fold admits of a CLOSE** (`store._fold_close`, ruled
2026-08-22 — the user's `--no-close` ruling plus the lead's one added
rule). The journal is never rewritten and no record is ever deleted;
these are statements about the LIVE TABLE the fold produces, and the
frames keep saying exactly what they always said.

1. **A close is terminal only while it is the LAST WORD.** A `CLOSE_KEY`
   write with COMMITS RECORDED AFTER IT is a SUPERSEDED close: the fold
   drops it under every policy, the session is OPEN, and the next closing
   run recomputes it from the certificates it holds and APPENDS a new
   `CloseRecord`. This is what keeps the commit wall's first rule true as
   written rather than merely mostly-true: a terminal close is immutable,
   and nothing ever committed after a close that was still terminal.
   Mechanism: a cache frame carries the commit it covers, and the last
   frame naming `CLOSE_KEY` is therefore an upper bound on the commit
   that wrote it — the direction the rule needs.
2. **`skip_close` is the read-time half of `--no-close`.** Opened with
   it, the fold takes no `CLOSE_KEY` record at all, so the store is not
   terminal and the wall admits commits. Core carries no policy: it
   carries what the fold admits, and the engine decides when to ask
   (`engine/DESIGN.md`, the close-policy axis). The old close stays in
   the frames and in the journal, so an ordinary open afterwards reads it
   again — superseded, if the skipping run committed anything.
3. **An `integrity_failure` close is neither skipped nor superseded.**
   Every other terminal status is a pure derivation from the certificate
   set, so dropping it loses nothing a later close cannot recompute. A
   conflict's record is not: the contradicting write was refused AT THE
   WALL and never became durable, so the record's `reason` is the only
   surviving trace of the event (F-11). `skip_close` refuses it by name
   with the remedy; supersession cannot reach it at all, since the wall
   refused every commit after it — stated anyway, so the next reader does
   not have to re-derive it.

## Measured facts core relies on

All from `holo2/docs/MEASUREMENTS.md` (H3 bench, toy workers — the
invariance results transfer, the ratios do not):

- **the transaction is cheap, the snapshot was not** (M-3.4): adjudicate
  + apply + trace = 0.29–0.69 s for ~2,120 commits (≈0.14 ms/commit);
  one snapshot of the 8.05 MB envelope costs 128–279 ms and is paid in
  full however little changed. Per-commit cadence is 57x the close-only
  wall. fsync is ~5 ms/snapshot — durability is nearly free; the
  *whole-envelope rewrite* was the cost, and F-16 deleted it (delta
  frames: 28 ms median at real-sheet scale, where the rewrite was 4.7 s).
- **replay is exact** (M-3.1): a threaded run replays serially into a
  byte-identical envelope — records, per-key versions, spend ledger,
  subscriptions and `commit_seq`. It cost 2.51x the free run's wall,
  which is what a serial debug instrument costs.
- **the serial floor is the arm step, not the commit** (M-3.3):
  transaction time *falls* with more workers; `read_keys` + identity
  binding + staleness re-derivation is the Amdahl term.
- **cadence changes no answer** (M-3.4): certificates, payload and
  counters identical across all seven cadences — L10 measured.

## TO-FIX — core's ledger

Known defects and the one ruling core owes. **D-n** = the founding-design
deviations (coordinator's audit 2026-08-10); **F-nn** = the adversarial
review (`holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md`) with its severity
scale. The root ledger (`holo2/docs/DESIGN.md` §15) indexes what crosses
packages. Adjudication is H3.5's milestone, not R4's.

| id | defect | where | sev |
|---|---|---|---|
| D1 | **CLOSED** (WP-1, 2026-08-10): `_by_route` holds one `SpendRecord` per `(worker, route)` — latest identity, outcome, `attempts` — with a read-set-shrink guard proving the monotonicity the fold rests on; `schema_version` 2→3, old states refuse at open. Was: EVERY spent identity retained as full `(key, version)` tuples | `identity.py` `SpendLedger` | BLOCKER (scale) |
| D2 | **CLOSED with D1** — a pointer, not a second defect. The close consult's identity has been O(1) since R1/M11 (read-set = `collection:certified`); its retained rows WERE D1's missing fold, and the fold removed them with no close-side edit | see D1; `solve/close.py` unchanged | BLOCKER (scale) |
| D3 | **CLOSED with F-16** (2026-08-13): the premise is gone rather than repaired — nothing is rewritten, so "cheap to snapshot" is now "cheap to append what moved". D1+D2 closed the spend half; the delta-frame cache closed the rest | `store.py` `_frame`; `cache.py` | CLOSED |
| D4 | **= F-07** (record↔key identity), with F-08 for the transition half. Tracked there, and CLOSED with F-07's relational half (2026-08-13); kept here only so the audit's D-numbering still resolves | see F-07, F-08 | CLOSED |
| — | **CLOSED** (WP-1): three copies of the "every `BlobRef` reachable from a record" walk — commit's bulk-present wall, the store's load-time check, the provider contract battery — of which the store's lacked commit's dataclass-TYPE guard. One published `records.blob_refs`, all three sites import it | `records.py` `blob_refs` | LOW |
| F-16 | **CLOSED / BUILT** (2026-08-13): journal-authoritative persistence — `journal.py` (starting point + one fsynced batch id per commit) and `cache.py` (append-only delta frames, interned keys, derived subscriptions), `SCHEMA_VERSION` 6, a pre-F-16 `state.json` directory refusing by name. Measured on a real 3,408-commit sheet: journal 217 KB (65.3 B/commit, 0.053 ms fsync each); cache 20.1 MB against the envelope's 476 MB; frame append 28 ms median / 801 ms max against a 4.7 s rewrite; load 2.8 s against 9.9 s. Riders: r1 (at-load validation deleted, open is a gate) and r2 (F-24 subsumed — crash recovery IS replay) landed with it; r3's storage-shape half of F-20 is the append-only cache itself. Was: every snapshot rewrote all facts, all spends and all subscriptions, however little changed | `journal.py`, `cache.py`, `store.py`; `tests/core/test_{journal,store}.py`, `holo2/measure/verdicts/test_durability.py` | CLOSED |
| F-07 | **CLOSED, both halves** (2026-08-13). *Identity half* (with F-11): a family's `validate` is key-aware — `validate(key, record)`, run at the commit wall and at load — which closed HARDENING-SYSTEMIC-REVIEW P0-1. NINE adopters, every family that can prove its own name; the check is published ONCE as `core.records.require_own_key`; the two that decline say why (`TileRecord` carries no component of its work key, `CloseRecord` is the keyless singleton) and a hint proves the source half of the two its key names. Battery: `tests/core/test_key_identity.py`. *Relational half* (queue item 3, D3r): `RecordFamily.references` — a pure per-family declaration of the record keys a record STANDS ON, resolved by the wall's adjudication pass against DECIDED BATCH ∪ STORE. It cannot ride `validate`, whose contract forbids reading other records; and one check is complete for all time, because facts are immutable and never deleted, so a reference that resolves at commit can never dangle later. A miss is an ordinary `CommitRefusal` naming referrer and reference — a WRONG WRITER, fatal by F-11's other half, never a `CertificateConflict` and never the terminal-fact path. SIX declaring families: certificate → minting pose + every contributor (only when CERTIFIED), evidence → pose + calibration, pose → window, window → region, region → capture, calibration → scope. Abstentions are RULINGS, each pinned with its reason by the meta-test: capture (root fact, L1), hint (its window is the ADDRESSEE — on the live path the anchor's seed hint commits BEFORE any window record exists), pool (no writer yet, B8), subject (opaque string parent), close (bulk, checked separately), session identity (keyless). Cost: O(refs) dict/store lookups per write on the serial path; suite wall unmoved. Batteries: `tests/core/test_references.py` (refusal naming both keys, batch inclusion, store-satisfies, union contributors, meta-test) + `tests/solve/test_record_references.py`; the real-sheet e2e is what proves the declarations match the real path | `registry.RecordFamily.references`, `commit._require_references`; declarations in `solve/records.py`, `capture/records.py` | CLOSED |
| F-08 | **CLOSED (H3.5 integrity cluster, 2026-08-13).** Every family now declares its transition law at the wall, or says in writing why it has none: tile monotone + frozen certified content (L5, unchanged); capture frozen WHOLE (the Q2 dpi refusal keeps its named message; shape/dtype/channels/footings are deterministic over the bytes, so a differing re-ingest = the derivation moved, refuse); region survey content frozen (B9's fresh-survey-wins is an EQUAL rewrite, a no-op by construction); evidence and calibration frozen (a certificate's provenance stands on them; H5's re-score semantics arrive as a DECLARED amendment or not at all); window's live statuses move freely and RETIRED is terminal with an immutable reason (+ the reason⇔RETIRED sum-state check at construction); pools grow-only (§6.2's law, now enforced); subject frozen (work identities stand on it, M3). DECLARED non-rules, pinned by test: hint (trust tier 1, fresher predictions overwrite BY DESIGN), pose (every field is identity — overwrite-in-place is unrepresentable since the identity law), close (the terminal-session wall IS its law, one wall stated once). No wire shape moved, no version bumps: the wall stopped accepting writes nothing legal makes. Batteries: `tests/{core,capture,solve}/test_*transitions.py`; real-sheet echo unchanged. The identity law had already narrowed the hole to non-key-named content; this closed what was left | `registry.check_transition`; transitions in `solve/records.py`, `capture/records.py`, `core/records.py` | CLOSED |
| F-02 | the bind/execute split is not built: binding on the scheduler thread producing immutable inputs. R1 closed the interface half (`SolveView`, staged blobs) | `work.py`, `view.py` | BLOCKER |
| F-11 | **CLOSED** (2026-08-13, H3.5 queue item 1): a `CertificateConflict` is a DATA integrity event lawful code can produce — a ~2^-32 CRC false accept, or a scissors session that mixed two physical sheets — so it alone among `CommitRefusal`s is CAUGHT (`engine.Orchestrator._integrity_failure`, at the one place all three run paths commit) and becomes one lawful terminal write: `CloseRecord(integrity_failure)` carrying the conflict's own message, which already names the key and what differed. Shape is B13's as executed — deliver what is deliverable, then terminal; mid-run nothing is deliverable, so the fact IS the delivery. Resume needed no code (a terminal close freezes the session at this wall), and the report rides the close dict the snapshot already publishes. The review's "both provenance digests" is deliberately NOT taken: the hash-free identity law says a certificate's provenance is the values its record and key already carry. Every other refusal stays fatal — the crash is the feature (F-08 dialogue), pinned by the `StateRegression` half of the battery | `commit.py` `CertificateConflict`; `engine/orchestrator.py`; `tests/engine/test_orchestrator.py` | CLOSED |
| F-13 | **CLOSED (2026-08-13, final form after user ruling)**: the sidecar is cache (re-scope stands). Built: honest refusal messages (missing address names itself + INCOMPLETE-not-corrupt + remedy; the open path names the citing record); the operator-handoff rule — verify=True at the ONE materialisation both live and resumed paths share (orchestrator, WP-4's site), and the `CloseRecord` construction invariant payload_sha256 == bytes_ref.sha256 (one payload, two names, must agree — commit AND load), which makes the runtime re-check UNREPRESENTABLE-redundant; the interim cli `_recheck_resumed_payload` machinery was built and then DELETED same day per the ruling (comparison beyond the verified read = guarding our own store). Declined with measurement: verify-on-read at `certified_symbols` — sha over 1,357 symbols = 2.5–3.8 ms = 1.12–1.68% of the site's 218–225 ms across three runs, above the pre-registered <1% bar; secondary: a corrupt symbol yields a mis-diagnosis, never a wrong VERIFIED (envelope sha). All other consumers feed transient compute — nothing added | `blobs.py`; `store.py` open; `core/records.py` CloseRecord | CLOSED |
| F-18 | **CLOSED** (publication-order round), structurally and with no rollback machinery: the whole delta is validated first, then the table publishes, then the store — so when the snapshot fails both halves have already moved together and the durable state is the previous commit. Was: store applied + snapshotted, and only then did a fallible collection callback move the table | `commit.apply`; `tests/core/test_publication.py` | HIGH |
| F-19 | no single-writer lock on the state directory; two processes can append at the same blob offset and replace each other's envelope | `store.create/open/open_or_create` | HIGH |
| F-20 | the monolithic sidecar remaps on growth and retains every historical mapping, so read/append/read is quadratic in virtual extent | `blobs.py` `_stale_maps` / `_remap` | HIGH |
| F-22.3 | the no-silent-stages contract is a bound, not a live signal: `ProgressSink` counts quanta privately and publishes at fire end (= D5b; the surface half is `diag`'s, the debt `engine`'s). WP-1 collapsed the retained per-quantum records into the two counters anything read — the live CHANNEL is still unbuilt | `work.py` `ProgressSink` | HIGH |
| S1 | CLOSED (WP-2) — format renamed its class `CertifiedSymbolConflict`; the one name now means one thing (`core.CertificateConflict` = same-key content conflict at the commit wall) | `commit.py:80`, `format/fountain_close.py:54` (WP-1.0 review fix: was `:66` pre-split) | HIGH |
| F-24 | **CLOSED with F-16** (2026-08-13): the fsynced ordering journal is authoritative past the cache's edge, and auditing a state dir IS re-folding it and comparing batch ids. The D5a observation became the designed behaviour — cache ≤ journal, tail re-earned by the SAME orchestrator loop `--replay` uses, gated by `holo2/measure/verdicts/test_durability.py` | `journal.ReplayCursor`; `engine/orchestrator._recover` | CLOSED |
| F-26 | core's RESIDUE: a damaged sidecar is created rather than reported, and `Write(content_changed=True)` can force a bump for equal content (test-only). Clause 1 is **CLOSED** (WP-1): `parse_json_bytes` refuses duplicate object keys and `NaN`/`Infinity`, matching what `canonical_json_bytes` refuses on write | `blobs.py`, `commit.py` | MEDIUM |
| OR-6 | ruling owed: snapshot cadence, fsync defaults, trace retention. MEASUREMENTS proposes 512 + fsync and records that cadence alone cannot reach the <5% target. The cadence is now the single name `store.DEFAULT_SNAPSHOT_EVERY` (= 1), so the ruling is a one-line edit rather than five signatures a sixth caller can miss | `store.py`, `cli.py` | — |
| F-01 | **CLOSED** (R1 providers; the orchestrator branches on no family name). The residue was ruled 2026-08-12 (worklist B14/Q1, "VERY in-tree only"): provider genericity is a COMPLEXITY BOUND — narrow interfaces, uniform observable behaviour, each family independently reasoned about and debugged — and third-party providers are NOT promised, so slack serving only that case is deleted. Both `runtime_checkable` protocols survive on in-tree readers alone (the orchestrator's worker-or-decline `isinstance`, the provider contract battery) | `work.py` `Provider` | BLOCKER |
| F-03 | **closed in smallest form** (R1/M4: count-versioned collection keys, so a member whose id did not exist still wakes a sleeper) | `resources.py`, `registry.py` | BLOCKER |

**D1 was RULED and is LANDED** (audit 2026-08-10; WP-1 the same day):
fold to the latest identity per `(worker, route)`, plus counters. **No
digests** — a digest-based compaction was proposed and explicitly
retracted; versions stay the identity mechanism. The storage engine was
then re-measured (M-3.4) and F-16 was reopened on that measurement and
BUILT (2026-08-13): delta frames landed, not as an optimization but as
half of the journal-authoritative shape above. F-16's SQLite/WAL
recommendation stays **not adopted** — the journal IS the write-ahead
log, in 65 bytes a commit, and it is readable by anyone with `cat`.

## Carried leaves

None. Every module here is holo2-original; the carry firewall
(`ENGINEERING.md`) has nothing to say about core.
