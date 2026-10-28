"""F2a's re-read arithmetic: the page-oriented placement it hands the block.

Ruling J2-3 (2026-08-23). ``resample.resample_window`` samples a placed
window's own cells through its LIVE pose and hands the result to the
ORDINARY emission block, which is what gives the re-read v1's fresh
calibration (``_payload_reuse:311-322``) and F1's context halo for free.
Two things about that hand-off are easy to get wrong silently, so they
are pinned here:

* **the rotation convention.** The block takes a placement in the
  SAMPLER's frame plus the ``rot_k`` that lays it on the sheet, and
  composes the two immediately. The re-read has the composition already —
  its cells came back from pieces keyed by PAGE tile — so it declares the
  identity rotation over page-oriented arrays. The fork: "rot_k is just
  0 because we do not know it", which would silently transpose or mirror
  every re-read on a rot90 capture (the Xerox sheet is one);
* **the pilot firewall.** v1's committed poses *"never re-enter the
  firewall word pool"* (``place._committed_patch``), because the W5
  known-position reduce adjudicates a placement being ACCEPTED and a
  re-read accepts nothing. The fork: carrying a sample into the block and
  quarantining a geometry the tree already committed.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.capture import region_key
from holo2.core import FootingId, ResourceKey
from holo2.core.blobs import stage_bytes
from holo2.format import TILE_CELLS
from holo2.solve.place_shared import FootingFrame
from holo2.solve.quarantine import word_verdict
from holo2.solve.records import (EvidenceObservation, PoseRecord,
                                 evidence_key, pack_observed_cells, pose_key,
                                 window_key)
from holo2.solve.refine_fit import local_segment, sample_at
from holo2.solve.resample import _page_placement, superseded_generation

CALIBRATION = ResourceKey("calibration", ("x",))
_BLOB = stage_bytes(b"observed cells")

AFFINE = (6.0, 0.0, 1.0, 0.0, 6.0, 2.0)


def _cells(rows: tuple[tuple[int, int], ...]) -> np.ndarray:
    return np.asarray(rows, np.int64)


def test_the_placement_is_the_page_frame_itself() -> None:
    """Identity rotation over absolute page cells, spanning their bbox.

    ``page_origin_yx`` is the bbox corner and every observed cell lands
    at its own page coordinate minus that corner — which is exactly what
    ``emit_placement``'s ``np.rot90(scores, rot_k)`` and
    ``fragment_reference_sites(..., rot_k)`` compute when ``rot_k`` is 0.
    """
    cells = _cells(((70, 5), (70, 6), (72, 5)))
    placement = _page_placement(3, AFFINE, cells, np.array([0.25, 0.5, 0.75]))
    assert placement.page == 3 and placement.rot_k == 0
    assert placement.page_origin_yx == (70, 5)
    assert placement.observed.shape == (3, 2)
    assert placement.observed.tolist() == [[True, True],
                                           [False, False],
                                           [True, False]]
    assert np.rot90(placement.scores, placement.rot_k) is not None
    assert placement.affine == AFFINE, (
        "the emission's pose and the placement's geometry are one answer")


def test_the_scores_are_negated_luma() -> None:
    """``place_shared``'s own polarity: larger means MORE ink.

    The monotone PAVA map and the tile chain both require it, and the
    re-read must not invent a second convention — a sign flip here would
    calibrate every re-read window inside out and read ink as paper.
    """
    cells = _cells(((0, 0), (0, 1)))
    placement = _page_placement(0, AFFINE, cells, np.array([0.2, 0.9]))
    assert placement.scores[0, 0] == -0.2 and placement.scores[0, 1] == -0.9


def test_an_unobserved_cell_of_the_box_is_absent_not_zero_ink() -> None:
    """The bbox is a span, not a claim: only the cells sampled are seen.

    The tile slicing and the F1 halo both read "absent" off the observed
    mask, so a hole in the box behaves exactly as a cell off the box's
    edge — which is why spanning the bbox rather than the window's full
    extent changes neither the pieces nor their context rings.
    """
    cells = _cells(((0, 0), (1, 1)))
    placement = _page_placement(0, AFFINE, cells, np.array([0.1, 0.2]))
    assert placement.observed.tolist() == [[True, False], [False, True]]
    assert placement.scores[0, 1] == 0.0 and not placement.observed[0, 1]


def test_the_re_read_carries_no_sample_so_the_firewall_stays_shut(
) -> None:
    """v1's rule, and the one line of the block that reads it.

    ``word_verdict`` returns an EMPTY verdict for a placement with no
    sample, so the emission proceeds to its pieces without harvesting a
    single pilot read — no reduce, no contradiction, no quarantine.
    """
    placement = _page_placement(0, AFFINE, _cells(((0, 0),)),
                                np.array([0.5]))
    assert placement.sample is None
    assert not word_verdict(
        None, pose=None, provider=None, stream="main", capture_id="x",
        sample=placement.sample, observed=placement.observed, page=0,
        page_origin_yx=placement.page_origin_yx, rot_k=placement.rot_k)


# ------------------------------------------------ the sampling chain itself

#: A native footing frame and a synthetic plane, the ``test_refine`` shape:
#: pitch 6 native px per cell, a cell's sample point is its own centre.
FRAME = FootingFrame.native((240, 240))
PITCH_PX = 6.0
LIVE_AFFINE = (PITCH_PX, 0.0, PITCH_PX / 2, 0.0, PITCH_PX, PITCH_PX / 2)
BACKING = 0.5
#: A plane whose value IS its coordinate pair, so a sampled mean names the
#: pixel it was read at and a drift of one pixel is visible in the number.
FILTERED = (np.arange(240, dtype=np.float64)[:, None] * 1000.0
            + np.arange(240, dtype=np.float64)[None, :])
#: Deliberately scattered and NOT the bbox: the re-read's cells come back
#: from the superseded pieces, so holes in the box are the normal case and
#: the cell -> mean correspondence must survive them.
CELLS = _cells(((3, 4), (3, 9), (7, 4), (11, 6), (11, 9)))


def test_the_re_read_reads_each_cell_at_its_live_pose_s_own_pixel() -> None:
    """The load-bearing arithmetic, end to end (review fix, 2026-08-23).

    ``local_segment`` restates the durable native affine in the rung's
    pixels and re-origins it at the CELL SET's corner; ``_page_placement``
    re-origins the same cells at the same corner. Nothing states that the
    two agree — they agree because both take ``cells.min(axis=0)`` — so
    the fork this pins is a silent origin, frame or ordering drift
    between them, which would scramble which mean lands on which cell
    without changing a single shape.

    The plane's value is its own coordinate, so the assertion is literal:
    the mean stored for page cell (y, x) is the pixel the LIVE affine
    predicts for that cell, and nothing else.
    """
    segment, local = local_segment(LIVE_AFFINE, FRAME, CELLS)
    means = sample_at(FILTERED, (0, 0), BACKING, segment.pose, local)
    placement = _page_placement(0, LIVE_AFFINE, CELLS, means)
    origin = np.asarray(placement.page_origin_yx)
    for (cy, cx), mean in zip(CELLS.tolist(), means.tolist()):
        py = PITCH_PX * cy + PITCH_PX / 2
        px = PITCH_PX * cx + PITCH_PX / 2
        assert mean == pytest.approx(py * 1000.0 + px), (
            f"cell ({cy}, {cx}) was not read at its own pose's pixel")
        stored = placement.scores[cy - origin[0], cx - origin[1]]
        assert stored == pytest.approx(-mean), (
            "the cell -> mean correspondence drifted between "
            "local_segment and _page_placement")
        assert placement.observed[cy - origin[0], cx - origin[1]]


def test_moving_the_pose_moves_every_sampled_pixel_by_the_same_delta(
) -> None:
    """The re-read IS the geometry experiment, so this is its signature.

    A pure translation of the live affine must move every sampled point
    by exactly that translation and change nothing else — no re-origin,
    no re-ordering, no aperture change. The fork: composing the delta
    into the local frame twice (or not at all), which would leave the
    re-read sampling the SUPERSEDED geometry while reporting the live
    pose id on every piece it emits.
    """
    delta = (1.0, 0.5)
    moved = (LIVE_AFFINE[0], LIVE_AFFINE[1], LIVE_AFFINE[2] + delta[0],
             LIVE_AFFINE[3], LIVE_AFFINE[4], LIVE_AFFINE[5] + delta[1])
    base, local = local_segment(LIVE_AFFINE, FRAME, CELLS)
    other, local_moved = local_segment(moved, FRAME, CELLS)
    assert local.tolist() == local_moved.tolist(), "the local frame moved"
    points = base.pose.points(local.astype(np.float64))
    shifted = other.pose.points(local_moved.astype(np.float64))
    assert np.allclose(shifted - points, np.asarray(delta)), (
        "a pose translation did not reach the sampler one-for-one")


# --------------------------------------------- W5, at the fire's own filter

FOOTING = FootingId("cap:1/1")
REGION = region_key("ab" * 32, (0, 0), 8, (240, 240))
WINDOW = window_key(FOOTING, REGION, (0, 0, 160, 160))
PARENT_AFFINE = LIVE_AFFINE
REVISED_AFFINE = (PITCH_PX, 0.0, PITCH_PX / 2 + 0.25,
                  0.0, PITCH_PX, PITCH_PX / 2)
PARENT = pose_key(WINDOW, 0, PARENT_AFFINE)
LIVE = pose_key(WINDOW, 0, REVISED_AFFINE)
PIECE = evidence_key(FOOTING, 0, 0, 0, "main", PARENT)
_PACKED = pack_observed_cells(
    np.eye(TILE_CELLS, dtype=bool))


class _Index:
    """The three index fields ``superseded_generation`` reads."""

    def __init__(self, poses: dict) -> None:
        self.poses = poses
        self.poses_by_window = {WINDOW: (PARENT, LIVE)}
        self.evidence_by_pose = {PARENT: (PIECE,)}


class _View:
    """A plane answering the four calls the grouping makes."""

    def __init__(self, condemned_parent: bool) -> None:
        parent = PoseRecord(window_id=WINDOW, footing_id=FOOTING, page=0,
                            native_affine=PARENT_AFFINE,
                            quarantined=condemned_parent)
        live = PoseRecord(window_id=WINDOW, footing_id=FOOTING, page=0,
                          native_affine=REVISED_AFFINE)
        self._index = _Index({PARENT: parent, LIVE: live})
        self._piece = EvidenceObservation(
            footing_id=FOOTING, page=0, ty=0, tx=0, stream="main",
            pose_id=PARENT, llr_ref=_BLOB.ref, observed_ref=_BLOB.ref,
            calibration_id=CALIBRATION, quarantined=condemned_parent)

    def index(self) -> _Index:
        return self._index

    def record(self, key: ResourceKey) -> object:
        return self._piece if key == PIECE else self._index.poses.get(key)

    def read_array(self, ref: object) -> np.ndarray:
        return _PACKED


def test_a_condemned_generation_is_never_the_one_a_re_read_replaces(
) -> None:
    """W5's law inside the fire, beside the one at the door.

    ``quarantine_writes`` marks the pose AND every piece, so the filter
    asks both and a condemned generation answers ``nothing_superseded``
    rather than handing its cells to a fresh, UNQUARANTINED emission at
    the live pose. The fork is the rehabilitation ``quarantine``'s header
    forbids: *"never rehabilitated … recovery is fresh-evidence-only
    (L8)"* — reachable because W5 reaches poses only through their
    pieces, so a revision committed before a contradiction is never
    marked and stands live above a condemned parent.

    The control below is the point of the pin: the SAME stub with the
    marking cleared does find the generation, so what refuses is the
    filter and not the double.
    """
    assert superseded_generation(_View(True), WINDOW, LIVE) is None
    found = superseded_generation(_View(False), WINDOW, LIVE)
    assert found is not None and found.pose_id == PARENT
    assert found.cells.shape == (TILE_CELLS, 2)
