# E025 machine contracts

## 1. Stimulus manifest

Schema:

```text
paper-store/e025/stimulus/v2
```

The top level records the fixed seed, layout version, page kind, primary and
comparison authored grids, requested printer grid, deterministic bundle ID,
page size, exact PostScript digest, semantic manifest digest, and one page.

The page contains four typed collections:

| collection | meaning |
|---|---|
| `candidates` | exact alphabet/grid/path records keyed by candidate ID |
| `infrastructure` | chiral corners, internal plus marks, and dynamic strips |
| `probes` | deterministic physical patterns with geometry and GT digest |
| `fields` | deterministic state fields and FEC coupons |

### Infrastructure

Corner and plus records use the 600-dpi layout frame. Machine-strip records
declare `PHCAL1/LAY=1`, 724×11 modules, 390 payload bytes, CRC-16/CCITT-FALSE,
and the effective-resolution module formula. Strip contents are generated at
print time and are therefore intentionally excluded from static GT hashing.

### Physical probe

Every probe records:

- stable `probe_id`, group, kind, and plane;
- source DPI and source-dot rectangle;
- equivalent 600-layout-dot rectangle;
- exact typed parameters and fixed seed label;
- SHA-256 of regenerated source-dot ground truth.

Kinds are `edge_tick`, `paper`, `solid`, `tone`, `profile_tone`, `grating`,
`phase_rail`, `line_width`, `checker`, `isolated_dots`, `white_holes`,
`slanted_edge`, `microtext`, and `registration_cross`.

Tone probes declare `mode = fixed-profile|response`, the nominal coverage,
station, and measured axis. `profile_tone` is balanced along that axis so the
analyzer can report the exact authored-coverage profile beside measured
density. Background probes are declared `paper` rectangles and emit no ink.
Each plane-registration station contains four spatially separated
`registration_cross` probes tied by one target ID.

### Channel field

Every field records:

- stable field ID, family, role, candidate key, seed label, and stratum;
- source and layout placement;
- cell dimensions `nx × ny`;
- exact state-label SHA-256;
- optional edge/gap identity;
- for `fec_coupon`, rate, calibration prefix, codeword start, and exact word
  count.

Families are:

| family | purpose |
|---|---|
| `prnd` | primary balanced channel evidence |
| `edge_canary` | payload-safe printable extent |
| `fec_coupon` | small real-code compatibility confirmation |

Ground truth is regenerated from the fixed public seed and field label. The
analyzer refuses any digest mismatch.

## 2. Print-time machine strip

The existing `PHCAL1/LAY=1` transport is reused. E025 adds raw semicolon
fields while preserving the 390-byte/CRC format:

```text
J bundle ID          S public seed         EX E025
PV E025 page layout  PK mono|color          AR primary grid
R0 requested grid/default
LL language level    RD default resolution RE effective resolution
PS page size         IB imaging bbox       DU/TU duplex/tumble
CM color model       PR/V/RV/SN product/version/revision/serial
```

Unknown or unavailable values are retained as such. Two strip placements must
decode independently; equality is expected because both were generated from
the same live device state.

## 3. Analysis report

The portable outer report remains:

```text
paper-store/channel-metrology/v1
```

Its `CandidateObservation` rows provide exact candidate identity, held-out
BER/MI, sampling, diagnostics, and optional LDPC yields. E025-specific evidence
lives under:

```text
metadata.e025.schema = paper-store/e025/analysis/v2
```

That block contains:

- `device_readback_strips`;
- `geometry`, including corner affine and internal-warp residuals;
- `probes`, split into printable ticks, `tone_metrology`, controlled
  `background`, `plane_registration`, morphology/frequency, and geometry
  rails;
- `field_summaries`;
- `candidate_factorials`, grouping shape, aspect, constellation, and
  emission-path rows;
- `payload_safe_extent`;
- measured-rectangle `capacity` rows;
- optional trace-directory path.

The outer report semantic digest covers all of this evidence.

`tone_metrology` retains every response sample, each fixed density and
authored-coverage profile, and per-plane least-squares models with categorical
coverage plus independent centered x/y slopes. `background` retains all ten
witnesses and R/G/B spatial fits. `plane_registration` retains each K/C/M/Y
centroid residual, CMY-minus-K vectors, RMS, and maximum displacement.

Printable-edge tick rows carry `scan_visible_fraction`. Their status is one
of `present`, `partial`, `absent`, or `unobservable`; the last value means the
registered full probe footprint was not contained in the scanner raster and
must not be interpreted as a printer margin. Morphology/frequency rows carry
`phase_alignment_source_dots` and `n_aligned_source_dots`. Alignment is a
bounded integer translation over non-wrapped overlap; invariant grating axes
are not searched. Blur and non-rigid errors remain in correlation/BER.

Each payload-safe canary records `reference_scope` and
`reference_field_ids`. Normal scope is the same candidate's designated
`role=channel` interior population. `fallback:any-prnd` is retained explicitly
only when a candidate has no such field. Stressed factorial/equal-grid arms
therefore cannot silently relax an edge threshold.

### Trace directory

Optional schema:

```text
paper-store/e025/trace-index/v1
```

`index.json` binds the manifest and capture digests to one compressed NPZ per
field. Each NPZ stores row-major arrays:

```text
true_state, predicted_state, split, features, state_scores, bit_llr
```

Split codes are 0 phase, 1 train, 2 validation, and 3 FEC codeword suffix.
Coordinates are reconstructed exactly from the manifest grid and flat index.

## 4. Profile

Schema:

```text
paper-store/e025/profile/v2
```

Profile kinds are `emitter`, `sensor`, and `pipeline`. Every profile records:

- policy and input report digests;
- capture footings and machine strips;
- conservative intersection of payload-safe extents;
- raw-channel summaries;
- per-level FEC compatibility confirmations;
- rate recommendations and reasons;
- qualified subset.

Sensor profiles additionally contain exact same-sheet field deltas. Pipeline
profiles may contain an advisory receiver hint with
`may_weaken_receiver_gates: false`.

Policies are intentionally explicit:

| policy | sheets | max worst BER | min MI/alphabet | exact coupon sheets |
|---|---:|---:|---:|---:|
| survey | 1 | 0.03 | 0.75 | 1 |
| production | 3 | 0.01 | 0.90 | 3 |
| archive | 6 | 0.005 | 0.95 | 6 |

Passing these policy gates is a feasibility recommendation, not a payload CRC
or archive-lifetime certificate.
