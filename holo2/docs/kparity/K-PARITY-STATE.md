# K-parity campaign — state as known, 2026-08-28 (campaign STOPPED here)

The user's directive (RULINGS §N, verbatim inside): every concrete
holo1 K algorithm that influences payload retrieval, implemented in
holo2, proven by honest code review + cross-tree oracle pins
(§N.1 — decode batteries once per batch and at milestones only; the
meta/audit families are off the critical path). The campaign was
stopped by the user on 2026-08-28 after Wave 1; this file is the
currently-known state, recorded at the stop.

The three sibling files in this directory are verbatim snapshots of the
campaign's working records (produced in the `holo2-catchup` worktree's
scratch, brought into main as documentation — NOT a code merge):

- `RULINGS.md` — the binding rulings §A–§N.1 (catch-up campaign
  through K-parity).
- `DIVERGENCE-LEDGER.md` — the 59-row v1-vs-holo2 divergence audit
  ("implement v1" line), each row with measured impact and package
  assignment F1–F10.
- `K-PARITY-CATALOG-draft.md` — the Wave-1 mechanism book: 101
  mechanisms (80 across placement / payload decode / calibration /
  refinement / union / close / state-provenance + 12 holo2-only + 9
  ledger blind spots), each with v1 file:line, holo2 counterpart,
  ledger row, and a §N classification. DRAFT STATUS: written by a
  Wave-1 worker, lead-skimmed but not editorially verified; known
  stale spots exist (some rows say "MISSING — build (F1/F2a)" for
  mechanisms F1/F2 already landed — read those classifications against
  the ledger's LANDED-SINCE rows before acting on them).

## What is where

- **In main** (merged earlier, commit `1affbcc` and before): the full
  holo2 catch-up line incl. F1+F2 ("implement v1": ownership freeze,
  window-scoped ctx, re-sample under revised pose), the crop harness +
  first battery record (MEASUREMENTS 2026-08-28 HEALTH row), and these
  docs.
- **On branch `holo2-catchup`, NOT in main** (the user ruled docs-only,
  no merge; the branch ref is KEPT because these four commits are
  finished, green, and would otherwise be lost): `4cc09e9` M1
  instrument (`holo2/measure/rf1_gate_flips.py` + oracle), `0c7c7dc` M2
  (`f7_lattice_probes.py` + oracle), `3d54b55` M3 (`f6_f8_counts.py` +
  oracle), `9480a3e` the F10 pin battery (9 mutation-verified
  cross-tree oracles, ledger rows 37/39/43/45/46/48/52/53/55). Fast
  lane was green at each (~2988–3000 passed).
- **Discarded with the worktree**: the interrupted F3 builder's
  uncommitted port (+253/−15 across solve/refine.py, refine_fit.py,
  test_refine.py) — mid-flight, unreviewed; the design is fully
  recorded (ledger row 5 + M1's verified transcription), so nothing
  unique was lost.
- **Salvaged text artifacts** (reports/results of every measurement,
  without the rebuildable state/crop bulk): `scratch/
  holo2-catchup-archive/` in the main checkout.

## Measured facts from Wave 1 (2026-08-28)

- **M1 — F3 gate (ledger row 5)**: re-scored every archived RF1
  adoption both ways (marginal-only vs v1's window-ctx-corrected
  logits): **zero flips in 237 revisions** (89 e029 / 148 xerox), worst
  margin ~1800× MIN_HELDOUT_GAIN. F2's recorded RF1 yields are NOT
  confounded. Row 54 prerequisite verified complete on every
  evidence-owning pose (1,294 + all xerox poses, 0 pieces dropped).
- **M2 — F7 evidence (row 6)**: origin-diversity drift is real (tx=0
  residue: v1 mean 4.94 distinct window origins/tile vs holo2 2.00);
  pose discriminator says both trees' registrations AGREE at 16/8/4 ppc
  (photometry reading; 2/1 sampling-limited); the decisive
  shifted-window experiment: **567 attempts, 311 accepted placements,
  zero certificates** on the 13 hardest tx=0 tiles. F7's yield case on
  these sheets collapsed; the mechanism gap stands.
- **M3 — F6/F8 counts (rows 15, 19)**: v1's loser ledger holds 2 (e029)
  / 5 (xerox) / 73 (demo9) losers; every real-sheet loser anchors
  already-certified territory — zero relevance to the current parity
  gap; demo9 is the real population. Word-firewall scope: pooled-vs-
  per-pose changes word-DECODE verdicts on 114/55 tiles but **conflict
  verdicts are zero under both scopes** — the firewall's protective
  role never fires on this corpus.
- **F10 pins**: 9 of 10 charged rows landed as mutation-verified
  cross-tree oracles (row 50 declined as not worth a fragile pin). One
  test-construction hazard caught and recorded (self-referential dtype
  reference made a pin vacuous; fixed by pinning the constant by name).
- **Crop battery context** (already in main): h2 certifies 9/22
  still-missing tiles and 15/48 neither-tiles on crops — the remaining
  full-sheet gap is context/scale-dependent, not cell capability;
  4 of 27 crops are control-perturbed (root-cause owed).

## K parity at the stop (H6 arithmetic, unchanged since 2026-08-24)

e029 −2, xerox −16, demo9 −5 vs v1's archived harvests; zero wrong
certificates everywhere; both trees end volumes honestly OPEN. The
residue is attributed: e029 = accepted floors; xerox = the tx=0
page-edge band (photometry-limited per M2); demo9 = predicted
unrescuable by ordering rules (F5 label-channel / union-baseline
candidates, unproven).

## The open retrieval-critical list (what a resumed campaign builds)

Per §N.1, in priority order, all v1-faithful with per-rule pins:

1. **F3** — RF1 adoption gate to v1's ctx-corrected logits (rows
   5/12/54; expected behavioural change NIL per M1 — a pure parity
   swap). A discarded draft existed; rebuild from the ledger + M1.
2. **F8** — pooled word-firewall voting + site-cell dedup (rows 19/22;
   expected NIL on this corpus per M3).
3. **F4** — placement admission: delete the holo2-only rival bar (row
   8, the sole holo2-only mechanism with no doctrine cover), v1
   pixel-space step quantisation (row 18 — the one expected to move
   behaviour), first-unconditioned-fit-wins seeding (17), support-floor
   ordering (23), straddle→subdivision routing (24).
4. **R-level re-derivation** (catalogue 1.12/4.11/4.12) — v1's
   `place_committed` unconditional per-level re-read + full schedule
   over the delta; F2 built only the revision-triggered half. Pull-model
   idiom recorded in the catalogue row; byte-equality contract
   (re-sample ≡ forced full re-derivation) is the acceptance gate.
5. **F5** — label channels L2/L4 + refused-marginal-fit-keeps-pose
   (rows 9/10/44; edge-localized, demo9-shaped).
6. **F6** — mop-up exhaustion sweep + loser-hint ledger (rows 15/16),
   BEHIND a census of `src/holo/receive/evidence_blocks.py`'s mop-up
   SUPERSESSION ALGEBRA (`validate_block_supersession` /
   `supersede_with_committed` / `apply_mopup_supersession` /
   `winner_codes`) — the catalogue's headline blind spot (§9.1): the
   byte-exact extension-only contract a re-observing window must obey;
   no census or ledger row covers it. A census agent was started and
   stopped with the campaign; nothing written.
7. **F7** — per-lane window lattices (row 6; fresh-state break — no
   archived state resumes across it; yield case weak per M2, mechanism
   parity is the reason).
8. **Union on paper** — the add-a-scan resume verdict (catalogue 5.2;
   unmeasured in BOTH trees; D5c unblocked it).

Off the critical path by §N.1 (classify-and-park): F9 provenance
(frontier digest, per-barrier re-auth, --page semantics, divergence
diagnostics), report surfaces, platen-backing watch item.

## Environment note (3.14t, measured 2026-08-28)

`/opt/homebrew/bin/python3.14t` = 3.14.7 free-threading build; the full
stack (numpy 2.5.2 / scipy 1.18.1 / pillow / cryptography) has native
cp314t wheels and the GIL stays off with all of them imported. holo3's
worktree already runs on this footing. holo2's recorded parallelism
ranking stands: vectorize the named kernels first (BCH ~72% CPU,
bit-exact = format law, ~2× serial), then the 3.14t experiment
(atomicity audit of the wall, byte-identical decode required), then a
process pool.
