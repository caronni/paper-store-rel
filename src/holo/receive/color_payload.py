"""Color evidence collection on BCH-promoted E022 placements.

This module owns the COLLECTION half of the durable color evidence
contract — region sampling, the arm ladder's inputs, and the emission of
one evidence row per accepted window.  Its other half, the record types
plus the one-owner freeze and the block conversion, is
:mod:`holo.receive.color_evidence` (split out 2026-08-20 at the seam this
header already named); those names are re-exported below, so the public
import surface is unchanged.  The image/grid work around the isolated
numerical leaves lives beside it:

* :mod:`holo.receive.color_sampling` — every raster read: crops, aperture
  filtering, and point sampling;
* :mod:`holo.receive.known_field` — the one derivation of what the
  receiver KNOWS about a window's cells (format furniture + prior-barrier
  certified components), and the single enforcement point of the §6.2a
  provenance law;
* :mod:`holo.receive.color_anchoring` — reference states and residual
  registration anchoring;
* :mod:`holo.receive.color_fitting` — region/page detector fits and the
  bounded CMY7 score adapter; and
* :mod:`holo.receive.color_stack` — the gated arm ladder that chooses one
  region's evidence model.

Collection deliberately stops before durable evidence blocks or FEC
attempts:

* E022 remains the sole geometry/address authority;
* quarantined placements are absent through ``payload_placements``;
* word and dust furniture train and validate one region/page model;
* label rows (D7 label placements + certified-complete windows, §8.2 pool
  law) feed that model and the pitch pool but never own or emit;
* C/M/Y residual registration is held-out gated against the shared pose;
* every accepted window emits physical-cell CMY7 or CMY8 evidence; and
* one deterministic owner is selected per acquisition/page/payload cell.

Raw RGB, detector models, and registration work are transient.  Only the
owned score vectors and their compact origin facts cross into persistence.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from ..format.descriptor import FormatSpec
from ._payload_sampling import _window_rows
from .color_anchoring import (
    COLOR_CMY7_KIND,
    COLOR_CMY8_KIND,
    _Rows,
    _color_kind,
    _features_with_page_fraction,
    _fit_registration,
    _label_site_rows,
    _neighbor_rows,
    color_reference_states,
)
from .color_fitting import (
    CMY7_RELATIVE_SCORE_BOUND,
    _owner_selection,
    _window_loss,
)
from .color_pool import (
    _emission_mask,
    _payload_cell_mask,
    fully_certified_color_addresses,
)
from .color_evidence import (
    ColorCaptureEvidence,
    ColorOwnedPageEvidence,
    ColorRegionSummary,
    ColorWindowEvidence,
    _freeze,
    color_blocks_from_frontier,
)
from .color_field import (
    PlaneFieldBuilder,
    PlaneFieldConfig,
    PlaneFieldReport,
    ProbeWindow,
    certified_projection_source,
    field_corrected_features,
)
from .color_projection import CertifiedColorProjection
from .color_registration import PlaneResidual
from .color_sampling import RawRGBRaster, crop_features, window_raw_crops
from .color_stack import ArmFeatures, StackConfig, fit_region_stack
from .evidence import TileCertificateRecord
from .known_field import build_known_rows
from .payload_model import EvidenceSource, PlacementModelError
from .color_policy import COLOR_PAYLOAD_POLICY_ID
from .placement.model import AddressResult, PlacedPatch
from . import _parallel


def collect_color_evidence(
    raster: RawRGBRaster,
    source: EvidenceSource,
    address: AddressResult,
    spec: FormatSpec,
    *,
    certificates: tuple[TileCertificateRecord, ...] = (),
    region_progress: Callable[[ColorRegionSummary], None] | None = None,
    included_patch_ids: frozenset[int] | None = None,
    arm_override: str | None = None,
    stack_config: StackConfig | None = None,
    plane_fields: PlaneFieldConfig | None = None,
    plane_field_progress: Callable[[PlaneFieldReport], None] | None = None,
) -> ColorCaptureEvidence:
    """Sample and calibrate one color capture/lane.

    Grayscale lanes refuse by returning no windows or pages.  A malformed
    RGB crop or E022 lineage remains an error because it indicates a broken
    internal contract rather than ordinary low detector support.

    ``arm_override`` (PK4.3) is the SUPPLEMENTAL lane's forced arm, one of
    ``types.UPLIFT_ARMS`` — lane-scoped configuration threaded explicitly
    from ``LaneSpec.arm_override`` and passed straight to the ladder.
    ``None`` (every ordinary, mop-up and refinement level) is the standing
    receiver, bit for bit.

    ``stack_config`` (``color_stack.StackConfig``) is the harness's
    explicit sweep record, threaded the same way; ``None`` — every
    production caller — is the frozen constants the policy id names.

    ``plane_fields`` (``color_field.PlaneFieldConfig``) is the
    PLANE-FIELDS W2/W4 dial, threaded the same way again and DEFAULT OFF:
    ``None`` builds no field, runs no probe, emits no event, and leaves
    the registration seam on its historical ``PlaneResidual`` branch bit
    for bit.  When it is set, ``plane_field_progress`` receives one
    ``PlaneFieldReport`` for the whole capture after the region loop —
    the analytics seam, since this leaf holds no ``LaneContext``.

    Pool law (RECEIVE-DESIGN §8.2, v0.35), color half: wholly terminal
    regions drop before image work (L1); a mixed region's certified-complete
    windows (every covered work key certified) do no payload work but join
    the region QDA/PAVA fit as furniture-site label rows (L2/L6), as do
    ``address.label_placements``, never terminal-gated (L3); the pitch and
    divisor pool is placements UNION label placements (L5).  Label rows
    never enter the returned windows, owned pages, blocks, or attempts.
    """
    kind, _arity = _color_kind(spec)
    # Interior seam: typed inputs are trusted (kiss validation-boundary
    # ruling).  Authority is still checked before any terminal-region fast
    # path: two different certificates for one work key are a contradiction
    # even if this region would otherwise be skipped without projecting
    # their payload.
    certificates_by_address: dict[
        tuple[int, int, int], list[TileCertificateRecord]
    ] = {}
    for certificate in certificates:
        certificates_by_address.setdefault(
            (certificate.page, *certificate.tile_yx), []
        ).append(certificate)
    certificate_index = {
        address_key: tuple(rows)
        for address_key, rows in certificates_by_address.items()
    }
    # The only legal value is derived here from the certificate authority
    # (the historical re-derive-and-compare parameter was deleted — trust
    # rulings 9.5/13a).
    fully_certified_addresses = fully_certified_color_addresses(
        certificates, spec)
    projection_cache: dict[
        tuple[int, int, int], CertifiedColorProjection
    ] = {}

    def codes_by_page(
        addresses: frozenset[tuple[int, int, int]],
    ) -> dict[int, np.ndarray]:
        return {
            selected_page: np.asarray(
                sorted(
                    ty * spec.layout.tiles_yx[1] + tx
                    for page, ty, tx in addresses
                    if page == selected_page
                ),
                dtype=np.int64,
            )
            for selected_page in sorted({
                value[0] for value in addresses})
        }

    fully_certified_codes_by_page = codes_by_page(
        fully_certified_addresses)
    suppressed_codes_by_page = fully_certified_codes_by_page
    # Refined-reuse seam (rework 6.1, K parity with collect_capture_evidence):
    # `included_patch_ids` restricts the sampled payload domain to the named
    # placements — the refined path passes exactly the affected regions'
    # complete patch sets, so each recomputed region replays with its full
    # generation-zero fit population.
    payload_placements = address.payload_placements
    if included_patch_ids is not None:
        payload_placements = tuple(
            row for row in payload_placements
            if int(row.patch_id) in included_patch_ids)
    if not payload_placements:
        return ColorCaptureEvidence(
            source, spec.spec_id, kind, (), (), ())

    grouped: dict[tuple[int, int], list[PlacedPatch]] = {}
    for patch in payload_placements:
        grouped.setdefault(
            (int(patch.region_index), int(patch.candidate.page)), []
        ).append(patch)
    labels_grouped: dict[tuple[int, int], list[PlacedPatch]] = {}
    for patch in address.label_placements:
        labels_grouped.setdefault(
            (int(patch.region_index), int(patch.candidate.page)), []
        ).append(patch)

    output: list[ColorWindowEvidence] = []
    summaries: list[ColorRegionSummary] = []
    unmeasured = tuple(PlaneResidual((0.0, 0.0), (0.0, 0.0), 0)
                       for _ in range(3))
    raster_probed = False
    # PLANE-FIELDS W2/W4: ONE field per capture, accumulated across
    # regions in canonical order and re-solved per region, so a region
    # sees its own evidence plus every earlier region's (the tile-space
    # pooling payoff, §3).  ``None`` — every production caller — never
    # constructs it and never reaches the seam.
    # ``done_tiles`` comes from the certificate authority, not from what
    # the probe pass happened to visit (INDEPENDENT-PLANES §6 P1).
    field_builder = (
        None if plane_fields is None
        else PlaneFieldBuilder(
            spec, plane_fields, done_tiles=fully_certified_addresses))
    certified_projection = certified_projection_source(
        spec, certificate_index, projection_cache, fully_certified_addresses)
    for (region_index, page), patch_rows in sorted(grouped.items()):
        patches = tuple(sorted(
            patch_rows, key=lambda row: int(row.patch_id)))
        label_patches = tuple(sorted(
            labels_grouped.get((region_index, page), ()),
            key=lambda row: int(row.patch_id)))
        prefix = f"{source.source_sha256}/{source.lane_id}"
        region_id = f"{prefix}/region-{region_index}/page-{page}"
        aligned_rows = tuple(
            _window_rows(patch, spec) for patch in patches)
        # Pool law L2/L4/L6: a window owes payload work only while one of
        # its payload cells lies on a tile with an uncertified stream —
        # the suppressed codes are the tiles whose EVERY stream certified.
        # The emission masks are computed ONCE here and reused by the
        # emission loop below (color-payload:06).
        emission_masks = tuple(
            _emission_mask(
                spec, page, aligned.page_cells_yx,
                suppressed_codes_by_page)
            for aligned in aligned_rows
        )
        open_flags = tuple(
            bool(np.any(
                _payload_cell_mask(spec, aligned.page_cells_yx) & emit
            ))
            for aligned, emit in zip(
                aligned_rows, emission_masks, strict=True)
        )
        if not any(open_flags):
            # Pool law L1: wholly terminal — no image work, no label rows.
            summary = ColorRegionSummary(
                region_id=region_id,
                page=page,
                accepted=True,
                reason="fully_certified_pruned",
                n_patches=len(patches),
                n_train=0,
                n_heldout=0,
                class_counts=(),
                baseline_heldout_logloss=None,
                selected_heldout_logloss=None,
                registration_adopted=False,
                residuals=unmeasured,  # type: ignore[arg-type]
                dependency_certificate_ids=(),
                uplift_arm=arm_override or "",
            )
            summaries.append(summary)
            continue
        if not raster_probed:
            probe = np.asarray(raster.crop_native(0, 1, 0, 1))
            if probe.ndim != 3 or probe.shape[2] != 3:
                return ColorCaptureEvidence(
                    source, spec.spec_id, kind, (), (), ())
            raster_probed = True
        payload_rows: list[_Rows] = []
        label_rows: list[_Rows] = []
        probe_windows: list[ProbeWindow] = []
        emission_by_row: list[np.ndarray] = []
        for patch, aligned, is_open, emit in zip(
                patches, aligned_rows, open_flags, emission_masks,
                strict=True):
            if field_builder is not None:
                # PLANE-FIELDS W4 (§6.1 pitfall 3): a label-only window
                # contributes NO anchor, so the strongest evidence tier
                # lives exactly where nothing looks.  The probe pass gets
                # the FULL audited alignment, not the sparse label row.
                # EVERY window is offered, mixed ones included
                # (INDEPENDENT-PLANES §4.G, ruling 2026-08-23): a fully
                # certified tile inside a still-open window is exactly as
                # certified, and the window covering it is exactly as
                # posed — and a tile that STRADDLES a boundary can now be
                # measured through each of its windows.
                probe_windows.append(ProbeWindow(
                    patch, page,
                    aligned.local_cells_yx, aligned.page_cells_yx))
            if not is_open:
                # L2: certified-complete/zero-payload — label row only.
                label_row = _label_site_rows(
                    spec, page, patch, aligned, certificate_index)
                if label_row is not None:
                    label_rows.append(label_row)
                continue
            # The ONE known-printed-field derivation (§6.2a provenance
            # law): format furniture plus prior-barrier certified
            # components, and nothing else.
            known = build_known_rows(
                spec,
                page,
                aligned.page_cells_yx,
                certificate_index,
                projection_cache,
            )
            row = _Rows(
                patch,
                aligned.local_cells_yx,
                aligned.page_cells_yx,
                aligned.scan_points_yx,
                known.states,
                known.furniture_kind,
                known.component_bits,
                known.component_mask,
                _neighbor_rows(aligned.local_cells_yx),
                known.dependency_certificate_ids,
            )
            payload_rows.append(row)
            emission_by_row.append(emit)
        for patch in label_patches:
            # L3: D7 label placements are never terminal-gated.
            label_row = _label_site_rows(
                spec, page, patch, _window_rows(patch, spec),
                certificate_index)
            if label_row is not None:
                label_rows.append(label_row)
        payload_row_tuple = tuple(payload_rows)
        row_tuple = payload_row_tuple + tuple(label_rows)
        # Pool law L5: the region pitch (and the divisor scale probe) pools
        # placements UNION label placements — the single-pass population.
        pitch_px = float(np.median(tuple(
            patch.segment.segment.pose.pitch_px
            for patch in patches + label_patches)))
        # One native read per window (color-upstream:07): the identical
        # probe/base crop footprint previously read twice — once for the
        # divisor maximum, once for the filtered base features.
        crops = window_raw_crops(
            raster, patches + label_patches, pitch_px)
        divisor = (
            255.0
            if max(
                float(np.max(raw)) if raw.size else 0.0
                for _y0, _x0, raw in crops.values()) > 1.5
            else 1.0
        )
        # Pure per-row filter+sample kernels: pooled ordered maps are
        # value-identical to the sequential comprehensions.
        base_tuple = tuple(_parallel.ordered_map(
            lambda row: crop_features(
                crops[int(row.patch.patch_id)], row.scan_points_yx,
                pitch_px, divisor),
            row_tuple))
        del crops
        # NCC anchors need complete 3x3 in-row neighbourhoods; a label
        # row's sparse furniture sites have none, so payload rows alone
        # carry the anchor workload (label rows would burn budget bins).
        # PK6 measure-first: the anchor field feeds instrumentation only
        # while the PLANE-FIELDS dial is off (every production caller).
        residuals, registration_anchors = _fit_registration(
            raster, payload_row_tuple,
            base_tuple[:len(payload_row_tuple)], spec)
        if field_builder is None:
            corrected_rows = tuple(_parallel.ordered_map(
                lambda row: _features_with_page_fraction(
                    raster, row, residuals, spec, pitch_px, divisor),
                row_tuple,
            ))
        else:
            field_builder.add_anchors(
                payload_row_tuple, registration_anchors)
            field_builder.add_certified_probes(
                raster, tuple(probe_windows), certified_projection)
            field_builder.solve()
            overrides, _adopted = field_builder.region_offsets(
                page, row_tuple)
            field_results = tuple(_parallel.ordered_map(
                lambda pair: field_corrected_features(
                    raster, pair[0], residuals, spec, pitch_px, divisor,
                    pair[1]),
                tuple(zip(row_tuple, overrides, strict=True)),
            ))
            corrected_rows = tuple(row for row, _null in field_results)
            for _row, nulled in field_results:
                if nulled:
                    field_builder.note_window_null()
        corrected = (
            None
            if any(row is None for row in corrected_rows)
            else tuple(row for row in corrected_rows if row is not None)
        )
        region_dependencies = tuple(sorted({
            identity for row in row_tuple
            for identity in row.dependency_certificate_ids
        }))
        # Ownership and the deterministic split depend only on the rows —
        # computed once, shared by every arm (color-upstream:07).
        selection = _owner_selection(row_tuple)
        # The ladder CONSUMES the arm tuples (color_stack's memory
        # ownership note): this frame drops its own references first, so
        # a tuple no arm can still select is freed inside the ladder
        # rather than living until the region loop rebinds.
        arms = ArmFeatures(base_tuple, corrected)
        del base_tuple, corrected, corrected_rows
        stack = fit_region_stack(
            spec, selection, row_tuple, arms, residuals,
            emission_masks=tuple(emission_by_row),
            arm_override=arm_override,
            stack_config=stack_config)
        baseline_fit = stack.baseline_fit
        selected_fit = stack.selected_fit
        selected_features = stack.selected_features
        adopted = stack.adopted
        if selected_fit is None:
            summary = ColorRegionSummary(
                region_id=region_id,
                page=page,
                accepted=False,
                reason=(stack.refusal_reason
                        or "color payload: detector fit refused"),
                n_patches=len(patches),
                n_train=0,
                n_heldout=0,
                class_counts=(),
                baseline_heldout_logloss=None,
                selected_heldout_logloss=None,
                registration_adopted=False,
                residuals=residuals,
                dependency_certificate_ids=region_dependencies,
                uplift_arm=arm_override or "",
            )
            summaries.append(summary)
            if region_progress is not None:
                region_progress(summary)
            continue

        # Only payload rows emit: label rows never own, block, or attempt.
        emitted_cells = 0
        saturated_cells = 0
        # A5 (P2): the per-row context bins, or ``None`` for every region
        # whose neighbourhood corrector refused — in which case the loop
        # below passes ``None`` and takes the literal pre-P2 path.
        context_bins = stack.context_bins
        for ordinal, (row, features, emit) in enumerate(zip(
                payload_row_tuple,
                selected_features[:len(payload_row_tuple)],
                emission_by_row,
                strict=True)):
            if not np.any(emit):
                continue
            # A4b (P9): the emitted cells' KnownField rows ride along.
            # Only CERTIFIED components condition — a payload cell's
            # known components can come from nowhere else, and format
            # furniture is excluded HERE rather than inside the head, so
            # the population the arm deploys on is exactly the one its
            # precondition counted (``color_stack``).  Every path with no
            # adopted A4b head ignores both arrays.
            certified = (
                np.asarray(row.known_component_mask, np.bool_)
                & (np.asarray(row.furniture_kind, np.int8) < 0)[:, None]
            )[emit]
            values, divisor = selected_fit.evidence_with_divisor(
                features[emit], certified,
                np.asarray(row.known_component_bits, np.uint8)[emit],
                None if context_bins is None else context_bins[ordinal][emit])
            evidence = np.asarray(values, np.float32)
            if divisor is not None:
                # P1's saturation canary, free: the divisor is the one the
                # bound just used, so no cell is scored twice.
                emitted_cells += int(divisor.shape[0])
                saturated_cells += int(np.count_nonzero(divisor > 1.0))
            if not np.isfinite(evidence).all():
                raise ValueError(
                    "color payload: detector emitted nonfinite evidence")
            placement_id = (
                f"{source.source_sha256}/{source.lane_id}/"
                f"patch-{int(row.patch.patch_id)}")
            output.append(ColorWindowEvidence(
                source=source,
                placement_id=placement_id,
                patch_id=int(row.patch.patch_id),
                region_id=region_id,
                page=page,
                page_cells_yx=row.page_cells_yx[emit],
                evidence_values=evidence,
                heldout_logloss=_window_loss(
                    selected_fit.model, row, features,
                    selected_fit.heldout_loss),
                evidence_kind=kind,
                dependency_certificate_ids=region_dependencies,
            ))
        summary = ColorRegionSummary(
            region_id=region_id,
            page=page,
            accepted=True,
            reason=(
                "accepted"
                if all(selected_fit.component_supported)
                else "accepted_component_erasures"
            ),
            n_patches=len(patches),
            n_train=selected_fit.n_train,
            n_heldout=selected_fit.n_heldout,
            class_counts=selected_fit.class_counts,
            baseline_heldout_logloss=(
                None if baseline_fit is None
                else baseline_fit.heldout_loss),
            selected_heldout_logloss=selected_fit.heldout_loss,
            registration_adopted=adopted,
            residuals=residuals,
            dependency_certificate_ids=region_dependencies,
            calibration_labels=selected_fit.calibration_labels,
            component_supported=selected_fit.component_supported,
            component_support_reasons=selected_fit.component_support_reasons,
            cmy7_head_reason=stack.head_reason,
            cmy7_head_adopted=stack.head_adopted,
            cmy7_head_temperature=stack.head_temperature,
            cmy7_saturation_fraction=(
                0.0 if not emitted_cells
                else saturated_cells / emitted_cells),
            cmy7_baseline_saturation_fraction=stack.head_saturation_fraction,
            cmy7_head_saturation_floor=stack.head_saturation_floor,
            window_photometry=stack.window_photometry,
            conditioning=stack.conditioning,
            context=stack.context,
            uplift_arm=arm_override or "",
        )
        summaries.append(summary)
        if region_progress is not None:
            region_progress(summary)

    if field_builder is not None and plane_field_progress is not None:
        # ONE capture-level report, after the last region — the field is
        # a property of the sheet, not of any single region.
        plane_field_progress(field_builder.report())

    windows = tuple(output)
    if len({row.placement_id for row in windows}) != len(windows):
        raise PlacementModelError(
            "color payload: E022 patch identities repeat")
    return ColorCaptureEvidence(
        source, spec.spec_id, kind, windows,
        _freeze(source, spec, windows), tuple(summaries))


__all__ = [
    "CMY7_RELATIVE_SCORE_BOUND",
    "COLOR_CMY7_KIND", "COLOR_CMY8_KIND", "COLOR_PAYLOAD_POLICY_ID",
    "ColorCaptureEvidence", "ColorOwnedPageEvidence",
    "ColorRegionSummary", "ColorWindowEvidence",
    "RawRGBRaster", "collect_color_evidence",
    "color_blocks_from_frontier",
    "color_reference_states",
    "fully_certified_color_addresses",
]
