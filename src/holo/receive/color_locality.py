"""P0: per-window photometric maps — the stack's A3 arm.

RECEIVE-DESIGN §6.2a.  Color photometry is per-REGION today (one QDA for
a whole page) while K's has been per-WINDOW since ``detect.fit_calibration``
("exact per-window PAVA or explicitly refuse").  The measured reason that
matters is the HP channel's cm-scale C/M mottle plus process banding
(COLOR-UPLIFT-PLAN §1): a page-global Gaussian model cannot track a gain
that drifts across the sheet, so its out-of-sample confidence is wrong in
a spatially structured way.

The family is the smallest correction that expresses "this window's
photometry is offset from the region's": one gain and one offset per RGB
channel,

    x'_c = g_c * x_c + o_c,        6 parameters per window,

fitted by weighted least squares toward the REGION QDA's own class means
— the map answers "what affine transform would put this window's labelled
cells on top of the region model's classes?", which is exactly the
quantity a refit region QDA can then exploit.

Five choices carry the arm, each for a measured reason:

* **An ADAPTIVE halo** (PK4.1 ruling, measured).  A window uses its OWN
  labelled cells whenever they clear the fit floors, and pools its
  neighbours' only on STARVATION — the halo is a fallback for windows
  that cannot identify six parameters alone, never a standing prior.
  PK4 swept the halo as a fixed weight over {0.25, 0.5, 1.0} and measured
  a monotone axis (row means +14.7 / +9.0 / +5.7 addresses), with an
  out-of-grid halo-0 diagnostic at +27: pooling a neighbour's cells
  dilutes exactly the window-scale drift the arm exists to track, because
  a neighbour's cells are evidence about the NEIGHBOUR's photometry.  So
  the weight is gone from the family; the machinery stays for the
  starved-window case this corpus never produced (every PK4 refusal was
  ``validation_gate_failed``, not a starvation reason — small windows on
  scrap/confetti material are where it should still matter).  Pooling,
  when it happens, is at :data:`WINDOW_PHOT_HALO_POOL_WEIGHT` = 1.0: a
  window that cannot see enough of itself has no basis for discounting
  what it can see.
* **Class balance.**  PK3's measured lesson is now law: known furniture is
  ~45% W and ~39% one dust state against a uniform payload field, so an
  unweighted fit would fold the furniture prior into the map.  The fit
  weights give every REPRESENTED state equal total mass, exactly
  :func:`color_calibration.class_balanced_weights` generalized to
  fractional base weights (and bit-identical to it when every base weight
  is 1, which is every fit at the frozen pooling weight).
* **Shrinkage toward identity.**  ``g <- (n_eff*g + L)/(n_eff + L)`` and
  ``o <- n_eff*o/(n_eff + L)`` with ``L =`` :data:`WINDOW_PHOT_PRIOR_LABELS`
  effective labels.  A window with little evidence returns approximately
  the identity map; a window with plenty keeps its fit.  There is no
  discontinuity at the floor.
* **Refusals are bit-exact nulls** (risk R3).  A refused window's feature
  array is passed through as the SAME OBJECT — never an identity
  transform, never a copy — so "no window adopted" is literally today's
  receiver, down to float re-association.  The same holds one level up:
  a region whose arm is refused gets its OWN feature tuple back, and the
  mapped arrays are never even allocated.
* **One per-window gate, and NO region applicability floor.**  A window's
  map must strictly improve the INCUMBENT model's class-balanced NLL on
  that window's OWN held-out labels before the region-level three-way
  comparison is offered the candidate.  There is no second, region-level
  applicability statistic: PK4.1 and PK4.2 built two of them (raw map
  dispersion, and its normalized variance-ratio successor), measured both
  on all 27 lanes of two captures, and NEITHER separates the lanes A3
  helps from the lanes it taxes — the requirement is contradictory by 15x
  (COLOR-UPLIFT-MEASUREMENTS §6.3/§7.4, retired at §12).  The applicability
  question is answered by SCHEDULING instead: A3 is unreachable from the
  standard ladder and runs only inside its own supplemental lane, where
  the per-address retirement law makes it monotone by construction
  (RECEIVE-DESIGN §6.2a, ``color_stack.UPLIFT_ARM_A3``).

Refusal reasons reuse K's vocabulary verbatim
(``detect.fit_calibration`` / ``detect.fit_context``):
``insufficient_search_support`` (fewer than three represented states — six
parameters are not identifiable from two class means),
``search_class_starved`` (too few labelled search cells),
``heldout_starved`` (too few own-window held-out labels),
``validation_gate_failed`` (the per-window pre-gate); adoption is
``adopted``.  The region-level verdicts are their own small vocabulary:
``no_window_maps``, ``region_gate_failed``, ``adopted``.

Kind-agnostic by construction: the map transforms RGB features, so cmy7
(7 states) and cmy8 (8 states) run the identical code, and the region QDA
that supplies the targets is whichever one the incumbent arm fitted.

Deterministic and RNG-free: bboxes, weights, and a 2x2 weighted normal
equation per channel, evaluated in canonical window order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.special import logsumexp

from . import color_detect
from .color_anchoring import _Rows
from .color_calibration import class_balanced_weights
from .color_fitting import _OwnerSelection


# SWEPT CONSTANT.  Provenance: COLOR-UPLIFT-MEASUREMENTS §5.2 (PK4's
# nine-point halo x prior grid), re-confirmed on the adaptive-halo
# landscape in §6.2.
#
# The shrinkage prior's strength, in EFFECTIVE (base-weighted) labels: a
# window fitted from exactly this much evidence lands halfway between its
# own fit and the identity map.  20 was the best on-grid point of PK4's
# sweep inside the winning halo row (+17 / +15 / +12 for 20 / 40 / 80)
# and is re-confirmed on the adaptive-halo landscape in §6.2.
WINDOW_PHOT_PRIOR_LABELS: Final = 20.0
# The weight a borrowed neighbour cell carries WHEN the halo is pooled at
# all — which happens only for a window too starved to identify its own
# six parameters (see the module note).  Not a swept knob: a window that
# cannot see enough of itself has no basis for discounting what it can.
WINDOW_PHOT_HALO_POOL_WEIGHT: Final = 1.0
# A loss that was never measured (the campaign's standing convention,
# ``color_context.CONTEXT_NLL_UNMEASURED`` /
# ``color_conditioning.CONDITIONING_NLL_UNMEASURED``): negative, never
# NaN, so a summary record stays ``==``-comparable and a skipped
# measurement is never readable as a very good 0.0.
NLL_UNMEASURED: Final = -1.0
# The P6 preview's population cap (report-only; see
# :func:`cert_population_preview`).  Chosen as a round number well above
# the smallest measured cert population that still resolves an NLL
# difference of order 1e-2, and far below the ~4M cells a late-lane
# three-plane cmy8 region carries.
CERT_PREVIEW_MAX_CELLS: Final = 250_000

# Floors.  The search floor is a raw label count over the fit population;
# the state floor is identifiability (W plus at least two inked states, so
# the six parameters see at least three distinct class means); the
# held-out floor is the pre-gate's own population and is OWN-WINDOW only —
# a gate scored on a neighbour's cells would not be measuring this window.
WINDOW_PHOT_MIN_SEARCH_LABELS: Final = 40
WINDOW_PHOT_MIN_STATES: Final = 3
WINDOW_PHOT_MIN_HELDOUT: Final = 20
# The standing 1e-9 strict-improvement convention (color_stack's three-way
# gate, color_calibration's head gate, detect.fit_context).
WINDOW_PHOT_GATE_SLACK: Final = 1e-9
# A channel whose weighted variance is below this carries no slope
# information at all (a window that saw one flat tone).  The regression
# then degenerates to its exact pure-offset limit rather than dividing by
# a near-zero — shrinkage would pull a wild gain back, but never reliably.
WINDOW_PHOT_MIN_VARIANCE: Final = 1e-12

REASON_ADOPTED: Final = "adopted"
REASON_SEARCH_STARVED: Final = "search_class_starved"
REASON_STATE_SUPPORT: Final = "insufficient_search_support"
REASON_HELDOUT_STARVED: Final = "heldout_starved"
REASON_GATE_FAILED: Final = "validation_gate_failed"
# Region-level verdicts (the arm as a whole, not one window).
REASON_NO_WINDOW_MAPS: Final = "no_window_maps"
REASON_REGION_GATE_FAILED: Final = "region_gate_failed"

def _token_number(value: float) -> str:
    """``0.02 -> '0p02'``: a policy token may not carry a bare dot."""
    return f"{value:g}".replace(".", "p").replace("-", "m")


@dataclass(frozen=True, slots=True)
class WindowPhotometryConfig:
    """A3's one swept constant, as an explicit argument.

    Passing it rather than reading a module global keeps
    :func:`fit_window_photometry` a pure function of its inputs — a swept
    run and the frozen path run literally the same code — and a sweep
    reaches it as lane-scoped configuration
    (``color_stack.StackConfig``), never through the environment.
    """

    prior_labels: float = WINDOW_PHOT_PRIOR_LABELS

    def __post_init__(self) -> None:
        prior = float(self.prior_labels)
        if not np.isfinite(prior) or prior <= 0.0:
            raise ValueError(
                "color window photometry: prior labels must be positive")
        object.__setattr__(self, "prior_labels", prior)

    @property
    def policy_token(self) -> str:
        """``winphot-gainoffset-adaptivehalo-shrink<L>``."""
        return ("winphot-gainoffset-adaptivehalo"
                f"-shrink{_token_number(self.prior_labels)}")


@dataclass(frozen=True, slots=True)
class WindowMap:
    """One window's per-RGB-channel gain and offset."""

    gains: np.ndarray                # (3,) float64
    offsets: np.ndarray              # (3,) float64

    def apply(self, features: np.ndarray) -> np.ndarray:
        """Return ``features * g + o``; pure, shape-preserving ``(N, 3)``."""
        values = np.asarray(features, np.float64)
        if values.ndim != 2 or values.shape[1] != self.gains.size:
            raise ValueError(
                "color window photometry: features must have shape (N, C)")
        return values * self.gains + self.offsets


@dataclass(frozen=True, slots=True)
class WindowMapFit:
    """One window's decision with the counts that produced it."""

    ordinal: int
    window_map: WindowMap | None
    reason: str
    n_own: int
    n_halo: int
    n_states: int
    n_heldout: int
    n_effective: float
    identity_nll: float | None
    candidate_nll: float | None

    @property
    def accepted(self) -> bool:
        return self.window_map is not None

    @property
    def pooled(self) -> bool:
        """True when this window had to borrow its neighbours' labels."""
        return self.n_halo > 0


@dataclass(frozen=True, slots=True)
class WindowPhotometrySummary:
    """A3's per-region verdict, as ONE published record.

    Lives here rather than in ``color_payload``'s region dataclass
    because these are A3's invariants (and ``color_payload`` is at its
    1000-line ceiling): every window is accounted for exactly once by the
    reason histogram, the published constant is one a fit could actually
    have used, and an unmeasured NLL is negative rather than a
    plausible-looking 0.0.

    ``accepted == 0`` IS "no window earned a map", which is a different
    fact from "maps were fitted and the region refused them" —
    :attr:`reason` carries the region-level verdict.  The ``cert_*``
    fields are the P6 PREVIEW (report-only, gates nothing): the same
    region comparison scored on prior-barrier CERT-LABELED payload cells
    instead of held-out furniture.
    """

    accepted: int = 0
    refused: int = 0
    reasons: tuple[tuple[str, int], ...] = ()
    reason: str = ""
    adopted: bool = False
    pooled: int = 0
    prior_labels: float = 0.0
    cert_cells: int = 0
    cert_incumbent_nll: float = NLL_UNMEASURED
    cert_mapped_nll: float = NLL_UNMEASURED

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in (
                self.accepted, self.refused, self.pooled, self.cert_cells)):
            raise ValueError("color payload: invalid window map counts")
        if type(self.adopted) is not bool:
            raise TypeError(
                "color payload: window photometry adoption must be a bool")
        if not isinstance(self.reason, str):
            raise TypeError(
                "color payload: window photometry reason must be a string")
        rows = tuple(self.reasons)
        if (any(not isinstance(name, str) or type(count) is not int
                or count <= 0 for name, count in rows)
                or sum(count for _name, count in rows)
                != self.accepted + self.refused):
            raise ValueError(
                "color payload: window map reasons must count every window")
        object.__setattr__(self, "reasons", rows)
        # Every float is finite, the CONSTANT is nonnegative, and the two
        # MEASUREMENTS are nonnegative or the unmeasured sentinel.
        for name in ("prior_labels", "cert_incumbent_nll",
                     "cert_mapped_nll"):
            value = float(getattr(self, name))
            measured = name != "prior_labels"
            if not np.isfinite(value) or (
                    value < 0.0
                    and not (measured and value == NLL_UNMEASURED)):
                raise ValueError(
                    "color payload: invalid window photometry "
                    f"{name} ({value!r})")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class WindowPhotometryResult:
    """The A3 arm's per-window outcome for one region.

    ``features`` is the mapped feature tuple, and ONLY when the arm is
    offerable: with no window accepted the caller gets its OWN tuple
    object back (risk R3), and the mapped arrays are never allocated at
    all.  ``arm_reason`` is empty exactly when ``features`` is a new
    mapped tuple the region gate should now judge.
    """

    features: tuple[np.ndarray, ...]
    fits: tuple[WindowMapFit, ...]
    accepted: int
    refused: int
    pooled: int
    reasons: tuple[tuple[str, int], ...]
    arm_reason: str


def _window_bboxes(row_tuple: tuple[_Rows, ...]) -> np.ndarray:
    """``(N, 4)`` inclusive ``(y0, y1, x0, x1)`` page-cell bounds."""
    bounds = np.empty((len(row_tuple), 4), np.int64)
    for index, row in enumerate(row_tuple):
        cells = np.asarray(row.page_cells_yx, np.int64)
        if cells.size == 0:
            bounds[index] = (0, -1, 0, -1)
            continue
        bounds[index] = (
            cells[:, 0].min(), cells[:, 0].max(),
            cells[:, 1].min(), cells[:, 1].max())
    return bounds


def _halo_membership(bounds: np.ndarray) -> np.ndarray:
    """``(N, N)`` bool: is window ``j`` in window ``i``'s halo?

    Window ``i``'s bbox is dilated by its OWN height and width per side —
    a window borrows from the neighbourhood its own extent defines, so a
    dense small-window region and a sparse large-window one both pool
    "roughly the adjacent ring" without a pitch- or dpi-dependent
    constant.  The diagonal is False: own cells are not halo cells.
    """
    empty = bounds[:, 1] < bounds[:, 0]
    height = bounds[:, 1] - bounds[:, 0]
    width = bounds[:, 3] - bounds[:, 2]
    y0 = bounds[:, 0] - height
    y1 = bounds[:, 1] + height
    x0 = bounds[:, 2] - width
    x1 = bounds[:, 3] + width
    overlap = (
        (bounds[None, :, 0] <= y1[:, None])
        & (bounds[None, :, 1] >= y0[:, None])
        & (bounds[None, :, 2] <= x1[:, None])
        & (bounds[None, :, 3] >= x0[:, None])
    )
    overlap &= ~empty[:, None]
    overlap &= ~empty[None, :]
    np.fill_diagonal(overlap, False)
    return overlap


def balanced_base_weights(
    states: np.ndarray,
    base: np.ndarray,
) -> np.ndarray:
    """Class-balanced weights over a population with fractional base mass.

    Every REPRESENTED state receives equal total weight and the
    population's total mass is preserved at ``base.sum()`` — so ``n_eff``
    means "effective labels" both before and after balancing, and the
    shrinkage prior is measured in the same unit as the label floors.

    With ``base`` all ones this is bit-identical to
    :func:`color_calibration.class_balanced_weights` (pinned in-suite),
    which is every fit at the frozen pooling weight; the generalization
    exists because the pooling weight is a constant, not a law.
    """
    labels = np.asarray(states, np.int64)
    mass = np.bincount(
        labels, weights=np.asarray(base, np.float64),
        minlength=int(labels.max(initial=-1)) + 1)
    per_row = np.where(
        mass[labels] > 0.0, base / np.where(mass[labels] > 0.0,
                                            mass[labels], 1.0), 0.0)
    total = float(per_row.sum())
    if total <= 0.0:
        return np.zeros(labels.size, np.float64)
    return per_row * (float(np.sum(base)) / total)


def _weighted_affine(
    features: np.ndarray,
    targets: np.ndarray,
    weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-channel weighted least squares ``t ~ g*x + o``.

    The exact 2x2 normal-equation solution, written as the centred
    covariance ratio so a flat channel degenerates to its pure-offset
    limit instead of dividing by a near-zero.  The gain and offset
    expressions are PK4's, character for character: they are what the
    corpus was measured with.
    """
    total = float(np.sum(weights))
    mean_x = (weights @ features) / total
    mean_t = (weights @ targets) / total
    var_x = (weights @ (features * features)) / total - mean_x * mean_x
    cov_xt = (weights @ (features * targets)) / total - mean_x * mean_t
    informative = var_x > WINDOW_PHOT_MIN_VARIANCE
    gains = np.where(
        informative,
        cov_xt / np.where(informative, var_x, 1.0),
        1.0)
    offsets = mean_t - gains * mean_x
    return gains, offsets


def _balanced_nll(
    model: color_detect.ColorQDAModel,
    features: np.ndarray,
    states: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Class-balanced held-out NLL of ``model`` on one window's rows."""
    scores = color_detect.qda_log_scores(model, features)
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    chosen = normalized[np.arange(states.size), states]
    return float(-np.sum(weights * chosen) / float(np.sum(weights)))


def cert_population_preview(
    incumbent: color_detect.ColorQDAModel,
    mapped: color_detect.ColorQDAModel,
    selection: _OwnerSelection,
    incumbent_features: tuple[np.ndarray, ...],
    mapped_features: tuple[np.ndarray, ...],
) -> tuple[int, float, float]:
    """P6 PREVIEW (report-only): the region gate on CERTIFIED cells.

    Both of A3's gates measure furniture, which is a registered
    limitation whose named fix is P6 (certificate-fed populations).  A
    region already carries the P6 population as labels — prior-barrier
    certified payload cells enter ``_OwnerSelection`` with furniture kind
    ``-1`` — so the counterfactual "would the region gate have ruled the
    same way on DEPLOYMENT cells?" costs two QDA scorings and gates
    nothing.  Returns ``(n_cells, incumbent_nll, mapped_nll)`` with the
    same class-balanced convention the real gates use; ``n_cells == 0``
    when the region has no certified payload labels (all of lane 0).
    """
    rows = np.flatnonzero(np.asarray(selection.kinds, np.int64) == -1)
    n_cells = int(rows.size)
    if n_cells == 0:
        return 0, NLL_UNMEASURED, NLL_UNMEASURED
    # BOUNDED, and for a measured reason: a three-plane cmy8 page carries
    # ~4M certified payload cells per region by the late lanes, and
    # scoring all of them through two QDAs costs about a GiB of transient
    # per worker — enough to eat the ladder's own memory saving
    # (COLOR-UPLIFT-MEASUREMENTS §6.6).  A report-only diagnostic may not
    # do that, so the population is subsampled by a deterministic stride
    # over its canonical (page, y, x) order.  The estimate is a mean, the
    # stride is content-independent, and nothing gates on the number.
    if n_cells > CERT_PREVIEW_MAX_CELLS:
        rows = rows[::-(-n_cells // CERT_PREVIEW_MAX_CELLS)]
    states = np.asarray(selection.states, np.int64)[rows]
    weights = class_balanced_weights(states)
    return (
        n_cells,
        _balanced_nll(
            incumbent, selection.gather(incumbent_features)[rows],
            states, weights),
        _balanced_nll(
            mapped, selection.gather(mapped_features)[rows],
            states, weights),
    )


def _fit_one_window(
    model: color_detect.ColorQDAModel,
    config: WindowPhotometryConfig,
    ordinal: int,
    known: np.ndarray,
    targets: np.ndarray,
    states: np.ndarray,
    own_search: np.ndarray,
    own_heldout: np.ndarray,
    halo: np.ndarray,
) -> WindowMapFit:
    """Fit and pre-gate ONE window's map; never raises on starvation."""
    n_heldout = int(np.count_nonzero(own_heldout))

    def represented(rows: np.ndarray) -> np.ndarray:
        return np.unique(states[rows])

    def identifiable(present: np.ndarray) -> bool:
        return bool(
            present.size >= WINDOW_PHOT_MIN_STATES
            and np.count_nonzero(present > 0) >= 2
            and np.any(present == 0))

    # THE ADAPTIVE HALO: own labels first, neighbours only on starvation.
    own_present = represented(own_search)
    n_own = int(np.count_nonzero(own_search))
    if n_own >= WINDOW_PHOT_MIN_SEARCH_LABELS and identifiable(own_present):
        fit_rows, present, n_halo = own_search, own_present, 0
    else:
        fit_rows = own_search | halo
        present = represented(fit_rows)
        n_halo = int(np.count_nonzero(halo))
    n_states = int(present.size)

    def refused(reason: str, n_effective: float = 0.0) -> WindowMapFit:
        return WindowMapFit(
            ordinal=ordinal, window_map=None, reason=reason, n_own=n_own,
            n_halo=n_halo, n_states=n_states, n_heldout=n_heldout,
            n_effective=n_effective, identity_nll=None, candidate_nll=None)

    if n_own + n_halo < WINDOW_PHOT_MIN_SEARCH_LABELS:
        return refused(REASON_SEARCH_STARVED)
    # Identifiability: W plus at least two inked states.  Two class means
    # determine a gain and an offset exactly, with no residual to judge
    # them by; three is the smallest over-determined fit.
    if not identifiable(present):
        return refused(REASON_STATE_SUPPORT)
    if n_heldout < WINDOW_PHOT_MIN_HELDOUT:
        return refused(REASON_HELDOUT_STARVED)

    fit_states = states[fit_rows]
    base = np.where(
        own_search[fit_rows], 1.0, WINDOW_PHOT_HALO_POOL_WEIGHT)
    weights = balanced_base_weights(fit_states, base)
    n_effective = float(np.sum(base))
    gains, offsets = _weighted_affine(
        known[fit_rows], targets[fit_rows], weights)
    # Shrinkage toward the identity map, in effective labels.
    denominator = n_effective + config.prior_labels
    gains = (n_effective * gains + config.prior_labels) / denominator
    offsets = n_effective * offsets / denominator
    candidate = WindowMap(
        np.ascontiguousarray(gains, np.float64),
        np.ascontiguousarray(offsets, np.float64))

    # The PK3.1 pre-gate, on this window's OWN held-out labels.
    heldout_states = states[own_heldout]
    heldout_weights = class_balanced_weights(heldout_states)
    heldout_features = known[own_heldout]
    identity_nll = _balanced_nll(
        model, heldout_features, heldout_states, heldout_weights)
    candidate_nll = _balanced_nll(
        model, candidate.apply(heldout_features), heldout_states,
        heldout_weights)
    accepted = identity_nll - candidate_nll > WINDOW_PHOT_GATE_SLACK
    return WindowMapFit(
        ordinal=ordinal,
        window_map=candidate if accepted else None,
        reason=REASON_ADOPTED if accepted else REASON_GATE_FAILED,
        n_own=n_own, n_halo=n_halo, n_states=n_states,
        n_heldout=n_heldout, n_effective=n_effective,
        identity_nll=identity_nll, candidate_nll=candidate_nll)


def fit_window_photometry(
    model: color_detect.ColorQDAModel,
    selection: _OwnerSelection,
    row_tuple: tuple[_Rows, ...],
    features: tuple[np.ndarray, ...],
    config: WindowPhotometryConfig,
) -> WindowPhotometryResult:
    """Fit, gate, and apply one region's per-window photometric maps.

    ``model`` is the INCUMBENT arm's region QDA: it supplies both the fit
    targets (its class means) and the pre-gate's measure, so a window's
    map is judged by the model it is about to correct.  ``features`` are
    that same arm's per-window feature arrays, in ``row_tuple`` order.

    A region where no window earned a map costs the fits and nothing
    else: it hands back the caller's own arrays untouched (R3) and never
    allocates a mapped tuple.
    """
    if len(features) != len(row_tuple):
        raise ValueError(
            "color window photometry: one feature array per window row")
    means = np.asarray(model.means, np.float64)
    known = selection.gather(features)
    states = np.asarray(selection.states, np.int64)
    ordinals = np.asarray(selection.window_ordinals, np.int64)
    search = np.asarray(selection.search, np.bool_)
    halo_of = _halo_membership(_window_bboxes(row_tuple))
    targets = means[states]

    own_of = [ordinals == ordinal for ordinal in range(len(row_tuple))]
    fits = [
        _fit_one_window(
            model, config, ordinal, known, targets, states,
            own & search, own & ~search,
            halo_of[ordinal][ordinals] & search & ~own)
        for ordinal, own in enumerate(own_of)
    ]
    accepted = sum(1 for fit in fits if fit.accepted)
    counts: dict[str, int] = {}
    for fit in fits:
        counts[fit.reason] = counts.get(fit.reason, 0) + 1
    # The only region-level refusal left: nothing to offer.  The two
    # applicability floors PK4.1/PK4.2 built here are RETIRED — measured
    # non-separating on 27 lanes of two captures (MEASUREMENTS §12) — and
    # the arm's applicability is answered by scheduling instead.
    arm_reason = "" if accepted else REASON_NO_WINDOW_MAPS
    mapped = features
    if not arm_reason:
        rows = list(features)
        for fit in fits:
            if fit.window_map is not None:
                rows[fit.ordinal] = fit.window_map.apply(
                    features[fit.ordinal])
        mapped = tuple(rows)
    return WindowPhotometryResult(
        # R3: a refused arm gets the caller's OWN tuple back, not a
        # rebuilt one holding the same arrays.
        features=mapped,
        fits=tuple(fits),
        accepted=accepted,
        refused=len(fits) - accepted,
        pooled=sum(1 for fit in fits if fit.pooled),
        reasons=tuple(sorted(counts.items())),
        arm_reason=arm_reason,
    )


__all__ = [
    "CERT_PREVIEW_MAX_CELLS", "NLL_UNMEASURED", "REASON_ADOPTED",
    "REASON_GATE_FAILED",
    "REASON_HELDOUT_STARVED", "REASON_NO_WINDOW_MAPS",
    "REASON_REGION_GATE_FAILED", "REASON_SEARCH_STARVED",
    "REASON_STATE_SUPPORT", "WINDOW_PHOT_GATE_SLACK",
    "WINDOW_PHOT_HALO_POOL_WEIGHT", "WINDOW_PHOT_MIN_HELDOUT",
    "WINDOW_PHOT_MIN_SEARCH_LABELS", "WINDOW_PHOT_MIN_STATES",
    "WINDOW_PHOT_MIN_VARIANCE", "WINDOW_PHOT_PRIOR_LABELS", "WindowMap",
    "WindowMapFit", "WindowPhotometryConfig",
    "WindowPhotometryResult", "WindowPhotometrySummary",
    "balanced_base_weights", "cert_population_preview",
    "fit_window_photometry",
]
