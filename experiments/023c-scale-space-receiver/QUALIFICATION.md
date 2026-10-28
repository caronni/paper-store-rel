# E023c production qualification

The production cascade is qualified with `qualify_e023c_cascade.py` against
an already completed `run_e023c.py` state. The qualifier is a read-only
observer: it does not ingest scans, retry decoding, alter certificates, or
feed ground truth back into the receiver.

The checked 2026-07-17 C3 qualification is
`E023C-CASCADE-HP1200.json`.  It is pinned to the qualified numerical
implementation at run commit `bdc9c54`,
run policy, state, manifest, frozen ground truth, diagnostic commit, and a
matched same-code endpoint control.  Its SHA-256 is
`04f4b63ad2976b67c6fcd6b5b2e5ac1300b04c13df42eb1bad9f471f4c68cd92`.
The additional checked C2 report is `E023C-CASCADE-HP1200-C2.json`; it uses
the same qualifier and safety boundary, with a matching native E023b
baseline but no endpoint-schedule control.

Commit `5ee753a` landed afterward and adds live diagnostic callbacks plus
observer-time exclusion.  It is not a fresh blind numerical
requalification: the frozen C3/C2 reports retain their original source
fingerprints.  The qualification tests pin the exact three-key source delta
(`e023c:cascade`, `e023c:run`, and `lower:paperholo.pilotsearch`), while the
E022/E023c callback tests prove observer-on/off timing and authoritative-state
neutrality.  Any different or additional fingerprint delta fails.  A future
numerical change still requires a fresh blind state and report.

## Build the qualification state

Use one physical capture, at least two scale levels, the registered manifest,
`--complete`, and diagnostics. Add `--bp-retry` when qualifying the
maximum-recovery profile:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scratch/e018b/hp-e018b-c3-hp-1200-page.tiff.png \
  --capture-groups e023c-qualified-hp-c3-1200 \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --manifest \
    experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_manifest.json \
  --detector-profile ctx-pava-v1 \
  --complete \
  --bp-retry \
  --state scratch/e023c-cascade-qualified/hp-c3-1200/session.pkl \
  --out scratch/e023c-cascade-qualified/hp-c3-1200/final.png \
  --report scratch/e023c-cascade-qualified/hp-c3-1200/report.json \
  --cache-dir scratch/e023c-cascade-qualified/hp-c3-1200/views \
  --diag scratch/e023c-cascade-qualified/hp-c3-1200/diag \
  --diag-port 0 \
  --panel-width 300 \
  --fresh
```

Keep the completed state, manifest, diagnostic directory, and exact
ground-truth array together as qualification inputs. The run must finish
exhaustively; an early-stopped state is not sufficient.  Use a new, empty
diagnostic directory for the qualification run: `--fresh` resets receiver
state, but it does not clear old diagnostic frames.

For the schedule ablation, build a second state with the same command and
policies, changing only the state/report/output paths, capture-group label,
and adding `--ppc-levels 2` (which produces the 2 → 6 endpoint schedule).
The checked control was run without `--diag`; if control diagnostics are
desired, give them a separate new, empty directory rather than sharing the
automatic run's path.

## Run the blind-state audit

First compute and retain the SHA-256 of the ground-truth `.npy` file:

```sh
shasum -a 256 \
  experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_gt/K__e018b_c3_012d9e3ae693_field.npy
```

Then run:

```sh
env/bin/python \
  experiments/023c-scale-space-receiver/qualify_e023c_cascade.py \
  scratch/e023c-cascade-qualified/hp-c3-1200/session.pkl \
  experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_manifest.json \
  --ground-truth \
    experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_gt/K__e018b_c3_012d9e3ae693_field.npy \
  --ground-truth-sha256 \
    6014881ce5001253804cc11423c8db19b84ff324a8cdd5b33a288830e01d3acc \
  --diag scratch/e023c-cascade-qualified/hp-c3-1200/diag \
  --baseline scratch/e018b/take-1/c3-hp-1200/session.pkl \
  --control-state \
    scratch/e023c-cascade-qualified/hp-c3-1200-two-level/session.pkl \
  --label hp-c3-1200-auto-2-3-6 \
  --out experiments/023c-scale-space-receiver/E023C-CASCADE-HP1200.json
```

`--baseline` and `--control-state` are optional audit comparators, never
inputs to E023c recovery.  The control must use the same physical source and
policy and share the automatic schedule's endpoints.  `--diag` is also
optional, but supply it when the diagnostic path itself is part of the
qualification claim. The command returns zero only when every applicable
gate passes; a completed audit with a failed gate returns 3.

## Qualification gates

The current production qualifier requires and records:

- a structurally valid, exhaustively completed persistent state;
- exactly one physical capture and at least two completed scale levels;
- the state file SHA-256 and authoritative semantic digest;
- exact agreement between the state's pinned implementation fingerprints and
  the current production implementation, including a registered run policy;
- the exact manifest file identity registered by the receiver state, plus an
  exact format, seed, geometry, encoding, and LDPC-rate match;
- every certified payload in every scale lane correct against frozen ground
  truth;
- every certificate in the conflict-checked portfolio correct against ground
  truth;
- no conflicting bits between the first and native scale lanes;
- at least one portfolio certificate contributed beyond the native lane;
- successful real fountain recovery with expected payload length and SHA-256;
- when `--diag` is supplied, a final `session_complete` sidecar, all expected
  page PNGs, and final metadata matching the committed certificate count,
  attempts, level count, pages, and authoritative digest.

With `--baseline`, five additional gates require the baseline to use the same
physical source and DPI, its certificates to be ground-truth-correct, the
E023c portfolio to lose none of them, the common certificates to agree
bit-for-bit, and E023c to improve strictly on that historical baseline.

With `--control-state`, additional gates require the control to be current,
exhaustive, ground-truth-correct, source/policy matched, endpoint matched, and
coarse-anchor identical.  The automatic portfolio must be a conflict-free
strict superset.  Decoder costs for both states are recorded alongside the
exclusive certificate sets.

The report includes per-lane placement methods, decoder effort, retry gain,
feedback adoption, certificate set and bit digests, first-versus-native set
differences, the portfolio audit, completion details, diagnostic evidence,
and every gate result. The intended success status is
`QUALIFIED_SINGLE_CAPTURE`.

This is deliberately a single-capture architectural and numerical
qualification. The production runner supports multiple captures, but this
qualifier does not claim cross-scanner or cross-print generalization.

## Checked outcome

The current automatic 2 → 3 → 6 ppc result has marginal certificate counts
671 + 74 + 9 = **754**.  All certificates are correct, the union is
conflict-free, and the reconstructed 88,157-byte payload matches SHA-256
`012d9e3ae693c00e464637eeffa519329f081a42262dedbfc9e0e8e1e86acf28`.
The matched 2 → 6 control has 747 correct certificates and is an exact
subset; the seven intermediate-scale additions are all correct.  The
historical native E023b baseline has 730 correct certificates and is also an
exact subset, leaving a net E023c gain of 24.

The automatic run spends 1,172 CRC calls, 92,930 BP iterations, and 1,321
attempt records.  The endpoint control spends 1,056, 69,613, and 1,171
respectively.  The diagnostic audit observes 38 frames and a final
`session_complete` record matching the authenticated state.  Full hashes,
per-level counts, exclusive keys, and limitations are frozen in the machine
report and summarized in `RESULTS.md`.

## Additional checked HP C2 outcome

The C2 capture uses the HP scan, C2 manifest/ground truth, automatic 2 → 4
ppc schedule, `--complete`, and `--bp-retry`.  Its state is exhaustively
complete and its diagnostic directory ends with a 25-frame
`session_complete` commit.  The report path is
`experiments/023c-scale-space-receiver/E023C-CASCADE-HP1200-C2.json`; the
pre-retention audit bytes had SHA-256
`1be5d720da62e8b1352f43873597855a99343f86a34f5b6cff123481b68405a9`.
That original audit carried an observer-only C3 label in `scope`; the
profile-aware qualifier corrects it to C2 without changing the authenticated
state, numerical results, or gates. The checked report SHA-256 is
`574f44c141e70c1fe7a806a9e20dfa4650e592242e6a98adc1b3197257474d6d`.

The automatic marginal certificate contributions are 1,310 at 2 ppc and
128 at 4 ppc, for **1,438** total.  All lane and portfolio certificates are
ground-truth correct and conflict-free.  The run spends 3,113 CRC calls,
362,356 BP iterations, and 3,165 attempt records.  Of the final
certificates, 1,363 are fountain-useful and 75 are inert edge addresses.  The
real fountain decoder reaches rank 737/737, reconstructs 192,160 bytes, and
matches payload SHA-256
`424e41a2825727bcb107b2c6574b2864e34c3846925754bbba6536d248a15b32`.

The qualifier additionally checks the current standalone native E023b
baseline: all 1,416 baseline certificates are correct, are retained
bit-for-bit by the E023c portfolio, and the portfolio adds 22 correct
certificates.  No endpoint-schedule causal claim is made for C2 because no
matched explicit-ladder control was supplied.

Every applicable gate passes: authenticated and exhaustive state; current
implementation/run policy; exactly one physical capture and both completed
levels; manifest/format identity; every lane and union certificate against
frozen truth; no cross-scale conflict; a contribution beyond the native lane;
historical-baseline source/correctness/retention/strict-improvement; real
payload length and SHA; diagnostic/state agreement; and recorded state file
identity.  This is a second single-capture format qualification, not
cross-scanner, cross-print, or schedule-optimal generalization.

## Reproducibility and code changes

Receiver state pins the transitive implementation and numerical run policy.
If production code or a pinned policy changes after a state was made, the
`current_implementation_matches_state` gate fails. Build a fresh state; do
not bless an old result by editing its report. Likewise, changing or replacing
the manifest fails its identity gate even when the replacement looks
semantically similar.

The ground-truth audit occurs only after the blind receiver state exists. The
qualifier reads certificates and compares them; it never opens a new decode
route. Preserve both the state file hash and its timing-independent
authoritative digest in any published result.

For a focused implementation check before an expensive capture run:

```sh
env/bin/pytest -q \
  tests/test_e023c_scale_space.py \
  tests/test_e023c_cascade.py \
  tests/test_e023c_state.py \
  tests/test_e023c_completion.py \
  tests/test_e023c_diag.py \
  tests/test_e023c_qualification_report.py
```

Unit tests establish invariants and failure behavior; they are not a
replacement for the real-scan qualification above.

## Historical factorial is not production qualification

`qualify_e023c.py`, `E023C-QUALIFICATION.json`, and
`SERIAL-PARALLEL.json` belong to the earlier frozen four-lane NN/DD/ND/DN
factorial. They remain useful historical evidence about geometry/sampler
complementarity, but they do not exercise the production cascade entry point,
persistent resume, automatic scale schedule, completion oracle, or current
diagnostics. Do not use that legacy command or report to qualify
`run_e023c.py`.

`E023C-CASCADE-HP1200.json` must likewise be regenerated whenever its pinned
state or numerical implementation changes.  The checked report passed every
gate against its frozen run.  The later, exact observer-only delta is retained
as separately tested compatibility evidence, not silently rewritten into the
report.  Any other fingerprint mismatch invalidates compatibility until a
fresh blind run and audit pass again.
