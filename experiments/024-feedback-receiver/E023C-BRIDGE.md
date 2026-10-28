# E023c lane bridge

`e023c_e024_bridge.py` is the v2 experiment adapter for measuring E024 after
a production E023c cascade. It is not a new receiver entry point and it never
combines correlated pixel evidence. The exact v1 source used for the frozen
2026-07-17 measurements is retained byte-for-byte as
`e023c_e024_bridge_v1.py`; v1 reports remain historical and are not rewritten
as v2 reports.

The bridge preserves the causal boundary in four steps:

1. `export` validates a current E023c cascade and writes each embedded,
   current-schema E023b lane as its own complete state.
2. The official E023b merger builds one conflict-checked certificate union.
   Each E024 run uses that certificate truth while replaying only its own
   lane's raster evidence.
3. Bound `audit` replays the manifest-referenced E023c cascade under its exact
   stored source closure, proves the declared cascade and ordered lane
   identities against that state, maps exactly one fixed-point E024 baseline
   and observer report to every lane, and proves every generation-zero key and
   bit equals the official union.
4. Only after every cascade, source closure, state, report, baseline,
   manifest, exported lane, and official-union identity has been replayed and
   rechecked does `audit` open frozen ground truth for post-hoc certificate
   checking.

## Export the embedded E023b lanes

Run from the repository root:

```text
env/bin/python \
  experiments/024-feedback-receiver/e023c_e024_bridge.py export \
  E023C-CASCADE.pkl \
  --out-dir BUILD/lanes
```

`BUILD/lanes/lanes.json` records the cascade identity, deterministic lane
order, full lane-state identities, certificate counts, and a `merge_source`
argument for every lane. Each v2 filename and label includes scale, lane kind,
and the complete E023c lane ID. Export rejects any generated label/path
collision and refuses to overwrite an existing state or manifest.

## Adopt exact lane files from a frozen v1 export

Do not re-export a historical lane merely to give it a v2 label: pickle
serialization can change its file SHA even when its authoritative state is
identical. To bind already completed E024 states to their exact historical
baseline bytes, create only a new v2 JSON manifest:

```text
env/bin/python \
  experiments/024-feedback-receiver/e023c_e024_bridge.py adopt-v1 \
  E023C-CASCADE.pkl \
  --legacy-manifest HISTORICAL-V1/lanes.json \
  --manifest-out HISTORICAL-V1/lanes-v2-adopted.json
```

`adopt-v1` accepts only v1 magic/version and the SHA-256 of the preserved
`e023c_e024_bridge_v1.py`. It authenticates and freezes the completed current
cascade, requires the legacy lane IDs to cover it bijectively, and replays
every exact legacy state through the current E023b loader. Each artifact's
manifest hash/size, cascade semantic digest, and receiver authoritative digest
must agree with the corresponding current cascade lane. Missing, duplicate,
changed, incompatible, or colliding lanes are fatal. All inputs are rechecked
before the v2 manifest is atomically created.

The cascade's stored numerical implementation must match the source closure
running `adopt-v1`. For a historical state that predates a later
observer-only source-fingerprint change, run the bridge from a clean source
snapshot matching the stored cascade; do not edit or bless the pickle's
fingerprints. The retained HP audits used the frozen `bdc9c54` numerical
closure plus the exact v2 bridge. Compatibility of later diagnostic commit
`5ee753a` is recorded separately and is not part of adoption.

The command writes no pickle and does not rename, copy, or rewrite a receiver
state. Its collision-safe v2 labels point to the original legacy paths. Build
a fresh official union from the adopted manifest's new `merge_source` values.
An old v1 union still carries the old labels and therefore cannot satisfy the
v2 bound-audit label proof.

## Build the generation-zero certificate portfolio

Pass every `merge_source` value from `lanes.json` to the production merger:

```text
env/bin/python \
  experiments/023b-integrated-receiver/merge_e023b.py \
  --source 'LANE-LABEL-0=/absolute/exported/lane-0.pkl' \
  --source 'LANE-LABEL-1=/absolute/exported/lane-1.pkl' \
  --out BUILD/lanes/portfolio.json
```

Use the exact labels and paths emitted for the actual scale plan. The merger
requires the same format, geometry, pages, rate, tile universe, and ordered
physical capture IDs across lanes. Any overlapping certificate disagreement
is fatal. It merges certificates only; LLRs, attempts, and raster evidence
remain lane-local.

## Run E024 independently for each lane

Use a distinct state, report, image, and diagnostic directory for every
exported lane. Give every run the same certificate portfolio:

```text
env/bin/python experiments/024-feedback-receiver/run_e024.py \
  --fresh \
  --from-e023b EXPORTED-LANE-PATH \
  --certificate-union BUILD/lanes/portfolio.json \
  --profile refine \
  --state BUILD/e024-coarse.pkl \
  --report BUILD/e024-coarse.json \
  --out BUILD/e024-coarse.png \
  --diag BUILD/e024-coarse-diag
```

Repeat for every lane to qualify the bound composition and measure the maximum
observed scale-space tail recovery. Running only the native lane is a cheaper
unbound observer experiment; it cannot produce `QUALIFIED_BOUND`. E024 still
operates at LDPC-and-below. Supplying a fountain manifest to the later audit
classifies certificates as useful or inert but does not introduce a fountain
stop condition.

## Audit the completed lane portfolio

```text
env/bin/python \
  experiments/024-feedback-receiver/e023c_e024_bridge.py audit \
  --run LANE-LABEL-0=BUILD/e024-lane-0.pkl \
  --report LANE-LABEL-0=BUILD/e024-lane-0.json \
  --run LANE-LABEL-1=BUILD/e024-lane-1.pkl \
  --report LANE-LABEL-1=BUILD/e024-lane-1.json \
  --export-manifest BUILD/lanes/lanes.json \
  --certificate-union BUILD/lanes/portfolio.json \
  --ground-truth PRINTED-FIELD.npy \
  --ground-truth-sha256 FROZEN-SHA256 \
  --manifest PRINTED-MANIFEST.json \
  --out BUILD/portfolio-audit.json
```

Use the exact lane labels emitted by `lanes.json`. Bound mode requires one and
only one run/report pair for every lane, and every E024 head must have reached
a fixed point. It first reloads and authenticates the exact cascade named by
the manifest under the matching stored E023c source closure. Cascade file,
authoritative, status, run-policy, format, page, capture, and certificate-union
identities must match; ordered lane IDs and all declared lane metadata,
semantic digests, and receiver authoritative digests must match bijectively.
It then replay-proves the official merger, binds every union source and E024
baseline to the export's exact file and authoritative identities, and requires
every generation-zero certificate set and bit vector to equal that union. Run
`audit` from the same clean source closure required by `export`/`adopt-v1`; a
later observer-only fingerprint change is not waived. A lowercase 64-hex
`--ground-truth-sha256` is mandatory in bound mode; an omitted or malformed
digest is rejected before any state replay. The audit then reports per-lane effects,
certificate conflicts and exclusivity, the global start/final union, wrong
certificates, optional useful/inert symbol counts, and work accounting. Use
`--baseline LABEL=PATH` only when an immutable E023b baseline was moved without
changing its bytes; the exact artifact identity must still match its lane.

## Retained HP bound evidence

The C3 and C2 HP-1200 portfolios were re-audited through this exact v2
contract after adopting the frozen v1 lane files without rewriting them.
Both reports have status `QUALIFIED_BOUND`, all gates pass, and every
certificate matches ground truth:

- C3: 754 → 754, no gain; audit SHA-256
  `2b70cdaabe5c60f4a2ffee75b77d4abe980a3e4bacd1880659f4a733694375a4`.
- C2: 1,438 → 1,439 via useful tile `(0,18,26)`; audit SHA-256
  `8f54ac717cf661bbb227f6e169b9f818357fa70b918ca89f05dd15d51e3511f2`.

The original v1 portfolio reports remain useful historical observer
evidence, but they are explicitly unbound and must not be cited as proof of
the E023c→E024 composition. Exact adopted-manifest, official-union, and audit
identities are retained in `HP-E018B-QUALIFICATION.json`.

## Explicit unbound observer mode

Omitting both `--export-manifest` and `--certificate-union` retains a useful
audit for standalone E024 states or ad-hoc portfolios. Reports are optional in
this mode. A successful output is deliberately labeled `OBSERVED_UNBOUND`, its
`binding.qualified` field is false, and it must not be cited as proof of an
E023c→E024 composition. Supplying only one binding argument is an error.

Exit status is `0` only when every applicable replay, conflict, preservation,
and ground-truth gate passes. In bound mode the output status is
`QUALIFIED_BOUND`; in unbound mode it is `OBSERVED_UNBOUND`. Status `3` means a
completed audit exposed a failed gate; `2` means malformed, unreadable, or
incompletely bound input.
