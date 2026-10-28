# Deletion log — executed steps, counts, gate outputs

Nothing is deleted before Gate D. This file records Phase 0 baselines and,
later, every landing with its sha and test-count arithmetic.

## Phase 0 baselines (tree `29d9a8d`, 2026-09-02, interpreter `env/bin/python` 3.14.7 FREE-THREADED — `sys._is_gil_enabled()` False, numpy 2.5.2, scipy 1.18.1; the one venv Germano rebuilt in `29d9a8d`)

| gate | result | notes |
|---|---|---|
| `env/bin/pyflakes holo3/ src/holo/ measure/` | exit 1 | holo3: 3 unused imports (`plugins/color_region.py:82`, `tests/test_h3_plugins_swim.py:31`, `tests/test_h3_plugins_uplift.py:15` — the three known leftovers). src/holo: 54 findings, all unused imports/redefinitions EXCEPT one real undefined name, `src/holo/receive/color_payload.py:367: undefined name 'crops'` (a v1 receiver branch that cannot have executed; recorded, not fixed — v1 is retirement-bound). measure/: 3 unused-import findings in v1-only instruments. |
| holo3 fast lane `env/bin/python -m pytest holo3/tests -q` | **1,773 passed, 449 skipped**, wall 46.8 s, exit 1 | exit 1 is the fast-lane wall tripwire (15 s) tripping under load 3.4 with three workers running (certificate extraction, artefact inventory, W3 readers). Per the plan a trip under fleet load is a load signal, not a regression; the pre-merge record for the same tree (`4d98851` commit body) is 1,772 passed. **Quiet-machine re-run owed** before the number is used as a baseline. |
| holo3 slow lane `HOLO3_RUN_SLOW_TESTS=1 …` | **17 failed, 2,151 passed, 54 skipped**, wall 320 s, exit 1 (load 4.7–5.0, three workflows + the full suite running) | Failures: `test_h3_e2e_rotations` frozen-sha mismatches (rotated K rasters 1/2/3 + colour), `test_h3_e2e_sims::test_k_serial_job_counts_are_the_churn_tripwire` (golden mismatch — its own message says never update), seven `test_h3_degraded_sim` tests (pinned address set, serial job counts, rescue rows firing), `test_h3_multires::test_the_split_tile_certifies_only_at_the_mixed_union`, four `test_h3_plugins_local_ctx` tests (incl. the eight-worker determinism test), plus the 140 s wall tripwire. The sha/golden mismatches are deterministic and cannot be load: **the slow lane is red on main at `29d9a8d` before this campaign touched anything** (the identity merge re-froze the sim renders; `4d98851` reports only the fast lane and one K e2e as verified). Quiet re-run owed; a fix or re-freeze ruling from Germano is a Phase-2 prerequisite. |
| full repo suite `env/bin/python -m pytest -q` | **5,030 passed, 52 skipped**, 27:44 wall, exit 0 (2026-09-02 late) | `tests/` + `holo2/tests` per pyproject; holo3/tests not included by design |
| sim payload shas | K `59495601d00fa78145f5400e97eb53ee31424c57d6be905f00f2f62a7699848f`, colour `ddf7acebcd86ae52aea2a61224c80cf3dee3746083a616a4a28e9b333754e1d6` | pinned in `holo3/tests/_h3_sims.py:118,122`; unchanged by the identity merge (`b8471fc` body) |

## Phase 0 steps

| step | status |
|---|---|
| 0.1 environment | **DONE by Germano, commit `29d9a8d`** (2026-09-02 16:03): one venv at the root built on python3.14t; `requirements.txt` unified (holo3's floors, plus imagecodecs / pytest-xdist / mypy; coverage dropped); `holo3/requirements.txt` deleted; the stale editable paperholo `.pth` NOT re-established (conftest + pyproject pythonpath are the mechanism); gil stays disabled through every extension import; holo3 fast lane 1,773 passed on the rebuilt env; both CLIs smoke-clean. Also landed: `104494e` splits `holo3/diag/model.py` (1000 lines) into model.py 357 / readout.py 509 / report.py 152 with a one-way dependency — the 1000-line seam constraint on that file in Phase 2.2 is moot. Note for W3: the running g6b reader was given the pre-split file list; `readout.py` and `report.py` get a supplemental pass after W3 completes. |
| 0.2 `confetti3.py` | added at the repo root (untracked); `./confetti3.py --help` lists `decode`, `schedule`; runs on the rebuilt free-threaded env |
| 0.3 holo1 certificate freeze | **DONE 2026-09-02**: all 28 archived states frozen (batch 1: 17, batch 2: the 11 colour-uplift PK-FINAL/control states under `scratch/color-uplift/full/` that the first census missed); 267.8 s total wall, peak RSS 15.27 GiB on the 15 GB sheet-H state; no decode run. Exit criterion MET: all six parity columns reproduce exactly (1,940 / 720 / 5,370 / 1,930 / 1,559 / 5,297) and all three best-on-record counts (1,559 c2-cmy7 close sha 5963b9d1…, 5,466 c2-cmy8 close sha f13c34db…, 810 c3-cmy7 close sha 4f68dbf9…) from states with `verified` close records. Findings: `scratch/in/holo-xerox-c2-cmy7-counting-receive.state` is the 83-certificate FAILED e032 run; four hp c2-cmy7 files are byte-identical (sha 4042d3fb…); `plane-fields/policy-detach/cmy8-pkfinal.state` is a copy of the HP c2-cmy8 attempt (15 certificates, open), not the xerox PK-FINAL; `plane-fields/qual` = the W6 sheet-I run at 5,549; sheet H is r0850 (4,144); `cu-hp-c3-cmy8-pkfinal` reached 796 (C 740 / M 56 / Y 0) and still did not close — every HP colour attempt in the 28 stays open, only xerox colour and the four K states verified. Record: `holo1-certificates/INDEX.md` (28 rows + close-record table). |
| 0.4 baselines | pyflakes, fast lane, slow lane recorded above (slow lane RED on main); full repo suite running; quiet re-run of the slow lane owed |

## Phase 1 — find (DONE 2026-09-02; nothing in code changed)

| step | status |
|---|---|
| 1.0 artefact inventory | `ARTEFACTS.md` (990 lines; 32 named gaps; seed-pointer audit in its Appendix B) |
| W1 holo2 map | `HOLO2-MAP.md` 144 rows; 64 ruling entries; 24 Opus agents |
| W2 holo1 map | `HOLO1-MAP.md` 225 rows; 65 ruling entries; 12 port briefs; 27 Opus agents |
| W3 comment carry | 578 items harvested (12 groups) + verified + tiered: A 274 / B 127 / C 177; `COMMENT-CARRY.md`, `COMMENT-CARRY-DIGEST.md`, `scratchpad/w3/landing-set.json`; 36 Opus agents |
| synthesis | `RULINGS.md` (129 entries, priority index), `GATE-B-BRIEF.md` |
| Gate B / C | awaiting Germano |
