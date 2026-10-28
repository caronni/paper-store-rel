# E020 reasoning and design record

## Starting point

E019 addresses the front end of the confetti receiver: identify the parts of
a platen scan that actually contain the printed payload lattice. It must not
claim the homogeneous scanner backing or the unprinted paper margin around a
field. Angle, lattice phase, pilots, BCH, and payload decoding remain
downstream.

The e019 implementation and its Claude discussion went through an important
correction. The first formulation used brightness relative to the estimated
backing, which necessarily included white paper margins on a dark backing.
The discussion then identified modulation, not paper membership, as the right
signal. It also corrected the synthetic model to render each c3 code cell as
one solid bit rather than independent print dots.

The resulting e019 detector uses local standard deviation over a two-cell
window. That is a reasonable acquisition statistic, but it describes only
"contrast nearby." A payload field, a torn paper boundary, a shadow, and a
textured paper patch can all produce local variance. E019 therefore needs the
following decisions after measuring variance:

1. absolute loose and strict thresholds (`8` and `22` in 8-bit units);
2. erosion of the strict seed to remove thin edges;
3. propagation through the loose mask to recover faint field boundaries;
4. binary opening to remove small structures;
5. a component median threshold (`25`) to reject remaining weak blobs.

Those operations are individually defensible, but together they indicate that
the statistic does not directly encode the distinction the receiver cares
about. They also couple boundary shape to a morphology recipe and assume that
toner, scanner, and bit depth have already been normalized to the calibration
conditions.

## Reframing the signal

The useful geometric distinction is dimensionality:

- backing and blank margin have little gradient energy;
- a clean paper/backing boundary has gradient energy mostly normal to one
  curve, so it is locally one-dimensional;
- a scrambled binary lattice contains transitions in two directions over a
  few cells, independent of its rotation and phase.

The local gradient structure tensor records exactly this distinction:

```
J = G_sigma * [[Ix^2, Ix Iy], [Ix Iy, Iy^2]]
```

Its large eigenvalue measures the dominant gradient direction. Its small
eigenvalue is large only when meaningful gradient energy exists in a second
direction. E020 therefore uses:

```
score = sqrt(lambda_min(J))
```

The square root puts the score back in gradient-amplitude-like units. The
eigenvalues make the statistic rotation invariant. Tensor integration makes
it insensitive to the exact cell phase.

## Alternatives considered

### Raw local variance

Keeping e019's signal and merely choosing thresholds adaptively would remove
the fixed 8-bit constants, but it would not remove the paper-edge ambiguity.
Morphology would still carry the semantic burden.

### Difference of Gaussians or band-pass energy

A cell-scale band-pass is cheap and suppresses slow brightness changes. A
sharp paper edge, however, has energy over a wide range of spatial
frequencies. It still requires a shape or occupancy test. This remains a good
candidate if tensor computation proves too expensive.

### Autocorrelation or spectral peaks

The printed field has cell-scale correlation, but a solid random-cell pattern
does not create a narrow spectral line in every small window. Rotation and
small fragments make local spectral estimation less stable, while a spectral
method starts to overlap with the downstream pitch/angle stage.

### Harris or determinant response

The determinant also measures two-dimensional gradient energy, but it scales
quadratically with contrast and can be dominated by very strong corners. The
minor eigenvalue has the simpler interpretation: how much energy exists in the
weaker direction.

## Final pipeline

1. Convert greyscale input to an 8-bit-equivalent intensity range.
2. Block-average to approximately four pixels per code cell. The real-scan
   comparison uses two pixels per cell.
3. Compute scale-normalized Gaussian derivatives.
4. Smooth the three tensor products over `0.30` cell, with a one-pixel lower
   bound.
5. Compute `sqrt(lambda_min)` and average it to one score per cell site.
6. Select a threshold as the larger of:
   - a 12-MAD robust estimate from the low-score half of the platen;
   - log-space Otsu separation between unmodulated material and payload.
7. Retain an active site only when at least five of its 3x3 neighbourhood are
   active. This validates density without growing the mask.
8. Label connected regions and apply the existing 9 mm2 physical area floor.

There is deliberately no hysteresis, erosion, propagation, opening, hole
filling, or post-component contrast threshold.

## Iteration history

### Initial tensor version

The first implementation integrated the tensor over `1.25` cells and used a
robust background-floor threshold. It found every normal and faint synthetic
field and rejected blank scraps, but its masks had a large integration halo.
Synthetic IoU was only about `0.52--0.69` despite perfect field recall.

The initial 3x3 density operation also expanded every qualifying site. It was
changed to validate the original active site instead:

```
region = active & (neighbour_count >= density_min)
```

This removed an avoidable one-cell growth operation.

### Support and density calibration

Calibration seeds `100--107` were used to sweep tensor support, threshold MAD,
and density. Tensor support between `0.20` and `0.75` cell, MAD multipliers from
`6` to `12`, and density requirements from `3` to `5` were examined.

The chosen point was `0.30` cell, 12 MAD, and 5-of-9. Smaller support lost too
much of the faint blurred field; larger support grew beyond field boundaries.
The higher density condition improved precision without fragmenting the
scrambled fields.

### Real-paper threshold failure

The first real e018 run appeared successful by candidate count: both detectors
found 17 components. Visual inspection showed that this was misleading. E020
candidate boxes extended through the real paper margins because the robust
noise-floor threshold was only `0.216`; actual paper stock had structure score
above the synthetic noise model.

The real score distribution made the missing model visible:

| percentile | score |
|---:|---:|
| 50 | 0.073 |
| 70 | 0.928 |
| 75 | 5.875 |
| 90 | 10.268 |

Log-space Otsu selected `2.356`, cleanly between paper texture and toner. E020
now takes the maximum of the robust floor and Otsu threshold. Re-running all
six scans produced tight field boxes and thresholds from `2.336` to `2.440`.

This failure is why the real overlays are part of the experiment. Candidate
count alone was not an adequate qualification metric.

### Ground-truth correction and held-out run

An early synthetic schedule included a real printed field smaller than the
shared 9 mm2 acceptance floor. Its intentional rejection was incorrectly
counted as segmentation recall loss. The fixture was enlarged so every truth
field is eligible.

After all choices were fixed using the 100-series seeds, seeds `200--207` were
run untouched. The results recorded in `README.md` and `build/results.csv` are
from that held-out range.

## What the experiment supports

On held-out synthetic scenes, e020 improves IoU and precision for normal dark
and white backing, torn fields, and dense nearby fields. It detects the faint
case that the absolute e019 thresholds reject. Both detectors reject the
blank-paper controls. E020 also separates the nearby dense pair that e019's
propagation merges.

On the six available real white-lid scans, e019 and e020 agree on every
component: 17, 17, 10, 10, 8, and 8. Their boxes closely align after the Otsu
correction. This demonstrates compatibility on existing material, not greater
real-world accuracy, because those scans have no exact annotation.

## Cost and scope

The tensor requires several Gaussian-filter passes and is slower than local
variance at the same reduced footing. In the observed real runs, e020 took
roughly 1.6--1.9 seconds while e019's detector took roughly 0.4--0.5 seconds;
the timings are not perfectly symmetric because e020 includes its input
reduction and the e019 timer receives the already reduced image.

Memory is the more important change. Acquisition works at two to four pixels
per cell instead of maintaining native 4800-dpi float arrays. Native samples
remain available to the downstream lattice and decode stages after candidate
selection.

E020 still assumes nominal cell pitch. It does not estimate angle, lock phase,
read pilots, or decode data. A downstream crop should include a small fixed
halo while the e020 mask remains the claim about where modulation exists.

## Remaining risks and promotion criteria

The real evidence covers one printer, scanner, paper stock, white lid, and
normal toner contrast. Dark backing, faint toner, and blank-paper controls are
synthetic. Otsu can fail if payload covers almost the whole platen or if a
second material creates another broad high-texture population.

Before replacing e019 in `paperholo.segment`, collect and annotate:

1. real dark-backing scans with substantial white margins;
2. deliberately faint and overexposed prints;
3. multiple paper stocks, including visibly fibrous stock;
4. isolated dust, scratches, text, and non-payload printed material;
5. heavily occupied platens and pieces touching the scan boundary.

Promotion should be based on pixel-mask precision/recall and candidate splits
or merges against those annotations, not candidate count or visual agreement
with e019 alone.
