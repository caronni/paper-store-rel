# DONE-GEOMETRY — certified-done pixel space and early retirement of payload work

Status: **design record, adopted in principle — not adjudicated in detail,
not built, not normative** (2026-08-04, user dialogue after the first
physical v1 decode — e029, the ink-counting page). RECEIVE-DESIGN v0.45/v0.46
remains the receiver contract. Building any part of this requires a
RECEIVE-DESIGN amendment, hand-bumped policy identities, and comparative
qualification. This document records the idea, the reasoning, the draft
law, the recorded costs, and the measurement that should precede execution.

Provenance: user proposal 2026-08-04 ("every time we certify a payload
tile, we have a set of cells and a pose, so actually a set of physical
pixels on the scan itself that we know will never directly contribute
anything ever again"), sharpened in dialogue against the current code and
the adjudication record. It subsumes and strengthens
`docs/PLACEMENT-IMPROVEMENTS.md` §1.4 ("certified-footprint
deprioritization", NOT built, census-gated) and is the parked kiss-branch
frontier-scheduler clause "placed/occupied area prunes domain +
certificate-aware early-stop" (`.claude/memories/holo-v1-kiss-branch.md`,
top-down item 3). This dialogue is that top-down session's first product.

## 1. Problem: certificate knowledge arrives late and ad hoc

The receiver already refuses to redo certified payload work — but every
gate is **address-space and post-placement**, applied at scattered points:

- payload plan L1/L2 (pool law, v0.35): wholly-terminal regions drop, and
  certified-complete windows go label-only — decided in
  `production_payload.ProductionPayload._plan` /
  `payload.unresolved_region_patch_ids`, i.e. AFTER placement ran;
- terminal-key attempt no-ops + NeedMap inside the payload engine;
- R-level pixel-free pre-gates (v0.44): no committed poses / no frontier /
  every committed span certified ⇒ empty delta without materializing the
  raster — the only pre-raster gate, and it exists only for R(Lk);
- verified-close preemption at barriers (kills everything, but only once
  the whole volume closes);
- the color twins (`fully_certified_color_addresses`, per-stream
  work-key terminality).

Verified holes (code read 2026-08-04):

- `receive/place.py` contains **zero** references to certificates: an
  ordinary lane places every window — chain probes, staged word decodes,
  priced cold — even when the window's whole span is already certified,
  and only the payload plan then prunes it.
- `place.place_mopup` consumes **all** durable parked rows with no
  certificate filter (place.py:685-690): a window that parked at L0 and
  whose tiles were later certified by other windows still pays hint
  transport, rest-word decode, possibly priced cold and subdivision at its
  M-level, and is then discarded by the payload plan. Pure waste.

Motivating magnitudes (measured): 48.2% of lane time went to zero-yield
lanes (kiss profiling); open-domain cold ≈ 12 s/window at production
scale; on the v0.23 synthetic A/B the coarse lane minted 575/604
certificates (95%) while every finer lane re-placed the full inventory to
rescue 29; today's ink-page session ran 12 levels and 1,451 accepted
placements for ≤ 1,961 addressable symbols, with 7,492 dropped mop-up
re-observations. Verified-close preemption hides this on happy intact
sheets; the waste concentrates exactly where sessions are long — open
fragment/damage sessions, `--complete`/`--mopup`/`--refine` runs,
multi-page volumes with finished pages.

## 2. The idea: done-ness as pixel geometry, projected at certification time

A CRC certificate is minted through a committed, audited pose. That pose
maps the tile's cells to an exact set of physical pixels of the capture —
**at certification time, with no prediction involved**. Those pixels are
thenceforth *payload-done for that capture*: they can never again change
the payload result. Maintain, per capture, the union of those footprints;
a window — in any later lane or stage — whose supported extent lies
entirely inside the done set is never posed, never searched, never
scheduled, and (for parked rows) is retired the moment its span becomes
done.

The load-bearing inversion, and why §1.4's formulation was weaker: any
**address-space** test on a future window needs a pose to map the window
to page addresses, so it can only fire *after* (or by predicting) pose
computation — §1.4 therefore said "deprioritize, never skip", because
anchor-transport predictions can be wrong. The **pixel-space** test needs
no pose for the new window at all: the projection direction is reversed
(certifying pose → pixels, once, using committed audited geometry), and a
future window's pixel extent is known a priori from window layout plus the
exact lane→native transform. The test

```
(window extent ∩ survey support) ⊆ done-pixels(capture)
```

is exact, pose-free, prediction-free — the only formulation that can
retire *pose computation itself*.

## 3. Soundness

Authority chain: CRC certificate (sole cross-lane bit authority) →
minting/owner placements (committed, audited, durable PoseRecords) →
pixel footprint. Case analysis for a fully-done window:

- any *correct* pose it might fit re-reads addresses that are terminal —
  NeedMap discards the attempts today; the content is already known;
- any *incorrect* pose yields evidence the admission gates must refuse;
  and if a wrong pose somehow passed, it would only mint evidence at
  already-terminal keys.

Under every branch the payload contribution is exactly zero, so skipping
is **payload-neutral by construction** (it is deliberately NOT
evidence-neutral — §5, §6). Trust class: identical to NeedMap. A wrong
certificate (CRC false accept ≈ 2⁻³², or the v0.34 surplus-audit
masked-wrong class) poisons the done set exactly as it poisons NeedMap
today; no new hazard surface. Quarantine interaction: the §5.4 firewall
gates promotion *before* minting within a level, and minted certificates
are never revoked (conflicting certified bits are fatal, not voted away) —
so a certificate's minting geometry was un-quarantined and audited at
minting time, and the projection may use it unconditionally.

## 4. Draft law (amendment material, not yet ruled)

1. **Construction.** Per capture, done-pixels = the union over committed
   placements P (all lanes of that capture) of the pixel footprints of
   {audited cells of P whose address is payload-terminal}, projected
   through P's committed pose and the exact lane→native transform.
   Payload-terminal = the existing terminality predicate: K certified;
   color per work key (a CMY8 tile with only C certified is NOT done).
   This base form is purely factual (audited cell ∧ certified address);
   see §7.1 for the erasure extension.
2. **The gate.** At window planning in any lane (ordinary, M, R): a window
   whose supported extent is contained in the done set is not created. A
   durable ParkedWindowRecord whose supported extent becomes contained is
   retired (reason recorded) instead of re-attempted at its M-level. A
   level whose entire inventory is done pre-gates to an empty artifact —
   the v0.44 R-gate generalized to M and ordinary levels.
3. **Semantics.** The done set is a barrier-frontier snapshot, fixed at
   lane start (NeedMap's semantics) — deterministic, replayable. It is
   **derived** from certificates + PoseRecords on demand, never persisted
   (facts derivable from the causal record are not persisted twice).
4. **Representation.** Native-frame, cell-granular (boxes/runs at cell
   pitch), bounded per region — the §9.4 site-granular pending-mask
   doctrine. Never a native-resolution bitmap over a multi-GB scan.
5. **Per-capture asymmetry (inherent, correct).** Certificates are global
   in address space; pixel footprints exist only where *this* capture has
   committed audited geometry. A tile certified from capture A is
   pixel-done in A but not in B until B commits poses covering it; B's
   windows there run normally and die at L1/L2 as today. In B we genuinely
   do not know which pixels carry that tile.
6. **Support intersection.** Unsupported (background) pixels are
   ignorable; supported-but-uncommitted pixels are live — a window
   covering done payload plus uncommitted support must still run.
7. **No domain side effects.** The gate never shrinks a declared route
   domain, floor, or budget for any window that does run (H_r stays
   frozen; v0.23 precedent: scheduling reorders and defers — here,
   retires — but admission arithmetic is untouched).
8. **Authority discipline.** Done-ness derives from certificates plus the
   committed poses that minted/own them — never from accepted poses alone,
   never from LLR confidence (no self-seeding).

## 5. What stays outside the gate

- **Label/context furniture (pool law).** L2/L3 (v0.35) deliberately keep
  certified-complete windows in the region context fit as label rows; a
  mixed region still wants that furniture. Fully-done windows therefore
  keep serving the fit — but via **committed-pose reconstruction**
  (the D7 / `place_committed` machinery, v0.34/v0.42/v0.44), which needs
  no fresh pose, consistent with the core claim. Note honestly: in
  ordinary finer lanes today those labels ride *fresh current-lane
  placements*; reconstruction changes their provenance and values — the
  main numerics delta of this design (hence policy bumps + comparative
  qualification, not a result-exact hoist). Cross-lane reconstruction is
  deterministic but not bit-exact-to-anything existing; it needs its own
  contract (the per-lane D7 bit-exactness carrier does not transport).
- **Chain-anchor duty.** Neighboring live windows lose the skipped
  window's fresh pose as a same-level anchor; committed-pose hints already
  serve this role (M-level inheritance, lower-hint portfolio, R binding).
- **Context halo.** Done pixels remain readable as sampling context for
  adjacent live cells; "done" means *never again a payload observation
  target*, not *never sampled*.

## 6. Recorded costs and hazards

- **D5 canary channel.** Fully-done windows are where the v0.46 flip
  canary samples two-view consistency at committed cells (M-level
  supersession). Gating them removes the *healthiest* slice of that
  channel (partial windows keep theirs). The flip-rate threshold doctrine
  is still pending post-08-04 data — and the first real datum is loud:
  today's ink page read flips 1,614/7,492 ≈ 21.5% against the 5.35%
  healthy-scrap anchor (clipped edge tiles are the suspect, uninvestigated).
  Do not build broader suppression while that number is uninterpreted;
  bundle or order this design with the D5 doctrine session. A bounded
  audit-sample of done windows is the available knob.
- **Wrong-certificate poisoning.** Parity with NeedMap (§3); the surplus
  audit (v0.34) remains the disclosure instrument. No new class, but the
  suppression is broader — record it.
- **Done ≠ exhausted.** A certificate-only mask never stops work on
  *hopeless* material (e.g. today's deliberately clipped edge tiles, which
  can never certify). A priced "exhausted" state could share the geometry
  but has different authority (EV/scheduling, always resurrectable) —
  explicitly out of scope here; do not conflate.
- **Not evidence-neutral.** Labels change provenance (§5), parked rows
  retire, placement inventories shrink. This is a semantic scheduling +
  evidence-formation change: RECEIVE-DESIGN amendment, hand-bumped
  address/payload policy ids, yield-parity comparative qualification on
  the frozen corpus and the new real states.

## 7. Open rulings (adjudication queue)

1. **Erasure extension.** LDPC certifies tiles with missing cells, so the
   base (audited ∧ certified) footprint under-covers a tile's 64×64
   extent. Option A: project the full tile rectangle through the
   certifying window's pose, clipped to that window's span (affine
   extrapolation over a few cells — the same extrapolation sampling
   performs). Option B: audited cells only (conservative, leaves slivers
   live). One-line rule either way; must be ruled, not defaulted.
2. **Label channel for fully-done windows.** Keep via committed-pose
   reconstruction (recommended; preserves L2/L3 intent), or drop with
   measured calibration impact, or keep only while the region fit is
   label-poor. Interacts with docs/LABEL-SAMPLING-SHAPE-ANALYSIS.md (A3).
3. **Canary audit-sample.** Whether to retain a bounded fraction of done
   windows as flip-observation probes, and at what rate; ordering with the
   D5 threshold doctrine session.
4. **L1 subsumption.** Whether the address-stage gate retires the payload
   plan's region-granular L1 test or both remain (defense in depth vs
   one-concept-one-implementation).

## 8. Measure first (the census)

Owed by the §1.4b record ("revisit with the real-corpus census",
post-08-04 — now satisfiable) and by the standing measure-gates doctrine.
Read-only harness over durable states (no receiver changes):

- inputs: the e029 ink-page `receive.state`
  (`scratch/e028/holo-c2-r0700-q07-ink-counting/`, 12 levels, 1,451
  accepted placements, 1,940 certificates), plus the frozen E023c C2/C3
  states and any forthcoming multi-scan session;
- per lane, reconstruct the done set at lane start (certificate frontier +
  prior committed poses) and count: windows whose supported extent was
  fully done; placements/word-decodes/colds/subdivisions actually spent on
  them; parked rows that were already done at their M-level; label rows
  those windows contributed (the §5 exposure); flip observations they
  carried (the §6 exposure);
- price with the timing harness attribution (address vs payload buckets).

Decision input: if the done-covered share of address-stage cost is small,
only the parked-retirement slice (§9.1) is worth building; if it is large
(expected on ladder-heavy sessions), the full gate pays.

### 8a. Census results — e029 (measured 2026-08-05, zero print)

Harness `experiments/029-holo-v1-first-print/census_done_geometry.py`
(read-only; state sha `bdd7b293fefee87c…`, tail-invocation events sha
`68ed1b91649b8801…`); artifact
`experiments/029-holo-v1-first-print/DONE-GEOMETRY-CENSUS.json`; log
addendum 029.2. Gate simulated per the §4 law: 16 px grid (= one c2 cell
at 4800 dpi), tile bboxes through each committing pose's `native_affine`,
union eroded one cell, supported-cells-only containment — every
approximation biases AGAINST gating. Events cover only the final
invocation (M/R tail; earlier logs replaced), so ordinary-lane rows are
durable-pose views.

| level | certified at start | placements | A: fully done | B: pixel-gated |
|---|---:|---:|---:|---:|
| l00 2ppc | 0 | 227 | 0 | 0 |
| l01 4ppc | 1,075 (54.8%) | 315 | 3 | 4 |
| l02 8ppc | 1,927 (98.3%) | 315 | 227 | **236 (75%)** |
| l03 16ppc | 1,930 | 315 | 228 | **236 (75%)** |
| m00 (tail) | 1,938 | 279 | 242 | **243 (87%)**; windows 398/440 gated, colds 136/160, word-rests 136/160 |
| m01–m03 | 1,940 | 0 | — | already empty (v0.37 parked-emptiness pre-gate) |
| r00–r03 | 1,940 | 28 | 0 | **0** — the gate never touches live refinement work |

Totals: **719 of 1,479 committed placements (48.6%) pixel-gated**; the
l02+l03 pair spent 630 placements to mint 11 certificates with 75%
gateable; the m00 `--complete` tail spent 440 windows / 160 priced colds
(133-page sweeps; 7,200 cold-progress steps) / 160 rest-word decodes to
mint 2 certificates, 85-90% gateable. Gated windows minted zero
certificates — provable, not just observed: a fully-done supported extent
cannot contain an uncertified tile's pixels (§3).

Readings:

- **B > A at l02/l03 is the supported-pixels law working**: the excess is
  exactly the page-edge overhang windows (28 verified at l02) whose
  out-of-page "tiles" can never certify — A's rectangle accounting counts
  them partial, the gate correctly ignores unsupported pixels.
- **l01 near-zero is correct behavior**: at 54.8% frontier density nearly
  every 200-cell window touches an uncertified tile. The gate is a
  high-density instrument — decisive from ~98% (l02 start) on this
  window/tile geometry.
- **L1 never fired all session** (`payload.pruned_terminal_patches` = 0
  everywhere): one region + 21 never-certifying tiles means the
  region-granular prune cannot engage — the window-granular gap is
  precisely what this design fills.
- Event-window gating (398, planned boxes) vs pose gating (243, placed
  footprints) differ because planned boxes carry no orientation/warp and
  include never-accepted windows; both views agree on the magnitude.
- Caveats: one intact dense sheet — the gate's favorable regime; the
  fragment/confetti census (sparser coverage, per-scrap page domains) is
  still owed; no wall-clock attribution (events are timing-neutral by
  design) — counts are the currency, and a `--profile-timing` rerun can
  price the m00 colds if seconds are wanted.

Census verdict for §9: the m00 tail alone justifies §9.1
(parked/window retirement at M-entry: 90% of tail windows, 85% of colds);
the l02/l03 75% share justifies the §9.2 planning gate on ladder-heavy
sessions. §9 ordering stands.

## 9. Execution sketch (later; smallest first)

1. **Parked-row retirement** — filter `place_mopup`'s inventory against
   the done set at M-entry; retire with reason; pins for retire/replay.
   Cheapest, self-contained, no label interaction (parked rows contribute
   no labels today). Scheduling-only except the retirement record.
2. **Window-planning gate** in ordinary lanes + committed-pose label
   rerouting (the §5 contract) — the policy-bumping core.
3. **Level pre-gates** — generalize the v0.44 R pre-gate shape to M and
   ordinary levels (skip raster materialization when the whole inventory
   is done).
4. Comparative qualification: yield parity (zero lost certificates on the
   frozen corpus), cost deltas, canary posture, then the amendment lands
   in RECEIVE-DESIGN with its ledger row.

## 10. Not reopened

PLACEMENT-IMPROVEMENTS §1.4a's whole-lane adjudication (coarse lanes are
not dispensable) stands. The phased schedule D1–D20, declared domains and
floors (§5.3), the pool law's fit arithmetic for live windows, NeedMap as
the payload-attempt authority, and the close schedule are unchanged by
this design; the done set is scheduling/creation authority layered above
them, never a replacement.
