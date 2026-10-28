# E023b invocation how-to

Run these commands from the repository root. E023b ends at CRC-certified LDPC
tiles; it does not perform fountain/RaptorQ recovery or define a stop
condition. Optional post-run volume evaluation is documented under
[Score one receiver state](#score-one-receiver-state); it is a read-only
outer-layer handoff, not part of E023b processing.

## Choose an arm

| arm | ingestion profile | afterwards | measured certified tiles, decimated / native |
|---|---|---|---:|
| baseline | `pava-v1` | nothing | 742 / 742 |
| BP | `pava-v1` | run `--bp-retry` | 747 / 747 |
| context | `ctx-pava-v1` | nothing | 749 / 746 |
| combined | `ctx-pava-v1` | run `--bp-retry` | **757 / 752** |

`pava-v1` is the default E023b.0 detector. `ctx-pava-v1` adds the
pilot-only, held-out-gated context correction.

The detector profile is frozen when the state is created. Use a fresh,
separate state to compare `pava-v1` and `ctx-pava-v1`.

## Ingest scans

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  scan-1.tiff scan-2.tiff \
  --dpi 1600 --format e018-v3-c3 --pages 0 \
  --capture-groups capture-1,capture-2 \
  --state experiments/023b-integrated-receiver/build/session.pkl \
  --detector-profile pava-v1 --fresh --diag
```

For the context arm, change the profile to:

```text
--detector-profile ctx-pava-v1
```

Omit `--fresh` when appending later independent scans to the same state.

## Apply adaptive BP

BP retry is a separate state-only command: do not pass TIFFs,
`--capture-groups`, or `--fresh`.

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  --dpi 1600 --format e018-v3-c3 --pages 0 \
  --state experiments/023b-integrated-receiver/build/session.pkl \
  --detector-profile pava-v1 --bp-retry --diag
```

Use the state’s frozen detector profile in this command. Thus a combined-arm
state uses `--detector-profile ctx-pava-v1`.

BP retry can be run again after appending new scans. Repeating it without new
eligible evidence is an exact no-op.

## When to apply BP

`--bp-retry` operates only on each tile's latest failed evidence frontier.
Running it once after all scans is therefore not mathematically equivalent to
trying max-150 BP at every historical scan prefix.

The measured comparison is:

| footing / detector | final-only: cert / calls / iterations | after every scan: cert / calls / iterations |
|---|---:|---:|
| decimated / PAVA | 747 / 1,127 / 63,417 | **748** / 1,270 / 108,459 |
| decimated / context | **757** / 1,101 / 57,544 | **757** / 1,241 / 101,340 |
| native / PAVA | **747** / 1,151 / 67,418 | **747** / 1,308 / 117,217 |
| native / context | **752** / 1,125 / 62,246 | **752** / 1,274 / 109,222 |

Calls and iterations are cumulative whole-session totals, including the
ordinary max-60 attempts.

The checked scheduling record is
[`bp_schedule_report.json`](bp_schedule_report.json), SHA-256
`dd3d89b3d583f1c3191b8983f3f24e603998791e96e445e5ce352f01d31479af`.
Reproduce it with:

```text
env/bin/python \
  experiments/023b-integrated-receiver/qualify_e023b_bp_schedule.py
```

Only decimated PAVA gained a final certificate, tile `(0,28,11)`.  The other
three certificate sets were identical.  In particular, the native/decimated
context+BP union remains exactly 769 either way.

Use final-only BP for the measured best method.  Retrying after every scan
cost 140--157 extra CRC-bearing calls and about 44,000--50,000 extra BP
iterations per branch without improving either context branch.

For an explicit prefix-schedule experiment, ingest one TIFF per invocation
and run the state-only retry immediately after each successful commit:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  next-scan.tiff \
  --dpi DPI --format e018-v3-c3 --pages 0 \
  --capture-groups physical-capture-id \
  --state experiments/023b-integrated-receiver/build/session.pkl \
  --detector-profile ctx-pava-v1

env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  --dpi DPI --format e018-v3-c3 --pages 0 \
  --state experiments/023b-integrated-receiver/build/session.pkl \
  --detector-profile ctx-pava-v1 --bp-retry
```

Add `--fresh` only to the first ingestion command, then repeat the pair in the
qualified scan order.  Once several TIFFs have been ingested without the
intermediate retries, current `--bp-retry` does not go back and search their
old frontiers.

No whole E021/E022/payload rerun is needed after a BP certificate.  E023b
currently has no feedback edge from LDPC certificates into segmentation,
placement, calibration, or sampling, and one tile's certificate does not
alter another tile's LLRs.  There is therefore no same-generation recovery
cascade. Such a rerun matters only in the separate E024 feedback generation,
now implemented under `experiments/024-feedback-receiver/`; E023b itself
remains unchanged.

## Highest measured single-footing recovery

The best measured setting is the combined arm on all six 1600-dpi decimated
scans: context + PAVA, then adaptive BP. It certified 757 LDPC tiles.

First ingest the six scans in the qualified order:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  scratch/e018/decimated-1_1600.tiff \
  scratch/e018/decimated-1-2nd_1600.tiff \
  scratch/e018/decimated-2_1600.tiff \
  scratch/e018/decimated-2-2nd_1600.tiff \
  scratch/e018/decimated-3_1600.tiff \
  scratch/e018/decimated-3-2nd_1600.tiff \
  --dpi 1600 --format e018-v3-c3 --pages 0 \
  --capture-groups \
    confetti-1,confetti-1b,confetti-2,confetti-2b,confetti-3,confetti-3b \
  --state experiments/023b-integrated-receiver/build/e018-dec-context.pkl \
  --out experiments/023b-integrated-receiver/build/e018-dec-context.png \
  --report experiments/023b-integrated-receiver/build/e018-dec-context.json \
  --detector-profile ctx-pava-v1 --fresh \
  --diag experiments/023b-integrated-receiver/build/e018-dec-context-diag
```

Then apply adaptive BP to the completed state:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  --dpi 1600 --format e018-v3-c3 --pages 0 \
  --state experiments/023b-integrated-receiver/build/e018-dec-context.pkl \
  --out experiments/023b-integrated-receiver/build/e018-dec-combined.png \
  --report experiments/023b-integrated-receiver/build/e018-dec-combined.json \
  --detector-profile ctx-pava-v1 --bp-retry \
  --diag experiments/023b-integrated-receiver/build/e018-dec-context-diag
```

## Add the native view

Run the same combined arm in a separate state over the six native TIFFs.  The
capture-group names deliberately match the decimated branch: these are
alternate rasterizations of the same six physical captures.

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  scratch/e018/hp-e018-canon-4800-confetti-1.tiff \
  scratch/e018/hp-e018-canon-4800-confetti-1-2ndtake.tiff \
  scratch/e018/hp-e018-canon-4800-confetti-2.tiff \
  scratch/e018/hp-e018-canon-4800-confetti-2-2ndtake.tiff \
  scratch/e018/hp-e018-canon-4800-confetti-3.tiff \
  scratch/e018/hp-e018-canon-4800-confetti-3-2ndtake.tiff \
  --dpi 4800 --format e018-v3-c3 --pages 0 \
  --capture-groups \
    confetti-1,confetti-1b,confetti-2,confetti-2b,confetti-3,confetti-3b \
  --state experiments/023b-integrated-receiver/build/e018-native-context.pkl \
  --out experiments/023b-integrated-receiver/build/e018-native-context.png \
  --report \
    experiments/023b-integrated-receiver/build/e018-native-context.json \
  --detector-profile ctx-pava-v1 --fresh \
  --diag experiments/023b-integrated-receiver/build/e018-native-context-diag
```

Then apply adaptive BP:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  --dpi 4800 --format e018-v3-c3 --pages 0 \
  --state experiments/023b-integrated-receiver/build/e018-native-context.pkl \
  --out experiments/023b-integrated-receiver/build/e018-native-combined.png \
  --report \
    experiments/023b-integrated-receiver/build/e018-native-combined.json \
  --detector-profile ctx-pava-v1 --bp-retry \
  --diag experiments/023b-integrated-receiver/build/e018-native-context-diag
```

This branch certified 752 tiles in the frozen qualification.

## Combine native and decimated recovery

Do not put the twelve TIFFs into one ordinary receiver state and do not give
native and decimated files different physical-capture identities.  Their LLRs
are correlated.

Instead, union only their syndrome+CRC-certified payloads:

```text
env/bin/python experiments/023b-integrated-receiver/merge_e023b.py \
  --source \
    decimated=experiments/023b-integrated-receiver/build/e018-dec-context.pkl \
  --source \
    native=experiments/023b-integrated-receiver/build/e018-native-context.pkl \
  --out \
    experiments/023b-integrated-receiver/build/e018-multiview-certificates.json
```

The merger loads and validates both complete receiver states, requires the
same ordered physical-capture ids, preserves both state hashes and
certificate-boundary provenance, and stops fatally if two certificates for
one tile carry different bits.  It never combines scan LLRs.
Each large state is hashed, validated, and reduced to compact packed
certificates before the next state is loaded; the merger does not retain both
full receiver sessions in memory.

The output is a terminal certificate bundle, not a resumable E023b receiver
state.  Do not pass it back through `--state`.  If either input branch later
ingests another scan or gains certificates, rerun `merge_e023b.py` to replace
the bundle.  Retain both source states: they contain the window evidence,
emissions, and replay material needed by a future E024; the compact bundle
does not.  The merger accepts current production E023b.1 states; the legacy
qualification pickles under the ignored `build/` directory are intentionally
not production inputs.

Each branch keeps its own E023b diagnostic view.  The certificate merger has
no raster/pilot pane because the two inputs do not share one sampling footing;
it reports the merged tile statistics and provenance in JSON.

Qualified combined-arm statistics:

| result | certified tiles |
|---|---:|
| decimated | 757 |
| native | 752 |
| shared | 740 |
| decimated only | 17 |
| native only | 12 |
| certificate union | **769** |

All 769 were ground-truth correct.  The two branches spent 2,226 CRC-bearing
calls and 119,790 BP iterations; their conservative aggregate false-accept
bound is `5.1828e-7`.  The bundle leaves 36 of 805 non-degenerate tiles
uncertified.  See [`MULTIVIEW-RECOVERY.md`](MULTIVIEW-RECOVERY.md) for the
overlap analysis and the measured fusion alternatives.

For the frozen qualification, the merger's summary fields are:

```text
merged=769 shared=740 exclusive=29 unresolved=36 crc_calls=2226 bp_iterations=119790 crc_bound=5.18281e-07
```

The proposed integrated successor is the design-only
[`E023c scale-space receiver`](../023c-scale-space-receiver/README.md).
It processes deterministic views inside one physical-capture transaction,
but retains separate payload/LDPC hypotheses because the measured early
fusions lost certificates.

## Score one receiver state

`score_e023b.py` evaluates one completed E023b state against the matching
emitted-sheet manifest. It excludes certified edge tiles that carry no
fountain symbol, computes actual fountain rank, and verifies recovered
length and SHA-256 when the volume closes.

```text
env/bin/python experiments/023b-integrated-receiver/score_e023b.py \
  experiments/023b-integrated-receiver/build/session.pkl \
  experiments/018b-payload-sheet/build/MANIFEST.json \
  --label scan-footing-name \
  --out experiments/023b-integrated-receiver/build/score.json
```

This command never changes the receiver state. An under-ranked volume is a
valid `OPEN` score and exits successfully. Add `--require-recovered` to make
an open result exit with status 4. To write recovered bytes only after
length/SHA verification:

```text
env/bin/python experiments/023b-integrated-receiver/score_e023b.py \
  experiments/023b-integrated-receiver/build/session.pkl \
  experiments/018b-payload-sheet/build/MANIFEST.json \
  --out experiments/023b-integrated-receiver/build/score.json \
  --recovered-out experiments/023b-integrated-receiver/build/payload.bin \
  --require-recovered
```

The current scorer accepts an authoritative E023b `.pkl`, not the terminal
multiview certificate-union JSON. Score native and decimated branches
separately; do not imply that their 769-tile certificate union has already
been passed through the fountain scorer. The full scorer contract is
[`SCORE.md`](SCORE.md).

## Run the pinned E018b take-1 harness

`018b-take-1.sh` is a committed, pinned first-take driver for the four
existing native E018b cases:

- C3 on the HP 1200-dpi scan;
- C3 on the Canon 4800-dpi scan;
- C2 on the HP 1200-dpi scan;
- C2 on the Canon 4800-dpi scan.

It creates four separate context+PAVA states, applies final adaptive BP,
keeps the live diagnostic on one sequentially reused port, and runs the
manifest scorer. It deliberately performs no decimation. The script expects
the exact ignored manifests and scan paths named inside it; it is not a
generic batch interface.

Inspect every command and prerequisite without running the receiver:

```text
DRY_RUN=1 \
  experiments/023b-integrated-receiver/018b-take-1.sh
```

Run the pinned take:

```text
experiments/023b-integrated-receiver/018b-take-1.sh
```

Optional environment:

```text
DIAG_PORT=8023 PANEL_WIDTH=600 \
OUTPUT_ROOT=scratch/e018b/take-1 \
  experiments/023b-integrated-receiver/018b-take-1.sh
```

Open `http://localhost:8023/` while it runs. Per-case states, diagnostics,
receiver reports, and `score.json` files land below `OUTPUT_ROOT`.

## Important state rules

- `--capture-groups` takes one comma-separated physical-capture ID per TIFF.
- Independent captures need distinct IDs.
- Derived files from one physical capture must share an ID; E023b refuses to
  count the second derivation independently.
- Native and decimated versions of one scan are the same physical capture.
  Use separate states and `merge_e023b.py`; never sum them as independent
  evidence.
- DPI, pages, format, detector profile, search configuration, and
  implementation are frozen per state.
- Refeeding an already committed TIFF SHA is an authoritative no-op.
- `--rate` and `--no-bch-first` are experimental overrides. Omit them for the
  qualified E018 setup.

`--diag [DIR]` is observer-only. `--diag-port N`, `--out FILE.png`, and
`--report FILE.json` control the viewer, final four-pane image, and JSON
report without changing receiver decisions.
