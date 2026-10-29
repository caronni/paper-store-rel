# holo2 documentation census (Gate D input)

Tree: `1d72f96`, date 2026-09-04. Criterion: a holo2 doc is ARCHIVED (git-mv
to `docs/archive/holo2/`) if it carries at least one measured number or
ruling with no citation, in its meaning, anywhere outside `holo2/` in the
current tree; otherwise it goes to HISTORY (the deletion commit is the
pointer). Checks were run as `git grep -n '<number or phrase>' -- ':!holo2'`.

Superseded 2026-09-05: Germano took the tightened cut in GATE-D-BRIEF.md §2 (receiver measurements and adopted rulings only), so 31 of the 38 rows marked ARCHIVE below were archived at `39df5cf`; the other seven — `holo2/README.md`, `H3BIS-ARCHITECTURE-REVIEW.md`, `H4-W3/W4/W5-PLAN.md`, `HARDENING-WORKLIST.md`, `REFACTOR-WORKPLAN.md` — went to history with the deletion (`a805888`), their three ruled sentences quoted in `docs/archive/holo2/README.md`. The table below stays as the record of the literal criterion.

## 1. Decisions

| file | decision | archive name | the unique number/ruling (line) — or why history |
|---|---|---|---|
| `holo2/docs/DESIGN.md` | ARCHIVE | `DESIGN.md` | ruled |
| `holo2/src/holo2/capture/DESIGN.md` | ARCHIVE | `pkg-capture-DESIGN.md` | ruled |
| `holo2/src/holo2/core/DESIGN.md` | ARCHIVE | `pkg-core-DESIGN.md` | ruled |
| `holo2/src/holo2/diag/DESIGN.md` | ARCHIVE | `pkg-diag-DESIGN.md` | ruled |
| `holo2/src/holo2/engine/DESIGN.md` | ARCHIVE | `pkg-engine-DESIGN.md` | ruled |
| `holo2/src/holo2/format/DESIGN.md` | ARCHIVE | `pkg-format-DESIGN.md` | ruled |
| `holo2/src/holo2/solve/DESIGN.md` | ARCHIVE | `pkg-solve-DESIGN.md` | ruled |
| `holo2/src/holo2/solve/PROVIDERS.md` | ARCHIVE | `PROVIDERS.md` | ruled |
| `holo2/docs/MEASUREMENTS.md` | ARCHIVE | `MEASUREMENTS.md` | ruled |
| `holo2/docs/measurements-h3.json` | ARCHIVE | `measurements-h3.json` | ruled |
| `holo2/docs/CAPABILITIES.md` | ARCHIVE | `CAPABILITIES.md` | ruled |
| `holo2/docs/ENGINEERING.md` | ARCHIVE | `ENGINEERING.md` | ruled |
| `holo2/docs/CATCHUP-SUMMARY.md` | ARCHIVE | `CATCHUP-SUMMARY.md` | ruled |
| `holo2/docs/kparity/DIVERGENCE-LEDGER.md` | ARCHIVE | `kparity/DIVERGENCE-LEDGER.md` | ruled |
| `holo2/docs/kparity/K-PARITY-CATALOG-draft.md` | ARCHIVE | `kparity/K-PARITY-CATALOG-draft.md` | ruled |
| `holo2/docs/kparity/K-PARITY-STATE.md` | ARCHIVE | `kparity/K-PARITY-STATE.md` | ruled |
| `holo2/docs/kparity/RULINGS.md` | ARCHIVE | `kparity/RULINGS.md` | ruled |
| `holo2/docs/kparity/wave1-instruments.patch` | ARCHIVE | `kparity/wave1-instruments.patch` | ruled |
| `holo2/README.md` | ARCHIVE | `holo2-README.md` | "2701 passed / 0 skipped" and "nine verdicts / 40 checks over five shared real decodes plus one CLI-driven end-to-end run (~91 s)" (:15-18) — no outside hit |
| `holo2/measure/README.md` | ARCHIVE | `measure-README.md` | `index_equivalence.py` W3 measurement "1,244 commits compared, 476 expansions, 24,571 descriptors, 0 divergences" (:134-135) — no outside hit |
| `holo2/docs/CATCHUP-PLAN.md` | ARCHIVE | `CATCHUP-PLAN.md` | tile (0,42,9)'s sibling (42,8) "already named as unrescuable by any ownership rule (oracle ceiling 2.76%)" (:434) — no outside hit |
| `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md` | ARCHIVE | `H3BIS-ARCHITECTURE-REVIEW.md` | F-16 finding: "an 8.05 MB envelope and roughly 2,119 commits; 98.1% of wall in per-commit snapshots; per-commit snapshotting 57x slower than close-only" (:391-396) — no outside hit for the 2,119-commit / 57x pairing |
| `holo2/docs/H4-LANES-PLAN.md` | ARCHIVE | `H4-LANES-PLAN.md` | two ruled decisions: "the duplicate-capture provenance rider is DEAD ... The duplicate-sha drop (b58b69f) is the whole guard" and "`capture/scale_space.py` is KEPT — it is the cascade's carrier" (:73-77) — no outside hit. (The headline number this file was flagged for — e029 K 55.4% / hp c3-cmy8 27.0% / xerox c3-cmy7 46-54% / e023c HP 89-92%, :33 — IS fully carried outside, see §2; it does not itself justify archiving, the two rulings above do.) |
| `holo2/docs/H4-PLAN.md` | ARCHIVE | `H4-PLAN.md` | W1a fixture-lattice fix: "comparisons 4,066 -> 4,081 (default) and 9,001 -> 9,131 (slow)" (:256-257); also "10.56 s / 720 MB measured" health-spine re-pin (:645) and real-sheet echo "utilisation 93.9%" (:685) — no outside hit |
| `holo2/docs/H4-W2-PLAN.md` | ARCHIVE | `H4-W2-PLAN.md` | "holo2/tests (1,596 in 13.4 s)" fast-suite count (:236); RSS ladder "61 MB -> 2,157 MB peak -> 517 MB after" (:288) — no outside hit |
| `holo2/docs/H4-W3-PLAN.md` | ARCHIVE | `H4-W3-PLAN.md` | W3 exit snapshot "unit 1825, oracles 314, verdicts 36" (:32-33); verdicts consolidation "37 checks/143 s -> 36/78 s" (:25-26) — no outside hit |
| `holo2/docs/H4-W4-PLAN.md` | ARCHIVE | `H4-W4-PLAN.md` | test-count snapshot "unit 1,864, oracles 314, verdicts 37 at ~81 s" (:30) — no outside hit |
| `holo2/docs/H4-W5-PLAN.md` | ARCHIVE | `H4-W5-PLAN.md` | "the verdicts gate 39 checks, 81.83 s live vs 80.11 s with..." (:209) — no outside hit |
| `holo2/docs/H5-PLAN.md` | ARCHIVE | `H5-PLAN.md` | commit-count reductions "8,394 commits (was 13,317...)" and "6,791 commits (was 11,469, -41%)" (:396,398) — no outside hit |
| `holo2/docs/HARDENING-SYSTEMIC-REVIEW.md` | HISTORY | — | a review with no adopted ("RULED"-tagged) decision; its only unmatched numbers are incidental pytest wall-clock snapshots ("1287 passed in 206.98s" :470, "84 passed in 63.96s" :576) from a since-superseded commit, not substantive receiver findings; every substantive number it quotes (1,356 / 1,359 certificates, 465,580 bytes, 401 s at cadence 512) is cited outside via `ARTEFACTS.md` / `seeds/holo2-behaviour-ledger.md` |
| `holo2/docs/HARDENING-WORKLIST.md` | ARCHIVE | `HARDENING-WORKLIST.md` | baseline "899 passed, 35.7 s" / "388 passed, 213.7 s" (:22-24); ruling "RULED 2026-08-12: 512 + fsync" for the snapshot cadence (:960) — no outside hit |
| `holo2/docs/REFACTOR-WORKPLAN.md` | ARCHIVE | `REFACTOR-WORKPLAN.md` | user ruling 2026-08-10: "each subsystem is a quasi-independent library in one repo — reviewable alone, replaceable alone, with LOCAL design authority" (:17-19) — no outside hit (thin: this is the file's only qualifying content, a process/architecture ruling rather than a receiver measurement) |
| `holo2/docs/STEP-BACK-ROUND.md` | ARCHIVE | `STEP-BACK-ROUND.md` | nine-platen demo scheduling-tax census: "stale 5,076 at pool 8, sleeping ~6,100 payload workers per (tile, footing, route)" (:41-42) — no outside hit |
| `holo2/docs/WORKPLAN.md` | ARCHIVE | `WORKPLAN.md` | F-16 "MEASURED at real-sheet scale (3,408 commits, 6,105 records, 2,251 spend rows)" (:299); orchestrator-fold rider "1,283 measured in-flight pushes ... 0 tombstone hits in 8,816 binds" (:301); F2-parity "e029 1,938 vs 1,940 (99.90%...); xerox 1,914 vs 1,930 (99.17%...)" (:562-563) — no outside hit |
| `holo2/tests/README.md` | HISTORY | — | no measured number; its one substantive claim, "the five-verdict gate ... in `holo2/measure/verdicts/`", is cited at `CLAUDE.md:542` |
| `holo2/measure/H4-measurements/README.md` | ARCHIVE | `H4-measurements/README.md` | provenance counts for the trashed `scratch/holo2-demo/` (312 GB / 300 GB trashed, "the ~0.7 MB of it that a tracked document cites", :5-8); "85 files" / "102 state directories" / "78 byte-identical copies" (:63,96-97) — no outside hit |
| `holo2/measure/H4-measurements/reports/holo2-cards-measure-REPORT.md` | ARCHIVE | `H4-measurements/reports/holo2-cards-measure-REPORT.md` | commit-path attribution "1,498,864 from `tilemap.py:121:StoreIndex.build`" (:233); absorb-cost row "207.57 \| 59.3% \| 0.01 \| 1,917 \| 108.3 ms" (:198) — no outside hit |
| `holo2/measure/H4-measurements/reports/holo2-gil-diagnosis-REPORT.md` | ARCHIVE | `H4-measurements/reports/holo2-gil-diagnosis-REPORT.md` | per-kernel GIL/contention table, e.g. "1,278,072" fire count at w2 (:34), "9.32 / 21.42 / 44.46" vs "36.02 / 91.58 / 211.92" (gil-w4 vs gil-w4-sw50, :105-106) — no outside hit |
| `holo2/measure/H4-measurements/reports/holo2-measure-w1exit-REPORT.md` | ARCHIVE | `H4-measurements/reports/holo2-measure-w1exit-REPORT.md` | "837.13s" real-time run (:17,85); wakes/commit "95.57" (:76) — no outside hit |
| `holo2/measure/H4-measurements/reports/holo2-measure-w2exit-REPORT.md` | ARCHIVE | `H4-measurements/reports/holo2-measure-w2exit-REPORT.md` | "8,048,178 vs 8,034,771 total" capture-vs-DPI comparison (:311); "involuntary context switches 95,749" (:308); "79.48" sys time (:383) — no outside hit |
| artefact group: `holo2/measure/H4-measurements/drivers/*` (32 files) + `reports/*.log,*.json,*.out` (81 files) | HISTORY (as one group) | — | every REPORT.md above presents its numbers as finished prose/tables and is readable standalone; the raw run logs/JSON/driver scripts are provenance backup, not required to read the reports, so the group is not needed to keep the archived reports readable |

## 2. Numbers checked

| file | candidate (line) | first outside citation |
|---|---|---|
| `holo2/README.md` | "2701 passed / 0 skipped" (:15) | none |
| `holo2/README.md` | "nine verdicts / 40 checks ... (~91 s)" (:16-18) | none |
| `holo2/README.md` | "twelve of src/holo's fourteen" catalogued identities (:6) | `CLAUDE.md:555` |
| `holo2/tests/README.md` | "the five-verdict gate ... `holo2/measure/verdicts/`" (:8) | `CLAUDE.md:542` |
| `holo2/measure/README.md` | "1,244 commits compared, 476 expansions, 24,571 descriptors, 0 divergences" (:134-135) | none |
| `holo2/measure/README.md` | kernel table "7.27 -> 6.82 ms (1.07x)" (:180) | none |
| `holo2/measure/README.md` | done-gate "3.5% (e029 45/1,273), 3.2% (xerox 42/1,324)" (:477) | `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:575-579`, `seeds/holo2-behaviour-ledger.md:120` |
| `holo2/measure/README.md` | crop_harness_gt smoke "1,940/1,940 (e029) and 1,930/1,930 (xerox)" (:753) | `docs/DONE-GEOMETRY.md:267` (v1's own number, same meaning) |
| `holo2/docs/CATCHUP-PLAN.md` | "26-29/30 e029 gap tiles and 27/48 Xerox gap tiles" F1 rescue (:409-414) | `seeds/holo2-behaviour-ledger.md:138` item (53) |
| `holo2/docs/CATCHUP-PLAN.md` | "9.15%/14.30% of cells they both observe" (:410-411) | `seeds/holo2-behaviour-ledger.md:138` item (56) |
| `holo2/docs/CATCHUP-PLAN.md` | "269 (e029) / 272 (xerox) pose revisions carried ZERO evidence" (:424-426) | `seeds/holo2-behaviour-ledger.md:48` (B38) |
| `holo2/docs/CATCHUP-PLAN.md` | C3 "400,000 random (pitch_px, dpi) pairs, zero divergence" (:119) | `src/holo/receiver/docs/retirement_docs-2026-09/COMMENT-CARRY.md:17345` |
| `holo2/docs/CATCHUP-PLAN.md` | "(42,8) ... oracle ceiling 2.76%" (:434) | none |
| `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md` | "recovered 465,580 bytes with 1,359 certificates" (:18) | `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:593` (number carried via `MEASUREMENTS.md:602,617`) |
| `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md` | "1287 passed in 206.98s" (:470) | none |
| `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md` | "84 passed in 63.96s" (:576) | none |
| `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md` | F-16: "8.05 MB envelope and roughly 2,119 commits ... 57x slower than close-only" (:391-396) | none |
| `holo2/docs/H4-LANES-PLAN.md` | real coarse shares "e029 K 55.4%, hp c3-cmy8 27.0%, xerox c3-cmy7 46-54%, e023c HP sheets 89-92%" (:32-36) | `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:471`, `HOLO2-MAP.md:1360,1813`, `seeds/holo2-behaviour-ledger.md:136` |
| `holo2/docs/H4-LANES-PLAN.md` | "the duplicate-capture provenance rider is DEAD ... duplicate-sha drop (b58b69f)" ruling (:73-75) | none |
| `holo2/docs/H4-LANES-PLAN.md` | "`capture/scale_space.py` is KEPT" ruling (:76-77) | none |
| `holo2/docs/H4-PLAN.md` | "1,930 (Xerox) / 1,940 (HP) of 1,961 ... vs holo2's close-at-solvable ~1,357" (:1006-1008) | `src/holo/receiver/docs/retirement_docs-2026-09/HOLO2-MAP.md:2269,3545` (the 1,357 figure) |
| `holo2/docs/H4-PLAN.md` | OR-9 lattice fix "262,144 Stage-A hypotheses against a 147,456 budget" (:495-497) | `src/holo/receiver/lib/geometry.py:10` (identical fact, in code) |
| `holo2/docs/H4-PLAN.md` | fixture comparisons "4,066 -> 4,081 (default) and 9,001 -> 9,131 (slow)" (:256-257) | none |
| `holo2/docs/H4-PLAN.md` | "10.56 s / 720 MB measured" health-spine re-pin (:645) | none |
| `holo2/docs/H4-PLAN.md` | real-sheet echo "certified 1,356, wall 2,630 s at workers 8, utilisation 93.9%" (:684-686) | none |
| `holo2/docs/H4-W2-PLAN.md` | "holo2/tests (1,596 in 13.4 s)" (:236) | none |
| `holo2/docs/H4-W2-PLAN.md` | RSS ladder "61 MB -> 2,157 MB peak -> 517 MB after" (:288) | none |
| `holo2/docs/H4-W3-PLAN.md` | "unit 1825, oracles 314, verdicts 36" exit snapshot (:32-33) | none |
| `holo2/docs/H4-W3-PLAN.md` | verdicts consolidation "37 checks/143 s -> 36/78 s" (:25-26) | none |
| `holo2/docs/H4-W4-PLAN.md` | "unit 1,864, oracles 314, verdicts 37 at ~81 s" (:30) | none |
| `holo2/docs/H4-W5-PLAN.md` | "39 checks, 81.83 s live vs 80.11 s" (:209) | none |
| `holo2/docs/H5-PLAN.md` | "8,394 commits (was 13,317 ...)" (:396) | none |
| `holo2/docs/H5-PLAN.md` | "6,791 commits (was 11,469, -41%)" (:398) | none |
| `holo2/docs/H5-PLAN.md` | "K=2,913" (:59) | none |
| `holo2/docs/HARDENING-SYSTEMIC-REVIEW.md` | "1287 passed in 206.98s" (:470) | none (incidental, not judged significant) |
| `holo2/docs/HARDENING-SYSTEMIC-REVIEW.md` | "the earlier real run still took 401 seconds at cadence 512" (:434) | `seeds/holo2-behaviour-ledger.md:140` item (77) (same fact, via `MEASUREMENTS.md:662`) |
| `holo2/docs/HARDENING-SYSTEMIC-REVIEW.md` | "the right disposition is side-by-side, opt-in, explicitly provisional" (:44) | none, but unadjudicated (no "RULED" tag) — not treated as a qualifying ruling |
| `holo2/docs/HARDENING-WORKLIST.md` | "899 passed, 35.7 s" / "388 passed, 213.7 s" (:22-24) | none |
| `holo2/docs/HARDENING-WORKLIST.md` | "RULED 2026-08-12: 512 + fsync" (:960) | none |
| `holo2/docs/HARDENING-WORKLIST.md` | "engine 13, capture 17, format 34, diag 67, solve 102" typing-error census (:1210) | none |
| `holo2/docs/HARDENING-WORKLIST.md` | "fires 3,080 -> 2,065 (-33%)" (:423) | `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:727` |
| `holo2/docs/REFACTOR-WORKPLAN.md` | "each subsystem is a quasi-independent library ... reviewable alone, replaceable alone" (:17-19) | none |
| `holo2/docs/STEP-BACK-ROUND.md` | "stale 5,076 at pool 8, sleeping ~6,100 payload workers" (:41-42) | none |
| `holo2/docs/WORKPLAN.md` | F-16 "3,408 commits, 6,105 records, 2,251 spend rows" (:299) | none (the derived ratios — 217.3 KB, 475.9 MB, 23.7x — ARE cited at `ARTEFACTS.md:731`, but not these raw counts) |
| `holo2/docs/WORKPLAN.md` | "1,283 measured in-flight pushes ... 0 tombstone hits in 8,816 binds" (:301) | none |
| `holo2/docs/WORKPLAN.md` | "e029 1,938 vs 1,940 (99.90%...); xerox 1,914 vs 1,930 (99.17%...)" (:562-563) | none |
| `holo2/docs/WORKPLAN.md` | "identical 1,357 / 1,873 / 2,643 echo" (:222) | none |
| `holo2/measure/H4-measurements/README.md` | "312 GB, of which 300 GB were `.prepared` raster caches" (:6) | none |
| `holo2/measure/H4-measurements/README.md` | "85 files" / "102 state directories" / "78 byte-identical copies" (:63,96-97) | none |
| `holo2/measure/H4-measurements/reports/holo2-cards-measure-REPORT.md` | "1,498,864 from `tilemap.py:121:StoreIndex.build`" (:233) | none |
| `holo2/measure/H4-measurements/reports/holo2-cards-measure-REPORT.md` | absorb row "207.57 \| 59.3% \| 0.01 \| 1,917 \| 108.3 ms" (:198) | none |
| `holo2/measure/H4-measurements/reports/holo2-gil-diagnosis-REPORT.md` | "1,278,072" fire count, w2 row (:34) | none |
| `holo2/measure/H4-measurements/reports/holo2-gil-diagnosis-REPORT.md` | "36.02 / 91.58 / 211.92" gil-w4-sw50 row (:106) | none |
| `holo2/measure/H4-measurements/reports/holo2-measure-w1exit-REPORT.md` | "837.13s" wall (:17,85) | none |
| `holo2/measure/H4-measurements/reports/holo2-measure-w1exit-REPORT.md` | wakes/commit "95.57" (:76) | none |
| `holo2/measure/H4-measurements/reports/holo2-measure-w2exit-REPORT.md` | "8,048,178 vs 8,034,771 total" (:311) | none |
| `holo2/measure/H4-measurements/reports/holo2-measure-w2exit-REPORT.md` | "involuntary context switches 95,749" (:308) | none |

## 3. Yield digest — numbers for the archive README

- **RF1 re-read gain.** "+27 (e029) and +32 (xerox)" certificates against the refine-off baseline (e029 1,911→1,938, xerox 1,882→1,914), at cost "+112% wall on e029" (1,127→2,385 s) and "+386% wall on xerox" (719→3,494 s) — `holo2/docs/WORKPLAN.md:578-580` (also `holo2/docs/MEASUREMENTS.md:1129-1136`). First outside citation: `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:560`.
- **Done gate.** v1's "719 of 1,479 committed placements (48.6%) pixel-gated" is a SIMULATED counterfactual; holo2's realized rate is "45/1,273 (3.5%) on e029, 42/1,324 (3.2%) on xerox" — `holo2/measure/README.md:430,477`. The two are explicitly not a ratio (different receivers/denominators). First outside citation: `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:573,577` (§2.4); v1's own 48.6% number is also at `docs/DONE-GEOMETRY.md:267`.
- **Preempted close.** "465,580 bytes with 1,359 certificates" (H3bis, close-preempted) for the same volume v1 needed "1,930" full-harvest certificates for — `holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md:18` (canonical: `holo2/docs/MEASUREMENTS.md:602,617`). First outside citation: `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:593`.
- **Ownership by pose-id order.** Switching the freeze's contested-cell ranking from holo2's `pose-id` order to v1's context-corrected held-out log-loss (tie-broken on pose id) rescued "27/30 e029 and 27/48 Xerox" tiles, zero regressions in 1,910+1,882 — `holo2/docs/kparity/DIVERGENCE-LEDGER.md:65` (also `holo2/docs/CATCHUP-PLAN.md:507`). The controls make it causal: holo2's own pose-id order alone scores "0/30 — worse than random"; the ctx correction is applied by binning each cell in its "owner's 200x200 window", derived from a one-cell context halo — the "observed mask" the window's own context fit reads (`DIVERGENCE-LEDGER.md:66`, "bins from the assembled 64x64 component's own observed mask"). First outside citation: `src/holo/receiver/docs/retirement_docs-2026-09/seeds/holo2-behaviour-ledger.md:138` items (52)-(53).
- **The ranked K gaps**, `holo2/docs/kparity/DIVERGENCE-LEDGER.md` §3, in the ledger's own order:
  1. **F1 — THE FREEZE** (rows 1,2,20,21,25,40,42). Landed. Ownership key: context-corrected held-out log-loss, tie-broken on pose id, ctx applied window-scoped.
  2. **F2 — THE RE-READ** (rank 2, two commits). Landed. **F2a** re-samples a superseded pose's residue through the live pose (rows 4,7,11,13,14). **F2b** same-capture cross-rung pooling (row 3) — labelled NEW WORK, REFUSED as not owed (v1 has no such mechanism).
  3. **F3 — RF1'S GATE AND ITS INPUTS** (rows 5,12,54). Depends on F1's per-(pose,pool) field; not built.
  4. **F4 — PLACEMENT ADMISSION PARITY** (rows 8,17,18,23,24). The rival bar, lattice quantisation, seed rule, straddle re-arm; not built.
  5. **F5 — THE LABEL CHANNEL AND THE REFUSED FIT** (rows 9,10,44). Covered windows retire unposed and contribute no labels; not built.
  6. **F6 — SCHEDULING COMPLETENESS** (rows 15,16,38). The unconditional mop-up-equivalent exhaustion round, loser-hypothesis seed, wide-tier counters; not built.
  7. **F7 — THE PER-RUNG WINDOW LATTICE PHASE** (row 6). GATED — a fresh-state change; needs two measurements first.
  8. **F8 — THE WORD-POOL FIREWALL** (rows 19,22). GATED on a pooled-vs-per-pose rerun; historical incidence 0 conflicts in 21,079/21,508 records.
  9. **F9 — PROVENANCE, AUDIT, OPERATOR SURFACE** (rows 26,27,28,31,32). No yield; not built.
  10. **F10 — PINS ONLY** (rows 37-39,41,43,45-56 + watch rows 29,30). Oracle/differential pins, no behaviour change.
- **The GIL thread ceiling.** "Thread Amdahl ceiling ~= 1.01x — the pool is AT its ceiling" — `holo2/docs/MEASUREMENTS.md:2162`. Cited outside at `CLAUDE.md:545`, `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:728`, `src/holo/receiver/docs/conversion_docs/01-bch.md:239`, `seeds/holo2-behaviour-ledger.md:123`. Superseded by holo3's free-threaded acceptance bar of ">=3x" wall-clock speedup at eight workers on one real sheet, identical payload (`src/holo/receiver/docs/conversion_docs/00-plan.md:93`, item 8). No measured achieved multiple is pinned anywhere yet — `src/holo/receiver/docs/retirement_docs-2026-09/ARTEFACTS.md:838` (G-28) states explicitly that "no byte-identical free-threaded 3.14t decode or wall exists"; state it as ">=3x" (the bar), not an achieved number.
- **The five doc-vs-code contradictions**, `src/holo/receiver/docs/retirement_docs-2026-09/HOLO2-MAP.md`:
  1. **placement-26** (:1199) — holo3's own spec (`13-engine-diag-cli.md:110-115`) "still SAYS the tiers should be gated; the gate was deleted at d399ba3."
  2. **evidence-ownership-13** (:1996) — holo2's `DESIGN.md:670-676` says "scale_space's memmap arm has no production caller to flip" and "derived footings hold no pixels in this tree," but `capture/ingest.py:302` calls `derive_footing_rasters` on every directory ingest, writing into a `w+` memmap.
  3. **dryness-01** (:4284) — holo2's own `DESIGN.md:265` "still calls cold 'gated on quiescence', which is wrong twice over" (the quiescent gate was deleted and replaced by the dryness gate).
  4. **refinement-15** (:2939) — holo3's `API.md:415-416` "still describes `place.done_covers` as ... reading ... `WindowPass.done_cells`," a field `WindowPass` does not have; separately `tiles.done_covers` has no production caller at all.
  5. **pricing-02** (:4704, "DOC CONTRADICTIONS FOUND" at :4612) — `13-engine-diag-cli.md:118` "still declares COLD_LIVE 140 / COLD_REST 150 ... 'verbatim'; the tree has 250/260 and no rework term."

## 4. Totals

archive 38 files (26,338 lines): 18 ruled files (16,845 lines) + 20 decided files (9,493 lines: 15 `holo2/docs`+`holo2/README.md`+`holo2/measure/README.md` at 7,929 lines, plus the 5 `H4-measurements` documents at 1,564 lines).
history 2 files (684 lines): `holo2/tests/README.md` (21), `holo2/docs/HARDENING-SYSTEMIC-REVIEW.md` (663).
plus the artefact group: 113 run-artefact files (32 `drivers/*`, 81 `reports/*.log,*.json,*.out`), ~652 KB, to HISTORY as one group (no archived REPORT.md depends on them for readability).
