# holo3-diag deep review — findings digest (2026-08-29 evening)

Four-dimension review of branch holo3-diag at ee4b01e (3 commits) vs holo3
HEAD ca28219. NOTE: the branch advanced to 8062c64 (5 commits) DURING the
review — rounds ac4bbce + 8062c64 are UNREVIEWED. All verdicts:
MERGE_WITH_FIXES. Full evidence: the review workflow journal
(wf_875f7b7b-edb) and task output wxz6up90l.


## UX design quality vs the ruled DIAG-DESIGN.md (holo3 diag: model/panes/server + test_h3_diag)
VERDICT: MERGE_WITH_FIXES

- [SERIOUS] "every pane a browser shows is the same tick by construction" (doc §1) is not enforced by the cache key: the cache is keyed (pane, selector) and merely flushed on revision change, and the ?rev= the client sends is parsed away, so a /status fold landing between two of the browser's four image requests puts two different revisions on screen at once.
  EVIDENCE: src/holo/receiver/diag/server.py:308 `self._panes: dict[tuple[str, int], bytes] = {}` — key is (pane, selector), not (pane, selector, revision); server.py:319-321 `if self._model.cursor != self._revision: self._panes = {}`; server.py:368 `path = urlparse(self.path).path` discards the query, and server.py:391 `pane, dash, raw_selector = name.rpartition("-")` never sees rev. Client sends it: server.py:78 `return "/pane/" + pane + "-" + sel + ".png?rev=" + revision`. Reproduced on a live server: rev0=2, rev1=4, `payload bytes served under ?rev=2 equal the rev1 render: True`, and `rev0-content payload frame =
- [SERIOUS] The per-pane revision the doc lists in the /status payload (§5) does not exist, so any event of any kind refetches and re-renders all four PNG panes; measured 135-223 ms of render and 0.2-1.8 MB of PNG per second, sustained for the whole decode, with the capture pane alone 84-147 ms.
  EVIDENCE: Doc §5: "returns rows, revision …, capture list …, page list, per-pane revision". src/holo/receiver/diag/model.py:552 `"panes": {"capture": ordinals, "page": pages, "payload": pages, "pose": pages}` — selector lists, no revisions; model.py:544 `"revision": model.cursor` is the only one. Client refreshes everything off that single number: server.py:267-271 `if (status.revision !== revision) { … refreshCapture(); refreshPages(); }`, and revision moves every tick because EngineStat is appended once per engine loop iteration (engine.py:179). Measured at 53x37 tiles / 3 streams: capture 147.3 ms / 1634.7 KiB (
- [SERIOUS] The hard "never print zero where the fact is unavailable" invariant is violated in the scheduler block: before the first EngineStat the operator reads "attempts none · stale skips 0 · retired 0 · wakes 0" — four fabricated zeros for producers that have not fired.
  EVIDENCE: src/holo/receiver/diag/model.py:559-561 `"stale_skips": stat.stale_skips if stat is not None else 0,` / `"retired": … else 0,` / `"wakes": … else 0`; rendered unconditionally at server.py:166-169 `"attempts " + (hist || "none") + " · stale skips " + sched.stale_skips + " · retired " + sched.retired + " · wakes " + (sched.wakes || 0)`. Confirmed live against the committed tree before any EngineStat: `{"attempts_hist": [], "stale_skips": 0, "retired": 0, "wakes": 0}`. Note the same class of bug was just fixed one layer over in the close block (ac4bbce added `consulted` + "K, metadata, blocks unavailable bef
- [SERIOUS] The "rank as of last solve" caption fires on fresh solves: every non-verified status is treated as stale, but a solve that ran and failed returns status "open" with its own fresh blocks, so through the entire post-ready endgame — the phase the operator actually watches — live block ranks are captioned as old.
  EVIDENCE: src/holo/receiver/diag/model.py:28 `RANK_STALE_STATUSES = ("open", "count_ready", "deferred")` and model.py:574-575 `"rank_stale": bool(blocks) and close_status in RANK_STALE_STATUSES`; src/holo/receiver/format/close.py:272 `return CloseResult("open", None, k_total, blocks, n_used, …)` is a completed solve. engine.py `_close_consult`: `solve = (not no_close and bool(certs) and (final if complete else (ready or final)))` — once ready holds, every consult re-solves, so blocks are fresh and status stays "open" until verified. Caption at server.py:196 `+ (close.rank_stale ? " (rank as of last solve)" : "")`. The discrimi
- [SERIOUS] The client layer is effectively untested — one test greps the shell for id= strings — and every never-zero violation found in this review lives there; the test that names the invariant covers only the six rows, so its name overstates its reach.
  EVIDENCE: src/holo/receiver/tests/test_h3_diag.py:741 `def test_the_home_shell_names_every_pane_img` asserts only `f'id="img-{pane}"'.encode() in body` for four panes — nothing about rows, close, scheduler, selectors, spark, or the never-zero law. test_h3_diag.py:307 `def test_unavailable_facts_are_named_never_printed_as_zero(model_pre)` asserts six-row strings only. The new `consulted` flag is key-checked at test_h3_diag.py:43 (CLOSE_KEYS) and nowhere exercised. Nothing pins the cache/revision contract either: no test asserts a revision bump invalidates a cached pane, or that ?rev= is honoured or ignored; test_h3_
- [MINOR] "wakes per merge" (doc §3 SCHEDULER) ships as a raw cumulative counter, which is the one form of the number that carries no signal — the holo2 result this row exists to surface was a ratio (0.8 wakes/commit).
- [MINOR] The now-line has no per-job age, so a place worker wedged for minutes is indistinguishable from one that started this second; the doc specifies the age and the global "last activity" cannot substitute for it (it moves on any event from any plugin).
- [MINOR] Final-frame economics: at end of run the whole pane set is rendered twice and the event list folded three times, and the duplicate render runs BEFORE the browser's grace window opens, so the operator's last live frame sits stale for that interval.
- [MINOR] The ruled doc now contradicts itself on the pose band: §1's layout block still says full width while §3's heading (updated in the same commit as the code) says half the bottom row; the code is half, leaving the other half of row 2 empty.
- [MINOR] A duplicate scan is invisible to the operator: intake emits CaptureOpen(duplicate=True) and diag drops it entirely, so passing the same file twice reads exactly like passing it once, with no line explaining why the second scan did nothing. The guard that looks like it handles this is dead.
- [MINOR] Pane C's per-tile number sums outcomes across streams while the chips it sits on are per-stream, so the new legend's "decode attempts" reads ~3x high on a colour page relative to the segment the eye is on.
- [MINOR] As UX: the two number-bearing panes are unreadable in the layout that justifies them. Three images plus the scheduler/close table share one 4-column row, so each pane displays at ~25% of window width; pane B's 0..100 site counts and pane C's evidence counts are rasterized to fit a 16 px native tile and land at ~4 px on screen — and glyph rasterization is the acknowledged frame hot spot, so the cost is paid every tick for text nobody reads without zooming.
- [MINOR] No rate anywhere: the only progress instrument is a cumulative-certified sparkline with an auto-scaled y-axis, no labels and no value, so "is it still finding tiles, and how fast" is a slope estimate on a 640x48 canvas; the history is unbounded and fully redrawn every tick.
- [PRAISE] The "one formatter" claim is true, not aspirational: shell rows, the stderr epilogue and report.json all come from six_row_status over the same fold, and a test pins the equality.
- [PRAISE] The tests are exact-value pins, not smoke: verbatim row strings, computed-blend pixel equality, and a PNG byte-equality that proves the address masks OR rather than sum — plus an AST grep that keeps the settled vocabulary honest against place.py.
- [PRAISE] The colour law holds where it matters: durable state fills, transient work is stroke-only, and deep red is defined but genuinely never painted — the design's own §8 rule that the contradiction colour ships with its producer is respected in code.

## Dimension 1 — hard invariants and the engine seam (holo3-diag, committed content)
VERDICT: MERGE_WITH_FIXES

- [SERIOUS] The attempts histogram double-counts every attempt after the first one inside a multi-attempt band, so the scheduler pane's re-work/churn signal reads 2-4x too high and one worker can appear in three bands at once.
  EVIDENCE: src/holo/receiver/engine.py:357-364: `bucket = attempt_bucket(worker.attempts)` … the decrement of the previous band fires only `if previous != bucket`, but `self._attempts_hist[bucket] = …get(bucket, 0) + 1` runs unconditionally. Replaying that exact arithmetic (scratchpad replay against `engine.attempt_bucket`): one worker reaching 5 attempts yields {'3-5': 3} where truth is {'3-5': 1}; one worker reaching 12 attempts yields {'3-5': 2, '6-10': 4, '>10': 2} where truth is {'>10': 1}; a realistic mix (50x1, 20x2, 10x3, 6x5, 3x9) yields {'1':50,'2':20,'3-5':34,'6-10':12} against truth {'1':50,'2':20,'3-5':
- [SERIOUS] EngineStat is emitted once per merge iteration (~1 per job) and retained for the run, but the fold keeps only the most recent one — 371 MB of never-read objects on a 243k-job sheet, paid whether or not --diag is passed.
  EVIDENCE: Emitted unconditionally at src/holo/receiver/engine.py:179-190 (`self._events.append(data.EngineStat(queued=tuple(sorted(...)), … attempts_hist=tuple(sorted(...))))`), two freshly built tuples-of-tuples per event; consumed at src/holo/receiver/diag/model.py:259-260 `elif isinstance(event, EngineStat): working.engine_stat = event` — last value only. Measured on the K sim: 165 EngineStat for 176 jobs (0.938/job), 866 B/event by deep getsizeof. Measured RSS at 243k-job scale with the engine's own tuple shapes (11 plugins, 5 bands, shared name strings): EngineStat alone 371 MB, JobStarted alone 28 MB; whole new bill vs o
- [SERIOUS] Diag-only computation runs inside the placement job, and job exceptions are unguarded — a defect in diag-only geometry code aborts the decode, contradicting 'no diag failure may change payload, status, or exit code'.
  EVIDENCE: src/holo/receiver/plugins/place.py:835 `coverage = _address_coverage(placement, local_shape, job.row)` sits on the accepted-placement path of run_window_pass, which is the executor job (place_sched.py:135-152). _address_coverage (place.py:639-670) does modulo/index/packbits arithmetic that serves only pane B's address overlay. src/holo/receiver/engine.py:374 `result: data.JobResult = future.result()` has no try/except (the only `except` clauses in engine.py are 115/125/138, all in the _diag_serve/_diag_stop/_diag_products wrappers), so any raise inside the job propagates out of run(). Every other diag entry point IS 
- [MINOR] The scheduler block prints 0 for stale skips / retired / wakes before any EngineStat exists, violating the never-print-zero rule that the six rows in the same file honour correctly.
- [MINOR] RegionMark.cells publishes the survey's own array by reference rather than a copy, and it is not small — the one genuinely new ndarray in the event stream.
- [MINOR] Four doc/code divergences in the invariants the doc states absolutely.
- [PRAISE] Byte-identity viewer-on vs viewer-off holds, measured, and the diag counters are provably inert in the decode path.
- [PRAISE] The one decision-path line the branch changed in the engine is behaviour-preserving, and I verified it rather than assuming.

## Dimension 4 — merge verification (holo3-diag → holo3), hands-on in a throwaway worktree
VERDICT: MERGE_WITH_FIXES

- [BLOCKER] The naive conflict resolution (resolve engine.py, accept git's auto-merge elsewhere) produces a tree that passes pyflakes and imports fine but crashes on the first job dispatch. HEAD deleted the `attempts` field from WorkerBookmark in descriptor.py — a file the diag branch never touched, so git auto-merged the deletion with no conflict — while the merged engine.py still reads `worker.attempts`. The conflict marker and the deleted field are in different files, so nothing points the merger at the break.
  EVIDENCE: src/holo/receiver/descriptor.py, HEAD-side deletion at the WorkerBookmark dataclass: `-    attempts: int = 0` (commit ec42fa3, alongside job_price/REWORK_FLOOR/REWORK_SLOPE removal). Merged src/holo/receiver/engine.py:345 still carries `worker.attempts += 1` and :348 `bucket = attempt_bucket(worker.attempts)`. Measured by actually running the naive resolution: `E  AttributeError: 'WorkerBookmark' object has no attribute 'attempts'` / `src/holo/receiver/engine.py:345: AttributeError`; fast lane result `12 failed, 1236 passed, 367 skipped, 33 errors in 12.09s` (33 errors all in test_h3_engine_contract.py). FIX (2 edits): descripto
- [BLOCKER] A second silent semantic break that the FAST LANE CANNOT SEE. HEAD added a new helper reading `report["plugin_rows"]`; the diag branch moved that data to `report["scheduler"]["plugins"]` and renamed its own consumers. Git took both hunks cleanly. The merged tree passes pyflakes and the full fast lane, and fails only under HOLO3_RUN_SLOW_TESTS=1 — so a merger who runs only the fast lane ships a broken churn tripwire.
  EVIDENCE: HEAD-side addition (commit ec42fa3) src/holo/receiver/tests/test_h3_e2e_sims.py:299-301 `def _serial_jobs(record)` → `for row in record.report["plugin_rows"]}`. Diag-side rename of the identical access in src/holo/receiver/tests/test_h3_degraded_sim.py:32-33 `for row in record.report["scheduler"]["plugins"]}`. Merged report has no top-level plugin_rows: src/holo/receiver/diag/model.py:554 emits `"scheduler": {` with `"plugins": plugins,` nested inside. Measured: fast lane GREEN `1281 passed, 367 skipped in 13.62s` while slow lane failed `KeyError: 'plugin_rows'` / `src/holo/receiver/tests/test_h3_e2e_sims.py:301` → `FAILED test_k_serial_job
- [SERIOUS] Follow-on shape mismatch behind that same fix: the two report structures are not interchangeable. Diag's `scheduler.plugins` lists queued-but-never-run plugins with jobs=0; HEAD's `plugin_rows` only ever held plugins with at least one JobDone. Re-pointing the helper without filtering flips HEAD's golden on rows that represent no churn at all.
  EVIDENCE: Cause at src/holo/receiver/diag/model.py:516 `names = sorted(set(queued) | set(model.plugin_rows)` union'd with inflight — so queue depth alone mints a row. Measured failure after the naive re-point: `E  actual   {'calibrate': 45, 'ctx': 9, 'place': 66, 'refine': 0, 'revisit': 0, 'survey': 1, 'tiles.retry': 18, 'tiles.scan': 88}` vs HEAD's golden K_SERIAL_JOB_COUNTS (test_h3_e2e_sims.py:304) which omits refine/revisit — the six non-zero counts match exactly, only the two zero rows differ. The `if row["jobs"]` filter is provably equivalent to HEAD's semantics, not a golden weakening: model.plugin_rows is b
- [SERIOUS] The resolution restores a field HEAD deliberately deleted, and that intent reversal deserves an explicit note in the merge commit or the next reader will think rework aging came back. I recommend keeping it (option A) over the alternative of dropping the attempts histogram (option B), because the histogram carries real operator signal — but this is a judgement call the merge should record rather than bury.
  EVIDENCE: Measured on a live K decode, final report.json: `attempts_hist [['1', 47], ['2', 12], ['3-5', 86], ['6-10', 40], ['>10', 7]]` — 47 workers fired once, but 40 fired 6-10 times and 7 fired more than 10. Dropping the histogram (option B) would delete that and require touching 6 more files: engine.py (ATTEMPT_BUCKETS/attempt_bucket/_attempts_hist), data.py:332 `attempts_hist: tuple[tuple[str, int], ...]`, diag/model.py:556, diag/server.py:160-163, tests/test_h3_diag.py:40/198/585, tests/test_h3_engine_contract.py:811, plus docs/DIAG-DESIGN.md:138 and :214 which rule the pane and the event contract
- [PRAISE] Merge mechanics are otherwise excellent and the merge is behaviorally inert on the K path. The conflict surface is one file and one hunk despite ~2,400 lines changing on the diag side, and the design's hardest invariant — a run with the viewer on is byte-identical to viewer off — holds field-by-field, not just at the payload sha.
- [MINOR] One smoke observation that is correct behavior, not a defect, recorded so it is not mistaken for one later: a pane request issued the instant the port opens returns 404, because panes do not exist until a page does. It is a clean typed refusal, not a crash, and it satisfies the 'never print zero for unavailable' rule.

## Dimension 2 — the event contract and producer bill (holo3-diag: data.py event types, producers in intake/survey/place/words/engine)
VERDICT: MERGE_WITH_FIXES

- [SERIOUS] The attempts histogram double-counts a worker every time it re-attempts WITHIN a bucket, so the scheduler pane's re-work/churn band over-reports and can never come back down.
  EVIDENCE: src/holo/receiver/engine.py:357-364 — the increment `self._attempts_hist[bucket] = …get(bucket, 0) + 1` is unconditional, but the decrement at :361-362 fires only `if previous != bucket`. Attempts 4 and 5 both land in "3-5" with no matching decrement. Measured on the K sim: reported `attempts_hist=(('1',103),('2',26),('3-5',6))` sum 135 vs ground truth from `_bookmarks` `(('1',103),('2',26),('3-5',4))` sum 133 workers — +50% in exactly the band DIAG-DESIGN §3 calls "the re-work band = churn". A worker reaching 10 attempts contributes 2 to "3-5" and 5 to "6-10" simultaneously.
- [SERIOUS] Pane A's done-wash rebuilds its own composite frame (survey region origin + survey region pitch + window extent) instead of applying the `native_affine` that rides the very same PoseCommitted event — the ruled "renderer applies exactly one transform" invariant, and it misregisters measurably.
  EVIDENCE: src/holo/receiver/diag/panes.py:448-460 builds `frames_by_region = {…: (mark.origin_yx, mark.pitch_px)}` and panes.py:386-433 projects via `origin_x + (cx0 + lx0) * pitch`. Measured on the K sim, per-window distance between that projection and the emitted affine (`geometry.compose_from_native(pose.native_affine, 1)` applied once to the page-origin cell): 8.1 px at the near corner rising to 13.8 px at the far corner (region pitch 5.9883 vs the placement's own 5.99999; region origin (189,189) vs affine (194.5,194.9)). Error grows with distance from the region origin and the projection has no rotation/skew t
- [SERIOUS] EngineStat has no representation for "not measured yet", and the scheduler block prints hard zeros for stale skips / retired / wakes before the first merge — the one hard invariant the six rows and the close block both honour.
  EVIDENCE: src/holo/receiver/diag/model.py:559-561 `"stale_skips": stat.stale_skips if stat is not None else 0` (same for retired, wakes; attempts_hist → []), rendered verbatim at src/holo/receiver/diag/server.py:163-169 as "attempts none · stale skips 0 · retired 0 · wakes 0". Contrast model.py:371 `"frontier unavailable before the first merge"` and server.py:177-183 which gates the whole close block on `close.consulted` with "K, metadata, blocks unavailable before the first close consult". DIAG-DESIGN §0: "Never print zero where the fact is unavailable"; §3 SCHEDULER: "Only numbers the engine actually produces — no promises w
- [SERIOUS] WordOutcome is emitted only for the candidate that bootstrapped an accepted placement, so pane B's "word-solved" chip colour reports a far narrower fact than its name — and `result` is a one-valued field.
  EVIDENCE: src/holo/receiver/plugins/place.py:827-834 emits WordOutcome only under `if route == ROUTE_WORD and word_candidate is not None`, always `result="solved"`; the consumer at src/holo/receiver/diag/model.py:164-166 then re-tests `event.result != "solved"` — dead vocabulary on both ends. Measured on the K sim: routes `Counter({'chain': 17, 'word': 1})`, 1 WordOutcome, 48 certified tiles on a 7x7-tile page. Pane B lights exactly one word-solved chip on a fully recovered page. Failed/refused word attempts (`no_word_candidate_centre` 9, `no_word_candidate_rest` 8) produce no WordOutcome, so `errors`/`sites` describe successe
- [MINOR] `PoseCommitted.shape_yx` is exactly derivable from `extent_cells` on the same event — a redundant field, and it is not in the doc's producer bill.
- [MINOR] The governing doc's producer bill is stale in three places, one of them a direct contradiction.
- [MINOR] Every new field encodes "unavailable" as a value that is also legitimate — zero — including `rot_k` and `ordinal`, where 0 is a real reading.
- [MINOR] Two counter updates use a magic `1` default to make a can't-happen path land on zero — guard-shaped arithmetic that hid the histogram bug.
- [MINOR] `_address_coverage` is the only diag-only computation that runs unguarded inside a worker on the payload path — cheap, but its failure fails the decode.
- [MINOR] `_SITE_INDEX_CACHE` introduces the only module-level mutable cache in holo3 production code, and it exists solely to feed a diag event.
- [MINOR] One job identity is carried in three shapes across the contract — decomposed in the window events, raw in JobStarted, stringified in JobDone — and the model bridges them with `str()`.
- [MINOR] EngineStat is a full snapshot appended once per merge while only the last one is ever consumed — it is the second-largest contributor to events.jsonl on the smallest sim there is.
- [MINOR] A palette constant for the contradiction state is defined but never referenced.
- [PRAISE] Emission is not gated on `--diag`, which makes the byte-identity invariant structural rather than something tests have to defend — and the A/B run confirms the producer changes are pure emission.
- [PRAISE] The two cheapest-looking producer hunks are genuinely free: `visible` reuses a value the decoder already computed, and RegionMark publishes the survey's own read-only array by reference.


## Intent audit (2026-08-30, holo3 @ 8fc4028 → the applied-fix commits)

Three-dimension audit of the day's delta 28cf0c2..8fc4028 against
_distill/RULINGS-NIGHT.md (Germano's verbatim words), DESCRIPTOR-PLAN
addenda, CLOSE-PORT-SPEC and D6-EXECUTION. Mechanical findings were
applied in 2543bbe / 1b8db87 / edc8b1d / bcd6155 / 3569719; the ruling
list went to the morning report. What follows is the RECORD-ONLY
residue — true, worth knowing, nothing to change tonight.

Every claim below marked [verified] was re-checked against the tree by
the applier, not taken from the audit report. That discipline is the
point: THE SPECIMEN CLASS OF THE NIGHT IS CLAIMS IN COMMIT BODIES AND
REPORTS THAT WERE NEVER CHECKED AGAINST THE TREE.

### Commit bodies whose claims the tree does not support

- **1968590 (two-pass crop streaming) reports lane numbers that cannot
  have come from its own tree.** It claims "fast lane 1329 passed / 367
  skipped; slow lane 1675 passed / 4 skipped". The two are mutually
  inconsistent (1329+367 = 1696; 1675+4 = 1679) and its tree collects
  1670. 1329 is its CHILD's count — 1cd3dfa added 26 pins and correctly
  says "was 1303" — so the worker read a shared worktree carrying the
  parallel refine worker's uncommitted work. Neighbours reconcile
  exactly (1d8a52e 1666 = 1299+367 as claimed; 1cd3dfa 1696 = 1329+367
  as claimed). CONSEQUENCE: the body's other gate claims — colour-sim
  w1 payload sha ddf7aceb… + certificate signature a418a9a5… "identical
  to d6-baseline… the bit-exactness proof" — carry no independent
  credibility from that commit. They are, however, TRUE OF THE TIP:
  the applier re-ran all four sims against _distill/d6-baseline at the
  post-audit tree and every hard field is identical (payload sha, cert
  signature, cert addresses, per-cert bits), colour
  ddf7acebcd86ae52 / a418a9a5230d1eec, K 59495601d00fa781 /
  028cee2647bdd0ba. So the property holds; only that commit's evidence
  for it does not. [verified]
- **1cd3dfa's prose contradicts its own test.** The body says retirement
  moved to "a fully certified (or empty) reach". An empty reach does
  NOT retire: refine.py:544 `return bool(reach) and …`, same shape in
  color_refine.color_refine_exhausted:330 — both False on empty. The
  commit's own added test is
  `test_an_empty_reach_is_not_an_exhausted_one`. Code and test are
  right; the sentence is wrong. [verified]
- **1d8a52e asserts "K's context was never capped — calibrate.py
  untouched" in a commit that edits calibrate.py** (two hunks:
  `_window_cost` and `_ctx_cost` gain the attempts/last_cost
  parameters). The substantive half is true — no cap ever existed
  there. [verified]
- **b1bfd4d's "absorb is O(new)" is not what the code does.**
  CloseProgress.absorb iterates the ENTIRE certificate dict on every
  consult (`for key, cert in certificates.items(): if key in
  self._processed: continue`); only the per-certificate work is O(new).
  At sheet-I scale (5,297 certificates x hundreds of consults) that is
  an O(all)-per-consult scan — still far cheaper than the removed
  rebuild + decode_metadata, so the WIN is real and the measured
  −27%/−69% consult CPU stands; the stated complexity is wrong.
  [verified]
- **e58d1de's "Grep over the post-merge tree including diag/: no reader
  anywhere" for RegionColorModel is false**, and 1d8a52e silently broke
  the same file by deleting stride_select. Both trees carry the
  references (src/holo/receiver/docs/conversion_docs/verify/verify_color_region.py:672,
  102-103, and the live _distill copy). Neither commit body mentions
  conversion_docs/verify. Mitigating and now recorded in-tree: the D4
  gate "all existing verify scripts green" was ALREADY collectively
  dead from verify_tiles.py / verify_engine.py (TileEvidence, deleted
  in e995e28). [verified]
- **1e2182a is the only production-touching commit in the range with an
  entirely empty gate cell.** It changed six decode-path files
  (data.py, engine.py, plugins/{place,words,intake,survey}.py; 9 files,
  502 insertions) and its body ends at "bare-engine fixture learns the
  counters" with no test counts, no pyflakes line, no sim claim. By
  contrast a0e06bd and 31a6262 honestly declare the failure they
  inherited. The tip was re-gated later at c54cd4c, so the property is
  covered; the commit itself is unverified. [verified]
- **876d379 ships new pane logic with no test and no gate line**
  (+16 lines of renderClose() JS inside a Python string; test-def count
  unchanged 995 → 995). The close-state port's own diag-seam contract
  listed "display-side shortfall sum" as a follow-up owed a test
  adaptation. It is also an ownership deviation: CLOSE-PORT-SPEC
  allocated the pane follow-ups to paper-c2 ("after I confirm the
  port") and it landed in this worktree. The end state is coherent —
  holo3-diag sits exactly at 876d379, consistent with the coordinated
  rebase — so this is a record, not a defect.
- **1d8a52e's slow-lane count is off by one against its own tree**: it
  claims 1661 passed + 4 skipped = 1665 where the commit collects 1666.
  Its fast-lane line reconciles exactly. A fifth skip, an xfail, or a
  miscount — worth one grep before the number is quoted onward.

The unverified-claims class is otherwise CLOSED for this delta as far
as falsification could reach: the time-law chain's final claims were
re-run (hygiene 13 green, fast lane 1372 at 8fc4028, production
wall-clock scan clean but for the one licensed diag finish-grace site),
the close-port provenance clause was proven by history (`git log -S` on
engine.py empty; d427dce is not an ancestor), and the structural claims
of 1d8a52e / e58d1de / 9a15a51 / b1bfd4d were each re-checked.

### Design observations — true, latent, no action tonight

- **The placement cell's schema answer holds only by accident.**
  `placement_ordinal`'s third term is `-quality`, and quality is
  `search_mismatch` (place.py:810) produced by three different search
  procedures over different support masks and floors — chain (:727),
  word (:738), cold (:760) — with no evidence-base term. It is harmless
  today only because the basis-major terms dominate (2026-09-12: the
  ordinal is now (route, field revision, certificate count, -quality)
  — the handoff's R6 — and the observation stands), `place` writes at
  most once per window (`place_sched._place_eligible` requires `not
  state.placed`), and refine/refine.color are mutually exclusive by
  family. Change any of those three and the ordinal starts comparing
  units that were never commensurable. [verified]
- **`_fold_placement` can now return changed=True with an empty key
  tuple** — better quality, identical pose and route — where the old
  early return said False. That inflates JobDone pose accounting and
  re-runs `_births`. Latent only: refine refuses `unchanged_affine` and
  place writes once. [verified]
- **`_pose_gen` survives DESCRIPTOR-PLAN addendum 8's absolute "ZERO
  hashes/epochs/generations survive".** store.py:88/173/271/445: a
  per-window monotone counter, bumped only on a real affine change,
  feeding place_sched's `pose/{…}/g{generation}` anchor ids and the
  done_cells cache-validity stamp. FAMILIES-AUDIT declares it and W10
  requires it, and it is not a staleness mechanism in the wake sense —
  but the plan's wording admits no survivor and no test pins the
  exception. [verified]
- **`cost()`'s `last_cost` parameter is dead surface.** Threaded
  through all eleven descriptors, read by none — only `attempts` is
  used (color_region.py:839); the sole reader of `last_cost` is the
  test probe `_recording_descriptor`. It STANDS: Germano ruled it in as
  data ("the worker receives the previous cost and run ordinal"), and
  the engine passing data it does not interpret is the point. Recorded
  so nobody "cleans it up" as unused. [verified]
- **34b1428's opt-in holo1 arm leaves a coverage residual.** Making the
  crop self-check's holo1 side opt-in has a real measured reason
  (>20 min, 7.9 GiB RSS) and the battery-side argument is sound (40
  holo1 certs, zero out-of-bbox, zero GT mismatch on e029) — but the
  default self-check now exercises neither holo1's build_command
  invocation shape nor its address frame, so a break there surfaces
  only during a battery run.
- **ca28219 (COLOR-REDESIGN.md) traces to no row in RULINGS-NIGHT.md.**
  Docs-only, self-labelled "Charter input only — nothing built,
  ratification pending", and recorded in the project memory — so not an
  unauthorized change, but under the declared source-of-truth doctrine
  it has no ledger row. [verified]
- **DESCRIPTOR-PLAN addendum 11's Tier-2 leg is now due and undisposed**:
  "crop pins for scan-borne bugs (half-cell class), pending the crop
  harness go". The go was ruled (59cc634); src/holo/receiver/tests contains no
  crop-derived module. The half-cell fork is the exact bug class the
  ladder already paid for twice, and the harness now exists to make
  such pins affordable.
