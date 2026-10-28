# Experiment 018b — PAYLOAD-SHEET: generic C3/C2 K-plane encoder

**2026-07-17 — status: BUILT; C3 + C2 PRINTED, SCANNED, NATIVE-TAKE
DECODED ON HP/CANON; E023c SINGLE-CAPTURE QUALIFIED ON ONE HP-1200 SCAN PER
PROFILE.**
This is the reusable encoder that E018 and E016 deliberately were not:

- E018 proved the layout-version-3 **C3** K-plane sheet and a near-half-page
  confetti volume.
- E016 proved the layout-version-3 **C2 black-only** coded volume.
- E018b accepts an arbitrary non-empty payload file and emits either geometry
  with the same coding stack: `fountain-v1` → per-tile `r0550` LDPC + CRC-32
  → one archive-style K imagemask.

The implementation is
`experiments/018b-payload-sheet/gen_e018b.py`. It emits files only; it never
prints.

## User contract

From the repository root:

```text
# Show both fixed-key capacities.
env/bin/python experiments/018b-payload-sheet/gen_e018b.py capacity

# Show one profile, optionally as JSON.
env/bin/python experiments/018b-payload-sheet/gen_e018b.py capacity c3
env/bin/python experiments/018b-payload-sheet/gen_e018b.py capacity c2 --json

# Encode a file. Default output is content-addressed under this experiment's
# ignored build/ directory.
env/bin/python experiments/018b-payload-sheet/gen_e018b.py emit \
  c3 payload.tar.zst

env/bin/python experiments/018b-payload-sheet/gen_e018b.py emit \
  c2 payload.tar.zst -o /path/to/archive-c2.ps
```

Each emit writes:

- the one-page PostScript file;
- `<stem>_manifest.json`, which is the complete out-of-band volume descriptor;
- `<stem>_gt/K__...npy`, the exact addressed K bitmap for render/receiver
  verification.

The input bytes are stored verbatim. E018b does not compress, encrypt, name,
or wrap the payload, so callers should prepare a self-describing compressed
archive when that is the desired archival object.

## Frozen profiles and capacity

| profile | inherited geometry | fixed symbol bits | interior symbols N | max source symbols K | payload capacity | net field density |
|---|---|---:|---:|---:|---:|---:|
| `c3` | E018/E012, 2220×1500 cells, 3×3 dots/cell | 2,090 | 782 | 391 | **102,148 B (99.75 KiB)** | 15.21 b/mm² |
| `c2` | E016/E014, 3300×2220 cells, 2×2 dots/cell | 2,087 | 1,734 | 867 | **226,178 B (220.88 KiB)** | 34.45 b/mm² |

Both are single-plane K pages. “C2 black-and-white” means a clean K
imagemask at two printer dots per cell; C3 is the analogous three-dot cell.

The keys are fixed, so capacity is exact and stable for each profile. As a
defensive invariant, E018b also proves the adversarial lower bound over every
possible p60b6 key:

1. a 64-cell LDPC tile over the p60b6 pilot lattice can contain at most 144
   pilot sites for any seed;
2. `r0550` has 2,240 information positions and each tile spends 32 on CRC;
3. every interior fountain symbol therefore has at least
   `2240 - 144 - 32 = 2064` bits;
4. either fixed key must therefore provide at least 2,064 symbol bits.

The actual fixed-key minima are 2,090 bits for C3 and 2,087 bits for C2.
Capacity is `floor(N/2) × fixed_symbol_bits / 8`; it does not vary with the
payload.

## What “0.5 recovery” means

At the advertised capacity, `K/N <= 0.5`: at most half of the interior
symbols are source symbols and the rest are fountain repair symbols. Smaller
files are not padded to capacity; they get a lower K/N and therefore more
recovery headroom.

This is the coding dial, not a promise that exactly 50.000% of arbitrary
physical paper always closes:

- `fountain-v1` is the repository's declared dense-random-linear stand-in
  for RaptorQ and needs a small rank overhead above K for high confidence;
- only CRC-certified LDPC tiles count;
- fragment boundaries reduce certified-tile yield. Experiment 015 measured
  that physical-area tax explicitly.

The manifest records `rank_overhead_reserved: false` so no decoder can
mistake the K/N budget for a strict zero-overhead threshold.

## Seed, determinism, and format identity

The public keys are hardcoded format constants:

```text
C3: paper-store/018b-c3-r0550-0.5
C2: paper-store/018b-c2-r0550-0.5
```

They do not depend on the payload filename, length, bytes, or SHA-256. A
receiver therefore knows the key as soon as it selects `c3` or `c2`, before
recovering any payload. Different payloads intentionally reuse their
profile's key; C2 and C3 remain distinct.

This is a declared exception to the earlier “one seed per printed sheet”
doctrine. It trades seed-level instance identity for bootstrap independence.
Consequently, receiver state must never combine two different physical E018b
payload sheets of the same profile: their pilots and addresses are
indistinguishable, while their valid LDPC/fountain symbols carry different
data. Bind a decode session to one physical sheet/volume and use the
manifest's data length and expected SHA-256 for the final instance check.

The payload SHA-256 is used only for integrity metadata and the default
content-addressed output filename. It never enters a pilot, LDPC, fountain,
or payload-scramble key.

## Descriptor and decode handoff

The fixed keys also have decoder registry rows:

- `e018b-v3-c3` → `paper-store/018b-c3-r0550-0.5`
- `e018b-v3-c2` → `paper-store/018b-c2-r0550-0.5`

Thus format identification and payload sampling need no payload-derived
information. The manifest records the remaining volume inputs:

- layout version, encoding id, K plane, page cells, and field placement;
- public seed;
- `fountain-v1`, `r0550`, data length, data SHA-256, K, N, and symbol size.

This is still an R5 limitation: the descriptor is not printed in-band.
Preserve the manifest with the page. The static `FormatDescriptor` supplies
the geometry and key; a receiver constructs `fountain.VolumeSpec` from the
manifest's payload length and volume block.

## Verification

`tests/test_e018b.py` gates:

1. direct equality with the E018 C3 and E016 C2 `ComposeSpec`s;
2. the exhaustive 144-pilot adversarial bound and exact fixed-key capacities;
3. the two literal public keys, payload-independence, and oversize refusal;
4. byte-exact fountain recovery from a deterministic K+16 near-half subset
   at full advertised capacity for both profiles;
5. actual PS/manifest/GT emission for both C3 and C2, Ghostscript
   pixel-exact rendering, deterministic regeneration, and descriptor
   reconstruction.

The generator itself performs no physical action. Printing remains external
to the tool and subject to `.claude/rules/hardware.md`.

## 018b.1 — first payload pages printed (2026-07-16)

The user printed both generated pages. The generated artifacts are fully
identified from their manifests:

| profile | input | bytes | K/N | PS sha256 |
|---|---|---:|---:|---|
| C3 | `lena_std-88.heic` | 88,157 | 338/782 = 0.4322 | `f8c948f9d6b7bdec1009fd4f306bd3d678de0ccfe43cfdffde40452c49b2900d` |
| C2 | `lena_std-192.heic` | 192,160 | 737/1734 = 0.4250 | `995ef4ab208542c08ab8158ba259ce47cebd0949a60749bac335286705898b81` |

Manifest print commands:

```text
scripts/print_plane.sh experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693.ps
scripts/print_plane.sh experiments/018b-payload-sheet/build/e018b-c2-424e41a28257.ps
```

The pages are confirmed physically available because scanner captures now
exist. Print engine, media, exact send-path confirmation, and print settings
remain pending user confirmation; they must not be guessed from the
manifest's recommended command.

## 018b.2 — native HP/Canon take 1 prepared (2026-07-16)

Four full-page grayscale captures are present under `scratch/e018b/`:

| profile | scanner footing | raster (H×W) | file | sha256 |
|---|---|---:|---|---|
| C3 | HP 1200 dpi | 14,028×9,920, 8-bit gray PNG | `hp-e018b-c3-hp-1200-page.tiff.png` | `dca3cdff39049949cbb83b3bd9a594c2d27d46229d3bfef708eeeda254dbf282` |
| C3 | Canon 4800 dpi | 56,128×40,832, 8-bit gray uncompressed TIFF | `hp-e018b-c3-canon-4800-page.tiff` | `547ddb04a05f6ad056d340f44c8cf311f529952da3f12d6f6405f4a85576dc6d` |
| C2 | HP 1200 dpi | 14,028×9,920, 8-bit gray PNG | `hp-e018b-c2-hp-1200-page.tiff.png` | `51b2841d044d939b2355c4d9069141ba5ced709a76986a492f0b2b4d514b2798` |
| C2 | Canon 4800 dpi | 56,128×40,832, 8-bit gray uncompressed TIFF | `hp-e018b-c2-canon-4800-page.tiff` | `b49e40f6de2872126bd2215e7779123efdc955961647680d41148a1b54b6234f` |

HP metadata identifies `Color LaserJet MFP M281fdw (<host>)` via Apple Image
Capture at nominal 1200 dpi. The Canon TIFFs declare 4800 dpi but do not
carry scanner-model or acquisition-command metadata. Media and any scanner
enhancement settings remain unknown and must not be invented.

`experiments/023b-integrated-receiver/018b-take-1.sh` runs the four
**native** footings without decimation. Each case gets its own fresh E023b
state, runs `ctx-pava-v1`, spends one final `--bp-retry`, then invokes
`experiments/023b-integrated-receiver/score_e023b.py` against the matching
manifest:

```text
experiments/023b-integrated-receiver/018b-take-1.sh
```

Keep `http://localhost:8023/` open while it runs. The same live-diagnostic
port is reused sequentially, while persisted frames and score JSON remain
separate under `scratch/e018b/take-1/<case>/`. `DIAG_PORT`, `PANEL_WIDTH`,
`OUTPUT_ROOT`, and `PYTHON` are environment overrides; `DRY_RUN=1` prints
the complete command matrix without decoding.

This take compares practical native scanner footings, not a controlled
scanner-only variable: HP runs at 1200 dpi and Canon at 4800 dpi. The
context+BP arm is the best qualified E023b C3 setting; applying it to C2 is
format-compatible but remains a first physical C2 measurement.

The scorer preserves E023b's boundary: it does not change receiver state or
pretend that raw LDPC certificate count equals recovery. It excludes
fountain-inert edge certificates, computes actual fountain rank, and verifies
the recovered payload length and SHA-256. An under-ranked session is an
honest `OPEN` result. Full contract:
`experiments/023b-integrated-receiver/SCORE.md`.

## Run table

| run | date | action | result |
|---|---|---|---|
| 018b.0 | 2026-07-16 | generic C3/C2 emitter + fixed public keys + exact capacity + preflight | zero-print build; 8 E018b + 47 registry/inherited regressions green |
| 018b.1 | 2026-07-16 | user printed first C3 and C2 payload pages above | physical pages confirmed by subsequent scans; print engine/media/path/settings pending |
| 018b.2 | 2026-07-16 | HP-1200 + Canon-4800 native scans recorded; E023b scorer and four-case take script prepared | scan hashes pinned; 6 scorer tests green |
| 018b.3 | 2026-07-17 | four native E023b ctx+PAVA+BP cases completed and scored | C3 HP 730/709 useful; C3 Canon 805/782; C2 HP 1,416/1,358; C2 Canon 1,813/1,730; all payload length/SHA checks pass |
| 018b.4 | 2026-07-17 | HP C3/C2 reprocessed through production E023c and E024 `refine` tails | E023c gives C3 754/731 useful and C2 1,438/1,363; post-E023c E024 gives 0 and +1 useful respectively; all frozen audits correct/conflict-free |
| 018b.5 | 2026-07-17 | C2/C3 inner-rung and fountain-rate allocation study | analytic design note only: C2 remains the absolute-payload choice; next Canon-4800 intact-sheet hypothesis is C2 `r0700` at `K/N=0.70--0.75`; no format or generator change |

## Measured native take and HP feedback follow-up

`018b-take-1.sh` has completed all four practical native footings.  Counts
are reported as syndrome+CRC LDPC certificates followed by fountain-useful
symbols; the difference is made of certified layout-edge addresses that do
not map to a fountain ESI.

| profile | scanner | LDPC certificates | useful symbols | rank | payload |
|---|---|---:|---:|---:|---|
| C3 | HP 1200 | 730 | 709 / 782 | 338 / 338 | 88,157 bytes, SHA verified |
| C3 | Canon 4800 | 805 | 782 / 782 | 338 / 338 | 88,157 bytes, SHA verified |
| C2 | HP 1200 | 1,416 | 1,358 / 1,734 | 737 / 737 | 192,160 bytes, SHA verified |
| C2 | Canon 4800 | 1,813 | 1,730 / 1,734 | 737 / 737 | 192,160 bytes, SHA verified |

These numbers establish successful recovery on every recorded first-take
scan.  They do not isolate scanner quality: HP and Canon have different
native sampling densities and the acquisition metadata caveats above remain.

The HP scans were then used for a current-stack receiver comparison:

| route | C3 LDPC/useful | C2 LDPC/useful |
|---|---:|---:|
| native E023b+BP generation zero | 730 / 709 | 1,416 / 1,358 |
| after E024 `refine` | 734 / 712 | 1,423 / 1,358 |
| production E023c generation zero | 754 / 731 | 1,438 / 1,363 |
| after per-lane E024 `refine` | 754 / 731 | 1,439 / 1,364 |

All final certificate bits match frozen printed ground truth; no baseline
certificate is lost or changes value, and all unions are conflict-free.
The post-E023c v2 audits are `QUALIFIED_BOUND`: they bind exact adopted lane
files and the official union to every baseline/state/report, replay and
freeze every non-truth input before hashed ground truth, and pass with hashes
`2b70cdaa...75a4` (C3) and `8f54ac71...11f2` (C2).  Earlier v1 portfolio
reports are retained only as historical unbound observers.  The compact
authoritative retention record is
`experiments/024-feedback-receiver/HP-E018B-QUALIFICATION.json`.

The seven E024 additions to standalone HP C2 are all inert column-34 edge
addresses and therefore add no usable fountain symbol.  After the production
scale cascade, E024 adds no C3 tile and one useful C2 tile `(0,18,26)` at
high revision/decoder cost.  The standalone E023b→E024 final set is a strict
subset of the E023c→E024 set for both formats.  The practical lesson is to
keep raw LDPC certification and payload-useful yield separate, and to treat
broad affine feedback after scale-space recovery as a low-return tail rather
than the next primary acquisition mechanism.

## 018b.5 — C2/C3 rate allocation study (2026-07-17)

**Status: analytic design note, not a format freeze or hardware
qualification.**  The emitted E018b profiles remain exactly `r0550` with
`K/N <= 0.5`; `gen_e018b.py`, the registry, manifests, and printed pages are
unchanged.  Ratios below mean the fountain source fraction `K/N`, so a lower
number spends more page symbols on outer repair.

### What the Canon evidence says

The comparable full-page Canon-4800 measurements are the native E023b runs
above, including their E021 segmentation, E022 placement, context+PAVA, and
final BP paths.  They are not matched production-E023c full-page runs.  The
current Canon E023c evidence is C2 confetti with incomplete physical coverage;
it is valid recovery evidence but not a page-yield denominator.

| r0550 Canon take | C2 | C3 |
|---|---:|---:|
| fountain-bearing tiles | 1,734 | 782 |
| useful certificates | 1,730 (99.77%) | 782 (100%) |
| useful-tile pre-decode hard disagreement, mean | 1.59% | 0.54% |
| useful-tile disagreement, p95 / p99 | 3.83% / 5.99% | 2.15% / 5.77% |

The disagreement statistic compares the hard sign of the stored scan LLR at
each informative cell with the re-encoded CRC-certified codeword.  It is a
pre-decode channel statistic, not residual decoded BER.  It is conditioned on
useful tiles that certified; failed and unavailable tiles are excluded, so it
is not an unconditional page/channel BER distribution.  C3 is plainly
cleaner, but its useful-certificate advantage on this take is only 0.23
percentage points.  C2 has 2.217 times as many fountain-bearing tiles and
nearly the same bits per tile, giving 2.214 times C3's payload at equal inner
rung and `K/N`.  That geometry dominates the measured yield difference.

### Exact prospective capacities

These values reuse the current fixed profile seeds and recompute the minimum
full-tile capacity at each existing LDPC rung.  A future profile with a new
seed must recompute and freeze its own minimum.  Capacities use
`K=floor(N*f)` and do not subtract an explicit fountain-rank reserve.

| profile / rung | symbol bits | `f=.65` | `f=.70` | `f=.75` | `f=.80` |
|---|---:|---:|---:|---:|---:|
| C2 `r0550` | 2,087 | 294,006 B | 316,441 B | 339,137 B | 361,833 B |
| C2 `r0625` | 2,407 | 339,086 B | 364,961 B | 391,137 B | 417,313 B |
| C2 `r0700` | 2,727 | 384,166 B | 413,481 B | 443,137 B | 472,793 B |
| C2 `r0775` | 3,047 | 429,246 B | 462,001 B | 495,137 B | 528,273 B |
| C2 `r0850` | 3,367 | 474,326 B | 510,521 B | 547,137 B | 583,753 B |
| C3 `r0550` | 2,090 | 132,715 B | 142,903 B | 153,092 B | 163,281 B |
| C3 `r0625` | 2,410 | 153,035 B | 164,783 B | 176,532 B | 188,281 B |
| C3 `r0700` | 2,730 | 173,355 B | 186,663 B | 199,972 B | 213,281 B |
| C3 `r0775` | 3,050 | 193,675 B | 208,543 B | 223,412 B | 238,281 B |
| C3 `r0850` | 3,370 | 213,995 B | 230,423 B | 246,852 B | 263,281 B |

C3 can overtake only by accepting a much more aggressive channel contract.
For example, matching C2 `r0550/.65` (294,006 B) requires C3 `r0850` with at
least 698 source symbols, `K/N=0.8926`; `r0850/.90` carries 296,138 B with
only ten percent nominal outer repair.  C3 `r0700/.80` carries 213,281 B,
still below the current conservative C2 `r0550/.50` capacity of 226,178 B.
Thus a high-likelihood C3 setting does not carry more absolute payload than a
high-likelihood C2 setting.

### Observer-only alternative-rung replay

One non-authoritative exploratory diagnostic replayed the Canon evidence at the other
LDPC rungs.  For each originally certified useful tile it retained the exact
erasure positions, hard-error locations, and LLR magnitudes, re-signed that
evidence onto a valid alternative-rung codeword, and invoked the LDPC decoder.
The C2 `r0550` control reproduced all 1,730 available tiles; its
four unavailable original tiles were conservatively retained as failures.
The C3 control reproduced all 782 tiles.

| rung | C2 useful replay | C3 useful replay |
|---|---:|---:|
| `r0550` | 1,730 / 1,734 (99.77%) | 782 / 782 (100%) |
| `r0625` | 1,730 / 1,734 (99.77%) | 775 / 782 (99.10%) |
| `r0700` | 1,723 / 1,734 (99.37%) | 771 / 782 (98.59%) |
| `r0775` | 1,695 / 1,734 (97.75%) | 768 / 782 (98.21%) |
| `r0850` | 1,555 / 1,734 (89.68%) | 756 / 782 (96.68%) |

The sources were the post-BP Canon states reported by
`scratch/e018b/take-1/c2-canon-4800/combined.json` (authoritative digest
`4668e29c3206a214471ef39a3c59016014aaec4f95805e4e0d2503f10504dccb`)
and the analogous C3 report (digest
`a02d94d1a5cc4b702eb055b39c97571a12249d7c3e5046f4710d6531dee43a3c`).
The ephemeral calculation retained no script, report, alternative-codeword
seed, or exact decoder schedule.  The table is therefore deliberately
**non-reproducible exploratory evidence**, not a retained measurement.  It
also assumes that changing the scrambled payload/codeword does not change the
physical error/reliability field.  Scrambling makes that a useful channel
hypothesis, but neighborhood-dependent printing, structured errors, and
print/day variation can violate it.  These numbers may guide a tracked replay
or the next physical experiment; they are not a direct higher-rung print
result and must not be cited as qualification.

### Decision and next checkpoint

- **Absolute payload:** choose C2.  C3 remains attractive when acquisition
  latitude, lower compute, or a poorer scanner matters more than bytes per
  sheet, but it does not win the high-recovery capacity comparison.
- **Evidence-backed conservative design:** C2 `r0550` at `K/N=.70--.75`
  carries 316,441--339,137 B.  The historical E016.2 receiver, before its
  later field-aligned-window correction, yielded 1,452, 1,377, and 1,412
  interior `r0550` symbols from its three individual Canon scans.  With a
  16-symbol rank cushion, `.75` needs 1,316 and all three clear it; `.80`
  needs 1,403, which one misses and another clears by only nine.  E016.3
  subsequently raised scan A to 1,681/1,734 by correcting boundary-window
  registration; do not mix those receiver generations into one channel
  distribution.
- **Best next Canon-4800 intact-sheet hypothesis:** C2 `r0700` at
  `K/N=.70--.75`, carrying 413,481--443,137 B.  The replay places `r0700` at
  the useful knee, while the existing BSC gates and weaker physical evidence
  make `r0775` an aggressive follow-up rather than the first freeze.  The HP
  single-capture `r0550` yield is only 1,363 useful symbols, 47 above a
  `.75` K+16 target before any higher-rung loss; do not generalize this
  recommendation across scanner footings.
- **Fragment/confetti priority:** retain C2 `r0550` around `.60--.65`; its
  partial-tile erasure tolerance has direct value at cut boundaries.
  C2 `r0625/.60` (312,910 B) is the clean intermediate experiment.
- **Rank rule:** dense `fountain-v1` needs a small algebraic surplus.  For the
  current one-block dense-GF(2) E018b volume, 16 rows beyond K gives an
  approximate random-row rank-failure scale of `2^-16`.  A hard promise to
  recover from exactly fraction `q` therefore uses
  `K <= floor(q*N)-16`, rather than setting `K/N=q` and spending the entire
  physical allowance.  Multi-block volumes need per-block and union failure
  accounting rather than blindly reusing one global 16-row reserve.

The first clean physical qualification is a matched-payload full-page C2
ladder, printed in the same batch and scanned at the same placements, that
holds payload near 294 kB while moving protection from inner LDPC to the
fountain layer:

```text
r0550: K=1127, K/N=.64994, 294006 B
r0625: K= 978, K/N=.56401, 294255 B
r0700: K= 863, K/N=.49769, 294175 B
```

That comparison directly tests whether Canon failures are
predominantly cell noise, for which the lower rung helps, or whole/marginal
tiles, for which the stronger outer erasure layer helps.  Repeat it across
multiple print copies/days and at least two scan placements, reporting
lower-tail useful yield and partial-coverage bins.  Only after locating that
allocation knee should a high-capacity `r0700/.70--.75` candidate and an
aggressive `r0775` follow-up be frozen or compared.
