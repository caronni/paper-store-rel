"""cmy's calibration chain (R11): the hi-first head in the head slot.

cmy's evidence is three W-relative state scores (C, M, Y) and its
decoders read them through `tile_codec.cmy_soft_demap`.  The chain
calibrates them once per colour lane, at evidence time, the way cmy7's
`Cmy7Head` does (CMY-DESIGN §2.7, R11 "we follow cmy8"): fitted in
`color_region_head.finish_region_stack` on the QDA's held-out side and
applied in `evidence_with_divisor` before the context matrix, the
erasure and the L-infinity bound.  It is a HEAD, never a `detector`: the
lane's `detector is not None` switch stays False for cmy.

Three PAVA maps, hi first -- L_hi on the hi marginal, L_{lo|hi=0} (W vs
Y) on sY, L_{lo|hi=1} (M vs C) on sC - sM -- each fitted on the exact
form the demap hands its consumer (E017.5), state-balanced (each state
a quarter of a marginal's mass, so C-heavy furniture cannot tilt the
map off the payload's prior) and evaluated in logit space.  They fold
back into scores exactly under equal priors, so the demap returns the
three maps themselves:

    sY = L_{lo|hi=0}
    sM = L_hi + log(1 - s(L_{lo|hi=1})) - log(1 - s(L_{lo|hi=0}))
    sC = L_hi + log s(L_{lo|hi=1})      - log(1 - s(L_{lo|hi=0}))

The population is the QDA's held-out side (`&1`): word sites admitted,
dust, and the certified cells the store hands the refit -- split again
by `&2` (`color_model.head_sub_split`, the cmy7 head's own) into the
maps' fit side and a disjoint validation side.  A map below its floors
-- the marginal under cmy8's 6 / 2 / 3, a conditional under A4b's 40 fit
labels / 6 per class plus 20 validation rows -- leaves its piece to the
raw statistic under the bound (the cold start, R11's per-map fallback).
The head is adopted through cmy8's three-way gate on the validation
side: the chain's emitted scores against the raw ones, total strictly
better and neither furniture leg worse, every leg published on the fit
record.  cmy's dust leg is single-class at p120 -- the balance law lays
every dust cell M -- so it reports only how M cells read as M.

The erasure law composes (§2.7): a dead lo fits L_hi alone and the
erasure projects the folded scores onto (L_hi, L_hi, 0); a dead hi takes
no chain at all, so the lane emits the raw bounded lo statistic, (l, 0,
l), as before -- L_hi on a dead stream is not evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.special import logsumexp

from ..format import tile_codec
from ..lib import pava
from . import color_model
from .color_conditioning import (
    CONDITIONED_MIN_CLASS_LABELS,
    CONDITIONED_MIN_LABELS,
    CONDITIONED_MIN_VALIDATION,
)

#: The hi-first chain as (stream, sibling label bit): the hi marginal,
#: lo given hi = 0 (W vs Y), lo given hi = 1 (M vs C).  A map's population
#: is the states whose sibling bit matches, its label the stream's bit,
#: its statistic `cmy_soft_demap(scores, stream, sibling)` -- derived from
#: the label table, never typed out.
CHAIN_MAPS: tuple[tuple[int, int | None], ...] = ((0, None), (1, 0), (1, 1))

CHAIN_REASON_ADOPTED: str = "adopted"
CHAIN_REASON_NO_MAP: str = "no_map_qualified"
CHAIN_REASON_HELDOUT_STARVED: str = "heldout_starved"
CHAIN_REASON_GATE_FAILED: str = "validation_gate_failed"
CHAIN_REASON_HI_ERASED: str = "hi_erased"
MAP_REASON_ERASED: str = "stream_erased"
MAP_REASON_STARVED: str = "search_class_starved"
#: A leg that was never measured: negative, never NaN (the conditioning
#: and context idiom), so it can neither poison a comparison nor read as
#: a perfect one.
CHAIN_NLL_UNMEASURED: float = -1.0
_UNMEASURED = (CHAIN_NLL_UNMEASURED,) * 3

MapSlot = color_model.PavaMap | None


def chain_statistic(scores: np.ndarray, index: int) -> np.ndarray:
    stream, sibling = CHAIN_MAPS[index]
    values = np.asarray(scores, np.float64)
    given = (None if sibling is None
             else np.full(values.shape[0], sibling, np.uint8))
    return tile_codec.cmy_soft_demap(values, stream, given)


def map_population(columns: np.ndarray,
                   index: int) -> tuple[np.ndarray, np.ndarray]:
    stream, sibling = CHAIN_MAPS[index]
    bits = color_model.CMY_COLUMN_LABEL_BITS[np.asarray(columns, np.int64)]
    member = (np.ones(bits.shape[0], np.bool_) if sibling is None
              else bits[:, 1 - stream] == bool(sibling))
    return member, bits[:, stream].astype(np.int64)


#: cmy8's marginal floors in label space (`qualify_cmy8_support`'s
#: vocabulary): six labels per class, and two states per class with
#: three labels each.  A conditional map has one state per class by
#: construction, so it takes A4b's floors instead.
def map_refusal(fit_columns: np.ndarray, validation_columns: np.ndarray,
                index: int) -> str | None:
    member, labels = map_population(fit_columns, index)
    class_counts = np.bincount(labels[member], minlength=2)
    if CHAIN_MAPS[index][1] is None:
        state_counts = np.bincount(
            np.asarray(fit_columns, np.int64)[member],
            minlength=len(tile_codec.CMY_STATE_IDS))
        state_bits = color_model.CMY_COLUMN_LABEL_BITS[:, CHAIN_MAPS[index][0]]
        weak = [binary for binary in range(2) if int(class_counts[binary])
                < color_model.CMY8_CALIBRATION_MIN_CLASS_LABELS]
        if weak:
            return "class_labels:" + ",".join(str(value) for value in weak)
        thin = [binary for binary in range(2) if int(np.count_nonzero(
            state_counts[state_bits == bool(binary)]
            >= color_model.CMY8_CALIBRATION_MIN_LABELS_PER_STATE))
            < color_model.CMY8_CALIBRATION_MIN_STATES_PER_CLASS]
        if thin:
            return "state_diversity:" + ",".join(str(value) for value in thin)
        return None
    if (int(np.count_nonzero(member)) < CONDITIONED_MIN_LABELS
            or int(class_counts.min()) < CONDITIONED_MIN_CLASS_LABELS):
        return MAP_REASON_STARVED
    if (int(np.count_nonzero(map_population(validation_columns, index)[0]))
            < CONDITIONED_MIN_VALIDATION):
        return CHAIN_REASON_HELDOUT_STARVED
    return None


def fit_chain_map(scores: np.ndarray, columns: np.ndarray,
                  index: int) -> color_model.PavaMap:
    member, labels = map_population(columns, index)
    state_columns = np.asarray(columns, np.int64)[member]
    return replace(color_model.fit_component_pava(
        chain_statistic(np.asarray(scores, np.float64)[member], index),
        labels[member],
        pava.class_balanced_weights(state_columns,
                                    len(tile_codec.CMY_STATE_IDS))),
        logit_interpolation=True)


#: §2.7's fold in softplus form: -log(1 - s(b)) = softplus(b), log s(c) =
#: -softplus(-c), log(1 - s(c)) = -softplus(c).  Exact for any real
#: pieces, so `cmy_soft_demap` returns hi, lo|hi=0 and lo|hi=1 as given.
def fold_hi_first(hi: np.ndarray, lo_given_w: np.ndarray,
                  lo_given_m: np.ndarray) -> np.ndarray:
    lead = hi + np.logaddexp(0.0, lo_given_w)
    return np.stack((lead - np.logaddexp(0.0, -lo_given_m),
                     lead - np.logaddexp(0.0, lo_given_m),
                     np.asarray(lo_given_w, np.float64)), axis=-1)


def bounded(scores: np.ndarray, bound: float) -> np.ndarray:
    values = np.asarray(scores, np.float64)
    return values / np.maximum(
        1.0, np.max(np.abs(values), axis=1, keepdims=True) / bound)


@dataclass(frozen=True)
class CmyChain:
    maps: tuple[MapSlot, MapSlot, MapSlot]
    bound: float

    def apply(self, scores: np.ndarray) -> np.ndarray:
        raw = np.asarray(scores, np.float64)
        fallback = bounded(raw, self.bound)
        pieces = [
            chain_statistic(fallback, index) if calibration is None
            else calibration.llrs(chain_statistic(raw, index))
            for index, calibration in enumerate(self.maps)]
        return fold_hi_first(*pieces)


@dataclass(frozen=True)
class ChainFit:
    """What one chain fit did: the head (None unless the gate adopted
    it), why, each map's verdict, and the gate's three legs -- total,
    word, dust mean 4-state NLL on the validation side -- for the raw
    scores (incumbent) and the chain's (candidate)."""
    head: CmyChain | None
    reason: str
    map_reasons: tuple[str, str, str]
    incumbent_nll: tuple[float, float, float]
    candidate_nll: tuple[float, float, float]
    n_fit: int
    n_validation: int


#: `fit_detector`'s held-out loss form over the emitted scores: the
#: 4-state NLL with W pinned at 0, a plain mean per leg (an empty leg
#: reads +inf, as there, and so never refuses).
def gate_losses(scores: np.ndarray, columns: np.ndarray,
                kinds: np.ndarray) -> tuple[float, float, float]:
    values = np.asarray(scores, np.float64)
    logits = np.concatenate(
        (np.zeros((values.shape[0], 1), np.float64), values), axis=1)
    rows = np.arange(values.shape[0])
    nll = logsumexp(logits, axis=1) - logits[rows, columns]

    def leg(selected: np.ndarray) -> float:
        return float(np.mean(nll[selected])) if np.any(selected) else (
            float("inf"))

    return (leg(np.ones(rows.size, np.bool_)), leg(kinds == 0),
            leg(kinds == 1))


def _emitted(scores: np.ndarray, erased: tuple[int, ...],
             bound: float) -> np.ndarray:
    values = (color_model.cmy_erase_streams(scores, erased) if erased
              else np.asarray(scores, np.float64))
    return bounded(values, bound)


def _three_way(candidate: tuple[float, float, float],
               incumbent: tuple[float, float, float]) -> bool:
    slack = color_model.HEAD_GATE_SLACK
    return (candidate[0] + slack < incumbent[0]
            and candidate[1] <= incumbent[1] + slack
            and candidate[2] <= incumbent[2] + slack)


def fit_cmy_chain(scores: np.ndarray, columns: np.ndarray,
                  kinds: np.ndarray, site_keys: np.ndarray,
                  erased: tuple[int, ...], bound: float) -> ChainFit:
    values = np.asarray(scores, np.float64)
    labels = np.asarray(columns, np.int64)
    furniture = np.asarray(kinds, np.int8)
    fit_side = color_model.head_sub_split(site_keys)
    validation = ~fit_side
    counts = (int(np.count_nonzero(fit_side)),
              int(np.count_nonzero(validation)))
    if 0 in erased:
        return ChainFit(None, CHAIN_REASON_HI_ERASED,
                        (MAP_REASON_ERASED,) * 3, _UNMEASURED,
                        _UNMEASURED, *counts)
    maps: list[MapSlot] = []
    reasons: list[str] = []
    for index, (stream, _sibling) in enumerate(CHAIN_MAPS):
        refusal = (MAP_REASON_ERASED if stream in erased else map_refusal(
            labels[fit_side], labels[validation], index))
        maps.append(None if refusal else fit_chain_map(
            values[fit_side], labels[fit_side], index))
        reasons.append(refusal or CHAIN_REASON_ADOPTED)
    verdicts = (reasons[0], reasons[1], reasons[2])
    if all(calibration is None for calibration in maps):
        return ChainFit(None, CHAIN_REASON_NO_MAP, verdicts, _UNMEASURED,
                        _UNMEASURED, *counts)
    if not np.any(validation):
        return ChainFit(None, CHAIN_REASON_HELDOUT_STARVED, verdicts,
                        _UNMEASURED, _UNMEASURED, *counts)
    head = CmyChain((maps[0], maps[1], maps[2]), float(bound))
    gate_rows = (labels[validation], furniture[validation])
    incumbent = gate_losses(_emitted(values[validation], erased, bound),
                            *gate_rows)
    candidate = gate_losses(
        _emitted(head.apply(values[validation]), erased, bound), *gate_rows)
    adopted = _three_way(candidate, incumbent)
    return ChainFit(head if adopted else None,
                    CHAIN_REASON_ADOPTED if adopted
                    else CHAIN_REASON_GATE_FAILED,
                    verdicts, incumbent, candidate, *counts)
