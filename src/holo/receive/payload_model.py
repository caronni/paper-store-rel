"""Immutable typed records for :mod:`holo.receive.payload`.

The numerical algorithms live in ``payload.py``.  This module keeps their
replay substrate and staged-attempt results explicit, compact, immutable,
and independently validatable without importing placement or raster code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Protocol

import numpy as np

from . import detect, tiles
from .evidence_blocks import TileAttemptView

PAVA_PROFILE = "pava-v1"
CONTEXT_PROFILE = "ctx-pava-v1"
DetectorProfile = Literal["pava-v1", "ctx-pava-v1"]


class PlacementModelError(ValueError):
    """E022 output cannot identify one authoritative sample per patch cell."""


class RawLumaRaster(Protocol):
    """The small raster surface used by native and scale-lane views."""

    shape: tuple[int, int]

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray: ...


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"payload: {name} must be a non-empty string")
    return value


def _immutable(value: np.ndarray, dtype: np.dtype | type,
               shape: tuple[int, ...] | None = None) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype=dtype)
    if shape is not None and array.shape != shape:
        raise ValueError(f"payload: expected array shape {shape}, got {array.shape}")
    return np.frombuffer(array.tobytes(), dtype=np.dtype(dtype)).reshape(
        array.shape)


def _nonnegative(value: int, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)) or int(value) < 0:
        raise ValueError(f"payload: {name} must be a non-negative integer")
    return int(value)


def _sha256(value: str, name: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(f"payload: {name} must be lowercase SHA-256")
    return value


def divergence_identity(certificate_id: str, evidence_block_id: str) -> str:
    """Content identity of one certificate/evidence-block divergence pair."""
    _sha256(certificate_id, "certificate_id")
    _sha256(evidence_block_id, "evidence_block_id")
    return tiles.sha256_parts_le(
        b"holo/divergence/v3", certificate_id.encode("ascii"),
        evidence_block_id.encode("ascii"))


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """One physical acquisition viewed in one internally generated lane."""

    source_sha256: str
    lane_id: str

    def __post_init__(self) -> None:
        _sha256(self.source_sha256, "source_sha256")
        _identity(self.lane_id, "lane_id")


@dataclass(frozen=True, slots=True)
class WindowEvidence:
    """Replay-complete evidence for one accepted/redundant E022 window.

    ``segment_id`` identifies the window pose shared by every aligned sample;
    ``segment_local_cells_yx`` identifies each cell within that pose.
    ``reference_values`` is -1 for cargo and 0/1 only for format-predictable
    word/filler labels. Refused windows retain means/scores but carry no node
    or LLR arrays.
    """

    source: EvidenceSource
    placement_id: str
    patch_id: int
    region_id: str
    page: int
    redundant: bool
    segment_id: int
    segment_local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray
    raw_means: np.ndarray
    scores: np.ndarray
    reference_values: np.ndarray
    calibration_score_nodes: np.ndarray
    calibration_probability_nodes: np.ndarray
    baseline_printed_llr: np.ndarray
    printed_llr: np.ndarray
    accepted: bool
    refusal_reason: str
    n_search_0: int
    n_search_1: int
    n_heldout: int
    heldout_logloss: float | None
    detector_profile: DetectorProfile = PAVA_PROFILE
    context_decision_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, EvidenceSource):
            raise TypeError("payload: window source must be EvidenceSource")
        _identity(self.placement_id, "placement_id")
        _identity(self.region_id, "region_id")
        patch_id = _nonnegative(self.patch_id, "patch_id")
        page = _nonnegative(self.page, "page")
        segment_id = _nonnegative(self.segment_id, "segment_id")
        if type(self.redundant) is not bool:
            raise ValueError("payload: redundant must be boolean")
        page_cells = np.asarray(self.page_cells_yx)
        n_rows = page_cells.shape[0] if page_cells.ndim == 2 else -1
        arrays = (
            ("segment_local_cells_yx", self.segment_local_cells_yx,
             np.int32, (n_rows, 2)),
            ("page_cells_yx", page_cells, np.int32, (n_rows, 2)),
            ("scan_points_yx", self.scan_points_yx, np.float64, (n_rows, 2)),
            ("raw_means", self.raw_means, np.float32, (n_rows,)),
            ("scores", self.scores, np.float32, (n_rows,)),
            ("reference_values", self.reference_values, np.int8, (n_rows,)),
        )
        if n_rows < 0:
            raise ValueError("payload: page_cells_yx must have shape (N,2)")
        for name, value, dtype, shape in arrays:
            out = np.asarray(value)
            if out.shape != shape:
                raise ValueError(f"payload: {name} must have shape {shape}")
            if name in ("raw_means", "scores", "scan_points_yx") and not (
                    np.isfinite(out).all()):
                raise ValueError(f"payload: {name} must be finite")
            object.__setattr__(self, name, _immutable(out, dtype, shape))
        if n_rows and np.unique(self.page_cells_yx, axis=0).shape[0] != n_rows:
            raise ValueError("payload: one E022 window has duplicate page cells")
        if not np.all(np.isin(self.reference_values, (-1, 0, 1))):
            raise ValueError("payload: reference_values must be -1/0/1")
        nodes_s = np.asarray(self.calibration_score_nodes, np.float64).ravel()
        nodes_p = np.asarray(
            self.calibration_probability_nodes, np.float64).ravel()
        baseline = np.asarray(self.baseline_printed_llr, np.float32).ravel()
        selected = np.asarray(self.printed_llr, np.float32).ravel()
        if nodes_s.size != nodes_p.size or not (
                np.isfinite(nodes_s).all() and np.isfinite(nodes_p).all()
                and np.isfinite(baseline).all() and np.isfinite(selected).all()):
            raise ValueError("payload: calibration/LLR arrays are malformed")
        loss = (None if self.heldout_logloss is None
                else float(self.heldout_logloss))
        if self.accepted:
            if (nodes_s.size == 0 or baseline.size != n_rows
                    or selected.size != n_rows
                    or loss is None or not np.isfinite(loss) or loss < 0.0
                    or self.refusal_reason):
                raise ValueError("payload: accepted window lacks calibrated evidence")
            natural = detect.clamp_for(self.n_search)
            selected_bound = (
                detect.CTX_LLR_CLAMP
                if self.detector_profile == CONTEXT_PROFILE else natural)
            if (np.max(np.abs(baseline), initial=0.0) > natural + 1e-6
                    or np.max(np.abs(selected), initial=0.0)
                    > selected_bound + 1e-6):
                raise ValueError(
                    "payload: emitted LLR exceeds its historical profile bound")
        elif (nodes_s.size or baseline.size or selected.size
              or self.heldout_logloss is not None or not self.refusal_reason):
            raise ValueError("payload: refused window leaked calibrated evidence")
        if self.detector_profile not in (PAVA_PROFILE, CONTEXT_PROFILE):
            raise ValueError("payload: unknown detector profile")
        if self.detector_profile == CONTEXT_PROFILE:
            _identity(self.context_decision_id or "", "context_decision_id")
        elif self.context_decision_id is not None:
            raise ValueError("payload: baseline window names a context decision")
        for name in ("n_search_0", "n_search_1", "n_heldout"):
            _nonnegative(getattr(self, name), name)
        object.__setattr__(self, "patch_id", patch_id)
        object.__setattr__(self, "page", page)
        object.__setattr__(self, "segment_id", segment_id)
        object.__setattr__(self, "heldout_logloss", loss)
        object.__setattr__(self, "calibration_score_nodes",
                           _immutable(nodes_s, np.float64))
        object.__setattr__(self, "calibration_probability_nodes",
                           _immutable(nodes_p, np.float64))
        object.__setattr__(self, "baseline_printed_llr",
                           _immutable(baseline, np.float32))
        object.__setattr__(self, "printed_llr",
                           _immutable(selected, np.float32))

    @property
    def n_search(self) -> int:
        return self.n_search_0 + self.n_search_1


@dataclass(frozen=True, slots=True)
class ContextDecision:
    """Persistable sidecar for one exact E023b region decision."""

    decision_id: str
    region_id: str
    eligible: bool
    adopted: bool
    reason: str
    offsets: np.ndarray
    search_support_by_bin: np.ndarray
    validation_support_by_bin: np.ndarray
    search_observations_by_bin: np.ndarray
    validation_observations_by_bin: np.ndarray
    n_search: int
    n_search_0: int
    n_search_1: int
    n_search_observations: int
    n_validation: int
    n_validation_0: int
    n_validation_1: int
    n_validation_observations: int
    baseline_validation_logloss: float | None
    candidate_validation_logloss: float | None

    def __post_init__(self) -> None:
        _identity(self.decision_id, "context decision id")
        _identity(self.region_id, "context region id")
        if not self.reason or self.adopted and not self.eligible:
            raise ValueError("payload: invalid context decision state")
        for name, dtype in (
            ("offsets", np.float64),
            ("search_support_by_bin", np.float64),
            ("validation_support_by_bin", np.float64),
            ("search_observations_by_bin", np.int64),
            ("validation_observations_by_bin", np.int64),
        ):
            value = np.asarray(getattr(self, name), dtype=dtype).ravel()
            if (value.shape != (detect.N_CONTEXT_BINS,)
                    or not np.isfinite(value).all()
                    or (name != "offsets" and np.any(value < 0))):
                raise ValueError(f"payload: malformed context field {name}")
            object.__setattr__(self, name, _immutable(value, dtype))
        for name in (
            "n_search", "n_search_0", "n_search_1",
            "n_search_observations", "n_validation", "n_validation_0",
            "n_validation_1", "n_validation_observations",
        ):
            _nonnegative(getattr(self, name), name)
        for name in ("baseline_validation_logloss",
                     "candidate_validation_logloss"):
            value = getattr(self, name)
            if value is not None:
                loss = float(value)
                if not np.isfinite(loss) or loss < 0.0:
                    raise ValueError(
                        "payload: context loss must be finite and non-negative")
                object.__setattr__(self, name, loss)


@dataclass(frozen=True, slots=True)
class OwnedPageEvidence:
    """One-owner printed-domain payload evidence for a single page."""

    page: int
    cells_yx: np.ndarray
    printed_llr: np.ndarray
    window_indices: np.ndarray
    window_row_indices: np.ndarray

    def __post_init__(self) -> None:
        page = _nonnegative(self.page, "owned page")
        cells = np.asarray(self.cells_yx)
        n_rows = cells.shape[0] if cells.ndim == 2 else -1
        if n_rows < 0 or cells.shape[1:] != (2,):
            raise ValueError("payload: owned cells must have shape (N,2)")
        llr = np.asarray(self.printed_llr, np.float32).ravel()
        wi = np.asarray(self.window_indices, np.int32).ravel()
        ri = np.asarray(self.window_row_indices, np.int32).ravel()
        if not (llr.size == wi.size == ri.size == n_rows):
            raise ValueError("payload: owned-page arrays are not aligned")
        if not np.isfinite(llr).all():
            raise ValueError("payload: owned LLRs must be finite")
        if n_rows and (np.unique(cells, axis=0).shape[0] != n_rows
                       or np.any(np.lexsort((cells[:, 1], cells[:, 0]))
                                 != np.arange(n_rows))):
            raise ValueError("payload: owned cells must be unique row-major")
        object.__setattr__(self, "page", page)
        object.__setattr__(self, "cells_yx", _immutable(cells, np.int32))
        object.__setattr__(self, "printed_llr", _immutable(llr, np.float32))
        object.__setattr__(self, "window_indices", _immutable(wi, np.int32))
        object.__setattr__(self, "window_row_indices", _immutable(ri, np.int32))


def freeze_page_owners(
    candidates: Iterable[
        tuple[int, int, np.ndarray, np.ndarray, np.ndarray]],
    page_shape_yx: tuple[int, int],
) -> tuple[tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray], ...]:
    """One-owner competition shared by the K and color freezes (§8.2).

    ``candidates`` iterate in competition order — ascending
    ``(heldout_logloss, patch_id)`` — and the FIRST candidate observing a
    physical page cell owns it.  Each entry is ``(window_index, page,
    cells_yx, row_indices, values)`` already restricted to that window's
    payload cells; ``values`` has one row per cell (any column count).
    Returns, per ascending page, ``(page, cells_yx row-major int32, values,
    window_indices int32, row_indices int32)``.  Both codecs' historical
    per-cell competitions reduce to this exact shape: first occurrence in
    the ``np.unique`` key order is the best ``(loss, patch_id)`` owner, and
    ascending ``y * width + x`` keys are row-major cell order.
    """
    height, width = (int(value) for value in page_shape_yx)
    grouped: dict[
        int, list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    ] = {}
    for window_index, page, cells_yx, row_indices, values in candidates:
        cells = np.asarray(cells_yx, np.int64)
        if not cells.shape[0]:
            continue
        if np.any(
                (cells[:, 0] < 0) | (cells[:, 0] >= height)
                | (cells[:, 1] < 0) | (cells[:, 1] >= width)):
            raise PlacementModelError(
                "payload: owned candidate lies outside the page")
        keys = cells[:, 0] * np.int64(width) + cells[:, 1]
        grouped.setdefault(int(page), []).append((
            keys,
            np.full(keys.size, int(window_index), np.int32),
            np.asarray(row_indices, np.int32),
            np.asarray(values),
        ))
    output: list[
        tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for page in sorted(grouped):
        parts = grouped[page]
        keys = np.concatenate([part[0] for part in parts])
        unique_keys, owner_rows = np.unique(keys, return_index=True)
        window_indices = np.concatenate(
            [part[1] for part in parts])[owner_rows]
        row_indices = np.concatenate(
            [part[2] for part in parts])[owner_rows]
        values = np.concatenate(
            [part[3] for part in parts], axis=0)[owner_rows]
        cells = np.column_stack((
            unique_keys // np.int64(width),
            unique_keys % np.int64(width),
        )).astype(np.int32, copy=False)
        output.append((page, cells, values, window_indices, row_indices))
    return tuple(output)


@dataclass(frozen=True, slots=True)
class CaptureEvidence:
    """Complete same-lane evidence: all windows plus frozen owners."""

    source: EvidenceSource
    spec_id: str
    windows: tuple[WindowEvidence, ...]
    context_decisions: tuple[ContextDecision, ...]
    pages: tuple[OwnedPageEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, EvidenceSource):
            raise TypeError("payload: capture source must be EvidenceSource")
        _identity(self.spec_id, "spec_id")
        if any(row.source != self.source for row in self.windows):
            raise ValueError("payload: window belongs to another source")
        if len({row.placement_id for row in self.windows}) != len(self.windows):
            raise ValueError("payload: duplicate placement ids")
        if tuple(sorted(row.page for row in self.pages)) != tuple(
                row.page for row in self.pages):
            raise ValueError("payload: owned pages must be sorted")
        if len({row.page for row in self.pages}) != len(self.pages):
            raise ValueError("payload: duplicate owned page")
        # Validate owner rows in window-sized batches (the color capture's
        # vectorized template).  The former per-cell Python loop performed
        # two tiny array comparisons per owned cell, up to three times per
        # K lane (gen-0, refined, prune-rebuild); the first invalid row and
        # its message class are preserved exactly.
        n_windows = len(self.windows)
        window_pages = np.asarray(
            tuple(row.page for row in self.windows), np.int64)
        window_sizes = np.asarray(
            tuple(row.page_cells_yx.shape[0] for row in self.windows),
            np.int64)
        window_accepted = np.asarray(
            tuple(row.accepted for row in self.windows), np.bool_)
        for page in self.pages:
            wi = page.window_indices.astype(np.int64)
            if not wi.size:
                continue
            outside = (wi < 0) | (wi >= n_windows)
            if n_windows == 0:
                raise ValueError("payload: owner points outside window ledger")
            ri = page.window_row_indices.astype(np.int64)
            safe = np.where(outside, 0, wi)
            mismatch = (
                ~window_accepted[safe]
                | (window_pages[safe] != page.page)
                | (ri < 0)
                | (ri >= window_sizes[safe])
            ) & ~outside
            candidate = np.flatnonzero(~(outside | mismatch))
            if candidate.size:
                order = candidate[
                    np.argsort(wi[candidate], kind="stable")]
                ordered_windows = wi[order]
                starts = np.flatnonzero(np.concatenate((
                    np.asarray((True,)),
                    ordered_windows[1:] != ordered_windows[:-1],
                )))
                stops = np.concatenate(
                    (starts[1:], np.asarray((order.size,))))
                for start, stop in zip(starts, stops, strict=True):
                    selected = order[start:stop]
                    window = self.windows[int(ordered_windows[start])]
                    rows_selected = ri[selected]
                    cells_match = np.all(
                        page.cells_yx[selected]
                        == window.page_cells_yx[rows_selected],
                        axis=1,
                    )
                    llr_match = (
                        page.printed_llr[selected]
                        == window.printed_llr[rows_selected]
                    )
                    bad = ~(cells_match & llr_match)
                    if np.any(bad):
                        mismatch[selected[bad]] = True
            invalid = np.flatnonzero(outside | mismatch)
            if invalid.size:
                if outside[int(invalid[0])]:
                    raise ValueError(
                        "payload: owner points outside window ledger")
                raise ValueError("payload: owner/window evidence mismatch")

    @property
    def lane_id(self) -> str:
        return self.source.lane_id


@dataclass(frozen=True, slots=True)
class DivergenceRecord:
    """Non-gating disagreement counts for one certificate/frontier pair.

    The linked records supply the address and the counts supply the rate.
    """

    divergence_id: str
    certificate_id: str
    evidence_block_id: str
    n_observed: int
    n_disagree: int

    def __post_init__(self) -> None:
        for name in ("divergence_id", "certificate_id", "evidence_block_id"):
            _sha256(getattr(self, name), name)
        observed = _nonnegative(self.n_observed, "divergence observed count")
        disagree = _nonnegative(self.n_disagree, "divergence disagreement count")
        if observed < 1 or disagree > observed:
            raise ValueError("payload: invalid divergence counts")
        if self.divergence_id != divergence_identity(
                self.certificate_id, self.evidence_block_id):
            raise ValueError("payload: divergence id is not content-derived")

    @property
    def disagreement_rate(self) -> float:
        return self.n_disagree / self.n_observed


__all__ = [
    "CONTEXT_PROFILE", "PAVA_PROFILE", "CaptureEvidence",
    "ContextDecision", "DetectorProfile", "DivergenceRecord",
    "EvidenceSource",
    "OwnedPageEvidence",
    "PlacementModelError", "RawLumaRaster",
    "WindowEvidence", "divergence_identity", "freeze_page_owners",
]
