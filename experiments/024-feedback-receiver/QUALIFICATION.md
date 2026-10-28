# E024 qualification

**Status: own-branch and union-seeded factorials passed, 2026-07-16.**

## Registered experiment

The primary qualification is the blind 2×2 factorial:

| profile | recalibration | pose refinement |
|---|---:|---:|
| control | off | off |
| recal | on | off |
| refine | off | on |
| combined | on | on |

Within each footing, all four profiles start from the same byte-identical,
current-schema E023b generation-zero artifact. The decimated and native
footings are deliberately distinct artifacts of the same printed volume.
All blind outputs are reduced to certificates and ordinary accounting before
the frozen E018 printed ground truth is opened.

Safety/execution qualification requires:

- the E023b starting certificates are correct;
- control is an exact no-op;
- certificates are monotone and never change value;
- every final certificate matches ground truth;
- every profile reaches a validated terminal feedback fixed point;
- no candidate/source-integrity failure is downgraded to an ordinary refusal;
- pose arms actually read their source TIFFs when eligible work exists;
- accepted revisions use the comparable fixed-pilot owner score;
- pose changes remain inside the registered angle/phase box;
- pose changes pass E022's hard mismatch rule on the authoritative-core pilot
  population against the immutable generation-zero threshold, while the
  admitted discrete page/address/orientation/BCH/rival hypothesis remains
  frozen.

Efficacy is reported separately. An arm can be safe but inoperative, or safe
and operative without producing an additional certificate.

## Unit and synthetic qualification

The focused suite currently covers:

- exact control import and no-op replay;
- overlay save/load and generation-zero relocation;
- complete-file baseline tamper rejection;
- exact certificate-to-printed-cell regeneration;
- dependency-index, direct target, and transitive cycle rejection;
- atomic save failure;
- optional certificate-union import;
- durable embedded-union reproof, exact source-footing binding, forged
  external-certificate rejection, and type-strict malformed-JSON rejection;
- weighted PAVA and ordered-context recalibration;
- exact generation-zero detector score/logit/payload replay;
- bounded subcell pose recovery and fatal raw-mean replay mismatch;
- target-specific predecessor fallback and per-capture supersession;
- true combined-arm same-pose recalibration;
- exact dense base-clip-before-context replay and comparable pilot owner rank;
- evidence-addressed attempt deduplication, one-component scan60→retry150
  lineage, and generation barriers;
- exact sequential replay of candidate discovery, accepted/refused revisions,
  patches, decode scheduling, certificates, fixed-point decision, and final
  authoritative digest;
- incomplete candidate-frontier and false fixed-point rejection;
- fatal candidate-construction exceptions;
- distinct-footing and union-source qualification prebinding;
- persisted terminal fixed-point memoization;
- fatal source content/metadata replay failures in pose profiles;
- observer-only diagnostic materialization.

Command:

```text
env/bin/pytest -q \
  tests/test_e024_state.py \
  tests/test_e024_algorithm.py \
  tests/test_e024_qualification.py
```

Current result: **61 passed**.

The broader E021–E024 regression surface has 170 non-diagnostic passes. Four
local HTTP diagnostic tests require localhost socket permission in the
desktop sandbox and pass when run with that permission.

## Real-sheet results

The registered own-branch factorial uses:

| footing | bytes | file SHA-256 | authoritative SHA-256 | certificates |
|---|---:|---|---|---:|
| decimated E021.6 | 650,336,693 | `c22f888d073c8218d8320ed0bd79080818303316d1cf7dbf265f26a12c1e7108` | `bb3e78f28e12e714a7b443d70a60c6e537046c21b0224d977050f95ef1d48670` | 757 |
| native E021.6 | 1,244,140,085 | `744dbf337a899cd515f6f16e483b954bc9812f52f99c6635abd320872fd5bd00` | `4845832ada7ce3e0ab4819e9239c852ecc69c8d08c146ac2b960b89489588446` | 757 |

The optional current E021.6 certificate seed is
`build/e018-e0216-multiview-certificates.json`, 1,929,805 bytes, SHA-256
`2b295edbbf00cd95e9e8c38a9c978f7250c848a77c4c40c8f3f52734e2af5289`.
It contains 770 correct certificates: 744 shared and 13 exclusive to each
footing.

### Own-branch factorial

The blind own-branch matrix passed every safety and execution gate:

- every final certificate matches ground truth;
- no generation-zero certificate was lost or changed;
- every arm reached its validated local feedback fixed point;
- every arm passed the durable-boundary exact sequential replay validator;
- all pose revisions stayed in bounds and passed the inherited E022 hard
  mismatch gate;
- every candidate/source-integrity failure remained fatal.

| footing/profile | certificates | exact feedback gains | accepted/refused revisions | changed cells | CRC calls / BP iterations / TIFF reads | runtime |
|---|---:|---|---:|---:|---:|---:|
| decimated control | 757 → 757 | — | 0 / 0 | 0 | 0 / 0 / 0 | 70.52 s |
| decimated recal | 757 → 758 | `(0,18,18)` | 14 / 444 | 143,303 | 39 / 6,796 / 0 | 211.01 s |
| decimated refine | 757 → 759 | `(0,7,18)`, `(0,7,22)` | 57 / 399 | 572,230 | 83 / 14,703 / 12 | 373.51 s |
| decimated combined | 757 → 759 | `(0,7,18)`, `(0,7,22)` | 67 / 389 | 679,237 | 88 / 15,303 / 12 | 437.21 s |
| native control | 757 → 757 | — | 0 / 0 | 0 | 0 / 0 / 0 | 73.20 s |
| native recal | 757 → 757 | — | 10 / 205 | 127,836 | 32 / 5,820 / 0 | 151.44 s |
| native refine | 757 → 762 | `(0,1,14)`, `(0,1,18)`, `(0,12,0)`, `(0,21,15)`, `(0,23,7)` | 68 / 331 | 657,585 | 92 / 16,023 / 12 | 724.78 s |
| native combined | 757 → 761 | `(0,1,14)`, `(0,1,18)`, `(0,12,0)`, `(0,23,7)` | 76 / 325 | 738,300 | 94 / 16,602 / 12 | 778.18 s |

All eight arms have wrong/lost/changed certificate counts of `0/0/0`.
Each operative arm committed its recoveries in generation 1 and recorded a
terminal no-new-certificate fixed point in generation 2; native `recal`
reached that fixed point in generation 1.

The factorial interaction is `-1` on both footings. Decimated recalibration
alone recovers `(0,18,18)`, while refinement alone recovers `(0,7,18)` and
`(0,7,22)`; combined retains only the two refinement gains. Native
refinement recovers five tiles, while combined omits `(0,21,15)`.
There is no combined-only synergy.

`refine` is therefore the measured own-branch winner. It strictly dominates
`combined` here: equal decimated yield and one more native certificate, with
less runtime, fewer changed cells, fewer CRC calls, and fewer BP iterations.

Merging the two own-branch outputs gives:

| profile | final conflict-free union | gain over generation-zero union | shared | branch-exclusive |
|---|---:|---:|---:|---:|
| control | 770 | 0 | 744 | 26 |
| recal | 770 | 0 | 745 | 25 |
| refine | **772** | **+2** | 749 | 23 |
| combined | 772 | +2 | 748 | 24 |

The `refine` and `combined` final unions are byte-identical at the
certificate level: set SHA-256
`0ed85227c02456e76c4bd963b344a513d157ad53c7d4a67c3ca71f9429658c28`
and bits SHA-256
`87a4e99c1f3a35c2273fc1c8f41d2fcf3eb67a4da4fb8f61c57fd55bc54770d0`.
The two globally new tiles are `(0,7,18)` and `(0,7,22)` from the decimated
refinement branch; all five native branch-local recoveries were already
present in decimated generation zero.

The authoritative own-branch report is
`experiments/024-feedback-receiver/QUALIFICATION.json`, 2,836,772 bytes,
SHA-256
`089b00e08249460042c360b374175e77f0ce51168fc93c8fe6f7b1717223691b`.
Total qualifier runtime was 2,969.43 seconds.

### Union-seeded factorial

The separately registered union qualification replayed the fingerprinted
E023b merger, proved the 770-certificate bundle against both exact source
states, and bound each footing to its matching source before running any
profile. Every safety, execution, and cross-footing gate passed.

| footing/profile | certificates | exact feedback gains | accepted/refused revisions | changed cells | CRC calls / BP iterations / TIFF reads | runtime |
|---|---:|---|---:|---:|---:|---:|
| decimated control | 770 → 770 | — | 0 / 0 | 0 | 0 / 0 / 0 | 75.45 s |
| decimated recal | 770 → 770 | — | 10 / 173 | 82,442 | 13 / 2,460 / 0 | 137.41 s |
| decimated refine | 770 → **772** | `(0,7,18)`, `(0,7,22)` | 47 / 310 | 415,728 | 45 / 7,983 / 12 | 337.79 s |
| decimated combined | 770 → 772 | `(0,7,18)`, `(0,7,22)` | 54 / 303 | 482,763 | 46 / 8,103 / 12 | 384.70 s |
| native control | 770 → 770 | — | 0 / 0 | 0 | 0 / 0 / 0 | 77.00 s |
| native recal | 770 → 770 | — | 10 / 168 | 127,836 | 29 / 5,280 / 0 | 147.94 s |
| native refine | 770 → 770 | — | 58 / 120 | 609,381 | 71 / 12,840 / 6 | 418.87 s |
| native combined | 770 → 770 | — | 66 / 112 | 695,121 | 72 / 12,960 / 6 | 440.89 s |

Each footing imported 13 exact certificates exclusive to the other source.
All eight arms again have wrong/lost/changed certificate counts of `0/0/0`
and pass the durable-boundary sequential replay validator. Decimated
`refine` and `combined` produce the same exact 772-certificate set; `refine`
uses 67,035 fewer changed cells, one fewer CRC call, 120 fewer BP iterations,
and 46.91 seconds less runtime. The native revisions are operative but add no
global certificate because every own-branch native recovery was already
present in decimated generation zero.

The union-seeded and merged own-branch 772 frontiers are
certificate-identical: set SHA-256
`0ed85227c02456e76c4bd963b344a513d157ad53c7d4a67c3ca71f9429658c28`
and bits SHA-256
`87a4e99c1f3a35c2273fc1c8f41d2fcf3eb67a4da4fb8f61c57fd55bc54770d0`.

The authoritative union-seeded report is
`experiments/024-feedback-receiver/QUALIFICATION-UNION.json`, 2,520,496
bytes, SHA-256
`d92dd7e753e0b8f5e1e6592d2b04d95156f284a3f6f9ba1034b1bfdf8c6710e8`.
Total qualifier runtime was 2,176.99 seconds.

The measured operational winner is therefore:

```text
trusted 770-certificate union
  + decimated E021.6 pixels
  + refine profile
  = 772 correct certificates
```

The exact persistent-state command is in [`HOWTO.md`](HOWTO.md).

The historical E023c factorial separately qualified NN/DD/ND/DN at 752/757/749/756 on legacy
pre-E021.6 E023b.0 v1 footings. Its correct 772 set overlaps the E024
`refine`/`combined` 772 set on 770 tiles. E023c alone has `(0,21,16)` and
`(0,27,21)`; E024 alone has `(0,7,22)` and `(0,27,12)`. Their observer-side
union is 774 correct tiles.

This is not yet an admissible E024 seed. E023c's checked report lacks packed
per-tile certificate rows and exact certifying-attempt provenance, and it
does not contain either exact current E021.6 source artifact. Import requires
a blind provenance-complete E023c rerun/exporter plus a replayable,
conflict-checked composite trust root; mere report conversion is
insufficient.

## HP E018b current-stack validation

The 2026-07-17 validation is a separate experiment from the E018 factorial
above. It runs the registered `refine` profile against the two real HP-1200
E018b payload sheets, both from standalone native E023b+BP and from every
lane in the production E023c cascade. The retained compact report is
[`HP-E018B-QUALIFICATION.json`](HP-E018B-QUALIFICATION.json).

| route | start LDPC/useful | final LDPC/useful | new useful/inert |
|---|---:|---:|---:|
| C3 standalone E023b | 730 / 709 | 734 / 712 | 3 / 1 |
| C3 production E023c | 754 / 731 | 754 / 731 | 0 / 0 |
| C2 standalone E023b | 1,416 / 1,358 | 1,423 / 1,358 | 0 / 7 |
| C2 production E023c | 1,438 / 1,363 | 1,439 / 1,364 | 1 / 0 |

Standalone C3 recovers `(0,0,17)`, `(0,15,8)`, `(0,15,9)` plus inert
`(0,34,1)`. Standalone C2 recovers seven correct column-34 edge addresses,
all outside the 1,734-symbol fountain domain. The only post-cascade recovery
is useful C2 tile `(0,18,26)`.

The audits were not recovery inputs. The standalone v1 runs are retained as
historical unbound observer evidence. The post-E023c portfolios were
re-audited with the v2 bound contract: every cascade, exact adopted export,
official union, baseline, E024 state, observer report, and manifest was
replayed and frozen before the hashed printed ground truth was opened. The
bound audit then:

1. replay-loaded every E024 state through the production validator;
2. matched the supplied observer report to authoritative state;
3. required format, geometry, rate, page, and physical-capture compatibility;
4. reconstructed conflict-free generation-zero and final portfolios;
5. proved no generation-zero certificate was lost or changed;
6. checked every lane and final-union certificate against frozen truth; and
7. split final and newly recovered certificates into useful fountain symbols
   and inert layout-edge addresses from the matching manifest.

All gates pass and every one of the 734 C3, 1,423 C2, 754 post-cascade C3,
and 1,439 post-cascade C2 final certificates is correct. The retained audit
SHA-256 values are:

- standalone C3:
  `41a22c0188a994d84985147bd724b423e02c0de4e1f706c40a47f0227c0f728b`;
- standalone C2:
  `6cd16a0131b5473f307972af03e25f77f26b0f0bca11211535b9839c6a14f8b7`;
- production E023c C3 v2 `QUALIFIED_BOUND` portfolio:
  `2b70cdaabe5c60f4a2ffee75b77d4abe980a3e4bacd1880659f4a733694375a4`;
- production E023c C2 v2 `QUALIFIED_BOUND` portfolio:
  `8f54ac717cf661bbb227f6e169b9f818357fa70b918ca89f05dd15d51e3511f2`.

The earlier post-E023c v1 hashes `cad2dded...7a8c9` and
`02c4994d...58f1` remain in the machine record as historical unbound
observer reports; they are not the composition proof.

The work/yield result is the important qualification outcome:

| route | accepted/refused revisions | changed cells | CRC calls | BP iterations | gain |
|---|---:|---:|---:|---:|---:|
| C3 standalone | 16 / 100 | 237,989 | 65 | 13,220 | +4 LDPC / +3 useful |
| C2 standalone | 67 / 387 | 1,408,273 | 379 | 78,173 | +7 LDPC / +0 useful |
| C3 after E023c, 3 lanes total | 24 / 113 | 250,806 | 58 | 12,180 | 0 |
| C2 after E023c, 2 lanes total | 102 / 624 | 1,696,545 | 461 | 96,682 | +1 useful |

For both formats, the standalone E023b→E024 final set is a strict subset of
the production E023c→E024 final set. E023c therefore performs most of the
recoverable work here, and broad affine feedback after it has sharply
diminishing return. This does not invalidate E024's safety architecture or
its original E018 `refine` win; it changes where to spend the next algorithm
budget. The next distinct hypothesis should be bounded seam-aware piecewise
pose plus explicit support revision, not an indiscriminate repetition of the
same global affine/context/BP route.

The production-cascade experiment uses
`e023c_e024_bridge.py` to export complete embedded E023b lanes, merge their
exact certificates with the official E023b merger, run one independent E024
state per lane, and audit the final union. It never treats deterministic
scale views as independent LLR evidence. The adapter is qualified here as
experimental measurement plumbing, not as an integrated production entry
point or a backward E023c replay loop.
