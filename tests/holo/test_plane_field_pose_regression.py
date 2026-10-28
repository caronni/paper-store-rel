"""The probe-density flip's POSE regression, and the residual itself.

The 2026-08-23 ruling makes ``TILE_FRAGMENT`` the shipped probe density
(INDEPENDENT-PLANES §2.9c): ONE measurement per (certified tile,
covering window), serving the per-plane FIELD and the plane-common POSE
residual from the same correlation.  The field half ties (§2.9b); the
pose half is the reason, and a pose residual that is measured but wrong
would be worse than none.  So the flip owes three layers of regression,
and this module is the second and third of them.

1. **Dial OFF is untouched.**  A ``None`` config constructs no builder,
   so the density is not consulted at all — the existing byte-identity
   pins carry that claim and none of them moved:
   ``test_color_field.test_the_default_decode_is_unchanged_by_this_arm``
   (certificate digest + close sha), ``test_payload_nulls``,
   ``test_color_field_arm`` and the seven-coding real-payload gate net.
2. **Dial ON commits the same geometry at either density.**  The probe
   pass runs DOWNSTREAM of placement and the plane-common residual is
   reported, never applied, so a density change must not move one
   committed pose or one placement record.  Pinned three ways here: the
   pass writes nothing it was handed; the one production lane that turns
   the dial on (``uF``) commits no pose and no replacement address at
   either density while its FIELD EVIDENCE demonstrably differs; and a
   whole dial-ON decode lands on byte-identical ``PoseRecord`` rows.
3. **The residual recovers what it claims.**  Synthetic captures with a
   KNOWN plane-common shift, under every ``rot_k`` and through
   label-only, mixed and clipped windows, must report that shift in the
   window's LOCAL frame with the right sign — and a capture whose planes
   are displaced against each OTHER (C ``+d``, M ``-d``, Y 0) must
   report no plane-common shift at all, because there is none.

The synthetic captures are the ``_color_stack_fixtures`` forward model
with its per-plane ``offset_xy`` (scan pixels; ``PX_PER_DOT`` = 2 of
them per print dot) used as the injected truth, and hand-built windows
whose pose carries the rotation exactly the way a placed window's does.
"""
from __future__ import annotations

import hashlib
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

import _color_stack_fixtures as stack_fixtures
import test_color_field as w2
import test_color_uplift_lanes as uplift_fixtures
import test_receive_color_refine as refine_fixtures
from holo.core import channel
from holo.format.registry import get_format_row
from holo.gen.emit import emit_volume
from holo.receive._payload_sampling import rotated_points
from holo.receive.color_field import (
    UPLIFT_ARM_FIELD,
    PlaneFieldBuilder,
    PlaneFieldConfig,
    ProbeMode,
    ProbeWindow,
)
from holo.receive.color_projection import CertifiedColorProjection
from holo.receive.placement.model import (
    AffinePose,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)
from holo.receive.production_color import ProductionColorPayload
from holo.receive.scan import open_capture

ROW = "c3-cmy8-p120-v0@2240x1536"
DENSITIES = (ProbeMode.BLOCK_PER_BIN, ProbeMode.TILE_FRAGMENT)

#: The injected plane-COMMON capture shift, in scanner pixels ``(x, y)``.
#: Two scanner pixels per print dot, so this is ``(0.7, -0.5)`` print
#: dots — inside the +/-2.5-dot NCC search and off both axes' zero, so a
#: swapped axis or a dropped sign cannot pass.
COMMON_SHIFT_PX_XY = (1.4, -1.0)
#: The per-plane-only displacement: C one way, M the other, Y still.
#: Its three-plane mean is exactly zero, which is the claim.
PLANE_SHIFT_PX = 1.2

#: ``local -> page`` linear part of one window's ``rot_k``, in ``(y, x)``
#: order.  Written out rather than taken from ``_rotate_delta_xy``, which
#: is the production function under regression here: an independent
#: statement of the same rotation is the whole point of the check.
ROTATIONS = {
    0: np.array([[1.0, 0.0], [0.0, 1.0]]),
    1: np.array([[0.0, -1.0], [1.0, 0.0]]),
    2: np.array([[-1.0, 0.0], [0.0, -1.0]]),
    3: np.array([[0.0, 1.0], [-1.0, 0.0]]),
}
#: The one tile these synthetic windows certify: interior, so a 64-cell
#: template plus its search margin stays inside the rendered sheet.
CERTIFIED_TILE = (1, 1)


# --------------------------------------------------------------- fixtures
@lru_cache(maxsize=None)
def _shifted_capture(offsets_px_xy: tuple[tuple[float, float], ...]):
    """One clean render of the 3x3 tile field at chosen plane offsets."""
    spec = get_format_row(ROW)
    pitch_px = stack_fixtures.PX_PER_DOT * spec.cell_dots
    field = stack_fixtures._tile_field(spec, stack_fixtures.TILES_YX)
    rgb = stack_fixtures._render_with(
        field, pitch_px, offsets_px_xy,
        stack_fixtures._CLEAN_BLUR_SIGMA, stack_fixtures._CLEAN_NOISE_STD)
    raster = open_capture(rgb, 600.0 * stack_fixtures.PX_PER_DOT)
    return spec, field, raster, float(pitch_px)


def _projection_source(field: np.ndarray, certified: frozenset):
    """Exact printed cells for the certified tiles, nothing else."""
    bits = channel.states_to_planes(field).astype(np.uint8)

    def projection_for(address):
        _page, tile_y, tile_x = address
        if (tile_y, tile_x) not in certified:
            return None
        block = bits[tile_y * 64:(tile_y + 1) * 64,
                     tile_x * 64:(tile_x + 1) * 64]
        if block.shape[:2] != (64, 64):
            return None
        return CertifiedColorProjection(
            address, block, np.ones((64, 64, 3), np.bool_), ())

    return projection_for


def _window(
    pitch_px: float,
    patch_id: int,
    origin_cells_yx: tuple[int, int],
    page_shape_cells: tuple[int, int],
    rot_k: int,
) -> ProbeWindow:
    """A placed window over a PAGE rectangle, at a chosen orientation.

    The pose is built so ``pose.points(local)`` is the scan centre of the
    page cell that local cell maps to — which is the invariant a real
    placement satisfies and the only thing the probe pass depends on.
    ``rot_k`` therefore lives in the pose's Jacobian, not in a rotated
    raster: the capture stays the one the offsets were rendered into.
    """
    local_shape = (
        (page_shape_cells[1], page_shape_cells[0]) if rot_k % 2
        else page_shape_cells)
    local = stack_fixtures._grid(local_shape).astype(np.int64)
    page_relative = rotated_points(local, local_shape, rot_k)
    origin = np.asarray(origin_cells_yx, np.int64)
    page = page_relative + origin
    matrix = ROTATIONS[rot_k] * pitch_px
    translation = page_relative[0] - ROTATIONS[rot_k] @ local[0]
    pose = AffinePose(
        tuple((translation + origin) * pitch_px + (pitch_px - 1.0) / 2.0),
        tuple(map(tuple, matrix)), (0.5, 0.5), pitch_px, 0.0)
    segment = PoseSegment(
        PoseWindow(patch_id, 0, tuple(int(v) for v in origin), local_shape),
        pose, local.shape[0], 1.0, (pitch_px, pitch_px), 0.0)
    placed = PlacedSegment(
        segment, tuple(int(v) for v in origin), rot_k, local.astype(np.int32))
    return ProbeWindow(
        PlacedPatch(
            patch_id, 0, 0, "pose-regression", stack_fixtures._candidate(0),
            (), placed, (), False, page.astype(np.int32)),
        0, local, page)


def _expected_local_dots(page_dots_xy: tuple[float, float], rot_k: int):
    """The page-frame shift as the window's LOCAL ``(dx, dy)``."""
    page_dyx = np.asarray((page_dots_xy[1], page_dots_xy[0]), np.float64)
    local_dyx = ROTATIONS[rot_k].T @ page_dyx
    return (float(local_dyx[1]), float(local_dyx[0]))


#: The three window geometries the probe pass must treat alike (§4.G):
#: a certified-complete (label-only) window, a MIXED window whose other
#: tile is uncertified, and a mixed window that also CLIPS the certified
#: tile so the fragment is a partial rectangle.
WINDOW_KINDS = {
    "label-only": ((64, 64), (64, 64)),
    "mixed": ((64, 0), (64, 128)),
    "mixed-clipped": ((64, 96), (64, 96)),
}


# ------------------------------------------ layer 2: the pass writes none
def _capture_digest(raster) -> str:
    native = np.ascontiguousarray(
        np.asarray(raster.crop_native(0, raster.shape[0], 0, raster.shape[1])))
    return hashlib.sha256(native.tobytes()).hexdigest()


def _window_digest(window: ProbeWindow) -> str:
    patch = window.patch
    pose = patch.segment.segment.pose
    return hashlib.sha256("|".join((
        repr(pose.origin_yx), repr(pose.jacobian_yx), repr(pose.phase_yx),
        repr(pose.pitch_px), repr(pose.angle_deg),
        repr(patch.segment.rot_k), repr(patch.segment.page_origin_yx),
        np.asarray(patch.segment.audited_cells_yx).tobytes().hex(),
        np.asarray(patch.page_cells_yx).tobytes().hex(),
        np.asarray(window.local_cells_yx).tobytes().hex(),
        np.asarray(window.page_cells_yx).tobytes().hex(),
    )).encode("ascii")).hexdigest()


@pytest.mark.parametrize("mode", DENSITIES)
def test_the_probe_pass_writes_nothing_it_was_given(mode: ProbeMode) -> None:
    """The structural half of layer 2: poses and pixels are INPUTS.

    The pass reads a committed pose to rectify a template and reads the
    capture through it.  Neither is its to change — at any density — so
    both are digested before and after the pass and must match.
    """
    spec, field, raster, pitch_px = _shifted_capture(
        (COMMON_SHIFT_PX_XY,) * 3)
    windows = tuple(
        _window(pitch_px, ordinal, origin, shape, ordinal % 4)
        for ordinal, (origin, shape) in enumerate(WINDOW_KINDS.values()))
    before = ([_window_digest(row) for row in windows],
              _capture_digest(raster))

    builder = PlaneFieldBuilder(spec, PlaneFieldConfig(probe_mode=mode))
    added = builder.add_certified_probes(
        raster, windows,
        _projection_source(field, frozenset({CERTIFIED_TILE})))
    assert added > 0, "the check is vacuous unless the pass actually ran"

    assert ([_window_digest(row) for row in windows],
            _capture_digest(raster)) == before


# ------------------------------------------- layer 2: the uF lane commits
def _uplift_details(events) -> dict:
    rows = [details for name, details in events
            if name == "payload.plane_fields"]
    assert len(rows) == 1, "one field report per capture collection"
    return refine_fixtures._detail_map(rows[0])


def _run_density(mode: ProbeMode):
    spec, raster, plan, region_record, poses = (
        uplift_fixtures._cmy7_uplift_fixture())
    events: list = []
    _context, output = uplift_fixtures._run_uplift(
        spec, raster, plan, region_record, poses, UPLIFT_ARM_FIELD, events,
        refine_fixtures.LANE,
        processor=ProductionColorPayload(
            plane_fields=PlaneFieldConfig(probe_mode=mode)))
    return poses, output, events, _uplift_details(events)


def test_a_density_change_moves_evidence_and_not_geometry() -> None:
    """The lane-level half of layer 2, on a lane with REAL probes.

    ``uF`` is the one production lane that turns the dial on, and its
    fixture has four of six tiles certified, so the probe pass has tier-i
    evidence at either density.  The evidence it produces DIFFERS — which
    is what makes the geometry half non-vacuous — and the geometry does
    not: no replacement address, no pose-refinement event, no final
    address, and the committed poses the lane was handed come back
    untouched.
    """
    runs = {mode: _run_density(mode) for mode in DENSITIES}

    for mode, (poses, output, events, details) in runs.items():
        assert details["plane_fields.probe_sites"] > 0, mode
        assert details["plane_fields.probes"] > 0, mode
        # A supplemental lane refines no pose and mints no replacement.
        assert output.replacement_address is None, mode
        names = {name for name, _details in events}
        assert "pose_refine.window_progress" not in names, mode
        assert "address.final" not in names, mode
        assert poses == runs[ProbeMode.BLOCK_PER_BIN][0], mode

    block = runs[ProbeMode.BLOCK_PER_BIN][3]
    fragment = runs[ProbeMode.TILE_FRAGMENT][3]
    # THE EVIDENCE MOVED.  Same sites (one per certified tile per covering
    # window at ``bins_per_tile = 1``), same probe count, different
    # template — and the number the ruling is about is the LAST one: the
    # site-to-site spread of the plane-common residual collapses once the
    # template is the covered part of a tile rather than a 5x5 block,
    # which is E5b's finding (0.264 -> 0.187 dots on sheet I) reproduced
    # on a fixture whose truth is known.
    assert block["plane_fields.probe_sites"] == fragment[
        "plane_fields.probe_sites"]
    assert (block["plane_fields.rms_dots.c"],
            block["plane_fields.rms_dots.m"],
            block["plane_fields.rms_dots.y"]) != (
        fragment["plane_fields.rms_dots.c"],
        fragment["plane_fields.rms_dots.m"],
        fragment["plane_fields.rms_dots.y"])
    assert fragment["plane_fields.pose_residual_spread_dots"] < 0.2 * block[
        "plane_fields.pose_residual_spread_dots"]


# --------------------------------------- layer 2: the whole decode commits
def _pose_digest(state) -> str:
    return hashlib.sha256(
        "\n".join(repr(row) for row in state.poses).encode("ascii")
    ).hexdigest()


def _placement_digest(state) -> str:
    return hashlib.sha256("\n".join(
        [repr(row) for row in state.regions]
        + [repr(row) for row in state.proposals]
        + [repr(row) for row in state.losers]
        + [repr(row) for row in state.parked]).encode("ascii")).hexdigest()


def test_a_dial_on_decode_commits_the_same_poses_at_either_density(
    tmp_path: Path,
) -> None:
    """The decode-level half of layer 2: real ``PoseRecord`` rows.

    The W2 warped pooled fixture through the whole production pipeline
    with the dial ON, once per density.  What is pinned is that the dial
    cannot reach placement AT ALL: identical committed poses, identical
    placement ledger, identical certificates, identical close.

    Honest about its own reach: this fixture's single colour lane opens
    with an EMPTY certificate ledger, so the probe pass has nothing to
    probe here and the two densities collect the same anchor-only
    evidence — the probe count is asserted to be zero rather than
    assumed away.  The non-vacuous "evidence differs, geometry does not"
    pin is ``test_a_density_change_moves_evidence_and_not_geometry``
    above; this one is the whole-pipeline plumbing guard behind it.
    """
    spec = w2._pooled_spec()
    payload = w2._pooled_payload()
    volume = emit_volume(spec, payload, w2._Q, tmp_path / "volume")
    raster = w2._raster(spec, w2._warp_plane(
        w2._coverage(spec, volume.pages[0].gt_path), w2.WARP_PLANE))

    digests = {}
    for mode in DENSITIES:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result, events = w2._decode(
                spec, raster, tmp_path / f"{mode.value}.receive.json",
                PlaneFieldConfig(probe_mode=mode))
        reports = [row for row in events if row.name == "payload.plane_fields"]
        assert reports, "the dial-on lane must report its field"
        details = {row.name: row.value for row in reports[-1].details}
        assert details["plane_fields.probe_sites"] == 0, (
            "this fixture's colour lane has no certified tile yet; if that "
            "changed, this test is now comparing two different fields")
        digests[mode] = (
            _pose_digest(result.state),
            _placement_digest(result.state),
            w2._certificate_digest(result.state),
            result.state.close.payload_sha256,
            len(result.state.poses),
        )
        assert result.payload == payload

    assert digests[ProbeMode.BLOCK_PER_BIN][4] > 0
    assert digests[ProbeMode.BLOCK_PER_BIN] == digests[
        ProbeMode.TILE_FRAGMENT]


# ------------------------------ layer 3: the residual recovers the shift
@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
@pytest.mark.parametrize("kind", tuple(WINDOW_KINDS))
def test_the_plane_common_residual_recovers_a_known_capture_shift(
    rot_k: int, kind: str,
) -> None:
    """A known plane-common shift, in the window's own LOCAL frame.

    Every plane of the capture is displaced by the SAME
    ``COMMON_SHIFT_PX_XY``, which is a pose error and not a registration
    difference, so the whole of it must land in the plane-common
    residual.  The expected value is the page shift carried into the
    window's local frame by an independently written rotation, so a
    ``rot_k`` handled backwards fails on three of four orientations and a
    swapped axis fails on all four.
    """
    spec, field, raster, pitch_px = _shifted_capture(
        (COMMON_SHIFT_PX_XY,) * 3)
    origin, shape = WINDOW_KINDS[kind]
    window = _window(pitch_px, 3, origin, shape, rot_k)
    builder = PlaneFieldBuilder(spec, PlaneFieldConfig())
    builder.add_certified_probes(
        raster, (window,),
        _projection_source(field, frozenset({CERTIFIED_TILE})))
    report = builder.report()

    assert report.n_probe_sites == 1, "one (certified tile, window) pair"
    assert report.n_probes == 3, "all three planes carry the same shift"
    assert len(report.window_pose_residuals) == 1
    measured = report.window_pose_residuals[0]
    assert measured.patch_id == 3 and measured.page == 0
    expected = _expected_local_dots(
        (COMMON_SHIFT_PX_XY[0] / stack_fixtures.PX_PER_DOT,
         COMMON_SHIFT_PX_XY[1] / stack_fixtures.PX_PER_DOT), rot_k)
    assert measured.median_dx_dots == pytest.approx(expected[0], abs=0.05)
    assert measured.median_dy_dots == pytest.approx(expected[1], abs=0.05)


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_a_per_plane_displacement_leaves_no_plane_common_residual(
    rot_k: int,
) -> None:
    """C ``+d``, M ``-d``, Y ``0``: a field disease, not a pose error.

    The restraint half of layer 3, and the one that would catch a
    residual built from a varying subset of planes: the three per-plane
    measurements are large and cancel, so the plane-common part is zero
    while the FIELD carries the whole displacement.
    """
    delta = PLANE_SHIFT_PX
    spec, field, raster, pitch_px = _shifted_capture(
        ((delta, delta), (-delta, -delta), (0.0, 0.0)))
    window = _window(pitch_px, 5, *WINDOW_KINDS["label-only"], rot_k)
    builder = PlaneFieldBuilder(spec, PlaneFieldConfig())
    builder.add_certified_probes(
        raster, (window,),
        _projection_source(field, frozenset({CERTIFIED_TILE})))
    builder.solve()
    report = builder.report()

    assert report.n_probes == 3
    assert max(report.pose_residual_magnitudes()) < 0.02

    # ...and it is not zero because nothing was measured: the field holds
    # the injected per-plane displacement, in the PAGE frame it pools in.
    truth = delta / stack_fixtures.PX_PER_DOT
    deltas = [
        builder._field.lookup_tile_index(0, *CERTIFIED_TILE)[plane]
        for plane in range(3)]
    for plane, sign in enumerate((1.0, -1.0, 0.0)):
        assert deltas[plane].covered
        for axis in (0, 1):
            # The field's shrinkage prior pulls a single sample in, so
            # the bar is direction and order of magnitude, not the digit.
            assert deltas[plane].delta_dots_xy[axis] == pytest.approx(
                sign * truth, abs=0.15)
