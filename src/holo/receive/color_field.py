"""W2/W4: the per-plane delta field at the colour registration seam.

Normative: docs/PLANE-FIELDS.md §3 (representation ruling), §6.1 (the
mapped seams and the nine measured constraints), §6.2 W2 and W4.

This module is the PRODUCTION INTEGRATION of the W1 core
(:mod:`holo.receive.plane_fields`).  It does three things and nothing
else:

* **collect** (W4 + the kept anchors) -- convert the
  :class:`~holo.receive.color_anchoring.RegistrationAnchors` array that
  ``color_payload`` used to discard into :class:`FieldEvidence`, and run
  a rectified-NCC probe pass over every certified tile of every window
  the caller offers (:mod:`holo.receive.color_probes` owns WHICH cells
  that is; certified-complete windows contribute no anchors at all,
  §6.1 pitfall 3);
* **solve** -- one :class:`PlaneDeltaField` per capture (per
  ``collect_color_evidence`` call), accumulated across regions in the
  caller's canonical region order and re-solved once per region, so a
  region always sees its own evidence plus every earlier region's; and
* **serve** -- per region and per plane, an ADOPTION verdict and, when
  adopted, the per-row translation delta that replaces
  :class:`~holo.receive.color_registration.PlaneResidual` at
  ``_features_with_page_fraction``.

**Default OFF.**  A ``None`` config anywhere on the chain is the
standing receiver, bit for bit: the builder is never constructed, no
probe runs, no event is emitted, and the seam takes its historical
branch (the null proof in ``tests/holo/test_color_field.py``).

Frames and units (§6.1 constraint 1).  The FIELD stores print-dot
deltas along the PAGE axes over tile space.  The SEAM consumes print-dot
deltas along the placed window's LOCAL axes -- the frame
``_measure_anchor`` measures in and ``pose.matrix()`` maps from.  The two
differ by the placement's ``rot_k``, so every crossing here goes through
:func:`_rotate_delta_xy`; on ``rot_k == 0`` (every synthetic fixture and
most real sheets) it is the identity, but pooling deltas over tile space
is only meaningful in the page frame.

Adoption (§6.2 W2, and the PK6 measured harm on registration-immune
tails).  Adoption is per REGION and per PLANE, never universal.  A plane
is adopted for a region only when the field is COVERED over enough of
the region's windows, its local posterior sd is small enough to be worth
believing, and it actually PREDICTS something -- a median correction of
at least :attr:`PlaneFieldConfig.min_delta_dots`, the measured sheet-I
cliff threshold.  Anything else falls back to the ``PlaneResidual``
behaviour unchanged.  Per-window clamp/null (§6.1 pitfall 2): a window
whose field-corrected points leave the raster loses only its own
correction; the region's corrected arm is never nulled by the field.

Production anchor SELECTION is untouched (§6.1 pitfall 4): this module
reads the returned array and does its own weighting.  The field is
TRANSIENT (§3c item 1) -- it lives for one collection call and never
enters session state.

The plane-COMMON part of every probe measurement is not field evidence
at all -- it is the covering WINDOW's own pose error, seen through
certified ground truth.  It is summarised per window in
:class:`WindowPoseResidual` and reported; applying it is P5 writer work
(docs/COMPOSITE-POSE-DESIGN.md §6), deliberately not done here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field as dataclass_field
from typing import (
    Any, Callable, Container, Final, Iterable, Mapping, Sequence,
)

import numpy as np

from ..format.descriptor import FormatSpec
from .color_anchoring import (
    RegistrationAnchors,
    _features_with_page_fraction,
    _rectified_ncc,
    _Rows,
)
from .color_probes import (
    ProbeMode,
    ProbeWindow,
    _ProbeSite,
    probe_sites_for_window,
    probe_template,
    template_is_flat,
)
from .color_projection import (
    CertifiedColorProjection,
    project_certified_color_tile,
)
from .color_registration import PlaneResidual
from .plane_fields import (
    DEFAULT_BANDWIDTH_TILES,
    DEFAULT_PLANE_SIGMA_DOTS,
    DEFAULT_PRIOR_SIGMA_DOTS,
    DEFAULT_REFINE_PASSES,
    DEFAULT_SAMPLE_SIGMA_DOTS,
    FieldEvidence,
    PlaneDeltaField,
    SOURCE_CERTIFIED,
    SOURCE_DUST,
    SOURCE_PROBE,
    SOURCE_WORD,
)

PLANE_NAMES: Final = ("C", "M", "Y")
N_PLANES: Final = 3

#: The W3 supplemental arm (docs/PLANE-FIELDS.md §6.2, the lane the
#: workplan calls ``uF``).  Registered in ``lane_uplift.UPLIFT_ARMS``
#: alongside the campaign's three, and owned HERE for the same reason
#: ``color_stack`` owns ``off``/``a3``/``a4b``: the module that
#: implements an arm names it.  It is not a stack arm — the ladder sees
#: it as no override at all and runs its standing configuration — it is
#: a REGISTRATION arm: the lane it names forces the plane-field dial on
#: for its own evidence collection.  THE ARM IS THE OPT-IN: the global
#: ``ProductionColorPayload.plane_fields`` dial stays default OFF and
#: keeps governing every ordinary, mop-up and refinement lane.
UPLIFT_ARM_FIELD: Final = "field"

#: Anchor bucket (``RegistrationAnchors.bucket``) -> field evidence tier.
_BUCKET_SOURCE: Final = {0: SOURCE_WORD, 1: SOURCE_DUST, 2: SOURCE_CERTIFIED}


_ROTATIONS: Final = (
    ((1.0, 0.0), (0.0, 1.0)),      # rot_k 0: (dy, dx)
    ((0.0, -1.0), (1.0, 0.0)),     # rot_k 1: (-dx, dy)
    ((-1.0, 0.0), (0.0, -1.0)),    # rot_k 2: (-dy, -dx)
    ((0.0, 1.0), (-1.0, 0.0)),     # rot_k 3: (dx, -dy)
)


def _rotate_delta_xy(
    delta_xy: np.ndarray, rot_k: int, *, inverse: bool
) -> np.ndarray:
    """Move ``(dx, dy)`` rows between a window's LOCAL and PAGE frames.

    ``rotated_points`` (``_payload_sampling``) is the exact integer map
    from window-local cells to page cells; on DIFFERENCES it reduces to
    one of the four rotations in :data:`_ROTATIONS`, acting on ``(dy,
    dx)``.  Rows here are ``(dx, dy)`` -- the anchor/residual order --
    so the axes are swapped in and back out.
    """
    if rot_k not in (0, 1, 2, 3):
        raise ValueError("plane fields: rot_k must be 0, 1, 2, or 3")
    rows = np.asarray(delta_xy, np.float64)
    if rot_k == 0:
        return rows.copy()
    matrix = np.asarray(_ROTATIONS[rot_k], np.float64)
    if inverse:
        matrix = matrix.T
    rotated = rows[:, ::-1] @ matrix.T
    return np.ascontiguousarray(rotated[:, ::-1])


@dataclass(frozen=True, slots=True)
class PlaneFieldConfig:
    """The W2/W4 dial: constructing one turns the arm ON.

    Threaded exactly the way ``arm_override`` and
    ``color_stack.StackConfig`` already are --
    ``ProductionColorPayload`` -> ``collect_color_evidence`` -> here --
    and ``None`` at every production construction site.  There is no
    environment hatch: the receiver's behaviour is a function of its
    declared arguments.
    """

    # -- estimator (passed straight to PlaneDeltaField) ----------------
    bandwidth_tiles: float = DEFAULT_BANDWIDTH_TILES
    plane_sigma_dots: float = DEFAULT_PLANE_SIGMA_DOTS
    sample_sigma_dots: float = DEFAULT_SAMPLE_SIGMA_DOTS
    prior_sigma_dots: float = DEFAULT_PRIOR_SIGMA_DOTS
    bins_per_tile: int = 1
    refine_passes: int = DEFAULT_REFINE_PASSES
    # -- adoption margin (per region, per plane) -----------------------
    #: The measured sheet-I cliff: below a quarter dot of Y error the
    #: dead-band residue collapses from 39.8/53 to 1.3/53.  A field that
    #: predicts less than this has nothing to say that the committed
    #: pose is not already saying.
    min_delta_dots: float = 0.25
    #: Local posterior sd above which the field is not worth believing.
    max_uncertainty_dots: float = 0.25
    #: Fraction of a region's windows that must fall inside the field's
    #: evidence hull before the region may adopt.
    min_coverage_fraction: float = 0.5
    #: Per-window magnitude clamp -- a wild lookup can move sampling by
    #: at most this much (per-window clamp, §6.1 pitfall 2).
    max_delta_dots: float = 2.0
    # -- W4 probe pass -------------------------------------------------
    #: Probe DENSITY; see :class:`~holo.receive.color_probes.ProbeMode`
    #: and its measured record (INDEPENDENT-PLANES §2.9 / §2.9b / §2.9c).
    #: TILE_FRAGMENT since 2026-08-23: one measurement per (certified
    #: tile, covering window), serving the field AND the plane-common
    #: pose residual from the same correlation.
    probe_mode: ProbeMode = ProbeMode.TILE_FRAGMENT
    #: Probe block edge in cells; must be odd and at least 3.  It is the
    #: template edge for the square densities, ignored by
    #: :attr:`ProbeMode.WHOLE_TILE` (whose edge IS the tile), and the
    #: per-axis identifiability floor for
    #: :attr:`ProbeMode.TILE_FRAGMENT`.
    probe_block_cells: int = 5
    #: NCC floor for a probe measurement to become evidence.
    probe_min_quality: float = 0.30
    #: NCC floor for a kept anchor to become evidence (the production
    #: anchor gate has already applied its own, lower, floor).
    anchor_min_quality: float = 0.10
    # -- reporting -----------------------------------------------------
    #: Quiver exaggeration the W5 field pane should draw at.
    exaggeration_hint: float = 50.0

    def __post_init__(self) -> None:
        if not isinstance(self.probe_mode, ProbeMode):
            raise ValueError("plane fields: probe_mode must be a ProbeMode")
        if self.probe_block_cells < 3 or self.probe_block_cells % 2 == 0:
            raise ValueError(
                "plane fields: probe_block_cells must be odd and >= 3")
        for name in (
            "min_delta_dots", "max_uncertainty_dots",
            "min_coverage_fraction", "max_delta_dots",
            "probe_min_quality", "anchor_min_quality", "exaggeration_hint",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(
                    f"plane fields: {name} must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class WindowPoseResidual:
    """One window's plane-COMMON probe residual -- MEASURED, NEVER APPLIED.

    Every probe measurement splits into a per-plane part, which is what
    the field consumes, and a part every plane shares.  The shared part is
    not a registration difference at all: it is this WINDOW's committed
    pose being off, seen through certified ground truth.  Feeding it back
    to the pose is P5 writer work (docs/COMPOSITE-POSE-DESIGN.md §6: word
    solves and pose refinement own the plane-common lane, the field owns
    the differential); this record exists so the size of that correction
    is a MEASUREMENT before anyone builds the writer.

    Units are print dots along the window's LOCAL axes -- the frame a
    pose correction would be applied in, NOT the page frame the field
    pools over.  Only sites where every plane produced a measurement
    contribute: a mean over a varying subset of planes is not a common
    component.  ``spread_*`` is the plain median absolute deviation of
    the contributing sites, which is the number that says whether the
    window's tiles AGREE -- a consistent shift is a pose correction
    waiting to be fed back; a scattered one is noise.
    """

    page: int
    patch_id: int
    n_sites: int
    median_dx_dots: float
    median_dy_dots: float
    spread_dx_dots: float
    spread_dy_dots: float

    @property
    def magnitude_dots(self) -> float:
        return float(np.hypot(self.median_dx_dots, self.median_dy_dots))


@dataclass(frozen=True, slots=True)
class PlaneFieldReport:
    """One capture's field summary -- the W5 analytics contract.

    ``rms_dots``/``peak_dots``/``coverage_by_plane`` come from
    :meth:`PlaneDeltaField.stats` over the COVERED bins.  ``adopted`` is
    the plane names adopted by at least one region.  The ``*_seconds``
    pair is the measured cost of the arm itself (solve + probes), which
    the workplan requires to stay far below the lane's decode cost.
    """

    rms_dots: tuple[float, ...]
    peak_dots: tuple[float, ...]
    coverage_by_plane: tuple[float, ...]
    coverage: float
    adopted: tuple[str, ...]
    regions: int
    regions_adopted_by_plane: tuple[int, ...]
    n_samples: int
    samples_by_source: dict[str, int] = dataclass_field(default_factory=dict)
    n_probes: int = 0
    n_probe_sites: int = 0
    window_nulls: int = 0
    solve_seconds: float = 0.0
    probe_seconds: float = 0.0
    quiver: tuple[tuple[int, int, int, float, float], ...] = ()
    #: ``(page, tile_y, tile_x)`` for every tile whose every stream is
    #: certified, straight from the certificate authority -- not from
    #: whatever the probe pass happened to visit.  The W5 pane needs
    #: these to tell "nothing left to do here" apart from "nothing known
    #: here and still failing", both of which are simply UNCOVERED
    #: (2026-08-21: a fully decoded area reads as a hole because the pool
    #: law gives certified-complete windows no anchors).  PAGE-AWARE
    #: since 2026-08-22: a band that painted another page's certified
    #: tiles would report "nothing left to measure" exactly where the
    #: operator is hunting a blind spot.
    done_tiles: tuple[tuple[int, int, int], ...] = ()
    exaggeration_hint: float = 0.0
    #: Per-window plane-common probe residuals (:class:`WindowPoseResidual`)
    #: -- measured and reported, never applied to a pose.
    window_pose_residuals: tuple[WindowPoseResidual, ...] = ()

    @property
    def adopted_text(self) -> str:
        return ",".join(self.adopted)

    def pose_residual_magnitudes(self) -> tuple[float, ...]:
        """The per-window plane-common magnitudes, in print dots."""
        return tuple(
            row.magnitude_dots for row in self.window_pose_residuals)

    def snapshot(self) -> dict[str, Any]:
        """The pinned ``payload.plane_fields`` snapshot payload."""
        return {
            "planes": [list(row) for row in self.quiver],
            "done": [list(row) for row in self.done_tiles],
            "exaggeration_hint": float(self.exaggeration_hint),
        }


class PlaneFieldBuilder:
    """One capture's field: accumulate, solve, and serve the seam.

    Constructed only when the dial is on.  ``add_*`` scatter evidence,
    :meth:`solve` rebuilds the smoothed posterior, and
    :meth:`region_offsets` returns the per-row per-plane translation
    deltas the seam should use -- ``None`` per plane wherever the region
    did not adopt, which is the historical ``PlaneResidual`` branch.
    """

    def __init__(
        self,
        spec: FormatSpec,
        config: PlaneFieldConfig,
        *,
        done_tiles: Iterable[tuple[int, int, int]] = (),
    ) -> None:
        """``done_tiles`` is the certificate authority's own address set.

        The fully-certified ``(page, tile_y, tile_x)`` addresses, handed
        in by the caller that already computed them
        (``fully_certified_color_addresses``).  The builder REPORTS them;
        it does not discover them.  The probe pass used to be the only
        thing that populated this, so a lane whose probes happened not to
        reach a certified area painted it as unknown.
        """
        self._spec = spec
        self._config = config
        self._field = PlaneDeltaField(
            N_PLANES,
            spec.layout.tiles_yx,
            bandwidth_tiles=config.bandwidth_tiles,
            plane_sigma_dots=config.plane_sigma_dots,
            sample_sigma_dots=config.sample_sigma_dots,
            prior_sigma_dots=config.prior_sigma_dots,
            bins_per_tile=config.bins_per_tile,
            refine_passes=config.refine_passes,
        )
        self._solve_seconds = 0.0
        self._probe_seconds = 0.0
        self._n_probes = 0
        self._n_probe_sites = 0
        self._window_nulls = 0
        self._regions = 0
        self._done_tiles: tuple[tuple[int, int, int], ...] = tuple(sorted({
            (int(page), int(tile_y), int(tile_x))
            for page, tile_y, tile_x in done_tiles}))
        self._regions_adopted = [0] * N_PLANES
        self._adopted_planes: set[int] = set()
        #: ``(page, patch_id)`` -> the LOCAL-frame plane-common offset of
        #: every site of that window where all three planes measured.
        self._pose_residuals: dict[tuple[int, int], list[np.ndarray]] = {}
        self._dirty = False

    # -- collection -----------------------------------------------------

    def add_anchors(
        self,
        rows: Sequence[_Rows],
        anchors: Sequence[RegistrationAnchors],
    ) -> int:
        """Keep what ``color_payload`` used to discard (§6.1, F1 step 1).

        All three buckets (0 word, 1 dust, 2 prior-barrier certificate)
        become evidence; the bucket rides along as the source tier and
        the NCC quality becomes the sample's relative precision.
        """
        evidence: list[FieldEvidence] = []
        for plane, plane_anchors in enumerate(anchors):
            page = np.asarray(plane_anchors.page, np.int64)
            if not page.size:
                continue
            cells = np.asarray(plane_anchors.cell_yx, np.int64)
            quality = np.asarray(plane_anchors.quality, np.float64)
            bucket = np.asarray(plane_anchors.bucket, np.int64)
            window_index = np.asarray(plane_anchors.window_index, np.int64)
            offsets = np.asarray(plane_anchors.offset_dots_xy, np.float64)
            keep = np.flatnonzero(
                np.isfinite(offsets).all(axis=1)
                & (quality >= self._config.anchor_min_quality))
            if not keep.size:
                continue
            # One rotation per distinct placement orientation, not per row.
            page_offsets = np.empty((keep.size, 2), np.float64)
            rot = np.fromiter(
                (int(rows[int(index)].patch.segment.rot_k)
                 for index in window_index[keep]),
                np.int64, keep.size)
            for rot_k in np.unique(rot):
                take = rot == rot_k
                page_offsets[take] = _rotate_delta_xy(
                    offsets[keep][take], int(rot_k), inverse=False)
            for ordinal, index in enumerate(keep):
                evidence.append(FieldEvidence.from_cell_yx(
                    page=int(page[index]),
                    cell_yx=(float(cells[index, 0]) + 0.5,
                             float(cells[index, 1]) + 0.5),
                    plane_index=plane,
                    offset_dots_xy=(
                        float(page_offsets[ordinal, 0]),
                        float(page_offsets[ordinal, 1])),
                    weight=float(min(1.0, quality[index])),
                    source=_BUCKET_SOURCE[int(bucket[index])],
                ))
        return self._add(evidence)

    def add_certified_probes(
        self,
        raster: Any,
        windows: Sequence[ProbeWindow],
        projection_for: Callable[
            [tuple[int, int, int]], CertifiedColorProjection | None],
    ) -> int:
        """W4: the tier-(i) probe pass over windows that cover done tiles.

        A certified-complete window is LABEL-ONLY under the pool law
        (§6.1 pitfall 3) -- ``_fit_registration`` never sees it -- so
        without this pass the field's strongest evidence class is exactly
        the one it never collects.  Since 2026-08-23 the caller offers
        MIXED windows too (INDEPENDENT-PLANES §4.G): a fully certified
        tile inside a window that still owes payload work is exactly as
        certified, and the window that covers it is exactly as posed.
        Each site measures the rectified NCC of the scan against the
        certificate's own re-encoded printed cells, per plane, at the
        committed pose.

        EVERY eligible site is probed (see
        :func:`~holo.receive.color_probes.probe_sites_for_window`): the
        cost is a declared function of how much of the sheet is
        certified and of the declared :class:`ProbeMode` density, not of
        a number someone picked.
        """
        if not windows:
            return 0
        started = time.perf_counter()
        config = self._config
        tiles_x = int(self._spec.layout.tiles_yx[1])
        certified_cache: dict[
            tuple[int, int, int], CertifiedColorProjection | None] = {}

        def projection(address: tuple[int, int, int]):
            if address not in certified_cache:
                certified_cache[address] = projection_for(address)
            return certified_cache[address]

        sites: list[_ProbeSite] = []
        for ordinal, window in enumerate(windows):
            sites.extend(probe_sites_for_window(
                window, ordinal, config.probe_mode,
                lambda address: projection(address) is not None,
                tiles_x,
                block_cells=int(config.probe_block_cells),
                bins_per_tile=int(config.bins_per_tile)))
        if not sites:
            self._probe_seconds += time.perf_counter() - started
            return 0
        sites.sort(key=lambda site: (
            site.page, site.page_y, site.page_x, site.window_ordinal))
        evidence: list[FieldEvidence] = []
        for site in sites:
            window = windows[site.window_ordinal]
            projected = projection(site.address)
            if projected is None:
                continue
            template = probe_template(
                window, site, projected,
                min_edge_cells=int(config.probe_block_cells))
            if template is None:
                continue
            bits, weights = template
            self._n_probe_sites += 1
            rot_k = int(window.patch.segment.rot_k)
            inside = weights > 0.0
            centre_local_yx = site.centre_local_yx
            local_offsets: list[np.ndarray] = []
            for plane in range(N_PLANES):
                plane_bits = bits[..., plane]
                if template_is_flat(plane_bits, inside):
                    continue
                measured = _rectified_ncc(
                    raster, window.patch, self._spec,
                    centre_local_yx, plane_bits, weights, plane)
                if measured is None:
                    continue
                offset_dots_xy, quality = measured
                if quality < config.probe_min_quality:
                    continue
                self._n_probes += 1
                local_offsets.append(offset_dots_xy)
                page_offset = _rotate_delta_xy(
                    offset_dots_xy.reshape(1, 2), rot_k, inverse=False)[0]
                evidence.append(FieldEvidence.from_cell_yx(
                    page=site.page,
                    cell_yx=site.centre_page_yx,
                    plane_index=plane,
                    offset_dots_xy=(
                        float(page_offset[0]), float(page_offset[1])),
                    weight=float(min(1.0, quality)),
                    source=SOURCE_PROBE,
                ))
            if len(local_offsets) == N_PLANES:
                # The plane-COMMON component of this site's measurement:
                # not a registration difference, this window's own pose.
                # Recorded per window, never applied (P5 writer work).
                self._pose_residuals.setdefault(
                    (site.page, int(window.patch.patch_id)), []
                ).append(np.mean(local_offsets, axis=0))
        added = self._add(evidence)
        self._probe_seconds += time.perf_counter() - started
        return added

    def _add(self, evidence: Iterable[FieldEvidence]) -> int:
        rows = list(evidence)
        if not rows:
            return 0
        added = self._field.add(rows)
        self._dirty = added > 0
        return added

    # -- solving --------------------------------------------------------

    def solve(self) -> None:
        """Re-solve when new evidence landed; a no-op otherwise."""
        if not self._dirty and self._field.solved:
            return
        started = time.perf_counter()
        self._field.solve()
        self._solve_seconds += time.perf_counter() - started
        self._dirty = False

    # -- the seam -------------------------------------------------------

    def region_offsets(
        self, page: int, rows: Sequence[_Rows]
    ) -> tuple[
        tuple[tuple[np.ndarray | None, ...], ...], tuple[bool, ...]
    ]:
        """Per-row per-plane deltas for one region, in the LOCAL frame.

        Returns ``(overrides, adopted)``: ``overrides[i][plane]`` is the
        ``(N, 2)`` ``(dx, dy)`` print-dot array for row ``i`` and that
        plane, or ``None`` when the region did not adopt that plane --
        in which case the seam takes the ``PlaneResidual`` branch
        unchanged.
        """
        self._regions += 1
        if not rows or not self._field.solved:
            return (
                tuple((None,) * N_PLANES for _ in rows),
                (False,) * N_PLANES,
            )
        centres: list[tuple[float, float]] = []
        lookups = []
        for row in rows:
            cells = np.asarray(row.page_cells_yx, np.float64)
            centre = (float(cells[:, 0].mean()), float(cells[:, 1].mean()))
            centres.append(centre)
            lookups.append(self._field.lookup_cells(page, centre))
        adopted = self._adoption(lookups)
        for plane in range(N_PLANES):
            if adopted[plane]:
                self._regions_adopted[plane] += 1
                self._adopted_planes.add(plane)
        if not any(adopted):
            return tuple(
                (None,) * N_PLANES for _ in rows), adopted
        clamp = float(self._config.max_delta_dots)
        overrides: list[tuple[np.ndarray | None, ...]] = []
        for row, centre, affines in zip(rows, centres, lookups, strict=True):
            cells = np.asarray(row.page_cells_yx, np.float64)
            offset_cells_xy = np.stack(
                (cells[:, 1] - centre[1], cells[:, 0] - centre[0]), axis=1)
            rot_k = int(row.patch.segment.rot_k)
            per_plane: list[np.ndarray | None] = []
            for plane in range(N_PLANES):
                if not adopted[plane]:
                    per_plane.append(None)
                    continue
                affine = affines[plane]
                jacobian = np.asarray(
                    affine.jacobian_dots_per_cell, np.float64)
                delta = (
                    np.asarray(affine.delta_dots_xy, np.float64)
                    + offset_cells_xy @ jacobian.T)
                magnitude = np.hypot(delta[:, 0], delta[:, 1])
                scale = np.where(
                    magnitude > clamp, clamp / np.maximum(magnitude, 1e-12),
                    1.0)
                delta = delta * scale[:, None]
                per_plane.append(_rotate_delta_xy(delta, rot_k, inverse=True))
            overrides.append(tuple(per_plane))
        return tuple(overrides), adopted

    def _adoption(self, lookups: Sequence[Sequence[Any]]) -> tuple[bool, ...]:
        config = self._config
        verdicts: list[bool] = []
        for plane in range(N_PLANES):
            affines = [row[plane] for row in lookups]
            covered = [affine for affine in affines if affine.covered]
            fraction = len(covered) / len(affines)
            if not covered or fraction < config.min_coverage_fraction:
                verdicts.append(False)
                continue
            uncertainty = float(np.median(
                [affine.uncertainty_dots for affine in covered]))
            magnitude = float(np.median([
                float(np.hypot(*affine.delta_dots_xy)) for affine in covered]))
            verdicts.append(
                uncertainty <= config.max_uncertainty_dots
                and magnitude >= config.min_delta_dots)
        return tuple(verdicts)

    def note_window_null(self) -> None:
        """One window's field correction left the raster and was dropped."""
        self._window_nulls += 1

    # -- reporting ------------------------------------------------------

    def report(self) -> PlaneFieldReport:
        if not self._field.solved:
            self.solve()
        stats = self._field.stats()
        coverage = (
            float(np.mean(stats.coverage_fraction))
            if stats.coverage_fraction else 0.0)
        return PlaneFieldReport(
            rms_dots=tuple(stats.rms_dots),
            peak_dots=tuple(stats.peak_dots),
            coverage_by_plane=tuple(stats.coverage_fraction),
            coverage=coverage,
            adopted=tuple(
                PLANE_NAMES[plane] for plane in sorted(self._adopted_planes)),
            regions=self._regions,
            regions_adopted_by_plane=tuple(self._regions_adopted),
            n_samples=stats.n_samples,
            samples_by_source=dict(stats.samples_by_source),
            n_probes=self._n_probes,
            n_probe_sites=self._n_probe_sites,
            window_nulls=self._window_nulls,
            solve_seconds=self._solve_seconds,
            probe_seconds=self._probe_seconds,
            quiver=self._quiver(stats.pages),
            done_tiles=self._done_tiles,
            exaggeration_hint=float(self._config.exaggeration_hint),
            window_pose_residuals=self._window_pose_residuals(),
        )

    def _window_pose_residuals(self) -> tuple[WindowPoseResidual, ...]:
        """Summarise each window's plane-common probe residual."""
        rows: list[WindowPoseResidual] = []
        for (page, patch_id), offsets in sorted(self._pose_residuals.items()):
            block = np.asarray(offsets, np.float64)
            median = np.median(block, axis=0)
            spread = np.median(np.abs(block - median), axis=0)
            rows.append(WindowPoseResidual(
                page=page,
                patch_id=patch_id,
                n_sites=int(block.shape[0]),
                median_dx_dots=float(median[0]),
                median_dy_dots=float(median[1]),
                spread_dx_dots=float(spread[0]),
                spread_dy_dots=float(spread[1]),
            ))
        return tuple(rows)

    def _quiver(
        self, pages: tuple[int, ...]
    ) -> tuple[tuple[int, int, int, float, float], ...]:
        """Compact ``(plane, tile_y, tile_x, dx, dy)`` rows, covered only.

        Rows pool over pages: the pinned snapshot shape carries no page
        slot, which is exact for the single-page case and an overlay
        otherwise (the W5 pane draws one sheet at a time).
        """
        tiles_y, tiles_x = self._field.tiles_yx
        rows: list[tuple[int, int, int, float, float]] = []
        for page in pages:
            for tile_y in range(tiles_y):
                for tile_x in range(tiles_x):
                    for affine in self._field.lookup_tile_index(
                            page, tile_y, tile_x):
                        if not affine.covered:
                            continue
                        rows.append((
                            affine.plane_index, tile_y, tile_x,
                            round(float(affine.delta_dots_xy[0]), 4),
                            round(float(affine.delta_dots_xy[1]), 4),
                        ))
        return tuple(rows)


def certified_projection_source(
    spec: FormatSpec,
    certificate_index: Mapping[tuple[int, int, int], tuple[Any, ...]],
    projection_cache: dict[
        tuple[int, int, int], CertifiedColorProjection],
    fully_certified_addresses: Container[tuple[int, int, int]],
) -> Callable[[tuple[int, int, int]], CertifiedColorProjection | None]:
    """The W4 probe pass's GT source: exact cells, ALL planes known.

    Only a FULLY certified tile qualifies -- a projection missing one
    stream would leave that plane's template partly unknown, and a probe
    measured against a guess is not tier-i evidence.  Writes through the
    caller's per-capture projection memo, so a tile re-encoded for the
    known-field derivation is never re-encoded for a probe.
    """
    def projection_for(
        address: tuple[int, int, int],
    ) -> CertifiedColorProjection | None:
        if address not in fully_certified_addresses:
            return None
        cached = projection_cache.get(address)
        if cached is None:
            cached = project_certified_color_tile(
                certificate_index.get(address, ()), spec, address)
            projection_cache[address] = cached
        return cached

    return projection_for


def field_corrected_features(
    raster: Any,
    row: _Rows,
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual],
    spec: FormatSpec,
    pitch_px: float,
    divisor: float,
    override: tuple[np.ndarray | None, ...],
) -> tuple[np.ndarray | None, bool]:
    """One window's corrected features with the W2 clamp/null.

    §6.1 pitfall 2: the historical A1 arm is all-or-nothing per REGION --
    one out-of-raster proposal nulls every window's corrected features.
    A field correction must never be able to do that, so a window whose
    field-corrected points leave the acquisition falls back to the
    ``PlaneResidual`` proposal FOR THAT WINDOW ALONE.  Only if that also
    leaves the raster does the historical region-wide null fire, exactly
    as it does today.  Returns ``(features, field_was_nulled)``; the flag
    is returned rather than counted in place because this runs inside
    ``ordered_map``.
    """
    if any(entry is not None for entry in override):
        corrected = _features_with_page_fraction(
            raster, row, residuals, spec, pitch_px, divisor,
            offsets_override=override)
        if corrected is not None:
            return corrected, False
        return (
            _features_with_page_fraction(
                raster, row, residuals, spec, pitch_px, divisor),
            True,
        )
    return (
        _features_with_page_fraction(
            raster, row, residuals, spec, pitch_px, divisor),
        False,
    )


__all__ = [
    "N_PLANES",
    "PLANE_NAMES",
    "UPLIFT_ARM_FIELD",
    "PlaneFieldBuilder",
    "PlaneFieldConfig",
    "PlaneFieldReport",
    "ProbeMode",
    "ProbeWindow",
    "WindowPoseResidual",
    "certified_projection_source",
    "field_corrected_features",
]
