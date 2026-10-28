"""The four sampling configurations, and the decode verdict at each.

docs/COMPOSITE-POSE-DESIGN.md §3 fixes the composite's order by physics:
the printer field acts on the page, the pose acts on the paper.  At the
seam both arrive as a per-plane ``(dx, dy)`` print-dot array along the
window's LOCAL axes (``color_anchoring._features_with_page_fraction``'s
``offsets_override``), where the composite is additive -- so a
configuration here is exactly one such array per plane per window:

    (i)   committed          the arm's OWN zero -- today's pre-field
                             sampling (``PlaneResidual`` on an A1 fit,
                             the bare committed pose on an A0 one)
    (ii)  field              the per-plane field delta on every ADOPTED
                             plane (``PlaneFieldBuilder.region_offsets``),
                             the arm's zero elsewhere
    (iii) field+pose-t       (ii) plus the window's plane-common
                             TRANSLATION
    (iv)  field+pose-affine  (ii) plus the window's plane-common local
                             AFFINE

EVERY configuration, (i) included, goes through the SAME override path.
That is deliberate: ``_swim_region.null_proof`` measures the seam to be
bit-identical on an A1 fit and within float32 rounding on an A0 one, and
putting the baseline through the other branch would put that rounding
into the very difference the instrument is trying to measure.

Attempts only ADD evidence, so (iii)/(iv) certifying a slot that (ii)
also certified is not news; the number the P5 bar is about is the
INCREMENT, and the per-slot cell BER is what shows a gain where the gate
was not crossed.
"""
from __future__ import annotations

import numpy as np

from . import _swim_region

N_PLANES = 3

#: The configurations, in ladder order.  The last two are the
#: DIFFERENTIAL arms and they are not part of the pre-registered clause:
#: the shipped field is fed the FULL local probe offset per plane, so its
#: prediction already carries a (page-smoothed) plane-common component,
#: and a pose writer stacked on top of it double-counts.  Subtracting the
#: field's own plane-common part restores COMPOSITE-POSE-DESIGN §4.1's
#: construction -- "Delta_p is defined RELATIVE to the plane-common
#: frame" -- and lets the plane-common sampling come from the pose alone.
CONFIGS = ("committed", "field", "field+pose-t", "field+pose-affine",
           "field-diff", "field-diff+pose-t")
#: The subset a REFIT footing pays for (a refit whose override equals the
#: arm's own zero is a no-op ``fit_region`` refuses by design).
REFIT_CONFIGS = ("field", "field+pose-t", "field-diff+pose-t")


def arm_zero(row, residuals, spec, base_is_residual: bool) -> np.ndarray:
    """``(3, n, 2)`` the arm's own zero offsets for one window."""
    count = row.page_cells_yx.shape[0]
    if not base_is_residual:
        return np.zeros((N_PLANES, count, 2), np.float64)
    fraction = (row.page_cells_yx[:, 0].astype(np.float64)
                / spec.layout.cells_yx[0])
    return np.stack([residuals[plane].offsets(fraction)
                     for plane in range(N_PLANES)])


def config_override(row, residuals, spec, base_is_residual: bool,
                    field_row, pose, config: str) -> tuple:
    """``offsets_override`` for one window under one configuration.

    ``field_row`` is one entry of ``region_offsets``'s first return value:
    a per-plane ``(n, 2)`` LOCAL-frame array, or ``None`` where the region
    did not adopt that plane.  ``pose`` is that window's
    :class:`~._pose_probe.WindowPose`, or ``None`` when no probe reached
    it -- in which case the pose configurations fall back to (ii) FOR
    THAT WINDOW, which is what a writer with no evidence would do.

    A ``field-diff`` configuration replaces the field's plane-common part
    with the ARM'S OWN, so the only plane-common content in the sampling
    is whatever the pose configuration adds.  It needs all three planes
    adopted -- a differential over a varying subset of planes is not a
    differential -- and falls back to the plain field arm otherwise.
    """
    base = arm_zero(row, residuals, spec, base_is_residual)
    out = [np.array(base[plane], np.float64) for plane in range(N_PLANES)]
    if config != "committed" and field_row is not None:
        entries = [field_row[plane] for plane in range(N_PLANES)]
        if config.startswith("field-diff") and all(
                entry is not None for entry in entries):
            stacked = np.stack(
                [np.asarray(entry, np.float64) for entry in entries])
            stacked = stacked - stacked.mean(axis=0) + base.mean(axis=0)
            out = [stacked[plane] for plane in range(N_PLANES)]
        else:
            for plane in range(N_PLANES):
                if entries[plane] is not None:
                    out[plane] = np.asarray(entries[plane], np.float64).copy()
    if pose is not None and (config.endswith("pose-t")
                             or config.endswith("pose-affine")):
        correction = pose.offsets(
            row.local_cells_yx, affine=config.endswith("pose-affine"))
        for plane in range(N_PLANES):
            out[plane] = out[plane] + correction
    return tuple(out)


def field_common_content(fit, spec, field_by_patch, poses) -> dict:
    """Does the FIELD already carry the window's plane-common residual?

    The pose writer's premise (COMPOSITE-POSE-DESIGN §6) is that the
    plane-common half of every probe measurement is currently thrown
    away.  It is not: the field is fed each plane's FULL local offset, so
    its per-plane prediction contains that half too, pooled over tile
    space.  This measures how much -- per window, the plane-common CHANGE
    configuration (ii) makes to the sampling, against the per-window
    translation a writer would add on top.  A slope near 1 means the two
    are the same correction applied twice.
    """
    rows = []
    for ordinal in range(fit.n_payload):
        row = fit.rows[ordinal]
        patch_id = int(row.patch.patch_id)
        pose = poses.get(patch_id)
        if pose is None:
            continue
        base = arm_zero(row, fit.residuals, spec, fit.base_is_residual)
        field = config_override(
            row, fit.residuals, spec, fit.base_is_residual,
            field_by_patch.get(patch_id), None, "field")
        change = (np.stack(field).mean(axis=0) - base.mean(axis=0)).mean(
            axis=0)
        rows.append((change, np.asarray(pose.translation_xy, np.float64)))
    if not rows:
        return {"windows": 0}
    field_common = np.asarray([row[0] for row in rows], np.float64)
    pose_common = np.asarray([row[1] for row in rows], np.float64)
    slopes = []
    for axis in range(2):
        denominator = float((pose_common[:, axis] ** 2).sum())
        slopes.append(
            None if denominator == 0.0 else
            float((field_common[:, axis] * pose_common[:, axis]).sum()
                  / denominator))
    return {
        "windows": len(rows),
        "field_common_magnitude_median": float(np.median(
            np.hypot(field_common[:, 0], field_common[:, 1]))),
        "pose_translation_magnitude_median": float(np.median(
            np.hypot(pose_common[:, 0], pose_common[:, 1]))),
        "residual_after_removing_pose_median": float(np.median(np.hypot(
            *(field_common - pose_common).T))),
        "regression_slope_field_on_pose_xy": slopes,
        "correlation_xy": [
            float(np.corrcoef(field_common[:, axis],
                              pose_common[:, axis])[0, 1])
            for axis in range(2)],
    }


def override_builder(spec, field_by_patch, poses, config: str):
    """A ``fit_region(refit_overrides=...)`` builder for one configuration.

    The E1 refit seam (INDEPENDENT-PLANES §6 P2): handing this to
    ``_swim_region.fit_region`` re-cuts the registration fit, the QDA/PAVA
    stack and the A5 context BINS at the corrected geometry instead of
    scoring corrected samples through a detector cut at delta = 0.
    ``fit_region`` calls it once per arm, with that arm's own
    ``base_is_residual``.
    """
    def build(row, residuals, spec_, base_is_residual: bool) -> tuple:
        patch_id = int(row.patch.patch_id)
        return config_override(
            row, residuals, spec_ or spec, base_is_residual,
            field_by_patch.get(patch_id), poses.get(patch_id), config)

    return build


# --------------------------------------------------------------------------
# one capture, one configuration
# --------------------------------------------------------------------------
def capture_blocks(fit, raster, spec, field_by_patch, poses, config: str,
                   addresses: frozenset, *, use_cached: bool = False
                   ) -> dict[tuple[int, int, int], tuple]:
    """Every payload window resampled, emitted, frozen -- blocks per tile.

    ``use_cached`` is the REFIT footing: the fit was already built with
    this configuration's override in place, so ``fit.features0`` already
    holds the selected arm's corrected features and re-sampling would
    only reproduce them (through the other arm's zero, at that).
    """
    from holo.receive import _parallel
    from holo.receive.color_anchoring import _features_with_page_fraction

    def one(ordinal: int):
        row = fit.rows[ordinal]
        if use_cached:
            return fit.features0.get(ordinal)
        return _features_with_page_fraction(
            raster, row, fit.residuals, spec, fit.pitch_px, fit.divisor,
            offsets_override=config_override(
                row, fit.residuals, spec, fit.base_is_residual,
                field_by_patch.get(int(row.patch.patch_id)),
                poses.get(int(row.patch.patch_id)), config))

    ordinals = tuple(range(fit.n_payload))
    features = _parallel.ordered_map(one, ordinals)
    windows = []
    nulls = 0
    for ordinal, values in zip(ordinals, features, strict=True):
        if values is None:
            nulls += 1
            continue
        windows.append(_swim_region.window_evidence(fit, ordinal, values))
    del features
    if not windows:
        return {}, nulls
    blocks = _swim_region.capture_blocks(fit, spec, windows)
    del windows
    grouped: dict[tuple[int, int, int], list] = {}
    for block in blocks:
        if block.address in addresses:
            grouped.setdefault(block.address, []).append(block)
    return {key: tuple(value) for key, value in grouped.items()}, nulls


# --------------------------------------------------------------------------
# the oracle and the ground-truth cell error
# --------------------------------------------------------------------------
def slot_verdict(blocks_by_capture, spec, target) -> dict:
    """The ordinary certificate gate over the union, UNION then RETRY150.

    A UNION attempt identity names its component blocks and the receiver
    refuses to mint one over fewer than two (``tiles.attempt_identity``);
    a tile carried by a single window of a single capture therefore has
    no union verdict at all, and saying so is the honest answer rather
    than substituting a different attempt identity.
    """
    from .swim_pilot import union_verdict

    per_capture = [row.get(target.address, ()) for row in blocks_by_capture]
    if sum(len(row) for row in per_capture) < 2:
        return {"certified": False,
                "reason": "fewer than two blocks — no union identity"}
    return union_verdict(per_capture, spec, target)


def override_divergence(fit, spec, field_by_patch, poses) -> dict:
    """How far each configuration's override sits from configuration (i).

    The ``null_proof`` discipline applied to the LADDER: a configuration
    that silently equals the baseline would report a tie that looks like
    a measurement.  Pure arithmetic on the override arrays -- no pixels,
    no detector -- so it can never be confused with the outcome.
    """
    out: dict[str, dict] = {}
    for name in CONFIGS[1:]:
        worst = 0.0
        total = 0.0
        count = 0
        touched = 0
        for ordinal in range(fit.n_payload):
            row = fit.rows[ordinal]
            patch_id = int(row.patch.patch_id)
            base = config_override(
                row, fit.residuals, spec, fit.base_is_residual,
                field_by_patch.get(patch_id), poses.get(patch_id),
                "committed")
            other = config_override(
                row, fit.residuals, spec, fit.base_is_residual,
                field_by_patch.get(patch_id), poses.get(patch_id), name)
            delta = np.abs(np.asarray(other) - np.asarray(base))
            worst = max(worst, float(delta.max()))
            total += float(delta.mean())
            count += 1
            touched += int(delta.max() > 0.0)
        out[name] = {
            "windows": count,
            "windows_moved": touched,
            "max_abs_delta_dots": worst,
            "mean_abs_delta_dots": total / max(1, count),
        }
    return out


def slot_ber(blocks_by_capture, spec, target, truth_bits) -> dict:
    """Hard-decision cell error against the printed truth, union view."""
    from holo.receive.evidence_blocks import tile_attempt_view

    from . import _swim_truth

    components = tuple(
        row for capture in blocks_by_capture
        for row in capture.get(target.address, ()))
    if not components:
        return {"observed": 0, "ber": None}
    payload_indices, truth = _swim_truth.tile_truth(
        truth_bits, target.address, target.plane, spec)
    entry = _swim_truth.hard_decision_ber(
        tile_attempt_view(components), payload_indices, truth,
        target.plane, ink_is_positive=True)
    return entry


__all__ = [
    "CONFIGS", "REFIT_CONFIGS", "N_PLANES", "arm_zero", "capture_blocks",
    "config_override", "field_common_content", "override_builder",
    "override_divergence", "slot_ber", "slot_verdict",
]
