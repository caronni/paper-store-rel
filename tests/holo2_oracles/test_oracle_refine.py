"""H5 P4 pin (a): RF1's refine step against v1's own ``certified_refine``.

What P4 carries from v1 is the BOUNDED POSE REVISION — its constants, its
two-stage grid, its deterministic holdout and site caps, its contrast
objective and weighted log-loss, and its three-part adoption gate. So the
bar is v1's own code, called here, on identical inputs, compared to the
bit.

The comparison is taken at TWO depths, because the carry has two:

* **piece by piece** — every carried function against the private v1
  function it was carried from, byte for byte, over populations wide
  enough to exercise their tie-breaks and their floors. This half is
  EXACT and unconditional;
* **end to end** — v1's ``refine_segment`` and holo2's ``propose`` on one
  real rendered page, one real pose error, and one real certificate
  frontier. The REVISED AFFINE byte-compares; the log-losses match to
  float32 round-off, for the one reason stated below.

THE ONE CONVENTION THAT DIFFERS, and why it is not a divergence. holo2
calibrates on NEGATED RAW LUMA (``place_shared`` emits ``scores =
-means``), so a committed ``CalibrationRecord``'s knots live on that
scale; v1 normalises first (``(midpoint - raw) / spread``) and its nodes
live on THAT one. The two scales are related by a positive affine map, so
the PAVA is the same monotone function either way — but each tree must
score through the convention its own knots were fitted under, or it reads
the wrong map. This fixture therefore hands v1 the SAME calibration
expressed on v1's scale (:func:`_v1_nodes`), which is what makes the two
end-to-end runs comparable at all. v1 then computes candidate scores in
float32 while holo2 stays in float64, so the LOSSES agree to about 1e-7
rather than to the bit. The WINNER does not depend on that: the ranking
is ``_pose_objective`` on raw means, which is identical in both trees
because both sample the identical float32 prepared plane through the
identical ``map_coordinates(order=1)`` call.

Both packages may be imported HERE, outside the holo2 tree, which is the
standing every oracle in this directory has.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest
from scipy import ndimage

from holo.format.resolve import resolve_format_ref as h_resolve_format_ref
from holo.receive import certified_refine as v1
from holo.receive.evidence import TileCertificateRecord
from holo.receive.records import stream_certificate_identity
from holo.receive.payload import format_reference_values
from holo.receive.payload_model import PAVA_PROFILE, EvidenceSource
from holo.receive.payload_model import WindowEvidence as V1WindowEvidence
from holo.receive.placement.model import AffinePose as V1AffinePose
from holo.receive.placement.model import PlacedSegment as V1PlacedSegment
from holo.receive.placement.model import PoseSegment as V1PoseSegment
from holo.receive.placement.model import PoseWindow as V1PoseWindow

from holo2.capture.footing_raster import FootingFrame
from holo2.format.registry_rows import tile_format_for
from holo2.solve import refine
from holo2.solve.detect import Calibration
from holo2.solve.reference import ReferencePage, V1ReferenceField
from holo2.solve.refine import RefineInput
from holo2.solve.tiles import printed_cells_for
from holo2.format.resolve import format_row_for

# v2 IDENTITY since 2026-08-22 (package C4, RULINGS G5), on exactly the
# tile matrix the retired 68x68 mm synthetic media derived at c2 —
# geometry is identity (FORMAT-SPACE §7), so one string describes the
# page to both trees and no media has to be inverted to find it.
FORMAT = "c2-k-r0550@12x12"
WINDOW_TILES_YX = (2, 2)          # the refine window, in 64-cell tiles
PITCH_PX = 6.0
POSE_ERROR_CELLS = 0.14
BACKING = 210.0


# ------------------------------------------------- pin (a1): the constants

CARRIED_CONSTANTS = (
    "BLOCK_CELLS", "VALIDATION_MODULUS", "MIN_PAYLOAD_TRAIN",
    "MIN_PAYLOAD_VALIDATION", "MIN_TRAIN_PER_CLASS",
    "MIN_VALIDATION_PER_CLASS", "MIN_CERTIFIED_BLOCKS", "MIN_POSE_PILOTS",
    "MIN_HELDOUT_GAIN", "PILOT_MISMATCH_SLACK", "ANGLE_LIMIT_DEG",
    "ANGLE_COARSE_STEP_DEG", "ANGLE_FINE_STEP_DEG", "PHASE_LIMIT_CELLS",
    "PHASE_COARSE_STEP_CELLS", "PHASE_FINE_STEP_CELLS",
    "POSE_SITE_CAP_TRAIN", "POSE_SITE_CAP_VALIDATION",
)


@pytest.mark.parametrize("name", CARRIED_CONSTANTS)
def test_every_carried_constant_equals_v1s(name: str) -> None:
    """holo2 re-declares these (the import firewall); v1 owns their values.

    Re-declaration is what the firewall costs, and this is what keeps it
    from costing anything else: a value that drifts from v1's is a test
    failure naming the constant, not a silent fork of the algorithm.
    """
    assert getattr(refine, name) == getattr(v1, name), name


def test_the_spread_floor_is_the_carried_one() -> None:
    """``SCORE_SPREAD_FLOOR`` lives in v1's ``_payload_sampling``."""
    from holo.receive._payload_sampling import SCORE_SPREAD_FLOOR
    assert refine.SCORE_SPREAD_FLOOR == SCORE_SPREAD_FLOOR


# -------------------------------------------------- pin (a2): the two grids

def test_the_coarse_grid_is_v1s_own_enumeration() -> None:
    """Same ``np.arange`` triple product, same order, same floats."""
    angles = np.arange(-v1.ANGLE_LIMIT_DEG, v1.ANGLE_LIMIT_DEG + 1e-12,
                       v1.ANGLE_COARSE_STEP_DEG)
    phase = np.arange(-v1.PHASE_LIMIT_CELLS, v1.PHASE_LIMIT_CELLS + 1e-12,
                      v1.PHASE_COARSE_STEP_CELLS)
    expected = [(float(a), float(u), float(dv))
                for a in angles for u in phase for dv in phase]
    assert list(refine.candidate_grid()) == expected


@pytest.mark.parametrize("corner", [(-0.15, -0.25, -0.25), (0.0, 0.0, 0.0),
                                    (0.15, 0.25, 0.25), (0.15, -0.25, 0.25)])
def test_the_fine_grid_is_v1s_own_clipped_enumeration(corner) -> None:
    """v1 re-tests every fine step against the LIMIT; so does this one.

    Transcribed from ``refine_segment``'s fine block directly, including
    the asymmetry that ``dv`` is clipped inside the innermost loop while
    ``dtheta`` and ``du`` are clipped by ``continue`` — same set, same
    order.
    """
    fine_angles = np.arange(corner[0] - v1.ANGLE_COARSE_STEP_DEG,
                            corner[0] + v1.ANGLE_COARSE_STEP_DEG + 1e-12,
                            v1.ANGLE_FINE_STEP_DEG)
    fine_du = np.arange(corner[1] - v1.PHASE_COARSE_STEP_CELLS,
                        corner[1] + v1.PHASE_COARSE_STEP_CELLS + 1e-12,
                        v1.PHASE_FINE_STEP_CELLS)
    fine_dv = np.arange(corner[2] - v1.PHASE_COARSE_STEP_CELLS,
                        corner[2] + v1.PHASE_COARSE_STEP_CELLS + 1e-12,
                        v1.PHASE_FINE_STEP_CELLS)
    expected = []
    for dtheta in fine_angles:
        if abs(dtheta) > v1.ANGLE_LIMIT_DEG + 1e-12:
            continue
        for du in fine_du:
            if abs(du) > v1.PHASE_LIMIT_CELLS + 1e-12:
                continue
            for dv in fine_dv:
                if abs(dv) <= v1.PHASE_LIMIT_CELLS + 1e-12:
                    expected.append((float(dtheta), float(du), float(dv)))
    assert list(refine.fine_grid(corner)) == expected


# ---------------------------------------------- pin (a3): the pure functions

def test_pose_candidate_is_byte_identical_over_the_whole_grid() -> None:
    """THE function pin (a) is about: the revised affine itself.

    Every key both stages can produce, on a pose with a real shear and a
    real rotation, compared field for field as exact floats — origin,
    Jacobian, pitch and angle.
    """
    terms = ((6.01, 0.031), (-0.029, 5.98))
    base = refine.pose_candidate.__globals__["AffinePose"](
        (12.25, -7.5), terms, (0.0, 0.0), 6.0, 0.3)
    v1_base = V1AffinePose((12.25, -7.5), terms, (0.0, 0.0), 6.0, 0.3)
    keys = list(refine.candidate_grid())
    for corner in refine.candidate_grid():
        keys += list(refine.fine_grid(corner))
    assert len(keys) > 500
    for key in keys:
        mine = refine.pose_candidate(base, *key)
        theirs = v1._pose_candidate(v1_base, *key)
        assert mine.origin_yx == theirs.origin_yx, key
        assert mine.jacobian_yx == theirs.jacobian_yx, key
        assert mine.pitch_px == theirs.pitch_px, key
        assert mine.angle_deg == theirs.angle_deg, key


def test_the_objective_and_the_logloss_are_byte_identical() -> None:
    """Both scalars, over a wide seeded population."""
    rng = np.random.default_rng(20260818)
    for _ in range(16):
        n = int(rng.integers(64, 4096))
        means = rng.normal(120.0, 40.0, n)
        weights = rng.random(n) + 1e-3
        values = (rng.random(n) > 0.5).astype(np.uint8)
        assert (refine.pose_objective(means, values, weights)
                == v1._pose_objective(means, values, weights))
        logits = rng.normal(0.0, 4.0, n)
        assert (refine.weighted_logloss(logits, values, weights)
                == v1._weighted_logloss(logits, values, weights))


def test_the_objective_agrees_on_v1s_single_class_sentinel() -> None:
    """A one-class population returns ``-inf`` in both trees."""
    means = np.linspace(0.0, 1.0, 32)
    weights = np.ones(32)
    for values in (np.zeros(32, np.uint8), np.ones(32, np.uint8)):
        assert (refine.pose_objective(means, values, weights)
                == v1._pose_objective(means, values, weights) == -np.inf)


def test_the_adoption_gate_agrees_on_every_corner() -> None:
    """All three conditions, each swept across its own boundary."""
    slack = v1.PILOT_MISMATCH_SLACK
    gain = v1.MIN_HELDOUT_GAIN
    rows = []
    for candidate in (1.0, 1.0 - gain / 2, 1.0 - gain, 1.0 - 2 * gain, 0.5):
        for pilot in (0.1, 0.1 + slack, 0.1 + 2 * slack, 0.05):
            for raw in (0.1, 0.1 + slack, 0.1 + 2 * slack, 0.05):
                rows.append((1.0, candidate, 0.1, pilot, 0.1, raw))
    assert len(rows) == 80
    for row in rows:
        assert refine.adoption_gate(*row) == v1._adoption_gate(*row), row
    # And the sweep is not vacuous: both verdicts really occur.
    verdicts = {v1._adoption_gate(*row) for row in rows}
    assert verdicts == {True, False}


def test_the_block_holdout_and_weights_are_byte_identical() -> None:
    """The stripe assignment (with its 9177 ruling) and the block weights."""
    rng = np.random.default_rng(4242)
    for page in (0, 1, 7):
        cells = rng.integers(0, 900, size=(3000, 2))
        assert np.array_equal(refine.block_validation(page, cells),
                              v1._block_validation(page, cells))
    ids = rng.integers(0, 400, size=3000)
    assert np.array_equal(refine.block_weights(ids), v1._block_weights(ids))
    assert np.array_equal(refine.block_weights(np.zeros(0, np.int64)),
                          v1._block_weights(np.zeros(0, np.int64)))


def test_the_deterministic_site_cap_is_byte_identical() -> None:
    """The seedless hash order that keeps a capped population reproducible.

    v1 reads the coordinates off a ``SegmentLabels``; holo2 takes them as
    an argument. Same golden-ratio mixing constants, same stable argsort,
    same prefix — including the pass-through when the population is
    already under the cap.
    """
    rng = np.random.default_rng(99)
    cells = rng.integers(0, 500, size=(5000, 2)).astype(np.int64)
    positions = np.arange(5000, dtype=np.int64)

    class _Labels:
        page_cells_yx = cells

    for cap in (0, 1, 17, 1024, 4999, 5000, 6000):
        assert np.array_equal(
            refine.deterministic_cap(positions, cells, cap),
            v1._deterministic_cap(positions, _Labels(), cap)), cap


# --------------------------------------------------- the end-to-end fixture

@pytest.fixture(scope="module")
def page() -> dict:
    """One real page, described by BOTH trees, with real pixels.

    The printed field is minted through holo2's ``printed_cells_for`` and
    the certificates are v1 ``TileCertificateRecord``s over the same user
    bits, so v1's own ``CertificateFrontier`` re-encodes back to exactly
    this field — the agreement that ``test_oracle_certified_labels.py``
    already pins, reused here rather than re-asserted.
    """
    spec = h_resolve_format_ref(FORMAT)
    # ONE STRING, BOTH TREES: the tile grid used to be v1's own layout's
    # answer to a media size, and holo2's row was derived from it; now
    # the grid IS the identity and each tree resolves it for itself,
    # which is what makes the seed comparison below a comparison.
    fmt = tile_format_for(format_row_for(FORMAT))
    assert fmt.spec_id == spec.spec_id and fmt.seed == spec.seed
    cells_y, cells_x = fmt.cells_yx
    # ONE WINDOW, not the whole page: a real refine window is a couple of
    # hundred cells, and rendering a 12x12-tile page at 6 px/cell to
    # refine all of it would be 21 M pixels for no extra evidence. The
    # window sits at page cell (0, 0) and spans the four corner tiles.
    tiles = [(ty, tx) for ty in range(WINDOW_TILES_YX[0])
             for tx in range(WINDOW_TILES_YX[1])]
    span_y, span_x = WINDOW_TILES_YX[0] * 64, WINDOW_TILES_YX[1] * 64
    rng = np.random.default_rng(20260818)
    user_bits = {row: rng.integers(0, 2, fmt.tile_user_bits, dtype=np.uint8)
                 for row in tiles}
    field = np.zeros((cells_y, cells_x), np.uint8)
    for (ty, tx), bits in user_bits.items():
        field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = printed_cells_for(
            fmt, (0, ty, tx), bits)
    window_field = field[:span_y, :span_x]
    raw = np.kron(np.where(window_field.astype(bool), 40.0, 210.0),
                  np.ones((6, 6), np.float64))
    raw = ndimage.gaussian_filter(raw, sigma=1.6, mode="nearest")
    aperture = max(1, int(round(0.7 * PITCH_PX)))
    filtered = np.asarray(ndimage.uniform_filter(
        np.asarray(raw, np.float32), size=aperture, mode="nearest"),
        np.float32)
    #: The certified frontier: exactly the window's tiles, so the label
    #: population is real rather than total — the cells outside them are
    #: cargo nobody can label, which is the state RF1 actually fires in.
    sites = np.zeros((cells_y, cells_x), bool)
    sites[:span_y, :span_x] = True
    def _certificate(ty: int, tx: int, bits: np.ndarray
                     ) -> TileCertificateRecord:
        # v1 validates that a certificate NAMES its own content, so the id
        # is minted by v1's own identity function rather than invented.
        packed = np.packbits(bits, bitorder="little").tobytes()
        return TileCertificateRecord(
            certificate_id=stream_certificate_identity(
                spec, 0, (ty, tx), "main", packed),
            page=0, tile_yx=(ty, tx), packed_user_bits=packed,
            origin_attempt_id=hashlib.sha256(b"attempt").hexdigest())

    certificates = tuple(_certificate(ty, tx, bits)
                         for (ty, tx), bits in sorted(user_bits.items()))
    return {"spec": spec, "fmt": fmt, "field": field, "sites": sites,
            "filtered": filtered, "certificates": certificates,
            "span_yx": (span_y, span_x)}


#: The PAVA both trees score through, on holo2's ``-means`` scale.
CAL_KNOTS = np.asarray([-210.0, -160.0, -90.0, -40.0], np.float64)
CAL_PROBS = np.asarray([0.02, 0.10, 0.90, 0.98], np.float64)


def _v1_nodes(raw_means: np.ndarray) -> tuple[np.ndarray, float, float]:
    """The same calibration, restated on v1's normalised score scale.

    holo2 knot ``k`` names raw luma ``-k``; v1's score for that luma is
    ``(midpoint - (-k)) / spread``. Mapping the knots the same way the
    queries are mapped is what makes the two trees read one monotone
    function — see the module docstring.
    """
    midpoint = float(np.median(raw_means))
    spread = max(float(np.abs(raw_means - midpoint).mean()),
                 v1.SCORE_SPREAD_FLOOR)
    return (midpoint + CAL_KNOTS) / spread, midpoint, spread


def _wrong_affine() -> tuple[float, ...]:
    off = PITCH_PX * POSE_ERROR_CELLS
    return (PITCH_PX, 0.0, PITCH_PX / 2 + off, 0.0, PITCH_PX,
            PITCH_PX / 2 + off)


class _Enriched:
    """The reference field overlaid with the window's certified tiles."""

    def __init__(self, fmt, field, sites) -> None:
        self.spec = fmt
        self._field = field
        self._sites = sites

    def page(self, page: int) -> ReferencePage:
        return ReferencePage(page, self._field, self._sites)


def _frame(page: dict) -> FootingFrame:
    span_y, span_x = page["span_yx"]
    return FootingFrame.native((span_y * 6, span_x * 6))


def _window_cells(page: dict) -> np.ndarray:
    span_y, span_x = page["span_yx"]
    return np.stack(np.meshgrid(np.arange(span_y), np.arange(span_x),
                                indexing="ij"), axis=-1).reshape(-1, 2)


def _holo2_side(page: dict) -> tuple[RefineInput, refine.SegmentLabels]:
    cells = _window_cells(page)
    segment, local = refine.local_segment(_wrong_affine(), _frame(page), cells)
    means = refine.sample_at(page["filtered"], (0, 0), BACKING, segment.pose,
                             local)
    calibration = Calibration("oracle", CAL_KNOTS, CAL_PROBS, 400)
    labels = refine.collect_labels(
        0, cells, V1ReferenceField(page["fmt"]),
        _Enriched(page["fmt"], page["field"], page["sites"]))
    data = RefineInput(0, segment, local, cells, means, calibration,
                       page["filtered"], (0, 0), BACKING)
    return data, labels


def _v1_side(page: dict, means: np.ndarray):
    """v1's ``refine_segment`` inputs, built from the identical geometry."""
    span_y, span_x = page["span_yx"]
    cells = _window_cells(page)
    a, b, c, d, e, f = _wrong_affine()
    pose = V1AffinePose((c, f), ((a, b), (d, e)), (0.0, 0.0), PITCH_PX, 0.0)
    window = V1PoseWindow(0, 0, (0, 0), (span_y, span_x))
    segment = V1PoseSegment(window, pose, int(cells.shape[0]), 0.0,
                            (PITCH_PX, PITCH_PX), 0.0)
    placed = V1PlacedSegment(segment, (0, 0), 0, cells.astype(np.int32))
    image = v1.RefinementRegionImage(
        0, 0, 0, (span_y * 6, span_x * 6), page["filtered"], BACKING)
    raw = np.asarray(means, np.float32)
    nodes, midpoint, spread = _v1_nodes(raw)
    scores = ((np.float32(midpoint) - raw) / np.float32(spread)).astype(
        np.float32)
    llr = np.asarray(np.interp(scores.astype(np.float64), nodes, CAL_PROBS),
                     np.float64)
    llr = np.log(llr / (1.0 - llr)).astype(np.float32)
    reference = format_reference_values(page["spec"], 0, cells)
    evidence = V1WindowEvidence(
        source=EvidenceSource(hashlib.sha256(b"capture").hexdigest(),
                              "oracle-lane"),
        placement_id=hashlib.sha256(b"placement").hexdigest(),
        patch_id=0, region_id=hashlib.sha256(b"region").hexdigest(), page=0,
        redundant=False, segment_id=0,
        segment_local_cells_yx=cells.astype(np.int32),
        page_cells_yx=cells.astype(np.int32),
        scan_points_yx=pose.points(cells.astype(np.float64)),
        raw_means=raw, scores=scores,
        reference_values=np.asarray(reference, np.int8),
        calibration_score_nodes=nodes,
        calibration_probability_nodes=CAL_PROBS,
        baseline_printed_llr=llr, printed_llr=llr, accepted=True,
        refusal_reason="", n_search_0=200, n_search_1=200, n_heldout=200,
        heldout_logloss=0.1, detector_profile=PAVA_PROFILE)
    request = v1.SegmentRefinementRequest(placed, evidence)
    frontier = v1.CertificateFrontier.from_certificates(
        page["spec"], page["certificates"])
    return image, request, frontier


# --------------------------------------------------- pin (a4): end to end

def test_the_revised_affine_byte_compares_against_v1s_own_refine(page) -> None:
    """THE pin: one page, one pose error, both trees, the same new geometry.

    Both refines are handed the identical prepared plane, the identical
    committed pose and the identical certificate frontier, and both walk
    their own two-stage grid. What is compared is the thing that gets
    committed — the revised affine — as exact floats, plus the winning
    offsets that produced it.
    """
    data, labels = _holo2_side(page)
    mine = refine.propose(data, labels, _frame(page))
    assert mine.adopted, mine.reason
    image, request, frontier = _v1_side(page, data.baseline_means)
    theirs = v1.refine_segment(image, request, page["spec"], frontier)
    assert theirs.metrics.adopted, theirs.metrics.reason

    # The winning offsets first — where a tie-break or a clipping
    # difference would show up before the affine does.
    assert (mine.dtheta_deg, mine.du_cells, mine.dv_cells) == (
        theirs.metrics.dtheta_deg, theirs.metrics.du_cells,
        theirs.metrics.dv_cells)
    # And the geometry itself. holo2 commits a native page-cell affine
    # while v1 keeps a segment-local pose; the window's corner is page
    # cell (0, 0) here, so the two are the same six numbers.
    revised = theirs.refined_segment.pose
    assert mine.affine is not None
    assert mine.affine == (
        revised.jacobian_yx[0][0], revised.jacobian_yx[0][1],
        revised.origin_yx[0], revised.jacobian_yx[1][0],
        revised.jacobian_yx[1][1], revised.origin_yx[1])


def test_the_two_trees_walk_the_same_candidate_population(page) -> None:
    """Same grid, same dedup, same count — the search itself is carried."""
    data, labels = _holo2_side(page)
    mine = refine.propose(data, labels, _frame(page))
    image, request, frontier = _v1_side(page, data.baseline_means)
    theirs = v1.refine_segment(image, request, page["spec"], frontier)
    assert mine.candidates == theirs.metrics.candidates


def test_the_heldout_losses_agree_to_float32_round_off(page) -> None:
    """The calibrated half, at the precision the convention permits.

    v1 computes candidate scores in float32 (``_fixed_marginal_logits``
    casts); holo2 stays in float64. The two therefore agree to about
    1e-7, not to the bit, and the gap between adjacent grid keys is four
    orders of magnitude larger — which is why the winner above is exact
    even though these are not.
    """
    data, labels = _holo2_side(page)
    mine = refine.propose(data, labels, _frame(page))
    image, request, frontier = _v1_side(page, data.baseline_means)
    theirs = v1.refine_segment(image, request, page["spec"], frontier)
    assert mine.baseline_logloss is not None
    assert mine.candidate_logloss is not None
    assert mine.baseline_logloss == pytest.approx(
        theirs.metrics.baseline_validation_logloss, rel=1e-5)
    assert mine.candidate_logloss == pytest.approx(
        theirs.metrics.candidate_validation_logloss, rel=1e-5)


def test_the_two_trees_sample_the_identical_raw_luma(page) -> None:
    """The precondition everything above rests on, asserted on its own.

    holo2's sampler upcasts ``map_coordinates``' float32 output to
    float64 and v1 keeps it float32, so the VALUES must be identical and
    only the container differs. If this ever stopped holding, the winner
    comparison would become a coincidence rather than a consequence.
    """
    data, _labels = _holo2_side(page)
    image, request, _frontier = _v1_side(page, data.baseline_means)
    theirs = v1._sample(image, request.placed.segment.pose,
                        data.local_cells_yx)
    assert theirs.dtype == np.float32
    assert np.array_equal(np.asarray(theirs, np.float64), data.baseline_means)
