# RULINGS — the decision sheet for Gate B

Rebuilt 2026-09-03 after Germano's reading of the first draft ("gate B is
overwhelming"). His provisional ruling: the bulk of the 129 entries are not
yield-bearing losses and stand as "keep holo3's, recorded". This sheet keeps the
six decisions that are real, records everything else under the block it belongs
to, and points at `RULINGS-full.md` (the 129 entries, unchanged) for the evidence
behind any line.

Every number below cites `ARTEFACTS.md` through its entry in `RULINGS-full.md`.
No receiver ran on a real capture. Nothing in code has changed.

## 1. Decide now — six questions

### D1 — Address-word contradictions: quarantine and known-position words
Entries: `k-placement-29` (holo1), `placement-23` (holo2), `evidence-ownership-15` (holo2), `extra-16` (holo2), `done-gate-08` (holo2).

v1 pooled every accepted placement's read of each printed address word, decoded
the pooled read with erasures, and on a contradiction with the expected counter
quarantined the contributors (hints dropped, their payload evidence refused, the
run aborted loudly). holo2 built the same idea as durable facts: a legally decoded
word that names a different counter than the standing placements mints a
contradiction fact; the placement is born quarantined and its evidence is excluded
from every attempt, calibration pool and done projection. holo3 has none of it:
word reads and audited cores go only to the diag; the certificate gate (LDPC
syndrome, CRC, re-encode identity) is the only bar.

Evidence: the mechanism has never fired on any corpus on any side. v1: zero
contradictions in about 1,780 known-position reads (70 of 70 regions, all 925
tiles). holo2: zero contradictions and zero quarantined records across 21,079 and
21,508 evidence records; cost +2% wall. Zero wrong certificates in 69,066,304
audited cells (v1) and on every holo3 battery and head-to-head.

What is lost: the ability to NOTICE a contradiction, not protection against one — a
cell read through a wrong pose fails its CRC instead of minting a wrong tile.
Fragment or damaged material is where a contradiction could first appear.

Options: accept the loss and record the argument · archive for later port · keep a
diagnostic-only form (pool the word reads, emit a contradiction event, quarantine
nothing).
Recommendation: accept the loss. If you want the alarm back, the diagnostic-only
form is the cheap one and needs no gate.
**Ruling (Germano, 2026-09-03):** accept the loss of the quarantine logic for now. holo3 must emit a LOUD console warning when an address-word contradiction is detected — the diagnostic-only form (pool the word reads, compare a decoded word against the standing placements at that position, warn; quarantine nothing). Phase-2 work package.

### D2 — Same-capture cross-rung pooling
Entry: `evidence-ownership-10` (holo2).

Built nowhere. holo2 named it, measured its potential from the gap census (summing
one scan's four corrected rungs certifies +2 e029 tiles no single footing closes;
16 of 78 gap tiles sit below the informative floor at 1.2–4.9% cell error and are
never attempted at all) and then refused it for v1 parity ("a lane IS a rung"). It
sums one physical capture's rungs, which the never-sum-the-same-capture law forbids
because the rungs' errors are correlated (holo3's codec measurement: pooled closes
from noise amplitude 1.2 only on independent noise). The sharp half: below-floor
tiles are never ATTEMPTED, so no rescue row is ever born for them; a cross-rung sum
is the only door to that class.

Options: leave absent · build as an ADDITIVE residue row under the toolbox doctrine
(monotone, zero-wrong gated, priced) — a new holo3 line, not a port · measure first:
count, on holo3's archived event streams, how many tiles sit below floor at every
rung (no decode).
Recommendation: not part of retirement. Record it as a candidate residue row with
the +2 and 16-of-78 numbers; measure the below-floor class from the archived
streams before building anything.
**Ruling (Germano, 2026-09-03):** not built. Document the choice in holo3's design record (we do not sum one capture's rungs for now; the gain is probably subsumed by the analyzer's yield). Phase-2 doc package.

### D3 — Which detector the refinement adoption gate scores
Entry: `refinement-03` (holo1). Brief: `PORT-BRIEFS/context-corrected-adoption-gate.md`.

v1 measures the held-out gain on context-corrected logits (it recomputes the
neighbour counts for the candidate pose and applies the region's adopted offsets).
holo3 scores marginal logits only, a holo2 ruling carried into spec 08. No artefact
compares the two gates; v1's prior is that context adoption moved 742 to 749
certificates and cut cell BER from 1.92% to 1.35% (a different question); holo3's
own adoption rate is high (2,471 adoptions on 4,616 fires). The v1 arm is fourteen
lines. It cannot be measured on the archived v1 states (they hold no refinement
inputs).

Options: keep holo3's · port now behind a dial and A/B on the two sims plus the
existence stimuli (minutes, test lanes) · archive for later port.
Recommendation: archive; git-move the fourteen lines before Gate E. The sim A/B is
optional and cheap if you want it now.
**Ruling (Germano, 2026-09-03, provisional):** "we should carry this over to holo3, no? are we sure this would lose no yield?" — see the lead's answer in the session record: nobody is sure either way; the port lands behind a dial with a sim A/B and the existence stimuli before it becomes the default. Phase-2 work package if he confirms.

### D4 — Refinement chains and the single evidence namespace
Entries: `refinement-09` (holo1), `refinement-11` (holo1), `scheduling-06` (holo1), `refinement-04` (holo2). Brief: `PORT-BRIEFS/refinement-evidence-namespacing.md`.

v1 refines a window at most once per rung, in the refinement level's own evidence
namespace, so a bad revision can only cost the fit; only certificates cross lanes.
holo2 allowed at most one revision per window, structurally. holo3 refines again
whenever the window's certified reach strictly outgrows the basis of its last
revision (steps compose), and an adopted revision's re-read REPLACES the standing
evidence with no quality test; placement supersession is one-way.

Evidence for holo3's design: sheet I ran 2,950 colour refinement fires for 1,631
adoptions; 124 tiles first certified after the first adoption, 96 of them new
against baseline. The forensics looked for the predicted failure mode and found no
loss attributable to it (54 lost tiles across three volumes, none a refinement
defect; sheet I's 13 losses half attempted before any adoption, 11 of 13 in Y).
Measured from the archived streams by the second lens: 162 windows have already
taken more than one adoption, 8 took three; three composed steps can move a window
about three quarters of a cell and half a degree, enough to read a neighbour's cell
(which fails CRC — lost, never wrong). Evidence against iterating: the E024 knee
(+2 to 5 tiles of about 760; "one or two productive passes").

Options: keep the chain · keep it and add holo2's guard (refuse a geometry the
window has already stood at; a few lines) · bound composed drift against the
original placement at one search box · revert to one revision · give evidence an
ordinal so a worse re-read cannot supersede a better one.
Recommendation: keep the chain and the single namespace. Add the "already stood
here" guard as a Phase-2 package with a test-lane proof; run the composed-drift
measurement on the archived streams (no decode) before anyone makes chains cheaper
or longer; archive the namespace brief; add the colour-sim tripwire that the
pre-adoption certificate set survives an adoption.
**Ruling (Germano, 2026-09-03):** yes — keep the chain and the single namespace; add the "already stood here" guard; run the composed-drift measurement on the archived streams; archive the namespace brief; add the colour-sim tripwire. He adds: holo3's scheduler shows many redundant runs and that needs a conceptual answer; this guard may help. Recorded as a follow-up line (scheduler redundancy), outside this campaign.

### D5 — A survey that votes no pitch loses the whole capture
Entries: `k-placement-07` (holo1), `placement-24` (holo2).

holo3 refuses the run when the survey votes a printed pitch that contradicts the
declared format row (right: it is the e033.2 misdeclared-dpi catch). It also treats
"no vote" — a tie, or no component that snaps — as pitch None, and a capture with
pitch None gets no windows. v1 proceeded on the declared fallback; holo2 recorded
the vote and skipped only unschedulable regions. The no-vote branch guards nothing
holo3 uses (frame geometry is built from the declared pitch) and bites exactly on
fragment or confetti captures with few components or an off-catalogue pitch: a
whole capture lost, silently. No artefact measures it (ARTEFACTS gap G-08).

Options: keep · accept · port now: keep the contradiction refusal, downgrade the
no-vote case to a warning, build frames on the declared pitch. Cost: one branch in
the survey fold plus a warning event, and a sim-lane test at a capture with no
votable component. No decode.
Recommendation: port now (a Phase-2 package). It is the only placement mechanism
that can silently lose a whole capture, and it protects nothing.
**Ruling (Germano, 2026-09-03):** port. Phase-2 work package: keep the contradiction refusal, downgrade the no-vote case to a warning, build frames on the declared pitch, sim-lane test at a capture with no votable component.

### D6 — The region-context cell's ordinal
Entry: `calibration-context-ownership-15` (holo1).

holo3 keeps a region's context fit as a decision cell ordered by (adopted,
−held-out loss): a re-fit that scores worse never replaces the standing one, and
the standing offsets are pushed to windows that arrive later. v1 fitted once per
pass over that pass's complete population and had no cross-pass comparison. The
first holo3 landing dropped the whole rewrite batch on a worse re-fit and cost 274
certificates on e029 (1,664 against 1,938; fixed the same day). Still open, in that
commit's own words: context quality is measurably non-monotone as evidence grows
(0.0201–0.0216 oscillation), so quality-only against evidence-base-major (newest fit
wins, quality as tie-break) is a yield question with no paper measurement (zero
effect on the sims).

Options: keep holo3's · make the ordinal evidence-base-major · measure: the e029 K
harvest pair with the alternative ordinal, about 25–35 minutes for the pair, one
decode at a time — the only real receiver run this sheet proposes.
Recommendation: keep holo3's now; lift the 274-certificate incident into
ARTEFACTS.md §2.2 (it lives only in commit bodies). Whether the 30-minute pair is
worth running is your call.
**Ruling:** pending — Germano asked for a plain-words explanation (given in the session record); ruling to follow.

## 1b. Follow-up line recorded from the D4 ruling

Germano, 2026-09-03: "I see a lot of redundant runs in holo3's scheduler, we'll need to take care of that conceptually." Recorded as an open line outside this campaign (candidates in the record: the colour lane's 46.9 fires per subject on the machine 2 sheet-I run, calibrate ~23 fires per window and ctx up to 80 per subject on real sheets — `OPEN-2026-08-31.md`; refine re-fires on every reach change — `SCHEDULE.md` debt rows).

## 2. Already your rulings, recorded — no decision (18)
The dryness gate and the cold prices (`d399ba3`, "cold last by price"; on every
archived whole-sheet K run nothing in the gated band ever fired); the dynamic page
domain, its per-flavour floors and the cold tried marks (PAGE-DOMAIN, qualified
byte-exact on e029 — the accepted narrowing is that certificate SETS may differ
across worker counts); the aging band (engine owns no pricing, 2026-08-29); the
plane-common field component subtracted as the median (2026-08-31 — note the
contrary number: the v1 instrument's MEAN-subtraction arm cost one certificate and
0.6 pp dead-band BER on the frozen W6 state, `docs/INDEPENDENT-PLANES.md` §2.11; the
median form has no paper number); `--mopup`/`--refine` bounds (accepted as lost);
cold format discovery (archive for port).
| id | side | class | yield | title | draft recommendation |
|---|---|---|---|---|---|
| `dryness-01` | holo2 | ABSENT | decides-certificates | The dryness gate: an admission hold that stops expensive work from starting whil | keep holo3's behaviour, and archive the ten-line clause as a brief rather than porting it blind. Rec |
| `dryness-02` | holo2 | ABSENT | decides-order-only | Which work the gate holds back: three named passes versus a whole price band | Keep holo3's (no gate). If the in-flight clause is ever ported per DRY-01, port holo2's SHAPE and no |
| `dryness-04` | holo2 | DIVERGED | decides-certificates | Where the page-correlation search sits in the price order relative to refinement | keep holo3's order, record it as reasoned but unexercised, and schedule that one fragment re-run as  |
| `dryness-05` | holo2 | DIVERGED | decides-order-only | The escalation door: making repeated expensive work drain last without refusing  | keep holo3's prices, fix the two unguarded rows, and log the missing payload aging as a cost-only im |
| `dryness-07` | holo2 | DIVERGED | decides-certificates | How big the expensive band is: the page set a cold search sweeps | keep it - it is the only route that can reach a page nothing else has opened, and capping an evidenc |
| `dryness-08` | holo2 | DIVERGED | decides-certificates | Nothing bounds how many expensive page searches run at once, and each one accumu | keep holo3's behaviour, add one sentence to the design's memory section saying the per-fire cache sc |
| `placement-26` | holo2 | ABSENT | decides-order-only | The dryness gate — an expensive placement tier may not start while anything chea | accept the loss as written, with a costed follow-up rather than a port. The measured head-to-head re |
| `pricing-02` | holo2 | DIVERGED | decides-order-only | The two cold prices — 140/150 gated behind global dryness vs 250/260 ordered las | Keep holo3's. The only head-to-head we have says the gate buys nothing on a draining run, and 250/26 |
| `pricing-09` | holo2 | ABSENT | decides-certificates | The rework/aging band max(base, 90 + 5*(n-1)) + premium — a re-attempt's price g | Keep holo3's behaviour and record the cost honestly rather than porting: the user ruled the engine m |
| `placement-25` | holo2 | DIVERGED | decides-certificates | The default page domain — how many pages placement may address without an operat | keep holo3's. It is the newest merged work, qualified against its own null with a byte-exact close,  |
| `placement-10` | holo2 | DIVERGED | decides-certificates | Cold's tried-set dedup granularity — per page, or per (flavour, page) | keep holo3's. It cannot remove an attempt, only add one, and it must move together with the per-flav |
| `k-placement-15` | holo1 | DIVERGED | decides-certificates | Cold page domain and the support floor it prices |  |
| `k-placement-16` | holo1 | DIVERGED | decides-certificates | The page domain itself: static declared set vs dynamic live set over a possible  |  |
| `k-placement-33` | holo1 | ABSENT | decides-order-only | The small-domain cold-first price inversion (cold_first_max_pages) |  |
| `fields-discovery-continuation-operator-05` | holo1 | DIVERGED | decides-certificates | Handling of the plane-COMMON component of the measured field | Keep holo3's median (a), and put the §2.11 table in the entry so the ruling is made with the contrar |
| `refinement-18` | holo1 | ? (ruled) | ? | The refinement dial: --refine / --mopup plan-prefix bound vs always-queued rows | Keep the existing ruling; do not reopen. One correction to carry into the map: the v1 flag path is s |
| `scheduling-09` | holo1 | ? (ruled) | ? | Invocation reach as a flag-bounded plan prefix (--mopup / --refine) vs unconditi | no change - already ruled (claude-plan.md §12 item 4, the operator bounds accepted as lost because t |
| `fields-discovery-continuation-operator-15` | holo1 | ? (ruled) | ? | Discovery-first receive: receiver-wide orchestration over isolated exact-row bra | Archive for later port (b) — already ruled. The capability is real and unreproducible from anything  |

## 3. Placement geometry adopted from holo2 or measured favourable — recorded (6)
One shared cell lattice (holo2 measured extents identical across footings where
v1's origins were disjoint; e029 1,940/1,940); permissive window admission;
declared-pitch geometry (the house rule; v1's own comment agrees); the whole-word
cross-page rival bar (v1 had first-hit-wins; no miss attributed); the straddle-audit
path (holo3 quarters AND re-arms — a superset of both predecessors); consult reach
at the cheap tier (holo3 ahead on every row of the only head-to-head).
| id | side | class | yield | title | draft recommendation |
|---|---|---|---|---|---|
| `k-placement-03` | holo1 | DIVERGED | decides-certificates | Where the observation-window lattice is laid: per-lane pixel frame vs one shared |  |
| `k-placement-04` | holo1 | DIVERGED | decides-certificates | Window admission at layout time (support floor) |  |
| `k-placement-06` | holo1 | DIVERGED | decides-certificates | Which pitch the region aperture and cell grid are built from |  |
| `k-placement-13` | holo1 | DIVERGED | decides-certificates | Word-route admission: first-hit-wins vs the whole-word cross-page rival bar |  |
| `k-placement-22` | holo1 | DIVERGED | decides-certificates | What happens to a window whose straddle audit refuses |  |
| `placement-01` | holo2 | DIVERGED | decides-certificates | Consult reach at the cheap tier — which already-placed windows may steer an unpl | keep holo3's. Record the repetition as a separate cost line, to be null-proved on certificates befor |

## 4. Port-now candidates, integrity or operational, none yield — say yes or no as a block (9)
| id | side | class | yield | title | draft recommendation |
|---|---|---|---|---|---|
| `fields-discovery-continuation-operator-20` | holo1 | ABSENT | integrity | Additive schema migration for a stored state | Port now, in minimal form (c). Not a migration table — a stamp. It is a few lines in snapshot.write  |
| `payload-union-retry-intake-27` | holo1 | DIVERGED | integrity | Non-uint8 rasters: dtype-preserving views vs uint8-only materialisation | port now, cheaply — one dtype check in load_native that refuses anything but 8-bit, naming the dtype |
| `fields-discovery-continuation-operator-30` | holo1 | CARRIED-DIFFERENT | integrity | The provisional-placement warning contract | port now, in minimal form |
| `payload-union-retry-intake-06` | holo1 | CARRIED-DIFFERENT | integrity | The 018.7 bounded-LLR invariant and the finiteness boundary | port now. Move the finiteness check from the black-and-white body into _combine so all three familie |
| `payload-union-retry-intake-23` | holo1 | CARRIED-DIFFERENT | integrity | Native raster ingest: acquisition identity and the ingest refusals | port now, cheaply — a page-count check and a channel-count check in load_native, two statements betw |
| `extra-05` | holo2 | CARRIED-DIFFERENT | integrity | Capture identity, the refusals at ingest, and re-authenticating the source file  | port now, cheaply: a handful of refusals at holo3's `load_native` (dtype real-numeric, channels in { |
| `close-06` | holo1 | DIVERGED | operational | Disposition of a TERMINAL non-verified close (integrity_failure / unsupported) | Port now, option 2 - a small, format-free change with no yield at stake, but it must be scoped at ru |
| `colour-stack-25` | holo1 | ABSENT | operational | Publication of the arm ladder's own verdicts: the A4 head reason and saturation, | port now, in its cheapest form: put the head reason and saturation and the context verdict counters  |
| `refinement-16` | holo1 | ABSENT | operational | Refinement observability: per-window progress events and refusal reasons | Port now — the cheapest and highest-leverage item in the family. Scope: one event dataclass emitted  |

## 5. Archive for later port — the briefs in `PORT-BRIEFS/` (5)
| id | side | class | yield | title | draft recommendation |
|---|---|---|---|---|---|
| `colour-stack-12` | holo1 | ABSENT | decides-certificates | The supplemental BASELINE lane — the `off` arm, which re-reads the residue on th | archive for later port, bundled with colour-stack-11. |
| `close-13` | holo1 | ABSENT | integrity | D16 post-solve surplus audit — certified symbols of SOLVED blocks that disagree  | Archive for later port, with a brief. It changes no outcome, so it must not delay the retirement; bu |
| `payload-union-retry-intake-19` | holo1 | ABSENT | integrity | The certificate divergence audit (non-gating, per observed cell) | archive for later port, with the brief below. Nothing is at risk without it — the checksum gate stan |
| `payload-union-retry-intake-24` | holo1 | ABSENT | integrity | Per-barrier source re-authentication | archive for later port, with the brief below. |
| `refinement-07` | holo1 | ABSENT | integrity | Certificate/pose dependency lineage on refined poses and blocks | Archive for later port, and fold the cheap half into refinement-16's event package now — the adoptio |

## 6. Cheap measurements offered, none a receiver run unless marked (11)
| id | side | class | yield | title | draft recommendation |
|---|---|---|---|---|---|
| `payload-union-retry-intake-14` | holo1 | DIVERGED | decides-certificates | Retry never tunnels past its baseline evidence | measure, then accept. A sim-lane case that re-fits a window between an ordinary attempt and its retr |
| `payload-union-retry-intake-05` | holo1 | CARRIED-DIFFERENT | decides-certificates | The multiview combination arithmetic (equal-weight per-capture LLR sum) | run the costed measurement, and run it before src/holo goes. Extend test_k_tile_attempts_match_the_v |
| `payload-union-retry-intake-08` | holo1 | CARRIED-DIFFERENT | decides-certificates | Per-child support floors for the colour codecs (CMY7 pack-complete scatter, CMY8 | run the costed measurement before src/holo goes — add a below-floor colour case to the drift lane on |
| `payload-union-retry-intake-28` | holo1 | CARRIED-DIFFERENT | decides-certificates | Platen backing — per-lane vs per-capture | keep holo3's. The one measurement says the two numbers differ by at most two levels and that no payl |
| `refinement-02` | holo1 | CARRIED-DIFFERENT | decides-certificates | The composed RF1 fit for one window (refine_segment vs refine_window) end to end | Costed measurement, written as one drift-suite test in Phase 2 alongside the literal-vector freeze o |
| `scheduling-11` | holo1 | CARRIED-DIFFERENT | decides-certificates | Supplemental (uplift) work bound to the FINEST ordinary rung vs one uplift subje | COSTED MEASUREMENT, in two steps, the first of which is free. Step one: read `tiles.uplift` job coun |
| `done-gate-01` | holo2 | CARRIED-DIFFERENT | decides-certificates | The done projection: certified tiles mapped back onto a capture's own cells | keep holo3's, and consider a costed pin before Phase 3: a cross-tree drift oracle comparing holo2.so |
| `done-gate-10` | holo2 | CARRIED-DIFFERENT | decides-certificates | Permanence — a done retirement against a projection that can recede | keep holo3's and run that measurement when the gate is next touched. holo3 is strictly safer than ho |
| `pricing-14` | holo2 | ABSENT | integrity | The fire-count tripwire — max_fires_per_worker = 256, charged at arm time | accept the loss. The measured fire counts on a real holo3 sheet peak around 46 per subject, an order |
| `placement-03` | holo2 | DIVERGED | decides-order-only | Ordering WITHIN a price class — the offered-seed-distance leg of the queue key ( | keep holo3's and write the reopening brief. The measurement that would settle it is cheap and needs  |
| `extra-18` | holo2 | CARRIED-DIFFERENT | decides-order-only | Not re-reading a capture a lineage has already read — the ingest attempt as a sp | keep holo3's, and measure once if resume latency ever bites. The costed measurement is cheap and is  |

## 7. Everything else — "keep holo3's" or "accept the loss", accepted en bloc (66)
Per Germano 2026-09-03 ("if you think we won't lose anything yield-bearing, let's
try that"): these stand as their draft recommendation. Name an id to reopen it.
| id | side | class | yield | title | draft recommendation |
|---|---|---|---|---|---|
| `colour-stack-08` | holo1 | DIVERGED | decides-certificates | A5's deterministic 40,000-row stride subsample of the fit and gate populations | keep holo3's, and record the sheet-I cost numbers next to v1's cap comment so the fear is retired wi |
| `k-placement-18` | holo1 | ABSENT | decides-certificates | The two-loser ledger (runner-up hints) |  |
| `k-placement-30` | holo1 | ABSENT | decides-certificates | Redundant-placement suppression (observed-sites dedup) and who may be an anchor |  |
| `payload-union-retry-intake-17` | holo1 | ABSENT | decides-certificates | Durable compact evidence blocks and the cross-invocation same-lane frontier | keep holo3's and record the operator rule, noting that it is already enforced: dropping a capture fr |
| `close-13` | holo2 | ABSENT | decides-certificates | The durable close record, the terminal-session freeze, and the close-detach prop | accept the loss — and note it is a gain, not a loss, for yield. Because the close is a pure derivati |
| `done-gate-11` | holo2 | DIVERGED | decides-certificates | Done as a subdivision verdict — whether a done child counts as having served the | keep holo3's and run that count before ruling - its version is the safe direction (it spends CPU whe |
| `extra-03` | holo2 | ABSENT | decides-certificates | Attaching a capture to a resumed run BY RECORD — its surveyed regions and footin | keep holo3's — but record the consequence. The two designs need different things: holo2 stores evide |
| `placement-06` | holo2 | DIVERGED | decides-certificates | Window subdivision — WHEN four corner windows are added, and what happens to the | keep holo3's straddle behaviour, which loses nothing either predecessor would have tried, and rule t |
| `placement-11` | holo2 | DIVERGED | decides-certificates | The declared hypothesis count a cold sweep's support floor is derived from | keep holo3's, and put the two-consumer fact in front of Germano explicitly rather than as a footnote |
| `placement-17` | holo2 | DIVERGED | decides-certificates | Park / dormancy and the wake channels — what re-arms a window that has nothing l | keep holo3's wake set, and rule separately on bounding the retry supply. That is a cost fix and must |
| `placement-22` | holo2 | DIVERGED | decides-certificates | What a calibration refusal costs — does the accepted pose survive it? | keep holo3's. This is the cleanest case in the family of a divergence that is a repair rather than a |
| `placement-29` | holo2 | DIVERGED | decides-certificates | Terminality short of success — which refusals remove a window from the frontier | keep holo3's retirement, and strike the never-retiring-parent item from the map; there is no defect  |
| `refinement-02` | holo2 | DIVERGED | decides-certificates | The window-local geometry restatement and the point the baseline is sampled at ( | (a) and (b). Strike holo2's refinement adoption and yield rows as confounded, in place, with this re |
| `colour-stack-11` | holo1 | CARRIED-DIFFERENT | decides-certificates | How the supplemental arms are reached and scheduled: v1's u-lane in the scale pl | keep holo3's shape and land colour-stack-25's verdict publication, which costs nothing at run time a |
| `colour-stack-14` | holo1 | CARRIED-DIFFERENT | decides-certificates | What the supplemental arm's corrected evidence is: v1's durable lane-scoped evid | keep holo3's and record the lost cross-capture pooling as a named limit of the arm rows. |
| `fields-discovery-continuation-operator-01` | holo1 | CARRIED-DIFFERENT | decides-certificates | Per-plane registration-delta field estimator (the W1 core) | Keep holo3's (b and c buy nothing: v1's own paper result is confounded and its primary bar failed).  |
| `payload-union-retry-intake-12` | holo1 | CARRIED-DIFFERENT | decides-certificates | Attempt identity and the spend-once / no-op rule | rule this with rows 14 and 18 — one seam, that holo3 has no content-addressed evidence identity. Kee |
| `refinement-06` | holo1 | CARRIED-DIFFERENT | decides-certificates | Which certificates may label a proposal: prior-barrier snapshot vs fire-time liv | Keep holo3's. It cannot lose labels, and the reproducibility cost it introduces is a workers questio |
| `refinement-08` | holo1 | CARRIED-DIFFERENT | decides-certificates | The refinement domain: which windows are offered a fit, and when | Keep holo3's, and treat refinement-16 as this row's prerequisite rather than a separate line. Fold i |
| `refinement-14` | holo1 | CARRIED-DIFFERENT | decides-certificates | Colour certified pose refinement (per-plane presence labels, frozen per-plane ca | Keep holo3's. This is the strongest mechanism in the family and its composition difference is the sa |
| `scheduling-13` | holo1 | CARRIED-DIFFERENT | decides-certificates | Supplemental arm membership and plan order: off, a3, a4b, field | keep holo3's for arm membership and order, and cross-reference the field half to the fields/plane-fi |
| `done-gate-04` | holo2 | CARRIED-DIFFERENT | decides-certificates | What 'done' means for a PLACED window — exact tile reach vs the projected extent | keep holo3's, and run the two-verdict census when the gate is next touched. The exact-reach test is  |
| `evidence-ownership-05` | holo2 | CARRIED-DIFFERENT | decides-certificates | Two generations of a window's evidence, and which one decodes | keep holo3's, after a zero-cost check: the archived holo3 event streams already carry one `Calibrate |
| `evidence-ownership-16` | holo2 | CARRIED-DIFFERENT | decides-certificates | Tile cover membership — which windows are offered to a tile's freeze at all | keep holo3's membership rule - it is v1's and it is the better side. Record the pose-retention diffe |
| `placement-08` | holo2 | CARRIED-DIFFERENT | decides-certificates | The parent's afterlife — a window whose four corners all failed arms COLD on its | keep holo3's and record the deferral in plain words, because on every whole sheet in the corpus it c |
| `pricing-15` | holo2 | CARRIED-DIFFERENT | decides-certificates | The tried-set floor — identical inputs never re-run — and whether that memory is | keep holo3's. The re-offer-everything resume is the mechanism the deepest read on record used (+323  |
| `refinement-03` | holo2 | CARRIED-DIFFERENT | decides-certificates | Refinement eligibility — the e024 two-sided reach gate | keep holo3's gate, and close G-10 first: add per-fire refinement events (subject, reach sizes, refus |
| `refinement-06` | holo2 | CARRIED-DIFFERENT | decides-certificates | Live-pose derivation — which geometry of a window the rest of the tree reads | (b). One standing placement is the simpler and safer answer and it deletes holo2's whole live-pose a |
| `refinement-07` | holo2 | CARRIED-DIFFERENT | decides-certificates | The re-read after a revision — when and at what price the revised geometry is ac | (a) plus (b). Folding the re-read into calibration deletes a scheduler door, a four-clause predicate |
| `refinement-08` | holo2 | CARRIED-DIFFERENT | decides-certificates | Two generations of evidence, and which one decodes | keep holo3's. The fallback holo2 retains is not actually used by any holo2 reader (live_generation p |
| `refinement-09` | holo2 | CARRIED-DIFFERENT | decides-certificates | The region context fit must see the re-read's evidence | keep holo3's — the subscription is already the right shape and needs no port. Worth one line in the  |
| `refinement-10` | holo2 | CARRIED-DIFFERENT | decides-certificates | The owner-loss fallback for a pose with no published loss | keep holo3's; record the row as closed by construction rather than as a carry, so a future reader do |
| `refinement-11` | holo2 | CARRIED-DIFFERENT | decides-certificates | Which calibration the refinement scores through | keep holo3's — 'score through the calibration the current evidence was fitted under' is the only con |
| `close-18` | holo1 | ABSENT | integrity | The durable close record and its binding to the certified frontier | Accept the loss, recorded rather than ported. The cheap idiom the catalogue proposed does not transf |
| `close-21` | holo1 | ABSENT | integrity | Certificate↔counter binding check at the close boundary | Accept the loss, but record it as the refuter states it rather than as 'unrepresentability replaced  |
| `colour-stack-16` | holo1 | ABSENT | integrity | `--force-null` / HOLO_COLOR_STACK_FORCE_NULL — the contract that makes the recei | accept the loss. Deleting a descriptor row cannot be half-off, which is a stronger null proof than a |
| `colour-stack-24` | holo1 | ABSENT | integrity | The cmy7 head's population-disjointness assertions: site keys unique, fit/valida | accept the loss, and record the invariant instead — one comment at holo3/plugins/color_region_head.p |
| `fields-discovery-continuation-operator-21` | holo1 | ABSENT | integrity | Policy detach — continuing an archived state under today's receiver policy | (c). The detach is structurally unnecessary in holo3: there is no policy identity to refuse, holo3's |
| `payload-union-retry-intake-18` | holo1 | ABSENT | integrity | The mop-up supersession contract (extension-only, byte-exact, never revise a com | accept the loss for the algebra — there is no second namespace in holo3 for it to guard, and v1's ow |
| `payload-union-retry-intake-22` | holo1 | ABSENT | integrity | The attempt-record validation contract and the per-child outcome ledger | accept the loss for the validation clauses — they guard a durable record holo3 does not keep (attemp |
| `scheduling-18` | holo1 | DIVERGED | integrity | Determinism of the certificate set under scheduling order and worker count | keep holo3's - the narrowing is ruled, documented and deliberate, and the replacement invariants (pa |
| `close-15` | holo2 | ABSENT | integrity | D16 surplus audit — re-encoding every certified symbol of every solved block to  | accept the loss. By its own contract it can never change an outcome, and the wrong-certificate quest |
| `extra-17` | holo2 | ABSENT | integrity | Whether a resume is allowed to reuse durable facts written under a different pol | port a minimal form now: stamp the format row id and the tree describe string into facts.npz and ref |
| `placement-12` | holo2 | ABSENT | integrity | Cold's transform residency — the lease, the resource key, and the per-fire trans | accept the loss — the lease was never gated on in holo2 either, and the store it would have governed |
| `payload-union-retry-intake-04` | holo1 | CARRIED-DIFFERENT | integrity | Never sum the same physical capture twice (the v0.27 fix and the duplicate-sourc | keep holo3's, plus the one-line assertion in _combine that the component capture ids are distinct. T |
| `payload-union-retry-intake-29` | holo1 | CARRIED-DIFFERENT | integrity | Duplicate re-ingest and the one-DPI-per-source refusal | keep holo3's, and record the scope difference rather than a loss. |
| `refinement-05` | holo2 | CARRIED-DIFFERENT | integrity | The no-op guard — refusing a revision that did not move | keep holo3's, and fold the missing half into refinement-04's guard rather than as a separate mechani |
| `extra-20` | holo2 | DIVERGED | decides-order-only | Whether a window that has been retired can ever come back | keep holo3's |
| `scheduling-07` | holo1 | CARRIED-DIFFERENT | decides-order-only | Tail class rank M > R > U vs the 200 / 210-220 / 230-240 price bands | keep holo3's, and hand the five-tile gap to the refinement family rather than paying for it here. If |
| `evidence-ownership-08` | holo2 | CARRIED-DIFFERENT | decides-order-only | Payload lane premium — what a decode over a given rung costs | keep holo3's. The two rules agree on every single-dpi stack and differ only on mixed-dpi unions, whe |
| `placement-28` | holo2 | CARRIED-IDENTICAL | decides-order-only | Placement takes no re-work / aging term | keep holo3's behaviour and open the escalation door as a separate, gated line. This is the residue r |
| `pricing-04` | holo2 | CARRIED-DIFFERENT | decides-order-only | COST_INGEST = 10 — a declared scan converted to its resolution ladder as priced  | keep holo3's, and record the gap. What would settle it: a multi-capture holo3 run already writes per |
| `pricing-11` | holo2 | CARRIED-DIFFERENT | decides-order-only | COST_REFINE = 200 — pose re-work priced at the top, 'after the ladder' as an eme | keep holo3's. The flat price makes the ruled property unconditional and no artefact suggests the lan |
| `pricing-12` | holo2 | CARRIED-DIFFERENT | decides-order-only | The payload lane premium of a UNION attempt — dearest component vs shallowest ru | keep holo3's, and record the delta. The whole payload band is 20..28 and sits under every placement  |
| `pricing-20` | holo2 | CARRIED-DIFFERENT | decides-order-only | What the re-read after a pose revision costs | keep holo3's. Re-reading revised geometry early is defensible on its own terms (a corrected pose mak |
| `refinement-12` | holo2 | CARRIED-DIFFERENT | decides-order-only | Re-arm and spend identity — what makes refinement ask again | keep holo3's. The e029 post-step-2 number is the honest cost of the widening (4x the fires for 1.16x |
| `refinement-13` | holo2 | CARRIED-DIFFERENT | decides-order-only — | The price of refinement and its rung premium | (a) now, with the justification restated honestly as a deliberate reordering rather than a fix, and  |
| `close-10` | holo1 | ABSENT | operational | The e028 verified-close trap — a retained VERIFIED close must re-ask the fountai | Accept the loss. The mechanism exists only to service a durable close record holo3 deliberately does |
| `close-17` | holo1 | ABSENT | operational | Close detach — reopening a terminal state so accumulation can continue | Accept the loss. Record the reasoning so the doctrine is not re-derived later, and carry the load-be |
| `close-10` | holo2 | DIVERGED | nothing observable | The default-mode exhaustion consult — holo3 forces one unconditional full close  | keep holo3's and close the question. Record the proposed one-clause fix as unnecessary rather than a |
| `close-12` | holo2 | DIVERGED | nothing observable | What happens when the close finds an integrity failure — a durable terminal reco | port only the narrow half. Wrap the run loop so the finishing step still writes its products, then r |
| `close-12` | holo1 | CARRIED-DIFFERENT | operational | Rank reporting for unsolved blocks — exact GE rank vs the have-floor | Keep holo3's, and say the sentence out loud in the ruling and in the operator string: holo3's 'needs |
| `close-20` | holo1 | CARRIED-DIFFERENT | operational | Certificate→close-input conversion and its mint-once memo | Keep holo3's - a one-line ruling. If the consult ever shows up in a run's accounting, the fix is one |
| `done-gate-02` | holo2 | CARRIED-DIFFERENT | nothing observable o | One pose per window — the latest, never the union of an extent's poses | keep holo3's. The hazard the rule exists to close is structurally impossible here, and the only way  |
| `done-gate-12` | holo2 | ? | ? | The colour gap — window-granular done-ness cannot suppress a per-lane colour row | keep holo3's for this campaign, and record the gap as a scheduled line rather than a retirement bloc |
| `pricing-19` | holo2 | ? | ? | The escalation door — plugin-owned multiplicative re-pricing on six rows, and th | Fix and confirm on the simulation. This is an omission, not a design: the row declares 180 and 170,  |
