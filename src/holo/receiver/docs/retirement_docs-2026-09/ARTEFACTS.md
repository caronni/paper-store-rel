# ARTEFACTS — the measurement record the maps cite

Plan of record `claude-plan.md` §2 principle 3: **no receiver runs.** Every
yield or cost number in `HOLO2-MAP.md`, `HOLO1-MAP.md` and `RULINGS.md`
comes from an artefact listed here. A number with no artefact is a GAP (§3)
and the row that wants it is marked UNPROVEN.

Compiled 2026-09-02 on `main` @ `29d9a8d` by reading each artefact. Every
path below was `ls`-ed or opened; paths that the plan names and that do not
exist are called out in Appendix B.

---


> Path note (2026-09-05): every `holo2/…` path in this file names the tree as it stood at `06a8129`; holo2 was deleted at `a805888` and its documents of record live under `docs/archive/holo2/` (README.md there is the index). `git show 06a8129:holo2/<path>` reaches any file.

## How to cite

| artefact kind | citation form | example |
|---|---|---|
| markdown / python / text | `path:line` | `src/holo/receiver/docs/conversion_docs/PARITY.md:11` |
| JSON, keyed object | `path` + the key path in `→` form | `src/holo/receiver/docs/conversion_docs/parity.json → "7".holo3.n` |
| JSON, array of records | `path` + the record's own id field | `…/xerox-c2-cmy8-results.json → cases[case_id="xerox-c2-cmy8-c01"]` |
| JSONL ledger | `path` + the row's identifying field | `src/holo/receiver/docs/conversion_docs/overnight/ledger.jsonl → step="sheet-I"` |
| holo3 `events.jsonl[.xz]` | `path` + event `type` + the filter | `…/events-resume-3.jsonl.xz → TileOutcome result=certified, deduped on (page,ty,tx,stream_id)` |
| holo3 `report.json` | `path` + top-level key | `scratch/sheetI-20260831/report-resume-3.json → close.verified` |
| a file inside the salvage tarball | `scratch/holo3-worktree-salvage/small-artifacts.tar.gz!<member>` | `…!scratch/crop-parity/sheet-I/cases.json` |
| an archived holo1 `.state` | path + "size/mtime only; readable only through `src/holo/receive/state_codec.py`" | — |


> **2026-10-09 (evidence-archive line).** `scratch/holo3-worktree-salvage/small-artifacts.tar.gz`
> (36 MB, 370 members, written 2026-09-02) was judged an intermediate work product of the
> holo3 conversion — tools, parity sidecars and run reports of the deleted `paper-holo3`
> worktree, not evidence of anything printed or scanned — and is TRASHED with the rest of
> `scratch/` (owner's ruling, docs/EVIDENCE-ARCHIVE-2026-10-08.md §1). The conversion
> harness it served is pinned by the holo3 tags. Every `…!<member>` citation in this
> document and in the conversion_docs therefore resolves to nothing on disk from that date;
> the numbers those members supported stand as recorded here and in
> `src/holo/receiver/docs/conversion_docs/`.

Two rules for map writers:

1. **Say which receiver and which tree.** Numbers on the same volume differ
   by receiver (holo1 / holo2 / holo3) and by tree (holo3 moved eight arms
   in 24 h on 2026-08-31 and the earlier baselines were explicitly
   superseded — `src/holo/receiver/docs/conversion_docs/PARITY.md:661-671`). Every row below
   carries the tree stamp where one was recorded.
2. **Never cite a number across the supersession line without saying so.**
   `PARITY.md` / `parity.json` / `GAPS.md` / `POST-FORENSICS.md` /
   `crop-batteries/` describe the receiver of **2026-08-30 evening**.

---

## 0. Where the record physically lives

| home | tracked? | what | size |
|---|---|---|---|
| `src/holo/receiver/docs/conversion_docs/` | yes | the holo3 build + parity record: 14 specs, `PARITY.md`, `parity.json`, `GAPS.md`, `POST-FORENSICS.md`, the 08-31 ARMS/MEASUREMENTS/RULINGS/OPEN ledgers, `crop-batteries/`, `d6-baseline/`, `overnight/` manifests+ledgers | ~2 MB |
| `holo2/docs/` | yes | holo2's `MEASUREMENTS.md`, `measurements-h3.json`, `kparity/` | ~1.6 MB |
| `docs/` | yes | v1's normative + measurement records (`RECEIVE-DESIGN*`, `COLOR-UPLIFT-*`, `PLANE-FIELDS.md`, `INDEPENDENT-PLANES.md`, `PAYLOAD-MEASUREMENTS.md`, `PHASED-SCHEDULE.md`, `TOOLBOX-INVENTORY.md`, `DONE-GEOMETRY.md`) | — |
| `measure/*/README.md` | yes | ten instrument records, each carrying its own verdict + numbers | ~160 KB |
| `experiments/NNN-*.md` | yes | the normative print-day logs (029–034) | — |
| `scratch/` | **NO — gitignored** | the raw run dirs: events, reports, argv, tree stamps, panes, and the 28 archived holo1 `.state` files | ~200 GB |
| `scratch/holo3-worktree-salvage/small-artifacts.tar.gz` | no | **the only surviving copy** of the deleted `paper-holo3` worktree's `_distill/verify/` (parity, overnight, gap-analysis, acceptance run reports) and every crop-parity per-case sidecar | 36 MB, 370 members, written 2026-09-02 15:56 | *(tarball trashed 2026-10-09; see the dated note below the citation-form table)*
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/` | yes (new) | this campaign's Phase-0.3 certificate freeze, in progress | — |

**The deleted worktree.** `<checkout>` **does not exist**
(`git worktree list` shows only `paper` and `paper-identity`). Every
`_distill/…` and `scratch/crop-parity/…` path printed inside `PARITY.md`,
`parity.json`, the crop-battery manifests, `acceptance.json` and the
overnight ledgers is a **dead path**. Their content survives only as (a) the
tracked summaries in `src/holo/receiver/docs/conversion_docs/`, and (b) the salvage tarball.
Cite the tarball member, never the `paper-holo3` path.

---

## 1. Per volume

### 1.0 Volume roster

| volume | format id | tiles × streams | payload | payload sha (16) |
|---|---|---|---|---|
| e029 HP K | `L:c2-r0700@3392x2368` | 53×37 = 1961 × 1 | 465,580 B | `e5021f8d099587c3` |
| xerox K | `L:c2-r0700@3392x2368` | 1961 × 1 | 465,580 B | `e5021f8d099587c3` |
| xerox c3-cmy7 | `L:c3-cmy7-p120-v0@2240x1536` | 35×24 = 840 × 1 | 301,600 B | `4f68dbf932324aa8` |
| xerox c2-cmy8 | `L:c2-cmy8-p120-v0@3328x2304` | 52×36 = 1872 × 3 = 5616 | 718,413 B | `f13c34db6c96796e` |
| xerox c2-cmy7 | `L:c2-cmy7-p120-v0@3328x2304` | 1872 × 1 | 686,859 B | `5963b9d16abca48d` |
| hp c2-cmy7 | `L:c2-cmy7-p120-v0@3328x2304` | 1872 × 1 | never recovered | — |
| e030 hp c2-cmy8 | `c2-cmy8-p120-v0@3328x2304` | 5616 | never recovered | — |
| e030 hp c3-cmy8 | `c3-cmy8-p120-v0@2240x1536` | 840 × 3 = 2520 | never recovered (663 certs) | — |
| sheet I | `L:c2-cmy8-r0700-p120-x1@3392x2368` | 1961 × 3 = 5883 | 1,798,761 B | `2445b95db5b49bf3` |
| sheet H | `L:c2-cmy8-r0850-p120-x1@3392x2368` | 1961 × 3 = 5883 | never closed (K 5277) | — |
| sheet J | `c2-cmy8-r0547@53x37` | 1961 × 3 | open (K 4020) | — |
| sim K | `c3-k-r0550@7x7` | 49 | 6,000 B | `59495601d00fa781` |
| sim colour | `c3-cmy8-r0550x0550x0547@10x10` | 279 | 20,000 B | `ddf7acebcd86ae52` |

Roster sources: `src/holo/receiver/docs/conversion_docs/verify/acceptance.json → steps[]`
(format, dpi, payload bytes + sha per volume);
`src/holo/receiver/docs/conversion_docs/parity.json → <step>.holo1.format_row_id`;
`src/holo/receiver/tests/_h3_sims.py:118,122` (the two sim shas).

### 1.1 e029 HP K — `L:c2-r0700@3392x2368`, HP M281, Canon 4800 grey

| artefact | date | receiver / tree | what it measures | how to read |
|---|---|---|---|---|
| `experiments/029-holo-v1-first-print.md` | print 2026-08-04, scan 21:08 (`:51-52`) | **holo1** — invocation `./confetti.py decode … --state <dir>/receive.state` at `:57-59` | **`## RESULTS` `:71-107`**: close + bytes `:73`; **tiles 1940/1961 = 98.93%** (+5 from selective BP150), 21 failed, 0 conflicts `:74-76`; surplus 584 symbols, single-sheet q≈0.98 `:76-77`; **64.7 b/mm² field / 59.7 per full A4** (e016 55.1, +17%) `:78-81`; footprint 99.8% (7,818,243/7,836,156), placements 1451 acc / 161 unres / 0 quar, words 229 match / 531 insuff / 125 refused, LDPC 2933 calls (3279 folded) `:82-85`; K=1356 of N=1961 `:42-43`; **failure geography: 11 extreme-column, 9 in the row-42 band, 1 singleton (48,32) — banding, not margin** `:95-107`. Second block `## 029.2` `:159-186` = the done-geometry census, no new decode | `path:line` |
| `experiments/029-holo-v1-first-print/{census_done_geometry.py,DONE-GEOMETRY-CENSUS.json}` | 2026-08-05 | — | the census driver and its output (both exist) | JSON / python |
| `docs/DONE-GEOMETRY.md:244-302` (§8a) | 2026-08-05 | holo1 | **the only measured done-gate section**: 719 of 1,479 committed placements (48.6%) pixel-gated; per level l00 0/227, l01 4/315, l02 236 (75%), l03 236 (75%), **m00 243 (87%)** of 279 with windows 398/440, colds 136/160, word-rests 136/160; **r00–r03 zero — the gate never touches live refinement work**; l02+l03 spent 630 placements to mint 11 certificates; the m00 `--complete` tail spent 440 windows / 160 priced colds / 160 rest-word decodes to mint **2**; gated windows minted **zero** certificates, provably | `path:line`; per-level table `:257-265`, totals `:267-273` |
| `.claude/memories/e029-holo-v1-first-print.md:10-11,24-28` | 2026-08-04 | holo1 | the condensed record: 465,580 B, 1940/1961 = 98.9%, +5 BP150, surplus 584, 64.7 / 59.7 b/mm² | `path:line` |
| `scratch/e028/holo-c2-r0700-q07-ink-counting/receive.state` | 2026-08-04, 8,206,654 B | holo1 | the archived session: 1940 certificates, close `verified` | size/mtime only; `state_codec.py` or `measure/parity/extract_holo1_certs.py` |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/e029-hp-c2-r0700-k.json` | 2026-09-02 16:50 | holo1 (frozen) | **n_certificates 1940**, per-stream `{main:1940}`, close `payload_sha256 e5021f8d…`, `payload_length 465580`, `policy_id`, `certificate_frontier_sha256 0aaee541…`, state size/mtime, extraction peak RSS + wall | JSON; keys `n_certificates`, `addresses`, `per_stream`, `close`, `policy_id`, `format_row_id`, `tree_sha` |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:29-41` (`## step 2`) | 2026-08-29 | holo1 vs holo3 `--complete` | **1940 / 1940 / matched 1940 / miss 0 / extra 0**; holo3 wall 655.7 s, child max RSS 12.75 GiB; TileOutcome rows 7375 (`below_attempt_floor` 852, `certified` 1940, `attempted_failed` 4583) | `path:line`; machine copy at `parity.json → "2"` |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:456-470` (`### post step 2`) | 2026-08-30 | holo3 HEAD `f4a18ea` | **post 1938 — FAILED the pre-registered "stays 1940"**, lost 2 (both at ty=42, the HP weak-horizontal band), gained 0; wall 761.9 s (1.16×), peak 15.35 GiB; row fires `refine` 106→406, `revisit` 0→124, all crediting **0** certificates | `path:line` |
| `src/holo/receiver/docs/conversion_docs/crop-batteries/crop-battery-e029.md` + `e029-results.json` | 2026-08-30 04:29 | holo1 tree `3537128d0084` vs holo3 tree `e7ad566755e5` | 1 case, 2 target addresses; **zero wrong certificates**; address-frame check passes; both sides agree on 2, disagree on 0; walls holo1 421.2 s (adopted sidecar) vs holo3 80.6 s | md for prose, JSON for `gap_counts`, `aggregates`, `cases[]` |
| `scratch/holo3-overnight-events/e029-events.jsonl.xz` (691 KB) and `e029-postfix-events.jsonl.xz` (651 KB) | 2026-08-30 | holo3 | the full event streams of the baseline and post-fix harvests | `xz -dc … \| jq` — see Appendix A |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger-run3.jsonl → step="e029"` | 2026-08-30 | holo3 | wall 1081.9 s, peak RSS 5.84 GiB, `payload_sha256 e5021f8d…`, `sha_ok true` | JSONL, one object per step |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger.jsonl → step="e029-postfix"` | 2026-08-30 | holo3 | wall 710.0 s, peak RSS 4.66 GiB | JSONL |
| `scratch/page-domain-qual/` (3 run dirs + 3 logs + 3 `.bin`) | **2026-09-02 01:05–01:20** | holo3, page-domain merge | the newest e029 numbers on the current tree: base `1357` certs / 2517.3 cpu-s; merged with `--pages 1` (null) `1360` / 2557.4 cpu-s; merged default (133 possible pages) `1356` / 1639.8 cpu-s — **all three VERIFIED `e5021f8d…`**, 465,580 B | `*.log` = the diag summary + per-plugin table; `*-run.NNNNN/{argv,tree,events.jsonl,report.json,facts.npz,pane-*.png}` |
| `measure/calibration/` (`README.md`, `e9_k.py`, `_arms.py`, `_run.py`, `_reduce.py`, `_inputs.py`, `_figures.py`) + `docs/INDEPENDENT-PLANES.md:1155-1342` (§2.13) + `docs/TOOLBOX-INVENTORY.md:1273-1317` (§6.13) + `scratch/plane-fields/p2/e9/` | 2026-08-23 | v1 instrument | **E9: LOCAL vs PAGE-GLOBAL detector calibration over e029's complete 21-tile residue — a sharp measured NEGATIVE.** ZERO certificates, every arm, both lanes, all 21 tiles (`INDEPENDENT-PLANES.md:1223`); arm deltas H1 217k/336k labels, 15/25 tiles, 0/0 certs, −0.79/−1.04 pp; H2 389k/561k, 28/42, 0/0, −0.96/−1.09 pp (`:1178-1179`); 651 s wall, peak RSS 5.6 GB (`:1181`). Also records the shipped K granularity: **photometry per window, calibration per window, context page-global, and neither head has ever seen a certified payload cell as a label** (`:1193-1195`) | md + `path:line`; artefacts `e9-k.json` (46 KB), `e9-k-raw.json` (2.1 MB), one PNG per lane |
| `measure/crop_parity/cases/e029/{cases.json,cases-census.md}` | 2026-08-30 | — | the crop manifest: bbox, tiles, targets, controls, capture fits | JSON keys listed in Appendix A |

*Note:* the page-domain-qual runs are the **only e029 numbers on the
post-2026-08-31 tree** and the only ones from `main` rather than the deleted
worktree. `src/holo/receiver/docs/PAGE-DOMAIN.md` (v1.0, 2026-09-01, tracked) is the
design; `src/holo/receiver/docs/PAGE-DOMAIN-WORKPLAN.md` its workplan.

### 1.2 xerox K — `L:c2-r0700@3392x2368`, AltaLink C8245, Canon 4800 grey

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `experiments/032-xerox-altalink-payload-volumes.md:99-108` | 2026-08-05/06 | holo1 (log written from the states' `.diag/status.json` + `report.json`, `:19-22` — the log author did not run the decodes) | **1,930 certificates** (+1 BP150), 31 failed, 3,125 LDPC calls; mop-up drops 10,498 (flips 1,942) `:102-103`; **1,930/1,961 = 98.4%** vs e029's 98.9% — **the two engines land within 0.5 pp on K** `:106-108`, `:226-228`; close VERIFIED 465,580 B `:104`; footprint 99.8%, 2713 acc / 82 unres, words 1027/749/185 `:99-101` |
| `scratch/in/holo-xerox-c2-counting-receive.state` (9,429,553 B, 2026-08-05) + `…-recovered.bin` (465,580 B) | 2026-08-05 | holo1 | the print-day counting session |
| `scratch/color-uplift/full/xerox-c2-k-pkfinal/receive.state` (9,429,565 B, 2026-08-09) + `scratch/color-uplift/runs/address-pkfinal-xerox-c2-k.json` + `cache/xerox-c2-k/` | 2026-08-09 | holo1 PK-FINAL | the colour-uplift re-decode of the same scan; `docs/COLOR-UPLIFT-MEASUREMENTS.md:3013` (§14.2 row 4) records **certificate-ID set identical archived↔candidate**; B2 cost row `:3158`; run ledger `:3816` |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/xerox-c2-k-counting.json` | 2026-09-02 | holo1 (frozen) | **1930**, close `e5021f8d…` / 465,580 B, `certificate_frontier_sha256 dc489fbc…` |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:206-237` (`## step 5`) | 2026-08-29 | holo1 vs holo3 | **1930 / 1924 / matched 1922 / miss 8 / extra 2 (0.41%)** |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:520-546` (`### post step 5`) | 2026-08-30 | holo3 `f4a18ea` | **PARTIAL** — 1927, miss 8→5 (recovered 3, lost 0, two of them tx=0 rescue-column); wall **0.68× baseline** (the only volume that got faster) |
| `src/holo/receiver/docs/conversion_docs/GAPS.md:82-160` | 2026-08-29 | both | **the sharpest mechanism finding in the record**: both receivers fail almost entirely in columns 0/21/34/36; 29 of the failures are the same tiles; v1 won only **18** of its 1,930 certificates by refinement and **all 18 are in column 0**; holo3 certified **13 of those 18 with no refinement**, 7 at the finest level against a 4.7% finest-level population; **the 5 it did not get are 5 of the 8 misses** |
| `src/holo/receiver/docs/conversion_docs/GAPS.md:334-360` | 2026-08-29 | vs holo2 | cross-checks the same sheet against `holo2/docs/CATCHUP-PLAN.md` ~300–560: holo2's gap 48 → 19 after two fixes; **holo3's gap is 8**; the three tiles holo2 got that v1 missed are named and adjudicated |
| `src/holo/receiver/docs/conversion_docs/crop-batteries/crop-battery-xerox-k.md` + `xerox-k-results.json` | 2026-08-30 04:42 | holo1 `3537128d0084` vs holo3 `e7ad566755e5` | 5 cases; full-sheet `post-5` 1930/1927/both 1925, miss 5, gain 2, neither 29; **zero wrong**; agree 7 / disagree 0; walls holo1 395.4 s vs holo3 145.4 s |
| `scratch/holo3-overnight-events/xerox-k-events.jsonl.xz` (904 KB), `xerox-k-postfix-events.jsonl.xz` (765 KB) | 2026-08-30 | holo3 | event streams |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger-run3.jsonl → step="xerox-k"` / `ledger.jsonl → step="xerox-k-postfix"` | 2026-08-30 | holo3 | 1447.8 s / 4.81 GiB; 952.1 s / 7.84 GiB |
| `scratch/angle-residue/` (1.4 GB) + `scratch/sheetI-20260831/v2v3-placement-residue.md` | 2026-08-31 | **holo2 vs holo3 head-to-head** | see §2 "placement" — the material is a 1000×1000-cell crop of *this* sheet's scan (`manifest.json → source`) |

### 1.3 xerox c3-cmy7 — `L:c3-cmy7-p120-v0@2240x1536`

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `experiments/032-xerox-altalink-payload-volumes.md:112-122` | 2026-08-05/06 | holo1 | **720 certificates** (+8 BP150), 120 failed, 3,766 LDPC calls; mop-up drops 119,499 (flips 35,882) `:118-119`; **720/840 = 85.7%** `:122`; close VERIFIED 301,600 B `:120`; footprint 99.6%, 808 acc / 18 unres, words 722/94/24; lane `r03-12ppc-2400dpi` — **the only 2400 dpi capture of the five** `:112-117` |
| `scratch/in/holo-xerox-c3-cmy7-counting-receive.state` (138,019,450 B) + `…-recovered.bin` (301,600 B) | 2026-08-06 | holo1 | print-day counting session |
| `scratch/color-uplift/full/xerox-c3-cmy7-pkfinal/receive.state` (51,753,007 B, 2026-08-09) + `cache/`, `feature-library/`, `regmap/`, `runs/*xerox-c3-cmy7*` | 2026-08-09 | holo1 PK-FINAL | **the state that holds the best-on-record 810** (`PARITY.md:47`; `docs/COLOR-UPLIFT-MEASUREMENTS.md:3010` §14.2 row 1: **720 → 810, +91/−1**). **This is the campaign's canary volume** — its measurement threads run through `COLOR-UPLIFT-MEASUREMENTS.md` §4.4/§4.5 `:183-247`, §5.6 `:687-759`, §10.4 `:1947-1964`, §11.2 `:2113`, §13.5 `:2722-2822`, §13.11 `:2925-2956`, §14.5 `:3152`, §15.4/§15.5 `:3456-3630` |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/xerox-c3-cmy7-counting.json` | 2026-09-02 | holo1 (frozen) | **720**, close `4f68dbf9…` / 301,600 B |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:42-107` (`## step 3`) | 2026-08-29 | holo1 vs holo3 | 720 / 786 / matched 716 / **miss 4** / extra 70; holo3 wall 891.9 s, RSS 15.82 GiB; the four missing addresses are printed verbatim at `:66-71` |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:489-513` (`### post step 3`) | 2026-08-30 | holo3 `f4a18ea` | **EXCEEDED** — 815, miss 4→0 (exact parity with holo1); peak RSS 15.8→39.4 GiB; the gain sits entirely in `tiles/scan` (786→815) on 3,399→3,840 attempts with the retry row minting **zero** — attribution UNRESOLVED (`PARITY.md:449-455`) |
| `src/holo/receiver/docs/conversion_docs/GAPS.md:174-217` | 2026-08-29 | both | the four missing tiles, tile by tile |
| `src/holo/receiver/docs/conversion_docs/crop-batteries/crop-battery-xerox-c3-cmy7.md` + `xerox-c3-cmy7-results.json` | 2026-08-30 15:51 | holo1 `3537128d0084` vs holo3 `a6f43747064e` | 8 cases, 95 gain targets; **zero wrong**; agree 91 / disagree 4; walls holo1 2,978.3 s vs holo3 710.8 s |
| `scratch/holo3-overnight-events/c3-cmy7-events.jsonl.xz` (105 KB) | 2026-08-30 | holo3 | event stream |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger-run3.jsonl → step="c3-cmy7"` | 2026-08-30 | holo3 | 637.1 s, 9.24 GiB, `sha_ok true` |

### 1.4 xerox c2-cmy8 — `L:c2-cmy8-p120-v0@3328x2304` (the first CMY8 volume ever read off paper)

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `experiments/032-xerox-altalink-payload-volumes.md:81-92` | 2026-08-05/06 | holo1 | **5,370 certificates** (+80 BP150), 246 failed, 0 low, 5,370 divergences; 14,476 LDPC calls (14,825 folded); mop-up drops 214,924 (flips 74,122) `:86-88`; ceiling ~5,616 → **95.6%** `:92`, `:174`, `:198-199`; close VERIFIED 718,413 B `:89`; footprint 99.7%, 1890 acc / 56 unres / 0 quar, words 1198/411/263/0 `:83-85`; lane `r03-16ppc-4800dpi`, level 12/12, 16 px/cell `:81` |
| `scratch/in/holo-xerox-c2-cmy8-q05-counting-receive.state` (1,309,153,068 B) + `…-recovered.bin` (718,413 B) | 2026-08-06 | holo1 | print-day counting session |
| `scratch/color-uplift/full/xerox-c2-cmy8-pkfinal/receive.state` (1,266,752,808 B) + `cache/`, `feature-library/`, `regmap/` siblings | 2026-08-10 | holo1 PK-FINAL | **holds the best-on-record 5466** (`PARITY.md:113`; `docs/COLOR-UPLIFT-MEASUREMENTS.md:3012` §14.2 row 3: **5,370 → 5,466, +98/−2**). This is the campaign's **B1 non-regression volume**: §5.8 `:804-821`, §9.5 `:1630-1667`, §9.9 `:1755-1785`, §11.2 `:2114`, §14.5 `:3154`, §15.5 `:3574`; the A4b conditioning-tier law that read +19 here and finished at net −5 is `docs/RECEIVE-DESIGN.md:1051-1054` |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/xerox-c2-cmy8-q05-counting.json` | 2026-09-02 | holo1 (frozen) | **5370**, close `f13c34db…` / 718,413 B |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:108-205` (`## step 4`) | 2026-08-29 | holo1 vs holo3 | 5370 / **5422** / matched 5334 / miss 36 / extra 88 (0.67%) |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:514-519` (`### post step 4`) | 2026-08-30 | holo3 `f4a18ea` | **NO MEASUREMENT** — killed at the 58 GiB ceiling at BOTH `--workers 8` (60.51 GiB) and `--workers 6` (60.24 GiB); worker count is not the driver and the reduced-worker fallback cannot rescue this volume on this machine (`PARITY.md:451`) |
| `src/holo/receiver/docs/conversion_docs/GAPS.md:289-333` | 2026-08-29 | both | the 36 misses / 88 extras |
| `src/holo/receiver/docs/conversion_docs/crop-batteries/crop-battery-xerox-c2-cmy8.md` + `xerox-c2-cmy8-results.json` | 2026-08-31 00:23 | holo1 `3537128d0084` vs holo3 `f5d7c0e2efc8` | 16 cases, 124 targets; **zero wrong**; agree 102 / **disagree 22** (the largest disagreement in the battery set); per-class `gain` n=88 reproduces holo1 14 / holo3 55; walls holo1 7,613.3 s vs holo3 2,677.9 s |
| `scratch/holo3-overnight-events/c2-cmy8-events.jsonl.xz` (327 KB) | 2026-08-30 | holo3 | event stream |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger.jsonl → step="c2-cmy8"` | 2026-08-30 | holo3 | 1709.9 s, peak RSS **29.67 GiB**, exit 0 |

### 1.5 xerox c2-cmy7 — `L:c2-cmy7-p120-v0@3328x2304` (the print-frozen negative control)

Two distinct records that must never be conflated:

* the **e032 print-day counting run**, which FAILED (83 of 1,872 tiles, 1,789 LDPC failures);
* the **colour-uplift PK-FINAL** run, which CLOSED at 686,859 B with 1,559 certificates.

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `experiments/032-xerox-altalink-payload-volumes.md:128-139` | 2026-08-05/06 | holo1 | the FAILURE: footprint **99.8%**, 1472 acc / 32 unres, words **1,489 match** / 262 insuff / 121 refused / 0 conflict `:128-131`; LDPC 28,702 calls (29,131 folded), **83 certificates** (+5 BP150), **1,789 failed**; mop-up drops 413,389 (flips 125,525) `:132-133`; fountain 83/920 K over 1 block, metadata trusted, close deferred; **83/1,872 = 4.4%** `:134-135`, `:139`, `:174`. **STALE ON ITS OWN HEADLINE** — see GAP G-06 |
| `scratch/in/holo-xerox-c2-cmy7-counting-receive.state` (**1,664,114,915 B**, 2026-08-06) | 2026-08-06 | holo1 | that failed session; **no `recovered.bin`** (`032:44-45`, `:265`) |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/xerox-c2-cmy7-counting.json` | 2026-09-02 | holo1 (frozen) | **83**, close `status: open` — confirms the failure from the state itself |
| `scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/receive.state` (**701,559,473 B**, 2026-08-10) + `cache/`, `regmap/` siblings | 2026-08-10 | holo1 PK-FINAL | **the state `PARITY.md:240` uses**: 1,559 certificates, closed 686,859 B. **Not in the plan's Appendix-A list of 17** (Appendix B) |
| `docs/COLOR-UPLIFT-MEASUREMENTS.md:3026` (§14.2 row 6), `:3035-3078` (§14.3), `:3204` (B4), `:3281` (§14.7), run ledger `:3820` | 2026-08-31 | holo1 | **the campaign headline: 83 → 1,559 certificates, +1,476 / −0, a STRICT SUPERSET; close VERIFIED at 686,859 bytes** (`:3048`) — "a volume that had never been recovered; no archived `recovered.bin` exists". Also the PK6/A2 PRIMARY capture (`:3574`) |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:238-321` (`## step 6`) | 2026-08-29 | holo1 vs holo3 | 1559 / 1586 / matched 1537 / **miss 22 (1.41% — FLAGGED)** / extra 49 |
| `src/holo/receiver/docs/conversion_docs/PARITY.md:547-615` (`### post step 6`) | 2026-08-30 | holo3 `f4a18ea` | **FAILED** — regressed to miss 26 (recovered 8, **lost 39**); retry attempts 1,028 → 23,881 (23×) minting 13 certificates; wall **3.1× (8,487 s)** — crossed the 2.5× tripwire and was logged not killed; peak 57.96 GiB, within 0.04 GiB of the kill line |
| `src/holo/receiver/docs/conversion_docs/POST-FORENSICS.md:296-329` (`### B.2`) | 2026-08-30 | holo3 | the 39 losses adjudicated |
| `src/holo/receiver/docs/conversion_docs/GAPS.md:218-288` | 2026-08-29 | both | the 22 misses / 49 extras; and the bound on the supplemental photometry arm's share (at most 15 sheet-wide, 2 of 22 excluded) |
| `src/holo/receiver/docs/conversion_docs/crop-batteries/crop-battery-xerox-c2-cmy7.md` + `xerox-c2-cmy7-results.json` | 2026-08-30 21:31 | holo1 `3537128d0084` vs holo3 `f5d7c0e2efc8` | 20 cases, 57 targets (26 miss + 31 gain); **zero wrong**; agree 55 / disagree 2; walls holo1 **16,625.6 s** vs holo3 **3,773.6 s** (4.4×) |
| `scratch/holo3-overnight-events/c2-cmy7-events.jsonl.xz` (378 KB) | 2026-08-30 | holo3 | event stream |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger-run3.jsonl → step="c2-cmy7"` | 2026-08-30 | holo3 | 4,160.1 s, peak RSS 28.21 GiB, `payload_sha256 5963b9d1…`, `sha_ok true` |
| `src/holo/receiver/docs/conversion_docs/14-acceptance.md:327-329` | 2026-08-29 | — | **"Vol 6 has never been closed by a PLAIN CLI invocation on any tree (harness-only close)"** — a standing caveat on every c2-cmy7 number |

### 1.6 hp c2-cmy7 — the clean-refusal volume

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `experiments/032-xerox-altalink-payload-volumes.md:147-152` | 2026-08-05/06 | holo1 | never became addressable: footprint **60.3%** (4,485,766/7,443,072), windows 4183/880, 808 acc, **2,713 unres** `:147-149`; words **47 match** / 1051 / 322; **LDPC 0 calls, 0 certificates — the payload stage never ran** `:150`; fountain received 0, K unavailable, **metadata rank 0/24**, +48 checks to trust `:151-152`. Print date unestablished (`:254-256`) |
| `scratch/in/holo-hp-c2-cmy7-counting-receive.state` (2,222,275 B) | 2026-08-06 | holo1 | the refusal session |
| `scratch/color-uplift/full/hp-c2-cmy7-{control-price,pkfinal,pkfinal-repin}/receive.state` (2.22 MB each) | 2026-08-07 / 08-10 | holo1 | three colour-uplift re-runs, all still refusing — **the campaign's B6 control, the pure no-op**: 0 certificates, 0 payload blocks on any lane, u-lane tail costs **0.0 s and emits nothing** (`docs/COLOR-UPLIFT-MEASUREMENTS.md:3028` §14.2 row 8; `:3157`, `:3178-3180`; run ledger `:3813-3814`) |
| `scratch/plane-fields/{policy-detach/cmy7-counting.state, prefix-repair/smoke-hp-c2-cmy7.state}` (2.22 MB each) | 2026-08-23 | holo1 | plane-fields policy/prefix smoke copies of the same refusal |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/hp-c2-cmy7-counting-failed.json` | 2026-09-02 | holo1 (frozen) | **0 certificates**, close `open` |
| `src/holo/receiver/docs/conversion_docs/14-acceptance.md:331-332` | 2026-08-29 | — | proposes it as an explicit acceptance negative control ("must NOT close, must refuse cleanly") — **not yet adopted** |
| — | — | holo3 | **NO holo3 decode of this volume exists.** Not in the parity six, not in the batteries, not in the overnight ledgers. See GAP G-04 |

### 1.7 e030 hp c2/c3-cmy8 — neither volume recovered

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `experiments/030-holo-cmy8-hp-canon.md:109-146` | 2026-08-05 | holo1 | **c2 `:113-118`** — footprint **45.1%** (3.36M/7.44M), 721 acc / 5139 unres, words 2/1060/161, LDPC 6,586 calls with **0 certificates**, 1,515 failed, 2,229 low, `crc_ok=0`; fountain received 0, **metadata rank 0/24**, close deferred; verdict "not a viable CMY8 channel at c2 on the M281" `:124-126`. **c3 `:132-141`** — footprint **99.3%**, 1381 acc / 379 unres, words 78/629/133, LDPC 35,281 calls, **663 certificates** (scan `crc_ok` 621 + retry150 `crc_ok` 42), 1,842 failed, 15 low; **per-stream C 620 / M 43 / Y 0, C∩M only 31 tiles** `:137`; fountain 663/402 K, reach **663/1206 over 3 blocks**, metadata trusted, **close OPEN** `:138-139`. Payloads 718,413 B `f13c34db…` and **314,579 B `a98e9935…`** `:40-45` |
| `.claude/memories/e030-holo-cmy8-hp-canon.md:8-12,24,32` | 2026-08-05 | holo1 | the condensed record + the four payload sizes |
| `scratch/e030/holo-c2-cmy8-q05-counting/receive.state` (81,096,384 B) + `.diag/` | 2026-08-05 | holo1 | the c2 failure session |
| `scratch/e030/holo-c3-cmy8-q05-counting/receive.state` (633,828,523 B) + `.diag/` | 2026-08-05 | holo1 | the c3 partial session |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/e030-hp-c2-cmy8-q05-hardfail.json` | 2026-09-02 | holo1 (frozen) | **0**, close `open` |
| `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/e030-hp-c3-cmy8-q05-partial.json` | 2026-09-02 | holo1 (frozen) | **663**, close `open` |
| `scratch/color-uplift/full/hp-c2-cmy8-{control-price,pkfinal}/receive.state` (81 MB / 160 MB) and `hp-c3-cmy8-pkfinal/receive.state` (887 MB) + `cache/`, `feature-library/`, `regmap/` siblings | 2026-08-08/10 | holo1 PK-FINAL | **the best-on-record for both**: hp c3-cmy8 **663 → 796 (C 740 / M 56 / Y 0), +133 / −0 STRICT SUPERSET, close still OPEN** — 2 of 3 blocks, **≥748 symbols short** (`docs/COLOR-UPLIFT-MEASUREMENTS.md:3011` §14.2 row 2); hp c2-cmy8 **0 → 15, close OPEN**, metadata coefficient rank **0 → 14 of 24** (`:3027` row 7). **This volume carried the campaign's largest single move**: A5 multi-state context took it 663 → 796, address level +127/−1, adopted in all 17 lanes, **CPU −5.3%** (`:2187-2200`) |
| `scratch/color-uplift/runs/hp-c3-cmy8-replay-{baseline,pk5-matrix,pk5-planes,pk5v2-matrix,pk89iter3}.diag/` and `xerox-c{2-cmy8,3-cmy7}-replay-*.diag/` (24 replay dirs in all) | 2026-08-08/10 | holo1 | **the per-arm replay ladder** — the clean A/B material for the colour arms; the reductions are `scratch/color-uplift/runs/{address,lanes,stagetime,setdiff,delta,compare}-<packet>-<capture>.{json,md}` (290 entries, 2.8 GB) |
| `scratch/e030/{tiff-shas.txt, cmy8-gt-vs-scan-tiles.png}` and `holo-c{2,3}-cmy7-q05-counting/` (emit-only: manifest, `page000.ps`, `page000_gt.npy`, payload — **no state, print pending**) | 2026-08-05 | — | scan provenance, a GT/scan tile montage, and the two never-printed cmy7 emissions |
| — | — | holo3 | **NO holo3 decode exists** of either e030 volume. See GAP G-04 |

### 1.8 sheet I — `L:c2-cmy8-r0700-p120-x1@3392x2368` (the deepest-read volume on record)

Four distinct holo3 epochs plus three holo1 states. Keep them apart.

**holo1 side**

| artefact | date | size | what it measures |
|---|---|---|---|
| `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/receive.state` + `.diag/` | 2026-08-18 | 3.68 GB | the e033 three-scan pooled close; **the state `PARITY.md:324` uses — 5,297 certificates (M 1958 / C 1895 / Y 1444)** |
| `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm-4800/receive.state` + `.diag/` | 2026-08-19 | 3.65 GB | the 4800-capture arm |
| `scratch/xerox-v1-20260818/I-multi-pf/receive.state` + `.diag/` | 2026-08-21 | 5.71 GB | the plane-fields W6 qualification run |
| `scratch/xerox-v1-20260818/I-multi-pf2/receive.state` + `.diag/` | 2026-08-23 | 5.42 GB | the second plane-fields run |
| `scratch/plane-fields/qual/` (`receive.state` 3.95 GB, `events.jsonl` + `events-pass1.jsonl` 174 MB each, `events-close.jsonl`, `close-result.json`, `score-on{,-pass1}.json`, `recovered.bin` 1,798,761 B, `run-on.log`, two residue PNGs) | 2026-08-21 | 8.4 GB | **the plane-fields W6 sheet-I qualification, with its own event logs and scoring JSONs** — the only holo1 run in the archive that ships raw `events.jsonl` |
| `scratch/plane-fields/{field-from-certs-I.json, comparison-I.png, plane-fields-I.png, band-preview.png, e9-candidates.json}` | 2026-08-20/23 | — | the fitted field, the certificate comparison, the band preview |
| `experiments/033-xerox-rung-experiments.md:69-86` | 2026-08-18 | holo1, branch `c4-row` (`:4-8`) | sheet I's first close: **VERIFIED byte-exact in-flight, 1,798,761 B, sha `2445b95db5b49bf3…`** == emitted payload, `recovered.bin` cmp-identical `:73-75`; **certificates 5,297/5,883 — M 1958 (99.7%) / C 1895 (95.3%) / Y 1444 (73.6%)** `:76-77`; run 1 single-capture reach 5152/5277, **shortfall 125** `:71-72`; run 3 `--complete` resume **crashed at LOAD** ("stream 'M' is not declared"), state undamaged `:78-80`; **230.7 b/mm² ≈ 3.6× e029's certified record** `:85-86`. **Y mechanism: a sinusoidal x-registration, peak 3.33 px @2400 = 0.83 dot = 0.42 cell, period ≈18.5 tiles ≈100 mm, Spearman +0.80 (p=4e-9)** `:110-114`; Y capture gain 1377 → 1444 across two extra captures `:133`. **Caveat the log states itself: the §033.4 residue table is a mid-run snapshot (sums 581, Y 1380) — the archived VERIFIED state ends at 517 (Y 1444)** `:174-179`. The other nine identities A–H are tabulated at `:24-32`, **all unscanned at log time** `:12-14`, `:162` |
| `experiments/034-sheet-i-full-readout.md` | 2026-08-31 | **holo3** (run dirs, `facts.npz`/`report.json`/`events.jsonl`, `:22-24`, `:30-33`) | **5,880/5,883 = 99.949% — M 1961/1961, C 1960/1961, Y 1959/1961, zero wrong** `:3-9`; close **VERIFIED byte-exact on every closing run (3 closes)** `:31-33`, `:181-182`; the chain table `:28-33`; per-run detail `## Run 1` `:46`, `## Run 2` `:68`, `## Run 3` `:98`, `## Run 4` `:107`; residue `:127-145`. Chain cost **≈302,400 cpu-s ≈ 84 cpu-hours** `:44`. **Does not record a tree sha for any run** (`:173-174`, the log's own "one provenance gap") |

**holo3 side, by epoch**

| epoch | artefact | date | certs | close |
|---|---|---|---|---|
| baseline `run-7` | `src/holo/receiver/docs/conversion_docs/PARITY.md:322-423`; `parity.json → "7"`; `scratch/holo3-overnight-events/sheet-I-events.jsonl.xz` (2.0 MB); `overnight/ledger-run3.jsonl → step="sheet-I"` | 2026-08-29/30 | **5326** vs holo1 5297, matched 5193, **miss 104 (1.96% — FLAGGED)**, extra 133; wall 11,246.1 s, peak RSS 48.8 GiB; step 7 needed two attempts, the first died at ~33 min to harness reaping (not memory) and the re-run survived 1h52m at 47.86 GiB (`PARITY.md:18`) | VERIFIED `2445b95d…` |
| post `post-7` | `src/holo/receiver/docs/conversion_docs/PARITY.md:616-660`; `POST-FORENSICS.md:330-345` (`### B.3`) | 2026-08-30 | **5439** — **MET** the pre-registered bar, miss 104→34, dropping below the 1% flag; Y 1470→1559; recovered 73, lost 13; wall 2.03× (13,580 s), peak 48.09 GiB | VERIFIED |
| crop battery | `measure/crop_parity/cases/sheet-I/{cases.json,cases-census.md}`; `src/holo/receiver/docs/conversion_docs/crop-batteries/sheet-I-battery-partial.log`; the salvage tarball's `scratch/crop-parity/sheet-I/runs/*` | 2026-08-31 | **PARTIAL — no `results.json`, no battery markdown.** `cases.json → gap_counts` = holo1 5297 / holo3 5439 / both 5263 / miss 34 / gain 176 / neither 410, over 26 cases; the run log shows c01–c13 only, holo1 exit 2 on c01 and c10 | — |
| arms-wave machine 2 | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:22-35` | 2026-08-31 | **5,543 — best ever at that moment** (previous holo3 best 5,445; holo1 5,297), C 1,949 / M 1,960 / Y 1,634; count-ready with 266 symbols of margin; `tiles.local` minted 213 at **73% of the run's CPU**; **the plane field contributed nothing** — 54 fits, 5,211 CPU-s, ZERO PlaneField facts (that tree's floor was effectively 0.50 dots and its fitter cells-valued) | `--no-close` |
| **the four-run resume chain (e034)** | `scratch/sheetI-20260831/` — `argv-{first,resume,resume-2,resume-3}`, `report-{first,resume,resume-2,resume-3}.json`, `events-{first,resume,resume-2,resume-3}.jsonl.xz`, `pane-*.png`, `shell-transcript.txt`, `web-final-status.txt` | 2026-08-31 | **5543 → 5866 → 5866 → 5880**; run 1 `count_ready` (3×2400, `--workers 12`, `--plane-fields --complete`); run 2 +323 (`tiles.planek` 281, `tiles.local` 26, `tiles.retry` 10, `tiles.swim` 6) and **the first VERIFIED close**; run 3 +0 (the control, 1,039 jobs / 4,193 cpu-s, still VERIFIED); run 4 adds the 4800 capture and takes **+14** (`tiles.planek` 9, `tiles.local` 2, `tiles.swim` 1, `tiles.retry` 1, `tiles.union` 1) — C 2 / M 0 / Y 12 | VERIFIED `2445b95db5b49bf3`, 1,798,761 B, three times |

**sheet-I analysis documents** (read-only post-mortems, gitignored, no decode run):

| path | date | what |
|---|---|---|
| `scratch/sheetI-20260831/angle-vs-placement.md` (18.7 KB) | 2026-08-31 | platen angle vs window placement, over four finished runs; **its two primary sources `/tmp/I/holo3-I-first-run/events.jsonl` and `/tmp/I/holo3-I-resume-3-run/events.jsonl` still exist under `/tmp/I/` but are not backed up** — the xz copies in `scratch/sheetI-20260831/` are the durable ones |
| `scratch/sheetI-20260831/v2v3-placement-residue.md` (45 KB) | 2026-08-31 | **the holo2-vs-holo3 placement head-to-head** — see §2 |
| `scratch/sheetI-20260831/review-cmy8-p-axis-plan.md`, `…-rev3.md` | 2026-08-31 | two adversarial reviews of the cmy8 p-axis plan (format-axis, not receiver) |

### 1.9 sheet H — `L:c2-cmy8-r0850-p120-x1@3392x2368` (never closed)

| artefact | date | receiver | what it measures |
|---|---|---|---|
| `scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm/` and `H-multi-pf/receive.state` (**14,999,749,753 B — the 15 GB memory risk**) + `.diag/` | 2026-08-18 / 08-23 | holo1 | the archived holo1 sessions |
| `docs/INDEPENDENT-PLANES.md:1795-1819` (§7) | 2026-08-23 | holo1 | **the ONLY artefact holding a holo1 sheet-H number**, and it scores a prediction registered before the read: one 2400 dpi capture, `--refine --no-close`, state `H-multi-pf`, capture `68c16fcb…` → **4,092/5,883 — C 1,663/1,961 (85%), M 1,891/1,961 (96%), Y 538/1,961 (27%)**, 1,791 LDPC failures (`:1806-1810`). Pre-registration at `:1795-1805`; caveats (one capture, one footing, first read) `:1813-1817`. **No experiment log records a sheet-H decode at all** |
| `scratch/holo3-overnight-events/sheetH-maxstack-report.json` | 2026-08-30 21:24 | holo3 | **the seven-capture max-stack: 4,237/5,277, close OPEN**; C 1,694 / M 1,883 / **Y 660**; 680,472 jobs / 121,967.7 CPU-s; certs by plugin `tiles.scan 2183 · tiles.union 1818 · tiles.retry 236`; **`tiles.union` contributed 1,818 — 43% of the harvest**, the largest union yield anywhere in the record |
| `scratch/holo3-overnight-events/sheetH-maxstack-events.jsonl.xz` (9.2 MB, 1.48 M events) | 2026-08-30 | holo3 | the full event stream; the primary dataset of `angle-vs-placement.md` |
| `scratch/holo3-overnight-events/sheetH-maxstack-certified-tiles.json` (61.8 KB) + `sheetH-maxstack-certmap.png` | 2026-08-30 21:42 | holo3 | the certified address list and its map — the Y dead/alive banding drawn in certificates |
| `scratch/holo3-overnight-events/sheetH-mixed-events.jsonl.xz` (3.2 MB) | 2026-08-30 | holo3 | the four-capture (2×1200 + 2×2400) run |
| `src/holo/receiver/docs/conversion_docs/overnight/ledger.jsonl → step="sheetH-mixed"` | 2026-08-30 | holo3 | wall 5,380.5 s, peak RSS **40.67 GiB**, exit 2 |
| `src/holo/receiver/docs/conversion_docs/overnight/final-manifest.json → steps[id="sheetH-mixed"].argv` | 2026-08-30 | — | the exact four-capture invocation |
| `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:12-20` | 2026-08-31 | holo3 | **the seven-capture stack is 70 BELOW the four-capture run (4,307)**, Y 660 vs 709; the colour lane burned 38,512 CPU-s (31%) on the escalating-refit ladder the repricing fix then killed; **first cross-dpi union certificates on paper: 1,508 of the 4,307** |
| `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:36-43` | 2026-08-31 | — | **"The 4800 question re-opened honestly"** — the −70 was measured on the defective-scheduling tree and the objection to the stated mechanism stands; the discriminating pair is unrun (machine 4) |
| `measure/yask/README.md` | 2026-08-31 | instrument | the Y-as-K ablation ladder **on sheet-H crops vs the seven-capture harvest** — 324 tiles all C/M-certified in production, 105 Y-certified there and 219 not; arms C0 (raw blue) 0 adds, C1 25 certs / +1, A0 39 certs / +5; **zero wrong anywhere in the battery**; null arm certifies nothing |
| `experiments/034-sheet-i-full-readout.md` / `docs/INDEPENDENT-PLANES.md` | 2026-08-23/31 | — | the pre-registered sheet-H Y prediction and its confirmation (Y 538/1961) |

### 1.10 sheet J — `c2-cmy8-r0547@53x37` (NOT in the plan's volume list; live as of 2026-09-01)

A new confetti/fragment volume printed on the AltaLink and scanned 2026-09-01/02. It is the **only multi-page / fragment material in the holo3 record** and therefore the only artefact that bears on the page-domain rows beyond the synthetic e029 merge.

| artefact | date | what |
|---|---|---|
| `scratch/xerox-canon-1.9-J-c2-cmy8-r0547-confetti-2400-{1a,2a,3a,4a,6a,7a,8a,9a}.tiff` (1.72 GB each), `…-4800-{1,5a}.tiff` (6.88 GB each), `…-full-2400-{a,b}.tiff` | 2026-09-01/02 | ten confetti captures + two full-sheet captures |
| `scratch/J-run.52093/` (2.1 GB) — `argv`, `tree` (`…-912-g1faa7a2b`), `events.jsonl` (9.7 MB, **uncompressed**), `facts.npz`, `report.json`, five panes | 2026-09-01 18:34 | one capture, `--pages` default: **357 certificates** (C 124 / M 126 / Y 107), K 357/4020, close OPEN; UNKNOWN 4398 / ADDRESSED 480 / FLOOR 546; `tiles.scan` 243 · `tiles.retry` 71 · `tiles.local` 27 · `tiles.planek` 10 |
| `scratch/J-run.54028/` (2.1 GB) — 311 entries incl. per-page panes | 2026-09-01 19:39 | `--pages 100 --resume`: **+300 → 657 certificates**, K 657/4020, still OPEN; `tiles.scan` 221 · `tiles.retry` 30 · `tiles.local` 21 · `tiles.planek` 16 · `tiles.swim` 12 |
| `scratch/J-run.56088/` (4.2 GB) — `argv`, `tree`, two capture dirs, no `report.json` | 2026-09-01 19:46 | `--pages 2 --resume` over two captures; **incomplete run dir — no report, no events** |
| `scratch/c2-cmy8-r0547-q06860-1MiB/` (148 MB) | 2026-09-01 | the emission side |

### 1.11 sim captures

| artefact | date | what | how to read |
|---|---|---|---|
| `src/holo/receiver/tests/_h3_sims.py:118,122` | tracked | the two pinned payload shas: K `59495601d00fa781…` (6,000 B), colour `ddf7acebcd86ae52…` (20,000 B) | python constants |
| `src/holo/receiver/docs/conversion_docs/verify/acceptance.json → steps[id="1k"], steps[id="1c"]` | 2026-08-29 | the sim step definitions: formats `c3-k-r0550@7x7` / `c3-cmy8-r0550x0550x0547@10x10`, 1200 dpi | JSON |
| `src/holo/receiver/docs/conversion_docs/verify/make_sims.py` | 2026-08-29 | the stimulus builder | python |
| `src/holo/receiver/docs/conversion_docs/d6-baseline/{k-w1,k-w8,color-w1,color-w8}.json` | 2026-08-29/30 | **the worker-count byte-identity baseline**: K 49/49 certs and colour 279/279 at `--workers 1` and `8`, same payload sha, plus full `plugin_rows` (jobs/cpu_seconds/certificates/poses/words per row), `certificate_addresses`, `certificate_signature_sha256`, `event_counts`, `job_counts_per_row`, `argv` | JSON; `plugin_rows` is the per-mechanism CPU record |
| `src/holo/receiver/docs/conversion_docs/d6-baseline/{manifest,reference,lanes,ingest-planes}.json`, `schedule-baseline.txt` | 2026-08-29 | the D6 wave-0 baseline: `lanes.json` records fast lane 1,182 passed / 8.08 s and slow 1,534 / 64.24 s at head `28cf0c29`; `schedule-baseline.txt` is the readable cost/tier/premium table per row | JSON / text |
| `src/holo/receiver/docs/SCHEDULE.md:426-520` | 2026-09-01 | **the per-mechanism sim evidence section** — see §2 | `path:line` |
| `src/holo/receiver/tests/test_h3_e2e_sims.py`, `test_h3_e2e_modes.py`, `test_h3_e2e_rotations.py`, `test_h3_degraded_sim.py`, `test_h3_multires.py` | tracked | the live sim decode lanes (seconds to minutes; **not** receiver runs per §2 principle 3) | pytest |
| `src/holo/receiver/tests/test_h3_{color_field_yield,planek_existence,swim_existence,uplift_existence,page_domain}.py` | tracked | the per-arm existence proofs, each with its own constructed stimulus | pytest |

### 1.12 The crop batteries

Five committed batteries + one partial. Every battery is a **holo1-vs-holo3
per-tile comparison on identical crops**, ground-truthed against the golden
payload re-encoded through holo1 generation, with a wrong-certificate audit.

| volume | md | JSON | cases | targets | wrong | agree/disagree | holo1 wall | holo3 wall |
|---|---|---|---:|---:|---:|---|---:|---:|
| e029 | `crop-battery-e029.md` | `e029-results.json` | 1 | 2 | 0 | 2 / 0 | 421.2 s (adopted) | 80.6 s |
| xerox-k | `crop-battery-xerox-k.md` | `xerox-k-results.json` | 5 | 7 | 0 | 7 / 0 | 395.4 s | 145.4 s |
| xerox-c3-cmy7 | `crop-battery-xerox-c3-cmy7.md` | `xerox-c3-cmy7-results.json` | 8 | 95 | 0 | 91 / 4 | 2,978.3 s | 710.8 s |
| xerox-c2-cmy7 | `crop-battery-xerox-c2-cmy7.md` | `xerox-c2-cmy7-results.json` | 20 | 57 | 0 | 55 / 2 | 16,625.6 s | 3,773.6 s |
| xerox-c2-cmy8 | `crop-battery-xerox-c2-cmy8.md` | `xerox-c2-cmy8-results.json` | 16 | 124 | 0 | 102 / 22 | 7,613.3 s | 2,677.9 s |
| sheet-I | **none** | **none** | 26 planned, 13 attempted | 210 | — | — | — | — |

All under `src/holo/receiver/docs/conversion_docs/crop-batteries/`. Manifests +
census: `measure/crop_parity/cases/<volume>/{cases.json,cases-census.md}`.
Harness: `measure/crop_parity/` (`README.md` documents the invocation;
`harness.py`, `cases.py`, `_gt.py`, `_selfcheck.py`, `_volumes.py`).
Per-case sidecars (`holo1.sidecar.json`, `holo.receiver.sidecar.json`,
`holo3-certs.json`, `holo3-run/report.json`) survive **only in the salvage
tarball** under `scratch/crop-parity/<volume>/runs/<case>/`.

Batch cost, from `src/holo/receiver/docs/conversion_docs/overnight/ledger.jsonl`:
`crop-xerox-c3-cmy7` 3,691.9 s, `crop-xerox-c2-cmy7` 20,412.8 s,
`crop-xerox-c2-cmy8` 10,306.6 s, `crop-sheet-I` 24,188.7 s (exit 1);
peak RSS 0.31–2.22 GiB — **the batteries are three orders of magnitude
cheaper in memory than a full-sheet run.**

Aggregate across the five completed batteries: **285 target addresses, zero
wrong certificates on either side, zero out-of-bbox certificates.**

### 1.13 demo9 and the synthetic fixtures

`demo9` is a **holo2 fixture** — nine scraps, 3 pages × 3, decoded by v1 and
holo2 only. No holo1 or holo3 artefact in this repo decodes it.

| artefact | what it measures |
|---|---|
| `holo2/docs/MEASUREMENTS.md:1084-1091` (the F2-tree parity table) | **v1 2,673 / holo2 2,668, −5, both closes OPEN, wall 33,945 s** — RULING I1 NOT MET. Wall footnote at `:1093`: solve+prepare, not a solve wall (demo9 built 36 of its 2,187 prepared planes) |
| `holo2/docs/MEASUREMENTS.md:1118` | the five tiles, named: (0,31,2), (1,4,15), (2,8,12), (2,41,12), (2,44,6) — **unchanged from W4; 0 of 5 rescued by any ordering rule and one has a single pose at every footing** |
| `holo2/docs/MEASUREMENTS.md:1131`, `:1171` | the W-wave movement 2,665 → 2,668 (+3), and the earlier 2,673/2,668 row at a different vintage |
| `holo2/docs/kparity/DIVERGENCE-LEDGER.md:362` (§4) | **"demo9 — the one K population with no candidate mechanism"**: 0 of its 5 gap tiles is explained by any of the 59 ledger rows |
| `holo2/docs/CATCHUP-PLAN.md:525`, `:530`, `:557`, `:592`, `:628`, `:647`, `:652` | the same numbers plus the doctrine — demo9 is the natural target population for the pose-drop line, and it is a half-day nine-platen fixture, not a real sheet |
| `scratch/holo2-catchup/real/parity-F2/{h2,v1}-demo9.parity.json` | the machine record of the F2-tree parity run; also `fx-channel`, `fx-banded`, `fx-subdivision` alongside it |
| `scratch/holo2-catchup/real/parity-k-F2.md:110-233` | the per-sheet report sections |

holo3's own synthetic fixtures are the sim captures (§1.11) plus the
per-arm constructed stimuli that live in `src/holo/receiver/tests/` and are described,
with their measured yields, in `src/holo/receiver/docs/SCHEDULE.md:426-520` and
`src/holo/receiver/docs/conversion_docs/ARMS-2026-08-31.md`.

### 1.14 The archived holo1 `.state` corpus — the complete disk inventory

**28 states, not 17.** Sizes and mtimes only; none was opened.

| path | size | mtime |
|---|---:|---|
| `scratch/e028/holo-c2-r0700-q07-ink-counting/receive.state` | 8,206,654 | 2026-08-04 |
| `scratch/e030/holo-c2-cmy8-q05-counting/receive.state` | 81,096,384 | 2026-08-05 |
| `scratch/e030/holo-c3-cmy8-q05-counting/receive.state` | 633,828,523 | 2026-08-05 |
| `scratch/in/holo-xerox-c2-counting-receive.state` | 9,429,553 | 2026-08-05 |
| `scratch/in/holo-hp-c2-cmy7-counting-receive.state` | 2,222,275 | 2026-08-06 |
| `scratch/in/holo-xerox-c2-cmy7-counting-receive.state` | 1,664,114,915 | 2026-08-06 |
| `scratch/in/holo-xerox-c2-cmy8-q05-counting-receive.state` | 1,309,153,068 | 2026-08-06 |
| `scratch/in/holo-xerox-c3-cmy7-counting-receive.state` | 138,019,450 | 2026-08-06 |
| `scratch/color-uplift/full/hp-c2-cmy7-control-price/receive.state` | 2,222,275 | 2026-08-07 |
| `scratch/color-uplift/full/hp-c2-cmy8-control-price/receive.state` | 81,096,426 | 2026-08-08 |
| `scratch/color-uplift/full/xerox-c2-k-pkfinal/receive.state` | 9,429,565 | 2026-08-09 |
| `scratch/color-uplift/full/xerox-c3-cmy7-pkfinal/receive.state` | 51,753,007 | 2026-08-09 |
| `scratch/color-uplift/full/hp-c2-k-pkfinal/receive.state` | 8,206,666 | 2026-08-10 |
| `scratch/color-uplift/full/hp-c2-cmy7-pkfinal/receive.state` | 2,224,400 | 2026-08-10 |
| `scratch/color-uplift/full/hp-c2-cmy7-pkfinal-repin/receive.state` | 2,224,413 | 2026-08-10 |
| `scratch/color-uplift/full/hp-c2-cmy8-pkfinal/receive.state` | 159,654,582 | 2026-08-10 |
| `scratch/color-uplift/full/hp-c3-cmy8-pkfinal/receive.state` | 887,575,794 | 2026-08-10 |
| `scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/receive.state` | 701,559,473 | 2026-08-10 |
| `scratch/color-uplift/full/xerox-c2-cmy8-pkfinal/receive.state` | 1,266,752,808 | 2026-08-10 |
| `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/receive.state` | 3,684,201,722 | 2026-08-18 |
| `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm-4800/receive.state` | 3,652,237,548 | 2026-08-19 |
| `scratch/xerox-v1-20260818/I-multi-pf/receive.state` | 5,712,224,423 | 2026-08-21 |
| `scratch/plane-fields/qual/receive.state` | 3,953,200,764 | 2026-08-21 |
| `scratch/xerox-v1-20260818/I-multi-pf2/receive.state` | 5,417,727,320 | 2026-08-23 |
| `scratch/xerox-v1-20260818/H-multi-pf/receive.state` | **14,999,749,753** | 2026-08-23 |
| `scratch/plane-fields/policy-detach/cmy7-counting.state` | 2,222,275 | 2026-08-23 |
| `scratch/plane-fields/policy-detach/cmy8-pkfinal.state` | 159,654,582 | 2026-08-23 |
| `scratch/plane-fields/prefix-repair/smoke-hp-c2-cmy7.state` | 2,222,275 | 2026-08-23 |

Every one also carries a sibling `receive.state.diag/` directory (holo1's
own diag dump: `events.jsonl`, `report.json`, panes) except the
`color-uplift/full/` and `plane-fields/{policy-detach,prefix-repair}`
copies; the corresponding diag dumps for the colour-uplift runs live under
`scratch/color-uplift/runs/<name>.diag/`.

**Reading a state.** Full `load_session` decompresses every inlined evidence
block — measured ~7× the file size in RAM, 931 MB peak for a 131 MB colour
state (`PARITY.md:22`). For addresses only, use the mmap slice path
(`measure/parity/extract_holo1_certs.py:1-19`), cross-validated against a
real `load_session` on two states with identical sorted address lists
(`PARITY.md:22-23`). That reader **leaves with the tree** — see GAP G-01.

---

## 2. Per mechanism family

Each family lists, per side, the artefacts that carry a measured yield or
cost number, with the headline and its `path:line`. Bare `MEASUREMENTS.md:N`
means `holo2/docs/MEASUREMENTS.md`. Numbers below were read at the cited
line by the readers who compiled them; where a seed pointer was wrong the
corrected line is given here and recorded in Appendix B.

### 2.0 The three cross-cutting artefacts every family will want

| artefact | what it is |
|---|---|
| `src/holo/receiver/docs/conversion_docs/PARITY.md` + `parity.json` | the **certificate-address** comparison, holo1 vs holo3, on all six full-harvest volumes; both baseline and post-change |
| `src/holo/receiver/docs/conversion_docs/crop-batteries/` + `measure/crop_parity/` | the same comparison **per tile on a crop**, in seconds instead of hours, with a wrong-certificate audit |
| `holo2/docs/kparity/DIVERGENCE-LEDGER.md:61-126` | **59 v1-vs-holo2 divergence rows, one per line, with the measured effect in column 6** — the closest thing in the repo to a prior art of this campaign's own map |

### 2.1 Placement

**holo3 vs holo2 — the only direct head-to-head that exists.**
`scratch/sheetI-20260831/v2v3-placement-residue.md` (2026-08-31, gitignored,
45 KB) with artefacts in `scratch/angle-residue/` and instruments
`measure/angle_residue{,_h2,_census,_certs,_nyquist}.py`. Four decodes over
one 1000×1000-cell crop of the e029 HP K sheet at two synthetic platen
angles, each TIFF handed unchanged to both receivers (`:19-56`,
reproduction recipe `:823-845`):

| | holo2 0.00° | holo3 0.00° | holo2 0.80° | holo3 0.80° |
|---|---:|---:|---:|---:|
| unresolved windows left | 196 | **155** | 397 | **281** |
| windows retired | **0** | 4 | **0** | 0 |
| lane-0 (2 px/cell) failure | 54.6% | **37.1%** | 81.6% | **58.3%** |
| placement CPU on unresolved windows | 60.2% | **49.2%** | 75.4% | **62.5%** |
| certificates | 100 | **112** | 56 | **82** |
| wall | 1,370 s | **842 s** | 1,206 s | **786 s** |

Verdict `:21-22`: **"the hypothesis is REFUTED on the mechanism it names,
and measured head-to-head on identical material holo2 is the worse of the
two."** Also measured there: the refusal is **inherited and identical in
both trees** — at 2 px/cell the printed cell fundamental sits on the Nyquist
bin of `np.fft.rfft2`'s last column so the magnitude argmax cannot recover
the sign of the platen rotation; both return `|θ|` at ppc 2 and both return
θ correctly 10/10 at ppc 4 and 8 (`:52-56`, §2 `:296-373`). **Zero wrong
certificates on either side at either angle**, and at 0.80° holo3's
certificate set is a **strict superset** of holo2's (`:57-59`;
`scratch/angle-residue/certs-summary.json`). What holo3 has that holo2 does
not is a longer tail — one window fired 18 times against holo2's worst of 7
— but that same reach places the coarse lane at all: **28–80% of every
lane-0 chain pose in four datasets comes from an anchor holo2's rule would
never have offered** (`:60-66`). Recommendation recorded: cap the
repetition, not the reach (`:67-70`).

**holo1 side.**

| number | value | cite |
|---|---|---|
| the zero-contradiction invariant | 70/70 regions, all 925 pilot tiles, **ZERO contradictory reads across ~1,780 attempted known-position decodes**; routing split 331 chain / 42 correlation / 38 BCH-seed | `docs/RECEIVE-DESIGN-EVIDENCE.md:492` — **the plan's citation RESOLVES exactly** |
| spectral Jacobian accuracy | **within 0.001 px of GT** at 200-cell windows, angle-blind mod 90, no seed, no sweep ladder | `docs/RECEIVE-DESIGN-EVIDENCE.md:489` |
| pose battery Q3 | rotations 0–44° × subpixel origins × anisotropy ±0.3–0.4% × shear ±0.15–0.25° — **all placed exactly**; worst cell-mapping error 0.199 cells at 8–11.7 ppc, 0.029 at native | `docs/RECEIVE-DESIGN-EVIDENCE.md:490` |
| native == decimated at addressing | 362 vs 363 tiles, 361 common, **ZERO contradictions**; peak RSS 6.2 vs 13.5 GB | `docs/RECEIVE-DESIGN-EVIDENCE.md:491` |
| null battery | Q1 **12/12** exact over a four-page legal set; **0/49** adversarial-null false accepts over 784 field hypotheses | `docs/RECEIVE-DESIGN-EVIDENCE.md:496` |
| multi-slot Stage A | declared hypotheses **147,456/window** vs an α=1e-3 union-bound ceiling of **581,074**; route substitution 19 word + 32 cold → **51 word + 0 cold**, yield exactly invariant (604 certs, same tiles, same bits) | `docs/PLACEMENT-IMPROVEMENTS.md:298-300`, `:304-307` |
| staged Stage A | up-front all-slot sweep costs **+267 s address CPU (+21%)** at identical yield; the staged form is **3,627 → 794 ms** per word-succeeding window | `docs/RECEIVE-DESIGN.md:59`; `docs/PLACEMENT-IMPROVEMENTS.md:308-311` |
| cold-search exactness speedup | **1.33× / 1.55× / 1.65×** at P = 4/16/64 (the earlier "~3×" was the FFT-count bound, not a measurement) | `docs/PLACEMENT-IMPROVEMENTS.md:290-293` |
| three-way address CPU | v0.21 493 s → v0.24 783 s → v0.31 **647 s** | `docs/PLACEMENT-IMPROVEMENTS.md:319-322` |
| cold boundary | ~75 word-dead windows each pay ~2.8 s of 8-slot decode ahead of a cold costing ~1–3 s **at single-page domain**; widening pays decisively only at large domains (**30–48 s per avoided cold**) | `docs/PLACEMENT-IMPROVEMENTS.md:325-331` |
| the d=27 whole-word gate | a parity split can hide an alias in **7 of 45 sites** | `src/holo/receive/placement/search.py:38` |

**holo2 side.**

| number | value | cite |
|---|---|---|
| accepted consult distances | **0.0 ×24 / 0.9812 ×18 / 1.0 ×14**; **accepted rank is 0 on all 56 — the nearest offer won every time** | `MEASUREMENTS.md:1628-1630`, `:1636` |
| `CONSULT_KEEP=8` never bound | truncation bit on **0 of 60 passes**, per-pass max 5, median 2 | `MEASUREMENTS.md:1648-1651` |
| `WIDE_ANCHORS=8` | **UNMEASURED** — 0 wide passes on all three arms | `MEASUREMENTS.md:1654-1655` |
| cross-footing donors | **half of all acceptances** on the cascade arms | `MEASUREMENTS.md:1640-1645` |
| Stage-A parity deviation | `min_support` **31 where v1 reads 30**; knee at **250,530**; the two-stages-spent pass at a domain of **294,961** | `MEASUREMENTS.md:1367-1368` and `holo2/src/holo2/solve/DESIGN.md:649` (**not** `:1366-1370` as the seed says) |
| word staging | **3,627 → 794 ms** per word-succeeding window (same number as v1's) | `holo2/src/holo2/solve/DESIGN.md:790` |
| cold cost | transform cache **~7.6 GiB** + ~1.1 GiB reference pages, **47.9 s per patch** | `holo2/src/holo2/solve/DESIGN.md:798` |
| W4 cold | **+1.4%** on the consolidated wall, zero new decodes; **0 diff lines in `cold.py`** | `MEASUREMENTS.md:1343`, `:1351` |
| chain interference radius | **~6–15 strides** | `holo2/src/holo2/solve/DESIGN.md:370`, `:844` |
| run-streaming / lanes | 86 → **87** certificates (first cross-lane exclusivity); fragment class **4/12 → 12/12** whole pre-subdivision | `MEASUREMENTS.md:1785-1786`, `:1788` |
| v1 clipped edge windows | **193 and 131 cells** on the differential's own arms, dropped under the floor | `holo2/src/holo2/solve/DESIGN.md:337` |
| "~95% coarse" | **WITHDRAWN** — sole source a non-closing 2026-07-31 A/B; real shares e029 K **55.4%**, e023c HP 89–92%; e029's coarse lane alone (1,075) could not close K=1,356 | `holo2/docs/H4-LANES-PLAN.md:31-35` |
| subdivision | F-04 closed: `run_subdivision` arm **88 = 88** vs v1 | `MEASUREMENTS.md:1091`, `:1174` |
| tx=0 residue origin diversity | **v1 4.94 vs holo2 2.00** distinct window origins per tile; the shifted-window experiment ran **567 attempts, 311 accepted placements, ZERO certificates** on the 13 hardest tx=0 tiles | `holo2/docs/kparity/K-PARITY-STATE.md:63`, `:66-67` (Wave-1 M2; backing `scratch/holo2-catchup/detect/probes/f7-*-xerox.md`) |

**The straddle-audit refusal path and declared-vs-voted pitch** (Appendix B
seed rows) have **no measured number on any side** — see GAP G-08.

### 2.2 Evidence, ownership and context

**holo1.**

| number | value | cite |
|---|---|---|
| 2×2 factorial (BP × context) | baseline/BP/context/combined **742 / 747 / 749 / 757** decimated, **742 / 747 / 746 / 752** native; emitted-cell BER PAVA→context **1.9179% → 1.3509%** (dec), **2.6440% → 1.8757%** (native) | `docs/RECEIVE-DESIGN-EVIDENCE.md:611` |
| context calibration quality | **all 70 eligible region fits adopt** on both footings; held-out pilot log loss 0.08147 → 0.05698 (dec), 0.09690 → 0.07480 (native) | `docs/RECEIVE-DESIGN-EVIDENCE.md:612` |
| K calibration bars | `CAL_MIN_PER_CLASS=10` "frozen E023 marginal-calibration bars"; `N_CONTEXT_BINS=9` "frozen ctx-pava-v1 constants from E023b.1" | `src/holo/receive/detect.py:31`, `:35` |
| the bounded-LLR invariant (018.7) | each calibrated capture output bounded by its PAVA label count **before** this module; independent captures then summed; **the boundary deliberately does NOT saturate a multiview sum** | `src/holo/receive/tiles.py:28-33` |
| **E9 — local vs page-global calibration, a sharp measured NEGATIVE** | **ZERO certificates, every arm, both lanes, all 21 e029 residue tiles**; H1 217k/336k labels, 15/25 tiles, 0/0 certs, −0.79/−1.04 pp; H2 389k/561k, 28/42, 0/0, −0.96/−1.09 pp; 651 s wall, peak RSS 5.6 GB | `docs/INDEPENDENT-PLANES.md:1223`, `:1178-1179`, `:1181`; instrument `measure/calibration/` |
| shipped K head granularity | **photometry per window, calibration per window, context page-global — and neither head has ever seen a certified payload cell as a label** | `docs/INDEPENDENT-PLANES.md:1193-1195` |
| campaign-wide certificate audit | **0 wrong certificates in 69,066,304 audited cells** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3029` |

**holo2.**

| number | value | cite |
|---|---|---|
| pose-id ordering | handed the lowest extent **90.3–94.1%** of contests; the cost of that order is **27 e029 + 27 xerox** certificates | `holo2/docs/kparity/DIVERGENCE-LEDGER.md:65`; `holo2/src/holo2/solve/payload.py:107-108` |
| v1's key rule rescues | **26–29 of 30 e029 + 27 of 48 xerox, 0 regressions in 1,910 + 1,882** | `DIVERGENCE-LEDGER.md:65`; `K-PARITY-CATALOG-draft.md:445`; `holo2/docs/CATCHUP-PLAN.md:416` (**not** `:436-448`) |
| competing poses disagree | on **9.15% / 14.30%** of cells | `holo2/docs/CATCHUP-PLAN.md:423` (**not** `:446-448`) |
| context bin −1 share | **6.15% tile-scoped vs 1.56% window-scoped**; alternative reading **6.6–7.5%** of a component's observed cells, forgone offsets **±2.3…±3.0 nats** | `holo2/docs/kparity/RULINGS.md:521-522`; `DIVERGENCE-LEDGER.md:66`; `CATCHUP-PLAN.md:437-440` |
| CA2 context fit | **4 fits each sheet, every one ADOPTED, zero refusals**; held-out log-loss deltas **−0.052 to −0.094** | `holo2/docs/CATCHUP-PLAN.md:473-476` (**not** `:479-487`) |
| orphan piece loads | **30.9%** of piece loads own no cell on the archived e029 store | `holo2/src/holo2/solve/payload.py:412` |
| post-F1 ownership gaps | **0 of 4 pools** on either real sheet had a fit that had seen a re-read's pieces; **0 of 255** xerox re-read poses had a published window loss; **0 of 6** re-read windows had a loss for their live pose while **6 of 6** had one for the parent | `holo2/src/holo2/solve/calibration.py:594-595`, `resample.py:51`, `ctx_apply.py:133-135` |
| **certified-label enrichment (CA1)** | wall **81.6 → 137.4 s = +68%**; **yield on this corpus: ZERO**; mechanism ~100 label cells → 4,096 (~40×); ruling DIALED, DEFAULT OFF; **v1 never fed certified reconstructions to the ctx/PAVA channel, so this is a holo2 EXTENSION, not parity** | `MEASUREMENTS.md:978`, `:983`, `:980-981`, `:994`, `:987-990` |
| **same-capture cross-rung pooling** | REFUSED by ruling J2-4; the forgone yield **is** measured: summing the four corrected components certifies **+2 e029 tiles no single footing closes ((42,9), (22,1))** and reaches the `below_floor` class — **16 of 78 gap tiles at 1.2–4.9% cell error refused for coverage** | `DIVERGENCE-LEDGER.md:67`; ranked H3 in `scratch/holo2-catchup/detect/DETECTION-GAP.md:113` |
| RF1 adoption-gate flips | re-scored both ways: **zero flips in 237 revisions (89 e029 / 148 xerox)**, worst margin ~1800× `MIN_HELDOUT_GAIN` | `K-PARITY-STATE.md:58-61`; backing `scratch/holo2-catchup/real/rf1-gate-flips.{md,json}` |

**holo3.** `measure/pooled_ctx/README.md` is the pooled colour-context arm's
decode evidence: the **null proof** (2026-08-30) against a pristine `main`
at `259e622` — three cases (`null-k`, `null-color`, `mixed`) with identical
payload sha, identical certificate sets (49/49 and 279/279) and **identical
per-plugin job counts row for row**. `measure/ctx_equivalence.py`,
`ctx_fixture.py`, `ctx_bench.py` are the K-side equivalence instruments.

### 2.3 Refinement

**holo1 vs holo3, the sharpest measured comparison in the record.**
`src/holo/receiver/docs/conversion_docs/GAPS.md:82-107`: on the xerox K sheet v1 won **18 of
its 1,930 certificates by refinement and all 18 are in column 0**; holo3
certified **13 of those 18 with no refinement at all** (7 at the finest
level, against a population where only 4.7% of certificates come from the
finest level — "holo3 leans on resolution where the old receiver leaned on
geometry"); **the 5 it did not get are 5 of holo3's 8 missing tiles**.
`GAPS.md:138-160` is the tile-by-tile "why the refinement did not reach five
of them"; `GAPS.md:377-381` records that **why holo3's refinement was not
scheduled at those five rows is inference, not measurement** — its
refinement writes no events.

**The zero-adoption finding.** `src/holo/receiver/docs/conversion_docs/PARITY.md:443-448`:
across the five completed post-change volumes `refine` fired **717** times,
`refine.color` **3,899** and `revisit` **593**, producing **0 `route=refine`
poses — zero, everywhere**; on c2-cmy7 and sheet I that is 788 and 2,950
colour-lane fires for no adoption. `POST-FORENSICS.md:98-262` adjudicates
it: §A.1 why the refusals are honest not a stuck gate, §A.2 the genuine
instrumentation gaps, §A.3 `revisit` is the one genuinely zero row and it is
honest, §A.4 reconciles it with GAPS' "53 of 58 colour misses = missing
refinement lane". `POST-FORENSICS.md:463-481` (§C.4) records steps 3 and 6
as **UNKNOWN, honestly** — the events in hand cannot isolate what re-fired
the extra scans.

**holo1 cost numbers.**

| number | value | cite |
|---|---|---|
| colour refinement cost, zero yield | **~550 s** on the 20×2 scrap corpus; 986 window crop+grid fits across 16 barriers; **~94% of the payload bucket** in `sampling_calibration_ctx`; BP/CRC ~38 s total | `docs/PAYLOAD-MEASUREMENTS.md:213-219` |
| candidate-loop crop regression | base.payload **532 → 924 s** | `docs/RECEIVE-DESIGN.md:75` (the **v0.41** row — the seed labels it v0.42) |
| payload-rework A/B, four arms | 1555.4 / 1724.0 / **1485.9** / 2036.5 s wall; base.payload 550.3 / 532.2 / **457.4** / 959.9 s; RSS 16.4 / 23.1 / 27.4 / 27.2 GiB — **certificates 604 in all four** | `docs/PAYLOAD-MEASUREMENTS.md:196-201` |
| R-lane qualification | default flags **1,166 s CPU, 601 certificates**, 95 windows parked across 8 M-lanes, distinct-symbol reach 601/1294 | `docs/PAYLOAD-MEASUREMENTS.md:288-291` |
| the pose writer — measured negative | W6 state `9514d618…` VERIFIED, 5,549 certs; **all 334 open (tile, stream) slots (Y 332, C 2) over 333 tiles** unmoved | `docs/INDEPENDENT-PLANES.md:833-838` |
| the refinement search box | `ANGLE_LIMIT_DEG=0.15`, `PHASE_LIMIT_CELLS=0.25`, `MIN_POSE_PILOTS=30`, `MIN_HELDOUT_GAIN=1e-4`, `PILOT_MISMATCH_SLACK=0.005` — **17 constants, no provenance comment on any of them** | `src/holo/receive/certified_refine.py:45-64` |

**holo2 cost numbers.**

| number | value | cite |
|---|---|---|
| the re-read population | **269/1,228 e029 and 272/1,282 xerox** windows already carry two committed poses; **4,392 / 4,117** evidence pieces hang on a non-live pose, and the live pose "currently has none" | `K-PARITY-CATALOG-draft.md:545-549`; `DIVERGENCE-LEDGER.md:71` |
| **RF1 yield: zero three ways** | W2 resume **+0/+0** with 270/275 revisions adopted 100% and none read; W3 **+0**; W4 **−1 / +0** | `MEASUREMENTS.md:1195-1201` |
| RF1 cost | one adopted revision **~3.7–3.8 s** of fire time; real-sheet wall e029 1,126.9 → 1,347.1 s (**+220 s, +19.5%**), xerox 719.0 → 1,367.2 s (**+648 s, +90%**) | `MEASUREMENTS.md:1218`, `:1228-1229` (seed cites `:1205-1213` / `:1214-1219` — both wrong) |
| RF1 churn | **+1,784 commits on e029 (+15.5%), +1,618 on xerox (+13.2%), for zero certificates**; 274 expansions × 270 = 73,980 mints vs a dial-off control's 2 × 0 | `MEASUREMENTS.md:1222-1225` |
| RF1 done coverage went DOWN | e029 **−3,996** cells, xerox **−1,449** cells | `MEASUREMENTS.md:1234-1236` (seed cites `:1220-1225` — wrong) |
| F1+F2 combined | yield **+27 e029 / +32 xerox** (1,911→1,938; 1,882→1,914); cost **+112% e029 (1,127→2,385 s) / +386% xerox (719→3,494 s)**; commits 11,513→13,701 and 12,263→19,252 | `MEASUREMENTS.md:1129-1130` (table), `:1136` (prose) |
| the W4 gap closed | **60 of the 83** gap tiles the W4 line measured are gone (e029 30→3, xerox 48→19, demo9 5→5) | `MEASUREMENTS.md:1102-1103` |
| the first holo2-only tiles | (0,42,3) e029; (0,5,21), (0,7,0), (0,27,36) xerox — v1 retains uncertified evidence on all four | `MEASUREMENTS.md:1107-1110` |
| re-read census | **239/239 and 255/255 `resampled`, no refusals** | `holo2/src/holo2/solve/place_sched.py:456` |
| F2 resume | **+13 / +12** — **and explicitly superseded**: `HANDOFF-F2.md:654` says these "PREDATE R2/R3/R4 and must not be carried forward as the post-fix result" | `holo2/docs/CATCHUP-SUMMARY.md:58`; `scratch/holo2-catchup/study/HANDOFF-F2.md:236`, `:654` |

**holo3.** `src/holo/receiver/docs/conversion_docs/PARITY.md:456-660` carries per-volume
`refine` / `refine.color` / `revisit` fire counts and credited certificates
(all zero); `measure/parity/analyze_post.py:1-30` documents why row-for-row
job deltas are meaningless across the row-vocabulary change.

### 2.4 The done gate / done geometry

| side | number | cite |
|---|---|---|
| holo1 (census, simulated counterfactual) | **719 of 1,479 committed placements = 48.6% pixel-gateable**; l02+l03 spent **630 placements to mint 11 certificates**; the m00 `--complete` tail spent **440 windows / 160 priced colds / 160 rest-word decodes to mint 2**; **gated windows minted zero certificates, provably**; **r00–r03 zero — the gate never touches live refinement work**; l01 near-zero because at **54.8% frontier density** nearly every 200-cell window touches an uncertified tile — the gate is decisive from ~98% | `docs/DONE-GEOMETRY.md:257-273`, `:280-283`; restated `holo2/docs/DESIGN.md:46-49` |
| holo1 | L1 never fired: `payload.pruned_terminal_patches = 0` everywhere | `docs/DONE-GEOMETRY.md:284-287` |
| holo2 (realized rate) | e029 **45 / 1,273 = 3.5%**, xerox **42 / 1,324 = 3.2%**; off-census floor +44 / +11 | `MEASUREMENTS.md:1246-1247` |
| **the two are not a ratio** | v1's 48.6% is a SIMULATED counterfactual, holo2's 3.2–3.5% a REALIZED rate; holo2 1,273/1,324 vs v1's l00–l03 = 1,172 | `MEASUREMENTS.md:1249-1256` |
| holo2 concentration | last-decile **e029 44/45 = 97.8%, xerox 42/42 = 100%**; coarsest rung ppc 2/1 **16.2% [44/271] / 12.2% [39/319]**; subdivision-child denominator **0/57 e029, 0/15 xerox** (pooling the two was a review-retracted denominator error); **ZERO at ppc 4/1 and 8/1** | `MEASUREMENTS.md:1258-1266` (seed cites `:1264-1275` — wrong) |
| holo2 detail tables | per-rung and per-decile | `scratch/holo2-catchup/real/done-gate.md:17-31` (e029), `:59-73` (xerox) |
| holo2 coupling | eager payload's `done_covered` fires **21 eager vs 42 phased**; 2,018 → 4,478 placement fires | `MEASUREMENTS.md:360` |
| holo3 | `measure/donegeo_{parity,realstate,saturation,timeline}.py` are the instruments; `src/holo/receiver/tests/test_h3_done_geometry.py` the pins. **No holo3 measured gating rate on a real sheet is recorded** — GAP G-09 |
| owed on both sides | **no fragment/confetti done-geometry census** — the 48.6% is one intact dense sheet, the gate's favourable regime | `docs/DONE-GEOMETRY.md:293-296` |

### 2.5 Close

| side | number | cite |
|---|---|---|
| holo1 doctrine | the stop is the SHA, never a count; a stream that solves but fails its digest is a failed volume, never a partial one | `src/holo/receive/fountain_close.py:5-11` |
| holo1 | five verified closes: c3-cmy7 **301,600 B**, c2-cmy8 **718,413 B**, xerox-K and hp-K **465,580 B**, c2-cmy7 **686,859 B**; two opens: hp c3-cmy8 **≥748 symbols short**, hp c2-cmy8 metadata rank **0 → 14 of 24** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3010-3029` |
| holo1 | the e028 verified-close trap: a retained VERIFIED close stores only SHA/length, so `CloseExecution(verified, payload=None)` trips the verified-payload invariant | `src/holo/receive/production_close.py:68-72` |
| holo1 | close detach is lossless — a close is a pure derivation from the certificate set and a later closing run recomputes it byte-exactly | `src/holo/receive/session.py:662` |
| holo2 | H3bis real sheet **1,359 certified vs v1's 1,930** for the same 465,580 B, sha byte-identical | `MEASUREMENTS.md:602`, `:617` |
| holo2 | xerox K-stop **1,356** (= K exactly), 6,839 commits, 69.4% done coverage, 410 s; `--complete` **1,882**, 12,263 commits, 96.0%, 719 s | `MEASUREMENTS.md:1296-1297` |
| holo2 | e029 K-stop **1,357** (surplus 1), 6,441 commits, 507 s; `--complete` **1,911**, 11,513 commits, 97.5%, 1,127 s | `MEASUREMENTS.md:1307-1308` |
| holo2 | **H6 UNMET**: e029 1,911 vs 1,940 = 98.5%, **29 tiles short**; xerox 1,882 vs 1,930 = 97.5%, **48 tiles short** | `MEASUREMENTS.md:1310-1311`, `:1323` |
| holo2 | F2-tree parity **e029 −2 / xerox −16 / demo9 −5**, zero-wrong on all three, walls 2,385 / 3,494 / 33,945 s, RULING I1 NOT MET | `MEASUREMENTS.md:1086-1088`; `K-PARITY-STATE.md:87` |
| holo2 | **every v1-only tile on both real sheets is ATTEMPTED-FAILED**; NEVER-ADDRESSED and ADDRESSED-NOT-ATTEMPTED are 0 | `MEASUREMENTS.md:1120-1121` |
| holo2 | gap column concentration: xerox tx=0/tx=34 = **92% of 48**; e029 tx=32/ty=22 = 9 each of 29 | `holo2/docs/CATCHUP-PLAN.md:324-326`; `MEASUREMENTS.md:1211-1213` |
| holo2 | close consult **1,358 consults = 34.1 s = 6.0% of wall**, linear at ~30 µs/certificate | `holo2/src/holo2/solve/close.py:46-47` |
| holo2 | trust floor: rank **24** = unique word; **48 distinct equations** = the false-accept floor, residual ≤ ~2⁻²⁴ | `holo2/src/holo2/solve/close.py:57-60` |
| holo2 | close preemption worth **3.7×** (v1's 49.67 → 13.46 s) — **v1's number; holo2 never re-measured it** | `holo2/src/holo2/engine/DESIGN.md:492-494` |
| holo2 | v1's loser ledger holds **2 (e029) / 5 (xerox) / 73 (demo9)** losers, every real-sheet loser anchoring already-certified territory; the word firewall changes word-DECODE verdicts on **114/55 tiles** but **conflict verdicts are zero under both scopes** | `K-PARITY-STATE.md:69-75`; backing `scratch/holo2-catchup/real/{f6,f8}-counts.md` |
| holo3 | every close in the campaign record is byte-exact where it ran: `PARITY.md:441` "**Every close that ran stayed byte-exact.** Five of five completed volumes recovered their payload sha exactly. The changes moved WHICH tiles certify; they never broke payload reconstruction" | `src/holo/receiver/docs/conversion_docs/PARITY.md:441` |
| holo3 | pooled close: vol 7 closes **ONLY** with pooled-fountain algebra AND three pooled captures (single capture: shortfall 125) | `src/holo/receiver/docs/conversion_docs/14-acceptance.md:255-256` |

### 2.6 Union and retry

| side | number | cite |
|---|---|---|
| holo1 schedule | SCAN → UNION (only where ≥2 components) → advisory PRECLOSE → selective RETRY150 | `src/holo/receive/payload_engine.py:210-234`, `:236-256`, `:258-262`, `:264-302` |
| holo1 | multiview certificate union: dec 757, native 752, shared 740, dec-only 17, native-only 12, **union 769 — all 769 GT-correct** | `docs/RECEIVE-DESIGN-EVIDENCE.md:615` |
| holo1 | view correlation over **6,049,897** paired common payload observations: LLR Pearson **r = 0.9697**, hard-decision disagreement **2.2842%** | `docs/RECEIVE-DESIGN-EVIDENCE.md:616` |
| holo1 | the v0.27 union fix: SCAN gets this capture's blocks only; the merged frontier feeds UNION | `src/holo/receive/production_payload.py:424-430` |
| holo1 | multi-scan persistence: s000 45/248 + s001 27/150 → **72 provenance-distinct placements / 264 unique tiles**; duplicate re-ingest preserved state byte-for-byte | `docs/RECEIVE-DESIGN-EVIDENCE.md:499` |
| holo2 | per-attempt caps: **scan 641 attempts mean 91.2/120**, **union 88 mean 120.0/120**, **retry150 386 mean 299.2/300** | `MEASUREMENTS.md:1439-1441` (seed cites `:1449-1455` — wrong) |
| holo2 | certified and failed populations do not overlap: **certified n=160, median 2 iterations, max 17**; **failed n=955, median 120, max 300** | `MEASUREMENTS.md:1443-1444` |
| holo2 | worst per-(arm,key) lifetime **11,820 iterations = 61 BP attempts (scan ×29 + retry150 ×25 + union ×7), never certified = 6.2× one ladder walk** | `MEASUREMENTS.md:1467`, `:1475-1479` |
| holo2 | same-DPI union A 39/64, B 36/64, **joint 40/64 (Δ +1)**; **101 union descriptors spent, 14 certificates minted by the union route**; the two acquisitions disagree about only **3** tiles and the one joint-only tile was minted by `retry150`, not union | `MEASUREMENTS.md:733-747` |
| holo2 | cross-DPI union (1200 + 2400): 39 / 39 → **41/64**; joint = exact union of the two singles' sets; driver wall 342 s | `MEASUREMENTS.md:775-784` |
| **holo3, the largest union yield on paper** | sheet H seven-capture max-stack: **`tiles.union` minted 1,818 of 4,237 certificates = 43%** | `scratch/holo3-overnight-events/sheetH-maxstack-report.json → rows[3]` |
| holo3 | first cross-dpi union certificates on paper: **1,508 of the 4,307** four-capture harvest | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:18-19` |
| **holo3 — the premise correction** | **holo3 already pools across captures**: `tiles._combine` sums per-capture post-context LLRs, so `tiles.union` IS the multi-scan law and `tiles.retry` already re-runs it at bp150; **the only discarded evidence is WITHIN-capture window overlap** (108 of 138 cover entries on the mixed sim had 2–9 covering windows). The pooling amplitude window, measured at the codec: pooled closes from noise amplitude 1.2, winner-take-all union from 1.6, a single view from 2.4 — **on synthetic independent noise, which is true across captures and false within one** | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:183-199` |
| holo3 retry, post-change | attempts rose 4.7× on step 2, 0→2,694 on step 3, 3.7× on step 5, **23× on step 6 (1,028 → 23,881)**, 1.9× on step 7 — minting only **50 / 0 / 21 / 13 / 99** certificates | `src/holo/receiver/docs/conversion_docs/PARITY.md:449-455` |

### 2.7 The colour stack

**holo2: none, by construction.** `holo2/docs/CAPABILITIES.md:43` — colour
codings are "identities nameable and rows buildable at the format layer",
verified column empty of any decode; `CATCHUP-PLAN.md:272` "cmy8 sheets have
no reader by design". The only colour-shaped numbers in `holo2/docs/` are
**imported v1 priors** (`H4-LANES-PLAN.md:33` coarse-lane shares, sourced to
`COLOR-UPLIFT-MEASUREMENTS §9.8`) and byte targets
(`holo2/docs/DESIGN.md:893`). **Do not cite either as a holo2 measurement.**

**holo1: the whole record.**

| number | value | cite |
|---|---|---|
| **campaign yield** | **10,706 → 12,516 certified tiles, +1,813 / −3** (net +1,810, +16.9%), five verified closes, one of them a volume never recovered before | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3029`, `:3264` |
| gain attribution | the uplift target contributed **133 of 1,813**; **1,476 came from xerox c2-cmy7** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3268` |
| the ladder | A0 → A1 region registration → **A2 [STRUCK]** → A3 window photometrics → A4 kind heads → A4b KnownField-conditioned marginalisation → A5 per-plane context; every stage adopts only through the three-way held-out comparison and **every refusal is a BIT-EXACT null** | `docs/RECEIVE-DESIGN.md:686-720`; `src/holo/receive/color_stack.py:1-20` |
| **saturation floor 0.30** | swept over 0.15/0.20/0.25/0.30; at 0.30 l00/r00/m00, **0 regressions, 4 of 5, +11 predicted**, margin **.079** (.221 m00 vs .455 m01); cost **1.03 CPU s per 3.23 M cells**; robust on re-check (22/64, 0.037475 → 0.035083 = −6.4%; later "sits between .276 and .338"; later "sits 0.002 from the empty band") | `docs/COLOR-UPLIFT-MEASUREMENTS.md:397`, sweep `:351-397`, cost `:345-346`, re-checks `:677`, `:745-749`, `:960-965`; constant `src/holo/receive/color_stack.py:249` |
| **three demapping iterations** | `DEMAP_ITERATIONS=3`; **B7 MET at 3**: p\* = 0.0275 ≥ 0.025 (baseline 0.015, iters-2 0.0225 — NOT MET); tiles-CRC deltas +1, 0, +105, +322, +454, +478, +477, +268; at p = 0.0275 the arm reads **480/480 against the baseline's 2/480** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:2636-2656`; constant `src/holo/receive/color_attempts.py:57` |
| **A5 multi-state context matrix** | l00 head-to-head: hp c3-cmy8 179 → **251 (+40%)**; xerox c3-cmy7 333 → **413 (+24%)**; xerox c2-cmy8 3,596 → **4,006 (+11%)** — while the per-plane PORT is **byte-identical to OFF on all three**. Why the port loses: the label population is **83–84% WORD**, and the port improves word by .09–.19 nats while degrading dust by .04–.20 → `region_gate_failed` every time | `docs/COLOR-UPLIFT-MEASUREMENTS.md:2112-2114`, `:2129-2142`, gate rows `:2119-2125`; constants `src/holo/receive/color_context.py:124`, `:136` |
| A5 on the uplift target | hp c3-cmy8 **663 → 796 (C 620→740, M 43→56, Y 0)**, address level **+127 / −1**, adopted in **all 17 lanes**, **CPU −5.3%** — the campaign's largest single move | `docs/COLOR-UPLIFT-MEASUREMENTS.md:2187-2200` |
| A4b (PK10) | exact end-to-end null on hp c3-cmy8: **663 certificates cert-for-cert identical to the archive, M = 43, bar M>43 NOT met**; the standing three-way gate refuses on the DUST leg at all fourteen conditioned lanes. Its three-way pre-gate variant keeps **2 strata of 9 and +11 certificates** where the single test keeps **8 and +19** | `docs/RECEIVE-DESIGN.md:890-896`, `:886-888` |
| A4b conditioning tier law | a two-lane library unit read **+19 on xerox c2-cmy8**; the full twelve-lane replay reproduced that lane exactly and finished at **net −5** (1 new address, 18 re-timings, 10 later losses) | `docs/RECEIVE-DESIGN.md:1051-1054` |
| A3 damage/gain asymmetry | l00tax over the adopting pair: **20 worse / 1 better / 0 unchanged, p = 2.1e-5**; loss rate 2/23 = 8.7% vs the capture's 11.4%. **"A3 at patch scale reproduces its DAMAGE and not its whole-page GAIN"** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:1437-1444` |
| **the cmy7 bound order** | "cmy7: scalar-temperature + 6-offset head fit on the selected arm's held-out scores via the `(131y+17x)&2` sub-split, refusal ⇒ the literal current uncalibrated path, **L∞ = 20 bound applied last**" | `docs/RECEIVE-DESIGN.md:710-712`; constant `src/holo/receive/color_fitting.py:35` (**no provenance comment there**) |
| the fact behind that bound | **19% of emitted cells saturate the L∞=20 bound and the WRONG cells sit at median \|score\| 18.8/20** | `src/holo/receive/color_calibration.py:8-11`; restated `docs/RECEIVE-DESIGN.md:84` |
| **head floors** | `HEAD_N_OFFSETS=6` and `HEAD_MIN_SEARCH_PER_STATE=10` (mirrors K's `CAL_MIN_PER_CLASS`) have provenance; `HEAD_SCALE_MAX=10.0`, `HEAD_GRAD_TOL=1e-10`, `HEAD_LINE_SEARCH_STEPS=40`, `HEAD_MIN_VALIDATION=40`, `HEAD_MIN_VALIDATION_PER_STATE=3` **do not** | `src/holo/receive/color_calibration.py:53`, `:71`; unprovenanced `:58`, `:62`, `:68`, `:72-73` |
| specimen-tier validity | `outside_domain = 0` on every specimen; wrong certificates 0 everywhere; **agreement 1.000000000**; the negative control certifies 0; sweep 941 s, per patch 37–327 s | `docs/COLOR-UPLIFT-MEASUREMENTS.md:1426-1430` |
| force-null invariant | xerox c3-cmy7 **720/720 cert-ID identical**; wrong certs **0 / 8,588,160 cells, agreement 1.0** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:1049` |
| a correction the record makes about itself | **"A3 never cost 12 GiB. The baseline was contended."** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:1299` |

**holo3 colour.** `src/holo/receiver/docs/SCHEDULE.md:426-520` is the per-mechanism sim
evidence; the colour refinement row fires 14 times with 2 adoptions on the
colour sim, certificate set and payload byte-identical to the pre-lane
baseline (279/279, every certificate re-checked against the emit ground
truth — zero wrong), workers 1 == 8 byte-identical. Real-sheet colour
numbers are the parity/battery rows in §1.

### 2.8 Plane fields, swim, planek, local context, uplift

**holo2: none.** The terms *swim*, *planek*, *plane field*, *local context*
and *uplift lane* do not occur in `holo2/docs/`. Its nearest analogue is the
prepared-planes memory record: workers-8 and workers-4 both **SIGKILLed
(exit 137)** on a 64 GB machine while serial survived; ingest holds **~19.5
GB resident**; the killed serial run projected 4–6 h and its gen-clean
sibling completed **1,471 s serial at 95.3% utilisation, fire p90 2.6 s**
(`MEASUREMENTS.md:2308-2320`; doctrine `holo2/docs/DESIGN.md:635`).

**holo1.**

| number | value | cite |
|---|---|---|
| **W6, the primary bar FAILED** | median dead-band Y residue **24.0/53 against the pre-registered ≤5/53** (baselines 39/53 archived, 44/53 from the mid-run table) | `docs/PLANE-FIELDS.md:915-918` |
| **W6 yield, nonetheless** | **5,297 → 5,549 (+252; Y 1444 → 1629)**; whole-page Y residue 517 → 332, C 66 → 2, M 3 → 0; **close VERIFIED byte-exact** | `docs/PLANE-FIELDS.md:918-921`; `docs/RECEIVE-DESIGN.md:1740-1741` |
| W6 band structure | band 1 (cols 8–11) 164 → 121; band 2 (15–19) 189 → **62**; band 3 (27–29) 108 → **127 — WORSE**; column 8 (zero Y evidence) 53 → 46 | `docs/PLANE-FIELDS.md:927-930` |
| W6 confounds, stated by the doc | zero-evidence bands defeat extrapolation; adoption is **all-or-nothing per page**; **tree drift uncontrolled — the 5,297 baseline is the August `c4-row` tree, so part of +252 may be receiver drift** | `docs/PLANE-FIELDS.md:931-943` |
| W6 probe cost | **16,125 measurements / 5,376 sites for 42.7 s + 0.052 s solve**; run 2 h 18 m, 12-level plan × 3 captures, **~11.6 GB peak** | `docs/PLANE-FIELDS.md:921-924` |
| V0 blind gate | **PASSED at Spearman +0.997** on `dY_rel_x` per tile column (gate ≥0.7) | `measure/plane_fields/README.md:48-52` |
| **E4 — Y-context circularity closes nothing** | baseline dead 8.744 / control 6.590, gap **+2.155**; with Y = GT, dead 6.317 / control 4.137, gap **+2.180 — wider by 0.025**; certified 1 of 6 → **4 of 6**. Method control exact: C,M = GT reproduces the baseline on all eight tiles to every digit | `docs/INDEPENDENT-PLANES.md:749-752`, `:766-780` |
| **E6 — Y's breadth was the CARTRIDGE** | healthy AltaLink σ **M 37.7 / C 37.3 / K 36.8 / Y 34.8 µm**; same code on e028 **Y 46.0 / K 39.6 / C 38.1 / M 36.8**; the stable statistic is **+7.7/+7.7/+10.5 µm on the M281 and −2.5/−2.2/−3.0 on the AltaLink**. M281 Y bars are narrowest **and** faintest (FWHM 98.9 vs K's 119.1 µm, peak 0.43 vs 0.61) — thin ragged development, not scatter | `docs/INDEPENDENT-PLANES.md:265-271` |
| **E8 — the realizable non-oracle loop** | G1 one iteration Δ **−1.07 / −1.57 = 44 / 64% of oracle**, certs 0/2; two iterations **regresses** to 25/24%; Y term OFF **+1.76/+1.57**; **self-column removed reads −585/−646%** (the circularity, exposed). G2 production-like: (e1) **37 / 64%**. Cost **8,875 s, peak RSS 13.97 GB** | `docs/INDEPENDENT-PLANES.md:1021-1032`, `:1001-1002` |
| **PK6/A2 — the line closes as a measured negative** | ALL-FOUR conjunction: xerox c2-cmy7 (PRIMARY) 0.0149 placebo / 0.001 bootstrap, ΔMSE +36.2, RMS 0.0357, ΔMSE_diff +21.7 → **NO**; the other three also NO, **each failing a DIFFERENT leg**. τ ≈ **0.1–0.3 print dots is REAL** on every capture and clears the shrinkage-MSE bound on the primary; own-window κ=8 reach on the residue is **C 20.8% / M 16.0% / Y 0% ≪ 50% — FAILS DECISIVELY**; Y is independently unmeasurable at fine pitch (9–22% saturation) | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3574-3600`, `:3515-3517`, `:3582-3583`; `docs/RECEIVE-DESIGN.md:693-701` |
| dial status | **DEFAULT OFF, null-proved**; `--refine` is required for any field activity | `docs/RECEIVE-DESIGN.md:1712-1751`, `:1729-1730` |

**holo3.**

| mechanism | number | cite |
|---|---|---|
| **the field line** | units fix: the fitter measured in cells while every consumer read dots — effective clamp had been 6 dots at c3 / 4 at c2, effective floor 0.75 / 0.50 dots; post-fix the displaced-sim Y field reads **1.024 dots against an injected median of exactly 1.000** | `src/holo/receiver/docs/conversion_docs/ARMS-2026-08-31.md:13-22` |
| **the field contributed nothing on the best-ever sheet-I run** | 54 fits, **5,211 CPU-s, ZERO PlaneField facts in the snapshot** — the 5,543 record was achieved with the field effectively off | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:28-35` |
| the anchor tier's justification | the PAPER measurement (sheet I vs recorded ground truth, 481 tiles): **gain 0.94–1.00, per-column Pearson +0.982, zero saturation on Y**, where the photometric estimator reads gain 0.53; on every sim the photometric tier dominates **122–163×** | `src/holo/receiver/docs/conversion_docs/ARMS-2026-08-31.md:36-44` |
| median publication | the mean-of-others form measured **(0,0,D) → (−D/2, −D/2, D)**, 0.45–0.56 dots of spurious sibling publish; clamp-first annihilates a 0.97-dot common part | `src/holo/receiver/docs/conversion_docs/ARMS-2026-08-31.md:46-52` |
| **the swim** | field-hinted search bound buys reach past the clamp — **4.043 dots recovered at a 4-dot injection where the blind search clips at 3.0**; the existence proof was **re-bracketed twice as field repairs erased it (2 → 3.5 → 4.0 dots)**; licence table: the honest field DEGRADES past its clamp (**26% at 4 dots, 13% at 5**) while the swim holds **94–103% inside its bound** | `src/holo/receiver/docs/conversion_docs/ARMS-2026-08-31.md:54-79` |
| **planek (Y-as-K)** | `measure/yask/README.md`: on sheet H, 324 tiles all C/M-certified in production and 105 Y-certified there, 219 not — arms **C0 raw blue 0 certs / 0 adds** ("magenta darkens blue at 60% of yellow's strength — the naive read is worthless"), **C1 25 certs / +1**, **A0 39 certs / +5**; **zero wrong certificates anywhere in the battery**, null arm certifies nothing | `measure/yask/README.md:12-26` |
| planek on paper | sheet I run 2: **281 certificates for 2,278 cpu-s = 8.1 cpu-s per certificate**; **82% cascade** (mean 2.21 same-run neighbour predecessors), 51 seeds / 230 descendants, chains **7 generations** deep, middle 50% of mints inside 9.8% of the journal | `experiments/034-sheet-i-full-readout.md:80-93` |
| **tiles.local (local context)** | NULL: byte-identical payload and certificate sets on both clean sims at workers 1, every per-plugin job count unmoved. EXISTENCE (K): without the row **45 certificates and the volume is LOST**; with it 15 fires, **48 certificates and the volume comes back byte-exact**, a strict superset, zero wrong. EXISTENCE (colour): without **285**, with **291 — +6, every one a C-stream certificate on a patch tile**, i.e. the gain lands on the misregistered plane and nowhere else | `src/holo/receiver/docs/SCHEDULE.md:436-489` |
| what the colour sim would NOT do | three other local anomalies were measured and the region head absorbed all of them without losing a certificate — contrast compressed to 35%, a 160-level per-plane photometric offset, and a 0.67-cell per-plane registration jump on its own. **"Read the +6 as an existence proof of the MECHANISM, never as a yield estimate"** | `src/holo/receiver/docs/SCHEDULE.md:490-497` |
| tiles.local on paper | sheet I machine 2: minted **213** certificates at **73% of the run's CPU**; the four-run chain's later runs read 26 then 2, at ~3,000 cpu-s each | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:30-31`; `experiments/034-sheet-i-full-readout.md:89-93` |
| **union vs per-origin for `tiles.local`** | `measure/local_ab/README.md:23-33`: **PER-ORIGIN WINS AND THE UNION NEVER WON ALONE** — two crop cases off sheet I's three 2400 dpi captures, 153 armed subjects: union 2 certificates (both also won by per-origin, **0 union-only**), per-origin **6** (4 per-origin-only), N0 null 0. Artefacts `scratch/local-ab/` (3.3 GB: `runs/{I-nw,I-tl,sim-*}`, `reports/`, `sheet-I-{certified,residue}.json`, 14 logs) | `measure/local_ab/README.md:23-33` |
| **per-tool accounting for the local arms** | K arm 15 fires / 3.25 CPU-s / 3 certs = **1.08 s/cert = 8% of run CPU**; colour arm 33 fires / 141.3 CPU-s / 6 certs = **23.6 s/cert = 47% of run CPU** — ~20× dearer per fire because it re-runs the entire colour head. **Both are priced at 220 and that is a KNOWN MISPRICING, flagged not patched** | `src/holo/receiver/docs/SCHEDULE.md:508-520` |
| **the informative-floor ceiling** | below it no `AttemptFact` is emitted, so **no rescue row is ever born — a rescue row can only help a tile the receiver still tries** | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:57-60` |
| **the receiver outgrew every naive sim stimulus** | measured at least four independent ways in one day (field-yield 300/300 dial-off; the faint knife-edge band absorbed entirely by the rescue tiers, 453 `tiles.local` fires; `local_ctx`'s six rescued identically by three different rows; the swim's bracket erased twice by field repairs) | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:45-56` |
| the field-line instruments | `measure/h3_plane_fields.py` (26 KB, the driver), `h3_field_units.py`, `h3_field_bandwidth.py`, `h3_swim.py`, `planek_{existence,fixture,parity}.py`, `uplift_{existence,fixture,cliff}.py`, `ysampler/`, `yask/`, `scanfield/`, `scanner/` | `measure/` |
| scanner field verdicts | `measure/scanfield/README.md`: **Canon LiDE 400 NOT USEFUL — everything 2.8–9× under the 0.25-dot publish floor**; HP flatbed **NOT USEFUL AS A FIELD** — a real above-floor offset, but constant, and no colour capture from it was ever decoded. Artefacts `scratch/scanfield/` (2.1 MB) | `measure/scanfield/README.md:1-20` |

### 2.9 Scheduling and pricing

| side | number | cite |
|---|---|---|
| holo1 | phased real-corpus wall decomposition: survey 194.6 vs 196.2 s; address **627.6 vs 649.5** (329.5 base + 320.0 mop-up — **relocated, not added**); payload 550.3 vs 545.8; runtime residual 182.9 vs 332.5 — **and the whole +169 s residual is eight extra source re-authentications** (one SHA-256 pass over a 6.8 GB TIFF costs ~19.1 s) | `docs/PHASED-SCHEDULE.md:535-548` |
| holo1 | u-lane `a4b` on a single-payload-stream coding: **98 blocks / 185 attempts / 0 certificates / 70 s wall / 144 s CPU**, not one `color.conditioning.*` key — a guaranteed zero, hence the per-coding filter | `docs/RECEIVE-DESIGN.md:1019-1021`; `src/holo/receive/cascade.py:54-57` |
| holo1 | supplemental tail cost **0% to +31%** of the archived ladder, buying **24 certificates** across six volumes (0 / 2 / 6 / 15 / 1 / 0) | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3172-3177` |
| holo1 | **B2 FAILED AS WRITTEN**: the bar is colour ≤ +10% / K ≤ +5% replay CPU; measured **+28.6%** on the cmy7 canary. Full-decode split: xerox c3-cmy7 **+18.7% standard lanes** (1,587.6 → 1,885.2 s) + 147.0 s u-lanes = **+28.0% total** — the only row above the ±15% K-instrument noise; three rows came in cheaper by more than noise | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3201` (bar), `:3185`/`:3218`/`:3234` (verdict), `:3152-3164` (split) |
| holo1 | campaign totals **41,532 s wall / 86,272 s CPU**, peak RSS ≤ 42.2 GiB; **the peak-RSS law: 40.3–42.1 GiB for every 4800 dpi capture regardless of coding or engine, 12.8 GiB for the 2400 dpi canary — set by the finest rung, unmoved by the arms** | `docs/COLOR-UPLIFT-MEASUREMENTS.md:3029`, `:3180-3181` |
| holo1 | policy-detach at segment granularity drops **6,098 pending blocks** when only the arm SCHEDULE changed | `docs/RECEIVE-DESIGN.md:1805` |
| holo1 | tail class rank `lane_class = -1 uplift, 0 refine, 1 mopup` descending — all M, then all R, then all U | `src/holo/receive/runtime.py:742-761` |
| holo2 | **payload above placement starves**: 2,529 ready workers, 1,287 armed payload, 431 fires, **zero tiles attempted, zero certified**; `COST_PAYLOAD = 20` undercuts every placement rung at the deepest ladder (`20 + 2*4 == 28 < 40`) | `holo2/docs/DESIGN.md:226-228`; `holo2/src/holo2/engine/recipe.py:211-214` |
| holo2 | eager vs phased payload **10.372 s vs 20.686 s**, 2,018 vs 4,478 placement fires, identical certificates and payload | `MEASUREMENTS.md:351-352` |
| holo2 | aging: attempts **1,248 → 760 (−39%)**, BP-running 1,115 → 588 (−47%); worst key **61 → 22 BP attempts / 11,820 → 4,260 iterations (−64%)**; **certified 160 → 160 unchanged**; heaviest certified lifetime **548 → 17 (−97%)**; wall over three arms **96.1 → 49.1 s** with 3 volumes VERIFIED byte-exact both sides | `MEASUREMENTS.md:1563-1570` |
| holo2 | aging on the real sheet: commits **−37% / −41%**, close verifies with **3,970 / 3,702 deferred re-attempts unfired** | `MEASUREMENTS.md:947-948` |
| holo2 | rework band crossings: `REWORK_BASE 90 + REWORK_STEP 5*(n-1)` crosses **wide at the 7th re-attempt, cold at the 11th**, reaches `COST_REFINE` 200 at the **23rd** | `MEASUREMENTS.md:1533`; `holo2/src/holo2/engine/recipe.py:351-352` |
| holo2 | pool knee at **8 on a 10-core machine**; burn=64 **8.626 s = 5.27× wall**; per-fire 14.75 → 4.07 ms = **3.62×**; 12 workers flat-to-worse at 10.9% stale; round width tracks pool exactly (2.00 / 3.99 / 7.94 / 11.82 at N = 2/4/8/12); fires 3,080 → 2,065 (−33%) | `MEASUREMENTS.md:231`, `:234`, `:240-241`, `:244-245` |
| **holo2 — the GIL ceiling** | **thread Amdahl ceiling ≈ 1.01× — the pool is AT its ceiling.** CPU/wall 0.997/1.051/1.098/1.174 cores at w1/2/4/8; lock-wait 74.3% of fire wall at w4, **86.1% at w8**; IPC 4.81 → 4.10, sys time 2.4 → 81.4 s; GIL-free fraction **f = 0.00** for `bch.decode_many`, `_chien_roots`, `_berlekamp_massey`, `map_coordinates`, `pose_audit.evaluate`, and only `ldpc.decode_soft` at f = 0.63 on 0.4% of fire CPU; **Stage-A BCH sweep ≈ 72% of ALL CPU**; even fully GIL-free the serial commit path bounds threads at 1.69/2.57/3.48×, 5.40× asymptotic | `MEASUREMENTS.md:2162`, `:2138-2145`, `:2151`, `:2154-2165` |
| **holo2 — W2 exit walls** | real sheet serial **632 → 290 s**; real sheet w8 **2,630 → 287 s**; gen-clean serial 836 → 537 s; gen-clean w2/w4/w8 1,300/2,281/4,667 → 526/550/592 s. **Wakes per commit 45.25 → 0.71–0.82**; stale discards (w8) **2,126 → 14–41**; RSS unchanged | `MEASUREMENTS.md:2094-2103` (the seed's `:2093-2096` misses `:2097`) |
| holo2 | read-set breadth: useful-rerun **9.4% at region scope vs 17.3% at r=1**; wake amplification **1.739 → 1.839**; halving the read-set is **−45% commits, −49% wall** with the certificate set unchanged and payload byte-exact | `MEASUREMENTS.md:194-195`, `:181`/`:185`/`:190`, `:196-199` |
| holo2 | snapshot **128–279 ms per 8.05 MB**; per-commit snapshotting **57×** the close-only wall; transaction ≈ 0.14 ms/commit; persistence at real-sheet scale — journal **217.3 KB (65.3 B/commit, fsync 0.053 ms/commit)**, cache **20.1 MB against a 475.9 MB envelope (23.7×)**, frame append **28 ms median / 801 ms max vs a 4.7 s rewrite**, load **2.82 s vs 9.9 s** | `MEASUREMENTS.md:283-292`; `holo2/docs/WORKPLAN.md:299` |
| holo2 | replay costs **2.51×** the free run (4.613 → 11.574 s), envelope bytes identical; re-offer skip: a serial gen-clean run **offered 1,677,186 descriptors to mint 1,768 workers**, the other 1.68 M costing 4.95 s = 33% of the commit path | `MEASUREMENTS.md:146`, `:140-141`; `holo2/src/holo2/engine/frontier.py:76-79` |
| **holo3 — the cost table itself** | `src/holo/receiver/docs/conversion_docs/d6-baseline/schedule-baseline.txt` = the readable name / subject / born-by / reads / tier / premium table for all twelve rows; `src/holo/receiver/docs/SCHEDULE.md` §"The life of a decode" `:337-373` | text + `path:line` |
| holo3 | per-plugin CPU and job counts for a whole run are in **every** `report.json` (`rows[3]` "work jobs … cpu …s · certs by plugin [...]") and in `d6-baseline/*.json → plugin_rows`; the page-domain `.log` files print the full `plugin / jobs / cpu_s / certs / poses / words` table plus a **churn** line (cpu-s per fire at price, fires per subject) | see Appendix A |
| holo3 | `tiles.local` at **73% of the sheet-I machine 2 run's CPU** — the one recorded holo3 pricing anomaly on a real sheet | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:30-31` |
| holo3 | repricing: the sheet-H colour lane burned **38,512 CPU-s (31%)** on an escalating-refit ladder that the repricing fix then killed | `src/holo/receiver/docs/conversion_docs/MEASUREMENTS-2026-08-31.md:16-17`; instrument `measure/h3_repricing.py` |
| holo3 memory | post-change peaks: step 3 **15.8 → 39.4 GiB**; step 6 **56.3 → 57.96** (0.04 GiB from the kill line); step 4 breached at **both** workers 8 (60.51) and workers 6 (60.24) — **0.27 GiB apart, so worker count is not the driver**; `POST-FORENSICS.md:496-621` (§D) is the full memory adjudication with §D.2 "where the growth is NOT" and §D.3 "where it probably is — and why the artifacts cannot close it" | `src/holo/receiver/docs/conversion_docs/PARITY.md:451`; `POST-FORENSICS.md:496-621` |
| holo3 | wall vs holo1 on identical crops (the cleanest cost comparison in the record): **4.4× / 4.2× / 2.8× / 2.7×** on c2-cmy7 / c3-cmy7 / c2-cmy8 / xerox-k — see §1.12 | `src/holo/receiver/docs/conversion_docs/crop-batteries/*-results.json → aggregates.walls` |

### 2.10 The dryness gate

| side | number | cite |
|---|---|---|
| holo2 | **NO yield or cost number exists.** The gate is described only as mechanism — cold ladder `cold_live(d) 140+20d` / `cold_rest(d) 150+20d`, +5 for a child, "both dryness-gated" (`MEASUREMENTS.md:1350`); implementation `holo2/src/holo2/engine/orchestrator.py:387-395` (the `job.gated` / `min(in_play) < job.cost` test), **no instrumentation** |
| holo2 | its predecessor **was** measured away: the quiescent gate was DELETED with `quiesces` (footing progression became pure pricing), `MEASUREMENTS.md:1771-1772`. `holo2/docs/DESIGN.md:265` still says cold is "gated on quiescence" and is **stale** |
| **holo3 vs holo2, measured** | `scratch/sheetI-20260831/v2v3-placement-residue.md:41-47`: **"holo2's dryness gate saves nothing on a run that drains."** Both arms go to full exhaustion and a gate that only defers cannot remove work. Measured: holo2's first cold fire sits at **44% / 36%** of its placement stream, holo3's at **53% / 44%** — **holo3's plain price ladder already reproduces the ordering at `--workers 1`** |
| holo3 | the gate was deleted at `d399ba3`; cold is ordered last by price. `measure/h3_repricing.py` is the instrument |

### 2.11 Quarantine (the row grok flagged as holo2's only unique yield lever)

| claim | what the artefacts actually say | cite |
|---|---|---|
| the zero-contradiction invariant is **e022's**, not holo2's | **~1,780 known-position reads across the six-scan sessions, zero contradictory** | `docs/RECEIVE-DESIGN-EVIDENCE.md:492` — **the plan's citation resolves exactly** |
| holo2 quotes it as the expected silence | | `holo2/src/holo2/solve/quarantine.py:104` |
| holo2's **own** measurement is a wall cost, not a yield | W5 quarantine: unit 1,915, oracles 314, 39 verdicts, wall 79.0 s — **"the wave costs ~1.7 s against a bypassed baseline, +2%"** | `MEASUREMENTS.md:1345` (**the plan's `:1345` is right; the seed's `:1344` and `:1377` are both off by one**) |
| holo2 yield | **"Zero contradictions on every healthy fixture"** — L8's own expected silence; done coverage untouched, adversarially pinned. The W5 block became `quarantine.py`, 236 lines | `MEASUREMENTS.md:1384-1386`, `:1390` |

**So the grok hypothesis has no measured yield behind it on either side.**

### 2.12 The page domain

| side | number | cite |
|---|---|---|
| holo1 | the e029 done-geometry census is the page-domain cost record: the m00 `--complete` tail spent **160 priced colds over 133-page sweeps = 7,200 cold-progress steps** to mint 2 certificates | `docs/DONE-GEOMETRY.md:268-273` |
| holo1 | scrap corpus page domain is **{0}**; a scrap-only session cannot reach K so neither arm closes | `docs/PAYLOAD-MEASUREMENTS.md:21-26` |
| holo1 | cold cost at single-page domain ~1–3 s vs **30–48 s per avoided cold** at large domains; `cold_first_max_pages` **default 1** | `docs/PLACEMENT-IMPROVEMENTS.md:328-341` |
| holo2 | ran `--pages 1` with flavourless cold tried-ids; **no page-domain measurement exists** |
| **holo3 — the merge qualification, 2026-09-02** | `scratch/page-domain-qual/`: base (pre-merge tree) **1,357 certs / 2,517.3 cpu-s / 37,469 jobs**; merged with `--pages 1` (the null) **1,360 / 2,557.4 / 37,945**; merged at default (**133 possible pages**) **1,356 / 1,639.8 / 23,855**. **All three VERIFIED `e5021f8d…`, 465,580 B.** The default-domain arm is **35% cheaper in CPU and 36% fewer jobs for −1 certificate** | the three `*.log` files and `*-run.NNNNN/report.json` |
| holo3 design | `src/holo/receiver/docs/PAGE-DOMAIN.md` v1.0 (§1 the ruling `:18-45`, §5 floors price the address space `:114-152`, §6 rest is last by price `:153-164`, §8 determinism `:175-182`) + `src/holo/receiver/docs/PAGE-DOMAIN-WORKPLAN.md` | tracked |
| holo3 | sheet J is the only real fragment material: **357 → 657 certificates** across a default-domain run and a `--pages 100` resume, close OPEN both times | `scratch/J-run.52093/report.json`, `scratch/J-run.54028/report.json` |
| owed on both sides | **no fragment/confetti done-geometry census** | `docs/DONE-GEOMETRY.md:293-296` |

### 2.13 Bit-exactness evidence (the CARRIED-IDENTICAL currency)

Four holo3 test files hold **127 test functions across 3,295 lines** that
compare holo3's kernels against v1's and holo2's **by importing both trees
live**:

| file | tests | imports |
|---|---:|---|
| `src/holo/receiver/tests/test_h3_drift_format.py` | 43 | 15 `holo.*` format/core modules |
| `src/holo/receiver/tests/test_h3_drift_receiver.py` | 45 | 16 `holo.*` (11 of them `holo.receive.*`) + 3 `holo2.solve.*` |
| `src/holo/receiver/tests/test_h3_drift_kernels.py` | 31 | 6 `holo.*` (4 `holo.receive.*`) + 4 `holo2.{format,solve,capture}.*` |
| `src/holo/receiver/tests/test_h3_drift_declared.py` | 8 | 4 `holo.*` + 2 `holo2.format.*` |

**Every one of those imports is `pytest.importorskip`.** When `holo2/` and
`src/holo/receive` go, these tests do not fail — **they silently skip**, and
with them the only live proof that holo3's BCH, LDPC, PAVA, detector,
context, sampling, calibration, refine and colour numerics still match v1's.
This is a first-class inventory fact for the maps and for Phase 2/4. See
GAP G-02.

---

## 3. Gaps

Questions the maps will need answered for which **no artefact holds a
number**. One line each; no runs proposed.

**Structural / campaign-critical**

- **G-01** The archived holo1 `.state` corpus is readable only by `src/holo/receive/state_codec.py` + `session.py`; when the tree goes, 28 states (≈60 GB) become unreadable except through git history. Only the Phase-0.3 address freeze survives.
- **G-02** The 127 cross-tree drift tests use `pytest.importorskip`, so after deletion they skip silently rather than fail — no artefact records what the suite's *effective* coverage becomes.
- **G-03** The crop-parity per-case sidecars, `_distill/verify/` run reports and every raw crop live only in `scratch/holo3-worktree-salvage/small-artifacts.tar.gz`; the crops themselves (TIFFs) are **gone** — no artefact can be re-derived from the deleted worktree. *(tarball trashed 2026-10-09; see the dated note below the citation-form table)*
- **G-04** **No holo3 decode exists of hp c2-cmy7, e030 hp c2-cmy8 or e030 hp c3-cmy8.** Three of the campaign's named volumes have a holo1 record and no holo3 counterpart at all.
- **G-05** No artefact carries a **sheet-I crop battery result** — the run stopped at case 13 of 26 and no `results.json` or battery markdown was written.
- **G-06** `experiments/032` is **stale on its own headline**: it records xerox c2-cmy7 as FAILED at 83 certificates; that volume was later closed VERIFIED at 686,859 B / 1,559 certificates, and no experiment log records it. The same staleness applies to three other volumes' best-on-record (c3-cmy7 720→810, c2-cmy8 5,370→5,466, hp c3-cmy8 663→796).

**Placement / evidence / refinement**

- **G-07** **holo3's `--workers 8` multiple on a real sheet is nowhere recorded.** What exists: the byte-identity control (`d6-baseline/{k,color}-w{1,8}.json`, sims only), the acceptance step-8 requirement of *identical payload* at workers 8 vs 1 (`14-acceptance.md:264`), and the open acceptance question of whether a colour 4800 volume is needed to make a **≥3×** claim representative (`14-acceptance.md:329`). **The ≥3× bar has never been measured.**
- **G-08** The **straddle-audit refusal path** and **declared-vs-voted pitch** rows (Appendix B seeds) have no measured number on any of the three sides — only code behaviour.
- **G-09** No **holo3** realized done-gating rate on a real sheet (holo1 has 48.6% simulated, holo2 3.2–3.5% realized).
- **G-10** Why holo3's refinement was not scheduled at the five column-0 rows v1 rescued is **inference, not measurement** — holo3's refinement writes no events (`GAPS.md:377-381`).
- **G-11** What re-fired the extra scans that took step 3 to exact parity is **UNKNOWN**; attribution would need instrumentation the batch does not carry (`PARITY.md:449-455`, `POST-FORENSICS.md:463-481`).
- **G-12** `WIDE_ANCHORS = 8` is **UNMEASURED** on holo2 (0 wide passes on all three arms) and the real sheet that would bind it was never run.
- **G-13** holo1's `placement/search.py` (1,099 lines, the E022 kernel) is cited by **no** conversion spec and **no** measurement doc — `place_survey` / `place_mopup` / `place_committed` / `_cold_stage_a` have zero measured yield anywhere.
- **G-14** holo1's cold **format discovery** (`discovery.py` 860 ln + `discovery_state.py` 395 ln) has **no yield or cost number anywhere** — no measured cost of a discovery-first entry vs a `--format`-told one.
- **G-15** No real-corpus comparative qualification of holo1's frontier/multi-slot placement family — every number is synthetic-fixture (`PLACEMENT-IMPROVEMENTS.md:310-312`).
- **G-16** holo2's `receive/evidence_blocks.py` supersession algebra is the catalogue's own headline blind spot: named in none of the four censuses, no ledger row, census "started and stopped with the campaign; nothing written" (`K-PARITY-CATALOG-draft.md:77-89`).

**Colour and fields**

- **G-17** **holo2 has no colour number of any kind, by construction** — no wall, no certificate count, no yield for cmy7 or cmy8 on any sheet. Every holo2 colour row in the map is ABSENT by design, not by omission.
- **G-18** No **same-tree dial-off control** for PLANE-FIELDS W6 — the doc records the tree-drift confound as owed, so part of the +252 is unattributed (`PLANE-FIELDS.md:940-943`).
- **G-19** No per-column pattern and no close for **sheet H** on either receiver; the one holo1 read is a single capture at one footing (`INDEPENDENT-PLANES.md:1813-1817`).
- **G-20** The **4800-capture question** has two data points pointing opposite ways (sheet H seven-stack **−70**, sheet I run 4 **+14**) and no controlled experiment; the discriminating pair is unrun, machine 4's assignment (`MEASUREMENTS-2026-08-31.md:36-43`).
- **G-21** e032's **per-plane concentration hypothesis** for the c2-cmy7 failure is untested — no artefact records the discriminating per-plane diagnostic (`032:213-219`).
- **G-22** No artefact resolves which of xerox c2-cmy7's 22 holo3 misses the supplemental photometry arm won — bounded at ≤15 sheet-wide but unresolved; **certificates carry no lane marker** (`GAPS.md:381-383`).
- **G-23** B2's two instruments were never reconciled: the same c3-cmy7 cost reads **+18.7%** full-decode and **+28.6%** replay-primary, and the review's question 4 (`COLOR-UPLIFT-REVIEW.md:678`) is unanswered.
- **G-24** holo3's colour-arm mispricing is **flagged, not measured away**: K and colour `tiles.local` are both priced 220 while drawing CPU that differs 20-fold (`SCHEDULE.md:516-520`).

**Cost, memory, environment**

- **G-25** holo3 memory growth on the largest colour volumes is **not attributable from the artefacts** — `POST-FORENSICS.md:564-621` says where it probably is and why the run dirs cannot close it; xerox c2-cmy8 has **no post-change measurement at all**.
- **G-26** No measured comparison of holo1 `--workers` settings, and `--workers` is **unknown for every archived capture** (`COLOR-UPLIFT-MEASUREMENTS.md:17-19`) — every archived-vs-candidate CPU delta carries an uncontrolled worker-count term.
- **G-27** `hp-c2-k` is **not flag-reproducible** (multi-invocation, earlier flags unrecoverable), so its 465,580 B close cannot be re-derived from the record alone.
- **G-28** holo2's process pool was never built — the 2.5–3× is a reasoned estimate explicitly "not a measured comparison" (`MEASUREMENTS.md:261-263`, `:2177`); and no byte-identical free-threaded 3.14t decode or wall exists (`K-PARITY-STATE.md:135-137`).
- **G-29** holo2's close preemption number (**3.7×**) is v1's; holo2 never re-measured it (`engine/DESIGN.md:494`).
- **G-30** The **v1 scheduler vintage confound (v4 → v5)** sits under every holo2 parity row and is UNMEASURED (`MEASUREMENTS.md:1081-1082`, `:1163-1165`).
- **G-31** e034 records **no tree sha for any of its four runs** — the deepest read on record has no receiver provenance (`034:173-174`).
- **G-32** **Union on paper via an add-a-scan resume is "unmeasured in BOTH trees"** per holo2's own stop-state (`K-PARITY-STATE.md:126-127`); the sheet-I chain is the closest thing and it is a single sheet.

---

## Appendix A — artefact format reference

**holo3 `report.json`** (every run dir). Top-level keys: `capture_facts`,
`captures` (`[{ordinal, sha12}]`), `close`, `fold_errors`,
`ladder_isolation`, `last`, `now`, `pages`, `pane_revs`, `panes`,
`plane_certs` (`[[stream, n], …]`), `plane_fields` (present only when the
dial ran), `replayed` (resumes only), `revision`, `rows`, `run_done`,
`scheduler`. `close` = `{blocks[], certified, consulted, counting, k_total,
metadata_n_unique, metadata_rank, status, symbols_used, verified{n_bytes,
sha16}}`. **`rows` is the diag summary as six strings** — `rows[3]` carries
`work jobs N · cpu Xs · certs by plugin [name:n · …]`, which is the
per-mechanism certificate attribution; `rows[4]` carries the tile-state
census.

**holo3 `events.jsonl[.xz]`.** One JSON object per line, keyed by `type`.
Read with `xz -dc file | …`. The types and their uses:

| type | fields that matter |
|---|---|
| `RunOpen` | `format_id`, `pages`, `tiles_yx`, `stream_ids`, `n_captures`, `workers`, `pitch_in`, `plane_fields` |
| `CaptureOpen` | `capture` (sha256), `dpi`, `shape_yx`, `channels`, `duplicate`, `ordinal`, `levels_ppc` |
| **`TileOutcome`** | `page`, `ty`, `tx`, `stream_id`, `source` (`tiles/scan` etc.), `result` (`certified` / `attempted_failed` / `below_attempt_floor`), `bp_iters`. **The certificate set = rows with `result=certified`, deduped on `(page, ty, tx, stream_id)`** — deduping matters on pooled multi-capture sheets (step 7 emitted 6,072 rows for 5,326 distinct addresses) |
| `JobDone` | `plugin`, `subject`, `cost`, `cpu_s`, `n_certificates`, `n_poses`, `n_words` — **the per-mechanism cost record** |
| `PoseCommitted` | `capture`, `level_index`, `region_index`, `extent_cells`, `page`, `route` (`word`/`chain`/`refine`), `mismatch`, `accepted`, `page_origin_yx`, `rot_k`, `pitch_px`, `native_affine`, `shape_yx` |
| `WindowScheduled` / `WindowRetired` / `WindowSettled` | `capture`, `level_index`, `region_index`, `extent_cells`, `stage`, `cost` |
| `FieldFitted` / `PlaneFieldTiers` | per-plane `published`, `refusal`, `median_delta_dots`, `n_sites`, `residual`, `support_tiles`, `delta_grid_dots_xy` |
| `CloseCheck` / `RunDone` | `certified`, `symbols_used`, `k_total`, `metadata_rank`, `status`; `RunDone` adds `payload_sha256`, `n_bytes` |
| `EngineStat` | `stale_skips`, `retired`, `attempts_hist`, `wakes`, `consult_cpu_s` |

**holo3 run dir** also carries `argv` (the exact command, one line),
`tree` (the `git describe` stamp, e.g.
`pre-gpt-5.6-cleanup-20260804-912-g1faa7a2b…`), `facts.npz` (the resumable
snapshot; since main `31d786f` every cadence write keeps the previous
generation as `facts.npz.bak`), and `pane-*.png`. **`tree` is the only receiver-provenance
record in a run dir** — the sheet-I chain has `argv` but the e034 log notes
no tree sha was captured for those runs.

**holo3 `.log` files** (page-domain qual): the six diag rows, then a
`churn` line (cpu-s per fire at price, fires per subject, per plugin), then
the `plugin / jobs / cpu_s / certs / poses / words` table, the run dir, and
the `VERIFIED <n> bytes sha256 <sha>` line.

**`src/holo/receiver/docs/conversion_docs/parity.json`** — object keyed by step id `"2"`…`"7"`.
Each: `step`, `label`, `holo1{n, by_stream, format_row_id, state}`,
`harvest{exit_code, wall_s, child_max_rss_gib, bytes, sha256, sha_ok, …}`,
`holo3{n, events, by_stream}`, `matched`, `holo1_only`, `holo3_only`,
`miss_fraction`, `*_sample`, `*_by_stream`, `cluster_note`, `tile_matrix`,
`over_one_percent`, `holo1_provenance{state_epoch, best_on_record, note}`.

**crop-battery `*-results.json`** — `volume`, `label`, `colour`, `manifest`,
`format_ref`, `classes`, **`gap_counts{holo1, holo3, both, miss, gain,
neither, holo3_run, events{…}}`**, `generated_at`, `harness`,
**`gt{payload_sha256, validated_certificates, rule}`**, `cases[]`, and
**`aggregates{per_class{<class>{n, holo1_crop_certified, holo3_crop_certified,
holo1_compared, holo3_compared, reproduces_full_sheet{holo1, holo3}}},
wrong_certificates[], out_of_bbox[], walls{executed_wall_seconds{holo1,
holo3}, runs_executed, runs_adopted, adopted_wall_seconds},
agreement{agree, disagree, undetermined}}}`. Each `cases[i]` has `case_id`,
`cell_bbox`, `runs{holo1{status, reason, sidecar{argv, cwd, crop_sha256,
…}}, holo3{…}}`, `n_certificates`, `bits_available`, `targets`, `controls`,
`wrong_certificates`, `out_of_bbox`, `checked_certificates`, `crops`,
`crop_sha256`.

**`measure/crop_parity/cases/<vol>/cases.json`** — the manifest: `volume`,
`label`, `step`, `format_ref`, `tile_matrix`, `cells_yx`, `streams`,
`colour`, `classes`, `captures[]` (id, path, dpi, shape), the geometry
conventions as prose (`tile_convention`, `cell_axes`), `halo_cells`,
`merge_gap_tiles`, `max_span_cells`, `px_pad_cells`, `control_rim_cells`,
`gap_counts`, `payload{path, sha256, bytes, gt_validated_certificates}`,
`generator{tree, dirty_sha}`, `cases[]` (`case_id`, `cell_bbox`, `tiles`,
`crops[]`, `targets`, `controls`).

**`src/holo/receiver/docs/conversion_docs/overnight/ledger*.jsonl`** — one object per step:
`step`, `argv`, `started`, `exit_code`, `killed_at_footprint`, `wall_s`,
`peak_footprint_gib`, `peak_rss_gib`, and for closing steps
`payload_sha256` + `sha_ok`. The final row is `{"batch_done": true, "ts": …}`.
`final-manifest*.json` holds the pre-registered `steps[]` with argv and
expected sha.

**`src/holo/receiver/docs/conversion_docs/d6-baseline/*.json`** — `argv`,
`certificate_addresses`, `certificate_bits_sha256`,
`certificate_signature_sha256`, `certified`, `event_counts`, `exit_code`,
`job_counts_per_row`, `label`, `n_events`, `payload_bytes`,
`payload_matches_source`, `payload_sha256`, **`plugin_rows{<row>{jobs,
cpu_seconds, certificates, poses, words}}`**, `report_close`.

**holo1 `.state`** — one canonical-JSON file (`state_codec.py`: sorted keys,
no whitespace, evidence blocks inlined as base64(zlib)). Full `load_session`
costs ~7× the file size in RAM. For addresses only use
`measure/parity/extract_holo1_certs.py` (mmap, find `"certificates":[`,
bracket-scan, `json.loads` that slice; cross-validated against a real
`load_session` on two states). Each state has a sibling
`receive.state.diag/` with `report.json`, `status.json`, `events.jsonl`,
`diagnostic-health.json` and frames.

**holo1 certificate freeze** (`holo1-certificates/*.json`) — `addresses`,
`close{certificate_frontier_sha256, metadata_version, payload_length,
payload_sha256, reason, status}`, `extraction_utc`, `format_row_id`,
`marker_occurrences`, `mtime`, `n_certificates`, `n_duplicate_work_keys`,
`n_raw_rows`, `peak_rss_bytes`, `peak_rss_gib`, `per_stream`, `policy_id`,
`schema_version`, `size_bytes`, `state_path`, `tree_sha`, `wall_seconds`.

**holo2 `scratch/holo2-catchup/` formats** — `crops/<sheet>/results.json`
mirrors the holo3 battery shape with
`aggregates.per_class{flipped, still_missing_v2, v1_missing, neither}`, each
`{n, v1{compared, crop_certified, full_sheet_certified}, h2{…}}`;
`real/parity*/{h2,v1}-<sheet>.parity.json` = `{argv, certificates,
payload_sha, payload_bytes, returncode, wall_s, epilogue, ran_at, prepared,
prepared_before, prepared_after, provenance}`; `real/rf1-gate-flips.json` =
a list of two objects (e029, xerox) with `n_windows_with_2_poses`,
`n_scored`, `flips`, `rows`, `quarantine_*`; `f1/f1-<sheet>.json` =
`{sheet, n_tiles_with_evidence, v1_certified, h2_certified, fidelity,
classes, results, h2_unchanged, seconds}`; per-case sidecars = `{argv,
crop_sha256, receiver_tree, receiver_dirty_sha, repo_head, wall_seconds,
exit, summary, ran_at}`.

**`scratch/plane-fields/**/*.json`** — every one carries
`tree_before` / `tree_after` / `tree_moved` (receiver tree sha256, git head,
dirty flag) and an **`approximations`** list of prose caveats. **Check
`tree_moved` before trusting any of them**; `p2/e5b/e5b-VOID-tree-moved.json`
is a preserved example of that check failing.

---

## Appendix B — corrections to the plan's own pointers

Recorded so the maps do not inherit them. None of these is a defect in the
plan's reasoning; they are stale or incomplete pointers.

| the plan says | what is true |
|---|---|
| Appendix A: "the 17 archived `.state` files" | **28 states exist on disk.** The 11 under `scratch/color-uplift/full/` are missing from the list, and they include `xerox-c2-cmy7-pkfinal/receive.state` — **the very state `PARITY.md:240` uses for step 6**, and the only one holding the 1,559 / 686,859 B close |
| §5 step 0.3: "the colour-uplift PK-FINAL states under `scratch/plane-fields/policy-detach/`" | that directory holds exactly two states — `cmy7-counting.state` (2.2 MB, the *failed* HP volume) and `cmy8-pkfinal.state` (160 MB). **The PK-FINAL corpus is `scratch/color-uplift/full/`** |
| §6 1.0 names `scratch/holo3-overnight-events` and holo3 run dirs "under `scratch/`" | correct, and incomplete: also `scratch/page-domain-qual/` (2026-09-02, the newest e029 numbers and the only ones from `main`), `scratch/J-run.{52093,54028,56088}/`, `scratch/local-ab/`, `scratch/angle-residue/`, `scratch/scanfield/` |
| §6 1.0 names `measure/crop_parity/cases/` "+ sidecars" | the **sidecars are not in the repo**. They live only in `scratch/holo3-worktree-salvage/small-artifacts.tar.gz`, together with the whole `_distill/verify/` tree. `<checkout>` no longer exists | *(tarball trashed 2026-10-09; see the dated note below the citation-form table)*
| Appendix B, quarantine: "`MEASUREMENTS.md:1345`" | **correct.** (The seed ledger's `:1344` / `:1377` are both off by one) |
| Appendix B, quarantine: "`docs/RECEIVE-DESIGN-EVIDENCE.md:492`" | **correct — resolves exactly**, including the ~1,780-read figure |
| Appendix B, "certified-label enrichment (+68% wall / 0 yield in holo2)" | **correct**: `MEASUREMENTS.md:978`, `:983`. Add the finding that makes it a *candidate* rather than a parity row: **v1 never fed certified reconstructions to the ctx/PAVA channel**, so this is a holo2 extension (`:987-990`) |
| Appendix B, "same-capture cross-rung pooling (+2 e029 tiles, 16 of 78 gap tiles)" | **correct**: `DIVERGENCE-LEDGER.md:67`; ranked H3 at `scratch/holo2-catchup/detect/DETECTION-GAP.md:113` |
| Appendix B, holo2 W2-exit "290 s serial / 287 s w8, wakes 45 → 0.8" | **correct**: `MEASUREMENTS.md:2096-2098` |
| Appendix B, "the 2026-08-31 sheet-I run recorded `tiles.local` at 73% of CPU" | **correct**: `MEASUREMENTS-2026-08-31.md:30-31` |
| seed `holo2-behaviour-ledger.md` §4 | **60 of 90 entries resolve as cited; 10 are off by a few lines; 14 do not resolve (corrected lines given in §2 above); 6 point at the wrong file or are stale.** Three named hazards: the F-17 numbers **disagree between `MEASUREMENTS.md:1810-1813` and `solve/DESIGN.md:874`**; the F2 resume `+13/+12` is **explicitly superseded** (`HANDOFF-F2.md:654`); `holo2/docs/measurements-h3.json` self-declares `"PROVISIONAL; measured on toys"` and is not citable for real-sheet claims |
| seed `holo1-receive-inventory.md` §2 | its measured-number paragraph is at **`:144`** (the section itself is schedule semantics, not measurements). All ten pointers resolve; one label is wrong — the candidate-loop crop cost 532 → 924 s is the **v0.41** row at `RECEIVE-DESIGN.md:75`, not v0.42 (`:76`). Its §0 claim "§6.2a:411" is a **section-relative offset**; the absolute line is `docs/RECEIVE-DESIGN.md:1089` |
| — | `holo2/docs/kparity/K-PARITY-STATE.md:51-52` names `scratch/holo2-catchup-archive/`; **that directory does not exist** |
| — | `scratch/sheetI-20260831/angle-vs-placement.md` cites `/tmp/I/holo3-I-first-run/events.jsonl` and `/tmp/I/holo3-I-resume-3-run/events.jsonl`. Those still exist **under `/tmp`** and are not backed up; the durable copies are the four `events-*.jsonl.xz` in `scratch/sheetI-20260831/` |
| — | `src/holo/receiver/docs/conversion_docs/crop-batteries/*.md`, `parity.json`, `acceptance.json` and every overnight `argv` print `<checkout>/…` paths. **All dead.** Cite the tarball member or the tracked summary |
