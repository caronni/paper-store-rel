# refine_chains — how long the refinement chains are, how far they
# travel, and whether they lose tiles

The measurement `RULINGS.md` D4 ordered, over the archived event streams
and fact snapshots. **No decode was run**; nothing outside this worktree
was written. Compiled 2026-09-04 on branch `rt/d4-refine-guard`.

holo3 refines a window again whenever the certified tiles in its reach
strictly outgrow the basis its last revision was fitted on, and each new
fit starts from the already-revised geometry, so the steps compose. The
ruling kept that chain, added the already-stood guard
(`src/holo/receiver/plugins/refine.py`, `color_refine.py`), and ordered this census
before anyone makes chains cheaper or longer.

---

## 1. The verdict

**Chains are common, short, and small — and chained windows are not the
ones that lose tiles.**

- **23 archived runs, 117,103 refinement fires, 28,010 adoptions.**
  24,656 window-runs adopted at least one revision; **2,788 adopted
  twice and 272 three or more times. The longest chain on the record is
  five** (sheet J, the from-scratch `--complete` run).
- The D4 entry's second-lens figure — *162 windows with more than one
  adoption, 8 with three* — is an order of magnitude low. It was
  measured over seven volumes; the sheet-H stacks, the sheet-J chain and
  the sheet-I resume runs carry most of the chaining.
- **Composed drift, measured where a fact snapshot survives: median
  0.29–0.32 cells and at most 0.954 cells / 0.35° over a chain.** A
  window that adopted once moves a median 0.20 cells and at most 0.15° —
  exactly one step at the search's own angle limit, which is the
  arithmetic checking itself.
- **The lost-tile join finds no consistent over-representation**:
  comparing chained windows against once-revised ones, chained windows
  have the HIGHER share of uncertified addresses in 8 runs and the LOWER
  share in 9 — including every sheet-J run and the seven-capture
  sheet-H stack. The comparison is confounded either way (see §6).
- **The redundancy Germano flagged is real and is not what this guard
  fixes: 76.1% of all refinement fires (89,093 of 117,103) refuse.** The
  worst case is one sheet-J resume at 96.2% refused, 29.8 fires per
  adopting window. The mechanism is the re-arm, not the adoption: a
  refusing fit publishes no basis, so the window stays eligible and
  re-fires on every reach change (`src/holo/receiver/docs/SCHEDULE.md` debt row, pinned
  by `test_h3_plugins_calibrate_refine.py`). The already-stood guard
  refuses at the adoption point and cannot reduce fires.

## 2. What was read, and how

`_sources.py` holds the roster: every holo3 `events.jsonl[.xz]` under
`--evidence-root` (the evidence archive, which keeps the main
checkout's scratch/-era layout the census read; `measure/_evidence.py`,
else `$PAPER_EVIDENCE_ROOT`, refused by name when neither is given)
that `ARTEFACTS.md` §1 names, plus the
`sheetJ-20260902` archive. Runs from the separate `analyzer/` tree are
deliberately excluded — that is a different receiver.

One streaming pass per file collects, per run: `RunOpen` (format,
captures, workers, stream ids), `PoseCommitted` (the accepted
placements, with geometry), `JobDone` for `refine` and `refine.color`
(fires, and an adoption wherever `n_poses > 0`), and `TileOutcome` (the
addresses touched and the addresses certified).

**An adopted revision writes no event of its own.** `place` is the only
writer of `PoseCommitted`, so the stream carries the geometry a chain
DEPARTS from and never the geometry it arrives at; the final standing
pose comes from the run dir's `facts.npz`. Five archived runs have one:
the three page-domain qualification runs (which adopt nothing at all —
a clean null) and the two sheet-J runs. So the chain census covers 23
runs and the drift census 2.

Three more limits, stated rather than worked around:

- A **resume** run replays its placements from the snapshot instead of
  re-committing them, so `I-chain-2`, `I-chain-3` and `J-arch-5` have
  adoption counts but no pose geometry and no lost-tile join.
- A window's tile reach is taken as the tiles its page-cell BOX touches,
  which over-approximates the audited-cell reach `refine.reach_tiles`
  computes — identically for every window, chained or not.
- The **refusal reason never reaches the event stream**: `JobDone`
  carries counts only. The guard's own firing rate will therefore not be
  visible in a future run's events either (§7).

## 3. Chains

`refused` is fires that minted no pose; `1 / 2 / 3+` count windows by
how many revisions they adopted; `longest` is the longest chain in the
run.

<!-- BEGIN census.md chains -->
| run | events | placed | fires | adoptions | refused | adopting | 1 | 2 | 3+ | longest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| e029 | 116749 | 1228 | 932 | 240 | 74.2% | 239 | 238 | 1 | 0 | 2 |
| e029-postfix | 121675 | 722 | 126 | 31 | 75.4% | 31 | 31 | 0 | 0 | 1 |
| xerox-k | 169731 | 836 | 156 | 65 | 58.3% | 64 | 63 | 1 | 0 | 2 |
| xerox-k-postfix | 143638 | 845 | 168 | 67 | 60.1% | 66 | 65 | 1 | 0 | 2 |
| c3-cmy7 | 10695 | 594 | 327 | 168 | 48.6% | 147 | 129 | 15 | 3 | 3 |
| c2-cmy8 | 39368 | 1354 | 2043 | 651 | 68.1% | 617 | 583 | 34 | 0 | 2 |
| c2-cmy7 | 50037 | 1345 | 1269 | 569 | 55.2% | 555 | 542 | 12 | 1 | 3 |
| sheet-I | 339276 | 3266 | 5128 | 1844 | 64.0% | 1712 | 1584 | 124 | 4 | 3 |
| sheetH-maxstack | 1492972 | 8208 | 15919 | 5796 | 63.6% | 5335 | 4910 | 390 | 35 | 4 |
| sheetH-mixed | 539614 | 3838 | 6684 | 2779 | 58.4% | 2535 | 2304 | 218 | 13 | 3 |
| I-chain-1 | 261500 | 3108 | 8049 | 1823 | 77.4% | 1671 | 1532 | 126 | 13 | 3 |
| I-chain-2 | 69789 | 0 | 7334 | 1136 | 84.5% | 1095 | 1054 | 41 | 0 | 2 |
| I-chain-3 | 12198 | 0 | 166 | 0 | 100.0% | 0 | 0 | 0 | 0 | 0 |
| I-chain-4 | 28898 | 579 | 457 | 76 | 83.4% | 61 | 46 | 15 | 0 | 2 |
| pd-base | 79496 | 322 | 0 | 0 | — | 0 | 0 | 0 | 0 | 0 |
| pd-null | 80486 | 350 | 0 | 0 | — | 0 | 0 | 0 | 0 | 0 |
| pd-merged | 52425 | 350 | 0 | 0 | — | 0 | 0 | 0 | 0 | 0 |
| J-run-1 | 49840 | 234 | 1025 | 219 | 78.6% | 174 | 133 | 37 | 4 | 3 |
| J-run-2 | 59911 | 591 | 2572 | 546 | 78.8% | 417 | 312 | 82 | 23 | 4 |
| J-arch-3 | 277955 | 2078 | 8416 | 2024 | 76.0% | 1616 | 1259 | 314 | 43 | 4 |
| J-arch-4 | 520349 | 3222 | 13054 | 2798 | 78.6% | 2511 | 2246 | 245 | 20 | 4 |
| J-arch-5 | 375065 | 283 | 8149 | 306 | 96.2% | 273 | 242 | 29 | 2 | 3 |
| J-complete | 905626 | 7291 | 35129 | 6872 | 80.4% | 5537 | 4323 | 1103 | 111 | 5 |
<!-- END census.md chains -->

Three K runs on the page-domain tree (`pd-*`, 2026-09-02, the newest
e029 numbers and the only ones from `main`) adopt **nothing**, and
`e029-postfix` adopts 31 times with no chain at all. Chaining is a
COLOUR phenomenon on this corpus: of the 2,788 windows that adopted
twice, 2,785 are colour and 3 are K, and **every one of the 272 windows
that adopted three or more times is colour**.

## 4. Composed drift — and where the guard's quantum comes from

Drift is measured between the accepted placement `PoseCommitted` carries
and the final standing pose in `facts.npz`, evaluated at the window's
four page-cell corners and its centre: the largest corner displacement
in cells (divided by the pose's own pitch) and the change in the pose
angle.

<!-- BEGIN census.md drift -->
| run | class | n | median cells | p90 cells | max cells | max deg |
|---|---|---:|---:|---:|---:|---:|
| J-run-1 | once | 133 | 0.1976 | 0.3046 | 0.5194 | 0.15000 |
| J-run-1 | chained | 41 | 0.3193 | 0.5161 | 0.9539 | 0.35000 |
| J-run-2 | once | 312 | 0.2060 | 0.3540 | 0.5430 | 0.15000 |
| J-run-2 | chained | 105 | 0.2914 | 0.4848 | 0.6543 | 0.30000 |
<!-- END census.md drift -->

The `once` rows are the check: a single revision may not exceed
`ANGLE_LIMIT_DEG` 0.15° and 0.25 cells per phase axis, and the measured
maximum is 0.15000° exactly. The D4 entry's estimate — *three composed
steps can move a window about three quarters of a cell and half a
degree* — is confirmed and slightly exceeded in translation: **0.954
cells, 0.35°**, on a window that adopted three times. That is enough to
sample a neighbour's cell, and the failure mode is a lost tile, never a
wrong one (a mis-addressed cell fails its CRC).

**The pose quantum.** The guard compares a candidate against the
window's pose history, and it cannot do that with `==`: a search that
walks away and back does not return the affine it started from, because
the rotation and the origin are recomposed in floating point. holo3 had
no pose quantum to borrow — `store._fold_placement` compares affines
with exact float equality and `data.placement_ordinal` never reads them
at all; `refine.DEDUP_DECIMALS` (12) is a dedup on the search grid's
offsets, not a pose identity. `POSE_TERM_DECIMALS = 6` is holo2's
measured value (`solve/keys.py`, W0-B, ratified 2026-08-15), re-derived
here on holo3's own arithmetic and pinned in
`src/holo/receiver/tests/test_h3_refine_guard.py`:

| walk-back | recomposes bit-exactly | residual, native px | one fine step |
|---|---|---:|---:|
| translation (0.0625 cells) | yes | 0 | 4.375e-01 px |
| rotation (0.05°) | **no** | 8.882e-16 | 6.152e-03 px |

The quantum, 1e-6 native px, sits about nine orders above the
recomposition residual and four below the smallest step the search can
take, so it collapses a walked-back pose onto the geometry it started
from and separates every real fit.

## 5. The lost-tile join

Each tile is given the highest class among the windows whose box covers
it — `chained` (2+ adoptions), `revised` (1), `plain` (0) — so `chained`
reads "a chained window had a hand in this tile". `lost rate` is the
share of that class's TOUCHED addresses that never certified.

<!-- BEGIN census.md lost -->
| run | class | tiles | addresses | certified | lost rate |
|---|---|---:|---:|---:|---:|
| e029 | chained | 20 | 16 | 6 | 0.6250 |
| e029 | revised | 1382 | 1285 | 1026 | 0.2016 |
| e029 | plain | 738 | 660 | 632 | 0.0424 |
| e029-postfix | revised | 261 | 237 | 219 | 0.0759 |
| e029-postfix | plain | 1879 | 1724 | 1719 | 0.0029 |
| xerox-k | chained | 20 | 15 | 14 | 0.0667 |
| xerox-k | revised | 313 | 251 | 220 | 0.1235 |
| xerox-k | plain | 1807 | 1695 | 1691 | 0.0024 |
| xerox-k-postfix | chained | 20 | 15 | 13 | 0.1333 |
| xerox-k-postfix | revised | 348 | 279 | 246 | 0.1183 |
| xerox-k-postfix | plain | 1772 | 1667 | 1663 | 0.0024 |
| c3-cmy7 | chained | 135 | 113 | 92 | 0.1858 |
| c3-cmy7 | revised | 261 | 205 | 196 | 0.0439 |
| c3-cmy7 | plain | 563 | 522 | 522 | 0.0000 |
| c2-cmy8 | chained | 456 | 1248 | 1173 | 0.0601 |
| c2-cmy8 | revised | 1194 | 3228 | 3145 | 0.0257 |
| c2-cmy8 | plain | 402 | 1140 | 1139 | 0.0009 |
| c2-cmy7 | chained | 198 | 182 | 133 | 0.2692 |
| c2-cmy7 | revised | 1358 | 1204 | 944 | 0.2159 |
| c2-cmy7 | plain | 493 | 486 | 483 | 0.0062 |
| sheet-I | chained | 1073 | 3132 | 2817 | 0.1006 |
| sheet-I | revised | 841 | 2283 | 2160 | 0.0539 |
| sheet-I | plain | 231 | 468 | 468 | 0.0000 |
| sheetH-maxstack | chained | 1613 | 4527 | 3284 | 0.2746 |
| sheetH-maxstack | revised | 536 | 1356 | 953 | 0.2972 |
| sheetH-mixed | chained | 1197 | 3414 | 2456 | 0.2806 |
| sheetH-mixed | revised | 948 | 2469 | 1851 | 0.2503 |
| I-chain-1 | chained | 1137 | 3297 | 3049 | 0.0752 |
| I-chain-1 | revised | 751 | 2043 | 1951 | 0.0450 |
| I-chain-1 | plain | 257 | 543 | 543 | 0.0000 |
| I-chain-4 | chained | 96 | 11 | 10 | 0.0909 |
| I-chain-4 | revised | 84 | 5 | 3 | 0.4000 |
| pd-base | plain | 2053 | 1841 | 1357 | 0.2629 |
| pd-null | plain | 2068 | 1856 | 1360 | 0.2672 |
| pd-merged | plain | 1809 | 1669 | 1356 | 0.1875 |
| J-run-1 | chained | 265 | 537 | 228 | 0.5754 |
| J-run-1 | revised | 214 | 384 | 129 | 0.6641 |
| J-run-2 | chained | 256 | 501 | 202 | 0.5968 |
| J-run-2 | revised | 169 | 333 | 98 | 0.7057 |
| J-arch-3 | chained | 1471 | 3207 | 1839 | 0.4266 |
| J-arch-3 | revised | 906 | 1584 | 672 | 0.5758 |
| J-arch-4 | chained | 980 | 1650 | 637 | 0.6139 |
| J-arch-4 | revised | 1650 | 1579 | 232 | 0.8531 |
| J-arch-5 | chained | 233 | 535 | 302 | 0.4355 |
| J-arch-5 | revised | 391 | 807 | 412 | 0.4895 |
| J-complete | chained | 3275 | 8517 | 6302 | 0.2601 |
| J-complete | revised | 961 | 2244 | 1519 | 0.3231 |
<!-- END census.md lost -->

`census.md` beside the artefacts carries the empty rows this table
drops. Comparing `chained` against `revised` — the like-for-like
comparison, since both classes are windows refinement chose to work —
chained is worse in 8 runs and better in 9. Against `plain` chained is
worse almost everywhere, and that comparison says nothing (§6).

## 6. What this does not say

**The lost-tile join cannot separate cause from selection.** Refinement
fires exactly where certified tiles are appearing next to uncertified
ones, and it fires AGAIN when more of them appear, so a chained window
is by construction a window sitting in hard material. `chained` vs
`plain` therefore measures where refinement is scheduled, not what it
costs. `chained` vs `revised` narrows that a great deal and comes out a
coin flip. Nothing here supports the predicted failure mode, and nothing
here would have detected it if it were half this size.

**Two runs of one sheet is the whole drift record.** Every other
adopting run in the archive was kept as an event stream without its
`facts.npz`. Any future run that keeps its snapshot widens this table
for free.

**No decode was run and none is proposed here.** The census is arithmetic
over files already on disk.

## 7. Open, for the record

- **The guard is invisible in the event stream.** A refused revision is
  a `JobDone` with `n_poses = 0`, indistinguishable from a failed
  adoption gate; the `Revision.reason` never leaves the plugin. So this
  instrument cannot say how often the already-stood guard fires on a
  real sheet, and neither can a future run's events. Carrying the reason
  would be a change to a pinned event family — a separate decision.
- **The 76.1% refusal rate is the scheduler question**, and the guard
  does not touch it. The lever named in the record is the re-arm: a
  refusing fit publishes no basis, so eligibility persists.
- The three `pd-*` runs adopt nothing at all. Whether the newest tree
  simply refines less on K, or those runs stopped earlier, is not
  answered here.

## 8. Re-running

    cd <worktree>
    PYTHONPATH=src:. env/bin/python -m measure.refine_chains.census \
        --evidence-root <evidence> --out build/refine-chains
    PYTHONPATH=src:. env/bin/python -m measure.refine_chains.census \
        --run sheet-I --evidence-root <evidence> --out build/refine-chains

About seven minutes for the whole roster (5,797,293 events across 23
runs), one process, one stream at a time. Artefacts land in
`--out` (`census.json`, `census.md`);
the tables above are pasted from `census.md`.

2026-10-09: inputs renamed to the published archive paths — and this census has none. Every
event stream and fact snapshot in `_sources.py`'s roster (`holo3-overnight-events/`,
`sheetI-20260831/`, `page-domain-qual/`, `sheetJ-20260902/`, the two J run dirs) is tier delete
(event journals and fact snapshots excluded by rule); only the runs' `argv`/`tree`/`report.json`
identity files are published (under `034-sheet-i-full-readout/records/runs/`,
`035-sheet-j-confetti/records/runs/`, `029-holo-v1-first-print/c2-r0700-ink/records/runs/page-domain-qual/`).
Pointed at the published archive, `census` finds no run and refuses by name; the tables above
are the record.
