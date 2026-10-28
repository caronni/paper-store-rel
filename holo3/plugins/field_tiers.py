"""The registration field's evidence tiers, and the law that keeps them
from counting the same site twice.

The field used to have one source of evidence: PHOTOMETRY.  Every cell
whose value the receiver knows contributes the linearisation of its own
sampled value against that known value, which is a rank-1 equation along
the local gradient.  That tier is sound and it is also
attenuated -- measured on sheet I against the recorded per-plane ground
truth it recovers **46%** of the displacement the printer actually made
(Pearson +0.80 per tile, +0.88 per column;
`measure/ysampler/README.md`, phase 1), even though it responds to an
INJECTED displacement at gain ~1.  And a plane with no contrast has
nothing photometric to say at all, which is what a dead band is.

Two more tiers say it a different way, and neither needs contrast:

* ANCHOR -- correlate the plane's own channel against the FORMAT'S OWN
  SITES.  The receiver knows every word and dust value before it reads
  anything, so a whole-tile template with weight at those cells and
  nowhere else is a blind, truth-independent measurement of WHERE the
  ink is.  Measured gain against an injected displacement: **1.000**
  (rms nonlinearity < 0.001 dot); against sheet I's recorded sinusoid,
  **0.947** per tile with a bootstrap interval of [0.894, 0.998] and
  **1.002** per column, at Pearson +0.912 / +0.977.  One measurement per
  tile per plane, on every tile including Y, at zero saturation.
* BLIND OFFSET -- pick a window's sampling offset by the lowest held-out
  log loss on the plane's own labels, the `measure/yask` A1 estimator.
  It works where the other two are weakest, because it asks only whether
  the READING improves, not whether a gradient or a correlation exists.

THE ATTRIBUTION LAW (project-lead ruling, binding).  No site may pay
twice.  The partition is STRUCTURAL, not a filter: it falls out of the
format's own site kinds, which are disjoint by construction and which
every window already carries.

    certified PAYLOAD cells         -> the PHOTOMETRIC tier
    FURNITURE at even site parity   -> the ANCHOR tier
    FURNITURE at odd site parity    -> the BLIND OFFSET tier

Payload is the complement of furniture in the format's own geometry and
parity is a pure function of the cell, so the three sets are pairwise
disjoint and their union is every cell the receiver knows -- pinned, not
asserted, by `test_h3_plane_fields.py`.

WHY PARITY AND NOT KIND.  Splitting word from dust looks tidier and is
wrong, in a way the format decides.  The v1 colour word renders states
{0, 3}, so **no word site carries Y** -- a word-only template has no
polarity on that plane and the anchor tier would refuse exactly the
plane this whole line exists for.  Dust cycles {1, 2, 4, 5, 6, 7} and
carries all three, so both halves need both kinds.  Site parity is the
receiver's own way of cutting one site population into two independent
halves (`calibrate.fit_window_calibration`, `local_ctx`, the anchor
lattice in `color_region_anchor`), it keeps word and dust in both
halves, and it makes the two furniture tiers genuinely independent --
which is what makes their agreement worth reading.

One consequence, stated because it is a real constraint rather than a
detail: the blind tier cannot call `calibrate.fit_window_calibration`,
because that function splits its OWN input by site parity and would find
one class empty inside a parity half.  The tier ports the estimator's
numerics (`measure/yask`, sweep offsets, score by held-out log loss of a
PAVA map) and splits its half by a second key.

Each tier's site count and weight mass is reported, and because tiers
add as normal equations, so is each tier's EFFECT: leave one out by
subtracting its equations and re-solving.

HOW A TIER'S CONTRIBUTION IS MEASURED, AND WHY (2026-08-31)
-----------------------------------------------------------
By the exact subtraction above, not by decoding with the tier switched
off and counting certificates.  That is not a preference: on every
simulation this tree currently owns, certificate-level ablation is
structurally unobtainable, because the receiver's own rescue tiers close
the page by themselves and leave no residue for a tier's absence to
show up in.  Measured, dial OFF, same page, same displacement:

    row             displaced   + faint band
    tiles.local            13            453
    refine.color           57            378
    tiles.retry           215            559
    certificates          300            300

The faint band tripled to thirty-fived the rescue work and cost NOTHING.
A gate that asks "which certificates does this tier buy back" therefore
has nothing to weigh on these stimuli, while leave-one-out weighs the
same question directly and exactly -- it is a subtraction on ``a`` and
``b``, so it needs no headroom and no second decode.

Certificate-level tier ablations are still the stronger evidence where
they are possible, and they AWAIT A STIMULUS FAMILY that no other
residue row can rescue (the yield-repin line owns that design, with
cross-row fire-count goldens).  Until such a stimulus exists, the exact
per-tier accounting here stands in for it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..lib import pava, plane_field
from ..lib.geometry import TILE_CELLS, site_hash, site_parity

#: Site kinds, as `color_model.reference_states` reports them.
KIND_WORD: int = 0
KIND_DUST: int = 1
KIND_PAYLOAD: int = -1

TIER_PHOTOMETRIC: str = "photometric"
TIER_ANCHOR: str = "anchor"
TIER_BLIND: str = "blind"
TIER_NAMES: tuple[str, ...] = (TIER_PHOTOMETRIC, TIER_ANCHOR, TIER_BLIND)

#: The anchor correlation's search radius in printed dots, per plane.
#: Project-lead ruling 2026-08-31: Y wider, C and M untouched.  §15.6
#: derives Y's >= 2.2 from a censored p95; 2.5 is the first value on this
#: grid that clears it.
ANCHOR_RADIUS_DOTS: tuple[float, float, float] = (1.5, 1.5, 2.5)
ANCHOR_STEP_DOTS: float = 0.25
#: Below this the correlation is not a measurement.  The receiver's own
#: anchor floor, carried.
ANCHOR_MIN_QUALITY: float = 0.10
#: A template needs enough sites, and both polarities, to localize.
ANCHOR_MIN_SITES: int = 24
#: What the phase-1 calibration says this kernel reads for one dot of
#: real displacement.  Measured on sheet I by moving the sampling frame a
#: known distance with the template frozen (the production situation: the
#: pose an anchor measures against is plane-COMMON and the displacement
#: is per-plane) -- slope 1.000 on C and 1.000 on M, with an rms
#: nonlinearity below 0.001 dot over a +-0.75 dot sweep.  The tier
#: divides by it, so what it contributes is in printed dots; at 1.0 that
#: division is a no-op, which is the honest state of the measurement
#: rather than a fitted correction nobody needs.
#:
#: OWED: the same calibration on Y, and the cross-check against sheet I's
#: recorded sinusoid.  Both were measured before a HALF-CELL error in the
#: instrument's own pose was found (measure/ysampler/README.md), and the
#: numbers they produced -- an anchor gain of 0.94 and a photometric gain
#: of 0.04 on Y -- are retracted.
ANCHOR_GAIN: float = 1.0
#: A measurement at the wall is a peak-lock, not a displacement: a tenth
#: of Y anchors run to whatever radius they are given (README, the
#: saturation-by-quality-quartile table).
ANCHOR_SATURATION_MARGIN_DOTS: float = 0.26
#: Fewer overlap tiles than this and the tier cannot check its own gain
#: against the photometric tier, so it refuses rather than fit noise.
MIN_GAIN_OVERLAP_TILES: int = 8
#: The ratio the check allows before it calls the two tiers inconsistent.
#: Phase 1 measured the two against the same ground truth at 0.95 and
#: 0.46, so the anchor reads about twice the photometric tier and that
#: is the photometric tier's attenuation, not the anchor's error -- this
#: is a sanity bound on the anchor, never a match requirement.
MAX_GAIN_RATIO: float = 100.0


@dataclass(frozen=True)
class SitePartition:
    """Which rows of one window belong to which tier.

    Index arrays into the window's own row order, pairwise disjoint by
    construction: a cell's ``furniture_kind`` is one value.
    """

    photometric: np.ndarray
    anchor: np.ndarray
    blind: np.ndarray

    @property
    def counts(self) -> dict[str, int]:
        return {TIER_PHOTOMETRIC: int(self.photometric.size),
                TIER_ANCHOR: int(self.anchor.size),
                TIER_BLIND: int(self.blind.size)}


def partition_sites(kinds: np.ndarray, complete: np.ndarray,
                    page_cells_yx: np.ndarray) -> SitePartition:
    """The attribution law, applied once, to one window's rows.

    ``complete`` is the receiver's own "all three planes known here" --
    furniture always, certified payload where a tile has closed.  Payload
    goes to photometry; the furniture is halved by SITE PARITY, which is
    a pure function of the cell, so no cell can reach two tiers and the
    split is the same on every capture of the same page.
    """
    kind = np.asarray(kinds, np.int64)
    known = np.asarray(complete, bool)
    cells = np.asarray(page_cells_yx, np.int64)
    parity = site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    furniture = known & (kind >= 0)
    return SitePartition(
        photometric=np.flatnonzero(known & (kind == KIND_PAYLOAD)),
        anchor=np.flatnonzero(furniture & ~parity),
        blind=np.flatnonzero(furniture & parity))


def assert_partition(partition: SitePartition, complete: np.ndarray) -> None:
    """The pin: disjoint, and together the whole known population."""
    sets = (set(partition.photometric.tolist()),
            set(partition.anchor.tolist()),
            set(partition.blind.tolist()))
    for left in range(3):
        for right in range(left + 1, 3):
            shared = sets[left] & sets[right]
            if shared:
                raise ValueError(
                    "plane field: the attribution law is broken -- "
                    f"{len(shared)} site(s) reach two tiers")
    union = sets[0] | sets[1] | sets[2]
    expected = set(np.flatnonzero(np.asarray(complete, bool)).tolist())
    if union != expected:
        raise ValueError(
            "plane field: the tiers do not partition the known cells -- "
            f"{len(expected - union)} unattributed, "
            f"{len(union - expected)} attributed but not known")


def offset_grid(radius_dots: float,
                step_dots: float = ANCHOR_STEP_DOTS) -> np.ndarray:
    """Candidate displacements, ``(S, 2)`` as (dx, dy) in printed dots."""
    reach = max(1, int(round(float(radius_dots) / float(step_dots))))
    axis = np.arange(-reach, reach + 1, dtype=np.float64) * float(step_dots)
    grid_y, grid_x = np.meshgrid(axis, axis, indexing="ij")
    return np.stack((grid_x.ravel(), grid_y.ravel()), axis=1), axis.size


def weighted_ncc(values: np.ndarray, template: np.ndarray,
                 weights: np.ndarray) -> np.ndarray:
    """Weighted normalized cross-correlation, one score per candidate.

    ``values`` is ``(S, N)`` -- the plane sampled at N sites for each of
    S candidate displacements -- against one ``(N,)`` template.  This is
    the same functional the receiver's own ``xcorr_offset_ncc`` computes,
    on a SPARSE site set instead of a dense pixel block: the template is
    ~120 known cells out of a tile's 4,096, so correlating whole blocks
    would spend 34 times the work to use the same evidence.
    """
    w = np.asarray(weights, np.float64)
    total = float(w.sum()) + 1e-9
    centred_template = np.asarray(template, np.float64)
    centred_template = centred_template - float(
        (centred_template * w).sum()) / total
    template_norm = np.sqrt(
        float((centred_template * centred_template * w).sum())) + 1e-9
    sampled = np.asarray(values, np.float64)
    centred = sampled - (sampled * w).sum(axis=1, keepdims=True) / total
    numerator = (centred * centred_template * w).sum(axis=1)
    norm = np.sqrt((centred * centred * w).sum(axis=1))
    return numerator / (norm * template_norm + 1e-9)


def _parabola(left: float, centre: float, right: float) -> float:
    denominator = left - 2.0 * centre + right
    if abs(denominator) < 1e-12:
        return 0.0
    return float(np.clip((left - right) / (2.0 * denominator), -0.5, 0.5))


def peak_offset(scores: np.ndarray, side: int, step_dots: float,
                grid: np.ndarray) -> tuple[np.ndarray, float]:
    """The correlation peak, refined by a parabola along each axis."""
    square = scores.reshape(side, side)
    row, column = np.unravel_index(int(np.argmax(square)), square.shape)
    shift_y = (_parabola(square[row - 1, column], square[row, column],
                         square[row + 1, column])
               if 0 < row < side - 1 else 0.0)
    shift_x = (_parabola(square[row, column - 1], square[row, column],
                         square[row, column + 1])
               if 0 < column < side - 1 else 0.0)
    base = grid[row * side + column]
    return (np.asarray((base[0] + shift_x * step_dots,
                        base[1] + shift_y * step_dots), np.float64),
            float(square[row, column]))


@dataclass(frozen=True)
class AnchorObservation:
    """One tile's worth of anchor evidence for one plane."""

    tile_code: int
    delta_dots_xy: np.ndarray
    quality: float
    n_sites: int
    saturated: bool


def anchor_offsets(sample, template_bits: np.ndarray,
                   weights: np.ndarray, radius_dots: float,
                   step_dots: float = ANCHOR_STEP_DOTS,
                   ) -> tuple[np.ndarray, float] | None:
    """Correlate one plane against one block of KNOWN cells.

    ``sample(offsets)`` takes the ``(S, 2)`` candidate grid in printed
    dots and returns the ``(S, N)`` plane values at the N template sites
    displaced by each candidate.  The caller owns the geometry; this owns
    the correlation and nothing else.
    """
    bits = np.asarray(template_bits, np.float64)
    w = np.asarray(weights, np.float64)
    live = bits[w > 0.0]
    if live.size < ANCHOR_MIN_SITES or live.min() == live.max():
        return None
    grid, side = offset_grid(radius_dots, step_dots)
    values = sample(grid)
    if values is None:
        return None
    scores = weighted_ncc(values, 1.0 - bits, w)
    if not np.all(np.isfinite(scores)):
        return None
    return peak_offset(scores, side, step_dots, grid)


def saturated(delta_dots_xy: np.ndarray, radius_dots: float) -> bool:
    """At the wall is a peak-lock, not a displacement."""
    return bool(np.max(np.abs(np.asarray(delta_dots_xy, np.float64)))
                >= radius_dots - ANCHOR_SATURATION_MARGIN_DOTS)


def anchor_equations(observations: tuple[AnchorObservation, ...],
                     tiles_yx: tuple[int, int],
                     gain: float = ANCHOR_GAIN,
                     min_quality: float = ANCHOR_MIN_QUALITY,
                     ) -> plane_field.NormalEquations:
    """The anchor tier's rank-2 pseudo-observations, in printed dots.

    Each accepted tile contributes ONE observation of the delta itself,
    weighted by its correlation quality.  The measurement is divided by
    the phase-1 gain, which is what puts a correlation peak on the same
    scale as a photometric residual so the two can be added.
    """
    kept = tuple(o for o in observations
                 if o.quality >= min_quality and not o.saturated)
    if not kept:
        return plane_field.NormalEquations.empty(tiles_yx)
    codes = np.asarray([o.tile_code for o in kept], np.int64)
    deltas = np.stack([o.delta_dots_xy for o in kept]) / float(gain)
    weights = np.asarray([o.quality for o in kept], np.float64)
    return plane_field.observe(codes, deltas, weights, tiles_yx)


#: The blind tier's offset sweep, in printed dots.  `measure/yask` swept
#: +-2 dots in 0.25-dot steps and found the printer's own +-0.4 dot wave;
#: this keeps the step and trims the reach to the anchor tier's, so the
#: two tiers cannot disagree merely about how far they were allowed to
#: look.
BLIND_STEP_DOTS: float = 0.25
#: Below this many labels in a half there is no map to fit and no
#: held-out set to score it on, so the window declines.
BLIND_MIN_PER_HALF: int = 24
BLIND_MIN_PER_CLASS: int = 4
#: A sweep that does not beat its own centre is not a measurement.
BLIND_MIN_IMPROVEMENT: float = 1e-4
#: The blind tier's own weight floor.  Its weight is a log-loss
#: improvement, not a correlation coefficient, so ANCHOR_MIN_QUALITY is
#: meaningless against it -- see `blind_equations`.
BLIND_MIN_WEIGHT: float = 1e-12


def split_key(page_cells_yx: np.ndarray) -> np.ndarray:
    """A SECOND independent halving, inside the blind tier's own half.

    ``calibrate.fit_window_calibration`` splits its input by site parity,
    and the blind tier's sites are already one parity class, so that
    function would find one of its classes empty.  The tier keeps the
    estimator and supplies its own key: the site hash's next bit.
    """
    cells = np.asarray(page_cells_yx, np.int64)
    return ((site_hash(cells[:, 0], cells[:, 1]) >> 1) & 1).astype(bool)


def blind_logloss(values: np.ndarray, labels: np.ndarray,
                  split: np.ndarray) -> float | None:
    """`measure/yask`'s A1 objective: held-out log loss of a PAVA map.

    The window's own known labels are halved; a monotone map is fitted
    on one half and scored on the other.  Comparing that number across
    sampling offsets compares models on one fixed held-out set, which is
    the ordinary use of a held-out score and is blind -- the labels are
    the format's own.
    """
    scores = _scores(values)
    search = ~split
    held = split
    search_labels = np.asarray(labels, np.int8)[search]
    held_labels = np.asarray(labels, np.int8)[held]
    if (search_labels.size < BLIND_MIN_PER_HALF
            or held_labels.size < BLIND_MIN_PER_HALF):
        return None
    ones = int(search_labels.sum())
    if min(ones, int(search_labels.size) - ones) < BLIND_MIN_PER_CLASS:
        return None
    knots, probs = pava._pava_nodes(scores[search], search_labels)
    probability = np.clip(
        np.interp(scores[held], knots, probs), 1e-6, 1.0 - 1e-6)
    return float(-np.mean(
        held_labels * np.log(probability)
        + (1 - held_labels) * np.log1p(-probability)))


def _scores(values: np.ndarray) -> np.ndarray:
    """`calibrate.window_scores`, on one plane's sampled values."""
    means = np.asarray(values, np.float64)
    midpoint = float(np.median(means))
    spread = max(float(np.abs(means - midpoint).mean()), 1e-6)
    return (midpoint - means) / spread


def blind_offset(sample, labels: np.ndarray, split: np.ndarray,
                 radius_dots: float,
                 step_dots: float = BLIND_STEP_DOTS,
                 ) -> tuple[np.ndarray, float] | None:
    """One window's sampling offset, chosen blind on its own labels.

    ``sample(offset)`` returns the plane's values at this tier's sites
    displaced by one ``(dx, dy)`` in printed dots.  The sweep is along x
    only, which is the axis the printer's registration wanders on (the
    AltaLink sinusoid) and the axis `measure/yask` measured; a y sweep
    would triple the cost for an axis no measurement has found moving.
    """
    reach = max(1, int(round(float(radius_dots) / float(step_dots))))
    shifts = np.arange(-reach, reach + 1, dtype=np.float64) * step_dots
    losses: list[float] = []
    for shift in shifts:
        loss = blind_logloss(
            sample(np.asarray((shift, 0.0), np.float64)), labels, split)
        losses.append(np.inf if loss is None else loss)
    scores = np.asarray(losses, np.float64)
    if not np.any(np.isfinite(scores)):
        return None
    best = int(np.argmin(scores))
    centre = int(np.argmin(np.abs(shifts)))
    if not np.isfinite(scores[centre]):
        return None
    improvement = float(scores[centre] - scores[best])
    if improvement < BLIND_MIN_IMPROVEMENT:
        return np.zeros(2, np.float64), 0.0
    return (np.asarray((shifts[best], 0.0), np.float64),
            improvement)


def blind_equations(observations: tuple[AnchorObservation, ...],
                    tiles_yx: tuple[int, int],
                    ) -> plane_field.NormalEquations:
    """The blind-offset tier, in the same rank-2 form and the same unit.

    The estimator differs -- held-out log loss on the plane's own labels,
    `measure/yask` A1 -- but what it produces is the same object, "this
    plane's sampler should move by this much here", already in printed
    dots.  No gain divides it: the estimator IS the sampler, so what it
    finds is what the sampler wants.

    ITS WEIGHT IS NOT AN NCC QUALITY.  An anchor's weight is a
    correlation coefficient, order 0.5-1.0, and :data:`ANCHOR_MIN_QUALITY`
    floors it at 0.10.  A blind offset's weight is a HELD-OUT LOG LOSS
    IMPROVEMENT divided over the window's tiles -- orders of magnitude
    smaller, and a different quantity entirely.  Passing it through the
    anchor floor silently discarded every blind observation ever made:
    measured on the displaced sim, the estimator returned 163 real
    offsets over 69 windows and NONE of them reached the fit.  The tier
    keeps its own floor, and it is simply "positive": an offset that
    bought nothing already returns zero weight upstream.

    What is NOT settled here is how a log-loss improvement should be
    scaled against a correlation coefficient so the two tiers carry
    commensurate weight in one solve.  This admits the evidence at its
    own natural size, which is small, and leaves that scaling to a
    measurement rather than inventing a factor.
    """
    return anchor_equations(observations, tiles_yx, gain=1.0,
                            min_quality=BLIND_MIN_WEIGHT)


def gain_check(tiers: dict[str, plane_field.NormalEquations]) -> dict:
    """May the anchor tier contribute to THIS page's fit for THIS plane?

    The ruling: the tier refuses per plane when too few overlap sites
    existed to fit its gain.  Overlap is counted per LANE-PAGE, over
    tiles where the anchor tier and the photometric tier both carry
    evidence -- which is what lets a page calibrate on its healthy region
    and still correct a band where photometry has nothing to say.  A page
    with no photometric evidence at all gives the anchor nothing to check
    itself against, and the tier declines rather than fit unchecked.

    What the check does NOT do is rescale the anchor onto the photometric
    tier's scale.  Phase 1 measured both against sheet I's recorded
    per-plane ground truth and the anchor reads 0.95 where the
    photometric tier reads 0.46, so matching the anchor to it would
    throw the better measurement away.
    The anchor carries :data:`ANCHOR_GAIN`, measured against ground
    truth; this is a sanity bound and a refusal, nothing more.
    """
    anchor = tiers.get(TIER_ANCHOR)
    photometric = tiers.get(TIER_PHOTOMETRIC)
    if anchor is None:
        return {"tier": TIER_ANCHOR, "present": False, "refused": False}
    if photometric is None:
        return {
            "tier": TIER_ANCHOR, "present": True, "refused": True,
            "overlap_tiles": 0,
            "reason": "this lane-page has no photometric evidence at all, "
                      "so the anchor tier has nothing to check its gain "
                      "against and declines"}
    overlap = int(np.count_nonzero(
        (anchor.mass > 0.0) & (photometric.mass > 0.0)))
    out: dict = {"tier": TIER_ANCHOR, "present": True,
                 "overlap_tiles": overlap,
                 "refused": overlap < MIN_GAIN_OVERLAP_TILES}
    if out["refused"]:
        out["reason"] = (
            f"only {overlap} tile(s) carry both anchor and photometric "
            f"evidence; {MIN_GAIN_OVERLAP_TILES} are needed to fit the "
            f"anchor's gain, so the tier declines")
    return out


def observed_ratio(anchor_delta: np.ndarray,
                   photometric_delta: np.ndarray) -> float | None:
    """What the two tiers' fitted deltas say about each other.

    Reported, never applied -- see :func:`gain_check`.
    """
    left = np.asarray(anchor_delta, np.float64).ravel()
    right = np.asarray(photometric_delta, np.float64).ravel()
    good = np.isfinite(left) & np.isfinite(right)
    denominator = float(np.dot(right[good], right[good]))
    if denominator <= 0.0:
        return None
    return float(np.dot(left[good], right[good]) / denominator)


def leave_one_out(tiers: dict[str, plane_field.NormalEquations],
                  solve) -> dict[str, dict]:
    """Each tier's measured EFFECT on the fit it took part in.

    Tiers add as normal equations, so removing one is a subtraction and
    the comparison is exact -- no re-measurement, no re-derivation.
    """
    present = {name: equations for name, equations in tiers.items()
               if float(equations.mass.sum()) > 0.0}
    if not present:
        return {}
    joint = plane_field.combine(*present.values())
    full, _support = solve(joint)
    out: dict[str, dict] = {}
    for name in present:
        others = [equations for other, equations in present.items()
                  if other != name]
        if not others:
            out[name] = {"sole_tier": True}
            continue
        without, _mass = solve(plane_field.combine(*others))
        difference = np.hypot(full[..., 0] - without[..., 0],
                              full[..., 1] - without[..., 1])
        out[name] = {
            "sites": int(present[name].mass.sum()),
            "weight_mass": float(present[name].a[..., 0, 0].sum()),
            "median_effect_dots": float(np.median(difference)),
            "max_effect_dots": float(difference.max()),
        }
    return out


def tile_codes_of(page_cells_yx: np.ndarray,
                  tiles_yx: tuple[int, int]) -> np.ndarray:
    return plane_field.tile_codes(page_cells_yx, tiles_yx, TILE_CELLS)
