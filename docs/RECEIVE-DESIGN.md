# RECEIVE-DESIGN v0.59 — holo Track 3 production read-back

Retired 2026-09-05. This was the normative design of the v1 receiver,
`src/holo/receive`, which holo3 superseded and which was deleted at `284ae3e`;
from that sha this document is historical. It stays as the record of what was
measured and ruled here — the E021-E023c constants, the colour-uplift campaign,
the version ledger's rulings — and nothing below it has been rewritten, so read
every present tense as of that date. The living receiver documents are
`src/holo/receiver/docs/API.md`, `src/holo/receiver/docs/SCHEDULE.md`, `src/holo/receiver/docs/DIAG-DESIGN.md` and
`src/holo/receiver/docs/PAGE-DOMAIN.md`; the mechanism-by-mechanism map from v1 to holo3 is
`src/holo/receiver/docs/retirement_docs-2026-09/HOLO1-MAP.md`. Cold format discovery (§8) was
archived rather than deleted, as a later-port candidate:
`docs/archive/holo1/discovery/`.

Status: **the numerical receiver and the §10 diagnostic implementation are
operational with an explicitly provisional historical policy; physical
production qualification is not frozen; the diagnostic implementation has
production-runtime ideal-fixture parity plus source-local/synthetic failure
qualification, and its operator presentation has been design-reviewed against
the historical E023c view and a current Holo synthetic run, but it is not a
physical production-capture or full-volume performance qualification**
(2026-07-28).

This document is normative for `src/holo/receive`. It extends the clean v0.7
baseline and replaces the v0.1–v0.3 description of the discarded first
Track-3 implementation. There is one receiver, no compatibility path, and no
ideal-capture production fallback. The E021, E022, E023b, and E023c
experiments and the old `paperholo` library are provenance and comparative
test material; the production generator, receiver, runtime, and CLI import
none of them. Qualification-only differential oracles may import historical
code but never enter the runtime graph. Numerical deviations from known-best
receiver behavior require an explicit design amendment and comparative
qualification.

`HOLO-DESIGN.md` remains authoritative for format v1. In particular, the
receiver consumes the amended counter-addressed metadata equations from
§13.16 and stores `(counter, certified_bit)`, never `counter % 24` residues.

## Version ledger

One line per version; full amendment text lives in git history and
`docs/REASONING-LOG.md`. Every body section below states the current rule
exactly once; superseded wording is not restated.

| Version | Date | Decision |
|---|---|---|
| v0.1 | 2026-07-20 | initial Track-3 production read-back design and build sequencing |
| v0.2 | 2026-07-20 | review-panel adjudication; correlation-lane P0 confirmed |
| v0.3 | 2026-07-20 | described the first Track-3 build, later discarded (HOLO-DESIGN §13.17) |
| v0.4–v0.5 | 2026-07-21 | clean reconstruction + operational provisional policy; v0.5 landing numbers in §12.1 |
| v0.6 | 2026-07-22 | causal diagnostics (§10); storage model superseded 2026-07-26; cost re-review kept in §10.6 |
| v0.7 | 2026-07-25 | placement-scoped known-position BCH quarantine at the E022→E023b boundary (§5.4); clean baseline replacing the v0.1–v0.3 text |
| v0.8 | 2026-07-25/26 | selective BP150 fixed per lane (§6.3); external-view/evidence-group model removed; state reduced to non-derivable facts |
| v0.9 | 2026-07-26 | authority audit done; one-policy pipelines; derived checkpoints/dead residue removed; diagnostics invocation-local |
| v0.10 | 2026-07-27 | fixed operator status block + four equal panes replace the audit-heavy live composition; detached audit retained (§10.3) |
| v0.11 | 2026-07-28 | operator review: white double-buffered view, glyph-free fills, address bit counts, terminal-frame delivery, quieter working placement |
| v0.12 | 2026-07-28 | RETRACTED — incorrect “continue after verified” reading of `--complete` |
| v0.13 | 2026-07-28 | corrected `--complete`: defer-only fountain check/solve, never reopens verified state, no other policy change (§8.1) |
| v0.14 | 2026-07-28 | result-exact work boundary operational (terminal-key rejection, byte-exact refinement reuse, count-only deferred status) — ordinary optimizations, not extra `--complete` behavior (§§7, 8.2, 10) |
| v0.15 | 2026-07-28 | CMY8 one-tile p120 contract replaces the 300-dust-label cliff (§6.2); certificate feedback strictly cross-barrier; wholly terminal region/owner pruning (§8.2); Pane-B footprint-only completed lanes (§10.3.3) |
| v0.16 | 2026-07-30 | leaned, current-truth-once; semantics identical to v0.15 |
| v0.17 | 2026-07-30 | stream-generic payload engine registered (§6.4, KISS task 10): one per-tile/per-stream engine for K/CMY7/CMY8, detectors behind a bounded-per-stream-LLR contract, color fork scheduled for deletion; acceptance = the seven-coding real-payload gate net |
| v0.18 | 2026-07-30 | §6.4 engine BUILT, color adopted (one vocabulary, subclass folds); K-schedule adoption recorded as residue behind the certificate/attempt family unification — no adapter shims (validation-boundary ruling also governs readability) |
| v0.19 | 2026-07-30 | FAMILY UNIFICATION EXECUTED (user: no legacy/shims/backward obligation): one certificate identity + minting for every codec; K mints records directly (payload.attempt_k_tile) and rides the engine via a store-backed leaf; records.CertificateStore (stream-aware, work_key-keyed); ONE close-input shape (CertifiedStreamSymbol) and ONE divergence pairing loop with per-codec kernels; TileCertificate, the old K store/schedule, and all conversion adapters deleted; K payload policy v8 |
| v0.20 | 2026-07-30 | survey angle hints removed (user ruling): producer-only output with no runtime consumer — placement derives pose itself; `_angle_hint`, the SurveyRegion/SurveyRegionRecord field, and the e021 gate's angle comparison deleted; state schema 22 |
| v0.21 | 2026-07-31 | truth-alignment amendments from the E022+ gap audit, no semantic change: §5.2 states the rival/gap bar is cold-route-only (historical E022-v2 behavior — rivals reported only where actually searched); §5.1 rot90 ownership corrected to `placement/search.py`/`placement/reference.py`; §5.3 policy-identity sentence aligned to the kiss hand-bump ruling with the frozen numeric row now executable-pinned in `tests/holo/test_placement_policy_golden.py`; §11 gains the missing E023 row |
| v0.22 | 2026-07-31 | PLACEMENT-IMPROVEMENTS execution. Word-route widening (§3.1-3.3): Stage A sweeps every full 64-cell slot (declared 147,456/window under the α=1e-3 ceiling 581,074; 3-row envelope 442,368 → 7.6e-4; a fourth row refuses at construction); window-wide `bch_min_mask_fraction` gate removed (per-phase ≥90/100 floor is the slot protection; the config field is deleted — tuning data, not identity); global errors-first candidate ordering (ties: oriented row-major slot, rot_k, phase); word gate identity → `holo-v1/e022-single-word-multi-slot-union-bound`. Cold-search exact-cost items (§2.1-2.3) executed under the standing §5.3 caching allowance: winner-only second peak, hoisted rfftn kernel/page transforms — bit-identical, pinned by `tests/holo/test_cold_search_exactness.py` against a verbatim legacy reimplementation; §2.4 stacked batching rejected (strided-batch FFT kernels not provable bit-identical by fixture). Comparative qualification vs the pre-amendment receiver on real corpus remains owed before any freeze |
| v0.23 | 2026-07-31 | frontier scheduler (PLACEMENT-IMPROVEMENTS §1.1-1.3): wave-front window order (expand from accepted poses; layout order until the first anchor), nearest-first anchor ordering in chain, and region-wide DEFERRED COLD — a window whose cheap routes fail parks until no chain/lower/word progress remains anywhere in the region; cold then runs one window at a time (best support first), re-opening the chain re-pass after each acceptance (already-tried anchors excluded per window, so re-passes pay only for new anchors). Admission bars, budgets, floors, and per-route domains are UNCHANGED — scheduling only reorders and defers. Synthetic measurement (`tests/holo/test_placement_frontier.py` + `tests/holo/_bench_placement.py`): a two-window fragment with word-killed slots places 2/2 with 0 cold searches (sequential ladder: 1); §2 cold caching measured 1.33-1.65x at P=4-64, growing with P, outcomes identical to the legacy oracle. §1.4 certified-footprint deprioritization NOT built (needs cross-lane certificate context; census-gated). Comparative qualification on real corpus owed |
| v0.24 | 2026-07-31 | §5.3 report-exposure duty closed: `ProductionAddress.route_domain_report` resolves the declared per-route domains, per-parity floors, gate row, and envelope exactly as the runtime does, and `--diag`'s `report.json` publishes it as `placement_route_domains`; pinned in `tests/holo/test_placement_policy_golden.py` |
| v0.25 | 2026-07-31 | §12.1 item 2 measured, no semantic change: post-hoist full-domain rerun reproduces the 0.176 rival exactly and diagnoses it as a cross-page tile-lattice GF(2) alias concentrating 8/31 difference bits in the search parity class (docs/FULL-DOMAIN-RIVAL-ANALYSIS.md); full-domain cold on clean tile-aligned C3 fragments refuses structurally; measured 47.9 s / 9.4 GiB peak RSS at P=312 (page-transform cache ~7.6 GiB — the §2.3 caching's memory cost at full domain); gate decision pending user ruling |
| v0.26 | 2026-07-31 | staged multi-slot Stage A, from the synthetic A/B measurement: the up-front all-slot sweep cost +267 s address CPU (+21%) on the single-page chain vs the pre-widening receiver at identical yield (same 604 certificates bit-for-bit; the multi-slot reach converted all 32 old cold acceptances into word acceptances). The word route now decodes the historical centre slot first and the remaining slots only when the centre stage yields no passing seed; trial order becomes stage-wise errors-first; the declared domain, budget refusal, and union-bound spend are unchanged (declared >= attempted). Measured per window: 3,627 -> 794 ms on the word-succeeding path |
| v0.27 | 2026-07-31 | operator presentation rulings (user declaration): §10.3 presentation authority clarified — presentation rules are operator-serving decisions amendable by user declaration in session, while the §10.1/§10.6 invariants (strictly downstream, no fabricated data, headless purity, timing neutrality) bind unchanged; status rows reordered format/lane/scraps/address/LDPC/fountain (scraps are lane-scoped, so lane context precedes); the address row additionally owns window-queue and deferred-cold progress counters; pane A gains the pending/active/parked/erased work-in-flight window overlay (geometry only; parked = the v0.23 deferred-cold frontier); pane D gains a transient retry-frontier in-flight layer fed by an explicit per-tile snapshot at retry open; primaries-on-white palette refresh; pane C/D tile fills borderless. `docs/DIAG-IMPROVEMENTS.md` is the execution plan |
| v0.28 | 2026-07-31 | K-path multi-capture BUG FIX from the growth audit (docs/RECEIVER-GROWTH-AUDIT.md): ProductionPayload passed the merged frontier as BOTH `run_attempts` arguments, minting SCAN attempts over prior acquisitions' components — the barrier's "scan attempt does not use the current acquisition" refusal then crashed every second same-lane K capture at its first payload commit (reproduced, `tests/holo/test_receive_multicapture_k.py`; color always honored the documented `(new, frontier)` contract; the 3-4-scans/sheet doctrine was unreachable for K). SCAN is now strictly this-capture evidence, the merged frontier feeds UNION, resume semantics unchanged. Plus three exact-preserving growth fixes: the eagerly rebuilt divergence-block index (zero readers, O(N·V) per barrier accept) deleted; the delta-validation index built lazily only for k-v1 deltas that carry divergences; the per-persist full prior-state read short-circuited by a size prefilter. Audit verdict recorded: no quadratic ledgers — requirement 5 delivered; slowdown = the lane resolution ladder plus a linearly growing persist/index tail |
| v0.29 | 2026-07-31 | lazy slot staging (user ruling): the v0.22 global errors-first order dropped — trial order never changes admission, a truthful window's slots imply one placement, and the false-decode corner is union-bounded regardless. The centre slot decodes in the cheap ladder; a deferred window's remaining slots decode at most once, at the cold decision point, best-supported first — any rest-stage acceptance re-opens the chain re-pass, and no cold runs while an undecoded slot remains in the region. Declared word domain unchanged, declared once per window. Plus a result-exact cold early-out when no orientation has an eligible origin (measured: 70-cell subdivision children each paid a full 312-page sweep before dying at the 55/parity floor) |
| v0.30 | 2026-07-31 | WHOLE-WORD RIVAL GATE (user ruling on the 0.176 analysis): the decoy bar and winner gap evaluate whole-word mismatches — all overlap sites, both parity classes — with the decoy bar binding the minimum over the complete historical rival set; rival selection, the winner's parity-split admission, and every numeric bar unchanged. New gate identity `holo-v1/e022-v2-wholeword-rival/session-gap-gate`; ProductionAddress policy id hand-bumped to `v5-wholeword-rival` (constants are data, identity is hand-bumped — standing ruling). Restores the d=27 floor against parity-concentrated cross-page aliases. VERIFIED: the complete 312-page C3 domain now ACCEPTS the exact winner (was rival_gap_failed at 0.176; alias rivals measure 0.298/0.307 whole-word), 50.4 s / 9.0 GiB; the 44-degree 128-cell scrap recovers (winner mismatch 0.0, pose RMS 0.081 cells) — recovery pin in the extended null battery. Real-capture qualification of the new gate remains owed |
| v0.31 | 2026-07-31 | pane-A work-in-flight overlay gains the v0.29 rest-decode state (operator gap report): a parked window spending the remaining-slot word route is drawn as working, not waiting, and a refused rest returns it to parked — the overlay now escalates with the cost of the route in flight (pending / parked / rest / cold), within the existing §10.3.4 palette (cyan is active focus; weight carries cheap-vs-expensive). Presentation only |

| v0.32 | 2026-07-31 | operator gap report, five findings (user declaration). (1) SINGLE COMPOSED FRAME restored: the v0.27 W25 four-file shape is withdrawn — one `frame_pNNN.png` per page, four equal panes in one horizontal row under the §10.3.1 `A ACQUIRED / B PLACED / C ADDRESS / D PAYLOAD` headings, served as `frame.png?page=N&frame=<revision>`; the browser scales it to the window (`width:100%`), so pane width is raster detail, not layout, and the legends stay HTML text under the image. Pane bodies are cached rasters keyed by (scan revision, page revision), and only the default page plus the page a browser last requested are composed — a frame is one encode, so multi-page runs cost less than the withdrawn per-pane shape, not more. Pane A now re-renders only off `survey.*`/`address.*`/`capture.*`, so payload-stage frames stop redrawing the capture underlay. (2) PANE-A TIGHT REGION BOX + piece number implemented as §10.3.3 already required: a detected-but-unplaced scrap had no boundary of its own for the whole address stage, only its fine mask edge. No angle is printed because the survey estimates none. (3) PANE C/D adopt the E022/E023c two-tone chip: soft fill + darker same-hue outline, full grid drawn including untouched tiles, one dark count color, DejaVu/Arial truetype — superseding v0.27's borderless ruling. The §10.3.4 semantic table is unchanged and E023's attempted-failed red is deliberately NOT ported: deep red stays reserved for contradiction. (4) PANE-D STRIPE BUG FIX: the stream-segment split re-inset an already-inclusive tile box, dropping one column of every drawn tile (measured 3.2% of the pane as background stripes at n_streams=1 and 3 alike). (5) K UNDER `--complete`: the §10.4 deferred-close projection was specified but never wired — the barrier handed the view a null progress thunk, so K, metadata trust and block reach were invisible for entire runs (and, in discovery with no selected row, never shown at all). The deferred snapshot now carries `metadata_progress`: metadata K plus count-only distinct-ESI block reach via the existing `distinct_esi_block_counts`, instantiating no decoder and computing no rank; rank and solved state remain explicitly deferred. Default `--diag-panel-width` 440 -> 600, the narrowest width at which every registered row can print pane C's 3-digit counts under the §10.3.3 one-font rule |
| v0.33 | 2026-07-31 | PHASED SESSION SCHEDULE (user ruling; docs/PHASED-SCHEDULE.md is the full design + execution plan, decisions D1-D19 as corrected by the same-day four-lens adversarial review — 16 verified defects folded in). Session execution becomes rung-major breadth-first with a deferred costly tail. (1) The runtime's capture loop and discovery's per-branch inner loop are replaced by a session phase driver: every capture advances through the ascending union of ladder target-ppc values together (rung correspondence by ppc, never ordinal — ladders differ across native DPIs), then a priced mop-up tail runs; the phase cursor is derived from per-capture prefix lengths, never stored. Multiple ACTIVE captures become legal: the three single-ACTIVE gates are replaced by "a resume request must include every ACTIVE capture; new captures may join at any barrier boundary while the session is open". (2) `scale_plan` (still a pure function of dpi + cell_dots) appends one mop-up entry M(Lk) per ladder lane after native; `LaneSpec` gains `mopup_of`; a level's EVIDENCE lane is `mopup_of or lane_id` — block keys/content addresses, frontier selection, attempt/divergence lane binding, and quarantine (now union-accumulating per evidence lane) key on the evidence lane, while plan identity, artifact ids, and durable-id namespaces stay on the unique plan lane_id. (3) Phase-1 lanes run the cheap ladder only; fall-through windows PARK as compact durable ParkedWindow rows (schema receiver 23 / discovery 9: window + fitted-pose geometry, patch ordinal, attempted routes, region cell_pitch_px and the 2x2 reciprocal lattice_f matrix as four row-major floats; no pixels — sampling re-derives bit-exactly from the re-materialized lane raster), named by the committing address artifact and retired at their M(Lk) barrier; an unretired parked row for a committed M-level is a structural load error. (4) M(Lk) mints an empty survey artifact (its address references the base level's durable regions), inherits ALL of its capture's accepted poses AND losing hypotheses across lanes as hints (native-affine conversion; runner class keeps the 6+2 portfolio semantics — without it the loser-revisit channel would be unreachable since every cold moves to M-levels; mop-up-only selector; ordinary lanes keep nearest-productive-prior-lane), mints fresh patch ordinals strictly above the evidence lane's durable maximum (one evidence lane = one patch-ordinal namespace; the barrier refuses collisions), runs hint transport, remaining-slot word decode, and cold under the PLACEMENT-IMPROVEMENTS §3.5 price rule (cold first iff the declared cold domain's page count <= cold_first_max_pages, policy data, default 1), chains among its own acceptances, subdivides on cold refusal (children seeded from the persisted lattice_f matrix), runs its own per-level §5.4 known-position firewall, re-samples base-accepted windows as calibration/context labels only (ownership stays pass-ordered: committed cells are never re-owned), and harvests payload at the base lane's aperture under the ordinary v0.28 SCAN/UNION contract; retry150 stays confined to the M-level's own delta. A mop-up block may replace a live same-evidence-lane block only as a strict-superset extension agreeing exactly on every previously-observed cell — committed cells are never revised. The v0.29 no-cold-while-undecoded-slots rule re-scopes to the M-level visit; a window's Stage-A domain is declared once per window LIFETIME, at the level that first samples it. (5) Tail order: across captures by parked EV (support-weighted descending, ties by request order), within a capture in plan order; preemption granularity is the M-level visit — a verified close is terminal for the driver. (6) CLOSE-ATTEMPT SCHEDULE (ordinary mode): metadata-terminal states consult UNCONDITIONALLY (precedence over every other clause — a metadata conflict is detectable at two counters, long before trust); otherwise the per-barrier close runs iff metadata is trusted, every (stream, block)'s distinct certified ESIs reach K_b (skipping is exact — below count cannot be at rank), and, after a want_more attempt this invocation, every then-rank-short (stream, block) gained at least its then-reported shortfall in distinct ESIs. NO surplus buffer — the drafted B=2 was WITHDRAWN on adversarial review: rank gain is bounded by distinct-ESI gain, so the exact shortfall baseline never skips a verifiable barrier, while any B>0 can forfeit a closable session at its final barrier and creates open-but-solvable states that ordinary load reproduction refuses as corruption; the invocation-transient baseline degrades to the count gate alone on resume, never to a skip. §8.1/--complete is untouched: no mid-session fountain consult, the full tail runs, one final close. (7) Native rasters are held open per invocation across phases. CaptureStatus derivation is unchanged (M-levels count toward COMPLETE; a verified-preempted session legally leaves ACTIVE captures; `--complete` runs the whole tail — its exhaustive meaning). Scheduler identity `holo/phased-session/rung-major-v1`; ProductionAddress policy id hand-bumped `v6-phased-schedule`; golden pins updated; every pre-v0.33 state refuses (plan change + schema bump, no migration). Route labels, component inheritance, attempt identities, and redundancy bookkeeping deliberately diverge from any capture-major replay; admission bars, budgets, floors, per-route domains, and rival sets are UNCHANGED. Diag (D14; execution rebases on the in-flight diag split): session phase indicator (scheduler event + context field, lane-row tail), pane-A per-chip plan-level digit + parked-for-mop-up overlay state, count-bounded cold/rest heartbeats (<=64 emissions/sweep, never milestones), a mopup.* event family preserving address.final's finality, parked rows riding the barrier snapshot. CLI: durable parked-inventory epilogue (counts + support distribution; conditional rescan hint) — a deliberate new durable-advice row in the §10.7 availability table. Comparative qualification vs the capture-major receiver on real corpus is owed before any freeze; the cold-necessity counterfactual and the §1.4b census are the measured gates. Housekeeping: stale §8 schema sentence corrected (said 19; code stood at 22 → now 23/9), title bumped, --complete wording de-lane-shaped; post-review sweep: §5.4 firewall re-scoped per level, §6.1 capture-major attribution fixed, §10.4 event families corrected (payload.color.* retired; session.phase/mopup.*/heartbeats added), §10.5 parked-chip clearing exemption, §10.7 parked-inventory availability row added, §12.1 item 2 un-staled to the v0.30 resolution, §3 flow lines count-gated, and WindowOutcome gains `parked` with non-terminal region states (D19). SEPARATE RULING OWED (D16, not in this amendment): the payload GF(2) solver never checks surplus-equation consistency — a wrong certificate in a pivot bricks terminally without localization; recommended report-only post-solve surplus re-encode audit awaits a doctrine ruling |
| v0.34 | 2026-08-01 | D7 + D16 rulings executed (user determinations 2026-08-01). D7 LABEL RE-SAMPLING (ruling: implement now): PoseRecord grows the exact lane-frame re-sampling carrier — window ints plus the fitted lane AffinePose and PoseSegment stats, mirroring ParkedWindowRecord — because the canonical native affine rounds once on conversion and cannot re-derive the lane sample bit-exactly. M-levels reconstruct their evidence lane's placed windows (accepted and redundant) as calibration LABELS: persisted pose -> bit-exact re-sample -> identical rescore -> identical audit, all pure; AddressResult carries transient `label_placements` (id-disjoint, observation-free, never owners, never firewall inputs); the region crop pitch pools placements UNION labels — the single-pass aperture; `apply_region_context(rows, label_rows)` fits over the union in ascending patch-ordinal order and profiles rows only; the refined-reuse path pools labels into its pitch/filter signatures and re-derives them for affected regions. PINNED: label reconstruction is bit-exact (pose, audited cells, page footprint) and the split-region fit equals the pooled single-pass oracle exactly — decision offsets/supports and profiled LLRs identical (tests/holo/test_phased_schedule.py). D16 RULING (ii) REPORT-ONLY SURPLUS AUDIT: after every solve, each certified symbol of a solved block re-encodes from the solved sources (one bulk frozen-row draw per block; inherently covers the systematic fast path whose repair symbols the solve never consults); mismatches surface as CloseSurplusInconsistency (stream, counter, page, tile) through CloseResult/CloseProgress and the CLI epilogues — a VERIFIED run now discloses masked wrong certificates (payload still SHA-correct), an integrity failure gains a localization list for the postmortem. PROVABLY OUTCOME-NEUTRAL: with-vs-without equivalence pinned across five scenarios (status, payload, blocks, reason, CloseRecord); the audit is observation, never detection — an exactly-K brick keeps an empty audit and a corrupted pivot can evade when the lone dependent row is blind to its direction (frozen-keystream fact, pinned). Fatal-vs-quarantine adjudication remains an explicitly open post-08-04 doctrine ruling, to be made with the incidence data this audit now gathers |
| v0.35 | 2026-08-01 | POOL LAW (PAYLOAD-REWORK-PLAN Phase 1; PAYLOAD-IMPROVEMENTS §1 resolved by the §13a ruling): one region pool law L1–L6 (§8.2) replaces the c7aa340 window-granular terminal skip's fit erasure — L1 wholly-terminal regions drop before image work (unchanged); L2 a certified-complete window in a mixed region does no payload work (no owner rows/blocks/attempts — the c7aa340 savings stand) but routes through the D7 label channel full-window, its word/filler sites re-joining the region context fit; L3 labels never terminal-gated in ANY path (gen-0's gating was incidental and never substantiated; the refined path's ungated behavior ruled correct); L4 zero-payload windows label-only always (the certificate-existence knife edge dies); L5 pitch/filter-signature pool = placements ∪ all label rows, identical in gen-0, refined-reuse, and certified-refinement replay — the reconciled-window pool deletion and the promoted-only replay pool are gone, making the refinement:01 RefinementIntegrityError pool-flip brick structurally impossible; L6 same law for K/CMY7/CMY8 (CMY8 terminality per work key). K paths shipped in this amendment (stage 1a); stage 1b (same pass) shipped the color half — the window-granular skip color never had plus its D7 label wiring: certified-complete color windows and D7 label placements join the region QDA/PAVA fit and pitch pool as furniture-site (word/dust) label rows carrying certificate-lineage dependencies, never payload-sampled and never owners/blocks/attempts, while registration anchoring stays on payload rows (sparse label sites have no complete 3×3 in-row neighbourhoods to measure — and a fully-certified window consequently no longer contributes its prior-certified payload states to the fit, only its furniture). K payload policy hand-bumped `paperholo-e023b-e023c-v8` → `v9-pool-law`; color policy hand-bumped `provisional-v4` → `provisional-v5-pool-law` with the literal now fully spelled instead of interpolating a live constant (color-payload:09). Old states refuse; no migration. Acceptance instrument: `tests/holo/test_pool_law_oracle.py` — the five Phase-0 law xfails flipped, the c7aa340 skip pin consciously replaced by its label-contribution counterpart |
| v0.36 | 2026-08-01 | CLOSE/D8 WIRING REPAIR + CLOSE PLUMBING COLLAPSE (PAYLOAD-REWORK-PLAN Phase 2; PAYLOAD-IMPROVEMENTS §2 crash cluster + §4.1 D5 disclosure + lens-coverage:03). (1) CRASH REPAIR, correcting v0.32 ledger item (5) and PHASED-SCHEDULE §5b deviation 4 as recorded: both `metadata_progress` thunks fed raw durable `TileCertificateRecord` rows where `CertifiedStreamSymbol` is required — the D8 gated-skip progress now consumes the already-converted rows and the deferred-barrier snapshot converts inside its lazy thunk, so the D15/D16 epilogues and every `--diag` pane snapshot survive gated barriers (on the real corpus all 16 checks were gated, so every barrier crashed its snapshot builder). A NON-raising metadata-terminal state (malformed/unsupported) now consults instead of reaching `VolumeCode(None,…)` (TypeError): `close_count_status` returns (ready, counts) with counts=None exactly on the metadata-no-K states, and the gate treats no-counts as the documented metadata-terminal precedence. The count-only marking is single-sourced as `CloseProgress.count_only` (set by `metadata_progress`; the close snapshot's `deferred_counts` derives from it; `close_factory` lost its parameter), so a gated skip renders distinct-symbol reach — never a fake rank 0/N — in the fountain row and the CLI shortfall epilogue's new count-only shape. Reproduction paths (deferred terminal replay and the verified non-deferred resume) now populate the close-progress sink, so reruns of terminal states re-print the D15/D16 epilogues. §8.1 documents the gate's behavior at the one deferred final consult. (2) ONE CONVERSION POINT (makes PAYLOAD-MEASUREMENTS §3's memo sentence true): `ProductionClose` memoizes `certificate_for_close` per `certificate_id` (records immutable + content-addressed; mint-once), one `close_count_status` pass builds at most one VolumeCode per stream per consult (the gate and the shortfall baseline previously each built their own), and `close_volume` validates each certificate once instead of once per stream (×3 on CMY8). Result-identical. (3) `BlockStatus`/`CloseBlockProgress` MERGED to the one `CloseBlockProgress` dataclass (stricter validation + `rank_shortfall` kept); `CloseResult.blocks` carries it directly and `from_fountain_result` passes rows through instead of copying. (4) K ADVISORY PRECLOSE wired exactly as color's (ruling 6.6; engine flag inherits the `--complete` suppression); K payload policy hand-bumped to the fully spelled literal `holo/e023b-e023c-payload/paperholo-e023b-e023c-v10-pool-law/needmap-region-prune-label-rows-owner-prune-acquisition-components-max60-preclose-selective-retry150-unified-cert-identity`. (5) D5 DISAGREEMENT COUNTER (ruling 11.2, health canary only — no gating, no thresholds; doctrine deferred to post-08-04 incidence data): `supersede_with_committed` returns (block, dropped-disagreement count) — fresh observations at committed cells whose float32 value bytes OR origin row differ; full-agreement collisions excluded — aggregated by `apply_mopup_supersession`, carried through `PayloadProduct`/`BarrierDelta`, folded into the new durable `SessionCounters.mopup_dropped_disagreements`, surfaced as a `payload.complete`/`color.*` event detail, a nonzero-only CLI epilogue note, and beside divergences on the diag LDPC row. SessionCounters schema change: pre-v0.36 states refuse; no migration. Pins: tests/holo/test_close_schedule.py (D8 want_more baseline skip/consult, rewound reset, metadata-terminal both forms, gated-skip count-only shape, replay sink, conversion memo, K preclose ×3, counter fold + epilogue) + the deferred-observer and gated-skip regression pins in test_phased_schedule.py |
| v0.37 | 2026-08-01 | PAYLOAD-REWORK-PLAN Phase 3 exact-preserving hoists (PAYLOAD-IMPROVEMENTS §6/§7; one lettered clause per lane, every clause result-identical with its own exactness pin). (D) PERSIST BLOB CACHE + SINGLE ENVELOPE SERIALIZATION (plan 3.6, growth-audit row 3): the state codec's per-barrier persist no longer re-serializes and re-zlib-compresses every immutable `EvidenceBlock` — the compressed+base64 inline form is memoized per block content address (`block_id`; blocks immutable + content-addressed, so the inline form is a pure function of the digest), the cache is armed only during `_save_typed` encoding and pruned to the just-persisted live block set after every save (bound = one barrier's blocks, invocation-local); and the persisted payload JSON is serialized ONCE and spliced into both the digest preimage and the envelope in canonical key order (canonical dumps are compositional, so the spliced documents are byte-identical to whole-document dumps; the load path still recomputes the authoritative digest through the unchanged generic encoder). State file bytes, digests, and load behavior are unchanged. Pins (tests/holo/test_receive_state_codec.py, naive pre-change encoder kept as the test-local oracle per the cold-search precedent): file-level byte identity vs the naive encoder on a nontrivial blocks-bearing session state and on an adversarial-values state (non-ASCII magic, escaped strings, float extremes), `to_bytes`/`zlib.compress` counted ONCE per block across two persists + cache pruned to the live set, and the persist digest equals `authoritative_state_sha256` of the loaded round-trip. (B) MINT-ONCE IN THE BLOCK FAMILY + PRINTED-FIELD CACHE + PRECLOSE ALIGNMENT (plan 3.1/3.2/3.3; growth-audit A3/A4; findings refinement:06, engine-records:04/05, §6.2 preclose ordering): the `EvidenceBlock` content digest is computed exactly once at the authoritative construction site — `_block_from_encoded_rows` hashes the body it just serialized and the durable-boundary `from_bytes` keeps its body-vs-trailer verification — while `__post_init__` no longer rebuilds and re-hashes the body (interior validation via types/immutability/tests per the kiss validation-boundary ruling; structural checks stay); the state-load triple SHA (growth-audit A3) collapses to the ONE `from_bytes` boundary check — `_decode_blob_items` drops its pre-hash and binds the manifest identity through the already-verified `block_id`; `TileAttemptView`'s combined tensor is summed once in `tile_attempt_view` and passed through trusted (the `__post_init__` re-sum equality check is gone — growth-audit A4). PRINTED-FIELD MINT-ONCE CACHE: `records.printed_cells_from_record` memoizes the LDPC re-encoded 64x64 field per `certificate_id` (the identity binds spec_id, seed, address, stream, and the certified user bits; ~4 KB/certificate) and serves one immutable array, so divergence pairing (previously once per (certificate, block) pair) and `CertificateFrontier.from_certificates` (previously eager once per lane consult) each re-encode once per certificate MAX per process, with validation running at the mint; `refine_address_once`'s empty-domain early-out is hoisted ABOVE frontier construction, so an empty-promoted or certificate-less lane builds no frontier and re-encodes nothing (degenerate-input note: conflicting prior certificates paired with an empty promoted domain now return the empty refinement instead of raising — no work is scheduled, so no conflict is adjudicated there; nonempty domains keep the conflict-fatal path). COLOR PRECLOSE ALIGNED TO K's v0.36 shape: the certificate-less short-circuit runs before any `certificate_for_close` conversion (previously the full prior set converted first); no memo added — the engine consults preclose at most once per run, K parity. All result-identical. Pins (tests/holo/test_mint_once_payload.py, naive computations kept as test-local oracles per the cold-search precedent): digest counted once per construction and byte-identical to the independent re-serialization oracle via both construction paths; load-boundary tamper and manifest-identity refusals re-pinned; exactly one SHA per inline blob at state load; view tensor byte-identical to the naive component-sum oracle with each component materialized once; printed-field cache byte-identical to a fresh naive re-encode, identical-object on re-consult, read-only, and call-counted once-per-certificate through divergence pairing and frontier construction; empty-promoted refinement builds no frontier; a certificate-less color preclose converts nothing. (A) RE-AUTH STAT-MEMO + DERIVED-LANE RASTER LIFETIME (plan 3.3/3.4; PAYLOAD-IMPROVEMENTS 7.2 and 6.3): the §8 re-authentication law keeps its one-check-per-retention-barrier shape, but the detector is now stat-based with cryptographic escalation — `open_capture` retains the ingest-verified (dev, ino, size, mtime_ns) tuple on the Raster; `verify_source_unchanged` fstats the path, a full tuple match skips the byte re-stream (memo hit), ANY difference escalates to the full re-stream + SHA-256 comparison, and the memo refreshes only after a passing full check (PHASED-SCHEDULE §5a-bis candidate (ii) SHIPPED — the measured ~267 s of real-corpus re-hash residual; caveat on record: a deliberate rewrite forging size+mtime_ns onto the same dev/ino is undetected — accidental-mutation threat model, the code is not adversarial). RASTER LIFETIME: a derived scale lane is streamed once and pooled per (native raster, lane label, derivation kind) for the invocation (`DerivedLanePool`, file-backed temp mmaps, explicit runtime release at drive end), so the M-level visit reuses the base visit's bit-exact derivation instead of re-reading native; the phased scheduler consults parked-emptiness BEFORE first materialization, and a parked-empty M-level receives a metadata-complete `LazyDerivedRaster` that derives only if a consumer actually reads pixels — on the production no-consumer paths (empty M survey/address/payload) nothing does, so it never materializes, and any unexpected read derives exactly (exactness by construction). All result-identical. Pins (tests/holo/test_receive_reauth_memo.py + test_receive_raster_pool.py, wrapped `_sha256_file`/`_derive_level`/`Raster.crop_native` call counters): a memo hit streams zero bytes, any stat delta escalates then re-memos, mutation is refused at unit level and end-to-end at the runtime commit (fast-pin port of the orphaned `_source_mutation_case`), pooled reuse returns the same object byte-identical to the naive re-derivation oracle, a full phased run derives each lane exactly once with full-frame native reads == derivations and releases at drive end, and a resumed parked-empty mop-up tail completes with ZERO derivations (C) K/COLOR VECTORIZATION UNIFICATION (plan 3.5; findings lens-efficiency:04, payload-windows:05, color-payload:04/06, color-upstream:07/10, evidence-core:04): ONE owner freeze — `payload_model.freeze_page_owners` is the shared K/color one-owner competition (ascending (heldout_logloss, patch_id), first observer owns; np.unique first-occurrence over y*width+x keys = the historical dict setdefault in row-major cell order), called by both `freeze_capture_evidence` and color `_freeze` (degenerate-input notes: an accepted K window whose payload-cell set is empty no longer manufactures an empty owned page — the historical dict path crashed on it — and out-of-page K owned candidates now refuse with the shared PlacementModelError "payload: owned candidate lies outside the page" instead of silently owning; color keeps its bound check under the shared message). ONE frontier→block converter — `evidence_blocks.blocks_from_owner_pages` encodes each page's owned value tensor once as canonical little-endian float32 and slices per row (byte-identical to both codecs' per-element encodings); `blocks_from_frontier` and `color_blocks_from_frontier` are thin wrappers, and the color converter's per-window owner-provenance re-verification is deleted (mint-once: validated at frontier construction on immutable arrays). `CaptureEvidence.__post_init__` owner validation vectorized on the color template (batch per-window cell/LLR comparison; first-invalid row and message class preserved) — previously a per-cell Python loop paid up to 3x per K lane. `apply_region_context` physical ids via strided-int64 np.unique/searchsorted (`_physical_cell_ids`; numeric key order = lexicographic (page, y, x) once each axis is offset to zero; the tuple/dict enumeration survives as the overflow fallback). Color hoists: ownership + the deterministic fit split computed ONCE per region (`color_fitting._owner_selection`) and gathered per fit (baseline + registration-corrected; color-upstream:07); the divisor probe and the base features share ONE native window read (`_window_raw_crops` — previously two identical crops per window); emission masks computed once at open_flags and reused by the emit loop (color-payload:06); p120 furniture geometry cached per family seed (`_color_site_lookup` + `_payload_site_mask`, the color analog of the K `_site_lookup` cache; color-payload:04); and `fit_cmy8_detector` no longer fits PAVA maps for planes the QDA guard zeroes (degenerate/clipped → neutral map, `llrs` writes the erased column directly; color-upstream:10 — the historical path computed the map and then overwrote the column with zeros). All result-identical; certificates and recovered bytes unchanged on the 0.3 synthetic corpus (49 certificates, verified, both arms). Pins (tests/holo/test_payload_unification.py; naive computations kept as test-local oracles per the cold-search precedent, and the owner-freeze winners HAND-CONSTRUCTED per the audit's differential-cancellation warning): K and color freezes vs hand-built (loss, patch_id) winners over overlapping windows including a loss tie and a refused K window; out-of-page refusal; vectorized owner-validation refusal parity vs the naive loop over tampered llr/row-index/window-index/refused-owner corruptions; K and color converter block bytes + block ids byte-identical to the naive per-element oracles; `_physical_cell_ids` vs the naive tuple/dict oracle (multi-window, multi-page) plus an apply_region_context differential under the monkeypatched naive ids (decision id, every decision field, and profiled rows identical); `_owner_selection` + gather vs the naive `_known_owners` oracle including a second gather through the frozen selection; furniture caches byte-equal to fresh naive derivations, identical-object on re-consult, read-only; PAVA-skip fit-count pins (clipped plane → 2 maps, degenerate → 0) with llrs byte-identical to an old-behavior oracle detector; shared window crop equal to the naive probe/base reads, and the bounded-sampling read-count pin re-derived (4 window-sized RGB reads, was 6). Measured (0.3 synthetic decomposition harness, same invocation): payload buckets ownership_freeze 0.52→0.10 s, sampling+calibration+ctx 0.93→0.67 s, block_build+first_attempt 0.41→0.34 s; payload total 1.91→1.15 s (-40%), yield identical |
| v0.38 | 2026-08-02 | PAYLOAD-REWORK-PLAN Phase 4 hammer batch (structure, dead code, doc truth; one lettered clause per lane). (A) DEAD-CODE + DUCKTYPING + TRIVIA SWEEP (plan 4.1/4.3; PAYLOAD-IMPROVEMENTS §5.1–§5.3, §9.2/§9.4–§9.7; every §5 pin re-verified against the v0.37 worktree before acting). DELETIONS, grouped: scheduler — `ScaleCascadeScheduler` (pre-v0.33; IndexErrors on the doubled plan) with its `__all__` export, together with the slow qualification battery's barrier-restart case that drove it (production-drivers:02 — the resumed state carried the cascade-composed policy id and could never pass post-v0.33; the battery keeps its other four cases, case-count pin 5→4; full battery retirement stays Phase 7); evidence family — `EvidenceDoctrineError`, `evidence.unresolved_stream_ids`, `blocks_for_address`, both `stream_llr` methods, the documented `EvidenceBlock.llr_cells` compatibility alias (no-shims ruling; callers use `cell_tensor`) and the `TileAttemptView.cell_tensor_f64` alias property (`llr_cells_f64` is the one name); session — the two kiss-5-orphaned validators (`_validate_block`, `address_fully_certified`), the dead `_artifact_records` helper, and the computed-then-del'd `lane_id` local in `_validate_structural`; detect — `ContextFit.apply`, `Calibration.clamp`, `Calibration.node_llrs`, and the triplicated context clip kernel consolidated to ONE `detect.apply_context_offsets` (certified_refine + _payload_windows rewired; identical float64 math); color — `SharedAffine`/`fit_shared_affine`/`ColorRegistration` (still test-only), `COLOR_DETECTOR_PROFILE`, `normalize_rgb`/`rgb_features` (the >1.5⇒/255 rule now exists once, inline in the color divisor probe), the unreachable best-anchor tie-break (per-key setdefault already dedupes, plain assignment; the tie-break-only patch_id tuple element died with it), and the dead color_divergence imports (certificate_work_index, validate_certificate_record, divergence_identity, Iterable); records/tiles — `CertificateStore.fork`, `records.attempt_view_from_record`, `tiles.CRC_FALSE_ACCEPT` (NOTE: the §10.7 CRC-accounting report it was to feed is UNIMPLEMENTED — the constant goes with its never-built consumer), `tiles.attempt_floor` (the floor logic is inline in both leaves) plus the diag snapshot's computed-then-del'd `attempt_floor` parameter, and `tiles.CertificateIntegrityError`; close — six `CloseResult` convenience properties (terminal, want_more, blocks_need_more, rank_shortfall, metadata_rank_shortfall, metadata_check_shortfall — `verified` is LIVE post-phase-2 and stays), `CertifiedStreamSymbol.address`, and the `_certificate_stream_id` helper with its dead "main" getattr default (the validated type always carries stream_id; direct attribute access); refinement — `SegmentRefinement.target_raw_means` (constructed, never read; four construction sites trimmed); constant branches — production's `detector_profile` local collapsed to the literal `CONTEXT_PROFILE` at both collect calls (wiring pin unchanged), `collect_capture_evidence`'s included_patch_ids if/else call fork collapsed to one call, `certificate_divergence`'s `existing_ids` parameter (production-constant empty) deleted, and the no-op `deduplicate_divergences` wrapper call + function deleted (the ONE pairing loop dedupes by construction); micro-helpers — the FIVE length-framed SHA framer copies collapse to `tiles.sha256_parts_le/_be`, the `fountain_close._stream_profile` clone and `records.stream_profile` collapse to the ONE `FormatSpec.stream_profile` method, the four read-only-array idioms collapse to `detect.readonly_array`, the evidence-arity map exists once (`evidence_blocks.evidence_arity`; color_payload's two inline maps and `_color_kind` rewired), `PLANE_ORDER` exists once (`core.channel`; color_detect/color_fitting rewired, color_registration's copy deleted), and `max(1, 64)` → 64. DUCKTYPING/INTERIOR-DEFENSIVE SWEEP (§9.2 + §9.4, the 'across all stages' ruling): payload_engine's `RecordingLeaf` fully typed (CertificateStore store, typed decode/progress callables, `list[TileCertificateRecord]` ledgers) and `run_attempts`' bare-tuple `retry_open` typed; `close_progress_sink` typed `Callable[[], CloseProgress | None]` end to end, `from_fountain_result(result: CloseResult)`, and cli's two `getattr(res, 'close_progress', None)` ducks call the typed method; the bare 4-tuple owner-page surface became the typed `OwnedPageRows` NamedTuple (both codecs construct it) and `blocks_from_frontier`/`_origin_for_window` are annotated on the real payload_model types with all getattr access deleted; cascade's two `getattr(context, 'spec', None)` unreachable defaults (ScheduleContext.spec is a typed field), production_color's window-getattr triple, and `_note`'s object parameter (now CloseResult) fixed. Interior re-validation DELETED per the kiss validation-boundary ruling: the certified/terminal-address element-revalidation preambles downstream of their `certificate_work_index` mints (`payload.unresolved_region_patch_ids`, `production._prune_certified_k_owners`), the duplicated isinstance preambles in BOTH samplers (`sample_and_calibrate`, `sample_refined_reusing_generation`; the cross-object domain invariants — promoted-domain equality, subset rules — are kept), and `collect_color_evidence`'s `fully_certified_addresses` re-derive-and-compare parameter (ruling 9.5: the callee derives the only legal value from the certificate authority; production_color keeps its local derivation solely for the pruned-addresses Detail). RETAINED as route guards, not interior re-validation: the survey/address/payload stages' `transient` isinstance narrowing (the field is typed `object` and legitimately absent on resumed lanes). Trivia: three positional `ColorRegionSummary` constructions keyworded (16-field record); bare `pitch` renamed `pitch_px` across _payload_windows/color_payload/color_anchoring/certified_refine (public signature renames, no compatibility). NO-LONGER-APPLICABLE at v0.37: `COLOR_PAYLOAD_POLICY_ID` already spelled literally (phase 1's v5-pool-law bump); the ScaleRaster/ColorScaleRaster consolidation was gated on one being dead — both are LIVE (grey vs RGB derivation classes), kept; `CloseResult.verified` live, kept. The PAVA collection-mode ARM inside collect_* remains deliberately: it is the differential test harness footing (quarantine/refined-reuse/pool-law fixtures) — only the wiring-level constant indirection died. Tests that existed only to exercise deleted symbols were deleted or trimmed with the code (stream_llr/blocks_for_address/llr_cells-alias/rgb_features/shared-affine/attempt_floor/unresolved_stream_ids/existing_ids exercises); close-property assertions rewritten against status/blocks/diagnostics; the metadata-close SimpleNamespace fakes now carry stream_id under the typed contract; the raster-pool stub carries a codec_id-bearing spec. Suite green. (B) DOC-TRUTH BATCH (plan 4.4; PAYLOAD-IMPROVEMENTS §4 rows 4.1–4.14 + finding 3.2, every row re-verified against the worktree at v0.37 before editing): RECEIVE-DESIGN §8 drops deleted `session_replay.py` from the module list (adds `session_model.py`), states load as structural validation plus close reproduction — never a causal barrier replay (kiss-5 ruling) — and corrects the durable-state list: attempt/divergence records are invocation-transient and fold to `SessionCounters`, never persisted; §6.1 notes that LLR bounding is enforced at emission (the block boundary validates finiteness only) and that the attempt no-op rule rests on determinism plus invocation-local dedup, not a durable ledger; §6.3's chain now lists the true erasure step (word/filler site cells — no separate metadata sites exist at erasure time) and the informative-bit floor's true pre-decode position, gives the at-most-one-CRC rule its no-durable-spend-once-ledger note, and re-attributes accepted-tile re-encode + certificate-identity validation from tiles.py to the records family (`stream_certificate_identity`/`certificate_record_from_user_bits`/`printed_cells_from_record`, v0.37 mint-once); §6.4 states the as-built color truth — the DOWNSTREAM fork was deleted while the four color files survive re-roled as detection-side modules and thin leaves, both codecs run the one `payload_engine.RecordingLeaf` (`production._KPayloadLeaf` is gone), and the one-owner freeze / frontier-to-block converter are single implementations since v0.37 (the "exists twice" caveat is dead). PHASED-SCHEDULE: D4 gains the watermark clarification (the collision set is base accepted/quarantined ordinals only; parked-ordinal re-use is the mandated case), D5 records the shipped materialization (committed-verbatim plus novel-only supersets, nothing-novel emits nothing, dropped disagreements counted — d2e5281/v0.36) and the validator's extra origin-row-equality strictness plus the numeric-not-byte −0.0 nuance, D13's dead `word_declared` sentence is fixed to the D6 structural reality, D14c heartbeats are corrected to cold-only (`address.cold_progress` is the only family), D15 records the discovery-mode unavailability of the parked epilogue, and §5b's deviation list gains entries 6 (D5 materialization) and 7 (cold-only heartbeats). PAYLOAD-MEASUREMENTS: the §1.1 "+22 s" reading is marked interpretation-not-measured-decomposition (MR-08) and the payload-row "pooled labels" reading is corrected to unattributed variance (color consumed no labels pre-v0.35); the fountain knee pin is re-anchored (MR-02); §3's memo sentence was already made TRUE by phase 2 — recorded, not re-edited (4.3). HOLO-DESIGN: F8 and §7.2 gain the live multistream rank-reserve form reserve = 16 + bit_length(B·n_streams − 1) (`fountain.rank_reserve_for`); §13.26's "DUST ROWS ONLY" is annotated to the shipped dust-plus-prior-certified truth. COLOR-INTEGRATION-DESIGN: the "Calibration rows are dust only" paragraph is corrected to dust plus prior-barrier CRC-certified complete states (policy family `dust20-priorcert-…`, sanctioned by §6.2 here). HOLO-SOFTWARE-ARCHITECTURE: stale `session_replay.py` rows removed, load wording made structural, the persisted-record sentence corrected to folded counters, and a dated re-verification note added (module lists checked against this worktree; the pending file splits will re-touch §4). RECEIVER-GROWTH-AUDIT: dated status preamble — rows 1/2/4 and the K SCAN crash fixed in v0.28/9c9e66d, row 3 and A3/A4 resolved by phase 3, row 5 and A5 resolved by phase 2 (the stale close_count_ready sentence flagged). PAYLOAD-IMPROVEMENTS: EXECUTION status block pointing at the rework plan and the phase 0–3 commits. Two sanctioned wording fixes ride along in src (diagnostics lane, no numerical change): payload_engine.py's stale pre-v0.28 "K passes the whole frontier" stage-2 comment (the unexecuted D18 item, 4.7) and the K retry report's eligible-vs-attempted conflation — `payload.retry150_eligible` now reports the engine's selected retry frontier instead of duplicating the attempted count (4.13). Rows already true at v0.37 recorded as resolved, not re-edited: 4.3 (phase 2) and 4.12 (v0.35 label_placements sentence). (C) FILE SPLITS (plan 4.2; PAYLOAD-IMPROVEMENTS §9.1; kiss-precedent style — bodies moved byte-identical wherever possible, split over the FINAL post-(A)/(B) shapes, zero behavior change). SPLIT MAP (lines before → after): `production.py` 1278 → `production.py` 704 (survey/address stages, `_address_product` + hint helpers, pipeline composition), NEW `production_payload.py` 610 (`ProductionPayload` + `_window_dependencies`/`_certified_k_addresses`/`_prune_certified_k_owners`), NEW `production_close.py` 121 (`ProductionClose` + the v0.36 conversion memo); `_payload_windows.py` 1032 DELETED → NEW `_payload_sampling.py` 465 (window rows/crop/filter/sample, `_site_lookup` + `format_reference_values`, `_scores`/`_calibrate`, `sample_and_calibrate` with the pool-law label routing, APERTURE_CELLS/SCORE_SPREAD_FLOOR), NEW `_payload_context.py` 296 (`apply_region_context`, `_physical_cell_ids`, the context decision records), NEW `_payload_reuse.py` 331 (`sample_refined_reusing_generation`, `_marginal_window`, `_validate_reused_window`). Every receive file ≤1000 lines. FACADE DECISION: NO facades (no-shims ruling; fan-out was small) — `_payload_windows.py` is deleted outright with all importers rewired to the split homes (src: payload.py, color_anchoring.py, color_payload.py, certified_refine.py; tests: refined-reuse, bounded-sampling, payload-unification incl. its `_physical_cell_ids` monkeypatch target, pool-law oracle, phased-schedule, production-policy, `_e023c_fixtures`, `_qualify_runtime_fixtures`); `payload.py`'s public re-export surface is UNCHANGED, so `payload`-level consumers see no rename. `production.__all__` shrinks to `ProductionAddress`/`ProductionSurvey`/`production_pipeline`; `production_pipeline` imports `ProductionPayload` lazily exactly as it always imported `ProductionColorPayload` (production_payload top-imports `production._address_product` — the lazy import keeps the import geometry acyclic), and test_close_schedule/test_receive_production_policy import the split homes directly. ADDRESS-BRANCH DEDUP (lens-kiss:02, executed WHILE the code moved): the mop-up/base ~80-line duplication collapses to `ProductionAddress._resolve_pages`/`._resolve_budgets` + module-level `_address_adapter_callbacks`, and the THREE identical `address.final` 8-detail emissions collapse to ONE `_emit_address_final(result, product)` — the empty-mop-up branch now derives its zeros from the empty `AddressResult` (len/sum over empty tuples ≡ the previous literals; details byte-identical — the one sanctioned tolerance). `ProductionPayload.process` (~280 lines) decomposed into named stage methods `_plan → _sample → _freeze → _blocks → _decode → _retry → _complete` with the typed frozen `_PayloadPlan` carrier — pure mechanical extraction, no reordering, event order and every Detail unchanged. Consult-counting patch sites that relied on the one-module shape (test_phased_schedule's close-gate pin, `_bench_phased`) now patch BOTH `production_close.close_volume` AND `production_payload.close_volume` (pre-split one setattr covered the close gate and the K preclose together). The dead `tiles` import in production.py died with the move. Docs re-pointed: HOLO-SOFTWARE-ARCHITECTURE status note + §4/§4.5/§4.6 module lists, RECEIVE-DESIGN §3 composition-root and §6.1 module sentences, HOLO-DESIGN §9.1 tree. Verified: full tests/holo 881 passed / 35 skipped (identical counts to post-(A)); targeted battery pins (test_receive_qualification), backbone default lanes 3/3, pool-law oracle, payload unification, mint-once, phased schedule, close schedule, refined reuse, bounded sampling all green |
| v0.39 | 2026-08-02 | PAYLOAD-REWORK-PLAN Phase 5 ruled numerical changes (one lettered clause per lane). (5.3) SIGMOID CANONICALIZATION (ruling 10.3, finding detect-k:06; non-semantic, NO identity bump): the two-branch sigmoid inside `detect._solve_offset` (`1/(1+exp(-x))` for `x >= 0`, `exp(x)/(1+exp(x))` otherwise) is declared the PROJECT-CANONICAL sigmoid for every receive path in every encoding — documented in the function docstring. Verified: it is the ONLY sigmoid site in `src/holo` (color lanes use QDA/`logsumexp`, never a binary sigmoid; `characterize` — outside receiver scope — also carries none) and no `scipy.special.expit`/logistic import exists anywhere in `src/holo`. Measured non-identity to `scipy.special.expit` (scipy 1.18.0 / numpy 2.5.1): bit-identical for all `x >= 0`, differs on ~45% of negative inputs by 1–3 ulp — masked by the CTX_ROOT_TOL=1e-12 bisection, so numerically irrelevant. CORRECTION to the audit's background claim: legacy paperholo `payloaddec.py` did NOT use the manual form — it imports and uses scipy `expit` (lines 50/519), so the canonical form is a bit-level divergence FROM legacy, recorded in §11 as canonical-by-fiat. New pins in `tests/holo/test_canonical_sigmoid.py`: AST+call-site import gate over `src/holo/receive`+`src/holo/core`, source-form pin of the two branch expressions in detect.py, hex-frozen canonical-sigmoid values on a 19-point probe grid (both branches, the `x >= 0` boundary, subnormals, saturation), `_solve_offset` shortcut pins (±CTX_OFFSET_LIMIT clips, exact derivative(0)==0, one hex-frozen bisection value), and the legacy relationship pin (non-negative branch bit-identical to expit, negative branch ≤4 ulp). No production numerics changed. (5.4) BP_ALPHA THREADING (ruling 3.4/§13a, findings engine-records:06 + color-payload:10; non-semantic, NO identity bump — identities already spell `alpha0.8`): the two unlinked constants (tiles.BP_ALPHA=0.8 rendered into every durable decoder_profile/stream_attempt_identity vs decode()'s own signature default alpha=0.8 that every decode actually rode) are now LINKED BY CALL: `decode_tile` (core/ldpc/tile.py) and `decode_frame` (core/ldpc/frame.py) accept `alpha` (default 0.8, forwarded to `decode`), `cmy8_decode_stream` (core/color_tile.py) forwards it, and BOTH receive-side leaves pass `alpha=tiles.BP_ALPHA` explicitly — K in `payload.attempt_k_tile`'s decode_tile call, color in `color_attempts` at the CMY7 decode_frame call and the CMY8 cmy8_decode_stream call. Gen-side/qualification users of decode_tile/decode_frame (encode paths, cmy7_decode_payload/cmy8_decode_payload conveniences) keep the unchanged defaults. Pins: signature-default equality (inspect over decode/decode_tile/decode_frame: every `alpha` default == tiles.BP_ALPHA == 0.8, so a future default change screams before it forks identity-from-executed-decoder; tests/holo/test_receive_tiles.py) and call-threading capture (monkeypatched core `decode` observes alpha=tiles.BP_ALPHA arriving from the K leaf and from both color routes; tests/holo/test_receive_tiles.py + test_receive_color_attempts.py). Zero value changes by construction (passed value == prior default); targeted lanes green. (5.2) HOLDOUT STRIPE COEFFICIENT (ruling 10.5 "adjust for health", finding refinement:07; RESULT-AFFECTING — identity bumped): archaeology first per the plan gate — NO deliberate rationale for the x-degenerate span exists anywhere in the record: the `page*104729 + by*1009 + bx*9176` form first appears uncommented in the E024 commit (916c7d8, `feedback._validation_block`) and was ported verbatim into `certified_refine._block_validation` by the Track-3 rebuild (2079676); REASONING-LOG, RECEIVE-DESIGN-EVIDENCE, the e023c/e024 memories and the 023c/024 experiment logs say only "deterministic spatial-block train/validation weights" and never mention the coefficients; PAYLOAD-IMPROVEMENTS §10.5 itself records the span as a historical quirk faithfully preserved. The defect: with BLOCK_CELLS=16 and VALIDATION_MODULUS=4, bx coefficient 9176 ≡ 0 (mod 4), so cargo-holdout membership depended only on (page, by) — the partition degenerated to horizontal bands and a y-correlated pose-error direction was over-represented in held-out adoption evaluation. FIX: bx coefficient 9176 → 9177 (all three coefficients now odd, hence coprime to the power-of-two modulus): holdout blocks form diagonal stripes and every axis-aligned run of VALIDATION_MODULUS blocks — horizontal AND vertical — contains exactly one held-out block; the 1/4 stripe fraction, block quantization, and determinism are unchanged, and the pilot parity split (131/17, already x-y-mixing) is untouched. Legacy `paperholo/feedback.py` keeps the historical form (legacy reader for printed v2–v4 sheets, out of scope). Held-out membership changed ⇒ refinement adoption can change ⇒ `ProductionPayload.policy_id` gains the `-stripes-xy` segment, spelled literally (rides the same v11 literal as 5.1's f32 bump; no standalone refinement identity exists — the payload policy is the covering identity, verified via production_payload's refine_address_once call). Pins: no FIXED numeric refinement pin exists to re-derive — the refined-reuse differentials recompute both sides (forced full recomputation vs optimized path) and stay green (test_receive_refined_reuse, test_receive_bch_quarantine); the policy-literal pin in test_close_schedule spells the new literal. Sanity: `_bench_payload_decomp` yield unchanged — 49/49 certificates, close verified, refinement adopts 0 on the synthetic corpus, exactly as before. (5.1) FLOAT32-NATIVE SCORE PATH (ruling 10.2 — “pinned does not always mean good”; finding detect-k:04 as corrected by the audit verifier; RESULT-AFFECTING — identity bumped): `_payload_sampling._scores` is rewritten float32-native — the float64 compute-then-quantize detour is gone, median/spread/score arithmetic runs in float32 with every constant spelled `np.float32` so weak-scalar rules cannot re-widen it, and the stored scores ARE the computed scores, matching the legacy E023b float32-native photometric path; PAVA keeps its float64 interior exactly as legacy `pava_calibrate` consumed float32-valued scores. `ProductionPayload.policy_id` hand-bumped `v10-pool-law` → `v11-f32-scores` (one shared literal with 5.2’s `-stripes-xy` segment; spelled in full at production_payload.py and pinned in test_close_schedule). Affected fixture expectations re-derived through the generating path (`_e023c_fixtures`). ACCEPTANCE: the full measured-channel slow gate green on the f32 path (12 passed incl. the c2/c3 real-channel fixtures — completed by the phase supervisor after the implementing agent returned before its background gate finished), fast suite green, `_bench_payload_decomp` yield unchanged (49/49 certificates, verified) |
| v0.40 | 2026-08-02 | PAYLOAD-REWORK-PLAN Phase 6 color parity (one lettered clause per lane). (6.2) COLOR DRIVER EVENT PARITY (finding production-drivers:05): `ProductionColorPayload` now honors the §10.4 requirement that EVERY payload lane emits the forced max60→retry150 boundary milestone and the owner-frozen fine snapshot — both were K-only. `payload.retry_complete` is emitted after the shared engine run, mirroring `ProductionPayload._retry` exactly: same observer gate (`context.observer_enabled`), same `_production_diagnostics.retry_summary_details` scalar summary (max60 attempts/decoder calls/BP iterations/certificates vs retry150 frontier/eligible/attempts/decoder calls/BP iterations/certificates/no-op), same report shape incl. the v0.38 eligible-vs-attempted distinction (eligible = the engine's selected retry frontier). `payload.owner_frozen` gains the lazy `snapshot_factory` K already carried — the generic `_diagnostic_snapshots.payload` payload_reach builder over the frozen color evidence (per-page touched 64-cell tiles; built only when an observer requests snapshots), feeding pane D's reachable layer. NO viewer changes: the diag viewer already consumes both events codec-generically (`payload_reach` snapshot ingest, retry-pending clearing, milestone set) — verified, no codec branch existed. Scalar detail keys on the color lane's OTHER events are untouched (the `color.*` detail family is the color driver's established vocabulary; §6.4 retired only the `payload.color.*` EVENT names). Pins in test_receive_production_color.py: retry_complete ordering (after `payload.retry_attempt`, before `payload.complete`) and its full detail dict on the scan/union/retry battery (5 max60 attempts / 2 certificates / frontier=eligible=1 / 1 retry attempt+certificate / noop False), and the owner_frozen factory returning the generic payload_reach shape lazily. (6.3) DIVERGENCE PAIRING TIGHTENED (lens-doc-s6 family): `color_divergence.validate_color_divergence` DELETED — it re-implemented the pairing identity checks (divergence↔block↔certificate id equality) that its one caller, `session.py`'s barrier validation loop, had already established by fetching both records by the divergence's own ids. `color_divergence.py` now exports exactly ONE symbol, the comparison kernel `color_divergence_counts` consumed by the ONE pairing loop (`records.certificate_divergence`) and, since this amendment, directly by the barrier replay: session.py recomputes (n_observed, n_disagree) through the kernel and refuses on counter mismatch with the K-family wording ("observation count disagrees with source" / "disagreement count is not replayable"). Result-identical: divergence counts byte-equal on the color fixtures. Pins: kernel-vs-pairing-loop differentials in test_receive_color_divergence.py (CMY8 per-stream + CMY7 seven-state: `color_divergence_counts` == the records-loop record counts), and a new barrier-level tamper pin (a +1 `n_disagree` divergence in an otherwise-valid CMY8 delta refuses at `append_level_barrier` with "not replayable") replacing the deleted validator's direct-call exercise. (6.1) COLOR CERTIFIED POSE REFINEMENT (ruling 10.6 "color needs it too", finding color-payload:11; design note COLOR-INTEGRATION-DESIGN §5.5 written first, §7 here amended — the v0.38 doc-truth "color has none" note is superseded): NEW `color_refine.py` implements the §7 forward arm for CMY7/CMY8 — one bounded pose proposal per emitting E022 color window, labelled ONLY by prior-barrier certificates. LABELS: flattened (cell, plane) presence bits — word/dust furniture (all three planes, the pilot analog) plus certified cargo planes reconstructed through the ONE color reconstruction primitive, now mint-once cached per (format, address, certificate-set) as `color_projection.cached_certified_color_projection` (the color analog of `printed_cells_from_record`; validation at the mint, immutable, shared). FIT: K's two-stage structure with K's grid/holdout/support machinery IMPORTED from `certified_refine` (angle/phase limits+steps, `_pose_candidate`, `_pose_objective` verbatim on negated calibrated scores, `_weighted_logloss`, the ruling-10.5 diagonal-stripe `_block_validation` shared by furniture and cargo, `_block_weights`, all support-ladder constants; deterministic cargo site cap extended with an odd plane-mixing constant); the frozen detector stand-in is the per-plane affine calibration (midpoint=median, spread=floored MAD of the baseline-pose samples) because the color region QDA/PAVA detector is transient by design — both gate arms ride the same frozen transform, so the gate measures pose, not calibration, and the RGB scale/region divisor cancel by construction (refinement samples the undivided filtered window crop; the L5 region pitch pool IS replayed). GATE (color-native held-out-improvement-without-pilot-regression): candidate held-out summed per-plane logloss must improve by MIN_HELDOUT_GAIN AND held-out furniture logloss must not worsen (slack 1e-9, float re-association only). FROZEN DISCRETE IDENTITY enforced structurally by the `ColorWindowRefinement` constructor (page/rot90/page-origin/audited cells/authoritative cells byte-equal; only the continuous pose moves); color gen-0 retains detector outputs, not raw samples, so the K photometric baseline replay is replaced by a structural subset replay — recorded honestly in §5.5. REUSE at REGION granularity (the color detector fit, registration, pitch pool, and divisor probe are region-scoped; window granularity not cleanly reachable): `collect_refined_color_evidence` recomputes exactly the affected (region, page) groups through the ordinary `collect_color_evidence` via the NEW K-parity `included_patch_ids` seam (each recomputed region replays with its complete fit population), reuses gen-0 windows verbatim elsewhere (same objects), and reruns the ONE global owner freeze over the merged windows. WIRING: `ProductionColorPayload` runs refinement between gen-0 collection and the owner freeze, emits K's event family (`pose_refine.window_progress` with color-named furniture details via `_production_diagnostics.color_refinement_details`, `address.final` with `address.refined`), rebuilds the address product with `patch_dependency_overrides` (adopted label certificates ride into window/block lineage), and publishes `replacement_address`; `payload.complete` gains `color.refinement_eligible`/`color.refinement_adopted`. `COLOR_PAYLOAD_POLICY_ID` hand-bumped `provisional-v5-pool-law` → `provisional-v6-refine` (full literal; every durable color payload product re-derived under it). Pins (tests/holo/test_receive_color_refine.py): (a) MEASURED adoption gate — perturbed-pose synthetic (compose_color_tile forward fixture, blurred, 4 px/cell) adopts, recovers the pose (origin error shrinks), and the driver-level A/B (refinement disabled vs enabled through `ProductionColorPayload.process`) certifies no fewer streams; (b) adversarial-search negative — a monkeypatched candidate objective cannot force adoption past the held-out gate (`pose_gate_failed`, geometry unchanged) and a true-pose baseline selects `active_pose_selected`; (c) frozen-discrete-identity — adopted revision changes only the pose, and a tampered discrete field refuses at construction; (d) reuse exactness differential — optimized region-merge path byte-equal to forced full recomputation on the refined address, unaffected regions reused as the same objects; (e) the full v6 policy literal pinned. HONEST LIMITS: synthetic-only qualification (clean forward model; adoption incidence, gain, and the adequacy of the frozen per-plane calibration on real plane-drifting hardware channels unmeasured until post-08-04); the region recompute pays a full region re-collect per adopted pose (no window-level reuse by design); refinement reads its own window crops (one extra native RGB read per emitting window when certificates exist) — unmeasured cost, bounded by the certificate-bearing lanes |
| v0.41 | 2026-08-02 | PAYLOAD-REWORK-PLAN Phase 7 test-strategy redesign (user ruling: "reasonably fast tests that do their intended job well, and a few optional end-to-end / pathological case testing ones, that still need reasonable runtimes"). COVERAGE MAP FIRST — already landed in phases 0–6 and kept: pool-law oracle (phase 0/1, test_pool_law_oracle), D5 materialization pins incl. the dropped-disagreement counter (phase 0/2, test_supersession_materialization + test_close_schedule), D8 want_more shortfall baseline / rewound reset / metadata-terminal precedence / close schedule (phase 2, test_close_schedule), K one-owner hand-constructed-winner differential (phase 3, test_payload_unification — verified it builds expected winners by hand, no differential-cancellation), stat-memo re-auth + source-mutation guard (phase 3, test_receive_reauth_memo), raster-pool lifetime (phase 3, test_receive_raster_pool), canonical-sigmoid + BP_ALPHA threading pins (phase 5), color refinement pins (phase 6, test_receive_color_refine). NEW FAST PINS closing the remaining §8 gaps: (7.1a) tests/holo/test_detect_unit.py — the numerical evidence boundary's first unit file (lens-coverage:05): CAL_MIN_* refusal ladder each floor at its bar, ctx floor ladder all four reasons, CTX_LLR_CLAMP kernel (clip exactness, -1 bins untouched even beyond the clamp, fresh array), duplicate-weight total-weight-one differential + conflicting-label refusal, held-out STRICT-improvement adoption incl. the exact-tie non-adoption (offsets solve 0 exactly on symmetric data), partition leakage/identity refusals, and the 018.7 bounded-LLR invariant (|LLR| <= log(n+1) attained at the extremes, PAVA-support refusal); (7.1b) tests/holo/test_payload_nulls.py — the payload-stage null set (lens-coverage:11): WRONG-KEYSTREAM null (true 7x7 tile evidence vs a same-coding different-geometry sibling seed: decoder genuinely runs, ZERO certificates over 8 tiles, positive control certifies) and STATE-TAMPER nulls (one flipped bit inside a persisted block's inline compressed payload refuses at load with byte-exact recovery on restore; truncated envelope refuses; tampered certificate packed_user_bits refuses validation under both old and unchanged id; tampered origin row refuses at the block content address, and a re-signed body with a poisoned loss field refuses structurally); (7.1c) tests/holo/test_retry_eligibility.py — the §6.3 sentences at engine/records scale with the REAL K decode: new-capture-new-frontier mints a NEW retry identity over the union digest, a newer below-floor baseline (exact-cancellation union) blocks tunnelling to the older scan failure, unchanged frontier is an identity-level no-op (fresh-leaf determinism re-derives byte-identical attempt ids; same-leaf replay records nothing); (7.1d) tests/holo/test_trust_boundaries.py — 16 fast ports of the orphaned qualify_runtime guards (lens-coverage:02): barrier-restart resume exactness, same-address lane frontier + attempt publication provenance (unpublished/cross-lane refusals), lower-scale evidence selection lane purity, duplicate-capture exact no-op + metadata-conflict refusal, interpretation envelope fail-closed family, SCAN-current-acquisition doctrine probes (union-without-scan, partial components), terminal close persistence + reopen refusal, observer isolation off/on/failing byte-parity, canonical source identity, derived stage view, native raster reuse + affine round-trips, transient non-authority, acquisition retention, static source invariants (>=1000-line debt pinned to the known 3-file set instead of merely reported). RETIREMENTS (7.2): _qualify_runtime_fixtures.py loses its battery scaffolding (RuntimeQualification*, all 16 _*_case bodies, qualify_runtime, __main__) and becomes the shared fixture library its importers actually use; the 4-case _qualify_production_roundtrip.py pathological battery (>20-min class, lens-coverage:10) is DELETED with its @_SLOW_QUALIFICATION hook — the shared 7x7 fixture builder moves to tests/holo/_roundtrip_fixture.py (8 importers rewired; grep-verified no residual importer). THE BOUNDED E2E (7.3): tests/holo/test_phased_roundtrip_e2e.py, slow-gated, ONE phased-native multi-capture case built from _bench_phased's corpus helpers — full field + re-placed 90-degree-ROTATED 128-cell scrap, K row, resume-mid-session leg (stop after the first committed barrier, resumed to a verified byte-exact close without re-running the committed level), --complete leg (every ladder AND M-level barrier on both captures, exactly one close.check, blind non-native pose retained, session.phase observed), mandatory max60→retry150 boundary event on every payload lane; WALL BUDGET tripwire 180 s (~3x the measured 61 s reference wall, kiss precedent — a breach is a mechanism regression, never noise). CURATED SLOW LANE = seven-coding real-payload gate net (THE acceptance checkpoint) + measured-channel gates + this e2e; measured 2026-08-02: 13 passed in 7:53 total (seven-coding calls ~2:01, measured-channel calls ~4:48, e2e 1:03) — comfortably inside the ~15-min lane bar. Docs: §10.8 qualification-split paragraph and §12 lane preamble rewritten to the new lane structure; CLAUDE.md acceptance-checkpoint sentence updated (seven-coding stays the checkpoint; batteries noted retired). Fast suite green: 944 passed / 35 skipped, 2:23 (baseline 898/35 at 2:20 — the 46 new pins cost ~3 s). CHECKPOINT FIX (same day, from the real-corpus A/B): the color refinement candidate loop paid the native RGB window crop+filter for EVERY emitting window before any cargo check — on the c2-cmy7 real corpus (604 prior certificates, 16 barriers) this alone inflated base.payload 532→924 s; `refine_color_address_once` now pre-gates each window on certified-cargo overlap of its FULL aligned geometric footprint (geometry only, no crop; the emitted cells exclude certified tiles by construction and must not be used) and emits the byte-identical `insufficient_payload_train` refusal summary for zero-overlap windows — a window with no certified cargo can never pass the `_support_metrics` ladder, so the pre-gate is exact by construction; differential pin `test_zero_cargo_overlap_window_refuses_without_cropping` (sampled-path oracle equality + crop-never-called) |
| v0.42 | 2026-08-02 | REFINEMENT LANES R(Lk) + PARKING FLAGS (user rulings 2026-08-02, adjudicated; full decision text PHASED-SCHEDULE D20; resolves the PAYLOAD-MEASUREMENTS §6 open ruling as option (a)-as-lane for K AND color). (A) PLAN SHAPE + FLAGS + PARKING + AMENDMENTS (stage A): refinement moves out of the inline payload stages into per-ladder-lane REFINEMENT LEVELS — `scale_plan` (pure function, unchanged inputs) returns `[L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln)]`, one R entry per ladder lane after ALL M-levels, coarse→fine; `LaneSpec.refine_of` mirrors `mopup_of` (a level is exactly one of ordinary/mop-up/refine); R(Lk) binds to Lk's exact transform (`LaneSpec.base_lane_id`; `validate_lane_request` binds it exactly as it binds M(Lk)) but owns its OWN evidence namespace — `evidence_lane_id` stays the R lane's own id (only certificates cross lanes; LLRs never cross correlated views, so no supersession of base blocks and no new evidence law). The R(Lk) address takes Lk's committed poses and the full accumulated certificate frontier; its payload delta covers ONLY affected regions (adopted windows + region-coupled context) — unaffected regions contribute NOTHING at the R barrier (their Lk evidence stands; NeedMap prunes certified addresses); no adoptions ⇒ empty delta, cheap barrier. FLAGS `--mopup`/`--refine` (invocation-only, scheduling-only, absent from policy/schema — the `--complete` family): default drives the ordinary ladder ONLY (stop before the first M entry); `--mopup` extends through M-levels (stop before the first R entry); `--refine` extends through everything — by the plan-prefix law this includes pending M-levels. Verified-close preemption and stop_requested keep their existing precedence; committed prefixes are always honored; resume with different flags continues monotonically. `--COMPLETE` CORRECTED (§8.1, amending the v0.33/D11 wording): it governs EXACTLY ONE thing — deferring every fountain check/solve to the end of the invocation's flag-bounded plan prefix, then one close; it does NOT imply `--mopup`/`--refine` and never did imply lane families; a `--complete` run without lane flags legally ends OPEN with parked lane families and is resumable. CaptureStatus.COMPLETE still means every plan level committed (now incl. R-levels); sessions that never run the flags legally keep ACTIVE captures; CLI epilogues advise pending families by flag name ("mop-up tail parked: N windows (--mopup)"; "refinement pending: M eligible lanes (--refine)"). Tail order: all M-levels before any R-level session-wide (class-ranked tail EV) so every R(Lk) sees the maximal frontier. Discovery: per-branch drives flag-bounded identically; the deferred one-final-close fires when every candidate/acquisition pair is c-excluded, terminal, or has committed its flag-bounded prefix (durable round_complete/status stay full-plan and flag-free). Stage A ships EMPTY R-level processors (survey = empty mint; address = empty durable product carrying the typed transient `RefineAddressPlan` base-lane references — the stage-B/C contract; payload = empty delta) and R-levels ALWAYS run behind the lazy raster stand-in (no eligible work ⇒ no raster materialization). Identity: receiver schema 23→24, discovery 9→10, scheduler `holo/phased-session/rung-major-v2-r-lanes`; pre-existing states refuse, no migration, pins re-derived through the code. The codec refinement leaves + policy-id bumps land in stages B/C as lettered clauses of this row. (B) K R-LEVEL CODEC LEAF (stage B, 2026-08-02): inline certified pose refinement REMOVED from `ProductionPayload` (no `refine_address_once` call, no refined-address re-emission, no refined-reuse generation swap) — ordinary and mop-up K lanes are generation-zero only; `payload.complete` keeps its schema with the refinement counts pinned 0 there. The R(Lk) K leaf is `production_refine.process_refine_level`, routed from `ProductionPayload.process` on `refine_of` and reusing the engine's freeze/blocks/decode/retry/complete methods over the delta: (1) INVENTORY — `place.place_committed` re-derives Lk's durable PoseRecords (accepted AND redundant; base-QUARANTINED placements excluded at the evidence-context seam, mirroring the base payload pool) as payload-capable placements: deterministic re-sample + re-audit on the re-derived base aperture (one pitch = the median committed pose pitch, mirroring the base survey's single global estimate), a synthesized CandidateScore replaying the durable verdict (passes=True, validation_mismatch = 1 - quality), no search/words/firewall/parking; a window whose support/audit no longer re-derives is simply not a refinement candidate. (2) NEEDMAP — a pixel-free bounding-box pre-gate (every committed window's page-span tile cover certified is a SUPERSET proof that the exact law prunes it too) keeps the lazy raster stand-in unmaterialized on no-poses/no-frontier/fully-certified levels; then the exact `unresolved_region_patch_ids` law prunes at region granularity. (3) one generation-zero collection over the needed domain feeds `refine_address_once` against the full accumulated frontier (mint-once printed-field cache); `pose_refine.window_progress` publishes at the R level now. (4) DELTA — `payload.collect_refined_region_delta` (successor of the retired whole-capture `collect_refined_capture_evidence`; the `_payload_reuse` region-recompute re-homed) returns ONLY the affected regions: fresh sampling at refined poses, region context over the pool law's full population, one-owner freeze WITHIN the delta; unaffected regions emit no windows, owners, blocks, or attempts at the R barrier (their Lk evidence stands); no adoptions => empty delta, silent cheap barrier (stage-A shape). (5) NAMESPACE — blocks/attempts/certificates mint under the R lane's own id through the ordinary engine schedule (scan -> union -> advisory preclose -> selective retry150 within the delta); adopted refined poses mint as PoseRecords under the R lane id via the payload `replacement_address` barrier (`address.final` re-emitted with `address.refined`, per the stage-A product semantics), dependency lineage = base pose lineage UNION the adopted frontier certificates; no proposals/losers/parked rows at R barriers. PINS: the refined-reuse byte-equality differential is RE-SCOPED — the old generation-swap contract dissolves; its replacement (test_receive_refined_reuse) pins the R-lane affected-region recompute == a FORCED FULL RECOMPUTE of those regions (`collect_capture_evidence` over the refined address restricted to them), byte-exact through windows, owner freeze, compact blocks, attempts, certificates, and divergences; pool-law case (f) re-pinned on the delta seam; NEW test_receive_refine_lane pins the pixel-free pre-gates (a pixel-refusing raster stand-in), `place_committed` determinism + payload-capability, and the adoption path's own-namespace affected-region-only delta (R-lane blocks/attempts/poses, base∪frontier lineage, nothing from unadopted regions). IDENTITY: `ProductionPayload.policy_id` hand-bumped `paperholo-e023b-e023c-v11-f32-scores` -> `paperholo-e023b-e023c-v12-r-lane` (same trailing segments incl. `-stripes-xy`; spelled in full at production_payload.py, literal pinned in test_close_schedule). (C) COLOR R-LANE CODEC LEAF (stage C, 2026-08-02): inline refinement REMOVED from `ProductionColorPayload` — ordinary and mop-up color barriers are generation-zero only (no `refine_color_address_once` call, no `replacement_address`, no `address.final`, no `color.refinement_*` details there); the shared barrier tail (owner freeze report → blocks → shared attempt engine → selective BP150 → divergence audit → typed product) is factored once and serves both the base and the R barrier unchanged. R(Lk) COLOR LEAF: `color_refine.reconstruct_committed_color_address` rebuilds the base lane's durable `RefineAddressPlan.poses` as a geometry-only address — pose-exact (the R level binds Lk's transform, so the persisted lane-frame pose replays verbatim); the base audit's cell subset is NOT durable, so the rebuilt inventory is the full window rectangle clipped to page and lane-raster bounds (a superset of the base audit; trust rides the held-out gates and the CRC'd attempts, never the inventory), and base-QUARANTINED placements are excluded at the evidence-context seam (a quarantined placement must never re-enter the payload domain, including as region context). `refine_color_address_once` gains the committed-pose drive (`generation0=None`: domain = every reconstructed placement; the structural gen-0 replay check is vacuous — the aligned cells were just re-derived from the committed pose) plus a second crop-free pre-gate ahead of the pinned v0.41 certified-cargo gate: a window whose covered payload tiles are ALL fully certified refuses with reason `certified_complete` (the NeedMap analog — nothing left to gain), so a lane with no eligible window never materializes its lazy raster (pinned with a pixel-refusing raster stand-in). ADOPTION ⇒ THE R DELTA: `affected_color_patch_ids` closes the adopted windows over their (region, page) fits and the ordinary `collect_color_evidence` `included_patch_ids` seam recomputes exactly those groups against the refined address in the R lane's OWN evidence namespace — `collect_refined_color_evidence` (the inline gen-0 merge) is DELETED, its affected-region recompute re-homed as the delta; unaffected regions contribute no windows, owners, blocks, or attempts at the R barrier (their Lk evidence stands; only certificates cross lanes). Window lineage = base pose deps ∪ adopted refinement label deps ∪ region deps. Adopted refined poses are minted under the R lane's own id namespace via the payload `replacement_address` barrier (adopted-only `_address_product`; poses cite the base lane's durable regions exactly as mop-up poses do — D7 global region validation; unadopted poses are never re-minted). No adoptions ⇒ empty delta, cheap barrier (refinement summaries + a zero `payload.complete` still report; the trivially-empty no-poses/no-certificates level stays stage-A silent). `COLOR_PAYLOAD_POLICY_ID` hand-bumped `provisional-v6-refine` → `provisional-v7-r-lane` (full literal pinned; `region-reuse` token replaced by `r-lane-committed-pose-domain-affected-region-delta`). Pins re-derived in test_receive_color_refine.py: leaf-level adoption/adversarial/frozen-identity/crop-free-cargo pins survive unchanged; the driver A/B is now an R-lane A/B (arm A = ordinary barrier, refinement-free; arm B = R level over the committed poses, no fewer certified streams, adopted pose minted under the R lane id); new pins for the R-delta affected-region byte-equality, the region closure, committed-pose reconstruction replay, the certified-complete pixel-free refusal, and the silent empty level. |
| v0.43 | 2026-08-02 | PANE-C ADDRESS-AUTHORITY TRI-STATE (declared operator-presentation ruling 2026-08-02, the v0.27 mechanism; presentation only). The declared states: "GREEN (current green, unchanged): tile addressed by an actual BCH word-route SOLVE (the word decoder produced the address — the seeder route). LIGHTER GREEN (new): tile placement-addressed (chain/lower/transport) AND its word subsequently PASSED the §5.4 known-position BCH evaluation (the per-level final-word firewall) — read-and-validated. YELLOW (unchanged): word sites observed but not validated (below the known-position evaluation floor, or no evaluation outcome yet). DEEP RED (unchanged, reserved): BCH conflict/contradiction (v0.32 ruling: deep red stays contradiction-only)." Data path: `address.patch_accepted` gains two observer-gated int details `address.word_tile_y`/`address.word_tile_x`, present only when the accepted route is the word route, naming the tile whose BCH word the seeder decoded (`SearchOutcome.word_tile_yx`, diagnostic provenance only — admission, scores, and refusal semantics untouched); the §5.4 PASS keeps riding `address.final`'s existing words snapshot (`KnownWord.certified`). Viewer: `_WORD_SOLVED` (full green; outranks every non-conflict state) vs `_WORD_VALIDATED` (lighter green `_CHIP_GREEN_SOFT`, soft fill + darker same-hue outline per the v0.32 two-tone chip); conflict stays sticky; the §10.3.2 address row is text-identical (both greens tally as "match" — a word-route solve is a matching decode by construction); the HTML legend names both green authorities. No new pane, no new milestone, count-bounded (<=2 int details per accepted word-route placement), §10.6 headless-timing-neutral. |
| v0.44 | 2026-08-02 | COLOR R-LANE COMMITTED-POSE DOMAIN = SHARED AUDITED RECONSTRUCTION (real-corpus crash fix, same-solution ruling: mirror K). The real-corpus R-lane resume run crashed in the color R delta: `PlacementModelError "corrected sample leaves the region crop"` (`color_anchoring._sample` via `color_payload._crop_features` inside `collect_color_evidence`). Root cause: `color_refine.reconstruct_committed_color_address` rebuilt each committed window's inventory as the FULL window rectangle clipped to page+raster bounds; on partial-coverage scrap material the rectangle keeps off-support cells up to the acquisition edge, and once refinement adopts a bounded pose revision (frozen discrete identity keeps the cell set) the delta's sampling walks those cells past the raster-clipped window crop — the `_sample` trust boundary correctly refuses. Fix: the color R leaf now uses the SAME `place.place_committed` reconstruction as K — deterministic, search-free re-derivation of the base lane's durable PoseRecords with bit-exact re-sampled/re-audited cell sets on the re-derived base aperture (the address/audit layer is codec-independent; placement runs on the lane raster luma for color lanes too), so the reconstructed inventory is the base audit, never a rectangle superset, and the `_sample` guard holds by construction. The rectangle reconstruction is DELETED (dead). Pixel-free pre-gates now mirror K exactly: no committed poses, no certificate frontier, or every committed window span fully certified (`_every_span_certified` over the color all-streams NeedMap complement, the new shared `color_payload.fully_certified_color_addresses`) commit the silent empty delta without materializing the lazy raster; the per-window crop-free `certified_complete`/certified-cargo gates remain for mixed frontiers. R-delta numerics change on partial-coverage material => `COLOR_PAYLOAD_POLICY_ID` hand-bump v7-r-lane -> v8-r-lane with the truthful token `r-lane-audited-committed-pose-domain-affected-region-delta`. Pins: tests/holo/test_receive_color_refine.py — `test_partial_coverage_rectangle_crashes_audited_domain_completes` (the crash by construction: rectangle inventory raises, audited domain excludes off-support cells, re-derives byte-identically, and the same adopted-pose delta completes), `test_committed_pose_reconstruction_replays_geometry` (shared reconstruction replays the durable pose, audited subset, byte-identical re-derivation), `test_r_level_certified_complete_frontier_never_reads_pixels` (silent K-mirror span pre-gate), `test_certified_complete_window_refuses_crop_free` (per-window gate kept for mixed frontiers). |
| v0.45 | 2026-08-02 | PANES A/C RESUME SEED FROM DURABLE RECORDS (declared operator-presentation ruling, the v0.27 mechanism; display only, zero receiver-side changes — the seam is the `session.open` committed bootstrap pane D already rode). THE GAP (observed live): the view is event-fed, so a resumed invocation (`--mopup --refine` over committed state) showed panes A/C nearly empty — committed levels emit no survey/address events — and the v0.43 tri-state had almost nothing to colour although hundreds of tiles are addressed in durable state. THE RULING: at the committed bootstrap (lazy, observer-gated; headless runs and scalar-only observers never build it — §10.6 neutrality pinned) the view seeds both panes from durable records, the D15 parked-inventory pattern. Pane A, per capture, from the base lane of the next uncommitted level (where the resumed invocation's live events land), else the finest committed lane with regions: `SurveyRegionRecord` support masks via `survey.region_from_record` through the ONE shared `PaneRenderer.scan_views` geometry (live ingest re-based onto it — seeded frames are exactly what the live pass would draw); region states derived exactly (`PoseRecord` accepted/redundant -> placed; `ParkedWindowRecord` -> parked; a committed address artifact with neither -> unresolved; uncommitted -> surveyed); durable parked chips rebuilt from the records' persisted lane-frame geometry (region-crop origin + `origin_yx_px`, `shape_yx_cells * cell_pitch_px` — the live `address.window_planned` convention) under their live identity keys, so live re-parks overwrite and barrier reconciliation retires them unchanged; installed at `capture.open`/`capture.resume`, replaced wholesale by the next ordinary live survey; NO capture-preview underlay (preview pixels are not durable and are never re-read — geometry and records only, no crop/filter work). Pane C: durable `BchConflictRecord` rows seed exact sticky deep red; every tile covered by a committed placement's oriented window footprint (page cell origin + rot90-oriented window shape) seeds the NEW committed-addressed state `_WORD_SEEDED` — pale amber `_CHIP_AMBER_SOFT`, the amber-family analog of the v0.32 reach/blue lightening. RECONSTRUCTABILITY (the honesty core, said plainly): NEITHER green authority is durably provable — `PoseRecord` carries no route, so BCH-word-route-solved vs placement-addressed is not durably distinguishable, AND the `KnownWord` rows carrying the §5.4 `certified` outcome are transient (§10.7: word states other than conflicts are cold-unavailable) — so the seed cannot even paint the lighter green and paints the weaker committed-addressed amber for everything non-conflict; the seeded code ranks below every live evaluation outcome, so this invocation's re-reads (validated/solved/refused/floor) upgrade seeded chips in place and conflict stays sticky. Seeded tiles print NO observed-site count (counts are live facts; zero is never fabricated) — the absent count plus the pale chip IS the deliberate seeded-vs-live distinction, kept because an incremental run's own activity must read against the seeded backdrop. Rows: the scraps row reads the seeded exact region classification (located from region records, placed from pose records — exact durable classification, not the forbidden placement-hypothesis reconstruction); seeded tiles join NO live word-evaluation bucket (match/insufficient/refused text-identical; durable conflicts count). Idempotence is the hard requirement, pinned in tests/holo/test_diag_viewer.py: seed-then-live-same-facts double-counts nothing (sites, mapped footprint, and every live-touched word state equal a never-seeded control view; live re-park overwrites the seeded chip under the same key; re-seeding against the evolved model is a no-op), plus the resumed-session fixture (panes A/C carry the prior invocation's geometry, nothing fabricated) and the headless-no-cost pin (the seed builder runs exactly once, at the committed bootstrap, never without a snapshot). §10.3.3/§10.3.4/§10.7 amended below. |
| v0.46 | 2026-08-02 | D5 DROP COUNTER REPLACED: OBSERVATIONS + WINNER FLIPS (user ruling 2026-08-02 "replace", superseding ruling 11.2's byte-inequality form; full investigation record docs/CANARY-D5-DISAGREEMENTS.md). THE FINDING (measured, fixture + instrumented real-corpus rerun): the v0.36 dropped-DISAGREEING count was structurally vacuous — at an M-level every fresh observation at a committed cell comes from a DIFFERENT window than the committed owner (per-pass owner freeze; D4 fresh/parked ordinals; D7 labels never observe), so byte-level (value, origin) inequality holds at ~100% of collisions on healthy material (real corpus: 44,561 = every collision, 0 aperture flips anywhere, exact deterministic reproduction across runs) and the counter measured M-window overlap geometry, not health. THE REPLACEMENT: `supersede_with_committed`/`apply_mopup_supersession` return `SupersessionDrops(dropped, winner_flips)` — `dropped` counts EVERY fresh mop-up observation at a committed cell (expected overlap geometry, full-agreement collisions included), `winner_flips` counts dropped cells whose IMPLIED CELL DECISION differs from the committed owner's under the new `evidence_blocks.winner_codes` conventions: K = LLR sign category; CMY8 = per-plane sign-category pattern (the implied C/M/Y bit triple); CMY7 = the W-relative 7-state winner (state W wins when no score is positive, else argmax+1 — the `color_tile.cmy7_demap_payload` convention). The flip rate is the two-view consistency canary with measured anchors: 0% clean-synthetic overlap, 5.35% healthy real scrap (the mop-up windows are by construction the base pass's hardest), ~50%+ for a misplaced window (chance-level winner agreement) — an order of magnitude of separation aimed at the wrong-but-admitted M-pose class the old counter could not see. CARRIERS: PayloadProduct/BarrierDelta/SessionCounters swap `mopup_dropped_disagreements` for `mopup_dropped_observations` + `mopup_winner_flips` (flips <= dropped validated); event details `payload.mopup_dropped_observations`/`payload.mopup_winner_flips` + `color.*` twins; CLI epilogue reports rate with denominator ("dropped N re-observation(s); winner flips M (x%)", nonzero-dropped-only); the diag LDPC row appends "(flips F)". Advice only, never a gate; threshold doctrine post-08-04 now lands on the flip rate. IDENTITY: receiver schema 24->25, discovery 10->11 (nested SessionCounters); pre-existing states refuse, no migration; NO policy-id bumps (counters never touch evidence, attempts, or certificates — diagnostics lane). PINS: tests/holo/test_supersession_materialization.py re-derived (hand-annotated drop/flip tallies per case incl. full-agreement-counts-as-dropped; winner_codes conventions pinned per kind on hand-built vectors), test_close_schedule fold/epilogue pins re-derived (flips>dropped refusal), tests/holo/test_phased_schedule.py gains the positive control `test_winner_flip_rate_separates_misplaced_mopup_window` (same-corpus overlapping windows: correct pose <=2% flip rate, 8-cell-misplaced pose >=25%, identical dropped counts), schema pins re-derived 25/11. MEASURED CONFIRMATION (real corpus, production counters, this working tree): dropped 44,561 — byte-identical to the investigation baseline and the run-2 epilogue — winner flips 2,383 (5.35%) under the corrected W-relative convention (the investigation hook's uncorrected argmax-over-6 read 3,430/7.7%); 604 certificates, 16 barriers, CPU 1572 s (scratch/canary-probe/confirm_real_report.json). OPEN (explicitly not in this amendment): the §6.1 "same aperture" cross-pass sentence stays population-contingent — pinning the M-pass payload aperture to the base pool (option 2) vs amending the sentence (option 3) awaits its own ruling; PRE-EXISTING slow-lane failures `test_c2_clean_16px_does_not_lose_certificates` / `test_c2_full_measured_channel_verifies` (verified identical at a814539 — flagless gates lost inline refinement's certificates when v0.42 moved refinement behind `--refine`) are recorded as an open regression owed its own session |
| v0.47 | 2026-08-05 | PANE-A OVERLAYS HOLD ONE CAPTURE-NATIVE FRAME (e030 corner-pile fix; presentation-only). A mop-up or refinement level reuses its BASE lane's raster, so `address.window_planned` and the `window_phase` snapshot carry that lane's pixels, while pane A's underlay belongs to whichever ladder rung surveyed last; projecting the former through the latter collapsed every M-level overlay into a corner pile at the ratio between them (observed e030 CMY8 c3, ~12x). RULING: the pixel frame is a property of the geometry, not of whatever surveyed most recently. `LaneSpec.native_per_view` is now published as `lane.native_per_view.num/den` on `level.open` (cascade) and `lane.open` (runtime) and folded into `EventContext.native_per_view` beside `ppc`; the viewer multiplies every pane-A box into CAPTURE-NATIVE px at ingest and keeps ONE `_scan_transform` (native -> pane). `_active_scan_box` stops being frozen to pane px at ingest (renamed `_active_window`, projected at draw) — it was the higher-volume half of the same defect and rode `address.window_progress`, which unlike the M/R `survey.complete` DOES carry a snapshot. The per-`(capture,lane)` transform registry and the parked-chip fallback are DELETED, superseding 32345ef's mechanism whole while preserving what it protected (chips are never pane-frozen) for free. Absent the ratio the multiplier is 1, so legacy streams and direct-harness lanes are unchanged. The underlay crop stays in lane px (the preview's decimation counts lane pixels). Emitted event geometry is UNCHANGED — normalization is viewer-local, so `census_done_geometry.py` and the phased-schedule snapshot tests keep reading lane px. Seed path takes the ratio from the durable `capture.plan` LaneSpec (it runs at `session.open`, before the first `level.open`). Pin: `test_overlays_hold_one_native_frame_across_rungs` — one physical region at an 8x rung ratio, a PRODUCTION-SHAPED M-level `survey.complete` (details only, snapshot=None: the shape two earlier fixes never exercised, which is why both shipped as dead code behind the viewer's snapshot gate), and a negative control that measures the un-normalized displacement. |
| v0.48 | 2026-08-05 | PANE-A REGION STATES ARE LANE-SCOPED (companion to v0.47's frame fix; presentation-only). Region ordinals are LANE-RELATIVE: `address.region` is a positional index into the EMITTING lane's survey tuple (`place.place_survey` over the area-sorted regions), and rungs segment independently, so index N of one rung is a different scrap from index N of another. An M level indexes its BASE lane — `place.mopup_survey` rebuilds that lane's durable records dense from 0 — and a refined `address.final` carries base-lane placements, while the views on screen belong to whichever ordinary rung surveyed last. `_set_region_state` applied them positionally, so during every M/R level the WRONG scrap lit up (or, out of range, the update vanished), and `rows._scraps_row`'s located/placed/working counts mixed two segmentations. Reproduced both directions against the real viewer. RULING: skip rather than guess — a wrong paint is worse than an absent one on the pane that says where the receiver is working. `_scan_lane` now means THE LANE THAT OWNS `_scan_regions` (assigned beside the views, so a zero-region survey cannot relabel views it did not install); `_refine_base` joins `_mopup_base` from the already-emitted `survey.refine_of`; `_region_lane()` = mopup_base or refine_base or the event's own lane, and a state write whose region lane differs from `_scan_lane` is dropped. One guard covers BOTH call sites — the `address.region_open`/`region_complete` branches and `_paint_patch`'s tail — with no signature change and no wire change; `_paint_patch`'s placement ingest, coverage counters and site bitmask are untouched. The receiver core already treated these indices as a foreign namespace (`ProductionAddress` re-bases them); pane A was the last consumer that assumed they were local. KNOWN RESIDUAL, recorded not fixed: pane-B placement hue still comes from `patch.region_index % len(_HUES)`, so pane-A and pane-B hues disagree during M/R levels; closing that needs per-lane retained pane-A models (a per-lane underlay stash does not exist today). Pin: `test_region_states_ignore_foreign_lane_indices` — 1 coarse region vs 3 fine, positive control on the owning lane, production-shaped M and R surveys, and ownership handback. |
| v0.49 | 2026-08-05 | PANE A BECOMES ITS OWN MODULE (G1 compliance, no behaviour change). `diag/viewer.py` was 1229 lines against the <=1000-line rule, carried on the `test_trust_boundaries` grandfather allowlist. Pane A is the natural seam: it is the ONLY pane in scan space (B/C/D are page/tile-indexed and therefore frame-free), which is exactly why both v0.47 and v0.48 were pane-A bugs. `diag/scan_model.py` now owns that model — `ScanModel` (survey ingest, native normalization, planned/parked overlays, region-state lane scoping, projection, stash/restore/seed) plus `ScanFrame`, a dataclass that is THE per-capture display contract. ScanFrame matters beyond tidiness: the same twelve field names were previously spelled out in FIVE places (`__init__`, the `capture.open` reset, `_SCAN_FIELDS`, `_restore_scan`'s blank branch, and seed.py's model dict) with nothing pinning them to agree — adding `_refine_base` in v0.48 meant editing all five. `capture.open` is now `apply(ScanFrame.blank())` and the seed returns `ScanFrame`s directly. The live `EventContext` moves onto the model (it is what makes a box's frame and a region index interpretable), so the ingest signatures lose their context parameter. viewer.py 1229 -> 965, scan_model.py 336; `diag/viewer.py` is REMOVED from the allowlist, converting the headroom into a live tripwire (the assertion is a subset check, so the suite was green either way — removing it is what makes the bound durable). Pin: `test_scan_frame_is_the_one_resume_contract` — the field set, non-aliased mutable defaults across `blank()` calls, and a capture_frame/apply round-trip so a stash cannot silently drop a field. Suite 993 passed / 37 skipped. NEXT SEAM when this file grows again: the B/C block + D/counters + their `_pane_*` inputs as a page-space model. |
| v0.50 | 2026-08-07 | COLOR-UPLIFT CAMPAIGN CHARTER + THE COLOR CALIBRATED-EVIDENCE STACK (design ruling, plan-adjudicated over three review rounds; charter, bars B1–B8, packet program PK0–PK10 in docs/COLOR-UPLIFT-PLAN.md v1.3; DESIGN ONLY — no receiver code changes in this bump, every policy id unchanged until the first numerics packet lands its hand-bump). New §6.2a states the law: (1) one gated ARM LADDER per color region — A0 baseline → A1 region registration (both = today's two arms) → A2 window plane-registration residuals → A3 window photometrics (region QDA refit on mapped features) → A4 kind heads (cmy7 temperature+offset head, a NEW calibration where today there is none; cmy8 = the standing dust PAVA, pattern-stratified under A4b) → A4b KnownField-conditioned marginalization → A5 per-plane ctx-pava — every stage adopted only through the standing three-way held-out gate (total strictly better 1e-9 AND word AND dust not worse) and refusing to a BIT-EXACT predecessor (exact-null law: all gates off ≡ today's receiver, cert-for-cert); the stack is transient (nothing persisted; evidence-block shapes unchanged); stages are typed scores→scores with declared label needs (kind-neutral; K does NOT migrate). (2) THE CROSS-LANE TRUST HIERARCHY is law: candidate facts (proposals/losers/parked) steer search only; committed geometry (poses/regions) places, labels, and projects; certified content (certificates) labels, suppresses, and now CONDITIONS likelihoods; raw evidence never crosses lanes. (3) TWO ITERATION LAWS: soft iteration only INSIDE one attempt (the P3 demap↔BP loop); across attempts/lanes only certified knowledge conditions; soft cross-attempt feedback is REJECTED (correlated-error propagation + a new false-accept story). (4) P9 CONDITIONING RULING: restricting a cell's marginalization to the states consistent with prior-barrier certified sibling components is legal under the component-only law — conditioning on authority fabricates nothing; arity-0 unconditioned marginalization remains the NORMAL case, not a fallback; calibration stratified by (plane, conditioning-pattern) under the two-source provenance law — cert-cross cells primary where dense, deterministically MASKED furniture floor everywhere (reveal-bit (131·y+17·x)&4, extending the &1 split / &2 sub-split family) — with the SCOPED masking law: masking is a view, not a mutation, existing only inside P9's gate-evaluation and stratum-PAVA populations; conditioning-dependent evidence is legitimately different evidence for the divergence audit and mop-up supersession (dependency ids carry the provenance). (5) REGISTERED COMPROMISES: per-window heldout double-use (bounded, one-sided, monitored via color.stack.arms); cert-cross stratum selection bias toward clean tiles (the masked-furniture floor is the spatially unbiased mitigation). (6) TRANSITIONAL-FORM DECLARATION: the stack is the transitional form of the future payload→raw-pixel channel-model loop; the KnownField carrier and the sampling leaf are the stable contracts that rework keeps; K migrates only when that rework forces K changes. Replay-vs-full doctrine: committed-pose payload replays are development signal (for P9 additionally a kill test — replay conditions on the archived final certificate set and is structurally optimistic); FULL decodes are the only qualification numbers. Measured basis: COLOR-UPLIFT-PLAN §1 (per-region-only color photometry vs K's per-window contract; cmy7 uncalibrated, 19% bound-saturated cells, wrong cells median 18.8/20; no color context ⇒ F1∘F6 multi-scan forfeited; uplift target C620/M43/Y0). Qualification record accrues in docs/COLOR-UPLIFT-MEASUREMENTS.md. |
| v0.51 | 2026-08-08 | **THE SUPPLEMENTAL-LANE LAW** (color-uplift PK4.3; policy `union-lanes-a3-a4b-v1`, scheduler `rung-major-v3-u-lanes`; the law text is §6.2a). An arm that cannot prove universal non-regression is not gated — it is SCHEDULED, as its own lane after the standard ladder, where §6.3's per-address retirement law makes it MONOTONE BY CONSTRUCTION (the store is restored from the accumulated frontier, so `unresolved_streams` never offers a certified stream and the lane's reachable set is exactly the uncertified residue). No adoption gate, no applicability floor; the zero-wrong-certificate audit is the only bar. PLAN: `scale_plan` is codec-aware — K unchanged, a COLOR coding gains `[U(Ln,a3), U(Ln,a4b)]` after the whole l/m/r sequence, both bound to the FINEST ordinary rung (the residue is the page's hardest tiles, so it is read through the best evidence the capture has; and it is the only capture-independent choice — a per-capture footing would be a swept constant, and the supplemental form's whole point is that it has no tuning surface). U-lanes rank below R-lanes in the tail order and ride `--refine`; no fifth flag, because a monotone lane gives an operator nothing to weigh. LANE CLASS: the fourth one — binds its base lane's transform and committed poses like an R-level, owns its own evidence namespace, mints no pose, parks no window, inherits the R leaf's pixel-free pre-gates verbatim, and needs no new pruning law because the §8.2 pool law already IS the residue. IDENTITY, NOT AMBIENT STATE: the forced arm is spelled into the lane id (`u<NN>-<arm>-<ppc>ppc-<dpi>dpi`, one parse in `receive/lane_uplift.py`), so `LaneSpec.uplift_of`/`.arm_override` are DERIVED like `base_lane_id` — no new persisted field, durable state shape unchanged, every archived state still loads — and the override is threaded explicitly `collect_color_evidence(arm_override=)` → `fit_region_stack`, with no environment hatch on any production path. OVERRIDES: `a3` zeroes A3's two PARKED dispersion floors only (per-window pre-gate and the three-way region comparison still rule); `a4b` bypasses `CONDITIONING_PARKED` AND the region adoption gate — the gate is what made the arm unreachable rather than unhelpful (measured: dust-leg refusal at all fourteen conditioned lanes) — while the per-stratum pre-gate stands and all three legs are still published under the distinct reason `region_gate_forced`. FORCE-NULL SKIPS U-LANES ENTIRELY, so `--force-null` stays EXACTLY the pre-campaign receiver. Diagnostics: `lane.kind` + `lane.arm_override` on `level.open`, `survey.uplift_of`/`survey.uplift_arm` on `survey.complete`, `color.uplift_arm` per region and on `payload.plan`/`payload.complete`, and a `[uplift <arm>]` tag on the pane-A lane row. Pins: `tests/holo/test_color_uplift_lanes.py` (plan shape, K has none, identity round-trip, THE SUPPRESSION PIN — a u-lane cannot attempt a certified address — force-null skip, and each override's bypass on the case that makes it necessary). Measured record: COLOR-UPLIFT-MEASUREMENTS §10. |
| v0.52 | 2026-08-09 | **THE OVERRIDE-ONLY LAW, AND THE RETIREMENT OF WHAT MEASUREMENT KILLED** (color-uplift PK-CLEAN; policy `winphot-gainoffset-adaptivehalo-shrink20` / `knownfield-conditioned-marginals-ulane-only` / `union-lanes-a3-a4b-off-v3-codingaware`, scheduler `rung-major-v4-u-lanes-codingaware`; retirement record COLOR-UPLIFT-MEASUREMENTS §12). Five rulings, every one of them a DELETION justified by a measurement already in the record. (1) OVERRIDE-ONLY REACHABILITY. v0.51 scheduled A3 and A4b as supplemental lanes while ALSO leaving them in the standard ladder behind a parked floor (A3) and a park flag (A4b). Both of those are gone. `fit_region_stack` runs A3 iff `arm_override == 'a3'` and A4b iff `arm_override == 'a4b'`, so the standard ladder has no branch that could engage either arm and there is no constant, flag or environment variable to flip. The evidence a standard lane emits is unchanged (both arms were exact nulls there); what changes is that it no longer PAYS for them — a standard lane fits no window maps at all. Pinned structurally: `test_the_standard_ladder_never_calls_either_arms_fitter` counts both fitters on a fixture where both arms DO fire under their own overrides. (2) A3'S APPLICABILITY MACHINERY IS RETIRED. `A3_DISPERSION_FLOOR` (PK4.1, raw mass-weighted gain spread) and `A3_NORM_DISPERSION_FLOOR` (PK4.2, its Huber-White variance-ratio successor), the standard-error plumbing that fed the second one, `map_dispersion`, `WindowMapDispersion` and every diagnostics key they published are DELETED. Measured on all 27 lanes of two captures and NEITHER separates: refusing every lane A3 damages needs a floor above 31.1, keeping every lane it helps needs at most 2.09 (§6.3/§7.4). The finding that outlives them is stronger than either statistic — on the uplift target A3 buys the campaign's largest gain while its fitted maps disagree by only 1.9-3.7x their own standard errors, so A3's benefit does not require the pathology A3 was designed to treat to be detectable, and no test of 'does this page visibly drift?' can be its applicability condition. SCHEDULING is the applicability answer. (3) A4b'S PARK AND ITS LADDER GATE ARE RETIRED. `CONDITIONING_PARKED` is deleted (a flag is still something to flip) and so is the un-forced region-gate branch: the arm is reachable only from a lane that forces it, so `region_gate_failed` became unreachable. The three region legs are still MEASURED and PUBLISHED on every fit — the verdict is always `region_gate_forced` and an auditor reads the legs — because §9.4/§9.8 measured that the gate, not the material, is what made the arm unreachable rather than unhelpful. (4) THE PER-PLANE K PORT IS RETIRED. A5's comparison arm (`detect.fit_context`/`apply_context_offsets` verbatim, one 3x9 ordered-logit fit per plane on the post-head marginals), its plane-composition sum and the MARGINAL application locus are deleted; the `ContextHead` interface and the multi-state matrix stay. Mechanism, stated once because it is the transferable part: ONE CURVE PER PLANE IS SPENT ON THE POPULATION THAT DOMINATES THE LABELS — 83-84% word — so it improves the word leg by .09-.19 nats, damages dust by .04-.20, and the standing three-way gate refuses it; measured, it adopted in 0 of 17 lanes on the uplift target and paid 8,648 s CPU to refuse (§11.2/§11.4). (5) PER-CODING U-LANE APPLICABILITY. `cascade.uplift_arms_for_codec` filters the supplemental tail by what the codec can express: A4b needs a certified SIBLING plane, so a single-stream coding schedules only `[U(Ln,off), U(Ln,a3)]`. Measured waste removed: xerox c3-cmy7's `u03-a4b` ran 98 blocks / 185 attempts for a guaranteed zero at 70 s wall / 144 s CPU (§10.7). An unknown colour codec keeps the full tail — narrowing a plan is a claim about a codec. PLAN SHAPE and therefore the scheduler token move with it. HATCH CONSOLIDATION: `HOLO_COLOR_WINDOW_PHOTOMETRY`, `HOLO_COLOR_HEAD_SATURATION_FLOOR` and `HOLO_COLOR_CONTEXT` are deleted from every production module. Every swept constant now travels as one explicit `color_stack.StackConfig`, threaded `ProductionColorPayload` -> `collect_color_evidence` -> `fit_region_stack` exactly the way `arm_override` already was; the production runtime passes none, so a production decode runs the constants the policy id names and there is no ambient state that could move them. The harness threads it from its own entry points, and the tiers that cannot (full `run_receive`, the specimen runner) REFUSE a sweep flag rather than silently ignore it. `HOLO_COLOR_STACK_FORCE_NULL` STAYS and is now the receiver's only colour environment read: it is a contract ('the receiver as it was'), it can only remove behaviour, and it must reach code paths no configuration object touches. `satfloor30` STAYS in the token — PK3.1's floor is alive and earning; only the way a sweep reaches it changed. Nothing measured is lost: every retired item has its numbers in COLOR-UPLIFT-MEASUREMENTS and its code in git history. |
| v0.53 | 2026-08-09 | **THE CMY7 CODEC LEAF: ITERATIVE DEMAPPING ADOPTED, MARGIN ERASURE REFUSED** (color-uplift PK8/PK9; policy segment `cmy7-demapiter3`; the amendment text is §6.2a, the attempt-cost consequence is §6.3). (1) P3 IS the soft-iteration law's instance: the pack7 demapper and the frame decoder exchange EXTRINSICS up to `color_attempts.DEMAP_ITERATIONS` = 3 times inside ONE attempt — one identity, one retry150 spend, no soft value crossing the call, CRC stop. New surfaces are additive and null-exact: `ldpc.decode.decode_soft` (posterior minus the clipped channel input, bit-identical numerics to `decode`), `decode_frame(want_extrinsic=)` with an additive `FrameDecodeOutcome.extrinsic_llrs`, `channel.cmy7_soft_demap(prior_bit_llrs)` (folded into all 2,048 candidate metrics and SUBTRACTED from the result), `color_tile.cmy7_iterated_decode`. (2) `n_iters` is the BP sum over every inner decode, so the §6.3 two-pass cost bound becomes two passes × DEMAP_ITERATIONS for CMY7 and its exactness clause survives only at the null. (3) `--force-null` REACHES THE LEAF through `color_stack`'s single sanctioned read (`effective_demap_iterations()` returns 1), so v0.51's "exactly the pre-campaign receiver" stays literally true — pinned by a demap COUNTER on a tile built to fail its first decode, and by a force-null replay on the SHIPPED tree reproducing 720/720. (4) REGISTERED, no new bar: per-attempt CRC exposure rises to at most DEMAP_ITERATIONS, guarded empirically by the wrong-certificate audit (0 in 61.2M certified cells). (5) P4's margin-gated pack erasure is a MEASURED NEGATIVE and is RETIRED (MEASUREMENTS §13.10 R11); `channel.state_score_margins` is kept. Bars: **B7 MET** (p* 0.015 → 0.0275 ≥ 0.025, no tested p regressing; not met at two iterations), **B8 MET by P3 alone** and NOT met by P4 (0/20 all-pass, −36 tiles). Paper: xerox c3-cmy7 **771 → 810 certificates, strict superset, 0 lost, 0 wrong**, close still VERIFIED byte-exact, uncertified tail 69 → 30, +45% payload CPU; hp c3-cmy8 an asserted strict no-op; 10/10 specimens identical. Measured record: COLOR-UPLIFT-MEASUREMENTS §13. |

| v0.54 | 2026-08-10 | **THE REVIEW-RESPONSE AMENDMENT** (external review COLOR-UPLIFT-REVIEW.md, every load-bearing finding verified first-hand before disposition; user adoption ruling 2026-08-10; policy `union-lanes-a3-a4b-off-v4-zerofrontier-codingaware`). (1) **THE ZERO-FRONTIER FIX**: v0.51's "inherits the R leaf's pixel-free pre-gates verbatim" was WRONG for U(off)/U(a3) — the R leaf's `not plan.certificates` clause is sound for frontier-anchored refinement but contradicted the u-lane law's own reachable-set sentence: on a zero-certificate capture the scheduled u-lanes were suppressed before touching the raster (reproduced by probe; visible on hp c2-cmy7, where the measured loss is zero because the page is cell-level dead under both configurations, archived yield 0). The pre-gates are now ARM-SPLIT: every u-lane needs poses and an uncertified residue; only U(a4b) needs a certified frontier (conditioning on siblings is vacuous without one). U(off)'s stranding-safety-net property is now true at the zero frontier — the case it was designed for. Pinned: zero-cert u-off/u-a3 reach evidence collection, u-a4b still empty-barriers. (2) **A2 STRUCK from the normative ladder** (never built; formally deferred to a measure-first line — see the §6.2a annotation) and the three never-minted tokens removed from the identity roster. (3) **CRC union bound restated** as `calls x DEMAP_ITERATIONS x 2^-32` for cmy7 lanes (exposures bounded, not counted; §13.8 addendum). (4) **Identity truth**: the effective cmy7 demap count is minted into the attempt decoder identity, so a force-null (1-iteration) attempt and a live (3-iteration) attempt are distinct identities; the harness refuses an inherited FORCE_NULL env when force-null was not requested; full-mode qualification binds the capture TIFF via `expected_sha256`. (5) **Scope corrections recorded**: prior states of ALL codings refuse under scheduler bumps (not only color); B2's final adjudication is FAILED-AS-WRITTEN with the waiver ratified by the user ruling (MEASUREMENTS §14.6); the §14.6a "code the campaign never touches" K-clause wording corrected to bit-identical-with-≤0.1%-measured-delta. Findings evaluated and REFUTED with measurement, no change shipped: lazy LDPC extrinsics, per-coding scheduler identity, u-prefix parser fail-closed. |
| v0.55 | 2026-08-10 | **PK6/A2 MEASURE-FIRST CLOSED AS A MEASURED NEGATIVE (doc-only; no code, no policy bump).** The deferred line ran its stage 1: `_fit_registration` gained the promised return-only per-anchor field (RegistrationAnchors; null-proven — suite green, 10/10 specimens identical at the unchanged policy key, instrumented replays cert-exact to PK-FINAL on all four archived color captures, 61 lanes, 2.27M anchor measurements), and the pre-registered gate (MEASUREMENTS §15.3, committed before the primary field existed) FAILED on every capture — primary xerox c2-cmy7: placebo p 0.0149 > 0.01, reach C 20.8%/M 16.0%/Y 0% vs >=50%, Y saturation-censored. The A2 annotation above carries the disposition and the two routings the data does support. The struck token `winreg-const-shrink8` stays unminted forever. |
| v0.58 | 2026-08-23 | **THE PLAN-PREFIX ACCEPTANCE RULE** (the plan half of the policy-compatibility repair; user ruling 2026-08-23 "do the prefix repair"; no policy bump, no format change, receiver-axis only). A capture recorded before a lane family joined `cascade.scale_plan` carries a plan that is a strict PREFIX of the plan the same format row schedules today — the PLANE-FIELDS `u0x-field` arm is the case that forced it (every archived colour state is one lane short; the pre-campaign ones three or four), exactly as the `off`/`a3`/`a4b` arms would have. `validate_state_for_spec` demanded EXACT equality and refused the whole state at load. It now accepts a stored plan that is an exact prefix of today's and refuses, NAMING the first offending lane, when a stored entry differs (the standard ladder moved, so the retained levels no longer correspond to the lanes that produced them) or the stored plan is LONGER (a lane retired under a live state) — `_runtime_validation.scale_plan_tail`, the rule the replay instruments have run against this archive since PK4.3. Acceptance alone is not resume: `CaptureRecord.status` is what says how many lanes a capture owes, so the runtime ADOPTS today's plan at load (`adopt_current_scale_plans`, before `started`, like the `--no-close` detach) with the retained levels untouched. The phase cursor then does the rest — it IS the prefix length — and the capture resumes into exactly the appended lanes under the ordinary `--mopup`/`--refine` bound; a `u0x-field` tail therefore rides `--refine`, as §9b requires. Adoption is flag-free and writes nothing: the on-disk record changes only when a barrier legitimately rewrites that capture. Measured read-only on the whole archive (16 states): all load; K states are exact (K plans never changed); every colour state is a prefix, appending 1 lane (PK-FINAL) or 3-4 (pre-campaign), sheet I's three captures included. THE ID HALF IS NOT THIS RULING: `receiver_policy_id` still refuses every archived state of every coding (v0.54(5)), so a real archived resume remains blocked until that half is decided. |
| v0.59 | 2026-08-23 | **THE POLICY-DETACH RULE** (the id half of the policy-compatibility repair; user ruling 2026-08-23 "unlock that gate"; receiver-axis only, no format change, no new flag). `receive state belongs to a different policy` no longer raises: `_runtime_validation.policy_detach` DERIVES a continuation under today's policy (§9c). The policy id's five readable components make the change classifiable (`runtime_model.parse_pipeline_policy_id`, the exact inverse of the composition), and each durable ledger belongs to one of them: certificates and captures are kept always (gate-verified against the FORMAT, not against a policy); regions and word-validated poses are kept unless their own segment moved; a moved `payload` segment drops the evidence pools (LLR blobs minted by a different demapper); a moved `address` segment drops the search state (proposals, losers, parked) and clears the ids the retained artifacts named; the close, the counters and the BCH quarantine are kept (a quarantine is a REFUSAL — dropping one would widen the accepted set). The previous id is appended to the new `SessionState.policy_lineage` (schema 26, wall-clock free, oldest first) and announced once as a `PolicyDetachWarning` plus a `session.policy_detach` event carrying both ids and the kept/dropped census. Still refused, and named: a moved `survey` segment (its region ledger is named by every retained level artifact — no keep-the-levels detach exists) and any id that is not a kiss-v1 five-component composition. Detach is monotone by construction (attempts only re-derive; certificates are kept) and composes with the §9a close detach. The archive still loads: schema 25 files lift through one additive migration (`session.STATE_MIGRATIONS`; discovery lifts 11 to 12 the same way, its branches being sessions), because orphaning the archive to record that it is not orphaned would defeat the ruling. Pinned in `tests/holo/test_receive_policy_detach.py`: today's policy is the fixed point and stays byte-identical; a synthetic old-policy state resumes into the appended lanes with a superset certificate id set; and an e2e sim volume, detached and closed, matches the never-detached control byte for byte (its only durable difference is the lineage). |

Historical v0.1–v0.3 section numbering, still cited by some code docstrings
and `RECEIVE-DESIGN-TRIAGE.md`: old §2.5 → §6.2, old §2.6 → §6.3,
old §2.8 → §8.2, old §2.9 → §9.

## 1. Requirements

The Track-3 receiver must satisfy all of these together:

1. recover at least the certificate/payload yield of the qualified historical
   E021→E023c chain on equivalent evidence;
2. retain the old algorithms and admission semantics unless an intentional
   change is designed and qualified;
3. exploit format-v1 pilot/payload colocation to remove obsolete coordinate
   plumbing and duplicated work;
4. remain simple at module boundaries, readable, typed, robust, resumable,
   and independently testable stage by stage;
5. make performance an architectural property: native raster retention,
   bounded crops, direct-from-native scale views, compact evidence, cached
   deterministic structures, frontier scheduling, and no quadratic ledgers;
6. never gain yield by silently changing evidence, double-counting correlated
   views, weakening a gate, or imposing a hidden result-changing resource cap;
7. expose `--diag` as a strictly downstream observer which cannot affect
   state or numerical results; and
8. either return SHA-verified payload bytes, retain honest partial state, or
   refuse. Counts and ranks are advice, not a success condition.

## 2. What colocation changes—and what it does not

Format v1 places 100 BCH word/pilot sites, the metadata bit, and the LDPC
payload in one 64×64 tile. The counter addresses all of them. Consequently:

- E022 pose and address results are already in payload coordinates;
- E023b does not translate between the legacy 60-cell pilot lattice and the
  64-cell payload lattice;
- one sampled window can supply pilot labels, payload LLRs, metadata, and a
  re-encoded certified reference;
- the generator and receiver share the exact site pattern, slot permutation,
  descramble, BCH, LDPC, metadata, and fountain primitives; and
- a certified tile has one unambiguous counter and page/tile location.

Colocation does **not** make absolute phase or page identity observable from
unlabelled ink: the printed sites are balanced and scrambled, so cold
acquisition still tests legal row/page/pose hypotheses and pays the
corresponding false-accept budget. Nor does it justify a new photometric
convention: Track 3 retains raw scanner luma and the historical held-out
calibration path — capture-wide percentile "normalized darkness" is
quarantined Track-2 behavior, not an E021 or Track-3 algorithm.

## 3. One-way production flow

For each physical capture, and for every direct-from-native scale lane chosen
by the scheduler:

```text
authenticated native raster
  -> E021 support survey
  -> E022 placement + BCH addressing
  -> E023b ownership/calibration/cell evidence
  -> max60 scan attempts for the current physical acquisition
  -> max60 union attempts for changed same-lane acquisition evidence
  -> select the latest attempted_failed baseline frontier
  -> mandatory selective retry150 (zero or one max150 attempt/address+digest)
  -> CRC certificates carrying counter-addressed metadata bits
  -> E023c retention barrier
  -> ordinary run: count-gated fountain/SHA close check (v0.33 —
     metadata-terminal states consult unconditionally)
     --complete run: no fountain work at this barrier
  -> if still open, the next level (finer lane, or a mop-up level after
     native) sees the certificates in NeedMap and pose refinement
  -> canonical envelope + SHA-256 verification
  -> ordinary run: stop at the first verified barrier
     --complete run: after every requested barrier, perform exactly one
     fountain/SHA close over the final certificate frontier
```

`receive/production.py` is the composition root and the survey/address
stage home; the K payload driver lives in `production_payload.py`, the
close stage in `production_close.py`, and the color driver in
`production_color.py` (v0.38 split). `receive/runtime.py` owns
the transaction, not the numerical algorithms. Each stage returns a typed
product plus a typed disposition; every installed stage either completes or
refuses, and a refusal is committed only as part of a complete causal prefix.
Pipelines are structurally complete and tests provide explicit fakes.

## 4. E021 survey: retained algorithm, production representation

`survey.py` is the physically denominated E021 production port. Its contract
is deliberately narrow: identify where later placement work is supported and
estimate at most one platen-wide integer cell pitch. It never reads pilots or
invents addresses. (The historical conservative two-scale angle hints were
removed in v0.20: producer-only output — placement derives pose itself.)

The retained algorithm is:

- minor-eigenvalue structure-tensor activity at the historical 340 µm
  footing;
- log-Otsu classification, 5-of-9 density support, and a 9 mm² component
  floor;
- at most one pitch vote per component and one fused platen-wide vote;
- refinement only at region boundaries and coherent separating valleys;
- topology-aware support completion;
- asymmetric coarse/fine fusion, so fine silence cannot erase authoritative
  coarse support; and
- work denominated in measured cells rather than native pixels.

The production changes are representational and computational: block-constant
`SupportMask` records, overlap-qualified whole-platen tensor tiles, bounded
crops, compact run encoding in durable state, and batched/vectorized work.
The qualification compares masks, pitch, refusal, tiled equivalence,
and work bounds against the historical behavior. No normalized-darkness
preprocessing appears at ingest or at the survey boundary. Whole-page scans
pass through the same survey; a large support component is not special-cased
into a second receiver.

## 5. E022 placement and addressing

### 5.1 Ownership

The implementation is split by responsibility:

- `placement/geometry.py`: coordinate systems, affine composition, and window
  geometry (continuous pose only — no page-cell frame);
- `placement/reference.py`: exact format-generated pilot/word references and
  the rot90 algebra;
- `placement/search.py`: complete cold/local/lower-hint hypothesis scoring,
  including all rot90 hypothesis handling;
- `placement/model.py`: immutable results, gates, budgets, and proposals;
- `placement/policy.py`: content-identified statistical policy data;
- `placement/defaults.py`: the exact operational provisional v1 policy row;
- `place.py`: region orchestration, chaining, reference caching, and retained
  E023c hint routing; and
- `words.py`: BCH Stage-A/readout, five-pad/legal-page checks, known-position
  comparison, and word-attempt budget derivation.

No ground-truth provider is reachable from these modules.

### 5.2 Retained E022 principles

- Search and held-out validation sites are disjoint and deterministic.
- Search fits may not consume validation sites.
- Placement acceptance uses the historical weighted mismatch family. On the
  cold correlation route, true search fit, rival/decoy separation, minimum
  winner gap, and held-out true mismatch all pass together. Since v0.30 the
  decoy bar and winner gap evaluate WHOLE-WORD mismatches (all overlap
  sites, both parity classes), with the decoy bar binding the minimum over
  the complete historical rival set: d = 27 binds full words, and the
  parity split can concentrate a cross-page alias's difference codeword
  into as few as 7 of 45 search-class bits, so the parity-class decoy
  question was structurally unanswerable at complete domains
  (docs/FULL-DOMAIN-RIVAL-ANALYSIS.md). Rival selection, the winner's own
  parity-split admission, and every numeric bar are unchanged. The local routes
  (chain, lower-hint) replace rival separation with the bounded 2-cell
  consistency test against their prediction, and the word route is a single
  point check under its own Stage-A union bound — exactly the historical
  E022-v2 behavior, where rivals were reported only where actually searched.
- Stage A accepts a BCH decode only within t=13, with five zero pads and a
  legal page, then requires that seed to pass the ordinary disjoint
  search/validation pilot gate. Since v0.29 slot decoding is LAZY: the
  historical centre slot decodes in the cheap ladder; a deferred window's
  remaining slots decode at most once, at the cold decision point — any
  deferred window's rest-stage acceptance re-opens the chain re-pass, and
  no cold FFT is spent while an undecoded slot remains anywhere in the
  region. Since v0.33 that rule binds within the mop-up level's visit and
  yields to the §3.5 price inversion: a cold whose declared domain is at
  most `cold_first_max_pages` pages (policy data, default 1) may run before
  the remaining-slot sweep, rest-decode following only on its refusal.
  Trial order is stage-wise errors-first within a slot (ties:
  rot_k, then row-major phase); the v0.22 global errors-first order was
  dropped deliberately — trial order never changes admission, a truthful
  window's slots imply one placement, and the only order-sensitive corner
  (a false decode passing both gates) is priced by the union bound
  regardless. The declared domain remains the full multi-slot ceiling,
  declared once per window lifetime, at the level that first samples it
  (declared >= attempted; a mop-up level's remaining-slot decodes add no
  declared hypotheses — a structural fact, not a stored flag). There is no
  extra d>=27 margin or novel neighbor-arithmetic admission rule.
- Known-position word reads distinguish refusal, matching decode, and a legal
  contradictory decode. Refusals never veto an independently accepted Lane-C
  placement. A contradiction invokes the contributor-scoped promotion
  firewall in §5.4: the placement audit remains visible, but contributing
  placements cannot reach payload work.
- Neighbor chaining and same-level anchors are tried before global cold
  work. Since v0.23 this is region-wide, not per-window: cold-needing
  windows defer while any chain/lower/word progress remains, windows are
  processed as a wave-front expanding from accepted placements, and anchors
  are tried nearest-first (the anchor's Jacobian is a local warp model, so
  short transports are the reliable ones). Since v0.33 the deferral crosses
  the lane barrier: a phase-1 lane runs only the cheap ladder and parks
  fall-through windows durably for the capture's same-evidence-lane mop-up
  level, whose hint inventory is every accepted pose of the capture across
  all lanes (native-affine conversion, nearest-first, the ordinary bounded
  portfolio), and the priced session tail runs the mop-up levels last
  (docs/PHASED-SCHEDULE.md).
- Lower-scale accepted and runner-up hypotheses are proposals only. They are
  transformed through native coordinates and must pass on the current raster.
- The retained E023c lower portfolio is eight hints total: normally six
  accepted hypotheses plus up to two runners, with deterministic backfill.
  This is the historical search portfolio, not a general memory or page cap.
- Pose is local. Known-position words are assembled from absolute
  `PilotObservation` records emitted by independent overlapping local windows;
  there is no global stitched `PoseField` object and no assumption that one
  window spans exactly one 64-cell tile.
- Retained E022 window geometry is 200 cells with 40-cell overlap; adaptive
  subdivisions preserve the local-warp contract rather than tile-aligning
  windows for format-v1 convenience.
- The integer-cell ambiguity belongs to addressing. Local photometric or
  spectral objectives are not allowed to manufacture absolute cell offsets.

### 5.3 Complete-domain budgeting

Placement support and Stage-A word admission have separate budgets. Every
placement route freezes its complete hypothesis count `H_r` before examining
the current pixels. For **each** disjoint search and held-out validation parity
population, its effective hard support floor is:

```text
n_r = max(
    30,
    ceil(log2(H_r) / (1 - h2(p_max))) + support_margin
)
```

Here `h2` is binary entropy. The `30` term is the retained executable E022-v2
per-parity minimum (a floor of 57 means at least 57 search **and** 57 disjoint
held-out validation sites), not a v1 false-accept certificate: the historical
weighted rival bar was measured in a substantially higher-support regime and
the legacy record leaves sub-100-site use open. The initial 30-mask-cell patch
check is only a processing precondition; final admission uses the route floor
on both parity populations.

The second term is e026's necessary identifiability bound for the route's
complete admitted domain at the policy's maximum true-error envelope — not a
tail bound for the evidence-weighted mismatch statistic; the declared
familywise alpha does not appear in it, so changing alpha alone does not
change the floor. The weighted true/rival/gap/held-out gate, true-BER
envelope, physical/null behavior, and support safety margin still require
separate qualification. Stage A instead carries its own BCH multi-slot
union bound and, after decoding a legal word candidate, must pass the
ordinary local pilot gate. Its declared domain covers every full 64-cell
slot of the window under four orientations, each slot declared at the
uniform base-slot phase capacity `min(64, H-63) x min(64, W-63)`; trailing
slots physically admit fewer fitting phases, so the declaration is a
conservative ceiling on decode attempts — the single-word union bound only
requires the declared count to dominate the attempts actually made. For
the 200-cell window this declares 9 x 4,096 x 4 = 147,456 hypotheses (the
historical selected-slot form spent 16,384); the alpha = 1e-3 word budget
admits up to 581,074, and the three-row discovery envelope declares
3 x 147,456 = 442,368 (union bound 7.6e-4 < 1e-3 — a fourth 200-cell row
would refuse at construction, exactly as intended).

The route domains are:

- cold correlation: every admitted integer origin, four rot90 orientations,
  every declared page, and—in discovery—the frozen union of every admitted
  format row;
- same-level chain: 49 local origins times every accepted anchor actually
  tried; its exact aggregate floor grows if the anchor inventory becomes large;
- lower-scale continuation: 49 local origins times every selected hint (the
  retained portfolio is at most eight); and
- BCH word seed: the separate Stage-A slot/phase/orientation domain over
  every full 64-cell slot of the window, followed by a page/address-specific
  local placement check. There is no window-wide mask-fraction gate on the
  route: slot damage is priced per phase by the >=90/100 visible-word-site
  floor, so one damaged corner no longer refuses a window whose other slots
  are pristine.

`PlacementBudgetPolicy.resolve()` derives these budgets from the actual format
geometry, legal page domain, 200-cell window, and hint inventory. The
word-route domain in the receiver-wide discovery envelope is rows x
per-window word domain; the stored envelope's counts are data, so resuming a
pre-v0.22 discovery state fails the exact envelope comparison and requires a
fresh session (receiver status is PROVISIONAL; no qualified state is
invalidated). The provisional policy row's word gate identity is
`holo-v1/e022-single-word-multi-slot-union-bound`. Current
implementation-derived examples for `p_max = 0.08`, zero margin, and overhang
search are:

| Admitted placement domain | `H_r` | Floor on each parity |
|---|---:|---:|
| one same-level local neighborhood | 49 | 30 |
| eight lower hints in one row | 392 | 30 |
| one C3 page, row known | 16,926,660 | 41 |
| one C2 page, row known | 35,312,324 | 42 |
| page 0 across all three registered rows | 87,551,308 | 45 |
| all 140 pages of one C2 row | 4,943,725,360 | 54 |
| all 312 pages of the C3 row | 5,281,117,920 | 55 |
| complete all-row discovery envelope | 15,168,568,640 | 57 |

“About 50–57” therefore describes blind cold placement over a large declared
domain, not intrinsically noisier pixels: context supplies identity, and a
word-seeded check or bounded pose/page continuation normally stays at the
historical 30-site minimum. A same-level chain is not silently capped — its
`49 × anchors_tried` domain is recomputed and can raise its own floor.

The cold domain is never truncated for convenience. With no operator `--page`
all addressable pages are legal; an explicit page list mathematically narrows
the request and becomes a separate exact axis of the session contract —
“the legal pages for this request,” never “the pages decoded so far” — and
both that axis and the semantic policy must match on resume.

A decoded maximum is not a terminal marker: under the standard contiguous
generator, observing page `m` proves only `n_pages >= m + 1`, and a high
counter similarly gives a lower bound, format-row-dependent before row
selection. Metadata carries `version` and `K`, not `n_pages` or the
generation repair fraction, so it cannot make the observed maximum an upper
bound; the optional generation manifest records `n_pages`, but the
zero-out-of-band receiver does not currently consume it as authority.

The counter law does expose one additional format clue:
`c(page, tile_y + 1, tile_x) - c(page, tile_y, tile_x) = tiles_x`, so two
correctly associated, vertically adjacent word decodes on one page reveal its
column count—24 for the current C3 row, 36 for either current C2 row, but not
which C2 rate row. Current Holo does **not** construct or consume this
pairwise stride invariant: word candidates are interpreted inside an
already-row-specific branch, E021 `c` votes may prune cell families, and a CRC
tile certificate provisionally selects a row. A future stride observation may
be useful as bounded pruning or scheduling evidence, but it cannot
retroactively reduce the frozen discovery envelope or its support floor.

Consequently, a page/counter decoded from the current pixels may select the
existing page-specific word/local route, and previously established pages may
affect scheduling, but neither may shrink the durable cold domain, lower the
current attempt's floor, or retroactively accept a prior refusal — and page
identity alone does not supply the origin/pose context which makes the local
routes small. A future “seen-page” fast lane may prioritize work or produce a
placement proposal; while unseen pages remain legal, however, it cannot
authoritatively accept at a smaller floor — the ordinary cold decision still
owes comparison against the complete cross-page rival set at the full-domain
floor. Reduced-floor acceptance would require independent authority to narrow
the legal page domain before the attempt, with the source, exact page set,
`H_r`, floor, and domain epoch retained and qualified. No current route
performs global adaptive page-domain narrowing.

The policy is immutable declarative data. Its identifier is a hand-bumped
qualification literal (the holo-kiss ruling: constants are data, not
identity), so editing a statistical field does NOT change the identifier;
cross-run safety rests on whole-dataclass equality at resume, the envelope
coverage check in `resolve()`, and the executable golden pins in
`tests/holo/test_placement_policy_golden.py`, which freeze the complete
numeric row (alpha, BER envelope, gate bars, margin, word alpha) and the
domain/floor table below — a mismatch there is a design amendment, never a
test edit. The runtime policy identity also binds the survey, payload,
scheduler, and close semantics. The exact page hypotheses are a separate
required session axis; both must match on resume. Source-code hashes are
deliberately absent. Reference fields and page-invariant transforms may be
cached or batched only while preserving exact scores, candidate ordering,
and acceptance — never by approximating the cold domain or discarding a
candidate because a volume is large. The machine-readable report exposes the
resolved route domains and per-parity floors, including the complete
discovery value above (`ProductionAddress.route_domain_report`, published
as `placement_route_domains` in the diagnostic `report.json`, v0.24); a
prose table is an explanation, not the source of numerical truth.

Until physical v1 qualification freezes a replacement, the production root
selects one exact provisional row: familywise alpha `1e-3`, true-channel BER
stand-in `0.08`, the unchanged historical weighted gate (`search < 0.20`,
`validation < 0.24`, `rival > 0.20`, gap `>= 0.08`), support margin zero,
word alpha `1e-3`, and the pre-existing qualification identifiers —
historically believable E021–E023c development values, not measured v1
claims. The row moved from qualification-only storage into active defaults
without a numerical or identifier change; implicit or explicit selection
yields the same semantic pipeline identity.

Qualification status is deliberately outside semantic identity: every
`ReceivePipeline` must state it explicitly (no default `qualified` label),
and a current production composition and its result carry `provisional` plus
the open duties without that annotation changing state compatibility, scores,
candidate order, certificates, or bytes. Every actual provisional run warns
before state load/creation or raster access; the CLI forces that warning on
every invocation, and `--diag` records `receiver.provisional` as a detached
first event and in the final human/machine-readable report.

### 5.4 Known-position BCH outcome authority

**Selected policy: final-word, selected-contributor, placement-scoped
quarantine.** This is an intentional precision-preserving departure from the
historical whole-session abort. It changes only downstream promotion after
ordinary E022 placement has finished; it does not change BCH decoding,
placement scores, candidate order, admission bars, or refusal semantics.

A known-position word outcome has three materially different states:

- **refusal:** coverage is algebraically insufficient, or no legal
  pad-valid codeword decodes; it carries no negative authority and never
  vetoes placement;
- **matching decode:** a legal decoded counter equals the counter implied by
  the accepted placement; and
- **conflict:** a legal, pad-valid decoded counter differs from the counter
  implied by that placement — affirmative contradictory evidence, not another
  spelling of refusal.

The historical E022 session records all three outcomes; its E023 input
boundary treats any conflict as a fail-closed integrity event and refuses
payload emission, while refusals remain harmless. That rule was
precision-conservative rather than proof the placement was wrong: the
historical per-tile aggregate could not attribute the contradiction to one
offending window. Holo can be selective because every final site read names
the accepted E022 patch that produced it. The firewall runs once per LEVEL,
after all of that level's windows have completed and its final
known-position words have been computed (v0.33: a mop-up level runs its own
firewall over its own final words; quarantine accumulates by union on the
evidence lane, and raw site reads are never pooled across levels — the
patch-ordinal namespace is shared per evidence lane, so quarantined ids
stay unambiguous):

1. for each word site, retain the existing strict strongest-absolute-evidence
   observation per source-SHA/lane acquisition key; equal strength keeps the
   earlier observation;
2. combine those selected per-acquisition reads with the existing
   evidence-weighted vote and run the unchanged known-position BCH decode;
3. for a legal decoded counter that contradicts the expected counter, take the
   union of patch ids attached to the selected reads actually used by that
   word; and
4. quarantine those complete placements. A placement that merely overlaps the
   word but loses every same-scan site selection is not quarantined.

The complete placement—not merely the contradictory tile or its pilot sites—is
the safety scope: a conflict can indicate a wrong page/origin/pose, so payload
from anywhere in that independently fitted window is suspect; conversely,
quarantining the whole lane or every placement touching the tile would discard
evidence that did not contribute to the contradiction.

The Address→Payload contract is therefore:

- all accepted/redundant placements and their compact poses remain retained;
  raw site observations and the detailed address-attempt audit remain
  transient diagnostics;
- continuation hints and finer-lane pose proposals owned by a quarantined patch
  are removed;
- a quarantined patch is never sampled for payload calibration and can produce
  no payload LLR, owner, evidence block, decoder attempt, certificate, or
  certified-pose refinement;
- unquarantined placements continue normally in the same lane; and
- E023c refinement requires and processes windows only for the promoted subset,
  while retaining quarantined placements unchanged in the address artifact.

`NeedMap` remains certificate-derived; the firewall creates no second
solved/needed authority. Neither the expected nor the contradictory decoded
counter is marked solved by BCH — withheld evidence leaves the expected tile
needed unless some unquarantined placement independently produces a
syndrome+CRC certificate — and the decoded counter is not inserted as a
payload address.

Recovery is fresh-evidence only: a later independently fitted, non-conflicting
placement — at a finer lane or from another capture — may recover the tile.
The quarantined placement is never automatically rehabilitated, and its raw
BCH votes are not replayed or pooled across barriers, keeping correlation and
scale-lane isolation unchanged and avoiding a second cross-capture word state
machine.

The durable address artifact stores one typed `BchConflictRecord` per
contradictory word: page/tile, the contradictory decoded counter, errors,
erasures, and sorted contributing patch ids. The expected counter derives from
page/tile plus the active format row, observed sites derive from erasures, and
the quarantined set is always derived as their union — none is duplicated or
persisted separately. Barrier and full-replay validation bind each contributor
to exactly one accepted retained pose and reject any retained or newly merged
compact-evidence origin from a quarantined patch; the strict state schema
intentionally refuses pre-firewall state rather than guessing the missing
decision. Live address progress exposes conflicting words and
quarantined/promoted placement counts; the final report derives exact
conflicts and the unique quarantine count from the retained records.
Matching/refused word outcomes and raw votes remain transient, so cold Pane C
still correctly labels general word state unavailable.

The alternatives were rejected for narrow reasons: session-fatal handling
throws away clean attributable coverage; tile-only or site-only quarantine is
too narrow for a potentially wrong pose; diagnostic-only handling lets
affirmative address contradiction reach payload; retaining all raw votes with
automatic rehabilitation adds state without a justified recovery rule. The
selected rule gains clean-placement survival and exact audit at the cost of
being less conservative than historical session abort.

Historical real-confetti work observed zero contradictory E022 decodes in
1,780 attempted reads and zero wrong final payload certificates, so this is a
guard for an unobserved mathematical tail, not a response to a measured
failure — and those results do not qualify format-v1 Holo.
Synthetic/adversarial tests cover attribution, hint suppression, clean
survival, all-quarantined empty emission, fresh recovery, refinement,
persistence, replay validation, and reporting. Physical v1 conflict incidence
and false-quarantine/yield impact remain part of the production qualification
campaign.

## 6. E023b payload transaction

### 6.1 Cell evidence and physical provenance

`payload.py`, `payload_model.py`, `_payload_sampling.py`,
`_payload_context.py`, `_payload_reuse.py` (the v0.38 three-way split of
`_payload_windows.py`), `evidence.py`, and
`evidence_blocks.py` implement the historical E023b transaction over the
colocated tile geometry. They consume `AddressResult.payload_placements`
(§5.4 owns that promotion decision) plus the observation-free
`label_placements`; under the §8.2 pool law, promoted windows that owe no
payload work (certified-complete or zero-payload) join the same label
channel — sampled for the region fit, never owner-eligible or returned.

Within one physical capture and scale lane, each payload cell has one owner:
overlapping E022 windows compete, they do not sum. Every admitted source is
one original scanner acquisition and contributes at most one owner-frozen
component per lane/tile; distinct physical acquisitions may contribute to the
same-lane staged calibrated-LLR sum. Deterministic scale views are generated
internally, retain the same capture identity, remain in separate lanes, and
meet only at the certificate boundary.

Since v0.33 a level's evidence lane is `mopup_of or lane_id`: a mop-up level
contributes to its base lane's evidence exactly as a deferred second pass of
that lane — same aperture, same frontier, same union law — restricted to
work the base pass did not commit. A mop-up block may replace a live block
at its evidence-lane key only as a strict-superset extension agreeing
exactly on every previously-observed cell; committed cells are never
revised.

The durable representation stores observed-cell masks and bounded float32
LLRs in blocks keyed by capture, lane, page, and tile. Bounding is enforced
at emission time, by the calibrated detectors (the LAYERS bounded-LLR
invariant); the block boundary itself validates finiteness only. A `scan`
attempt has
exactly one acquisition component; a `union` attempt has at least two
same-lane components. Attempt identities derive from the exact component
frontier, address, stage, and decoder profile, so repeating an unchanged
attempt is an authoritative no-op, not another chance at the CRC — a rule
delivered by determinism plus invocation-local deduplication, not by a
durable spend-once ledger (attempt records fold to counters at the barrier;
see §6.3).

Every unresolved capture/lane component remains live until that tile
certifies. Only the newest failed baseline at an address is eligible for the
immediate retry150 schedule, but older scale-lane components are not waste:
the phased schedule needs them when a later physical acquisition joins the
session and reaches the matching evidence lane, forming its same-lane
union. Certification removes every
remaining numerical block at that address.

### 6.2 Calibration and detection

Ingest supplies raw luma. Detection retains per-window `pava-v1` as the
historical primitive and uses per-region `ctx-pava-v1` with held-out adoption
for every production scale lane, deterministic search/validation partitions,
bounded LLRs, and calibrate-or-refuse behavior. There is no global
detector/profile and no CLI detector selector: production is deliberately
hard-wired to `ctx-pava-v1`. Format-predictable word/filler sites provide the
E023b calibration labels; per the §8.2 pool law those sites also arrive as
label rows from D7 label placements and from certified-complete/zero-payload
windows, never terminal-gated, feeding the region fit population identically
in every pass. CRC-certified payload cells are used later by E023c
pose refinement and divergence reporting, not to refit the generation-zero
E023b detector. A candidate placement never labels itself by assuming its
payload decisions are correct.

The provisional CMY8 path follows a separate, explicit color contract. Word
and dust furniture train and validate one equal-prior eight-state QDA on
deterministic, disjoint search/held-out partitions; the historical coordinate
parity is unchanged when every state already occurs on both sides, and for a
sparse one-tile state wholly on one side its canonical first row moves to the
empty side, so no row appears in both populations. First-order component PAVA
uses all 20 format-known dust rows on that one fitted score axis; there is no
aggregate `N >= 300` area proxy. Per the §8.2 pool law, furniture-site label
rows — from D7 label placements and from certified-complete windows — join
those train/validation (and dust-calibration) populations and the region
pitch/divisor pool in every pass, never terminal-gated and never emitting
evidence of their own.

C, M, and Y qualify independently: each binary class needs six labels, and
each class needs two nuisance states represented by at least three labels.
Those numbers are the actual p120 base-multiset contract — the six missing
CMY8 states occur three times each, and every component has at least six
labels in both binary classes before the two address-varying extras — so one
decoded 100-site BCH word plus its 20 dust sites can start a clean
first-order payload attempt. An unsupported component emits exact-zero
evidence while qualified siblings remain usable; a degenerate joint QDA
erases all three; raw or rescaled uncalibrated QDA scores never cross the
evidence boundary.

A CRC certificate is external exact payload authority, not a candidate
decision. Only certificates committed before a lane opens may supply exact
registration/component facts and complete-state labels in that lane; a
certificate minted by current-lane BP is never fed back before its barrier
and becomes available to a later scale lane or physical capture. Partial CMY8
certificates remain component-only and never fabricate their two siblings,
and the certificate work index is conflict-checked before any fully-certified
region fast path. This preserves the session's prior-barrier dependency law
and provides bounded second-order improvement across real acquisitions
without self-training or a decode/calibrate loop.

### 6.2a The color calibrated-evidence stack (color-uplift campaign, v0.51)

Charter, engineering detail, corpus, pre-registered bars, and packet program:
`docs/COLOR-UPLIFT-PLAN.md` (v1.5). This section is the normative law; the
plan is the execution contract. Receiver status stays PROVISIONAL throughout.

**The stack.** Color evidence for one region is produced by one sequential, greedily
gated arm ladder replacing the current inline baseline-vs-registration choice:
A0 baseline → A1 region registration (the two existing arms, byte-identical) →
A2 per-window plane-registration residuals **[STRUCK v0.54 — declared here at
v0.50 and NEVER BUILT: packet PK6 never ran, no measurement, no code, no
minted token; formally deferred by user ruling 2026-08-10 to a measure-first
future line (gather the per-anchor registration field on the existing corpus
first; build the arm only if window-scale structure exceeds the shrinkage
prior's noise floor). Spec preserved for that line: constant per window,
shrunk toward the region constant+slope-in-y model, κ=8; <8 anchors ⇒ exact
region fallback. **v0.55: THE MEASURE-FIRST LINE RAN AND THE GATE FAILED —
A2 STAYS UNBUILT, the line is CLOSED as a measured negative**
(COLOR-UPLIFT-MEASUREMENTS §15: per-anchor field mapped on all four
archived color captures under the deployed decode, cert-exact to PK-FINAL;
plane-differential window-scale structure is REAL at τ ≈ 0.1–0.3 dots but
predominantly smooth/plane-common, the own-window κ=8 arm reaches only
0–21% of the primary residue, and the reachable halo variant is a field
model, not this arm; routing: pose refinement for the common mode,
region-field enrichment for the smooth differential — both future
measure-first lines answerable from the archived regmap NPZs)]** →
A3 per-window photometric maps (per-RGB-channel gain+offset, weighted least squares
toward the incumbent region QDA's class means over the window's OWN labelled cells —
neighbours pooled only on starvation — class-balanced, shrinkage λ0 toward identity,
per-window held-out pre-gate, region dispersion floor; region QDA refit on mapped
features — **PK4/PK4.1 amendments below**) →
A4 kind heads (cmy7: scalar-temperature + 6-offset head fit on the selected arm's
held-out scores via the (131y+17x)&2 sub-split, refusal ⇒ the literal current
uncalibrated path, L∞=20 bound applied last; cmy8: the standing in-sample dust PAVA,
pattern-stratified under A4b) → A4b KnownField-conditioned marginalization (below) →
A5 per-plane context (3×9 ordered bins via the K ctx-pava primitives verbatim, applied
per SUPPORTED plane only for cmy8 and as the per-state plane-composition sum for cmy7;
one joint 7-way validation gate for cmy7, strict-improvement 1e-9). Every stage adopts
only through the standing three-way held-out comparison (total strictly better by 1e-9
AND word AND dust not worse); every refusal is a BIT-EXACT null (same array objects, no
identity transforms). The stack is transient — fitted per region per lane, nothing
persisted, evidence-block shapes unchanged — and every fit is a deterministic pure
function of canonical-ordered inputs (Newton/bisection/PAVA/Theil–Sen; no RNG). Stages
are typed scores→scores with declared label needs; K's pipeline does not migrate (its
per-window pava-v1 + ctx-pava-v1 contract in §6.2 is untouched; the shared surface is
the imported primitive layer only).

**PK4 amendment (A3, measured).** Two things the v0.50 sentence did not state, both
forced by PK3.1's measured lesson that a furniture-population gate is necessary and not
sufficient. (1) A3 carries a **per-window held-out PRE-GATE**: a window's map is applied
only where it strictly improves (1e-9) the INCUMBENT region model's class-balanced NLL
on that window's OWN held-out labels — the region-level three-way comparison never sees
a candidate built from windows that could not each earn their own map. Both gates are
still furniture populations; that limit is registered (P6 is its fix) and is why this
arm's evidence is per-lane certificate deltas, never fit losses. (2) The refusal
vocabulary is K's, verbatim: `search_class_starved` (fewer than 40 labelled search cells
in window ∪ halo), `insufficient_search_support` (fewer than three represented states —
W plus ≥2 inked; six parameters are not identifiable from two class means),
`heldout_starved` (fewer than 20 own-window held-out labels), `validation_gate_failed`
(the pre-gate). The halo is rows-only geometry — every window of the same region whose
page-cell bbox meets this window's bbox dilated by its OWN height/width per side — and
the class-balanced weights are `color_calibration.class_balanced_weights` generalized to
fractional base mass (bit-identical to it when every base weight is 1), so `n_eff` and
λ0 are measured in the same unit as the label floors. The constants are SWEPT and named
in the policy token by construction (`WindowPhotometryConfig.policy_token`), and the
EFFECTIVE values are published per region (`color.window_maps.prior_labels` /
`.dispersion_floor`) so a swept run states its own numbers rather than relying on the
token. Kind-AGNOSTIC: the maps transform RGB features, so cmy8 regions fit them too —
unlike A4, A3 is not a cmy8 no-op.

**PK4.1 amendments (A3, measured).** Two changes to the family above, both forced by
measurement, plus one unresolved constant. *(Change (2), the region dispersion floor,
is RETIRED at v0.52 along with PK4.2's successor — see the PK4.2 verdict below and
COLOR-UPLIFT-MEASUREMENTS §12. Change (1), the adaptive halo, STANDS.)* (1) The halo is ADAPTIVE, not weighted: a
window fits from its OWN labelled search cells whenever they clear the search-label and
state-support floors, and pools its neighbours' (at weight 1.0, and only then) when they
do not. The swept halo weight leaves the family. Measured basis: the nine-point grid's
halo axis was monotone (row means +14.7 / +9.0 / +5.7 addresses for 0.25 / 0.5 / 1.0)
and own-window-only measured +27 on the same unit, i.e. a neighbour's cells are evidence
about the NEIGHBOUR's photometry and pooling dilutes exactly the window-scale drift the
arm exists to track; the starvation case the halo was designed for occurs, but rarely
(4 windows in one lane of the whole eight-capture corpus). `search_class_starved` and
`insufficient_search_support` are therefore counted over "own, or own ∪ halo if own
alone was starved"; `heldout_starved` was and stays own-window only. (2) A3 gains a
REGION-level applicability condition in PK3.1's shape — `A3_DISPERSION_FLOOR` on the
per-region photometric DISPERSION of the fitted maps (the mass-weighted standard
deviation of the per-window gains, max over RGB; the offsets' is measured, published and
ungated). Below it the arm refuses with `photometric_dispersion_below_floor` and the
mapped arrays are never allocated — an exact null that is also the memory saving. (3)
The floor's VALUE is NOT swept-and-frozen: measured, the statistic tracks sampling
noise as strongly as photometric drift (COLOR-UPLIFT-MEASUREMENTS §6.2/§6.3 — the lane
A3 damages carries the corpus's highest dispersion and the lane it helps most one of the
lowest, so no threshold in either direction separates the two captures), and A3 stays
NOT ADOPTED with a parked floor above every dispersion measured on paper. A normalized
statistic (observed spread against the spread the fit's own noise predicts) is the
named next candidate; it is not built.

**PK4.2 amendment (A3, measured, and NEGATIVE).** The named successor is BUILT and
MEASURED, and it does not separate either; A3 stays NOT ADOPTED.
`A3_NORM_DISPERSION_FLOOR` is a VARIANCE RATIO rather than a raw spread: the observed
mass-weighted between-window variance of the fitted gains, over the variance those same
fits' own residuals predict for those same windows. Stated exactly, per RGB channel `c`,
over the windows that earned a map, with effective label masses `m_w` and shares
`p_w = m_w / SUM m`:

    observed_c  = SUM_w p_w (g_wc - gbar_c)^2                   (PK4.1's numerator)
    predicted_c = SUM_w p_w (1 - p_w) s_wc^2                    (its null expectation)
    NORM        = median over c of  observed_c / predicted_c

`s_wc` is the standard error of that window's SHRUNK gain — the heteroskedasticity-
consistent (Huber-White) sandwich for the window's own weighted least squares, scaled by
`kappa_w^2` so numerator and denominator measure the same quantity. The robust form is
required, not stylistic: the fit weights are CLASS-BALANCING weights, not replication
counts, so the textbook `sigma^2 / S_xx` would understate the variance of a gain
leveraged by a sparsely populated state — precisely the 2 px/cell regime the statistic
exists to detect. `(1 - p_w)` is what the estimated weighted mean absorbs. The reducer
is the MEDIAN channel, not PK4.1's max: a ratio has a denominator, so one quiet channel
would dominate a maximum on arithmetic alone. Both square roots of the chosen channel
are published beside the ratio (`observed_dispersion` / `predicted_dispersion`) so it
can be read rather than believed, and 1.0 is the no-structure null exactly. Fewer than
two accepted maps stays UNMEASURED (`-1.0`) and refuses; the raw gain and offset spreads
stay published and become UNGATED, joining the offsets as measurements the record keeps.
Fit-side only — window maps, their own residuals, their own label mass — so it is
pre-decode, conditions on no certificate, and a deployment capture computes it before it
decodes a tile.

The measured verdict is COLOR-UPLIFT-MEASUREMENTS §7, and it is a STOP. **Both floors
are RETIRED at PK-CLEAN** (v0.52; retirement record §12): the constants, the
Huber-White standard-error plumbing that fed the normalized one, `map_dispersion`,
`WindowMapDispersion` and every diagnostics key they published are deleted, and A3's
applicability is answered by SCHEDULING instead — the arm is unreachable from the
standard ladder and runs only in its supplemental lane. What follows is why, kept
because the reasoning transfers and the code does not. Harvested at floor 0 on all
27 lanes of both captures: refusing every lane A3 damages needs a floor above 31.1 while
keeping every lane it helps needs one at or below 2.09, and neither the numerator, the
denominator, nor PK4.1's raw spread separates them either. WITHIN a capture the
normalization works and PK4.1's diagnosis is confirmed — xerox c3-cmy7's damaged l00
falls from the corpus MAXIMUM on the raw statistic to below-median on this one — but a
variance ratio is a DETECTION statistic, so at fixed drift it grows with evidence, and
across captures it acquires a label-mass confound in the sampling confound's place
(measured spearman +0.73 with a lane's labelled population). The structural finding
underneath: on hp c3-cmy8 every lane's maps disagree by only 1.9-3.7x their own standard
errors — no resolvable window-scale drift — and A3 still pays +62 addresses there. A3's
benefit therefore does not require its designed pathology to be detectable, which is why
every "is this page sick?" gate has failed; its LADDER-side gain waits for the
payload->raw-pixel channel model this stack is the declared transitional form of, not
for a sixth constant, and its RESIDUE-side gain is claimable now through its u-lane.

**Cross-lane trust hierarchy (law).** The lane bus (`EvidenceContext`) carries three
authority tiers, each restricted to a consumer class: CANDIDATE facts (pose proposals,
losers, parked windows) steer search only — cost, never content; COMMITTED geometry
(poses, regions, label poses) places samples, carries label rows, defines refine
domains, and projects; CERTIFIED content (CRC certificates) labels, suppresses, and
conditions likelihoods. Raw evidence never crosses lanes. A wrong candidate hint can
waste time but structurally cannot corrupt evidence.

**Iteration laws.** Soft iteration is legal only INSIDE one attempt (the P3 demap↔BP
loop, contained within one tile's decode). Across attempts, lanes, and captures, only
certified (hard, prior-barrier) knowledge conditions anything. Soft cross-attempt
feedback — feeding candidate posteriors from one stream's failed decode into another's
evidence — is REJECTED: it breaks the certificates-are-authority law, propagates
correlated errors across tiles, and would require a new false-accept qualification.

**P9 conditioning ruling (A4b).** Restricting a cell's state marginalization to the
subset consistent with prior-barrier certified sibling components is legal under this
section's component-only law: conditioning on authority fabricates nothing about the
remaining components. Arity-0 unconditioned marginalization is the NORMAL case (all of
lane 0, most early-lane cells), not a fallback. Head calibration is stratified by
(plane, conditioning-pattern) — {∅, {sib1}, {sib2}, {both}} per plane — under the
two-source provenance law: (a) cert-cross cells are the primary stratum material where
dense (deployment-exact, on captures whose sibling streams certified); (b) the floor
everywhere is deterministically MASKED format-known cells, reveal-bit = (131·y+17·x)&4
(extending the established &1 split / &2 sub-split hash family). The masking law is
SCOPED — a view, not a mutation: masking exists only inside P9's gate-evaluation and
stratum-PAVA populations; every other consumer (the QDA fit, context conditioning,
registration templates, ownership labels) sees the cell's true state exactly as today.
Pinned three ways: one masked cell contributes its full state to the QDA, its masked
pattern to exactly one stratum, and its true bits to context/registration. A starved
stratum falls back to the unconditioned marginal. Conditioning-dependent evidence is
legitimately different evidence: the divergence audit and mop-up supersession compare
under the dependency-certificate provenance already carried by evidence blocks.

**PK10 amendments (A4b, measured).** Four, all forced by building and running it;
the measured record is COLOR-UPLIFT-MEASUREMENTS §9. (1) The reveal field is TWO
bits, `(131·y+17·x) & 12`, whose LOW BIT is the ruling's named &4 and selects sib1
vs sib2 exactly as written; the high bit adds "both". One bit chooses between two
siblings but cannot also choose the ARITY, and there are three nonempty patterns —
with two bits the four codes PARTITION every furniture cell into exactly one
pattern per plane, which is what makes "exactly one stratum" literally true.
Measured uniform (1024 each over a 64×64 tile) and exactly independent of the &1
QDA split and the &2 P1 sub-split. (2) The stratum material is the INCUMBENT's own
calibration population stratified — dust (both split sides, masked) plus certified
payload cells, and NO word. Symmetry is a requirement, not a preference:
`_fit_detector` calibrates the incumbent maps in-sample on exactly that population
and keeps word out, so a candidate fitted on anything else meets an optimistic
rival on the gate's DUST leg and a pessimistic one on its WORD leg. Measured on hp
c3-cmy8 l01, the asymmetric first cut inflated the dust regression by 64%
(+0.0233 vs +0.0083 nats). Only PARTIALLY certified cells are new material — they
resolve no state and so can never be owners. (3) Only CERTIFIED knowledge
conditions an EMITTED cell: format furniture is known exactly and is still
excluded, because §6.3 step 3 erases furniture before any bit of it is used, so
conditioning it would move every block digest for no decode. Furniture is fit and
gate material only, which is where the masking law wanted it. (4) The per-stratum
PRE-GATE is A3's shape (one strict improvement on that stratum's own held-out
cells), with the standing three-way rule reserved for the region comparison; all
three legs are measured and PUBLISHED per stratum (`color.conditioning.
strata_deltas`) because a region refusal is spent by particular strata and a
region number cannot name them. The three-way pre-gate variant was built and
measured and is NOT adopted (§9.7: it keeps 2 strata of 9 and +11 certificates
where the single test keeps 8 and +19).

**PK10 measured status: BUILT AND INSTRUMENTED, ADOPTION REFUSED — the arm does
not earn its place on this corpus.** Full-domain replays: on the hp c3-cmy8
uplift target it is an exact end-to-end null (663 certificates cert-for-cert
identical to the archive, M = 43, bar M>43 NOT met) because the standing
three-way region gate refuses on the DUST leg at all fourteen conditioned lanes
while total and word improve by 0.015–0.023 nats — including under MAXIMAL
conditioning (the seeded-frontier kill test, §9.4: zero new certificates because
the arm never applied). On xerox c2-cmy8 the close still verifies byte-exact but
the ADDRESS delta is **net −5** (5 gained, 10 lost, nine of them at the finest
lane); the +19 a two-lane library sweep measured decomposes into 1 new address
and 18 re-timings, which is PK4's failure shape. Zero wrong certificates
throughout (32.7 M cells audited, agreement 1.000000000).

The mechanism is identified and is registered compromise (ii) below, measured
for the first time: the dust cost — and, by hypothesis, the l03 certificate
losses — concentrate in exactly the strata fed by CERT-CROSS material, and the
severity scales with how selective the certification was (hp l01 conditions on
the easiest 3% of the page; xerox c2-cmy8 l01 on 64%). A material SIZE floor
cannot separate them, because on hp the harmful strata are the material-rich
ones. **The named next candidate is a cert-versus-masked BALANCE rule** — how
much deployment-exact-but-selection-biased material may outvote the spatially
unbiased floor — and it is **NOT sweepable from this corpus**: two cmy8
captures, and the statistic that would have to separate them is confounded with
how much of each page had already certified.

**A4b is therefore PARKED BY FLAG** (lead ruling 2026-08-08; *the FLAG is RETIRED at
v0.52 — the verdict stands but the arm is OVERRIDE-ONLY rather than parked, and the
token says `ulane-only` rather than `parked0`, because since PK4.3 the arm CONTRIBUTES
from its own lane. See the v0.52 amendment below and COLOR-UPLIFT-MEASUREMENTS §12 R5*):
`color_conditioning.CONDITIONING_PARKED = True` short-circuits the arm before
the arity census, the population gather and every fit, so parked means ABSENT —
default summary, no `color.conditioning.*` key, and emission passes the same
array objects the arm-never-built receiver passed (pinned byte-for-byte on a
capture where the unparked arm does adopt). It parks by FLAG and not behind a
threshold because no statistic separated the lanes it helps from the ones it
costs, and a constant chosen now would be fitted to the data that refused the
arm. The identity carries the state: the token segment
`knownfield-conditioned-marginals-parked<N>` is GENERATED from that constant in
`satfloor30`'s pattern (0 = contributes nothing, 1 = live), so a declared
identity can never claim conditioning the tree did not run, nor the reverse.

**P9's remaining in-scope evaluation moves to the supplemental-lane form below**
— suppression-protected and monotone by construction, so it needs no gate at all
— which measures forced conditioning on the RESIDUE. That is the question the
seeded-frontier kill test could not reach: it answered "no certificates" only
because the region gate blocked the arm upstream of any decode.

**THE SUPPLEMENTAL-LANE LAW (PK4.3, `union-lanes-a3-a4b-v1`).** *An arm that
cannot prove universal non-regression is not gated — it is SCHEDULED.* It runs
as a SUPPLEMENTAL LANE (u-lane) after the standard ladder, where the per-address
retirement law of §6.3 — a certificate suppresses its stream, and a certified
address is never re-attempted — makes it MONOTONE BY CONSTRUCTION: the store is
restored from the accumulated frontier before the leaf runs, so
`unresolved_streams` never offers it a certified (address, stream) and its
reachable set is exactly the uncertified residue. It can therefore only ADD
certificates. **No adoption gate, no applicability floor; the zero-wrong-
certificate audit remains the only bar.** Evidence stays lane-scoped (raw
evidence never crosses lanes, unchanged from the trust hierarchy below) and the
divergence/conflict machinery already governs cross-lane disagreement — a
u-lane's blocks are its own, its certificates cross exactly as any lane's do,
and a conflicting certificate is fatal, never voted.

*Plan shape.* `scale_plan` is codec-aware: K keeps `[L0..Ln, M(L0)..M(Ln),
R(L0)..R(Ln)]` unchanged and a COLOR coding gains the tail `[U(Ln, a3),
U(Ln, a4b)]` — one lane per registered arm override, both bound to the FINEST
ordinary rung. Finest because a u-lane reads the residue that survived every
earlier barrier, by construction the page's hardest tiles, so it should read
them through the best evidence the capture has; and because it is the only
capture-independent choice — a per-capture footing would be a swept constant,
and the point of the supplemental form is that it has NO tuning surface.
Supplemental lanes rank below refinement lanes in the tail order (they must run
after every lane that could still shrink the residue) and ride `--refine`,
which already means "the whole plan"; there is no fifth flag, because a
monotone lane gives an operator nothing to weigh.

*Lane class.* `U(Lk, arm)` is the fourth lane class. It binds its base lane's
exact transform and committed poses like a refinement level (`base_lane_id`),
owns its own evidence namespace (`evidence_lane_id` = itself), mints no pose and
parks no window, and inherits the R leaf's pixel-free pre-gates verbatim (no
committed poses, no certificates, or every committed span certified ⇒ the lazy
raster stand-in never materializes). Its domain needs no new pruning law: the
§8.2 pool law already drops wholly certified regions before image work and
demotes certified-complete windows to label rows, which IS the residue.

*The override is IDENTITY, never ambient state.* The forced arm is spelled into
the lane id (`u<NN>-<arm>-<ppc>ppc-<dpi>dpi`, grammar and the one parse in
`receive/lane_uplift.py`), so `LaneSpec.uplift_of` / `.arm_override` are DERIVED
exactly as `base_lane_id` is — no new persisted field, so the durable state
shape is unchanged — and a durable plan, a resumed state, a `level.open` event,
a `survey.complete` detail and the pane-A lane row all read the same fact from
the same string. It is threaded explicitly (`collect_color_evidence(...,
arm_override=...)` → `fit_region_stack`); there is no environment hatch for it
in any production path, and an ordinary, mop-up or refinement plan entry cannot
carry one.

*What each override bypasses, and nothing else.* `a3` zeroes A3's two PARKED
region dispersion floors (raw and normalized), so the window maps fit and apply;
the per-window held-out pre-gate and the standing three-way region comparison
still rule, i.e. the u-lane runs the arm measured at floor 0, not a new one.
`a4b` bypasses `CONDITIONING_PARKED` **and** the region adoption gate, because
the park is a flag and the region gate is what actually made the arm
unreachable: measured, even under maximal conditioning it refused on the dust
leg at all fourteen conditioned lanes while total and word improved. The
per-stratum pre-gate is NOT bypassed — it is how the arm is constructed, not
whether it may run — and all three region legs are still measured and published,
under the distinct reason `region_gate_forced` so a forced adoption can never be
read as one the comparison granted. Every other arm, and the standard ladder,
are untouched: `dispfloor0p12` and `parked0` still describe the ordinary lanes
exactly. *(Superseded at v0.52, immediately below: there is nothing left to
bypass — the floors and the flag are retired and the override IS the
reachability test.)*

**v0.52 amendment — OVERRIDE-ONLY, and the per-coding filter (PK-CLEAN).** The
paragraph above describes overrides that BYPASS things. Those things are gone:
A3's two dispersion floors and A4b's park flag are deleted, and with them the
last way either arm could engage from an ordinary lane. `arm_override` is now
the whole reachability test — `fit_region_stack` runs A3 iff the override is
`a3` and A4b iff it is `a4b` — so there is no constant, no flag and no
environment variable to flip, and a standard lane no longer even PAYS for an arm
it was always going to refuse (it fits no window maps at all; its evidence is
unchanged, one QDA pass cheaper). Pinned structurally with a spy on both fitters
on a fixture where both arms fire under their own overrides. A4b's un-forced
region-gate branch went with the park: since only a forced lane can reach the
arm, `region_gate_failed` became unreachable, and the comparison is measured and
published on every fit while the verdict is always `region_gate_forced`.

The supplemental tail is also PER-CODING (`cascade.uplift_arms_for_codec`):
A4b conditions a plane's marginal on its certified SIBLING planes, so a coding
with one payload stream has nothing to condition on and its `a4b` lane is a
guaranteed zero — measured at 98 blocks / 185 attempts, 0 certificates, not one
`color.conditioning.*` key, 70 s wall / 144 s CPU on xerox c3-cmy7 (§10.7). A
cmy7 plan therefore schedules `[U(Ln,off), U(Ln,a3)]` and a cmy8 plan all three.
An UNKNOWN colour codec keeps the full tail: narrowing a plan is a claim about a
codec, and the filter may only make it about codecs it knows. Plan shape moved,
so the scheduler id moved with it.

**v0.52 amendment — NO SWEEP HATCH IN A PRODUCTION PATH.** Every swept constant
the colour stack reads travels as one explicit `color_stack.StackConfig`
(A3's shrinkage prior, A4's saturation floor, A5's variant and floors), threaded
`ProductionColorPayload` -> `collect_color_evidence` -> `fit_region_stack`
exactly the way `arm_override` already is. The production runtime passes none, so
a production decode runs the constants the policy id names; only the campaign
harness passes one, from its own entry point, and the tiers with no configuration
seam (a full `run_receive` decode, the specimen runner) REFUSE a sweep flag rather
than accept one they would silently ignore. `HOLO_COLOR_STACK_FORCE_NULL` remains
and is the receiver's ONLY colour environment read: it is a contract, it can only
REMOVE behaviour, and it must reach code paths no configuration object touches.

*Force-null skips u-lanes entirely.* `--force-null` must mean "the pre-campaign
receiver, exactly". A supplemental lane exists only to run a campaign arm, so
with the arms off it has no reason to exist — and running it with them off would
not be a null but an extra committed-pose decode pass, with its own attempts,
blocks and cost, that the pre-campaign receiver never made. The hatch is read
first in the leaf and the lane commits the empty barrier without touching a
pixel. Pinned, with the suppression law itself, in
`tests/holo/test_color_uplift_lanes.py`.

**Tier-law amendment (measured, PK10).** For CONDITIONING-CLASS arms — anything
consuming prior-barrier certificates, whose first-order effect is that
certificates arrive EARLIER — a truncated lane set systematically OVERSTATES the
gain, because a short window scores re-timing as yield and cannot see the
compensation. Measured: a two-lane library unit read +19 on xerox c2-cmy8 and
the full twelve-lane replay reproduced that lane exactly and then finished at
net −5 (1 new address, 18 re-timings, 10 later losses). Only full-lane-set runs
are evidence of yield for such arms; the library still gates their iteration.

**Registered compromises.** (i) Per-window photometric gates re-use window held-out
labels that later inform the region-level arm comparison — bounded, one-sided,
monitored via the `color.stack.arms` diagnostic. (ii) Cert-cross strata are
selection-biased toward clean tiles (siblings certified because easy; deployment
targets are the hard remainder); the masked-furniture floor is the spatially unbiased
mitigation.

**Transitional form.** This stack is the transitional form of the planned
payload→raw-pixel channel-model loop: certified content projected through committed
geometry (the DONE-GEOMETRY construction) becomes the channel re-estimator's input, a
pixel-resolution view of the same KnownField. The KnownField carrier and the sampling
leaf are the stable contracts that rework keeps; the context stage sits behind a
neighborhood-corrector interface a model-based corrector may later replace; K migrates
only when that rework forces K changes.

**Identity and qualification.** Each decode-relevant packet lands one hand-bumped
`COLOR_PAYLOAD_POLICY_ID` token (as shipped:
cmy7cal-temp7-heldout-subsplit-satfloor30,
winphot-gainoffset-adaptivehalo-shrink20,
ctxmatrix-9bin-zeroanchor-sweeps3-floors80-20-40-10,
knownfield-conditioned-marginals-ulane-only,
union-lanes-a3-a4b-off-v4-zerofrontier-codingaware, cmy7-demapiter3.
The once-rostered stack-greedy-arms, winreg-const-shrink8 and
certfeed-window-cmy7-ctx were NEVER MINTED — the skeleton was a no-bump
byte-identical refactor, PK6 never ran, and PK7's substance was absorbed
without numerics of its own — removed from this roster at v0.54); prior
states of ALL codings refuse resume by design — the scheduler token is
coding-independent, so its bumps orphan pre-campaign K states too, not only
color (their plans are unchanged; re-run from capture; RECEIVE-DESIGN keeps
the hand-bump no-migration doctrine). The union token is decode-relevant
because the PLAN is: a state minted
under it schedules a different lane set than a `v8` or `v2` state did. The
scheduler's own id bumps with it
(`holo/phased-session/rung-major-v4-u-lanes-codingaware`).
A3's token carries its shrinkage prior (20 effective labels, the best on-grid point of
the nine-point sweep measured as the address delta on the uplift target's own first two
barriers, §5.2 of the campaign's measured record) and the fact that its halo is ADAPTIVE
rather than weighted (§6.3: own-window-only measured +27 on that same unit against the
frozen weight's +17). It carries NO region applicability floor, because there is none:
`dispfloor` and `normdisp` are retired (§12), measured non-separating from both
directions — refusing every harm lane needs > 31.1, keeping every help lane needs
≤ 2.09 — and the arm's reachability is a SCHEDULING fact the union token states.
A4b's `ulane-only` is that same fact spelled for the other arm, and it replaces
`parked0`: the arm is not parked, it contributes (+1 M on hp c3-cmy8, +2 on xerox
c2-cmy8, §10) from its own lane and nowhere else.
The cmy7 head's token carries BOTH of its adoption conditions: the held-out
furniture validation gate, and PK3.1's `satfloor30` — the head applies only where
the region's own deployment population saturates the L∞ bound at ≥30% pre-head,
because the furniture gate alone was measured adopting into a lane the head
strictly loses (§4.5.1 of the campaign's measured record).

**PK8/PK9 amendment (the CMY7 CODEC LEAF, measured, v0.53).** The soft-iteration
law's own instance now exists. `color_attempts.DEMAP_ITERATIONS` (3) is how many
times ONE attempt may re-demap the pack7 mapper from the frame decoder's extrinsic
before giving up; the loop stops at the CRC, lives entirely inside
`attempt_color_tile`, mints one attempt identity, spends the retry150 ledger once,
and lets no soft value out (`FrameDecodeOutcome.extrinsic_llrs` is dropped). It is
exact rather than approximate for two structural reasons: the pack7 codebook realizes
all 2,048 eleven-bit patterns, so a prior with no channel evidence factorizes and its
extrinsic is zero — an unobserved pack stays silent and the nonzero-LLR support gate
cannot be fooled — and the demapper subtracts the prior it was given, so nothing is
double counted. `n_iters` is the BP sum over every inner decode (§6.3). Two consequences
are REGISTERED, not hidden. (a) The per-attempt CRC exposure rises from one to at
most `DEMAP_ITERATIONS` — a 3x undetected-error budget on the same denominator,
carried on the registered-compromises ledger beside R6/R12 with no new bar, because
the wrong-certificate audit is its empirical guard (measured: zero in 61.2M certified
cells over six replays, and the final matrix re-measures it). (b) **`--force-null` REACHES THIS LEAF**,
so v0.51's "exactly the pre-campaign receiver" stays literally true: the budget comes
from `color_attempts.effective_demap_iterations()`, which returns 1 when
`color_stack.force_null_enabled()` is true. It asks `color_stack` rather than the
environment — one sanctioned reader for the one surviving contract, per PK-CLEAN's
hatch consolidation — and, like everything else force-null does, it only REMOVES
behaviour. **PK9's margin-gated pack erasure is a MEASURED NEGATIVE and is RETIRED**:
pack semantics are all-or-nothing, so erasing a low-margin slot costs eleven code bits
to save one cell, which B8 priced at −36 tiles at the bar point, and iteration re-reads
that slot from its ten siblings instead of discarding them (jointly, grid CRC 788 ->
651). `channel.state_score_margins` outlives it as a primitive.

Committed-pose payload REPLAYS are development signal only (for P9, a kill test);
FULL decodes are the only qualification numbers; the measured record accrues in
`docs/COLOR-UPLIFT-MEASUREMENTS.md` against the plan's pre-registered bars (zero wrong
certificates is the campaign-stopping hard bar).

### 6.3 Certification chain

`tiles.py` is scan- and pose-free. For one hypothesized tile it performs the
format-defined chain:

1. gather calibrated cell LLRs with positive meaning printed bit 1;
2. apply payload descramble by flipping LLR signs at absolute cells;
3. erase the format word/filler site cells (there are no separate metadata
   sites at erasure time — the metadata bit rides the framed user bits);
4. refuse below the informative-bit floor (pre-decode, before any slot
   arithmetic);
5. invert the per-tile affine slot permutation;
6. apply uniform information-tail shortening;
7. run the registered LDPC decoder profile; and
8. require both zero syndrome and CRC-32 before emitting a certificate.

The ordinary profile is the historical max-60, alpha-0.8 decoder. Every lane
then schedules the separate `retry150` profile before its retention barrier:
scheduling is mandatory, work is selective. The newest max-60 scan/union
baseline is selected first and is eligible only if it is itself
`attempted_failed`, the address remains uncertified, and its exact retry
identity is absent; a newer below-floor baseline blocks tunnelling back to an
older failure. One `(address, evidence digest, retry150 profile)` identity can
spend at most one CRC-bearing attempt; an unchanged frontier is an
authoritative no-op; a later capture may create a new evidence digest and
therefore a new eligible frontier. The spend-once and no-op rules are not
backed by a durable ledger: the attempt ledger is deliberately
invocation-local (recorded kiss ruling; durable state folds it to
counters), and on resume it is determinism — identical evidence re-derives
identical attempt identities and outcomes — that delivers the intent.

The durable attempt record stores measured total BP iterations, not the fixed
per-pass budget: format-bound replay derives that budget from stage and rate,
total work cannot exceed the two decoder passes, and a final false syndrome
means both passes exhausted exactly — cost accounting stays authoritative
without persisting a duplicate profile or maximum. **For CMY7 the bound is
the two passes times `color_attempts.effective_demap_iterations()` (v0.53):
one attempt
may run the frame decoder once per demap iteration and `n_iters` is the SUM
over all of them, which is what keeps the record an honest cost. The
exactness statement — a failed child spent exactly the budget — is a
consequence of the single-pass schedule and holds only at one iteration,
because a child can carry a clean syndrome under one a-priori vector and
fail under the next.** K and CMY8 read the historical bound unchanged.

There is no `--retry150` choice and no retry Boolean in request or discovery
state. `retry150` remains a distinct ledger stage, decoder profile, and
attempt identity so its calls, iterations, CRC exposure, and certificate gain
remain auditable; running max150 globally would erase that distinction and
waste work on ordinary successes. Conflicting certificates are fatal, never
voted or resolved by confidence.

Certificate identity is minted and validated once, at record construction,
by the records family (`records.stream_certificate_identity` /
`certificate_record_from_user_bits`); the exact printed field of an
accepted tile is re-encoded on demand — once per certificate, memoized
(v0.37 mint-once) — by `records.printed_cells_from_record` for later
certified pose refinement and divergence checks. `tiles.py` itself stays
the pure LLR-to-certificate chain above.

### 6.4 Stream-generic payload engine (v0.17 registered; v0.18 BUILT for color)

User ruling 2026-07-30 (KISS task 10): the payload transaction of §§6.1–6.3
becomes ONE per-tile/per-stream engine shared by every coding — K and CMY7
run it with the single stream `"main"`, CMY8 with the three presence-bit
streams `C`/`M`/`Y`. Everything downstream of detection is stream-generic
and exists exactly once: evidence blocks, one-owner freeze, bounded
calibration, gather → LDPC → syndrome+CRC → certificate
`(page, tile, stream)`, scan/union max-60 → selective per-lane retry-150,
divergence audit, close progress, fountain export. The DOWNSTREAM
`production_color`/`color_payload`/`color_attempts`/`color_divergence`
fork (~2.8k lines of duplicated schedule/records/close machinery)
collapses onto that engine. As built, the four files themselves were NOT
deleted — they survive re-roled (~1.8k lines) as the detection-side color
modules and thin leaves: registration/projection/QDA detection and
fitting strictly upstream of the detector contract, the color decode
callable, and the color divergence comparison kernel. Everything
downstream of the contract runs the one engine. (The one-owner freeze and
the frontier-to-block converter, which briefly existed twice, are one
implementation each since v0.37: `payload_model.freeze_page_owners` and
`evidence_blocks.blocks_from_owner_pages`, with per-codec thin wrappers.)

The branch point is the **detector contract**: a coding row supplies a
detector that, given the lane raster, owned payload cells, and pose-sampled
windows, returns **bounded per-stream LLR fields at owned payload cells plus
its calibration labels** (the LAYERS bounded-LLR invariant; raw detector
scores never cross the contract). K plugs in the established ctx+PAVA
detector; CMY8 plugs in the color detector emitting three presence-bit LLR
planes; CMY7 maps its 7-state detection to its stream packing. Registration,
projection, and reference-state estimation remain color-only stages strictly
UPSTREAM of the contract and invisible to the engine.

One event vocabulary: the engine emits `payload.attempt` /
`payload.retry_attempt` with integer `payload.tile_y`/`payload.tile_x` and a
`payload.stream` detail; the `payload.color.*` names and the string-encoded
`color.tile_yx` retire, as does the color-specific close-progress subclass
(close progress is stream-keyed generically). Policy identities are
hand-bumped; the format axis is untouched (records and `streamset` already
carry `stream_id`), and pre-freeze states from the forked path carry no
compatibility promise.

BUILD STATUS (v0.19, 2026-07-30): COMPLETE. `payload_engine.py` owns the
schedule for every codec; both leaves mint the ONE records family
through the ONE identity/minting functions
(`records.stream_certificate_identity` /
`certificate_record_from_user_bits`; K attempt ids unchanged by
construction, K certificate ids re-domained — pre-existing dev states
refuse on the v8 policy id, no compatibility path). Both codecs run the
ONE shared `payload_engine.RecordingLeaf` over the stream-aware
`records.CertificateStore` — K plugs in `payload.attempt_k_tile` as its
decode callable, color its `color_attempts` decode
(`production._KPayloadLeaf` is gone); the old two-call K schedule,
`TileAttemptResult`, `tiles.TileCertificate`, and every conversion
adapter are deleted. ONE close-input shape (`CertifiedStreamSymbol`,
stream "main" for K/CMY7 — the metadata channel consumes only the
certified counter and bit, per its contract) and ONE divergence pairing
loop (`records.certificate_divergence`) with per-codec comparison
kernels (K printed-field re-encode inline;
`color_divergence.color_divergence_counts` as the color leaf —
since v0.40 `color_divergence.py` exports exactly that kernel and
nothing else, and the barrier's replay of durable divergence counters
consumes the same kernel directly inside `session.py`'s validation
loop).
`printed_cells_from_record` derives the printed field on demand for
divergence and certified refinement, which consume durable records
directly.

Acceptance (pre-registered, gates landed 2026-07-30 as
`tests/holo/test_backbone_payload_gates.py`): (i) the full seven-coding
real-payload net green before and after; (ii) K rows byte-identical in
certificates and recovered payload (state digests may move with policy
ids); (iii) color per-stream certificate counts not below the forked
baseline on the same fixtures; (iv) the diag viewer consumes one
vocabulary with no color branch. Two measured limits recorded with the
gates stay OUT of this engine's scope: open-domain cold-search cost and
the ~70–75% clean-composite placement coverage — both belong to the parked
top-down placement/scheduler work.

## 7. E023c scale-space and certified refinement

`scale_space.py` produces every lane directly from the authenticated native
raster using exact area semantics; views are never recursively resized.
Coordinate transforms preserve half-pixel meaning. The scheduler chooses a
sparse coarse-to-native footing ladder from native pixels per printed cell.

At each barrier:

- typed stage products and evidence are committed atomically;
- conflict-free CRC certificates join the global authoritative portfolio;
- lower-scale accepted and losing pose hypotheses become bounded proposals;
- the NeedMap removes globally certified addresses from finer LDPC work; and
- LLRs never cross between correlated scale lanes.

`certified_cascade.py` and `certified_refine.py` implement the E023c
certificate-labelled forward refinement. Discrete page, tile origin, and
orientation are frozen; replay rejects any orientation outside the canonical
four `rot90` values instead of normalizing it. The fit uses current-lane pilot
labels plus exact printed cells reconstructed from prior certificates;
adoption requires improvement on held-out evidence without pilot regression,
otherwise the original placement remains. A certificate is an external label
for refinement, never permission to revise the certified bits themselves.

Since v0.40 this section is codec-complete: color lanes run the analogous
forward arm (`color_refine.py`; COLOR-INTEGRATION-DESIGN §5.5), superseding
the v0.38-recorded absence (finding color-payload:11). The color fit labels
are certificate-reconstructed per-plane presence bits (mint-once
projection) with word/dust furniture as the pilot analog; adoption requires
held-out improvement through a per-plane calibration frozen from the
baseline pose, without furniture-logloss regression, on the same shared
candidate grid and diagonal-stripe holdout. Color refined reuse is
region-granularity — the color detector fit is region-scoped — under the
same forced-full byte-equality contract.

Refinement reuse is numerical identity, not an approximation. Generation-zero
window evidence remains the exact source for every unchanged region and every
unchanged window in an affected region; an adopted pose patch resamples only
the windows whose sampling transform changed, and a changed integer crop or
filter signature recomputes the whole affected region conservatively.
Regional context is then rerun for affected evidence and the global one-owner
freeze is rerun as before. Differential tests compare the optimized path with
a forced full recomputation through `CaptureEvidence`, dependency blocks,
attempts, certificates, divergences, and the canonical barrier delta; any
byte difference is a failure.

The live observer does not expose a half-replaced refinement generation:
generation-zero payload coverage remains visible while affected
generation-one regions are recomputed, and `payload.owner_frozen` atomically
replaces it with the complete refined ownership result — a display rule that
is observer-only and suppresses no numerical work or events.

Losing hypotheses are retained because a finer lane may distinguish a close
runner; they are data, not an unbounded search history. No E024 backward
fixed-point or arbitrary revision loop is included: the experiments measured
negligible benefit at substantial cost, and Track 3 preserves the state seams
needed for a separately designed future pass.

## 8. Runtime, state, and replay

`runtime.py` is the sole ingestion harness. `session.py`, `session_model.py`,
`state_codec.py`, `session_validation.py`, `records.py`, and
`_runtime_validation.py` own durable state and its validation.

The default CLI entry is discovery-first. `format/registry.py` supplies the
frozen complete-row domain. `discovery_state.py` persists only the discovery
policy id, requested rows, cross-row placement-domain envelope, authenticated
capture facts plus the native E021 `c` decision, and isolated exact-row
`SessionState` branches; candidate ids come from those branches, and
per-candidate completion, c-based exclusion, the selected row, root status,
and decoder count are derived directly — no parallel prune, trial, or
selection ledger. E021 `c` votes only exclude incompatible cell families;
each surviving row runs the unchanged E022→E023 branch under the global
hypothesis envelope. Exactly one row with a CRC tile certificate is
provisionally selected; a certificate from any other row is a terminal format
conflict, and a second row certificate stops nested work at that exact
committed barrier. Root verification waits until every candidate/acquisition
pair in the current round is derivably complete or c-excluded; a deliberately
interrupted, partially active exact-row call is not complete. Native
discovery facts and every branch ingest are SHA-bound to the same bytes;
resume reauthenticates those facts instead of rerunning E021, and every
ACTIVE branch capture must be present in a resume request (since v0.33
multiple captures are legally ACTIVE; the phased driver advances them
rung-major within each branch). Per-scale E023c lanes
still execute their own E021 survey, including the native lane, so discovery
retains only the native `c` decision used to exclude incompatible rows rather
than duplicating exact-row E021 products. The root exposes the receiver-wide
count of all actual CRC decoder invocations. `--coding` remains an optional
exact-row narrowing/debugging path.

Binding rules:

- the authenticated source SHA-256 is the sole acquisition identity; there is
  no operator-declared capture id or evidence-group id;
- externally decimated, resized, cropped, rotated, contrast-adjusted, or
  otherwise derived rasters are not receiver inputs; Holo derives every scale
  view directly from the authenticated native acquisition;
- an actual physical rescan normally has different bytes and is therefore a
  new same-lane acquisition component; the acquisition protocol should
  reposition the specimen between useful repeat scans;
- byte-different re-encodings or transforms of one acquisition are not made
  independent by their hashes; excluding them is an explicit operator/input
  trust boundary rather than an image-equivalence classifier;
- raster source bytes, dtype, shape, channels, and true DPI are bound at ingest
  and the source is re-authenticated before every retention barrier. The
  per-barrier detector is stat-based with cryptographic escalation (v0.37):
  ingest retains the verified source stat tuple (dev, ino, size, mtime_ns);
  a barrier whose fresh fstat exactly matches the retained tuple is a memo
  hit and skips the byte re-stream, while ANY observable difference
  escalates to the full encoded-byte re-stream and SHA-256 comparison, the
  memo refreshing only after a passing full check. Threat model on record:
  accidental mutation (overwrite, truncation, re-scan onto the same path),
  not an adversary — a deliberate rewrite that forges size and mtime_ns
  onto the same dev/ino defeats the stat probe, and a mutate-then-revert
  between barriers was never detected by the full re-stream either
  (PAYLOAD-IMPROVEMENTS 7.2); the re-authentication law itself — one check
  per retention barrier — stands unweakened;
- in-memory arrays are detached; file-backed TIFFs use native-dtype mmap when
  possible; consumers request bounded raw float32 luma crops;
- a scale plan and level history are append-only prefixes;
- every barrier retains the causal artifact prefix produced before its
  terminal refusal, or all three artifacts on completion, and validates all
  new references/conflicts incrementally;
- generic loading checks schema and performs structural validation plus close
  reproduction — never a causal barrier replay (kiss-5 ruling): the load
  validates the retained state's structure and reproduces its close record
  from the certified frontier (a `--complete` invocation defers that
  numerical fountain reproduction to its one final close phase, §8.1); once
  the exact row is known, load/entry also reconstructs and validates scale policy,
  page/counter law, payload-site legality, BP policy/cost, and certificate
  identity. `run_receive` then rejects a semantic-policy or exact page-domain
  mismatch; the authenticated source SHA is bound, but no source-code/module
  fingerprint exists;
- page-domain records are explicit and cannot be silently reinterpreted;
- an exact source with matching immutable facts resumes its unfinished scale
  prefix while the session is open. A terminal session is never reopened by
  `--complete`; a fully exhausted source remains a no-op, and conflicting
  immutable facts refuse;
- since v0.33 any number of captures may be ACTIVE while the session is
  open; a resume request must include every ACTIVE capture (supersets are
  fine), and new captures may join at any barrier boundary — the phased
  driver advances all of them rung-major by target ppc, then runs the
  priced mop-up tail, then (v0.42) the refinement levels; the
  invocation-only `--mopup`/`--refine` flags bound how far the drive may
  proceed this invocation (default: the ordinary ladder only), committed
  prefixes are always honored, and a session that never runs the flags
  legally retains ACTIVE captures;
- atomic save is temp-write, fsync, replace, and directory fsync where
  supported; and
- session terminal states are open, verified, integrity failure, or
  unsupported. All three terminal states are immutable. `--complete` keeps
  the state open until its one final close rather than extending any terminal
  frontier.

State retains compact support, accepted poses, typed BCH conflict quarantine
records, bounded pose proposals, losing hypotheses, parked-window records
(compact window/fitted-pose/route facts for the mop-up tail — no pixels, no
sampled evidence; v0.33), compact observed
payload-cell evidence blocks, certificates (including their
packed metadata bit), folded work counters (`SessionCounters`: per-stage
attempt tallies plus divergence and dropped-disagreement counts — attempt
and divergence records are invocation-transient and fold to those counters
at commit, never persisted; requirement 5), and the close record. A
certificate's counter derives from its retained page/tile and the active
format row. State does not retain whole float rasters, source-code identity,
arbitrary diagnostic images, raw address-site observations, detailed
address-window audit, context decisions, separate metadata observations, all
matching/refused word outcomes, raw BCH vote history, or duplicated derived
views. Stage disposition is derived from the causal artifact prefix;
checkpoint counters/profile labels and finding prose are operational
presentation, not persisted authority.

Persisted state follows authority rather than presentation convenience:
`LevelRecord.status` and its operational stage/disposition view derive from
the survey/address/payload artifact prefix; `CaptureRecord.status` and the
next lane derive from the complete scale plan and number of retained levels;
`SessionState.status` derives from the close record; level ordinal, lane,
scale, source identity, dtype, and shape come from the owning capture and
plan rather than being copied into every level; discovery completion,
selection, and status are derived as described above. The current strict
schemas are receiver 24 and discovery 10; no migration or compatibility
decoder is maintained.

The same authority rule applies during execution: a scheduler receives the
existing capture prefix and a runtime-owned barrier callback and returns no
value — the runtime, not the scheduler, owns the candidate state, close
check, persistence, accepted barrier count, and per-invocation
`state_changed` result. Since v0.33 the runtime's session phase driver owns
cross-capture iteration — rung-major by target ppc, then the priced mop-up
tail, then (v0.42) the refinement levels, all M-levels before any R-level
session-wide — with the phase cursor derived from per-capture prefix
lengths, never stored, and the invocation's reach bounded by the
`--mopup`/`--refine` flags (scale plans are
`[L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln)]` since v0.42).

The plan itself is a prefix in the same sense (v0.58). A capture recorded
before a lane family joined `cascade.scale_plan` carries a plan that is a
strict PREFIX of the plan its format row schedules today; that is a capture
with work still owed, not a corrupt record, so `validate_state_for_spec`
accepts it and refuses — naming the first offending lane — only when a
stored entry DIFFERS (the standard ladder moved, so the retained levels no
longer correspond to the lanes that produced them) or the stored plan is
LONGER than today's (a lane retired under a live state). Because
`CaptureRecord.status` and the next lane derive from the complete plan, the
runtime ADOPTS today's plan into each retained capture at load, levels
untouched: the cursor is still the retained prefix length, so the capture
resumes into exactly the appended lanes under the ordinary flag bound.
Adoption is flag-free and writes nothing — the on-disk record changes only
when a barrier legitimately rewrites that capture. Plan compatibility is
independent of `receiver_policy_id` compatibility, which is a separate gate
with its own rule (§9c, the id half — it runs immediately after this one,
at the same load-time point and for the same reason).

Some non-authoritative machinery intentionally remains: `SessionIndex` and
placement/reference/tile indexes are transient, reproducible accelerators for
validation and frontier lookup, and bounded diagnostic caches provide atomic
observer snapshots without entering receiver state — they remove measured
repeated work while adding no alternate evidence, selection, completion, or
persistence authority.

### 8.1 Invocation-only deferred close

Normal reception runs the close at retained lane barriers under the v0.33
count gate. Clause precedence first: any metadata-terminal state
(inconsistent, unsupported, malformed) consults IMMEDIATELY, at any rank,
count, or gate state — terminal states always materialize. Otherwise the
fountain is consulted only when metadata is trusted, every (stream,
block)'s distinct certified ESIs reach K_b, and — after a want_more attempt
in this invocation — every then-rank-short (stream, block) has gained at
least its then-reported shortfall in distinct ESIs since that attempt.
There is no surplus buffer: rank gain is bounded by distinct-ESI gain, so
every skipped attempt provably could not verify, no verify is ever delayed
or forfeited, and every ordinary open record remains numerically open —
which is exactly what this section's load-reproduction contract below
requires. The re-attempt baseline is invocation-transient by design; after
a resume the gate degrades to the count gate alone (one conservative
consult), never to a skip. The first complete metadata/fountain solve whose
canonical envelope and SHA-256 check produce `verified` is the successful
stop.

`holo decode --complete` governs EXACTLY ONE thing (v0.42 correction of the
v0.33 "full plan / exhaustive harvest" wording, which wrongly implied the
lane families): it defers every fountain check and solve until the work
THIS invocation runs is exhausted — every requested capture has committed
its flag-bounded plan prefix (default: the ordinary ladder; with
`--mopup`: through the M-levels; with `--refine`: the whole plan) — and
then closes once. It does NOT imply `--mopup` or `--refine` and creates no
lane; a `--complete` run without the lane flags legally ends OPEN with
parked lane families and is resumable. Intermediate barriers are still
validated, source-authenticated,
persisted atomically, and exposed to the next lane, but their session close
remains `open`; after the invocation's final requested barrier, one
exact-row session
invokes the installed close processor exactly once over its final certificate
frontier and persists that result, and receiver-wide discovery performs that
one final check only for its uniquely recognized branch — once every
candidate/acquisition pair is c-excluded, terminal, or has committed its
flag-bounded prefix — never once per
candidate row or capture-shaped child call. This includes the K and color advisory
precloses: because they call the fountain implementation, both are suppressed
during a `--complete` run. The v0.33 count gate lives in the close
processor, so it also runs at the one deferred final consult and at
terminal replays; that is exactly the shipped behavior (v0.36): a
count-short final frontier is legally count-gate-skipped (it provably
cannot verify — the skip returns the retained close record unchanged) and
its published progress is the count-only shape, while a terminal replay
always consults (metadata-terminal precedence) and reproduces the retained
record. No separate complete-mode BP, retry, placement,
payload, certificate, NeedMap, or diagnostic rule replaces it; any work an
ordinary advisory terminal close would have avoided is merely the direct
consequence of not asking the fountain question early.

The flag is invocation-only, absent from the semantic pipeline policy and
receiver/discovery schemas, creates no lane, and changes no numerical gate.
An interrupted complete run retains an ordinary `open` barrier prefix and is
resumable; if every requested barrier was already retained before the
interruption, resume still performs the one deferred final close. A state
already terminal before the invocation is never reopened or extended:
verified, integrity-failure, and unsupported states retain their exact close
record and perform one immutable reproduction at the final phase.

Validated loading, discovery-state hashing, and discovery-state saves preserve
the same invocation boundary. Ordinary validation reproduces the close
processor and therefore requires an `open` record to remain numerically open;
only a `--complete` invocation may structurally validate any frontier without
asking the fountain during load, hashing, or save. Open-but-solvable is the
legal state throughout deferred reception and across a crash between the final
retained barrier and the deferred close. At the common final phase, an exact
session or uniquely selected discovery branch performs one close: a completed
open frontier may apply its final result; a retained terminal close is only
reproduced and compared, never reopened or changed; a verified replay must
also reproduce its payload bytes. An unrecognized or receiver-wide-conflicted
discovery root has no selected interpretation to solve and performs no
fountain call. No persisted marker or schema axis is introduced. Automatic
discovery obeys the same boundary across its internal child calls and must
not accidentally close once per capture-shaped call: candidate branches
finish their requested acquisition work first, then only the uniquely
recognized branch is checked once on its final frontier. A certificate from a
second row remains an integrity-fatal format conflict independent of fountain
scheduling; having no selected interpretation, it is structurally validated
but not fountain-solved.

### 8.2 Certified work boundary

Certification is terminal for one logical payload work key
`(page, tile_y, tile_x, stream)`. LDPC evidence and belief propagation are
tile-local: a certified payload does not improve a neighbouring tile's parity
equations, and the receiver must never construct or decode another attempt for
that terminal work key. In a multi-stream row, only the certified component is
terminal until every required stream is certified.

The current exact, result-preserving boundary is:

- test terminal work before materializing a dense `TileAttemptView`;
- omit terminal addresses from scan/union grouping;
- retain only unresolved compact evidence at the barrier;
- audit certificate/evidence divergence once, then compare only certificates
  newly minted by a later retry; and
- render a durable certificate as an immutable green payload state rather than
  replaying transient work over it.

This boundary does **not** imply that every pixel belonging to a certified
tile can be discarded before placement: raw scan space has no page/tile
identity; after a window is mapped, certified printed cargo can still be a
pose label for that window, and a window spanning certified and unresolved
tiles can improve unresolved cells; current marginal normalization uses every
sampled cell in its window; and the registered context arm fits known
pilot/filler observations across a region with a one-cell neighbourhood
around each corrected site. These are geometry/photometry dependencies, not
cross-tile LDPC dependencies.

A deeper NeedMap cut is therefore applied only after correspondence and must
preserve a deterministic **active window cone**:

1. every window which can own an unresolved payload cell;
2. every competing overlap needed to choose that owner;
3. the exact sampled cells used by that active window's frozen marginal
   normalization;
4. its known pilot/filler calibration sites and one-cell context halo; and
5. bounded certified-cargo labels inside the active window when they are
   eligible for pose refinement.

A mapped region whose payload footprint intersects no unresolved work is
payload-inert: it leaves the placement/address fact needed to account for the
scrap but produces no payload raster sampling, context fit, certified pose
refinement, region-progress animation, evidence block, decoder view, attempt,
or divergence work. The **pool law** (v0.35) states the mixed-region cut
once, window-granularly:

- **L1** A wholly terminal region is dropped before image work (unchanged).
- **L2** Inside a mixed region, a window whose payload cells all lie on
  certified tiles does NO payload work — no owner rows, no evidence blocks,
  no attempts — but becomes a **label row**: it is sampled and calibrated
  through the D7 label channel (full-window for K, whose context fit needs
  the payload neighbourhoods present; furniture-site rows for color, whose
  QDA fit is per-cell) and its format-known word/filler (word/dust) sites
  join the region fit exactly as they did in the pooled single pass.
- **L3** Label rows are never terminal-gated, in any path — generation zero,
  refined reuse, certified-refinement replay, and M-levels alike.
- **L4** A zero-payload (all-reference) window is label-only ALWAYS,
  independent of any certificate's existence.
- **L5** The region pitch/filter-signature pool is placements ∪ all label
  rows — identical in every path; the refined-reuse and replay paths pool
  the full generation-zero population instead of deleting reconciled
  windows, so a pool-membership flip between passes is structurally
  impossible.
- **L6** The same law governs K, CMY7, and CMY8; CMY8 judges "all
  certified" at work-key granularity (page, tile, stream) — a window is
  label-only when every stream of every covered tile is certified, and
  partial tiles keep attempting only their uncertified streams.

Label rows never enter returned payload evidence, never own cells, and never
mint observations, origin rows, or attempts — the window-granular cut's
ownership/block/attempt savings stand; only the calibration/context
contribution the pre-law skip erased is restored.

After that early cut, K still removes any terminal owner rows at the final
owner boundary as a fail-safe (unresolved blocks byte-identical to the
unpruned oracle); color applies the same law (stage 1b): certified-complete
color windows and D7 label placements join the region QDA/PAVA fit and
pitch pool as furniture-site label rows and never reach the returned
windows, owned pages, blocks, or attempts, while registration anchoring
stays on payload rows (sparse label sites carry no complete 3×3 in-row
neighbourhood to measure). Stale prior-capture terminal blocks are excluded from the
working frontier, evidence origins are constructed once per window rather
than once per cell, and block construction streams one tile-sized group at a
time. None of these cuts changes `--complete`, survey/placement search,
calibration support for an active neighbour, LDPC evidence, or recovered
bytes.

## 9. Metadata and verified close

Each CRC certificate supplies one `(counter, metadata_bit)` equation.
`format/metadata.py` owns both the counter-addressed LFSR row and GF(2)
recovery. The receiver requires rank 24 and at least 48 distinct counters;
opposite duplicates or an inconsistent dependency are terminal integrity
failures. Unsupported but structurally valid metadata versions retain their
certificates and stop as `unsupported`.

For version 0, `fountain_close.py` uses ESI=counter and performs exact
per-block fountain-v2 accounting and solve. A global symbol count cannot close
a volume. The recovered stream must contain a canonical envelope, match its
declared SHA-256, use the unique minimal K implied by the payload length, and
contain only zero source padding. Only then does the runtime publish payload
bytes and enter `verified`.

### 9a. Close policy modes: greedy, --complete, --no-close (v0.56)

Ruled 2026-08-19 (rebuilt by derivation after the condemned c4-row
version): three close policies, one axis.

- **default (greedy)**: close attempts run per barrier; the first
  verifying close terminates.
- **--complete**: non-greedy ONLY — no close is attempted until every
  requested capture has committed its bounded plan prefix; then one
  deferred close runs (or a terminal record replays).  That deferral is
  --complete's entire function.
- **--no-close**: the close layer is never entered.  No closing record
  is read on replay (deferred fountain validation), none is attempted,
  none is written; the session ends OPEN with certificates accumulated.
  A TERMINAL state loaded under --no-close is **detached**
  (``session.detach_close``, the deliberate inverse of ``apply_close``):
  the close record is removed, the state reopens, and new captures
  ingest.  Detach is lossless — a close is a pure derivation from the
  certificate set, and the later closing run recomputes it (byte-exact
  when the certificates still solve).  --no-close implies the
  non-greedy deferral, so --complete alongside is legal and redundant;
  ``finalize_deferred_close=False`` without deferral is incoherent and
  refused at ``run_receive``.

The state x mode matrix (absent/OPEN/terminal x default/--complete/
--no-close) is pinned in ``tests/holo/test_no_close.py``, including the
e033 sheet-I workflow: accumulate rung scans under --no-close, add a
late capture to a detached terminal state, close once at the end.

### 9b. Per-plane registration fields (PLANE-FIELDS, v0.57)

Governing detail doc: **docs/PLANE-FIELDS.md** (v0.10 — charter,
dialogue record, build record, W6 qualification, owed list). The
receiver-axis summary:

- A per-plane translation-delta VECTOR field over tile space
  (`receive/plane_fields.py` core, `receive/color_field.py`
  production builder): evidence = the registration anchors
  (word/dust/certificate buckets, formerly discarded) + a bounded
  certified-tile probe pass; smoothed with shrinkage toward the
  plane-common field; applied at the colour readout seam as a
  per-cell local affine composed onto the committed pose, behind
  per-region/per-plane adoption margins.
- **Dial DEFAULT OFF, null-proved**: the stock decode is bit-identical
  to the pre-field receiver (pinned by certificate digest + close sha).
  No CLI flag yet; the only stock-CLI activation is the `uF`
  supplemental arm (below), so **--refine is required for any field
  activity**.
- **`uF` supplemental colour arm** (`UPLIFT_ARM_FIELD`): last in the
  u-lane tail, forces the field on for its own collection over the
  unresolved residue, certificate-gated, monotone. Its registration
  **bumped the scheduler policy id** and lengthened the colour plan.
  Neither is a refusal any more: the plan is an accepted prefix
  (v0.58, §8) and the moved scheduler segment detaches (v0.59, §9c),
  so an archived colour state resumes into the appended `u0x-field`
  lane under `--refine` — which is what made this arm reachable on
  real archived captures at all.
- Measured (sheet I, 3×2400, dial ON in ordinary lanes): +252
  certificates (Y 1444→1629), close byte-exact; the pre-registered
  dead-band bar FAILED (24/53 vs ≤5/53) with causes isolated —
  per-page adoption misfit (band-3 regression) and zero-evidence
  extrapolation limits. Consequently the default stays OFF until
  per-block adoption lands and a same-tree strict-superset proof
  passes (PLANE-FIELDS §6.5 sequencing).
- Observability: `plane_fields.*` Details + the `payload.plane_fields`
  snapshot event, the FieldStats observer + CLI epilogue, and the
  conditional fifth diag pane (bottom band, three-colour quiver) that
  renders only once a snapshot exists — dial-off frames stay
  byte-identical.

### 9c. Policy detach: continuing an archived state (v0.59)

Ruled 2026-08-23. The **id half** of archive compatibility, whose plan
half is §8's prefix rule. A state minted under an older receiver policy
no longer refuses: it CONTINUES under today's policy, by derivation.

The receiver policy id is a readable five-component composition
(`survey`, `address`, `payload`, `scheduler`, `close` — the "no hash"
ruling, G2), and `runtime_model.parse_pipeline_policy_id` is its exact
inverse. A differing id is therefore never opaquely foreign: exactly
which semantic components moved is legible, and each durable ledger in
`session_model.SessionState` belongs to exactly one of them.
`_runtime_validation.policy_detach` (the sibling of §9a's
`session.detach_close`, and the neighbour of §8's plan adoption — same
load-time point, before `started`, so a run that drives no barrier
still writes nothing) derives the continuation:

| ledger | detach | why |
| --- | --- | --- |
| `certificates` | KEEP always | CRC+LDPC-verified against the FORMAT and re-validated against the format row at every load — gate-verified truth, not a policy opinion. This is what makes a detached resume monotone. |
| `captures` | KEEP always | authenticated source facts, the plan (already rebound by §8; rung correspondence by ppc, never ordinal) and the retained level prefix. |
| `regions`, `poses` | KEEP unless their segment moved | a region is the survey's support mask; a pose is a placement the BCH address words VALIDATED. Physical facts — and the referents every retained level artifact names. |
| `proposals`, `losers`, `parked` | DROP when `address` moved | search state scored and priced by the old address policy (retained rivals; parked `attempted_routes`). Dropping forfeits future yield, never a certificate; the retained address artifacts stop naming them. |
| `blocks` | DROP when `payload` moved | float32 LLRs/state scores minted by the old detector+calibration+demapper; summing them with today's is exactly the cross-policy mixing the id exists to prevent. |
| `close` | KEEP | a pure derivation from the certificate set, re-reproduced numerically at load; `--no-close` detaches it as today, and the two detaches compose. |
| `counters` | KEEP | monotone work tallies (advice, never a gate); they now span epochs, which is what the lineage records. |
| BCH quarantine (inside the retained address artifacts) | KEEP | "when in doubt, drop" governs derived YIELD; a quarantine is a REFUSAL minted from contradictory decoded words, and dropping one would widen the accepted set. |

The previous id is appended to `SessionState.policy_lineage` (state
schema 26; oldest first, no wall clock — the list order IS the sequence
and `receiver_policy_id` is the current epoch). The divergence audit and
every counter apply per policy epoch. One `PolicyDetachWarning` line
goes to stderr and one `session.policy_detach` event carries both full
ids, the moved segments, and the kept/dropped census.

**Still refused**, and named: a moved `survey` segment (regions are its
product, every retained level names them through its survey artifact,
and poses reference them — there is no keep-the-levels detach; the
answer when that day comes is a full re-derivation detach that drops the
level histories too and keeps the certificates), and an id that is not a
kiss-v1 five-component composition (hashed, truncated or foreign — a
detach that cannot classify the change cannot be safe). The refusals
ahead of it are unchanged: a differing format row or page domain, a
stored plan that is not a prefix of today's, and any state whose
structure does not validate. Out of scope by intent: a DISCOVERY state
(`discovery.py`, its own composed root identity) still refuses on a
policy change — it is a short-lived format-identification artifact, not
an archive; its branches lift schemas, nothing more.

The granularity is the SEGMENT, deliberately. A payload id says that
something in the payload composition moved, not which leaf, so the
evidence pools go even when only the arm SCHEDULE changed — measured on
the PK-FINAL cmy8 state that costs 6,098 pending blocks, and the `uF`
tail then works from its own collection. Splitting the payload identity
into numerical leaves vs arm schedule would keep the pools across a
schedule-only change; it is the obvious next refinement, and it is a
refinement of the ID, never of the detach.

There is deliberately **no flag**: the behaviour is ruled, and a
refusing escape hatch would only be a way to keep the orphaning bug.
Older state schemas load through one additive migration table
(`session.STATE_MIGRATIONS`, `state_codec._migrated`): a step supplies
the keys a later field set added, at their declared defaults, and never
rewrites a stored value — the archive is the reason this gate was
unlocked, so a state-shape change that orphaned it would defeat its own
purpose. A file is rewritten at the current schema only by the first
barrier that legitimately saves it.

## 10. Diagnostics

`holo decode --diag` is the operational inspection surface for the whole
E021→E023c transaction, not merely a terminal tile-count report. It has three
strictly downstream layers:

1. an invocation-local scalar event log and cheap current-status snapshot;
2. typed, detached stage snapshots from which the current causal four-pane
   view is rendered; and
3. a deterministic final report rebuilt from committed receiver state.

Diagnostics are disposable observer output, not a second resumable state
machine. Live PNG/status/HTML and the optional loopback viewer are transports
over detached event values; the final JSON/HTML/SVG report is a separate
projection of already committed state. Neither path is a receiver dependency
or success condition, and a later invocation does not restore transient
diagnostic history. The live path has a bounded operator contract: an event
may append one compact scalar row, apply one detached delta, update
fixed-size status, and—only when the refresh interval permits—render the
current selected page; it must never construct or serialize the
multi-megabyte audit projection. Bulk detail is unavailable through the
loopback server while reception is active and is materialized once at
finalization for post-run audit/LLM use.

The diagnostic CLI surface is deliberately small: `--diag` enables
diagnostics, `--diag-dir` chooses the output directory, explicit `--diag-port`
enables the loopback viewer (`0` requests an ephemeral port),
`--diag-interval` controls only expensive refresh cadence, and
`--diag-panel-width` controls presentation. Supplying a tuning option without
`--diag` is refused, and there is no PAVA/detector selector. The resolved
diagnostic directory must be disjoint from the authoritative state file, its
evidence-blob directory, and the recovered-payload output path: equality or
ancestor/descendant overlap is a configuration error rather than an observer
degradation.

### 10.1 Typed, lazy, detached observation

Every runtime event has a small causal envelope: run-local sequence, event
name and stage, capture id (the authenticated source SHA-256), message/details,
transient or committed authority, the currently bound authoritative state
digest, and the accumulated session, capture, lane, scale, page-domain, and
qualification context. `events.jsonl` adds only its operational format schema
and the current invocation's contiguous sequence. It is truncated for a new
diagnostic invocation and is never reconciled with receiver state. Scalar
events remain useful even when no image renderer is installed. The current
structured detail projection is schema 5; the bump records removal of
source/group presentation fields and carries no receiver-state compatibility
meaning.

Fine stage snapshots are immutable typed observer values, never borrowed
receiver objects or mutable dictionaries. The required snapshot families are:

- survey: raster-preview identity, raster facts, pitch/cell-size result, and
  compact region support;
- address window: queue/anchor counts, native bounds, fitted affine pose and
  phase, attempted routes, current candidate/scores, and terminal outcome;
- address final: accepted poses, unresolved attempts, proposals/losers,
  site coverage, and known-position word outcomes;
- context/refinement: eligibility, held-out decision, adopted pose, reason,
  and certificate dependencies;
- payload ownership: geometric, emitted, and informative coverage kept
  distinct, plus refused windows and attempt-ready tiles;
- tile attempt: the latest completed attempt and its exact evidence/decoder
  metrics; and
- close: the durable metadata/final-verification summary and, while the
  numerical close result is still present, optional per-block fountain
  rank/shortfall progress.

The max60→retry150 boundary is a forced diagnostic milestone.
`payload.retry_complete` is emitted once for every payload lane, including an
empty or already-tried frontier; its scalar summary distinguishes max60
attempts/calls/iterations/certificates from the retry frontier, eligible
count, actual retry150 attempts/calls/iterations/certificates, and no-op
result. Actual retries additionally emit `payload.retry_attempt`, whose
detached attempt snapshot retains stage `retry150`, max-150 profile, evidence
digest, contributors, iterations, syndrome, CRC, and certificate identity.
Live status and the final report derive per-stage metrics for `scan`, `union`,
and `retry150` from these ledger rows rather than persisting another
authoritative counter.

Snapshot construction is lazy. With no diagnostic consumer installed, the
runtime builds no raster previews, per-window snapshots, pane data, or
attempt render state. With diagnostics enabled, the numerical stage detaches a
compact observer copy only after the corresponding evaluation barrier and
never passes whole rasters, `AddressResult`, decoder stores, session state, or
other authority-bearing objects to the observer. Diagnostic images and
snapshot state are not retained in `SessionState` and are not part of pipeline
policy or the authoritative digest.

The in-memory committed diagnostic view uses one full detached bootstrap at
`session.open`. Each successful retention barrier thereafter publishes a
compact delta bound to the previous authoritative digest and checked against
exact post-barrier ledger counts: append-only ledgers are extended, evidence
blocks are exact-key upserted or removed for newly certified addresses, the
durable close summary is replaced, and each barrier carries one
capture-id-checked scale-ladder upsert rather than every prior capture plan.
`session.complete` publishes a ledger-free terminal summary, including the
complete capture ladders, without copying the
attempt/evidence/proposal/loser ledgers again.

Close progress follows the same rule rather than being precomputed as a side
effect of closing. The numerical close returns its durable `CloseRecord` and a
lazy, non-authoritative `CloseProgress` factory called only from the
fine-snapshot builder, after the close result exists, inside the observer
exception boundary. Headless receive never constructs block-progress rows,
and a broken progress factory can lose only that optional snapshot — never
the close record, payload, barrier, or scalar event. Numerical close computes
its metadata facts once; one memoized close snapshot copies them and is
shared by `close.check` and the following barrier, so live diagnostics
neither decode the observations again nor build block progress twice. A cold
bootstrap may independently decode the compact retained certificates'
counter/metadata bits because the numerical result is then no longer present.

At an intermediate `--complete` barrier there is deliberately no numerical
close result. Fine diagnostics may still recover metadata K and count distinct
legal ESI symbols per stream and fountain block from the certified frontier;
that projection instantiates no fountain decoder, builds no generator rows,
computes no rank, and performs no solve — rank and solved state are explicitly
reported as deferred. The invocation's sole final close supplies the actual
rank/solve snapshot shared by `close.check` and `session.complete`. Count-only
status is diagnostic projection, never an additional close.

Observer adapters share that boundary. Formatting, callback-state building,
and scalar/fine publication run through a runtime-owned isolation guard: an
adapter exception is recorded and disables the observer without escaping into
E021/E022/E023b/E023c, and a broken fine snapshot builder degrades the
invocation to scalar diagnostics and stops later fine construction instead of
repeatedly rebuilding a known-broken product. Address regions publish only
their newly completed placements, pilot reads, and region state; the observer
retains the immutable window/support tuples as append-only chunks rather than
concatenating the earlier prefix, and detaches pilot-site fields into
fixed-width records (signed 64-bit page/tile coordinates, byte site/bits,
binary64 evidence), not one persistent Python object per read. An
observer-only capture/tile index updates the strict
strongest-absolute-evidence winner across internal lanes for only the new
sites, then votes across distinct physical captures and reruns the production
known-position BCH presentation only for affected words; equal strength keeps
the earlier read. Placement counts and touched-word coverage likewise advance
by delta/refcount rather than rescanning earlier support, and `address.final`
atomically replaces the active region representation without double-counting
it.

Payload progress is a generation-keyed, per-capture/lane cumulative delta
stream. Each completed region carries cumulative window, profile, and region
scalars plus cumulative upserts only for tiles touched by that region; exact
same-generation duplicates are idempotent, scalar/coverage/older-generation
regressions are rejected, and a newer refinement generation replaces that
provenance's provisional view. `payload.owner_frozen` is one full exact
replacement and may shrink or otherwise differ from the provisional
all-accepted-window union because one-owner selection is then authoritative.
The accumulator uses compact overlap-safe integer tile bitsets, never retains
`WindowEvidence` or image arrays, never copies the earlier state prefix into a
region delta, and is released immediately if fine diagnostics degrade; these
controls are observer state only and cannot influence a stage result or
numerical cache. A newer partial refinement generation is accumulated out of
view: the last complete generation-zero panes remain stable until
`payload.owner_frozen` supplies the full exact replacement.

### 10.2 Transient and committed authority

A diagnostic must never make working state look committed. Each event and
frame is explicitly one of:

- **transient**: a view of current capture/level work against the authoritative
  state digest currently bound to the event stream; or
- **committed**: a view reconstructed from, or checked against, a completed
  retention barrier, carrying the resulting authoritative digest. The compact
  barrier snapshot additionally binds its base digest and exact ledger counts.

Before a level barrier, current placements, attempts, and candidate
certificates are overlays on the committed base state; they may remain as
useful current-invocation diagnostic evidence after an exception but are
never retained receiver facts. `barrier.committed` is emitted only after
state validation, source re-authentication, and atomic save. An invocation
that terminates before `session.complete` emits a best-effort `run.failed`
observer event without changing the receiver failure.

### 10.3 Operator presentation and the four-pane language

The live browser is an operator progress instrument for watching scraps
arrive, place, certify, and close — not the audit report rendered as a web
application. The detached structured detail and final report retain the exact
diagnostic evidence described below; the browser deliberately projects only
the small subset useful while acquisition is running.

The rules in this section are operator-serving presentation decisions, not
safety invariants: the user's declaration in a working session is the
amendment authority for them, recorded by a ledger row. The hard constraints
on this instrument are §10.1 and §10.6 — strictly downstream observation, no
fabricated or reconstructed evidence, headless purity, and timing neutrality
— and those bind every presentation choice. The view may paint anything
faithfully derived from emitted observation; what it may never do is invent
data, reach into receiver authority, or change what the receiver computes.

#### 10.3.1 Fixed composition

The live composition has two fixed parts:

1. a fixed-height six-row text status block; and
2. four equal portrait panes, A through D, in one horizontal row, each with
   its own compact legend below the page image.

The four panes are ONE composed image per page (v0.32), not four separately
published ones: a frame's panes are always the same tick, and the shell
scales that image to the window width, so the rendered pane width is raster
detail rather than layout. The legends stay HTML text in four columns under
the image, where they remain readable at any window width.

All four panes use the registered A4 page aspect and the same visual height;
pane A letterboxes a cropped or non-page-shaped acquisition preview rather
than stretching it. Values changing width, becoming known, or becoming
unavailable must not change the status-block height or move the panes —
reserved placeholders keep every row and legend stable.

There are no mode tabs, page tabs, progress bars, expandable sections,
fold-outs, hover inspectors, scrolling event prose, raw hashes, or full
provenance strings in this composition. A multi-page view may use a compact
plain-text `previous · page n/N · next` selector without changing the fixed
layout; the selected page and current run state are always present as
ordinary text. Browser controls never become receiver policy or evidence.

Each page carries a monotonically advancing presentation revision in the
polled status. The browser keys its displayed image by `(page, revision)` and
requests the stable bounded frame artifact with the canonical
`?frame=<revision>` cache identity; the loopback server accepts that query
only for a valid frame resource and still sends `Cache-Control: no-store`,
other resource queries remain unavailable. Reassigning the same query-free
image URL is not a refresh mechanism because a browser may reuse its
already-decoded image without issuing an HTTP request — the query is a
current-presentation cache key, not a retained historical-frame API. Delivery
acknowledgement records the revision atomically paired with the bytes
actually returned, never the caller-supplied query number, so a stale or
future query cannot falsely acknowledge a later terminal frame.

The shell and pane surround are white. A refresh is double-buffered: the
currently decoded frame stays visible until its replacement has loaded, then
the image node is exchanged — the page must not hide or blank the current
frame while a replacement is in flight. At terminal close, `session.complete`
forces one selected-page presentation revision; if a browser has connected,
normal finalization keeps the loopback server alive until that exact revision
is served or a short bounded deadline expires, while an explicit/error close
remains immediate and the optional acknowledgement never affects receiver
success.

Pane headings are short, high-contrast labels: `A ACQUIRED`, `B PLACED`,
`C ADDRESS`, and `D PAYLOAD`. Long stage names, capture SHA values, lane
identities, and gate explanations remain in detached detail, not burned into
the page image.

#### 10.3.2 Fixed status vocabulary

The six rows have stable semantic ownership:

| Row | Operator content |
|---|---|
| format | detected cell family, registered print geometry, selected/possible encoding row, selected page, and overall open/refused/verified/integrity state |
| lane | lane ordinal/count, pixels per cell, effective DPI, and active/complete/skipped/refused state |
| scraps | unique scrap regions located, placed, and unresolved; explicitly labelled mapped-footprint coverage |
| address | window-queue progress (attempted of the current queue total, and the deferred-cold count while a region is open), placement totals, and matching, insufficient/not-attempted, BCH-refused, and contradictory known-position word totals |
| LDPC | actual decoder calls, durable distinct certificates, certificates born in `retry150`, attempted failures, and below-floor candidates |
| K/fountain | metadata/K decoding state, unique received symbols versus required K, rank versus K, and open/verified close state |

The format row does not overclaim discovery: an E021 `c` vote identifies only
a cell family (never rate, printer, geometry, or encoding); printer and print
geometry are declared/registered facts; an exact encoding row is shown as
recognized only after certificate authority selects it, before which the row
says `discovering` or gives the remaining family; print DPI and current
effective scan-lane DPI stay separately labelled.

Scrap counts are a derived live operator projection keyed by unique
`(capture, lane, region_id)`, not the raw placement-hypothesis count. A region
is `placed` when its current terminal representation has an accepted canonical
placement (accepted redundant pieces count as placed); a located region with
no accepted placement is unresolved while pending or after terminal refusal,
and pane A distinguishes the two. Repeated windows, routes, page hypotheses,
and retained runners never increment the region total. Absent exact region
classification on a cold/no-op view, these counts are `unavailable` — never
reconstructed from placement rows or printed as zero.

The coverage number is written, for example, as
`mapped footprint 18.4% (632000/3440640 cells)`: numerator = the unique
selected-page `(tile, payload-cell)` set with current-generation geometric
reach; denominator = every registered payload cell on that page. Registered
cells have equal printed area, so this is an area-weighted union of the
payload field at printed-cell granularity; it excludes margins, does not
resolve partial coverage within one cell — so it is **not continuous physical
coverage of the whole A4 sheet** — and is not a processed-work counter (a
certified tile can still be geometrically covered by a later scrap).
`mapped footprint` deliberately names only that geometric fact. The older
`128/840 tiles touched (15.2%)` style is a different metric (a tile counts
once whether one cell or the whole tile is reached); it remains useful audit
context but is not the operator coverage percentage, and neither metric may
be silently substituted for the other. Cold state does not retain geometric
cell reach; its exact emitted/informative tile reach may be reported in audit
detail but never substituted for the live mapped-footprint number.

`LDPC calls` counts actual decoder invocations; a below-floor evaluation is
listed separately and spends no call. `certified` is the durable distinct
certificate portfolio, not attempt rows or CRC successes counted twice.
`+N BP150` counts distinct durable certificates whose minting attempt is the
`retry150` stage; ordinary certificates merely revisited there do not count.
Attempted-failed and below-floor remain separate because they imply different
next work. A nonzero address contradiction or integrity failure is shown even
when space requires lower-priority zero fields to be omitted.

The K/fountain row is causal. Before metadata authority it reports metadata
rank/trust progress and `K unavailable` — rank 24 without the required 48
distinct certified equations is not trusted K; once metadata is trusted it
shows the decoded K and state. Fountain `received` is the number of unique
eligible ESI symbols, `required` is K, and rank is shown independently as
`rank r/K` because `received >= K` does not imply full rank. Neither count nor
rank is success: only canonical envelope reconstruction, zero-padding checks,
and payload SHA-256 yield `verified`.

`--complete` does not suspend that causality (v0.32). K is the certified
metadata word, so it appears at the first barrier whose certificates reach
metadata trust, beside the §10.4 count-only block reach; only the facts a
deferred barrier genuinely does not compute — rank and solved state — are
reported as deferred, and never as zero.

For CMY8, metadata K remains shared but the LDPC and fountain facts are
stream-labelled C/M/Y triples, each with its own calls, certificates, retry150
births, received count, and rank; fixed compact stream labels replace extra
rows or a mode tab. A complete physical tile and a closed volume require the
exact row-declared stream conditions; a certificate in one plane is not a
certificate in its siblings.

#### 10.3.3 The four panes

The view retains the E022/E023b/E023c causal vocabulary, adapted to the
colocated v1 tile rather than the old 60/64-cell atlas.

**Pane A — acquired scraps and current geometry.** One authenticated
capture/lane preview with each unique support region numbered. Visible facts:
tight region box, fine-grained active-payload boundary, angle, short
processing state, active window/basis. Accepted, redundant, unresolved,
parked (v0.33 — a phase-1 region with parked windows is NOT unresolved;
that word stays bound to cold-refused-terminal), and
active pieces stay visually distinct by color and outline; the region label
carries only piece number and angle, no state glyph. The box and its number
stand from the moment the survey detects the region until placement resolves
it or the next lane's survey replaces the set (v0.32) — the fine mask edge
alone left a detected-but-unplaced scrap with no boundary of its own for the
whole address stage. Angle is drawn only where a pose has actually been
estimated; the survey estimates none, so none is invented there. Piece
identities are reserved for every surveyed region in survey order, before
placement, so an unresolved region keeps its number and cannot renumber a
later accepted placement; panes A and B share that reserved identity. Pane A is always
capture- and lane-local — several rasters are never composited into an
imaginary physical scan. The preview uses the historical
first/99th-percentile display stretch on detached preview pixels only: not
receiver radiometry, payload evidence, or a new normalized-darkness
algorithm. Queue depth, native bounds, pose origin, pitches, shear,
orthogonality, phase, routes, and refusal evidence remain in structured
detail, not printed over the pane. At resume, pane A seeds from durable
records (v0.45): the committed bootstrap rebuilds the capture's region set
— the base lane of the next uncommitted level, else the finest committed
lane with regions — through the survey records' support masks, with region
states derived exactly from committed poses (placed), parked-window
records (parked), and the committed address prefix (unresolved), and
durable parked chips rebuilt from their persisted lane-frame geometry
under their live identity keys; the next ordinary live survey replaces
the seeded set as it replaces any prior model. The capture-preview
underlay is never seeded: preview pixels are not durable and are not
re-read.

Pane A additionally carries the work-in-flight window overlay (v0.27): the
region's laid-out pose windows drawn as thin outlines in scan space —
pending (laid out, not yet attempted), parked (the v0.23 deferred-cold
frontier, distinctly marked or shaded), rest-decoding (a parked window
spending the v0.29 remaining-slot word route, the last cheap route before a
cold sweep), active (the cold sweep itself, drawn more heavily than the
cheap routes so escalation is visible), and erased on terminal resolution of
either outcome. Subdivision children join
the set when they are queued, so the overlay tracks the real growing queue.
The overlay draws geometry only and is strictly non-authoritative: numeric
queue state lives in the address status row, and the overlay is built from
the actual emitted layout and `address.cold_deferred` facts, never
reconstructed from aggregates. Since v0.33 the overlay adds a distinct
parked-for-mop-up state and a per-chip plan-level digit (per-chip omission
below fit, outline kept), parked rows ride the barrier snapshot so chips
survive their lane's barrier, the lane row's phase tail carries the session
phase driver's rung/tail announcements, long placement sweeps emit
count-bounded heartbeat events (at most 64 per cold sweep; never
milestones), and mop-up levels report through the ordinary event families
under their own unique lane ids (§10.4), so `address.final`'s per-lane
finality stands (docs/PHASED-SCHEDULE.md D14). An R-level's stage-A
`address.final` is empty by design — its snapshot carries the typed
refinement plan (base-lane input, not placements), the view ingests nothing
from it, and adopted refined poses appear only through the same lane's
`address.refined` re-emission, whose snapshot carries an ordinary address
result. Pending work is drawn only in pane A —
a window not yet placed has no page position, so no pending mark may appear
in page space.

**Pane B — page-space placement and pose state.** The selected A4 page with
short piece numbers and stable per-piece identity tints. Piece identity is
keyed by physical capture and deterministic normalized scan-geometry
correspondence between successive surveys, not by scale lane or lane-local
region index: the same scrap keeps its number and tint when independent area
sorting reorders regions, and ambiguous segmentation splits or merges
deliberately receive fresh identities instead of being falsely joined. A
terminal accepted placement uses its solid piece-color footprint immediately
— never a full dashed-violet cover merely because the invocation has not yet
crossed its durable barrier; redundant placement uses a thin footprint;
current candidate focus uses cyan brackets or an outline. Purple remains only
on genuinely current proposals/continuations, while bounded runner, proposal,
refusal, and loser shapes retain their event colors; the legend demonstrates
the actual outline, plus/cross, and diamond/triangle treatments rather than
implying that every placed piece is green. Durable/transient authority
remains exact in detached detail and the fixed run state. Page filtering is
exact: another page's geometry never leaks into the selected pane. While a
lane is active, its piece number, placement boundary, current candidate,
runner-up, refusal, proposal, and loser metadata may be drawn; a committed
lane barrier immediately leaves only the accepted/redundant scrap-colored
support footprint — no old box, number, candidate, runner-up, refusal,
proposal, loser, or continuation remains. A following `lane.open` snapshot
may carry prior-lane continuations for processing but does not redraw them;
metadata appears again only when the new lane produces it. Support from a
finer lane is composited once per physical scrap and lane: overlap gains a
second shade while newly reached boundary cells retain the lighter shade,
exposing a real refinement without resurrecting old metadata. Completed lane
support is decoded once at commit and projected directly into the fixed
panel-resolution history canvas; no second full-resolution cell union is
retained, and ordinary frame redraws do not walk and decode the entire
address history. A completed-only pane carries just the quiet `placed scraps`
heading — no zero counts, provenance line, or unavailable-layer text — while
the underlying durable rows remain in detached audit detail. During the
invocation audited support is exact. On a cold/no-op view, pane B may draw
exact durable scrap poses when their support is available, but historical
proposals and losers remain audit-only; it never presents a semantic
footprint as the missing support mask or window history.

**Pane C — colocated BCH word/address evidence.** Every tile/counter is one of
unseen, partially observed, insufficient/not attempted, BCH-refused,
word-route solved, read-and-validated, or contradictory; refusal and
contradiction are never collapsed, and the two green states are distinct
address authorities (v0.43 declared ruling): full green marks a tile whose
address the word decoder itself produced (an actual BCH word-route SOLVE —
the seeder route), lighter green a placement-addressed tile
(chain/lower/transport) whose word subsequently PASSED the §5.4
known-position evaluation. Every touched
tile prints the numeric count of observed BCH address sites (`0..100`) —
evidence quantity, not decoded counter value. One pane-wide count font is
chosen against the smallest registered tile and the widest legal label
(`100`), leaving an inner border on every tile; counts are omitted when a
deliberately tiny panel cannot fit that minimum safely, and on
durably-seeded tiles, whose counts are live facts that state does not
retain — an omitted count is the honest form, never a fabricated zero.
Several deterministic
scale views of one capture are view support, not independent votes: the
strongest absolute-evidence read wins per site within a capture, distinct
physical captures vote by evidence weight, and production known-position BCH
performs the classification. A small lane corner tick may show where the
current evidence came from; a full inner provenance rectangle may not obscure
the state fill. Exact pilot reads and ordinary word states are live observer
data, so pane C says `unavailable` on a cold state-only/no-op invocation
instead of reconstructing them heuristically; exact durable contradictions
remain visible. At resume, pane C additionally seeds from durable records
(v0.45): durable BCH conflict rows paint exact sticky deep red, and every
tile covered by a committed placement's oriented window footprint paints
the committed-addressed state — pale amber, count omitted — the strongest
claim the record set proves. Neither green authority is durably
reconstructable (pose records carry no route, and the §5.4 word outcomes
are transient), so the seed never paints either green; live re-reads
upgrade seeded tiles in place, and seeded tiles join no live
word-evaluation total on the address row while durable conflicts count.

**Pane D — payload, LDPC, and close state.** Every tile has one primary fill:
unseen, geometrically reachable/evidence, below floor, attempted failed, or
certified; small overlays may identify attempt-ready and latest completed
ordinary/union/retry work without replacing that primary state. Current raw
coverage is exactly one capture/lane/generation; unrelated raw layers are not
max-merged, and provisional region coverage stays visibly distinct from
owner-frozen coverage. A CMY8 tile with stream activity carries an ordered
three-part top rail, segments C/M/Y left to right as stated once in the pane
legend (letters not repeated inside every tile); a wholly unseen tile has no
rail; once any stream is active, neutral sibling segments remain visible so
partial stream success is never rendered as a generic purple tile; the
full-tile certified treatment is used only when every row-required stream is
certified.

Pane D additionally carries a transient retry in-flight layer (v0.27): when a
mandatory selective retry150 pass opens, its frontier's tile addresses are
emitted once as an explicit per-tile snapshot and drawn with the transient
treatment; each highlight clears on that tile's terminal retry outcome —
certificate or repeated failure alike — and the layer never overwrites a
monotone primary state. The layer is presentation only: it is built from the
emitted frontier snapshot, never back-projected from aggregate counts, and an
absent snapshot leaves the layer absent rather than approximated.

Pane D detail retains exact component blocks and source/lane provenance,
evidence digest, derived `k_eff` and nonshort counts, decoder profile and
iterations, syndrome/CRC, certificate dependencies, divergence, context and
refinement decisions, metadata, and live blockwise fountain progress when
causally available. On a cold/no-op view, compact evidence blocks reproduce
exact emitted/informative tile reach and provenance, while attempts,
certificates, divergence, and the close summary remain exact; geometric,
refused, attempt-ready, context, refinement, and address-word facts not
retained in state are labelled unavailable; per-block fountain
`needed`/`have`/rank/solved rows, `k_total`, and `symbols_used` are transient
`CloseProgress` and unavailable cold. No NeedMap is fabricated.

#### 10.3.4 Semantic palette and marks

Durable/terminal state owns fill hue; work and provenance use strokes or
small marks. Each pane's legend is stable and lists its meaningful non-neutral
states; the neutral unseen/background state is implicit and intentionally
omitted. State is not repeated as a one-character accessibility code in either
the legend or the page body. Piece numbers, Pane C observed-bit counts,
coordinate axis labels, and C/M/Y stream labels remain because they carry data
or identity rather than duplicate a color state.

| Meaning | Fill/mark |
|---|---|
| word-route solved address, or certified | green |
| read-and-validated address (placement-addressed, §5.4 pass) | lighter green (v0.43) |
| partial observation or payload evidence | blue |
| insufficient, not attempted, or below floor | amber |
| committed-addressed at resume (durable seed, word evidence not retained) | pale amber, count omitted (v0.45) |
| BCH-refused or attempted-failed | orange |
| contradiction or integrity failure | deep red with a double border |
| unseen | neutral gray |
| transient/in flight | purple dashed outline only |
| active focus/window | cyan brackets or outline only |

Pane B is the exception in which fill hue identifies the physical piece;
stroke and shape carry its state. Certified green and conflict red may never
share a similar hue, lightness, or border treatment. Purple is reserved
for transient work and is not a generic partial/failure color.

Rendering rulings (2026-07-31, superseding the 2028-07-28 dark
presentation): the shell and panes render on white per §10.3.1, with the
semantic fills saturated toward primaries so they read on a white field.

Pane C and pane D use the E022/E023c two-tone chip (v0.32, superseding the
v0.27 borderless ruling): each tile is a soft fill paired with a darker
same-hue outline, the full tile grid is drawn including untouched tiles so
the pane always carries the page's shape, and every count prints in one
dark text color at the single pane-wide font of §10.3.3. Conflict keeps its
double border, active focus stays cyan, transient marks stay purple dashed.
The semantic table above is unchanged and binds the chips: E023's own
attempted-failed red is not ported, because deep red is reserved for
contradiction. Exact color values are implementation presentation under
this table's semantic contract.

#### 10.3.5 Audit retention and qualification boundary

Removing audit prose from the browser does not remove audit evidence. The
terminal detail JSON and final JSON/HTML/SVG report retain source hashes,
full capture/lane/region/window identities, decision metrics, exact winner
and selected searched rival, routes, search/validation mismatch and support,
soft-z and gaps, context offsets/bin observations, attempt evidence,
certificate dependencies, and close facts according to their live/cold
availability; the browser has no fold-out path to these rows — they are
post-run and machine/LLM diagnostic resources. The E022 audit retains the
selected decision rival plus the historical bounded continuation losers, not
all roughly `4P` cold-domain runners merely for presentation; the E023b
context audit retains the actual nine fitted offsets and nine-bin
search/validation support and observation vectors, not aggregates alone;
fixed-profile attempt fields and divergence address/rate continue to be
derived from retained causal facts and the active format row rather than
persisted as duplicate authority.

Production panes contain no ground truth, BER, or qualification-only labels.
Coverage/certification curves, core-edge BER, context-conditioned realized
error, and unresolved-sliver scoring are separate qualification consumers of
recorded evidence and may never feed the receiver. The operator redesign was
a presentation change only: observer isolation, event order, evidence, gates,
attempts, certificates, close state, authoritative digest, and recovered
bytes remain unchanged.

### 10.4 Causal milestones

The observer records cheap status for every event. The canonical pane-bearing
milestones and scalar lifecycle families are:

```text
receiver.provisional
session.open
capture.open
ingest.complete | capture.duplicate
scale.plan
level.open
lane.open
stage.open | stage.complete | stage.failed | stage.refused
survey.complete
address.region_open
address.patch_open | address.patch_accepted | address.patch_refused
address.pose_refused | address.insufficient_support
address.lower_hint_budget_refused
address.window_progress        [pose, route, refine, terminal observer view]
address.region_complete
address.final                  [final known-position word barrier]
context.region_complete
pose_refine.window_progress
payload.plan
payload.region_emitted
payload.owner_frozen
payload.attempt                [latest completed ordinary/union attempt]
payload.retry_attempt
payload.retry_complete
payload.complete
payload.blocks_built             [stream-generic; color carries a
                                  payload.stream detail — the retired
                                  payload.color.* family is gone]
session.phase                    [v0.33 phase driver: rung/tail announcements]
                                 (v0.33 M-levels emit no mopup.* family: they
                                  are ordinary levels to the observer,
                                  reporting through the ordinary survey./
                                  address./payload. families under their own
                                  unique lane.id — so address.final's
                                  per-lane finality holds structurally; the
                                  mop-up survey.complete carries a
                                  survey.mopup_of detail naming its base
                                  lane, with zero regions.)
address.cold_progress            [v0.33 count-bounded heartbeat, <=64 per
                                  sweep; heartbeats are deliberately NEVER
                                  milestones and never snapshot]
close.check
barrier.committed
level.complete | level.refused
scale.stopped
capture.complete | capture.active
session.complete | run.failed
```

`receiver.provisional` is conditional on the installed policy. The address
family above names the actual scalar runtime events; the fine observer groups
their pose/route/refinement/terminal facts into typed address snapshots. The
list does not imply that every scalar event forces an image render.

`address.final` is distinct from the last region callback: it follows final
observation combination and known-position word evaluation and precedes
payload authority; the address panes remain on that final state while pane D
advances. Attempt callbacks run after the decoder result exists, so an active
tile marker means the latest completed attempt, not work allegedly executing
inside another thread.

The scalar `level.open` event precedes its lane snapshot, so it deliberately
does not render the preceding lane under a new level header — the immediately
following `lane.open` snapshot is the effective level-open frame. Full pane
renders are forced at scale stop and lane open, survey completion, each
address final, owner freeze, block completion, the first result of each
ordinary/union/retry attempt kind, retry completion, close check, barrier
commit, level and capture completion/refusal/active stop, and failure; the
first fitted pose or terminal pose refusal in each lane also forces a frame.
Fine region, context, and refinement callbacks update status/state under the
normal frame throttle, and other window/route/attempt events advance
text/status without requiring a frame. `session.complete` forces one final
selected-page revision even when its body matches the final barrier; normal
finalization then gives an already-connected browser a bounded opportunity to
request that revision before shutting down the loopback server.

### 10.5 Multi-page, scale, and capture behavior

The exact session page domain is always present in status and the live
plain-text page selector, including unseen pages. Page filtering is
independent and exact; there are no page tabs. Live frames are materialized
only for pages reached by the current causal snapshot (or the current/default
page); the byte-only HTTP server does not render on a GET and reports an
unmaterialized page as unavailable. The committed final report writes one
compact vector artifact for every declared page, including blank unseen
pages. This event-driven/lazy presentation is an observer optimization, not a
page, history, or evidence cap, and it avoids a full-volume raster contact
sheet. On a cold/no-op invocation, the single committed bootstrap therefore
renders only the current/default live page while still reconstructing the
complete compact committed view in memory, exposing the entire page domain in
status and the selector, and letting the deterministic final report cover
every declared page: cold live-page laziness is not evidence loss and does
not imply that every report page has a PNG frame.

An already-terminal discovery root with one selected exact row routes that
branch through this same observer-only no-op bootstrap when an observer
factory is present: it emits the normal committed exact-row view, must leave
branch state byte-identical, and reuses the close processor's reproduced
payload, without rerunning discovery or a capture lane. A receiver-wide
format conflict has no selected exact-row interpretation and does not run an
open child merely to manufacture a pane.

The in-memory committed observer mirror retains one detached complete scale
ladder for every persisted capture. Its pending/complete/refused/skipped rung
presentation is regenerated from the authoritative plan and retained stage
prefixes — not duplicate `SessionState` authority — and transient live
progress may additionally mark the current rung active. A full bootstrap or
terminal summary with a missing/duplicate ladder is invalid; each barrier
instead upserts exactly its event capture and validates projected
capture/retained-level totals. Compact status exposes the active/latest
ladder plus the total ladder count; current `capture-ladders.json`, cold
bootstrap, terminal summary, and final report expose every complete plan
beside the detailed retained-level records. Panes A/B identify the current
scale lane; pane C combines committed word knowledge without double-voting
internal views of one physical capture; pane D shows the current lane against
the conflict-checked global attempt/certificate portfolio. Non-window events
clear the active-window overlay; lane and barrier boundaries clear the other
lane-local overlays as their authority changes — EXCEPT the v0.33
parked-for-mop-up chips, which deliberately survive their lane's barrier
(they ride the barrier snapshot) and clear only at terminal resolution or
their M-level's retirement.

Prior captures remain visible through committed B/C/D state during the same
invocation, but pane A stays with the current raster. Capture id and evidence
source identity are shown: the capture id is the source SHA, evidence
provenance additionally names its lane, and attempt provenance names its
stage. A new lane clears lane-local window, context, refinement, and raw
payload overlays; the latest completed attempt remains visible across scalar
and lane events until a later completed/committed attempt state replaces it.
An exact duplicate or no-op resume may publish a new committed view from the
exact durable subset described below, but invents no numerical progress
events.

### 10.6 Throttling and timing neutrality

Scalar status, snapshot consumption, and compact view-state updates are
unthrottled so every causal event is represented. Four-pane rendering, PNG
encoding, and current-frame publication use a wall-clock throttle, initially
three seconds, anchored after render/publication completion; repeated
address-region, payload-region, context, and refinement events update the
compact view but do not bypass it, and only the first useful presentation and
major lane/ownership/barrier/terminal milestones may force a frame. A clean
view is never rendered; when a forced revision encodes to the same PNG bytes,
the revision may advance for transport causality but the file is not
rewritten. The interval is observer configuration — absent from the receive
policy and state envelope and unable to alter which snapshots are
semantically available.

Timing is itself observer-only: a headless run performs no clock reads.
Terminal stage events carry `timing.wall_seconds`, `timing.observer_seconds`,
and `timing.processor_seconds` only when an observer and a valid monotonic
clock are present; synchronous observer work nested inside the processor call
is measured as a union without double-counting, processor time is wall minus
that observer time, and stage-open delivery, terminal-event delivery, and
asynchronous HTTP serving sit outside the interval. These are wall-clock
attribution figures, not CPU timings; a missing, non-finite, faulting, or
regressing clock omits all three fields rather than fabricating zero.
Enabling an observer may delay wall-clock completion but cannot change queue
order, search gates, evidence, attempt order or identity, certificates, close
state, or recovered bytes.

The implementation must avoid accidental cumulative work in its core mirror.
Re-review of the first v0.6 implementation projected roughly 41 million
committed-record conversions for C3 and 18 million for C2 because it rebuilt
the full retained snapshot at repeated milestones; it also detached unused
per-block bitmaps worth roughly 256 MiB at full scale and matched every
attempt against every block. The corrected design uses the one-bootstrap/
barrier-delta protocol above, compact block facts, address/capture/lane
indices, and the already-authoritative `AttemptEvidence` produced by numerical
decoding. A proposed retained cache of full 64x64 attempt views was rejected:
it would cross the numerical/observer boundary and could consume multiple GiB.
These are exact representation/work changes; no page, history, certificate,
attempt, or volume cap was introduced.

The committed mirror also maintains exact per-page block, latest-attempt,
certificate, divergence, proposal, and loser aggregates, so pane D and scalar
status read requested-page indexes rather than scanning the complete frontier.
These are presentation-only indexes; no cached value is visible to the
decoder.

This removes the known full-ledger reconstruction paths; it is not yet a
whole-volume performance qualification. No active event builds page/global
audit detail, and repeated region boundaries no longer force page rendering.
Finalization builds global, capture-ladder, survey, and selected-page detail
once. Current files overwrite their predecessor rather than accumulating
history, so disk use is bounded by the current presentation plus the final
report. A bounded-work qualification feeds hundreds of region events and pins
constant bulk-detail work plus interval-bounded rendering; full-C2/C3
render/RSS and observer/core wall-ratio measurement remains the physical
performance gate.

### 10.7 Operational files, transports, and failure domains

A diagnostic invocation publishes only current operational output:

- `events.jsonl`, replaced by the first event and then appended in
  run-sequence order;
- atomically replaced `status.json`;
- one current `frame_pNNN.png` per composed page — the four panes of
  §10.3.1 in one horizontal row, replaced in place and never accumulated
  (ruled 2026-07-31, v0.32, withdrawing the v0.27 W25 four-file shape: the
  composed frame is the operational form, and a frame's four panes are
  always the same tick, pane A included). During a run only the default
  page and the page a browser last requested are composed; the terminal
  frame composes every retained page;
- terminal-only `detail-pNNNNNN.json` for the selected page plus
  `detail.json`, `capture-ladders.json`, and `survey.json`; and
- the final committed-state report and `diagnostic-health.json`.

There is no diagnostic manifest, receipt, epoch, history-gap ledger, transient
frame archive, or resume reconciliation. A new invocation starts a new
operational view and reconstructs its committed base only from receiver state.
Before current finalization succeeds, the live/index shell links only current
status and the current-run event log — never a possibly retained
`report.json` from an earlier invocation; successful report publication
atomically replaces the index with the current committed-state report. The
live shell is served from memory by the optional loopback server
(`--diag-port`); a headless run publishes the files above without an HTML
shell, which is the intended operational form and not a missing artifact.

The output directory is observer storage, never an authority container: its
resolved path may not equal, contain, or be contained by the state file, the
state evidence-blob directory, or the recovered-payload output path, checked
before diagnostic construction so cleanup, corruption, or degradation of
observer output cannot alias authoritative input or output. Filesystem
operations are also bound to the diagnostic directory inode captured at
initialization: every child open is a single-basename, directory-relative,
no-follow operation, an appendable child must be a private regular file
opened nonblocking, and replacing or symlinking the root or a child fails the
affected observer capability instead of redirecting reads or writes. The
opened directory descriptor pins the checked inode across each atomic
operation, closing the check/use rename race.

When pane rendering is installed, each current page PNG is written atomically
under a stable page name; new output replaces the prior current view and is
not a frame commit marker or historical record. Terminal bulk-detail
documents use the same atomic stable-name rule. A write failure disables only
the affected observer capability and never changes receiver state, committed
report input, or cold-state reconstruction.

Event logging, scalar status, frame rendering, final reporting, and an
optional loopback viewer with a plain-text page selector are best-effort
capabilities with explicit dependencies:

- a malformed snapshot or renderer failure disables pane/frame rendering but
  leaves scalar events and the receiver alive;
- an unavailable pane is explicit rather than populated from fabricated data;
- an event-log failure does not disable current status, frames, terminal
  details, or final reporting;
- a status-file failure also disables terminal detail-file publication because
  no current disk locator can be advertised; frame/detail failures otherwise
  disable only their affected disk output while detached in-memory status and
  the live transport may continue;
- a socket bind or live-server failure leaves disk/report publication intact;
  and
- close/final-report errors are warnings and cannot roll back committed work.

`status.json` is deliberately scalar and cheap: current active window, latest
payload attempt, per-page counters, availability/basis labels, and transport
health — never a repeat of the accumulated word, address-attempt, context,
refinement, or evidence-block ledgers on every event. Terminal bulk detail
uses stable resource names; selected-page detail contains only rows indexed
to that logical page (partial word states, current E022 windows, durable
attempts, proposals/losers, coverage, latest-per-tile payload facts), while
page-less E022 failures and complete capture ladders have separate terminal
global resources. Cold-unavailable geometric/refused/attempt-ready fields are
`null`, never fabricated zeros; durable emitted/informative evidence is
explicitly tile reach (`emitted_reach`/`informative_reach`), while
unavailable live cell counts remain `null`. During active reception every
bulk-detail resource is explicitly unavailable and browser polling reads only
compact status and already-encoded current frames; finalization materializes
the selected page and global resources exactly once. There is no row cap or
retained generation.

The live server binds only `127.0.0.1`, requires the exact loopback `Host`,
and serves only detached HTML, pre-serialized current status, terminal detail
bytes, and the current page frame. Its request threads never serialize,
render, or touch the diagnostic view or receiver state; an active-run detail
request returns unavailable and callback failures do likewise.

The final JSON/HTML/per-page SVG report is rebuilt directly from committed
state on a normal run, exact no-op, or resume. Its metadata agrees with the
exact page domain, level/capture states, accepted-pose/proposal/loser and
evidence-block ledgers, attempt and certificate counts, close state,
qualification annotation, and authoritative digest. Every declared page gets
an SVG, including a blank page with no attempts. Each output file is replaced
atomically, but the report is operational output rather than a multi-file
transaction or receiver authority; a partial finalization may leave
individually valid files and a reported diagnostic failure without affecting
committed state. The report does not claim that historical live panes are
reconstructible.

CRC accounting counts only rows for which the decoder was actually invoked;
below-attempt-floor candidates spend zero CRC calls. JSON reports both the
per-call `2^-32` false-accept class and the union bound — stated, since
v0.54, as `calls * DEMAP_ITERATIONS * 2^-32` for cmy7-coded lanes and
`calls * 2^-32` elsewhere: the iterated cmy7 attempt can invoke the CRC once
per inner pass but the durable record keeps only the final pass's outcome,
so exposures are BOUNDED, not counted (registered compromise,
COLOR-UPLIFT-MEASUREMENTS §13.8; exact counting deliberately deferred) — and
retains each evidence origin's source-SHA/lane/placement/patch provenance,
exact held-out log loss, and certificate dependencies. Context decisions
remain live diagnostic snapshots and are not reconstructed in the committed
report. HTML summarizes and links that complete JSON rather than duplicating
every origin row.

Exact compact-state availability is:

| View fact after cold/no-op resume | Availability |
|---|---|
| accepted poses in the report; proposals and losers | exact |
| address attempt/window semantics | unavailable |
| durable BCH conflict rows and quarantined contributors | exact |
| audited address support cells, pilot reads, other word states | unavailable |
| context decisions | unavailable |
| payload emitted/informative block reach | exact |
| geometric/refused/attempt-ready payload coverage | unavailable |
| decoder attempts, certificates, divergence, session state | exact |
| close metadata/final summary | exact |
| per-block fountain rank/shortfall, K and symbol-use progress | unavailable |
| parked mop-up windows: per-(capture, lane) counts, support distribution | exact |
| pending refinement lanes: per-capture count of uncommitted R-levels (v0.42 epilogue) | exact |
| refinement decision audit and lane preview | unavailable |
| pane A/C resume seed: region support and states, committed placement tile cover, parked chips, conflicts (v0.45) | exact — derived only from the exact rows above; word-route/§5.4 authority and site counts stay unavailable |

The live four-pane renderer follows the same boundary: it shows the exact
durable subset and labels absent facts, never mines prior frames as authority
or retains a whole raster/unauthenticated path merely to improve diagnostics.

### 10.8 Implementation and qualification boundary

The current implementation (first landed at v0.10) includes the typed lazy
snapshot path (including observer-isolated `CloseProgress` construction),
causal A/B/C/D renderer, the fixed operator status/pane composition and
semantic legends, current-layer/correlation semantics, disjoint
diagnostic/authority paths, atomic current files, explicit optional loopback
server, committed-state report, explicit cold availability, one in-memory
committed bootstrap followed by digest/count-checked barrier deltas, and
independently degradable capabilities. The CLI starts it only for `--diag`;
interval, panel width, and explicit optional port are observer settings,
while the production detector remains fixed at `ctx-pava-v1` and has no
diagnostic or detector-selection switch.

Qualification is deliberately split (Phase-7 lane structure, v0.41): the
bounded phased multi-capture end-to-end (`test_phased_roundtrip_e2e`, slow
lane) closes a genuine production-runtime session — full ladder, mop-up
tail, blind rotated re-placed scrap, resume-mid-session, deferred
`--complete` close — under a wall-budget tripwire; fast source-local/
synthetic pins exercise observer isolation, throttling, malformed
snapshots, injected observer/capability failure, and operational-output
edge cases which would be artificial in that round trip. Together they
exercise all of the following:

- observers of any fidelity (off, scalar, fine, deliberately failing)
  never change authoritative state or recovered bytes (synthetic
  byte-parity pins in `test_trust_boundaries` + the observed e2e legs);
- source-local fixtures preserve attempt ordering/identities, certificate set,
  close result, and recovered bytes with observation on, throttled, and
  deliberately failing;
- a headless run constructs no fine snapshots, close block-progress values,
  or render data; a failing close-progress factory is observer-isolated;
- event ordering and transient/committed authority match retention barriers,
  including an aborted transaction and exact no-op resume;
- every causally materialized live page is independently renderable without
  cross-page leakage; the final report covers every declared page with no
  page-domain truncation;
- compact status work does not grow with accumulated per-page rows, active
  detail requests stay unavailable, finalization builds each selected/global
  detail resource once, and hundreds of repeated region/window/attempt events
  do not rebuild bulk detail;
- same-capture scale views carry no false independence; distinct physical
  acquisitions remain separate same-lane components;
- throttle boundaries and post-render anchoring are deterministic under a
  fake clock; recorded numerical timings exclude observer work;
- each invocation starts a fresh scalar log and bounded current-file set,
  observer/authority path disjointness is enforced, and no implicit HTTP
  server starts without an explicit port;
- cold committed snapshots expose the exact close summary and explicitly omit
  transient per-block fountain progress;
- B/W and CMY8 operator projections keep six fixed status rows, four equal
  page-shaped panes and per-pane legends while exercising pre-K, retry150,
  verified, contradiction/integrity, and cold-unavailable states — with
  status assertions distinguishing unique regions from hypotheses,
  payload-cell area from tile touch and whole-sheet physical area, calls from
  below-floor evaluations, and per-stream CMY8 progress; and
- renderer, disk, optional live-server, and final-report failures are
  injected independently, with the final committed report matching state
  digest, pages, levels, attempts, certificates, qualification status, and
  close state.

These gates establish implementation correctness, production-path parity on
the ideal fixture, observer non-authority, and synthetic failure isolation;
they do not make the receiver or its diagnostics physically
production-qualified. Outstanding work is a recorded real-v1 campaign that
compares the diagnostic facts and real-capture operator usefulness against
E022/E023b/E023c on the same captures, plus whole-volume render time and peak-
RSS measurements. The numerical physical/null/support and
complete-domain receiver blockers in §12 also remain visible in every
diagnostic result.

## 11. Relationship to the historical experiments

| Historical stage | Retained in Track 3 | Removed or adapted for v1 |
|---|---|---|
| E021 | tensor survey, physical constants, one platen pitch, asymmetric fusion, topology completion | compact support records and bounded tiled work; no alternate raster normalizer; angle hints dropped (v0.20) |
| E022 | complete hypothesis testing, search/validation split, weighted winner/rival gate, BCH and chaining, lower-hint route | reference generated from colocated v1 word sites; no 60-cell lattice or pilot/payload transform; §5.4 replaces historical session abort with selected-contributor placement quarantine |
| E023 | per-tile LDPC attempt chain incl. the 018.7 bounded-LLR invariant, gather inversions, syndrome+CRC certification | one counter addresses pilot and payload; typed attempt records; no GE erasure fallback (E023 round-4 record, ~2 unique tiles) |
| E023b | one-owner capture evidence, PAVA/context calibration, independent-capture union, max60 followed by mandatory selective retry150, CRC authority | one counter/pose addresses pilot and payload; compact evidence blocks and typed attempt identities; no retry policy toggle |
| E023c | direct-native scale lanes, barrier proposals/losers, certificate-only authority, NeedMap, held-out certified refinement | format-v1 lane schedule and metadata; no old opaque session embedding or source-code fingerprints |

The old experiment results remain the comparison floor, especially the HP C3
754-certificate and HP C2 1,438-certificate single-capture runs and their
verified payloads. They are not automatically format-v1 qualification — the
printed geometry, site density, LDPC framing, metadata, and page domain
changed — so a v1 qualification must compare like-for-like evidence and state
its footing.

Divergence register: the context-offset sigmoid is canonical-by-fiat (v0.39
ruling 10.3) — Track 3 uses the two-branch form in `detect._solve_offset`
while legacy paperholo `payloaddec.py` used `scipy.special.expit`, and the
two are measurably non-identical (1–3 ulp on ~45% of negative inputs, scipy
1.18.0/numpy 2.5.1; masked by the CTX_ROOT_TOL bisection tolerance, pinned
in `tests/holo/test_canonical_sigmoid.py`). Conversely, the K window score
transform is float32-native as of v0.39 (ruling 10.2):
`_payload_sampling._scores` computes median/spread/score arithmetic in
float32, restoring the legacy E023b arithmetic shape (`payloaddec.py`
`_emit_window_from_means` — float32 means whose scalar casting never left
float32); the earlier Track-3 float64 compute-then-quantize detour was an
unregistered bit-level divergence from legacy and is gone.

Explicit exclusions:

- no production generator/receiver/runtime/CLI imports from `paperholo` or any
  experiment (qualification-only differential oracles are outside the runtime
  graph);
- no Track-2 charsheet/analyzer dependency, normalization, constants, or
  promotion path;
- no E024 feedback loop;
- no compatibility loader for discarded pre-freeze Track-3 state;
- no source-code hash in state;
- no ideal-capture production decoder; and
- no hidden page, history, certificate, or full-volume memory cap.

## 12. Qualification boundary and current gaps

The Phase-7 test lanes (v0.41) exercise the layers independently and in
composition. Fast pins cover E021 survey, E022 placement (incl. the null
batteries), the E023b payload transaction (detect unit floors/clamps, the
payload null set, retry150 eligibility, trust-boundary guards ported from
the retired `qualify_runtime` battery), E023c scale/refinement,
metadata/state, policy identity/domain, and runtime/replay. The curated
slow lane (`HOLO_RUN_SLOW_TESTS=1`) holds the seven-coding real-payload
gate net (THE acceptance checkpoint), the measured-channel gates, and the
ONE bounded phased multi-capture end-to-end (restart, rotation, mop-up
tail, `--complete`, wall-budget tripwire) that replaced the pathological
production-roundtrip battery.
The AST boundary tests in `tests/holo/test_characterize_boundaries.py`
enforce that production receiver/generator modules do not import the
standalone characterization package and that characterization does not import
production generation/reception code.

Current-API regression tests additionally pin native ingest identity/dtype/
crop/refusal contracts, wrong-page and noisy/erased LDPC certification with
zero wrong certificates, and a K=61 fountain close that exercises repair-row
elimination, exact rank shortfall, and terminal envelope-SHA failure. These
replace useful invariants formerly buried inside discarded receiver-API tests.

### 12.1 Authentic E021 differential gate

E021 does not interpret payload values or require their seed/key, but its
tensor response depends on the realized two-dimensional modulation texture —
an all-uniform field is intentionally invisible — so varied payloads, planes,
stocks, scanners, and placements strengthen the evidence. Historical c2/c3
sheets and physical confetti are therefore valid stage-0 qualification inputs
even though they predate the colocated format; they qualify
survey/segmentation only, not the v1 E022/E023 address, channel, LDPC, or
fountain layers.

`holo.receive.qualification.e021_real` freezes 38 authentic/derived corpus
entries by encoded SHA-256, runs production and frozen E021 sequentially in
separate processes, and first requires the same encoded-source identity and
canonical float32 E021 feature-plane SHA-256 — this matters for JPEG/YCbCr
TIFFs, where Pillow and tifffile can decode the same compressed samples
differently (an ingest difference, not a segmentation difference).

After input identity, the pinned-environment gate compares exactly:

- global c, scanner pitch, and ordered pitch votes;
- all normalized diagnostics;
- ordered candidate count, bbox, area, and tensor score (angle hints were
  additionally compared until their v0.20 removal); and
- a streamed SHA-256 and true-pixel count for every native support mask.

Holo's compact support is expanded in bounded row strips, so qualification
does not allocate a second page-sized mask. A separate topology inventory
counts foreground components, exterior-connected false support, enclosed
holes, their maximum inscribed radii in payload cells, and residual holes
eligible for the three-cell repair rule. Physical piece counts and known c
are independent gates where frozen evidence exists; differential equality
alone is not relabelled as segmentation quality.

The complete 2026-07-23 campaign exercised all 38 frozen sources — 34 grey
and four RGB/YCbCr captures/qualified derivatives totaling 68.6 GB, spanning
c2 and c3 full sheets, displaced repeats, three scanner resolutions, repeated
physical confetti, close scraps, K/CMY material, and mixed-structure stress
pages. All 38 were bit-exact across every field and native mask bit: 540
regions and 27.6 billion supported native pixels. Known physical counts were
17/10/8 on both c3 confetti takes; all known c and full-sheet counts passed.
The masks retained 19 enclosed topological support voids across the corpus
and left zero voids eligible for bounded repair or disconnected supports —
where “void” means an enclosed inactive component of the coarse
search-support mask, not by itself a physical hole or excluded payload.

A post-campaign diagnostic atlas reauthenticated each source, regenerated the
complete survey contract, and mapped every component through exact half-open
native coordinates onto raw scanner samples. Manual inspection found no
apparent exclusion of payload-bearing material among the 19: three are the
explicit rectangular voids on the Xerox RGB large-hole stress page, 13 RGB
and two grey E025 cases fall on non-payload mixed-structure patterns
(including black/white stripes), and the remaining C3 confetti case lies at a
material/background boundary. Black/white bars can select as support while
their light corridors become enclosed after density selection and
compact-grid quantization, so the topology can report voids in structure
which is not payload. Nine E025 RGB cases are threshold-edge results — radius
3.000065 payload cells, only `6.51e-5` support-grid cells beyond the
three-cell fill cutoff: correctly retained by the frozen comparison, but not
to be presented as comfortably separated from that threshold. The atlas is a
qualitative corpus audit, not an independently annotated-mask gate or proof
that every future payload texture is immune; the durable conclusion is “no
visually apparent payload exclusion in the audited corpus,” while exact
differential equality establishes only that Holo and frozen E021 segment
these inputs identically.

The reproducible lanes are:

```
python -m holo.receive.qualification.e021_real --lane smoke
python -m holo.receive.qualification.e021_real --lane campaign
python -m holo.receive.qualification.e021_real --lane full
```

`full` runs the multi-gigabyte native release corpus; it is offline by design
and is not part of ordinary CI. Frozen scan hashes, dependency versions,
implementation hashes, exact results, topology, wall time, and peak RSS are
emitted in strict JSON.

Landing validation for v0.5: `tests/holo` 192/192 green in 96.62 s; the
repository collected 880 tests, its sandbox-safe pass ran 873 with one
expected skip in 1069.23 s (explicitly deselecting six historical live-view
tests that require a localhost bind), and those exact six passed in 67.20 s
with localhost binding enabled — every collected non-skipped test passed
under the permissions it requires.

The final diagnostic release re-audit was qualified on 2026-07-22: the
current `tests/holo` run passed 341 tests in 127.74 s with its one loopback
test sandbox-skipped (that exact test passed with socket permission); the
complete repository collected 1,030 tests — 1,022 passed, six historical
live-view tests failed only at sandbox-denied binds, two loopback tests
skipped, in 1128.01 s — with the exact six failures passing 6/6 in 67.53 s
and both skips passing separately with localhost permission. The source
diagnostic qualifier passed 9/9 and the genuine production round-trip
qualifier 4/4, including fine diagnostics versus headless byte/state/payload
parity, restart, rotation, and observer-failure isolation. Compile,
source-size, archive-isolation, and diff checks passed; no experiment source
was changed for this validation.

At the v0.9 baseline, these programs establish technical regression coverage
and synthetic composition. Historical/physical equivalence remains the
qualification target. In particular:

1. the v1 physical/null placement gate, true channel-BER envelope, and support
   safety margin have not been frozen from real v1 captures;
2. the complete-domain rival refusal is now MEASURED AND DIAGNOSED
   (2026-07-31 post-hoist rerun, `docs/FULL-DOMAIN-RIVAL-ANALYSIS.md`,
   harness `tests/holo/_bench_full_domain_rival.py`): the 0.176 reproduces
   exactly on current code — the rival is a cross-page tile-lattice-aligned
   full-overlap alias whose single GF(2) difference codeword (|E| = 31,
   spectrum row 31:119) lands only 8 of its 31 bits in the 45-site search
   parity class, a deterministic 8/45 = 0.178 hard / 0.176 weighted; d = 27
   binds full words (alias full-word mismatch 0.303 >= 0.27) but not the
   parity subclass, so a sub-0.20 rival at the complete C3 domain was
   structural, not unlucky. The inherited decoy bar was qualified on the
   single-sheet ~784-hypothesis domain with no cross-page linear-alias
   family. RESOLVED BY USER RULING at v0.30: the whole-word rival gate
   (gate id `holo-v1/e022-v2-wholeword-rival/session-gap-gate`, policy id
   `v5-wholeword-rival`) restores the d=27 floor — the complete 312-page
   domain now ACCEPTS the exact winner and the 44-degree small scrap
   recovers. Open duty: real-capture qualification of the new gate;
3. whole-volume C2/C3 wall time and peak RSS after the final cold-search
   optimizations still need a reported production run;
4. physical multi-capture, crop/confetti, mixed-volume, and scanner/clientele
   gates remain to be run;
5. the measured-channel simulator's pessimistic C2 development floor cannot
   substitute for real C2 qualification;
6. the operational diagnostic has implementation/synthetic qualification but
   still needs the real-v1 comparison, operator-usefulness, full-volume
   render-time, and peak-RSS campaign in §10.8; and
7. the persisted known-position BCH firewall in §5.4 has synthetic and
   adversarial Address→Payload coverage, but physical-v1 conflict incidence,
   false-quarantine rate, and yield impact remain unmeasured. Its selective
   quarantine is an intentional departure from historical session abort, not a
   claim of exact reference behavior.

By user ruling, these open duties no longer make the receiver unavailable.
The production composition installs the exact historical stand-in described
in §5.3 and is operational, but every run and result remains visibly
provisional. The warning explicitly includes the physical/null/support work
and the diagnosed `0.176` complete-domain rival with the v0.30 whole-word
gate that resolved it (real-capture qualification still owed). Availability does not satisfy E022's
readiness gate, upgrade synthetic round trips to physical qualification, or
permit copying, retuning, or weakening the constants. A future qualified row
requires the recorded evidence, a design amendment, and a deliberate status
change.

## 13. Standalone characterization boundary

The suspect Track-2 implementation has been deleted. The current
`src/holo/characterize` instrument was built independently and is reached
through `./confetti.py discover`; it is not a receiver mode, kernel, oracle,
or profile-promotion path.

Dependency direction is forbidden between characterization and the production
generator, receiver, and shared format/device/core packages: only the CLI
composition root imports `holo.characterize`, and characterization does not
import the generator, receiver, experiments, Track-2, or `paperholo` —
enforced by current AST boundary tests. Characterization's known-ground-truth
detector and local pose estimates are supervised metrology evidence and
cannot be substituted for a blind production-receiver qualification.

The current characterization v2 pages use two separated compact HCAL-R1
strips to bind canonical page identity to guarded live interpreter/device
readback. That readback is provenance only. Usable authored DPI/cell size,
geometry, scanner adequacy, and payload-safe reach come from physical
sheet measurements and do not become receiver constants automatically.
Likewise, the restored E025-derived phase, grid, edge, tone, morphology, and
scanner probes remain characterization evidence; no receiver coupon,
detector, or compatibility transport is imported from them.
