"""Existence probe for the supplemental arms, with the arm-off control.

Renders the colour sim's real emitted page through a channel built to
carry one of the two arms' diseases (``uplift_fixture``), runs the
ordinary colour path to establish a certificate frontier, and then runs
THREE tiers over the identical residue and the identical frontier:

    off   the same region derivation with no arm      (the control)
    a3    per-window photometric maps
    a4b   sibling-conditioned marginals

The control is the point.  A tier that simply re-fits the region with a
frontier it did not have the first time gains certificates for a reason
that is NOT the arm — the ordinary receiver's own certificate feedback.
v1 registered exactly this and never ran it ("the discriminating test is
a u-lane pair differing only in the override, and it is owed, not done",
COLOR-UPLIFT-MEASUREMENTS §10.6).  Here off/a3/a4b differ in the override
and in nothing else, so the delta against ``off`` is the arm's.

Usage:

    PYTHONPATH=. env/bin/python measure/uplift_existence.py \
        <page000_gt.npy> [gain_sd] [absorption] [noise_sd] [y_scale]
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

from holo3.lib.geometry import TILE_CELLS
from dataclasses import replace as dc_replace  # noqa: E402

from holo3.plugins import (
    color_arms,
    color_conditioning as conditioning,
    color_model,
    color_photometry,
    color_region,
    color_region_head,
    tiles,
    uplift,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uplift_fixture as fixture  # noqa: E402

ARM_OFF = "off"
# A diagnostic tier that is NOT production and must never become one: the
# shipped A4b, with its per-stratum furniture pre-gate not consulted. It
# exists to separate two questions the shipped arm answers together —
# "does sibling conditioning convert a tile?" and "does the stratum earn
# its map on held-out FURNITURE?" — because v1 registered the second as a
# known limitation ("both gates measure furniture ... the named fix is
# P6") and this is where that limitation becomes visible.
ARM_A4B_UNGATED = "a4b*"
TIERS = (ARM_OFF, color_arms.UPLIFT_ARM_A3, color_arms.UPLIFT_ARM_A4B,
         ARM_A4B_UNGATED)


def fitted_dispersion(fits) -> tuple[float, float, int, int]:
    """PK4.1's raw statistic on the maps A3 actually accepted.

    Mass-weighted stdev of the fitted (shrunk) per-window gains, max over
    RGB, and the same for the offsets.  MEASURED ON PAPER
    (COLOR-UPLIFT-MEASUREMENTS §6.2/§6.3): gain spread 0.016-0.086,
    offset spread 0.012-0.041; the uplift target's own lane reads 0.0601.
    Reported so the synthetic channel can be PLACED against that window
    rather than tuned until the arm fires.
    """
    accepted = [fit for fit in fits if fit.window_map is not None]
    if len(accepted) < 2:
        return -1.0, -1.0, len(accepted), len(fits) - len(accepted)
    mass = np.asarray([fit.n_effective for fit in accepted], np.float64)
    shares = mass / mass.sum()
    gains = np.stack([fit.window_map.gains for fit in accepted])
    offsets = np.stack([fit.window_map.offsets for fit in accepted])

    def spread(values: np.ndarray) -> float:
        mean = shares @ values
        return float(np.sqrt(np.max(shares @ (values - mean) ** 2)))

    return (spread(gains), spread(offsets), len(accepted),
            len(fits) - len(accepted))


def crosstalk_mix(strength: float) -> tuple[tuple[float, ...], ...]:
    """A subtractive CMY->RGB matrix with one off-diagonal strength.

    The knob A4b's premise depends on: at strength 0 the channels are
    independent and a certified sibling carries NO information about the
    remaining component, so conditioning is provably vacuous however the
    rest of the channel is tuned.
    """
    return tuple(
        tuple(1.0 if row == column else strength for column in range(3))
        for row in range(3))


def ungated_stratum_map(detector, material, plane: int, pattern: int):
    """One stratum's calibration, fitted exactly as the arm fits it.

    ``color_conditioning._fit_stratum`` discards the map it fitted when
    the pre-gate refuses, so the ungated tier refits the same thing from
    the same material and the same floors.
    """
    chosen = np.flatnonzero(
        material.labelled[:, plane]
        & (material.pattern[:, plane] == pattern))
    labels = material.bits[chosen, plane].astype(np.int64)
    if (chosen.size < conditioning.CONDITIONED_MIN_LABELS
            or int(np.bincount(labels, minlength=2).min())
            < conditioning.CONDITIONED_MIN_CLASS_LABELS):
        return None
    rows = chosen[conditioning._stride_subsample(
        chosen.size, conditioning.CONDITIONED_MAX_LABELS)]
    fitted_labels = material.bits[rows, plane].astype(np.int64)
    if int(np.bincount(fitted_labels, minlength=2).min()) < 1:
        return None
    return color_model.fit_component_pava(
        conditioning._plane_llrs(material, detector.qda, plane, rows,
                                 conditioned=True),
        fitted_labels)


def ungated_a4b_stack(row, inputs):
    """The shipped A4b with its per-stratum pre-gate measured but not read.

    Every other part is the production path: the same populations, the
    same PAVA calibration per (plane, pattern) stratum, the same
    conditioned marginal at emission.  Only the ``passed`` verdict is
    ignored, so a stratum that the furniture gate refuses still carries
    its map.  DIAGNOSTIC ONLY.
    """
    selected, features, adopted, reason = (
        color_region_head.select_registration_arm(
            row, inputs.selection, inputs.base_tuple, inputs.corrected))
    if selected is None or selected.detector is None:
        return color_region_head.fit_region_stack(
            row, inputs.selection, inputs.row_tuple, inputs.base_tuple,
            inputs.corrected, inputs.emission_by_row,
            color_region_head.StackConfig())
    known_features = inputs.selection.gather(features)
    kinds = np.asarray(inputs.selection.kinds, np.int8)
    search = np.asarray(inputs.selection.search, np.bool_)
    furniture = np.flatnonzero(kinds >= 0)
    material = color_arms.concatenate_populations(
        color_arms.furniture_population(
            selected.model, inputs.selection, known_features,
            np.flatnonzero(kinds == 1)),
        color_arms.cert_cross_population(
            selected.model, inputs.row_tuple, features))
    del furniture, search
    grid = [[None] * conditioning.CONDITIONING_N_PATTERNS
            for _ in range(3)]
    for plane in range(3):
        if not selected.detector.supported_planes[plane]:
            continue
        for pattern in range(1, conditioning.CONDITIONING_N_PATTERNS):
            grid[plane][pattern] = ungated_stratum_map(
                selected.detector, material, plane, pattern)
    if not any(cell is not None for row_maps in grid for cell in row_maps):
        return color_region_head.fit_region_stack(
            row, inputs.selection, inputs.row_tuple, inputs.base_tuple,
            inputs.corrected, inputs.emission_by_row,
            color_region_head.StackConfig())
    head = conditioning.Cmy8ConditionedHead(
        tuple(tuple(row_maps) for row_maps in grid))
    selected = dc_replace(selected, conditioned=head)
    return color_region_head.finish_region_stack(
        row, inputs.selection, inputs.row_tuple, selected, features,
        adopted, reason, inputs.emission_by_row,
        color_region_head.StackConfig())


def attempt_residue(row, geometry, order_of, transient, targets, stage):
    certified: dict = {}
    for ty, tx, pending in targets:
        cut = uplift.uplift_cut(row, geometry, order_of, transient, "cap", 0,
                                0, ty, tx)
        if cut is None:
            continue
        for stream_id in pending:
            outcome = tiles.attempt_tile(row, geometry, (cut,), stream_id,
                                         stage)
            if outcome.certificate is not None:
                certified[(0, ty, tx, stream_id)] = outcome.certificate
    return certified


def run_tier(row, geometry, windows, planes, frontier, targets, arm):
    inputs = color_region.build_region_inputs(
        row, geometry, windows, (), planes, frontier, "cap", 0)
    verdict = None
    if arm == ARM_OFF:
        stack = color_region_head.fit_region_stack(
            row, inputs.selection, inputs.row_tuple, inputs.base_tuple,
            inputs.corrected, inputs.emission_by_row,
            color_region_head.StackConfig())
    elif arm == ARM_A4B_UNGATED:
        stack = ungated_a4b_stack(row, inputs)
    else:
        stack, verdict = color_arms.fit_region_stack_arm(
            row, inputs, color_region_head.StackConfig(), arm)
    if stack.selected is None:
        return {}, verdict, inputs, stack
    order_of = {int(window.patch_ordinal): (window.window_id[3], 0)
                for window in windows}
    transient = uplift._transient_rows(inputs, stack)
    stage = (tiles.STAGE_UPLIFT_A3 if arm != color_arms.UPLIFT_ARM_A4B
             else tiles.STAGE_UPLIFT_A4B)
    return (attempt_residue(row, geometry, order_of, transient, targets,
                            stage),
            verdict, inputs, stack)


def main() -> int:
    gt_path = Path(sys.argv[1])
    channel = fixture.Channel()
    if len(sys.argv) > 2:
        channel = replace(channel, gain_sd=float(sys.argv[2]))
    if len(sys.argv) > 3:
        channel = replace(channel, absorption=float(sys.argv[3]))
    if len(sys.argv) > 4:
        channel = replace(channel, noise_sd=float(sys.argv[4]))
    if len(sys.argv) > 5:
        channel = replace(
            channel, plane_scale=(1.0, 1.0, float(sys.argv[5])))
    if len(sys.argv) > 6:
        channel = replace(channel, plane_jitter_sd=float(sys.argv[6]))
    if len(sys.argv) > 7:
        channel = replace(channel, mix=crosstalk_mix(float(sys.argv[7])))
    row, geometry = fixture.format_row_and_geometry()
    bits = fixture.page_bits(gt_path, row)
    gains, offsets = fixture.window_gains(channel)
    image = fixture.render(bits, channel, gains, offsets)
    windows = fixture.region_windows(row, channel)
    all_streams = tuple(stream.stream_id for stream in row.streams)
    every_tile = tuple(
        (ty, tx, all_streams)
        for ty in range(channel.tiles_side)
        for tx in range(channel.tiles_side))
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        frontier, _v, _i, _s = run_tier(
            row, geometry, windows, planes, {}, every_tile, ARM_OFF)
        residue = tuple(
            entry for entry in (
                (ty, tx, tuple(name for name in all_streams
                               if (0, ty, tx, name) not in frontier))
                for ty, tx, _s in every_tile)
            if entry[2])
        tiers = {}
        for arm in TIERS:
            tiers[arm] = run_tier(row, geometry, windows, planes,
                                  dict(frontier), residue, arm)
    everything = dict(frontier)
    for arm in TIERS:
        everything.update(tiers[arm][0])
    wrong = 0
    for ty in range(channel.tiles_side):
        for tx in range(channel.tiles_side):
            wrong += fixture.audit_certificate(
                row, geometry, everything, bits, 0, ty, tx)
    stack_off = tiers[ARM_OFF][3]
    maps = None
    if stack_off.selected is not None:
        maps = color_photometry.fit_window_photometry(
            stack_off.selected.model, tiers[ARM_OFF][2].selection,
            tiers[ARM_OFF][2].row_tuple, stack_off.features,
            color_photometry.WindowPhotometryConfig())
    gain_spread, offset_spread, accepted, refused = (
        fitted_dispersion(maps.fits) if maps is not None
        else (-1.0, -1.0, 0, 0))
    n_streams = len(row.streams)
    total = channel.tiles_side * channel.tiles_side * n_streams
    offered = sum(len(entry[2]) for entry in residue)
    print(f"channel gain_sd={channel.gain_sd} offset_sd={channel.offset_sd} "
          f"absorption={channel.absorption} noise_sd={channel.noise_sd} "
          f"plane_scale={channel.plane_scale}")
    print(f"tiles {channel.tiles_side}x{channel.tiles_side} "
          f"windows {channel.windows_side}x{channel.windows_side} "
          f"streams/tile {n_streams} cells/tile {TILE_CELLS}x{TILE_CELLS}")
    print(f"first pass certified    {len(frontier)}/{total}")
    print(f"residue offered         {offered}")
    base = len(tiers[ARM_OFF][0])
    for arm in TIERS:
        gained = len(tiers[arm][0])
        delta = "" if arm == ARM_OFF else f"   arm delta {gained - base:+d}"
        print(f"  tier {arm:<4} gained    {gained}/{offered}{delta}")
    print(f"A3 maps accepted/refused {accepted}/{refused}")
    print(f"fitted gain spread      {gain_spread:.4f}  "
          f"(paper 0.016-0.086, uplift lane 0.0601)")
    print(f"fitted offset spread    {offset_spread:.4f}  "
          f"(paper 0.012-0.041)")
    print(f"wrong certificate bits  {wrong}")
    for arm in TIERS:
        verdict = tiers[arm][1]
        if verdict is None:
            continue
        print(f"{arm}: reason={verdict.reason} adopted={verdict.adopted} "
              f"maps={verdict.accepted_maps}/{verdict.refused_maps} "
              f"strata={verdict.strata_adopted} "
              f"arity1={verdict.cells_arity1} arity2={verdict.cells_arity2} "
              f"cert={verdict.cert_cells} masked={verdict.masked_cells}")
        for stratum, delta in zip(verdict.strata, verdict.strata_deltas):
            plane, pattern, reason, n_cert, n_masked = stratum
            print(f"    plane {plane} pattern {pattern} {reason:<22} "
                  f"cert={n_cert:<7} masked={n_masked:<6} "
                  f"total={delta[2]:+.4f} word={delta[3]:+.4f} "
                  f"dust={delta[4]:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
