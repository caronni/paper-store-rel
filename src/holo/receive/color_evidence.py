"""The durable colour evidence contract: records, freeze, and blocks.

Split out of :mod:`holo.receive.color_payload` (2026-08-20) at the seam
that module's own header names — the record/freeze/emit half, kept
apart from the region sampling-and-fit half that produces it.  Nothing
here samples a raster, fits a detector, or schedules anything: these are
the immutable rows the collection pass mints, the one-owner page freeze
that validates them, and the conversion into shared physical evidence
blocks.

The four record types plus :func:`color_blocks_from_frontier` remain
part of ``color_payload``'s public surface and are re-exported there, so
this split moved code and not one import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..format.descriptor import FormatSpec
from .color_anchoring import (
    COLOR_CMY7_KIND,
    COLOR_CMY8_KIND,
    _readonly,
)
from .color_conditioning import ConditioningSummary
from .color_context import ContextSummary
from .color_locality import WindowPhotometrySummary
from .color_pool import _payload_site_mask
from .color_registration import PlaneResidual
from .color_stack import HEAD_SATURATION_UNMEASURED
from .evidence_blocks import (
    EvidenceBlock,
    EvidenceOrigin,
    OwnedPageRows,
    blocks_from_owner_pages,
    evidence_arity,
)
from .payload_model import EvidenceSource, freeze_page_owners


@dataclass(frozen=True, slots=True)
class ColorWindowEvidence:
    """One accepted window's aligned physical-state evidence."""

    source: EvidenceSource
    placement_id: str
    patch_id: int
    region_id: str
    page: int
    page_cells_yx: np.ndarray
    evidence_values: np.ndarray
    heldout_logloss: float
    evidence_kind: str
    dependency_certificate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, EvidenceSource):
            raise TypeError("color payload: source must be EvidenceSource")
        if not self.placement_id or not self.region_id:
            raise ValueError("color payload: window identities must be nonempty")
        if type(self.patch_id) is not int or self.patch_id < 0:
            raise ValueError("color payload: patch id must be nonnegative")
        if type(self.page) is not int or self.page < 0:
            raise ValueError("color payload: page must be nonnegative")
        cells = np.asarray(self.page_cells_yx)
        values = np.asarray(self.evidence_values)
        if self.evidence_kind not in (COLOR_CMY7_KIND, COLOR_CMY8_KIND):
            raise ValueError("color payload: unknown evidence kind")
        arity = evidence_arity(self.evidence_kind)
        if cells.ndim != 2 or cells.shape[1:] != (2,):
            raise ValueError("color payload: cells must have shape (N,2)")
        if values.shape != (cells.shape[0], arity):
            raise ValueError(
                f"color payload: values must have shape "
                f"({cells.shape[0]},{arity})")
        if not np.isfinite(values).all():
            raise ValueError("color payload: evidence values must be finite")
        if cells.shape[0] and np.unique(cells, axis=0).shape[0] != cells.shape[0]:
            raise ValueError("color payload: one window repeats a page cell")
        loss = float(self.heldout_logloss)
        if not np.isfinite(loss) or loss < 0.0:
            raise ValueError("color payload: held-out loss must be finite")
        dependencies = tuple(self.dependency_certificate_ids)
        if dependencies != tuple(sorted(set(dependencies))):
            raise ValueError(
                "color payload: dependency ids must be sorted and unique")
        if any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in dependencies):
            raise ValueError(
                "color payload: dependency ids must be lowercase SHA-256")
        object.__setattr__(self, "page_cells_yx",
                           _readonly(cells, np.int32))
        object.__setattr__(self, "evidence_values",
                           _readonly(values, np.float32))
        object.__setattr__(self, "heldout_logloss", loss)
        object.__setattr__(
            self, "dependency_certificate_ids", dependencies)


@dataclass(frozen=True, slots=True)
class ColorOwnedPageEvidence:
    """One deterministic owner per observed color payload cell."""

    page: int
    cells_yx: np.ndarray
    evidence_values: np.ndarray
    window_indices: np.ndarray
    window_row_indices: np.ndarray

    def __post_init__(self) -> None:
        cells = np.asarray(self.cells_yx)
        values = np.asarray(self.evidence_values)
        wi = np.asarray(self.window_indices)
        ri = np.asarray(self.window_row_indices)
        if cells.ndim != 2 or cells.shape[1:] != (2,):
            raise ValueError("color payload: owned cells must have shape (N,2)")
        n_rows = cells.shape[0]
        if (values.ndim != 2 or values.shape[0] != n_rows
                or wi.shape != (n_rows,) or ri.shape != (n_rows,)):
            raise ValueError("color payload: owned arrays are not aligned")
        if not np.isfinite(values).all():
            raise ValueError("color payload: owned evidence must be finite")
        if n_rows:
            ascending = (
                (cells[1:, 0] > cells[:-1, 0])
                | (
                    (cells[1:, 0] == cells[:-1, 0])
                    & (cells[1:, 1] > cells[:-1, 1])
                )
            )
            if not np.all(ascending):
                # Keep precise diagnostics on the malformed-input path
                # without sorting every valid full-page frontier twice.
                if np.unique(cells, axis=0).shape[0] != n_rows:
                    raise ValueError("color payload: owned cells repeat")
                raise ValueError(
                    "color payload: owned cells are not row-major")
        object.__setattr__(self, "cells_yx", _readonly(cells, np.int32))
        object.__setattr__(
            self, "evidence_values", _readonly(values, np.float32))
        object.__setattr__(self, "window_indices",
                           _readonly(wi, np.int32))
        object.__setattr__(self, "window_row_indices",
                           _readonly(ri, np.int32))


@dataclass(frozen=True, slots=True)
class ColorRegionSummary:
    """Transient operational facts for one region/page detector fit."""

    region_id: str
    page: int
    accepted: bool
    reason: str
    n_patches: int
    n_train: int
    n_heldout: int
    class_counts: tuple[int, ...]
    baseline_heldout_logloss: float | None
    selected_heldout_logloss: float | None
    registration_adopted: bool
    # P8: MEASURED registration, never zeroed to signal non-adoption
    # (applied correction = these residuals iff registration_adopted).
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual]
    dependency_certificate_ids: tuple[str, ...] = ()
    calibration_labels: int = 0
    component_supported: tuple[bool, ...] = ()
    component_support_reasons: tuple[str | None, ...] = ()
    # P1 (append-only, risk R4).  CMY7 regions only: a CMY8 region has no
    # head and leaves the reason empty, which is what gates the
    # `color.cmy7_head.*` diagnostic keys.  ``saturation_fraction`` is the
    # 19% canary — the share of EMITTED cells whose L-infinity divisor
    # exceeded 1 — and is measured whether or not a head was adopted, so
    # the force-null and live arms are directly comparable.
    cmy7_head_reason: str = ""
    cmy7_head_adopted: bool = False
    cmy7_head_temperature: float = 1.0
    cmy7_saturation_fraction: float = 0.0
    # PK3.1 (append-only, risk R4): the same population's PRE-head
    # saturation — what A4's floor gated on, and the "before" to the field
    # above's "after" within ONE run.  Negative = NOT MEASURED (no fitted
    # head reached the floor), never confusable with a measured 0.0.
    cmy7_baseline_saturation_fraction: float = HEAD_SATURATION_UNMEASURED
    # PK4.1 (append-only, risk R4): the EFFECTIVE floor the line above was
    # judged against.  Same sentinel convention: negative = not measured.
    cmy7_head_saturation_floor: float = HEAD_SATURATION_UNMEASURED
    # PK4 / A3 (append-only, risk R4): the per-window photometric maps, as
    # ONE published record that validates its own invariants
    # (color_locality.WindowPhotometrySummary).  Kind-AGNOSTIC — a cmy8
    # region fits these too — so unlike the cmy7 head keys the diagnostic
    # is gated on the arm having run at all, never on the codec.
    window_photometry: WindowPhotometrySummary = WindowPhotometrySummary()
    # PK10 / A4b (append-only, risk R4): the KnownField-conditioned
    # marginals.  CMY8-only by construction, so an empty ``reason`` is
    # this record's discriminator exactly as a nonempty one is the cmy7
    # head's.
    conditioning: ConditioningSummary = ConditioningSummary()
    # PK5 / A5 (append-only, risk R4): the neighbourhood corrector.
    # Kind-AGNOSTIC like A3's record — both codecs fit context — so the
    # empty reason means "the arm never ran", never "wrong codec".
    context: ContextSummary = ContextSummary()
    # PK4.3 (append-only): the SUPPLEMENTAL lane's forced arm, empty on
    # every ordinary/mop-up/refinement region.  Published per region and
    # not only per lane because a u-lane's whole claim is per-region
    # ("this region's arm was forced, and here is what it then read"),
    # and a diagnostics row must never have to join two events to know.
    uplift_arm: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.uplift_arm, str):
            raise TypeError("color payload: uplift arm must be a string")
        if not isinstance(self.window_photometry, WindowPhotometrySummary):
            raise TypeError(
                "color payload: window photometry must be a summary record")
        if not isinstance(self.conditioning, ConditioningSummary):
            raise TypeError(
                "color payload: conditioning must be a summary record")
        if not isinstance(self.context, ContextSummary):
            raise TypeError(
                "color payload: context must be a summary record")
        if not isinstance(self.cmy7_head_reason, str):
            raise TypeError("color payload: head reason must be a string")
        if type(self.cmy7_head_adopted) is not bool:
            raise TypeError("color payload: head adoption must be a bool")
        temperature = float(self.cmy7_head_temperature)
        fraction = float(self.cmy7_saturation_fraction)
        # The baseline and the floor additionally admit the sentinel.
        baseline = float(self.cmy7_baseline_saturation_fraction)
        floor = float(self.cmy7_head_saturation_floor)
        if not np.isfinite(temperature) or temperature <= 0.0:
            raise ValueError("color payload: head temperature must be > 0")
        if not 0.0 <= fraction <= 1.0 or not (
                0.0 <= baseline <= 1.0
                or baseline == HEAD_SATURATION_UNMEASURED):
            raise ValueError(
                "color payload: saturation fraction must be a fraction")
        # The FLOOR is a published record of what the ladder compared
        # against, not a claim about a population, so it admits any
        # nonnegative value a caller could have set (the sweep hatch
        # itself refuses anything outside [0, 1]; an in-process test may
        # legitimately push it past 1 to force a refusal).
        if not np.isfinite(floor) or (
                floor < 0.0 and floor != HEAD_SATURATION_UNMEASURED):
            raise ValueError("color payload: invalid head saturation floor")
        object.__setattr__(self, "cmy7_head_temperature", temperature)
        object.__setattr__(self, "cmy7_saturation_fraction", fraction)
        object.__setattr__(
            self, "cmy7_baseline_saturation_fraction", baseline)
        object.__setattr__(self, "cmy7_head_saturation_floor", floor)
        if not self.region_id:
            raise ValueError("color payload: region id must be nonempty")
        if type(self.page) is not int or self.page < 0:
            raise ValueError("color payload: region page must be nonnegative")
        if type(self.accepted) is not bool or not isinstance(self.reason, str):
            raise TypeError("color payload: invalid region disposition")
        if any(type(value) is not int or value < 0 for value in (
                self.n_patches, self.n_train, self.n_heldout,
                self.calibration_labels)):
            raise ValueError("color payload: invalid region support count")
        if (not isinstance(self.class_counts, tuple)
                or any(type(value) is not int or value < 0
                       for value in self.class_counts)):
            raise ValueError("color payload: invalid class counts")
        for value in (
                self.baseline_heldout_logloss,
                self.selected_heldout_logloss):
            if value is not None and (
                    not np.isfinite(float(value)) or float(value) < 0.0):
                raise ValueError(
                    "color payload: invalid region held-out loss")
        if (not isinstance(self.residuals, tuple)
                or len(self.residuals) != 3
                or any(not isinstance(value, PlaneResidual)
                       for value in self.residuals)):
            raise ValueError("color payload: region needs C/M/Y residuals")
        dependencies = tuple(self.dependency_certificate_ids)
        if dependencies != tuple(sorted(set(dependencies))):
            raise ValueError(
                "color payload: region dependencies are not canonical")
        if any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in dependencies):
            raise ValueError(
                "color payload: region dependency ids must be SHA-256")
        component_supported = tuple(self.component_supported)
        component_reasons = tuple(self.component_support_reasons)
        if (
            len(component_supported) != len(component_reasons)
            or len(component_supported) not in (0, 3)
            or any(type(value) is not bool for value in component_supported)
            or any(
                value is not None and not isinstance(value, str)
                for value in component_reasons
            )
            or any(
                supported != (reason is None)
                for supported, reason in zip(
                    component_supported,
                    component_reasons,
                    strict=True,
                )
            )
        ):
            raise ValueError(
                "color payload: invalid component calibration status")
        object.__setattr__(
            self, "dependency_certificate_ids", dependencies)
        object.__setattr__(
            self, "component_supported", component_supported)
        object.__setattr__(
            self, "component_support_reasons", component_reasons)


@dataclass(frozen=True, slots=True)
class ColorCaptureEvidence:
    """Complete lane-local color evidence after owner selection."""

    source: EvidenceSource
    spec_id: str
    evidence_kind: str
    windows: tuple[ColorWindowEvidence, ...]
    pages: tuple[ColorOwnedPageEvidence, ...]
    regions: tuple[ColorRegionSummary, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, EvidenceSource):
            raise TypeError("color payload: capture source is invalid")
        if not isinstance(self.spec_id, str) or not self.spec_id:
            raise ValueError("color payload: capture spec id must be nonempty")
        if self.evidence_kind not in (COLOR_CMY7_KIND, COLOR_CMY8_KIND):
            raise ValueError("color payload: capture evidence kind is invalid")
        arity = evidence_arity(self.evidence_kind)
        if any(not isinstance(row, ColorWindowEvidence)
               for row in self.windows):
            raise TypeError("color payload: capture has a foreign window")
        if any(not isinstance(row, ColorOwnedPageEvidence)
               for row in self.pages):
            raise TypeError("color payload: capture has a foreign page")
        if any(not isinstance(row, ColorRegionSummary)
               for row in self.regions):
            raise TypeError("color payload: capture has a foreign region")
        if any(
                row.source != self.source
                or row.evidence_kind != self.evidence_kind
                or row.evidence_values.shape[1] != arity
                for row in self.windows):
            raise ValueError(
                "color payload: capture/window boundary disagrees")
        identities = tuple(row.placement_id for row in self.windows)
        if len(identities) != len(set(identities)):
            raise ValueError("color payload: capture repeats a window")
        patch_ids = tuple(row.patch_id for row in self.windows)
        if len(patch_ids) != len(set(patch_ids)):
            raise ValueError(
                "color payload: capture repeats a patch identity")
        page_ids = tuple(row.page for row in self.pages)
        if page_ids != tuple(sorted(set(page_ids))):
            raise ValueError(
                "color payload: pages must be unique and sorted")
        for page in self.pages:
            if page.evidence_values.shape[1] != arity:
                raise ValueError(
                    "color payload: page evidence arity disagrees")
            window_indices = page.window_indices
            if np.any(
                    (window_indices < 0)
                    | (window_indices >= len(self.windows))):
                raise ValueError(
                    "color payload: owner window index is out of range")
            # Validate rows in window-sized batches.  Full pages can carry
            # millions of owned cells; the former Python loop performed two
            # tiny array comparisons per cell and dominated receiver time.
            if window_indices.size:
                window_pages = np.asarray(
                    tuple(window.page for window in self.windows),
                    np.int64,
                )
                window_sizes = np.asarray(
                    tuple(
                        window.page_cells_yx.shape[0]
                        for window in self.windows
                    ),
                    np.int64,
                )
                row_indices = page.window_row_indices
                invalid = (
                    (window_pages[window_indices] != page.page)
                    | (row_indices < 0)
                    | (row_indices >= window_sizes[window_indices])
                )
                bad = np.flatnonzero(invalid)
                if bad.size:
                    raise ValueError(
                        "color payload: owner provenance is not "
                        f"replayable at row {int(bad[0])}")
                order = np.argsort(window_indices, kind="stable")
                ordered_windows = window_indices[order]
                starts = np.flatnonzero(np.concatenate((
                    np.asarray((True,)),
                    ordered_windows[1:] != ordered_windows[:-1],
                )))
                stops = np.concatenate(
                    (starts[1:], np.asarray((order.size,))))
                first_mismatch: int | None = None
                for start, stop in zip(starts, stops, strict=True):
                    positions = order[start:stop]
                    window_index = int(ordered_windows[start])
                    row_indices = page.window_row_indices[positions]
                    window = self.windows[window_index]
                    cells_match = np.all(
                        page.cells_yx[positions]
                        == window.page_cells_yx[row_indices],
                        axis=1,
                    )
                    values_match = np.all(
                        page.evidence_values[positions]
                        == window.evidence_values[row_indices],
                        axis=1,
                    )
                    mismatch = np.flatnonzero(
                        ~(cells_match & values_match))
                    if mismatch.size:
                        candidate = int(positions[int(mismatch[0])])
                        first_mismatch = (
                            candidate
                            if first_mismatch is None
                            else min(first_mismatch, candidate)
                        )
                if first_mismatch is not None:
                    raise ValueError(
                        "color payload: owner provenance is not "
                        f"replayable at row {first_mismatch}")

    @property
    def lane_id(self) -> str:
        return self.source.lane_id


def _freeze(
    source: EvidenceSource,
    spec: FormatSpec,
    windows: tuple[ColorWindowEvidence, ...],
) -> tuple[ColorOwnedPageEvidence, ...]:
    del source
    payload_mask = _payload_site_mask(spec.family_seed)
    index_by_identity = {
        id(window): index for index, window in enumerate(windows)}

    def candidates() -> Iterable[
        tuple[int, int, np.ndarray, np.ndarray, np.ndarray]
    ]:
        for window in sorted(
            windows,
            key=lambda row: (row.heldout_logloss, row.patch_id),
        ):
            local_flat = (
                (window.page_cells_yx[:, 0] % 64) * 64
                + window.page_cells_yx[:, 1] % 64
            )
            row_indices = np.flatnonzero(payload_mask[local_flat]).astype(
                np.int32, copy=False)
            if not row_indices.size:
                continue
            yield (
                index_by_identity[id(window)],
                window.page,
                window.page_cells_yx[row_indices],
                row_indices,
                window.evidence_values[row_indices],
            )

    return tuple(
        ColorOwnedPageEvidence(
            page, cells, values, window_indices, row_indices)
        for page, cells, values, window_indices, row_indices
        in freeze_page_owners(candidates(), spec.layout.cells_yx))


def color_blocks_from_frontier(
    frontier: ColorCaptureEvidence,
    dependency_certificate_ids: dict[str, tuple[str, ...]] | None = None,
) -> tuple[EvidenceBlock, ...]:
    """Persist one owned color acquisition as shared physical blocks."""
    if not isinstance(frontier, ColorCaptureEvidence):
        raise TypeError("color payload: frontier type is invalid")
    window_ids = {
        window.placement_id for window in frontier.windows}
    if dependency_certificate_ids is None:
        dependencies = {
            window.placement_id: window.dependency_certificate_ids
            for window in frontier.windows
        }
    else:
        dependencies = dependency_certificate_ids
        if set(dependencies) != window_ids:
            raise ValueError(
                "color payload: dependency keys differ from windows")
    origins = tuple(
        EvidenceOrigin(
            window.placement_id,
            window.patch_id,
            window.heldout_logloss,
            tuple(sorted(set(dependencies.get(
                window.placement_id, ())))),
        )
        for window in frontier.windows
    )
    # Owner provenance was validated when the immutable frontier was
    # constructed (mint-once); the stream-generic converter serializes it.
    return blocks_from_owner_pages(
        frontier.source.source_sha256,
        frontier.lane_id,
        (
            OwnedPageRows(
                page.page,
                page.cells_yx,
                page.evidence_values,
                page.window_indices,
            )
            for page in frontier.pages
        ),
        origins,
        kind=frontier.evidence_kind,
    )

__all__ = [
    "ColorCaptureEvidence",
    "ColorOwnedPageEvidence",
    "ColorRegionSummary",
    "ColorWindowEvidence",
    "color_blocks_from_frontier",
]
