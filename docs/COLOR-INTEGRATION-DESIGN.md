# COLOR-INTEGRATION-DESIGN — provisional CMY7 and CMY8 formats

**Accepted and implemented provisional design, 2026-07-26.**

Status: **SOFTWARE PATH IMPLEMENTED; NOT PAPER-QUALIFIED.** This document
defines the as-built provisional CMY7 and CMY8 architecture in `src/holo`.
It does not claim that any color row is reliable on paper, promote a color
row into default discovery, or supersede the qualification requirements in
[HOLO-DESIGN](HOLO-DESIGN.md).

The implementation sequence, code ownership, and merge gates live in
[COLOR-IMPLEMENTATION-PLAYBOOK](COLOR-IMPLEMENTATION-PLAYBOOK.md). This
document owns the reasons for the design and the provisional format and
receiver semantics.

Evidence labels used below:

- **MEASURED** — supported by an existing experiment or hardware record.
- **AS-BUILT** — describes the implementation before this color work.
- **SELECTED** — the provisional behavior selected by the design.
- **IMPLEMENTED** — present in the current `src/holo` software path; this
  is not a paper-channel claim.
- **DEFERRED** — a possible optimization that is deliberately not in the
  first implementation.

---

## 0. Revision ledger

The design changed materially during review. The sequence is recorded here
so later readers do not mistake a superseded proposal for the current
decision.

| Revision | What changed | Current standing |
|---|---|---|
| `09ebd1e` | Added the first CMY7/CMY8 integration proposal. It emphasized an append-only color family and reconstructed the historical color evidence. | Historical basis. Its channel arithmetic and experiment record remain useful. |
| `a97815c` | Added the implementation playbook and changed the preferred policy to a common v1 architecture, initially by migrating K through generalized codec/state seams first. | The no-migration/no-legacy-state decision remains. The broad K-first numerical migration does not. |
| `f3e31a7` | Updated the document after discovery state became derived rather than separately persisted. | Retained: discovery status is derived from branch facts. |
| `f49bcdb` | Aligned the proposal with the lean receiver: source-SHA identity, lane-local raw evidence, flat attempts and certificates, derived diagnostics, BCH quarantine, and mandatory `retry150`. | Retained as the shared authority model. |
| 2026-07-26 current revision | Selected both CMY7 and CMY8 at c2 and c3; replaced broad K generalization with shared authority plus explicit row-selected numerical leaves; selected RGB scale lanes, full known-furniture use, per-lane plane registration/refinement, and the historical `paperholo` detector footing. | Current implementation baseline. |
| `1b100cb`, 2026-07-26 initial implementation tranche | Added immutable profiles and four catalog-only rows, p120 furniture and frozen random domains, exact CMY7/CMY8 framing and mappers, common-K stream-major CMY8 source mapping, multistream fountain accounting, color composition, composite DeviceCMYK emission, plane ground truth, and an independent synthetic color channel. | Implemented and digitally tested. Its receiver-open status is superseded by the later receiver tranche. |
| `78ac26a`, 2026-07-26 | Added a deterministic production-PostScript → Ghostscript RGB-TIFF corpus with source dropout/speckle, centered shear, crop, blur, and synthetic RGB noise. | Superseded and removed. The useful distortion algorithms were relocated into the standalone TIFF-in/TIFF-out tool; the corpus builder, generator/render orchestration, manifest, and receiver gate were not retained. |
| 2026-07-26 receiver tranche | Added p120 binary luma placement projection, aligned direct-native RGB lanes, historical color detection/registration with a deterministic 512-anchor cap per class and plane, pre-lane certified component projection, compact multistate evidence, stream-aware BP60/BP150 attempts, certificates, replay, retention, and multistream close. | Initial as-built receiver baseline, corrected by the 2026-07-27 receiver review below. Physical qualification and default promotion remain open. |
| 2026-07-26 terminal-replay correction | Kept immediate stop at the first terminal color close and retired all remaining color numerical block bodies at that boundary. Attempts, certificates, artifact publications, and block identities remained the causal audit; K close and retention bytes remained unchanged. | **Superseded 2026-07-27.** Color now retains the ordinary K-like live frontier; terminal close adds no global evidence wipe. |
| 2026-07-26 CMY7 evidence-bound correction | Kept the historical QDA leaf exact and transient, but bounded each CMY7 cell's six-score vector at the durable adapter boundary by uniform L-infinity scaling to 20. The receiver policy ID records this choice. | Current CMY7 persistence invariant. K remains unchanged; CMY8 calibration was subsequently corrected by the 2026-07-27 review. |
| 2026-07-26 color-divergence parity correction | Added non-gating color certificate/evidence comparisons on the published live frontier: CMY8 selects the certificate stream's evidence column; CMY7 compares the exact reconstructed state with the seven-state hard maximum. | Current color audit invariant. Generic records remain shared; K scalar generation, replay, reports, and snapshot shape are unchanged. |
| 2026-07-26 RGB scale-contract clarification | Pinned ordinary nonnegative uint8 RGB and equivalent common-scale uint16 RGB as the provisional scanner footing; added direct evidence-equivalence coverage. | Documentation/test clarification only; detector behavior and K remain unchanged. |
| 2026-07-27 committed-diagnostic retirement correction | Made terminal color frontier retirement an explicit committed-barrier diagnostic operation instead of asking an observer to infer it from certificate completeness. | **Superseded 2026-07-27** with the terminal-wipe policy itself; ordinary per-address retirement remains visible without a global diagnostic operation. |
| 2026-07-27 Q0/Q1 evidence tranche | Recorded a nominal production-receiver corpus result and added an all-four full-page production `tiffsep` gate against authored C/M/Y truth and zero K plus exact clean-`tiff24nc` plane recovery. | The corpus result, its Q0 record, and its receiver gate were subsequently removed. The independent Q1 emission gate remains software qualification evidence; paper qualification and default promotion remain open. |
| 2026-07-27 standalone TIFF qualification tool | Relocated the useful distortion algorithms into one strict TIFF-in/TIFF-out command, with explicit synthetic transforms and optional `nominal`, `stress`, and `hp-m281-flatbed` shortcuts. | Current; 2026-08-02 the characterized shortcut split into `hp-m281-flatbed-cmy` and the K-only `hp-m281-flatbed-k` (grayscale output). With no profile, synthetic parameters start at identity and only explicitly named effects apply. It accepts one 600-dpi RGB TIFF and emits one 1200- or 4800-dpi scan TIFF. It does not invoke or depend on Ghostscript, the generator, the receiver, a corpus builder, manifests, or sidecars. |
| 2026-07-27 full-page M281/CAL-1 operational check | Ran the characterized arm on one production c3-CMY8 page and ingested its 1200-dpi TIFF with the production receiver. | File/transform/ingest seams passed; acquisition did not: zero poses, attempts, or certificates and an open close. This is retained as an explicit negative record. |
| 2026-07-27 receiver correctness review | Pooled PAVA ties and class-balanced its binary planes without changing dust; made collapsed planes exact erasures; bounded K/RGB payload sampling locally while retaining region-wide fits; enforced actual post-demapper nonzero floors; count-gated one pre-BP150 close; removed color terminal wiping; strengthened registered-row public validation; and corrected codec/repair reporting semantics. | Current as-built receiver contract. Software tests cover the corrected boundaries; paper qualification remains open. |
| 2026-07-28 one-tile/NeedMap correction | Removed the inherited 300-dust aggregate cliff; repaired sparse QDA train/validation state coverage without overlap; calibrated CMY8 planes from the full 20-row dust contract with component-local support; enforced prior-barrier-only certificate feedback; and skipped wholly terminal regions before RGB work. | Current as-built receiver contract. Synthetic one-tile c2/c3 and full TIFF-chain software gates pass; physical qualification remains open. |
| 2026-07-27 direct all-four receiver gate | Composed the production generator, Ghostscript, standalone TIFF CLI, real receiver CLI, and strict reload in one slow opt-in test per color row. | Current test-only gate. No corpus package or production orchestration was restored. |
| 2026-07-27 CMY7 structural attempt gate | Scatter complete-pack support through the exact inverse interleaver and check every child before paying for soft demapping. | Current necessary scheduling gate. The actual post-demap nonzero floor remains authoritative; qualification standing is unchanged. |
| 2026-07-27 bounded receiver vectorization | Vectorized bounded E022 row alignment, window-local 3×3 setup, stable owner selection, batched provenance validation, and the exact CMY7 bit marginals. | Behavior-preserving KISS/performance refinement only; format, policy, evidence, ownership, and qualification standing are unchanged. |
| 2026-08-02 certified pose refinement (§5.5) | Added the RECEIVE-DESIGN §7 forward pose-refinement arm for color lanes (payload-rework 6.1, ruling 10.6): certificate-labelled per-plane presence bits through the mint-once projection, a frozen per-plane baseline calibration, K's shared candidate grid and diagonal-stripe holdout, furniture-logloss non-regression, and region-granularity refined reuse. Policy `provisional-v5-pool-law` → `provisional-v6-refine`. | Current as-built receiver contract. Qualification on synthetics only; hardware standing post-08-04. |
| 2026-08-13 pooled-fountain -v1 rows (HOLO-DESIGN §13.35; docs/CMY8-POOLED-FOUNTAIN.md) | Appended `c2/c3-cmy8-p120-v1`: the SAME CMY8 tile codec, detection, certification and receiver payload path, with ONE pooled fountain (`esi = counter·n_streams + stream_idx`, stream-exact block quotas, deterministic dead-plane tier — dial-conditional, enforced and reported guaranteed at q ≤ (n−1)/n, reported absent above, ruled 2026-08-14) and per-stream metadata equations. This SUPERSEDES, **for the -v1 rows only**, every -v0-scoped statement in this document — each remains exact for the -v0 rows and the printed e030/e032 sheets: §8.3's "bit striping, different K values, different q values, and pooled ESI numbering are not part of the format"; §8.3's "the physical counter … is never flattened with the level" and §8.5's "not flattened to 3*counter+level" (a pooled row flattens by STREAM, not level — the level/scale sense stays true everywhere); §8.5's "verified close requires all three source streams … exact stream-major reassembly" and its per-stream `VolumePlan.n_repair` reporting (pooled: one solve space, row-major slicing, pool-global repair; any 2-of-3-stream evidence can close); §8's "four provisional -p120-v0 catalog rows" (now six, F14); and §9.1's stream-major-only package-map line (streamset additionally owns the pooled row-major mapping). | Adopted, implemented, simulation-qualified (dead-Y E2E gate, nine-row backbone net, gs+distortion chain on both rows). Rows catalog-only provisional; physical qualification open; the version-0/row-identity signaling ruling is OPEN (design note §4). |

The important correction is:

> “One architecture” means one generator/receiver authority and lifecycle.
> It does not require K, CMY7, and CMY8 to use the same numerical detector,
> mapper, FEC framing, or renderer.

Small, explicit format dispatch at those mathematical leaves is simpler and
safer than forcing the established K path through speculative color
abstractions. It is also different from maintaining separate K and color
applications: scheduling, provenance, barriers, state, conflict authority,
metadata, fountain close, and diagnostics remain shared.

---

## 1. Basis and claim discipline

This design reconciles two repository generations:

| Source | Evidence for | Not evidence for |
|---|---|---|
| [COLOR-DESIGN](COLOR-DESIGN.md) | historical `paperholo` CMY8/PID-MLC design, its later CMY7 amendment, and the measured device split | the current `src/holo` architecture or a completed pack7 codec |
| [Experiment 017](../experiments/017-color-channel.md) | the built CMY8 detector/emitter, pilot/dust behavior, registration model, and M281 hardware failure analysis | a certified color volume in current Holo or a CMY7 coded round trip |
| [PILOTS-DESIGN §16](PILOTS-DESIGN.md) | measured W/CM word rendering and the training-dust precedent | qualification of the new 64×64 `p120` family |
| [HOLO-DESIGN](HOLO-DESIGN.md) | current 64×64 archive architecture, K invariants, and receiver authority | a qualified color row |
| `src/holo` | the current K implementation and the implemented provisional CMY7/CMY8 software path | paper reliability or default-discovery eligibility |
| `src/paperholo` | the historical color algorithm used as a differential oracle for the production-local port | an API or runtime dependency for production Holo |

“Measured” always means measured on the cited engine, emission path,
scanner footing, detector footing, and consumable state. It is not a
transfer claim. Exact capacity arithmetic is not a reliability claim.

The historical record contains a working CMY8 experiment and direct
known-state CMY7 fields. It does **not** contain:

- a CMY7 `bytes -> FEC -> 11-to-4 pack7 -> paper -> receiver` path;
- qualification of any color format in the current 64×64 Holo receiver;
- evidence that c2 color is usable on either target engine.

`COLOR-DESIGN` is also internally transitional: it first selected CMY8,
later promoted pack7 for the M281, and still contains text calling pack7
unbuilt or conditional. The present document resolves that ambiguity:
both modulations are implementation deliverables, and both remain
provisional until their own paper qualification.

---

## 2. Selected outcome

The implementation contains four explicit color rows:

| Modulation | Cell size | Initial purpose | Discovery status |
|---|---:|---|---|
| CMY7 | c3 | M281-class triple-free candidate | catalog only |
| CMY7 | c2 | density experiment on the same modulation | catalog only |
| CMY8 | c3 | AltaLink-class eight-state candidate | catalog only |
| CMY8 | c2 | density experiment on the same modulation | catalog only |

Here c2 and c3 mean cells two and three 600-dpi device dots wide. The final
registry identifiers are implementation names; the four semantic rows above
are not optional.

All four rows use:

- the 64×64 tile;
- a new exact-120-site (`p120`) furniture family;
- a 100-site binary W/CM BCH address word;
- 20 deterministic known-state dust sites;
- the existing scale-lane cadence and receiver scheduler;
- composite DeviceCMYK emission;
- the shared session, provenance, barrier, certificate, metadata, fountain,
  close, and diagnostic authorities.

All four rows must be usable explicitly end to end: generation, scan
ingest, discovery under an explicit candidate set, address placement,
color evidence, `max60`, hardwired `retry150`, certification, persisted
resume, metadata/fountain recovery, verified envelope close, and
operational diagnostics.

That is what “on equal footing with K” means. It does not mean that an
unqualified color row joins default discovery or that color and K share a
numerical detector.

### 2.1 Device interpretation

**MEASURED:** on the HP M281-class engine the CMY triple was toxic. In the
e017 hardware page its cells produced roughly 25/43/52% C/M/Y level error.
Seven-state direct fields had hidden this failure.

**MEASURED:** on the Xerox AltaLink-class engine the eighth state was useful;
the historical comparison reported about 2.208 bits/cell for CMY8 versus
2.138 bits/cell for the best seven-state subset.

The initial operational expectations are therefore:

```text
M281-class engine       -> CMY7-c3 first
AltaLink-class engine   -> CMY8-c3 first
c2 rows                 -> explicit experimental rows
```

Those are measurement priorities, not row restrictions. The software
implements all four.

### 2.2 Deliberate non-goals

The first implementation does not include:

- GF(7) LDPC;
- arithmetic/ANS modulation;
- a connected 10,934-bit CMY7 LDPC;
- CMYK or CMY-plus-K payload modulation;
- automatic feature/model search;
- iterative multilevel decoding;
- partial CMY7 pack inference;
- runtime-negotiated alphabets or arbitrary codebooks;
- a second color scheduler, session type, discovery state machine, or
  diagnostic database;
- old development-state migration or a compatibility shim.

---

## 3. Architectural boundary

### 3.1 Shared authority

The following owners are shared across K, CMY7, and CMY8:

- format-row resolution and isolated discovery hypotheses;
- scale scheduling and lane barriers;
- scan SHA-256 identity and exact-duplicate refusal;
- placement ownership and the BCH-contradiction firewall;
- evidence provenance and same-lane combination authority;
- attempt provenance, `max60`, `retry150`, and CRC exposure accounting;
- certificate conflict authority;
- addressed metadata solving;
- fountain planning, ingest, and verified envelope close;
- durable replay and operational diagnostics.

CMY8 adds `stream_id` as a real coordinate to the owners that need it.
K and CMY7 use `stream_id = main`; CMY8 uses `C`, `M`, and `Y`.

### 3.2 Row-selected numerical leaves

The row selects the numerical operations that are genuinely different:

| Leaf | K | CMY7 | CMY8 |
|---|---|---|---|
| lane raster | existing grey | area-decimated RGB plus derived luma | area-decimated RGB plus derived luma |
| payload detector | existing scalar K detector | seven-class QDA state scores | eight-class QDA, marginal level LLRs, tie-pooled class-balanced PAVA |
| channel mapper | one bit per cell | natural-radix 11 bits to 4 legal states | three presence bits per cell |
| FEC/frame | existing one-code K tile path | three-child compound bank, one shared frame/CRC | one independently framed code per C/M/Y stream |
| certified projection | binary printed cells | complete C/M/Y presence tile | known certified component planes only |
| output renderer | existing K `imagemask` | composite DeviceCMYK | composite DeviceCMYK |

The leaf dispatch is explicit and exhaustive over the registered row. The
generator composition and color-attempt boundaries select on the stable
`codec_id` value, not Python object identity, so an equal reconstructed
descriptor does not depend on sharing a singleton instance. This is not an
extensible plugin hierarchy and does not duplicate the outer pipeline.

### 3.3 K preservation boundary

Existing K rows keep:

- coding and row identities;
- family and row seeds;
- word/filler site draws and values;
- LDPC graphs, shortening, frame, CRC, and bit order;
- slot mapping and payload keystream;
- cell fields and PostScript bytes;
- scalar detector values and decode decisions for identical evidence;
- metadata equations, fountain symbols, certificate conflicts, and
  verified-close results.

Shared record shapes may acquire the minimum stream/score coordinates
needed by color; old development-state loading is not required. K's
mathematical leaves are not rewritten merely to make CMY7 or CMY8 look
generic.

### 3.4 Generator and receiver flow

```text
generator
  envelope
    -> row-declared logical fountain stream set
    -> row-selected frame/FEC
    -> row-selected channel mapper
    -> canonical state/presence tile
    -> K imagemask or composite DeviceCMYK image
```

```text
receiver
  authenticated scan
    -> row-selected direct-native grey or aligned RGB scale lane
    -> shared binary-luma E021/E022 footing
       (word plus dust; dust is dark iff >=2 ink components)
    -> E022 placement/pose and 100-site BCH word authority
    -> BCH authority or quarantine
    -> exact multistate furniture plus pre-lane certificate projection
    -> per-plane dot-domain residual registration
    -> row-selected K or color payload detector/evidence
    -> scan and same-lane union BP60 attempts
    -> selective automatic BP150 retry
    -> row-selected soft demapper/FEC
    -> certificate keyed by (physical address, stream)
    -> retained/replayed stream frontier
    -> shared metadata/per-stream fountain close
```

---

## 4. Physical state and `p120` furniture

### 4.1 Canonical color states

Use the presence tuple `(C,M,Y)` and canonical numeric state:

```text
state = C + 2*M + 4*Y
```

| State | Presence | Name |
|---:|---|---|
| 0 | 000 | W |
| 1 | 100 | C |
| 2 | 010 | M |
| 3 | 110 | CM |
| 4 | 001 | Y |
| 5 | 101 | CY |
| 6 | 011 | MY |
| 7 | 111 | CMY |

The tuple is written in `(C,M,Y)` order; the numeric weights above remove
any ambiguity. CMY7 permits states 0 through 6. CMY8 permits all eight.

Canonical state/presence fields are logical render inputs, not promises
about scanner RGB values. The renderer maps them to device C/M/Y plane
samples.

### 4.2 Site geometry

Every color tile contains:

```text
4096 total cells
- 100 W/CM BCH word sites
-  20 known-state dust sites
= 3976 payload cells
```

The new family seed derives all 120 positions as one collision-free
`p120` family. It may redraw the 100 word positions relative to current
`p100`; that does not alter an existing K row.

Position and value derivation stay separate:

- furniture positions derive from the `p120` family seed and repeat at the
  tile lattice;
- word values derive from the row seed, physical counter, and word index;
- dust values derive from the row seed and absolute page/tile/site address.

The same derivations are used by generator, receiver, re-encoder, tests,
and diagnostics.

### 4.3 Binary address word

The 100-site address word remains binary:

```text
word bit 0 -> W
word bit 1 -> fixed CM
```

This retains the measured robust bootstrap. “One means any ink” is not
used: it is a mixture of different channel states, was substantially worse
in the historical measurements, and becomes fragile when Y or another
consumable weakens.

The address path remains luma-first. It does not require a successful color
model or any one color plane.

### 4.4 Dust values

Word sites already provide many W and CM labels. Dust therefore covers the
missing states.

CMY7 uses exactly four examples of each missing state per tile:

```text
4 x {C, M, Y, CY, MY} = 20
```

CMY8 uses a three-each base quota:

```text
3 x {C, M, Y, CY, MY, CMY} = 18
```

For each tile, the generator constructs the stated multiset and applies a
row/address-keyed permutation before assigning it to dust sites in canonical
raster order. For CMY8, let the ordered missing-state vector be
`[C,M,Y,CY,MY,CMY]`; its two extra entries at physical counter `c` are
elements `(2*c) mod 6` and `(2*c+1) mod 6`. This balances extras over three
successive counters. W and CM are not spent again in the initial dust
quota.

The CMY8 dust multiset is intentionally a **wire-format fact**, not a desired
binary calibration prior. Because the address word already supplies W and CM,
the six missing dust states make C and M present in one half of their rows but
Y present in two thirds. That explains the imbalance; address-word rows do
not enter the component PAVA estimator. The receiver leaves the printed
schedule and its golden vectors unchanged and class-balances the dust labels
inside each binary PAVA fit. Word and dust rows both remain part of QDA
training and held-out model validation.

This is a new 64×64 design. The historical evidence established that
18 sites in a 60×60 tile could support its detector footing; it did not
qualify the exact `p120` geometry or these missing-state-only quotas.

### 4.5 Shared luma projection and exact color labels

The implementation uses the same spatial reference machinery for K and
color placement. Under each concrete row/page/tile hypothesis, the 120
color furniture states have this deterministic binary projection:

```text
word:  W -> 0, CM -> 1
dust:  state -> 1 iff popcount(C,M,Y) >= 2, otherwise 0
```

This is the equal-channel ideal-luma split used by the shared E021/E022
footing. It lets both word and dust positions contribute to correlation,
pose refinement, held-out placement audit, and ownership. It is not a
hard-state color detector and does not change the printed multistate dust.
The page hypothesis supplies the counter needed to derive its expected dust
states; competing page hypotheses retain their own references.

The roles remain deliberately asymmetric:

```text
binary word + dust -> placement score and shared pose
100-site BCH word  -> address authority
exact word + dust  -> color registration, QDA labels, held-out validation
```

Only the 100 indexed word sites are collected into BCH votes. Dust
agreement cannot rescue a BCH failure, manufacture an address, or override
a word conflict. After BCH promotion, the exact state of **every one of the
120 sites** is known and may be used to:

- score and reject the concrete color model;
- fit C/M/Y residual registration;
- train the color detector;
- provide deterministic held-out word and dust validation; and
- monitor live plane/channel health.

The binary projection is intentionally simple and provisional. Its
paper-channel separation must be measured at both cell sizes; successful
synthetic placement is not that measurement.

### 4.6 BCH contradiction firewall

The existing simple firewall applies to color without exception. If a BCH
word conflict occurs:

1. identify every placement/window that contributed to the conflicting
   word evidence up to that point;
2. quarantine those placements;
3. retain the physical candidate in the need map so later independent
   evidence may resolve it;
4. report the number of quarantined placements operationally.

A quarantined placement contributes no:

- dust or pilot training label;
- registration fit;
- K or color payload evidence;
- LDPC attempt or CRC exposure;
- certificate;
- refinement label or hint.

This gate is important because the richer color detector otherwise gives a
bad address hypothesis more downstream ways to appear plausible.

---

## 5. Scale lanes, registration, and refinement

### 5.1 Color uses the existing scale cadence

Color is processed at every existing scale lane, just as K is. Each color
lane is area-decimated independently and per channel from the authenticated
native RGB raster; it is never derived from another lane. The resulting RGB
and its deterministic luma reduction have the same coordinate system,
dimensions, scale order, lane identity, and barrier. Luma feeds E021/E022;
the aligned RGB samples feed the color payload detector.

The receiver does **not** add:

- a color-only lane schedule;
- a second scheduler;
- a persistent RGB pyramid;
- a native-only color pass after all luma lanes.

Only the current lane needs to be materialized. The memory cost is therefore
roughly the RGB form of one transient lane, not three full-page pyramids.
An implementation may share a resampling primitive, but K continues to
request and receive its existing grey lane so its numerical path remains
unchanged.

Payload sampling is bounded below the lane as well. K computes the historical
region-median pitch once, then crops and filters exactly one E022 window at a
time; only its sampled means survive for region-context calibration. Color
likewise uses short-lived per-window RGB crops for base features, small raw
footprints for individual NCC anchors, and only the residual-corrected sample
points plus an aperture halo for proposed features. The region-wide QDA and
held-out comparison consume the collected sample arrays from every window,
not one bounding-box raster. A common region scale divisor is found from the
local window footprints. There is no multi-window union crop and no
page-sized crop cache.

A grayscale source can still contribute W/CM address evidence to an
explicit color hypothesis. It cannot create C/M/Y payload evidence or a
color certificate.

The provisional color photometric contract is finite, nonnegative reflected
RGB in ordinary uint8 form or an equivalent common positive uint16 scaling
(for example, `uint8 * 257`). The historical `/255` detector normalization
does not infer a per-image or per-channel range. A common positive scaling
is harmless here because registration and detector fitting/scoring use the
same scale; uint8/uint16 evidence equivalence is pinned by regression tests.

### 5.2 Registration model

For each physical capture and each scale lane independently, color uses:

1. the E022 lane pose as the shared page/fragment geometry;
2. one residual registration model for each of C, M, and Y.

The residual model is the historical first-order shape:

```text
delta_plane(y_page) =
    (dy0_plane + dy1_plane*y_page,
     dx0_plane + dx1_plane*y_page)
```

`y_page` is a normalized absolute page coordinate. Common paper/scanner
deformation belongs to the shared affine. Toner-plate displacement and
printer-direction drift belong to the plane residuals. The policy fixes the
reference/gauge so common motion is not counted twice.

This is intentionally not three unrelated page poses. Printers impose a
shared sheet geometry and plane-specific registration residuals.

### 5.3 Registration anchors

Registration uses exact furniture and any eligible certified components
after word lock:

- W/CM word sites strongly constrain the common affine and provide abundant
  C/M-bearing anchors;
- exact-state dust supplies pure C, M, and Y anchors and the other
  constellation combinations;
- certificates committed before the lane opens add payload components;
  CMY7 supplies all three, while a CMY8 certificate supplies only its named
  component.

For each reflected RGB channel, the implementation first runs the historical
pinned-prior two-Gaussian blind component detector over the region. Exact
known-ink candidates are kept in three separate classes: word, dust, and
pre-lane certificate. For each plane, each class is sorted by canonical
`(page, y, x)` coordinate and deterministically bounded to 512 candidates.
When a class is larger, candidate `floor(i*N/512)` is selected for
`i = 0..511`: the left edge of each equal-width coordinate bin. This bounds
the expensive registration work without changing detector fitting, which
continues to consume every known site.

For each selected candidate, the blind bits and confidence form its 3×3
halo; exact furniture/certificate bits override the corresponding halo
components. A weighted-NCC search on a fixed two-samples-per-device-dot
rectification measures the anchor offset. Those offsets are converted back
to print-dot units before the robust constant-plus-linear-in-page-Y fit.
Insufficient or degenerate support returns the zero/constant historical
fallback rather than inventing a plane pose.

The anchor NCC leaf and robust residual fit are production-local ports with
differential tests against the historical `paperholo` functions.
Production `src/holo` imports no behavior from `paperholo`.

### 5.4 Lane-local refinement

Refinement is performed once, before decoding, independently in every lane.
Numerical evidence, detector fits, poses, and residual registration models
never cross lane boundaries. Certificates may enable refinement in a later
lane because they are authoritative decoded facts; raw measurements do not.

Certified re-encoding returns a physical projection plus a
known-component mask:

- K: the existing complete binary projection;
- CMY7: one certificate reconstructs all three presence planes;
- CMY8: a C, M, or Y certificate reconstructs only that component; unknown
  sibling components stay masked out.

Thus CMY7 and CMY8 are both multilayer tiles. CMY7 requires the inverse
pack7/interleaver/FEC operation before its three printed planes are known;
CMY8 obtains them one certified stream at a time.

The baseline samples the shared E022 pose with zero plane residuals. The
candidate samples with the C/M/Y residuals described above. Both fit an
equal-prior state model on the deterministic search split and score the
disjoint held-out split. The candidate is adopted only when:

- total held-out known-state loss improves;
- held-out word loss does not regress; and
- held-out dust loss does not regress.

Fully reconstructed certified cells may become QDA state labels. A partial
CMY8 projection remains component-only: it can supply registration anchors,
but the implementation does not synthesize a joint state label from
uncertified siblings. Certificate IDs used by an adopted residual are
carried into the compact evidence block as dependencies.

Only certificates committed before the lane opens participate. A
certificate minted by the lane's BP work is not fed back into a same-lane
loop; it becomes available to a later lane or physical capture. No color
plane is inferred from an uncertified sibling.

### 5.5 Certified pose refinement (the RECEIVE-DESIGN §7 color arm)

Added 2026-08-02 (payload-rework 6.1; ruling 10.6 "color needs it too").
§5.4's residual registration adjusts per-plane sampling *offsets* within a
fixed window pose; this section adds the color counterpart of K's E023c
certificate-labelled *pose* refinement (`color_refine.py`, mirroring
`certified_refine.py`): one bounded forward proposal per emitting E022
color window, labelled only by certificates committed before the lane
barrier, adopted only against held-out evidence, discrete identity frozen.

**Labels.** The exact printed truth for a certified color tile is
reconstructed through the ONE reconstruction primitive this document
already sanctions for known-component overlays and divergence:
`project_certified_color_tile` (§4.5/§5.4's projection), now mint-once
cached per (format, address, certificate-set) —
`color_projection.cached_certified_color_projection`, the color analog of
`records.printed_cells_from_record`. Labels are flattened **(cell, plane)
binary presence observations**: word/dust furniture sites contribute all
three planes (format facts — the pilot analog), certified cargo cells
contribute exactly the planes their certificates authorize (CMY7: all
three from `main`; CMY8: one per certified stream). No joint state label
is synthesized from uncertified siblings, as §5.4 already requires.

**Fit.** The structure is K's, deliberately: a detector-free photometric
contrast ranks the shared bounded candidate grid (identical
angle/phase limits and steps, imported from `certified_refine`, never
copied), and the adoption decision is made through a detector **frozen
before the search**. K freezes its retained generation-zero PAVA
calibration; color's region QDA/PAVA detector is transient by design
(kiss), so nothing durable can be replayed. The frozen stand-in is the
per-plane affine calibration `score_p = (midpoint_p − value_p) /
spread_p`, with midpoint/spread = median / floored mean absolute
deviation of the baseline-pose samples of the complementary channel over
all aligned cells. This is deterministic, pose-independent within the
comparison (both gate arms ride the same transform, so the gate measures
pose, not calibration), ink-positive like K's score sign, and makes the
RGB scale — u8/u16 footing and the §6 region divisor — cancel by
construction, which is why refinement samples the undivided filtered
window crop and does not replay the divisor probe. The candidate-search
objective is K's `_pose_objective` verbatim on the (negated) calibrated
scores; the train-loss tie-break and coarse→fine grid schedule are K's.

**Adoption gate** (the color-native held-out-improvement-without-pilot-
regression): the holdout is the ONE §7 diagonal-stripe block partition
(ruling 10.5 machinery, shared for furniture and cargo alike; block
weights keep K's furniture/cargo separation), and adoption requires

- held-out summed per-plane logloss improves by `MIN_HELDOUT_GAIN`
  (K's constant); and
- held-out **word/dust furniture logloss does not worsen** (the furniture
  sites are the color pilot analog; slack `1e-9`, float re-association
  only).

Support gates reuse K's refinement ladder constants over flattened
observations (payload train/validation minima, per-class minima,
certified-block minimum, furniture-count minima, deterministic cargo site
caps extended with an odd plane-mixing constant).

**Frozen discrete identity.** Page, orientation (`rot90`), integer page
origin, audited cells, and the authoritative page-cell set never change;
an adopted revision replaces only the continuous window pose, and the
`ColorWindowRefinement` constructor enforces this structurally. Because
color generation zero retains detector outputs rather than raw samples,
the K-style photometric baseline replay is impossible; the color
integrity check is structural (the emitted cells must replay as a subset
of the frozen aligned placement). This is an honest, recorded difference
from K, not an oversight.

**Scope and reuse.** Forward-only — no E024 backward loop, exactly as §7
rules for K. Adoption granularity for reuse is the **region**: the color
detector fit, residual registration, pitch pool, and divisor probe are
all region-scoped (§6), so an adopted pose invalidates its whole
(region, page) fit and window-granularity reuse is not cleanly reachable.
`color_refine.collect_refined_color_evidence` therefore recomputes
exactly the affected regions through the ordinary
`collect_color_evidence` (restricted via the K-parity
`included_patch_ids` seam so each recomputed region replays with its
complete fit population), reuses generation-zero windows verbatim
everywhere else, and reruns the ONE global one-owner freeze over the
merged windows. Byte-equality with a forced full recomputation on the
refined address is the pinned contract, mirroring §7's K reuse
differential. Adopted labels' certificate ids ride
`patch_dependency_overrides` into the rebuilt address product and from
there into window, block, and certificate lineage, exactly as K.

The refinement runs in `ProductionColorPayload` between generation-zero
collection and the owner freeze, emits the same `pose_refine.
window_progress` / `address.final` event family as K (color-named detail
keys; furniture fields replace the pilot fields), and publishes the
refined address as the lane's replacement geometry. Policy identity:
`provisional-v5-pool-law` → `provisional-v6-refine` (spelled in full in
`color_payload.COLOR_PAYLOAD_POLICY_ID`).

Measured standing: synthetic qualification only (perturbed-pose adoption
with certificate non-regression, refusal on held-out regression, reuse
exactness). Whether refinement pays on real color scans — and whether
the frozen per-plane calibration is a good enough detector stand-in on
hardware channels with plane-dependent photometric drift — is unmeasured
until the printer/scanner return (post-08-04).

**Superseded by RECEIVE-DESIGN v0.42 stage C (2026-08-02).** The inline
wiring above (refinement between gen-0 collection and the owner freeze,
the gen-0-merge reuse `collect_refined_color_evidence`, the replacement
geometry on the ordinary barrier) moved into the refinement level R(Lk):
the committed base-lane poses reconstruct through the SHARED
`place.place_committed` audited re-derivation (RECEIVE-DESIGN v0.44; the
short-lived geometry-only rectangle reconstruction crashed the R delta
on partial-coverage scrap and was deleted), pixel-free pre-gates
(no poses / no frontier / every committed span certified) plus the
per-window crop-free gates (`certified_complete` remainder gate + the
certified-cargo gate) decide eligibility, and adoption triggers the
affected-region delta (`affected_color_patch_ids` + the
`included_patch_ids` seam) in the R lane's OWN evidence namespace —
unaffected regions contribute nothing; adopted poses mint under the R
lane id. The adoption gate, frozen discrete identity, labels, and
support ladders above are unchanged and remain normative for the leaf.
Policy identity: `provisional-v6-refine` → `provisional-v7-r-lane` →
`provisional-v8-r-lane` (v0.44 audited committed-pose domain).

---

## 6. Provisional color detector

### 6.1 The selected baseline

The first detector is the current historical `paperholo` color detector,
ported rather than redesigned:

```text
promoted E022 pose + exact word/dust labels + pre-lane certificates
  -> blind-GMM anchor halos
  -> per-plane dot-domain residual registration
  -> registered per-cell RGB features
  -> full-covariance equal-prior QDA
  -> collapse/degeneracy guards
  -> word/dust held-out non-regression gate
  -> codec-specific evidence
```

Its important properties are retained:

- word pilots and dust both contribute labeled states; fully reconstructed
  pre-lane certified cells may add state labels;
- covariance estimates shrink toward a pooled within-class covariance;
- a small trace-scaled ridge makes every class covariance solvable;
- missing/collapsed classes are detected; CMY7 refuses a collapsed joint
  model, while CMY8 erases only the affected component and preserves usable
  sibling planes;
- QDA class priors are flat regardless of the highly unequal training
  counts;
- blind EM does not replace missing furniture labels;
- fits use word plus dust for the eight-state QDA. At the one-tile boundary,
  pooled shrinkage makes the three examples of each missing state usable;
  deterministic sparse-state repair guarantees disjoint train/validation
  representation. This is software-qualified for p120 but remains subject to
  the format's physical qualification gates.

The first policy uses the actually implemented historical default feature
footing: the three registered reflected-channel cell means (`rgb`). It does
not expose the historical manual `rgb+luma` choice or claim the unimplemented
automatic feature search. Feature/model optimization is
post-paper-qualification work.

### 6.2 CMY8 evidence

For CMY8, compute equal-prior eight-state QDA log densities, marginalize
them into three presence-bit scores, then apply the production-corrected
per-level PAVA calibration:

```text
L_C = logsumexp(states with C) - logsumexp(states without C)
L_M = logsumexp(states with M) - logsumexp(states without M)
L_Y = logsumexp(states with Y) - logsumexp(states without Y)
```

PAVA remains in-sample on scores from the same full QDA that will score
payload cells; cross-fitted score axes remain forbidden. Before isotonic
regression, all equal scores are pooled into one indivisible observation.
Each binary class receives equal total weight, independently per C/M/Y
component, so the 2/3-Y dust frequency is not treated as an ink prior. The
result is invariant to label order inside a tie and stores strictly increasing
score nodes. The historical explicit score-zero/probability-0.5 anchor and
`1/(n+2)` finite probability clamp remain.

Calibration rows are dust plus prior-certified complete states (updated
2026-08-02 to the shipped truth; the original "dust only" wording predated
the certificate feedback law): prior-barrier CRC-certified complete-state
payload rows are equally exact labels and join the component PAVA
calibration population — sanctioned by RECEIVE-DESIGN §6.2, policy family
`dust20-priorcert-…` — while the plentiful W/CM address word still neither
enters nor
“balances” a component PAVA map. All 20 dust rows in the region are scored on
the one selected QDA axis and enter PAVA; they are not halved a second time by
the QDA validation split. A component qualifies when both binary classes have
six labels and each class has two nuisance states with at least three labels.
Those floors are exactly met by one p120 base multiset. This estimator
distinction is deliberate; the printed dust schedule is unchanged.

At the final evidence boundary, a plane named by the QDA collapse guard emits
exact-zero LLR. Other planes continue independently. A globally degenerate
QDA emits an all-zero `N×3` result rather than manufacturing evidence from its
pooled stand-ins. An uninformative constant score axis therefore maps to zero,
including the skewed Y labels.

The three calibrated level LLRs are descrambled and delivered independently
to the C, M, and Y LDPC streams.

### 6.3 CMY7 evidence

CMY7 cannot discard joint state information into three marginal LLRs.
Pack7 maps eleven correlated coded bits into four seven-state cells, so its
exact soft demapper needs the seven class scores for each cell.

Use the QDA output **before** CMY8 per-level marginalization/PAVA.
Normalize by the W score:

```text
r_s(z) = log p(z | printed state s)
         - log p(z | printed W),  s in {C,M,CM,Y,CY,MY}
```

Flat class priors are mandatory. A shared per-cell additive constant is
irrelevant and is removed by this representation. The six relative scores
then cross the durable evidence boundary as

```text
r_hat = r / max(1, ||r||_infinity / 20)
```

Thus every one-capture CMY7 component lies in `[-20,+20]`. Scaling is
uniform across all six components of one cell, so it preserves their
pairwise order and every sign relative to W's fixed zero score.
Componentwise saturation is deliberately not used: it would tie distinct
strong color hypotheses and can change the seven-state hard decision. The
exact raw QDA scores remain transient inside the detector adapter.

This is the same historical detector stopped at the output CMY7 requires,
not a new optimized joint calibration. Joint calibration, mixtures, and
context models are deferred. The bound is part of the receiver policy
identity (`cmy7linf20`); changing it is a policy change, not an invisible
numerical tweak.

### 6.4 Shared evidence authority, codec-specific numbers

The durable authority envelope remains common:

```text
source SHA-256
scale lane
physical address
observed/owned cells
origin windows
content identity
row-selected score payload
```

The numerical payload is row-declared:

```text
K       one existing scalar printed LLR
CMY7    six W-relative QDA state scores
CMY8    three tie-pooled, class-balanced marginal/PAVA level LLRs
```

The durable color representation is one compact physical block per
`(source SHA, lane, physical address)`. It contains a bit-packed
observed-cell mask and the row-major values for observed cells only:
`N×6` for CMY7 or `N×3` for CMY8. Origin windows and certificate
dependencies remain attached to the block digest. CMY8 does not copy that
block three times; its C, M, and Y attempt views select columns from the same
physical observation.

Do not assert that these three score families have stronger common
statistics than they do. They share provenance and combination authority,
not a universal calibration law.

Within one physical capture and lane, overlapping windows choose one owner
per physical cell. Distinct physical captures may add compatible evidence
only within the same scale lane. Scale lanes derived from one capture do
not add raw scores; they meet only at certificates. These are the existing
receiver rules and remain load-bearing for color.

Their implementation uses bounded array operations rather than per-cell
Python maps/loops: integer-key alignment within each E022 window, a dense
window-local lookup for the nine neighborhood offsets, stable first-owner
selection over the current page frontier, and provenance comparison batched
by origin window. These are alternative computations of the same row order,
owner priority, and replay checks. Temporary arrays are bounded by the
current window or page frontier, not raster dimensions or session history.

For CMY7 specifically, a same-lane union of `N` source blocks may therefore
reach at most `20*N` in absolute value per stored state component. The union
is the ordinary sum of independently bounded physical observations; it is
  not clipped or renormalized a second time. CMY8 uses the tie-pooled,
  class-balanced PAVA rule above; K retains its existing scalar detector
  bounds and semantics.

---

## 7. CMY7 compound pack7 format

### 7.1 Alphabet and geometry

CMY7 uses states 0 through 6 and never emits state 7 (`CMY`).

At `p120`:

```text
3976 payload cells / 4 = 994 complete packs
994 packs * 11 bits    = 10934 transmitted coded bits
```

The modulation rate is 2.75 coded bits/cell, about 97.96% of
`log2(7)`.

### 7.2 Natural 11-to-4 mapper, version 0

The first and only initial mapper is natural radix:

1. interpret each eleven-bit group as one MSB-first integer `u` in
   `0..2047`;
2. write `u` as four big-endian base-7 digits
   `(s0,s1,s2,s3)`, including leading zeros;
3. render each digit as canonical color state 0 through 6.

Equivalently:

```text
u = s0*7^3 + s1*7^2 + s2*7 + s3
```

Only the first 2,048 of 2,401 four-state tuples are used. The mapping is
injective and cannot emit CMY.

This table is frozen as the provisional `pack7-11x4-v0` semantics and is
generated/tested exhaustively. A balanced or channel-optimized codebook may
become a new row after paper measurements; it does not silently replace v0.

### 7.3 Compound FEC and frame

The selected bank reuses three existing 4096-bit mothers:

| Child | Mother | `k_bits` | Shortened information tail | Transmitted bits | Active information |
|---|---|---:|---:|---:|---:|
| A | `r0550` | 2,240 | 0 | 4,096 | 2,240 |
| B | `r0625` | 2,560 | 677 | 3,419 | 1,883 |
| C | `r0625` | 2,560 | 677 | 3,419 | 1,883 |
| **Total** | | **7,360** | **1,354** | **10,934** | **6,006** |

A/B/C are FEC children, not toner planes.

One shared outer frame occupies all 6,006 active information positions:

```text
[1 metadata bit | 5973 fountain bits | 32 CRC bits]
```

The frame splits contiguously:

```text
A = metadata | fountain[0:2239]
B = fountain[2239:4122]
C = fountain[4122:5973] | CRC32
```

B and C restore their 677 shortened information-tail bits as known zero.
The shared CRC covers the metadata bit and all 5,973 fountain bits using the
same MSB-first byte packing and zero tail padding doctrine as K.

After encoding:

```text
concatenate A/B/C transmitted bits
  -> deterministic compound interleaver
  -> keyed bit dither
  -> consecutive 11-bit groups
  -> pack7-11x4-v0
  -> deterministic payload-cell placement
```

The dither occurs before pack7; therefore every dither outcome still maps
to legal CMY7 states.

### 7.4 Exact soft demapping

For one complete four-cell pack and candidate word `u`, let `s_i(u)` be its
four mapped states and `ell_i(s)` the cell's state score:

```text
metric(u) = sum_i ell_i(s_i(u))
```

For coded bit `j`:

```text
LLR_j =
    logsumexp(metric(u) where bit_j(u)=1)
  - logsumexp(metric(u) where bit_j(u)=0)
```

Only the 2,048 valid mapper inputs participate. A hard observation near one
of the 353 unused tuples is not automatically rejected and is not
automatically weak; confidence follows the valid-candidate likelihood sums.

The implementation computes the same metric table, subtracts one shared
maximum per pack, and reduces normalized candidate weights against all eleven
bit columns at once. The common normalization cancels in every one/zero
log-ratio, so this dense path is mathematically equivalent to eleven separate
log-sum-exp reductions. If an extreme finite input underflows either
normalized partition, that row alone uses the direct log-domain reduction.
The working set is bounded to one tile's pack-by-2,048 candidate table plus
small marginal arrays; no format, evidence, or attempt-policy value changes.

### 7.5 Complete-pack policy

Version 0 uses complete packs only. If any of a pack's four physical cells
lacks admitted owned evidence, the entire pack is an erasure and contributes
neutral evidence for all eleven bits.

There is no projection-cardinality product, partial-pack factor graph, or
attempt to count eleven demapped bits as eleven independent observations.
Before soft demapping, the receiver gives every complete pack eleven
supported positions, scatters that Boolean support through the exact inverse
interleaver, and splits it by child. If A has fewer than 2,240 structurally
supported positions or B/C fewer than 1,883 each, the tile cannot qualify and
the demapper is not run. This is a necessary cost gate, not evidence and not
decoder authority.

Only a structurally eligible tile is soft-demapped, exactly once. The
receiver applies inverse dither/interleaving, splits that exact LLR vector by
each child's transmitted width, and independently requires 2,240/1,883/1,883
**actual nonzero** LLRs. This post-demap floor remains authoritative, and the
same vector is passed to the decoder only when all three floors hold. The
former scalar `complete_packs*11 >= 6006` approximation is not equivalent to
either per-child gate and is not used.

This conservative rule gives up some torn-fragment evidence in exchange for
an exact, easy-to-audit baseline. Partial packs are a later measured
optimization.

### 7.6 Decode, certification, and retry

CMY7 is one logical stream, `main`.

For each newly contributed physical block, the scheduler first forms a
`scan` view from that block alone. If the address has at least two retained
same-lane source blocks, it then forms one canonical `union` view from the
complete same-lane frontier. Each eligible view performs this ordinary
attempt:

1. inverse-interleaves complete-pack support and applies the necessary
   per-child structural gate;
2. if structurally eligible, soft-demaps every complete pack exactly once;
3. removes dither, inverts the compound interleaver, and applies the
   authoritative per-child actual-nonzero floor;
4. restores child shortening;
5. runs all three BP decoders at `max60`;
6. checks the shared CRC only if all three syndromes pass;
7. issues one certificate only if that CRC passes.

Child syndrome success has no independent metadata or fountain authority.
No partial child certificate or durable partial-child state exists.

After ordinary processing, only the latest eligible `scan`/`union` view
whose BP60 attempt actually failed enters the hardwired `retry150` frontier.
Below-floor views and already-certified work do not. BP150 reuses exactly
the parent's compact block IDs and certificate dependencies and reruns the
**whole three-child bank**, not merely a failed child. It checks the shared
CRC at most once if all retry syndromes pass. `retry150` is a distinct
ledger/provenance stage for audit, cost accounting, and idempotence; it is
not a user-facing policy choice.

One committed CMY7 certificate reconstructs the complete three-plane
printed tile for a subsequent lane/capture's refinement and divergence
checks.

---

## 8. CMY8 level-stratified format

### 8.1 Direct presence mapping

Every payload cell directly carries one coded bit from each level:

```text
C-presence code bit
M-presence code bit
Y-presence code bit
        -> one state in 0..7
```

All eight combinations are legal. Each stream has its own deterministic
payload-bit dither. Every one of the 120 furniture cells is shortened in
all three codes, leaving 3,976 transmitted positions per stream.

The initial historical rate tuple is:

```text
C -> r0550
M -> r0550
Y -> r0547
```

`r0547` and `r0550` currently have the same `k_bits=2240` but distinct
frozen graphs. At `p120`, each stream therefore has:

```text
active information = 2240 - 120 = 2120 bits
outer user bits     = 2120 - 32 CRC = 2088 bits
fountain symbol     = 2088 - 1 metadata = 2087 bits
```

The tuple is provisional and is identical at c2 and c3 for the first
software rows. Changing a rung later creates a different explicit row.

### 8.2 Independent stream certificates

Each stream frames and certifies:

```text
[same addressed metadata equation bit | 2087-bit fountain symbol | CRC32]
```

C, M, and Y decode independently. One physical tile may therefore produce
zero, one, two, or three immediately useful certificates:

```text
(physical address, stream=C|M|Y, certified user bits)
```

There is no fourth bundle CRC and no all-three prerequisite. A same-key
different-value certificate is integrity-fatal. Different streams at the
same address are ordinary distinct symbols.

A stream certificate reconstructs only its own printed component. Once
committed, it may support component-masked refinement in a subsequent
lane/capture while its siblings remain unresolved.

### 8.3 Common metadata `K`, common `q`

CMY8 uses the current addressed metadata word and one common fountain
source-symbol count `K`. Every stream carries the same metadata equation at
a physical counter. Agreeing copies improve consistency but do not add
linear rank; an opposite certified copy is an integrity conflict.

Generation also uses one common source fraction `q` for all three streams.
There is no per-plane user policy or planner search.

Given fountain symbol widths `S_C`, `S_M`, and `S_Y`, map the encoded
envelope as follows:

1. compute
   `K = ceil(envelope_bits / (S_C + S_M + S_Y))`;
2. append canonical zero padding to exactly
   `K*(S_C + S_M + S_Y)` bits;
3. take the first `K*S_C` bits as C, the next `K*S_M` as M, and the last
   `K*S_Y` as Y;
4. reshape each stream-major slice into `K` source symbols;
5. fountain-code each stream independently with stream-domain-separated
   rows and block assignments.

Boundaries are exact bit boundaries, not rounded bytes. Reassembly is the
inverse C-then-M-then-Y concatenation followed by the existing envelope
length, SHA-256, and canonical-padding gates.

The physical counter remains the ESI within each stream. It is never
flattened with the level. If `B = ceil(K/16384)` is the number of fountain
blocks per stream, planning uses the three-stream rank reserve
`16 + ceil(log2(3*B))` per block so the existing approximate `2^-16`
whole-volume union-bound footing covers all `3*B` blocks. Page feasibility
must hold for all three streams at the one selected `q`; `K` is not inflated
to search around a failed page plan.

This is deliberately simple. Bit striping, different `K` values, different
`q` values, and pooled ESI numbering are not part of the format.

### 8.4 Decode and retry

The three corrected marginal/PAVA LLR vectors feed their corresponding
binary LDPCs. For each new physical block, each unresolved stream is tried
on the block's `scan` view and, when present, the complete same-lane
`union` view. Eligibility, ordinary BP60, CRC invocation, certificate, and
work suppression are evaluated per unresolved stream.

Eligibility counts actual nonzero LLR support in the selected observed
component, not merely observed physical cells. A stream runs only when that
count reaches its FEC child's active-information count. Thus an exact-zero
collapsed plane remains a true erasure and cannot spend BP or reach CRC by
inflating a physical-cell count; C, M, and Y make this decision independently.

After ordinary processing in a lane, the latest eligible failed
`scan`/`union` view for each still-unresolved stream is hardwired through
BP150 as its own `retry150` stage. The retry reuses the exact parent block
set and dependencies. Successful C suppresses later C work at that address
but does not suppress M or Y. Each retry is distinct ledger provenance and
is idempotent.

### 8.5 Close and integrity meaning

Metadata and fountain ingest are stream-qualified; physical counters are
not flattened to `3*counter+level`. Verified close requires all three source
streams to solve, exact stream-major reassembly, and the existing envelope
verification.

`VolumePlan.n_repair` is `N-K` for each logical stream. The multistream
capacity CLI therefore reports `n_repair_symbols_per_stream`, not “repair
tiles.” CMY8 block assignment is stream-domain-separated, so one physical
tile address can be systematic in one stream and repair in another; there is
no single source/repair label for that physical tile.

As in K, verified close certifies reconstructed content. It does not prove
that every nonoverlapping retained repair equation came from one physical
sheet. A stronger volume authenticator would be a different archive-format
property, not a color-specific patch.

---

## 9. Generation and emission

### 9.1 Composition boundary

The outer generator owns:

```text
envelope -> metadata/fountain stream set -> physical tile addresses
```

The selected row then calls one numerical leaf:

- K keeps its existing composer and binary slot/word behavior;
- CMY7 invokes the compound frame/FEC, pack7 mapper, and color furniture;
- CMY8 invokes the three stream frames/FECs, direct presence mapper, and
  color furniture.

All leaves return a canonical page state/presence field plus renderer
identity. Sharing the outer page loop does not justify rewriting K's exact
inner composition.

### 9.2 Color rendering

Both color modulations render one composite DeviceCMYK image whose K samples
are zero. The emission contract pins:

- canonical C/M/Y sample order;
- top-left raster convention and image matrix;
- row packing and padding;
- 600-dpi hardware resolution;
- composite path identity;
- overprint/OPM behavior;
- absence of RGB/JPEG substitution.

The current K `imagemask` operation and its output bytes remain unchanged.
Sequential plane overprint is not an interchangeable fallback; if ever
qualified, it is a distinct row/emission identity.

The implementation may copy and adapt the historical `paperholo`
DeviceCMYK operation, but production Holo does not import `paperholo`.

---

## 10. Shared outer receiver semantics

### 10.1 Attempts and certificates

Attempts and certificates are keyed by:

```text
(physical address, stream_id, stage, evidence selection)
```

K and CMY7 use `main`. CMY8 uses C/M/Y. The row derives FEC profile,
shortening, symbol width, and expected child structure; those facts are not
persisted redundantly in every record.

Attempt selection is physical-first and deterministic:

```text
new source block alone                     -> scan / BP60
complete retained same-lane source set     -> union / BP60
latest eligible failed ordinary work view  -> retry150 / BP150
```

Attempt identity includes the canonical compact-block selection. A retry
must name exactly the same block IDs and certificate dependencies as its
ordinary parent. This makes repeated scheduling a no-op without a persisted
policy flag.

Color close is scheduled at two deliberate points, not after each
certificate:

```text
complete scan+union batch
  -> if new certificates and count-ready: one advisory pre-BP150 close
  -> terminal: skip retry150
  -> open/not-ready: selective retry150
completed lane barrier
  -> authoritative close and durable state transition
```

The pure count-ready gate first recovers metadata. Incomplete metadata cannot
preclose; malformed, unsupported, or inconsistent terminal metadata is passed
to full close so its exact terminal result is materialized. With a valid `K`,
every logical stream needs at least `K` distinct certified ESIs. If the volume
has multiple fountain blocks, the authoritative row/stream block mapping must
also have at least `K_b` ESIs in every block. These are necessary conditions
only: generator rank, reassembly, padding, payload length, and envelope SHA
remain decisions of full close. There is at most one advisory preclose per
lane, no per-certificate close, and no close inside retry150. Diagnostics
report `color.preclose_attempted`; `color.terminal_close` means that advisory
close returned a non-open result.

CRC exposure accounting follows actual invocations:

```text
K ordinary/retry attempt      0 or 1
CMY7 whole-bank attempt       0 or 1
CMY8 stream attempt           0 or 1
CMY8 physical lane/address    0 through 3 per stage
```

LDPC syndrome checks are not CRC exposures. CMY7's three BP decoders still
lead to at most one shared CRC invocation. Diagnostics report BP work and
CRC exposure separately from physical tile counts.

### 10.2 Evidence and lane isolation

The cleaned receiver rules remain:

- a scan is identified by SHA-256; byte-identical ingest is refused/no-op
  according to the existing command contract;
- overlapping placements within a source/lane resolve to one owner per
  physical cell;
- repeated physical scans remain distinct evidence;
- compatible evidence may combine only within the same scale lane;
- raw numerical evidence never crosses lanes;
- certificates, not raw scores, are the cross-lane authority.

External decimation is neither needed nor treated as a special evidence
group. Operators should supply the original scan; Holo creates its own
deterministic lanes.

### 10.3 Certified work suppression

Work suppression uses `(physical address, stream_id)`:

- a K or CMY7 certificate resolves `main`;
- a CMY8 C certificate resolves only C;
- shared multistate source evidence remains available to unresolved CMY8
  siblings;
- unresolved entries remain in the need map;
- while a color session is open, numerical evidence becomes
  retirement-eligible only when every required stream at that address is
  certified under the existing retirement rule.

Thus one CMY8 certificate does not retire the physical block needed by its
siblings while more receiver work remains. The block is retained once, not
copied per stream, until C, M, and Y at that address are all certified.

Terminal close changes no evidence-retention policy. Color now follows the
ordinary K-like per-address live-frontier rule before and after close: blocks
for fully certified work retire at ordinary barriers; unresolved baseline
blocks remain. This is useful for provisional inspection and removes a
color-only lifecycle branch, but it is not full numerical history—normally
retired certified-address bodies are still gone. A terminal result still
suppresses all further decoding, so retained unresolved CMY8 siblings do not
provoke gratuitous BP or CRC work.

Committed diagnostics display those ordinary upserts and per-address
retirements. There is no terminal-only `retire_all_payload_blocks` operation
and no format-specific global-wipe policy for an observer to reproduce.

### 10.4 Discovery

Every exact row hypothesis owns the same kind of isolated session branch.
Recognition and branch status derive from certificates and conflicts; they
are not separately persisted.

The catalog and default candidate set are distinct:

- all four color rows are registered/resolvable and may be explicitly
  selected;
- none enters default cold discovery before its complete paper
  qualification and aggregate false-accept accounting pass;
- merely registering a color row must not enlarge the default K trial set.

A certified result in two incompatible exact-row branches is an integrity
failure under the existing discovery doctrine.

### 10.5 Durable state

There is one current state architecture (receiver schema 19) and no
compatibility loader for earlier development schemas. Persist causal facts
only:

- source/lane/address-owned evidence with row-declared numerical payload;
- flat stream-qualified attempts including stage, evidence dependencies,
  ordered child outcomes where applicable, and nullable CRC result;
- minimal stream-qualified certificates containing certified user bits and
  origin dependencies; and
- non-gating generic divergence counts keyed by certificate and published
  compact block.

Counter, capacity, rate tuple, progress, retry frontier, metadata rank,
fountain rank, and status derive from the exact row and committed facts.
Detector fits, registration models, and diagnostics are operational
derivations, not new persistent authorities.

Replay validates evidence kind/arity and digests, attempt block selection,
stream/stage identities, child outcomes, CRC exposure, certificate lineage,
same-stream conflicts, and the all-required-stream per-address retention rule
before reconstructing the live frontier. Terminal and open states obey the
same rule; a terminal color state may retain unresolved numerical blocks.
When a referenced color block remains live, replay also reconstructs its
divergence exactly. CMY8 compares the named certificate stream's expected
component with the sign of that block's C/M/Y column. CMY7 compares the
exact reconstructed seven-state tile with
`argmax([W=0, C..MY relative scores])`. Once ordinary retirement removes a
block body, only the existing content identity and causal
certificate/block reference remain replayable; divergence is diagnostic and
never gates a certificate or close.
Close converts each certified record through its row/stream profile, solves
one fountain instance per declared stream, checks that repeated metadata
equations agree, and applies the row's deterministic stream reassembly before
ordinary envelope verification.

Public save (with its default validation) and every public load of a
registered row now add format-bound checks to generic graph replay: exact
scale plans and page domains, BCH-conflict addresses, payload-site legality,
attempt iteration/policy facts, certificate identities, and exact close
reproduction from the certified frontier. Runtime barrier persistence may
skip that full pass only after its synchronized index has incrementally
validated the delta. Opaque unregistered diagnostic labels retain structural
validation only.

The atomic mutation boundary remains one completed source/lane barrier.
Processors return products; runtime validates and commits them. Color does
not move commit authority into the scheduler or detector.

---

## 11. Format identity and random domains

A color row freezes:

```text
cell size
p120 family and row seed
alphabet/state order
dust value schedule
mapper and mapper version
FEC child tuple and shortening
frame/CRC semantics
interleaving, dither, and placement
stream set and fountain domains
renderer/emission identity
page geometry
```

Wrong K/color, CMY7/CMY8, c2/c3, geometry, or seed hypotheses are expected
to cross-reject probabilistically through row-specific word scrambling and
the BCH/pad gate. “Always fail” is not claimed; every new row must pass the
registered null and pairwise cross-rejection budget.

K random domains and vectors remain exact. Color receives new,
domain-separated draws for:

- dust state values;
- CMY7 code-bit interleaving and dither;
- CMY7 state placement where needed;
- CMY8 C/M/Y payload dithers;
- CMY8 stream-qualified fountain rows and block assignment.

The final domain-byte allocations and golden vectors are frozen by the
implementation and become row identity. No generic string-labeled random
service is introduced.

The fountain selector is deliberately explicit because both K and CMY7 use
the logical stream name `main`. K selects no color auxiliary and therefore
retains domains 7/8. A color stream supplies both its semantic stream ID and
its frozen auxiliary (`main=0`, `C=1`, `M=2`, `Y=3`) and therefore uses
domains 14/15. A name alone is not allowed to select the numerical domain.

---

## 12. Qualification contract

The playbook owns test placement and implementation order. The design owns
these promotion conditions.

### 12.1 K non-regression

For existing K rows:

- format/seed/family and LDPC goldens remain exact;
- composed cells and PostScript bytes remain exact;
- identical admitted evidence produces identical scalar values and decode
  results;
- metadata/fountain/certificate/conflict/verified-close transcripts remain
  semantically exact;
- default discovery candidates and trial accounting remain unchanged; a
  printer/geometry hint may remap only those default rows and must never
  promote catalog-only color candidates;
- the full current suite passes.

No color convenience is allowed to weaken these gates.

### 12.2 Pure codec tests

CMY7 must prove:

- all 2,048 mapper inputs round-trip and none emits state 7;
- every payload tile has exactly 994 complete packs and 10,934 coded bits;
- child shortening/frame splits and shared CRC match frozen vectors;
- exact soft demapping matches a brute-force oracle;
- incomplete packs erase all eleven outputs;
- a per-child structural shortage after inverse interleaving refuses before
  the soft demapper, while passing that necessary gate does not bypass the
  actual post-demap nonzero floor;
- no certificate appears without all three syndromes and the one CRC;
- both `max60` and whole-bank `retry150` are deterministic and idempotent;
- certified re-encoding reproduces all three presence planes.

CMY8 must prove:

- all eight states map exhaustively to C/M/Y presence;
- each stream shortens exactly 120 positions and round-trips independently;
- stream-major common-`K` slicing/reassembly is bit-exact at every
  non-byte-aligned boundary;
- same-address sibling failures do not suppress a successful stream;
- per-stream `max60`/`retry150`, conflicts, and certificates are exact;
- one stream re-encodes only its known component and all three reconstruct
  the complete tile.

### 12.3 Synthetic receiver data

Tests require deterministic synthetic RGB observations that can express:

- all seven/eight state class means and covariances;
- one shared affine plus independently chosen C/M/Y offsets and
  linear-in-page-Y drift;
- c2 and c3 area decimation at every real lane scale;
- class collapse, a missing/weak plane, unequal noise, erasures, folds,
  clipped crops, and partial tiles;
- independent rescans versus correlated scale lanes;
- locked and contradictory BCH words;
- furniture/certified-label train/validation splits.

The synthetic oracle must expose printed states, physical planes, addresses,
and geometry separately so a fake detector or fake word provider can test
one subsystem without circularly invoking the implementation under test.
Synthetic green tests validate plumbing and mathematics, not paper
qualification.

Printer/scanner distortion is deliberately outside the generator, receiver,
and synthetic-oracle machinery. The standalone transformer has one narrow
contract:

- input: one single-frame, 600-dpi RGB TIFF;
- output: one RGB TIFF at 1200 or 4800 dpi;
- operation: an optional deterministic seed (zero by default), optional
  profile shortcut, and optional explicit transform parameters;
- publication: refuse overwrite and publish only the completed TIFF;
- dependencies: no Ghostscript invocation, generator, receiver, corpus
  builder, manifest, or sidecar.

With no `--profile`, all synthetic parameters start at identity and only the
explicitly named effects apply. With no explicit effects either, the tool
only performs the requested scan-density resampling:

```console
PYTHONPATH=src env/bin/python -m holo.qualification.color_distort \
  INPUT-r600.tif OUTPUT-r4800.tif \
  --seed 1234 --output-dpi 4800 \
  --shear 0.001 -0.0005 --blur 0.2 --noise-rgb 1.0 1.5 2.0
```

`nominal` and `stress` are optional shortcuts for complete deterministic
synthetic parameter sets, not mandatory bases and not printer or scanner
identities:

```console
PYTHONPATH=src env/bin/python -m holo.qualification.color_distort \
  INPUT-r600.tif OUTPUT-r4800.tif \
  --profile nominal --seed 1234 --output-dpi 4800
```

Each shortcut includes source-space dropout/speckle, centered affine shear
and translation, margin/crop, blur, and RGB sensor noise. The caller may
override individual shortcut values with `--shear`, `--translate`,
`--margin`, `--crop`, `--dropout`, `--speckle`, `--speckle-rgb`, `--blur`,
and `--noise-rgb`. Without a shortcut those same flags enable only their
named effects. Geometric and blur values are expressed in 600-dpi
printer-dot coordinates before the result is resampled to the selected scan
density.

The same TIFF-only command exposes the one already-characterized historical
simulation as a profile (since 2026-08-02 split into a color and a K-only
variant; `hp-m281-flatbed-k` takes a black/white page through the same
pair's bit-faithful single-plane imagemask path and emits grayscale):

```console
PYTHONPATH=src env/bin/python -m holo.qualification.color_distort \
  INPUT-r600.tif OUTPUT-r1200.tif \
  --profile hp-m281-flatbed-cmy --seed 17 --output-dpi 1200
```

The `hp-m281-flatbed-cmy` shortcut is deliberately narrow and mutually
exclusive with the explicit synthetic effects. It accepts a clean,
threshold-separable C/M/Y palette from the input TIFF, recovers the three
binary presence planes, and passes them to the existing
`paperholo.channel.simulator` M281 + M281-flatbed CAL-1 path. It does not
infer physical colorants from an already-degraded observation, copy device
constants, introduce a new device model, or consult the receiver's device
registry. Its output is fixed at 1200 dpi. The inherited simulator is
non-streaming and can require several GiB for a full page.

The synthetic and characterized profiles must not be stacked. The measured
simulator already composes development, re-screening, per-plane PSF and
registration, shared printer wander, scanner transport and scale, density
crosstalk, and sensor noise; applying `nominal` or `stress` as a second pass
would double-count several channel effects. AltaLink and Canon observations
do not yet form complete simulator parameter sets and therefore have no
corresponding profile.

“Measured” here is bounded by the historical model's own record. Its frozen
scanner parameters do not include the 11.3-pixel comb later observed in the
M281 home-flatbed COLOR mode, which E017.4 found acquisition-breaking, and
its per-level reliability order differs from hardware. The tool records
no separate metadata file; these limitations belong in qualification
documentation. Its output is useful adversarial material, not a claim that
this is a usable M281 color acquisition footing.

The historical compact record
[`COLOR-M281-CAL1-QUALIFICATION.json`](COLOR-M281-CAL1-QUALIFICATION.json)
retains a full-page operational outcome from the former orchestration. Its
generated image passed the TIFF and receiver-ingest seams, but the receiver
found no pose, attempt, certificate, or payload block and remained open. It
shows that the then-current bridge ran; it neither describes current tool
output nor qualifies M281/CAL-1 acquisition.

### 12.4 Receiver, replay, and diagnostics

The four rows must pass:

- all-120-site binary-luma placement projection, with the `>=2`-ink dust
  split, and 100-word-site-only BCH authority;
- BCH quarantine that blocks every downstream color artifact;
- exact word/dust plus pre-lane-certificate projection;
- blind-GMM halo anchor extraction, dot-domain C/M/Y residual fitting, and
  held-out word/dust non-regression;
- tie-pooled, label-order-invariant, class-balanced CMY8 PAVA with exact
  constant-score neutrality and independent collapsed-plane erasure;
- bounded per-window K/RGB sampling whose region-wide numerical result matches
  the single-window reference without a multi-window union allocation;
- necessary inverse-interleaved per-child CMY7 complete-pack pre-gating,
  followed by the authoritative per-child post-demapper nonzero-support
  floor; per-plane CMY8 nonzero-support floors;
- lane-local evidence combination and cross-lane refusal;
- crash/resume at every lane barrier;
- exact duplicate ingest/no-op behavior;
- stream-qualified attempt, retry, CRC, conflict, and certificate replay;
- count-gated advisory pre-BP150 close, selective retry when still open, and
  authoritative post-BP150 barrier close;
- ordinary per-address compact-block retention before and after terminal close;
- registered-row public save/load format checks and close reproduction;
- CMY8 partial-stream progress across scans;
- catalog-only explicit discovery with unchanged default K candidates;
- operational diagrams that distinguish physical tiles, streams, BP calls,
  CRC exposures, quarantined placements, and refinement generations without
  persisting those summaries.

### 12.5 Emission and paper qualification

Before any promotion:

- Ghostscript plane-separated rendering must reproduce authored C/M/Y
  planes;
- the actual print path must remain composite DeviceCMYK;
- each `(engine, modulation, cell size, emission path, scanner footing)`
  must pass pilot/address, dust/registration, uncoded state, coded coupon,
  blind page, multi-page verified close, repeated session, and
  fragment/replacement tests;
- rate and detector decisions must use the same channel/footing as the
  coded page;
- aggregate default-discovery false-accept cost must be re-evaluated.

The emission item has a dedicated, opt-in Q1 software gate for all four
current rows. It inspects each complete production page, compares every
addressed C/M/Y dot with the packed generator truth, rejects marks in the
surrounding page margins, requires the entire K plate to be empty, and pins
the clean composite RGB palette and threshold recovery consumed by the
`hp-m281-flatbed-cmy` profile:

```console
HOLO_RUN_GS_COLOR_SEPARATIONS=1 PYTHONPATH=src env/bin/pytest -q \
  tests/holo/test_color_software_qualification.py -k q1
```

This proves the software emission seam, not the printer transport, toner,
paper, or scanner channel.

The complete current software composition has a second slow, opt-in gate:

```console
HOLO_RUN_GS_COLOR_RECEIVER=1 PYTHONPATH=src env/bin/pytest -q \
  tests/holo/test_color_software_qualification.py \
  -k closes_through_standalone_tiff_transformer
```

For each row it performs production generation, Ghostscript `tiff24nc`,
the standalone TIFF command with the `nominal` profile, the real receiver
CLI, byte-exact payload comparison, and strict registered-row reload. This is
test-local composition, not a restored corpus package, builder, corpus
manifest layer, or production distortion path.

Until then, “CMY7-c2 works” or “CMY8-c3 works” means software/synthetic
operation only.

---

## 13. Alternatives and deferred optimization

### 13.1 CMY8 everywhere

Rejected as the only format. The M281 CMY-triple failure directly motivates
the triple-free alternative.

### 13.2 CMY7 everywhere

Rejected as the only format. It discards a useful AltaLink state and adds
more demapper/FEC complexity where direct CMY8 works.

### 13.3 Seven states as unconstrained three-bit cells

Rejected. Independent binary C/M/Y codewords produce `111`; an ordinary
binary LDPC cannot guarantee that the forbidden state is absent. Pack7 is
the constraint code between binary FEC and physical cells.

### 13.4 Hard base-7 decoding

Rejected. A state error can fan out into many wrong bits and discards the
soft likelihoods needed by LDPC.

### 13.5 Partial CMY7 packs

Deferred. Projection-cardinality and factor-graph approaches can recover
some torn-pack information, but they complicate eligibility and accounting.
The complete-pack baseline is correct and measurable.

### 13.6 Balanced or learned pack7 table

Deferred as a new mapper row. Natural radix is not claimed optimal; it is
selected because it is complete, exact, and easy to audit before paper
data exists.

### 13.7 Connected CMY7 code

Deferred. A connected code near 10,934 transmitted bits may outperform the
three-child block-diagonal bank, but requires a new graph, decoder-size
qualification, and waterfall. The current compound bank reuses frozen
primitives and isolates the new risk.

### 13.8 Bundled CMY8 certificate

Rejected. It would delay useful C/M/Y progress until all three decode,
discard the measured benefit of unequal level reliability, and require a
different outer frame. Three independently CRC-certified streams do not
need a fourth CRC.

### 13.9 Automatic detector optimization

Deferred until after paper qualification. Feature selection, mixture
models, context correction, joint CMY7 calibration, successive CMY8
decoding, and better registration fields can all be compared later against
the deliberately historical baseline.

### 13.10 Independent per-plane page poses

Rejected for the first implementation. Shared sheet geometry plus residual
plane registration models printer physics more honestly and has fewer
degrees of freedom. A richer field must demonstrate held-out paper gain.

---

## 14. Final disposition

Implemented provisionally now:

- all four CMY7/CMY8 × c2/c3 rows;
- catalog-only color discovery until paper qualification;
- one shared outer generator/receiver authority;
- explicit K, CMY7, and CMY8 numerical leaves;
- exact preservation of K physical and numerical behavior;
- `p120`: 100 W/CM word sites plus 20 deterministic dust sites;
- shared E021/E022 binary-luma reference over word and dust sites, with
  dust dark exactly at two-or-more present ink components, while the
  100-site BCH word alone grants address authority;
- quarantine of every placement contributing to a BCH contradiction and
  complete downstream gating of quarantined evidence;
- RGB area decimation at every existing color scale lane, with no second
  scheduler;
- direct-native, per-channel RGB lane derivation and aligned luma;
- transient per-E022-window K/RGB payload crops and local anchor/corrected-point
  footprints, with region-wide fits over retained samples rather than a union
  raster;
- one shared E022 pose plus dot-domain C/M/Y residual registration per lane,
  using blind-GMM 3×3 halos and exact known-component overrides;
- pilot-word, dust, and eligible pre-lane certified cells used for
  registration/training, with held-out word/dust non-regression;
- the historical `paperholo` QDA detector as the provisional baseline;
- tie-pooled, class-balanced dust PAVA for CMY8 without changing the printed
  dust schedule, with exact-zero independent collapsed-plane evidence;
- pre-PAVA seven-state QDA evidence for CMY7, uniformly L-infinity-bounded
  to 20 per physical observation at the durable adapter boundary;
- per-lane color refinement using certified known-component masks;
- one compact physical color evidence block shared by the row's logical
  streams;
- natural-radix CMY7 `11 -> 4` mapper v0, complete packs only, one shared
  frame/CRC, necessary inverse-interleaved per-child structural pre-gating,
  authoritative per-child post-demapper nonzero floors, scan/union BP60,
  and whole-bank selective BP150;
- CMY8 independent C/M/Y certificates with common metadata `K`, common
  `q`, C-then-M-then-Y stream-major envelope slicing, and per-stream
  actual-nonzero eligibility, scan/union BP60, and selective BP150;
- one necessary-only metadata/per-stream/per-block count-gated pre-BP150 close
  plus the authoritative post-BP150 barrier close;
- stream-aware current-schema replay, ordinary K-like per-address evidence
  retention across terminal close, registered-row public validation, and
  per-stream fountain close;
- stable codec-ID dispatch at generator/attempt leaves and repair-symbols-
  per-stream reporting for multistream plans;
- the standalone deterministic TIFF distortion tool;
- the lean opt-in all-four generator/GS/TIFF-CLI/receiver/reload gate, with
  the former corpus subsystem still absent;
- composite DeviceCMYK emission;
- no old-state compatibility machinery.

Still provisional and changeable only through a new explicit row/policy
after evidence:

- color rate rungs and c2 viability;
- dust sufficiency;
- detector features/calibration;
- registration model richness;
- optimized pack7 tables or partial-pack decoding;
- connected/native FEC profiles;
- admission to default discovery.

The governing design statement is:

> CMY7 and CMY8 are full Holo formats, not experiment-side attachments.
> They share K's archive authority, lifecycle, and operational model while
> retaining the channel mathematics their physical alphabets require. That
> boundary gives color equal standing without putting the existing K
> detector, codec, or renderer at unnecessary risk.
