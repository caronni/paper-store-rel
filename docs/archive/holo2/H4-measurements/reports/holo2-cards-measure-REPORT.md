# Post-parallelism-cards measurement — real-sheet re-measure + the commit-path profile

Measurement operator's report. Tree under measurement:
`<checkout>` pinned at **8d4107a** (all three
parallelism cards — refine, Chien, lockstep BM — live by default). Nothing
in the repo was edited; every clock, counter, wrapper and profiler lives in
the drivers under `scratch/holo2-demo/` (L12).

Machine: 10 logical CPUs, 64 GiB. Runs strictly sequential, one decode at a
time, each under `/usr/bin/time -l`. Ports 8701+ (job A), 8711+ (job B).

---

## JOB A — the real-sheet re-measure

Sheet `scratch/in/xerox-canon-c2-bw.tiff` @ 4800 dpi (2.29 GB capture),
row `c2-r0700@3392x2368`, expected payload `c2bw-waved.bin`.
Driver `run_decode_ab.py`; logs `scratch/holo2-demo/cards-real-*.log`.

**All three runs PASS: VERIFIED and BYTE-IDENTICAL** (payload 465,580 B,
sha `e5021f8d099587c3…`, the same digest all three runs and both epochs).

| | serial (W1) | W4 | W8 |
|---|---|---|---|
| **wall, pre-cards (W2 exit)** | **290 s** | not run | **287 s** |
| **wall, post-cards** | **258 s** | **224 s** | **231 s** |
| speedup vs pre-cards | 1.12x | — | 1.24x |
| status | VERIFIED | VERIFIED | VERIFIED |
| vs `c2bw-waved.bin` | BYTE-IDENTICAL | BYTE-IDENTICAL | BYTE-IDENTICAL |
| certified tiles | **1358** (= serial pin) | **1358** | 1357 |
| commits | 1919 | 1921 | 1890 |
| fires | 1930 | 1932 | 1903 |
| wakes/commit | 0.82 | 0.82 | 0.82 |
| useful fires | 0.99 | 0.99 | 0.99 |
| stale discards | **0** | 12 | 49 |
| peak inflight | 0 (serial) | 4 | 8 |
| fire busy (thread-seconds) | 103.1 s | 674.2 s | 1537.3 s |
| utilisation (busy / wall·W) | 40.0% | 75.4% | 83.4% |
| fire wall median / p90 / max | 4.0 / 142 / **34115** ms | 139 / 573 / **37590** ms | 328 / 1545 / **35415** ms |
| max RSS | 29.9 GiB | 29.9 GiB | 29.9 GiB |
| user / sys | 237.1 / 10.3 s | 261.0 / 17.9 s | 282.5 / 42.6 s |
| instructions retired | 3.623 T | 3.709 T | 3.798 T |
| cycles | 0.792 T | 0.863 T | 0.982 T |
| IPC | 4.57 | 4.30 | 3.87 |
| involuntary ctx switches | 63,064 | 1,760,873 | 4,742,581 |

Epoch-over-epoch, same sheet, same driver:

| | serial | W8 |
|---|---|---|
| wall | 290 → **258 s** (1.12x) | 287 → **231 s** (1.24x) |
| fire busy | 122.1 → 103.1 s | 1974.0 → 1537.3 s |
| instructions | 3.852 → 3.623 T (−6.0%) | 4.273 → 3.798 T (−11.1%) |
| cycles | 0.884 → 0.792 T (−10.4%) | 1.222 → 0.982 T (−19.6%) |
| IPC | 4.36 → 4.57 | 3.50 → 3.87 |
| involuntary switches | 95,749 → 63,064 | 10,165,697 → **4,742,581** |
| max RSS | 25.8 → 29.9 GiB (+16%) | 27.9 → 29.9 GiB (+7%) |

### What job A says

1. **The cards are real on paper too, but small: 1.12x serial, 1.24x at
   W8** — against 2.57x / 3.72x on gen-clean. Same code, same cards. The
   difference is not the cards; it is what the real-sheet wall is made of.
2. **The thread ceiling moved but stayed low: 1.01x → 1.15x.** Post-cards
   the best threaded run is **W4 at 224 s** (1.153x over serial); W8 is
   *slower* than W4 (231 s, 1.119x). Pre-cards, W8 bought 1.010x — i.e. the
   pool was exactly at its ceiling. **W4 is the operating point on this
   sheet**, and the lockstep-BM card is what made W8's extra threads stop
   being pure tax (involuntary switches halved, IPC 3.50 → 3.87).
3. **60% of the serial wall is not in a fire at all** (258 s wall,
   103 s fire busy ⇒ **155 s residual**). Pre-cards it was 168 s of 290 s
   (58%) — the cards took 19 s off the fire side and 13 s off the residual,
   so the residual's *share* went UP. This is the same statement the
   gen-clean row makes ("the bottleneck moved to the commit path"), and on
   the real sheet the residual was always the majority.
4. **The residual is not all commit path.** Gen-clean serial residual is
   97 s at 1918 commits; real-sheet serial residual is 155 s at 1919
   commits — near-identical commit counts. The 58 s difference is
   ingest/survey of a 2.29 GB capture versus a 134 MB one (INFERENCE from
   the two residuals, not a measured split; job B measures the gen-clean
   side directly).
5. **A single ~35 s fire exists in every run** (max fire wall 34.1 / 37.6 /
   35.4 s) = a third of all serial fire-side thread-seconds in ONE task. It
   is not today's binding constraint (155 s residual > 35 s), but it is a
   hard floor on the fire side that no worker count can cross.
6. **Certified counts hold the pooled band**: serial 1358 = the serial pin
   exactly; W4 1358; W8 1357. Zero stale discards serial, 12 at W4, 49 at
   W8 — the expected pooled cost, and it costs one tile at W8, not
   correctness.
7. **Anomaly — RSS grew +16% serial / +7% W8** (25.8 → 29.9 GiB), and all
   three post-cards runs sit at the same 29.9 GiB. Consistent with the BM
   card's batched word sweep holding (H,127) candidate-row arrays; it is a
   memory-for-speed trade nobody has priced. 29.9 GiB of 64 GiB is fine on
   this machine; it is worth a line in the row because a 2x sheet would
   not be.

---

## JOB B — the commit-path profile

**Headline: the profile CONTRADICTS the serializer hypothesis. Encode+digest
of batches is 0.19% of main-thread CPU. The encode-at-propose card buys
1.002x serial and moves the thread ceiling by +0.001x. It should not be
built.** What the main thread actually spends its commits on is
`_absorb` → `_refresh`: a full re-enumeration of the work frontier, and
inside it a full rebuild of the derived store index, once per commit.

Both runs gen-clean (`e028-genclean-c2-r0700.tiff` @ 1200 dpi), SERIAL,
both VERIFIED and BYTE-IDENTICAL against `w1a-gc-serial.bin`.

* `cards-profile.log` / `cards-profile.pstats` — cProfile around the whole
  `decode()`. `workers=1` takes `Orchestrator._run_serial`, so every frame
  (fire-side and commit-side) is on the profiled thread. **Its wall (368 s)
  is disqualified; it is used for RANKING only.**
* `cards-commitcost.log` / `.commitcost.json` — the same decode with
  `time.thread_time` wrappers instead of a profiler. **Wall 208.0 s against
  the 209.7 s unprofiled anchor: the instrumentation is free, so these are
  the honest seconds** and every number below is from this run unless
  marked "profiled".

Analysis scripts: `profile_attribute.py`, `profile_absorb.py` (both read
the pstats; no repo file was touched).

### The main thread, top down (profiler-free, 1918 commits / 2323 fires)

| | seconds | % of 207.6 s wall | per call |
|---|---|---|---|
| fire side (`_propose`) | 110.96 | 53.4% | 47.8 ms/fire |
| **main-thread-only (wall − fire)** | **96.66** | **46.6%** | |
| ├ **commit path (`Orchestrator._apply`)** | **79.18** | **38.1%** | **41.3 ms/commit** |
| │  ├ `_absorb` → `_refresh` (re-enumeration) | **76.75** | **37.0%** | = **96.9% of the commit path** |
| │  ├ ‑‑ of which `StoreIndex.build` | 54.52 | 26.3% | 28.4 ms × 1921 builds |
| │  ├ `CommitEngine.apply` — THE TRANSACTION | **1.45** | **0.7%** | 0.758 ms/commit |
| │  └ close consult (`_maybe_consult`) | 0.98 | 0.5% | 0.42 ms |
| ├ `blobs.put` (n=6975) | 0.65 | 0.31% | 0.093 ms |
| ├ `journal.append` (n=4242) | 0.42 | 0.20% | 0.099 ms |
| ├ `store.mark_start` (dispatch marker) | 0.34 | 0.16% | 0.148 ms |
| └ `store._frame` (4 snapshots) | 0.24 | 0.12% | 60.5 ms |

### (a) What fraction of main-thread CPU is ENCODE + DIGEST of batches?

**0.194% of main-thread CPU (0.399 s of 205.5 s).** Split:

| site | seconds | % of main CPU | per call |
|---|---|---|---|
| wall side — `digest_json` inside `CommitEngine.apply` (+ its `canonical()`) | **0.083** | **0.040%** | 0.043 ms/commit |
| fire side — `batch_id(batch)` in `_propose` | 0.316 | 0.154% | 0.136 ms/fire |
| **total** | **0.399** | **0.194%** | |

Two facts that decide the card:

1. **The workers ALREADY serialize and digest their own batches, and the
   result is thrown away.** `Orchestrator._propose` computes
   `batch_id(batch)` — canonicalize + JSON + SHA-256 — into
   `Proposal.batch_id`, and **nothing in production reads that field**
   (verified by grep over all of `src/`: the only readers are a test spy,
   `tests/engine/test_pool.py:1016`, and replay, which deliberately
   recomputes its own `engine.settled_id(proposal.batch)` instead). The
   card's mechanism exists; it is dead code costing 0.32 s per serial run.
2. **The wall's re-encode is 100% redundant, measured.** Instrumenting
   `_settle_merges` over the whole run: **same-object 555, new-object-but-
   VALUE-EQUAL 1364, VALUE-DIFFERS 0 — 1919/1919 = 100.0%.** The tile
   family's `join_tiles` always constructs a fresh `TileRecord`, so an
   identity test says 71.1% of batches "changed"; a VALUE test says none
   did. That is exactly what the algebra predicts in serial (nothing can
   commit between a fire's read and its own wall), so the propose-side id
   is already the post-merge id the journal wants.

Even so: the wall-side encode+digest it would remove is **0.083 s of a
207.6 s wall — 0.04%.**

### (b) Is `canonical_json_bytes` on the stdlib C encoder? YES.

`core/codec.py:44` calls `json.dumps(obj, sort_keys=True,
separators=(",",":"), ensure_ascii=True, allow_nan=False)` — no Python
object walk. `sort_keys`/`separators` skip `dumps`'s `_default_encoder`
fast path, so a `JSONEncoder` is constructed per call, but `encode()` still
reaches `c_make_encoder` (indent is None, one-shot). The profile confirms
it: `canonical_json_bytes` has exactly two children — `__init__.py:185:dumps`
(0.24 s / 11,752 calls ≈ 20 µs) and `str.encode` (0.00 s). Nothing to win
here; the "stdlib C encoder" cure named in the MEASUREMENTS row is
**already in effect**.

The Python-side work is *building* the dict, not dumping it —
`encode_dataclass`/`encode_value` walk type hints (profiled cum 1.78 s /
1.62 s vs `dumps` 0.24 s, so ~7x the encoder). Still 0.5% of profiled CPU:
irrelevant at this scale.

### (c) What else in the commit path is material — top functions

Profiled cumtime (RANKING only; cProfile taxes Python calls, so
Python-heavy frames are over-weighted — see the calibration note below):

| cum s | % profiled | tot s | n | per call | function |
|---|---|---|---|---|---|
| 213.25 | 60.9% | 0.00 | 2,323 | 91.8 ms | `orchestrator.py:672:_apply` |
| 211.40 | 60.4% | 0.01 | 2,323 | 91.0 ms | `orchestrator.py:677:_commit` |
| **207.57** | **59.3%** | 0.01 | 1,917 | 108.3 ms | **`orchestrator.py:765:_absorb`** |
| **206.6** | **59.0%** | — | 1,581 | 130.7 ms | **`orchestrator.py:450:_refresh`** |
| 145.55 | 41.6% | 0.25 | 1,686,092 | 0.086 ms | `plane.py:146:index` |
| **143.94** | **41.1%** | 10.37 | 1,919 | 75.0 ms | **`tilemap.py:121:StoreIndex.build`** |
| 120.58 | 34.4% | 0.57 | 1,680,271 | 0.072 ms | `plane.py:431:tiles` |
| 96.52 | 27.6% | 3.80 | **12,415,410** | 0.008 ms | `solve/keys.py:131:parse_evidence_key` |
| 47.63 | 13.6% | 2.12 | 6,625,247 | 0.007 ms | `solve/keys.py:80:tile_key` |
| 23.68 | 6.8% | 0.04 | 1,921 | 12.3 ms | `store.py:451:keys` — `tuple(sorted(entries))` |
| 5.42 | 1.5% | — | 1,677,186 | 0.003 ms | `orchestrator.py:480:_offer` |
| 3.41 | 1.0% | 0.04 | 1,919 | 1.78 ms | `commit.py:315:CommitEngine.apply` |
| 1.85 | 0.5% | 0.00 | 2,323 | 0.80 ms | `orchestrator.py:792:_maybe_consult` |
| 0.90 | 0.3% | 0.01 | 1,919 | 0.47 ms | `store.py:520:apply_committed` |
| 0.83 | 0.2% | 0.01 | 2,323 | 0.36 ms | `commit.py:232:batch_id` (dead) |
| 0.81 | 0.2% | 0.02 | 4,242 | 0.19 ms | `journal.py:303:append` |

**The exclusive hot list is key machinery — 127.8 s = 36.5% of profiled
main-thread CPU:**

| tot s | % | n | function |
|---|---|---|---|
| 52.31 | 14.9% | 12,421,463 | `core/keys.py:234:parse_key` |
| 17.43 | 5.0% | 26,555,246 | `core/keys.py:116:key_parts` |
| 16.88 | 4.8% | **88,851,419** | `<string>:14:__lt__` (`ResourceKey`, `order=True`) |
| 14.14 | 4.0% | 6,642,100 | `core/keys.py:206:build_key` |
| 11.21 | 3.2% | 124,202,312 | `core/keys.py:253:<genexpr>` |
| 5.79 | 1.7% | 86,937,921 | `core/keys.py:198:<genexpr>` |
| 3.80 | 1.1% | 12,415,410 | `solve/keys.py:131:parse_evidence_key` |
| 3.45 | 1.0% | 12,421,463 | `core/keys.py:195:arity` |

For contrast, the post-card fire-side kernels: `berlekamp_massey_many`
36.33 s (10.4%), `chien_root_mask` 24.30 s (6.9%). **The main thread's key
parsing alone outweighs both cards' kernels combined.**

Where the 12.4 M `parse_evidence_key` calls come from (edge attribution):
5,422,705 from `payload_h3bis:162:evidence_footing` (inside `_refresh`'s
expansion) and 1,498,864 from `tilemap.py:121:StoreIndex.build`. The
6.6 M `tile_key` calls: 3,026,332 from `StoreIndex.build`.

**Calibration.** Profiled fire side 121.4 s vs 111.0 s measured = 1.09x
inflation; profiled main-thread-only 228.7 s vs 96.7 s measured = 2.37x.
cProfile roughly doubles the weight of this (call-dense, Python) code. All
*seconds* quoted outside this section are from the profiler-free run.

### (d) Per-commit CPU cost today

| | ms per commit |
|---|---|
| whole commit path (`_apply`) | **41.28** |
| ├ `_absorb`/`_refresh` | 40.0 |
| ├ `CommitEngine.apply` (the transaction) | 0.758 |
| ├ close consult | 0.51 |
| └ **wall-side encode + digest** | **0.043** |

### The mechanism, in one paragraph

`SessionContext.apply` calls `plane.invalidate()` on every commit, which
bumps the generation and drops the derived views. The very next main-thread
act is `_absorb`, which re-enumerates the frontier whenever the commit
touched a structural kind; `_refresh` asks every provider to `expand`;
`payload_h3bis.expand` walks **every open work key**, and for each calls
`resident_footings` + `union_tags`, which call `evidence_footing` →
`parse_evidence_key` on **every evidence piece**. The first plane read in
that pass forces `StoreIndex.build`, which does `tuple(sorted(store._entries))`
— a full sort of every durable key through a Python `order=True` dataclass
`__lt__` (88.9 M comparisons) — then re-`parse`s and re-`build`s every
evidence and tile key it indexes. Both the index and the enumeration are
recomputed from scratch, from *strings*, ~1,900 times per run, and the
answers differ from the previous one by a handful of keys.

### THE CARD, PRICED

Model: `T = S + F` (serial wall = main-thread-only + fire side);
`k = F / (T_W4 − S)` is the **measured** fire-side scaling from the two
unprofiled post-cards anchors (serial 209.67 s, W4 145.26 s):
**S = 97.2 s, F = 112.5 s, k = 2.34x, today's ceiling 1.443x**. (k is the
empirical post-BM number — it already contains the GIL residue, switching
tax and everything else; the kernel-derived f gives 1.44x and the observed
ceiling is 1.443x, so the two agree.)

**Card as written — ENCODE AT PROPOSE:**

| arm | serial | W4 | thread ceiling |
|---|---|---|---|
| wall stops re-encoding (valid for **100%** of settles) | 209.7 → **209.6 s (1.000x)** | 145.3 → 145.2 s | 1.443 → 1.444x |
| + delete the dead per-fire `batch_id` | 209.7 → **209.3 s (1.002x)** | 145.3 → 145.0 s | 1.443 → 1.444x |

- Fraction of the serial wall that moves off the main thread: **0.04%**.
- Share the wall would still have to re-encode (merge-declared keys):
  **0% by value** (0/1919), 71.1% if the test is object identity — so the
  test must be `==`, not `is`, and then the wall re-encodes nothing.
- **Verdict: do not build it.** Not because it is wrong — it is correct,
  and the value-equality result (0/1919) is a genuinely clean licence —
  but because it is worth 0.1 s on a 210 s wall. The one piece worth
  taking is the two-line deletion of the dead `Proposal.batch_id`
  (0.32 s, and it removes a field that reads as load-bearing and is not).
- The protobuf debate is moot at this magnitude: the entire canonical-JSON
  surface, both sides, is 0.4 s of 207.6 s.

**Card the profile actually points at — INCREMENTAL DERIVED VIEWS**
(maintain `StoreIndex` and the enumeration frontier across commits from the
commit's own `changed_keys` instead of rebuilding from sorted strings;
the factors below are ESTIMATES — the 79.2 s is measured, the speedup is
not):

| commit path improved by | serial | W4 | vs today's serial | thread ceiling |
|---|---|---|---|---|
| 2x (conservative) | 209.7 → **170.1 s (1.23x)** | 145.3 → **105.7 s** | 1.98x | 1.44 → **1.61x** |
| 5x | 209.7 → **146.3 s (1.43x)** | 145.3 → **81.9 s** | 2.56x | 1.44 → **1.79x** |
| 10x | 209.7 → **138.4 s (1.52x)** | 145.3 → **74.0 s** | 2.83x | 1.44 → **1.87x** |
| → 0 (the bound) | 209.7 → **130.5 s (1.61x)** | 145.3 → **66.1 s** | 3.17x | 1.44 → **1.97x** |

Sub-targets, in the order the measurement ranks them:

1. **`StoreIndex.build`, 54.5 s = 26.3% of the serial wall**, 28.4 ms ×
   1,921 rebuilds. It is a pure function of the store and the commit
   already carries its own delta (`CommitResult.changed_keys`). The
   `_DerivedViews` generation object already carries two views forward
   (windows, done); the index is the third. Cheapest first step:
   `store.keys()` returns `tuple(sorted(self._entries))` uncached —
   maintaining one sorted key list, or dropping `order=True` from
   `ResourceKey` in favour of a tuple sort key, attacks 88.9 M Python
   comparisons on its own.
2. **`_refresh` re-enumeration, ~22 s beyond the index rebuild**, 1,581
   full passes producing 1,677,186 `_offer` calls that mostly hit the
   "already minted / declined / pending" early-return. The expansion
   re-derives every descriptor's footings by re-parsing evidence keys;
   memoizing `evidence_footing` per key, or carrying the footing beside
   the key instead of *in* it, removes 5.4 M parses.
3. **Do not re-parse keys at all.** `ResourceKey` is `(kind, parts:
   tuple[str,...])` and every consumer parses the strings back into
   values on every rebuild. 36.5% of profiled main-thread CPU is
   construct/parse/compare of keys.

Note these three overlap; they are not additive.

**On the real sheet.** Serial there is 258.5 s with 103.1 s of fire, i.e.
**S = 155.4 s** at 1,919 commits — the same commit count as gen-clean, so
the commit path should cost about the same ~79 s and the remaining ~76 s is
ingest/survey of the 2.29 GB capture (INFERENCE from the two residuals,
consistent with §JOB A note 4). A 10x commit-path win would take the real
serial to roughly **187 s** and W4 to roughly **145 s** — the first change
in this campaign that would move the real sheet more than the synthetic one.

### Anomalies and caveats

- **`_absorb` fires 1,917 times but `_refresh` only 1,581** — a quarter of
  commits absorb wakes without re-enumerating. The re-enumeration is
  already conditional on `structural_kinds`; it is just that tile and
  evidence writes are structural, which is most commits.
- **`plane.index()` is called 1.69 M times and `plane.tiles()` 1.68 M
  times** per run. Each is a cache hit costing a `getattr` + generation
  compare, but 1.7 M of them is itself ~1 s of profiled time. Callers
  fetch the view inside inner loops instead of hoisting it.
- **`blobs.put` is called 6,975 times for 1,918 commits** (~3.6 blobs per
  commit) at 0.093 ms each including `fsync`. Cheap today (0.65 s), but
  note the sha256 is computed **twice** per blob — `stage_array` on the
  worker, then `BlobSidecar.put` re-derives it to verify the staged ref.
  That re-derivation is a deliberate integrity check (`store.py:494`), it
  costs 0.3 s, and it is the only place where "the worker already digested
  it" is true *and* the wall repeats the work. Leave it alone.
- **`store._frame` is 60 ms per snapshot** and only 4 fired (cadence 512,
  gated on no outstanding dispatch). Not a factor serial; worth re-checking
  under a saturated pool, where the docstring already predicts the memo lags.
- The profiled run and the counters run each certified **1357** tiles and
  closed VERIFIED, identical to the unprofiled anchor — the instrumentation
  changed no decode outcome.
- `_maybe_consult` costs 0.98 s total, not the ~80 s a first reading of the
  older `bm-post-w4.gil.json` (`apply` 82 s CPU vs `ctx.apply` 1.6 s)
  suggests. That gap is `_absorb`, which sits inside `_commit` alongside
  `ctx.apply`. Recorded because it is an easy misattribution: the close
  consult is innocent.

### Files

- Job A: `scratch/holo2-demo/cards-real-{serial,w4,w8}.log`, driver
  `run_decode_ab.py`, runner `cards_runs.sh`.
- Job B: `cards-profile.log`, `cards-profile.pstats`,
  `cards-commitcost.log`, `cards-commitcost.commitcost.json`; drivers
  `run_decode_profile.py`, `run_decode_commitcost.py`; analysis
  `profile_attribute.py`, `profile_absorb.py`, `price_card.py`; runner
  `cards_jobb.sh`.
