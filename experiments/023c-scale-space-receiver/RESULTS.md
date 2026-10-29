# E023c production cascade results

**Status: QUALIFIED_SINGLE_CAPTURE per format, 2026-07-17.**

The production coarse-to-fine receiver is numerically and architecturally
qualified on one HP 1200-dpi scan of the E018b C3 sheet, with an additional
checked single-capture result on the HP C2 sheet.  These are strong
format-specific results, not a cross-scanner generalization claim.

The checked machine record is
[`E023C-CASCADE-HP1200.json`](E023C-CASCADE-HP1200.json), SHA-256
`04f4b63ad2976b67c6fcd6b5b2e5ac1300b04c13df42eb1bad9f471f4c68cd92`.
Every gate in that report passes.  Commands and audit procedure are in
[`HOWTO.md`](HOWTO.md) and [`QUALIFICATION.md`](QUALIFICATION.md).

These numerical reports are frozen to run commit `bdc9c54`.  Later commit
`5ee753a` adds observer-only live progress instrumentation and changes three
full-source fingerprints; it is not a fresh blind run.  Exact-delta pins and
observer-on/off state-neutrality tests retain compatibility without claiming
that the frozen report was regenerated.  Any numerical delta requires a new
state and qualification.

## Qualified result

The automatic C3/1200 schedule is 2 → 3 → 6 scan pixels per printed cell,
equivalent to 400 → 600 → 1200 dpi views.  `--complete --bp-retry` was used,
so processing continued after the volume was already verified at 2 ppc.

| level | placements | lower hints | pose refinements adopted | globally solved candidates skipped | certified before retry | retry gain | marginal certificates | CRC calls | BP iterations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 ppc / 400 dpi | 184 | 0 | 0 | 0 | 650 | 21 | **671** | 866 | 44,942 |
| 3 ppc / 600 dpi | 143 | 186 | 50 | 671 | 73 | 1 | **74** | 195 | 26,150 |
| 6 ppc / 1200 dpi | 143 | 144 | 43 | 745 | 7 | 2 | **9** | 111 | 21,838 |
| **total** | — | — | — | **1,416** | — | **24** | **754** | **1,172** | **92,930** |

The finer lane counts are deliberately marginal.  A certificate committed at
a lower scale is final for the global objective, so the residual NeedMap keeps
the complete finer scan/evidence record but suppresses redundant LDPC/CRC
decoding of that tile.  The 671 + 74 + 9 partition is therefore the portfolio,
not three independently comparable full-page decoder totals.

All 754 certificates are ground-truth correct.  There are no cross-scale bit
conflicts.  The portfolio digests are:

```text
set  70ed14f8e9582535632ca8fc803dc5848d6e1238a24f44fc289b05995aa80324
bits 806b1c1aa91b494d98efe0327d2a70438e9517c6afc8fd83bea5402195628c25
```

The real fountain decoder received 731 useful symbols, reached rank 338/338,
reconstructed 88,157 bytes, and matched payload SHA-256
`012d9e3ae693c00e464637eeffa519329f081a42262dedbfc9e0e8e1e86acf28`.
Twenty-three certified edge tiles are fountain-inert.  The coarse 2-ppc level
alone already reached rank 338/338 and verified the payload; the remaining 83
certificates are the extra recovery obtained by `--complete`, not certificates
needed for this particular volume decode.

## Does the 3-ppc intermediate level earn its place?

Yes for recovery, with a measurable cost.

A same-code endpoint control used the same source, policies, manifest,
identical 671-certificate coarse anchor, and `--complete --bp-retry`, but an
explicit 2 → 6 ppc schedule.  It ends at 747 certificates.  The automatic
2 → 3 → 6 result is a strict superset:

| schedule | certificates | CRC calls | BP iterations | attempt records |
|---|---:|---:|---:|---:|
| 2 → 6 control | 747 | 1,056 | 69,613 | 1,171 |
| 2 → 3 → 6 automatic | **754** | 1,172 | 92,930 | 1,321 |
| delta | **+7** | +116 | +23,317 | +150 |

The seven additions, all correct and with no control-only loss, are:

```text
(0, 4, 20)  (0, 4, 22)
(0, 12, 8)  (0, 12, 9)  (0, 12, 10)
(0, 15, 7)  (0, 15, 9)
```

Thus the intermediate representation is not merely an earlier route to the
same certificates.  It adds seven successful local decoding trajectories for
about 11.0% more CRC calls, 33.5% more BP iterations, and 12.8% more attempt
records than the two-level residual control.  Whether that trade is desirable
depends on the objective:

- for maximum tile recovery, keep the automatic 2 → 3 → 6 schedule;
- for this volume's fastest verified recovery, omit `--complete` and stop at
  2 ppc;
- for a cheaper exhaustive pass, `--ppc-levels 2` gives the qualified 2 → 6
  control and loses exactly those seven tiles on this capture.

Wall-clock totals are not used for the causal cost comparison because the
automatic run rendered 38 diagnostic frames while the endpoint control ran
without live diagnostics.  The recorded level totals were 488.8 s and
317.2 s respectively; these mix algorithm work, image I/O, state writes, and
different observer overhead.

## What the residual NeedMap buys

The current two-level control has the exact same 747 certificate keys and
bits as the earlier two-level development run, but it no longer asks native
LDPC to re-prove the 671 coarse certificates.

| two-level implementation | certificates | CRC calls | BP iterations | attempt records |
|---|---:|---:|---:|---:|
| pre-NeedMap development state | 747 | 1,758 | 81,271 | 1,874 |
| current residual control | 747 | **1,056** | **69,613** | **1,171** |

That is the same outcome with 39.9% fewer CRC calls, 14.3% fewer BP
iterations, and 37.5% fewer attempt records.  The historical state is not a
current qualification input because its implementation fingerprint predates
the hardened state schema; this comparison is a controlled read-only audit of
its certificate and attempt ledgers.  The current endpoint control itself is
fully ground-truth and fountain qualified inside the checked production
report.

The NeedMap is intentionally conservative.  It does not crop E021/E022 or
skip current-pixel pose/sampling work: solved material may still anchor an
unresolved neighbour, and pilot/pose need differs from payload-tile need.
Its proven benefit is at the safe syndrome+CRC boundary.

## Comparison with historical native E023b

The historical native-only E023b state contains 730 correct certificates.
The production automatic portfolio contains every one of them, agrees on all
bits, and adds 24:

```text
historical native E023b     730
production E023c automatic 754
lost/conflicting              0
net gain                    +24
```

This comparison is useful but not a pure algorithm ablation: the production
cascade includes a coarse scale, the intermediate scale, lower placement
hints, bounded certificate-labelled pose refinement, and residual scheduling.
The endpoint control above is the cleaner measurement of the intermediate
scale itself.

## Geometry and feedback observations

The automatic run confirms several design choices without proving a universal
mechanism:

- The coarse view accepts 184 placements, versus 143 at both finer levels.
  Its regularized geometry remains the dominant acquisition route.
- Only one placement at each finer level is accepted directly through the
  lower-chain route; most accepted placements still use same-level neighbour
  chaining.  Lower information is nevertheless important as a bounded route
  and as the certificate field for pose refinement.
- Certificate-labelled pose refinement is frequently eligible: 50/142
  windows are adopted at 3 ppc and 43/142 at native.  The current qualifier
  does not isolate its causal certificate gain; a dedicated
  `--no-forward-refine` arm would be needed for that claim.
- BP retry remains useful but small after the coarse level: +21 coarse, +1 at
  3 ppc, and +2 native.  Running it at each changed residual frontier is cheap
  in CRC exposures once solved keys are removed.

The seven intermediate-scale additions occur in three local row bands.  That
is consistent with the earlier observation that raster scale changes local
pose/phase/aperture and nonlinear BP trajectories rather than adding new
physical information.  One capture cannot distinguish scanner batch/reseek
structure from local paper/print damage or estimator non-invariance.

## Qualification evidence

The checked report requires all of the following simultaneously:

- exact qualified-run implementation and run-policy fingerprints;
- one exhaustively completed physical capture and all three scale barriers;
- authenticated state, lane, attempt, dependency, and certificate invariants;
- every lane and portfolio certificate correct against frozen printed truth;
- real fountain reconstruction, length, and SHA verification;
- the automatic schedule strictly supersets the current 2 → 6 control;
- the portfolio strictly supersets and agrees with the historical native
  E023b baseline;
- a final `session_complete` diagnostic sidecar whose pages, counts, level
  state, and authoritative digest match the committed session.

The production state authoritative digest is
`46194a2861819f56b2423c7240c7b5ee86fa37f8c4a53cdf9e26bf17bc0b541b`.
The checked state file SHA-256 is
`02e32656d31a236be8dd65b96232aba8c219156dc2bc22c79f8e1b9a211f8faf`.

## Scope and disposition

The clean architecture is promoted for continued experimentation.  The
automatic ladder is justified when maximum certificate recovery is the goal,
and the residual NeedMap is justified independently by exact-output cost
reduction.

The two qualified HP results do not yet establish:

- behavior at 600-dpi native, an exhaustive/full-page Canon-4800 yield, or a
  qualified multi-capture schedule; the later HP two-capture reference and
  Canon C2 confetti recovery are real but separately scoped observations;
- generalization of the seven-tile intermediate gain;
- the isolated contribution of lower hints versus certificate pose refine;
- an optimal automatic schedule for every scan/format;
- a fixed-point feedback strategy.

Those are bounded follow-ups.  They do not require changing the core evidence
rule: correlated scales remain alternative lanes, and only syndrome+CRC
certificates cross between them.

## Additional HP C2/1200 result

The production entry point was also run exhaustively on the HP C2 sheet with
the automatic 2 → 4 ppc schedule, `ctx-pava-v1`, and `--bp-retry`.  Its
checked report is
[`E023C-CASCADE-HP1200-C2.json`](E023C-CASCADE-HP1200-C2.json); the
pre-retention audit bytes had SHA-256
`1be5d720da62e8b1352f43873597855a99343f86a34f5b6cff123481b68405a9`.
That audit had a presentation-only C3 label in its `scope` field. The
profile-aware requalification corrects it to C2 while preserving the exact
state/numerical result; the checked report SHA-256 is
`574f44c141e70c1fe7a806a9e20dfa4650e592242e6a98adc1b3197257474d6d`.

| level | placements | pose refinements adopted | certified before retry | retry gain | marginal certificates | CRC calls | BP iterations | attempt records |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 ppc / 600 dpi | 391 | 0 | 1,299 | 11 | **1,310** | 2,221 | 200,535 | 2,272 |
| 4 ppc / 1200 dpi | 294 | 84 | 126 | 2 | **128** | 892 | 161,821 | 893 |
| **total** | — | **84** | — | **13** | **1,438** | **3,113** | **362,356** | **3,165** |

The 1,310 + 128 counts are ordered marginal contributions after the residual
NeedMap, not independently decoded full-page totals.  Every one of the 1,438
certificates matches frozen printed truth, the scale union is conflict-free,
and 1,363 are useful fountain symbols while 75 are inert edge addresses.
The real fountain decoder reaches rank 737/737, reconstructs 192,160 bytes,
and matches payload SHA-256
`424e41a2825727bcb107b2c6574b2864e34c3846925754bbba6536d248a15b32`.

All applicable production-qualification gates pass: qualified-run implementation
and policy fingerprints, authenticated/exhaustive state, all scale lanes,
certificate and portfolio ground truth, no scale conflict, historical
baseline retention/improvement, real payload verification, state hash, and
diagnostic evidence.  The C2 result is one HP capture and does not prove that
2 → 4 is globally optimal or generalize to another scanner or print.

## Observed HP C2/1200 two-capture maximum-recovery run

**Status: `OBSERVED_EXHAUSTIVE_MULTI_CAPTURE`, 2026-07-17.**  This is a
retained, truth-audited reference run, not `QUALIFIED_SINGLE_CAPTURE` and
not yet a new multi-capture qualification point.  The compact raw receiver
report is
[`E023C-C2-HP1200-TWO-CAPTURE-RUN.json`](E023C-C2-HP1200-TWO-CAPTURE-RUN.json),
SHA-256
`426b7ed02257bafe5f4627a524950988a2e448875ff713995502f4f8c158fe16`.
The exact command and the deliberately non-qualifying audit probe are in
[`HOWTO.md`](HOWTO.md).

The offset rescan was admitted first and the original scan second.  Both are
1200-dpi scans of the same HP-printed C2 sheet on the same HP scanner.  The
automatic 2 → 4 ppc ladder, `ctx-pava-v1`, `--complete`, and per-frontier
`--bp-retry` were used:

| capture / level | placements | lower hints | refinements adopted | attempts | retry gain | marginal certificates | cumulative | recorded time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| offset, 2 ppc / 600 dpi | 406 | 0 | 0 | 2,199 | 34 | **1,346** | 1,346 | 854.9 s |
| offset, 4 ppc / 1200 dpi | 354 | 408 | 80 | 824 | 2 | **123** | 1,469 | 450.4 s |
| original, 2 ppc / 600 dpi | 391 | 0 | 138 | 412 | 1 | **331** | 1,800 | 896.0 s |
| original, 4 ppc / 1200 dpi | 294 | 393 | 82 | 29 | 0 | **15** | **1,815** | 391.6 s |

These are ordered marginal contributions.  Once an earlier capture/level
barrier certifies a tile, the residual NeedMap suppresses redundant later
LDPC work; reversing the capture order would therefore repartition the
counts even if the final union were unchanged.  Likewise, the coarse/fine
certificate sets are disjoint by construction and do not imply independent
physical evidence.
Only certificates cross scale-lane boundaries.  Independent physical
captures within one level may combine through E023b's union path; correlated
scale LLRs are never summed.

The final result is 1,815/1,819 nondegenerate LDPC tiles (99.7801%), of which
1,730/1,734 are useful fountain symbols and 85 are inert edge addresses.
All 2,035 pilot tiles are known: 1,653 were BCH-solved and 382 were
placement-addressed, with zero unseen or conflicted pilots.  The four
remaining nondegenerate tiles are:

```text
(page 0, row 11, col 3)   ESI 377
(page 0, row 11, col 16)  ESI 390
(page 0, row 18, col 8)   ESI 620
(page 0, row 18, col 9)   ESI 621
```

`(0,51,34)` is the format's sole zero-capacity degenerate tile.  The real
fountain decoder reaches rank 737/737, reconstructs 192,160 bytes, and
matches payload SHA-256
`424e41a2825727bcb107b2c6574b2864e34c3846925754bbba6536d248a15b32`.
That volume was already verified after the offset capture's 2-ppc level;
`--complete` intentionally measures the remaining recovery frontier.
Across all four capture/level barriers the receiver records 3,464 attempts,
3,370 CRC calls, 336,346 BP iterations, and 774 retry calls.  Retry directly
contributes 37 certificates.

A read-only application of the existing production qualifier finds all
1,815 certificates correct against frozen printed truth, no cross-scale bit
conflict, exhaustive capture/level state, a state-consistent final diagnostic
frame, and a source-matched E023b baseline that is an exact 1,807-certificate
subset.  E023c adds these eight correct tiles with no loss:

```text
(0,11,2)  (0,11,4)  (0,11,5)  (0,11,6)
(0,18,6)  (0,18,7)  (0,18,20) (0,18,27)
```

The probe intentionally exits 3: the current qualifier's contract requires
exactly one physical capture, and its completed-level gate is consequently
single-capture-scoped.  Every core certificate, truth, provenance, state,
diagnostic, baseline, fountain, and SHA gate passes.  A multi-capture reader
must ignore the probe's single-capture `scope` label and
first-matching-capture feedback summaries.  A proper multi-capture
qualification must aggregate per-capture feedback correctly and specify the
schedule-control semantics; this result must not be relabelled by weakening
the existing frozen qualifier.

Frozen identities for replay are:

```text
source, offset       cd07d91e4db17ca7fd21eee2d4af8ce199112a7f8f9908f83f9917c2fdd0bd81
source, original     51b2841d044d939b2355c4d9069141ba5ced709a76986a492f0b2b4d514b2798
state file           21f599c4cdec8e1edf73feaa012bc8f198bca76533991661bf984f438f2b583e
authoritative state  76ebdb11566bf77d39741ec9a8b1d88df19a099d8595f92235af6c46d0a99c57
report identity set  64a0890da08cf3a4f3eaae7c0f2c12abfbf1e2b819fb06604db80bbc39d7c814
audited key set      c3d03724dde66417e74cfd10c8a282148cbbf7a3333a20f9bd38a9a31b76883a
audited bits         dfb352ec232d260584cc923594eb021eabc69acaecc5d75838bcc80f22901f0b
```

The 2.1-GB authoritative pickle remains a scratch artifact rather than a Git
object; the compact report and hashes retain its reproducible identity.  The
43m12.9s sum of recorded level times includes live diagnostics, state I/O,
and image work and is not a benchmark.  This experiment demonstrates strong
scan-pose complementarity on one print/scanner pair, not cross-print or
cross-scanner generalization.

## E024 after the production cascade

The retained experimental bridge exports the complete E023b sessions from
each cascade lane, builds their exact certificate union with the official
E023b merger, and runs an independent union-seeded E024 `refine` state per
lane.  The v2 bound audit maps every adopted export and official-union source
to exactly one E024 baseline/report, replay-loads and freezes every non-truth
input, preserves every generation-zero certificate and value, rejects any
bit conflict, and only then opens the hashed printed ground truth.

| format | E023c LDPC/useful | after E024 LDPC/useful | aggregate E024 work |
|---|---:|---:|---|
| C3 | 754 / 731 | 754 / 731 | 24 accepted revisions; 250,806 changed cells; 58 CRC; 12,180 BP iterations |
| C2 | 1,438 / 1,363 | 1,439 / 1,364 | 102 accepted revisions; 1,696,545 changed cells; 461 CRC; 96,682 BP iterations |

C3 has no gain.  C2 gains the one useful, ground-truth-correct tile
`(0,18,26)`.  Neither portfolio loses or changes a certificate and both are
conflict-free.  The `QUALIFIED_BOUND` portfolio-audit SHA-256 values are
`2b70cdaabe5c60f4a2ffee75b77d4abe980a3e4bacd1880659f4a733694375a4`
(C3) and
`8f54ac717cf661bbb227f6e169b9f818357fa70b918ca89f05dd15d51e3511f2`
(C2).

The earlier `cad2dded...7a8c9` and `02c4994d...58f1` v1 reports are retained
as historical unbound observer evidence, not as proof of the composition.

This is not an integrated production feedback loop: the adapter does not
mutate E023c, combine correlated-scale LLRs, or feed E024 revisions back into
earlier acquisition.  It establishes that broad affine feedback has sharply
diminishing yield after scale-space recovery on both HP sheets.  The more
distinct next hypothesis is bounded seam-aware piecewise pose plus explicit
support revision.

## Canon 4800-dpi C2 confetti recovery

On 2026-07-17, an intentionally unfinished multi-capture session over cut and
repositioned pieces of the E018b C2 sheet reached 809 conflict-free LDPC
certificates.  The receiver had been started without a manifest and capture
`c` still had its 8- and 16-ppc levels pending, so neither the unfinished
state nor certificate count alone constituted a recovery claim.

The read-only `score_e023c.py` audit attached the matching frozen E018b C2
manifest after acquisition.  Of 809 certificates, 784 carry fountain symbols
and 25 are inert boundary addresses.  The real fountain decoder reached rank
737/737 with shortfall zero, reconstructed 192,160 bytes, and verified SHA-256
`424e41a2825727bcb107b2c6574b2864e34c3846925754bbba6536d248a15b32`.
The result is therefore `RECOVERED + SHA PASS`; no remaining capture or scale
work is required for payload recovery.

This is valuable end-to-end evidence for displaced-confetti acquisition on
one HP-print/Canon-scan C2 specimen.  It is not a complete receiver-yield
measurement, because processing stopped as soon as the external audit proved
the volume, and it is not cross-print or cross-scanner generalization.

## Historical E023c factorial

`E023C-QUALIFICATION.json`, `SERIAL-PARALLEL.json`, and
`qualify_e023c.py` describe the earlier NN/DD/ND/DN geometry/sampler
factorial.  That experiment remains useful causal history (772 certificates
from four full lanes on six paired captures), but it is not the production
cascade, its state schema, or its current qualification anchor.

## Addendum 2026-10-09 — capture hash

`scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-b-3rd.tiff` (2,291,818,718 B, mtime 2026-07-17 20:14), sha256
from the raw-hash pass of 2026-10-09 (sha256 over the retained evidence): `d23adc17cd998e74fc36c84289e56defd0697904bb44b96022fc956ead8dd00c`.
