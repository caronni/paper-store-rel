"""The calibration arms: same production machinery, different populations.

WHAT THE PRODUCTION K HEAD IS (read from the tree, not from memory):

* `_payload_sampling._scores` — per WINDOW, the sampled means are turned
  into scores by that window's OWN median and mean-absolute-deviation.
  A per-window affine photometric normalization is therefore already in
  the shipped path, before any calibration.
* `_payload_sampling._calibrate` -> `detect.fit_calibration` — the
  `pava-v1` isotonic score->P(ink) map is fitted per WINDOW, on that
  window's OWN FORMAT-KNOWN cells only (BCH word sites; this row has
  `n_filler = 0`), split by the absolute-cell parity
  `(131*y + 17*x) & 1` into a SEARCH half that fits and a HELDOUT half
  that never fits and never gates quality.  Bars: >= 10 labels per class
  in SEARCH, >= 10 HELDOUT labels.
* `_payload_context.apply_region_context` -> `detect.fit_context` — the
  nine-bin `ctx-pava-v1` additive-logit correction is fitted per REGION,
  pooled over every window of that region, on the same format-known
  labels, and adopted only on a strict weighted held-out log-loss gain.

So the incumbent's granularity is: PHOTOMETRY per window, CALIBRATION
per window, CONTEXT per region.  On this capture each ladder lane has
exactly ONE region covering the whole sheet, so the context arm is
page-global and the marginal head is window-local — and neither of them
has ever seen a certified payload cell as a label.

THE ARMS.  Every arm changes exactly one thing: the population of
LABELS the marginal PAVA is fitted on.  The score transform, the parity
split, the acceptance bars, the region context arm, the owner freeze,
the block materialization and the certificate gate are the production
code, untouched and shared.

  R   incumbent recipe — this window's format-known SEARCH-parity cells.
  W   window-local     — R's labels UNION this window's certified payload
                         cells (a certified tile's printed field is
                         exact, from `records.printed_cells_from_record`).
  H1  +1 window ring   — W's labels pooled over every window whose cell
                         bbox meets this window's bbox dilated by one
                         window extent.
  H2  +2 window rings  — the same at two window extents.
  G   page-global      — one PAVA over every window of the lane.

R is the reproduction control (it must reproduce the archived evidence
bit for bit) and G is the "refit at all" control that separates LOCALITY
from the mere presence of certified labels.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

import numpy as np

from holo.receive import detect
from holo.receive._payload_context import apply_region_context
from holo.receive.payload import freeze_capture_evidence
from holo.receive.payload_model import PAVA_PROFILE, WindowEvidence

ARM_IDS = ("R", "W", "H1", "H2", "G")
ARM_RINGS: dict[str, int | None] = {
    "R": 0, "W": 0, "H1": 1, "H2": 2, "G": None}
# R is production spelled in this instrument's own vocabulary: window-only
# scope, format-known labels.  Its blocks must come out bit-identical to
# the archived ones, which is the instrument's honesty proof.
ARM_FURNITURE_ONLY = frozenset({"R"})


def parity_mask(page_cells_yx: np.ndarray) -> np.ndarray:
    """The registered absolute-cell HELDOUT parity (E023, `_calibrate`)."""
    cells = np.asarray(page_cells_yx, np.int64)
    return ((131 * cells[:, 0] + 17 * cells[:, 1]) & 1).astype(bool)


@dataclass(frozen=True)
class LabelPool:
    """Flat, patch-ordered label/score pool over one lane's windows.

    `site_id` is the page-major physical cell id, so the same printed
    cell seen by two overlapping windows carries the same id and can be
    de-duplicated exactly (marginal PAVA is unweighted and refuses
    duplicate physical labels — `detect.CalibrationObservations`).
    """

    order: tuple[int, ...]          # window index per pool slice
    start: np.ndarray               # (n_windows,) slice starts
    stop: np.ndarray                # (n_windows,) slice stops
    site_id: np.ndarray             # int64
    score: np.ndarray               # float64
    label: np.ndarray               # int8, -1 = unlabelled
    furniture: np.ndarray           # bool, format-known (the R population)
    search: np.ndarray              # bool, SEARCH parity
    bbox: np.ndarray                # (n_windows, 4) y0,x0,y1,x1 in cells
    extent: np.ndarray              # (n_windows, 2) window cell extent


def build_label_pool(rows: tuple[WindowEvidence, ...], spec,
                     certified: np.ndarray) -> LabelPool:
    """Pool every window's scores with its production + certified labels."""
    width = int(spec.layout.cells_yx[1])
    starts: list[int] = []
    stops: list[int] = []
    site_parts: list[np.ndarray] = []
    score_parts: list[np.ndarray] = []
    label_parts: list[np.ndarray] = []
    furniture_parts: list[np.ndarray] = []
    search_parts: list[np.ndarray] = []
    bbox = np.zeros((len(rows), 4), np.int64)
    extent = np.zeros((len(rows), 2), np.int64)
    cursor = 0
    for index, row in enumerate(rows):
        cells = np.asarray(row.page_cells_yx, np.int64)
        reference = np.asarray(row.reference_values, np.int8)
        known = certified[cells[:, 0], cells[:, 1]]
        label = np.where(reference >= 0, reference, known).astype(np.int8)
        # A certified tile's printed field includes its own word sites, so
        # the two authorities must agree wherever both speak.
        both = (reference >= 0) & (known >= 0)
        if np.any(reference[both] != known[both]):
            raise SystemExit(
                "label pool: a certificate disagrees with the format word "
                "sites it contains")
        site_parts.append(cells[:, 0] * width + cells[:, 1])
        score_parts.append(np.asarray(row.scores, np.float64))
        label_parts.append(label)
        furniture_parts.append(reference >= 0)
        search_parts.append(~parity_mask(cells))
        starts.append(cursor)
        cursor += cells.shape[0]
        stops.append(cursor)
        bbox[index] = (cells[:, 0].min(), cells[:, 1].min(),
                       cells[:, 0].max() + 1, cells[:, 1].max() + 1)
        extent[index] = (bbox[index, 2] - bbox[index, 0],
                         bbox[index, 3] - bbox[index, 1])
    return LabelPool(
        tuple(range(len(rows))),
        np.asarray(starts, np.int64), np.asarray(stops, np.int64),
        np.concatenate(site_parts), np.concatenate(score_parts),
        np.concatenate(label_parts), np.concatenate(furniture_parts),
        np.concatenate(search_parts), bbox, extent)


def ring_members(pool: LabelPool, index: int, ring: int) -> list[int]:
    """Windows whose cell bbox meets this window's bbox dilated by `ring`.

    `ring = 0` is the window alone — the brief's "window-only" arm — and
    each further ring dilates by ONE of this window's own cell extents,
    so the halo is measured in windows, not in an invented cell radius.
    """
    if ring <= 0:
        return [index]
    y0, x0, y1, x1 = pool.bbox[index]
    height, width = pool.extent[index]
    pad_y, pad_x = int(ring * height), int(ring * width)
    other = pool.bbox
    hit = ((other[:, 0] < y1 + pad_y) & (other[:, 2] > y0 - pad_y)
           & (other[:, 1] < x1 + pad_x) & (other[:, 3] > x0 - pad_x))
    members = [int(value) for value in np.flatnonzero(hit) if value != index]
    return [index, *members]


def _pool_rows(pool: LabelPool, members: list[int]) -> np.ndarray:
    """Row indices of the members' slices, in member order."""
    return np.concatenate([
        np.arange(pool.start[member], pool.stop[member], dtype=np.int64)
        for member in members])


def fit_rows(pool: LabelPool, members: list[int],
             furniture_only: bool) -> np.ndarray:
    """SEARCH-parity labelled pool rows, one per physical cell.

    De-duplication keeps the FIRST observation of each physical cell in
    member order (the target window first, then ascending window index),
    so a cell the target window saw itself is always read through the
    target window's own photometric normalization.
    """
    rows = _pool_rows(pool, members)
    eligible = (pool.label[rows] >= 0) & pool.search[rows]
    if furniture_only:
        eligible &= pool.furniture[rows]
    labelled = rows[eligible]
    _unique, first = np.unique(pool.site_id[labelled], return_index=True)
    return labelled[np.sort(first)]


@dataclass(frozen=True)
class MarginalFit:
    """One fitted (or refused) marginal head plus its label counts."""

    calibration: detect.Calibration | None
    reason: str
    n_search_0: int
    n_search_1: int
    n_nodes_clipped: int = 0


# DECLARED DEVIATION (the only one in this instrument).  A `pava-v1` map's
# LLR bound is log(n_fit + 1): production fits ~490 format-known labels per
# window, so that bound is ~6.2 and every emitted LLR sits far inside the
# receiver's registered emitted-evidence clamp `detect.CTX_LLR_CLAMP` = 12.
# A certified-label population is 10^4-10^6 wide, its bound passes 12, and
# `WindowEvidence` then REFUSES the row ("emitted LLR exceeds its
# historical profile bound") for any cell with no valid context
# neighbourhood — `detect.apply_context_offsets` clamps only the cells it
# corrects.  We therefore clamp the fitted PROBABILITY NODES to the range
# that clamp implies, once, at the fit: the map itself can no longer exceed
# +/-12, which every downstream re-derivation respects.  It is an exact
# no-op for arm R (its own pmin floor is 2e-3, far above sigma(-12)) and
# conservative everywhere else: |LLR| = 12 is already P(ink) = 0.999994.
_NODE_FLOOR = float(1.0 / (1.0 + np.exp(detect.CTX_LLR_CLAMP)))


def fit_for_window(pool: LabelPool, index: int, ring: int | None,
                   furniture_only: bool,
                   cache: dict[object, MarginalFit]) -> MarginalFit:
    """Fit one window's marginal PAVA on this arm's label population.

    The cache key is the MEMBER SET, so two windows with the same halo
    share one fit and the page-global arm fits exactly once per lane.
    """
    if ring is None:
        key: object = ("global", furniture_only)
        members = list(pool.order)
    else:
        members = ring_members(pool, index, ring)
        key = (furniture_only, tuple(members))
    hit = cache.get(key)
    if hit is not None:
        return hit
    selected = fit_rows(pool, members, furniture_only)
    labels = pool.label[selected]
    n1 = int(labels.sum())
    n0 = int(labels.size - n1)
    if min(n0, n1) < detect.CAL_MIN_PER_CLASS:
        result = MarginalFit(None, "search_class_starved", n0, n1)
    else:
        knots, probabilities = detect._pava_nodes(
            pool.score[selected], labels)
        clipped = np.clip(probabilities, _NODE_FLOOR, 1.0 - _NODE_FLOOR)
        result = MarginalFit(
            detect.Calibration(
                f"e9/{ring}/{furniture_only}/{index}",
                knots, clipped, int(labels.size)),
            "accepted", n0, n1,
            int(np.count_nonzero(clipped != probabilities)))
    cache[key] = result
    return result


@dataclass(frozen=True)
class WindowFit:
    """One window's arm outcome, kept for the calibration-delta table."""

    patch_id: int
    accepted: bool
    reason: str
    n_search: int
    n_search_0: int
    n_search_1: int
    n_members: int
    t50: float
    t50_clamped: bool
    n_nodes_clipped: int
    centre_yx: tuple[float, float]


def _threshold(calibration: detect.Calibration) -> tuple[float, bool]:
    """Score at which the fitted map crosses P(ink) = 0.5."""
    probabilities = np.asarray(calibration.probabilities, np.float64)
    knots = np.asarray(calibration.knots, np.float64)
    if probabilities[0] >= 0.5:
        return float(knots[0]), True
    if probabilities[-1] <= 0.5:
        return float(knots[-1]), True
    return float(np.interp(0.5, probabilities, knots)), False


def apply_arm(rows: tuple[WindowEvidence, ...], pool: LabelPool,
              arm: str) -> tuple[tuple[WindowEvidence, ...],
                                 tuple[WindowFit, ...], float]:
    """Refit every window under one arm and return production-shaped rows."""
    ring = ARM_RINGS[arm]
    furniture_only = arm in ARM_FURNITURE_ONLY
    cache: dict[object, MarginalFit] = {}
    out: list[WindowEvidence] = []
    fits: list[WindowFit] = []
    started = time.process_time()
    for index, row in enumerate(rows):
        cells = np.asarray(row.page_cells_yx, np.int64)
        reference = np.asarray(row.reference_values, np.int8)
        heldout = parity_mask(cells) & (reference >= 0)
        n_heldout = int(heldout.sum())
        n_members = (len(pool.order) if ring is None
                     else len(ring_members(pool, index, ring)))
        fitted = fit_for_window(pool, index, ring, furniture_only, cache)
        centre = (float(0.5 * (pool.bbox[index, 0] + pool.bbox[index, 2])),
                  float(0.5 * (pool.bbox[index, 1] + pool.bbox[index, 3])))
        calibration = fitted.calibration
        if calibration is None or n_heldout < detect.CAL_MIN_HELDOUT:
            reason = (fitted.reason if calibration is None
                      else "heldout_starved")
            out.append(replace(
                row, calibration_score_nodes=np.zeros(0),
                calibration_probability_nodes=np.zeros(0),
                baseline_printed_llr=np.zeros(0, np.float32),
                printed_llr=np.zeros(0, np.float32), accepted=False,
                refusal_reason=reason, heldout_logloss=None,
                n_search_0=0, n_search_1=0, n_heldout=n_heldout,
                detector_profile=PAVA_PROFILE, context_decision_id=None))
            fits.append(WindowFit(int(row.patch_id), False, reason,
                                  0, 0, 0, n_members, float("nan"), True, 0,
                                  centre))
            continue
        scores = np.asarray(row.scores, np.float64)
        llr = np.asarray(calibration.llr(scores), np.float32)
        probability = calibration.probability(scores[heldout])
        labels = reference[heldout].astype(np.float64)
        loss = float(-np.mean(
            labels * np.log(probability)
            + (1.0 - labels) * np.log(1.0 - probability)))
        threshold, clamped = _threshold(calibration)
        out.append(replace(
            row, calibration_score_nodes=calibration.knots,
            calibration_probability_nodes=calibration.probabilities,
            baseline_printed_llr=llr, printed_llr=llr, accepted=True,
            refusal_reason="", heldout_logloss=loss,
            n_search_0=fitted.n_search_0, n_search_1=fitted.n_search_1,
            n_heldout=n_heldout, detector_profile=PAVA_PROFILE,
            context_decision_id=None))
        fits.append(WindowFit(
            int(row.patch_id), True, "accepted",
            fitted.n_search_0 + fitted.n_search_1,
            fitted.n_search_0, fitted.n_search_1, n_members, threshold,
            clamped, fitted.n_nodes_clipped, centre))
    return tuple(out), tuple(fits), time.process_time() - started


def context_and_freeze(rows: tuple[WindowEvidence, ...], source, spec):
    """The production context arm + owner freeze over one arm's rows."""
    profiled, decisions = apply_region_context(rows)
    return freeze_capture_evidence(source, spec, profiled, decisions), decisions


__all__ = [
    "ARM_FURNITURE_ONLY", "ARM_IDS", "ARM_RINGS", "LabelPool", "MarginalFit",
    "WindowFit", "apply_arm", "build_label_pool", "context_and_freeze",
    "fit_for_window", "fit_rows", "parity_mask", "ring_members",
]
