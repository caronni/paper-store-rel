"""F1's two ownership pins: v1's freeze key, and v1's ctx apply scope.

Rulings J2-1 and J2-2, "we implement v1" (2026-08-23). Each test names
the fork it prevents:

* **a contested cell owned by the worse-calibrated window** — holo2
  ordered freeze candidates by ``pose_id``, which is
  ``window_key + page + affine`` and therefore a fixed GEOMETRIC
  preference; on the e029/xerox gap tiles that handed about half the
  tile to a window reading it at up to 36% BER where the other read the
  same cells at 2% (``scratch/holo2-catchup/detect/DETECTION-GAP.md``
  §0/§3). The fork is any reintroduction of a geometric order — here,
  the piece with the LOWER pose id is the one with the WORSE held-out
  loss, so the two rules disagree on every contested cell;
* **a bin −1 cell that window-scoping reaches** — holo2 binned the
  assembled 64-cell component, so a tile's outer ring had no
  eight-neighbourhood and kept its uncorrected marginal (MEASURED 6.15%
  of cells against v1's 1.56-2.11%). The fork is a piece whose halo
  makes a border cell's neighbourhood complete and an apply that still
  leaves it at −1.

The blob-layout tests exist for a third fork the design leans on: F1
adds the halo WITHOUT bumping a record family, so a pre-F1 blob must
keep answering the tile-mask question byte for byte.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.core import FootingId, ResourceKey
from holo2.solve import (calibration, ctx_apply, detect, payload,
                         record_families)
from holo2.capture import region_key
from holo2.solve.records import (HALO_FRAME, HALO_RING_CELLS, OBSERVED_BYTES,
                                 PIECE_HALO_BYTES, PoseRecord, evidence_key,
                                 pack_observed_cells, pack_piece_observation,
                                 pose_collection_key, ring_masks,
                                 unpack_observed_cells, unpack_piece_halo,
                                 window_key)

TILE = 64
CAPTURE = "cd" * 32
FOOTING = FootingId("cap:1/1")
REGION = region_key(CAPTURE, (0, 0), 8, (256, 256))
WINDOW_LOW = window_key(FOOTING, REGION, (0, 0, 128, 128))
WINDOW_HIGH = window_key(FOOTING, REGION, (0, 0, 192, 192))
IDENTITY_AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _pose(window: ResourceKey) -> ResourceKey:
    return PoseRecord(window, FOOTING, 0, IDENTITY_AFFINE).resource_key()


def _piece(pose: ResourceKey, value: float, observed: np.ndarray,
           loss: float) -> payload._Piece:
    return payload._Piece(str(FOOTING), pose,
                          np.full((TILE, TILE), value, np.float64),
                          observed, loss)


# ---------------------------------------------- J2-1: who owns the cell

def test_a_contested_cell_goes_to_the_better_calibrated_window() -> None:
    """v1's key: ascending held-out loss, THEN the id — never the id alone.

    Both poses observe the left half of the tile; the pose that sorts
    FIRST by key (the numerically-smaller extent, holo2's pre-F1 order)
    is the badly-calibrated one. Under v1's rule the contested column
    reads the well-calibrated window's value.
    """
    low, high = _pose(WINDOW_LOW), _pose(WINDOW_HIGH)
    assert low < high, "the fixture's premise: the worse window sorts first"
    contested = np.zeros((TILE, TILE), bool)
    contested[:, :32] = True
    owner, owners, _bins = payload.RealPayloadWorker._freeze_with_owners([
        _piece(low, -1.0, contested, 0.42),
        _piece(high, +1.0, contested, 0.09)])
    assert np.all(owner.llr[:, :32] == +1.0), (
        "the contested cells must read the LOWER held-out loss's window")
    assert owners.keys() == {high}
    assert owner.pose_id == high, "the mint credits the ranked-first pose"


def test_equal_losses_fall_back_to_the_pose_id_tie_break() -> None:
    """The declared stand-in for v1's patch ordinal (which holo2 has not).

    Ties — including the "no pool has published a loss yet" case, where
    every piece carries ``inf`` — keep the content-derived pose order, so
    the freeze stays total and run-independent.
    """
    low, high = _pose(WINDOW_LOW), _pose(WINDOW_HIGH)
    contested = np.ones((TILE, TILE), bool)
    for loss in (0.25, float("inf")):
        owner, owners, _bins = payload.RealPayloadWorker._freeze_with_owners([
            _piece(high, +1.0, contested, loss),
            _piece(low, -1.0, contested, loss)])
        assert owner.pose_id == low
        assert owners.keys() == {low}


def test_ownership_reads_no_payload_cell_value() -> None:
    """F-09 survives F1, stated precisely (renamed on review 2026-08-23).

    Scaling one piece's LLRs by ten — the evidence's own value at the
    contested cells — cannot move a single cell of ownership; only the
    published window loss can. That is the per-cell property, and it is
    all this arm can pin: the ranking statistic IS a statistic of the
    evidence, just at sites whose values the FORMAT fixes. The half that
    matters and that this test cannot see — that the loss never widens to
    payload cells — is pinned on the harvest itself, in
    ``test_calibration.py`` ``test_the_ranking_statistic_reads_only_
    format_fixed_sites``.
    """
    low, high = _pose(WINDOW_LOW), _pose(WINDOW_HIGH)
    mask = np.ones((TILE, TILE), bool)
    quiet = payload.RealPayloadWorker._freeze_with_owners([
        _piece(low, -1.0, mask, 0.4), _piece(high, +1.0, mask, 0.2)])
    loud = payload.RealPayloadWorker._freeze_with_owners([
        _piece(low, -10.0, mask, 0.4), _piece(high, +0.1, mask, 0.2)])
    assert quiet[1].keys() == loud[1].keys() == {high}


# ------------------------------------------- J2-2: what the bins are of

def _halo_piece() -> tuple[np.ndarray, np.ndarray,
                           tuple[np.ndarray, np.ndarray]]:
    """A fully observed tile plus a halo whose ring is all present ink."""
    rng = np.random.default_rng(11)
    ink = rng.random((TILE, TILE)) < 0.5
    llr = np.where(ink, 1.5, -1.5)
    observed = np.ones((TILE, TILE), bool)
    present = np.ones((HALO_FRAME, HALO_FRAME), bool)
    ring_ink = np.ones((HALO_FRAME, HALO_FRAME), bool)
    return llr, observed, (present, ring_ink)


def test_a_bin_minus_one_border_cell_is_reached_by_window_scoping() -> None:
    """The 252-cell ring stops being structurally invalid.

    Tile-scoped, every cell of the outer ring has an incomplete
    eight-neighbourhood and is bin −1 by construction; with the pose's
    own halo the same cells bin like any interior cell, which is what v1
    has because v1 corrects the whole window.
    """
    llr, observed, halo = _halo_piece()
    ys, xs = np.nonzero(observed)
    counts, valid = detect.context_neighbour_counts(
        np.stack((ys, xs), axis=1).astype(np.int64), llr[observed] > 0.0)
    tile_bins = np.full(llr.shape, -1, np.int8)
    tile_bins[observed] = detect.context_bins(counts, valid=valid)
    window_bins = ctx_apply.window_context_bins(llr, observed, halo)

    ring = np.ones(llr.shape, bool)
    ring[1:-1, 1:-1] = False
    assert np.all(tile_bins[ring] == -1), "the pre-F1 floor, restated"
    assert np.all(window_bins[ring] >= 0), "every ring cell now bins"
    assert int(np.count_nonzero(ring)) == 4 * TILE - 4 == 252
    assert np.array_equal(tile_bins[1:-1, 1:-1], window_bins[1:-1, 1:-1]), (
        "the interior's neighbourhood never depended on the halo")

    offsets = np.arange(9, dtype=np.float64) * 0.1 - 0.4
    mask = np.ones(llr.shape, bool)
    corrected = ctx_apply.apply_component_context(
        llr, observed, ((mask, offsets),), window_bins)
    uncorrected = ctx_apply.apply_component_context(
        llr, observed, ((mask, offsets),), tile_bins)
    assert not np.array_equal(corrected[ring], uncorrected[ring])
    assert np.array_equal(uncorrected[ring], llr[ring]), (
        "tile-scoped, the ring keeps its marginal — the fork this pins")


def test_a_window_edge_cell_stays_bin_minus_one() -> None:
    """v1's own answer where the WINDOW ends, not the tile.

    A ring the pose never covered is absent, so the tile cells beside it
    are still invalid — the halo restores v1's scope, it does not invent
    neighbours.
    """
    llr, observed, (present, ink) = _halo_piece()
    present = present.copy()
    present[0, :] = False                      # the window ends above us
    bins = ctx_apply.window_context_bins(llr, observed, (present, ink))
    assert np.all(bins[0, :] == -1)
    assert np.all(bins[1:-1, 1:-1] >= 0)


def test_a_piece_without_a_halo_takes_the_tile_scoped_bins() -> None:
    """Pre-F1 evidence decodes exactly as it did — one component, one
    scope. A mixed component would correct half its cells in one frame
    and half in another, which is neither tree's rule."""
    low, high = _pose(WINDOW_LOW), _pose(WINDOW_HIGH)
    left = np.zeros((TILE, TILE), bool)
    left[:, :32] = True
    right = ~left
    _llr, _observed, halo = _halo_piece()
    llr = np.zeros((TILE, TILE), np.float64)

    both = payload.RealPayloadWorker._freeze_with_owners([
        payload._Piece(str(FOOTING), high, llr, left, 0.2, halo),
        payload._Piece(str(FOOTING), low, llr, right, 0.4, halo)])
    assert both[2] is not None, "two haloed pieces make a haloed component"

    mixed = payload.RealPayloadWorker._freeze_with_owners([
        payload._Piece(str(FOOTING), high, llr, left, 0.2, halo),
        _piece(low, -1.0, right, 0.4)])
    assert mixed[2] is None, (
        "a bare piece that OWNS cells takes the whole component back to "
        "the tile-scoped derivation — never half of each scope")

    ignored = payload.RealPayloadWorker._freeze_with_owners([
        payload._Piece(str(FOOTING), high, llr, np.ones((TILE, TILE), bool),
                       0.2, halo),
        _piece(low, -1.0, right, 0.4)])
    assert ignored[2] is not None, (
        "a bare piece that owns NOTHING cannot force the fallback")


def test_a_piece_that_owns_nothing_never_derives_its_bins(
        monkeypatch) -> None:
    """The derivation follows OWNERSHIP (review fix, 2026-08-23).

    ``_pieces`` used to derive the window bins of every piece an attempt
    loads, but the freeze skips any piece that owns no cell — MEASURED
    30.9% of piece loads on the archived e029 store. ``_Piece.bins``
    derives at first read and the freeze reads it only after
    ``take.any()``, so an idle piece costs nothing. The fork this
    prevents: hoisting the derivation back out of the loop, where a third
    of it is waste that grows with every extra covering window.
    """
    calls: list[int] = []
    real = ctx_apply.window_context_bins

    def counted(llr: np.ndarray, observed: np.ndarray,
                halo: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        calls.append(1)
        return real(llr, observed, halo)

    monkeypatch.setattr(ctx_apply, "window_context_bins", counted)
    low, high = _pose(WINDOW_LOW), _pose(WINDOW_HIGH)
    llr, observed, halo = _halo_piece()
    owner, owners, bins = payload.RealPayloadWorker._freeze_with_owners([
        payload._Piece(str(FOOTING), high, llr, observed, 0.2, halo),
        payload._Piece(str(FOOTING), low, llr, observed, 0.4, halo)])
    assert owners.keys() == {high}, "the first-ranked piece owns everything"
    assert len(calls) == 1, "only the OWNING piece derived its bins"
    assert bins is not None
    assert np.array_equal(bins, real(llr, observed, halo))


# ------------------------------------------------ the blob's own layout

def test_the_halo_blob_keeps_the_tile_mask_answer_byte_for_byte() -> None:
    """The reason no record family bumps: leading-bit compatibility.

    Every existing reader asks ``unpack_observed_cells(packed, (64, 64))``
    and must get the same mask from either layout — which is what lets
    the archived states F1 is measured on stay open.
    """
    rng = np.random.default_rng(3)
    observed = rng.random((TILE, TILE)) < 0.7
    ring_present = rng.random(HALO_RING_CELLS) < 0.6
    ring_ink = rng.random(HALO_RING_CELLS) < 0.4

    legacy = pack_observed_cells(observed)
    haloed = pack_piece_observation(observed, ring_present, ring_ink)
    assert legacy.size == OBSERVED_BYTES == 512
    assert haloed.size == PIECE_HALO_BYTES == 577
    assert np.array_equal(unpack_observed_cells(legacy, (TILE, TILE)),
                          unpack_observed_cells(haloed, (TILE, TILE)))
    assert unpack_piece_halo(legacy) is None, "a pre-F1 blob has no halo"

    present, ink = unpack_piece_halo(haloed)
    assert present.shape == ink.shape == (HALO_FRAME, HALO_FRAME)
    assert not present[1:-1, 1:-1].any(), "the interior is the piece's own"
    frame = np.zeros((HALO_FRAME, HALO_FRAME), bool)
    frame[0, :] = frame[-1, :] = frame[:, 0] = frame[:, -1] = True
    assert np.array_equal(present[frame], ring_present)
    assert np.array_equal(ink[frame], ring_ink)


def test_ring_masks_reads_the_window_and_stops_at_its_edge() -> None:
    """A placement's own arrays are the whole source of a tile's ring."""
    observed = np.ones((TILE + 8, TILE + 8), bool)
    ink = np.zeros_like(observed)
    ink[:, :] = True
    present, ring_ink = ring_masks(observed, ink, (0, 0), 0, 0)
    frame = np.zeros((HALO_FRAME, HALO_FRAME), bool)
    frame[0, :] = frame[-1, :] = frame[:, 0] = frame[:, -1] = True
    expanded = np.zeros((HALO_FRAME, HALO_FRAME), bool)
    expanded[frame] = present
    assert not expanded[0, :].any(), "page row -1 is off the sheet"
    assert not expanded[:, 0].any(), "page column -1 is off the sheet"
    assert expanded[-1, 1:-1].all(), "the row below the tile IS covered"


# -------------------------------------------- the published window loss

def test_a_pre_f1_params_blob_publishes_no_window_loss() -> None:
    """The other half of "no family bumps": an old fit still reads."""
    params = np.zeros(calibration.PARAM_LENGTH, np.float64)
    assert calibration.published_losses(params) == {}
    with pytest.raises(ValueError, match="malformed ctx params blob"):
        calibration.published_losses(np.zeros(
            calibration.PARAM_LENGTH + 2, np.float64))


def test_window_losses_round_trip_through_the_params_blob() -> None:
    """What the freeze reads is what the fit wrote, per member window."""
    low, high = _pose(WINDOW_LOW), _pose(WINDOW_HIGH)
    losses = {low: 0.42, high: 0.09}
    body = calibration._member_loss_params(losses)
    params = np.concatenate(
        (np.zeros(calibration.PARAM_LENGTH, np.float64), body))
    published = calibration.published_losses(params)
    assert published[calibration.member_digest(low)] == 0.42
    assert published[calibration.member_digest(high)] == 0.09
    fit = ctx_apply.AdoptedContextFit(
        low, np.zeros(9, np.float64), published)
    assert fit.loss_of(high) == 0.09
    assert fit.loss_of(_pose(window_key(
        FOOTING, REGION, (0, 0, 64, 64)))) is None


def test_the_corrected_window_loss_is_the_number_v1_ranks_by() -> None:
    """v1 OVERWRITES the window's loss on adoption; so does this.

    ``member_window_losses`` with offsets measures the corrected window,
    without them the marginal one — the two numbers v1 spells at
    ``_payload_context.py:290-294`` and ``_payload_sampling.py:384-388``.
    """
    pose = _pose(WINDOW_LOW)
    marginal = np.asarray([-0.5, 0.5, -0.5, 0.5], np.float64)
    bins = np.asarray([0, 1, -1, 2], np.int8)
    labels = np.asarray([True, True, False, True])
    member = calibration._MemberHeldout(pose, marginal, bins, labels)
    offsets = np.zeros(9, np.float64)
    offsets[:3] = (3.0, 3.0, 3.0)

    bare = calibration.member_window_losses([member], None)[pose]
    fitted = calibration.member_window_losses([member], offsets)[pose]
    assert bare == calibration.binary_logloss(marginal, labels)
    assert fitted < bare, "the correction helps where the labels say so"
    corrected = detect.apply_context_offsets(marginal, bins, offsets)
    assert corrected[2] == marginal[2], "bin -1 is untouched, as v1 leaves it"
    assert fitted == calibration.binary_logloss(corrected, labels)


# ------------------------------------------------------ J2-3: the wake

def test_the_payload_attempt_subscribes_to_its_windows_pose_collection(
) -> None:
    """The supersede wake, at the one place it is a key question.

    A revision writes a new ``PoseRecord`` and joins its window's pose
    collection; a payload attempt names that same collection, derived
    from its pieces' keys alone. So the revision moves the attempt's
    read-set version, the standing attempt goes stale, and the window's
    uncertified tiles act again at their turn.
    """
    pose = PoseRecord(WINDOW_LOW, FOOTING, 0, IDENTITY_AFFINE)
    piece = evidence_key(FOOTING, 0, 3, 5, "main", pose.resource_key())
    assert payload.evidence_window(piece) == WINDOW_LOW

    (family,) = [entry for entry in record_families(page_domain=())
                 if entry.record_type is PoseRecord]
    joined = family.collections(pose.resource_key(), pose)
    assert pose_collection_key(payload.evidence_window(piece)) in joined
    assert "collection:poses-window" in payload.RealPayloadProvider.sources
