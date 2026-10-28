# capture — DESIGN

The physical plane: rasters, footings, survey. capture opens an
acquisition, authenticates it, exposes it at a declared footing,
measures local lattice pitch, surveys payload regions, and writes the
facts that follow. Imports `core` only (plus stdlib/numpy/scipy and the
declared image decoders).

Constitution: `holo2/docs/DESIGN.md`. Public surface + rationale: the
`__init__.py` docstring.

## Purpose

capture answers three questions and no others:

1. **what was acquired** — `scan.open_capture` authenticates a file and
   yields an immutable native `Raster`; the source SHA-256 is THE
   acquisition identity (L1);
2. **at what aperture** — `scale_space` derives footing views by
   exact-area decimation, always direct from native, never recursively;
3. **where the payload is** — `survey` + `lattice` + `_survey_tensor`
   segment scrap regions, produce cell-granular support masks and a
   printed-cell-PITCH vote per region (an exact rational of an inch;
   C3, RULINGS G4, 2026-08-22 — it was a count of 600-dpi engine dots).
   The hypotheses it votes among are `survey.candidate_pitches(...)`:
   the blind ladder `CANDIDATE_PITCHES_IN` (the registered pitch
   classes) UNION the declared row's own pitch when there is one
   (C3b, RULINGS H1(b), 2026-08-22). Discovery, which declares no row,
   gets the blind ladder unchanged; a decode of a sheet at a lawful
   rational pitch is not made to guess against a set that cannot name
   it. A declared c1..c4 row returns the blind tuple itself, so no
   decision in the corpus can move.

`ingest` is the writer that turns all three into durable facts. It holds
no format **imports** and no scheduling: the printed pitch arrives as
data (`ingest_capture(..., pitch_in)`), and the lattice it would feed is
`solve`'s. Note for F-05: a `CaptureInterpretation` has to carry
`pitch_in` as well as the declared DPI — the footing ladder is a
function of both (`ppc = pitch_in x dpi_true`), so DPI alone does not
name the interpretation.

`catalog` is `ingest`'s inverse (B9): the same three answers, read back
out of the store when no file was supplied. It derives nothing new —
`RegionRecord` v4 carries the support grid, so the rebuilt `SupportMask`
is byte-exact and the candidate's bbox and area are the survey's own two
expressions over it — and it commits nothing. An ATTACHED capture is
always ingested: **the fresh survey wins**.

`_survey_tensor` is package-private — no module outside `capture` may
name it (`holo2/tests/test_layering.py`).

## Public surface

`holo2.capture.__all__`, pinned by `holo2/tests/test_surfaces.py`.
Since B4 it carries no exception type: `LatticeNotFound` is raised and
handled inside capture, and `test_error_taxonomy.py` derives DECLARED
from `__all__`. Only `solve` and the composition root import this
package, which is why B4's census could take seven more names off —
the acquisition path (`open_capture`, `survey_raster`,
`region_candidates`, `ScaleSchedule`, `footing_id_for`) runs inside
`ingest`, and only its RESULT crosses a package line.

## Owned record families (R3)

| family | kind | version | invariant |
|---|---|---|---|
| `CaptureRecord` (+ `FootingSpec`) | `capture` | **3** | keyed by `source_sha256`, which IS the identity; footings ascend in ppc and are derived from the operator-declared true DPI. Joins `collection:captures`. v2 (B9): every `FootingSpec` names its own `capture_sha256`, validated against the record's identity — the `ingest.FootingView` collapse, which is what lets a footing exist without an ingest. **v3 (2026-08-17): `platen_backing`** — the median native luma of the four 32-px platen borders, the scalar every unsupported region pixel is filled to and one of the inputs `solve.prepared` hashes into a prepared plane's FILE NAME. It was computed per session from the raster and durable nowhere, so a resume without the file could not name the prepared planes already on disk; recording it at the producer is what lets a crash-cut resume re-earn its placement tail from the surviving `<state-dir>.prepared` sibling. Guarded for finiteness only (0.0 is a legal black border), a deterministic function of the authenticated bytes like `shape_px`, hence covered by F-08 on the same terms, and pinned BIT-EQUAL to the carried `solve.pose_fit.platen_backing` (the layering forbids the import, so the arithmetic exists twice and a drift of one ULP would rename every plane on disk). The MANIFEST is what refuses a pre-v3 state, by name; `store.SCHEMA_VERSION` is the state DIRECTORY's own layout and did not move. F-08 (2026-08-13): the WHOLE record is frozen at the wall — the Q2 dpi refusal keeps its named message, and any other differing re-ingest of identical bytes means the derivation moved (refuse loudly, pre-freeze rule). F-07 (same day, the cheap half): the family adopts `core.require_own_key` — an authentication fact may not be filed under another capture's sha, which is the one way it could lie about which bytes it authenticates, and a lie every footing and region derived from it would inherit. F-07's relational half (2026-08-13): a capture DECLARES NO REFERENCES — an acquisition is a ROOT fact (L1), standing on the authenticated bytes and on nothing durable |
| `RegionRecord` | `region` | **4** | one surveyed region of ONE capture. Its capture and its support grid (origin / step / extent) ARE its identity — `region_key` builds the key from exactly those values and the record carries no id field, so the family validates that the two agree (F-07's mechanism). Since 2026-08-12 the shape is DECLARED (`REGION_SPEC`, a `core.keys` slot spec) and `REGION_KEY_PARTS` is derived from it — `solve`'s `window` embeds these parts wholesale, and an embed is injective only against a fixed arity. F-08 (2026-08-13): survey content (`pitch_in_vote`, the mask blob) is FROZEN (`_region_transition`); B9's fresh-survey-wins stays intact because a lawful re-survey re-derives EQUAL records. F-07 relational (same day): a region DECLARES ITS CAPTURE — `ingest` commits both in one batch, and a region whose capture is absent is geometry with no dpi to interpret it |

`attachment_key(capture)` names "this capture's pixels are attached to
this session" (M12) and carries no record — a work item may decline with
a wake on it instead of vanishing when a raster is not supplied.

**OR-12 CLOSED (R3).** `RegionRecord` v2 carries its capture parent and
`support_origin_px` / `support_step_px` / `support_extent_px`, so durable
state ALONE places the region's lattice: the record plus its mask blob
rebuild the survey's `SupportMask` exactly (pinned byte-identical), and
the cell pitch follows from the printed row, the declared dpi and
`pitch_in_vote`. Re-surveying on resume is now an operational choice, not
a requirement to know the geometry. The components were always inside
`region_id`'s digest; R3 stopped them being write-only, and the
hash-free identity law (2026-08-11) then made the digest redundant and
deleted it — v3, with `survey.region_id` and `survey.support_mask_sha256`
gone from the carry's declared additions.

## The laws capture enforces, and where

| law | where |
|---|---|
| **L1** capture identity | `scan.open_capture` — source SHA-256 is the sole identity, and `scan.verify_source_unchanged` is the retention-barrier re-authentication. What is ENFORCED is exactly source-digest identity: two acquisitions of one sheet are distinct iff their bytes differ. "Only distinct physical acquisitions are independent" is the DOCTRINE, not the check — a re-encode, a crop or a resize of one capture has a different digest and would be admitted as independent evidence (see the ledger row below) |
| **L2** (its footing half) | `footing_id_for` puts the aperture IN the id, so a footing is the unit of LLR comparability and an illegal cross-aperture combination is a key mismatch, not a runtime check |
| **L11** determinism | survey and decimation are seeded-free pure functions of the pixels; no clock, no RNG |
| **L15** honesty | a region whose pitch vote declines says so (`pitch_in_vote = None`) rather than guessing — and since C3b it declines less often for the honest reason that the caller told it the answer, never by widening what a BLIND survey will guess |

Footing correspondence ACROSS captures is by ppc value (the D1 rule) —
that is what makes a session with a 1200-dpi and a 4800-dpi scan
well-defined.

## Measured facts capture relies on

- **Exact-area decimation, direct from native.** 8 px/dot roughly halves
  BER vs 2 px/dot on Canon scans; scans of one sheet mutually agree
  ~99%, so residual floors are print-frozen, not scanner noise
  (`CLAUDE.md` channel facts; e023b/e023c).
- **The optical ceiling behind the decimate doctrine**: Canon 4800
  knife-edge glass-level MTF10 ≈ 17 lp/mm ≈ 860-dpi information ceiling
  (e028) — sampling above it buys nothing but bytes.
- **3–4 scans/sheet is the knee** for multi-capture combining, and
  errors are print-correlated: equal-weight combining LOSES to
  best-single on a global detector and WINS only after a context
  detector de-correlates the bias (F1∘F6 law, `CLAUDE.md`).
- **Assembly cost is real but not scheduling**: ingest + survey of two
  captures is a constant 2.87–2.93 s in the H3 bench and is excluded
  from every `solve_s` (`holo2/docs/MEASUREMENTS.md`, method notes).
- **The survey is production and works**: 36 scrap regions segmented
  from the e023c scissors scan with all c2 (1/300 in) votes correct
  (MEASUREMENTS §H3bis) — the honest OPEN there was addressing, not
  segmentation.
- E021 structure-tensor scoring, the region survey and the pitch vote
  are qualified `src/holo` work carried unchanged
  (`.claude/memories/e021-payload-regions.md`).

## The pixel ground-truth path — capture's half (2026-08-15)

Root DESIGN §6.8 is the doctrine. Capture's obligations: the raw
raster stays memory-mapped (already true, `scan.py` `out="memmap"`);
the derived footings SHOULD move to the scale-space writer's existing
memmap arm (`scale_space.py`'s ndarray-or-memmap seam) so the ingest
apparatus stops holding region-scale anonymous memory — measured
~19.5 GB resident at ingest on the real sheet today. That flip is
scheduled follow-up work, taken with a before/after RSS measurement,
not folded silently into another wave.

## TO-FIX — capture's ledger

**F-nn** = the adversarial review with its severity scale; **D-n** = the
founding-design deviations indexed in `holo2/docs/DESIGN.md` §15.
Adjudication is H3.5's.

| id | defect | where | sev |
|---|---|---|---|
| F-05 / D5c | **CLOSED 2026-08-12 (worklist B9, RULED "build it").** A capture is attachable BY RECORD: `catalog.py` rebuilds `SupportMask`/`RegionCandidate` from `RegionRecord` v3 + the mask blob, `IngestedCapture.raster` is `Raster | None`, `FootingSpec` carries its capture (family v2), and `solve/plane.open_plane` catalogues every capture the store knows that this invocation was not handed. **An attached capture's fresh survey WINS** — ids are content-derived, so at equal bytes and dpi the two agree. Decode-resume needs ZERO pixels; pixel work declines and sleeps on `attachment_key` (M12). No pyramid caching, ever. Residue, deliberately unbuilt: the `CaptureFact` / `CaptureInterpretation` concept split, which Q2 still refuses in the meantime | `catalog.py`; `solve/plane.open_plane` | — |
| Q2 | **CLOSED — reject the conflict.** `CaptureRecord` now declares a `transition` that refuses a changed `dpi_true` at an existing capture key, naming both values. A corrected DPI renames every footing (`ppc = pitch_in x dpi`), hence every `EvidenceObservation` key that cites one, and re-mints every region while the old ones stay as unreachable geometry — the one option the review forbids. Minting a NEW interpretation stays available to F-05; until it has an identity, the write refuses | `records._capture_transition` | — |
| Q3 | **ANSWERED — no.** "Must every historical TIFF be resupplied on every resume?" B9 built the catalog split: a resume may name fewer captures than the state holds, down to none, and the CLI insists on `--scan` only when the state directory holds no session to resume. The proof is a resume that closes a volume byte-exact with no capture attached (`holo2/measure/verdicts/test_durability.py`) | `catalog.py`; `cli.parse_request` | — |
| F-12 | **CONVERGED 2026-08-13 — correctness closed by architecture; operator advisory only** (the WORKPLAN §H3.5 F-12 row carries the full argument and the two rejected overbuilds). The boundary: the source file is EXTERNAL input; its sha seals correctness at ingest (everything downstream self-verifies — per-tile CRC, payload SHA, attach re-auth); the carried post-survey `verify_source_unchanged` and the cli closure advisory (stat always, hash on stat-change, report-only) are operator-error SERVICE, not integrity mechanisms. **BUILT 2026-08-13** as `cli._source_advisory`: the CLI stats each named source at its own entry, re-stats after `decode` returns, and hashes only a source whose `(st_mtime_ns, st_size)` moved — "touched but identical", or "SOURCE CHANGED DURING THIS RUN" naming the ingested and the current sha8. The ingested identity rides the observer catalog `main` already reads, so a source this run never ingested (a terminal resume) has no ingest window and stays silent. stderr only — no status, no exit code, no durable state | `cli._source_advisory`; `scan.verify_source_unchanged` |
| region bbox tie | two disjoint survey components of ONE capture that share a bounding box AND a support step would now share a region key — the mask digest that used to disambiguate them left with `region_id`. Geometrically possible (interlocking L-shapes), never observed; the cheap closure if it ever binds is to append the support mask's blob content address, which is the sanctioned hash and already computed | `records.region_key` | LOW |
| L1 gap | the identity check is source-digest equality, so a DERIVED capture (re-encode, crop, resize) presents as an independent acquisition and its correlated errors would be summed as if independent — which is exactly what the F1∘F6 multi-scan law says must not happen. Nothing in `open_capture` can see derivation from bytes alone; the fix is a declared provenance field on the ingest boundary, not a stricter digest | `scan.open_capture` | MEDIUM |
| F-26 | `footing_id_for` shortens the capture SHA to 12 hex characters AND flattens `(capture, ppc)` into a `:`/`/`-delimited string, and that id is part 0 of every window, pose and evidence key. Re-read as **hygiene**, not integrity: the delimiters cannot occur in hex or in an integer, so the flattening is injective over the alphabets it actually uses, and the full digest costs ~+52 B per key × tiles × footings, order 200 KB on an e029-class envelope. The identity law (2026-08-11) deliberately did NOT restructure it — every evidence key moves when it does, so it is scheduled WITH or AFTER core's D1 fold, never separately | `ingest.footing_id_for` (not `records.py`) | MEDIUM (hygiene) |

**Ingest is not a worker** — idempotent, content-addressed and
unconditional, so it spends nothing and expands the frontier directly
(PROVIDERS CP1). Not a defect; promotion to a scheduled provider waits
until captures start arriving mid-session.

**Ingest is also the tree's longest silent stage.** `ingest_capture`
emits ONE event, at the end: open + authenticate + full-raster luma +
whole-platen survey all run before anything reaches the observer, and on
a 2.29 GB TIFF that is the entire wait an operator sees with no output.
This is a §6.6 progress gap in its own right, distinct from D5b (which is
about what a *worker* reports), and it is why the H3 bench excludes the
constant 2.87–2.93 s assembly from every `solve_s`.

## Carried leaves

| leaf | from | adaptation |
|---|---|---|
| capture ingest/auth | `src/holo/receive/scan.py` | store/commit wiring (R2: `ingest.py`) |
| exact-area scale views | `src/holo/receive/scale_space.py` | footing derivation |
| survey / segmentation | `src/holo/receive/survey.py`, `_survey_tensor.py` | region records; the pitch vote (unit, and its per-survey candidate set); "working very well" (user) |
| local lattice measurement | `src/holo/receive/lattice.py` | none |

**How much of the carry is actually exercised.** Production reaches this
package through exactly two entry points — `open_capture` and
`survey_raster` — plus `auto_ppc_levels` for the footing ladder. Nothing
in `holo2/src` calls `survey.full_support`, reads `PayloadSurvey`'s
`cell_pitch_px`, `pitch_votes` or `diagnostics`, or materialises a single
decimated view: **all** of `scale_space`'s decimation machinery
(`area_decimate`, the chunked writers, `AreaPixelTransform`,
`ScaleLevel`/`ScaleSchedule`) is carried, oracle-pinned and unused, because
H3bis reads one footing and it is the native one. That is roughly 55% of
the package's lines. Kept deliberately — the ladder is the D1 footing rule
and H4/H5 will read coarser lanes — but it is carried inventory, not
running code, and a reader should not infer coverage from line count.

Byte-equality with `src/holo` on shared fixtures is pinned outside the
tree: `tests/holo2_oracles/test_oracle_scan.py`, `test_oracle_scale_space.py`,
`test_oracle_survey.py`.
