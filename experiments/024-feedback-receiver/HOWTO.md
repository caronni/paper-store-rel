# E024 how-to

E024 is a state-only feedback pass over a completed, current-schema E023b
state. It does not ingest TIFFs through E021/E022 itself and it does not do
fountain/RaptorQ accounting.

## Run the registered default combined profile

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh \
  --from-e023b \
    experiments/024-feedback-receiver/build/e018-e0216-dec-context.pkl \
  --profile combined \
  --state experiments/024-feedback-receiver/build/e018-e0216-dec-e024-combined.pkl \
  --report experiments/024-feedback-receiver/build/e018-e0216-dec-e024-combined.json \
  --out experiments/024-feedback-receiver/build/e018-e0216-dec-e024-combined.png \
  --diag experiments/024-feedback-receiver/build/e018-e0216-dec-e024-diag
```

`--diag` starts a local observer-only viewer and also writes numbered PNG
frames. Diagnostic failures disable the viewer but do not alter or stop the
receiver transaction.

Dense C2 overlays exposed a presentation-only rectangle-ordering failure at
`--panel-width 400`; the audited receiver state remained valid and a
600-pixel panel rendered successfully. Current code clamps overlay insets to
the scaled partial-edge dimensions and has a 400-pixel C2 regression, so
narrow panels are supported without changing receiver state.

The omitted-profile default remains the preregistered `combined` arm for
fingerprint stability. The measured recommendation is explicit
`--profile refine`; see “Measured winner” below.

The input E023b file is immutable generation zero. E024 binds it by complete
file hash, file size, authoritative digest, format, pages, rate, and ordered
captures. If the E023b receiver implementation has changed, regenerate the
E023b state rather than bypassing the check.

## Resume or prove the fixed point

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --state experiments/024-feedback-receiver/build/e018-e0216-dec-e024-combined.pkl \
  --report experiments/024-feedback-receiver/build/e018-e0216-dec-e024-combined.json \
  --out experiments/024-feedback-receiver/build/e018-e0216-dec-e024-combined.png \
  --diag experiments/024-feedback-receiver/build/e018-e0216-dec-e024-diag
```

On resume, the stored profile is used automatically. A state whose terminal
generation is already a fixed point is an exact no-op: no TIFF read, detector
fit, LDPC call, or state mutation occurs. The existing report, image, and
diagnostic frames are not rewritten; `--diag` is intentionally not started
for that no-op invocation.

Use `--from-e023b NEW/PATH.pkl` on resume only to relocate an unchanged
generation-zero artifact. The bytes and all semantic identities must still
match.

## Run the four factorial profiles

Use a separate state for each profile:

| profile | pose treatment | detector treatment |
|---|---|---|
| `control` | unchanged | unchanged; exact no-op |
| `recal` | unchanged | dense certified-label PAVA/context |
| `refine` | bounded certified-label pose | exact E023b detector replay |
| `combined` | bounded pose if admitted | dense recalibration, including a same-pose fallback |

Example:

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh \
  --from-e023b BASELINE.pkl \
  --profile recal \
  --state RECAL.pkl \
  --report RECAL.json \
  --out RECAL.png
```

Do not reuse one E024 state with another profile. The profile and numerical
configuration are part of the state fingerprint.

## Seed exact certificates from another footing

Build the current E021.6 multiview certificate bundle from the two exact
E023b source artifacts:

```text
env/bin/python \
  experiments/023b-integrated-receiver/merge_e023b.py \
  --source \
    decimated=experiments/024-feedback-receiver/build/e018-e0216-dec-context.pkl \
  --source \
    native=experiments/024-feedback-receiver/build/e018-e0216-native-context.pkl \
  --out \
    experiments/024-feedback-receiver/build/e018-e0216-multiview-certificates.json
```

The resulting E023b multiview merge bundle may seed generation zero:

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh \
  --from-e023b DECIMATED.pkl \
  --certificate-union MULTIVIEW-CERTIFICATES.json \
  --profile refine \
  --state DECIMATED-UNION-E024-REFINE.pkl \
  --report DECIMATED-UNION-E024-REFINE.json \
  --out DECIMATED-UNION-E024-REFINE.png
```

The bundle is certificate truth only. It is not extra pixel evidence and it
does not permit native and decimated rasterizations of one capture to be
summed. E024 validates compatibility and requires the selected E023b branch
to appear in the bundle provenance.

`--certificate-union` is accepted only with `--fresh`. E024 first replays the
fingerprinted E023b merger against every source artifact and requires a
type-strict, canonical-JSON match. It then embeds the complete union bytes
and SHA-256 as the durable trust root. Save/load invokes the same proof,
binds the selected baseline by file hash/size and authoritative digest, and
cross-checks external certificate bits and certifying-attempt provenance.
Successful source replay may be cached only within the current process for
the exact union/merger/receiver hash key.

Do not pass
`experiments/023c-scale-space-receiver/E023C-QUALIFICATION.json` here. It is
a qualification report from legacy E023b.0 footings, not a replayable
certificate-union bundle.

## Run E024 after a production E023c cascade

Production E023c states embed complete current-schema E023b sessions for
every scale lane. The retained experimental adapter exports those lanes and
audits independently persisted E024 overlays; it does not alter the cascade
or combine correlated-scale LLRs. The shorter normative adapter reference is
[`E023C-BRIDGE.md`](E023C-BRIDGE.md).

The current command is the hardened v2 adapter. The exact v1 implementation
used by the frozen 2026-07-17 audits is retained separately as
`e023c_e024_bridge_v1.py`; do not regenerate or relabel those historical v1
reports.

First export all lanes from the completed cascade:

```text
env/bin/python \
  experiments/024-feedback-receiver/e023c_e024_bridge.py export \
  E023C-SESSION.pkl \
  --out-dir E023C-E024/lanes
```

`lanes.json` records collision-safe filenames and ready-to-use `merge_source`
values. V2 labels and filenames include the full E023c lane identity.

For a historical v1 run, do not replace its immutable E023b baseline with a
new pickle serialization. Adopt the exact v1 files into a v2 manifest instead:

```text
env/bin/python \
  experiments/024-feedback-receiver/e023c_e024_bridge.py adopt-v1 \
  E023C-SESSION.pkl \
  --legacy-manifest E023C-E024/legacy-v1-lanes.json \
  --manifest-out E023C-E024/adopted-v2-lanes.json
```

This migration accepts only a manifest attributed to the byte-frozen v1
bridge, matches every lane bijectively to the authenticated current cascade by
lane ID and semantic identities, replays every exact file through the current
receiver loader, and rechecks all bytes before writing JSON. It never writes a
receiver state. Rebuild the official union from the adopted manifest so its
source labels equal the new v2 labels; do not reuse the v1-labeled union for a
bound v2 audit.

The stored numerical implementation must match the E023c source closure
running `export`, `adopt-v1`, and the later bound `audit`. For a historical
cascade after a later observer-only fingerprint change, use a clean source
snapshot matching the stored run; never edit the pickle or waive the check.
The retained HP
reaudits used the frozen `bdc9c54` numerical closure plus the exact v2 bridge,
with later `5ee753a` diagnostic compatibility proved separately.

For either an ordinary export or an adopted manifest, build the union by
copying the complete `merge_source` values:

```text
env/bin/python experiments/023b-integrated-receiver/merge_e023b.py \
  --source 'LANE-LABEL-0=/absolute/exported/lane-0.pkl' \
  --source 'LANE-LABEL-1=/absolute/exported/lane-1.pkl' \
  --source 'LANE-LABEL-2=/absolute/exported/lane-2.pkl' \
  --out E023C-E024/lanes/portfolio.json
```

Run a separate E024 state for every lane, always supplying the same exact
portfolio. The measured tail profile is `refine`:

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh \
  --from-e023b EXPORTED-LANE-PATH \
  --certificate-union E023C-E024/lanes/portfolio.json \
  --profile refine \
  --state E023C-E024/e024-native.pkl \
  --report E023C-E024/e024-native.json \
  --out E023C-E024/e024-native.png \
  --diag E023C-E024/diag-native \
  --panel-width 600
```

Repeat with distinct output paths for the 2-ppc and 3-ppc lanes. Then audit
all completed overlays together. Ground truth is a post-hoc correctness
input only; complete the blind states and reports before invoking `audit`:

```text
env/bin/python \
  experiments/024-feedback-receiver/e023c_e024_bridge.py audit \
  --run LANE-LABEL-0=E023C-E024/e024-lane-0.pkl \
  --report LANE-LABEL-0=E023C-E024/e024-lane-0.json \
  --run LANE-LABEL-1=E023C-E024/e024-lane-1.pkl \
  --report LANE-LABEL-1=E023C-E024/e024-lane-1.json \
  --run LANE-LABEL-2=E023C-E024/e024-lane-2.pkl \
  --report LANE-LABEL-2=E023C-E024/e024-lane-2.json \
  --export-manifest E023C-E024/lanes/lanes.json \
  --certificate-union E023C-E024/lanes/portfolio.json \
  --ground-truth PRINTED-GROUND-TRUTH.npy \
  --ground-truth-sha256 FROZEN-SHA256 \
  --manifest E018B-MANIFEST.json \
  --out E023C-E024/portfolio-audit.json
```

The labels on every `--run` and `--report` must be the exact labels from
`lanes.json`; the numbered names above are placeholders.
For C2, export and merge its two 2/4-ppc lanes and omit the third pair. Bound
mode requires exactly one run and observer report for every exported lane,
requires every E024 run to be at a fixed point, reloads and authenticates the
manifest-referenced cascade under its matching source closure, proves its
exact ordered lane metadata and semantic identities, replay-proves the
official union, binds every baseline to its exact export, and proves every
generation-zero key and bit equals the union before it can emit
`QUALIFIED_BOUND`. Bound mode also requires a lowercase, 64-hex
`--ground-truth-sha256`; omission or malformed input fails before replay.

Omit both `--export-manifest` and `--certificate-union` only for a standalone
or ad-hoc observer audit. Such a successful report is explicitly
`OBSERVED_UNBOUND`, has `binding.qualified=false`, and is not evidence for an
E023c→E024 composition. In either mode all non-truth inputs are replayed and
re-frozen before ground truth is opened.

This workflow is experimental measurement plumbing. It is not a single
production E023c→E024 command and it does not feed E024 changes back into
earlier E023c levels. The retained HP result is summarized in
`HP-E018B-QUALIFICATION.json`: C3 754→754 and C2 1,438→1,439 (+1 useful).

## Limit work for debugging

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh --from-e023b BASELINE.pkl \
  --profile combined --max-generations 1 \
  --state DEBUG.pkl --report DEBUG.json --out DEBUG.png
```

A generation limit is a debugging/measurement cap, not a decoding stop
condition. If the head is not a fixed point, invoke the state again to
continue.

## Blind numerical qualification

```text
env/bin/python experiments/024-feedback-receiver/qualify_e024.py \
  --baseline \
    decimated=experiments/024-feedback-receiver/build/e018-e0216-dec-context.pkl \
  --baseline \
    native=experiments/024-feedback-receiver/build/e018-e0216-native-context.pkl \
  --out experiments/024-feedback-receiver/QUALIFICATION.json
```

The harness runs all four profiles for every footing before opening E018
ground truth. It reports safety and execution gates separately from efficacy,
including wrong/lost/changed certificates, factorial effects, held-out
improvements, pose bounds, context adoption, dependency depth, changed cells,
BP/CRC work, source TIFF reads, and runtime. File-identity hashing is
additional I/O and is not counted as a source TIFF read.

Qualify the 770-certificate multiview seed separately so the primary report
is not overwritten:

```text
env/bin/python experiments/024-feedback-receiver/qualify_e024.py \
  --baseline \
    decimated=experiments/024-feedback-receiver/build/e018-e0216-dec-context.pkl \
  --baseline \
    native=experiments/024-feedback-receiver/build/e018-e0216-native-context.pkl \
  --certificate-union \
    experiments/024-feedback-receiver/build/e018-e0216-multiview-certificates.json \
  --out experiments/024-feedback-receiver/QUALIFICATION-UNION.json
```

The qualifier requires at least two distinct baseline paths, complete-file
identities, and authoritative state digests. With a union, every footing
must also match one exact proven union source before any profile begins.

## Focused regression suite

```text
env/bin/pytest -q \
  tests/test_e024_state.py \
  tests/test_e024_algorithm.py \
  tests/test_e024_qualification.py
```

Current result: **61 passed**.

## Measured winner

The maximum measured persistent state imports the trusted 770-certificate
union into the decimated E021.6 footing and runs pose-only `refine`:

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh \
  --from-e023b \
    experiments/024-feedback-receiver/build/e018-e0216-dec-context.pkl \
  --certificate-union \
    experiments/024-feedback-receiver/build/e018-e0216-multiview-certificates.json \
  --profile refine \
  --state \
    experiments/024-feedback-receiver/build/e018-e0216-dec-union-e024-refine.pkl \
  --report \
    experiments/024-feedback-receiver/build/e018-e0216-dec-union-e024-refine.json \
  --out \
    experiments/024-feedback-receiver/build/e018-e0216-dec-union-e024-refine.png \
  --diag \
    experiments/024-feedback-receiver/build/e018-e0216-dec-union-e024-refine-diag
```

Measured result:

- certificates: **770 → 772**;
- new tiles: `(0,7,18)` and `(0,7,22)`;
- generations: 2, ending at a validated no-new-certificate fixed point;
- accepted/refused revisions: 47 / 310;
- changed cells / owner changes / patches: 415,728 / 61,369 / 6;
- CRC calls / BP iterations / source TIFF reads: 45 / 7,983 / 12;
- runtime: 337.79 seconds on the qualification machine;
- wrong/lost/changed certificates: 0 / 0 / 0.

This state has the exact same certificate set and bits as merging the two
own-branch `refine` outputs, but needs only the decimated feedback pass after
the trusted union import. Without a union seed, the largest single-footing
result is native `refine`, 757 → 762.
