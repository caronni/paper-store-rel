# r0775 versus QR v40-L: size and conditional FEC resilience

## Size assumptions

The common payload is **2,953 arbitrary bytes**, QR v40-L's byte-mode
maximum. The QR symbol has 177 × 177 modules; its four-module quiet zone
makes the full footprint 185 × 185 module pitches.

Our comparison uses K/black ink, r0775-p100, q=1, a 36-byte volume envelope,
and a **hypothetical two-symbol fountain reserve**. The production planner
is unchanged. Each tile carries 3,067 fountain-symbol bits, so the source
needs ceil((2,953 + 36) × 8 / 3,067) = 8 symbols. Ten printed tiles supply
eight source symbols plus two extra symbols. A compact 3 × 4 rectangle
prints twelve tiles instead, adding two more symbols through layout rounding.

These compact layouts assume the **format, version, tile addresses and K=8
are supplied out of band**. They are sizing proposals, not volumes accepted
by the current production receiver. Its metadata channel requires rank 24
and at least 48 distinct certified equations before trusting the metadata
word; a K/black-ink tile supplies only one equation. Reducing the fountain
reserve alone does not remove that constraint. See the
[metadata format contract](../src/holo/format/metadata.py).

| Layout | c3 (0.127 mm/cell) | c4 (0.169333… mm/cell) |
| --- | --- | --- |
| QR v40-L, with quiet zone | 23.495 × 23.495 mm | 31.327 × 31.327 mm |
| Our minimum ten tiles, 2 × 5 | 16.256 × 40.640 mm | 21.675 × 54.187 mm |
| Our compact twelve tiles, 3 × 4 | 24.384 × 32.512 mm | 32.512 × 43.349 mm |

Our sizes exclude surrounding blank space. The ten-tile active area is
1.197× the QR footprint including its quiet zone; the twelve-tile area is
1.436×. This compares equal module pitch. Enlarging QR modules to equal
physical area would change the optical comparison.

The shortened LDPC rate is 3,100/3,996 = 0.775776. QR v40-L has 19
RS(148,118) blocks and six RS(149,119) blocks: data rate 2,956/3,706 =
0.797625. Each RS block has 30 parity bytes. The similar inner-code rates
do not include our outer fountain overhead or either format's acquisition
structures.

### Proposed 3 × 3 XOR variant

The later discussion proposed eight systematic source tiles and one tile
containing their bitwise XOR. That would recover any single missing or
CRC-rejected tile deterministically. The eight symbols hold up to 3,031 file
bytes after the 36-byte envelope, so they fit the common 2,953-byte payload.
The active field would be **24.384 mm square at c3**, or **32.512 mm square
at c4**, excluding surrounding blank space: 1.077× QR's area including its
quiet zone at the same cell pitch.

This variant is **not implemented or simulated here**. It would need an
explicit toy contract with the metadata supplied out of band, or a new small
object framing design. The generator and image decoder remain single-tile,
263-byte **r0547-p103** harnesses. The recorded study below retains its
earlier ten-tile model; it does not measure the proposed XOR arrangement.

## What was computed

```sh
env/bin/python qr-toy/resilience.py \
  --out qr-toy/build/resilience-new --trials 1000 --workers 4
```

The recorded run uses seed 20260909 and **1,000 independent arbitrary-payload
trials at each of 19 channel settings**. LDPC results use the actual receiver
tile encoder and decoder, shortened by 100 positions, with CRC validation
and comparison to the original bits. Decoder settings: normalized min-sum
alpha=0.8, up to 60 iterations, followed on syndrome failure by the receiver's
existing sum-product retry, also up to 60 iterations. No extra 150-iteration
stage is used.

Three channel models act on correctly located data cells:

- **Independent bit flips:** each bit is flipped with probability p. All
  channel LLR magnitudes are log((1-p)/p).
- **Gaussian soft evidence:** binary levels ±1 plus independent Gaussian
  noise, with sigma chosen to give hard-sliced BER p. LDPC receives the exact
Gaussian channel LLRs. The RS comparison uses the same BER after hard slicing.
- **Identified independent cell erasures:** each missing cell gets LLR zero;
  the other cells are clean. For conventional RS erasure decoding, a byte is
  marked erased if any of its eight bits is erased.

The production LDPC decoder clips finite input LLRs to ±20. The Gaussian
model supplies correctly calibrated channel evidence before that clipping;
photo calibration error is not part of this experiment.

For QR, this is an exact calculation of the probability that **all 25 blocks
are inside the conventional RS unique-decoding radius**, not a QR-reader run.
With independent bit-error or bit-erasure probability p, a byte is affected
with probability b = 1-(1-p)^8. Thus:

    P(all RS blocks within radius) = F(148, b, t)^19 × F(149, b, t)^6

where F is a binomial CDF and t is 15 for unknown byte errors or 30 for
identified byte erasures. The mixed RS condition is 2E + S <= 30 per block.
Correctness is guaranteed inside that radius; recovery outside it is not
modeled. A soft/list decoder or a solver retaining partial-byte information
would be a different RS comparison.

The script now also records the base-10 log probability, evaluated in log
space, so very small positive RS probabilities remain distinguishable from
zero when the ordinary floating-point probability underflows.

For object-scale context, the JSON also reports s^10, where s is the measured
single-tile success fraction. This is the estimated probability that **all
ten independent tiles succeed**, a conservative sufficient condition for
the eight-source-symbol object. Fewer than ten successes can still recover
it; the fountain solve is not simulated. Wilson 95% intervals are reported
for the tile success fraction and propagated through this expression.
These are pointwise intervals, not simultaneous confidence bounds over all
19 channel settings.

## Boundaries of this result

These are conditional FEC results, **not end-to-end photo success rates**.
Scale, grid phase, perspective, address and orientation are already known.
Pilot corruption, missed detection, wrong pose and format discovery are not
tested. IID channels make the particular tile permutation irrelevant, so the
experiment uses an identity slot permutation and arbitrary reserved positions.

Scratches, glare, moiré, defocus, occlusion, paper curvature and residual warp
produce correlated errors. A contiguous damaged region can affect fewer QR
bytes than the same number of scattered bit errors, improving the RS side
relative to the IID model. Conversely, its placement can damage essential
acquisition structures or overload particular blocks. Our tile permutation
redistributes spatial damage within a tile, but a sufficiently obscured tile
still fails as a whole. A two-symbol reserve is not an unconditional promise
to recover any two lost tiles with the current GF(2) fountain construction.

Known erasures are also different from confidently reading covered cells as
white. The latter must be modeled as wrong observations, not zero evidence.
"Deletion" here means absent observations at known grid positions; it is
not a sequence-deletion/synchronization channel.

A planar projective distortion can be removed geometrically before FEC.
Residual distortion needs a spatial displacement field or actual images to
compute its effect; a single angle or damaged-area percentage is insufficient.
A fair next photo comparison needs both formats rendered at the chosen
physical sizes, the same imaging conditions, and separate acquisition and
payload-recovery scores. The earlier r0547 phone successes are not r0775
qualification.

## Sources and reproducibility

- [QR v31–40 capacity table](https://www.qrcode.com/en/about/versionPage/versionPage31_40.html).
- [DENSO's RS correction explanation](https://www.qrcode.com/en/about/error_correction.html).
- RS block sizes were checked against the installed `qrcode` 8.2 table.
- [Study script](resilience.py).
- [Original raw 1,000-trial results](records/resilience-r0775-1000.json), including
  measured input error rates, decoder iterations, confidence intervals and
  wrong-certificate counts. This is the original, pre-review run, retained
  unchanged. It predates the metadata caveat, log-probability output and
  software provenance fields added during code review. New runs record
  Python/NumPy/SciPy versions and SHA256 hashes of the study script, receiver
  codec, LDPC implementation and r0775 matrix. Generated build outputs remain
  ignored by Git; regenerate with the command above.

## Recorded results

All 19,000 trials completed; **zero wrong certificates**. Percentages below
are estimates, not guarantees. Even 1,000/1,000 tile successes has a Wilson
95% lower bound of about 99.62%, or about 96.24% after taking the tenth power.
Entries marked `underflow` are positive RS probabilities too small for the
original floating-point output; they are not mathematically zero.

| Channel | Input error/erasure % | LDPC tile successes | Ten-tile all-success estimate | QR whole-symbol RS probability |
| --- | ---: | ---: | ---: | ---: |
| bit_flips | 0.5 | 1000/1000 | 100% | 99.344% |
| bit_flips | 1 | 999/1000 | 99.004% | 5.4541% |
| bit_flips | 1.5 | 999/1000 | 99.004% | 1.7832e-09% |
| bit_flips | 2 | 994/1000 | 94.159% | 1.322e-29% |
| bit_flips | 2.5 | 844/1000 | 18.341% | 6.832e-58% |
| bit_flips | 3 | 284/1000 | 0.00034134% | 4.7068e-92% |
| gaussian_soft | 1 | 1000/1000 | 100% | 5.4541% |
| gaussian_soft | 2 | 1000/1000 | 100% | 1.322e-29% |
| gaussian_soft | 3 | 1000/1000 | 100% | 4.7068e-92% |
| gaussian_soft | 4 | 1000/1000 | 100% | 1.8591e-172% |
| gaussian_soft | 5 | 867/1000 | 23.999% | 8.357e-264% |
| gaussian_soft | 6 | 35/1000 | 2.7585e-13% | underflow |
| known_cell_erasures | 1 | 1000/1000 | 100% | 99.999% |
| known_cell_erasures | 2 | 1000/1000 | 100% | 45.758% |
| known_cell_erasures | 5 | 1000/1000 | 100% | 1.0213e-89% |
| known_cell_erasures | 10 | 1000/1000 | 100% | underflow |
| known_cell_erasures | 15 | 1000/1000 | 100% | underflow |
| known_cell_erasures | 18 | 948/1000 | 58.625% | underflow |
| known_cell_erasures | 20 | 127/1000 | 1.0915e-07% | underflow |
