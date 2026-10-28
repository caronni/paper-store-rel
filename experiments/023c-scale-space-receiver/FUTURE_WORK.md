# E023c — future work

Recorded 2026-07-17 from the production cascade design, live C2/HP-1200
diagnostics, and completed original/offset two-capture run.  The normative
current receiver contract remains [DESIGN.md](DESIGN.md); this file is the
ranked architecture and performance backlog, not a commitment schedule or a
license to weaken current-pixel, held-out, certificate, or provenance gates.

## Placement search scheduling (E022; observed through E023c C2)

**Status:** acquisition/placement-axis future work, recorded 2026-07-17
from the live E023c C2/HP-1200 offset run, its diagnostic sidecars, and
read-only replay of the original and offset C2 coarse states.  This is a
ranked design and measurement plan, not the current E022 contract and not a
claim that scheduling can repair genuinely bad pixels.

### Problem statement

Current E022 is only superficially easy-first.  Primary windows are ordered
by support and scan position and failed children go to the tail, but each
window exhausts every route before the next window begins:

1. all accepted non-redundant same-level anchors, in insertion order;
2. bounded, physically ranked lower-scale hints;
3. BCH address recovery;
4. full-page pilot correlation;
5. only after failure, subdivision into four children.

Earlier failures are not retried when a useful anchor later arrives from
another direction.  A fully gated `redundant_skipped` placement is retained
for payload sampling but deliberately cannot relay geometry.  Consequently
the current process is a temporal one-way anchor walk, not a spatial
frontier, and a failed window becomes *more* expensive as the anchor list
grows.

Pane C is not a correctness-safe crop.  It shows pilot observation state,
not local-pose completeness or LDPC certification.  The seed-derived pilot
field was already known everywhere; a pilot-redundant placement can still
provide the best pose for payload cells.  The safe objective is therefore
to avoid or postpone implausible **address search**, not to erase scan-space
windows merely because their pilots are green.

### Measured trigger

At 2 ppc in the C2 HP scans:

| capture | coarse windows | chain time | BCH time | full correlations | correlation time | post-seed correlation accepts |
|---|---:|---:|---:|---:|---:|---:|
| original | 486 | 68.7 s | 46.5 s | 71 | 95.6 s | 0 |
| offset | 554 | 109.6 s | 69.4 s | 128 | 170.7 s | 0 |

The live offset barrier is especially diagnostic.  Primary windows 170–180
are one complete scan row at `y=4800`; the accepted-anchor count remains
139 while all eleven windows run chain → BCH → full correlation, take
about 3.12 seconds each, and refuse.  Their 44 depth-1 children run later;
36 place by cheap chain, seven remain unresolved, and one refuses pose.
The useful operation was subdivision, not proving eleven times that no
unrelated page address could repair the weak pixels.

Other read-only measurements:

- The nearest earlier accepted anchor reproduces all 390 original and all
  405 offset successful coarse chain placements.
- Retrying failed primaries against later successful anchors recovers 0/48
  original and 0/64 offset.  Easy-first scheduling should save work and
  expose useful children sooner; it must not be advertised as evidence
  recovery for these particular weak parents.
- Failed-anchor walks evaluate heavily overlapping 7×7 local grids.  The
  original's 678,356 `_score_known` probes contain only 38,167 unique
  `(page, rotation, origin)` candidates; the offset's 1,427,419 contain only
  58,352.  Per-window memoization can remove 94–96% of these evaluations
  without changing anchor order or decisions.
- `_pending_masks` currently copies the full 3300×2220 pilot-site bitmap and
  replays all accumulated observations for every pose-fitted window.  A
  completed-state rebuild costs about 0.1–0.2 seconds; accumulated cost is
  estimated at roughly 30 seconds original and 50 seconds offset.  It is
  bookkeeping that becomes slower as pane C fills, yet is used only to mark
  a successful placement redundant.

The browser's throttled frames over-represent slow windows: easy chains can
finish in 0.08–0.13 seconds and disappear between frames.  That observer
bias does not change the measured route costs above.

### Proposed progression

#### A. Exact, semantics-preserving cost removal

1. Maintain one incremental pending-pilot bitmap and clear sites as
   observations are emitted; do not reconstruct it per window.
2. Memoize `_score_known` within one window by
   `(page, rotation, origin, parity)`.  Preserve present anchor order, ties,
   gates, and floating results exactly.

These are the first implementation candidates because they should change
only timing.  Exact result/state parity is the acceptance gate.

#### B. Spatial easy frontier and deferred hard search

1. On first visit, fit/sample a window once and retain that immutable
   current-pixel substrate for any scheduled retry.
2. Establish one trusted seed from a lower hint, BCH, or, only when needed,
   full-page correlation.
3. Put spatial neighbours of each trusted placement on a deterministic
   frontier.  Try the nearest same-level geometry nodes first, then bounded
   lower hints, then a small component-diverse same-level portfolio.
4. A success wakes pending windows in every direction.  A refusal is
   deferred and is retried only after a genuinely new nearby geometry node
   appears.
5. When trusted local predictions agree on address but current pixels fail
   mismatch/validation, subdivide before blind whole-page search.  A
   different address cannot repair weak or straddled pixels.
6. When the cheap frontier reaches a fixed point, choose one strong deferred
   child to BCH/full-correlate as the seed of an unserved spatial component,
   then resume the cheap frontier.
7. If exhaustive semantics are requested, hard-backfill the residual by
   spatial cluster after the wave.  A parent whose children already cover
   its useful core need not be independently correlated.

Full-page correlation thereby becomes a **component seeder**, not a
per-window fallback.  Propagation remains within an E021 region: disconnected
scraps can have arbitrary platen-relative positions.  Cross-scale hints are
separate and retain their present same-capture/current-pixel gates.

#### C. Separate geometry relay from pilot contribution

Maintain two roles:

- **geometry nodes:** every fully gated and straddle-audited placement,
  including a pilot-redundant one;
- **pilot contributors:** only placements that add previously unobserved
  pilot sites.

A redundant node emits no duplicate pilot vote and does not increment the
pilot-accepted count, but it may relay its authenticated pose/address to a
neighbour.  This prevents the geometric waterfall from stopping precisely
when pilot coverage becomes full.  Spatial ranking/bounds are required so
the relay set does not recreate the present unbounded anchor walk.

Initially, an unaccepted address candidate must not recursively mint a
geometry node.  Trusted nodes can jump over one failed neighbour and the
destination still has to pass its own current-pixel search/validation gates.
Only if measurements show this insufficient should a separate arm test a
one-hop, search-only pseudo-anchor, bounded to cases where at least two
trusted predictions agree within about one cell.  It may propose a search
centre but may never emit evidence itself.

### Certificate-gated residual scheduling

There are two distinct solved masks:

1. the **pilot pending mask**, which suppresses duplicate pilot emission but
   does not prove payload or make a pose unnecessary;
2. the **payload NeedMap**, where only syndrome+CRC certification removes an
   exact canonical LDPC tile from later decoder scheduling.

Pilot tiles are 60×60 cells and LDPC tiles are 64×64 cells; the grids are
deliberately misaligned.  One 200×200 placement usually supplies partial
payload evidence to several LDPC tiles.  A valid BCH/address therefore says
"this window maps here," not "this payload tile is solved."

The safe feedback point is a certificate barrier, not necessarily one LDPC
attempt after every placement.  The qualified `ctx-pava-v1` path pools a
region, overlapping windows compete for one-owner payload cells, and
separate windows/scraps can complete one tile.  Per-placement decode would
repeatedly expose provisional evidence frontiers to CRC and complicate the
owner/context contract.

A bounded future arm can instead:

1. run the cheap spatial placement wave to quiescence;
2. freeze context and ownership for the accumulated evidence;
3. attempt newly coverable LDPC tiles once at that evidence frontier;
4. immediately remove syndrome+CRC-certified tile keys from later BP/CRC
   scheduling;
5. use the refreshed NeedMap to prioritize the hard placement backfill,
   retaining a one-window halo and any windows needed as geometry bridges;
6. never prune on BCH success, a failed LDPC attempt, or a below-floor tile.

Even a certificate should not blindly erase scan-space placement: a window
may straddle solved and unsolved LDPC tiles, relay geometry, provide the best
owner for neighbouring cells, or supply dense labels for later pose
refinement.  Certification can safely suppress exact-tile decoder work and
guide priority; hard spatial cropping needs separate qualification.

### Invariants and qualification

- Every accepted destination passes its own current-raster pose, SEARCH,
  held-out VALIDATION, and straddle gates; hints never supply pilot bits.
- Failed windows and pseudo-hypotheses cannot emit evidence or become
  authoritative geometry recursively.
- When global correlation is invoked, retain the complete legal rival set;
  pruning solved candidates post-FFT neither saves the FFT nor preserves the
  same refusal-biased gate.
- Preserve deterministic queue order, bounded hypothesis counts, complete
  attempt/provenance ledgers, and current same-capture evidence semantics.
- Measure placement/pilot/LDPC outcomes, unique certificate gain, chain
  probes/cache hits, winning anchor rank, frontier retries, subdivisions,
  BCH/global calls and accepts, CRC calls, BP iterations, and wall time.
- Qualify the ladder incrementally: exact-cache parity first; nearest-anchor
  ranks and bounds next; spatial frontier/component seeding; redundant
  geometry relays; only then any pseudo-anchor or certificate-barrier arm.
- Exercise both C2 captures, C3, and the fold, scanner-y-step,
  touching-scrap, wrong-seed/page, and adversarial-null fixtures.  The C2
  observations are a strong performance diagnosis, not cross-print or
  false-accept qualification.

**Expected value:** large placement-time simplification is the primary
hypothesis.  Recovery should initially be neutral; any added certificates
from earlier subdivision, better boundary poses, or geometry relays must be
reported as a separate measured result.
