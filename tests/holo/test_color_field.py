"""PLANE-FIELDS W2/W4: the field at the colour registration seam.

Three claims, in the order they matter.

1. **THE NULL PROOF.**  The dial is DEFAULT OFF, and off means *nothing
   happened*: the 10x10 pooled colour fixture decodes to the SAME
   certificate set and the SAME close payload it decoded to before this
   arm existed (digest pinned from the pre-change tree at 9f9c569), and
   no ``payload.plane_fields`` event is emitted at all.
2. **The probe pass measures what it claims** (W4).  Against a
   certificate's own re-encoded printed cells, the rectified NCC
   recovers the ``cmy8-residual`` fixture's injected per-plane
   displacement to a few hundredths of a print dot — and reads zero on
   its clean twin, which is the restraint half of the same claim.
3. **The dial earns its slot on a channel the residual cannot model.**
   ``PlaneResidual`` is a constant plus a term linear in page-y; a
   sinusoid in page-x is outside its basis entirely.  With one plane
   warped that way the field recovers the whole loss.

The plane chosen for claim 3 is M, deliberately.  Words are W/CM, so C
and M carry word anchors while Y is dust-only — and MEASURED on this
fixture the Y anchors are noise (sd 0.94 dots, correlation +0.02 with
the injected truth), which is the PK6/A2 measured negative reproducing
itself exactly.  A field arm fed anchors alone therefore cannot help Y;
that is what W4's certified-tile probes are for, and claim 2 is where
they are pinned.
"""
from __future__ import annotations

import hashlib
import os
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from _color_stack_fixtures import build_fixture
from holo.core import channel
from holo.format.descriptor import CODINGS, FormatSpec
from holo.gen.emit import emit_volume
from holo.qualification.color_synthetic import render_color_scan
from holo.receive._payload_sampling import _window_rows
from holo.receive.color_anchoring import RegistrationAnchors, _Rows
from holo.receive.color_field import (
    PLANE_NAMES,
    PlaneFieldBuilder,
    PlaneFieldConfig,
    ProbeMode,
    ProbeWindow,
    _rotate_delta_xy,
    field_corrected_features,
)
from holo.receive.color_projection import CertifiedColorProjection
from holo.receive.color_registration import PlaneResidual
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.plane_fields import FieldEvidence
from holo.receive.production import production_pipeline
from holo.receive.production_color import ProductionColorPayload
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput

# ---------------------------------------------------------------- pins
# Captured on the PRE-CHANGE tree (worktree plane-fields at 9f9c569) by
# decoding the fixture below through the unmodified production pipeline.
# A mismatch here is a behaviour change on the DEFAULT path, which this
# arm is not allowed to have.
NULL_CERT_DIGEST = (
    "113ca9a5d7666b3858308e836286c7166bc87590421651abd92e2299584eef1d")
NULL_CLOSE_SHA = (
    "18afd73a28b53df4567a293877d98027fd4a0565a988c711412a1b6d86224c71")
NULL_CERTIFICATES = 300

# The ``cmy8-residual`` fixture's injected plane displacement, converted
# from its scanner pixels to the print dots the field stores in
# (``_color_stack_fixtures.PX_PER_DOT`` = 2).
RESIDUAL_TRUTH_DOTS_XY = ((0.0, 0.0), (0.7, -0.5), (-0.6, 0.6))

_Q = 0.35
_MEDIA_MM = (82.0, 82.0)
_CODING = "c3-cmy8-p120-v1"
# One cycle of x-sinusoid at 0.45 cell peak: unmodelable by the residual
# (constant + linear in page-y), comfortably inside the anchor NCC's
# +/-2.5-dot search, and under the half-cell unwrap limit.
WARP_AMPLITUDE_DOTS = 1.35
WARP_CYCLES = 1.0
WARP_PLANE = 1                       # M -- the plane words actually ink


# ------------------------------------------------------------- helpers
def _pooled_spec() -> FormatSpec:
    spec = FormatSpec(CODINGS[_CODING], "dead-plane-q", _MEDIA_MM, 0.0)
    if spec.layout.tiles_yx != (10, 10):
        raise AssertionError(
            f"pooled colour fixture geometry drifted: {spec.layout.tiles_yx}")
    return spec


def _pooled_payload() -> bytes:
    return hashlib.shake_256(
        b"holo/dead-plane-gate/" + _CODING.encode("ascii")).digest(20_000)


def _coverage(spec: FormatSpec, gt_path: Path) -> np.ndarray:
    packed = np.load(gt_path, allow_pickle=False)
    field_w = spec.layout.field_dots_yx[1]
    return np.stack([
        np.unpackbits(packed[plane], axis=1, count=field_w,
                      bitorder="big").astype(np.float64)
        for plane in range(3)
    ], axis=-1)


def _warp_plane(coverage: np.ndarray, plane: int) -> np.ndarray:
    """Sinusoidal x displacement of ONE plane; coverage is at dot pitch."""
    height, width, _ = coverage.shape
    ys, xs = np.mgrid[0:height, 0:width]
    shift_dots = WARP_AMPLITUDE_DOTS * np.sin(
        2.0 * np.pi * WARP_CYCLES * xs / width)
    warped = ndimage.map_coordinates(
        coverage[..., plane], [ys.ravel(), (xs - shift_dots).ravel()],
        order=1, mode="nearest").reshape(height, width)
    out = coverage.copy()
    out[..., plane] = warped
    return out


def _raster(spec: FormatSpec, coverage: np.ndarray) -> np.ndarray:
    page_x, page_y = spec.layout.page_dots_xy
    origin_y, origin_x = spec.layout.origin_dots_yx
    field_h, field_w = spec.layout.field_dots_yx
    canvas = np.zeros((page_y, page_x, 3), np.float64)
    canvas[origin_y:origin_y + field_h,
           origin_x:origin_x + field_w] = coverage
    border = 60
    padded = np.zeros(
        (page_y + 2 * border, page_x + 2 * border, 3), np.float64)
    padded[border:-border, border:-border] = canvas
    source = np.repeat(np.repeat(padded, 2, axis=0), 2, axis=1)
    rgb = np.clip(np.asarray(render_color_scan(source).rgb), 0.0, 1.0)
    return np.ascontiguousarray(np.round(rgb * 255.0).astype(np.uint8))


def _decode(spec, raster, state_path, config):
    """Run the production pipeline, optionally with the dial on."""
    request = ReceiveRequest(
        spec, (CaptureInput(raster, 1200.0),),
        state_path=state_path, page_hypotheses=(0,))
    pipeline = production_pipeline(request)
    if config is not None:
        pipeline = replace(pipeline, lanes=replace(
            pipeline.lanes,
            payload=ProductionColorPayload(plane_fields=config)))
    events: list = []

    def observer(event) -> None:
        events.append(event)

    observer.wants_snapshots = True   # type: ignore[attr-defined]
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        result = run_receive(request, pipeline=pipeline, observer=observer)
    return result, events


def _certificate_digest(state) -> str:
    return hashlib.sha256("\n".join(sorted(
        f"{row.page}/{row.tile_yx[0]}/{row.tile_yx[1]}/{row.stream_id}"
        for row in state.certificates)).encode("ascii")).hexdigest()


def _projection_source(field: np.ndarray):
    """Serve exact printed cells per tile from a fixture's truth field."""
    bits = channel.states_to_planes(field).astype(np.uint8)

    def projection_for(address):
        _page, tile_y, tile_x = address
        block = bits[tile_y * 64:(tile_y + 1) * 64,
                     tile_x * 64:(tile_x + 1) * 64]
        if block.shape[:2] != (64, 64):
            return None
        return CertifiedColorProjection(
            address, block, np.ones((64, 64, 3), np.bool_), ())

    return projection_for


def _probe_windows(fixture) -> tuple[ProbeWindow, ...]:
    return tuple(
        ProbeWindow(patch, 0, rows.local_cells_yx, rows.page_cells_yx)
        for patch, rows in (
            (patch, _window_rows(patch, fixture.spec))
            for patch in fixture.address.placements)
    )


# ------------------------------------------------------------ W1 seams
def test_the_local_page_rotation_round_trips_every_orientation() -> None:
    """The frame crossing must be exact, or pooling means nothing."""
    rows = np.asarray([[0.7, -0.3], [-1.25, 2.0]], np.float64)
    for rot_k in (0, 1, 2, 3):
        page = _rotate_delta_xy(rows, rot_k, inverse=False)
        back = _rotate_delta_xy(page, rot_k, inverse=True)
        assert np.allclose(back, rows)
        # Rotation is an isometry: magnitudes survive the crossing.
        assert np.allclose(np.hypot(*page.T), np.hypot(*rows.T))
    assert np.array_equal(_rotate_delta_xy(rows, 0, inverse=False), rows)
    # rot_k 1 sends local (dy, dx) to page (-dx, dy), i.e. (dx, dy) rows
    # become (dy, -dx).
    assert np.allclose(
        _rotate_delta_xy(np.asarray([[1.0, 0.0]]), 1, inverse=False),
        [[0.0, -1.0]])
    with pytest.raises(ValueError, match="rot_k"):
        _rotate_delta_xy(rows, 4, inverse=False)


def test_kept_anchors_become_evidence_in_every_bucket() -> None:
    """F1 step 1: keep the array ``color_payload`` used to discard."""
    fixture = build_fixture("cmy8-residual")
    rows = tuple(_window_rows(patch, fixture.spec)
                 for patch in fixture.address.placements)

    class _Stub:
        def __init__(self, patch) -> None:
            self.patch = patch

    stubs = tuple(_Stub(patch) for patch in fixture.address.placements)
    anchors = []
    for plane in range(3):
        cells = np.concatenate([row.page_cells_yx[:8] for row in rows])
        anchors.append(RegistrationAnchors(
            page=np.zeros(cells.shape[0], np.int64),
            cell_yx=cells.astype(np.int64),
            window_index=np.repeat(
                np.arange(len(rows), dtype=np.int64), 8),
            offset_dots_xy=np.full(
                (cells.shape[0], 2), 0.5 * (plane + 1), np.float64),
            quality=np.full(cells.shape[0], 0.8),
            bucket=np.tile(
                np.asarray([0, 1, 2, 0, 1, 2, 0, 1], np.int8), len(rows)),
        ))
    builder = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    added = builder.add_anchors(stubs, tuple(anchors))
    assert added == 3 * 8 * len(rows)
    builder.solve()
    report = builder.report()
    assert set(report.samples_by_source) == {"word", "dust", "certified"}
    assert report.n_samples == added
    # Each plane's constant offset is recovered, plane by plane.
    for plane in range(3):
        affine = builder._field.lookup_cells(
            0, (32.0, 32.0))[plane]
        assert affine.covered
        assert affine.delta_dots_xy[0] == pytest.approx(
            0.5 * (plane + 1), abs=0.05)


def test_a_low_quality_anchor_is_not_evidence() -> None:
    """The weight IS the NCC quality, and the floor is a real gate."""
    fixture = build_fixture("cmy8-clean")

    class _Stub:
        def __init__(self, patch) -> None:
            self.patch = patch

    stub = _Stub(fixture.address.placements[0])
    anchors = tuple(
        RegistrationAnchors(
            page=np.zeros(2, np.int64),
            cell_yx=np.asarray([[10, 10], [20, 20]], np.int64),
            window_index=np.zeros(2, np.int64),
            offset_dots_xy=np.asarray([[0.4, 0.4], [0.4, 0.4]], np.float64),
            quality=np.asarray([0.9, 0.01]),
            bucket=np.zeros(2, np.int8),
        )
        for _plane in range(3)
    )
    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(anchor_min_quality=0.1))
    assert builder.add_anchors((stub,), anchors) == 3


# ------------------------------------------------------ W4: the probes
@pytest.mark.parametrize(
    "mode,expected_probes",
    # BLOCK_PER_BIN's 5x5 template fits inside every window; the shipped
    # TILE_FRAGMENT template is the whole covered part of the tile, and
    # each fixture window IS one tile, so its search frame overhangs the
    # synthetic raster on the eight EDGE windows and only the interior
    # window measures -- the same geometry
    # ``test_the_whole_tile_density_measures_the_same_displacement``
    # pins.  Both densities land on the injected truth, which is the
    # claim; the counts are the reach the fixture can offer each.
    ((ProbeMode.BLOCK_PER_BIN, 27), (ProbeMode.TILE_FRAGMENT, 3)),
)
def test_the_probe_pass_recovers_the_injected_plane_offsets(
    mode: ProbeMode, expected_probes: int,
) -> None:
    """Tier (i) against the certificate's own re-encoded printed cells."""
    fixture = build_fixture("cmy8-residual")
    windows = _probe_windows(fixture)
    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(probe_mode=mode))
    added = builder.add_certified_probes(
        fixture.raster, windows, _projection_source(fixture.field))
    assert added > 0
    builder.solve()
    report = builder.report()
    # One site per (certified tile, covering window), and these windows
    # are one tile each: every window is probed, none twice -- which at
    # ``bins_per_tile = 1`` is also where BLOCK_PER_BIN puts its sites.
    assert report.n_probe_sites == len(windows)
    assert added == report.n_probes == expected_probes
    assert report.samples_by_source == {"probe": report.n_probes}
    for plane, truth in enumerate(RESIDUAL_TRUTH_DOTS_XY):
        affine = builder._field.lookup_tile_index(0, 1, 1)[plane]
        assert affine.covered, PLANE_NAMES[plane]
        assert affine.delta_dots_xy[0] == pytest.approx(truth[0], abs=0.10)
        assert affine.delta_dots_xy[1] == pytest.approx(truth[1], abs=0.10)


def test_the_probe_pass_reads_zero_on_the_clean_twin() -> None:
    """The restraint half: no disease, no correction."""
    fixture = build_fixture("cmy8-clean")
    builder = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    builder.add_certified_probes(
        fixture.raster, _probe_windows(fixture),
        _projection_source(fixture.field))
    builder.solve()
    report = builder.report()
    assert max(report.peak_dots) < 0.05
    # And with nothing to say, the adoption margin refuses.
    rows = tuple(_window_rows(patch, fixture.spec)
                 for patch in fixture.address.placements)

    class _Stub:
        def __init__(self, row, patch) -> None:
            self.page_cells_yx = row.page_cells_yx
            self.patch = patch

    stubs = tuple(
        _Stub(row, patch)
        for row, patch in zip(rows, fixture.address.placements))
    overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (False, False, False)
    assert all(entry is None for row in overrides for entry in row)


def test_the_probe_pass_has_no_ceiling_and_covers_every_bin() -> None:
    """No budget: the site set is GEOMETRY (user ruling 2026-08-22).

    Was ``test_the_probe_budget_bounds_the_pass``, which pinned the
    retired ``probe_budget_per_region`` -- a silent 256-site cap that
    decided how much of a decoded sheet the field was allowed to see.
    What replaces it is one probe per FIELD BIN, so the count follows
    ``bins_per_tile`` (resolution) and the certified area, and nothing is
    dropped for being over a number.
    """
    fixture = build_fixture("cmy8-clean")
    windows = _probe_windows(fixture)
    projection = _projection_source(fixture.field)
    assert not hasattr(PlaneFieldConfig(), "probe_budget_per_region")

    sites = {}
    fragment_sites = {}
    for bins_per_tile in (1, 2, 4):
        builder = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig(
            probe_mode=ProbeMode.BLOCK_PER_BIN,
            bins_per_tile=bins_per_tile))
        builder.add_certified_probes(fixture.raster, windows, projection)
        builder.solve()
        report = builder.report()
        sites[bins_per_tile] = report.n_probe_sites
        assert report.n_probes >= 3 * 0.8 * report.n_probe_sites
        fragment = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig(
            probe_mode=ProbeMode.TILE_FRAGMENT,
            bins_per_tile=bins_per_tile))
        fragment.add_certified_probes(fixture.raster, windows, projection)
        fragment_sites[bins_per_tile] = fragment.report().n_probe_sites
    # every window is one tile here, so a bin is (1/bins_per_tile)^2 of it
    assert sites == {1: len(windows), 2: 4 * len(windows),
                     4: 16 * len(windows)}
    # The SHIPPED density is tile-centric, so ``bins_per_tile`` is a FIELD
    # resolution dial there and not a probe-site dial: one site per
    # (certified tile, covering window) at every bin count.
    assert fragment_sites == {bins: len(windows) for bins in (1, 2, 4)}

    # and the same windows probed twice give the same sites, in the same
    # order: the choice is a function of the geometry, nothing else
    twice = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    twice.add_certified_probes(fixture.raster, windows, projection)
    once = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    once.add_certified_probes(fixture.raster, windows, projection)
    assert twice._field.to_json()["bins"] == once._field.to_json()["bins"]


def test_an_uncertified_tile_is_never_probed() -> None:
    """Tier (i) is CERTIFIED evidence: a guess is not ground truth."""
    fixture = build_fixture("cmy8-clean")
    builder = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    assert builder.add_certified_probes(
        fixture.raster, _probe_windows(fixture), lambda _address: None) == 0
    assert builder.report().n_probe_sites == 0


def test_done_tiles_are_the_certificate_set_page_aware() -> None:
    """P1: every fully certified tile, whatever the probe pass visited.

    ``done_tiles`` used to be a by-product of the probe memo, so a page
    the pass never reached -- or, at ``probe_budget_per_region=0``, the
    whole sheet -- painted as "nothing known here" in the W5 band, which
    is the opposite of the truth.  It is now the caller's own
    fully-certified address set, verbatim, and it names its page.
    """
    fixture = build_fixture("cmy8-clean")
    addresses = ((1, 4, 2), (0, 3, 1), (0, 3, 1), (0, 0, 0))
    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(), done_tiles=addresses)
    builder.solve()
    report = builder.report()
    assert report.done_tiles == ((0, 0, 0), (0, 3, 1), (1, 4, 2))
    assert report.n_probe_sites == 0        # no probe pass ran at all
    assert report.snapshot()["done"] == [[0, 0, 0], [0, 3, 1], [1, 4, 2]]

    # a builder told nothing reports nothing -- it never guesses
    bare = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    bare.add_certified_probes(
        fixture.raster, _probe_windows(fixture),
        _projection_source(fixture.field))
    bare.solve()
    assert bare.report().n_probe_sites > 0
    assert bare.report().done_tiles == ()


def _interior_window(fixture) -> ProbeWindow:
    """The one fixture window a 64-cell template can reach at all."""
    for window in _probe_windows(fixture):
        page = np.asarray(window.page_cells_yx, np.int64)
        if tuple(page[0] // 64) == (1, 1):
            return window
    raise AssertionError("the fixture lost its interior window")


def _split_window(
    window: ProbeWindow, at_local_x: int
) -> tuple[ProbeWindow, ProbeWindow]:
    """Two windows over ONE tile, sharing its patch and therefore its pose.

    The fixture's windows are one tile each, so nothing in it straddles a
    boundary; splitting the audited cells of one window in two is the
    same geometry seen from the other side -- one tile, two covering
    windows, each holding a PART of it.
    """
    local = np.asarray(window.local_cells_yx, np.int64)
    page = np.asarray(window.page_cells_yx, np.int64)
    left = local[:, 1] < at_local_x
    return (
        ProbeWindow(window.patch, window.page, local[left], page[left]),
        ProbeWindow(window.patch, window.page, local[~left], page[~left]),
    )


def test_a_straddling_tile_is_probed_through_every_covering_window() -> None:
    """E5b's reach mechanism, and the user's correction of E5.

    "When you have a certified tile, each window that covers this tile
    (fully or partially) can profit from the pose/field measurement."  A
    SQUARE template must lie wholly inside one window, so a tile split
    across two windows is invisible to the whole-tile density -- which is
    what capped E5's density B at 516 of 1,628 tiles.  TILE_FRAGMENT asks
    the other question and measures the covered PART, once per covering
    window, and still lands on the injected truth.
    """
    fixture = build_fixture("cmy8-residual")
    halves = _split_window(_interior_window(fixture), 30)
    projection = _projection_source(fixture.field)

    square = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(probe_mode=ProbeMode.WHOLE_TILE))
    assert square.add_certified_probes(
        fixture.raster, halves, projection) == 0
    assert square.report().n_probe_sites == 0

    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(probe_mode=ProbeMode.TILE_FRAGMENT))
    added = builder.add_certified_probes(fixture.raster, halves, projection)
    report = builder.report()
    assert report.n_probe_sites == 2          # one per covering window
    assert added == report.n_probes == 6      # x three planes
    for plane, truth in enumerate(RESIDUAL_TRUTH_DOTS_XY):
        affine = builder._field.lookup_tile_index(0, 1, 1)[plane]
        assert affine.covered, PLANE_NAMES[plane]
        assert affine.delta_dots_xy[0] == pytest.approx(truth[0], abs=0.15)
        assert affine.delta_dots_xy[1] == pytest.approx(truth[1], abs=0.15)


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_a_fragment_site_is_local_in_extent_and_page_in_centre(
    rot_k: int,
) -> None:
    """The frame split a rot90 would break if it were got wrong.

    ``height_cells``/``width_cells`` slice the window's LOCAL cells (the
    frame ``_rectified_ncc`` walks) while ``centre_page_yx`` is where the
    evidence is scattered in PAGE tile space.  The implementation takes
    the page centre from the extrema of the covered page cells, which is
    only the rectangle's centre because min/max commute with a rot90; the
    independent check here is the CENTROID, which equals the centre of a
    full rectangle whatever the orientation.
    """
    from holo.receive._payload_sampling import rotated_points
    from holo.receive.color_probes import _tile_fragment_sites

    shape = (64, 64)
    rows, columns = 64, 20        # deliberately not square
    local = np.stack(np.mgrid[0:rows, 0:columns], axis=-1).reshape(-1, 2)
    page = rotated_points(local, shape, rot_k)
    sites = _tile_fragment_sites(
        ProbeWindow(None, 0, local, page), 0,
        lambda _address: True, 10, min_edge_cells=5)
    assert len(sites) == 1
    site = sites[0]
    assert (site.height_cells, site.width_cells) == (rows, columns)
    assert (site.local_y0, site.local_x0) == (0, 0)
    assert site.dense is True
    assert site.centre_page_yx == pytest.approx((
        float(page[:, 0].mean()) + 0.5, float(page[:, 1].mean()) + 0.5))
    assert site.address == (0, 0, 0)


def test_a_fragment_too_thin_to_locate_is_refused() -> None:
    """The eligibility floor is IDENTIFIABILITY, not thrift.

    The template is piecewise constant per CELL, so a fragment fewer than
    ``probe_block_cells`` cells wide has no horizontal structure at all
    and its ``dx`` would be whatever the search window's edges say.  The
    floor is the shipped 5x5 probe's own extent, per axis and in total --
    a fragment below it would be weaker evidence than the density the
    receiver already ships on.
    """
    from holo.receive.color_probes import _tile_fragment_sites

    def sites(rows: int, columns: int):
        local = np.stack(np.mgrid[0:rows, 0:columns], axis=-1).reshape(-1, 2)
        return _tile_fragment_sites(
            ProbeWindow(None, 0, local, local.copy()), 0,
            lambda _address: True, 10, min_edge_cells=5)

    assert len(sites(64, 4)) == 0        # 256 cells, but 4 wide
    assert len(sites(4, 64)) == 0        # 256 cells, but 4 tall
    assert len(sites(6, 4)) == 0         # 24 cells: under one block's worth
    assert len(sites(5, 5)) == 1         # exactly one block's worth


def test_a_holed_fragment_carries_weights_not_a_refusal() -> None:
    """Weight 0 on the cells that are not this tile's certified ink."""
    from holo.receive.color_probes import _tile_fragment_sites, probe_template

    fixture = build_fixture("cmy8-clean")
    window = _interior_window(fixture)
    local = np.asarray(window.local_cells_yx, np.int64)
    page = np.asarray(window.page_cells_yx, np.int64)
    # Punch a hole: one interior cell of the tile is simply not audited.
    keep = ~((local[:, 0] == 20) & (local[:, 1] == 20))
    holed = ProbeWindow(window.patch, 0, local[keep], page[keep])
    site = _tile_fragment_sites(
        holed, 0, lambda _address: True,
        int(fixture.spec.layout.tiles_yx[1]), min_edge_cells=5)[0]
    assert site.dense is False
    bits, weights = probe_template(
        holed, site, _projection_source(fixture.field)((0, 1, 1)),
        min_edge_cells=5)
    assert bits.shape == (64, 64, 3)
    assert weights.sum() == 64 * 64 - 1
    assert weights[20, 20] == 0.0


def test_the_plane_common_residual_is_measured_and_never_applied() -> None:
    """The pose feedback is REPORTED, not fed back (P5 writer work).

    Every probe splits into a per-plane part -- what the field consumes --
    and a part all three planes share, which is the covering WINDOW's own
    pose error seen through certified ground truth.  The clean twin pins
    the restraint half: nothing wrong with the pose, nothing reported.
    """
    fixture = build_fixture("cmy8-clean")
    windows = _probe_windows(fixture)
    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(probe_mode=ProbeMode.TILE_FRAGMENT))
    builder.add_certified_probes(
        fixture.raster, windows, _projection_source(fixture.field))
    report = builder.report()
    assert report.window_pose_residuals
    assert len(report.window_pose_residuals) <= len(windows)
    patch_ids = {int(window.patch.patch_id) for window in windows}
    for entry in report.window_pose_residuals:
        assert entry.patch_id in patch_ids
        assert entry.page == 0
        assert entry.n_sites >= 1
        assert entry.magnitude_dots < 0.05
    # and it stays out of the field: this is not evidence, it is a report
    assert report.samples_by_source == {"probe": report.n_probes}


def test_the_plane_common_residual_is_not_the_differential_disease() -> None:
    """A per-plane warp must NOT show up as a pose correction."""
    fixture = build_fixture("cmy8-residual")
    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(probe_mode=ProbeMode.TILE_FRAGMENT))
    builder.add_certified_probes(
        fixture.raster, _probe_windows(fixture),
        _projection_source(fixture.field))
    report = builder.report()
    # The three injected plane offsets average to (0.033, 0.033) dots,
    # an order below the 0.7-0.86 dot per-plane truth the field recovers.
    assert max(report.peak_dots) > 0.4
    assert max(report.pose_residual_magnitudes()) < 0.20


def test_the_probe_density_default_is_the_measured_one() -> None:
    """The 2026-08-23 ruling, pinned: the shipped density is TILE_FRAGMENT.

    E5b measured the three densities on the archived W6 sheet-I state,
    capture 1, lane ``l02-8ppc-2400dpi``
    (``measure/plane_fields/probe_density.py``,
    ``scratch/plane-fields/p2/e5b/``; INDEPENDENT-PLANES §2.9b/§2.9c).
    For the FIELD alone the three tie once every window is offered --
    coverage 0.997 both, Spearman +0.9711 vs +0.9699, per-tile MAD 0.163
    vs 0.168 -- which is why §2.9b left the default where it was.  The
    ruling changes the question the pass answers: ONE measurement per
    (certified tile, covering window) serves the per-plane field AND the
    plane-common pose residual, and the pose residual is the half a 5x5
    template cannot carry (site-to-site spread 0.264 dots against a
    0.184-0.200 dot signal, 9% of windows self-consistent, against
    TILE_FRAGMENT's 0.187 and 17%).  A ``ProbeMode`` other than this one
    is a deliberate, measured decision, so it is pinned.
    """
    assert PlaneFieldConfig().probe_mode is ProbeMode.TILE_FRAGMENT
    assert PlaneFieldConfig().probe_block_cells == 5
    with pytest.raises(ValueError, match="probe_mode"):
        PlaneFieldConfig(probe_mode="whole-tile")


def test_the_whole_tile_density_measures_the_same_displacement() -> None:
    """E5's density B is a real alternative, not a broken one.

    One probe per fully-certified tile against that tile's ENTIRE 64x64
    re-encoded cells -- the V0 instrument's template, inside the
    production pass.  It recovers the injected per-plane displacement
    the way the 5x5 blocks do; what it does not do is REACH as many
    tiles, which is what kept it out of the default.  On this fixture
    that shows up as the eight EDGE windows: a 64-cell template plus its
    search margin leaves the synthetic raster, so only the interior
    window's tile yields measurements at all.
    """
    fixture = build_fixture("cmy8-residual")
    windows = _probe_windows(fixture)
    builder = PlaneFieldBuilder(
        fixture.spec, PlaneFieldConfig(probe_mode=ProbeMode.WHOLE_TILE))
    added = builder.add_certified_probes(
        fixture.raster, windows, _projection_source(fixture.field))
    builder.solve()
    report = builder.report()
    # One site per window: each window here is exactly one tile, and a
    # 64-cell square wholly inside a 64-cell tile IS that tile -- no bin
    # rule needed, and never two probes of one tile from one window.
    assert report.n_probe_sites == len(windows)
    assert added == report.n_probes == 3
    assert report.samples_by_source == {"probe": 3}
    for plane, truth in enumerate(RESIDUAL_TRUTH_DOTS_XY):
        affine = builder._field.lookup_tile_index(0, 1, 1)[plane]
        assert affine.covered, PLANE_NAMES[plane]
        assert affine.delta_dots_xy[0] == pytest.approx(truth[0], abs=0.15)
        assert affine.delta_dots_xy[1] == pytest.approx(truth[1], abs=0.15)


# --------------------------------------------------- W2: the adoption
def _adoption_builder(spec, delta_dots_xy, *, weight=1.0, tile_origin=0,
                      config=None):
    """A field scattered over a 3x3 tile block at a chosen delta.

    ``tile_origin`` moves that block away from the fixture's windows
    (which sit on tiles 0..2), which is how a region ends up OUTSIDE the
    evidence hull without touching the estimator's own constants.
    """
    builder = PlaneFieldBuilder(spec, config or PlaneFieldConfig())
    evidence = []
    for tile_y in range(3):
        for tile_x in range(3):
            for plane in range(3):
                for repeat in range(8):
                    evidence.append(FieldEvidence(
                        page=0,
                        tile_yx=(tile_origin + tile_y + 0.5,
                                 tile_origin + tile_x + 0.5),
                        plane_index=plane,
                        offset_dots_xy=delta_dots_xy,
                        weight=weight,
                        source="probe" if repeat else "certified",
                    ))
    builder._add(evidence)
    builder.solve()
    return builder


def _region_stubs(fixture):
    class _Stub:
        def __init__(self, row, patch) -> None:
            self.page_cells_yx = row.page_cells_yx
            self.patch = patch

    return tuple(
        _Stub(_window_rows(patch, fixture.spec), patch)
        for patch in fixture.address.placements)


def test_a_correction_under_the_margin_is_not_adopted() -> None:
    """The measured sheet-I cliff is the bar: below it, say nothing."""
    fixture = build_fixture("cmy8-clean")
    stubs = _region_stubs(fixture)
    builder = _adoption_builder(fixture.spec, (0.05, 0.05))
    _overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (False, False, False)


def test_a_correction_over_the_margin_is_adopted_and_served() -> None:
    fixture = build_fixture("cmy8-clean")
    stubs = _region_stubs(fixture)
    builder = _adoption_builder(fixture.spec, (0.9, -0.6))
    overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (True, True, True)
    for row, stub in zip(overrides, stubs):
        for entry in row:
            assert entry is not None
            assert entry.shape == (stub.page_cells_yx.shape[0], 2)
            assert entry[:, 0] == pytest.approx(0.9, abs=0.15)
            assert entry[:, 1] == pytest.approx(-0.6, abs=0.15)
    report = builder.report()
    assert report.adopted_text == "C,M,Y"
    assert report.regions_adopted_by_plane == (1, 1, 1)


def test_a_region_outside_the_evidence_hull_falls_back() -> None:
    """The PK6 lesson: never a free parameter where evidence is thin."""
    fixture = build_fixture("cmy8-clean")
    stubs = _region_stubs(fixture)
    builder = _adoption_builder(fixture.spec, (0.9, -0.6), tile_origin=20)
    _overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (False, False, False)


def test_an_uncertain_field_falls_back_even_where_it_is_covered() -> None:
    """Covered is not believed: the posterior sd has its own gate."""
    fixture = build_fixture("cmy8-clean")
    stubs = _region_stubs(fixture)
    builder = _adoption_builder(fixture.spec, (0.9, -0.6), weight=0.002)
    affine = builder._field.lookup_cells(0, (96.0, 96.0))[0]
    assert affine.covered
    assert affine.uncertainty_dots > PlaneFieldConfig().max_uncertainty_dots
    _overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (False, False, False)


def test_an_unsolved_field_serves_nothing() -> None:
    fixture = build_fixture("cmy8-clean")
    stubs = _region_stubs(fixture)
    builder = PlaneFieldBuilder(fixture.spec, PlaneFieldConfig())
    overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (False, False, False)
    assert all(entry is None for row in overrides for entry in row)


def test_the_served_delta_is_clamped() -> None:
    """A wild lookup can move sampling by at most ``max_delta_dots``."""
    fixture = build_fixture("cmy8-clean")
    stubs = _region_stubs(fixture)
    builder = _adoption_builder(
        fixture.spec, (12.0, -9.0),
        config=PlaneFieldConfig(max_delta_dots=1.5, plane_sigma_dots=50.0,
                                prior_sigma_dots=50.0))
    overrides, adopted = builder.region_offsets(0, stubs)
    assert adopted == (True, True, True)
    for row in overrides:
        for entry in row:
            assert float(np.hypot(*entry.T).max()) <= 1.5 + 1e-9


# ------------------------------------------- W2: per-window clamp/null
def _fixture_rows(fixture, patch) -> _Rows:
    """A ``_Rows`` carrying only what the sampling seam reads."""
    aligned = _window_rows(patch, fixture.spec)
    count = aligned.page_cells_yx.shape[0]
    return _Rows(
        patch,
        aligned.local_cells_yx,
        aligned.page_cells_yx,
        aligned.scan_points_yx,
        np.full(count, -1, np.int8),
        np.full(count, -1, np.int8),
        np.zeros((count, 3), np.uint8),
        np.zeros((count, 3), np.bool_),
        np.zeros((count, 9), np.int32),
        (),
    )


def test_a_window_that_exits_the_raster_nulls_only_its_own_correction(
) -> None:
    """§6.1 pitfall 2: the field must never null a whole region's arm."""
    fixture = build_fixture("cmy8-clean")
    patch = fixture.address.placements[0]
    rows = _fixture_rows(fixture, patch)
    residuals = tuple(
        PlaneResidual((0.0, 0.0), (0.0, 0.0), 0) for _ in range(3))
    count = rows.page_cells_yx.shape[0]
    absurd = np.full((count, 2), -1.0e6, np.float64)

    baseline, nulled = field_corrected_features(
        fixture.raster, rows, residuals, fixture.spec,
        fixture.pitch_px, 255.0, (None, None, None))
    assert baseline is not None and not nulled

    corrected, nulled = field_corrected_features(
        fixture.raster, rows, residuals, fixture.spec,
        fixture.pitch_px, 255.0, (absurd, None, None))
    assert nulled is True
    # The window keeps a corrected arm — the residual one, unchanged.
    assert corrected is not None
    assert np.array_equal(corrected, baseline)

    small = np.full((count, 2), 0.25, np.float64)
    shifted, nulled = field_corrected_features(
        fixture.raster, rows, residuals, fixture.spec,
        fixture.pitch_px, 255.0, (small, None, None))
    assert not nulled
    assert not np.array_equal(shifted, baseline)


# ------------------------------------------------------- THE NULL PROOF
def test_the_dial_is_off_by_default_everywhere() -> None:
    assert ProductionColorPayload().plane_fields is None
    assert ProductionColorPayload().stack_config is None


def test_the_default_decode_is_unchanged_by_this_arm(tmp_path: Path) -> None:
    """THE NULL PROOF — the campaign-style bit-identity claim.

    The pooled 10x10 colour fixture through the ORDINARY production
    pipeline: same certificate set, same close, and not one
    ``payload.plane_fields`` event.  Both digests were captured on the
    pre-change tree.
    """
    spec = _pooled_spec()
    payload = _pooled_payload()
    volume = emit_volume(spec, payload, _Q, tmp_path / "volume")
    raster = _raster(spec, _coverage(spec, volume.pages[0].gt_path))

    result, events = _decode(
        spec, raster, tmp_path / "null.receive.json", None)

    state = result.state
    assert result.payload == payload
    assert state.status.value == "verified"
    assert len(state.certificates) == NULL_CERTIFICATES
    assert _certificate_digest(state) == NULL_CERT_DIGEST
    assert state.close.payload_sha256 == NULL_CLOSE_SHA
    assert state.close.payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert not [row for row in events if row.name == "payload.plane_fields"]
    assert not [
        detail for row in events for detail in row.details
        if detail.name.startswith("plane_fields")]


# ---------------------------------------------------- the dial-ON smoke
@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the plane-fields dial smoke",
)
def test_the_dial_recovers_a_plane_the_residual_cannot_model(
    tmp_path: Path,
) -> None:
    """Claim 3: same evidence, wider basis, measured certificate gain."""
    spec = _pooled_spec()
    payload = _pooled_payload()
    volume = emit_volume(spec, payload, _Q, tmp_path / "volume")
    coverage = _warp_plane(
        _coverage(spec, volume.pages[0].gt_path), WARP_PLANE)
    raster = _raster(spec, coverage)

    off, _off_events = _decode(
        spec, raster, tmp_path / "warp-off.receive.json", None)
    on, on_events = _decode(
        spec, raster, tmp_path / "warp-on.receive.json", PlaneFieldConfig())

    n_off = len(off.state.certificates)
    n_on = len(on.state.certificates)
    # The disease exists: the warp really does cost certificates.
    assert n_off < NULL_CERTIFICATES, (
        "the warped fixture stopped being degraded — the smoke proves "
        "nothing until it is")
    assert n_on >= n_off
    assert n_on == NULL_CERTIFICATES
    assert on.payload == payload

    emitted = [row for row in on_events if row.name == "payload.plane_fields"]
    assert emitted, "the dial-on lane must report its field"
    details = {row.name: row.value for row in emitted[-1].details}
    for name in PLANE_NAMES:
        assert f"plane_fields.rms_dots.{name.lower()}" in details
    assert "plane_fields.coverage" in details
    assert PLANE_NAMES[WARP_PLANE] in str(details["plane_fields.adopted"])
    snapshot = emitted[-1].snapshot
    assert set(snapshot) == {"planes", "done", "exaggeration_hint"}
    assert snapshot["planes"] and len(snapshot["planes"][0]) == 5
    # ``done`` rows are PAGE-AWARE (P1): [page, tile_y, tile_x].  Empty
    # here and RIGHTLY so -- one colour lane fires on this fixture and it
    # opens with an empty certificate ledger, so at report time nothing
    # on the sheet is done yet.  The populated shape is pinned in
    # ``test_done_tiles_are_the_certificate_set_page_aware``.
    assert all(len(row) == 3 for row in snapshot["done"])
    assert snapshot["exaggeration_hint"] > 0.0
