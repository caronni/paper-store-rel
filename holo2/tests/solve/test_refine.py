"""H5 P4's plumbing pins: RF1's bounded, certificate-labeled revision.

The refine ARITHMETIC is byte-compared against ``src/holo``'s own
``certified_refine`` in ``tests/holo2_oracles/test_oracle_refine.py``
(pin (a)); what is pinned HERE is everything holo2 added around it, in
the style H5 P1 set — durable records over a real store, real pixels
through the real sampler, and the fire's own verdicts:

* **pin (b)** — the bounds are structural: every candidate the two-stage
  grid can propose lies inside +-0.15 deg and +-0.25 cell, tested AT the
  boundary, and the fine stage's re-clipping is what makes it so;
* **pin (c)** — the held-out gain gate and BOTH pilot non-regression
  gates, adopt arm and refuse arm, with the refusal committing its
  reason;
* **pin (d)** — eligibility: a fully-certified reach mints NOTHING, one
  uncertified tile in reach mints exactly one descriptor, and a new
  certificate re-arms it (the frontier version is in the read-set);
* **pin (e)** — done is inviolable: an adopted revision writes ONE
  ``PoseRecord`` at a NEW key and touches no tile, no evidence and no
  certificate; the old pose stands.

THE FIXTURE is a real printed page, not a drawing of one. A (2, 2)-tile
c2 page is built from certified user bits through ``tiles.printed_cells_
for``, rendered at 6 px/cell, and box-filtered exactly as
``pose_fit.prepare_region`` filters a real region — so the labels, the
pixels and the certificates are all the same page, and a pose error is
the only thing the refine can be reacting to. The COMMITTED pose is
deliberately wrong by a sub-cell offset well inside the bounds; the TRUE
pose is what the grid should walk toward.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import numpy as np
from scipy import ndimage

from holo2.capture import (CaptureRecord, FootingSpec, RegionRecord,
                           capture_key, region_key)
from holo2.capture.footing_raster import FootingFrame
from holo2.core import FootingId, ProgressSink, ResourceKey
from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.core import ExpansionRequest
from holo2.solve import refine
from holo2.solve.certified_labels import CertifiedLabelSource
from holo2.solve.detect import Calibration
from holo2.solve.keys import COLLECTION_CERTIFIED
from holo2.solve.place_model import PlacementConfig
from holo2.solve.pose_fit import PreparedRegion
from holo2.solve.records import (CalibrationRecord, EvidenceObservation,
                                 HeldoutGate, MintRef, PoseRecord, TileRecord,
                                 WindowRecord, WindowStatus, calibration_key,
                                 evidence_key, pack_observed_cells, tile_key,
                                 window_key)
from holo2.solve.refine import (PoseRefineProvider, PoseRefineWorker, Reach,
                                RefineInput)
from holo2.solve.reference import V1ReferenceField
from holo2.solve.tiles import printed_cells_for
from holo2.solve.tilemap import StoreIndex, TileMap
from holo2.format.format_v1 import tile_format
from holo2.format.registry_rows import format_row

SPEC = tile_format("c2-k-r0550", (2, 2))
REFERENCE = V1ReferenceField(SPEC)
STREAM = "main"
TILE = 64
TILES = ((0, 0), (0, 1), (1, 0), (1, 1))
CELLS_Y, CELLS_X = SPEC.cells_yx

CAPTURE = "ab" * 32
FOOTING = FootingId("cap:1/1")
REGION = region_key(CAPTURE, (0, 0), 8, (CELLS_Y * 6, CELLS_X * 6))
FRAME = FootingFrame.native((CELLS_Y * 6, CELLS_X * 6))

#: THE GEOMETRY. Pitch 6 native px per cell; a cell's sample point is its
#: own centre, so cell (0, 0) reads pixel (3, 3) and the true affine is a
#: pure scale-plus-half-cell translation.
PITCH_PX = 6.0
TRUE_AFFINE = (PITCH_PX, 0.0, PITCH_PX / 2, 0.0, PITCH_PX, PITCH_PX / 2)

#: THE COMMITTED (wrong) pose: 0.14 cell of translation on each axis,
#: comfortably inside the +-0.25-cell bound, so the true correction is
#: reachable and the grid has a real optimum to find.
POSE_ERROR_CELLS = 0.14
WRONG_AFFINE = (PITCH_PX, 0.0, PITCH_PX / 2 + PITCH_PX * POSE_ERROR_CELLS,
                0.0, PITCH_PX, PITCH_PX / 2 + PITCH_PX * POSE_ERROR_CELLS)

WINDOW = window_key(FOOTING, REGION, (0, 0, CELLS_Y, CELLS_X))
POSE = PoseRecord(WINDOW, FOOTING, 0, WRONG_AFFINE)
TRUE_POSE = PoseRecord(WINDOW, FOOTING, 0, TRUE_AFFINE)

_RNG = np.random.default_rng(11)
USER_BITS = {(ty, tx): _RNG.integers(0, 2, SPEC.tile_user_bits, dtype=np.uint8)
             for ty, tx in TILES}
PRINTED = {(ty, tx): printed_cells_for(SPEC, (0, ty, tx), USER_BITS[(ty, tx)])
           for ty, tx in TILES}


def _page_cells() -> np.ndarray:
    """The whole page's printed field, tile by tile."""
    page = np.zeros((CELLS_Y, CELLS_X), np.uint8)
    for (ty, tx), cells in PRINTED.items():
        page[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = cells
    return page


PAGE_CELLS = _page_cells()


def _render() -> tuple[np.ndarray, np.ndarray]:
    """The page as pixels, and the one box aperture a prepared plane holds.

    Ink is dark and paper is light (raw luma, the polarity every score in
    the tree is taken on), and the aperture is ``round(0.7 * pitch)`` —
    ``pose_fit.prepare_region``'s own, so a candidate here is sampled
    through exactly what production samples through.

    THE OPTICAL BLUR IS NOT DECORATION. Rendered as hard 6x6 blocks, the
    page has a FLAT PLATEAU across the middle of every cell — a 0.7-cell
    box aperture centred anywhere within +-1 px reads exactly the same
    number — so no sub-cell pose error is observable and every candidate
    inside the plateau ties on contrast (measured: identical to all
    printed digits at -0.25, -0.14, -0.125 and 0.0). A real capture is
    band-limited by the scanner's MTF, which is precisely what makes a
    fraction of a cell recoverable at all; sigma here is 1.6 px against a
    6 px cell, comfortably inside the Canon knife-edge's measured
    ~860-dpi information ceiling and enough to give the objective a real
    gradient. Without it this fixture would pin a refinement that cannot
    see, and the adopt arm would be vacuous.
    """
    raw = np.kron(np.where(PAGE_CELLS.astype(bool), 40.0, 210.0),
                  np.ones((6, 6), np.float64))
    raw = np.asarray(ndimage.gaussian_filter(raw, sigma=1.6, mode="nearest"),
                     np.float32)
    aperture = max(1, int(round(0.7 * PITCH_PX)))
    return raw, np.asarray(
        ndimage.uniform_filter(raw, size=aperture, mode="nearest"), np.float32)


RAW, FILTERED = _render()
BACKING = 210.0
PREPARED = PreparedRegion(0, 0, 0, RAW, FILTERED,
                          np.ones_like(RAW, np.float32), BACKING,
                          PITCH_PX, max(1, int(round(0.7 * PITCH_PX))))

#: A PAVA on the ``-means`` scale holo2 calibrates on (place_shared:596):
#: dark ink reads about -40, light paper about -210, so a monotone map
#: from that scale to P(ink) is the whole generation-zero calibration.
CAL_KNOTS = np.asarray([-210.0, -160.0, -90.0, -40.0], np.float64)
CAL_PROBS = np.asarray([0.02, 0.10, 0.90, 0.98], np.float64)
CAL_PARAMS = stage_array(np.stack([CAL_KNOTS, CAL_PROBS]))
SUPPORT_MASK = stage_array(np.ones(16, np.uint8))


def _calibration_key(window: ResourceKey = WINDOW) -> ResourceKey:
    return calibration_key(window, "pava-v1", CAL_PARAMS.ref.sha256)


def _ground() -> list[Write]:
    return [
        Write(capture_key(CAPTURE), CaptureRecord(
            source_sha256=CAPTURE, dpi_true=1200.0,
            shape_px=(CELLS_Y * 6, CELLS_X * 6), dtype="uint8", channels=1,
            platen_backing=BACKING,
            footings=(FootingSpec(FOOTING, Fraction(1), CAPTURE),))),
        Write(REGION, RegionRecord(
            capture_sha256=CAPTURE, support_mask_ref=SUPPORT_MASK.ref,
            pitch_in_vote=Fraction(8, 600), support_origin_px=(0, 0), support_step_px=8,
            support_extent_px=(CELLS_Y * 6, CELLS_X * 6))),
        Write(_calibration_key(), CalibrationRecord(
            scope=WINDOW, algorithm="pava-v1", params_ref=CAL_PARAMS.ref,
            heldout=HeldoutGate(adopted=True, logloss_delta=-0.4))),
    ]


def _placement(pose: PoseRecord = POSE, *, band_cells: int = 0
               ) -> tuple[list[Write], list]:
    """One committed placement: window, pose, and a piece per tile.

    ``band_cells`` narrows what the pose OBSERVED to a square of that
    many cells in each tile's corner. It exists for the starvation pin: a
    pose that saw a whole 64x64 tile clears v1's cargo floors many times
    over (4096 cells against a floor of 64), so the only way to reach
    ``insufficient_payload_train`` through the real fire is a placement
    that genuinely observed very little — a clipped edge window, which is
    exactly the population the floor is there for.
    """
    writes: list[Write] = [
        Write(pose.window_id, WindowRecord(pose.footing_id, REGION,
                                           (0, 0, CELLS_Y, CELLS_X),
                                           WindowStatus.ACTIVE)),
        Write(pose.resource_key(), pose),
    ]
    blobs = []
    seen = np.zeros((TILE, TILE), bool)
    if band_cells:
        seen[:band_cells, :band_cells] = True
    else:
        seen[:, :] = True
    mask = stage_array(pack_observed_cells(seen))
    blobs.append(mask)
    for ty, tx in TILES:
        llr = stage_array(np.zeros((TILE, TILE), np.float32))
        blobs.append(llr)
        writes.append(Write(
            evidence_key(pose.footing_id, 0, ty, tx, STREAM,
                         pose.resource_key()),
            EvidenceObservation(
                footing_id=pose.footing_id, page=0, ty=ty, tx=tx,
                stream=STREAM, pose_id=pose.resource_key(), llr_ref=llr.ref,
                observed_ref=mask.ref,
                calibration_id=_calibration_key(pose.window_id))))
    return writes, blobs


def _certify(tiles: tuple[tuple[int, int], ...]) -> tuple[list[Write], list]:
    """Certified records whose re-encode IS the printed page (P2's law)."""
    writes: list[Write] = []
    blobs = []
    for ty, tx in tiles:
        bits = USER_BITS[(ty, tx)]
        symbol = stage_array(np.asarray(bits[1:], np.uint8))
        blobs.append(symbol)
        writes.append(Write(tile_key(0, ty, tx, STREAM), TileRecord(
            minting=MintRef(POSE.resource_key(), "scan", "bp-60"),
            bits_ref=symbol.ref, metadata_bit=int(bits[0]),
            observed_by=(FOOTING,))))
    return writes, blobs


def _open(tiles: tuple[tuple[int, int], ...]) -> list[Write]:
    """Addressed-but-uncertified records — the residue RF1 gains on."""
    return [Write(tile_key(0, ty, tx, STREAM),
                  TileRecord(observed_by=(FOOTING,))) for ty, tx in tiles]


def _seed(store: Store, *, certified: tuple[tuple[int, int], ...],
          pose: PoseRecord = POSE, band_cells: int = 0) -> CommitEngine:
    engine = CommitEngine(store)
    writes = list(_ground())
    blobs = [SUPPORT_MASK, CAL_PARAMS]
    placement, staged = _placement(pose, band_cells=band_cells)
    writes += placement
    blobs += staged
    certify, certify_blobs = _certify(certified)
    writes += certify
    blobs += certify_blobs
    writes += _open(tuple(t for t in TILES if t not in certified))
    engine.apply(CommitBatch(writes=tuple(writes), blobs=tuple(blobs)))
    return engine


class _View:
    """The plane reads RF1 makes, over a real store and real pixels."""

    def __init__(self, store: Store, *, pixels: bool = True) -> None:
        self._store = store
        self._index = StoreIndex.build(store)
        self._tiles = TileMap(self._index, (STREAM,), (2, 2))
        self._pixels = pixels

    def index(self) -> StoreIndex:
        return self._index

    def record(self, key: ResourceKey) -> object | None:
        return self._store.get(key)

    def read_array(self, ref) -> np.ndarray:
        return self._store.read_array(ref)

    def tile(self, key: ResourceKey):
        return self._tiles.record(key)

    def region(self, region_id: ResourceKey):
        return region_id

    def has_region(self, region_id: ResourceKey) -> bool:
        return True

    def has_footing_pixels(self, footing_id: FootingId) -> bool:
        return self._pixels

    def prepared_region(self, region, *, config, footing_id=None):
        return PREPARED if self._pixels else None

    def footing_frame(self, footing_id: FootingId) -> FootingFrame:
        return FRAME

    def footing_depth(self, footing_id: FootingId) -> int:
        return 0


def _worker(pose: ResourceKey | None = None) -> PoseRefineWorker:
    # A FRESH label source per worker, as H5 P1's fixture does: the caches
    # belong to the provider in production, and sharing one here would
    # hide a re-encode that never happened.
    return PoseRefineWorker(pose or POSE.resource_key(), REFERENCE,
                            CertifiedLabelSource(REFERENCE),
                            PlacementConfig())


def _fire(engine: CommitEngine, *, pixels: bool = True):
    worker = _worker()
    result = worker.run(_View(engine.store, pixels=pixels), (),
                        ProgressSink("refine"))
    if result.writes:
        engine.apply(CommitBatch(writes=result.writes, blobs=result.blobs))
    return result


def _input(pose_affine: tuple[float, ...] = WRONG_AFFINE) -> tuple:
    """One ``RefineInput`` and its labels, without a store in the way.

    The gate tests drive :func:`refine.propose` directly: the plumbing
    around it has its own pins, and what these need is the ability to move
    ONE input at a time.
    """
    cells = np.stack(np.meshgrid(np.arange(CELLS_Y), np.arange(CELLS_X),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    segment, local = refine.local_segment(pose_affine, FRAME, cells)
    means = refine.sample_at(FILTERED, (0, 0), BACKING, segment.pose, local)
    calibration = Calibration(str(WINDOW), CAL_KNOTS, CAL_PROBS, 400)
    labels = refine.collect_labels(0, cells, REFERENCE, _EnrichedAll())
    data = RefineInput(0, segment, local, cells, means, calibration,
                       FILTERED, (0, 0), BACKING)
    return data, labels


class _EnrichedAll:
    """Every cell of the page as a label — the fully-certified frontier."""

    spec = SPEC

    def page(self, page: int):
        base = REFERENCE.page(page)
        return type(base)(page, PAGE_CELLS, np.ones_like(base.sites, bool))


# ------------------------------------------------------ pin (b): the bounds

def test_every_proposable_offset_is_inside_the_carried_bounds() -> None:
    """No candidate the grid can reach violates +-0.15 deg / +-0.25 cell.

    The coarse stage lands ON the boundary by construction (its step IS
    the limit), and the fine stage walks a coarse step OUTWARD from
    whichever coarse key won — so without re-clipping it would propose
    0.30 deg. Both stages are enumerated here from the worst-case corner,
    which is the one that would escape.
    """
    coarse = refine.candidate_grid()
    assert (-refine.ANGLE_LIMIT_DEG, -refine.PHASE_LIMIT_CELLS,
            -refine.PHASE_LIMIT_CELLS) in coarse
    assert (refine.ANGLE_LIMIT_DEG, refine.PHASE_LIMIT_CELLS,
            refine.PHASE_LIMIT_CELLS) in coarse
    for corner in coarse:
        for dtheta, du, dv in refine.fine_grid(corner):
            assert abs(dtheta) <= refine.ANGLE_LIMIT_DEG + 1e-12
            assert abs(du) <= refine.PHASE_LIMIT_CELLS + 1e-12
            assert abs(dv) <= refine.PHASE_LIMIT_CELLS + 1e-12


def test_the_fine_stage_actually_reaches_the_boundary() -> None:
    """The clipping is a bound, not a truncation that never bites.

    A test that only asserted "nothing exceeds the limit" would pass on a
    grid that timidly stopped short; this one requires the boundary
    itself to be proposable, so the bound is TIGHT.
    """
    fine = refine.fine_grid((refine.ANGLE_LIMIT_DEG,
                             refine.PHASE_LIMIT_CELLS,
                             refine.PHASE_LIMIT_CELLS))
    assert any(abs(row[0] - refine.ANGLE_LIMIT_DEG) < 1e-12 for row in fine)
    assert any(abs(row[1] - refine.PHASE_LIMIT_CELLS) < 1e-12 for row in fine)
    # And the outward walk really would have escaped without the clip.
    assert refine.ANGLE_LIMIT_DEG + refine.ANGLE_COARSE_STEP_DEG > \
        refine.ANGLE_LIMIT_DEG


def test_a_revision_moves_the_pose_by_a_bounded_cell_offset() -> None:
    """The adopted geometry, measured where the bound is stated: in CELLS.

    A term inside +-0.25 is only half the promise; what it has to mean is
    that the sampled points move by less than a quarter cell. This
    measures the actual displacement of the window's own corner in cell
    units through the base Jacobian.
    """
    data, labels = _input()
    verdict = refine.propose(data, labels, FRAME)
    assert verdict.adopted, verdict.reason
    assert abs(verdict.dtheta_deg) <= refine.ANGLE_LIMIT_DEG + 1e-12
    assert abs(verdict.du_cells) <= refine.PHASE_LIMIT_CELLS + 1e-12
    assert abs(verdict.dv_cells) <= refine.PHASE_LIMIT_CELLS + 1e-12


# ------------------------------------------------------- pin (c): the gates

def test_the_adopt_arm_walks_toward_the_true_pose() -> None:
    """A wrong pose over real pixels is corrected, and the gain is real.

    Not merely "something adopted": the revision has to reduce the
    held-out log-loss (that IS the first gate) and it has to move the
    geometry in the direction of the pose the page was rendered under.

    WHICH HALF OF ``select_best`` IS DOING THE WORK, stated so nobody
    reads more into this than it says. ``_pose_objective`` normalises by
    the population spread, so on a two-level page under a symmetric blur
    a small translation maps the samples almost exactly affinely and the
    contrast is INVARIANT to it (measured: bit-identical at 0.0 and
    -0.125). The winner here is therefore chosen by v1's tie-break — the
    training log-loss — which is exactly what v1 does when contrasts tie
    within 1e-9. The contrast arm is live, just flat near the optimum: it
    drops to 1.80 from 2.00 once an offset walks toward the neighbouring
    cell (+0.25), which is what keeps the search from wandering.
    """
    data, labels = _input()
    verdict = refine.propose(data, labels, FRAME)
    assert verdict.adopted, verdict.reason
    assert verdict.candidate_logloss is not None
    assert verdict.baseline_logloss is not None
    assert (verdict.candidate_logloss + refine.MIN_HELDOUT_GAIN
            < verdict.baseline_logloss)
    # The committed pose is 0.14 cell too far along both axes, so the
    # correction must be NEGATIVE on both and must not overshoot the
    # bound. This is the whole reason the fixture renders a real page.
    assert verdict.du_cells < 0.0 and verdict.dv_cells < 0.0
    assert abs(verdict.du_cells + POSE_ERROR_CELLS) < 0.1
    assert abs(verdict.dv_cells + POSE_ERROR_CELLS) < 0.1


def test_a_correct_pose_is_refused_with_its_reason() -> None:
    """The refuse arm: nothing to gain, so nothing is adopted.

    Fired on the TRUE pose, the held-out gain gate cannot clear — the
    baseline is already the optimum — and the fire returns a reason
    rather than geometry. This is the arm that must never be lossy: a
    refusal leaves the standing pose untouched.
    """
    data, labels = _input(TRUE_AFFINE)
    verdict = refine.propose(data, labels, FRAME)
    assert not verdict.adopted
    assert verdict.reason in ("pose_gate_failed", "active_pose_selected")
    assert verdict.affine is None


def test_the_heldout_gain_gate_is_strict_at_its_own_constant() -> None:
    """v1's ``MIN_HELDOUT_GAIN``, exercised on both sides of the line."""
    assert refine.adoption_gate(1.0, 1.0 - 2 * refine.MIN_HELDOUT_GAIN,
                                0.1, 0.1, 0.1, 0.1)
    assert not refine.adoption_gate(1.0, 1.0 - refine.MIN_HELDOUT_GAIN / 2,
                                    0.1, 0.1, 0.1, 0.1)
    # Exactly at the constant is a REFUSAL: the comparison is strict.
    assert not refine.adoption_gate(1.0, 1.0 - refine.MIN_HELDOUT_GAIN,
                                    0.1, 0.1, 0.1, 0.1)


def test_both_pilot_gates_veto_a_candidate_that_wins_on_logloss() -> None:
    """Either non-regression alone is enough to refuse — v1's conjunction.

    A candidate with a large held-out gain is rejected when the
    CALIBRATED pilot mismatch regresses past the slack, and again,
    independently, when the RAW one does. The raw gate is the
    detector-free one: it is what stops a candidate buying log-loss by
    moving somewhere the luma no longer separates pilots.
    """
    gain = (1.0, 0.5)
    assert refine.adoption_gate(*gain, 0.10, 0.10, 0.10, 0.10)
    slack = refine.PILOT_MISMATCH_SLACK
    assert refine.adoption_gate(*gain, 0.10, 0.10 + slack, 0.10, 0.10)
    assert not refine.adoption_gate(*gain, 0.10, 0.10 + 2 * slack, 0.10, 0.10)
    assert refine.adoption_gate(*gain, 0.10, 0.10, 0.10, 0.10 + slack)
    assert not refine.adoption_gate(*gain, 0.10, 0.10, 0.10, 0.10 + 2 * slack)


def test_a_label_starved_pose_refuses_on_the_carried_floor(new_store) -> None:
    """No certified cargo, no revision — v1's payload-train floor, live.

    Driven through the FIRE rather than the arithmetic, because the
    reason a starved pose reaches the floor at all is the plumbing: the
    labels come from the committed frontier over the cells this pose
    ACTUALLY OBSERVED, so a clipped window that saw an 8x8 corner of a
    certified tile carries ~48 cargo training labels against a floor of
    64 and refuses by name.
    """
    engine = _seed(new_store(), certified=((0, 0),), band_cells=8)
    result = _fire(engine)
    assert result.outcome == (refine.OUTCOME_REFUSED_PREFIX
                              + "insufficient_payload_train")
    assert not result.writes


# ------------------------------------------------- pin (d): the eligibility

def test_a_fully_certified_reach_mints_nothing(new_store) -> None:
    """The e024 gate. A pose with nothing left to gain is never offered.

    This is the property the whole family's cost rests on: on material
    that certifies cleanly, RF1 does not decline work — it never derives
    any.
    """
    engine = _seed(new_store(), certified=TILES)
    view = _View(engine.store)
    found = refine.reach(view, POSE.resource_key())
    assert found.certified and not found.open
    assert not found.eligible


def test_one_uncertified_tile_in_reach_mints_exactly_one(new_store) -> None:
    """Eligibility is expansion (§3a), and its granularity is the POSE.

    One descriptor per eligible (window, pose) — never one per tile and
    never one per route — so a window with three certified tiles and one
    open one buys exactly one bounded revision.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    view = _View(engine.store)
    found = refine.reach(view, POSE.resource_key())
    assert len(found.open) == 1 and len(found.certified) == 3
    assert found.eligible
    live = {pose for pose, row in refine.reaches(view).items() if row.eligible}
    assert live == {POSE.resource_key()}


def test_no_certified_material_in_reach_is_also_ineligible(new_store) -> None:
    """The other half: certified cargo IS the label channel.

    A pose with residue but no certificates has nothing to learn from, so
    it is not offered a revision either. Both halves are one derivation,
    which is what keeps the family from paying a full grid walk to reach
    a floor it could have predicted.
    """
    engine = _seed(new_store(), certified=())
    view = _View(engine.store)
    found = refine.reach(view, POSE.resource_key())
    assert found.open and not found.certified
    assert not found.eligible


def test_a_new_certificate_in_reach_re_arms_the_descriptor(new_store) -> None:
    """The spend identity's second half: the certificate-frontier version.

    The read-set names ``COLLECTION_CERTIFIED``, so the arrival of a
    certificate bumps a key the descriptor already declared and the
    engine re-offers it. Nothing else can move: evidence is frozen and
    the pose's affine is its own name.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1)))
    worker = _worker()
    keys = worker.read_keys(_View(engine.store))

    assert set(keys) == {COLLECTION_CERTIFIED, POSE.resource_key()}
    before = _View(engine.store).index().certified_tiles
    certify, blobs = _certify(((1, 0),))
    engine.apply(CommitBatch(writes=tuple(certify), blobs=tuple(blobs)))
    after = _View(engine.store).index().certified_tiles
    assert after != before, "the frontier the read-set names must move"


def test_a_quarantined_pose_is_never_offered_a_revision(new_store) -> None:
    """Condemned material never labels and never seeds a revision.

    ``is_quarantined``'s reader here is expansion, so the descriptor is
    not merely declined — it is never derived, exactly as a condemned
    pose never enters a calibration pool.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    assert refine.reach(_View(engine.store), POSE.resource_key()).eligible
    engine.apply(CommitBatch(writes=(
        Write(POSE.resource_key(), replace(POSE, quarantined=True)),)))
    view = _View(engine.store)
    assert not refine.reach(view, POSE.resource_key()).eligible
    assert not refine.reaches(view)
    result = _fire(engine)
    assert result.outcome == refine.OUTCOME_REFUSED_PREFIX + "no_live_pose"


def test_an_empty_reach_is_ineligible_rather_than_an_error() -> None:
    """A pose nobody observed through: no pieces, no reach, no work."""
    empty = Reach((), (), ())
    assert not empty.eligible


# ------------------------------------------------ pin (e): done inviolable

def test_an_adopted_revision_writes_one_new_pose_and_nothing_else(
        new_store) -> None:
    """The proposal shape, asserted as a property of the WRITES.

    An adopted revision proposes exactly one record, it is a
    ``PoseRecord``, and its key is NEW. No tile, no evidence, no
    certificate and no calibration is touched — which is what makes "done
    is inviolable" structural here rather than a claim: this family
    cannot express such a write.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    result = _fire(engine)
    assert result.outcome == refine.OUTCOME_ADOPTED, result.outcome
    assert len(result.writes) == 1
    write = result.writes[0]
    assert isinstance(write.record, PoseRecord)
    assert write.key.kind == "pose"
    assert write.key != POSE.resource_key()


def test_the_standing_pose_survives_its_own_revision(new_store) -> None:
    """Nothing is retracted: the old pose is still committed afterwards.

    The pull model's own shape — a revision is a PROPOSAL, and a proposal
    that lands is a new fact beside the old one, not a mutation of it.
    Readers re-arm through the window's pose collection, which versions
    on the new member like any other placement.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    result = _fire(engine)
    assert result.outcome == refine.OUTCOME_ADOPTED
    assert engine.store.get(POSE.resource_key()) == POSE
    revised = engine.store.get(result.writes[0].key)
    assert isinstance(revised, PoseRecord)
    assert revised.window_id == POSE.window_id
    assert revised.page == POSE.page
    assert revised.native_affine != POSE.native_affine


def test_a_revision_changes_no_certificate(new_store) -> None:
    """The zero-wrong invariant's own reading of pin (e).

    Every certified record is byte-identical before and after the fire —
    asserted over the records themselves rather than over a count, so a
    silent re-mint would fail it too.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    keys = tuple(_View(engine.store).index().certified_tiles)
    before = {key: engine.store.get(key) for key in keys}
    result = _fire(engine)
    assert result.outcome == refine.OUTCOME_ADOPTED
    after = {key: engine.store.get(key) for key in keys}
    assert after == before
    assert tuple(_View(engine.store).index().certified_tiles) == keys


def test_the_revised_pose_is_an_ordinary_pose(new_store) -> None:
    """No new durable record kind: a revised pose IS a pose.

    Its key rebuilds from its own values (F-07's law, which every pose
    obeys), it carries the same window and page, and it is not marked in
    any way — nothing downstream can tell it apart from a first fit,
    which is precisely why nothing downstream needs to.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    result = _fire(engine)
    revised = result.writes[0].record
    assert revised.resource_key() == result.writes[0].key
    assert revised.quarantined is False
    assert set(vars(revised)) == set(vars(POSE))


def test_a_fire_without_pixels_refuses_instead_of_raising(new_store) -> None:
    """A detached capture declines; it does not cross the worker boundary.

    The same M12 discipline the placement source keeps: no pixels is a
    refusal with a reason, never a ``KeyError`` escaping a fire.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    result = _fire(engine, pixels=False)
    assert result.outcome == refine.OUTCOME_REFUSED_PREFIX + "no_pixels"
    assert not result.writes


# --------------------------------------------- generation-zero calibration

def test_the_replayed_calibration_is_the_committed_one(new_store) -> None:
    """Frozen replay: the knots and probabilities are the durable ones."""
    engine = _seed(new_store(), certified=((0, 0),))
    replayed = refine.replay_calibration(_View(engine.store), WINDOW,
                                         _calibration_key())
    assert replayed is not None
    assert np.array_equal(replayed.knots, CAL_KNOTS)
    assert np.array_equal(replayed.probabilities, CAL_PROBS)


def test_the_reconstructed_n_search_cannot_change_a_logit() -> None:
    """The one value the params blob does not carry, proven inert.

    ``Calibration.llr`` reads knots and probabilities only, so every
    legal ``n_search`` yields BIT-IDENTICAL logits and the reconstruction
    exists solely to satisfy a constructor's support check. Asserted the
    strong way — byte equality, over a wide span of legal values.
    """

    scores = np.linspace(-220.0, -30.0, 512)
    reference = Calibration(str(WINDOW), CAL_KNOTS, CAL_PROBS, 400).llr(scores)
    for n_search in (49, 98, 400, 4096, 100_000):
        other = Calibration(str(WINDOW), CAL_KNOTS, CAL_PROBS, n_search)
        assert np.array_equal(other.llr(scores), reference)


def test_a_missing_calibration_refuses_by_name(new_store) -> None:
    """Generation zero must be replayable; if it is not, say so."""
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    assert refine.replay_calibration(
        _View(engine.store), WINDOW,
        calibration_key(WINDOW, "pava-v1", "ff" * 32)) is None


# ------------------------------------------------------------ the provider

def test_the_provider_mints_one_descriptor_per_eligible_pose(new_store) -> None:
    """Expansion end to end, over the real record shapes."""


    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    provider = PoseRefineProvider(format_row("c2-k-r0550", (2, 2)), revise=True)
    minted = provider.expand(_View(engine.store), ExpansionRequest("entry"))
    assert len(minted) == 1
    assert minted[0].subject == POSE.resource_key()
    assert minted[0].route == refine.ROUTE_REFINE_K
    assert minted[0].family == refine.FAMILY_REFINE


def test_the_provider_mints_nothing_when_the_page_is_done(new_store) -> None:
    """The no-op that keeps RF1 free on material that certifies cleanly."""


    engine = _seed(new_store(), certified=TILES)
    provider = PoseRefineProvider(format_row("c2-k-r0550", (2, 2)), revise=True)
    assert provider.expand(_View(engine.store),
                           ExpansionRequest("entry")) == ()


def test_the_production_dial_is_ON_and_the_off_arm_mints_nothing(
        new_store) -> None:
    """RE-PINNED W3 (RULING I2, the user's ruling of 2026-08-23).

    OLD: ``revise`` defaulted to FALSE and this asserted the composition
    root derived no refinement work at all. The two rulings H5 P4 was
    waiting on have been made — the barrier translation is the top price
    (``COST_REFINE`` = 200) and a window MAY carry more than one
    committed pose, with "the latest committed wins" derived at the
    consumers — so the default is TRUE and the family is live in every
    stock decode.

    What the re-pin keeps rather than drops: ``revise=False`` still mints
    NOTHING — not a descriptor that declines, which would still cost a
    spend and a wake — because that arm is what a dial-off CONTROL binds
    when a measurement has to attribute a change to this family (W2's
    ``rf1_resume.py --no-revise``). Both arms are asserted here, over the
    same eligible frontier, so neither can quietly stop meaning what it
    says.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    row = format_row("c2-k-r0550", (2, 2))
    live = PoseRefineProvider(row)
    assert live.revise is True
    assert len(live.expand(_View(engine.store), ExpansionRequest("entry"))) == 1

    control = PoseRefineProvider(row, revise=False)
    assert control.expand(_View(engine.store), ExpansionRequest("entry")) == ()
    # And the eligibility really would have minted one, so the control
    # arm is silenced by its dial and not by an empty frontier.
    assert refine.reach(_View(engine.store), POSE.resource_key()).eligible


# ------------------------------------------ RULING I4: no pose spam (W3)

def test_a_window_revised_twice_to_the_same_affine_holds_one_pose(
        new_store) -> None:
    """RULING I4 (user, 2026-08-23): a no-op revision is not committed.

    THE FORK it names: committing every adopted fit. The certificate
    frontier re-arms this descriptor at k=1 — every new certificate in
    reach — so a search that keeps landing on the answer it already gave
    would mint a fresh ``PoseRecord`` per wake, and an extent's pose
    collection would grow without bound while its LIVE pose never moved.

    Fired twice over an unmoved store, so the second fit is the first
    one's answer exactly. One revision stands and the second fire commits
    nothing.

    WHICH GUARD SAYS SO MOVED AT F2a (2026-08-23, ruling J2-3). Through
    W3 the second fire reached the search and refused ``pose_unmoved``
    (the affine equals the standing live pose). Since F2a an extent that
    already carries a revision offers NO subject at all — neither the
    revision nor the parent — so the refusal is
    ``extent_already_revised`` and it happens before a pixel is read.
    The property this test exists for is unchanged and now holds by a
    STRICTLY STRONGER rule; the no-op guard is pinned on its own, on a
    single-pose extent, by the sibling below.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    first = _fire(engine)
    assert first.outcome == refine.OUTCOME_ADOPTED
    revised = first.writes[0].key
    assert StoreIndex.build(engine.store).live_pose(WINDOW) == revised

    second = _fire(engine)
    assert second.outcome == (refine.OUTCOME_REFUSED_PREFIX
                              + "extent_already_revised")
    assert not second.writes
    index = StoreIndex.build(engine.store)
    assert index.poses_by_window[WINDOW] == tuple(
        sorted((POSE.resource_key(), revised))), "one revision, not two"
    assert index.live_pose(WINDOW) == revised
    assert not refine.reach(_View(engine.store), POSE.resource_key()).eligible


def test_a_fit_that_returns_to_the_standing_pose_commits_nothing(
        new_store, monkeypatch) -> None:
    """The NO-OP GUARD itself (RULING I4), on a single-pose extent.

    THE FORK: committing a ``PoseRecord`` whose canonical affine equals
    the one already standing. A pose IS its affine, so that is a second
    record for one geometry — the pose collection grows, every reader of
    it re-arms, and the live pose never moves.

    Staged where the guard actually lives since F2a: an extent with ONE
    committed pose, whose search is made to return that pose's own
    geometry. On an extent that already carries a revision the earlier
    guard (``extent_already_revised``) fires first, which is what the
    sibling above pins.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    monkeypatch.setattr(refine, "propose", lambda *_args: refine.Revision(
        adopted=True, reason="staged", affine=tuple(POSE.native_affine)))
    result = _fire(engine)
    assert result.outcome == (refine.OUTCOME_REFUSED_PREFIX + "pose_unmoved")
    assert not result.writes
    assert StoreIndex.build(engine.store).poses_by_window[WINDOW] == (
        POSE.resource_key(),)


def test_a_revision_that_moves_the_affine_moves_the_live_pose(
        new_store) -> None:
    """The other side of the guard: a DIFFERENT answer is a new pose.

    The guard refuses geometry that already stands and nothing else, so a
    fit that lands somewhere new commits — and the extent's live pose
    follows it, while both earlier poses stay committed and unmarked.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    adopted = _fire(engine)
    assert adopted.outcome == refine.OUTCOME_ADOPTED
    revised = adopted.writes[0].record

    moved = PoseRecord(window_id=revised.window_id,
                       footing_id=revised.footing_id, page=revised.page,
                       native_affine=tuple(revised.native_affine[:2])
                       + (revised.native_affine[2] + 0.5,)
                       + tuple(revised.native_affine[3:]))
    engine.apply(CommitBatch(writes=(Write(moved.resource_key(), moved),)))

    index = StoreIndex.build(engine.store)
    assert index.live_pose(WINDOW) == moved.resource_key()
    assert len(index.poses_by_window[WINDOW]) == 3
    assert all(not index.poses[key].quarantined
               for key in index.poses_by_window[WINDOW]), (
        "nothing a revision supersedes is marked in any way")


def test_an_extent_that_carries_a_revision_offers_no_subject(
        new_store) -> None:
    """F2a (ruling J2-3, 2026-08-23): at most TWO poses on one extent.

    THE FORK: leaving "a revision is never itself eligible" as an
    accident. Through F1 it held because eligibility is derived from
    EVIDENCE and a revision had none. F2a's re-sample gives a revision
    evidence, so without this clause the tree would chain revisions off
    revisions — and, worse, the PARENT would stay eligible off its own
    now-superseded evidence and could mint a THIRD geometry. A third
    generation makes ``solve.generation``'s rule under-determined (a
    live pose with no pieces above a second generation that has some),
    which is why the bound is structural and stated in both modules.

    Both poses of the extent are checked, because the clause is over the
    EXTENT and not over one pose.

    WHAT THIS TEST RETIRED, and the fork a future package owes a pin
    for: ``refused_pose_already_stands`` — the branch that names a fit
    landing on an EARLIER revision — is now unreachable through this
    family's own door, because reaching it needs the two-pose extent this
    clause refuses. The branch is kept as the total spelling of "a pose
    is its affine" (``PoseRefineWorker.run``); a package that lifts the
    chaining bar owes it a pin again, and owes ``generation`` a commit
    ordinal.
    """
    engine = _seed(new_store(), certified=((0, 0), (0, 1), (1, 0)))
    adopted = _fire(engine)
    assert adopted.outcome == refine.OUTCOME_ADOPTED
    revision = adopted.writes[0].key

    view = _View(engine.store)
    parent = refine.reach(view, POSE.resource_key())
    assert parent.revised and not parent.eligible, (
        "the parent of a revised extent stops being a subject too")
    assert not refine.reach(view, revision).eligible

    again = _fire(engine)
    assert again.outcome == (refine.OUTCOME_REFUSED_PREFIX
                             + "extent_already_revised")
    assert not again.writes


def test_a_done_tile_is_never_re_posed(new_store) -> None:
    """The eligibility pin, stated as the ruling states it (I3).

    "Done tiles never change pose (eligibility: nothing to buy)" — and it
    is structural rather than checked: a pose whose whole reach is
    certified mints no descriptor, so no fire exists to propose one, and
    the family cannot express a write that touches a tile at all.

    SCOPE, corrected by the W3 review (2026-08-23). This is exactly the
    FULLY-certified reach, which is the case eligibility already excludes.
    An eligible pose's reach is by definition PART certified and part
    open (``Reach.eligible``), so a revision of it does re-project the
    certified half's tiles through new geometry — the done map is taken
    at the live pose, not at the pose that spent the pixels. The ruled
    clause is about POSE OWNERSHIP of a done tile's certificate, which no
    revision touches; the projection caveat lives in
    ``tilemap.project_done`` and ``solve/DESIGN.md`` §6.
    """
    engine = _seed(new_store(), certified=TILES)
    view = _View(engine.store)
    provider = PoseRefineProvider(format_row("c2-k-r0550", (2, 2)))
    assert provider.expand(view, ExpansionRequest("entry")) == ()
    before = StoreIndex.build(engine.store)
    assert before.live_pose(WINDOW) == POSE.resource_key()

    # And the fire, if one were staged by hand, refuses before a pixel.
    result = _worker().run(view, (), ProgressSink("refine"))
    assert result.outcome == (refine.OUTCOME_REFUSED_PREFIX
                              + "no_uncertified_residue")
    assert not result.writes
    assert StoreIndex.build(engine.store).live_poses == before.live_poses
