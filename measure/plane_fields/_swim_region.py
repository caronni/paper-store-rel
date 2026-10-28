"""The per-candidate decode driver: production leaves, harness scheduling.

docs/PLANE-FIELDS.md §6.5.5a (THE SWIM CHARTER) asks for a decode verdict
at each candidate per-plane sampling offset, and acceptance is the
ORDINARY certificate gate — never a similarity score.  This module gets
that by mirroring ``color_payload.collect_color_evidence``'s REGION LOOP
(and nothing else) around the production leaves:

    _payload_sampling._window_rows / known_field.build_known_rows
    color_pool._emission_mask / _payload_cell_mask
    color_sampling.window_raw_crops / crop_features
    color_anchoring._fit_registration
    color_anchoring._features_with_page_fraction   <- THE SWIM SEAM
    color_stack.fit_region_stack
    ColorFit.evidence_with_divisor
    color_evidence._freeze / color_blocks_from_frontier
    evidence_blocks.tile_attempt_view
    color_attempts.attempt_color_tile              <- THE ORACLE

Three deliberate deviations from a production lane, all reported with the
result (the pilot brief's "MECHANISM LATITUDE"):

1. **Restricted region.**  A sheet-I colour region is the whole page
   (~2k windows); fitting that per candidate is hours.  The fit
   population here is the windows within ``--fit-radius`` tiles of any
   target — a production-shaped fit over a smaller pool.
2. **Frozen detector.**  The region is fitted ONCE at delta = 0 and that
   detector (with its A5 context bins) scores every candidate; only the
   target windows are re-sampled per candidate.  ``refit_overrides``
   is the escape from that approximation: those tiles' windows are
   sampled at the correction BEFORE anything is fitted, so the
   registration fit, the QDA/PAVA stack and the A5 context bins all see
   the shifted evidence.
3. **Dial-off zero.**  delta = 0 is the arm's own ``PlaneResidual``
   prediction, i.e. the pre-PLANE-FIELDS sampling, not the W6 state's
   dial-ON field sampling.  The swim therefore has to re-earn whatever
   the field was already contributing, which makes its winning offsets
   directly comparable to the regmap-gt sinusoid.

``delta == 0`` reproduces the historical branch exactly whenever the A1
arm was adopted, and to float32 rounding when the A0 arm was;
:func:`null_proof` MEASURES which, on both arms (it used to
short-circuit to ``True`` on A0, so the seam was never checked on the
captures where it is not the identity).

THE ARM-INDEPENDENCE RULE (2026-08-22 review fix).  A correction is
expressed relative to the ARM'S OWN ZERO: the A1 arm's zero is the
``PlaneResidual`` prediction, the A0 arm's zero is the bare committed
pose.  :func:`fit_region` therefore applies a refit override to BOTH
arms, each about its own zero, and asserts afterwards that the features
the stack actually SELECTED differ from that arm's zero features.  The
previous code injected the override into the A1 arm alone, so on a
capture whose stack selected A0 — two of sheet I's three — the refit was
a silent no-op.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage

from holo.receive import _parallel
from holo.receive._payload_sampling import _window_rows
from holo.receive.color_anchoring import (
    _Rows,
    _color_kind,
    _features_with_page_fraction,
    _fit_registration,
    _label_site_rows,
    _neighbor_rows,
)
from holo.receive.color_attempts import attempt_color_tile
from holo.receive.color_evidence import (
    ColorCaptureEvidence,
    ColorWindowEvidence,
    _freeze,
    color_blocks_from_frontier,
)
from holo.receive.color_fitting import _owner_selection, _window_loss
from holo.receive.color_pool import (
    _emission_mask,
    _payload_cell_mask,
    fully_certified_color_addresses,
)
from holo.receive.color_sampling import (
    crop_features,
    filtered_crop,
    window_raw_crops,
)
from holo.receive.color_stack import ArmFeatures, fit_region_stack
from holo.receive.evidence import AttemptStage
from holo.receive.evidence_blocks import tile_attempt_view
from holo.receive.known_field import build_known_rows
from holo.receive.payload_model import EvidenceSource

N_PLANES = 3

#: ``_payload_sampling.rotated_points`` linear parts: local (y,x) cell
#: deltas -> page (y,x) cell deltas, per ``rot_k``.  The translation the
#: real map carries is irrelevant to a DELTA.
_ROT_YX = {
    0: np.asarray(((1.0, 0.0), (0.0, 1.0))),
    1: np.asarray(((0.0, -1.0), (1.0, 0.0))),
    2: np.asarray(((-1.0, 0.0), (0.0, -1.0))),
    3: np.asarray(((0.0, 1.0), (-1.0, 0.0))),
}
_SWAP = np.asarray(((0.0, 1.0), (1.0, 0.0)))


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def patch_tiles(patch) -> frozenset[tuple[int, int, int]]:
    """The (page, tile_y, tile_x) addresses one placement's cells touch."""
    cells = np.asarray(patch.page_cells_yx, np.int64)
    page = int(patch.candidate.page)
    return frozenset(
        (page, int(ty), int(tx))
        for ty, tx in np.unique(cells // 64, axis=0))


def page_to_local_dots(patch) -> np.ndarray:
    """2x2 matrix taking a PAGE-dot ``(dx, dy)`` to LOCAL-window dots.

    ``_features_with_page_fraction`` applies its override along the
    window's LOCAL axes, while the field, the sinusoid and every probe
    speak PAGE axes.  Local and page cells differ by the placement's
    exact integer ``rot90`` (``_payload_sampling.rotated_points``), so the
    change of basis is that rotation's transpose; ``cell_dots`` cancels.
    """
    rotation = _ROT_YX[int(patch.segment.rot_k) % 4]
    return _SWAP @ rotation.T @ _SWAP


# --------------------------------------------------------------------------
# one fitted region
# --------------------------------------------------------------------------
@dataclass
class RegionFit:
    """One restricted region, fitted once at delta = 0."""

    capture_sha256: str
    lane_id: str
    region_id: str
    page: int
    source: EvidenceSource
    kind: str
    pitch_px: float
    divisor: float
    residuals: tuple
    selected_fit: object
    context_bins: tuple | None
    adopted: bool
    rows: tuple                       # payload rows first, then label rows
    n_payload: int
    emission_by_row: tuple
    patch_by_ordinal: tuple
    features0: dict                   # ordinal -> selected-arm features
    tile_rows: dict                   # address -> payload ordinals
    n_windows: int
    n_labels: int
    heldout_loss: float
    refusal: str | None = None
    #: The refit seam's own verdict: for every window the override
    #: touched, how far the features the stack SELECTED sit from that
    #: arm's zero features.  ``None`` on an ordinary (frozen-detector)
    #: fit; :class:`RefitDidNotReach` is raised rather than recorded when
    #: any of those distances is zero.
    refit_probe: dict | None = None

    @property
    def base_is_residual(self) -> bool:
        """True when delta = 0 is the residual prediction (A1 adopted)."""
        return self.adopted


class RefitDidNotReach(RuntimeError):
    """A refit override left the selected arm's features unchanged.

    The 2026-08-22 review's finding, promoted to a hard failure: a refit
    that silently evaluates at delta = 0 is worse than no refit, because
    it reports a verdict that looks like a validation and is not one.
    """


def _split_rows(spec, page, patches, aligned_rows, emission_masks,
                certificate_index, projection_cache):
    """Region placements -> (payload rows, their patches, label rows, emit)."""
    open_flags = tuple(
        bool(np.any(_payload_cell_mask(spec, aligned.page_cells_yx) & emit))
        for aligned, emit in zip(aligned_rows, emission_masks, strict=True))
    payload_rows: list[_Rows] = []
    payload_patches: list = []
    label_rows: list[_Rows] = []
    emission_by_row: list[np.ndarray] = []
    for patch, aligned, is_open, emit in zip(
            patches, aligned_rows, open_flags, emission_masks, strict=True):
        if not is_open:
            label_row = _label_site_rows(
                spec, page, patch, aligned, certificate_index)
            if label_row is not None:
                label_rows.append(label_row)
            continue
        known = build_known_rows(
            spec, page, aligned.page_cells_yx, certificate_index,
            projection_cache)
        payload_rows.append(_Rows(
            patch, aligned.local_cells_yx, aligned.page_cells_yx,
            aligned.scan_points_yx, known.states, known.furniture_kind,
            known.component_bits, known.component_mask,
            _neighbor_rows(aligned.local_cells_yx),
            known.dependency_certificate_ids))
        payload_patches.append(patch)
        emission_by_row.append(emit)
    return (tuple(payload_rows), tuple(payload_patches), tuple(label_rows),
            tuple(emission_by_row))


def override_offsets(row, residuals, spec, delta_page_dots,
                     base_is_residual: bool) -> tuple:
    """The ``offsets_override`` tuple for one window at a page-dot delta.

    ONE definition, shared by the per-candidate sampler and the
    per-candidate REFIT, so a spot-check can never differ from the
    frozen-detector path by an accident of arithmetic.

    ``residuals`` is read only when ``base_is_residual`` is true, so the
    A0 arm — whose zero is the bare committed pose — may pass ``None``
    and be sampled before the registration fit exists.
    """
    count = row.page_cells_yx.shape[0]
    page_y_fraction = (row.page_cells_yx[:, 0].astype(np.float64)
                       / spec.layout.cells_yx[0])
    basis = page_to_local_dots(row.patch)
    override = []
    for plane in range(N_PLANES):
        base = (residuals[plane].offsets(page_y_fraction) if base_is_residual
                else np.zeros((count, 2), np.float64))
        local = basis @ np.asarray(delta_page_dots[plane], np.float64)
        override.append(base + local[None, :])
    return tuple(override)


def constant_override(delta_page_dots):
    """A refit override builder for a per-plane CONSTANT page-dot delta.

    ``fit_region``'s override seam takes a builder rather than an array
    so a per-CELL correction (``gt_affine.affine_override``) and a
    constant one are the same kind of thing to it.
    """
    delta = np.asarray(delta_page_dots, np.float64)

    def build(row, residuals, spec, base_is_residual: bool) -> tuple:
        return override_offsets(row, residuals, spec, delta, base_is_residual)

    return build


def base_features(crop, row, spec, pitch_px: float, divisor: float,
                  offsets_override=None) -> np.ndarray:
    """The A0 arm's features for one window, optionally displaced.

    ``offsets_override is None`` is ``color_sampling.crop_features``
    verbatim — the production A0 arm, bit for bit.  With an override the
    SAME filtered window crop is sampled once per plane at that plane's
    own displaced points, which is the only way a PER-PLANE correction
    can reach an arm whose production form samples all three channels at
    one point set.  An all-zero override adds exactly ``0.0`` to those
    points, so it is bit-identical to the ``None`` branch.
    """
    if offsets_override is None:
        return crop_features(crop, row.scan_points_yx, pitch_px, divisor)
    y0, x0, raw = crop
    local_crop = filtered_crop(y0, x0, raw, pitch_px, divisor)
    image = local_crop.filtered
    pose = np.asarray(row.patch.segment.segment.pose.matrix(), np.float64)
    points_yx = np.asarray(row.scan_points_yx, np.float64)
    out = np.empty((points_yx.shape[0], N_PLANES), np.float64)
    for plane in range(N_PLANES):
        offsets = np.asarray(offsets_override[plane], np.float64)
        points = points_yx + (offsets[:, ::-1] / spec.cell_dots) @ pose.T
        local = points - np.asarray((local_crop.y0, local_crop.x0), np.float64)
        if local.size and (
                np.any(local[:, 0] < 0.0) or np.any(local[:, 1] < 0.0)
                or np.any(local[:, 0] > image.shape[0] - 1)
                or np.any(local[:, 1] > image.shape[1] - 1)):
            raise ValueError(
                f"refit: the displaced A0 sample of patch "
                f"{int(row.patch.patch_id)} leaves its window crop")
        out[:, plane] = ndimage.map_coordinates(
            image[..., plane], local.T, order=1, mode="nearest",
            output=np.float64)
    return out


def fit_region(
    spec,
    raster,
    source: EvidenceSource,
    patches: tuple,
    certificates: tuple,
    page: int,
    region_id: str,
    *,
    keep_features_for: frozenset[tuple[int, int, int]],
    refit_deltas: dict | None = None,
    refit_overrides: dict | None = None,
    keep_all_features: bool = False,
) -> RegionFit:
    """Collect and fit one restricted region as production's loop does.

    ``keep_features_for`` are the tile addresses whose windows' delta = 0
    features are retained (the swim's baseline); every other window's
    features are released with the ladder, exactly as in production.

    ``keep_all_features`` retains EVERY row's selected features instead —
    payload rows and LABEL rows alike, which the address-keyed form
    cannot reach (label rows own no tile).  E4 (the Y-context circularity
    test) needs them: A5's ink map is a region-wide object built from one
    evidence call per row, so rebuilding it outside the ladder needs the
    same per-row features the ladder used.  Default off, and off is
    byte-identical to the address-keyed behaviour for every other caller.

    ``refit_deltas`` maps a tile address to a ``(3, 2)`` page-dot delta,
    and ``refit_overrides`` maps a tile address to an override BUILDER
    ``(row, residuals, spec, base_is_residual) -> tuple`` — the general
    form, which a per-CELL affine (``gt_affine.affine_override``) can
    express and a constant delta cannot.  Both are the REFIT seam: those
    tiles' windows are sampled at the correction BEFORE anything is
    fitted, so the registration fit, the detector, its A5 context bins
    and the emission all see the shifted evidence.  ``None`` — every
    ordinary call — is the frozen-detector path.

    The correction is applied to BOTH arms about each arm's own zero (the
    A0 arm's is the bare committed pose, the A1 arm's is the
    ``PlaneResidual`` prediction), so it reaches the features whichever
    arm the ladder selects.  :class:`RefitDidNotReach` is raised if the
    selected arm's features nevertheless equal that arm's zero.

    NOT STRICTLY LOCAL, deliberately: the corrected base features are
    what ``_fit_registration`` is fitted on, so a correction on one
    tile's cells moves that region's residual model and therefore every
    window's A1 zero by a little.  That is what a receiver holding the
    better geometry would do; the size of the side effect is visible in
    the region's held-out log-loss, which the caller records.
    """
    kind, _arity = _color_kind(spec)
    by_address: dict[tuple[int, int, int], list] = {}
    for certificate in certificates:
        by_address.setdefault(
            (certificate.page, *certificate.tile_yx), []).append(certificate)
    certificate_index = {key: tuple(rows) for key, rows in by_address.items()}
    fully_certified = fully_certified_color_addresses(certificates, spec)
    projection_cache: dict = {}
    suppressed = {
        selected_page: np.asarray(sorted(
            ty * spec.layout.tiles_yx[1] + tx
            for pg, ty, tx in fully_certified if pg == selected_page),
            dtype=np.int64)
        for selected_page in {row[0] for row in fully_certified}}

    patches = tuple(sorted(patches, key=lambda row: int(row.patch_id)))
    aligned_rows = tuple(_window_rows(patch, spec) for patch in patches)
    emission_masks = tuple(
        _emission_mask(spec, page, aligned.page_cells_yx, suppressed)
        for aligned in aligned_rows)
    payload_rows, payload_patches, label_rows, emission_by_row = _split_rows(
        spec, page, patches, aligned_rows, emission_masks,
        certificate_index, projection_cache)
    row_tuple = payload_rows + label_rows
    empty = RegionFit(
        capture_sha256=source.source_sha256, lane_id=source.lane_id,
        region_id=region_id, page=page, source=source, kind=kind,
        pitch_px=0.0, divisor=1.0, residuals=(), selected_fit=None,
        context_bins=None, adopted=False, rows=(), n_payload=0,
        emission_by_row=(), patch_by_ordinal=(), features0={}, tile_rows={},
        n_windows=0, n_labels=0, heldout_loss=float("nan"),
        refusal="no open payload window")
    if not payload_rows:
        return empty

    tile_rows: dict[tuple[int, int, int], list[int]] = {}
    for ordinal, patch in enumerate(payload_patches):
        for address in patch_tiles(patch):
            tile_rows.setdefault(address, []).append(ordinal)
    builder_by_address = dict(refit_overrides or {})
    for address, delta in (refit_deltas or {}).items():
        builder_by_address[address] = constant_override(delta)
    builder_by_row: dict[int, object] = {}
    for address, builder in builder_by_address.items():
        for ordinal in tile_rows.get(address, ()):
            builder_by_row[ordinal] = builder

    pitch_px = float(np.median(tuple(
        patch.segment.segment.pose.pitch_px for patch in patches)))
    crops = window_raw_crops(raster, patches, pitch_px)
    divisor = (
        255.0 if max(float(np.max(raw)) if raw.size else 0.0
                     for _y0, _x0, raw in crops.values()) > 1.5 else 1.0)

    def _base(pair):
        ordinal, row = pair
        builder = builder_by_row.get(ordinal)
        # The A0 arm's zero is the bare committed pose, so the builder is
        # asked for the ``base_is_residual = False`` form and never reads
        # ``residuals`` — which do not exist yet, being fitted BELOW on
        # exactly these features.
        return base_features(
            crops[int(row.patch.patch_id)], row, spec, pitch_px, divisor,
            offsets_override=(None if builder is None
                              else builder(row, None, spec, False)))

    base_tuple = tuple(_parallel.ordered_map(
        _base, tuple(enumerate(row_tuple))))
    zero_base = {
        ordinal: base_features(
            crops[int(row_tuple[ordinal].patch.patch_id)], row_tuple[ordinal],
            spec, pitch_px, divisor)
        for ordinal in builder_by_row}
    crops = {}                      # transient: released with the region
    residuals, _anchors = _fit_registration(
        raster, payload_rows, base_tuple[:len(payload_rows)], spec)

    def _corrected(pair):
        ordinal, row = pair
        builder = builder_by_row.get(ordinal)
        return _features_with_page_fraction(
            raster, row, residuals, spec, pitch_px, divisor,
            offsets_override=(None if builder is None
                              else builder(row, residuals, spec, True)))

    corrected_rows = tuple(_parallel.ordered_map(
        _corrected, tuple(enumerate(row_tuple))))
    corrected = (None if any(row is None for row in corrected_rows)
                 else tuple(row for row in corrected_rows if row is not None))
    zero_corrected = {
        ordinal: _features_with_page_fraction(
            raster, row_tuple[ordinal], residuals, spec, pitch_px, divisor)
        for ordinal in builder_by_row}

    selection = _owner_selection(row_tuple)
    arms = ArmFeatures(base_tuple, corrected)
    del base_tuple, corrected, corrected_rows
    stack = fit_region_stack(
        spec, selection, row_tuple, arms, residuals,
        emission_masks=emission_by_row)
    if stack.selected_fit is None:
        return replace(empty, refusal=stack.refusal_reason or "fit refused")
    refit_probe = (
        None if not builder_by_row else _refit_probe(
            stack, builder_by_address, tile_rows,
            zero_corrected if stack.adopted else zero_base,
            region_id, source.source_sha256))
    del zero_base, zero_corrected
    features0 = {}
    if keep_all_features:
        features0 = {ordinal: np.array(stack.selected_features[ordinal])
                     for ordinal in range(len(row_tuple))}
    else:
        for address in keep_features_for:
            for ordinal in tile_rows.get(address, ()):
                features0.setdefault(
                    ordinal, np.array(stack.selected_features[ordinal]))
    return RegionFit(
        capture_sha256=source.source_sha256, lane_id=source.lane_id,
        region_id=region_id, page=page, source=source, kind=kind,
        pitch_px=pitch_px, divisor=divisor, residuals=residuals,
        selected_fit=stack.selected_fit, context_bins=stack.context_bins,
        adopted=bool(stack.adopted), rows=row_tuple,
        n_payload=len(payload_rows), emission_by_row=emission_by_row,
        patch_by_ordinal=payload_patches, features0=features0,
        tile_rows={key: tuple(value) for key, value in tile_rows.items()},
        n_windows=len(payload_rows), n_labels=len(label_rows),
        heldout_loss=float(stack.selected_fit.heldout_loss),
        refit_probe=refit_probe)


def _refit_probe(stack, builder_by_address, tile_rows, zero_by_ordinal,
                 region_id: str, capture_sha256: str) -> dict:
    """Did the correction reach the features the ladder SELECTED?

    Compares, per touched window, the selected arm's features against
    that arm's OWN zero features, computed through the identical code
    path — so any difference at all is the correction and nothing else.
    A zero difference means the refit silently evaluated at the zero, and
    that is raised rather than recorded.
    """
    arm = "A1" if stack.adopted else "A0"
    rows: dict[str, dict] = {}
    for address in builder_by_address:
        for ordinal in tile_rows.get(address, ()):
            zero = zero_by_ordinal.get(ordinal)
            used = stack.selected_features[ordinal]
            reached = zero is not None and used is not None
            difference = (float(np.abs(np.asarray(used, np.float64)
                                       - np.asarray(zero, np.float64)).max())
                          if reached else float("nan"))
            rows[f"{address}/{ordinal}"] = {
                "address": list(address), "ordinal": int(ordinal),
                "max_abs_feature_delta": difference,
                "mean_abs_feature_delta": (
                    float(np.abs(np.asarray(used, np.float64)
                                 - np.asarray(zero, np.float64)).mean())
                    if reached else float("nan")),
                "n_cells": (0 if not reached else int(np.size(used) // 3)),
            }
    unreached = sorted(
        key for key, row in rows.items()
        if not row["max_abs_feature_delta"] > 0.0)
    if unreached or not rows:
        raise RefitDidNotReach(
            f"{capture_sha256[:12]} {region_id}: the refit override did not "
            f"reach the SELECTED {arm} arm's features for "
            f"{unreached or 'any window'} — the refit would have evaluated "
            f"at the zero and reported it as a validation")
    return {"arm": arm, "windows": rows,
            "max_abs_feature_delta": max(
                row["max_abs_feature_delta"] for row in rows.values()),
            "min_abs_feature_delta": min(
                row["max_abs_feature_delta"] for row in rows.values())}


# --------------------------------------------------------------------------
# per-candidate sampling and evidence
# --------------------------------------------------------------------------
def window_features(fit: RegionFit, raster, spec, ordinal: int,
                    delta_page_dots: np.ndarray | None) -> np.ndarray | None:
    """One window's features at a per-plane PAGE-dot delta.

    ``delta_page_dots`` is ``(3, 2)`` — per plane, ``(dx, dy)`` PAGE dots
    added to the delta = 0 sampling grid.  ``None`` or an all-zero delta
    returns the cached delta = 0 features, so the pilot never re-reads
    pixels for its own baseline.
    """
    if delta_page_dots is None or not np.any(delta_page_dots):
        cached = fit.features0.get(ordinal)
        if cached is not None:
            return cached
    row = fit.rows[ordinal]
    return _features_with_page_fraction(
        raster, row, fit.residuals, spec, fit.pitch_px, fit.divisor,
        offsets_override=override_offsets(
            row, fit.residuals, spec,
            np.zeros((3, 2)) if delta_page_dots is None else delta_page_dots,
            fit.base_is_residual))


def window_evidence(fit: RegionFit, ordinal: int,
                    features: np.ndarray) -> ColorWindowEvidence:
    """The production emission step for one window's features."""
    row = fit.rows[ordinal]
    emit = fit.emission_by_row[ordinal]
    certified = (
        np.asarray(row.known_component_mask, np.bool_)
        & (np.asarray(row.furniture_kind, np.int8) < 0)[:, None])[emit]
    bins = (None if fit.context_bins is None
            else fit.context_bins[ordinal][emit])
    values, _divisor = fit.selected_fit.evidence_with_divisor(
        features[emit], certified,
        np.asarray(row.known_component_bits, np.uint8)[emit], bins)
    return ColorWindowEvidence(
        source=fit.source,
        placement_id=(f"{fit.source.source_sha256}/{fit.source.lane_id}/"
                      f"patch-{int(row.patch.patch_id)}"),
        patch_id=int(row.patch.patch_id),
        region_id=fit.region_id,
        page=fit.page,
        page_cells_yx=row.page_cells_yx[emit],
        evidence_values=np.asarray(values, np.float32),
        heldout_logloss=_window_loss(
            fit.selected_fit.model, row, features,
            fit.selected_fit.heldout_loss),
        evidence_kind=fit.kind,
        dependency_certificate_ids=(),
    )


def capture_blocks(fit: RegionFit, spec, windows) -> tuple:
    """One capture's durable blocks for the supplied window evidence."""
    rows = tuple(windows)
    frontier = ColorCaptureEvidence(
        fit.source, spec.spec_id, fit.kind, rows,
        _freeze(fit.source, spec, rows), ())
    return color_blocks_from_frontier(frontier)


def attempt(blocks, spec, address, stream_id, *, stage=AttemptStage.UNION):
    """THE ORACLE: the ordinary certificate gate over the union view."""
    components = tuple(row for row in blocks if row.address == address)
    if not components:
        return None
    view = tile_attempt_view(components)
    return attempt_color_tile(
        view, spec, stream_id, stage,
        source_sha256=components[0].source_sha256,
        lane_id=components[0].lane_id)


def null_proof(fit: RegionFit, raster, spec, ordinal: int) -> dict:
    """delta = 0 through the override seam == the SELECTED arm's features.

    Both arms are checked, each against its own zero — the A0 case used
    to short-circuit to ``True``, which meant the seam went unverified on
    exactly the captures where it is not the identity map (two of sheet
    I's three).  The bars differ because the paths do:

    * **A1**: the override reproduces ``residual.offsets`` and adds an
      exact ``0.0``, so the sample points are identical and the answer
      must be BIT-identical.
    * **A0**: the seam samples the exact point footprint
      (``_points_crop``) where the arm samples the WINDOW footprint.  The
      points are the same, the aperture filter is the same box in
      float32, but it accumulates from a different crop origin — so the
      bar is float32 rounding, and anything larger is a real geometric
      disagreement.
    """
    row = fit.rows[ordinal]
    zeroed = _features_with_page_fraction(
        raster, row, fit.residuals, spec, fit.pitch_px, fit.divisor,
        offsets_override=override_offsets(
            row, fit.residuals, spec, np.zeros((N_PLANES, 2)),
            fit.base_is_residual))
    if fit.base_is_residual:
        historical = _features_with_page_fraction(
            raster, row, fit.residuals, spec, fit.pitch_px, fit.divisor)
    else:
        crop = window_raw_crops(raster, (row.patch,), fit.pitch_px)[
            int(row.patch.patch_id)]
        historical = base_features(
            crop, row, spec, fit.pitch_px, fit.divisor)
    if historical is None or zeroed is None:
        return {"arm": "A1" if fit.base_is_residual else "A0",
                "ok": False, "reason": "a sampler refused"}
    worst = float(np.abs(np.asarray(historical, np.float64)
                         - np.asarray(zeroed, np.float64)).max())
    bit_identical = bool(np.array_equal(historical, zeroed))
    return {
        "arm": "A1" if fit.base_is_residual else "A0",
        "bit_identical": bit_identical,
        "within_float32_rounding": bool(worst <= 1e-6),
        "max_abs_diff": worst,
        "cells_checked": int(np.size(historical) // N_PLANES),
        # The A1 seam must be exact; the A0 seam crosses a crop boundary.
        "ok": bit_identical if fit.base_is_residual else bool(worst <= 1e-6),
    }


__all__ = [
    "N_PLANES", "AttemptStage", "RefitDidNotReach", "RegionFit", "attempt",
    "base_features", "capture_blocks", "constant_override", "fit_region",
    "null_proof", "override_offsets", "page_to_local_dots", "patch_tiles",
    "window_evidence", "window_features",
]
