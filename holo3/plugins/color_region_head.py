"""The colour detector stack: fitting a region's head, and reading with it.

Split out of ``color_region`` at the 1000-line seam. This half knows
nothing about windows on a page, rasters or certificates — it takes
sampled features and the reference states that label them, fits the
QDA / CMY8 detector / CMY7 head / context head over the region's own
labels (letting a pooled head compete where one is offered), and turns
features into the evidence the tile decoders read. ``color_region``
keeps the other half: what a window is, where its cells land, how the
page is sampled, and the descriptor.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
from scipy.special import logsumexp

from ..data import PlaneResidual, WindowRows
from ..format.identity import Family, FormatRow
from ..lib.geometry import site_parity
from . import color_conditioning as conditioning
from . import color_model
from . import color_photometry as photometry
from . import color_region_ctx as ctx

CMY7_RELATIVE_SCORE_BOUND: float = 20.0
STACK_GATE_SLACK: float = 1e-9
HEAD_SATURATION_FLOOR: float = 0.30
HEAD_SATURATION_UNMEASURED: float = -1.0
HEAD_SATURATION_REASON: str = "saturation_below_floor"

@dataclass(frozen=True)
class StackConfig:
    head_saturation_floor: float = HEAD_SATURATION_FLOOR
    context: ctx.ContextConfig = field(
        default_factory=ctx.ContextConfig)
    window_photometry: photometry.WindowPhotometryConfig = field(
        default_factory=photometry.WindowPhotometryConfig)


@dataclass(frozen=True)
class OwnerSelection:
    window_ordinals: np.ndarray
    row_indices: np.ndarray
    states: np.ndarray
    kinds: np.ndarray
    keys: np.ndarray
    search: np.ndarray

    def gather(self, features: tuple[np.ndarray, ...],
               dtype: type = np.float64) -> np.ndarray:
        n_rows = self.window_ordinals.size
        width = features[0].shape[1] if features else 0
        gathered = np.empty((n_rows, width), dtype)
        for ordinal in np.unique(self.window_ordinals):
            selected = self.window_ordinals == ordinal
            gathered[selected] = np.asarray(
                features[int(ordinal)], dtype,
            )[self.row_indices[selected]]
        return gathered


@dataclass(frozen=True)
class DetectorFit:
    model: color_model.QdaModel
    detector: color_model.Cmy8Detector | None
    heldout_loss: float
    word_heldout_loss: float
    dust_heldout_loss: float
    heldout_scores: np.ndarray | None
    heldout_states: np.ndarray | None
    heldout_keys: np.ndarray | None
    cmy7_head: color_model.Cmy7Head | None = None
    context: ctx.ContextHead | None = None
    conditioned: conditioning.Cmy8ConditionedHead | None = None


@dataclass(frozen=True)
class CtxLabels:
    """The lane's own context-fit population, in the shape the pooled arm
    consumes: format-truth and certified labels, this lane's scores, this
    lane's bins, this lane's fit/held-out split."""
    keys_pyx: np.ndarray
    scores: np.ndarray
    states: np.ndarray
    kinds: np.ndarray
    bins: np.ndarray
    search: np.ndarray


@dataclass(frozen=True)
class StackResult:
    selected: DetectorFit | None
    features: tuple[np.ndarray, ...]
    adopted: bool
    refusal_reason: str
    head_reason: str
    head_saturation: float
    ctx_verdict: ctx.ContextVerdict | None
    context_bins: tuple[np.ndarray, ...] | None
    labels: CtxLabels | None = None
    pooled_adopted: bool = False


@dataclass(frozen=True)
class LaneHead:
    """A standing head, with the region frame it was fitted in.

    A head only reads the way it was fitted: through the region's
    aperture (``pitch_px``), at its native scale (``divisor``), against
    the plane registration ``residuals`` it corrected for, and only if
    ``corrected`` sampling was what won the registration arm. Carrying
    the five together is what lets a window that arrived AFTER the fit
    be read by that head without re-fitting it. What the head does NOT
    carry is fire-time truth — the lane's standing plane fields are read
    again at every fire, so a later window is sampled against the field
    that stands then, not the one that stood at the fit.
    """
    fit: DetectorFit
    pitch_px: float
    divisor: float
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual]
    corrected: bool


@dataclass(frozen=True)
class ColorLaneFit:
    """What one colour-lane fire did, as a fact the store folds.

    ``assembled`` are the patch ordinals the fire covered. The lane's
    ASSEMBLY DEBT is every placed window whose ordinal is not in the
    standing set, and a fire clears the windows it covered whether or
    not each ended up with an evidence row — a fully certified window
    has none to give, and a refused fit gave none to anybody.

    ``head_fitted`` is true when the fire RAN the fit. The lane's count
    of those is the re-fit pricing ordinal, which is why an assembly
    fire — which applies the standing head and fits nothing — never
    inflates the next re-fit's price. ``head`` carries a fit forward,
    and is None when the fire fitted nothing or the fit refused.
    """
    capture_id: str
    level_index: int
    page: int
    assembled: tuple[int, ...]
    head_fitted: bool
    head: LaneHead | None


def deterministic_fit_split(states: np.ndarray,
                            keys: np.ndarray) -> np.ndarray:
    labels = np.asarray(states, np.int64)
    coordinates = np.asarray(keys, np.int64)
    search = site_parity(coordinates[:, 1], coordinates[:, 2]) == 0
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


def owner_selection(rows: tuple[WindowRows, ...]) -> OwnerSelection:
    owned: dict[tuple[int, int, int], tuple[int, int, int, int]] = {}
    for ordinal, window in sorted(
        enumerate(rows),
        key=lambda pair: int(pair[1].patch_ordinal),
    ):
        for index in np.flatnonzero(window.states >= 0):
            cell = window.page_cells_yx[index]
            key = (window.page, int(cell[0]), int(cell[1]))
            owned.setdefault(
                key,
                (ordinal, int(index), int(window.states[index]),
                 int(window.furniture_kind[index])),
            )
    ordered = [owned[key] for key in sorted(owned)]
    keys = np.asarray(sorted(owned), np.int64).reshape(len(owned), 3)
    states = np.asarray([entry[2] for entry in ordered], np.int64)
    return OwnerSelection(
        np.asarray([entry[0] for entry in ordered], np.int64),
        np.asarray([entry[1] for entry in ordered], np.int64),
        states,
        np.asarray([entry[3] for entry in ordered], np.int8),
        keys,
        deterministic_fit_split(states, keys),
    )


def fit_detector(
    family: Family,
    selection: OwnerSelection,
    features: tuple[np.ndarray, ...],
) -> tuple[DetectorFit | None, str]:
    if selection.window_ordinals.shape[0] == 0:
        return None, "no_known_furniture"
    known_features = selection.gather(features)
    states = selection.states
    kinds = selection.kinds
    search = selection.search
    heldout = ~search
    n_states = 7 if family is Family.CMY7 else 8
    counts = np.bincount(states[search], minlength=n_states)
    heldout_counts = np.bincount(states[heldout], minlength=n_states)
    if np.any(counts == 0):
        return None, "search_split_missing_state"
    if np.any(heldout_counts == 0):
        return None, "heldout_split_missing_state"
    try:
        if family is Family.CMY7:
            model = color_model.fit_qda(
                known_features[search], states[search], 7)
            detector = None
        else:
            calibration = (kinds == 1) | (kinds == -1)
            detector = color_model.fit_cmy8_detector(
                known_features[search],
                states[search],
                known_features[calibration],
                states[calibration],
            )
            model = detector.qda
    except ValueError:
        return None, "detector_fit_failed"
    if family is Family.CMY7 and (model.degenerate
                                  or model.clipped_planes):
        return None, "collapsed_color_support"
    scores = color_model.qda_log_scores(model, known_features[heldout])
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    heldout_states = states[heldout]
    heldout_kinds = kinds[heldout]
    nll = -normalized[np.arange(normalized.shape[0]), heldout_states]
    heldout_loss = float(np.mean(nll))

    def furniture_loss(kind: int) -> float:
        selected = heldout_kinds == kind
        return (
            float(np.mean(nll[selected]))
            if np.any(selected) else float("inf")
        )

    if family is Family.CMY7:
        heldout_scores: np.ndarray | None = scores[:, 1:] - scores[:, :1]
        population_states: np.ndarray | None = heldout_states
        population_keys: np.ndarray | None = selection.keys[heldout]
    else:
        heldout_scores = None
        population_states = None
        population_keys = None
    return DetectorFit(
        model=model,
        detector=detector,
        heldout_loss=heldout_loss,
        word_heldout_loss=furniture_loss(0),
        dust_heldout_loss=furniture_loss(1),
        heldout_scores=heldout_scores,
        heldout_states=population_states,
        heldout_keys=population_keys,
    ), ""


def improves(candidate: DetectorFit,
             selected: DetectorFit | None) -> bool:
    if selected is None:
        return True
    return (
        candidate.heldout_loss + STACK_GATE_SLACK < selected.heldout_loss
        and candidate.word_heldout_loss
        <= selected.word_heldout_loss + STACK_GATE_SLACK
        and candidate.dust_heldout_loss
        <= selected.dust_heldout_loss + STACK_GATE_SLACK
    )


def evidence_with_divisor(
    fit: DetectorFit,
    features: np.ndarray,
    bins: np.ndarray | None,
    known_mask: np.ndarray | None = None,
    known_bits: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray | None]:
    if fit.detector is None:
        scores = color_model.cmy7_relative_scores(fit.model, features)
        if fit.cmy7_head is not None:
            scores = fit.cmy7_head.apply(scores)
        if fit.context is not None and bins is not None:
            scores = fit.context.apply_states(scores, bins)
        divisor = np.maximum(
            1.0,
            np.max(np.abs(scores), axis=1, keepdims=True)
            / CMY7_RELATIVE_SCORE_BOUND,
        )
        return scores / divisor, divisor
    conditioned = fit.conditioned if known_mask is not None else None
    if fit.context is None or bins is None:
        if conditioned is None:
            return fit.detector.llrs(features), None
        return conditioned.llrs(
            fit.detector, features, known_mask, known_bits), None
    scores = fit.context.apply_states(
        color_model.qda_log_scores(fit.detector.qda, features), bins)
    if conditioned is None:
        return ctx.emitted_llrs(fit.detector, scores), None
    return conditioned.llrs_from_scores(
        fit.detector, scores, known_mask, known_bits), None


def pre_head_saturation_counts(
    fit: DetectorFit,
    features: np.ndarray,
) -> tuple[int, int]:
    if fit.detector is not None:
        return 0, 0
    scores = color_model.cmy7_relative_scores(fit.model, features)
    divisor = np.maximum(
        1.0,
        np.max(np.abs(scores), axis=1) / CMY7_RELATIVE_SCORE_BOUND,
    )
    return int(divisor.size), int(np.count_nonzero(divisor > 1.0))


def deployment_saturation(
    fit: DetectorFit,
    features: tuple[np.ndarray, ...],
    emission_masks: tuple[np.ndarray, ...],
) -> float:
    emitted = 0
    saturated = 0
    for row_features, emit in zip(
            features[:len(emission_masks)], emission_masks):
        if not np.any(emit):
            continue
        cells, hits = pre_head_saturation_counts(fit, row_features[emit])
        emitted += cells
        saturated += hits
    return 0.0 if not emitted else saturated / emitted


def window_loss(
    model: color_model.QdaModel,
    rows: WindowRows,
    features: np.ndarray,
    fallback: float,
) -> float:
    heldout = (
        (rows.states >= 0)
        & (site_parity(rows.page_cells_yx[:, 0],
                       rows.page_cells_yx[:, 1]) == 1)
    )
    if not np.any(heldout):
        return fallback
    scores = color_model.qda_log_scores(model, features[heldout])
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    labels = rows.states[heldout].astype(np.int64)
    return float(-np.mean(
        normalized[np.arange(labels.size), labels]))


def pooled_candidate(
    pooled: ctx.ContextHead | None,
    supported: tuple[bool, bool, bool],
    width: int,
) -> ctx.ContextHead | None:
    """The pooled head as this lane can wear it: unsupported planes
    zeroed, a head of the wrong state width refused outright."""
    if pooled is None:
        return None
    if tuple(np.shape(pooled.offsets)) != (width, 3, ctx.N_CONTEXT_BINS):
        return None
    candidate = ctx.mask_unsupported(pooled, supported)
    if not np.any(candidate.applied):
        return None
    return candidate


def select_registration_arm(
    row: FormatRow,
    selection: OwnerSelection,
    base: tuple[np.ndarray, ...],
    corrected: tuple[np.ndarray, ...] | None,
) -> tuple[DetectorFit | None, tuple[np.ndarray, ...], bool, str]:
    baseline, reason = fit_detector(row.family, selection, base)
    candidate = (
        None if corrected is None
        else fit_detector(row.family, selection, corrected)[0])
    selected = baseline
    selected_features = base
    adopted = False
    if candidate is not None and improves(candidate, selected):
        selected = candidate
        selected_features = corrected
        adopted = True
    return selected, selected_features, adopted, reason


def fit_region_stack(
    row: FormatRow,
    selection: OwnerSelection,
    rows: tuple[WindowRows, ...],
    base: tuple[np.ndarray, ...],
    corrected: tuple[np.ndarray, ...] | None,
    emission_masks: tuple[np.ndarray, ...],
    config: StackConfig,
    pooled: ctx.ContextHead | None = None,
    publish_labels: bool = False,
) -> StackResult:
    selected, selected_features, adopted, reason = select_registration_arm(
        row, selection, base, corrected)
    return finish_region_stack(
        row, selection, rows, selected, selected_features, adopted, reason,
        emission_masks, config, pooled, publish_labels)


def finish_region_stack(
    row: FormatRow,
    selection: OwnerSelection,
    rows: tuple[WindowRows, ...],
    selected: DetectorFit | None,
    selected_features: tuple[np.ndarray, ...],
    adopted: bool,
    reason: str,
    emission_masks: tuple[np.ndarray, ...],
    config: StackConfig,
    pooled: ctx.ContextHead | None = None,
    publish_labels: bool = False,
) -> StackResult:
    head_reason = ""
    saturation = HEAD_SATURATION_UNMEASURED
    if selected is not None and row.family is Family.CMY7:
        head, head_reason = color_model.fit_cmy7_head(
            selected.heldout_scores,
            selected.heldout_states,
            selected.heldout_keys)
        if head is not None:
            saturation = deployment_saturation(
                selected, selected_features, emission_masks)
            if saturation < config.head_saturation_floor:
                head = None
                head_reason = HEAD_SATURATION_REASON
        selected = replace(selected, cmy7_head=head)
    ctx_verdict: ctx.ContextVerdict | None = None
    context_bins: tuple[np.ndarray, ...] | None = None
    labels: CtxLabels | None = None
    pooled_adopted = False
    if selected is not None and config.context.enabled:
        starved = ctx.label_floor_refusal(
            selection.search, config.context)
        wants_pool = pooled is not None or publish_labels
        gate_starved = ctx.validation_floor_refusal(
            selection.search, config.context)
        if starved and (not wants_pool or gate_starved):
            ctx_verdict = ctx.ContextVerdict(None, False, starved, 0, 0)
        else:
            cmy8 = selected.detector is not None
            fit = selected
            bins = ctx.region_context_bins(
                rows,
                lambda ordinal: evidence_with_divisor(
                    fit, selected_features[ordinal], None)[0],
                cmy8)
            known_bins = selection.gather(bins, np.int8)
            if not np.any(np.asarray(known_bins) >= 0):
                ctx_verdict = ctx.ContextVerdict(
                    None, False, ctx.REASON_NO_CELLS, 0, 0)
            else:
                supported = (selected.detector.supported_planes
                             if cmy8 else (True, True, True))
                scores = ctx.locus_scores(
                    selected.model, selected.cmy7_head,
                    selection.gather(selected_features), cmy8)
                validation = ctx.population(
                    scores, selection.states, known_bins, selection.kinds,
                    ~selection.search)
                ctx_verdict = (
                    ctx.ContextVerdict(None, False, starved, 0, 0)
                    if starved
                    else ctx.context_verdict(
                        ctx.population(scores, selection.states, known_bins,
                                       selection.kinds, selection.search),
                        validation, config.context, cmy8, supported,
                        selected.detector))
                head = ctx_verdict.head
                candidate = pooled_candidate(
                    pooled, supported,
                    scores.shape[1] if cmy8 else scores.shape[1] - 1)
                if candidate is not None:
                    better, _loss = ctx.improves_region(
                        selected.detector, validation, head, candidate,
                        cmy8)
                    if better:
                        head = candidate
                        pooled_adopted = True
                if head is not None:
                    selected = replace(selected, context=head)
                    context_bins = bins
                if publish_labels:
                    labels = CtxLabels(
                        keys_pyx=selection.keys,
                        scores=np.asarray(scores, np.float32),
                        states=np.asarray(selection.states, np.int8),
                        kinds=np.asarray(selection.kinds, np.int8),
                        bins=known_bins,
                        search=np.asarray(selection.search, np.bool_))
    return StackResult(
        selected=selected,
        features=selected_features,
        adopted=adopted,
        refusal_reason="" if selected is not None else reason,
        head_reason=head_reason,
        head_saturation=saturation,
        ctx_verdict=ctx_verdict,
        context_bins=context_bins,
        labels=labels,
        pooled_adopted=pooled_adopted,
    )


