"""Detector fitting for color payload evidence.

One region/page detector per acquisition: deduplicated known-furniture
owners, the historical coordinate-parity train/validation split with
deterministic sparse-state repair, equal-prior QDA (CMY7) or the
PAVA-calibrated first-order detector (CMY8), and held-out log-loss
accounting.  The CMY7 relative-score bound lives here so every durable
evidence row is bounded at this adapter boundary.

Detector models are transient.  :mod:`holo.receive.color_payload` owns
the durable evidence contract around these helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.special import logsumexp

from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from . import color_detect
from .color_anchoring import _Rows
from .color_calibration import Cmy7Head
from .color_conditioning import Cmy8ConditionedHead
from .color_context import (
    LOCUS_STATES,
    ContextHead,
    emitted_llrs,
)
from ..core.channel import PLANE_ORDER


CMY7_RELATIVE_SCORE_BOUND: Final = 20.0


@dataclass(frozen=True, slots=True)
class _HeldoutPopulation:
    """The CMY7 head's fit material, taken from the QDA's own held-out side.

    P1 (RECEIVE-DESIGN §6.2a A4) needs the held-out relative scores, their
    true states, and their canonical ``(page, y, x)`` site keys — plus the
    QDA's training keys so the head fitter can CHECK the disjointness the
    split guarantees.  ``_fit_detector`` already scores this exact
    population for its own held-out loss, so carrying it costs one view
    and no rescoring; it is attached for CMY7 only (a CMY8 region has no
    head and would pay pure memory).
    """

    relative_scores: np.ndarray
    states: np.ndarray
    site_keys: np.ndarray
    search_site_keys: np.ndarray


@dataclass(frozen=True, slots=True)
class _DetectorFit:
    model: color_detect.ColorQDAModel
    detector: color_detect.CMY8Detector | None
    heldout_loss: float
    word_heldout_loss: float
    dust_heldout_loss: float
    n_train: int
    n_heldout: int
    class_counts: tuple[int, ...]
    calibration_labels: int = 0
    component_supported: tuple[bool, ...] = ()
    component_support_reasons: tuple[str | None, ...] = ()
    # P1 (append-only, risk R4).  ``cmy7_head is None`` is the pre-P1
    # receiver EXACTLY — see ``evidence``.
    cmy7_head: Cmy7Head | None = None
    head_reason: str = ""
    heldout_population: _HeldoutPopulation | None = None
    # P9/PK10 (append-only, risk R4).  ``conditioned is None`` is the
    # pre-P9 receiver EXACTLY, and so is a present head applied to cells
    # with no certified sibling — see ``evidence_with_divisor``.
    conditioned: Cmy8ConditionedHead | None = None
    conditioning_reason: str = ""
    # P2/PK5 (append-only, risk R4).  ``context is None`` is the pre-P2
    # receiver EXACTLY, and so is a present head at a cell with no valid
    # 8-neighbourhood — see ``evidence_with_divisor``.
    context: ContextHead | None = None
    context_reason: str = ""

    def evidence(self, features: np.ndarray) -> np.ndarray:
        return self.evidence_with_divisor(features)[0]

    def evidence_with_divisor(
        self,
        features: np.ndarray,
        known_mask: np.ndarray | None = None,
        known_bits: np.ndarray | None = None,
        context_bins: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Evidence plus the CMY7 L∞ divisor (``None`` for CMY8).

        The divisor is the saturation canary P1 reports (``divisor > 1``
        means the cell hit the bound); it is returned rather than
        recomputed because recomputing it would score the region twice.

        ``known_mask``/``known_bits`` are the emitted cells' KnownField
        rows (P9).  They are consulted ONLY by an adopted A4b head on a
        CMY8 region; every other path ignores them, so a caller may
        always pass them and a caller that does not gets the historical
        evidence by construction.

        ``context_bins`` are the same cells' ``(N, 3)`` per-plane
        neighbourhood bins (P2).  They are consulted only by an adopted
        A5 head, and a head is attached only when the ladder also carries
        the bins, so the two travel together or not at all.
        """
        context = self.context if context_bins is not None else None
        if self.detector is None:
            # The historical QDA leaf intentionally remains exact and
            # unbounded.  Bound only at this adapter boundary so every
            # physical acquisition contributes bounded durable CMY7
            # evidence; legal same-lane unions may then add those bounded
            # independent contributions.  Uniform per-cell L-infinity
            # scaling, rather than componentwise saturation, preserves all
            # seven-state orderings and every sign relative to W=0.
            scores = color_detect.cmy7_relative_scores(
                self.model, features)
            # P1: the fitted head calibrates BEFORE the bound, so
            # `cmy7linf20` stays truthful (the bound still applies, after
            # calibration).  Note the head is the one step here that MAY
            # reorder states: the bound's uniform scaling deliberately
            # cannot, but a calibration with per-state offsets that could
            # not change a decision could not fix a wrong one either.  The
            # result is still a proper joint seven-state logit vector, so
            # the exact pack7 demapper's contract holds.  With no head the
            # expression below is literally the pre-P1 one — same
            # operations, same order, byte-identical evidence (risk R2).
            if self.cmy7_head is not None:
                scores = self.cmy7_head.apply(scores)
            # A5 (P2): the neighbourhood correction rides the same six
            # logits, AFTER A4's calibration (it is the next ladder rung)
            # and BEFORE the bound (which stays the last operation, so
            # `cmy7linf20` keeps meaning what it says).  With no head the
            # expression is literally the pre-P2 one.
            if context is not None:
                scores = context.apply_states(scores, context_bins)
            divisor = np.maximum(
                1.0,
                np.max(np.abs(scores), axis=1, keepdims=True)
                / CMY7_RELATIVE_SCORE_BOUND,
            )
            return scores / divisor, divisor
        if context is None:
            if self.conditioned is None or known_mask is None:
                return self.detector.llrs(features), None
            # A4b: the same detector, marginalized over the state subset
            # the certified siblings leave, and read through that
            # stratum's own calibration.  Every cell with no known
            # sibling comes back byte-identical to the branch above
            # (color_conditioning).
            return self.conditioned.llrs(
                self.detector, features, known_mask, known_bits), None
        # A5 on CMY8, at the STATE locus: the multi-state matrix
        # corrects the state scores before marginalization, so one
        # scoring pass feeds both A4b's subset marginals and the
        # unconditioned ones.  (The per-plane K port occupied a second,
        # MARGINAL locus; it is retired — measured an exact null in
        # 0 of 17 lanes on the uplift target, MEASUREMENTS §11.4/§12.)
        return self._cmy8_evidence(
            features, known_mask, known_bits, context, context_bins), None

    def _cmy8_evidence(
        self,
        features: np.ndarray,
        known_mask: np.ndarray | None,
        known_bits: np.ndarray | None,
        context: ContextHead,
        context_bins: np.ndarray,
    ) -> np.ndarray:
        detector = self.detector
        if detector is None:                       # pragma: no cover
            raise ValueError("color payload: CMY8 evidence needs a detector")
        if context.locus != LOCUS_STATES:          # pragma: no cover
            raise ValueError("color payload: unknown context locus")
        scores = context.apply_states(
            color_detect.qda_log_scores(detector.qda, features),
            context_bins)
        if self.conditioned is None or known_mask is None:
            return emitted_llrs(detector, scores)
        return self.conditioned.llrs_from_scores(
            detector, scores, known_mask, known_bits)

    def pre_head_saturation_counts(
        self, features: np.ndarray,
    ) -> tuple[int, int]:
        """``(cells, cells at the L-infinity bound)`` with NO head applied.

        The A4 saturation FLOOR (color_stack) gates the head on the
        deployment population's own pathology, so it needs the divisor the
        pre-P1 receiver would have produced — measured on payload cells,
        before any head exists.  This deliberately ignores
        ``self.cmy7_head``: it answers "is this population saturated?",
        never "is it still saturated after calibration?" (that second
        question is the emitted canary ``cmy7_saturation_fraction``).

        The divisor expression is the LITERAL one from
        ``evidence_with_divisor`` so the two numbers are comparable float
        for float; only the ``keepdims`` is dropped.  CMY8 has no bound
        and returns ``(0, 0)``.
        """
        if self.detector is not None:
            return 0, 0
        scores = color_detect.cmy7_relative_scores(self.model, features)
        divisor = np.maximum(
            1.0,
            np.max(np.abs(scores), axis=1) / CMY7_RELATIVE_SCORE_BOUND,
        )
        return int(divisor.size), int(np.count_nonzero(divisor > 1.0))


@dataclass(frozen=True, slots=True)
class _OwnerSelection:
    """One region's known-furniture ownership and fit split.

    Ownership (deduplication by numeric patch ID) and the deterministic
    train/validation split depend only on the rows' states and coordinates
    — never on sampled features — so a region computes them ONCE and both
    detector fits (baseline and registration-corrected) gather their own
    features through the same selection (color-upstream:07).
    """

    window_ordinals: np.ndarray
    row_indices: np.ndarray
    states: np.ndarray
    kinds: np.ndarray
    keys: np.ndarray
    search: np.ndarray

    def gather(
        self,
        features: tuple[np.ndarray, ...],
        dtype: np.dtype | type = np.float64,
    ) -> np.ndarray:
        """Gather one per-row array set through the frozen ownership.

        ``dtype`` is float64 for features — the historical and only
        pre-P2 use — and int8 for A5's per-row context bins, which are
        per-CELL facts that must be selected through exactly the same
        ownership so a labelled cell's bin can never come from a
        different window than its feature.
        """
        n_rows = self.window_ordinals.size
        width = features[0].shape[1] if features else 0
        gathered = np.empty((n_rows, width), dtype)
        for ordinal in np.unique(self.window_ordinals):
            selected = self.window_ordinals == ordinal
            gathered[selected] = np.asarray(
                features[int(ordinal)], dtype,
            )[self.row_indices[selected]]
        return gathered


def _owner_selection(rows: tuple[_Rows, ...]) -> _OwnerSelection:
    """Deduplicate known cells by numeric patch ID; split once."""
    owned: dict[tuple[int, int, int], tuple[int, int, int, int]] = {}
    for ordinal, window in sorted(
        enumerate(rows),
        key=lambda pair: int(pair[1].patch.patch_id),
    ):
        for index in np.flatnonzero(window.states >= 0):
            cell = window.page_cells_yx[index]
            key = (window.patch.candidate.page,
                   int(cell[0]), int(cell[1]))
            owned.setdefault(
                key,
                (ordinal, int(index), int(window.states[index]),
                 int(window.furniture_kind[index])),
            )
    ordered = [owned[key] for key in sorted(owned)]
    keys = np.asarray(sorted(owned), np.int64).reshape(len(owned), 3)
    states = np.asarray([row[2] for row in ordered], np.int64)
    return _OwnerSelection(
        np.asarray([row[0] for row in ordered], np.int64),
        np.asarray([row[1] for row in ordered], np.int64),
        states,
        np.asarray([row[3] for row in ordered], np.int8),
        keys,
        _deterministic_fit_split(states, keys),
    )


def _deterministic_fit_split(
    states: np.ndarray,
    keys: np.ndarray,
) -> np.ndarray:
    """Return the historical split with deterministic sparse-state repair.

    Large regions retain the coordinate-parity split byte-for-byte.  A
    one-tile p120 region can put all three examples of a dust state on one
    parity, however, which made first-order CMY8 fitting impossible despite
    the format deliberately printing that state.  When a represented state
    has at least two rows but only one side, move its canonical first row to
    the empty side.  No observation appears in both train and validation.
    """
    labels = np.asarray(states, np.int64)
    coordinates = np.asarray(keys, np.int64)
    search = (
        ((131 * coordinates[:, 1] + 17 * coordinates[:, 2]) & 1) == 0
    )
    for state in range(int(labels.max(initial=-1)) + 1):
        selected = np.flatnonzero(labels == state)
        if selected.size < 2:
            continue
        state_search = search[selected]
        if np.all(state_search):
            search[selected[0]] = False
        elif not np.any(state_search):
            search[selected[0]] = True
    return search


def _fit_detector(
    spec: FormatSpec,
    selection: _OwnerSelection,
    features: tuple[np.ndarray, ...],
) -> _DetectorFit:
    if selection.window_ordinals.shape[0] == 0:
        raise ValueError("color payload: no known furniture is visible")
    known_features = selection.gather(features)
    states = selection.states
    kinds = selection.kinds
    search = selection.search
    heldout = ~search
    n_states = 7 if spec.codec_family is Family.CMY7 else 8
    counts = np.bincount(states[search], minlength=n_states)
    heldout_counts = np.bincount(states[heldout], minlength=n_states)
    if np.any(counts == 0):
        raise ValueError(
            "color payload: training split does not cover every state")
    if np.any(heldout_counts == 0):
        raise ValueError(
            "color payload: held-out split does not cover every state")
    if spec.codec_family is Family.CMY7:
        model = color_detect.fit_equal_prior_qda(
            known_features[search], states[search], n_states=7)
        detector = None
        calibration_labels = 0
        component_supported: tuple[bool, ...] = ()
        component_support_reasons: tuple[str | None, ...] = ()
    else:
        # The first-order model is calibrated by all format-known dust on one
        # fixed QDA score axis.  This uses the complete 20-site p120 contract
        # even when the QDA's disjoint validation split is sparse.  Prior-
        # barrier CRC-certified complete states are equally exact labels and
        # may strengthen a later lane.  BCH word sites remain out of PAVA so
        # their structured W/CM population cannot dominate the deliberately
        # balanced dust map.
        calibration = (kinds == 1) | (kinds == -1)
        detector = color_detect.fit_cmy8_detector(
            known_features[search],
            states[search],
            known_features[calibration],
            states[calibration],
        )
        model = detector.qda
        calibration_labels = detector.calibration_labels
        component_supported = detector.supported_planes
        component_support_reasons = detector.unsupported_reasons
    if (spec.codec_family is Family.CMY7
            and (model.degenerate or model.clipped_planes)):
        planes = ",".join(
            PLANE_ORDER[index] for index in model.clipped_planes)
        raise ValueError(
            "color payload: detector has collapsed color support"
            + ("" if not planes else f" ({planes})"))
    scores = color_detect.qda_log_scores(
        model, known_features[heldout])
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    heldout_states = states[heldout]
    heldout_kinds = kinds[heldout]
    nll = -normalized[
        np.arange(normalized.shape[0]), heldout_states]
    heldout_loss = float(np.mean(nll))

    def furniture_loss(kind: int) -> float:
        selected = heldout_kinds == kind
        return (
            float(np.mean(nll[selected]))
            if np.any(selected) else float("inf")
        )

    # P1's fit material, CMY7 only.  ``cmy7_relative_scores`` is exactly
    # ``qda_log_scores(...)[:, 1:] - [:, :1]``, so deriving the relative
    # scores from the array just computed is bit-identical to calling it
    # and saves one full rescoring of the held-out population.
    population = (
        _HeldoutPopulation(
            scores[:, 1:] - scores[:, :1],
            heldout_states,
            selection.keys[heldout],
            selection.keys[search],
        )
        if spec.codec_family is Family.CMY7 else None
    )
    return _DetectorFit(
        model, detector, heldout_loss,
        furniture_loss(0), furniture_loss(1),
        int(search.sum()), int(heldout.sum()),
        tuple(int(value) for value in counts),
        calibration_labels,
        component_supported,
        component_support_reasons,
        heldout_population=population,
    )


def _window_loss(
    model: color_detect.ColorQDAModel,
    rows: _Rows,
    features: np.ndarray,
    fallback: float,
) -> float:
    heldout = (
        (rows.states >= 0)
        & (((131 * rows.page_cells_yx[:, 0]
             + 17 * rows.page_cells_yx[:, 1]) & 1) == 1)
    )
    if not np.any(heldout):
        return fallback
    scores = color_detect.qda_log_scores(model, features[heldout])
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    labels = rows.states[heldout].astype(np.int64)
    return float(-np.mean(
        normalized[np.arange(labels.size), labels]))
